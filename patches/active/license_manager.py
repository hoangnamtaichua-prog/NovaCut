# -*- coding: utf-8 -*-
"""
Hệ thống Quản lý Bản quyền, Mã máy Phần cứng (HWID), và Phân quyền Gói cước.
Tích hợp đồng bộ Google Sheets Backend & Cổng thanh toán VietQR SePay.
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import subprocess
import requests
import re
import threading
from datetime import datetime, timedelta
from urllib.parse import quote

import email.utils
import uuid

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, 'web', 'index.html')):
            norm_curr = os.path.normpath(curr).lower()
            if not norm_curr.endswith(os.path.normpath('patches/active').lower()) and not norm_curr.endswith(os.path.normpath('release/novacut').lower()):
                return os.path.abspath(curr)
        curr = os.path.dirname(curr)
    return os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = get_app_root_dir()

def get_user_data_dir():
    """Lấy thư mục lưu trữ dữ liệu an toàn của người dùng (%APPDATA%/NovaCut trên Windows)."""
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        if appdata:
            path = os.path.join(appdata, 'NovaCut')
            try:
                os.makedirs(path, exist_ok=True)
                return path
            except Exception:
                pass
    return ROOT_DIR

DATA_DIR = get_user_data_dir()
LICENSE_CACHE_FILE = os.path.join(DATA_DIR, '.license.dat')
CONFIG_FILE = os.path.join(DATA_DIR, 'license_config.json')
FROZEN_RESOURCE_DIR = getattr(sys, '_MEIPASS', '')
BOOTSTRAP_CONFIG_FILE = os.path.join(FROZEN_RESOURCE_DIR, 'license_bootstrap.json') if FROZEN_RESOURCE_DIR else ''
PROCESSED_TX_FILE = os.path.join(DATA_DIR, '.processed_txs.dat')
TOKEN_CACHE_FILE = os.path.join(DATA_DIR, '.token_quota.dat')
# Lưu trạng thái (tier, expire_epoch, status) của lần sync cloud gần nhất đã thành công.
# Dùng để phát hiện nâng gói / gia hạn khi check bản quyền lần đầu mỗi phiên.
LAST_SYNC_STATE_FILE = os.path.join(DATA_DIR, '.last_sync_state.dat')
MAX_PROMPT_TOKENS = 1_000_000      # 1,000,000 Token gửi đi (Prompt)
MAX_COMPLETION_TOKENS = 1_000_000  # 1,000,000 Token nhận về (Completion)

# Secret Salt bảo mật chống giả mạo chữ ký HMAC cục bộ và định danh HWID máy
DEFAULT_LOCAL_SALT = "AMS_SECRET_SALT_2026_@GOOGLE_DEEPMIND_ANTIGRAVITY_SECURE_KEY"
SECRET_SALT = os.environ.get("NOVACUT_LOCAL_INTEGRITY_KEY", "").strip() or DEFAULT_LOCAL_SALT

_last_qr_generation_epoch = 0
_quota_lock = threading.RLock()
_processed_tx_lock = threading.RLock()
_trial_registration_lock = threading.RLock()
_last_trial_registration_attempt = 0
TRIAL_REGISTRATION_RETRY_SECONDS = 60
CLOUD_SYNC_MIN_INTERVAL_SECONDS = 60
_cloud_sync_lock = threading.Lock()
_last_cloud_sync_attempt = 0.0
_cloud_sync_in_progress = False
_sync_execution_lock = threading.Lock()
_last_sync_result = None
_last_sync_result_time = 0.0
SYNC_CACHE_DEBOUNCE_SECONDS = 5.0


def _atomic_write_json(path, payload):
    """Write security-sensitive state without leaving a partial file on interruption."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

def load_last_sync_state():
    """Đọc trạng thái (tier, expire_epoch, status) của lần sync cloud gần nhất từ file local."""
    try:
        if os.path.exists(LAST_SYNC_STATE_FILE):
            with open(LAST_SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_last_sync_state(license_status: dict):
    """Lưu trạng thái cloud sync thành công vào file — chỉ giữ các field cần so sánh."""
    state = {
        'tier': license_status.get('tier', ''),
        'expire_epoch': license_status.get('expire_epoch', 0),
        'status': license_status.get('status', ''),
        'saved_at': time.time(),
    }
    try:
        _atomic_write_json(LAST_SYNC_STATE_FILE, state)
    except Exception:
        pass


def _tier_rank(tier: str) -> int:
    """Trả về thứ bậc của tier để so sánh nâng/hạ gói."""
    order = {'unlicensed': 0, 'trial': 1, 'basic': 2, 'pro': 3, 'vip': 4, 'yearly': 5, 'admin': 99}
    return order.get(str(tier).lower(), -1)


_last_sync_state_lock = threading.RLock()


def sync_and_detect_event(force=False):
    """
    Critical section nguyên tử (Thread-safe & Race-condition free):
    1. Đồng bộ cloud
    2. Đọc baseline cũ trong lock
    3. Xác định sự kiện (kích hoạt mới, nâng gói, gia hạn)
    4. Luôn cập nhật baseline mới (kể cả downgrade hay no-event)
    5. Trả về (success, current_status, is_event, was_upgraded, was_renewed)
    """
    with _last_sync_state_lock:
        license_info = sync_with_cloud(force=force)
        current_status = get_current_license_status()

        if not current_status or not current_status.get('is_valid'):
            if current_status:
                save_last_sync_state(current_status)
            return bool(license_info), current_status, False, False, False

        prev_state = load_last_sync_state()

        # Nếu chưa từng có baseline (lần đầu khởi chạy), chỉ lưu baseline và không bắn event
        if not prev_state or not prev_state.get('tier'):
            save_last_sync_state(current_status)
            return bool(license_info), current_status, False, False, False

        prev_tier = str(prev_state.get('tier', '') or '').lower()
        curr_tier = str(current_status.get('tier', '') or '').lower()
        prev_expire = int(prev_state.get('expire_epoch') or 0)
        curr_expire = int(current_status.get('expire_epoch') or 0)
        prev_status = str(prev_state.get('status', '') or '').upper()
        curr_status = str(current_status.get('status', '') or '').upper()

        was_newly_activated = (prev_status != 'ACTIVE' and curr_status == 'ACTIVE')
        was_upgraded = (curr_tier != prev_tier and _tier_rank(curr_tier) > _tier_rank(prev_tier))
        # Chỉ coi là gia hạn nếu cùng gói (hoặc không bị hạ gói) và hạn dùng tăng lên
        was_renewed = (_tier_rank(curr_tier) >= _tier_rank(prev_tier) and curr_expire > prev_expire > 0)

        is_event = was_newly_activated or was_upgraded or was_renewed

        # Luôn lưu baseline mới nhất để các lần sau có dữ liệu đối soát chuẩn xác
        save_last_sync_state(current_status)

        return bool(license_info), current_status, is_event, was_upgraded, was_renewed



def _load_processed_tx_ids():
    """Tải danh sách các mã giao dịch SePay đã từng được kích hoạt để chống lặp lại."""
    if not os.path.exists(PROCESSED_TX_FILE):
        return set()
    try:
        with open(PROCESSED_TX_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(x) for x in data) if isinstance(data, list) else set()
    except Exception:
        return set()

def _save_processed_tx_id(tx_id):
    """Ghi nhận vĩnh viễn mã giao dịch đã được sử dụng."""
    if not tx_id:
        return
    try:
        with _processed_tx_lock:
            current = _load_processed_tx_ids()
            current.add(str(tx_id))
            _atomic_write_json(PROCESSED_TX_FILE, sorted(current))
    except Exception as e:
        print(f"Lỗi lưu lịch sử giao dịch: {e}")

# Thông tin nhận thanh toán là dữ liệu công khai, nhưng phải do bản phát hành
# quản lý. Không lấy ba trường này từ %APPDATA% để tránh một cấu hình cũ (hoặc
# bị chỉnh sửa) hiển thị QR chuyển tiền sai trên máy khách.
MANAGED_PAYMENT_CONFIG = {
    "bank_code": "TPBank",
    "bank_account": "02151334904",
    "bank_account_name": "NGUYEN HOANG NAM",
}

# Cấu hình Mặc định Bảng giá & VietQR SePay
DEFAULT_CONFIG = {
    "google_apps_script_url": os.environ.get("NOVACUT_LICENSE_API_URL", "").strip(),
    "client_license_token": os.environ.get("NOVACUT_CLIENT_LICENSE_TOKEN", "").strip(),
    "api_secret_token": os.environ.get("NOVACUT_LICENSE_API_TOKEN", "").strip(),
    "sepay_api_token": "",
    **MANAGED_PAYMENT_CONFIG,
    "prices": {
        "trial": 0,
        "pro": 300000,
        "vip": 500000,
        "yearly": 3990000
    }
}

def load_app_config():
    """Đọc cấu hình cloud và thông tin thanh toán do bản phát hành quản lý."""
    cfg = {**DEFAULT_CONFIG, "prices": dict(DEFAULT_CONFIG["prices"])}
    legacy_cfg = os.path.join(ROOT_DIR, 'license_config.json')
    # Bản EXE nhận cấu hình kết nối tối thiểu từ PyInstaller resource. File này
    # chỉ chứa URL + token bản quyền, không có SePay token hoặc thông tin ngân
    # hàng; như vậy máy cài mới vẫn đồng bộ được mà không phụ thuộc AppData.
    if BOOTSTRAP_CONFIG_FILE and os.path.exists(BOOTSTRAP_CONFIG_FILE):
        try:
            with open(BOOTSTRAP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                bootstrap_data = json.load(f)
            for key in ("google_apps_script_url", "client_license_token"):
                value = bootstrap_data.get(key)
                if isinstance(value, str) and value.strip():
                    cfg[key] = value.strip()
        except Exception:
            pass
    # Trong môi trường phát triển, file gốc vẫn là nơi cấu hình server. Khi
    # đóng gói, file này không được phát hành vì có secret.
    if not getattr(sys, 'frozen', False) and os.path.exists(legacy_cfg):
        try:
            with open(legacy_cfg, 'r', encoding='utf-8') as f:
                legacy_data = json.load(f)
            # license_config.json từ các bản cũ có thể còn tài khoản MBBank.
            # Chỉ lấy cấu hình kết nối cloud; đích nhận tiền luôn theo bản phát
            # hành hoặc biến môi trường triển khai bên dưới.
            for key in ("google_apps_script_url", "client_license_token", "api_secret_token", "sepay_api_token", "prices"):
                if key in legacy_data:
                    cfg[key] = legacy_data[key]
        except Exception:
            pass

    # Không nhận endpoint hoặc credential từ AppData. Nếu người dùng có thể
    # trỏ app tới server của họ và tự chọn token, họ cũng có thể tự ký phản hồi
    # HMAC để vượt bản quyền. EXE mới dùng resource bootstrap chỉ-đọc; môi
    # trường triển khai đáng tin cậy có thể ghi đè ở bên dưới.

    # Cho phép cấu hình ở môi trường triển khai đáng tin cậy ghi đè khi cần,
    # nhưng không dùng dữ liệu tùy ý trong AppData.
    for key, env_name in (
        ("bank_code", "NOVACUT_BANK_CODE"),
        ("bank_account", "NOVACUT_BANK_ACCOUNT"),
        ("bank_account_name", "NOVACUT_BANK_ACCOUNT_NAME"),
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            cfg[key] = value
    return cfg

def save_app_config(new_cfg):
    """Lưu cấu hình server-side."""
    cfg = load_app_config()
    cfg.update(new_cfg)
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def get_trusted_network_time():
    """
    Truy vấn thời gian chuẩn quốc tế từ HTTP Date Header của các máy chủ lớn (Google/Cloudflare).
    Trả về (epoch: int, date_str: str) nếu có mạng, hoặc None nếu hoàn toàn offline.
    """
    endpoints = [
        "https://www.google.com",
        "https://1.1.1.1",
        "https://www.cloudflare.com"
    ]
    for url in endpoints:
        try:
            res = requests.head(url, timeout=2.0)
            date_val = res.headers.get('Date')
            if date_val:
                dt = email.utils.parsedate_to_datetime(date_val)
                epoch = int(dt.timestamp())
                return epoch, dt.strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            continue
    return None, None


def verify_clock_integrity(cached_payload):
    """
    (Anti-Clock Rollback)
    Kiểm tra xem đồng hồ hệ thống Windows có bị chỉnh lùi về quá khứ hay không.
    So sánh giữa thời gian máy hiện tại với last_seen_epoch đã lưu và ký số HMAC.
    Thực hiện kiểm tra tức thì (instant) không block luồng mạng.
    """
    if not cached_payload:
        return True, "OK"

    now_epoch = int(time.time())
    last_seen = int(cached_payload.get('last_seen_epoch', 0))

    # Nếu thời gian máy tính bị chỉnh lùi quá 300 giây (5 phút) so với mốc thời gian đã ghi nhận trước đó
    if last_seen > 0 and now_epoch < (last_seen - 300):
        err_msg = f"Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ! (Hiện tại: {now_epoch}, Mốc ghi nhận: {last_seen}). Vui lòng chỉnh lại ngày giờ chính xác hoặc kết nối Internet để đồng bộ."
        return False, err_msg

    return True, "OK"


def verify_cloud_signature(data_dict, secret_token):
    """
    (Anti-MITM / Anti-Fiddler)
    Xác thực chữ ký số HMAC-SHA256 của gói tin trả về từ Google Apps Script.
    Chống kẻ gian dùng Proxy (Fiddler/Charles) sửa nội dung {valid: true}.
    """
    if not isinstance(data_dict, dict):
        return False
    
    sig_received = data_dict.get('sig', '')
    if not sig_received:
        return False

    hwid = str(data_dict.get('hwid', '')).upper()
    tier = str(data_dict.get('tier', '')).lower()
    status = str(data_dict.get('status', '')).upper()
    expire_date = str(data_dict.get('expire_date', ''))
    expire_epoch = str(data_dict.get('expire_epoch', 0))
    nonce = str(data_dict.get('nonce', ''))
    server_time = str(data_dict.get('server_time', ''))

    raw_sign_string = f"{hwid}|{tier}|{status}|{expire_date}|{expire_epoch}|{nonce}|{server_time}"
    expected_sig = hmac.new(secret_token.encode('utf-8'), raw_sign_string.encode('utf-8'), hashlib.sha256).hexdigest()

    return hmac.compare_digest(sig_received, expected_sig)


_CACHED_RAW_HWID = None
_CACHED_HWID = None

def _get_machine_trial_anchor():
    """Đọc mốc dùng thử từ Registry Windows để chống việc người dùng ngắt mạng xóa file .license.dat."""
    try:
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\AMS_MovieShorts\Security", 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "TrialExpireEpoch")
                if val:
                    return int(val)
    except Exception:
        pass
    return None

def _set_machine_trial_anchor(expire_epoch):
    """Ghi mốc dùng thử vào Registry Windows."""
    try:
        if os.name == 'nt':
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\AMS_MovieShorts\Security")
            winreg.SetValueEx(key, "TrialExpireEpoch", 0, winreg.REG_SZ, str(expire_epoch))
            winreg.CloseKey(key)
    except Exception:
        pass

def get_hardware_raw_components():
    """Thu thập thông số phần cứng máy tính (Motherboard UUID + CPU ID + BaseBoard Serial) với Registry cache siêu tốc."""
    global _CACHED_RAW_HWID
    if _CACHED_RAW_HWID:
        return _CACHED_RAW_HWID

    # 1. Đọc nhanh từ Registry Cache (0.01ms)
    try:
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\AMS_MovieShorts\Security", 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "HardwareAnchor")
                if val and len(val.split('|')) == 3:
                    _CACHED_RAW_HWID = val
                    return _CACHED_RAW_HWID
    except Exception:
        pass

    uuid_str = ""
    cpu_str = ""
    board_str = ""

    if os.name == 'nt':
        try:
            # Lấy đồng thời cả 3 thông số trong 1 lệnh PowerShell duy nhất
            ps_cmd = "$u=(Get-CimInstance Win32_ComputerSystemProduct).UUID; $c=(Get-CimInstance Win32_Processor).ProcessorId; $b=(Get-CimInstance Win32_BaseBoard).SerialNumber; \"$u|$c|$b\""
            res = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, creationflags=0x08000000 if os.name == 'nt' else 0)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split('|')
                if len(parts) >= 1: uuid_str = parts[0].strip()
                if len(parts) >= 2: cpu_str = parts[1].strip()
                if len(parts) >= 3: board_str = parts[2].strip()
        except Exception:
            pass

        if not uuid_str:
            try:
                cmd = ['wmic', 'csproduct', 'get', 'uuid']
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3, creationflags=0x08000000 if os.name == 'nt' else 0)
                lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and 'UUID' not in l.upper()]
                if lines: uuid_str = lines[0]
            except Exception:
                pass
    else:
        try:
            with open('/etc/machine-id', 'r') as f:
                uuid_str = f.read().strip()
        except Exception:
            uuid_str = os.uname().nodename

    if not uuid_str: uuid_str = "FALLBACK-UUID-001"
    if not cpu_str: cpu_str = "FALLBACK-CPU-001"
    if not board_str: board_str = "FALLBACK-MB-001"

    _CACHED_RAW_HWID = f"{uuid_str.upper()}|{cpu_str.upper()}|{board_str.upper()}"

    # Lưu vào Registry Cache để lần sau đọc trong 0.01ms
    try:
        if os.name == 'nt':
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\AMS_MovieShorts\Security")
            winreg.SetValueEx(key, "HardwareAnchor", 0, winreg.REG_SZ, _CACHED_RAW_HWID)
            winreg.CloseKey(key)
    except Exception:
        pass

    return _CACHED_RAW_HWID


def get_hardware_id():
    """
    Sinh mã định danh máy tính duy nhất (HWID) định dạng: AMS-XXXX-XXXX-XXXX
    Không đổi khi cài lại ứng dụng hoặc khởi động lại máy tính.
    """
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    raw = get_hardware_raw_components()
    h = hashlib.sha256((raw + SECRET_SALT).encode('utf-8')).hexdigest().upper()
    # Lấy 12 ký tự hex chia làm 3 cụm: AMS-A1B2-C3D4-E5F6
    part1 = h[0:4]
    part2 = h[4:8]
    part3 = h[8:12]
    _CACHED_HWID = f"AMS-{part1}-{part2}-{part3}"
    return _CACHED_HWID


def get_short_hwid(hwid=None):
    """Lấy 6 ký tự rút gọn của HWID để dùng làm cú pháp chuyển khoản ngắn gọn (e.g. A1B2C3)."""
    if not hwid:
        hwid = get_hardware_id()
    clean = hwid.replace('AMS-', '').replace('-', '')
    return clean[:6].upper()


def _sign_payload(data_dict):
    """Ký số HMAC-SHA256 cho dữ liệu cache để chống người dùng sửa file offline."""
    if not SECRET_SALT:
        return ""
    raw_str = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    sig = hmac.new(SECRET_SALT.encode('utf-8'), raw_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return sig


def save_local_license_cache(license_data):
    """Lưu trữ chứng chỉ bản quyền mã hóa kèm chữ ký HMAC và mốc thời gian last_seen_epoch."""
    try:
        hwid = get_hardware_id()
        now_epoch = int(time.time())
        last_seen = int(license_data.get('last_seen_epoch') or now_epoch)

        payload = {
            "hwid": hwid,
            "tier": license_data.get('tier', 'unlicensed'),
            "status": str(license_data.get('status') or '').upper(),
            "plan_name": license_data.get('plan_name', 'Chưa kích hoạt'),
            "expire_epoch": int(license_data.get('expire_epoch', 0)),
            "expire_str": license_data.get('expire_str', ''),
            "activated_at": int(license_data.get('activated_at', now_epoch)),
            "last_seen_epoch": max(last_seen, now_epoch),
            "user_name": license_data.get('user_name', ''),
            "phone_zalo": license_data.get('phone_zalo', ''),
            "pro_selected_module": license_data.get('pro_selected_module', None),
            "features": license_data.get('features', {})
        }
        sig = _sign_payload(payload)
        if not sig:
            print("Không thể lưu cache bản quyền: thiếu NOVACUT_LOCAL_INTEGRITY_KEY")
            return False
        envelope = {
            "p": base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii'),
            "s": sig
        }
        _atomic_write_json(LICENSE_CACHE_FILE, envelope)
        return True
    except Exception as e:
        print(f"Lỗi lưu cache bản quyền: {e}")
        return False


def load_local_license_cache(auto_update_clock=True):
    """Đọc và giải mã chứng chỉ bản quyền offline, xác thực chữ ký HMAC và kiểm tra Anti-Clock Rollback."""
    target_file = LICENSE_CACHE_FILE
    if not os.path.exists(target_file):
        fallback = os.path.join(ROOT_DIR, '.license.dat')
        if os.path.exists(fallback):
            target_file = fallback
        else:
            return None
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            envelope = json.load(f)
        b64_p = envelope.get('p', '')
        sig = envelope.get('s', '')
        raw_json = base64.b64decode(b64_p).decode('utf-8')
        payload = json.loads(raw_json)
        
        # 1. Kiểm tra chữ ký HMAC
        expected_sig = _sign_payload(payload)
        if not expected_sig or not hmac.compare_digest(sig, expected_sig):
            print("⚠️ Chữ ký bản quyền không hợp lệ (Dữ liệu đã bị can thiệp)!")
            return None
        
        # 2. Kiểm tra HWID khớp với máy hiện tại
        current_hwid = get_hardware_id()
        if payload.get('hwid') != current_hwid:
            print("⚠️ Mã máy HWID không khớp với chứng chỉ bản quyền!")
            return None

        # 3. Anti-Clock Rollback: Kiểm tra đồng hồ hệ thống có bị chỉnh lùi về quá khứ không
        is_clock_valid, clock_msg = verify_clock_integrity(payload)
        if not is_clock_valid:
            print(f"⚠️ {clock_msg}")
            payload['clock_tampered'] = True
            payload['clock_error'] = clock_msg
            return payload
        else:
            payload['clock_tampered'] = False
            # Tự động cập nhật mốc thời gian mới nếu đã trôi qua hơn 30 phút
            now_epoch = int(time.time())
            last_seen = int(payload.get('last_seen_epoch', 0))
            if auto_update_clock and (now_epoch - last_seen > 1800):
                payload['last_seen_epoch'] = now_epoch
                save_local_license_cache(payload)
            
        return payload
    except Exception as e:
        print(f"Lỗi đọc cache bản quyền: {e}")
        return None


# ═════════════════════════════════════════════════════════════════
# 🪙 QUẢN LÝ ĐỊNH MỨC TOKEN (QUOTA: 1M GỬI ĐI & 1M NHẬN VỀ)
# ═════════════════════════════════════════════════════════════════

def load_token_quota_stats():
    """Đọc dữ liệu thống kê token sử dụng và xác thực chữ ký HMAC."""
    default_stats = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "last_updated": int(time.time()),
        "max_prompt_tokens": MAX_PROMPT_TOKENS,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "max_total_tokens": MAX_PROMPT_TOKENS + MAX_COMPLETION_TOKENS
    }
    if not SECRET_SALT:
        default_stats["prompt_tokens"] = MAX_PROMPT_TOKENS
        default_stats["completion_tokens"] = MAX_COMPLETION_TOKENS
        default_stats["total_tokens"] = MAX_PROMPT_TOKENS + MAX_COMPLETION_TOKENS
        default_stats["integrity_error"] = "Thiếu NOVACUT_LOCAL_INTEGRITY_KEY"
        return default_stats
    if not os.path.exists(TOKEN_CACHE_FILE):
        return default_stats
    try:
        with open(TOKEN_CACHE_FILE, 'r', encoding='utf-8') as f:
            envelope = json.load(f)
        b64_p = envelope.get('p', '')
        sig = envelope.get('s', '')
        raw_json = base64.b64decode(b64_p).decode('utf-8')
        payload = json.loads(raw_json)

        expected_sig = _sign_payload(payload)
        if not expected_sig or not hmac.compare_digest(sig, expected_sig):
            print("⚠️ Chữ ký bộ đếm Token không hợp lệ!")
            default_stats["prompt_tokens"] = MAX_PROMPT_TOKENS
            default_stats["completion_tokens"] = MAX_COMPLETION_TOKENS
            default_stats["total_tokens"] = MAX_PROMPT_TOKENS + MAX_COMPLETION_TOKENS
            default_stats["integrity_error"] = "Chữ ký bộ đếm không hợp lệ"
            return default_stats

        payload["max_prompt_tokens"] = MAX_PROMPT_TOKENS
        payload["max_completion_tokens"] = MAX_COMPLETION_TOKENS
        payload["max_total_tokens"] = MAX_PROMPT_TOKENS + MAX_COMPLETION_TOKENS
        payload["total_tokens"] = payload.get("prompt_tokens", 0) + payload.get("completion_tokens", 0)
        return payload
    except Exception as e:
        print(f"Lỗi đọc token quota: {e}")
        return default_stats


def save_token_quota_stats(stats):
    """Lưu trữ thống kê token kèm chữ ký số HMAC."""
    try:
        payload = {
            "prompt_tokens": int(stats.get("prompt_tokens", 0)),
            "completion_tokens": int(stats.get("completion_tokens", 0)),
            "total_tokens": int(stats.get("prompt_tokens", 0)) + int(stats.get("completion_tokens", 0)),
            "requests": int(stats.get("requests", 0)),
            "last_updated": int(time.time())
        }
        sig = _sign_payload(payload)
        if not sig:
            return False
        envelope = {
            "p": base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii'),
            "s": sig
        }
        _atomic_write_json(TOKEN_CACHE_FILE, envelope)
        return True
    except Exception as e:
        print(f"Lỗi lưu token quota: {e}")
        return False


def check_token_quota():
    """
    Kiểm tra xem người dùng đã vượt quá hạn mức 1,000,000 token gửi đi (Prompt)
    hoặc 1,000,000 token nhận về (Completion) hay chưa.
    """
    stats = load_token_quota_stats()
    prompt_used = stats.get("prompt_tokens", 0)
    completion_used = stats.get("completion_tokens", 0)

    if prompt_used >= MAX_PROMPT_TOKENS:
        return False, f"⚠️ Bạn đã đạt giới hạn tối đa 1,000,000 Token gửi đi (Prompt: {prompt_used:,} / 1,000,000). Vui lòng liên hệ Admin để nâng cấp thêm Token!"

    if completion_used >= MAX_COMPLETION_TOKENS:
        return False, f"⚠️ Bạn đã đạt giới hạn tối đa 1,000,000 Token nhận về (Completion: {completion_used:,} / 1,000,000). Vui lòng liên hệ Admin để nâng cấp thêm Token!"

    return True, "OK"


def record_token_usage(prompt_tokens=0, completion_tokens=0):
    """Ghi nhận số lượng token đã sử dụng sau mỗi lượt gọi OpenAI."""
    with _quota_lock:
        stats = load_token_quota_stats()
        stats["prompt_tokens"] = stats.get("prompt_tokens", 0) + max(0, int(prompt_tokens))
        stats["completion_tokens"] = stats.get("completion_tokens", 0) + max(0, int(completion_tokens))
        stats["total_tokens"] = stats["prompt_tokens"] + stats["completion_tokens"]
        stats["requests"] = stats.get("requests", 0) + 1
        save_token_quota_stats(stats)
        return stats


def reset_token_quota_stats():
    """(Dành cho Admin) Đặt lại bộ đếm token về 0."""
    stats = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "last_updated": int(time.time())
    }
    with _quota_lock:
        return save_token_quota_stats(stats)


# --- PHÂN QUYỀN TÍNH NĂNG TỪNG GÓI ---
PACKAGE_TIERS = {
    "trial": {
        "tier": "trial",
        "plan_name": "Dùng Thử 24h",
        "badge_class": "badge-trial",
        "badge_text": "⚡ Dùng Thử",
        "features": {
            "can_access_review": True,
            "can_access_editor": True,
            "can_access_batch": False, # Chỉ dành riêng cho Admin Quản Trị
            "can_clone_voice": True,
            "clone_voice_limit": 2,
            "allow_save_cloned_voice": False,
            "max_video_export_duration": 60, # Tối đa 60s
            "tts_unlimited_local": True,
            "online_voices_enabled": False,
            "cloud_gpt_included": True
        }
    },
    "pro": {
        "tier": "pro",
        "plan_name": "Gói Pro (300k/tháng)",
        "badge_class": "badge-pro",
        "badge_text": "⭐ Gói Pro",
        "features": {
            "can_access_review": True,
            "can_access_editor": True,
            "can_access_batch": False, # Chỉ dành riêng cho Admin Quản Trị
            "can_clone_voice": True,
            "clone_voice_limit": 1,
            "allow_save_cloned_voice": True,
            "max_video_export_duration": 99999,
            "tts_unlimited_local": True,
            "online_voices_enabled": False,
            "cloud_gpt_included": False # Tự túc API key
        }
    },
    "vip": {
        "tier": "vip",
        "plan_name": "Gói VIP (500k/tháng)",
        "badge_class": "badge-vip",
        "badge_text": "👑 Gói VIP",
        "features": {
            "can_access_review": True,
            "can_access_editor": True,
            "can_access_batch": False, # Chỉ dành riêng cho Admin Quản Trị
            "can_clone_voice": True,
            "clone_voice_limit": 5,
            "allow_save_cloned_voice": True,
            "max_video_export_duration": 99999,
            "tts_unlimited_local": True,
            "online_voices_enabled": True, # Full 1000+ giọng
            "cloud_gpt_included": True      # Bao server GPT
        }
    },
    "yearly": {
        "tier": "yearly",
        "plan_name": "Gói 1 Năm (3.990k)",
        "badge_class": "badge-yearly",
        "badge_text": "💎 Gói 1 Năm",
        "features": {
            "can_access_review": True,
            "can_access_editor": True,
            "can_access_batch": False, # Chỉ dành riêng cho Admin Quản Trị
            "can_clone_voice": True,
            "clone_voice_limit": 99,
            "allow_save_cloned_voice": True,
            "max_video_export_duration": 99999,
            "tts_unlimited_local": True,
            "online_voices_enabled": True,
            "cloud_gpt_included": True
        }
    },
    "admin": {
        "tier": "admin",
        "plan_name": "Tài Khoản Quản Trị (Admin)",
        "badge_class": "badge-admin",
        "badge_text": "🛡️ Admin Quản Trị",
        "features": {
            "can_access_review": True,
            "can_access_editor": True,
            "can_access_batch": True,
            "can_clone_voice": True,
            "clone_voice_limit": 9999,
            "allow_save_cloned_voice": True,
            "max_video_export_duration": 999999,
            "tts_unlimited_local": True,
            "online_voices_enabled": True,
            "cloud_gpt_included": True,
            "is_admin": True
        }
    },
    "unlicensed": {
        "tier": "unlicensed",
        "plan_name": "Chưa Kích Hoạt",
        "badge_class": "badge-unlicensed",
        "badge_text": "🔒 Chưa Kích Hoạt",
        "features": {
            "can_access_review": False,
            "can_access_editor": False,
            "can_access_batch": False,
            "can_clone_voice": False,
            "clone_voice_limit": 0,
            "allow_save_cloned_voice": False,
            "max_video_export_duration": 0,
            "tts_unlimited_local": False,
            "online_voices_enabled": False,
            "cloud_gpt_included": False
        }
    }
}


def schedule_background_cloud_sync():
    """Đồng bộ cloud ở nền, tối đa một lần mỗi phút để không chặn UI hay spam Sheet."""
    global _last_cloud_sync_attempt, _cloud_sync_in_progress

    now = time.monotonic()
    with _cloud_sync_lock:
        if _cloud_sync_in_progress or (now - _last_cloud_sync_attempt) < CLOUD_SYNC_MIN_INTERVAL_SECONDS:
            return False
        _last_cloud_sync_attempt = now
        _cloud_sync_in_progress = True

    def _worker():
        global _cloud_sync_in_progress
        try:
            sync_with_cloud()
        except Exception as exc:
            # sync_with_cloud đã tự xử lý lỗi thông thường; đây là hàng rào cuối
            # để worker daemon không làm gián đoạn luồng ứng dụng.
            print(f"Lỗi đồng bộ bản quyền nền: {exc}")
        finally:
            with _cloud_sync_lock:
                _cloud_sync_in_progress = False

    try:
        threading.Thread(target=_worker, name='silent-license-cloud-sync', daemon=True).start()
        return True
    except Exception:
        with _cloud_sync_lock:
            _cloud_sync_in_progress = False
        return False


def get_current_license_status(force_cloud_sync=False):
    """
    Trả về thông tin bản quyền hiện tại của máy tính trong < 1ms.
    Tự động tính toán số ngày / giờ còn lại và trạng thái hợp lệ.
    """
    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid)
    cached = load_local_license_cache()

    if force_cloud_sync:
        sync_with_cloud(force=True)
        cached = load_local_license_cache()
    else:
        schedule_background_cloud_sync()

    now_epoch = int(time.time())

    # Nếu chưa có file .license.dat:
    if not cached:
        # 1. Kiểm tra mốc dùng thử từ Registry Windows (Chống ngắt mạng & xóa file dùng chùa)
        trial_anchor_epoch = _get_machine_trial_anchor()

        if trial_anchor_epoch:
            # Máy này ĐÃ TỪNG DÙNG THỬ trước đó
            if trial_anchor_epoch <= now_epoch:
                # Đã hết 24h -> EXPIRED ngay lập tức, tuyệt đối không cấp thêm trial
                unlic_tier = PACKAGE_TIERS["unlicensed"]
                expired_cache = {
                    "hwid": hwid,
                    "tier": "unlicensed",
                    "plan_name": "Gói Dùng Thử (Đã hết hạn)",
                    "expire_epoch": trial_anchor_epoch,
                    "expire_str": datetime.fromtimestamp(trial_anchor_epoch).strftime('%d/%m/%Y %H:%M'),
                    "activated_at": trial_anchor_epoch - 86400,
                    "features": unlic_tier["features"]
                }
                save_local_license_cache(expired_cache)
                cached = expired_cache
            else:
                # Vẫn còn thời gian của lần dùng thử trước
                plan_info = PACKAGE_TIERS["trial"]
                cached = {
                    "hwid": hwid,
                    "tier": "trial",
                    "plan_name": plan_info["plan_name"],
                    "expire_epoch": trial_anchor_epoch,
                    "expire_str": datetime.fromtimestamp(trial_anchor_epoch).strftime('%d/%m/%Y %H:%M'),
                    "activated_at": trial_anchor_epoch - 86400,
                    "user_name": "Khách Dùng Thử 24h",
                    "features": plan_info["features"]
                }
                save_local_license_cache(cached)
        else:
            # 2. Máy mới cài đặt lần đầu 100%: Tự động cấp 24h Dùng Thử
            now = datetime.now()
            expire_dt = now + timedelta(hours=24)
            expire_epoch = int(expire_dt.timestamp())
            expire_str = expire_dt.strftime('%d/%m/%Y %H:%M')
            plan_info = PACKAGE_TIERS["trial"]

            # Ghi mốc vào Registry Windows
            _set_machine_trial_anchor(expire_epoch)

            cached = {
                "hwid": hwid,
                "tier": "trial",
                "plan_name": plan_info["plan_name"],
                "expire_epoch": expire_epoch,
                "expire_str": expire_str,
                "activated_at": int(now.timestamp()),
                "user_name": "Khách Dùng Thử 24h",
                "phone_zalo": "",
                "features": plan_info["features"],
                "is_first_launch": True
            }
            save_local_license_cache(cached)

    # Máy đã có cache dùng thử từ một lần gửi hỏng trước đó cũng được tự đồng
    # bộ lại theo nhịp giới hạn. Đây là phần còn thiếu khiến khách không xuất
    # hiện trên Sheet dù vẫn dùng thử bình thường trên máy.
    schedule_trial_cloud_registration(cached)

    # Anti-Clock Rollback: Nếu phát hiện đồng hồ bị lùi giờ
    if cached.get('clock_tampered'):
        return {
            "hwid": hwid,
            "short_hwid": short_hwid,
            "status": "CLOCK_TAMPERED",
            "is_valid": False,
            "tier": "unlicensed",
            "plan_name": "Lỗi Đồng Hồ Hệ Thống",
            "badge_class": "badge-expired",
            "badge_text": "⚠️ Lỗi Đồng Hồ",
            "expire_str": cached.get('expire_str', ''),
            "expire_epoch": 0,
            "days_left": 0,
            "hours_left": 0,
            "clock_error": cached.get('clock_error', 'Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ! Vui lòng chỉnh lại đúng giờ hoặc kết nối Internet để đồng bộ.'),
            "features": PACKAGE_TIERS["unlicensed"]["features"],
            "can_activate_trial": False
        }

    expire_epoch = int(cached.get('expire_epoch', 0))
    tier = cached.get('tier', 'unlicensed')
    base_tier_info = PACKAGE_TIERS.get(tier, PACKAGE_TIERS["unlicensed"])
    cached_status = str(cached.get('status') or '').upper()

    # Trạng thái bị khóa/hết hạn từ cloud phải được ưu tiên hơn cache cũ để
    # quản trị viên có thể vô hiệu hóa hoặc hết hạn bản quyền ngay lập tức.
    if cached_status == 'BLOCKED':
        return {
            "hwid": hwid,
            "short_hwid": short_hwid,
            "status": "BLOCKED",
            "is_valid": False,
            "tier": "unlicensed",
            "plan_name": cached.get('plan_name') or "Bản quyền đã bị khóa",
            "badge_class": "badge-expired",
            "badge_text": "🔒 Bản quyền bị khóa",
            "expire_str": cached.get('expire_str', ''),
            "expire_epoch": 0,
            "days_left": 0,
            "hours_left": 0,
            "user_name": cached.get('user_name', ''),
            "phone_zalo": cached.get('phone_zalo', ''),
            "features": PACKAGE_TIERS["unlicensed"]["features"],
            "can_activate_trial": False
        }

    if cached_status == 'EXPIRED':
        return {
            "hwid": hwid,
            "short_hwid": short_hwid,
            "status": "EXPIRED",
            "is_valid": False,
            "tier": "expired",
            "plan_name": f"Hết hạn ({base_tier_info['plan_name']})",
            "badge_class": "badge-expired",
            "badge_text": "🔒 Đã hết hạn",
            "expire_str": cached.get('expire_str') or (datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M') if expire_epoch else ''),
            "expire_epoch": expire_epoch,
            "days_left": 0,
            "hours_left": 0,
            "user_name": cached.get('user_name', ''),
            "phone_zalo": cached.get('phone_zalo', ''),
            "features": PACKAGE_TIERS["unlicensed"]["features"],
            "can_activate_trial": False
        }

    machine_has_used_trial = _get_machine_trial_anchor() is not None

    if expire_epoch > now_epoch:
        # Còn hạn sử dụng
        seconds_left = expire_epoch - now_epoch
        days_left = seconds_left // 86400
        hours_left = (seconds_left % 86400) // 3600
        
        if days_left > 0:
            badge_text = f"{base_tier_info['badge_text']} ({days_left} ngày)"
        else:
            badge_text = f"{base_tier_info['badge_text']} ({hours_left}h)"

        features = dict(base_tier_info["features"])
        pro_selected_module = cached.get('pro_selected_module', None)
        if tier == 'pro':
            if pro_selected_module == 'review':
                features['can_access_review'] = True
                features['can_access_editor'] = False
            elif pro_selected_module == 'editor':
                features['can_access_editor'] = True
                features['can_access_review'] = False
            else:
                # Chưa chọn Module: Khóa cả 2 module cho đến khi người dùng chọn trong modal
                features['can_access_editor'] = False
                features['can_access_review'] = False

        return {
            "hwid": hwid,
            "short_hwid": short_hwid,
            "status": "ACTIVE",
            "is_valid": True,
            "tier": tier,
            "plan_name": base_tier_info["plan_name"],
            "badge_class": base_tier_info["badge_class"],
            "badge_text": badge_text,
            "expire_str": cached.get('expire_str') or datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M'),
            "expire_epoch": expire_epoch,
            "days_left": int(days_left),
            "hours_left": int(hours_left),
            "user_name": cached.get('user_name', ''),
            "phone_zalo": cached.get('phone_zalo', ''),
            "pro_selected_module": pro_selected_module,
            "vip_api_keys": cached.get('vip_api_keys', {}),
            "features": features,
            "can_activate_trial": False
        }
    else:
        # Đã hết hạn hoặc chưa kích hoạt
        can_trial = not machine_has_used_trial
        return {
            "hwid": hwid,
            "short_hwid": short_hwid,
            "status": "EXPIRED" if machine_has_used_trial else "UNLICENSED",
            "is_valid": False,
            "tier": "expired" if machine_has_used_trial else "unlicensed",
            "plan_name": f"Hết hạn ({base_tier_info['plan_name']})" if machine_has_used_trial else "Chưa Kích Hoạt",
            "badge_class": "badge-expired" if machine_has_used_trial else "badge-unlicensed",
            "badge_text": "🔒 Đã hết hạn" if machine_has_used_trial else "🔒 Chưa Kích Hoạt",
            "expire_str": cached.get('expire_str') or (datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M') if expire_epoch else ''),
            "expire_epoch": expire_epoch,
            "days_left": 0,
            "hours_left": 0,
            "user_name": cached.get('user_name', ''),
            "phone_zalo": cached.get('phone_zalo', ''),
            "features": PACKAGE_TIERS["unlicensed"]["features"],
            "can_activate_trial": can_trial
        }


def check_permission(feature_name):
    """
    (Bảo Mật & Phân Quyền)
    Kiểm tra xem máy tính hiện tại có quyền sử dụng tính năng feature_name hay không.
    Trả về: (is_allowed: bool, reason_message: str, status_dict: dict)
    """
    status = get_current_license_status()
    if not status.get('is_valid', False):
        if status.get('status') == 'EXPIRED':
            return False, f"⚠️ Bản quyền {status.get('plan_name', '')} của bạn đã hết hạn (Hạn dùng: {status.get('expire_str', '')}). Vui lòng gia hạn gói để tiếp tục sử dụng tính năng này!", status
        elif status.get('status') == 'CLOCK_TAMPERED':
            return False, f"⚠️ Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ! Vui lòng chỉnh lại đúng ngày giờ chuẩn hoặc kết nối mạng để đồng bộ.", status
        else:
            return False, "⚠️ Ứng dụng chưa được kích hoạt bản quyền! Vui lòng kích hoạt Dùng Thử 24h hoặc nâng cấp gói để sử dụng tính năng này.", status

    features = status.get('features', {})
    if not features.get(feature_name, False):
        return False, f"⚠️ Tính năng này không thuộc phạm vi gói {status.get('plan_name', '')}. Vui lòng nâng cấp lên gói cao hơn để sử dụng!", status

    return True, "OK", status


def register_trial_in_cloud(license_info=None, timeout=6):
    """Đăng ký (hoặc cập nhật) máy dùng thử trên Google Sheet có kiểm tra lỗi."""
    cfg = load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('client_license_token', '').strip()
    if not gas_url or not token:
        return False, 'Chưa cấu hình máy chủ bản quyền'

    info = license_info or load_local_license_cache() or {}
    hwid = get_hardware_id()
    expire_str = str(info.get('expire_str') or '').strip()
    if not expire_str:
        expire_epoch = int(info.get('expire_epoch') or 0)
        if expire_epoch:
            expire_str = datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M')

    payload = {
        'action': 'register_trial',
        'token': token,
        # Gửi đủ HWID 12 ký tự. Apps Script sẽ nâng cấp dòng short-HWID cũ
        # thay vì tạo thêm một dòng trùng.
        'hwid': hwid,
        'user_name': str(info.get('user_name') or 'Khách Dùng Thử 24h'),
        'phone_zalo': str(info.get('phone_zalo') or ''),
        'expire_date': expire_str,
    }
    try:
        response = requests.post(gas_url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get('success'):
            return False, str(data.get('error') or data.get('message') or 'Máy chủ từ chối đăng ký dùng thử')
        return True, ''
    except (requests.RequestException, ValueError) as exc:
        return False, str(exc)


def schedule_trial_cloud_registration(license_info):
    """Gửi lại đăng ký dùng thử có giới hạn nhịp để không làm chậm giao diện."""
    global _last_trial_registration_attempt
    if not license_info or license_info.get('tier') != 'trial':
        return
    if int(license_info.get('expire_epoch') or 0) <= int(time.time()):
        return

    with _trial_registration_lock:
        now = time.monotonic()
        if now - _last_trial_registration_attempt < TRIAL_REGISTRATION_RETRY_SECONDS:
            return
        _last_trial_registration_attempt = now

    def _worker():
        success, error = register_trial_in_cloud(license_info)
        if not success:
            # Không log token/HWID/payload để tránh lộ dữ liệu nhạy cảm.
            print(f"Chưa đồng bộ được đăng ký dùng thử lên Google Sheet: {error}")

    threading.Thread(target=_worker, name='trial-sheet-sync', daemon=True).start()


def activate_trial_license(user_name="Khách Dùng Thử", phone_zalo=""):
    """Tự động kích hoạt gói Trial 24h cho máy mới."""
    current = get_current_license_status()
    if current.get('status') == 'ACTIVE':
        return False, "Máy tính của bạn đang có bản quyền hoạt động!"
    if not current.get('can_activate_trial', False):
        return False, "Máy tính này đã dùng hết lượt trải nghiệm 24h. Vui lòng nâng cấp gói để tiếp tục sử dụng."

    hwid = get_hardware_id()
    now = datetime.now()
    expire_dt = now + timedelta(hours=24)
    expire_epoch = int(expire_dt.timestamp())
    expire_str = expire_dt.strftime('%d/%m/%Y %H:%M')

    license_info = {
        "hwid": hwid,
        "tier": "trial",
        "plan_name": PACKAGE_TIERS["trial"]["plan_name"],
        "expire_epoch": expire_epoch,
        "expire_str": expire_str,
        "activated_at": int(now.timestamp()),
        "user_name": user_name,
        "phone_zalo": phone_zalo,
        "features": PACKAGE_TIERS["trial"]["features"]
    }

    save_local_license_cache(license_info)
    _set_machine_trial_anchor(expire_epoch)

    # Khi người dùng chủ động bấm kích hoạt, phản hồi phải phản ánh được việc
    # Sheet đã nhận dữ liệu hay chưa; lỗi mạng sẽ được thử lại ở nền.
    cloud_success, cloud_error = register_trial_in_cloud(license_info)
    if not cloud_success:
        schedule_trial_cloud_registration(license_info)
        return True, f"🎉 Đã kích hoạt Dùng Thử 24h trên máy. Hệ thống sẽ tự đồng bộ lên Sheet khi có mạng ({cloud_error})."

    return True, "🎉 Chúc mừng! Đã kích hoạt thành công 24h Dùng Thử trải nghiệm đầy đủ tính năng!"


def set_pro_selected_module(module):
    """
    Cập nhật lựa chọn Module chính cho Gói Pro ('editor' hoặc 'review').
    Chỉ cho phép chọn 1 LẦN DUY NHẤT khi kích hoạt. Không cho phép đổi lại qua API sau khi đã chọn.
    """
    if module not in ['editor', 'review']:
        return False, "Lựa chọn Module không hợp lệ. Vui lòng chọn 'editor' (Biên tập phim) hoặc 'review' (Review Phim)."

    cached = load_local_license_cache()
    if not cached:
        return False, "Chưa tìm thấy thông tin bản quyền trên máy!"

    tier = cached.get('tier')
    if tier != 'pro':
        return False, "Tính năng lựa chọn 1 trong 2 Module chỉ áp dụng cho Gói Pro. Gói của bạn có thể sử dụng đồng thời cả 2 module!"

    # Kiểm tra nếu đã chọn trước đó rồi thì khóa cứng không cho chọn lại
    existing_mod = cached.get('pro_selected_module')
    if existing_mod and existing_mod in ['editor', 'review']:
        mod_title = 'Biên tập phim' if existing_mod == 'editor' else 'Review Phim'
        return False, f"Bạn đã chọn cố định Module '{mod_title}' cho Gói Pro. Để sử dụng cả 2 Module, vui lòng nâng cấp lên Gói VIP!"

    cached['pro_selected_module'] = module
    save_local_license_cache(cached)
    mod_title = 'Biên tập phim' if module == 'editor' else 'Review Phim'
    return True, f"Đã thiết lập Module: {mod_title} thành công!"


def activate_test_tier(tier="vip", days=30):
    """
    (Chế độ Thử nghiệm / Test Mode)
    Kích hoạt trực tiếp gói cước (Trial, Pro, VIP, Yearly) không cần chờ thanh toán thật.
    Tự động lưu cache .license.dat và đẩy dòng cập nhật lên Google Sheet!
    """
    if os.environ.get("NOVACUT_ENABLE_DEV_ENDPOINTS") != "1":
        return False, "Chức năng kích hoạt thử nghiệm bị tắt trong bản phát hành."
    tier = tier.lower()
    if tier not in PACKAGE_TIERS:
        tier = "vip"
    
    if tier == "yearly":
        days = 365
    elif tier == "admin":
        days = 3650
    elif tier == "trial":
        days = 1

    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid)
    now = datetime.now()
    expire_dt = now + timedelta(days=days)
    expire_epoch = int(expire_dt.timestamp())
    expire_str = expire_dt.strftime('%d/%m/%Y %H:%M')
    plan_info = PACKAGE_TIERS[tier]

    license_info = {
        "hwid": hwid,
        "tier": tier,
        "plan_name": plan_info["plan_name"],
        "expire_epoch": expire_epoch,
        "expire_str": expire_str,
        "activated_at": int(now.timestamp()),
        "user_name": "Admin Test",
        "phone_zalo": "",
        "pro_selected_module": None if tier == 'pro' else None,
        "features": plan_info["features"]
    }
    save_local_license_cache(license_info)

    # Đẩy lên Google Sheet qua Webhook / register
    cfg = load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    if gas_url:
        try:
            requests.post(gas_url, json={
                "gateway": "TEST_GATEWAY",
                "transferAmount": cfg.get('prices', {}).get(tier, 500000),
                "content": f"AMS {short_hwid} {tier.upper()}",
                "id": f"TEST_{int(time.time())}"
            }, timeout=8)
        except Exception as e:
            print(f"Lỗi gửi test lên Google Sheet: {e}")

    return True, f"🎉 Đã kích hoạt thành công {plan_info['plan_name']} ({days} ngày)!"


def check_sepay_direct_api(tier="vip"):
    """
    Truy vấn trực tiếp SePay API (GET https://my.sepay.vn/userapi/transactions/list)
    để kiểm tra xem có giao dịch chuyển khoản thành công nào khớp với mã máy (HWID) không.
    Nếu tìm thấy:
      1. Tự động cộng ngày & kích hoạt bản quyền cục bộ (.license.dat)
      2. Tự động gửi dữ liệu giao dịch lên Google Sheet để đồng bộ
      3. Trả về True kèm thông tin bản quyền mới!
    """
    if os.environ.get("NOVACUT_ENABLE_DIRECT_SEPAY") != "1":
        return False, "Đối soát trực tiếp bị tắt; vui lòng xác thực qua máy chủ bản quyền."
    cfg = load_app_config()
    sepay_token = cfg.get('sepay_api_token', '').strip()
    bank_account = cfg.get('bank_account', '').strip()
    
    if not sepay_token:
        return False, "Chưa cấu hình SePay API Token trong license_config.json"
        
    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid).upper()
    
    try:
        url = "https://my.sepay.vn/userapi/transactions/list"
        params = {"limit": 20}
        if bank_account:
            params["account_number"] = bank_account
            
        headers = {
            "Authorization": f"Bearer {sepay_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            return False, f"Lỗi gọi SePay API (Mã {res.status_code}): {res.text[:200]}"
            
        data = res.json()
        transactions = data.get('transactions', [])
        if not transactions:
            return False, "Chưa tìm thấy giao dịch chuyển khoản nào mới từ SePay"
            
        matched_tx = None
        matched_tier = tier or 'vip'
        prices = cfg.get('prices', {})
        processed_tx_ids = _load_processed_tx_ids()
        
        now = datetime.now()
        now_epoch = int(now.timestamp())
        # Chỉ chấp nhận giao dịch trong vòng 10 phút trở lại đây hoặc sau thời điểm tạo mã QR
        min_valid_epoch = max(now_epoch - 600, _last_qr_generation_epoch - 30) if _last_qr_generation_epoch > 0 else (now_epoch - 600)
        
        # Tạo regex chuẩn: bắt buộc chứa từ khóa 'AMS' và đúng mã máy short_hwid
        # Ví dụ: "AMS 6C2FA9 VIP", "AMS6C2FA9", "MBVCB.123.AMS 6C2FA9 PRO", "AMS-6C2FA9"
        clean_short = short_hwid.replace('-', '').strip()
        hwid_pattern = re.compile(rf"(?:^|\b|[^A-Z0-9])AMS[\s_-]*{re.escape(clean_short)}(?:$|\b|[^A-Z0-9])", re.IGNORECASE)
        
        for tx in transactions:
            tx_id = str(tx.get('id') or tx.get('reference_number') or '')
            
            # 1. Chống kích hoạt lặp lại (Bỏ qua giao dịch đã từng xử lý)
            if not tx_id or tx_id in processed_tx_ids:
                continue
                
            # 2. Kiểm tra mốc thời gian giao dịch (Chống nhận nhầm giao dịch cũ trong quá khứ)
            tx_date_str = str(tx.get('transaction_date') or '').strip()
            if not tx_date_str:
                continue
            try:
                tx_dt = datetime.strptime(tx_date_str, '%Y-%m-%d %H:%M:%S')
                if int(tx_dt.timestamp()) < min_valid_epoch:
                    continue
            except (TypeError, ValueError):
                continue
                
            content = str(tx.get('transaction_content') or tx.get('content') or '').upper()
            amount_in = float(tx.get('amount_in') or tx.get('transferAmount') or 0)
            
            # 3. So khớp chặt chẽ Nội dung chuyển khoản (Content Validation Key)
            is_content_matched = bool(hwid_pattern.search(content)) or (f"AMS{clean_short}" in content.replace(' ', '').replace('-', ''))
            
            if is_content_matched:
                # 4. So khớp số tiền chuyển khoản (Amount Verification)
                requested_tier = str(tier or '').lower()
                content_tiers = [name for name in ('yearly', 'vip', 'pro') if name.upper() in content]
                matched_tier = content_tiers[0] if len(content_tiers) == 1 else requested_tier
                if matched_tier not in ('yearly', 'vip', 'pro'):
                    continue
                expected_amount = float(prices.get(matched_tier, 0) or 0)
                if expected_amount <= 0 or amount_in < expected_amount:
                    continue
                    
                matched_tx = tx
                break
                
        if not matched_tx:
            return False, f"Chưa tìm thấy giao dịch mới nào có nội dung chuyển khoản hợp lệ chứa 'AMS {short_hwid}'"
            
        days = 365 if matched_tier == 'yearly' else 30
        
        current_lic = load_local_license_cache()
        if current_lic and current_lic.get('expire_epoch') and current_lic.get('expire_epoch') > int(now.timestamp()):
            base_dt = datetime.fromtimestamp(current_lic['expire_epoch'])
            expire_dt = base_dt + timedelta(days=days)
        else:
            expire_dt = now + timedelta(days=days)
            
        expire_epoch = int(expire_dt.timestamp())
        expire_str = expire_dt.strftime('%d/%m/%Y %H:%M')
        plan_info = PACKAGE_TIERS.get(matched_tier, PACKAGE_TIERS['vip'])
        
        tx_id = str(matched_tx.get('id') or matched_tx.get('reference_number') or int(time.time()))
        amount_paid = float(matched_tx.get('amount_in') or cfg.get('prices', {}).get(matched_tier, 500000))
        
        new_license = {
            "hwid": hwid,
            "tier": matched_tier,
            "plan_name": plan_info["plan_name"],
            "expire_epoch": expire_epoch,
            "expire_str": expire_str,
            "activated_at": int(now.timestamp()),
            "user_name": matched_tx.get('sender_account_name') or "Khách Hàng SePay",
            "phone_zalo": "",
            "pro_selected_module": current_lic.get('pro_selected_module') if current_lic else None,
            "features": plan_info["features"],
            "transaction_id": tx_id,
            "amount_paid": amount_paid
        }
        save_local_license_cache(new_license)
        _save_processed_tx_id(tx_id)
        
        # Gửi dữ liệu đồng bộ lên Google Sheet
        gas_url = cfg.get('google_apps_script_url', '').strip()
        if gas_url:
            try:
                requests.post(gas_url, json={
                    "gateway": "SEPAY_DIRECT_API",
                    "transferAmount": amount_paid,
                    "content": f"AMS {short_hwid} {matched_tier.upper()}",
                    "id": tx_id,
                    "hwid": hwid,
                    "tier": matched_tier,
                    "expire_date": expire_str
                }, timeout=8)
            except Exception as e:
                print(f"Lỗi gửi đồng bộ lên Google Sheet: {e}")
                
        plan_title = plan_info['plan_name'] if plan_info['plan_name'].startswith('Gói') else f"Gói {plan_info['plan_name']}"
        return True, f"🎉 Xác nhận thanh toán thành công! {plan_title} đã được kích hoạt ({days} ngày)."
        
    except Exception as e:
        return False, f"Lỗi kiểm tra SePay API: {str(e)}"


_cached_bank_details = None
_cached_bank_details_key = None

def resolve_bank_details(cfg=None):
    """
    Tự động lấy thông tin Ngân hàng (Bank Code, Số tài khoản, Tên chủ tài khoản)
    trực tiếp từ SePay API nếu trong cấu hình để trống!
    """
    if cfg is None:
        cfg = load_app_config()

    bank_code = cfg.get('bank_code', '').strip()
    bank_account = cfg.get('bank_account', '').strip()
    bank_name = cfg.get('bank_account_name', '').strip()
    sepay_token = cfg.get('sepay_api_token', '').strip()
    cache_key = (bank_code, bank_account, bank_name, sepay_token)

    global _cached_bank_details, _cached_bank_details_key
    if _cached_bank_details and _cached_bank_details_key == cache_key:
        return _cached_bank_details
    
    # Nếu chưa có bank_code hoặc bank_account mà có SePay token -> Tự động truy vấn SePay API
    if (not bank_code or not bank_account) and sepay_token:
        try:
            url = "https://my.sepay.vn/userapi/transactions/list"
            headers = {
                "Authorization": f"Bearer {sepay_token}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = requests.get(url, params={"limit": 5}, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                txs = data.get('transactions', [])
                if txs:
                    latest = txs[0]
                    detected_bank = latest.get('bank_brand_name', '')
                    detected_acc = latest.get('account_number', '')
                    
                    if not bank_code and detected_bank:
                        bank_code = detected_bank
                    if not bank_account and detected_acc:
                        bank_account = detected_acc
        except Exception as e:
            print(f"Lỗi tự động lấy tài khoản từ SePay: {e}")
            
    _cached_bank_details = {
        'bank_code': bank_code,
        'bank_account': bank_account,
        'bank_account_name': bank_name
    }
    _cached_bank_details_key = cache_key
    return _cached_bank_details


def generate_vietqr_url(tier="vip", amount=None):
    """
    Tạo link mã QR VietQR động (chuẩn Napas 247) tích hợp SePay.
    Tự động lấy ngân hàng từ SePay API nếu để trống!
    Cú pháp nội dung: AMS <HWID_12_KÝ_TỰ> <TIER_CODE>
    """
    cfg = load_app_config()
    bank_info = resolve_bank_details(cfg)
    bank_code = bank_info.get('bank_code', '').strip()
    bank_account = bank_info.get('bank_account', '').strip()
    bank_name = bank_info.get('bank_account_name', '').strip()
    if not bank_code or not bank_account or not bank_name:
        raise RuntimeError('Chưa cấu hình đầy đủ NOVACUT_BANK_CODE, NOVACUT_BANK_ACCOUNT và NOVACUT_BANK_ACCOUNT_NAME')
    if not re.fullmatch(r'[A-Za-z0-9]{3,20}', bank_code):
        raise RuntimeError('Mã ngân hàng không hợp lệ')
    if not re.fullmatch(r'\d{6,24}', bank_account):
        raise RuntimeError('Số tài khoản nhận tiền không hợp lệ')
    
    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid)
    payment_hwid = hwid.replace('AMS-', '').replace('-', '').upper()

    global _last_qr_generation_epoch
    _last_qr_generation_epoch = int(time.time())

    if tier not in ('pro', 'vip', 'yearly'):
        raise ValueError('Gói thanh toán không hợp lệ')
    configured_amount = int(cfg.get('prices', {}).get(tier, 0) or 0)
    if configured_amount <= 0:
        raise RuntimeError(f'Chưa cấu hình giá hợp lệ cho gói {tier}')
    amount = configured_amount
    # Dùng đủ 12 ký tự HWID để webhook không thể gia hạn nhầm khi hai máy có
    # cùng 6 ký tự đầu. VietQR tự điền nội dung này nên khách không phải gõ tay.
    transfer_content = quote(f"AMS {payment_hwid} {tier.upper()}", safe='')
    raw_content = f"AMS {payment_hwid} {tier.upper()}"

    # Link VietQR QuickLink (hỗ trợ hiển thị trực tiếp ảnh QR sắc nét)
    qr_image_url = f"https://img.vietqr.io/image/{bank_code}-{bank_account}-compact2.png?amount={amount}&addInfo={transfer_content}&accountName={quote(bank_name, safe='')}"

    return {
        "qr_image_url": qr_image_url,
        "bank_code": bank_code,
        "bank_account": bank_account,
        "bank_account_name": bank_name,
        "amount": amount,
        "amount_formatted": f"{amount:,.0f}đ",
        "transfer_content": raw_content,
        "tier": tier,
        "hwid": hwid,
        "short_hwid": short_hwid
    }


def activate_license_with_key(key_str):
    """
    Kích hoạt bản quyền bằng License Key thủ công.
    Hỗ trợ Key Offline dạng HMAC (ví dụ đại lý cấp): AMS-KEY-<TIER>-<DAYS>-<SIG>
    """
    key_str = (key_str or '').strip().upper()
    if not key_str:
        return False, "Vui lòng nhập mã kích hoạt!"

    # Key phải được xác thực bởi máy chủ. Cơ chế offline HMAC cũ đã bị loại bỏ
    # vì secret nằm trong client cho phép người dùng tự tạo license.
    cfg = load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('client_license_token', '')
    if gas_url:
        try:
            hwid = get_hardware_id()
            res = requests.post(gas_url, json={
                "action": "activate_key",
                "token": token,
                "hwid": hwid,
                "key": key_str
            }, timeout=8)
            data = res.json()
            if data.get('success'):
                sync_with_cloud()
                return True, data.get('message', 'Kích hoạt bản quyền thành công!')
            else:
                return False, data.get('error', 'Mã kích hoạt không hợp lệ hoặc đã được sử dụng!')
        except Exception as e:
            return False, f"Không thể kết nối máy chủ xác thực: {e}"

    return False, "Mã kích hoạt không hợp lệ!"


def generate_offline_master_key(short_hwid, tier="vip", days=30):
    """Cơ chế key offline cũ không còn an toàn và đã bị vô hiệu hóa."""
    raise RuntimeError("Offline master key generation has been disabled; use the license server.")


def _record_cloud_sync_attempt():
    """Ghi nhận cả các lần đồng bộ chủ động để lượt đọc cache kế tiếp không tạo worker thừa."""
    global _last_cloud_sync_attempt
    with _cloud_sync_lock:
        _last_cloud_sync_attempt = time.monotonic()


def _parse_cloud_expire_epoch(expire_epoch_value, expire_str, fallback_epoch=0):
    """Chuẩn hóa hạn dùng cloud, hỗ trợ cả epoch lẫn định dạng ngày cũ của Sheet."""
    try:
        expire_epoch = int(expire_epoch_value or 0)
        if expire_epoch > 0:
            return expire_epoch
    except (TypeError, ValueError):
        pass

    for date_format in ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
        try:
            return int(datetime.strptime(str(expire_str), date_format).timestamp())
        except (TypeError, ValueError):
            continue
    return int(fallback_epoch or 0)


def _do_sync_with_cloud():
    _record_cloud_sync_attempt()
    cfg = load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('client_license_token', '')
    if not gas_url or not token:
        return None

    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid)
    nonce = uuid.uuid4().hex[:12]
    client_time = int(time.time())

    # Kiểm tra bản ghi HWID đầy đủ trước; short-HWID chỉ để tương thích các
    # dòng đã được tạo bởi phiên bản cũ.
    hwid_candidates = [hwid, f"AMS-{short_hwid}", short_hwid]

    for cand_hwid in hwid_candidates:
        try:
            res = requests.get(gas_url, params={
                "action": "check_license",
                "hwid": cand_hwid,
                "token": token,
                "nonce": nonce,
                "client_time": client_time
            }, timeout=8)
            if res.status_code == 200:
                data = res.json()

                # 1. Anti-Replay Check: Khớp mã Nonce 1 lần
                if not data.get('nonce') or data.get('nonce') != nonce:
                    print("⚠️ Gói tin phản hồi không khớp Nonce (Phát hiện Replay Attack)!")
                    continue

                # 2. Anti-MITM Check: Xác thực chữ ký HMAC-SHA256
                if not verify_cloud_signature(data, token):
                    print("⚠️ Gói tin bản quyền thiếu hoặc sai chữ ký HMAC!")
                    continue

                cloud_status = str(data.get('status') or '').upper()
                if cloud_status == 'NOT_FOUND':
                    continue

                local_cached = load_local_license_cache()
                is_cloud_invalid = data.get('valid') is False
                if cloud_status == 'BLOCKED' or cloud_status == 'EXPIRED' or is_cloud_invalid:
                    expire_str = str(data.get('expire_date') or '')
                    existing_tier = (local_cached or {}).get('tier', 'unlicensed')
                    tier = str(data.get('tier') or existing_tier or 'unlicensed').lower()
                    server_time = int(data.get('server_time') or time.time())

                    if cloud_status == 'BLOCKED':
                        tier_info = PACKAGE_TIERS['unlicensed']
                        license_info = {
                            "hwid": hwid,
                            "status": "BLOCKED",
                            "tier": "unlicensed",
                            "plan_name": "Bản quyền đã bị khóa",
                            "expire_epoch": 0,
                            "expire_str": expire_str,
                            "activated_at": int(time.time()),
                            "last_seen_epoch": server_time,
                            "user_name": data.get('user_name', (local_cached or {}).get('user_name', '')),
                            "phone_zalo": data.get('phone_zalo', (local_cached or {}).get('phone_zalo', '')),
                            "pro_selected_module": None,
                            "vip_api_keys": {},
                            "features": tier_info["features"]
                        }
                    else:
                        expire_epoch = _parse_cloud_expire_epoch(
                            data.get('expire_epoch'), expire_str, int(time.time()) - 1
                        )
                        if not expire_str and expire_epoch:
                            expire_str = datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M')
                        tier_info = PACKAGE_TIERS.get(tier, PACKAGE_TIERS['unlicensed'])
                        license_info = {
                            "hwid": hwid,
                            "status": "EXPIRED",
                            "tier": tier,
                            "plan_name": tier_info["plan_name"],
                            "expire_epoch": expire_epoch,
                            "expire_str": expire_str,
                            "activated_at": int(time.time()),
                            "last_seen_epoch": server_time,
                            "user_name": data.get('user_name', (local_cached or {}).get('user_name', '')),
                            "phone_zalo": data.get('phone_zalo', (local_cached or {}).get('phone_zalo', '')),
                            "pro_selected_module": (local_cached or {}).get('pro_selected_module'),
                            "vip_api_keys": {},
                            "features": PACKAGE_TIERS['unlicensed']["features"]
                        }

                    save_local_license_cache(license_info)
                    return license_info

                if data.get('tier') or data.get('expire_date'):
                    tier = str(data.get('tier', 'pro')).lower()
                    expire_str = str(data.get('expire_date') or '')
                    expire_epoch = _parse_cloud_expire_epoch(
                        data.get('expire_epoch'), expire_str, int(time.time() + 86400 * 30)
                    )
                    if not expire_str and expire_epoch:
                        expire_str = datetime.fromtimestamp(expire_epoch).strftime('%d/%m/%Y %H:%M')

                    tier_info = PACKAGE_TIERS.get(tier, PACKAGE_TIERS["pro"])
                    server_time = int(data.get('server_time') or time.time())
                    pro_mod = data.get('pro_selected_module') or (local_cached.get('pro_selected_module') if local_cached else None)
                    vip_keys = local_cached.get('vip_api_keys', {}) if local_cached else {}

                    # Tự động nạp API Keys cho Gói VIP / Gói Năm / Gói Admin
                    if vip_keys and isinstance(vip_keys, dict) and (tier in ['vip', 'yearly', 'admin']):
                        try:
                            from routes.state import API_KEYS_FILE
                            existing_keys = {}
                            if os.path.exists(API_KEYS_FILE):
                                with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
                                    for line in f:
                                        if '=' in line:
                                            k, v = line.strip().split('=', 1)
                                            existing_keys[k] = v
                            for k, v in vip_keys.items():
                                if v:
                                    existing_keys[k] = v
                            with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
                                for k, v in existing_keys.items():
                                    f.write(f"{k}={v}\n")
                        except Exception as e_k:
                            print(f"Lỗi lưu VIP API Keys: {e_k}")

                    license_info = {
                        "hwid": hwid,
                        "status": "ACTIVE",
                        "tier": tier,
                        "plan_name": tier_info["plan_name"],
                        "expire_epoch": expire_epoch,
                        "expire_str": expire_str,
                        "activated_at": int(time.time()),
                        "last_seen_epoch": server_time,
                        "user_name": data.get('user_name', ''),
                        "phone_zalo": data.get('phone_zalo', ''),
                        "pro_selected_module": pro_mod,
                        "vip_api_keys": vip_keys,
                        "features": tier_info["features"]
                    }
                    save_local_license_cache(license_info)
                    return license_info
        except Exception as e:
            print(f"Lỗi đồng bộ Google Sheets: {e}")

    # Nếu cloud không có dòng nhưng máy còn Trial hợp lệ, đăng ký lại ngay khi
    # người dùng bấm "Đồng bộ". Nhờ vậy lỗi mạng ở lần mở máy đầu không còn
    # khiến máy khách bị mất khỏi Google Sheet mãi mãi.
    local_cached = load_local_license_cache()
    if (
        local_cached
        and local_cached.get('tier') == 'trial'
        and int(local_cached.get('expire_epoch') or 0) > int(time.time())
    ):
        success, error = register_trial_in_cloud(local_cached)
        if success:
            return local_cached
        print(f"Chưa thể đăng ký lại Trial lên Google Sheet: {error}")
    return None


def sync_with_cloud(force=False):
    """
    Đồng bộ trạng thái bản quyền với Google Sheets Apps Script (Thread-safe & Debounced).
    Tự động cập nhật cache nếu khách hàng vừa thanh toán SePay thành công.
    Hỗ trợ đối soát cả HWID đầy đủ (AMS-XXXX-XXXX-XXXX) và Short HWID (AMS-XXXXXX / XXXXXX).
    """
    global _last_sync_result, _last_sync_result_time
    with _sync_execution_lock:
        now_mono = time.monotonic()
        if not force and _last_sync_result is not None and (now_mono - _last_sync_result_time) < SYNC_CACHE_DEBOUNCE_SECONDS:
            return _last_sync_result

        result = _do_sync_with_cloud()
        _last_sync_result = result
        _last_sync_result_time = time.monotonic()
        return result


def sync_user_keys_to_cloud(keys_dict):
    """
    Đẩy 1 CHIỀU (WRITE-ONLY) các cấu hình API Key (OpenAI, OpenSpeaker) lên Google Sheet.
    Chạy trong background thread, tuyệt đối không lộ API Key ra ngoài response.
    """
    cfg = load_app_config()
    gas_url = cfg.get('google_apps_script_url', '').strip()
    token = cfg.get('client_license_token', '')
    if not gas_url or not token or os.environ.get('NOVACUT_SYNC_KEYS_TO_CLOUD') != '1':
        return False

    hwid = get_hardware_id()
    short_hwid = get_short_hwid(hwid)
    payload = {
        "action": "sync_keys",
        "token": token,
        "hwid": hwid,
        "short_hwid": short_hwid,
        "openai_key": keys_dict.get('openaiKey', ''),
        "openai_base_url": keys_dict.get('openaiBaseUrl', 'https://api.openai.com/v1'),
        "openai_model": keys_dict.get('openaiModel', 'gpt-5.6-luna'),
        "openspeaker_key": keys_dict.get('openSpeakerApiKey', '')
    }

    try:
        res = requests.post(gas_url, json=payload, timeout=10)
        if res.status_code == 200:
            res_data = res.json()
            if not res_data.get('success', False) and res_data.get('error'):
                print(f"⚠️ Phản hồi từ Google Apps Script khi lưu Keys: {res_data.get('error')}")
                return False
            return True
        else:
            print(f"⚠️ Lỗi kết nối Google Apps Script (HTTP {res.status_code}): {res.text}")
            return False
    except Exception as e:
        print(f"Lỗi đẩy keys 1 chiều lên Google Sheet: {e}")
        return False
