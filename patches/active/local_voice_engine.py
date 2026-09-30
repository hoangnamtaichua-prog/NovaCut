import os
import sys
import time
import json
import wave
import shutil
import threading
import subprocess
import numpy as np

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
CLONES_DIR = os.path.join(ROOT_DIR, "voices", "local_clones")
SAMPLES_DIR = os.path.join(ROOT_DIR, "web", "samples")
os.makedirs(CLONES_DIR, exist_ok=True)
os.makedirs(SAMPLES_DIR, exist_ok=True)

# Curated Local Voice Presets (Vietnamese & English)
LOCAL_VOICE_PRESETS = [
    {
        "id": "local_ngoc_huyen",
        "preset_name": "Ngọc Huyền",
        "name": "Ngọc Huyền (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Bắc",
        "gender": "Female",
        "age": "young",
        "style": "story",
        "tag": "Local Voice • Miền Bắc Nữ • Giọng đọc tự nhiên chuẩn 48kHz",
        "avatar": "🎙️",
        "preview_url": "/samples/local_ngoc_huyen.wav"
    },
    {
        "id": "local_minh_duc",
        "preset_name": "Minh Đức",
        "name": "Minh Đức (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Bắc",
        "gender": "Male",
        "age": "young",
        "style": "news",
        "tag": "Local Voice • Miền Bắc Nam • Phong cách tin tức / Review",
        "avatar": "👦",
        "preview_url": "/samples/local_minh_duc.wav"
    },
    {
        "id": "local_truc_ly",
        "preset_name": "Trúc Ly",
        "name": "Trúc Ly (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Bắc",
        "gender": "Female",
        "age": "young",
        "style": "story",
        "tag": "Local Voice • Miền Bắc Nữ • Truyền cảm tự nhiên",
        "avatar": "👩",
        "preview_url": "/samples/local_truc_ly.wav"
    },
    {
        "id": "local_thai_son",
        "preset_name": "Thái Sơn",
        "name": "Thái Sơn (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Nam",
        "gender": "Male",
        "age": "middle_aged",
        "style": "story",
        "tag": "Local Voice • Miền Nam Nam • Phong cách kể chuyện",
        "avatar": "🎙️",
        "preview_url": "/samples/local_thai_son.wav"
    },
    {
        "id": "local_thuc_doan",
        "preset_name": "Thục Đoan",
        "name": "Thục Đoan (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Nam",
        "gender": "Female",
        "age": "young",
        "style": "story",
        "tag": "Local Voice • Miền Nam Nữ • Dịu dàng truyền cảm",
        "avatar": "👧",
        "preview_url": "/samples/local_thuc_doan.wav"
    },
    {
        "id": "local_thanh_binh",
        "preset_name": "Thanh Bình",
        "name": "Thanh Bình (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Bắc",
        "gender": "Male",
        "age": "young",
        "style": "review",
        "tag": "Local Voice • Miền Bắc Nam • Thuyết minh Review Phim",
        "avatar": "👨‍💼",
        "preview_url": "/samples/local_thanh_binh.wav"
    },
    {
        "id": "local_ngoc_tran",
        "preset_name": "Ngọc Trân",
        "name": "Ngọc Trân (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Trung",
        "gender": "Female",
        "age": "young",
        "style": "story",
        "tag": "Local Voice • Miền Trung Nữ • Ngọt ngào",
        "avatar": "✨",
        "preview_url": "/samples/local_ngoc_tran.wav"
    },
    {
        "id": "local_quang_son",
        "preset_name": "Quang Sơn",
        "name": "Quang Sơn (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "Vietnamese",
        "region": "Miền Trung",
        "gender": "Male",
        "age": "young",
        "style": "story",
        "tag": "Local Voice • Miền Trung Nam • Tự nhiên",
        "avatar": "🎙️",
        "preview_url": "/samples/local_quang_son.wav"
    },
    {
        "id": "local_adam",
        "preset_name": "Adam",
        "name": "Adam (Local Voice)",
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": "English",
        "region": "US English",
        "gender": "Male",
        "age": "young",
        "style": "news",
        "tag": "Local Voice • English Male • Natural 48kHz",
        "avatar": "🌎",
        "preview_url": "/samples/local_adam.wav"
    }
]

def _get_vieneu_onnx_dir():
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    app_data = os.environ.get('APPDATA', '')
    candidates = [
        os.path.join(ROOT_DIR, "models", "vieneu", "onnx_int8"),
        os.path.join(ROOT_DIR, "models", "vieneu"),
        os.path.join(os.path.dirname(sys.executable), "models", "vieneu", "onnx_int8"),
        os.path.join(os.path.dirname(sys.executable), "models", "vieneu"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "models", "vieneu", "onnx_int8") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(local_app_data, "Programs", "NovaCut", "models", "vieneu", "onnx_int8") if local_app_data else None,
        os.path.join(local_app_data, "Programs", "NovaCut", "models", "vieneu") if local_app_data else None,
        os.path.join(app_data, "NovaCut", "models", "vieneu", "onnx_int8") if app_data else None,
        os.path.join(os.getcwd(), "models", "vieneu", "onnx_int8"),
    ]
    chosen_dir = None
    for c in candidates:
        if c and os.path.exists(c):
            if os.path.exists(os.path.join(c, "vieneu_v3_heads.npz")):
                chosen_dir = c
                break
            sub = os.path.join(c, "onnx_int8")
            if os.path.exists(os.path.join(sub, "vieneu_v3_heads.npz")):
                chosen_dir = sub
                break

    if chosen_dir:
        # Tự động đồng bộ speaker_encoder.onnx, denoiser.onnx, tokenizer.json, config.json vào thư mục onnx_int8 nếu thiếu
        parent_dir = os.path.dirname(chosen_dir)
        for fn in ["speaker_encoder.onnx", "denoiser.onnx", "tokenizer.json", "config.json"]:
            target_file = os.path.join(chosen_dir, fn)
            parent_file = os.path.join(parent_dir, fn)
            root_file = os.path.join(ROOT_DIR, "models", "vieneu", fn)
            if not os.path.exists(target_file):
                src = parent_file if os.path.exists(parent_file) else (root_file if os.path.exists(root_file) else None)
                if src:
                    try:
                        shutil.copy2(src, target_file)
                        print(f"[Local Voice] Auto-synced {fn} into {chosen_dir}")
                    except Exception as err:
                        print(f"[Local Voice] Warning copying {fn}: {err}")
            # Đảm bảo cả parent_dir cũng có file để checkpoint_path phân giải đúng
            if not os.path.exists(parent_file) and os.path.exists(target_file):
                try:
                    shutil.copy2(target_file, parent_file)
                except Exception:
                    pass
    return chosen_dir

def _get_vieneu_codec_dir():
    """
    Tìm hoặc đồng bộ thư mục chứa MOSS Audio Tokenizer Codec ONNX (decode_full, encode, step, etc.).
    """
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    app_data = os.environ.get('APPDATA', '')
    candidates = [
        os.path.join(ROOT_DIR, "models", "vieneu", "codec"),
        os.path.join(os.path.dirname(sys.executable), "models", "vieneu", "codec"),
        os.path.join(ROOT_DIR, "models", "codec"),
        os.path.join(local_app_data, "Programs", "NovaCut", "models", "vieneu", "codec") if local_app_data else None,
        os.path.join(app_data, "NovaCut", "models", "vieneu", "codec") if app_data else None,
        os.path.join(getattr(sys, '_MEIPASS', ''), "models", "vieneu", "codec") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(ROOT_DIR, "models", "vieneu"),
    ]
    
    required_codec_files = [
        "moss_audio_tokenizer_decode_full.onnx",
        "moss_audio_tokenizer_decode_shared.data",
        "moss_audio_tokenizer_decode_step.onnx",
        "moss_audio_tokenizer_encode.onnx",
        "moss_audio_tokenizer_encode.data",
        "codec_browser_onnx_meta.json"
    ]
    
    for c in candidates:
        if c and os.path.exists(c):
            if any(os.path.exists(os.path.join(c, f)) for f in required_codec_files[:2]):
                return c
                
    # Nếu chưa có, thử tìm trong HuggingFace Cache để tự động đồng bộ sang models/vieneu/codec
    target_codec_dir = os.path.join(ROOT_DIR, "models", "vieneu", "codec")
    os.makedirs(target_codec_dir, exist_ok=True)
    
    try:
        hf_cache_pattern = os.path.expanduser("~/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX/snapshots/*")
        import glob
        snapshots = glob.glob(hf_cache_pattern)
        if snapshots:
            snap_dir = snapshots[0]
            for fn in required_codec_files:
                src_f = os.path.join(snap_dir, fn)
                dst_f = os.path.join(target_codec_dir, fn)
                if os.path.exists(src_f) and not os.path.exists(dst_f):
                    try:
                        shutil.copy2(src_f, dst_f)
                    except Exception:
                        pass
            if any(os.path.exists(os.path.join(target_codec_dir, f)) for f in required_codec_files[:2]):
                print(f"[Local Voice] Auto-synced MOSS Codec models into {target_codec_dir}")
                return target_codec_dir
    except Exception as e:
        print(f"[Local Voice] HF Cache lookup note: {e}")

    # Fallback cuối: Nếu vẫn thiếu, tải trực tiếp qua huggingface_hub vào target_codec_dir
    try:
        from huggingface_hub import hf_hub_download
        print("[Local Voice] ⏳ Đang tải bổ sung Codec nén âm thanh MOSS (offline package)...")
        for fn in required_codec_files:
            dst_f = os.path.join(target_codec_dir, fn)
            if not os.path.exists(dst_f):
                try:
                    f_path = hf_hub_download("OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX", fn)
                    shutil.copy2(f_path, dst_f)
                except Exception as dl_err:
                    print(f"[Local Voice] Note fetching {fn}: {dl_err}")
        return target_codec_dir
    except Exception as err:
        print(f"[Local Voice] Warning loading codec dir: {err}")
        
    return target_codec_dir if os.path.exists(target_codec_dir) else None

def _ensure_sea_g2p_assets():
    """
    Đảm bảo tệp từ điển nhị phân `sea_g2p.bin` (62.8 MB) luôn tồn tại hợp lệ trong gói `sea_g2p`.
    Tự động phục hồi / đồng bộ từ `models/vieneu/sea_g2p.bin`, `models/sea_g2p.bin` hoặc AppData/dist
    để giải quyết triệt để lỗi Rust `The system cannot find the file specified. (os error 2)` trên máy khách.
    """
    try:
        import sea_g2p
        pkg_dir = os.path.dirname(sea_g2p.__file__)
        target_bin = os.path.join(pkg_dir, "sea_g2p.bin")
        
        # Nếu đã có file > 10MB thì coi như hợp lệ
        if os.path.exists(target_bin) and os.path.getsize(target_bin) > 10 * 1024 * 1024:
            # Đồng bộ ngược lại models/vieneu/sea_g2p.bin nếu thư mục models thiếu
            root_model_bin = os.path.join(ROOT_DIR, "models", "vieneu", "sea_g2p.bin")
            if not os.path.exists(root_model_bin):
                try:
                    os.makedirs(os.path.dirname(root_model_bin), exist_ok=True)
                    shutil.copy2(target_bin, root_model_bin)
                except Exception:
                    pass
            return True
            
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        app_data = os.environ.get('APPDATA', '')
        
        candidates = [
            os.path.join(ROOT_DIR, "models", "vieneu", "sea_g2p.bin"),
            os.path.join(ROOT_DIR, "models", "sea_g2p.bin"),
            os.path.join(os.path.dirname(sys.executable), "models", "vieneu", "sea_g2p.bin"),
            os.path.join(os.path.dirname(sys.executable), "models", "sea_g2p.bin"),
            os.path.join(local_app_data, "Programs", "NovaCut", "models", "vieneu", "sea_g2p.bin") if local_app_data else None,
            os.path.join(app_data, "NovaCut", "models", "vieneu", "sea_g2p.bin") if app_data else None,
            os.path.join(getattr(sys, '_MEIPASS', ''), "models", "vieneu", "sea_g2p.bin") if hasattr(sys, '_MEIPASS') else None,
            os.path.join(getattr(sys, '_MEIPASS', ''), "sea_g2p", "sea_g2p.bin") if hasattr(sys, '_MEIPASS') else None,
            os.path.join(os.path.dirname(sys.executable), "_internal", "sea_g2p", "sea_g2p.bin"),
        ]
        
        found_src = None
        for c in candidates:
            if c and os.path.exists(c) and os.path.getsize(c) > 10 * 1024 * 1024:
                found_src = c
                break
                
        if found_src:
            try:
                os.makedirs(pkg_dir, exist_ok=True)
                shutil.copy2(found_src, target_bin)
                print(f"[Local Voice] Successfully auto-synced sea_g2p.bin ({os.path.getsize(target_bin):,} bytes) from {found_src} into {pkg_dir}")
                return True
            except Exception as copy_err:
                print(f"[Local Voice] Warning copying sea_g2p.bin: {copy_err}")
                
        # Nếu chưa tìm thấy ở bất kỳ đâu, thử tải tự động từ Hugging Face
        try:
            from huggingface_hub import hf_hub_download
            print("[Local Voice] ⏳ Đang tải bổ sung tệp từ điển phiên âm sea_g2p.bin (offline package)...")
            dl_path = hf_hub_download("pnnbao-ump/VieNeu-TTS-v3-Turbo", "sea_g2p.bin", repo_type="model")
            if dl_path and os.path.exists(dl_path):
                shutil.copy2(dl_path, target_bin)
                root_model_bin = os.path.join(ROOT_DIR, "models", "vieneu", "sea_g2p.bin")
                os.makedirs(os.path.dirname(root_model_bin), exist_ok=True)
                shutil.copy2(dl_path, root_model_bin)
                return True
        except Exception as dl_err:
            print(f"[Local Voice] Note HF download sea_g2p.bin: {dl_err}")
            
    except Exception as err:
        print(f"[Local Voice] _ensure_sea_g2p_assets note: {err}")
    return False

# ── Tối ưu hóa hiệu năng đỉnh cao cho Local Voice Engine ──────────────────────
import queue
from functools import lru_cache

try:
    import vieneu_utils.phonemize_text as _p_mod
    if not hasattr(_p_mod, '_orig_phonemize_fn'):
        _p_mod._orig_phonemize_fn = _p_mod.phonemize_text_with_emotions
        @lru_cache(maxsize=20000)
        def _cached_phonemize_text(text):
            return _p_mod._orig_phonemize_fn(text)
        _p_mod.phonemize_text_with_emotions = _cached_phonemize_text
except Exception as _p_err:
    print(f"[Local Voice] Phoneme cache note: {_p_err}")

_ENGINE_INSTANCE = None
_ENGINE_LOCK = threading.Lock()

_ENGINE_POOL = None
_ENGINE_POOL_LOCK = threading.Lock()
_POOL_SIZE = 2  # 2 ONNX sessions song song tận dụng tối đa CPU đa lõi mà không ngốn RAM

def _create_single_engine(threads=4):
    _ensure_sea_g2p_assets()
    from vieneu import Vieneu
    local_onnx_dir = _get_vieneu_onnx_dir()
    local_codec_dir = _get_vieneu_codec_dir()
    
    if not local_onnx_dir or not os.path.exists(local_onnx_dir):
        raise FileNotFoundError(f"Không tìm thấy thư mục mô hình ONNX tại {ROOT_DIR}/models/vieneu/onnx_int8!")

    model_root = os.path.dirname(local_onnx_dir) if (local_onnx_dir and os.path.basename(local_onnx_dir) == 'onnx_int8') else local_onnx_dir

    for req_f in ["tokenizer.json", "config.json", "speaker_encoder.onnx", "denoiser.onnx"]:
        tgt = os.path.join(local_onnx_dir, req_f)
        if not os.path.exists(tgt):
            alt = os.path.join(model_root, req_f)
            if os.path.exists(alt):
                shutil.copy2(alt, tgt)
                
    for spk_f in ["speaker_encoder.onnx", "denoiser.onnx"]:
        root_spk = os.path.join(model_root, spk_f)
        sub_spk = os.path.join(local_onnx_dir, spk_f)
        if not os.path.exists(root_spk) and os.path.exists(sub_spk):
            shutil.copy2(sub_spk, root_spk)
        elif not os.path.exists(sub_spk) and os.path.exists(root_spk):
            shutil.copy2(root_spk, sub_spk)

    kwargs = {
        "backend": "onnx",
        "onnx_dir": local_onnx_dir,
        "backbone_repo": model_root,
        "threads": threads
    }
    if local_codec_dir:
        kwargs["codec_dir"] = local_codec_dir

    return Vieneu(**kwargs)

def get_engine():
    """
    Singleton Loader for Local Voice Engine (VieNeu v3 Turbo ONNX Lite).
    Tải mô hình 100% Offline từ thư mục models/vieneu/ và models/vieneu/codec/.
    """
    global _ENGINE_INSTANCE
    if _ENGINE_INSTANCE is None:
        with _ENGINE_LOCK:
            if _ENGINE_INSTANCE is None:
                try:
                    print("[Local Voice] Initializing High-Speed Local Voice Engine (ONNX 48kHz)...")
                    _ENGINE_INSTANCE = _create_single_engine(threads=min(max((os.cpu_count() or 8) // 2, 2), 6))
                    print("[Local Voice] Engine loaded successfully (100% Offline Ready)!")
                except Exception as e:
                    _ENGINE_INSTANCE = None
                    print(f"[Local Voice] Failed to load engine: {e}")
                    raise e
    return _ENGINE_INSTANCE

def get_engine_pool():
    """
    Quản lý hàng đợi Multi-Engine Pool cho phép xử lý suy luận song song đồng thời.
    """
    global _ENGINE_POOL
    if _ENGINE_POOL is None:
        with _ENGINE_POOL_LOCK:
            if _ENGINE_POOL is None:
                q = queue.Queue()
                # Thêm instance chính đã có
                primary = get_engine()
                q.put(primary)
                # Khởi tạo instance thứ 2 để chạy song song
                try:
                    secondary = _create_single_engine(threads=4)
                    q.put(secondary)
                    print("[Local Voice] Multi-Engine Session Pool (2x Workers) initialized for parallel throughput!")
                except Exception as pool_err:
                    print(f"[Local Voice] Session pool secondary instance note: {pool_err}")
                _ENGINE_POOL = q
    return _ENGINE_POOL

def _get_ffmpeg_exe():
    try:
        import ffmpeg_installer
        cand = ffmpeg_installer.get_ffmpeg_path()
        if cand and os.path.exists(cand):
            return cand
    except Exception:
        pass
    bin_candidates = [
        os.path.join(os.path.dirname(sys.executable), 'bin', 'ffmpeg.exe'),
        os.path.join(getattr(sys, '_MEIPASS', ''), 'bin', 'ffmpeg.exe') if hasattr(sys, '_MEIPASS') else None,
        os.path.join(ROOT_DIR, 'bin', 'ffmpeg.exe')
    ]
    for b in bin_candidates:
        if b and os.path.exists(b):
            return b
    return shutil.which('ffmpeg.exe') or shutil.which('ffmpeg') or 'ffmpeg'

def validate_and_convert_audio_sample(input_audio_path, output_wav_path=None, return_meta=False, max_duration=10.0):
    """
    Kiểm tra và chuẩn hóa file âm thanh mẫu (thời lượng >= 1.0s, chuyển về 24kHz Mono WAV).
    Nếu file vượt quá max_duration (hoặc chứa khoảng lặng dài / timestamp lệch),
    hệ thống sẽ tự động tối ưu và cắt gọn (auto-trim) lấy đoạn âm thanh vàng 5-8s thay vì báo lỗi chặn người dùng.
    """
    if not os.path.exists(input_audio_path):
        return False, "Tệp âm thanh mẫu không tồn tại."
        
    if output_wav_path is None:
        base_dir = os.path.dirname(os.path.abspath(input_audio_path))
        output_wav_path = os.path.join(base_dir, f"clean_{int(time.time()*1000)}.wav")
        
    ffmpeg_exe = _get_ffmpeg_exe()

    # 1. Chuyển đổi an toàn qua ffmpeg với đồng bộ PTS và resample 24kHz mono
    try:
        cmd = [
            ffmpeg_exe, "-y",
            "-avoid_negative_ts", "make_zero",
            "-i", input_audio_path,
            "-vn", "-sn", "-dn",
            "-af", "aresample=async=1,asetpts=PTS-STARTPTS",
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
            output_wav_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=0x08000000 if os.name == 'nt' else 0)
        
        # Nếu ffmpeg không sinh được file > 100 bytes, thử đọc qua soundfile/librosa
        if not os.path.exists(output_wav_path) or os.path.getsize(output_wav_path) < 100:
            import soundfile as sf
            data, samplerate = sf.read(input_audio_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1) # Mono
            # Resample to 24000 if needed
            if samplerate != 24000:
                try:
                    import scipy.signal
                    num_samples = int(len(data) * 24000 / samplerate)
                    data = scipy.signal.resample(data, num_samples)
                except Exception:
                    pass
            sf.write(output_wav_path, data, 24000, subtype='PCM_16')

        with wave.open(output_wav_path, 'r') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            
        if duration < 1.0:
            return False, f"Đoạn âm thanh mẫu quá ngắn ({duration:.1f}s). Vui lòng chọn hoặc thu âm mẫu từ 2-10 giây."
            
        is_trimmed = False
        original_duration = duration

        # 2. Tự động tối ưu và cắt gọn (Auto-trim) nếu file dài hơn max_duration (tránh lỗi file quá dài)
        if duration > max_duration:
            target_trim_sec = 8.0 # Đoạn mẫu lý tưởng cho mô hình clone voice
            trimmed_wav_path = output_wav_path + f".trim_{int(time.time()*1000)}.wav"
            
            # Thử cắt bỏ silence ở đầu rồi lấy 8 giây
            trim_cmd = [
                ffmpeg_exe, "-y", "-i", output_wav_path,
                "-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-35dB",
                "-t", str(target_trim_sec),
                "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                trimmed_wav_path
            ]
            subprocess.run(trim_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=0x08000000 if os.name == 'nt' else 0)
            
            valid_trim = False
            if os.path.exists(trimmed_wav_path) and os.path.getsize(trimmed_wav_path) > 100:
                try:
                    with wave.open(trimmed_wav_path, 'r') as twf:
                        t_dur = twf.getnframes() / float(twf.getframerate())
                        if t_dur >= 2.0:
                            valid_trim = True
                except Exception:
                    valid_trim = False
                    
            if not valid_trim:
                # Fallback cắt trực tiếp target_trim_sec giây từ đầu file
                fallback_trim_cmd = [
                    ffmpeg_exe, "-y", "-i", output_wav_path,
                    "-t", str(target_trim_sec),
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                    trimmed_wav_path
                ]
                subprocess.run(fallback_trim_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=0x08000000 if os.name == 'nt' else 0)
                
            if os.path.exists(trimmed_wav_path) and os.path.getsize(trimmed_wav_path) > 100:
                try:
                    if os.path.exists(output_wav_path):
                        os.remove(output_wav_path)
                    os.replace(trimmed_wav_path, output_wav_path)
                except Exception:
                    shutil.copy2(trimmed_wav_path, output_wav_path)
                    try: os.remove(trimmed_wav_path)
                    except: pass
                    
                is_trimmed = True
                try:
                    with wave.open(output_wav_path, 'r') as wf:
                        duration = wf.getnframes() / float(wf.getframerate())
                except Exception:
                    duration = target_trim_sec

        if return_meta:
            return True, {
                'path': output_wav_path,
                'duration': round(duration, 2),
                'original_duration': round(original_duration, 2),
                'is_trimmed': is_trimmed
            }

        return True, output_wav_path
    except Exception as e:
        return False, f"Lỗi xử lý file âm thanh mẫu: {str(e)}"

def select_preset_for_voice(voice_id=None, gender=None, lang=None) -> str:
    """
    Chọn preset cục bộ bảo toàn 100% giới tính và ngôn ngữ:
    Nam Việt -> Minh Đức
    Nữ Việt -> Ngọc Huyền
    Nam Anh -> Adam
    Nữ Anh -> Không hỗ trợ (ném lỗi)
    """
    profile = {}
    if voice_id:
        try:
            import custom_voices
            profile = custom_voices.resolve_voice_profile(voice_id)
        except Exception:
            pass

    # Direct name aliases
    v_id_low = str(voice_id or '').lower()
    if any(w in v_id_low for w in ['adam', 'kokoro_am_adam', 'en_adam', 'local_adam']):
        return "Adam"

    g = (gender or profile.get('gender') or '').strip().lower()
    l = (lang or profile.get('lang') or '').strip().lower()

    if not g:
        g = 'male' if any(w in v_id_low for w in ['nam', 'duc', 'dung', 'dat', 'binh', 'son', 'khoa', 'quang', 'male', 'adam']) else 'female'
    if not l:
        l = 'en' if any(w in v_id_low for w in ['en', 'english', 'us', 'adam']) else 'vi'

    is_male = (g == 'male')
    is_en = ('en' in l)

    if voice_id:
        for p in LOCAL_VOICE_PRESETS:
            if p["id"] == voice_id:
                return p.get("preset_name")

    if is_en:
        if is_male:
            return "Adam"
        raise ValueError(f"Local Voice ONNX không có preset nữ Tiếng Anh cho '{voice_id}'")
    return "Minh Đức" if is_male else "Ngọc Huyền"

def synthesize(text, voice_id=None, ref_audio=None, speed=1.0, output_path=None, target_sample_rate=None, target_channels=None):
    """
    Sinh giọng nói từ văn bản bằng Local Voice Engine (hỗ trợ cả preset, cloned voice và audio mẫu trực tiếp).
    Tối ưu hóa: Sử dụng Engine Pool để hỗ trợ đa luồng thật sự + In-memory Resampling không cần gọi ffmpeg.
    """
    if not text or not str(text).strip():
        raise ValueError("Văn bản đọc không được để trống")

    if not output_path:
        output_path = os.path.join(ROOT_DIR, "output", f"local_voice_{int(time.time()*1000)}.wav")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 1. Xác định Voice Preset hoặc Ref Audio
    target_preset = None
    target_ref_audio = ref_audio

    import custom_voices
    resolved_profile = custom_voices.resolve_voice_profile(voice_id) if voice_id else {
        "gender": "Female", "lang": "Vietnamese"
    }
    is_male = (resolved_profile.get("gender", "").lower() == "male")
    is_en = "en" in resolved_profile.get("lang", "").lower()

    # Tìm trong Preset
    if voice_id:
        for p in LOCAL_VOICE_PRESETS:
            if p["id"] == voice_id:
                target_preset = p.get("preset_name")
                break
                
        # Nếu là cloned voice trong custom_voices.json
        if not target_preset and not target_ref_audio:
            target_ref_audio = resolved_profile.get("reference_audio")
            if target_ref_audio and not os.path.isabs(target_ref_audio):
                target_ref_audio = os.path.join(ROOT_DIR, target_ref_audio)

    # Nếu không có ref_audio và chưa có target_preset, bảo toàn giới tính & ngôn ngữ tuyệt đối
    if not target_preset and not (target_ref_audio and os.path.exists(target_ref_audio)):
        target_preset = select_preset_for_voice(voice_id, gender=resolved_profile.get("gender"), lang=resolved_profile.get("lang"))

    # 2. Xử lý chuẩn hóa text
    try:
        import vietnamese_text_normalizer
        norm_text = vietnamese_text_normalizer.normalize_text_for_tts(text)
    except Exception:
        norm_text = text

    # 3. Ưu tiên GPU Worker qua IPC nếu có sẵn (Tốc độ ~20x, resident model)
    try:
        import local_voice_worker_client
        client = local_voice_worker_client.get_voice_worker_client()
        if client.is_runtime_available():
            dst_sr = int(target_sample_rate) if target_sample_rate else 48000
            dst_ch = int(target_channels) if target_channels else 1
            default_vid = "local_adam" if (is_en and is_male) else ("local_minh_duc" if is_male else "local_ngoc_huyen")
            target_vid = "local_adam" if (is_en and is_male) else (voice_id or default_vid)
            batch_res = client.synthesize_batch(
                items=[{"id": 0, "text": norm_text, "output_path": output_path}],
                voice_id=target_vid,
                speed=float(speed),
                batch_size=4,
                target_sample_rate=dst_sr,
                target_channels=dst_ch,
                ref_audio=target_ref_audio
            )
            if batch_res and batch_res[0].get("success") and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return output_path
    except Exception as gpu_err:
        print(f"[Local Voice] GPU worker fallback to CPU engine pool: {gpu_err}")

    # 4. Lấy engine từ Pool để chạy CPU ONNX dự phòng
    pool = get_engine_pool()
    tts = pool.get()
    try:
        if target_ref_audio and os.path.exists(target_ref_audio):
            audio_data = tts.infer(text=norm_text, ref_audio=target_ref_audio, apply_watermark=False)
        elif target_preset:
            audio_data = tts.infer(text=norm_text, voice=target_preset, apply_watermark=False)
        else:
            fallback_preset = "Adam" if (is_en and is_male) else ("Minh Đức" if is_male else "Ngọc Huyền")
            audio_data = tts.infer(text=norm_text, voice=fallback_preset, apply_watermark=False)
    finally:
        pool.put(tts)

    # 5. Xuất âm thanh & Resample trực tiếp trên bộ nhớ (In-memory, Zero FFmpeg overhead)
    orig_sr = getattr(tts, 'sample_rate', 48000)
    audio_arr = np.asarray(audio_data, dtype=np.float32)

    # Nếu cần resample hoặc chỉnh tốc độ bằng in-memory
    dst_sr = int(target_sample_rate) if target_sample_rate else orig_sr
    dst_ch = int(target_channels) if target_channels else 1
    needs_in_memory_resample = (target_sample_rate is not None and dst_sr != orig_sr) or (target_channels is not None and dst_ch != 1) or (abs(speed - 1.0) > 0.03)

    if needs_in_memory_resample:
        try:
            import scipy.signal
            import soundfile as sf
            
            proc_audio = audio_arr
            # Chỉnh tốc độ (speed) nếu khác 1.0
            if abs(speed - 1.0) > 0.03:
                speed_val = max(0.5, min(2.5, float(speed)))
                target_len = int(round(len(proc_audio) / speed_val))
                proc_audio = scipy.signal.resample(proc_audio, target_len)

            # Resample tần số mẫu nếu khác orig_sr
            if dst_sr != orig_sr:
                new_num_samples = int(round(len(proc_audio) * dst_sr / orig_sr))
                proc_audio = scipy.signal.resample(proc_audio, new_num_samples)

            # Chuyển kênh mono -> stereo nếu yêu cầu 2 channels
            if dst_ch == 2 and len(proc_audio.shape) == 1:
                final_pcm = np.column_stack((proc_audio, proc_audio))
            else:
                final_pcm = proc_audio

            # Chuyển float32 sang int16 chuẩn CD PCM 16-bit
            pcm_int16 = np.clip(final_pcm * 32767.0, -32768, 32767).astype(np.int16)
            sf.write(output_path, pcm_int16, dst_sr, subtype='PCM_16')
            return output_path
        except Exception as resample_err:
            print(f"[Local Voice] In-memory resample note ({resample_err}), falling back to standard write...")

    # Fallback ghi chuẩn qua tts.save
    temp_out = output_path if abs(speed - 1.0) < 0.05 else os.path.join(os.path.dirname(output_path), f"temp_speed_{int(time.time()*1000)}.wav")
    tts.save(audio_data, temp_out)

    if temp_out != output_path and os.path.exists(temp_out):
        ffmpeg_exe = _get_ffmpeg_exe()
        try:
            speed_val = max(0.5, min(2.5, float(speed)))
            atempo_filters = []
            cur_s = speed_val
            while cur_s > 2.0:
                atempo_filters.append("atempo=2.0")
                cur_s /= 2.0
            while cur_s < 0.5:
                atempo_filters.append("atempo=0.5")
                cur_s /= 0.5
            atempo_filters.append(f"atempo={cur_s:.4f}")
            filter_str = ",".join(atempo_filters)

            cmd = [ffmpeg_exe, "-y", "-i", temp_out, "-filter:a", filter_str, output_path]
            subprocess.run(cmd, capture_output=True, check=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        finally:
            if os.path.exists(temp_out):
                try: os.remove(temp_out)
                except Exception: pass

    return output_path

def clone_voice(audio_file_path, name, gender="Female", region="Miền Bắc", style="review", lang="Vietnamese", age="young", tag=None, avatar=None):
    """
    Nhân bản một giọng nói mới từ file âm thanh mẫu và lưu cố định vào thư viện.
    """
    v_id = f"local_clone_{int(time.time()*1000)}"
    clean_sample_path = os.path.join(CLONES_DIR, f"{v_id}.wav")
    
    # 1. Kiểm tra và chuẩn hóa file mẫu
    ok, res = validate_and_convert_audio_sample(audio_file_path, clean_sample_path)
    if not ok:
        raise ValueError(res)

    # 2. Tạo Preview mẫu thử âm thanh
    preview_sample_path = os.path.join(SAMPLES_DIR, f"{v_id}.wav")
    sample_text = f"Xin chào! Đây là giọng đọc {name}, được nhân bản chuẩn phòng thu bằng Local Voice."
    synthesize(text=sample_text, ref_audio=clean_sample_path, speed=1.0, output_path=preview_sample_path)

    # 3. Tạo Profile lưu vào custom_voices.json
    final_name = name if name.endswith("(Local Voice)") else f"{name} (Local Voice)"
    if not avatar:
        avatar = "👨" if gender == "Male" else "👩"

    voice_profile = {
        "id": v_id,
        "name": final_name,
        "provider": "local_voice",
        "provider_name": "Local Voice",
        "lang": lang or "Vietnamese",
        "region": region or "Miền Bắc",
        "gender": gender or "Female",
        "age": age or "young",
        "style": style or "review",
        "tag": tag or f"Local Voice • {region} • {gender}",
        "avatar": avatar,
        "reference_audio": os.path.relpath(clean_sample_path, ROOT_DIR).replace("\\", "/"),
        "preview_url": f"/samples/{v_id}.wav",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    import custom_voices
    custom_voices.add_or_update_voice(voice_profile)
    return voice_profile


def get_versioned_audio_cache_key(text, voice_id, speed=1.0, target_sample_rate=48000, target_channels=1, version="v3"):
    import hashlib
    raw = f"{text.strip()}|{voice_id}|{float(speed):.2f}|{int(target_sample_rate)}|{int(target_channels)}|{version}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def synthesize_batch(items, voice_id=None, ref_audio=None, speed=1.0, target_sample_rate=None, target_channels=None, batch_size=16, cancel_token=None):
    """
    Sinh giọng hàng loạt (Batch Synthesis) tối ưu cho GPU RTX 5060 qua tiến trình Worker độc lập.
    Hỗ trợ cả voice presets và custom cloned voices. Fallback an toàn về CPU nếu GPU không khả dụng.
    """
    if not items:
        return []

    # 1. Chuẩn hóa voice_id và ref_audio
    target_ref = ref_audio
    if voice_id and not target_ref:
        for p in LOCAL_VOICE_PRESETS:
            if p["id"] == voice_id:
                break
        else:
            import custom_voices
            prof = custom_voices.get_voice_by_id(voice_id)
            if prof and prof.get("reference_audio"):
                target_ref = prof.get("reference_audio")
                if not os.path.isabs(target_ref):
                    target_ref = os.path.join(ROOT_DIR, target_ref)

    # 2. Chuẩn hóa text cho tất cả items
    import vietnamese_text_normalizer
    normalized_items = []
    for it in items:
        raw_t = it.get("text", "")
        try:
            norm_t = vietnamese_text_normalizer.normalize_text_for_tts(raw_t)
        except Exception:
            norm_t = raw_t
        normalized_items.append({
            "id": it.get("id"),
            "text": norm_t,
            "output_path": it.get("output_path")
        })

    # 3. Ưu tiên GPU Worker qua IPC
    try:
        import local_voice_worker_client
        client = local_voice_worker_client.get_voice_worker_client()
        if client.is_runtime_available():
            dst_sr = int(target_sample_rate) if target_sample_rate else 48000
            dst_ch = int(target_channels) if target_channels else 1
            return client.synthesize_batch(
                items=normalized_items,
                voice_id=voice_id or "local_ngoc_huyen",
                speed=float(speed),
                batch_size=int(batch_size),
                target_sample_rate=dst_sr,
                target_channels=dst_ch,
                ref_audio=target_ref,
                cancel_token=cancel_token
            )
    except Exception as gpu_batch_err:
        print(f"[Local Voice] GPU batch failed ({gpu_batch_err}), falling back to parallel CPU pool...")

    # 4. Fallback CPU Engine Pool
    from concurrent.futures import ThreadPoolExecutor
    def _cpu_worker(it):
        if cancel_token and cancel_token():
            return {"id": it["id"], "error": "Cancelled", "success": False}
        try:
            out_p = synthesize(
                text=it["text"],
                voice_id=voice_id,
                ref_audio=target_ref,
                speed=speed,
                output_path=it["output_path"],
                target_sample_rate=target_sample_rate,
                target_channels=target_channels
            )
            return {"id": it["id"], "path": out_p, "success": True, "error": None}
        except Exception as ex:
            return {"id": it["id"], "error": str(ex), "success": False}

    with ThreadPoolExecutor(max_workers=2) as ex:
        return list(ex.map(_cpu_worker, normalized_items))

