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

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, 'web', 'index.html')):
            norm_curr = os.path.normpath(curr).lower()
            if not norm_curr.endswith(os.path.normpath('patches/active').lower()) and not norm_curr.endswith(os.path.normpath('release/novacut').lower()):
                return os.path.abspath(curr)
        curr = os.path.dirname(curr)
    return os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = get_app_root_dir()
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
    # 0. Ưu tiên biến môi trường FFMPEG_PATH hoặc cờ thử nghiệm VIDEO_EXPORT_EXPERIMENTAL_GPU
    env_ffmpeg = os.environ.get('FFMPEG_PATH')
    if env_ffmpeg and os.path.exists(env_ffmpeg):
        return os.path.normpath(env_ffmpeg)

    if os.environ.get('VIDEO_EXPORT_EXPERIMENTAL_GPU', '1') == '1':
        exp_path = os.path.join(ROOT_DIR, "tools", "ffmpeg-nvenc-test", "ffmpeg.exe")
        if os.path.exists(exp_path) and os.path.getsize(exp_path) > 1000:
            return os.path.normpath(exp_path)

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


def get_stealth_subprocess_kwargs():
    """
    Trả về cấu hình chuẩn Windows để đảm bảo 100% không bao giờ nháy/bật cửa sổ đen Console/CMD:
    1. creationflags = 0x08000000 (CREATE_NO_WINDOW)
    2. startupinfo: STARTF_USESHOWWINDOW + SW_HIDE
    3. stdin = subprocess.DEVNULL (ngắt kế thừa console stdin)
    """
    if os.name != 'nt':
        return {}
    import subprocess
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        'creationflags': 0x08000000,
        'startupinfo': si,
        'stdin': subprocess.DEVNULL
    }


_HW_CAPS_CACHE = {}



def get_hardware_capabilities(ffmpeg_path=None):
    """
    Phân tích toàn diện và cache khả năng hỗ trợ phần cứng của binary FFmpeg hiện tại:
    - NVENC (H.264, HEVC)
    - Hardware Decoder NVDEC (av1_cuvid, h264_cuvid, hevc_cuvid, -hwaccel cuda)
    - QSV / AMF / MediaFoundation
    - Thông tin GPU và Driver NVIDIA
    - Chi tiết mã lỗi cụ thể nếu GPU encoder thất bại (để hiển thị UI, không bao giờ fallback im lặng)
    """
    global _HW_CAPS_CACHE
    if not ffmpeg_path:
        ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return {
            'ffmpeg_path': None,
            'nvenc_supported': False,
            'nvenc_error': 'Không tìm thấy FFmpeg',
            'hevc_nvenc_supported': False,
            'qsv_supported': False,
            'amf_supported': False,
            'mf_supported': False,
            'hw_decoders': {},
            'gpu_name': None,
            'gpu_model': 'N/A',
            'driver_version': None,
            'supported_encoders': ['libx264'],
            'hardware_decoders': []
        }

    mtime = os.path.getmtime(ffmpeg_path)
    cache_key = (ffmpeg_path, mtime)
    if cache_key in _HW_CAPS_CACHE:
        return _HW_CAPS_CACHE[cache_key]

    import subprocess
    stealth_kwargs = get_stealth_subprocess_kwargs()

    caps = {
        'ffmpeg_path': ffmpeg_path,
        'nvenc_supported': False,
        'nvenc_error': None,
        'hevc_nvenc_supported': False,
        'qsv_supported': False,
        'amf_supported': False,
        'mf_supported': False,
        'hw_decoders': {},
        'gpu_name': None,
        'driver_version': None
    }

    # Query GPU and Driver via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            res_smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3, **stealth_kwargs
            )
            if res_smi.returncode == 0 and res_smi.stdout.strip():
                parts = [p.strip() for p in res_smi.stdout.strip().splitlines()[0].split(',')]
                if len(parts) >= 1:
                    caps['gpu_name'] = parts[0]
                if len(parts) >= 2:
                    caps['driver_version'] = parts[1]
        except Exception:
            pass

    def _test_codec(args):
        try:
            cmd = [ffmpeg_path, '-y', '-hide_banner', '-nostdin'] + args
            res = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=4, **stealth_kwargs)
            return res.returncode == 0, res.stderr.strip()
        except Exception as ex:
            return False, str(ex)

    # 1. Test h264_nvenc
    ok_nvenc, err_nvenc = _test_codec(['-f', 'lavfi', '-i', 'testsrc=s=256x256:d=0.2', '-c:v', 'h264_nvenc', '-preset', 'p4', '-f', 'null', '-'])
    if ok_nvenc:
        caps['nvenc_supported'] = True
    else:
        caps['nvenc_supported'] = False
        caps['nvenc_error'] = err_nvenc

    # 2. Test hevc_nvenc
    ok_hevc, _ = _test_codec(['-f', 'lavfi', '-i', 'testsrc=s=256x256:d=0.2', '-c:v', 'hevc_nvenc', '-preset', 'p4', '-f', 'null', '-'])
    caps['hevc_nvenc_supported'] = ok_hevc

    # 3. Test QSV
    ok_qsv, _ = _test_codec(['-f', 'lavfi', '-i', 'testsrc=s=256x256:d=0.2', '-c:v', 'h264_qsv', '-preset', 'veryfast', '-f', 'null', '-'])
    caps['qsv_supported'] = ok_qsv

    # 4. Test AMF
    ok_amf, _ = _test_codec(['-f', 'lavfi', '-i', 'testsrc=s=256x256:d=0.2', '-c:v', 'h264_amf', '-f', 'null', '-'])
    caps['amf_supported'] = ok_amf

    # 5. Test MediaFoundation (mf)
    ok_mf, _ = _test_codec(['-f', 'lavfi', '-i', 'testsrc=s=256x256:d=0.2', '-c:v', 'h264_mf', '-f', 'null', '-'])
    caps['mf_supported'] = ok_mf

    # 6. Test Hardware Decoders (CUDA / CUVID)
    if caps['nvenc_supported']:
        # Probe decoders via ffmpeg -decoders
        try:
            res_dec = subprocess.run([ffmpeg_path, '-hide_banner', '-decoders'], capture_output=True, encoding='utf-8', errors='replace', timeout=3, **stealth_kwargs)
            dec_txt = res_dec.stdout.lower() if res_dec.returncode == 0 else ''
            caps['hw_decoders'] = {
                'av1': 'av1_cuvid' in dec_txt,
                'h264': 'h264_cuvid' in dec_txt,
                'hevc': 'hevc_cuvid' in dec_txt,
                'cuda_hwaccel': True
            }
        except Exception:
            pass

    # Build standardized encoder & decoder lists for consumers
    supported_encoders = ['libx264']
    if caps.get('nvenc_supported'):
        supported_encoders.append('h264_nvenc')
    if caps.get('hevc_nvenc_supported'):
        supported_encoders.append('hevc_nvenc')
    if caps.get('qsv_supported'):
        supported_encoders.append('h264_qsv')
    if caps.get('amf_supported'):
        supported_encoders.append('h264_amf')
    if caps.get('mf_supported'):
        supported_encoders.append('h264_mf')
    caps['supported_encoders'] = supported_encoders
    caps['gpu_model'] = caps.get('gpu_name') or 'GPU'

    hardware_decoders = []
    if caps.get('hw_decoders', {}).get('cuda_hwaccel'):
        hardware_decoders.append('cuda')
    for dec_name, supported in caps.get('hw_decoders', {}).items():
        if supported and dec_name != 'cuda_hwaccel':
            hardware_decoders.append(f"{dec_name}_cuvid")
    caps['hardware_decoders'] = hardware_decoders

    _HW_CAPS_CACHE[cache_key] = caps
    return caps


def detect_hardware_encoder(ffmpeg_path=None):
    """
    Phát hiện và kiểm tra tính khả dụng thực tế của GPU Hardware Encoder (NVENC, QSV, AMF, MF).
    Trả về: (encoder_name, is_gpu, encoder_args)
    """
    caps = get_hardware_capabilities(ffmpeg_path)
    if caps.get('nvenc_supported'):
        return ('h264_nvenc', True, ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '20'])
    if caps.get('qsv_supported'):
        return ('h264_qsv', True, ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-global_quality', '20'])
    if caps.get('amf_supported'):
        return ('h264_amf', True, ['-c:v', 'h264_amf', '-quality', 'quality'])
    if caps.get('mf_supported'):
        return ('h264_mf', True, ['-c:v', 'h264_mf'])
    return ('libx264', False, ['-c:v', 'libx264', '-preset', 'faster', '-crf', '20'])



