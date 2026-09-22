# -*- coding: utf-8 -*-
"""
Bộ kiểm thử tự động toàn diện cho mô-đun Social Media Video Publisher (NovaCut).
Kiểm thử các thành phần:
1. social_publisher.py (Core engine, hashtags parser, content preparer, profile scanner, history manager)
2. routes/social_publish.py (Tất cả 6 API endpoint: platforms, profiles, prepare, open, status, history)
3. Các trường hợp ngoại lệ: Platform không tồn tại, Video file không tồn tại, định dạng cấm, lỗi bản quyền 403.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Nạp thư mục gốc vào sys.path
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import social_publisher
from flask import Flask
from routes.social_publish import social_publish_bp
import license_manager


class TestSocialPublisherCore(unittest.TestCase):
    """Kiểm thử tầng Core Logic social_publisher.py"""

    def test_clean_hashtags(self):
        """Kiểm thử chuẩn hóa hashtags từ chuỗi và mảng."""
        self.assertEqual(social_publisher.clean_hashtags(""), "")
        self.assertEqual(social_publisher.clean_hashtags(None), "")
        
        # Chuỗi phân cách dấu phẩy và khoảng trắng
        cleaned = social_publisher.clean_hashtags("reviewphim, phimhay  #shorts")
        self.assertIn("#reviewphim", cleaned)
        self.assertIn("#phimhay", cleaned)
        self.assertIn("#shorts", cleaned)

        # Mảng
        cleaned_arr = social_publisher.clean_hashtags(["tiktok", "#reels", "novacut"])
        self.assertEqual(cleaned_arr, "#tiktok #reels #novacut")

    def test_prepare_publish_content_youtube(self):
        """Kiểm thử chuẩn bị nội dung cho YouTube Studio (Có tiêu đề riêng)."""
        prep = social_publisher.prepare_publish_content(
            platform_id="youtube",
            title="Review Phim Kinh Dị Siêu Hay",
            description="Tóm tắt nội dung kịch tính",
            hashtags="#reviewphim #shorts",
            privacy="public"
        )
        self.assertEqual(prep["platform_id"], "youtube")
        self.assertEqual(prep["title"], "Review Phim Kinh Dị Siêu Hay")
        self.assertIn("Tóm tắt nội dung kịch tính", prep["description"])
        self.assertIn("#reviewphim", prep["description"])
        self.assertEqual(prep["privacy"], "public")
        self.assertEqual(len(prep["warnings"]), 0)

    def test_prepare_publish_content_tiktok(self):
        """Kiểm thử chuẩn bị nội dung cho TikTok Studio (Gộp caption)."""
        prep = social_publisher.prepare_publish_content(
            platform_id="tiktok",
            caption="Phim này cuốn quá mọi người ơi",
            hashtags="#tiktok #phimhay",
            privacy="friends"
        )
        self.assertEqual(prep["platform_id"], "tiktok")
        self.assertEqual(prep["title"], "")  # TikTok không tách riêng title
        self.assertIn("Phim này cuốn quá mọi người ơi", prep["caption"])
        self.assertIn("#tiktok", prep["caption"])
        self.assertEqual(prep["privacy"], "friends")

    def test_prepare_publish_content_invalid_platform(self):
        """Kiểm thử nạp nền tảng không hợp lệ."""
        with self.assertRaises(ValueError):
            social_publisher.prepare_publish_content(platform_id="non_existent_platform")

    def test_prepare_publish_content_warnings_length(self):
        """Kiểm thử cảnh báo khi nội dung vượt quá số ký tự cho phép."""
        long_title = "A" * 150  # YouTube max 100
        prep = social_publisher.prepare_publish_content(
            platform_id="youtube",
            title=long_title,
            description="Short desc"
        )
        self.assertTrue(len(prep["warnings"]) > 0)
        self.assertIn("vượt quá giới hạn", prep["warnings"][0])

    def test_chrome_executable_and_profiles(self):
        """Kiểm thử tìm Chrome và quét danh sách profile không gây crash."""
        chrome = social_publisher.find_chrome_executable()
        # Không bắt buộc máy test có Chrome, nhưng hàm không được crash
        self.assertTrue(chrome is None or isinstance(chrome, str))

        profiles = social_publisher.list_chrome_profiles()
        self.assertIsInstance(profiles, list)
        self.assertTrue(len(profiles) >= 1)
        self.assertIn("id", profiles[0])
        self.assertIn("display_name", profiles[0])

    def test_publish_history_io(self):
        """Kiểm thử ghi và đọc lịch sử thao tác an toàn."""
        entry = social_publisher.record_publish_action(
            platform_id="youtube",
            video_path=os.path.join(APP_DIR, "output", "test_video.mp4"),
            title="Video Test UnitTest",
            profile_id="Default",
            privacy="public",
            status="OPENED"
        )
        self.assertIn("id", entry)
        self.assertEqual(entry["title"], "Video Test UnitTest")

        history = social_publisher.load_publish_history()
        self.assertIsInstance(history, list)
        self.assertTrue(any(item.get("id") == entry["id"] for item in history))


class TestSocialPublisherRoutes(unittest.TestCase):
    """Kiểm thử các Flask API Route trong routes/social_publish.py"""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(social_publish_bp)
        self.client = self.app.test_client()

    def test_api_platforms(self):
        """GET /api/social/platforms"""
        res = self.client.get("/api/social/platforms")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["platforms"], list)
        plat_ids = [p["id"] for p in data["platforms"]]
        self.assertIn("youtube", plat_ids)
        self.assertIn("tiktok", plat_ids)
        self.assertIn("facebook", plat_ids)
        self.assertIn("instagram", plat_ids)

    def test_api_profiles(self):
        """GET /api/social/profiles"""
        res = self.client.get("/api/social/profiles")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("chrome_installed", data)
        self.assertIn("profiles", data)

    def test_api_prepare_valid(self):
        """POST /api/social/prepare với dữ liệu hợp lệ"""
        payload = {
            "platform_id": "youtube",
            "title": "Tập 1 - Review Phim Chiến Tranh",
            "description": "Nội dung hấp dẫn",
            "hashtags": "#phimhay #shorts",
            "privacy": "unlisted"
        }
        res = self.client.post("/api/social/prepare", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["prepared"]["privacy"], "unlisted")
        self.assertIn("Tập 1", data["prepared"]["title"])

    def test_api_prepare_invalid_platform(self):
        """POST /api/social/prepare với platform sai -> 400"""
        payload = {"platform_id": "unknown_app"}
        res = self.client.post("/api/social/prepare", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_api_prepare_invalid_extension(self):
        """POST /api/social/prepare với file không phải video -> 400"""
        payload = {
            "platform_id": "youtube",
            "video_path": os.path.join(APP_DIR, "license_manager.py")  # File .py không phải video
        }
        res = self.client.post("/api/social/prepare", json=payload)
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("không được hỗ trợ", data["error"])

    def test_api_prepare_nonexistent_file(self):
        """POST /api/social/prepare với file không tồn tại -> 404"""
        payload = {
            "platform_id": "youtube",
            "video_path": os.path.join(APP_DIR, "output", "non_existent_file_xyz123.mp4")
        }
        res = self.client.post("/api/social/prepare", json=payload)
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertIn("không tồn tại", data["error"])

    @patch("license_manager.check_permission")
    def test_api_open_unlicensed_permission_denied(self, mock_perm):
        """POST /api/social/open khi chưa có bản quyền -> 403 Forbidden"""
        mock_perm.return_value = (False, "Ứng dụng chưa được kích hoạt bản quyền!", {})
        res = self.client.post("/api/social/open", json={"platform_id": "youtube"})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data.get("license_error", False))

    @patch("license_manager.check_permission")
    @patch("social_publisher.launch_chrome_with_profile")
    def test_api_open_success_mocked(self, mock_launch, mock_perm):
        """POST /api/social/open khi có bản quyền và mở Chrome thành công"""
        mock_perm.return_value = (True, "OK", {})
        mock_launch.return_value = (True, "Đã mở Chrome thành công.")

        payload = {
            "platform_id": "youtube",
            "profile_id": "Default",
            "title": "Video Demo Thành Công",
            "caption": "Mô tả",
            "copy_video_path": False
        }
        res = self.client.post("/api/social/open", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["platform_id"], "youtube")
        self.assertIn("history_entry", data)

    def test_api_status(self):
        """GET /api/social/status"""
        res = self.client.get("/api/social/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("supported_platforms_count", data)

    def test_api_history_and_clear(self):
        """GET /api/social/history & POST /api/social/history/clear"""
        # Đọc lịch sử
        res = self.client.get("/api/social/history")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["history"], list)

        # Xóa lịch sử
        res_clear = self.client.post("/api/social/history/clear")
        self.assertEqual(res_clear.status_code, 200)
        data_clear = res_clear.get_json()
        self.assertTrue(data_clear["success"])

        # Kiểm tra lại lịch sử đã rỗng
        res_after = self.client.get("/api/social/history")
        self.assertEqual(res_after.get_json()["total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
