# -*- coding: utf-8 -*-
"""
Routes API Bản quyền, HWID & Thanh toán VietQR SePay
"""

import os
import hmac
from flask import Blueprint, jsonify, request
import license_manager

license_bp = Blueprint('license', __name__)

def _require_dev_admin():
    expected = os.environ.get('NOVACUT_ADMIN_TOKEN', '')
    supplied = request.headers.get('X-NovaCut-Admin-Token', '')
    return (
        os.environ.get('NOVACUT_ENABLE_DEV_ENDPOINTS') == '1'
        and bool(expected)
        and hmac.compare_digest(supplied, expected)
    )

@license_bp.route('/api/license/info', methods=['GET'])
def get_license_info():
    """Lấy thông tin bản quyền và mã máy hiện tại."""
    force_sync = request.args.get('sync', 'false').lower() == 'true'
    status = license_manager.get_current_license_status(force_cloud_sync=force_sync)
    cfg = license_manager.load_app_config()
    status['prices'] = cfg.get('prices', {})
    status['bank_info'] = license_manager.resolve_bank_details(cfg)
    return jsonify(status)

@license_bp.route('/api/license/activate_trial', methods=['POST'])
def activate_trial():
    """Kích hoạt gói dùng thử 24h miễn phí."""
    data = request.get_json(silent=True) or {}
    user_name = data.get('user_name', 'Khách Dùng Thử')
    phone_zalo = data.get('phone_zalo', '')
    
    success, msg = license_manager.activate_trial_license(user_name, phone_zalo)
    if success:
        new_status = license_manager.get_current_license_status()
        return jsonify({'success': True, 'message': msg, 'license': new_status})
    return jsonify({'success': False, 'error': msg}), 400

@license_bp.route('/api/license/activate_key', methods=['POST'])
def activate_key():
    """Kích hoạt bằng License Key thủ công."""
    data = request.get_json(silent=True) or {}
    key_str = data.get('key', '').strip()
    if not key_str:
        return jsonify({'success': False, 'error': 'Vui lòng nhập mã kích hoạt!'}), 400

    success, msg = license_manager.activate_license_with_key(key_str)
    if success:
        new_status = license_manager.get_current_license_status()
        return jsonify({'success': True, 'message': msg, 'license': new_status})
    return jsonify({'success': False, 'error': msg}), 400

@license_bp.route('/api/license/qr_info', methods=['GET'])
def get_qr_info():
    """Tạo link mã QR VietQR động theo gói cước."""
    tier = request.args.get('tier', 'vip')
    if tier not in ('pro', 'vip', 'yearly'):
        return jsonify({'success': False, 'error': 'Gói thanh toán không hợp lệ'}), 400
    qr_data = license_manager.generate_vietqr_url(tier=tier, amount=None)
    return jsonify(qr_data)

@license_bp.route('/api/license/sync_cloud', methods=['POST'])
def sync_cloud():
    """Chủ động đồng bộ dữ liệu từ Google Sheets Cloud."""
    license_info = license_manager.sync_with_cloud()
    current_status = license_manager.get_current_license_status()
    if license_info:
        return jsonify({'success': True, 'message': 'Đồng bộ bản quyền thành công!', 'license': current_status})
    return jsonify({'success': False, 'message': 'Không có cập nhật mới từ máy chủ.', 'license': current_status})

@license_bp.route('/api/license/get_system_api', methods=['POST', 'GET'])
def get_system_api():
    """Lấy API Key cấp sẵn từ máy chủ / Google Sheet cho tài khoản hiện tại."""
    # 1. Thử sync cloud để lấy thông tin mới nhất
    license_manager.sync_with_cloud()
    status = license_manager.get_current_license_status()
    
    vip_keys = status.get('vip_api_keys') or {}
    tier = status.get('tier', 'unlicensed')
    
    has_system_keys = bool(vip_keys and any(v for v in vip_keys.values() if v))
    
    if has_system_keys:
        return jsonify({
            'success': True,
            'has_keys': True,
            'tier': tier,
            'message': 'Đã nhận thành công API Key cấp sẵn từ hệ thống!',
            'license': status
        })
    else:
        return jsonify({
            'success': False,
            'has_keys': False,
            'tier': tier,
            'message': f'Gói {status.get("plan_name", "hiện tại")} chưa có API Key cấp sẵn trên máy chủ hoặc quản trị viên chưa cấu hình key. Bạn có thể tự điền API Key cá nhân của mình để sử dụng!',
            'license': status
        })

@license_bp.route('/api/license/test_activate', methods=['POST'])
def test_activate():
    """Kích hoạt thử nghiệm gói cước (chế độ test không cần chuyển khoản thật)."""
    if not _require_dev_admin():
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    tier = data.get('tier', 'vip')
    days = data.get('days', 30)
    success, msg = license_manager.activate_test_tier(tier=tier, days=days)
    new_status = license_manager.get_current_license_status()
    return jsonify({'success': success, 'message': msg, 'license': new_status})

@license_bp.route('/api/license/token_quota', methods=['GET'])
def get_token_quota():
    """Lấy thông tin định mức và số lượng Token đã sử dụng (Prompt 1M / Completion 1M)."""
    stats = license_manager.load_token_quota_stats()
    return jsonify(stats)

@license_bp.route('/api/license/token_quota/reset', methods=['POST'])
def reset_token_quota():
    """(Dành cho Admin) Đặt lại bộ đếm token về 0."""
    if not _require_dev_admin():
        return jsonify({'success': False, 'error': 'Not found'}), 404
    license_manager.reset_token_quota_stats()
    return jsonify({'success': True, 'message': 'Đã đặt lại bộ đếm token về 0!'})

@license_bp.route('/api/license/set_pro_module', methods=['POST'])
def set_pro_module():
    """Thiết lập Module chính cho Gói Pro ('editor' hoặc 'review')."""
    data = request.get_json(silent=True) or {}
    module = data.get('module', 'editor')
    success, msg = license_manager.set_pro_selected_module(module)
    new_status = license_manager.get_current_license_status()
    if success:
        return jsonify({'success': True, 'message': msg, 'license': new_status})
    return jsonify({'success': False, 'error': msg, 'license': new_status}), 400

@license_bp.route('/api/license/check_sepay_payment', methods=['POST'])
def check_sepay_payment():
    """Đối soát qua backend; client không giữ SePay API token."""
    license_manager.sync_with_cloud()
    new_status = license_manager.get_current_license_status()
    if new_status.get('is_valid') and new_status.get('tier') not in ('trial', 'unlicensed'):
        return jsonify({
            'success': True,
            'message': 'Máy chủ đã xác nhận thanh toán và kích hoạt bản quyền.',
            'license': new_status
        })
    return jsonify({
        'success': False,
        'message': 'Chưa tìm thấy giao dịch đã được backend xác nhận.',
        'license': new_status
    }), 404
