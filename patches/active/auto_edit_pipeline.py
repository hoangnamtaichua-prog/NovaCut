import os
import sys
import json
import time
import requests
import subprocess
import re
import shutil
import random
import uuid
import traceback
import ffmpeg_installer
import ai_dubbing
import timeline_sanitizer
import openai
try:
    import tiktoken
except ImportError:
    tiktoken = None
import asyncio
import hashlib
import concurrent.futures
from typing import List, Dict, Tuple, Any, Optional

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, 'web', 'index.html')):
            norm_curr = os.path.normpath(curr).lower()
            if not norm_curr.endswith(os.path.normpath('patches/active').lower()) and not norm_curr.endswith(os.path.normpath('release/novacut').lower()):
                return os.path.abspath(curr)
        curr = os.path.dirname(curr)
    return os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = get_app_root_dir()

def get_stealth_subprocess_kwargs():
    try:
        if hasattr(ffmpeg_installer, 'get_stealth_subprocess_kwargs'):
            return ffmpeg_installer.get_stealth_subprocess_kwargs()
    except Exception:
        pass
    if os.name != 'nt':
        return {}
    import subprocess
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        'creationflags': 0x08000000,
        'startupinfo': si,
        'stdin': subprocess.DEVNULL
    }

def detect_hardware_encoder(ffmpeg_path=None):
    try:
        if hasattr(ffmpeg_installer, 'detect_hardware_encoder'):
            return ffmpeg_installer.detect_hardware_encoder(ffmpeg_path)
    except Exception:
        pass
    return 'libx264', False, ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22']

def is_api_voice(voice_id):
    if not voice_id:
        return False
    vid = str(voice_id).strip().lower()
    # 1. Các giọng Kokoro Offline chuẩn
    if vid in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc'] or vid.startswith('kokoro'):
        return False
    # 2. Các giọng Local Voice Clone, RVC Model Clone, Edge-TTS
    if vid.startswith(('local_', 'rvc_', 'edge_', 'vi-vn-')):
        return False
    # 3. Tra cứu profile trong custom_voices.json
    try:
        import custom_voices
        v_prof = custom_voices.get_voice_by_id(voice_id)
        if v_prof:
            provider = v_prof.get('provider', '').lower()
            if provider in ['local_voice', 'rvc', 'kokoro', 'edge', 'local']:
                return False
    except Exception:
        pass
    # 4. Chỉ coi là OpenSpeaker API khi có tiền tố hoặc được cấu hình rõ ràng là cloud API
    return vid.startswith(('openspeaker_', 'api_', 'os_'))

def parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes', 'on'):
            return True
        if lowered in ('false', '0', 'no', 'off', ''):
            return False
    return default

LANGUAGE_NAMES = {
    'vi': ('Tiếng Việt', 'Vietnamese'),
    'en': ('Tiếng Anh', 'English'),
    'zh': ('Tiếng Trung', 'Chinese'),
    'ja': ('Tiếng Nhật', 'Japanese'),
    'ko': ('Tiếng Hàn', 'Korean'),
    'fr': ('Tiếng Pháp', 'French'),
    'es': ('Tiếng Tây Ban Nha', 'Spanish'),
    'de': ('Tiếng Đức', 'German'),
    'ru': ('Tiếng Nga', 'Russian'),
    'th': ('Tiếng Thái', 'Thai'),
    'id': ('Tiếng Indonesia', 'Indonesian'),
    'ms': ('Tiếng Malaysia', 'Malay'),
    'pt': ('Tiếng Bồ Đào Nha', 'Portuguese'),
    'hi': ('Tiếng Hindi', 'Hindi')
}

def get_language_directive(lang_code):
    if not lang_code:
        return ""
    code = str(lang_code).lower().strip()
    if code in ('vi', 'vietnamese'):
        return ""
    lang_info = LANGUAGE_NAMES.get(code, (code, code))
    lang_vn, lang_en = lang_info
    return (
        f"MANDATORY OUTPUT LANGUAGE REQUIREMENT:\n"
        f"- Toàn bộ kịch bản voice-over review phim phải được viết 100% bằng {lang_vn.upper()} ({lang_en.upper()}).\n"
        f"- Mọi lời thoại, phân tích, dẫn dắt, hook mở đầu, câu giữ chân khán giả và outro đều phải sử dụng {lang_en} tự nhiên, chuẩn ngữ pháp, đúng ngữ cảnh bản xứ của một kênh YouTube Movie Recap / Review chuyên nghiệp.\n"
        f"- TUYỆT ĐỐI KHÔNG xuất văn bản bằng tiếng Việt hay bất kỳ ngôn ngữ nào khác ngoài {lang_en}."
    )

def parse_srt_time(t_str):
    t_str = t_str.strip().replace(',', '.')
    parts = t_str.split(':')
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(t_str)

def format_srt_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def get_review_temp_dir(output_dir: str, video_path: str) -> str:
    """
    Trả về đường dẫn thư mục tạm duy nhất cho từng video trong Review Phim.
    - Bảo toàn tên gốc tiếng Việt/tiếng Trung sạch sẽ, chuẩn hóa ký tự cấm Windows.
    - Kết hợp băm MD5 (10 ký tự) từ đường dẫn tuyệt đối chuẩn hóa của video.
    - Đảm bảo 100% không bao giờ có 2 video khác nhau bị trùng lặp hoặc nhận nhầm cache của nhau.
    """
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)

    v_str = str(video_path or '').strip(' "\'')
    if not v_str:
        return os.path.join(output_dir, 'auto_edit_temp', '_unnamed_video')

    norm_video = os.path.normpath(os.path.abspath(v_str))
    raw_stem = os.path.splitext(os.path.basename(norm_video))[0]
    safe_stem = re.sub(r'[\s\<\>\:\"\/\\\|\?\*\x00-\x1f\']+', '_', raw_stem).strip('._ ')
    if not safe_stem:
        safe_stem = 'video'
    safe_stem = safe_stem[:60].strip('._ ')

    path_hash = hashlib.md5(norm_video.lower().encode('utf-8', errors='ignore')).hexdigest()[:10]
    folder_name = f"{safe_stem}_{path_hash}"
    return os.path.join(output_dir, 'auto_edit_temp', folder_name)

def parse_srt_entries(srt_file_path):
    if not srt_file_path or not os.path.exists(srt_file_path):
        return []
    entries = []
    try:
        with open(srt_file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) >= 2:
                time_line = lines[1] if '-->' in lines[1] else lines[0]
                if '-->' in time_line:
                    t_parts = time_line.split('-->')
                    s_sec = parse_srt_time(t_parts[0])
                    e_sec = parse_srt_time(t_parts[1])
                    txt_lines = lines[2:] if time_line == lines[1] else lines[1:]
                    txt = " ".join(txt_lines).strip()
                    entries.append((s_sec, e_sec, txt))
    except Exception:
        pass
    return entries

def condense_srt_for_llm(srt_text: str, max_chars: int = 40000) -> str:
    """
    Rút gọn và tối ưu nội dung phụ đề SRT trước khi gửi tới LLM.
    - Loại bỏ số thứ tự thừa, chỉ giữ timestamp định dạng gọn [mm:ss] hoặc [hh:mm:ss]
    - Loại bỏ các dòng lặp lại hoặc thẻ âm thanh trống [music], [âm nhạc], (tiếng vỗ tay)
    - Nếu tổng dung lượng vẫn vượt quá max_chars, tiến hành lấy mẫu thông minh (smart sampling)
      để đảm bảo không bị quá tải token gây nghẽn và timeout API.
    """
    if not srt_text or not isinstance(srt_text, str):
        return ""
        
    lines = srt_text.strip().splitlines()
    condensed_entries = []
    
    time_pattern = re.compile(r'(\d{1,2}:\d{2}:\d{2})[,\.]\d{3}\s*-->\s*(\d{1,2}:\d{2}:\d{2})[,\.]\d{3}')
    cur_time = None
    cur_texts = []
    
    for line in lines:
        line_s = line.strip()
        if not line_s:
            if cur_time and cur_texts:
                text_block = " ".join(cur_texts).strip()
                if text_block:
                    condensed_entries.append(f"[{cur_time}] {text_block}")
                cur_time = None
                cur_texts = []
            continue
            
        if line_s.isdigit():
            continue
            
        m = time_pattern.search(line_s)
        if m:
            if cur_time and cur_texts:
                text_block = " ".join(cur_texts).strip()
                if text_block:
                    condensed_entries.append(f"[{cur_time}] {text_block}")
                cur_texts = []
            cur_time = m.group(1)
        else:
            cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', line_s).strip()
            if cleaned:
                cur_texts.append(cleaned)
                
    if cur_time and cur_texts:
        text_block = " ".join(cur_texts).strip()
        if text_block:
            condensed_entries.append(f"[{cur_time}] {text_block}")
            
    result = "\n".join(condensed_entries)
    return result if result else srt_text

def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    if not text:
        return 0
    try:
        if tiktoken is not None:
            encoding = None
            try:
                encoding = tiktoken.encoding_for_model(model_name)
            except Exception:
                try:
                    encoding = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    encoding = None
            if encoding is not None:
                return len(encoding.encode(text))
    except Exception:
        pass
        
    # Heuristic fallback: An toàn tuyệt đối khi tiktoken không khả dụng hoặc lỗi encoding
    # Trung bình 1 token ~ 3.5 ký tự hoặc ~1.3 từ đối với văn bản/phụ đề
    words = len(text.split())
    chars = len(text)
    return max(1, int(chars / 3.5), int(words * 1.3))

def split_srt_by_tokens(srt_text: str, max_tokens: int = 6000, model_name: str = "gpt-3.5-turbo") -> list:
    """
    Chia srt_text (đã được rút gọn qua condense_srt) thành các chunk, 
    mỗi chunk đảm bảo không vượt quá max_tokens. Cắt ở ranh giới dòng.
    """
    lines = srt_text.splitlines()
    chunks = []
    current_chunk_lines = []
    current_tokens = 0
    
    for line in lines:
        line_tokens = count_tokens(line + "\n", model_name)
        if current_tokens + line_tokens > max_tokens and current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))
            current_chunk_lines = [line]
            current_tokens = line_tokens
        else:
            current_chunk_lines.append(line)
            current_tokens += line_tokens
            
    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))
        
    return chunks

def call_openai_chat_resilient(url, headers, payload, max_retries=3, initial_timeout=240, check_stop_func=None, progress_logger=None):
    """
    Gọi OpenAI/ChatGPT API với cơ chế tự động thử lại (Retry with Exponential Backoff),
    tăng dần thời gian chờ Timeout (240s -> 300s -> 360s) và báo cáo tiến trình.
    """
    timeout = initial_timeout
    last_error = None
    
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=1, pool_connections=5, pool_maxsize=10)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    for attempt in range(1, max_retries + 1):
        if check_stop_func and check_stop_func():
            return None, "Tác vụ đã bị người dùng dừng."
            
        try:
            if attempt > 1 and progress_logger:
                progress_logger(f"🔄 Đang thử gửi lại yêu cầu tới ChatGPT (Lần {attempt}/{max_retries}, Timeout: {timeout}s)...")
                
            res = session.post(url, headers=headers, json=payload, timeout=timeout)
            if res.status_code == 200:
                res_json = res.json()
                if 'error' in res_json:
                    err_info = res_json['error']
                    err_text = err_info.get('message', str(err_info)) if isinstance(err_info, dict) else str(err_info)
                    last_error = f"Lỗi máy chủ AI (HTTP 200 Error): {err_text}"
                    wait_sec = 4 * attempt
                    if progress_logger:
                        progress_logger(f"⚠️ Máy chủ AI thông báo quá tải hoặc lỗi: {err_text[:120]}, tự động thử lại sau {wait_sec}s...")
                    time.sleep(wait_sec)
                    continue
                if 'choices' in res_json and len(res_json['choices']) > 0:
                    content = res_json['choices'][0].get('message', {}).get('content', '')
                    usage = res_json.get('usage', {})
                    return {
                        "content": content,
                        "usage": usage,
                        "raw": res_json
                    }, None
                else:
                    last_error = f"Phản hồi từ AI không chứa dữ liệu choices: {str(res_json)[:200]}"
            elif res.status_code in [429, 500, 502, 503, 504]:
                err_text = res.text[:200]
                last_error = f"Lỗi máy chủ OpenAI/OpenRouter (Mã {res.status_code}): {err_text}"
                wait_sec = 3 * attempt
                if progress_logger:
                    progress_logger(f"⚠️ Máy chủ AI bận (Mã {res.status_code}), tự động chờ {wait_sec}s để thử lại...")
                time.sleep(wait_sec)
            else:
                return None, f"Lỗi API OpenAI/OpenRouter (Mã {res.status_code}): {res.text}"
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as e:
            last_error = f"Quá thời gian chờ phản hồi ({timeout}s) do mạng hoặc phản hồi dài: {str(e)}"
            timeout += 60
            wait_sec = 4 * attempt
            if progress_logger:
                progress_logger(f"⏳ Kết nối ChatGPT bị nghẽn (Timeout {timeout-60}s). Đang nâng thời gian chờ lên {timeout}s...")
            time.sleep(wait_sec)
        except (requests.exceptions.ConnectionError, Exception) as e:
            last_error = f"Lỗi mạng khi kết nối tới OpenAI: {str(e)}"
            wait_sec = 3 * attempt
            if progress_logger:
                progress_logger(f"⚠️ Mạng chập chờn khi gọi OpenAI: {str(e)[:100]}, thử lại sau {wait_sec}s...")
            time.sleep(wait_sec)
            
    return None, f"Không thể kết nối sau {max_retries} lần thử: {last_error}"

def calc_sub_width_ratio(text):
    """Tính tỷ lệ chiều rộng box blur khớp với độ dài câu chữ (chữ ngắn -> blur ngắn, chữ dài -> blur dài)"""
    if not text:
        return 0.35
    clean = text.strip()
    if not clean:
        return 0.35
    units = 0.0
    for char in clean:
        code = ord(char)
        # Ký tự CJK (Trung, Nhật, Hàn)
        if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0xAC00 <= code <= 0xD7AF):
            units += 2.9
        elif char == ' ':
            units += 0.9
        else:
            units += 1.45
    return max(0.12, min(0.92, (units * 1.02 + 4.5) / 100.0))

_last_dynamic_blur_mask_file = None

def format_ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def generate_dynamic_blur_ass_mask(raw_boxes, output_ass_path, play_res_x=10000, play_res_y=10000):
    """
    Tạo tệp phụ đề ASS chứa các hình khối vector màu trắng (mask) trên nền đen
    cho từng khoảng thời gian phụ đề xuất hiện.
    raw_boxes: list of (s_lead, e_trail, w_ratio, center_x_ratio, item_y_ratio, item_h_ratio)
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: MaskBox,Arial,20,&H00FFFFFF,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    for item in raw_boxes:
        s_lead, e_trail, w_ratio, cx_ratio, y_ratio, h_ratio = item
        if e_trail <= s_lead or w_ratio <= 0 or h_ratio <= 0:
            continue
        b = max(0.01, min(0.99, float(w_ratio)))
        h_val = max(0.01, min(0.99, float(h_ratio)))
        x_ratio = max(0.0, min(1.0 - b, float(cx_ratio) - (b / 2.0)))
        y_val = max(0.0, min(1.0 - h_val, float(y_ratio)))
        
        x_px = int(round(x_ratio * play_res_x))
        y_px = int(round(y_val * play_res_y))
        w_px = max(1, int(round(b * play_res_x)))
        h_px = max(1, int(round(h_val * play_res_y)))
        
        t_start = format_ass_time(s_lead)
        t_end = format_ass_time(e_trail)
        ass_lines.append(f"Dialogue: 0,{t_start},{t_end},MaskBox,,0,0,0,,{{\\pos({x_px},{y_px})\\p1}}m 0 0 l {w_px} 0 l {w_px} {h_px} l 0 {h_px}{{\\p0}}")
        
    with open(output_ass_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(ass_lines))
        
    return output_ass_path

def generate_styled_ass(srt_source_path: str, ass_dest_path: str, cur_out_w: int, cur_out_h: int, subtitle_style: dict = None, speed: float = 1.0) -> str:
    """Chuyển đổi file SRT sang ASS với hệ quy chiếu PlayResX/PlayResY chuẩn xác 1:1 với kích thước video xuất.
    Tính toán font size, viền (outline), màu sắc, lề và vị trí chuẩn."""
    if subtitle_style is None:
        subtitle_style = {}
    entries = parse_srt_entries(srt_source_path)
    font_name = re.sub(r'[^\w .-]', '', str(subtitle_style.get('font', 'Montserrat')))[:80] or 'Montserrat'

    base_font_size = max(8, min(120, int(subtitle_style.get('size', 24))))
    font_size = max(12, int(round(base_font_size * (cur_out_h / 720.0))))

    def hex_to_ass(hex_val, default='&H00FFFFFF'):
        if not hex_val:
            return default
        h = str(hex_val).lstrip('#')
        if len(h) == 6:
            return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
        return default

    primary_col = hex_to_ass(subtitle_style.get('color'), '&H00FFFFFF')
    outline_col = hex_to_ass(subtitle_style.get('outline_color'), '&H00000000')

    raw_outline = subtitle_style.get('outline')
    if raw_outline is not None and int(raw_outline) == 0:
        outline_w = 0
    else:
        outline_val = int(raw_outline) if raw_outline is not None else 1
        outline_w = max(0, min(15, int(round(outline_val * (cur_out_h / 720.0)))))

    bold_flag = -1 if parse_bool(subtitle_style.get('bold'), True) else 0
    italic_flag = -1 if parse_bool(subtitle_style.get('italic'), False) else 0
    is_uppercase = parse_bool(subtitle_style.get('uppercase'), False)

    sub_region = subtitle_style.get('region') or {}
    sub_align = str(subtitle_style.get('align') or 'center').lower()
    sub_x = float(sub_region.get('x', 10.0))
    sub_y = float(sub_region.get('y', 81.5))
    sub_w = float(sub_region.get('w', 80.0))
    sub_h = float(sub_region.get('h', 9.5))

    box_x = cur_out_w * sub_x / 100.0
    box_y = cur_out_h * sub_y / 100.0
    box_w = max(10.0, cur_out_w * sub_w / 100.0)
    box_h = max(10.0, cur_out_h * sub_h / 100.0)
    center_x = box_x + box_w / 2.0
    center_y = box_y + box_h / 2.0
    if sub_align == 'left':
        ass_align, an_tag, pos_x = 4, r'\an4', round(box_x)
    elif sub_align == 'right':
        ass_align, an_tag, pos_x = 6, r'\an6', round(box_x + box_w)
    else:
        ass_align, an_tag, pos_x = 5, r'\an5', round(center_x)
    pos_y = round(center_y)
    margin_v = max(5, int(round(cur_out_h - (box_y + box_h))))
    margin_l = max(5, int(round(box_x)))
    margin_r = max(5, int(round(cur_out_w - (box_x + box_w))))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {cur_out_w}\n"
        f"PlayResY: {cur_out_h}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_col},&H000000FF,{outline_col},&H80000000,"
        f"{bold_flag},{italic_flag},0,0,100,100,0,0,1,{outline_w},0,"
        f"{ass_align},{margin_l},{margin_r},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    spd = max(0.01, float(speed))
    events = []
    override_tag = f"{{{an_tag}\\pos({pos_x},{pos_y})}}"
    for s, e, txt in entries:
        t_start = format_ass_time(s / spd)
        t_end = format_ass_time(e / spd)
        txt_display = txt.upper() if is_uppercase else txt
        txt_display = txt_display.replace('\\N', ' ').replace('\n', '\\N')
        events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{override_tag}{txt_display}\n")

    os.makedirs(os.path.dirname(os.path.abspath(ass_dest_path)), exist_ok=True)
    with open(ass_dest_path, 'w', encoding='utf-8') as f:
        f.write(header + "".join(events))

    return ass_dest_path

def build_dynamic_blur_filter_chain(curr_v, active_intervals, blur_sz=15, y_ratio=0.815, h_ratio=0.095, center_x_ratio=0.50, lead_sec=0.18, pad_sec=0.22, manual_mode=False, manual_w=None, engine='auto', temp_dir=None, frame_w=10000, frame_h=10000, content_h=None):
    """Xây dựng filter FFmpeg blur tự động bám sát chữ phụ đề theo độ dài và thời gian.
    Hỗ trợ 2 engine:
    1. 'mask' (Timeline Masking): Dùng ASS vector mask + RGB full-range maskedmerge (gbrp). Cố định 5 filter nodes,
       giảm 99% RAM (từ >1.8GB xuống ~80MB), triệt tiêu hoàn toàn rò rỉ dải màu YUV limited range và khớp preview.
    2. 'legacy' (Crop/Overlay): Tạo filter chain truyền thống cho tác vụ nhỏ/kiểm thử.
    3. 'auto': Tự động chuyển sang 'mask' khi số lượng câu thoại > 25.
    """
    global _last_dynamic_blur_mask_file
    raw_list = []
    has_any_per_entry_box = False
    for item in active_intervals:
        box_x = None
        box_w = None
        box_y = None
        box_h = None
        vis_s = None
        vis_e = None
        if isinstance(item, dict):
            s = float(item.get('start', item.get('startSeconds', 0)))
            e = float(item.get('end', item.get('endSeconds', 0)))
            txt = str(item.get('text', ''))
            box = item.get('box') or item
            if isinstance(box, dict) and 'x_pct' in box and 'w_pct' in box:
                box_x = float(box['x_pct']) / 100.0
                box_w = float(box['w_pct']) / 100.0
                box_y = float(box.get('y_pct', 81.5)) / 100.0
                box_h = float(box.get('h_pct', 9.5)) / 100.0
                vis_s = float(box.get('visual_start')) if box.get('visual_start') is not None else None
                vis_e = float(box.get('visual_end')) if box.get('visual_end') is not None else None
        elif len(item) >= 9:
            s, e, txt, box_x, box_w, box_y, box_h, vis_s, vis_e = item[:9]
        elif len(item) >= 7:
            s, e, txt, box_x, box_w, vis_s, vis_e = item[0], item[1], item[2], item[3], item[4], item[5], item[6]
        elif len(item) >= 5:
            s, e, txt, box_x, box_w = item[0], item[1], item[2], item[3], item[4]
        elif len(item) == 3:
            s, e, txt = item
        else:
            s, e = item[0], item[1]
            txt = ""
            
        s_lead = max(0.0, float(s) - lead_sec)
        if vis_s is not None and float(vis_s) >= 0:
            s_lead = min(s_lead, float(vis_s))

        e_trail = float(e) + pad_sec
        if vis_e is not None and float(vis_e) > float(e):
            e_trail = max(e_trail, float(vis_e))
        
        item_center_x = center_x_ratio
        item_y = y_ratio
        item_h = h_ratio
        if box_w is not None and float(box_w) > 0:
            raw_w = max(0.01, min(0.98, float(box_w)))
            pad_w = max(0.015, min(0.04, raw_w * 0.05))
            w = min(0.98, raw_w + (pad_w * 2.0))
            has_any_per_entry_box = True
            if box_x is not None and float(box_x) >= 0:
                item_center_x = float(box_x) + (raw_w / 2.0)
            if box_y is not None and box_h is not None and float(box_h) > 0:
                raw_y = max(0.0, min(0.99, float(box_y)))
                raw_h = max(0.01, min(0.99 - raw_y, float(box_h)))
                # Đệm an toàn ôm khít chiều cao dòng chữ thực tế
                pad_h = max(0.008, min(0.025, raw_h * 0.18))
                
                # Cho phép người dùng tùy chỉnh chiều cao hộp làm mờ qua h_ratio (thanh trượt blurHeight / khung kéo)
                # trong khi chiều ngang vẫn tự động bám theo câu chữ AI (w)
                is_multiline = (('\n' in txt) or ('\\N' in txt) or ('\\n' in txt)) and (h_ratio is not None and float(h_ratio) > 0 and raw_h > float(h_ratio))
                if h_ratio is not None and float(h_ratio) > 0:
                    user_h = float(h_ratio)
                    if is_multiline:
                        item_h = min(0.40, max(user_h, raw_h + (pad_h * 2.0)))
                    else:
                        item_h = min(0.40, max(raw_h + (pad_h * 2.0), user_h * 0.85))
                else:
                    item_h = min(0.35, max(0.03, raw_h + (pad_h * 2.0)))
                item_y = max(0.0, min(0.98 - item_h, raw_y + (raw_h / 2.0) - (item_h / 2.0)))
        elif manual_mode and manual_w is not None and float(manual_w) > 0:
            w = float(manual_w)
        else:
            w = calc_sub_width_ratio(txt)
            if manual_w is not None and float(manual_w) > 0:
                w = min(w, float(manual_w))
            is_multiline = ('\n' in txt) or ('\\N' in txt)
            if is_multiline:
                item_h = min(0.25, max(h_ratio, 0.11))
                item_y = max(0.0, min(0.98 - item_h, y_ratio - (item_h - h_ratio) / 2.0))
            else:
                item_h = min(h_ratio, 0.075) if h_ratio > 0.08 else h_ratio
                item_y = y_ratio
            
        raw_list.append((s_lead, e_trail, w, item_center_x, item_y, item_h))

    if not raw_list:
        return [], curr_v

    # 1. Sắp xếp theo dòng thời gian
    sorted_raw = sorted(raw_list, key=lambda x: x[0])

    # KỊCH BẢN A: VÙNG BLUR CỐ ĐỊNH (Manual Mode hoặc các box phụ đề đồng nhất)
    # Tối ưu siêu tốc: gộp interval, dùng crop + avgblur + overlay với biểu thức enable.
    # Tránh hoàn toàn split=3, format=gbrp, geq và maskedmerge, tăng tốc độ từ 1.1x lên ~7.5x - 8.0x.
    if manual_mode or not has_any_per_entry_box:
        merged_intervals = []
        for it in sorted_raw:
            s, e = it[0], it[1]
            if not merged_intervals:
                merged_intervals.append([s, e])
            else:
                # Gộp nếu hai khoảng cách nhau dưới 0.35s hoặc gối đầu nhau
                if s <= merged_intervals[-1][1] + 0.35:
                    merged_intervals[-1][1] = max(merged_intervals[-1][1], e)
                else:
                    merged_intervals.append([s, e])

        fixed_w = float(manual_w) if (manual_w is not None and float(manual_w) > 0) else sorted_raw[0][2]
        fixed_w = max(0.05, min(0.98, fixed_w))
        fixed_center_x = center_x_ratio if center_x_ratio is not None else 0.50
        fixed_x = max(0.0, min(1.0 - fixed_w, fixed_center_x - (fixed_w / 2.0)))
        fixed_h = max(0.02, min(0.40, float(h_ratio if h_ratio is not None else 0.095)))
        fixed_y = max(0.0, min(1.0 - fixed_h, float(y_ratio if y_ratio is not None else 0.815)))

        filter_chain = []
        curr = curr_v
        step = 0
        CHUNK_SIZE = 30
        for i in range(0, len(merged_intervals), CHUNK_SIZE):
            chunk = merged_intervals[i:i + CHUNK_SIZE]
            enable_expr = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in chunk)
            next_v = f"v_fixblur_{step}"
            filter_chain.append(f"[{curr}]split[v_bbase_{step}][v_bcrop_{step}]")
            filter_chain.append(
                f"[v_bcrop_{step}]crop=iw*{fixed_w:.3f}:ih*{fixed_h:.3f}:iw*{fixed_x:.3f}:ih*{fixed_y:.3f},"
                f"avgblur=sizeX={blur_sz}:sizeY={blur_sz},eq=brightness=-0.05[v_bblur_{step}]"
            )
            filter_chain.append(
                f"[v_bbase_{step}][v_bblur_{step}]overlay=main_w*{fixed_x:.3f}:main_h*{fixed_y:.3f}:enable='{enable_expr}'[{next_v}]"
            )
            curr = next_v
            step += 1

        return filter_chain, curr

    # KỊCH BẢN B: VÙNG BLUR ĐỘNG THEO TỪNG CÂU (has_any_per_entry_box == True)
    # Dùng Timeline Masking ASS nâng cao nhưng loại bỏ triệt để bottleneck format=gbrp và geq.
    # Chạy trực tiếp trên YUV420p với lut O(1) per pixel và avgblur SIMD.
    if engine == 'mask' or (engine == 'auto' and (len(sorted_raw) > 30 or has_any_per_entry_box)):
        try:
            if not temp_dir:
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'editor_temp')
            os.makedirs(temp_dir, exist_ok=True)
            u_hex = uuid.uuid4().hex[:4] if 'uuid' in globals() else f"{random.randint(1000, 9999)}"
            tag_id = f"{int(time.time()*1000)%100000}_{u_hex}"
            mask_ass_path = os.path.join(temp_dir, f"dynamic_blur_mask_{tag_id}.ass")
            play_res_x = frame_w or 1280
            play_res_y = frame_h or 720
            mask_boxes = [(it[0], it[1], it[2], it[3], it[4], it[5]) for it in sorted_raw]
            generate_dynamic_blur_ass_mask(mask_boxes, mask_ass_path, play_res_x=play_res_x, play_res_y=play_res_y)
            _last_dynamic_blur_mask_file = mask_ass_path

            escaped_ass = mask_ass_path.replace('\\', '/').replace(':', r'\:')
            next_v = f"v_dynblur_{tag_id}"
            effective_h = content_h or 720
            blur_val = max(3, min(60, int(blur_sz * effective_h / 720.0)))
            filter_chain = [
                f"[{curr_v}]split=3[v_b_orig_{tag_id}][v_b_blur_{tag_id}][v_b_mask_{tag_id}]",
                f"[v_b_orig_{tag_id}]format=yuv420p[v_b_orig_yuv_{tag_id}]",
                f"[v_b_blur_{tag_id}]avgblur=sizeX={blur_val}:sizeY={blur_val},lut=y='val*0.94'[v_b_blur_yuv_{tag_id}]",
                f"[v_b_mask_{tag_id}]drawbox=c=black:t=fill,subtitles=filename='{escaped_ass}',format=yuv420p,lut=y='if(gt(val,80),255,0)':u=128:v=128[v_b_mask_yuv_{tag_id}]",
                f"[v_b_orig_yuv_{tag_id}][v_b_blur_yuv_{tag_id}][v_b_mask_yuv_{tag_id}]maskedmerge[{next_v}]"
            ]
            return filter_chain, next_v
        except Exception as e_mask:
            try:
                print(f"[Dynamic Blur] Warning creating timeline mask: {e_mask}. Fallback to buckets/groups.")
            except Exception:
                pass

    groups = []
    for it in sorted_raw:
        if not groups:
            groups.append([it[0], it[1], it[2], it[3]])
        else:
            # Chế độ AI Dynamic: Gộp khi 2 câu cách nhau rất ngắn (<= 0.25s) VÀ có độ rộng tương đồng (sai số <= 18%)
            if it[0] <= groups[-1][1] + 0.25 and abs(it[2] - groups[-1][2]) <= 0.18:
                groups[-1][1] = max(groups[-1][1], it[1])
                groups[-1][2] = max(groups[-1][2], it[2])
                groups[-1][3] = (groups[-1][3] + it[3]) / 2.0
            else:
                groups.append([it[0], it[1], it[2], it[3]])

    # aiBox fallback: chỉ gom nhóm theo precision groups nếu số lượng nhóm nhỏ (<= 25 nhóm)
    # để tránh tràn bộ lọc FFmpeg làm đơ hoặc sập tiến trình xuất video.
    if has_any_per_entry_box:
        precision_groups = {}
        for s, e, w, center, item_y, item_h in sorted_raw:
            key = (round(w, 2), round(center, 2), round(item_y, 2), round(item_h, 2))
            precision_groups.setdefault(key, []).append((s, e))
        if len(precision_groups) <= 25:
            filter_chain = []
            curr = curr_v
            step = 0
            for (b, center, item_y, item_h), intervals in sorted(precision_groups.items()):
                x_ratio = max(0.0, min(1.0 - b, center - (b / 2.0)))
                for pos in range(0, len(intervals), 25):
                    chunk = intervals[pos:pos + 25]
                    enable_expr = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in chunk)
                    next_v = f"v_dynblur_{step}"
                    filter_chain.append(f"[{curr}]split[v_bbase_{step}][v_bcrop_{step}]")
                    filter_chain.append(f"[v_bcrop_{step}]crop=iw*{b:.3f}:ih*{item_h:.3f}:iw*{x_ratio:.3f}:ih*{item_y:.3f},avgblur=sizeX={blur_sz}:sizeY={blur_sz}[v_bblur_{step}]")
                    filter_chain.append(f"[v_bbase_{step}][v_bblur_{step}]overlay=main_w*{x_ratio:.3f}:main_h*{item_y:.3f}:enable='{enable_expr}'[{next_v}]")
                    curr = next_v
                    step += 1
            return filter_chain, curr

    # 2. Phân phối vào các bucket độ rộng tối ưu
    if manual_mode and manual_w is not None and float(manual_w) > 0:
        b_val = round(max(0.05, min(1.0, float(manual_w))), 3)
        BUCKETS = [b_val]
        bucket_map = {b_val: []}
        for g in groups:
            bucket_map[b_val].append((g[0], g[1], g[3]))
    else:
        # Chế độ AI Dynamic: 6 bucket độ rộng linh hoạt ôm sát từ câu cực ngắn (1-2 từ) đến câu dài
        BUCKETS = [0.25, 0.40, 0.55, 0.72, 0.88, 0.96]
        bucket_map = {b: [] for b in BUCKETS}
        for g in groups:
            chosen = next((b for b in BUCKETS if b >= g[2]), BUCKETS[-1])
            bucket_map[chosen].append((g[0], g[1], g[3]))

    filter_chain = []
    curr = curr_v
    step = 0
    MAX_EXPR_CHUNK = 25

    for b in BUCKETS:
        raw_intervals = bucket_map[b]
        if not raw_intervals:
            continue
            
        chunks = [raw_intervals[i:i + MAX_EXPR_CHUNK] for i in range(0, len(raw_intervals), MAX_EXPR_CHUNK)]
        
        for ch in chunks:
            avg_center = sum(c[2] for c in ch) / float(len(ch)) if ch else center_x_ratio
            x_ratio = max(0.0, min(1.0 - b, avg_center - (b / 2.0)))
            enable_expr = "+".join([f"between(t,{s:.2f},{e:.2f})" for s, e, _ in ch])
            next_v = f"v_dynblur_{step}"
            filter_chain.append(f"[{curr}]split[v_bbase_{step}][v_bcrop_{step}]")
            filter_chain.append(f"[v_bcrop_{step}]crop=iw*{b:.3f}:ih*{h_ratio:.3f}:iw*{x_ratio:.3f}:ih*{y_ratio:.3f},avgblur=sizeX={blur_sz}:sizeY={blur_sz}[v_bblur_{step}]")
            filter_chain.append(f"[v_bbase_{step}][v_bblur_{step}]overlay=main_w*{x_ratio:.3f}:main_h*{y_ratio:.3f}:enable='{enable_expr}'[{next_v}]")
            curr = next_v
            step += 1

    return filter_chain, curr

def build_subtitle_filter(curr_v, out_v, srt_path, project_config=None):
    """Xây dựng filter subtitle cho video export tương thích preview style."""
    cfg = project_config or {}
    style = cfg.get("subtitle_style", {})
    font_name = style.get("font", "Arial")
    font_size = style.get("size", 24)
    color_hex = str(style.get("color", "#FFFFFF")).lstrip("#")
    outline_hex = str(style.get("outline_color", "#000000")).lstrip("#")

    if len(color_hex) == 6:
        r, g, b = color_hex[0:2], color_hex[2:4], color_hex[4:6]
        primary_color = f"&H00{b}{g}{r}".upper()
    else:
        primary_color = "&H00FFFFFF"

    if len(outline_hex) == 6:
        r, g, b = outline_hex[0:2], outline_hex[2:4], outline_hex[4:6]
        outline_color = f"&H00{b}{g}{r}".upper()
    else:
        outline_color = "&H00000000"

    bold_flag = "-1" if style.get("bold") else "0"
    italic_flag = "-1" if style.get("italic") else "0"
    outline_w = style.get("outline", 2)

    escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:")
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "fonts").replace("\\", "/").replace(":", "\\:")
    force_style = f"Fontname={font_name},Fontsize={font_size},PrimaryColour={primary_color},OutlineColour={outline_color},Outline={outline_w},Bold={bold_flag},Italic={italic_flag}"
    return f"[{curr_v}]subtitles=filename='{escaped_srt}':fontsdir='{fonts_dir}':force_style='{force_style}'[{out_v}]"

def is_statistical_or_meta_sentence(sentence: str) -> bool:
    """Kiểm tra xem câu có phải là thống kê số từ / thời lượng / ghi chú của LLM hay không."""
    if not sentence:
        return True
    s = re.sub(r'[\*\_\#\`\[\]\(\)]', '', sentence).strip()
    if not s or len(s) <= 1:
        return True
    lower = s.lower()
    
    # 1. Các tiền tố thống kê phổ biến
    stat_prefixes = (
        'tổng số từ', 'số từ thực tế', 'tổng số chữ', 'thời lượng đọc', 
        'thời lượng ước tính', 'ước tính thời lượng', 'tốc độ đọc', 'tổng cộng:', 
        'total words', 'word count', 'reading time', 'estimated time',
        'lưu ý:', 'ghi chú:', 'chú thích:', 'note:', 'bối cảnh tiếp nối:'
    )
    if any(lower.startswith(p) for p in stat_prefixes):
        return True
        
    # 2. Chứa cả 'tổng số từ' hoặc 'số từ' đi kèm số lượng từ
    if ('tổng số từ' in lower or 'số từ' in lower) and ('khoảng' in lower or 'thực tế' in lower or re.search(r'\d+[\.,]?\d*\s*từ', lower)):
        return True
        
    # 3. Chứa 'thời lượng' và số phút/giây
    if 'thời lượng' in lower and ('ước tính' in lower or 'đối chiếu' in lower or re.search(r'\d+\s*(?:phút|giây|s|m)', lower)):
        return True

    # 4. Ký hiệu kết thúc kịch bản
    if lower in ('hết.', 'kết thúc kịch bản.', 'the end.', 'hết kịch bản.', '--- hết ---', '---'):
        return True
        
    return False


def sanitize_review_script(text: str) -> str:
    """Loại bỏ triệt để các đoạn thống kê số từ, thời lượng, ghi chú thừa mà AI tự thêm vào đầu/cuối kịch bản."""
    if not text:
        return ""
    
    lines = text.strip().split('\n')
    
    # 1. Dò từ cuối lên để cắt bỏ các dòng thống kê / ghi chú
    end_idx = len(lines)
    while end_idx > 0:
        line_to_check = lines[end_idx - 1].strip()
        if not line_to_check:
            end_idx -= 1
            continue
        
        # Dòng phân cách (---, ***, ===)
        if re.match(r'^[\-\*\=\_]{3,}$', line_to_check):
            end_idx -= 1
            continue
            
        clean_strip = re.sub(r'[\*\_\#\`\[\]\(\)]', '', line_to_check).strip()
        if is_statistical_or_meta_sentence(clean_strip):
            end_idx -= 1
            continue
            
        break
        
    lines = lines[:end_idx]
    
    # 2. Dò từ đầu xuống loại bỏ preamble thừa nếu có
    start_idx = 0
    preamble_pattern = re.compile(
        r'^(?:dưới đây là|đây là|kịch bản review|bản kịch bản|chào bạn|sau đây là).*(?:kịch bản|voice|thu âm|hoàn chỉnh)[\:\.]?$',
        re.IGNORECASE
    )
    while start_idx < len(lines):
        line_to_check = lines[start_idx].strip()
        if not line_to_check:
            start_idx += 1
            continue
        if preamble_pattern.match(line_to_check):
            start_idx += 1
            continue
        break
        
    lines = lines[start_idx:]
    return "\n".join(lines).strip()


def split_text_to_sentences(text):
    """Tách văn bản thành các câu riêng biệt để TTS từng câu (đã lọc sạch thống kê/ghi chú thừa)."""
    text = sanitize_review_script(text)
    if not text:
        return []
    # Tách theo dấu câu kết thúc (.!? hoặc 。！？) hoặc xuống dòng kép
    raw_parts = re.split(r'(?<=[.!?。！？])\s*|\n{2,}', text)
    sentences = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        # Nếu câu quá dài (>80 ký tự), cố tách thêm ở dấu phẩy/chấm phẩy (kể cả CJK ，；)
        if len(part) > 80:
            sub_parts = re.split(r'(?<=[,;，；])\s*', part)
            buffer = ""
            for sp in sub_parts:
                if buffer and len(buffer) + len(sp) > 70:
                    sentences.append(buffer.strip())
                    buffer = sp
                else:
                    buffer = (buffer + " " + sp).strip() if buffer else sp
            if buffer:
                sentences.append(buffer.strip())
        else:
            sentences.append(part)
    return [s for s in sentences if len(s) > 1 and not is_statistical_or_meta_sentence(s)]

def enforce_max_2_lines_srt(srt_entries, max_chars_per_line=40):
    """Đảm bảo mỗi block SRT chỉ hiện tối đa 2 dòng trên màn hình.
    Nếu text dài hơn 2 dòng, tách thành nhiều block kế tiếp."""
    result = []
    for start, end, text in srt_entries:
        text = text.strip()
        if not text:
            continue
        words = text.split()
        # Tính số dòng nếu wrap ở max_chars_per_line
        lines = []
        current_line = ""
        for word in words:
            if current_line and len(current_line) + 1 + len(word) > max_chars_per_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = (current_line + " " + word).strip() if current_line else word
        if current_line:
            lines.append(current_line)
        
        if len(lines) <= 2:
            # OK, giữ nguyên (dùng \N cho 2 dòng nếu cần)
            display_text = "\n".join(lines)
            result.append((start, end, display_text))
        else:
            # Tách thành nhiều block, mỗi block tối đa 2 dòng
            total_dur = end - start
            total_chars = sum(len(l) for l in lines)
            chunks = []
            i = 0
            while i < len(lines):
                chunk_lines = lines[i:i+2]
                chunks.append("\n".join(chunk_lines))
                i += 2
            # Phân bổ thời gian theo tỷ lệ ký tự
            cursor = start
            for i, chunk_text in enumerate(chunks):
                chunk_chars = len(chunk_text.replace("\n", ""))
                chunk_dur = (total_dur * chunk_chars / total_chars) if total_chars > 0 else (total_dur / len(chunks))
                
                # To prevent float precision issues leaving a gap at the very end
                if i == len(chunks) - 1:
                    chunk_end = end
                else:
                    chunk_end = cursor + chunk_dur
                    
                result.append((cursor, chunk_end, chunk_text))
                cursor = chunk_end
    return result

def get_video_duration_ffprobe(video_path):
    """Lấy duration video bằng ffprobe, ffmpeg -i fallback, hoặc cv2 fallback."""
    if not video_path or not os.path.exists(video_path):
        return 0.0

    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    
    # 1. Thử ffprobe nếu có binary
    ffprobe_candidates = []
    if os.name == 'nt':
        ffprobe_candidates.append(os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe'))
    ffprobe_candidates.append('ffprobe')
    
    for ff_p in ffprobe_candidates:
        if os.path.exists(ff_p) or ff_p == 'ffprobe':
            try:
                cmd = [ff_p, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
                res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, **get_stealth_subprocess_kwargs()).strip()
                val = float(res)
                if val > 0:
                    return val
            except Exception:
                pass

    # 2. Thử ffmpeg -i stderr inspection (luôn hoạt động vì ffmpeg.exe luôn có sẵn)
    try:
        cmd = [ffmpeg_path, '-i', video_path]
        proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', **get_stealth_subprocess_kwargs())
        m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', proc.stderr)
        if m:
            h, mins, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            val = h * 3600 + mins * 60 + s
            if val > 0:
                return val
    except Exception:
        pass

    # 3. Fallback OpenCV
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            if fps > 0 and frames > 0:
                return float(frames / fps)
    except Exception:
        pass

    return 0.0

def get_video_dimensions_fast(video_path, ffmpeg_path=None):
    """Lấy kích thước chiều rộng/cao video chuẩn xác."""
    if not video_path or not os.path.exists(video_path):
        return 1920, 1080
    if not ffmpeg_path:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    ffprobe_candidates = []
    if os.name == 'nt':
        ffprobe_candidates.append(os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe'))
    ffprobe_candidates.append('ffprobe')
    for ff_p in ffprobe_candidates:
        if os.path.exists(ff_p) or ff_p == 'ffprobe':
            try:
                cmd = [
                    ff_p, '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height', '-of', 'json', video_path
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, **get_stealth_subprocess_kwargs())
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    streams = data.get('streams', [])
                    if streams:
                        w = int(streams[0].get('width', 0) or 0)
                        h = int(streams[0].get('height', 0) or 0)
                        if w > 0 and h > 0:
                            return w, h
            except Exception:
                pass
    return 1920, 1080

def run_ffmpeg_with_progress_yield(cmd, total_duration, start_pct, end_pct, desc, check_stop_func=None):
    """Chạy FFmpeg và yield % tiến độ dựa trên time= trong output."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        **get_stealth_subprocess_kwargs()
    )
    last_reported_pct = -1
    last_report_time = 0
    time_regex = re.compile(r'time=(\d+):(\d+):([0-9.]+)')
    error_lines = []

    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        if check_stop_func and check_stop_func():
            process.terminate()
            yield f"data: 🛑 Đã dừng tiến trình {desc}.\n\n"
            return False

        line_str = line.strip()
        if 'error' in line_str.lower() or 'fatal' in line_str.lower():
            error_lines.append(line_str)

        m = time_regex.search(line_str)
        if m and total_duration > 0:
            hrs = int(m.group(1))
            mins = int(m.group(2))
            secs = float(m.group(3))
            cur_sec = hrs * 3600 + mins * 60 + secs
            render_ratio = min(1.0, cur_sec / total_duration)
            overall_pct = int(start_pct + ((end_pct - start_pct) * render_ratio))
            now = time.time()
            if overall_pct >= last_reported_pct + 2 or (now - last_report_time > 2.0 and overall_pct > last_reported_pct):
                yield f"data: ⚙️ {desc}: {cur_sec:.0f}s/{total_duration:.0f}s ({overall_pct}%)\n\n"
                yield f"data: [PROGRESS] {overall_pct}\n\n"
                last_reported_pct = overall_pct
                last_report_time = now

    process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        if check_stop_func and check_stop_func():
            yield f"data: 🛑 Đã dừng tiến trình {desc}.\n\n"
            return False
        err_msg = "\n".join(error_lines[-5:]) if error_lines else f"Exit code {return_code}"
        yield f"data: 🛑 Lỗi khi {desc}: {err_msg}\n\n"
        return False
    return True

def generate_tts_per_sentence_stream(sentences, voice_id, speed, temp_dir, api_key_openspeaker='', check_stop_func=None, start_pct=20, end_pct=40, threads=8, use_cache=False):
    """
    Tạo TTS cho từng câu theo cơ chế đa luồng (Multi-threading) và yield progress real-time.
    Yields:
      ('progress', (completed_count, total, step_pct, overall_pct, snippet))
      ('error', error_str)
      ('done', (final_audio, final_srt, srt_entries))
    """
    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe') if os.name == 'nt' else 'ffprobe'
    
    sentence_dir = os.path.join(temp_dir, 'sentences')
    if not use_cache and os.path.exists(sentence_dir):
        try:
            shutil.rmtree(sentence_dir, ignore_errors=True)
        except Exception:
            pass
    os.makedirs(sentence_dir, exist_ok=True)
    
    is_kokoro = voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh']
    tts_url = "http://127.0.0.1:5000/api/tts/kokoro" if is_kokoro else "http://127.0.0.1:5000/api/tts/openspeaker"
    
    total = len(sentences)
    if total == 0:
        yield 'error', "Không có câu nào để tạo TTS."
        return

    num_threads = max(1, min(10, int(threads or 8)))
    results_map = {}
    error_holder = []
    
    def process_sentence(idx, sentence):
        if check_stop_func and check_stop_func():
            return None
            
        filename = f"sent_{idx}.wav" if is_kokoro else f"sent_{idx}.mp3"
        wav_path = os.path.join(sentence_dir, f"sent_{idx}_pcm.wav")
        
        # Nếu đã có file WAV hợp lệ (từ cache/lần chạy trước) VÀ use_cache=True thì tái sử dụng
        if use_cache and os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
            dur = 2.0
            try:
                import wave
                with wave.open(wav_path, 'rb') as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        dur = frames / float(rate)
            except Exception:
                dur = get_video_duration_ffprobe(wav_path)
                if dur <= 0: dur = 2.0
            return idx, wav_path, dur, sentence

        tts_payload = {
            "text": sentence,
            "voice_id": voice_id,
            "speed": speed,
            "output_dir": sentence_dir,
            "filename": filename,
            "skip_notify": True
        }
        if not is_kokoro and api_key_openspeaker:
            tts_payload['api_key'] = api_key_openspeaker
            
        try:
            res = requests.post(tts_url, json=tts_payload, timeout=120)
            if res.status_code != 200:
                raise Exception(f"Lỗi TTS câu {idx+1}: {res.text}")
        except Exception as e:
            raise Exception(f"Lỗi gọi API TTS câu {idx+1}: {str(e)}")
            
        audio_path = os.path.join(sentence_dir, filename)
        if not os.path.exists(audio_path):
            raise Exception(f"Không tìm thấy file audio câu {idx+1}")
            
        try:
            conv_cmd = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error', '-i', audio_path, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', wav_path]
            subprocess.run(conv_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **get_stealth_subprocess_kwargs())
        except subprocess.CalledProcessError as e:
            raise Exception(f"Lỗi convert WAV câu {idx+1}: {e.stderr.decode() if e.stderr else str(e)}")
            
        dur = 2.0
        try:
            import wave
            with wave.open(wav_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    dur = frames / float(rate)
        except Exception:
            dur = get_video_duration_ffprobe(wav_path)
            if dur <= 0:
                dur = 2.0
                
        return idx, wav_path, dur, sentence

    completed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_idx = {executor.submit(process_sentence, i, s): i for i, s in enumerate(sentences)}
        for future in concurrent.futures.as_completed(future_to_idx):
            if check_stop_func and check_stop_func():
                yield 'error', "STOPPED"
                return
                
            try:
                res = future.result()
                if res:
                    idx, wav_p, dur, sent_text = res
                    results_map[idx] = (wav_p, dur, sent_text)
                    completed_count += 1
                    
                    step_pct = int(completed_count / total * 100)
                    overall_pct = int(start_pct + ((end_pct - start_pct) * completed_count / total))
                    snippet = (sent_text[:35] + '...') if len(sent_text) > 35 else sent_text
                    yield 'progress', (completed_count, total, step_pct, overall_pct, snippet)
            except Exception as e:
                error_holder.append(str(e))
                yield 'error', str(e)
                return

    if error_holder:
        yield 'error', error_holder[0]
        return

    # Sắp xếp đúng thứ tự câu 0 -> total-1
    audio_segments = [results_map[i] for i in range(total) if i in results_map]
    if len(audio_segments) != total:
        yield 'error', f"Lỗi tạo TTS: Chỉ tạo được {len(audio_segments)}/{total} câu."
        return

    # Concat tất cả audio thành 1 file
    concat_list_path = os.path.join(sentence_dir, 'concat.txt')
    with open(concat_list_path, 'w', encoding='utf-8') as f:
        for seg_path, _, _ in audio_segments:
            fname = os.path.basename(seg_path).replace("'", "'\\''")
            f.write(f"file '{fname}'\n")
    
    final_audio = os.path.join(temp_dir, 'voice_review.wav')
    cmd_concat = [
        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0', '-i', concat_list_path,
        '-c:a', 'pcm_s16le',
        final_audio
    ]
    proc = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
    if proc.returncode != 0:
        yield 'error', f"Lỗi concat audio: {proc.stderr}"
        return
    
    # Tạo SRT chính xác từ duration cộng dồn
    final_srt = os.path.join(temp_dir, 'voice_review.srt')
    cursor = 0.0
    srt_entries = []
    with open(final_srt, 'w', encoding='utf-8') as sf:
        for idx, (_, dur, txt) in enumerate(audio_segments):
            s_time = cursor
            e_time = cursor + dur
            sf.write(f"{idx+1}\n")
            sf.write(f"{format_srt_time(s_time)} --> {format_srt_time(e_time)}\n")
            sf.write(f"{txt}\n\n")
            srt_entries.append((s_time, e_time, txt))
            cursor = e_time
    
    yield 'done', (final_audio, final_srt, srt_entries)

def generate_tts_per_sentence(sentences, voice_id, speed, temp_dir, api_key_openspeaker='', check_stop_func=None, start_pct=20, end_pct=40, threads=8, use_cache=False):
    final_audio = None
    final_srt = None
    srt_entries = []
    error = None
    for msg_type, data in generate_tts_per_sentence_stream(sentences, voice_id, speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct, end_pct, threads, use_cache=use_cache):
        if msg_type == 'error':
            error = data
        elif msg_type == 'done':
            final_audio, final_srt, srt_entries = data
    return final_audio, final_srt, srt_entries, error

def validate_rendered_video(video_path: str, expected_duration: float = None, ffmpeg_path: str = None) -> Tuple[bool, Dict[str, Any]]:
    """
    POST-RENDER VALIDATOR:
    Dùng ffprobe kiểm tra chi tiết tính hợp lệ và đồng bộ của file video đã xuất:
    - Thời lượng stream video và audio
    - Kiểm tra PTS discontinuity (PTS giảm hoặc nhảy vọt)
    - Độ lệch so với Master Voice Clock
    """
    report = {
        "is_valid": True,
        "video_duration": 0.0,
        "audio_duration": 0.0,
        "drift_ms": 0.0,
        "pts_drop_detected": False,
        "warnings": [],
        "errors": []
    }
    if not video_path or not os.path.exists(video_path):
        report["is_valid"] = False
        report["errors"].append("File video đầu ra không tồn tại.")
        return False, report

    if not ffmpeg_path:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe') if (ffmpeg_path and os.name == 'nt') else 'ffprobe'

    try:
        cmd = [
            ffprobe_path, '-v', 'error',
            '-show_entries', 'stream=index,codec_type,duration,r_frame_rate:format=duration',
            '-of', 'json',
            video_path
        ]
        out = subprocess.check_output(cmd, **get_stealth_subprocess_kwargs()).decode('utf-8', errors='replace')
        data = json.loads(out)
        fmt_dur = float(data.get('format', {}).get('duration') or 0.0)
        report["video_duration"] = round(fmt_dur, 3)

        streams = data.get('streams', [])
        for s in streams:
            if s.get('codec_type') == 'audio':
                report["audio_duration"] = round(float(s.get('duration') or fmt_dur), 3)

        if expected_duration is not None and expected_duration > 0:
            drift = abs(report["video_duration"] - expected_duration) * 1000.0
            report["drift_ms"] = round(drift, 1)
            if drift > 80.0:
                report["warnings"].append(f"Thời lượng video ({report['video_duration']:.2f}s) lệch so với voice ({expected_duration:.2f}s) {drift:.1f}ms (> 80ms).")

        # Kiểm tra tính liên tục của PTS (pkt_pts không được giảm)
        cmd_pkt = [
            ffprobe_path, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'packet=pts_time',
            '-read_intervals', '%+4,%-4',
            '-of', 'json',
            video_path
        ]
        out_pkt = subprocess.check_output(cmd_pkt, **get_stealth_subprocess_kwargs()).decode('utf-8', errors='replace')
        pkt_data = json.loads(out_pkt)
        packets = pkt_data.get('packets', [])
        prev_pts = -1.0
        for p in packets:
            pts_val = p.get('pts_time')
            if pts_val is not None:
                try:
                    cur_pts = float(pts_val)
                    if cur_pts < prev_pts - 0.001:
                        report["pts_drop_detected"] = True
                        report["warnings"].append(f"Phát hiện PTS giảm (PTS drop): {prev_pts:.3f}s -> {cur_pts:.3f}s.")
                        break
                    prev_pts = cur_pts
                except Exception:
                    pass
    except Exception as e:
        report["warnings"].append(f"Không thể chạy ffprobe validation: {str(e)}")

    if len(report["errors"]) > 0:
        report["is_valid"] = False
    return report["is_valid"], report


def resolve_openai_credentials(payload=None):
    if payload is None:
        payload = {}
    openai_key = payload.get('openai_key')
    openai_base_url = payload.get('openai_base_url') or 'https://api.openai.com/v1'
    openai_model = payload.get('openai_model') or 'gpt-5.6-luna'
    
    if not openai_key or not str(openai_key).strip() or str(openai_key).startswith('•'):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_files = [
            os.path.join(root_dir, 'api_keys.txt'),
            'api_keys.txt'
        ]
        try:
            import license_manager
            candidate_files.append(os.path.join(license_manager.get_user_data_dir(), 'api_keys.txt'))
        except Exception:
            pass

        for api_keys_file in candidate_files:
            if os.path.exists(api_keys_file):
                try:
                    with open(api_keys_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('openaiKey='):
                                openai_key = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiBaseUrl=') and (not openai_base_url or openai_base_url == 'https://api.openai.com/v1'):
                                openai_base_url = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiModel=') and (not openai_model or openai_model in ['gpt-5.6-luna', 'gpt-5.6-luna']):
                                openai_model = line.strip().split('=', 1)[1]
                    if openai_key and not openai_key.startswith('•'):
                        break
                except Exception:
                    pass

        if not openai_key:
            try:
                import license_manager
                st = license_manager.get_current_license_status()
                vk = st.get('vip_api_keys') or {}
                if isinstance(vk, dict):
                    openai_key = vk.get('openaiKey') or vk.get('openai_key') or vk.get('api_key')
            except Exception:
                pass

        if not openai_key:
            openai_key = os.environ.get('OPENAI_API_KEY')

    if openai_key:
        openai_key = str(openai_key).strip()
        if openai_key.startswith('sk-or-') and (not openai_base_url or openai_base_url == 'https://api.openai.com/v1'):
            openai_base_url = 'https://openrouter.ai/api/v1'
        if openai_key.startswith('sk-or-') or 'openrouter.ai' in str(openai_base_url):
            if not openai_model or openai_model in ['gpt-5.6-luna', 'gpt-5.6-luna']:
                openai_model = 'gpt-5.6-luna'

    return openai_key, openai_base_url, openai_model

import threading
import queue

def run_map_reduce_pipeline_sync(openai_key, openai_base_url, openai_model, chunks, target_words, prompt_map, prompt_reduce, temp_dir, log_func, style_directive="", use_cache=False):
    q = queue.Queue()
    
    async def async_worker():
        try:
            import httpx
            from openai import AsyncOpenAI
            client_headers = {}
            is_openrouter = 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-')
            if is_openrouter:
                client_headers = {"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
            
            # Timeout 120s cho mỗi request — tránh treo vĩnh viễn trên Free models
            http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
            client = AsyncOpenAI(
                api_key=openai_key, base_url=openai_base_url,
                default_headers=client_headers if client_headers else None,
                http_client=http_client
            )
            
            # Đối với model Free hoặc OpenRouter: giới hạn concurrency = 1 để tránh lỗi 429 upstream rate limit
            concurrency = 1 if ('free' in str(openai_model).lower() or is_openrouter) else 2
            sem = asyncio.Semaphore(concurrency)
            is_free = 'free' in str(openai_model).lower() or is_openrouter
            
            q.put({"type": "log", "msg": f"🔄 Bắt đầu Map: Xử lý {len(chunks)} đoạn kịch bản (Tuần tự, timeout 120s)..."})

            async def process_chunk(idx, chunk_text):
                prompt = prompt_map.replace("{SỐ_THỨ_TỰ_CHUNK}", str(idx+1))\
                                   .replace("{TỔNG_SỐ_CHUNK}", str(len(chunks)))\
                                   .replace("{NỘI_DUNG_SRT_CHUNK}", chunk_text)\
                                   .replace("{SỐ_TỪ_MỤC_TIÊU_CHUNK}", str(target_words // max(1, len(chunks))))
                
                prev_text = "Không có (đoạn đầu)" if idx == 0 else "\\n".join(chunks[idx-1].splitlines()[-10:])
                prompt = prompt.replace("{TÓM_TẮT_ĐOẠN_TRƯỚC}", prev_text)
                prompt = prompt.replace("{MỐC_THỜI_GIAN_BẮT_ĐẦU}", "Đầu đoạn").replace("{MỐC_THỜI_GIAN_KẾT_THÚC}", "Cuối đoạn")
                
                if style_directive:
                    prompt = f"{style_directive}\n\n{prompt}"

                cache_key = hashlib.md5((chunk_text + prompt + str(openai_model)).encode('utf-8')).hexdigest()
                cache_file = os.path.join(temp_dir, f"chunk_{cache_key}.txt")
                
                if use_cache and os.path.exists(cache_file):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_text = f.read()
                        q.put({"type": "token", "count": len(cached_text)})
                        return cached_text
                        
                async with sem:
                    max_attempts = 5
                    for attempt in range(1, max_attempts + 1):
                        try:
                            q.put({"type": "log", "msg": f"📝 Đoạn {idx+1}/{len(chunks)}: Đang gửi đến AI (lần {attempt})..."})
                            # Dùng NON-streaming cho Map phase — ổn định hơn trên Free models
                            response = await client.chat.completions.create(
                                model=openai_model,
                                messages=[
                                    {"role": "system", "content": "Bạn là chuyên gia review phim hàng đầu."},
                                    {"role": "user", "content": prompt}
                                ]
                            )
                            
                            result = ""
                            if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                                result = response.choices[0].message.content or ""
                            if result.strip():
                                q.put({"type": "token", "count": len(result)})
                                with open(cache_file, 'w', encoding='utf-8') as f:
                                    f.write(result)
                                q.put({"type": "log", "msg": f"✅ Đoạn {idx+1}/{len(chunks)}: Hoàn thành ({len(result)} ký tự)"})
                                return result
                            raise RuntimeError("Phản hồi kịch bản rỗng")
                        except Exception as e:
                            err_msg = str(e)[:120]
                            if attempt < max_attempts:
                                wait_s = 5 * attempt
                                q.put({"type": "log", "msg": f"⏳ Đoạn {idx+1}: Lỗi ({err_msg}), đợi {wait_s}s thử lại ({attempt}/{max_attempts})..."})
                                await asyncio.sleep(wait_s)
                            else:
                                raise RuntimeError(f"Đoạn {idx+1} thất bại sau {max_attempts} lần: {err_msg}")

            # Xử lý Map chunks: Song song cho paid/fast models, tuần tự có giãn cách cho free models
            if is_free:
                map_results = []
                for i, c in enumerate(chunks):
                    result = await process_chunk(i, c)
                    map_results.append(result)
                    if i < len(chunks) - 1:
                        await asyncio.sleep(2)  # Cooldown cho Free models
            else:
                map_tasks = [process_chunk(i, c) for i, c in enumerate(chunks)]
                map_results = await asyncio.gather(*map_tasks)
            
            q.put({"type": "log", "msg": "🔄 Bắt đầu Reduce: Gộp các kịch bản thành một kịch bản hoàn chỉnh..."})
            combined = "\n\n--- ĐOẠN TIẾP THEO ---\n\n".join(map_results)
            prompt_red = prompt_reduce.replace("{NỘI_DUNG_CÁC_ĐOẠN_ĐÃ_GHÉP}", combined)\
                                      .replace("{SỐ_PHÚT}", str(target_words // 210))\
                                      .replace("{SỐ_PHÚT x 270}", str(target_words))\
                                      .replace("{SỐ_PHÚT x 210}", str(target_words))
            
            if style_directive:
                prompt_red = f"{style_directive}\n\n{prompt_red}"

            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                try:
                    q.put({"type": "log", "msg": f"📝 Reduce: Đang gộp kịch bản hoàn chỉnh (lần {attempt})..."})
                    response = await client.chat.completions.create(
                        model=openai_model,
                        messages=[
                            {"role": "system", "content": "Bạn là biên tập viên kịch bản review phim chuyên nghiệp."},
                            {"role": "user", "content": prompt_red}
                        ],
                        stream=True
                    )
                    
                    final_result = ""
                    async for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            final_result += content
                            q.put({"type": "token", "count": len(content)})
                            
                    if final_result.strip():
                        final_result = sanitize_review_script(final_result)
                        q.put({"type": "done", "result": final_result})
                        break
                    raise RuntimeError("Phản hồi Reduce rỗng")
                except Exception as e:
                    err_msg = str(e)[:120]
                    if attempt < max_attempts:
                        wait_s = 5 * attempt
                        q.put({"type": "log", "msg": f"⏳ Reduce: Lỗi ({err_msg}), đợi {wait_s}s thử lại ({attempt}/{max_attempts})..."})
                        await asyncio.sleep(wait_s)
                    else:
                        raise RuntimeError(f"Reduce thất bại sau {max_attempts} lần: {err_msg}")
            
            await http_client.aclose()
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})
            
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_worker())
        
    t = threading.Thread(target=run_loop)
    t.start()
    
    final_script = ""
    token_accum = 0
    last_log = 0
    while True:
        try:
            item = q.get(timeout=2)
            if item["type"] == "log":
                yield log_func(item["msg"])
            elif item["type"] == "token":
                token_accum += item["count"]
                if token_accum - last_log >= 1000:
                    yield log_func(f"⚡ Đang nhận dữ liệu: {token_accum} ký tự...")
                    last_log = token_accum
            elif item["type"] == "done":
                final_script = sanitize_review_script(item["result"])
                yield log_func(f"✅ Hoàn thành tổng cộng {token_accum} ký tự kịch bản.")
                break
            elif item["type"] == "error":
                yield log_func(f"🛑 Lỗi API (Map/Reduce): {item['msg']}")
                return None
        except queue.Empty:
            if not t.is_alive():
                yield log_func("🛑 Luồng xử lý kịch bản kết thúc bất thường mà không có kết quả.")
                return None
    return sanitize_review_script(final_script)

def get_sliding_orig_srt(condensed_orig_srt, batch_idx, total_batches, window_ratio=0.45):
    """
    Trích xuất cửa sổ trượt ngữ cảnh (Sliding Context Window) tương ứng với mẻ kịch bản hiện tại.
    Giảm 60-75% số lượng tokens cần gửi, tăng tốc độ phản hồi của AI gấp 3-4 lần cho Step 3.
    """
    if not condensed_orig_srt or len(condensed_orig_srt) <= 15000 or total_batches <= 1:
        return condensed_orig_srt

    lines = condensed_orig_srt.splitlines()
    total_lines = len(lines)
    if total_lines < 50:
        return condensed_orig_srt

    center_ratio = batch_idx / max(1, total_batches - 1)
    start_ratio = max(0.0, center_ratio - window_ratio / 2.0)
    end_ratio = min(1.0, center_ratio + window_ratio / 2.0)

    start_idx = int(start_ratio * total_lines)
    end_idx = min(total_lines, int(end_ratio * total_lines))

    # Đảm bảo cửa sổ tối thiểu 30% nội dung để không bị hụt ngữ cảnh
    if (end_idx - start_idx) < int(0.3 * total_lines):
        end_idx = min(total_lines, start_idx + int(0.3 * total_lines))

    selected_lines = lines[start_idx:end_idx]
    prefix = f"... [Đã lược bớt {start_idx} dòng phụ đề trước đó] ...\n" if start_idx > 0 else ""
    suffix = f"\n... [Đã lược bớt {total_lines - end_idx} dòng phụ đề phía sau] ..." if end_idx < total_lines else ""
    return prefix + "\n".join(selected_lines) + suffix

def run_timeline_map_reduce_pipeline_sync(
    openai_key, openai_base_url, openai_model,
    voice_entries, condensed_orig_srt, prompt_json_template,
    temp_dir, log_func, batch_size=35, max_concurrency=3, use_cache=False
):
    """
    Xử lý Step 3 theo cơ chế Map-Reduce / Batching:
    - Chia voice_entries (e.g. 906 blocks) thành các batch (mỗi batch ~35 blocks).
    - Gọi API song song với giới hạn concurrency để lấy JSON timeline cho từng batch.
    - Gộp tất cả JSON timeline và sắp xếp theo voice_ref.
    - Fallback thông minh nếu có block bị thiếu hoặc model trả về không chuẩn.
    """
    q = queue.Queue()
    total_voice_blocks = len(voice_entries)
    if total_voice_blocks == 0:
        return []

    # Tạo các batch voice entries
    batches = []
    for i in range(0, total_voice_blocks, batch_size):
        chunk = voice_entries[i:i + batch_size]
        start_ref = i + 1
        end_ref = i + len(chunk)
        
        # Format chunk thành chuỗi SRT
        chunk_lines = []
        for idx, (s, e, txt) in enumerate(chunk):
            ref = start_ref + idx
            chunk_lines.append(f"{ref}\n{format_srt_time(s)} --> {format_srt_time(e)}\n{txt}\n")
        voice_chunk_text = "\n".join(chunk_lines)
        
        batches.append({
            "batch_idx": len(batches),
            "start_ref": start_ref,
            "end_ref": end_ref,
            "voice_chunk_text": voice_chunk_text,
            "chunk_entries": chunk
        })

    total_batches = len(batches)

    async def async_worker():
        try:
            import httpx
            from openai import AsyncOpenAI
            client_headers = {}
            is_openrouter = 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-')
            if is_openrouter:
                client_headers = {"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
            
            http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
            client = AsyncOpenAI(
                api_key=openai_key, base_url=openai_base_url,
                default_headers=client_headers if client_headers else None,
                http_client=http_client
            )
            is_free = 'free' in str(openai_model).lower() or is_openrouter
            effective_concurrency = 2 if is_free else max_concurrency
            sem = asyncio.Semaphore(effective_concurrency)
            
            q.put({"type": "log", "msg": f"🎬 Bắt đầu phân tích timeline theo {total_batches} mẻ (mỗi mẻ ~{batch_size} câu, timeout 120s)..."})

            async def process_batch(batch):
                b_idx = batch["batch_idx"]
                s_ref = batch["start_ref"]
                e_ref = batch["end_ref"]
                v_text = batch["voice_chunk_text"]
                
                # Check cache for this batch
                cache_key = hashlib.md5((f"step3_{openai_model}_{s_ref}_{e_ref}_" + v_text[:100]).encode('utf-8')).hexdigest()
                cache_file = os.path.join(temp_dir, f"timeline_batch_{b_idx}_{cache_key}.json")
                
                if use_cache and os.path.exists(cache_file):
                    try:
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            cached_data = json.load(f)
                            if isinstance(cached_data, list) and len(cached_data) > 0:
                                q.put({"type": "log", "msg": f"⚡ Mẻ {b_idx+1}/{total_batches} (câu {s_ref}→{e_ref}): Đã tải từ Cache ({len(cached_data)} clips)."})
                                return cached_data
                    except Exception:
                        pass
                        
                orig_context = get_sliding_orig_srt(condensed_orig_srt, b_idx, total_batches)
                prompt_user = prompt_json_template.replace("{DÁN_SRT_PHIM_GỐC_VÀO_ĐÂY}", orig_context).replace("{DÁN_SRT_VOICE_REVIEW_VÀO_ĐÂY}", v_text)
                instruction_addon = f"\n\nLƯU Ý QUAN TRỌNG: Chỉ xử lý và trả về mảng JSON cho các voice_ref từ {s_ref} đến {e_ref} xuất hiện trong SRT_VOICE trên."
                prompt_user += instruction_addon
                
                async with sem:
                    for attempt in range(1, 5):
                        try:
                            q.put({"type": "log", "msg": f"📝 Mẻ {b_idx+1}/{total_batches} (câu {s_ref}→{e_ref}): Đang phân tích (lần {attempt})..."})
                            response = await client.chat.completions.create(
                                model=openai_model,
                                messages=[
                                    {"role": "system", "content": "Bạn là kỹ thuật viên dựng phim. Chỉ trả về duy nhất mảng JSON danh sách các clip cắt [{\"voice_ref\": int, \"start\": float, \"end\": float}], không giải thích gì thêm."},
                                    {"role": "user", "content": prompt_user}
                                ]
                            )
                            raw_content = response.choices[0].message.content or ""
                            
                            # Parse JSON
                            clean_json = raw_content.strip()
                            if "```json" in clean_json:
                                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                            elif "```" in clean_json:
                                clean_json = clean_json.split("```")[1].split("```")[0].strip()
                                
                            try:
                                parsed = json.loads(clean_json)
                            except Exception:
                                clean_json = re.sub(r',\s*([\]}])', r'\1', clean_json)
                                try:
                                    parsed = json.loads(clean_json)
                                except Exception:
                                    json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_content, re.DOTALL)
                                    if json_match:
                                        parsed = json.loads(json_match.group(0))
                                    else:
                                        raise ValueError("Không tìm thấy cấu trúc JSON hợp lệ trong phản hồi AI")
                                
                            if isinstance(parsed, dict):
                                for k in ['clips', 'timeline', 'data', 'result', 'segments', 'cuts']:
                                    if isinstance(parsed.get(k), list) and len(parsed[k]) > 0:
                                        parsed = parsed[k]
                                        break

                            if isinstance(parsed, list) and len(parsed) > 0:
                                # Chuẩn hóa format từng item
                                normalized_batch = []
                                for idx_item, item in enumerate(parsed):
                                    if not isinstance(item, dict):
                                        continue
                                    def_ref = s_ref + idx_item
                                    v_ref = item.get("voice_ref") or item.get("ref") or def_ref
                                    try:
                                        v_ref = int(v_ref)
                                    except Exception:
                                        v_ref = def_ref
                                    s_val = float(item.get("start") or item.get("start_time") or item.get("time_start") or 0.0)
                                    e_val = float(item.get("end") or item.get("end_time") or item.get("time_end") or (s_val + 2.5))
                                    if e_val <= s_val:
                                        e_val = s_val + 2.5
                                    normalized_batch.append({
                                        "voice_ref": v_ref,
                                        "start": round(s_val, 3),
                                        "end": round(e_val, 3)
                                    })
                                
                                if normalized_batch:
                                    with open(cache_file, 'w', encoding='utf-8') as f:
                                        json.dump(normalized_batch, f, indent=2)
                                    q.put({"type": "log", "msg": f"✅ Mẻ {b_idx+1}/{total_batches} (câu {s_ref}→{e_ref}): Hoàn thành {len(normalized_batch)} phân đoạn."})
                                    return normalized_batch

                            raise ValueError(f"Dữ liệu trả về không chứa danh sách clip hợp lệ: {raw_content[:80]}")
                        except Exception as e:
                            if attempt == 4:
                                q.put({"type": "log", "msg": f"⚠️ Mẻ {b_idx+1}/{total_batches} gặp lỗi ({str(e)[:80]}), áp dụng phân bổ dự phòng."})
                            else:
                                wait_s = 5 * attempt
                                q.put({"type": "log", "msg": f"⏳ Mẻ {b_idx+1}: Lỗi ({str(e)[:60]}), đợi {wait_s}s thử lại..."})
                                await asyncio.sleep(wait_s)
                            
                # Fallback nếu batch này không gọi được hoặc API trả về rỗng
                fallback_items = []
                for entry_i, (s_sec, e_sec, _) in enumerate(batch["chunk_entries"]):
                    ref = s_ref + entry_i
                    dur = max(0.5, e_sec - s_sec)
                    fallback_items.append({
                        "voice_ref": ref,
                        "start": round(s_sec, 3),
                        "end": round(s_sec + dur, 3)
                    })
                return fallback_items

            tasks = [process_batch(b) for b in batches]
            results = await asyncio.gather(*tasks)
            
            # Gộp tất cả results
            all_clips = []
            for r in results:
                if isinstance(r, list):
                    all_clips.extend(r)
                    
            # Sắp xếp theo voice_ref
            all_clips.sort(key=lambda x: int(x.get("voice_ref", 0)))
            
            # Chuẩn hóa thứ tự thời gian tuyến tính và chống trùng lặp cảnh ngay từ bước tổng hợp mẻ
            try:
                import timeline_sanitizer
                all_clips, order_logs = timeline_sanitizer.enforce_chronological_and_unique_timeline(all_clips)
                for log_msg in order_logs:
                    q.put({"type": "log", "msg": log_msg})
            except Exception as e:
                q.put({"type": "log", "msg": f"⚠️ Cảnh báo chuẩn hóa thứ tự timeline: {e}"})

            q.put({"type": "done", "result": all_clips})
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_worker())

    t = threading.Thread(target=run_loop)
    t.start()

    final_timeline = []
    while True:
        try:
            item = q.get(timeout=2)
            if item["type"] == "log":
                yield log_func(item["msg"])
            elif item["type"] == "done":
                final_timeline = item["result"]
                yield log_func(f"🎉 Hoàn thành phân tích toàn bộ timeline ({len(final_timeline)} phân đoạn).")
                break
            elif item["type"] == "error":
                yield log_func(f"🛑 Lỗi phân tích timeline: {item['msg']}")
                return []
        except queue.Empty:
            if not t.is_alive():
                yield log_func("🛑 Luồng xử lý timeline kết thúc bất thường mà không có kết quả.")
                return []

    return final_timeline

def run_audio_separator_with_progress(
    video_path,
    output_dir,
    mode="mdx_net_hq4",
    device="auto",
    log_func=None,
    check_stop_func=None
):
    """
    Chạy tách âm thanh AI (Stem Separator / MDX-Net) trong background worker thread và
    stream liên tục số % tiến độ ('Đang tách âm AI (21%): đoạn 10/543 [còn ~1808s]')
    trực tiếp vào System Log qua generator SSE.
    """
    import queue
    import threading
    import audio_separator

    q = queue.Queue()

    def _prog(pct, msg):
        q.put(('progress', pct, msg))

    def _log(msg):
        q.put(('log', msg))

    def _worker():
        try:
            res = audio_separator.separate_audio_stems(
                video_path,
                output_dir=output_dir,
                mode=mode,
                device=device,
                progress_cb=_prog,
                logger_cb=_log,
                cancel_check_cb=check_stop_func
            )
            q.put(('done', res))
        except Exception as e:
            q.put(('error', e))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    last_pct = -1
    last_msg = ""
    last_emit_time = 0
    result = None

    while t.is_alive() or not q.empty():
        try:
            item = q.get(timeout=0.25)
            kind = item[0]
            if kind == 'progress':
                pct, msg = item[1], item[2]
                now = time.time()
                # Báo số % vào System Log: "🎛️ Đang tách âm AI (21%): đoạn 10/543 [còn ~1808s]"
                if msg and (pct != last_pct or msg != last_msg or (now - last_emit_time) >= 2.5):
                    last_pct = pct
                    last_msg = msg
                    last_emit_time = now
                    if log_func:
                        yield log_func(f"🎛️ {msg}")
            elif kind == 'log':
                pass
            elif kind == 'done':
                result = item[1]
                break
            elif kind == 'error':
                raise item[1]
        except queue.Empty:
            if check_stop_func and check_stop_func():
                if log_func:
                    yield log_func("🛑 Đã dừng tách âm thanh theo yêu cầu.")
                return None

    return result

def run_auto_edit_workflow(payload, check_stop_func):
    start_time_auto_edit = time.time()
    video_path = payload.get('video_path')
    srt_path = payload.get('srt_path')
    voice_id = payload.get('voice_id', 'ngoc_huyen')
    output_dir = payload.get('output_dir', 'output')
    output_name = payload.get('output_name', 'video_review.mp4')
    
    openai_key, openai_base_url, openai_model = resolve_openai_credentials(payload)
    api_key_openspeaker = payload.get('openspeaker_api_key', '')
    auto_subtitles = payload.get('auto_subtitles', False)
    
    # Advanced Anti-Flicker & Sync Parameters
    enable_scene_detect = payload.get('enable_scene_detect', True)
    snap_threshold = float(payload.get('snap_threshold', 0.6))
    min_clip_duration = float(payload.get('min_clip_duration', 1.2))
    max_speed_ratio_dev = float(payload.get('max_speed_ratio_deviation', 0.15))
    enable_crossfade = payload.get('enable_crossfade', False)
    crossfade_duration = float(payload.get('crossfade_duration', 0.15))
    encoder = payload.get('encoder', 'libx264')

    if not api_key_openspeaker:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_p = [os.path.join(root_dir, 'api_keys.txt'), 'api_keys.txt']
        try:
            import license_manager
            candidate_p.append(os.path.join(license_manager.get_user_data_dir(), 'api_keys.txt'))
        except Exception:
            pass
        for p in candidate_p:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key_openspeaker = line.split('=', 1)[1].strip()
                            break
                if api_key_openspeaker:
                    break

    continue_from_script = parse_bool(payload.get('continue_from_script'), False)
    pause_after_script = parse_bool(payload.get('pause_after_script', True), True)
    custom_script = payload.get('custom_script')
    custom_srt_content = payload.get('custom_srt_content') or payload.get('narration_srt_content')
    use_cache = bool(payload.get('use_cache', False))

    if not continue_from_script and not custom_script:
        if not openai_key:
            yield "data: 🛑 Lỗi: Chưa tìm thấy OpenAI API Key. Vui lòng vào Cài đặt để nhập Key cá nhân hoặc bấm [Lấy API Cấp Sẵn] nếu bạn dùng gói VIP/1 Năm!\n\n"
            return
        if not srt_path or not os.path.exists(srt_path):
            yield "data: 🛑 Lỗi: Không tìm thấy file SRT đầu vào. Phải có SRT gốc để GPT làm việc!\n\n"
            return

    if not video_path or not os.path.exists(video_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file Video đầu vào.\n\n"
        return

    os.makedirs(output_dir, exist_ok=True)
    custom_temp = payload.get('temp_dir')
    if custom_temp:
        try:
            norm_custom = os.path.realpath(custom_temp)
            norm_out = os.path.realpath(output_dir)
            if norm_custom.startswith(norm_out):
                temp_dir = custom_temp
            else:
                temp_dir = get_review_temp_dir(output_dir, video_path)
        except Exception:
            temp_dir = get_review_temp_dir(output_dir, video_path)
    else:
        temp_dir = get_review_temp_dir(output_dir, video_path)
    os.makedirs(temp_dir, exist_ok=True)

    # Đọc nội dung SRT đầu vào nếu có, hoặc tạo SRT fallback từ kịch bản thuyết minh
    srt_content = ""
    if srt_path and os.path.exists(srt_path):
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
    elif continue_from_script or custom_script or custom_srt_content:
        srt_path = os.path.join(temp_dir, 'uploaded_narration.srt')
        if custom_srt_content and str(custom_srt_content).strip():
            srt_content = str(custom_srt_content).strip()
            with open(srt_path, 'w', encoding='utf-8') as sf:
                sf.write(srt_content)
        else:
            script_lines = [s.strip() for s in split_text_to_sentences(str(custom_script or '')) if s.strip()]
            if not script_lines:
                script_lines = ["Kịch bản thuyết minh review phim"]
            srt_blocks = []
            for s_idx, s_txt in enumerate(script_lines, 1):
                t_s = (s_idx - 1) * 4.0
                t_e = s_idx * 4.0
                srt_blocks.append(f"{s_idx}\n{seconds_to_srt_time(t_s)} --> {seconds_to_srt_time(t_e)}\n{s_txt}\n")
            srt_content = "\n".join(srt_blocks)
            with open(srt_path, 'w', encoding='utf-8') as sf:
                sf.write(srt_content)

    # Luôn đảm bảo ffmpeg_path và cấu hình OpenAI sẵn sàng cho toàn bộ workflow
    ffmpeg_path = None
    try:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    except Exception as e:
        yield f"data: 🛑 Lỗi kiểm tra FFmpeg: {e}\n\n"
        return

    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    if 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-'):
        headers["HTTP-Referer"] = "https://novacut.app"
        headers["X-Title"] = "NovaCut AI"
    url = f"{openai_base_url.rstrip('/')}/chat/completions"

    def log(msg, step=None):
        if step:
            return f"data: [STEP] {step}\n\ndata: {msg}\n\n"
        return f"data: {msg}\n\n"

    if not use_cache and not continue_from_script and os.path.exists(temp_dir):

        yield log("🧹 Đang dọn dẹp tài liệu cũ để tạo mới hoàn toàn...")
        undeleted = []
        try:
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                except Exception:
                    undeleted.append(item)
            if undeleted:
                yield log(f"⚠️ Một số file tạm đang bị khóa ({', '.join(undeleted[:3])}), hệ thống sẽ ghi đè trực tiếp.")
            else:
                yield log("✨ Đã dọn sạch tài liệu cũ thành công.")
        except Exception as e:
            yield log(f"⚠️ Cảnh báo dọn dẹp tài liệu cũ: {e}")
    os.makedirs(temp_dir, exist_ok=True)

    script_txt_path = os.path.join(temp_dir, 'script.txt')
    voice_audio_path = os.path.join(temp_dir, "voice_review.wav")
    voice_srt_path = os.path.join(temp_dir, "voice_review.srt")
    voice_srt_cleaned_path = os.path.join(temp_dir, "voice_review_cleaned.srt")
    json_path = os.path.join(temp_dir, 'timeline.json')
    sanitized_json_path = os.path.join(temp_dir, 'timeline_sanitized.json')

    try:
        # --- BƯỚC 1: LÊN KỊCH BẢN ---
        yield log("Đang đọc SRT và lên kịch bản review (Bước 1)...", step=1)
        yield log("[PROGRESS] 5")
        if check_stop_func(): return
        
        review_script = ""
        script_meta_path = os.path.join(temp_dir, 'script_meta.json')
        review_style = payload.get('review_style', 'dramatic')
        custom_style_prompt = payload.get('custom_style_prompt', '')
        script_language = payload.get('script_language') or payload.get('target_lang') or 'vi'
        target_minutes = payload.get('target_minutes', 5)
        current_script_fingerprint = hashlib.md5((srt_content + str(target_minutes) + str(review_style) + str(custom_style_prompt) + str(script_language) + str(openai_model)).encode('utf-8')).hexdigest()

        if custom_script and str(custom_script).strip():
            review_script = sanitize_review_script(str(custom_script).strip())
            with open(script_txt_path, 'w', encoding='utf-8') as f:
                f.write(review_script)
            with open(script_meta_path, 'w', encoding='utf-8') as mf:
                json.dump({'fingerprint': current_script_fingerprint, 'custom': True}, mf)
            yield log(f"💚 Sử dụng kịch bản đã chỉnh sửa của người dùng ({len(review_script.split())} từ).")
            yield log("[PROGRESS] 20")
        else:
            cache_valid = False
            if use_cache and os.path.exists(script_txt_path) and os.path.exists(script_meta_path):
                try:
                    with open(script_meta_path, 'r', encoding='utf-8') as mf:
                        meta_data = json.load(mf)
                        if meta_data.get('fingerprint') == current_script_fingerprint:
                            cache_valid = True
                except Exception:
                    cache_valid = False

            if cache_valid:
                with open(script_txt_path, 'r', encoding='utf-8') as f:
                    review_script = sanitize_review_script(f.read())
                yield log(f"💚 Đã tìm thấy kịch bản cũ, tái sử dụng tại {script_txt_path}")
                yield log("[PROGRESS] 20")
            else:
                import prompt_vault
                import review_styles
                prompt_map = prompt_vault.get_prompt('prompt_map_chunk')
                prompt_reduce = prompt_vault.get_prompt('prompt_reduce_script')
                if not prompt_map or not prompt_reduce:
                    yield log("🛑 Không tìm thấy nội dung kịch bản mẫu prompt_map_chunk hoặc prompt_reduce_script!")
                    return
                    
                style_info = review_styles.get_style_by_id(review_style)
                style_directive = review_styles.get_style_directive(review_style, custom_style_prompt)
                yield log(f"🎭 Phong cách Review: {style_info.get('icon', '🎬')} {style_info.get('name', 'Mặc định')}")

                lang_code = str(script_language).lower().strip()
                lang_info = LANGUAGE_NAMES.get(lang_code, ('Tiếng Việt', 'Vietnamese'))
                lang_directive = get_language_directive(lang_code)
                yield log(f"🌐 Ngôn ngữ kịch bản đầu ra: {lang_info[0]} ({lang_info[1]})")

                if lang_directive:
                    prompt_map = f"{lang_directive}\n\n{prompt_map}"
                    prompt_reduce = f"{lang_directive}\n\n{prompt_reduce}"

                target_words = int(target_minutes * 210)  # 3.5 từ/giây = 210 từ/phút
                condensed_srt = condense_srt_for_llm(srt_content, max_chars=40000)
                
                yield log("Đang phân chia file phụ đề thành các chunk...")
                srt_chunks = split_srt_by_tokens(condensed_srt, max_tokens=6000, model_name=openai_model)
                if not srt_chunks:
                    yield log("🛑 File phụ đề rỗng sau khi xử lý!")
                    return
                    
                review_script = yield from run_map_reduce_pipeline_sync(
                    openai_key, openai_base_url, openai_model, srt_chunks, 
                    target_words, prompt_map, prompt_reduce, temp_dir, log,
                    style_directive=style_directive,
                    use_cache=use_cache
                )
                
                if not review_script:
                    return
                    
                review_script = sanitize_review_script(review_script)
                with open(script_txt_path, 'w', encoding='utf-8') as f:
                    f.write(review_script)
                with open(script_meta_path, 'w', encoding='utf-8') as mf:
                    json.dump({'fingerprint': current_script_fingerprint}, mf)
                yield log(f"✅ Đã viết kịch bản xong, lưu tại {script_txt_path}")
                yield log("[PROGRESS] 20")

        # Tách câu và gửi sự kiện [SCRIPT_READY] cho Frontend
        sentences = split_text_to_sentences(review_script)
        script_info = {
            "script": review_script,
            "sentences": sentences,
            "word_count": len(review_script.split()),
            "sentence_count": len(sentences),
            "est_minutes": round(len(review_script.split()) / 210.0, 1)
        }
        yield f"data: [SCRIPT_READY] {json.dumps(script_info, ensure_ascii=False)}\n\n"

        if pause_after_script and not continue_from_script:
            yield log(f"⏸️ [TẠM DỪNG DUYỆT KỊCH BẢN] Đã tạo xong kịch bản ({len(sentences)} câu, {len(review_script.split())} từ).")
            yield log("📝 Hệ thống đã nạp kịch bản vào bảng bên dưới để bạn xem và chỉnh sửa.")
            yield log("👉 Hãy kiểm tra các câu thoại, nghe thử giọng đọc nếu muốn, sau đó bấm [TIẾP TỤC DỰNG VIDEO] để hoàn tất!")
            return
        
        # --- BƯỚC 2: TẠO GIỌNG ĐỌC (TỪNG CÂU - CHÍNH XÁC TIMESTAMP) ---
        yield log("Đang tạo giọng đọc (Bước 2 - Tách câu TTS)...", step=2)
        if check_stop_func(): return
        
        voice_speed = float(payload.get('voice_speed', 1.0))
        tts_threads = int(payload.get('tts_threads', 8))
        
        if use_cache and not continue_from_script and os.path.exists(voice_audio_path) and os.path.exists(voice_srt_path) and os.path.getsize(voice_audio_path) > 1000:
            yield log("💚 Đã tìm thấy file giọng đọc cũ, tái sử dụng.")
            yield log("[PROGRESS] 40")
        else:
            if is_api_voice(voice_id) and api_key_openspeaker:
                yield log("☁️ Đang gọi OpenSpeaker API tạo giọng đọc và phụ đề 1 lần (with_transcript)...")
                try:
                    temp_aud_raw = os.path.join(temp_dir, 'voice_raw.mp3')
                    ai_dubbing.synthesize_openspeaker_with_transcript(
                        review_script, voice_id, voice_speed, temp_aud_raw, voice_srt_path, api_key_openspeaker
                    )
                    
                    # Convert raw audio sang PCM WAV 24kHz để khớp pipeline
                    cmd_conv = [
                        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', temp_aud_raw, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
                        voice_audio_path
                    ]
                    subprocess.run(cmd_conv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **get_stealth_subprocess_kwargs())
                    
                    yield log("✅ Đã nhận xong giọng đọc và phụ đề trực tiếp từ API!")
                    yield log("[PROGRESS] 40")
                except Exception as e:
                    yield log(f"⚠️ Lỗi gọi API tạo voice 1 lần ({str(e)}), chuyển sang luồng dự phòng (Tách câu)...")
            
            if not os.path.exists(voice_audio_path) or not os.path.exists(voice_srt_path):
                # Tách kịch bản thành câu riêng biệt (Luồng Local hoặc Fallback)
                sentences = split_text_to_sentences(review_script)
                yield log(f"Đã tách kịch bản thành {len(sentences)} câu.")
                
                if not sentences:
                    yield log("🛑 Lỗi: Kịch bản rỗng sau khi tách câu.")
                    return
                
                # TTS từng câu đa luồng, concat, tạo SRT chính xác với cập nhật tiến trình %
                yield log(f"Đang tạo giọng đọc cho {len(sentences)} câu (Đa luồng: {tts_threads} workers)...")
                final_audio = None
                final_srt = None
                srt_entries = []
                error = None
                
                for msg_type, data in generate_tts_per_sentence_stream(
                    sentences, voice_id, voice_speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct=20, end_pct=40, threads=tts_threads, use_cache=use_cache
                ):
                    if msg_type == 'progress':
                        curr_i, total_i, step_pct, overall_pct, snippet = data
                        yield log(f"🎙️ [{curr_i}/{total_i} - {step_pct}%] Đang tạo giọng đọc: \"{snippet}\"")
                        yield log(f"[PROGRESS] {overall_pct}")
                    elif msg_type == 'error':
                        error = data
                    elif msg_type == 'done':
                        final_audio, final_srt, srt_entries = data
                
                if error:
                    if error == "STOPPED":
                        return
                    yield log(f"🛑 {error}")
                    return
                if final_audio and final_audio != voice_audio_path and os.path.exists(final_audio):
                    shutil.copy2(final_audio, voice_audio_path)
                if final_srt and final_srt != voice_srt_path and os.path.exists(final_srt):
                    shutil.copy2(final_srt, voice_srt_path)
                
                yield log(f"✅ Đã tạo xong giọng đọc ({len(srt_entries)} block SRT chính xác).")
                yield log("[PROGRESS] 40")
            
        # --- BƯỚC 2.5: CHUẨN HÓA SRT (TỐI ĐA 2 DÒNG / BLOCK) ---
        yield log("Đang chuẩn hóa SRT giọng đọc (tối đa 2 dòng/block)...")
        if check_stop_func(): return
        
        if use_cache and os.path.exists(voice_srt_cleaned_path) and os.path.getsize(voice_srt_cleaned_path) > 10:
            yield log("💚 Đã tìm thấy file SRT giọng đọc đã chuẩn hóa, tái sử dụng.")
        else:
            # Đọc SRT vừa tạo và enforce max 2 dòng
            raw_entries = parse_srt_entries(voice_srt_path)
            cleaned_entries = enforce_max_2_lines_srt(raw_entries, max_chars_per_line=38)
            
            with open(voice_srt_cleaned_path, 'w', encoding='utf-8') as f:
                for idx, (s, e, txt) in enumerate(cleaned_entries):
                    f.write(f"{idx+1}\n")
                    f.write(f"{format_srt_time(s)} --> {format_srt_time(e)}\n")
                    f.write(f"{txt}\n\n")
            
            yield log(f"✅ Đã chuẩn hóa SRT: {len(raw_entries)} → {len(cleaned_entries)} block (tối đa 2 dòng/block).")
        yield log("[PROGRESS] 42")
        
        # --- BƯỚC 3: PHÂN TÍCH CẢNH (ĐẠO DIỄN / JSON) ---
        yield log("Đang phân tích cảnh bằng GPT (Bước 3)...", step=3)
        yield log("[PROGRESS] 43")
        if check_stop_func(): return
        
        timeline_data = []
        if use_cache and os.path.exists(json_path) and os.path.getsize(json_path) > 10:
            with open(json_path, 'r', encoding='utf-8') as f:
                try:
                    loaded = json.load(f)
                    if isinstance(loaded, list) and len(loaded) > 0:
                        timeline_data = loaded
                        yield log(f"💚 Đã tìm thấy file timeline cũ ({len(timeline_data)} phân đoạn), tái sử dụng.")
                        yield log("[PROGRESS] 50")
                except Exception:
                    timeline_data = []
        
        if not timeline_data:
            import prompt_vault
            prompt_json_template = prompt_vault.get_prompt('prompt_json')
            if not prompt_json_template:
                yield log("🛑 Không tìm thấy nội dung mẫu prompt_json!")
                return
            
            # Đọc danh sách block giọng đọc từ file SRT đã chuẩn hóa
            voice_entries = parse_srt_entries(voice_srt_cleaned_path)
            if not voice_entries:
                voice_entries = parse_srt_entries(voice_srt_path)
                
            if not voice_entries:
                yield log("🛑 Không tìm thấy block giọng đọc nào để phân tích timeline!")
                return
                
            condensed_orig_srt = condense_srt_for_llm(srt_content, max_chars=40000)
            
            timeline_data = yield from run_timeline_map_reduce_pipeline_sync(
                openai_key=openai_key,
                openai_base_url=openai_base_url,
                openai_model=openai_model,
                voice_entries=voice_entries,
                condensed_orig_srt=condensed_orig_srt,
                prompt_json_template=prompt_json_template,
                temp_dir=temp_dir,
                log_func=log,
                batch_size=35,
                max_concurrency=4,
                use_cache=use_cache
            )
            
            if not timeline_data or len(timeline_data) == 0:
                yield log("🛑 Lỗi: Không tạo được timeline phân đoạn!")
                return
                
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(timeline_data, f, indent=4)
                
            yield log(f"✅ Đã phân tích xong {len(timeline_data)} phân đoạn.")
            yield log("[PROGRESS] 50")
        
        # --- BƯỚC 3.5: SCENE DETECTION & TIMELINE SANITIZER (CHỐNG NHÁY HÌNH) ---
        scene_cuts = []
        if enable_scene_detect:
            yield log("Đang quét điểm chuyển cảnh phim gốc (Boundary-Targeted Scene Detection)...")
            if check_stop_func(): return
            
            for msg, cuts in timeline_sanitizer.extract_scene_cuts_with_progress(
                video_path, threshold=27.0, cache_dir=temp_dir, check_stop_func=check_stop_func, target_timeline=timeline_data
            ):
                if check_stop_func(): return
                if msg:
                    yield log(msg)
                    if "Đang quét chuyển cảnh" in msg and "%" in msg:
                        try:
                            detect_pct = int(msg.split("%")[0].split(":")[-1].strip())
                            overall_pct = int(50 + (8 * detect_pct / 100))
                            yield log(f"[PROGRESS] {overall_pct}")
                        except Exception:
                            pass
                if cuts is not None:
                    scene_cuts = cuts
        else:
            yield log("Bỏ qua quét chuyển cảnh (Scene Sanitizer tắt).")
        
        yield log("Đang tối ưu điểm cắt (Deterministic Resolver & Voice Master Clock)...")
        voice_entries = parse_srt_entries(voice_srt_cleaned_path)
        if not voice_entries:
            voice_entries = parse_srt_entries(voice_srt_path)

        sanitized_timeline, sanitize_logs = timeline_sanitizer.resolve_timeline_with_voice_clock(
            timeline=timeline_data,
            voice_entries=voice_entries,
            scene_cuts=scene_cuts,
            snap_threshold=snap_threshold,
            min_clip_duration=min_clip_duration,
            min_speed=max(0.70, 1.0 - max_speed_ratio_dev),
            max_speed=min(1.30, 1.0 + max_speed_ratio_dev)
        )
        
        for msg in sanitize_logs:
            yield log(msg)

        # PRE-RENDER VALIDATOR
        is_valid_tl, tl_report = timeline_sanitizer.validate_timeline(sanitized_timeline)
        yield log(f"📊 [PRE-RENDER VALIDATOR] Tổng {tl_report['total_clips']} clips | Voice: {tl_report['total_voice_duration']:.2f}s | Video: {tl_report['total_video_duration']:.2f}s | Độ lệch P95: {tl_report['p95_sync_error_ms']:.1f}ms (Max: {tl_report['max_sync_error_ms']:.1f}ms).")
        if tl_report.get('warnings'):
            for w in tl_report['warnings']:
                yield log(f"⚠️ [VALIDATOR] {w}")
        if not is_valid_tl:
            yield log(f"🛑 [VALIDATOR] Timeline không hợp lệ: {'; '.join(tl_report['errors'])}")
            return
            
        with open(sanitized_json_path, 'w', encoding='utf-8') as f:
            json.dump(sanitized_timeline, f, indent=4)
            
        yield log(f"✅ Đã lưu timeline tối ưu tại {sanitized_json_path}")
        yield log("[PROGRESS] 60")
        
        # --- BƯỚC 4: CẮT GHÉP & ĐỒNG BỘ ÂM THANH THEO TỪNG CLIP (PARALLEL FFMPEG) ---
        detected_enc, is_gpu_enc, _ = detect_hardware_encoder(ffmpeg_path)
        encoder = payload.get('encoder') or detected_enc
        cpu_cores = os.cpu_count() or 4

        # Tối ưu worker song song: GPU NVENC giới hạn session -> chạy 2 workers; CPU -> tối đa 4 workers
        if is_gpu_enc:
            num_workers = min(2, max(1, cpu_cores // 4))
            yield log(f"⚡ Đã kích hoạt tăng tốc phần cứng GPU ({detected_enc}) với {num_workers} worker song song (chống nghẽn queue GPU)!")
        else:
            num_workers = min(4, max(2, cpu_cores // 2))
            yield log(f"⚙️ Sử dụng động cơ CPU Multithread tối ưu ({encoder} veryfast, {num_workers} workers song song).")

        total_clips = len(sanitized_timeline)
        if total_clips == 0:
            yield log("🛑 Lỗi: Timeline sau khi tối ưu rỗng!")
            return

        yield log(f"🎬 Đang tiến hành cắt song song {total_clips} clip câm ({num_workers} workers song song)...", step=4)
        if check_stop_func(): return

        blur_orig_subs = parse_bool(payload.get('blur_original_subtitles'), False)
        blur_sz = max(3, min(40, int(payload.get('blur_intensity', 15))))
        blur_y = float(payload.get('blur_y_pos', 81.5)) / 100.0
        blur_lead_offset = abs(float(payload.get('blur_lead_offset', -180)) / 1000.0)
        blur_padding = float(payload.get('blur_padding', 220)) / 1000.0
        blur_ai_boxes = payload.get('ai_boxes') or []

        # Video Zoom parameter
        raw_zoom = float(payload.get('video_zoom', 100.0))
        zoom_val = (raw_zoom / 100.0) if raw_zoom > 5.0 else raw_zoom
        enable_zoom = bool(payload.get('enable_zoom', False) or payload.get('pan_zoom', False) or zoom_val > 1.005)
        zoom_factor = max(1.0, min(5.0, zoom_val)) if enable_zoom else 1.0
        if zoom_factor > 1.005:
            yield log(f"🔍 Kích hoạt phóng to video (Zoom: {zoom_factor*100:.0f}%)...")

        video_pan_x = float(payload.get('video_pan_x', 0.0))
        video_pan_y = float(payload.get('video_pan_y', 0.0))

        orig_sub_entries = parse_srt_entries(srt_path) if blur_orig_subs else []
        if blur_orig_subs and orig_sub_entries and blur_ai_boxes and isinstance(blur_ai_boxes, list):
            enriched = []
            for idx, entry in enumerate(orig_sub_entries):
                s, e = entry[0], entry[1]
                txt = entry[2] if len(entry) >= 3 else ''
                ai_b = blur_ai_boxes[idx] if idx < len(blur_ai_boxes) else None
                if ai_b and isinstance(ai_b, dict) and 'x_pct' in ai_b and 'w_pct' in ai_b:
                    bx = float(ai_b['x_pct']) / 100.0
                    bw = float(ai_b['w_pct']) / 100.0
                    vs = ai_b.get('visual_start')
                    ve = ai_b.get('visual_end')
                    if vs is not None and ve is not None:
                        enriched.append((s, e, txt, bx, bw, float(vs), float(ve)))
                    else:
                        enriched.append((s, e, txt, bx, bw))
                else:
                    enriched.append(entry)
            orig_sub_entries = enriched

        if blur_orig_subs and orig_sub_entries:
            yield log(f"✨ Kích hoạt làm mờ phụ đề gốc theo thời gian ({len(orig_sub_entries)} đoạn phát hiện, độ mờ: {blur_sz}px).")

        def render_single_clip(i, clip):
            if check_stop_func and check_stop_func():
                return i, None, "STOPPED"

            v_src_start = float(clip.get('source_start', clip.get('start', 0.0)))
            v_src_end = float(clip.get('source_end', clip.get('end', v_src_start + 2.0)))
            v_src_dur = max(0.1, round(v_src_end - v_src_start, 3))
            target_dur = float(clip.get('video_duration', clip.get('duration', v_src_dur)))
            video_speed = float(clip.get('video_speed', clip.get('speed_ratio', 1.0)))
            if video_speed <= 0.01:
                video_speed = 1.0

            if target_dur <= 0:
                return i, None, None

            # Phát hiện phụ đề gốc trong khoảng thời gian clip này
            active_orig_intervals = []
            if blur_orig_subs and orig_sub_entries:
                v_end_calc = v_src_start + v_src_dur
                for item in orig_sub_entries:
                    s, e = item[0], item[1]
                    if e > v_src_start and s < v_end_calc:
                        rel_s = max(0.0, s - v_src_start)
                        rel_e = min(v_src_dur, e - v_src_start)
                        if rel_e > rel_s:
                            if len(item) == 7:
                                active_orig_intervals.append((rel_s, rel_e, item[2], item[3], item[4], item[5], item[6]))
                            elif len(item) >= 5:
                                active_orig_intervals.append((rel_s, rel_e, item[2], item[3], item[4]))
                            else:
                                active_orig_intervals.append((rel_s, rel_e, item[2] if len(item) >= 3 else ''))

            # Xây dựng filter_complex cho VIDEO CÂM
            clip_silent_path = os.path.join(temp_dir, f"clip_silent_{i:04d}.mp4")
            filter_chain = []
            curr_v = "0:v"

            # 1. Phóng to Video (Zoom & Center Crop & Upscale)
            if zoom_factor > 1.005:
                clip_vw, clip_vh = get_video_dimensions_fast(video_path, ffmpeg_path)
                crop_w = f"trunc(iw/{zoom_factor:.4f}/2)*2"
                crop_h = f"trunc(ih/{zoom_factor:.4f}/2)*2"
                crop_x = f"(iw-{crop_w})/2 - ({video_pan_x:.1f}*(iw/800))"
                crop_y = f"(ih-{crop_h})/2 - ({video_pan_y:.1f}*(ih/450))"
                filter_chain.append(f"[{curr_v}]crop=w={crop_w}:h={crop_h}:x='max(0,min(iw-ow,trunc(({crop_x})/2)*2))':y='max(0,min(ih-oh,trunc(({crop_y})/2)*2))',scale={clip_vw}:{clip_vh}:flags=lanczos[v_zoomed]")
                curr_v = "v_zoomed"

            # 2. Làm mờ động phụ đề gốc
            if blur_orig_subs and active_orig_intervals:
                dyn_filters, curr_v = build_dynamic_blur_filter_chain(
                    curr_v, active_orig_intervals,
                    blur_sz=blur_sz,
                    y_ratio=blur_y,
                    h_ratio=0.095,
                    center_x_ratio=0.50,
                    lead_sec=blur_lead_offset,
                    pad_sec=blur_padding
                )
                filter_chain.extend(dyn_filters)

            # 3. ÁP DỤNG VIDEO SPEED THỰC TẾ BẰNG SETPTS (P0 FIX)
            if abs(video_speed - 1.0) > 0.005:
                filter_chain.append(f"[{curr_v}]setpts=PTS/{video_speed:.6f}[v_speed]")
                curr_v = "v_speed"

            # 4. CHUẨN HÓA TOÀN BỘ STREAM (P1 FIX: FPS=30, AVTB, STARTPTS=0, YUV420P)
            filter_chain.append(f"[{curr_v}]fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v]")
            vf_filter = ";".join(filter_chain)

            common_enc_args = ['-r', '30', '-video_track_timescale', '90000', '-g', '60', '-keyint_min', '60']
            if encoder == 'h264_nvenc':
                enc_cmd = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '22', '-pix_fmt', 'yuv420p', *common_enc_args]
            elif encoder == 'hevc_nvenc':
                enc_cmd = ['-c:v', 'hevc_nvenc', '-preset', 'p4', '-cq', '24', '-pix_fmt', 'yuv420p', *common_enc_args]
            elif encoder == 'h264_qsv':
                enc_cmd = ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-global_quality', '22', '-pix_fmt', 'yuv420p', *common_enc_args]
            elif encoder == 'h264_amf':
                enc_cmd = ['-c:v', 'h264_amf', '-quality', 'speed', '-qp_i', '22', '-qp_p', '22', '-pix_fmt', 'yuv420p', *common_enc_args]
            elif encoder == 'h264_mf':
                enc_cmd = ['-c:v', 'h264_mf', '-rate_control', 'vbr', '-b:v', '6000k', '-pix_fmt', 'yuv420p', *common_enc_args]
            else:
                enc_cmd = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', *common_enc_args, '-threads', '2']

            # Accurate Seek (Hybrid Seek: fast seek trước -i và fine seek sau -i để chính xác từng frame)
            if v_src_start > 2.0:
                fast_s = max(0.0, v_src_start - 1.5)
                fine_s = round(v_src_start - fast_s, 3)
                seek_args = ['-ss', f"{fast_s:.3f}", '-i', video_path, '-ss', f"{fine_s:.3f}", '-t', f"{v_src_dur:.3f}"]
            else:
                seek_args = ['-ss', f"{v_src_start:.3f}", '-i', video_path, '-t', f"{v_src_dur:.3f}"]

            cmd_mux = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                *seek_args,
                '-filter_complex', vf_filter,
                '-map', '[v]',
                *enc_cmd,
                '-t', f"{target_dur:.3f}",
                '-an',
                clip_silent_path
            ]

            proc_m = subprocess.run(cmd_mux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
            if proc_m.returncode != 0:
                # Nếu GPU bị lỗi, thử lại 1 lần với CPU libx264
                if encoder != 'libx264':
                    cmd_mux_fallback = [
                        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                        *seek_args,
                        '-filter_complex', vf_filter,
                        '-map', '[v]',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p', *common_enc_args,
                        '-t', f"{target_dur:.3f}",
                        '-an',
                        clip_silent_path
                    ]
                    proc_fb = subprocess.run(cmd_mux_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
                    if proc_fb.returncode == 0:
                        return i, clip_silent_path, None
                return i, None, f"Lỗi FFmpeg clip #{i+1}: {proc_m.stderr}"

            return i, clip_silent_path, None

        results_map = {}
        completed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_idx = {
                executor.submit(render_single_clip, idx, clip): idx
                for idx, clip in enumerate(sanitized_timeline)
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                if check_stop_func and check_stop_func():
                    executor.shutdown(wait=False, cancel_futures=True)
                    yield log("🛑 Đã dừng tiến trình theo yêu cầu.")
                    return

                idx, clip_path, err = future.result()
                if err:
                    if err == "STOPPED":
                        return
                    executor.shutdown(wait=False, cancel_futures=True)
                    yield log(f"🛑 {err}")
                    return

                if clip_path and os.path.exists(clip_path):
                    results_map[idx] = clip_path

                completed_count += 1
                step_pct = int(completed_count / total_clips * 100)
                overall_pct = int(60 + (30 * completed_count / total_clips))
                if completed_count % max(1, total_clips // 12) == 0 or completed_count == total_clips:
                    yield log(f"🎬 [{completed_count}/{total_clips} - {step_pct}%] Đang cắt clip câm song song ({num_workers} workers)...")
                    yield log(f"[PROGRESS] {overall_pct}")

        silent_clip_files = [results_map[idx] for idx in sorted(results_map.keys()) if results_map.get(idx)]

        if not silent_clip_files:
            yield log("🛑 Lỗi: Không dựng được clip nào từ danh sách timeline.")
            return

        yield log("[PROGRESS] 90")

        # --- BƯỚC 5: NỐI TẤT CẢ CÁC CLIP CÂM LẠI ---
        yield log("Đang ghép nối toàn bộ video câm (Bước 5)...")
        yield log("[PROGRESS] 92")
        if check_stop_func(): return
        
        concat_txt = os.path.join(temp_dir, 'concat_silent.txt')
        with open(concat_txt, 'w', encoding='utf-8') as f:
            for c in silent_clip_files:
                fname = os.path.basename(c).replace("'", "'\\''")
                f.write(f"file '{fname}'\n")
                
        concat_silent_path = os.path.join(temp_dir, 'concat_silent.mp4')
        
        cmd_concat = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'concat', '-safe', '0',
            '-i', concat_txt,
            '-c', 'copy',
            concat_silent_path
        ]
        proc_c = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
        if proc_c.returncode != 0:
            yield log(f"🛑 Lỗi ghép nối video: {proc_c.stderr}")
            return
            
        # --- BƯỚC 6: CHÈN AUDIO TỔNG VÀ PHỤ ĐỀ VÀO VIDEO GHÉP ---
        yield log("Đang chèn voice tổng và phụ đề vào video ghép (Bước 6)...")
        yield log("[PROGRESS] 95")
        if check_stop_func(): return

        # AI Stem Separation (Lọc bỏ lời thoại cũ, giữ lại hiệu ứng SFX nếu bật)
        stem_sep_data = payload.get('stem_separation', {})
        stem_enabled = bool(stem_sep_data.get('enabled', False) or payload.get('remove_original_vocals', False))
        cleaned_sfx_path = None
        orig_vol = float(payload.get('original_volume', 15 if stem_enabled else 0)) / 100.0

        if stem_enabled:
            has_orig_audio = True
            try:
                p_cmd = [ffmpeg_path, '-i', video_path]
                p_proc = subprocess.run(p_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', **get_stealth_subprocess_kwargs())
                has_orig_audio = 'Audio:' in p_proc.stderr
            except Exception:
                pass

            if has_orig_audio:
                yield log("🎛️ Bắt đầu tách âm thanh AI (MDX-Net) để lọc sạch lời thoại cũ & bảo lưu tiếng động SFX...")
                try:
                    stem_mode = stem_sep_data.get('mode', 'mdx_net_hq4')
                    stem_device = stem_sep_data.get('device', 'auto')
                    sep_res = yield from run_audio_separator_with_progress(
                        video_path=video_path,
                        output_dir=temp_dir,
                        mode=stem_mode,
                        device=stem_device,
                        log_func=log,
                        check_stop_func=check_stop_func
                    )
                    if sep_res and sep_res.get('cleaned_path') and os.path.exists(sep_res.get('cleaned_path')):
                        cleaned_sfx_path = sep_res.get('cleaned_path')
                        yield log("✅ Đã tách và bảo lưu âm thanh nền SFX thành công!")
                except Exception as e:
                    yield log(f"⚠️ Lỗi tách âm thanh: {e} (Tiếp tục xử lý)")

        if not output_name.lower().endswith('.mp4'):
            output_name += '.mp4'
        final_output = os.path.join(output_dir, output_name)

        # Logo Watermark
        logo_data = payload.get('logo') or {}
        logo_enabled = bool(logo_data.get('enabled', False))
        logo_path = logo_data.get('path', '').strip()

        # BGM Configuration
        bgm_data = payload.get('bgm') or {}
        bgm_enabled = bool(bgm_data.get('enabled', False))
        bgm_vol = max(0.0, min(1.0, float(bgm_data.get('volume', 15)) / 100.0))
        bgm_ducking = bool(bgm_data.get('ducking', False))
        bgm_path = bgm_data.get('path', '').strip()

        bgm_file = None
        if bgm_enabled:
            if bgm_path and os.path.exists(bgm_path):
                bgm_file = bgm_path
            else:
                bgm_preset = bgm_data.get('preset', '')
                preset_dir = os.path.join(ROOT_DIR, 'backgroundmusic')
                if bgm_preset and os.path.exists(os.path.join(preset_dir, bgm_preset)):
                    bgm_file = os.path.join(preset_dir, bgm_preset)
                elif os.path.exists(preset_dir):
                    preset_files = [os.path.join(preset_dir, f) for f in os.listdir(preset_dir) if f.lower().endswith(('.mp3', '.m4a', '.wav', '.aac'))]
                    if preset_files:
                        bgm_file = random.choice(preset_files)

        overlay_inputs = ['-i', concat_silent_path, '-i', voice_audio_path]
        sfx_input_idx = None
        if cleaned_sfx_path and os.path.exists(cleaned_sfx_path) and orig_vol > 0.01:
            yield log(f"🔊 Đang mix âm thanh hiệu ứng SFX gốc (Âm lượng: {int(orig_vol*100)}%)...")
            sfx_input_idx = overlay_inputs.count('-i')
            overlay_inputs.extend(['-stream_loop', '-1', '-i', cleaned_sfx_path])

        bgm_input_idx = None
        if bgm_file and os.path.exists(bgm_file):
            yield log(f"🎵 Đang mix nhạc nền: {os.path.basename(bgm_file)} (Âm lượng: {int(bgm_vol*100)}%)...")
            bgm_input_idx = overlay_inputs.count('-i')
            overlay_inputs.extend(['-stream_loop', '-1', '-i', bgm_file])

        v_filters = []
        curr_v = "0:v"

        if auto_subtitles and os.path.exists(voice_srt_cleaned_path):
            sub_style = payload.get('subtitle_style') or {}
            if payload.get('sub_font') and 'font' not in sub_style:
                sub_style['font'] = payload['sub_font']
            vw, vh = get_video_dimensions_fast(concat_silent_path, ffmpeg_path)
            ass_target = os.path.join(temp_dir, 'rendered_review_subtitles.ass')
            sub_applied = False
            try:
                generate_styled_ass(voice_srt_cleaned_path, ass_target, vw, vh, sub_style)
                if os.path.exists(ass_target) and os.path.getsize(ass_target) > 20:
                    escaped_ass = ass_target.replace('\\', '/').replace(':', '\\:')
                    fonts_dir = os.path.join(ROOT_DIR, 'resources', 'fonts')
                    escaped_fonts = fonts_dir.replace('\\', '/').replace(':', '\\:')
                    if os.path.isdir(fonts_dir):
                        v_filters.append(f"[{curr_v}]subtitles=filename='{escaped_ass}':fontsdir='{escaped_fonts}'[v_sub]")
                    else:
                        v_filters.append(f"[{curr_v}]subtitles=filename='{escaped_ass}'[v_sub]")
                    curr_v = "v_sub"
                    sub_applied = True
            except Exception as e_ass:
                pass
            if not sub_applied:
                escaped_srt = voice_srt_cleaned_path.replace('\\', '/').replace(':', '\\:')
                v_filters.append(f"[{curr_v}]subtitles='{escaped_srt}':force_style='Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=25,MarginL=20,MarginR=20,WrapStyle=0'[v_sub]")
                curr_v = "v_sub"

        if logo_enabled and logo_path and os.path.exists(logo_path):
            logo_idx = overlay_inputs.count('-i')
            overlay_inputs.extend(['-i', logo_path])
            x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
            y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
            w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
            h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
            opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

            vw, vh = get_video_dimensions_fast(concat_silent_path, ffmpeg_path)
            box_w = max(2, (int(round(vw * (w_pct / 100.0))) // 2) * 2)
            box_h = max(2, (int(round(vh * (h_pct / 100.0))) // 2) * 2)
            box_x = max(0, int(round(vw * (x_pct / 100.0))))
            box_y = max(0, int(round(vh * (y_pct / 100.0))))

            v_filters.append(f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f},scale=w={box_w}:h={box_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_scaled]")
            v_filters.append(f"[{curr_v}][logo_scaled]overlay=x='{box_x}+({box_w}-overlay_w)/2':y='{box_y}+({box_h}-overlay_h)/2'[v_logo]")
            curr_v = "v_logo"

        if not v_filters:
            vf_complex = "[0:v]null[v_out]"
        else:
            v_filters[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[v_out]', v_filters[-1])
            vf_complex = ";".join(v_filters)

        audio_filter = ""
        if sfx_input_idx is not None and bgm_input_idx is not None:
            if bgm_ducking:
                audio_filter = f"[1:a]volume=1.0[v_aud];[{sfx_input_idx}:a]volume={orig_vol:.2f}[sfx_raw];[{bgm_input_idx}:a]volume={bgm_vol:.2f}[bgm_raw];[bgm_raw][v_aud]sidechaincompress=threshold=0.08:ratio=4:attack=200:release=800[bgm_duck];[v_aud][sfx_raw][bgm_duck]amix=inputs=3:duration=first:dropout_transition=2[a_out]"
            else:
                audio_filter = f"[1:a]volume=1.0[v_aud];[{sfx_input_idx}:a]volume={orig_vol:.2f}[sfx_raw];[{bgm_input_idx}:a]volume={bgm_vol:.2f}[bgm_raw];[v_aud][sfx_raw][bgm_raw]amix=inputs=3:duration=first:dropout_transition=2[a_out]"
        elif sfx_input_idx is not None:
            audio_filter = f"[1:a]volume=1.0[v_aud];[{sfx_input_idx}:a]volume={orig_vol:.2f}[sfx_raw];[v_aud][sfx_raw]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
        elif bgm_input_idx is not None:
            if bgm_ducking:
                audio_filter = f"[1:a]volume=1.0[v_aud];[{bgm_input_idx}:a]volume={bgm_vol:.2f}[bgm_raw];[bgm_raw][v_aud]sidechaincompress=threshold=0.08:ratio=4:attack=200:release=800[bgm_duck];[v_aud][bgm_duck]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
            else:
                audio_filter = f"[1:a]volume=1.0[v_aud];[{bgm_input_idx}:a]volume={bgm_vol:.2f}[bgm_raw];[v_aud][bgm_raw]amix=inputs=2:duration=first:dropout_transition=2[a_out]"

        filter_chains = [vf_complex]
        if audio_filter:
            filter_chains.append(audio_filter)
        combined_filter = ";".join(filter_chains)

        if encoder == 'h264_nvenc':
            final_enc_cmd = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '22', '-pix_fmt', 'yuv420p']
        elif encoder == 'h264_qsv':
            final_enc_cmd = ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-global_quality', '22', '-pix_fmt', 'yuv420p']
        else:
            final_enc_cmd = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']

        has_audio_out = (sfx_input_idx is not None or bgm_input_idx is not None)
        map_args = ['-map', '[v_out]', '-map', '[a_out]' if has_audio_out else '1:a']

        cmd_overlay = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            *overlay_inputs,
            '-filter_complex', combined_filter,
            *map_args,
            *final_enc_cmd,
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            final_output
        ]
        
        proc_overlay = subprocess.run(cmd_overlay, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
        if proc_overlay.returncode != 0:
            err_msg = (proc_overlay.stderr or '').strip()
            if bgm_input_idx is not None and bgm_file:
                yield log(f"⚠️ Lỗi mix BGM nâng cao ({err_msg[:120] if err_msg else 'FFmpeg'}), đang thử xuất không nhạc nền (giữ nguyên logo & phụ đề)...")
                fallback_inputs = []
                skip_count = 0
                for i, arg in enumerate(overlay_inputs):
                    if skip_count > 0:
                        skip_count -= 1
                        continue
                    if arg == '-stream_loop' and i + 3 < len(overlay_inputs) and overlay_inputs[i+3] == bgm_file:
                        skip_count = 3
                        continue
                    if arg == '-i' and i + 1 < len(overlay_inputs) and overlay_inputs[i+1] == bgm_file:
                        skip_count = 1
                        continue
                    fallback_inputs.append(arg)

                fallback_vf = vf_complex
                if logo_enabled and logo_path and os.path.exists(logo_path) and (logo_path in fallback_inputs):
                    new_logo_idx = fallback_inputs[:fallback_inputs.index(logo_path)].count('-i')
                    fallback_vf = re.sub(rf'\[{logo_idx}:v\]', f'[{new_logo_idx}:v]', fallback_vf)

                has_sfx_fallback = (sfx_input_idx is not None and cleaned_sfx_path and os.path.exists(cleaned_sfx_path) and (cleaned_sfx_path in fallback_inputs))
                if has_sfx_fallback:
                    new_sfx_idx = fallback_inputs[:fallback_inputs.index(cleaned_sfx_path)].count('-i')
                    fallback_af = f"[1:a]volume=1.0[v_aud];[{new_sfx_idx}:a]volume={orig_vol:.2f}[sfx_raw];[v_aud][sfx_raw]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
                    fallback_filter = f"{fallback_vf};{fallback_af}"
                    fallback_map = ['-map', '[v_out]', '-map', '[a_out]']
                else:
                    fallback_filter = fallback_vf
                    fallback_map = ['-map', '[v_out]', '-map', '1:a']

                cmd_fallback = [
                    ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                    *fallback_inputs,
                    '-filter_complex', fallback_filter,
                    *fallback_map,
                    *final_enc_cmd,
                    '-c:a', 'aac', '-b:a', '192k',
                    '-shortest',
                    final_output
                ]
                proc_overlay = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
            if proc_overlay.returncode != 0:
                yield log(f"🛑 Lỗi chèn âm thanh/sub cuối cùng: {proc_overlay.stderr}")
                return
            
        if not os.path.exists(final_output):
            yield log(f"🛑 Không tìm thấy file video đầu ra: {final_output}")
            return

        out_srt = os.path.splitext(final_output)[0] + '.srt'
        if os.path.exists(voice_srt_cleaned_path):
            try:
                shutil.copy2(voice_srt_cleaned_path, out_srt)
            except Exception:
                pass

        # --- BƯỚC 7: POST-RENDER VALIDATOR (KIỂM TRA ĐỒNG BỘ VÀ PTS) ---
        expected_total_dur = tl_report.get('total_voice_duration', 0.0) if 'tl_report' in locals() else None
        val_ok, post_report = validate_rendered_video(final_output, expected_duration=expected_total_dur, ffmpeg_path=ffmpeg_path)
        pts_status_str = "⚠️ CÓ PHÁT HIỆN LỖI PTS" if post_report.get('pts_drop_detected') else "✅ LIÊN TỤC (KHÔNG GIẬT HÌNH)"
        yield log(f"🔍 [POST-RENDER VALIDATOR] Video: {post_report['video_duration']:.2f}s | Audio: {post_report['audio_duration']:.2f}s | Độ lệch: {post_report['drift_ms']:.1f}ms | PTS: {pts_status_str}.")
        if post_report.get('warnings'):
            for w in post_report['warnings']:
                yield log(f"⚠️ [POST-VALIDATOR] {w}")
            
        if not payload.get('skip_history_recording'):
            try:
                from export_history import get_export_history_service
                service = get_export_history_service()
                export_run_id = payload.get('export_run_id') or f"review_{int(time.time()*1000)}"
                service.record_export(
                    output_path=final_output,
                    source_tool='review',
                    source_kind='review',
                    export_run_id=export_run_id,
                    params={
                        'title': payload.get('title'),
                        'video_style': payload.get('video_style')
                    }
                )
            except Exception as he:
                logging.getLogger(__name__).error(f"[ExportHistory] Error recording review export: {he}")

        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                movie_name = payload.get('title') or (os.path.splitext(os.path.basename(video_path))[0] if video_path else "Review Phim")
                file_size_mb = (os.path.getsize(final_output) / (1024 * 1024)) if os.path.exists(final_output) else 0
                notifier.notify_task_success(
                    task_type='review',
                    task_title='Review Phim AI (Auto-Edit)',
                    video_title=movie_name,
                    output_path=final_output,
                    duration_sec=time.time() - start_time_auto_edit,
                    file_size_mb=file_size_mb,
                    extra_info={'Giọng đọc': voice_id, 'Phong cách': payload.get('video_style', '')}
                )
        except Exception as te:
            logging.getLogger(__name__).warning(f"[Telegram] Error sending review notification: {te}")

        yield log(f"Tất cả đã xong! File được lưu tại: {final_output}", step=5)
        yield log("[PROGRESS] 100")
        
    except Exception as e:
        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                movie_name = payload.get('title') or (os.path.splitext(os.path.basename(video_path))[0] if video_path else "Review Phim")
                notifier.notify_task_failure(
                    task_type='review',
                    task_title='Review Phim AI (Auto-Edit)',
                    video_title=movie_name,
                    error_message=str(e),
                    duration_sec=time.time() - start_time_auto_edit
                )
        except Exception as te:
            pass
        yield log(f"🛑 Lỗi không xác định trong Auto-Edit: {str(e)} | {traceback.format_exc()}")


def run_narration_workflow(payload, check_stop_func):
    """Chế độ 'Kể lại Video' - Giữ nguyên video gốc, overlay voice-over + phụ đề."""
    start_time_narration = time.time()
    video_path = payload.get('video_path')
    srt_path = payload.get('srt_path')
    voice_id = payload.get('voice_id', 'ngoc_huyen')
    voice_speed = float(payload.get('voice_speed', 1.0))
    output_dir = payload.get('output_dir', 'output')
    output_name = payload.get('output_name', 'video_narration.mp4')
    
    openai_key, openai_base_url, openai_model = resolve_openai_credentials(payload)
    api_key_openspeaker = payload.get('openspeaker_api_key', '')
    auto_subtitles = payload.get('auto_subtitles', False)
    blur_orig_subs = parse_bool(payload.get('blur_original_subtitles'), False)
    orig_volume = float(payload.get('original_volume', 15)) / 100.0  # 0.0 - 1.0

    if not api_key_openspeaker:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_p = [os.path.join(root_dir, 'api_keys.txt'), 'api_keys.txt']
        try:
            import license_manager
            candidate_p.append(os.path.join(license_manager.get_user_data_dir(), 'api_keys.txt'))
        except Exception:
            pass
        for p in candidate_p:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key_openspeaker = line.split('=', 1)[1].strip()
                            break
                if api_key_openspeaker:
                    break

    continue_from_script = parse_bool(payload.get('continue_from_script'), False)
    pause_after_script = parse_bool(payload.get('pause_after_script', True), True)
    custom_script = payload.get('custom_script')
    custom_srt_content = payload.get('custom_srt_content') or payload.get('narration_srt_content')
    use_cache = bool(payload.get('use_cache', False))

    if not continue_from_script and not custom_script:
        if not openai_key:
            yield "data: 🛑 Lỗi: Chưa tìm thấy OpenAI API Key. Vui lòng vào Cài đặt để nhập Key cá nhân hoặc bấm [Lấy API Cấp Sẵn] nếu bạn dùng gói VIP/1 Năm!\n\n"
            return
        if not srt_path or not os.path.exists(srt_path):
            yield "data: 🛑 Lỗi: Không tìm thấy file SRT đầu vào. Cần SRT gốc để GPT phân tích!\n\n"
            return

    if not video_path or not os.path.exists(video_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file Video đầu vào.\n\n"
        return

    srt_content = ""
    if srt_path and os.path.exists(srt_path):
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()

    ffmpeg_path = None
    try:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    except Exception as e:
        yield f"data: 🛑 Lỗi kiểm tra FFmpeg: {e}\n\n"
        return

    # Tự động nhận diện phần cứng GPU hoặc theo encoder chỉ định
    req_encoder = payload.get('encoder')
    if not req_encoder or str(req_encoder).strip().lower() == 'auto':
        detected_enc, is_gpu_enc, _ = detect_hardware_encoder(ffmpeg_path)
        encoder = detected_enc
    else:
        encoder = str(req_encoder).strip()
        is_gpu_enc = (encoder != 'libx264')

    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    if 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-'):
        headers["HTTP-Referer"] = "https://novacut.app"
        headers["X-Title"] = "NovaCut AI"
    url = f"{openai_base_url.rstrip('/')}/chat/completions"

    os.makedirs(output_dir, exist_ok=True)
    custom_temp = payload.get('temp_dir')
    if custom_temp:
        try:
            norm_custom = os.path.realpath(custom_temp)
            norm_out = os.path.realpath(output_dir)
            if norm_custom.startswith(norm_out):
                temp_dir = custom_temp
            else:
                temp_dir = get_review_temp_dir(output_dir, video_path)
        except Exception:
            temp_dir = get_review_temp_dir(output_dir, video_path)
    else:
        temp_dir = get_review_temp_dir(output_dir, video_path)
    os.makedirs(temp_dir, exist_ok=True)

    def log(msg, step=None):
        if step:
            return f"data: [STEP] {step}\n\ndata: {msg}\n\n"
        return f"data: {msg}\n\n"

    if not use_cache and not continue_from_script and os.path.exists(temp_dir):

        yield log("🧹 Đang dọn dẹp tài liệu cũ để tạo mới hoàn toàn...")
        undeleted = []
        try:
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                except Exception:
                    undeleted.append(item)
            if undeleted:
                yield log(f"⚠️ Một số file tạm đang bị khóa ({', '.join(undeleted[:3])}), hệ thống sẽ ghi đè trực tiếp.")
            else:
                yield log("✨ Đã dọn sạch tài liệu cũ thành công.")
        except Exception as e:
            yield log(f"⚠️ Cảnh báo dọn dẹp tài liệu cũ: {e}")
    os.makedirs(temp_dir, exist_ok=True)
    script_txt_path = os.path.join(temp_dir, 'narration_script.txt')
    voice_audio_path = os.path.join(temp_dir, 'voice_narration.wav')
    voice_srt_path = os.path.join(temp_dir, 'voice_narration.srt')
    voice_srt_cleaned_path = os.path.join(temp_dir, 'voice_narration_cleaned.srt')
    filter_script_path = None

    try:
        # --- BƯỚC 1: ĐỌC VIDEO DURATION & LÊN KỊCH BẢN ---
        yield log("📐 Đang đo thời lượng video gốc...", step=1)
        if check_stop_func(): return

        video_duration = get_video_duration_ffprobe(video_path)
        if video_duration <= 0:
            yield log("🛑 Không thể đo thời lượng video.")
            return

        video_minutes = video_duration / 60.0
        yield log(f"Video gốc: {video_minutes:.1f} phút ({video_duration:.0f} giây).")
        yield log("[PROGRESS] 5")

        narration_script = ""
        if custom_script and str(custom_script).strip():
            narration_script = sanitize_review_script(str(custom_script).strip())
            with open(script_txt_path, 'w', encoding='utf-8') as f:
                f.write(narration_script)
            yield log(f"💚 Sử dụng kịch bản kể lại đã chỉnh sửa của người dùng ({len(narration_script.split())} từ).")
        elif use_cache and os.path.exists(script_txt_path):
            with open(script_txt_path, 'r', encoding='utf-8') as f:
                narration_script = sanitize_review_script(f.read())
            yield log(f"💚 Đã tìm thấy kịch bản cũ, tái sử dụng tại {script_txt_path}")
        else:
            # Đọc prompt narration qua Vault bảo mật
            import prompt_vault
            import review_styles
            prompt_template = prompt_vault.get_prompt('prompt_narration')
            if not prompt_template:
                yield log("🛑 Không tìm thấy nội dung mẫu prompt_narration!")
                return

            review_style = payload.get('review_style', 'dramatic')
            custom_style_prompt = payload.get('custom_style_prompt', '')
            script_language = payload.get('script_language') or payload.get('target_lang') or 'vi'
            style_info = review_styles.get_style_by_id(review_style)
            style_directive = review_styles.get_style_directive(review_style, custom_style_prompt)
            yield log(f"🎭 Phong cách Kể lại: {style_info.get('icon', '🎙️')} {style_info.get('name', 'Mặc định')}")

            lang_code = str(script_language).lower().strip()
            lang_info = LANGUAGE_NAMES.get(lang_code, ('Tiếng Việt', 'Vietnamese'))
            lang_directive = get_language_directive(lang_code)
            yield log(f"🌐 Ngôn ngữ kịch bản đầu ra: {lang_info[0]} ({lang_info[1]})")

            condensed_srt = condense_srt_for_llm(srt_content, max_chars=45000)
            target_words = int(video_minutes * 200)  # ~200 từ/phút (chậm hơn recap để vừa xem)
            prompt_final = prompt_template.replace("{DÁN_NỘI_DUNG_SRT_VÀO_ĐÂY}", condensed_srt) \
                                           .replace("{SỐ_PHÚT}", f"{video_minutes:.1f}") \
                                           .replace("{SỐ_GIÂY}", f"{video_duration:.0f}") \
                                           .replace("{SỐ_TỪ}", str(target_words))

            if lang_directive:
                prompt_final = f"{lang_directive}\n\n{prompt_final}"
            if style_directive:
                prompt_final = f"{style_directive}\n\n{prompt_final}"

            headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            if 'openrouter.ai' in str(openai_base_url) or str(openai_key).startswith('sk-or-'):
                headers["HTTP-Referer"] = "https://novacut.app"
                headers["X-Title"] = "NovaCut AI"
            url = f"{openai_base_url.rstrip('/')}/chat/completions"

            sys_content = f"Bạn là chuyên gia review phim, viết kịch bản voice-over kể lại nội dung phim bằng {lang_info[0]} ({lang_info[1]})." if lang_code != 'vi' else "Bạn là chuyên gia review phim, viết kịch bản voice-over kể lại nội dung phim."
            payload_gpt = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": prompt_final}
                ]
            }

            yield log("Đang gọi AI viết kịch bản kể lại phim (Đã tối ưu Token)...")
            gpt_res, err = call_openai_chat_resilient(
                url=url, headers=headers, payload=payload_gpt,
                max_retries=3, initial_timeout=240, check_stop_func=check_stop_func,
                progress_logger=lambda m: log(m)
            )
            if err or not gpt_res:
                yield log(f"🛑 Lỗi gọi ChatGPT Bước 1: {err or 'Không có phản hồi'}")
                return

            narration_script = sanitize_review_script(gpt_res['content'])
            u = gpt_res.get('usage', {})
            token_str = f" (🪙 {u.get('total_tokens', 0):,} tokens)" if u else ""

            with open(script_txt_path, 'w', encoding='utf-8') as f:
                f.write(narration_script)
            yield log(f"✅ Đã viết kịch bản kể lại ({len(narration_script.split())} từ).{token_str}")

        yield log("[PROGRESS] 20")

        # Tách câu và gửi sự kiện [SCRIPT_READY] cho Frontend
        sentences = split_text_to_sentences(narration_script)
        script_info = {
            "script": narration_script,
            "sentences": sentences,
            "word_count": len(narration_script.split()),
            "sentence_count": len(sentences),
            "est_minutes": round(len(narration_script.split()) / 200.0, 1)
        }
        yield f"data: [SCRIPT_READY] {json.dumps(script_info, ensure_ascii=False)}\n\n"

        if pause_after_script and not continue_from_script:
            yield log(f"⏸️ [TẠM DỪNG DUYỆT KỊCH BẢN] Đã tạo xong kịch bản kể lại ({len(sentences)} câu, {len(narration_script.split())} từ).")
            yield log("📝 Hệ thống đã nạp kịch bản vào bảng bên dưới để bạn xem và chỉnh sửa.")
            yield log("👉 Hãy kiểm tra các câu thoại, nghe thử giọng đọc nếu muốn, sau đó bấm [TIẾP TỤC DỰNG VIDEO] để hoàn tất!")
            return

        # --- BƯỚC 2: TẠO GIỌNG ĐỌC (TỪNG CÂU) ---
        yield log("Đang tạo giọng đọc (Bước 2 - Tách câu TTS)...", step=2)
        if check_stop_func(): return

        if use_cache and not continue_from_script and os.path.exists(voice_audio_path) and os.path.exists(voice_srt_path):
            yield log("💚 Đã tìm thấy file giọng đọc cũ, tái sử dụng.")
        else:
            if is_api_voice(voice_id) and api_key_openspeaker:
                yield log("☁️ Đang gọi OpenSpeaker API tạo giọng đọc và phụ đề 1 lần (with_transcript)...")
                try:
                    temp_aud_raw = os.path.join(temp_dir, 'voice_raw.mp3')
                    ai_dubbing.synthesize_openspeaker_with_transcript(
                        narration_script, voice_id, voice_speed, temp_aud_raw, voice_srt_path, api_key_openspeaker
                    )
                    
                    # Convert raw audio sang PCM WAV 24kHz để khớp pipeline
                    cmd_conv = [
                        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', temp_aud_raw, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
                        voice_audio_path
                    ]
                    subprocess.run(cmd_conv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **get_stealth_subprocess_kwargs())
                    
                    yield log("✅ Đã nhận xong giọng đọc và phụ đề trực tiếp từ API!")
                    yield log("[PROGRESS] 50")
                except Exception as e:
                    yield log(f"⚠️ Lỗi gọi API tạo voice 1 lần ({str(e)}), chuyển sang luồng dự phòng (Tách câu)...")

            if not os.path.exists(voice_audio_path) or not os.path.exists(voice_srt_path):
                sentences = split_text_to_sentences(narration_script)
                yield log(f"Đã tách kịch bản thành {len(sentences)} câu.")

                if not sentences:
                    yield log("🛑 Kịch bản rỗng sau khi tách câu.")
                    return

                tts_threads = int(payload.get('tts_threads', 8))
                yield log(f"Đang tạo giọng đọc cho {len(sentences)} câu (Đa luồng: {tts_threads} workers)...")
                final_audio = None
                final_srt = None
                srt_entries = []
                error = None

                for msg_type, data in generate_tts_per_sentence_stream(
                    sentences, voice_id, voice_speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct=20, end_pct=50, threads=tts_threads
                ):
                    if msg_type == 'progress':
                        curr_i, total_i, step_pct, overall_pct, snippet = data
                        yield log(f"🎙️ [{curr_i}/{total_i} - {step_pct}%] Đang tạo giọng đọc: \"{snippet}\"")
                        yield log(f"[PROGRESS] {overall_pct}")
                    elif msg_type == 'error':
                        error = data
                    elif msg_type == 'done':
                        final_audio, final_srt, srt_entries = data

                if error:
                    if error == "STOPPED": return
                    yield log(f"🛑 {error}")
                    return

                # Di chuyển file về đúng path mong muốn
                if final_audio and final_audio != voice_audio_path and os.path.exists(final_audio):
                    shutil.copy2(final_audio, voice_audio_path)
                if final_srt and final_srt != voice_srt_path and os.path.exists(final_srt):
                    shutil.copy2(final_srt, voice_srt_path)

                yield log(f"✅ Đã tạo xong giọng đọc ({len(srt_entries)} block SRT).")
                yield log("[PROGRESS] 50")

        yield log("[PROGRESS] 50")

        # --- BƯỚC 2.5: CHUẨN HÓA SRT (TỐI ĐA 2 DÒNG) ---
        if use_cache and os.path.exists(voice_srt_cleaned_path) and os.path.getsize(voice_srt_cleaned_path) > 10:
            yield log("💚 Tái sử dụng SRT chuẩn hóa.")
        else:
            raw_entries = parse_srt_entries(voice_srt_path)
            cleaned_entries = enforce_max_2_lines_srt(raw_entries, max_chars_per_line=38)
            with open(voice_srt_cleaned_path, 'w', encoding='utf-8') as f:
                for idx, (s, e, txt) in enumerate(cleaned_entries):
                    f.write(f"{idx+1}\n")
                    f.write(f"{format_srt_time(s)} --> {format_srt_time(e)}\n")
                    f.write(f"{txt}\n\n")
            yield log(f"✅ Chuẩn hóa SRT: {len(cleaned_entries)} block (tối đa 2 dòng/block).")

        yield log("[PROGRESS] 55")

        # --- BƯỚC 3: OVERLAY VOICE + SUB LÊN VIDEO GỐC ---
        yield log("Đang overlay giọng đọc & phụ đề lên video gốc (Bước 3)...", step=3)
        if check_stop_func(): return

        if not output_name.lower().endswith('.mp4'):
            output_name += '.mp4'

        # Xây dựng filter
        filter_parts = []
        curr_v = "0:v"

        # Video Zoom parameter
        raw_zoom = float(payload.get('video_zoom', 100.0))
        zoom_val = (raw_zoom / 100.0) if raw_zoom > 5.0 else raw_zoom
        enable_zoom = bool(payload.get('enable_zoom', False) or payload.get('pan_zoom', False) or zoom_val > 1.005)
        zoom_factor = max(1.0, min(5.0, zoom_val)) if enable_zoom else 1.0

        video_pan_x = float(payload.get('video_pan_x', 0.0))
        video_pan_y = float(payload.get('video_pan_y', 0.0))

        # Phóng to video nếu bật
        if zoom_factor > 1.005:
            yield log(f"🔍 Kích hoạt phóng to video (Zoom: {zoom_factor*100:.0f}%)...")
            vw, vh = get_video_dimensions_fast(video_path, ffmpeg_path)
            crop_w = f"trunc(iw/{zoom_factor:.4f}/2)*2"
            crop_h = f"trunc(ih/{zoom_factor:.4f}/2)*2"
            crop_x = f"(iw-{crop_w})/2 - ({video_pan_x:.1f}*(iw/800))"
            crop_y = f"(ih-{crop_h})/2 - ({video_pan_y:.1f}*(ih/450))"
            filter_parts.append(f"[{curr_v}]crop=w={crop_w}:h={crop_h}:x='max(0,min(iw-ow,trunc(({crop_x})/2)*2))':y='max(0,min(ih-oh,trunc(({crop_y})/2)*2))',scale={vw}:{vh}:flags=lanczos[v_zoomed]")
            curr_v = "v_zoomed"

        # Làm mờ phụ đề gốc nếu bật
        if blur_orig_subs:
            blur_sz = max(3, min(40, int(payload.get('blur_intensity', 15))))
            blur_y = float(payload.get('blur_y_pos', 81.5)) / 100.0
            blur_lead_offset = abs(float(payload.get('blur_lead_offset', -180)) / 1000.0)
            blur_padding = float(payload.get('blur_padding', 220)) / 1000.0
            blur_ai_boxes = payload.get('ai_boxes') or []

            orig_sub_entries = parse_srt_entries(srt_path)
            if blur_ai_boxes and isinstance(blur_ai_boxes, list):
                enriched = []
                for idx, entry in enumerate(orig_sub_entries):
                    s, e = entry[0], entry[1]
                    txt = entry[2] if len(entry) >= 3 else ''
                    ai_b = blur_ai_boxes[idx] if idx < len(blur_ai_boxes) else None
                    if ai_b and isinstance(ai_b, dict) and 'x_pct' in ai_b and 'w_pct' in ai_b:
                        bx = float(ai_b['x_pct']) / 100.0
                        bw = float(ai_b['w_pct']) / 100.0
                        vs = ai_b.get('visual_start')
                        ve = ai_b.get('visual_end')
                        if vs is not None and ve is not None:
                            enriched.append((s, e, txt, bx, bw, float(vs), float(ve)))
                        else:
                            enriched.append((s, e, txt, bx, bw))
                    else:
                        enriched.append(entry)
                orig_sub_entries = enriched

            if orig_sub_entries:
                yield log(f"✨ Làm mờ {len(orig_sub_entries)} đoạn phụ đề gốc (Độ mờ: {blur_sz}px)...")
                dyn_filters, curr_v = build_dynamic_blur_filter_chain(
                    curr_v, orig_sub_entries,
                    blur_sz=blur_sz,
                    y_ratio=blur_y,
                    h_ratio=0.095,
                    center_x_ratio=0.50,
                    lead_sec=blur_lead_offset,
                    pad_sec=blur_padding
                )
                filter_parts.extend(dyn_filters)

        # Burn-in subtitle mới
        if auto_subtitles and os.path.exists(voice_srt_cleaned_path):
            sub_style = payload.get('subtitle_style') or {}
            if payload.get('sub_font') and 'font' not in sub_style:
                sub_style['font'] = payload['sub_font']
            vw, vh = get_video_dimensions_fast(video_path, ffmpeg_path)
            ass_target = os.path.join(temp_dir, 'rendered_review_subtitles.ass')
            sub_applied = False
            try:
                generate_styled_ass(voice_srt_cleaned_path, ass_target, vw, vh, sub_style)
                if os.path.exists(ass_target) and os.path.getsize(ass_target) > 20:
                    escaped_ass = ass_target.replace('\\', '/').replace(':', '\\:')
                    fonts_dir = os.path.join(ROOT_DIR, 'resources', 'fonts')
                    escaped_fonts = fonts_dir.replace('\\', '/').replace(':', '\\:')
                    if os.path.isdir(fonts_dir):
                        filter_parts.append(f"[{curr_v}]subtitles=filename='{escaped_ass}':fontsdir='{escaped_fonts}'[v_sub]")
                    else:
                        filter_parts.append(f"[{curr_v}]subtitles=filename='{escaped_ass}'[v_sub]")
                    curr_v = "v_sub"
                    sub_applied = True
            except Exception as e_ass:
                pass
            if not sub_applied:
                escaped_srt = voice_srt_cleaned_path.replace('\\', '/').replace(':', '\\:')
                filter_parts.append(f"[{curr_v}]subtitles='{escaped_srt}':force_style='Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=25,MarginL=20,MarginR=20,WrapStyle=0'[v_sub]")
                curr_v = "v_sub"

        # Inputs cho FFmpeg
        inputs_list = ['-i', video_path, '-i', voice_audio_path]

        # Logo Watermark cho Narration
        logo_data = payload.get('logo') or {}
        logo_enabled = bool(logo_data.get('enabled', False))
        logo_path = logo_data.get('path', '').strip()
        if logo_enabled and logo_path and os.path.exists(logo_path):
            logo_idx = inputs_list.count('-i')
            inputs_list.extend(['-i', logo_path])
            x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
            y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
            w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
            h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
            opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

            vw, vh = get_video_dimensions_fast(video_path, ffmpeg_path)
            box_w = max(2, (int(round(vw * (w_pct / 100.0))) // 2) * 2)
            box_h = max(2, (int(round(vh * (h_pct / 100.0))) // 2) * 2)
            box_x = max(0, int(round(vw * (x_pct / 100.0))))
            box_y = max(0, int(round(vh * (y_pct / 100.0))))

            filter_parts.append(f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f},scale=w={box_w}:h={box_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_scaled]")
            filter_parts.append(f"[{curr_v}][logo_scaled]overlay=x='{box_x}+({box_w}-overlay_w)/2':y='{box_y}+({box_h}-overlay_h)/2'[v_logo]")
            curr_v = "v_logo"

        # Hoàn tất video filter
        if not filter_parts:
            video_filter = f"[0:v]null[vout]"
        else:
            last = filter_parts[-1]
            filter_parts[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[vout]', last)
            video_filter = ";".join(filter_parts)

        # Kiểm tra xem video gốc có kênh âm thanh hay không
        has_orig_audio = True
        try:
            p_cmd = [ffmpeg_path, '-i', video_path]
            p_proc = subprocess.run(p_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', **get_stealth_subprocess_kwargs())
            has_orig_audio = 'Audio:' in p_proc.stderr
        except Exception:
            pass

        # AI Stem Separation (Lọc bỏ lời thoại cũ, giữ lại hiệu ứng SFX)
        stem_sep_data = payload.get('stem_separation', {})
        stem_enabled = bool(stem_sep_data.get('enabled', False) or payload.get('remove_original_vocals', False))
        sfx_idx = None
        if stem_enabled and has_orig_audio:
            yield log("🎛️ Bắt đầu tách âm thanh AI (MDX-Net) để lọc sạch lời thoại cũ & bảo lưu tiếng động SFX...")
            try:
                stem_mode = stem_sep_data.get('mode', 'mdx_net_hq4')
                stem_device = stem_sep_data.get('device', 'auto')
                sep_res = yield from run_audio_separator_with_progress(
                    video_path=video_path,
                    output_dir=temp_dir,
                    mode=stem_mode,
                    device=stem_device,
                    log_func=log,
                    check_stop_func=check_stop_func
                )
                if sep_res and sep_res.get('cleaned_path') and os.path.exists(sep_res.get('cleaned_path')):
                    sfx_idx = inputs_list.count('-i')
                    inputs_list.extend(['-i', sep_res.get('cleaned_path')])
                    yield log("✅ Đã tách và bảo lưu âm thanh nền SFX thành công!")
            except Exception as e:
                yield log(f"⚠️ Lỗi tách âm thanh: {e} (Tiếp tục với âm thanh gốc)")

        # Audio mix: giảm volume gốc / SFX (nếu có audio) + overlay voice
        orig_audio_src = f"[{sfx_idx}:a]" if sfx_idx is not None else "[0:a]"
        if has_orig_audio and orig_volume > 0.01:
            audio_filter = f"{orig_audio_src}volume={orig_volume:.2f}[a_orig];[1:a]volume=2.5[a_voice];[a_orig][a_voice]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        else:
            audio_filter = f"[1:a]volume=2.5[aout]"

        full_filter = f"{video_filter};{audio_filter}"

        # BGM
        bgm_data = payload.get('bgm') or {}
        bgm_enabled = bool(bgm_data.get('enabled', False))
        bgm_vol = max(0.0, min(1.0, float(bgm_data.get('volume', 15)) / 100.0))
        bgm_path = bgm_data.get('path', '').strip()
        bgm_file = None
        if bgm_enabled:
            if bgm_path and os.path.exists(bgm_path):
                bgm_file = bgm_path
            else:
                bgm_preset = bgm_data.get('preset', '')
                preset_dir = os.path.join(ROOT_DIR, 'backgroundmusic')
                if bgm_preset and os.path.exists(os.path.join(preset_dir, bgm_preset)):
                    bgm_file = os.path.join(preset_dir, bgm_preset)
                elif os.path.exists(preset_dir):
                    bgm_files = [os.path.join(preset_dir, f) for f in os.listdir(preset_dir) if f.lower().endswith(('.mp3', '.m4a', '.wav', '.aac'))]
                    if bgm_files:
                        bgm_file = random.choice(bgm_files)

        # Lệnh FFmpeg cuối
        temp_no_bgm = os.path.join(temp_dir, 'narration_no_bgm.mp4')
        render_target = temp_no_bgm if bgm_file else os.path.join(output_dir, output_name)

        filter_script_path = None
        filter_args = []
        if full_filter:
            try:
                filter_script_path = os.path.join(temp_dir, f'narration_filter_{int(time.time()*1000)}.txt')
                with open(filter_script_path, 'w', encoding='utf-8') as f_fc:
                    f_fc.write(full_filter)
                fc_flag = ffmpeg_installer.get_filter_script_flag(ffmpeg_path)
                filter_args = [fc_flag, filter_script_path]
            except Exception:
                filter_script_path = None
                filter_args = ['-filter_complex', full_filter]

        # Cấu hình tham số encoder video linh hoạt theo GPU / CPU
        if encoder == 'h264_nvenc':
            enc_v_args = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '22', '-pix_fmt', 'yuv420p']
        elif encoder == 'hevc_nvenc':
            enc_v_args = ['-c:v', 'hevc_nvenc', '-preset', 'p4', '-cq', '24', '-pix_fmt', 'yuv420p']
        elif encoder == 'h264_qsv':
            enc_v_args = ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-global_quality', '22', '-pix_fmt', 'yuv420p']
        elif encoder == 'h264_amf':
            enc_v_args = ['-c:v', 'h264_amf', '-quality', 'speed', '-qp_i', '22', '-qp_p', '22', '-pix_fmt', 'yuv420p']
        elif encoder == 'h264_mf':
            enc_v_args = ['-c:v', 'h264_mf', '-rate_control', 'vbr', '-b:v', '6000k', '-pix_fmt', 'yuv420p']
        else:
            enc_v_args = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p']

        cmd = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info',
            *inputs_list,
            *filter_args,
            '-map', '[vout]', '-map', '[aout]',
            *enc_v_args,
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            render_target
        ]

        enc_display = f"GPU ({encoder})" if encoder != 'libx264' else "CPU (libx264)"
        yield log(f"🎬 Đang render video gốc với giọng đọc và phụ đề [{enc_display}] ({video_duration:.0f}s)...")
        render_success = yield from run_ffmpeg_with_progress_yield(
            cmd,
            total_duration=video_duration,
            start_pct=55,
            end_pct=90,
            desc=f"Render video ({encoder})",
            check_stop_func=check_stop_func
        )

        # Cơ chế dự phòng: Tự động fallback về CPU libx264 nếu GPU gặp sự cố driver / out-of-memory
        if not render_success and encoder != 'libx264' and not check_stop_func():
            yield log(f"⚠️ Bộ mã hóa GPU {encoder} gặp sự cố, tự động chuyển sang chế độ dự phòng CPU (libx264)...")
            cmd_fallback = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info',
                *inputs_list,
                *filter_args,
                '-map', '[vout]', '-map', '[aout]',
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k',
                '-shortest',
                render_target
            ]
            render_success = yield from run_ffmpeg_with_progress_yield(
                cmd_fallback,
                total_duration=video_duration,
                start_pct=55,
                end_pct=90,
                desc="Render video (CPU Fallback)",
                check_stop_func=check_stop_func
            )
        if filter_script_path and os.path.exists(filter_script_path):
            try:
                os.remove(filter_script_path)
                filter_script_path = None
            except Exception:
                pass

        if not render_success or not os.path.exists(render_target):
            yield log("🛑 Không thể hoàn tất render video.")
            return

        yield log("[PROGRESS] 90")

        # --- BƯỚC 4: THÊM BGM (NẾU BẬT) ---
        final_output = os.path.join(output_dir, output_name)

        if bgm_file:
            yield log(f"🎵 Đang mix nhạc nền: {os.path.basename(bgm_file)}...", step=4)
            cmd_bgm = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', temp_no_bgm, '-stream_loop', '-1', '-i', bgm_file,
                '-filter_complex', f"[0:a]volume=1.0[a0];[1:a]volume={bgm_vol:.2f}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac',
                final_output
            ]
            proc_bgm = subprocess.run(cmd_bgm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **get_stealth_subprocess_kwargs())
            if proc_bgm.returncode != 0:
                yield log(f"⚠️ Lỗi mix BGM, sử dụng bản không nhạc nền: {proc_bgm.stderr[:200]}")
                shutil.copy2(temp_no_bgm, final_output)
        else:
            if bgm_enabled:
                yield log("Không tìm thấy nhạc nền, bỏ qua.")

        yield log("[PROGRESS] 95")

        if not os.path.exists(final_output):
            yield log(f"🛑 Không tìm thấy file đầu ra: {final_output}")
            return

        out_srt = os.path.splitext(final_output)[0] + '.srt'
        if os.path.exists(voice_srt_cleaned_path):
            try:
                shutil.copy2(voice_srt_cleaned_path, out_srt)
            except Exception:
                pass

        if not payload.get('skip_history_recording'):
            try:
                from export_history import get_export_history_service
                service = get_export_history_service()
                export_run_id = payload.get('export_run_id') or f"narration_{int(time.time()*1000)}"
                service.record_export(
                    output_path=final_output,
                    source_tool='narration',
                    source_kind='narration',
                    export_run_id=export_run_id,
                    params={
                        'video_path': video_path,
                        'voice_id': payload.get('voice_id')
                    }
                )
            except Exception as he:
                logging.getLogger(__name__).error(f"[ExportHistory] Error recording narration export: {he}")

        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                movie_name = os.path.splitext(os.path.basename(video_path))[0] if video_path else "Kể Lại Phim"
                file_size_mb = (os.path.getsize(final_output) / (1024 * 1024)) if os.path.exists(final_output) else 0
                notifier.notify_task_success(
                    task_type='narration',
                    task_title='Kể Lại Phim (Narration)',
                    video_title=movie_name,
                    output_path=final_output,
                    duration_sec=time.time() - start_time_narration,
                    file_size_mb=file_size_mb,
                    extra_info={'Giọng đọc': voice_id}
                )
        except Exception as te:
            logging.getLogger(__name__).warning(f"[Telegram] Error sending narration notification: {te}")

        yield log(f"🎉 HOÀN THÀNH! Video kể lại phim đã lưu tại: {final_output}", step=5)
        yield log("[PROGRESS] 100")

    except Exception as e:
        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                movie_name = os.path.splitext(os.path.basename(video_path))[0] if video_path else "Kể Lại Phim"
                notifier.notify_task_failure(
                    task_type='narration',
                    task_title='Kể Lại Phim (Narration)',
                    video_title=movie_name,
                    error_message=str(e),
                    duration_sec=time.time() - start_time_narration if 'start_time_narration' in locals() else None
                )
        except Exception as te:
            pass
        yield log(f"🛑 Lỗi không xác định trong Narration: {str(e)} | {traceback.format_exc()}")
    finally:
        if 'filter_script_path' in locals() and filter_script_path and os.path.exists(filter_script_path):
            try:
                os.remove(filter_script_path)
            except Exception:
                pass
