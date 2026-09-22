"""
Module Downloader cho AI-Movie-Shorts
Áp dụng đầy đủ chuẩn kỹ thuật từ Technical Specification (document.md):
1. URL Parser & Canonicalizer (Section 6)
2. Media Resolver (Section 8)
3. Stream Downloader với HTTP Range Resume, Chunking & Exponential Backoff Retry (Section 9 & 27)
4. FFmpeg Post-processing & Remuxing (Section 13)
5. File Naming & Sanitization (Section 28)
"""

import os
import re
import sys
import json
import time
import random
import hashlib
import requests
import subprocess
import yt_dlp
import ffmpeg_installer
import concurrent.futures
import threading


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

def get_ffmpeg_dir():
    ffmpeg_path = ffmpeg_installer.get_ffmpeg_path()
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        return os.path.dirname(ffmpeg_path)
    bin_dir = os.path.join(ROOT_DIR, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'ffmpeg.exe')):
        return bin_dir
    return None


def probe_video_specs(file_path):
    """
    Phân tích chi tiết thông số kỹ thuật của file video/audio bằng ffprobe:
    - Độ phân giải thực tế (width x height)
    - Tên mức chuẩn (1080p Full HD, 4K Ultra HD, 720p HD, v.v.)
    - Tỉ lệ khung hình (16:9 Ngang, 9:16 Dọc TikTok, v.v.)
    - Tốc độ khung hình (FPS)
    - Codec video (H.264, HEVC, VP9, AV1...) & Codec audio (AAC, MP3...)
    - Thời lượng (giây) & Dung lượng file (MB)
    - Chuỗi tóm tắt thông số trực quan
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        ffmpeg_path = ffmpeg_installer.get_ffmpeg_path()
        ffprobe = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe') if ffmpeg_path else 'ffprobe'
        cmd = [
            ffprobe, '-v', 'error',
            '-show_entries', 'format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate',
            '-of', 'json', file_path
        ]
        kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs() if hasattr(ffmpeg_installer, 'get_stealth_subprocess_kwargs') else {}
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, **kwargs)
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
        streams = data.get('streams', [])
        fmt = data.get('format', {})

        v_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        a_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

        file_size = int(fmt.get('size') or os.path.getsize(file_path) or 0)
        size_mb = f"{file_size / (1024*1024):.1f} MB"
        duration = float(fmt.get('duration') or 0.0)

        if not v_stream:
            acodec = a_stream.get('codec_name', 'audio').upper() if a_stream else 'AUDIO'
            return {
                'is_video': False,
                'is_audio': True,
                'acodec': acodec,
                'duration': round(duration, 2),
                'file_size': size_mb,
                'summary': f"Âm thanh {acodec} • {size_mb}"
            }

        w = int(v_stream.get('width') or 0)
        h = int(v_stream.get('height') or 0)
        vcodec = v_stream.get('codec_name', 'video').upper()
        acodec = a_stream.get('codec_name', '').upper() if a_stream else None

        fps = 0.0
        fps_str = v_stream.get('r_frame_rate') or v_stream.get('avg_frame_rate') or '0/0'
        if '/' in fps_str:
            num, den = fps_str.split('/')
            if float(den) > 0:
                fps = round(float(num) / float(den), 2)
        fps_disp = int(fps) if fps.is_integer() else fps

        min_dim = min(w, h) if w > 0 and h > 0 else 0
        max_dim = max(w, h) if w > 0 and h > 0 else 0

        if max_dim >= 3840 or min_dim >= 2160:
            res_label = '4K Ultra HD'
        elif max_dim >= 2560 or min_dim >= 1440:
            res_label = '2K QHD'
        elif max_dim >= 1920 or min_dim >= 1080:
            res_label = '1080p Full HD'
        elif max_dim >= 1280 or min_dim >= 720:
            res_label = '720p HD'
        elif min_dim >= 480:
            res_label = '480p SD'
        elif min_dim >= 360:
            res_label = '360p'
        else:
            res_label = f'{min_dim}p' if min_dim > 0 else 'SD'

        is_vertical = h > w if w > 0 and h > 0 else False
        ratio_str = '9:16 (Dọc)' if is_vertical else ('16:9 (Ngang)' if abs(w / max(1, h) - 16 / 9) < 0.05 else f'{w}:{h}')

        summary = f"{w}x{h} ({res_label}) • {fps_disp} FPS • {vcodec} • {ratio_str} • {size_mb}"

        return {
            'is_video': True,
            'is_audio': False,
            'width': w,
            'height': h,
            'resolution': f"{w}x{h}",
            'resolution_label': res_label,
            'fps': fps_disp,
            'aspect_ratio': ratio_str,
            'is_vertical': is_vertical,
            'vcodec': vcodec,
            'acodec': acodec,
            'duration': round(duration, 2),
            'file_size': size_mb,
            'summary': summary
        }
    except Exception as e:
        return {'error': str(e)}


# =========================================================================
# 1. URL PARSER & CANONICALIZER (document.md Section 6)
# =========================================================================
def clean_url_input(text):
    """
    Trích xuất link URL sạch nếu người dùng dán cả đoạn văn bản chia sẻ từ TikTok/Douyin/YouTube
    """
    if not text:
        return ''
    text = text.strip()
    match = re.search(r'(https?://[^\s\'"<>]+)', text)
    if match:
        url = match.group(1).rstrip('.,;!?/')
        
        # Sửa lỗi link Douyin dạng modal_id (thường từ link chia sẻ trên web)
        if 'douyin.com' in url and 'modal_id=' in url:
            modal_match = re.search(r'modal_id=(\d+)', url)
            if modal_match:
                video_id = modal_match.group(1)
                url = f"https://www.douyin.com/video/{video_id}"
                
        return url
    return text

def parse_douyin_url(input_text):
    """
    Chuẩn hóa URL Douyin và trích xuất video_id theo chuẩn Section 6
    """
    clean_url = clean_url_input(input_text)
    if not clean_url:
        return None, None
        
    video_id = None
    
    # 1. Link dạng /video/123456789
    vid_match = re.search(r'/video/(\d+)', clean_url)
    if vid_match:
        video_id = vid_match.group(1)
        canonical = f"https://www.douyin.com/video/{video_id}"
        return canonical, video_id
        
    # 2. Link dạng modal_id=123456789
    if 'modal_id=' in clean_url:
        modal_match = re.search(r'modal_id=(\d+)', clean_url)
        if modal_match:
            video_id = modal_match.group(1)
            canonical = f"https://www.douyin.com/video/{video_id}"
            return canonical, video_id
            
    # 3. Link rút gọn v.douyin.com/xyz
    return clean_url, None

def is_douyin_url(url):
    """Kiểm tra xem URL có phải thuộc nền tảng Douyin không"""
    if not url:
        return False
    return any(domain in url.lower() for domain in ['douyin.com', 'iesdouyin.com', 'v.douyin.com'])

def is_bilibili_url(url):
    """Kiểm tra xem URL có phải thuộc nền tảng Bilibili không"""
    if not url:
        return False
    u = url.lower()
    return any(domain in u for domain in ['bilibili.com', 'b23.tv'])

def sanitize_filename_windows(name, max_len=120):
    r"""
    Vệ sinh tên file theo chuẩn Windows (loại bỏ \ / : * ? " < > | và ký tự điều khiển).
    Bảo tồn trọn vẹn Unicode (tiếng Việt, tiếng Trung, v.v.), không cắt cụt quá sớm.
    """
    if not name:
        return 'video'
    # Loại bỏ ký tự cấm của Windows
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]', '', str(name)).strip()
    # Windows không cho phép file kết thúc bằng '.' hoặc khoảng trắng
    clean = clean.rstrip('. ')
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip('. ')
    return clean or 'video'

def sanitize_filename(name, max_len=120):
    r"""Alias tương thích cho sanitize_filename_windows."""
    return sanitize_filename_windows(name, max_len=max_len)

def resolve_unique_filename(dir_path, base_title, ext='mp4', prefix_index=None):
    """
    Tạo tên file an toàn cho Windows không bị trùng tên (collision handling):
    - Dùng prefix_index nếu được chỉ định: 001_{title}.mp4
    - Nếu trùng tên: {stem} (2).mp4, {stem} (3).mp4 theo quy ước Windows.
    - Trả về: (final_path, file_stem)
    """
    safe_title = sanitize_filename_windows(base_title)
    if prefix_index is not None:
        file_stem = f"{prefix_index:03d}_{safe_title}"
    else:
        file_stem = safe_title
        
    ext_clean = ext.lstrip('.')
    candidate = os.path.join(dir_path, f"{file_stem}.{ext_clean}")
    if not os.path.exists(candidate):
        return candidate, file_stem
        
    counter = 2
    while True:
        collision_stem = f"{file_stem} ({counter})"
        candidate = os.path.join(dir_path, f"{collision_stem}.{ext_clean}")
        if not os.path.exists(candidate):
            return candidate, collision_stem
        counter += 1


def _find_aweme_detail_in_json(data, target_video_id=None):
    """
    Tìm đối tượng aweme_detail hoặc video detail hợp lệ trong cấu trúc JSON lồng nhau.
    Nếu có target_video_id: Ưu tiên tuyệt đối tìm đúng video có ID trùng khớp, 
    tránh nhầm lẫn với danh sách video đề xuất (Swiper/Recommended Feed list).
    """
    if target_video_id:
        target_str = str(target_video_id).strip()
        # 1. Tìm chính xác video có ID trùng khớp trước
        def _find_exact(node):
            if isinstance(node, dict):
                cur_id = str(node.get('aweme_id') or node.get('id') or node.get('awemeId') or '')
                if cur_id and cur_id == target_str and 'video' in node and isinstance(node.get('video'), dict):
                    return node
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        found = _find_exact(v)
                        if found: return found
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        found = _find_exact(item)
                        if found: return found
            return None

        exact_match = _find_exact(data)
        if exact_match:
            return exact_match

    # 2. Fallback tìm video đầu tiên nếu không có target_video_id hoặc không khớp ID tuyệt đối
    if isinstance(data, dict):
        if ('aweme_id' in data or 'id' in data) and 'video' in data and isinstance(data.get('video'), dict):
            video = data['video']
            if video.get('play_addr') or video.get('bit_rate') or video.get('download_addr'):
                return data
                
        for key in ['aweme_detail', 'awemeDetail', 'videoDetail', 'itemStruct', 'itemInfo', 'item_list']:
            if key in data:
                res = _find_aweme_detail_in_json(data[key], target_video_id)
                if res:
                    return res

        for k, v in data.items():
            if isinstance(v, (dict, list)):
                res = _find_aweme_detail_in_json(v, target_video_id)
                if res:
                    return res
                    
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                res = _find_aweme_detail_in_json(item, target_video_id)
                if res:
                    return res

    return None

def _find_all_aweme_details_in_json(data):
    """
    Thu thập TẤT CẢ các đối tượng aweme_detail / video hợp lệ tìm thấy trong cây JSON lồng nhau
    (Bao gồm video chính, các tập trong playlist/mix, feed video đề xuất, v.v.)
    Khử trùng lặp theo aweme_id.
    """
    collected = []
    seen_ids = set()

    def _walk(node):
        if isinstance(node, dict):
            # Kiểm tra nếu là một aweme video hoàn chỉnh
            aweme_id = str(node.get('aweme_id') or node.get('id') or node.get('awemeId') or '')
            if aweme_id and 'video' in node and isinstance(node.get('video'), dict):
                v = node['video']
                if (v.get('play_addr') or v.get('bit_rate') or v.get('download_addr')) and not _is_ad_or_guide_url(str(node.get('desc', ''))):
                    if aweme_id not in seen_ids:
                        seen_ids.add(aweme_id)
                        collected.append(node)
            
            # Tiếp tục duyệt sâu vào các key
            for k, val in node.items():
                if isinstance(val, (dict, list)):
                    _walk(val)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk(item)

    _walk(data)
    return collected

def _extract_all_aweme_details_from_html(html_content):
    """
    Trích xuất TẤT CẢ aweme_detail từ toàn bộ các thẻ script SSR của Douyin
    """
    if not html_content:
        return []

    import urllib.parse
    all_details = []
    seen_ids = set()

    def _add_details(det_list):
        for d in det_list:
            aid = str(d.get('aweme_id') or d.get('id') or '')
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                all_details.append(d)

    # 1. __UNIVERSAL_DATA_FOR_REHYDRATION__
    m_univ = re.search(r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"\s+type="application/json">([^<]+)</script>', html_content)
    if m_univ:
        try:
            raw_json = json.loads(m_univ.group(1).strip())
            _add_details(_find_all_aweme_details_in_json(raw_json))
        except Exception:
            pass

    # 2. _ROUTER_DATA
    m_router = re.search(r'<script\s+id="_ROUTER_DATA"\s+type="application/json">([^<]+)</script>', html_content)
    if m_router:
        try:
            raw_json = json.loads(m_router.group(1).strip())
            _add_details(_find_all_aweme_details_in_json(raw_json))
        except Exception:
            pass

    # 3. RENDER_DATA
    m_render = re.search(r'<script\s+id="RENDER_DATA"\s+type="application/json">([^<]+)</script>', html_content)
    if m_render:
        try:
            raw_text = urllib.parse.unquote(m_render.group(1).strip())
            raw_json = json.loads(raw_text)
            _add_details(_find_all_aweme_details_in_json(raw_json))
        except Exception:
            pass

    # 4. Fallback: Bất kỳ thẻ script chứa JSON
    script_matches = re.findall(r'<script[^>]*type="application/json"[^>]*>([^<]+)</script>', html_content)
    for s_content in script_matches:
        try:
            raw_json = json.loads(s_content.strip())
            _add_details(_find_all_aweme_details_in_json(raw_json))
        except Exception:
            pass

    return all_details

def _is_ad_or_guide_url(url):
    """
    Kiểm tra xem URL có phải là video quảng cáo / Get APP / hướng dẫn không
    """
    if not url:
        return True
    u_lower = url.lower()
    ad_keywords = [
        'get_app', 'getapp', 'download_app', 'client_guide', 'guide_video',
        'login_guide', 'app_download', 'landing_video', 'qrcode', 'banner_video',
        'promo_video', 'tos-cn-v-0000', 'guide'
    ]
    return any(kw in u_lower for kw in ad_keywords)

# =========================================================================
# 2. MEDIA RESOLVER CHO DOUYIN (document.md Section 8)
# =========================================================================
_DOUYIN_RESOLVE_CACHE = {}

def _is_clean_douyin_url(u):
    if not u:
        return False
    u_lower = str(u).lower()
    return not ('playwm' in u_lower or 'watermark' in u_lower or '_wm.' in u_lower or '/wm/' in u_lower)

def resolve_douyin_variants(detail, aweme_id=None):
    """
    Trích xuất và xếp hạng toàn bộ các biến thể (variants) của video Douyin từ metadata:
    - Nguồn dữ liệu:
      1. video.bit_rate: danh sách biến thể bitrate, gear_name, quality_type, fps.
      2. video.download_addr: link tải do Douyin cấp.
      3. video.play_addr & video.play_addr_h264: stream xem trực tuyến.
    - Tiêu chuẩn đánh giá:
      * is_clean: True nếu nguồn không chứa watermark ('playwm', 'watermark', v.v.).
      * Độ phân giải (height x width).
      * Bitrate thực tế.
      * FPS (tốc độ khung hình).
    - Xếp hạng từ cao xuống thấp: (is_clean, height * width, bitrate, fps).
    """
    if not detail or not isinstance(detail, dict):
        return []

    video = detail.get('video') or {}
    candidates = []
    seen_urls = set()

    v_w = int(video.get('width') or 0)
    v_h = int(video.get('height') or 0)
    is_vertical = (v_h >= v_w) if (v_w > 0 and v_h > 0) else True

    # 1. Khai thác từ video.bit_rate (chứa profile bitrate và độ phân giải cao nhất)
    bit_rate_list = video.get('bit_rate', []) or []
    for br in bit_rate_list:
        if not isinstance(br, dict):
            continue
        gear = str(br.get('gear_name', '')).lower()
        q_type = int(br.get('quality_type', 0) or 0)
        w = int(br.get('width') or v_w or 0)
        h = int(br.get('height') or v_h or 0)
        br_val = int(br.get('bit_rate', 0) or 0)
        fps = float(br.get('fps') or 30.0)
        is_h265 = br.get('is_h265', 0)
        codec = 'hevc' if is_h265 else 'h264'

        # Xác định độ phân giải chuẩn từ gear hoặc quality_type nếu chưa đủ thông tin
        if '1080' in gear or q_type == 1080:
            target_q = 1080
            w, h = (1080, 1920) if is_vertical else (1920, 1080)
        elif '720' in gear or q_type == 720:
            target_q = 720
            w, h = (720, 1280) if is_vertical else (1280, 720)
        elif '540' in gear or q_type == 540:
            target_q = 540
            w, h = (540, 960) if is_vertical else (960, 540)
        elif '480' in gear or q_type == 480:
            target_q = 480
            w, h = (480, 854) if is_vertical else (854, 480)
        else:
            target_q = min(w, h) if (w > 0 and h > 0) else (q_type or 720)
            if not (w > 0 and h > 0):
                w, h = (720, 1280) if is_vertical else (1280, 720)

        play_addr_obj = br.get('play_addr') or {}
        raw_urls = play_addr_obj.get('url_list', []) or []
        valid_urls = [u for u in raw_urls if u and not _is_ad_or_guide_url(u)]
        if not valid_urls:
            continue

        clean_urls = [u for u in valid_urls if _is_clean_douyin_url(u)]
        if clean_urls:
            is_clean = True
            primary = clean_urls[0]
            backups = [u for u in clean_urls[1:]] + [u for u in valid_urls if u not in clean_urls]
        else:
            is_clean = False
            replaced_urls = [u.replace('playwm', 'play') for u in valid_urls]
            primary = replaced_urls[0]
            backups = replaced_urls[1:]

        q_num = min(w, h) if (w > 0 and h > 0) else target_q
        lbl = f"{q_num}p"
        if q_num >= 2160: lbl += " (4K Ultra HD)"
        elif q_num >= 1440: lbl += " (2K QHD)"
        elif q_num >= 1080: lbl += " (Full HD)"
        elif q_num >= 720: lbl += " (HD)"
        if is_clean: lbl += " [Bản sạch]"

        candidates.append({
            'url': primary,
            'backup_urls': backups,
            'width': w,
            'height': h,
            'fps': fps,
            'bitrate': br_val,
            'codec': codec,
            'quality_type': q_num,
            'quality': f"{q_num}p",
            'label': lbl,
            'is_clean': is_clean,
            'source': 'bit_rate'
        })
        for u in valid_urls:
            seen_urls.add(u)

    # 2. Khai thác từ download_addr (nguồn tải chính thức của Douyin)
    download_addr = video.get('download_addr') or {}
    dl_urls = [u for u in download_addr.get('url_list', []) if u and not _is_ad_or_guide_url(u)]
    if dl_urls:
        w = int(download_addr.get('width') or v_w or 0)
        h = int(download_addr.get('height') or v_h or 0)
        if not (w > 0 and h > 0):
            w, h = (1080, 1920) if is_vertical else (1920, 1080)
        q_num = min(w, h)
        is_clean = all(_is_clean_douyin_url(u) for u in dl_urls)
        candidates.append({
            'url': dl_urls[0],
            'backup_urls': dl_urls[1:],
            'width': w,
            'height': h,
            'fps': 30.0,
            'bitrate': 2000000,
            'codec': 'h264',
            'quality_type': q_num,
            'quality': f"{q_num}p",
            'label': f"{q_num}p (Tải trực tiếp Douyin)",
            'is_clean': is_clean,
            'source': 'download_addr'
        })
        for u in dl_urls:
            seen_urls.add(u)

    # 3. Khai thác từ play_addr và play_addr_h264
    for src_name, addr_obj in [('play_addr', video.get('play_addr')), ('play_addr_h264', video.get('play_addr_h264'))]:
        if not addr_obj or not isinstance(addr_obj, dict):
            continue
        urls = [u for u in addr_obj.get('url_list', []) if u and not _is_ad_or_guide_url(u)]
        if not urls:
            continue
        new_urls = [u for u in urls if u not in seen_urls]
        if not new_urls:
            continue
        w = int(addr_obj.get('width') or v_w or 0)
        h = int(addr_obj.get('height') or v_h or 0)
        if not (w > 0 and h > 0):
            w, h = (720, 1280) if is_vertical else (1280, 720)
        q_num = min(w, h)
        clean_urls = [u for u in new_urls if _is_clean_douyin_url(u)]
        if clean_urls:
            is_clean = True
            primary = clean_urls[0]
            backups = [u for u in clean_urls[1:]] + [u for u in new_urls if u not in clean_urls]
        else:
            is_clean = False
            replaced_urls = [u.replace('playwm', 'play') for u in new_urls]
            primary = replaced_urls[0]
            backups = replaced_urls[1:]
        candidates.append({
            'url': primary,
            'backup_urls': backups,
            'width': w,
            'height': h,
            'fps': 30.0,
            'bitrate': 1200000,
            'codec': 'h264',
            'quality_type': q_num,
            'quality': f"{q_num}p",
            'label': f"{q_num}p ({src_name})",
            'is_clean': is_clean,
            'source': src_name
        })
        for u in new_urls:
            seen_urls.add(u)

    # Sắp xếp ưu tiên: Bản sạch -> Độ phân giải cao nhất -> Bitrate cao nhất -> FPS
    candidates.sort(
        key=lambda v: (
            1 if v.get('is_clean') else 0,
            (v.get('height') or 0) * (v.get('width') or 0),
            v.get('bitrate') or 0,
            v.get('fps') or 0
        ),
        reverse=True
    )
    return candidates

def refresh_douyin_url(aweme_id):
    """
    Làm mới liên kết tải Douyin khi URL bị 403 hoặc 410 (hết hạn).
    Gọi API Douyin web aweme_detail để lấy danh sách URL mới nhất.
    """
    if not aweme_id or str(aweme_id).lower() in ['unknown_id', 'video', 'none', '']:
        return []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': f'https://www.douyin.com/video/{aweme_id}',
        'Accept': 'application/json, text/plain, */*'
    }
    api_urls = [
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id={aweme_id}",
        f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}"
    ]
    for api_url in api_urls:
        try:
            resp = requests.get(api_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                detail = data.get('aweme_detail')
                if detail:
                    variants = resolve_douyin_variants(detail, aweme_id=aweme_id)
                    if variants:
                        fresh_urls = []
                        for v in variants:
                            u = v.get('url')
                            if u and u not in fresh_urls:
                                fresh_urls.append(u)
                            for bu in v.get('backup_urls', []):
                                if bu and bu not in fresh_urls:
                                    fresh_urls.append(bu)
                        if fresh_urls:
                            return fresh_urls
        except Exception:
            pass

    try:
        ssr_info = resolve_douyin_media(f"https://www.douyin.com/video/{aweme_id}", use_cache=False)
        if ssr_info and ssr_info.get('video_urls'):
            return ssr_info['video_urls']
    except Exception:
        pass
    return []

def _format_single_douyin_detail(detail, video_id=None, page_title='', target_url=''):
    """
    Format 1 video detail Douyin thành cấu trúc chuẩn Section 8 sử dụng resolve_douyin_variants.
    """
    if not detail:
        return None
    aweme_id = str(detail.get('aweme_id') or detail.get('id') or video_id or 'unknown_id')
    title = detail.get('desc') or page_title or 'Video Douyin'
    title = re.sub(r' - 抖音$', '', title).strip()
    safe_title = sanitize_filename_windows(title)

    author = detail.get('author', {}).get('nickname', 'Tác giả Douyin')
    duration = round((detail.get('duration', 0) or 0) / 1000.0, 1)
    video = detail.get('video', {})
    cover = video.get('cover', {}).get('url_list', [''])[0] or video.get('origin_cover', {}).get('url_list', [''])[0]
    height = video.get('height', 1080)
    width = video.get('width', 1920)

    variants = resolve_douyin_variants(detail, aweme_id=aweme_id)

    resolutions = []
    format_url_map = {}
    url_list = []
    seen_heights = set()
    is_clean = False

    if variants:
        is_clean = variants[0].get('is_clean', False)
        for v in variants:
            h = v.get('height') or height
            fmt_id = str(h)
            v_urls = [v.get('url')] + [bu for bu in v.get('backup_urls', []) if bu != v.get('url')]
            v_urls = [u for u in v_urls if u]
            for u in v_urls:
                if u not in url_list:
                    url_list.append(u)

            if fmt_id not in seen_heights:
                seen_heights.add(fmt_id)
                resolutions.append({
                    'format_id': fmt_id,
                    'label': v.get('label') or f"{h}p",
                    'height': h,
                    'ext': 'mp4',
                    'is_clean': v.get('is_clean', False)
                })
                format_url_map[fmt_id] = v_urls

        best_v = variants[0]
        best_urls = [best_v.get('url')] + [bu for bu in best_v.get('backup_urls', []) if bu != best_v.get('url')]
        best_urls = [u for u in best_urls if u]
        clean_tag = " (Bản sạch không logo)" if is_clean else " (Bản có logo gốc)"
        resolutions.insert(0, {
            'format_id': 'best',
            'label': f"Chất lượng cao nhất ({best_v.get('label', f'{height}p')}){clean_tag}",
            'height': best_v.get('height', height),
            'ext': 'mp4',
            'is_clean': is_clean
        })
        format_url_map['best'] = best_urls
    else:
        # Fallback truyền thống nếu không trích xuất được variant
        for u in video.get('play_addr', {}).get('url_list', []):
            u_clean = u.replace('playwm', 'play')
            if u_clean and u_clean not in url_list and not _is_ad_or_guide_url(u_clean):
                url_list.append(u_clean)
        for u in video.get('download_addr', {}).get('url_list', []):
            if u and u not in url_list and not _is_ad_or_guide_url(u):
                url_list.append(u)
        lbl = f"{height}p"
        if height >= 1080: lbl += " (Full HD)"
        elif height >= 720: lbl += " (HD)"
        resolutions = [
            {'format_id': 'best', 'label': 'Chất lượng cao nhất (Gốc)', 'height': 9999, 'ext': 'mp4', 'is_clean': False},
            {'format_id': str(height), 'label': lbl, 'height': height, 'ext': 'mp4', 'is_clean': False}
        ]
        format_url_map['best'] = url_list
        format_url_map[str(height)] = url_list

    if not url_list:
        return None

    return {
        'success': True,
        'video_id': aweme_id,
        'title': safe_title or title,
        'uploader': author,
        'author': author,
        'duration': duration,
        'thumbnail': cover,
        'width': width,
        'height': height,
        'extractor': 'Douyin',
        'url': f"https://www.douyin.com/video/{aweme_id}" if aweme_id and aweme_id != 'unknown_id' else target_url,
        'video_urls': url_list,
        'resolutions': resolutions,
        'format_url_map': format_url_map,
        'variants': variants,
        'is_clean': is_clean,
        'raw_detail': detail
    }

def _format_douyin_result(detail, video_id, page_title, target_url, original_url, captured_video_srcs=None, all_details=None):
    """
    Chuẩn hóa cấu trúc dữ liệu kết quả Douyin, hỗ trợ trả về TẤT CẢ video tìm thấy trong link.
    """
    if captured_video_srcs is None:
        captured_video_srcs = []
        
    primary_info = _format_single_douyin_detail(detail, video_id, page_title, target_url)
    
    if not primary_info:
        if captured_video_srcs:
            aweme_id = video_id or 'unknown_id'
            title = page_title or 'Video Douyin'
            title = re.sub(r' - 抖音$', '', title).strip()
            safe_title = sanitize_filename(title)
            clean_srcs = [s for s in captured_video_srcs if not _is_ad_or_guide_url(s)]
            if clean_srcs:
                primary_info = {
                    'success': True,
                    'video_id': aweme_id,
                    'title': safe_title or title,
                    'uploader': 'Tác giả Douyin',
                    'author': 'Tác giả Douyin',
                    'duration': 0,
                    'thumbnail': '',
                    'width': 1920,
                    'height': 1080,
                    'extractor': 'Douyin',
                    'url': target_url,
                    'video_urls': clean_srcs,
                    'resolutions': [{'format_id': 'best', 'label': 'Chất lượng cao nhất (Gốc)', 'height': 9999, 'ext': 'mp4'}],
                    'format_url_map': {'best': clean_srcs},
                    'raw_detail': {}
                }
        
        if not primary_info:
            return {'error': 'Không tìm thấy luồng tải video khả dụng cho video Douyin này (đã loại trừ video quảng cáo).'}

    # Thu thập tất cả các video được quét (chống circular reference)
    all_formatted_videos = []
    seen_ids = set()
    
    if primary_info and primary_info.get('video_id'):
        seen_ids.add(primary_info['video_id'])
        # Tạo dict copy độc lập, tránh lồng ghép tham chiếu vòng
        all_formatted_videos.append(dict(primary_info))
        
    if all_details and not video_id:
        for d in all_details:
            d_id = str(d.get('aweme_id') or d.get('id') or '')
            if d_id and d_id not in seen_ids:
                f_item = _format_single_douyin_detail(d, d_id, page_title, target_url)
                if f_item and f_item.get('success'):
                    seen_ids.add(d_id)
                    all_formatted_videos.append(f_item)
                    
    primary_info['is_multiple'] = len(all_formatted_videos) > 1
    primary_info['video_count'] = len(all_formatted_videos)
    primary_info['videos'] = all_formatted_videos
    
    # Lưu cache
    now = time.time()
    _DOUYIN_RESOLVE_CACHE[target_url] = {'timestamp': now, 'data': primary_info}
    _DOUYIN_RESOLVE_CACHE[original_url] = {'timestamp': now, 'data': primary_info}
    aweme_id = primary_info.get('video_id')
    if aweme_id:
        _DOUYIN_RESOLVE_CACHE[str(aweme_id)] = {'timestamp': now, 'data': primary_info}
        
    return primary_info

def _resolve_douyin_http_direct(url, video_id=None):
    """
    Giải mã Douyin cực nhanh qua HTTP Direct API & SSR Parser không cần mở trình duyệt Playwright.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7',
            'Referer': 'https://www.douyin.com/'
        }
        target_url = url
        # 1. Giải mã link rút gọn nếu có
        if 'v.douyin.com' in url or not video_id:
            try:
                resp_head = requests.get(url, headers=headers, allow_redirects=True, timeout=3.0)
                target_url = resp_head.url
                canonical_url, vid = parse_douyin_url(target_url)
                if vid:
                    video_id = vid
            except Exception:
                pass

        if not video_id:
            canonical_url, vid = parse_douyin_url(target_url)
            video_id = vid

        # 2. Thử gọi Mobile API nếu có video_id
        if video_id:
            api_url = f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=1128&version_name=23.5.0&device_platform=android&os_version=2333"
            try:
                r_api = requests.get(api_url, headers=headers, timeout=2.5)
                if r_api.status_code == 200:
                    api_json = r_api.json()
                    det = _find_aweme_detail_in_json(api_json, target_video_id=video_id)
                    if det:
                        return _format_douyin_result(det, video_id, '', target_url, url, [])
            except Exception:
                pass

        # 3. Thử tải HTML của target_url và bóc tách SSR JSON
        try:
            r_page = requests.get(target_url, headers=headers, timeout=3.0)
            if r_page.status_code == 200:
                all_ssr_details = _extract_all_aweme_details_from_html(r_page.text)
                if all_ssr_details:
                    primary_detail = None
                    if video_id:
                        for d in all_ssr_details:
                            if str(d.get('aweme_id') or d.get('id') or '') == str(video_id):
                                primary_detail = d
                                break
                    elif all_ssr_details:
                        primary_detail = all_ssr_details[0]

                    if primary_detail:
                        title_m = re.search(r'<title>([^<]+)</title>', r_page.text)
                        p_title = title_m.group(1) if title_m else ''
                        return _format_douyin_result(primary_detail, video_id, p_title, target_url, url, [], all_details=all_ssr_details)
        except Exception:
            pass

    except Exception:
        pass
    return None

def _resolve_via_cloud_api(url):
    """
    Giải mã Douyin & TikTok qua Cloud Direct API (TikWM) - 100% không phụ thuộc Chromium/Playwright.
    """
    try:
        api_url = "https://www.tikwm.com/api/"
        resp = requests.post(api_url, data={'url': url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}, timeout=3.5)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get('code') == 0 and res_data.get('data'):
                d = res_data['data']
                vid = str(d.get('id') or '')
                title = sanitize_filename(d.get('title') or 'Video Douyin')
                author = d.get('author', {}).get('nickname') or 'Tác giả'
                duration = d.get('duration') or 0
                cover = d.get('cover') or ''
                
                vid_urls = []
                if d.get('hdplay'):
                    hd_u = d['hdplay']
                    if hd_u.startswith('/'): hd_u = f"https://www.tikwm.com{hd_u}"
                    vid_urls.append(hd_u)
                if d.get('play'):
                    p_u = d['play']
                    if p_u.startswith('/'): p_u = f"https://www.tikwm.com{p_u}"
                    if p_u not in vid_urls: vid_urls.append(p_u)
                if d.get('wmplay'):
                    wm_u = d['wmplay']
                    if wm_u.startswith('/'): wm_u = f"https://www.tikwm.com{wm_u}"
                    if wm_u not in vid_urls: vid_urls.append(wm_u)
                    
                if vid_urls:
                    single_v = {
                        'success': True,
                        'video_id': vid or 'unknown_id',
                        'title': title,
                        'uploader': author,
                        'author': author,
                        'duration': duration,
                        'thumbnail': cover,
                        'width': 1080,
                        'height': 1920,
                        'extractor': 'Douyin/TikTok Cloud API',
                        'url': url,
                        'video_urls': vid_urls,
                        'resolutions': [
                            {'format_id': 'best', 'label': 'Chất lượng cao nhất (Gốc)', 'height': 1080, 'ext': 'mp4'}
                        ],
                        'format_url_map': {'best': vid_urls}
                    }
                    single_v['is_multiple'] = False
                    single_v['video_count'] = 1
                    single_v['videos'] = [dict(single_v)]
                    return single_v
    except Exception:
        pass
    return None

def resolve_douyin_media(url, use_cache=True):
    """
    Media Resolver trích xuất metadata Douyin chuẩn hóa (Section 8).
    Thứ tự ưu tiên: 1. Cache -> 2. HTTP Direct API/SSR -> 3. Cloud API -> 4. yt-dlp -> 5. Playwright Browser.
    """
    canonical_url, video_id = parse_douyin_url(url)
    target_url = canonical_url or url
    
    # 0. Giải mã link rút gọn v.douyin.com ngay từ đầu để lấy chính xác Video ID
    if 'v.douyin.com' in url or not video_id:
        try:
            resp_head = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}, allow_redirects=True, timeout=5.0, stream=True)
            if resp_head.url:
                target_url = resp_head.url
                c_url, vid = parse_douyin_url(target_url)
                if vid:
                    video_id = vid
                    target_url = c_url
        except Exception:
            pass

    # 1. Kiểm tra Cache trước (chỉ dùng nếu cache hợp lệ và có thông tin thật)
    if use_cache:
        now = time.time()
        for k in [target_url, url, video_id]:
            if k and k in _DOUYIN_RESOLVE_CACHE:
                entry = _DOUYIN_RESOLVE_CACHE[k]
                c_data = entry.get('data') or {}
                if c_data.get('title') and c_data.get('title') != 'Video Douyin' and (c_data.get('duration', 0) > 0 or c_data.get('video_urls')):
                    if now - entry.get('timestamp', 0) < 1800:
                        return c_data

    # 2. Thử giải mã trực tiếp qua HTTP Direct API / SSR (Nhanh gấp 10x, 100% không phụ thuộc Chromium)
    http_result = _resolve_douyin_http_direct(target_url, video_id)
    if http_result and http_result.get('success'):
        return http_result

    # 3. Thử giải mã qua Cloud API (Timeout nhanh 3s)
    try:
        cloud_result = _resolve_via_cloud_api(target_url)
        if cloud_result and cloud_result.get('success'):
            _DOUYIN_RESOLVE_CACHE[target_url] = {'timestamp': time.time(), 'data': cloud_result}
            return cloud_result
    except Exception:
        pass

    # 5. Fallback cuối cùng: Playwright Headless Browser (với try-catch an toàn nếu thiếu binary)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'error': 'Không thể tải video từ link này. Video có thể đang ở chế độ riêng tư hoặc link đã hết hạn.'}

    captured_data = {}
    captured_video_srcs = []
    captured_all_details = []
    seen_captured_ids = set()

    def _collect_details(det_list):
        for d in det_list:
            aid = str(d.get('aweme_id') or d.get('id') or '')
            if aid and aid not in seen_captured_ids:
                seen_captured_ids.add(aid)
                captured_all_details.append(d)
    
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
                )
            except Exception:
                return {'error': 'Không thể bóc tách luồng video từ link này. Video có thể đang bị chặn khu vực hoặc link đã hết hạn.'}

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                locale='zh-CN',
                viewport={'width': 1280, 'height': 800}
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.navigator.chrome = { runtime: {} };
            """)
            
            def handle_response(response):
                try:
                    r_url = response.url
                    if any(endpoint in r_url for endpoint in [
                        'aweme/v1/web/aweme/detail',
                        'aweme/v1/web/aweme/iteminfo',
                        'aweme/v1/web/item/detail',
                        'aweme/v1/web/tab/feed',
                        'aweme/v1/web/aweme/post',
                        'aweme/v1/web/slider/video'
                    ]):
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                if data.get('aweme_detail'):
                                    aw_d = data['aweme_detail']
                                    aw_id = str(aw_d.get('aweme_id') or '')
                                    if not video_id or aw_id == str(video_id):
                                        captured_data['detail'] = aw_d
                                    _collect_details([aw_d])
                                elif data.get('aweme_list'):
                                    _collect_details(data['aweme_list'])
                                    for itm in data['aweme_list']:
                                        if str(itm.get('aweme_id') or '') == str(video_id):
                                            captured_data['detail'] = itm
                                            break
                            found_items = _find_all_aweme_details_in_json(data)
                            if found_items:
                                _collect_details(found_items)
                                if not captured_data.get('detail'):
                                    det = _find_aweme_detail_in_json(data, target_video_id=video_id)
                                    if det:
                                        captured_data['detail'] = det
                                    elif not video_id:
                                        captured_data['detail'] = found_items[0]
                        except Exception:
                            pass
                    elif ('.mp4' in r_url or 'video/tos' in r_url or 'douyinvod' in r_url or 'aweme/v1/play' in r_url) and response.status in [200, 206]:
                        if not _is_ad_or_guide_url(r_url):
                            if 'video' in response.headers.get('content-type', ''):
                                if r_url not in captured_video_srcs:
                                    captured_video_srcs.append(r_url)
                except Exception:
                    pass

            page.on('response', handle_response)
                    
            # 1. Khởi tạo cookie Douyin
            try:
                page.goto("https://www.douyin.com/", timeout=10000)
                time.sleep(1.2)
            except Exception:
                pass

            # 2. Mở target URL
            try:
                page.goto(target_url, timeout=20000)
            except Exception:
                pass
            
            for _ in range(35):
                if 'detail' in captured_data:
                    break
                time.sleep(0.2)
                
            try:
                html_content = page.content()
                ssr_all = _extract_all_aweme_details_from_html(html_content)
                if ssr_all:
                    _collect_details(ssr_all)
                    if not captured_data.get('detail'):
                        det = _find_aweme_detail_in_json({'items': ssr_all}, target_video_id=video_id)
                        if det:
                            captured_data['detail'] = det
                        elif not video_id:
                            captured_data['detail'] = ssr_all[0]
            except Exception:
                pass

            final_url = page.url
            page_title = page.title() or ''
            if not video_id:
                vid_m = re.search(r'/(?:video|note)/(\d+)', final_url) or re.search(r'modal_id=(\d+)', final_url)
                if vid_m:
                    video_id = vid_m.group(1)

            browser.close()
            
        if 'detail' not in captured_data and not captured_video_srcs:
            return {'error': 'Không thể trích xuất thông tin video từ Douyin. Video có thể bị ẩn, riêng tư hoặc link đã hết hạn.'}
            
        return _format_douyin_result(
            captured_data.get('detail'),
            video_id,
            page_title,
            target_url,
            url,
            captured_video_srcs,
            all_details=captured_all_details
        )
    except Exception as e:
        return {'error': f'Lỗi phân tích Douyin: {str(e)}'}


# =========================================================================
# 3. STREAM DOWNLOAD MANAGER VỚI RANGE RESUME & RETRY (Section 9 & 27)
# =========================================================================


class ResumableRangeDownloader:
    """
    Unified Multi-Connection Range Downloader (Chuẩn IDM 4-6 luồng) bền bỉ cho Douyin và video dài:
    1. Bắt buộc kiểm tra HTTP 206 và header Content-Range cho từng part.
    2. Nếu server trả về HTTP 200 cho Range request, hủy ngay đa luồng và chuyển sang tải đơn luồng (chống nhân đôi/hỏng file).
    3. Ghi manifest JSON (.download_manifest.json) lưu ETag, dung lượng và trạng thái từng part để resume chính xác.
    4. Tự động refresh URL khi gặp lỗi HTTP 403 / 410 bằng aweme_id.
    5. Exponential backoff với jitter ngẫu nhiên khi retry lỗi mạng.
    6. Hỗ trợ giới hạn tổng kết nối qua connection_semaphore.
    7. Stream dữ liệu theo chunk (128KB - 256KB) trực tiếp ra đĩa, không nạp toàn bộ file vào RAM.
    8. Xác thực toàn vẹn container bằng ffprobe sau khi tải xong.
    """
    def __init__(self, urls=None, output_path=None, num_threads=4, num_connections=None,
                 connection_semaphore=None, connection_pool=None, progress_callback=None,
                 cancel_event=None, max_retries=4, aweme_id=None, backup_urls=None,
                 refresh_url_cb=None, is_audio=False, url=None, chunk_size_threshold=None, **kwargs):
        target_urls = urls if urls is not None else url
        if isinstance(target_urls, list):
            self.urls = [u for u in target_urls if u]
        elif target_urls:
            self.urls = [target_urls]
        else:
            self.urls = []

        if backup_urls and isinstance(backup_urls, list):
            for bu in backup_urls:
                if bu and bu not in self.urls:
                    self.urls.append(bu)

        self.output_path = os.path.abspath(output_path)
        self.part_path = self.output_path + '.part'
        self.manifest_path = self.output_path + '.download_manifest.json'
        threads = num_connections if num_connections is not None else num_threads
        self.num_threads = max(1, min(int(threads or 4), 6))

        sem = connection_semaphore
        if sem is None and connection_pool is not None:
            sem = getattr(connection_pool, 'semaphore', connection_pool)
        self.semaphore = sem

        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()
        self.max_retries = max(1, int(max_retries or 4))
        self.aweme_id = aweme_id
        self.refresh_url_cb = refresh_url_cb or refresh_douyin_url
        self.is_audio = is_audio
        self.chunk_size_threshold = chunk_size_threshold if chunk_size_threshold is not None else 2 * 1024 * 1024
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Referer': 'https://www.douyin.com/',
            'Accept': '*/*'
        }
        self.session = requests.Session()

    def download(self):
        """Hàm giao diện tải trả về đường dẫn file đã lưu"""
        res = self.execute()
        if isinstance(res, tuple):
            return res[0]
        return res

    def _notify_progress(self, downloaded_bytes, total_bytes, start_time, last_cb_state, force=False):
        now = time.time()
        if not self.progress_callback:
            return
        last_time = last_cb_state.get('time', 0)
        if not force and (now - last_time < 0.15) and (downloaded_bytes < total_bytes):
            return
        last_cb_state['time'] = now

        pct = round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
        elapsed = now - start_time
        speed = (downloaded_bytes / elapsed) if elapsed > 0 else 0
        speed_str = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 0 else "-- MB/s"
        rem = max(0, total_bytes - downloaded_bytes)
        eta = int(rem / speed) if speed > 0 else 0

        self.progress_callback({
            'status': 'downloading',
            'downloaded_bytes': downloaded_bytes,
            'total_bytes': total_bytes,
            'percent': pct,
            'speed': speed_str,
            'eta': f"{eta}s" if eta else "--"
        })

    def probe_stream(self):
        """
        Thăm dò URL khả dụng, kích thước file và khả năng hỗ trợ HTTP Range (206).
        """
        selected_url = None
        total_file_size = 0
        accept_ranges = False
        etag = None

        candidate_urls = list(self.urls)
        for attempt in range(2):
            for v_url in candidate_urls:
                if self.cancel_event.is_set():
                    return None, 0, False, None
                # Thử HEAD request
                try:
                    r_head = self.session.head(v_url, headers=self.headers, allow_redirects=True, timeout=8)
                    if r_head.status_code in [200, 206]:
                        selected_url = v_url
                        total_file_size = int(r_head.headers.get('content-length', 0))
                        etag = r_head.headers.get('etag', '').strip('"')
                        accept_ranges = ('bytes' in r_head.headers.get('accept-ranges', '').lower()) or (r_head.status_code == 206)
                        break
                    elif r_head.status_code in [403, 410] and self.aweme_id and self.refresh_url_cb:
                        fresh = self.refresh_url_cb(self.aweme_id)
                        if fresh:
                            for fu in fresh:
                                if fu not in candidate_urls:
                                    candidate_urls.append(fu)
                except Exception:
                    pass

                # Nếu HEAD không ra hoặc bị chặn, probe GET 2 bytes (Range 0-1)
                try:
                    test_h = self.headers.copy()
                    test_h['Range'] = 'bytes=0-1'
                    with self.session.get(v_url, headers=test_h, stream=True, timeout=8) as r_test:
                        if r_test.status_code == 206:
                            selected_url = v_url
                            accept_ranges = True
                            etag = r_test.headers.get('etag', '').strip('"')
                            cr = r_test.headers.get('content-range', '')
                            if '/' in cr:
                                total_file_size = int(cr.split('/')[-1])
                            break
                        elif r_test.status_code == 200:
                            selected_url = v_url
                            accept_ranges = False
                            total_file_size = int(r_test.headers.get('content-length', 0))
                            break
                except Exception:
                    pass

            if selected_url:
                break
            # Nếu chưa tìm được URL sống và có aweme_id, refresh và thử lại vòng 2
            if self.aweme_id and self.refresh_url_cb and attempt == 0:
                fresh = self.refresh_url_cb(self.aweme_id)
                if fresh:
                    candidate_urls = fresh

        if not selected_url and candidate_urls:
            selected_url = candidate_urls[0]

        return selected_url, total_file_size, accept_ranges, etag

    def _load_or_create_manifest(self, total_bytes, etag, selected_url, num_parts):
        manifest = None
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if (data.get('total_bytes') == total_bytes and
                    len(data.get('parts', [])) == num_parts):
                    manifest = data
            except Exception:
                manifest = None

        if not manifest:
            chunk_size = total_bytes // num_parts
            parts = []
            for i in range(num_parts):
                start = i * chunk_size
                end = total_bytes - 1 if i == num_parts - 1 else (start + chunk_size - 1)
                p_file = f"{self.part_path}.part{i}"
                # Nếu file part cũ đã tồn tại trên đĩa, đồng bộ số byte
                existing_bytes = os.path.getsize(p_file) if os.path.exists(p_file) else 0
                expected_len = end - start + 1
                completed = (existing_bytes >= expected_len)
                parts.append({
                    'index': i,
                    'start': start,
                    'end': end,
                    'downloaded': min(existing_bytes, expected_len),
                    'completed': completed,
                    'file': p_file
                })
            manifest = {
                'version': 1,
                'url': selected_url,
                'aweme_id': self.aweme_id,
                'total_bytes': total_bytes,
                'etag': etag,
                'num_parts': num_parts,
                'parts': parts
            }
            self._save_manifest(manifest)
        else:
            # Đồng bộ lại kích thước thực tế trên đĩa
            for p in manifest.get('parts', []):
                p_file = p.get('file')
                if p_file and os.path.exists(p_file):
                    cur_size = os.path.getsize(p_file)
                    expected_len = p['end'] - p['start'] + 1
                    p['downloaded'] = min(cur_size, expected_len)
                    p['completed'] = (cur_size >= expected_len)
                else:
                    p['downloaded'] = 0
                    p['completed'] = False

        return manifest

    def _save_manifest(self, manifest):
        try:
            tmp_path = self.manifest_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            if os.path.exists(tmp_path):
                os.replace(tmp_path, self.manifest_path)
        except Exception:
            pass

    def _download_part(self, part_idx, manifest, shared_state, lock, start_time, last_cb_state):
        part = manifest['parts'][part_idx]
        if part.get('completed'):
            return True

        p_file = part['file']
        expected_len = part['end'] - part['start'] + 1
        cur_downloaded = os.path.getsize(p_file) if os.path.exists(p_file) else 0

        if cur_downloaded >= expected_len:
            part['completed'] = True
            part['downloaded'] = expected_len
            return True

        req_start = part['start'] + cur_downloaded
        req_end = part['end']

        for attempt in range(self.max_retries):
            if self.cancel_event.is_set():
                return False
            if shared_state.get('fallback_to_single'):
                return False

            # Điều tiết kết nối qua semaphore nếu có
            sem = self.semaphore
            if sem:
                sem.acquire()

            try:
                cur_url = shared_state.get('current_url') or manifest.get('url')
                req_h = self.headers.copy()
                req_h['Range'] = f"bytes={req_start}-{req_end}"

                resp = self.session.get(cur_url, headers=req_h, stream=True, timeout=25)

                # KIỂM TRA QUAN TRỌNG: Server PHẢI trả về 206 Partial Content
                if resp.status_code == 200:
                    resp.close()
                    with lock:
                        shared_state['fallback_to_single'] = True
                    return False

                if resp.status_code in [403, 410]:
                    resp.close()
                    if self.aweme_id and self.refresh_url_cb:
                        fresh = self.refresh_url_cb(self.aweme_id)
                        if fresh:
                            with lock:
                                shared_state['current_url'] = fresh[0]
                    delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.4)
                    time.sleep(delay)
                    continue

                if resp.status_code != 206:
                    resp.close()
                    delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.4)
                    time.sleep(delay)
                    continue

                # Xác thực Content-Range header
                cr = resp.headers.get('content-range', '')
                if cr and not cr.startswith(f"bytes {req_start}-"):
                    # Range không khớp với yêu cầu
                    resp.close()
                    with lock:
                        shared_state['fallback_to_single'] = True
                    return False

                open_mode = 'ab' if cur_downloaded > 0 else 'wb'
                with open(p_file, open_mode) as pf:
                    for chunk in resp.iter_content(chunk_size=128 * 1024):
                        if self.cancel_event.is_set() or shared_state.get('fallback_to_single'):
                            resp.close()
                            return False
                        if chunk:
                            pf.write(chunk)
                            cur_downloaded += len(chunk)
                            part['downloaded'] = cur_downloaded
                            with lock:
                                shared_state['total_downloaded'] += len(chunk)
                                tot_dl = shared_state['total_downloaded']
                            self._notify_progress(tot_dl, manifest['total_bytes'], start_time, last_cb_state)

                if cur_downloaded >= expected_len:
                    part['completed'] = True
                    part['downloaded'] = expected_len
                    with lock:
                        self._save_manifest(manifest)
                    return True
                else:
                    req_start = part['start'] + cur_downloaded

            except Exception:
                delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.5)
                time.sleep(delay)
            finally:
                if sem:
                    try: sem.release()
                    except Exception: pass

        return False

    def _execute_multipart(self, selected_url, total_file_size, etag):
        manifest = self._load_or_create_manifest(total_file_size, etag, selected_url, self.num_threads)
        start_time = time.time()
        last_cb_state = {'time': start_time}
        lock = threading.Lock()

        # Tính tổng số byte đã có từ các part hoàn thành trước đó
        initial_downloaded = sum(p.get('downloaded', 0) for p in manifest.get('parts', []))
        shared_state = {
            'fallback_to_single': False,
            'current_url': selected_url,
            'total_downloaded': initial_downloaded
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(
                    self._download_part,
                    i, manifest, shared_state, lock, start_time, last_cb_state
                )
                for i in range(self.num_threads)
            ]
            concurrent.futures.wait(futures)

        if shared_state.get('fallback_to_single') or self.cancel_event.is_set():
            # Xóa các part tải dở và manifest khi fallback
            for p in manifest.get('parts', []):
                pf = p.get('file')
                if pf and os.path.exists(pf):
                    try: os.remove(pf)
                    except Exception: pass
            if os.path.exists(self.manifest_path):
                try: os.remove(self.manifest_path)
                except Exception: pass
            return False

        # Kiểm tra tính toàn vẹn của tất cả các part
        for p in manifest.get('parts', []):
            pf = p.get('file')
            expected_len = p['end'] - p['start'] + 1
            if not pf or not os.path.exists(pf) or os.path.getsize(pf) != expected_len:
                return False

        # Ghép nối các part thành file tạm
        assembling_file = self.output_path + '.assembling'
        with open(assembling_file, 'wb') as out_f:
            for p in manifest['parts']:
                with open(p['file'], 'rb') as in_f:
                    while True:
                        buf = in_f.read(1024 * 1024 * 2)
                        if not buf:
                            break
                        out_f.write(buf)

        # Kiểm tra dung lượng sau ghép nối
        if os.path.getsize(assembling_file) != total_file_size:
            if os.path.exists(assembling_file):
                try: os.remove(assembling_file)
                except Exception: pass
            return False

        # Dọn dẹp part files và manifest
        for p in manifest['parts']:
            if os.path.exists(p['file']):
                try: os.remove(p['file'])
                except Exception: pass
        if os.path.exists(self.manifest_path):
            try: os.remove(self.manifest_path)
            except Exception: pass

        if os.path.exists(self.output_path):
            try: os.remove(self.output_path)
            except Exception: pass
        os.rename(assembling_file, self.output_path)
        self._notify_progress(total_file_size, total_file_size, start_time, last_cb_state, force=True)
        return True

    def _execute_single_part(self, selected_url, total_file_size):
        """
        Tải đơn luồng an toàn với stream trực tiếp ra đĩa và HTTP Range Resume.
        Dùng khi server trả về HTTP 200 hoặc không hỗ trợ Range đa kết nối.
        """
        downloaded_total = 0
        if os.path.exists(self.part_path):
            downloaded_total = os.path.getsize(self.part_path)

        cur_url = selected_url
        start_time = time.time()
        last_cb_state = {'time': start_time}
        success = False

        for attempt in range(self.max_retries):
            if self.cancel_event.is_set():
                return False

            sem = self.semaphore
            if sem: sem.acquire()

            try:
                req_h = self.headers.copy()
                if downloaded_total > 0:
                    req_h['Range'] = f"bytes={downloaded_total}-"

                with self.session.get(cur_url, headers=req_h, stream=True, timeout=25) as r:
                    if r.status_code == 206:
                        cr = r.headers.get('content-range', '')
                        m = re.search(r'/(\d+)', cr)
                        if m:
                            total_file_size = int(m.group(1))
                        mode = 'ab'
                    elif r.status_code == 200:
                        total_file_size = int(r.headers.get('content-length', 0))
                        downloaded_total = 0
                        mode = 'wb'
                    elif r.status_code in [403, 410]:
                        if self.aweme_id and self.refresh_url_cb:
                            fresh = self.refresh_url_cb(self.aweme_id)
                            if fresh:
                                cur_url = fresh[0]
                        delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.4)
                        time.sleep(delay)
                        continue
                    else:
                        delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.4)
                        time.sleep(delay)
                        continue

                    with open(self.part_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=128 * 1024):
                            if self.cancel_event.is_set():
                                return False
                            if chunk:
                                f.write(chunk)
                                downloaded_total += len(chunk)
                                self._notify_progress(downloaded_total, total_file_size, start_time, last_cb_state)

                    if (total_file_size > 0 and downloaded_total >= total_file_size) or (downloaded_total > 1024 * 100 and total_file_size == 0):
                        success = True
                        break
            except Exception:
                delay = min(8, (2 ** attempt)) + random.uniform(0.1, 0.5)
                time.sleep(delay)
            finally:
                if sem:
                    try: sem.release()
                    except Exception: pass

            if success:
                break

        if not success or not os.path.exists(self.part_path):
            return False

        if os.path.exists(self.output_path):
            try: os.remove(self.output_path)
            except Exception: pass
        os.rename(self.part_path, self.output_path)
        self._notify_progress(total_file_size or downloaded_total, total_file_size or downloaded_total, start_time, last_cb_state, force=True)
        return True

    def execute(self):
        """
        Khởi chạy tiến trình tải với đầy đủ cơ chế đa luồng -> fallback đơn luồng -> hậu kiểm ffprobe.
        """
        selected_url, total_file_size, accept_ranges, etag = self.probe_stream()
        if not selected_url:
            raise Exception('Không tìm thấy URL tải video khả dụng hoặc link Douyin đã hết hạn.')

        success = False
        # Nếu hỗ trợ Range và file vượt ngưỡng, ưu tiên tải đa luồng
        if accept_ranges and total_file_size > self.chunk_size_threshold:
            success = self._execute_multipart(selected_url, total_file_size, etag)

        # Fallback về đơn luồng nếu đa luồng không áp dụng được hoặc bị lỗi giữa chừng
        if not success:
            success = self._execute_single_part(selected_url, total_file_size)

        if not success or not os.path.exists(self.output_path):
            raise Exception('Không thể tải video Douyin sau nhiều lần thử lại.')

        # Xử lý trích xuất Audio MP3 nếu được yêu cầu
        if self.is_audio:
            if self.progress_callback:
                self.progress_callback({
                    'status': 'processing',
                    'message': 'Đang chuyển đổi âm thanh sang MP3 bằng FFmpeg...'
                })
            temp_vid = self.output_path + '.temp.mp4'
            if os.path.exists(temp_vid):
                try: os.remove(temp_vid)
                except Exception: pass
            os.rename(self.output_path, temp_vid)

            ffmpeg_dir = get_ffmpeg_dir()
            ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else 'ffmpeg'
            cmd = [ffmpeg_exe, '-y', '-i', temp_vid, '-vn', '-ab', '192k', self.output_path]
            kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs() if hasattr(ffmpeg_installer, 'get_stealth_subprocess_kwargs') else {}
            subprocess.run(cmd, capture_output=True, check=True, **kwargs)
            if os.path.exists(temp_vid):
                try: os.remove(temp_vid)
                except Exception: pass

        # Xác thực container qua ffprobe
        specs = probe_video_specs(self.output_path)
        return self.output_path, specs


def download_stream_with_resume(video_urls, output_path, is_audio=False, progress_callback=None,
                                max_retries=4, num_threads=4, connection_semaphore=None,
                                cancel_event=None, aweme_id=None, refresh_url_cb=None):
    """
    Hàm giao diện tải stream thống nhất chuẩn Section 9 & 27.
    Ủy quyền trực tiếp cho ResumableRangeDownloader.
    """
    downloader = ResumableRangeDownloader(
        urls=video_urls,
        output_path=output_path,
        num_threads=num_threads,
        connection_semaphore=connection_semaphore,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
        max_retries=max_retries,
        aweme_id=aweme_id,
        refresh_url_cb=refresh_url_cb,
        is_audio=is_audio
    )
    final_path, _ = downloader.execute()
    return final_path


# =========================================================================
# 3.1 EPISODE STITCHING / CONCAT ENGINE (Section 5)
# =========================================================================
def merge_collection_episodes(file_list, output_path, merge_mode="auto", progress_callback=None):
    """
    Ghép nhiều tập video thành 1 video dài hoàn chỉnh (Section 5):
    - Kiểm tra tính tương thích qua ffprobe: codec, resolution, fps.
    - Nếu tương thích và merge_mode == "auto" | "copy":
      Sử dụng FFmpeg Concat Demuxer (-c copy) ghép siêu tốc không nén lại.
    - Nếu không tương thích hoặc merge_mode == "reencode":
      Sử dụng filter_complex concat chuẩn hóa kích thước, encode qua NVENC hoặc libx264.
    - Giữ nguyên các tệp tập gốc ban đầu.
    """
    if not file_list or not isinstance(file_list, list):
        raise ValueError("Danh sách file cần ghép rỗng.")

    valid_files = [os.path.abspath(f) for f in file_list if f and os.path.exists(f) and os.path.getsize(f) > 1000]
    if not valid_files:
        raise ValueError("Không tìm thấy file video hợp lệ nào để ghép.")

    if len(valid_files) == 1:
        # Nếu chỉ có 1 file, copy trực tiếp sang output_path nếu khác vị trí
        if os.path.abspath(valid_files[0]) != os.path.abspath(output_path):
            import shutil
            shutil.copy2(valid_files[0], output_path)
        return output_path

    if progress_callback:
        progress_callback({'status': 'probing', 'message': f'Đang kiểm tra thông số {len(valid_files)} video...'})

    ffmpeg_dir = get_ffmpeg_dir()
    ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else 'ffmpeg'
    kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs() if hasattr(ffmpeg_installer, 'get_stealth_subprocess_kwargs') else {}

    # 1. Thu thập thông số kỹ thuật từng file
    specs = []
    for f in valid_files:
        sp = probe_video_specs(f)
        if not sp or not sp.get('is_video'):
            raise Exception(f"File không phải video hợp lệ: {os.path.basename(f)}")
        specs.append(sp)

    first_spec = specs[0]
    w0 = first_spec.get('width', 0)
    h0 = first_spec.get('height', 0)
    vcodec0 = first_spec.get('vcodec', '')
    acodec0 = first_spec.get('acodec', '')
    fps0 = first_spec.get('fps', 0.0)

    # Đánh giá tính tương thích để chọn stream copy hay re-encode
    is_compatible = True
    for sp in specs[1:]:
        same_dim = (sp.get('width') == w0 and sp.get('height') == h0)
        same_vcodec = (sp.get('vcodec') == vcodec0)
        same_acodec = (sp.get('acodec') == acodec0)
        fps_diff = abs((sp.get('fps') or 0.0) - fps0)
        if not (same_dim and same_vcodec and same_acodec and fps_diff < 1.0):
            is_compatible = False
            break

    use_copy = is_compatible and (merge_mode in ["auto", "copy"])

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_concat_list = os.path.join(os.path.dirname(output_path), f"concat_list_{int(time.time())}.txt")

    if use_copy:
        # --- CHIẾN LƯỢC 1: FFmpeg Concat Demuxer (Stream Copy siêu tốc) ---
        if progress_callback:
            progress_callback({'status': 'merging', 'mode': 'copy', 'message': f'Đang ghép siêu tốc {len(valid_files)} tập (Stream Copy)...'})

        try:
            with open(temp_concat_list, 'w', encoding='utf-8') as f:
                for vf in valid_files:
                    norm_path = vf.replace('\\', '/')
                    f.write(f"file '{norm_path}'\n")

            cmd = [
                ffmpeg_exe, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', temp_concat_list,
                '-c', 'copy',
                output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kwargs)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                if os.path.exists(temp_concat_list):
                    try: os.remove(temp_concat_list)
                    except Exception: pass
                return output_path
        except Exception:
            pass

    # --- CHIẾN LƯỢC 2: Filter Complex Concat (Re-encode chuẩn hóa) ---
    if progress_callback:
        progress_callback({'status': 'merging', 'mode': 'reencode', 'message': f'Đang chuẩn hóa và ghép {len(valid_files)} tập (Re-encode)...'})

    target_w = w0 if w0 > 0 else 1920
    target_h = h0 if h0 > 0 else 1080

    cmd = [ffmpeg_exe, '-y']
    for vf in valid_files:
        cmd.extend(['-i', vf])

    filter_chunks = []
    concat_inputs = ""
    for idx in range(len(valid_files)):
        filter_chunks.append(
            f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{idx}];"
            f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{idx}]"
        )
        concat_inputs += f"[v{idx}][a{idx}]"

    filter_complex = ";".join(filter_chunks) + f";{concat_inputs}concat=n={len(valid_files)}:v=1:a=1[outv][outa]"

    cmd.extend([
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '22',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, **kwargs)
        if res.returncode != 0:
            raise Exception(f"FFmpeg ghép video thất bại: {res.stderr[-400:] if res.stderr else 'Lỗi không xác định'}")
    finally:
        if os.path.exists(temp_concat_list):
            try: os.remove(temp_concat_list)
            except Exception: pass

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise Exception("Không thể tạo file ghép sau khi xử lý.")

    return output_path


# =========================================================================
# 4. CHUNG CHO CÁC NỀN TẢNG KHÁC (YouTube, TikTok, Bilibili, Facebook...)
# =========================================================================
def get_common_ydl_opts():
    """
    Cấu hình tối ưu cho yt-dlp đối với các nền tảng khác (YouTube 2K/4K, TikTok, Facebook...)
    """
    ffmpeg_dir = get_ffmpeg_dir()
    opts = {
        'quiet': True,
        'no_warnings': True,
        'windowsfilenames': True,
        'socket_timeout': 30,
        'http_chunk_size': 10485760,  # 10MB chunking chống YouTube drop kết nối & IncompleteRead (bytes read, more expected)
        'retries': 20,  # Thử lại tối đa 20 lần khi rớt mạng
        'fragment_retries': 20,  # Thử lại từng phân đoạn khi mạng ngắt
        'file_access_retries': 5,
        'continuedl': True,  # Tự động tải nối tiếp từ mốc byte đã nhận (HTTP Range Resume)
        'buffersize': 1024 * 32,
        'nocheckcertificate': True,
        'js_runtimes': {'node': {}},
        'remote_components': {'ejs': 'github'},
        'extractor_args': {
            'tiktok': {
                'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8,zh-CN;q=0.7',
        }
    }
    
    cookie_file = os.path.join(ROOT_DIR, 'cookies.txt')
    if os.path.exists(cookie_file):
        opts['cookiefile'] = cookie_file

    if ffmpeg_dir:
        opts['ffmpeg_location'] = ffmpeg_dir
    return opts

def extract_video_info(url):
    """
    Trích xuất metadata video cực nhanh cho tất cả nền tảng
    """
    clean_url = clean_url_input(url)
    if not clean_url:
        return {'error': 'URL không hợp lệ. Vui lòng nhập link video!'}

    # 1. Nền tảng Douyin -> Dùng Douyin Media Resolver chuyên biệt (Section 8)
    if is_douyin_url(clean_url):
        return resolve_douyin_media(clean_url)

    # 2. Nền tảng Bilibili -> Dùng BBDown Engine chuyên biệt
    if is_bilibili_url(clean_url):
        try:
            import bilibili_downloader
            return bilibili_downloader.extract_bilibili_info(clean_url)
        except Exception as e:
            return {'error': f"Lỗi phân tích Bilibili: {str(e)}"}

    # 3. Các nền tảng khác -> Dùng yt-dlp
    ydl_opts = get_common_ydl_opts()
    ydl_opts['skip_download'] = True
    ydl_opts['extract_flat'] = False

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            title = info.get('title', 'Video không có tiêu đề')
            thumbnail = info.get('thumbnail') or (info.get('thumbnails')[-1]['url'] if info.get('thumbnails') else '')
            duration = info.get('duration', 0)
            uploader = info.get('uploader') or info.get('channel') or info.get('creator') or 'Không rõ'
            extractor = info.get('extractor_key') or info.get('extractor') or 'Khác'
            
            formats = info.get('formats', [])
            available_resolutions = []
            seen_heights = set()
            
            available_resolutions.append({
                'format_id': 'best',
                'label': 'Chất lượng cao nhất (Gốc)',
                'height': 9999,
                'ext': 'mp4'
            })

            for f in formats:
                height = f.get('height')
                vcodec = f.get('vcodec')
                if height and height >= 144 and vcodec != 'none':
                    if height not in seen_heights:
                        seen_heights.add(height)
                        lbl = f"{height}p"
                        if height >= 4320: lbl += " (8K Ultra HD)"
                        elif height >= 2160: lbl += " (4K Ultra HD)"
                        elif height >= 1440: lbl += " (2K QHD)"
                        elif height >= 1080: lbl += " (Full HD)"
                        elif height >= 720: lbl += " (HD)"
                        
                        available_resolutions.append({
                            'format_id': str(height),
                            'label': lbl,
                            'height': height,
                            'ext': 'mp4'
                        })

            available_resolutions.sort(key=lambda x: x['height'], reverse=True)

            return {
                'success': True,
                'title': sanitize_filename(title) or title,
                'thumbnail': thumbnail,
                'duration': duration,
                'uploader': uploader,
                'extractor': extractor,
                'url': clean_url,
                'resolutions': available_resolutions
            }
    except Exception as e:
        err_msg = str(e)
        err_msg = re.sub(r'\x1b\[[0-9;]*m', '', err_msg)
        err_msg = re.sub(r'ERROR:\s*', '', err_msg)
        
        if 'HTTP Error 403' in err_msg:
            err_msg = 'Không thể truy cập video (HTTP 403). Video có thể bị giới hạn vùng hoặc yêu cầu đăng nhập.'
        elif 'Video unavailable' in err_msg or 'unavailable' in err_msg.lower():
            err_msg = 'Video không khả dụng. Video có thể đã bị xóa hoặc bị giới hạn. Vui lòng thử video khác.'
        elif 'Private video' in err_msg:
            err_msg = 'Đây là video riêng tư, không thể tải về.'
        elif 'Sign in' in err_msg or 'age' in err_msg.lower():
            err_msg = 'Video yêu cầu đăng nhập hoặc xác minh tuổi. Không thể tải về.'
        elif 'Unsupported URL' in err_msg:
            err_msg = 'Liên kết không được hỗ trợ. Vui lòng dùng link từ YouTube, TikTok, Douyin hoặc Bilibili.'
        return {'error': err_msg}

def download_media(url, format_id='best', is_audio=False, output_dir=None, progress_callback=None, info=None, video_urls=None):
    """
    Tải video hoặc audio từ URL và stream tiến độ
    """
    clean_url = clean_url_input(url)
    if not clean_url:
        raise ValueError('URL không hợp lệ')

    if not output_dir:
        output_dir = os.path.join(ROOT_DIR, 'downloads')
    os.makedirs(output_dir, exist_ok=True)

    # 1. Nếu là Douyin, sử dụng Stream Downloader với Range Resume & Retry (Section 9)
    if is_douyin_url(clean_url):
        resolved_info = info
        if not resolved_info or not resolved_info.get('video_urls'):
            resolved_info = resolve_douyin_media(clean_url, use_cache=True)
            
        if not resolved_info or not resolved_info.get('success'):
            raise Exception(resolved_info.get('error', 'Không thể phân tích video Douyin.'))
            
        fmt_map = resolved_info.get('format_url_map', {})
        if format_id and format_id in fmt_map and fmt_map[format_id]:
            target_video_urls = fmt_map[format_id]
        else:
            target_video_urls = video_urls or resolved_info.get('video_urls', [])
            
        if not target_video_urls:
            raise Exception('Không tìm thấy luồng tải video khả dụng.')
            
        title = resolved_info.get('title', 'douyin_video')
        video_id = resolved_info.get('video_id', 'video')
        ext = 'mp3' if is_audio else 'mp4'
        
        # Đặt tên file Windows an toàn, giữ nguyên tiêu đề gốc và xử lý collision (2), (3)
        base_name = f"{title} [{video_id}]" if video_id and video_id != 'video' else title
        final_filename, _ = resolve_unique_filename(output_dir, base_name, ext=ext)
            
        download_stream_with_resume(
            video_urls=target_video_urls,
            output_path=final_filename,
            is_audio=is_audio,
            progress_callback=progress_callback,
            aweme_id=video_id
        )
        return final_filename, resolved_info


    # 2. Nếu là Bilibili, sử dụng BBDown Engine chuyên biệt
    if is_bilibili_url(clean_url):
        import bilibili_downloader
        return bilibili_downloader.download_bilibili_media(
            url=clean_url,
            format_id=format_id,
            is_audio=is_audio,
            output_dir=output_dir,
            progress_callback=progress_callback,
            info=info
        )

    # 3. Xử lý chuẩn bằng yt-dlp cho các nền tảng khác
    downloaded_file = {'path': None}

    def hook(d):
        if progress_callback:
            status = d.get('status')
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                percent = 0
                if total_bytes > 0:
                    percent = round((downloaded / total_bytes) * 100, 1)
                
                speed = d.get('speed') or 0
                speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else "-- MB/s"
                eta = d.get('eta') or 0
                eta_str = f"{eta}s" if eta else "--"
                
                progress_callback({
                    'status': 'downloading',
                    'percent': percent,
                    'speed': speed_str,
                    'eta': eta_str
                })
            elif status == 'finished':
                progress_callback({
                    'status': 'processing',
                    'message': 'Đang chuyển đổi và đóng gói bằng FFmpeg...'
                })
                filename = d.get('filename')
                if filename:
                    downloaded_file['path'] = filename

    ydl_opts = get_common_ydl_opts()
    ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title).120B [%(id)s].%(ext)s')
    ydl_opts['progress_hooks'] = [hook]

    def pp_hook(d):
        if progress_callback:
            status = d.get('status')
            if status == 'started':
                progress_callback({
                    'status': 'processing',
                    'message': 'Đang đóng gói và ghép nối video bằng FFmpeg...'
                })
    ydl_opts['postprocessor_hooks'] = [pp_hook]

    if is_audio:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        if format_id and format_id != 'best' and format_id.isdigit():
            ydl_opts['format'] = f"bestvideo[height<={format_id}]+bestaudio/best[height<={format_id}]/best[ext=mp4]/best"
        elif format_id and format_id != 'best':
            ydl_opts['format'] = f"{format_id}+bestaudio/best[ext=mp4]/best"
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best[ext=mp4]/best'
            
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            final_filename = ydl.prepare_filename(info)
            
            if is_audio:
                base, _ = os.path.splitext(final_filename)
                final_filename = base + '.mp3'
            else:
                base, ext = os.path.splitext(final_filename)
                if ext.lower() != '.mp4' and os.path.exists(base + '.mp4'):
                    final_filename = base + '.mp4'

            return final_filename, info
    except Exception as e:
        err_msg = str(e)
        err_msg = re.sub(r'\x1b\[[0-9;]*m', '', err_msg)
        err_msg = re.sub(r'ERROR:\s*', '', err_msg)
        
        if 'HTTP Error 403' in err_msg:
            raise Exception('Không thể tải video (HTTP 403). Video có thể bị giới hạn vùng hoặc yêu cầu đăng nhập.')
        elif 'Video unavailable' in err_msg or 'unavailable' in err_msg.lower():
            raise Exception('Video không khả dụng. Video có thể đã bị xóa hoặc bị giới hạn. Vui lòng thử video khác.')
        elif 'bytes read' in err_msg or 'more expected' in err_msg or 'incompleteread' in err_msg.lower():
            raise Exception('Kết nối mạng bị gián đoạn giữa chừng khi tải từ máy chủ (Incomplete Read). Vui lòng kiểm tra lại đường truyền mạng hoặc thử lại!')
        else:
            raise Exception(f'Lỗi tải video: {err_msg}')
