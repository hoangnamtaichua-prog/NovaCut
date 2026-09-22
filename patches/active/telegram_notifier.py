"""
Telegram Notification Service for NovaCut
Chức năng gửi thông báo tiến độ biên tập video hàng loạt qua Telegram Bot:
1. Thông báo sau từng video (thành công hoặc thất bại).
2. Thông báo tổng kết khi hoàn tất toàn bộ batch hoặc khi bị hủy.
3. Bảo mật tuyệt đối: Không lưu bot token vào mã nguồn, tự động khử token khỏi log/traceback, masking token trên UI.
4. Chống lỗi & tách biệt hoàn toàn: Sự cố mạng Telegram không ảnh hưởng đến pipeline biên tập video.
5. Deduplication, timeout (10s), retry giới hạn và hỗ trợ Unicode tiếng Việt an toàn.
"""

import os
import sys
import json
import time
import re
import html
import logging
import threading
import requests
from typing import Dict, Any, Optional, Tuple
from platformdirs import user_data_dir

logger = logging.getLogger("telegram_notifier")
logger.setLevel(logging.INFO)

# Token regex pattern to detect and sanitize any bot token in logs or error messages
TOKEN_PATTERN = re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{35}\b")
TELEGRAM_API_URL_PATTERN = re.compile(r"https://api\.telegram\.org/bot[^/]+/")


def get_user_data_path() -> str:
    """Lấy đường dẫn thư mục lưu trữ cấu hình an toàn cho người dùng."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            target = os.path.join(appdata, "NovaCut")
            try:
                os.makedirs(target, exist_ok=True)
                return target
            except Exception:
                pass
    try:
        p = user_data_dir("NovaCut", "NovaCut", roaming=True)
        os.makedirs(p, exist_ok=True)
        return p
    except Exception:
        pass
    fallback = os.path.dirname(os.path.abspath(__file__))
    return fallback


DATA_DIR = get_user_data_path()
CONFIG_FILE = os.path.join(DATA_DIR, "telegram_config.json")
FALLBACK_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data", "telegram_config.json")


def scrub_sensitive_text(text: str, custom_token: str = "") -> str:
    """Loại bỏ hoàn toàn Bot Token khỏi mọi chuỗi văn bản, URL hoặc traceback lỗi."""
    if not text:
        return ""
    result = str(text)
    if custom_token and len(custom_token) >= 8:
        result = result.replace(custom_token, "[REDACTED_BOT_TOKEN]")
    result = TOKEN_PATTERN.sub("[REDACTED_BOT_TOKEN]", result)
    result = TELEGRAM_API_URL_PATTERN.sub("https://api.telegram.org/bot[REDACTED]/", result)
    return result


def mask_token(token: str) -> str:
    """Tạo chuỗi token che giấu (mask) để hiển thị trên giao diện an toàn."""
    if not token:
        return ""
    token = token.strip()
    if len(token) <= 8:
        return "••••••••"
    prefix = token[:4]
    suffix = token[-4:]
    return f"{prefix}••••••••••••••••••••••••{suffix}"


import secrets

def mask_chat_id(chat_id: str) -> str:
    """Tạo chuỗi Chat ID che giấu (mask) để hiển thị trên giao diện an toàn (VD: 5011****99 hoặc -1001****90)."""
    if not chat_id:
        return ""
    cid_str = str(chat_id).strip()
    is_neg = cid_str.startswith("-")
    raw = cid_str[1:] if is_neg else cid_str
    prefix_len = 5 if is_neg else 4
    if len(cid_str) <= prefix_len + 2:
        return "****"
    prefix = cid_str[:prefix_len]
    suffix = cid_str[-2:]
    return f"{prefix}****{suffix}"


def format_duration(seconds: float) -> str:
    """Định dạng số giây thành chuỗi thời gian dễ đọc (VD: 1 phút 25 giây hoặc 45 giây)."""
    if seconds is None or seconds < 0:
        return "0s"
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec}s"
    minutes = sec // 60
    remaining_sec = sec % 60
    if minutes < 60:
        return f"{minutes}p {remaining_sec}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min}p {remaining_sec}s"


class TelegramNotifier:
    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TelegramNotifier":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.enabled = False
        self.bot_token = ""
        self.chat_id = "5011367599"
        self.notify_per_video = True
        self.notify_batch_done = True
        self.users: Dict[str, dict] = {}

        # Quản lý phiên kết nối tự động lấy Chat ID
        self._pending_sessions: Dict[str, dict] = {}
        self._session_lock = threading.Lock()
        self._bot_info_cache: Dict[str, Any] = {}

        # Cache chống gửi trùng (Deduplication)
        self._sent_keys: Dict[str, float] = {}
        self._cache_lock = threading.Lock()

        self._load_config()

    def _load_config(self):
        """Nạp cấu hình từ file bảo mật hoặc biến môi trường."""
        with self._lock:
            loaded = False
            for path in [CONFIG_FILE, FALLBACK_CONFIG_FILE]:
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            self.enabled = bool(data.get("enabled", False))
                            self.bot_token = str(data.get("bot_token", "")).strip()
                            self.chat_id = str(data.get("chat_id", "5011367599")).strip() or "5011367599"
                            self.notify_per_video = bool(data.get("notify_per_video", True))
                            self.notify_batch_done = bool(data.get("notify_batch_done", True))
                            raw_users = data.get("users", {})
                            if isinstance(raw_users, dict):
                                self.users = raw_users
                            loaded = True
                            break
                    except Exception as e:
                        logger.warning(f"Lỗi đọc file cấu hình Telegram {path}: {scrub_sensitive_text(str(e))}")

            # Đọc từ biến môi trường (ưu tiên nếu có đặt)
            env_token = os.environ.get("NOVACUT_TELEGRAM_BOT_TOKEN", "").strip()
            if env_token:
                self.bot_token = env_token

            env_chat_id = os.environ.get("NOVACUT_TELEGRAM_CHAT_ID", "").strip()
            if env_chat_id:
                self.chat_id = env_chat_id

            env_enabled = os.environ.get("NOVACUT_TELEGRAM_ENABLED", "").strip().lower()
            if env_enabled in ("true", "1", "yes"):
                self.enabled = True
            elif env_enabled in ("false", "0", "no"):
                self.enabled = False

    def save_config(
        self,
        enabled: Optional[bool] = None,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        notify_per_video: Optional[bool] = None,
        notify_batch_done: Optional[bool] = None,
    ) -> bool:
        """Lưu cấu hình Telegram an toàn vào file cục bộ."""
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)

            # Chỉ ghi đè token nếu người dùng nhập token mới thực sự
            if bot_token is not None:
                clean_token = str(bot_token).strip()
                if clean_token in ("CLEAR", "__CLEAR__"):
                    self.bot_token = ""
                # Không ghi đè nếu là chuỗi mask hiển thị dạng •••• hoặc rỗng
                elif clean_token and "•" not in clean_token and not clean_token.startswith("****"):
                    self.bot_token = clean_token

            if chat_id is not None:
                clean_chat = str(chat_id).strip()
                if clean_chat:
                    self.chat_id = clean_chat

            if notify_per_video is not None:
                self.notify_per_video = bool(notify_per_video)

            if notify_batch_done is not None:
                self.notify_batch_done = bool(notify_batch_done)

            data = {
                "enabled": self.enabled,
                "bot_token": self.bot_token,
                "chat_id": self.chat_id,
                "notify_per_video": self.notify_per_video,
                "notify_batch_done": self.notify_batch_done,
                "users": self.users,
                "updated_at": time.time(),
            }

            try:
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                tmp_file = CONFIG_FILE + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if os.path.exists(CONFIG_FILE):
                    os.replace(tmp_file, CONFIG_FILE)
                else:
                    os.rename(tmp_file, CONFIG_FILE)
                return True
            except Exception as e:
                logger.error(f"Lỗi khi lưu cấu hình Telegram: {scrub_sensitive_text(str(e))}")
                return False

    def get_public_config(self) -> Dict[str, Any]:
        """Trả về cấu hình an toàn cho Frontend (đã che giấu token)."""
        with self._lock:
            has_tok = bool(self.bot_token and len(self.bot_token) > 10)
            return {
                "enabled": self.enabled,
                "has_token": has_tok,
                "masked_token": mask_token(self.bot_token) if has_tok else "",
                "chat_id": self.chat_id or "5011367599",
                "masked_chat_id": mask_chat_id(self.chat_id) if self.chat_id else "",
                "notify_per_video": self.notify_per_video,
                "notify_batch_done": self.notify_batch_done,
            }

    def _is_duplicate_and_mark(self, deduplication_key: Optional[str]) -> bool:
        """Kiểm tra và ghi nhớ khoá sự kiện để chống gửi trùng lặp."""
        if not deduplication_key:
            return False
        with self._cache_lock:
            now = time.time()
            # Dọn dẹp cache cũ hơn 1 giờ hoặc nếu kích thước quá 1000
            if len(self._sent_keys) > 1000:
                self._sent_keys = {k: v for k, v in self._sent_keys.items() if now - v < 3600}
            if deduplication_key in self._sent_keys:
                return True
            self._sent_keys[deduplication_key] = now
            return False

    def send_message(
        self,
        message_html: str,
        deduplication_key: Optional[str] = None,
        custom_chat_id: Optional[str] = None,
        custom_token: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 2,
    ) -> Tuple[bool, str]:
        """
        Gửi tin nhắn Telegram với định dạng HTML.
        - Tách lỗi an toàn, không bao giờ raise exception.
        - Khử hoàn toàn Token khỏi log và kết quả trả về.
        - Hỗ trợ custom_token để kiểm tra token mới trực tiếp từ UI.
        - Retry tối đa max_retries lần cho lỗi kết nối hoặc 429/5xx.
        """
        clean_custom_token = str(custom_token or "").strip()
        if clean_custom_token and "•" not in clean_custom_token and not clean_custom_token.startswith("****"):
            target_token = clean_custom_token
        else:
            target_token = self.bot_token

        target_chat_id = custom_chat_id or self.chat_id

        if not target_token:
            return False, "Chưa cấu hình Bot Token Telegram. Hãy nhập Token từ @BotFather."
        if not target_chat_id:
            return False, "Chưa cấu hình Chat ID Telegram"

        # Kiểm tra chống gửi trùng
        if deduplication_key and self._is_duplicate_and_mark(deduplication_key):
            logger.info(f"Bỏ qua tin nhắn trùng lặp: key={deduplication_key}")
            return True, "Bỏ qua do đã gửi trước đó (trùng lặp)"

        url = f"https://api.telegram.org/bot{target_token}/sendMessage"
        payload = {
            "chat_id": target_chat_id,
            "text": message_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    # Nếu dùng custom_token thành công và khác token hiện tại thì cập nhật luôn
                    if clean_custom_token and clean_custom_token != self.bot_token and "•" not in clean_custom_token:
                        self.bot_token = clean_custom_token
                        self.save_config()
                    return True, "Gửi tin nhắn thành công"

                # Parse lỗi từ Telegram API
                try:
                    resp_data = resp.json()
                    err_desc = resp_data.get("description", resp.text)
                except Exception:
                    err_desc = resp.text

                clean_desc = scrub_sensitive_text(err_desc, target_token)

                # Phân loại và giải thích lỗi rõ ràng
                if resp.status_code == 401:
                    last_error = f"HTTP 401: Unauthorized (Bot Token không hợp lệ hoặc đã bị thu hồi trên @BotFather)"
                    logger.warning(f"Lỗi Telegram client: {last_error}")
                    return False, last_error
                elif resp.status_code == 403:
                    last_error = f"HTTP 403: Forbidden ({clean_desc} - Bot chưa được nhấn START hoặc bị chặn trong cuộc trò chuyện)"
                    logger.warning(f"Lỗi Telegram client: {last_error}")
                    return False, last_error
                elif resp.status_code == 400:
                    last_error = f"HTTP 400: Bad Request ({clean_desc} - Chat ID không tồn tại hoặc bot chưa từng nhận tin nhắn từ Chat ID này)"
                    logger.warning(f"Lỗi Telegram client: {last_error}")
                    return False, last_error
                elif resp.status_code == 404:
                    last_error = f"HTTP 404: Not Found (Đường dẫn Telegram API không tồn tại)"
                    logger.warning(f"Lỗi Telegram client: {last_error}")
                    return False, last_error

                last_error = f"HTTP {resp.status_code}: {clean_desc}"

                # Lỗi tạm thời (5xx hoặc 429), chờ một chút rồi thử lại
                if attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
                clean_err = scrub_sensitive_text(str(net_err), target_token)
                last_error = f"Lỗi mạng Telegram: {clean_err}"
                if attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))
            except Exception as ex:
                clean_ex = scrub_sensitive_text(str(ex), target_token)
                last_error = f"Lỗi không xác định: {clean_ex}"
                break

        logger.error(f"Gửi tin nhắn Telegram thất bại sau {max_retries + 1} lần thử: {last_error}")
        return False, last_error

    def send_async(
        self,
        message_html: str,
        deduplication_key: Optional[str] = None,
        custom_chat_id: Optional[str] = None,
        custom_token: Optional[str] = None,
    ):
        """Gửi tin nhắn ở luồng nền (background thread) để không block caller."""
        threading.Thread(
            target=self.send_message,
            args=(message_html, deduplication_key, custom_chat_id, custom_token),
            daemon=True,
        ).start()

    # =========================================================================
    # QUẢN LÝ THÔNG TIN BOT & TỰ ĐỘNG LẤY CHAT ID CHO TỪNG USER
    # =========================================================================

    def get_bot_info(self) -> Dict[str, Any]:
        """Lấy thông tin công khai về Bot Telegram (username, tên hiển thị) qua getMe."""
        with self._lock:
            if not self.bot_token:
                return {"success": False, "error": "Chưa cấu hình Bot Token"}
            if self._bot_info_cache and self._bot_info_cache.get("token") == self.bot_token:
                return {
                    "success": True,
                    "username": self._bot_info_cache.get("username", ""),
                    "first_name": self._bot_info_cache.get("first_name", ""),
                    "can_join_groups": self._bot_info_cache.get("can_join_groups", True),
                }

        url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                info = {
                    "token": self.bot_token,
                    "username": data.get("username", ""),
                    "first_name": data.get("first_name", ""),
                    "can_join_groups": data.get("can_join_groups", True),
                }
                with self._lock:
                    self._bot_info_cache = info
                return {
                    "success": True,
                    "username": info["username"],
                    "first_name": info["first_name"],
                    "can_join_groups": info["can_join_groups"],
                }
            else:
                desc = resp.text
                return {"success": False, "error": scrub_sensitive_text(desc, self.bot_token)}
        except Exception as e:
            return {"success": False, "error": scrub_sensitive_text(str(e), self.bot_token)}

    def start_connect_session(self, user_id: str, timeout_sec: int = 300) -> Dict[str, Any]:
        """Bắt đầu phiên kết nối tự động lấy Chat ID cho một user cụ thể."""
        clean_user_id = str(user_id or "default").strip()
        if not self.bot_token:
            return {"success": False, "error": "Hệ thống chưa cấu hình Bot Token Telegram"}

        bot_info = self.get_bot_info()
        bot_username = bot_info.get("username", "")

        # Sinh mã kết nối ngẫu nhiên NC-XXXXXX
        code = f"NC-{secrets.token_hex(3).upper()}"
        now = time.time()
        expires_at = now + timeout_sec

        with self._session_lock:
            # Dọn dẹp session đã hết hạn
            self._pending_sessions = {
                uid: s for uid, s in self._pending_sessions.items() if s.get("expires_at", 0) > now
            }
            self._pending_sessions[clean_user_id] = {
                "connect_code": code,
                "created_at": now,
                "expires_at": expires_at,
                "status": "WAITING",
            }

        deep_link = f"https://t.me/{bot_username}?start={code}" if bot_username else ""

        return {
            "success": True,
            "user_id": clean_user_id,
            "connect_code": code,
            "bot_username": bot_username,
            "deep_link": deep_link,
            "expires_at": expires_at,
            "timeout_seconds": timeout_sec,
        }

    def poll_connect_session(self, user_id: str, connect_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Polling kiểm tra tin nhắn mới gửi đến bot từ Telegram getUpdates để lấy Chat ID.
        Nhận diện đúng user dựa trên connect_code hoặc session duy nhất.
        """
        clean_user_id = str(user_id or "default").strip()
        now = time.time()

        with self._session_lock:
            session = self._pending_sessions.get(clean_user_id)
            if not session:
                # Nếu đã có trong users profile
                if clean_user_id in self.users:
                    prof = self.get_user_profile(clean_user_id)
                    return {"success": True, "status": "CONNECTED", **prof}
                return {
                    "success": False,
                    "status": "NOT_FOUND",
                    "message": "Không tìm thấy phiên kết nối. Vui lòng bấm 'Kết nối Telegram'.",
                }

            if now > session.get("expires_at", 0):
                self._pending_sessions.pop(clean_user_id, None)
                return {
                    "success": False,
                    "status": "EXPIRED",
                    "message": "Phiên kết nối đã hết hạn sau 5 phút. Vui lòng thử lại.",
                }

            target_code = (connect_code or session.get("connect_code", "")).strip().upper()
            session_created = session.get("created_at", now - 300)
            pending_count = len(self._pending_sessions)

        if not self.bot_token:
            return {"success": False, "status": "ERROR", "message": "Chưa cấu hình Bot Token"}

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        try:
            resp = requests.get(url, params={"limit": 50, "timeout": 2}, timeout=6)
            # Tự động gỡ webhook nếu bot đang bị kẹt webhook (lỗi 409 Conflict)
            if resp.status_code == 409:
                try:
                    requests.post(f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook", timeout=5)
                    resp = requests.get(url, params={"limit": 50, "timeout": 2}, timeout=6)
                except Exception:
                    pass
            if resp.status_code != 200:
                return {"success": False, "status": "ERROR", "message": f"Telegram API lỗi ({resp.status_code})"}
            updates = resp.json().get("result", [])
        except Exception as e:
            return {"success": False, "status": "ERROR", "message": scrub_sensitive_text(str(e), self.bot_token)}

        matched_chat = None
        fallback_chat = None

        # Ngưỡng thời gian nhận tin nhắn (nới lỏng tới 15 phút trước để không bị lệch múi giờ hoặc user nhắn trước)
        time_threshold = min(session_created - 120, now - 900)

        # Duyệt updates từ mới nhất về cũ nhất
        for upd in reversed(updates):
            msg = upd.get("message") or upd.get("channel_post")
            if not msg:
                continue

            msg_text = (msg.get("text") or "").strip()
            msg_date = msg.get("date", 0)

            # Chỉ xét các tin nhắn trong vòng 15 phút gần nhất
            if msg_date < time_threshold:
                continue

            chat = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))
            chat_type = chat.get("type", "private")
            chat_title = chat.get("title") or chat.get("first_name") or chat.get("username") or "Telegram User"
            is_group = chat_type in ("group", "supergroup", "channel")

            chat_candidate = {
                "chat_id": chat_id,
                "chat_type": chat_type,
                "chat_title": chat_title,
                "is_group": is_group,
            }

            text_upper = msg_text.upper()

            # 1. Khớp tuyệt đối nếu có chứa mã kết nối (ví dụ: /start NC-XXXXXX hoặc NC-XXXXXX)
            if target_code and (
                text_upper == target_code
                or text_upper.startswith(f"/START {target_code}")
                or text_upper.startswith(f"/NOVACUT {target_code}")
                or target_code in text_upper
            ):
                matched_chat = chat_candidate
                break

            # 2. Lưu lại ứng viên fallback (tin nhắn /start hoặc bất kỳ tin nhắn nào gần nhất gửi cho bot)
            if fallback_chat is None:
                if text_upper.startswith("/START") or text_upper.startswith("/NOVACUT") or msg_text:
                    fallback_chat = chat_candidate

        # Nếu không có tin nhắn nào khớp chính xác mã, nhưng chỉ có 1 user đang chờ kết nối: dùng fallback candidate
        if not matched_chat and fallback_chat and pending_count == 1:
            matched_chat = fallback_chat

        if matched_chat:
            chat_id = matched_chat["chat_id"]
            connected_at = time.strftime("%H:%M:%S %d/%m/%Y")
            user_entry = {
                "chat_id": chat_id,
                "chat_type": matched_chat["chat_type"],
                "chat_title": matched_chat["chat_title"],
                "is_group": matched_chat["is_group"],
                "connected_at": connected_at,
                "notify_per_video": True,
                "notify_batch_done": True,
            }

            with self._lock:
                self.users[clean_user_id] = user_entry
                # Đồng bộ luôn chat_id mặc định của hệ thống nếu chưa có hoặc là mặc định
                if not self.chat_id or self.chat_id == "5011367599":
                    self.chat_id = chat_id
                self.save_config()

            with self._session_lock:
                self._pending_sessions.pop(clean_user_id, None)

            # Gửi tin nhắn xác nhận qua Telegram
            if matched_chat["is_group"]:
                confirm_msg = (
                    "🎉 <b>NovaCut - Kết Nối Nhóm Thành Công!</b>\n\n"
                    f"Nhóm <b>{html.escape(matched_chat['chat_title'])}</b> đã được liên kết với NovaCut.\n\n"
                    "⚠️ <i>Lưu ý: Mọi thông báo biên tập video của người dùng sẽ được gửi công khai tới nhóm này.</i>"
                )
            else:
                confirm_msg = (
                    "🎉 <b>NovaCut - Kết Nối Thành Công!</b>\n\n"
                    f"Xin chào <b>{html.escape(matched_chat['chat_title'])}</b>! Tài khoản NovaCut của bạn đã được kết nối với Telegram Bot.\n\n"
                    "🚀 <i>Từ bây giờ bạn sẽ nhận được thông báo tiến độ và kết quả biên tập video trực tiếp tại đây!</i>"
                )
            self.send_async(confirm_msg, custom_chat_id=chat_id)

            return {
                "success": True,
                "status": "CONNECTED",
                "chat_id": mask_chat_id(chat_id),
                "chat_type": matched_chat["chat_type"],
                "chat_title": matched_chat["chat_title"],
                "is_group": matched_chat["is_group"],
                "connected_at": connected_at,
            }

        # Chưa thấy tin nhắn khớp
        remaining_sec = max(0, int(session.get("expires_at", 0) - now))
        return {
            "success": True,
            "status": "WAITING",
            "expires_in": remaining_sec,
            "connect_code": session.get("connect_code", ""),
        }

    def set_user_manual_chat_id(self, user_id: str, chat_id: str, bot_token: Optional[str] = None) -> Dict[str, Any]:
        """Cho phép người dùng trực tiếp áp dụng Chat ID thủ công (không bắt buộc chờ bot)."""
        clean_user_id = str(user_id or "default").strip()
        clean_chat_id = str(chat_id or "").strip()
        clean_token = str(bot_token or "").strip()

        if not clean_chat_id:
            return {"success": False, "error": "Vui lòng nhập Chat ID hợp lệ"}

        is_group = clean_chat_id.startswith("-")
        connected_at = time.strftime("%H:%M:%S %d/%m/%Y")

        user_entry = {
            "chat_id": clean_chat_id,
            "chat_type": "group" if is_group else "private",
            "chat_title": "Nhóm Telegram" if is_group else "Người dùng NovaCut",
            "is_group": is_group,
            "connected_at": connected_at,
            "notify_per_video": True,
            "notify_batch_done": True,
        }

        with self._lock:
            self.users[clean_user_id] = user_entry
            self.chat_id = clean_chat_id
            if clean_token and "•" not in clean_token and not clean_token.startswith("****"):
                self.bot_token = clean_token
            self.save_config()

        with self._session_lock:
            self._pending_sessions.pop(clean_user_id, None)

        # Gửi tin nhắn xác nhận tới Chat ID vừa nhập
        if is_group:
            confirm_msg = (
                "🎉 <b>NovaCut - Kết Nối Nhóm Thành Công!</b>\n\n"
                f"Chat ID nhóm <code>{clean_chat_id}</code> đã được liên kết với NovaCut.\n\n"
                "⚠️ <i>Lưu ý: Mọi thông báo biên tập video sẽ được gửi công khai tới nhóm này.</i>"
            )
        else:
            confirm_msg = (
                "🎉 <b>NovaCut - Kết Nối Thành Công!</b>\n\n"
                f"Tài khoản NovaCut đã được liên kết với Chat ID <code>{clean_chat_id}</code>.\n\n"
                "🚀 <i>Từ bây giờ bạn sẽ nhận được thông báo tiến độ và kết quả biên tập video trực tiếp tại đây!</i>"
            )
        self.send_async(confirm_msg, custom_chat_id=clean_chat_id)

        profile = {
            "connected": True,
            "chat_id": mask_chat_id(clean_chat_id),
            "chat_type": user_entry["chat_type"],
            "chat_title": user_entry["chat_title"],
            "is_group": user_entry["is_group"],
            "connected_at": connected_at,
        }

        return {
            "success": True,
            "status": "CONNECTED",
            "profile": profile,
            **profile,
            "message": f"Đã áp dụng Chat ID {mask_chat_id(clean_chat_id)} thành công!",
        }

    def send_sample_notification(
        self,
        user_id: str,
        sample_type: str = "video",
        custom_token: Optional[str] = None,
        custom_chat_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Gửi mẫu thông báo mô phỏng thực tế để người dùng kiểm tra giao diện và kết nối bot."""
        clean_user_id = str(user_id or "default").strip()
        target_chat = custom_chat_id or self._resolve_target_chat(clean_user_id)
        clean_token = str(custom_token or "").strip()
        effective_token = clean_token if (clean_token and "•" not in clean_token and not clean_token.startswith("****")) else self.bot_token

        if not effective_token:
            return False, "Chưa cấu hình Bot Token Telegram. Hãy nhập Token từ @BotFather."
        if not target_chat:
            return False, "Chưa có Chat ID nhận tin nhắn. Hãy kết nối hoặc nhập Chat ID thủ công."

        curr_time = time.strftime("%H:%M:%S %d/%m/%Y")

        if sample_type == "video":
            msg = (
                "🎬 <b>NovaCut: Video Hoàn Thành (Thông Báo Thử Nghiệm)</b>\n\n"
                "📹 <b>Tên video:</b> <code>Review Phim - Tóm Tắt Siêu Phẩm Tập 1.mp4</code>\n"
                "✅ <b>Trạng thái:</b> Hoàn thành xuất sắc\n"
                "⚙️ <b>Preset:</b> TikTok / Shorts 9:16 (Auto Reframe)\n"
                "📁 <b>Tệp kết quả:</b> <code>output/video_review_ep1_1080p.mp4</code>\n"
                "⏱️ <b>Thời gian xử lý:</b> 1p 25s\n"
                "📊 <b>Tiến độ batch:</b> 1/5 (20%)\n\n"
                f"🕒 <i>Thời gian kiểm tra: {curr_time}</i>\n"
                "✨ <i>Đây là thông báo mẫu mô phỏng khi từng video được biên tập xong!</i>"
            )
        elif sample_type == "batch":
            msg = (
                "🎉 <b>NovaCut: Hoàn Tất Toàn Bộ Hàng Đợi! (Thông Báo Thử Nghiệm)</b>\n\n"
                "📦 <b>Tổng số video:</b> 10\n"
                "✅ <b>Thành công:</b> 10\n"
                "❌ <b>Thất bại:</b> 0\n"
                "⏱️ <b>Tổng thời gian:</b> 14p 32s\n"
                "📂 <b>Thư mục xuất:</b> <code>D:\\NovaCut\\Output\\Batch_Overnight</code>\n\n"
                f"🕒 <i>Thời gian kiểm tra: {curr_time}</i>\n"
                "🌟 <i>Tất cả video đã xử lý xong. Đây là báo cáo tổng kết mẫu khi chạy hàng loạt!</i>"
            )
        elif sample_type == "failure":
            msg = (
                "⚠️ <b>NovaCut: Video Thất Bại (Thông Báo Thử Nghiệm)</b>\n\n"
                "📹 <b>Tên video:</b> <code>Video Test Lỗi.mp4</code>\n"
                "❌ <b>Trạng thái:</b> Thất bại\n"
                "🛑 <b>Nguyên nhân:</b> Định dạng video đầu vào bị hỏng hoặc không thể đọc stream âm thanh.\n"
                "⏱️ <b>Thời gian trước khi lỗi:</b> 12s\n"
                "📊 <b>Tiến độ batch:</b> 2/5\n\n"
                "ℹ️ <i>NovaCut vẫn tiếp tục xử lý các video còn lại trong hàng đợi.</i>"
            )
        else:
            msg = (
                "🤖 <b>NovaCut - Kiểm Tra Kết Nối Bot</b>\n\n"
                "✅ <b>Thành công!</b> Kết nối giữa NovaCut và Telegram Bot đã sẵn sàng nhận thông báo.\n\n"
                f"🕒 <i>Thời gian kiểm tra: {curr_time}</i>"
            )

        return self.send_message(msg, custom_chat_id=target_chat, custom_token=effective_token)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Lấy thông tin kết nối Telegram của một user (đã mask chat_id)."""
        clean_user_id = str(user_id or "default").strip()
        with self._lock:
            u_data = self.users.get(clean_user_id, {})
            raw_chat_id = u_data.get("chat_id", "")
            connected = bool(raw_chat_id)
            return {
                "user_id": clean_user_id,
                "connected": connected,
                "chat_id": mask_chat_id(raw_chat_id) if connected else "",
                "chat_type": u_data.get("chat_type", "private"),
                "chat_title": u_data.get("chat_title", ""),
                "is_group": bool(u_data.get("is_group", False)),
                "connected_at": u_data.get("connected_at", ""),
                "notify_per_video": bool(u_data.get("notify_per_video", True)),
                "notify_batch_done": bool(u_data.get("notify_batch_done", True)),
            }

    def disconnect_user(self, user_id: str) -> bool:
        """Ngắt kết nối Telegram và xóa Chat ID đã lưu của một user."""
        clean_user_id = str(user_id or "default").strip()
        with self._lock:
            if clean_user_id in self.users:
                self.users.pop(clean_user_id, None)
                self.save_config()
        with self._session_lock:
            self._pending_sessions.pop(clean_user_id, None)
        return True

    def send_user_test_message(self, user_id: str, custom_token: Optional[str] = None) -> Tuple[bool, str]:
        """Gửi tin nhắn kiểm tra tới Chat ID đã lưu của một user cụ thể."""
        clean_user_id = str(user_id or "default").strip()
        target_chat = self._resolve_target_chat(clean_user_id)
        if not target_chat:
            return False, "Người dùng chưa kết nối Telegram. Hãy bấm 'Kết nối Telegram' hoặc dán Chat ID."
        time_str = time.strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "🧪 <b>NovaCut - Tin Nhắn Kiểm Tra</b>\n\n"
            "Xin chào! Kết nối Telegram của bạn đang hoạt động bình thường.\n\n"
            f"🕒 <i>Thời gian kiểm tra: {time_str}</i>"
        )
        return self.send_message(msg, custom_chat_id=target_chat, custom_token=custom_token)

    def _resolve_target_chat(self, user_id: Optional[str] = None) -> Optional[str]:
        """Tìm Chat ID phù hợp: ưu tiên Chat ID của user_id, fallback về default chat_id."""
        if user_id:
            clean_id = str(user_id).strip()
            with self._lock:
                if clean_id in self.users and self.users[clean_id].get("chat_id"):
                    return self.users[clean_id]["chat_id"]
        return self.chat_id

    # =========================================================================
    # CÁC MẪU THÔNG BÁO CHUYÊN BIỆT THEO YÊU CẦU NGHIỆM THU
    # =========================================================================

    def notify_video_success(
        self,
        video_title: str,
        output_path: str = "",
        duration_sec: Optional[float] = None,
        current_index: int = 1,
        total_count: int = 1,
        preset_name: str = "",
        task_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Gửi thông báo sau khi một video trong batch hoàn thành xuất sắc."""
        if not self.enabled or not self.notify_per_video:
            return False

        safe_title = html.escape(video_title or "Video không tên")
        safe_out_name = html.escape(os.path.basename(output_path)) if output_path else "Không rõ"
        safe_preset = html.escape(preset_name) if preset_name else ""

        duration_str = format_duration(duration_sec) if duration_sec is not None else "N/A"
        progress_pct = int(round((current_index / max(1, total_count)) * 100))

        lines = [
            "🎬 <b>NovaCut: Video Hoàn Thành</b>",
            "",
            f"📹 <b>Tên video:</b> <code>{safe_title}</code>",
            f"✅ <b>Trạng thái:</b> Thành công",
            f"📁 <b>Tệp kết quả:</b> <code>{safe_out_name}</code>",
            f"⏱️ <b>Thời gian xử lý:</b> {duration_str}",
            f"📊 <b>Tiến độ batch:</b> {current_index}/{total_count} ({progress_pct}%)",
        ]
        if safe_preset:
            lines.insert(3, f"⚙️ <b>Preset:</b> {safe_preset}")

        msg = "\n".join(lines)
        dedup = f"video_success:{task_id or safe_title}:{current_index}"
        target_chat = self._resolve_target_chat(user_id)
        self.send_async(msg, deduplication_key=dedup, custom_chat_id=target_chat)
        return True

    def notify_video_failure(
        self,
        video_title: str,
        error_message: str = "",
        duration_sec: Optional[float] = None,
        current_index: int = 1,
        total_count: int = 1,
        preset_name: str = "",
        task_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Gửi thông báo khi một video xử lý thất bại (ngắn gọn, không lộ traceback)."""
        if not self.enabled or not self.notify_per_video:
            return False

        safe_title = html.escape(video_title or "Video không tên")
        clean_err = scrub_sensitive_text(error_message or "Lỗi không xác định")
        clean_err = clean_err.split("\n")[0].strip()
        if len(clean_err) > 180:
            clean_err = clean_err[:177] + "..."
        safe_err = html.escape(clean_err)

        duration_str = format_duration(duration_sec) if duration_sec is not None else "N/A"

        lines = [
            "⚠️ <b>NovaCut: Video Thất Bại</b>",
            "",
            f"📹 <b>Tên video:</b> <code>{safe_title}</code>",
            f"❌ <b>Trạng thái:</b> Thất bại",
            f"🛑 <b>Nguyên nhân:</b> {safe_err}",
            f"⏱️ <b>Thời gian trước khi lỗi:</b> {duration_str}",
            f"📊 <b>Tiến độ batch:</b> {current_index}/{total_count}",
            "",
            "ℹ️ <i>NovaCut vẫn tiếp tục xử lý các video còn lại trong hàng đợi.</i>",
        ]

        msg = "\n".join(lines)
        dedup = f"video_failure:{task_id or safe_title}:{current_index}"
        target_chat = self._resolve_target_chat(user_id)
        self.send_async(msg, deduplication_key=dedup, custom_chat_id=target_chat)
        return True

    def notify_batch_completed(
        self,
        total_count: int,
        success_count: int,
        failed_count: int,
        cancelled_count: int = 0,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        output_dir: str = "",
        batch_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Gửi thông báo tổng hợp khi hoàn tất toàn bộ danh sách batch."""
        if not self.enabled or not self.notify_batch_done:
            return False

        now = end_time or time.time()
        elapsed_sec = (now - start_time) if start_time else None
        elapsed_str = format_duration(elapsed_sec) if elapsed_sec is not None else "N/A"

        safe_out_dir = html.escape(os.path.normpath(output_dir)) if output_dir else "output/batch"

        lines = [
            "🎉 <b>NovaCut: Hoàn Tất Toàn Bộ Hàng Đợi!</b>",
            "",
            f"📦 <b>Tổng số video:</b> {total_count}",
            f"✅ <b>Thành công:</b> {success_count}",
            f"❌ <b>Thất bại:</b> {failed_count}",
        ]
        if cancelled_count > 0:
            lines.append(f"⏹️ <b>Bỏ qua / Đã hủy:</b> {cancelled_count}")

        lines.extend([
            f"⏱️ <b>Tổng thời gian:</b> {elapsed_str}",
            f"📂 <b>Thư mục xuất:</b> <code>{safe_out_dir}</code>",
            "",
            "🌟 <i>Tất cả video đã được xử lý xong. Chúc bạn có những video triệu view!</i>",
        ])

        msg = "\n".join(lines)
        dedup = f"batch_completed:{batch_id or int(now)}:{total_count}:{success_count}"
        target_chat = self._resolve_target_chat(user_id)
        self.send_async(msg, deduplication_key=dedup, custom_chat_id=target_chat)
        return True

    def notify_batch_cancelled(
        self,
        total_count: int,
        completed_count: int,
        failed_count: int,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        batch_id: str = "",
        user_id: Optional[str] = None,
    ) -> bool:
        """Gửi thông báo khi tiến trình batch bị người dùng hủy/dừng ngang."""
        if not self.enabled or not self.notify_batch_done:
            return False

        now = end_time or time.time()
        elapsed_sec = (now - start_time) if start_time else None
        elapsed_str = format_duration(elapsed_sec) if elapsed_sec is not None else "N/A"

        lines = [
            "🛑 <b>NovaCut: Hàng Đợi Đã Bị Hủy</b>",
            "",
            "Trạng thái: Người dùng đã chủ động dừng hàng đợi biên tập.",
            f"📊 <b>Thống kê trước khi dừng:</b>",
            f"• Đã hoàn thành: {completed_count}/{total_count}",
            f"• Lỗi: {failed_count}",
            f"⏱️ <b>Thời gian đã chạy:</b> {elapsed_str}",
        ]

        msg = "\n".join(lines)
        dedup = f"batch_cancelled:{batch_id or int(now)}:{completed_count}"
        target_chat = self._resolve_target_chat(user_id)
        self.send_async(msg, deduplication_key=dedup, custom_chat_id=target_chat)
        return True

    def send_test_message(self, test_token: str = "", test_chat_id: str = "") -> Tuple[bool, str]:
        """Gửi một tin nhắn kiểm tra kết nối Telegram trực tiếp (đồng bộ để UI nhận kết quả ngay)."""
        token = test_token.strip() if test_token and "•" not in test_token and not test_token.startswith("****") else self.bot_token
        chat_id = test_chat_id.strip() if test_chat_id else self.chat_id

        if not token:
            return False, "Chưa nhập Bot Token Telegram. Vui lòng lấy Token từ @BotFather."
        if not chat_id:
            return False, "Chưa nhập Chat ID Telegram (mặc định: 5011367599)."

        curr_time = time.strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "🤖 <b>NovaCut - Kiểm Tra Kết Nối Telegram</b>\n\n"
            "✅ <b>Thành công!</b> Kết nối giữa NovaCut và Telegram Bot đã sẵn sàng.\n\n"
            f"🕒 <i>Thời gian kiểm tra: {curr_time}</i>\n"
            "🚀 <i>Từ giờ bạn sẽ nhận được thông báo tiến độ xử lý video trực tiếp qua đây!</i>"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return True, "Gửi tin nhắn kiểm tra thành công! Hãy kiểm tra ứng dụng Telegram của bạn."
            try:
                err_json = resp.json()
                desc = err_json.get("description", resp.text)
            except Exception:
                desc = resp.text
            clean_desc = scrub_sensitive_text(desc, token)
            return False, f"Telegram API lỗi ({resp.status_code}): {clean_desc}"
        except Exception as e:
            clean_err = scrub_sensitive_text(str(e), token)
            return False, f"Không thể kết nối đến máy chủ Telegram: {clean_err}"


def get_telegram_notifier() -> TelegramNotifier:
    return TelegramNotifier.get_instance()
