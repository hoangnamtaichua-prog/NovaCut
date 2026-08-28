from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
from routes.security import is_path_allowed, safe_join
import asr_manager
import license_manager
from urllib.parse import urlparse

subtitles_bp = Blueprint('subtitles', __name__)
MAX_SUBTITLE_FILE_BYTES = 20 * 1024 * 1024
MAX_SUBTITLE_ITEMS = 50000
MAX_AI_SUBTITLE_ITEMS = 5000
MAX_AI_TEXT_CHARS = 500000


def _require_editor():
    allowed, message, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None


def _validate_api_base_url(value):
    parsed = urlparse(str(value or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('OpenAI Base URL phải là HTTPS hợp lệ và không chứa thông tin đăng nhập.')
    allowed_hosts = {'api.openai.com', 'api.ai33.pro'}
    allowed_hosts.update(
        item.strip().lower()
        for item in os.environ.get('NOVACUT_ALLOWED_AI_HOSTS', '').split(',')
        if item.strip()
    )
    if parsed.hostname.lower() not in allowed_hosts:
        raise ValueError('Tên miền OpenAI Base URL chưa có trong NOVACUT_ALLOWED_AI_HOSTS.')
    return str(value).rstrip('/')

def _time_to_seconds(t_str):
    try:
        t_str = str(t_str).strip().replace(',', '.')
        parts = t_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(t_str)
    except Exception:
        return 0.0

def _normalize_timestamp(t_str):
    try:
        t_str = str(t_str).strip().replace(',', '.')
        parts = t_str.split(':')
        hrs, mins, secs = 0, 0, 0.0
        if len(parts) == 3:
            hrs = int(parts[0])
            mins = int(parts[1])
            secs = float(parts[2])
        elif len(parts) == 2:
            mins = int(parts[0])
            secs = float(parts[1])
        elif len(parts) == 1:
            secs = float(parts[0])
            
        total_sec = hrs * 3600 + mins * 60 + secs
        if total_sec < 0:
            total_sec = 0.0
        total_ms = max(0, int(round(total_sec * 1000)))
        h, remainder = divmod(total_ms, 3_600_000)
        m, remainder = divmod(remainder, 60_000)
        s, ms = divmod(remainder, 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    except Exception:
        return "00:00:00.000"

def _parse_srt_tolerant(content):
    if not content:
        return []
    # 1. Bóc bỏ thinking / reasoning tags (DeepSeek-R1, GPT-5.6-Luna, Luna, OpenAI reasoning models)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'```(?:srt|subtitles|text|markdown)?', '', content, flags=re.IGNORECASE)
    content = content.replace('```', '')
    
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    lines = content.split('\n')

    time_pattern = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?(?:[,\.]\d{1,3})?)\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[,\.]\d{1,3})?)')
    timestamp_indices = []
    for idx, line in enumerate(lines):
        match = time_pattern.search(line)
        if match:
            timestamp_indices.append((idx, match.group(1), match.group(2)))
            
    cleaned_subtitles = []
    if timestamp_indices:
        for i, (line_idx, start_t, end_t) in enumerate(timestamp_indices):
            next_line_idx = timestamp_indices[i + 1][0] if (i + 1 < len(timestamp_indices)) else len(lines)
            raw_text_lines = lines[line_idx + 1:next_line_idx]
            
            # Xóa dòng ID số nguyên ở cuối nếu có dòng tiếp theo
            if i + 1 < len(timestamp_indices) and raw_text_lines:
                if raw_text_lines[-1].strip().isdigit():
                    raw_text_lines.pop()
                    
            text = ' '.join([l.strip() for l in raw_text_lines if l.strip() and not l.strip().startswith('---') and not l.strip().startswith('===')])
            
            start_norm = _normalize_timestamp(start_t)
            end_norm = _normalize_timestamp(end_t)
            start_sec = _time_to_seconds(start_norm)
            end_sec = _time_to_seconds(end_norm)
            
            if end_sec <= start_sec:
                end_sec = start_sec + 2.0
                end_norm = _normalize_timestamp(str(end_sec))
                
            if text:
                cleaned_subtitles.append({
                    'id': str(len(cleaned_subtitles) + 1),
                    'time': f"{start_norm} - {end_norm}",
                    'startSeconds': start_sec,
                    'endSeconds': end_sec,
                    'text': text,
                    'translation': ''
                })
    return cleaned_subtitles

@subtitles_bp.route('/api/subtitles/parse_file', methods=['POST'])
def parse_subtitles_file():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.json or {}
    srt_path = data.get('srt_path')
    if not srt_path:
        return jsonify({'success': False, 'error': 'Chưa chọn file phụ đề', 'subtitles': []})
    srt_path = os.path.normpath(srt_path.strip('\'"'))
    if not is_path_allowed(srt_path, must_exist=True, extensions={'.srt', '.vtt'}):
        return jsonify({'success': False, 'error': 'File phụ đề không tồn tại hoặc chưa được cho phép', 'subtitles': []}), 400
    if os.path.getsize(srt_path) > MAX_SUBTITLE_FILE_BYTES:
        return jsonify({'success': False, 'error': 'File phụ đề vượt quá 20 MB', 'subtitles': []}), 413
    try:
        # Hỗ trợ nhiều loại encoding (utf-8, utf-8-sig, gbk, utf-16)
        content = ""
        for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'utf-16', 'latin-1']:
            try:
                with open(srt_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except Exception:
                continue
        subs = _parse_srt_tolerant(content)
        if len(subs) > MAX_SUBTITLE_ITEMS:
            return jsonify({'success': False, 'error': 'File có quá nhiều mục phụ đề', 'subtitles': []}), 413
        return jsonify({'success': True, 'subtitles': subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'subtitles': []})

def _format_srt_timestamp_helper(seconds):
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 0.0
    total_ms = max(0, int(round(seconds * 1000)))
    h, remainder = divmod(total_ms, 3_600_000)
    m, remainder = divmod(remainder, 60_000)
    s, ms = divmod(remainder, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

@subtitles_bp.route('/api/subtitles/export_temp', methods=['POST'])
def export_temp_srt():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.json or {}
    subtitles = data.get('subtitles', [])
    video_path = data.get('video_path', '')
    
    if not subtitles:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề rỗng'}), 400
    if not isinstance(subtitles, list) or len(subtitles) > MAX_SUBTITLE_ITEMS:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn'}), 413
    if video_path and not is_path_allowed(video_path, must_exist=True, extensions={'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}):
        return jsonify({'success': False, 'error': 'Video tham chiếu không hợp lệ hoặc chưa được cho phép'}), 400
        
    try:
        if video_path and is_path_allowed(video_path, must_exist=True, extensions={'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}):
            base_dir = os.path.dirname(os.path.abspath(video_path))
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            out_path = safe_join(base_dir, f"{video_name}_extracted.srt", extensions={'.srt'})
        else:
            temp_dir = os.path.join(USER_DATA_DIR, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            out_path = safe_join(temp_dir, f"subtitles_transfer_{time.time_ns()}.srt", extensions={'.srt'})
            
        with open(out_path, 'w', encoding='utf-8') as f:
            for idx, sub in enumerate(subtitles):
                start_sec = sub.get('startSeconds', 0.0)
                end_sec = sub.get('endSeconds', start_sec + 2.0)
                if end_sec <= start_sec:
                    end_sec = start_sec + 2.0
                text = str(sub.get('translation') or sub.get('text') or sub.get('original_text') or '').strip()[:20000]
                f.write(f"{idx + 1}\n")
                f.write(f"{_format_srt_timestamp_helper(start_sec)} --> {_format_srt_timestamp_helper(end_sec)}\n")
                f.write(f"{text}\n\n")
                
        return jsonify({'success': True, 'srt_path': out_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@subtitles_bp.route('/api/read_srt', methods=['POST'])
def read_srt():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    srt_path = data.get('srt_path')
    if not is_path_allowed(srt_path, must_exist=True, extensions={'.srt'}):
        return jsonify({'error': 'File not found'}), 404
    if os.path.getsize(srt_path) > MAX_SUBTITLE_FILE_BYTES:
        return jsonify({'error': 'File phụ đề vượt quá 20 MB'}), 413
        
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        blocks = re.split(r'\n\s*\n', content.strip())
        subtitles = []
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                time_match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                if time_match:
                    start_time = time_match.group(1).replace(',', '.')
                    end_time = time_match.group(2).replace(',', '.')
                    text = '\n'.join(lines[2:]).strip()
                    subtitles.append({
                        'id': lines[0].strip(),
                        'time': f"{start_time} - {end_time}",
                        'startSeconds': _time_to_seconds(time_match.group(1)),
                        'endSeconds': _time_to_seconds(time_match.group(2)),
                        'text': text,
                        'translation': ''
                    })
        return jsonify({'subtitles': subtitles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _resolve_openai_credentials(data=None):
    if data is None:
        data = {}
    openai_key = data.get('openai_key')
    openai_base_url = data.get('openai_base_url') or 'https://api.openai.com/v1'
    openai_model = data.get('openai_model') or 'gpt-5.6-luna'

    if not openai_key or not str(openai_key).strip() or str(openai_key).startswith('•'):
        candidate_files = [API_KEYS_FILE]

        for api_keys_file in candidate_files:
            if os.path.exists(api_keys_file):
                try:
                    with open(api_keys_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('openaiKey='):
                                openai_key = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiBaseUrl=') and (not openai_base_url or openai_base_url == 'https://api.openai.com/v1'):
                                openai_base_url = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiModel=') and (not openai_model or openai_model in ['gpt-4o-mini', 'gpt-5.6-luna']):
                                openai_model = line.strip().split('=', 1)[1]
                    if openai_key and not openai_key.startswith('•'):
                        break
                except Exception:
                    pass

        if not openai_key:
            openai_key = os.environ.get('OPENAI_API_KEY')

    openai_key = str(openai_key or '').strip()
    openai_base_url = _validate_api_base_url(openai_base_url)
    openai_model = re.sub(r'[^a-zA-Z0-9_.:/-]', '', str(openai_model))[:200]
    if not openai_model:
        raise ValueError('Tên model OpenAI không hợp lệ.')
    return openai_key, openai_base_url, openai_model

@subtitles_bp.route('/api/translate_subtitles', methods=['POST'])
def translate_subtitles():
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    mode = data.get('mode', 'free')  # 'free' or 'ai'
    source_lang = data.get('source_lang', 'auto')
    target_lang = data.get('target_lang', 'vi')
    try:
        openai_key, openai_base_url, openai_model = _resolve_openai_credentials(data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    
    if not subtitles:
        return jsonify({'error': 'Không có phụ đề nào để dịch.'}), 400
    if mode not in {'free', 'ai'} or not isinstance(subtitles, list) or len(subtitles) > MAX_AI_SUBTITLE_ITEMS or not all(isinstance(s, dict) for s in subtitles):
        return jsonify({'error': 'Mode hoặc danh sách phụ đề không hợp lệ/quá lớn.'}), 400
    if sum(len(str(s.get('text', ''))) for s in subtitles if isinstance(s, dict)) > MAX_AI_TEXT_CHARS:
        return jsonify({'error': 'Tổng nội dung phụ đề vượt quá giới hạn 500.000 ký tự.'}), 413
        
    try:
        if mode == 'free':
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            
            texts = [s.get('text', '').strip() for s in subtitles]
            translated_texts = []
            chunk_size = 25
            
            for i in range(0, len(texts), chunk_size):
                chunk = texts[i:i + chunk_size]
                non_empty_indices = [idx for idx, t in enumerate(chunk) if t]
                non_empty_texts = [chunk[idx] for idx in non_empty_indices]
                
                if non_empty_texts:
                    try:
                        results = translator.translate_batch(non_empty_texts)
                    except Exception:
                        results = [translator.translate(t) for t in non_empty_texts]
                else:
                    results = []
                    
                chunk_res = []
                res_idx = 0
                for idx, t in enumerate(chunk):
                    if t:
                        chunk_res.append(results[res_idx] if res_idx < len(results) else t)
                        res_idx += 1
                    else:
                        chunk_res.append('')
                translated_texts.extend(chunk_res)
                
            for s, trans in zip(subtitles, translated_texts):
                s['translation'] = trans
                
            return jsonify({'success': True, 'subtitles': subtitles, 'count': len(subtitles)})
            
        else:
            is_quota_ok, quota_msg = license_manager.check_token_quota()
            if not is_quota_ok:
                return jsonify({'error': quota_msg}), 403

            if not openai_key:
                return jsonify({'error': 'Vui lòng cung cấp OpenAI API Key.'}), 400
                
            import openai
            import prompt_vault
            client = openai.OpenAI(
                api_key=openai_key,
                base_url=openai_base_url,
                timeout=60.0,
                max_retries=1
            )
            
            system_prompt = prompt_vault.get_prompt('prompt_dich_phu_de', "You are a professional video subtitle translator. Translate each subtitle accurately and naturally.")
                    
            lang_map = {
                'vi': 'tiếng Việt',
                'en': 'tiếng Anh',
                'zh': 'tiếng Trung',
                'ja': 'tiếng Nhật',
                'ko': 'tiếng Hàn',
                'fr': 'tiếng Pháp',
                'es': 'tiếng Tây Ban Nha',
                'de': 'tiếng Đức',
                'ru': 'tiếng Nga',
                'th': 'tiếng Thái'
            }
            target_lang_display = lang_map.get(target_lang, target_lang)
            system_prompt = system_prompt.replace('{TARGET_LANG}', target_lang_display)

            def _calc_sub_duration(sub_item):
                start = sub_item.get('startSeconds')
                end = sub_item.get('endSeconds')
                if start is not None and end is not None:
                    try:
                        dur = float(end) - float(start)
                        if dur > 0:
                            return round(dur, 1)
                    except Exception:
                        pass
                time_str = sub_item.get('time', '')
                if ' - ' in time_str:
                    try:
                        parts = time_str.split(' - ')
                        t1 = _time_to_seconds(parts[0].replace('.', ','))
                        t2 = _time_to_seconds(parts[1].replace('.', ','))
                        dur = t2 - t1
                        if dur > 0:
                            return round(dur, 1)
                    except Exception:
                        pass
                return 2.5

            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            chunk_size = 30
            for i in range(0, len(subtitles), chunk_size):
                chunk = subtitles[i:i + chunk_size]
                input_lines = []
                for s in chunk:
                    sid = s.get('id', '')
                    txt = s.get('text', '').replace('\r', '').replace('\n', ' ').strip()
                    dur = _calc_sub_duration(s)
                    input_lines.append(f"[{sid}] ({dur}s) {txt}")
                user_msg = "\n".join(input_lines)
                
                req_kwargs = {
                    "model": openai_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg}
                    ]
                }
                
                # Check for reasoning models or models that require default temperature
                is_reasoning_model = any(m in openai_model.lower() for m in ['o1', 'o3', 'o4', 'luna', 'reasoning', 'gpt-5'])
                if not is_reasoning_model:
                    req_kwargs["temperature"] = 0.3
                    req_kwargs["max_tokens"] = 8000
                else:
                    req_kwargs["max_completion_tokens"] = 8000
                    
                try:
                    response = client.chat.completions.create(**req_kwargs)
                except Exception as call_err:
                    # If model rejects custom temperature, retry without temperature
                    if "temperature" in str(call_err).lower() and "temperature" in req_kwargs:
                        req_kwargs.pop("temperature", None)
                        response = client.chat.completions.create(**req_kwargs)
                    else:
                        raise call_err

                if hasattr(response, 'usage') and response.usage:
                    total_usage["prompt_tokens"] += getattr(response.usage, 'prompt_tokens', 0) or 0
                    total_usage["completion_tokens"] += getattr(response.usage, 'completion_tokens', 0) or 0
                    total_usage["total_tokens"] += getattr(response.usage, 'total_tokens', 0) or 0

                content = response.choices[0].message.content.strip()
                
                # Parse [ID] translation format
                import re
                trans_map = {}
                for line in content.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    m = re.match(r'^\[(\d+)\][:\s]*(.*)$', line)
                    if m:
                        sid = str(m.group(1))
                        trans_map[sid] = m.group(2).strip()
                    else:
                        m_num = re.match(r'^(\d+)[\.\:\-\)]\s*(.*)$', line)
                        if m_num and str(m_num.group(1)) not in trans_map:
                            trans_map[str(m_num.group(1))] = m_num.group(2).strip()

                # Fallback: Parse JSON if model returned JSON
                if not trans_map or len(trans_map) < len(chunk) * 0.5:
                    json_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if json_match:
                        try:
                            json_items = json.loads(json_match.group(0))
                            for item in json_items:
                                if isinstance(item, dict):
                                    sid = str(item.get('id', ''))
                                    trans = item.get('translation', item.get('text', ''))
                                    if sid:
                                        trans_map[sid] = trans
                        except Exception as pe:
                            print("JSON parse error:", pe)

                for s in chunk:
                    sid = str(s.get('id'))
                    if sid in trans_map:
                        s['translation'] = trans_map[sid]

            if total_usage.get("total_tokens", 0) > 0:
                license_manager.record_token_usage(
                    prompt_tokens=total_usage.get("prompt_tokens", 0),
                    completion_tokens=total_usage.get("completion_tokens", 0)
                )

            return jsonify({'success': True, 'subtitles': subtitles, 'count': len(subtitles), 'usage': total_usage})
            
    except Exception as e:
        from routes.core import format_api_error_to_vietnamese
        vi_err = format_api_error_to_vietnamese(getattr(e, 'status_code', 500), str(e))
        return jsonify({'error': f"Lỗi trong quá trình dịch: {vi_err}"}), 500

@subtitles_bp.route('/api/clean_subtitles_ai', methods=['POST'])
def clean_subtitles_ai():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    try:
        openai_key, openai_base_url, openai_model = _resolve_openai_credentials(data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    
    if not subtitles:
        return jsonify({'error': 'Không có phụ đề nào để làm sạch.'}), 400
    if not isinstance(subtitles, list) or len(subtitles) > MAX_AI_SUBTITLE_ITEMS or not all(isinstance(s, dict) for s in subtitles):
        return jsonify({'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn.'}), 400
    if sum(len(str(s.get('text', ''))) for s in subtitles if isinstance(s, dict)) > MAX_AI_TEXT_CHARS:
        return jsonify({'error': 'Tổng nội dung phụ đề vượt quá giới hạn 500.000 ký tự.'}), 413
        
    if not openai_key:
        return jsonify({'error': 'Chưa cấu hình OpenAI API Key trên hệ thống/máy chủ!'}), 400
        
    import prompt_vault
    prompt_template = prompt_vault.get_prompt('prompt_clean_srt', "Hãy gộp các đoạn phụ đề vụn sau thành câu hoàn chỉnh 5-8 giây, giữ nguyên timestamp SRT hợp lệ:\n\n[DÁN FILE SRT BỊ LẺ CỦA BẠN VÀO ĐÂY]")
        
    srt_lines = []
    for idx, s in enumerate(subtitles, 1):
        time_str = s.get('time', '00:00:00.000 - 00:00:05.000')
        times = time_str.split(' - ') if ' - ' in time_str else [time_str, '00:00:05.000']
        start_t = times[0].replace('.', ',').strip()
        end_t = times[1].replace('.', ',').strip() if len(times) > 1 else '00:00:05,000'
        text = s.get('text', '').strip()
        srt_lines.append(f"{idx}\n{start_t} --> {end_t}\n{text}\n")
        
    raw_srt_content = "\n".join(srt_lines)
    if "[Dán nội dung file SRT vào đây]" in prompt_template:
        user_prompt = prompt_template.replace("[Dán nội dung file SRT vào đây]", raw_srt_content)
    elif "[DÁN FILE SRT BỊ LẺ CỦA BẠN VÀO ĐÂY]" in prompt_template:
        user_prompt = prompt_template.replace("[DÁN FILE SRT BỊ LẺ CỦA BẠN VÀO ĐÂY]", raw_srt_content)
    else:
        user_prompt = f"{prompt_template}\n\n{raw_srt_content}"
    
    try:
        is_quota_ok, quota_msg = license_manager.check_token_quota()
        if not is_quota_ok:
            return jsonify({'error': quota_msg}), 403

        import openai
        client = openai.OpenAI(
            api_key=openai_key,
            base_url=openai_base_url,
            timeout=90.0,
            max_retries=1
        )
        
        req_kwargs = {
            "model": openai_model,
            "messages": [
                {"role": "system", "content": "You are a professional video editor and subtitle formatter. Return only the cleaned and merged SRT content with no extra commentary."},
                {"role": "user", "content": user_prompt}
            ]
        }
        
        is_reasoning_model = any(m in openai_model.lower() for m in ['o1', 'o3', 'o4', 'luna', 'reasoning', 'gpt-5'])
        if not is_reasoning_model:
            req_kwargs["temperature"] = 0.3
            req_kwargs["max_tokens"] = 16000
        else:
            req_kwargs["max_completion_tokens"] = 16000
            
        try:
            response = client.chat.completions.create(**req_kwargs)
        except Exception as call_err:
            err_msg = str(call_err).lower()
            if "temperature" in err_msg and "temperature" in req_kwargs:
                req_kwargs.pop("temperature", None)
                response = client.chat.completions.create(**req_kwargs)
            elif "system" in err_msg or "developer" in err_msg:
                # Merge system prompt into user message
                req_kwargs.pop("temperature", None)
                req_kwargs["messages"] = [{"role": "user", "content": f"You are a professional video editor. Return only the cleaned SRT content with no extra commentary.\n\n{user_prompt}"}]
                response = client.chat.completions.create(**req_kwargs)
            else:
                raise call_err
                
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if hasattr(response, 'usage') and response.usage:
            total_usage["prompt_tokens"] = getattr(response.usage, 'prompt_tokens', 0) or 0
            total_usage["completion_tokens"] = getattr(response.usage, 'completion_tokens', 0) or 0
            total_usage["total_tokens"] = getattr(response.usage, 'total_tokens', 0) or 0

        raw_content = response.choices[0].message.content or ""
        cleaned_subtitles = _parse_srt_tolerant(raw_content)
                    
        if not cleaned_subtitles:
            # Fallback 2: Kiểm tra nếu phản hồi là mảng JSON
            try:
                json_data = json.loads(raw_content.strip())
                if isinstance(json_data, list):
                    for item in json_data:
                        t = item.get('text', '') or item.get('content', '')
                        s_t = item.get('start', item.get('start_time', ''))
                        e_t = item.get('end', item.get('end_time', ''))
                        if t:
                            cleaned_subtitles.append({
                                'id': str(len(cleaned_subtitles) + 1),
                                'time': f"{_normalize_timestamp(s_t)} - {_normalize_timestamp(e_t)}",
                                'startSeconds': _time_to_seconds(s_t),
                                'endSeconds': _time_to_seconds(e_t),
                                'text': t,
                                'translation': ''
                            })
            except Exception:
                pass

        if not cleaned_subtitles:
            snippet = raw_content[:150].replace('\n', ' ') if raw_content else "(phản hồi rỗng)"
            return jsonify({'error': f'Không phân tích được định dạng SRT từ phản hồi của AI ({openai_model}). Phản hồi: "{snippet}"...'}), 500
            
        if total_usage.get("total_tokens", 0) > 0:
            license_manager.record_token_usage(
                prompt_tokens=total_usage.get("prompt_tokens", 0),
                completion_tokens=total_usage.get("completion_tokens", 0)
            )

        return jsonify({'success': True, 'subtitles': cleaned_subtitles, 'count': len(cleaned_subtitles), 'usage': total_usage})
    except Exception as e:
        from routes.core import format_api_error_to_vietnamese
        vi_err = format_api_error_to_vietnamese(getattr(e, 'status_code', 500), str(e))
        return jsonify({'error': f"Lỗi làm sạch SRT: {vi_err}"}), 500

@subtitles_bp.route('/api/get_translation_prompt')
def get_translation_prompt():
    prompt_file = os.path.join(ROOT_DIR, 'prompts', 'prompt_dich_phu_de.txt')
    if not os.path.exists(prompt_file):
        prompt_file = os.path.join(ROOT_DIR, 'prompt_dich_phu_de.txt')
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return jsonify({'prompt': f.read()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'prompt': ''})

@subtitles_bp.route('/api/get_clean_srt_prompt')
def get_clean_srt_prompt():
    prompt_file = os.path.join(ROOT_DIR, 'prompts', 'prompt_clean_srt.txt')
    if not os.path.exists(prompt_file):
        prompt_file = os.path.join(ROOT_DIR, 'prompt_clean_srt.txt')
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return jsonify({'prompt': f.read()})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'prompt': ''})

@subtitles_bp.route('/api/save_clean_srt_prompt', methods=['POST'])
def save_clean_srt_prompt():
    data = request.json or {}
    new_prompt = data.get('prompt', '').strip()
    if not new_prompt:
        return jsonify({'error': 'Prompt không được để trống'}), 400
    prompt_file = os.path.join(ROOT_DIR, 'prompts', 'prompt_clean_srt.txt')
    if not os.path.exists(os.path.dirname(prompt_file)):
        prompt_file = os.path.join(ROOT_DIR, 'prompt_clean_srt.txt')
    try:
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(new_prompt)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@subtitles_bp.route('/api/save_translation_prompt', methods=['POST'])
def save_translation_prompt():
    data = request.json or {}
    prompt_content = data.get('prompt', '')
    os.makedirs(os.path.join(ROOT_DIR, 'prompts'), exist_ok=True)
    prompt_file_prompts = os.path.join(ROOT_DIR, 'prompts', 'prompt_dich_phu_de.txt')
    prompt_file_root = os.path.join(ROOT_DIR, 'prompt_dich_phu_de.txt')
    try:
        with open(prompt_file_prompts, 'w', encoding='utf-8') as f:
            f.write(prompt_content)
        with open(prompt_file_root, 'w', encoding='utf-8') as f:
            f.write(prompt_content)
        return jsonify({'success': True, 'message': 'Đã lưu prompt thành công!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

