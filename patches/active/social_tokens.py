# -*- coding: utf-8 -*-
"""Protected Token Vault and OAuth PKCE primitives for Social Media Publishing.

Tokens are encrypted using a locally generated master key stored in the user data
directory and are never persisted in plaintext, job history, or application logs.
"""
import os
import json
import base64
import hashlib
import secrets
import time
import urllib.request
import urllib.parse
from cryptography.fernet import Fernet

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(ROOT_DIR, "user_data")
VAULT_KEY_FILE = os.path.join(USER_DATA_DIR, ".vault_key")
TOKENS_FILE = os.path.join(USER_DATA_DIR, "social_tokens.enc")

# Active in-memory OAuth state registry: {state: (platform_id, created_at, code_verifier)}
_OAUTH_STATES = {}


def _get_or_create_vault_key():
    """Retrieve or generate the local Fernet key for token encryption."""
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    if os.path.isfile(VAULT_KEY_FILE):
        try:
            with open(VAULT_KEY_FILE, "rb") as fh:
                key = fh.read().strip()
                if key:
                    return key
        except OSError:
            pass
    key = Fernet.generate_key()
    try:
        with open(VAULT_KEY_FILE, "wb") as fh:
            fh.write(key)
    except OSError:
        pass
    return key


def _get_fernet():
    key = _get_or_create_vault_key()
    return Fernet(key)


def _load_all_tokens():
    """Load and decrypt all tokens from the encrypted store."""
    if not os.path.isfile(TOKENS_FILE):
        return {}
    try:
        fernet = _get_fernet()
        with open(TOKENS_FILE, "rb") as fh:
            encrypted_data = fh.read()
        if not encrypted_data:
            return {}
        decrypted_bytes = fernet.decrypt(encrypted_data)
        data = json.loads(decrypted_bytes.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_all_tokens(tokens_dict):
    """Encrypt and persist the token dictionary."""
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    fernet = _get_fernet()
    raw_bytes = json.dumps(tokens_dict, ensure_ascii=False).encode("utf-8")
    encrypted_bytes = fernet.encrypt(raw_bytes)
    tmp_path = TOKENS_FILE + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(encrypted_bytes)
    os.replace(tmp_path, TOKENS_FILE)


def save_token(connection_id, token_data):
    """Save or update an encrypted token for a specific connection ID."""
    if not connection_id or not isinstance(token_data, dict):
        raise ValueError("Thiếu mã kết nối hoặc dữ liệu token không hợp lệ")
    tokens = _load_all_tokens()
    tokens[str(connection_id)] = {
        **token_data,
        "updated_at": time.time(),
    }
    _save_all_tokens(tokens)
    return True


def get_token(connection_id):
    """Retrieve and decrypt token data for a connection ID."""
    if not connection_id:
        return None
    tokens = _load_all_tokens()
    return tokens.get(str(connection_id))


def delete_token(connection_id):
    """Remove a token from the encrypted store."""
    if not connection_id:
        return False
    tokens = _load_all_tokens()
    if str(connection_id) in tokens:
        del tokens[str(connection_id)]
        _save_all_tokens(tokens)
        return True
    return False


# --- OAuth PKCE Primitives ---

def generate_pkce_pair():
    """Generate a high-entropy PKCE code_verifier and SHA256 code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def create_oauth_state(platform_id, code_verifier=None):
    """Generate a CSRF-protected state parameter linked to platform & PKCE verifier."""
    state = secrets.token_urlsafe(32)
    _cleanup_expired_states()
    _OAUTH_STATES[state] = {
        "platform_id": platform_id,
        "created_at": time.time(),
        "code_verifier": code_verifier,
    }
    return state


def verify_oauth_state(state, max_age_seconds=600):
    """Validate and consume an OAuth state parameter. Returns state data or None."""
    _cleanup_expired_states(max_age_seconds)
    data = _OAUTH_STATES.pop(state, None)
    if not data:
        return None
    if time.time() - data.get("created_at", 0) > max_age_seconds:
        return None
    return data


def _cleanup_expired_states(max_age_seconds=600):
    now = time.time()
    expired = [k for k, v in _OAUTH_STATES.items() if now - v.get("created_at", 0) > max_age_seconds]
    for k in expired:
        _OAUTH_STATES.pop(k, None)


# --- Token Refresh & Identity Verification ---

def refresh_token_if_needed(connection_id, client_id=None, client_secret=None):
    """Check if token is expired or close to expiry (< 300s); refresh if refresh_token exists."""
    token = get_token(connection_id)
    if not token:
        return None
    expires_at = token.get("expires_at", 0)
    now = time.time()
    # If valid for at least another 5 minutes, return existing access_token
    if expires_at and (expires_at - now > 300):
        return token.get("access_token")

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        if expires_at and expires_at > now:
            return token.get("access_token")
        return None

    platform_id = token.get("platform_id")
    if platform_id == "youtube":
        return _refresh_google_token(connection_id, token, client_id, client_secret)
    return token.get("access_token")


def _refresh_google_token(connection_id, token, client_id=None, client_secret=None):
    cid = client_id or os.environ.get("NOVACUT_YOUTUBE_CLIENT_ID")
    csecret = client_secret or os.environ.get("NOVACUT_YOUTUBE_CLIENT_SECRET")
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        return None

    payload = {
        "client_id": cid or "",
        "client_secret": csecret or "",
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    payload = {k: v for k, v in payload.items() if v}
    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        new_access_token = data.get("access_token")
        if new_access_token:
            token["access_token"] = new_access_token
            expires_in = data.get("expires_in", 3600)
            token["expires_at"] = time.time() + expires_in
            save_token(connection_id, token)
            return new_access_token
    except Exception:
        pass
    return None
