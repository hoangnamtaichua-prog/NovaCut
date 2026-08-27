# -*- coding: utf-8 -*-
"""
Module Auto-Updater (Hệ Thống Tự Động Cập Nhật Trực Tiếp Qua GitHub Private/Public Repository)
- Hỗ trợ kho Private & Public 100%.
- Máy Dev: Chỉ cần chạy 1 lệnh python scripts/publish_patch.py.
- Máy Khách: Mở app nhận diện phiên bản mới -> Bấm Cập nhật -> Tự động tải patch.zip và nâng cấp trong 2 giây.
- Bảo toàn 100% dữ liệu bản quyền (.license.dat), API keys, dự án (projects/) và mô hình AI.
"""

import os
import sys
import json
import time
import zipfile
import shutil
import subprocess
import threading
import re
import hmac
import hashlib
import requests
from urllib.parse import urlparse
import license_manager

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

VERSION_FILE = os.path.join(ROOT_DIR, 'version.json')
DEFAULT_VERSION = "1.0.0"

# Cấu hình kho GitHub chính thức
GITHUB_REPO = "hoangnamtaichua-prog/NovaCut"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

# Danh sách các tệp và thư mục BẮT BUỘC BẢO TOÀN (Tuyệt đối không ghi đè làm mất dữ liệu của khách)
PROTECTED_PATTERNS = {
    '.license.dat',
    '.processed_txs.dat',
    '.token_quota.dat',
    'license_config.json',
    'api_keys.txt',
    'config.json',
    'custom_voices.json',
    'custom_pronunciations.json',
    'projects',
    'movies',
    'movies_retired',
    'downloads',
    'output',
    'tiktok_output',
    'temp',
    'scratch',
    'voices',
    'backgroundmusic',
    'clips',
    '.git',
    '.agents',
    '.asr_venv',
    '.cache',
    '__pycache__'
}


def _get_auth_headers(accept_type="application/vnd.github.v3+json"):
    """Tạo Header xác thực an toàn truy cập kho GitHub."""
    token = os.environ.get('NOVACUT_GITHUB_TOKEN', '').strip()
    headers = {
        "Accept": accept_type,
        "User-Agent": "NovaCut-App-Updater/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


_ALLOWED_UPDATE_HOSTS = {
    'api.github.com', 'github.com', 'objects.githubusercontent.com',
    'release-assets.githubusercontent.com', 'raw.githubusercontent.com', 'drive.google.com'
}


def _validate_update_url(url):
    parsed = urlparse(str(url or '').strip())
    if parsed.scheme != 'https' or parsed.hostname not in _ALLOWED_UPDATE_HOSTS:
        raise ValueError('Nguồn cập nhật không nằm trong danh sách tin cậy.')
    return parsed.geturl()


def get_current_app_version():
    """Lấy phiên bản hiện tại của ứng dụng."""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return str(data.get('version', DEFAULT_VERSION)).strip()
        except Exception:
            pass
    return DEFAULT_VERSION


def set_current_app_version(version_str):
    """Ghi nhận phiên bản mới sau khi cập nhật thành công."""
    try:
        current_data = {}
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            except Exception:
                pass
        
        current_data["version"] = str(version_str).strip()
        current_data["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')

        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Lỗi ghi version.json: {e}")


def is_version_newer(latest_ver, current_ver):
    """So sánh 2 chuỗi phiên bản (ví dụ: '1.0.2' > '1.0.1')."""
    if not latest_ver or not current_ver:
        return False
    try:
        l_parts = [int(p) for p in re.findall(r'\d+', str(latest_ver))]
        c_parts = [int(p) for p in re.findall(r'\d+', str(current_ver))]
        for i in range(max(len(l_parts), len(c_parts))):
            l = l_parts[i] if i < len(l_parts) else 0
            c = c_parts[i] if i < len(c_parts) else 0
            if l > c:
                return True
            if l < c:
                return False
    except Exception:
        pass
    return False


# Trạng thái tiến trình tải & cập nhật thời gian thực
_update_progress_state = {
    "is_updating": False,
    "status": "idle", # 'idle', 'downloading', 'extracting', 'completed', 'error'
    "percent": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "message": "",
    "error": None,
    "target_version": ""
}


def get_update_progress():
    """Lấy trạng thái tiến độ tải cập nhật thời gian thực cho giao diện."""
    global _update_progress_state
    return dict(_update_progress_state)


def check_for_updates():
    """
    Kiểm tra phiên bản mới từ GitHub Repository (Hỗ trợ cả Public & Private).
    """
    current_ver = get_current_app_version()

    # 1. Thử kiểm tra qua GitHub Releases API
    try:
        res = requests.get(f"{GITHUB_API_BASE}/releases/latest", headers=_get_auth_headers(), timeout=6)
        if res.status_code == 200:
            data = res.json()
            tag_name = str(data.get('tag_name') or '').strip()
            latest_ver = tag_name.lstrip('v') if tag_name else current_ver
            changelog = str(data.get('body') or data.get('name') or '✨ Bản cập nhật tối ưu hóa hiệu năng & sửa lỗi.').strip()
            
            download_url = ""
            expected_sha256 = ""
            assets = data.get('assets', [])
            for a in assets:
                name = a.get('name', '')
                if name == 'patch.zip' or name.endswith('.zip'):
                    # Ưu tiên browser_download_url cho kho Public
                    download_url = a.get('browser_download_url') or a.get('url', '')
                    digest = str(a.get('digest') or '')
                    if digest.lower().startswith('sha256:'):
                        expected_sha256 = digest.split(':', 1)[1].strip().lower()
                    break
             
            # Nếu chưa có sha256 từ digest, tìm trong release body
            if not expected_sha256 and changelog:
                m = re.search(r'sha-?256[:\s=]+([0-9a-fA-F]{64})', changelog, re.IGNORECASE)
                if m:
                    expected_sha256 = m.group(1).lower()

            has_update = is_version_newer(latest_ver, current_ver) and bool(download_url)

            if has_update:
                return {
                    "has_update": True,
                    "current_version": current_ver,
                    "latest_version": latest_ver,
                    "download_url": download_url,
                    "sha256": expected_sha256,
                    "changelog": changelog,
                    "is_mandatory": False,
                    "source": "github_release"
                }
    except Exception as e:
        print(f"[Updater] GitHub Release check error: {e}")

    # 2. Thử kiểm tra trực tiếp qua file version.json (Raw GitHub)
    try:
        raw_urls = [
            f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json",
            f"{GITHUB_API_BASE}/contents/version.json"
        ]
        for u in raw_urls:
            try:
                headers = _get_auth_headers("application/json" if "raw" in u else "application/vnd.github.v3.raw")
                res = requests.get(u, headers=headers, timeout=6)
                if res.status_code == 200:
                    data = res.json()
                    latest_ver = str(data.get('version') or current_ver).strip()
                    download_url = str(data.get('download_url') or f"https://github.com/{GITHUB_REPO}/releases/download/v{latest_ver}/patch.zip").strip()
                    expected_sha256 = str(data.get('sha256') or '').strip().lower()
                    changelog = str(data.get('changelog') or '✨ Bản cập nhật tối ưu hiệu năng và sửa lỗi.').strip()
                    is_mandatory = bool(data.get('is_mandatory') is True)

                    has_update = is_version_newer(latest_ver, current_ver) and bool(download_url)
                    if has_update:
                        return {
                            "has_update": True,
                            "current_version": current_ver,
                            "latest_version": latest_ver,
                            "download_url": download_url,
                            "sha256": expected_sha256,
                            "changelog": changelog,
                            "is_mandatory": is_mandatory,
                            "source": "github_manifest"
                        }
            except Exception:
                continue
    except Exception as e:
        print(f"[Updater] Manifest check error: {e}")

    # 3. Fallback: Google Apps Script (nếu có cấu hình)
    cfg = license_manager.load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('api_secret_token', 'AMS_SECURE_TOKEN_2026_@DEEPMIND_ANTIGRAVITY')

    if gas_url:
        try:
            res = requests.get(gas_url, params={
                "action": "check_update",
                "current_version": current_ver,
                "token": token
            }, timeout=6)

            if res.status_code == 200:
                data = res.json()
                latest_ver = str(data.get('latest_version') or current_ver).strip()
                drive_file_id = str(data.get('google_drive_file_id') or '').strip()
                changelog = str(data.get('changelog') or 'Bản cập nhật tối ưu hóa hiệu năng và sửa lỗi.').strip()
                is_mandatory = bool(data.get('is_mandatory') is True or str(data.get('is_mandatory')).upper() == 'TRUE')
                expected_sha256 = str(data.get('sha256') or '').strip().lower()
                has_update = is_version_newer(latest_ver, current_ver) and bool(drive_file_id)

                if has_update:
                    return {
                        "has_update": True,
                        "current_version": current_ver,
                        "latest_version": latest_ver,
                        "google_drive_file_id": drive_file_id,
                        "download_url": f"https://drive.google.com/uc?export=download&id={drive_file_id}" if drive_file_id else "",
                        "sha256": expected_sha256,
                        "changelog": changelog,
                        "is_mandatory": is_mandatory,
                        "source": "google_sheet"
                    }
        except Exception:
            pass

    return {
        "has_update": False,
        "current_version": current_ver,
        "latest_version": current_ver,
        "message": "Bạn đang sử dụng phiên bản mới nhất."
    }


def download_file_direct(url, destination_path, progress_callback=None):
    """
    Tải file patch.zip trực tiếp từ GitHub Repository với chunked stream và báo % thời gian thực.
    Xử lý chuẩn chuyển hướng (Redirect) và tự động thử lại/tiếp tục tải (Resume/Retry) nếu đứt kết nối mạng.
    """
    url = _validate_update_url(url)
    token = os.environ.get('NOVACUT_GITHUB_TOKEN', '').strip()
    headers = {"User-Agent": "NovaCut-App-Updater/1.0"}
    if token and 'api.github.com' in url:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/octet-stream"
    
    # Pha 1: Bóc tách URL Storage đích (nếu là GitHub Release Asset API)
    stream_url = url
    try:
        res_init = requests.get(url, stream=True, headers=headers, timeout=(10, 30), allow_redirects=False)
        if res_init.status_code in (301, 302, 307, 308) and 'Location' in res_init.headers:
            stream_url = _validate_update_url(res_init.headers['Location'])
    except Exception as e:
        print(f"[Updater] Initial redirect probe notice: {e}")

    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    
    max_retries = 5
    chunk_size = 256 * 1024  # 256KB chunks
    total_size = 0
    downloaded = 0

    # Lấy tổng kích thước tệp trước
    try:
        head_headers = {"User-Agent": "NovaCut-App-Updater/1.0"}
        head_res = requests.head(stream_url, headers=head_headers, timeout=(10, 30), allow_redirects=True)
        if head_res.status_code == 200 and 'content-length' in head_res.headers:
            total_size = int(head_res.headers['content-length'])
    except Exception:
        pass

    for attempt in range(1, max_retries + 1):
        try:
            req_headers = {"User-Agent": "NovaCut-App-Updater/1.0"}
            if stream_url == url and token and 'api.github.com' in url:
                req_headers["Authorization"] = f"Bearer {token}"
                req_headers["Accept"] = "application/octet-stream"
            
            # Hỗ trợ tải tiếp (Resume) nếu đã tải được một phần
            if os.path.exists(destination_path):
                downloaded = os.path.getsize(destination_path)
                if total_size > 0 and downloaded >= total_size:
                    if progress_callback:
                        progress_callback(95, downloaded, total_size)
                    return destination_path
                if downloaded > 0:
                    req_headers['Range'] = f"bytes={downloaded}-"
            else:
                downloaded = 0

            mode = "ab" if downloaded > 0 else "wb"
            response = requests.get(stream_url, stream=True, headers=req_headers, timeout=(10, 60))

            if response.status_code not in (200, 206):
                # Nếu Range không được hỗ trợ (416), tải lại từ đầu
                if response.status_code == 416 or (downloaded > 0 and response.status_code == 200):
                    downloaded = 0
                    mode = "wb"
                    response = requests.get(stream_url, stream=True, headers={"User-Agent": "NovaCut-App-Updater/1.0"}, timeout=(10, 60))

            if response.status_code not in (200, 206):
                raise Exception(f"Máy chủ trả về mã HTTP {response.status_code}")

            if total_size == 0 and 'content-length' in response.headers:
                total_size = downloaded + int(response.headers['content-length'])

            with open(destination_path, mode) as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            pct = int((downloaded / total_size) * 95) if total_size > 0 else 0
                            pct = min(95, max(1, pct))
                            progress_callback(pct, downloaded, total_size)

            if total_size > 0 and downloaded < (total_size * 0.95):
                raise Exception(f"Tệp tải về chưa đủ ({downloaded}/{total_size} bytes). Đang thử lại...")

            return destination_path

        except Exception as err:
            print(f"[Updater] Lần thử {attempt}/{max_retries} gặp lỗi: {err}")
            if attempt == max_retries:
                raise Exception(f"Không thể hoàn tất tải bản cập nhật sau {max_retries} lần thử: {str(err)}")
            time.sleep(1.5)

    return destination_path


def apply_patch_zip(zip_path, target_version=""):
    """
    Giải nén bản vá đè lên mã nguồn, đảm bảo an toàn tuyệt đối cho tệp bản quyền và dữ liệu người dùng.
    """
    if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
        raise Exception("File tải về bị lỗi hoặc không phải định dạng .zip hợp lệ!")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        root_real = os.path.realpath(ROOT_DIR)
        total_uncompressed = sum(info.file_size for info in zip_ref.infolist())
        if total_uncompressed > 2 * 1024 * 1024 * 1024:
            raise Exception("Bản cập nhật vượt quá giới hạn dung lượng giải nén.")
        for file_info in zip_ref.infolist():
            filename = file_info.filename.replace('\\', '/')
            if not filename or filename.endswith('/'):
                continue

            dest_path = os.path.realpath(os.path.join(root_real, filename))
            if os.path.commonpath([root_real, dest_path]) != root_real:
                raise Exception(f"Bản cập nhật chứa đường dẫn không an toàn: {filename}")

            # Kiểm tra tệp có thuộc danh sách bảo vệ không
            is_protected = False
            top_level = filename.split('/')[0]
            basename = os.path.basename(filename)

            if basename in PROTECTED_PATTERNS or top_level in PROTECTED_PATTERNS:
                is_protected = True

            if is_protected and os.path.exists(os.path.join(ROOT_DIR, filename)):
                # Bỏ qua không ghi đè tệp bảo vệ
                continue

            # 1. Giải nén vào thư mục ứng dụng gốc
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with zip_ref.open(file_info) as source, open(dest_path, 'wb') as target:
                shutil.copyfileobj(source, target)

            # 2. Cơ chế OTA Patch Overlay: Giải nén bổ sung các file .py và package vào patches/active/ để nạp đè 100% C-binary (.pyd)
            if filename.endswith('.py') or filename.startswith('routes/'):
                overlay_root = os.path.realpath(os.path.join(ROOT_DIR, 'patches', 'active'))
                overlay_path = os.path.realpath(os.path.join(overlay_root, filename))
                if os.path.commonpath([overlay_root, overlay_path]) != overlay_root:
                    raise Exception(f"Overlay chứa đường dẫn không an toàn: {filename}")
                os.makedirs(os.path.dirname(overlay_path), exist_ok=True)
                with zip_ref.open(file_info) as source, open(overlay_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

            # 3. Tự động dọn dẹp các file C-binary (.pyd) cũ cùng tên nếu không bị tiến trình khóa
            if filename.endswith('.py'):
                base_name = os.path.splitext(dest_path)[0]
                dir_name = os.path.dirname(dest_path)
                stem = os.path.basename(base_name)
                try:
                    for f in os.listdir(dir_name):
                        if f.startswith(stem) and f.endswith('.pyd'):
                            try:
                                os.remove(os.path.join(dir_name, f))
                            except Exception:
                                pass
                except Exception:
                    pass

    # Cập nhật version mới
    if target_version:
        set_current_app_version(target_version)

    # Xóa file zip tạm
    try:
        os.remove(zip_path)
    except Exception:
        pass

    return True


def restart_application():
    """Khởi động lại ứng dụng một cách êm ái sau khi cập nhật."""
    def _restart():
        time.sleep(1.2)
        try:
            if getattr(sys, 'frozen', False):
                # Ứng dụng đã đóng gói EXE
                subprocess.Popen([sys.executable] + sys.argv[1:])
            else:
                # Chạy từ mã nguồn Python
                subprocess.Popen([sys.executable, os.path.join(ROOT_DIR, 'web_app.py')])
        except Exception as e:
            print(f"Lỗi khởi động lại app: {e}")
        os._exit(0)

    threading.Thread(target=_restart, daemon=True).start()


_UPDATE_THREAD_LOCK = threading.Lock()

def perform_auto_update_async(download_url_or_file_id, target_version, expected_sha256):
    """Thực hiện toàn bộ quá trình cập nhật trong background thread (Chống xung đột đa luồng)."""
    global _update_progress_state

    if _update_progress_state.get("is_updating"):
        print("[Updater] Update process already running in background, ignoring duplicate trigger.")
        return None

    with _UPDATE_THREAD_LOCK:
        if _update_progress_state.get("is_updating"):
            return None
        _update_progress_state["is_updating"] = True
        _update_progress_state["status"] = "downloading"
        _update_progress_state["percent"] = 0
        _update_progress_state["message"] = f"Đang tải bản cập nhật v{target_version} từ kho bảo mật..."
        _update_progress_state["target_version"] = target_version
        _update_progress_state["error"] = None
        _update_progress_state["downloaded_bytes"] = 0
        _update_progress_state["total_bytes"] = 0

    def _worker():
        global _update_progress_state
        safe_version = re.sub(r'[^0-9A-Za-z._-]', '_', str(target_version))[:64] or 'unknown'
        temp_zip = os.path.join(ROOT_DIR, 'temp', f'patch_v{safe_version}_{int(time.time())}.zip')

        def _on_progress(pct, down, total):
            _update_progress_state["percent"] = pct
            _update_progress_state["downloaded_bytes"] = down
            _update_progress_state["total_bytes"] = total
            if total > 0:
                mb_down = down / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                _update_progress_state["message"] = f"Đang tải bản cập nhật: {pct}% ({mb_down:.1f}MB / {mb_total:.1f}MB)"
            else:
                mb_down = down / (1024 * 1024)
                _update_progress_state["message"] = f"Đang tải bản cập nhật: {mb_down:.1f}MB..."

        try:
            target_url = download_url_or_file_id.strip()
            if not target_url.startswith('http://') and not target_url.startswith('https://'):
                target_url = f"https://drive.google.com/uc?export=download&id={target_url}"

            # 1. Tải bản vá trực tiếp từ GitHub Private Repo
            download_file_direct(target_url, temp_zip, progress_callback=_on_progress)

            expected = str(expected_sha256 or '').strip().lower()
            if expected and re.fullmatch(r'[0-9a-f]{64}', expected):
                hasher = hashlib.sha256()
                with open(temp_zip, 'rb') as patch_file:
                    for block in iter(lambda: patch_file.read(1024 * 1024), b''):
                        hasher.update(block)
                if not hmac.compare_digest(hasher.hexdigest(), expected):
                    raise Exception('SHA-256 của bản cập nhật không khớp manifest.')

            # 2. Giải nén và áp dụng bản vá
            _update_progress_state["status"] = "extracting"
            _update_progress_state["percent"] = 98
            _update_progress_state["message"] = "Đang cài đặt và cập nhật các tệp mới..."
            apply_patch_zip(temp_zip, target_version=target_version)

            # 2.5 Cài đặt các thư viện mới (CHỈ chạy khi ở môi trường Python source code, KHÔNG chạy trên EXE đóng băng)
            if not getattr(sys, 'frozen', False):
                req_path = os.path.join(ROOT_DIR, 'requirements.txt')
                if os.path.exists(req_path):
                    _update_progress_state["message"] = "Đang kiểm tra và cập nhật thư viện Python..."
                    try:
                        import ffmpeg_installer
                        stealth_kwargs = ffmpeg_installer.get_stealth_subprocess_kwargs()
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", req_path],
                            cwd=ROOT_DIR,
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=15,
                            **stealth_kwargs
                        )
                    except Exception as e:
                        print(f"Lỗi kiểm tra pip: {e}")

            # 3. Hoàn thành
            _update_progress_state["status"] = "completed"
            _update_progress_state["percent"] = 100
            _update_progress_state["message"] = f"🎉 Cập nhật lên v{target_version} thành công! Đang tự động khởi động lại..."
            
            # 4. Tự động khởi động lại sau 1.5 giây
            restart_application()

        except Exception as e:
            _update_progress_state["is_updating"] = False
            _update_progress_state["status"] = "error"
            _update_progress_state["error"] = str(e)
            _update_progress_state["message"] = f"Lỗi cập nhật: {str(e)}"
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread
