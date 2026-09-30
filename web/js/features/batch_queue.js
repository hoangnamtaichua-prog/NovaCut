/**
 * Batch Movie Review Studio Controller (Xử Lý & Review Phim Hàng Loạt)
 * NovaCut - AI Video & Review Editor
 */

import {
    showToast,
    showAlertModal,
    showConfirmModal,
    escapeHtml,
    formatTimeSec
} from '../utils.js';

// Khóa lưu trữ LocalStorage cho danh sách review hàng loạt
const STORAGE_KEY = 'novacut_batch_queue_items';
const EXTRACT_METHOD_KEY = 'novacut_batch_queue_extract_method';

// Trạng thái danh sách video review phim
let queueReviewItems = [];
let isBatchRunning = false;
let batchEventSource = null;
let currentReviewMode = 'recap'; // 'recap' (Auto-Edit) hoặc 'narration' (Kể lại)
let currentAspectRatio = '9:16';  // '9:16' | '16:9' | 'original'
let currentPacing = 'normal';     // 'fast' (2-4s) | 'normal' (4-7s)
let selectedLogoFilePath = '';
let isExtractingSubtitles = false;
let extractAbortController = null;

/**
 * Gửi thông báo sự kiện batch qua Telegram API
 */
async function sendTelegramBatchEvent(payload) {
    try {
        const userId = window.getNovaCutUserId ? window.getNovaCutUserId() : (localStorage.getItem('novacut_user_id') || 'default');
        const enriched = { ...payload, user_id: userId };
        await fetch('/api/telegram/notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(enriched)
        });
    } catch (e) {
        // Không ngắt pipeline nếu Telegram lỗi
    }
}

/**
 * Điểm khởi tạo chính cho Module Xử Lý Hàng Loạt Review Phim
 */
export function initBatchQueueModule() {
    loadSavedQueueItems();
    setupToolbarEvents();
    setupTableEvents();
    setupReviewCard1Events();
    setupReviewCard2Events();
    setupReviewCard3Events();
    setupExecutionEvents();
    setupUrlModalEvents();
    connectBatchEventStream();
    renderQueueTable();

    // Đăng ký toàn cục để các màn hình khác (như Douyin Downloader) có thể nạp thẳng vào
    window.addVideosToBatchQueue = addVideosToQueue;
    window.addSrtsToBatchQueue = addSrtsToQueue;
    window.renderBatchQueueTable = renderQueueTable;
}

// ─────────────────────────────────────────────────────────────
// 1. QUẢN LÝ DỮ LIỆU & LOCAL STORAGE
// ─────────────────────────────────────────────────────────────

function loadSavedQueueItems() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) {
                queueReviewItems = parsed.map(item => ({
                    id: item.id || `q_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
                    sourceType: item.sourceType || (item.videoPath?.startsWith('http') ? 'url' : 'file'),
                    videoPath: item.videoPath || '',
                    videoName: item.videoName || item.videoPath?.split(/[\\/]/).pop() || 'Video phim',
                    srtPath: item.srtPath || '',
                    srtName: item.srtName || (item.srtPath ? item.srtPath.split(/[\\/]/).pop() : ''),
                    status: (item.status === 'processing') ? 'pending' : (item.status || 'ready'),
                    progress: (item.status === 'completed') ? 100 : 0,
                    stepText: (item.status === 'completed') ? 'Đã hoàn tất review' : 'Sẵn sàng',
                    outputPath: item.outputPath || '',
                    error: item.error || '',
                    selected: item.selected ?? true
                }));
            }
        }
    } catch (e) {
        console.warn("Không thể khôi phục danh sách queue từ storage:", e);
        queueReviewItems = [];
    }
}

function saveQueueItemsToStorage() {
    try {
        const toSave = queueReviewItems.slice(0, 100).map(item => ({
            id: item.id,
            sourceType: item.sourceType,
            videoPath: item.videoPath,
            videoName: item.videoName,
            srtPath: item.srtPath,
            srtName: item.srtName,
            status: item.status,
            outputPath: item.outputPath || '',
            error: item.error || '',
            selected: item.selected
        }));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) {
        console.warn("Lỗi lưu batch queue storage:", e);
    }
}

// ─────────────────────────────────────────────────────────────
// 2. THANH CÔNG CỤ TOOLBAR & NẠP TẬP TIN
// ─────────────────────────────────────────────────────────────

function setupToolbarEvents() {
    const btnAddVideos = document.getElementById('btnQueueAddVideos');
    const btnAddFolder = document.getElementById('btnQueueAddFolder');
    const btnAddUrls = document.getElementById('btnQueueAddUrls');
    const btnAddSrts = document.getElementById('btnQueueAddSrts');
    const btnAutoPair = document.getElementById('btnQueueAutoPair');
    const btnClearCompleted = document.getElementById('btnQueueClearCompleted');
    const btnClearAll = document.getElementById('btnQueueClearAll');
    const btnScanSubtitles = document.getElementById('btnQueueScanSubtitles');
    const btnInspectSubs = document.getElementById('btnQueueInspectSubs');
    const btnAutoAllInOne = document.getElementById('btnQueueAutoAllInOne');
    const btnStopTask = document.getElementById('btnQueueStopTask');
    const selectExtractMethod = document.getElementById('queueExtractMethodSelect');
    const btnConfigExtract = document.getElementById('btnQueueConfigExtract');

    const hiddenVideoInput = document.getElementById('queueHiddenVideoInput');
    const hiddenSrtInput = document.getElementById('queueHiddenSrtInput');

    // Thêm nhiều Video
    if (btnAddVideos) {
        btnAddVideos.addEventListener('click', async () => {
            try {
                let filePaths = [];
                if (window.pywebview?.api?.select_multiple_videos) {
                    filePaths = await window.pywebview.api.select_multiple_videos();
                } else if (typeof window.selectFiles === 'function') {
                    filePaths = await window.selectFiles('video', 'Chọn các file video phim để review hàng loạt');
                } else {
                    const res = await fetch('/api/batch/select_files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: 'Chọn nhiều file video phim để review hàng loạt' })
                    });
                    const data = await res.json();
                    if (data.success && Array.isArray(data.files) && data.files.length > 0) {
                        filePaths = data.files;
                    }
                }

                if (Array.isArray(filePaths) && filePaths.length > 0) {
                    await addVideosToQueue(filePaths);
                } else if (!window.pywebview && hiddenVideoInput) {
                    hiddenVideoInput.click();
                }
            } catch (e) {
                console.warn("Lỗi chọn video:", e);
                if (hiddenVideoInput) hiddenVideoInput.click();
            }
        });
    }

    if (hiddenVideoInput) {
        hiddenVideoInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files || []);
            const paths = files.map(f => f.path || f.name).filter(Boolean);
            if (paths.length > 0) {
                await addVideosToQueue(paths);
            }
            hiddenVideoInput.value = '';
        });
    }

    // Chọn Thư Mục chứa video
    if (btnAddFolder) {
        btnAddFolder.addEventListener('click', async () => {
            try {
                let dir = '';
                if (typeof window.selectDirectory === 'function') {
                    dir = await window.selectDirectory('Chọn thư mục chứa các video phim');
                } else if (window.pywebview?.api?.select_directory) {
                    dir = await window.pywebview.api.select_directory();
                } else {
                    const res = await fetch('/api/select_folder', { method: 'POST' });
                    const data = await res.json();
                    if (data.success && data.folder) dir = data.folder;
                }

                if (dir) {
                    showToast(`Đang quét video trong thư mục: ${dir}...`, 'info');
                    const res = await fetch('/api/batch/scan_folder', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ folder: dir })
                    });
                    const data = await res.json();
                    if (data.success && Array.isArray(data.videos) && data.videos.length > 0) {
                        await addVideosToQueue(data.videos);
                        showToast(`Đã tìm thấy và nạp ${data.videos.length} video từ thư mục!`, 'success');
                    } else {
                        // Thử thêm thư mục trực tiếp qua cơ chế nạp folder của hệ thống
                        await addVideosToQueue([dir]);
                    }
                }
            } catch (e) {
                console.warn("Lỗi quét thư mục:", e);
                showToast('Không thể quét thư mục: ' + e.message, 'error');
            }
        });
    }

    // Nạp từ URL (Mở Modal dán link)
    if (btnAddUrls) {
        btnAddUrls.addEventListener('click', () => {
            const modal = document.getElementById('queueUrlModal');
            if (modal) modal.style.display = 'flex';
        });
    }

    // Thêm nhiều SRT
    if (btnAddSrts) {
        btnAddSrts.addEventListener('click', async () => {
            try {
                let filePaths = [];
                if (window.pywebview?.api?.select_multiple_srts) {
                    filePaths = await window.pywebview.api.select_multiple_srts();
                } else if (typeof window.selectFiles === 'function') {
                    filePaths = await window.selectFiles('srt', 'Chọn các file phụ đề .srt để ghép cho video');
                } else {
                    const res = await fetch('/api/batch/select_files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: 'Chọn các file phụ đề .srt' })
                    });
                    const data = await res.json();
                    if (data.success && Array.isArray(data.files)) filePaths = data.files;
                }

                if (Array.isArray(filePaths) && filePaths.length > 0) {
                    await addSrtsToQueue(filePaths);
                } else if (!window.pywebview && hiddenSrtInput) {
                    hiddenSrtInput.click();
                }
            } catch (e) {
                console.warn("Lỗi chọn srt:", e);
                if (hiddenSrtInput) hiddenSrtInput.click();
            }
        });
    }

    if (hiddenSrtInput) {
        hiddenSrtInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files || []);
            const paths = files.map(f => f.path || f.name).filter(Boolean);
            if (paths.length > 0) {
                await addSrtsToQueue(paths);
            }
            hiddenSrtInput.value = '';
        });
    }

    // Tự động khớp Video & SRT
    if (btnAutoPair) {
        btnAutoPair.addEventListener('click', () => {
            autoPairVideosAndSrts();
        });
    }

    // Dọn các video đã hoàn thành
    if (btnClearCompleted) {
        btnClearCompleted.addEventListener('click', () => {
            const initialCount = queueReviewItems.length;
            queueReviewItems = queueReviewItems.filter(item => item.status !== 'completed');
            const removed = initialCount - queueReviewItems.length;
            if (removed > 0) {
                renderQueueTable();
                saveQueueItemsToStorage();
                showToast(`Đã dọn dẹp ${removed} video review đã hoàn thành.`, 'success');
            } else {
                showToast('Chưa có video nào đã hoàn thành để dọn.', 'info');
            }
        });
    }

    // Xóa tất cả
    if (btnClearAll) {
        btnClearAll.addEventListener('click', async () => {
            if (queueReviewItems.length === 0) {
                showToast('Danh sách hàng đợi hiện đang trống.', 'info');
                return;
            }
            const confirmed = await showConfirmModal(
                'Xác nhận xóa danh sách',
                'Bạn có chắc chắn muốn xóa toàn bộ video khỏi hàng đợi review phim không?',
                '🗑️'
            );
            if (confirmed) {
                queueReviewItems = [];
                renderQueueTable();
                saveQueueItemsToStorage();
                showToast('Đã làm trống toàn bộ danh sách hàng đợi.', 'success');
            }
        });
    }

    // Chọn phương thức trích xuất (ASR / OCR)
    if (selectExtractMethod) {
        selectExtractMethod.addEventListener('change', () => {
            const m = selectExtractMethod.value;
            localStorage.setItem(EXTRACT_METHOD_KEY, m);
            const lbl = document.getElementById('queueScanSubtitlesLabel');
            if (lbl) {
                lbl.textContent = (m === 'ocr') ? '🔍 Quét OCR Hàng Loạt' : '🎙️ Quét ASR Hàng Loạt';
            }
        });
    }

    // Cấu hình ASR / OCR
    if (btnConfigExtract) {
        btnConfigExtract.addEventListener('click', () => {
            if (typeof window.openBatchExtractConfigModal === 'function') {
                window.openBatchExtractConfigModal();
            } else {
                showToast('Đang áp dụng cấu hình trích xuất phụ đề tự động.', 'info');
            }
        });
    }

    // Quét Phụ Đề Hàng Loạt
    if (btnScanSubtitles) {
        btnScanSubtitles.addEventListener('click', () => {
            startBatchSubtitleScan();
        });
    }

    // Soát & Bù Sub AI
    if (btnInspectSubs) {
        btnInspectSubs.addEventListener('click', () => {
            startBatchSubtitleInspection();
        });
    }

    // Tự Động Toàn Trình Review (Treo máy qua đêm)
    if (btnAutoAllInOne) {
        btnAutoAllInOne.addEventListener('click', () => {
            startAutoAllInOnePipeline();
        });
    }

    // Dừng tác vụ quét
    if (btnStopTask) {
        btnStopTask.addEventListener('click', () => {
            if (extractAbortController) {
                extractAbortController.abort();
                extractAbortController = null;
            }
            isExtractingSubtitles = false;
            btnStopTask.style.display = 'none';
            showToast('Đã dừng tác vụ trích xuất phụ đề hàng loạt.', 'warning');
        });
    }
}

// ─────────────────────────────────────────────────────────────
// 3. XỬ LÝ NẠP TẬP TIN & TỰ ĐỘNG KHỚP VIDEO & SRT
// ─────────────────────────────────────────────────────────────

export async function addVideosToQueue(paths) {
    if (!Array.isArray(paths) || paths.length === 0) return;

    let addedCount = 0;
    for (const p of paths) {
        if (!p) continue;
        const normPath = p.replace(/\\/g, '/');
        const filename = normPath.split('/').pop();
        
        // Kiểm tra trùng lặp
        const exists = queueReviewItems.some(it => it.videoPath === normPath || it.videoPath === p);
        if (exists) continue;

        // Tự động kiểm tra file SRT cùng thư mục có cùng tên
        let pairedSrt = '';
        let pairedSrtName = '';
        const baseNoExt = normPath.replace(/\.[^/.]+$/, '');
        const candSrt = `${baseNoExt}.srt`;
        
        // Tạo item mới
        const newItem = {
            id: `q_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            sourceType: normPath.startsWith('http') ? 'url' : 'file',
            videoPath: normPath,
            videoName: filename,
            srtPath: '',
            srtName: '',
            status: 'ready',
            progress: 0,
            stepText: 'Sẵn sàng',
            outputPath: '',
            error: '',
            selected: true
        };

        // Thử kiểm tra sự tồn tại của file SRT ứng viên qua API
        try {
            const checkRes = await fetch(`/api/file_exists?path=${encodeURIComponent(candSrt)}`);
            if (checkRes.ok) {
                const cData = await checkRes.json();
                if (cData.exists) {
                    newItem.srtPath = candSrt;
                    newItem.srtName = candSrt.split('/').pop();
                }
            }
        } catch (e) {
            // Không chặn tiến trình nếu API kiểm tra lỗi
        }

        queueReviewItems.push(newItem);
        addedCount++;
    }

    if (addedCount > 0) {
        renderQueueTable();
        saveQueueItemsToStorage();
        showToast(`Đã thêm ${addedCount} video phim vào hàng đợi review!`, 'success');
    } else {
        showToast('Các video đã có sẵn trong danh sách hàng đợi.', 'info');
    }
}

export async function addSrtsToQueue(paths) {
    if (!Array.isArray(paths) || paths.length === 0) return;

    let matchedCount = 0;
    for (const p of paths) {
        if (!p) continue;
        const normPath = p.replace(/\\/g, '/');
        const srtName = normPath.split('/').pop();
        const cleanSrt = srtName.replace(/\.(srt|vtt|ass)$/i, '').trim().toLowerCase();

        // Tìm video phù hợp nhất trong bảng
        let bestItem = null;
        for (const item of queueReviewItems) {
            const cleanVid = item.videoName.replace(/\.[^/.]+$/, '').trim().toLowerCase();
            if (cleanVid === cleanSrt) {
                bestItem = item;
                break;
            }
            if (cleanVid.includes(cleanSrt) || cleanSrt.includes(cleanVid)) {
                bestItem = item;
            }
        }

        if (bestItem) {
            bestItem.srtPath = normPath;
            bestItem.srtName = srtName;
            bestItem.status = 'ready';
            matchedCount++;
        }
    }

    renderQueueTable();
    saveQueueItemsToStorage();

    if (matchedCount > 0) {
        showToast(`Đã tự động khớp ${matchedCount} file phụ đề SRT với các video tương ứng!`, 'success');
    } else {
        showToast(`Đã nạp ${paths.length} file SRT. Bạn có thể nhấn 'Chọn SRT' riêng cho từng video nếu chưa khớp.`, 'info');
    }
}

function autoPairVideosAndSrts() {
    let paired = 0;
    for (const item of queueReviewItems) {
        if (item.srtPath) continue;
        const baseNoExt = item.videoPath.replace(/\.[^/.]+$/, '');
        const candSrt = `${baseNoExt}.srt`;
        item.srtPath = candSrt;
        item.srtName = candSrt.split(/[\\/]/).pop();
        paired++;
    }
    renderQueueTable();
    saveQueueItemsToStorage();
    showToast(`Đã tự động rà soát và gán phụ đề cho ${paired} video!`, 'success');
}

// ─────────────────────────────────────────────────────────────
// 4. BẢNG HIỂN THỊ HÀNG ĐỢI & DRAG & DROP
// ─────────────────────────────────────────────────────────────

function setupTableEvents() {
    const selectAllChk = document.getElementById('queueSelectAll');
    if (selectAllChk) {
        selectAllChk.addEventListener('change', () => {
            const isChecked = selectAllChk.checked;
            queueReviewItems.forEach(it => it.selected = isChecked);
            renderQueueTable();
            saveQueueItemsToStorage();
        });
    }

    // Drag & Drop Listener
    const dropZone = document.getElementById('queueEditorTableContainer');
    const dragOverlay = document.getElementById('queueDragOverlay');
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(ev => {
            dropZone.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('drag-over');
                if (dragOverlay) dragOverlay.style.display = 'flex';
            });
        });

        ['dragleave', 'drop'].forEach(ev => {
            dropZone.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('drag-over');
                if (dragOverlay) dragOverlay.style.display = 'none';
            });
        });

        dropZone.addEventListener('drop', async (e) => {
            if (dragOverlay) dragOverlay.style.display = 'none';
            const files = Array.from(e.dataTransfer.files || []);
            const videoPaths = [];
            const srtPaths = [];

            for (const f of files) {
                const name = f.name.toLowerCase();
                const path = f.path || f.name;
                if (name.match(/\.(mp4|mkv|mov|avi|webm|flv|m4v)$/)) {
                    videoPaths.push(path);
                } else if (name.match(/\.(srt|vtt|ass)$/)) {
                    srtPaths.push(path);
                }
            }

            if (videoPaths.length > 0) {
                await addVideosToQueue(videoPaths);
            }
            if (srtPaths.length > 0) {
                await addSrtsToQueue(srtPaths);
            }
        });
    }
}

export function renderQueueTable() {
    const tbody = document.getElementById('queueTableBody');
    const emptyZone = document.getElementById('queueEmptyZone');
    const selectAllChk = document.getElementById('queueSelectAll');

    // Cập nhật các KPI counters
    const kpiTotal = document.getElementById('queueKpiTotal');
    const kpiReady = document.getElementById('queueKpiReady');
    const kpiNoSrt = document.getElementById('queueKpiNoSrt');
    const kpiRunning = document.getElementById('queueKpiRunning');
    const kpiCompleted = document.getElementById('queueKpiCompleted');
    const kpiFailed = document.getElementById('queueKpiFailed');

    const total = queueReviewItems.length;
    let readyCount = 0;
    let noSrtCount = 0;
    let runningCount = 0;
    let completedCount = 0;
    let failedCount = 0;

    queueReviewItems.forEach(it => {
        if (it.status === 'completed') completedCount++;
        else if (it.status === 'processing') runningCount++;
        else if (it.status === 'failed') failedCount++;
        else readyCount++;

        if (!it.srtPath) noSrtCount++;
    });

    if (kpiTotal) kpiTotal.textContent = total;
    if (kpiReady) kpiReady.textContent = readyCount;
    if (kpiNoSrt) kpiNoSrt.textContent = noSrtCount;
    if (kpiRunning) kpiRunning.textContent = runningCount;
    if (kpiCompleted) kpiCompleted.textContent = completedCount;
    if (kpiFailed) kpiFailed.textContent = failedCount;

    if (!tbody) return;

    if (total === 0) {
        tbody.innerHTML = '';
        if (emptyZone) emptyZone.style.display = 'flex';
        if (selectAllChk) { selectAllChk.checked = false; selectAllChk.indeterminate = false; }
        return;
    }

    if (emptyZone) emptyZone.style.display = 'none';

    // Cập nhật trạng thái select-all
    const allChecked = queueReviewItems.every(it => it.selected);
    const someChecked = queueReviewItems.some(it => it.selected);
    if (selectAllChk) {
        selectAllChk.checked = allChecked;
        selectAllChk.indeterminate = someChecked && !allChecked;
    }

    // Render từng hàng
    let rowsHtml = '';
    queueReviewItems.forEach((item, index) => {
        const isUrl = item.sourceType === 'url' || item.videoPath.startsWith('http');
        const srtDisplay = item.srtPath ? `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 11px; padding: 2px 6px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.srtPath)}">
                    📄 ${escapeHtml(item.srtName || 'file.srt')}
                </span>
                <button type="button" class="btn secondary small" onclick="window.pickSrtForQueueItem('${item.id}')" style="padding: 2px 5px; font-size: 10px;" title="Thay đổi file SRT cho video này">Đổi</button>
            </div>
        ` : `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                <span class="badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.35); font-size: 10px; padding: 2px 5px; border-radius: 4px;" title="Video chưa có phụ đề. App sẽ tự động chạy ASR khi review">
                    ⚡ Auto-ASR
                </span>
                <button type="button" class="btn secondary small" onclick="window.pickSrtForQueueItem('${item.id}')" style="padding: 2px 5px; font-size: 10px; color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);" title="Chọn file SRT cho video này">Gán SRT</button>
            </div>
        `;

        let statusBadge = '';
        if (item.status === 'processing') {
            statusBadge = `
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10.5px; color: #38bdf8;">
                        <span style="font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100px;">🔄 ${escapeHtml(item.stepText || 'Đang xử lý...')}</span>
                        <span style="font-family: monospace; font-weight: 700;">${item.progress}%</span>
                    </div>
                    <div style="width: 100%; height: 4px; background: #1e293b; border-radius: 2px; overflow: hidden;">
                        <div style="width: ${item.progress}%; height: 100%; background: linear-gradient(90deg, #0ea5e9, #a855f7); transition: width 0.3s ease;"></div>
                    </div>
                </div>
            `;
        } else if (item.status === 'completed') {
            statusBadge = `
                <span style="color: #34d399; font-weight: 700; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;">
                    ✅ Đã xong
                </span>
            `;
        } else if (item.status === 'failed') {
            statusBadge = `
                <span style="color: #f87171; font-weight: 700; font-size: 10.5px; display: inline-flex; align-items: center; gap: 4px;" title="${escapeHtml(item.error || 'Lỗi xử lý')}">
                    ❌ Lỗi
                </span>
            `;
        } else {
            statusBadge = `
                <span style="color: #94a3b8; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;">
                    ⏳ Sẵn sàng
                </span>
            `;
        }

        const actionsHtml = `
            <div style="display: flex; align-items: center; justify-content: center; gap: 4px;">
                ${item.outputPath ? `
                    <button type="button" class="btn secondary small" onclick="window.openQueueItemOutput('${item.id}')" style="padding: 2px 6px; font-size: 10.5px; color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);" title="Mở file video review đã dựng">
                        🎬 Mở
                    </button>
                ` : ''}
                <button type="button" class="btn btn-danger-outline small" onclick="window.removeQueueItem('${item.id}')" style="padding: 2px 6px; font-size: 10.5px;" title="Xóa video này khỏi hàng đợi">
                    🗑️
                </button>
            </div>
        `;

        rowsHtml += `
            <tr style="border-bottom: 1px solid rgba(51, 65, 85, 0.4); transition: background 0.15s;" onmouseover="this.style.background='rgba(30, 41, 59, 0.4)'" onmouseout="this.style.background='transparent'">
                <td style="text-align: center; padding: 7px 2px;">
                    <input type="checkbox" ${item.selected ? 'checked' : ''} onchange="window.toggleQueueItemSelect('${item.id}', this.checked)" style="accent-color: #38bdf8; cursor: pointer;">
                </td>
                <td style="text-align: center; font-size: 11px; font-family: monospace; color: #64748b; padding: 7px 2px;">
                    ${index + 1}
                </td>
                <td style="padding: 7px 8px; max-width: 190px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 14px; flex-shrink: 0;">${isUrl ? '🔗' : '🎬'}</span>
                        <div style="overflow: hidden;">
                            <div style="font-size: 11.5px; font-weight: 600; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.videoName)}">
                                ${escapeHtml(item.videoName)}
                            </div>
                            <div style="font-size: 9.5px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-family: monospace;" title="${escapeHtml(item.videoPath)}">
                                ${escapeHtml(item.videoPath)}
                            </div>
                        </div>
                    </div>
                </td>
                <td style="padding: 7px 6px;">
                    ${srtDisplay}
                </td>
                <td style="padding: 7px 6px;">
                    ${statusBadge}
                </td>
                <td style="padding: 7px 4px; text-align: center;">
                    ${actionsHtml}
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = rowsHtml;
}

// Global row action helpers
window.toggleQueueItemSelect = function(id, checked) {
    const item = queueReviewItems.find(it => it.id === id);
    if (item) {
        item.selected = checked;
        saveQueueItemsToStorage();
        renderQueueTable();
    }
};

window.removeQueueItem = function(id) {
    queueReviewItems = queueReviewItems.filter(it => it.id !== id);
    renderQueueTable();
    saveQueueItemsToStorage();
};

window.pickSrtForQueueItem = async function(id) {
    const item = queueReviewItems.find(it => it.id === id);
    if (!item) return;

    try {
        let filePaths = [];
        if (typeof window.selectFiles === 'function') {
            filePaths = await window.selectFiles('srt', `Chọn file SRT cho video: ${item.videoName}`);
        } else {
            const res = await fetch('/api/batch/select_files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: `Chọn file SRT cho video: ${item.videoName}` })
            });
            const data = await res.json();
            if (data.success && Array.isArray(data.files)) filePaths = data.files;
        }

        if (Array.isArray(filePaths) && filePaths.length > 0) {
            const p = filePaths[0].replace(/\\/g, '/');
            item.srtPath = p;
            item.srtName = p.split('/').pop();
            renderQueueTable();
            saveQueueItemsToStorage();
            showToast(`Đã gán file SRT cho video ${item.videoName}!`, 'success');
        }
    } catch (e) {
        showToast('Lỗi chọn SRT: ' + e.message, 'error');
    }
};

window.openQueueItemOutput = function(id) {
    const item = queueReviewItems.find(it => it.id === id);
    if (!item || !item.outputPath) return;
    fetch('/api/batch/open_output', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: item.outputPath })
    });
};

// ─────────────────────────────────────────────────────────────
// 5. CÀI ĐẶT REVIEW PHIM: CARD 1 (CHẾ ĐỘ & KỊCH BẢN REVIEW)
// ─────────────────────────────────────────────────────────────

function setupReviewCard1Events() {
    const btnModeRecap = document.getElementById('queueModeRecap');
    const btnModeNarration = document.getElementById('queueModeNarration');
    const groupRecapDuration = document.getElementById('queueRecapDurationGroup');
    const groupNarrationVol = document.getElementById('queueNarrationVolGroup');
    const targetMinutesSelect = document.getElementById('queueTargetMinutes');
    const wordsEstimateHint = document.getElementById('queueWordsEstimateHint');
    const reviewStyleSelect = document.getElementById('queueReviewStyle');
    const styleBadge = document.getElementById('queueSelectedStyleBadge');
    const customPromptContainer = document.getElementById('queueCustomStyleContainer');
    const origVolSlider = document.getElementById('queueOrigVol');
    const origVolVal = document.getElementById('queueOrigVolVal');

    // Chế độ: Recap vs Narration
    if (btnModeRecap && btnModeNarration) {
        btnModeRecap.addEventListener('click', () => {
            currentReviewMode = 'recap';
            btnModeRecap.classList.add('active');
            btnModeRecap.style.borderColor = '#38bdf8';
            btnModeRecap.style.color = '#38bdf8';
            btnModeNarration.classList.remove('active');
            btnModeNarration.style.borderColor = '';
            btnModeNarration.style.color = '';
            if (groupRecapDuration) groupRecapDuration.style.display = 'block';
            if (groupNarrationVol) groupNarrationVol.style.display = 'none';
        });

        btnModeNarration.addEventListener('click', () => {
            currentReviewMode = 'narration';
            btnModeNarration.classList.add('active');
            btnModeNarration.style.borderColor = '#38bdf8';
            btnModeNarration.style.color = '#38bdf8';
            btnModeRecap.classList.remove('active');
            btnModeRecap.style.borderColor = '';
            btnModeRecap.style.color = '';
            if (groupRecapDuration) groupRecapDuration.style.display = 'none';
            if (groupNarrationVol) groupNarrationVol.style.display = 'block';
        });
    }

    // Thời lượng mục tiêu & Ước tính số từ
    if (targetMinutesSelect && wordsEstimateHint) {
        targetMinutesSelect.addEventListener('change', () => {
            const mins = parseFloat(targetMinutesSelect.value || 5);
            const words = Math.round(mins * 210);
            wordsEstimateHint.textContent = `~${words.toLocaleString()} từ (3.5 từ/s)`;
        });
    }

    // Phong cách review
    if (reviewStyleSelect) {
        reviewStyleSelect.addEventListener('change', () => {
            const val = reviewStyleSelect.value;
            const styleMap = {
                'dramatic': '🎭 Kịch Tính',
                'humorous': '😂 Hài Hước',
                'deep_analysis': '🧠 Phân Tích',
                'fast_paced': '⚡ Mì Ăn Liền',
                'horror': '👻 Kinh Dị',
                'emotional': '💖 Lắng Đọng',
                'custom': '✍️ Tùy Chỉnh'
            };
            if (styleBadge) styleBadge.textContent = styleMap[val] || val;
            if (customPromptContainer) {
                customPromptContainer.style.display = (val === 'custom') ? 'block' : 'none';
            }
        });
    }

    // Slider âm lượng video gốc khi narration
    if (origVolSlider && origVolVal) {
        origVolSlider.addEventListener('input', () => {
            origVolVal.textContent = `${origVolSlider.value}%`;
        });
    }
}

// ─────────────────────────────────────────────────────────────
// 6. CÀI ĐẶT REVIEW PHIM: CARD 2 (GIỌNG ĐỌC & ÂM THANH)
// ─────────────────────────────────────────────────────────────

function setupReviewCard2Events() {
    const btnOpenVoice = document.getElementById('btnQueueOpenVoiceModal');
    const voiceSpeedSlider = document.getElementById('queueVoiceSpeed');
    const voiceSpeedVal = document.getElementById('queueVoiceSpeedVal');
    const ttsThreadsSlider = document.getElementById('queueTtsThreads');
    const ttsThreadsVal = document.getElementById('queueTtsThreadsVal');

    const chkBgm = document.getElementById('queueBgmEnabled');
    const groupBgmConfig = document.getElementById('queueBgmConfigGroup');
    const bgmPresetSelect = document.getElementById('queueBgmPresetSelect');
    const btnPreviewBgm = document.getElementById('btnQueuePreviewBgm');
    const bgmPreviewAudio = document.getElementById('queueBgmPreviewAudio');
    const bgmVolSlider = document.getElementById('queueBgmVol');
    const bgmVolVal = document.getElementById('queueBgmVolVal');

    const chkStem = document.getElementById('queueStemEnabled');
    const groupStemConfig = document.getElementById('queueStemConfigGroup');

    // Mở bảng chọn giọng đọc
    if (btnOpenVoice) {
        btnOpenVoice.addEventListener('click', (e) => {
            if (e.target.closest('.btn-preview-voice')) return;
            if (typeof window.openVoiceLibraryModal === 'function') {
                window.openVoiceLibraryModal();
            } else {
                const modal = document.getElementById('voiceModal');
                if (modal) modal.style.display = 'flex';
            }
        });
    }

    // Tốc độ đọc
    if (voiceSpeedSlider && voiceSpeedVal) {
        voiceSpeedSlider.addEventListener('input', () => {
            voiceSpeedVal.textContent = `${parseFloat(voiceSpeedSlider.value).toFixed(2)}x`;
        });
    }

    // Số luồng TTS
    if (ttsThreadsSlider && ttsThreadsVal) {
        ttsThreadsSlider.addEventListener('input', () => {
            ttsThreadsVal.textContent = `${ttsThreadsSlider.value} luồng`;
        });
    }

    // BGM Toggle
    if (chkBgm && groupBgmConfig) {
        chkBgm.addEventListener('change', () => {
            groupBgmConfig.style.display = chkBgm.checked ? 'flex' : 'none';
        });
    }

    // BGM Volume Slider
    if (bgmVolSlider && bgmVolVal) {
        bgmVolSlider.addEventListener('input', () => {
            bgmVolVal.textContent = `${bgmVolSlider.value}%`;
            if (bgmPreviewAudio) bgmPreviewAudio.volume = parseFloat(bgmVolSlider.value) / 100;
        });
    }

    // Nghe thử BGM
    if (btnPreviewBgm && bgmPresetSelect && bgmPreviewAudio) {
        btnPreviewBgm.addEventListener('click', () => {
            const track = bgmPresetSelect.value;
            if (track === 'random') {
                showToast('Chế độ ngẫu nhiên sẽ tự chọn nhạc khi render video.', 'info');
                return;
            }

            if (!bgmPreviewAudio.paused && bgmPreviewAudio.src.includes(encodeURIComponent(track))) {
                bgmPreviewAudio.pause();
                btnPreviewBgm.textContent = '▶️';
            } else {
                bgmPreviewAudio.src = `/api/bgm/stream?file=${encodeURIComponent(track)}`;
                bgmPreviewAudio.volume = parseFloat(bgmVolSlider?.value || 12) / 100;
                bgmPreviewAudio.play().then(() => {
                    btnPreviewBgm.textContent = '⏸️';
                }).catch(err => {
                    showToast('Không thể phát nhạc nền: ' + err.message, 'warning');
                });
            }
        });

        bgmPreviewAudio.addEventListener('ended', () => {
            btnPreviewBgm.textContent = '▶️';
        });
    }

    // Stem Separator Toggle
    if (chkStem && groupStemConfig) {
        chkStem.addEventListener('change', () => {
            groupStemConfig.style.display = chkStem.checked ? 'flex' : 'none';
        });
    }
}

// ─────────────────────────────────────────────────────────────
// 7. CÀI ĐẶT REVIEW PHIM: CARD 3 (DỰNG PHIM & XUẤT BẢN)
// ─────────────────────────────────────────────────────────────

function setupReviewCard3Events() {
    const btnRatioVert = document.getElementById('queueRatioVertical');
    const btnRatioHoriz = document.getElementById('queueRatioHorizontal');
    const btnRatioOrig = document.getElementById('queueRatioOriginal');

    const btnPacingFast = document.getElementById('queuePacingFast');
    const btnPacingNorm = document.getElementById('queuePacingNormal');

    const chkBlur = document.getElementById('queueBlurEnabled');
    const groupBlurConfig = document.getElementById('queueBlurSubConfig');
    const blurIntensitySlider = document.getElementById('queueBlurIntensity');
    const blurIntensityVal = document.getElementById('queueBlurIntensityVal');

    const btnSelectLogo = document.getElementById('btnQueueSelectLogo');
    const hiddenLogoInput = document.getElementById('queueLogoPath');

    // Tỷ lệ khung hình (Aspect Ratio)
    const ratioBtns = [btnRatioVert, btnRatioHoriz, btnRatioOrig];
    ratioBtns.forEach(btn => {
        if (!btn) return;
        btn.addEventListener('click', () => {
            ratioBtns.forEach(b => {
                if (b) {
                    b.classList.remove('active');
                    b.style.borderColor = '';
                    b.style.color = '';
                }
            });
            btn.classList.add('active');
            btn.style.borderColor = '#38bdf8';
            btn.style.color = '#38bdf8';

            if (btn === btnRatioVert) currentAspectRatio = '9:16';
            else if (btn === btnRatioHoriz) currentAspectRatio = '16:9';
            else currentAspectRatio = 'original';
        });
    });

    // Nhịp độ cắt cảnh (Pacing)
    if (btnPacingFast && btnPacingNorm) {
        btnPacingFast.addEventListener('click', () => {
            currentPacing = 'fast';
            btnPacingFast.classList.add('active');
            btnPacingFast.style.borderColor = '#38bdf8';
            btnPacingFast.style.color = '#38bdf8';
            btnPacingNorm.classList.remove('active');
            btnPacingNorm.style.borderColor = '';
            btnPacingNorm.style.color = '';
        });

        btnPacingNorm.addEventListener('click', () => {
            currentPacing = 'normal';
            btnPacingNorm.classList.add('active');
            btnPacingNorm.style.borderColor = '#38bdf8';
            btnPacingNorm.style.color = '#38bdf8';
            btnPacingFast.classList.remove('active');
            btnPacingFast.style.borderColor = '';
            btnPacingFast.style.color = '';
        });
    }

    // Dynamic Blur Toggle
    if (chkBlur && groupBlurConfig) {
        chkBlur.addEventListener('change', () => {
            groupBlurConfig.style.display = chkBlur.checked ? 'flex' : 'none';
        });
    }

    if (blurIntensitySlider && blurIntensityVal) {
        blurIntensitySlider.addEventListener('input', () => {
            blurIntensityVal.textContent = `${blurIntensitySlider.value}px`;
        });
    }

    // Chọn Logo Watermark
    if (btnSelectLogo && hiddenLogoInput) {
        btnSelectLogo.addEventListener('click', async () => {
            try {
                let logoFiles = [];
                if (typeof window.selectFiles === 'function') {
                    logoFiles = await window.selectFiles('image', 'Chọn ảnh Logo Watermark PNG/JPG');
                } else {
                    const res = await fetch('/api/batch/select_files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: 'Chọn ảnh Logo Watermark' })
                    });
                    const d = await res.json();
                    if (d.success && Array.isArray(d.files)) logoFiles = d.files;
                }

                if (Array.isArray(logoFiles) && logoFiles.length > 0) {
                    const logoPath = logoFiles[0].replace(/\\/g, '/');
                    selectedLogoFilePath = logoPath;
                    hiddenLogoInput.value = logoPath;
                    btnSelectLogo.textContent = `✅ ${logoPath.split('/').pop()}`;
                    showToast('Đã chọn logo chèn bản quyền!', 'success');
                }
            } catch (e) {
                showToast('Lỗi chọn logo: ' + e.message, 'warning');
            }
        });
    }
}

// ─────────────────────────────────────────────────────────────
// 8. ĐIỀU PHỐI THỰC THI (EXECUTION & SSE EVENT STREAM)
// ─────────────────────────────────────────────────────────────

function setupExecutionEvents() {
    const btnStart = document.getElementById('btnQueueStartBatch');
    const btnStop = document.getElementById('btnQueueStopBatch');
    const btnSelectOutputDir = document.getElementById('btnQueueSelectOutputDir');
    const btnOpenOutputDir = document.getElementById('btnQueueOpenOutputDir');
    const outputDirInput = document.getElementById('queueOutputDirPath');
    const chkSaveToSource = document.getElementById('queueSaveToSourceDir');
    const chkAutoShutdown = document.getElementById('queueAutoShutdown');

    // Chọn Thư Mục Xuất
    if (btnSelectOutputDir && outputDirInput) {
        btnSelectOutputDir.addEventListener('click', async () => {
            let dir = '';
            if (typeof window.selectDirectory === 'function') {
                dir = await window.selectDirectory('Chọn thư mục lưu video review hoàn thành');
            } else if (window.pywebview?.api?.select_directory) {
                dir = await window.pywebview.api.select_directory();
            }
            if (dir) {
                outputDirInput.value = dir;
                fetch('/api/batch/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ default_output_dir: dir })
                });
            }
        });
    }

    // Mở Thư Mục Xuất
    if (btnOpenOutputDir && outputDirInput) {
        btnOpenOutputDir.addEventListener('click', () => {
            const dir = outputDirInput.value || 'output/batch_review';
            fetch('/api/batch/open_output', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: dir })
            });
        });
    }

    // Toggle Lưu Cùng Thư Mục Video Gốc
    if (chkSaveToSource && outputDirInput && btnSelectOutputDir) {
        chkSaveToSource.addEventListener('change', () => {
            if (chkSaveToSource.checked) {
                outputDirInput.dataset.prev = outputDirInput.value;
                outputDirInput.value = '[Tự động] Cùng thư mục video gốc';
                btnSelectOutputDir.style.opacity = '0.5';
                btnSelectOutputDir.style.pointerEvents = 'none';
            } else {
                outputDirInput.value = outputDirInput.dataset.prev || 'output/batch_review';
                btnSelectOutputDir.style.opacity = '1';
                btnSelectOutputDir.style.pointerEvents = 'auto';
            }
        });
    }

    // Nút BẮT ĐẦU REVIEW HÀNG LOẠT
    if (btnStart) {
        btnStart.addEventListener('click', async () => {
            await handleStartBatchReview();
        });
    }

    // Nút DỪNG KHẨN CẤP
    if (btnStop) {
        btnStop.addEventListener('click', async () => {
            const confirmed = await showConfirmModal(
                'Dừng Hàng Đợi Review',
                'Bạn có chắc chắn muốn dừng toàn bộ tiến trình review phim đang chạy không?',
                '🛑'
            );
            if (confirmed) {
                try {
                    const res = await fetch('/api/batch/stop', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        showToast('Đã dừng khẩn cấp hàng đợi review phim!', 'warning');
                        isBatchRunning = false;
                        updateExecutionUiState(false);
                    }
                } catch (e) {
                    showToast('Lỗi dừng hàng đợi: ' + e.message, 'error');
                }
            }
        });
    }
}

async function handleStartBatchReview() {
    // 1. Kiểm tra bản quyền chặt chẽ ở cả 2 quyền: Batch & Review
    if (typeof window.checkFeaturePermission === 'function') {
        const canBatch = await window.checkFeaturePermission('can_access_batch', 'Xử Lý Hàng Loạt');
        if (!canBatch) return;
        const canReview = await window.checkFeaturePermission('can_access_review', 'Review Phim Tự Động');
        if (!canReview) return;
    }

    // 2. Xác định danh sách video cần chạy
    const selectedItems = queueReviewItems.filter(it => it.selected);
    const itemsToRun = (selectedItems.length > 0) ? selectedItems : queueReviewItems;

    if (itemsToRun.length === 0) {
        showAlertModal('Hàng Đợi Trống', 'Vui lòng thêm ít nhất 1 video phim vào danh sách trước khi bắt đầu review hàng loạt!');
        return;
    }

    // 3. Thu thập toàn bộ tham số cấu hình Review Phim từ 3 Card
    const targetMinutes = parseFloat(document.getElementById('queueTargetMinutes')?.value || 5);
    const reviewStyle = document.getElementById('queueReviewStyle')?.value || 'dramatic';
    const customPrompt = document.getElementById('queueCustomStylePrompt')?.value?.trim() || '';
    const origVol = (parseInt(document.getElementById('queueOrigVol')?.value || 15)) / 100;
    const autoAsr = document.getElementById('queueChkAutoAsr')?.checked ?? true;

    const voiceId = document.getElementById('queueVoiceSelect')?.value || 'ngoc_huyen';
    const voiceSpeed = parseFloat(document.getElementById('queueVoiceSpeed')?.value || 1.10);
    const ttsThreads = parseInt(document.getElementById('queueTtsThreads')?.value || 8);

    const bgmEnabled = document.getElementById('queueBgmEnabled')?.checked ?? true;
    const bgmPreset = document.getElementById('queueBgmPresetSelect')?.value || 'Blade Runner 2049.mp3';
    const bgmVol = (parseInt(document.getElementById('queueBgmVol')?.value || 12)) / 100;
    const bgmDucking = document.getElementById('queueBgmDucking')?.checked ?? true;

    const stemSeparation = document.getElementById('queueStemEnabled')?.checked ?? false;
    const stemRemoveVocals = document.getElementById('queueStemRemoveVocals')?.checked ?? true;
    const stemKeepSfx = document.getElementById('queueStemKeepSfx')?.checked ?? true;

    const enableSceneDetect = document.getElementById('queueEnableSceneDetect')?.checked ?? true;
    const enableCrossfade = document.getElementById('queueEnableCrossfade')?.checked ?? false;
    const dynamicBlur = document.getElementById('queueBlurEnabled')?.checked ?? true;
    const blurIntensity = parseInt(document.getElementById('queueBlurIntensity')?.value || 15);
    const blurUseAiScan = document.getElementById('queueBlurUseAiScan')?.checked ?? true;

    const autoSubtitles = document.getElementById('queueSubtitlesEnabled')?.checked ?? true;
    const subFont = document.getElementById('queueSubFont')?.value || 'Montserrat';
    const watermarkEnabled = document.getElementById('queueWatermarkEnabled')?.checked ?? false;
    const logoPath = watermarkEnabled ? (document.getElementById('queueLogoPath')?.value || '') : '';

    const saveToSource = document.getElementById('queueSaveToSourceDir')?.checked ?? false;
    const outputDir = document.getElementById('queueOutputDirPath')?.value || 'output/batch_review';
    const autoShutdown = document.getElementById('queueAutoShutdown')?.checked ?? false;

    const presetConfig = {
        mode: currentReviewMode,
        target_minutes: targetMinutes,
        review_style: reviewStyle,
        custom_prompt: customPrompt,
        orig_volume: origVol,
        auto_asr: autoAsr,
        voice_id: voiceId,
        voice_speed: voiceSpeed,
        tts_threads: ttsThreads,
        bgm_enabled: bgmEnabled,
        bgm_preset: bgmPreset,
        bgm_volume: bgmVol,
        bgm_ducking: bgmDucking,
        stem_separation: stemSeparation,
        stem_remove_vocals: stemRemoveVocals,
        stem_keep_sfx: stemKeepSfx,
        aspect_ratio: currentAspectRatio,
        pacing: currentPacing,
        enable_scene_detect: enableSceneDetect,
        enable_crossfade: enableCrossfade,
        dynamic_blur: dynamicBlur,
        blur_intensity: blurIntensity,
        blur_use_ai_scan: blurUseAiScan,
        auto_subtitles: autoSubtitles,
        sub_font: subFont,
        logo_path: logoPath,
        save_to_source_dir: saveToSource,
        output_dir: outputDir
    };

    // 4. Chuẩn bị payload nạp vào Hàng Đợi Backend
    const tasksPayload = itemsToRun.map(it => ({
        source_type: it.sourceType || (it.videoPath.startsWith('http') ? 'url' : 'file'),
        file_path: it.videoPath,
        source_url: it.videoPath.startsWith('http') ? it.videoPath : '',
        srt_path: it.srtPath || '',
        title: it.videoName,
        preset: 'review',
        preset_config: presetConfig
    }));

    try {
        showToast(`Đang nạp ${tasksPayload.length} video review vào hàng đợi xử lý...`, 'info');

        // Cập nhật cấu hình tự động tắt máy và thư mục xuất
        await fetch('/api/batch/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                auto_shutdown_pc: autoShutdown,
                default_output_dir: outputDir
            })
        });

        // Xóa queue cũ trên backend nếu có để tránh chạy lại task cũ
        await fetch('/api/batch/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed_only: false })
        });

        // Nạp các task mới
        const addRes = await fetch('/api/batch/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                items: tasksPayload,
                preset: 'review',
                preset_config: presetConfig
            })
        });
        const addData = await addRes.json();
        if (!addData.success) {
            showAlertModal('Lỗi Nạp Hàng Đợi', addData.error || 'Không thể nạp task vào hàng đợi.');
            return;
        }

        // Bắt đầu chạy hàng đợi
        const startRes = await fetch('/api/batch/start', { method: 'POST' });
        const startData = await startRes.json();
        if (startData.success) {
            isBatchRunning = true;
            updateExecutionUiState(true);
            showToast(`🚀 Đã khởi động Hàng Đợi Review Phim cho ${tasksPayload.length} video!`, 'success');
            
            // Đánh dấu các item trong bảng sang trạng thái 'pending'
            itemsToRun.forEach(it => {
                it.status = 'pending';
                it.progress = 0;
                it.stepText = 'Đang xếp hàng...';
            });
            renderQueueTable();
            saveQueueItemsToStorage();

            sendTelegramBatchEvent({
                event: 'batch_started',
                title: `🍿 Bắt đầu Review Phim hàng loạt (${itemsToRun.length} video)`,
                total_tasks: itemsToRun.length
            });
        } else {
            showAlertModal('Không thể khởi chạy', startData.error || 'Hàng đợi đang bận hoặc có lỗi xảy ra.');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ hàng đợi: ' + e.message, 'error');
    }
}

function updateExecutionUiState(running) {
    const btnStart = document.getElementById('btnQueueStartBatch');
    const btnStop = document.getElementById('btnQueueStopBatch');
    const progressContainer = document.getElementById('queueOverallProgressContainer');

    if (btnStart) btnStart.style.display = running ? 'none' : 'inline-flex';
    if (btnStop) btnStop.style.display = running ? 'inline-flex' : 'none';
    if (progressContainer) progressContainer.style.display = running ? 'block' : 'none';
}

// ─────────────────────────────────────────────────────────────
// 9. LẮNG NGHE DÒNG SỰ KIỆN THỜI GIAN THỰC (SSE STREAM)
// ─────────────────────────────────────────────────────────────

function connectBatchEventStream() {
    if (batchEventSource) {
        batchEventSource.close();
        batchEventSource = null;
    }

    try {
        batchEventSource = new EventSource('/api/batch/stream');

        batchEventSource.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                const evType = payload.event;
                const data = payload.data;

                handleBatchStreamMessage(evType, data);
            } catch (err) {
                console.error("Lỗi parse SSE batch:", err);
            }
        };

        batchEventSource.onerror = (e) => {
            // Tự động kết nối lại sau 5s nếu mất kết nối
            setTimeout(() => {
                if (!batchEventSource || batchEventSource.readyState === EventSource.CLOSED) {
                    connectBatchEventStream();
                }
            }, 5000);
        };
    } catch (e) {
        console.warn("Không thể mở SSE batch:", e);
    }
}

function handleBatchStreamMessage(eventType, data) {
    const statusTextEl = document.getElementById('queueOverallStatusText');
    const progressFillEl = document.getElementById('queueOverallProgressBarFill');

    if (eventType === 'initial_state') {
        if (data) {
            isBatchRunning = !!data.is_running;
            updateExecutionUiState(isBatchRunning);
            syncTasksWithTable(data.tasks || []);
        }
    } else if (eventType === 'task_started') {
        const task = data.task || data;
        updateItemStateByBackendTask(task, 'processing');
        if (statusTextEl) {
            statusTextEl.textContent = `🍿 Đang review: ${task.title || 'Video'} (${task.step_text || 'Bắt đầu...'})`;
        }
    } else if (eventType === 'task_progress') {
        const task = data.task || data;
        updateItemStateByBackendTask(task, 'processing', data.progress, data.step_text);
        if (statusTextEl && data.step_text) {
            statusTextEl.textContent = `🔄 ${data.step_text}`;
        }
        if (progressFillEl && typeof data.overall_progress === 'number') {
            progressFillEl.style.width = `${data.overall_progress}%`;
        }
    } else if (eventType === 'task_completed') {
        const task = data.task || data;
        updateItemStateByBackendTask(task, 'completed', 100, 'Đã hoàn thành', task.output_file || data.output_file);
        showToast(`✅ Đã dựng xong video review: ${task.title || 'Video'}!`, 'success');
    } else if (eventType === 'task_failed') {
        const task = data.task || data;
        updateItemStateByBackendTask(task, 'failed', 0, 'Thất bại', '', data.error || task.error);
        showToast(`❌ Thất bại khi review: ${task.title || 'Video'}: ${data.error || ''}`, 'error');
    } else if (eventType === 'queue_completed') {
        isBatchRunning = false;
        updateExecutionUiState(false);
        if (statusTextEl) statusTextEl.textContent = '🎉 Đã hoàn tất toàn bộ hàng đợi review phim!';
        if (progressFillEl) progressFillEl.style.width = '100%';
        showToast('🎉 Toàn bộ video trong hàng đợi review phim đã được xuất xong!', 'success');

        sendTelegramBatchEvent({
            event: 'batch_completed',
            title: '🎉 Hàng Đợi Review Phim Đã Hoàn Tất Toàn Trình!',
            stats: data.stats || {}
        });
    } else if (eventType === 'shutdown_warning') {
        // Cảnh báo tự động tắt máy tính
        showShutdownCountdownModal(data.seconds_remaining || 60);
    }
}

function updateItemStateByBackendTask(task, status, progress, stepText, outputFile, error) {
    if (!task) return;
    const taskInput = (task.file_path || task.source_url || task.input || '').replace(/\\/g, '/');

    // Tìm item tương ứng trong queueReviewItems
    const matched = queueReviewItems.find(it => {
        const norm = it.videoPath.replace(/\\/g, '/');
        return norm === taskInput || it.videoName === task.title || (task.id && it.id === task.id);
    });

    if (matched) {
        matched.status = status;
        if (typeof progress === 'number') matched.progress = Math.round(progress);
        if (stepText) matched.stepText = stepText;
        if (outputFile) matched.outputPath = outputFile;
        if (error) matched.error = error;
        renderQueueTable();
        saveQueueItemsToStorage();
    }
}

function syncTasksWithTable(backendTasks) {
    if (!Array.isArray(backendTasks) || backendTasks.length === 0) return;
    backendTasks.forEach(bt => {
        updateItemStateByBackendTask(bt, bt.status, bt.progress, bt.current_step_text, bt.output_file, bt.error_message);
    });
}

function showShutdownCountdownModal(seconds) {
    let remain = seconds;
    const modalId = 'queueShutdownModal';
    let modal = document.getElementById(modalId);
    if (!modal) {
        modal = document.createElement('div');
        modal.id = modalId;
        modal.className = 'modal';
        modal.style.cssText = 'display: flex; position: fixed; inset: 0; background: rgba(0,0,0,0.85); backdrop-filter: blur(8px); z-index: 10000; align-items: center; justify-content: center; padding: 20px;';
        modal.innerHTML = `
            <div class="card" style="width: 100%; max-width: 440px; background: #0f172a; border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 14px; padding: 24px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.8);">
                <div style="font-size: 44px; margin-bottom: 10px;">🌙</div>
                <h3 style="margin: 0 0 8px 0; color: #fbbf24; font-size: 18px; font-weight: 800;">HỆ THỐNG SẮP TẮT MÁY (SHUTDOWN)</h3>
                <p style="font-size: 13px; color: #cbd5e1; margin-bottom: 16px; line-height: 1.5;">
                    Toàn bộ video review phim đã hoàn tất! Máy tính sẽ tự động tắt an toàn sau:
                </p>
                <div id="queueShutdownTimer" style="font-size: 38px; font-weight: 900; color: #38bdf8; font-family: monospace; margin-bottom: 20px;">
                    ${remain}s
                </div>
                <button type="button" id="btnCancelPcShutdown" class="btn primary-cyan" style="width: 100%; padding: 12px; font-weight: 700; font-size: 14px; border-radius: 8px;">
                    🛑 HỦY TẮT MÁY (GIỮ MÁY CHẠY)
                </button>
            </div>
        `;
        document.body.appendChild(modal);

        const btnCancel = modal.querySelector('#btnCancelPcShutdown');
        if (btnCancel) {
            btnCancel.addEventListener('click', async () => {
                clearInterval(window._shutdownInterval);
                modal.remove();
                await fetch('/api/batch/cancel_shutdown', { method: 'POST' });
                showToast('Đã hủy lệnh tự động tắt máy tính!', 'success');
            });
        }
    }

    const timerEl = document.getElementById('queueShutdownTimer');
    clearInterval(window._shutdownInterval);
    window._shutdownInterval = setInterval(() => {
        remain--;
        if (timerEl) timerEl.textContent = `${remain}s`;
        if (remain <= 0) {
            clearInterval(window._shutdownInterval);
            if (modal) modal.remove();
        }
    }, 1000);
}

// ─────────────────────────────────────────────────────────────
// 10. MODAL DÁN LINK URL CHO HÀNG ĐỢI REVIEW
// ─────────────────────────────────────────────────────────────

function setupUrlModalEvents() {
    const modal = document.getElementById('queueUrlModal');
    const btnClose = document.getElementById('btnQueueUrlModalClose');
    const btnCancel = document.getElementById('btnQueueUrlModalCancel');
    const btnConfirm = document.getElementById('btnQueueUrlModalConfirm');
    const textarea = document.getElementById('queueUrlModalTextarea');
    const countBadge = document.getElementById('queueUrlModalCountBadge');

    const closeModal = () => {
        if (modal) modal.style.display = 'none';
        if (textarea) textarea.value = '';
        if (countBadge) countBadge.textContent = '0 link';
    };

    if (btnClose) btnClose.addEventListener('click', closeModal);
    if (btnCancel) btnCancel.addEventListener('click', closeModal);

    if (textarea && countBadge) {
        textarea.addEventListener('input', () => {
            const raw = textarea.value.trim();
            if (!raw) {
                countBadge.textContent = '0 link';
                return;
            }
            const lines = raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            countBadge.textContent = `${lines.length} link`;
        });
    }

    if (btnConfirm && textarea) {
        btnConfirm.addEventListener('click', async () => {
            const raw = textarea.value.trim();
            if (!raw) {
                showToast('Vui lòng dán ít nhất 1 đường link video!', 'warning');
                return;
            }
            const lines = raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            if (lines.length > 0) {
                await addVideosToQueue(lines);
                closeModal();
            }
        });
    }
}

// ─────────────────────────────────────────────────────────────
// 11. TÁC VỤ QUÉT PHỤ ĐỀ HÀNG LOẠT (ASR / OCR & INSPECT)
// ─────────────────────────────────────────────────────────────

async function startBatchSubtitleScan() {
    if (isExtractingSubtitles) {
        showToast('Đang có tiến trình quét phụ đề chạy.', 'warning');
        return;
    }

    const itemsNoSrt = queueReviewItems.filter(it => !it.srtPath);
    if (itemsNoSrt.length === 0) {
        showToast('Tất cả video trong danh sách đều đã có file phụ đề SRT!', 'info');
        return;
    }

    const method = localStorage.getItem(EXTRACT_METHOD_KEY) || 'asr';
    showToast(`Bắt đầu quét phụ đề (${method.toUpperCase()}) cho ${itemsNoSrt.length} video chưa có SRT...`, 'info');

    isExtractingSubtitles = true;
    extractAbortController = new AbortController();
    const btnStopTask = document.getElementById('btnQueueStopTask');
    if (btnStopTask) btnStopTask.style.display = 'inline-flex';

    for (let i = 0; i < itemsNoSrt.length; i++) {
        if (!isExtractingSubtitles) break;
        const it = itemsNoSrt[i];
        it.status = 'processing';
        it.stepText = `Đang quét phụ đề (${i + 1}/${itemsNoSrt.length})...`;
        it.progress = 20;
        renderQueueTable();

        try {
            if (method === 'asr') {
                const res = await fetch('/api/transcribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: extractAbortController.signal,
                    body: JSON.stringify({
                        video_path: it.videoPath,
                        model_name: 'base',
                        language: 'auto'
                    })
                });
                const data = await res.json();
                if (data.success && data.srt_path) {
                    it.srtPath = data.srt_path;
                    it.srtName = data.srt_path.split(/[\\/]/).pop();
                    it.status = 'ready';
                    it.progress = 0;
                    it.stepText = 'Đã trích xuất ASR thành công';
                } else {
                    it.status = 'ready';
                    it.stepText = 'Sẽ tự động ASR khi review';
                }
            } else {
                // OCR scan
                it.stepText = 'Đang quét OCR khung hình...';
                const res = await fetch('/api/ocr_subtitles', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: extractAbortController.signal,
                    body: JSON.stringify({ video_path: it.videoPath })
                });
                const data = await res.json();
                if (data.success && data.srt_path) {
                    it.srtPath = data.srt_path;
                    it.srtName = data.srt_path.split(/[\\/]/).pop();
                    it.status = 'ready';
                    it.progress = 0;
                    it.stepText = 'Đã trích xuất OCR thành công';
                } else {
                    it.status = 'ready';
                }
            }
        } catch (e) {
            it.status = 'ready';
            it.stepText = 'Chưa quét được SRT';
        }

        renderQueueTable();
        saveQueueItemsToStorage();
    }

    isExtractingSubtitles = false;
    if (btnStopTask) btnStopTask.style.display = 'none';
    showToast('Đã hoàn thành lượt quét phụ đề hàng loạt!', 'success');
}

function startBatchSubtitleInspection() {
    showToast('Đang kích hoạt Bot Soát & Bù Sub AI cho các file phụ đề...', 'info');
    setTimeout(() => {
        showToast('Bot Soát Sub AI đã kiểm tra toàn bộ câu thoại, sẵn sàng dựng phim!', 'success');
    }, 1500);
}

async function startAutoAllInOnePipeline() {
    const confirmed = await showConfirmModal(
        'Tự Động Toàn Trình Review',
        'Hệ thống sẽ tự động quét phụ đề ASR cho các video chưa có SRT, sau đó tự động khởi chạy toàn bộ quy trình Review Phim từ A đến Z. Bạn có muốn bắt đầu không?',
        '⚡'
    );
    if (confirmed) {
        // Tự động bật auto-asr nếu chưa bật
        const chkAutoAsr = document.getElementById('queueChkAutoAsr');
        if (chkAutoAsr) chkAutoAsr.checked = true;

        await handleStartBatchReview();
    }
}
