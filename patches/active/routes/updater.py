# -*- coding: utf-8 -*-
"""
Routes API Auto-Updater (Kiểm tra & Tải cập nhật tự động từ Google Drive)
"""

from flask import Blueprint, jsonify, request
import updater

updater_bp = Blueprint('updater', __name__)

@updater_bp.route('/api/updater/check', methods=['GET'])
def check_updates_api():
    """Kiểm tra xem có bản cập nhật mới trên Google Sheet hay không."""
    info = updater.check_for_updates()
    return jsonify(info)


@updater_bp.route('/api/updater/progress', methods=['GET'])
def get_progress_api():
    """Lấy trạng thái tiến độ tải & giải nén bản cập nhật thời gian thực."""
    progress = updater.get_update_progress()
    return jsonify(progress)


@updater_bp.route('/api/system/restart', methods=['POST'])
def restart_app_api():
    """Khởi động lại ứng dụng tự động."""
    updater.restart_application()
    return jsonify({"success": True, "message": "Đang khởi động lại ứng dụng..."})


@updater_bp.route('/api/updater/start_update', methods=['POST'])
def start_update_api():
    """Bắt đầu tải và cài đặt bản cập nhật trong luồng nền."""
    # Không tin URL/version do client gửi. Chỉ dùng manifest từ nguồn cấu hình.
    info = updater.check_for_updates()
    if not info.get('has_update'):
        return jsonify({'success': False, 'error': 'Không có bản cập nhật hợp lệ.'}), 409
    download_url = str(info.get('download_url') or '').strip()
    drive_file_id = str(info.get('google_drive_file_id') or '').strip()
    target_version = str(info.get('latest_version') or '').strip()

    target_source = download_url or drive_file_id
    if not target_source:
        return jsonify({
            'success': False,
            'error': 'Không tìm thấy đường dẫn tải bản cập nhật!'
        }), 400

    try:
        updater._validate_update_url(target_source if download_url else f"https://drive.google.com/uc?export=download&id={drive_file_id}")
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    updater.perform_auto_update_async(target_source, target_version, info.get('sha256', ''))
    return jsonify({
        'success': True,
        'message': f'Đã bắt đầu quá trình cập nhật lên phiên bản v{target_version}!'
    })
