# -*- coding: utf-8 -*-
"""
NovaCut Desktop Launcher
Tự động kích hoạt môi trường làm việc, nạp bin/ vào PATH và khởi động ứng dụng NovaCut.
"""
import os
import sys
import io

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# Xử lý an toàn encoding cho stdout / stderr khi chạy windowed mode trên Windows
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stdout = io.StringIO()

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
else:
    sys.stderr = io.StringIO()

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

# Nạp thư mục bin/ vào PATH
bin_dir = os.path.join(APP_DIR, 'bin')
if os.path.exists(bin_dir) and bin_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

if __name__ == '__main__':
    try:
        import web_app
        web_app.main()
    except Exception as e:
        import ctypes, traceback
        err_msg = f"Loi khoi dong NovaCut:\n\n{str(e)}\n\nChi tiet:\n{traceback.format_exc()}"
        try:
            ctypes.windll.user32.MessageBoxW(None, err_msg, "NovaCut - Loi Khoi Dong", 0x10)
        except Exception:
            pass
