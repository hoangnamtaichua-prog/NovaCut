from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, urllib.parse
from routes.state import *
import asr_manager

tts_bp = Blueprint('tts', __name__)

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
    
    # 3. Load cached OpenSpeaker voices (500+ voices)
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

    openspeaker_path = os.path.join(ROOT_DIR, 'web', 'openspeaker_voices.json')
    os.makedirs(os.path.dirname(openspeaker_path), exist_ok=True)
    with open(openspeaker_path, 'w', encoding='utf-8') as out:
        json.dump(all_voices_list, out, indent=2, ensure_ascii=False)
        
    return jsonify({"success": True, "count": len(all_voices_list)})

@tts_bp.route('/api/custom-voices', methods=['GET'])
def api_get_custom_voices():
    import custom_voices
    voices = custom_voices.load_custom_voices()
    return jsonify({"success": True, "voices": voices})

@tts_bp.route('/api/custom-voices', methods=['POST'])
def api_add_custom_voice():
    import custom_voices
    data = request.json or {}
    name = data.get('name', '').strip()
    model_path = data.get('model_path', '').strip()
    
    if not name or not model_path:
        return jsonify({"success": False, "error": "Vui lòng nhập tên giọng và chọn file Model .pth"}), 400
        
    if not os.path.exists(model_path):
        return jsonify({"success": False, "error": f"Không tìm thấy file model: {model_path}"}), 400

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
        "index_path": data.get("index_path", "").strip() or None,
        "pitch": int(data.get("pitch", 0)),
        "f0_method": data.get("f0_method", "rmvpe"),
        "index_rate": float(data.get("index_rate", 0.45)),
        "protect": float(data.get("protect", 0.50))
    }
    
    saved = custom_voices.add_or_update_voice(new_voice)
    return jsonify({"success": True, "voice": saved})

@tts_bp.route('/api/custom-voices/<voice_id>', methods=['DELETE'])
def api_delete_custom_voice(voice_id):
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
    import vietnamese_text_normalizer
    d = vietnamese_text_normalizer.load_custom_pronunciations()
    if word in d:
        del d[word]
        vietnamese_text_normalizer.save_custom_pronunciations(d)
    return jsonify({"success": True, "pronunciations": d})

@tts_bp.route('/api/tts/preview', methods=['POST'])
def generate_tts_preview():
    try:
        data = request.json or {}
        voice_id = data.get('voice') or data.get('voice_id') or 'ngoc_huyen'
        text = data.get('text', 'Xin chào! Đây là bản nghe thử giọng đọc AI thuyết minh chuẩn phòng thu.').strip()
        
        samples_dir = os.path.join(ROOT_DIR, 'web', 'samples')
        os.makedirs(samples_dir, exist_ok=True)
        
        sample_filename = f"{voice_id}.wav"
        sample_path = os.path.join(samples_dir, sample_filename)
        
        # 1. If sample already exists, return instantly
        if os.path.exists(sample_path) and os.path.getsize(sample_path) > 1000:
            return jsonify({
                'success': True,
                'audio_url': f'/samples/{sample_filename}',
                'cached': True
            })
            
        # 2. Check root fallback aliases
        if voice_id == 'diem_trinh' and os.path.exists(os.path.join(ROOT_DIR, 'sample_hoatngon_diem_trinh.wav')):
            import shutil
            shutil.copy(os.path.join(ROOT_DIR, 'sample_hoatngon_diem_trinh.wav'), sample_path)
            return jsonify({'success': True, 'audio_url': f'/samples/{sample_filename}', 'cached': True})
            
        if voice_id == 'mai_linh' and os.path.exists(os.path.join(ROOT_DIR, 'sample_hoatngon_mai_linh.wav')):
            import shutil
            shutil.copy(os.path.join(ROOT_DIR, 'sample_hoatngon_mai_linh.wav'), sample_path)
            return jsonify({'success': True, 'audio_url': f'/samples/{sample_filename}', 'cached': True})
            
        # 3. Generate once and cache
        import ai_dubbing
        ai_dubbing.synthesize_sentence(text, voice_id, 1.0, sample_path)
        
        return jsonify({
            'success': True,
            'audio_url': f'/samples/{sample_filename}',
            'cached': False
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@tts_bp.route('/api/tts/sentence_preview', methods=['POST'])
def generate_sentence_preview():
    try:
        data = request.json or {}
        text = data.get('text', '').strip()
        voice_id = data.get('voice_id') or data.get('voice') or 'local_ngoc_huyen'
        speed = float(data.get('speed', 1.0))
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản rỗng'}), 400
            
        import hashlib
        cache_dir = os.path.join(ROOT_DIR, 'web', 'samples', 'tts_cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        # MD5 hash of voice, speed, text
        hash_key = hashlib.md5(f"{voice_id}_{speed}_{text}".encode('utf-8')).hexdigest()
        cache_filename = f"{hash_key}.wav"
        cache_path = os.path.join(cache_dir, cache_filename)
        
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 500:
            return jsonify({
                'success': True,
                'audio_url': f'/samples/tts_cache/{cache_filename}',
                'cached': True
            })
            
        import ai_dubbing
        ai_dubbing.synthesize_sentence(text, voice_id, speed, cache_path)
        
        return jsonify({
            'success': True,
            'audio_url': f'/samples/tts_cache/{cache_filename}',
            'cached': False
        })
    except Exception as e:
        import traceback
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
        speed = float(data.get('speed', 1.0))
        output_dir = data.get('output_dir') or 'output'
        filename = data.get('filename')
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản kịch bản trống'}), 400
            
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time()*1000)
        if not filename:
            clean_vid = re.sub(r'[^a-zA-Z0-9_]', '_', voice_id)
            filename = f"tts_{clean_vid}_{timestamp}.wav"
        if not filename.endswith('.wav'):
            filename += '.wav'
            
        audio_path = os.path.join(output_dir, filename)
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
            temp_chunks = []
            srt_blocks = []
            current_time = 0.0
            sentence_idx = 1
            target_sr = 48000
            
            for seg_type, val in segments:
                if seg_type == 'speech':
                    chunk_wav = os.path.join(output_dir, f"temp_chunk_{timestamp}_{sentence_idx}.wav")
                    ai_dubbing.synthesize_sentence(val, voice_id, speed, chunk_wav)
                    
                    data, sr = sf.read(chunk_wav)
                    target_sr = sr
                    if len(data.shape) > 1:
                        data = data.mean(axis=1) # convert to mono
                    dur = len(data) / float(target_sr)
                    
                    start_str = sec_to_srt_time(current_time)
                    end_str = sec_to_srt_time(current_time + dur)
                    srt_blocks.append(f"{sentence_idx}\n{start_str} --> {end_str}\n{val}\n")
                    sentence_idx += 1
                    
                    temp_chunks.append(data.astype(np.float32))
                    current_time += dur
                    
                    try: os.remove(chunk_wav)
                    except: pass
                    
                elif seg_type == 'pause':
                    pause_dur = float(val)
                    if pause_dur > 0:
                        pause_samples = int(target_sr * pause_dur)
                        temp_chunks.append(np.zeros(pause_samples, dtype=np.float32))
                        current_time += pause_dur
            
            # Combine all chunks
            final_audio = np.concatenate(temp_chunks, axis=0) if temp_chunks else np.zeros(target_sr, dtype=np.float32)
            sf.write(audio_path, final_audio, target_sr, subtype='PCM_16')
            
            duration = len(final_audio) / float(target_sr)
            srt_content = "\n".join(srt_blocks)
            with open(srt_path, 'w', encoding='utf-8') as srt_f:
                srt_f.write(srt_content)
            
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
        return jsonify({'success': False, 'error': f"Lỗi tạo TTS: {str(e)}"}), 500

@tts_bp.route('/api/tts/openspeaker/voices', methods=['GET'])
def get_openspeaker_voices():
    import requests
    api_key = request.args.get('api_key')
    if not api_key:
        api_keys_file = os.path.join(ROOT_DIR, 'api_keys.txt')
        if os.path.exists(api_keys_file):
            with open(api_keys_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('openSpeakerApiKey='):
                        api_key = line.split('=', 1)[1].strip()
    if not api_key:
        return jsonify({'error': 'Missing API Key'}), 400
    
    provider = request.args.get('provider', '')
    url = f"https://api.ai33.pro/v3/voices?limit=100"
    if provider:
        url += f"&provider={provider}"
        
    try:
        res = requests.get(url, headers={"xi-api-key": api_key})
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
        speed = float(data.get('speed', 1.0))
        output_dir = data.get('output_dir') or 'output'
        filename = data.get('filename')
        api_key = data.get('api_key')
        
        if not text:
            return jsonify({'success': False, 'error': 'Văn bản kịch bản trống'}), 400
            
        if not api_key:
            api_keys_file = os.path.join(ROOT_DIR, 'api_keys.txt')
            if os.path.exists(api_keys_file):
                with open(api_keys_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key = line.split('=', 1)[1].strip()
                            
        if not api_key:
            return jsonify({'success': False, 'error': 'Vui lòng cung cấp OpenSpeaker API Key'}), 400
            
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        if not filename:
            filename = f"tts_open_{voice_id}_{timestamp}.mp3"
        if not (filename.endswith('.mp3') or filename.endswith('.wav')):
            filename += '.mp3'
            
        audio_path = os.path.join(output_dir, filename)
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

    temp_dir = os.path.join(ROOT_DIR, "output", "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    raw_path = os.path.join(temp_dir, f"raw_{int(time.time()*1000)}_{file.filename}")
    file.save(raw_path)

    import local_voice_engine
    clean_sample_path = os.path.join(temp_dir, f"clean_{int(time.time()*1000)}.wav")
    ok, res = local_voice_engine.validate_and_convert_audio_sample(raw_path, clean_sample_path)
    
    # Dọn dẹp file raw nếu khác file clean
    if raw_path != clean_sample_path and os.path.exists(raw_path):
        try: os.remove(raw_path)
        except: pass

    if not ok:
        return jsonify({'success': False, 'error': res}), 400

    import wave
    with wave.open(clean_sample_path, 'r') as wf:
        duration = wf.getnframes() / float(wf.getframerate())

    quality_score = 90 if 2.0 <= duration <= 12.0 else 75
    quality_desc = "Rất tốt (24kHz Mono chuẩn)" if quality_score >= 80 else "Ổn định"

    return jsonify({
        'success': True,
        'filename': file.filename,
        'audio_path': clean_sample_path,
        'relative_path': os.path.relpath(clean_sample_path, ROOT_DIR).replace("\\", "/"),
        'duration': round(duration, 2),
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
    speed = float(data.get('speed', 1.0))

    if not audio_path and not voice_id:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp file âm thanh mẫu hoặc chọn giọng'}), 400

    if audio_path and not os.path.isabs(audio_path):
        audio_path = os.path.join(ROOT_DIR, audio_path)

    temp_out = os.path.join(ROOT_DIR, "output", f"preview_{int(time.time()*1000)}.wav")
    try:
        import local_voice_engine
        local_voice_engine.synthesize(
            text=text,
            voice_id=voice_id or None,
            ref_audio=audio_path if audio_path and os.path.exists(audio_path) else None,
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

    if not os.path.exists(audio_path):
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
    data = request.json or {}
    voice_id = data.get('voice_id', '').strip()
    if not voice_id:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp voice_id cần xóa'}), 400

    import custom_voices
    custom_voices.delete_voice(voice_id)
    return jsonify({'success': True, 'message': 'Đã xóa giọng khỏi thư viện thành công!'})


