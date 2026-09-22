"""
Routes Blueprint cho tính năng thông báo Telegram trong NovaCut.
Hỗ trợ quản lý cấu hình hệ thống, thông tin bot chung và quy trình tự động lấy Chat ID cho từng user.
"""

from flask import Blueprint, jsonify, request
import logging
from telegram_notifier import get_telegram_notifier, mask_chat_id

logger = logging.getLogger("telegram_routes")
telegram_bp = Blueprint("telegram", __name__)


@telegram_bp.route("/api/telegram/config", methods=["GET"])
def api_get_telegram_config():
    """Lấy cấu hình Telegram hiện tại (đã che giấu token để bảo mật)."""
    notifier = get_telegram_notifier()
    return jsonify({
        "success": True,
        "config": notifier.get_public_config()
    })


@telegram_bp.route("/api/telegram/config", methods=["POST"])
def api_save_telegram_config():
    """Lưu cấu hình Telegram từ giao diện cài đặt."""
    data = request.json or {}
    notifier = get_telegram_notifier()

    enabled = data.get("enabled")
    bot_token = data.get("bot_token")
    chat_id = data.get("chat_id")
    notify_per_video = data.get("notify_per_video")
    notify_batch_done = data.get("notify_batch_done")

    saved = notifier.save_config(
        enabled=enabled,
        bot_token=bot_token,
        chat_id=chat_id,
        notify_per_video=notify_per_video,
        notify_batch_done=notify_batch_done,
    )

    user_id = data.get("user_id", "").strip()
    if chat_id and user_id:
        try:
            notifier.set_user_manual_chat_id(user_id=user_id, chat_id=chat_id)
        except Exception:
            pass

    if saved:
        return jsonify({
            "success": True,
            "message": "Đã lưu cấu hình Telegram thành công",
            "config": notifier.get_public_config()
        })
    else:
        return jsonify({
            "success": False,
            "error": "Không thể lưu tệp cấu hình Telegram"
        }), 500


@telegram_bp.route("/api/telegram/bot_info", methods=["GET"])
def api_get_bot_info():
    """Lấy thông tin công khai về Bot Telegram chung (username, tên bot)."""
    notifier = get_telegram_notifier()
    info = notifier.get_bot_info()
    return jsonify(info)


@telegram_bp.route("/api/telegram/user/status", methods=["GET"])
def api_get_user_status():
    """Lấy trạng thái kết nối Telegram của từng user cụ thể."""
    user_id = request.args.get("user_id", "default").strip()
    notifier = get_telegram_notifier()
    profile = notifier.get_user_profile(user_id)
    return jsonify({
        "success": True,
        "profile": profile
    })


@telegram_bp.route("/api/telegram/connect/start", methods=["POST"])
def api_start_telegram_connect():
    """Bắt đầu phiên kết nối tự động lấy Chat ID cho user (hết hạn sau 5 phút)."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    notifier = get_telegram_notifier()
    res = notifier.start_connect_session(user_id=user_id, timeout_sec=300)
    status_code = 200 if res.get("success") else 400
    return jsonify(res), status_code


@telegram_bp.route("/api/telegram/connect/poll", methods=["POST"])
def api_poll_telegram_connect():
    """Polling kiểm tra tin nhắn mới từ bot để trích xuất Chat ID."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    connect_code = data.get("connect_code", "").strip()
    notifier = get_telegram_notifier()
    res = notifier.poll_connect_session(user_id=user_id, connect_code=connect_code)
    return jsonify(res)


@telegram_bp.route("/api/telegram/user/disconnect", methods=["POST"])
def api_disconnect_user_telegram():
    """Ngắt kết nối Telegram và xóa Chat ID đã lưu của user."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    notifier = get_telegram_notifier()
    notifier.disconnect_user(user_id=user_id)
    return jsonify({
        "success": True,
        "message": "Đã ngắt kết nối Telegram và xóa Chat ID thành công"
    })


@telegram_bp.route("/api/telegram/user/manual_connect", methods=["POST"])
def api_manual_connect_user_telegram():
    """Áp dụng Chat ID điền thủ công cho user hiện tại."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    chat_id = data.get("chat_id", "").strip()
    bot_token = data.get("bot_token", "").strip()

    notifier = get_telegram_notifier()
    res = notifier.set_user_manual_chat_id(user_id=user_id, chat_id=chat_id, bot_token=bot_token)
    status_code = 200 if res.get("success") else 400
    return jsonify(res), status_code


@telegram_bp.route("/api/telegram/test_sample", methods=["POST"])
def api_test_sample_telegram():
    """Gửi mẫu thông báo mô phỏng thực tế (ping / video / batch / failure) để user kiểm tra."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    sample_type = data.get("sample_type", "video").strip().lower()
    bot_token = data.get("bot_token", "").strip()
    chat_id = data.get("chat_id", "").strip()

    notifier = get_telegram_notifier()
    success, msg = notifier.send_sample_notification(
        user_id=user_id,
        sample_type=sample_type,
        custom_token=bot_token,
        custom_chat_id=chat_id,
    )

    if success:
        return jsonify({
            "success": True,
            "message": msg,
            "chat_id": mask_chat_id(chat_id or notifier._resolve_target_chat(user_id) or "")
        })
    else:
        return jsonify({"success": False, "error": msg}), 400


@telegram_bp.route("/api/telegram/user/test", methods=["POST"])
def api_test_user_telegram():
    """Gửi tin nhắn kiểm tra tới Chat ID cá nhân của user."""
    data = request.json or {}
    user_id = data.get("user_id", "default").strip()
    bot_token = data.get("bot_token", "").strip()
    notifier = get_telegram_notifier()
    success, msg = notifier.send_user_test_message(user_id=user_id, custom_token=bot_token)
    if success:
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"success": False, "error": msg}), 400


@telegram_bp.route("/api/telegram/test", methods=["POST"])
def api_test_telegram():
    """Gửi một tin nhắn kiểm tra tới Bot Telegram với cấu hình chỉ định."""
    data = request.json or {}
    test_token = data.get("bot_token", "")
    test_chat_id = data.get("chat_id", "")

    notifier = get_telegram_notifier()
    success, msg = notifier.send_test_message(test_token=test_token, test_chat_id=test_chat_id)

    if success:
        return jsonify({
            "success": True,
            "message": msg
        })
    else:
        return jsonify({
            "success": False,
            "error": msg
        }), 400


@telegram_bp.route("/api/telegram/notify", methods=["POST"])
def api_trigger_telegram_notify():
    """
    Endpoint cho phép frontend kích hoạt gửi thông báo Telegram.
    Hỗ trợ truyền user_id để gửi đúng Chat ID của user.
    Sự cố mạng Telegram sẽ không bao giờ làm lỗi request (luôn trả về 200).
    """
    data = request.json or {}
    event_type = data.get("event")
    user_id = data.get("user_id")
    notifier = get_telegram_notifier()

    if not notifier.enabled:
        return jsonify({"success": True, "skipped": "Telegram notifications disabled"})

    try:
        if event_type == "video_success":
            notifier.notify_video_success(
                video_title=data.get("title", ""),
                output_path=data.get("output_path", ""),
                duration_sec=data.get("duration_sec"),
                current_index=int(data.get("current_index", 1)),
                total_count=int(data.get("total_count", 1)),
                preset_name=data.get("preset_name", ""),
                task_id=data.get("task_id", ""),
                user_id=user_id,
            )
        elif event_type == "video_failure":
            notifier.notify_video_failure(
                video_title=data.get("title", ""),
                error_message=data.get("error", ""),
                duration_sec=data.get("duration_sec"),
                current_index=int(data.get("current_index", 1)),
                total_count=int(data.get("total_count", 1)),
                preset_name=data.get("preset_name", ""),
                task_id=data.get("task_id", ""),
                user_id=user_id,
            )
        elif event_type == "batch_completed":
            notifier.notify_batch_completed(
                total_count=int(data.get("total_count", 0)),
                success_count=int(data.get("success_count", 0)),
                failed_count=int(data.get("failed_count", 0)),
                cancelled_count=int(data.get("cancelled_count", 0)),
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                output_dir=data.get("output_dir", ""),
                batch_id=data.get("batch_id", ""),
                user_id=user_id,
            )
        elif event_type == "batch_cancelled":
            notifier.notify_batch_cancelled(
                total_count=int(data.get("total_count", 0)),
                completed_count=int(data.get("completed_count", 0)),
                failed_count=int(data.get("failed_count", 0)),
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                batch_id=data.get("batch_id", ""),
                user_id=user_id,
            )
    except Exception as e:
        logger.warning(f"Lỗi khi xử lý notify event: {e}")

    return jsonify({"success": True})
