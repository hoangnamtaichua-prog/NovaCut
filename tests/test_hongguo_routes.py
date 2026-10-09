# -*- coding: utf-8 -*-
"""
Unit and integration tests for routes/hongguo.py.
Tests Flask blueprint routes, dual-layer license protection (403), request forwarding,
and security path registration.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from web_app import app


class TestHongguoRoutes(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch('license_manager.check_permission')
    def test_license_forbidden_on_all_endpoints(self, mock_perm):
        """Rule 3 Enforcement: If unlicensed, ALL Hongguo API endpoints return 403 Forbidden."""
        mock_perm.return_value = (False, "⚠️ Bản quyền đã hết hạn! Vui lòng gia hạn gói.", {"status": "EXPIRED"})

        endpoints = [
            ("GET", "/api/hongguo/status", None),
            ("POST", "/api/hongguo/start", {}),
            ("POST", "/api/hongguo/stop", {}),
            ("POST", "/api/hongguo/resolve", {"text": "https://drama.com/1"}),
            ("GET", "/api/hongguo/episodes?series_id=123", None),
            ("GET", "/api/hongguo/drama-detail?series_id=123", None),
            ("POST", "/api/hongguo/submit", {"series_ids": ["123"], "episodes": [1, 2]}),
            ("GET", "/api/hongguo/tasks", None),
            ("POST", "/api/hongguo/cancel", {}),
            ("GET", "/api/hongguo/library", None),
            ("GET", "/api/hongguo/library/episodes?name=TestDrama", None),
            ("POST", "/api/hongguo/open-folder", {}),
        ]

        for method, url, body in endpoints:
            if method == "POST":
                res = self.client.post(url, json=body or {})
            else:
                res = self.client.get(url)

            self.assertEqual(
                res.status_code, 403,
                f"Endpoint {method} {url} failed to reject unlicensed request with 403"
            )
            data = res.get_json()
            self.assertFalse(data.get("success"))
            self.assertTrue(data.get("license_error", True))
            self.assertIn("hết hạn", data.get("error", ""))

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_status_endpoint_authorized(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {"status": "ACTIVE"})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "installed": True,
            "tool_dir": r"D:\Tool\Hongguo Downloader",
            "signer_running": True,
            "signer_port": 9099,
            "server_running": True,
            "server_port": 8000,
            "output_dir": r"D:\Videos\Hongguo",
            "error": None
        }
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["signer_port"], 9099)
        self.assertEqual(data["data"]["server_port"], 8000)

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_start_endpoint_authorized(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.start_services.return_value = (True, "Services started successfully")
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": r"D:\Videos\Hongguo"}
        mock_get_mgr.return_value = mock_mgr

        res = self.client.post('/api/hongguo/start')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("started", data["message"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_stop_endpoint_authorized(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.stop_services.return_value = (True, "Services stopped")
        mock_mgr.get_status.return_value = {"server_running": False}
        mock_get_mgr.return_value = mock_mgr

        res = self.client.post('/api/hongguo/stop')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("stopped", data["message"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_resolve_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "ok": True,
            "resolved": [{"series_id": "745678", "title": "Bá Đạo Tổng Tài", "total": 80}]
        })
        mock_get_mgr.return_value = mock_mgr

        res = self.client.post('/api/hongguo/resolve', json={"text": "https://url.test/745678"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["resolved"][0]["title"], "Bá Đạo Tổng Tài")

    @patch('license_manager.check_permission')
    def test_resolve_empty_text_returns_400(self, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        res = self.client.post('/api/hongguo/resolve', json={"text": ""})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_episodes_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "title": "Bá Đạo Tổng Tài",
            "episodes": [1, 2, 3],
            "total": 80
        })
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/episodes?series_id=745678')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["episodes"]), 3)

    @patch('license_manager.check_permission')
    def test_episodes_missing_id_returns_400(self, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        res = self.client.get('/api/hongguo/episodes')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_drama_detail_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "series_id": "745678",
            "series_name": "Bá Đạo Tổng Tài",
            "episode_cnt": 80
        })
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/drama-detail?series_id=745678')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["series_name"], "Bá Đạo Tổng Tài")

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_submit_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": r"D:\Videos\Hongguo"}
        mock_mgr.forward_request.return_value = (200, {"task_id": "task_001"})
        mock_get_mgr.return_value = mock_mgr

        res = self.client.post('/api/hongguo/submit', json={"series_ids": ["745678"]})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    @patch('license_manager.check_permission')
    def test_submit_missing_series_returns_400(self, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        res = self.client.post('/api/hongguo/submit', json={})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_tasks_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "running": True,
            "series": {"title": "Bá Đạo Tổng Tài", "done": 10, "total": 80},
            "log": ["Downloaded episode 10"]
        })
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/tasks')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["running"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    def test_cancel_forwarding(self, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {"message": "Cancelled"})
        mock_get_mgr.return_value = mock_mgr

        res = self.client.post('/api/hongguo/cancel')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    @patch('routes.security.register_user_path')
    def test_security_path_registration_on_submit_and_library(self, mock_reg_path, mock_get_mgr, mock_perm):
        """Verifies that output video directories are registered in routes.security for HTML5 preview."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.forward_request.return_value = (200, {
            "items": [{"name": "Test Drama", "path": r"D:\Videos\Hongguo\Test Drama"}]
        })
        mock_mgr.get_status.return_value = {"output_dir": r"D:\Videos\Hongguo", "server_running": True}
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/library')
        self.assertEqual(res.status_code, 200)
        mock_reg_path.assert_called()

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    @patch('routes.security.register_user_path')
    def test_library_episodes_endpoint(self, mock_reg_path, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.forward_request.return_value = (200, {
            "episodes": [{"name": "01.mp4", "path": r"D:\Videos\Hongguo\Drama\01.mp4", "size": 1024, "ep_num": 1}]
        })
        mock_mgr.get_status.return_value = {"output_dir": r"D:\Videos\Hongguo", "server_running": True}
        mock_get_mgr.return_value = mock_mgr

        res = self.client.get('/api/hongguo/library/episodes?name=Drama')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["episodes"]), 1)
        mock_reg_path.assert_called()

    @patch('license_manager.check_permission')
    @patch('services.hongguo_service.get_service_manager')
    @patch('routes.security.register_user_path')
    def test_open_folder_endpoint(self, mock_reg_path, mock_get_mgr, mock_perm):
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": r"D:\Videos\Hongguo"}
        mock_get_mgr.return_value = mock_mgr

        with patch('os.startfile', create=True) as mock_startfile:
            res = self.client.post('/api/hongguo/open-folder', json={})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            mock_reg_path.assert_called()


if __name__ == '__main__':
    unittest.main()
