import os
import re
import sys
import json
import time
import zipfile
import shutil
import urllib.parse
import concurrent.futures
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8,zh-CN;q=0.7,zh;q=0.6',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}

def get_session_dir(root_dir, session_id, custom_parent_dir=None, folder_name=None):
    clean_folder = ""
    if folder_name and folder_name.strip():
        clean_folder = re.sub(r'[\\/*?:"<>|]', '_', folder_name.strip())
    if not clean_folder:
        clean_folder = session_id

    if custom_parent_dir and os.path.exists(custom_parent_dir):
        s_dir = os.path.join(custom_parent_dir, clean_folder)
    else:
        s_dir = os.path.join(root_dir, 'projects', 'comic_reviews', clean_folder)

    os.makedirs(s_dir, exist_ok=True)
    os.makedirs(os.path.join(s_dir, 'raw_pages'), exist_ok=True)
    os.makedirs(os.path.join(s_dir, 'panels'), exist_ok=True)
    os.makedirs(os.path.join(s_dir, 'scripts'), exist_ok=True)
    os.makedirs(os.path.join(s_dir, 'audio'), exist_ok=True)
    return s_dir

AD_KEYWORDS = [
    'logo', 'icon', 'banner', 'avatar', 'ads', 'loading', 'blank.gif', 'data:image/svg',
    'quangcao', 'quang-cao', 'sponsor', 'affiliate', 'shopee', 'lazada', 'tiki',
    'popup', 'float', 'widget', 'donate', 'momo', 'tracking', 'pixel', 'analytics',
    'doubleclick', 'adnxs', 'eclick', 'yandex', 'facebook', 'mgid', 'taboola',
    'adtrue', 'monetag', 'adsterra', 'admicro', 'adnow', 'propellerads', 'adcash',
    'tele', 'telegram', 'zalo', 'zakad', 'cocoon', 'mypham', 'shopeemall', 'ad-container', 'baotangtruyen'
]

def extract_image_urls_from_html(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    candidate_urls = []

    # 1. Tìm trong thẻ script có mảng ảnh JSON hoặc JS string
    script_patterns = [
        r'var\s+(?:chapter_images|images|pages|lstImages|docData|image_list)\s*=\s*(\[[^\]]+\])',
        r'(?:chapter_images|images|pages|slides)\s*:\s*(\[[^\]]+\])',
        r'window\.__DATA__\s*=\s*(\{.*?\});',
    ]
    for pattern in script_patterns:
        matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
        for m in matches:
            try:
                parsed = json.loads(m)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str) and any(item.lower().endswith(ext) or ext in item.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            if not any(ign in item.lower() for ign in AD_KEYWORDS):
                                candidate_urls.append(item.strip())
                        elif isinstance(item, dict):
                            for key in ['url', 'src', 'link', 'image', 'path']:
                                if key in item and isinstance(item[key], str):
                                    v = item[key].strip()
                                    if not any(ign in v.lower() for ign in AD_KEYWORDS):
                                        candidate_urls.append(v)
            except Exception:
                # Trích xuất dạng regex thô các link ảnh trong block script
                raw_urls = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', m, re.IGNORECASE)
                for ru in raw_urls:
                    if not any(ign in ru.lower() for ign in AD_KEYWORDS):
                        candidate_urls.append(ru)

    # 2. Tìm tất cả thẻ img thông thường và lazy loading
    img_tags = soup.find_all('img')
    for img in img_tags:
        # Kiểm tra cha có phải thẻ quảng cáo không
        parent_str = ""
        curr = img.parent
        p_depth = 0
        is_ad_parent = False
        while curr and p_depth < 4:
            c_name = str(curr.get('class') or '') + ' ' + str(curr.get('id') or '')
            if curr.name == 'a' and any(ad_link in str(curr.get('href') or '').lower() for ad_link in ['shopee', 'lazada', 'tiki', 'affiliate', 'doubleclick', 'click']):
                is_ad_parent = True
                break
            if any(w in c_name.lower() for w in ['ad', 'ads', 'banner', 'quangcao', 'qc', 'sponsor', 'shopee', 'lazada']):
                is_ad_parent = True
                break
            curr = curr.parent
            p_depth += 1
        if is_ad_parent:
            continue

        # Kiểm tra các thuộc tính phổ biến chứa link ảnh
        for attr in ['data-src', 'data-original', 'data-url', 'data-lazy-src', 'data-cdn', 'src', 'data-fallback']:
            val = img.get(attr)
            if val:
                val = val.strip()
                # Bỏ qua icon, logo, avatar, quảng cáo
                if any(ignored in val.lower() for ignored in AD_KEYWORDS):
                    continue
                if any(val.lower().endswith(ext) or ext in val.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    candidate_urls.append(val)
                elif 'cdn' in val or 'chapter' in val or 'page' in val:
                    candidate_urls.append(val)

    # Chuẩn hóa link (chuyển relative thành absolute) và lọc trùng lặp giữ nguyên thứ tự
    cleaned_urls = []
    seen = set()
    for u in candidate_urls:
        u = u.replace('\\/', '/')
        full_url = urllib.parse.urljoin(base_url, u)
        if full_url not in seen and full_url.startswith('http'):
            seen.add(full_url)
            cleaned_urls.append(full_url)

    return cleaned_urls

def extract_images_via_browser(url, root_dir, check_stop=None):
    """
    Sử dụng Playwright Persistent Context với stealth mode để tự động vượt qua
    Cloudflare Turnstile / Managed Challenge / 403 Forbidden và kích hoạt lazy loading ảnh truyện.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    profile_dir = os.path.join(root_dir, "temp", "comic_browser_profile")
    os.makedirs(profile_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            context = None
            for channel in ["msedge", "chrome", None]:
                try:
                    launch_kwargs = {
                        "user_data_dir": profile_dir,
                        "headless": False,
                        "args": [
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--window-size=1280,800"
                        ]
                    }
                    if channel:
                        launch_kwargs["channel"] = channel
                    context = p.chromium.launch_persistent_context(**launch_kwargs)
                    break
                except Exception:
                    continue

            if not context:
                return []

            try:
                page = context.new_page()
                page.goto(url, timeout=35000)

                # Chờ vượt qua Cloudflare Challenge (chỉ chờ nếu trang bị chặn)
                cur_title = page.title()
                if any(cf in cur_title for cf in ["Just a moment", "Cloudflare", "Attention Required"]):
                    for _ in range(12):
                        if check_stop and check_stop():
                            context.close()
                            return []
                        time.sleep(1)
                        t = page.title()
                        if not any(cf in t for cf in ["Just a moment", "Cloudflare", "Attention Required"]):
                            break

                # Tự động cuộn trang siêu tốc bằng JavaScript nội hàm để kích hoạt ảnh lazy-load
                fast_scroll_js = """
                () => new Promise(resolve => {
                    let totalHeight = 0;
                    let distance = 3500;
                    let count = 0;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        count++;
                        if (totalHeight >= scrollHeight || count >= 10) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 80);
                })
                """
                try:
                    page.evaluate(fast_scroll_js)
                except Exception:
                    pass

                # Lấy toàn bộ link ảnh với đầy đủ các thuộc tính lazy-load
                js_code = """
                () => {
                    const selectors = [
                        '.page-chapter img', '.story-see-content img', '.chapter_content img', 
                        '.reading-detail img', '.inner img', 'div[class*="chapter"] img', 
                        'div[id*="chapter"] img', '.chapter-img img', '.viewer img'
                    ];
                    let found = [];
                    for (const s of selectors) {
                        const els = document.querySelectorAll(s);
                        if (els.length > found.length) {
                            found = Array.from(els);
                        }
                    }
                    if (found.length === 0) {
                        found = Array.from(document.querySelectorAll('img'));
                    }
                    const adWords = ['ad', 'ads', 'banner', 'qc', 'quangcao', 'quang-cao', 'sponsor', 'shopee', 'lazada', 'tiki', 'affiliate', 'popup', 'donate', 'zakad', 'cocoon'];

                    const isAdElement = (el) => {
                        let parent = el.parentElement;
                        let depth = 0;
                        while (parent && depth < 6) {
                            const pCls = (parent.className || '').toString().toLowerCase();
                            const pId = (parent.id || '').toLowerCase();
                            if (parent.tagName === 'A') {
                                const href = (parent.getAttribute('href') || '').toLowerCase();
                                if (href.includes('shopee') || href.includes('lazada') || href.includes('tiki') || href.includes('affiliate') || href.includes('click') || href.includes('doubleclick') || href.includes('utm_')) {
                                    return true;
                                }
                            }
                            for (const w of adWords) {
                                if (pCls.includes(w) || pId.includes(w)) return true;
                            }
                            parent = parent.parentElement;
                            depth++;
                        }
                        const cls = (el.className || '').toString().toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const alt = (el.getAttribute('alt') || '').toLowerCase();
                        for (const w of adWords) {
                            if (cls.includes(w) || id.includes(w) || alt.includes(w)) return true;
                        }
                        return false;
                    };

                    const extractUrl = (el) => {
                        if (isAdElement(el)) return null;
                        return el.getAttribute('data-src') || 
                               el.getAttribute('data-original') || 
                               el.getAttribute('data-cdn') || 
                               el.getAttribute('data-lazy-src') || 
                               el.src || '';
                    };
                    return found.map(extractUrl).filter(Boolean);
                }
                """
                raw_urls = page.evaluate(js_code)
                context.close()

                # Lọc và chuẩn hóa ảnh truyện
                filtered = []
                seen = set()
                for u in raw_urls:
                    u = u.replace('\\/', '/')
                    full_url = urllib.parse.urljoin(url, u)
                    if full_url not in seen and full_url.startswith('http'):
                        if any(ext in full_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            if not any(ign in full_url.lower() for ign in AD_KEYWORDS):
                                seen.add(full_url)
                                filtered.append(full_url)
                return filtered
            except Exception as err:
                try:
                    context.close()
                except Exception:
                    pass
                print(f"[ComicCrawler] Lỗi browser crawler: {err}")
                return []
    except Exception as e:
        print(f"[ComicCrawler] Lỗi khởi tạo Playwright: {e}")
        return []

def detect_chapter_sequence(start_url, max_chapters=5, is_all=False, html_content=None, check_stop=None):
    """
    Tự động xác định danh sách link các chương truyện tiếp theo hoặc toàn bộ truyện
    từ URL chương hiện tại hoặc trang chủ truyện.
    """
    chapters = [start_url]
    if max_chapters <= 1 and not is_all:
        return chapters

    # 1. Nếu có HTML nội dung, phân tích <select> hoặc danh sách chapter
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        select_chap = None
        for s in soup.find_all('select'):
            cls_id = ((s.get('class') or [''])[0] if isinstance(s.get('class'), list) else str(s.get('class') or '')) + ' ' + (s.get('id') or '')
            if 'chap' in cls_id.lower() or any('chap' in o.text.lower() or 'chương' in o.text.lower() for o in s.find_all('option')):
                select_chap = s
                break

        if select_chap:
            opts = select_chap.find_all('option')
            opt_urls = []
            for o in opts:
                v = o.get('value', '').strip()
                if v:
                    full_v = urllib.parse.urljoin(start_url, v)
                    if full_v not in opt_urls:
                        opt_urls.append(full_v)

            curr_idx = -1
            clean_start = start_url.split('?')[0].rstrip('/')
            for i, u in enumerate(opt_urls):
                if u.split('?')[0].rstrip('/') == clean_start:
                    curr_idx = i
                    break

            if curr_idx != -1:
                rem = opt_urls[curr_idx:]
                if len(rem) >= 2:
                    return rem[:25] if is_all else rem[:max_chapters]
                elif curr_idx > 0:
                    rem_rev = list(reversed(opt_urls[:curr_idx + 1]))
                    return rem_rev[:25] if is_all else rem_rev[:max_chapters]

        chapter_links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            if any(k in href.lower() or k in text for k in ['-chap-', '/chap-', '/chapter-', '/chuong-']):
                full_h = urllib.parse.urljoin(start_url, href)
                if full_h not in chapter_links and full_h.startswith('http'):
                    chapter_links.append(full_h)

        if len(chapter_links) > 1:
            return chapter_links[:25] if is_all else chapter_links[:max_chapters]

    # 2. Regex pattern fallback (chap-1 -> chap-2 -> chap-3 ...)
    pattern = r'([-_/](?:chap|chapter|chuong|ep|tap|ch)[-_/]?)([0-9]+)'
    m = list(re.finditer(pattern, start_url, re.I))
    if m:
        last = m[-1]
        num = int(last.group(2))
        lim = 25 if is_all else max_chapters
        for n in range(num + 1, num + lim):
            next_u = start_url[:last.start(2)] + str(n) + start_url[last.end(2):]
            if next_u not in chapters:
                chapters.append(next_u)
        return chapters

    return chapters

def crawl_comic_chapters(url, root_dir, session_id, chapter_scope='5', chapter_count=5, is_all=False, custom_parent_dir=None, folder_name=None, check_stop=None):
    """
    Tải tất cả các trang ảnh của một hoặc nhiều chương truyện (hoặc toàn bộ truyện).
    Lần lượt cào các chương và gộp các trang ảnh theo thứ tự vào thư mục raw_pages.
    """
    is_all = is_all or (chapter_scope == 'all')
    if is_all:
        target_chaps = 25
        scope_label = "🌟 Toàn Bộ Truyện (Chuỗi chương cốt lõi)"
    elif chapter_scope == 'custom':
        target_chaps = max(1, min(50, int(chapter_count)))
        scope_label = f"{target_chaps} Chap tùy chọn"
    else:
        target_chaps = int(chapter_scope) if str(chapter_scope).isdigit() else max(1, int(chapter_count))
        scope_label = f"{target_chaps} Chap liên tiếp"

    session_dir = get_session_dir(root_dir, session_id, custom_parent_dir=custom_parent_dir, folder_name=folder_name)
    yield f"data: 🚀 Khởi động thu thập dữ liệu: {scope_label}\n\n"
    yield f"data: 📁 Thư mục lưu trữ dự án: {session_dir}\n\n"

    raw_pages_dir = os.path.join(session_dir, 'raw_pages')
    os.makedirs(raw_pages_dir, exist_ok=True)
    # Xóa ảnh cũ nếu có
    for f in os.listdir(raw_pages_dir):
        try:
            os.remove(os.path.join(raw_pages_dir, f))
        except Exception:
            pass

    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=32,
        pool_maxsize=32,
        max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(DEFAULT_HEADERS)
    session.headers['Referer'] = url

    # Thử lấy HTML của trang đầu tiên để nhận diện danh sách chapter
    first_html = ""
    try:
        r = session.get(url, timeout=12)
        if r.status_code == 200:
            first_html = r.text
    except Exception:
        pass

    chapter_urls = detect_chapter_sequence(url, max_chapters=target_chaps, is_all=is_all, html_content=first_html, check_stop=check_stop)
    yield f"data: 📑 Đã xác định lộ trình {len(chapter_urls)} chương truyện cần cào.\n\n"

    all_downloaded_files = []
    global_page_idx = 1

    for c_idx, chap_url in enumerate(chapter_urls, start=1):
        if check_stop and check_stop():
            yield "data: 🛑 Đã dừng tiến trình crawl.\n\n"
            break

        yield f"data: 📖 [Chương {c_idx}/{len(chapter_urls)}] Đang bóc tách ảnh: {chap_url}\n\n"

        image_urls = []
        need_browser = False

        try:
            session.headers['Referer'] = chap_url
            resp = session.get(chap_url, timeout=15)
            if resp.status_code == 403 or "Just a moment" in resp.text:
                need_browser = True
            else:
                resp.raise_for_status()
                image_urls = extract_image_urls_from_html(resp.text, chap_url)
                if not image_urls:
                    raw_matches = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', resp.text, re.IGNORECASE)
                    filtered = [u for u in raw_matches if not any(x in u.lower() for x in ['logo', 'icon', 'avatar', 'ads'])]
                    image_urls = list(dict.fromkeys(filtered))
                if len(image_urls) == 0:
                    need_browser = True
        except Exception:
            need_browser = True

        if need_browser:
            if c_idx == 1:
                yield "data: 🌐 Kích hoạt Trình duyệt Thông minh (Smart Browser Worker) vượt bảo vệ...\n\n"
            image_urls = extract_images_via_browser(chap_url, root_dir, check_stop=check_stop)

        if not image_urls:
            yield f"data: ⚠️ Chương {c_idx} không tìm thấy ảnh hoặc đã hết chương truyện.\n\n"
            if c_idx > 1:
                break
            else:
                continue

        total_in_chap = len(image_urls)
        yield f"data: 📥 [Chương {c_idx}] Tìm thấy {total_in_chap} trang ảnh. Bắt đầu tải siêu tốc đa luồng (Multi-threading)...\n\n"

        # Chuẩn bị danh sách download tasks kèm đường dẫn file chính xác
        download_tasks = []
        for img_idx, img_url in enumerate(image_urls, start=1):
            ext = '.jpg'
            for e in ['.png', '.webp', '.jpeg']:
                if e in img_url.lower():
                    ext = e
                    break

            filename = f"page_{global_page_idx:03d}{ext}"
            save_path = os.path.join(raw_pages_dir, filename)
            download_tasks.append((global_page_idx, img_url, chap_url, save_path))
            global_page_idx += 1

        def _download_worker(item):
            p_idx, i_url, r_url, s_path = item
            if check_stop and check_stop():
                return p_idx, s_path, False, "stopped"

            hdrs = dict(DEFAULT_HEADERS)
            hdrs['Referer'] = r_url
            for attempt in range(2):
                try:
                    r = session.get(i_url, headers=hdrs, timeout=18, stream=True)
                    if r.status_code == 200:
                        with open(s_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=64 * 1024):
                                if chunk:
                                    f.write(chunk)
                        if os.path.exists(s_path) and os.path.getsize(s_path) > 500:
                            # Tự động phát hiện và loại bỏ banner quảng cáo theo kích thước / tỉ lệ
                            try:
                                from PIL import Image
                                with Image.open(s_path) as im:
                                    w, h = im.size
                                    # 1. Kích thước quá nhỏ (icon, avatar, button)
                                    if w < 320 or h < 250:
                                        os.remove(s_path)
                                        return p_idx, s_path, False, "icon/logo too small"
                                    # 2. Tỉ lệ vuông 1:1 tuyệt đối (banner shopee/mỹ phẩm/ads)
                                    aspect = w / h
                                    if 0.93 <= aspect <= 1.07 and min(w, h) >= 300:
                                        os.remove(s_path)
                                        return p_idx, s_path, False, "square ad banner"
                            except Exception:
                                pass
                            return p_idx, s_path, True, ""
                except Exception as err:
                    if attempt == 1:
                        return p_idx, s_path, False, str(err)
                    time.sleep(0.2)
            return p_idx, s_path, False, "status not 200"

        # Tải song song 14 luồng bằng ThreadPoolExecutor
        max_workers = min(16, max(4, total_in_chap))
        completed_count = 0
        chap_downloaded = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_download_worker, item): item for item in download_tasks}
            for future in concurrent.futures.as_completed(futures):
                if check_stop and check_stop():
                    yield "data: 🛑 Đã dừng tiến trình tải ảnh.\n\n"
                    executor.shutdown(wait=False, cancel_futures=True)
                    return all_downloaded_files

                p_idx, s_path, ok, err_msg = future.result()
                completed_count += 1
                if ok:
                    chap_downloaded.append((p_idx, s_path))

                # Gửi tiến trình trực tiếp theo thời gian thực (mỗi 3-4 ảnh hoặc khi hoàn tất)
                if completed_count % 3 == 0 or completed_count == total_in_chap:
                    chap_pct = int((completed_count / total_in_chap) * 100)
                    overall_pct = int(((c_idx - 1) / len(chapter_urls) + (completed_count / total_in_chap) / len(chapter_urls)) * 100)
                    yield f"data: [PROGRESS] {overall_pct}\n\ndata: ⚡ [Chương {c_idx}] Đã tải siêu tốc: {completed_count}/{total_in_chap} ảnh ({chap_pct}%)...\n\n"

        # Sắp xếp lại file theo đúng thứ tự trang truyện gốc
        chap_downloaded.sort(key=lambda x: x[0])
        all_downloaded_files.extend([x[1] for x in chap_downloaded])

        overall_pct = int((c_idx / len(chapter_urls)) * 100)
        yield f"data: [PROGRESS] {overall_pct}\n\ndata: ✅ Đã hoàn tất tải Chương {c_idx}/{len(chapter_urls)} (Đã gom {len(all_downloaded_files)} trang ảnh)\n\n"

    yield f"data: 🎉 Hoàn thành! Đã tải về tổng cộng {len(all_downloaded_files)} trang ảnh truyện tranh sẵn sàng để cắt ô tranh!\n\n"
    return all_downloaded_files

crawl_comic_chapter = crawl_comic_chapters

def load_from_local_folder(folder_path, root_dir, session_id, custom_parent_dir=None, folder_name=None):
    """
    Nạp các file ảnh từ thư mục cục bộ của người dùng vào session.
    """
    session_dir = get_session_dir(root_dir, session_id, custom_parent_dir=custom_parent_dir, folder_name=folder_name)
    raw_pages_dir = os.path.join(session_dir, 'raw_pages')
    os.makedirs(raw_pages_dir, exist_ok=True)

    if not os.path.isdir(folder_path):
        raise ValueError(f"Thư mục không tồn tại: {folder_path}")

    files = sorted([f for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS])
    if not files:
        raise ValueError(f"Không tìm thấy file ảnh hợp lệ (.jpg, .png, .webp) trong {folder_path}")

    saved = []
    for idx, f in enumerate(files, start=1):
        src = os.path.join(folder_path, f)
        ext = os.path.splitext(f)[1].lower()
        dst = os.path.join(raw_pages_dir, f"page_{idx:03d}{ext}")
        shutil.copy2(src, dst)
        saved.append(dst)

    return saved

def load_from_archive(archive_path, root_dir, session_id, custom_parent_dir=None, folder_name=None):
    """
    Giải nén file zip/cbz chứa ảnh truyện vào session.
    """
    session_dir = get_session_dir(root_dir, session_id, custom_parent_dir=custom_parent_dir, folder_name=folder_name)
    raw_pages_dir = os.path.join(session_dir, 'raw_pages')
    os.makedirs(raw_pages_dir, exist_ok=True)

    if not os.path.isfile(archive_path):
        raise ValueError(f"File nén không tồn tại: {archive_path}")

    with zipfile.ZipFile(archive_path, 'r') as zf:
        img_members = [m for m in zf.namelist() if os.path.splitext(m)[1].lower() in IMAGE_EXTENSIONS and not m.startswith('__MACOSX')]
        img_members.sort()
        saved = []
        for idx, m in enumerate(img_members, start=1):
            ext = os.path.splitext(m)[1].lower()
            dst = os.path.join(raw_pages_dir, f"page_{idx:03d}{ext}")
            with zf.open(m) as source, open(dst, 'wb') as target:
                shutil.copyfileobj(source, target)
            saved.append(dst)
        return saved
