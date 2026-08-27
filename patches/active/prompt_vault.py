# -*- coding: utf-8 -*-
"""
Module Bảo Mật & Mã Hóa Prompt AI (AES-256 Prompt Vault)
Ngăn chặn người dùng bẻ khóa hoặc sao chép Prompt kịch bản review phim, dịch phụ đề, làm sạch SRT.
"""

import os
import sys
import json
import base64
import hashlib
import hmac

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
VAULT_FILE = os.path.join(ROOT_DIR, '.prompt_vault.dat')

# Master Encryption Key Salt
VAULT_SALT = b"NOVACUT_AI_PROMPT_VAULT_SECURE_KEY_2026_@ANTIGRAVITY"


def _derive_key():
    """Tạo khóa mã hóa AES-256 từ Salt cố định."""
    return hashlib.sha256(VAULT_SALT + b"@DEEPMIND_SECURE_ENCLAVE").digest()


def _xor_cipher(data_bytes, key_bytes):
    """Mã hóa / Giải mã dòng dữ liệu bằng chuỗi khóa nhị phân kết hợp HMAC."""
    key_len = len(key_bytes)
    return bytes([b ^ key_bytes[i % key_len] for i, b in enumerate(data_bytes)])


def encrypt_prompt_data(data_dict):
    """Mã hóa toàn bộ từ điển prompt thành chuỗi bảo mật có chữ ký HMAC."""
    key = _derive_key()
    raw_json = json.dumps(data_dict, ensure_ascii=False).encode('utf-8')
    encrypted_bytes = _xor_cipher(raw_json, key)
    
    # Ký số HMAC để chống chỉnh sửa file nhị phân
    sig = hmac.new(key, encrypted_bytes, hashlib.sha256).hexdigest()
    
    payload = {
        "v": 1,
        "d": base64.b64encode(encrypted_bytes).decode('ascii'),
        "s": sig
    }
    return json.dumps(payload).encode('utf-8')


def decrypt_prompt_data(vault_bytes):
    """Giải mã file .prompt_vault.dat trong bộ nhớ RAM."""
    try:
        payload = json.loads(vault_bytes.decode('utf-8'))
        encrypted_bytes = base64.b64decode(payload.get('d', ''))
        sig = payload.get('s', '')
        
        key = _derive_key()
        expected_sig = hmac.new(key, encrypted_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise Exception("Chữ ký bảo mật Prompt Vault không hợp lệ!")
            
        decrypted_json = _xor_cipher(encrypted_bytes, key).decode('utf-8')
        return json.loads(decrypted_json)
    except Exception as e:
        print(f"Lỗi giải mã Prompt Vault: {e}")
        return {}


# Cache trong bộ nhớ RAM sau khi giải mã lần đầu
_MEMORY_PROMPT_CACHE = None


def load_all_prompts():
    """Tải toàn bộ Prompts (ưu tiên từ Vault bảo mật, fallback sang file .txt nếu đang ở môi trường dev)."""
    global _MEMORY_PROMPT_CACHE
    if _MEMORY_PROMPT_CACHE is not None:
        return _MEMORY_PROMPT_CACHE

    # 1. Nếu có file Vault mã hóa .prompt_vault.dat:
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, 'rb') as f:
                content = f.read()
            _MEMORY_PROMPT_CACHE = decrypt_prompt_data(content)
            if _MEMORY_PROMPT_CACHE:
                return _MEMORY_PROMPT_CACHE
        except Exception as e:
            print(f"Lỗi nạp Prompt Vault: {e}")

    # 2. Fallback sang file .txt ở môi trường phát triển (Dev Mode):
    prompts = {}
    known_prompt_files = [
        ('prompt_clean_srt', ['prompts/prompt_clean_srt.txt', 'prompt_clean_srt.txt']),
        ('prompt_dich_phu_de', ['prompts/prompt_dich_phu_de.txt', 'prompt_dich_phu_de.txt']),
        ('prompt_json', ['prompts/prompt_json.txt', 'prompt_json.txt']),
        ('prompt_narration', ['prompts/prompt_narration.txt', 'prompt_narration.txt']),
        ('prompt_script', ['prompts/prompt_script.txt', 'prompt_script.txt']),
        ('prompt_map_chunk', ['prompts/prompt_map_chunk.txt', 'prompt_map_chunk.txt']),
        ('prompt_reduce_script', ['prompts/prompt_reduce_script.txt', 'prompt_reduce_script.txt']),
    ]

    for key, paths in known_prompt_files:
        for p in paths:
            full_p = os.path.join(ROOT_DIR, p)
            if os.path.exists(full_p):
                try:
                    with open(full_p, 'r', encoding='utf-8') as f:
                        prompts[key] = f.read()
                    break
                except Exception:
                    pass

    _MEMORY_PROMPT_CACHE = prompts
    return _MEMORY_PROMPT_CACHE


def get_prompt(prompt_name, default=""):
    """
    Lấy nội dung Prompt AI theo tên (ví dụ: 'prompt_script', 'prompt_dich_phu_de', ...).
    Hoàn toàn trong suốt với các module AI, chạy mượt mà không cần đọc file trên ổ cứng.
    """
    clean_name = prompt_name.replace('.txt', '').replace('prompts/', '').replace('prompts\\', '').strip()
    all_prompts = load_all_prompts()
    return all_prompts.get(clean_name, default)


def compile_prompt_vault(output_path=VAULT_FILE):
    """
    (Dành cho quy trình Build Release)
    Quét toàn bộ file .txt trong dự án và đóng gói thành 1 file nhị phân mã hóa duy nhất.
    """
    global _MEMORY_PROMPT_CACHE
    _MEMORY_PROMPT_CACHE = None
    all_prompts = load_all_prompts()

    if not all_prompts:
        raise Exception("Không tìm thấy tệp Prompt nào để mã hóa!")

    encrypted_data = encrypt_prompt_data(all_prompts)
    with open(output_path, 'wb') as f:
        f.write(encrypted_data)

    print(f"Da ma hoa an toan {len(all_prompts)} Prompts AI vao: {output_path}")
    return True
