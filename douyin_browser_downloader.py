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
        res = requests.head(clean_url, headers=headers, allow_redirects=True, timeout=timeout)
        return res.url or clean_url
    except Exception:
        return clean_url


def extract_sec_uid(url_or_text):
    """Trích xuất sec_uid của kênh Douyin từ link profile hoặc link chia sẻ."""
    raw_url = clean_url_input(url_or_text)
    if not raw_url:
        return None, None
    
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

    def scan_channel_videos(self, channel_url_or_sec_uid, limit=30, progress_cb=None):
        """
        Cào danh sách video từ 1 kênh Douyin bằng cách lắng nghe API /aweme/v1/web/aweme/post/.
        Hỗ trợ phân trang tự động bằng cách cuộn chuột ảo.
        """
        sec_uid, resolved_url = extract_sec_uid(channel_url_or_sec_uid)
        if not sec_uid:
            # Thử giải mã nếu URL chứa video thay vì profile
            raise ValueError(f"Không tìm thấy sec_uid của kênh Douyin từ: {channel_url_or_sec_uid}")

        profile_url = f"https://www.douyin.com/user/{sec_uid}"
        if progress_cb: progress_cb(5, f"Đang kết nối tới kênh Douyin: {sec_uid[:15]}...")

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
            if progress_cb: progress_cb(10, "Đang khởi động trình duyệt ngầm (Microsoft Edge)...")
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="msedge",
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
                user_agent=DEFAULT_USER_AGENT,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
            )

            page = context.pages[0] if context.pages else context.new_page()

            # Lắng nghe Network Response của Douyin Post API
            def on_response(response):
                try:
                    if "/aweme/v1/web/aweme/post/" in response.url:
                        res_json = response.json()
                        aweme_list = res_json.get("aweme_list", []) or []
                        for item in aweme_list:
                            aweme_id = str(item.get("aweme_id") or item.get("id") or "")
                            if not aweme_id or aweme_id in seen_aweme_ids:
                                continue
                            
                            # Trích xuất thông tin video
                            desc = str(item.get("desc") or "Video Douyin").strip()
                            video_obj = item.get("video") or {}
                            
                            # Cover Thumbnail
                            cover_list = (
                                (video_obj.get("cover") or {}).get("url_list") or
                                (video_obj.get("origin_cover") or {}).get("url_list") or
                                (video_obj.get("dynamic_cover") or {}).get("url_list") or []
                            )
                            cover_url = cover_list[0] if cover_list else ""

                            # Direct MP4 URL
                            play_addr_list = (video_obj.get("play_addr") or {}).get("url_list") or []
                            # Ưu tiên link có định dạng mp4 chuẩn
                            play_url = ""
                            if play_addr_list:
                                play_url = play_addr_list[-1] # Thường link cuối là chất lượng cao nhất hoặc link gốc
                                if "playwm" in play_url:
                                    # Thay thế playwm (watermark) thành play (không logo)
                                    play_url = play_url.replace("playwm", "play")

                            duration_ms = int(video_obj.get("duration") or 0)
                            duration_sec = duration_ms // 1000 if duration_ms > 1000 else duration_ms

                            stats = item.get("statistics") or {}
                            digg_count = stats.get("digg_count", 0)
                            comment_count = stats.get("comment_count", 0)
                            share_count = stats.get("share_count", 0)

                            author_obj = item.get("author") or {}
                            if author_obj.get("nickname") and channel_info["nickname"] == "Kênh Douyin":
                                channel_info["nickname"] = author_obj.get("nickname")
                                channel_info["avatar"] = ((author_obj.get("avatar_thumb") or {}).get("url_list") or [""])[0]
                                channel_info["signature"] = author_obj.get("signature", "")

                            video_item = {
                                "aweme_id": aweme_id,
                                "title": desc,
                                "clean_title": sanitize_filename(desc),
                                "url": f"https://www.douyin.com/video/{aweme_id}",
                                "download_url": play_url,
                                "cover_url": cover_url,
                                "duration": duration_sec,
                                "duration_formatted": f"{duration_sec // 60:02d}:{duration_sec % 60:02d}",
                                "digg_count": digg_count,
                                "comment_count": comment_count,
                                "share_count": share_count,
                                "author": author_obj.get("nickname", channel_info["nickname"]),
                                "create_time": item.get("create_time", int(time.time()))
                            }

                            seen_aweme_ids.add(aweme_id)
                            collected_videos.append(video_item)
                except Exception:
                    pass

            page.on("response", on_response)

            if progress_cb: progress_cb(20, "Đang mở trang cá nhân của kênh trên Douyin...")
            try:
                page.goto(profile_url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                pass

            time.sleep(3)

            # Vòng lặp cuộn trang để bắt thêm các trang phân trang (pagination)
            max_scrolls = 40 if limit is None or limit > 50 else math.ceil(limit / 10) + 5
            no_new_count = 0
            prev_len = len(collected_videos)

            for scroll_idx in range(max_scrolls):
                current_count = len(collected_videos)
                if limit and current_count >= limit:
                    break

                pct = 25 + int((scroll_idx + 1) / max_scrolls * 65)
                if progress_cb:
                    progress_cb(pct, f"Đang quét danh sách video... Đã tìm thấy {current_count} video.")

                # Cuộn chuột xuống dưới
                page.mouse.wheel(0, 3000)
                time.sleep(1.8 + random.uniform(0.1, 0.4))

                if len(collected_videos) == prev_len:
                    no_new_count += 1
                    if no_new_count >= 3:
                        # Thử cuộn nhẹ lên rồi xuống lại
                        page.mouse.wheel(0, -500)
                        time.sleep(0.5)
                        page.mouse.wheel(0, 3500)
                        time.sleep(1.5)
                        if len(collected_videos) == prev_len and no_new_count >= 5:
                            break
                else:
                    no_new_count = 0
                    prev_len = len(collected_videos)

            context.close()

        # Giới hạn số lượng nếu có yêu cầu
        if limit and len(collected_videos) > limit:
            collected_videos = collected_videos[:limit]

        channel_info["total_videos_scanned"] = len(collected_videos)
        if progress_cb: progress_cb(100, f"Hoàn tất quét! Tìm thấy {len(collected_videos)} video từ kênh {channel_info['nickname']}.")

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

            def on_res(response):
                try:
                    # Bắt API aweme/detail hoặc video stream .douyinvod.com
                    if "/aweme/v1/web/aweme/detail/" in response.url:
                        j = response.json()
                        aweme_detail = j.get("aweme_detail") or {}
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
                page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
                time.sleep(3)
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


def download_stream_file(video_url, output_path, progress_cb=None):
    """
    Tải file video MP4 từ URL trực tiếp qua stream chunk (1MB) kèm header Referer.
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*"
    }

    res = requests.get(video_url, headers=headers, stream=True, timeout=30)
    if res.status_code not in [200, 206]:
        raise Exception(f"Máy chủ Douyin trả về mã lỗi HTTP: {res.status_code}")

    total_size = int(res.headers.get("content-length", 0))
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


def download_channel_batch(video_list, output_dir=None, max_workers=2, progress_cb=None):
    """
    Tải hàng loạt danh sách video Douyin qua ThreadPoolExecutor (2-3 workers).
    """
    if not output_dir:
        output_dir = DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    total_count = len(video_list)
    results = []
    completed_count = 0

    def _worker(idx, video_info):
        nonlocal completed_count
        vid_id = video_info.get("aweme_id") or f"vid_{idx}"
        title = video_info.get("clean_title") or f"video_{vid_id}"
        file_name = f"{idx+1:03d}_{title}.mp4"
        file_path = os.path.join(output_dir, file_name)

        # Tránh ghi đè nếu đã tồn tại và đủ dung lượng
        if os.path.exists(file_path) and os.path.getsize(file_path) > 100000:
            completed_count += 1
            if progress_cb:
                progress_cb(completed_count, total_count, video_info, file_path, "existed")
            return file_path

        # Lấy URL tải
        dl_url = video_info.get("download_url")
        if not dl_url:
            # Lấy link mới nếu link cũ rỗng
            try:
                crawler = DouyinBrowserDownloader()
                single_info = crawler.get_single_video_info(video_info.get("url") or vid_id)
                dl_url = single_info.get("download_url")
            except Exception:
                pass

        if not dl_url:
            return None

        # Tải stream
        time.sleep(random.uniform(0.3, 0.8)) # Delay nhẹ chống rate-limit
        try:
            download_stream_file(dl_url, file_path)
            completed_count += 1
            if progress_cb:
                progress_cb(completed_count, total_count, video_info, file_path, "success")
            return file_path
        except Exception as e:
            if progress_cb:
                progress_cb(completed_count, total_count, video_info, None, f"error: {str(e)}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, i, v) for i, v in enumerate(video_list)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                results.append(res)

    return results
