from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, urllib.parse, uuid, hashlib
from routes.state import *
from routes.security import atomic_write_json, is_path_allowed, safe_join
from werkzeug.utils import secure_filename
import asr_manager

tts_bp = Blueprint('tts', __name__)

VOICE_CACHE_FILE = os.path.join(USER_DATA_DIR, 'openspeaker_voices.json')
TTS_SAMPLE_DIR = os.path.join(USER_DATA_DIR, 'samples')
_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.webm', '.ogg', '.flac'}
MAX_VOICE_UPLOAD_BYTES = 50 * 1024 * 1024


def _require_media_access(feature=None):
    import license_manager
    if feature:
        allowed, message, _ = license_manager.check_permission(feature)
    else:
        status = license_manager.get_current_license_status()
        features = status.get('features', {})
        allowed = bool(status.get('is_valid') and (
            features.get('can_access_editor') or features.get('can_access_review')
        ))
        message = 'Gói bản quyền hiện tại không cho phép sử dụng tính năng xử lý giọng nói.'
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None


def _safe_speed(value):
    speed = float(value)
    if not 0.5 <= speed <= 2.0:
        raise ValueError('Tốc độ giọng đọc phải nằm trong khoảng 0.5 đến 2.0.')
    return speed


def _safe_output_dir(value):
    output_dir = str(value or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        raise ValueError('Thư mục đầu ra chưa được người dùng cho phép.')
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _save_limited_upload(file_storage, destination, limit=MAX_VOICE_UPLOAD_BYTES):
    total = 0
    try:
        with open(destination, 'xb') as handle:
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError(f'Tệp tải lên vượt quá {limit // (1024 * 1024)} MB.')
                handle.write(chunk)
    except Exception:
        try:
            os.remove(destination)
        except OSError:
            pass
        raise

@tts_bp.route('/api/voices', methods=['GET'])
@tts_bp.route('/api/get_voices', methods=['GET'])
def get_voices():
    base_voices = []
    seen_ids = set()

    # 0. Local Voice Presets (High-Quality On-Device Presets)
    try:
        import local_voice_engine
        for lv in local_voice_engine.LOCAL_VOICE_PRESETS:
            if lv['id'] not in seen_ids:
                base_voices.append(lv)
                seen_ids.add(lv['id'])
    except Exception as e:
        print("[Local Voice] Error loading presets:", e)

    # 1. Custom Cloned & RVC Voice Profiles from custom_voices.json
    import custom_voices
    custom_list = custom_voices.load_custom_voices()
    for v in custom_list:
        if v['id'] not in seen_ids:
            base_voices.append(v)
            seen_ids.add(v['id'])

    # 2. Kokoro Offline voices
    default_kokoro = [
        {"id": "ngoc_huyen", "name": "Ngọc Huyền V1 (Kokoro)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "Vietnamese", "region": "Hà Nội", "gender": "Female", "age": "young", "style": "review", "tag": "Offline • Miền Bắc Nữ • Chuẩn cảm xúc", "avatar": "🎙️", "preview_url": "/samples/ngoc_huyen.wav"},
        {"id": "diem_trinh", "name": "Diễm Trinh (Kokoro)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "Vietnamese", "region": "Sài Gòn", "gender": "Female", "age": "young", "style": "story", "tag": "Offline • Miền Nam Nữ • Truyền cảm", "avatar": "👩", "preview_url": "/samples/diem_trinh.wav"},
        {"id": "mai_linh", "name": "Mai Linh (Kokoro)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "Vietnamese", "region": "Huế", "gender": "Female", "age": "young", "style": "emotional", "tag": "Offline • Miền Trung Nữ • Dịu dàng", "avatar": "👧", "preview_url": "/samples/mai_linh.wav"},
        {"id": "manh_dung", "name": "Mạnh Dũng (Kokoro)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "Vietnamese", "region": "Hà Nội", "gender": "Male", "age": "young", "style": "review", "tag": "Offline • Miền Bắc Nam • Trầm ấm", "avatar": "👦", "preview_url": "/samples/manh_dung.wav"},
        {"id": "thanh_dat", "name": "Thành Đạt (Kokoro)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "Vietnamese", "region": "Sài Gòn", "gender": "Male", "age": "young", "style": "news", "tag": "Offline • Miền Nam Nam • Tự nhiên", "avatar": "👨‍💼", "preview_url": "/samples/thanh_dat.wav"},
        {"id": "en_heart", "name": "Heart (Kokoro EN)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "English", "region": "US English", "gender": "Female", "age": "young", "style": "story", "tag": "Offline • English Female • Soft & Warm", "avatar": "💖", "preview_url": "/samples/en_heart.wav"},
        {"id": "en_michael", "name": "Michael (Kokoro EN)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "English", "region": "US English", "gender": "Male", "age": "middle_aged", "style": "news", "tag": "Offline • English Male • Professional", "avatar": "🎙️"},
        {"id": "en_nicole", "name": "Nicole (Kokoro EN)", "provider": "kokoro", "provider_name": "Kokoro Offline", "lang": "English", "region": "US English", "gender": "Female", "age": "young", "style": "review", "tag": "Offline • English Female • Dynamic", "avatar": "✨"}
    ]
    for v in default_kokoro:
        if v['id'] not in seen_ids:
            base_voices.append(v)
            seen_ids.add(v['id'])
    
    # 3. Load full Microsoft Edge Neural TTS voices (100% Miễn phí, 300+ giọng toàn cầu)
    edge_voices_path = os.path.join(ROOT_DIR, 'web', 'edge_voices.json')
    if os.path.exists(edge_voices_path):
        try:
            with open(edge_voices_path, 'r', encoding='utf-8') as f:
                edge_voices = json.load(f)
                for ev in edge_voices:
                    if isinstance(ev, dict) and ev.get('id') and ev['id'] not in seen_ids:
                        base_voices.append(ev)
                        seen_ids.add(ev['id'])
        except Exception as e:
            print("Error loading edge_voices.json:", e)

    # 4. Load cached OpenSpeaker voices (500+ voices)
    openspeaker_path = VOICE_CACHE_FILE
    if not os.path.exists(openspeaker_path):
        openspeaker_path = os.path.join(ROOT_DIR, 'web', 'openspeaker_voices.json')
    if os.path.exists(openspeaker_path):
        try:
            with open(openspeaker_path, 'r', encoding='utf-8') as f:
                api_voices = json.load(f)
                for av in api_voices:
                    if isinstance(av, dict) and av.get('id') and av['id'] not in seen_ids:
                        base_voices.append(av)
                        seen_ids.add(av['id'])
        except Exception as e:
            print("Error loading openspeaker_voices.json:", e)

    return jsonify(base_voices)

def get_open_speaker_key():
    if request.is_json and request.json:
        k = request.json.get('api_key') or request.json.get('openSpeakerApiKey')
        if k:
            return k.strip()
    if os.path.exists(API_KEYS_FILE):
        try:
            with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('openSpeakerApiKey='):
                        return line.split('=', 1)[1].strip()
        except Exception:
            pass
    return None

@tts_bp.route('/api/voices/refresh', methods=['POST'])
def refresh_voices():
    permission_error = _require_media_access('online_voices_enabled')
    if permission_error:
        return permission_error
    import requests
    api_key = get_open_speaker_key()
    if not api_key:
        return jsonify({"success": False, "error": "Chưa cấu hình OpenSpeaker API Key trong Cài đặt."})
        
    providers = ['vbee', 'elevenlabs', 'minimax', 'fishaudio', 'edge', 'clone', 'kokoro']
    all_voices_list = []
    seen_ids = set()

    for p in providers:
        page = 1
        while True:
            try:
                url = f"https://api.ai33.pro/v3/voices?provider={p}&page={page}&limit=100"
                res = requests.get(url, headers={"xi-api-key": api_key}, timeout=20)
                if res.status_code != 200:
                    break
                res_json = res.json()
                items = res_json.get('data', [])
                if not items:
                    break
                
                for item in items:
                    v_id = item.get('voice_id') or item.get('id')
                    if not v_id or v_id in seen_ids:
                        continue
                    seen_ids.add(v_id)
                    name = item.get('name', v_id)
                    gender = item.get('gender') or item.get('labels', {}).get('gender', '')
                    if str(gender).lower() in ['female', 'nữ', 'f']: gender = 'Female'
                    elif str(gender).lower() in ['male', 'nam', 'm']: gender = 'Male'
                    else: gender = 'Female'
                    
                    lang = item.get('language') or item.get('lang') or item.get('locale') or item.get('labels', {}).get('language', '')
                    lang_lower = str(lang).lower()
                    if 'vi' in lang_lower or 'viet' in lang_lower:
                        lang = 'Vietnamese'
                    elif 'en' in lang_lower or 'eng' in lang_lower:
                        lang = 'English'
                    elif 'zh' in lang_lower or 'chi' in lang_lower:
                        lang = 'Chinese'
                    elif 'ja' in lang_lower or 'jap' in lang_lower:
                        lang = 'Japanese'
                    elif 'ko' in lang_lower or 'kor' in lang_lower:
                        lang = 'Korean'
                    elif p not in ['vbee', 'kokoro']:
                        # Bỏ qua các ngôn ngữ khác để giữ thư viện giọng gọn nhẹ, siêu mượt
                        continue
                    
                    # Giới hạn ElevenLabs tiếng Anh ở mức 150 giọng phổ biến nhất
                    if p == 'elevenlabs' and lang == 'English':
                        el_en_count = sum(1 for x in all_voices_list if x['provider'] == 'elevenlabs' and x['lang'] == 'English')
                        if el_en_count >= 150:
                            continue
                    
                    region = item.get('accent') or item.get('region') or item.get('labels', {}).get('accent', 'Toàn quốc')
                    age = item.get('age') or item.get('labels', {}).get('age', 'young')
                    desc = item.get('description') or item.get('tag') or f"{p.capitalize()} • {lang}"
                    
                    avatar = "🎙️"
                    if p == 'vbee': avatar = "🇻🇳"
                    elif p == 'edge': avatar = "🌟"
                    elif p == 'minimax': avatar = "👦" if gender == 'Male' else "👱‍♀️"
                    elif p == 'elevenlabs': avatar = "✨"
                    elif p == 'fishaudio': avatar = "🎀" if gender == 'Female' else "🐵"
                    
                    all_voices_list.append({
                        "id": v_id,
                        "name": name,
                        "provider": p,
                        "provider_name": f"{p.capitalize()} Cloud" if p != 'edge' else "Edge AI (Miễn phí)",
                        "lang": lang,
                        "region": region,
                        "gender": gender,
                        "age": age,
                        "style": item.get('style', 'review'),
                        "tag": f"{p.capitalize()} • {gender} • {region} • {desc}",
                        "avatar": avatar,
                        "preview_url": item.get('preview_url', '')
                    })
                if len(items) < 100:
                    break
                page += 1
            except Exception as e:
                print(f"Error fetching {p} voices page {page}: {e}")
                break

    if all_voices_list:
        atomic_write_json(VOICE_CACHE_FILE, all_voices_list)
        return jsonify({"success": True, "count": len(all_voices_list)})
    return jsonify({"success": False, "error": "Không thể tải danh sách giọng từ máy chủ (danh sách rỗng)."}), 502

@tts_bp.route('/api/custom-voices', methods=['GET'])
def api_get_custom_voices():
    import custom_voices
    voices = custom_voices.load_custom_voices()
    return jsonify({"success": True, "voices": voices})

@tts_bp.route('/api/custom-voices', methods=['POST'])
def api_add_custom_voice():
    permission_error = _require_media_access('can_clone_voice')
    if permission_error:
        return permission_error
    import custom_voices
    data = request.json or {}
    name = data.get('name', '').strip()
    model_path = data.get('model_path', '').strip()
    
    if not name or not model_path:
        return jsonify({"success": False, "error": "Vui lòng nhập tên giọng và chọn file Model .pth"}), 400
        
    if not is_path_allowed(model_path, must_exist=True, extensions={'.pth'}):
        return jsonify({"success": False, "error": f"Không tìm thấy file model: {model_path}"}), 400

    index_path = data.get("index_path", "").strip()
    if index_path and not is_path_allowed(index_path, must_exist=True, extensions={'.index'}):
        return jsonify({"success": False, "error": "File index không hợp lệ hoặc chưa được cho phép"}), 400

    new_voice = {
        "id": data.get("id") or f"rvc_{int(time.time())}",
        "name": name,
        "provider": "rvc",
        "provider_name": "RVC Clone",
        "lang": data.get("lang", "Vietnamese"),
        "region": data.get("region", "Toàn quốc"),
        "gender": data.get("gender", "Female"),
        "age": data.get("age", "young"),
        "style": data.get("style", "review"),
        "tag": data.get("tag") or f"RVC Model • RTX 5060 • {name}",
        "avatar": data.get("avatar") or ("👩" if data.get("gender") == "Female" else "👨"),
        "base_voice": data.get("base_voice") or ("edge_vi-VN-HoaiMyNeural" if data.get("gender") == "Female" else "edge_vi-VN-NamMinhNeural"),
        "model_path": model_path,
        "index_path": index_path or None,
        "pitch": int(data.get("pitch", 0)),
        "f0_method": data.get("f0_method", "rmvpe"),
        "index_rate": float(data.get("index_rate", 0.45)),
        "protect": float(data.get("protect", 0.50))
    }
    
    saved = custom_voices.add_or_update_voice(new_voice)
    return jsonify({"success": True, "voice": saved})

@tts_bp.route('/api/custom-voices/<voice_id>', methods=['DELETE'])
def api_delete_custom_voice(voice_id):
    permission_error = _require_media_access('can_clone_voice')
    if permission_error:
        return permission_error
    import custom_voices
    custom_voices.delete_voice(voice_id)
    return jsonify({"success": True})

@tts_bp.route('/api/pronunciations', methods=['GET'])
def get_pronunciations():
    import vietnamese_text_normalizer
    return jsonify({
        "success": True,
        "custom": vietnamese_text_normalizer.load_custom_pronunciations(),
        "defaults_count": len(vietnamese_text_normalizer.DEFAULT_PRONUNCIATIONS)
    })

@tts_bp.route('/api/pronunciations', methods=['POST'])
def add_pronunciation():
    permission_error = _require_media_access()
    if permission_error:
        return permission_error
    import vietnamese_text_normalizer
    data = request.json or {}
    word = data.get('word', '').strip()
    phonetic = data.get('phonetic', '').strip()
    if not word or not phonetic:
        return jsonify({"success": False, "error": "Vui lòng nhập từ gốc và phiên âm"}), 400
    
    d = vietnamese_text_normalizer.load_custom_pronunciations()
    d[word] = phonetic
    vietnamese_text_normalizer.save_custom_pronunciations(d)
    return jsonify({"success": True, "pronunciations": d})

@tts_bp.route('/api/pronunciations/<word>', methods=['DELETE'])
def delete_pronunciation(word):
    permission_error = _require_media_access()
    if permission_error:
        return permission_error
    import vietnamese_text_normalizer
    d = vietnamese_text_normalizer.load_custom_pronunciations()
    if word in d:
        del d[word]
        vietnamese_text_normalizer.save_custom_pronunciations(d)
    return jsonify({"success": True, "pronunciations": d})

@tts_bp.route('/api/tts/preview', methods=['POST'])
def generate_tts_preview():
    try:
        permission_error = _require_media_access()
        if permission_error:
            return permission_error
        data = request.json or {}
        raw_vid = str(data.get('voice') or data.get('voice_id') or 'local_ngoc_huyen').strip()
        voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_vid)[:100]
        
        import custom_voices
        voice_profile = custom_voices.resolve_voice_profile(voice_id)
        
        lang = str(data.get('lang') or voice_profile.get('lang') or 'Vietnamese').strip()
        locale = str(data.get('locale') or voice_profile.get('locale') or ('en-US' if 'en' in lang.lower() else 'vi-VN')).strip()
        gender = str(data.get('gender') or voice_profile.get('gender') or 'Female').strip()
        speed = float(data.get('speed') or 1.0)
        speed = max(0.5, min(2.0, speed))
        
        # Lấy text truyền vào hoặc text mặc định theo đúng locale/ngôn ngữ
        text = str(data.get('text') or '').strip()
        default_vi = "Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu."
        is_en_voice = 'en' in lang.lower() or locale.lower().startswith('en')
        if not text or (is_en_voice and text == default_vi):
            text = custom_voices.get_default_preview_text(locale or lang)
        else:
            # Kiểm tra text có bị lệch ngôn ngữ nghiêm trọng so với voice không
            is_vi_text = bool(re.search(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', text, re.IGNORECASE))
            if is_en_voice and is_vi_text:
                return jsonify({
                    'success': False,
                    'error': f"Language mismatch: Văn bản ('{text[:30]}...') là tiếng Việt, không khớp với voice tiếng Anh '{voice_id}' (locale: {locale})."
                }), 400
            if ('vi' in lang.lower() or locale.lower().startswith('vi')) and re.search(r'[\u4e00-\u9fff]', text):
                return jsonify({
                    'success': False,
                    'error': f"Language mismatch: Văn bản chứa chữ Hán, không khớp với voice tiếng Việt '{voice_id}'."
                }), 400
        text = text[:1000]

        samples_dir = TTS_SAMPLE_DIR
        os.makedirs(samples_dir, exist_ok=True)
        
        # Cache key phải gồm voice + text + locale + speed + engine version
        engine_version = "v2_locale_fixed"
        cache_raw = f"{voice_id}|{text}|{locale.lower()}|{speed:.2f}|{engine_version}"
        cache_hash = hashlib.sha256(cache_raw.encode('utf-8')).hexdigest()[:16]
        sample_filename = f"prev_{voice_id}_{cache_hash}.wav"
        sample_path = os.path.join(samples_dir, sample_filename)
        
        # 1. If sample already exists, return instantly
        if os.path.exists(sample_path) and os.path.getsize(sample_path) > 1000:
            return jsonify({
                'success': True,
                'audio_url': f'/api/file?path={urllib.parse.quote(sample_path)}',
                'cached': True
            })
            
        # 2. Generate and cache
        import ai_dubbing
        ai_dubbing.synthesize_sentence(text, voice_id, speed, sample_path)
        
        return jsonify({
            'success': True,
            'audio_url': f'/api/file?path={urllib.parse.quote(sample_path)}',
            'cached': False
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

_timeline_preview_lock = threading.Lock()


@tts_bp.route('/api/tts/timeline_preview', methods=['POST'])
def generate_timeline_preview():
    permission_error = _require_media_access()
    if permission_error:
        return permission_error
    try:
        import hashlib
        import math
        import ai_dubbing
        data = request.get_json() or {}
        subtitles = data.get('subtitles')
        if not isinstance(subtitles, list) or not 0 < len(subtitles) <= 10000:
            raise ValueError('Danh sách phụ đề phải có từ 1 đến 10.000 câu.')
        normalized = []
        for sub in subtitles:
            text = str(sub.get('translation') or sub.get('text') or '').strip()
            start = float(sub.get('startSeconds', 0))
            end = float(sub.get('endSeconds', start + 3))
            if not all(math.isfinite(v) and 0 <= v <= 86400 for v in (start, end)):
                raise ValueError('Thời gian phụ đề không hợp lệ.')
            if text:
                normalized.append({'text': text, 'startSeconds': start, 'endSeconds': end})
        if not normalized or sum(len(s['text']) for s in normalized) > 250000:
            raise ValueError('Phụ đề rỗng hoặc vượt quá 250.000 ký tự.')
        voice = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id') or 'local_ngoc_huyen'))[:100]
        speed = _safe_speed(data.get('speed', 1))
        identity = json.dumps([normalized, voice, speed], ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        directory = os.path.join(ROOT_DIR, 'temp', 'timeline_preview', digest)
        track = os.path.join(directory, 'dubbed_timeline.wav')
        with _timeline_preview_lock:
            if not os.path.isfile(track) or os.path.getsize(track) <= 1000:
                key = ''
                if os.path.isfile(API_KEYS_FILE):
                    with open(API_KEYS_FILE, encoding='utf-8') as stream:
                        for line in stream:
                            if line.startswith('openSpeakerApiKey='):
                                key = line.split('=', 1)[1].strip()
                errors = []
                output = None
                for kind, message in ai_dubbing.build_dubbing_track_for_subtitles_generator(
                        normalized, voice, speed, directory, open_speaker_key=key,
                        max_workers=None):
                    if kind == 'done':
                        output = message
                    elif 'Lỗi câu #' in message or 'LỖI' in message or 'Lỗi xử lý:' in message:
                        errors.append(message)
                if not output or errors:
                    if os.path.isfile(track):
                        os.remove(track)
                    raise RuntimeError(errors[0] if errors else 'Không tạo được âm thanh nghe thử.')
        return jsonify(success=True, audio_url='/api/file?path=' + urllib.parse.quote(track))
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 500


@tts_bp.route('/api/tts/sentence_preview', methods=['POST'])
def generate_sentence_preview():
    try:
        permission_error = _require_media_access()
        if permission_error:
            return permission_error
        data = request.json or {}
        text = str(data.get('text', '')).strip()
        voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id') or data.get('voice') or 'local_ngoc_huyen'))[:100]
        speed = _safe_speed(data.get('speed', 1.0))
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản rỗng'}), 400
        if len(text) > 5000:
            return jsonify({'success': False, 'error': 'Văn bản nghe thử vượt quá 5.000 ký tự'}), 413
            
        import hashlib
        cache_dir = os.path.join(TTS_SAMPLE_DIR, 'tts_cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        # MD5 hash of voice, speed, text
        hash_key = hashlib.md5(f"{voice_id}_{speed}_{text}".encode('utf-8')).hexdigest()
        cache_filename = f"{hash_key}.wav"
        cache_path = os.path.join(cache_dir, cache_filename)
        
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 500:
            return jsonify({
                'success': True,
                'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
                'cached': True
            })
            
        import ai_dubbing
        ai_dubbing.synthesize_sentence(text, voice_id, speed, cache_path)
        
        return jsonify({
            'success': True,
            'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
            'cached': False
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@tts_bp.route('/api/tts/batch_sentence_preview', methods=['POST'])
def generate_batch_sentence_preview():
    try:
        permission_error = _require_media_access()
        if permission_error:
            return permission_error
        data = request.json or {}
        sentences = data.get('sentences', [])
        voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id') or data.get('voice') or 'local_ngoc_huyen'))[:100]
        speed = _safe_speed(data.get('speed', 1.0))

        if not isinstance(sentences, list) or not sentences:
            return jsonify({'success': False, 'error': 'Danh sách câu rỗng'}), 400

        sentences = sentences[:30]

        import hashlib
        cache_dir = os.path.join(TTS_SAMPLE_DIR, 'tts_cache')
        os.makedirs(cache_dir, exist_ok=True)

        results = []
        to_synthesize = []

        for item in sentences:
            if isinstance(item, str):
                item = {'text': item}
            raw_text = str(item.get('text', '')).strip()
            item_id = item.get('id', item.get('index'))
            if not raw_text:
                continue

            hash_key = hashlib.md5(f"{voice_id}_{speed}_{raw_text}".encode('utf-8')).hexdigest()
            cache_filename = f"{hash_key}.wav"
            cache_path = os.path.join(cache_dir, cache_filename)

            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 500:
                results.append({
                    'id': item_id,
                    'text': raw_text,
                    'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
                    'cached': True,
                    'success': True
                })
            else:
                to_synthesize.append({
                    'id': item_id,
                    'text': raw_text,
                    'cache_path': cache_path
                })

        if to_synthesize:
            is_local = voice_id.startswith('local_')
            if is_local:
                import local_voice_engine
                batch_items = [{'id': task['id'], 'text': task['text'], 'output_path': task['cache_path']} for task in to_synthesize]
                b_results = local_voice_engine.synthesize_batch(batch_items, voice_id=voice_id, speed=speed, batch_size=8)
                for task, res in zip(to_synthesize, b_results):
                    if res.get('success') and os.path.exists(task['cache_path']) and os.path.getsize(task['cache_path']) > 100:
                        results.append({
                            'id': task['id'],
                            'text': task['text'],
                            'audio_url': f"/api/file?path={urllib.parse.quote(task['cache_path'])}",
                            'cached': False,
                            'success': True
                        })
                    else:
                        results.append({
                            'id': task['id'],
                            'text': task['text'],
                            'error': res.get('error', 'Lỗi tạo audio GPU'),
                            'success': False
                        })
            else:
                import ai_dubbing
                from concurrent.futures import ThreadPoolExecutor

                def _synth(task):
                    try:
                        ai_dubbing.synthesize_sentence(task['text'], voice_id, speed, task['cache_path'])
                        return {
                            'id': task['id'],
                            'text': task['text'],
                            'audio_url': f"/api/file?path={urllib.parse.quote(task['cache_path'])}",
                            'cached': False,
                            'success': True
                        }
                    except Exception as ex:
                        return {
                            'id': task['id'],
                            'text': task['text'],
                            'error': str(ex),
                            'success': False
                        }

                max_workers = min(4, len(to_synthesize))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    synth_results = list(executor.map(_synth, to_synthesize))
                    results.extend(synth_results)

        return jsonify({
            'success': True,
            'results': results,
            'total': len(results)
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def parse_text_into_speech_segments(text, default_pause=0.5):
    """
    Tách văn bản thành danh sách các câu nói và các khoảng nghỉ theo giây.
    Hỗ trợ cả tag [pause Xs] hoặc tự động ngắt câu với khoảng nghỉ mặc định 0.5s.
    """
    pause_pattern = re.compile(r'\[pause(?:\s+([\d\.]+)\s*s?)?\]', re.IGNORECASE)
    parts = pause_pattern.split(text)
    
    segments = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            try:
                p_sec = float(part) if part else default_pause
            except Exception:
                p_sec = default_pause
            if p_sec > 0:
                segments.append(('pause', p_sec))
        else:
            if not part:
                continue
            # Tách tiếp part thành các câu tự nhiên
            raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?…\n])\s+', part) if s.strip()]
            for s in raw_sentences:
                segments.append(('speech', s))
                if default_pause > 0:
                    segments.append(('pause', default_pause))

    # Xóa pause thừa ở cuối
    while segments and segments[-1][0] == 'pause':
        segments.pop()

    return segments

def sec_to_srt_time(sec):
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    milis = int(round((sec - int(sec)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{milis:03d}"

@tts_bp.route('/api/tts/kokoro', methods=['POST'])
def generate_tts_kokoro():
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('tts_unlimited_local')
        if not allowed:
            return jsonify({'success': False, 'error': perm_msg}), 403

        data = request.json or {}
        text = data.get('text', '').strip()
        voice_id = data.get('voice') or data.get('voice_id') or 'local_ngoc_huyen'
        speed = _safe_speed(data.get('speed', 1.0))
        output_dir = _safe_output_dir(data.get('output_dir'))
        filename = data.get('filename')
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản kịch bản trống'}), 400
        if len(text) > 250000:
            return jsonify({'success': False, 'error': 'Kịch bản vượt quá 250.000 ký tự'}), 413

        timestamp = int(time.time()*1000)
        if not filename:
            clean_vid = re.sub(r'[^a-zA-Z0-9_]', '_', voice_id)
            filename = f"tts_{clean_vid}_{timestamp}.wav"
        filename = secure_filename(str(filename))
        if not filename.endswith('.wav'):
            filename += '.wav'
            
        audio_path = safe_join(output_dir, filename, extensions={'.wav'})
        srt_filename = filename.rsplit('.', 1)[0] + '.srt'
        srt_path = os.path.join(output_dir, srt_filename)
        
        import importlib
        import ai_dubbing
        import soundfile as sf
        import numpy as np

        segments = parse_text_into_speech_segments(text, default_pause=0.5)
        speech_segments = [s for s in segments if s[0] == 'speech']
        
        if len(speech_segments) <= 1:
            # Single sentence
            raw_text = speech_segments[0][1] if speech_segments else text
            ai_dubbing.synthesize_sentence(raw_text, voice_id, speed, audio_path)
            f = sf.SoundFile(audio_path)
            duration = len(f) / float(f.samplerate)
            srt_content = f"1\n{sec_to_srt_time(0.0)} --> {sec_to_srt_time(duration)}\n{raw_text}\n"
            with open(srt_path, 'w', encoding='utf-8') as srt_f:
                srt_f.write(srt_content)
        else:
            # Multi-sentence TTS with sentence-level timestamps & 0.5s silence pauses
            # Kích hoạt xử lý đa luồng song song (Multi-threading) tăng tốc độ tạo giọng
            from concurrent.futures import ThreadPoolExecutor
            
            is_edge = voice_id.startswith('edge_')
            req_threads = int(data.get('threads') or data.get('tts_threads') or 16)
            max_workers = max(2, min(req_threads, 32 if is_edge else 16))
            
            speech_tasks = []
            speech_idx = 1
            for seg_type, val in segments:
                if seg_type == 'speech':
                    chunk_wav = os.path.join(output_dir, f"temp_chunk_{timestamp}_{speech_idx}.wav")
                    speech_tasks.append((speech_idx, val, chunk_wav))
                    speech_idx += 1

            def _synth_worker(task):
                idx, sentence_text, chunk_file = task
                try:
                    ai_dubbing.synthesize_sentence(sentence_text, voice_id, speed, chunk_file)
                    return (idx, chunk_file, None)
                except Exception as ex:
                    return (idx, chunk_file, str(ex))

            chunk_results = {}
            if speech_tasks:
                if voice_id.startswith('local_'):
                    import local_voice_engine
                    batch_items = [{'id': s_idx, 'text': val, 'output_path': c_file} for s_idx, val, c_file in speech_tasks]
                    b_res = local_voice_engine.synthesize_batch(batch_items, voice_id=voice_id, speed=speed, batch_size=16)
                    for item, r in zip(speech_tasks, b_res):
                        chunk_results[item[0]] = (item[2], r.get('error') if not r.get('success') else None)
                else:
                    actual_workers = min(max_workers, len(speech_tasks))
                    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
                        for s_idx, c_file, err in pool.map(_synth_worker, speech_tasks):
                            chunk_results[s_idx] = (c_file, err)

            # Xác định sample rate chuẩn từ chunk đầu tiên
            target_sr = 48000 if voice_id.startswith('local_') else 24000
            for s_idx in sorted(chunk_results.keys()):
                cf, _ = chunk_results[s_idx]
                if cf and os.path.exists(cf) and os.path.getsize(cf) > 100:
                    try:
                        with sf.SoundFile(cf) as sff:
                            if sff.samplerate > 0:
                                target_sr = sff.samplerate
                                break
                    except Exception:
                        pass

            srt_blocks = []
            current_time = 0.0
            sentence_idx = 1
            has_written_frames = False

            # Ghi tuần tự theo khối (Stream-based chunk write) trực tiếp vào file đích
            # Giữ mức RAM sử dụng luôn < 5MB, chống triệt để lỗi Out-Of-Memory và C-segfault trong libsndfile
            with sf.SoundFile(audio_path, mode='w', samplerate=target_sr, channels=1, subtype='PCM_16') as out_f:
                for seg_type, val in segments:
                    if seg_type == 'speech':
                        c_file, err = chunk_results.get(sentence_idx, (None, None))
                        if c_file and os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                            try:
                                data, sr = sf.read(c_file, dtype='float32')
                                if len(data.shape) > 1:
                                    data = data.mean(axis=1) # convert to mono
                                # Nếu sample rate khác target_sr thì resample an toàn
                                if sr != target_sr and len(data) > 0:
                                    import scipy.signal
                                    new_len = int(round(len(data) * target_sr / float(sr)))
                                    data = scipy.signal.resample(data, new_len)
                                
                                dur = len(data) / float(target_sr)
                                start_str = sec_to_srt_time(current_time)
                                end_str = sec_to_srt_time(current_time + dur)
                                srt_blocks.append(f"{sentence_idx}\n{start_str} --> {end_str}\n{val}\n")
                                out_f.write(data)
                                has_written_frames = True
                                current_time += dur
                            except Exception as read_err:
                                print(f"[TTS] Lỗi đọc đoạn audio câu #{sentence_idx}: {read_err}")
                            finally:
                                try:
                                    if os.path.exists(c_file):
                                        os.remove(c_file)
                                except Exception:
                                    pass
                        sentence_idx += 1
                        
                    elif seg_type == 'pause':
                        pause_dur = float(val)
                        if pause_dur > 0:
                            pause_samples = int(target_sr * pause_dur)
                            out_f.write(np.zeros(pause_samples, dtype=np.float32))
                            current_time += pause_dur

                if not has_written_frames:
                    out_f.write(np.zeros(target_sr, dtype=np.float32))
                    current_time = 1.0

            duration = current_time
            srt_content = "\n".join(srt_blocks)
            with open(srt_path, 'w', encoding='utf-8') as srt_f:
                srt_f.write(srt_content)
            
        # Không bắn Telegram nếu là tác vụ tạo từng câu nhỏ trong chuỗi review / sub-clip
        skip_notify = data.get('skip_notify', False) or data.get('notify') is False
        if not skip_notify and filename and str(filename).startswith(('sent_', 'narration_', 'temp_')):
            skip_notify = True
        if not skip_notify and output_dir and any(x in str(output_dir).replace('\\', '/').lower() for x in ['auto_edit_temp', 'clips/audio', 'sentences', '/temp']):
            skip_notify = True

        if not skip_notify:
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    notifier.notify_task_success(
                        task_type='tts',
                        task_title='Tạo Giọng Đọc AI (TTS)',
                        video_title=os.path.basename(audio_path),
                        output_path=audio_path,
                        extra_info={
                            'Giọng đọc': voice_id,
                            'Tốc độ': f"{speed}x",
                            'Thời lượng': f"{round(duration, 1)}s"
                        }
                    )
            except Exception as _te:
                logging.getLogger(__name__).warning(f"[Telegram] Error sending TTS notification: {_te}")

        import urllib.parse
        return jsonify({
            'success': True,
            'filename': filename,
            'audio_url': f'/api/file?path={urllib.parse.quote(audio_path)}',
            'srt_url': f'/api/file?path={urllib.parse.quote(srt_path)}',
            'absolute_path': os.path.abspath(audio_path),
            'srt_absolute_path': os.path.abspath(srt_path),
            'duration': round(duration, 2)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        if not locals().get('skip_notify', False):
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    notifier.notify_task_failure(
                        task_type='tts',
                        task_title='Tạo Giọng Đọc AI (TTS)',
                        video_title=filename if 'filename' in locals() else "TTS Audio",
                        error_message=str(e)
                    )
            except Exception:
                pass
        return jsonify({'success': False, 'error': f"Lỗi tạo TTS: {str(e)}"}), 500

@tts_bp.route('/api/tts/openspeaker/voices', methods=['GET'])
def get_openspeaker_voices():
    permission_error = _require_media_access('online_voices_enabled')
    if permission_error:
        return permission_error
    import requests
    api_key = get_open_speaker_key()
    if not api_key:
        return jsonify({'error': 'Missing API Key'}), 400
    
    provider = request.args.get('provider', '')
    url = f"https://api.ai33.pro/v3/voices?limit=100"
    if provider:
        url += f"&provider={provider}"
        
    try:
        res = requests.get(url, headers={"xi-api-key": api_key}, timeout=20)
        res.raise_for_status()
        return jsonify(res.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@tts_bp.route('/api/tts/openspeaker', methods=['POST'])
def generate_tts_openspeaker():
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('online_voices_enabled')
        if not allowed:
            return jsonify({'success': False, 'error': perm_msg}), 403

        data = request.json or {}
        text = data.get('text', '').strip()
        voice_id = data.get('voice') or data.get('voice_id') or 'ngoc_huyen'
        speed = _safe_speed(data.get('speed', 1.0))
        output_dir = _safe_output_dir(data.get('output_dir'))
        filename = data.get('filename')
        api_key = data.get('api_key')
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản kịch bản trống'}), 400
        if len(text) > 250000:
            return jsonify({'success': False, 'error': 'Kịch bản vượt quá 250.000 ký tự'}), 413
            
        if not api_key:
            api_keys_file = API_KEYS_FILE
            if os.path.exists(api_keys_file):
                with open(api_keys_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key = line.split('=', 1)[1].strip()
                            
        if not api_key:
            return jsonify({'success': False, 'error': 'Vui lòng cung cấp OpenSpeaker API Key'}), 400
            
        timestamp = int(time.time())
        if not filename:
            filename = f"tts_open_{voice_id}_{timestamp}.mp3"
        filename = secure_filename(str(filename))
        if not (filename.endswith('.mp3') or filename.endswith('.wav')):
            filename += '.mp3'
            
        audio_path = safe_join(output_dir, filename, extensions={'.mp3', '.wav'})
        srt_filename = filename.rsplit('.', 1)[0] + '.srt'
        srt_path = os.path.join(output_dir, srt_filename)
        
        import importlib
        import ai_dubbing
        importlib.reload(ai_dubbing)
        ai_dubbing.synthesize_sentence(text, voice_id, speed, audio_path, open_speaker_key=api_key)
        
        duration = 5.0
        try:
            import ffmpeg_installer
            ff = ffmpeg_installer.get_ffmpeg_path()
            p = subprocess.run([ff, '-i', audio_path], stderr=subprocess.PIPE, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
            import re
            m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', p.stderr)
            if m:
                duration = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
        except Exception:
            pass
            
        def sec_to_srt_time(sec):
            hrs = int(sec // 3600)
            mins = int((sec % 3600) // 60)
            secs = int(sec % 60)
            milis = int(round((sec - int(sec)) * 1000))
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{milis:03d}"
            
        srt_content = f"1\n{sec_to_srt_time(0.0)} --> {sec_to_srt_time(duration)}\n{text}\n"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
            
        # Không bắn Telegram nếu là tác vụ tạo từng câu nhỏ trong chuỗi review / sub-clip
        skip_notify = data.get('skip_notify', False) or data.get('notify') is False
        if not skip_notify and filename and str(filename).startswith(('sent_', 'narration_', 'temp_')):
            skip_notify = True
        if not skip_notify and output_dir and any(x in str(output_dir).replace('\\', '/').lower() for x in ['auto_edit_temp', 'clips/audio', 'sentences', '/temp']):
            skip_notify = True

        if not skip_notify:
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    notifier.notify_task_success(
                        task_type='tts',
                        task_title='Tạo Giọng Đọc AI (OpenSpeaker)',
                        video_title=os.path.basename(audio_path),
                        output_path=audio_path,
                        extra_info={
                            'Giọng đọc': voice_id,
                            'Tốc độ': f"{speed}x",
                            'Thời lượng': f"{round(duration, 1)}s"
                        }
                    )
            except Exception as _te:
                logging.getLogger(__name__).warning(f"[Telegram] Error sending OpenSpeaker TTS notification: {_te}")

        import urllib.parse
        return jsonify({
            'success': True,
            'filename': filename,
            'audio_url': f'/api/file?path={urllib.parse.quote(audio_path)}',
            'srt_url': f'/api/file?path={urllib.parse.quote(srt_path)}',
            'absolute_path': os.path.abspath(audio_path),
            'srt_absolute_path': os.path.abspath(srt_path),
            'duration': duration
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        if not locals().get('skip_notify', False):
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    notifier.notify_task_failure(
                        task_type='tts',
                        task_title='Tạo Giọng Đọc AI (OpenSpeaker)',
                        video_title=filename if 'filename' in locals() else "OpenSpeaker Audio",
                        error_message=str(e)
                    )
            except Exception:
                pass
        return jsonify({'success': False, 'error': str(e)}), 500

# =========================================================================
# CLONE VOICE & LOCAL VOICE API ENDPOINTS
# =========================================================================

@tts_bp.route('/api/clone_voice/upload', methods=['POST'])
def api_clone_voice_upload():
    """
    Nhận file âm thanh mẫu (WAV/MP3/M4A/WEBM từ upload hoặc ghi âm mic) và chuyển đổi thành WAV chuẩn.
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_clone_voice')
    if not allowed:
        return jsonify({'success': False, 'error': perm_msg}), 403

    file = request.files.get('audio') or request.files.get('audio_file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Không tìm thấy tệp âm thanh trong yêu cầu'}), 400

    original_name = secure_filename(file.filename)
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in _AUDIO_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Định dạng âm thanh không được hỗ trợ'}), 415
    if request.content_length and request.content_length > MAX_VOICE_UPLOAD_BYTES + 1024 * 1024:
        return jsonify({'success': False, 'error': 'Tệp âm thanh vượt quá 50 MB'}), 413

    temp_dir = os.path.join(ROOT_DIR, "output", "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    upload_id = uuid.uuid4().hex
    raw_path = safe_join(temp_dir, f"raw_{upload_id}{extension}", extensions=_AUDIO_EXTENSIONS)
    try:
        _save_limited_upload(file, raw_path)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 413

    import local_voice_engine
    clean_sample_path = safe_join(temp_dir, f"clean_{upload_id}.wav", extensions={'.wav'})
    ok, res = local_voice_engine.validate_and_convert_audio_sample(raw_path, clean_sample_path, return_meta=True)
    
    # Dọn dẹp file raw nếu khác file clean
    if raw_path != clean_sample_path and os.path.exists(raw_path):
        try: os.remove(raw_path)
        except: pass

    if not ok:
        return jsonify({'success': False, 'error': res}), 400

    meta = res if isinstance(res, dict) else {'path': clean_sample_path, 'duration': 0, 'original_duration': 0, 'is_trimmed': False}
    duration = meta.get('duration', 0)
    if not duration:
        import wave
        with wave.open(clean_sample_path, 'r') as wf:
            duration = round(wf.getnframes() / float(wf.getframerate()), 2)

    quality_score = 90 if 2.0 <= duration <= 12.0 else 75
    quality_desc = "Rất tốt (24kHz Mono chuẩn)" if quality_score >= 80 else "Ổn định"

    return jsonify({
        'success': True,
        'filename': original_name,
        'audio_path': clean_sample_path,
        'relative_path': os.path.relpath(clean_sample_path, ROOT_DIR).replace("\\", "/"),
        'duration': round(duration, 2),
        'original_duration': round(meta.get('original_duration', duration), 2),
        'is_trimmed': meta.get('is_trimmed', False),
        'quality_score': quality_score,
        'quality_desc': quality_desc,
        'preview_url': f'/api/file?path={urllib.parse.quote(clean_sample_path)}'
    })

@tts_bp.route('/api/clone_voice/preview', methods=['POST'])
def api_clone_voice_preview():
    """
    Sinh thử âm thanh giọng đọc từ file mẫu để người dùng nghe thử trước khi lưu.
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_clone_voice')
    if not allowed:
        return jsonify({'success': False, 'error': perm_msg}), 403

    data = request.json or {}
    text = data.get('text', '').strip() or 'Xin chào! Đây là bản nghe thử chất lượng nhân bản giọng nói Local Voice.'
    audio_path = data.get('audio_path', '').strip()
    voice_id = data.get('voice_id', '').strip()
    speed = _safe_speed(data.get('speed', 1.0))

    if not audio_path and not voice_id:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp file âm thanh mẫu hoặc chọn giọng'}), 400

    if audio_path:
        if not os.path.isabs(audio_path):
            audio_path = os.path.join(ROOT_DIR, audio_path)
        if not is_path_allowed(audio_path, must_exist=True, extensions=_AUDIO_EXTENSIONS):
            return jsonify({'success': False, 'error': f'Không tìm thấy file âm thanh mẫu: {audio_path}'}), 400

    temp_out = safe_join(os.path.join(ROOT_DIR, "output"), f"preview_{uuid.uuid4().hex}.wav", extensions={'.wav'})
    try:
        import local_voice_engine
        local_voice_engine.synthesize(
            text=text,
            voice_id=voice_id or None,
            ref_audio=audio_path if audio_path else None,
            speed=speed,
            output_path=temp_out
        )
        return jsonify({
            'success': True,
            'audio_url': f'/api/file?path={urllib.parse.quote(temp_out)}',
            'output_path': temp_out
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@tts_bp.route('/api/clone_voice/save', methods=['POST'])
def api_clone_voice_save():
    """
    Lưu giọng clone vĩnh viễn vào Thư viện custom_voices.json và voices/local_clones/.
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('allow_save_cloned_voice')
    if not allowed:
        return jsonify({'success': False, 'error': perm_msg}), 403

    data = request.json or {}
    name = data.get('name', '').strip()
    audio_path = data.get('audio_path', '').strip()
    lang = data.get('lang', 'Vietnamese')
    gender = data.get('gender', 'Female')
    region = data.get('region', 'Miền Bắc')
    age = data.get('age', 'young')
    style = data.get('style', 'review')
    tag = data.get('tag', '').strip()
    avatar = data.get('avatar', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Vui lòng nhập tên giọng nói'}), 400
    if not audio_path:
        return jsonify({'success': False, 'error': 'Không tìm thấy file âm thanh mẫu'}), 400

    if not os.path.isabs(audio_path):
        audio_path = os.path.join(ROOT_DIR, audio_path)

    if not is_path_allowed(audio_path, must_exist=True, extensions=_AUDIO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'File âm thanh mẫu không tồn tại hoặc đã bị xóa'}), 400

    try:
        import local_voice_engine
        voice_profile = local_voice_engine.clone_voice(
            audio_file_path=audio_path,
            name=name,
            gender=gender,
            region=region,
            style=style,
            lang=lang,
            age=age,
            tag=tag or None,
            avatar=avatar or None
        )
        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                ref_p = voice_profile.get('ref_audio_path', audio_path) if isinstance(voice_profile, dict) else audio_path
                notifier.notify_task_success(
                    task_type='clone_voice',
                    task_title='Clone Voice Studio',
                    video_title=name,
                    output_path=ref_p,
                    extra_info={
                        'Mã định danh': voice_profile.get('id', '') if isinstance(voice_profile, dict) else '',
                        'Giới tính': gender,
                        'Vùng miền': region
                    }
                )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f'Đã lưu thành công giọng "{name}" vào Thư viện Local Voice!',
            'voice': voice_profile
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@tts_bp.route('/api/clone_voice/update', methods=['POST'])
def api_clone_voice_update():
    """
    Chỉnh sửa thông tin định danh của giọng clone trong thư viện.
    """
    permission_error = _require_media_access('allow_save_cloned_voice')
    if permission_error:
        return permission_error
    data = request.json or {}
    voice_id = data.get('voice_id', '').strip()
    if not voice_id:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp voice_id'}), 400

    import custom_voices
    existing = custom_voices.get_voice_by_id(voice_id)
    if not existing:
        return jsonify({'success': False, 'error': 'Không tìm thấy giọng nói trong thư viện'}), 404

    name = data.get('name', '').strip() or existing.get('name')
    final_name = name if (name.endswith('(Local Voice)') or name.endswith('(RVC)')) else f"{name} (Local Voice)"

    lang = data.get('lang', existing.get('lang', 'Vietnamese'))
    region = data.get('region', existing.get('region', 'Miền Bắc'))
    gender = data.get('gender', existing.get('gender', 'Female'))
    age = data.get('age', existing.get('age', 'young'))
    style = data.get('style', existing.get('style', 'review'))
    tag = data.get('tag', existing.get('tag', ''))
    avatar = data.get('avatar', existing.get('avatar', '👩' if gender == 'Female' else '👨'))

    updated_data = {
        'id': voice_id,
        'name': final_name,
        'lang': lang,
        'region': region,
        'gender': gender,
        'age': age,
        'style': style,
        'tag': tag or f"Local Voice • {region} • {gender}",
        'avatar': avatar
    }

    voice_profile = custom_voices.add_or_update_voice(updated_data)
    return jsonify({
        'success': True,
        'message': f'Đã cập nhật thông tin giọng "{final_name}" thành công!',
        'voice': voice_profile
    })

@tts_bp.route('/api/clone_voice/delete', methods=['POST'])
def api_clone_voice_delete():
    """
    Xóa một giọng clone khỏi thư viện.
    """
    permission_error = _require_media_access('allow_save_cloned_voice')
    if permission_error:
        return permission_error
    data = request.json or {}
    voice_id = data.get('voice_id', '').strip()
    if not voice_id:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp voice_id cần xóa'}), 400

    import custom_voices
    custom_voices.delete_voice(voice_id)
    return jsonify({'success': True, 'message': 'Đã xóa giọng khỏi thư viện thành công!'})


