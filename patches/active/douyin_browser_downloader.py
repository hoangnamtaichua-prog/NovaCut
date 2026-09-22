# -*- coding: utf-8 -*-
"""
NovaCut Douyin Video & Channel Downloader Engine
Mô-đun Tải Video Đơn Lẻ & Tải Toàn Bộ Kênh Douyin Hàng Loạt (Channel Batch Downloader)
Sử dụng Browser Worker (Edge / Chromium Persistent Context) lắng nghe Network Response API & Luồng MP4 không logo.
"""

import os
import sys
import re
import json
import time
import math
import random
import urllib.parse
import requests
import concurrent.futures
import threading

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(ROOT_DIR, "temp", "douyin_browser_profile")
DOWNLOAD_DIR = os.path.join(ROOT_DIR, "downloads")
os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
)


def sanitize_filename(name, max_len=80):
    """Làm sạch tên file để lưu trữ an toàn trên Windows."""
    if not name:
        return "douyin_video"
    clean = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > max_len:
        clean = clean[:max_len].strip()
    return clean or "douyin_video"


def clean_url_input(text):
    """Trích xuất liên kết URL từ chuỗi người dùng dán vào."""
    if not text:
        return ""
    text = text.strip()
    match = re.search(r'(https?://[^\s\'"<>]+)', text)
    if match:
        return match.group(1).rstrip('.,;!?/')
    return text


def resolve_redirect_url(url, timeout=10):
    """Phân giải link rút gọn (v.douyin.com) để lấy URL thực tế."""
    clean_url = clean_url_input(url)
    if not clean_url:
        return ""
    try:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        res = requests.get(clean_url, headers=headers, allow_redirects=True, timeout=timeout, stream=True)
        return res.url or clean_url
    except Exception:
        return clean_url


def extract_sec_uid(url_or_text):
    """Trích xuất sec_uid của kênh Douyin từ link profile hoặc link chia sẻ."""
    raw_url = clean_url_input(url_or_text)
    if not raw_url:
        return None, None
    
    # Dạng chuỗi sec_uid trực tiếp
    if raw_url.startswith("MS4wLjAB") or (len(raw_url) >= 30 and not "/" in raw_url and not "." in raw_url):
        return raw_url, f"https://www.douyin.com/user/{raw_url}"
    
    # Nếu là link rút gọn, giải mã redirect
    if "v.douyin.com" in raw_url:
        raw_url = resolve_redirect_url(raw_url)

    # Tìm sec_uid trong URL
    # Dạng 1: /user/MS4wLjABAAAA...
    m_user = re.search(r'/user/([a-zA-Z0-9_\-]+)', raw_url)
    if m_user:
        return m_user.group(1), raw_url

    # Dạng 2: ?sec_uid=MS4wLjABAAAA... hoặc ?sec_user_id=MS4wLjABAAAA...
    m_param = re.search(r'sec_u(?:ser_)?id=([a-zA-Z0-9_\-]+)', raw_url)
    if m_param:
        return m_param.group(1), raw_url

    return None, raw_url


def extract_video_id(url_or_text):
    """Trích xuất video_id của video Douyin từ link hoặc chuỗi chia sẻ."""
    raw_url = clean_url_input(url_or_text)
    if not raw_url:
        return None, None

    if "v.douyin.com" in raw_url:
        raw_url = resolve_redirect_url(raw_url)

    # Dạng 1: /video/123456789...
    m_vid = re.search(r'/video/(\d+)', raw_url)
    if m_vid:
        return m_vid.group(1), raw_url

    # Dạng 2: modal_id=123456789...
    m_modal = re.search(r'modal_id=(\d+)', raw_url)
    if m_modal:
        return m_modal.group(1), raw_url

    # Dạng 3: /note/123456789... (Douyin Photo/Note)
    m_note = re.search(r'/note/(\d+)', raw_url)
    if m_note:
        return m_note.group(1), raw_url

    return None, raw_url


def extract_mix_id(url_or_text):
    """
    Trích xuất mix_id (ID bộ sưu tập / tuyển tập) từ liên kết Douyin hoặc chuỗi số thuần.
    Ví dụ:
    - https://www.douyin.com/collection/7412345678901234567
    - https://www.douyin.com/user/...&mix_id=7412345678901234567
    - 7412345678901234567
    """
    raw_url = clean_url_input(url_or_text)
    if not raw_url:
        return None
    if "v.douyin.com" in raw_url:
        raw_url = resolve_redirect_url(raw_url)
    m = re.search(r'collection/(\d+)', raw_url)
    if m:
        return m.group(1)
    m = re.search(r'mix_id=(\d+)', raw_url)
    if m:
        return m.group(1)
    if re.fullmatch(r'\d{15,22}', raw_url):
        return raw_url
    return None


class GlobalConnectionPool:
    """
    Quản lý pool giới hạn kết nối HTTP đồng thời trên toàn bộ batch job,
    chống bị rate-limit hoặc ngắt kết nối từ CDN Douyin.
    """
    _instances = {}
    _lock = threading.Lock()

    def __init__(self, max_connections=12, max_total_connections=None):
        limit = max_total_connections if max_total_connections is not None else max_connections
        self.max_connections = max(1, int(limit))
        self.semaphore = threading.Semaphore(self.max_connections)

    def acquire(self, blocking=True, timeout=None):
        from contextlib import contextmanager
        @contextmanager
        def _ctx():
            if timeout is not None:
                acquired = self.semaphore.acquire(blocking=blocking, timeout=timeout)
            else:
                acquired = self.semaphore.acquire(blocking=blocking)
            try:
                yield acquired
            finally:
                if acquired:
                    self.semaphore.release()
        return _ctx()

    def __enter__(self):
        self.semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.semaphore.release()

    @classmethod
    def get_pool(cls, max_connections=12):
        with cls._lock:
            key = max(1, int(max_connections))
            if key not in cls._instances:
                cls._instances[key] = cls(key)
            return cls._instances[key]



class DouyinBrowserDownloader:
    """
    Trình thu thập và tải video Douyin bằng Browser Worker ngầm (Microsoft Edge / Chromium).
    """


    def __init__(self, profile_dir=None, headless=True):
        self.profile_dir = profile_dir or PROFILE_DIR
        self.headless = headless
        os.makedirs(self.profile_dir, exist_ok=True)

    def open_login_window(self):
        """
        Mở cửa sổ trình duyệt Edge/Chromium (headless=False) để người dùng quét QR / đăng nhập Douyin 1 lần duy nhất.
        Phiên đăng nhập và Cookie sẽ được lưu vĩnh viễn trong thư mục temp/douyin_browser_profile.
        """
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    channel="msedge",
                    headless=False,
                    viewport={"width": 1280, "height": 850},
                    user_agent=DEFAULT_USER_AGENT,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=False,
                    viewport={"width": 1280, "height": 850},
                    user_agent=DEFAULT_USER_AGENT,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
            
            # Giữ cửa sổ mở để người dùng đăng nhập
            for _ in range(120):
                if context.pages:
                    time.sleep(1)
                else:
                    break
            try:
                context.close()
            except Exception:
                pass
        return True

    def scan_channel_videos(self, channel_url_or_sec_uid, limit=30, progress_cb=None):
        """
        Cào danh sách video từ 1 kênh Douyin hoặc từ Bộ sưu tập (Mix / Collection).
        Hỗ trợ phân trang tự động bằng cách cuộn chuột ảo và API cursor.
        """
        # Nếu người dùng truyền URL bộ sưu tập hoặc mix_id trực tiếp
        mix_id_direct = extract_mix_id(channel_url_or_sec_uid)
        if mix_id_direct:
            return self.scan_collection_videos(mix_id_direct, limit=limit, progress_cb=progress_cb)

        sec_uid, resolved_url = extract_sec_uid(channel_url_or_sec_uid)
        if not sec_uid:
            # Thử kiểm tra nếu dán link video -> tìm sec_uid của tác giả video
            try:
                import downloader
                vid_info = downloader.resolve_douyin_media(channel_url_or_sec_uid)
                if vid_info and vid_info.get("raw_detail"):
                    author_obj = vid_info["raw_detail"].get("author") or {}
                    sec_uid = author_obj.get("sec_uid")
            except Exception:
                pass

        if not sec_uid:
            raise ValueError(f"Không tìm thấy sec_uid của kênh Douyin từ: {channel_url_or_sec_uid}. Vui lòng kiểm tra lại link.")

        profile_url = f"https://www.douyin.com/user/{sec_uid}"

        if progress_cb: progress_cb(5, "Đang xác thực liên kết & thông tin kênh...")

        from playwright.sync_api import sync_playwright

        collected_videos = []
        seen_aweme_ids = set()
        channel_info = {
            "sec_uid": sec_uid,
            "nickname": "Kênh Douyin",
            "avatar": "",
            "signature": "",
            "total_videos_scanned": 0
        }

        with sync_playwright() as p:
            if progress_cb: progress_cb(12, "Đang khởi tạo kết nối phân tích dữ liệu...")
            context = None
            browser = None

            # Sử dụng Persistent Context (lưu giữ session, cookie và dấu vân tay thật của Edge/Chromium)
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    channel="msedge",
                    headless=self.headless,
                    viewport={"width": 1280, "height": 900},
                    user_agent=DEFAULT_USER_AGENT,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
                )
            except Exception:
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=self.profile_dir,
                        headless=self.headless,
                        viewport={"width": 1280, "height": 900},
                        user_agent=DEFAULT_USER_AGENT,
                        args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
                    )
                except Exception as e:
                    raise Exception(f"Không thể khởi tạo luồng phân tích dữ liệu: {str(e)}")

            # Kiểm tra và nạp sẵn ttwid nếu trình duyệt chưa có cookie
            try:
                existing_cookies = context.cookies()
                if not any(c.get('name') == 'ttwid' for c in existing_cookies):
                    s = requests.Session()
                    s.get("https://live.douyin.com/1", headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=6)
                    tw = s.cookies.get("ttwid")
                    if tw:
                        context.add_cookies([{"name": "ttwid", "value": tw, "domain": ".douyin.com", "path": "/"}])
            except Exception:
                pass

            page = context.pages[0] if context.pages else context.new_page()

            # Chặn ảnh, media, font, trackers nặng để quét danh sách kênh siêu tốc
            def block_heavy_assets(route):
                req = route.request
                rtype = req.resource_type
                rurl = req.url
                if rtype in ["image", "font", "media"] or any(x in rurl for x in ["bytead", "analytics", "report", "sentry", "log"]):
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", block_heavy_assets)

            pagination_state = {"last_url": "", "max_cursor": 0, "has_more": 1}

            def process_aweme_list(aweme_list):
                new_added = 0
                for item in aweme_list:
                    aweme_id = str(item.get("aweme_id") or item.get("id") or "")
                    if not aweme_id or aweme_id in seen_aweme_ids:
                        continue
                    
                    # Trích xuất thông tin video & bài viết
                    desc = str(item.get("desc") or "Video Douyin").strip()
                    video_obj = item.get("video") or {}
                    
                    # Cover Thumbnail HD
                    cover_list = (
                        (video_obj.get("cover") or {}).get("url_list") or
                        (video_obj.get("origin_cover") or {}).get("url_list") or
                        (video_obj.get("dynamic_cover") or {}).get("url_list") or []
                    )
                    cover_url = cover_list[0] if cover_list else ""

                    # Direct MP4 URL qua resolve_douyin_variants (ưu tiên bản sạch, bitrate/phân giải cao nhất)
                    import downloader
                    variants = downloader.resolve_douyin_variants(item, aweme_id=aweme_id)
                    play_url = ""
                    backup_urls = []
                    is_clean = False
                    if variants:
                        play_url = variants[0]["url"]
                        backup_urls = variants[0].get("backup_urls", [])
                        is_clean = variants[0].get("is_clean", False)
                    else:
                        bit_rate_list = video_obj.get("bit_rate") or []
                        if bit_rate_list and isinstance(bit_rate_list, list):
                            for b_item in bit_rate_list:
                                p_addrs = (b_item.get("play_addr") or {}).get("url_list") or []
                                if p_addrs:
                                    play_url = p_addrs[0]
                                    break
                        if not play_url:
                            p_list = (video_obj.get("play_addr") or {}).get("url_list") or []
                            if p_list:
                                play_url = p_list[0]

                    # Hỗ trợ bài đăng Album Ảnh / Slide (Photo Note)
                    is_images = bool(item.get("images") or item.get("aweme_type") == 68)
                    image_urls = []
                    if is_images:
                        raw_images = item.get("images") or []
                        for img_obj in raw_images:
                            u_list = img_obj.get("url_list") or []
                            if u_list:
                                image_urls.append(u_list[-1])
                        if not cover_url and image_urls:
                            cover_url = image_urls[0]

                    duration_ms = int(video_obj.get("duration") or 0)
                    duration_sec = duration_ms // 1000 if duration_ms > 1000 else duration_ms

                    stats = item.get("statistics") or {}
                    digg_count = stats.get("digg_count", 0)
                    comment_count = stats.get("comment_count", 0)
                    share_count = stats.get("share_count", 0)
                    collect_count = stats.get("collect_count", 0)

                    author_obj = item.get("author") or {}
                    if author_obj:
                        if author_obj.get("nickname") and channel_info["nickname"] == "Kênh Douyin":
                            channel_info["nickname"] = author_obj.get("nickname")
                            channel_info["avatar"] = ((author_obj.get("avatar_thumb") or {}).get("url_list") or [""])[0]
                            channel_info["signature"] = author_obj.get("signature", "")
                        if "follower_count" not in channel_info or not channel_info["follower_count"]:
                            channel_info["follower_count"] = author_obj.get("follower_count") or stats.get("follower_count") or 0
                            channel_info["total_favorited"] = author_obj.get("total_favorited") or stats.get("total_favorited") or 0
                            channel_info["aweme_count"] = author_obj.get("aweme_count") or 0

                    mix_info = item.get("mix_info") or {}
                    mix_order = item.get("_mix_order") or mix_info.get("mix_order") or mix_info.get("episode_number")

                    video_item = {
                        "aweme_id": aweme_id,
                        "title": desc,
                        "clean_title": downloader.sanitize_filename_windows(desc),
                        "url": f"https://www.douyin.com/video/{aweme_id}",
                        "download_url": play_url,
                        "backup_urls": backup_urls,
                        "is_clean": is_clean,
                        "variants": variants,
                        "mix_order": mix_order,
                        "mix_id": mix_info.get("mix_id"),
                        "cover_url": cover_url,
                        "is_images": is_images,
                        "image_urls": image_urls,
                        "duration": duration_sec,
                        "duration_formatted": f"{duration_sec // 60:02d}:{duration_sec % 60:02d}",
                        "digg_count": digg_count,
                        "comment_count": comment_count,
                        "share_count": share_count,
                        "collect_count": collect_count,
                        "author": author_obj.get("nickname", channel_info["nickname"]),
                        "create_time": item.get("create_time", int(time.time()))
                    }


                    seen_aweme_ids.add(aweme_id)
                    collected_videos.append(video_item)
                    new_added += 1
                return new_added

            # Lắng nghe Network Response của Douyin Post API
            def on_response(response):
                try:
                    if "/aweme/v1/web/aweme/post/" in response.url or ("post" in response.url and "aweme" in response.url):
                        res_json = response.json()
                        aweme_list = res_json.get("aweme_list", []) or []
                        pagination_state["last_url"] = response.url
                        pagination_state["max_cursor"] = res_json.get("max_cursor", 0)
                        pagination_state["has_more"] = res_json.get("has_more", 0)
                        process_aweme_list(aweme_list)
                except Exception:
                    pass

            page.on("response", on_response)

            if progress_cb: progress_cb(20, "Đang nạp cấu trúc kênh & phân tích video...")
            try:
                page.goto(profile_url, timeout=25000, wait_until="domcontentloaded")
            except Exception:
                pass

            time.sleep(2)

            # Tự động đóng popup đăng nhập / QR nếu có
            try:
                page.keyboard.press("Escape")
                page.mouse.click(962, 198)
                page.evaluate("""() => {
                    const closeBtns = document.querySelectorAll('[class*="close"], [class*="login-mask"] svg, .YoNA2Hyj, .dy-account-close');
                    closeBtns.forEach(b => { try { b.click(); } catch(e){} });
                }""")
            except Exception:
                pass

            # Đưa con trỏ chuột vào giữa vùng nội dung video
            try:
                page.mouse.move(640, 450)
            except Exception:
                pass

            # Vòng lặp cuộn trang Human-like & trigger đa tầng
            max_scrolls = 80 if limit is None or limit > 50 else math.ceil(limit / 8) + 12
            no_new_count = 0
            prev_len = len(collected_videos)

            for scroll_idx in range(max_scrolls):
                current_count = len(collected_videos)
                if limit and current_count >= limit:
                    break

                pct = 25 + int((scroll_idx + 1) / max_scrolls * 65)
                if progress_cb:
                    channel_name_str = f" từ kênh [{channel_info['nickname']}]" if channel_info.get("nickname") and channel_info["nickname"] != "Kênh Douyin" else ""
                    progress_cb(pct, f"Đang phân tích danh sách{channel_name_str}... Đã tìm thấy {current_count} video.")

                # Kích hoạt sự kiện cuộn đa tầng đồng bộ trên các container nội dung của Douyin & gỡ bỏ lớp chặn
                try:
                    # 1. Gỡ bỏ popup login/mask và cuộn DOM
                    page.evaluate("""() => {
                        // Gỡ bỏ mọi modal login hoặc lớp mask làm chặn sự kiện cuộn
                        const blockers = document.querySelectorAll('[class*="login-mask"], [class*="login-guide"], [class*="semi-modal"], [class*="YoNA2Hyj"], [class*="dy-account-close"]');
                        blockers.forEach(b => {
                            try { b.click(); } catch(e){}
                            try { b.remove(); } catch(e){}
                        });
                        document.body.style.overflow = 'auto';
                        document.documentElement.style.overflow = 'auto';

                        // Kích hoạt sự kiện cuộn trên toàn bộ các container tiềm năng
                        const containers = document.querySelectorAll('.route-scroll-container, [class*="route-scroll-container"], [class*="parent-route-container"], [data-e2e="user-post-list"], #slidelist');
                        containers.forEach(c => {
                            c.scrollTop += 3200;
                            c.dispatchEvent(new Event('scroll', { bubbles: true }));
                        });
                        window.scrollBy(0, 3200);
                        window.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }""")
                    
                    # 2. Giả lập chuột lăn tự nhiên tại nhiều vị trí
                    jitter_x = 640 + random.randint(-60, 60)
                    jitter_y = 520 + random.randint(-60, 60)
                    page.mouse.move(jitter_x, jitter_y)
                    page.mouse.wheel(0, 3200 + random.randint(-200, 500))
                    
                    # 3. Giả lập phím PageDown & End
                    if scroll_idx % 2 == 0:
                        page.keyboard.press("PageDown")
                    else:
                        page.keyboard.press("End")
                except Exception:
                    pass

                time.sleep(1.3 + random.uniform(0.2, 0.4))

                # Kiểm tra nếu không có video nào sau 6 lượt cuộn đầu tiên -> Dừng sớm
                if current_count == 0 and scroll_idx >= 6:
                    break

                if len(collected_videos) == prev_len:
                    no_new_count += 1
                    if no_new_count >= 2:
                        # Cuộn ngược nhẹ rồi cuộn mạnh xuống đáy để ép Douyin kích hoạt Infinite Pagination
                        try:
                            page.evaluate("""() => {
                                const containers = document.querySelectorAll('.route-scroll-container, [class*="route-scroll-container"], [class*="parent-route-container"], [data-e2e="user-post-list"]');
                                containers.forEach(c => {
                                    c.scrollTop -= 1000;
                                    c.dispatchEvent(new Event('scroll', { bubbles: true }));
                                });
                                window.scrollBy(0, -1000);
                            }""")
                            time.sleep(0.4)
                            page.evaluate("""() => {
                                const containers = document.querySelectorAll('.route-scroll-container, [class*="route-scroll-container"], [class*="parent-route-container"], [data-e2e="user-post-list"]');
                                containers.forEach(c => {
                                    c.scrollTop = c.scrollHeight;
                                    c.dispatchEvent(new Event('scroll', { bubbles: true }));
                                });
                                window.scrollTo(0, document.body.scrollHeight);
                                window.dispatchEvent(new Event('scroll', { bubbles: true }));
                            }""")
                            page.mouse.click(640, 500)
                            page.mouse.wheel(0, 4500)
                            page.keyboard.press("End")
                            time.sleep(1.2)
                        except Exception:
                            pass
                        if len(collected_videos) == prev_len and no_new_count >= 5:
                            break
                else:
                    no_new_count = 0
                    prev_len = len(collected_videos)

            # --- GIAI ĐOẠN 2: QUÉT CÁC BỘ SƯU TẬP (合集 - COLLECTIONS / MIXES) CỦA KÊNH ---
            if (limit is None or len(collected_videos) < limit):
                if progress_cb: progress_cb(75, "Đang quét thêm các Bộ sưu tập (合集) và Tuyển tập video của kênh...")
                try:
                    # Chuyển sang tab 合集 và tìm danh sách ID bộ sưu tập
                    mix_ids = page.evaluate("""async () => {
                        const allTabs = Array.from(document.querySelectorAll('div, span, button'));
                        const hejiTab = allTabs.find(el => el.innerText && el.innerText.trim() === '合集' && el.className.includes('semi-tabs-tab'));
                        if (hejiTab) hejiTab.click();
                        await new Promise(r => setTimeout(r, 1800));

                        const links = Array.from(document.querySelectorAll('a[href*="collection"], a[href*="mix"], [class*="mix"] a')).map(a => a.href);
                        const ids = [];
                        links.forEach(l => {
                            const m = l.match(/collection\\/(\\d+)/) || l.match(/mix_id=(\\d+)/);
                            if (m && !ids.includes(m[1])) ids.push(m[1]);
                        });
                        return ids;
                    }""") or []

                    if mix_ids:
                        for m_idx, m_id in enumerate(mix_ids):
                            if limit and len(collected_videos) >= limit:
                                break
                            cur_cursor = 0
                            cur_has_more = 1
                            while cur_has_more:
                                if limit and len(collected_videos) >= limit:
                                    break
                                if progress_cb:
                                    progress_cb(80 + int((m_idx + 1) / len(mix_ids) * 15), f"Đang trích xuất Bộ sưu tập {m_idx + 1}/{len(mix_ids)}... (Hiện có {len(collected_videos)} video)")

                                mix_data = page.evaluate(f"""async () => {{
                                    try {{
                                        const res = await window.fetch('/aweme/v1/web/mix/aweme/?device_platform=webapp&aid=6383&channel=channel_pc_web&mix_id={m_id}&cursor={cur_cursor}&count=20');
                                        return await res.json();
                                    }} catch(e) {{ return null; }}
                                }}""")
                                if not mix_data or not isinstance(mix_data, dict):
                                    break
                                aweme_list = mix_data.get("aweme_list") or []
                                if not aweme_list:
                                    break
                                process_aweme_list(aweme_list)
                                cur_cursor = mix_data.get("cursor", 0)
                                cur_has_more = int(mix_data.get("has_more", 0) or 0)
                                time.sleep(0.3)
                except Exception:
                    pass

            context.close()

        if not collected_videos:
            raise Exception("Không tìm thấy video nào từ kênh này (kênh có thể để chế độ riêng tư, chưa có video hoặc đường dẫn không hợp lệ).")

        # Giới hạn số lượng nếu có yêu cầu
        if limit and len(collected_videos) > limit:
            collected_videos = collected_videos[:limit]

        channel_info["total_videos_scanned"] = len(collected_videos)
        if progress_cb: progress_cb(100, f"Hoàn tất phân tích! Đã trích xuất thành công {len(collected_videos)} video từ kênh {channel_info['nickname']}.")

        return {
            "success": True,
            "channel_info": channel_info,
            "videos": collected_videos,
            "total": len(collected_videos)
        }

    def scan_collection_videos(self, mix_id_or_url, limit=None, progress_cb=None):
        """
        Trích xuất toàn bộ video thuộc một Bộ sưu tập (合集 / Collection / Mix) cụ thể của Douyin.
        Phân trang liên tục bằng cursor và has_more == 1 cho tới khi has_more == 0.
        Bảo toàn thứ tự mix_order của các tập để phục vụ ghép video dài.
        """
        mix_id = extract_mix_id(mix_id_or_url)
        if not mix_id:
            raise ValueError(f"Không nhận diện được mix_id từ liên kết: {mix_id_or_url}")

        if progress_cb: progress_cb(10, f"Đang kết nối để phân tích Bộ sưu tập (Mix ID: {mix_id})...")

        target_url = f"https://www.douyin.com/collection/{mix_id}"
        from playwright.sync_api import sync_playwright

        collected_videos = []
        seen_aweme_ids = set()
        channel_info = {
            "nickname": f"Tuyển tập {mix_id}",
            "avatar": "",
            "signature": "",
            "follower_count": 0,
            "total_favorited": 0,
            "mix_id": mix_id,
            "is_collection": True
        }

        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    channel="msedge",
                    headless=self.headless,
                    viewport={"width": 1280, "height": 800},
                    user_agent=DEFAULT_USER_AGENT,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
            except Exception:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=self.headless,
                    viewport={"width": 1280, "height": 800},
                    user_agent=DEFAULT_USER_AGENT,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )

            page = context.pages[0] if context.pages else context.new_page()

            def process_mix_items(items):
                import downloader
                new_added = 0
                for item in items:
                    aid = str(item.get("aweme_id") or "")
                    if not aid or aid in seen_aweme_ids:
                        continue
                    desc = str(item.get("desc") or "Video Douyin").strip()
                    video_obj = item.get("video") or {}
                    cover_list = ((video_obj.get("cover") or {}).get("url_list") or
                                  (video_obj.get("origin_cover") or {}).get("url_list") or [])
                    cover_url = cover_list[0] if cover_list else ""

                    variants = downloader.resolve_douyin_variants(item, aweme_id=aid)
                    play_url = variants[0]["url"] if variants else ""
                    backup_urls = variants[0].get("backup_urls", []) if variants else []
                    is_clean = variants[0].get("is_clean", False) if variants else False

                    is_images = bool(item.get("images") or item.get("aweme_type") == 68)
                    image_urls = []
                    if is_images:
                        for img_obj in (item.get("images") or []):
                            u_list = img_obj.get("url_list") or []
                            if u_list: image_urls.append(u_list[-1])
                        if not cover_url and image_urls: cover_url = image_urls[0]

                    dur_ms = int(video_obj.get("duration") or 0)
                    dur_sec = dur_ms // 1000 if dur_ms > 1000 else dur_ms
                    stats = item.get("statistics") or {}
                    author_obj = item.get("author") or {}
                    if author_obj.get("nickname") and channel_info["nickname"].startswith("Tuyển tập"):
                        channel_info["nickname"] = author_obj.get("nickname")
                        channel_info["avatar"] = ((author_obj.get("avatar_thumb") or {}).get("url_list") or [""])[0]

                    mix_info = item.get("mix_info") or {}
                    mix_order = item.get("_mix_order") or mix_info.get("mix_order") or mix_info.get("episode_number") or (len(collected_videos) + 1)
                    if mix_info.get("mix_name") and "mix_name" not in channel_info:
                        channel_info["mix_name"] = mix_info.get("mix_name")

                    collected_videos.append({
                        "aweme_id": aid,
                        "title": desc,
                        "clean_title": downloader.sanitize_filename_windows(desc),
                        "url": f"https://www.douyin.com/video/{aid}",
                        "download_url": play_url,
                        "backup_urls": backup_urls,
                        "is_clean": is_clean,
                        "variants": variants,
                        "mix_order": mix_order,
                        "mix_id": mix_id,
                        "cover_url": cover_url,
                        "is_images": is_images,
                        "image_urls": image_urls,
                        "duration": dur_sec,
                        "duration_formatted": f"{dur_sec // 60:02d}:{dur_sec % 60:02d}",
                        "digg_count": stats.get("digg_count", 0),
                        "comment_count": stats.get("comment_count", 0),
                        "author": author_obj.get("nickname", channel_info["nickname"]),
                        "create_time": item.get("create_time", int(time.time()))
                    })
                    seen_aweme_ids.add(aid)
                    new_added += 1
                return new_added

            try:
                page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(1.5)
            except Exception:
                pass

            cursor = 0
            has_more = 1
            page_idx = 0

            while has_more:
                if limit and len(collected_videos) >= limit:
                    break
                page_idx += 1
                if progress_cb:
                    progress_cb(min(95, 20 + page_idx * 5), f"Đang phân trang Bộ sưu tập: trang {page_idx} (Đã tìm thấy {len(collected_videos)} tập)...")

                mix_data = page.evaluate(f"""async () => {{
                    try {{
                        const res = await window.fetch('/aweme/v1/web/mix/aweme/?device_platform=webapp&aid=6383&channel=channel_pc_web&mix_id={mix_id}&cursor={cursor}&count=20');
                        return await res.json();
                    }} catch(e) {{ return null; }}
                }}""")

                if not mix_data or not isinstance(mix_data, dict):
                    break
                aweme_list = mix_data.get("aweme_list") or []
                if not aweme_list:
                    break

                process_mix_items(aweme_list)
                cursor = mix_data.get("cursor", 0)
                has_more = int(mix_data.get("has_more", 0) or 0)
                time.sleep(0.4)

            context.close()

        if not collected_videos:
            raise Exception(f"Không tìm thấy tập nào trong Bộ sưu tập ID {mix_id}.")

        collected_videos.sort(key=lambda x: int(x.get("mix_order") or 999999))
        channel_info["total_videos_scanned"] = len(collected_videos)
        if progress_cb:
            progress_cb(100, f"Hoàn tất! Đã trích xuất {len(collected_videos)} tập từ Bộ sưu tập.")

        return {
            "success": True,
            "channel_info": channel_info,
            "videos": collected_videos,
            "total": len(collected_videos)
        }


    def get_single_video_info(self, video_url_or_id):
        """
        Trích xuất thông tin và link MP4 không logo chất lượng cao nhất cho 1 video Douyin lẻ.
        Sử dụng cơ chế 2 tầng: Tầng 1 (Fast SSR) -> Tầng 2 (Browser Network Sniffer).
        """
        vid, resolved_url = extract_video_id(video_url_or_id)
        if not vid:
            resolved_url = resolve_redirect_url(video_url_or_id)
            vid, _ = extract_video_id(resolved_url)

        target_url = f"https://www.douyin.com/video/{vid}" if vid else resolved_url

        # Tầng 1: Thử cào nhanh qua requests SSR
        try:
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.douyin.com/"
            }
            res = requests.get(target_url, headers=headers, timeout=8)
            if res.status_code == 200 and ("__UNIVERSAL_DATA_FOR_REHYDRATION__" in res.text or "RENDER_DATA" in res.text):
                import downloader
                detail = downloader._extract_aweme_detail_from_html(res.text)
                if detail:
                    variants = downloader.resolve_douyin_variants(detail, aweme_id=vid)
                    if variants:
                        best = variants[0]
                        desc = str(detail.get("desc") or "Douyin Video").strip()
                        video_obj = detail.get("video") or {}
                        duration_ms = int(video_obj.get("duration") or 0)
                        duration_sec = duration_ms // 1000 if duration_ms > 1000 else duration_ms
                        return {
                            "success": True,
                            "video_id": vid,
                            "title": desc,
                            "clean_title": downloader.sanitize_filename_windows(desc),
                            "download_url": best["url"],
                            "is_clean": best.get("is_clean", False),
                            "quality": best.get("quality", "1080p"),
                            "backup_urls": [v["url"] for v in variants[1:]],
                            "duration": duration_sec,
                            "duration_formatted": f"{duration_sec // 60:02d}:{duration_sec % 60:02d}",
                            "cover_url": ((video_obj.get("cover") or {}).get("url_list") or [""])[0],
                            "author": (detail.get("author") or {}).get("nickname", "Douyin Creator")
                        }
        except Exception:
            pass

        # Tầng 2: Sử dụng Browser Worker bắt luồng video trực tiếp
        from playwright.sync_api import sync_playwright
        captured_data = {}

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="msedge",
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
                user_agent=DEFAULT_USER_AGENT,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            page = context.pages[0] if context.pages else context.new_page()

            def block_heavy_assets(route):
                req = route.request
                rtype = req.resource_type
                rurl = req.url
                if rtype in ["image", "font", "stylesheet"] or any(x in rurl for x in ["bytead", "analytics", "report", "sentry", "log", "pstatp"]):
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", block_heavy_assets)

            def on_res(response):
                try:
                    if any(x in response.url for x in ["/aweme/v1/web/aweme/detail/", "/aweme/v1/web/tab/feed/", "/aweme/v1/web/item/detail/"]):
                        j = response.json()
                        aweme_detail = j.get("aweme_detail")
                        if not aweme_detail and j.get("aweme_list"):
                            for itm in j.get("aweme_list", []):
                                if str(itm.get("aweme_id") or "") == str(vid):
                                    aweme_detail = itm
                                    break
                            if not aweme_detail and j.get("aweme_list"):
                                aweme_detail = j["aweme_list"][0]

                        if aweme_detail:
                            import downloader
                            variants = downloader.resolve_douyin_variants(aweme_detail, aweme_id=vid)
                            v_obj = aweme_detail.get("video") or {}
                            if variants:
                                best = variants[0]
                                captured_data["download_url"] = best["url"]
                                captured_data["is_clean"] = best.get("is_clean", False)
                                captured_data["backup_urls"] = [v["url"] for v in variants[1:]]
                                captured_data["quality"] = best.get("quality", "1080p")
                            else:
                                p_list = (v_obj.get("play_addr") or {}).get("url_list") or []
                                if p_list:
                                    captured_data["download_url"] = p_list[0]
                            captured_data["title"] = aweme_detail.get("desc", "")
                            captured_data["author"] = (aweme_detail.get("author") or {}).get("nickname", "")
                            captured_data["cover_url"] = ((v_obj.get("cover") or {}).get("url_list") or [""])[0]
                            dur = int(v_obj.get("duration") or 0)
                            captured_data["duration"] = dur // 1000 if dur > 1000 else dur
                    elif "douyinvod.com" in response.url and not captured_data.get("download_url"):
                        if response.status in [200, 206]:
                            captured_data["download_url"] = response.url
                except Exception:
                    pass

            page.on("response", on_res)

            try:
                page.goto(target_url, timeout=12000, wait_until="commit")
                for _ in range(15):
                    if captured_data.get("download_url"):
                        break
                    time.sleep(0.15)
            except Exception:
                pass

            if not captured_data.get("title"):
                captured_data["title"] = page.title()

            context.close()

        if not captured_data.get("download_url"):
            raise Exception("Không thể lấy link tải video Douyin. Vui lòng kiểm tra lại link video.")

        title = captured_data.get("title") or f"Douyin_Video_{vid or int(time.time())}"
        dur_sec = captured_data.get("duration", 0)

        import downloader
        return {
            "success": True,
            "video_id": vid,
            "title": title,
            "clean_title": downloader.sanitize_filename_windows(title),
            "download_url": captured_data["download_url"],
            "is_clean": captured_data.get("is_clean", False),
            "backup_urls": captured_data.get("backup_urls", []),
            "quality": captured_data.get("quality", "1080p"),
            "duration": dur_sec,
            "duration_formatted": f"{dur_sec // 60:02d}:{dur_sec % 60:02d}",
            "cover_url": captured_data.get("cover_url", ""),
            "author": captured_data.get("author", "Douyin Creator")
        }


def download_stream_file(video_url, output_path, progress_cb=None, num_threads=4, aweme_id=None, backup_urls=None, cancel_event=None, connection_pool=None):
    """
    Tải file video MP4 từ URL trực tiếp qua ResumableRangeDownloader (hỗ trợ HTTP 206, resume qua manifest, refresh URL 403/410, và connection pool).
    """
    import downloader
    downloader_instance = downloader.ResumableRangeDownloader(
        url=video_url,
        output_path=output_path,
        num_connections=num_threads,
        aweme_id=aweme_id,
        backup_urls=backup_urls,
        progress_callback=progress_cb,
        cancel_event=cancel_event,
        connection_pool=connection_pool
    )
    return downloader_instance.download()


BATCH_CANCEL_EVENT = threading.Event()

def cancel_active_batch_download():
    """Kích hoạt cờ hủy tải hàng loạt."""
    BATCH_CANCEL_EVENT.set()
    return True

def reset_batch_cancel_event():
    """Xóa cờ hủy tải."""
    BATCH_CANCEL_EVENT.clear()


def download_channel_batch(video_list, output_dir=None, channel_name=None, max_workers=3, connections_per_file=2, prefix_index=True, auto_merge=False, merge_mode="auto", progress_cb=None):
    """
    Tải hàng loạt danh sách video Douyin qua ThreadPoolExecutor với GlobalConnectionPool,
    hỗ trợ resume qua batch_manifest.json, Windows-safe filename, và tự động gộp tập (auto_merge).
    """
    reset_batch_cancel_event()

    if not output_dir:
        output_dir = DOWNLOAD_DIR
        
    import downloader
    if channel_name:
        clean_ch_name = downloader.sanitize_filename_windows(channel_name, max_len=60)
        output_dir = os.path.join(output_dir, f"Douyin_{clean_ch_name}")

    os.makedirs(output_dir, exist_ok=True)

    manifest_path = os.path.join(output_dir, "batch_manifest.json")
    manifest = {
        "channel_name": channel_name,
        "total_count": len(video_list),
        "created_at": time.time(),
        "items": {}
    }
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                old_m = json.load(mf)
                if isinstance(old_m, dict) and "items" in old_m:
                    manifest["items"] = old_m["items"]
        except Exception:
            pass

    max_total_conn = max(4, min(12, max_workers * connections_per_file))
    conn_pool = GlobalConnectionPool(max_total_connections=max_total_conn)

    total_count = len(video_list)
    results = []
    completed_count = 0
    lock = threading.Lock()

    def save_batch_manifest():
        with lock:
            try:
                with open(manifest_path, "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _worker(idx, video_info):
        nonlocal completed_count
        if BATCH_CANCEL_EVENT.is_set():
            return None

        vid_id = str(video_info.get("aweme_id") or f"vid_{idx}")
        title = video_info.get("title") or video_info.get("clean_title") or f"video_{vid_id}"

        # Kiểm tra manifest đã thành công chưa
        if vid_id in manifest["items"] and manifest["items"][vid_id].get("status") == "success":
            saved_f = manifest["items"][vid_id].get("file_path")
            if saved_f and os.path.exists(saved_f) and os.path.getsize(saved_f) > 100000:
                with lock:
                    completed_count += 1
                    if progress_cb:
                        progress_cb(completed_count, total_count, video_info, saved_f, "existed")
                return saved_f

        # 1. Nếu là Album Ảnh / Slide Photo Note
        if video_info.get("is_images") and video_info.get("image_urls"):
            prefix_str = f"{idx+1:03d}_" if prefix_index else ""
            album_dir_name = f"{prefix_str}{downloader.sanitize_filename_windows(title, max_len=60)}_Album"
            album_path = os.path.join(output_dir, album_dir_name)
            os.makedirs(album_path, exist_ok=True)
            
            img_urls = video_info.get("image_urls") or []
            saved_images = []
            for img_idx, img_u in enumerate(img_urls):
                if BATCH_CANCEL_EVENT.is_set():
                    break
                img_file_path = os.path.join(album_path, f"photo_{img_idx+1:02d}.jpg")
                if not os.path.exists(img_file_path):
                    try:
                        r = requests.get(img_u, headers={"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=12)
                        if r.status_code == 200:
                            with open(img_file_path, 'wb') as im_f:
                                im_f.write(r.content)
                            saved_images.append(img_file_path)
                    except Exception:
                        pass
                else:
                    saved_images.append(img_file_path)

            with lock:
                completed_count += 1
                manifest["items"][vid_id] = {
                    "status": "success",
                    "file_path": album_path,
                    "type": "album",
                    "title": title
                }
                save_batch_manifest()
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, album_path, "album_success")
            return album_path

        # 2. Nếu là Video MP4
        prefix = (idx + 1) if prefix_index else None
        file_path = downloader.resolve_unique_filename(output_dir, title, ext='mp4', prefix_index=prefix)

        # Tránh tải lại nếu file đã tồn tại và đủ dung lượng
        if os.path.exists(file_path) and os.path.getsize(file_path) > 100000:
            with lock:
                completed_count += 1
                manifest["items"][vid_id] = {
                    "status": "success",
                    "file_path": file_path,
                    "type": "video",
                    "title": title
                }
                save_batch_manifest()
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, file_path, "existed")
            return file_path

        # Lấy URL tải trực tiếp
        dl_url = video_info.get("download_url")
        backup_urls = video_info.get("backup_urls", [])
        if not dl_url:
            try:
                crawler = DouyinBrowserDownloader()
                single_info = crawler.get_single_video_info(video_info.get("url") or vid_id)
                dl_url = single_info.get("download_url")
                backup_urls = single_info.get("backup_urls", [])
            except Exception:
                pass

        if not dl_url or BATCH_CANCEL_EVENT.is_set():
            with lock:
                manifest["items"][vid_id] = {
                    "status": "failed",
                    "error": "No download URL found",
                    "title": title
                }
                save_batch_manifest()
            return None

        # Tải stream video với ResumableRangeDownloader
        time.sleep(random.uniform(0.1, 0.4))
        try:
            download_stream_file(
                video_url=dl_url,
                output_path=file_path,
                num_threads=connections_per_file,
                aweme_id=vid_id,
                backup_urls=backup_urls,
                cancel_event=BATCH_CANCEL_EVENT,
                connection_pool=conn_pool
            )
            if BATCH_CANCEL_EVENT.is_set():
                if os.path.exists(file_path):
                    try: os.remove(file_path)
                    except Exception: pass
                return None

            with lock:
                completed_count += 1
                manifest["items"][vid_id] = {
                    "status": "success",
                    "file_path": file_path,
                    "type": "video",
                    "title": title
                }
                save_batch_manifest()
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, file_path, "success")
            return file_path
        except Exception as e:
            with lock:
                manifest["items"][vid_id] = {
                    "status": "failed",
                    "error": str(e),
                    "title": title
                }
                save_batch_manifest()
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, None, f"error: {str(e)}")
            return None

    workers_num = max(1, min(max_workers, 6))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_num) as executor:
        futures = {executor.submit(_worker, i, v): i for i, v in enumerate(video_list)}
        for f in concurrent.futures.as_completed(futures):
            if BATCH_CANCEL_EVENT.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            res = f.result()
            if res:
                results.append(res)

    # Tự động gộp tập nếu auto_merge=True
    merged_result_file = None
    if auto_merge and not BATCH_CANCEL_EVENT.is_set():
        ordered_files = []
        for v in video_list:
            v_id = str(v.get("aweme_id") or "")
            item_data = manifest.get("items", {}).get(v_id, {})
            fp = item_data.get("file_path")
            if fp and os.path.exists(fp) and fp.lower().endswith(".mp4"):
                ordered_files.append(fp)

        if len(ordered_files) > 1:
            try:
                if progress_cb:
                    progress_cb(completed_count, total_count, {}, None, "Đang ghép nối các tập video...")
                merged_name = f"Merged_{downloader.sanitize_filename_windows(channel_name or 'Collection', max_len=60)}.mp4"
                merged_path = os.path.join(output_dir, merged_name)
                merged_result_file = downloader.merge_collection_episodes(ordered_files, merged_path, merge_mode=merge_mode)
            except Exception as me:
                print(f"[Douyin Merge Error]: {me}")

    return {
        "downloaded_files": results,
        "total": len(results),
        "merged_file": merged_result_file,
        "manifest_path": manifest_path
    }


def retry_failed_batch_items(manifest_path_or_dir, max_workers=2, connections_per_file=2, progress_cb=None):
    """
    Đọc manifest và tải lại các video bị thất bại trong lần chạy trước.
    """
    if os.path.isdir(manifest_path_or_dir):
        manifest_path = os.path.join(manifest_path_or_dir, "batch_manifest.json")
    else:
        manifest_path = manifest_path_or_dir

    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Không tìm thấy manifest tại {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    failed_items = []
    output_dir = os.path.dirname(manifest_path)

    for aweme_id, item in manifest.get("items", {}).items():
        if item.get("status") == "failed":
            failed_items.append({
                "aweme_id": aweme_id,
                "title": item.get("title", f"video_{aweme_id}"),
                "clean_title": item.get("title", f"video_{aweme_id}"),
                "url": f"https://www.douyin.com/video/{aweme_id}"
            })

    if not failed_items:
        return {"retried": 0, "message": "Không có video lỗi cần tải lại."}

    return download_channel_batch(
        failed_items,
        output_dir=output_dir,
        channel_name=manifest.get("channel_name"),
        max_workers=max_workers,
        connections_per_file=connections_per_file,
        progress_cb=progress_cb
    )

