# -*- coding: utf-8 -*-
"""
Unit tests for services/hongguo_service.py.
Completely decoupled from Flask and web_app.py.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure repo root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.hongguo_service import HongguoServiceManager, get_service_manager


class TestHongguoServiceManager(unittest.TestCase):

    def setUp(self):
        self.mgr = HongguoServiceManager(tool_dir=r"D:\Tool\Hongguo Downloader")

    def tearDown(self):
        self.mgr.stop_services()

    @patch('os.path.isdir')
    def test_detect_tool_directory_present(self, mock_isdir):
        mock_isdir.return_value = True
        self.assertTrue(self.mgr.is_installed())

    @patch('os.path.isdir')
    def test_detect_tool_directory_missing(self, mock_isdir):
        mock_isdir.return_value = False
        self.assertFalse(self.mgr.is_installed())
        status = self.mgr.get_status()
        self.assertFalse(status['installed'])
        self.assertIn("not found", status['error'].lower())

    @patch('os.path.exists')
    def test_verify_runtime_all_present(self, mock_exists):
        mock_exists.return_value = True
        ok, msg = self.mgr.verify_runtime()
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    @patch('os.path.exists')
    def test_verify_runtime_missing_java(self, mock_exists):
        def side_effect(path):
            if "java.exe" in path:
                return False
            return True
        mock_exists.side_effect = side_effect
        ok, msg = self.mgr.verify_runtime()
        self.assertFalse(ok)
        self.assertIn("java", msg.lower())

    @patch('os.path.exists')
    def test_verify_runtime_missing_jar(self, mock_exists):
        def side_effect(path):
            if "unidbg-sign.jar" in path:
                return False
            return True
        mock_exists.side_effect = side_effect
        ok, msg = self.mgr.verify_runtime()
        self.assertFalse(ok)
        self.assertIn("unidbg", msg.lower())

    @patch('socket.socket')
    def test_port_detection(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        # When connect succeeds: port is open
        mock_sock.connect.return_value = None
        self.assertTrue(self.mgr.port_open(9099))

        # When connect raises: port is closed
        mock_sock.connect.side_effect = ConnectionRefusedError()
        self.assertFalse(self.mgr.port_open(9099))

    @patch.object(HongguoServiceManager, 'port_open')
    @patch.object(HongguoServiceManager, 'is_port_bindable')
    def test_select_port_occupied_fallback(self, mock_bindable, mock_open):
        # Default port 9099 is occupied and not bindable
        def port_open_side(p, host="127.0.0.1"):
            return False
        def bindable_side(p, host="127.0.0.1"):
            return p == 8766  # First available fallback

        mock_open.side_effect = port_open_side
        mock_bindable.side_effect = bindable_side

        selected = self.mgr.select_port("HG_SIGN_PORT", 9099, [8766, 8765, 9599])
        self.assertEqual(selected, 8766)

    @patch('subprocess.Popen')
    @patch.object(HongguoServiceManager, 'check_signer_health', return_value=False)
    @patch.object(HongguoServiceManager, 'check_server_health', return_value=False)
    @patch.object(HongguoServiceManager, 'verify_runtime')
    @patch.object(HongguoServiceManager, 'wait_port')
    def test_start_services_success(self, mock_wait, mock_verify, mock_srv_health, mock_sign_health, mock_popen):
        mock_verify.return_value = (True, "")
        mock_wait.return_value = True

        p1 = MagicMock()
        p1.poll.return_value = None
        p1.pid = 1001

        p2 = MagicMock()
        p2.poll.return_value = None
        p2.pid = 1002

        mock_popen.side_effect = [p1, p2]

        ok, msg = self.mgr.start_services()
        self.assertTrue(ok)
        self.assertEqual(mock_popen.call_count, 2)

    @patch('subprocess.Popen')
    @patch.object(HongguoServiceManager, 'check_signer_health', return_value=False)
    @patch.object(HongguoServiceManager, 'verify_runtime')
    @patch.object(HongguoServiceManager, 'wait_port')
    def test_start_services_java_failure(self, mock_wait, mock_verify, mock_sign_health, mock_popen):
        mock_verify.return_value = (True, "")
        # Signer fails to open port
        mock_wait.return_value = False

        dead_p = MagicMock()
        dead_p.poll.return_value = 1
        dead_p.pid = 1001
        dead_p.stderr.read.return_value = b"Out of memory"
        mock_popen.return_value = dead_p

        ok, msg = self.mgr.start_services()
        self.assertFalse(ok)
        self.assertIn("signer", msg.lower())
        dead_p.terminate.assert_called()

    @patch('subprocess.Popen')
    @patch.object(HongguoServiceManager, 'check_signer_health', return_value=False)
    @patch.object(HongguoServiceManager, 'check_server_health', return_value=False)
    @patch.object(HongguoServiceManager, 'verify_runtime')
    @patch.object(HongguoServiceManager, 'wait_port')
    def test_start_services_python_failure(self, mock_wait, mock_verify, mock_srv_health, mock_sign_health, mock_popen):
        mock_verify.return_value = (True, "")
        # Java signer succeeds, server fails
        mock_wait.side_effect = [True, False]

        java_p = MagicMock()
        java_p.poll.return_value = None
        java_p.pid = 1001

        server_p = MagicMock()
        server_p.poll.return_value = 1
        server_p.pid = 1002
        mock_popen.side_effect = [java_p, server_p]

        ok, msg = self.mgr.start_services()
        self.assertFalse(ok)
        self.assertIn("server", msg.lower())
        # Crucial: Java process must be terminated when server fails
        java_p.terminate.assert_called()

    def test_stop_services_clean(self):
        p1 = MagicMock()
        p1.poll.return_value = None
        p2 = MagicMock()
        p2.poll.return_value = None
        self.mgr._procs = [p1, p2]

        ok, msg = self.mgr.stop_services()
        self.assertTrue(ok)
        p1.terminate.assert_called()
        p2.terminate.assert_called()
        self.assertEqual(len(self.mgr._procs), 0)

    @patch.object(HongguoServiceManager, 'check_server_health', return_value=True)
    @patch('requests.request')
    def test_forward_request_success(self, mock_req, mock_health):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True, "series_id": "123"}
        mock_req.return_value = mock_resp

        self.mgr.server_port = 8000
        status_code, data = self.mgr.forward_request("POST", "/dl/resolve", json_data={"text": "url"})
        self.assertEqual(status_code, 200)
        self.assertEqual(data["series_id"], "123")

    @patch.object(HongguoServiceManager, 'check_server_health', return_value=True)
    @patch('requests.request')
    def test_forward_request_connection_error(self, mock_req, mock_health):
        import requests
        mock_req.side_effect = requests.exceptions.ConnectionError("Connection refused")

        self.mgr.server_port = 8000
        status_code, data = self.mgr.forward_request("GET", "/dl/status")
        self.assertEqual(status_code, 502)
        self.assertIn("error", data)

    @patch.object(HongguoServiceManager, 'check_server_health', return_value=True)
    @patch('requests.request')
    def test_forward_request_timeout(self, mock_req, mock_health):
        import requests
        mock_req.side_effect = requests.exceptions.Timeout("Connection timed out")

        self.mgr.server_port = 8000
        status_code, data = self.mgr.forward_request("GET", "/dl/status")
        self.assertEqual(status_code, 504)
        self.assertIn("error", data)

    def test_job_object_creation_windows(self):
        if os.name == 'nt':
            h_job = self.mgr._init_job_object()
            self.assertIsNotNone(h_job)
            self.mgr.stop_services()
            self.assertIsNone(self.mgr._job_handle)


if __name__ == '__main__':
    unittest.main()
