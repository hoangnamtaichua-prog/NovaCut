/**
 * Batch Processing Queue Feature Controller (Overnight Batch Engine)
 * NovaCut - AI Video & Review Editor
 */

import { escapeHtml, safeHttpUrl } from '../utils.js';

let batchEventSource = null;
let currentBatchState = {
    is_running: false,
    is_paused: false,
    current_task_id: null,
    auto_shutdown_pc: false,
    default_output_dir: 'output/batch',
    stats: { total: 0, completed: 0, failed: 0, pending: 0, running: 0 },
    tasks: []
};

let selectedLocalFiles = [];

export function initBatchQueueModule() {
    setupIngestionUI();
    setupControlsUI();
    setupDouyinIntegration();
    connectBatchEventStream();
}

// -------------------------------------------------------------
// 1. SETUP INGESTION & PRESET UI
// -------------------------------------------------------------
function setupIngestionUI() {
    const tabUrl = document.getElementById('btnBatchSourceUrlTab');
    const tabFile = document.getElementById('btnBatchSourceFileTab');
    const panelUrl = document.getElementById('batchPanelUrl');
    const panelFile = document.getElementById('batchPanelFile');
    const inputUrls = document.getElementById('batchInputUrls');
    const urlCountBadge = document.getElementById('batchUrlCountBadge');

    if (tabUrl && tabFile && panelUrl && panelFile) {
        tabUrl.addEventListener('click', () => {
            tabUrl.style.background = '#1e293b';
            tabUrl.style.color = '#38bdf8';
            tabUrl.style.border = '1px solid rgba(56, 189, 248, 0.4)';
            tabFile.style.background = 'transparent';
            tabFile.style.color = '#94a3b8';
            tabFile.style.border = 'none';
            panelUrl.style.display = 'flex';
            panelFile.style.display = 'none';
        });

        tabFile.addEventListener('click', () => {
            tabFile.style.background = '#1e293b';
            tabFile.style.color = '#38bdf8';
            tabFile.style.border = '1px solid rgba(56, 189, 248, 0.4)';
            tabUrl.style.background = 'transparent';
            tabUrl.style.color = '#94a3b8';
            tabUrl.style.border = 'none';
            panelFile.style.display = 'flex';
            panelUrl.style.display = 'none';
        });
    }

    if (inputUrls && urlCountBadge) {
        inputUrls.addEventListener('input', () => {
            const raw = inputUrls.value.trim();
            if (!raw) {
                urlCountBadge.textContent = '0 link';
                return;
            }
            const lines = raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            urlCountBadge.textContent = `${lines.length} link`;
        });
    }

    // Select Folder
    const btnSelectFolder = document.getElementById('btnSelectBatchFolder');
    const folderInput = document.getElementById('batchFolderInputPath');
    if (btnSelectFolder && folderInput) {
        btnSelectFolder.addEventListener('click', async () => {
            if (window.selectDirectory) {
                const dir = await window.selectDirectory();
                if (dir) {
                    folderInput.value = dir;
                    selectedLocalFiles = [dir];
                    const summary = document.getElementById('batchLocalFilesSummary');
                    if (summary) {
                        summary.style.display = 'block';
                        summary.textContent = `📁 Đã chọn thư mục: ${dir}`;
                    }
                }
            }
        });
    }

    // Select Output Dir
    const btnSelectOutputDir = document.getElementById('btnSelectBatchOutputDir');
    const outputDirInput = document.getElementById('batchOutputDirPath');
    if (btnSelectOutputDir && outputDirInput) {
        btnSelectOutputDir.addEventListener('click', async () => {
            if (window.selectDirectory) {
                const dir = await window.selectDirectory();
                if (dir) {
                    outputDirInput.value = dir;
                    await fetch('/api/batch/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ default_output_dir: dir })
                    });
                }
            }
        });
    }

    // Preset Selector Change Listener
    const selectPreset = document.getElementById('batchSelectPreset');
    const reviewStyleRow = document.getElementById('batchReviewStyleRow');
    if (selectPreset && reviewStyleRow) {
        selectPreset.addEventListener('change', () => {
            reviewStyleRow.style.display = (selectPreset.value === 'review') ? 'block' : 'none';
        });
    }

    // Add To Queue Button
    const btnAdd = document.getElementById('btnBatchAddToQueue');
    if (btnAdd) {
        btnAdd.addEventListener('click', async () => {
            await handleAddTasksToQueue();
        });
    }
}

async function handleAddTasksToQueue() {
    if (typeof window.checkFeaturePermission === 'function') {
        if (!window.checkFeaturePermission('can_access_batch', 'Xử Lý Hàng Loạt (Dành Riêng Cho Admin)')) return;
    }
    const isUrlMode = document.getElementById('batchPanelUrl').style.display !== 'none';
    let items = [];

    if (isUrlMode) {
        const text = (document.getElementById('batchInputUrls').value || '').trim();
        if (!text) {
            window.showToast?.('⚠️ Vui lòng dán ít nhất 1 liên kết video URL!', 'warning');
            return;
        }
        items = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    } else {
        const folder = (document.getElementById('batchFolderInputPath').value || '').trim();
        if (folder) {
            items = [folder];
        } else if (selectedLocalFiles.length > 0) {
            items = selectedLocalFiles;
        } else {
            window.showToast?.('⚠️ Vui lòng chọn một thư mục hoặc file video trên máy!', 'warning');
            return;
        }
    }

    if (items.length === 0) {
        window.showToast?.('⚠️ Không có dữ liệu video hợp lệ để thêm vào hàng đợi.', 'warning');
        return;
    }

    const preset = document.getElementById('batchSelectPreset')?.value || 'review';
    const voice_id = document.getElementById('batchSelectVoice')?.value || 'ngoc_huyen';
    const aspect_ratio = document.getElementById('batchSelectAspect')?.value || '9:16';
    const auto_subtitles = document.getElementById('batchChkAutoSubtitles')?.checked !== false;
    const review_style = document.getElementById('batchSelectReviewStyle')?.value || 'dramatic';
    const output_dir = (document.getElementById('batchOutputDirPath')?.value || '').trim();

    const preset_config = {
        voice_id,
        aspect_ratio,
        auto_subtitles,
        review_style,
        output_dir: output_dir || undefined
    };

    try {
        const res = await fetch('/api/batch/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                items,
                preset,
                preset_config
            })
        });

        const data = await res.json();
        if (!res.ok) {
            if (res.status === 403) {
                window.showAlertModal?.({
                    title: '🔒 Giới Hạn Bản Quyền',
                    message: data.error || 'Tính năng Hàng Đợi Xử Lý yêu cầu kích hoạt bản quyền gói Pro/VIP!',
                    theme: 'warning'
                });
                return;
            }
            throw new Error(data.error || `HTTP ${res.status}`);
        }

        window.showToast?.(`✅ Đã thêm thành công ${data.added_count} video vào Hàng Đợi!`, 'success');
        
        // Reset URL input if url mode
        if (isUrlMode) {
            document.getElementById('batchInputUrls').value = '';
            document.getElementById('batchUrlCountBadge').textContent = '0 link';
        }

        if (data.state) {
            updateBatchUI(data.state);
        }
    } catch (err) {
        window.showToast?.(`🛑 Lỗi nạp hàng đợi: ${err.message}`, 'error');
    }
}

// -------------------------------------------------------------
// 2. SETUP CONTROLS UI (START / PAUSE / STOP / RETRY / CLEAR)
// -------------------------------------------------------------
function setupControlsUI() {
    const btnStart = document.getElementById('btnBatchStartQueue');
    const btnPause = document.getElementById('btnBatchPauseQueue');
    const btnStop = document.getElementById('btnBatchStopQueue');
    const btnRetryFailed = document.getElementById('btnBatchRetryFailed');
    const btnClearCompleted = document.getElementById('btnBatchClearCompleted');
    const btnClearAll = document.getElementById('btnBatchClearAll');
    const btnOpenFolder = document.getElementById('btnBatchOpenOutputFolder');
    const chkShutdown = document.getElementById('batchChkAutoShutdown');

    if (btnStart) {
        btnStart.addEventListener('click', async () => {
            if (typeof window.checkFeaturePermission === 'function') {
                if (!window.checkFeaturePermission('can_access_batch', 'Xử Lý Hàng Loạt (Dành Riêng Cho Admin)')) return;
            }
            try {
                const res = await fetch('/api/batch/start', { method: 'POST' });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    if (res.status === 403) {
                        window.showAlertModal?.({
                            title: '🔒 Giới Hạn Bản Quyền',
                            message: data.error || 'Vui lòng kích hoạt bản quyền để bắt đầu chạy hàng đợi!',
                            theme: 'warning'
                        });
                        return;
                    }
                    throw new Error(data.error || 'Không thể bắt đầu');
                }
                window.showToast?.('🚀 Đã kích hoạt Hàng Đợi xử lý video tự động!', 'success');
            } catch (err) {
                window.showToast?.(`🛑 Lỗi: ${err.message}`, 'error');
            }
        });
    }

    if (btnPause) {
        btnPause.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/batch/pause', { method: 'POST' });
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'Không thể tạm dừng');
                window.showToast?.('⏸️ Đã tạm dừng hàng đợi.', 'info');
            } catch (err) { window.showToast?.(`🛑 ${err.message}`, 'error'); }
        });
    }

    if (btnStop) {
        btnStop.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/batch/stop', { method: 'POST' });
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'Không thể dừng');
                window.showToast?.('⏹️ Đã dừng hoàn toàn hàng đợi.', 'warning');
            } catch (err) { window.showToast?.(`🛑 ${err.message}`, 'error'); }
        });
    }

    if (btnRetryFailed) {
        btnRetryFailed.addEventListener('click', async () => {
            const res = await fetch('/api/batch/retry', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
            const data = await res.json();
            window.showToast?.(`🔄 Đã đưa ${data.retried_count || 0} tác vụ lỗi trở lại hàng đợi!`, 'info');
        });
    }

    if (btnClearCompleted) {
        btnClearCompleted.addEventListener('click', async () => {
            await fetch('/api/batch/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completed_only: true }) });
            window.showToast?.('🧹 Đã dọn sạch các video đã hoàn thành.', 'info');
        });
    }

    if (btnClearAll) {
        btnClearAll.addEventListener('click', async () => {
            const confirmed = await window.showConfirmModal?.({
                title: 'Xóa toàn bộ hàng đợi?',
                message: 'Thao tác này sẽ xóa toàn bộ tác vụ đang chờ.',
                confirmText: 'Xóa toàn bộ',
                confirmType: 'danger'
            });
            if (confirmed) {
                try {
                    const res = await fetch('/api/batch/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completed_only: false }) });
                    const data = await res.json();
                    if (!res.ok || !data.success) throw new Error(data.error || 'Không thể xóa hàng đợi');
                    window.showToast?.('🗑️ Đã xóa toàn bộ hàng đợi.', 'info');
                } catch (err) { window.showToast?.(`🛑 ${err.message}`, 'error'); }
            }
        });
    }

    if (btnOpenFolder) {
        btnOpenFolder.addEventListener('click', async () => {
            const outDir = document.getElementById('batchOutputDirPath')?.value || '';
            await fetch('/api/batch/open_output', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: outDir })
            });
        });
    }

    if (chkShutdown) {
        chkShutdown.addEventListener('change', async (e) => {
            await fetch('/api/batch/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_shutdown_pc: e.target.checked })
            });
            if (e.target.checked) {
                window.showToast?.('🌙 Chế độ tự động tắt máy tính (Shutdown PC) đã được BẬT.', 'warning');
            } else {
                window.showToast?.('☀️ Đã TẮT chế độ tự động tắt máy tính.', 'info');
            }
        });
    }
}

// -------------------------------------------------------------
// 3. INTEGRATION WITH DOUYIN CHANNEL DOWNLOADER
// -------------------------------------------------------------
function setupDouyinIntegration() {
    const btnSend = document.getElementById('btnSendDouyinToBatchQueue');
    if (!btnSend) return;

    btnSend.addEventListener('click', async () => {
        const checkedBoxes = document.querySelectorAll('#douyinChannelGrid input[type="checkbox"]:checked');
        if (checkedBoxes.length === 0) {
            window.showToast?.('⚠️ Vui lòng tích chọn ít nhất 1 video Douyin từ danh sách kênh!', 'warning');
            return;
        }

        const items = [];
        checkedBoxes.forEach(chk => {
            const raw = chk.value || chk.dataset.url;
            if (raw) items.push(raw);
        });

        if (items.length === 0) {
            window.showToast?.('⚠️ Không tìm thấy URL của các video đã chọn.', 'warning');
            return;
        }

        try {
            const res = await fetch('/api/batch/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    items,
                    preset: 'review',
                    preset_config: { aspect_ratio: '9:16', auto_subtitles: true }
                })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Lỗi thêm vào hàng đợi');

            window.showToast?.(`⚡ Đã chuyển ${data.added_count} video Douyin sang Hàng Đợi Xử Lý!`, 'success');

            // Switch to Batch Queue Tab
            const batchTabBtn = document.querySelector('.header-tabs button[data-target="viewBatchQueue"]');
            if (batchTabBtn) batchTabBtn.click();

        } catch (err) {
            window.showToast?.(`🛑 Lỗi: ${err.message}`, 'error');
        }
    });
}

// -------------------------------------------------------------
// 4. SSE REALTIME EVENT STREAM & UI DISPATCHER
// -------------------------------------------------------------
function connectBatchEventStream() {
    if (batchEventSource) {
        batchEventSource.close();
    }

    try {
        batchEventSource = new EventSource('/api/batch/stream');

        batchEventSource.onmessage = (e) => {
            try {
                const payload = JSON.parse(e.data);
                if (payload.event === 'initial_state' || payload.event === 'queue_updated') {
                    updateBatchUI(payload.data);
                } else if (payload.event === 'task_progress') {
                    updateTaskProgressRow(payload.data);
                } else if (payload.event === 'task_started' || payload.event === 'task_finished' || payload.event === 'task_status_changed') {
                    fetchCurrentBatchState();
                } else if (payload.event === 'shutdown_countdown') {
                    window.showConfirmModal?.({
                        title: '🌙 Máy tính sẽ tắt sau 60 giây',
                        message: 'Chọn “Tiếp tục làm việc” để hủy lịch tắt máy.',
                        confirmText: 'Tiếp tục làm việc',
                        cancelText: 'Cho phép tắt máy',
                        confirmType: 'warning'
                    }).then(async (keepWorking) => {
                        if (!keepWorking) return;
                        try {
                            const res = await fetch('/api/batch/cancel_shutdown', { method: 'POST' });
                            const data = await res.json();
                            window.showToast?.(
                                data.success ? '☀️ Đã hủy lịch tắt máy.' : 'Không thể hủy lịch tắt máy.',
                                data.success ? 'success' : 'error'
                            );
                        } catch (err) {
                            window.showToast?.('Không thể kết nối máy chủ để hủy tắt máy.', 'error');
                        }
                    });
                }
            } catch (err) {
                // Ignore json parse error for heartbeats
            }
        };

        batchEventSource.onerror = () => {
            setTimeout(connectBatchEventStream, 5000);
        };
    } catch (err) {
        console.warn('Batch EventSource connection error:', err);
    }
}

async function fetchCurrentBatchState() {
    try {
        const res = await fetch('/api/batch/state');
        if (res.ok) {
            const state = await res.json();
            updateBatchUI(state);
        }
    } catch (err) {
        // Silent
    }
}

function updateBatchUI(state) {
    if (!state) return;
    currentBatchState = state;

    // Update KPIs
    const stats = state.stats || { total: 0, completed: 0, failed: 0, running: 0 };
    const kpiTotal = document.getElementById('batchKpiTotal');
    const kpiRunning = document.getElementById('batchKpiRunning');
    const kpiCompleted = document.getElementById('batchKpiCompleted');
    const kpiFailed = document.getElementById('batchKpiFailed');

    if (kpiTotal) kpiTotal.textContent = stats.total || 0;
    if (kpiRunning) kpiRunning.textContent = stats.running || 0;
    if (kpiCompleted) kpiCompleted.textContent = stats.completed || 0;
    if (kpiFailed) kpiFailed.textContent = stats.failed || 0;

    // Controls visibility & text
    const btnStart = document.getElementById('btnBatchStartQueue');
    const btnPause = document.getElementById('btnBatchPauseQueue');
    const btnStop = document.getElementById('btnBatchStopQueue');
    const footerStatus = document.getElementById('batchQueueFooterStatus');

    if (state.is_running) {
        if (btnStart) btnStart.style.display = 'none';
        if (btnPause) {
            btnPause.style.display = 'flex';
            btnPause.innerHTML = state.is_paused ? '<span>▶️</span> <span>Tiếp Tục</span>' : '<span>⏸️</span> <span>Tạm Dừng</span>';
        }
        if (btnStop) btnStop.style.display = 'flex';
        if (footerStatus) footerStatus.innerHTML = `<span style="color: #38bdf8; font-weight: 700;">⚡ Đang chạy hàng đợi (${stats.completed}/${stats.total} video)...</span>`;
    } else {
        if (btnStart) btnStart.style.display = 'flex';
        if (btnPause) btnPause.style.display = 'none';
        if (btnStop) btnStop.style.display = 'none';
        if (footerStatus) footerStatus.textContent = stats.total > 0 ? `Đã dừng (${stats.completed}/${stats.total} hoàn tất)` : 'Trạng thái: Sẵn sàng';
    }

    // Auto Shutdown checkbox
    const chkShutdown = document.getElementById('batchChkAutoShutdown');
    if (chkShutdown) chkShutdown.checked = Boolean(state.auto_shutdown_pc);

    // Default output dir
    const outDirInput = document.getElementById('batchOutputDirPath');
    if (outDirInput && state.default_output_dir) {
        outDirInput.value = state.default_output_dir;
    }

    // Render Table
    renderQueueTable(state.tasks || []);
}

function renderQueueTable(tasks) {
    const tbody = document.getElementById('batchQueueTableBody');
    if (!tbody) return;

    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = `
            <div id="batchQueueEmptyNotice" style="padding: 60px 20px; text-align: center; color: #64748b; display: flex; flex-direction: column; align-items: center; gap: 12px;">
                <span style="font-size: 42px; opacity: 0.5;">📋</span>
                <div style="font-size: 15px; font-weight: 600; color: #94a3b8;">Hàng đợi hiện đang trống</div>
                <div style="font-size: 12.5px; max-width: 400px; line-height: 1.5;">Dán danh sách link Douyin/TikTok hoặc chọn thư mục video ở cột bên trái rồi bấm <strong>"Nạp Vào Hàng Đợi"</strong> để bắt đầu.</div>
            </div>
        `;
        return;
    }

    let html = '';
    tasks.forEach((task, idx) => {
        const isRunning = task.status === 'processing' || task.status === 'downloading';
        const isCompleted = task.status === 'completed';
        const isFailed = task.status === 'failed';
        const isCancelled = task.status === 'cancelled';

        let badgeBg = '#334155';
        let badgeColor = '#94a3b8';
        let badgeText = 'Chờ xử lý';

        if (isRunning) {
            badgeBg = 'rgba(14, 165, 233, 0.2)';
            badgeColor = '#38bdf8';
            badgeText = task.status === 'downloading' ? 'Đang tải video' : 'Đang biên tập AI';
        } else if (isCompleted) {
            badgeBg = 'rgba(16, 185, 129, 0.2)';
            badgeColor = '#10b981';
            badgeText = 'Hoàn thành 100%';
        } else if (isFailed) {
            badgeBg = 'rgba(239, 68, 68, 0.2)';
            badgeColor = '#f87171';
            badgeText = 'Lỗi';
        } else if (isCancelled) {
            badgeBg = 'rgba(245, 158, 11, 0.2)';
            badgeColor = '#fbbf24';
            badgeText = 'Đã hủy';
        }

        let presetLabel = '🍿 Review Phim';
        if (task.preset === 'dubbing') presetLabel = '🎙️ Lồng Tiếng';
        else if (task.preset === 'anti_copyright') presetLabel = '🛡️ Clean 9:16';

        const titleText = task.title || task.source_url || task.file_path || 'Video # ' + (idx + 1);
        const taskId = escapeHtml(task.id);
        const sourceText = task.source_type === 'url' ? task.source_url : (task.file_path || '');
        const stepText = task.current_step_text || 'Chờ lượt xử lý...';
        const progress = Math.max(0, Math.min(100, Number(task.progress) || 0));
        const thumbnailUrl = safeHttpUrl(task.thumbnail);

        html += `
            <div id="task_row_${taskId}" class="batch-task-row" style="display: grid; grid-template-columns: 40px 1fr 140px 220px 110px; gap: 12px; padding: 12px 18px; border-bottom: 1px solid rgba(51, 65, 85, 0.5); align-items: center; background: ${isRunning ? 'rgba(14, 165, 233, 0.04)' : 'transparent'}; transition: background 0.2s;">
                <!-- # Index -->
                <div style="text-align: center; font-family: monospace; font-size: 12px; color: ${isRunning ? '#38bdf8' : '#64748b'}; font-weight: 700;">
                    ${idx + 1}
                </div>

                <!-- Video Title / Info -->
                <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
                    <div style="width: 44px; height: 32px; border-radius: 6px; background: #0f172a; border: 1px solid #334155; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; overflow: hidden;">
                        ${thumbnailUrl ? `<img src="${escapeHtml(thumbnailUrl)}" alt="" style="width: 100%; height: 100%; object-fit: cover;">` : '🎬'}
                    </div>
                    <div style="min-width: 0; flex: 1;">
                        <div style="font-size: 13px; font-weight: 600; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(titleText)}">
                            ${escapeHtml(titleText)}
                        </div>
                        <div style="font-size: 11px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${escapeHtml(sourceText)}
                        </div>
                    </div>
                </div>

                <!-- Preset -->
                <div>
                    <span style="font-size: 11.5px; font-weight: 600; color: #c084fc; background: rgba(192, 132, 252, 0.1); border: 1px solid rgba(192, 132, 252, 0.3); padding: 3px 8px; border-radius: 6px;">
                        ${presetLabel}
                    </span>
                </div>

                <!-- Status & Progress Bar -->
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11.5px;">
                        <span style="font-weight: 700; color: ${badgeColor}; display: inline-flex; align-items: center; gap: 5px;">
                            ${isRunning ? '<span class="status-pulse-dot"></span>' : ''}
                            <span>${badgeText}</span>
                        </span>
                        <span id="task_pct_${taskId}" style="font-weight: 800; font-family: monospace; color: ${badgeColor};">${progress}%</span>
                    </div>
                    <div style="width: 100%; height: 6px; background: #0f172a; border-radius: 4px; overflow: hidden;">
                        <div id="task_bar_${taskId}" style="width: ${progress}%; height: 100%; background: ${isFailed ? '#ef4444' : isCompleted ? '#10b981' : 'linear-gradient(90deg, #0ea5e9, #38bdf8)'}; transition: width 0.3s ease;"></div>
                    </div>
                    <div id="task_step_${taskId}" style="font-size: 10.5px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(stepText)}">
                        ${escapeHtml(stepText)}
                    </div>
                </div>

                <!-- Actions -->
                <div style="display: flex; align-items: center; justify-content: center; gap: 6px;">
                    ${isCompleted && task.output_path ? `
                        <button class="btn secondary small batch-open-output" data-path="${escapeHtml(task.output_path)}" title="Mở file video thành phẩm" style="padding: 4px 8px; font-size: 11px; color: #10b981; border-color: rgba(16, 185, 129, 0.4);">
                            ▶️ Mở
                        </button>
                    ` : ''}
                    ${(isFailed || isCancelled) ? `
                        <button class="btn secondary small batch-retry-task" data-task-id="${taskId}" title="Thử lại tác vụ này" style="padding: 4px 8px; font-size: 11px; color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);">
                            🔄
                        </button>
                    ` : ''}
                    <button class="btn secondary small batch-remove-task" data-task-id="${taskId}" title="Xóa khỏi hàng đợi" style="padding: 4px 8px; font-size: 11px; color: #f87171; border-color: rgba(239, 68, 68, 0.3);">
                        ✕
                    </button>
                </div>
            </div>
        `;
    });

    tbody.innerHTML = html;
    tbody.querySelectorAll('.batch-open-output').forEach((button) => {
        button.addEventListener('click', () => window.openBatchOutputVideo(button.dataset.path));
    });
    tbody.querySelectorAll('.batch-retry-task').forEach((button) => {
        button.addEventListener('click', () => window.retryBatchTask(button.dataset.taskId));
    });
    tbody.querySelectorAll('.batch-remove-task').forEach((button) => {
        button.addEventListener('click', () => window.removeBatchTask(button.dataset.taskId));
    });
}

function updateTaskProgressRow(data) {
    if (!data || !data.id) return;
    const bar = document.getElementById(`task_bar_${data.id}`);
    const pct = document.getElementById(`task_pct_${data.id}`);
    const step = document.getElementById(`task_step_${data.id}`);

    if (bar) bar.style.width = `${data.progress || 0}%`;
    if (pct) pct.textContent = `${data.progress || 0}%`;
    if (step && data.current_step_text) {
        step.textContent = data.current_step_text;
        step.title = data.current_step_text;
    }
}

// Global actions exposed for inline onclicks
if (typeof window !== 'undefined') {
    window.retryBatchTask = async (taskId) => {
        try {
            const res = await fetch('/api/batch/retry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Không thể thử lại tác vụ');
            window.showToast?.('🔄 Đã đưa video trở lại hàng đợi!', 'info');
        } catch (err) {
            window.showToast?.(`🛑 ${err.message}`, 'error');
        }
    };

    window.removeBatchTask = async (taskId) => {
        try {
            const res = await fetch('/api/batch/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Không thể xóa tác vụ');
        } catch (err) {
            window.showToast?.(`🛑 ${err.message}`, 'error');
        }
    };

    window.openBatchOutputVideo = async (filePath) => {
        try {
            const res = await fetch('/api/batch/open_output', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath })
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Không thể mở video');
        } catch (err) {
            window.showToast?.(`🛑 ${err.message}`, 'error');
        }
    };
}
