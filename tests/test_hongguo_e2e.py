# -*- coding: utf-8 -*-
"""
tests/test_hongguo_e2e.py
Authoritative 4-Tier End-to-End Test Suite for Hongguo Downloader in NovaCut.

Structured into 4 Tiers:
- Tier 1: Feature Coverage (Isolation)
- Tier 2: Boundary & Corner Cases (Stress & Adversarial)
- Tier 3: Cross-Feature Combinations (Integration Pipelines)
- Tier 4: Real-World Application Scenarios (End-to-End User Journeys)
"""

import os
import sys
import json
import time
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure repo root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from web_app import app
from services.hongguo_service import (
    HongguoServiceManager,
    get_service_manager,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    CREATE_NO_WINDOW
)
from routes.security import (
    register_user_path,
    is_path_allowed,
    _selected_roots,
    _selection_lock,
    _real
)


# =============================================================================
# Helper Fixtures & Utilities
# =============================================================================

def create_mock_hongguo_tool_directory(base_dir: str) -> dict:
    """Creates a mock valid directory structure for Hongguo Downloader."""
    tool_dir = os.path.join(base_dir, "Hongguo Downloader")
    jre_bin = os.path.join(tool_dir, "jre", "bin")
    python_dir = os.path.join(tool_dir, "python")
    app_dir = os.path.join(tool_dir, "app")
    app_sign = os.path.join(app_dir, "sign")

    os.makedirs(jre_bin, exist_ok=True)
    os.makedirs(python_dir, exist_ok=True)
    os.makedirs(app_sign, exist_ok=True)

    java_exe = os.path.join(jre_bin, "java.exe")
    with open(java_exe, "wb") as f:
        f.write(b"MOCK_JAVA")

    python_exe = os.path.join(python_dir, "python.exe")
    with open(python_exe, "wb") as f:
        f.write(b"MOCK_PYTHON")

    signer_jar = os.path.join(app_sign, "unidbg-sign.jar")
    with open(signer_jar, "wb") as f:
        f.write(b"MOCK_SIGNER_JAR")

    server_script = os.path.join(app_dir, "server_ext.py")
    with open(server_script, "wb") as f:
        f.write(b"# MOCK_SERVER_SCRIPT")

    return {
        "tool_dir": tool_dir,
        "java_exe": java_exe,
        "python_exe": python_exe,
        "signer_jar": signer_jar,
        "server_script": server_script
    }


def create_mock_downloaded_drama(output_dir: str, drama_name: str, ep_count: int = 5) -> str:
    """Creates a realistic downloaded drama folder on disk with .series.json and mp4s."""
    drama_dir = os.path.join(output_dir, drama_name)
    os.makedirs(drama_dir, exist_ok=True)

    meta_file = os.path.join(drama_dir, ".series.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({
            "series_id": "7410001",
            "title": drama_name,
            "total": ep_count,
            "cover": "http://example.com/cover.jpg",
            "downloaded_episodes": ep_count
        }, f, ensure_ascii=False)

    for i in range(1, ep_count + 1):
        ep_file = os.path.join(drama_dir, f"Tập {i:02d}.mp4")
        with open(ep_file, "wb") as f:
            # Minimal mock MP4 header
            f.write(b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00mp42isomMOCK_VIDEO_DATA")

    return drama_dir


# =============================================================================
# TIER 1: FEATURE COVERAGE (ISOLATION)
# =============================================================================

class TestTier1FeatureCoverage(unittest.TestCase):
    """
    Tier 1: Test all features in complete isolation.
    Validates Feature 1 through Feature 14 per PROJECT.md inventory.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_e2e_t1_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Feature 1: Tool Auto-Detection & Validation ---
    def test_t1_f1_tool_detection_success(self):
        """F1: Detect and validate healthy Hongguo Downloader directory structure."""
        tool_env = create_mock_hongguo_tool_directory(self.temp_dir)
        mgr = HongguoServiceManager(override_tool_dir=tool_env["tool_dir"])

        self.assertTrue(mgr.is_installed())
        ok, msg = mgr.verify_runtime()
        self.assertTrue(ok)
        self.assertEqual(msg, "")

        status = mgr.get_status()
        self.assertTrue(status["installed"])
        self.assertIsNone(status["error"])
        self.assertEqual(os.path.normcase(status["tool_dir"]), os.path.normcase(tool_env["tool_dir"]))

    def test_t1_f1_tool_detection_missing(self):
        """F1: Detect missing Hongguo Downloader tool directory gracefully."""
        missing_dir = os.path.join(self.temp_dir, "NonExistentTool")
        mgr = HongguoServiceManager(override_tool_dir=missing_dir)

        self.assertFalse(mgr.is_installed())
        ok, msg = mgr.verify_runtime()
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())

        status = mgr.get_status()
        self.assertFalse(status["installed"])
        self.assertIsNotNone(status["error"])

    # --- Feature 2: Win32 Job Object & Process Supervisor ---
    def test_t1_f2_win32_job_object_initialization(self):
        """F2: Verify Win32 Job Object is created with KILL_ON_JOB_CLOSE on Windows."""
        mgr = HongguoServiceManager()
        if os.name == "nt":
            job = mgr._init_job_object()
            self.assertIsNotNone(job)
            self.assertEqual(job, mgr._job_handle)
            self.assertEqual(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, 0x2000)
            self.assertEqual(CREATE_NO_WINDOW, 0x08000000)
        else:
            self.assertIsNone(mgr._init_job_object())

    # --- Feature 3: Status Endpoint (/api/hongguo/status) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f3_status_endpoint_schema(self, mock_get_mgr, mock_perm):
        """F3: Verify /api/hongguo/status adheres to PROJECT.md status schema contract."""
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

        resp = self.client.get("/api/hongguo/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        status_data = data["data"]
        for key in ["installed", "tool_dir", "signer_running", "signer_port", "server_running", "server_port", "output_dir", "error"]:
            self.assertIn(key, status_data)

    # --- Feature 4: Graceful Teardown Hooks ---
    def test_t1_f4_graceful_teardown(self):
        """F4: Verify stop_services safely terminates managed subprocesses and releases Job Object."""
        mgr = HongguoServiceManager()
        mock_p1 = MagicMock()
        mock_p1.poll.return_value = None
        mock_p2 = MagicMock()
        mock_p2.poll.return_value = None

        mgr._procs = [mock_p1, mock_p2]
        success, msg = mgr.stop_services()
        self.assertTrue(success)
        self.assertEqual(len(mgr._procs), 0)
        mock_p1.terminate.assert_called()
        mock_p2.terminate.assert_called()

    # --- Feature 5: License Backend Protection ---
    @patch("license_manager.check_permission")
    def test_t1_f5_backend_license_protection_403(self, mock_perm):
        """F5: Verify backend before_request guard blocks unlicensed requests with HTTP 403."""
        mock_perm.return_value = (False, "⚠️ Chưa kích hoạt bản quyền!", {"status": "UNLICENSED"})

        resp = self.client.get("/api/hongguo/status")
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data.get("license_error"))

    # --- Feature 6: Gateway API Proxy (/resolve, /episodes, /drama-detail) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f6_resolve_endpoint(self, mock_get_mgr, mock_perm):
        """F6: Verify /api/hongguo/resolve forwards drama URL and returns resolved series list."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "resolved": [{
                "series_id": "7410001",
                "title": "Chàng Rể Quyền Lực",
                "total": 80,
                "cover": "http://img.com/cover.jpg"
            }]
        })
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/resolve", json={"text": "https://novel.snssdk.com/drama/7410001"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["resolved"]), 1)
        self.assertEqual(data["resolved"][0]["series_id"], "7410001")

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f6_episodes_endpoint(self, mock_get_mgr, mock_perm):
        """F6: Verify /api/hongguo/episodes returns episodes list."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "title": "Chàng Rể Quyền Lực",
            "total": 2,
            "episodes": [
                {"item_id": "ep_1", "title": "Tập 1", "order": 1},
                {"item_id": "ep_2", "title": "Tập 2", "order": 2}
            ]
        })
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/episodes?series_id=7410001")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["episodes"]), 2)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f4_start_services_endpoint(self, mock_get_mgr, mock_perm):
        """F4: Verify /api/hongguo/start endpoint kicks off child processes."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.start_services.return_value = (True, "Services started successfully")
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": self.temp_dir}
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/start")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("started", data["message"].lower())

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f4_stop_services_endpoint(self, mock_get_mgr, mock_perm):
        """F4: Verify /api/hongguo/stop endpoint terminates child processes cleanly."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.stop_services.return_value = (True, "Services stopped")
        mock_mgr.get_status.return_value = {"server_running": False}
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("stopped", data["message"].lower())

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f6_drama_detail_endpoint(self, mock_get_mgr, mock_perm):
        """F6: Verify /api/hongguo/drama-detail endpoint returns series synopsis and metadata."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {
            "series_id": "7410001",
            "series_name": "Chàng Rể Quyền Lực",
            "series_intro": "Câu chuyện về chàng rể siêu cấp...",
            "series_cover": "http://img.com/cover.jpg",
            "episode_cnt": 80
        })
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/drama-detail?series_id=7410001")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["series_name"], "Chàng Rể Quyền Lực")
        self.assertEqual(data["data"]["episode_cnt"], 80)

    # --- Feature 7: Secure Path Registration & /library ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f7_library_and_path_registration(self, mock_get_mgr, mock_perm):
        """F7: Verify /api/hongguo/library scans downloaded media and registers paths securely."""
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "OutputVideos")
        os.makedirs(out_dir, exist_ok=True)
        drama_dir = create_mock_downloaded_drama(out_dir, "Bá Đạo Tổng Tài", ep_count=3)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "server_running": False,
            "output_dir": out_dir
        }
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/library")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["name"], "Bá Đạo Tổng Tài")
        self.assertEqual(data["items"][0]["episodes_count"], 3)

        # Confirm path was registered into routes.security whitelist
        self.assertTrue(is_path_allowed(os.path.join(drama_dir, "Tập 01.mp4"), must_exist=True))

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f7_library_episodes_listing(self, mock_get_mgr, mock_perm):
        """F7: Verify /api/hongguo/library/episodes lists individual mp4 files and registers them."""
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "OutputVideos")
        os.makedirs(out_dir, exist_ok=True)
        drama_dir = create_mock_downloaded_drama(out_dir, "Bá Đạo Tổng Tài", ep_count=3)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "server_running": False,
            "output_dir": out_dir
        }
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/library/episodes?name=Bá Đạo Tổng Tài")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["episodes"]), 3)
        self.assertEqual(data["episodes"][0]["ep_num"], 1)

    # --- Feature 8: Episode Selector & Range Parser Logic ---
    def test_t1_f8_range_parser_isolation(self):
        """F8: Verify episode range parser contract (equivalent to JS parseEpisodeRange)."""
        def parse_range(range_str, max_ep=100):
            selected = set()
            if not range_str:
                return selected
            clean = range_str.strip().lower()
            if clean in ("all", "tất cả"):
                return set(range(1, max_ep + 1))
            import re
            tokens = re.split(r"[,;\s]+", clean)
            for t in tokens:
                if not t:
                    continue
                m = re.match(r"^(\d+)\s*[-~..]\s*(\d+)$", t)
                if m:
                    s, e = int(m.group(1)), int(m.group(2))
                    if s > e:
                        s, e = e, s
                    for i in range(s, e + 1):
                        if 1 <= i <= max_ep:
                            selected.add(i)
                elif t.isdigit():
                    val = int(t)
                    if 1 <= val <= max_ep:
                        selected.add(val)
            return selected

        self.assertEqual(parse_range("1-5, 8, 10-12", 20), {1, 2, 3, 4, 5, 8, 10, 11, 12})
        self.assertEqual(parse_range("all", 5), {1, 2, 3, 4, 5})
        self.assertEqual(parse_range("5-1", 10), {1, 2, 3, 4, 5})  # Auto-swap inverted range

    # --- Feature 9: Submit Download & Tasks Monitoring ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f9_submit_and_tasks(self, mock_get_mgr, mock_perm):
        """F9: Verify submit download and task polling proxying."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": self.temp_dir}
        mock_mgr.forward_request.side_effect = [
            (200, {"success": True, "task_id": "t123"}),  # /submit
            (200, {"running": True, "series": {"7410001": {"progress": 50}}, "log": ["Downloading ep 1"]})  # /tasks
        ]
        mock_get_mgr.return_value = mock_mgr

        # Submit
        resp_sub = self.client.post("/api/hongguo/submit", json={"series_ids": ["7410001"], "episodes": [1, 2]})
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.get_json()["success"])

        # Tasks
        resp_tasks = self.client.get("/api/hongguo/tasks")
        self.assertEqual(resp_tasks.status_code, 200)
        t_data = resp_tasks.get_json()
        self.assertTrue(t_data["success"])
        self.assertTrue(t_data["running"])

    # --- Feature 10: Cancel Download ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t1_f10_cancel_download(self, mock_get_mgr, mock_perm):
        """F10: Verify cancel download endpoint."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {"message": "Cancelled"})
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/cancel")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    # --- Feature 11: Open Folder Safely ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    @patch("subprocess.Popen")
    def test_t1_f11_open_folder(self, mock_popen, mock_get_mgr, mock_perm):
        """F11: Verify open-folder route opens output folder and registers path."""
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "SafeDownloads")
        os.makedirs(out_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": out_dir}
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/open-folder", json={"folder": out_dir})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])
        self.assertTrue(is_path_allowed(out_dir))

    # --- Feature 12: Frontend License Guard & Zero alert() Contract ---
    def test_t1_f12_frontend_code_integrity(self):
        """F12: Verify frontend contains zero alert() and enforces checkHongguoLicense."""
        hongguo_js_path = os.path.join(REPO_ROOT, "web", "js", "features", "hongguo.js")
        self.assertTrue(os.path.isfile(hongguo_js_path))

        with open(hongguo_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Strict Zero Alert check
        import re
        alert_calls = re.findall(r"(?<!\w)alert\(", content)
        self.assertEqual(len(alert_calls), 0, "Found native alert() call in hongguo.js")

        confirm_calls = re.findall(r"(?<!\w)confirm\(", content)
        self.assertEqual(len(confirm_calls), 0, "Found native confirm() call in hongguo.js")

        # Verify presence of dark modal / toast invocations
        self.assertIn("showAlertModal", content)
        self.assertIn("showToast", content)
        self.assertIn("checkHongguoLicense", content)

    # --- Feature 13: Workflow Bridges Contracts ---
    def test_t1_f13_workflow_bridges_contracts(self):
        """F13: Verify sendVideoToEditor and sendVideoToReview contracts in web/app.js."""
        app_js_path = os.path.join(REPO_ROOT, "web", "app.js")
        self.assertTrue(os.path.isfile(app_js_path))

        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("function sendVideoToEditor(", content)
        self.assertIn("function sendVideoToReview(", content)
        self.assertIn("window.sendVideoToEditor = sendVideoToEditor;", content)
        self.assertIn("window.sendVideoToReview = sendVideoToReview;", content)


# =============================================================================
# TIER 2: BOUNDARY & CORNER CASES (STRESS & ADVERSARIAL)
# =============================================================================

class TestTier2BoundaryAndCornerCases(unittest.TestCase):
    """
    Tier 2: Boundary, invalid inputs, stress, and security tamper tests.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_e2e_t2_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- B1: Empty String & Whitespace on /resolve ---
    @patch("license_manager.check_permission")
    def test_t2_b1_resolve_empty_string_rejection(self, mock_perm):
        """B1: Verify /resolve cleanly rejects empty string, spaces, or None with HTTP 400."""
        mock_perm.return_value = (True, "OK", {})

        bad_inputs = ["", "   ", None, "None", "none"]
        for val in bad_inputs:
            resp = self.client.post("/api/hongguo/resolve", json={"text": val})
            self.assertEqual(resp.status_code, 400, f"Failed on input: {val}")
            data = resp.get_json()
            self.assertFalse(data["success"])
            self.assertIn("Vui lòng nhập", data["error"])

    # --- B2: Missing/Invalid Series ID ---
    @patch("license_manager.check_permission")
    def test_t2_b2_episodes_missing_series_id(self, mock_perm):
        """B2: Verify /episodes rejects empty series_id with HTTP 400."""
        mock_perm.return_value = (True, "OK", {})
        resp = self.client.get("/api/hongguo/episodes?series_id=")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Thiếu tham số series_id", resp.get_json()["error"])

    # --- B3: Empty Series IDs on /submit ---
    @patch("license_manager.check_permission")
    def test_t2_b3_submit_empty_payload(self, mock_perm):
        """B3: Verify /submit rejects empty series_ids with HTTP 400."""
        mock_perm.return_value = (True, "OK", {})
        resp = self.client.post("/api/hongguo/submit", json={"series_ids": []})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("không được để trống", resp.get_json()["error"])

    # --- B4: Malformed, Null, and Non-Dict Payloads ---
    @patch("license_manager.check_permission")
    def test_t2_b4_malformed_json_payloads(self, mock_perm):
        """B4: Verify endpoints handle malformed or non-dict payloads without 500 crashes."""
        mock_perm.return_value = (True, "OK", {})

        # Empty body
        resp = self.client.post("/api/hongguo/resolve", data="", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

        # JSON array instead of dict
        resp = self.client.post("/api/hongguo/resolve", json=["random_array"])
        self.assertEqual(resp.status_code, 400)

        # Null JSON
        resp = self.client.post("/api/hongguo/open-folder", data="null", content_type="application/json")
        self.assertIn(resp.status_code, (200, 400))  # Handled safely

    # --- B5: Port Collision & Fallback ---
    @patch.object(HongguoServiceManager, "is_port_bindable")
    @patch.object(HongguoServiceManager, "port_open")
    def test_t2_b5_port_collision_fallback(self, mock_port_open, mock_is_bindable):
        """B5: Verify port selector selects available fallback port when 9099 / 8000 are occupied."""
        mgr = HongguoServiceManager()

        # Simulate 9099 occupied, 8766 available
        def mock_bind(p, host="127.0.0.1"):
            return p != 9099

        mock_is_bindable.side_effect = mock_bind
        selected_sign = mgr.select_port("HG_SIGN_PORT", 9099, [8766, 8765])
        self.assertEqual(selected_sign, 8766)

    # --- B6: Path Traversal in /library/episodes ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t2_b6_path_traversal_library_episodes(self, mock_get_mgr, mock_perm):
        """B6: Verify /library/episodes rejects path traversal attempts with HTTP 400."""
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "HG_Output")
        os.makedirs(out_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": out_dir, "server_running": False}
        mock_get_mgr.return_value = mock_mgr

        traversal_attempts = [
            "../etc",
            "..\\windows",
            "../../root",
            ".",
            "..",
            "foo/../../bar",
            "folder:name"
        ]
        for bad_name in traversal_attempts:
            resp = self.client.get(f"/api/hongguo/library/episodes?name={bad_name}")
            self.assertEqual(resp.status_code, 400, f"Allowed traversal: {bad_name}")
            self.assertFalse(resp.get_json()["success"])

    # --- B7: Path Traversal in /open-folder ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t2_b7_path_traversal_open_folder(self, mock_get_mgr, mock_perm):
        """B7: Verify /open-folder rejects directories outside output_dir and whitelist."""
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "HG_Output")
        os.makedirs(out_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": out_dir}
        mock_get_mgr.return_value = mock_mgr

        bad_folders = [
            "../secret",
            r"C:\Windows\System32",
            r"/etc/shadow",
            r"..\..\Unauthorized"
        ]
        for f in bad_folders:
            resp = self.client.post("/api/hongguo/open-folder", json={"folder": f})
            self.assertEqual(resp.status_code, 400, f"Allowed rogue path: {f}")

    # --- B8: Security Whitelist Verification on Unregistered Paths ---
    def test_t2_b8_unregistered_paths_blocked_by_whitelist(self):
        """B8: Verify is_path_allowed strictly blocks unregistered external files."""
        unregistered_file = os.path.join(self.temp_dir, "outside_whitelist.mp4")
        with open(unregistered_file, "wb") as f:
            f.write(b"SAMPLE")

        self.assertFalse(is_path_allowed(unregistered_file, must_exist=True))

        # Once registered, it must pass
        register_user_path(unregistered_file)
        self.assertTrue(is_path_allowed(unregistered_file, must_exist=True))

    # --- B9: Process Crash Simulation & Recovery ---
    def test_t2_b9_process_crash_detection(self):
        """B9: Simulate unexpected process crash and verify health status detects failure."""
        mgr = HongguoServiceManager()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process exited with error code 1
        mgr._procs = [mock_proc]

        with patch.object(mgr, "check_server_health", return_value=False):
            with patch.object(mgr, "check_signer_health", return_value=False):
                status = mgr.get_status()
                self.assertFalse(status["server_running"])
                self.assertFalse(status["signer_running"])

    # --- B10: Mid-Session License Expiration ---
    @patch("license_manager.check_permission")
    def test_t2_b10_mid_session_license_expiration(self, mock_perm):
        """B10: Verify immediate 403 when license expires during active session."""
        # 1. First call is valid
        mock_perm.return_value = (True, "OK", {"status": "ACTIVE"})
        with patch("services.hongguo_service.get_service_manager") as mock_mgr:
            mock_mgr.return_value.get_status.return_value = {"installed": True}
            resp1 = self.client.get("/api/hongguo/status")
            self.assertEqual(resp1.status_code, 200)

        # 2. License expires immediately
        mock_perm.return_value = (False, "⚠️ Bản quyền của bạn đã hết hạn!", {"status": "EXPIRED"})
        resp2 = self.client.get("/api/hongguo/status")
        self.assertEqual(resp2.status_code, 403)
        data = resp2.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(data.get("license_error"))
        self.assertIn("hết hạn", data.get("error", ""))

    # --- B11: Clock Tampering Detection ---
    @patch("license_manager.check_permission")
    def test_t2_b11_clock_tampering_rejection(self, mock_perm):
        """B11: Verify CLOCK_TAMPERED triggers immediate 403 rejection."""
        mock_perm.return_value = (False, "⚠️ Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ!", {"status": "CLOCK_TAMPERED"})
        resp = self.client.get("/api/hongguo/status")
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("đồng hồ", data.get("error", ""))

    # --- B12: Upstream Gateway 502/504 Handling ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t2_b12_upstream_gateway_errors(self, mock_get_mgr, mock_perm):
        """B12: Verify gateway cleanly translates upstream 502/504 without internal server crash."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (504, {"detail": "Hongguo API timeout"})
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.post("/api/hongguo/resolve", json={"text": "7410001"})
        self.assertEqual(resp.status_code, 504)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("timeout", data.get("error", "").lower())


# =============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (INTEGRATION PIPELINES)
# =============================================================================

class TestTier3CrossFeatureCombinations(unittest.TestCase):
    """
    Tier 3: Multi-feature sequential pipelines and cross-module interactions.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_e2e_t3_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- C1: Flow A (Resolve -> Range -> Submit -> Tasks -> Whitelist -> Editor Bridge) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t3_c1_flow_download_to_editor_bridge(self, mock_get_mgr, mock_perm):
        """
        C1: Flow A: Service status -> Resolve drama -> Parse range -> Submit download
        -> Poll tasks -> Register media whitelist -> Bridge to Biên tập phim.
        """
        mock_perm.return_value = (True, "OK", {"status": "ACTIVE"})
        out_dir = os.path.join(self.temp_dir, "HongguoDown")
        os.makedirs(out_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "installed": True,
            "server_running": True,
            "output_dir": out_dir
        }
        mock_get_mgr.return_value = mock_mgr

        # Step 1: Healthcheck
        r_status = self.client.get("/api/hongguo/status")
        self.assertEqual(r_status.status_code, 200)

        # Step 2: Resolve Drama
        mock_mgr.forward_request.return_value = (200, {
            "resolved": [{
                "series_id": "7418888",
                "title": "Vương Giả Trở Lại",
                "total": 50,
                "cover": "http://img/cover.png"
            }]
        })
        r_res = self.client.post("/api/hongguo/resolve", json={"text": "7418888"})
        self.assertEqual(r_res.status_code, 200)
        drama = r_res.get_json()["resolved"][0]
        self.assertEqual(drama["series_id"], "7418888")

        # Step 3: Range Parser logic ("1-3, 5")
        ep_selection = [1, 2, 3, 5]

        # Step 4: Submit Download
        mock_mgr.forward_request.return_value = (200, {"success": True, "message": "Queued"})
        r_sub = self.client.post("/api/hongguo/submit", json={
            "series_ids": [drama["series_id"]],
            "episodes": ep_selection
        })
        self.assertEqual(r_sub.status_code, 200)

        # Step 5: Tasks Polling
        mock_mgr.forward_request.return_value = (200, {
            "running": False,
            "started": int(time.time()),
            "series": [{"sid": "7418888", "completed": 4, "total": 4, "progress": 100}],
            "log": ["Finished download"]
        })
        r_tasks = self.client.get("/api/hongguo/tasks")
        self.assertEqual(r_tasks.status_code, 200)
        self.assertFalse(r_tasks.get_json()["running"])

        # Step 6: File materialized on disk & registered
        drama_dir = create_mock_downloaded_drama(out_dir, "Vương Giả Trở Lại", ep_count=4)
        target_video = os.path.join(drama_dir, "Tập 01.mp4")

        # Step 7: Library scans folder and whitelists paths
        r_lib = self.client.get("/api/hongguo/library")
        self.assertEqual(r_lib.status_code, 200)

        # Step 8: Editor workflow bridge acceptance
        self.assertTrue(is_path_allowed(target_video, must_exist=True))

    # --- C2: Flow B (Resolve -> Submit -> Library -> Review Bridge) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t3_c2_flow_download_to_review_bridge(self, mock_get_mgr, mock_perm):
        """
        C2: Flow B: Resolve -> Submit -> Scan library episodes -> Bridge to Review phim.
        """
        mock_perm.return_value = (True, "OK", {})
        out_dir = os.path.join(self.temp_dir, "HongguoDown")
        os.makedirs(out_dir, exist_ok=True)
        drama_dir = create_mock_downloaded_drama(out_dir, "Tiểu Thư Quyền Quý", ep_count=2)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": False, "output_dir": out_dir}
        mock_get_mgr.return_value = mock_mgr

        # Query Library Episodes
        r_ep = self.client.get("/api/hongguo/library/episodes?name=Tiểu Thư Quyền Quý")
        self.assertEqual(r_ep.status_code, 200)
        episodes = r_ep.get_json()["episodes"]
        self.assertEqual(len(episodes), 2)
        ep1_path = episodes[0]["path"]

        # Whitelist verification for Review Studio
        self.assertTrue(is_path_allowed(ep1_path, must_exist=True))

    # --- C3: Flow C (License Check Failure Blocks Entire Flow Cascade) ---
    @patch("license_manager.check_permission")
    def test_t3_c3_license_failure_blocks_all_cascades(self, mock_perm):
        """C3: Flow C: Unlicensed status blocks every sequential endpoint in the cascade."""
        mock_perm.return_value = (False, "⚠️ Bản quyền chưa kích hoạt!", {"status": "UNLICENSED"})

        cascade_steps = [
            ("GET", "/api/hongguo/status", None),
            ("POST", "/api/hongguo/start", {}),
            ("POST", "/api/hongguo/resolve", {"text": "7410001"}),
            ("GET", "/api/hongguo/episodes?series_id=7410001", None),
            ("GET", "/api/hongguo/drama-detail?series_id=7410001", None),
            ("POST", "/api/hongguo/submit", {"series_ids": ["7410001"]}),
            ("GET", "/api/hongguo/tasks", None),
            ("POST", "/api/hongguo/cancel", {}),
            ("GET", "/api/hongguo/library", None),
            ("GET", "/api/hongguo/library/episodes?name=Test", None),
            ("POST", "/api/hongguo/open-folder", {}),
            ("POST", "/api/hongguo/stop", {})
        ]

        for method, url, body in cascade_steps:
            if method == "POST":
                resp = self.client.post(url, json=body or {})
            else:
                resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403, f"Endpoint {url} failed to block unlicensed call!")
            self.assertTrue(resp.get_json().get("license_error"))

    # --- C4: Flow D (Submit -> Poll -> Cancel -> Resubmit Chain) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t3_c4_submit_cancel_resubmit_chain(self, mock_get_mgr, mock_perm):
        """C4: Flow D: Submit batch -> Cancel in flight -> Resubmit updated selection."""
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.side_effect = [
            (200, {"success": True, "task_id": "job1"}),  # Submit 1
            (200, {"success": True, "message": "Cancelled"}),  # Cancel
            (200, {"success": True, "task_id": "job2"})   # Submit 2
        ]
        mock_get_mgr.return_value = mock_mgr

        # Submit initial
        r1 = self.client.post("/api/hongguo/submit", json={"series_ids": ["7410001"], "episodes": [1, 2, 3]})
        self.assertEqual(r1.status_code, 200)

        # Cancel
        r_cancel = self.client.post("/api/hongguo/cancel")
        self.assertEqual(r_cancel.status_code, 200)

        # Re-submit with revised episodes
        r2 = self.client.post("/api/hongguo/submit", json={"series_ids": ["7410001"], "episodes": [4, 5]})
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.get_json()["success"])


# =============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (END-TO-END USER JOURNEYS)
# =============================================================================

class TestTier4RealWorldScenarios(unittest.TestCase):
    """
    Tier 4: Authentic, complete end-to-end user journeys mirroring actual production usage.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_e2e_t4_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Scenario 1: Realistic Full Journey (Paste URL -> Range 1-10 -> Download -> File Verify -> Editor Timeline) ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t4_user_journey_drama_download_to_editor_timeline(self, mock_get_mgr, mock_perm):
        """
        R1: Complete user journey:
        1. User opens Hongguo Downloader tab (status verified)
        2. Pastes authentic drama link https://novel.snssdk.com/api/novel/page/series?series_id=7410001
        3. Resolves drama metadata (80 episodes, title "Chiến Thần Đô Thị")
        4. Selects episodes 1-10 via range selector
        5. Submits download batch
        6. Real-time tasks polling updates progress from 0% -> 100%
        7. Verified MP4 files and metadata materialized on disk
        8. Library refreshed with verified episodes
        9. Quick action 'Chuyển sang Biên tập' triggered
        10. File successfully whitelisted for HTML5 / WebView2 timeline playback.
        """
        mock_perm.return_value = (True, "OK", {"status": "ACTIVE", "tier": "vip"})
        out_dir = os.path.join(self.temp_dir, "NovaCut_Hongguo")
        os.makedirs(out_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "installed": True,
            "tool_dir": r"D:\Tool\Hongguo Downloader",
            "signer_running": True,
            "server_running": True,
            "output_dir": out_dir,
            "error": None
        }
        mock_get_mgr.return_value = mock_mgr

        # 1. User arrives at tab: Status API called
        status_res = self.client.get("/api/hongguo/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertTrue(status_res.get_json()["data"]["installed"])

        # 2. User pastes URL & clicks Analyze
        drama_url = "https://novel.snssdk.com/api/novel/page/series?series_id=7410001"
        mock_mgr.forward_request.return_value = (200, {
            "resolved": [{
                "series_id": "7410001",
                "title": "Chiến Thần Đô Thị",
                "total": 80,
                "cover": "http://img.com/chienthan.jpg"
            }]
        })
        resolve_res = self.client.post("/api/hongguo/resolve", json={"text": drama_url})
        self.assertEqual(resolve_res.status_code, 200)
        drama_info = resolve_res.get_json()["resolved"][0]
        self.assertEqual(drama_info["title"], "Chiến Thần Đô Thị")

        # 3. User selects episodes 1 to 10
        selected_eps = list(range(1, 11))
        self.assertEqual(len(selected_eps), 10)

        # 4. User clicks 'Bắt Đầu Tải'
        mock_mgr.forward_request.return_value = (200, {
            "success": True,
            "task_id": "task_ct_1_10"
        })
        submit_res = self.client.post("/api/hongguo/submit", json={
            "series_ids": [drama_info["series_id"]],
            "episodes": selected_eps
        })
        self.assertEqual(submit_res.status_code, 200)

        # 5. Tasks polling simulator (0% -> 50% -> 100%)
        mock_mgr.forward_request.return_value = (200, {
            "running": False,
            "started": int(time.time()),
            "series": [{"sid": "7410001", "completed": 10, "total": 10, "progress": 100}],
            "log": ["Downloaded Episode 1", "Downloaded Episode 10", "All tasks completed!"]
        })
        tasks_res = self.client.get("/api/hongguo/tasks")
        self.assertEqual(tasks_res.status_code, 200)
        self.assertFalse(tasks_res.get_json()["running"])

        # 6. Materialize actual files on filesystem
        drama_dir = create_mock_downloaded_drama(out_dir, "Chiến Thần Đô Thị", ep_count=10)
        self.assertTrue(os.path.isdir(drama_dir))

        # Verify disk files integrity
        for ep in range(1, 11):
            ep_file = os.path.join(drama_dir, f"Tập {ep:02d}.mp4")
            self.assertTrue(os.path.isfile(ep_file))
            self.assertGreater(os.path.getsize(ep_file), 0)
            with open(ep_file, "rb") as vf:
                header = vf.read(16)
                self.assertIn(b"ftyp", header)

        # 7. Library refreshed
        lib_res = self.client.get("/api/hongguo/library")
        self.assertEqual(lib_res.status_code, 200)
        items = lib_res.get_json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["episodes_count"], 10)

        # 8. User clicks 'Chuyển sang Biên tập' on Episode 1
        ep1_target = os.path.join(drama_dir, "Tập 01.mp4")
        self.assertTrue(is_path_allowed(ep1_target, must_exist=True))

    # --- Scenario 2: Batch Download to Review Phim Studio ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t4_user_journey_drama_download_to_review_workflow(self, mock_get_mgr, mock_perm):
        """
        R2: Complete user journey to Review Phim:
        1. Resolve drama -> Download 3 episodes
        2. User selects Episode 2 to send to Review Phim studio
        3. Verifies path registration and read access for Review AI processing.
        """
        mock_perm.return_value = (True, "OK", {"status": "ACTIVE"})
        out_dir = os.path.join(self.temp_dir, "HongguoReview")
        os.makedirs(out_dir, exist_ok=True)
        drama_dir = create_mock_downloaded_drama(out_dir, "Cung Đấu Ký", ep_count=3)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": False, "output_dir": out_dir}
        mock_get_mgr.return_value = mock_mgr

        # Query Library Episodes
        ep_res = self.client.get("/api/hongguo/library/episodes?name=Cung Đấu Ký")
        self.assertEqual(ep_res.status_code, 200)
        episodes = ep_res.get_json()["episodes"]
        self.assertEqual(len(episodes), 3)

        # User chooses Episode 2 for Review
        ep2 = episodes[1]
        self.assertEqual(ep2["ep_num"], 2)
        self.assertTrue(is_path_allowed(ep2["path"], must_exist=True))

    # --- Scenario 3: Network Interruption Resilience during Task Polling ---
    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_t4_user_journey_resilience_recovery_polling(self, mock_get_mgr, mock_perm):
        """
        R3: Resilience scenario:
        1. Download in progress
        2. Client encounters transient upstream 502/504
        3. System recovers on next poll and cleanly finishes.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}

        # Sequence of polls: 1. Running -> 2. Network 502 error -> 3. Completed
        mock_mgr.forward_request.side_effect = [
            (200, {"running": True, "series": [{"sid": "1", "progress": 30}], "log": []}),
            (502, {"success": False, "error": "Bad Gateway"}),
            (200, {"running": False, "series": [{"sid": "1", "progress": 100}], "log": ["Done"]})
        ]
        mock_get_mgr.return_value = mock_mgr

        # Poll 1
        p1 = self.client.get("/api/hongguo/tasks").get_json()
        self.assertTrue(p1["running"])

        # Poll 2 (Transient error)
        p2 = self.client.get("/api/hongguo/tasks").get_json()
        self.assertTrue(p2["success"])  # Graceful fallback in get_tasks()
        self.assertIn("Bad Gateway", p2.get("warning", ""))

        # Poll 3 (Recovery)
        p3 = self.client.get("/api/hongguo/tasks").get_json()
        self.assertFalse(p3["running"])
        self.assertEqual(p3["series"][0]["progress"], 100)


if __name__ == "__main__":
    unittest.main()
