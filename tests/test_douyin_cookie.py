# -*- coding: utf-8 -*-
"""
Unit tests for Douyin Cookie & Account Manager (douyin_cookie_manager.py)
"""

import os
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import douyin_cookie_manager


class TestDouyinCookieManager(unittest.TestCase):

    def setUp(self):
        # Thiết lập file cookie tạm thời để không ảnh hưởng dữ liệu thật
        self.tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self.tmp_file.close()
        self.orig_cookie_file = douyin_cookie_manager.DOUYIN_COOKIE_FILE
        douyin_cookie_manager.DOUYIN_COOKIE_FILE = self.tmp_file.name

    def tearDown(self):
        douyin_cookie_manager.DOUYIN_COOKIE_FILE = self.orig_cookie_file
        if os.path.exists(self.tmp_file.name):
            try:
                os.remove(self.tmp_file.name)
            except Exception:
                pass

    def test_01_format_raw_cookie_string(self):
        raw = "sessionid=abcd1234efgh; passport_csrf_token=tok5678; ttwid=tw9999"
        formatted = douyin_cookie_manager.format_douyin_cookie(raw)
        self.assertIn("sessionid=abcd1234efgh", formatted)
        self.assertIn("passport_csrf_token=tok5678", formatted)
        self.assertIn("ttwid=tw9999", formatted)

    def test_02_format_multiline_cookie(self):
        raw = """
        sessionid=abcd1234efgh
        passport_csrf_token=tok5678
        odin_tt=odin112233
        """
        formatted = douyin_cookie_manager.format_douyin_cookie(raw)
        self.assertIn("sessionid=abcd1234efgh", formatted)
        self.assertIn("passport_csrf_token=tok5678", formatted)
        self.assertIn("odin_tt=odin112233", formatted)

    def test_03_format_json_cookie_editor(self):
        json_cookies = """[
            {"name": "sessionid", "value": "json_sess_123"},
            {"name": "passport_csrf_token", "value": "json_csrf_456"},
            {"name": "ttwid", "value": "json_ttwid_789"}
        ]"""
        formatted = douyin_cookie_manager.format_douyin_cookie(json_cookies)
        self.assertIn("sessionid=json_sess_123", formatted)
        self.assertIn("passport_csrf_token=json_csrf_456", formatted)
        self.assertIn("ttwid=json_ttwid_789", formatted)

    def test_04_format_netscape_cookies(self):
        netscape = """
        # Netscape HTTP Cookie File
        .douyin.com\tTRUE\t/\tFALSE\t1799999999\tsessionid\tnetscape_sess_888
        .douyin.com\tTRUE\t/\tFALSE\t1799999999\tttwid\tnetscape_tw_999
        """
        formatted = douyin_cookie_manager.format_douyin_cookie(netscape)
        self.assertIn("sessionid=netscape_sess_888", formatted)
        self.assertIn("ttwid=netscape_tw_999", formatted)

    def test_05_save_and_read_cookie(self):
        test_c = "sessionid=my_secret_session_id; ttwid=tw_value"
        ok = douyin_cookie_manager.save_douyin_cookie(test_c)
        self.assertTrue(ok)
        self.assertTrue(douyin_cookie_manager.is_douyin_logged_in())

        read_c = douyin_cookie_manager.get_douyin_custom_cookie()
        self.assertIn("sessionid=my_secret_session_id", read_c)

        # Kiểm tra chuyển đổi sang Playwright list
        pw_list = douyin_cookie_manager.get_douyin_cookie_list_for_playwright()
        self.assertEqual(len(pw_list), 2)
        names = [x["name"] for x in pw_list]
        self.assertIn("sessionid", names)
        self.assertIn("ttwid", names)
        for item in pw_list:
            self.assertEqual(item["domain"], ".douyin.com")
            self.assertEqual(item["path"], "/")

        # Xóa cookie
        douyin_cookie_manager.clear_douyin_cookie()
        self.assertFalse(douyin_cookie_manager.is_douyin_logged_in())
        self.assertIsNone(douyin_cookie_manager.get_douyin_custom_cookie())

    @patch("urllib.request.urlopen")
    def test_06_verify_douyin_cookie_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"error_code": 0, "name": "NovaCutTester", "user_id": "12345678", "sec_user_id": "SEC123", "avatar_url": "https://example.com/avatar.jpg"}, "message": "success"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = douyin_cookie_manager.verify_douyin_cookie("sessionid=mock_valid_session")
        self.assertTrue(res["valid"])
        self.assertEqual(res["uname"], "NovaCutTester")
        self.assertEqual(res["user_id"], "12345678")
        self.assertEqual(res["sec_uid"], "SEC123")
        self.assertEqual(res["avatar_url"], "https://example.com/avatar.jpg")

    @patch("urllib.request.urlopen")
    def test_07_verify_douyin_cookie_expired(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"error_code": 1, "description": "\xe4\xbc\x9a\xe8\xaf\x9d\xe8\xbf\x87\xe6\x9c\x9f\xef\xbc\x8c\xe8\xaf\xb7\xe9\x87\x8d\xe6\x96\xb0\xe7\x99\xbb\xe5\xbd\x95"}, "message": "error"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = douyin_cookie_manager.verify_douyin_cookie("sessionid=mock_expired_session")
        self.assertFalse(res["valid"])
        self.assertIn("会话过期", res["description"])

    def test_08_extract_and_save_from_playwright_context(self):
        mock_context = MagicMock()
        mock_context.cookies.return_value = [
            {"name": "sessionid", "value": "pw_sess_999", "domain": ".douyin.com"},
            {"name": "passport_csrf_token", "value": "pw_csrf_888", "domain": ".douyin.com"},
            {"name": "ignored_cookie", "value": "val", "domain": ".other.com"}
        ]
        ok = douyin_cookie_manager.extract_and_save_cookies_from_playwright_context(mock_context)
        self.assertTrue(ok)
        saved = douyin_cookie_manager.get_douyin_custom_cookie()
        self.assertIn("sessionid=pw_sess_999", saved)
        self.assertIn("passport_csrf_token=pw_csrf_888", saved)
        self.assertNotIn("ignored_cookie", saved)


if __name__ == "__main__":
    unittest.main()
