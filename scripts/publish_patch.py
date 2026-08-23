# -*- coding: utf-8 -*-
"""
Script 1-Click Auto-Publisher Cho Kho GitHub Private (NovaCut Private Release Publisher)
Dành cho máy Dev:
1. Đóng gói patch.zip (< 25MB).
2. Cập nhật version.json.
3. Tự động đẩy Git commit lên kho Private.
4. Tự động tạo GitHub Release và tải patch.zip lên kho Private qua GitHub API (Không cần mở trình duyệt!).
"""

import os
import sys
import json
import time
import zipfile
import shutil
import subprocess
import argparse
import requests

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT_DIR, "version.json")
RELEASE_DIR = os.path.join(ROOT_DIR, "release")
PATCH_ZIP = os.path.join(RELEASE_DIR, "patch.zip")

GITHUB_REPO = "hoangnamtaichua-prog/NovaCut"
GITHUB_TOKEN = "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"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

PATCH_INCLUDE_DIRS = [
    "web",
    "resources",
    "routes"
]

PATCH_INCLUDE_FILES = [
    "web_app.py",
    "auto_edit_pipeline.py",
    "ai_dubbing.py",
    "license_manager.py",
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
    "audio_separator.py",
    "requirements.txt",
    "version.json"
]

PATCH_EXCLUDES = [
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".license.dat",
    ".processed_txs.dat",
    ".token_quota.dat",
    "api_keys.txt",
    "license_config.json",
    "projects",
    "movies",
    "downloads",
    "output",
    "tiktok_output",
    "temp",
    "scratch",
    "models",
    "voices",
    "build",
    "dist",
    ".system_generated",
    "*.log"
]


def log(msg):
    print(f"[PUBLISH] {msg}")


def get_current_version():
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "1.0.0")
        except Exception:
            pass
    return "1.0.0"


def increment_version(ver_str):
    parts = ver_str.split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except Exception:
            pass
    return f"{ver_str}.1"


def build_patch_zip(target_version):
    os.makedirs(RELEASE_DIR, exist_ok=True)
    if os.path.exists(PATCH_ZIP):
        try:
            os.remove(PATCH_ZIP)
        except Exception:
            pass

    log(f"Đang đóng gói bản vá patch.zip cho phiên bản v{target_version}...")

    with zipfile.ZipFile(PATCH_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for f in PATCH_INCLUDE_FILES:
            src = os.path.join(ROOT_DIR, f)
            if os.path.exists(src):
                zipf.write(src, arcname=f)

        for d in PATCH_INCLUDE_DIRS:
            src_dir = os.path.join(ROOT_DIR, d)
            if not os.path.exists(src_dir):
                continue
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [sub for sub in dirs if sub not in PATCH_EXCLUDES and not sub.startswith('.')]
                for file in files:
                    if file.endswith('.pyc') or file.endswith('.log') or file.startswith('.'):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, ROOT_DIR)
                    zipf.write(full_path, arcname=rel_path)

    zip_size_mb = os.path.getsize(PATCH_ZIP) / (1024 * 1024)
    log(f"✅ Đã tạo file patch.zip thành công! Dung lượng: {zip_size_mb:.2f} MB")
    return PATCH_ZIP


def update_version_manifest(version, changelog):
    download_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/assets/latest"

    manifest = {
        "version": version,
        "download_url": download_url,
        "changelog": changelog,
        "is_mandatory": False,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log(f"✅ Đã cập nhật version.json lên phiên bản v{version}!")
    return manifest


def upload_github_release(version, changelog, patch_path):
    """
    Tự động tạo Release và Upload patch.zip lên GitHub Private Repository qua API.
    """
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "NovaCut-Publisher/1.0"
    }

    tag_name = f"v{version}" if not version.startswith("v") else version
    release_name = f"NovaCut Patch {tag_name}"

    log(f"Đang kết nối GitHub API để tạo Release {tag_name} trên kho Private...")

    # 1. Kiểm tra xem release này đã tồn tại chưa
    rel_id = None
    upload_url_template = None
    
    r_check = requests.get(f"{GITHUB_API_BASE}/releases/tags/{tag_name}", headers=headers)
    if r_check.status_code == 200:
        rel_data = r_check.json()
        rel_id = rel_data.get("id")
        upload_url_template = rel_data.get("upload_url")
        log(f" -> Release {tag_name} đã tồn tại (ID: {rel_id}), tiến hành cập nhật...")
    else:
        # Tạo release mới
        payload = {
            "tag_name": tag_name,
            "target_commitish": "main",
            "name": release_name,
            "body": changelog,
            "draft": False,
            "prerelease": False
        }
        r_create = requests.post(f"{GITHUB_API_BASE}/releases", headers=headers, json=payload)
        if r_create.status_code not in (200, 201):
            log(f"⚠️ Không thể tạo release mới qua API (HTTP {r_create.status_code}): {r_create.text}")
            return False
        rel_data = r_create.json()
        rel_id = rel_data.get("id")
        upload_url_template = rel_data.get("upload_url")
        log(f"✅ Đã tạo Release {tag_name} thành công trên kho Private (ID: {rel_id})!")

    # 2. Xóa asset patch.zip cũ nếu đã có
    r_assets = requests.get(f"{GITHUB_API_BASE}/releases/{rel_id}/assets", headers=headers)
    if r_assets.status_code == 200:
        for a in r_assets.json():
            if a.get("name") == "patch.zip":
                log(f" -> Đang xóa file patch.zip cũ (Asset ID: {a.get('id')})...")
                requests.delete(f"{GITHUB_API_BASE}/releases/assets/{a.get('id')}", headers=headers)

    # 3. Upload file patch.zip mới lên
    upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{rel_id}/assets?name=patch.zip"
    upload_headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/zip",
        "User-Agent": "NovaCut-Publisher/1.0"
    }

    log(f"Đang tải file patch.zip lên GitHub Private Release ({os.path.getsize(patch_path)/(1024*1024):.2f} MB)...")
    with open(patch_path, "rb") as f:
        r_up = requests.post(upload_url, headers=upload_headers, data=f)

    if r_up.status_code in (200, 201):
        log(f"🎉 TẢI LÊN GITHUB PRIVATE RELEASE THÀNH CÔNG 100%!")
        return True
    else:
        log(f"⚠️ Lỗi upload asset lên GitHub (HTTP {r_up.status_code}): {r_up.text}")
        return False


def git_push_changes(version):
    """Tự động commit và push thay đổi lên GitHub qua git."""
    try:
        log("Đang đồng bộ mã nguồn và version.json lên GitHub Private repo...")
        subprocess.run(["git", "add", "."], cwd=ROOT_DIR, check=True)
        subprocess.run(["git", "commit", "-m", f"Release patch v{version}"], cwd=ROOT_DIR, check=False)
        res = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res.returncode == 0:
            log("✅ Đã push thành công lên GitHub origin main!")
        else:
            log(f"⚠️ Git push output: {res.stderr or res.stdout}")
    except Exception as e:
        log(f"⚠️ Lỗi git push: {e}")


def main():
    parser = argparse.ArgumentParser(description="NovaCut Private Auto-Update Patch Publisher")
    parser.add_argument("--version", type=str, help="Số phiên bản mới (vd: 1.0.1 hoặc 1.0.2)")
    parser.add_argument("--changelog", type=str, help="Nội dung thay đổi / tính năng mới")
    args = parser.parse_args()

    cur_ver = get_current_version()
    print("=" * 65)
    print("🚀 NOVACUT 1-CLICK PRIVATE AUTO-UPDATE PUBLISHER")
    print("=" * 65)
    print(f"🔒 Kho GitHub Private: {GITHUB_REPO}")
    print(f"📌 Phiên bản hiện tại : v{cur_ver}")

    new_ver = args.version or increment_version(cur_ver)
    changelog = args.changelog or f"✨ Bản cập nhật v{new_ver}:\n- Tối ưu hóa hiệu năng và cải tiến giao diện.\n- Tích hợp Offline Clone Voice và Live Dubbing."

    print(f"🎯 Phiên bản phát hành : v{new_ver}")
    print(f"📝 Nội dung Changelog  :\n{changelog}")
    print("-" * 65)

    # 1. Cập nhật version.json
    update_version_manifest(new_ver, changelog)

    # 2. Đóng gói patch.zip
    patch_path = build_patch_zip(new_ver)

    # 3. Đẩy code lên GitHub Private
    git_push_changes(new_ver)

    # 4. Tự động tạo Release và Upload patch.zip lên GitHub Private
    upload_github_release(new_ver, changelog, patch_path)

    print("=" * 65)
    print(f"🎉 ĐÃ PHÁT HÀNH BẢN CẬP NHẬT v{new_ver} LÊN KHO PRIVATE THÀNH CÔNG!")
    print("=" * 65)
    print("👉 Bây giờ, bất kỳ người dùng nào mở app NovaCut lên:")
    print(f"   1. App sẽ tự động phát hiện phiên bản mới: v{new_ver}")
    print("   2. Khách bấm [🚀 Cập Nhật Ngay] -> Tự động tải patch.zip và nâng cấp trong 2 giây!")
    print("   3. Kho GitHub của bạn vẫn là PRIVATE 100%, không ai nhìn thấy mã nguồn.")


if __name__ == "__main__":
    main()
