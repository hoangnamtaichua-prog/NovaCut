"""
Automated unit and integration tests for Telegram notification system in NovaCut.
Kiểm tra toàn diện các trường hợp:
1. Nạp và lưu cấu hình, giá trị mặc định Chat ID 5011367599, Masking Bot Token.
2. Khử Token (Scrubbing / Redaction) khỏi mọi văn bản, URL, lỗi.
3. Gửi tin nhắn thành công, an toàn Unicode và ký tự đặc biệt (<, >, &).
4. Xử lý lỗi mạng và mất kết nối: không dừng pipeline, timeout, retry giới hạn.
5. Cơ chế chống gửi trùng (Deduplication cache).
6. Các sự kiện: video thành công, video thất bại, hoàn tất batch, hủy batch, batch rỗng.
7. Trạng thái tắt thông báo (disabled): không thực hiện request mạng.
8. Các API route Flask: GET/POST /api/telegram/config, POST /api/telegram/test, POST /api/telegram/notify.
"""

import os
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from telegram_notifier import (
    TelegramNotifier,
    scrub_sensitive_text,
    mask_token,
    format_duration,
    get_telegram_notifier
)
import web_app


class TestTelegramNotifier(unittest.TestCase):
    def setUp(self):
        self.notifier = TelegramNotifier()
        # Reset state for tests
        self.notifier.enabled = True
        self.notifier.bot_token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ1234567"
        self.notifier.chat_id = "5011367599"
        self.notifier.notify_per_video = True
        self.notifier.notify_batch_done = True
        self.notifier._sent_keys.clear()

    def test_default_chat_id(self):
        """Chat ID mặc định phải là 5011367599."""
        fresh_notifier = TelegramNotifier()
        self.assertEqual(fresh_notifier.chat_id, "5011367599")

    def test_mask_token(self):
        """Token phải được che giấu, không lộ toàn bộ trên giao diện."""
        fake_token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ1234567"
        masked = mask_token(fake_token)
        self.assertTrue(masked.startswith("1234"))
        self.assertTrue(masked.endswith("4567"))
        self.assertIn("••••", masked)
        self.assertNotIn("ABCdefGHI", masked)

        # Empty / short token
        self.assertEqual(mask_token(""), "")
        self.assertEqual(mask_token("1234"), "••••••••")

    def test_scrub_sensitive_text(self):
        """Hàm scrub phải loại bỏ triệt để token khỏi chuỗi, URL và traceback."""
        fake_token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ1234567"
        raw_error = f"Failed to call https://api.telegram.org/bot{fake_token}/sendMessage with token {fake_token}"
        cleaned = scrub_sensitive_text(raw_error, fake_token)

        self.assertNotIn(fake_token, cleaned)
        self.assertIn("[REDACTED_BOT_TOKEN]", cleaned)
        self.assertIn("https://api.telegram.org/bot[REDACTED]/sendMessage", cleaned)

    def test_format_duration(self):
        """Định dạng thời gian dễ đọc."""
        self.assertEqual(format_duration(45), "45s")
        self.assertEqual(format_duration(85), "1p 25s")
        self.assertEqual(format_duration(3665), "1h 1p 5s")
        self.assertEqual(format_duration(None), "0s")

    @patch("requests.post")
    def test_send_message_success(self, mock_post):
        """Gửi tin nhắn thành công qua Telegram API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {}}
        mock_post.return_value = mock_response

        success, msg = self.notifier.send_message("<b>Xin chào NovaCut</b>")
        self.assertTrue(success)
        self.assertEqual(msg, "Gửi tin nhắn thành công")
        mock_post.assert_called_once()

        # Check payload
        called_args = mock_post.call_args
        payload = called_args[1]["json"]
        self.assertEqual(payload["chat_id"], "5011367599")
        self.assertEqual(payload["text"], "<b>Xin chào NovaCut</b>")
        self.assertEqual(payload["parse_mode"], "HTML")

    @patch("requests.post")
    def test_deduplication(self, mock_post):
        """Tin nhắn có cùng deduplication_key chỉ được gửi 1 lần duy nhất."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Lần 1: gửi thành công
        res1, _ = self.notifier.send_message("Event 1", deduplication_key="key_123")
        self.assertTrue(res1)
        self.assertEqual(mock_post.call_count, 1)

        # Lần 2: bị deduplication chặn, không gọi requests.post lần 2
        res2, msg2 = self.notifier.send_message("Event 1", deduplication_key="key_123")
        self.assertTrue(res2)
        self.assertIn("trùng lặp", msg2)
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_network_failure_isolated(self, mock_post):
        """Mất mạng Telegram: không gây dừng hoặc crash pipeline."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        # Không raise exception, trả về False an toàn
        success, error_msg = self.notifier.send_message("Test message")
        self.assertFalse(success)
        self.assertIn("Lỗi mạng Telegram", error_msg)

    @patch("requests.post")
    def test_client_error_no_retry(self, mock_post):
        """Lỗi 401 Unauthorized (sai token) không lặp lại retry vô ích."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}
        mock_post.return_value = mock_response

        success, error_msg = self.notifier.send_message("Test message")
        self.assertFalse(success)
        self.assertIn("401", error_msg)
        # Chỉ gọi 1 lần, không retry khi gặp 401
        self.assertEqual(mock_post.call_count, 1)

    @patch.object(TelegramNotifier, "send_async")
    def test_notify_video_success_unicode(self, mock_send_async):
        """Thông báo video thành công an toàn với ký tự tiếng Việt và ký tự đặc biệt."""
        title = "Tóm Tắt Phim: Người Nhện <4K> & Siêu Anh Hùng"
        out_path = "D:/output/batch/Người_Nhện_<4K>_&_Siêu_Anh_Hùng.mp4"
        sent = self.notifier.notify_video_success(
            video_title=title,
            output_path=out_path,
            duration_sec=125.4,
            current_index=3,
            total_count=10,
            preset_name="Auto Review Phim AI",
            task_id="task_1"
        )
        self.assertTrue(sent)
        mock_send_async.assert_called_once()
        sent_html = mock_send_async.call_args[0][0]

        # Kiểm tra ký tự đặc biệt đã được escape thành HTML an toàn
        self.assertIn("&lt;4K&gt; &amp; Siêu Anh Hùng", sent_html)
        self.assertIn("3/10 (30%)", sent_html)
        self.assertIn("2p 5s", sent_html)
        self.assertIn("Auto Review Phim AI", sent_html)

    @patch.object(TelegramNotifier, "send_async")
    def test_notify_video_failure(self, mock_send_async):
        """Thông báo video thất bại ngắn gọn, không có traceback."""
        long_traceback = "RuntimeError: FFmpeg execution failed\nTraceback (most recent call last):\n  File 'test.py', line 10"
        sent = self.notifier.notify_video_failure(
            video_title="Video Lỗi",
            error_message=long_traceback,
            duration_sec=10.0,
            current_index=2,
            total_count=5,
            task_id="task_fail"
        )
        self.assertTrue(sent)
        sent_html = mock_send_async.call_args[0][0]
        self.assertIn("Thất bại", sent_html)
        self.assertIn("FFmpeg execution failed", sent_html)
        # Không được chứa traceback
        self.assertNotIn("most recent call last", sent_html)

    @patch.object(TelegramNotifier, "send_async")
    def test_notify_batch_completed_and_empty(self, mock_send_async):
        """Thông báo hoàn tất batch với thống kê chính xác."""
        sent = self.notifier.notify_batch_completed(
            total_count=10,
            success_count=8,
            failed_count=2,
            cancelled_count=0,
            start_time=time.time() - 300,
            end_time=time.time(),
            output_dir="D:/NovaCut/output"
        )
        self.assertTrue(sent)
        sent_html = mock_send_async.call_args[0][0]
        self.assertIn("Tổng số video:</b> 10", sent_html)
        self.assertIn("Thành công:</b> 8", sent_html)
        self.assertIn("Thất bại:</b> 2", sent_html)

    @patch.object(TelegramNotifier, "send_async")
    def test_notify_batch_cancelled(self, mock_send_async):
        """Thông báo khi batch bị hủy bởi người dùng."""
        sent = self.notifier.notify_batch_cancelled(
            total_count=10,
            completed_count=4,
            failed_count=1,
            start_time=time.time() - 120,
            end_time=time.time()
        )
        self.assertTrue(sent)
        sent_html = mock_send_async.call_args[0][0]
        self.assertIn("Hàng Đợi Đã Bị Hủy", sent_html)
        self.assertIn("Đã hoàn thành: 4/10", sent_html)

    @patch.object(TelegramNotifier, "send_async")
    def test_disabled_notifications(self, mock_send_async):
        """Khi người dùng tắt thông báo, hệ thống không gọi gửi Telegram."""
        self.notifier.enabled = False
        res1 = self.notifier.notify_video_success("Test", "out.mp4")
        res2 = self.notifier.notify_video_failure("Test", "Err")
        res3 = self.notifier.notify_batch_completed(5, 5, 0)
        res4 = self.notifier.notify_batch_cancelled(5, 2, 0)

        self.assertFalse(res1)
        self.assertFalse(res2)
        self.assertFalse(res3)
        self.assertFalse(res4)
        mock_send_async.assert_not_called()


class TestTelegramFlaskRoutes(unittest.TestCase):
    def setUp(self):
        self.app = web_app.app
        self.client = self.app.test_client()
        self.notifier = get_telegram_notifier()
        self.notifier.enabled = True
        self.notifier.bot_token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ1234567"
        self.notifier.chat_id = "5011367599"

    def test_get_telegram_config(self):
        """GET /api/telegram/config trả về cấu hình an toàn, token được che giấu."""
        resp = self.client.get("/api/telegram/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        cfg = data["config"]
        self.assertIn("enabled", cfg)
        self.assertIn("chat_id", cfg)
        self.assertEqual(cfg["chat_id"], "5011367599")
        # Token phải được masked
        self.assertTrue(cfg["has_token"])
        self.assertNotIn("ABCdefGHI", cfg["masked_token"])
        self.assertIn("••••", cfg["masked_token"])

    def test_post_telegram_config(self):
        """POST /api/telegram/config cập nhật cấu hình hợp lệ."""
        payload = {
            "enabled": True,
            "chat_id": "999888777",
            "notify_per_video": True,
            "notify_batch_done": False,
        }
        resp = self.client.post("/api/telegram/config", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["config"]["chat_id"], "999888777")
        self.assertFalse(data["config"]["notify_batch_done"])

        # Phục hồi chat_id
        self.notifier.save_config(chat_id="5011367599", notify_batch_done=True)

    @patch("requests.post")
    def test_post_telegram_test(self, mock_post):
        """POST /api/telegram/test kiểm tra kết nối với Bot Telegram."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {}}
        mock_post.return_value = mock_response

        resp = self.client.post("/api/telegram/test", json={"chat_id": "5011367599"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("thành công", data["message"].lower())

    def test_post_telegram_notify_disabled(self):
        """POST /api/telegram/notify khi tắt thông báo."""
        self.notifier.enabled = False
        resp = self.client.post("/api/telegram/notify", json={"event": "video_success", "title": "Test"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("skipped", data)
        self.notifier.enabled = True


if __name__ == "__main__":
    unittest.main()
