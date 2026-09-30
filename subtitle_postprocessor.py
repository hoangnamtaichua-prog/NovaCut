# -*- coding: utf-8 -*-
"""
subtitle_postprocessor.py
Hậu kiểm SRT deterministic cho NovaCut:
- Chuẩn hóa timestamp (start < end, float seconds, time string)
- Sắp xếp (sort) theo start time
- Xóa dòng lỗi (rỗng, start >= end, timestamp âm, text rỗng)
- Xử lý overlap (không để phụ đề chồng lấn)
- Gộp / xóa câu trùng nếu khoảng cách < 0.7s
- Đánh lại ID tuần tự
- Kiểm tra tính hợp lệ của bản dịch (bảo đảm không sót câu chưa dịch, câu nguồn, câu song ngữ, sai target lang)
"""

import re
import os
import copy
from typing import List, Dict, Any, Tuple


def time_to_seconds(time_val: Any) -> float:
    """Chuyển đổi linh hoạt chuỗi timestamp SRT hoặc số sang float seconds."""
    if isinstance(time_val, (int, float)):
        return max(0.0, float(time_val))
    s = str(time_val or '').strip().replace(',', '.')
    if not s:
        return 0.0
    if ' - ' in s:
        s = s.split(' - ')[0].strip()
    elif '-->' in s:
        s = s.split('-->')[0].strip()
    parts = s.split(':')
    try:
        if len(parts) == 3:
            return max(0.0, float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2]))
        if len(parts) == 2:
            return max(0.0, float(parts[0]) * 60.0 + float(parts[1]))
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return 0.0


def seconds_to_srt_time(seconds: float) -> str:
    """Chuyển đổi số giây sang định dạng chuẩn SRT 00:00:00,000."""
    sec = max(0.0, float(seconds))
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    msecs = int(round((sec - int(sec)) * 1000))
    if msecs >= 1000:
        secs += 1
        msecs -= 1000
    if secs >= 60:
        mins += 1
        secs -= 60
    if mins >= 60:
        hrs += 1
        mins -= 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"


def is_valid_translation(source_text: str, trans_text: str, target_lang: str = 'vi', source_lang: str = 'auto') -> bool:
    """
    Kiểm tra bản dịch có hợp lệ không:
    - Không được rỗng
    - Không được giữ nguyên chữ Hán nếu target lang là tiếng Việt hoặc tiếng Anh
    - Không được giống y hệt câu nguồn (câu chưa dịch) nếu nguồn là tiếng nước ngoài
    - Không được chứa câu song ngữ (vd: '你好 (Xin chào)')
    - Target lang phải tương ứng
    """
    s_txt = str(source_text or '').strip()
    t_txt = str(trans_text or '').strip()

    if not t_txt:
        return False

    low_t = t_txt.lower()
    # 0. Kiểm tra thông báo lỗi API hoặc hệ thống
    if any(err_kw in low_t for err_kw in ('[lỗi', '[error', 'api error', 'quota', 'rate limit', 'error:', 'exception')):
        return False

    tgt = str(target_lang or 'vi').lower()
    src = str(source_lang or 'auto').lower()

    # 1. Kiểm tra chữ Hán sót lại khi dịch sang Vi hoặc En
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', t_txt))
    if has_chinese and tgt in ('vi', 'vietnamese', 'en', 'english'):
        return False

    # 2. Câu chưa dịch: bản dịch giống hệt câu nguồn ngoại ngữ
    src_clean = re.sub(r'[^\w\s]', '', s_txt.lower()).strip()
    trans_clean = re.sub(r'[^\w\s]', '', t_txt.lower()).strip()
    if src_clean and trans_clean and src_clean == trans_clean:
        # Nếu nguồn có chữ Hán hoặc target khác source mà text y hệt -> chưa dịch
        if bool(re.search(r'[\u4e00-\u9fff]', s_txt)) and tgt in ('vi', 'vietnamese', 'en', 'english'):
            return False
        if src in ('zh', 'cn', 'chinese') and tgt in ('vi', 'vietnamese', 'en', 'english'):
            return False
        if src in ('en', 'english') and tgt in ('vi', 'vietnamese') and len(src_clean) > 3:
            return False

    # 3. Câu song ngữ ngoài ý muốn: chứa cả chữ Hán nguồn lẫn chữ Latin
    if has_chinese and re.search(r'[a-zA-Zà-ỹÀ-Ỹ]', t_txt):
        return False

    # 4. Kiểm tra target English: không được chứa dấu tiếng Việt
    if tgt in ('en', 'english'):
        # Ký tự tiếng Việt có dấu
        if re.search(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', t_txt, re.IGNORECASE):
            return False

    return True


def validate_subtitles_for_export(subtitles: List[Dict[str, Any]], target_lang: str = 'vi', source_lang: str = 'auto') -> Tuple[bool, List[str], List[str]]:
    """
    Hậu kiểm nghiêm ngặt danh sách phụ đề trước khi xuất video:
    Trả về: (is_valid, error_messages, invalid_ids)
    """
    if not subtitles or not isinstance(subtitles, list):
        return False, ["Danh sách phụ đề rỗng"], []

    errors = []
    invalid_ids = []

    for idx, s in enumerate(subtitles, 1):
        sid = str(s.get('id', idx))
        src_text = str(s.get('text') or s.get('original_text') or '').strip()
        trans_text = str(s.get('translation') or '').strip()

        raw_st = s.get('startSeconds') if s.get('startSeconds') is not None else s.get('start_sec', s.get('start', s.get('start_time', 0)))
        raw_et = s.get('endSeconds') if s.get('endSeconds') is not None else s.get('end_sec', s.get('end', s.get('end_time', 0)))
        if (raw_st == 0 or raw_st is None) and (raw_et == 0 or raw_et is None) and s.get('time'):
            t_str = str(s.get('time')).strip()
            t_parts = t_str.split('-->') if '-->' in t_str else t_str.split(' - ')
            if len(t_parts) >= 2:
                raw_st = t_parts[0].strip()
                raw_et = t_parts[1].strip()
        st = time_to_seconds(raw_st)
        et = time_to_seconds(raw_et)

        if et <= st:
            errors.append(f"Câu ID {sid}: Timestamp không hợp lệ ({st:.2f}s >= {et:.2f}s)")
            invalid_ids.append(sid)
            continue

        if not trans_text:
            errors.append(f"Câu ID {sid}: Chưa có bản dịch")
            invalid_ids.append(sid)
            continue

        if not is_valid_translation(src_text, trans_text, target_lang=target_lang, source_lang=source_lang):
            errors.append(f"Câu ID {sid}: Bản dịch không hợp lệ hoặc sai ngôn ngữ đích ({trans_text[:30]}...)")
            invalid_ids.append(sid)

    return (len(invalid_ids) == 0), errors, invalid_ids


def deterministic_normalize_subtitles(subtitles: List[Dict[str, Any]], dedup_window: float = 0.7, min_gap_sec: float = None, reindex: bool = True) -> List[Dict[str, Any]]:
    """
    Hậu kiểm SRT deterministic:
    1. Parse chuẩn hóa timestamp
    2. Lọc bỏ các dòng lỗi (rỗng, start >= end, timestamp âm)
    3. Sort ổn định theo start time
    4. Gộp / xóa câu trùng text nếu khoảng cách < dedup_window (0.7s)
    5. Xử lý overlap (không để đè lấn)
    6. Đánh lại ID tuần tự 1..N (nếu reindex=True) hoặc bảo toàn ID gốc (nếu reindex=False)
    7. Cập nhật time string chuẩn
    """
    if not subtitles or not isinstance(subtitles, list):
        return []

    if min_gap_sec is not None:
        dedup_window = float(min_gap_sec)

    parsed_items = []
    for s in subtitles:
        if not isinstance(s, dict):
            continue
        raw_st = s.get('startSeconds') if s.get('startSeconds') is not None else s.get('start_sec', s.get('start', s.get('start_time', 0)))
        raw_et = s.get('endSeconds') if s.get('endSeconds') is not None else s.get('end_sec', s.get('end', s.get('end_time', 0)))
        if (raw_st == 0 or raw_st is None) and (raw_et == 0 or raw_et is None) and s.get('time'):
            t_str = str(s.get('time')).strip()
            t_parts = t_str.split('-->') if '-->' in t_str else t_str.split(' - ')
            if len(t_parts) >= 2:
                raw_st = t_parts[0].strip()
                raw_et = t_parts[1].strip()
        st = time_to_seconds(raw_st)
        et = time_to_seconds(raw_et)

        text = str(s.get('text') or s.get('original_text') or '').strip()
        trans = str(s.get('translation') or '').strip()

        # Bỏ qua nếu cả text lẫn translation đều rỗng
        if not text and not trans:
            continue

        # Xóa dòng lỗi: nếu end <= start hoặc âm -> loại bỏ ngay lập tức
        if et <= st or st < 0:
            continue

        st = round(max(0.0, st), 3)
        et = round(max(st + 0.1, et), 3)

        item = copy.deepcopy(s)
        item['startSeconds'] = st
        item['endSeconds'] = et
        item['text'] = text
        item['translation'] = trans
        parsed_items.append(item)

    if not parsed_items:
        return []

    # 2. Sort ổn định theo startSeconds, sau đó endSeconds
    parsed_items.sort(key=lambda x: (x['startSeconds'], x['endSeconds']))

    # 3. Gộp / xóa câu trùng lặp text nếu khoảng cách < dedup_window
    deduped = []
    for item in parsed_items:
        if not deduped:
            deduped.append(item)
            continue

        prev = deduped[-1]
        prev_txt = (prev.get('translation') or prev.get('text') or '').strip().lower()
        curr_txt = (item.get('translation') or item.get('text') or '').strip().lower()

        # Làm sạch dấu câu để so sánh text cốt lõi
        prev_clean = re.sub(r'[^\w\s]', '', prev_txt)
        curr_clean = re.sub(r'[^\w\s]', '', curr_txt)

        is_same_text = bool(prev_clean and curr_clean and prev_clean == curr_clean)
        gap = item['startSeconds'] - prev['endSeconds']
        start_gap = item['startSeconds'] - prev['startSeconds']

        # Nếu trùng text và khoảng cách kết thúc-bắt đầu < dedup_window hoặc bắt đầu-bắt đầu < dedup_window
        if is_same_text and (gap < dedup_window or start_gap < dedup_window):
            # Gộp khoảng thời gian
            prev['endSeconds'] = round(max(prev['endSeconds'], item['endSeconds']), 3)
            # Ưu tiên bản dịch dài hơn / đầy đủ hơn nếu có
            if len(item.get('translation', '')) > len(prev.get('translation', '')):
                prev['translation'] = item['translation']
            continue

        deduped.append(item)

    # 4. Xử lý Overlap: Không để câu sau chen vào thời gian hiển thị của câu trước
    for i in range(len(deduped) - 1):
        curr = deduped[i]
        nxt = deduped[i + 1]
        if curr['endSeconds'] > nxt['startSeconds']:
            overlap = curr['endSeconds'] - nxt['startSeconds']
            # Nếu overlap nhỏ hoặc câu sau bắt đầu sau curr.startSeconds
            if nxt['startSeconds'] > curr['startSeconds'] + 0.3:
                curr['endSeconds'] = round(nxt['startSeconds'], 3)
            else:
                # Dịch chuyển start của nxt
                nxt['startSeconds'] = round(curr['endSeconds'], 3)
                if nxt['endSeconds'] <= nxt['startSeconds']:
                    nxt['endSeconds'] = round(nxt['startSeconds'] + 1.0, 3)

    # 5. Đánh lại ID tuần tự & Chuẩn hóa time string
    result = []
    for idx, item in enumerate(deduped, 1):
        st = round(item['startSeconds'], 3)
        et = round(max(st + 0.1, item['endSeconds']), 3)
        item['id'] = idx if reindex else item.get('id', idx)
        item['startSeconds'] = st
        item['endSeconds'] = et
        item['start'] = seconds_to_srt_time(st)
        item['end'] = seconds_to_srt_time(et)
        item['time'] = f"{seconds_to_srt_time(st).replace(',', '.')} - {seconds_to_srt_time(et).replace(',', '.')}"
        result.append(item)

    return result


def export_subtitles_to_srt_file(subtitles: List[Dict[str, Any]], output_path: str, prefer_translation: bool = True) -> str:
    """Ghi danh sách phụ đề ra file SRT chuẩn định dạng UTF-8."""
    norm_subs = deterministic_normalize_subtitles(subtitles)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, sub in enumerate(norm_subs, 1):
            st_str = seconds_to_srt_time(sub['startSeconds'])
            et_str = seconds_to_srt_time(sub['endSeconds'])
            if prefer_translation:
                txt = sub.get('translation') or sub.get('text') or ''
            else:
                txt = sub.get('text') or sub.get('translation') or ''
            f.write(f"{idx}\n{st_str} --> {et_str}\n{txt.strip()}\n\n")
    return output_path
