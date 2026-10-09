/**
 * =========================================================================
 * NovaCut - Hongguo Short Drama Downloader Feature Controller
 * File: web/js/features/hongguo.js
 * 
 * Manages:
 * 1. Background Service healthcheck & lifecycle (Unidbg Signer :9099 & FastAPI :8000)
 * 2. Drama URL/ID resolution, metadata card & episode selection
 * 3. Range parser ("1-20, 25, 30-40") & visual multi-select
 * 4. Real-time download task monitoring (1-second polling & logs)
 * 5. Downloaded library explorer & quick preview
 * 6. Workflow bridges to Editor (sendToEditor) and Review (sendToReview)
 * 7. Dual-layer license protection & Zero-alert Dark Mode UX
 * =========================================================================
 */

import { showToast, showAlertModal, showConfirmModal, escapeHtml } from '../utils.js';

const getConfirmModal = () => (typeof window !== 'undefined' && window.showConfirmModal) || showConfirmModal;
const getAlertModal = () => (typeof window !== 'undefined' && window.showAlertModal) || showAlertModal;
const getToast = () => (typeof window !== 'undefined' && window.showToast) || showToast;

// =========================================================================
// 1. Module State
// =========================================================================
export const hongguoState = {
    service: {
        installed: false,
        toolDir: '',
        signerRunning: false,
        signerPort: 9099,
        serverRunning: false,
        serverPort: 8000,
        outputDir: '',
        error: null,
        isStarting: false
    },
    currentDrama: null,          // { series_id, title, total, cover, author, desc, tags, rating }
    episodes: [],               // [ { item_id, title, episode_number, duration, video_id } ]
    selectedEpisodes: new Set(),// Set of episode numbers (integers: 1, 2, 3...)
    downloadTasks: {
        running: false,
        started: 0,
        mode: 'download',
        series: [],
        log: []
    },
    library: [],                // [ { name, title, path, episodes_count, cover } ]
    activeLibraryDrama: null,   // currently viewed drama folder
    libraryEpisodes: [],        // [ { name, path, size, ep_num } ]
    pollingTimer: null,
    isPolling: false
};

// =========================================================================
// 2. License Permission Guard
// =========================================================================
export function checkHongguoLicense(actionName = 'Tải Phim Hồng Quả') {
    if (typeof window.checkFeaturePermission === 'function') {
        return window.checkFeaturePermission('hongguo_downloader', actionName);
    }
    return true;
}

export function handleLicenseError(errData) {
    const errMsg = (errData && errData.error) || 'Tính năng Tải Phim Hồng Quả yêu cầu bản quyền hợp lệ.';
    const alertFn = (typeof window !== 'undefined' && window.showAlertModal) || showAlertModal;
    const alertPromise = (alertFn === showAlertModal)
        ? showAlertModal({
            title: '⚡ Yêu Cầu Bản Quyền',
            message: errMsg,
            type: 'warning'
        })
        : alertFn({
            title: '⚡ Yêu Cầu Bản Quyền',
            message: errMsg,
            type: 'warning'
        });
    alertPromise.then(() => {
        const licenseModal = document.getElementById('licenseModal');
        if (licenseModal) {
            licenseModal.style.display = 'flex';
            if (typeof window.fetchLicenseInfo === 'function') {
                window.fetchLicenseInfo(false);
            }
        }
    });
}

// =========================================================================
// 3. API Communication Layer
// =========================================================================
async function fetchApi(endpoint, options = {}) {
    try {
        const res = await fetch(endpoint, options);
        if (res.status === 403) {
            const data = await res.json().catch(() => ({}));
            handleLicenseError(data);
            return { success: false, licenseError: true, error: data.error || 'Bị từ chối truy cập do chưa kích hoạt bản quyền.' };
        }
        const data = await res.json();
        return data;
    } catch (err) {
        return { success: false, error: 'Lỗi kết nối máy chủ: ' + err.message };
    }
}

// =========================================================================
// 4. Service Healthcheck & Management
// =========================================================================
export async function checkHongguoStatus(autoStart = false) {
    const data = await fetchApi('/api/hongguo/status');
    if (!data.success) {
        if (!data.licenseError) {
            updateServiceStatusUI(false, false, false, data.error);
        }
        return false;
    }

    const s = data.data || {};
    hongguoState.service = {
        installed: Boolean(s.installed),
        toolDir: s.tool_dir || '',
        signerRunning: Boolean(s.signer_running),
        signerPort: s.signer_port || 9099,
        serverRunning: Boolean(s.server_running),
        serverPort: s.server_port || 8000,
        outputDir: s.output_dir || '',
        error: s.error || null,
        isStarting: false
    };

    updateServiceStatusUI(
        hongguoState.service.installed,
        hongguoState.service.signerRunning,
        hongguoState.service.serverRunning,
        hongguoState.service.error
    );

    if (hongguoState.service.outputDir) {
        const outDirEl = document.getElementById('hongguoOutputDirDisplay');
        if (outDirEl) outDirEl.value = hongguoState.service.outputDir;
    }

    // Tự động kích hoạt dịch vụ nếu tool đã cài nhưng chưa bật
    if (autoStart && hongguoState.service.installed && (!hongguoState.service.signerRunning || !hongguoState.service.serverRunning)) {
        startHongguoServices();
    }

    return true;
}

export async function startHongguoServices() {
    if (hongguoState.service.isStarting) return;
    hongguoState.service.isStarting = true;
    updateServiceStartingUI(true);

    try {
        const data = await fetchApi('/api/hongguo/start', { method: 'POST' });
        if (data.success) {
            showToast('Dịch vụ nền Hồng Quả đã khởi động thành công!', 'success');
            await checkHongguoStatus(false);
        } else if (!data.licenseError) {
            showToast('Không thể bật dịch vụ Hồng Quả: ' + (data.error || 'Lỗi không xác định'), 'error');
            updateServiceStatusUI(hongguoState.service.installed, false, false, data.error);
        }
    } finally {
        hongguoState.service.isStarting = false;
        updateServiceStartingUI(false);
    }
}

export async function stopHongguoServices() {
    const confirmFn = (typeof window !== 'undefined' && window.showConfirmModal) || showConfirmModal;
    const confirmed = (confirmFn === showConfirmModal)
        ? await showConfirmModal({
            title: 'Dừng Dịch Vụ Hồng Quả',
            message: 'Bạn có chắc chắn muốn dừng toàn bộ tiến trình Signer và Server của Hồng Quả?',
            type: 'warning',
            confirmText: 'Dừng Dịch Vụ',
            cancelText: 'Hủy'
        })
        : await confirmFn({
            title: 'Dừng Dịch Vụ Hồng Quả',
            message: 'Bạn có chắc chắn muốn dừng toàn bộ tiến trình Signer và Server của Hồng Quả?',
            type: 'warning',
            confirmText: 'Dừng Dịch Vụ',
            cancelText: 'Hủy'
        });
    if (!confirmed) return;

    const data = await fetchApi('/api/hongguo/stop', { method: 'POST' });
    const toastFn = (typeof window !== 'undefined' && window.showToast) || showToast;
    if (data.success) {
        toastFn('Đã dừng toàn bộ dịch vụ Hồng Quả.', 'info');
        stopProgressPolling();
        await checkHongguoStatus(false);
    } else {
        toastFn(data.error || 'Lỗi khi dừng dịch vụ', 'error');
    }
}

// =========================================================================
// 5. Drama Resolution & Parsing
// =========================================================================
export async function resolveHongguoDrama() {
    if (!checkHongguoLicense('Phân giải link phim Hồng Quả')) return;

    const inputEl = document.getElementById('hongguoInputUrl') || document.getElementById('hongguoInputText');
    const rawText = inputEl ? inputEl.value.trim() : '';
    if (!rawText) {
        showToast('Vui lòng dán liên kết chia sẻ hoặc nhập ID phim Hồng Quả!', 'warning');
        if (inputEl) inputEl.focus();
        return;
    }

    setResolveLoading(true);

    try {
        const res = await fetchApi('/api/hongguo/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: rawText })
        });

        if (!res.success) {
            if (!res.licenseError) {
                showToast(res.error || 'Không thể phân giải thông tin phim từ liên kết này.', 'error');
            }
            return;
        }

        const resolvedList = res.resolved || [];
        if (!Array.isArray(resolvedList) || resolvedList.length === 0) {
            showToast('Không tìm thấy thông tin bộ phim nào từ dữ liệu nhập vào.', 'warning');
            return;
        }

        const drama = resolvedList[0];
        hongguoState.currentDrama = drama;

        // Tải chi tiết drama từ drama-detail (nếu có bổ sung như synopsis, tags, rating)
        try {
            const detailRes = await fetchApi(`/api/hongguo/drama-detail?series_id=${encodeURIComponent(drama.series_id)}`);
            if (detailRes.success && detailRes.data) {
                const d = detailRes.data;
                drama.intro = d.series_intro || d.intro || drama.intro || '';
                drama.tags = d.tags || drama.tags || [];
                drama.rating = d.score || drama.rating || '-';
                drama.cover = d.series_cover || drama.cover || '';
                drama.total = d.episode_cnt || drama.total || 0;
            }
        } catch (_) {}

        // Tải danh sách chi tiết các tập phim
        await loadDramaEpisodes(drama.series_id);

        // Hiển thị Card thông tin phim
        renderDramaCard(drama);
        showToast(`Đã tìm thấy: ${drama.title || 'Phim'} (${drama.total || 0} tập)`, 'success');
    } finally {
        setResolveLoading(false);
    }
}

async function loadDramaEpisodes(seriesId) {
    if (!seriesId) return;

    const res = await fetchApi(`/api/hongguo/episodes?series_id=${encodeURIComponent(seriesId)}`);
    if (res.success && Array.isArray(res.episodes) && res.episodes.length > 0) {
        hongguoState.episodes = res.episodes.map((ep, idx) => ({
            episode_number: ep.order || ep.episode_number || (idx + 1),
            title: ep.title || `Tập ${ep.order || (idx + 1)}`,
            item_id: ep.item_id || `${seriesId}_${idx + 1}`
        }));
    } else {
        // Fallback: Tự sinh danh sách tập theo số lượng total
        const total = (hongguoState.currentDrama && hongguoState.currentDrama.total) || 0;
        hongguoState.episodes = Array.from({ length: total }, (_, i) => ({
            episode_number: i + 1,
            title: `Tập ${i + 1}`,
            item_id: `${seriesId}_${i + 1}`
        }));
    }

    // Mặc định chọn tất cả tập khi phân giải thành công
    selectAllEpisodes();
    renderEpisodesGrid();
    updateSelectionCounter();
}

// =========================================================================
// 6. Episode Selection Logic & Range Parser
// =========================================================================

/**
 * Phân tích dải tập người dùng nhập vào.
 * Ví dụ hợp lệ: "1-20, 25, 30-40", "1-10; 15; 20-25", "all", "1~20"
 */
export function parseEpisodeRange(rangeStr, maxEpisodes = 1000) {
    const selected = new Set();
    if (!rangeStr || typeof rangeStr !== 'string') return selected;

    const cleanStr = rangeStr.trim().toLowerCase();
    if (cleanStr === 'all' || cleanStr === 'tất cả') {
        for (let i = 1; i <= maxEpisodes; i++) selected.add(i);
        return selected;
    }

    const tokens = cleanStr.split(/[,;\s]+/).map(t => t.trim()).filter(Boolean);

    for (const token of tokens) {
        // Khớp dải số: 1-20 hoặc 1~20 hoặc 1..20
        const rangeMatch = token.match(/^(\d+)\s*[-~..]\s*(\d+)$/);
        if (rangeMatch) {
            let start = parseInt(rangeMatch[1], 10);
            let end = parseInt(rangeMatch[2], 10);
            if (!isNaN(start) && !isNaN(end)) {
                if (start > end) [start, end] = [end, start];
                for (let i = start; i <= end; i++) {
                    if (i >= 1 && i <= maxEpisodes) selected.add(i);
                }
            }
            continue;
        }

        // Khớp số đơn: 25
        const singleNum = parseInt(token, 10);
        if (!isNaN(singleNum) && singleNum >= 1 && singleNum <= maxEpisodes) {
            selected.add(singleNum);
        }
    }

    return selected;
}

/**
 * Gom tập hợp các số tập thành chuỗi rút gọn gửi lên server.
 * Ví dụ: Set(1, 2, 3, 5, 7, 8, 9) -> "1-3, 5, 7-9"
 */
export function formatEpisodeRange(selectedSet, totalCount) {
    if (!selectedSet || selectedSet.size === 0) return '';
    if (totalCount && selectedSet.size === totalCount) return 'all';

    const sorted = Array.from(selectedSet).sort((a, b) => a - b);
    const ranges = [];
    let start = sorted[0];
    let prev = sorted[0];

    for (let i = 1; i < sorted.length; i++) {
        const cur = sorted[i];
        if (cur === prev + 1) {
            prev = cur;
        } else {
            ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
            start = cur;
            prev = cur;
        }
    }
    ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
    return ranges.join(', ');
}

export function selectAllEpisodes() {
    const total = hongguoState.episodes.length;
    hongguoState.selectedEpisodes = new Set();
    for (let i = 1; i <= total; i++) {
        hongguoState.selectedEpisodes.add(i);
    }
    syncEpisodeCheckboxes();
    updateSelectionCounter();
}

export function deselectAllEpisodes() {
    hongguoState.selectedEpisodes.clear();
    syncEpisodeCheckboxes();
    updateSelectionCounter();
}

export function invertEpisodeSelection() {
    const total = hongguoState.episodes.length;
    const nextSet = new Set();
    for (let i = 1; i <= total; i++) {
        if (!hongguoState.selectedEpisodes.has(i)) {
            nextSet.add(i);
        }
    }
    hongguoState.selectedEpisodes = nextSet;
    syncEpisodeCheckboxes();
    updateSelectionCounter();
}

export function applyCustomRange() {
    const inputEl = document.getElementById('hongguoRangeInput') || document.getElementById('hongguoEpisodeRangeInput');
    if (!inputEl) return;
    const val = inputEl.value.trim();
    if (!val) {
        showToast('Vui lòng nhập dải tập (ví dụ: 1-20, 25, 30-40)', 'warning');
        return;
    }

    const total = hongguoState.episodes.length;
    const parsed = parseEpisodeRange(val, total);
    if (parsed.size === 0) {
        showToast('Dải tập không hợp lệ hoặc nằm ngoài phạm vi số tập của phim!', 'warning');
        return;
    }

    hongguoState.selectedEpisodes = parsed;
    syncEpisodeCheckboxes();
    updateSelectionCounter();
    showToast(`Đã chọn ${parsed.size}/${total} tập theo dải nhập.`, 'info');
}

export function toggleEpisode(epNum) {
    if (hongguoState.selectedEpisodes.has(epNum)) {
        hongguoState.selectedEpisodes.delete(epNum);
    } else {
        hongguoState.selectedEpisodes.add(epNum);
    }
    syncEpisodeCheckboxes();
    updateSelectionCounter();
}

// =========================================================================
// 7. Download Submission & Task Execution
// =========================================================================
export async function submitHongguoDownload() {
    if (!checkHongguoLicense('Tải phim Hồng Quả')) return;

    if (!hongguoState.currentDrama) {
        showToast('Vui lòng phân giải link phim trước khi tải!', 'warning');
        return;
    }

    const selectedCount = hongguoState.selectedEpisodes.size;
    if (selectedCount === 0) {
        showToast('Vui lòng chọn ít nhất 1 tập phim để tải!', 'warning');
        return;
    }

    const seriesId = String(hongguoState.currentDrama.series_id);
    const total = hongguoState.episodes.length;
    const rangeStr = formatEpisodeRange(hongguoState.selectedEpisodes, total);

    const qualitySel = document.getElementById('hongguoDownloadQuality');
    const quality = qualitySel ? qualitySel.value : '1080p';

    const concSel = document.getElementById('hongguoDownloadConcurrency');
    const concurrency = concSel ? parseInt(concSel.value, 10) || 4 : 4;

    const payload = {
        series_ids: [seriesId],
        series_id: seriesId,
        ranges: { [seriesId]: rangeStr || 'all' },
        concurrency: concurrency,
        quality: quality
    };

    setDownloadButtonLoading(true);

    try {
        const res = await fetchApi('/api/hongguo/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.success) {
            if (!res.licenseError) {
                showToast(res.error || 'Không thể gửi yêu cầu tải phim.', 'error');
            }
            return;
        }

        showToast(`Đã đưa ${selectedCount} tập vào hàng đợi tải video!`, 'success');
        
        // Mở rộng khu vực tiến trình và kích hoạt Polling 1 giây
        expandProgressCard();
        startProgressPolling();
    } finally {
        setDownloadButtonLoading(false);
    }
}

export async function cancelHongguoDownload() {
    const confirmFn = (typeof window !== 'undefined' && window.showConfirmModal) || showConfirmModal;
    const confirmed = (confirmFn === showConfirmModal)
        ? await showConfirmModal({
            title: 'Hủy Tác Vụ Tải',
            message: 'Bạn có chắc chắn muốn hủy bỏ tiến trình tải phim đang diễn ra?',
            type: 'warning',
            confirmText: 'Hủy Tải',
            cancelText: 'Tiếp Tục Tải'
        })
        : await confirmFn({
            title: 'Hủy Tác Vụ Tải',
            message: 'Bạn có chắc chắn muốn hủy bỏ tiến trình tải phim đang diễn ra?',
            type: 'warning',
            confirmText: 'Hủy Tải',
            cancelText: 'Tiếp Tục Tải'
        });
    if (!confirmed) return;

    const res = await fetchApi('/api/hongguo/cancel', { method: 'POST' });
    const toastFn = (typeof window !== 'undefined' && window.showToast) || showToast;
    if (res.success) {
        toastFn('Đã gửi yêu cầu hủy tải phim.', 'info');
        stopProgressPolling();
        renderProgressCancelledUI();
    } else {
        toastFn(res.error || 'Lỗi khi hủy tải phim.', 'error');
    }
}

// =========================================================================
// 8. Real-Time Progress Polling (1-Second Interval)
// =========================================================================
export function startProgressPolling() {
    if (hongguoState.pollingTimer) {
        clearInterval(hongguoState.pollingTimer);
    }
    hongguoState.isPolling = true;
    pollDownloadTasks();
    hongguoState.pollingTimer = setInterval(pollDownloadTasks, 1000);
}

export function stopProgressPolling() {
    if (hongguoState.pollingTimer) {
        clearInterval(hongguoState.pollingTimer);
        hongguoState.pollingTimer = null;
    }
    hongguoState.isPolling = false;
}

export async function pollDownloadTasks() {
    const res = await fetchApi('/api/hongguo/tasks');
    if (!res.success) return;

    const isRunning = Boolean(res.running);
    const logList = Array.isArray(res.log) ? res.log : [];

    // Chuyển đổi res.series thành danh sách chuẩn
    let seriesTasks = [];
    if (Array.isArray(res.series)) {
        seriesTasks = res.series;
    } else if (res.series && typeof res.series === 'object') {
        seriesTasks = Object.entries(res.series).map(([sid, item]) => ({ sid, ...item }));
    }

    const wasRunning = hongguoState.downloadTasks.running;

    hongguoState.downloadTasks = {
        running: isRunning,
        started: res.started || 0,
        mode: res.mode || 'download',
        series: seriesTasks,
        log: logList
    };

    renderProgressUI(hongguoState.downloadTasks);

    // Xử lý khi hoàn tất quá trình tải
    if (!isRunning && wasRunning) {
        stopProgressPolling();
        showToast('🎉 Đã hoàn tất tiến trình tải phim!', 'success');
        // Tự động làm mới Thư viện phim đã tải
        loadHongguoLibrary();
    }
}

// =========================================================================
// 9. Downloaded Library & Explorer
// =========================================================================
export async function loadHongguoLibrary() {
    const res = await fetchApi('/api/hongguo/library');
    if (!res.success) {
        if (!res.licenseError) {
            renderLibraryEmptyState(res.error);
        }
        return;
    }

    hongguoState.library = Array.isArray(res.items) ? res.items : [];
    if (res.output_dir) {
        hongguoState.service.outputDir = res.output_dir;
        const outDirEl = document.getElementById('hongguoOutputDirDisplay');
        if (outDirEl) outDirEl.value = res.output_dir;
    }

    renderLibraryGrid();
}

export async function loadLibraryEpisodes(folderName) {
    if (!folderName) return;
    hongguoState.activeLibraryDrama = folderName;

    const res = await fetchApi(`/api/hongguo/library/episodes?name=${encodeURIComponent(folderName)}`);
    if (res.success && Array.isArray(res.episodes)) {
        hongguoState.libraryEpisodes = res.episodes;
        openLibraryEpisodesModal(folderName, res.episodes);
    } else {
        showToast(res.error || 'Không thể tải danh sách tập trong thư mục này.', 'error');
    }
}

// =========================================================================
// 10. Workflow Bridges to NovaCut Core
// =========================================================================

/**
 * Cầu nối 1: Gửi video sang tab "Biên tập phim"
 */
export function sendToEditor(filePath) {
    if (!filePath) {
        showToast('Đường dẫn tệp video không hợp lệ.', 'warning');
        return;
    }

    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_editor', 'Biên tập phim')) return;
    }

    // 1. Ưu tiên gọi hàm chuẩn của NovaCut nếu có
    if (typeof window.sendVideoToEditor === 'function') {
        window.sendVideoToEditor(filePath);
        return;
    }

    // 2. Fallback trực tiếp: Chuyển tab và nạp video vào timeline/player
    const editorTab = document.querySelector('.nav-tab[data-target="viewEditor"]');
    if (editorTab) editorTab.click();

    const editorInput = document.getElementById('editorInputVideoPath');
    if (editorInput) editorInput.value = filePath;

    const videoPlayer = document.getElementById('videoPlayer');
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    if (videoPlayer) {
        videoPlayer.src = `/api/file?path=${encodeURIComponent(filePath)}`;
        videoPlayer.load();
        if (videoPlaceholder) videoPlaceholder.style.display = 'none';
        videoPlayer.style.display = 'block';
    }

    showToast('Đã nạp video vào Biên tập phim thành công!', 'success');
}

/**
 * Cầu nối 2: Gửi video sang tab "Review phim"
 */
export function sendToReview(filePath) {
    if (!filePath) {
        showToast('Đường dẫn tệp video không hợp lệ.', 'warning');
        return;
    }

    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_review', 'Review Phim')) return;
    }

    // 1. Ưu tiên gọi hàm chuẩn của NovaCut nếu có
    if (typeof window.sendVideoToReview === 'function') {
        window.sendVideoToReview(filePath);
        return;
    }

    // 2. Fallback trực tiếp: Chuyển tab và nạp video vào studio review
    const reviewTab = document.querySelector('.nav-tab[data-target="viewReview"]');
    if (reviewTab) reviewTab.click();

    const reviewInput = document.getElementById('reviewInputVideoPath');
    if (reviewInput) reviewInput.value = filePath;

    if (typeof window.loadReviewVideoPlayer === 'function') {
        window.loadReviewVideoPlayer(filePath);
    }

    const reviewInsightBox = document.getElementById('reviewVideoInsightBox');
    const reviewInsightDuration = document.getElementById('reviewInsightDuration');
    if (reviewInsightBox) {
        reviewInsightBox.style.display = 'flex';
        const filename = filePath.split('\\').pop().split('/').pop();
        if (reviewInsightDuration) reviewInsightDuration.textContent = `🎬 ${filename}`;
    }

    showToast('Đã nạp video vào Studio Review Phim!', 'success');
}

/**
 * Cầu nối 3: Mở thư mục tải về hoặc thư mục phim trong Windows Explorer
 */
export async function openFolder(folderPath = null) {
    try {
        const payload = folderPath ? { folder: folderPath } : {};
        const res = await fetchApi('/api/hongguo/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.success) {
            showToast('Đã mở thư mục trong File Explorer.', 'info');
        } else {
            showToast(res.error || 'Không thể mở thư mục.', 'error');
        }
    } catch (err) {
        showToast('Lỗi khi mở thư mục: ' + err.message, 'error');
    }
}

// =========================================================================
// 11. UI Rendering Helpers & DOM Updates
// =========================================================================

function updateServiceStatusUI(installed, signerRunning, serverRunning, errorMsg) {
    const pill = document.getElementById('hongguoServiceStatusPill');
    const dot = document.getElementById('hongguoStatusDot');
    const text = document.getElementById('hongguoStatusText');
    const portBadges = document.getElementById('hongguoPortBadges');
    const signerBadge = document.getElementById('hongguoSignerBadge');
    const serverBadge = document.getElementById('hongguoServerBadge');

    const isFullyHealthy = installed && signerRunning && serverRunning;

    if (dot) {
        dot.style.background = isFullyHealthy ? '#10b981' : (installed ? '#f59e0b' : '#ef4444');
        dot.style.boxShadow = isFullyHealthy ? '0 0 8px #10b981' : (installed ? '0 0 8px #f59e0b' : '0 0 6px #ef4444');
    }

    if (text) {
        if (isFullyHealthy) {
            text.textContent = 'Dịch Vụ Sẵn Sàng';
            text.style.color = '#34d399';
        } else if (installed) {
            text.textContent = 'Dịch Vụ Chưa Bật';
            text.style.color = '#fbbf24';
        } else {
            text.textContent = 'Chưa Cài Đặt Tool';
            text.style.color = '#f87171';
        }
    }

    if (portBadges) {
        portBadges.style.display = isFullyHealthy ? 'inline-flex' : 'none';
    }

    if (signerBadge) {
        signerBadge.style.opacity = signerRunning ? '1' : '0.4';
    }
    if (serverBadge) {
        serverBadge.style.opacity = serverRunning ? '1' : '0.4';
    }
}

function updateServiceStartingUI(isStarting) {
    const btn = document.getElementById('btnHongguoRestartService');
    if (!btn) return;
    if (isStarting) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span><span>Đang khởi động...</span>';
    } else {
        btn.disabled = false;
        btn.innerHTML = '<span>🔄</span><span>Khởi động lại</span>';
    }
}

function setResolveLoading(isLoading) {
    const btn = document.getElementById('btnHongguoAnalyze') || document.getElementById('btnHongguoResolve');
    const textEl = document.getElementById('hongguoAnalyzeBtnText');
    if (btn) btn.disabled = isLoading;
    if (textEl) textEl.textContent = isLoading ? 'Đang Phân Tích...' : 'Phân Tích Phim';
}

function setDownloadButtonLoading(isLoading) {
    const btn = document.getElementById('btnHongguoStartDownload');
    if (btn) btn.disabled = isLoading;
}

function expandProgressCard() {
    const card = document.getElementById('hongguoProgressCard');
    if (card) card.style.display = 'block';
    const liveBox = document.getElementById('hongguoLiveTaskBox');
    if (liveBox) liveBox.style.display = 'flex';
    const btnCancel = document.getElementById('btnHongguoCancelDownload');
    if (btnCancel) btnCancel.style.display = 'inline-flex';
}

function renderDramaCard(drama) {
    const placeholder = document.getElementById('hongguoMetadataEmptyPlaceholder');
    const content = document.getElementById('hongguoMetadataContent');
    if (placeholder) placeholder.style.display = 'none';
    if (content) content.style.display = 'flex';

    const idBadge = document.getElementById('hongguoSeriesIdBadge');
    if (idBadge) {
        idBadge.style.display = 'inline-block';
        idBadge.textContent = `ID: ${drama.series_id || '-'}`;
    }

    const poster = document.getElementById('hongguoDramaPoster');
    if (poster) {
        poster.src = drama.cover || '';
        poster.onerror = () => {
            poster.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="110" height="155" fill="%231e293b"><rect width="100%" height="100%"/><text x="50%" y="50%" fill="%2364748b" font-size="12" text-anchor="middle" dominant-baseline="middle">No Cover</text></svg>';
        };
    }

    const overlay = document.getElementById('hongguoPosterEpisodeOverlay');
    if (overlay) overlay.textContent = `${drama.total || 0} Tập`;

    const titleEl = document.getElementById('hongguoDramaTitle');
    if (titleEl) {
        titleEl.textContent = drama.title || 'Phim Hồng Quả';
        titleEl.title = drama.title || '';
    }

    const totalEl = document.getElementById('hongguoDramaTotalEpisodes');
    if (totalEl) totalEl.textContent = `${drama.total || 0} tập`;

    const ratingEl = document.getElementById('hongguoDramaRating');
    if (ratingEl) ratingEl.textContent = `⭐ ${drama.rating || '9.2'}`;

    const tagsContainer = document.getElementById('hongguoDramaTagsContainer');
    if (tagsContainer) {
        tagsContainer.innerHTML = '';
        const tags = Array.isArray(drama.tags) ? drama.tags : ['Phim Ngắn', 'Hồng Quả', 'HD'];
        tags.forEach(t => {
            const span = document.createElement('span');
            span.style.cssText = 'font-size: 10px; background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); padding: 1px 6px; border-radius: 4px;';
            span.textContent = t;
            tagsContainer.appendChild(span);
        });
    }

    const synopsis = document.getElementById('hongguoDramaSynopsis');
    if (synopsis) {
        synopsis.textContent = drama.intro || drama.desc || 'Chưa có phần giới thiệu phim.';
    }
}

function renderEpisodesGrid() {
    const placeholder = document.getElementById('hongguoEpisodeGridPlaceholder');
    const container = document.getElementById('hongguoEpisodeGridContainer');
    const grid = document.getElementById('hongguoEpisodeGrid') || document.getElementById('hongguoEpisodesGrid');

    if (placeholder) placeholder.style.display = 'none';
    if (container) container.style.display = 'flex';
    if (!grid) return;

    grid.innerHTML = '';
    const frag = document.createDocumentFragment();

    hongguoState.episodes.forEach(ep => {
        const epNum = ep.episode_number;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `hongguo-ep-tile ${hongguoState.selectedEpisodes.has(epNum) ? 'selected' : ''}`;
        btn.dataset.ep = String(epNum);
        btn.textContent = `Tập ${epNum}`;
        btn.addEventListener('click', () => toggleEpisode(epNum));
        frag.appendChild(btn);
    });

    grid.appendChild(frag);
}

function syncEpisodeCheckboxes() {
    const grid = document.getElementById('hongguoEpisodeGrid') || document.getElementById('hongguoEpisodesGrid');
    if (!grid) return;
    const tiles = grid.querySelectorAll('.hongguo-ep-tile');
    tiles.forEach(tile => {
        const ep = parseInt(tile.dataset.ep, 10);
        if (hongguoState.selectedEpisodes.has(ep)) {
            tile.classList.add('selected');
        } else {
            tile.classList.remove('selected');
        }
    });
}

function updateSelectionCounter() {
    const total = hongguoState.episodes.length;
    const count = hongguoState.selectedEpisodes.size;

    const badge = document.getElementById('hongguoSelectedEpisodesBadge') || document.getElementById('hongguoSelectedCountBadge');
    if (badge) {
        badge.textContent = `Đã chọn: ${count} / ${total} tập`;
    }

    const summaryText = document.getElementById('hongguoDownloadSummaryText');
    if (summaryText) {
        summaryText.textContent = count > 0 ? `Đã chọn ${count} trên tổng số ${total} tập để tải` : 'Chưa chọn tập nào để tải';
    }

    const btnCount = document.getElementById('hongguoDownloadButtonCount');
    if (btnCount) {
        btnCount.textContent = String(count);
    }

    const btnDownload = document.getElementById('btnHongguoStartDownload');
    if (btnDownload) {
        btnDownload.disabled = count === 0;
    }
}

function renderProgressUI(tasks) {
    const isRunning = tasks.running;
    const seriesList = tasks.series || [];
    const activeTask = seriesList.find(s => s.status === 'downloading') || seriesList[0] || null;

    const countBadge = document.getElementById('hongguoActiveTaskCountBadge');
    if (countBadge) {
        countBadge.textContent = `${seriesList.length} tác vụ ${isRunning ? 'đang chạy' : 'hoàn tất'}`;
    }

    const liveBox = document.getElementById('hongguoLiveTaskBox');
    if (liveBox && (isRunning || seriesList.length > 0)) {
        liveBox.style.display = 'flex';
    }

    const cancelBtn = document.getElementById('btnHongguoCancelDownload');
    if (cancelBtn) {
        cancelBtn.style.display = isRunning ? 'inline-flex' : 'none';
    }

    const dramaTitleEl = document.getElementById('hongguoProgressDramaTitle');
    const currentEpEl = document.getElementById('hongguoCurrentDownloadingEp');
    const speedEl = document.getElementById('hongguoProgressSpeed');
    const counterEl = document.getElementById('hongguoProgressCounter');
    const progressBar = document.getElementById('hongguoOverallProgressBar') || document.getElementById('hongguoProgressBar');
    const statusTextEl = document.getElementById('hongguoProgressStatusText');
    const percentTextEl = document.getElementById('hongguoProgressPercentText') || document.getElementById('hongguoProgressPercent');

    if (activeTask) {
        const total = activeTask.total || 1;
        const current = activeTask.done || activeTask.current || 0;
        const pct = Math.min(100, Math.round((current / total) * 100));

        if (dramaTitleEl) dramaTitleEl.textContent = activeTask.title || (hongguoState.currentDrama ? hongguoState.currentDrama.title : 'Phim Đang Tải');
        if (currentEpEl) currentEpEl.textContent = activeTask.current_ep ? `Tập ${activeTask.current_ep}` : `Tập ${current}/${total}`;
        if (speedEl) speedEl.textContent = activeTask.speed || (isRunning ? 'Đang tải...' : '0.0 MB/s');
        if (counterEl) counterEl.textContent = `${current}/${total} tập`;
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (statusTextEl) statusTextEl.textContent = isRunning ? `Đang tải tập ${current + 1}...` : 'Hoàn tất tải toàn bộ!';
        if (percentTextEl) percentTextEl.textContent = `${pct}%`;
    }

    // Render Tasks Table Body
    const tbody = document.getElementById('hongguoTasksTableBody');
    if (tbody) {
        if (seriesList.length === 0) {
            tbody.innerHTML = `
                <tr id="hongguoTasksEmptyRow">
                    <td colspan="7" style="padding: 24px; text-align: center; color: #64748b;">
                        Hiện không có tác vụ tải nào đang hoạt động
                    </td>
                </tr>
            `;
        } else {
            tbody.innerHTML = seriesList.map(task => {
                const total = task.total || 1;
                const done = task.done || task.current || 0;
                const pct = Math.min(100, Math.round((done / total) * 100));
                return `
                    <tr style="border-bottom: 1px solid rgba(51, 65, 85, 0.4);">
                        <td style="padding: 10px 12px; font-weight: 600; color: #f8fafc;">${escapeHtml(task.title || '-')}</td>
                        <td style="padding: 10px 12px; font-family: monospace; color: #94a3b8;">${escapeHtml(task.ranges || 'all')}</td>
                        <td style="padding: 10px 12px; color: #38bdf8;">${escapeHtml(String(task.current_ep || done))}</td>
                        <td style="padding: 10px 12px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="width: 80px; height: 6px; background: #1e293b; border-radius: 3px; overflow: hidden;">
                                    <div style="width: ${pct}%; height: 100%; background: #38bdf8;"></div>
                                </div>
                                <span style="font-size: 11px; font-family: monospace;">${pct}%</span>
                            </div>
                        </td>
                        <td style="padding: 10px 12px; font-family: monospace; color: #4ade80;">${escapeHtml(task.speed || '0 MB/s')}</td>
                        <td style="padding: 10px 12px;">
                            <span class="badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${isRunning ? 'rgba(56, 189, 248, 0.15)' : 'rgba(34, 197, 94, 0.15)'}; color: ${isRunning ? '#38bdf8' : '#4ade80'};">
                                ${isRunning ? 'Đang tải' : 'Xong'}
                            </span>
                        </td>
                        <td style="padding: 10px 12px; text-align: right;">
                            <button type="button" class="btn secondary small btn-task-view-folder" data-folder="${escapeHtml(task.save_dir || task.path || task.title || '')}" style="padding: 3px 8px; font-size: 11px;">📂 Thư mục</button>
                        </td>
                    </tr>
                `;
            }).join('');

            tbody.querySelectorAll('.btn-task-view-folder').forEach(btn => {
                btn.addEventListener('click', () => openFolder(btn.dataset.folder || null));
            });
        }
    }

    // Render Log Terminal
    const logBox = document.getElementById('hongguoLogTerminal') || document.getElementById('hongguoLogBox');
    if (logBox && Array.isArray(tasks.log) && tasks.log.length > 0) {
        logBox.innerHTML = tasks.log.map(l => `<div>${escapeHtml(l)}</div>`).join('');
        logBox.scrollTop = logBox.scrollHeight;
    }
}

function renderProgressCancelledUI() {
    const statusTextEl = document.getElementById('hongguoProgressStatusText');
    if (statusTextEl) statusTextEl.textContent = 'Đã hủy tải phim';
    const cancelBtn = document.getElementById('btnHongguoCancelDownload');
    if (cancelBtn) cancelBtn.style.display = 'none';
}

function renderLibraryGrid() {
    const placeholder = document.getElementById('hongguoLibraryEmptyPlaceholder');
    const container = document.getElementById('hongguoLibraryContainer') || document.getElementById('hongguoLibraryGrid');
    const countBadge = document.getElementById('hongguoLibraryCountBadge');

    const items = hongguoState.library || [];
    if (countBadge) {
        countBadge.textContent = `${items.length} bộ phim`;
    }

    if (items.length === 0) {
        if (placeholder) placeholder.style.display = 'flex';
        if (container) container.style.display = 'none';
        return;
    }

    if (placeholder) placeholder.style.display = 'none';
    if (!container) return;

    container.style.display = 'grid';
    container.innerHTML = '';
    const frag = document.createDocumentFragment();

    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'hg-library-item';
        card.style.cssText = 'background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(51, 65, 85, 0.6); border-radius: 12px; padding: 14px; display: flex; gap: 14px; align-items: center; transition: all 0.2s ease;';

        const coverSrc = item.cover || 'logo.png';
        const titleText = item.title || item.name || 'Phim Hồng Quả';
        const epCount = (item.episodes_count !== undefined && item.episodes_count !== null) ? item.episodes_count : (item.local || item.total || 0);

        card.innerHTML = `
            <img class="hg-library-thumb" src="${escapeHtml(coverSrc)}" alt="${escapeHtml(titleText)}" style="width: 68px; height: 90px; border-radius: 8px; object-fit: cover; background: #1e293b; border: 1px solid #334155; flex-shrink: 0;" onerror="this.src='logo.png'">
            <div class="hg-library-details" style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px;">
                <div class="hg-library-name" style="font-size: 14px; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(titleText)}">
                    ${escapeHtml(titleText)}
                </div>
                <div class="hg-library-meta" style="font-size: 12px; color: #94a3b8; display: flex; gap: 8px; align-items: center;">
                    <span style="color: #38bdf8; font-weight: 600;">📁 ${epCount} tập đã tải</span>
                </div>
                <div class="hg-workflow-actions" style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;">
                    <button type="button" class="btn small primary-cyan btn-lib-inspect" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">
                        <span>🎬</span><span>Chọn Tập</span>
                    </button>
                    <button type="button" class="btn small secondary btn-lib-open-folder" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px; border: 1px solid #334155;">
                        <span>📂</span><span>Mở Thư Mục</span>
                    </button>
                </div>
            </div>
        `;

        card.querySelector('.btn-lib-inspect')?.addEventListener('click', () => loadLibraryEpisodes(item.name || item.title));
        card.querySelector('.btn-lib-open-folder')?.addEventListener('click', () => openFolder(item.path || item.name || item.title));

        frag.appendChild(card);
    });

    container.appendChild(frag);
}

function renderLibraryEmptyState(msg = null) {
    const placeholder = document.getElementById('hongguoLibraryEmptyPlaceholder');
    const container = document.getElementById('hongguoLibraryContainer') || document.getElementById('hongguoLibraryGrid');
    if (container) container.style.display = 'none';
    if (placeholder) {
        placeholder.style.display = 'flex';
        if (msg) {
            placeholder.querySelector('div:nth-child(2)').textContent = msg;
        }
    }
}

function openLibraryEpisodesModal(folderName, episodes) {
    const modal = document.getElementById('hongguoLibraryEpisodesModal') || document.getElementById('hongguoEpisodesModal');
    if (!modal) return;

    const titleEl = document.getElementById('hongguoModalDramaTitle');
    const pathEl = document.getElementById('hongguoModalDramaPath');
    const listEl = document.getElementById('hongguoModalEpisodesList');
    const countEl = document.getElementById('hongguoModalEpisodesCount');

    if (titleEl) titleEl.textContent = folderName || 'Danh Sách Tập Phim';
    if (pathEl) pathEl.textContent = `Thư mục: ${folderName}`;
    if (countEl) countEl.textContent = `${episodes.length} tập MP4`;

    if (listEl) {
        listEl.innerHTML = '';
        const frag = document.createDocumentFragment();

        episodes.forEach(ep => {
            const row = document.createElement('div');
            row.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(15, 23, 42, 0.75); border: 1px solid #334155; border-radius: 8px; gap: 10px; flex-wrap: wrap;';
            const sizeMb = (ep.size / (1024 * 1024)).toFixed(1);

            row.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1;">
                    <span style="font-size: 15px;">🎬</span>
                    <div style="min-width: 0;">
                        <div style="font-size: 13px; font-weight: 600; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(ep.name)}">
                            ${escapeHtml(ep.name)}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; font-family: monospace;">Dung lượng: ${sizeMb} MB</div>
                    </div>
                </div>
                <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                    <button type="button" class="btn small secondary btn-preview-ep" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; border: 1px solid #334155;">
                        ▶️ Xem Trước
                    </button>
                    <button type="button" class="btn small btn-hg-workflow-editor btn-send-editor" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; background: rgba(14, 165, 233, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; font-weight: 600;">
                        ✂️ Biên Tập
                    </button>
                    <button type="button" class="btn small btn-hg-workflow-review btn-send-review" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc; font-weight: 600;">
                        🎙️ Review Phim
                    </button>
                    <button type="button" class="btn small secondary btn-open-ep-folder" style="padding: 4px 8px; font-size: 11.5px; border-radius: 6px; border: 1px solid #334155;" title="Mở trong File Explorer">
                        📁
                    </button>
                </div>
            `;

            row.querySelector('.btn-preview-ep')?.addEventListener('click', () => {
                openVideoPreviewModal(ep.path, ep.name);
            });
            row.querySelector('.btn-send-editor')?.addEventListener('click', () => {
                modal.style.display = 'none';
                sendToEditor(ep.path);
            });
            row.querySelector('.btn-send-review')?.addEventListener('click', () => {
                modal.style.display = 'none';
                sendToReview(ep.path);
            });
            row.querySelector('.btn-open-ep-folder')?.addEventListener('click', () => {
                openFolder(ep.path);
            });

            frag.appendChild(row);
        });

        listEl.appendChild(frag);
    }

    modal.style.display = 'flex';
}

export function openVideoPreviewModal(videoPath, title) {
    const modal = document.getElementById('hongguoVideoPreviewModal');
    const player = document.getElementById('hongguoVideoPreviewPlayer');
    const titleEl = document.getElementById('hongguoPreviewTitle');
    if (!modal || !player) return;

    if (titleEl) titleEl.textContent = title || 'Xem Trước Video';
    player.src = `/api/file?path=${encodeURIComponent(videoPath)}`;
    player.load();
    player.play().catch(() => {});

    const btnToEditor = document.getElementById('btnPreviewModalToEditor');
    const btnToReview = document.getElementById('btnPreviewModalToReview');

    if (btnToEditor) {
        btnToEditor.onclick = () => {
            modal.style.display = 'none';
            player.pause();
            sendToEditor(videoPath);
        };
    }
    if (btnToReview) {
        btnToReview.onclick = () => {
            modal.style.display = 'none';
            player.pause();
            sendToReview(videoPath);
        };
    }

    modal.style.display = 'flex';
}

// =========================================================================
// 12. Lifecycle Initializer & Event Listeners
// =========================================================================
export function initHongguoModule() {
    setupHongguoEventListeners();
    // Gắn helpers lên window để truy cập từ mọi nơi
    window.sendHongguoToEditor = sendToEditor;
    window.sendHongguoToReview = sendToReview;
    window.openHongguoFolder = openFolder;
    window.onHongguoTabActivated = onHongguoTabActivated;
    window.resolveHongguoDrama = resolveHongguoDrama;
}

export function onHongguoTabActivated() {
    if (!checkHongguoLicense('Tải Phim Hồng Quả')) return;

    // 1. Kiểm tra trạng thái dịch vụ nền và tự bật nếu cần
    checkHongguoStatus(true);

    // 2. Tải danh sách thư viện video đã tải
    loadHongguoLibrary();

    // 3. Nếu đang có tác vụ tải chạy ngầm, kích hoạt ngay polling
    fetchApi('/api/hongguo/tasks').then(res => {
        if (res.success && res.running) {
            expandProgressCard();
            startProgressPolling();
        }
    });
}

function setupHongguoEventListeners() {
    // 1. Analyze / Resolve button & Enter key
    const btnAnalyze = document.getElementById('btnHongguoAnalyze') || document.getElementById('btnHongguoResolve');
    const inputUrl = document.getElementById('hongguoInputUrl') || document.getElementById('hongguoInputText');
    const btnClearUrl = document.getElementById('btnHongguoClearUrl');
    const btnPasteUrl = document.getElementById('btnHongguoPasteUrl');

    if (btnAnalyze) {
        btnAnalyze.addEventListener('click', resolveHongguoDrama);
    }
    if (inputUrl) {
        inputUrl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') resolveHongguoDrama();
        });
        inputUrl.addEventListener('input', () => {
            if (btnClearUrl) {
                btnClearUrl.style.display = inputUrl.value.trim() ? 'block' : 'none';
            }
        });
    }
    if (btnClearUrl && inputUrl) {
        btnClearUrl.addEventListener('click', () => {
            inputUrl.value = '';
            btnClearUrl.style.display = 'none';
            inputUrl.focus();
        });
    }
    if (btnPasteUrl && inputUrl) {
        btnPasteUrl.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    inputUrl.value = text.trim();
                    if (btnClearUrl) btnClearUrl.style.display = 'block';
                    resolveHongguoDrama();
                }
            } catch (_) {
                showToast('Vui lòng cấp quyền dán nội dung từ clipboard!', 'info');
            }
        });
    }

    // 2. Output folder controls
    const btnOpenFolder = document.getElementById('btnHongguoOpenFolder');
    if (btnOpenFolder) {
        btnOpenFolder.addEventListener('click', () => openFolder(null));
    }
    const btnChangeFolder = document.getElementById('btnHongguoChangeFolder');
    if (btnChangeFolder) {
        btnChangeFolder.addEventListener('click', () => {
            showToast('Thư mục tải về mặc định tại thư mục tải của Hongguo Downloader.', 'info');
        });
    }

    // 3. Episode selection controls
    const btnSelectAll = document.getElementById('btnHongguoSelectAll');
    if (btnSelectAll) btnSelectAll.addEventListener('click', selectAllEpisodes);

    const btnDeselectAll = document.getElementById('btnHongguoDeselectAll');
    if (btnDeselectAll) btnDeselectAll.addEventListener('click', deselectAllEpisodes);

    const btnInvert = document.getElementById('btnHongguoInvertSelection');
    if (btnInvert) btnInvert.addEventListener('click', invertEpisodeSelection);

    const btnApplyRange = document.getElementById('btnHongguoApplyRange');
    const inputRange = document.getElementById('hongguoRangeInput') || document.getElementById('hongguoEpisodeRangeInput');
    if (btnApplyRange) btnApplyRange.addEventListener('click', applyCustomRange);
    if (inputRange) {
        inputRange.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') applyCustomRange();
        });
    }

    // 4. Download & Cancel triggers
    const btnDownload = document.getElementById('btnHongguoStartDownload');
    if (btnDownload) btnDownload.addEventListener('click', submitHongguoDownload);

    const btnCancel = document.getElementById('btnHongguoCancelDownload');
    if (btnCancel) btnCancel.addEventListener('click', cancelHongguoDownload);

    // 5. Service controls
    const btnRestartService = document.getElementById('btnHongguoRestartService');
    if (btnRestartService) btnRestartService.addEventListener('click', startHongguoServices);

    const btnStopService = document.getElementById('btnHongguoStopService');
    if (btnStopService) btnStopService.addEventListener('click', stopHongguoServices);

    // 6. Library controls
    const btnRefreshLibrary = document.getElementById('btnHongguoRefreshLibrary');
    if (btnRefreshLibrary) btnRefreshLibrary.addEventListener('click', loadHongguoLibrary);

    const btnOpenLibraryFolder = document.getElementById('btnHongguoOpenLibraryFolder');
    if (btnOpenLibraryFolder) btnOpenLibraryFolder.addEventListener('click', () => openFolder(null));

    // 7. Log toggle
    const btnToggleLog = document.getElementById('btnHongguoToggleLog');
    const logTerminal = document.getElementById('hongguoLogTerminal');
    const logToggleIcon = document.getElementById('hongguoLogToggleIcon');
    if (btnToggleLog && logTerminal) {
        btnToggleLog.addEventListener('click', () => {
            const isHidden = logTerminal.style.display === 'none';
            logTerminal.style.display = isHidden ? 'block' : 'none';
            if (logToggleIcon) logToggleIcon.textContent = isHidden ? '▼' : '▶';
        });
    }

    // 8. Modal close buttons
    const btnCloseEpisodesModal = document.getElementById('btnCloseHongguoEpisodesModal');
    const btnHongguoModalClose = document.getElementById('btnHongguoModalClose');
    const modalEpisodes = document.getElementById('hongguoLibraryEpisodesModal') || document.getElementById('hongguoEpisodesModal');

    const closeEpisodesModal = () => {
        if (modalEpisodes) modalEpisodes.style.display = 'none';
    };
    if (btnCloseEpisodesModal) btnCloseEpisodesModal.addEventListener('click', closeEpisodesModal);
    if (btnHongguoModalClose) btnHongguoModalClose.addEventListener('click', closeEpisodesModal);

    const btnClosePreviewModal = document.getElementById('btnCloseHongguoPreviewModal');
    const btnPreviewModalClose = document.getElementById('btnPreviewModalClose');
    const modalPreview = document.getElementById('hongguoVideoPreviewModal');
    const previewPlayer = document.getElementById('hongguoVideoPreviewPlayer');

    const closePreviewModal = () => {
        if (modalPreview) modalPreview.style.display = 'none';
        if (previewPlayer) previewPlayer.pause();
    };
    if (btnClosePreviewModal) btnClosePreviewModal.addEventListener('click', closePreviewModal);
    if (btnPreviewModalClose) btnPreviewModalClose.addEventListener('click', closePreviewModal);
}
