import os
import json
import re
import tempfile
import threading
import urllib.parse
from platformdirs import user_data_dir

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = user_data_dir('NovaCut', 'NovaCut', roaming=True)
CUSTOM_VOICES_FILE = os.path.join(USER_DATA_DIR, "custom_voices.json")
VOICE_SAMPLES_DIR = os.path.join(USER_DATA_DIR, 'samples')
_voices_lock = threading.RLock()

DEFAULT_CUSTOM_VOICES = []
_default_model = os.environ.get('NOVACUT_DEFAULT_RVC_MODEL', '').strip()
_default_index = os.environ.get('NOVACUT_DEFAULT_RVC_INDEX', '').strip()
if _default_model and os.path.isfile(_default_model):
    DEFAULT_CUSTOM_VOICES.append({
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
        "model_path": _default_model,
        "index_path": _default_index or None,
        "pitch": 0,
        "f0_method": "rmvpe",
        "index_rate": 0.75
    })


def _atomic_save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.novacut_', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise

def load_custom_voices():
    if not os.path.exists(CUSTOM_VOICES_FILE):
        legacy_file = os.path.join(ROOT_DIR, 'custom_voices.json')
        if os.path.exists(legacy_file):
            try:
                with open(legacy_file, 'r', encoding='utf-8') as handle:
                    legacy_voices = json.load(handle)
                voices = legacy_voices if isinstance(legacy_voices, list) else list(DEFAULT_CUSTOM_VOICES)
            except Exception:
                voices = list(DEFAULT_CUSTOM_VOICES)
        else:
            voices = list(DEFAULT_CUSTOM_VOICES)
        save_custom_voices(voices)
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
    samples_dir = VOICE_SAMPLES_DIR
    for v in voices:
        v_id = v.get("id")
        if v_id and not v.get("preview_url"):
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(v_id))[:100]
            sample_f = os.path.join(samples_dir, f"{safe_id}.wav")
            if os.path.exists(sample_f):
                v["preview_url"] = f"/api/file?path={urllib.parse.quote(sample_f)}"
            elif os.path.exists(os.path.join(samples_dir, f"sample_{safe_id}.wav")):
                fallback_sample = os.path.join(samples_dir, f"sample_{safe_id}.wav")
                v["preview_url"] = f"/api/file?path={urllib.parse.quote(fallback_sample)}"

    return voices

def save_custom_voices(voices):
    with _voices_lock:
        _atomic_save_json(CUSTOM_VOICES_FILE, voices)

def get_voice_by_id(voice_id):
    voices = load_custom_voices()
    for v in voices:
        if v.get("id") == voice_id:
            return v
    return None

def generate_sample_for_voice(voice_data):
    """Generates a short preview in the per-user data directory."""
    try:
        import ai_dubbing
        v_id = voice_data.get("id")
        samples_dir = VOICE_SAMPLES_DIR
        os.makedirs(samples_dir, exist_ok=True)
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(v_id))[:100]
        out_sample = os.path.join(samples_dir, f"{safe_id}.wav")
        sample_text = "Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu."
        ai_dubbing.synthesize_sentence(sample_text, v_id, 1.0, out_sample)
    except Exception as e:
        print(f"Error generating sample for {voice_data.get('id')}: {e}")

def add_or_update_voice(voice_data):
    with _voices_lock:
        voices = load_custom_voices()
        v_id = voice_data.get("id")
        if not v_id:
            import uuid
            v_id = f"rvc_{uuid.uuid4().hex}"
        v_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(v_id))[:100]
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
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(voice_id))[:100]
    if safe_id != voice_id:
        return False
    with _voices_lock:
        voices = load_custom_voices()
        new_voices = [v for v in voices if v.get("id") != voice_id]
        save_custom_voices(new_voices)
    # Remove cached sample file if exists
    try:
        sample_f = os.path.join(VOICE_SAMPLES_DIR, f"{safe_id}.wav")
        if os.path.exists(sample_f):
            os.remove(sample_f)
    except:
        pass
    return True
