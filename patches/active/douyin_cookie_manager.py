# -*- coding: utf-8 -*-
"""
NovaCut Douyin Cookie & Account Manager
Quản lý và đồng bộ Cookie / Phiên đăng nhập Douyin.
Hỗ trợ xác thực với Douyin Passport API, định dạng chuỗi Cookie,
đồng bộ với Playwright Browser Context và Requests Session.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DOUYIN_COOKIE_FILE = os.path.join(ROOT_DIR, "douyin_cookie.txt")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
)


def format_douyin_cookie(cookie_text):
    """
    Chuẩn hóa chuỗi cookie từ nhiều nguồn khác nhau (chuỗi thô, Cookie-Editor JSON, Netscape cookies.txt).
    Trả về chuỗi cookie dạng 'key1=val1; key2=val2' chuẩn HTTP Header.
    """
    if not cookie_text or not isinstance(cookie_text, str):
        return ""

    raw = cookie_text.strip()
    if not raw:
        return ""

    # Trường hợp 1: Dạng JSON (ví dụ xuất từ tiện ích Cookie-Editor: [{"name": "...", "value": "..."}, ...])
    if raw.startswith("[") and raw.endswith("]"):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                cookie_parts = []
                for item in items:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        cookie_parts.append(f"{item['name']}={item['value']}")
                if cookie_parts:
                    return "; ".join(cookie_parts)
        except Exception:
            pass

    # Trường hợp 2: Dạng Netscape cookies.txt (tab-separated)
    if "\t" in raw:
        cookie_parts = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and "douyin" in parts[0]:
                cookie_parts.append(f"{parts[5]}={parts[6]}")
        if cookie_parts:
            return "; ".join(cookie_parts)

    # Trường hợp 3: Chuỗi cookie thô thông thường hoặc nhiều dòng
    clean_parts = []
    # Tách theo dấu chấm phẩy hoặc xuống dòng
    entries = re.split(r'[;\r\n]+', raw)
    for entry in entries:
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue
        if "=" in entry:
            k, v = entry.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                clean_parts.append(f"{k}={v}")

    if clean_parts:
        return "; ".join(clean_parts)

    return raw


def get_douyin_custom_cookie():
    """Lấy chuỗi cookie Douyin nếu người dùng đã lưu thủ công hoặc đã đăng nhập"""
    if os.path.exists(DOUYIN_COOKIE_FILE):
        try:
            with open(DOUYIN_COOKIE_FILE, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    return format_douyin_cookie(c)
        except Exception as e:
            logger.warning(f"[DouyinCookie] Lỗi đọc cookie file: {e}")
    return None


def get_douyin_cookie_dict(cookie_str=None):
    """Chuyển chuỗi cookie thành dict {name: value}"""
    if not cookie_str:
        cookie_str = get_douyin_custom_cookie()
    if not cookie_str:
        return {}

    cookie_dict = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookie_dict[k.strip()] = v.strip()
    return cookie_dict


def get_douyin_cookie_list_for_playwright(cookie_str=None):
    """
    Chuyển đổi cookie thành danh sách dict tương thích với Playwright context.add_cookies()
    [{'name': ..., 'value': ..., 'domain': '.douyin.com', 'path': '/'}]
    """
    c_dict = get_douyin_cookie_dict(cookie_str)
    cookie_list = []
    for name, value in c_dict.items():
        cookie_list.append({
            "name": name,
            "value": value,
            "domain": ".douyin.com",
            "path": "/"
        })
    return cookie_list


def is_douyin_logged_in():
    """Kiểm tra xem tệp cookie Douyin có tồn tại và có nội dung không"""
    if os.path.exists(DOUYIN_COOKIE_FILE):
        try:
            return os.path.getsize(DOUYIN_COOKIE_FILE) > 5
        except Exception:
            return False
    return False


def verify_douyin_cookie(cookie_str=None):
    """
    Xác minh cookie Douyin bằng cách gọi endpoint Douyin Passport Web Account Info API.
    Trả về dict: {
        'valid': bool,
        'uname': str,
        'user_id': str,
        'sec_uid': str,
        'avatar_url': str,
        'description': str
    }
    """
    if not cookie_str:
        cookie_str = get_douyin_custom_cookie()

    res = {
        'valid': False,
        'uname': None,
        'user_id': None,
        'sec_uid': None,
        'avatar_url': None,
        'description': None
    }

    if not cookie_str:
        res['description'] = 'Chưa thiết lập Cookie'
        return res

    try:
        url = 'https://www.douyin.com/passport/web/account/info/'
        headers = {
            'User-Agent': DEFAULT_USER_AGENT,
            'Referer': 'https://www.douyin.com/',
            'Cookie': cookie_str,
            'Accept': 'application/json, text/plain, */*'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as response:
            body = response.read().decode('utf-8', errors='ignore')
            data_json = json.loads(body)

            data = data_json.get('data') or {}
            error_code = data.get('error_code', -1)
            message = data_json.get('message', '')

            # Nếu error_code == 0 hoặc có thông tin user
            if error_code == 0 or (isinstance(data, dict) and ('name' in data or 'screen_name' in data or 'user_id' in data)):
                res['valid'] = True
                res['uname'] = data.get('name') or data.get('screen_name') or 'Tài Khoản Douyin'
                res['user_id'] = str(data.get('user_id') or '')
                res['sec_uid'] = str(data.get('sec_user_id') or '')
                res['avatar_url'] = data.get('avatar_url')
                res['description'] = 'Phiên đăng nhập hợp lệ'
                return res
            else:
                desc = data.get('description') or message or 'Phiên đăng nhập hết hạn hoặc Cookie không hợp lệ'
                res['description'] = desc
                return res

    except urllib.error.HTTPError as he:
        res['description'] = f"HTTP Error {he.code}"
    except Exception as e:
        res['description'] = f"Lỗi xác minh: {str(e)}"

    return res


def save_douyin_cookie(cookie_text):
    """Lưu chuỗi cookie vào douyin_cookie.txt"""
    try:
        cookie_str = format_douyin_cookie(cookie_text)
        if not cookie_str:
            return False
        with open(DOUYIN_COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(cookie_str)
        return True
    except Exception as e:
        logger.error(f"[DouyinCookie] Lỗi khi lưu cookie: {e}")
        return False


def clear_douyin_cookie():
    """Xóa bỏ cookie đã lưu (Đăng xuất)"""
    try:
        if os.path.exists(DOUYIN_COOKIE_FILE):
            os.remove(DOUYIN_COOKIE_FILE)
        return True
    except Exception as e:
        logger.error(f"[DouyinCookie] Lỗi khi xóa cookie: {e}")
        return False


def extract_and_save_cookies_from_playwright_context(context):
    """
    Trích xuất cookies từ Playwright Browser Context và lưu vào douyin_cookie.txt.
    Thường được gọi sau khi người dùng đăng nhập bằng cửa sổ trình duyệt Headed.
    """
    try:
        cookies = context.cookies()
        if not cookies:
            return False
        
        cookie_parts = []
        for c in cookies:
            domain = c.get("domain", "")
            if "douyin" in domain or "bytedance" in domain:
                cookie_parts.append(f"{c['name']}={c['value']}")

        if cookie_parts:
            cookie_str = "; ".join(cookie_parts)
            with open(DOUYIN_COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(cookie_str)
            logger.info(f"[DouyinCookie] Đã tự động trích xuất và lưu {len(cookie_parts)} cookies từ trình duyệt.")
            return True
    except Exception as e:
        logger.error(f"[DouyinCookie] Lỗi trích xuất cookie từ browser context: {e}")
    return False
