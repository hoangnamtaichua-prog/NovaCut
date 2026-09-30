/**
 * Export History Feature Module (Lịch Sử Xuất Video & Quản Lý File)
 * NovaCut - AI Video & Review Editor
 */

import { showToast, showAlertModal, showConfirmModal } from '../utils.js';

let currentPage = 1;
const limitPerPage = 50;
let totalCount = 0;
let totalPages = 1;
let searchDebounceTimer = null;
let currentItems = [];

let activeScanId = null;
let scanPollInterval = null;
let currentCandidates = [];
let pendingDeleteId = null;
let currentDetailItem = null;

const TOOL_LABELS = {
    'editor': { label: 'Biên tập phim', color: '#0ea5e9' },
    'batch_editor': { label: 'Biên tập hàng loạt', color: '#6366f1' },
    'review': { label: 'Review phim', color: '#a855f7' },
    'narration': { label: 'Kể chuyện', color: '#f59e0b' },
    'batch_queue': { label: 'Hàng đợi batch', color: '#10b981' },
    'comic_review': { label: 'Review truyện', color: '#ec4899' },
    'import': { label: 'Nhập từ đĩa', color: '#14b8a6' }
};

export function initExportHistoryModule() {
    window.loadExportHistory = loadExportHistory;
    window.openExportVideo = handleOpenVideo;
    window.revealExportFolder = handleRevealFolder;
    window.copyExportPath = handleCopyPath;
    window.showExportDetail = handleShowDetail;
    window.confirmDeleteExport = handleOpenDeleteModal;

    setupExportHistoryEventListeners();
}

function setupExportHistoryEventListeners() {
    const txtSearch = document.getElementById('txtExportSearch');
    if (txtSearch) {
        txtSearch.addEventListener('input', () => {
            if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                loadExportHistory(1);
            }, 300);
        });
    }

    const selTool = document.getElementById('selExportToolFilter');
    if (selTool) {
        selTool.addEventListener('change', () => loadExportHistory(1));
    }

    const selStatus = document.getElementById('selExportStatusFilter');
    if (selStatus) {
        selStatus.addEventListener('change', () => loadExportHistory(1));
    }

    const dtFrom = document.getElementById('dtExportFrom');
    if (dtFrom) {
        dtFrom.addEventListener('change', () => loadExportHistory(1));
    }

    const dtTo = document.getElementById('dtExportTo');
    if (dtTo) {
        dtTo.addEventListener('change', () => loadExportHistory(1));
    }

    const btnReset = document.getElementById('btnResetExportFilters');
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            if (txtSearch) txtSearch.value = '';
            if (selTool) selTool.value = '';
            if (selStatus) selStatus.value = '';
            if (dtFrom) dtFrom.value = '';
            if (dtTo) dtTo.value = '';
            loadExportHistory(1);
        });
    }

    const btnRefresh = document.getElementById('btnRefreshExportHistory');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => loadExportHistory(currentPage));
    }

    const btnClearAll = document.getElementById('btnClearAllExportHistory');
    if (btnClearAll) {
        btnClearAll.addEventListener('click', handleClearAllHistory);
    }

    const btnPrev = document.getElementById('btnExportPrevPage');
    if (btnPrev) {
        btnPrev.addEventListener('click', () => {
            if (currentPage > 1) loadExportHistory(currentPage - 1);
        });
    }

    const btnNext = document.getElementById('btnExportNextPage');
    if (btnNext) {
        btnNext.addEventListener('click', () => {
            if (currentPage < totalPages) loadExportHistory(currentPage + 1);
        });
    }

    // Modal Details Actions
    const btnCloseDetail = document.getElementById('btnCloseExportDetailModal');
    const btnDetailClose = document.getElementById('btnDetailClose');
    const modalDetail = document.getElementById('exportDetailModal');
    if (btnCloseDetail && modalDetail) {
        btnCloseDetail.addEventListener('click', () => {
            modalDetail.style.display = 'none';
        });
    }
    if (btnDetailClose && modalDetail) {
        btnDetailClose.addEventListener('click', () => {
            modalDetail.style.display = 'none';
        });
    }
    const btnDetailOpenVideo = document.getElementById('btnDetailOpenVideo');
    if (btnDetailOpenVideo) {
        btnDetailOpenVideo.addEventListener('click', () => {
            if (currentDetailItem && currentDetailItem.id) {
                handleOpenVideo(currentDetailItem.id);
            }
        });
    }
    const btnDetailRevealFolder = document.getElementById('btnDetailRevealFolder');
    if (btnDetailRevealFolder) {
        btnDetailRevealFolder.addEventListener('click', () => {
            if (currentDetailItem && currentDetailItem.id) {
                handleRevealFolder(currentDetailItem.id);
            }
        });
    }
    const btnDetailCopyPath = document.getElementById('btnDetailCopyPath');
    if (btnDetailCopyPath) {
        btnDetailCopyPath.addEventListener('click', () => {
            if (currentDetailItem && currentDetailItem.output_path) {
                handleCopyPath(currentDetailItem.output_path);
            }
        });
    }

    // Modal Delete
    const modalDelete = document.getElementById('exportDeleteModal');
    const btnCancelDelete = document.getElementById('btnCancelExportDelete');
    const btnConfirmDelete = document.getElementById('btnConfirmExportDelete');
    if (modalDelete && btnCancelDelete && btnConfirmDelete) {
        btnCancelDelete.addEventListener('click', () => {
            modalDelete.style.display = 'none';
            pendingDeleteId = null;
        });
        btnConfirmDelete.addEventListener('click', executeDeleteRecord);
    }

    // Modal Import
    const btnOpenImport = document.getElementById('btnOpenImportModal');
    const modalImport = document.getElementById('exportImportModal');
    const btnCloseImport = document.getElementById('btnCloseImportModal');
    const btnBrowseFolder = document.getElementById('btnBrowseImportFolder');
    const btnStartScan = document.getElementById('btnStartImportScan');
    const btnCancelScan = document.getElementById('btnCancelImportScan');
    const btnCommitImport = document.getElementById('btnCommitImport');
    const chkSelectAll = document.getElementById('chkImportSelectAll');

    if (btnOpenImport && modalImport) {
        btnOpenImport.addEventListener('click', openImportModal);
    }
    if (btnCloseImport && modalImport) {
        btnCloseImport.addEventListener('click', closeImportModal);
    }
    if (btnBrowseFolder) {
        btnBrowseFolder.addEventListener('click', handleBrowseImportFolder);
    }
    if (btnStartScan) {
        btnStartScan.addEventListener('click', handleStartImportScan);
    }
    if (btnCancelScan) {
        btnCancelScan.addEventListener('click', handleCancelImportScan);
    }
    if (btnCommitImport) {
        btnCommitImport.addEventListener('click', handleCommitImport);
    }
    if (chkSelectAll) {
        chkSelectAll.addEventListener('change', (e) => {
            const checked = e.target.checked;
            const itemCheckboxes = document.querySelectorAll('.import-candidate-chk');
            itemCheckboxes.forEach(cb => {
                if (!cb.disabled) cb.checked = checked;
            });
            updateImportCommitButtonState();
        });
    }
}

/**
 * Tải danh sách lịch sử xuất từ API
 */
export async function loadExportHistory(page = 1) {
    currentPage = page;
    const tableBody = document.getElementById('exportHistoryTableBody');
    const loadingEl = document.getElementById('exportHistoryLoading');
    const emptyEl = document.getElementById('exportHistoryEmpty');

    if (tableBody) tableBody.innerHTML = '';
    if (loadingEl) loadingEl.style.display = 'flex';
    if (emptyEl) emptyEl.style.display = 'none';

    const search = document.getElementById('txtExportSearch')?.value?.trim() || '';
    const tool = document.getElementById('selExportToolFilter')?.value?.trim() || '';
    const status = document.getElementById('selExportStatusFilter')?.value?.trim() || '';
    const fromDate = document.getElementById('dtExportFrom')?.value?.trim() || '';
    const toDate = document.getElementById('dtExportTo')?.value?.trim() || '';

    const queryParams = new URLSearchParams({
        page: String(currentPage),
        limit: String(limitPerPage)
    });
    if (search) queryParams.set('search', search);
    if (tool) queryParams.set('source_tool', tool);
    if (status) queryParams.set('status', status);
    if (fromDate) queryParams.set('from_date', fromDate);
    if (toDate) queryParams.set('to_date', toDate);

    try {
        const response = await fetch(`/api/export-history?${queryParams.toString()}`);
        if (loadingEl) loadingEl.style.display = 'none';

        if (!response.ok) {
            if (response.status === 403) {
                const data = await response.json().catch(() => ({}));
                showAlertModal({
                    title: 'Bản Quyền Yêu Cầu',
                    message: data.message || 'Bạn cần kích hoạt bản quyền để sử dụng tính năng Lịch Sử Xuất Video.',
                    theme: 'warning'
                });
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || 'Lỗi tải lịch sử xuất');
        }

        currentItems = data.items || [];
        totalCount = data.total || 0;
        totalPages = data.total_pages || 1;

        updatePaginationUI();

        if (currentItems.length === 0) {
            if (emptyEl) emptyEl.style.display = 'flex';
        } else {
            renderExportTable(currentItems);
        }
    } catch (err) {
        if (loadingEl) loadingEl.style.display = 'none';
        showToast(`Không thể tải lịch sử xuất: ${err.message}`, 'error');
    }
}

/**
 * Render bảng lịch sử với textContent an toàn tuyệt đối chống XSS
 */
function renderExportTable(items) {
    const tableBody = document.getElementById('exportHistoryTableBody');
    if (!tableBody) return;
    tableBody.innerHTML = '';

    items.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = 'export-history-row';
        row.style.cssText = `
            display: grid;
            grid-template-columns: 48px 1fr 150px 100px 170px 130px 180px;
            gap: 12px;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid #1f2937;
            background: ${index % 2 === 0 ? '#111827' : '#0e1526'};
            transition: background 0.15s;
        `;
        row.addEventListener('mouseenter', () => row.style.background = '#1e293b');
        row.addEventListener('mouseleave', () => row.style.background = index % 2 === 0 ? '#111827' : '#0e1526');

        // 1. STT
        const sttCol = document.createElement('div');
        sttCol.style.cssText = 'color: #9ca3af; font-size: 12px; text-align: center; font-weight: 600; font-family: monospace;';
        sttCol.textContent = String((currentPage - 1) * limitPerPage + index + 1);
        row.appendChild(sttCol);

        // 2. Tên video & Đường dẫn
        const fileCol = document.createElement('div');
        fileCol.style.cssText = 'min-width: 0; display: flex; flex-direction: column; gap: 3px;';

        const nameEl = document.createElement('div');
        nameEl.style.cssText = 'font-weight: 700; color: #f9fafb; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;';
        nameEl.textContent = item.filename || 'Chưa đặt tên';
        nameEl.title = `Click để phát video: ${item.output_path || ''}`;
        nameEl.addEventListener('click', () => handleOpenVideo(item.id));

        const pathEl = document.createElement('div');
        pathEl.style.cssText = 'font-size: 11.5px; color: #9ca3af; font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; user-select: all; cursor: pointer;';
        pathEl.textContent = item.output_path || '';
        pathEl.title = `Click để mở thư mục lưu video trong File Explorer: ${item.output_path || ''}`;
        pathEl.addEventListener('click', (e) => {
            e.stopPropagation();
            handleRevealFolder(item.id);
        });

        fileCol.appendChild(nameEl);
        fileCol.appendChild(pathEl);
        row.appendChild(fileCol);

        // 3. Công cụ xuất
        const toolCol = document.createElement('div');
        const toolMeta = TOOL_LABELS[item.source_tool] || { label: item.source_tool || 'Editor', color: '#0ea5e9' };
        const toolBadge = document.createElement('span');
        toolBadge.style.cssText = `
            display: inline-block;
            padding: 3px 10px;
            border-radius: 6px;
            font-size: 11.5px;
            font-weight: 700;
            background: ${toolMeta.color}22;
            color: ${toolMeta.color};
            border: 1px solid ${toolMeta.color}44;
            white-space: nowrap;
        `;
        toolBadge.textContent = toolMeta.label;
        toolCol.appendChild(toolBadge);
        row.appendChild(toolCol);

        // 4. Dung lượng
        const sizeCol = document.createElement('div');
        sizeCol.style.cssText = 'font-size: 12.5px; color: #cbd5e1; font-weight: 600;';
        sizeCol.textContent = formatBytes(item.file_size_bytes);
        row.appendChild(sizeCol);

        // 5. Ngày hoàn thành
        const dateCol = document.createElement('div');
        dateCol.style.cssText = 'font-size: 12px; color: #9ca3af; display: flex; flex-direction: column; gap: 2px;';
        const dateText = document.createElement('span');
        dateText.textContent = formatDateTime(item.completed_at || item.created_at);
        dateCol.appendChild(dateText);

        if (item.origin === 'import') {
            const importSub = document.createElement('span');
            importSub.style.cssText = 'font-size: 10.5px; color: #14b8a6;';
            importSub.textContent = `(Nhập: ${formatDateTime(item.imported_at)})`;
            dateCol.appendChild(importSub);
        }
        row.appendChild(dateCol);

        // 6. Trạng thái
        const statusCol = document.createElement('div');
        const statusBadge = document.createElement('span');
        statusBadge.style.cssText = 'display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 700; padding: 3px 8px; border-radius: 6px;';
        
        const status = item.file_status || 'available';
        if (status === 'available') {
            statusBadge.style.background = 'rgba(16, 185, 129, 0.15)';
            statusBadge.style.color = '#34d399';
            statusBadge.style.border = '1px solid rgba(16, 185, 129, 0.3)';
            statusBadge.textContent = '🟢 Có sẵn';
        } else if (status === 'missing') {
            statusBadge.style.background = 'rgba(239, 68, 68, 0.15)';
            statusBadge.style.color = '#f87171';
            statusBadge.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            statusBadge.textContent = '🔴 Mất file';
        } else {
            statusBadge.style.background = 'rgba(245, 158, 11, 0.15)';
            statusBadge.style.color = '#fbbf24';
            statusBadge.style.border = '1px solid rgba(245, 158, 11, 0.3)';
            statusBadge.textContent = '⚠️ Ổ offline';
        }
        statusCol.appendChild(statusBadge);
        row.appendChild(statusCol);

        // 7. Thao tác
        const actionsCol = document.createElement('div');
        actionsCol.style.cssText = 'display: flex; align-items: center; gap: 6px; justify-content: flex-end;';

        // Nút Mở video
        const btnOpen = document.createElement('button');
        btnOpen.type = 'button';
        btnOpen.className = 'btn-history-action';
        btnOpen.title = 'Mở video bằng trình phát mặc định của Windows';
        btnOpen.innerHTML = '▶';
        btnOpen.style.cssText = 'padding: 5px 8px; font-size: 12px; background: #0ea5e922; color: #38bdf8; border: 1px solid #0ea5e944; border-radius: 6px; cursor: pointer;';
        btnOpen.addEventListener('click', () => handleOpenVideo(item.id));

        // Nút Thư mục
        const btnReveal = document.createElement('button');
        btnReveal.type = 'button';
        btnReveal.className = 'btn-history-action';
        btnReveal.title = 'Mở File Explorer và chọn tệp video';
        btnReveal.innerHTML = '📁';
        btnReveal.style.cssText = 'padding: 5px 8px; font-size: 12px; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 6px; cursor: pointer;';
        btnReveal.addEventListener('click', () => handleRevealFolder(item.id));

        // Nút Copy
        const btnCopy = document.createElement('button');
        btnCopy.type = 'button';
        btnCopy.className = 'btn-history-action';
        btnCopy.title = 'Sao chép đường dẫn đầy đủ vào bộ nhớ tạm';
        btnCopy.innerHTML = '📋';
        btnCopy.style.cssText = 'padding: 5px 8px; font-size: 12px; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 6px; cursor: pointer;';
        btnCopy.addEventListener('click', () => handleCopyPath(item.output_path));

        // Nút Chi tiết
        const btnDetail = document.createElement('button');
        btnDetail.type = 'button';
        btnDetail.className = 'btn-history-action';
        btnDetail.title = 'Xem chi tiết thông số kỹ thuật';
        btnDetail.innerHTML = 'ℹ️';
        btnDetail.style.cssText = 'padding: 5px 8px; font-size: 12px; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 6px; cursor: pointer;';
        btnDetail.addEventListener('click', () => handleShowDetail(item));

        // Nút Xóa
        const btnDel = document.createElement('button');
        btnDel.type = 'button';
        btnDel.className = 'btn-history-action';
        btnDel.title = 'Xóa bản ghi này khỏi lịch sử (không xóa file trên đĩa)';
        btnDel.innerHTML = '🗑';
        btnDel.style.cssText = 'padding: 5px 8px; font-size: 12px; background: #ef444422; color: #f87171; border: 1px solid #ef444444; border-radius: 6px; cursor: pointer;';
        btnDel.addEventListener('click', () => handleOpenDeleteModal(item.id, item.filename));

        actionsCol.appendChild(btnOpen);
        actionsCol.appendChild(btnReveal);
        actionsCol.appendChild(btnCopy);
        actionsCol.appendChild(btnDetail);
        actionsCol.appendChild(btnDel);
        row.appendChild(actionsCol);

        tableBody.appendChild(row);
    });
}

function updatePaginationUI() {
    const lblCount = document.getElementById('lblExportCountInfo');
    const btnPrev = document.getElementById('btnExportPrevPage');
    const btnNext = document.getElementById('btnExportNextPage');

    if (lblCount) {
        lblCount.textContent = `Trang ${currentPage} / ${Math.max(1, totalPages)} (Tổng cộng ${totalCount} video)`;
    }
    if (btnPrev) {
        btnPrev.disabled = currentPage <= 1;
        btnPrev.style.opacity = currentPage <= 1 ? '0.5' : '1';
        btnPrev.style.cursor = currentPage <= 1 ? 'not-allowed' : 'pointer';
    }
    if (btnNext) {
        btnNext.disabled = currentPage >= totalPages;
        btnNext.style.opacity = currentPage >= totalPages ? '0.5' : '1';
        btnNext.style.cursor = currentPage >= totalPages ? 'not-allowed' : 'pointer';
    }
}

/**
 * Thao tác mở video bằng hệ thống
 */
async function handleOpenVideo(id) {
    try {
        const res = await fetch(`/api/export-history/${id}/open`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            showAlertModal({
                title: 'Không Thể Mở Video',
                message: data.message || 'Tệp video không tồn tại hoặc không thể mở được.',
                theme: 'warning'
            });
            return;
        }
        showToast('Đang phát video...', 'success');
    } catch (e) {
        showToast(`Lỗi khi mở video: ${e.message}`, 'error');
    }
}

/**
 * Thao tác mở thư mục và chọn video
 */
async function handleRevealFolder(id) {
    try {
        const res = await fetch(`/api/export-history/${id}/reveal`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            showAlertModal({
                title: 'Không Thể Mở Thư Mục',
                message: data.message || 'Thư mục không tồn tại trên ổ đĩa.',
                theme: 'warning'
            });
            return;
        }
        showToast(data.message || 'Đã mở thư mục trong Explorer', 'info');
    } catch (e) {
        showToast(`Lỗi khi mở thư mục: ${e.message}`, 'error');
    }
}

/**
 * Sao chép đường dẫn
 */
async function handleCopyPath(path) {
    if (!path) return;
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(path);
        } else {
            const ta = document.createElement('textarea');
            ta.value = path;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
        showToast('Đã sao chép đường dẫn video!', 'success');
    } catch (e) {
        showToast('Không thể sao chép đường dẫn', 'error');
    }
}

/**
 * Mở modal chi tiết
 */
function handleShowDetail(item) {
    currentDetailItem = item;
    const modal = document.getElementById('exportDetailModal');
    if (!modal) return;

    document.getElementById('dtlExportId').textContent = String(item.id || '');
    document.getElementById('dtlExportName').textContent = item.filename || '';
    document.getElementById('dtlExportPath').textContent = item.output_path || '';
    document.getElementById('dtlExportTool').textContent = item.source_tool || '';
    document.getElementById('dtlExportOrigin').textContent = item.origin === 'import' ? 'Nhập từ thư mục' : 'Xuất từ hệ thống';
    document.getElementById('dtlExportSize').textContent = `${formatBytes(item.file_size_bytes)} (${(item.file_size_bytes || 0).toLocaleString()} bytes)`;
    document.getElementById('dtlExportCompleted').textContent = item.completed_at ? formatDateTime(item.completed_at) : 'Không xác định (Import)';
    document.getElementById('dtlExportCreated').textContent = formatDateTime(item.created_at);
    document.getElementById('dtlExportEventKey').textContent = item.event_key || '';

    let paramsStr = '{}';
    try {
        paramsStr = typeof item.params_json === 'string' ? item.params_json : JSON.stringify(item.params_json || {}, null, 2);
    } catch (e) {
        paramsStr = String(item.params_json || '');
    }
    document.getElementById('dtlExportParams').textContent = paramsStr;

    modal.style.display = 'flex';
}

/**
 * Mở modal xác nhận xóa
 */
function handleOpenDeleteModal(id, filename) {
    pendingDeleteId = id;
    const modal = document.getElementById('exportDeleteModal');
    const nameEl = document.getElementById('exportDeleteFileName');
    if (nameEl) nameEl.textContent = filename || 'video này';
    if (modal) modal.style.display = 'flex';
}

/**
 * Thực hiện xóa record khỏi DB
 */
async function executeDeleteRecord() {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    const modal = document.getElementById('exportDeleteModal');
    if (modal) modal.style.display = 'none';

    try {
        const res = await fetch(`/api/export-history/${id}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            showToast(data.message || 'Không thể xóa bản ghi', 'error');
            return;
        }
        showToast('Đã xóa bản ghi lịch sử', 'success');
        loadExportHistory(currentPage);
    } catch (e) {
        showToast(`Lỗi khi xóa: ${e.message}`, 'error');
    } finally {
        pendingDeleteId = null;
    }
}

/**
 * Xóa toàn bộ lịch sử
 */
async function handleClearAllHistory() {
    const confirmed = await showConfirmModal(
        '🗑️ Xóa Toàn Bộ Lịch Sử',
        `Bạn có chắc chắn muốn xóa toàn bộ ${totalCount} bản ghi lịch sử xuất video không?\n\n⚠️ Thao tác này không thể hoàn tác. Các tệp video trên ổ đĩa sẽ KHÔNG bị xóa.`
    );
    if (!confirmed) return;

    try {
        const res = await fetch('/api/export-history', { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            showToast(data.message || 'Không thể xóa lịch sử', 'error');
            return;
        }
        showToast(`✅ Đã xóa ${data.deleted_count ?? totalCount} bản ghi lịch sử!`, 'success');
        loadExportHistory(1);
    } catch (e) {
        showToast(`Lỗi khi xóa: ${e.message}`, 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// IMPORT WORKFLOW (Scan -> Preview Candidates -> Commit)
// ─────────────────────────────────────────────────────────────────────────────

function openImportModal() {
    const modal = document.getElementById('exportImportModal');
    if (!modal) return;

    resetImportModalState();
    modal.style.display = 'flex';
}

function closeImportModal() {
    const modal = document.getElementById('exportImportModal');
    if (modal) modal.style.display = 'none';
    if (scanPollInterval) {
        clearInterval(scanPollInterval);
        scanPollInterval = null;
    }
}

function resetImportModalState() {
    activeScanId = null;
    currentCandidates = [];
    if (scanPollInterval) {
        clearInterval(scanPollInterval);
        scanPollInterval = null;
    }
    const txtFolder = document.getElementById('txtImportFolder');
    const chkRec = document.getElementById('chkImportRecursive');
    const scanProgress = document.getElementById('importScanProgressWrapper');
    const previewContainer = document.getElementById('importCandidatesContainer');
    const btnCommit = document.getElementById('btnCommitImport');
    const btnStart = document.getElementById('btnStartImportScan');
    const btnCancel = document.getElementById('btnCancelImportScan');

    if (scanProgress) scanProgress.style.display = 'none';
    if (previewContainer) previewContainer.style.display = 'none';
    if (btnCommit) {
        btnCommit.style.display = 'none';
        btnCommit.disabled = true;
    }
    if (btnStart) {
        btnStart.style.display = 'inline-flex';
        btnStart.disabled = false;
    }
    if (btnCancel) btnCancel.style.display = 'none';
}

async function handleBrowseImportFolder() {
    try {
        if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.select_output_directory === 'function') {
            const folder = await window.pywebview.api.select_output_directory();
            if (folder) {
                const txt = document.getElementById('txtImportFolder');
                if (txt) txt.value = folder;
            }
        } else {
            showToast('Hãy dán trực tiếp đường dẫn thư mục vào ô bên dưới', 'info');
        }
    } catch (e) {
        console.warn('Lỗi mở hộp thoại chọn thư mục:', e);
    }
}

async function handleStartImportScan() {
    const folder = document.getElementById('txtImportFolder')?.value?.trim();
    if (!folder) {
        showToast('Vui lòng nhập hoặc chọn thư mục video cần quét', 'warning');
        return;
    }

    const recursive = Boolean(document.getElementById('chkImportRecursive')?.checked);
    const scanProgress = document.getElementById('importScanProgressWrapper');
    const previewContainer = document.getElementById('importCandidatesContainer');
    const statusText = document.getElementById('importScanStatusText');
    const btnStart = document.getElementById('btnStartImportScan');
    const btnCancel = document.getElementById('btnCancelImportScan');
    const btnCommit = document.getElementById('btnCommitImport');

    if (scanProgress) scanProgress.style.display = 'flex';
    if (previewContainer) previewContainer.style.display = 'none';
    if (statusText) statusText.textContent = 'Đang bắt đầu quét thư mục...';
    if (btnStart) btnStart.style.display = 'none';
    if (btnCancel) btnCancel.style.display = 'inline-flex';
    if (btnCommit) btnCommit.style.display = 'none';

    try {
        const res = await fetch('/api/export-history/import/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder_path: folder,
                include_subfolders: recursive
            })
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Không thể bắt đầu quét thư mục');
        }

        activeScanId = data.scan_id;
        pollImportProgress(activeScanId);
    } catch (e) {
        showToast(e.message, 'error');
        resetImportModalState();
    }
}

function pollImportProgress(scanId) {
    if (scanPollInterval) clearInterval(scanPollInterval);

    scanPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/export-history/import/scan/${scanId}`);
            if (!res.ok) return;
            const data = await res.json();
            if (!data.success || !data.scan) return;

            const scan = data.scan;
            const statusText = document.getElementById('importScanStatusText');
            if (statusText) {
                statusText.textContent = `Đang quét (${scan.scanned_count} tệp)... Đã tìm thấy ${scan.found_count} video hợp lệ`;
            }

            if (scan.status === 'completed') {
                clearInterval(scanPollInterval);
                scanPollInterval = null;
                onScanCompleted(scan);
            } else if (scan.status === 'failed' || scan.status === 'cancelled') {
                clearInterval(scanPollInterval);
                scanPollInterval = null;
                showToast(scan.error || 'Quá trình quét đã bị dừng', 'warning');
                resetImportModalState();
            }
        } catch (e) {
            console.error('Lỗi kiểm tra tiến độ quét:', e);
        }
    }, 500);
}

async function handleCancelImportScan() {
    if (!activeScanId) return;
    try {
        await fetch(`/api/export-history/import/scan/${activeScanId}/cancel`, { method: 'POST' });
        showToast('Đã gửi yêu cầu hủy quét', 'info');
    } catch (e) {
        // ignore
    }
}

function onScanCompleted(scan) {
    const scanProgress = document.getElementById('importScanProgressWrapper');
    const previewContainer = document.getElementById('importCandidatesContainer');
    const btnStart = document.getElementById('btnStartImportScan');
    const btnCancel = document.getElementById('btnCancelImportScan');
    const btnCommit = document.getElementById('btnCommitImport');
    const summaryText = document.getElementById('importCandidatesSummary');

    if (scanProgress) scanProgress.style.display = 'none';
    if (btnStart) btnStart.style.display = 'inline-flex';
    if (btnCancel) btnCancel.style.display = 'none';

    currentCandidates = scan.candidates || [];

    if (previewContainer) previewContainer.style.display = 'flex';

    const newCandidates = currentCandidates.filter(c => !c.already_exists);
    const existingCount = currentCandidates.length - newCandidates.length;

    if (summaryText) {
        summaryText.textContent = `Tìm thấy ${currentCandidates.length} video (${newCandidates.length} video mới sẵn sàng nhập, ${existingCount} video đã có trong lịch sử).`;
    }

    renderImportCandidateList(currentCandidates);

    if (btnCommit) {
        btnCommit.style.display = 'inline-flex';
        updateImportCommitButtonState();
    }
}

function renderImportCandidateList(candidates) {
    const listBody = document.getElementById('importCandidatesListBody');
    if (!listBody) return;
    listBody.innerHTML = '';

    if (candidates.length === 0) {
        const emptyRow = document.createElement('div');
        emptyRow.style.cssText = 'padding: 24px; text-align: center; color: #9ca3af; font-size: 13px;';
        emptyRow.textContent = 'Không tìm thấy tệp video nào trong thư mục này.';
        listBody.appendChild(emptyRow);
        return;
    }

    candidates.forEach((cand, idx) => {
        const itemRow = document.createElement('div');
        itemRow.style.cssText = `
            display: grid;
            grid-template-columns: 36px 1fr 90px 140px 110px;
            gap: 10px;
            align-items: center;
            padding: 8px 12px;
            border-bottom: 1px solid #1e293b;
            background: ${idx % 2 === 0 ? '#0f172a' : '#0b1120'};
            font-size: 12px;
        `;

        // Checkbox
        const chkCol = document.createElement('div');
        chkCol.style.textAlign = 'center';
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.className = 'import-candidate-chk';
        chk.dataset.index = String(idx);
        chk.checked = !cand.already_exists;
        chk.disabled = cand.already_exists;
        chk.style.cssText = 'accent-color: #0ea5e9; width: 15px; height: 15px; cursor: pointer;';
        chk.addEventListener('change', updateImportCommitButtonState);
        chkCol.appendChild(chk);
        itemRow.appendChild(chkCol);

        // Name & Path (an toàn tuyệt đối bằng textContent)
        const infoCol = document.createElement('div');
        infoCol.style.cssText = 'min-width: 0; display: flex; flex-direction: column; gap: 2px;';
        const nameEl = document.createElement('div');
        nameEl.style.cssText = 'font-weight: 600; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
        nameEl.textContent = cand.filename;
        const pathEl = document.createElement('div');
        pathEl.style.cssText = 'font-size: 10.5px; color: #94a3b8; font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
        pathEl.textContent = cand.output_path;
        infoCol.appendChild(nameEl);
        infoCol.appendChild(pathEl);
        itemRow.appendChild(infoCol);

        // Size
        const sizeCol = document.createElement('div');
        sizeCol.style.cssText = 'color: #cbd5e1; font-weight: 600;';
        sizeCol.textContent = formatBytes(cand.file_size_bytes);
        itemRow.appendChild(sizeCol);

        // Modified time
        const mtimeCol = document.createElement('div');
        mtimeCol.style.cssText = 'color: #94a3b8; font-size: 11px;';
        mtimeCol.textContent = formatDateTime(cand.mtime_iso);
        itemRow.appendChild(mtimeCol);

        // Status Badge
        const statusCol = document.createElement('div');
        const badge = document.createElement('span');
        badge.style.cssText = 'font-size: 10.5px; font-weight: 700; padding: 2px 6px; border-radius: 4px;';
        if (cand.already_exists) {
            badge.style.background = '#334155';
            badge.style.color = '#94a3b8';
            badge.textContent = 'Đã có trong DB';
        } else {
            badge.style.background = '#0ea5e922';
            badge.style.color = '#38bdf8';
            badge.style.border = '1px solid #0ea5e944';
            badge.textContent = 'Mới phát hiện';
        }
        statusCol.appendChild(badge);
        itemRow.appendChild(statusCol);

        listBody.appendChild(itemRow);
    });
}

function updateImportCommitButtonState() {
    const checkboxes = document.querySelectorAll('.import-candidate-chk:checked');
    const btnCommit = document.getElementById('btnCommitImport');
    if (btnCommit) {
        btnCommit.disabled = checkboxes.length === 0;
        btnCommit.textContent = `📥 Nhập ${checkboxes.length} video đã chọn`;
    }
}

async function handleCommitImport() {
    const checkboxes = document.querySelectorAll('.import-candidate-chk:checked');
    if (checkboxes.length === 0) {
        showToast('Vui lòng chọn ít nhất 1 video để nhập', 'warning');
        return;
    }

    const selectedCandidates = [];
    checkboxes.forEach(cb => {
        const idx = parseInt(cb.dataset.index, 10);
        if (currentCandidates[idx]) {
            selectedCandidates.push(currentCandidates[idx]);
        }
    });

    const btnCommit = document.getElementById('btnCommitImport');
    if (btnCommit) {
        btnCommit.disabled = true;
        btnCommit.textContent = 'Đang lưu vào lịch sử...';
    }

    try {
        const res = await fetch('/api/export-history/import/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scan_id: activeScanId,
                selected_candidates: selectedCandidates
            })
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Không thể lưu video đã nhập');
        }

        showToast(`Đã nhập thành công ${data.imported_count} video vào lịch sử!`, 'success');
        closeImportModal();
        loadExportHistory(1);
    } catch (e) {
        showToast(e.message, 'error');
        if (btnCommit) {
            btnCommit.disabled = false;
            updateImportCommitButtonState();
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────────────────────

function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDateTime(isoString) {
    if (!isoString) return '--';
    try {
        const dt = new Date(isoString);
        if (isNaN(dt.getTime())) return String(isoString);
        const y = dt.getFullYear();
        const m = String(dt.getMonth() + 1).padStart(2, '0');
        const d = String(dt.getDate()).padStart(2, '0');
        const hh = String(dt.getHours()).padStart(2, '0');
        const mm = String(dt.getMinutes()).padStart(2, '0');
        const ss = String(dt.getSeconds()).padStart(2, '0');
        return `${d}/${m}/${y} ${hh}:${mm}:${ss}`;
    } catch (e) {
        return String(isoString);
    }
}
