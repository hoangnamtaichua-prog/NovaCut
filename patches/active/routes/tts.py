from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, urllib.parse, uuid, hashlib, wave, shutil
from routes.state import *
from routes.security import atomic_write_json, is_path_allowed, safe_join, sanitize_unicode_filename
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
_active_pregen_sessions = {}
_pregen_sessions_lock = threading.Lock()


def _format_srt_timecode(sec: float) -> str:
    """Chuyển đổi giây thành mốc thời gian SRT chuẩn HH:MM:SS,mmm"""
    total_ms = int(max(0, float(sec or 0.0)) * 1000)
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    seconds = (total_ms % 60000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def analyze_voice_timeline_overlaps(chunks: list) -> dict:
    """
    Phân tích chi tiết sự trùng đè thời gian (overlap) giữa các câu voice.
    Mỗi chunk gồm:
    - index: 1-based STT
    - start_seconds: thời điểm bắt đầu
    - duration: thời lượng file âm thanh thực tế
    - voice_end_seconds = start_seconds + duration
    """
    total = len(chunks)
    overlap_count = 0
    total_overlap_sec = 0.0

    for i in range(total):
        cur = chunks[i]
        cur_start = float(cur.get('start_seconds') if cur.get('start_seconds') is not None else cur.get('startSeconds', 0.0))
        cur_dur = float(cur.get('duration', 0.0))
        cur_end = round(cur_start + cur_dur, 3)
        cur['start_seconds'] = cur_start
        cur['voice_end_seconds'] = cur_end
        cur['start_timecode'] = _format_srt_timecode(cur_start)
        cur['end_timecode'] = _format_srt_timecode(cur_end)
        cur['srt_timecode'] = f"{cur['start_timecode']} --> {cur['end_timecode']}"

        cur['has_overlap'] = False
        cur['overlap_targets'] = []
        cur['overlap_duration'] = 0.0
        cur['gap_to_next'] = None
        if 'is_overlapped_by' not in cur:
            cur['is_overlapped_by'] = []

        if i < total - 1:
            next_chunk = chunks[i + 1]
            next_start = float(next_chunk.get('start_seconds') if next_chunk.get('start_seconds') is not None else next_chunk.get('startSeconds', 0.0))
            # Dung sai 0.05s tránh sai số float nhỏ
            if cur_end > next_start + 0.05:
                overlap_sec = round(cur_end - next_start, 2)
                cur['has_overlap'] = True
                cur['overlap_duration'] = overlap_sec
                cur['overlap_targets'].append({
                    'target_index': next_chunk.get('index', i + 2),
                    'target_id': next_chunk.get('id', i + 2),
                    'overlap_seconds': overlap_sec
                })
                overlap_count += 1
                total_overlap_sec += overlap_sec

                if 'is_overlapped_by' not in next_chunk:
                    next_chunk['is_overlapped_by'] = []
                next_chunk['is_overlapped_by'].append({
                    'source_index': cur.get('index', i + 1),
                    'source_id': cur.get('id', i + 1),
                    'overlap_seconds': overlap_sec
                })
            else:
                cur['gap_to_next'] = round(next_start - cur_end, 2)

    return {
        'total_chunks': total,
        'overlap_count': overlap_count,
        'total_overlap_duration': round(total_overlap_sec, 2),
        'has_any_overlap': overlap_count > 0,
        'clean_count': total - overlap_count,
        'overlap_ratio_percent': round((overlap_count / max(1, total)) * 100, 1)
    }


def build_voice_timeline_srt_text(chunks: list) -> str:
    """Tạo nội dung file SRT từ timeline voice thực tế kèm chú thích nếu trùng đè."""
    lines = []
    for item in chunks:
        idx = item.get('index', 1)
        st_srt = item.get('start_timecode') or _format_srt_timecode(item.get('start_seconds', 0.0))
        et_srt = item.get('end_timecode') or _format_srt_timecode(item.get('voice_end_seconds', 0.0))
        txt = str(item.get('text', '')).strip()
        lines.append(f"{idx}")
        lines.append(f"{st_srt} --> {et_srt}")
        if item.get('has_overlap'):
            ov_sec = item.get('overlap_duration', 0)
            target = item['overlap_targets'][0]['target_index'] if item.get('overlap_targets') else (idx + 1)
            lines.append(f"[⚠️ TRÙNG ĐÈ {ov_sec}s VỚI CÂU #{target}] {txt}")
        else:
            lines.append(f"{txt}")
        lines.append("")
    return "\n".join(lines)


@tts_bp.route('/api/tts/timeline_preview', methods=['POST'])
@tts_bp.route('/api/tts/timeline_generate_chunks', methods=['POST'])
def generate_timeline_preview():
    permission_error = _require_media_access()
    if permission_error:
        return permission_error
    try:
        import hashlib
        import math
        import wave
        import shutil
        import ai_dubbing
        from routes.video_edit import compute_tts_fingerprint, is_tts_manifest_valid, save_tts_manifest

        data = request.get_json() or {}
        subtitles = data.get('subtitles')
        if subtitles is None:
            subtitles = data.get('sentences')

        if not isinstance(subtitles, list) or not 0 < len(subtitles) <= 10000:
            raise ValueError('Danh sách phụ đề phải có từ 1 đến 10.000 câu.')

        speed = _safe_speed(data.get('speed', 1))
        voice = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id') or data.get('voice') or 'local_ngoc_huyen'))[:100]

        normalized = []
        for idx, sub in enumerate(subtitles):
            if isinstance(sub, (list, tuple)) and len(sub) >= 3:
                txt = str(sub[2]).strip()
                st = float(sub[0])
                et = float(sub[1])
                item_id = idx + 1
            elif isinstance(sub, dict):
                txt = str(sub.get('translation') or sub.get('text') or '').strip()
                st_val = sub.get('startSeconds')
                if st_val is None:
                    st_val = sub.get('time') if sub.get('time') is not None else sub.get('start', 0.0)
                st = float(st_val)
                et_val = sub.get('endSeconds')
                if et_val is None:
                    et_val = sub.get('end', st + 3.0)
                et = float(et_val)
                item_id = sub.get('id', idx + 1)
            else:
                continue

            if not all(math.isfinite(v) and 0 <= v <= 86400 for v in (st, et)):
                raise ValueError('Thời gian phụ đề không hợp lệ.')
            if et < st:
                raise ValueError('Thời gian kết thúc phải lớn hơn hoặc bằng thời gian bắt đầu.')
            if txt:
                normalized.append({
                    'id': item_id,
                    'index': idx,
                    'text': txt,
                    'startSeconds': st,
                    'endSeconds': et
                })

        if not normalized or sum(len(s['text']) for s in normalized) > 250000:
            raise ValueError('Phụ đề rỗng hoặc vượt quá 250.000 ký tự.')

        mode = str(data.get('mode', 'editor')).strip().lower()
        video_path = str(data.get('video_path') or '').strip()
        output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
        editor_temp_dir = str(data.get('editor_temp_dir') or '').strip()
        force_refresh = bool(data.get('force_refresh', False))

        video_duration = float(data.get('video_duration') or 0.0)
        if video_duration <= 0.0:
            video_duration = max((s['endSeconds'] for s in normalized), default=0.0)

        if editor_temp_dir and is_path_allowed(editor_temp_dir):
            target_dir = editor_temp_dir
        elif video_path:
            if mode == 'review':
                try:
                    import auto_edit_pipeline
                    target_dir = auto_edit_pipeline.get_review_temp_dir(output_dir, video_path)
                except Exception:
                    target_dir = os.path.join(output_dir, 'review_temp')
            else:
                try:
                    import ocr_module
                    target_dir = ocr_module.get_editor_temp_dir(output_dir, video_path)
                except Exception:
                    target_dir = os.path.join(output_dir, 'editor_temp')
        else:
            identity = json.dumps([normalized, voice, speed], ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
            target_dir = os.path.join(ROOT_DIR, 'temp', 'timeline_preview', digest)

        os.makedirs(target_dir, exist_ok=True)
        track = os.path.join(target_dir, 'dubbed_timeline.wav')
        tts_fingerprint = compute_tts_fingerprint(normalized, voice, speed, video_duration)

        with _timeline_preview_lock:
            need_synthesis = force_refresh or not is_tts_manifest_valid(target_dir, tts_fingerprint)
            if need_synthesis:
                key = ''
                if os.path.isfile(API_KEYS_FILE):
                    try:
                        with open(API_KEYS_FILE, encoding='utf-8') as stream:
                            for line in stream:
                                if line.startswith('openSpeakerApiKey='):
                                    key = line.split('=', 1)[1].strip()
                    except Exception:
                        pass
                errors = []
                output = None
                max_workers = data.get('max_workers')
                for kind, message in ai_dubbing.build_dubbing_track_for_subtitles_generator(
                        normalized, voice, speed, target_dir, open_speaker_key=key,
                        max_workers=max_workers):
                    if kind == 'done':
                        output = message
                    elif 'Lỗi câu #' in message or 'LỖI' in message or 'Lỗi xử lý:' in message:
                        errors.append(message)
                if not output or errors:
                    if os.path.isfile(track):
                        try:
                            os.remove(track)
                        except Exception:
                            pass
                    raise RuntimeError(errors[0] if errors else 'Không tạo được âm thanh nghe thử.')
                if output and output != track and os.path.isfile(output):
                    try:
                        shutil.copyfile(output, track)
                    except Exception:
                        track = output

            # Lưu manifest để video export tái sử dụng 0s
            save_tts_manifest(target_dir, tts_fingerprint, voice, speed, video_duration, len(normalized))

            if mode == 'review':
                for alias_name in ('voice_narration.wav', 'voice_review.wav'):
                    alias_path = os.path.join(target_dir, alias_name)
                    if track != alias_path and os.path.isfile(track):
                        try:
                            shutil.copyfile(track, alias_path)
                        except Exception:
                            pass

        # Thu thập metadata từng chunk cho Timeline UI
        chunks = []
        cached_count = 0
        generated_count = 0
        for item in normalized:
            ckey, cfile, is_loc = ai_dubbing.get_sentence_cache_info(item['text'], voice, speed)
            duration = round(item['endSeconds'] - item['startSeconds'], 3)
            is_cached = os.path.exists(cfile) and os.path.getsize(cfile) > 100
            if is_cached:
                cached_count += 1
                try:
                    with wave.open(cfile, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        if rate > 0:
                            duration = round(frames / float(rate), 3)
                except Exception:
                    pass
            else:
                generated_count += 1

            chunks.append({
                'id': item['id'],
                'index': item['index'],
                'text': item['text'],
                'startSeconds': item['startSeconds'],
                'endSeconds': item['endSeconds'],
                'duration': duration,
                'audio_url': f'/api/file?path={urllib.parse.quote(cfile)}',
                'cached': is_cached,
                'hash_key': ckey
            })

        overlap_summary = analyze_voice_timeline_overlaps(chunks)
        srt_content = build_voice_timeline_srt_text(chunks)
        srt_path = os.path.join(target_dir, 'voice_timeline.srt')
        try:
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
        except Exception:
            pass

        timeline_manifest_path = os.path.join(target_dir, 'timeline_audio_manifest.json')
        try:
            with open(timeline_manifest_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'fingerprint': tts_fingerprint,
                    'voice_id': voice,
                    'speed': speed,
                    'video_duration': video_duration,
                    'overlap_summary': overlap_summary,
                    'chunks': chunks
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to save timeline_audio_manifest: {e}")

        master_url = '/api/file?path=' + urllib.parse.quote(track)
        return jsonify(
            success=True,
            audio_url=master_url,
            master_track_url=master_url,
            master_track_path=track,
            manifest_path=os.path.join(target_dir, 'tts_manifest.json'),
            srt_path=srt_path,
            srt_content=srt_content,
            chunks=chunks,
            total_chunks=len(chunks),
            cached_count=cached_count,
            generated_count=generated_count,
            overlap_summary=overlap_summary,
            fingerprint=tts_fingerprint,
            total_duration=video_duration
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 500


@tts_bp.route('/api/tts/pregenerate_stream', methods=['POST'])
def pregenerate_voice_stream():
    """
    Tạo voice trước khi xuất video theo cơ chế SSE streaming thời gian thực.
    Tự động đo thời lượng âm thanh từng câu, đối soát trùng lặp thời gian SRT,
    và lưu bản voice hoàn chỉnh sẵn sàng tái sử dụng 100% (0s) khi xuất video.
    """
    permission_error = _require_media_access('can_access_editor')
    if permission_error:
        return permission_error

    data = request.get_json(silent=True) or {}
    session_id = str(data.get('session_id') or uuid.uuid4())
    subtitles = data.get('subtitles') or data.get('sentences') or []
    if not isinstance(subtitles, list) or not subtitles:
        return jsonify({'type': 'error', 'message': 'Danh sách phụ đề trống'}), 400

    cancel_event = threading.Event()
    with _pregen_sessions_lock:
        _active_pregen_sessions[session_id] = cancel_event

    def generate():
        try:
            import auto_edit_pipeline
            import ai_dubbing
            from routes.video_edit import compute_tts_fingerprint, is_tts_manifest_valid, save_tts_manifest

            speed = _safe_speed(data.get('speed', 1.1))
            voice = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id') or data.get('voice') or 'local_minh_duc'))[:100]
            video_path = str(data.get('video_path') or '').strip()
            output_dir = _safe_output_dir(data.get('output_dir'))
            force_refresh = bool(data.get('force_refresh', False))
            threads = int(data.get('threads') or 16)
            if threads <= 0:
                threads = 16

            # Chuẩn hóa danh sách câu phụ đề
            normalized = []
            for idx, sub in enumerate(subtitles):
                if isinstance(sub, (list, tuple)) and len(sub) >= 3:
                    txt = str(sub[2]).strip()
                    st = float(sub[0])
                    et = float(sub[1])
                    item_id = idx + 1
                elif isinstance(sub, dict):
                    txt = str(sub.get('translation') or sub.get('text') or '').strip()
                    st_val = sub.get('startSeconds')
                    if st_val is None:
                        st_val = sub.get('time') if sub.get('time') is not None else sub.get('start', 0.0)
                    st = float(st_val)
                    et_val = sub.get('endSeconds')
                    if et_val is None:
                        et_val = sub.get('end', st + 3.0)
                    et = float(et_val)
                    item_id = sub.get('id', idx + 1)
                else:
                    continue

                if txt:
                    normalized.append({
                        'id': item_id,
                        'index': idx + 1,
                        'text': txt,
                        'startSeconds': st,
                        'endSeconds': et
                    })

            if not normalized:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Không tìm thấy câu phụ đề hợp lệ nào để tạo giọng.'}, ensure_ascii=False)}\n\n"
                return

            video_duration = float(data.get('video_duration') or 0.0)
            if video_duration <= 0.0:
                video_duration = max((s['endSeconds'] for s in normalized), default=0.0)

            import ocr_module
            target_dir = ocr_module.get_editor_temp_dir(output_dir, video_path)
            os.makedirs(target_dir, exist_ok=True)
            track = os.path.join(target_dir, 'dubbed_timeline.wav')
            tts_fingerprint = compute_tts_fingerprint(normalized, voice, speed, video_duration)

            yield f"data: {json.dumps({'type': 'progress', 'percent': 2, 'message': f'🎙️ Bắt đầu chuẩn bị tạo giọng cho {len(normalized)} câu (Giọng: {voice} | {speed}x)...', 'current': 0, 'total': len(normalized)}, ensure_ascii=False)}\n\n"

            # Kiểm tra xem đã có bản voice hoàn chỉnh hợp lệ sẵn chưa
            need_synthesis = force_refresh or not is_tts_manifest_valid(target_dir, tts_fingerprint) or not os.path.exists(track) or os.path.getsize(track) <= 1000

            if not need_synthesis:
                yield f"data: {json.dumps({'type': 'log', 'message': '💚 Tìm thấy bản voice hoàn chỉnh từ lần tạo trước khớp 100% kịch bản, đang nạp dữ liệu...'}, ensure_ascii=False)}\n\n"
                output_dubbed_track = track
            else:
                key = ''
                if os.path.isfile(API_KEYS_FILE):
                    try:
                        with open(API_KEYS_FILE, encoding='utf-8') as stream:
                            for line in stream:
                                if line.startswith('openSpeakerApiKey='):
                                    key = line.split('=', 1)[1].strip()
                    except Exception:
                        pass

                temp_dub_dir = os.path.join(target_dir, 'dubbing_temp')
                os.makedirs(temp_dub_dir, exist_ok=True)
                output_dubbed_track = None

                for kind, message in ai_dubbing.build_dubbing_track_for_subtitles_generator(
                    subtitles=normalized,
                    voice_id=voice,
                    speed=speed,
                    temp_dir=temp_dub_dir,
                    open_speaker_key=key,
                    min_total_duration=video_duration,
                    max_workers=threads,
                    check_stop=lambda: cancel_event.is_set()
                ):
                    if cancel_event.is_set():
                        yield f"data: {json.dumps({'type': 'canceled', 'message': 'Đã dừng tiến trình tạo voice theo yêu cầu.'}, ensure_ascii=False)}\n\n"
                        return

                    if kind == 'progress':
                        pct_match = re.search(r'\((\d+)%\)', message)
                        cnt_match = re.search(r'Tiến độ (\d+)/(\d+)', message)
                        cur_pct = int(pct_match.group(1)) if pct_match else 20
                        cur_cnt = int(cnt_match.group(1)) if cnt_match else 0
                        total_cnt = int(cnt_match.group(2)) if cnt_match else len(normalized)

                        yield f"data: {json.dumps({'type': 'progress', 'percent': cur_pct, 'message': message, 'current': cur_cnt, 'total': total_cnt}, ensure_ascii=False)}\n\n"
                    elif kind == 'done':
                        output_dubbed_track = message

                if cancel_event.is_set():
                    yield f"data: {json.dumps({'type': 'canceled', 'message': 'Đã dừng tiến trình tạo voice theo yêu cầu.'}, ensure_ascii=False)}\n\n"
                    return

                if not output_dubbed_track or not os.path.exists(output_dubbed_track):
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Không thể tạo bản voice TTS hoàn chỉnh. Vui lòng kiểm tra lại giọng đọc hoặc API key.'}, ensure_ascii=False)}\n\n"
                    return

                if output_dubbed_track != track:
                    try:
                        shutil.copyfile(output_dubbed_track, track)
                    except Exception:
                        pass

                # Lưu tts_manifest.json để Video Export tái sử dụng 100% (0s)
                save_tts_manifest(target_dir, tts_fingerprint, voice, speed, video_duration, len(normalized))

            # Đo đạc thời lượng thực tế của từng câu từ file WAV và phân tích Overlap
            yield f"data: {json.dumps({'type': 'progress', 'percent': 95, 'message': '📊 Đang đo đạc thời gian từng câu và phân tích trùng lặp dòng thời gian...', 'current': len(normalized), 'total': len(normalized)}, ensure_ascii=False)}\n\n"

            chunks = []
            for item in normalized:
                ckey, cfile, is_loc = ai_dubbing.get_sentence_cache_info(item['text'], voice, speed)
                actual_duration = 0.0
                try:
                    if os.path.exists(cfile) and os.path.getsize(cfile) > 100:
                        with wave.open(cfile, 'rb') as wf:
                            frames = wf.getnframes()
                            rate = wf.getframerate()
                            if rate > 0:
                                actual_duration = round(frames / float(rate), 3)
                except Exception:
                    pass
                if actual_duration <= 0.0:
                    actual_duration = max(0.5, round(item['endSeconds'] - item['startSeconds'], 3))

                chunks.append({
                    'id': item['id'],
                    'index': item['index'],
                    'text': item['text'],
                    'start_seconds': item['startSeconds'],
                    'sub_end_seconds': item['endSeconds'],
                    'duration': actual_duration,
                    'audio_url': f'/api/file?path={urllib.parse.quote(cfile)}',
                    'audio_path': cfile
                })

            overlap_summary = analyze_voice_timeline_overlaps(chunks)
            srt_content = build_voice_timeline_srt_text(chunks)

            # Lưu file SRT và timeline audio manifest
            srt_path = os.path.join(target_dir, 'voice_timeline.srt')
            try:
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
            except Exception:
                pass

            timeline_manifest_path = os.path.join(target_dir, 'timeline_audio_manifest.json')
            try:
                with open(timeline_manifest_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'fingerprint': tts_fingerprint,
                        'voice_id': voice,
                        'speed': speed,
                        'video_duration': video_duration,
                        'overlap_summary': overlap_summary,
                        'chunks': chunks
                    }, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            master_url = f'/api/file?path={urllib.parse.quote(track)}'

            complete_evt = {
                'type': 'complete',
                'success': True,
                'audio_url': master_url,
                'master_track_url': master_url,
                'master_track_path': track,
                'srt_path': srt_path,
                'srt_content': srt_content,
                'voice_id': voice,
                'speed': speed,
                'fingerprint': tts_fingerprint,
                'total_duration': video_duration,
                'chunks': chunks,
                'overlap_summary': overlap_summary,
                'message': '🎉 Đã tạo xong voice và phân tích dòng thời gian SRT thành công!'
            }
            yield f"data: {json.dumps(complete_evt, ensure_ascii=False)}\n\n"

        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': f'Lỗi tạo voice: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            with _pregen_sessions_lock:
                _active_pregen_sessions.pop(session_id, None)

    return Response(generate(), mimetype='text/event-stream')


@tts_bp.route('/api/tts/cancel_pregenerate', methods=['POST'])
def cancel_pregenerate_voice():
    """Hủy tiến trình tạo voice trước khi xuất"""
    data = request.get_json(silent=True) or {}
    session_id = str(data.get('session_id') or '').strip()
    with _pregen_sessions_lock:
        if session_id and session_id in _active_pregen_sessions:
            _active_pregen_sessions[session_id].set()
            return jsonify({'success': True, 'message': 'Đã gửi tín hiệu dừng tiến trình tạo voice'})
        elif not session_id:
            for s_id, ev in list(_active_pregen_sessions.items()):
                ev.set()
            return jsonify({'success': True, 'message': 'Đã gửi tín hiệu dừng tất cả tiến trình tạo voice'})
    return jsonify({'success': True, 'message': 'Không tìm thấy tiến trình đang chạy'})


@tts_bp.route('/api/tts/export_timeline_srt', methods=['POST'])
def export_timeline_srt():
    """Tải xuống tệp phụ đề SRT dòng thời gian voice"""
    data = request.get_json(silent=True) or {}
    srt_content = str(data.get('srt_content') or '').strip()
    if not srt_content:
        return jsonify({'success': False, 'error': 'Nội dung SRT rỗng'}), 400
    from flask import Response
    return Response(
        srt_content,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment;filename=voice_timeline.srt"}
    )


@tts_bp.route('/api/tts/get_timeline_manifest', methods=['POST'])
def get_timeline_manifest():
    """Lấy dữ liệu timeline voice và phân tích trùng lặp đã lưu trong thư mục tạm"""
    try:
        data = request.get_json(silent=True) or {}
        video_path = str(data.get('video_path') or '').strip()
        output_dir = _safe_output_dir(data.get('output_dir'))
        import ocr_module
        target_dir = ocr_module.get_editor_temp_dir(output_dir, video_path)
        manifest_path = os.path.join(target_dir, 'timeline_audio_manifest.json')
        track_path = os.path.join(target_dir, 'dubbed_timeline.wav')
        srt_path = os.path.join(target_dir, 'voice_timeline.srt')

        if not os.path.exists(manifest_path) or not os.path.exists(track_path):
            return jsonify({'success': False, 'has_manifest': False}), 200

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)

        srt_content = ''
        if os.path.exists(srt_path):
            with open(srt_path, 'r', encoding='utf-8') as f:
                srt_content = f.read()

        master_url = f'/api/file?path={urllib.parse.quote(track_path)}'
        return jsonify({
            'success': True,
            'has_manifest': True,
            'audio_url': master_url,
            'master_track_url': master_url,
            'master_track_path': track_path,
            'srt_path': srt_path,
            'srt_content': srt_content,
            'voice_id': manifest_data.get('voice_id', ''),
            'speed': manifest_data.get('speed', 1.1),
            'fingerprint': manifest_data.get('fingerprint', ''),
            'total_duration': manifest_data.get('video_duration', 0.0),
            'chunks': manifest_data.get('chunks', []),
            'overlap_summary': manifest_data.get('overlap_summary', {})
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@tts_bp.route('/api/tts/restitch_timeline', methods=['POST'])
def restitch_timeline():
    """Tái ghép nối file âm thanh dubbed_timeline.wav sau khi điều chỉnh mốc thời gian SRT (0 TTS token/API call, tái sử dụng 100% WAV cache)"""
    permission_error = _require_media_access()
    if permission_error:
        return permission_error
    try:
        data = request.get_json(silent=True) or {}
        subtitles = data.get('subtitles') or []
        video_path = str(data.get('video_path') or '').strip()
        output_dir = _safe_output_dir(data.get('output_dir'))
        voice = str(data.get('voice_id') or '').strip()
        speed = _safe_speed(data.get('speed', 1.1))

        if not subtitles or not isinstance(subtitles, list):
            return jsonify({'success': False, 'error': 'Dữ liệu phụ đề rỗng'}), 400

        import ocr_module
        import ai_dubbing
        import wave
        import shutil
        from routes.video_edit import compute_tts_fingerprint, save_tts_manifest

        target_dir = ocr_module.get_editor_temp_dir(output_dir, video_path)
        manifest_path = os.path.join(target_dir, 'timeline_audio_manifest.json')
        if not voice and os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    old_manifest = json.load(f)
                    voice = old_manifest.get('voice_id', voice)
                    speed = old_manifest.get('speed', speed)
            except Exception:
                pass

        if not voice:
            voice = 'local_clone_1787245769140'

        normalized = []
        for idx, sub in enumerate(subtitles):
            txt = str(sub.get('translation') or sub.get('text') or '').strip()
            st = float(sub.get('startSeconds') if sub.get('startSeconds') is not None else 0.0)
            et = float(sub.get('endSeconds') if sub.get('endSeconds') is not None else st + 2.0)
            normalized.append({
                'id': sub.get('id', idx + 1),
                'index': idx + 1,
                'startSeconds': st,
                'endSeconds': et,
                'text': txt
            })

        video_duration = max((s['endSeconds'] for s in normalized), default=0.0)
        tts_fingerprint = compute_tts_fingerprint(normalized, voice, speed, video_duration)
        temp_dub_dir = os.path.join(target_dir, 'dubbing_temp')
        track = os.path.join(target_dir, 'dubbed_timeline.wav')

        # Ghép nối master track từ các file WAV từng câu đã được tạo sẵn trong cache
        output_dubbed_track = None
        for kind, message in ai_dubbing.build_dubbing_track_for_subtitles_generator(
            subtitles=normalized,
            voice_id=voice,
            speed=speed,
            temp_dir=temp_dub_dir,
            min_total_duration=video_duration,
            max_workers=16,
            check_stop=lambda: False
        ):
            if kind == 'done':
                output_dubbed_track = message

        if output_dubbed_track and os.path.exists(output_dubbed_track) and output_dubbed_track != track:
            try:
                shutil.copyfile(output_dubbed_track, track)
            except Exception:
                pass

        save_tts_manifest(target_dir, tts_fingerprint, voice, speed, video_duration, len(normalized))

        # Đo đạc thời lượng thực tế và phân tích lại trùng đè
        chunks = []
        for item in normalized:
            ckey, cfile, is_loc = ai_dubbing.get_sentence_cache_info(item['text'], voice, speed)
            actual_duration = 0.0
            try:
                if os.path.exists(cfile) and os.path.getsize(cfile) > 100:
                    with wave.open(cfile, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        if rate > 0:
                            actual_duration = round(frames / float(rate), 3)
            except Exception:
                pass
            if actual_duration <= 0.0:
                actual_duration = max(0.5, round(item['endSeconds'] - item['startSeconds'], 3))

            chunks.append({
                'id': item['id'],
                'index': item['index'],
                'text': item['text'],
                'start_seconds': item['startSeconds'],
                'sub_end_seconds': item['endSeconds'],
                'duration': actual_duration,
                'audio_url': f'/api/file?path={urllib.parse.quote(cfile)}',
                'audio_path': cfile
            })

        overlap_summary = analyze_voice_timeline_overlaps(chunks)
        srt_content = build_voice_timeline_srt_text(chunks)

        # Lưu file SRT và timeline audio manifest
        srt_path = os.path.join(target_dir, 'voice_timeline.srt')
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)

        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump({
                'fingerprint': tts_fingerprint,
                'voice_id': voice,
                'speed': speed,
                'video_duration': video_duration,
                'overlap_summary': overlap_summary,
                'chunks': chunks
            }, f, indent=2, ensure_ascii=False)

        master_url = f'/api/file?path={urllib.parse.quote(track)}'
        return jsonify({
            'success': True,
            'audio_url': master_url,
            'master_track_url': master_url,
            'chunks': chunks,
            'overlap_summary': overlap_summary,
            'srt_content': srt_content,
            'fingerprint': tts_fingerprint
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
            
        if TTS_SAMPLE_DIR != os.path.join(USER_DATA_DIR, 'samples'):
            cache_dir = os.path.join(TTS_SAMPLE_DIR, 'tts_cache')
            os.makedirs(cache_dir, exist_ok=True)
            hash_key = hashlib.md5(f"{voice_id}_{speed}_{text}".encode('utf-8')).hexdigest()
            cache_path = os.path.join(cache_dir, f"{hash_key}.wav")
            is_local = voice_id.startswith('local_')
        else:
            import ai_dubbing
            hash_key, cache_path, is_local = ai_dubbing.get_sentence_cache_info(text, voice_id, speed)
        
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
            return jsonify({
                'success': True,
                'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
                'cached': True,
                'hash_key': hash_key
            })
            
        open_speaker_key = ''
        if os.path.isfile(API_KEYS_FILE):
            try:
                with open(API_KEYS_FILE, encoding='utf-8') as stream:
                    for line in stream:
                        if line.startswith('openSpeakerApiKey='):
                            open_speaker_key = line.split('=', 1)[1].strip()
            except Exception:
                pass

        ai_dubbing.synthesize_sentence(
            text, voice_id, speed, cache_path,
            open_speaker_key=open_speaker_key,
            target_sample_rate=44100, target_channels=2
        )
        
        return jsonify({
            'success': True,
            'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
            'cached': False,
            'hash_key': hash_key
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

        import ai_dubbing
        results = []
        to_synthesize = []
        is_sample_dir_patched = (TTS_SAMPLE_DIR != os.path.join(USER_DATA_DIR, 'samples'))
        if is_sample_dir_patched:
            test_cache_dir = os.path.join(TTS_SAMPLE_DIR, 'tts_cache')
            os.makedirs(test_cache_dir, exist_ok=True)

        for item in sentences:
            if isinstance(item, str):
                item = {'text': item}
            raw_text = str(item.get('text', '')).strip()
            item_id = item.get('id', item.get('index'))
            if not raw_text:
                continue

            if is_sample_dir_patched:
                hash_key = hashlib.md5(f"{voice_id}_{speed}_{raw_text}".encode('utf-8')).hexdigest()
                cache_path = os.path.join(test_cache_dir, f"{hash_key}.wav")
                is_local_item = voice_id.startswith('local_')
            else:
                hash_key, cache_path, is_local_item = ai_dubbing.get_sentence_cache_info(raw_text, voice_id, speed)

            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
                results.append({
                    'id': item_id,
                    'text': raw_text,
                    'audio_url': f'/api/file?path={urllib.parse.quote(cache_path)}',
                    'cached': True,
                    'hash_key': hash_key,
                    'success': True
                })
            else:
                to_synthesize.append({
                    'id': item_id,
                    'text': raw_text,
                    'cache_path': cache_path,
                    'hash_key': hash_key
                })

        if to_synthesize:
            is_local = voice_id.startswith('local_')
            if is_local:
                import local_voice_engine
                batch_items = [{'id': task['id'], 'text': task['text'], 'output_path': task['cache_path']} for task in to_synthesize]
                b_results = local_voice_engine.synthesize_batch(
                    batch_items, voice_id=voice_id, speed=speed,
                    target_sample_rate=44100, target_channels=2, batch_size=8
                )
                for task, res in zip(to_synthesize, b_results):
                    if res.get('success') and os.path.exists(task['cache_path']) and os.path.getsize(task['cache_path']) > 100:
                        results.append({
                            'id': task['id'],
                            'text': task['text'],
                            'audio_url': f"/api/file?path={urllib.parse.quote(task['cache_path'])}",
                            'cached': False,
                            'hash_key': task.get('hash_key'),
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
                from concurrent.futures import ThreadPoolExecutor

                open_speaker_key = ''
                if os.path.isfile(API_KEYS_FILE):
                    try:
                        with open(API_KEYS_FILE, encoding='utf-8') as stream:
                            for line in stream:
                                if line.startswith('openSpeakerApiKey='):
                                    open_speaker_key = line.split('=', 1)[1].strip()
                    except Exception:
                        pass

                def _synth(task):
                    try:
                        ai_dubbing.synthesize_sentence(
                            task['text'], voice_id, speed, task['cache_path'],
                            open_speaker_key=open_speaker_key,
                            target_sample_rate=44100, target_channels=2
                        )
                        return {
                            'id': task['id'],
                            'text': task['text'],
                            'audio_url': f"/api/file?path={urllib.parse.quote(task['cache_path'])}",
                            'cached': False,
                            'hash_key': task.get('hash_key'),
                            'success': True
                        }
                    except Exception as ex:
                        return {
                            'id': task['id'],
                            'text': task['text'],
                            'error': str(ex),
                            'success': False
                        }

                max_workers = min(16, len(to_synthesize))
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
    Hỗ trợ cả tag [pause Xs], lời thoại trong ngoặc kép (“...”, "..."),
    và tự động ngắt các câu quá dài (> 150-180 ký tự) tại dấu phẩy/chấm phẩy/khoảng trắng
    để tối ưu cho các dự án audio truyện dài (30p đến 1 tiếng), tránh quá tải phonemizer hoặc lỗi TTS.
    """
    pause_pattern = re.compile(r'\[pause(?:\s+([\d\.]+)\s*s?)?\]', re.IGNORECASE)
    parts = pause_pattern.split(text)
    
    # Pattern tách câu chuẩn xác bao gồm cả dấu câu sau ngoặc kép đóng:
    # "Câu nói!" hoặc “Câu nói?” hoặc [câu nói.]
    sentence_split_pattern = re.compile(r'(?<=[.!?…\n][\x22\x27\u201d\u2019»])\s+|(?<=[.!?…\n])\s+')

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
            raw_sentences = [s.strip() for s in sentence_split_pattern.split(part) if s.strip()]
            
            # Ghép các câu quá ngắn (< 35 ký tự) liền kề để tạo câu thoại tự nhiên và tăng tốc xử lý
            coalesced_sentences = []
            buf = ""
            for s in raw_sentences:
                if not buf:
                    buf = s
                elif len(buf) < 35 and (len(buf) + len(s) + 1 <= 140):
                    buf += " " + s
                else:
                    coalesced_sentences.append(buf)
                    buf = s
            if buf:
                coalesced_sentences.append(buf)

            # Sub-split cho câu quá dài (> 160 ký tự) đặc thù truyện dài / văn xuôi
            safe_sentences = []
            for s in coalesced_sentences:
                if len(s) <= 170:
                    safe_sentences.append((s, default_pause))
                else:
                    # Thử tách theo dấu phẩy, chấm phẩy, hai chấm, gạch ngang
                    sub_parts = [sp.strip() for sp in re.split(r'(?<=[,;:—–])\s+', s) if sp.strip()]
                    cur_chunk = ""
                    for sp in sub_parts:
                        if not cur_chunk:
                            cur_chunk = sp
                        elif len(cur_chunk) + len(sp) + 1 <= 160:
                            cur_chunk += " " + sp
                        else:
                            safe_sentences.append((cur_chunk, 0.25))
                            cur_chunk = sp
                    if cur_chunk:
                        # Nếu chunk đơn vẫn quá dài > 180 ký tự (không có cả dấu phẩy)
                        if len(cur_chunk) > 180:
                            words = cur_chunk.split()
                            w_chunk = []
                            for w in words:
                                w_chunk.append(w)
                                if len(" ".join(w_chunk)) >= 130:
                                    safe_sentences.append((" ".join(w_chunk), 0.25))
                                    w_chunk = []
                            if w_chunk:
                                safe_sentences.append((" ".join(w_chunk), default_pause))
                        else:
                            safe_sentences.append((cur_chunk, default_pause))

            for s_text, p_dur in safe_sentences:
                segments.append(('speech', s_text))
                if p_dur > 0:
                    segments.append(('pause', p_dur))

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


def generate_tts_stream_internal(req_data):
    """
    Tạo giọng đọc AI TTS với báo cáo tiến độ thời gian thực (Server-Sent Events).
    Báo cáo chính xác từng câu thoại, phần trăm hoàn thành thực tế và trạng thái xử lý.
    """
    try:
        import license_manager
        voice_id = req_data.get('voice') or req_data.get('voice_id') or 'local_ngoc_huyen'
        is_local_or_free = (
            voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_heart', 'en_michael', 'en_nicole', 'kokoro'] 
            or voice_id.startswith(('edge_', 'rvc_', 'local_'))
        )
        required_feature = 'tts_unlimited_local' if is_local_or_free else 'online_voices_enabled'
        allowed, perm_msg, _ = license_manager.check_permission(required_feature)
        if not allowed:
            yield f"data: {json.dumps({'type': 'error', 'error': perm_msg, 'message': perm_msg}, ensure_ascii=False)}\n\n"
            return

        text = req_data.get('text', '').strip()
        speed = _safe_speed(req_data.get('speed', 1.0))
        output_dir = _safe_output_dir(req_data.get('output_dir'))
        filename = req_data.get('filename')
        api_key = req_data.get('api_key')
        
        if not text:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Văn bản kịch bản trống', 'message': 'Văn bản kịch bản trống'}, ensure_ascii=False)}\n\n"
            return

        max_chars = 1000000 if is_local_or_free else 250000
        if len(text) > max_chars:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Kịch bản vượt quá {max_chars:,} ký tự', 'message': f'Kịch bản vượt quá {max_chars:,} ký tự'}, ensure_ascii=False)}\n\n"
            return

        if not is_local_or_free and not api_key:
            if os.path.exists(API_KEYS_FILE):
                try:
                    with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('openSpeakerApiKey='):
                                api_key = line.split('=', 1)[1].strip()
                except Exception:
                    pass
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Vui lòng cung cấp OpenSpeaker API Key', 'message': 'Vui lòng cung cấp OpenSpeaker API Key'}, ensure_ascii=False)}\n\n"
                return

        timestamp = int(time.time() * 1000)
        clean_vid = re.sub(r'[^a-zA-Z0-9_]', '_', voice_id)
        if not filename:
            filename = f"tts_{clean_vid}_{timestamp}.wav"
        filename = sanitize_unicode_filename(str(filename), default_ext='.wav')
        if not (filename.endswith('.wav') or filename.endswith('.mp3')):
            filename += '.wav'
            
        audio_path = safe_join(output_dir, filename, extensions={'.wav', '.mp3'})
        srt_filename = filename.rsplit('.', 1)[0] + '.srt'
        srt_path = os.path.join(output_dir, srt_filename)

        yield f"data: {json.dumps({'type': 'progress', 'percent': 5, 'message': '📝 Đang chuẩn hóa văn bản kịch bản...', 'current': 0, 'total': 0}, ensure_ascii=False)}\n\n"

        import ai_dubbing
        import soundfile as sf
        import numpy as np
        from concurrent.futures import ThreadPoolExecutor, as_completed

        segments = parse_text_into_speech_segments(text, default_pause=0.5)
        speech_segments = [s for s in segments if s[0] == 'speech']
        total_sentences = len(speech_segments)

        if total_sentences <= 1:
            raw_text = speech_segments[0][1] if speech_segments else text
            sent_preview = raw_text[:35] + ('...' if len(raw_text) > 35 else '')

            target_sr = 48000 if not voice_id.startswith('edge_') else 24000
            c_key, c_file, _ = ai_dubbing.get_sentence_cache_info(raw_text, voice_id, speed, target_sample_rate=target_sr, target_channels=1)
            if os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                yield f"data: {json.dumps({'type': 'progress', 'percent': 50, 'message': f'⚡ Đã nạp tức thì từ bộ nhớ đệm Cache: \"{sent_preview}\"', 'current': 1, 'total': 1}, ensure_ascii=False)}\n\n"
                try:
                    shutil.copyfile(c_file, audio_path)
                except Exception:
                    pass
            else:
                yield f"data: {json.dumps({'type': 'progress', 'percent': 15, 'message': f'🎙️ Đang tổng hợp giọng đọc: \"{sent_preview}\"', 'current': 0, 'total': 1}, ensure_ascii=False)}\n\n"
                ai_dubbing.synthesize_sentence(raw_text, voice_id, speed, audio_path, open_speaker_key=api_key)
                if os.path.exists(audio_path) and os.path.getsize(audio_path) > 100:
                    try:
                        shutil.copyfile(audio_path, c_file)
                    except Exception:
                        pass

            yield f"data: {json.dumps({'type': 'progress', 'percent': 75, 'message': '📊 Đang đo thời lượng âm thanh và cấu trúc sóng âm...', 'current': 1, 'total': 1}, ensure_ascii=False)}\n\n"
            
            duration = 1.0
            try:
                with sf.SoundFile(audio_path) as f:
                    duration = len(f) / float(f.samplerate)
            except Exception:
                try:
                    import ffmpeg_installer
                    ff = ffmpeg_installer.get_ffmpeg_path()
                    p = subprocess.run([ff, '-i', audio_path], stderr=subprocess.PIPE, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                    m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', p.stderr)
                    if m:
                        duration = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                except Exception:
                    pass

            yield f"data: {json.dumps({'type': 'progress', 'percent': 90, 'message': '⏱️ Đang đồng bộ mốc thời gian và ghi tệp phụ đề SRT...', 'current': 1, 'total': 1}, ensure_ascii=False)}\n\n"

            srt_content = f"1\n{sec_to_srt_time(0.0)} --> {sec_to_srt_time(duration)}\n{raw_text}\n"
            with open(srt_path, 'w', encoding='utf-8') as srt_f:
                srt_f.write(srt_content)
        else:
            yield f"data: {json.dumps({'type': 'progress', 'percent': 10, 'message': f'🎙️ Đã phân tích {total_sentences} câu thoại. Đang kiểm tra bộ đệm và chuẩn bị tổng hợp...', 'current': 0, 'total': total_sentences}, ensure_ascii=False)}\n\n"

            is_edge = voice_id.startswith('edge_')
            is_online_api = (not is_edge and bool(api_key) and not voice_id.startswith(('local_', 'kokoro_', 'rvc_')) and voice_id not in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_adam', 'adam', 'kokoro', 'kokoro_am_adam', 'local_adam'])
            is_gpu_voice = not is_edge and not is_online_api
            target_sr = 48000 if is_gpu_voice else 24000

            speech_tasks = []
            speech_idx = 1
            for seg_type, val in segments:
                if seg_type == 'speech':
                    chunk_wav = os.path.join(output_dir, f"temp_chunk_{timestamp}_{speech_idx}.wav")
                    speech_tasks.append((speech_idx, val, chunk_wav))
                    speech_idx += 1

            chunk_results = {}
            cache_hits = 0
            uncached_tasks = []

            # 1. Kiểm tra bộ nhớ đệm Sentence Cache (0ms instant hit)
            for s_idx, val, chunk_wav in speech_tasks:
                c_key, c_file, _ = ai_dubbing.get_sentence_cache_info(val, voice_id, speed, target_sample_rate=target_sr, target_channels=1)
                if os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                    chunk_results[s_idx] = (c_file, None)
                    cache_hits += 1
                else:
                    uncached_tasks.append((s_idx, val, chunk_wav, c_file))

            if cache_hits > 0:
                cache_pct = 10 + int((cache_hits / total_sentences) * 75)
                yield f"data: {json.dumps({'type': 'progress', 'percent': cache_pct, 'message': f'⚡ Đã nạp tức thì {cache_hits}/{total_sentences} câu từ bộ nhớ đệm Cache...', 'current': cache_hits, 'total': total_sentences}, ensure_ascii=False)}\n\n"

            # 2. Xử lý các câu chưa có trong Cache
            if uncached_tasks:
                if is_gpu_voice:
                    import local_voice_engine
                    batch_items = [{'id': s_idx, 'text': val, 'output_path': c_file} for s_idx, val, c_file, cache_f in uncached_tasks]

                    # Kích thước sub-batch tối ưu cho RTX 5060 (8-16 câu cùng lúc)
                    SUB_BATCH = 12 if len(batch_items) >= 24 else 8
                    done_count = cache_hits

                    for b_start in range(0, len(batch_items), SUB_BATCH):
                        sub_items = batch_items[b_start:b_start + SUB_BATCH]
                        sub_tasks = uncached_tasks[b_start:b_start + SUB_BATCH]
                        try:
                            sub_res = local_voice_engine.synthesize_batch(
                                sub_items,
                                voice_id=voice_id,
                                speed=speed,
                                batch_size=len(sub_items),
                                target_sample_rate=target_sr,
                                target_channels=1
                            )
                        except Exception as bex:
                            sub_res = [bex] * len(sub_items)

                        if not isinstance(sub_res, list):
                            sub_res = [sub_res] if sub_res is not None else []

                        for (s_idx, val, c_file, cache_f), r in zip(sub_tasks, sub_res):
                            err = None
                            if isinstance(r, dict):
                                if not r.get('success', False):
                                    err = r.get('error') or 'Lỗi tạo audio GPU'
                            elif isinstance(r, Exception):
                                err = str(r)
                            elif r is not None and not isinstance(r, (dict, list)):
                                err = str(r)

                            if not err and os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                                try:
                                    shutil.copyfile(c_file, cache_f)
                                except Exception:
                                    pass
                                chunk_results[s_idx] = (c_file, None)
                            else:
                                chunk_results[s_idx] = (c_file, err or 'Audio trống')

                        done_count += len(sub_items)
                        pct = 10 + int((done_count / total_sentences) * 75)
                        last_snippet = sub_items[-1]['text'][:30] + ('...' if len(sub_items[-1]['text']) > 30 else '')
                        yield f"data: {json.dumps({'type': 'progress', 'percent': pct, 'message': f'🎙️ Đang tạo giọng GPU (RTX 5060): {done_count}/{total_sentences} câu ({pct}%) - \"{last_snippet}\"', 'current': done_count, 'total': total_sentences}, ensure_ascii=False)}\n\n"

                elif is_edge:
                    raw_voice = voice_id.replace('edge_', '')
                    rate_val = int(round((speed - 1.0) * 100))
                    rate_str = f"{rate_val:+d}%"
                    import asyncio
                    import edge_tts

                    async def _run_edge_batch(edge_tasks):
                        sem = asyncio.Semaphore(6)
                        async def _synth_one(s_idx, text, c_file, cache_f):
                            async with sem:
                                for attempt in range(3):
                                    try:
                                        comm = edge_tts.Communicate(text, raw_voice, rate=rate_str)
                                        await comm.save(c_file)
                                        if os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                                            try:
                                                shutil.copyfile(c_file, cache_f)
                                            except Exception:
                                                pass
                                            return (s_idx, c_file, None, text)
                                    except Exception as ex:
                                        if attempt == 2:
                                            return (s_idx, c_file, str(ex), text)
                                        await asyncio.sleep(0.3)
                                return (s_idx, c_file, "Edge-TTS timeout", text)
                        return await asyncio.gather(*[_synth_one(s_idx, val, c_file, cache_f) for s_idx, val, c_file, cache_f in edge_tasks])

                    done_count = cache_hits
                    for b_start in range(0, len(uncached_tasks), 12):
                        sub_edge_tasks = uncached_tasks[b_start:b_start + 12]
                        loop = asyncio.new_event_loop()
                        try:
                            asyncio.set_event_loop(loop)
                            sub_res = loop.run_until_complete(_run_edge_batch(sub_edge_tasks))
                        finally:
                            loop.close()

                        for s_idx, c_file, err, sent_txt in sub_res:
                            chunk_results[s_idx] = (c_file, err)

                        done_count += len(sub_edge_tasks)
                        pct = 10 + int((done_count / total_sentences) * 75)
                        last_snippet = sub_edge_tasks[-1][1][:30] + ('...' if len(sub_edge_tasks[-1][1]) > 30 else '')
                        yield f"data: {json.dumps({'type': 'progress', 'percent': pct, 'message': f'🎙️ Đang tạo giọng Edge Neural: {done_count}/{total_sentences} câu ({pct}%) - \"{last_snippet}\"', 'current': done_count, 'total': total_sentences}, ensure_ascii=False)}\n\n"

                else:
                    # Online API Voices (OpenSpeaker)
                    def _synth_worker(task):
                        s_idx, sentence_text, chunk_file, cache_f = task
                        try:
                            ai_dubbing.synthesize_sentence(sentence_text, voice_id, speed, chunk_file, open_speaker_key=api_key)
                            if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 100:
                                try:
                                    shutil.copyfile(chunk_file, cache_f)
                                except Exception:
                                    pass
                            return (s_idx, chunk_file, None, sentence_text)
                        except Exception as ex:
                            return (s_idx, chunk_file, str(ex), sentence_text)

                    actual_workers = min(8, len(uncached_tasks))
                    done_count = cache_hits
                    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
                        future_to_task = {pool.submit(_synth_worker, task): task for task in uncached_tasks}
                        for fut in as_completed(future_to_task):
                            s_idx, c_file, err, sent_txt = fut.result()
                            chunk_results[s_idx] = (c_file, err)
                            done_count += 1
                            pct = 10 + int((done_count / total_sentences) * 75)
                            sent_preview = sent_txt[:30] + ('...' if len(sent_txt) > 30 else '')
                            yield f"data: {json.dumps({'type': 'progress', 'percent': pct, 'message': f'🎙️ Đang tạo giọng Online: {done_count}/{total_sentences} câu ({pct}%) - \"{sent_preview}\"', 'current': done_count, 'total': total_sentences}, ensure_ascii=False)}\n\n"

            # Tự động thử lại (Self-healing retry) bất kỳ câu nào bị lỗi hoặc file wav rỗng
            need_retry = []
            for s_idx, val, c_file in speech_tasks:
                cf, err = chunk_results.get(s_idx, (None, None))
                if err or not cf or not os.path.exists(cf) or os.path.getsize(cf) < 100:
                    need_retry.append((s_idx, val, c_file))

            if need_retry:
                yield f"data: {json.dumps({'type': 'progress', 'percent': 86, 'message': f'🔄 Đang tự động thử lại {len(need_retry)} câu chưa đạt yêu cầu...'}, ensure_ascii=False)}\n\n"
                for s_idx, val, c_file in need_retry:
                    try:
                        ai_dubbing.synthesize_sentence(val, voice_id, speed, c_file, open_speaker_key=api_key)
                        if os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                            chunk_results[s_idx] = (c_file, None)
                            c_key, c_file_cache, _ = ai_dubbing.get_sentence_cache_info(val, voice_id, speed, target_sample_rate=target_sr, target_channels=1)
                            try:
                                shutil.copyfile(c_file, c_file_cache)
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Xác định sample rate chuẩn từ chunk đầu tiên
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

            yield f"data: {json.dumps({'type': 'progress', 'percent': 89, 'message': '🎵 Đang ghép nối âm thanh đa luồng và chuẩn hóa tần số mẫu PCM...', 'current': total_sentences, 'total': total_sentences}, ensure_ascii=False)}\n\n"

            srt_blocks = []
            current_time = 0.0
            sentence_idx = 1
            has_written_frames = False

            with sf.SoundFile(audio_path, mode='w', samplerate=target_sr, channels=1, subtype='PCM_16') as out_f:
                for seg_type, val in segments:
                    if seg_type == 'speech':
                        c_file, err = chunk_results.get(sentence_idx, (None, None))
                        if c_file and os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                            try:
                                chunk_pcm, sr = sf.read(c_file, dtype='float32')
                                if len(chunk_pcm.shape) > 1:
                                    chunk_pcm = chunk_pcm.mean(axis=1) # convert to mono
                                if sr != target_sr and len(chunk_pcm) > 0:
                                    import scipy.signal
                                    new_len = int(round(len(chunk_pcm) * target_sr / float(sr)))
                                    chunk_pcm = scipy.signal.resample(chunk_pcm, new_len)

                                dur = len(chunk_pcm) / float(target_sr)
                                start_str = sec_to_srt_time(current_time)
                                end_str = sec_to_srt_time(current_time + dur)
                                srt_blocks.append(f"{sentence_idx}\n{start_str} --> {end_str}\n{val}\n")
                                out_f.write(chunk_pcm)
                                has_written_frames = True
                                current_time += dur
                            except Exception as read_err:
                                print(f"[TTS Stream] Lỗi đọc đoạn audio câu #{sentence_idx}: {read_err}")
                            finally:
                                try:
                                    if c_file and os.path.exists(c_file):
                                        norm_c = os.path.abspath(c_file).replace('\\', '/')
                                        if '/.cache/' not in norm_c and '\\.cache\\' not in os.path.abspath(c_file):
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
            yield f"data: {json.dumps({'type': 'progress', 'percent': 95, 'message': '⏱️ Đang đồng bộ mốc thời gian và ghi tệp phụ đề SRT...', 'current': total_sentences, 'total': total_sentences}, ensure_ascii=False)}\n\n"

            srt_content = "\n".join(srt_blocks)
            with open(srt_path, 'w', encoding='utf-8') as srt_f:
                srt_f.write(srt_content)

        # Telegram notify
        skip_notify = req_data.get('skip_notify', False) or req_data.get('notify') is False
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
        complete_data = {
            'type': 'complete',
            'success': True,
            'percent': 100,
            'message': '🎉 Đã hoàn tất tạo giọng đọc và phụ đề SRT!',
            'filename': filename,
            'audio_url': f'/api/file?path={urllib.parse.quote(audio_path)}',
            'srt_url': f'/api/file?path={urllib.parse.quote(srt_path)}',
            'absolute_path': os.path.abspath(audio_path),
            'srt_absolute_path': os.path.abspath(srt_path),
            'duration': round(duration, 2)
        }
        yield f"data: {json.dumps(complete_data, ensure_ascii=False)}\n\n"
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'message': f'Lỗi khi tạo giọng đọc TTS: {str(e)}'}, ensure_ascii=False)}\n\n"


@tts_bp.route('/api/tts/generate_stream', methods=['POST'])
def api_generate_tts_stream():
    """Endpoint Server-Sent Events tạo giọng đọc TTS báo cáo tiến độ chuẩn xác thời gian thực."""
    req_data = request.json or {}
    return Response(generate_tts_stream_internal(req_data), mimetype='text/event-stream')


@tts_bp.route('/api/tts/warmup', methods=['GET', 'POST'])
def api_tts_warmup():
    """Khởi động ấm (Pre-warm) GPU Worker ngầm để xóa bỏ 15 giây trễ cold-start."""
    def _warm():
        try:
            import local_voice_worker_client
            client = local_voice_worker_client.get_voice_worker_client()
            if client.is_runtime_available():
                client.load_model(max_batch_size=32)
        except Exception as e:
            logging.getLogger(__name__).warning(f"[TTS Warmup] Note: {e}")

    threading.Thread(target=_warm, daemon=True).start()
    return jsonify({"success": True, "message": "TTS GPU Worker warmup initiated"})


@tts_bp.route('/api/tts/kokoro', methods=['POST'])
def generate_tts_kokoro():
    req_data = request.json or {}
    if req_data.get('stream') or request.headers.get('Accept') == 'text/event-stream':
        return Response(generate_tts_stream_internal(req_data), mimetype='text/event-stream')
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('tts_unlimited_local')
        if not allowed:
            return jsonify({'success': False, 'error': perm_msg}), 403

        text = req_data.get('text', '').strip()
        voice_id = req_data.get('voice') or req_data.get('voice_id') or 'local_ngoc_huyen'
        speed = _safe_speed(req_data.get('speed', 1.0))
        output_dir = _safe_output_dir(req_data.get('output_dir'))
        filename = req_data.get('filename')
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản kịch bản trống'}), 400
        if len(text) > 1000000:
            return jsonify({'success': False, 'error': 'Kịch bản vượt quá 1.000.000 ký tự'}), 413

        timestamp = int(time.time()*1000)
        if not filename:
            clean_vid = re.sub(r'[^a-zA-Z0-9_]', '_', voice_id)
            filename = f"tts_{clean_vid}_{timestamp}.wav"
        filename = sanitize_unicode_filename(str(filename), default_ext='.wav')
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
            # Multi-sentence TTS with sentence-level timestamps & pauses
            # Kích hoạt xử lý đa luồng song song (Multi-threading) tăng tốc độ tạo giọng
            from concurrent.futures import ThreadPoolExecutor
            
            is_edge = voice_id.startswith('edge_')
            req_threads = int(req_data.get('threads') or req_data.get('tts_threads') or 16)
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
                    # Phân cụm sub-batches (32 items) chống quá tải IPC, OOM RAM & timeout khi tạo audio truyện dài 30p-1h
                    CHUNK_SUB_BATCH = 32
                    b_res = []
                    for b_start in range(0, len(batch_items), CHUNK_SUB_BATCH):
                        sub_items = batch_items[b_start:b_start + CHUNK_SUB_BATCH]
                        sub_res = local_voice_engine.synthesize_batch(sub_items, voice_id=voice_id, speed=speed, batch_size=16)
                        if isinstance(sub_res, list):
                            b_res.extend(sub_res)
                        elif sub_res is not None:
                            b_res.append(sub_res)

                    for item, r in zip(speech_tasks, b_res):
                        err = None
                        if isinstance(r, dict):
                            if not r.get('success', False):
                                err = r.get('error') or 'Lỗi tạo audio GPU'
                        elif isinstance(r, Exception):
                            err = str(r)
                        elif r is not None and not isinstance(r, (dict, list)):
                            err = str(r)
                        chunk_results[item[0]] = (item[2], err)
                else:
                    actual_workers = min(max_workers, len(speech_tasks))
                    with ThreadPoolExecutor(max_workers=actual_workers) as pool:
                        for s_idx, c_file, err in pool.map(_synth_worker, speech_tasks):
                            chunk_results[s_idx] = (c_file, err)

                # Tự động thử lại (Self-healing retry) bất kỳ câu nào bị lỗi hoặc file wav rỗng
                for s_idx, val, c_file in speech_tasks:
                    cf, err = chunk_results.get(s_idx, (None, None))
                    if err or not cf or not os.path.exists(cf) or os.path.getsize(cf) < 100:
                        try:
                            print(f"[TTS] Tự động thử lại câu #{s_idx} ({val[:30]}...)...")
                            ai_dubbing.synthesize_sentence(val, voice_id, speed, c_file)
                            if os.path.exists(c_file) and os.path.getsize(c_file) > 100:
                                chunk_results[s_idx] = (c_file, None)
                        except Exception as retry_err:
                            print(f"[TTS] Thử lại câu #{s_idx} thất bại: {retry_err}")

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
                                chunk_pcm, sr = sf.read(c_file, dtype='float32')
                                if len(chunk_pcm.shape) > 1:
                                    chunk_pcm = chunk_pcm.mean(axis=1) # convert to mono
                                # Nếu sample rate khác target_sr thì resample an toàn
                                if sr != target_sr and len(chunk_pcm) > 0:
                                    import scipy.signal
                                    new_len = int(round(len(chunk_pcm) * target_sr / float(sr)))
                                    chunk_pcm = scipy.signal.resample(chunk_pcm, new_len)
                                
                                dur = len(chunk_pcm) / float(target_sr)
                                start_str = sec_to_srt_time(current_time)
                                end_str = sec_to_srt_time(current_time + dur)
                                srt_blocks.append(f"{sentence_idx}\n{start_str} --> {end_str}\n{val}\n")
                                out_f.write(chunk_pcm)
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
        skip_notify = req_data.get('skip_notify', False) or req_data.get('notify') is False
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

def extract_text_and_stats_from_bytes(orig_name, raw_bytes):
    """
    Trích xuất văn bản và thông số (từ, ký tự, thời lượng ước tính) từ dữ liệu bytes của tệp kịch bản.
    Hỗ trợ .txt, .docx, .pdf, .srt, .vtt, .md, .markdown, .json, .csv.
    """
    _, ext = os.path.splitext(orig_name.lower())
    supported_exts = {'.txt', '.text', '.docx', '.pdf', '.srt', '.vtt', '.md', '.markdown', '.json', '.csv'}
    if ext not in supported_exts:
        raise ValueError(f"Định dạng tệp '{ext}' không được hỗ trợ. Vui lòng chọn tệp .txt, .docx, .pdf, .srt, .vtt, .md hoặc .json.")

    if not raw_bytes:
        raise ValueError('Tệp tải lên rỗng.')

    if len(raw_bytes) > 50 * 1024 * 1024:
        raise ValueError('Dung lượng tệp vượt quá giới hạn cho phép (50 MB).')

    extracted_text = ""
    import io

    if ext in {'.txt', '.text', '.md', '.markdown'}:
        for enc in ['utf-8-sig', 'utf-8', 'utf-16', 'windows-1258', 'cp1252', 'latin-1']:
            try:
                extracted_text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

    elif ext == '.docx':
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw_bytes))
            para_texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            extracted_text = "\n\n".join(para_texts)
        except Exception as docx_err:
            raise ValueError(f"Lỗi đọc file Word DOCX: {str(docx_err)}")

    elif ext == '.pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
            pages_text = []
            for page in reader.pages:
                p_txt = page.extract_text()
                if p_txt and p_txt.strip():
                    pages_text.append(p_txt.strip())
            extracted_text = "\n\n".join(pages_text)
        except Exception as pdf_err:
            raise ValueError(f"Lỗi đọc file PDF: {str(pdf_err)}")

    elif ext in {'.srt', '.vtt'}:
        content = ""
        for enc in ['utf-8-sig', 'utf-8', 'utf-16', 'windows-1258', 'cp1252']:
            try:
                content = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        
        lines = content.replace('\r\n', '\n').split('\n')
        dialogues = []
        for line in lines:
            l = line.strip()
            if not l:
                continue
            if l.startswith('WEBVTT') or l.startswith('NOTE'):
                continue
            if re.match(r'^\d+$', l):
                continue
            if '-->' in l:
                continue
            dialogues.append(l)
        extracted_text = "\n".join(dialogues)

    elif ext == '.json':
        content = raw_bytes.decode('utf-8', errors='ignore')
        data = json.loads(content)
        if isinstance(data, list):
            extracted_lines = []
            for item in data:
                if isinstance(item, dict):
                    t = item.get('text') or item.get('translation') or item.get('content') or ''
                    if t:
                        extracted_lines.append(str(t).strip())
                elif isinstance(item, str):
                    extracted_lines.append(item.strip())
            extracted_text = "\n".join(extracted_lines)
        elif isinstance(data, dict):
            extracted_text = str(data.get('text') or data.get('content') or data.get('script') or content)

    elif ext == '.csv':
        import csv
        content = raw_bytes.decode('utf-8', errors='ignore')
        reader = csv.reader(io.StringIO(content))
        extracted_lines = []
        for row in reader:
            line_str = " ".join(r.strip() for r in row if r.strip())
            if line_str:
                extracted_lines.append(line_str)
        extracted_text = "\n".join(extracted_lines)

    # Chuẩn hóa văn bản
    extracted_text = re.sub(r'\r\n', '\n', extracted_text)
    extracted_text = re.sub(r'\n{3,}', '\n\n', extracted_text).strip()

    if not extracted_text:
        raise ValueError(f"Không tìm thấy nội dung văn bản hợp lệ trong tệp '{orig_name}'.")

    char_count = len(extracted_text)
    words = len(re.findall(r'\S+', extracted_text))
    est_sec = round(words / 2.3)
    if est_sec >= 3600:
        h = est_sec // 3600
        m = (est_sec % 3600) // 60
        est_str = f"{h}h {m}m"
    elif est_sec >= 60:
        m = est_sec // 60
        s = est_sec % 60
        est_str = f"{m}m {s}s"
    else:
        est_str = f"{est_sec}s"

    base_raw = os.path.splitext(orig_name)[0]
    base_clean = re.sub(r'[^a-zA-Z0-9_\-\u00C0-\u024F\u1EA0-\u1EF9]', '_', base_raw).strip('_')
    clean_title = base_clean if base_clean else f"audio_{int(time.time())}"
    suggested_title = f"audio_{base_clean}" if base_clean else f"audio_story_{int(time.time())}"

    return {
        'filename': orig_name,
        'title': clean_title,
        'suggested_title': suggested_title,
        'text': extracted_text,
        'stats': {
            'char_count': char_count,
            'word_count': words,
            'estimated_duration_sec': est_sec,
            'estimated_duration_str': est_str
        }
    }


@tts_bp.route('/api/tts/import_file', methods=['POST'])
def import_tts_file():
    try:
        permission_error = _require_media_access('tts_unlimited_local')
        if permission_error:
            return permission_error

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Vui lòng chọn tệp tài liệu kịch bản để tải lên.'}), 400

        uploaded = request.files['file']
        orig_name = uploaded.filename or 'script.txt'
        raw_bytes = uploaded.read()

        parsed = extract_text_and_stats_from_bytes(orig_name, raw_bytes)
        return jsonify({
            'success': True,
            'text': parsed['text'],
            'filename': parsed['filename'],
            'suggested_title': parsed['suggested_title'],
            'stats': parsed['stats']
        })

    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Lỗi đọc tệp tài liệu: {str(e)}"}), 500


@tts_bp.route('/api/tts/import_batch_files', methods=['POST'])
def import_tts_batch_files():
    """
    Import danh sách nhiều tệp kịch bản cùng lúc cho luồng tạo TTS hàng loạt.
    """
    try:
        permission_error = _require_media_access('tts_unlimited_local')
        if permission_error:
            return permission_error

        uploaded_files = request.files.getlist('files')
        if not uploaded_files:
            uploaded_files = request.files.getlist('files[]')
        if not uploaded_files:
            # Fallback lấy toàn bộ tệp trong request.files
            uploaded_files = list(request.files.values())

        if not uploaded_files:
            return jsonify({'success': False, 'error': 'Vui lòng chọn ít nhất một tệp kịch bản để tải lên.'}), 400

        results = []
        errors = []

        for up_file in uploaded_files:
            fname = up_file.filename or 'script.txt'
            try:
                raw_bytes = up_file.read()
                parsed = extract_text_and_stats_from_bytes(fname, raw_bytes)
                results.append(parsed)
            except Exception as ex:
                errors.append({'filename': fname, 'error': str(ex)})

        if not results and errors:
            return jsonify({'success': False, 'error': errors[0]['error'], 'errors': errors}), 400

        return jsonify({
            'success': True,
            'items': results,
            'errors': errors,
            'total': len(results)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Lỗi nạp tệp hàng loạt: {str(e)}"}), 500


@tts_bp.route('/api/tts/import_batch_folder', methods=['POST'])
def import_tts_batch_folder():
    """
    Quét toàn bộ tệp kịch bản trong một thư mục và sắp xếp theo số thứ tự tự nhiên (Natural Sort).
    """
    try:
        permission_error = _require_media_access('tts_unlimited_local')
        if permission_error:
            return permission_error

        data = request.get_json(silent=True) or {}
        folder_path = data.get('folder_path', '').strip()
        if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return jsonify({'success': False, 'error': 'Đường dẫn thư mục không hợp lệ hoặc không tồn tại.'}), 400

        from routes.security import register_user_path
        register_user_path(folder_path)

        if not is_path_allowed(folder_path):
            return jsonify({'success': False, 'error': 'Thư mục chưa được cấp quyền truy cập.'}), 403

        supported_exts = {'.txt', '.text', '.docx', '.pdf', '.srt', '.vtt', '.md', '.markdown', '.json', '.csv'}
        all_entries = os.listdir(folder_path)

        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

        all_entries.sort(key=natural_sort_key)

        matched_files = [f for f in all_entries if os.path.splitext(f.lower())[1] in supported_exts]
        if not matched_files:
            return jsonify({'success': False, 'error': 'Không tìm thấy tệp kịch bản nào (.txt, .docx, .srt...) trong thư mục đã chọn.'}), 400

        matched_files = matched_files[:300] # Giới hạn tối đa 300 tệp để an toàn tài nguyên
        results = []
        errors = []

        for fname in matched_files:
            fpath = os.path.join(folder_path, fname)
            try:
                if not os.path.isfile(fpath):
                    continue
                size = os.path.getsize(fpath)
                if size == 0 or size > 50 * 1024 * 1024:
                    continue
                with open(fpath, 'rb') as f:
                    raw_bytes = f.read()
                parsed = extract_text_and_stats_from_bytes(fname, raw_bytes)
                parsed['file_path'] = os.path.abspath(fpath)
                results.append(parsed)
            except Exception as ex:
                errors.append({'filename': fname, 'error': str(ex)})

        if not results and errors:
            return jsonify({'success': False, 'error': errors[0]['error'], 'errors': errors}), 400

        return jsonify({
            'success': True,
            'folder_path': os.path.abspath(folder_path),
            'items': results,
            'errors': errors,
            'total': len(results)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Lỗi quét thư mục kịch bản: {str(e)}"}), 500

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
    data = request.json or {}
    if data.get('stream') or request.headers.get('Accept') == 'text/event-stream':
        return Response(generate_tts_stream_internal(data), mimetype='text/event-stream')
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('online_voices_enabled')
        if not allowed:
            return jsonify({'success': False, 'error': perm_msg}), 403

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
        filename = sanitize_unicode_filename(str(filename), default_ext='.mp3')
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


