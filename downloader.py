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
import requests
import subprocess
import yt_dlp
import ffmpeg_installer
import concurrent.futures
import threading

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_ffmpeg_dir():
    ffmpeg_path = ffmpeg_installer.get_ffmpeg_path()
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        return os.path.dirname(ffmpeg_path)
    bin_dir = os.path.join(ROOT_DIR, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'ffmpeg.exe')):
        return bin_dir
    return None

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

def sanitize_filename(name, max_len=90):
    r"""
    Vệ sinh tên file theo chuẩn Section 28 (loại bỏ / \ : * ? " < > |)
    """
    if not name:
        return 'video'
    # Loại bỏ ký tự cấm của hệ điều hành
    clean = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    # Rút gọn khoảng trắng
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > max_len:
        clean = clean[:max_len].strip()
    return clean or 'video'

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

def _format_single_douyin_detail(detail, video_id=None, page_title='', target_url=''):
    """
    Format 1 video detail Douyin thành cấu trúc chuẩn Section 8.
    """
    if not detail:
        return None
    aweme_id = str(detail.get('aweme_id') or detail.get('id') or video_id or 'unknown_id')
    title = detail.get('desc') or page_title or 'Video Douyin'
    title = re.sub(r' - 抖音$', '', title).strip()
    safe_title = sanitize_filename(title)
    
    author = detail.get('author', {}).get('nickname', 'Tác giả Douyin')
    duration = round((detail.get('duration', 0) or 0) / 1000.0, 1)
    video = detail.get('video', {})
    cover = video.get('cover', {}).get('url_list', [''])[0] or video.get('origin_cover', {}).get('url_list', [''])[0]
    height = video.get('height', 1080)
    width = video.get('width', 1920)
    
    resolutions = []
    format_url_map = {}
    bit_rate_list = video.get('bit_rate', []) or []
    sorted_bitrates = sorted(bit_rate_list, key=lambda x: (x.get('quality_type', 0) or 0, x.get('bit_rate', 0) or 0), reverse=True)
    
    seen_heights = set()
    for br in sorted_bitrates:
        gear = str(br.get('gear_name', ''))
        q_type = br.get('quality_type')
        h = br.get('height') or height or 1080
        if '1080' in gear or q_type == 1080: h = 1080
        elif '720' in gear or q_type == 720: h = 720
        elif '540' in gear or q_type == 540: h = 540
        elif '480' in gear or q_type == 480: h = 480
        
        br_urls = br.get('play_addr', {}).get('url_list', []) or []
        clean_br_urls = [u.replace('playwm', 'play') for u in br_urls if u and not _is_ad_or_guide_url(u)]
        
        if clean_br_urls:
            lbl = f"{h}p"
            if h >= 2160: lbl += " (4K Ultra HD)"
            elif h >= 1440: lbl += " (2K QHD)"
            elif h >= 1080: lbl += " (Full HD)"
            elif h >= 720: lbl += " (HD)"
            
            fmt_id = str(h)
            if fmt_id not in seen_heights:
                seen_heights.add(fmt_id)
                resolutions.append({
                    'format_id': fmt_id,
                    'label': lbl,
                    'height': h,
                    'ext': 'mp4'
                })
                format_url_map[fmt_id] = clean_br_urls

    url_list = []
    for u in video.get('play_addr', {}).get('url_list', []):
        u_clean = u.replace('playwm', 'play')
        if u_clean and u_clean not in url_list and not _is_ad_or_guide_url(u_clean):
            url_list.append(u_clean)
            
    for u in video.get('download_addr', {}).get('url_list', []):
        if u and u not in url_list and not _is_ad_or_guide_url(u):
            url_list.append(u)
            
    for u in video.get('play_addr_h264', {}).get('url_list', []):
        if u and u not in url_list and not _is_ad_or_guide_url(u):
            url_list.append(u)

    if not url_list:
        for br_urls in format_url_map.values():
            for u in br_urls:
                if u not in url_list:
                    url_list.append(u)

    if not url_list:
        return None

    if resolutions:
        best_fmt = resolutions[0]
        best_urls = format_url_map.get(best_fmt['format_id'], url_list)
        resolutions.insert(0, {
            'format_id': 'best',
            'label': f"Chất lượng cao nhất ({best_fmt['label']})",
            'height': best_fmt['height'],
            'ext': 'mp4'
        })
        format_url_map['best'] = best_urls
    else:
        lbl = f"{height}p"
        if height >= 1080: lbl += " (Full HD)"
        elif height >= 720: lbl += " (HD)"
        resolutions = [
            {'format_id': 'best', 'label': 'Chất lượng cao nhất (Gốc)', 'height': 9999, 'ext': 'mp4'},
            {'format_id': str(height), 'label': lbl, 'height': height, 'ext': 'mp4'}
        ]
        format_url_map['best'] = url_list
        format_url_map[str(height)] = url_list

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
        else:
            return {'error': 'Không tìm thấy luồng tải video khả dụng cho video Douyin này (đã loại trừ video quảng cáo).'}

    # Thu thập tất cả các video được quét (chống circular reference)
    all_formatted_videos = []
    seen_ids = set()
    
    if primary_info and primary_info.get('video_id'):
        seen_ids.add(primary_info['video_id'])
        # Tạo dict copy độc lập, tránh lồng ghép tham chiếu vòng
        all_formatted_videos.append(dict(primary_info))
        
    if all_details:
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
                        captured_data['detail'] = det or ssr_all[0]
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
def download_stream_with_resume(video_urls, output_path, is_audio=False, progress_callback=None, max_retries=3, num_threads=4):
    """
    Tải stream đa luồng (Multi-Connection Range Downloader - chuẩn IDM 4-6 luồng)
    với tự động fallback đơn luồng, hỗ trợ HTTP Range Resume và Exponential Backoff Retry.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
        'Accept': '*/*',
    }
    
    part_path = output_path + '.part'
    backoff_delays = [1, 2, 4]
    
    # 1. Thử qua từng URL để thăm dò kích thước và hỗ trợ Range
    selected_url = None
    total_file_size = 0
    accept_ranges = False
    
    session = requests.Session()
    
    for v_url in video_urls:
        try:
            r_head = session.head(v_url, headers=headers, allow_redirects=True, timeout=8)
            if r_head.status_code in [200, 206]:
                selected_url = v_url
                total_file_size = int(r_head.headers.get('content-length', 0))
                accept_ranges = 'bytes' in r_head.headers.get('accept-ranges', '').lower() or r_head.status_code == 206
                break
        except Exception:
            pass
        # Nếu HEAD bị chặn, thử GET 2 bytes
        try:
            r_test = session.get(v_url, headers={**headers, 'Range': 'bytes=0-1'}, stream=True, timeout=8)
            if r_test.status_code == 206:
                selected_url = v_url
                accept_ranges = True
                cr = r_test.headers.get('content-range', '')
                if '/' in cr:
                    total_file_size = int(cr.split('/')[-1])
                break
            elif r_test.status_code == 200:
                selected_url = v_url
                total_file_size = int(r_test.headers.get('content-length', 0))
                break
        except Exception:
            pass
            
    if not selected_url and video_urls:
        selected_url = video_urls[0]

    success = False
    
    # 2. Nếu server hỗ trợ Range và dung lượng > 2MB -> TẢI ĐA LUỒNG SIÊU TỐC (IDM Standard)
    if accept_ranges and total_file_size > 2 * 1024 * 1024:
        threads_count = min(num_threads, 6)
        chunk_size_per_thread = total_file_size // threads_count
        ranges = []
        for i in range(threads_count):
            start = i * chunk_size_per_thread
            end = total_file_size - 1 if i == threads_count - 1 else (start + chunk_size_per_thread - 1)
            ranges.append((i, start, end))
            
        temp_files = [f"{part_path}.part{i}" for i in range(threads_count)]
        downloaded_bytes = [0] * threads_count
        lock = threading.Lock()
        t0 = time.time()
        last_cb_time = t0
        
        def _download_range(idx, start_byte, end_byte):
            nonlocal last_cb_time
            req_h = headers.copy()
            req_h['Range'] = f"bytes={start_byte}-{end_byte}"
            temp_f = temp_files[idx]
            
            with requests.get(selected_url, headers=req_h, stream=True, timeout=25) as r:
                r.raise_for_status()
                with open(temp_f, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*512):
                        if chunk:
                            f.write(chunk)
                            with lock:
                                downloaded_bytes[idx] += len(chunk)
                                total_dl = sum(downloaded_bytes)
                                now = time.time()
                                if progress_callback and (now - last_cb_time >= 0.15 or total_dl >= total_file_size):
                                    last_cb_time = now
                                    pct = round((total_dl / total_file_size) * 100, 1) if total_file_size > 0 else 0
                                    el = now - t0
                                    spd = (total_dl / el) if el > 0 else 0
                                    spd_str = f"{spd / (1024*1024):.1f} MB/s" if spd else "-- MB/s"
                                    rem = max(0, total_file_size - total_dl)
                                    eta = int(rem / spd) if spd > 0 else 0
                                    progress_callback({
                                        'status': 'downloading',
                                        'downloaded_bytes': total_dl,
                                        'total_bytes': total_file_size,
                                        'percent': pct,
                                        'speed': spd_str,
                                        'eta': f"{eta}s" if eta else "--"
                                    })
                                    
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads_count) as executor:
                futures = [executor.submit(_download_range, r[0], r[1], r[2]) for r in ranges]
                concurrent.futures.wait(futures)
                for f in futures:
                    f.result()
                    
            # Ghép nối các file part thành part_path chính thức
            with open(part_path, 'wb') as out_f:
                for temp_f in temp_files:
                    if os.path.exists(temp_f):
                        with open(temp_f, 'rb') as in_f:
                            while True:
                                b = in_f.read(1024 * 1024 * 2)
                                if not b:
                                    break
                                out_f.write(b)
                        try:
                            os.remove(temp_f)
                        except Exception:
                            pass
            success = True
        except Exception:
            for temp_f in temp_files:
                if os.path.exists(temp_f):
                    try: os.remove(temp_f)
                    except Exception: pass
            success = False

    # 3. Fallback: Đơn luồng nếu Range không hỗ trợ hoặc tải đa luồng gặp lỗi
    if not success:
        downloaded_total = 0
        if os.path.exists(part_path):
            downloaded_total = os.path.getsize(part_path)
            
        for attempt in range(max_retries):
            for v_url in ([selected_url] if selected_url else []) + [u for u in video_urls if u != selected_url]:
                try:
                    req_headers = headers.copy()
                    if downloaded_total > 0:
                        req_headers['Range'] = f"bytes={downloaded_total}-"
                        
                    with requests.get(v_url, headers=req_headers, stream=True, timeout=25) as r:
                        if r.status_code == 206:
                            content_range = r.headers.get('content-range', '')
                            m = re.search(r'/(\d+)', content_range)
                            total_file_size = int(m.group(1)) if m else (downloaded_total + int(r.headers.get('content-length', 0)))
                            mode = 'ab'
                        elif r.status_code == 200:
                            total_file_size = int(r.headers.get('content-length', 0))
                            downloaded_total = 0
                            mode = 'wb'
                        else:
                            continue
                            
                        start_time = time.time()
                        last_update = start_time
                        
                        with open(part_path, mode) as f:
                            for chunk in r.iter_content(chunk_size=1024*1024):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_total += len(chunk)
                                    now = time.time()
                                    if progress_callback and (now - last_update >= 0.2 or (total_file_size and downloaded_total == total_file_size)):
                                        last_update = now
                                        percent = round((downloaded_total / total_file_size) * 100, 1) if total_file_size > 0 else 0
                                        elapsed = now - start_time
                                        speed = (downloaded_total - (downloaded_total if mode == 'wb' else 0)) / elapsed if elapsed > 0 else 0
                                        speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else "-- MB/s"
                                        remaining = max(0, total_file_size - downloaded_total)
                                        eta = int(remaining / speed) if speed > 0 else 0
                                        
                                        progress_callback({
                                            'status': 'downloading',
                                            'downloaded_bytes': downloaded_total,
                                            'total_bytes': total_file_size,
                                            'percent': percent,
                                            'speed': speed_str,
                                            'eta': f"{eta}s" if eta else "--"
                                        })
                                        
                        if (total_file_size > 0 and downloaded_total >= total_file_size) or (downloaded_total > 1024*100 and total_file_size == 0):
                            success = True
                            break
                except (requests.RequestException, IOError):
                    time.sleep(backoff_delays[min(attempt, len(backoff_delays)-1)])
                    continue
            if success:
                break

    if not success or not os.path.exists(part_path):
        raise Exception('Không thể tải luồng video từ máy chủ Douyin sau nhiều lần thử lại.')
        
    # Xử lý âm thanh nếu yêu cầu Audio MP3 (Section 13)
    if is_audio:
        if progress_callback:
            progress_callback({
                'status': 'processing',
                'message': 'Đang chuyển đổi âm thanh sang MP3 bằng FFmpeg...'
            })
        ffmpeg_dir = get_ffmpeg_dir()
        ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else 'ffmpeg'
        cmd = [ffmpeg_exe, '-y', '-i', part_path, '-vn', '-ab', '192k', output_path]
        subprocess.run(cmd, capture_output=True, check=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except Exception:
                pass
        return output_path
        
    # Đổi tên nguyên tử từ .part sang file chính thức
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    os.rename(part_path, output_path)
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

    # 2. Các nền tảng khác -> Dùng yt-dlp
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
        safe_title = sanitize_filename(title, max_len=70)
        ext = 'mp3' if is_audio else 'mp4'
        
        # Đặt tên file chuẩn Section 28: {sanitized_title} [{video_id}].mp4
        final_filename = os.path.join(output_dir, f"{safe_title} [{video_id}].{ext}")
        
        counter = 1
        base_path, _ = os.path.splitext(final_filename)
        while os.path.exists(final_filename):
            final_filename = f"{base_path}_{counter}.{ext}"
            counter += 1
            
        download_stream_with_resume(
            video_urls=target_video_urls,
            output_path=final_filename,
            is_audio=is_audio,
            progress_callback=progress_callback
        )
        return final_filename, resolved_info


    # 2. Xử lý chuẩn bằng yt-dlp cho các nền tảng khác
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
        else:
            raise Exception(f'Lỗi tải video: {err_msg}')
