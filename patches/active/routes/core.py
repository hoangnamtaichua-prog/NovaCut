from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, requests, tempfile, ipaddress, socket, uuid
from routes.state import *
import asr_manager
from routes.security import is_path_allowed, register_user_path, safe_join
from urllib.parse import urlparse
from werkzeug.utils import secure_filename

core_bp = Blueprint('core', __name__)

_MEDIA_EXTENSIONS = {
    '.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.mp4', '.mkv', '.avi',
    '.mov', '.webm', '.srt', '.vtt', '.ass', '.png', '.jpg', '.jpeg', '.webp', '.gif'
}
MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024
_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def _validate_external_api_url(value):
    parsed = urlparse(str(value or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Base URL phải là địa chỉ HTTPS hợp lệ.')
    allowed_hosts = {'api.openai.com', 'api.ai33.pro', 'openrouter.ai'}
    allowed_hosts.update(
        item.strip().lower()
        for item in os.environ.get('NOVACUT_ALLOWED_AI_HOSTS', '').split(',')
        if item.strip()
    )
    if parsed.hostname.lower() not in allowed_hosts:
        raise ValueError('Tên miền Base URL chưa có trong NOVACUT_ALLOWED_AI_HOSTS.')
    return str(value).rstrip('/')


def _require_any_media_permission():
    import license_manager
    status = license_manager.get_current_license_status()
    features = status.get('features', {})
    if not status.get('is_valid') or not (features.get('can_access_editor') or features.get('can_access_review')):
        return jsonify({'success': False, 'error': 'Gói bản quyền hiện tại không cho phép thao tác media.'}), 403
    return None

def _validated_media_path(raw_path):
    path = os.path.realpath(str(raw_path or '').strip('\'"'))
    if not is_path_allowed(path, must_exist=True, extensions=_MEDIA_EXTENSIONS):
        return None
    return path

def find_media_on_system(raw_path):
    if not raw_path:
        return None
    raw_clean = str(raw_path or '').strip('\'"')
    target_name = os.path.basename(raw_clean)
    if not target_name:
        return None

    from routes.security import _selected_roots, register_user_path, _selection_lock

    search_dirs = []
    with _selection_lock:
        search_dirs.extend(list(_selected_roots))

    common_locations = [
        os.path.join(ROOT_DIR, 'movies'),
        os.path.join(ROOT_DIR, 'downloads'),
        os.path.join(USER_DATA_DIR, 'downloads'),
        os.path.expanduser(r'~\Downloads'),
        os.path.expanduser(r'~\Videos'),
        os.path.expanduser(r'~\Desktop')
    ]
    for loc in common_locations:
        if loc and os.path.exists(loc) and loc not in search_dirs:
            search_dirs.append(loc)

    for d in search_dirs:
        try:
            cand = os.path.join(d, target_name)
            if os.path.isfile(cand):
                norm_c = os.path.normpath(cand)
                register_user_path(norm_c)
                return norm_c
            if os.path.isdir(d):
                for sub in os.listdir(d):
                    sub_p = os.path.join(d, sub)
                    if os.path.isdir(sub_p):
                        cand = os.path.join(sub_p, target_name)
                        if os.path.isfile(cand):
                            norm_c = os.path.normpath(cand)
                            register_user_path(norm_c)
                            return norm_c
        except Exception:
            continue

    return None

def _ps_literal(value):
    return "'" + str(value or '').replace("'", "''") + "'"

@core_bp.after_request
def add_no_cache_headers(response):
    if response.mimetype in ['text/html', 'text/javascript', 'application/javascript', 'text/css']:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

@core_bp.route('/')
def index():
    web_dir = os.path.join(ROOT_DIR, 'web')
    return send_from_directory(web_dir, 'index.html')

@core_bp.route('/<path:path>')
def static_files(path):
    web_dir = os.path.join(ROOT_DIR, 'web')
    target_file = os.path.join(web_dir, path)
    if os.path.exists(target_file) and not os.path.isdir(target_file):
        return send_from_directory(web_dir, path)
    if '.' not in os.path.basename(path):
        return send_from_directory(web_dir, 'index.html')
    return send_from_directory(web_dir, path)

@core_bp.route('/api/file')
def serve_file():
    path = _validated_media_path(request.args.get('path'))
    if not path:
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
    # 1. Ưu tiên tìm trong web/samples tĩnh
    web_samples_dir = os.path.join(ROOT_DIR, 'web', 'samples')
    target = os.path.join(web_samples_dir, filename)
    if os.path.exists(target):
        return send_from_directory(web_samples_dir, filename)

    # 2. Tìm trong USER_DATA_DIR/samples (nơi lưu các voice đã cache hoặc clone)
    user_samples_dir = os.path.join(USER_DATA_DIR, 'samples')
    user_target = os.path.join(user_samples_dir, filename)
    if os.path.exists(user_target) and os.path.getsize(user_target) > 500:
        return send_from_directory(user_samples_dir, filename)

    # 3. Nếu là file mẫu giọng .wav chưa có sẵn, tự động sinh tức thì và lưu cache
    if filename.endswith('.wav'):
        voice_id = filename[:-4]
        try:
            import ai_dubbing
            os.makedirs(user_samples_dir, exist_ok=True)
            text = "Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu."
            ai_dubbing.synthesize_sentence(text, voice_id, 1.0, user_target)
            if os.path.exists(user_target) and os.path.getsize(user_target) > 500:
                return send_from_directory(user_samples_dir, filename)
        except Exception as e:
            print(f"[serve_samples] Lỗi sinh mẫu giọng trực tiếp cho {voice_id}: {e}")

    return send_from_directory(web_samples_dir, filename)

@core_bp.route('/api/video')
def stream_video():
    raw = request.args.get('path')
    path = _validated_media_path(raw)
    if not path:
        clean_p = os.path.realpath(str(raw or '').strip('\'"'))
        if os.path.exists(clean_p) and os.path.isfile(clean_p) and os.path.splitext(clean_p)[1].lower() in _MEDIA_EXTENSIONS:
            register_user_path(clean_p)
            path = clean_p
        else:
            resolved = find_media_on_system(raw)
            if resolved and os.path.exists(resolved) and os.path.isfile(resolved):
                register_user_path(resolved)
                path = resolved
            else:
                return "Video not found", 404
        
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = 'video/mp4'
        
    return send_file(path, mimetype=mime_type, conditional=True)

@core_bp.route('/api/resolve_media_path', methods=['GET', 'POST'])
def resolve_media_path_api():
    data = request.json if request.is_json else request.args
    raw_path = data.get('path') or data.get('name') or data.get('filename', '')
    if not raw_path:
        return jsonify({'success': False, 'error': 'Chưa cung cấp đường dẫn'}), 400

    clean_p = os.path.realpath(str(raw_path).strip('\'"'))
    if os.path.exists(clean_p) and os.path.isfile(clean_p):
        norm_p = os.path.normpath(clean_p)
        register_user_path(norm_p)
        return jsonify({'success': True, 'resolved_path': norm_p, 'exists': True})

    resolved = find_media_on_system(raw_path)
    if resolved and os.path.exists(resolved):
        norm_p = os.path.normpath(resolved)
        register_user_path(norm_p)
        return jsonify({'success': True, 'resolved_path': norm_p, 'exists': True})

    return jsonify({'success': False, 'error': 'Không tìm thấy file trên hệ thống'}), 404

@core_bp.route('/api/register_paths', methods=['POST'])
def register_paths_api():
    data = request.json or {}
    paths = data.get('paths') or []
    if isinstance(paths, str):
        paths = [paths]
    registered = []
    for p in paths:
        if not p:
            continue
        clean_p = str(p).strip('\'"')
        if os.path.exists(clean_p):
            norm_p = os.path.normpath(clean_p)
            register_user_path(norm_p)
            registered.append(norm_p)
    return jsonify({'success': True, 'registered_count': len(registered)})

@core_bp.route('/api/image')
def stream_image():
    raw_path = request.args.get('path', '')
    if not raw_path:
        return "Image not found", 404
        
    path = _validated_media_path(raw_path)
    if not path or os.path.splitext(path)[1].lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
        clean_p = os.path.realpath(str(raw_path or '').strip('\'"'))
        if os.path.exists(clean_p) and os.path.isfile(clean_p) and os.path.splitext(clean_p)[1].lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
            register_user_path(clean_p)
            path = clean_p
        else:
            return "Image not found", 404
        
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = 'image/png'
        
    return send_file(path, mimetype=mime_type, conditional=True)

@core_bp.route('/api/upload_image', methods=['POST'])
def upload_image_api():
    try:
        permission_error = _require_any_media_permission()
        if permission_error:
            return permission_error
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'Không tìm thấy file ảnh'}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Chưa chọn file'}), 400
        if request.content_length and request.content_length > MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024:
            return jsonify({'success': False, 'error': 'File ảnh vượt quá 20 MB'}), 413
            
        uploads_dir = os.path.join(USER_DATA_DIR, 'uploads', 'logos')
        os.makedirs(uploads_dir, exist_ok=True)
        
        safe_name = secure_filename(file.filename)
        extension = os.path.splitext(safe_name)[1].lower()
        if extension not in _IMAGE_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Định dạng ảnh không được hỗ trợ'}), 415
        filename = f"logo_{uuid.uuid4().hex}{extension}"
        save_path = safe_join(uploads_dir, filename, extensions=_IMAGE_EXTENSIONS)
        total = 0
        with open(save_path, 'xb') as handle:
            while True:
                chunk = file.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_IMAGE_UPLOAD_BYTES:
                    raise ValueError('File ảnh vượt quá 20 MB')
                handle.write(chunk)
        try:
            from PIL import Image
            with Image.open(save_path) as image:
                image.verify()
        except Exception:
            try:
                os.remove(save_path)
            except OSError:
                pass
            return jsonify({'success': False, 'error': 'Nội dung file không phải ảnh hợp lệ'}), 415
        
        return jsonify({
            'success': True,
            'file_path': save_path,
            'url': f"/api/image?path={save_path}"
        })
    except ValueError as e:
        if 'save_path' in locals() and os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        return jsonify({'success': False, 'error': str(e)}), 413
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
                $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                [Console]::InputEncoding = [System.Text.Encoding]::UTF8
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.FolderBrowserDialog
                $f.Description = {_ps_literal(title)}
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.SelectedPath
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, encoding='utf-8', errors='replace', timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                folder_path = proc.stdout.strip()
            except Exception:
                pass
                
        if folder_path and os.path.exists(folder_path):
            folder_path = os.path.normpath(folder_path)
            register_user_path(folder_path)
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
                $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                [Console]::InputEncoding = [System.Text.Encoding]::UTF8
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.OpenFileDialog
                $f.Title = {_ps_literal(title)}
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.FileName
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, encoding='utf-8', errors='replace', timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                file_path = proc.stdout.strip()
            except Exception:
                pass
                
        if file_path and os.path.exists(file_path):
            file_path = os.path.normpath(file_path)
            register_user_path(file_path)
            return jsonify({'success': True, 'file_path': file_path, 'path': file_path, 'file': file_path})
        elif file_path == "":
            return jsonify({'success': False, 'cancelled': True, 'message': 'Đã hủy chọn file'})
        else:
            return jsonify({'success': False, 'error': 'File không tồn tại'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/select_files', methods=['POST'])
def select_files_api():
    try:
        data = request.json or {}
        title = data.get('title', 'Chọn các file')
        file_type = data.get('type', 'video')
        filetypes = data.get('filetypes')

        if not filetypes:
            if file_type == 'video':
                filetypes = [('Video Files', '*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v'), ('All Files', '*.*')]
            elif file_type == 'srt':
                filetypes = [('Subtitle Files', '*.srt;*.vtt;*.ass'), ('All Files', '*.*')]
            elif file_type == 'audio':
                filetypes = [('Audio Files', '*.mp3;*.wav;*.m4a;*.aac;*.flac'), ('All Files', '*.*')]
            else:
                filetypes = [('All Files', '*.*')]

        file_paths = []
        if sys.platform.startswith('win'):
            try:
                ps_filter = 'All Files (*.*)|*.*'
                if file_type == 'video':
                    ps_filter = 'Video Files (*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v)|*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v|All Files (*.*)|*.*'
                elif file_type == 'srt':
                    ps_filter = 'Subtitle Files (*.srt;*.vtt;*.ass)|*.srt;*.vtt;*.ass|All Files (*.*)|*.*'
                elif file_type == 'audio':
                    ps_filter = 'Audio Files (*.mp3;*.wav;*.m4a;*.aac;*.flac)|*.mp3;*.wav;*.m4a;*.aac;*.flac|All Files (*.*)|*.*'

                ps_cmd = f"""
                $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                [Console]::InputEncoding = [System.Text.Encoding]::UTF8
                [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
                $form = New-Object System.Windows.Forms.Form
                $form.TopMost = $true
                $form.Width = 0
                $form.Height = 0
                $form.StartPosition = "CenterScreen"
                $f = New-Object System.Windows.Forms.OpenFileDialog
                $f.Title = {_ps_literal(title)}
                $f.Filter = '{ps_filter}'
                $f.Multiselect = $true
                if ($f.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.FileNames | ForEach-Object {{ Write-Output $_ }}
                }}
                $form.Dispose()
                """
                proc = subprocess.run(
                    ['powershell', '-STA', '-NoProfile', '-Command', ps_cmd],
                    capture_output=True, encoding='utf-8', errors='replace', timeout=60,
                    creationflags=0x08000000 if os.name == 'nt' else 0
                )
                lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
                if lines:
                    file_paths = lines
            except Exception:
                pass

        if not file_paths:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                res = filedialog.askopenfilenames(title=title, filetypes=filetypes)
                if res:
                    if isinstance(res, (list, tuple)):
                        file_paths = [str(x) for x in res if str(x).strip()]
                    elif isinstance(res, str):
                        try:
                            file_paths = [str(x) for x in root.tk.splitlist(res) if str(x).strip()]
                        except Exception:
                            file_paths = [res.strip()] if res.strip() else []
                root.destroy()
            except Exception:
                file_paths = []

        valid_paths = []
        for p in file_paths:
            if p:
                clean_p = str(p).strip().strip('"').strip("'")
                if os.path.exists(clean_p):
                    norm_p = os.path.normpath(clean_p)
                    register_user_path(norm_p)
                    valid_paths.append(norm_p)

        if valid_paths:
            return jsonify({'success': True, 'file_paths': valid_paths, 'files': valid_paths, 'paths': valid_paths, 'count': len(valid_paths)})
        else:
            return jsonify({'success': False, 'cancelled': True, 'message': 'Không có file nào được chọn'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@core_bp.route('/api/save_file_dialog', methods=['POST'])
def save_file_dialog_api():
    try:
        data = request.json or {}
        title = data.get('title', 'Lưu file')
        default_name = data.get('default_name', 'subtitles_translated.srt')
        content = data.get('content', '')
        filetypes = data.get('filetypes')
        defaultextension = data.get('defaultextension', '.srt')
        filter_str = data.get('filter_str', 'Subtitle Files (*.srt)|*.srt|All Files (*.*)|*.*')

        if not filetypes:
            filetypes = [('Subtitle Files', '*.srt'), ('All Files', '*.*')]

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
                $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                [Console]::InputEncoding = [System.Text.Encoding]::UTF8
                Add-Type -AssemblyName System.Windows.Forms
                $f = New-Object System.Windows.Forms.SaveFileDialog
                $f.Title = {_ps_literal(title)}
                $f.FileName = {_ps_literal(default_name)}
                $f.Filter = {_ps_literal(filter_str)}
                if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    $f.FileName
                }}
                """
                proc = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], capture_output=True, encoding='utf-8', errors='replace', timeout=30, creationflags=0x08000000 if os.name == 'nt' else 0)
                file_path = proc.stdout.strip()
            except Exception:
                pass
                
        if file_path:
            file_path = os.path.normpath(file_path)
            register_user_path(file_path)
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
    data = request.get_json(silent=True) or {}
    target_path = str(data.get('path') or data.get('file_path') or '').strip(' "\'')
    video_path = str(data.get('video_path') or '').strip(' "\'')

    if not target_path and video_path:
        target_path = video_path

    if not target_path:
        target_path = os.path.join(ROOT_DIR, 'output')

    if not os.path.isabs(target_path):
        target_path = os.path.abspath(os.path.join(ROOT_DIR, target_path))

    # Nếu file mục tiêu chưa tồn tại hoặc bị xóa/chuyển, tìm đường dẫn dự phòng
    if not os.path.exists(target_path):
        parent_dir = os.path.dirname(target_path)
        if os.path.isdir(parent_dir):
            target_path = parent_dir
        elif video_path and os.path.exists(video_path):
            target_path = os.path.abspath(video_path)
        elif video_path and os.path.isdir(os.path.dirname(video_path)):
            target_path = os.path.abspath(os.path.dirname(video_path))
        else:
            target_path = os.path.join(ROOT_DIR, 'output')
            os.makedirs(target_path, exist_ok=True)

    # Đăng ký quyền truy cập cho đường dẫn này
    register_user_path(target_path)

    norm_path = os.path.normpath(target_path)
    try:
        if os.name == 'nt':
            if os.path.isdir(norm_path):
                try:
                    os.startfile(norm_path)
                except Exception:
                    subprocess.Popen(f'explorer "{norm_path}"', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    subprocess.Popen(f'explorer /select,"{norm_path}"', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    os.startfile(os.path.dirname(norm_path))
        elif sys.platform == 'darwin':
            args = ['open', '-R', norm_path] if not os.path.isdir(norm_path) else ['open', norm_path]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            args = ['xdg-open', norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'success': True, 'opened_path': norm_path})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Không thể mở File Explorer: {str(e)}'}), 500

@core_bp.route('/api/test-openai', methods=['POST'])
def test_openai():
    data = request.get_json(silent=True) or {}
    openai_key = data.get('openai_key')
    openai_base_url = data.get('openai_base_url', 'https://api.openai.com/v1')
    if not openai_key:
        return jsonify({'success': False, 'message': 'Thiếu API Key'})
        
    try:
        url = _validate_external_api_url(openai_base_url)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
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
            return jsonify({'success': False, 'message': format_api_error_to_vietnamese(res.status_code, res.text[:500])}), 400
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
    elif 'guardrail' in raw_lower or 'data policy' in raw_lower:
        return "Tài khoản OpenRouter của bạn đang bật Guardrail chặn nhà cung cấp này (https://openrouter.ai/workspaces/default/guardrails). Hãy tắt bộ lọc hoặc chọn model Qwen3.7 Flash / Deepseek V3.2."
    elif 'batch api' in raw_lower or 'api/beta/batches' in raw_lower:
        return "Mô hình này có đuôi :batch chỉ dành cho Batch API xử lý ngầm trên OpenRouter, không hỗ trợ dịch trực tiếp. Vui lòng chọn Qwen3.7 Flash hoặc Deepseek V3.2."
    elif status_code == 404 or 'model_not_found' in raw_lower or 'does not exist' in raw_lower:
        return "Model AI này không tồn tại hoặc tài khoản của bạn chưa được cấp quyền sử dụng model này."
    elif 'max_tokens' in raw_lower or 'max_completion_tokens' in raw_lower or 'unsupported parameter' in raw_lower:
        return "Tham số cấu hình của Model AI đã được hệ thống tự động tối ưu."
    elif (status_code == 500 or status_code == 502 or status_code == 503) and not any(k in raw_lower for k in ['nameerror', 'typeerror', 'keyerror', 'attributeerror', 'syntaxerror', 'valueerror']):
        return "Máy chủ AI / OpenRouter hiện đang bị quá tải hoặc gặp sự cố tạm thời. Vui lòng thử lại sau vài giây."
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
    model = data.get('openai_model') or data.get('openaiModel') or 'gpt-6-luna'
    if model in ['gpt-5.6-luna', 'gpt-5.6-luna-pro', 'gpt-6-luna-pro']:
        model = 'gpt-6-luna'

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
    if api_key.startswith('sk-or-') and (not base_url or base_url == 'https://api.openai.com/v1'):
        base_url = 'https://openrouter.ai/api/v1'
    try:
        base_url = _validate_external_api_url(base_url)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    model = re.sub(r'[^a-zA-Z0-9_.:/\-\s]', '', str(model))[:200].strip()
    if not model or model == 'gpt-5.6-luna':
        model = 'gpt-5.6-luna-pro-batch'

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        is_openrouter = 'openrouter.ai' in base_url or api_key.startswith('sk-or-')
        if is_openrouter:
            headers['HTTP-Referer'] = 'https://novacut.app'
            headers['X-Title'] = 'NovaCut AI'

            # 1. Xác thực siêu tốc qua OpenRouter Auth API (phản hồi < 0.5s, không bị nghẽn queue Free)
            try:
                auth_res = requests.get('https://openrouter.ai/api/v1/auth/key', headers=headers, timeout=8)
                if auth_res.status_code == 200:
                    auth_data = auth_res.json().get('data', {})
                    is_free = auth_data.get('is_free_tier', False)
                    tier_label = "Gói Miễn Phí (Free Tier)" if is_free else "Gói Trả Phí"
                    return jsonify({
                        'success': True,
                        'message': f'🎉 Kết nối thành công! API Key OpenRouter hợp lệ ({tier_label}, Model: {model})'
                    })
                elif auth_res.status_code in [401, 403]:
                    return jsonify({'success': False, 'error': '❌ OpenRouter API Key không hợp lệ hoặc đã hết hạn!'}), 400
            except Exception:
                pass  # Fallback tiếp xuống chat/completions bên dưới

        test_url = f"{base_url}/chat/completions"
        
        # Nhận diện reasoning/luna models để truyền max_completion_tokens thay vì max_tokens
        is_reasoning_model = any(m in model.lower() for m in ['o1', 'o3', 'o4', 'luna', 'reasoning', 'gpt-5'])
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}]
        }
        if is_reasoning_model:
            payload["max_completion_tokens"] = 30
        else:
            payload["max_tokens"] = 30

        # Timeout 45s cho chat completions (đủ thời gian cho Nemotron 3 Ultra 550B queue)
        res = requests.post(test_url, headers=headers, json=payload, timeout=45)
        
        # Nếu model từ chối do max_tokens/max_completion_tokens, thử lại với /models endpoint nhẹ nhàng
        if res.status_code == 400 and ('max_tokens' in res.text.lower() or 'max_completion_tokens' in res.text.lower()):
            models_url = f"{base_url}/models"
            res_models = requests.get(models_url, headers=headers, timeout=10)
            if res_models.status_code == 200:
                return jsonify({'success': True, 'message': f'🎉 Kết nối thành công! API Key hợp lệ (Model: {model})'})

        if res.status_code == 200:
            res_data = res.json()
            if 'error' in res_data:
                err_msg = res_data['error'].get('message', str(res_data['error']))
                return jsonify({'success': False, 'error': f'⚠️ Máy chủ AI thông báo: {err_msg}'}), 400
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
        return jsonify({'success': False, 'error': 'Quá thời gian chờ kết nối (Timeout). Hãy thử lại hoặc chuyển tạm sang mô hình Free khác!'}), 400
    except Exception as e:
        vi_msg = format_api_error_to_vietnamese(500, str(e))
        return jsonify({'success': False, 'error': vi_msg}), 400

@core_bp.route('/api/keys', methods=['GET'])
@core_bp.route('/api/get_api_keys', methods=['GET'])
def get_api_keys():
    keys = {}
    legacy_file = os.path.join(ROOT_DIR, 'api_keys.txt')
    candidate_files = [API_KEYS_FILE]
    if os.path.abspath(legacy_file) != os.path.abspath(API_KEYS_FILE):
        candidate_files.append(legacy_file)

    for p in candidate_files:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            k, v = line.strip().split('=', 1)
                            if k not in keys or not keys[k]:
                                keys[k] = v
            except Exception:
                pass
    return jsonify(keys)

@core_bp.route('/api/keys', methods=['POST'])
@core_bp.route('/api/save_api_keys', methods=['POST'])
def save_api_keys():
    data = request.json or {}
    allowed_keys = {'openaiKey', 'openaiBaseUrl', 'openaiModel', 'openSpeakerApiKey'}
    if not isinstance(data, dict) or any(k not in allowed_keys for k in data):
        return jsonify({'success': False, 'error': 'Trường cấu hình API không hợp lệ'}), 400
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
        if not isinstance(v, str) or len(v) > 4096 or '\r' in v or '\n' in v:
            return jsonify({'success': False, 'error': f'Giá trị {k} không hợp lệ'}), 400
        value = v.strip()
        if not value and k in ['openaiKey', 'openSpeakerApiKey'] and keys.get(k):
            continue  # Giữ nguyên key cũ nếu người dùng không nhập key mới
        if k == 'openaiBaseUrl' and value:
            try:
                value = _validate_external_api_url(value)
            except ValueError as exc:
                return jsonify({'success': False, 'error': str(exc)}), 400
        if k == 'openaiModel':
            value = re.sub(r'[^a-zA-Z0-9_.:/-]', '', value)[:200]
            if not value:
                return jsonify({'success': False, 'error': 'Tên model không hợp lệ'}), 400
        keys[k] = value
        
    os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.novacut_keys_', suffix='.tmp', dir=os.path.dirname(API_KEYS_FILE))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for k, v in keys.items():
                f.write(f"{k}={v}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, API_KEYS_FILE)
        if os.name != 'nt':
            os.chmod(API_KEYS_FILE, 0o600)

        # Đồng bộ sang legacy keys trong thư mục ứng dụng để các module phụ trợ đọc được
        legacy_file = os.path.join(ROOT_DIR, 'api_keys.txt')
        if os.path.abspath(legacy_file) != os.path.abspath(API_KEYS_FILE):
            try:
                import shutil
                shutil.copy2(API_KEYS_FILE, legacy_file)
            except Exception:
                pass
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

    return jsonify({'success': True})

@core_bp.route('/api/system/hardware', methods=['GET'])
def get_hardware_info():
    import subprocess
    import shutil
    import ffmpeg_installer
    ffmpeg_path = ffmpeg_installer.get_ffmpeg_path()
    
    caps = ffmpeg_installer.get_hardware_capabilities(ffmpeg_path)

    encoders = [
        {"id": "libx264", "name": "CPU x264 (Chuẩn tương thích cao nhất)", "is_gpu": False}
    ]

    gpu_label = f" ({caps.get('gpu_name')})" if caps.get('gpu_name') else ""
    if caps.get('nvenc_supported'):
        encoders.insert(0, {"id": "h264_nvenc", "name": f"NVIDIA NVENC H.264 (GPU Siêu nhanh{gpu_label})", "is_gpu": True})
    elif caps.get('mf_supported'):
        encoders.insert(0, {"id": "h264_mf", "name": "GPU H.264 (Windows MediaFoundation / DirectX)", "is_gpu": True})
    elif caps.get('amf_supported'):
        encoders.insert(0, {"id": "h264_amf", "name": "AMD AMF H.264 (GPU)", "is_gpu": True})
    elif caps.get('qsv_supported'):
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
        "has_cuda": has_cuda,
        "gpu_capabilities": caps
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

