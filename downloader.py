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

def _find_aweme_detail_in_json(data):
    """
    Tìm đối tượng aweme_detail hoặc video detail hợp lệ trong cấu trúc JSON lồng nhau
    """
    if isinstance(data, dict):
        # 1. Kiểm tra nếu chính là aweme_detail hoặc itemStruct
        if ('aweme_id' in data or 'id' in data) and 'video' in data and isinstance(data.get('video'), dict):
            video = data['video']
            if video.get('play_addr') or video.get('bit_rate') or video.get('download_addr'):
                return data
                
        # 2. Kiểm tra các key phổ biến
        for key in ['aweme_detail', 'awemeDetail', 'videoDetail', 'itemStruct', 'itemInfo', 'item_list']:
            if key in data:
                res = _find_aweme_detail_in_json(data[key])
                if res:
                    return res

        for k, v in data.items():
            if isinstance(v, (dict, list)):
                res = _find_aweme_detail_in_json(v)
                if res:
                    return res
                    
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                res = _find_aweme_detail_in_json(item)
                if res:
                    return res

    return None

def _extract_aweme_detail_from_html(html_content):
    """
    Trích xuất aweme_detail từ tất cả các thẻ script SSR của Douyin
    """
    if not html_content:
        return None

    import urllib.parse
    # 1. __UNIVERSAL_DATA_FOR_REHYDRATION__
    m_univ = re.search(r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"\s+type="application/json">([^<]+)</script>', html_content)
    if m_univ:
        try:
            raw_json = json.loads(m_univ.group(1).strip())
            detail = _find_aweme_detail_in_json(raw_json)
            if detail:
                return detail
        except Exception:
            pass

    # 2. _ROUTER_DATA
    m_router = re.search(r'<script\s+id="_ROUTER_DATA"\s+type="application/json">([^<]+)</script>', html_content)
    if m_router:
        try:
            raw_json = json.loads(m_router.group(1).strip())
            detail = _find_aweme_detail_in_json(raw_json)
            if detail:
                return detail
        except Exception:
            pass

    # 3. RENDER_DATA
    m_render = re.search(r'<script\s+id="RENDER_DATA"\s+type="application/json">([^<]+)</script>', html_content)
    if m_render:
        try:
            raw_text = urllib.parse.unquote(m_render.group(1).strip())
            raw_json = json.loads(raw_text)
            detail = _find_aweme_detail_in_json(raw_json)
            if detail:
                return detail
        except Exception:
            pass

    # 4. Fallback: Bất kỳ thẻ script chứa JSON có aweme_id hoặc video
    script_matches = re.findall(r'<script[^>]*type="application/json"[^>]*>([^<]+)</script>', html_content)
    for s_content in script_matches:
        try:
            raw_json = json.loads(s_content.strip())
            detail = _find_aweme_detail_in_json(raw_json)
            if detail:
                return detail
        except Exception:
            pass

    return None

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

def _format_douyin_result(detail, video_id, page_title, target_url, original_url, captured_video_srcs=None):
    """
    Chuẩn hóa cấu trúc dữ liệu kết quả Douyin chuẩn Section 8 & 28.
    """
    if captured_video_srcs is None:
        captured_video_srcs = []
        
    resolutions = []
    format_url_map = {}
    
    if detail:
        aweme_id = detail.get('aweme_id') or video_id or 'unknown_id'
        title = detail.get('desc') or page_title or 'Video Douyin'
        title = re.sub(r' - 抖音$', '', title).strip()
        safe_title = sanitize_filename(title)
        
        author = detail.get('author', {}).get('nickname', 'Tác giả Douyin')
        duration = round((detail.get('duration', 0) or 0) / 1000.0, 1)
        video = detail.get('video', {})
        cover = video.get('cover', {}).get('url_list', [''])[0] or video.get('origin_cover', {}).get('url_list', [''])[0]
        height = video.get('height', 1080)
        width = video.get('width', 1920)
        
        # Trích xuất tất cả các luồng phân giải từ bit_rate
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

        # Thu thập các URL mặc định
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

        for s in captured_video_srcs:
            if s not in url_list and not _is_ad_or_guide_url(s):
                url_list.append(s)
    else:
        aweme_id = video_id or 'unknown_id'
        title = page_title or 'Video Douyin'
        title = re.sub(r' - 抖音$', '', title).strip()
        safe_title = sanitize_filename(title)
        author = 'Tác giả Douyin'
        duration = 0
        cover = ''
        url_list = [s for s in captured_video_srcs if not _is_ad_or_guide_url(s)]
        height = 1080
        width = 1920
        detail = {}
    
    if not url_list:
        return {'error': 'Không tìm thấy luồng tải video khả dụng cho video Douyin này (đã loại trừ video quảng cáo).'}

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
    
    res_info = {
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
        'url': target_url,
        'video_urls': url_list,
        'resolutions': resolutions,
        'format_url_map': format_url_map,
        'raw_detail': detail
    }
    
    # Lưu cache
    now = time.time()
    _DOUYIN_RESOLVE_CACHE[target_url] = {'timestamp': now, 'data': res_info}
    _DOUYIN_RESOLVE_CACHE[original_url] = {'timestamp': now, 'data': res_info}
    if aweme_id:
        _DOUYIN_RESOLVE_CACHE[str(aweme_id)] = {'timestamp': now, 'data': res_info}
        
    return res_info

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
                resp_head = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
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
                r_api = requests.get(api_url, headers=headers, timeout=8)
                if r_api.status_code == 200:
                    api_json = r_api.json()
                    det = _find_aweme_detail_in_json(api_json)
                    if det:
                        return _format_douyin_result(det, video_id, '', target_url, url, [])
            except Exception:
                pass

        # 3. Thử tải HTML của target_url và bóc tách SSR JSON
        try:
            r_page = requests.get(target_url, headers=headers, timeout=10)
            if r_page.status_code == 200:
                ssr_detail = _extract_aweme_detail_from_html(r_page.text)
                if ssr_detail:
                    title_m = re.search(r'<title>([^<]+)</title>', r_page.text)
                    p_title = title_m.group(1) if title_m else ''
                    return _format_douyin_result(ssr_detail, video_id, p_title, target_url, url, [])
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
        resp = requests.post(api_url, data={'url': url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}, timeout=10)
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
                    res_info = {
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
                    return res_info
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
    
    # 1. Kiểm tra Cache trước
    if use_cache:
        now = time.time()
        for k in [target_url, url, video_id]:
            if k and k in _DOUYIN_RESOLVE_CACHE:
                entry = _DOUYIN_RESOLVE_CACHE[k]
                if now - entry['timestamp'] < 1800:
                    return entry['data']

    # 2. Thử giải mã trực tiếp qua HTTP Direct API / SSR (Nhanh gấp 10x, 100% không phụ thuộc Chromium)
    http_result = _resolve_douyin_http_direct(target_url, video_id)
    if http_result and http_result.get('success'):
        return http_result

    # 3. Thử giải mã qua Cloud API
    cloud_result = _resolve_via_cloud_api(target_url)
    if cloud_result and cloud_result.get('success'):
        _DOUYIN_RESOLVE_CACHE[target_url] = {'timestamp': time.time(), 'data': cloud_result}
        return cloud_result

    # 4. Thử giải mã qua yt-dlp
    try:
        ydl_opts = get_common_ydl_opts()
        ydl_opts['skip_download'] = True
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            if info:
                vid_urls = []
                for f in info.get('formats', []):
                    u = f.get('url')
                    if u and u.startswith('http') and not _is_ad_or_guide_url(u):
                        vid_urls.append(u)
                if info.get('url') and info['url'].startswith('http'):
                    vid_urls.insert(0, info['url'])
                if vid_urls:
                    res_ytdlp = {
                        'success': True,
                        'video_id': str(info.get('id') or video_id or 'unknown_id'),
                        'title': sanitize_filename(info.get('title') or 'Video Douyin'),
                        'uploader': info.get('uploader') or 'Tác giả Douyin',
                        'author': info.get('uploader') or 'Tác giả Douyin',
                        'duration': info.get('duration') or 0,
                        'thumbnail': info.get('thumbnail') or '',
                        'width': info.get('width', 1080),
                        'height': info.get('height', 1920),
                        'extractor': 'Douyin',
                        'url': target_url,
                        'video_urls': vid_urls,
                        'resolutions': [
                            {'format_id': 'best', 'label': 'Chất lượng cao nhất (yt-dlp)', 'height': 1080, 'ext': 'mp4'}
                        ],
                        'format_url_map': {'best': vid_urls}
                    }
                    _DOUYIN_RESOLVE_CACHE[target_url] = {'timestamp': time.time(), 'data': res_ytdlp}
                    return res_ytdlp
    except Exception:
        pass

    # 5. Fallback cuối cùng: Playwright Headless Browser (với try-catch an toàn nếu thiếu binary)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'error': 'Không thể tải video từ link này. Video có thể đang ở chế độ riêng tư hoặc link đã hết hạn.'}

    captured_data = {}
    captured_video_srcs = []
    
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                return {'error': 'Không thể bóc tách luồng video từ link này. Video có thể đang bị chặn khu vực hoặc link đã hết hạn.'}

            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                locale='zh-CN',
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            
            def handle_response(response):
                try:
                    r_url = response.url
                    if any(endpoint in r_url for endpoint in [
                        'aweme/v1/web/aweme/detail/',
                        'aweme/v1/web/aweme/iteminfo/',
                        'aweme/v1/web/item/detail/',
                        'aweme/v1/web/tab/feed/',
                        'aweme/v1/web/aweme/post/',
                        'aweme/v1/web/slider/video/'
                    ]):
                        try:
                            data = response.json()
                            det = _find_aweme_detail_in_json(data)
                            if det and not captured_data.get('detail'):
                                captured_data['detail'] = det
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
            
            try:
                page.goto(target_url, wait_until='domcontentloaded', timeout=15000)
            except Exception:
                pass
                
            for _ in range(15):
                if 'detail' in captured_data:
                    break
                page.wait_for_timeout(400)
                
            if 'detail' not in captured_data:
                try:
                    html_content = page.content()
                    ssr_detail = _extract_aweme_detail_from_html(html_content)
                    if ssr_detail:
                        captured_data['detail'] = ssr_detail
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
            
        return _format_douyin_result(captured_data.get('detail'), video_id, page_title, target_url, url, captured_video_srcs)
    except Exception as e:
        return {'error': f'Lỗi phân tích Douyin: {str(e)}'}


# =========================================================================
# 3. STREAM DOWNLOAD MANAGER VỚI RANGE RESUME & RETRY (Section 9 & 27)
# =========================================================================
def download_stream_with_resume(video_urls, output_path, is_audio=False, progress_callback=None, max_retries=3):
    """
    Tải stream chunk trực tiếp xuống disk (.part), hỗ trợ HTTP Range Resume và Exponential Backoff Retry.
    Không lưu toàn bộ video trong RAM (Section 27).
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
        'Accept': '*/*',
    }
    
    part_path = output_path + '.part'
    backoff_delays = [2, 5, 10]
    chunk_size = 1024 * 256  # 256 KB chunk
    
    # Kiểm tra file dở dang để tải tiếp (Resume - Section 9)
    downloaded_total = 0
    if os.path.exists(part_path):
        downloaded_total = os.path.getsize(part_path)
        
    success = False
    total_file_size = 0
    
    for attempt in range(max_retries):
        for v_url in video_urls:
            try:
                req_headers = headers.copy()
                if downloaded_total > 0:
                    req_headers['Range'] = f"bytes={downloaded_total}-"
                    
                with requests.get(v_url, headers=req_headers, stream=True, timeout=25) as r:
                    if r.status_code == 206:
                        # Server hỗ trợ Resume (Partial Content)
                        content_range = r.headers.get('content-range', '')
                        m = re.search(r'/(\d+)', content_range)
                        total_file_size = int(m.group(1)) if m else (downloaded_total + int(r.headers.get('content-length', 0)))
                        mode = 'ab'
                    elif r.status_code == 200:
                        # Server gửi full stream từ đầu
                        total_file_size = int(r.headers.get('content-length', 0))
                        downloaded_total = 0
                        mode = 'wb'
                    else:
                        continue
                        
                    start_time = time.time()
                    last_update = start_time
                    
                    with open(part_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded_total += len(chunk)
                                now = time.time()
                                if progress_callback and (now - last_update >= 0.25 or (total_file_size and downloaded_total == total_file_size)):
                                    last_update = now
                                    percent = round((downloaded_total / total_file_size) * 100, 1) if total_file_size > 0 else 0
                                    elapsed = now - start_time
                                    speed = (downloaded_total - (downloaded_total if mode == 'wb' else 0)) / elapsed if elapsed > 0 else 0
                                    speed_str = f"{speed / (1024*1024):.1f} MB/s" if speed else "-- MB/s"
                                    remaining = max(0, total_file_size - downloaded_total)
                                    eta = int(remaining / speed) if speed > 0 else 0
                                    eta_str = f"{eta}s" if eta else "--"
                                    
                                    progress_callback({
                                        'status': 'downloading',
                                        'downloaded_bytes': downloaded_total,
                                        'total_bytes': total_file_size,
                                        'percent': percent,
                                        'speed': speed_str,
                                        'eta': eta_str
                                    })
                                    
                    # Kiểm tra hoàn thành
                    if (total_file_size > 0 and downloaded_total >= total_file_size) or (downloaded_total > 1024*100 and total_file_size == 0):
                        success = True
                        break
                        
            except (requests.RequestException, IOError) as e:
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
    Cấu hình tối ưu cho yt-dlp đối với các nền tảng khác
    """
    ffmpeg_dir = get_ffmpeg_dir()
    opts = {
        'quiet': True,
        'no_warnings': True,
        'windowsfilenames': True,
        'socket_timeout': 30,
        'js_runtimes': {'node': {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            },
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
                'label': 'Chất lượng cao nhất (Tự động)',
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
                        if height >= 2160: lbl += " (4K Ultra HD)"
                        elif height >= 1440: lbl += " (2K QHD)"
                        elif height >= 1080: lbl += " (Full HD)"
                        elif height >= 720: lbl += " (HD)"
                        
                        available_resolutions.append({
                            'format_id': f.get('format_id') or str(height),
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
