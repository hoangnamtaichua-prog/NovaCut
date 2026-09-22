# -*- coding: utf-8 -*-
"""
Module Bilibili Downloader sử dụng BBDown Engine chuyên biệt cho NovaCut.
- Hỗ trợ tải video Bilibili độ phân giải cao nhất (1080P 60fps, 4K, 8K)
- Tự động tách & ghép luồng DASH video + audio bằng FFmpeg sạch, không dính logo watermark player
- Hỗ trợ phân tích danh sách tập (multi-page/P1, P2...)
- Hỗ trợ đăng nhập qua QR Code bằng App Bilibili trên điện thoại hoặc nhập Cookie/SESSDATA
- Bắt realtime tiến độ tải từ stdout (xử lý cả \\r và \\n) và đẩy về giao diện người dùng
"""

import os
import re
import sys
import json
import time
import shutil
import base64
import subprocess
import threading
import urllib.request
import urllib.parse

def get_app_root_dir():
    """Xác định chính xác thư mục gốc của ứng dụng NovaCut."""
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

# Biến toàn cục quản lý tác vụ đăng nhập QR đang chạy
_login_process = None
_login_lock = threading.Lock()
_login_start_time = 0
_login_qr_path = None

def get_bin_dir():
    """Lấy đường dẫn thư mục bin chứa binary"""
    candidates = [
        os.path.join(ROOT_DIR, "bin"),
        os.path.join(os.path.dirname(sys.executable), "bin"),
        os.path.join(os.getcwd(), "bin")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    target = os.path.join(ROOT_DIR, "bin")
    os.makedirs(target, exist_ok=True)
    return target

def get_bbdown_path():
    """Tìm đường dẫn tệp thực thi BBDown.exe"""
    bin_dir = get_bin_dir()
    candidates = [
        os.path.join(bin_dir, "BBDown.exe"),
        os.path.join(ROOT_DIR, "BBDown.exe"),
        os.path.join(os.path.dirname(sys.executable), "BBDown.exe"),
        shutil.which("BBDown.exe") or shutil.which("BBDown")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None

def ensure_bbdown_installed():
    """Đảm bảo BBDown.exe sẵn sàng, tự tải phiên bản mới nhất nếu chưa có"""
    bb_path = get_bbdown_path()
    if bb_path and os.path.exists(bb_path):
        return bb_path

    bin_dir = get_bin_dir()
    target_exe = os.path.join(bin_dir, "BBDown.exe")

    # Ưu tiên: thử lấy phiên bản mới nhất từ GitHub Releases API
    download_url = None
    try:
        api_req = urllib.request.Request(
            'https://api.github.com/repos/nilaoda/BBDown/releases/latest',
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github.v3+json'}
        )
        with urllib.request.urlopen(api_req, timeout=10) as resp:
            release_data = json.loads(resp.read().decode('utf-8'))
            tag = release_data.get('tag_name', '?')
            for asset in release_data.get('assets', []):
                asset_name = asset.get('name', '')
                if 'win-x64' in asset_name.lower() and asset_name.endswith('.zip'):
                    download_url = asset.get('browser_download_url')
                    print(f"[BBDown] Phiên bản mới nhất: {tag} ({asset_name})")
                    break
    except Exception as e:
        print(f"[BBDown] Không thể query GitHub API: {e}")

    # Fallback về phiên bản cố định nếu API không hoạt động
    if not download_url:
        download_url = "https://github.com/nilaoda/BBDown/releases/download/1.6.3/BBDown_1.6.3_20240814_win-x64.zip"
        print("[BBDown] Dùng URL fallback v1.6.3")

    try:
        import io, zipfile
        print(f"[BBDown] Đang tải: {download_url}")
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            z.extractall(bin_dir)
        if os.path.exists(target_exe):
            print(f"[BBDown] Đã cài đặt thành công tại {target_exe}")
            return target_exe
    except Exception as e:
        print(f"[BBDown] Tự động tải thất bại: {e}")
    return None


def _get_ytdlp_cookie_file():
    """
    Chuyển đổi cookie Bilibili dạng 'Key=Value; Key2=Value2'
    sang file Netscape format để yt-dlp đọc được.
    Trả về đường dẫn file cookie hoặc None nếu không có cookie.
    """
    custom_cookie = get_bilibili_custom_cookie()
    if not custom_cookie:
        return None

    cookie_file = os.path.join(ROOT_DIR, '.bilibili_ytdlp_cookies.txt')
    try:
        parts = {}
        for part in custom_cookie.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                parts[k.strip()] = v.strip()

        if not parts:
            return None

        # Lấy expiry từ SESSDATA nếu có (dạng hash%2Ctimestamp%2C...)
        expiry = '1900000000'
        sess_val = parts.get('SESSDATA', '')
        if sess_val:
            decoded = urllib.parse.unquote(sess_val)
            ts_match = re.search(r'%(2C|,)(\d{10})', sess_val + ',' + decoded)
            if not ts_match:
                ts_parts = decoded.split(',')
                if len(ts_parts) >= 2 and ts_parts[1].isdigit():
                    expiry = ts_parts[1]

        lines = ['# Netscape HTTP Cookie File']
        for key, val in parts.items():
            # domain, include_subdomains, path, secure, expiry, name, value
            lines.append(f'.bilibili.com\tTRUE\t/\tFALSE\t{expiry}\t{key}\t{val}')

        with open(cookie_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return cookie_file
    except Exception as e:
        print(f"[Bilibili] Lỗi tạo cookie file cho yt-dlp: {e}")
        return None


def download_bilibili_via_ytdlp(url, format_id='best', is_audio=False, output_dir=None,
                                 progress_callback=None, info=None):
    """
    Tải video Bilibili bằng yt-dlp (engine thay thế khi BBDown gặp lỗi API).
    Hỗ trợ đầy đủ các mức chất lượng và xác thực cookie.
    """
    try:
        import yt_dlp
    except ImportError:
        raise Exception("yt-dlp chưa được cài đặt. Vui lòng chạy: pip install yt-dlp")

    if not output_dir:
        output_dir = os.path.join(ROOT_DIR, "downloads")
    os.makedirs(output_dir, exist_ok=True)

    # Mapping format_id → yt-dlp format selector
    fmt_str = str(format_id or 'best').upper()
    if is_audio:
        fmt_spec = 'bestaudio[ext=m4a]/bestaudio/best'
    elif '4K' in fmt_str or '2160' in fmt_str:
        fmt_spec = ('bestvideo[height>=2160]+bestaudio'
                    '/bestvideo[height>=1080]+bestaudio'
                    '/bestvideo+bestaudio/best')
    elif '1080P60' in fmt_str:
        fmt_spec = ('bestvideo[height>=1080][fps>=60]+bestaudio'
                    '/bestvideo[height>=1080]+bestaudio'
                    '/bestvideo+bestaudio/best')
    elif '1080' in fmt_str:
        fmt_spec = ('bestvideo[height>=1080]+bestaudio'
                    '/bestvideo[height>=720]+bestaudio'
                    '/bestvideo+bestaudio/best')
    elif '720' in fmt_str:
        fmt_spec = ('bestvideo[height>=720]+bestaudio'
                    '/bestvideo[height>=480]+bestaudio'
                    '/bestvideo+bestaudio/best')
    elif '480' in fmt_str:
        fmt_spec = 'bestvideo[height>=480]+bestaudio/bestvideo+bestaudio/best'
    elif '360' in fmt_str:
        fmt_spec = 'bestvideo[height>=360]+bestaudio/bestvideo+bestaudio/best'
    else:
        # 'best' → cố gắng lấy 1080P trở lên
        fmt_spec = ('bestvideo[height>=1080]+bestaudio'
                    '/bestvideo[height>=720]+bestaudio'
                    '/bestvideo+bestaudio/best')

    output_template = os.path.join(output_dir, '%(title)s [%(id)s].%(ext)s')
    existing_files = set(os.listdir(output_dir))
    downloaded_info = {'path': None}

    def progress_hook(d):
        status = d.get('status')
        if status == 'downloading' and progress_callback:
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes', 0)
            pct = round(done / total * 100, 1) if total > 0 else 0
            speed = d.get('speed') or 0
            speed_str = f"{speed / 1048576:.1f} MB/s" if speed > 0 else '-- MB/s'
            eta = d.get('eta') or 0
            eta_str = (f"{int(eta) // 60:02d}:{int(eta) % 60:02d}"
                       if eta else '--')
            progress_callback({
                'status': 'downloading',
                'percent': min(pct, 99.0),
                'speed': speed_str,
                'eta': eta_str
            })
        elif status == 'finished':
            fp = (d.get('filename')
                  or d.get('info_dict', {}).get('_filename')
                  or d.get('info_dict', {}).get('filepath'))
            if fp:
                downloaded_info['path'] = fp

    ffmpeg_path = get_ffmpeg_path()
    ydl_opts = {
        'format': fmt_spec,
        'outtmpl': output_template,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }
    if ffmpeg_path:
        ydl_opts['ffmpeg_location'] = os.path.dirname(ffmpeg_path)

    # Thêm cookie nếu có
    cookie_file = _get_ytdlp_cookie_file()
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts['cookiefile'] = cookie_file

    if progress_callback:
        progress_callback({
            'status': 'downloading',
            'percent': 2.0,
            'speed': '-- MB/s',
            'eta': '--'
        })

    extracted = None
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        extracted = ydl.extract_info(url, download=True)

    if progress_callback:
        progress_callback({
            'status': 'processing',
            'message': 'Đang đóng gói tệp video...'
        })

    meta = {
        'title': (extracted or {}).get('title', ''),
        'thumbnail': (extracted or {}).get('thumbnail', ''),
        'duration': (extracted or {}).get('duration', 0)
    }

    # Tìm file đầu ra
    target_file = downloaded_info.get('path')
    if target_file and os.path.exists(target_file):
        return target_file, meta

    current_files = set(os.listdir(output_dir))
    new_files = list(current_files - existing_files)
    media_exts = ('.mp4', '.mkv', '.mov', '.webm', '.mp3', '.m4a')
    media_files = [
        f for f in new_files
        if f.lower().endswith(media_exts) and not f.lower().endswith('.aria2')
    ]
    if media_files:
        media_files.sort(
            key=lambda x: os.path.getmtime(os.path.join(output_dir, x)),
            reverse=True
        )
        return os.path.join(output_dir, media_files[0]), meta

    # Quét toàn bộ thư mục, lấy file mới nhất
    all_media = [
        os.path.join(output_dir, f) for f in os.listdir(output_dir)
        if f.lower().endswith(media_exts) and not f.lower().endswith('.aria2')
    ]
    if all_media:
        all_media.sort(key=os.path.getmtime, reverse=True)
        return all_media[0], meta

    raise Exception("yt-dlp: Tải xong nhưng không tìm thấy file video đầu ra.")

def get_ffmpeg_path():
    """Lấy đường dẫn ffmpeg.exe trong bin/ hoặc hệ thống"""
    try:
        import ffmpeg_installer
        path = ffmpeg_installer.get_ffmpeg_path()
        if path and os.path.exists(path):
            return os.path.abspath(path)
    except Exception:
        pass
    bin_dir = get_bin_dir()
    candidate = os.path.join(bin_dir, "ffmpeg.exe")
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    system_ffmpeg = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    return os.path.abspath(system_ffmpeg) if system_ffmpeg else None

def is_bilibili_url(url):
    """Kiểm tra URL có thuộc nền tảng Bilibili hay không"""
    if not url:
        return False
    u = url.lower()
    return any(domain in u for domain in ['bilibili.com', 'b23.tv'])

def resolve_bilibili_url(url):
    """Chuẩn hóa URL Bilibili, giải mã link rút gọn b23.tv nếu có"""
    if not url:
        return url
    text = url.strip()
    match = re.search(r'(https?://[^\s\'"<>]+)', text)
    clean_url = match.group(1).rstrip('.,;!?/') if match else text
    
    if 'b23.tv' in clean_url.lower():
        try:
            req = urllib.request.Request(clean_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.url and 'bilibili.com' in resp.url:
                    return resp.url
        except Exception:
            pass
    return clean_url

def get_bilibili_data_path():
    """Tìm file lưu trữ phiên đăng nhập BBDown.data"""
    bin_dir = get_bin_dir()
    for p in [os.path.join(bin_dir, "BBDown.data"), os.path.join(ROOT_DIR, "BBDown.data")]:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None

def format_bilibili_cookie(cookie_text):
    """
    Chuẩn hóa Cookie Bilibili:
    - Nếu người dùng chỉ dán chuỗi SESSDATA, tự động bọc SESSDATA=...
    - Tự động gọi Bilibili nav API để lấy DedeUserID (mid) và ghép DedeUserID={mid}; SESSDATA={sess}
      (Bắt buộc phải có DedeUserID thì BBDown mới không bị lỗi 412!)
    """
    if not cookie_text:
        return None
    raw = cookie_text.strip()
    if not raw:
        return None

    sess_val = None
    if 'SESSDATA=' in raw:
        m = re.search(r'SESSDATA=([^;\s]+)', raw)
        if m:
            sess_val = m.group(1)
    else:
        # User pasted just the SESSDATA hash
        sess_val = raw

    # Nếu chuỗi cookie đã có cả DedeUserID và SESSDATA
    if 'DedeUserID=' in raw and 'SESSDATA=' in raw:
        return raw

    if sess_val:
        # Tự động truy vấn nav API để lấy DedeUserID
        try:
            req = urllib.request.Request(
                'https://api.bilibili.com/x/web-interface/nav',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                    'Cookie': f'SESSDATA={sess_val}'
                }
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                if data.get('code') == 0 and data.get('data', {}).get('isLogin'):
                    mid = data['data'].get('mid')
                    if mid:
                        return f"DedeUserID={mid}; SESSDATA={sess_val}"
        except Exception as e:
            print(f"[Bilibili] Cookie enrichment error: {e}")

        return f"SESSDATA={sess_val}"
    return raw

def get_bilibili_custom_cookie():
    """Lấy cookie tùy chỉnh nếu người dùng đã lưu thủ công"""
    cookie_file = os.path.join(ROOT_DIR, "bilibili_cookie.txt")
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c:
                    if 'DedeUserID=' not in c:
                        c_enriched = format_bilibili_cookie(c)
                        if c_enriched and 'DedeUserID=' in c_enriched:
                            try:
                                with open(cookie_file, "w", encoding="utf-8") as f2:
                                    f2.write(c_enriched)
                            except Exception:
                                pass
                            return c_enriched
                    return c
        except Exception:
            pass
    # Fallback kiểm tra cookies.txt
    general_cookie = os.path.join(ROOT_DIR, "cookies.txt")
    if os.path.exists(general_cookie):
        try:
            with open(general_cookie, "r", encoding="utf-8") as f:
                lines = f.readlines()
                bili_parts = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7 and 'bilibili' in parts[0]:
                        bili_parts.append(f"{parts[5]}={parts[6]}")
                if bili_parts:
                    return "; ".join(bili_parts)
        except Exception:
            pass
    return None

def verify_bilibili_cookie(cookie_str=None):
    """
    Xác minh cookie Bilibili có hợp lệ với server không (gọi nav API).
    Trả về dict: {'valid': bool, 'uname': str, 'is_vip': bool, 'mid': int}
    """
    if not cookie_str:
        cookie_str = get_bilibili_custom_cookie()
    if not cookie_str:
        return {'valid': False, 'uname': None, 'is_vip': False, 'mid': None}

    try:
        req = urllib.request.Request(
            'https://api.bilibili.com/x/web-interface/nav',
            headers={
                'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 Chrome/120.0 Safari/537.36'),
                'Referer': 'https://www.bilibili.com/',
                'Cookie': cookie_str
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            if data.get('code') == 0:
                d = data.get('data', {})
                if d.get('isLogin'):
                    return {
                        'valid': True,
                        'uname': d.get('uname', ''),
                        'is_vip': bool(d.get('vipStatus')),
                        'mid': d.get('mid')
                    }
    except Exception as e:
        print(f"[Bilibili] verify_cookie error: {e}")

    return {'valid': False, 'uname': None, 'is_vip': False, 'mid': None}


def is_bilibili_logged_in():
    """Kiểm tra xem app đã có phiên đăng nhập Bilibili hay chưa (kiểm tra file)"""
    if get_bilibili_data_path():
        return True
    if get_bilibili_custom_cookie():
        return True
    return False

def save_bilibili_cookie(cookie_text):
    """Lưu chuỗi cookie Bilibili hoặc SESSDATA thủ công kèm tự động enrich DedeUserID"""
    if not cookie_text:
        return False
    cookie_str = format_bilibili_cookie(cookie_text)
    if not cookie_str:
        return False
    cookie_file = os.path.join(ROOT_DIR, "bilibili_cookie.txt")
    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write(cookie_str)
    return True

# =========================================================================
# QUẢN LÝ ĐĂNG NHẬP QR BẰNG BBDOWN
# =========================================================================
def start_qr_login():
    """
    Khởi chạy BBDown login ngầm để lấy mã QR đăng nhập
    Trả về: (dict) {'success': True, 'qr_image': 'data:image/png;base64,...'}
    """
    global _login_process, _login_start_time, _login_qr_path
    bb_path = ensure_bbdown_installed()
    if not bb_path:
        raise Exception("Không tìm thấy BBDown.exe trên hệ thống")
    
    with _login_lock:
        if _login_process and _login_process.poll() is None:
            try:
                _login_process.terminate()
            except Exception:
                pass
            _login_process = None

        bin_dir = get_bin_dir()
        qr_file = os.path.join(bin_dir, "qrcode.png")
        if os.path.exists(qr_file):
            try:
                os.remove(qr_file)
            except Exception:
                pass
        
        # Chạy BBDown login trong thư mục bin/
        _login_process = subprocess.Popen(
            [bb_path, "login"],
            cwd=bin_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            errors='ignore'
        )
        _login_start_time = time.time()
        _login_qr_path = qr_file

    # Chờ tối đa 5 giây để BBDown tạo file qrcode.png
    for _ in range(25):
        time.sleep(0.2)
        if os.path.exists(qr_file) and os.path.getsize(qr_file) > 100:
            try:
                with open(qr_file, "rb") as f:
                    b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
                return {
                    'success': True,
                    'qr_image': b64,
                    'message': 'Vui lòng mở ứng dụng Bilibili trên điện thoại và quét mã QR'
                }
            except Exception as e:
                pass

    return {
        'success': False,
        'error': 'Không thể tạo mã QR đăng nhập. Vui lòng thử lại!'
    }

def poll_qr_login_status():
    """Kiểm tra xem người dùng đã quét mã QR thành công chưa"""
    global _login_process, _login_start_time, _login_qr_path
    with _login_lock:
        # Nếu đã có file BBDown.data mới tạo
        bin_dir = get_bin_dir()
        data_file = os.path.join(bin_dir, "BBDown.data")
        if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
            if _login_process and _login_process.poll() is None:
                try:
                    _login_process.terminate()
                except Exception:
                    pass
                _login_process = None
            if _login_qr_path and os.path.exists(_login_qr_path):
                try:
                    os.remove(_login_qr_path)
                except Exception:
                    pass
            return {
                'status': 'success',
                'logged_in': True,
                'message': 'Đăng nhập Bilibili thành công! Đã lưu phiên đăng nhập.'
            }

        if not _login_process:
            return {
                'status': 'idle',
                'logged_in': is_bilibili_logged_in()
            }

        # Kiểm tra nếu tiến trình đã dừng
        ret = _login_process.poll()
        if ret is not None:
            _login_process = None
            if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
                return {
                    'status': 'success',
                    'logged_in': True,
                    'message': 'Đăng nhập Bilibili thành công!'
                }
            return {
                'status': 'expired',
                'logged_in': False,
                'message': 'Mã QR đã hết hạn hoặc phiên đăng nhập bị hủy. Vui lòng bấm tạo mã mới!'
            }

        # Kiểm tra quá thời gian chờ (180 giây)
        if time.time() - _login_start_time > 180:
            try:
                _login_process.terminate()
            except Exception:
                pass
            _login_process = None
            return {
                'status': 'timeout',
                'logged_in': False,
                'message': 'Quá thời gian quét mã. Vui lòng bấm tạo mã mới!'
            }

        return {
            'status': 'waiting',
            'logged_in': False,
            'message': 'Đang chờ bạn quét mã trên ứng dụng Bilibili...'
        }

# =========================================================================
# PHÂN TÍCH THÔNG TIN VIDEO (METADATA RESOLVER)
# =========================================================================
def extract_bilibili_info(url):
    """
    Trích xuất metadata video Bilibili cực nhanh & chính xác.
    Ưu tiên dùng mobile endpoint (m.bilibili.com) để tránh hoàn toàn lỗi 412.
    Hỗ trợ hiển thị danh sách tập (multi-page/P1, P2...).
    """
    clean_url = resolve_bilibili_url(url)
    if not clean_url:
        return {'error': 'URL Bilibili không hợp lệ!'}

    # Trích xuất BV ID
    bv_match = re.search(r'(BV[a-zA-Z0-9]{10})', clean_url, re.IGNORECASE)
    bvid = bv_match.group(1) if bv_match else None

    # Danh sách độ phân giải tiêu chuẩn của Bilibili
    standard_resolutions = [
        {'format_id': 'best', 'label': 'Chất lượng cao nhất (Auto Best)', 'height': 9999, 'ext': 'mp4'},
        {'format_id': '4K', 'label': '4K Ultra HD (Yêu cầu VIP)', 'height': 2160, 'ext': 'mp4'},
        {'format_id': '1080P60', 'label': '1080P 60FPS Siêu mượt (Yêu cầu VIP)', 'height': 1081, 'ext': 'mp4'},
        {'format_id': '1080P', 'label': '1080P Full HD (Đăng nhập)', 'height': 1080, 'ext': 'mp4'},
        {'format_id': '720P', 'label': '720P HD (Chuẩn)', 'height': 720, 'ext': 'mp4'},
        {'format_id': '480P', 'label': '480P Tiêu chuẩn', 'height': 480, 'ext': 'mp4'},
        {'format_id': '360P', 'label': '360P Tiết kiệm dung lượng', 'height': 360, 'ext': 'mp4'}
    ]

    title = 'Video Bilibili'
    thumbnail = ''
    duration = 0
    uploader = 'Bilibili Creator'
    multi_videos = []

    # 1. Nếu đã có tài khoản / BBDown.data, thử dùng BBDown -info trước
    bb_path = get_bbdown_path()
    if is_bilibili_logged_in() and bb_path:
        try:
            bin_dir = get_bin_dir()
            ffmpeg_path = get_ffmpeg_path()
            info_cmd = [bb_path, "-info", clean_url]
            if ffmpeg_path:
                info_cmd.extend(["--ffmpeg-path", ffmpeg_path])
            custom_cookie = get_bilibili_custom_cookie()
            if custom_cookie and not get_bilibili_data_path():
                info_cmd.extend(["-c", custom_cookie])

            p = subprocess.Popen(
                info_cmd,
                cwd=bin_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='ignore'
            )
            out, _ = p.communicate(timeout=8)
            if p.returncode == 0:
                # Trích xuất tiêu đề từ stdout BBDown
                m_title = re.search(r'标题:\s*([^\r\n]+)', out) or re.search(r'Title:\s*([^\r\n]+)', out)
                if m_title:
                    title = m_title.group(1).strip()
                m_up = re.search(r'UP:\s*([^\r\n]+)', out) or re.search(r'作者:\s*([^\r\n]+)', out)
                if m_up:
                    uploader = m_up.group(1).strip()
        except Exception as e:
            print(f"[Bilibili] BBDown -info error: {e}")

    # 2. Thử lấy qua m.bilibili.com với timeout ngắn (4s)
    if (not title or title == 'Video Bilibili') and bvid:
        mobile_url = f"https://m.bilibili.com/video/{bvid}"
        try:
            req = urllib.request.Request(
                mobile_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                    'Referer': 'https://m.bilibili.com/'
                }
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                m_state = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});', html)
                if m_state:
                    state_data = json.loads(m_state.group(1))
                    video_block = state_data.get('video', {})
                    view_info = video_block.get('viewInfo', {})
                    up_info = video_block.get('upInfo', {})

                    if view_info.get('title'):
                        title = view_info.get('title')
                    if view_info.get('pic'):
                        thumbnail = view_info.get('pic')
                    if view_info.get('duration'):
                        duration = int(view_info.get('duration', 0))
                    if up_info.get('name'):
                        uploader = up_info.get('name')

                    # Kiểm tra danh sách tập (multi-pages)
                    pages = view_info.get('pages', [])
                    if isinstance(pages, list) and len(pages) > 1:
                        for p in pages:
                            p_num = p.get('page', 1)
                            p_title = p.get('part', f'Tập {p_num}')
                            p_dur = p.get('duration', duration)
                            multi_videos.append({
                                'title': f"{title} - [P{p_num}] {p_title}",
                                'thumbnail': thumbnail,
                                'duration': p_dur,
                                'uploader': uploader,
                                'extractor': 'Bilibili',
                                'url': f"https://www.bilibili.com/video/{bvid}?p={p_num}",
                                'resolutions': standard_resolutions,
                                'page': p_num
                            })
        except Exception:
            pass

    # 3. Fallback tiêu đề thân thiện kèm BV ID nếu không lấy được từ web
    if not title or title == 'Video Bilibili':
        title = f"Bilibili Video [{bvid}]" if bvid else "Bilibili Video"

    # Làm sạch tiêu đề video
    clean_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or (f"Bilibili_{bvid}" if bvid else "Bilibili_Video")

    result = {
        'success': True,
        'title': clean_title,
        'thumbnail': thumbnail,
        'duration': duration,
        'uploader': uploader,
        'extractor': 'Bilibili',
        'url': clean_url,
        'resolutions': standard_resolutions,
        'logged_in': is_bilibili_logged_in()
    }

    if multi_videos:
        result['videos'] = multi_videos

    return result

# =========================================================================
# TẢI VIDEO BẰNG BBDOWN (STREAM TẢI & GHÉP FFMPEG)
# =========================================================================
def download_bilibili_media(url, format_id='best', is_audio=False, output_dir=None, progress_callback=None, info=None):
    """
    Tải video Bilibili bằng BBDown Engine:
    - Bắt realtime stdout xử lý \\r và \\n để stream % tiến độ, tốc độ, ETA
    - Bắt giai đoạn FFmpeg muxing
    - Tự động tìm tệp video sau khi ghép hoàn tất
    """
    bb_path = ensure_bbdown_installed()
    if not bb_path:
        raise Exception("Không tìm thấy công cụ BBDown.exe. Vui lòng kiểm tra lại kết nối mạng để app tự động cài đặt!")

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise Exception("Không tìm thấy FFmpeg trên hệ thống. BBDown cần FFmpeg để ghép luồng video và audio!")

    clean_url = resolve_bilibili_url(url)
    if not clean_url:
        raise ValueError("URL Bilibili không hợp lệ")

    if not output_dir:
        output_dir = os.path.join(ROOT_DIR, "downloads")
    os.makedirs(output_dir, exist_ok=True)

    # Ghi nhận danh sách file trước khi tải để đối soát file mới sinh ra
    existing_files = set(os.listdir(output_dir))

    # Xác định chính xác số tập cần tải (target_page: 1, 2, 3... hoặc ALL)
    target_page = None
    if info and isinstance(info, dict) and info.get('page') is not None:
        target_page = str(info['page']).strip()
    if not target_page:
        page_match = re.search(r'[?&]p=([0-9]+|ALL|all)', clean_url, re.IGNORECASE)
        if page_match:
            target_page = page_match.group(1).upper()

    # Chuẩn hóa URL cho BBDown: loại bỏ query tracking (spm_id_from, vd_source, p=...)
    # để tránh việc BBDown bị xung đột giữa p trong URL và tham số dòng lệnh -p
    bv_match = re.search(r'(BV[a-zA-Z0-9]{10})', clean_url, re.IGNORECASE)
    if bv_match:
        bvid = bv_match.group(1)
        bbdown_target = f"https://www.bilibili.com/video/{bvid}"
    else:
        bbdown_target = clean_url.split('?')[0]

    # Xây dựng lệnh gọi BBDown
    # -hs: tránh bị dừng chờ chọn luồng tương tác
    # -mt: multi-thread tải song song (tăng tốc độ đáng kể)
    cmd = [
        bb_path,
        bbdown_target,
        "-hs",
        "-mt",
        "-e", "hevc,avc,av1",
        "--work-dir", output_dir,
        "--ffmpeg-path", ffmpeg_path,
        "-F", "<videoTitle> [<bvid>]",
        "-M", "[P<pageNumberWithZero>] <pageTitle> [<bvid>]"
    ]

    # Thêm cờ chọn tập cụ thể
    if target_page:
        cmd.extend(["-p", target_page])

    # Chế độ tải chỉ âm thanh
    if is_audio:
        cmd.append("--audio-only")

    # Ưu tiên độ phân giải (cải thiện: thêm 高码率 vào danh sách fallback 1080P)
    if format_id and format_id != 'best':
        fmt_str = str(format_id).upper()
        if '4K' in fmt_str or '2160' in fmt_str:
            cmd.extend(["-q", "4K 超清, 1080P 60帧, 1080P 高码率, 1080P 高清, 720P 高清"])
        elif '1080P60' in fmt_str:
            cmd.extend(["-q", "1080P 60帧, 1080P 高码率, 1080P 高清, 720P 高清"])
        elif '1080P' in fmt_str or '1080' in fmt_str:
            cmd.extend(["-q", "1080P 高码率, 1080P 高清, 720P 高清"])
        elif '720P' in fmt_str or '720' in fmt_str:
            cmd.extend(["-q", "720P 高清, 480P 清晰"])
        elif '480P' in fmt_str or '480' in fmt_str:
            cmd.extend(["-q", "480P 清晰, 360P 流畅"])
        elif '360P' in fmt_str or '360' in fmt_str:
            cmd.extend(["-q", "360P 流畅"])
    else:
        # Mặc định: tự động chọn chất lượng cao nhất có thể
        cmd.extend(["-q", "4K 超清, 1080P 60帧, 1080P 高码率, 1080P 高清, 720P 高清, 480P 清晰, 360P 流畅"])

    # Thêm cookie tùy chỉnh nếu có
    custom_cookie = get_bilibili_custom_cookie()
    if custom_cookie and not get_bilibili_data_path():
        cmd.extend(["-c", custom_cookie])

    # Báo tiến độ ban đầu
    if progress_callback:
        progress_callback({
            'status': 'downloading',
            'percent': 1.0,
            'speed': '-- MB/s',
            'eta': '--'
        })

    # Chạy BBDown subprocess
    bin_dir = get_bin_dir()
    proc = subprocess.Popen(
        cmd,
        cwd=bin_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        bufsize=0
    )

    last_percent = 1.0
    buffer = b""
    full_logs = []
    error_detail = None

    try:
        while True:
            char = proc.stdout.read(1)
            if not char:
                break
            if char in (b'\r', b'\n'):
                line = buffer.decode('utf-8', errors='ignore').strip()
                buffer = b""
                if not line:
                    continue

                full_logs.append(line)
                if len(full_logs) > 200:
                    full_logs.pop(0)

                # Bắt lỗi 412 chính xác (tránh nhầm lẫn với chuỗi URL token chứa 412)
                if '412, Precondition Failed' in line or 'statuscode_reason, 412' in line or 'Precondition Failed' in line:
                    error_detail = "Bilibili yêu cầu xác thực bảo mật (Lỗi 412). Vui lòng bấm 'Đăng nhập Bilibili' để quét mã QR hoặc nhập Cookie SESSDATA!"

                # Bắt giai đoạn FFmpeg đóng gói / ghép nối
                if any(kw in line.lower() for kw in ['ffmpeg', '混流', '合并', 'mux', 'muxing', '开始处理']):
                    if progress_callback:
                        progress_callback({
                            'status': 'processing',
                            'message': 'Đang đóng gói và ghép nối video bằng FFmpeg...'
                        })

                # Bắt % tiến độ: ví dụ "45.2% 12.3MB/s 00:01:23" hoặc "[45%]"
                pct_match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if pct_match:
                    try:
                        pct = float(pct_match.group(1))
                        if pct > last_percent:
                            last_percent = pct

                        speed_match = re.search(r'([\d\.]+\s*(?:[KkMmGg][Bb]|B)/s)', line)
                        speed_str = speed_match.group(1) if speed_match else '-- MB/s'

                        eta_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', line)
                        eta_str = eta_match.group(1) if eta_match else '--'

                        if progress_callback:
                            progress_callback({
                                'status': 'downloading',
                                'percent': min(round(last_percent, 1), 99.0),
                                'speed': speed_str,
                                'eta': eta_str
                            })
                    except Exception:
                        pass
            else:
                buffer += char

        proc.wait()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        raise e

    # Kiểm tra mã trả về
    if proc.returncode != 0:
        recent_log = "\n".join(full_logs[-10:])

        # Phát hiện lỗi API tương thích: BBDown cũ không hoạt động với Bilibili API mới
        api_broken = (
            error_detail is not None
            or 'Arg_KeyNotFound' in recent_log
            or '412' in recent_log
            or 'KeyNotFound' in recent_log
            or 'Precondition Failed' in recent_log
        )

        if api_broken:
            # Tự động chuyển sang yt-dlp làm engine thay thế
            fallback_msg = (
                "BBDown gặp lỗi xác thực Bilibili API (có thể do phiên bản BBDown cũ). "
                "Đang tự động chuyển sang yt-dlp engine..."
            )
            print(f"[Bilibili] {fallback_msg}")
            if progress_callback:
                progress_callback({
                    'status': 'processing',
                    'message': '⚠️ BBDown lỗi API → Đang thử lại với yt-dlp...'
                })
            try:
                return download_bilibili_via_ytdlp(
                    url=url,
                    format_id=format_id,
                    is_audio=is_audio,
                    output_dir=output_dir,
                    progress_callback=progress_callback,
                    info=info
                )
            except Exception as ytdlp_err:
                base_err = error_detail or f"BBDown lỗi (exit {proc.returncode})"
                raise Exception(
                    f"{base_err}\n\n"
                    f"yt-dlp cũng thất bại: {ytdlp_err}\n\n"
                    f"BBDown log:\n{recent_log}"
                )

        raise Exception(f"Lỗi tải video Bilibili (Exit code {proc.returncode}):\n{recent_log}")

    # Tìm file vừa tải về trong output_dir
    current_files = set(os.listdir(output_dir))
    new_files = list(current_files - existing_files)

    target_file = None

    # Nếu tải tập cụ thể (target_page là số), ưu tiên tìm file chứa nhãn tập đó
    if target_page and target_page.isdigit():
        p_int = int(target_page)
        p_patterns = [f"[p{p_int:02d}]", f"[p{p_int}]", f"p{p_int:02d}", f"p{p_int}"]
        
        # 1. Tìm trong các file mới sinh ra
        if new_files:
            p_new = [
                os.path.join(output_dir, f) for f in new_files
                if any(pat in f.lower() for pat in p_patterns) and f.lower().endswith(('.mp4', '.mkv', '.mov', '.mp3', '.m4a')) and not f.lower().endswith('.aria2')
            ]
            if p_new:
                p_new.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                target_file = p_new[0]

        # 2. Nếu không có trong file mới (hoặc file đã tải trước đó bị ghi đè), tìm trong toàn thư mục
        if not target_file:
            p_all = [
                os.path.join(output_dir, f) for f in os.listdir(output_dir)
                if any(pat in f.lower() for pat in p_patterns) and f.lower().endswith(('.mp4', '.mkv', '.mov', '.mp3', '.m4a')) and not f.lower().endswith('.aria2')
            ]
            if p_all:
                p_all.sort(key=os.path.getmtime, reverse=True)
                target_file = p_all[0]

    if not target_file and new_files:
        # Lọc file media (.mp4, .mkv, .mp3, .m4a)
        media_files = [
            f for f in new_files
            if f.lower().endswith(('.mp4', '.mkv', '.mov', '.mp3', '.m4a')) and not f.lower().endswith('.aria2')
        ]
        if media_files:
            # Ưu tiên file mới nhất
            media_files.sort(key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
            target_file = os.path.join(output_dir, media_files[0])

    if not target_file:
        # Quét tất cả file trong output_dir sắp xếp theo thời gian sửa đổi gần nhất
        all_media = [
            os.path.join(output_dir, f) for f in os.listdir(output_dir)
            if f.lower().endswith(('.mp4', '.mkv', '.mov', '.mp3', '.m4a')) and not f.lower().endswith('.aria2')
        ]
        if all_media:
            all_media.sort(key=os.path.getmtime, reverse=True)
            target_file = all_media[0]

    if not target_file or not os.path.exists(target_file):
        raise Exception("Quá trình tải hoàn tất nhưng không tìm thấy file video đầu ra.")

    # Thông báo hoàn tất đóng gói
    if progress_callback:
        progress_callback({
            'status': 'processing',
            'message': 'Đang hoàn tất tệp video...'
        })

    return target_file, (info or {'title': os.path.basename(target_file)})
