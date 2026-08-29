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
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

def get_github_token(cli_token=None):
    """Lấy token GitHub từ CLI, biến môi trường hoặc file .github_token."""
    token = (cli_token or "").strip()
    if not token:
        token = os.environ.get("NOVACUT_GITHUB_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token_file = os.path.join(ROOT_DIR, ".github_token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    token = f.read().strip()
            except Exception:
                pass
    return token

GITHUB_TOKEN = get_github_token()

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
    ".prompt_vault.dat",
    "asr_manager.py",
    "asr_inference.py",
    "capcut_sync.py",
    "downloader.py",
    "douyin_browser_downloader.py",
    "ffmpeg_installer.py",
    "ocr_module.py",
    "custom_voices.py",
    "custom_voices.json",
    "review_phim.py",
    "review_styles.py",
    "batch_queue_manager.py",
    "timeline_sanitizer.py",
    "vietnamese_text_normalizer.py",
    "local_voice_engine.py",
    "rvc_bridge.py",
    "audio_separator.py",
    "mdx_separator.py",
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
    ".last_sync_state.dat",
    "api_keys.txt",
    "license_config.json",
    "projects",
    "movies",
    "downloads",
    "output",
    "outputs",
    "tiktok_output",
    "temp",
    "scratch",
    "models",
    "voices",
    "build",
    "dist",
    "patches",
    "release",
    ".system_generated",
    "tts_cache",
    "temp_uploads",
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

    log(f"Đang đóng gói bản vá patch.zip sạch cho phiên bản v{target_version}...")

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
                norm_root = root.replace('\\', '/')
                if 'tts_cache' in norm_root or 'outputs' in norm_root or 'temp_uploads' in norm_root:
                    continue
                for file in files:
                    if file.endswith('.pyc') or file.endswith('.log') or file.startswith('.'):
                        continue
                    if file.endswith(('.exe', '.wav', '.mp3', '.mp4', '.mkv', '.avi', '.zip', '.tar', '.gz')):
                        if norm_root.endswith('web/samples') and not file.startswith('clean_') and file.endswith(('.wav', '.mp3')):
                            pass
                        else:
                            continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, ROOT_DIR)
                    zipf.write(full_path, arcname=rel_path)

    zip_size_mb = os.path.getsize(PATCH_ZIP) / (1024 * 1024)
    log(f"✅ Đã tạo file patch.zip thành công! Dung lượng siêu nhẹ: {zip_size_mb:.2f} MB")
    return PATCH_ZIP


import hashlib


def compute_file_sha256(filepath):
    """Tính toán mã băm SHA-256 chuẩn của tệp nhị phân."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def update_version_manifest(version, changelog, sha256_hash=""):
    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/patch.zip"

    manifest = {
        "version": version,
        "download_url": download_url,
        "sha256": sha256_hash,
        "changelog": changelog,
        "is_mandatory": False,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log(f"✅ Đã cập nhật version.json lên phiên bản v{version} (SHA256: {sha256_hash[:12]}...)!")
    return manifest


def upload_github_release(version, changelog, patch_path, sha256_hash="", token=""):
    """
    Tự động tạo Release và Upload patch.zip lên GitHub Repository qua API.
    """
    auth_token = (token or GITHUB_TOKEN).strip()
    if not auth_token:
        log("⚠️ LƯU Ý: Chưa có GitHub Personal Access Token để tạo Release tự động!")
        log("   👉 Cách 1: Truyền token khi chạy: python scripts/publish_patch.py --version " + version + " --token <TOKEN_CỦA_BẠN>")
        log("   👉 Cách 2: Lưu token vào file .github_token tại thư mục dự án.")
        log("   👉 Hoặc tạo Release thủ công trên GitHub: https://github.com/" + GITHUB_REPO + "/releases/new (đính kèm release/patch.zip)")
        return False

    headers = {
        "Authorization": f"token {auth_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "NovaCut-Publisher/1.0"
    }

    tag_name = f"v{version}" if not version.startswith("v") else version
    release_name = f"NovaCut Patch {tag_name}"

    body_text = changelog
    if sha256_hash and "SHA-256:" not in body_text:
        body_text = f"{changelog}\n\n**Checksum:**\n`SHA-256: {sha256_hash}`"

    log(f"Đang kết nối GitHub API để tạo Release {tag_name} trên kho...")

    # 1. Kiểm tra xem release này đã tồn tại chưa
    rel_id = None
    upload_url_template = None
    
    r_check = requests.get(f"{GITHUB_API_BASE}/releases/tags/{tag_name}", headers=headers)
    if r_check.status_code == 200:
        rel_data = r_check.json()
        rel_id = rel_data.get("id")
        upload_url_template = rel_data.get("upload_url")
        log(f" -> Release {tag_name} đã tồn tại (ID: {rel_id}), tiến hành cập nhật...")
        requests.patch(f"{GITHUB_API_BASE}/releases/{rel_id}", headers=headers, json={"body": body_text, "name": release_name})
    else:
        # Tạo release mới
        payload = {
            "tag_name": tag_name,
            "target_commitish": "main",
            "name": release_name,
            "body": body_text,
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
        log(f"✅ Đã tạo Release {tag_name} thành công (ID: {rel_id})!")

    # 2. Xóa các asset cũ nếu đã có
    r_assets = requests.get(f"{GITHUB_API_BASE}/releases/{rel_id}/assets", headers=headers)
    existing_assets = {}
    if r_assets.status_code == 200:
        for a in r_assets.json():
            existing_assets[a.get("name")] = a.get("id")

    files_to_upload = [("patch.zip", patch_path, "application/zip")]
    
    setup_exe = os.path.join(RELEASE_DIR, f"NovaCut_Setup_v{version}.exe")
    if not os.path.exists(setup_exe):
        setup_exe = os.path.join(ROOT_DIR, "release", f"NovaCut_Setup_v{version}.exe")
    if os.path.exists(setup_exe):
        files_to_upload.append((f"NovaCut_Setup_v{version}.exe", setup_exe, "application/vnd.microsoft.portable-executable"))

    portable_zip = os.path.join(ROOT_DIR, "release", f"NovaCut_v{version}_Portable.zip")
    if os.path.exists(portable_zip):
        files_to_upload.append((f"NovaCut_v{version}_Portable.zip", portable_zip, "application/zip"))

    for asset_name, asset_file, content_type in files_to_upload:
        if asset_name in existing_assets:
            log(f" -> Đang xóa asset cũ {asset_name} (ID: {existing_assets[asset_name]})...")
            requests.delete(f"{GITHUB_API_BASE}/releases/assets/{existing_assets[asset_name]}", headers=headers)

        upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{rel_id}/assets?name={asset_name}"
        upload_headers = {
            "Authorization": f"token {auth_token}",
            "Content-Type": content_type,
            "User-Agent": "NovaCut-Publisher/1.0"
        }
        log(f"Đang tải {asset_name} lên GitHub Release ({os.path.getsize(asset_file)/(1024*1024):.2f} MB)...")
        with open(asset_file, "rb") as f:
            r_up = requests.post(upload_url, headers=upload_headers, data=f)
        if r_up.status_code in (200, 201):
            log(f"🎉 ĐÃ TẢI {asset_name} THÀNH CÔNG!")
        else:
            log(f"⚠️ Lỗi upload {asset_name} (HTTP {r_up.status_code}): {r_up.text[:200]}")

    return True


def git_push_changes(version):
    """Tự động commit và push thay đổi lên GitHub qua git."""
    try:
        log("Đang đồng bộ mã nguồn và version.json lên GitHub repo...")
        subprocess.run(["git", "add", "."], cwd=ROOT_DIR, check=True)
        subprocess.run(["git", "commit", "-m", f"Release patch v{version}"], cwd=ROOT_DIR, check=False)
        res = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res.returncode == 0:
            log("✅ Đã push thành công lên GitHub origin main!")
        else:
            log(f"⚠️ Git push notice: {res.stderr or res.stdout}")
    except Exception as e:
        log(f"⚠️ Lỗi git push: {e}")


def main():
    parser = argparse.ArgumentParser(description="NovaCut Auto-Update Patch Publisher")
    parser.add_argument("--version", type=str, help="Số phiên bản mới (vd: 1.0.1 hoặc 1.2.2)")
    parser.add_argument("--changelog", type=str, help="Nội dung thay đổi / tính năng mới")
    parser.add_argument("--token", type=str, help="GitHub Personal Access Token (PAT)")
    args = parser.parse_args()

    token = get_github_token(args.token)
    cur_ver = get_current_version()
    print("=" * 65)
    print("🚀 NOVACUT 1-CLICK AUTO-UPDATE PUBLISHER")
    print("=" * 65)
    print(f"🔒 Kho GitHub        : {GITHUB_REPO}")
    print(f"📌 Phiên bản hiện tại: v{cur_ver}")

    new_ver = args.version or cur_ver
    existing_changelog = ""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                existing_changelog = json.load(f).get("changelog", "")
        except Exception:
            pass

    changelog = args.changelog or existing_changelog or f"✨ Bản cập nhật v{new_ver}:\n- Tối ưu hóa hiệu năng và cải tiến giao diện.\n- Tích hợp Offline Clone Voice và Live Dubbing."

    print(f"🎯 Phiên bản phát hành : v{new_ver}")
    print(f"📝 Nội dung Changelog  :\n{changelog}")
    print("-" * 65)

    # 1. Đóng gói patch.zip
    patch_path = build_patch_zip(new_ver)
    patch_sha256 = compute_file_sha256(patch_path)
    log(f"🔑 SHA-256 Checksum: {patch_sha256}")

    # 2. Cập nhật version.json với SHA-256 và download_url
    update_version_manifest(new_ver, changelog, patch_sha256)

    # 3. Đẩy code lên GitHub
    git_push_changes(new_ver)

    # 4. Tự động tạo Release và Upload patch.zip lên GitHub
    upload_github_release(new_ver, changelog, patch_path, patch_sha256, token=token)

    print("=" * 65)
    print(f"🎉 ĐÃ PHÁT HÀNH BẢN CẬP NHẬT v{new_ver} LÊN GITHUB THÀNH CÔNG!")
    print("=" * 65)
    print("👉 Bây giờ, bất kỳ người dùng nào mở app NovaCut lên:")
    print(f"   1. App sẽ tự động phát hiện phiên bản mới: v{new_ver}")
    print("   2. Khách bấm [🚀 Cập Nhật Ngay] -> Tự động tải patch.zip và nâng cấp trong 2 giây!")
    print(f"   3. Mã SHA-256 đối soát: {patch_sha256[:16]}...")


if __name__ == "__main__":
    main()
