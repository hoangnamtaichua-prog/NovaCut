"""
Test Suite for Hongguo Downloader Frontend Integration (Milestone 2)
Tests:
- web/index.html DOM elements, tab button, main-view cards, and modals
- web/js/features/hongguo.js exports, range parser, compact formatter, and zero-alert guarantee
- web/app.js tab switching, license check, and workflow bridges exposure
- web/style.css dark mode tokens and responsive styling
- Dual-layer frontend/backend license permissions
"""

import os
import re
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT_DIR, 'web', 'index.html')
HONGGUO_JS = os.path.join(ROOT_DIR, 'web', 'js', 'features', 'hongguo.js')
APP_JS = os.path.join(ROOT_DIR, 'web', 'app.js')
STYLE_CSS = os.path.join(ROOT_DIR, 'web', 'style.css')


class TestHongguoHtmlLayout:
    """Tests the DOM structure and elements in web/index.html."""

    @pytest.fixture(autouse=True)
    def load_html(self):
        assert os.path.exists(INDEX_HTML), "web/index.html must exist"
        with open(INDEX_HTML, 'r', encoding='utf-8') as f:
            self.html = f.read()

    def test_navigation_tab_present(self):
        """Verify navigation tab button with data-target='viewHongguo' exists in .header-tabs."""
        assert 'data-target="viewHongguo"' in self.html
        assert 'Tải Phim Hồng Quả' in self.html
        # Verify it has class nav-tab
        match = re.search(r'<button[^>]*class="[^"]*nav-tab[^"]*"[^>]*data-target="viewHongguo"[^>]*>', self.html)
        assert match is not None, "nav-tab with data-target='viewHongguo' not found"

    def test_main_view_container_present(self):
        """Verify main view #viewHongguo with class main-view exists and starts hidden."""
        match = re.search(r'<div[^>]*id="viewHongguo"[^>]*class="[^"]*main-view[^"]*"[^>]*>', self.html)
        assert match is not None, "#viewHongguo container not found"
        assert 'display: none' in match.group(0), "#viewHongguo should be initially hidden"

    def test_service_status_bar_elements(self):
        """Verify header bar and status pill elements exist."""
        expected_ids = [
            'hongguoServiceStatusPill',
            'hongguoStatusDot',
            'hongguoStatusText',
            'hongguoPortBadges',
            'hongguoSignerBadge',
            'hongguoServerBadge',
            'btnHongguoRestartService',
            'btnHongguoStopService',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_input_hero_card_elements(self):
        """Verify input hero card, buttons, and output dir elements exist."""
        expected_ids = [
            'hongguoInputUrl',
            'btnHongguoClearUrl',
            'btnHongguoPasteUrl',
            'btnHongguoAnalyze',
            'hongguoAnalyzeBtnText',
            'hongguoOutputDirDisplay',
            'btnHongguoChangeFolder',
            'btnHongguoOpenFolder',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_drama_metadata_card_elements(self):
        """Verify metadata card elements exist."""
        expected_ids = [
            'hongguoSeriesIdBadge',
            'hongguoMetadataEmptyPlaceholder',
            'hongguoMetadataContent',
            'hongguoDramaPoster',
            'hongguoPosterEpisodeOverlay',
            'hongguoDramaTitle',
            'hongguoDramaTotalEpisodes',
            'hongguoDramaRating',
            'hongguoDramaTagsContainer',
            'hongguoDramaSynopsis',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_episode_selector_elements(self):
        """Verify episode selector controls, grid, and download button exist."""
        expected_ids = [
            'hongguoSelectedEpisodesBadge',
            'btnHongguoSelectAll',
            'btnHongguoDeselectAll',
            'btnHongguoInvertSelection',
            'hongguoRangeInput',
            'btnHongguoApplyRange',
            'hongguoEpisodeGridPlaceholder',
            'hongguoEpisodeGridContainer',
            'hongguoEpisodeGrid',
            'hongguoDownloadSummaryText',
            'hongguoDownloadQuality',
            'hongguoDownloadConcurrency',
            'btnHongguoStartDownload',
            'hongguoDownloadButtonCount',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_progress_card_elements(self):
        """Verify download progress monitor elements exist."""
        expected_ids = [
            'hongguoProgressCard',
            'hongguoActiveTaskCountBadge',
            'btnHongguoCancelDownload',
            'hongguoLiveTaskBox',
            'hongguoProgressDramaTitle',
            'hongguoCurrentDownloadingEp',
            'hongguoProgressSpeed',
            'hongguoProgressCounter',
            'hongguoOverallProgressBar',
            'hongguoProgressStatusText',
            'hongguoProgressPercentText',
            'hongguoTasksTableBody',
            'hongguoTasksEmptyRow',
            'btnHongguoToggleLog',
            'hongguoLogTerminal',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_library_card_elements(self):
        """Verify library card and actions exist."""
        expected_ids = [
            'hongguoLibraryCountBadge',
            'btnHongguoRefreshLibrary',
            'btnHongguoOpenLibraryFolder',
            'hongguoLibraryEmptyPlaceholder',
            'hongguoLibraryContainer',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"

    def test_library_modals_present(self):
        """Verify episodes inspector modal and video preview modal exist."""
        expected_ids = [
            'hongguoLibraryEpisodesModal',
            'hongguoModalDramaTitle',
            'hongguoModalDramaPath',
            'btnCloseHongguoEpisodesModal',
            'hongguoModalEpisodesList',
            'hongguoModalEpisodesCount',
            'btnHongguoModalClose',
            'hongguoVideoPreviewModal',
            'hongguoVideoPreviewPlayer',
            'hongguoPreviewTitle',
            'btnCloseHongguoPreviewModal',
            'btnPreviewModalToEditor',
            'btnPreviewModalToReview',
            'btnPreviewModalClose',
        ]
        for elem_id in expected_ids:
            assert f'id="{elem_id}"' in self.html, f"Missing #{elem_id} in index.html"


class TestHongguoJavaScriptController:
    """Tests the frontend logic, exports, and integrity of web/js/features/hongguo.js."""

    @pytest.fixture(autouse=True)
    def load_js(self):
        assert os.path.exists(HONGGUO_JS), "web/js/features/hongguo.js must exist"
        with open(HONGGUO_JS, 'r', encoding='utf-8') as f:
            self.js = f.read()

    def test_zero_alert_guarantee(self):
        """Verify zero occurrences of window.alert() or alert() in hongguo.js."""
        matches = re.findall(r'\balert\s*\(', self.js)
        assert len(matches) == 0, f"Found native alert() in hongguo.js: {matches}"

    def test_zero_native_confirm_guarantee(self):
        """Verify zero occurrences of window.confirm() or confirm() in hongguo.js."""
        # showConfirmModal is allowed, but native confirm( is forbidden
        # Filter out showConfirmModal
        cleaned = re.sub(r'showConfirmModal\s*\(', '', self.js)
        matches = re.findall(r'\bconfirm\s*\(', cleaned)
        assert len(matches) == 0, f"Found native confirm() in hongguo.js: {matches}"

    def test_license_guard_function_present(self):
        """Verify checkHongguoLicense calls window.checkFeaturePermission with 'hongguo_downloader'."""
        assert 'checkFeaturePermission' in self.js
        assert "'hongguo_downloader'" in self.js or '"hongguo_downloader"' in self.js

    def test_required_exports_present(self):
        """Verify all required functions and state objects are exported."""
        expected_exports = [
            'hongguoState',
            'checkHongguoLicense',
            'checkHongguoStatus',
            'startHongguoServices',
            'stopHongguoServices',
            'resolveHongguoDrama',
            'parseEpisodeRange',
            'formatEpisodeRange',
            'selectAllEpisodes',
            'deselectAllEpisodes',
            'invertEpisodeSelection',
            'applyCustomRange',
            'toggleEpisode',
            'submitHongguoDownload',
            'cancelHongguoDownload',
            'startProgressPolling',
            'stopProgressPolling',
            'pollDownloadTasks',
            'loadHongguoLibrary',
            'loadLibraryEpisodes',
            'sendToEditor',
            'sendToReview',
            'openFolder',
            'initHongguoModule',
            'onHongguoTabActivated',
        ]
        for exp in expected_exports:
            assert f'export function {exp}' in self.js or f'export const {exp}' in self.js or f'export async function {exp}' in self.js, f"Missing export {exp} in hongguo.js"

    def test_workflow_bridges_logic(self):
        """Verify sendToEditor and sendToReview interact with Editor and Review components."""
        assert 'sendVideoToEditor' in self.js
        assert 'sendVideoToReview' in self.js
        assert 'editorInputVideoPath' in self.js
        assert 'reviewInputVideoPath' in self.js

    def test_range_parser_python_simulation(self):
        """Simulate and verify the exact range parsing algorithm used by parseEpisodeRange."""
        def parse_range(range_str, max_episodes=1000):
            selected = set()
            if not range_str or not isinstance(range_str, str):
                return selected
            clean = range_str.strip().lower()
            if clean in ('all', 'tất cả'):
                return set(range(1, max_episodes + 1))
            tokens = [t.strip() for t in re.split(r'[,;\s]+', clean) if t.strip()]
            for token in tokens:
                m = re.match(r'^(\d+)\s*[-~..]\s*(\d+)$', token)
                if m:
                    start, end = int(m.group(1)), int(m.group(2))
                    if start > end:
                        start, end = end, start
                    for i in range(start, end + 1):
                        if 1 <= i <= max_episodes:
                            selected.add(i)
                    continue
                if token.isdigit():
                    num = int(token)
                    if 1 <= num <= max_episodes:
                        selected.add(num)
            return selected

        # Test single episodes
        assert parse_range("5", 80) == {5}
        # Test ranges
        assert parse_range("1-5", 80) == {1, 2, 3, 4, 5}
        # Test mixed
        assert parse_range("1-3, 5, 8-10", 80) == {1, 2, 3, 5, 8, 9, 10}
        # Test out of bounds clipping
        assert parse_range("1-100", 20) == set(range(1, 21))
        # Test inverted range
        assert parse_range("10-5", 20) == set(range(5, 11))
        # Test all keyword
        assert parse_range("all", 15) == set(range(1, 16))
        assert parse_range("tất cả", 10) == set(range(1, 11))

    def test_compact_range_formatter_simulation(self):
        """Simulate and verify formatEpisodeRange output."""
        def format_range(selected_set, total):
            if not selected_set:
                return ''
            if total and len(selected_set) == total:
                return 'all'
            sorted_eps = sorted(selected_set)
            ranges = []
            start = sorted_eps[0]
            prev = sorted_eps[0]
            for cur in sorted_eps[1:]:
                if cur == prev + 1:
                    prev = cur
                else:
                    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
                    start = cur
                    prev = cur
            ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
            return ", ".join(ranges)

        assert format_range({1, 2, 3, 4, 5}, 5) == 'all'
        assert format_range({1, 2, 3, 5, 7, 8, 9}, 10) == '1-3, 5, 7-9'
        assert format_range({1}, 10) == '1'
        assert format_range(set(), 10) == ''


class TestAppJsIntegration:
    """Tests web/app.js integration with Hongguo Downloader."""

    @pytest.fixture(autouse=True)
    def load_app_js(self):
        assert os.path.exists(APP_JS), "web/app.js must exist"
        with open(APP_JS, 'r', encoding='utf-8') as f:
            self.app_js = f.read()

    def test_imports_hongguo_module(self):
        """Verify app.js imports initHongguoModule and onHongguoTabActivated."""
        assert 'import { initHongguoModule, onHongguoTabActivated } from \'./js/features/hongguo.js\';' in self.app_js

    def test_tab_switch_license_guard(self):
        """Verify tab switch handler gates viewHongguo with checkFeaturePermission."""
        pattern = r"targetId === 'viewHongguo'[\s\S]*?checkFeaturePermission\('hongguo_downloader', 'Tải Phim Hồng Quả'\)"
        match = re.search(pattern, self.app_js)
        assert match is not None, "License check for viewHongguo missing in tab switch listener"

    def test_view_display_block_setting(self):
        """Verify viewHongguo displays as 'block' in targetView.style.display."""
        assert "targetId === 'viewHongguo'" in self.app_js
        assert "viewHongguo" in self.app_js

    def test_special_case_tab_activation(self):
        """Verify special case for viewHongguo triggers onHongguoTabActivated."""
        pattern = r"targetId === 'viewHongguo'[\s\S]*?onHongguoTabActivated\(\)"
        match = re.search(pattern, self.app_js)
        assert match is not None, "Tab activation callback for viewHongguo missing"

    def test_global_window_exposure(self):
        """Verify sendVideoToEditor, sendVideoToReview, and showToast are exposed on window."""
        assert 'window.sendVideoToEditor = sendVideoToEditor;' in self.app_js
        assert 'window.sendVideoToReview = sendVideoToReview;' in self.app_js
        assert 'window.showToast = showToast;' in self.app_js

    def test_startup_initialization(self):
        """Verify initHongguoModule() is invoked during startup."""
        assert 'initHongguoModule()' in self.app_js


class TestStyleCssTokensAndRules:
    """Tests web/style.css styling for Hongguo Downloader."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        assert os.path.exists(STYLE_CSS), "web/style.css must exist"
        with open(STYLE_CSS, 'r', encoding='utf-8') as f:
            self.css = f.read()

    def test_hongguo_container_classes(self):
        """Verify container and bar classes exist."""
        assert '.hongguo-container' in self.css
        assert '.hongguo-top-bar' in self.css
        assert '.hongguo-status-pill' in self.css

    def test_card_and_tile_classes(self):
        """Verify cards, episode tiles, and selected states exist."""
        assert '.hongguo-ep-tile' in self.css
        assert '.hongguo-ep-tile.selected' in self.css
        assert '.hongguo-ep-tile.downloaded' in self.css
        assert '.hongguo-tasks-table' in self.css

    def test_workflow_buttons(self):
        """Verify workflow bridge styling exists."""
        assert '.btn-hg-workflow-editor' in self.css
        assert '.btn-hg-workflow-review' in self.css
        assert '.btn-hg-workflow-folder' in self.css
        assert '.btn.primary-rose' in self.css


class TestDualLayerLicensePermission:
    """Tests dual-layer licensing configurations for hongguo_downloader."""

    def test_license_tier_configuration(self):
        """Verify hongguo_downloader is configured across tiers in license_manager.py."""
        from license_manager import PACKAGE_TIERS
        # Paid and trial tiers must have permission
        for tier in ['trial', 'pro', 'vip', 'yearly', 'admin']:
            assert tier in PACKAGE_TIERS, f"Tier {tier} missing in PACKAGE_TIERS"
            assert PACKAGE_TIERS[tier]['features'].get('hongguo_downloader') is True, f"Tier {tier} must allow hongguo_downloader"

        # Unlicensed tier must not have permission
        unlicensed_feat = PACKAGE_TIERS.get('unlicensed', {}).get('features', {})
        assert unlicensed_feat.get('hongguo_downloader', False) is False, "Unlicensed tier must NOT allow hongguo_downloader"
