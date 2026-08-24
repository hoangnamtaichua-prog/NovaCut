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
    import threading
    import time
    import os
    import sys
    
    def delayed_restart():
        time.sleep(1)
        # Sử dụng os.execl để thay thế tiến trình hiện tại bằng một tiến trình Python mới
        os.execl(sys.executable, sys.executable, *sys.argv)
        
    threading.Thread(target=delayed_restart).start()
    return jsonify({"success": True, "message": "Đang khởi động lại ứng dụng..."})


@updater_bp.route('/api/updater/start_update', methods=['POST'])
def start_update_api():
    """Bắt đầu tải và cài đặt bản cập nhật trong luồng nền."""
    data = request.get_json(silent=True) or {}
    download_url = data.get('download_url', '').strip()
    drive_file_id = data.get('google_drive_file_id', '').strip()
    target_version = data.get('target_version', '').strip()

    if not download_url and not drive_file_id:
        info = updater.check_for_updates()
        download_url = info.get('download_url', '').strip()
        drive_file_id = info.get('google_drive_file_id', '').strip()
        target_version = info.get('latest_version', '').strip()

    target_source = download_url or drive_file_id
    if not target_source:
        return jsonify({
            'success': False,
            'error': 'Không tìm thấy đường dẫn tải bản cập nhật!'
        }), 400

    updater.perform_auto_update_async(target_source, target_version)
    return jsonify({
        'success': True,
        'message': f'Đã bắt đầu quá trình cập nhật lên phiên bản v{target_version}!'
    })
