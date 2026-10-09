from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, shutil
from routes.state import *
from routes.security import is_path_allowed, safe_join, sanitize_unicode_filename
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
        isolate_vocals = data.get('isolateVocals', False)
        if isinstance(isolate_vocals, str):
            isolate_vocals = isolate_vocals.strip().lower() in {'1', 'true', 'yes', 'on'}
        else:
            isolate_vocals = bool(isolate_vocals)
        video_path = data.get('videoPath')
        output_dir = data.get('outputDir') or 'output'
        output_filename = data.get('outputFilename') or 'phude_video'
        if not output_filename.endswith('.srt'):
            output_filename += '.srt'

        if model_name not in _ASR_MODELS or language not in _ASR_LANGUAGES:
            return jsonify({'success': False, 'error': 'Model hoặc ngôn ngữ ASR không hợp lệ'}), 400

        if video_path:
            video_path = video_path.strip(' "\'')

        if not video_path:
            return jsonify({"success": False, "error": "Chưa cung cấp đường dẫn video đầu vào"}), 400

        if not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
            from routes.core import find_media_on_system
            resolved = find_media_on_system(video_path)
            if resolved and is_path_allowed(resolved, must_exist=True, extensions=_VIDEO_EXTENSIONS):
                video_path = resolved
            elif os.path.exists(video_path) and os.path.splitext(video_path)[1].lower() in _VIDEO_EXTENSIONS:
                from routes.security import register_user_path
                register_user_path(video_path)
            else:
                return jsonify({"success": False, "error": f"Video đầu vào không hợp lệ hoặc chưa được cấp quyền. Đường dẫn: '{video_path}'"}), 400

        if not os.path.isabs(output_dir):
            output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
        if not is_path_allowed(output_dir):
            return jsonify({'success': False, 'error': 'Thư mục đầu ra chưa được người dùng cho phép'}), 403
        os.makedirs(output_dir, exist_ok=True)
        output_filename = sanitize_unicode_filename(output_filename, default='subtitles.srt', default_ext='.srt')
        if not output_filename:
            return jsonify({'success': False, 'error': 'Tên file đầu ra không hợp lệ'}), 400
        output_srt_path = safe_join(output_dir, output_filename, extensions={'.srt'})

        with _asr_lock:
            if _asr_job_active:
                return jsonify({'success': False, 'error': 'Một tác vụ ASR khác đang chạy'}), 409
            _asr_job_active = True
            _asr_cancel_requested = False

        # Chuẩn bị lệnh chạy
        asr_start_time = time.time()
        temp_audio = os.path.join(output_dir, f"temp_asr_{int(time.time()*1000)}.wav")
        temp_sep_dir = os.path.join(output_dir, f".asr_vocals_{int(time.time()*1000)}") if isolate_vocals else None
        base_out_no_ext = os.path.splitext(output_srt_path)[0]

        def generate():
            import subprocess
            global current_asr_process, _asr_job_active, _asr_cancel_requested
            process = None
            try:
                import asr_manager
                whisper_cli = asr_manager.get_whisper_cli()
                model_path = asr_manager.get_whisper_model_path(model_name)
                python_exec = asr_manager.get_python_exec()
                gpu_available = False
                if device in {"auto", "cuda"}:
                    try:
                        gpu_probe = subprocess.run(
                            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                            capture_output=True, text=True, timeout=5,
                            creationflags=0x08000000 if os.name == "nt" else 0
                        )
                        gpu_available = gpu_probe.returncode == 0 and bool(gpu_probe.stdout.strip())
                    except Exception:
                        gpu_available = False
                use_gpu_asr = bool(gpu_available and python_exec)
                if use_gpu_asr:
                    try:
                        fw_probe = subprocess.run(
                            [python_exec, "-c", "import faster_whisper"],
                            capture_output=True, text=True, timeout=12,
                            creationflags=0x08000000 if os.name == "nt" else 0
                        )
                        use_gpu_asr = fw_probe.returncode == 0
                    except Exception:
                        use_gpu_asr = False
                if use_gpu_asr:
                    yield "[HARDWARE] ASR ưu tiên GPU CUDA (Faster-Whisper); CPU chỉ dùng khi GPU lỗi.\n"

                source_for_asr = video_path
                if isolate_vocals:
                    yield "[STEP] 🎙️ Đang tách giọng thoại khỏi nhạc nền bằng AI (UVR/MDX)...\n"
                    try:
                        import audio_separator
                        os.makedirs(temp_sep_dir, exist_ok=True)
                        separation_logs = []
                        separated = audio_separator.separate_audio_stems(
                            input_media_path=video_path, output_dir=temp_sep_dir,
                            remove_vocals=False, remove_bgm=True, keep_sfx=False,
                            mode="mdx_net_voc_ft",
                            device=device if device in {"auto", "cpu", "cuda"} else "auto",
                            logger_cb=lambda msg: separation_logs.append(str(msg))
                        )
                        for separation_log in separation_logs:
                            yield f"[HARDWARE] {separation_log}\n" if "Hardware:" in separation_log or "ExecutionProvider" in separation_log else f"[STEP] {separation_log}\n"
                        candidate = separated.get("vocals_path") if isinstance(separated, dict) else None
                        if candidate and os.path.exists(candidate) and os.path.getsize(candidate) > 500:
                            source_for_asr = candidate
                            yield "[STEP] ✅ Đã tách xong vocal; ASR sẽ chỉ nhận giọng thoại.\n"
                        else:
                            yield "[STEP] ⚠️ Không tìm thấy file vocal sau khi tách; tiếp tục với audio gốc.\n"
                    except Exception as separation_error:
                        yield f"[STEP] ⚠️ Tách vocal không khả dụng ({separation_error}); tiếp tục với audio gốc.\n"

                # 1. Tự động tải môi trường nếu chưa có
                if not use_gpu_asr and (not whisper_cli or not model_path):
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
                    ff_bin, "-y", "-i", source_for_asr,
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
                if use_gpu_asr:
                    yield "[STEP] 🚀 Bắt đầu nhận dạng bằng Faster-Whisper CUDA...\n"
                    asr_script = os.path.join(ROOT_DIR, "asr_inference.py")
                    cmd = [python_exec, "-u", asr_script, source_for_asr, model_name, output_srt_path, language, "cuda"]
                elif whisper_cli and model_path:
                    dev_label = "Tự động tối ưu" if device == 'auto' else device.upper()
                    yield f"[HARDWARE] ASR sử dụng CPU (Whisper Native C++; GPU CUDA không khả dụng hoặc runtime GPU chưa sẵn sàng).\n"
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
                    if not python_exec:
                        import json
                        yield f"\n[RESULT] {json.dumps({'success': False, 'error': 'Không thể khởi tạo môi trường Whisper ASR.'})}\n"
                        return
                    asr_script = os.path.join(ROOT_DIR, "asr_inference.py")
                    cmd = [python_exec, "-u", asr_script, source_for_asr, model_name, output_srt_path, language, "cpu"]

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
                    # Gửi thông báo Telegram khi ASR thành công
                    try:
                        from telegram_notifier import get_telegram_notifier
                        notifier = get_telegram_notifier()
                        if notifier.enabled and notifier.notify_per_video:
                            notifier.notify_task_success(
                                task_type='asr',
                                task_title='Trích Xuất Phụ Đề ASR',
                                video_title=os.path.basename(video_path),
                                output_path=output_srt_path,
                                duration_sec=time.time() - asr_start_time,
                                extra_info={
                                    'Model': model_name,
                                    'Ngôn ngữ': language.upper()
                                }
                            )
                    except Exception as _te:
                        logging.getLogger(__name__).warning(f"[Telegram] Error sending ASR notification: {_te}")
                elif process.returncode != 0:
                    err_msg = f'Tiến trình AI kết thúc với mã {process.returncode}'
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': False, 'error': err_msg})}\n"
                    try:
                        from telegram_notifier import get_telegram_notifier
                        notifier = get_telegram_notifier()
                        if notifier.enabled and notifier.notify_per_video and not _asr_cancel_requested:
                            notifier.notify_task_failure(
                                task_type='asr',
                                task_title='Trích Xuất Phụ Đề ASR',
                                video_title=os.path.basename(video_path),
                                error_message=err_msg,
                                duration_sec=time.time() - asr_start_time
                            )
                    except Exception as _te:
                        logging.getLogger(__name__).warning(f"[Telegram] Error sending ASR failure notification: {_te}")
                else:
                    err_msg = 'Không tạo được tệp phụ đề SRT.'
                    import json
                    yield f"\n[RESULT] {json.dumps({'success': False, 'error': err_msg})}\n"
                    try:
                        from telegram_notifier import get_telegram_notifier
                        notifier = get_telegram_notifier()
                        if notifier.enabled and notifier.notify_per_video and not _asr_cancel_requested:
                            notifier.notify_task_failure(
                                task_type='asr',
                                task_title='Trích Xuất Phụ Đề ASR',
                                video_title=os.path.basename(video_path),
                                error_message=err_msg,
                                duration_sec=time.time() - asr_start_time
                            )
                    except Exception as _te:
                        logging.getLogger(__name__).warning(f"[Telegram] Error sending ASR failure notification: {_te}")

            except GeneratorExit:
                _terminate_process_tree(process)
            except Exception as exc:
                yield f"\n[RESULT] {json.dumps({'success': False, 'error': str(exc)})}\n"
                try:
                    from telegram_notifier import get_telegram_notifier
                    notifier = get_telegram_notifier()
                    if notifier.enabled and notifier.notify_per_video and not _asr_cancel_requested:
                        notifier.notify_task_failure(
                            task_type='asr',
                            task_title='Trích Xuất Phụ Đề ASR',
                            video_title=os.path.basename(video_path),
                            error_message=str(exc),
                            duration_sec=time.time() - asr_start_time
                        )
                except Exception as _te:
                    logging.getLogger(__name__).warning(f"[Telegram] Error sending ASR failure notification: {_te}")
            finally:
                with _asr_lock:
                    if current_asr_process is process:
                        current_asr_process = None
                    _asr_job_active = False
                    _asr_cancel_requested = False
                if os.path.exists(temp_audio):
                    try: os.remove(temp_audio)
                    except Exception: pass
                if temp_sep_dir and os.path.isdir(temp_sep_dir):
                    try: shutil.rmtree(temp_sep_dir, ignore_errors=True)
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
