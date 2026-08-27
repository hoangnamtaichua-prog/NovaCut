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

_ENGINE_INSTANCE = None
_ENGINE_LOCK = threading.Lock()

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
                    _ensure_sea_g2p_assets()
                    from vieneu import Vieneu
                    print("[Local Voice] Initializing High-Speed Local Voice Engine (ONNX 48kHz)...")
                    local_onnx_dir = _get_vieneu_onnx_dir()
                    local_codec_dir = _get_vieneu_codec_dir()
                    
                    if not local_onnx_dir or not os.path.exists(local_onnx_dir):
                        raise FileNotFoundError(f"Không tìm thấy thư mục mô hình ONNX tại {ROOT_DIR}/models/vieneu/onnx_int8!")

                    model_root = os.path.dirname(local_onnx_dir) if (local_onnx_dir and os.path.basename(local_onnx_dir) == 'onnx_int8') else local_onnx_dir

                    # Kiểm tra và đảm bảo các file ONNX & Tokenizer tồn tại đầy đủ
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

                    print(f"[Local Voice] - ONNX Backbone: {local_onnx_dir}")
                    print(f"[Local Voice] - Codec Dir: {local_codec_dir}")
                    print(f"[Local Voice] - Model Root: {model_root}")

                    kwargs = {
                        "backend": "onnx",
                        "onnx_dir": local_onnx_dir,
                        "backbone_repo": model_root,
                    }
                    if local_codec_dir:
                        kwargs["codec_dir"] = local_codec_dir

                    _ENGINE_INSTANCE = Vieneu(**kwargs)
                    print("[Local Voice] Engine loaded successfully (100% Offline Ready)!")
                except Exception as e:
                    _ENGINE_INSTANCE = None
                    print(f"[Local Voice] Failed to load engine: {e}")
                    raise e
    return _ENGINE_INSTANCE

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

def validate_and_convert_audio_sample(input_audio_path, output_wav_path=None):
    """
    Kiểm tra và chuẩn hóa file âm thanh mẫu (thời lượng 1s-60s, chuyển về 24kHz Mono WAV).
    """
    if not os.path.exists(input_audio_path):
        return False, "Tệp âm thanh mẫu không tồn tại."
        
    if output_wav_path is None:
        base_dir = os.path.dirname(os.path.abspath(input_audio_path))
        output_wav_path = os.path.join(base_dir, f"clean_{int(time.time()*1000)}.wav")
        
    ffmpeg_exe = _get_ffmpeg_exe()

    # 1. Chuyển đổi an toàn qua ffmpeg
    try:
        cmd = [
            ffmpeg_exe, "-y", "-i", input_audio_path,
            "-vn", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
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
            return False, f"Đoạn âm thanh mẫu quá ngắn ({duration:.1f}s). Vui lòng chọn hoặc thu âm mẫu từ 2-5 giây."
        if duration > 60.0:
            return False, f"Đoạn âm thanh mẫu quá dài ({duration:.1f}s). Vui lòng chọn mẫu dưới 30 giây (tốt nhất 3-6s)."
            
        return True, output_wav_path
    except Exception as e:
        return False, f"Lỗi xử lý file âm thanh mẫu: {str(e)}"

def synthesize(text, voice_id=None, ref_audio=None, speed=1.0, output_path=None):
    """
    Sinh giọng nói từ văn bản bằng Local Voice Engine (hỗ trợ cả preset, cloned voice và audio mẫu trực tiếp).
    """
    if not text or not str(text).strip():
        raise ValueError("Văn bản đọc không được để trống")

    if not output_path:
        output_path = os.path.join(ROOT_DIR, "output", f"local_voice_{int(time.time()*1000)}.wav")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    tts = get_engine()
    
    # 1. Xác định Voice Preset hoặc Ref Audio
    target_preset = None
    target_ref_audio = ref_audio

    # Tìm trong Preset
    if voice_id:
        for p in LOCAL_VOICE_PRESETS:
            if p["id"] == voice_id:
                target_preset = p.get("preset_name", "Ngọc Huyền")
                break
                
        # Nếu là cloned voice trong custom_voices.json
        if not target_preset and not target_ref_audio:
            import custom_voices
            voice_prof = custom_voices.get_voice_by_id(voice_id)
            if voice_prof:
                target_ref_audio = voice_prof.get("reference_audio")
                if target_ref_audio and not os.path.isabs(target_ref_audio):
                    target_ref_audio = os.path.join(ROOT_DIR, target_ref_audio)

    # 2. Xử lý chuẩn hóa text
    try:
        import vietnamese_text_normalizer
        norm_text = vietnamese_text_normalizer.normalize_text_for_tts(text)
    except Exception:
        norm_text = text

    # 3. Chạy Inference
    with _ENGINE_LOCK:
        if target_ref_audio and os.path.exists(target_ref_audio):
            audio_data = tts.infer(text=norm_text, ref_audio=target_ref_audio, apply_watermark=False)
        elif target_preset:
            audio_data = tts.infer(text=norm_text, voice=target_preset, apply_watermark=False)
        else:
            audio_data = tts.infer(text=norm_text, voice="Ngọc Huyền", apply_watermark=False)

    temp_out = output_path if abs(speed - 1.0) < 0.05 else os.path.join(os.path.dirname(output_path), f"temp_speed_{int(time.time()*1000)}.wav")
    tts.save(audio_data, temp_out)

    # 4. Điều chỉnh tốc độ (Speed Adjustment) nếu khác 1.0
    if temp_out != output_path and os.path.exists(temp_out):
        ffmpeg_exe = _get_ffmpeg_exe()
        try:
            # Build atempo filter chain
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
