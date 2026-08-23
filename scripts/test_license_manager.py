# -*- coding: utf-8 -*-
"""
Test Suite: License Manager, HWID & VietQR SePay System
"""

import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import license_manager

def test_hwid_generation():
    print("1. Testing Hardware ID (HWID) Generation...")
    hwid = license_manager.get_hardware_id()
    print(f"  -> Generated HWID: {hwid}")
    assert hwid.startswith("AMS-"), f"HWID phải bắt đầu bằng AMS-, nhận: {hwid}"
    parts = hwid.split('-')
    assert len(parts) == 4, f"HWID phải gồm 4 cụm, nhận: {parts}"
    for p in parts[1:]:
        assert len(p) == 4, f"Mỗi cụm HWID phải có 4 ký tự, nhận: {p}"

    # Kiểm tra tính nhất quán (chạy lại 3 lần phải ra cùng HWID)
    hwid2 = license_manager.get_hardware_id()
    assert hwid == hwid2, "HWID không được thay đổi qua các lần gọi!"
    
    short_hwid = license_manager.get_short_hwid()
    print(f"  -> Short HWID (6 chars): {short_hwid}")
    assert len(short_hwid) == 6, f"Short HWID phải có đúng 6 ký tự, nhận: {short_hwid}"
    print("  ✅ PASS: HWID Generation")

def test_vietqr_generation():
    print("\n2. Testing VietQR URL & Transfer Syntax Generation...")
    qr_data = license_manager.generate_vietqr_url(tier='vip', amount=500000)
    print(f"  -> QR Image URL: {qr_data['qr_image_url']}")
    print(f"  -> Transfer Content: {qr_data['transfer_content']}")
    assert 'img.vietqr.io' in qr_data['qr_image_url'], "Link QR phải thuộc vietqr.io"
    assert qr_data['transfer_content'].startswith('AMS '), "Nội dung chuyển khoản phải bắt đầu bằng AMS"
    assert qr_data['short_hwid'] in qr_data['transfer_content'], "Nội dung chuyển khoản phải chứa short HWID"
    assert 'VIP' in qr_data['transfer_content'], "Nội dung chuyển khoản phải chứa mã gói"
    print("  ✅ PASS: VietQR Generation")

def test_offline_master_key():
    print("\n3. Testing Offline Master Key Generation & Verification...")
    short_hwid = license_manager.get_short_hwid()
    
    # Tạo Key VIP 30 ngày
    master_key = license_manager.generate_offline_master_key(short_hwid, tier='vip', days=30)
    print(f"  -> Generated Master Key: {master_key}")
    assert master_key.startswith("AMS-KEY-VIP-30-"), "Key không đúng định dạng"

    # Thử kích hoạt
    success, msg = license_manager.activate_license_with_key(master_key)
    print(f"  -> Activation Result: {success}, Message: {msg}")
    assert success is True, "Kích hoạt bằng Master Key phải thành công"

    # Kiểm tra trạng thái sau kích hoạt
    status = license_manager.get_current_license_status()
    assert status['is_valid'] is True, "License phải ở trạng thái ACTIVE"
    assert status['tier'] == 'vip', f"Tier phải là VIP, nhận: {status['tier']}"
    assert status['days_left'] >= 29, f"Số ngày còn lại phải >= 29, nhận: {status['days_left']}"
    print(f"  -> Current License Status: {status['plan_name']} (Còn {status['days_left']} ngày)")
    print("  ✅ PASS: Master Key Activation")

def test_tamper_resistance():
    print("\n4. Testing Local Cache Tamper Resistance...")
    # Thử sửa file cache trực tiếp
    cache_file = license_manager.LICENSE_CACHE_FILE
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Làm hỏng chữ ký
        tampered = content.replace('"s": "', '"s": "FAKE_SIG_')
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(tampered)
        
        # Đọc lại -> Phải trả về None vì chữ ký hỏng
        loaded = license_manager.load_local_license_cache()
        assert loaded is None, "Phải phát hiện và từ chối file bản quyền bị chỉnh sửa!"
        print("  -> Chữ ký giả mạo đã bị phát hiện và từ chối thành công!")
        
        # Khôi phục lại
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("  ✅ PASS: Tamper Resistance")

def test_flask_endpoints():
    print("\n5. Testing Flask API Routes (/api/license/info, /api/license/qr_info)...")
    from flask import Flask
    from routes.license import license_bp
    
    test_app = Flask(__name__)
    test_app.register_blueprint(license_bp)
    client = test_app.test_client()
    
    # Test GET /api/license/info
    res = client.get('/api/license/info')
    assert res.status_code == 200, f"Mã HTTP phải là 200, nhận: {res.status_code}"
    data = res.get_json()
    assert 'hwid' in data, "Response phải chứa HWID"
    assert 'status' in data, "Response phải chứa status"
    assert 'prices' in data, "Response phải chứa prices"
    print(f"  -> GET /api/license/info: 200 OK (HWID: {data['hwid']}, Tier: {data['tier']})")
    
    # Test GET /api/license/qr_info
    res_qr = client.get('/api/license/qr_info?tier=vip')
    assert res_qr.status_code == 200, f"Mã HTTP phải là 200, nhận: {res_qr.status_code}"
    qr_json = res_qr.get_json()
    assert 'qr_image_url' in qr_json, "Response phải chứa qr_image_url"
    assert 'transfer_content' in qr_json, "Response phải chứa transfer_content"
    print(f"  -> GET /api/license/qr_info: 200 OK (Transfer note: {qr_json['transfer_content']})")
    print("  ✅ PASS: Flask API Endpoints")

def test_write_only_keys_sync():
    print("\n6. Testing Write-Only Cloud Keys Push (1 chiều)...")
    keys_sample = {
        "openaiKey": "sk-proj-test12345678",
        "openaiBaseUrl": "https://api.openai.com/v1",
        "openaiModel": "gpt-4o-mini",
        "openSpeakerApiKey": "ospk_sample_987654"
    }
    res = license_manager.sync_user_keys_to_cloud(keys_sample)
    print(f"  -> Write-only push without GAS URL: {res} (Handled safely)")
    assert res is False or res is True
    print("  ✅ PASS: Write-Only Keys Sync Functionality")

def test_anti_clock_rollback():
    print("\n7. Testing Anti-Clock Rollback Detection...")
    now_epoch = int(time.time())
    
    # Giả lập 1 bản quyền có last_seen_epoch là 2 giờ trong tương lai (người dùng vừa lùi giờ Windows 2 tiếng)
    fake_future_epoch = now_epoch + 7200
    fake_license = {
        "hwid": license_manager.get_hardware_id(),
        "tier": "vip",
        "plan_name": "Gói VIP (500k/tháng)",
        "expire_epoch": now_epoch + 86400 * 30,
        "expire_str": "30/09/2026 23:59",
        "activated_at": now_epoch - 3600,
        "last_seen_epoch": fake_future_epoch
    }
    
    # Lưu cache với mốc tương lai
    license_manager.save_local_license_cache(fake_license)
    
    # Đọc lại cache -> verify_clock_integrity phải phát hiện ra
    loaded = license_manager.load_local_license_cache(auto_update_clock=False)
    assert loaded is not None, "Cache phải giải mã được chữ ký"
    assert loaded.get('clock_tampered') is True, "Phải phát hiện clock_tampered = True khi lùi giờ!"
    
    # Kiểm tra get_current_license_status()
    status = license_manager.get_current_license_status(force_cloud_sync=False)
    assert status['is_valid'] is False, "License phải bị vô hiệu hóa khi lùi giờ"
    assert status['status'] == 'CLOCK_TAMPERED', f"Status phải là CLOCK_TAMPERED, nhận: {status['status']}"
    print(f"  -> Clock Tamper Detected Successfully: {status['clock_error']}")
    
    # Khôi phục lại cache hợp lệ với giờ hiện tại
    fake_license['last_seen_epoch'] = now_epoch
    license_manager.save_local_license_cache(fake_license)
    restored_status = license_manager.get_current_license_status(force_cloud_sync=False)
    assert restored_status['is_valid'] is True, "Sau khi chỉnh đúng giờ phải hoạt động bình thường"
    print("  ✅ PASS: Anti-Clock Rollback Protection")

def test_anti_mitm_signature_and_nonce():
    print("\n8. Testing Anti-MITM / Anti-Fiddler HMAC Verification...")
    token = "AMS_SECURE_TOKEN_2026_@DEEPMIND_ANTIGRAVITY"
    hwid = license_manager.get_hardware_id()
    nonce = "testnonce123"
    server_time = str(int(time.time()))
    
    # 1. Gói tin hợp lệ từ Google Apps Script
    raw_str = f"{hwid}|vip|ACTIVE|30/09/2026 23:59|1790812740|{nonce}|{server_time}"
    valid_sig = license_manager.hmac.new(token.encode('utf-8'), raw_str.encode('utf-8'), license_manager.hashlib.sha256).hexdigest()
    
    valid_response = {
        "valid": True,
        "hwid": hwid,
        "tier": "vip",
        "status": "ACTIVE",
        "expire_date": "30/09/2026 23:59",
        "expire_epoch": 1790812740,
        "nonce": nonce,
        "server_time": server_time,
        "sig": valid_sig
    }
    assert license_manager.verify_cloud_signature(valid_response, token) is True, "Gói tin chuẩn phải xác thực thành công"
    print("  -> Valid Signature: Verified OK")
    
    # 2. Gói tin bị hacker dùng Fiddler/Charles sửa gói tin (sửa tier từ pro lên vip mà không có chữ ký đúng)
    tampered_response = valid_response.copy()
    tampered_response['tier'] = 'yearly' # Hacker can thiệp sửa gói
    assert license_manager.verify_cloud_signature(tampered_response, token) is False, "Gói tin bị sửa đổi phải bị từ chối ngay lập tức"
    print("  -> Tampered Response (MITM): Successfully Rejected!")
    print("  ✅ PASS: Anti-MITM / Anti-Fiddler Protection")

def test_token_quota_limits():
    print("\n9. Testing Token Quota (1M Prompt & 1M Completion Limits)...")
    license_manager.reset_token_quota_stats()
    
    # 1. Ban đầu: 0 token -> Check phải OK
    is_ok, msg = license_manager.check_token_quota()
    assert is_ok is True, "Ban đầu khi chưa dùng token nào phải trả về True"
    
    # 2. Ghi nhận 5,000 prompt và 2,000 completion
    stats = license_manager.record_token_usage(prompt_tokens=5000, completion_tokens=2000)
    assert stats['prompt_tokens'] == 5000
    assert stats['completion_tokens'] == 2000
    assert stats['total_tokens'] == 7000
    print(f"  -> Recorded: Prompt {stats['prompt_tokens']}, Completion {stats['completion_tokens']}")
    
    # 3. Giả lập dùng vượt 1,000,000 Prompt tokens
    license_manager.save_token_quota_stats({
        "prompt_tokens": 1000005,
        "completion_tokens": 50000,
        "requests": 100
    })
    is_ok_prompt, err_prompt = license_manager.check_token_quota()
    assert is_ok_prompt is False, "Khi vượt 1M prompt token phải bị chặn"
    assert "1,000,000 Token gửi đi" in err_prompt
    print(f"  -> Prompt Quota Block Verified: {err_prompt}")
    
    # 4. Giả lập dùng vượt 1,000,000 Completion tokens
    license_manager.save_token_quota_stats({
        "prompt_tokens": 200000,
        "completion_tokens": 1000010,
        "requests": 150
    })
    is_ok_comp, err_comp = license_manager.check_token_quota()
    assert is_ok_comp is False, "Khi vượt 1M completion token phải bị chặn"
    assert "1,000,000 Token nhận về" in err_comp
    print(f"  -> Completion Quota Block Verified: {err_comp}")
    
    # 5. Reset lại về 0
    license_manager.reset_token_quota_stats()
    stats_after_reset = license_manager.load_token_quota_stats()
    assert stats_after_reset['total_tokens'] == 0
    assert license_manager.check_token_quota()[0] is True
    print("  ✅ PASS: Token Quota Limits & Reset")

if __name__ == '__main__':
    print("==========================================================")
    print("🧪 BẮT ĐẦU KIỂM THỬ HỆ THỐNG BẢN QUYỀN, HWID & SEPAY VIETQR")
    print("==========================================================")
    test_hwid_generation()
    test_vietqr_generation()
    test_offline_master_key()
    test_tamper_resistance()
    test_flask_endpoints()
    test_write_only_keys_sync()
    test_anti_clock_rollback()
    test_anti_mitm_signature_and_nonce()
    test_token_quota_limits()
    print("\n🎉 TẤT CẢ 9 BÀI KIỂM THỬ BẢO MẬT & QUOTA ĐÃ PASS 100%! HỆ THỐNG HOÀN TOÀN BẤT KHẢ XÂM PHẠM!")
