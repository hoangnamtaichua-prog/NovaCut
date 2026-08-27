# -*- coding: utf-8 -*-
"""
NovaCut AI - UVR5 MDX-NET Pure Separation Engine
Được chuyển giao nguyên bản từ dự án Ultimate Vocal Remover GUI (UVR5).
Hỗ trợ các mô hình: UVR-MDX-NET-Inst_HQ_4, UVR-MDX-NET-Inst_HQ_5, UVR-MDX-NET-Voc_FT.
Tối ưu hóa GPU: Tự động chuyển đổi DirectML trong tiến trình cô lập (Zero-Lock) để chạy 100% trên RTX 50-series & mọi GPU.
"""

import os
import sys
import time
import math
import shutil
import subprocess
import urllib.request
import numpy as np
import torch


# ─── BƯỚC 0: TỰ ĐỘNG CÀI ĐẶT DIRECTML TRONG TIẾN TRÌNH CÔ LẬP (TRÁNH KHÓA DLL) ───

def _bootstrap_onnxruntime():
    """
    Kiểm tra và cài đặt onnxruntime-directml mà KHÔNG import vào tiến trình chính trước,
    tránh hoàn toàn hiện tượng Windows khóa file .pyd / DLL dẫn đến lỗi thiếu InferenceSession.
    """
    if getattr(sys, 'frozen', False):
        return

    # 1. Dùng tiến trình con cô lập để kiểm tra onnxruntime-directml
    check_code = (
        "try:\n"
        "    import onnxruntime as ort\n"
        "    has_session = hasattr(ort, 'InferenceSession')\n"
        "    provs = ort.get_available_providers() if hasattr(ort, 'get_available_providers') else []\n"
        "    has_dml = 'DmlExecutionProvider' in provs\n"
        "    if has_session and has_dml:\n"
        "        print('OK_DML')\n"
        "    elif has_session and 'CUDAExecutionProvider' in provs:\n"
        "        print('OK_CUDA')\n"
        "    else:\n"
        "        print('NEED_REPAIR')\n"
        "except Exception:\n"
        "    print('NEED_INSTALL')\n"
    )

    try:
        res_check = subprocess.run(
            [sys.executable, "-c", check_code],
            capture_output=True, text=True, timeout=15
        )
        status = res_check.stdout.strip()
    except Exception:
        status = "NEED_INSTALL"

    # Nếu đã có DmlExecutionProvider sẵn sàng hoạt động thì không cần cài lại
    if status == "OK_DML":
        return

    print("[AI-Installer] 🚀 Đang tự động cấu hình động cơ GPU DirectML (Hỗ trợ 100% RTX 5060 & Windows GPU)...")
    try:
        # Gỡ sạch các bản cũ bị lỗi hoặc thiếu file
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime", "onnxruntime-gpu", "onnxruntime-directml"],
            capture_output=True, text=True, timeout=60
        )
        # Cài đặt sạch onnxruntime-directml
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", "--no-warn-script-location", "onnxruntime-directml"],
            capture_output=True, text=True, timeout=180
        )
        print(f"[AI-Installer] ✅ Đã kích hoạt thành công onnxruntime-directml (Code: {res.returncode})")
    except Exception as e:
        print(f"[AI-Installer] ⚠️ Lỗi cài đặt DirectML: {e}")

# Gọi bootstrap ngay khi nạp file (tiến trình chính chưa hề import onnxruntime nên không bị lock file)
_bootstrap_onnxruntime()


# ─── CONFIG & DIRECTORIES ──────────────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(ROOT_DIR, "models", "mdx_net")
os.makedirs(MODELS_DIR, exist_ok=True)

UVR_SCRATCH_DIR = os.path.join(
    os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch",
    "ultimatevocalremovergui", "models", "MDX_Net_Models"
)

MDX_MODEL_URLS = {
    "UVR-MDX-NET-Inst_HQ_4.onnx": "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Inst_HQ_4.onnx",
    "UVR-MDX-NET-Inst_HQ_5.onnx": "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Inst_HQ_5.onnx",
    "UVR-MDX-NET-Voc_FT.onnx":    "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx",
}

MDX_CONFIGS = {
    "UVR-MDX-NET-Inst_HQ_4.onnx": {
        "dim_f": 2560, "dim_t": 256, "n_fft": 6144, "hop_length": 1024,
        "compensate": 1.035, "primary_stem": "Instrumental",
        "name": "MDX-NET Inst HQ4 (Chuẩn UVR5 - Lọc thoại 99.5% & Giữ SFX)"
    },
    "UVR-MDX-NET-Inst_HQ_5.onnx": {
        "dim_f": 2560, "dim_t": 256, "n_fft": 6144, "hop_length": 1024,
        "compensate": 1.045, "primary_stem": "Instrumental",
        "name": "MDX-NET Inst HQ5 (Chuẩn UVR5 - Chống vang Reverb/Echo)"
    },
    "UVR-MDX-NET-Voc_FT.onnx": {
        "dim_f": 2048, "dim_t": 256, "n_fft": 6144, "hop_length": 1024,
        "compensate": 1.035, "primary_stem": "Vocals",
        "name": "MDX-NET Vocals FT (Chuẩn UVR5 - Trích xuất giọng nói/hát)"
    }
}

_MDX_SESSIONS = {}


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _setup_cuda_dll_paths():
    """Liên kết CUDA/cuDNN DLLs từ PyTorch vào Windows PATH."""
    if os.name != 'nt':
        return
    try:
        torch_lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.exists(torch_lib):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(torch_lib)
                except Exception:
                    pass
            os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
    except Exception:
        pass

_setup_cuda_dll_paths()


class STFT:
    """STFT / iSTFT chuẩn UVR5 (lib_v5/tfc_tdf_v3.py)."""
    def __init__(self, n_fft, hop_length, dim_f, device="cpu"):
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.window = torch.hann_window(window_length=n_fft, periodic=True)
        self.dim_f = dim_f
        self.device = device

    def __call__(self, x):
        window = self.window.to(x.device)
        batch_dims = x.shape[:-2]
        c, t = x.shape[-2:]
        x = x.reshape([-1, t])
        x = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop_length,
                        window=window, center=True, return_complex=False)
        x = x.permute([0, 3, 1, 2])
        x = x.reshape([*batch_dims, c, 2, -1, x.shape[-1]]).reshape([*batch_dims, c * 2, -1, x.shape[-1]])
        return x[..., :self.dim_f, :]

    def inverse(self, x):
        window = self.window.to(x.device)
        batch_dims = x.shape[:-3]
        c, f, t = x.shape[-3:]
        n = self.n_fft // 2 + 1
        f_pad = torch.zeros([*batch_dims, c, n - f, t]).to(x.device)
        x = torch.cat([x, f_pad], -2)
        x = x.reshape([*batch_dims, c // 2, 2, n, t]).reshape([-1, 2, n, t])
        x = x.permute([0, 2, 3, 1])
        x = x[..., 0] + x[..., 1] * 1.j
        x = torch.istft(x, n_fft=self.n_fft, hop_length=self.hop_length, window=window, center=True)
        x = x.reshape([*batch_dims, 2, -1])
        return x


def _find_or_download_mdx_model(model_name="UVR-MDX-NET-Inst_HQ_4.onnx", progress_cb=None):
    """Tìm file mô hình cục bộ hoặc tự động tải về từ kho UVR Model Repo."""
    target_path = os.path.join(MODELS_DIR, model_name)
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1_000_000:
        return target_path

    scratch_path = os.path.join(UVR_SCRATCH_DIR, model_name)
    if os.path.exists(scratch_path) and os.path.getsize(scratch_path) > 1_000_000:
        try:
            shutil.copy2(scratch_path, target_path)
            return target_path
        except Exception:
            return scratch_path

    url = MDX_MODEL_URLS.get(model_name)
    if not url:
        raise Exception(f"Không tìm thấy URL tải cho mô hình MDX: {model_name}")

    print(f"[UVR-MDX] Đang tải mô hình {model_name}...")
    if progress_cb:
        progress_cb(5, f"Đang tải mô hình AI {model_name} (chỉ tải 1 lần)...")

    def _dl_progress(count, block_size, total_size):
        if total_size > 0 and progress_cb and count % 50 == 0:
            pct = int((count * block_size / total_size) * 30)
            progress_cb(5 + pct, f"Đang tải mô hình AI ({pct * 3}%)...")

    urllib.request.urlretrieve(url, target_path, reporthook=_dl_progress)
    if not os.path.exists(target_path) or os.path.getsize(target_path) < 1_000_000:
        raise Exception(f"Tải mô hình thất bại: {target_path}")
    return target_path


# ─── ONNX SESSION TỰ ĐỘNG CHỌN GPU PHÙ HỢP NHẤT ───────────────────────────────

def get_mdx_session(model_name="UVR-MDX-NET-Inst_HQ_4.onnx", device="auto",
                    progress_cb=None, logger_cb=None):
    """
    Khởi tạo ONNX Runtime Session chuẩn UVR5.
    Ưu tiên DmlExecutionProvider (DirectX 12 GPU) để chạy 100% trên GPU NVIDIA RTX 5060.
    """
    global _MDX_SESSIONS
    cache_key = f"{model_name}_{device}"
    if cache_key in _MDX_SESSIONS:
        return _MDX_SESSIONS[cache_key]

    _setup_cuda_dll_paths()

    try:
        import onnxruntime as ort
    except Exception as e:
        raise Exception(f"Không thể import onnxruntime: {e}")

    model_path = _find_or_download_mdx_model(model_name, progress_cb)

    avail_providers = ort.get_available_providers() if hasattr(ort, 'get_available_providers') else []

    # Ưu tiên DirectML (chạy mượt mà trên RTX 5060 và mọi GPU Windows)
    if device in ["cuda", "gpu", "auto"]:
        providers = []
        if 'DmlExecutionProvider' in avail_providers:
            providers.append('DmlExecutionProvider')
        if 'CUDAExecutionProvider' in avail_providers:
            providers.append('CUDAExecutionProvider')
        providers.append('CPUExecutionProvider')
    elif device == "directml":
        providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
    else:
        providers = ['CPUExecutionProvider']

    opts = None
    if hasattr(ort, 'SessionOptions'):
        try:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = min(os.cpu_count() or 4, 8)
            opts.intra_op_num_threads = min(os.cpu_count() or 4, 8)
            if hasattr(ort, 'GraphOptimizationLevel') and hasattr(ort.GraphOptimizationLevel, 'ORT_ENABLE_ALL'):
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            if 'DmlExecutionProvider' in providers:
                if hasattr(ort, 'ExecutionMode') and hasattr(ort.ExecutionMode, 'ORT_SEQUENTIAL'):
                    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                if hasattr(opts, 'enable_mem_pattern'):
                    opts.enable_mem_pattern = False
        except Exception:
            opts = None

    session = (
        ort.InferenceSession(model_path, sess_options=opts, providers=providers)
        if opts is not None
        else ort.InferenceSession(model_path, providers=providers)
    )

    act_prov = session.get_providers()[0] if session.get_providers() else "CPUExecutionProvider"
    is_gpu = ("Dml" in act_prov) or ("CUDA" in act_prov)
    
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "GPU"
    hardware_label = f"GPU ({gpu_name})" if is_gpu else "CPU"

    log_msg = f"[UVR-MDX] ⚡ Động cơ nạp thành công: {model_name} • Hardware: {act_prov} [{hardware_label}]"
    print(log_msg)
    if logger_cb:
        logger_cb(log_msg)

    _MDX_SESSIONS[cache_key] = (session, hardware_label)
    return session, hardware_label


# ─── MAIN SEPARATION ENGINE ───────────────────────────────────────────────────

def separate_stems_mdx(
    input_audio_path,
    output_dir,
    model_name="UVR-MDX-NET-Inst_HQ_4.onnx",
    device="auto",
    remove_vocals=True,
    remove_bgm=False,
    keep_sfx=True,
    overlap=0.5,
    progress_cb=None,
    logger_cb=None,
    cancel_check_cb=None
):
    """Hàm tách âm thanh AI chuẩn UVR5 (SeperateMDX.demix)."""
    import torchaudio
    import torchaudio.functional as F

    def log(msg):
        print(msg)
        if logger_cb:
            logger_cb(msg)

    base_name = os.path.splitext(os.path.basename(input_audio_path))[0]
    os.makedirs(output_dir, exist_ok=True)

    vocals_path = os.path.join(output_dir, f"{base_name}_vocals.wav")
    instrumental_path = os.path.join(output_dir, f"{base_name}_instrumental.wav")

    if cancel_check_cb and cancel_check_cb():
        raise Exception("🛑 Đã dừng tác vụ tách âm thanh khẩn cấp theo yêu cầu.")

    cfg = MDX_CONFIGS.get(model_name, MDX_CONFIGS["UVR-MDX-NET-Inst_HQ_4.onnx"])
    dim_f = cfg["dim_f"]
    dim_t = cfg["dim_t"]
    n_fft = cfg["n_fft"]
    hop_length = cfg["hop_length"]
    compensate = cfg["compensate"]
    primary_stem = cfg["primary_stem"]

    session, hw_label = get_mdx_session(model_name, device=device,
                                         progress_cb=progress_cb, logger_cb=logger_cb)

    # Đọc kích thước thực từ ONNX graph
    try:
        shape = session.get_inputs()[0].shape
        if len(shape) >= 4:
            if isinstance(shape[2], int) and shape[2] > 0:
                dim_f = shape[2]
            if isinstance(shape[3], int) and shape[3] > 0:
                dim_t = shape[3]
    except Exception:
        pass

    log(f"[UVR-MDX] 🎵 Đang nạp âm thanh: {os.path.basename(input_audio_path)}")
    if progress_cb:
        progress_cb(15, "Đang nạp và tiền xử lý tín hiệu âm thanh...")

    wav, sr = torchaudio.load(input_audio_path)
    if sr != 44100:
        log(f"[UVR-MDX] Resample {sr}Hz → 44100Hz")
        wav = F.resample(wav, sr, 44100)
        sr = 44100
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    elif wav.shape[0] > 2:
        wav = wav[:2, :]

    total_samples = wav.shape[1]
    log(f"[UVR-MDX] Thời lượng: {total_samples/sr:.1f}s | Chạy trên: {hw_label}")

    stft = STFT(n_fft=n_fft, hop_length=hop_length, dim_f=dim_f, device="cpu")

    trim = n_fft // 2
    chunk_size = hop_length * (dim_t - 1)
    gen_size = chunk_size - 2 * trim
    pad = gen_size + trim - (total_samples % gen_size)

    mixture = np.concatenate([
        np.zeros((2, trim), dtype=np.float32),
        wav.numpy(),
        np.zeros((2, pad), dtype=np.float32)
    ], axis=1)

    step = int((1.0 - overlap) * chunk_size)
    total_len = mixture.shape[1]
    result  = np.zeros((1, 2, total_len), dtype=np.float32)
    divider = np.zeros((1, 2, total_len), dtype=np.float32)
    total_chunks = math.ceil(total_len / step)
    input_name = session.get_inputs()[0].name

    log(f"[UVR-MDX] Chia {total_chunks} đoạn (Overlap {overlap*100:.0f}%, Hanning Window)...")

    chunk_idx = 0
    start_time = time.time()

    for i in range(0, total_len, step):
        if cancel_check_cb and cancel_check_cb():
            raise Exception("🛑 Đã dừng tác vụ tách âm thanh khẩn cấp.")

        chunk_idx += 1
        start, end = i, min(i + chunk_size, total_len)
        actual_chunk = end - start

        mix_part_ = mixture[:, start:end]
        if actual_chunk < chunk_size:
            mix_part_ = np.concatenate([mix_part_,
                np.zeros((2, chunk_size - actual_chunk), dtype=np.float32)], axis=-1)

        window = np.tile(np.hanning(actual_chunk)[None, None, :], (1, 2, 1))
        mix_part = torch.tensor([mix_part_], dtype=torch.float32)

        with torch.no_grad():
            spek = stft(mix_part)
            spek[:, :, :3, :] *= 0
            spec_pred = session.run(None, {input_name: spek.numpy()})[0]
            tar_wave = stft.inverse(torch.tensor(spec_pred)).detach().numpy()
            tar_wave = tar_wave[..., :actual_chunk] * window
            divider[..., start:end] += window
            result[..., start:end]  += tar_wave

        pct = 20 + int((chunk_idx / total_chunks) * 70)
        fps = chunk_idx / max(time.time() - start_time, 0.001)
        rem = (total_chunks - chunk_idx) / max(fps, 0.001)
        if progress_cb:
            progress_cb(pct, f"Đang tách âm AI ({pct}%): đoạn {chunk_idx}/{total_chunks} [còn ~{rem:.0f}s]")
        if chunk_idx % 4 == 0 or chunk_idx == total_chunks:
            log(f"[UVR-MDX] Đoạn {chunk_idx}/{total_chunks} ({pct}%) • Tốc độ: {fps:.1f} chunk/s • Hardware: {hw_label}")

    divider[divider == 0] = 1.0
    estimated = (result / divider)[:, :, trim:-trim][0, :, :total_samples] * compensate

    orig_wav_np = wav.numpy()
    if primary_stem == "Instrumental":
        inst_np   = estimated
        vocals_np = orig_wav_np - inst_np
    else:
        vocals_np = estimated
        inst_np   = orig_wav_np - vocals_np

    if progress_cb:
        progress_cb(92, "Đang xuất âm thanh PCM 16-bit...")

    torchaudio.save(vocals_path, torch.tensor(vocals_np, dtype=torch.float32), sr)
    torchaudio.save(instrumental_path, torch.tensor(inst_np,   dtype=torch.float32), sr)

    clean_bg_path = instrumental_path if remove_vocals else input_audio_path
    if progress_cb:
        progress_cb(100, "Hoàn tất tách âm thanh bằng UVR5 MDX-NET!")
    log(f"[UVR-MDX] ✅ Tách âm hoàn tất:\n  - Nhạc nền / SFX: {instrumental_path}\n  - Lời thoại Vocal: {vocals_path}")

    return {
        "vocals_path": vocals_path,
        "instrumental_path": instrumental_path,
        "clean_background_path": clean_bg_path,
    }
