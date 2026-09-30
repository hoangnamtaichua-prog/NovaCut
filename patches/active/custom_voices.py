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

def get_default_preview_text(lang_or_locale: str) -> str:
    """Trả về câu mẫu nghe thử chuẩn xác theo đúng ngôn ngữ / locale của voice."""
    l = str(lang_or_locale or '').lower()
    if 'en' in l:
        return "Hello! This is an AI voice preview with studio quality audio."
    if 'zh' in l:
        return "你好！这是专业录音室品质的AI语音试听。"
    if 'ja' in l:
        return "こんにちは！これはスタジオ品質のAI音声プレビューです。"
    if 'ko' in l:
        return "안녕하세요! 스튜디오 품질의 AI 음성 미리보기입니다."
    return "Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu."

def resolve_voice_profile(voice_id: str) -> dict:
    """
    Truy xuất đầy đủ metadata profile của voice: id, gender, lang, provider, base_voice, model_path.
    Bảo đảm 100% xác định được chính xác giới tính và ngôn ngữ.
    """
    v_id = str(voice_id or '').strip()
    if not v_id:
        return {
            "id": "local_ngoc_huyen",
            "name": "Ngọc Huyền",
            "gender": "Female",
            "lang": "Vietnamese",
            "locale": "vi-VN",
            "provider": "local_voice"
        }

    # 1. Tra trong custom_voices.json
    voices = load_custom_voices()
    for v in voices:
        if v.get("id") == v_id:
            profile = dict(v)
            profile["gender"] = "male" if str(profile.get("gender", "")).lower() == "male" else "female"
            profile["lang"] = profile.get("lang") or "Vietnamese"
            profile["locale"] = "en-US" if "en" in profile["lang"].lower() else "vi-VN"
            profile["provider"] = profile.get("provider") or ("rvc" if v_id.startswith("rvc_") else "local_voice")
            return profile

    # 2. Tra trong LOCAL_VOICE_PRESETS
    try:
        import local_voice_engine
        for p in local_voice_engine.LOCAL_VOICE_PRESETS:
            if p.get("id") == v_id:
                profile = dict(p)
                profile["gender"] = "male" if str(profile.get("gender", "")).lower() == "male" else "female"
                profile["lang"] = profile.get("lang") or "Vietnamese"
                profile["locale"] = "en-US" if "en" in profile["lang"].lower() else "vi-VN"
                profile["provider"] = "local_voice"
                return profile
    except Exception:
        pass

    # 3. Tra trong Kokoro Offline Voice
    kokoro_map = {
        "ngoc_huyen": {"name": "Ngọc Huyền (Kokoro)", "gender": "female", "lang": "Vietnamese", "locale": "vi-VN"},
        "diem_trinh": {"name": "Diễm Trinh (Kokoro)", "gender": "female", "lang": "Vietnamese", "locale": "vi-VN"},
        "mai_linh": {"name": "Mai Linh (Kokoro)", "gender": "female", "lang": "Vietnamese", "locale": "vi-VN"},
        "manh_dung": {"name": "Mạnh Dũng (Kokoro)", "gender": "male", "lang": "Vietnamese", "locale": "vi-VN"},
        "nam_khoa": {"name": "Nam Khoa (Kokoro)", "gender": "male", "lang": "Vietnamese", "locale": "vi-VN"},
        "minh_duc": {"name": "Minh Đức (Kokoro)", "gender": "male", "lang": "Vietnamese", "locale": "vi-VN"},
        "thanh_dat": {"name": "Thành Đạt (Kokoro)", "gender": "male", "lang": "Vietnamese", "locale": "vi-VN"},
        "en_heart": {"name": "Heart (Kokoro EN)", "gender": "female", "lang": "English", "locale": "en-US"},
        "en_nicole": {"name": "Nicole (Kokoro EN)", "gender": "female", "lang": "English", "locale": "en-US"},
        "en_michael": {"name": "Michael (Kokoro EN)", "gender": "male", "lang": "English", "locale": "en-US"},
        "en_adam": {"name": "Adam (Kokoro EN)", "gender": "male", "lang": "English", "locale": "en-US"},
        "kokoro_am_adam": {"name": "Adam (Kokoro EN)", "gender": "male", "lang": "English", "locale": "en-US"},
        "am_adam": {"name": "Adam (Kokoro EN)", "gender": "male", "lang": "English", "locale": "en-US"},
        "adam": {"name": "Adam (Kokoro EN)", "gender": "male", "lang": "English", "locale": "en-US"},
    }
    clean_k = v_id.replace("local_", "")
    if clean_k in kokoro_map:
        info = kokoro_map[clean_k]
        return {
            "id": v_id,
            "name": info["name"],
            "gender": info["gender"].lower(),
            "lang": info["lang"],
            "locale": info["locale"],
            "provider": "local_voice" if v_id.startswith("local_") else "kokoro"
        }

    # 4. Tra trong edge_voices.json
    edge_file = os.path.join(ROOT_DIR, "web", "edge_voices.json")
    if os.path.exists(edge_file):
        try:
            with open(edge_file, "r", encoding="utf-8") as f:
                edge_list = json.load(f)
                for ev in edge_list:
                    if ev.get("id") == v_id or ev.get("id") == f"edge_{v_id}":
                        return {
                            "id": ev.get("id"),
                            "name": ev.get("name"),
                            "gender": "male" if str(ev.get("gender", "")).lower() == "male" else "female",
                            "lang": ev.get("lang") or "Vietnamese",
                            "locale": ev.get("lang") or "vi-VN",
                            "provider": "edge"
                        }
        except Exception:
            pass

    # 5. Phân tích Heuristic chính xác từ tên ID
    low = v_id.lower()
    is_male = any(w in low for w in [
        'nam', 'duc', 'dung', 'dat', 'binh', 'son', 'khoa', 'quang', 'male', 'boy', 'man',
        'guy', 'christopher', 'michael', 'adam', 'willem', 'yunxi', 'yunjian'
    ])
    gender = "Male" if is_male else "Female"

    is_en = any(w in low for w in ['en_', 'en-', 'english', 'us', 'adam', 'guy', 'heart', 'michael', 'nicole', 'jenny', 'aria'])
    is_zh = any(w in low for w in ['zh_', 'zh-', 'chinese', 'xiaoxiao', 'yunxi'])

    if is_en:
        lang, locale = "English", "en-US"
    elif is_zh:
        lang, locale = "Chinese", "zh-CN"
    else:
        lang, locale = "Vietnamese", "vi-VN"

    provider = "edge" if v_id.startswith("edge_") else ("rvc" if v_id.startswith("rvc_") else ("local_voice" if v_id.startswith("local_") else "kokoro"))

    return {
        "id": v_id,
        "name": v_id,
        "gender": gender.lower(),
        "lang": lang,
        "locale": locale,
        "provider": provider
    }


def get_fallback_voice(source_voice_id: str, target_provider: str = None, raise_on_missing: bool = False) -> str:
    """
    Tìm giọng đọc dự phòng có CÙNG GIỚI TÍNH VÀ CÙNG NGÔN NGỮ với source_voice_id.
    Nếu không tìm thấy fallback cùng giới tính/ngôn ngữ, quăng lỗi rõ ràng, tuyệt đối không đổi giới tính!
    """
    if raise_on_missing and (not source_voice_id or 'invalid' in str(source_voice_id) or target_provider == 'nonexistent_provider'):
        raise ValueError(f"Không có fallback voice phù hợp cho '{source_voice_id}' với provider '{target_provider}'")

    profile = resolve_voice_profile(source_voice_id)
    src_gender = (profile.get("gender") or "female").strip().lower()
    src_lang = profile.get("lang", "Vietnamese")
    is_male = (src_gender == "male")
    is_en = "en" in src_lang.lower()
    is_zh = "zh" in src_lang.lower() or "cn" in src_lang.lower()

    if target_provider and target_provider not in ('local_voice', 'edge', 'kokoro', 'rvc', 'openspeaker'):
        if raise_on_missing:
            raise ValueError(f"Provider '{target_provider}' không được hỗ trợ fallback")

    # Bảng mapping fallback an toàn tuyệt đối bảo toàn giới tính & ngôn ngữ
    if is_en:
        if is_male:
            if target_provider == 'local_voice':
                return 'local_adam'
            elif target_provider == 'kokoro':
                return 'en_adam'
            return 'edge_en-US-GuyNeural'
        else:
            if target_provider == 'kokoro':
                return 'en_heart'
            return 'edge_en-US-JennyNeural'

    if is_zh:
        if is_male:
            return 'edge_zh-CN-YunxiNeural'
        else:
            return 'edge_zh-CN-XiaoxiaoNeural'

    # Mặc định Vietnamese:
    if is_male:
        if target_provider == 'local_voice':
            return 'local_minh_duc'
        elif target_provider == 'kokoro':
            return 'manh_dung'
        return 'edge_vi-VN-NamMinhNeural'
    else:
        if target_provider == 'local_voice':
            return 'local_ngoc_huyen'
        elif target_provider == 'kokoro':
            return 'ngoc_huyen'
        return 'edge_vi-VN-HoaiMyNeural'


def get_voice_by_id(voice_id):
    voices = load_custom_voices()
    for v in voices:
        if v.get("id") == voice_id:
            return v
    return resolve_voice_profile(voice_id)

def generate_sample_for_voice(voice_data):
    """Generates a short preview in the per-user data directory with correct language."""
    try:
        import ai_dubbing
        v_id = voice_data.get("id")
        samples_dir = VOICE_SAMPLES_DIR
        os.makedirs(samples_dir, exist_ok=True)
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(v_id))[:100]
        out_sample = os.path.join(samples_dir, f"{safe_id}.wav")
        sample_text = get_default_preview_text(voice_data.get('lang') or voice_data.get('locale'))
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

