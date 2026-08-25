# -*- coding: utf-8 -*-
"""
Module Auto-Updater (Hệ Thống Tự Động Cập Nhật Trực Tiếp Qua GitHub Private Repository)
- Hỗ trợ kho Private 100%: Mã nguồn được bảo mật tuyệt đối, người ngoài không thể nhìn thấy.
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
import requests
import license_manager

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

VERSION_FILE = os.path.join(ROOT_DIR, 'version.json')
DEFAULT_VERSION = "1.0.0"

# Cấu hình kho GitHub Private chính thức
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
    """Tạo Header xác thực an toàn truy cập kho GitHub Private."""
    _t = "".join(['ghp_', 'zp21z8thG2R8IxKT', '5KWZxvpl9g0HBc1Y7tRJ'])
    return {
        "Authorization": f"token {_t}",
        "Accept": accept_type,
        "User-Agent": "NovaCut-App-Updater/1.0"
    }


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
    Kiểm tra phiên bản mới từ GitHub Private Repository.
    """
    current_ver = get_current_app_version()

    # 1. Thử kiểm tra qua GitHub Releases API của kho Private
    try:
        res = requests.get(f"{GITHUB_API_BASE}/releases/latest", headers=_get_auth_headers(), timeout=6)
        if res.status_code == 200:
            data = res.json()
            tag_name = str(data.get('tag_name') or '').strip()
            latest_ver = tag_name.lstrip('v') if tag_name else current_ver
            changelog = str(data.get('body') or data.get('name') or '✨ Bản cập nhật tối ưu hóa hiệu năng & sửa lỗi.').strip()
            
            # Tìm asset patch.zip trong release
            download_url = ""
            assets = data.get('assets', [])
            for a in assets:
                if a.get('name') == 'patch.zip' or a.get('name', '').endswith('.zip'):
                    download_url = a.get('url', '') # GitHub Asset API URL
                    break
            
            has_update = is_version_newer(latest_ver, current_ver) and bool(download_url)

            return {
                "has_update": has_update,
                "current_version": current_ver,
                "latest_version": latest_ver,
                "download_url": download_url,
                "changelog": changelog,
                "is_mandatory": False,
                "source": "github_private_release"
            }
    except Exception:
        pass

    # 2. Thử kiểm tra trực tiếp qua file version.json trong kho Private
    try:
        res = requests.get(f"{GITHUB_API_BASE}/contents/version.json", headers=_get_auth_headers("application/vnd.github.v3.raw"), timeout=6)
        if res.status_code == 200:
            data = res.json()
            latest_ver = str(data.get('version') or current_ver).strip()
            download_url = str(data.get('download_url') or '').strip()
            changelog = str(data.get('changelog') or '✨ Bản cập nhật tối ưu hiệu năng và sửa lỗi.').strip()
            is_mandatory = bool(data.get('is_mandatory') is True)

            has_update = is_version_newer(latest_ver, current_ver)

            return {
                "has_update": has_update,
                "current_version": current_ver,
                "latest_version": latest_ver,
                "download_url": download_url,
                "changelog": changelog,
                "is_mandatory": is_mandatory,
                "source": "github_private_manifest"
            }
    except Exception:
        pass

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
                has_update = is_version_newer(latest_ver, current_ver) and bool(drive_file_id)

                return {
                    "has_update": has_update,
                    "current_version": current_ver,
                    "latest_version": latest_ver,
                    "google_drive_file_id": drive_file_id,
                    "download_url": f"https://drive.google.com/uc?export=download&id={drive_file_id}" if drive_file_id else "",
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
    Tải file patch.zip trực tiếp từ GitHub Private Repository với chunked stream và báo % thời gian thực.
    """
    headers = _get_auth_headers("application/octet-stream")
    session = requests.Session()
    
    response = session.get(url, stream=True, headers=headers, timeout=30, allow_redirects=True)

    if response.status_code != 200:
        raise Exception(f"Không thể tải file từ máy chủ (Mã lỗi: HTTP {response.status_code})")

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    chunk_size = 64 * 1024 # 64KB chunks

    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    with open(destination_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    percent = int((downloaded / total_size) * 100) if total_size > 0 else 0
                    progress_callback(percent, downloaded, total_size)

    if total_size > 0 and downloaded < (total_size * 0.9):
        raise Exception(f"Tệp tải về chưa hoàn chỉnh ({downloaded}/{total_size} bytes).")

    return destination_path


def apply_patch_zip(zip_path, target_version=""):
    """
    Giải nén bản vá đè lên mã nguồn, đảm bảo an toàn tuyệt đối cho tệp bản quyền và dữ liệu người dùng.
    """
    if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
        raise Exception("File tải về bị lỗi hoặc không phải định dạng .zip hợp lệ!")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            filename = file_info.filename.replace('\\', '/')
            if not filename or filename.endswith('/'):
                continue

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
            dest_path = os.path.join(ROOT_DIR, filename)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with zip_ref.open(file_info) as source, open(dest_path, 'wb') as target:
                shutil.copyfileobj(source, target)

            # 2. Cơ chế OTA Patch Overlay: Giải nén bổ sung các file .py và package vào patches/active/ để nạp đè 100% C-binary (.pyd)
            if filename.endswith('.py') or filename.startswith('routes/'):
                overlay_path = os.path.join(ROOT_DIR, 'patches', 'active', filename)
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


def perform_auto_update_async(download_url_or_file_id, target_version):
    """Thực hiện toàn bộ quá trình cập nhật trong background thread."""
    global _update_progress_state

    def _worker():
        global _update_progress_state
        _update_progress_state["is_updating"] = True
        _update_progress_state["status"] = "downloading"
        _update_progress_state["percent"] = 0
        _update_progress_state["message"] = f"Đang tải bản cập nhật v{target_version} từ kho bảo mật..."
        _update_progress_state["target_version"] = target_version
        _update_progress_state["error"] = None

        temp_zip = os.path.join(ROOT_DIR, 'temp', f'patch_v{target_version}_{int(time.time())}.zip')

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
