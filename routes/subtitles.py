from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
try:
    from translation_config import DEFAULT_TRANSLATION_MODEL, DEFAULT_TRANSLATION_CONFIG
except ImportError:
    try:
        from routes.state import DEFAULT_TRANSLATION_MODEL, DEFAULT_TRANSLATION_CONFIG
    except ImportError:
        DEFAULT_TRANSLATION_MODEL = "qwen/qwen3.8-flash"
        DEFAULT_TRANSLATION_CONFIG = {
            "model": "qwen/qwen3.8-flash",
            "chunkSize": 80,
            "concurrency": 3,
            "maxRetries": 3,
            "requestTimeout": 60,
            "contextLines": 6,
            "temperature": 0.0,
            "providerRouting": "throughput"
        }
from routes.security import is_path_allowed, safe_join
import asr_manager
import license_manager
from urllib.parse import urlparse

subtitles_bp = Blueprint('subtitles', __name__)
MAX_SUBTITLE_FILE_BYTES = 20 * 1024 * 1024
MAX_SUBTITLE_ITEMS = 50000
MAX_AI_SUBTITLE_ITEMS = 50000
MAX_AI_TEXT_CHARS = 10000000


def _require_editor():
    allowed, message, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None


def _validate_api_base_url(value):
    parsed = urlparse(str(value or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('OpenAI Base URL phải là HTTPS hợp lệ và không chứa thông tin đăng nhập.')
    allowed_hosts = {'api.openai.com', 'api.ai33.pro', 'openrouter.ai'}
    allowed_hosts.update(
        item.strip().lower()
        for item in os.environ.get('NOVACUT_ALLOWED_AI_HOSTS', '').split(',')
        if item.strip()
    )
    if parsed.hostname.lower() not in allowed_hosts:
        raise ValueError('Tên miền OpenAI Base URL chưa có trong NOVACUT_ALLOWED_AI_HOSTS.')
    return str(value).rstrip('/')

TRANSLATION_STYLE_PROMPTS_VI = {
    'cinema': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: CHUẨN ĐIỆN ẢNH (CINEMA)】\n"
        "- Dịch tự nhiên, mượt mà, thoát ý, giàu cảm xúc, chuẩn văn phong phụ đề phim chiếu rạp Việt Nam.\n"
        "- Giữ đúng tính cách nhân vật, biểu cảm tự nhiên và bối cảnh phân cảnh."
    ),
    'street_raw': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: DÂN DÃ / ĐƯỜNG PHỐ / BỤI BẶM / THÔ TỤC NHẸ (STREET & RAW)】\n"
        "- Dịch theo ngôn ngữ đời sống đường phố bụi bặm, dân dã, chân thực, mang khẩu khí giang hồ hoặc bạn bè bình dân.\n"
        "- Xưng hô: Sử dụng đại từ nhân xưng bình dân, phong trần (mày - tao, bố mày, ông đây, bà đây, thằng ranh, con ranh, lão già, thằng nhãi... khi nhân vật tức giận, đối đầu, cãi cọ hoặc đùa giỡn thân mật).\n"
        "- Khẩu ngữ và tiếng lóng: Cho phép và khuyến khích dùng các từ cảm thán thô mộc, từ lóng đời thực và chửi thề nhẹ khi tức giận/đánh nhau (ví dụ: mẹ kiếp, vãi, mé, chết tiệt, cút mẹ mày đi, khốn nạn, chó chết, cay vãi, ăn cám...).\n"
        "- Tuyệt đối KHÔNG dịch văn vẻ điệu đà, sách vở; phải biến tấu thành lời ăn tiếng nói đường phố chân thật, gai góc và giàu năng lượng."
    ),
    'historical': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: CỔ TRANG / KIẾM HIỆP / TIÊN HIỆP】\n"
        "- Dịch theo phong thái cổ kính, kiếm hiệp, tiên hiệp trang trọng, hào sảng và uy nghiêm.\n"
        "- Xưng hô chuẩn mực cổ trang: ta - ngươi, tại hạ, các hạ, huynh - đệ, bệ hạ - thần thiếp, trẫm - ái khanh, bản tọa, bản tôn, bổn vương, sư phụ - đồ nhi, lão hủ, công tử, cô nương...\n"
        "- Sử dụng tối đa các thuật ngữ và từ ngữ Hán Việt chuẩn xác, quen thuộc trong phim cổ trang võ hiệp kinh điển."
    ),
    'humorous_bua': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: HÀI HƯỚC / BỰA / LẦY LỘI / TRENDING GEN Z】\n"
        "- Dịch dí dỏm, lầy lội, bựa, hài hước và châm biếm sâu cay nhằm mang lại tiếng cười sảng khoái và tính giải trí cao.\n"
        "- Khéo léo lồng ghép ngôn ngữ mạng hiện đại, tiếng lóng giới trẻ (Gen Z) hóm hỉnh một cách tự nhiên, duyên dáng."
    ),
    'romance': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: NGÔN TÌNH / LÃNG MẠN / SÂU LẮNG】\n"
        "- Dịch tha thiết, ngọt ngào, tinh tế, giàu chất thơ và lay động trái tim.\n"
        "- Xưng hô tình cảm (anh - em, chàng - thiếp, người ơi...), câu từ mềm mại, lãng mạn, tôn vinh cảm xúc tình yêu sâu sắc."
    ),
    'formal': (
        "\n\n【YÊU CẦU PHONG CÁCH DỊCH: NGHIÊM TÚC / CHÍNH KỊCH / TÀI LIỆU】\n"
        "- Dịch trung tính, nghiêm túc, sát nghĩa, chuẩn xác, văn minh và lịch sự.\n"
        "- Xưng hô chuẩn mực (tôi - anh/chị, quý vị, các đồng chí...), không dùng từ lóng hay tiếng lóng đời thường."
    )
}

TRANSLATION_STYLE_PROMPTS_EN = {
    'cinema': (
        "\n\n[STYLE REQUIREMENT: CINEMATIC & NATURAL]\n"
        "- Translate into natural, idiomatic, cinematic dialogue suitable for modern theatrical releases.\n"
        "- Keep character voices natural and emotionally expressive."
    ),
    'street_raw': (
        "\n\n[STYLE REQUIREMENT: RAW / STREET / GRITTY / COLLOQUIAL / MILD PROFANITY]\n"
        "- Translate using gritty, authentic, colloquial street language.\n"
        "- Use informal pronouns, authentic street slang, and raw expressions.\n"
        "- Mild profanities and curses (e.g. damn, hell, crap, shit, bastard, get lost, what the hell...) are explicitly permitted and encouraged during arguments, fights, or intense street dialogues to maintain gritty realism."
    ),
    'historical': (
        "\n\n[STYLE REQUIREMENT: HISTORICAL / MARTIAL ARTS / PERIOD PIECE]\n"
        "- Translate in an archaic, noble, dramatic period-piece tone (using forms like Sire, My Lord, Master, Thy/Thee where appropriate)."
    ),
    'humorous_bua': (
        "\n\n[STYLE REQUIREMENT: HUMOROUS / WITTY / SATIRICAL / GEN-Z SLANG]\n"
        "- Translate with wit, humour, playful banter, modern sarcasm, and entertaining pop-culture-friendly slang."
    ),
    'romance': (
        "\n\n[STYLE REQUIREMENT: ROMANTIC / POETIC / TENDER]\n"
        "- Translate with tenderness, romantic warmth, poetic nuance, and deep emotional resonance."
    ),
    'formal': (
        "\n\n[STYLE REQUIREMENT: FORMAL / DOCUMENTARY / PRECISE]\n"
        "- Neutral, polite, formal, precise, and literal translation without slang."
    )
}

def clean_sub_translation(trans: str, target_lang: str = 'vi') -> str:
    """
    Làm sạch triệt để bản dịch phụ đề:
    - Loại bỏ tận gốc cấu trúc giải thích từ vựng: [Chữ Hán] (nghĩa tiếng Việt) -> [nghĩa tiếng Việt]
      Ví dụ: '既然 (vì)' -> 'vì', '竟然 (lại)' -> 'lại', 'thật有心 (có tình ý)' -> 'thật có tình ý'
    - Xóa các ngoặc chỉ chứa chữ Hán: '(既然)' -> ''
    - Xóa sạch bất kỳ ký tự Hán tự nào còn sót lại trong bản dịch tiếng Việt
    - Chuẩn hóa khoảng trắng, dấu câu và viết hoa đầu câu
    """
    if not trans or not isinstance(trans, str):
        return ""
    trans = str(trans).strip()
    tgt = str(target_lang or 'vi').lower()
    # 1. Khử cấu trúc Hán tự kèm chú thích trong ngoặc đơn / ngoặc toàn giác:
    trans = re.sub(r'[\u4e00-\u9fff]+\s*[\(\（]([^\)\）]+)[\)\）]', r' \1 ', trans)
    trans = re.sub(r'[\(\（]([^\)\）]+)[\)\）]\s*[\u4e00-\u9fff]+', r' \1 ', trans)

    # 2. Xóa các ngoặc chỉ chứa chữ Hán:
    trans = re.sub(r'[\(\（]\s*[\u4e00-\u9fff]+\s*[\)\）]', '', trans)

    # 3. Dọn sạch bất kỳ chữ Hán đơn lẻ nào còn sót lại khi dịch sang vi hoặc en:
    if tgt in ('vi', 'vietnamese', 'en', 'english'):
        if re.search(r'[\u4e00-\u9fff]', trans):
            trans = re.sub(r'[\u4e00-\u9fff]+', '', trans)

    # 4. Chuẩn hóa khoảng trắng và dấu câu:
    trans = re.sub(r'\s+', ' ', trans).strip()
    trans = re.sub(r'\s+([,.:;?!])', r'\1', trans)
    if trans and trans[0].islower():
        trans = trans[0].upper() + trans[1:]
    return trans

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
    target_srt_path = data.get('target_srt_path', '')
    replace_original = data.get('replace_original', False)
    
    if not subtitles:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề rỗng'}), 400
    if not isinstance(subtitles, list) or len(subtitles) > MAX_SUBTITLE_ITEMS:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn'}), 413
    if video_path and not is_path_allowed(video_path, must_exist=True, extensions={'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}):
        if os.path.exists(video_path) and os.path.splitext(video_path)[1].lower() in {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}:
            from routes.security import register_user_path
            register_user_path(video_path)
        else:
            return jsonify({'success': False, 'error': 'Video tham chiếu không hợp lệ hoặc chưa được cho phép'}), 400
        
    try:
        out_path = None
        if target_srt_path:
            norm_target = os.path.abspath(str(target_srt_path).strip('"\''))
            if not replace_original and not norm_target.endswith('_novacut.srt'):
                base_target, _ = os.path.splitext(norm_target)
                norm_target = f"{base_target}_novacut.srt"
            target_parent = os.path.dirname(norm_target)
            if os.path.exists(target_parent):
                from routes.security import register_user_path
                register_user_path(target_parent)
            if is_path_allowed(norm_target, must_exist=False, extensions={'.srt'}):
                os.makedirs(os.path.dirname(norm_target), exist_ok=True)
                out_path = norm_target
        if not out_path:
            if video_path and is_path_allowed(video_path, must_exist=True, extensions={'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}):
                base_dir = os.path.dirname(os.path.abspath(video_path))
                video_name = os.path.splitext(os.path.basename(video_path))[0]
                filename = f"{video_name}.srt" if replace_original else f"{video_name}_novacut.srt"
                out_path = safe_join(base_dir, filename, extensions={'.srt'})
            else:
                temp_dir = os.path.join(USER_DATA_DIR, 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                out_path = safe_join(temp_dir, f"subtitles_transfer_{time.time_ns()}.srt", extensions={'.srt'})
            
        with open(out_path, 'w', encoding='utf-8') as f:
            for idx, sub in enumerate(subtitles):
                raw_st = sub.get('startSeconds') if sub.get('startSeconds') is not None else sub.get('start_sec', sub.get('start', 0.0))
                raw_et = sub.get('endSeconds') if sub.get('endSeconds') is not None else sub.get('end_sec', sub.get('end', 0.0))
                start_sec = _time_to_seconds(raw_st)
                end_sec = _time_to_seconds(raw_et)
                if end_sec <= start_sec:
                    end_sec = start_sec + 2.0
                text = str(sub.get('translation') or sub.get('text') or sub.get('original_text') or '').strip()[:20000]
                f.write(f"{idx + 1}\n")
                f.write(f"{_format_srt_timestamp_helper(start_sec)} --> {_format_srt_timestamp_helper(end_sec)}\n")
                f.write(f"{text}\n\n")
                
        return jsonify({'success': True, 'srt_path': out_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@subtitles_bp.route('/api/subtitles/normalize_dedup', methods=['POST'])
def api_normalize_dedup_subtitles():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    min_gap_sec = float(data.get('min_gap_sec', 0.7) or 0.7)
    if not isinstance(subtitles, list):
        return jsonify({'success': False, 'error': 'Dữ liệu phụ đề không hợp lệ'}), 400
    try:
        import subtitle_postprocessor
        normalized = subtitle_postprocessor.deterministic_normalize_subtitles(
            subtitles,
            dedup_window=min_gap_sec,
            min_gap_sec=min_gap_sec,
            reindex=True
        )
        return jsonify({'success': True, 'subtitles': normalized})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@subtitles_bp.route('/api/read_srt', methods=['GET', 'POST'])
def read_srt():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        srt_path = data.get('srt_path') or data.get('path')
    else:
        srt_path = request.args.get('srt_path') or request.args.get('path')
    if not srt_path:
        return jsonify({'error': 'Chưa chọn file phụ đề'}), 400
    srt_path = os.path.normpath(str(srt_path).strip('\'"'))
    if not is_path_allowed(srt_path, must_exist=True, extensions={'.srt', '.vtt'}):
        return jsonify({'error': 'File not found'}), 404
    if os.path.getsize(srt_path) > MAX_SUBTITLE_FILE_BYTES:
        return jsonify({'error': 'File phụ đề vượt quá 20 MB'}), 413
        
    try:
        content = ""
        for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'utf-16', 'latin-1']:
            try:
                with open(srt_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except Exception:
                continue
            
        blocks = re.split(r'\n\s*\n', content.strip())
        subtitles = []
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                time_match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                if time_match:
                    start_time = time_match.group(1).replace(',', '.')
                    end_time = time_match.group(2).replace(',', '.')
                    lines_text = lines[2:]
                    joined_text = '\n'.join(lines_text).strip()
                    
                    # Phát hiện phụ đề song ngữ (Dòng 1: Chữ Hán/Gốc, Dòng 2: Bản dịch Tiếng Việt)
                    if len(lines_text) >= 2 and any(0x4E00 <= ord(c) <= 0x9FFF for c in lines_text[0]) and not any(0x4E00 <= ord(c) <= 0x9FFF for c in lines_text[1]):
                        orig_text = lines_text[0].strip()
                        trans_text = '\n'.join(lines_text[1:]).strip()
                    elif not any(0x4E00 <= ord(c) <= 0x9FFF for c in joined_text):
                        # File SRT đã dịch hoàn chỉnh sang Tiếng Việt (hoặc ký tự Latin, không chứa chữ Hán)
                        orig_text = joined_text
                        trans_text = joined_text
                    else:
                        orig_text = joined_text
                        trans_text = ''

                    subtitles.append({
                        'id': lines[0].strip(),
                        'time': f"{start_time} - {end_time}",
                        'startSeconds': _time_to_seconds(time_match.group(1)),
                        'endSeconds': _time_to_seconds(time_match.group(2)),
                        'text': orig_text,
                        'translation': trans_text
                    })
        return jsonify({'subtitles': subtitles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _resolve_openai_credentials(data=None):
    if data is None:
        data = {}
    openai_key = data.get('openai_key')
    openai_base_url = data.get('openai_base_url') or 'https://api.openai.com/v1'
    try:
        from translation_config import DEFAULT_TRANSLATION_MODEL
    except Exception:
        DEFAULT_TRANSLATION_MODEL = 'qwen/qwen3.8-flash'

    openai_model = data.get('openai_model') or DEFAULT_TRANSLATION_MODEL

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
                            elif line.startswith('openaiModel='):
                                val = line.strip().split('=', 1)[1]
                                if val and not data.get('openai_model'):
                                    openai_model = val
                    if openai_key and not openai_key.startswith('•'):
                        break
                except Exception:
                    pass

        if not openai_key:
            openai_key = os.environ.get('OPENAI_API_KEY')

    openai_key = str(openai_key or '').strip()
    if openai_key.startswith('sk-or-') and (not openai_base_url or openai_base_url == 'https://api.openai.com/v1'):
        openai_base_url = 'https://openrouter.ai/api/v1'
    if openai_key.startswith('sk-or-') or 'openrouter.ai' in str(openai_base_url):
        if not openai_model:
            openai_model = DEFAULT_TRANSLATION_MODEL
    openai_base_url = _validate_api_base_url(openai_base_url)
    openai_model = re.sub(r'[^a-zA-Z0-9_.:/-]', '', str(openai_model))[:200]
    if not openai_model:
        raise ValueError('Tên model OpenAI / OpenRouter không hợp lệ.')
    return openai_key, openai_base_url, openai_model

@subtitles_bp.route('/api/translate_subtitles', methods=['POST'])
def translate_subtitles():
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    mode = data.get('mode')
    if not mode:
        if data.get('engine') == 'offline':
            mode = 'local'
        elif data.get('openai_key') or data.get('engine') == 'online':
            mode = 'ai'
        else:
            mode = 'ai'  # Luôn ưu tiên AI thay vì free scraper dễ bị 500
    source_lang = data.get('source_lang', 'auto')
    target_lang = data.get('target_lang', 'vi')
    context_before = data.get('context_before', [])
    glossary = data.get('glossary', {})
    translation_style = str(data.get('translation_style', 'cinema')).strip().lower()
    if translation_style not in TRANSLATION_STYLE_PROMPTS_VI:
        translation_style = 'cinema'
    if mode != 'local':
        try:
            openai_key, openai_base_url, openai_model = _resolve_openai_credentials(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        if not openai_key:
            return jsonify({'error': 'Vui lòng cung cấp OpenAI API Key.'}), 400

        # Khi dịch phụ đề Online: Bắt buộc định tuyến sang Qwen (mặc định qwen/qwen3.8-flash) nếu yêu cầu gửi lên Luna hoặc không phải Qwen
        req_model = (data.get('openai_model') or openai_model or '').strip().lower()
        if not req_model or 'luna' in req_model or 'qwen' not in req_model:
            openai_model = 'qwen/qwen3.8-flash'
    else:
        openai_key, openai_base_url, openai_model = None, None, None
    
    if not subtitles:
        return jsonify({'error': 'Không có phụ đề nào để dịch.'}), 400
    if mode not in {'free', 'ai', 'local'} or not isinstance(subtitles, list) or len(subtitles) > MAX_AI_SUBTITLE_ITEMS or not all(isinstance(s, dict) for s in subtitles):
        return jsonify({'error': 'Mode hoặc danh sách phụ đề không hợp lệ/quá lớn.'}), 400
    if sum(len(str(s.get('text', ''))) for s in subtitles if isinstance(s, dict)) > MAX_AI_TEXT_CHARS:
        return jsonify({'error': 'Tổng nội dung phụ đề vượt quá giới hạn 10.000.000 ký tự.'}), 413
        
    try:
        if mode == 'local':
            import local_ai_manager
            local_model = data.get('local_model')
            res = local_ai_manager.translate_subtitles_local(
                subtitles=subtitles,
                model=local_model,
                source_lang=source_lang,
                target_lang=target_lang,
                translation_style=translation_style,
                return_usage=True
            )
            if isinstance(res, tuple) and len(res) == 2:
                translated, usage = res
            else:
                translated, usage = res, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return jsonify({'success': True, 'subtitles': translated, 'translated': translated, 'usage': usage})
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
                if trans and ('Error 500' in trans or 'Server Error' in trans or '<!DOCTYPE' in trans or '<html' in trans):
                    s['translation'] = ''
                else:
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
            client_headers = {}
            if 'openrouter.ai' in openai_base_url or openai_key.startswith('sk-or-'):
                client_headers = {"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
            client = openai.OpenAI(
                api_key=openai_key,
                base_url=openai_base_url,
                default_headers=client_headers if client_headers else None,
                timeout=45.0,
                max_retries=1
            )
            
            system_prompt = prompt_vault.get_prompt('prompt_dich_phu_de')
            if not system_prompt:
                system_prompt = (
                    "Bạn là công cụ dịch phụ đề chuyên nghiệp từ tiếng Trung sang tiếng Việt.\n\n"
                    "Nhiệm vụ: Dịch thoại phim Trung Quốc sang tiếng Việt tự nhiên, chính xác và phù hợp ngữ cảnh.\n\n"
                    "Quy tắc tối quan trọng:\n"
                    "- Dịch thoát ý, mượt mà tự nhiên như phụ đề phim điện ảnh.\n"
                    "- TUYỆT ĐỐI KHÔNG để sót bất kỳ chữ Hán nào trong kết quả dịch tiếng Việt.\n"
                    "- TUYỆT ĐỐI KHÔNG giải thích từ vựng dạng: Chữ Hán (nghĩa tiếng Việt) như '既然 (vì)', '竟然 (lại)', '有心 (có tình ý)'.\n"
                    "- BẮT BUỘC dịch liền mạch thành câu tiếng Việt hoàn chỉnh.\n"
                    "- 100% bản dịch đầu ra phải là tiếng Việt thuần túy, không chứa chữ Hán và không chú thích ngoặc đơn.\n\n"
                    "Input có dạng:\nID|Chinese text\n\nOutput bắt buộc có dạng:\nID|Vietnamese translation\n\n"
                    "Mỗi subtitle input phải có đúng một subtitle output.\nChỉ output các dòng cần dịch.\nKhông output context được cung cấp để tham khảo."
                )
                    
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
            if target_lang != 'vi':
                system_prompt = system_prompt.replace('tiếng Việt', target_lang_display)
                system_prompt = system_prompt.replace('Vietnamese translation', f'{target_lang_display} translation')

            style_directive = TRANSLATION_STYLE_PROMPTS_VI.get(translation_style, '') if target_lang == 'vi' else TRANSLATION_STYLE_PROMPTS_EN.get(translation_style, '')
            if style_directive:
                system_prompt += style_directive

            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            last_chunk_stats = {}
            chunk_size = 100
            
            for i in range(0, len(subtitles), chunk_size):
                chunk = subtitles[i:i + chunk_size]
                user_sections = []
                
                # 1. Ngữ cảnh phụ đề trước đó (CONTEXT)
                chunk_context = context_before if i == 0 else subtitles[max(0, i - DEFAULT_TRANSLATION_CONFIG.get("contextLines", 8)):i]
                if chunk_context:
                    ctx_lines = []
                    for c_sub in chunk_context:
                        c_id = str(c_sub.get('id', '')).strip()
                        c_txt = str(c_sub.get('text', '')).replace('\r', '').replace('\n', ' ').strip()
                        if c_id and c_txt:
                            ctx_lines.append(f"{c_id}|{c_txt}")
                    if ctx_lines:
                        user_sections.append("[CONTEXT - DO NOT OUTPUT]\n" + "\n".join(ctx_lines))
                
                # 2. Bảng thuật ngữ Tu Tiên & Danh Xưng (GLOSSARY)
                import glossary_manager
                chunk_texts = [s.get('text', '') for s in chunk]
                auto_glossary = glossary_manager.filter_relevant_glossary(chunk_texts, max_terms=30)
                if glossary and isinstance(glossary, dict):
                    auto_glossary.update(glossary)
                elif glossary and isinstance(glossary, list):
                    for item in glossary:
                        if isinstance(item, dict):
                            auto_glossary[item.get('src', '')] = item.get('tgt', '')
                
                if auto_glossary:
                    gloss_lines = [f"{k}={v}" for k, v in auto_glossary.items() if k and v]
                    if gloss_lines:
                        user_sections.append("[GLOSSARY - BẮT BUỘC TUÂN THỦ DANH XƯNG & THUẬT NGỮ]\n" + "\n".join(gloss_lines))
                
                # 3. Phụ đề cần dịch (TRANSLATE) - Không kèm timestamp
                trans_lines = []
                for s in chunk:
                    sid = str(s.get('id', '')).strip()
                    txt = str(s.get('text', '')).replace('\r', '').replace('\n', ' ').strip()
                    trans_lines.append(f"{sid}|{txt}")
                user_sections.append("[TRANSLATE]\n" + "\n".join(trans_lines))
                
                user_msg = "\n\n".join(user_sections)
                
                req_kwargs = {
                    "model": openai_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg}
                    ],
                    "temperature": 0.0
                }
                # Tắt suy nghĩ ngầm (Reasoning/Thinking) để dịch siêu tốc (1-2s thay vì 35s suy nghĩ)
                if 'openrouter.ai' in str(openai_base_url) or openai_key.startswith('sk-or-'):
                    req_kwargs["extra_body"] = {"reasoning": {"effort": "none"}}
                
                response = None
                last_call_err = None
                call_retries = 0
                t_start = time.perf_counter()
                for attempt in range(2):
                    try:
                        response = client.chat.completions.create(**req_kwargs)
                        break
                    except Exception as call_err:
                        last_call_err = call_err
                        call_retries += 1
                        err_str = str(call_err).lower()
                        print(f"[{time.strftime('%X')}] [Subtitles-AI] Cảnh báo thử lại lần {attempt + 1}: {call_err}")

                        if "temperature" in err_str and "temperature" in req_kwargs:
                            req_kwargs.pop("temperature", None)
                            try:
                                response = client.chat.completions.create(**req_kwargs)
                                break
                            except Exception as sub_err:
                                last_call_err = sub_err
                                err_str = str(sub_err).lower()

                        if "reasoning" in err_str and "extra_body" in req_kwargs:
                            req_kwargs.pop("extra_body", None)
                            try:
                                response = client.chat.completions.create(**req_kwargs)
                                break
                            except Exception as sub_err:
                                last_call_err = sub_err
                                err_str = str(sub_err).lower()

                        is_retryable = any(k in err_str for k in ['429', 'rate_limit', 'rate-limited', 'temporarily', 'overload', '500', '502', '503', '504', 'timeout', 'timed out', 'busy', 'unavailable', 'upstream'])
                        if is_retryable and attempt < 1:
                            import random
                            time.sleep(2.0 + random.uniform(0.5, 1.5))
                            continue
                        raise call_err

                t_end = time.perf_counter()
                gen_duration = max(0.01, round(t_end - t_start, 2))

                if response is None:
                    raise last_call_err or Exception("Không nhận được phản hồi từ dịch vụ AI")

                chunk_prompt_tok = 0
                chunk_comp_tok = 0
                if hasattr(response, 'usage') and response.usage:
                    chunk_prompt_tok = getattr(response.usage, 'prompt_tokens', 0) or 0
                    chunk_comp_tok = getattr(response.usage, 'completion_tokens', 0) or 0
                    total_usage["prompt_tokens"] += chunk_prompt_tok
                    total_usage["completion_tokens"] += chunk_comp_tok
                    total_usage["total_tokens"] += getattr(response.usage, 'total_tokens', 0) or 0

                raw_content = response.choices[0].message.content
                if not raw_content and hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    raw_content = response.choices[0].message.reasoning
                if not raw_content:
                    print(f"[{time.strftime('%X')}] [WARN] Model {openai_model} returned empty content for chunk, skipping")
                    continue
                content = raw_content.strip()
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
                content = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
                content = re.sub(r'```(?:[a-zA-Z0-9_-]+)?', '', content).replace('```', '').strip()
                
                # Parse format ID|translation hoặc [ID] translation
                trans_map = {}
                for line in content.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    m = re.match(r'^\[?(\d+)\]?\s*\|\s*(.*)$', line)
                    if m:
                        sid = str(m.group(1))
                        trans_map[sid] = clean_sub_translation(m.group(2).strip(), target_lang)
                    else:
                        m_num = re.match(r'^\[?(\d+)\]?[\.\:\-\)]\s*(.*)$', line)
                        if m_num and str(m_num.group(1)) not in trans_map:
                            trans_map[str(m_num.group(1))] = clean_sub_translation(m_num.group(2).strip(), target_lang)

                # Fallback: Parse JSON nếu model trả về JSON
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
                                        trans_map[sid] = clean_sub_translation(trans, target_lang)
                        except Exception as pe:
                            print("JSON parse error:", pe)

                # ── Auto-Rescue (Cứu hộ tự động 2 tầng): Kiểm tra các câu bị model AI bỏ sót hoặc bản dịch rỗng do dính 100% chữ Hán ──
                missing_in_chunk = []
                for s in chunk:
                    sid = str(s.get('id', '')).strip()
                    trans_val = trans_map.get(sid, '')
                    if not trans_val or (target_lang == 'vi' and re.search(r'[\u4e00-\u9fff]', trans_val)):
                        missing_in_chunk.append(s)

                if missing_in_chunk:
                    print(f"[{time.strftime('%X')}] [Subtitles-AI] Phát hiện {len(missing_in_chunk)} câu chưa dịch trong chunk (IDs: {[s.get('id') for s in missing_in_chunk]}), kích hoạt Auto-Rescue...")
                    # Tầng 1: LLM Mini-Rescue
                    rescue_lines = []
                    for m_s in missing_in_chunk:
                        m_sid = str(m_s.get('id', '')).strip()
                        m_txt = str(m_s.get('text', '')).replace('\r', '').replace('\n', ' ').strip()
                        if m_sid and m_txt:
                            rescue_lines.append(f"{m_sid}|{m_txt}")
                    if rescue_lines:
                        try:
                            rescue_prompt = (
                                f"Bạn là công cụ dịch phụ đề chuyên nghiệp sang {target_lang_display}.\n"
                                f"Nhiệm vụ: Dịch các câu sau đây sang {target_lang_display}.\n"
                                f"BẮT BUỘC định dạng: ID|bản dịch\n"
                                f"Tuyệt đối không giữ lại chữ Hán. Dịch từng câu một cách trôi chảy."
                            )
                            r_kwargs = {
                                "model": openai_model,
                                "messages": [
                                    {"role": "system", "content": rescue_prompt},
                                    {"role": "user", "content": "[TRANSLATE]\n" + "\n".join(rescue_lines)}
                                ],
                                "temperature": 0.0
                            }
                            if 'openrouter.ai' in str(openai_base_url) or openai_key.startswith('sk-or-'):
                                r_kwargs["extra_body"] = {"reasoning": {"effort": "none"}}
                            r_resp = client.chat.completions.create(**r_kwargs)
                            r_raw = r_resp.choices[0].message.content or ""
                            r_raw = re.sub(r'<think>.*?</think>', '', r_raw, flags=re.DOTALL | re.IGNORECASE).strip()
                            for r_l in r_raw.split('\n'):
                                r_m = re.match(r'^\[?(\d+)\]?\s*\|\s*(.*)$', r_l.strip())
                                if r_m:
                                    r_sid = str(r_m.group(1))
                                    r_cl = clean_sub_translation(r_m.group(2).strip(), target_lang)
                                    if r_cl:
                                        trans_map[r_sid] = r_cl
                        except Exception as rescue_err:
                            print(f"[{time.strftime('%X')}] [Subtitles-AI] LLM Rescue thất bại: {rescue_err}")

                    # Tầng 2: Fallback bằng GoogleTranslator (Bảo hiểm tuyệt đối 100% không bao giờ sót câu)
                    still_missing = [s for s in missing_in_chunk if not trans_map.get(str(s.get('id', '')).strip())]
                    if still_missing:
                        print(f"[{time.strftime('%X')}] [Subtitles-AI] Còn {len(still_missing)} câu thiếu sau LLM Rescue, dùng GoogleTranslator dự phòng...")
                        try:
                            from deep_translator import GoogleTranslator
                            src_code = 'zh-CN' if source_lang in ['zh', 'auto'] else source_lang
                            gt = GoogleTranslator(source=src_code, target=target_lang)
                            for s_miss in still_missing:
                                sid_miss = str(s_miss.get('id', '')).strip()
                                txt_miss = str(s_miss.get('text', '')).strip()
                                if txt_miss:
                                    gt_res = gt.translate(txt_miss)
                                    if gt_res and not any(k in gt_res for k in ['Error 500', 'Server Error', '<!DOCTYPE', '<html']):
                                        trans_map[sid_miss] = clean_sub_translation(gt_res, target_lang)
                        except Exception as gt_err:
                            print(f"[{time.strftime('%X')}] [Subtitles-AI] GoogleTranslator Fallback lỗi: {gt_err}")

                for s in chunk:
                    sid = str(s.get('id'))
                    if sid in trans_map:
                        s['translation'] = trans_map[sid]
                    elif 'translation' in s:
                        s['translation'] = clean_sub_translation(s['translation'], target_lang)

                # Quét làm sạch lần cuối cho toàn bộ câu trong chunk
                for s in chunk:
                    if 'translation' in s:
                        s['translation'] = clean_sub_translation(s['translation'], target_lang)

                throughput = round(chunk_comp_tok / gen_duration, 1) if gen_duration > 0 else 0
                last_chunk_stats = {
                    "model": openai_model,
                    "lines": len(chunk),
                    "input_tokens": chunk_prompt_tok,
                    "output_tokens": chunk_comp_tok,
                    "generation_time": gen_duration,
                    "throughput": throughput,
                    "retries": call_retries
                }

            if total_usage.get("total_tokens", 0) > 0:
                license_manager.record_token_usage(
                    prompt_tokens=total_usage.get("prompt_tokens", 0),
                    completion_tokens=total_usage.get("completion_tokens", 0)
                )

            # Đảm bảo 100% tất cả phụ đề trả về đều đã qua bộ lọc clean_sub_translation và đối chiếu glossary hậu kiểm
            # Nhận diện và xử lý riêng biệt câu rác OCR ngắn (1–5 chữ Hán đơn lẻ)
            OCR_GARBAGE_MAX_CHARS = 5  # Câu gốc có tổng <= 5 ký tự Hán thì coi là rác OCR
            for s in subtitles:
                sid = str(s.get('id', '')).strip()
                trans_val = s.get('translation', '')
                needs_rescue = (not trans_val) or (target_lang in ('vi', 'en') and re.search(r'[\u4e00-\u9fff]', trans_val))
                if needs_rescue:
                    raw_txt = str(s.get('text', '')).strip()
                    if not raw_txt:
                        continue

                    # Phân loại: câu rác OCR (1–5 ký tự Hán thuần túy) vs câu thực sự thiếu dịch
                    chinese_chars = re.findall(r'[\u4e00-\u9fff]', raw_txt)
                    non_space_chars = raw_txt.replace(' ', '')
                    is_ocr_garbage = (
                        len(chinese_chars) > 0
                        and len(chinese_chars) == len(non_space_chars)  # chỉ toàn chữ Hán
                        and len(chinese_chars) <= OCR_GARBAGE_MAX_CHARS
                    )

                    if is_ocr_garbage:
                        # Câu rác OCR: thử Google Translate nhưng nếu không được thì gán trống (bỏ qua gracefully)
                        try:
                            from deep_translator import GoogleTranslator
                            src_code = 'zh-CN' if source_lang in ['zh', 'auto'] else source_lang
                            gt = GoogleTranslator(source=src_code, target=target_lang)
                            gt_res = gt.translate(raw_txt)
                            if gt_res and not any(k in gt_res for k in ['Error 500', 'Server Error', '<!DOCTYPE', '<html']) and not re.search(r'[\u4e00-\u9fff]', gt_res):
                                s['translation'] = clean_sub_translation(gt_res, target_lang)
                            else:
                                # Bỏ qua gracefully – không block video
                                s['translation'] = ''
                                s['_ocr_garbage_skipped'] = True
                                print(f"[OCR-Garbage] ID {sid}: '{raw_txt}' – bo qua gracefully.")
                        except Exception:
                            # Bỏ qua gracefully nếu Google Translate cũng thất bại
                            s['translation'] = ''
                            s['_ocr_garbage_skipped'] = True
                            print(f"[OCR-Garbage] ID {sid}: '{raw_txt}' – Google Translate that bai, bo qua gracefully.")
                    else:
                        # Lưới an toàn cuối cùng: Tự động dịch bổ sung nếu vẫn còn câu sót chữ Hán
                        try:
                            from deep_translator import GoogleTranslator
                            src_code = 'zh-CN' if source_lang in ['zh', 'auto'] else source_lang
                            gt = GoogleTranslator(source=src_code, target=target_lang)
                            # Loại bỏ các mẩu tiếng Anh vụn bám đuôi sau dấu câu tiếng Trung (do OCR quét dính dòng sub tiếng Anh)
                            clean_src = raw_txt
                            if bool(re.search(r'[\u4e00-\u9fff]', raw_txt)) and bool(re.search(r'[a-zA-Z]', raw_txt)):
                                clean_src = re.sub(r'([。，！？\.\,\!\?])\s*[a-zA-Z\s\',.-]+$', r'\1', raw_txt).strip()
                                if not clean_src:
                                    clean_src = raw_txt
                            gt_res = gt.translate(clean_src)
                            if gt_res and not any(k in gt_res for k in ['Error 500', 'Server Error', '<!DOCTYPE', '<html']):
                                s['translation'] = clean_sub_translation(gt_res, target_lang)
                        except Exception:
                            pass

                if 'translation' in s:
                    cleaned = clean_sub_translation(s['translation'], target_lang)
                    if target_lang == 'vi' and s.get('text'):
                        cleaned = glossary_manager.post_process_with_glossary(s.get('text', ''), cleaned)
                    s['translation'] = cleaned

            return jsonify({
                'success': True,
                'subtitles': subtitles,
                'count': len(subtitles),
                'usage': total_usage,
                'stats': last_chunk_stats
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        from routes.core import format_api_error_to_vietnamese
        status_code = getattr(e, 'status_code', None)
        if status_code is not None:
            vi_err = format_api_error_to_vietnamese(status_code, str(e))
        else:
            vi_err = str(e)
        return jsonify({'error': f"Lỗi trong quá trình dịch: {vi_err}"}), 500

@subtitles_bp.route('/api/clean_subtitles_ai', methods=['POST'])
def clean_subtitles_ai():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    engine = data.get('engine', 'online')
    is_offline = engine == 'offline'
    if is_offline:
        import local_ai_manager
        local_model = data.get('local_model') or 'qwen2.5:7b'
        openai_key = 'ollama'
        openai_base_url = f"{local_ai_manager.OLLAMA_BASE_URL}/v1"
        openai_model = local_model
    else:
        try:
            openai_key, openai_base_url, openai_model = _resolve_openai_credentials(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        if not openai_key:
            return jsonify({'error': 'Chưa cấu hình OpenAI API Key trên hệ thống/máy chủ!'}), 400

        # Làm sạch phụ đề Online: Bắt buộc gọi GPT Luna (mặc định openai/gpt-6-luna)
        req_model = (data.get('openai_model') or '').strip().lower()
        if not req_model or 'luna' not in req_model:
            if 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-'):
                openai_model = 'openai/gpt-6-luna'
            else:
                openai_model = 'gpt-6-luna'
        else:
            openai_model = data.get('openai_model')
            if 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-'):
                if 'gpt-5.6-luna' in openai_model:
                    openai_model = 'openai/gpt-6-luna'
    
    if not subtitles:
        return jsonify({'error': 'Không có phụ đề nào để làm sạch.'}), 400
    if not isinstance(subtitles, list) or len(subtitles) > MAX_AI_SUBTITLE_ITEMS or not all(isinstance(s, dict) for s in subtitles):
        return jsonify({'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn.'}), 400
    if sum(len(str(s.get('text', ''))) for s in subtitles if isinstance(s, dict)) > MAX_AI_TEXT_CHARS:
        return jsonify({'error': 'Tổng nội dung phụ đề vượt quá giới hạn 10.000.000 ký tự.'}), 413
        
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
        if not is_offline:
            is_quota_ok, quota_msg = license_manager.check_token_quota()
            if not is_quota_ok:
                return jsonify({'error': quota_msg}), 403

        import openai
        client_headers = {}
        if not is_offline and ('openrouter.ai' in openai_base_url or openai_key.startswith('sk-or-')):
            client_headers = {"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
        client = openai.OpenAI(
            api_key=openai_key,
            base_url=openai_base_url,
            default_headers=client_headers if client_headers else None,
            timeout=360.0 if is_offline else 180.0,
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
            if not is_offline and ('openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-')):
                req_kwargs["extra_body"] = {"reasoning": {"effort": "low"}}
            
        try:
            response = client.chat.completions.create(**req_kwargs)
        except Exception as call_err:
            err_msg = str(call_err).lower()
            if "reasoning" in err_msg and "extra_body" in req_kwargs:
                req_kwargs.pop("extra_body", None)
                response = client.chat.completions.create(**req_kwargs)
            elif "temperature" in err_msg and "temperature" in req_kwargs:
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
        import traceback
        traceback.print_exc()
        from routes.core import format_api_error_to_vietnamese
        status_code = getattr(e, 'status_code', None)
        if status_code is not None:
            vi_err = format_api_error_to_vietnamese(status_code, str(e))
        else:
            vi_err = str(e)
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

@subtitles_bp.route('/api/glossary', methods=['GET'])
def get_glossary_api():
    try:
        import glossary_manager
        return jsonify({'success': True, 'glossary': glossary_manager.load_glossary()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@subtitles_bp.route('/api/glossary/save', methods=['POST'])
def save_glossary_api():
    data = request.json or {}
    glossary = data.get('glossary', {})
    try:
        import glossary_manager
        if glossary_manager.save_glossary(glossary):
            return jsonify({'success': True, 'message': 'Đã lưu từ điển thành công!'})
        return jsonify({'error': 'Không thể lưu từ điển'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@subtitles_bp.route('/api/glossary/apply_to_subtitles', methods=['POST'])
def apply_glossary_to_subtitles():
    data = request.json or {}
    subtitles = data.get('subtitles', [])
    if not subtitles:
        return jsonify({'error': 'Không có phụ đề để đối chiếu'}), 400
    try:
        import glossary_manager
        glossary = glossary_manager.load_glossary()
        updated_count = 0
        for s in subtitles:
            src = s.get('text', '')
            trans = s.get('translation', '')
            if src and trans:
                new_trans = glossary_manager.post_process_with_glossary(src, trans, glossary)
                if new_trans != trans:
                    s['translation'] = new_trans
                    updated_count += 1
        return jsonify({'success': True, 'subtitles': subtitles, 'updated_count': updated_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@subtitles_bp.route('/api/local_ai/status')
def local_ai_status():
    try:
        import local_ai_manager
        status = local_ai_manager.get_local_ai_status()
        return jsonify({'status': status})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@subtitles_bp.route('/api/local_ai/pull_model', methods=['POST'])
def local_ai_pull_model():
    data = request.json or {}
    model_name = data.get('model_name', 'qwen2.5:7b')
    import local_ai_manager
    from flask import Response

    def generate():
        for chunk in local_ai_manager.stream_pull_model(model_name):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream')


# =========================================================================
# AI SUBTITLE INSPECTOR BOT (ĐỐI SOÁT PHỤ ĐỀ VIDEO 2 CHIỀU)
# =========================================================================

@subtitles_bp.route('/api/subtitles/inspect_stream', methods=['POST'])
def subtitle_inspect_stream():
    """API đối soát phụ đề video 2 chiều theo luồng SSE thời gian thực"""
    permission_error = _require_editor()
    if permission_error:
        return permission_error

    data = request.get_json(silent=True) or {}
    video_path = str(data.get('video_path', '')).strip(' "\'')
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Đường dẫn video không tồn tại hoặc bị bỏ trống'}), 400

    if not is_path_allowed(video_path):
        return jsonify({'error': 'Đường dẫn video không được phép truy cập'}), 403

    subtitles = data.get('subtitles', [])
    ocr_region = data.get('ocr_region')
    options = data.get('options', {})

    import importlib
    import subtitle_inspector
    importlib.reload(subtitle_inspector)
    bot = subtitle_inspector.get_subtitle_inspector()

    def generate():
        try:
            for evt in bot.inspect_stream(video_path, subtitles, ocr_region, options):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            err_evt = {"type": "error", "message": f"Lỗi trong quá trình đối soát: {str(e)}"}
            yield f"data: {json.dumps(err_evt, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@subtitles_bp.route('/api/subtitles/inspect', methods=['POST'])
def subtitle_inspect():
    """API đối soát phụ đề video 2 chiều đồng bộ trả về kết quả một lần"""
    permission_error = _require_editor()
    if permission_error:
        return permission_error

    data = request.get_json(silent=True) or {}
    video_path = str(data.get('video_path', '')).strip(' "\'')
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Đường dẫn video không tồn tại hoặc bị bỏ trống'}), 400

    if not is_path_allowed(video_path):
        return jsonify({'error': 'Đường dẫn video không được phép truy cập'}), 403

    subtitles = data.get('subtitles', [])
    ocr_region = data.get('ocr_region')
    options = data.get('options', {})

    import importlib
    import subtitle_inspector
    importlib.reload(subtitle_inspector)
    bot = subtitle_inspector.get_subtitle_inspector()
    result = bot.inspect(video_path, subtitles, ocr_region, options)
    return jsonify(result)


@subtitles_bp.route('/api/subtitles/apply_inspector_fixes', methods=['POST'])
def subtitle_apply_inspector_fixes():
    """Áp dụng các chỉnh sửa từ kết quả đối soát của Bot (Thêm câu sót, xóa câu ảo)"""
    permission_error = _require_editor()
    if permission_error:
        return permission_error

    data = request.get_json(silent=True) or {}
    subtitles = data.get('subtitles', [])
    missing_to_add = data.get('missing_to_add')
    if missing_to_add is None:
        missing_to_add = data.get('missing_warnings', [])

    ghost_ids_to_remove = set(str(gid) for gid in data.get('ghost_ids_to_remove', []))
    if not ghost_ids_to_remove and data.get('ghost_warnings'):
        ghost_ids_to_remove = set(str(g.get('sub_id', '')) for g in data.get('ghost_warnings', []))

    if not isinstance(subtitles, list):
        return jsonify({'error': 'Dữ liệu phụ đề không hợp lệ'}), 400

    # Lọc bỏ các ghost subs nếu có yêu cầu
    kept_subs = []
    for s in subtitles:
        sid = str(s.get('id', ''))
        if sid not in ghost_ids_to_remove:
            kept_subs.append(s)

    # Thêm các missing subs
    for m in missing_to_add:
        kept_subs.append({
            'id': 0,
            'start': m.get('start'),
            'end': m.get('end'),
            'startSeconds': m.get('start_sec', m.get('startSeconds')),
            'endSeconds': m.get('end_sec', m.get('endSeconds')),
            'text': m.get('text', ''),
            'translation': m.get('translation', ''),
            'is_auto_filled': True
        })

    from subtitle_postprocessor import deterministic_normalize_subtitles
    fixed_subtitles = deterministic_normalize_subtitles(kept_subs, dedup_window=0.5, reindex=True)

    return jsonify({
        'success': True,
        'subtitles': fixed_subtitles,
        'fixed_subtitles': fixed_subtitles,
        'added_count': len(missing_to_add),
        'removed_count': len(ghost_ids_to_remove)
    })



