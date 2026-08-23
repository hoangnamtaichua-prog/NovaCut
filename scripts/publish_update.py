# -*- coding: utf-8 -*-
"""
NovaCut 1-Click Auto-Publish Patch to Google Drive & Google Sheet
Tự động đóng gói bản vá siêu nhẹ (.zip), tải trực tiếp lên Google Drive và ghi vào Google Sheet qua Webhook.
"""

import os
import sys
import json
import base64
import zipfile
import argparse
import requests
import io

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import license_manager

# Danh sách các tệp mã nguồn và tài nguyên cần đưa vào bản vá
PATCH_FILES = [
    "license_manager.py",
    "web_app.py",
    "auto_edit_pipeline.py",
    "ai_dubbing.py",
    "updater.py",
    "prompt_vault.py",
    "asr_manager.py",
    "asr_inference.py",
    "capcut_sync.py",
    "downloader.py",
    "ffmpeg_installer.py",
    "ocr_module.py",
    "custom_voices.py",
    "review_phim.py",
    "timeline_sanitizer.py",
    "vietnamese_text_normalizer.py",
    "local_voice_engine.py",
    "rvc_bridge.py",
    "tts_cli.py"
]

PATCH_DIRS = [
    "web",
    "routes"
]

EXCLUDE_EXTENSIONS = ('.pyc', '.log', '.wav', '.mp4', '.mkv', '.avi', '.mp3')
EXCLUDE_DIR_NAMES = ('__pycache__', 'outputs', 'samples')

def build_patch_zip(version):
    """Đóng gói các tệp mã nguồn thay đổi thành file zip siêu nhẹ."""
    release_dir = os.path.join(ROOT_DIR, "release")
    os.makedirs(release_dir, exist_ok=True)
    zip_path = os.path.join(release_dir, f"NovaCut_Patch_v{version}.zip")

    print(f"[PATCH] Dang dong goi ban va v{version} -> {zip_path}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        # File đơn lẻ
        for f in PATCH_FILES:
            full = os.path.join(ROOT_DIR, f)
            if os.path.exists(full):
                z.write(full, f)
        
        # Thư mục
        for d in PATCH_DIRS:
            d_full = os.path.join(ROOT_DIR, d)
            if os.path.exists(d_full):
                for root, _, files in os.walk(d_full):
                    # Bỏ qua các thư mục tạm
                    if any(ex in root for ex in EXCLUDE_DIR_NAMES):
                        continue
                    for file in files:
                        if file.endswith(EXCLUDE_EXTENSIONS):
                            continue
                        f_path = os.path.join(root, file)
                        rel_path = os.path.relpath(f_path, ROOT_DIR)
                        z.write(f_path, rel_path)

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"[PATCH] Da tao xong file zip sieu nhe: {size_kb:.2f} KB")
    return zip_path

def publish_to_cloud(zip_path, version, changelog, is_mandatory=False):
    """Gửi bản vá lên Google Apps Script để tự tạo file Google Drive & điền Google Sheet."""
    cfg = license_manager.load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('api_secret_token', 'AMS_SECURE_TOKEN_2026_@DEEPMIND_ANTIGRAVITY')

    if not gas_url:
        print("[ERROR] Chua cau hinh google_apps_script_url trong license_config.json!")
        return False

    print(f"[CLOUD] Dang ma hoa Base64 va tai len Google Drive qua Apps Script...")
    with open(zip_path, 'rb') as f:
        file_base64 = base64.b64encode(f.read()).decode('ascii')

    payload = {
        "action": "publish_patch",
        "token": token,
        "version": version,
        "changelog": changelog,
        "is_mandatory": is_mandatory,
        "file_name": os.path.basename(zip_path),
        "file_base64": file_base64
    }

    try:
        res = requests.post(gas_url, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            if data.get('success'):
                print("=" * 60)
                print(f"[SUCCESS] {data.get('message')}")
                print(f" - Phien ban moi       : v{data.get('version')}")
                print(f" - Google Drive File ID: {data.get('google_drive_file_id')}")
                print(f" - Download URL        : {data.get('download_url')}")
                print("=" * 60)
                return True
            else:
                print(f"[ERROR] Apps Script tra ve loi: {data.get('error')}")
                return False
        else:
            print(f"[ERROR] HTTP {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Loi ket noi Cloud: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="NovaCut 1-Click Auto-Publish Patch")
    parser.add_argument("--version", default="1.0.1", help="Phien ban moi (e.g. 1.0.1)")
    parser.add_argument("--changelog", default="Cap nhat tai khoan TPBank, toi uu giao dien va co che ban quyen Windows Sandbox.", help="Noi dung cap nhat")
    parser.add_argument("--mandatory", action="store_true", help="Bat buoc nguoi dung phai cap nhat")

    args = parser.parse_args()
    zip_path = build_patch_zip(args.version)
    publish_to_cloud(zip_path, args.version, args.changelog, is_mandatory=args.mandatory)

if __name__ == '__main__':
    main()
