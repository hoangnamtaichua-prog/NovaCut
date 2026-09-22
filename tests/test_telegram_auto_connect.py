# -*- coding: utf-8 -*-
"""
Unit tests cho quy trình tự động lấy Chat ID Telegram cho từng user trong NovaCut.
Xác thực các tiêu chí:
1. Cơ chế Bot chung, username bot và bảo mật Token.
2. Tự động lấy Chat ID qua getUpdates (Private chat & Group chat).
3. Phân tách dữ liệu giữa các User (User Isolation).
4. Định danh chính xác khi nhiều user kết nối cùng lúc.
5. Timeout 5 phút và chống gửi trùng.
6. Masking Chat ID bảo mật.
7. Tích hợp gửi thông báo batch theo User ID.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import json
import time

# Thêm đường dẫn project
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import telegram_notifier
from telegram_notifier import (
    TelegramNotifier,
    mask_chat_id,
    mask_token,
    scrub_sensitive_text,
    get_telegram_notifier
)
from web_app import app


class TestTelegramAutoConnect(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = os.path.join(self.temp_dir, "telegram_config.json")
        telegram_notifier.CONFIG_FILE = self.temp_config
        telegram_notifier.FALLBACK_CONFIG_FILE = os.path.join(self.temp_dir, "fallback.json")

        self.notifier = TelegramNotifier()
        self.notifier.enabled = True
        self.notifier.bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz_1234567"
        self.notifier.chat_id = "5011367599"
        self.notifier.users = {}
        self.notifier._pending_sessions = {}
        self.notifier._bot_info_cache = {}

        # Gán singleton instance để Flask routes dùng chung
        TelegramNotifier._instance = self.notifier

        self.client = app.test_client()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mask_chat_id(self):
        """Kiểm tra che giấu Chat ID (1-1 và group)."""
        self.assertEqual(mask_chat_id("5011367599"), "5011****99")
        self.assertEqual(mask_chat_id("-1001987654321"), "-1001****21")
        self.assertEqual(mask_chat_id("123"), "****")
        self.assertEqual(mask_chat_id(""), "")

    @patch("requests.get")
    def test_get_bot_info(self, mock_get):
        """Kiểm tra lấy thông tin bot chung qua getMe."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": {
                "id": 123456789,
                "is_bot": True,
                "first_name": "NovaCut Test Bot",
                "username": "NovaCutTestBot",
                "can_join_groups": True
            }
        }
        mock_get.return_value = mock_resp

        info = self.notifier.get_bot_info()
        self.assertTrue(info["success"])
        self.assertEqual(info["username"], "NovaCutTestBot")
        self.assertEqual(info["first_name"], "NovaCut Test Bot")
        self.assertTrue(info["can_join_groups"])

    @patch.object(TelegramNotifier, "get_bot_info")
    def test_start_connect_session_lifecycle(self, mock_info):
        """Kiểm tra khởi tạo phiên kết nối với mã NC-XXXXXX và thời hạn 5 phút."""
        mock_info.return_value = {"success": True, "username": "NovaCutTestBot"}

        session = self.notifier.start_connect_session(user_id="user_123", timeout_sec=300)
        self.assertTrue(session["success"])
        self.assertEqual(session["user_id"], "user_123")
        self.assertTrue(session["connect_code"].startswith("NC-"))
        self.assertEqual(session["bot_username"], "NovaCutTestBot")
        self.assertTrue("start=" in session["deep_link"])
        self.assertGreater(session["expires_at"], time.time() + 290)

    @patch("requests.get")
    @patch.object(TelegramNotifier, "send_async")
    def test_poll_connect_private_chat(self, mock_send, mock_get):
        """Kiểm tra nhận diện tin nhắn kết nối trong chat riêng tư."""
        session = self.notifier.start_connect_session(user_id="user_alice", timeout_sec=300)
        code = session["connect_code"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1001,
                    "message": {
                        "message_id": 50,
                        "from": {"id": 99887766, "first_name": "Alice"},
                        "chat": {"id": 99887766, "type": "private", "first_name": "Alice"},
                        "date": int(time.time()),
                        "text": f"/start {code}"
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        poll_res = self.notifier.poll_connect_session(user_id="user_alice", connect_code=code)
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "CONNECTED")
        self.assertEqual(poll_res["chat_id"], mask_chat_id("99887766"))
        self.assertFalse(poll_res["is_group"])

        # Xác thực user profile đã được lưu
        profile = self.notifier.get_user_profile("user_alice")
        self.assertTrue(profile["connected"])
        self.assertEqual(profile["chat_id"], mask_chat_id("99887766"))

    @patch("requests.get")
    @patch.object(TelegramNotifier, "send_async")
    def test_poll_connect_group_chat(self, mock_send, mock_get):
        """Kiểm tra nhận diện tin nhắn kết nối trong nhóm Telegram kèm cờ is_group."""
        session = self.notifier.start_connect_session(user_id="user_bob", timeout_sec=300)
        code = session["connect_code"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 2001,
                    "message": {
                        "message_id": 80,
                        "from": {"id": 112233, "first_name": "Bob"},
                        "chat": {"id": -100987654321, "type": "supergroup", "title": "NovaCut Team Group"},
                        "date": int(time.time()),
                        "text": f"/novacut {code}"
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        poll_res = self.notifier.poll_connect_session(user_id="user_bob", connect_code=code)
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "CONNECTED")
        self.assertTrue(poll_res["is_group"])
        self.assertEqual(poll_res["chat_title"], "NovaCut Team Group")

    @patch("requests.get")
    def test_poll_waiting_and_expired(self, mock_get):
        """Kiểm tra trạng thái WAITING và EXPIRED."""
        session = self.notifier.start_connect_session(user_id="user_wait", timeout_sec=1)
        code = session["connect_code"]

        # Chưa có tin nhắn -> WAITING
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": []}
        mock_get.return_value = mock_resp

        poll_res = self.notifier.poll_connect_session(user_id="user_wait", connect_code=code)
        self.assertEqual(poll_res["status"], "WAITING")

        # Hết hạn -> EXPIRED
        time.sleep(1.1)
        poll_res_exp = self.notifier.poll_connect_session(user_id="user_wait", connect_code=code)
        self.assertEqual(poll_res_exp["status"], "EXPIRED")

    @patch("requests.get")
    @patch.object(TelegramNotifier, "send_async")
    def test_concurrent_users_isolation(self, mock_send, mock_get):
        """Kiểm tra khi nhiều user kết nối cùng lúc, mỗi user nhận đúng Chat ID của mình."""
        session_a = self.notifier.start_connect_session(user_id="user_A", timeout_sec=300)
        session_b = self.notifier.start_connect_session(user_id="user_B", timeout_sec=300)

        code_a = session_a["connect_code"]
        code_b = session_b["connect_code"]

        # Giả lập 2 tin nhắn gửi cùng lúc trong updates
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 3001,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": 11111111, "type": "private", "first_name": "UserA"},
                        "date": int(time.time()),
                        "text": f"/start {code_a}"
                    }
                },
                {
                    "update_id": 3002,
                    "message": {
                        "message_id": 2,
                        "chat": {"id": 22222222, "type": "private", "first_name": "UserB"},
                        "date": int(time.time()),
                        "text": f"/start {code_b}"
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        res_a = self.notifier.poll_connect_session(user_id="user_A", connect_code=code_a)
        res_b = self.notifier.poll_connect_session(user_id="user_B", connect_code=code_b)

        self.assertEqual(res_a["chat_id"], mask_chat_id("11111111"))
        self.assertEqual(res_b["chat_id"], mask_chat_id("22222222"))

        # Kiểm tra cách ly: user_A không thấy chat_id của user_B
        prof_a = self.notifier.get_user_profile("user_A")
        prof_b = self.notifier.get_user_profile("user_B")
        self.assertNotEqual(prof_a["chat_id"], prof_b["chat_id"])

    def test_disconnect_user(self):
        """Kiểm tra ngắt kết nối và xóa cấu hình user."""
        self.notifier.users["user_x"] = {
            "chat_id": "77778888",
            "connected_at": "12:00:00 22/09/2026"
        }
        self.assertTrue(self.notifier.get_user_profile("user_x")["connected"])

        self.notifier.disconnect_user("user_x")
        self.assertFalse(self.notifier.get_user_profile("user_x")["connected"])

    @patch("requests.post")
    def test_send_user_test_message(self, mock_post):
        """Kiểm tra gửi tin nhắn thử nghiệm tới Chat ID của user."""
        self.notifier.users["user_test"] = {"chat_id": "12345678"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        success, msg = self.notifier.send_user_test_message("user_test")
        self.assertTrue(success)

    @patch.object(TelegramNotifier, "send_async")
    def test_batch_notify_routes_to_user_chat_id(self, mock_send):
        """Kiểm tra gửi thông báo video success và batch completed đúng chat_id của user."""
        self.notifier.users["user_vip"] = {"chat_id": "999888777"}

        # Gửi video success kèm user_id
        self.notifier.notify_video_success(
            video_title="Video 1",
            user_id="user_vip"
        )
        self.assertTrue(mock_send.called)
        _, kwargs = mock_send.call_args
        self.assertEqual(kwargs.get("custom_chat_id"), "999888777")

    @patch.object(TelegramNotifier, "send_async")
    def test_set_user_manual_chat_id(self, mock_send):
        """Kiểm tra điền Chat ID thủ công (cá nhân và nhóm) hoạt động ngay lập tức."""
        # 1. Chat ID cá nhân
        res1 = self.notifier.set_user_manual_chat_id("user_manual_1", "5011367599")
        self.assertTrue(res1["success"])
        self.assertTrue(res1["connected"])
        self.assertTrue(res1["profile"]["connected"])
        self.assertFalse(res1["is_group"])
        self.assertEqual(res1["chat_type"], "private")

        # 2. Chat ID nhóm (âm)
        res2 = self.notifier.set_user_manual_chat_id("user_manual_2", "-1001234567890")
        self.assertTrue(res2["success"])
        self.assertTrue(res2["connected"])
        self.assertTrue(res2["profile"]["connected"])
        self.assertTrue(res2["is_group"])
        self.assertEqual(res2["chat_type"], "group")

    @patch("requests.post")
    def test_send_sample_notification(self, mock_post):
        """Kiểm tra gửi các loại thông báo mẫu (ping, video, batch, failure)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        self.notifier.users["user_sample"] = {"chat_id": "5011367599"}

        for stype in ["ping", "video", "batch", "failure"]:
            success, msg = self.notifier.send_sample_notification("user_sample", sample_type=stype)
            self.assertTrue(success, f"Failed for sample type: {stype}")

    @patch("requests.get")
    @patch.object(TelegramNotifier, "send_async")
    def test_poll_connect_fallback_without_code(self, mock_send, mock_get):
        """Kiểm tra người dùng chỉ gửi tin nhắn thông thường không có mã thì vẫn fallback kết nối thành công nếu chỉ có 1 session."""
        session = self.notifier.start_connect_session(user_id="user_single", timeout_sec=300)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 9999,
                    "message": {
                        "message_id": 10,
                        "chat": {"id": 88887777, "type": "private", "first_name": "SingleUser"},
                        "date": int(time.time()),
                        "text": "/start"  # Người dùng chỉ bấm nút Start trơn, không có mã đính kèm
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        poll_res = self.notifier.poll_connect_session(user_id="user_single", connect_code=session["connect_code"])
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "CONNECTED")
        self.assertEqual(poll_res["chat_id"], mask_chat_id("88887777"))

    def test_api_routes_auto_connect(self):
        """Kiểm tra các endpoints Flask liên quan đến auto-connect."""
        with patch.object(TelegramNotifier, "get_bot_info", return_value={"success": True, "username": "TestBot"}):
            res = self.client.get("/api/telegram/bot_info")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json.get("username"), "TestBot")

        # Test start
        with patch.object(TelegramNotifier, "get_bot_info", return_value={"success": True, "username": "TestBot"}):
            res_start = self.client.post("/api/telegram/connect/start", json={"user_id": "api_user"})
            self.assertEqual(res_start.status_code, 200)
            self.assertTrue(res_start.json.get("connect_code").startswith("NC-"))

        # Test status
        res_status = self.client.get("/api/telegram/user/status?user_id=api_user")
        self.assertEqual(res_status.status_code, 200)
        self.assertFalse(res_status.json.get("profile", {}).get("connected"))

        # Test manual_connect route
        with patch.object(TelegramNotifier, "send_async"):
            res_manual = self.client.post("/api/telegram/user/manual_connect", json={
                "user_id": "api_user",
                "chat_id": "5011367599"
            })
            self.assertEqual(res_manual.status_code, 200)
            self.assertTrue(res_manual.json.get("success"))
            self.assertTrue(res_manual.json.get("profile", {}).get("connected"))

        # Test sample test route
        with patch.object(TelegramNotifier, "send_sample_notification", return_value=(True, "OK")):
            res_sample = self.client.post("/api/telegram/test_sample", json={
                "user_id": "api_user",
                "sample_type": "video"
            })
            self.assertEqual(res_sample.status_code, 200)
            self.assertTrue(res_sample.json.get("success"))

        # Test disconnect
        res_disc = self.client.post("/api/telegram/user/disconnect", json={"user_id": "api_user"})
        self.assertEqual(res_disc.status_code, 200)
        self.assertTrue(res_disc.json.get("success"))


if __name__ == "__main__":
    unittest.main()

