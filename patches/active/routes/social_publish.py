# -*- coding: utf-8 -*-
"""
NovaCut Social Media Video Publisher Routes
Cung cấp các API endpoint cho tính năng Đăng video lên mạng xã hội:
- GET  /api/social/platforms : Danh sách các nền tảng được hỗ trợ
- GET  /api/social/profiles  : Quét danh sách Google Chrome Profile
- POST /api/social/prepare   : Chuẩn hóa & xem trước nội dung đăng
- POST /api/social/open      : Khởi chạy Chrome mở trang upload với Profile đã chọn
- GET  /api/social/status    : Trạng thái môi trường & phân quyền bản quyền
- GET  /api/social/history   : Lịch sử thao tác đăng video
- POST /api/social/history/clear : Xóa lịch sử thao tác
- Các workflow và OAuth endpoints:
  - POST   /api/social/workflow/plan
  - GET    /api/social/workflow/jobs/<job_id>
  - POST   /api/social/workflow/jobs/<job_id>/copy
  - POST   /api/social/workflow/jobs/<job_id>/publish
  - POST   /api/social/workflow/jobs/<job_id>/publish_async
  - POST   /api/social/workflow/jobs/<job_id>/platforms/<platform_id>/publish
  - GET    /api/social/workflow/connections
  - POST   /api/social/workflow/connections
  - DELETE /api/social/workflow/connections/<connection_id>
  - GET    /api/social/oauth/start
  - GET    /api/social/oauth/callback
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.parse
from flask import Blueprint, jsonify, request, render_template_string

import social_publisher
from routes.security import is_path_allowed, register_user_path
import license_manager
import social_workflow
import social_adapters
import social_tokens

social_publish_bp = Blueprint("social_publish", __name__)
logger = logging.getLogger("social_publish")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _check_social_license():
    """Enforce License & Feature Permission Enforcement Rule on all backend endpoints."""
    allowed, reason, _ = license_manager.check_permission("can_access_social_publish")
    if not allowed:
        return False, reason
    return True, None


@social_publish_bp.route("/api/social/workflow/plan", methods=["POST"])
def create_social_publish_plan():
    """Create a persistent one-video/multi-platform plan for review or publishing."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    try:
        data = request.json or {}
        video_path = os.path.abspath(str(data.get("video_path") or "").strip())
        ext = os.path.splitext(video_path)[1].lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            return jsonify({"success": False, "error": "Định dạng video không được hỗ trợ."}), 400
        job = social_workflow.create_publish_plan(
            video_path,
            data.get("title_template"),
            data.get("platform_ids") or list(social_publisher.SUPPORTED_PLATFORMS),
            use_ai=bool(data.get("use_ai", True)),
            connection_ids=data.get("connection_ids") or [],
        )
        return jsonify({"success": True, "job": job}), 201
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("Lỗi tạo publish plan: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Không thể tạo kế hoạch đăng."}), 500


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>", methods=["GET"])
def get_social_publish_job(job_id):
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    job = social_workflow.get_publish_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Không tìm thấy job."}), 404
    return jsonify({"success": True, "job": job})


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>/copy", methods=["POST"])
def update_social_job_copy(job_id):
    """Allows user to customize title, caption, hashtags or target connection for a platform."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    data = request.json or {}
    platform_id = data.get("platform_id")
    if not platform_id:
        return jsonify({"success": False, "error": "Thiếu mã nền tảng"}), 400
    try:
        updated = social_workflow.update_platform_copy(
            job_id,
            platform_id,
            title=data.get("title"),
            caption=data.get("caption"),
            hashtags=data.get("hashtags"),
            connection_id=data.get("connection_id"),
        )
        if not updated:
            return jsonify({"success": False, "error": "Không tìm thấy job"}), 404
        return jsonify({"success": True, "job": updated})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("Lỗi cập nhật copy bài đăng: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Không thể cập nhật nội dung"}), 500


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>/platforms/<platform_id>", methods=["PATCH"])
def update_social_platform_status(job_id, platform_id):
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403
    return jsonify({"success": False, "error": "Trạng thái đăng chỉ được cập nhật từ adapter đã xác minh."}), 405


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>/platforms/<platform_id>/publish", methods=["POST"])
def publish_social_platform(job_id, platform_id):
    """Run one official adapter and persist its confirmed result/state."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    job = social_workflow.get_publish_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Không tìm thấy job."}), 404
    item = next((p for p in job.get("platforms", []) if p.get("platform_id") == platform_id), None)
    if not item:
        return jsonify({"success": False, "error": "Nền tảng không nằm trong job."}), 404
    result = social_adapters.publish(job, item)
    updated = social_workflow.update_platform_status(job_id, platform_id, result.status, result.remote_id, result.url, result.message)
    return jsonify({"success": result.status == "PUBLISHED", "result": result.to_dict(), "job": updated}), (200 if result.status == "PUBLISHED" else 409)


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>/publish", methods=["POST"])
def publish_social_job(job_id):
    """Attempt every READY platform independently; return a complete report."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    job = social_workflow.get_publish_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Không tìm thấy job."}), 404
    results = []
    for item in job.get("platforms", []):
        if item.get("status") in {"PUBLISHED", "PROCESSING", "UPLOADING"}:
            continue
        result = social_adapters.publish(job, item)
        social_workflow.update_platform_status(job_id, item["platform_id"], result.status, result.remote_id, result.url, result.message)
        results.append({"platform_id": item["platform_id"], **result.to_dict()})
    updated = social_workflow.get_publish_job(job_id)
    return jsonify({"success": updated["status"] == "PUBLISHED", "results": results, "job": updated})


@social_publish_bp.route("/api/social/workflow/jobs/<job_id>/publish_async", methods=["POST"])
def publish_social_job_async(job_id):
    """Start asynchronous background publish worker for the job."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    job = social_workflow.get_publish_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Không tìm thấy job."}), 404
    data = request.json or {}
    platform_ids = data.get("platform_ids")
    try:
        social_workflow.start_background_publish(job_id, platform_ids)
        return jsonify({"success": True, "message": "Đã bắt đầu đăng nền tảng trong luồng ngầm."})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@social_publish_bp.route("/api/social/workflow/connections", methods=["GET", "POST"])
def social_workflow_connections():
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    if request.method == "GET":
        return jsonify({"success": True, "connections": social_workflow.list_connections()})
    try:
        data = request.json or {}
        connection = social_workflow.save_connection(
            data.get("platform_id"),
            data.get("account_label"),
            data.get("profile_id"),
            data.get("capabilities"),
            account_type=data.get("account_type", "chrome_profile"),
            remote_account_id=data.get("remote_account_id"),
            avatar_url=data.get("avatar_url"),
            connection_id=data.get("connection_id"),
        )
        return jsonify({"success": True, "connection": connection}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@social_publish_bp.route("/api/social/workflow/connections/<connection_id>", methods=["DELETE"])
def delete_social_connection(connection_id):
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    success = social_workflow.delete_connection(connection_id)
    if not success:
        return jsonify({"success": False, "error": "Không tìm thấy tài khoản để xóa."}), 404
    return jsonify({"success": True, "message": "Đã xóa tài khoản kết nối và mã ủy quyền thành công."})


# --- OAuth Endpoints ---

@social_publish_bp.route("/api/social/oauth/start", methods=["GET"])
def start_social_oauth():
    """Start OAuth PKCE authorization flow for official API connection."""
    allowed, reason = _check_social_license()
    if not allowed:
        return jsonify({"success": False, "error": reason, "license_error": True}), 403

    platform_id = request.args.get("platform_id", "youtube").strip().lower()
    if platform_id != "youtube":
        return jsonify({"success": False, "error": f"Nền tảng {platform_id} chưa hỗ trợ đăng nhập OAuth tự động."}), 400

    client_id = os.environ.get("NOVACUT_YOUTUBE_CLIENT_ID") or request.args.get("client_id")
    if not client_id:
        return jsonify({
            "success": False,
            "error": "Chưa cấu hình Google Client ID. Vui lòng thiết lập biến môi trường NOVACUT_YOUTUBE_CLIENT_ID hoặc truyền client_id.",
        }), 400

    code_verifier, code_challenge = social_tokens.generate_pkce_pair()
    state = social_tokens.create_oauth_state(platform_id, code_verifier)

    # Google OAuth Authorization URL
    redirect_uri = "http://localhost:5000/api/social/oauth/callback"
    scopes = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return jsonify({"success": True, "auth_url": auth_url, "state": state})


@social_publish_bp.route("/api/social/oauth/callback", methods=["GET"])
def social_oauth_callback():
    """Handle OAuth redirect callback, exchange code, retrieve remote channel identity, and save encrypted token."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    html_template = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>NovaCut - Kết Nối Tài Khoản</title>
<style>
body { background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 32px; max-width: 480px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
h2 { margin-top: 0; color: {{ '#34d399' if success else '#f87171' }}; }
p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
.btn { margin-top: 18px; padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; text-decoration: none; display: inline-block; }
</style>
</head>
<body>
<div class="card">
  <h2>{{ title }}</h2>
  <p>{{ message }}</p>
  <button class="btn" onclick="window.close()">Đóng Cửa Sổ Này</button>
</div>
</body>
</html>"""

    if error:
        return render_template_string(html_template, success=False, title="Ủy Quyền Thất Bại", message=f"Nền tảng báo lỗi: {error}"), 400

    state_data = social_tokens.verify_oauth_state(state) if state else None
    if not state_data:
        return render_template_string(html_template, success=False, title="Phiên Hết Hạn", message="Mã trạng thái OAuth không hợp lệ hoặc đã hết hạn. Vui lòng thử lại từ NovaCut."), 400

    platform_id = state_data["platform_id"]
    code_verifier = state_data["code_verifier"]

    client_id = os.environ.get("NOVACUT_YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("NOVACUT_YOUTUBE_CLIENT_SECRET")
    redirect_uri = "http://localhost:5000/api/social/oauth/callback"

    # Exchange authorization code for tokens
    payload = {
        "client_id": client_id or "",
        "client_secret": client_secret or "",
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    payload = {k: v for k, v in payload.items() if v}

    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))

        access_token = token_resp.get("access_token")
        refresh_token = token_resp.get("refresh_token")
        expires_in = token_resp.get("expires_in", 3600)

        # Retrieve remote channel identity
        ch_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        with urllib.request.urlopen(ch_req, timeout=15) as ch_resp:
            ch_data = json.loads(ch_resp.read().decode("utf-8"))

        items = ch_data.get("items", [])
        if not items:
            return render_template_string(html_template, success=False, title="Không Tìm Thấy Kênh", message="Tài khoản Google này chưa có kênh YouTube nào được khởi tạo."), 400

        snippet = items[0].get("snippet", {})
        channel_id = items[0].get("id")
        channel_title = snippet.get("title") or "YouTube Channel"
        avatar_url = snippet.get("thumbnails", {}).get("default", {}).get("url")

        # Save connection record
        conn = social_workflow.save_connection(
            platform_id="youtube",
            account_label=channel_title,
            profile_id="Default",
            capabilities=["manual_browser", "verified_api"],
            account_type="oauth",
            remote_account_id=channel_id,
            avatar_url=avatar_url,
        )

        # Save encrypted token
        social_tokens.save_token(conn["connection_id"], {
            "platform_id": "youtube",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + expires_in,
            "remote_account_id": channel_id,
            "account_title": channel_title,
        })

        return render_template_string(
            html_template,
            success=True,
            title="Kết Nối Kênh Thành Công! 🎉",
            message=f"Đã liên kết kênh YouTube '{channel_title}' ({channel_id}) với NovaCut. Bạn có thể đóng tab này và bắt đầu xuất bản video.",
        )
    except Exception as exc:
        logger.error("Lỗi hoàn tất OAuth callback: %s", exc, exc_info=True)
        return render_template_string(html_template, success=False, title="Lỗi Kết Nối", message=f"Không thể hoàn tất ủy quyền: {exc}"), 500


# --- Original Routes Preserved ---

@social_publish_bp.route("/api/social/platforms", methods=["GET"])
def get_platforms():
    """Trả về danh sách các mạng xã hội được hỗ trợ kèm cấu hình từng nền tảng."""
    try:
        platforms_list = list(social_publisher.SUPPORTED_PLATFORMS.values())
        return jsonify({
            "success": True,
            "platforms": platforms_list,
            "total": len(platforms_list),
        })
    except Exception as e:
        logger.error(f"Lỗi nạp danh sách nền tảng: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"Lỗi nạp nền tảng: {str(e)}"}), 500


@social_publish_bp.route("/api/social/profiles", methods=["GET"])
def get_chrome_profiles():
    """Dò tìm Google Chrome và quét danh sách profile người dùng."""
    try:
        chrome_exe = social_publisher.find_chrome_executable()
        has_chrome = bool(chrome_exe and os.path.isfile(chrome_exe))
        profiles = social_publisher.list_chrome_profiles() if has_chrome else []

        return jsonify({
            "success": True,
            "chrome_installed": has_chrome,
            "chrome_path": chrome_exe or "",
            "profiles": profiles,
            "default_profile": profiles[0]["id"] if profiles else "Default",
        })
    except Exception as e:
        logger.error(f"Lỗi quét profile Chrome: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"Lỗi quét profile: {str(e)}"}), 500


@social_publish_bp.route("/api/social/prepare", methods=["POST"])
def prepare_social_post():
    """
    Tiếp nhận thông tin bài đăng, kiểm tra tệp video và định dạng nội dung xem trước (Review Step).
    """
    try:
        data = request.json or {}
        platform_id = str(data.get("platform_id") or "youtube").strip()
        video_path = str(data.get("video_path") or "").strip()
        title = str(data.get("title") or "").strip()
        description = str(data.get("description") or "").strip()
        caption = str(data.get("caption") or "").strip()
        hashtags = data.get("hashtags") or ""
        privacy = str(data.get("privacy") or "public").strip()

        if platform_id not in social_publisher.SUPPORTED_PLATFORMS:
            return jsonify({
                "success": False,
                "error": f"Nền tảng '{platform_id}' không tồn tại hoặc chưa được hỗ trợ.",
            }), 400

        video_info = None
        if video_path:
            norm_video_path = os.path.abspath(video_path)
            ext = os.path.splitext(norm_video_path)[1].lower()

            if ext not in ALLOWED_VIDEO_EXTENSIONS:
                return jsonify({
                    "success": False,
                    "error": f"Định dạng tệp '{ext}' không được hỗ trợ. Vui lòng chọn tệp video ({', '.join(ALLOWED_VIDEO_EXTENSIONS)}).",
                }), 400

            if not os.path.isfile(norm_video_path):
                return jsonify({
                    "success": False,
                    "error": f"Tệp video không tồn tại trên ổ đĩa: {video_path}",
                }), 404

            register_user_path(norm_video_path)

            if not is_path_allowed(norm_video_path, must_exist=True):
                return jsonify({
                    "success": False,
                    "error": "Đường dẫn tệp nằm ngoài phạm vi được phép truy cập.",
                }), 403

            size_bytes = os.path.getsize(norm_video_path)
            size_mb = round(size_bytes / (1024 * 1024), 2)
            video_info = {
                "path": norm_video_path,
                "name": os.path.basename(norm_video_path),
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "exists": True,
            }

        prepared = social_publisher.prepare_publish_content(
            platform_id=platform_id,
            title=title,
            description=description,
            caption=caption,
            hashtags=hashtags,
            privacy=privacy,
        )

        return jsonify({
            "success": True,
            "prepared": prepared,
            "video": video_info,
        })
    except Exception as e:
        logger.error(f"Lỗi chuẩn bị nội dung đăng: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_publish_bp.route("/api/social/open", methods=["POST"])
def open_social_platform():
    """
    (Bảo mật & Phân quyền)
    Kiểm tra bản quyền, mở Google Chrome với Profile chỉ định và ghi nhận lịch sử.
    """
    try:
        allowed, reason = _check_social_license()
        if not allowed:
            return jsonify({
                "success": False,
                "error": reason,
                "license_error": True,
            }), 403

        data = request.json or {}
        platform_id = str(data.get("platform_id") or "youtube").strip()
        profile_id = str(data.get("profile_id") or "Default").strip()
        video_path = str(data.get("video_path") or "").strip()
        title = str(data.get("title") or "").strip()
        caption = str(data.get("caption") or "").strip()
        privacy = str(data.get("privacy") or "public").strip()
        copy_video_path = bool(data.get("copy_video_path", True))
        custom_url = str(data.get("custom_url") or "").strip()

        platform = social_publisher.SUPPORTED_PLATFORMS.get(platform_id)
        if not platform:
            return jsonify({"success": False, "error": f"Nền tảng '{platform_id}' không hợp lệ."}), 400

        norm_video_path = ""
        if video_path:
            norm_video_path = os.path.abspath(video_path)
            if not os.path.isfile(norm_video_path):
                return jsonify({"success": False, "error": f"Tệp video không tồn tại: {video_path}"}), 404

            register_user_path(norm_video_path)
            if not is_path_allowed(norm_video_path, must_exist=True):
                return jsonify({"success": False, "error": "Đường dẫn video không được phép."}), 403

        target_url = custom_url or platform.get("upload_url") or platform.get("direct_url")

        success, msg = social_publisher.launch_chrome_with_profile(
            profile_id=profile_id,
            target_url=target_url,
        )

        if not success:
            social_publisher.record_publish_action(
                platform_id=platform_id,
                video_path=norm_video_path,
                title=title,
                caption=caption,
                profile_id=profile_id,
                privacy=privacy,
                status="FAILED",
                message=msg,
            )
            return jsonify({"success": False, "error": msg}), 500

        clipboard_copied = False
        if copy_video_path and norm_video_path:
            clipboard_copied = social_publisher.copy_text_to_windows_clipboard(norm_video_path)

        history_entry = social_publisher.record_publish_action(
            platform_id=platform_id,
            video_path=norm_video_path,
            title=title,
            caption=caption,
            profile_id=profile_id,
            privacy=privacy,
            status="OPENED",
            message="Đã mở Chrome thành công",
        )

        return jsonify({
            "success": True,
            "message": msg,
            "platform_id": platform_id,
            "platform_name": platform.get("name"),
            "target_url": target_url,
            "profile_id": profile_id,
            "clipboard_copied": clipboard_copied,
            "history_entry": history_entry,
        })
    except Exception as e:
        logger.error(f"Lỗi mở mạng xã hội: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_publish_bp.route("/api/social/status", methods=["GET"])
def get_social_status():
    """Trả về trạng thái tổng quan hệ thống đăng video & Chrome."""
    try:
        chrome_exe = social_publisher.find_chrome_executable()
        has_chrome = bool(chrome_exe and os.path.isfile(chrome_exe))
        profiles = social_publisher.list_chrome_profiles() if has_chrome else []
        history = social_publisher.load_publish_history()
        allowed, reason, _ = license_manager.check_permission("can_access_social_publish")

        return jsonify({
            "success": True,
            "chrome_installed": has_chrome,
            "chrome_path": chrome_exe or "",
            "profiles_count": len(profiles),
            "supported_platforms_count": len(social_publisher.SUPPORTED_PLATFORMS),
            "history_count": len(history),
            "can_access_social_publish": allowed,
            "license_message": reason,
        })
    except Exception as e:
        logger.error(f"Lỗi lấy trạng thái social: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_publish_bp.route("/api/social/history", methods=["GET"])
def get_publish_history():
    """Trả về danh sách lịch sử thao tác đăng gần đây."""
    try:
        history = social_publisher.load_publish_history()
        history_reversed = list(reversed(history))
        return jsonify({
            "success": True,
            "history": history_reversed,
            "total": len(history_reversed),
        })
    except Exception as e:
        logger.error(f"Lỗi đọc lịch sử social: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_publish_bp.route("/api/social/history/clear", methods=["POST"])
def clear_publish_history():
    """Xóa toàn bộ lịch sử thao tác đăng video."""
    try:
        social_publisher.save_publish_history([])
        return jsonify({
            "success": True,
            "message": "Đã dọn dẹp toàn bộ lịch sử đăng video.",
        })
    except Exception as e:
        logger.error(f"Lỗi xóa lịch sử social: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
