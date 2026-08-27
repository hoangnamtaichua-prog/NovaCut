import re
import os
import json
import tempfile
import threading
from platformdirs import user_data_dir

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = user_data_dir('NovaCut', 'NovaCut', roaming=True)
CUSTOM_DICT_FILE = os.path.join(USER_DATA_DIR, "custom_pronunciations.json")
_dictionary_lock = threading.RLock()

# Common Vietnamese abbreviations & units only (NO English word transliteration)
VIETNAMESE_ABBREVIATIONS = {
    # Common Vietnamese abbreviations
    r"\bko\b": "không",
    r"\bKo\b": "Không",
    r"\bk\b": "không",
    r"\bkhum\b": "không",
    r"\bhok\b": "không",
    r"\bdc\b": "được",
    r"\bđc\b": "được",
    r"\bDc\b": "Được",
    r"\bĐc\b": "Được",
    r"\bvs\b": "với",
    r"\bVs\b": "Với",
    r"\bmn\b": "mọi người",
    r"\bMn\b": "Mọi người",
    r"\bae\b": "anh em",
    r"\bAe\b": "Anh em",
    r"\btgian\b": "thời gian",
    r"\bcty\b": "công ty",
    r"\bCty\b": "Công ty",
    r"\bTP\.HCM\b": "thành phố Hồ Chí Minh",
    r"\bTPHCM\b": "thành phố Hồ Chí Minh",
    r"\btphcm\b": "thành phố Hồ Chí Minh",
    r"\bHN\b": "Hà Nội",
    r"\bVN\b": "Việt Nam",
    r"\bNxb\b": "nhà xuất bản",
    r"\bNXB\b": "nhà xuất bản",
    r"\bBS\b": "bác sĩ",
    r"\bBs\b": "bác sĩ",
    r"\bGS\.TS\b": "giáo sư tiến sĩ",
    r"\bGS\b": "giáo sư",
    r"\bTS\b": "tiến sĩ",
    r"\bThS\b": "thạc sĩ",
    r"\bUBND\b": "Ủy ban nhân dân",
    r"\bHĐND\b": "Hội đồng nhân dân",
    
    # Measurement & Currency
    r"\bkm/h\b": "ki lô mét trên giờ",
    r"\bkm/g\b": "ki lô mét trên giờ",
    r"\bkm\b": "ki lô mét",
    r"\bkg\b": "ki lô gam",
    r"\bcm\b": "xen ti mét",
    r"\bmm\b": "mi li mét",
    r"\bm2\b": "mét vuông",
    r"\bm3\b": "mét khối",
    r"\bha\b": "héc ta",
    r"\bVND\b": "đồng",
    r"\bvnd\b": "đồng",
    r"\bVNĐ\b": "đồng",
    r"\bUSD\b": "đô la",
    r"\busd\b": "đô la",
    r"\bEUR\b": "ơ rô",
    r"\beur\b": "ơ rô"
}

def load_custom_pronunciations():
    if not os.path.exists(CUSTOM_DICT_FILE):
        try:
            legacy_file = os.path.join(ROOT_DIR, 'custom_pronunciations.json')
            legacy_data = {}
            if os.path.exists(legacy_file):
                with open(legacy_file, 'r', encoding='utf-8') as handle:
                    loaded = json.load(handle)
                    if isinstance(loaded, dict):
                        legacy_data = loaded
            save_custom_pronunciations(legacy_data)
        except:
            pass
        if not os.path.exists(CUSTOM_DICT_FILE):
            return {}
    try:
        with open(CUSTOM_DICT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_custom_pronunciations(custom_dict):
    os.makedirs(os.path.dirname(CUSTOM_DICT_FILE), exist_ok=True)
    with _dictionary_lock:
        fd, temporary = tempfile.mkstemp(prefix='.novacut_', suffix='.tmp', dir=os.path.dirname(CUSTOM_DICT_FILE))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(custom_dict, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, CUSTOM_DICT_FILE)
        except Exception:
            try:
                os.remove(temporary)
            except OSError:
                pass
            raise

def normalize_text_for_tts(text):
    """
    Cleans and normalizes Vietnamese text for TTS engines:
    - Removes or converts pause syntax [pause 1.0s] into natural pauses (ellipsis)
    - Normalizes numbers with units (100k -> 100 nghìn, 10tr -> 10 triệu, 50% -> 50 phần trăm)
    - Expands common Vietnamese abbreviations (ko -> không, dc -> được)
    - Keeps all English words (AI, Studio, Review, Video, Shorts, etc.) intact as original
    - Expands user-defined custom dictionary entries if specified
    """
    if not text:
        return ""

    text = str(text)

    # 1. Handle pause tokens like [pause 1.0s], [pause 500ms], [nghi 1s]
    text = re.sub(r"\.\s*\[pause\s*[0-9.]+s?\]", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[pause\s*[0-9.]+s?\]", "... ", text, flags=re.IGNORECASE)
    text = re.sub(r"\.\s*\[nghỉ\s*[0-9.]+s?\]", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[nghỉ\s*[0-9.]+s?\]", "... ", text, flags=re.IGNORECASE)
    text = re.sub(r"\[break\s*[0-9.]+s?\]", "... ", text, flags=re.IGNORECASE)

    # 2. Number + Slang units normalization (100k, 10tr, 5tỷ, 50%, 24/7)
    text = re.sub(r"(\d+)\s*[kK]\b", r"\1 nghìn", text)
    text = re.sub(r"(\d+)\s*[tT][rR]\b", r"\1 triệu", text)
    text = re.sub(r"(\d+)\s*%", r"\1 phần trăm", text)
    text = re.sub(r"\b24/7\b", "hai mươi bốn trên bảy", text)
    text = re.sub(r"\b24/24\b", "hai mươi bốn trên hai mươi bốn", text)

    # 3. Currency symbol normalization
    text = re.sub(r"\$\s*(\d+)", r"\1 đô la", text)
    text = re.sub(r"(\d+)\s*\$", r"\1 đô la", text)

    # 4. Built-in Vietnamese Abbreviations
    for pattern, replacement in VIETNAMESE_ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)

    # 5. User Custom Pronunciations (if user explicitly configured)
    custom_dict = load_custom_pronunciations()
    if custom_dict and isinstance(custom_dict, dict):
        for word, phonetic in custom_dict.items():
            if word and phonetic:
                escaped = re.escape(word)
                text = re.sub(rf"\b{escaped}\b", phonetic, text, flags=re.IGNORECASE)

    # 6. Clean up duplicate punctuation & extra whitespaces
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*\.\s*", ". ", text)
    text = text.strip()

    return text

if __name__ == "__main__":
    test_str = "Chào mừng bạn đến với Studio thuyết minh AI cao cấp. [pause 1.0s] Hệ thống hỗ trợ review video 100k view 50% ko lag."
    print("Original:", test_str)
    print("Normalized:", normalize_text_for_tts(test_str))
