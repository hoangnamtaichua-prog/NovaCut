from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, requests
from routes.state import *
import asr_manager

core_bp = Blueprint('core', __name__)

@core_bp.after_request
def add_no_cache_headers(response):
    if response.mimetype in ['text/html', 'text/javascript', 'application/javascript', 'text/css']:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@core_bp.route('/')
def index():
    return send_from_directory(os.path.join(ROOT_DIR, 'web'), 'index.html')

@core_bp.route('/<path:path>')
def static_files(path):
    return send_from_directory(os.path.join(ROOT_DIR, 'web'), path)

@core_bp.route('/api/file')
def serve_file():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return "File not found", 404
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        if path.lower().endswith('.wav'):
            mime_type = 'audio/wav'
        elif path.lower().endswith('.mp3'):
            mime_type = 'audio/mpeg'
        elif path.lower().endswith('.srt'):
            mime_type = 'text/plain'
    return send_file(path, mimetype=mime_type, conditional=True)

@core_bp.route('/samples/<path:filename>')
def serve_samples(filename):
    samples_dir = os.path.join(ROOT_DIR, 'web', 'samples')
    return send_from_directory(samples_dir, filename)

@core_bp.route('/api/video')
def stream_video():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return "Video not found", 404
        
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = 'video/mp4'
        
    return send_file(path, mimetype=mime_type, conditional=True)

@core_bp.route('/api/image')
def stream_image():
    raw_path = request.args.get('path', '')
    if not raw_path:
        return "Image not found", 404
        
    path = os.path.normpath(raw_path.strip('\'"'))
    if not os.path.exists(path):
        alt_path = os.path.abspath(path)
        if os.path.exists(alt_path):
            path = alt_path
        else:
            return "Image not found", 404
        
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = 'image/png'
        
    return send_file(path, mimetype=mime_type, conditional=True)

@core_bp.route('/api/upload_image', methods=['POST'])
def upload_image_api():
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'Không tìm thấy file ảnh'}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Chưa chọn file'}), 400
            
        uploads_dir = os.path.join(os.getcwd(), 'uploads', 'logos')
        os.makedirs(uploads_dir, exist_ok=True)
        
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
        filename = f"logo_{int(time.time())}_{safe_name}"
        save_path = os.path.normpath(os.path.join(uploads_dir, filename))
        file.save(save_path)
        
        return jsonify({
            'success': True,
            'file_path': save_path,
            'url': f"/api/image?path={save_path}"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/select_folder', methods=['POST'])
def select_folder_api():
    try:
        data = request.json or {}
        title = data.get('title', 'Chọn thư mục')
        
        folder_path = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder_path = filedialog.askdirectory(title=title)
            root.destroy()
        except Exception:
            folder_path = ""
            
        if not folder_path and sys.platform.startswith('win'):
            try:
                ps_cmd = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.FolderBrowserDialog
                $f.Description = "{title}"
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.SelectedPath
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, text=True, timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                folder_path = proc.stdout.strip()
            except Exception:
                pass
                
        if folder_path and os.path.exists(folder_path):
            folder_path = os.path.normpath(folder_path)
            return jsonify({'success': True, 'folder_path': folder_path, 'path': folder_path, 'folder': folder_path})
        elif folder_path == "":
            return jsonify({'success': False, 'cancelled': True, 'message': 'Đã hủy chọn thư mục'})
        else:
            return jsonify({'success': False, 'error': 'Thư mục không tồn tại'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/select_file', methods=['POST'])
def select_file_api():
    try:
        data = request.json or {}
        title = data.get('title', 'Chọn file')
        filetypes = data.get('filetypes', [('All Files', '*.*')])
        
        file_path = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
            root.destroy()
        except Exception:
            file_path = ""
            
        if not file_path and sys.platform.startswith('win'):
            try:
                ps_cmd = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.OpenFileDialog
                $f.Title = "{title}"
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.FileName
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, text=True, timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                file_path = proc.stdout.strip()
            except Exception:
                pass
                
        if file_path and os.path.exists(file_path):
            file_path = os.path.normpath(file_path)
            return jsonify({'success': True, 'file_path': file_path, 'path': file_path, 'file': file_path})
        elif file_path == "":
            return jsonify({'success': False, 'cancelled': True, 'message': 'Đã hủy chọn file'})
        else:
            return jsonify({'success': False, 'error': 'File không tồn tại'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/save_file_dialog', methods=['POST'])
def save_file_dialog_api():
    try:
        data = request.json or {}
        title = data.get('title', 'Lưu file')
        default_name = data.get('default_name', 'subtitles_translated.srt')
        content = data.get('content', '')
        defaultextension = data.get('defaultextension', os.path.splitext(default_name)[1] or '.srt')
        filetypes = data.get('filetypes')
        filter_str = data.get('filter')

        if not filetypes:
            if defaultextension.lower() == '.amsproj':
                filetypes = [("AI Movie Shorts Project", "*.amsproj"), ("JSON Project", "*.json"), ("All Files", "*.*")]
                if not filter_str:
                    filter_str = "AI Movie Shorts Project (*.amsproj)|*.amsproj|JSON Project (*.json)|*.json|All Files (*.*)|*.*"
            elif defaultextension.lower() == '.srt':
                filetypes = [("SubRip Subtitles", "*.srt"), ("All Files", "*.*")]
                if not filter_str:
                    filter_str = "SubRip Subtitles (*.srt)|*.srt|All Files (*.*)|*.*"
            else:
                filetypes = [("All Files", "*.*")]
                if not filter_str:
                    filter_str = "All Files (*.*)|*.*"
        
        if not filter_str:
            filter_str = "All Files (*.*)|*.*"
        
        file_path = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.asksaveasfilename(
                title=title,
                initialfile=default_name,
                defaultextension=defaultextension,
                filetypes=filetypes
            )
            root.destroy()
        except Exception:
            file_path = ""
            
        if not file_path and sys.platform.startswith('win'):
            try:
                ps_cmd = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.SaveFileDialog
                $f.Title = "{title}"
                $f.FileName = "{default_name}"
                $f.Filter = "{filter_str}"
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.FileName
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, text=True, timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                file_path = proc.stdout.strip()
            except Exception:
                pass
                
        if file_path:
            file_path = os.path.normpath(file_path)
            if content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return jsonify({'success': True, 'file_path': file_path})
        else:
            return jsonify({'success': False, 'cancelled': True, 'message': 'Đã hủy lưu file'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/open_folder', methods=['POST'])
def api_general_open_folder():
    import subprocess
    data = request.json or {}
    target_path = data.get('path') or data.get('file_path') or ''
    if not target_path or not os.path.exists(target_path):
        folder = os.path.join(ROOT_DIR, 'output')
        os.makedirs(folder, exist_ok=True)
        subprocess.Popen(f'explorer "{folder}"')
        return jsonify({'success': True})
    
    if os.path.isdir(target_path):
        subprocess.Popen(f'explorer "{target_path}"')
    else:
        subprocess.Popen(f'explorer /select,"{target_path}"')
    return jsonify({'success': True})

@core_bp.route('/api/test-openai', methods=['POST'])
def test_openai():
    data = request.json
    openai_key = data.get('openai_key')
    openai_base_url = data.get('openai_base_url', 'https://api.openai.com/v1')
    if not openai_key:
        return jsonify({'success': False, 'message': 'Thiếu API Key'})
        
    url = openai_base_url
    if not url.endswith('/models'):
        url = f"{url.rstrip('/')}/models"
        
    headers = {
        "Authorization": f"Bearer {openai_key}"
    }
    try:
        import requests
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code == 200:
            return jsonify({'success': True, 'message': 'Kết nối thành công!'})
        else:
            return jsonify({'success': False, 'message': f'Lỗi API: {res.text}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'})

def format_api_error_to_vietnamese(status_code, raw_err_msg):
    """
    Chuyển đổi các mã lỗi kỹ thuật tiếng Anh (OpenAI / HTTP) thành thông báo tiếng Việt dễ hiểu cho người dùng cuối.
    """
    raw_lower = str(raw_err_msg).lower()
    
    if status_code == 401 or 'incorrect api key' in raw_lower or 'invalid api key' in raw_lower or 'unauthorized' in raw_lower:
        return "Mã API Key OpenAI không chính xác hoặc đã bị vô hiệu hóa. Vui lòng kiểm tra lại Key trên trang OpenAI."
    elif status_code == 429 or 'insufficient_quota' in raw_lower or 'quota' in raw_lower or 'rate_limit' in raw_lower:
        return "Tài khoản OpenAI đã hết hạn mức sử dụng (hết tiền/hết quota) hoặc gửi yêu cầu quá nhanh. Vui lòng kiểm tra số dư tại platform.openai.com."
    elif status_code == 404 or 'model_not_found' in raw_lower or 'does not exist' in raw_lower:
        return "Model AI này không tồn tại hoặc tài khoản của bạn chưa được cấp quyền sử dụng model này."
    elif 'max_tokens' in raw_lower or 'max_completion_tokens' in raw_lower or 'unsupported parameter' in raw_lower:
        return "Tham số cấu hình của Model AI đã được hệ thống tự động tối ưu."
    elif status_code == 500 or status_code == 502 or status_code == 503:
        return "Máy chủ OpenAI hiện đang bị quá tải hoặc gặp sự cố tạm thời. Vui lòng thử lại sau vài giây."
    elif 'timeout' in raw_lower or 'timed out' in raw_lower:
        return "Quá thời gian kết nối (Timeout). Vui lòng kiểm tra lại đường truyền mạng Internet hoặc Base URL."
    elif 'connection' in raw_lower or 'failed to establish' in raw_lower:
        return "Không thể kết nối đến máy chủ OpenAI. Vui lòng kiểm tra lại kết nối mạng."
    else:
        return f"Lỗi từ dịch vụ OpenAI: {raw_err_msg}"

@core_bp.route('/api/test_openai_key', methods=['POST'])
def test_openai_key():
    data = request.json or {}
    api_key = data.get('openai_key') or data.get('openaiKey')
    base_url = data.get('openai_base_url') or data.get('openaiBaseUrl') or 'https://api.openai.com/v1'
    model = data.get('openai_model') or data.get('openaiModel') or 'gpt-5.6-luna'

    if not api_key or str(api_key).startswith('•') or data.get('test_vip'):
        # Tự động đọc Key thật từ file cấu hình / bản quyền VIP
        if os.path.exists(API_KEYS_FILE):
            with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('openaiKey='):
                        api_key = line.strip().split('=', 1)[1]
                        break
        if not api_key or str(api_key).startswith('•'):
            try:
                from routes.subtitles import _resolve_openai_credentials
                rk, ru, rm = _resolve_openai_credentials()
                if rk and not rk.startswith('•'):
                    api_key = rk
                    if ru: base_url = ru
                    if rm: model = rm
            except Exception:
                pass

    if not api_key or not str(api_key).strip():
        return jsonify({'success': False, 'error': 'Vui lòng nhập OpenAI API Key trước khi kiểm tra!'}), 400

    api_key = str(api_key).strip()
    base_url = str(base_url).strip().rstrip('/')

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        test_url = f"{base_url}/chat/completions"
        
        # Nhận diện reasoning/luna models để truyền max_completion_tokens thay vì max_tokens
        is_reasoning_model = any(m in model.lower() for m in ['o1', 'o3', 'o4', 'luna', 'reasoning', 'gpt-5'])
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}]
        }
        if is_reasoning_model:
            payload["max_completion_tokens"] = 15
        else:
            payload["max_tokens"] = 15

        res = requests.post(test_url, headers=headers, json=payload, timeout=15)
        
        # Nếu model từ chối do max_tokens/max_completion_tokens, thử lại với /models endpoint nhẹ nhàng
        if res.status_code == 400 and ('max_tokens' in res.text.lower() or 'max_completion_tokens' in res.text.lower()):
            models_url = f"{base_url}/models"
            res_models = requests.get(models_url, headers=headers, timeout=10)
            if res_models.status_code == 200:
                return jsonify({'success': True, 'message': f'🎉 Kết nối thành công! API Key hợp lệ (Model: {model})'})

        if res.status_code == 200:
            return jsonify({'success': True, 'message': f'🎉 Kết nối thành công! API Key hợp lệ (Model: {model})'})
        else:
            try:
                err_data = res.json()
                err_msg = err_data.get('error', {}).get('message', res.text)
            except Exception:
                err_msg = res.text[:250]
            vi_msg = format_api_error_to_vietnamese(res.status_code, err_msg)
            return jsonify({'success': False, 'error': vi_msg}), 400
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Quá thời gian chờ kết nối. Vui lòng kiểm tra lại đường truyền mạng hoặc Base URL!'}), 400
    except Exception as e:
        vi_msg = format_api_error_to_vietnamese(500, str(e))
        return jsonify({'success': False, 'error': vi_msg}), 400

@core_bp.route('/api/keys', methods=['GET'])
@core_bp.route('/api/get_api_keys', methods=['GET'])
def get_api_keys():
    keys = {}
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    keys[k] = v
    return jsonify(keys)

@core_bp.route('/api/keys', methods=['POST'])
@core_bp.route('/api/save_api_keys', methods=['POST'])
def save_api_keys():
    data = request.json or {}
    keys = {}
    if os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    keys[k] = v
                    
    for k, v in data.items():
        if isinstance(v, str) and v.startswith('•'):
            continue  # Bỏ qua không ghi đè masked asterisks vào file
        keys[k] = v
        
    with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
        for k, v in keys.items():
            f.write(f"{k}={v}\n")
            
    # Đẩy 1 chiều (Write-Only) lên Google Sheet trong background thread (không block UI)
    try:
        import license_manager
        threading.Thread(target=license_manager.sync_user_keys_to_cloud, args=(keys,), daemon=True).start()
    except Exception:
        pass

    return jsonify({'success': True})

@core_bp.route('/api/system/hardware', methods=['GET'])
def get_hardware_info():
    import subprocess
    import shutil
    import ffmpeg_installer
    ffmpeg_path = ffmpeg_installer.get_ffmpeg_path()
    
    encoders = [
        {"id": "libx264", "name": "CPU x264 (Chuẩn phổ thông & ổn định nhất)", "is_gpu": False}
    ]
    
    def test_encoder_usable(encoder_name):
        if not ffmpeg_path: return False
        try:
            cmd = [
                ffmpeg_path, '-y', '-f', 'lavfi', '-i', 'nullsrc=s=64x64:d=0.1',
                '-c:v', encoder_name, '-f', 'null', '-'
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=0x08000000 if os.name == 'nt' else 0)
            return res.returncode == 0
        except Exception:
            return False

    if test_encoder_usable('h264_nvenc'):
        encoders.insert(0, {"id": "h264_nvenc", "name": "NVIDIA NVENC H.264 (GPU Siêu nhanh)", "is_gpu": True})
    elif test_encoder_usable('h264_mf'):
        encoders.insert(0, {"id": "h264_mf", "name": "GPU H.264 (Windows MediaFoundation / DirectX)", "is_gpu": True})
    elif test_encoder_usable('h264_amf'):
        encoders.insert(0, {"id": "h264_amf", "name": "AMD AMF H.264 (GPU)", "is_gpu": True})
    elif test_encoder_usable('h264_qsv'):
        encoders.insert(0, {"id": "h264_qsv", "name": "Intel QSV H.264 (GPU)", "is_gpu": True})

    # Quét thiết bị phần cứng cho AI (ASR, OCR, TTS)
    ai_devices = [
        {"id": "auto", "name": "⚡ Tự động tối ưu (Khuyên dùng)", "available": True},
        {"id": "cpu", "name": "⚪ CPU Đa luồng (Tất cả máy tính)", "available": True}
    ]
    
    has_cuda = False
    cuda_name = "🟢 GPU NVIDIA CUDA"
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=3, creationflags=0x08000000 if os.name == 'nt' else 0)
            if res.returncode == 0 and res.stdout.strip():
                gpu_model = res.stdout.strip().splitlines()[0]
                cuda_name = f"🟢 GPU NVIDIA CUDA ({gpu_model})"
                has_cuda = True
        except Exception:
            pass
    if not has_cuda:
        try:
            import torch
            if torch.cuda.is_available():
                cuda_name = f"🟢 GPU NVIDIA CUDA ({torch.cuda.get_device_name(0)})"
                has_cuda = True
        except Exception:
            pass

    if has_cuda:
        ai_devices.insert(1, {"id": "cuda", "name": cuda_name, "available": True})
    else:
        ai_devices.append({"id": "cuda", "name": "🟢 GPU NVIDIA CUDA (Không có sẵn trên máy này)", "available": False})

    if os.name == 'nt':
        ai_devices.insert(2 if has_cuda else 1, {"id": "directml", "name": "🔵 GPU DirectML (AMD / Intel / DirectX 12)", "available": True})

    return jsonify({
        "success": True,
        "encoders": encoders,
        "ai_devices": ai_devices,
        "has_cuda": has_cuda
    })

def _time_to_seconds(t_str):
    try:
        t_str = str(t_str).strip().replace(',', '.')
        parts = t_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(t_str)
    except Exception:
        return 0.0

