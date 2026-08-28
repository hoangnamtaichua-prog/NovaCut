from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, shutil
from routes.state import *
from routes.security import is_path_allowed, safe_join
from werkzeug.utils import secure_filename
import asr_manager

asr_bp = Blueprint('asr', __name__)
_asr_lock = threading.RLock()
_asr_job_active = False
_asr_cancel_requested = False
_ASR_MODELS = {'whisper', 'base', 'small', 'medium'}
_ASR_LANGUAGES = {'auto', 'vi', 'en', 'zh', 'ja', 'ko', 'fr', 'es', 'de', 'ru', 'th'}
_VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mp3', '.wav', '.m4a', '.flac'}


def _require_editor():
    import license_manager
    allowed, message, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None


def _terminate_process_tree(process):
    if not process or process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True, timeout=10, creationflags=0x08000000)
        else:
            process.terminate()
            process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass

@asr_bp.route('/api/asr/check', methods=['POST'])
def asr_check():
    data = request.json or {}
    model_name = str(data.get('model', 'whisper')).lower()
    if model_name not in _ASR_MODELS:
        return jsonify({'success': False, 'error': 'Model ASR không được hỗ trợ'}), 400
    import asr_manager
    whisper_cli = asr_manager.get_whisper_cli()
    model_path = asr_manager.get_whisper_model_path(model_name)
    installed = asr_manager.check_model_installed(model_name)
    return jsonify({
        "installed": bool(installed),
        "has_cli": bool(whisper_cli),
        "has_model": bool(model_path),
        "model_name": model_name
    })

@asr_bp.route('/api/asr/install', methods=['POST'])
def asr_install():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    model_name = str(data.get('model', 'whisper')).lower()
    if model_name not in _ASR_MODELS:
        return jsonify({'success': False, 'error': 'Model ASR không được hỗ trợ'}), 400
    import asr_manager
    def generate():
        for log in asr_manager.install_model_stream(model_name):
            yield log
    return Response(generate(), mimetype='text/event-stream')

@asr_bp.route('/api/asr/scan', methods=['POST'])
def asr_scan():
    global _asr_job_active, _asr_cancel_requested
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
        if not allowed:
            return jsonify({"success": False, "error": perm_msg}), 403

        data = request.json or {}
        model_name = str(data.get('model', 'whisper')).lower()
        language = str(data.get('language', 'auto')).lower()
        device = data.get('device', 'auto')
        video_path = data.get('videoPath')
        output_dir = data.get('outputDir') or 'output'
        output_filename = data.get('outputFilename') or 'phude_video'
        if not output_filename.endswith('.srt'):
            output_filename += '.srt'

        if model_name not in _ASR_MODELS or language not in _ASR_LANGUAGES:
            return jsonify({'success': False, 'error': 'Model hoặc ngôn ngữ ASR không hợp lệ'}), 400

        if video_path:
            video_path = video_path.strip(' "\'')

        if not video_path or not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
            return jsonify({"success": False, "error": f"Video đầu vào không hợp lệ. Đường dẫn nhận được: '{video_path}'"})

        if not os.path.isabs(output_dir):
            output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
        if not is_path_allowed(output_dir):
            return jsonify({'success': False, 'error': 'Thư mục đầu ra chưa được người dùng cho phép'}), 403
        os.makedirs(output_dir, exist_ok=True)
        output_filename = secure_filename(output_filename)
        if not output_filename:
            return jsonify({'success': False, 'error': 'Tên file đầu ra không hợp lệ'}), 400
        output_srt_path = safe_join(output_dir, output_filename, extensions={'.srt'})

        with _asr_lock:
            if _asr_job_active:
                return jsonify({'success': False, 'error': 'Một tác vụ ASR khác đang chạy'}), 409
            _asr_job_active = True
            _asr_cancel_requested = False

        # Chuẩn bị lệnh chạy
        temp_audio = os.path.join(output_dir, f"temp_asr_{int(time.time()*1000)}.wav")
        base_out_no_ext = os.path.splitext(output_srt_path)[0]

        def generate():
            import subprocess
            global current_asr_process, _asr_job_active, _asr_cancel_requested
            process = None
            try:
                import asr_manager
                whisper_cli = asr_manager.get_whisper_cli()
                model_path = asr_manager.get_whisper_model_path(model_name)

                # 1. Tự động tải môi trường nếu chưa có
                if not whisper_cli or not model_path:
                    yield "[STEP] 🔍 Đang kiểm tra môi trường ASR trên máy...\n"
                    if not whisper_cli:
                        yield "[STEP] 📥 Chưa có Lõi Whisper C++ Native. Đang tự động tải về (~15 MB)...\n"
                    if not model_path:
                        yield f"[STEP] 🧠 Chưa có Model AI Whisper '{model_name}'. Đang tự động tải về (~140 MB)...\n"
                    
                    for raw_msg in asr_manager.install_model_stream(model_name):
                        clean_msg = raw_msg.replace("data: ", "").strip()
                        if clean_msg and clean_msg != "[INSTALL_DONE]":
                            yield f"[STEP] {clean_msg}\n"
                    
                    whisper_cli = asr_manager.get_whisper_cli()
                    model_path = asr_manager.get_whisper_model_path(model_name)

                # 2. Trích xuất âm thanh 16kHz mono qua FFmpeg
                yield "[STEP] 🎵 Đang trích xuất luồng âm thanh 16kHz Mono từ video...\n"
                import ffmpeg_installer
                ff_bin = ffmpeg_installer.get_ffmpeg_path() or "ffmpeg"
                conv_cmd = [
                    ff_bin, "-y", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    temp_audio
                ]
                process = subprocess.Popen(
                    conv_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 if os.name == 'nt' else 0,
                    start_new_session=os.name != 'nt'
                )
                with _asr_lock:
                    current_asr_process = process
                while process.poll() is None:
                    if _asr_cancel_requested:
                        _terminate_process_tree(process)
                        yield f"\n[RESULT] {json.dumps({'success': False, 'cancelled': True, 'error': 'Đã dừng ASR'})}\n"
                        return
                    time.sleep(0.25)
                if not os.path.exists(temp_audio) or os.path.getsize(temp_audio) < 500:
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': False, 'error': 'Không thể trích xuất âm thanh từ video.'})}\n"
                    return

                # 3. Chạy Native Standalone Whisper C++ Engine
                if whisper_cli and model_path:
                    dev_label = "Tự động tối ưu" if device == 'auto' else device.upper()
                    yield f"[STEP] 🚀 Bắt đầu nhận dạng phụ đề bằng Lõi Whisper Native C++ (Model: {os.path.basename(model_path)}, Luồng: 8)...\n"
                    lang_arg = language if language and language != 'auto' else 'auto'
                    cmd = [
                        whisper_cli,
                        "-m", model_path,
                        "-f", temp_audio,
                        "-osrt",
                        "-of", base_out_no_ext,
                        "-l", lang_arg,
                        "-t", "8",
                        "-pp"
                    ]
                else:
                    python_exec = asr_manager.get_python_exec()
                    if not python_exec:
                        import json
                        yield f"\n[RESULT] {json.dumps({'success': False, 'error': 'Không thể khởi tạo môi trường Whisper ASR.'})}\n"
                        return
                    asr_script = os.path.join(ROOT_DIR, "asr_inference.py")
                    cmd = [python_exec, "-u", asr_script, video_path, model_name, output_srt_path, language]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    bufsize=1,
                    creationflags=0x08000000 if os.name == 'nt' else 0,
                    start_new_session=os.name != 'nt'
                )
                with _asr_lock:
                    current_asr_process = process

                for line in iter(process.stdout.readline, ''):
                    if line:
                        yield line
                
                process.stdout.close()
                process.wait()

                generated_srt = f"{base_out_no_ext}.srt"
                if os.path.exists(generated_srt) and os.path.getsize(generated_srt) > 10:
                    if generated_srt != output_srt_path:
                        shutil.move(generated_srt, output_srt_path)
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': True, 'srt_path': output_srt_path})}\n"
                elif process.returncode != 0:
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': False, 'error': f'Tiến trình AI kết thúc với mã {process.returncode}'})}\n"
                else:
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': False, 'error': 'Không tạo được tệp phụ đề SRT.'})}\n"

            except GeneratorExit:
                _terminate_process_tree(process)
            except Exception as exc:
                yield f"\n[RESULT] {json.dumps({'success': False, 'error': str(exc)})}\n"
            finally:
                with _asr_lock:
                    if current_asr_process is process:
                        current_asr_process = None
                    _asr_job_active = False
                    _asr_cancel_requested = False
                if os.path.exists(temp_audio):
                    try: os.remove(temp_audio)
                    except Exception: pass

        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        with _asr_lock:
            _asr_job_active = False
        def error_gen():
            yield f"\n[RESULT] {json.dumps({'success': False, 'error': str(e)})}\n"
        return Response(error_gen(), mimetype='text/plain')

@asr_bp.route('/api/stop_asr', methods=['POST'])
@asr_bp.route('/api/asr/stop', methods=['POST'])
def stop_asr():
    global current_asr_process, _asr_cancel_requested
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    with _asr_lock:
        _asr_cancel_requested = True
        process = current_asr_process
    if process and process.poll() is None:
        _terminate_process_tree(process)
        return jsonify({'success': True, 'message': 'Đã dừng tiến trình ASR'})
    return jsonify({'success': True, 'message': 'Không có tiến trình ASR nào đang chạy'})

