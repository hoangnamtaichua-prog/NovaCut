import os
import sys
import time
import json
import wave
import shutil
import threading
import subprocess
import numpy as np

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    candidates = [
        os.path.join(ROOT_DIR, "models", "vieneu", "onnx_int8"),
        os.path.join(os.path.dirname(sys.executable), "models", "vieneu", "onnx_int8"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "models", "vieneu", "onnx_int8") if hasattr(sys, '_MEIPASS') else None,
        os.path.join(ROOT_DIR, "models", "vieneu"),
        os.path.join(os.path.dirname(sys.executable), "models", "vieneu"),
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
        # Tự động đồng bộ speaker_encoder.onnx & denoiser.onnx vào thư mục onnx_int8 nếu thiếu
        parent_dir = os.path.dirname(chosen_dir)
        for fn in ["speaker_encoder.onnx", "denoiser.onnx"]:
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
    return chosen_dir

_ENGINE_INSTANCE = None
_ENGINE_LOCK = threading.Lock()

def get_engine():
    """
    Singleton Loader for Local Voice Engine (VieNeu v3 Turbo ONNX Lite).
    """
    global _ENGINE_INSTANCE
    if _ENGINE_INSTANCE is None:
        with _ENGINE_LOCK:
            if _ENGINE_INSTANCE is None:
                try:
                    from vieneu import Vieneu
                    print("[Local Voice] Initializing High-Speed Local Voice Engine (ONNX 48kHz)...")
                    local_onnx_dir = _get_vieneu_onnx_dir()
                    if local_onnx_dir:
                        print(f"[Local Voice] Loading offline pre-bundled ONNX model from: {local_onnx_dir}")
                        _ENGINE_INSTANCE = Vieneu(backend="onnx", onnx_dir=local_onnx_dir)
                    else:
                        print("[Local Voice] Loading default ONNX model...")
                        _ENGINE_INSTANCE = Vieneu(backend="onnx", precision="int8")
                    print("[Local Voice] Engine loaded successfully!")
                except Exception as e:
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
