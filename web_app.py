import os
import subprocess
import sys
import io
import mimetypes
import json
import logging
import traceback
import re
import time
import threading

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    candidates = [
        __file__ if '__file__' in globals() else None,
        sys.argv[0] if sys.argv and sys.argv[0] else None,
        os.getcwd()
    ]
    for c in candidates:
        if not c:
            continue
        p = os.path.abspath(c) if os.path.isdir(c) else os.path.dirname(os.path.abspath(c))
        while p and os.path.dirname(p) != p:
            if os.path.exists(os.path.join(p, 'web', 'index.html')):
                norm_p = os.path.normpath(p).lower()
                if not norm_p.endswith(os.path.normpath('patches/active').lower()) and not norm_p.endswith(os.path.normpath('release/novacut').lower()):
                    return os.path.abspath(p)
            p = os.path.dirname(p)
    return os.path.abspath(os.getcwd())

ROOT_DIR = get_app_root_dir()
os.chdir(ROOT_DIR)

PATCH_DIR = os.path.join(ROOT_DIR, 'patches', 'active')
os.makedirs(PATCH_DIR, exist_ok=True)

for p in [ROOT_DIR, PATCH_DIR]:
    if p in sys.path:
        sys.path.remove(p)

is_dev = os.path.exists(os.path.join(ROOT_DIR, '.git')) and os.environ.get("NOVACUT_USE_PATCH_OVERLAY") != "1"
if is_dev:
    # Trên môi trường Dev (Git repo): Luôn ưu tiên nạp từ ROOT_DIR
    # để tránh code mới đang phát triển bị các file cũ trong patches/active làm che khuất (shadowing)
    sys.path.insert(0, PATCH_DIR)
    sys.path.insert(0, ROOT_DIR)
else:
    # Trên môi trường Release / End-user: Bản vá OTA trong patches/active có độ ưu tiên cao nhất
    sys.path.insert(0, ROOT_DIR)
    sys.path.insert(0, PATCH_DIR)

try:
    from importlib.machinery import PathFinder
    for _idx, _finder in enumerate(sys.meta_path):
        if _finder is PathFinder or getattr(_finder, '__name__', '') == 'PathFinder':
            sys.meta_path.insert(0, sys.meta_path.pop(_idx))
            break
except Exception:
    pass

# Đăng ký tường minh MIME types để chống lỗi MIME trên Windows Sandbox
mimetypes.init()
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('application/json', '.json')

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import asr_manager
from flask import Flask, send_from_directory, Response, jsonify, request, send_file

web_static_dir = os.path.join(ROOT_DIR, 'web')
app = Flask(__name__, static_folder=web_static_dir, static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def add_no_cache_headers(response):
    # Cho phép bộ nhớ đệm cho luồng media, ảnh và Partial Content Range để WebView2 tua video mượt mà
    if response.status_code == 206 or request.path.startswith(('/api/video', '/api/image', '/samples/')):
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Tự động nạp thư mục bin/ (chứa ffmpeg.exe, ffprobe.exe) vào PATH hệ thống
bin_dir = os.path.join(ROOT_DIR, 'bin')
if os.path.exists(bin_dir) and bin_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


# Register Blueprints
from routes.core import core_bp
from routes.video_edit import video_edit_bp
from routes.tts import tts_bp
from routes.subtitles import subtitles_bp
from routes.download import download_bp
from routes.capcut import capcut_bp
from routes.asr import asr_bp
from routes.license import license_bp
from routes.project import project_bp
from routes.updater import updater_bp
from routes.audio import audio_bp
from routes.batch_queue import batch_queue_bp
from routes.comic_review import comic_review_bp
from routes.export_history import export_history_bp
from routes.telegram import telegram_bp
from routes.social_publish import social_publish_bp
from routes.hongguo import hongguo_bp

app.register_blueprint(core_bp)
app.register_blueprint(video_edit_bp)
app.register_blueprint(tts_bp)
app.register_blueprint(subtitles_bp)
app.register_blueprint(download_bp)
app.register_blueprint(capcut_bp)
app.register_blueprint(asr_bp)
app.register_blueprint(license_bp)
app.register_blueprint(project_bp)
app.register_blueprint(updater_bp)
app.register_blueprint(audio_bp)
app.register_blueprint(batch_queue_bp)
app.register_blueprint(comic_review_bp)
app.register_blueprint(export_history_bp)
app.register_blueprint(telegram_bp)
app.register_blueprint(social_publish_bp)
app.register_blueprint(hongguo_bp)

def main():
    import threading
    import webview
    
    # 1. Gán AppUserModelID để Windows Taskbar hiển thị đúng Icon NovaCut thay vì Icon Python mặc định
    if os.name == 'nt':
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('novacut.videoeditor.app.1.0')
        except Exception:
            pass

    # Cấu hình tham số Microsoft Edge WebView2 tối ưu: bật GPU Rasterization, chống crash DWM / TDR
    gpu_args = [
        "--enable-gpu-rasterization",
        "--ignore-gpu-blocklist",
        "--disable-features=CalculateNativeWinOcclusion,DirectCompositionVideoOverlays"
    ]
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join(gpu_args)

    def apply_custom_window_icon():
        """Tự động gắn icon.ico vào Titlebar và Taskbar của cửa sổ NovaCut trên Windows."""
        if os.name != 'nt':
            return
        import ctypes
        import time
        ico_path = os.path.abspath(os.path.join(ROOT_DIR, 'resources', 'icon.ico'))
        if not os.path.exists(ico_path):
            return

        user32 = ctypes.windll.user32
        LR_LOADFROMFILE = 0x00000010
        IMAGE_ICON = 1
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        hicon_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)

        # Quét và gán icon ngay khi cửa sổ được tạo
        for _ in range(30):
            time.sleep(0.2)
            hwnd = user32.FindWindowW(None, 'NovaCut - AI Video & Review Editor')
            if hwnd:
                if hicon_small:
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                if hicon_big:
                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                break

    def free_stale_port_5000():
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', 5000))
            s.close()
            return
        except OSError:
            pass
        if os.name == 'nt':
            try:
                curr_pid = os.getpid()
                out = subprocess.check_output('netstat -ano | findstr :5000', shell=True).decode('utf-8', errors='ignore')
                for line in out.splitlines():
                    if 'LISTENING' in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = int(parts[-1])
                            if pid != curr_pid and pid > 0:
                                print(f"[NovaCut] Giai phong port 5000 tu tien trinh cu PID {pid}...")
                                subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
                time.sleep(0.5)
            except Exception:
                pass

    free_stale_port_5000()

    def start_server():
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Luồng chạy ngầm gắn Icon cho cửa sổ Desktop
    threading.Thread(target=apply_custom_window_icon, daemon=True).start()

    window_ref = None

    def register_dialog_result(result):
        path = result[0] if result else None
        if path:
            from routes.security import register_user_path
            register_user_path(path)
        return path

    def register_dialog_results(result):
        if not result:
            return []
        from routes.security import register_user_path
        paths = []
        for p in result:
            if p:
                norm_p = os.path.normpath(p)
                register_user_path(norm_p)
                paths.append(norm_p)
        return paths

    dialog_open = getattr(getattr(webview, 'FileDialog', None), 'OPEN', getattr(webview, 'OPEN_DIALOG', None))
    dialog_folder = getattr(getattr(webview, 'FileDialog', None), 'FOLDER', getattr(webview, 'FOLDER_DIALOG', None))

    class Api:
        def select_input_video(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Video files (*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None

        def select_multiple_videos(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Video files (*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=True, file_types=file_types)
                return register_dialog_results(result)
            return []

        def select_output_directory(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                result = target_win.create_file_dialog(dialog_folder, allow_multiple=False)
                return register_dialog_result(result)
            return None
            
        def select_image_file(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Image Files (*.png;*.jpg;*.jpeg;*.webp)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None

        def select_audio_file(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Audio files (*.mp3;*.wav;*.m4a;*.aac;*.flac)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None
            
        def select_model_file(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Model files (*.pth)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None
            
        def select_rvc_index_file(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Index files (*.index)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None
            
        def select_srt_file(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('SRT files (*.srt;*.vtt;*.ass)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=False, file_types=file_types)
                return register_dialog_result(result)
            return None

        def select_multiple_srts(self):
            target_win = window_ref or (webview.windows[0] if getattr(webview, 'windows', None) else None)
            if target_win:
                file_types = ('Subtitle files (*.srt;*.vtt;*.ass)', 'All files (*.*)')
                result = target_win.create_file_dialog(dialog_open, allow_multiple=True, file_types=file_types)
                return register_dialog_results(result)
            return []

        def open_in_explorer(self, path):
            import subprocess
            if not path:
                return None
            norm = os.path.normpath(path)
            if os.name == 'nt' and len(norm) >= 2 and norm[1] == ':':
                norm = norm[0].upper() + norm[1:]
            if os.path.isdir(norm):
                try:
                    os.startfile(norm)
                except Exception:
                    subprocess.Popen(f'explorer "{norm}"')
            elif os.path.isfile(norm):
                if norm.upper().startswith(('G:', '\\\\')):
                    try:
                        os.startfile(os.path.dirname(norm))
                    except Exception:
                        subprocess.Popen(f'explorer "{os.path.dirname(norm)}"')
                else:
                    try:
                        subprocess.Popen(f'explorer /select,"{norm}"')
                    except Exception:
                        os.startfile(os.path.dirname(norm))
            elif os.path.exists(os.path.dirname(norm)):
                try:
                    os.startfile(os.path.dirname(norm))
                except Exception:
                    subprocess.Popen(f'explorer "{os.path.dirname(norm)}"')
            return None

        def toggle_fullscreen(self):
            if window_ref:
                window_ref.toggle_fullscreen()
            return None

    import signal
    def handle_exit_signal(sig, frame):
        print("\n[NovaCut] Dang dong ung dung va giai phong toan bo tien trinh con...")
        try:
            from services.hongguo_service import HongguoServiceManager
            HongguoServiceManager.get_instance().stop_services()
        except Exception:
            pass
        try:
            import ffmpeg_installer
            stealth_kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs()
            subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True, **stealth_kwargs)
            subprocess.run(['taskkill', '/F', '/IM', 'movie_summary_cli.exe'], capture_output=True, **stealth_kwargs)
        except Exception:
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)

    api = Api()
    print("[NovaCut] Desktop UI started!")
    import time
    time.sleep(1) # Give Flask a second to start
    
    window_ref = webview.create_window('NovaCut - AI Video & Review Editor', 'http://127.0.0.1:5000', js_api=api, width=1280, height=800, min_size=(1024, 768), maximized=True, fullscreen=False)
    try:
        # Bắt buộc sử dụng EdgeChromium (WebView2) để đảm bảo giao diện hiển thị chuẩn HTML5/CSS3
        # Tắt DevTools (debug=False) để giao diện gọn gàng, không tự mở cửa sổ inspect
        webview.start(gui='edgechromium', debug=False)
    except Exception as e:
        print(f"[NovaCut] Chu y: Khong the khoi dong WebView2 ({e}). Dang tu dong mo ung dung tren trinh duyet mac dinh...")
        import webbrowser
        webbrowser.open('http://127.0.0.1:5000')
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
    
    # Khi người dùng đóng cửa sổ app, dừng triệt để toàn bộ thread và tiến trình ngầm
    print("\n[NovaCut] Cua so ung dung da dong. Dang giai phong tai nguyen...")
    try:
        from services.hongguo_service import HongguoServiceManager
        HongguoServiceManager.get_instance().stop_services()
    except Exception:
        pass
    try:
        import ffmpeg_installer
        stealth_kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs()
        subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True, **stealth_kwargs)
        subprocess.run(['taskkill', '/F', '/IM', 'movie_summary_cli.exe'], capture_output=True, **stealth_kwargs)
    except Exception:
        pass
    os._exit(0)

if __name__ == '__main__':
    main()
