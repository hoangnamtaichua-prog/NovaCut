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
"""

import os
import sys
import logging
from flask import Blueprint, jsonify, request

import social_publisher
from routes.security import is_path_allowed, register_user_path
import license_manager

social_publish_bp = Blueprint("social_publish", __name__)
logger = logging.getLogger("social_publish")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


@social_publish_bp.route("/api/social/platforms", methods=["GET"])
def get_platforms():
    """Trả về danh sách các mạng xã hội được hỗ trợ kèm cấu hình từng nền tảng."""
    try:
        platforms_list = list(social_publisher.SUPPORTED_PLATFORMS.values())
        return jsonify({
            "success": True,
            "platforms": platforms_list,
            "total": len(platforms_list)
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
            "default_profile": profiles[0]["id"] if profiles else "Default"
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
                "error": f"Nền tảng '{platform_id}' không tồn tại hoặc chưa được hỗ trợ."
            }), 400

        # Kiểm tra tệp video nếu có truyền vào
        video_info = None
        if video_path:
            # Chuẩn hóa đường dẫn
            norm_video_path = os.path.abspath(video_path)
            ext = os.path.splitext(norm_video_path)[1].lower()

            if ext not in ALLOWED_VIDEO_EXTENSIONS:
                return jsonify({
                    "success": False,
                    "error": f"Định dạng tệp '{ext}' không được hỗ trợ. Vui lòng chọn tệp video ({', '.join(ALLOWED_VIDEO_EXTENSIONS)})."
                }), 400

            if not os.path.isfile(norm_video_path):
                return jsonify({
                    "success": False,
                    "error": f"Tệp video không tồn tại trên ổ đĩa: {video_path}"
                }), 404

            # Đăng ký quyền truy cập nếu là tệp người dùng chọn
            register_user_path(norm_video_path)

            if not is_path_allowed(norm_video_path, must_exist=True):
                return jsonify({
                    "success": False,
                    "error": "Đường dẫn tệp nằm ngoài phạm vi được phép truy cập."
                }), 403

            size_bytes = os.path.getsize(norm_video_path)
            size_mb = round(size_bytes / (1024 * 1024), 2)
            video_info = {
                "path": norm_video_path,
                "name": os.path.basename(norm_video_path),
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "exists": True
            }

        prepared = social_publisher.prepare_publish_content(
            platform_id=platform_id,
            title=title,
            description=description,
            caption=caption,
            hashtags=hashtags,
            privacy=privacy
        )

        return jsonify({
            "success": True,
            "prepared": prepared,
            "video": video_info
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
        # 1. Kiểm tra bản quyền (Backend Enforcement Rule)
        allowed, reason, _ = license_manager.check_permission("can_access_social_publish")
        if not allowed:
            return jsonify({
                "success": False,
                "error": reason,
                "license_error": True
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

        # Kiểm tra video path nếu có
        norm_video_path = ""
        if video_path:
            norm_video_path = os.path.abspath(video_path)
            if not os.path.isfile(norm_video_path):
                return jsonify({"success": False, "error": f"Tệp video không tồn tại: {video_path}"}), 404

            register_user_path(norm_video_path)
            if not is_path_allowed(norm_video_path, must_exist=True):
                return jsonify({"success": False, "error": "Đường dẫn video không được phép."}), 403

        # Chọn URL upload
        target_url = custom_url or platform.get("upload_url") or platform.get("direct_url")

        # Khởi chạy Google Chrome
        success, msg = social_publisher.launch_chrome_with_profile(
            profile_id=profile_id,
            target_url=target_url
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
                message=msg
            )
            return jsonify({"success": False, "error": msg}), 500

        # Tự động sao chép đường dẫn video vào Clipboard nếu được yêu cầu
        clipboard_copied = False
        if copy_video_path and norm_video_path:
            clipboard_copied = social_publisher.copy_text_to_windows_clipboard(norm_video_path)

        # Ghi nhận vào lịch sử
        history_entry = social_publisher.record_publish_action(
            platform_id=platform_id,
            video_path=norm_video_path,
            title=title,
            caption=caption,
            profile_id=profile_id,
            privacy=privacy,
            status="OPENED",
            message="Đã mở Chrome thành công"
        )

        return jsonify({
            "success": True,
            "message": msg,
            "platform_id": platform_id,
            "platform_name": platform.get("name"),
            "target_url": target_url,
            "profile_id": profile_id,
            "clipboard_copied": clipboard_copied,
            "history_entry": history_entry
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
            "license_message": reason
        })
    except Exception as e:
        logger.error(f"Lỗi lấy trạng thái social: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_publish_bp.route("/api/social/history", methods=["GET"])
def get_publish_history():
    """Trả về danh sách lịch sử thao tác đăng gần đây."""
    try:
        history = social_publisher.load_publish_history()
        # Trả về thứ tự mới nhất lên đầu
        history_reversed = list(reversed(history))
        return jsonify({
            "success": True,
            "history": history_reversed,
            "total": len(history_reversed)
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
            "message": "Đã dọn dẹp toàn bộ lịch sử đăng video."
        })
    except Exception as e:
        logger.error(f"Lỗi xóa lịch sử social: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
