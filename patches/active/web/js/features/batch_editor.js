/**
 * Batch Video Editor Feature Module (Biên Tập Hàng Loạt)
 * NovaCut - AI Video & Review Editor
 */

import { appendLog, showToast, showConfirmModal, showAlertModal, formatTimeSec, parseTimeToSeconds, formatSrtTimestamp, escapeHtml, timeNow } from '../utils.js';

// Danh sách các video trong hàng đợi biên tập hàng loạt
export let batchEditorItems = [];
window.batchCustomOverlayLayers = [];
let isBatchRunning = false;
let batchAbortController = null;
let taskAbortController = null;
let currentBatchItemIndex = -1;

// Biến lưu trữ item đang được mở trong Modal Sửa Chi Tiết
let activeModalItemIndex = -1;

const STORAGE_KEY = 'novacut_batch_editor_items';
const BATCH_OVERLAY_STORAGE_KEY = 'novacut_batch_overlay_layers';

/**
 * Gửi thông báo sự kiện batch qua Telegram API mà không làm gián đoạn pipeline
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
        // Lỗi mạng Telegram không bao giờ làm dừng hoặc ảnh hưởng pipeline biên tập
    }
}

/**
 * Khởi tạo toàn bộ module Biên tập hàng loạt
 */
export function initBatchEditorModule() {
    window.renderBatchTable = renderBatchTable;
    window.addVideosToBatch = addVideosToBatch;
    window.startBatchOcrScan = startBatchOcrScan;
    window.startBatchTranslateAndClean = startBatchTranslateAndClean;
    window.startBatchAllInOnePipeline = startBatchAllInOnePipeline;
    window.stopCurrentBatchTask = stopCurrentBatchTask;
    loadSavedBatchItems();
    setupBatchToolbarEvents();
    setupBatchTableEvents();
    setupBatchGlobalPresetEvents();
    setupBatchMultiOverlayLayers();
    setupBatchExecutionEvents();
    setupBatchModalDetailEvents();
    renderBatchTable();
}

/**
 * Khôi phục danh sách hàng đợi từ localStorage
 */
function loadSavedBatchItems() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) {
                batchEditorItems = parsed.map(item => {
                    let ocrRegion = item.ocrRegion;
                    if (ocrRegion && typeof ocrRegion === 'object') {
                        const w = Number(ocrRegion.w ?? ocrRegion.width ?? 60);
                        const h = Number(ocrRegion.h ?? ocrRegion.height ?? 9.5);
                        const x = Number(ocrRegion.x ?? 20);
                        const y = Number(ocrRegion.y ?? 81.5);
                        ocrRegion = { x, y, w, h, width: w, height: h };
                    } else {
                        ocrRegion = { x: 20, y: 81.5, w: 60, h: 9.5, width: 60, height: 9.5 };
                    }
                    return {
                        ...item,
                        ocrRegion,
                        status: (item.status === 'processing') ? 'pending' : item.status,
                        progress: (item.status === 'completed') ? 100 : 0
                    };
                });
            }
        }
    } catch (e) {
        console.warn("Không thể khôi phục danh sách batch từ storage:", e);
        batchEditorItems = [];
    }
}

/**
 * Lưu danh sách hàng đợi vào localStorage
 */
function saveBatchItemsToStorage() {
    try {
        // Chỉ lưu tối đa 50 item gần nhất và loại bỏ blob data để tránh quá tải quota
        const toSave = batchEditorItems.slice(0, 50).map(item => ({
            id: item.id,
            videoPath: item.videoPath,
            videoName: item.videoName,
            srtPath: item.srtPath,
            srtName: item.srtName,
            subtitles: (item.subtitles && item.subtitles.length <= 3000) ? item.subtitles : [],
            ocrRegion: item.ocrRegion,
            status: item.status,
            outputPath: item.outputPath || ''
        }));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) {
        console.warn("Lỗi lưu batch items vào storage:", e);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. TOOLBAR VÀ IMPORT VIDEO / SRT
// ─────────────────────────────────────────────────────────────────────────────

function setupBatchToolbarEvents() {
    // 1. Thêm Video qua hộp thoại hệ thống
    const btnAddVideos = document.getElementById('btnBatchAddVideos');
    if (btnAddVideos) {
        btnAddVideos.addEventListener('click', async () => {
            try {
                let filePaths = [];
                if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.select_multiple_videos === 'function') {
                    filePaths = await window.pywebview.api.select_multiple_videos();
                } else if (typeof window.selectFiles === 'function') {
                    filePaths = await window.selectFiles('video', 'Chọn các video cần biên tập hàng loạt');
                } else {
                    const res = await fetch('/api/select_files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            type: 'video',
                            title: 'Chọn các video cần biên tập hàng loạt'
                        })
                    });
                    const data = await res.json();
                    if (data.success && Array.isArray(data.file_paths) && data.file_paths.length > 0) {
                        filePaths = data.file_paths;
                    } else if (data.success && Array.isArray(data.files) && data.files.length > 0) {
                        filePaths = data.files;
                    }
                }

                if (Array.isArray(filePaths) && filePaths.length > 0) {
                    await addVideosToBatch(filePaths);
                }
            } catch (e) {
                console.error("Lỗi khi thêm video hàng loạt qua dialog hệ thống:", e);
                if (!window.pywebview) {
                    document.getElementById('batchHiddenVideoInput')?.click();
                }
            }
        });
    }

    // Hidden video file input
    const hiddenVideoInput = document.getElementById('batchHiddenVideoInput');
    if (hiddenVideoInput) {
        hiddenVideoInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length > 0) {
                const videoPaths = [];
                for (const f of files) {
                    if (f.path) {
                        videoPaths.push(f.path);
                    } else {
                        let resolved = null;
                        try {
                            const res = await fetch(`/api/resolve_media_path?path=${encodeURIComponent(f.name)}`);
                            if (res.ok) {
                                const d = await res.json();
                                if (d.success && d.resolved_path) resolved = d.resolved_path;
                            }
                        } catch (err) {}
                        videoPaths.push(resolved || f.name);
                    }
                }
                await addVideosToBatch(videoPaths);
            }
            hiddenVideoInput.value = '';
        });
    }

    // 2. Thêm nhiều SRT
    const btnAddSrts = document.getElementById('btnBatchAddSrts');
    if (btnAddSrts) {
        btnAddSrts.addEventListener('click', async () => {
            try {
                let filePaths = [];
                if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.select_multiple_srts === 'function') {
                    filePaths = await window.pywebview.api.select_multiple_srts();
                } else if (typeof window.selectFiles === 'function') {
                    filePaths = await window.selectFiles('srt', 'Chọn các file phụ đề .srt để gán cho video');
                } else {
                    const res = await fetch('/api/select_files', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            type: 'srt',
                            title: 'Chọn các file phụ đề .srt để gán cho video'
                        })
                    });
                    const data = await res.json();
                    if (data.success && Array.isArray(data.file_paths) && data.file_paths.length > 0) {
                        filePaths = data.file_paths;
                    } else if (data.success && Array.isArray(data.files) && data.files.length > 0) {
                        filePaths = data.files;
                    }
                }

                if (Array.isArray(filePaths) && filePaths.length > 0) {
                    await addSrtsToBatch(filePaths);
                }
            } catch (e) {
                console.error("Lỗi khi thêm SRT hàng loạt qua dialog hệ thống:", e);
                if (!window.pywebview) {
                    document.getElementById('batchHiddenSrtInput')?.click();
                }
            }
        });
    }

    // Hidden srt file input
    const hiddenSrtInput = document.getElementById('batchHiddenSrtInput');
    if (hiddenSrtInput) {
        hiddenSrtInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length > 0) {
                for (const file of files) {
                    const text = await file.text();
                    const subs = parseSrtContent(text);
                    assignSrtToBatchItem(file.name, file.path || file.name, subs);
                }
                renderBatchTable();
                saveBatchItemsToStorage();
                showToast(`Đã nạp ${files.length} file SRT vào danh sách!`, 'success');
            }
            hiddenSrtInput.value = '';
        });
    }

    // 3. Tự động khớp Video & SRT theo tên
    const btnAutoPair = document.getElementById('btnBatchAutoPair');
    if (btnAutoPair) {
        btnAutoPair.addEventListener('click', () => {
            autoPairVideosAndSrts();
        });
    }

    // 4. Dọn video đã xong
    const btnClearCompleted = document.getElementById('btnBatchClearCompleted');
    if (btnClearCompleted) {
        btnClearCompleted.addEventListener('click', () => {
            const beforeCount = batchEditorItems.length;
            batchEditorItems = batchEditorItems.filter(item => item.status !== 'completed');
            const removed = beforeCount - batchEditorItems.length;
            if (removed > 0) {
                renderBatchTable();
                saveBatchItemsToStorage();
                showToast(`Đã dọn dẹp ${removed} video đã hoàn thành!`, 'info');
            } else {
                showToast('Chưa có video nào hoàn thành để dọn dẹp.', 'info');
            }
        });
    }

    // 5. Xóa tất cả
    const btnClearAll = document.getElementById('btnBatchClearAll');
    if (btnClearAll) {
        btnClearAll.addEventListener('click', async () => {
            if (batchEditorItems.length === 0) return;
            const ok = await showConfirmModal(
                'Xác nhận xóa danh sách hàng loạt',
                `Bạn có chắc chắn muốn xóa toàn bộ ${batchEditorItems.length} video trong danh sách biên tập hàng loạt?`
            );
            if (ok) {
                batchEditorItems = [];
                renderBatchTable();
                saveBatchItemsToStorage();
                showToast('Đã xóa toàn bộ danh sách hàng loạt.', 'info');
            }
        });
    }

    // 6. Quét OCR hàng loạt ngoài bảng
    const btnScanOcr = document.getElementById('btnBatchScanOcr');
    if (btnScanOcr) {
        btnScanOcr.addEventListener('click', startBatchOcrScan);
    }

    // 7. Dịch & Làm sạch hàng loạt ngoài bảng
    const btnTranslateClean = document.getElementById('btnBatchTranslateClean');
    if (btnTranslateClean) {
        btnTranslateClean.addEventListener('click', startBatchTranslateAndClean);
    }

    // 8. Tự động toàn trình (Treo máy qua đêm)
    const btnAutoAllInOne = document.getElementById('btnBatchAutoAllInOne');
    if (btnAutoAllInOne) {
        btnAutoAllInOne.addEventListener('click', startBatchAllInOnePipeline);
    }

    // 9. Dừng tác vụ hàng loạt
    const btnStopTask = document.getElementById('btnBatchStopTask');
    if (btnStopTask) {
        btnStopTask.addEventListener('click', stopCurrentBatchTask);
    }

    // Drag & Drop vào khu vực bảng
    const dropZone = document.getElementById('batchEditorTableContainer');
    const dragOverlay = document.getElementById('batchDragOverlay');
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(name => {
            dropZone.addEventListener(name, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('drag-over');
                if (dragOverlay) dragOverlay.style.display = 'flex';
            });
        });
        ['dragleave', 'drop'].forEach(name => {
            dropZone.addEventListener(name, (e) => {
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
            const srtFiles = [];
            let hasMissingPath = false;

            for (const f of files) {
                const name = f.name.toLowerCase();
                if (name.match(/\.(mp4|mkv|mov|avi|webm|flv|m4v)$/)) {
                    if (f.path) {
                        videoPaths.push(f.path);
                    } else {
                        // Thử phân giải đường dẫn tuyệt đối qua API
                        let resolved = null;
                        try {
                            const res = await fetch(`/api/resolve_media_path?path=${encodeURIComponent(f.name)}`);
                            if (res.ok) {
                                const d = await res.json();
                                if (d.success && d.resolved_path) resolved = d.resolved_path;
                            }
                        } catch (err) {}
                        if (resolved && (resolved.includes('/') || resolved.includes('\\'))) {
                            videoPaths.push(resolved);
                        } else {
                            hasMissingPath = true;
                        }
                    }
                } else if (name.match(/\.(srt|vtt|ass)$/)) {
                    srtFiles.push(f);
                }
            }

            if (videoPaths.length > 0) {
                await addVideosToBatch(videoPaths);
            }

            if (hasMissingPath && videoPaths.length === 0) {
                showToast('⚠️ Trình duyệt bảo mật chặn đường dẫn thư mục gốc khi kéo thả. Vui lòng chọn video qua hộp thoại chuẩn để lấy đúng 100% đường dẫn!', 'warning', 5000);
                setTimeout(() => {
                    document.getElementById('btnBatchAddVideos')?.click();
                }, 400);
            }

            if (srtFiles.length > 0) {
                for (const sf of srtFiles) {
                    const text = await sf.text();
                    const subs = parseSrtContent(text);
                    assignSrtToBatchItem(sf.name, sf.path || sf.name, subs);
                }
                renderBatchTable();
                saveBatchItemsToStorage();
                showToast(`Đã nạp ${srtFiles.length} file phụ đề SRT vào danh sách!`, 'success');
            }
        });
    }
}

/**
 * Thêm danh sách video đường dẫn vào hàng đợi
 */
export async function addVideosToBatch(paths) {
    let addedCount = 0;
    for (const p of paths) {
        if (!p) continue;
        const normPath = p.replace(/\\/g, '/');
        const filename = normPath.split('/').pop();
        
        // Kiểm tra trùng
        const exists = batchEditorItems.some(item => item.videoPath === normPath);
        if (!exists) {
            batchEditorItems.push({
                id: 'batch_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
                videoPath: normPath,
                videoName: filename,
                srtPath: '',
                srtName: '',
                subtitles: [],
                ocrRegion: { x: 20, y: 81.5, w: 60, h: 9.5, width: 60, height: 9.5 },
                selected: true,
                status: 'pending', // 'pending' | 'ready' | 'processing' | 'completed' | 'error'
                progress: 0,
                outputPath: '',
                errorMsg: ''
            });
            addedCount++;
        }
    }

    if (addedCount > 0) {
        // Tự động kiểm tra file SRT cùng thư mục hoặc cùng tên
        autoCheckLocalSrtsForNewVideos();
        renderBatchTable();
        saveBatchItemsToStorage();
        showToast(`Đã thêm ${addedCount} video vào danh sách hàng loạt!`, 'success');
    } else {
        showToast('Các video đã có sẵn trong danh sách.', 'info');
    }
}

/**
 * Thêm các file SRT vào danh sách và tự động bắt cặp
 */
async function addSrtsToBatch(paths) {
    let matchedCount = 0;
    for (const p of paths) {
        if (!p) continue;
        const normPath = p.replace(/\\/g, '/');
        const filename = normPath.split('/').pop();
        
        // Thử fetch nội dung file srt qua API nếu có
        let subs = [];
        try {
            const res = await fetch(`/api/read_srt?path=${encodeURIComponent(normPath)}`);
            if (res.ok) {
                const data = await res.json();
                if (data.subtitles) subs = data.subtitles;
            }
        } catch(e) {}

        const matched = assignSrtToBatchItem(filename, normPath, subs);
        if (matched) matchedCount++;
    }

    renderBatchTable();
    saveBatchItemsToStorage();
    if (matchedCount > 0) {
        showToast(`Đã tự động ghép ${matchedCount} file SRT với các video tương ứng!`, 'success');
    } else {
        showToast(`Đã nạp ${paths.length} file SRT. Hãy bấm nút "Gán SRT" trên từng video nếu chưa tự động khớp.`, 'info');
    }
}

/**
 * Gán 1 SRT vào video thích hợp dựa trên tên tương đồng
 */
function assignSrtToBatchItem(srtFilename, srtPath, subtitles = []) {
    const cleanSrtName = srtFilename.replace(/\.(srt|vtt|ass)$/i, '').trim().toLowerCase();
    
    // Tìm video có tên gần giống nhất
    let bestMatchItem = null;
    let bestScore = -1;

    for (const item of batchEditorItems) {
        const cleanVidName = item.videoName.replace(/\.(mp4|mkv|mov|avi|webm|flv|m4v)$/i, '').trim().toLowerCase();
        if (cleanVidName === cleanSrtName) {
            bestMatchItem = item;
            break;
        }
        if (cleanVidName.includes(cleanSrtName) || cleanSrtName.includes(cleanVidName)) {
            bestMatchItem = item;
            break;
        }
    }

    if (bestMatchItem) {
        bestMatchItem.srtPath = srtPath;
        bestMatchItem.srtName = srtFilename;
        if (subtitles && subtitles.length > 0) {
            bestMatchItem.subtitles = subtitles;
        }
        bestMatchItem.status = 'ready';
        return true;
    }

    // Nếu không tìm được video khớp tên, thử gán cho video đầu tiên chưa có SRT
    const firstUnassigned = batchEditorItems.find(item => !item.srtPath);
    if (firstUnassigned) {
        firstUnassigned.srtPath = srtPath;
        firstUnassigned.srtName = srtFilename;
        if (subtitles && subtitles.length > 0) {
            firstUnassigned.subtitles = subtitles;
        }
        firstUnassigned.status = 'ready';
        return true;
    }

    return false;
}

/**
 * Tự động kiểm tra file .srt cùng thư mục và cùng tên với video
 */
async function autoCheckLocalSrtsForNewVideos() {
    for (const item of batchEditorItems) {
        if (item.srtPath) continue;
        const srtGuessPath = item.videoPath.replace(/\.[^/.]+$/, '.srt');
        try {
            const checkRes = await fetch('/api/editor/check_cache', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_video: item.videoPath })
            });
            if (checkRes.ok) {
                const data = await checkRes.json();
                const foundSrt = data.details?.cached_srt || data.details?.video_srt;
                if (foundSrt) {
                    item.srtPath = foundSrt.replace(/\\/g, '/');
                    item.srtName = item.srtPath.split('/').pop();
                    item.status = 'ready';
                }
            }
        } catch (e) {}
    }
    renderBatchTable();
}

/**
 * Tự động ghép nối video & srt theo tên tệp
 */
function autoPairVideosAndSrts() {
    let paired = 0;
    batchEditorItems.forEach(item => {
        if (!item.srtPath) {
            const cleanVidName = item.videoName.replace(/\.[^/.]+$/, '').toLowerCase();
            const srtGuess = item.videoPath.replace(/\.[^/.]+$/, '.srt');
            item.srtPath = srtGuess;
            item.srtName = item.videoName.replace(/\.[^/.]+$/, '.srt');
            item.status = 'ready';
            paired++;
        }
    });
    renderBatchTable();
    saveBatchItemsToStorage();
    showToast(`Đã thiết lập đường dẫn SRT tương ứng cho ${paired} video!`, 'success');
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. BẢNG DANH SÁCH HÀNG LOẠT (TABLE RENDERING)
// ─────────────────────────────────────────────────────────────────────────────

function setupBatchTableEvents() {
    const selectAllCheckbox = document.getElementById('batchSelectAll');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            const checked = e.target.checked;
            batchEditorItems.forEach(item => { item.selected = checked; });
            renderBatchTable();
        });
    }
}

/**
 * Render bảng danh sách video và cập nhật các chỉ số KPI
 */
export function renderBatchTable() {
    const tbody = document.getElementById('batchTableBody');
    const emptyZone = document.getElementById('batchEmptyZone');
    const selectAllCheckbox = document.getElementById('batchSelectAll');

    // Cập nhật các chỉ số thống kê
    const total = batchEditorItems.length;
    const withSrt = batchEditorItems.filter(i => !!i.srtPath).length;
    const noSrt = total - withSrt;
    const completed = batchEditorItems.filter(i => i.status === 'completed').length;
    const failed = batchEditorItems.filter(i => i.status === 'error').length;

    const elTotal = document.getElementById('batchKpiTotal');
    const elWithSrt = document.getElementById('batchKpiWithSrt');
    const elNoSrt = document.getElementById('batchKpiNoSrt');
    const elCompleted = document.getElementById('batchKpiCompleted');
    const elFailed = document.getElementById('batchKpiFailed');

    if (elTotal) elTotal.textContent = total;
    if (elWithSrt) elWithSrt.textContent = withSrt;
    if (elNoSrt) elNoSrt.textContent = noSrt;
    if (elCompleted) elCompleted.textContent = completed;
    if (elFailed) elFailed.textContent = failed;

    if (!tbody) return;

    if (total === 0) {
        tbody.innerHTML = '';
        if (emptyZone) emptyZone.style.display = 'flex';
        if (selectAllCheckbox) selectAllCheckbox.checked = false;
        return;
    }

    if (emptyZone) emptyZone.style.display = 'none';

    // Kiểm tra select all
    const allSelected = total > 0 && batchEditorItems.every(i => i.selected);
    if (selectAllCheckbox) selectAllCheckbox.checked = allSelected;

    let html = '';
    batchEditorItems.forEach((item, index) => {
        const isRunningThis = (currentBatchItemIndex === index && isBatchRunning);
        
        // Trạng thái badge
        let statusBadge = '';
        if (item.status === 'completed') {
            statusBadge = `<span class="batch-badge badge-success">✅ Hoàn thành</span>`;
        } else if (item.status === 'processing') {
            statusBadge = `
                <div class="batch-status-progress">
                    <span class="batch-badge badge-processing">⚙️ Đang xử lý (${item.progress || 0}%)</span>
                    <div class="mini-progress-bar"><div class="mini-progress-fill" style="width: ${item.progress || 0}%"></div></div>
                </div>
            `;
        } else if (item.status === 'error') {
            statusBadge = `<span class="batch-badge badge-danger" title="${escapeHtml(item.errorMsg || 'Lỗi xử lý')}">❌ Thất bại</span>`;
        } else if (item.status === 'translated') {
            statusBadge = `<span class="batch-badge badge-success" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);">✅ Đã dịch & làm sạch</span>`;
        } else if (item.status === 'ocr_done') {
            statusBadge = `<span class="batch-badge badge-ready" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8;">📄 Đã quét OCR</span>`;
        } else if (item.srtPath) {
            statusBadge = `<span class="batch-badge badge-ready">⚡ Sẵn sàng</span>`;
        } else {
            statusBadge = `<span class="batch-badge badge-pending">⏳ Chưa có SRT</span>`;
        }

        // Cột SRT
        let srtCell = '';
        if (item.srtPath) {
            const srtCountText = (item.subtitles && item.subtitles.length > 0) ? ` (${item.subtitles.length} câu)` : '';
            srtCell = `
                <div class="batch-srt-info" title="${escapeHtml(item.srtPath)}">
                    <span class="batch-srt-icon">📄</span>
                    <span class="batch-srt-name">${escapeHtml(item.srtName || item.srtPath.split('/').pop())}${srtCountText}</span>
                    <button type="button" class="btn-icon-link btn-change-srt" data-index="${index}" title="Đổi file SRT khác">Đổi</button>
                </div>
            `;
        } else {
            srtCell = `
                <div class="batch-srt-missing">
                    <span style="color: #fbbf24; font-size: 11px;">⚠️ Chưa có SRT</span>
                    <button type="button" class="btn secondary small btn-assign-srt-single" data-index="${index}" style="padding: 2px 6px; font-size: 10.5px;">+ Gán SRT</button>
                </div>
            `;
        }

        html += `
            <tr class="batch-row ${item.selected ? 'selected' : ''} ${isRunningThis ? 'running' : ''}" data-index="${index}">
                <td style="text-align: center;">
                    <input type="checkbox" class="batch-item-checkbox custom-checkbox-circle" data-index="${index}" ${item.selected ? 'checked' : ''}>
                </td>
                <td style="text-align: center; color: #94a3b8; font-size: 12px; font-family: monospace;">${index + 1}</td>
                <td>
                    <div class="batch-video-title-wrap" title="${escapeHtml(item.videoPath)}">
                        <span class="batch-video-icon">🎬</span>
                        <div class="batch-video-names">
                            <span class="batch-video-name">${escapeHtml(item.videoName)}</span>
                            <span class="batch-video-path">${escapeHtml(item.videoPath)}</span>
                        </div>
                    </div>
                </td>
                <td>${srtCell}</td>
                <td>${statusBadge}</td>
                <td style="text-align: center;">
                    <div class="batch-action-btns">
                        <button type="button" class="btn secondary small btn-edit-item" data-index="${index}" title="Mở Popup xem video, vẽ vùng OCR, chỉnh sửa SRT chi tiết">
                            ✏️ Sửa
                        </button>
                        <button type="button" class="btn secondary small btn-open-item-folder" data-index="${index}" title="${item.outputPath ? 'Mở thư mục chứa video thành phẩm trong File Explorer' : 'Mở thư mục chứa video này trong File Explorer'}">
                            📁
                        </button>
                        <button type="button" class="btn-icon-danger btn-delete-item" data-index="${index}" title="Xóa video khỏi danh sách">
                            🗑️
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;

    // Gắn sự kiện checkbox dòng
    tbody.querySelectorAll('.batch-item-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const idx = parseInt(e.target.getAttribute('data-index'));
            if (batchEditorItems[idx]) {
                batchEditorItems[idx].selected = e.target.checked;
                renderBatchTable();
            }
        });
    });

    // Gắn sự kiện nút Sửa -> Mở Modal Chi Tiết
    tbody.querySelectorAll('.btn-edit-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.getAttribute('data-index'));
            openBatchDetailModal(idx);
        });
    });

    // Gắn sự kiện nút Xóa dòng
    tbody.querySelectorAll('.btn-delete-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.getAttribute('data-index'));
            batchEditorItems.splice(idx, 1);
            renderBatchTable();
            saveBatchItemsToStorage();
        });
    });

    // Gắn sự kiện gán/đổi SRT đơn lẻ
    tbody.querySelectorAll('.btn-change-srt, .btn-assign-srt-single').forEach(btn => {
        btn.addEventListener('click', async () => {
            const idx = parseInt(btn.getAttribute('data-index'));
            const srtPath = await selectSingleFile('srt', 'Chọn file SRT cho video ' + batchEditorItems[idx]?.videoName);
            if (srtPath) {
                const normPath = srtPath.replace(/\\/g, '/');
                batchEditorItems[idx].srtPath = normPath;
                batchEditorItems[idx].srtName = normPath.split('/').pop();
                batchEditorItems[idx].status = 'ready';
                
                // Đọc thử subs
                try {
                    const res = await fetch(`/api/read_srt?path=${encodeURIComponent(normPath)}`);
                    if (res.ok) {
                        const data = await res.json();
                        if (data.subtitles) batchEditorItems[idx].subtitles = data.subtitles;
                    }
                } catch(e) {}

                renderBatchTable();
                saveBatchItemsToStorage();
                showToast(`Đã gán file phụ đề cho ${batchEditorItems[idx].videoName}!`, 'success');
            }
        });
    });

    // Gắn sự kiện mở folder video (cả video thành phẩm hoặc video gốc)
    tbody.querySelectorAll('.btn-open-item-folder').forEach(btn => {
        btn.addEventListener('click', async () => {
            const idx = parseInt(btn.getAttribute('data-index'));
            const item = batchEditorItems[idx];
            if (!item) return;

            const target = (item.outputPath && item.outputPath.trim()) ? item.outputPath.trim() : (item.videoPath || '');
            try {
                const res = await fetch('/api/open_folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        path: target,
                        video_path: item.videoPath || ''
                    })
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data.success) {
                    showToast('Đã mở thư mục trong File Explorer!', 'info');
                } else {
                    showToast(data.error || 'Không thể mở thư mục này!', 'error');
                }
            } catch (err) {
                showToast(`Lỗi mở thư mục: ${err.message}`, 'error');
            }
        });
    });
}

/**
 * Hộp thoại chọn 1 file
 */
async function selectSingleFile(type, title) {
    if (typeof window.selectFile === 'function') {
        return await window.selectFile(type, title);
    }
    try {
        const res = await fetch('/api/select_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, title })
        });
        const data = await res.json();
        if (data.success && (data.file_path || data.path || data.file)) {
            return data.file_path || data.path || data.file;
        }
    } catch(e) {}
    return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. POPUP MODAL CHỈNH SỬA CHI TIẾT VIDEO & OCR / SRT (BÊ NGUYÊN GIAO DIỆN & CHỨC NĂNG BIÊN TẬP PHIM)
// ─────────────────────────────────────────────────────────────────────────────

function setupBatchModalDetailEvents() {
    const btnClose = document.getElementById('btnBatchModalClose');
    const btnCancel = document.getElementById('btnBatchModalCancel');
    const btnSave = document.getElementById('btnBatchModalSave');
    const btnSaveOcrOnly = document.getElementById('btnBatchModalSaveOcrOnly');
    const btnApplyOcrToAll = document.getElementById('btnBatchModalApplyOcrToAll');

    const btnToggleLog = document.getElementById('btnBatchModalToggleLog');

    if (btnClose) btnClose.addEventListener('click', closeBatchDetailModal);
    if (btnCancel) btnCancel.addEventListener('click', closeBatchDetailModal);
    if (btnSave) btnSave.addEventListener('click', saveBatchDetailModal);
    if (btnSaveOcrOnly) btnSaveOcrOnly.addEventListener('click', saveBatchOcrRegionOnly);
    if (btnApplyOcrToAll) btnApplyOcrToAll.addEventListener('click', applyBatchOcrRegionToAll);
    if (btnToggleLog) {
        btnToggleLog.addEventListener('click', () => {
            const toggleTerminalBtn = document.getElementById('toggleTerminalBtn');
            if (toggleTerminalBtn) toggleTerminalBtn.click();
        });
    }
}

/**
 * Lấy vùng OCR hiện tại từ trình biên tập và chuẩn hóa đầy đủ tọa độ
 */
function getCurrentNormalizedEditorRegion() {
    let region = { x: 20, y: 81.5, w: 60, h: 9.5, width: 60, height: 9.5 };
    if (typeof window.getEditorOcrRegion === 'function') {
        const r = window.getEditorOcrRegion();
        if (r && typeof r === 'object') {
            const w = Number(r.w ?? r.width ?? 60);
            const h = Number(r.h ?? r.height ?? 9.5);
            const x = Number(r.x ?? 20);
            const y = Number(r.y ?? 81.5);
            region = { x, y, w, h, width: w, height: h };
        }
    }
    return region;
}

/**
 * Lưu riêng vùng quét OCR từ modal sửa cho video hiện tại
 */
function saveBatchOcrRegionOnly() {
    if (activeModalItemIndex < 0 || !batchEditorItems[activeModalItemIndex]) {
        closeBatchDetailModal();
        return;
    }
    const item = batchEditorItems[activeModalItemIndex];
    item.ocrRegion = getCurrentNormalizedEditorRegion();
    saveBatchItemsToStorage();
    renderBatchTable();
    showToast(`🎯 Đã lưu vùng quét OCR cho "${item.videoName}"! Giờ đây bạn có thể dùng nút Quét OCR Hàng Loạt ngoài bảng.`, 'success');
    closeBatchDetailModal();
}

/**
 * Áp dụng vùng quét OCR hiện tại cho toàn bộ video trong danh sách hàng loạt
 */
function applyBatchOcrRegionToAll() {
    if (batchEditorItems.length === 0) {
        closeBatchDetailModal();
        return;
    }
    const region = getCurrentNormalizedEditorRegion();
    batchEditorItems.forEach(item => {
        item.ocrRegion = JSON.parse(JSON.stringify(region));
    });
    saveBatchItemsToStorage();
    renderBatchTable();
    showToast(`🌐 Đã áp dụng vùng quét OCR này cho toàn bộ ${batchEditorItems.length} video trong danh sách!`, 'success');
    closeBatchDetailModal();
}

let modalOriginalEditorSnapshot = null;

/**
 * Mở Popup chỉnh sửa chi tiết video và phụ đề (Bê nguyên 100% giao diện & tính năng Biên Tập Phim)
 */
export async function openBatchDetailModal(index) {
    if (!batchEditorItems[index]) return;
    activeModalItemIndex = index;
    const item = batchEditorItems[index];

    const modal = document.getElementById('batchItemDetailModal');
    const titleEl = document.getElementById('batchModalVideoTitle');
    if (titleEl) titleEl.textContent = item.videoName;

    // 0. Lưu lại trạng thái editor hiện tại trước khi can thiệp
    if (typeof window.snapshotEditorState === 'function') {
        modalOriginalEditorSnapshot = window.snapshotEditorState();
    }

    // 1. Di chuyển phần tử DOM .top-row từ viewEditor sang batchModalTopRowSlot
    const topRow = document.querySelector('#viewEditor .top-row') || document.querySelector('#batchModalTopRowSlot .top-row');
    const slot = document.getElementById('batchModalTopRowSlot');
    if (topRow && slot && topRow.parentElement !== slot) {
        slot.appendChild(topRow);
    }

    // 1.1 Tự động phân giải đường dẫn video nếu item chỉ có tên file tương đối
    if (item.videoPath && (!item.videoPath.includes('/') && !item.videoPath.includes('\\'))) {
        try {
            const res = await fetch(`/api/resolve_media_path?path=${encodeURIComponent(item.videoPath)}`);
            if (res.ok) {
                const d = await res.json();
                if (d.success && d.resolved_path) {
                    item.videoPath = d.resolved_path.replace(/\\/g, '/');
                    item.videoName = item.videoPath.split('/').pop();
                    saveBatchItemsToStorage();
                    renderBatchTable();
                    if (titleEl) titleEl.textContent = item.videoName;
                }
            }
        } catch (e) {
            console.warn("Lỗi tự động phân giải đường dẫn video:", e);
        }
    }

    // 2. Nạp Video và Phụ đề vào Editor gốc của ứng dụng
    if (typeof window.loadVideoToEditor === 'function') {
        await window.loadVideoToEditor(item.videoPath, item.srtPath);
    }

    // 3. Khôi phục vùng OCR đã lưu của video này (nếu có)
    if (item.ocrRegion && typeof window.setEditorOcrRegion === 'function') {
        window.setEditorOcrRegion(item.ocrRegion);
    }

    // 4. Hiển thị modal
    if (modal) {
        modal.style.display = 'flex';
        modal.focus();
    }
}

/**
 * Cập nhật đường dẫn video của item đang mở trong modal nếu người dùng bấm nút Chọn File
 */
window.updateActiveBatchItemVideoPath = function(newPath) {
    if (activeModalItemIndex >= 0 && batchEditorItems[activeModalItemIndex]) {
        const norm = newPath.replace(/\\/g, '/');
        batchEditorItems[activeModalItemIndex].videoPath = norm;
        batchEditorItems[activeModalItemIndex].videoName = norm.split('/').pop();
        saveBatchItemsToStorage();
        renderBatchTable();
        const titleEl = document.getElementById('batchModalVideoTitle');
        if (titleEl) titleEl.textContent = batchEditorItems[activeModalItemIndex].videoName;
        const ocrFilenameEl = document.getElementById('ocrRegionFilename');
        if (ocrFilenameEl) ocrFilenameEl.textContent = batchEditorItems[activeModalItemIndex].videoName;
    }
};

/**
 * Đóng modal chi tiết và hoàn trả .top-row về lại tab Biên Tập Phim
 */
function closeBatchDetailModal() {
    if (typeof window.returnTopRowToEditor === 'function') {
        window.returnTopRowToEditor();
    } else {
        const topRow = document.querySelector('#batchModalTopRowSlot .top-row');
        const viewEditorLayout = document.querySelector('#viewEditor .main-layout');
        const bottomRow = viewEditorLayout ? viewEditorLayout.querySelector('.bottom-row') : null;
        if (topRow && viewEditorLayout) {
            if (bottomRow) {
                viewEditorLayout.insertBefore(topRow, bottomRow);
            } else {
                viewEditorLayout.appendChild(topRow);
            }
        }
        const modal = document.getElementById('batchItemDetailModal');
        if (modal) modal.style.display = 'none';
    }

    // Tạm dừng phát video
    const vp = document.getElementById('videoPlayer');
    if (vp && !vp.paused) vp.pause();

    // Khôi phục lại trạng thái cũ của Editor trước khi mở modal
    if (modalOriginalEditorSnapshot && typeof window.restoreEditorState === 'function') {
        window.restoreEditorState(modalOriginalEditorSnapshot);
        modalOriginalEditorSnapshot = null;
    }

    activeModalItemIndex = -1;
}

/**
 * Lưu các thay đổi từ modal vào item trong hàng đợi
 */
async function saveBatchDetailModal() {
    if (activeModalItemIndex < 0 || !batchEditorItems[activeModalItemIndex]) {
        closeBatchDetailModal();
        return;
    }

    const item = batchEditorItems[activeModalItemIndex];
    
    // Cập nhật đường dẫn video nếu người dùng đã chọn lại file trong modal
    const inputEl = document.getElementById('editorInputVideoPath');
    if (inputEl && inputEl.value) {
        const curPath = inputEl.value.trim().replace(/\\/g, '/');
        if (curPath) {
            item.videoPath = curPath;
            item.videoName = curPath.split('/').pop();
        }
    }

    // Lưu tọa độ vùng quét OCR nếu người dùng đã vẽ/chỉnh sửa
    if (typeof window.getEditorOcrRegion === 'function') {
        item.ocrRegion = window.getEditorOcrRegion();
    }

    const currentSubs = (typeof window.getEditorSrtData === 'function') ? window.getEditorSrtData() : [];

    if (currentSubs && currentSubs.length > 0) {
        item.subtitles = JSON.parse(JSON.stringify(currentSubs));
        
        // Luôn lưu file SRT vào cùng vị trí của video hoặc SRT gốc
        const targetDestSrt = item.srtPath || item.videoPath.replace(/\.[^/.]+$/, '.srt');
        try {
            const expRes = await fetch('/api/subtitles/export_temp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: item.videoPath,
                    target_srt_path: targetDestSrt,
                    replace_original: true,
                    subtitles: currentSubs
                })
            });
            if (expRes.ok) {
                const expData = await expRes.json();
                if (expData.success && expData.srt_path) {
                    item.srtPath = expData.srt_path.replace(/\\/g, '/');
                    item.srtName = item.srtPath.split('/').pop();
                }
            }
        } catch (e) {
            console.warn("Lỗi auto export SRT:", e);
        }

        if (!item.srtPath) {
            item.srtPath = targetDestSrt;
            item.srtName = targetDestSrt.split(/[\\/]/).pop();
        }
        item.status = 'ready';
    }

    closeBatchDetailModal();
    renderBatchTable();
    saveBatchItemsToStorage();
    showToast(`Đã lưu & cập nhật phụ đề cho "${item.videoName}" vào danh sách!`, 'success');
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. BỘ CÀI ĐẶT CHUNG ÁP DỤNG HÀNG LOẠT (GLOBAL PRESETS)
// ─────────────────────────────────────────────────────────────────────────────

function setupBatchGlobalPresetEvents() {
    // 1. Voice Modal Handler
    const btnOpenVoice = document.getElementById('btnBatchOpenVoiceModalDubbing');
    if (btnOpenVoice) {
        btnOpenVoice.addEventListener('click', (e) => {
            if (e.target.closest('.btn-preview-voice')) return;
            if (typeof window.openVoiceLibraryModal === 'function') {
                window.openVoiceLibraryModal();
            }
        });
    }

    // 2. Speed Slider
    const speedSlider = document.getElementById('batch_dubbingSpeed');
    const speedVal = document.getElementById('batch_dubbingSpeedVal');
    if (speedSlider && speedVal) {
        speedSlider.addEventListener('input', () => {
            speedVal.textContent = parseFloat(speedSlider.value).toFixed(2) + 'x';
        });
    }

    // Voice Volume Slider
    const voiceVolSlider = document.getElementById('batch_dubbingVoiceVol');
    const voiceVolVal = document.getElementById('batch_dubbingVoiceVolVal');
    if (voiceVolSlider && voiceVolVal) {
        voiceVolSlider.addEventListener('input', () => {
            voiceVolVal.textContent = voiceVolSlider.value + '%';
        });
    }

    // Original Volume Slider
    const origVolSlider = document.getElementById('batch_dubbingOrigVol');
    const origVolVal = document.getElementById('batch_dubbingOrigVolVal');
    if (origVolSlider && origVolVal) {
        origVolSlider.addEventListener('input', () => {
            origVolVal.textContent = origVolSlider.value + '%';
        });
    }

    // Parallel Threads Slider
    const threadsSlider = document.getElementById('batch_dubbingThreads');
    const threadsVal = document.getElementById('batch_dubbingThreadsVal');
    if (threadsSlider && threadsVal) {
        threadsSlider.addEventListener('input', () => {
            threadsVal.textContent = threadsSlider.value + ' luồng';
        });
    }

    // Stem separation toggle -> show/hide mode selector
    const stemToggle = document.getElementById('batch_editorStemSeparationEnabled');
    const stemGroup = document.getElementById('batch_stemModeGroup');
    if (stemToggle && stemGroup) {
        stemToggle.addEventListener('change', () => {
            stemGroup.style.display = stemToggle.checked ? 'block' : 'none';
        });
    }

    // 3. Subtitle Presets
    document.querySelectorAll('.batch-preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const preset = btn.getAttribute('data-preset');
            applyBatchSubtitlePreset(preset);
        });
    });

    // Subtitle size slider
    const subSizeSlider = document.getElementById('batch_subSize');
    const subSizeVal = document.getElementById('batch_subSizeVal');
    if (subSizeSlider && subSizeVal) {
        subSizeSlider.addEventListener('input', () => {
            subSizeVal.textContent = subSizeSlider.value + 'px';
            updateBatchSubLivePreview();
        });
    }

    // Subtitle outline slider
    const subOutlineSlider = document.getElementById('batch_subOutline');
    const subOutlineVal = document.getElementById('batch_subOutlineVal');
    if (subOutlineSlider && subOutlineVal) {
        subOutlineSlider.addEventListener('input', () => {
            subOutlineVal.textContent = subOutlineSlider.value + 'px';
            updateBatchSubLivePreview();
        });
    }

    // Color Pickers & Text Inputs Sync
    const subColorPicker = document.getElementById('batch_subColorPicker');
    const subColorText = document.getElementById('batch_subColorText');
    if (subColorPicker && subColorText) {
        subColorPicker.addEventListener('input', () => {
            subColorText.value = subColorPicker.value;
            updateBatchSubLivePreview();
        });
        subColorText.addEventListener('input', () => {
            if (/^#[0-9A-Fa-f]{6}$/.test(subColorText.value)) {
                subColorPicker.value = subColorText.value;
                updateBatchSubLivePreview();
            }
        });
    }

    const subOutlinePicker = document.getElementById('batch_subOutlineColorPicker');
    const subOutlineText = document.getElementById('batch_subOutlineColorText');
    if (subOutlinePicker && subOutlineText) {
        subOutlinePicker.addEventListener('input', () => {
            subOutlineText.value = subOutlinePicker.value;
            updateBatchSubLivePreview();
        });
        subOutlineText.addEventListener('input', () => {
            if (/^#[0-9A-Fa-f]{6}$/.test(subOutlineText.value)) {
                subOutlinePicker.value = subOutlineText.value;
                updateBatchSubLivePreview();
            }
        });
    }

    // Font changes -> update preview box
    const fontSelect = document.getElementById('batch_subFont');
    if (fontSelect) {
        fontSelect.addEventListener('change', updateBatchSubLivePreview);
    }

    // 5. Video Editor Speed Slider
    const vidSpeedSlider = document.getElementById('batch_editToolSpeedSlider');
    const vidSpeedVal = document.getElementById('batch_editToolSpeedVal');
    if (vidSpeedSlider && vidSpeedVal) {
        vidSpeedSlider.addEventListener('input', () => {
            vidSpeedVal.textContent = parseFloat(vidSpeedSlider.value).toFixed(2) + 'x';
        });
    }

    // Auto Delogo toggle
    const delogoToggle = document.getElementById('batch_enableAutoDelogo');
    const delogoOptions = document.getElementById('batch_delogoOptions');
    if (delogoToggle && delogoOptions) {
        delogoToggle.addEventListener('change', () => {
            delogoOptions.style.display = delogoToggle.checked ? 'grid' : 'none';
        });
    }

    // Logo Watermark toggle & selection
    const logoToggle = document.getElementById('batch_enableLogoWatermark');
    const logoOptions = document.getElementById('batch_watermarkOptions');
    if (logoToggle && logoOptions) {
        logoToggle.addEventListener('change', () => {
            logoOptions.style.display = logoToggle.checked ? 'block' : 'none';
        });
    }

    const btnSelectLogo = document.getElementById('btnBatchSelectLogo');
    if (btnSelectLogo) {
        btnSelectLogo.addEventListener('click', async () => {
            if (typeof window.selectFile === 'function') {
                const chosen = await window.selectFile('image', 'Chọn ảnh logo đóng dấu watermark');
                if (chosen) {
                    const logoInput = document.getElementById('batch_logoInputPath');
                    if (logoInput) logoInput.value = chosen;
                    showToast(`Đã chọn logo: ${chosen}`, 'success');
                }
            }
        });
    }

    const logoOpacitySlider = document.getElementById('batch_logoOpacity');
    const logoOpacityVal = document.getElementById('batch_logoOpacityVal');
    if (logoOpacitySlider && logoOpacityVal) {
        logoOpacitySlider.addEventListener('input', () => {
            logoOpacityVal.textContent = logoOpacitySlider.value + '%';
        });
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 4.1 BATCH MULTI-REGION BLUR & DYNAMIC TEXT OVERLAY CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

function loadSavedBatchOverlayLayers() {
    try {
        const saved = localStorage.getItem(BATCH_OVERLAY_STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) {
                window.batchCustomOverlayLayers = parsed;
            }
        }
    } catch(e) {
        window.batchCustomOverlayLayers = [];
    }
}

function saveBatchOverlayLayers() {
    try {
        if (Array.isArray(window.batchCustomOverlayLayers)) {
            localStorage.setItem(BATCH_OVERLAY_STORAGE_KEY, JSON.stringify(window.batchCustomOverlayLayers));
        }
    } catch(e) {}
}

function setupBatchMultiOverlayLayers() {
    loadSavedBatchOverlayLayers();

    const btnAddBlur = document.getElementById('batch_btnAddBlurLayer');
    const btnAddText = document.getElementById('batch_btnAddTextLayer');
    const btnOpenCanvas = document.getElementById('batch_btnOpenOverlayPositionModal');
    const btnOpenCanvasFromHint = document.getElementById('batch_btnOpenOverlayPositionModalFromHint');

    if (btnAddBlur) {
        btnAddBlur.addEventListener('click', () => {
            if (!Array.isArray(window.batchCustomOverlayLayers)) window.batchCustomOverlayLayers = [];
            const newLayer = {
                id: 'batch_layer_' + Date.now(),
                type: 'blur',
                name: `Vùng mờ #${window.batchCustomOverlayLayers.filter(l => l.type === 'blur').length + 1}`,
                x_pct: 10,
                y_pct: 80,
                w_pct: 80,
                h_pct: 12,
                timing_mode: 'all',
                start_time: '00:00',
                end_time: '00:10',
                random_duration: 5,
                random_interval: 15,
                blur_type: 'boxblur',
                blur_intensity: 15,
                mask_color: '#000000',
                visible: true,
                isTimeValid: true
            };
            window.batchCustomOverlayLayers.push(newLayer);
            renderBatchLayersListUI();
            showToast('Đã thêm vùng làm mờ áp dụng cho tất cả video!', 'success');
        });
    }

    if (btnAddText) {
        btnAddText.addEventListener('click', () => {
            if (!Array.isArray(window.batchCustomOverlayLayers)) window.batchCustomOverlayLayers = [];
            const newLayer = {
                id: 'batch_layer_' + Date.now(),
                type: 'text',
                text: 'Nhập nội dung chữ...',
                x_pct: 20,
                y_pct: 20,
                w_pct: 60,
                h_pct: 8,
                font_size: 24,
                color: '#ffffff',
                timing_mode: 'all',
                start_time: '00:00',
                end_time: '00:10',
                random_duration: 5,
                random_interval: 15,
                animation: 'none',
                visible: true,
                isTimeValid: true
            };
            window.batchCustomOverlayLayers.push(newLayer);
            renderBatchLayersListUI();
            showToast('Đã thêm chữ chèn mới cho toàn bộ video!', 'success');
        });
    }

    const openCanvasModal = () => {
        if (typeof window.openOverlayPositionModal === 'function') {
            window.openOverlayPositionModal(null, 'batch_editor');
        } else {
            showToast('Khung Canvas đang được nạp, vui lòng thử lại sau giây lát!', 'info');
        }
    };

    if (btnOpenCanvas) btnOpenCanvas.addEventListener('click', openCanvasModal);
    if (btnOpenCanvasFromHint) btnOpenCanvasFromHint.addEventListener('click', openCanvasModal);

    window.renderBatchMultiOverlayLayersUI = renderBatchLayersListUI;
    renderBatchLayersListUI();
}

function renderBatchLayersListUI() {
    const layersList = document.getElementById('batch_overlayLayersList');
    const emptyHint = document.getElementById('batch_overlayLayersEmptyHint');
    if (!layersList) return;

    layersList.innerHTML = '';
    if (!Array.isArray(window.batchCustomOverlayLayers) || window.batchCustomOverlayLayers.length === 0) {
        if (emptyHint) emptyHint.style.display = 'flex';
        saveBatchOverlayLayers();
        return;
    }
    if (emptyHint) emptyHint.style.display = 'none';

    window.batchCustomOverlayLayers.forEach((layer, idx) => {
        const item = document.createElement('div');
        item.className = 'overlay-layer-item';
        item.dataset.id = layer.id;

        const isBlur = layer.type === 'blur';
        const badgeClass = isBlur ? 'badge-layer-blur' : 'badge-layer-text';
        const badgeText = isBlur ? '🌫️ VÙNG MỜ' : '🔤 CHỮ';
        const layerTitle = isBlur ? (layer.name || `Vùng mờ #${idx + 1}`) : (layer.text ? `"${layer.text.substring(0, 16)}${layer.text.length > 16 ? '...' : ''}"` : `Chữ #${idx + 1}`);

        item.innerHTML = `
            <div class="overlay-layer-header" style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; flex: 1; min-width: 0;">
                    <span class="overlay-layer-type-badge ${badgeClass}">${badgeText}</span>
                    <span style="font-size: 11px; font-weight: 600; color: #e2e8f0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 110px;">${escapeHtml(layerTitle)}</span>
                    <span class="layer-coords-badge batch-coords-badge" data-id="${layer.id}" style="font-size: 9.5px; font-family: monospace; color: #38bdf8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 4px; padding: 1px 5px; cursor: pointer; transition: all 0.15s ease;" title="Bấm để mở khung canvas chỉnh sửa vị trí">X:${layer.x_pct}% Y:${layer.y_pct}% W:${layer.w_pct}% H:${layer.h_pct}% 📐</span>
                </div>
                <div style="display: flex; align-items: center; gap: 3px; flex-shrink: 0;">
                    <button type="button" class="btn-batch-canvas-layer" data-id="${layer.id}" style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 4px; color: #38bdf8; cursor: pointer; font-size: 10px; padding: 2px 5px; font-weight: 500;" title="Mở Canvas chỉnh vị trí">📐 Chỉnh</button>
                    <button type="button" class="btn-batch-center-layer" data-id="${layer.id}" style="background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.35); border-radius: 4px; color: #cbd5e1; cursor: pointer; font-size: 10px; padding: 2px 5px;" title="Căn giữa màn hình ngang">🎯</button>
                    <button type="button" class="btn-batch-toggle-layer-vis" data-id="${layer.id}" style="background: none; border: none; cursor: pointer; font-size: 12px; color: ${layer.visible !== false ? '#38bdf8' : '#64748b'}; padding: 2px;" title="Ẩn/Hiện">${layer.visible !== false ? '👁️' : '🕶️'}</button>
                    <button type="button" class="btn-batch-delete-layer" data-id="${layer.id}" style="background: none; border: none; cursor: pointer; font-size: 11px; color: #ef4444; padding: 2px;" title="Xóa lớp">🗑️</button>
                </div>
            </div>

            <!-- Timing Settings -->
            <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(51, 65, 85, 0.5); display: flex; flex-direction: column; gap: 5px;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-size: 10.5px; color: #94a3b8;">Thời gian xuất hiện:</span>
                    <select class="batch-layer-timing-mode" data-id="${layer.id}" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10.5px;">
                        <option value="all" ${layer.timing_mode === 'all' ? 'selected' : ''}>Toàn bộ video</option>
                        <option value="custom" ${layer.timing_mode === 'custom' ? 'selected' : ''}>Tự điền mốc (mm:ss)</option>
                        <option value="random" ${layer.timing_mode === 'random' ? 'selected' : ''}>Ngẫu nhiên chu kỳ</option>
                    </select>
                </div>

                <!-- Custom Timing Inputs -->
                <div class="batch-layer-custom-timing-wrap" style="display: ${layer.timing_mode === 'custom' ? 'flex' : 'none'}; flex-direction: column; gap: 3px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span style="font-size: 10px; color: #94a3b8;">Từ:</span>
                        <input type="text" class="batch-layer-start-time text-input" data-id="${layer.id}" value="${layer.start_time || '00:00'}" placeholder="00:00" style="width: 58px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                        <span style="font-size: 10px; color: #94a3b8;">Đến:</span>
                        <input type="text" class="batch-layer-end-time text-input" data-id="${layer.id}" value="${layer.end_time || '00:10'}" placeholder="00:10" style="width: 58px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                    </div>
                </div>

                <!-- Random Timing Settings -->
                <div class="batch-layer-random-timing-wrap" style="display: ${layer.timing_mode === 'random' ? 'flex' : 'none'}; align-items: center; gap: 6px;">
                    <span style="font-size: 10px; color: #94a3b8;">Hiện</span>
                    <input type="number" class="batch-layer-random-duration text-input" data-id="${layer.id}" value="${layer.random_duration || 5}" min="1" max="60" style="width: 42px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                    <span style="font-size: 10px; color: #94a3b8;">giây mỗi</span>
                    <input type="number" class="batch-layer-random-interval text-input" data-id="${layer.id}" value="${layer.random_interval || 15}" min="5" max="300" style="width: 48px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                    <span style="font-size: 10px; color: #94a3b8;">giây</span>
                </div>

                <!-- Specific Type Controls -->
                ${isBlur ? `
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 4px;">
                        <span style="font-size: 10.5px; color: #94a3b8;">Kiểu che:</span>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            <select class="batch-layer-blur-type" data-id="${layer.id}" style="background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10.5px;">
                                <option value="boxblur" ${layer.blur_type === 'boxblur' ? 'selected' : ''}>Làm mờ (Blur)</option>
                                <option value="color" ${layer.blur_type === 'color' ? 'selected' : ''}>Khối màu đơn sắc</option>
                            </select>
                            <input type="color" class="batch-layer-mask-color" data-id="${layer.id}" value="${layer.mask_color || '#000000'}" style="width: 20px; height: 20px; border: none; border-radius: 3px; cursor: pointer; display: ${layer.blur_type === 'color' ? 'inline-block' : 'none'};">
                        </div>
                    </div>
                ` : `
                    <div style="display: flex; flex-direction: column; gap: 4px; margin-top: 4px;">
                        <div style="display: flex; gap: 4px;">
                            <input type="text" class="batch-layer-text-content text-input" data-id="${layer.id}" value="${escapeHtml(layer.text || '')}" placeholder="Nhập nội dung chữ..." style="flex: 1; padding: 3px 6px; font-size: 11px;">
                        </div>
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                            <span style="font-size: 10px; color: #94a3b8;">Hiệu ứng:</span>
                            <select class="batch-layer-text-anim" data-id="${layer.id}" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10px;">
                                <option value="none" ${layer.animation === 'none' ? 'selected' : ''}>Tĩnh (Không hiệu ứng)</option>
                                <option value="fade" ${layer.animation === 'fade' ? 'selected' : ''}>✨ Ẩn hiện (Fade In/Out)</option>
                                <option value="marquee" ${layer.animation === 'marquee' ? 'selected' : ''}>🏃 Bay nhảy (Marquee)</option>
                                <option value="pulse" ${layer.animation === 'pulse' ? 'selected' : ''}>💓 Nhấp nháy chu kỳ (Pulse)</option>
                            </select>
                            <input type="color" class="batch-layer-text-color" data-id="${layer.id}" value="${layer.color || '#ffffff'}" title="Màu chữ" style="width: 20px; height: 20px; border: none; border-radius: 3px; cursor: pointer;">
                        </div>
                    </div>
                `}
            </div>
        `;

        layersList.appendChild(item);
    });

    attachBatchLayerEvents();
    saveBatchOverlayLayers();
}

function attachBatchLayerEvents() {
    const layersList = document.getElementById('batch_overlayLayersList');
    if (!layersList) return;

    // Mở Canvas định vị cho layer cụ thể
    const openLayerCanvas = (id) => {
        if (typeof window.openOverlayPositionModal === 'function') {
            window.openOverlayPositionModal(id, 'batch_editor');
        }
    };

    layersList.querySelectorAll('.btn-batch-canvas-layer').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            openLayerCanvas(btn.dataset.id);
        };
    });

    layersList.querySelectorAll('.batch-coords-badge').forEach(badge => {
        badge.onclick = (e) => {
            e.stopPropagation();
            openLayerCanvas(badge.dataset.id);
        };
    });

    // Căn giữa ngang
    layersList.querySelectorAll('.btn-batch-center-layer').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            const layer = window.batchCustomOverlayLayers.find(l => l.id === id);
            if (layer) {
                layer.x_pct = Math.max(0, Math.round(((100 - layer.w_pct) / 2) * 10) / 10);
                renderBatchLayersListUI();
            }
        };
    });

    // Toggle ẩn / hiện
    layersList.querySelectorAll('.btn-batch-toggle-layer-vis').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            const layer = window.batchCustomOverlayLayers.find(l => l.id === id);
            if (layer) {
                layer.visible = (layer.visible === false);
                renderBatchLayersListUI();
            }
        };
    });

    // Xóa layer
    layersList.querySelectorAll('.btn-batch-delete-layer').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            window.batchCustomOverlayLayers = window.batchCustomOverlayLayers.filter(l => l.id !== id);
            renderBatchLayersListUI();
        };
    });

    // Timing mode change
    layersList.querySelectorAll('.batch-layer-timing-mode').forEach(sel => {
        sel.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === sel.dataset.id);
            if (layer) {
                layer.timing_mode = sel.value;
                renderBatchLayersListUI();
            }
        };
    });

    // Timing inputs
    layersList.querySelectorAll('.batch-layer-start-time').forEach(inp => {
        inp.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.start_time = inp.value.trim();
                saveBatchOverlayLayers();
            }
        };
    });
    layersList.querySelectorAll('.batch-layer-end-time').forEach(inp => {
        inp.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.end_time = inp.value.trim();
                saveBatchOverlayLayers();
            }
        };
    });

    // Random timing
    layersList.querySelectorAll('.batch-layer-random-duration').forEach(inp => {
        inp.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.random_duration = parseFloat(inp.value) || 5;
                saveBatchOverlayLayers();
            }
        };
    });
    layersList.querySelectorAll('.batch-layer-random-interval').forEach(inp => {
        inp.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.random_interval = parseFloat(inp.value) || 15;
                saveBatchOverlayLayers();
            }
        };
    });

    // Blur specific
    layersList.querySelectorAll('.batch-layer-blur-type').forEach(sel => {
        sel.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === sel.dataset.id);
            if (layer) {
                layer.blur_type = sel.value;
                renderBatchLayersListUI();
            }
        };
    });
    layersList.querySelectorAll('.batch-layer-mask-color').forEach(inp => {
        inp.oninput = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.mask_color = inp.value;
                saveBatchOverlayLayers();
            }
        };
    });

    // Text specific
    layersList.querySelectorAll('.batch-layer-text-content').forEach(inp => {
        inp.oninput = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.text = inp.value;
                saveBatchOverlayLayers();
            }
        };
    });
    layersList.querySelectorAll('.batch-layer-text-anim').forEach(sel => {
        sel.onchange = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === sel.dataset.id);
            if (layer) {
                layer.animation = sel.value;
                saveBatchOverlayLayers();
            }
        };
    });
    layersList.querySelectorAll('.batch-layer-text-color').forEach(inp => {
        inp.oninput = () => {
            const layer = window.batchCustomOverlayLayers.find(l => l.id === inp.dataset.id);
            if (layer) {
                layer.color = inp.value;
                saveBatchOverlayLayers();
            }
        };
    });
}

function applyBatchSubtitlePreset(preset) {
    const font = document.getElementById('batch_subFont');
    const colorPicker = document.getElementById('batch_subColorPicker');
    const colorText = document.getElementById('batch_subColorText');

    if (preset === 'yellow') {
        if (font) font.value = 'Montserrat';
        if (colorPicker) colorPicker.value = '#fde047';
        if (colorText) colorText.value = '#fde047';
    } else if (preset === 'white') {
        if (font) font.value = 'Inter';
        if (colorPicker) colorPicker.value = '#ffffff';
        if (colorText) colorText.value = '#ffffff';
    } else if (preset === 'tiktok') {
        if (font) font.value = 'Tiktok';
        if (colorPicker) colorPicker.value = '#fef08a';
        if (colorText) colorText.value = '#fef08a';
    } else if (preset === 'neon') {
        if (font) font.value = 'Anton';
        if (colorPicker) colorPicker.value = '#38bdf8';
        if (colorText) colorText.value = '#38bdf8';
    }
    updateBatchSubLivePreview();
}

function updateBatchSubLivePreview() {
    const box = document.getElementById('batch_subLivePreviewBox');
    const font = document.getElementById('batch_subFont')?.value || 'Montserrat';
    const size = parseInt(document.getElementById('batch_subSize')?.value) || 24;
    const color = document.getElementById('batch_subColorPicker')?.value || '#ffffff';
    const outlineColor = document.getElementById('batch_subOutlineColorPicker')?.value || '#000000';
    const outline = parseInt(document.getElementById('batch_subOutline')?.value) || 1;

    if (box) {
        box.style.fontFamily = font;
        box.style.fontSize = Math.min(24, Math.max(14, size * 0.75)) + 'px';
        box.style.color = color;
        const o = Math.max(1, outline);
        box.style.textShadow = `-${o}px -${o}px 0 ${outlineColor}, ${o}px -${o}px 0 ${outlineColor}, -${o}px ${o}px 0 ${outlineColor}, ${o}px ${o}px 0 ${outlineColor}`;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. BỘ ĐIỀU PHỐI XUẤT VIDEO HÀNG LOẠT (FIFO QUEUE RUNNER)
// ─────────────────────────────────────────────────────────────────────────────

function getParentDir(filePath) {
    if (!filePath || typeof filePath !== 'string') return '';
    const clean = filePath.trim().replace(/^["']|["']$/g, '');
    const lastSlash = Math.max(clean.lastIndexOf('/'), clean.lastIndexOf('\\'));
    return lastSlash > 0 ? clean.substring(0, lastSlash) : '';
}

function setupBatchExecutionEvents() {
    const btnStart = document.getElementById('btnBatchStartExport');
    const btnStop = document.getElementById('btnBatchStopExport');
    const btnOpenDir = document.getElementById('btnBatchOpenOutputDir');
    const btnSelectDir = document.getElementById('btnBatchSelectOutputDir');
    const chkSaveToSource = document.getElementById('batch_saveToSourceDir');

    if (btnStart) btnStart.addEventListener('click', startBatchExport);
    if (btnStop) btnStop.addEventListener('click', stopBatchExport);

    if (chkSaveToSource) {
        chkSaveToSource.addEventListener('change', () => {
            const outInput = document.getElementById('batch_outputDir');
            const selectBtn = document.getElementById('btnBatchSelectOutputDir');
            if (chkSaveToSource.checked) {
                if (outInput) {
                    if (!outInput.dataset.prevDir) outInput.dataset.prevDir = outInput.value || '';
                    outInput.value = '[Tự động] Cùng thư mục chứa từng video gốc';
                }
                if (selectBtn) {
                    selectBtn.style.opacity = '0.5';
                    selectBtn.style.pointerEvents = 'none';
                }
            } else {
                if (outInput) {
                    outInput.value = outInput.dataset.prevDir || 'output/batch_export';
                }
                if (selectBtn) {
                    selectBtn.style.opacity = '1';
                    selectBtn.style.pointerEvents = 'auto';
                }
            }
        });
    }
    
    if (btnOpenDir) {
        btnOpenDir.addEventListener('click', () => {
            const isSaveToSource = Boolean(document.getElementById('batch_saveToSourceDir')?.checked);
            let outDir = (document.getElementById('batch_outputDir')?.value || 'output/batch_export').trim();
            if (isSaveToSource) {
                const firstWithVideo = batchEditorItems.find(it => it.videoPath);
                if (firstWithVideo && firstWithVideo.videoPath) {
                    const sDir = getParentDir(firstWithVideo.videoPath);
                    if (sDir) outDir = sDir;
                }
            }
            if (outDir.startsWith('[Tự động]')) {
                showToast('Chưa có video nào trong danh sách để mở thư mục gốc.', 'info');
                return;
            }
            fetch('/api/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: outDir })
            });
        });
    }

    if (btnSelectDir) {
        btnSelectDir.addEventListener('click', async () => {
            if (typeof window.selectDirectory === 'function') {
                const chosen = await window.selectDirectory('Chọn thư mục xuất video hàng loạt');
                if (chosen) {
                    const outInput = document.getElementById('batch_outputDir');
                    if (outInput) outInput.value = chosen;
                    showToast(`Đã chọn thư mục xuất: ${chosen}`, 'success');
                }
            }
        });
    }
}

/**
 * Thu thập cấu hình chung áp dụng cho tất cả video
 */
function collectBatchGlobalConfig() {
    const dubbingEnabled = document.getElementById('batch_dubbingEnabled')?.checked ?? true;
    const voiceInput = document.getElementById('batch_dubbingVoiceInput')?.value || 'local_clone_1787245769140';
    const speed = parseFloat(document.getElementById('batch_dubbingSpeed')?.value || 1.1);
    const voiceVol = (parseInt(document.getElementById('batch_dubbingVoiceVol')?.value || 100)) / 100;
    const origVol = (parseInt(document.getElementById('batch_dubbingOrigVol')?.value || 45)) / 100;
    const ducking = Boolean(document.getElementById('batch_dubbingDucking')?.checked);
    const threads = parseInt(document.getElementById('batch_dubbingThreads')?.value || 16);

    // Stem separation
    const stemEnabled = Boolean(document.getElementById('batch_editorStemSeparationEnabled')?.checked);
    const stemMode = document.getElementById('batch_editorStemMode')?.value || 'mdx_net_hq4';

    // Subtitle style
    const subtitlesEnabled = document.getElementById('batch_subtitlesEnabled')?.checked ?? true;
    const font = document.getElementById('batch_subFont')?.value || 'Montserrat';
    const size = parseInt(document.getElementById('batch_subSize')?.value || 24);
    const color = document.getElementById('batch_subColorPicker')?.value || '#ffffff';
    const outlineColor = document.getElementById('batch_subOutlineColorPicker')?.value || '#000000';
    const outline = parseInt(document.getElementById('batch_subOutline')?.value || 1);
    const blurSubOriginal = document.getElementById('batch_reviewBlurOriginalSubtitles')?.checked ?? true;

    // Video tools
    const videoSpeed = parseFloat(document.getElementById('batch_editToolSpeedSlider')?.value || 1.0);
    const aspectRatio = document.getElementById('batch_editToolAspectRatio')?.value || 'original';
    const mirrorFlip = Boolean(document.getElementById('batch_editToolMirrorFlip')?.checked);

    // Auto delogo
    const enableDelogo = Boolean(document.getElementById('batch_enableAutoDelogo')?.checked);
    const delogoCorner = document.getElementById('batch_delogoCorner')?.value || 'bottom-right';
    const delogoSize = document.getElementById('batch_delogoSize')?.value || 'medium';
    const delogoMethod = document.getElementById('batch_delogoMethod')?.value || 'delogo';

    // Watermark
    const enableWatermark = Boolean(document.getElementById('batch_enableLogoWatermark')?.checked);
    const watermarkPath = document.getElementById('batch_logoInputPath')?.value || '';
    const watermarkOpacity = parseInt(document.getElementById('batch_logoOpacity')?.value || 100);

    const effectiveOrigVol = dubbingEnabled ? origVol : 1.0;
    const effectiveDucking = dubbingEnabled ? ducking : false;
    const effectiveStemEnabled = dubbingEnabled && stemEnabled;

    return {
        mode: dubbingEnabled ? 'tts' : 'none',
        dubbing: {
            enabled: dubbingEnabled,
            mode: 'tts',
            voice_id: voiceInput,
            voice: voiceInput,
            speed: speed,
            voice_volume: voiceVol,
            voice_vol: voiceVol,
            original_volume: effectiveOrigVol,
            orig_vol: effectiveOrigVol,
            audio_ducking: effectiveDucking,
            threads: threads,
            remove_original_vocals: effectiveStemEnabled,
            stem_separation: {
                enabled: effectiveStemEnabled,
                mode: stemMode,
                device: 'auto',
                remove_vocals: effectiveStemEnabled,
                keep_sfx: true
            }
        },
        subtitles_enabled: subtitlesEnabled,
        subtitle_style: {
            font: font,
            size: size,
            color: color,
            outline_color: outlineColor,
            outline: outline,
            bold: true,
            italic: false,
            uppercase: false
        },
        blur_original_subtitles: blurSubOriginal,
        video_speed: videoSpeed,
        aspect_ratio: aspectRatio,
        mirror_flip: mirrorFlip,
        delogo: {
            enabled: enableDelogo,
            corner: delogoCorner,
            size: delogoSize,
            method: delogoMethod
        },
        logo: {
            enabled: enableWatermark,
            path: watermarkPath,
            opacity: watermarkOpacity
        },
        custom_overlay_layers: (Array.isArray(window.batchCustomOverlayLayers) ? window.batchCustomOverlayLayers : []).filter(l => l.visible !== false)
    };
}

/**
 * Bắt đầu xuất video hàng loạt tuần tự
 */
export async function startBatchExport() {
    // 1. Kiểm tra bản quyền
    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_editor', 'Biên tập hàng loạt')) {
            return;
        }
    }

    if (isBatchRunning) {
        showToast('Hàng đợi đang xử lý!', 'warning');
        return;
    }

    // 2. Lọc các video được tích chọn
    const selectedItems = batchEditorItems.filter(item => item.selected);
    if (selectedItems.length === 0) {
        showToast('Vui lòng tích chọn ít nhất 1 video trong bảng để bắt đầu!', 'warning');
        return;
    }

    // 3. Kiểm tra video thiếu SRT
    const missingSrtItems = selectedItems.filter(item => !item.srtPath && (!item.subtitles || item.subtitles.length === 0));
    if (missingSrtItems.length > 0) {
        const proceed = await showConfirmModal(
            'Phát hiện video chưa có phụ đề SRT',
            `Có ${missingSrtItems.length} / ${selectedItems.length} video chưa có phụ đề SRT kèm theo.\n\nBạn có muốn tự động bỏ qua các video này và chỉ xuất những video đã có SRT không?`
        );
        if (!proceed) return;
    }

    // Danh sách thực sự sẵn sàng chạy
    const queue = selectedItems.filter(item => !!item.srtPath || (item.subtitles && item.subtitles.length > 0));
    if (queue.length === 0) {
        showToast('Không có video nào đủ điều kiện (cần có file phụ đề SRT)!', 'error');
        return;
    }

    isBatchRunning = true;
    batchAbortController = new AbortController();

    const btnStart = document.getElementById('btnBatchStartExport');
    const btnStop = document.getElementById('btnBatchStopExport');
    const progressWrapper = document.getElementById('batchOverallProgressContainer');
    const overallStatus = document.getElementById('batchOverallStatusText');
    const overallProgress = document.getElementById('batchOverallProgressBarFill');

    if (btnStart) btnStart.style.display = 'none';
    if (btnStop) btnStop.style.display = 'inline-flex';
    if (progressWrapper) progressWrapper.style.display = 'block';

    appendLog(`[${timeNow()}] > 🚀 Bắt đầu xử lý hàng loạt ${queue.length} video theo hàng đợi tuần tự...`, 'info');

    const globalConfig = collectBatchGlobalConfig();
    const batchStartTime = Date.now() / 1000;
    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < queue.length; i++) {
        if (!isBatchRunning || (batchAbortController && batchAbortController.signal.aborted)) {
            sendTelegramBatchEvent({
                event: 'batch_cancelled',
                total_count: queue.length,
                completed_count: successCount,
                failed_count: failCount,
                start_time: batchStartTime,
                end_time: Date.now() / 1000,
                batch_id: 'batch_export_' + Math.floor(batchStartTime)
            });
            break;
        }

        const item = queue[i];
        const itemStartTime = Date.now() / 1000;
        currentBatchItemIndex = batchEditorItems.indexOf(item);
        item.status = 'processing';
        item.progress = 0;
        renderBatchTable();

        const overallPercent = Math.round((i / queue.length) * 100);
        if (overallStatus) overallStatus.textContent = `Đang xử lý (${i + 1}/${queue.length}): ${item.videoName}`;
        if (overallProgress) overallProgress.style.width = overallPercent + '%';

        appendLog(`[${timeNow()}] > [Video ${i + 1}/${queue.length}] Đang xuất: ${item.videoName}...`, 'info');

        try {
            const saveToSource = Boolean(document.getElementById('batch_saveToSourceDir')?.checked);
            let outDir = (document.getElementById('batch_outputDir')?.value || 'output/batch_export').trim();
            if (saveToSource && item.videoPath) {
                const sDir = getParentDir(item.videoPath);
                if (sDir) outDir = sDir;
            }
            const outName = `[Edited] ${item.videoName.replace(/\.[^/.]+$/, '')}.mp4`;

            const itemOverrides = {
                ...globalConfig,
                source_tool: 'batch_editor',
                inputVideo: item.videoPath,
                outputDir: outDir,
                save_to_source_dir: saveToSource,
                outputName: outName,
                manualSrt: item.srtPath || '',
                subtitles: (item.subtitles && item.subtitles.length > 0) ? item.subtitles : undefined,
                ocr_region: item.ocrRegion,
                custom_overlay_layers: (Array.isArray(window.batchCustomOverlayLayers) && window.batchCustomOverlayLayers.length > 0)
                    ? window.batchCustomOverlayLayers.filter(l => l.visible !== false)
                    : (globalConfig.custom_overlay_layers || [])
            };

            const payload = (typeof window.buildEditorExportConfig === 'function')
                ? window.buildEditorExportConfig(itemOverrides)
                : itemOverrides;

            const response = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: batchAbortController.signal
            });

            if (!response.ok) {
                let errText = 'Lỗi khởi chạy backend';
                try {
                    const errJson = await response.json();
                    if (errJson.error) errText = errJson.error;
                } catch(e) {}
                throw new Error(errText);
            }

            // Đọc SSE Stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let isItemSuccess = false;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    const cleanLine = line.replace('data: ', '').trim();
                    if (!cleanLine) continue;

                    if (cleanLine.startsWith('[EVENT:SUCCESS]')) {
                        isItemSuccess = true;
                        try {
                            const succData = JSON.parse(cleanLine.replace('[EVENT:SUCCESS]', '').trim());
                            if (succData.path) {
                                item.outputPath = succData.path;
                            }
                        } catch(e) {}
                    } else if (cleanLine.startsWith('[EVENT:FAILED]')) {
                        isItemSuccess = false;
                        item.errorMsg = cleanLine.replace('[EVENT:FAILED]', '').trim();
                    } else if (cleanLine.includes('Render') || cleanLine.includes('%')) {
                        const m = cleanLine.match(/(\d+)%/);
                        if (m) {
                            item.progress = Math.min(99, parseInt(m[1]));
                            renderBatchTable();
                        }
                    }
                }
            }

            if (isItemSuccess) {
                item.status = 'completed';
                item.progress = 100;
                if (!item.outputPath) item.outputPath = `${outDir}/${outName}`;
                successCount++;
                appendLog(`[${timeNow()}] > ✅ Hoàn tất video: ${item.videoName}`, 'success');

                sendTelegramBatchEvent({
                    event: 'video_success',
                    title: item.videoName,
                    output_path: item.outputPath,
                    duration_sec: (Date.now() / 1000) - itemStartTime,
                    current_index: i + 1,
                    total_count: queue.length,
                    task_id: `editor_${item.id || item.videoName}_${i}`
                });
            } else {
                item.status = 'error';
                failCount++;
                appendLog(`[${timeNow()}] > ❌ Thất bại video: ${item.videoName} - ${item.errorMsg || 'Lỗi không xác định'}`, 'error');

                sendTelegramBatchEvent({
                    event: 'video_failure',
                    title: item.videoName,
                    error: item.errorMsg || 'Lỗi không xác định',
                    duration_sec: (Date.now() / 1000) - itemStartTime,
                    current_index: i + 1,
                    total_count: queue.length,
                    task_id: `editor_${item.id || item.videoName}_${i}`
                });
            }

        } catch (e) {
            if (e.name === 'AbortError') {
                appendLog(`[${timeNow()}] > 🛑 Đã dừng tiến trình hàng loạt theo lệnh người dùng.`, 'warning');
                sendTelegramBatchEvent({
                    event: 'batch_cancelled',
                    total_count: queue.length,
                    completed_count: successCount,
                    failed_count: failCount,
                    start_time: batchStartTime,
                    end_time: Date.now() / 1000,
                    batch_id: 'batch_export_' + Math.floor(batchStartTime)
                });
                break;
            } else {
                item.status = 'error';
                item.errorMsg = e.message;
                failCount++;
                appendLog(`[${timeNow()}] > ❌ Lỗi xử lý ${item.videoName}: ${e.message}`, 'error');

                sendTelegramBatchEvent({
                    event: 'video_failure',
                    title: item.videoName,
                    error: e.message,
                    duration_sec: (Date.now() / 1000) - itemStartTime,
                    current_index: i + 1,
                    total_count: queue.length,
                    task_id: `editor_${item.id || item.videoName}_${i}`
                });
            }
        }

        renderBatchTable();
        saveBatchItemsToStorage();
    }

    // Kết thúc hàng đợi
    isBatchRunning = false;
    currentBatchItemIndex = -1;

    if (btnStart) btnStart.style.display = 'inline-flex';
    if (btnStop) btnStop.style.display = 'none';
    if (overallProgress) overallProgress.style.width = '100%';
    if (overallStatus) {
        overallStatus.textContent = `🎉 Hoàn tất hàng loạt: ${successCount} thành công, ${failCount} lỗi.`;
    }

    if (!batchAbortController?.signal?.aborted) {
        sendTelegramBatchEvent({
            event: 'batch_completed',
            total_count: queue.length,
            success_count: successCount,
            failed_count: failCount,
            start_time: batchStartTime,
            end_time: Date.now() / 1000,
            output_dir: (document.getElementById('batch_outputDir')?.value || 'output/batch_export').trim(),
            batch_id: 'batch_export_' + Math.floor(batchStartTime)
        });
    }

    renderBatchTable();
    saveBatchItemsToStorage();

    showAlertModal({
        title: '🎉 Hoàn Tất Biên Tập Hàng Loạt!',
        message: `Hệ thống đã hoàn tất xử lý danh sách hàng loạt.\n\n- Thành công: ${successCount} video\n- Thất bại: ${failCount} video\n\nBạn có thể nhấn nút 📂 ở cột Hành Động để xem từng video thành phẩm!`,
        theme: 'success'
    });
}

/**
 * Dừng khẩn cấp tiến trình hàng loạt
 */
export async function stopBatchExport() {
    if (!isBatchRunning) return;

    isBatchRunning = false;
    if (batchAbortController) {
        batchAbortController.abort();
    }

    try {
        await fetch('/api/stop_export', { method: 'POST' });
    } catch(e) {}

    const btnStart = document.getElementById('btnBatchStartExport');
    const btnStop = document.getElementById('btnBatchStopExport');
    const overallStatus = document.getElementById('batchOverallStatusText');

    if (btnStart) btnStart.style.display = 'inline-flex';
    if (btnStop) btnStop.style.display = 'none';
    if (overallStatus) overallStatus.textContent = '🛑 Đã dừng khẩn cấp hàng loạt!';

    if (currentBatchItemIndex >= 0 && batchEditorItems[currentBatchItemIndex]) {
        batchEditorItems[currentBatchItemIndex].status = 'pending';
    }
    currentBatchItemIndex = -1;

    renderBatchTable();
    saveBatchItemsToStorage();
    showToast('Đã dừng khẩn cấp tiến trình xuất video hàng loạt.', 'warning');
}

/**
 * Helper phân tích text SRT thành mảng objects
 */
function parseSrtContent(data) {
    if (!data) return [];
    const normalized = data.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
    const blocks = normalized.split(/\n\s*\n/);
    const result = [];

    blocks.forEach((block) => {
        const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.length >= 2) {
            let timeLine = lines[1];
            let textStartIndex = 2;

            if (lines[0].includes('-->')) {
                timeLine = lines[0];
                textStartIndex = 1;
            }

            const timeMatch = timeLine.match(/(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})/);
            if (timeMatch) {
                const text = lines.slice(textStartIndex).join(' ');
                result.push({
                    id: result.length + 1,
                    start: timeMatch[1],
                    end: timeMatch[2],
                    text: text
                });
            }
        }
    });

    return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. CÁC TÁC VỤ HÀNG LOẠT: QUÉT OCR, DỊCH & LÀM SẠCH, TỰ ĐỘNG TOÀN TRÌNH
// ─────────────────────────────────────────────────────────────────────────────

function setBatchTaskUiRunning(isRunning, taskName = '') {
    isBatchRunning = isRunning;
    const btnStopTask = document.getElementById('btnBatchStopTask');
    const btnScanOcr = document.getElementById('btnBatchScanOcr');
    const btnTranslateClean = document.getElementById('btnBatchTranslateClean');
    const btnAutoAllInOne = document.getElementById('btnBatchAutoAllInOne');
    const btnStartExport = document.getElementById('btnBatchStartExport');
    const progressWrapper = document.getElementById('batchOverallProgressContainer');
    const overallStatus = document.getElementById('batchOverallStatusText');

    if (btnStopTask) btnStopTask.style.display = isRunning ? 'inline-flex' : 'none';
    if (btnScanOcr) btnScanOcr.disabled = isRunning;
    if (btnTranslateClean) btnTranslateClean.disabled = isRunning;
    if (btnAutoAllInOne) btnAutoAllInOne.disabled = isRunning;
    if (btnStartExport) btnStartExport.disabled = isRunning;

    if (progressWrapper) progressWrapper.style.display = isRunning ? 'block' : 'none';
    if (overallStatus && taskName) {
        overallStatus.textContent = isRunning ? `Đang thực hiện: ${taskName}...` : 'Sẵn sàng';
    }
}

function updateBatchOverallProgress(current, total, statusText) {
    const overallStatus = document.getElementById('batchOverallStatusText');
    const overallProgress = document.getElementById('batchOverallProgressBarFill');
    if (overallStatus && statusText) overallStatus.textContent = statusText;
    if (overallProgress && total > 0) {
        const pct = Math.round((current / total) * 100);
        overallProgress.style.width = pct + '%';
    }
}

/**
 * Kiểm tra xem danh sách phụ đề có cần dịch lại hoặc sửa lỗi hay không
 */
function checkSubtitleNeedsTranslation(subtitles) {
    if (!subtitles || !Array.isArray(subtitles) || subtitles.length === 0) {
        return { needsTranslation: true, reason: 'Chưa có dữ liệu phụ đề', untranslatedCount: 0 };
    }

    let untranslatedCount = 0;
    let errorCount = 0;

    for (const sub of subtitles) {
        const orig = (sub.text || '').trim();
        const trans = (sub.translation || '').trim();

        if (trans.includes('[Lỗi') || trans.includes('API Error') || trans.includes('error:') || trans.includes('quota')) {
            errorCount++;
            continue;
        }

        if (!trans) {
            untranslatedCount++;
            continue;
        }

        // Bản dịch vẫn còn nguyên chữ Hán
        if (/[\u4e00-\u9fff]/.test(trans) && (/[\u4e00-\u9fff]/.test(orig) || trans === orig)) {
            untranslatedCount++;
            continue;
        }
    }

    const total = subtitles.length;
    if (errorCount > 0) {
        return {
            needsTranslation: true,
            reason: `Phát hiện ${errorCount}/${total} câu bị lỗi`,
            untranslatedCount: errorCount + untranslatedCount
        };
    }

    if (untranslatedCount > 0) {
        return {
            needsTranslation: true,
            reason: `Có ${untranslatedCount}/${total} câu chưa dịch`,
            untranslatedCount
        };
    }

    return { needsTranslation: false, reason: 'Đã hoàn tất bản dịch', untranslatedCount: 0 };
}

/**
 * Gọi API làm sạch phụ đề AI (Chỉ dùng khi người dùng chủ động bấm Làm sạch thủ công)
 * Tự động chia nhỏ chunk 200 câu an toàn để không bao giờ bị cắt cụt do chạm trần token LLM.
 */
async function executeSubtitlesCleanBatch(subs, aiChoice, signal) {
    if (!subs || subs.length === 0) return subs;
    const isOffline = aiChoice && aiChoice.engine === 'offline';
    const localModel = (aiChoice && aiChoice.localModel) || 'qwen2.5:7b';
    let openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
    let openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
    let openaiModel = (openaiBaseUrl.includes('openrouter.ai') || openaiKey.startsWith('sk-or-')) 
        ? 'openai/gpt-5.6-luna-pro' 
        : 'gpt-5.6-luna-pro-batch';

    // Nếu số câu quá lớn (> 300 câu), chia thành từng đợt 200 câu để chống tràn token
    const CLEAN_CHUNK = 200;
    let allCleaned = [];
    for (let c = 0; c < subs.length; c += CLEAN_CHUNK) {
        if (signal && signal.aborted) break;
        const subChunk = subs.slice(c, c + CLEAN_CHUNK);
        try {
            const res = await fetch('/api/clean_subtitles_ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subtitles: subChunk,
                    engine: isOffline ? 'offline' : 'online',
                    local_model: isOffline ? localModel : undefined,
                    openai_key: (!isOffline && openaiKey) ? openaiKey : undefined,
                    openai_base_url: !isOffline ? openaiBaseUrl : undefined,
                    openai_model: !isOffline ? openaiModel : undefined
                }),
                signal: signal
            });

            if (res.ok) {
                const data = await res.json();
                if (data.subtitles && Array.isArray(data.subtitles) && data.subtitles.length > 0) {
                    allCleaned.push(...data.subtitles);
                    continue;
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') throw err;
        }
        // Fallback giữ nguyên chunk gốc nếu clean lỗi
        allCleaned.push(...subChunk);
    }

    return allCleaned.length > 0 ? allCleaned : subs;
}

/**
 * Gọi API dịch phụ đề AI chuẩn mực theo logic của Biên Tập Phim:
 * 1. Sử dụng Parallel Worker Engine (6 luồng song song, Queue-based)
 * 2. Chia mẻ 100 câu có kèm ngữ cảnh, thử lại tối đa 5 lần nếu nghẽn mạng
 * 3. Bảo toàn tuyệt đối 100% số câu và timestamp, không làm mất hoặc cắt cụt phụ đề
 */
async function executeSubtitlesTranslateBatch(subs, aiChoice, signal) {
    if (!subs || subs.length === 0) return subs;

    const isOffline = aiChoice && aiChoice.engine === 'offline';
    const localModel = (aiChoice && aiChoice.localModel) || 'qwen2.5:7b';
    let openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
    let openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
    
    // Mặc định luôn dùng Qwen như Tab Biên Tập Phim
    let openaiModel = 'qwen/qwen3.7-flash';
    const configuredModel = document.getElementById('openaiModel')?.value?.trim() || '';
    if (configuredModel && configuredModel.toLowerCase().includes('qwen')) {
        openaiModel = configuredModel;
    }

    const sourceLang = (aiChoice && aiChoice.source_lang) || 'auto';
    const targetLang = (aiChoice && aiChoice.target_lang) || 'vi';
    const transStyle = (aiChoice && aiChoice.translation_style) || 'cinema';

    const CONCURRENCY = isOffline ? 1 : 6;
    const BATCH_SIZE = 100;
    const CONTEXT_LINES = 6;

    // Chuẩn bị danh sách chunks có kèm ngữ cảnh câu trước
    const allChunks = [];
    for (let i = 0; i < subs.length; i += BATCH_SIZE) {
        const chunk = subs.slice(i, i + BATCH_SIZE);
        let ctx = [];
        if (i > 0) {
            ctx = subs.slice(Math.max(0, i - CONTEXT_LINES), i).map(s => ({
                id: s.id,
                text: s.translation || s.text
            }));
        }
        allChunks.push({
            chunk,
            ctx,
            from: i + 1,
            to: Math.min(i + BATCH_SIZE, subs.length)
        });
    }

    const resultSubs = JSON.parse(JSON.stringify(subs));
    const subMap = new Map();
    resultSubs.forEach(s => subMap.set(String(s.id), s));

    let queueIdx = 0;
    let translatedCount = 0;
    const totalSubs = subs.length;

    appendLog(`[${timeNow()}] > ⚡ Khởi động Engine dịch thuật song song (${CONCURRENCY} worker, ${allChunks.length} nhóm, tổng ${totalSubs} câu)...`, 'info');

    async function translationWorker(workerIdx) {
        while (true) {
            if (signal && signal.aborted) return;
            const taskIdx = queueIdx++;
            if (taskIdx >= allChunks.length) return;

            const { chunk, ctx, from, to } = allChunks[taskIdx];
            const payload = {
                mode: isOffline ? 'local' : 'ai',
                subtitles: chunk,
                context_before: ctx,
                source_lang: sourceLang,
                target_lang: targetLang,
                translation_style: transStyle,
                stream: false,
                engine: isOffline ? 'offline' : 'online',
                local_model: isOffline ? localModel : undefined,
                openai_key: (!isOffline && openaiKey) ? openaiKey : undefined,
                openai_base_url: !isOffline ? openaiBaseUrl : undefined,
                openai_model: !isOffline ? openaiModel : undefined
            };

            let data = null;
            const MAX_RETRIES = 5;

            for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
                if (signal && signal.aborted) return;
                const ctrlTimeout = new AbortController();
                const timeoutId = setTimeout(() => ctrlTimeout.abort(), 90000);
                const onCancel = () => ctrlTimeout.abort();
                if (signal) signal.addEventListener('abort', onCancel);

                try {
                    const res = await fetch('/api/translate_subtitles', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                        signal: ctrlTimeout.signal
                    });
                    data = await res.json();
                    if (data && !data.error && Array.isArray(data.subtitles)) {
                        break;
                    }
                    if (attempt < MAX_RETRIES && (!signal || !signal.aborted)) {
                        const jitter = 1000 + attempt * 800 + Math.random() * 500;
                        await new Promise(r => setTimeout(r, jitter));
                    }
                } catch (fetchErr) {
                    if (signal && signal.aborted) return;
                    if (attempt < MAX_RETRIES) {
                        const jitter = 1200 + attempt * 1000;
                        await new Promise(r => setTimeout(r, jitter));
                    }
                } finally {
                    clearTimeout(timeoutId);
                    if (signal) signal.removeEventListener('abort', onCancel);
                }
            }

            if (signal && signal.aborted) return;

            if (data && Array.isArray(data.subtitles)) {
                let chunkOk = 0;
                data.subtitles.forEach(item => {
                    const target = subMap.get(String(item.id));
                    if (target && item.translation) {
                        target.translation = item.translation;
                        chunkOk++;
                    }
                });
                translatedCount += chunkOk;
                const pct = Math.round((translatedCount / totalSubs) * 100);
                appendLog(`[${timeNow()}] > [W${workerIdx}] ✅ Dịch xong nhóm ${from}–${to} (${pct}% | ${translatedCount}/${totalSubs} câu)`, 'info');
            } else {
                appendLog(`[${timeNow()}] > [W${workerIdx}] ⚠️ Nhóm ${from}–${to} giữ nguyên câu gốc do phản hồi AI không trả về bản dịch.`, 'warning');
            }
        }
    }

    const workers = [];
    const numWorkers = Math.min(CONCURRENCY, allChunks.length);
    for (let w = 0; w < numWorkers; w++) {
        workers.push(
            new Promise(resolve => {
                setTimeout(() => translationWorker(w + 1).then(resolve).catch(resolve), w * 120);
            })
        );
    }

    await Promise.all(workers);
    return resultSubs;
}

/**
 * 1. Quét OCR hàng loạt cho các video trong bảng
 */
export async function startBatchOcrScan() {
    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_editor', 'Quét OCR hàng loạt')) return;
    }

    const selected = batchEditorItems.filter(i => i.selected);
    const targetItems = selected.length > 0 ? selected : batchEditorItems;
    if (targetItems.length === 0) {
        showToast('Chưa có video nào trong danh sách!', 'warning');
        return;
    }

    let queue = targetItems;
    if (selected.length === 0) {
        queue = targetItems.filter(i => !i.srtPath && (!i.subtitles || i.subtitles.length === 0));
        if (queue.length === 0) {
            const proceed = await showConfirmModal(
                'Quét lại OCR toàn bộ danh sách?',
                `Tất cả ${targetItems.length} video đều đã có file SRT.\n\nBạn có muốn quét lại OCR cho toàn bộ video này không?`
            );
            if (!proceed) return;
            queue = targetItems;
        }
    }

    taskAbortController = new AbortController();
    setBatchTaskUiRunning(true, 'Quét OCR hàng loạt');
    appendLog(`[${timeNow()}] > 🔍 Bắt đầu quét OCR hàng loạt cho ${queue.length} video...`, 'info');

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < queue.length; i++) {
        if (taskAbortController.signal.aborted) {
            appendLog(`[${timeNow()}] > 🛑 Đã dừng quét OCR theo lệnh người dùng.`, 'warning');
            break;
        }

        const item = queue[i];
        item.status = 'processing';
        item.progress = 0;
        currentBatchItemIndex = batchEditorItems.indexOf(item);
        renderBatchTable();

        updateBatchOverallProgress(i, queue.length, `[OCR ${i+1}/${queue.length}] ${item.videoName}`);
        appendLog(`[${timeNow()}] > 🔍 [OCR ${i+1}/${queue.length}] Bắt đầu quét: ${item.videoName}...`, 'info');

        try {
            const defaultRegion = { x: 20, y: 81.5, w: 60, h: 9.5, width: 60, height: 9.5 };
            const rawRegion = item.ocrRegion || defaultRegion;
            const region = {
                x: Number(rawRegion.x ?? 20),
                y: Number(rawRegion.y ?? 81.5),
                w: Number(rawRegion.w ?? rawRegion.width ?? 60),
                h: Number(rawRegion.h ?? rawRegion.height ?? 9.5)
            };
            
            const response = await fetch('/api/ocr_extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: item.videoPath,
                    region: region,
                    fps: 2,
                    threads: 2,
                    device: 'auto'
                }),
                signal: taskAbortController.signal
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let generatedSrtPath = '';
            let serverErrorMsg = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const msg = line.substring(6).trim();
                        if (msg.startsWith('Lỗi') || msg.startsWith('🛑') || msg.includes('Error:') || msg.toLowerCase().includes('lỗi')) {
                            serverErrorMsg = msg;
                        }
                        const pctMatch = msg.match(/\[OCR\s+(\d+)%\]/i);
                        if (pctMatch) {
                            item.progress = parseInt(pctMatch[1]);
                            renderBatchTable();
                        }
                        if (msg.startsWith('[RESULT_SRT] ')) {
                            generatedSrtPath = msg.replace('[RESULT_SRT] ', '').trim();
                        } else if (msg.endsWith('.srt') && !msg.startsWith('Vùng') && !msg.startsWith('💾') && !msg.startsWith('Lỗi') && !msg.includes('\n')) {
                            generatedSrtPath = msg;
                        }
                    }
                }
            }

            if (generatedSrtPath) {
                let subs = [];
                try {
                    const readRes = await fetch('/api/read_srt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ srt_path: generatedSrtPath })
                    });
                    if (readRes.ok) {
                        const readData = await readRes.json();
                        subs = readData.subtitles || [];
                    }
                } catch(e) {}

                // Lưu file SRT vào cùng vị trí của video gốc
                const normDestSrt = item.videoPath.replace(/\.[^/.]+$/, '.srt');
                try {
                    await fetch('/api/subtitles/export_temp', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            video_path: item.videoPath,
                            target_srt_path: normDestSrt,
                            replace_original: true,
                            subtitles: subs
                        })
                    });
                    item.srtPath = normDestSrt;
                    item.srtName = normDestSrt.split('/').pop();
                } catch(e) {
                    item.srtPath = generatedSrtPath;
                    item.srtName = generatedSrtPath.split('/').pop();
                }

                item.subtitles = subs;
                item.status = 'ocr_done';
                item.progress = 100;
                successCount++;
                appendLog(`[${timeNow()}] > ✅ [OCR ${i+1}/${queue.length}] Hoàn tất: ${item.videoName} (${subs.length} câu) -> ${item.srtName}`, 'success');
            } else {
                throw new Error(serverErrorMsg || 'Không tạo được file SRT sau khi quét OCR');
            }

        } catch (err) {
            if (err.name === 'AbortError') {
                item.status = 'pending';
                break;
            } else {
                item.status = 'error';
                item.errorMsg = err.message;
                failCount++;
                appendLog(`[${timeNow()}] > ❌ [OCR Lỗi] ${item.videoName}: ${err.message}`, 'error');
            }
        }

        renderBatchTable();
        saveBatchItemsToStorage();
    }

    setBatchTaskUiRunning(false);
    renderBatchTable();
    saveBatchItemsToStorage();
    showToast(`Quét OCR hàng loạt xong: ${successCount} thành công, ${failCount} thất bại!`, successCount > 0 ? 'success' : 'warning');
}

/**
 * 2. Dịch & Làm sạch phụ đề AI hàng loạt
 */
export async function startBatchTranslateAndClean() {
    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_editor', 'Dịch & Làm sạch hàng loạt')) return;
    }

    const selected = batchEditorItems.filter(i => i.selected);
    const targetItems = selected.length > 0 ? selected : batchEditorItems;
    if (targetItems.length === 0) {
        showToast('Chưa có video nào trong danh sách!', 'warning');
        return;
    }

    const queue = targetItems.filter(i => !!i.srtPath || (i.subtitles && i.subtitles.length > 0));
    if (queue.length === 0) {
        showToast('Chưa có video nào có file phụ đề SRT để dịch! Vui lòng Quét OCR trước.', 'warning');
        return;
    }

    const promptActionFn = window.promptTranslateCleanAction;
    const action = promptActionFn ? await promptActionFn() : 'both';
    if (!action) return;

    const promptAiFn = window.promptAiExecutionMode;
    const aiChoice = promptAiFn ? await promptAiFn(
        action === 'both' ? 'Cả Dịch & Làm Sạch Hàng Loạt' : (action === 'clean' ? 'Làm Sạch SRT Hàng Loạt' : 'Dịch Phụ Đề Hàng Loạt'),
        'Thiết lập chế độ xử lý cho toàn bộ danh sách video',
        { showLanguageOptions: (action !== 'clean') }
    ) : { engine: 'online' };
    if (!aiChoice) return;

    taskAbortController = new AbortController();
    setBatchTaskUiRunning(true, 'Dịch & Làm sạch hàng loạt');
    appendLog(`[${timeNow()}] > 🌐 Bắt đầu Dịch & Làm sạch hàng loạt cho ${queue.length} video [Tác vụ: ${action}]...`, 'info');

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < queue.length; i++) {
        if (taskAbortController.signal.aborted) {
            appendLog(`[${timeNow()}] > 🛑 Đã dừng tiến trình Dịch hàng loạt theo yêu cầu.`, 'warning');
            break;
        }

        const item = queue[i];
        item.status = 'processing';
        item.progress = 0;
        currentBatchItemIndex = batchEditorItems.indexOf(item);
        renderBatchTable();

        updateBatchOverallProgress(i, queue.length, `[Dịch ${i+1}/${queue.length}] ${item.videoName}`);
        appendLog(`[${timeNow()}] > [Video ${i+1}/${queue.length}] Đang xử lý phụ đề: ${item.videoName}...`, 'info');

        try {
            let subs = item.subtitles;
            if (!subs || subs.length === 0) {
                if (item.srtPath) {
                    const res = await fetch('/api/read_srt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ srt_path: item.srtPath })
                    });
                    if (res.ok) {
                        const d = await res.json();
                        subs = d.subtitles || [];
                    }
                }
            }

            if (!subs || subs.length === 0) {
                throw new Error('File phụ đề rỗng hoặc không đọc được');
            }

            // Kiểm tra xem SRT có cần dịch hay không (nếu là tác vụ dịch)
            if (action !== 'clean') {
                const check = checkSubtitleNeedsTranslation(subs);
                if (!check.needsTranslation) {
                    appendLog(`[${timeNow()}] > ℹ️ [Video ${i+1}/${queue.length}] "${item.videoName}" đã có bản dịch hoàn chỉnh (${check.reason}), bỏ qua.`, 'info');
                    item.status = 'translated';
                    successCount++;
                    renderBatchTable();
                    continue;
                } else {
                    appendLog(`[${timeNow()}] > 🔄 [Video ${i+1}/${queue.length}] Cần dịch: ${check.reason}. Bắt đầu dịch...`, 'info');
                }
            }

            // Làm sạch nếu action chỉ là 'clean' (Tránh gộp câu làm mất timeline khi dịch)
            if (action === 'clean') {
                subs = await executeSubtitlesCleanBatch(subs, aiChoice, taskAbortController.signal);
            }

            // Dịch nếu action là 'both' hoặc 'translate' (Engine song song chuẩn Biên Tập Phim)
            if (action === 'both' || action === 'translate') {
                subs = await executeSubtitlesTranslateBatch(subs, aiChoice, taskAbortController.signal);
            }

            // LƯU FILE SRT MỚI DỊCH VÀO CÙNG VỊ TRÍ CỦA VIDEO / SRT GỐC
            const destSrtPath = item.srtPath || item.videoPath.replace(/\.[^/.]+$/, '.srt');
            const saveRes = await fetch('/api/subtitles/export_temp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: item.videoPath,
                    target_srt_path: destSrtPath,
                    replace_original: true,
                    subtitles: subs
                })
            });

            if (saveRes.ok) {
                const saveData = await saveRes.json();
                if (saveData.srt_path) {
                    item.srtPath = saveData.srt_path.replace(/\\/g, '/');
                    item.srtName = item.srtPath.split('/').pop();
                }
            }

            item.subtitles = subs;
            item.status = 'translated';
            item.progress = 100;
            successCount++;
            appendLog(`[${timeNow()}] > ✅ [Video ${i+1}/${queue.length}] Hoàn tất Dịch & Làm sạch "${item.videoName}" (${subs.length} câu) -> Lưu tại: ${item.srtName}`, 'success');

        } catch (err) {
            if (err.name === 'AbortError') {
                item.status = 'pending';
                break;
            } else {
                item.status = 'error';
                item.errorMsg = err.message;
                failCount++;
                appendLog(`[${timeNow()}] > ❌ [Lỗi Video ${i+1}] ${item.videoName}: ${err.message}`, 'error');
            }
        }

        renderBatchTable();
        saveBatchItemsToStorage();
    }

    setBatchTaskUiRunning(false);
    renderBatchTable();
    saveBatchItemsToStorage();
    showToast(`Dịch & Làm sạch hàng loạt xong: ${successCount} thành công, ${failCount} thất bại!`, successCount > 0 ? 'success' : 'warning');
}

/**
 * 3. Quy trình Tự Động Toàn Trình (Treo máy qua đêm):
 * Video đầu vào -> Quét OCR -> Dịch & Làm sạch -> Xuất video hoàn chỉnh có sub
 */
export async function startBatchAllInOnePipeline() {
    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_editor', 'Tự động toàn trình')) return;
    }

    const selected = batchEditorItems.filter(i => i.selected);
    const targetItems = selected.length > 0 ? selected : batchEditorItems;
    if (targetItems.length === 0) {
        showToast('Chưa có video nào trong danh sách!', 'warning');
        return;
    }

    const promptAiFn = window.promptAiExecutionMode;
    const aiChoice = promptAiFn ? await promptAiFn(
        '⚡ Tự Động Toàn Trình (Treo Máy Qua Đêm)',
        'Hệ thống sẽ tự động quét OCR -> Dịch & Làm sạch SRT -> Xuất video có phụ đề hoàn chỉnh tuần tự cho tất cả video.',
        { showLanguageOptions: true }
    ) : { engine: 'online' };
    if (!aiChoice) return;

    taskAbortController = new AbortController();
    setBatchTaskUiRunning(true, 'Tự động toàn trình qua đêm');
    appendLog(`[${timeNow()}] > ⚡ BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG TOÀN TRÌNH CHO ${targetItems.length} VIDEO (TREO MÁY QUA ĐÊM)...`, 'info');

    const batchStartTime = Date.now() / 1000;
    let totalSuccess = 0;
    let totalFail = 0;

    for (let i = 0; i < targetItems.length; i++) {
        if (taskAbortController.signal.aborted) {
            appendLog(`[${timeNow()}] > 🛑 Đã dừng quy trình tự động qua đêm theo yêu cầu.`, 'warning');
            sendTelegramBatchEvent({
                event: 'batch_cancelled',
                total_count: targetItems.length,
                completed_count: totalSuccess,
                failed_count: totalFail,
                start_time: batchStartTime,
                end_time: Date.now() / 1000,
                batch_id: 'allinone_' + Math.floor(batchStartTime)
            });
            break;
        }

        const item = targetItems[i];
        const itemStartTime = Date.now() / 1000;
        currentBatchItemIndex = batchEditorItems.indexOf(item);
        item.status = 'processing';
        item.progress = 5;
        renderBatchTable();

        updateBatchOverallProgress(i, targetItems.length, `[Toàn trình ${i+1}/${targetItems.length}] ${item.videoName}`);
        appendLog(`[${timeNow()}] > ═════════════════════════════════════════════════`, 'info');
        appendLog(`[${timeNow()}] > 🎬 [Video ${i+1}/${targetItems.length}] Xử lý: ${item.videoName}`, 'info');

        try {
            // ── BƯỚC 1: Quét OCR nếu video chưa có SRT hoặc chưa có subtitles ──
            let hasValidSrt = !!item.srtPath || (item.subtitles && item.subtitles.length > 0);
            if (!hasValidSrt) {
                appendLog(`[${timeNow()}] > 🔍 [Bước 1/3] Video chưa có phụ đề, bắt đầu quét OCR tự động...`, 'info');
                const defaultRegion = { x: 20, y: 81.5, w: 60, h: 9.5, width: 60, height: 9.5 };
                const rawRegion = item.ocrRegion || defaultRegion;
                const region = {
                    x: Number(rawRegion.x ?? 20),
                    y: Number(rawRegion.y ?? 81.5),
                    w: Number(rawRegion.w ?? rawRegion.width ?? 60),
                    h: Number(rawRegion.h ?? rawRegion.height ?? 9.5)
                };
                const ocrRes = await fetch('/api/ocr_extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video_path: item.videoPath,
                        region: region,
                        fps: 2,
                        threads: 2,
                        device: 'auto'
                    }),
                    signal: taskAbortController.signal
                });

                if (!ocrRes.ok) {
                    const errJson = await ocrRes.json().catch(() => ({}));
                    throw new Error(errJson.error || `HTTP ${ocrRes.status}`);
                }

                const reader = ocrRes.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let ocrSrtPath = '';
                let serverErrorMsg = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const msg = line.substring(6).trim();
                            if (msg.startsWith('Lỗi') || msg.startsWith('🛑') || msg.includes('Error:') || msg.toLowerCase().includes('lỗi')) {
                                serverErrorMsg = msg;
                            }
                            if (msg.startsWith('[RESULT_SRT] ')) {
                                ocrSrtPath = msg.replace('[RESULT_SRT] ', '').trim();
                            } else if (msg.endsWith('.srt') && !msg.startsWith('Vùng') && !msg.startsWith('💾') && !msg.startsWith('Lỗi') && !msg.includes('\n')) {
                                ocrSrtPath = msg;
                            }
                        }
                    }
                }

                if (ocrSrtPath) {
                    let subs = [];
                    try {
                        const readRes = await fetch('/api/read_srt', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ srt_path: ocrSrtPath })
                        });
                        if (readRes.ok) {
                            const rd = await readRes.json();
                            subs = rd.subtitles || [];
                        }
                    } catch(e) {}

                    const normDest = item.videoPath.replace(/\.[^/.]+$/, '.srt');
                    await fetch('/api/subtitles/export_temp', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            video_path: item.videoPath,
                            target_srt_path: normDest,
                            replace_original: true,
                            subtitles: subs
                        })
                    }).catch(() => {});

                    item.srtPath = normDest;
                    item.srtName = normDest.split('/').pop();
                    item.subtitles = subs;
                    appendLog(`[${timeNow()}] > ✅ [Bước 1/3] Quét OCR xong (${subs.length} câu)!`, 'success');
                } else {
                    throw new Error(serverErrorMsg || 'Không trích xuất được phụ đề từ OCR');
                }
            }

            // ── BƯỚC 2: Kiểm tra & Dịch / Làm sạch phụ đề ──
            item.progress = 35;
            renderBatchTable();

            let subsToProcess = item.subtitles;
            if (!subsToProcess || subsToProcess.length === 0) {
                if (item.srtPath) {
                    const rRes = await fetch('/api/read_srt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ srt_path: item.srtPath })
                    });
                    if (rRes.ok) {
                        const rd = await rRes.json();
                        subsToProcess = rd.subtitles || [];
                    }
                }
            }

            const check = checkSubtitleNeedsTranslation(subsToProcess);
            if (check.needsTranslation) {
                appendLog(`[${timeNow()}] > 🌐 [Bước 2/3] Bắt đầu Dịch thuật phụ đề AI chuẩn Biên Tập Phim (${check.reason})...`, 'info');
                subsToProcess = await executeSubtitlesTranslateBatch(subsToProcess, aiChoice, taskAbortController.signal);

                const finalSrtPath = item.srtPath || item.videoPath.replace(/\.[^/.]+$/, '.srt');
                await fetch('/api/subtitles/export_temp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video_path: item.videoPath,
                        target_srt_path: finalSrtPath,
                        replace_original: true,
                        subtitles: subsToProcess
                    })
                }).catch(() => {});

                item.srtPath = finalSrtPath;
                item.srtName = finalSrtPath.split('/').pop();
                item.subtitles = subsToProcess;
                appendLog(`[${timeNow()}] > ✅ [Bước 2/3] Dịch & Làm sạch hoàn tất!`, 'success');
            } else {
                appendLog(`[${timeNow()}] > ℹ️ [Bước 2/3] Phụ đề đã chuẩn, bỏ qua bước dịch.`, 'info');
            }

            // ── BƯỚC 3: Xuất Video thành phẩm có Sub hoàn chỉnh ──
            item.progress = 60;
            renderBatchTable();
            appendLog(`[${timeNow()}] > 🚀 [Bước 3/3] Đang render xuất video thành phẩm...`, 'info');

            const globalConfig = collectBatchGlobalConfig();
            const saveToSource = Boolean(document.getElementById('batch_saveToSourceDir')?.checked);
            let outDir = (document.getElementById('batch_outputDir')?.value || 'output/batch_export').trim();
            if (saveToSource && item.videoPath) {
                const sDir = getParentDir(item.videoPath);
                if (sDir) outDir = sDir;
            }
            const outName = `[Subbed] ${item.videoName.replace(/\.[^/.]+$/, '')}.mp4`;

            const itemOverrides = {
                ...globalConfig,
                source_tool: 'batch_editor',
                inputVideo: item.videoPath,
                outputDir: outDir,
                save_to_source_dir: saveToSource,
                outputName: outName,
                manualSrt: item.srtPath || '',
                subtitles: (item.subtitles && item.subtitles.length > 0) ? item.subtitles : undefined,
                ocr_region: item.ocrRegion,
                custom_overlay_layers: (Array.isArray(window.batchCustomOverlayLayers) && window.batchCustomOverlayLayers.length > 0)
                    ? window.batchCustomOverlayLayers.filter(l => l.visible !== false)
                    : (globalConfig.custom_overlay_layers || [])
            };

            const payload = (typeof window.buildEditorExportConfig === 'function')
                ? window.buildEditorExportConfig(itemOverrides)
                : itemOverrides;

            const exportRes = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: taskAbortController.signal
            });

            if (!exportRes.ok) {
                const errD = await exportRes.json().catch(() => ({}));
                throw new Error(errD.error || 'Lỗi khởi chạy xuất video');
            }

            const expReader = exportRes.body.getReader();
            const expDecoder = new TextDecoder();
            let isItemSuccess = false;

            while (true) {
                const { done, value } = await expReader.read();
                if (done) break;
                const chunk = expDecoder.decode(value);
                const lines = chunk.split('\n');
                for (const line of lines) {
                    const cleanLine = line.replace('data: ', '').trim();
                    if (!cleanLine) continue;
                    if (cleanLine.startsWith('[EVENT:SUCCESS]')) {
                        isItemSuccess = true;
                        try {
                            const succData = JSON.parse(cleanLine.replace('[EVENT:SUCCESS]', '').trim());
                            if (succData.path) {
                                item.outputPath = succData.path;
                            }
                        } catch(e) {}
                    } else if (cleanLine.startsWith('[EVENT:FAILED]')) {
                        isItemSuccess = false;
                        item.errorMsg = cleanLine.replace('[EVENT:FAILED]', '').trim();
                    } else if (cleanLine.includes('Render') || cleanLine.includes('%')) {
                        const m = cleanLine.match(/(\d+)%/);
                        if (m) {
                            const renderPct = parseInt(m[1]);
                            item.progress = Math.min(99, 60 + Math.round(renderPct * 0.39));
                            renderBatchTable();
                        }
                    }
                }
            }

            if (isItemSuccess) {
                item.status = 'completed';
                item.progress = 100;
                if (!item.outputPath) item.outputPath = `${outDir}/${outName}`;
                totalSuccess++;
                appendLog(`[${timeNow()}] > 🎉 [Xong Trọn Vẹn] Video: ${item.videoName} -> ${item.outputPath}`, 'success');

                sendTelegramBatchEvent({
                    event: 'video_success',
                    title: item.videoName,
                    output_path: item.outputPath,
                    duration_sec: (Date.now() / 1000) - itemStartTime,
                    current_index: i + 1,
                    total_count: targetItems.length,
                    preset_name: 'Tự động toàn trình',
                    task_id: `allinone_${item.id || item.videoName}_${i}`
                });
            } else {
                throw new Error(item.errorMsg || 'Xuất video không thành công');
            }

        } catch (err) {
            if (err.name === 'AbortError') {
                item.status = 'pending';
                sendTelegramBatchEvent({
                    event: 'batch_cancelled',
                    total_count: targetItems.length,
                    completed_count: totalSuccess,
                    failed_count: totalFail,
                    start_time: batchStartTime,
                    end_time: Date.now() / 1000,
                    batch_id: 'allinone_' + Math.floor(batchStartTime)
                });
                break;
            } else {
                item.status = 'error';
                item.errorMsg = err.message;
                totalFail++;
                appendLog(`[${timeNow()}] > ❌ [Lỗi Video ${i+1}] ${item.videoName}: ${err.message}`, 'error');

                sendTelegramBatchEvent({
                    event: 'video_failure',
                    title: item.videoName,
                    error: err.message,
                    duration_sec: (Date.now() / 1000) - itemStartTime,
                    current_index: i + 1,
                    total_count: targetItems.length,
                    preset_name: 'Tự động toàn trình',
                    task_id: `allinone_${item.id || item.videoName}_${i}`
                });
            }
        }

        renderBatchTable();
        saveBatchItemsToStorage();
    }

    if (!taskAbortController?.signal?.aborted) {
        sendTelegramBatchEvent({
            event: 'batch_completed',
            total_count: targetItems.length,
            success_count: totalSuccess,
            failed_count: totalFail,
            start_time: batchStartTime,
            end_time: Date.now() / 1000,
            output_dir: (document.getElementById('batch_outputDir')?.value || 'output/batch_export').trim(),
            batch_id: 'allinone_' + Math.floor(batchStartTime)
        });
    }

    setBatchTaskUiRunning(false);
    renderBatchTable();
    saveBatchItemsToStorage();

    showAlertModal({
        title: '🎉 Hoàn Tất Tự Động Toàn Trình!',
        message: `Đã xử lý xong ${targetItems.length} video trong hàng đợi qua đêm.\n\n- Thành công: ${totalSuccess} video\n- Thất bại: ${totalFail} video\n\nTất cả video hoàn tất đã được dịch, làm sạch và render phụ đề chỉn chu!`,
        theme: 'success'
    });
}

/**
 * Dừng tác vụ hàng loạt đang chạy
 */
export async function stopCurrentBatchTask() {
    if (taskAbortController) {
        taskAbortController.abort();
    }
    if (isBatchRunning) {
        await stopBatchExport();
    }
    setBatchTaskUiRunning(false);
    showToast('Đã yêu cầu dừng tác vụ hàng loạt!', 'warning');
}

