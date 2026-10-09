# -*- coding: utf-8 -*-
"""
Empirical Adversarial & Stress Testing Suite for Hongguo Downloader Backend.
Created by teamwork_preview_challenger_m1_1.

This test harness stress-tests:
1. Dual-layer license enforcement across all 12 Hongguo endpoints under UNLICENSED, CLOCK_TAMPERED, and error conditions.
2. Parameter tampering and validation boundaries (/resolve, /submit, /episodes, /drama-detail).
3. Path traversal vulnerabilities and security root pollution in /library/episodes and /open-folder.
4. Service manager runtime validation, override isolation, and process safety.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from web_app import app
from services.hongguo_service import HongguoServiceManager
from routes.security import _selected_roots, _selection_lock, is_path_allowed


class TestHongguoAdversarial(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    # =========================================================================
    # SUITE 1: LICENSE PERMISSION ENFORCEMENT & BYPASS CHALLENGES
    # =========================================================================

    def test_license_unlicensed_returns_403_all_12_endpoints(self):
        """Rule 3 Verification: Unauthorized client calling ANY /api/hongguo/* endpoint must get 403."""
        with patch('license_manager.check_permission') as mock_perm:
            mock_perm.return_value = (
                False,
                "⚠️ Ứng dụng chưa được kích hoạt bản quyền!",
                {"status": "UNLICENSED", "is_valid": False, "tier": "unlicensed"}
            )

            endpoints = [
                ("GET", "/api/hongguo/status", None),
                ("POST", "/api/hongguo/start", {}),
                ("POST", "/api/hongguo/stop", {}),
                ("POST", "/api/hongguo/resolve", {"text": "https://drama.com"}),
                ("GET", "/api/hongguo/episodes?series_id=100", None),
                ("GET", "/api/hongguo/drama-detail?series_id=100", None),
                ("POST", "/api/hongguo/submit", {"series_ids": ["100"]}),
                ("GET", "/api/hongguo/tasks", None),
                ("POST", "/api/hongguo/cancel", {}),
                ("GET", "/api/hongguo/library", None),
                ("GET", "/api/hongguo/library/episodes?name=Test", None),
                ("POST", "/api/hongguo/open-folder", {"folder": "test"}),
            ]

            for method, url, body in endpoints:
                if method == "POST":
                    resp = self.client.post(url, json=body or {})
                else:
                    resp = self.client.get(url)

                self.assertEqual(
                    resp.status_code, 403,
                    f"CRITICAL DEFECT: Endpoint {method} {url} returned {resp.status_code} instead of 403 Forbidden!"
                )
                data = resp.get_json()
                self.assertIsNotNone(data)
                self.assertFalse(data.get("success"))
                self.assertTrue(data.get("license_error"))

    def test_license_clock_tampered_returns_403(self):
        """Verify CLOCK_TAMPERED state is strictly blocked with 403 and descriptive error."""
        with patch('license_manager.check_permission') as mock_perm:
            mock_perm.return_value = (
                False,
                "⚠️ Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ!",
                {"status": "CLOCK_TAMPERED", "is_valid": False}
            )
            resp = self.client.get("/api/hongguo/status")
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertFalse(data["success"])
            self.assertIn("đồng hồ", data["error"])

    def test_license_check_exception_fails_closed(self):
        """Security Check: Unhandled exceptions during license checks must fail closed (403), never open."""
        with patch('license_manager.check_permission', side_effect=RuntimeError("License store unreachable")):
            resp = self.client.get("/api/hongguo/status")
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertFalse(data["success"])
            self.assertTrue(data["license_error"])

    def test_license_options_preflight_returns_204(self):
        """Verify CORS preflight OPTIONS is allowed through with 204."""
        resp = self.client.open("/api/hongguo/resolve", method="OPTIONS")
        self.assertEqual(resp.status_code, 204)

    # =========================================================================
    # SUITE 2: PARAMETER TAMPERING & INPUT VALIDATION
    # =========================================================================

    def test_resolve_empty_and_whitespace_validation(self):
        """Verify /resolve rejects empty and whitespace-only text with 400 Bad Request."""
        with patch('license_manager.check_permission', return_value=(True, "OK", {})):
            for bad_payload in [{}, {"text": ""}, {"text": "   \n\t  "}]:
                resp = self.client.post("/api/hongguo/resolve", json=bad_payload)
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertFalse(data["success"])

    def test_resolve_null_text_parameter_tampering_defect(self):
        """
        Verify that sending JSON {"text": null} is properly rejected with 400 Bad Request
        and is NOT forwarded as the literal string 'None'.
        """
        with patch('license_manager.check_permission', return_value=(True, "OK", {})):
            with patch('services.hongguo_service.get_service_manager') as mock_mgr:
                mgr = MagicMock()
                mgr.get_status.return_value = {"server_running": True}
                mock_mgr.return_value = mgr

                resp = self.client.post("/api/hongguo/resolve", json={"text": None})
                self.assertEqual(resp.status_code, 400, "Must return 400 Bad Request for null text")
                data = resp.get_json()
                self.assertFalse(data.get("success", True))
                mgr.forward_request.assert_not_called()

    def test_submit_missing_series_validation(self):
        """Verify /submit rejects empty bodies or missing series identifiers with 400 Bad Request."""
        with patch('license_manager.check_permission', return_value=(True, "OK", {})):
            for bad_payload in [{}, {"series_ids": []}, {"series_ids": None}, {"series_ids": "", "series_id": ""}, {"series_ids": [], "series_id": None}]:
                resp = self.client.post("/api/hongguo/submit", json=bad_payload)
                self.assertEqual(resp.status_code, 400)
                data = resp.get_json()
                self.assertFalse(data["success"])

    def test_episodes_and_detail_missing_params(self):
        """Verify /episodes and /drama-detail reject missing or empty series_id with 400."""
        with patch('license_manager.check_permission', return_value=(True, "OK", {})):
            for endpoint in ["/api/hongguo/episodes", "/api/hongguo/drama-detail"]:
                r1 = self.client.get(endpoint)
                self.assertEqual(r1.status_code, 400)
                r2 = self.client.get(f"{endpoint}?series_id=")
                self.assertEqual(r2.status_code, 400)
                r3 = self.client.get(f"{endpoint}?series_id=%20%20%20")
                self.assertEqual(r3.status_code, 400)

    # =========================================================================
    # SUITE 3: PATH TRAVERSAL & SECURITY SANDBOX INTEGRITY
    # =========================================================================

    def test_library_episodes_path_traversal_and_whitelist_pollution(self):
        """
        Verify that path traversal in /library/episodes (e.g. name=../private_vault or ../../)
        is rejected with 400 Bad Request and does NOT pollute _selected_roots.
        """
        with tempfile.TemporaryDirectory() as temp_root:
            out_dir = os.path.join(temp_root, "hongguo_out")
            secret_dir = os.path.join(temp_root, "private_vault")
            os.makedirs(out_dir, exist_ok=True)
            os.makedirs(secret_dir, exist_ok=True)

            secret_file = os.path.join(secret_dir, "classified.txt")
            with open(secret_file, "w") as f:
                f.write("top_secret")

            # Before attack: private_vault is NOT in allowed roots
            self.assertFalse(is_path_allowed(secret_file))

            with patch('license_manager.check_permission', return_value=(True, "OK", {})):
                with patch('services.hongguo_service.get_service_manager') as mock_mgr:
                    mgr = MagicMock()
                    mgr.get_status.return_value = {"server_running": False, "output_dir": out_dir}
                    mock_mgr.return_value = mgr

                    # Exploit traversal attempt: pass ../private_vault as the folder name
                    resp = self.client.get("/api/hongguo/library/episodes?name=../private_vault")
                    self.assertEqual(resp.status_code, 400, "Directory traversal must be rejected with 400")
                    data = resp.get_json()
                    self.assertFalse(data.get("success", True))

                    # Check security boundary impact: private_vault was NOT added to _selected_roots
                    normalized_vault = os.path.normcase(os.path.realpath(secret_dir))
                    with _selection_lock:
                        vault_is_polluted = normalized_vault in _selected_roots

                    self.assertFalse(vault_is_polluted, "Security verified: private_vault was NOT added to _selected_roots")
                    self.assertFalse(is_path_allowed(secret_file), "Security verified: secret file remains forbidden")

    def test_open_folder_arbitrary_whitelist_pollution(self):
        """
        Verify that POST /api/hongguo/open-folder rejects arbitrary untrusted directories
        with 400 Bad Request and does NOT inject them into _selected_roots.
        """
        with tempfile.TemporaryDirectory() as temp_root:
            arbitrary_dir = os.path.join(temp_root, "arbitrary_attacker_dir")
            probe_file = os.path.join(arbitrary_dir, "probe.txt")

            self.assertFalse(is_path_allowed(probe_file))

            with patch('license_manager.check_permission', return_value=(True, "OK", {})):
                with patch('os.startfile', create=True):
                    resp = self.client.post("/api/hongguo/open-folder", json={"folder": arbitrary_dir})
                    self.assertEqual(resp.status_code, 400, "Arbitrary folder must be rejected with 400")
                    data = resp.get_json()
                    self.assertFalse(data.get("success", True))

                    normalized_target = os.path.normcase(os.path.realpath(arbitrary_dir))
                    with _selection_lock:
                        target_is_polluted = normalized_target in _selected_roots

                    self.assertFalse(target_is_polluted, "Security verified: arbitrary folder was NOT added to whitelist")
                    self.assertFalse(is_path_allowed(probe_file), "Security verified: probe file remains forbidden")

    def test_open_folder_invalid_path_syntax_unhandled_500_defect(self):
        """
        Verify that invalid path syntax in /open-folder is caught and returns structured JSON error
        (HTTP 400 or handled 500), never an unhandled HTML 500 crash.
        """
        with patch('license_manager.check_permission', return_value=(True, "OK", {})):
            resp = self.client.post("/api/hongguo/open-folder", json={"folder": "C:\\invalid*dir?"})
            self.assertEqual(resp.status_code, 400)
            self.assertTrue(resp.is_json, "Must return structured JSON, not raw HTML crash page")
            data = resp.get_json()
            self.assertIsNotNone(data)
            self.assertFalse(data.get("success", True))
            self.assertIn("error", data)

    # =========================================================================
    # SUITE 4: SERVICE MANAGER RUNTIME DETECTION & ISOLATION
    # =========================================================================

    def test_service_manager_override_masking_defect(self):
        """
        Verify that passing override_tool_dir with an invalid path maintains strict isolation.
        It must NOT silently fall back to D:\\Tool\\Hongguo Downloader or any host directory.
        """
        invalid_path = r"D:\NonExistent_FakeTool_Dir_9999"
        mgr = HongguoServiceManager(override_tool_dir=invalid_path)
        stat = mgr.get_status()

        self.assertFalse(stat["installed"], "Strict isolation: installed must be False for invalid override_tool_dir")
        self.assertNotEqual(stat["tool_dir"], r"D:\Tool\Hongguo Downloader", "Must NOT silently fall back to host installation")
        self.assertIn("NonExistent_FakeTool_Dir_9999", stat["tool_dir"])
        self.assertIsNotNone(stat.get("error"))
        self.assertIn("not found", stat["error"].lower())

    def test_service_manager_missing_binaries_detection(self):
        """Verify detailed detection of which exact component is missing in a partial directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            jre_bin = os.path.join(temp_dir, "jre", "bin")
            py_dir = os.path.join(temp_dir, "python")
            app_sign = os.path.join(temp_dir, "app", "sign")
            os.makedirs(jre_bin, exist_ok=True)
            os.makedirs(py_dir, exist_ok=True)
            os.makedirs(app_sign, exist_ok=True)

            with open(os.path.join(jre_bin, "java.exe"), "w") as f:
                f.write("mock")
            with open(os.path.join(py_dir, "python.exe"), "w") as f:
                f.write("mock")

            ok, detected_dir, details = HongguoServiceManager.detect_installation(temp_dir)
            self.assertFalse(ok)
            self.assertIn("app/sign/unidbg-sign.jar", details["missing"])
            self.assertIn("app/server_ext.py (or server.pyc)", details["missing"])

    def test_service_manager_stop_services_idempotency(self):
        """Verify calling stop_services repeatedly or when no processes exist never raises."""
        mgr = HongguoServiceManager()
        for _ in range(5):
            ok, msg = mgr.stop_services()
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
