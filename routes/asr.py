from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
import asr_manager

asr_bp = Blueprint('asr', __name__)

@asr_bp.route('/api/asr/check', methods=['POST'])
def asr_check():
    data = request.json or {}
    model_name = data.get('model', 'whisper')
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

@asr_bp.route('/api/asr/install', methods=['GET'])
def asr_install():
    model_name = request.args.get('model', 'whisper')
    import asr_manager
    def generate():
        for log in asr_manager.install_model_stream(model_name):
            yield log
    return Response(generate(), mimetype='text/event-stream')

@asr_bp.route('/api/asr/scan', methods=['POST'])
def asr_scan():
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
        if not allowed:
            return jsonify({"success": False, "error": perm_msg}), 403

        data = request.json or {}
        model_name = data.get('model', 'whisper')
        language = data.get('language', 'auto')
        device = data.get('device', 'auto')
        video_path = data.get('videoPath')
        output_dir = data.get('outputDir') or 'output'
        output_filename = data.get('outputFilename') or 'phude_video'
        if not output_filename.endswith('.srt'):
            output_filename += '.srt'

        if video_path:
            video_path = video_path.strip(' "\'')

        if not video_path or not os.path.exists(video_path):
            return jsonify({"success": False, "error": f"Video đầu vào không hợp lệ. Đường dẫn nhận được: '{video_path}'"})

        os.makedirs(output_dir, exist_ok=True)
        output_srt_path = os.path.join(output_dir, output_filename)

        # Chuẩn bị lệnh chạy
        temp_audio = os.path.join(output_dir, f"temp_asr_{int(time.time()*1000)}.wav")
        base_out_no_ext = os.path.splitext(output_srt_path)[0]

        def generate():
            import subprocess
            global current_asr_process
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
                res_ff = subprocess.run(conv_cmd, capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
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
                    creationflags=0x08000000 if os.name == 'nt' else 0
                )
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
                if 'process' in locals() and process and process.poll() is None:
                    try:
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
                        process.kill()
                    except Exception:
                        pass
            finally:
                current_asr_process = None
                if os.path.exists(temp_audio):
                    try: os.remove(temp_audio)
                    except Exception: pass

        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        import traceback
        import json
        def error_gen():
            yield f"\n[RESULT] {json.dumps({'success': False, 'error': str(e), 'traceback': traceback.format_exc()})}\n"
        return Response(error_gen(), mimetype='text/plain')

@asr_bp.route('/api/stop_asr', methods=['POST'])
@asr_bp.route('/api/asr/stop', methods=['POST'])
def stop_asr():
    global current_asr_process
    if current_asr_process and current_asr_process.poll() is None:
        try:
            import subprocess
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(current_asr_process.pid)], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            current_asr_process.kill()
        except Exception:
            pass
        current_asr_process = None
        return jsonify({'success': True, 'message': 'Đã dừng tiến trình ASR'})
    return jsonify({'success': True, 'message': 'Không có tiến trình ASR nào đang chạy'})

