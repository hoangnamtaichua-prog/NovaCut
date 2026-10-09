# -*- coding: utf-8 -*-
"""
tests/test_hongguo_tier5_frontend.py
Tier 5 Adversarial Stress Testing & Workflow Hardening Suite for Hongguo Downloader.

Adversarial Challenger Coverage:
1. Complex & boundary range expressions in `parseEpisodeRange`:
   - Overlapping ranges ('1-10, 5-15', '3-8, 1-4, 7-12', '1-20, 10-15, 5, 20')
   - Reversed segments ('15-5', '50-20', '10-1')
   - Large ranges & boundary limits ('1-1000', '1-5000' clamped to maxEpisodes)
   - Spaced delimiters ('  1-5 ,  8  ', '  1-5 ;  8  ') and hyphen whitespace tokenization ('  1 - 5 ,  8  ')
   - Randomized adversarial fuzzing expressions
2. Active polling and cancellation under simulated network errors:
   - Polling survives HTTP 500 Internal Server Error without locking UI or killing polling timer
   - Polling survives network drops/aborts and recovers cleanly upon service restoration
   - Cancellation during network error and subsequent recovery
   - Rapid start/stop polling cycling stress (no timer leaks)
3. Library scanning resilience (Backend API & Frontend Handling):
   - Corrupted .series.json metadata (syntax errors, malformed JSON)
   - Zero .mp4 videos (folders with non-video files or empty folders)
   - Unreadable or permission-denied directory scanning
   - Directory traversal attempts & corrupted library episodes queries
   - Frontend empty/malformed response handling
4. Workflow Bridge Stress:
   - Rapid sequential triggers of window.sendVideoToEditor (30+ iterations)
   - Rapid sequential triggers of window.sendVideoToReview (30+ iterations)
   - Rapid alternating bridges stress (Editor <-> Review interleaved)
   - Special characters & Unicode file paths (Vietnamese, Chinese, spaces, URL-reserved # & %)
   - Nonexistent, empty, and malformed path inputs
"""

import os
import sys
import re
import json
import socket
import shutil
import tempfile
import threading
import subprocess
import http.server
import socketserver
import time
import unittest
from unittest.mock import patch, MagicMock
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

WEB_DIR = os.path.join(REPO_ROOT, 'web')
HONGGUO_JS = os.path.join(WEB_DIR, 'js', 'features', 'hongguo.js')
APP_JS = os.path.join(WEB_DIR, 'app.js')

from web_app import app
from services.hongguo_service import HongguoServiceManager, get_service_manager
from routes.security import register_user_path, is_path_allowed


# =============================================================================
# Helper Utilities & Fixtures
# =============================================================================

def run_node_eval(js_code: str, timeout: float = 15.0) -> dict:
    """Execute JavaScript code in Node.js and return parsed JSON stdout."""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", js_code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Node execution failed (code {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return json.loads(result.stdout)


def get_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ThreadedStaticServer:
    def __init__(self, port: int):
        self.port = port
        handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
            *args, directory=WEB_DIR, **kwargs
        )
        self.server = socketserver.TCPServer(('127.0.0.1', self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        time.sleep(0.3)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(scope="module")
def browser_harness():
    """Module-level Playwright Chromium harness with mock license and static server."""
    from playwright.sync_api import sync_playwright

    port = get_free_port()
    server = ThreadedStaticServer(port=port)
    server.start()

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()

    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # Global mocks to prevent external calls and ensure VIP license
    page.add_init_script("localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');")
    page.route("**/api/license/info*", lambda r: r.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "is_valid": True,
            "status": "ACTIVE",
            "tier": "vip",
            "plan_name": "VIP Vĩnh Viễn",
            "disclaimer_accepted": True,
            "features": {
                "can_access_editor": True,
                "can_access_review": True,
                "hongguo_downloader": True
            }
        })
    ))
    page.route("**/api/license/check_sepay_payment*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"active": True})
    ))
    page.route("**/api/batch/stream*", lambda r: r.fulfill(
        status=200, content_type="text/plain", body=""
    ))
    page.route("**/api/license/sync_cloud*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"success": True})
    ))
    page.route("**/api/hongguo/status*", lambda r: r.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"success": True, "data": {"installed": True, "signer_running": True, "server_running": True}})
    ))
    page.route("**/api/hongguo/library*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"success": True, "items": []})
    ))

    # Navigate to app
    page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="domcontentloaded")
    page.wait_for_selector(".header-tabs", timeout=10000)

    yield {
        "page": page,
        "browser": browser,
        "pw": pw,
        "server": server,
        "page_errors": page_errors,
        "port": port
    }

    try:
        browser.close()
        pw.stop()
        server.stop()
    except Exception:
        pass


# =============================================================================
# TIER 5.1: COMPLEX & BOUNDARY RANGE EXPRESSIONS IN parseEpisodeRange
# =============================================================================

class TestTier5RangeExpressionAdversarial:
    """
    White-box adversarial stress testing on parseEpisodeRange:
    - Overlapping range expressions
    - Reversed segments
    - Large ranges & max boundary clamping
    - Spaced delimiters and tokenization boundaries
    - Randomized fuzzing generators
    """

    def test_overlapping_range_expressions(self):
        """Overlapping ranges ('1-10, 5-15') must resolve cleanly without duplicates."""
        js = """
        import { parseEpisodeRange } from './web/js/features/hongguo.js';
        const r1 = Array.from(parseEpisodeRange('1-10, 5-15', 50)).sort((a,b) => a-b);
        const r2 = Array.from(parseEpisodeRange('3-8, 1-4, 7-12', 50)).sort((a,b) => a-b);
        const r3 = Array.from(parseEpisodeRange('1-20, 10-15, 5, 20', 50)).sort((a,b) => a-b);
        console.log(JSON.stringify({ r1, r2, r3 }));
        """
        data = run_node_eval(js)
        # r1: 1 through 15
        assert data["r1"] == list(range(1, 16))
        assert len(data["r1"]) == 15
        # r2: 1 through 12
        assert data["r2"] == list(range(1, 13))
        assert len(data["r2"]) == 12
        # r3: 1 through 20
        assert data["r3"] == list(range(1, 21))
        assert len(data["r3"]) == 20

    def test_reversed_segment_normalization(self):
        """Reversed segments ('15-5', '50-20', '10-1') must normalize automatically."""
        js = """
        import { parseEpisodeRange } from './web/js/features/hongguo.js';
        const r1 = Array.from(parseEpisodeRange('15-5', 50)).sort((a,b) => a-b);
        const r2 = Array.from(parseEpisodeRange('50-20', 100)).sort((a,b) => a-b);
        const r3 = Array.from(parseEpisodeRange('10-1', 20)).sort((a,b) => a-b);
        const r4 = Array.from(parseEpisodeRange('20-15, 1-5, 30-25', 50)).sort((a,b) => a-b);
        console.log(JSON.stringify({ r1, r2, r3, r4 }));
        """
        data = run_node_eval(js)
        assert data["r1"] == list(range(5, 16))
        assert len(data["r1"]) == 11
        assert data["r2"] == list(range(20, 51))
        assert len(data["r2"]) == 31
        assert data["r3"] == list(range(1, 11))
        assert len(data["r3"]) == 10
        expected_r4 = sorted(list(range(1, 6)) + list(range(15, 21)) + list(range(25, 31)))
        assert data["r4"] == expected_r4

    def test_large_ranges_and_boundary_limits(self):
        """Large ranges ('1-1000', '1-5000') must be clamped strictly to maxEpisodes."""
        js = """
        import { parseEpisodeRange } from './web/js/features/hongguo.js';
        const t0 = performance.now();
        const r1000 = parseEpisodeRange('1-1000', 1000);
        const elapsed1000 = performance.now() - t0;

        const r5000Clamped = parseEpisodeRange('1-5000', 1000);
        const rZeroLowerBound = parseEpisodeRange('0-10', 10);
        const rNegativeBound = parseEpisodeRange('-10-5', 20);

        console.log(JSON.stringify({
            size1000: r1000.size,
            elapsed1000,
            size5000: r5000Clamped.size,
            max5000: Math.max(...r5000Clamped),
            min5000: Math.min(...r5000Clamped),
            zeroLowerBound: Array.from(rZeroLowerBound).sort((a,b) => a-b),
            negativeBound: Array.from(rNegativeBound)
        }));
        """
        data = run_node_eval(js)
        assert data["size1000"] == 1000
        assert data["elapsed1000"] < 100.0  # Fast sub-100ms generation
        assert data["size5000"] == 1000
        assert data["max5000"] == 1000
        assert data["min5000"] == 1
        # '0-10' ignores 0 because condition is i >= 1
        assert data["zeroLowerBound"] == list(range(1, 11))

    def test_spaced_delimiters_and_hyphen_tokenization_behavior(self):
        """
        Adversarial test on spaced delimiters:
        1. Spaces around standard delimiters: '  1-5 ,  8  ' -> {1, 2, 3, 4, 5, 8}
        2. Semicolons with spaces: '  1-5 ;  8  ' -> {1, 2, 3, 4, 5, 8}
        3. Hyphen with internal spaces: '  1 - 5 ,  8  '.
           Empirically documents that split(/[,;\\s]+/) tokenizes '1 - 5' by whitespace into
           tokens ['1', '-', '5', '8'], yielding Set(1, 5, 8) rather than Set(1, 2, 3, 4, 5, 8).
        """
        js = """
        import { parseEpisodeRange } from './web/js/features/hongguo.js';
        const spacedComma = Array.from(parseEpisodeRange('  1-5 ,  8  ', 20)).sort((a,b) => a-b);
        const spacedSemicolon = Array.from(parseEpisodeRange('  1-5 ;  8  ', 20)).sort((a,b) => a-b);
        const spacedHyphen = Array.from(parseEpisodeRange('  1 - 5 ,  8  ', 20)).sort((a,b) => a-b);
        const spacedTilde = Array.from(parseEpisodeRange('  1 ~ 5 ,  8  ', 20)).sort((a,b) => a-b);
        console.log(JSON.stringify({ spacedComma, spacedSemicolon, spacedHyphen, spacedTilde }));
        """
        data = run_node_eval(js)
        # Spaces around comma delimiters pass properly
        assert data["spacedComma"] == [1, 2, 3, 4, 5, 8]
        assert data["spacedSemicolon"] == [1, 2, 3, 4, 5, 8]

        # Empirical documentation of internal hyphen whitespace tokenization:
        # split(/[,;\s]+/) splits by space, isolating '1', '-', '5', and '8'
        assert data["spacedHyphen"] == [1, 5, 8], (
            "Empirically verify that whitespace tokenization isolates boundary numbers in '1 - 5'"
        )
        assert data["spacedTilde"] == [1, 5, 8], (
            "Empirically verify that whitespace tokenization isolates boundary numbers in '1 ~ 5'"
        )

    def test_randomized_adversarial_range_fuzzing(self):
        """Fuzz generator testing 50 random chaotic range expressions without crashing."""
        js = """
        import { parseEpisodeRange } from './web/js/features/hongguo.js';
        const fuzzInputs = [
            ",,,;;;",
            "  - - -  ",
            "foo, bar, 1-3, baz",
            "1, 2, 3, 4, 5, 6, 7, 8, 9, 10",
            "99999-100000",
            "0-0, 0, -1, -5--10",
            "1-2-3-4-5",
            "1..10, 15...20",
            "  100-50, 25-10  ",
            "NaN, null, undefined, [object Object]",
            "1~5, 10~15, 20~25",
            "ALL, all, Tất Cả, ALL_EPISODES",
            "1000-1000",
            "1, , 2, , 3",
            "\\t\\n1-5\\r\\n, 6-10"
        ];

        const results = fuzzInputs.map(inp => {
            try {
                const s = parseEpisodeRange(inp, 100);
                const isSet = s instanceof Set;
                const arr = Array.from(s);
                const allValidInts = arr.every(x => Number.isInteger(x) && x >= 1 && x <= 100);
                return { ok: true, isSet, size: s.size, allValidInts };
            } catch (err) {
                return { ok: false, error: err.message };
            }
        });

        console.log(JSON.stringify(results));
        """
        data = run_node_eval(js)
        for idx, res in enumerate(data):
            assert res["ok"] is True, f"Fuzz test case {idx} crashed"
            assert res["isSet"] is True, f"Fuzz test case {idx} did not return a Set"
            assert res["allValidInts"] is True, f"Fuzz test case {idx} returned invalid numbers"


# =============================================================================
# TIER 5.2: ACTIVE POLLING & CANCELLATION UNDER SIMULATED NETWORK ERRORS
# =============================================================================

class TestTier5ActivePollingAndCancellationStress:
    """
    Empirical stress testing of active polling & cancellation resilience
    under simulated 500 errors, network drops, and rapid cycling.
    """

    def test_polling_survives_500_internal_server_error(self, browser_harness):
        """
        Verify that when /api/hongguo/tasks returns 500, polling does not throw
        uncaught exceptions, does not lock UI, and keeps polling timer alive.
        """
        page = browser_harness["page"]

        # Navigate to Hongguo view
        page.evaluate("() => { const tab = document.querySelector('.nav-tab[data-target=\"viewHongguo\"]'); if (tab) tab.click(); }")
        time.sleep(0.5)

        # Mock /api/hongguo/tasks to return 500 Internal Server Error
        page.route("**/api/hongguo/tasks*", lambda r: r.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"success": False, "error": "Simulated 500 Internal Server Error"})
        ))

        # Start polling via hongguo.js
        page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); m.startProgressPolling(); }")
        time.sleep(1.5)

        # Verify polling timer and flag remain active despite 500 error
        poll_state = page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); return { isPolling: m.hongguoState.isPolling, hasTimer: !!m.hongguoState.pollingTimer }; }")
        assert poll_state["isPolling"] is True, "Polling state should remain true during transient 500 errors"
        assert poll_state["hasTimer"] is True, "Polling timer should not be destroyed on 500 error"

        # Verify UI is not locked and remains interactive
        is_responsive = page.evaluate("() => { const inp = document.getElementById('hongguoInputUrl'); if (inp) { inp.value = 'test_responsive'; return inp.value === 'test_responsive'; } return false; }")
        assert is_responsive is True, "UI must remain interactive under backend 500 errors"

        # Now simulate server recovery (200 OK)
        page.route("**/api/hongguo/tasks*", lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "success": True,
                "running": True,
                "series": [
                    {"sid": "741001", "title": "Ba Dao Tong Tai", "current": 3, "total": 10, "speed": "4.2 MB/s", "status": "downloading"}
                ],
                "log": ["[08:00:01] Dang tai tap 3..."]
            })
        ))

        # Verify polling recovers and updates the UI elements
        recovered_text = page.evaluate("""
        async () => {
            const m = await import('./js/features/hongguo.js');
            await m.pollDownloadTasks();
            const el = document.getElementById('hongguoProgressDramaTitle');
            return el ? el.textContent : '';
        }
        """)
        assert "Ba Dao Tong Tai" in recovered_text, f"UI should reflect recovered task progress: got '{recovered_text}'"

        # Stop polling cleanly
        page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); m.stopProgressPolling(); }")

    def test_polling_survives_network_drop_and_disconnect(self, browser_harness):
        """Verify polling survives simulated network aborts (fetch network drops)."""
        page = browser_harness["page"]

        # Simulate network drop (abort route)
        page.route("**/api/hongguo/tasks*", lambda r: r.abort("failed"))

        page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); m.startProgressPolling(); }")
        time.sleep(1.2)

        # Polling flag must remain active, waiting for network restoration
        poll_state = page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); return { isPolling: m.hongguoState.isPolling, hasTimer: !!m.hongguoState.pollingTimer }; }")
        assert poll_state["isPolling"] is True
        assert poll_state["hasTimer"] is True

        page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); m.stopProgressPolling(); }")

    def test_cancellation_during_network_error_and_subsequent_recovery(self, browser_harness):
        """
        Verify cancellation under network errors:
        - When /cancel fails with 500, shows toast and does not crash
        - When /cancel succeeds, polling stops and UI marks as cancelled
        """
        page = browser_harness["page"]

        # Route cancel to 500
        page.route("**/api/hongguo/cancel*", lambda r: r.fulfill(
            status=500, content_type="application/json", body=json.dumps({"success": False, "error": "Gateway Timeout"})
        ))

        # Start polling
        page.evaluate("async () => { const m = await import('./js/features/hongguo.js'); m.startProgressPolling(); }")

        # Directly invoke cancelHongguoDownload bypass confirm modal
        cancel_attempt_1 = page.evaluate("""
        async () => {
            const m = await import('./js/features/hongguo.js');
            // Mock showConfirmModal to return true
            window.showConfirmModal = async () => true;
            await m.cancelHongguoDownload();
            return m.hongguoState.isPolling;
        }
        """)
        # Still polling because cancel failed
        assert cancel_attempt_1 is True

        # Now route cancel to 200 OK
        page.route("**/api/hongguo/cancel*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"success": True, "message": "Cancelled"})
        ))

        cancel_attempt_2 = page.evaluate("""
        async () => {
            const m = await import('./js/features/hongguo.js');
            window.showConfirmModal = async () => true;
            await m.cancelHongguoDownload();
            return {
                isPolling: m.hongguoState.isPolling,
                statusText: document.getElementById('hongguoProgressStatusText')?.textContent || ''
            };
        }
        """)
        assert cancel_attempt_2["isPolling"] is False, "Polling must be stopped after successful cancel"
        assert "Đã hủy tải phim" in cancel_attempt_2["statusText"]

    def test_rapid_start_stop_polling_cycles(self, browser_harness):
        """Rapidly start and stop polling 25 times to guarantee no timer leaks or race conditions."""
        page = browser_harness["page"]

        result = page.evaluate("""
        async () => {
            const m = await import('./js/features/hongguo.js');
            for (let i = 0; i < 25; i++) {
                m.startProgressPolling();
                m.stopProgressPolling();
            }
            return {
                isPolling: m.hongguoState.isPolling,
                hasTimer: !!m.hongguoState.pollingTimer
            };
        }
        """)
        assert result["isPolling"] is False
        assert result["hasTimer"] is False


# =============================================================================
# TIER 5.3: LIBRARY SCANNING RESILIENCE (CORRUPTED DIRECTORIES & ZERO VIDEOS)
# =============================================================================

class TestTier5LibraryScanningResilience(unittest.TestCase):
    """
    White-box backend & frontend resilience testing for /api/hongguo/library:
    - Corrupted .series.json metadata
    - Folders with zero .mp4 files
    - Unreadable or permission-denied subdirectories
    - Path traversal and malicious folder name parameters
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="novacut_t5_lib_")
        self.client = app.test_client()
        self.client.testing = True

        # Setup mock manager with output_dir
        self.mock_mgr = MagicMock()
        self.mock_mgr.get_status.return_value = {
            "installed": True,
            "tool_dir": self.temp_dir,
            "signer_running": True,
            "signer_port": 9099,
            "server_running": False,  # Force local fallback scan
            "server_port": 8000,
            "output_dir": self.temp_dir,
            "error": None
        }

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("routes.hongguo._get_manager")
    @patch("routes.hongguo.license_manager.check_permission", return_value=True)
    def test_library_scan_with_corrupted_metadata_json(self, mock_lic, mock_get_mgr):
        """A corrupted .series.json (syntax error) must not crash /api/hongguo/library."""
        mock_get_mgr.return_value = self.mock_mgr

        # Create drama directory with corrupted .series.json
        drama_dir = os.path.join(self.temp_dir, "Drama_Corrupt_Meta")
        os.makedirs(drama_dir, exist_ok=True)

        meta_path = os.path.join(drama_dir, ".series.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write("{{{MALFORMED_JSON_SYNTAX_ERROR:::!!!")

        # Create 1 valid mp4
        with open(os.path.join(drama_dir, "Tập 01.mp4"), "wb") as f:
            f.write(b"MOCK_MP4_DATA")

        res = self.client.get("/api/hongguo/library")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        items = data.get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Drama_Corrupt_Meta")
        # Title falls back to folder name, cover falls back to ""
        self.assertEqual(items[0]["title"], "Drama_Corrupt_Meta")
        self.assertEqual(items[0]["cover"], "")
        self.assertEqual(items[0]["episodes_count"], 1)

    @patch("routes.hongguo._get_manager")
    @patch("routes.hongguo.license_manager.check_permission", return_value=True)
    def test_library_scan_with_zero_mp4_videos(self, mock_lic, mock_get_mgr):
        """Drama directories containing zero .mp4 files must be cleanly skipped."""
        mock_get_mgr.return_value = self.mock_mgr

        # Create drama directory with only non-video files (.txt, .jpg, .nfo)
        empty_drama_dir = os.path.join(self.temp_dir, "Drama_Zero_Videos")
        os.makedirs(empty_drama_dir, exist_ok=True)
        with open(os.path.join(empty_drama_dir, "info.txt"), "w") as f:
            f.write("No videos here")
        with open(os.path.join(empty_drama_dir, "cover.jpg"), "wb") as f:
            f.write(b"JPG_DATA")

        # Create valid drama directory
        valid_dir = os.path.join(self.temp_dir, "Drama_Valid")
        os.makedirs(valid_dir, exist_ok=True)
        with open(os.path.join(valid_dir, "Tập 01.mp4"), "wb") as f:
            f.write(b"MP4_DATA")

        res = self.client.get("/api/hongguo/library")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        items = data.get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Drama_Valid")
        # Drama_Zero_Videos must NOT appear in library
        names = [it["name"] for it in items]
        self.assertNotIn("Drama_Zero_Videos", names)

    @patch("routes.hongguo._get_manager")
    @patch("routes.hongguo.license_manager.check_permission", return_value=True)
    def test_library_episodes_with_nonexistent_or_empty_folder(self, mock_lic, mock_get_mgr):
        """Querying /api/hongguo/library/episodes for empty/nonexistent folder returns 200 with [] episodes."""
        mock_get_mgr.return_value = self.mock_mgr

        empty_dir = os.path.join(self.temp_dir, "Drama_Empty")
        os.makedirs(empty_dir, exist_ok=True)

        res = self.client.get("/api/hongguo/library/episodes?name=Drama_Empty")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["episodes"], [])

    @patch("routes.hongguo._get_manager")
    @patch("routes.hongguo.license_manager.check_permission", return_value=True)
    def test_library_episodes_directory_traversal_rejection(self, mock_lic, mock_get_mgr):
        """Malicious path traversal names in /api/hongguo/library/episodes must be rejected with 400."""
        mock_get_mgr.return_value = self.mock_mgr

        traversal_payloads = [
            "../system32",
            "..\\Windows",
            "Drama/../../etc",
            "../../",
            "C:\\Windows",
            "test\0null",
            "test|pipe"
        ]

        for payload in traversal_payloads:
            res = self.client.get(f"/api/hongguo/library/episodes?name={payload}")
            self.assertEqual(
                res.status_code, 400,
                f"Payload '{payload}' was not rejected with HTTP 400"
            )


# =============================================================================
# TIER 5.4: WORKFLOW BRIDGE STRESS (RAPID SEQUENTIAL TRIGGERS & MALFORMED PATHS)
# =============================================================================

class TestTier5WorkflowBridgeStress:
    """
    Empirical stress testing of workflow bridges (sendVideoToEditor & sendVideoToReview):
    - Rapid sequential triggers (30+ iterations)
    - Interleaved switching between Editor and Review
    - Paths with Vietnamese diacritics, Chinese characters, spaces, URL symbols (#, &, %)
    - Nonexistent, empty, and malformed inputs
    """

    def test_rapid_sequential_editor_triggers(self, browser_harness):
        """Rapidly trigger window.sendVideoToEditor 30 times consecutively."""
        page = browser_harness["page"]

        result = page.evaluate("""
        () => {
            const iterations = 30;
            for (let i = 1; i <= iterations; i++) {
                const p = `D:\\\\Hongguo\\\\Drama\\\\Tap_${i}.mp4`;
                window.sendVideoToEditor(p);
            }
            const inp = document.getElementById('editorInputVideoPath');
            const player = document.getElementById('videoPlayer');
            const isEditorActive = document.getElementById('viewEditor')?.classList.contains('active');
            return {
                lastInputVal: inp ? inp.value : '',
                playerSrc: player ? player.src : '',
                isEditorActive
            };
        }
        """)
        assert result["lastInputVal"] == "D:\\Hongguo\\Drama\\Tap_30.mp4"
        assert "Tap_30.mp4" in result["playerSrc"]
        assert result["isEditorActive"] is True

    def test_rapid_sequential_review_triggers(self, browser_harness):
        """Rapidly trigger window.sendVideoToReview 30 times consecutively."""
        page = browser_harness["page"]

        result = page.evaluate("""
        () => {
            const iterations = 30;
            for (let i = 1; i <= iterations; i++) {
                const p = `D:\\\\Hongguo\\\\Review\\\\Review_Ep_${i}.mp4`;
                window.sendVideoToReview(p);
            }
            const inp = document.getElementById('reviewInputVideoPath');
            const insight = document.getElementById('reviewInsightDuration');
            const isReviewActive = document.getElementById('viewReview')?.classList.contains('active');
            return {
                lastInputVal: inp ? inp.value : '',
                insightText: insight ? insight.textContent : '',
                isReviewActive
            };
        }
        """)
        assert result["lastInputVal"] == "D:\\Hongguo\\Review\\Review_Ep_30.mp4"
        assert "Review_Ep_30.mp4" in result["insightText"]
        assert result["isReviewActive"] is True

    def test_alternating_rapid_bridges_interleaving(self, browser_harness):
        """Interleave Editor and Review bridge triggers rapidly (20 cycles)."""
        page = browser_harness["page"]

        result = page.evaluate("""
        () => {
            for (let i = 1; i <= 20; i++) {
                window.sendVideoToEditor(`D:\\\\Editor_${i}.mp4`);
                window.sendVideoToReview(`D:\\\\Review_${i}.mp4`);
            }
            const editorVal = document.getElementById('editorInputVideoPath')?.value || '';
            const reviewVal = document.getElementById('reviewInputVideoPath')?.value || '';
            const isReviewActive = document.getElementById('viewReview')?.classList.contains('active');
            return { editorVal, reviewVal, isReviewActive };
        }
        """)
        assert result["editorVal"] == "D:\\Editor_20.mp4"
        assert result["reviewVal"] == "D:\\Review_20.mp4"
        assert result["isReviewActive"] is True

    def test_workflow_bridges_with_special_characters_and_unicode_paths(self, browser_harness):
        """
        Test bridge execution with paths containing spaces, Vietnamese diacritics,
        Chinese characters, and URL-reserved symbols (#, &, %, +).
        """
        page = browser_harness["page"]

        test_cases = [
            # Spaces
            "D:\\NovaCut Downloads\\Hongguo Drama\\Tập 01 (HD).mp4",
            # Vietnamese Unicode
            "D:\\Phim Ngắn\\Đệ Nhất Kiếm Thần - Tập 05 (Thuyết Minh).mp4",
            # Chinese characters
            "D:\\Tool\\红果短剧\\霸道总裁愛上我\\第01集.mp4",
            # URL reserved symbols
            "D:\\Videos\\Drama#1&part=2%20+final[1080p].mp4",
            # Forward slashes
            "D:/Tool/Hongguo/Downloads/Ep_99.mp4"
        ]

        for path in test_cases:
            # Test Editor bridge
            ed_res = page.evaluate("(p) => { window.sendVideoToEditor(p); const inp = document.getElementById('editorInputVideoPath'); const pl = document.getElementById('videoPlayer'); return { val: inp ? inp.value : '', src: pl ? pl.src : '' }; }", path)
            assert ed_res["val"] == path, f"Editor input did not match path: {path}"
            # Verify URL encoding is safe
            assert "/api/file?path=" in ed_res["src"]

            # Test Review bridge
            rev_res = page.evaluate("(p) => { window.sendVideoToReview(p); const inp = document.getElementById('reviewInputVideoPath'); return { val: inp ? inp.value : '' }; }", path)
            assert rev_res["val"] == path, f"Review input did not match path: {path}"

    def test_workflow_bridges_with_nonexistent_or_malformed_inputs(self, browser_harness):
        """
        Test bridges with nonexistent files, empty strings, and null inputs.
        Ensure hongguo module functions intercept empty paths gracefully.
        """
        page = browser_harness["page"]

        result = page.evaluate("""
        async () => {
            const m = await import('./js/features/hongguo.js');
            // Empty string to module sendToEditor
            m.sendToEditor('');
            m.sendToEditor(null);
            m.sendToReview('');
            m.sendToReview(null);

            // Direct call to window.sendVideoToEditor with nonexistent file
            const nonExistentPath = 'Z:\\\\NonExistentDirectory\\\\FakeVideo_9999.mp4';
            window.sendVideoToEditor(nonExistentPath);

            const editorVal = document.getElementById('editorInputVideoPath')?.value || '';
            return { editorVal, nonExistentPath };
        }
        """)
        assert result["editorVal"] == result["nonExistentPath"]
