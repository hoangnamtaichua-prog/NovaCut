import os
import json

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VOICES_FILE = os.path.join(ROOT_DIR, "custom_voices.json")

DEFAULT_CUSTOM_VOICES = [
    {
        "id": "rvc_ngochuyen_reviewphim",
        "name": "Ngọc Huyền Review Phim (RVC)",
        "provider": "rvc",
        "provider_name": "RVC Clone",
        "lang": "Vietnamese",
        "region": "Hà Nội / Toàn quốc",
        "gender": "Female",
        "age": "young",
        "style": "review",
        "tag": "RVC Model • RTX 5060 GPU • Chuẩn giọng review",
        "avatar": "🎙️",
        "base_voice": "edge_vi-VN-HoaiMyNeural",
        "model_path": r"D:\Tool\RVC\RVC20260718Nvidia50x0\assets\weights\ngochuyen_reviewphim.pth",
        "index_path": r"D:\Tool\RVC\RVC20260718Nvidia50x0\logs\ngochuyen_reviewphim\added_IVF525_Flat_nprobe_1_ngochuyen_reviewphim_v2.index",
        "pitch": 0,
        "f0_method": "rmvpe",
        "index_rate": 0.75
    }
]

def load_custom_voices():
    if not os.path.exists(CUSTOM_VOICES_FILE):
        save_custom_voices(DEFAULT_CUSTOM_VOICES)
        voices = DEFAULT_CUSTOM_VOICES
    else:
        try:
            with open(CUSTOM_VOICES_FILE, "r", encoding="utf-8") as f:
                voices = json.load(f)
                if not isinstance(voices, list):
                    voices = DEFAULT_CUSTOM_VOICES
        except Exception as e:
            print("Error reading custom_voices.json:", e)
            voices = DEFAULT_CUSTOM_VOICES

    # Attach static preview_url if sample exists
    samples_dir = os.path.join(ROOT_DIR, "web", "samples")
    for v in voices:
        v_id = v.get("id")
        if v_id and not v.get("preview_url"):
            sample_f = os.path.join(samples_dir, f"{v_id}.wav")
            if os.path.exists(sample_f):
                v["preview_url"] = f"/samples/{v_id}.wav"
            elif os.path.exists(os.path.join(samples_dir, f"sample_{v_id}.wav")):
                v["preview_url"] = f"/samples/sample_{v_id}.wav"

    return voices

def save_custom_voices(voices):
    with open(CUSTOM_VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, ensure_ascii=False, indent=2)

def get_voice_by_id(voice_id):
    voices = load_custom_voices()
    for v in voices:
        if v.get("id") == voice_id:
            return v
    return None

def generate_sample_for_voice(voice_data):
    """Generates a 3-second sample wav in web/samples/ for instant preview."""
    try:
        import ai_dubbing
        v_id = voice_data.get("id")
        samples_dir = os.path.join(ROOT_DIR, "web", "samples")
        os.makedirs(samples_dir, exist_ok=True)
        out_sample = os.path.join(samples_dir, f"{v_id}.wav")
        sample_text = "Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu."
        ai_dubbing.synthesize_sentence(sample_text, v_id, 1.0, out_sample)
    except Exception as e:
        print(f"Error generating sample for {voice_data.get('id')}: {e}")

def add_or_update_voice(voice_data):
    voices = load_custom_voices()
    v_id = voice_data.get("id")
    if not v_id:
        import time
        v_id = f"rvc_{int(time.time())}"
        voice_data["id"] = v_id
    
    updated = False
    for idx, v in enumerate(voices):
        if v.get("id") == v_id:
            voices[idx] = {**v, **voice_data}
            updated = True
            break
    if not updated:
        voices.append(voice_data)
        
    save_custom_voices(voices)
    
    # Generate preview sample in background thread
    import threading
    threading.Thread(target=generate_sample_for_voice, args=(voice_data,), daemon=True).start()
    
    return voice_data

def delete_voice(voice_id):
    voices = load_custom_voices()
    new_voices = [v for v in voices if v.get("id") != voice_id]
    save_custom_voices(new_voices)
    # Remove cached sample file if exists
    try:
        sample_f = os.path.join(ROOT_DIR, "web", "samples", f"{voice_id}.wav")
        if os.path.exists(sample_f):
            os.remove(sample_f)
    except:
        pass
    return True
