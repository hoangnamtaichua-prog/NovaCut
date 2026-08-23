import os
import sys
import urllib.request
import zipfile
import shutil
import ssl

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

def get_bin_dir():
    """Lấy thư mục bin chuẩn xác dù chạy từ source, Shortcut hay file EXE đóng gói."""
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "bin"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "bin") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(ROOT_DIR, "bin"),
        os.path.join(os.getcwd(), "bin")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    # Mặc định tạo ở thư mục cạnh file exe hoặc ROOT_DIR
    target = os.path.join(os.path.dirname(sys.executable), "bin") if getattr(sys, 'frozen', False) else os.path.join(ROOT_DIR, "bin")
    os.makedirs(target, exist_ok=True)
    return target

def get_ffmpeg_path():
    """Tìm đường dẫn tệp thực thi ffmpeg.exe trên hệ thống theo thứ tự ưu tiên."""
    if os.name == 'nt':
        candidates = [
            os.path.join(os.path.dirname(sys.executable), "bin", "ffmpeg.exe"),
            os.path.join(getattr(sys, '_MEIPASS', ''), "bin", "ffmpeg.exe") if hasattr(sys, '_MEIPASS') else None,
            os.path.join(ROOT_DIR, "bin", "ffmpeg.exe"),
            os.path.join(os.getcwd(), "bin", "ffmpeg.exe")
        ]
        for c in candidates:
            if c and os.path.exists(c) and os.path.getsize(c) > 1000:
                return os.path.normpath(c)
                
    cand = shutil.which('ffmpeg.exe') or shutil.which('ffmpeg')
    if cand and os.path.exists(cand):
        return os.path.normpath(cand)
    return None

def ensure_ffmpeg(yield_func=None):
    """
    Đảm bảo tệp ffmpeg.exe khả dụng trên hệ thống.
    Nếu chưa có trên Windows, tự động tải bản build static và giải nén vào thư mục bin/.
    """
    path = get_ffmpeg_path()
    if path:
        return path
        
    if os.name != 'nt':
        raise FileNotFoundError("Không tìm thấy ffmpeg. Vui lòng cài đặt qua Package Manager (brew/apt).")
        
    def log(msg):
        if yield_func:
            yield_func(f"data: {msg}\n\n")
        else:
            try:
                print(msg)
            except:
                pass
            
    log("ℹ️ Đang kiểm tra lõi xử lý FFmpeg...")
    log("📥 Không tìm thấy FFmpeg, hệ thống bắt đầu tự động tải về (chỉ tải 1 lần duy nhất). Vui lòng chờ đợi...")
    
    bin_dir = get_bin_dir()
    ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")
    zip_path = os.path.join(bin_dir, "ffmpeg.zip")
    
    try:
        # Download
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        log("📦 Tải xong FFmpeg. Đang giải nén...")
        
        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            exe_name = "ffmpeg.exe"
            ffmpeg_zip_path = None
            for fileinfo in zip_ref.infolist():
                if fileinfo.filename.endswith(exe_name):
                    ffmpeg_zip_path = fileinfo.filename
                    break
            
            if not ffmpeg_zip_path:
                raise Exception("Không tìm thấy ffmpeg.exe trong file tải về!")
                
            extracted_path = zip_ref.extract(ffmpeg_zip_path, bin_dir)
            if os.path.exists(ffmpeg_exe):
                try: os.remove(ffmpeg_exe)
                except: pass
            shutil.move(extracted_path, ffmpeg_exe)
            
        log("✅ Đã cài đặt xong lõi FFmpeg!")
        
    except Exception as e:
        log(f"🛑 Lỗi khi tự động tải FFmpeg: {str(e)}")
        raise e
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass
            
        try:
            if 'ffmpeg_zip_path' in locals() and ffmpeg_zip_path:
                extracted_dir = os.path.join(bin_dir, ffmpeg_zip_path.split('/')[0])
                if os.path.exists(extracted_dir):
                    shutil.rmtree(extracted_dir, ignore_errors=True)
        except:
            pass

    return ffmpeg_exe
