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

# Khởi tạo cơ chế OTA Patch Overlay (ưu tiên tuyệt đối nạp file .py mới từ patches/active/ trước .pyd / frozen)
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(ROOT_DIR)

PATCH_DIR = os.path.join(ROOT_DIR, 'patches', 'active')
os.makedirs(PATCH_DIR, exist_ok=True)

for p in [ROOT_DIR, PATCH_DIR]:
    if p in sys.path:
        sys.path.remove(p)
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

app = Flask(__name__, static_folder='web')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Ensure we're running from the root directory so resources are found
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT_DIR)

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

    # Cấu hình tham số Microsoft Edge WebView2 tối ưu, chống crash GPU DWM / TDR trên dòng card RTX 50-series
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-features=CalculateNativeWinOcclusion,DirectCompositionVideoOverlays"

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

    def start_server():
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Luồng chạy ngầm gắn Icon cho cửa sổ Desktop
    threading.Thread(target=apply_custom_window_icon, daemon=True).start()

    window_ref = None

    class Api:
        def select_input_video(self):
            if window_ref:
                file_types = ('Video files (*.mp4;*.mkv;*.avi)', 'All files (*.*)')
                result = window_ref.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                return result[0] if result else None
            return None
            
        def select_output_directory(self):
            if window_ref:
                result = window_ref.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
                return result[0] if result else None
            return None
            
        
        def select_image_file(self):
            import webview
            file_types = ('Image Files (*.png;*.jpg;*.jpeg)', 'All files (*.*)')
            result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
            return result[0] if result else None

        def select_audio_file(self):
            if window_ref:
                file_types = ('Audio files (*.mp3;*.wav;*.m4a)', 'All files (*.*)')
                result = window_ref.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                return result[0] if result else None
            return None
            
        def select_model_file(self):
            if window_ref:
                file_types = ('Model files (*.pth)', 'All files (*.*)')
                result = window_ref.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                return result[0] if result else None
            return None
            
        def select_rvc_index_file(self):
            if window_ref:
                file_types = ('Index files (*.index)', 'All files (*.*)')
                result = window_ref.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                return result[0] if result else None
            return None
            
        def select_srt_file(self):
            file_types = ('SRT files (*.srt)', 'All files (*.*)')
            result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
            return result[0] if result else None

        def open_in_explorer(self, path):
            import subprocess
            if os.path.exists(path):
                subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            return None

        def toggle_fullscreen(self):
            if window_ref:
                window_ref.toggle_fullscreen()
            return None

    import signal
    def handle_exit_signal(sig, frame):
        print("\n[NovaCut] Dang dong ung dung va giai phong toan bo tien trinh con...")
        try:
            subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            subprocess.run(['taskkill', '/F', '/IM', 'movie_summary_cli.exe'], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
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
        webview.start(gui='edgechromium')
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
        subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        subprocess.run(['taskkill', '/F', '/IM', 'movie_summary_cli.exe'], capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
    except Exception:
        pass
    os._exit(0)

if __name__ == '__main__':
    main()
