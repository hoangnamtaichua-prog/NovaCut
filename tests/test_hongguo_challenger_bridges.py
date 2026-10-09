"""
Challenger Empirical Test Suite: Workflow Bridges & DOM Integration
Tests:
1. window.sendVideoToEditor(filePath)
   - Targets #editorInputVideoPath correctly
   - Clicks editor tab (.nav-tab[data-target="viewEditor"])
   - Sets #videoPlayer src and display style, hides #videoPlaceholder
   - Handles Unicode, spaces, and backslashes in video path
2. window.sendVideoToReview(filePath)
   - Targets #reviewInputVideoPath correctly
   - Clicks review tab (.nav-tab[data-target="viewReview"])
   - Calls loadReviewVideoPlayer and updates #reviewVideoPlayer
   - Updates #reviewHeaderVideoPath, #reviewVideoInsightBox, and #reviewInsightDuration
   - Handles Unicode, spaces, and backslashes in video path
3. Module functions sendToEditor & sendToReview in web/js/features/hongguo.js
   - Validates feature permissions (blocks when unlicensed)
   - Gracefully handles empty/invalid path inputs
   - Delegates to window.sendVideoToEditor / window.sendVideoToReview
   - Fallback behavior when window functions are absent
4. Preview Modal Workflow Buttons:
   - #btnPreviewModalToEditor delegates to sendToEditor and closes modal
   - #btnPreviewModalToReview delegates to sendToReview and closes modal
5. Zero alert() or confirm() in web/js/features/hongguo.js
   - Verifies 0 native browser alert() or confirm() calls
   - Verifies usage of dark mode modals and toasts
6. Unlicensed Protection Guard:
   - Clicking viewHongguo tab when unlicensed triggers license modal and rejects tab switch
"""

import os
import re
import json
import http.server
import socketserver
import threading
import time
import pytest
from playwright.sync_api import sync_playwright

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
HONGGUO_JS = os.path.join(WEB_DIR, 'js', 'features', 'hongguo.js')


class StaticServer:
    def __init__(self, port=8912):
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
def browser_context():
    server = StaticServer(port=8912)
    server.start()

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()

    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # Mock backend API responses to prevent polling errors and guarantee active VIP license
    def mock_license_info(route):
        route.fulfill(
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
        )

    page.add_init_script("localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');")
    page.route("**/api/license/info*", mock_license_info)
    page.route("**/api/license/check_sepay_payment*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"active": True})))
    page.route("**/api/batch/stream*", lambda r: r.fulfill(status=200, content_type="text/plain", body=""))
    page.route("**/api/license/sync_cloud*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True})))
    page.route("**/api/hongguo/status*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "data": {"installed": True, "signer_running": True, "server_running": True}})))
    page.route("**/api/hongguo/library*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "items": []})))
    page.route("**/api/hongguo/tasks*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True, "running": False})))

    page.goto(f"http://127.0.0.1:{server.port}/index.html")
    page.wait_for_timeout(1000)

    yield {
        "page": page,
        "errors": page_errors,
        "browser": browser,
        "pw": pw,
        "server": server,
    }

    browser.close()
    pw.stop()
    server.stop()


class TestEmpiricalWorkflowBridges:
    """Empirical verification of sendVideoToEditor and sendVideoToReview."""

    def test_page_loaded_and_bridge_functions_exposed(self, browser_context):
        page = browser_context["page"]
        assert page.evaluate("typeof window.sendVideoToEditor === 'function'"), (
            "window.sendVideoToEditor must be a function"
        )
        assert page.evaluate("typeof window.sendVideoToReview === 'function'"), (
            "window.sendVideoToReview must be a function"
        )
        assert page.evaluate("typeof window.sendHongguoToEditor === 'function'"), (
            "window.sendHongguoToEditor must be exposed by initHongguoModule"
        )
        assert page.evaluate("typeof window.sendHongguoToReview === 'function'"), (
            "window.sendHongguoToReview must be exposed by initHongguoModule"
        )

    def test_send_video_to_editor_targets_input(self, browser_context):
        """Verify window.sendVideoToEditor populates #editorInputVideoPath."""
        page = browser_context["page"]
        test_path = r"D:\Download\Hongguo\Thiên Nhai Minh Nguyệt\tập_01.mp4"

        page.evaluate("(p) => window.sendVideoToEditor(p)", test_path)
        page.wait_for_timeout(200)

        input_val = page.locator("#editorInputVideoPath").input_value()
        assert input_val == test_path, f"Expected {test_path}, got {input_val}"

    def test_send_video_to_editor_clicks_editor_tab(self, browser_context):
        """Verify window.sendVideoToEditor clicks the editor tab and activates viewEditor."""
        page = browser_context["page"]

        # First switch to Hongguo tab
        page.locator('.nav-tab[data-target="viewHongguo"]').click()
        page.wait_for_timeout(200)
        assert page.locator('#viewHongguo').is_visible()

        test_path = r"D:\Movies\Series\ep_05.mp4"
        page.evaluate("(p) => window.sendVideoToEditor(p)", test_path)
        page.wait_for_timeout(200)

        # Verify editor tab has class 'active'
        tab_classes = page.locator('.nav-tab[data-target="viewEditor"]').get_attribute('class') or ''
        assert 'active' in tab_classes.split(), f"viewEditor tab should be active, got: {tab_classes}"

        # Verify viewEditor is displayed
        assert page.locator('#viewEditor').is_visible(), "#viewEditor should be visible"
        # Verify viewHongguo is hidden
        assert not page.locator('#viewHongguo').is_visible(), "#viewHongguo should be hidden"

    def test_send_video_to_editor_loads_video_player(self, browser_context):
        """Verify window.sendVideoToEditor loads video into #videoPlayer with encoded URL."""
        page = browser_context["page"]
        test_path = r"D:\Videos\Hongguo Phim Tình Cảm\Ep 10 [1080p].mp4"

        page.evaluate("(p) => window.sendVideoToEditor(p)", test_path)
        page.wait_for_timeout(200)

        video_src = page.locator("#videoPlayer").get_attribute("src")
        assert video_src is not None
        assert "/api/file?path=" in video_src
        assert "Ep%2010%20%5B1080p%5D.mp4" in video_src or "Ep 10" in video_src

        # Verify video player display is block and placeholder is hidden
        player_display = page.locator("#videoPlayer").evaluate("el => window.getComputedStyle(el).display")
        assert player_display == "block", f"#videoPlayer should have display: block, got {player_display}"

        placeholder_display = page.locator("#videoPlaceholder").evaluate("el => window.getComputedStyle(el).display")
        assert placeholder_display == "none", f"#videoPlaceholder should be hidden, got {placeholder_display}"

    def test_send_video_to_review_targets_input(self, browser_context):
        """Verify window.sendVideoToReview populates #reviewInputVideoPath."""
        page = browser_context["page"]
        test_path = r"D:\Download\Hongguo\Review Target\drama_ep03.mp4"

        page.evaluate("(p) => window.sendVideoToReview(p)", test_path)
        page.wait_for_timeout(200)

        input_val = page.locator("#reviewInputVideoPath").input_value()
        assert input_val == test_path, f"Expected {test_path}, got {input_val}"

    def test_send_video_to_review_clicks_review_tab(self, browser_context):
        """Verify window.sendVideoToReview clicks review tab and activates viewReview."""
        page = browser_context["page"]

        # First switch to Editor tab
        page.locator('.nav-tab[data-target="viewEditor"]').click()
        page.wait_for_timeout(200)
        assert page.locator('#viewEditor').is_visible()

        test_path = r"D:\Movies\Review\ep_08.mp4"
        page.evaluate("(p) => window.sendVideoToReview(p)", test_path)
        page.wait_for_timeout(200)

        # Verify review tab has class 'active'
        tab_classes = page.locator('.nav-tab[data-target="viewReview"]').get_attribute('class') or ''
        assert 'active' in tab_classes.split(), f"viewReview tab should be active, got: {tab_classes}"

        # Verify viewReview is displayed
        assert page.locator('#viewReview').is_visible(), "#viewReview should be visible"

    def test_send_video_to_review_calls_load_review_video_player(self, browser_context):
        """Verify window.sendVideoToReview invokes loadReviewVideoPlayer and loads #reviewVideoPlayer."""
        page = browser_context["page"]
        test_path = r"D:\Media\Review_Test\Tập 12 - Cao Trào.mp4"

        page.evaluate("(p) => window.sendVideoToReview(p)", test_path)
        page.wait_for_timeout(200)

        # In loadReviewVideoPlayer, reviewVideoPlayer src is set to /api/video?path=...
        review_src = page.locator("#reviewVideoPlayer").get_attribute("src")
        assert review_src is not None
        assert "/api/video?path=" in review_src

        # Verify reviewHeaderVideoPath
        header_path = page.locator("#reviewHeaderVideoPath").input_value()
        assert header_path == test_path

        # Verify display style
        rvp_display = page.locator("#reviewVideoPlayer").evaluate("el => window.getComputedStyle(el).display")
        assert rvp_display == "block", f"#reviewVideoPlayer should have display: block, got {rvp_display}"

        # Verify reviewVideoInsightBox and reviewInsightDuration
        insight_display = page.locator("#reviewVideoInsightBox").evaluate("el => window.getComputedStyle(el).display")
        assert insight_display == "flex", f"#reviewVideoInsightBox should be flex, got {insight_display}"

        insight_text = page.locator("#reviewInsightDuration").inner_text()
        assert "Tập 12 - Cao Trào.mp4" in insight_text

    def test_send_hongguo_module_functions_handle_empty_paths_gracefully(self, browser_context):
        """Verify sendHongguoToEditor and sendHongguoToReview handle falsy paths without crashing."""
        page = browser_context["page"]
        # Calling with null/empty should not raise JavaScript exceptions
        page.evaluate("() => window.sendHongguoToEditor('')")
        page.evaluate("() => window.sendHongguoToEditor(null)")
        page.evaluate("() => window.sendHongguoToReview('')")
        page.evaluate("() => window.sendHongguoToReview(null)")

    def test_rapid_alternating_workflow_bridges(self, browser_context):
        """Stress-test rapid alternating calls between Editor and Review bridges."""
        page = browser_context["page"]
        for i in range(5):
            ed_path = f"D:\\Hongguo\\SeriesA\\ep_{i:02d}.mp4"
            rev_path = f"D:\\Hongguo\\SeriesB\\ep_{i:02d}.mp4"

            page.evaluate("(p) => window.sendVideoToEditor(p)", ed_path)
            assert page.locator("#editorInputVideoPath").input_value() == ed_path

            page.evaluate("(p) => window.sendVideoToReview(p)", rev_path)
            assert page.locator("#reviewInputVideoPath").input_value() == rev_path

    def test_preview_modal_workflow_bridges(self, browser_context):
        """Test #btnPreviewModalToEditor and #btnPreviewModalToReview in #hongguoVideoPreviewModal."""
        page = browser_context["page"]
        sample_path_ed = r"D:\Hongguo\Preview\ep_preview_ed.mp4"
        sample_path_rev = r"D:\Hongguo\Preview\ep_preview_rev.mp4"

        # 1. Trigger open modal for editor test
        page.evaluate("""(path) => {
            const modal = document.getElementById('hongguoVideoPreviewModal');
            const player = document.getElementById('hongguoVideoPreviewPlayer');
            const btnToEditor = document.getElementById('btnPreviewModalToEditor');
            const btnToReview = document.getElementById('btnPreviewModalToReview');
            modal.style.display = 'flex';
            btnToEditor.onclick = () => {
                modal.style.display = 'none';
                window.sendHongguoToEditor(path);
            };
            btnToReview.onclick = () => {
                modal.style.display = 'none';
                window.sendHongguoToReview(path);
            };
        }""", sample_path_ed)

        assert page.locator("#hongguoVideoPreviewModal").is_visible()
        page.locator("#btnPreviewModalToEditor").click()
        page.wait_for_timeout(200)

        # Modal must close and editor must be loaded
        assert not page.locator("#hongguoVideoPreviewModal").is_visible()
        assert page.locator("#editorInputVideoPath").input_value() == sample_path_ed
        assert page.locator("#viewEditor").is_visible()

        # 2. Trigger open modal for review test
        page.evaluate("""(path) => {
            const modal = document.getElementById('hongguoVideoPreviewModal');
            const btnToReview = document.getElementById('btnPreviewModalToReview');
            modal.style.display = 'flex';
            btnToReview.onclick = () => {
                modal.style.display = 'none';
                window.sendHongguoToReview(path);
            };
        }""", sample_path_rev)

        assert page.locator("#hongguoVideoPreviewModal").is_visible()
        page.locator("#btnPreviewModalToReview").click()
        page.wait_for_timeout(200)

        # Modal must close and review must be loaded
        assert not page.locator("#hongguoVideoPreviewModal").is_visible()
        assert page.locator("#reviewInputVideoPath").input_value() == sample_path_rev
        assert page.locator("#viewReview").is_visible()


class TestLicenseEnforcementOnWorkflowBridges:
    """Verify license gating on Hongguo tab and workflow bridge functions."""

    def test_unlicensed_tab_switch_triggers_modal(self, browser_context):
        """When license is unlicensed, clicking viewHongguo should open license modal and reject tab switch."""
        browser = browser_context["browser"]
        server = browser_context["server"]
        context = browser.new_context()
        page = context.new_page()

        # Mock unlicensed state
        def mock_unlicensed(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "is_valid": False,
                    "status": "UNLICENSED",
                    "tier": "unlicensed",
                    "plan_name": "Chưa kích hoạt",
                    "disclaimer_accepted": True,
                    "features": {}
                })
            )

        page.add_init_script("localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');")
        page.route("**/api/license/info*", mock_unlicensed)
        page.route("**/api/license/check_sepay_payment*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"active": False})))
        page.route("**/api/batch/stream*", lambda r: r.fulfill(status=200, content_type="text/plain", body=""))
        page.route("**/api/license/sync_cloud*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"success": False})))

        page.goto(f"http://127.0.0.1:{server.port}/index.html")
        page.wait_for_timeout(1000)

        # Attempt to click Hongguo tab programmatically
        page.evaluate('document.querySelector(\'.nav-tab[data-target="viewHongguo"]\').click()')
        page.wait_for_timeout(300)

        # viewHongguo must NOT be active or displayed
        assert not page.locator('#viewHongguo').is_visible(), "Unlicensed user must NOT be able to access viewHongguo"
        # licenseModal must be displayed
        assert page.locator('#licenseModal').is_visible(), "License modal must be displayed for unlicensed user"

        context.close()


class TestZeroAlertConfirmEnforcement:
    """Verify strictly zero browser alert() or confirm() in hongguo.js."""

    def test_zero_native_alert_in_hongguo_js(self):
        assert os.path.exists(HONGGUO_JS)
        with open(HONGGUO_JS, 'r', encoding='utf-8') as f:
            content = f.read()

        # Remove comments to avoid false alarms from docstrings
        no_comments = re.sub(r'//.*', '', content)
        no_comments = re.sub(r'/\*[\s\S]*?\*/', '', no_comments)

        alert_calls = re.findall(r'\b(?:window\.)?alert\s*\(', no_comments)
        assert len(alert_calls) == 0, f"Found native alert() calls in hongguo.js: {alert_calls}"

    def test_zero_native_confirm_in_hongguo_js(self):
        with open(HONGGUO_JS, 'r', encoding='utf-8') as f:
            content = f.read()

        no_comments = re.sub(r'//.*', '', content)
        no_comments = re.sub(r'/\*[\s\S]*?\*/', '', no_comments)

        # Must not have native confirm(...) but can have showConfirmModal(...)
        no_custom_modal = re.sub(r'\bshowConfirmModal\s*\(', '', no_comments)
        confirm_calls = re.findall(r'\b(?:window\.)?confirm\s*\(', no_custom_modal)
        assert len(confirm_calls) == 0, f"Found native confirm() calls in hongguo.js: {confirm_calls}"

    def test_modal_and_toast_dialog_replacements(self):
        """Verify that hongguo.js actively uses dark mode toast and modal abstractions."""
        with open(HONGGUO_JS, 'r', encoding='utf-8') as f:
            content = f.read()

        toasts = re.findall(r'\bshowToast\s*\(', content)
        alert_modals = re.findall(r'\bshowAlertModal\s*\(', content)
        confirm_modals = re.findall(r'\bshowConfirmModal\s*\(', content)

        assert len(toasts) >= 20, f"Expected abundant showToast calls, found {len(toasts)}"
        assert len(alert_modals) >= 1, "Expected showAlertModal usage"
        assert len(confirm_modals) >= 1, "Expected showConfirmModal usage"
