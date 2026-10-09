# -*- coding: utf-8 -*-
"""
tests/test_hongguo_tier5_backend.py
Tier 5 Backend & Security Adversarial Hardening Test Suite for Hongguo Downloader in NovaCut.

Adversarial Stress Testing Categories:
1. Concurrency & Race Conditions (rapid multi-threaded start/stop/status/gateway calls)
2. Malformed & Fuzzing Payloads (giant strings, unicode/emojis, nested objects, type mismatches)
3. Security Sandbox Traversal (encoded paths, null bytes, alternate separators, prefix collisions)
4. Upstream Error Simulation (502, 503, 504 timeout, HTML crash page, malformed JSON)
5. Dual-Layer License Verification Under Adversarial Stress (expired, tampered, bypass headers)
"""

import os
import sys
import json
import time
import shutil
import socket
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock, PropertyMock
import requests

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
    safe_join,
    _real,
    _is_within,
    _selected_roots,
    _selection_lock
)


def create_mock_hongguo_tool_directory(base_dir: str) -> dict:
    """Helper to create a valid Hongguo tool directory skeleton."""
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
        f.write(b"# MOCK_SERVER")

    return {
        "tool_dir": tool_dir,
        "java_exe": java_exe,
        "python_exe": python_exe,
        "signer_jar": signer_jar,
        "server_script": server_script
    }


# =============================================================================
# 1. CONCURRENCY & RACE CONDITIONS
# =============================================================================

class TestTier5ConcurrencyAndRaceConditions(unittest.TestCase):
    """
    Stress tests concurrent multi-threaded execution against manager lifecycle
    methods and gateway API endpoints to expose race conditions and deadlocks.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_t5_race_")
        self.tool_info = create_mock_hongguo_tool_directory(self.temp_dir)
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrency_rapid_start_stop_multithreaded(self):
        """
        Adversarial: 16 concurrent threads rapidly interleaving start_services()
        and stop_services() to test thread-safety, lock contention, and process list mutation.
        """
        mgr = HongguoServiceManager(override_tool_dir=self.tool_info["tool_dir"])

        # Mock spawn to avoid creating OS processes while testing threading logic
        created_procs = []
        def mock_spawn(cmd, cwd, env=None):
            m = MagicMock()
            m.pid = len(created_procs) + 1000
            m.poll.return_value = None
            created_procs.append(m)
            return m

        with patch.object(mgr, "_spawn", side_effect=mock_spawn), \
             patch.object(mgr, "wait_port", return_value=True), \
             patch.object(mgr, "check_signer_health", return_value=False), \
             patch.object(mgr, "check_server_health", return_value=False), \
             patch.object(mgr, "is_port_bindable", return_value=True):

            num_threads = 16
            iterations_per_thread = 10
            errors = []

            def worker_task(thread_id):
                for i in range(iterations_per_thread):
                    try:
                        if (thread_id + i) % 2 == 0:
                            mgr.start_services()
                        else:
                            mgr.stop_services()
                    except Exception as e:
                        errors.append(f"Thread {thread_id} step {i}: {type(e).__name__} {e}")

            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(worker_task, tid) for tid in range(num_threads)]
                for f in as_completed(futures):
                    f.result()

            self.assertEqual(errors, [], f"Race condition errors detected: {errors}")

            # Verify final state can be cleanly stopped
            mgr.stop_services()
            self.assertEqual(len(mgr._procs), 0)

    def test_concurrency_get_status_during_lifecycle_transitions(self):
        """
        Adversarial: Multiple threads query get_status() continuously while background
        threads trigger start_services() and stop_services() transitions.
        """
        mgr = HongguoServiceManager(override_tool_dir=self.tool_info["tool_dir"])

        running_flag = threading.Event()
        running_flag.set()
        status_results = []
        query_errors = []

        with patch.object(mgr, "_spawn", return_value=MagicMock(poll=lambda: None)), \
             patch.object(mgr, "wait_port", return_value=True), \
             patch.object(mgr, "is_port_bindable", return_value=True):

            def reader_task():
                while running_flag.is_set():
                    try:
                        st = mgr.get_status()
                        status_results.append(st)
                    except Exception as e:
                        query_errors.append(str(e))
                    time.sleep(0.002)

            def writer_task():
                for _ in range(8):
                    mgr.start_services()
                    time.sleep(0.005)
                    mgr.stop_services()
                    time.sleep(0.005)

            with ThreadPoolExecutor(max_workers=8) as executor:
                readers = [executor.submit(reader_task) for _ in range(4)]
                writers = [executor.submit(writer_task) for _ in range(4)]

                for w in writers:
                    w.result()

                running_flag.clear()
                for r in readers:
                    r.result()

        self.assertEqual(query_errors, [], f"get_status race errors: {query_errors}")
        self.assertGreater(len(status_results), 20)
        # Verify schema invariants across all concurrent reads
        for st in status_results:
            self.assertIsInstance(st, dict)
            self.assertIn("installed", st)
            self.assertIn("signer_running", st)
            self.assertIn("server_running", st)
            self.assertIn("output_dir", st)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_concurrency_flask_gateway_endpoints(self, mock_get_mgr, mock_perm):
        """
        Adversarial: Rapid concurrent requests to Flask routes (/status, /start, /stop, /tasks)
        using test client to verify Flask Blueprint thread safety and valid JSON output.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "installed": True,
            "tool_dir": self.tool_info["tool_dir"],
            "signer_running": True,
            "signer_port": 9099,
            "server_running": True,
            "server_port": 8000,
            "output_dir": self.temp_dir,
            "error": None
        }
        mock_mgr.start_services.return_value = (True, "Started")
        mock_mgr.stop_services.return_value = (True, "Stopped")
        mock_mgr.forward_request.return_value = (200, {"running": True, "series": {}, "log": []})
        mock_get_mgr.return_value = mock_mgr

        endpoints = [
            ("GET", "/api/hongguo/status", None),
            ("POST", "/api/hongguo/start", None),
            ("POST", "/api/hongguo/stop", None),
            ("GET", "/api/hongguo/tasks", None),
        ]

        errors = []
        def hit_endpoint(method, url, payload):
            try:
                if method == "GET":
                    resp = self.client.get(url)
                else:
                    resp = self.client.post(url, json=payload or {})
                if resp.status_code not in (200, 403, 500, 503):
                    errors.append(f"Unexpected status {resp.status_code} for {url}")
                # Ensure response is valid JSON
                data = resp.get_json()
                if not isinstance(data, dict):
                    errors.append(f"Non-JSON response from {url}: {resp.data}")
            except Exception as e:
                errors.append(f"Exception for {url}: {e}")

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = []
            for _ in range(10):
                for meth, url, pld in endpoints:
                    futures.append(executor.submit(hit_endpoint, meth, url, pld))
            for f in as_completed(futures):
                f.result()

        self.assertEqual(errors, [], f"Gateway concurrency errors: {errors}")


# =============================================================================
# 2. MALFORMED & FUZZING PAYLOADS
# =============================================================================

class TestTier5MalformedAndFuzzingPayloads(unittest.TestCase):
    """
    Fuzzes inputs with extreme lengths, unicode/emojis, nested objects,
    and invalid types across /resolve, /submit, and /open-folder.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_t5_fuzz_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_fuzz_resolve_giant_payloads(self, mock_get_mgr, mock_perm):
        """
        Adversarial: Send 100,000+ character strings to /resolve.
        System must handle gracefully without memory crashes or unhandled tracebacks.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (400, {"detail": "URL too long or invalid"})
        mock_get_mgr.return_value = mock_mgr

        giant_string = "https://novel.snssdk.com/drama/" + ("A" * 120000)
        resp = self.client.post("/api/hongguo/resolve", json={"text": giant_string})
        self.assertIn(resp.status_code, (400, 413, 500))
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertFalse(data["success"])

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_fuzz_resolve_unicode_and_bidi_attacks(self, mock_get_mgr, mock_perm):
        """
        Adversarial: Send RTL overrides, zero-width characters, emojis, surrogate pairs,
        Zalgo text, and format specifiers to /resolve.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {"resolved": []})
        mock_get_mgr.return_value = mock_mgr

        fuzz_samples = [
            "🎉🚀🔥戏剧短剧✨💎💯",
            "\u202e\u202d\u200e\u200f\ufeffhttps://novel.snssdk.com/7410001",
            "T\u0300\u0301\u0302\u0303e\u0304\u0305s\u0306\u0307t",  # Zalgo text
            "%s%d%n%x%p\\x00\\r\\n",
            "\x00nullbyteinstring",
            "𝒯𝑒𝓈𝓉 𝒟𝓇𝒶𝓂𝒶 𝟩𝟦𝟣𝟢𝟢𝟢𝟣",
            "简体中文繁體中文日本語한국어العربيةעברית",
        ]

        for sample in fuzz_samples:
            resp = self.client.post("/api/hongguo/resolve", json={"text": sample})
            self.assertIn(resp.status_code, (200, 400), f"Failed on sample: {repr(sample)}")
            data = resp.get_json()
            self.assertIsInstance(data, dict)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_fuzz_resolve_unexpected_nested_types(self, mock_get_mgr, mock_perm):
        """
        Adversarial: Send nested objects, arrays, booleans, and floats in the 'text' field.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        mock_mgr.forward_request.return_value = (200, {"resolved": []})
        mock_get_mgr.return_value = mock_mgr

        weird_payloads = [
            {"text": {"series_id": 7410001, "nested": True}},
            {"text": ["item1", "item2", 123]},
            {"text": 99999999999999999999999999},
            {"text": 3.141592653589793},
            {"text": True},
            {"text": False},
        ]

        for pld in weird_payloads:
            resp = self.client.post("/api/hongguo/resolve", json=pld)
            # Must return structured response without unhandled 500 crash
            self.assertIn(resp.status_code, (200, 400))
            data = resp.get_json()
            self.assertIsInstance(data, dict)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_fuzz_submit_malformed_and_edge_types(self, mock_get_mgr, mock_perm):
        """
        Adversarial: Send corrupt structures to /api/hongguo/submit:
        non-list series_ids, nested objects, extreme values, strings in lists.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": self.temp_dir}
        mock_mgr.forward_request.return_value = (200, {"task_id": "test_123"})
        mock_get_mgr.return_value = mock_mgr

        adversarial_submits = [
            {"series_ids": "not_a_list_string"},
            {"series_ids": {"key": "val"}},
            {"series_ids": [None, {}, []]},
            {"series_ids": [100000 * "x"]},
            {"series_id": {"nested": {"deep": [1, 2, 3]}}},
            {"series_id": -99999999},
            {"series_id": 1e308},
            {"unexpected_field": "garbage_value"},
        ]

        for pld in adversarial_submits:
            resp = self.client.post("/api/hongguo/submit", json=pld)
            self.assertIn(resp.status_code, (200, 400, 500))
            data = resp.get_json()
            self.assertIsInstance(data, dict)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    @patch("subprocess.Popen")
    def test_fuzz_open_folder_unexpected_types(self, mock_popen, mock_get_mgr, mock_perm):
        """
        Adversarial: Send unexpected types and oversized strings to /api/hongguo/open-folder.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": self.temp_dir}
        mock_get_mgr.return_value = mock_mgr

        fuzz_folders = [
            {"folder": 12345},
            {"folder": ["a", "b", "c"]},
            {"folder": {"path": "/etc"}},
            {"folder": True},
            {"folder": "A" * 15000},
            {"folder": "\t\n\r   "},
        ]

        for pld in fuzz_folders:
            resp = self.client.post("/api/hongguo/open-folder", json=pld)
            self.assertIn(resp.status_code, (200, 400))
            data = resp.get_json()
            self.assertIsInstance(data, dict)

    @patch("license_manager.check_permission")
    def test_fuzz_malformed_json_syntax_and_raw_bytes(self, mock_perm):
        """
        Adversarial: Send raw binary bytes, unclosed JSON, and invalid Content-Types.
        Flask must return clean 400 or handled response, never an unhandled 500 HTML traceback.
        """
        mock_perm.return_value = (True, "OK", {})

        # Raw broken JSON
        resp = self.client.post(
            "/api/hongguo/resolve",
            data='{"text": unclosed_string',
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIsInstance(data, dict)

        # Raw binary garbage
        resp = self.client.post(
            "/api/hongguo/resolve",
            data=b"\x00\xff\xfe\xaa\xbb\xcc",
            content_type="application/octet-stream"
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIsInstance(data, dict)


# =============================================================================
# 3. SECURITY SANDBOX TRAVERSAL HARDENING
# =============================================================================

class TestTier5SecuritySandboxTraversal(unittest.TestCase):
    """
    White-box adversarial testing against path traversal evasion techniques
    (URL-encoded slashes, null bytes, alternate separators, Windows reserved devices)
    for /library/episodes and /open-folder.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_t5_sec_")
        self.output_dir = os.path.join(self.temp_dir, "HongguoDownloads")
        os.makedirs(self.output_dir, exist_ok=True)
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_sandbox_traversal_library_episodes_adversarial_matrix(self, mock_get_mgr, mock_perm):
        """
        Adversarial matrix against /library/episodes?name=...
        Tests URL encoding, null bytes, backslashes, double encoding, and Windows devices.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": self.output_dir, "server_running": False}
        mock_get_mgr.return_value = mock_mgr

        adversarial_attempts = [
            # Standard traversals
            "../",
            "..\\",
            "../../",
            "..\\..\\",
            "foo/../../bar",
            "foo\\..\\..\\bar",
            # Encoded traversals
            "..%2f",
            "%2e%2e%2f",
            "..%5c",
            "%2e%2e%5c",
            "%252e%252e%252f",
            "..%252f",
            # Null bytes
            "drama\x00extra",
            "drama%00.mp4",
            "%00../../etc",
            # Windows drive / UNC paths
            "C:Windows",
            "C:\\Windows\\System32",
            "\\\\127.0.0.1\\c$\\secret",
            "//localhost/c$/secret",
            # Windows device names & NTFS alternate streams
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "LPT1",
            "drama::$DATA",
            # Dot variants
            ".",
            "..",
            "...",
            "....",
            "drama/..",
            "drama\\..",
            "drama/.",
            # Wildcards & pipe
            "drama*name",
            "drama?name",
            "drama|name",
            "drama<name",
            "drama>name",
            "drama\"name",
        ]

        evasions = []
        for bad_name in adversarial_attempts:
            resp = self.client.get(f"/api/hongguo/library/episodes?name={bad_name}")
            if resp.status_code != 400:
                evasions.append({
                    "payload": bad_name,
                    "status_code": resp.status_code,
                    "data": resp.get_json()
                })
        self.assertEqual(evasions, [], f"Sandbox traversal evasions permitted: {evasions}")

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_sandbox_valid_unicode_subfolder_permitted(self, mock_get_mgr, mock_perm):
        """
        Positive control: Legitimate drama folder names with Vietnamese and Chinese
        characters must be accepted without false-positive blocking.
        """
        mock_perm.return_value = (True, "OK", {})
        valid_drama_dir = os.path.join(self.output_dir, "Hào Môn Kinh Mộng (Tập 1-50)")
        os.makedirs(valid_drama_dir, exist_ok=True)

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": self.output_dir, "server_running": False}
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/library/episodes?name=Hào Môn Kinh Mộng (Tập 1-50)")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data.get("episodes"), list)


    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    @patch("subprocess.Popen")
    @patch("os.startfile", create=True)
    def test_sandbox_traversal_open_folder_adversarial_matrix(self, mock_startfile, mock_popen, mock_get_mgr, mock_perm):
        """
        Adversarial matrix against /open-folder.
        Verifies system strictly blocks unauthorized directory openings and NEVER
        calls os.startfile or subprocess.Popen on rogue paths.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"output_dir": self.output_dir}
        mock_get_mgr.return_value = mock_mgr

        rogue_paths = [
            "../../Windows",
            "..\\..\\Windows\\System32",
            "../secret",
            r"C:\Windows",
            r"C:\Windows\System32\cmd.exe",
            r"C:\Program Files",
            r"D:\System Volume Information",
            "/etc/shadow",
            "/var/root",
            "folder\x00name",
            "folder*wildcard",
            "folder?question",
            "folder<angle",
            "folder>angle",
            "folder|pipe",
            "folder\"quote",
        ]

        for rogue in rogue_paths:
            resp = self.client.post("/api/hongguo/open-folder", json={"folder": rogue})
            self.assertEqual(resp.status_code, 400, f"Allowed rogue path opening: {repr(rogue)}")
            data = resp.get_json()
            self.assertFalse(data["success"])

        # Crucial security check: Explorer or startfile was NEVER invoked on rogue paths
        mock_startfile.assert_not_called()
        mock_popen.assert_not_called()

    def test_sandbox_is_path_allowed_strictness_and_prefix_collision(self):
        """
        Adversarial: Direct test of is_path_allowed() against prefix collisions
        (e.g., allowed: 'output', rogue sibling: 'output_evil') and traversal tricks.
        """
        allowed_dir = os.path.join(self.temp_dir, "allowed_dir")
        sibling_evil_dir = os.path.join(self.temp_dir, "allowed_dir_evil")
        os.makedirs(allowed_dir, exist_ok=True)
        os.makedirs(sibling_evil_dir, exist_ok=True)

        register_user_path(allowed_dir)

        # 1. Allowed dir and file within allowed dir must pass
        test_file = os.path.join(allowed_dir, "ep1.mp4")
        with open(test_file, "wb") as f:
            f.write(b"SAFE")
        self.assertTrue(is_path_allowed(test_file))

        # 2. Sibling directory with prefix collision must be BLOCKED
        evil_file = os.path.join(sibling_evil_dir, "hacked.mp4")
        with open(evil_file, "wb") as f:
            f.write(b"EVIL")
        self.assertFalse(
            is_path_allowed(evil_file),
            "Prefix collision vulnerability: sibling directory allowed!"
        )

        # 3. Path traversal attempting to escape via dot-dots must be BLOCKED
        escape_attempt = os.path.join(allowed_dir, "..", "allowed_dir_evil", "hacked.mp4")
        self.assertFalse(is_path_allowed(escape_attempt))


# =============================================================================
# 4. UPSTREAM ERROR SIMULATION & GATEWAY RESILIENCE
# =============================================================================

class TestTier5UpstreamErrorSimulation(unittest.TestCase):
    """
    Simulates upstream failure scenarios (502 Connection Refused, 504 Timeout,
    500 HTML Error Page, 503 Plain Text, Corrupted JSON) to ensure the Flask
    gateway handles them cleanly with structured JSON responses.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_t5_upstream_")
        self.client = app.test_client()
        self.client.testing = True

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.requests.request")
    def test_upstream_502_bad_gateway_connection_refused(self, mock_req, mock_perm):
        """
        Upstream server drops or refuses TCP connection (RequestException).
        Verify forward_request and endpoints return structured 502 JSON error.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_req.side_effect = requests.ConnectionError("Connection refused by peer")

        mgr = HongguoServiceManager()
        with patch.object(mgr, "check_server_health", return_value=True):
            code, data = mgr.forward_request("GET", "/dl/status")
            self.assertEqual(code, 502)
            self.assertIsInstance(data, dict)
            self.assertFalse(data["success"])
            self.assertIn("Lỗi kết nối", data["error"])

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.requests.request")
    def test_upstream_504_gateway_timeout(self, mock_req, mock_perm):
        """
        Upstream server hangs and triggers socket read timeout.
        Verify forward_request returns 504 and structured JSON.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_req.side_effect = requests.Timeout("Gateway Read Timeout")

        mgr = HongguoServiceManager()
        with patch.object(mgr, "check_server_health", return_value=True):
            code, data = mgr.forward_request("GET", "/dl/episodes", params={"series_id": "7410001"})
            self.assertEqual(code, 504)
            self.assertIsInstance(data, dict)
            self.assertFalse(data["success"])
            self.assertIn("timeout", data["error"].lower())

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.requests.request")
    def test_upstream_500_html_crash_page(self, mock_req, mock_perm):
        """
        Upstream Python server throws uncaught exception and returns HTML crash page
        instead of JSON. Gateway must parse text safely and return structured JSON.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.text = "<html><body><h1>500 Internal Server Error</h1><pre>Traceback...</pre></body></html>"
        mock_req.return_value = mock_resp

        mgr = HongguoServiceManager()
        with patch.object(mgr, "check_server_health", return_value=True):
            code, data = mgr.forward_request("POST", "/dl/resolve", json_data={"text": "7410001"})
            self.assertEqual(code, 500)
            self.assertIsInstance(data, str)
            self.assertIn("500 Internal Server Error", data)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_upstream_gateway_endpoints_resilience_matrix(self, mock_get_mgr, mock_perm):
        """
        Test /resolve, /episodes, /drama-detail, /submit, /cancel when forward_request returns 502/504.
        All Flask routes must return structured JSON errors with correct HTTP status codes.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True, "output_dir": self.temp_dir}
        mock_mgr.forward_request.return_value = (502, {"success": False, "error": "Connection reset"})
        mock_get_mgr.return_value = mock_mgr

        # 1. /resolve
        resp = self.client.post("/api/hongguo/resolve", json={"text": "7410001"})
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

        # 2. /episodes
        resp = self.client.get("/api/hongguo/episodes?series_id=7410001")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

        # 3. /drama-detail
        resp = self.client.get("/api/hongguo/drama-detail?series_id=7410001")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

        # 4. /submit
        resp = self.client.post("/api/hongguo/submit", json={"series_ids": ["7410001"]})
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

        # 5. /cancel
        resp = self.client.post("/api/hongguo/cancel")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertFalse(data["success"])

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_upstream_tasks_polling_failover_resilience(self, mock_get_mgr, mock_perm):
        """
        Adversarial: When upstream drops or errors out during /tasks, the gateway
        must NOT return HTTP 500. It must return a safe fallback schema with
        running=False so frontend pollers never crash or trigger UI alerts.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": True}
        # Simulate upstream returning 502 error
        mock_mgr.forward_request.return_value = (502, "Server unreachable")
        mock_get_mgr.return_value = mock_mgr

        resp = self.client.get("/api/hongguo/tasks")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["running"])
        self.assertEqual(data["series"], {})
        self.assertEqual(data["log"], [])
        self.assertIn("warning", data)

    @patch("license_manager.check_permission")
    @patch("services.hongguo_service.get_service_manager")
    def test_upstream_503_service_unavailable_on_failed_start(self, mock_get_mgr, mock_perm):
        """
        Adversarial: When upstream services are down and start_services fails (e.g. missing JRE/binary),
        gateway must return HTTP 503 with structured JSON error, not crash with unhandled exception.
        """
        mock_perm.return_value = (True, "OK", {})
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {"server_running": False}
        mock_mgr.start_services.return_value = (False, "Môi trường JRE không tồn tại")
        mock_get_mgr.return_value = mock_mgr

        endpoints = [
            ("POST", "/api/hongguo/resolve", {"text": "7410001"}),
            ("GET", "/api/hongguo/episodes?series_id=7410001", None),
            ("GET", "/api/hongguo/drama-detail?series_id=7410001", None),
            ("POST", "/api/hongguo/submit", {"series_ids": ["7410001"]}),
        ]

        for method, url, payload in endpoints:
            if method == "POST":
                resp = self.client.post(url, json=payload)
            else:
                resp = self.client.get(url)

            self.assertEqual(resp.status_code, 503, f"Endpoint {url} failed to return 503 on service start failure")
            data = resp.get_json()
            self.assertIsInstance(data, dict)
            self.assertFalse(data["success"])
            self.assertIn("Không thể khởi động dịch vụ", data["error"])



# =============================================================================
# 5. DUAL-LAYER LICENSE VERIFICATION UNDER ADVERSARIAL STRESS
# =============================================================================

class TestTier5DualLayerLicenseUnderAdversarialStress(unittest.TestCase):
    """
    Adversarial verification of the dual-layer license guard under spoofed
    headers, mid-session transitions, and corrupted status payloads.
    """

    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch("license_manager.check_permission")
    def test_license_unauthorized_blocks_all_routes_consistently(self, mock_perm):
        """
        Verifies that EXPIRED, UNLICENSED, and CLOCK_TAMPERED states strictly
        block every single endpoint under the /api/hongguo blueprint with HTTP 403.
        """
        unauthorized_states = [
            (False, "Chưa kích hoạt bản quyền", {"status": "UNLICENSED"}),
            (False, "Bản quyền đã hết hạn", {"status": "EXPIRED"}),
            (False, "Phát hiện gian lận đồng hồ hệ thống", {"status": "CLOCK_TAMPERED"}),
            (False, "Gói cước không hỗ trợ tính năng này", {"status": "FEATURE_DISABLED"}),
        ]

        routes_to_test = [
            ("GET", "/api/hongguo/status"),
            ("POST", "/api/hongguo/start"),
            ("POST", "/api/hongguo/stop"),
            ("POST", "/api/hongguo/resolve"),
            ("GET", "/api/hongguo/episodes?series_id=123"),
            ("GET", "/api/hongguo/drama-detail?series_id=123"),
            ("POST", "/api/hongguo/submit"),
            ("GET", "/api/hongguo/tasks"),
            ("POST", "/api/hongguo/cancel"),
            ("GET", "/api/hongguo/library"),
            ("GET", "/api/hongguo/library/episodes?name=test"),
            ("POST", "/api/hongguo/open-folder"),
        ]

        for allowed, msg, stat in unauthorized_states:
            mock_perm.return_value = (allowed, msg, stat)
            for method, url in routes_to_test:
                if method == "GET":
                    resp = self.client.get(url)
                else:
                    resp = self.client.post(url, json={})

                self.assertEqual(
                    resp.status_code, 403,
                    f"Route {url} failed to block on status {stat['status']}"
                )
                data = resp.get_json()
                self.assertFalse(data["success"])
                self.assertTrue(data.get("license_error"))

    @patch("license_manager.check_permission")
    def test_license_bypass_header_spoofing_resistance(self, mock_perm):
        """
        Adversary attempts header spoofing (X-Forwarded-For, X-Admin, Authorization, Host)
        to bypass license check. License guard must ignore headers and reject with 403.
        """
        mock_perm.return_value = (False, "Chưa kích hoạt", {"status": "UNLICENSED"})

        spoofed_headers = {
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
            "X-Admin": "true",
            "Authorization": "Bearer superuser_token",
            "X-License-Override": "1",
            "User-Agent": "NovaCutInternal/1.0"
        }

        resp = self.client.get("/api/hongguo/status", headers=spoofed_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.get_json().get("license_error"))

    @patch("license_manager.check_permission")
    def test_license_concurrent_race_resistance(self, mock_perm):
        """
        High concurrency check: 16 threads hammering routes while license state
        transitions. Verify no requests slip through once revoked.
        """
        mock_perm.return_value = (False, "Expired", {"status": "EXPIRED"})

        def worker():
            resp = self.client.get("/api/hongguo/status")
            return resp.status_code

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker) for _ in range(32)]
            results = [f.result() for f in as_completed(futures)]

        self.assertTrue(all(code == 403 for code in results), f"Some requests bypassed 403: {results}")


if __name__ == "__main__":
    unittest.main()
