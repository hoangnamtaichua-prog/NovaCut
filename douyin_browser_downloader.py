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
        Cào danh sách video từ 1 kênh Douyin bằng cách lắng nghe API /aweme/v1/web/aweme/post/.
        Hỗ trợ phân trang tự động bằng cách cuộn chuột ảo.
        """
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

                    # Direct MP4 URL (Trích xuất luồng 1080p/Bitrate cao nhất)
                    play_url = ""
                    bit_rate_list = video_obj.get("bit_rate") or []
                    if bit_rate_list and isinstance(bit_rate_list, list):
                        try:
                            # Sắp xếp theo bitrate giảm dần để lấy chất lượng cao nhất
                            bit_rate_sorted = sorted(bit_rate_list, key=lambda b: int(b.get("bit_rate") or 0), reverse=True)
                            for b_item in bit_rate_sorted:
                                p_addrs = (b_item.get("play_addr") or {}).get("url_list") or []
                                if p_addrs:
                                    play_url = p_addrs[-1].replace("playwm", "play")
                                    break
                        except Exception:
                            pass

                    if not play_url:
                        play_addr_list = (video_obj.get("play_addr") or {}).get("url_list") or []
                        if play_addr_list:
                            play_url = play_addr_list[-1].replace("playwm", "play")

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

                    video_item = {
                        "aweme_id": aweme_id,
                        "title": desc,
                        "clean_title": sanitize_filename(desc),
                        "url": f"https://www.douyin.com/video/{aweme_id}",
                        "download_url": play_url,
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
                            if progress_cb:
                                progress_cb(80 + int((m_idx + 1) / len(mix_ids) * 15), f"Đang trích xuất Bộ sưu tập {m_idx + 1}/{len(mix_ids)}... (Hiện có {len(collected_videos)} video)")
                            
                            mix_data = page.evaluate(f"""async () => {{
                                try {{
                                    const res = await window.fetch('/aweme/v1/web/mix/aweme/?device_platform=webapp&aid=6383&channel=channel_pc_web&mix_id={m_id}&cursor=0&count=50');
                                    return await res.json();
                                }} catch(e) {{ return null; }}
                            }}""")
                            if mix_data and mix_data.get("aweme_list"):
                                process_aweme_list(mix_data["aweme_list"])
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

    def get_single_video_info(self, video_url_or_id):
        """
        Trích xuất thông tin và link MP4 không logo cho 1 video Douyin lẻ.
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
                    video_obj = detail.get("video") or {}
                    play_addr_list = (video_obj.get("play_addr") or {}).get("url_list") or []
                    if play_addr_list:
                        play_url = play_addr_list[-1].replace("playwm", "play")
                        desc = str(detail.get("desc") or "Douyin Video").strip()
                        duration_ms = int(video_obj.get("duration") or 0)
                        duration_sec = duration_ms // 1000 if duration_ms > 1000 else duration_ms
                        return {
                            "success": True,
                            "video_id": vid,
                            "title": desc,
                            "clean_title": sanitize_filename(desc),
                            "download_url": play_url,
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

            # Chặn toàn bộ ảnh, font, css, trackers để tải trang trong 1 - 2s
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
                    # Bắt API aweme/detail, tab/feed hoặc video stream .douyinvod.com
                    if any(x in response.url for x in ["/aweme/v1/web/aweme/detail/", "/aweme/v1/web/tab/feed/", "/aweme/v1/web/item/detail/"]):
                        j = response.json()
                        aweme_detail = j.get("aweme_detail")
                        if not aweme_detail and j.get("aweme_list"):
                            # Nếu là feed chứa danh sách, tìm đúng video có ID trùng khớp vid
                            for itm in j.get("aweme_list", []):
                                if str(itm.get("aweme_id") or "") == str(vid):
                                    aweme_detail = itm
                                    break
                            if not aweme_detail and j.get("aweme_list"):
                                aweme_detail = j["aweme_list"][0]

                        if aweme_detail:
                            v_obj = aweme_detail.get("video") or {}
                            p_list = (v_obj.get("play_addr") or {}).get("url_list") or []
                            if p_list:
                                captured_data["download_url"] = p_list[-1].replace("playwm", "play")
                                captured_data["title"] = aweme_detail.get("desc", "")
                                captured_data["author"] = (aweme_detail.get("author") or {}).get("nickname", "")
                                captured_data["cover_url"] = ((v_obj.get("cover") or {}).get("url_list") or [""])[0]
                                dur = int(v_obj.get("duration") or 0)
                                captured_data["duration"] = dur // 1000 if dur > 1000 else dur
                    elif "douyinvod.com" in response.url and not captured_data.get("download_url"):
                        if response.status == 200 or response.status == 206:
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

        return {
            "success": True,
            "video_id": vid,
            "title": title,
            "clean_title": sanitize_filename(title),
            "download_url": captured_data["download_url"],
            "duration": dur_sec,
            "duration_formatted": f"{dur_sec // 60:02d}:{dur_sec % 60:02d}",
            "cover_url": captured_data.get("cover_url", ""),
            "author": captured_data.get("author", "Douyin Creator")
        }


def download_stream_file(video_url, output_path, progress_cb=None, num_threads=4):
    """
    Tải file video MP4 từ URL trực tiếp qua Multi-Connection Range Downloader (IDM Standard 4 luồng).
    Tự động fallback về đơn luồng nếu server không hỗ trợ Range.
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*"
    }

    session = requests.Session()
    total_size = 0
    accept_ranges = False

    try:
        head_res = session.head(video_url, headers=headers, allow_redirects=True, timeout=10)
        if head_res.status_code in [200, 206]:
            total_size = int(head_res.headers.get("content-length", 0))
            accept_ranges = 'bytes' in head_res.headers.get('accept-ranges', '').lower() or head_res.status_code == 206
    except Exception:
        pass

    if not total_size:
        try:
            test_res = session.get(video_url, headers={**headers, 'Range': 'bytes=0-1'}, stream=True, timeout=8)
            if test_res.status_code == 206:
                accept_ranges = True
                cr = test_res.headers.get('content-range', '')
                if '/' in cr:
                    total_size = int(cr.split('/')[-1])
        except Exception:
            pass

    part_path = output_path + ".part"

    # 1. Đa luồng Range nếu hỗ trợ và file > 2MB
    if accept_ranges and total_size > 2 * 1024 * 1024:
        threads_count = min(num_threads, 6)
        chunk_size_per_thread = total_size // threads_count
        ranges = []
        for i in range(threads_count):
            start = i * chunk_size_per_thread
            end = total_size - 1 if i == threads_count - 1 else (start + chunk_size_per_thread - 1)
            ranges.append((i, start, end))

        temp_files = [f"{part_path}.p{i}" for i in range(threads_count)]
        downloaded_bytes = [0] * threads_count
        lock = threading.Lock()
        t0 = time.time()
        last_cb_time = t0

        def _download_range(idx, start_byte, end_byte):
            nonlocal last_cb_time
            req_h = headers.copy()
            req_h['Range'] = f"bytes={start_byte}-{end_byte}"
            temp_f = temp_files[idx]

            with requests.get(video_url, headers=req_h, stream=True, timeout=25) as r:
                r.raise_for_status()
                with open(temp_f, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 512):
                        if chunk:
                            f.write(chunk)
                            with lock:
                                downloaded_bytes[idx] += len(chunk)
                                total_dl = sum(downloaded_bytes)
                                now = time.time()
                                if progress_cb and (now - last_cb_time >= 0.15 or total_dl >= total_size):
                                    last_cb_time = now
                                    pct = int(total_dl / total_size * 100) if total_size > 0 else 0
                                    el = now - t0
                                    spd = (total_dl / (1024 * 1024)) / (el + 1e-6)
                                    progress_cb(pct, total_dl, total_size, spd)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads_count) as executor:
                futures = [executor.submit(_download_range, r[0], r[1], r[2]) for r in ranges]
                concurrent.futures.wait(futures)
                for f in futures:
                    f.result()

            with open(output_path, 'wb') as out_f:
                for temp_f in temp_files:
                    if os.path.exists(temp_f):
                        with open(temp_f, 'rb') as in_f:
                            while True:
                                b = in_f.read(1024 * 1024 * 2)
                                if not b: break
                                out_f.write(b)
                        try: os.remove(temp_f)
                        except Exception: pass
            return output_path
        except Exception:
            for temp_f in temp_files:
                if os.path.exists(temp_f):
                    try: os.remove(temp_f)
                    except Exception: pass

    # 2. Fallback đơn luồng
    res = requests.get(video_url, headers=headers, stream=True, timeout=30)
    if res.status_code not in [200, 206]:
        raise Exception(f"Máy chủ Douyin trả về mã lỗi HTTP: {res.status_code}")

    total_size = int(res.headers.get("content-length", 0)) if not total_size else total_size
    downloaded = 0
    chunk_size = 1024 * 1024 # 1MB

    t0 = time.time()
    with open(output_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and progress_cb:
                    pct = int(downloaded / total_size * 100)
                    elapsed = time.time() - t0
                    speed = (downloaded / (1024 * 1024)) / (elapsed + 1e-6)
                    progress_cb(pct, downloaded, total_size, speed)

    return output_path


BATCH_CANCEL_EVENT = threading.Event()

def cancel_active_batch_download():
    """Kích hoạt cờ hủy tải hàng loạt."""
    BATCH_CANCEL_EVENT.set()
    return True

def reset_batch_cancel_event():
    """Xóa cờ hủy tải."""
    BATCH_CANCEL_EVENT.clear()


def download_channel_batch(video_list, output_dir=None, channel_name=None, max_workers=3, progress_cb=None):
    """
    Tải hàng loạt danh sách video Douyin qua ThreadPoolExecutor (2-4 workers) với cơ chế hủy tức thì.
    Hỗ trợ cả Video MP4 1080p và Album ảnh / Slide Photo Notes.
    """
    reset_batch_cancel_event()

    if not output_dir:
        output_dir = DOWNLOAD_DIR
        
    if channel_name:
        clean_ch_name = sanitize_filename(channel_name, max_len=50)
        output_dir = os.path.join(output_dir, f"Douyin_{clean_ch_name}")

    os.makedirs(output_dir, exist_ok=True)

    total_count = len(video_list)
    results = []
    completed_count = 0
    lock = threading.Lock()

    def _worker(idx, video_info):
        nonlocal completed_count
        if BATCH_CANCEL_EVENT.is_set():
            return None

        vid_id = video_info.get("aweme_id") or f"vid_{idx}"
        title = video_info.get("clean_title") or f"video_{vid_id}"

        # 1. Nếu là Album Ảnh / Slide Photo Note
        if video_info.get("is_images") and video_info.get("image_urls"):
            album_dir_name = f"{idx+1:03d}_{title}_Album"
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
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, album_path, "album_success")
            return album_path

        # 2. Nếu là Video MP4
        file_name = f"{idx+1:03d}_{title}.mp4"
        file_path = os.path.join(output_dir, file_name)

        # Tránh tải lại nếu file đã tồn tại và đủ dung lượng
        if os.path.exists(file_path) and os.path.getsize(file_path) > 100000:
            with lock:
                completed_count += 1
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, file_path, "existed")
            return file_path

        # Lấy URL tải trực tiếp
        dl_url = video_info.get("download_url")
        if not dl_url:
            try:
                crawler = DouyinBrowserDownloader()
                single_info = crawler.get_single_video_info(video_info.get("url") or vid_id)
                dl_url = single_info.get("download_url")
            except Exception:
                pass

        if not dl_url or BATCH_CANCEL_EVENT.is_set():
            return None

        # Tải stream video đa kết nối
        time.sleep(random.uniform(0.2, 0.6))
        try:
            download_stream_file(dl_url, file_path)
            if BATCH_CANCEL_EVENT.is_set():
                if os.path.exists(file_path):
                    try: os.remove(file_path)
                    except Exception: pass
                return None

            with lock:
                completed_count += 1
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, file_path, "success")
            return file_path
        except Exception as e:
            with lock:
                if progress_cb:
                    progress_cb(completed_count, total_count, video_info, None, f"error: {str(e)}")
            return None

    workers_num = max(1, min(max_workers, 4))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_num) as executor:
        futures = {executor.submit(_worker, i, v): i for i, v in enumerate(video_list)}
        for f in concurrent.futures.as_completed(futures):
            if BATCH_CANCEL_EVENT.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            res = f.result()
            if res:
                results.append(res)

    return results
