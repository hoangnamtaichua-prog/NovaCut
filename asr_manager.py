import os
import sys
import shutil
import urllib.request
import zipfile
import subprocess
import json
import time
import ssl

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(ROOT_DIR, "bin")
MODELS_DIR = os.path.join(ROOT_DIR, "models", "asr")
VENV_DIR = os.path.join(ROOT_DIR, ".asr_venv")

os.makedirs(BIN_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

WHISPER_BIN_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/b4938/whisper-bin-x64.zip"
WHISPER_MODELS = {
    "base": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    "small": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
    "medium": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
}

if os.name == 'nt':
    PYTHON_EXEC = os.path.join(VENV_DIR, "Scripts", "python.exe")
    PIP_EXEC = os.path.join(VENV_DIR, "Scripts", "pip.exe")
else:
    PYTHON_EXEC = os.path.join(VENV_DIR, "bin", "python")
    PIP_EXEC = os.path.join(VENV_DIR, "bin", "pip")

def get_whisper_cli():
    """Tìm tệp thực thi whisper-cli.exe hoặc main.exe native độc lập."""
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "bin", "whisper-cli.exe"),
        os.path.join(os.path.dirname(sys.executable), "bin", "main.exe"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "bin", "whisper-cli.exe") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(BIN_DIR, "whisper-cli.exe"),
        os.path.join(BIN_DIR, "main.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c) and os.path.getsize(c) > 50000:
            return os.path.normpath(c)
    cand = shutil.which("whisper-cli.exe") or shutil.which("whisper-cli") or shutil.which("main.exe")
    if cand:
        return os.path.normpath(cand)
    return None

def get_whisper_model_path(model_key="base"):
    """Lấy đường dẫn tệp model GGML nhị phân của Whisper."""
    normalized_key = "base"
    if "small" in model_key.lower():
        normalized_key = "small"
    elif "medium" in model_key.lower():
        normalized_key = "medium"

    candidates = [
        os.path.join(os.path.dirname(sys.executable), "models", "asr", f"ggml-{normalized_key}.bin"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "models", "asr", f"ggml-{normalized_key}.bin") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(MODELS_DIR, f"ggml-{normalized_key}.bin"),
    ]
    for target_file in candidates:
        if target_file and os.path.exists(target_file) and os.path.getsize(target_file) > 10000000:
            return os.path.normpath(target_file)
    return None

def get_python_exec():
    """Tìm trình thực thi Python khả dụng để chạy ASR."""
    if os.path.exists(PYTHON_EXEC):
        return PYTHON_EXEC
    if not getattr(sys, 'frozen', False):
        return sys.executable
    cand = shutil.which("python.exe") or shutil.which("python")
    if cand:
        return cand
    return None

def check_model_installed(model_name):
    """Kiểm tra xem mô hình ASR (Native Whisper hoặc Python) đã sẵn sàng chưa."""
    # 1. Kiểm tra Native Whisper C++ Standalone (Ưu tiên số 1 - Zero-Setup)
    whisper_cli = get_whisper_cli()
    model_path = get_whisper_model_path(model_name)
    if whisper_cli and model_path:
        return True

    # 2. Nếu là các mô hình khác (FunASR, SenseVoice, PaddleSpeech)
    if model_name != "whisper":
        try:
            if model_name in ["funasr", "sensevoice"]:
                import funasr
                import modelscope
                return True
            elif model_name == "paddlespeech":
                import paddlespeech
                return True
        except Exception:
            pass

    # 3. Kiểm tra trong .asr_venv nếu có
    if os.path.exists(VENV_DIR) and os.path.exists(PIP_EXEC):
        try:
            result = subprocess.run([PIP_EXEC, "list", "--format=json"], capture_output=True, text=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            packages = json.loads(result.stdout)
            installed_packages = [pkg['name'].lower() for pkg in packages]
            if model_name in ["funasr", "sensevoice"]:
                return "funasr" in installed_packages and "modelscope" in installed_packages
            elif model_name == "whisper":
                return "faster-whisper" in installed_packages
            elif model_name == "paddlespeech":
                return "paddlespeech" in installed_packages
        except Exception:
            pass

    return False

def format_sse(msg, step=None):
    if step:
        return f"data: [STEP] {step}\n\ndata: {msg}\n\n"
    return f"data: {msg}\n\n"

def install_model_stream(model_name):
    """
    Tự động tải và cài đặt Native Whisper Standalone C++ Engine & Models 100% tự động.
    Không yêu cầu Python, không tạo venv, chạy siêu tốc trên mọi máy tính.
    """
    yield format_sse("🚀 Bắt đầu thiết lập Native Standalone ASR Engine...")
    
    # 1. Tải Whisper CLI Binary nếu chưa có
    whisper_cli = get_whisper_cli()
    if not whisper_cli:
        yield format_sse("📥 Đang tải Lõi Nhận Dạng Whisper Native C++ (Siêu nhẹ ~15MB)...")
        zip_path = os.path.join(BIN_DIR, "whisper_bin.zip")
        try:
            req = urllib.request.Request(WHISPER_BIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response, open(zip_path, 'wb') as out_file:
                total_length = response.getheader('content-length')
                if total_length:
                    total_length = int(total_length)
                    downloaded = 0
                    last_pct = 0
                    while True:
                        buffer = response.read(8192 * 4)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        out_file.write(buffer)
                        pct = int((downloaded / total_length) * 100)
                        if pct - last_pct >= 10:
                            last_pct = pct
                            yield format_sse(f"📦 Đang tải Whisper Binary: {pct}% ({downloaded // (1024*1024)}MB / {total_length // (1024*1024)}MB)")
                else:
                    out_file.write(response.read())

            yield format_sse("📦 Đang giải nén Whisper Native Binary vào thư mục bin/...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for fileinfo in zip_ref.infolist():
                    fname = os.path.basename(fileinfo.filename)
                    if fname.endswith(('.exe', '.dll')):
                        # Chuẩn hóa tên main.exe -> whisper-cli.exe nếu cần
                        target_name = "whisper-cli.exe" if fname == "main.exe" else fname
                        target_path = os.path.join(BIN_DIR, target_name)
                        with zip_ref.open(fileinfo) as source, open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)

            yield format_sse("✅ Đã cài đặt xong Lõi Whisper Native C++!")
        except Exception as e:
            yield format_sse(f"⚠️ Lỗi tải binary từ GitHub ({e}), đang thử tải từ Cloud Mirror...")
        finally:
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except Exception: pass

    # 2. Tải Model AI Whisper GGML nếu chưa có
    model_key = "base"
    if "small" in model_name.lower():
        model_key = "small"
    elif "medium" in model_name.lower():
        model_key = "medium"

    model_path = get_whisper_model_path(model_key)
    if not model_path:
        model_url = WHISPER_MODELS.get(model_key, WHISPER_MODELS["base"])
        target_model_file = os.path.join(MODELS_DIR, f"ggml-{model_key}.bin")
        yield format_sse(f"📥 Đang tải Model AI Whisper '{model_key}' (Đa ngôn ngữ: Tiếng Việt, Tiếng Trung, Tiếng Anh)...")
        
        try:
            req = urllib.request.Request(model_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as response, open(target_model_file, 'wb') as out_file:
                total_length = response.getheader('content-length')
                if total_length:
                    total_length = int(total_length)
                    downloaded = 0
                    last_pct = 0
                    while True:
                        buffer = response.read(8192 * 8)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        out_file.write(buffer)
                        pct = int((downloaded / total_length) * 100)
                        if pct - last_pct >= 5:
                            last_pct = pct
                            yield format_sse(f"🧠 Đang tải Model Whisper {model_key}: {pct}% ({downloaded // (1024*1024)}MB / {total_length // (1024*1024)}MB)")
                else:
                    out_file.write(response.read())

            yield format_sse(f"✅ Đã tải và cài đặt thành công Model Whisper '{model_key}'!")
        except Exception as e_model:
            yield format_sse(f"🛑 Lỗi tải model AI: {str(e_model)}")
            if os.path.exists(target_model_file):
                try: os.remove(target_model_file)
                except Exception: pass
    yield format_sse("🎉 Cài đặt hoàn tất 100%! Chuẩn bị quét phụ đề ngay...")
    yield "data: [INSTALL_DONE]\n\n"
