import { loadCapCutDrafts } from './js/features/capcut.js';
import { initCloneVoiceModule, loadClonedVoicesList } from './js/features/clone_voice.js';
import { initBatchQueueModule } from './js/features/batch_queue.js';
import { initBatchEditorModule } from './js/features/batch_editor.js';
import { initVideoStudioSuite, videoStudioInstances } from './js/features/video_studio_suite.js';
import { initExportHistoryModule, loadExportHistory } from './js/features/export_history.js';
import './js/features/comic_review.js';
import { appendLog, showToast, showConfirmModal, showAlertModal, showPromptModal, formatTimeSec, parseTimeToSeconds, formatSrtTimestamp, formatDurationStr, escapeHtml, safeHttpUrl, timeNow } from './js/utils.js';

export let currentLicenseState = {
    is_valid: false,
    status: 'CHECKING',
    tier: 'unlicensed',
    plan_name: 'Đang kiểm tra...',
    badge_class: 'badge-unlicensed',
    badge_text: '🔒 Kiểm tra bản quyền...',
    features: {}
};

const terminal = document.getElementById('terminal');
const startBtn = document.getElementById('startBtn');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

const editorInputVideoPath = document.getElementById('editorInputVideoPath');
// reviewInputVideoPath already declared at top
const outputDirPath = document.getElementById('outputDirPath');
const outputFileName = document.getElementById('outputFileName');
const manualAudioPath = document.getElementById('manualAudioPath');
const manualSrtPath = document.getElementById('manualSrtPath');
const videoPlayer = document.getElementById('videoPlayer');
const videoPlaceholder = document.getElementById('videoPlaceholder');

let isGenerating = false;
let currentMode = 'api'; // 'api' or 'manual'

// Terminal Toggle
const terminalOverlay = document.getElementById('terminalOverlay');
const toggleTerminalBtn = document.getElementById('toggleTerminalBtn');
if (toggleTerminalBtn) {
    toggleTerminalBtn.addEventListener('click', () => {
        if (terminalOverlay) {
            if (terminalOverlay.classList.contains('collapsed')) {
                terminalOverlay.classList.remove('collapsed');
                terminalOverlay.classList.add('expanded');
                toggleTerminalBtn.textContent = 'Thu gọn';
            } else {
                terminalOverlay.classList.remove('expanded');
                terminalOverlay.classList.add('collapsed');
                toggleTerminalBtn.textContent = 'Mở rộng';
            }
        }
    });
}

// Main Navigation Tab Switching
const mainNavTabs = document.querySelectorAll('.header-tabs .nav-tab');
const mainViews = document.querySelectorAll('.main-view');

// Sidebar collapse state is persisted so the editor keeps the user's preferred workspace width.
const navRail = document.querySelector('.header-tabs');
if (navRail) {
    const collapseButton = document.createElement('button');
    collapseButton.type = 'button';
    collapseButton.className = 'nav-rail-toggle';
    collapseButton.title = 'Thu gọn / mở rộng thanh điều hướng';
    const updateToggleIcon = (isCollapsed) => {
        collapseButton.innerHTML = isCollapsed 
            ? `<svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none"><polyline points="9 18 15 12 9 6"></polyline></svg>`
            : `<svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none"><polyline points="15 18 9 12 15 6"></polyline></svg>`;
    };
    collapseButton.style.cssText = 'width:24px;height:24px;border:1px solid rgba(51,65,85,0.7);border-radius:6px;background:#0f172a;color:#94a3b8;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:20;transition:all 0.2s;box-shadow:0 2px 6px rgba(0,0,0,0.3);flex-shrink:0;';
    const brandHeader = document.getElementById('sidebarBrandHeader');
    if (brandHeader) {
        brandHeader.appendChild(collapseButton);
    } else {
        navRail.appendChild(collapseButton);
    }
    const collapsed = localStorage.getItem('novacut.navCollapsed') === '1';
    document.body.classList.toggle('nav-collapsed', collapsed);
    updateToggleIcon(collapsed);
    collapseButton.addEventListener('click', () => {
        const next = !document.body.classList.contains('nav-collapsed');
        document.body.classList.toggle('nav-collapsed', next);
        localStorage.setItem('novacut.navCollapsed', next ? '1' : '0');
        updateToggleIcon(next);
    });
}

mainNavTabs.forEach(tab => {
    tab.addEventListener('click', (e) => {
        const targetId = tab.getAttribute('data-target');

        // Kiểm tra phân quyền 1 trong 2 Module chính của Gói Pro (chỉ áp dụng cho Biên tập phim và Review Phim)
        if (currentLicenseState && currentLicenseState.status === 'ACTIVE' && currentLicenseState.tier === 'pro') {
            const proMod = currentLicenseState.pro_selected_module;
            if (targetId === 'viewEditor' || targetId === 'viewReview') {
                if (!proMod) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (typeof openProModuleRequiredModal === 'function') {
                        openProModuleRequiredModal(targetId === 'viewReview' ? 'review' : 'editor');
                    }
                    return;
                }
                if (targetId === 'viewEditor' && proMod === 'review') {
                    e.preventDefault();
                    e.stopPropagation();
                    showAlertModal({
                        title: '⭐ Đặc Quyền Gói Pro',
                        message: 'Gói Pro của bạn đã chọn cố định Module "Review Phim".\n\nĐể mở khóa và sử dụng đồng thời cả 2 Module (Biên tập phim & Review Phim), vui lòng Nâng cấp lên Gói VIP!',
                        theme: 'primary'
                    });
                    return;
                }
                if (targetId === 'viewReview' && proMod === 'editor') {
                    e.preventDefault();
                    e.stopPropagation();
                    showAlertModal({
                        title: '⭐ Đặc Quyền Gói Pro',
                        message: 'Gói Pro của bạn đã chọn cố định Module "Biên tập phim".\n\nĐể mở khóa và sử dụng đồng thời cả 2 Module (Biên tập phim & Review Phim), vui lòng Nâng cấp lên Gói VIP!',
                        theme: 'primary'
                    });
                    return;
                }
            }
        }

        // Kiểm tra phân quyền Xử Lý Hàng Loạt (Chỉ dành riêng cho Admin Quản Trị)
        if (targetId === 'viewBatchQueue') {
            if (typeof checkFeaturePermission === 'function') {
                if (!checkFeaturePermission('can_access_batch', 'Xử Lý Hàng Loạt (Dành Riêng Cho Admin)')) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }
            }
        }

        // Kiểm tra phân quyền Biên Tập Hàng Loạt
        if (targetId === 'viewBatchEditor') {
            if (typeof checkFeaturePermission === 'function') {
                if (!checkFeaturePermission('can_access_editor', 'Biên tập hàng loạt')) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }
            }
        }

        // Remove active from all tabs
        mainNavTabs.forEach(t => t.classList.remove('active'));
        // Add active to clicked tab
        tab.classList.add('active');
        
        // Hide all views
        mainViews.forEach(v => {
            v.classList.remove('active');
            v.style.display = 'none';
        });
        
        // Luôn hoàn trả cụm top-row về tab viewEditor nếu đang mở trong modal batch
        if (typeof window.returnTopRowToEditor === 'function') {
            window.returnTopRowToEditor();
        }

        // Pause players when leaving view
        if (targetId !== 'viewEditor') {
            const vp = document.getElementById('videoPlayer');
            if (vp && !vp.paused) vp.pause();
        }
        if (targetId !== 'viewBatchEditor') {
            const bmp = document.getElementById('batchModalPlayer');
            if (bmp && !bmp.paused) bmp.pause();
        }
        if (targetId !== 'viewReview') {
            const rvp = document.getElementById('reviewVideoPlayer');
            if (rvp && !rvp.paused) rvp.pause();
        }
        
        const targetView = document.getElementById(targetId);
        if (targetView) {
            targetView.classList.add('active');
            targetView.style.display = (targetId === 'viewEditor' || targetId === 'viewBatchEditor' || targetId === 'viewReview' || targetId === 'viewDownload' || targetId === 'viewCapCut' || targetId === 'viewCloneVoice' || targetId === 'viewExportHistory') ? 'block' : 'flex';
            
            // Special case for Editor
            if (targetId === 'viewEditor') {
                const mainLayout = targetView.querySelector('.main-layout');
                if (mainLayout) mainLayout.style.display = 'flex';
            }
            // Special case for CapCut
            if (targetId === 'viewCapCut') {
                loadCapCutDrafts(true);
            }
            // Special case for Clone Voice
            if (targetId === 'viewCloneVoice') {
                loadClonedVoicesList();
            }
            // Special case for Batch Editor
            if (targetId === 'viewBatchEditor') {
                if (typeof window.renderBatchTable === 'function') {
                    window.renderBatchTable();
                }
            }
            // Special case for Export History
            if (targetId === 'viewExportHistory') {
                loadExportHistory(1);
            }
        }
    });
});

// ====== AI DUBBING (LỒNG TIẾNG AI) CONTROLS ======
let currentDubbingMode = 'tts';

const tabDubbingTts = document.getElementById('tabDubbingTts');
const tabDubbingManual = document.getElementById('tabDubbingManual');
const dubbingTtsContent = document.getElementById('dubbingTtsContent');
const dubbingManualContent = document.getElementById('dubbingManualContent');
const dubbingEnabled = document.getElementById('dubbingEnabled');
const dubbingToggleLabel = document.getElementById('dubbingToggleLabel');
const dubbingCard = document.querySelector('.ai-dubbing-card');

if (tabDubbingTts && tabDubbingManual) {
    tabDubbingTts.addEventListener('click', () => {
        currentDubbingMode = 'tts';
        tabDubbingTts.classList.add('active');
        tabDubbingManual.classList.remove('active');
        dubbingTtsContent.classList.add('active');
        dubbingManualContent.classList.remove('active');
    });

    tabDubbingManual.addEventListener('click', () => {
        currentDubbingMode = 'manual';
        tabDubbingManual.classList.add('active');
        tabDubbingTts.classList.remove('active');
        dubbingManualContent.classList.add('active');
        dubbingTtsContent.classList.remove('active');
    });
}

if (dubbingEnabled) {
    dubbingEnabled.addEventListener('change', (e) => {
        if (e.target.checked) {
            if (dubbingToggleLabel) {
                dubbingToggleLabel.textContent = 'Bật';
                dubbingToggleLabel.style.color = '#38bdf8';
            }
            dubbingCard?.classList.remove('dubbing-disabled');
            // Cập nhật lại âm lượng gốc đã cấu hình cho video khi bật lồng tiếng
            const vPlayer = document.getElementById('videoPlayer');
            const isEditedMode = document.getElementById('btnPreviewEdited')?.classList.contains('active');
            if (vPlayer && isEditedMode) {
                const origVal = parseFloat(document.getElementById('dubbingOrigVol')?.value || 45);
                vPlayer.volume = Math.max(0, Math.min(1.0, origVal / 100));
            }
        } else {
            if (dubbingToggleLabel) {
                dubbingToggleLabel.textContent = 'Tắt';
                dubbingToggleLabel.style.color = '#94a3b8';
            }
            dubbingCard?.classList.add('dubbing-disabled');
            // Dừng ngay giọng đọc đang phát và khôi phục âm thanh gốc nguyên bản 100%
            if (window.liveDubbingEngine) {
                window.liveDubbingEngine.stop();
            }
            const vPlayer = document.getElementById('videoPlayer');
            if (vPlayer) {
                vPlayer.volume = 1.0;
            }
        }
    });
}

// Dubbing Sliders
const dubbingSpeed = document.getElementById('dubbingSpeed');
const dubbingSpeedVal = document.getElementById('dubbingSpeedVal');
if (dubbingSpeed && dubbingSpeedVal) {
    dubbingSpeed.addEventListener('input', (e) => {
        dubbingSpeedVal.textContent = parseFloat(e.target.value).toFixed(2) + 'x';
    });
}

const dubbingVoiceVol = document.getElementById('dubbingVoiceVol');
const dubbingVoiceVolVal = document.getElementById('dubbingVoiceVolVal');
if (dubbingVoiceVol && dubbingVoiceVolVal) {
    dubbingVoiceVol.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        dubbingVoiceVolVal.textContent = val + '%';
        // Điều chỉnh âm lượng giọng đọc thời gian thực nếu đang phát
        if (window.liveDubbingEngine && window.liveDubbingEngine.currentAudio) {
            window.liveDubbingEngine.currentAudio.volume = Math.max(0, Math.min(1.0, val / 100));
        }
    });
}

const dubbingOrigVol = document.getElementById('dubbingOrigVol');
const dubbingOrigVolVal = document.getElementById('dubbingOrigVolVal');
if (dubbingOrigVol && dubbingOrigVolVal) {
    dubbingOrigVol.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        dubbingOrigVolVal.textContent = val + '%';
        // Điều chỉnh trực tiếp âm lượng video gốc thời gian thực trên player
        const vPlayer = document.getElementById('videoPlayer');
        const isEditedMode = document.getElementById('btnPreviewEdited')?.classList.contains('active');
        const isDubOn = document.getElementById('dubbingEnabled')?.checked !== false;
        if (vPlayer && isEditedMode && isDubOn) {
            vPlayer.volume = Math.max(0, Math.min(1.0, val / 100));
        }
    });
}

const dubbingThreads = document.getElementById('dubbingThreads');
const dubbingThreadsVal = document.getElementById('dubbingThreadsVal');
if (dubbingThreads && dubbingThreadsVal) {
    dubbingThreads.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        let speedLabel = 'Thường';
        if (val >= 24) speedLabel = 'Cực nhanh (Max)';
        else if (val >= 16) speedLabel = 'Siêu tốc';
        else if (val >= 10) speedLabel = 'Nhanh';
        dubbingThreadsVal.textContent = `${val} luồng (${speedLabel})`;
    });
}

const dubbingManualVol = document.getElementById('dubbingManualVol');
const dubbingManualVolVal = document.getElementById('dubbingManualVolVal');
if (dubbingManualVol && dubbingManualVolVal) {
    dubbingManualVol.addEventListener('input', (e) => {
        dubbingManualVolVal.textContent = e.target.value + '%';
    });
}

const dubbingManualOrigVol = document.getElementById('dubbingManualOrigVol');
const dubbingManualOrigVolVal = document.getElementById('dubbingManualOrigVolVal');
if (dubbingManualOrigVol && dubbingManualOrigVolVal) {
    dubbingManualOrigVol.addEventListener('input', (e) => {
        dubbingManualOrigVolVal.textContent = e.target.value + '%';
        const vPlayer = document.getElementById('videoPlayer');
        const isEditedMode = document.getElementById('btnPreviewEdited')?.classList.contains('active');
        if (vPlayer && isEditedMode) {
            vPlayer.volume = Math.max(0, Math.min(1.0, parseInt(e.target.value) / 100));
        }
    });
}

const btnQuickTestVoice = document.getElementById('btnQuickTestVoice');
if (btnQuickTestVoice) {
    btnQuickTestVoice.addEventListener('click', () => {
        const voiceId = document.getElementById('dubbingVoiceInput')?.value || 'local_clone_1787245769140';
        const previewBtn = document.querySelector('#btnOpenVoiceModalDubbing .btn-preview-voice');
        if (window.playPreviewVoice) {
            window.playPreviewVoice(voiceId, previewBtn || btnQuickTestVoice);
        }
    });
}

// AI Stem & Vocal Separation Event Listeners for Editor Tab
const editorStemSeparationEnabled = document.getElementById('editorStemSeparationEnabled');
const editorStemConfig = document.getElementById('editorStemConfig');
if (editorStemSeparationEnabled && editorStemConfig) {
    editorStemConfig.style.opacity = editorStemSeparationEnabled.checked ? '1' : '0.4';
    editorStemConfig.style.pointerEvents = editorStemSeparationEnabled.checked ? 'auto' : 'none';
    editorStemSeparationEnabled.addEventListener('change', (e) => {
        editorStemConfig.style.opacity = e.target.checked ? '1' : '0.4';
        editorStemConfig.style.pointerEvents = e.target.checked ? 'auto' : 'none';
    });
}

const btnRunStemSeparationEditor = document.getElementById('btnRunStemSeparationEditor');
const btnCancelStemSeparationEditor = document.getElementById('btnCancelStemSeparationEditor');
const btnToggleStemLogEditor = document.getElementById('btnToggleStemLogEditor');
const editorStemLogContainer = document.getElementById('editorStemLogContainer');

if (btnToggleStemLogEditor && editorStemLogContainer) {
    btnToggleStemLogEditor.addEventListener('click', () => {
        const isHidden = editorStemLogContainer.style.display === 'none';
        editorStemLogContainer.style.display = isHidden ? 'block' : 'none';
    });
}

if (btnCancelStemSeparationEditor) {
    btnCancelStemSeparationEditor.addEventListener('click', async () => {
        btnCancelStemSeparationEditor.disabled = true;
        btnCancelStemSeparationEditor.innerHTML = '<span>⏳</span> Đang hủy...';
        try {
            await fetch('/api/audio/separate/cancel', { method: 'POST' });
            showToast('🛑 Đã gửi lệnh dừng khẩn cấp tác vụ tách âm thanh!', 'info');
        } catch (e) {
            console.error(e);
        }
    });
}

if (btnRunStemSeparationEditor) {
    btnRunStemSeparationEditor.addEventListener('click', async () => {
        const videoInput = document.getElementById('editorInputVideoPath')?.value || '';
        if (!videoInput) {
            showToast('⚠️ Vui lòng chọn video đầu vào trước khi tách âm thanh!', 'warning');
            return;
        }

        const hasPerm = await checkFeaturePermission('can_access_editor', 'Tách Âm Thanh AI & Lọc Giọng Thoại');
        if (!hasPerm) return;

        const mode = document.getElementById('editorStemMode')?.value || 'mdx_net_hq4';
        const device = document.getElementById('editorStemDevice')?.value || 'auto';
        const removeVocals = document.getElementById('editorRemoveVocals')?.checked !== false;
        const keepSfx = document.getElementById('editorKeepSfx')?.checked !== false;

        const progressBox = document.getElementById('editorStemProgressBox');
        const progressBarFill = document.getElementById('editorStemProgressBarFill');
        const progressStatus = document.getElementById('editorStemProgressStatus');
        const progressPercent = document.getElementById('editorStemProgressPercent');
        const logBox = document.getElementById('editorStemLogContainer');
        const logCount = document.getElementById('editorStemLogCount');
        const hwBadge = document.getElementById('editorStemHardwareBadge');

        if (progressBox) progressBox.style.display = 'block';
        if (progressBarFill) progressBarFill.style.width = '5%';
        if (progressStatus) progressStatus.textContent = 'Đang khởi tạo mô hình...';
        if (progressPercent) progressPercent.textContent = '5%';
        if (hwBadge) hwBadge.textContent = `Hardware: ${device.toUpperCase()}`;
        if (logBox) logBox.textContent = `[System] Bắt đầu tách âm thanh (Model: ${mode}, Hardware: ${device.toUpperCase()})...\n`;

        btnRunStemSeparationEditor.disabled = true;
        btnRunStemSeparationEditor.innerHTML = '<span class="loading-spinner-small"></span> Đang tách âm thanh AI...';
        if (btnCancelStemSeparationEditor) {
            btnCancelStemSeparationEditor.style.display = 'inline-flex';
            btnCancelStemSeparationEditor.disabled = false;
            btnCancelStemSeparationEditor.innerHTML = '<span>🛑 Dừng khẩn cấp</span>';
        }

        showToast('🎛️ Đang chạy tách lời thoại cũ và bảo lưu tiếng động SFX...', 'info');

        let pollTimer = null;
        try {
            const res = await fetch('/api/audio/separate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    media_path: videoInput,
                    mode: mode,
                    device: device,
                    remove_vocals: removeVocals,
                    keep_sfx: keepSfx
                })
            });

            const data = await res.json();
            if (!data.success) {
                showToast(`❌ Lỗi: ${data.error || 'Không thể khởi động'}`, 'error');
                btnRunStemSeparationEditor.disabled = false;
                btnRunStemSeparationEditor.innerHTML = '<span>⚡</span> Tách & Nghe Thử Âm SFX';
                if (btnCancelStemSeparationEditor) btnCancelStemSeparationEditor.style.display = 'none';
                return;
            }

            // Vòng lặp lắng nghe tiến trình thời gian thực
            await new Promise((resolve) => {
                pollTimer = setInterval(async () => {
                    try {
                        const pRes = await fetch('/api/audio/separate/progress');
                        const pData = await pRes.json();
                        if (!pData) return;

                        if (progressBarFill && pData.percent !== undefined) progressBarFill.style.width = `${pData.percent}%`;
                        if (progressPercent && pData.percent !== undefined) progressPercent.textContent = `${pData.percent}%`;
                        if (progressStatus && pData.message) progressStatus.textContent = pData.message;
                        if (pData.logs && logBox) {
                            logBox.textContent = pData.logs.join('\n');
                            logBox.scrollTop = logBox.scrollHeight;
                            if (logCount) logCount.textContent = `(${pData.logs.length})`;
                        }

                        if (pData.status === 'completed') {
                            clearInterval(pollTimer);
                            if (progressBarFill) progressBarFill.style.width = '100%';
                            if (progressPercent) progressPercent.textContent = '100%';
                            if (progressStatus) progressStatus.textContent = '✅ Đã hoàn tất tách âm thanh!';
                            showToast('🎉 Đã tách và lọc âm thanh AI thành công!', 'success');

                            const resultBox = document.getElementById('editorStemResultAudio');
                            const player = document.getElementById('editorStemAudioPlayer');
                            const btnApplyStem = document.getElementById('btnApplyStemToEditedPreview');
                            const btnRemoveStem = document.getElementById('btnRemoveStemFromEditedPreview');
                            if (resultBox && player && pData.result && pData.result.cleaned_url) {
                                window._appliedStemAudioUrl = pData.result.cleaned_url;
                                window._appliedStemCleanedPath = pData.result.cleaned_path;
                                resultBox.style.display = 'block';
                                player.src = pData.result.cleaned_url;
                                if (window._syncedStemAudioPlayer) {
                                    window._syncedStemAudioPlayer.src = pData.result.cleaned_url;
                                    window._syncedStemAudioPlayer.load();
                                }
                                if (btnApplyStem) {
                                    btnApplyStem.innerHTML = '<span>✨ Áp dụng vào "Bản sau khi sửa"</span>';
                                    btnApplyStem.style.background = 'linear-gradient(135deg, #0ea5e9, #10b981)';
                                }
                                if (btnRemoveStem) btnRemoveStem.style.display = 'none';
                                player.play().catch(() => {});
                            }
                            resolve();
                        } else if (pData.status === 'cancelled') {
                            clearInterval(pollTimer);
                            if (progressStatus) progressStatus.textContent = '🛑 Đã dừng khẩn cấp.';
                            showToast('🛑 Đã dừng tác vụ tách âm thanh khẩn cấp!', 'info');
                            resolve();
                        } else if (pData.status === 'error') {
                            clearInterval(pollTimer);
                            if (progressStatus) progressStatus.textContent = `❌ Lỗi: ${pData.error || 'Thất bại'}`;
                            showToast(`❌ Lỗi tách âm: ${pData.error || 'Thất bại'}`, 'error');
                            resolve();
                        }
                    } catch (e) {
                        console.error("Polling progress error:", e);
                    }
                }, 300);
            });

        } catch (err) {
            showToast(`❌ Lỗi kết nối: ${err.message}`, 'error');
        } finally {
            if (pollTimer) clearInterval(pollTimer);
            btnRunStemSeparationEditor.disabled = false;
            btnRunStemSeparationEditor.innerHTML = '<span>⚡</span> Tách & Nghe Thử Âm SFX';
            if (btnCancelStemSeparationEditor) btnCancelStemSeparationEditor.style.display = 'none';
        }
    });
}

// File & Folder Selection Helper (works on both pywebview Desktop and Browser mode via Flask API)
async function selectDirectory(title = 'Chọn thư mục lưu trữ') {
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.select_output_directory) {
            return await window.pywebview.api.select_output_directory();
        }
        const res = await fetch('/api/select_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        const data = await res.json();
        if (data.success && (data.folder_path || data.path || data.folder)) {
            return data.folder_path || data.path || data.folder;
        }
    } catch (e) {
        console.error("Lỗi khi mở hộp thoại chọn thư mục:", e);
    }
    return null;
}

window.selectDirectory = selectDirectory;
window.selectFile = selectFile;

async function selectFile(type, title) {
    try {
        if (window.pywebview && window.pywebview.api) {
            if (type === 'video') return await window.pywebview.api.select_input_video();
            else if (type === 'dir') return await window.pywebview.api.select_output_directory();
            else if (type === 'audio') return await window.pywebview.api.select_audio_file();
            else if (type === 'image') return await window.pywebview.api.select_image_file();
            else if (type === 'srt') return await window.pywebview.api.select_srt_file();
        }
        
        if (type === 'dir') {
            return await selectDirectory(title || 'Chọn thư mục');
        }
        
        let filetypes = [['All Files', '*.*']];
        if (type === 'video') filetypes = [['Video Files', '*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm'], ['All Files', '*.*']];
        else if (type === 'audio') filetypes = [['Audio Files', '*.mp3;*.wav;*.m4a;*.aac;*.flac'], ['All Files', '*.*']];
        else if (type === 'srt') filetypes = [['Subtitle Files', '*.srt;*.vtt;*.ass'], ['All Files', '*.*']];
        else if (type === 'image') filetypes = [['Image Files', '*.png;*.jpg;*.jpeg;*.webp'], ['All Files', '*.*']];
        
        const res = await fetch('/api/select_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, title: title || 'Chọn tệp tin', filetypes })
        });
        const data = await res.json();
        if (data.success && (data.file_path || data.path || data.file)) {
            return data.file_path || data.path || data.file;
        }
    } catch (e) {
        console.error("Lỗi khi mở hộp thoại chọn file:", e);
    }
    return null;
}

async function selectFiles(type = 'video', title = 'Chọn các tệp tin') {
    try {
        if (window.pywebview && window.pywebview.api) {
            if (type === 'video' && typeof window.pywebview.api.select_multiple_videos === 'function') {
                const res = await window.pywebview.api.select_multiple_videos();
                if (Array.isArray(res) && res.length > 0) return res;
            } else if (type === 'srt' && typeof window.pywebview.api.select_multiple_srts === 'function') {
                const res = await window.pywebview.api.select_multiple_srts();
                if (Array.isArray(res) && res.length > 0) return res;
            }
        }
        
        let filetypes = [['All Files', '*.*']];
        if (type === 'video') filetypes = [['Video Files', '*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v'], ['All Files', '*.*']];
        else if (type === 'srt') filetypes = [['Subtitle Files', '*.srt;*.vtt;*.ass'], ['All Files', '*.*']];
        
        const res = await fetch('/api/select_files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, title: title || 'Chọn các tệp tin', filetypes })
        });
        const data = await res.json();
        if (data.success && Array.isArray(data.file_paths) && data.file_paths.length > 0) {
            return data.file_paths;
        }
        if (data.success && Array.isArray(data.files) && data.files.length > 0) {
            return data.files;
        }
    } catch (e) {
        console.error("Lỗi khi mở hộp thoại chọn nhiều file:", e);
    }
    return [];
}

window.selectFile = selectFile;
window.selectFiles = selectFiles;
window.selectDirectory = selectDirectory;


if(document.getElementById('btnSelectEditorInput')) {
    document.getElementById('btnSelectEditorInput').addEventListener('click', async () => {
        const path = await selectFile('video');
        if (path) {
            editorInputVideoPath.value = path;
            // Set video source for preview
            videoPlayer.src = `/api/video?path=${encodeURIComponent(path)}`;
            videoPlayer.style.display = 'block';
            videoPlaceholder.style.display = 'none';
            videoPlayer.load();

            if (typeof window.updateActiveBatchItemVideoPath === 'function') {
                window.updateActiveBatchItemVideoPath(path);
            }

            // Quét xem video này đã có dữ liệu phụ đề hoặc dữ liệu biên tập cũ chưa để hỏi người dùng làm tiếp
            try {
                const outDirVal = (document.getElementById('outputDir')?.value || '').trim();
                const checkRes = await fetch('/api/editor/check_cache', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        input_video: path,
                        output_dir: outDirVal
                    })
                });
                if (checkRes.ok) {
                    const checkData = await checkRes.json();
                    const srtCandidate = checkData.details && (checkData.details.cached_srt || checkData.details.video_srt);
                    const hasAiBoxes = !!(checkData.details && checkData.details.ai_boxes);
                    const aiBoxesCount = checkData.details && checkData.details.ai_boxes_count;

                    if (srtCandidate && (typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0)) {
                        const srtName = srtCandidate.split(/[\\/]/).pop();
                        let msg = `Hệ thống tìm thấy file phụ đề có sẵn cho video này ("${srtName}")`;
                        if (hasAiBoxes) {
                            msg += ` kèm toạ độ quét làm mờ AI Pixel (${aiBoxesCount ? aiBoxesCount + ' câu' : 'đầy đủ'})`;
                        }
                        msg += `. Bạn có muốn nạp ngay vào bảng biên tập để tiếp tục làm việc mà không cần quét lại không?`;

                        const loadConfirm = await showConfirmModal(
                            'Nạp dữ liệu đã xử lý trước đó?',
                            msg
                        );
                        if (loadConfirm) {
                            await loadSrtToEditor(srtCandidate);
                            
                            // Nếu có toạ độ quét AI đã lưu, tự động nạp vào srtData
                            if (hasAiBoxes) {
                                try {
                                    const boxesRes = await fetch(`/api/editor/cache_ai_boxes?video_path=${encodeURIComponent(path)}&output_dir=${encodeURIComponent(outDirVal)}`);
                                    if (boxesRes.ok) {
                                        const boxesData = await boxesRes.json();
                                        if (boxesData.success && Array.isArray(boxesData.boxes) && boxesData.boxes.length > 0) {
                                            let appliedCount = 0;
                                            boxesData.boxes.forEach(item => {
                                                const idx = item.index;
                                                const b = item.box || (Array.isArray(item) && item.length >= 5 ? {
                                                    x_pct: (item[3] * 100),
                                                    w_pct: (item[4] * 100),
                                                    visual_start: item[5],
                                                    visual_end: item[6]
                                                } : null);
                                                if (srtData[idx] && b) {
                                                    srtData[idx].aiBox = b;
                                                    if (b.visual_start !== undefined) srtData[idx].visual_start = b.visual_start;
                                                    if (b.visual_end !== undefined) srtData[idx].visual_end = b.visual_end;
                                                    appliedCount++;
                                                }
                                            });
                                            const chkAi = document.getElementById('blurUseAiScan');
                                            if (chkAi) chkAi.checked = true;
                                            if (typeof updateAiScanBadge === 'function') updateAiScanBadge();
                                            if (typeof updateDynamicBlurIntervals === 'function') updateDynamicBlurIntervals();
                                            showToast(`🎉 Đã nạp thành công phụ đề và ${appliedCount} toạ độ quét AI Pixel đã lưu!`, 'success');
                                            return;
                                        }
                                    }
                                } catch (be) {
                                    console.warn("Lỗi nạp toạ độ AI từ cache:", be);
                                }
                            }
                            showToast(`✨ Đã nạp thành công phụ đề "${srtName}"!`, 'success');
                        }
                    }
                }
            } catch (err) {
                console.debug("Kiểm tra dữ liệu có sẵn cho video thất bại:", err);
            }
        }
    });
}

const btnSelectOutputDir = document.getElementById('btnSelectOutputDir');
if (btnSelectOutputDir) {
    btnSelectOutputDir.addEventListener('click', async () => {
        const path = await selectFile('dir');
        if (path && outputDirPath) outputDirPath.value = path;
    });
}

const btnSelectReviewOutputFolder = document.getElementById('btnSelectReviewOutputFolder');
if (btnSelectReviewOutputFolder) {
    btnSelectReviewOutputFolder.addEventListener('click', async () => {
        const path = await selectFile('dir');
        if (path) document.getElementById('reviewOutputFolder').value = path;
    });
}

document.getElementById('btnSelectAudio').addEventListener('click', async () => {
    const path = await selectFile('audio');
    if (path) manualAudioPath.value = path;
});

const stopExportBtn = document.getElementById('stopExportBtn');
const btnEmergencyStop = document.getElementById('btnEmergencyStop');
let exportAbortController = null;

function setStatus(state) {
    if (statusDot) statusDot.className = 'dot ' + state;
    if (state === 'ready') {
        if (statusText) statusText.textContent = 'Sẵn sàng';
        startBtn.disabled = false;
        startBtn.style.display = 'inline-flex';
        startBtn.textContent = 'Xuất video';
        if (stopExportBtn) stopExportBtn.style.display = 'none';
        if (btnEmergencyStop) btnEmergencyStop.style.display = 'none';
        const badge = document.getElementById('exportStageBadge');
        if (badge) badge.style.display = 'none';
    } else if (state === 'running') {
        if (statusText) statusText.textContent = 'Đang xuất video...';
        startBtn.disabled = true;
        startBtn.style.display = 'none';
        if (stopExportBtn) stopExportBtn.style.display = 'inline-flex';
        if (btnEmergencyStop) btnEmergencyStop.style.display = 'inline-block';
        // Auto expand terminal on start
        terminalOverlay.classList.remove('collapsed');
        terminalOverlay.classList.add('expanded');
        toggleTerminalBtn.textContent = 'Thu gọn';
    } else if (state === 'reconnecting') {
        if (statusText) statusText.textContent = 'Mất kết nối cập nhật tiến độ — đang kiểm tra lại...';
        startBtn.disabled = true;
        startBtn.style.display = 'none';
        if (stopExportBtn) stopExportBtn.style.display = 'inline-flex';
        if (btnEmergencyStop) btnEmergencyStop.style.display = 'inline-block';
    } else if (state === 'error') {
        if (statusText) statusText.textContent = 'Có lỗi xảy ra';
        startBtn.disabled = false;
        startBtn.style.display = 'inline-flex';
        startBtn.textContent = 'THỬ LẠI';
        if (stopExportBtn) stopExportBtn.style.display = 'none';
        if (btnEmergencyStop) btnEmergencyStop.style.display = 'none';
    }
}

function updateExportStageUI(stageData) {
    const badge = document.getElementById('exportStageBadge');
    if (!badge || !stageData) return;
    badge.style.display = 'inline-block';
    const stageNames = {
        'preparing': '🛠️ Chuẩn bị',
        'tts_generating': '🎙️ Lồng tiếng AI',
        'stem_separating': '🎵 Tách âm thanh MDX',
        'building_filters': '🎨 Dựng bộ lọc',
        'encoding': '🎬 Biên mã FFmpeg',
        'finalizing': '✨ Hoàn tất'
    };
    const name = stageNames[stageData.stage] || stageData.stage || 'Đang xử lý';
    const pct = typeof stageData.progress === 'number' && stageData.progress > 0 ? ` (${Math.round(stageData.progress)}%)` : '';
    badge.textContent = `${name}${pct}`;
    if (stageData.stage === 'finalizing') {
        badge.style.color = '#4ade80';
        badge.style.borderColor = 'rgba(74, 222, 128, 0.35)';
        badge.style.background = 'rgba(74, 222, 128, 0.15)';
    } else {
        badge.style.color = '#38bdf8';
        badge.style.borderColor = 'rgba(56, 189, 248, 0.35)';
        badge.style.background = 'rgba(14, 165, 233, 0.18)';
    }
}

function updateExportProgressUI(progData) {
    const badge = document.getElementById('exportStageBadge');
    if (!badge || !progData) return;
    badge.style.display = 'inline-block';
    const stageNames = {
        'tts_generating': '🎙️ Lồng tiếng AI',
        'stem_separating': '🎵 Tách âm thanh',
        'encoding': '🎬 Biên mã FFmpeg'
    };
    const name = stageNames[progData.stage] || '🎬 Biên mã FFmpeg';
    const pct = Math.round(progData.progress || 0);
    badge.textContent = `${name} (${pct}%)`;
}

async function triggerEmergencyStopExport() {
    if (exportAbortController) {
        try {
            exportAbortController.abort();
        } catch (e) {}
    }
    appendLog('🛑 [DỪNG KHẨN CẤP] Đang gửi lệnh hủy và dừng toàn bộ tiến trình...', 'error');
    showToast('Đang dừng khẩn cấp tiến trình...', 'warning');
    
    try {
        await fetch('/api/stop_export', { method: 'POST' });
        appendLog('🛑 Đã dừng toàn bộ tiến trình xuất video!', 'error');
    } catch (err) {
        console.error("Error stopping export:", err);
    }
    
    isGenerating = false;
    setStatus('ready');
    showToast('Đã dừng xuất video!', 'info');
}

if (stopExportBtn) {
    stopExportBtn.addEventListener('click', triggerEmergencyStopExport);
}
if (btnEmergencyStop) {
    btnEmergencyStop.addEventListener('click', () => {
        if (isGenerating) {
            triggerEmergencyStopExport();
        } else {
            const btnStopReview = document.getElementById('btnStopReview');
            if (btnStopReview && btnStopReview.style.display !== 'none') {
                btnStopReview.click();
            }
        }
    });
}

// Export Modal References
const exportConfigModal = document.getElementById('exportConfigModal');
const closeExportModalBtn = document.getElementById('closeExportModalBtn');
const btnCancelExportModal = document.getElementById('btnCancelExportModal');
const btnConfirmStartExport = document.getElementById('btnConfirmStartExport');
const exportModalFileName = document.getElementById('exportModalFileName');
const exportModalOutputDir = document.getElementById('exportModalOutputDir');
const btnSelectModalOutputDir = document.getElementById('btnSelectModalOutputDir');
const exportModalSaveToSourceDir = document.getElementById('exportModalSaveToSourceDir');

function getSourceVideoDir(filePath) {
    if (!filePath || typeof filePath !== 'string') return '';
    const clean = filePath.trim().replace(/^["']|["']$/g, '');
    const lastSlash = Math.max(clean.lastIndexOf('/'), clean.lastIndexOf('\\'));
    return lastSlash > 0 ? clean.substring(0, lastSlash) : '';
}

if (btnSelectModalOutputDir) {
    btnSelectModalOutputDir.addEventListener('click', async () => {
        const path = await selectFile('dir');
        if (path && exportModalOutputDir) exportModalOutputDir.value = path;
    });
}

if (exportModalSaveToSourceDir) {
    exportModalSaveToSourceDir.addEventListener('change', () => {
        if (!exportModalOutputDir) return;
        if (exportModalSaveToSourceDir.checked) {
            if (!exportModalOutputDir.dataset.prevDir) {
                exportModalOutputDir.dataset.prevDir = exportModalOutputDir.value || '';
            }
            const inVid = (typeof editorInputVideoPath !== 'undefined' && editorInputVideoPath) ? editorInputVideoPath.value : '';
            const sDir = getSourceVideoDir(inVid);
            exportModalOutputDir.value = sDir || '[Tự động] Cùng thư mục video gốc';
            if (btnSelectModalOutputDir) {
                btnSelectModalOutputDir.style.opacity = '0.5';
                btnSelectModalOutputDir.style.pointerEvents = 'none';
            }
        } else {
            exportModalOutputDir.value = exportModalOutputDir.dataset.prevDir || '';
            if (btnSelectModalOutputDir) {
                btnSelectModalOutputDir.style.opacity = '1';
                btnSelectModalOutputDir.style.pointerEvents = 'auto';
            }
        }
    });
}

if (closeExportModalBtn) closeExportModalBtn.addEventListener('click', () => { if (exportConfigModal) exportConfigModal.style.display = 'none'; });
if (btnCancelExportModal) btnCancelExportModal.addEventListener('click', () => { if (exportConfigModal) exportConfigModal.style.display = 'none'; });

startBtn.addEventListener('click', () => {
    if (isGenerating) return;
    if (!checkFeaturePermission('can_access_editor', 'Xuất video Biên tập phim')) return;
    if (!editorInputVideoPath.value) {
        showToast("Vui lòng chọn video đầu vào!", 'warning');
        return;
    }
    if (exportModalSaveToSourceDir && exportModalSaveToSourceDir.checked && exportModalOutputDir) {
        const sDir = getSourceVideoDir(editorInputVideoPath.value);
        exportModalOutputDir.value = sDir || '[Tự động] Cùng thư mục video gốc';
    }
    if (exportConfigModal) {
        exportConfigModal.style.display = 'flex';
    } else {
        executeExportPipeline();
    }
});

if (btnConfirmStartExport) {
    btnConfirmStartExport.addEventListener('click', () => {
        if (exportConfigModal) exportConfigModal.style.display = 'none';
        executeExportPipeline();
    });
}

window.getEditorOcrRegion = function() {
    return (typeof currentRegion !== 'undefined' && currentRegion) 
        ? JSON.parse(JSON.stringify(currentRegion)) 
        : { x: 20, y: 81.5, w: 60, h: 9.5 };
};

window.setEditorOcrRegion = function(region) {
    if (region && typeof region === 'object') {
        const w = region.w ?? region.width ?? 60;
        const h = region.h ?? region.height ?? 9.5;
        const x = region.x ?? 20;
        const y = region.y ?? 81.5;
        currentRegion = { x, y, w, h };
        if (typeof ocrRegionCoords !== 'undefined' && ocrRegionCoords) {
            ocrRegionCoords.textContent = `X:${x.toFixed(1)}% Y:${y.toFixed(1)}% W:${w.toFixed(1)}% H:${h.toFixed(1)}%`;
        }
    }
};

window.snapshotEditorState = function() {
    const vp = document.getElementById('videoPlayer');
    return {
        videoPath: (typeof editorInputVideoPath !== 'undefined' && editorInputVideoPath) ? editorInputVideoPath.value : '',
        srtPath: (typeof manualSrtPath !== 'undefined' && manualSrtPath) ? manualSrtPath.value : '',
        srtData: (typeof srtData !== 'undefined' && Array.isArray(srtData)) ? JSON.parse(JSON.stringify(srtData)) : [],
        ocrRegion: window.getEditorOcrRegion(),
        videoTime: (vp && !isNaN(vp.currentTime)) ? vp.currentTime : 0,
        videoPaused: (vp) ? vp.paused : true,
        videoSrc: (vp) ? vp.src : ''
    };
};

window.restoreEditorState = function(snap) {
    if (!snap) return;
    if (typeof editorInputVideoPath !== 'undefined' && editorInputVideoPath) {
        editorInputVideoPath.value = snap.videoPath || '';
    }
    if (typeof manualSrtPath !== 'undefined' && manualSrtPath) {
        manualSrtPath.value = snap.srtPath || '';
    }
    if (typeof srtData !== 'undefined') {
        srtData = Array.isArray(snap.srtData) ? JSON.parse(JSON.stringify(snap.srtData)) : [];
        if (typeof renderSrtTable === 'function') {
            renderSrtTable();
        }
    }
    if (snap.ocrRegion) {
        window.setEditorOcrRegion(snap.ocrRegion);
    }
    const vp = document.getElementById('videoPlayer');
    if (vp) {
        if (snap.videoSrc && vp.src !== snap.videoSrc) {
            vp.src = snap.videoSrc;
            vp.currentTime = snap.videoTime || 0;
            if (!snap.videoPaused) {
                vp.play().catch(() => {});
            } else {
                vp.pause();
            }
        }
    }
};

window.buildEditorExportConfig = function(overrides = {}) {
    const isDubbingOn = overrides.dubbing?.enabled ?? (document.getElementById('dubbingEnabled')?.checked ?? false);
    const isDubbingTtsTab = (overrides.dubbing?.mode === 'tts') || (document.getElementById('tabDubbingTts')?.classList.contains('active') ?? true);

    const parseSafeNum = (val, def) => {
        if (val === undefined || val === null || val === '') return def;
        const n = Number(val);
        return Number.isFinite(n) ? n : def;
    };

    const saveToSourceModal = Boolean(document.getElementById('exportModalSaveToSourceDir')?.checked);
    const saveToSource = Boolean(overrides.save_to_source_dir ?? (overrides.outputDir ? false : saveToSourceModal));
    let outDirVal = overrides.outputDir || ((typeof exportModalOutputDir !== 'undefined' && exportModalOutputDir && exportModalOutputDir.value && !exportModalOutputDir.value.startsWith('[Tự động]')) ? exportModalOutputDir.value : ((typeof outputDirPath !== 'undefined' && outputDirPath && outputDirPath.value) ? outputDirPath.value : 'output'));
    if (saveToSource) {
        const inVid = overrides.inputVideo || (typeof editorInputVideoPath !== 'undefined' && editorInputVideoPath ? editorInputVideoPath.value : '');
        const sDir = getSourceVideoDir(inVid);
        if (sDir) outDirVal = sDir;
    }
    const outNameVal = overrides.outputName || ((typeof exportModalFileName !== 'undefined' && exportModalFileName && exportModalFileName.value.trim()) ? exportModalFileName.value.trim() : ((typeof outputFileName !== 'undefined' && outputFileName && outputFileName.value) ? outputFileName.value : "video_tom_tat.mp4"));

    const stemSepMasterEnabled = Boolean(
        overrides.dubbing?.stem_separation?.enabled ?? 
        document.getElementById('editorStemSeparationEnabled')?.checked
    );
    const shouldRemoveVocals = stemSepMasterEnabled && Boolean(
        overrides.dubbing?.remove_original_vocals ?? 
        overrides.dubbing?.stem_separation?.remove_vocals ?? 
        document.getElementById('editorRemoveVocals')?.checked
    );

    const dubbingConfig = {
        enabled: isDubbingOn,
        mode: isDubbingTtsTab ? 'tts' : 'manual',
        voice_id: overrides.dubbing?.voice_id || overrides.dubbing?.voice || document.getElementById('dubbingVoiceInput')?.value || 'local_clone_1787245769140',
        speed: parseFloat(overrides.dubbing?.speed ?? (document.getElementById('dubbingSpeed')?.value || 1.1)),
        threads: parseInt(overrides.dubbing?.threads ?? (document.getElementById('dubbingThreads')?.value || 16)),
        voice_volume: (overrides.dubbing?.voice_volume !== undefined)
            ? Number(overrides.dubbing.voice_volume)
            : (parseInt(document.getElementById('dubbingVoiceVol')?.value || 100) / 100),
        original_volume: (overrides.dubbing?.original_volume !== undefined)
            ? Number(overrides.dubbing.original_volume)
            : (isDubbingOn ? (parseInt(document.getElementById('dubbingOrigVol')?.value || 45) / 100) : 1.0),
        audio_ducking: isDubbingOn ? Boolean(overrides.dubbing?.audio_ducking ?? (document.getElementById('dubbingDucking')?.checked)) : false,
        remove_original_vocals: shouldRemoveVocals,
        stem_separation: {
            enabled: stemSepMasterEnabled,
            mode: overrides.dubbing?.stem_separation?.mode || document.getElementById('editorStemMode')?.value || 'mdx_net_hq4',
            device: overrides.dubbing?.stem_separation?.device || document.getElementById('editorStemDevice')?.value || 'auto',
            remove_vocals: shouldRemoveVocals,
            keep_sfx: overrides.dubbing?.stem_separation?.keep_sfx ?? (document.getElementById('editorKeepSfx')?.checked ?? true),
            precomputed_cleaned_path: overrides.dubbing?.stem_separation?.precomputed_cleaned_path || ((window._isStemAudioAppliedToEdited && window._appliedStemCleanedPath) ? window._appliedStemCleanedPath : '')
        },
        manual_audio: overrides.dubbing?.manual_audio || document.getElementById('manualAudioPath')?.value || '',
        manual_voice_volume: (overrides.dubbing?.manual_voice_volume !== undefined) ? Number(overrides.dubbing.manual_voice_volume) : (parseInt(document.getElementById('dubbingManualVol')?.value || 100) / 100),
        manual_original_volume: (overrides.dubbing?.manual_original_volume !== undefined) ? Number(overrides.dubbing.manual_original_volume) : (parseInt(document.getElementById('dubbingManualOrigVol')?.value || 30) / 100)
    };

    const isSubEnabled = overrides.subtitles_enabled ?? (document.getElementById('subtitlesEnabled')?.checked ?? true);
    const blurEnabled = overrides.blur_original_subtitles ?? (isSubEnabled && Boolean(document.getElementById('reviewBlurOriginalSubtitles')?.checked));
    const blurIntensity = parseInt(overrides.blur_intensity ?? (document.getElementById('dynBlurIntensity')?.value || document.getElementById('subBgBlur')?.value || 15));

    let subs = overrides.subtitles;
    if (!subs) {
        subs = (typeof srtData !== 'undefined' && Array.isArray(srtData)) ? srtData.map(s => {
            let orig = (s.text || '').trim();
            let trans = (s.translation || '').trim();
            if (!trans && orig && !/[\u4e00-\u9fff]/.test(orig)) {
                trans = orig;
            }
            return { ...s, text: orig, translation: trans };
        }) : [];
    }

    const config = {
        mode: isDubbingOn ? (isDubbingTtsTab ? 'tts' : 'manual') : 'none',
        inputVideo: overrides.inputVideo || (typeof editorInputVideoPath !== 'undefined' && editorInputVideoPath ? editorInputVideoPath.value : ''),
        outputDir: outDirVal,
        save_to_source_dir: saveToSource,
        outputName: outNameVal,
        encoder: overrides.encoder || document.getElementById('exportEncoder')?.value || 'auto',
        resolution: overrides.resolution || document.getElementById('exportResolution')?.value || 'original',
        bitrate: parseInt(overrides.bitrate || document.getElementById('exportBitrate')?.value) || 10000,
        bitrate_mode: overrides.bitrate_mode || document.getElementById('exportBitrateMode')?.value || 'VBR',
        threads: overrides.threads || document.getElementById('exportThreads')?.value || 'auto',
        preset: overrides.preset || document.getElementById('exportPreset')?.value || 'faster',
        video_speed: parseFloat(overrides.video_speed ?? (document.getElementById('editToolSpeedSlider')?.value || 1.0)),
        video_zoom: overrides.video_zoom ?? (typeof currentVideoZoom !== 'undefined' ? currentVideoZoom : 1.0),
        video_pan_x: overrides.video_pan_x ?? (typeof videoPanX !== 'undefined' ? videoPanX : 0),
        video_pan_y: overrides.video_pan_y ?? (typeof videoPanY !== 'undefined' ? videoPanY : 0),
        aspect_ratio: overrides.aspect_ratio || document.getElementById('editToolAspectRatio')?.value || 'original',
        mirror_flip: overrides.mirror_flip ?? (document.getElementById('editToolMirrorFlip')?.checked || false),
        trim_enabled: overrides.trim_enabled ?? (document.getElementById('editToolTrimEnabled')?.checked || false),
        trim_start: overrides.trim_start ?? (document.getElementById('editToolTrimStart')?.value || ''),
        trim_end: overrides.trim_end ?? (document.getElementById('editToolTrimEnd')?.value || ''),
        manualAudio: dubbingConfig.manual_audio,
        manualSrt: overrides.manualSrt || (typeof manualSrtPath !== 'undefined' && manualSrtPath ? manualSrtPath.value : ''),
        dubbing: dubbingConfig,
        subtitles: subs,
        subtitles_enabled: isSubEnabled,
        subtitle_style: {
            font: overrides.subtitle_style?.font || document.getElementById('subFont')?.value || 'Montserrat',
            size: parseInt(overrides.subtitle_style?.size ?? (document.getElementById('subSize')?.value || 24)),
            color: overrides.subtitle_style?.color || document.getElementById('subColorPicker')?.value || '#ffffff',
            outline_color: overrides.subtitle_style?.outline_color || document.getElementById('subOutlineColorPicker')?.value || '#000000',
            outline: parseSafeNum(overrides.subtitle_style?.outline ?? document.getElementById('subOutline')?.value, 1),
            bold: overrides.subtitle_style?.bold ?? (typeof isSubBold !== 'undefined' ? isSubBold : true),
            italic: overrides.subtitle_style?.italic ?? (typeof isSubItalic !== 'undefined' ? isSubItalic : false),
            uppercase: overrides.subtitle_style?.uppercase ?? (typeof isSubUppercase !== 'undefined' ? isSubUppercase : false),
            region: overrides.subtitle_style?.region || (typeof currentSubRegion !== 'undefined' && currentSubRegion ? { ...currentSubRegion } : { x: 10, y: 81.5, w: 80, h: 9.5 }),
            align: overrides.subtitle_style?.align || (typeof subTextAlign !== 'undefined' ? subTextAlign : 'center')
        },
        blur_original_subtitles: blurEnabled,
        blur_intensity: blurIntensity,
        blur_mode: overrides.blur_mode || document.querySelector('input[name="blurModeRadio"]:checked')?.value || 'fixed',
        blur_w: parseFloat(overrides.blur_w ?? (document.getElementById('blurWidth')?.value || 60)),
        blur_h: parseFloat(overrides.blur_h ?? (document.getElementById('blurHeight')?.value || 9.5)),
        blur_x: parseFloat(overrides.blur_x ?? (document.getElementById('blurXPos')?.value || 20)),
        blur_y: parseFloat(overrides.blur_y ?? (document.getElementById('blurYPos')?.value || 81.5)),
        blur_use_ai_scan: overrides.blur_use_ai_scan ?? (document.getElementById('blurUseAiScan')?.checked ?? true),
        original_srt_path: overrides.original_srt_path || (typeof manualSrtPath !== 'undefined' && manualSrtPath ? manualSrtPath.value : ''),
        ocr_region: overrides.ocr_region || (typeof currentRegion !== 'undefined' && currentRegion ? currentRegion : { x: 20, y: 81.5, w: 60, h: 9.5 }),
        blur_lead_offset: parseSafeNum(overrides.blur_lead_offset ?? document.getElementById('blurLeadOffset')?.value, -180),
        blur_padding: parseSafeNum(overrides.blur_padding ?? document.getElementById('blurPadding')?.value, 220),
        logo: {
            enabled: overrides.logo?.enabled ?? (document.getElementById('enableLogoWatermark')?.checked ?? false),
            path: overrides.logo?.path ?? (document.getElementById('logoInputPath')?.value || ''),
            x_pct: overrides.logo?.x_pct ?? (typeof currentLogoState !== 'undefined' ? currentLogoState.x_pct : 85),
            y_pct: overrides.logo?.y_pct ?? (typeof currentLogoState !== 'undefined' ? currentLogoState.y_pct : 5),
            w_pct: overrides.logo?.w_pct ?? (typeof currentLogoState !== 'undefined' ? currentLogoState.w_pct : 10),
            h_pct: overrides.logo?.h_pct ?? (typeof currentLogoState !== 'undefined' ? currentLogoState.h_pct : 5),
            opacity: parseInt(overrides.logo?.opacity ?? (document.getElementById('logoOpacity')?.value || 100))
        },
        delogo: {
            enabled: overrides.delogo?.enabled ?? (document.getElementById('enableAutoDelogo')?.checked ?? false),
            corner: overrides.delogo?.corner || document.getElementById('delogoCorner')?.value || 'bottom-right',
            size: overrides.delogo?.size || document.getElementById('delogoSize')?.value || 'medium',
            method: overrides.delogo?.method || document.getElementById('delogoMethod')?.value || 'delogo'
        },
        custom_overlay_layers: overrides.custom_overlay_layers || (Array.isArray(window.customOverlayLayers) ? window.customOverlayLayers : []).filter(l => l.visible !== false)
    };

    return config;
};

async function executeExportPipeline() {
    if (isGenerating) return;
    if (!checkFeaturePermission('can_access_editor', 'Xuất video Biên tập phim')) return;
    
    if (!editorInputVideoPath.value) {
        showToast("Vui lòng chọn video đầu vào!", 'warning');
        return;
    }
    
    const isDubbingOn = document.getElementById('dubbingEnabled')?.checked ?? false;
    const isDubbingTtsTab = document.getElementById('tabDubbingTts')?.classList.contains('active') ?? true;
    const manualAudioPathVal = document.getElementById('manualAudioPath')?.value || '';
    if (isDubbingOn && !isDubbingTtsTab && !manualAudioPathVal) {
        showToast("Bạn đang bật lồng tiếng thủ công nhưng chưa chọn file Audio!", 'warning');
        return;
    }

    const config = window.buildEditorExportConfig();

    // CHECK CACHE (Tái sử dụng dữ liệu như Review Phim)
    try {
        const cacheRes = await fetch('/api/editor/check_cache', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_video: config.inputVideo,
                output_dir: config.outputDir,
                output_name: config.outputName,
                dubbing: config.dubbing,
                blur_original_subtitles: config.blur_original_subtitles
            })
        });
        if (cacheRes.ok) {
            const cacheData = await cacheRes.json();
            if (cacheData.has_cache && cacheData.files && cacheData.files.length > 0) {
                const confirm = await showConfirmModal(
                    'Tái sử dụng dữ liệu?',
                    `Hệ thống tìm thấy dữ liệu đã xử lý từ lần chạy trước (${cacheData.files.join(', ')}). Bạn có muốn TÁI SỬ DỤNG chúng để tiết kiệm thời gian (và tiền API) không? Chọn 'Đồng ý' để tiếp tục dùng, hoặc 'Hủy' để làm lại từ đầu.`
                );
                config.use_cache = confirm;
            }
        }
    } catch(e) {
        console.error("Lỗi khi kiểm tra cache biên tập phim:", e);
    }

    try {
        isGenerating = true;
        setStatus('running');
        
        // Auto-open terminal so user sees real-time progress & error alerts
        const termOverlay = document.getElementById("terminalOverlay");
        if (termOverlay && termOverlay.classList.contains('collapsed')) {
            termOverlay.classList.remove('collapsed');
            termOverlay.classList.add('expanded');
            const toggleBtn = document.getElementById("toggleTerminalBtn");
            if (toggleBtn) toggleBtn.textContent = 'Thu gọn';
        }
        const term = document.getElementById("terminal");
        if (term) term.innerHTML = '';

        const blurLabel = config.blur_original_subtitles ? ' | Dynamic Blur: Bật (' + config.blur_intensity + 'px)' : '';
        const dubbingDesc = config.dubbing?.enabled 
            ? (config.dubbing?.mode === 'tts' ? `TTS (${config.dubbing?.voice_id || 'Mặc định'})` : 'File thủ công') 
            : 'Tắt';
        appendLog('> Bắt đầu xuất video... Lồng tiếng AI: ' + dubbingDesc + blurLabel, 'info');
        
        if (config.dubbing?.enabled && config.dubbing?.mode === 'tts' && Array.isArray(srtData)) {
            const missingCount = srtData.filter(s => {
                const tr = (s.translation || s.text || '').trim();
                return !tr || /[\u4e00-\u9fff]/.test(tr);
            }).length;
            if (missingCount > 0) {
                appendLog(`> ℹ️ [Lồng tiếng AI] Phát hiện ${missingCount} câu chưa dịch hoặc còn chữ Hán, hệ thống sẽ tự động dịch bổ sung khi tạo giọng đọc.`, 'info');
            }
        }

        exportAbortController = new AbortController();
        
        // Call Python backend to start process
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
            signal: exportAbortController.signal
        });
        
        if (!response.ok) {
            let errorMsg = "Failed to start process";
            try {
                const errData = await response.json();
                if (errData && errData.error) errorMsg = errData.error;
            } catch(e) {}
            throw new Error(errorMsg);
        }
        
        const decoder = new TextDecoder('utf-8');
        let lineBuffer = '';
        let lastSeq = 0;
        let activeJobId = null;
        let exportSuccessEvent = null;
        let exportFailedEvent = null;
        let exportCancelledEvent = false;

        function handleSseLine(rawLine) {
            const line = rawLine.trim();
            if (!line) return;
            if (line.startsWith(': job_id:')) {
                activeJobId = line.replace(': job_id:', '').trim();
                return;
            }
            if (line.startsWith(':')) {
                // Heartbeat comment
                return;
            }
            if (line.startsWith('id:')) {
                const parsedSeq = parseInt(line.replace('id:', '').trim(), 10);
                if (!isNaN(parsedSeq)) lastSeq = parsedSeq;
                return;
            }
            let msg = line;
            if (msg.startsWith('data:')) {
                msg = msg.substring(5).trim();
            }
            if (msg.startsWith('[EVENT:SUCCESS]')) {
                try {
                    exportSuccessEvent = JSON.parse(msg.replace('[EVENT:SUCCESS]', '').trim());
                } catch(e) {
                    exportSuccessEvent = { success: true };
                }
                return;
            }
            if (msg.startsWith('[EVENT:FAILED]')) {
                try {
                    exportFailedEvent = JSON.parse(msg.replace('[EVENT:FAILED]', '').trim());
                } catch(e) {
                    exportFailedEvent = { failed: true };
                }
                return;
            }
            if (msg.startsWith('[EVENT:CANCELLED]')) {
                exportCancelledEvent = true;
                return;
            }
            if (msg.startsWith('[EVENT:STAGE]')) {
                try {
                    const st = JSON.parse(msg.replace('[EVENT:STAGE]', '').trim());
                    updateExportStageUI(st);
                } catch(e) {}
                return;
            }
            if (msg.startsWith('[EVENT:PROGRESS]')) {
                try {
                    const pr = JSON.parse(msg.replace('[EVENT:PROGRESS]', '').trim());
                    updateExportProgressUI(pr);
                } catch(e) {}
                return;
            }
            if (msg.startsWith('[HEARTBEAT]')) {
                try {
                    const hb = JSON.parse(msg.replace('[HEARTBEAT]', '').trim());
                    if (hb && hb.stage) updateExportStageUI(hb);
                } catch(e) {}
                return;
            }
            if (msg.includes('ERROR:') || msg.includes('Failed') || msg.includes('🛑') || msg.includes('[LỖI')) {
                appendLog(msg, 'error');
                if (msg.includes('🛑') || msg.includes('[LỖI')) {
                    showToast(msg.replace(/^🛑\s*/, ''), 'error');
                }
            } else if (msg.includes('⚠️')) {
                appendLog(msg, 'warning');
            } else {
                appendLog(msg, 'info');
            }
        }

        async function consumeStream(streamReader) {
            while (true) {
                const { done, value } = await streamReader.read();
                if (done) break;
                lineBuffer += decoder.decode(value, { stream: true });
                const parts = lineBuffer.split('\n');
                lineBuffer = parts.pop();
                for (const pl of parts) {
                    handleSseLine(pl);
                }
            }
            if (lineBuffer.trim()) {
                handleSseLine(lineBuffer);
                lineBuffer = '';
            }
        }

        try {
            await consumeStream(response.body.getReader());
        } catch (streamErr) {
            if (streamErr.name !== 'AbortError') {
                console.warn("Stream read interrupted:", streamErr);
            }
        }

        // Status reconciliation on disconnect / EOF without terminal event
        if (isGenerating && !exportSuccessEvent && !exportFailedEvent && !exportCancelledEvent && (!exportAbortController || !exportAbortController.signal.aborted)) {
            setStatus('reconnecting');
            appendLog('⚠️ [Kết nối tiến độ] Mất kết nối luồng SSE — đang kiểm tra lại trạng thái tác vụ từ máy chủ...', 'warning');

            for (let attempt = 1; attempt <= 6; attempt++) {
                try {
                    await new Promise(r => setTimeout(r, Math.min(1000 * Math.pow(1.5, attempt - 1), 5000)));
                    const statusUrl = activeJobId ? `/api/export/jobs/${activeJobId}` : '/api/export_status';
                    const pollRes = await fetch(statusUrl);
                    if (pollRes.ok) {
                        const jobStatus = await pollRes.json();
                        const info = jobStatus.job || jobStatus;
                        const stState = info.state || (info.active ? 'running' : 'succeeded');

                        if (stState === 'succeeded' || (info.output_path && !info.active)) {
                            exportSuccessEvent = {
                                path: info.output_path,
                                size_mb: info.size_mb,
                                history_id: info.history_id
                            };
                            break;
                        } else if (stState === 'failed') {
                            exportFailedEvent = { reason: info.error || 'Xuất video thất bại' };
                            break;
                        } else if (stState === 'cancelled') {
                            exportCancelledEvent = true;
                            break;
                        } else if (stState === 'running' || info.active) {
                            appendLog(`🔄 [Kết nối tiến độ] Tác vụ vẫn đang chạy trên máy chủ (${info.stage || 'Xử lý'}). Đang thử tái kết nối (${attempt}/6)...`, 'info');
                            if (activeJobId) {
                                try {
                                    const rcRes = await fetch(`/api/export/jobs/${activeJobId}/events?after=${lastSeq}`, { signal: exportAbortController.signal });
                                    if (rcRes.ok) {
                                        setStatus('running');
                                        await consumeStream(rcRes.body.getReader());
                                        if (exportSuccessEvent || exportFailedEvent || exportCancelledEvent) {
                                            break;
                                        }
                                    }
                                } catch (rcErr) {
                                    console.warn("Reconnect attempt failed:", rcErr);
                                }
                            }
                        }
                    }
                } catch (pollErr) {
                    console.warn(`Lần kiểm tra trạng thái ${attempt}/6 thất bại:`, pollErr);
                }
            }
        }

        if (isGenerating) {
            isGenerating = false;
            if (exportSuccessEvent) {
                appendLog('--- HOÀN THÀNH ---', 'info');
                setStatus('ready');
                
                // Update player to show output video
                let fullOutPath = exportSuccessEvent.path || (config.outputDir ? (config.outputDir + '\\' + config.outputName) : ('output\\' + config.outputName));
                videoPlayer.src = `/api/video?path=${encodeURIComponent(fullOutPath)}`;
                videoPlayer.load();
                videoPlayer.play();
                if (subPreviewBox) subPreviewBox.style.display = 'none';
                if (dynamicBlurOverlay) {
                    dynamicBlurOverlay.style.opacity = '0';
                    dynamicBlurOverlay.style.visibility = 'hidden';
                }
                showToast('Xuất video hoàn tất thành công!', 'success');
            } else if (exportCancelledEvent) {
                setStatus('ready');
                appendLog('🛑 Đã dừng tiến trình xuất video.', 'warning');
                showToast('Đã dừng tiến trình xuất video!', 'info');
            } else if (exportFailedEvent) {
                setStatus('error');
                appendLog(`🛑 Quá trình xuất video thất bại: ${exportFailedEvent.reason || 'Lỗi không xác định'}`, 'error');
                showToast(`Xuất video thất bại: ${exportFailedEvent.reason || 'Vui lòng kiểm tra log'}`, 'error');
            } else {
                setStatus('error');
                appendLog('🛑 Quá trình xuất video không thể xác nhận trạng thái từ máy chủ.', 'error');
                showToast('Xuất video gặp sự cố kết nối! Vui lòng kiểm tra System Log.', 'error');
            }
        }
        
    } catch (e) {
        if (e.name === 'AbortError') {
            appendLog('🛑 Đã dừng tiến trình xuất video theo yêu cầu.', 'warning');
            setStatus('ready');
        } else {
            console.error(e);
            appendLog('Lỗi khởi tạo hoặc kết nối xuất video: ' + e.message, 'error');
            setStatus('error');
        }
        isGenerating = false;
    }
}

// Initial state
setStatus('ready');

// Reload Button
const reloadBtn = document.getElementById('reloadBtn');
if (reloadBtn) {
    reloadBtn.addEventListener('click', () => {
        window.location.reload();
    });
}

// Video Player Controls Logic
const playBtn = document.querySelector('.play-btn');
const volumeSlider = document.getElementById('volumeSlider');
const timeDisplay = document.querySelector('.time-display');
const timeline = document.getElementById('videoTimeline');
const btnPreviewOriginal = document.getElementById('btnPreviewOriginal');
const btnPreviewEdited = document.getElementById('btnPreviewEdited');

let isSeekingTimeline = false;

if (videoPlayer) {
    videoPlayer.addEventListener('play', () => {
        if (playBtn) playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
    });

    videoPlayer.addEventListener('pause', () => {
        if (playBtn) playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    });
}

if (playBtn) {
    playBtn.addEventListener('click', () => {
        if (videoPlayer) {
            if (videoPlayer.paused) {
                if (!videoPlayer.src || videoPlayer.src === '' || videoPlayer.src.endsWith('/')) {
                    if (editorInputVideoPath && editorInputVideoPath.value) {
                        videoPlayer.src = `/api/video?path=${encodeURIComponent(editorInputVideoPath.value)}`;
                    }
                }
                videoPlayer.play();
            } else {
                videoPlayer.pause();
            }
        }
    });
}

if (volumeSlider && videoPlayer) {
    volumeSlider.addEventListener('input', (e) => {
        videoPlayer.volume = e.target.value;
    });
}

// ═══════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════
// Dynamic Blur Preview System (Chữ ngắn -> blur ngắn, chữ dài -> blur dài, Binary-Search Zero-Lag 60fps)
// ═══════════════════════════════════════════════════════
const dynamicBlurOverlay = document.getElementById('dynamicBlurOverlay');
let _cachedSortedSubs = []; // Cached pre-processed subtitle intervals for O(log N) lookup

function calculateSubtitleWidthPercent(text) {
    if (!text) return 35;
    const cleanText = text.trim();
    if (!cleanText) return 35;
    
    let units = 0;
    for (let i = 0; i < cleanText.length; i++) {
        const code = cleanText.charCodeAt(i);
        // Ký tự CJK (Trung, Nhật, Hàn)
        if ((code >= 0x4E00 && code <= 0x9FFF) || 
            (code >= 0x3400 && code <= 0x4DBF) || 
            (code >= 0x3040 && code <= 0x30FF) || 
            (code >= 0xAC00 && code <= 0xD7AF)) {
            units += 2.9; // ~2.9% width per CJK char
        } else if (cleanText[i] === ' ') {
            units += 0.9;
        } else {
            units += 1.45; // ~1.45% width per Latin / digit / punct
        }
    }
    return Math.min(92, Math.max(10, units * 1.02 + 4.5));
}

function rebuildDynamicBlurIndex() {
    _cachedSortedSubs = [];
    if (typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0) {
        updateAiScanBadge();
        return;
    }
    
    // Sắp xếp và tính toán trước độ rộng tối thiểu an toàn (Zero CPU overhead khi render 60fps)
    const valid = srtData
        .filter(s => s.startSeconds != null && s.endSeconds != null && s.endSeconds > s.startSeconds)
        .map(s => {
            const origTxt = s.original_text || s.raw_text || s.text || '';
            const aiBox = s.aiBox || null;
            let widthPct = calculateSubtitleWidthPercent(origTxt);
            let leftPct = null;
            const visualStart = s.visual_start != null ? s.visual_start : (aiBox && aiBox.visual_start != null ? aiBox.visual_start : null);
            const visualEnd = s.visual_end != null ? s.visual_end : (aiBox && aiBox.visual_end != null ? aiBox.visual_end : null);
            
            if (aiBox && typeof aiBox === 'object' && typeof aiBox.w_pct === 'number' && aiBox.w_pct > 0) {
                const rawAiW = aiBox.w_pct;
                const rawAiX = aiBox.x_pct != null ? aiBox.x_pct : 20;
                const center = rawAiX + (rawAiW / 2.0);
                let targetW = rawAiW;
                if (origTxt) {
                    const estOrigW = calculateSubtitleWidthPercent(origTxt);
                    targetW = Math.max(targetW, estOrigW);
                }
                const padW = Math.max(1.5, Math.min(4.0, targetW * 0.05));
                widthPct = Math.min(98, targetW + (padW * 2));
                leftPct = Math.max(0, Math.min(100 - widthPct, center - (widthPct / 2.0)));
            }
            
            return {
                id: s.id,
                start: s.startSeconds,
                end: s.endSeconds,
                visualStart: visualStart,
                visualEnd: visualEnd,
                text: origTxt,
                aiBox: aiBox,
                widthPct: widthPct,
                leftPct: leftPct
            };
        })
        .sort((a, b) => a.start - b.start);
        
    _cachedSortedSubs = valid;
    updateAiScanBadge();
}

function getActiveSubtitleAtTime(currentTime) {
    if (!_cachedSortedSubs || _cachedSortedSubs.length === 0) {
        if (typeof srtData !== 'undefined' && Array.isArray(srtData) && srtData.length > 0) {
            rebuildDynamicBlurIndex();
        }
        if (!_cachedSortedSubs || _cachedSortedSubs.length === 0) return null;
    }
    
    // Đọc bù thời gian (Sync Offset) và đệm thời gian (Padding) từ thanh trượt
    const offsetMs = parseFloat(document.getElementById('blurLeadOffset')?.value) ?? -180;
    const paddingMs = parseFloat(document.getElementById('blurPadding')?.value) ?? 220;
    const offsetSec = offsetMs / 1000.0;
    const paddingSec = paddingMs / 1000.0;

    const subs = _cachedSortedSubs;
    const n = subs.length;

    // Binary Search O(log N) siêu tốc (< 0.02ms cho 5000+ câu)
    let low = 0, high = n - 1;
    let candidateIdx = 0;

    while (low <= high) {
        const mid = (low + high) >> 1;
        const sub = subs[mid];
        const baseStart = (sub.visualStart != null) ? Math.min(sub.start, sub.visualStart) : sub.start;
        const effStart = Math.max(0, baseStart + offsetSec);

        if (effStart <= currentTime) {
            candidateIdx = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }

    // Quét vùng lân cận hẹp (tối đa 4 câu xung quanh candidateIdx) để bắt chính xác hoặc nối mờ liên tục
    const checkStart = Math.max(0, candidateIdx - 2);
    const checkEnd = Math.min(n - 1, candidateIdx + 2);

    for (let i = checkStart; i <= checkEnd; i++) {
        const sub = subs[i];
        const baseStart = (sub.visualStart != null) ? Math.min(sub.start, sub.visualStart) : sub.start;
        const effStart = Math.max(0, baseStart + offsetSec);
        const baseEnd = (sub.visualEnd != null) ? Math.max(sub.end, sub.visualEnd) : sub.end;
        const effEnd = baseEnd + paddingSec;

        if (currentTime >= effStart && currentTime <= effEnd) {
            return sub;
        }

        // Smart Gap Bridging: Nếu khoảng trống giữa câu hiện tại và câu kế tiếp <= 0.75s, duy trì làm mờ liên tục chống chớp giật
        if (i < n - 1) {
            const nextSub = subs[i + 1];
            const nextBaseStart = (nextSub.visualStart != null) ? Math.min(nextSub.start, nextSub.visualStart) : nextSub.start;
            const nextEffStart = Math.max(0, nextBaseStart + offsetSec);
            if (currentTime > effEnd && currentTime < nextEffStart && (nextEffStart - effEnd) <= 0.75) {
                return (currentTime - effEnd < nextEffStart - currentTime) ? sub : nextSub;
            }
        }
    }

    return null;
}

let _lastBlurState = {
    visible: false,
    subId: null,
    left: null,
    top: null,
    width: null,
    height: null,
    blur: null,
    aiBorder: false
};

function updateDynamicBlurOverlayVisibility() {
    if (!dynamicBlurOverlay) return;
    const isSubEnabled = document.getElementById('subtitlesEnabled')?.checked ?? true;
    const blurCheckbox = document.getElementById('reviewBlurOriginalSubtitles');
    const isBlurEnabled = isSubEnabled && Boolean(blurCheckbox && blurCheckbox.checked);
    
    // Nếu người dùng đang bấm nút "Chỉnh vùng làm mờ" (isEditingBlurBox) hoặc vẽ vùng làm mờ
    const isEditing = (typeof isEditingBlurBox !== 'undefined' && isEditingBlurBox) || 
                      (typeof drawMode !== 'undefined' && drawMode === 'blur');

    if (!isBlurEnabled && !isEditing) {
        dynamicBlurOverlay.style.opacity = '0';
        dynamicBlurOverlay.style.visibility = 'hidden';
        _lastBlurState.visible = false;
        _lastBlurState.subId = null;
        return;
    }
    
    const currentTime = videoPlayer ? videoPlayer.currentTime : 0;
    const activeSub = getActiveSubtitleAtTime(currentTime);
    
    // Khi đang chỉnh mờ trực tiếp (isEditing), vẫn hiển thị dynamicBlurOverlay theo currentRegion để người dùng thấy rõ
    if (!activeSub && !isEditing) {
        if (_lastBlurState.visible) {
            dynamicBlurOverlay.style.opacity = '0';
            dynamicBlurOverlay.style.visibility = 'hidden';
            _lastBlurState.visible = false;
            _lastBlurState.subId = null;
        }
        return;
    }
    
    // 1. Lấy thông số vùng làm mờ (Ưu tiên slider và currentRegion do người dùng căn chỉnh)
    const sliderW = parseFloat(document.getElementById('blurWidth')?.value);
    const sliderH = parseFloat(document.getElementById('blurHeight')?.value);
    const sliderX = parseFloat(document.getElementById('blurXPos')?.value);
    const sliderY = parseFloat(document.getElementById('blurYPos')?.value);

    const regionY = !isNaN(sliderY) ? sliderY : ((currentRegion && typeof currentRegion.y === 'number') ? currentRegion.y : 81.5);
    const regionH = !isNaN(sliderH) ? sliderH : ((currentRegion && typeof currentRegion.h === 'number') ? currentRegion.h : 9.5);
    const regionX = !isNaN(sliderX) ? sliderX : ((currentRegion && typeof currentRegion.x === 'number') ? currentRegion.x : 20);
    const regionW = !isNaN(sliderW) ? sliderW : ((currentRegion && typeof currentRegion.w === 'number') ? currentRegion.w : 60);

    const isAiScanEnabled = document.getElementById('blurUseAiScan')?.checked ?? true;
    const centerX = regionX + (regionW / 2.0);

    let ocrY = regionY;
    let ocrH = regionH;
    let widthPct = regionW;
    let leftPct = regionX;

    const blurModeVal = document.querySelector('input[name="blurModeRadio"]:checked')?.value || 'fixed';
    const isFixedBlurMode = (blurModeVal === 'fixed');

    if (!isEditing && activeSub) {
        if (isFixedBlurMode) {
            // Chế độ cố định: giữ nguyên kích thước đã quét hoặc người dùng kéo chỉnh thủ công
            widthPct = regionW;
            leftPct = regionX;
            ocrY = regionY;
            ocrH = regionH;
        } else if (isAiScanEnabled && activeSub.aiBox && typeof activeSub.aiBox.w_pct === 'number' && activeSub.aiBox.w_pct > 0) {
            const rawAiW = activeSub.aiBox.w_pct;
            const rawAiX = activeSub.aiBox.x_pct != null ? activeSub.aiBox.x_pct : (centerX - rawAiW / 2.0);
            const subCenterX = rawAiX + (rawAiW / 2.0);

            let targetW = rawAiW;
            const origCandidate = activeSub.original_text || activeSub.raw_text || activeSub.text || '';
            if (origCandidate) {
                const estOrigW = calculateSubtitleWidthPercent(origCandidate);
                targetW = Math.max(targetW, estOrigW);
            }
            
            const padW = Math.max(1.5, Math.min(4.0, targetW * 0.05));
            widthPct = Math.min(98, targetW + (padW * 2));
            leftPct = Math.max(0, Math.min(100 - widthPct, subCenterX - (widthPct / 2.0)));

            if (activeSub.aiBox.y_pct != null && activeSub.aiBox.h_pct != null) {
                const rawAiY = activeSub.aiBox.y_pct;
                const rawAiH = activeSub.aiBox.h_pct;
                const subCenterY = rawAiY + (rawAiH / 2.0);
                // Đệm an toàn ôm khít chiều cao dòng chữ thực tế
                const padH = Math.max(0.8, Math.min(2.5, rawAiH * 0.18));
                
                // Cho phép người dùng tùy chỉnh chiều cao hộp làm mờ qua slider blurHeight / khung kéo (regionH)
                // trong khi chiều ngang vẫn tự động bám theo câu chữ AI (widthPct)
                const isMulti = (origCandidate.includes('\n') || origCandidate.includes('\\N') || origCandidate.includes('\\n')) && (typeof regionH === 'number' && rawAiH > regionH);
                if (typeof regionH === 'number' && regionH > 0) {
                    if (isMulti) {
                        ocrH = Math.min(40, Math.max(regionH, rawAiH + (padH * 2.0)));
                    } else {
                        ocrH = Math.min(40, Math.max(2.0, regionH));
                    }
                } else {
                    ocrH = Math.min(35, Math.max(3.0, rawAiH + (padH * 2.0)));
                }
                ocrY = Math.max(0, Math.min(98 - ocrH, subCenterY - (ocrH / 2.0)));
            }
        } else {
            // 2. Tự động tính kích thước theo câu chữ (Dynamic Text-based Blur)
            const origCandidate = activeSub.original_text || activeSub.raw_text || activeSub.text || activeSub.translation || '';
            if (origCandidate) {
                const textEstWidth = calculateSubtitleWidthPercent(origCandidate);
                widthPct = Math.min(regionW, Math.max(15, textEstWidth));
                leftPct = Math.max(0, Math.min(100 - widthPct, centerX - (widthPct / 2.0)));

                // Tự động điều chỉnh chiều cao theo số dòng text:
                const isMulti = (origCandidate.includes('\n') || origCandidate.includes('\\N'));
                if (isMulti) {
                    ocrH = Math.min(25, Math.max(regionH, 11));
                    ocrY = Math.max(0, Math.min(98 - ocrH, regionY - (ocrH - regionH) / 2.0));
                } else {
                    ocrH = Math.min(regionH, 7.5);
                    ocrY = regionY;
                }
            } else {
                widthPct = regionW;
                leftPct = regionX;
                ocrY = regionY;
                ocrH = regionH;
            }
        }
    } else {
        // Chế độ đang kéo chỉnh vùng (isEditing):
        widthPct = regionW;
        leftPct = regionX;
        ocrY = regionY;
        ocrH = regionH;
    }
    
    const blurVal = parseInt(document.getElementById('dynBlurIntensity')?.value) || parseInt(document.getElementById('subBgBlur')?.value) || 15;
    const hasAiBorder = !!(activeSub && activeSub.aiBox && isAiScanEnabled && !isEditing);

    // STATE DIFF CHECK: Nếu trạng thái giống hệt frame trước và không đang chỉnh sửa, không đụng vào DOM / Shader GPU!
    if (
        !isEditing &&
        _lastBlurState.visible === true &&
        _lastBlurState.subId === (activeSub ? activeSub.id : null) &&
        _lastBlurState.left === leftPct &&
        _lastBlurState.top === ocrY &&
        _lastBlurState.width === widthPct &&
        _lastBlurState.height === ocrH &&
        _lastBlurState.blur === blurVal &&
        _lastBlurState.aiBorder === hasAiBorder
    ) {
        return; // ZERO DOM mutation, ZERO GPU Shader recomposition!
    }

    _lastBlurState = {
        visible: true,
        subId: activeSub ? activeSub.id : (isEditing ? '__editing__' : null),
        left: leftPct,
        top: ocrY,
        width: widthPct,
        height: ocrH,
        blur: blurVal,
        aiBorder: hasAiBorder
    };

    // 4. Cập nhật style cho dynamicBlurOverlay (Zero-Reflow GPU composite, Video-AR-aware)
    const vRect = (typeof getVideoContentRect === 'function') ? getVideoContentRect() : null;
    const finalLeft = vRect ? ((vRect.videoX + (leftPct / 100) * vRect.videoW) / vRect.wrapperW * 100) : leftPct;
    const finalTop = vRect ? ((vRect.videoY + (ocrY / 100) * vRect.videoH) / vRect.wrapperH * 100) : ocrY;
    const finalWidth = vRect ? (((widthPct / 100) * vRect.videoW) / vRect.wrapperW * 100) : widthPct;
    const finalHeight = vRect ? (((ocrH / 100) * vRect.videoH) / vRect.wrapperH * 100) : ocrH;

    dynamicBlurOverlay.style.backdropFilter = `blur(${blurVal}px)`;
    dynamicBlurOverlay.style.webkitBackdropFilter = `blur(${blurVal}px)`;
    dynamicBlurOverlay.style.top = `${finalTop}%`;
    dynamicBlurOverlay.style.height = `${finalHeight}%`;
    dynamicBlurOverlay.style.left = `${finalLeft}%`;
    dynamicBlurOverlay.style.width = `${finalWidth}%`;
    dynamicBlurOverlay.style.bottom = 'auto';
    dynamicBlurOverlay.style.borderRadius = '6px';
    dynamicBlurOverlay.style.opacity = '1';
    dynamicBlurOverlay.style.visibility = 'visible';

    // Hiệu ứng viền/phát sáng khi khớp tọa độ AI
    if (hasAiBorder) {
        dynamicBlurOverlay.style.border = '1px dashed rgba(56, 189, 248, 0.6)';
        dynamicBlurOverlay.style.boxShadow = '0 0 12px rgba(14, 165, 233, 0.4)';
    } else {
        dynamicBlurOverlay.style.border = 'none';
        dynamicBlurOverlay.style.boxShadow = '0 0 8px rgba(0,0,0,0.1)';
    }
}

function updateDynamicBlurIntervals() {
    rebuildDynamicBlurIndex();
    updateDynamicBlurOverlayVisibility();
}

function setManualBlurRegion() {
    // Không tự động hủy checked của blurUseAiScan khi người dùng điều chỉnh khung định vị
    updateAiScanBadge();
}

function updateBlurModeHint() {
    const aiScanToggle = document.getElementById('blurUseAiScan');
    const hint = document.getElementById('blurAiScanHint');
    if (!hint || !aiScanToggle) return;
    hint.textContent = aiScanToggle.checked
        ? 'Tự quét pixel ôm khít chữ theo chiều ngang. Bạn có thể tự do chỉnh chiều cao hộp mờ ở thanh trượt ↕️ Cao (H).'
        : 'Đang dùng vùng thủ công: kích thước X, Y, W, H được giữ nguyên ở preview và video xuất.';
}

// ==========================================
// AI PREVIEW SCAN CONTROLLERS
// ==========================================
function updateAiScanBadge() {
    const badge = document.getElementById('aiScanBadge');
    const resetBtn = document.getElementById('btnResetAiBoxes');
    if (!badge) return;
    
    if (typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0) {
        badge.textContent = '0 câu đã quét AI';
        if (resetBtn) resetBtn.style.display = 'none';
        return;
    }
    
    const scannedCount = srtData.filter(s => s.aiBox && typeof s.aiBox === 'object' && s.aiBox.w_pct > 0).length;
    const totalCount = srtData.length;
    
    badge.textContent = `${scannedCount}/${totalCount} câu đã quét AI`;
    if (scannedCount > 0) {
        badge.style.background = 'rgba(16, 185, 129, 0.18)';
        badge.style.color = '#34d399';
        badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
        if (resetBtn) resetBtn.style.display = 'inline-block';
    } else {
        badge.style.background = 'rgba(56, 189, 248, 0.12)';
        badge.style.color = '#38bdf8';
        badge.style.borderColor = 'rgba(56, 189, 248, 0.25)';
        if (resetBtn) resetBtn.style.display = 'none';
    }
}

async function scanAiCurrentFrame() {
    const videoPath = (editorInputVideoPath && editorInputVideoPath.value) ? editorInputVideoPath.value.trim() : '';
    if (!videoPath) {
        showToast("Vui lòng chọn video đầu vào trước khi quét!", "warning");
        return;
    }
    
    const currentTime = videoPlayer ? videoPlayer.currentTime : 0;
    const region = currentRegion || { x: 20, y: 81.5, w: 60, h: 9.5 };
    
    const btn = document.getElementById('btnScanAiCurrentFrame');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-spinner" style="display:inline-block; width:10px; height:10px; border:2px solid #38bdf8; border-top-color:transparent; border-radius:50%; animation:spin 0.6s linear infinite; margin-right:4px;"></span> Quét...`;
    }
    
    try {
        const res = await fetch('/api/ocr/scan_preview_single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: videoPath,
                timestamp: currentTime,
                region: region
            })
        });
        
        const data = await res.json();
        if (data.success && data.box) {
            // Find active subtitle or assign to closest
            if (typeof srtData !== 'undefined' && Array.isArray(srtData) && srtData.length > 0) {
                const sub = srtData.find(s => currentTime >= s.startSeconds && currentTime <= (s.endSeconds + 0.3)) || srtData[0];
                if (sub) {
                    sub.aiBox = data.box;
                    if (data.box.visual_start !== undefined) {
                        sub.visual_start = data.box.visual_start;
                    }
                    if (data.box.visual_end !== undefined) {
                        sub.visual_end = data.box.visual_end;
                    }
                }
            }
            
            // Auto check blurUseAiScan
            const chkAi = document.getElementById('blurUseAiScan');
            if (chkAi) chkAi.checked = true;
            
            updateDynamicBlurIntervals();
            updateAiScanBadge();
            showToast(`🎯 Quét AI thành công! (X: ${data.box.x_pct}%, W: ${data.box.w_pct}%)`, "success");
        } else {
            showToast(data.message || data.error || "Không phát hiện chữ phụ đề ở frame này.", "info");
        }
    } catch (err) {
        showToast("Lỗi khi quét AI: " + err.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg> <span>Quét Frame Này</span>`;
        }
    }
}

let aiScanAbortController = null;

async function scanAiAllSubtitles() {
    const videoPath = (editorInputVideoPath && editorInputVideoPath.value) ? editorInputVideoPath.value.trim() : '';
    if (!videoPath) {
        showToast("Vui lòng chọn video đầu vào trước khi quét!", "warning");
        return;
    }
    
    if (typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0) {
        showToast("Chưa có danh sách phụ đề SRT để quét. Hãy tải SRT hoặc trích xuất OCR trước!", "warning");
        return;
    }
    
    const btnAll = document.getElementById('btnScanAiAllSubs');
    const btnCur = document.getElementById('btnScanAiCurrentFrame');
    const progWrap = document.getElementById('aiScanProgressWrapper');
    const progBar = document.getElementById('aiScanProgressBar');
    const progText = document.getElementById('aiScanPercentText');
    const statusText = document.getElementById('aiScanStatusText');
    
    if (aiScanAbortController) {
        aiScanAbortController.abort();
        aiScanAbortController = null;
        if (btnAll) {
            btnAll.classList.remove('btn-danger');
            btnAll.classList.add('primary-cyan');
            btnAll.innerHTML = `<span>🎯 Quét Toàn Bộ Sub</span>`;
        }
        if (btnCur) btnCur.disabled = false;
        if (progWrap) progWrap.style.display = 'none';
        showToast("Đã dừng quét AI.", "warning");
        return;
    }
    
    aiScanAbortController = new AbortController();
    
    if (btnAll) {
        btnAll.classList.remove('primary-cyan');
        btnAll.classList.add('btn-danger');
        btnAll.innerHTML = `<span>🛑 Dừng Quét</span>`;
    }
    if (btnCur) btnCur.disabled = true;
    if (progWrap) progWrap.style.display = 'flex';
    if (progBar) progBar.style.width = '0%';
    if (progText) progText.textContent = '0%';
    if (statusText) statusText.textContent = `Đang chuẩn bị quét ${srtData.length} câu...`;
    
    const region = currentRegion || { x: 20, y: 81.5, w: 60, h: 9.5 };
    
    try {
        const res = await fetch('/api/ocr/scan_preview_boxes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: videoPath,
                region: region,
                output_dir: (document.getElementById('outputDir')?.value || '').trim(),
                subtitles: srtData.map((s, idx) => ({
                    id: s.id || (idx + 1),
                    startSeconds: s.startSeconds,
                    endSeconds: s.endSeconds,
                    text: s.text || s.original_text || '',
                    aiBox: s.aiBox || null
                }))
            }),
            signal: aiScanAbortController.signal
        });
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n\n');
            buffer = lines.pop();
            
            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.substring(6));
                        if (event.type === 'progress') {
                            const idx = event.index;
                            if (srtData[idx]) {
                                if (event.box) {
                                    srtData[idx].aiBox = event.box;
                                    if (event.box.visual_start !== undefined) {
                                        srtData[idx].visual_start = event.box.visual_start;
                                    }
                                    if (event.box.visual_end !== undefined) {
                                        srtData[idx].visual_end = event.box.visual_end;
                                    }
                                }
                            }
                            if (progBar) progBar.style.width = `${event.pct}%`;
                            if (progText) progText.textContent = `${event.pct}%`;
                            const tag = event.cached ? '⚡ Tái sử dụng' : 'Đang quét';
                            if (statusText) statusText.textContent = `${tag} ${event.index + 1}/${event.total} câu...`;
                            updateAiScanBadge();
                        } else if (event.type === 'done') {
                            if (progBar) progBar.style.width = '100%';
                            if (progText) progText.textContent = '100%';
                            if (statusText) statusText.textContent = `Hoàn thành (${event.detected_count}/${event.total_scanned} câu)!`;
                            
                            // Auto check blurUseAiScan
                            const chkAi = document.getElementById('blurUseAiScan');
                            if (chkAi) chkAi.checked = true;
                            
                            updateDynamicBlurIntervals();
                            showToast(`🎉 Đã lưu & cập nhật toạ độ AI cho ${event.detected_count}/${event.total_scanned} câu phụ đề!`, "success");
                            
                            setTimeout(() => {
                                if (progWrap) progWrap.style.display = 'none';
                            }, 2500);
                        } else if (event.type === 'error') {
                            showToast(`Lỗi quét AI: ${event.message}`, "error");
                        }
                    } catch (pe) {
                        console.error("Error parsing scan SSE event:", pe);
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            showToast(`Lỗi kết nối quét AI: ${err.message}`, "error");
        }
    } finally {
        aiScanAbortController = null;
        if (btnAll) {
            btnAll.classList.remove('btn-danger');
            btnAll.classList.add('primary-cyan');
            btnAll.innerHTML = `<span>🎯 Quét Toàn Bộ Sub</span>`;
        }
        if (btnCur) btnCur.disabled = false;
        updateDynamicBlurIntervals();
        updateAiScanBadge();
    }
}

async function resetAiBoxes() {
    if (typeof srtData === 'undefined' || !Array.isArray(srtData)) return;
    srtData.forEach(s => {
        delete s.aiBox;
        delete s.visual_start;
        delete s.visual_end;
    });
    const videoPath = editorInputVideoPath?.value || '';
    const outDirVal = (document.getElementById('outputDir')?.value || '').trim();
    if (videoPath) {
        try {
            await fetch('/api/editor/clear_cache_boxes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_path: videoPath, output_dir: outDirVal })
            });
        } catch (e) {}
    }
    updateDynamicBlurIntervals();
    updateAiScanBadge();
    showToast("Đã xóa toạ độ AI và làm mới bộ nhớ tạm.", "info");
}

document.getElementById('btnScanAiCurrentFrame')?.addEventListener('click', scanAiCurrentFrame);
document.getElementById('btnScanAiAllSubs')?.addEventListener('click', scanAiAllSubtitles);
document.getElementById('btnResetAiBoxes')?.addEventListener('click', resetAiBoxes);
document.getElementById('blurUseAiScan')?.addEventListener('change', (e) => {
    updateBlurModeHint();
    updateDynamicBlurIntervals();
});

// Bấm vào khung làm mờ trên màn hình để bật ngay 8 điểm neo co giãn điều chỉnh
if (dynamicBlurOverlay) {
    dynamicBlurOverlay.style.cursor = 'pointer';
    dynamicBlurOverlay.style.pointerEvents = 'auto';
    dynamicBlurOverlay.title = 'Bấm vào đây để điều chỉnh vùng làm mờ trên màn hình (8 hướng)';

    dynamicBlurOverlay.addEventListener('click', (e) => {
        e.stopPropagation();
        if (typeof showBlurAdjustBox === 'function') {
            showBlurAdjustBox(true);
        }
    });
}

// Đồng bộ hiển thị phụ đề trực tiếp ở tốc độ khung hình cao (Zero-Lag Subtitle Sync)
function updateSubtitleLivePlayback(currentTime) {
    if (!subPreviewBox) return;
    const isSubEnabled = document.getElementById('subtitlesEnabled')?.checked ?? true;
    if (!isSubEnabled) {
        if (subPreviewBox.style.display !== 'none') {
            subPreviewBox.style.display = 'none';
        }
        window._lastPreviewSubId = null;
        return;
    }
    if (!Array.isArray(srtData) || srtData.length === 0) return;
    
    // Quick Binary Search for active subtitle in O(log N)
    let low = 0, high = srtData.length - 1;
    let foundSub = null;
    while (low <= high) {
        const mid = (low + high) >> 1;
        const s = srtData[mid];
        if (currentTime >= s.startSeconds && currentTime <= s.endSeconds) {
            foundSub = s;
            break;
        } else if (currentTime < s.startSeconds) {
            high = mid - 1;
        } else {
            low = mid + 1;
        }
    }
    
    if (foundSub) {
        if (window._lastPreviewSubId !== foundSub.id) {
            window._lastPreviewSubId = foundSub.id;
            const displayText = foundSub.translation || foundSub.text;
            if (typeof setSubtitlePreviewText === 'function') {
                setSubtitlePreviewText(displayText);
            } else {
                let textSpan = subPreviewBox.querySelector('.sub-text-inner');
                if (textSpan) textSpan.textContent = displayText;
            }
            subPreviewBox.style.display = 'flex';
            if (typeof applySubStylesToElement === 'function') {
                applySubStylesToElement(subPreviewBox);
            }
        }
    } else {
        const isDraw = typeof drawMode !== 'undefined' && drawMode === 'sub';
        const isEdit = typeof isEditingSubBox !== 'undefined' && isEditingSubBox;
        if (isDraw || isEdit) {
            if (window._lastPreviewSubId !== '__placeholder__') {
                window._lastPreviewSubId = '__placeholder__';
                if (typeof setSubtitlePreviewText === 'function') {
                    setSubtitlePreviewText('Phụ đề mẫu');
                } else {
                    let textSpan = subPreviewBox.querySelector('.sub-text-inner');
                    if (textSpan) textSpan.textContent = 'Phụ đề mẫu';
                }
                subPreviewBox.style.display = 'flex';
                if (typeof applySubStylesToElement === 'function') {
                    applySubStylesToElement(subPreviewBox);
                }
            }
        } else {
            if (window._lastPreviewSubId !== null) {
                window._lastPreviewSubId = null;
                if (typeof setSubtitlePreviewText === 'function') {
                    setSubtitlePreviewText('');
                } else {
                    let textSpan = subPreviewBox.querySelector('.sub-text-inner');
                    if (textSpan) textSpan.textContent = '';
                }
                subPreviewBox.style.display = 'none';
            }
        }
    }
}

// Smooth Animation Loop (~30-60fps) với state caching giúp loại bỏ 100% hiện tượng nghẽn GPU Compositor
let blurAnimFrameId = null;
let _lastBlurAnimTime = 0;
function syncBlurPreviewHighPrecision(now) {
    if (!now || (now - _lastBlurAnimTime) >= 28) {
        _lastBlurAnimTime = now || performance.now();
        updateDynamicBlurOverlayVisibility();
        if (videoPlayer) {
            updateSubtitleLivePlayback(videoPlayer.currentTime);
        }
    }
    if (videoPlayer && !videoPlayer.paused && !videoPlayer.ended) {
        blurAnimFrameId = requestAnimationFrame(syncBlurPreviewHighPrecision);
    }
}

videoPlayer.addEventListener('play', () => {
    if (blurAnimFrameId) cancelAnimationFrame(blurAnimFrameId);
    blurAnimFrameId = requestAnimationFrame(syncBlurPreviewHighPrecision);
});
videoPlayer.addEventListener('playing', () => {
    if (blurAnimFrameId) cancelAnimationFrame(blurAnimFrameId);
    blurAnimFrameId = requestAnimationFrame(syncBlurPreviewHighPrecision);
});
videoPlayer.addEventListener('pause', () => {
    if (blurAnimFrameId) cancelAnimationFrame(blurAnimFrameId);
    updateDynamicBlurOverlayVisibility();
});
videoPlayer.addEventListener('seeked', updateDynamicBlurOverlayVisibility);
videoPlayer.addEventListener('ended', () => {
    if (blurAnimFrameId) cancelAnimationFrame(blurAnimFrameId);
    updateDynamicBlurOverlayVisibility();
});

// Slider event listeners for real-time fine-tuning
const blurLeadOffsetSlider = document.getElementById('blurLeadOffset');
const blurLeadOffsetVal = document.getElementById('blurLeadOffsetVal');
if (blurLeadOffsetSlider && blurLeadOffsetVal) {
    blurLeadOffsetSlider.addEventListener('input', (e) => {
        blurLeadOffsetVal.textContent = `${e.target.value}ms`;
        updateDynamicBlurOverlayVisibility();
    });
}

const blurPaddingSlider = document.getElementById('blurPadding');
const blurPaddingVal = document.getElementById('blurPaddingVal');
if (blurPaddingSlider && blurPaddingVal) {
    blurPaddingSlider.addEventListener('input', (e) => {
        blurPaddingVal.textContent = `${e.target.value}ms`;
        updateDynamicBlurOverlayVisibility();
    });
}

const blurYPosSlider = document.getElementById('blurYPos');
const blurYPosVal = document.getElementById('blurYPosVal');
if (blurYPosSlider && blurYPosVal) {
    blurYPosSlider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        blurYPosVal.textContent = `${val}%`;
        if (currentRegion) {
            currentRegion.y = val;
        } else {
            currentRegion = { x: 20, y: val, w: 60, h: 9.5 };
        }
        updateDynamicBlurOverlayVisibility();
    });
}

// Collapsible Sub Custom Region Controls (Kích thước & Vị trí)
const subCustomRegionHeader = document.getElementById('subCustomRegionHeader');
const subCustomRegionBody = document.getElementById('subCustomRegionBody');
const subCustomRegionChevron = document.getElementById('subCustomRegionChevron');
if (subCustomRegionHeader && subCustomRegionBody) {
    subCustomRegionHeader.addEventListener('click', () => {
        const isHidden = subCustomRegionBody.style.display === 'none';
        subCustomRegionBody.style.display = isHidden ? 'flex' : 'none';
        if (subCustomRegionChevron) {
            subCustomRegionChevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
        }
    });
}

// Collapsible Dynamic Blur Config (Làm mờ động)
const dynamicBlurHeader = document.getElementById('dynamicBlurHeader');
const dynamicBlurSubConfig = document.getElementById('dynamicBlurSubConfig');
const dynamicBlurChevron = document.getElementById('dynamicBlurChevron');
const reviewBlurCheckbox = document.getElementById('reviewBlurOriginalSubtitles');
const dynamicBlurToggleLabel = document.getElementById('dynamicBlurToggleLabel');

function updateDynamicBlurUIState(notify = false) {
    if (!reviewBlurCheckbox) return;
    const isChecked = reviewBlurCheckbox.checked;
    if (dynamicBlurToggleLabel) {
        dynamicBlurToggleLabel.textContent = isChecked ? 'Bật' : 'Tắt';
        dynamicBlurToggleLabel.style.color = isChecked ? '#38bdf8' : '#94a3b8';
    }
    if (dynamicBlurSubConfig) {
        dynamicBlurSubConfig.style.display = isChecked ? 'flex' : 'none';
    }
    if (dynamicBlurChevron) {
        dynamicBlurChevron.style.transform = isChecked ? 'rotate(0deg)' : 'rotate(-90deg)';
    }
    updateDynamicBlurOverlayVisibility();
    if (notify) {
        showToast(isChecked ? '✨ Đã BẬT làm mờ phụ đề gốc.' : '🚫 Đã TẮT làm mờ phụ đề gốc.', isChecked ? 'info' : 'warning');
    }
}

if (dynamicBlurHeader) {
    dynamicBlurHeader.addEventListener('click', (e) => {
        if (e.target.id === 'reviewBlurOriginalSubtitles' || e.target.closest('.switch')) return;
        if (reviewBlurCheckbox) {
            reviewBlurCheckbox.checked = !reviewBlurCheckbox.checked;
            updateDynamicBlurUIState(true);
        }
    });
}

// Dynamic Blur Intensity Slider
const dynBlurIntensitySlider = document.getElementById('dynBlurIntensity');
const dynBlurIntensityVal = document.getElementById('dynBlurIntensityVal');
if (dynBlurIntensitySlider && dynBlurIntensityVal) {
    dynBlurIntensitySlider.addEventListener('input', (e) => {
        const val = parseInt(e.target.value) || 15;
        dynBlurIntensityVal.textContent = `${val}px`;
        updateDynamicBlurOverlayVisibility();
    });
}

if (reviewBlurCheckbox) {
    reviewBlurCheckbox.addEventListener('change', () => {
        updateDynamicBlurUIState(true);
    });
}
document.getElementById('subBgBlur')?.addEventListener('input', updateDynamicBlurOverlayVisibility);

videoPlayer.addEventListener('timeupdate', () => {
    if (videoPlayer.duration) {
        if (!isSeekingTimeline) {
            const percent = (videoPlayer.currentTime / videoPlayer.duration) * 100;
            timeline.value = percent;
        }
        
        let curMins = Math.floor(videoPlayer.currentTime / 60);
        let curSecs = Math.floor(videoPlayer.currentTime % 60);
        let durMins = Math.floor(videoPlayer.duration / 60);
        let durSecs = Math.floor(videoPlayer.duration % 60);
        
        curSecs = curSecs < 10 ? '0' + curSecs : curSecs;
        durSecs = durSecs < 10 ? '0' + durSecs : durSecs;
        
        timeDisplay.textContent = `${curMins}:${curSecs} / ${durMins}:${durSecs}`;
        
        // Dynamic Blur: show/hide blur overlay based on current time
        updateDynamicBlurOverlayVisibility();
    }
});

function safeSeekVideo(targetSecs, autoPlay = false) {
    if (!videoPlayer) return;
    
    const applySeek = () => {
        try {
            if (!isNaN(targetSecs) && targetSecs >= 0) {
                videoPlayer.currentTime = targetSecs;
            }
            if (autoPlay) {
                const p = videoPlayer.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(e => console.log('Play handled:', e));
                }
            }
        } catch(e) {
            console.error('safeSeekVideo error:', e);
        }
    };
    
    if (!videoPlayer.src || videoPlayer.src === '' || videoPlayer.src.endsWith('/')) {
        if (editorInputVideoPath && editorInputVideoPath.value) {
            videoPlayer.src = `/api/video?path=${encodeURIComponent(editorInputVideoPath.value)}`;
            videoPlayer.addEventListener('loadedmetadata', function onMeta() {
                videoPlayer.removeEventListener('loadedmetadata', onMeta);
                applySeek();
            });
            videoPlayer.load();
            return;
        }
    }
    
    if (videoPlayer.readyState >= 1) {
        applySeek();
    } else {
        const onMeta = () => {
            videoPlayer.removeEventListener('loadedmetadata', onMeta);
            applySeek();
        };
        videoPlayer.addEventListener('loadedmetadata', onMeta);
    }
}

let _pendingSeekRaf = null;
let _pendingSeekTime = null;

timeline.addEventListener('mousedown', () => { isSeekingTimeline = true; });
timeline.addEventListener('touchstart', () => { isSeekingTimeline = true; }, { passive: true });

timeline.addEventListener('input', (e) => {
    if (!videoPlayer.duration) return;
    const seekTime = (parseFloat(e.target.value) / 100) * videoPlayer.duration;
    
    // Cập nhật ngay lập tức hiển thị đồng hồ thời gian (Zero Latency)
    let curMins = Math.floor(seekTime / 60);
    let curSecs = Math.floor(seekTime % 60);
    let durMins = Math.floor(videoPlayer.duration / 60);
    let durSecs = Math.floor(videoPlayer.duration % 60);
    curSecs = curSecs < 10 ? '0' + curSecs : curSecs;
    durSecs = durSecs < 10 ? '0' + durSecs : durSecs;
    timeDisplay.textContent = `${curMins}:${curSecs} / ${durMins}:${durSecs}`;

    // Throttle lệnh seek qua requestAnimationFrame & kiểm tra trạng thái videoPlayer.seeking
    _pendingSeekTime = seekTime;
    if (!_pendingSeekRaf) {
        _pendingSeekRaf = requestAnimationFrame(() => {
            _pendingSeekRaf = null;
            if (_pendingSeekTime !== null && !videoPlayer.seeking) {
                if ('fastSeek' in videoPlayer) {
                    try { videoPlayer.fastSeek(_pendingSeekTime); } catch(_) { videoPlayer.currentTime = _pendingSeekTime; }
                } else {
                    videoPlayer.currentTime = _pendingSeekTime;
                }
            }
        });
    }
});

const onSeekEnd = (e) => {
    if (isSeekingTimeline && videoPlayer.duration) {
        if (_pendingSeekRaf) {
            cancelAnimationFrame(_pendingSeekRaf);
            _pendingSeekRaf = null;
        }
        const seekTime = (parseFloat(e.target.value) / 100) * videoPlayer.duration;
        _pendingSeekTime = null;
        safeSeekVideo(seekTime, false);
        isSeekingTimeline = false;
    }
};

timeline.addEventListener('change', onSeekEnd);
timeline.addEventListener('mouseup', onSeekEnd);
timeline.addEventListener('touchend', onSeekEnd);

// ═════════════════════════════════════════════════════════════
// SYNCED STEM AUDIO PLAYBACK ENGINE (Bản sau khi sửa)
// ═════════════════════════════════════════════════════════════
window._appliedStemAudioUrl = null;
window._appliedStemCleanedPath = null;
window._isStemAudioAppliedToEdited = false;
window._syncedStemAudioPlayer = new Audio();
window._syncedStemAudioPlayer.preload = 'auto';

const btnApplyStemToEdited = document.getElementById('btnApplyStemToEditedPreview');
const btnRemoveStemFromEdited = document.getElementById('btnRemoveStemFromEditedPreview');

if (btnApplyStemToEdited) {
    btnApplyStemToEdited.addEventListener('click', () => {
        if (!window._appliedStemAudioUrl) {
            showToast('⚠️ Chưa có audio SFX đã tách để áp dụng!', 'warning');
            return;
        }
        window._isStemAudioAppliedToEdited = true;
        window._syncedStemAudioPlayer.src = window._appliedStemAudioUrl;
        window._syncedStemAudioPlayer.load();

        btnApplyStemToEdited.innerHTML = '<span>✓ Đang áp dụng SFX</span>';
        btnApplyStemToEdited.style.background = '#059669';
        if (btnRemoveStemFromEdited) btnRemoveStemFromEdited.style.display = 'inline-flex';

        // Tự động chuyển sang xem tab "Bản sau khi sửa"
        if (btnPreviewEdited) {
            btnPreviewEdited.click();
        }

        // Đồng bộ tức thời âm thanh với video
        if (videoPlayer) {
            videoPlayer.muted = true;
            window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
            window._syncedStemAudioPlayer.volume = videoPlayer.volume;
            if (!videoPlayer.paused) {
                window._syncedStemAudioPlayer.play().catch(() => {});
            }
        }

        showToast('✨ Đã áp dụng âm thanh SFX sạch vào "Bản sau khi sửa"! Bấm Play trên video để nghe thử cùng hình ảnh.', 'success');
    });
}

if (btnRemoveStemFromEdited) {
    btnRemoveStemFromEdited.addEventListener('click', () => {
        window._isStemAudioAppliedToEdited = false;
        if (window._syncedStemAudioPlayer) {
            window._syncedStemAudioPlayer.pause();
        }
        if (videoPlayer) {
            videoPlayer.muted = false;
        }
        if (btnApplyStemToEdited) {
            btnApplyStemToEdited.innerHTML = '<span>✨ Áp dụng vào "Bản sau khi sửa"</span>';
            btnApplyStemToEdited.style.background = 'linear-gradient(135deg, #0ea5e9, #10b981)';
        }
        btnRemoveStemFromEdited.style.display = 'none';
        showToast('ℹ️ Đã khôi phục âm thanh gốc của video khi xem Bản sau khi sửa.', 'info');
    });
}

// Lắng nghe sự kiện đồng bộ videoPlayer <-> syncedStemAudioPlayer
if (videoPlayer) {
    videoPlayer.addEventListener('play', () => {
        if (window._isStemAudioAppliedToEdited && btnPreviewEdited && btnPreviewEdited.classList.contains('active')) {
            videoPlayer.muted = true;
            window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
            window._syncedStemAudioPlayer.volume = videoPlayer.volume;
            window._syncedStemAudioPlayer.play().catch(() => {});
        } else {
            videoPlayer.muted = false;
            if (window._syncedStemAudioPlayer) window._syncedStemAudioPlayer.pause();
        }
    });

    videoPlayer.addEventListener('pause', () => {
        if (window._syncedStemAudioPlayer) {
            window._syncedStemAudioPlayer.pause();
        }
    });

    videoPlayer.addEventListener('seeking', () => {
        if (window._isStemAudioAppliedToEdited && btnPreviewEdited && btnPreviewEdited.classList.contains('active')) {
            window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
        }
    });

    videoPlayer.addEventListener('seeked', () => {
        if (window._isStemAudioAppliedToEdited && btnPreviewEdited && btnPreviewEdited.classList.contains('active')) {
            window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
            if (!videoPlayer.paused) {
                window._syncedStemAudioPlayer.play().catch(() => {});
            }
        }
    });

    videoPlayer.addEventListener('volumechange', () => {
        if (window._syncedStemAudioPlayer) {
            window._syncedStemAudioPlayer.volume = videoPlayer.volume;
        }
    });

    videoPlayer.addEventListener('timeupdate', () => {
        if (window._isStemAudioAppliedToEdited && btnPreviewEdited && btnPreviewEdited.classList.contains('active') && !videoPlayer.paused) {
            if (Math.abs(window._syncedStemAudioPlayer.currentTime - videoPlayer.currentTime) > 0.18) {
                window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
            }
        }
    });
}

btnPreviewOriginal.addEventListener('click', () => {
    btnPreviewOriginal.classList.add('active');
    btnPreviewEdited.classList.remove('active');
    
    // Tạm dừng âm thanh SFX đồng bộ khi xem Bản gốc
    if (window._syncedStemAudioPlayer) {
        window._syncedStemAudioPlayer.pause();
    }
    if (videoPlayer) {
        videoPlayer.muted = false;
    }

    // In Original mode: hide subtitle preview overlay
    if (subPreviewBox) {
        subPreviewBox.style.display = 'none';
    }
    
    if (editorInputVideoPath.value) {
        const curTime = videoPlayer.currentTime;
        const isPaused = videoPlayer.paused;
        if (!videoPlayer.src || !videoPlayer.src.includes(encodeURIComponent(editorInputVideoPath.value))) {
            videoPlayer.src = `/api/video?path=${encodeURIComponent(editorInputVideoPath.value)}`;
            videoPlayer.currentTime = curTime;
            if (!isPaused) videoPlayer.play();
        }
    }
});

btnPreviewEdited.addEventListener('click', () => {
    btnPreviewEdited.classList.add('active');
    btnPreviewOriginal.classList.remove('active');
    
    // In Edited mode: make sure video is loaded and subPreviewBox is styled and shown
    if (editorInputVideoPath.value) {
        if (!videoPlayer.src || videoPlayer.src === '' || videoPlayer.src.endsWith('/')) {
            videoPlayer.src = `/api/video?path=${encodeURIComponent(editorInputVideoPath.value)}`;
        }
    }
    
    // Kích hoạt âm thanh SFX sạch đã tách nếu đang bật chế độ áp dụng
    if (window._isStemAudioAppliedToEdited && window._appliedStemAudioUrl) {
        if (videoPlayer) {
            videoPlayer.muted = true;
            window._syncedStemAudioPlayer.currentTime = videoPlayer.currentTime;
            window._syncedStemAudioPlayer.volume = videoPlayer.volume;
            if (!videoPlayer.paused) {
                window._syncedStemAudioPlayer.play().catch(() => {});
            }
        }
    } else {
        if (videoPlayer) {
            videoPlayer.muted = false;
        }
    }

    updateSubPreview();
    if (videoPlayer) {
        videoPlayer.dispatchEvent(new Event('timeupdate'));
    }
});

// ═════════════════════════════════════════════════════════════
// VIDEO ZOOM & PAN INTERACTIVE SYSTEM
// ═════════════════════════════════════════════════════════════
const videoZoomWrapper = document.getElementById('videoZoomWrapper');
const videoContainer = document.getElementById('videoContainer');
const floatingZoomValue = document.getElementById('floatingZoomValue');
const floatingZoomDropdown = document.getElementById('floatingZoomDropdown');
const btnFloatingZoomIn = document.getElementById('btnFloatingZoomIn');
const btnFloatingZoomOut = document.getElementById('btnFloatingZoomOut');
const btnFloatingZoomReset = document.getElementById('btnFloatingZoomReset');
const btnPlayerZoomIn = document.getElementById('btnPlayerZoomIn');
const btnPlayerZoomOut = document.getElementById('btnPlayerZoomOut');
const playerZoomSelect = document.getElementById('playerZoomSelect');

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];
let currentVideoZoom = 1.0;
let videoPanX = 0;
let videoPanY = 0;
let isPanningVideo = false;
let panStartX = 0;
let panStartY = 0;

function updateVideoZoomUI() {
    const pct = Math.round(currentVideoZoom * 100);
    const zoomText = (Math.abs(currentVideoZoom - 1.0) < 0.01) ? '100% (Fit)' : `${pct}%`;
    
    if (floatingZoomValue) floatingZoomValue.textContent = zoomText;
    if (editToolZoomVal) editToolZoomVal.textContent = zoomText;
    if (editToolZoomSlider) editToolZoomSlider.value = pct;
    
    if (playerZoomSelect) {
        let closestVal = ZOOM_STEPS[0];
        let minDiff = Math.abs(currentVideoZoom - closestVal);
        for (const step of ZOOM_STEPS) {
            const diff = Math.abs(currentVideoZoom - step);
            if (diff < minDiff) {
                minDiff = diff;
                closestVal = step;
            }
        }
        playerZoomSelect.value = closestVal.toString();
    }
    if (floatingZoomDropdown) {
        const items = floatingZoomDropdown.querySelectorAll('.zoom-dropdown-item');
        items.forEach(it => {
            const z = parseFloat(it.dataset.zoom);
            if (Math.abs(z - currentVideoZoom) < 0.05) {
                it.classList.add('active');
            } else {
                it.classList.remove('active');
            }
        });
    }

    if (videoContainer) {
        if (currentVideoZoom > 1.01) {
            videoContainer.classList.add('is-zoomed');
        } else {
            videoContainer.classList.remove('is-zoomed');
            videoContainer.classList.remove('is-panning');
        }
    }
}

function applyVideoZoomTransform(animate = true) {
    if (!videoZoomWrapper) return;
    if (currentVideoZoom <= 1.0) {
        videoPanX = 0;
        videoPanY = 0;
    } else {
        const maxPanX = (currentVideoZoom - 1.0) * (videoContainer ? videoContainer.clientWidth / 2 : 200);
        const maxPanY = (currentVideoZoom - 1.0) * (videoContainer ? videoContainer.clientHeight / 2 : 150);
        videoPanX = Math.max(-maxPanX, Math.min(maxPanX, videoPanX));
        videoPanY = Math.max(-maxPanY, Math.min(maxPanY, videoPanY));
    }

    videoZoomWrapper.style.transition = animate ? 'transform 0.12s cubic-bezier(0.2, 0, 0, 1)' : 'none';
    videoZoomWrapper.style.transform = `scale(${currentVideoZoom}) translate(${videoPanX / currentVideoZoom}px, ${videoPanY / currentVideoZoom}px)`;
    updateVideoZoomUI();
    syncZoomBoxFromVideoTransform();
}

function setVideoZoom(zoomLevel, animate = true) {
    currentVideoZoom = Math.max(0.5, Math.min(3.5, Math.round(zoomLevel * 100) / 100));
    applyVideoZoomTransform(animate);
}

function zoomVideoIn() {
    let nextStep = ZOOM_STEPS.find(s => s > currentVideoZoom + 0.02);
    if (!nextStep) nextStep = Math.min(3.5, currentVideoZoom + 0.25);
    setVideoZoom(nextStep);
}

function zoomVideoOut() {
    let prevStep = [...ZOOM_STEPS].reverse().find(s => s < currentVideoZoom - 0.02);
    if (!prevStep) prevStep = Math.max(0.5, currentVideoZoom - 0.25);
    setVideoZoom(prevStep);
}

function resetVideoZoom() {
    videoPanX = 0;
    videoPanY = 0;
    setVideoZoom(1.0);
}

if (btnFloatingZoomIn) btnFloatingZoomIn.addEventListener('click', (e) => { e.stopPropagation(); zoomVideoIn(); });
if (btnFloatingZoomOut) btnFloatingZoomOut.addEventListener('click', (e) => { e.stopPropagation(); zoomVideoOut(); });
if (btnFloatingZoomReset) btnFloatingZoomReset.addEventListener('click', (e) => { e.stopPropagation(); resetVideoZoom(); });

if (btnPlayerZoomIn) btnPlayerZoomIn.addEventListener('click', zoomVideoIn);
if (btnPlayerZoomOut) btnPlayerZoomOut.addEventListener('click', zoomVideoOut);
if (playerZoomSelect) {
    playerZoomSelect.addEventListener('change', (e) => {
        setVideoZoom(parseFloat(e.target.value));
    });
}

if (floatingZoomValue) {
    floatingZoomValue.addEventListener('click', (e) => {
        e.stopPropagation();
        if (floatingZoomDropdown) {
            floatingZoomDropdown.style.display = (floatingZoomDropdown.style.display === 'none') ? 'block' : 'none';
        }
    });
}

if (floatingZoomDropdown) {
    floatingZoomDropdown.querySelectorAll('.zoom-dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const z = parseFloat(item.dataset.zoom);
            setVideoZoom(z);
            floatingZoomDropdown.style.display = 'none';
        });
    });
}

document.addEventListener('click', () => {
    if (floatingZoomDropdown) floatingZoomDropdown.style.display = 'none';
});

if (videoContainer) {
    videoContainer.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            if (e.deltaY < 0) {
                setVideoZoom(currentVideoZoom * 1.15);
            } else {
                setVideoZoom(currentVideoZoom * 0.87);
            }
        }
    }, { passive: false });

    videoContainer.addEventListener('mousedown', (e) => {
        if (currentVideoZoom > 1.01 && e.button === 0) {
            if (e.target.closest('#videoZoomHud') || e.target.closest('#dynamicBlurOverlay') || e.target.closest('#videoZoomBox') || e.target.closest('#videoLogoOverlay') || e.target.closest('.overlay-interactive-box') || e.target.closest('#videoOverlayLayersContainer')) return;
            isPanningVideo = true;
            panStartX = e.clientX - videoPanX;
            panStartY = e.clientY - videoPanY;
            videoContainer.classList.add('is-panning');
            e.preventDefault();
        }
    });

    window.addEventListener('mousemove', (e) => {
        if (isPanningVideo && currentVideoZoom > 1.01) {
            videoPanX = e.clientX - panStartX;
            videoPanY = e.clientY - panStartY;
            applyVideoZoomTransform(false);
        }
    });

    window.addEventListener('mouseup', () => {
        if (isPanningVideo) {
            isPanningVideo = false;
            if (videoContainer) videoContainer.classList.remove('is-panning');
            applyVideoZoomTransform(true);
        }
    });

    videoContainer.addEventListener('dblclick', (e) => {
        if (e.target.closest('#videoZoomHud') || e.target.closest('#videoZoomBox') || e.target.closest('#videoLogoOverlay')) return;
        if (currentVideoZoom > 1.05) {
            resetVideoZoom();
        } else {
            setVideoZoom(1.5);
        }
    });
}

// ═════════════════════════════════════════════════════════════
// 8-POINT INTERACTIVE VIDEO ZOOM BOX CONTROLLER
// ═════════════════════════════════════════════════════════════
const videoZoomBox = document.getElementById('videoZoomBox');
const btnToggleZoomBox = document.getElementById('btnToggleZoomBox');
let isZoomBoxVisible = false;

function syncZoomBoxFromVideoTransform() {
    if (!videoZoomBox) return;
    const parentEl = videoZoomBox.offsetParent || videoContainer;
    if (!parentEl) return;
    const cW = parentEl.clientWidth;
    const cH = parentEl.clientHeight;
    if (cW <= 0 || cH <= 0) return;

    if (currentVideoZoom <= 1.0) {
        videoZoomBox.style.width = '100%';
        videoZoomBox.style.height = '100%';
        videoZoomBox.style.left = '0px';
        videoZoomBox.style.top = '0px';
    } else {
        const boxW = Math.max(20, cW / currentVideoZoom);
        const boxH = Math.max(20, cH / currentVideoZoom);
        const centerX = (cW / 2) - (videoPanX / currentVideoZoom);
        const centerY = (cH / 2) - (videoPanY / currentVideoZoom);
        const boxLeft = Math.max(0, Math.min(cW - boxW, centerX - (boxW / 2)));
        const boxTop = Math.max(0, Math.min(cH - boxH, centerY - (boxH / 2)));

        videoZoomBox.style.width = `${boxW}px`;
        videoZoomBox.style.height = `${boxH}px`;
        videoZoomBox.style.left = `${boxLeft}px`;
        videoZoomBox.style.top = `${boxTop}px`;
    }
}

function toggleZoomBox(forceState = null) {
    if (forceState !== null) {
        isZoomBoxVisible = forceState;
    } else {
        isZoomBoxVisible = !isZoomBoxVisible;
    }

    if (videoZoomBox) {
        if (isZoomBoxVisible) {
            videoZoomBox.classList.add('active');
            syncZoomBoxFromVideoTransform();
        } else {
            videoZoomBox.classList.remove('active');
        }
    }
    if (btnToggleZoomBox) {
        if (isZoomBoxVisible) {
            btnToggleZoomBox.classList.add('active');
        } else {
            btnToggleZoomBox.classList.remove('active');
        }
    }
}

if (btnToggleZoomBox) {
    btnToggleZoomBox.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleZoomBox();
    });
}

// ─── 8-POINT CROP BOUNDING BOX INTERACTION ───────────────────────────
function setupInteractiveVideoZoomBox() {
    if (!videoZoomBox) return;

    let isDraggingBox = false;
    let isResizing = false;
    let currentHandle = null;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;

    // 1. Dragging Entire Box
    videoZoomBox.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('zoom-resize-handle')) return;
        if (e.button !== 0) return;
        e.stopPropagation();
        e.preventDefault();

        isDraggingBox = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = videoZoomBox.getBoundingClientRect();
        const parentEl = videoZoomBox.offsetParent || videoContainer;
        const parentRect = parentEl.getBoundingClientRect();
        startLeft = rect.left - parentRect.left;
        startTop = rect.top - parentRect.top;
        startWidth = rect.width;
        startHeight = rect.height;
    });

    // 2. 8-Direction Handle Resizing
    const handles = videoZoomBox.querySelectorAll('.zoom-resize-handle');
    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.stopPropagation();
            e.preventDefault();

            isResizing = true;
            currentHandle = handle.dataset.handle;
            startX = e.clientX;
            startY = e.clientY;
            const rect = videoZoomBox.getBoundingClientRect();
            const parentEl = videoZoomBox.offsetParent || videoContainer;
            const parentRect = parentEl.getBoundingClientRect();
            startLeft = rect.left - parentRect.left;
            startTop = rect.top - parentRect.top;
            startWidth = rect.width;
            startHeight = rect.height;
        });
    });

    window.addEventListener('mousemove', (e) => {
        if (!isResizing && !isDraggingBox) return;
        e.preventDefault();

        const parentEl = videoZoomBox.offsetParent || videoContainer;
        const cW = parentEl.clientWidth;
        const cH = parentEl.clientHeight;
        if (cW <= 0 || cH <= 0) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (isDraggingBox) {
            let newLeft = Math.max(0, Math.min(cW - startWidth, startLeft + dx));
            let newTop = Math.max(0, Math.min(cH - startHeight, startTop + dy));

            videoZoomBox.style.left = `${newLeft}px`;
            videoZoomBox.style.top = `${newTop}px`;

            const boxCenterX = newLeft + (startWidth / 2);
            const boxCenterY = newTop + (startHeight / 2);
            videoPanX = -(boxCenterX - (cW / 2)) * currentVideoZoom;
            videoPanY = -(boxCenterY - (cH / 2)) * currentVideoZoom;
            applyVideoZoomTransform(false);
        } else if (isResizing) {
            let newLeft = startLeft;
            let newTop = startTop;
            let newWidth = startWidth;
            let newHeight = startHeight;

            const minW = cW / 3.5; // Max 350% zoom
            const minH = cH / 3.5;

            if (currentHandle.includes('e')) {
                newWidth = Math.max(minW, Math.min(cW - startLeft, startWidth + dx));
            }
            if (currentHandle.includes('s')) {
                newHeight = Math.max(minH, Math.min(cH - startTop, startHeight + dy));
            }
            if (currentHandle.includes('w')) {
                const maxDx = startWidth - minW;
                const actualDx = Math.max(-startLeft, Math.min(maxDx, dx));
                newLeft = startLeft + actualDx;
                newWidth = startWidth - actualDx;
            }
            if (currentHandle.includes('n')) {
                const maxDy = startHeight - minH;
                const actualDy = Math.max(-startTop, Math.min(maxDy, dy));
                newTop = startTop + actualDy;
                newHeight = startHeight - actualDy;
            }

            videoZoomBox.style.left = `${newLeft}px`;
            videoZoomBox.style.top = `${newTop}px`;
            videoZoomBox.style.width = `${newWidth}px`;
            videoZoomBox.style.height = `${newHeight}px`;

            // Calculate new zoom and pan
            const zoomX = cW / newWidth;
            const zoomY = cH / newHeight;
            const targetZoom = Math.max(0.5, Math.min(3.5, Math.max(zoomX, zoomY)));
            currentVideoZoom = Math.round(targetZoom * 100) / 100;

            const boxCenterX = newLeft + (newWidth / 2);
            const boxCenterY = newTop + (newHeight / 2);
            videoPanX = -(boxCenterX - (cW / 2)) * currentVideoZoom;
            videoPanY = -(boxCenterY - (cH / 2)) * currentVideoZoom;

            applyVideoZoomTransform(false);
        }
    });

    window.addEventListener('mouseup', () => {
        if (isResizing || isDraggingBox) {
            isResizing = false;
            isDraggingBox = false;
            currentHandle = null;
            applyVideoZoomTransform(true);
            syncZoomBoxFromVideoTransform();
        }
    });
}

setupInteractiveVideoZoomBox();

// ═════════════════════════════════════════════════════════════
// VIDEO EDITING TOOLS CARD CONTROLLER
// ═════════════════════════════════════════════════════════════
const editToolZoomSlider = document.getElementById('editToolZoomSlider');
const editToolZoomVal = document.getElementById('editToolZoomVal');
const btnCardZoomOut = document.getElementById('btnCardZoomOut');
const btnCardZoomIn = document.getElementById('btnCardZoomIn');
const btnCardZoomFit = document.getElementById('btnCardZoomFit');

const editToolSpeedSlider = document.getElementById('editToolSpeedSlider');
const editToolSpeedVal = document.getElementById('editToolSpeedVal');
const speedPresetBtns = document.querySelectorAll('.speed-preset-btn');

const editToolAspectRatio = document.getElementById('editToolAspectRatio');
const editToolMirrorFlip = document.getElementById('editToolMirrorFlip');

const editToolTrimEnabled = document.getElementById('editToolTrimEnabled');
const editToolTrimStart = document.getElementById('editToolTrimStart');
const editToolTrimEnd = document.getElementById('editToolTrimEnd');
const btnSetTrimStart = document.getElementById('btnSetTrimStart');
const btnSetTrimEnd = document.getElementById('btnSetTrimEnd');
const btnResetEditTools = document.getElementById('btnResetEditTools');

// 1. Zoom Slider in Card
if (editToolZoomSlider) {
    editToolZoomSlider.addEventListener('input', (e) => {
        setVideoZoom(parseFloat(e.target.value) / 100);
    });
}
if (btnCardZoomOut) btnCardZoomOut.addEventListener('click', zoomVideoOut);
if (btnCardZoomIn) btnCardZoomIn.addEventListener('click', zoomVideoIn);
if (btnCardZoomFit) btnCardZoomFit.addEventListener('click', resetVideoZoom);

// 2. Video Speed Control
if (editToolSpeedSlider) {
    editToolSpeedSlider.addEventListener('input', (e) => {
        const spd = parseFloat(e.target.value);
        if (editToolSpeedVal) editToolSpeedVal.textContent = spd.toFixed(2) + 'x';
        if (videoPlayer) videoPlayer.playbackRate = spd;
    });
}

speedPresetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const spd = parseFloat(btn.dataset.speed || 1.0);
        if (editToolSpeedSlider) editToolSpeedSlider.value = spd;
        if (editToolSpeedVal) editToolSpeedVal.textContent = spd.toFixed(2) + 'x';
        if (videoPlayer) videoPlayer.playbackRate = spd;
    });
});

// 3. Mirror Flip
if (editToolMirrorFlip) {
    editToolMirrorFlip.addEventListener('change', (e) => {
        if (videoPlayer) {
            videoPlayer.style.transform = e.target.checked ? 'scaleX(-1)' : 'none';
        }
    });
}

// 4. Aspect Ratio Preview
if (editToolAspectRatio) {
    editToolAspectRatio.addEventListener('change', (e) => {
        const ratio = e.target.value;
        const vContainer = document.getElementById('videoContainer');
        if (!vContainer) return;
        if (ratio === '9:16') {
            vContainer.style.aspectRatio = '9 / 16';
            vContainer.style.maxWidth = '280px';
            vContainer.style.margin = '0 auto';
        } else if (ratio === '1:1') {
            vContainer.style.aspectRatio = '1 / 1';
            vContainer.style.maxWidth = '400px';
            vContainer.style.margin = '0 auto';
        } else if (ratio === '21:9') {
            vContainer.style.aspectRatio = '21 / 9';
            vContainer.style.maxWidth = '100%';
            vContainer.style.margin = '0';
        } else {
            vContainer.style.aspectRatio = '16 / 9';
            vContainer.style.maxWidth = '100%';
            vContainer.style.margin = '0';
        }
    });
}

// 5. Trim In / Out Formatters


if (btnSetTrimStart) {
    btnSetTrimStart.addEventListener('click', () => {
        if (videoPlayer && editToolTrimStart) {
            editToolTrimStart.value = formatTimeSec(videoPlayer.currentTime);
            if (editToolTrimEnabled) editToolTrimEnabled.checked = true;
        }
    });
}

if (btnSetTrimEnd) {
    btnSetTrimEnd.addEventListener('click', () => {
        if (videoPlayer && editToolTrimEnd) {
            editToolTrimEnd.value = formatTimeSec(videoPlayer.currentTime);
            if (editToolTrimEnabled) editToolTrimEnabled.checked = true;
        }
    });
}

// 6. Reset Button
if (btnResetEditTools) {
    btnResetEditTools.addEventListener('click', () => {
        resetVideoZoom();
        if (editToolSpeedSlider) editToolSpeedSlider.value = 1.0;
        if (editToolSpeedVal) editToolSpeedVal.textContent = '1.00x';
        if (videoPlayer) {
            videoPlayer.playbackRate = 1.0;
            videoPlayer.style.transform = 'none';
        }
        if (editToolMirrorFlip) editToolMirrorFlip.checked = false;
        if (editToolAspectRatio) {
            editToolAspectRatio.value = 'original';
            editToolAspectRatio.dispatchEvent(new Event('change'));
        }
        if (editToolTrimEnabled) editToolTrimEnabled.checked = false;
        if (editToolTrimStart) editToolTrimStart.value = '';
        if (editToolTrimEnd) editToolTrimEnd.value = '';
        showToast('Đã đặt lại bộ công cụ biên tập về mặc định!', 'info');
    });
}

// ====== ROLE-BASED SETTINGS MODAL LOGIC ======
const settingsBtn = document.getElementById('settingsBtn');
const settingsModal = document.getElementById('settingsModal');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');

const settingsVipServerNotice = document.getElementById('settingsVipServerNotice');
const settingsTrialServerNotice = document.getElementById('settingsTrialServerNotice');
const settingsProApiContainer = document.getElementById('settingsProApiContainer');
const settingsVipNoticeTitle = document.getElementById('settingsVipNoticeTitle');

async function loadApiKeys() {
    try {
        const res = await fetch('/api/keys');
        if (res.ok) {
            const data = await res.json();
            const openaiKeyEl = document.getElementById('openaiKey');
            const openSpeakerApiKeyEl = document.getElementById('openSpeakerApiKey');
            const openaiBaseUrlEl = document.getElementById('openaiBaseUrl');
            const openaiModelEl = document.getElementById('openaiModel');

            const isVipTier = currentLicenseState && (currentLicenseState.tier === 'vip' || currentLicenseState.tier === 'yearly');
            
            if (openaiKeyEl) {
                if (data.openaiKey && !data.openaiKey.startsWith('•')) {
                    openaiKeyEl.value = data.openaiKey;
                    openaiKeyEl.readOnly = false;
                    openaiKeyEl.style.cursor = 'text';
                    openaiKeyEl.style.color = '#fff';
                    openaiKeyEl.style.background = '#0f172a';
                    openaiKeyEl.style.borderColor = '#334155';
                } else if (isVipTier && (!data.openaiKey || data.openaiKey.startsWith('•'))) {
                    openaiKeyEl.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                } else if (data.openaiKey) {
                    openaiKeyEl.value = data.openaiKey;
                }
            }
            if (openSpeakerApiKeyEl) {
                if (data.openSpeakerApiKey && !data.openSpeakerApiKey.startsWith('•')) {
                    openSpeakerApiKeyEl.value = data.openSpeakerApiKey;
                    openSpeakerApiKeyEl.readOnly = false;
                    openSpeakerApiKeyEl.style.cursor = 'text';
                    openSpeakerApiKeyEl.style.color = '#fff';
                    openSpeakerApiKeyEl.style.background = '#0f172a';
                    openSpeakerApiKeyEl.style.borderColor = '#334155';
                } else if (isVipTier && (!data.openSpeakerApiKey || data.openSpeakerApiKey.startsWith('•'))) {
                    openSpeakerApiKeyEl.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                } else if (data.openSpeakerApiKey) {
                    openSpeakerApiKeyEl.value = data.openSpeakerApiKey;
                }
            }
            if (openaiBaseUrlEl && data.openaiBaseUrl) {
                openaiBaseUrlEl.value = data.openaiBaseUrl;
            }
            if (openaiModelEl) {
                const currentModel = data.openaiModel || 'qwen/qwen3.7-flash';
                const modelSelect = document.getElementById('openaiModelSelect');
                const customRow = document.getElementById('openaiModelCustomRow');
                const customInput = document.getElementById('openaiModelCustomInput');
                if (modelSelect) {
                    const norm = (v) => (v || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                    let matchedOption = Array.from(modelSelect.options).find(o => 
                        o.value !== 'custom' && (
                            o.value === currentModel || 
                            norm(o.value) === norm(currentModel) ||
                            (currentModel.includes('qwen') && o.value.includes('qwen')) ||
                            (currentModel.includes('deepseek') && o.value.includes('deepseek')) ||
                            (currentModel.includes('luna') && o.value.includes('luna'))
                        )
                    );
                    if (matchedOption) {
                        modelSelect.value = matchedOption.value;
                        openaiModelEl.value = matchedOption.value;
                        if (customRow) customRow.style.display = 'none';
                    } else {
                        modelSelect.value = 'custom';
                        openaiModelEl.value = currentModel;
                        if (customRow) customRow.style.display = 'block';
                        if (customInput) customInput.value = currentModel;
                    }
                } else {
                    openaiModelEl.value = currentModel;
                }
            }
        }
    } catch (e) {
        console.warn('Lỗi tải API keys:', e);
    }
}

function updateSettingsModalPermissions(lic) {
    const tier = lic?.tier || 'unlicensed';
    const settingsApiTierBadge = document.getElementById('settingsApiTierBadge');
    const settingsApiSectionTitle = document.getElementById('settingsApiSectionTitle');
    const openaiKey = document.getElementById('openaiKey');
    const openSpeakerApiKey = document.getElementById('openSpeakerApiKey');
    const openaiKeyHelpText = document.getElementById('openaiKeyHelpText');
    const btnTestApiKey = document.getElementById('btnTestApiKey');

    if (settingsProApiContainer) settingsProApiContainer.style.display = 'block';

    if (tier === 'vip' || tier === 'yearly') {
        // Gói VIP / 1 Năm: Hiển thị banner VIP
        if (settingsTrialServerNotice) settingsTrialServerNotice.style.display = 'none';
        if (settingsVipServerNotice) {
            settingsVipServerNotice.style.display = 'block';
            if (settingsVipNoticeTitle) {
                settingsVipNoticeTitle.textContent = tier === 'yearly' 
                    ? '👑 Đặc Quyền Gói 1 Năm: Cấp Sẵn Toàn Bộ API Server AI' 
                    : '👑 Đặc Quyền Gói VIP: Cấp Sẵn Toàn Bộ API Server AI';
            }
        }
        if (settingsApiTierBadge) {
            settingsApiTierBadge.innerHTML = '👑 Gói VIP: Đã Kích Hoạt API Bản Quyền';
            settingsApiTierBadge.style.color = '#c084fc';
            settingsApiTierBadge.style.background = 'rgba(168, 85, 247, 0.15)';
        }
        if (settingsApiSectionTitle) {
            settingsApiSectionTitle.textContent = 'API Bản Quyền Hệ Thống (Được Cấp Sẵn)';
        }
        if (openaiKeyHelpText) {
            openaiKeyHelpText.innerHTML = '✨ Gói VIP của bạn được bảo vệ bản quyền. Bấm nút <strong>[Test Key]</strong> bên cạnh để kiểm tra kết nối API.';
        }

        // Mask và bảo vệ OpenAI Key - chỉ mask nếu người dùng KHÔNG có key riêng hợp lệ
        if (openaiKey) {
            const hasCustomKey = openaiKey.value && !openaiKey.value.startsWith('•') && !openaiKey.value.includes('[Bản Quyền VIP');
            if (!hasCustomKey) {
                openaiKey.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                openaiKey.readOnly = true;
                openaiKey.type = 'password';
                openaiKey.style.background = 'rgba(168, 85, 247, 0.08)';
                openaiKey.style.borderColor = 'rgba(168, 85, 247, 0.4)';
                openaiKey.style.color = '#c084fc';
                openaiKey.style.cursor = 'not-allowed';
                openaiKey.style.userSelect = 'none';
                openaiKey.style.webkitUserSelect = 'none';
                if (typeof openaiKey.setAttribute === 'function') {
                    openaiKey.setAttribute('oncopy', 'return false;');
                    openaiKey.setAttribute('oncut', 'return false;');
                    openaiKey.setAttribute('oncontextmenu', 'return false;');
                }
            }
        }

        // Mask và bảo vệ OpenSpeaker Key
        if (openSpeakerApiKey) {
            const hasCustomSpeaker = openSpeakerApiKey.value && !openSpeakerApiKey.value.startsWith('•') && !openSpeakerApiKey.value.includes('[Bản Quyền VIP');
            if (!hasCustomSpeaker) {
                openSpeakerApiKey.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                openSpeakerApiKey.readOnly = true;
                openSpeakerApiKey.type = 'password';
                openSpeakerApiKey.style.background = 'rgba(168, 85, 247, 0.08)';
                openSpeakerApiKey.style.borderColor = 'rgba(168, 85, 247, 0.4)';
                openSpeakerApiKey.style.color = '#c084fc';
                openSpeakerApiKey.style.cursor = 'not-allowed';
                openSpeakerApiKey.style.userSelect = 'none';
                openSpeakerApiKey.style.webkitUserSelect = 'none';
                if (typeof openSpeakerApiKey.setAttribute === 'function') {
                    openSpeakerApiKey.setAttribute('oncopy', 'return false;');
                    openSpeakerApiKey.setAttribute('oncut', 'return false;');
                    openSpeakerApiKey.setAttribute('oncontextmenu', 'return false;');
                }
            }
        }

        if (btnTestApiKey) {
            btnTestApiKey.style.display = 'inline-flex';
            btnTestApiKey.textContent = 'Test Key';
            btnTestApiKey.disabled = false;
        }
    } else if (tier === 'pro') {
        // Gói Pro: Mở quyền cho phép tự điền API Key cá nhân
        if (settingsVipServerNotice) settingsVipServerNotice.style.display = 'none';
        if (settingsTrialServerNotice) settingsTrialServerNotice.style.display = 'none';
        if (settingsApiTierBadge) {
            settingsApiTierBadge.innerHTML = '⭐ Gói Pro: Tự túc API';
            settingsApiTierBadge.style.color = '#fbbf24';
            settingsApiTierBadge.style.background = 'rgba(245, 158, 11, 0.15)';
        }
        if (settingsApiSectionTitle) {
            settingsApiSectionTitle.textContent = 'Cài đặt API Cá Nhân';
        }
        if (openaiKeyHelpText) {
            openaiKeyHelpText.textContent = 'Dùng để tự động sinh kịch bản và dịch phụ đề AI (Mặc định: Bản Luna).';
        }

        if (openaiKey) {
            if (openaiKey.value.includes('[Bản Quyền VIP')) openaiKey.value = '';
            openaiKey.readOnly = false;
            openaiKey.style.background = '#0f172a';
            openaiKey.style.borderColor = '#334155';
            openaiKey.style.color = '#fff';
            openaiKey.style.cursor = 'text';
            openaiKey.style.userSelect = '';
            openaiKey.style.webkitUserSelect = '';
            if (typeof openaiKey.removeAttribute === 'function') {
                openaiKey.removeAttribute('oncopy');
                openaiKey.removeAttribute('oncut');
                openaiKey.removeAttribute('oncontextmenu');
            }
        }

        if (openSpeakerApiKey) {
            if (openSpeakerApiKey.value.includes('[Bản Quyền VIP')) openSpeakerApiKey.value = '';
            openSpeakerApiKey.readOnly = false;
            openSpeakerApiKey.style.background = '#0f172a';
            openSpeakerApiKey.style.borderColor = '#334155';
            openSpeakerApiKey.style.color = '#fff';
            openSpeakerApiKey.style.cursor = 'text';
            openSpeakerApiKey.style.userSelect = '';
            openSpeakerApiKey.style.webkitUserSelect = '';
            if (typeof openSpeakerApiKey.removeAttribute === 'function') {
                openSpeakerApiKey.removeAttribute('oncopy');
                openSpeakerApiKey.removeAttribute('oncut');
                openSpeakerApiKey.removeAttribute('oncontextmenu');
            }
        }

        loadApiKeys();
    } else {
        // Gói Trial / Chưa có bản quyền: Cho phép điền key nếu có
        if (settingsVipServerNotice) settingsVipServerNotice.style.display = 'none';
        if (settingsTrialServerNotice) settingsTrialServerNotice.style.display = (tier === 'trial') ? 'block' : 'none';
        if (settingsApiTierBadge) {
            settingsApiTierBadge.innerHTML = tier === 'trial' ? '⚡ Gói Thử Nghiệm' : '🔑 Tự túc API';
            settingsApiTierBadge.style.color = '#38bdf8';
            settingsApiTierBadge.style.background = 'rgba(56, 189, 248, 0.15)';
        }
        if (settingsApiSectionTitle) {
            settingsApiSectionTitle.textContent = 'Cài đặt API Cá Nhân';
        }
        if (openaiKeyHelpText) {
            openaiKeyHelpText.textContent = 'Dùng để tự động sinh kịch bản và dịch phụ đề AI (Mặc định: Bản Luna).';
        }

        if (openaiKey) {
            if (openaiKey.value.includes('[Bản Quyền VIP')) openaiKey.value = '';
            openaiKey.readOnly = false;
            openaiKey.style.background = '#0f172a';
            openaiKey.style.borderColor = '#334155';
            openaiKey.style.color = '#fff';
            openaiKey.style.cursor = 'text';
            if (typeof openaiKey.removeAttribute === 'function') {
                openaiKey.removeAttribute('oncopy');
                openaiKey.removeAttribute('oncut');
                openaiKey.removeAttribute('oncontextmenu');
            }
        }

        if (openSpeakerApiKey) {
            if (openSpeakerApiKey.value.includes('[Bản Quyền VIP')) openSpeakerApiKey.value = '';
            openSpeakerApiKey.readOnly = false;
            openSpeakerApiKey.style.background = '#0f172a';
            openSpeakerApiKey.style.borderColor = '#334155';
            openSpeakerApiKey.style.color = '#fff';
            openSpeakerApiKey.style.cursor = 'text';
            if (typeof openSpeakerApiKey.removeAttribute === 'function') {
                openSpeakerApiKey.removeAttribute('oncopy');
                openSpeakerApiKey.removeAttribute('oncut');
                openSpeakerApiKey.removeAttribute('oncontextmenu');
            }
        }

        loadApiKeys();
    }
}

function updateSettingsDisclaimerStatus() {
    const isAccepted = (localStorage.getItem('ams_copyright_disclaimer_accepted') === 'true') ||
                       (currentLicenseState && currentLicenseState.disclaimer_accepted);
    const acceptedAt = localStorage.getItem('ams_disclaimer_accepted_at');
    const statusBox = document.getElementById('settingsDisclaimerStatusBox');
    const statusText = document.getElementById('settingsDisclaimerStatusText');
    const timeText = document.getElementById('settingsDisclaimerTimeText');
    const btnPopup = document.getElementById('btnOpenPopupDisclaimerFromSettings');

    if (isAccepted) {
        if (statusBox) {
            statusBox.style.background = 'rgba(16, 185, 129, 0.12)';
            statusBox.style.borderColor = 'rgba(16, 185, 129, 0.35)';
        }
        if (statusText) {
            statusText.textContent = '✅ Đã xác nhận cam kết bản quyền & miễn trừ trách nhiệm';
            statusText.style.color = '#10b981';
        }
        if (timeText) {
            let formatted = '';
            if (acceptedAt) {
                try {
                    const d = new Date(acceptedAt);
                    formatted = ` (Xác nhận lúc ${d.toLocaleTimeString('vi-VN')} ngày ${d.toLocaleDateString('vi-VN')})`;
                } catch(e) {}
            }
            timeText.textContent = `Bạn đã đọc và đồng ý với toàn bộ 8 điều khoản quy định pháp lý${formatted}.`;
        }
        if (btnPopup) {
            btnPopup.innerHTML = '<span>🔄</span> Ký Lại / Xem Popup';
        }
    } else {
        if (statusBox) {
            statusBox.style.background = 'rgba(239, 68, 68, 0.12)';
            statusBox.style.borderColor = 'rgba(239, 68, 68, 0.35)';
        }
        if (statusText) {
            statusText.textContent = '⚠️ Chưa xác nhận cam kết bản quyền';
            statusText.style.color = '#f87171';
        }
        if (timeText) {
            timeText.textContent = 'Bạn bắt buộc phải xác nhận cam kết trước khi sử dụng các tính năng biên tập & review phim AI.';
        }
        if (btnPopup) {
            btnPopup.innerHTML = '<span>✍️</span> Mở Popup Ký Ngay';
        }
    }
}

function switchSettingsTab(tabName) {
    const tabBtnApi = document.getElementById('tabBtnSettingsApi');
    const tabBtnTelegram = document.getElementById('tabBtnSettingsTelegram');
    const tabBtnDisclaimer = document.getElementById('tabBtnSettingsDisclaimer');
    const contentApi = document.getElementById('tabContentSettingsApi');
    const contentTelegram = document.getElementById('tabContentSettingsTelegram');
    const contentDisclaimer = document.getElementById('tabContentSettingsDisclaimer');
    const saveBtn = document.getElementById('saveSettingsBtn');

    // Reset all tabs
    [tabBtnApi, tabBtnTelegram, tabBtnDisclaimer].forEach(btn => {
        if (btn) {
            btn.classList.remove('active');
            btn.style.borderColor = 'transparent';
            btn.style.background = 'transparent';
            btn.style.color = '#94a3b8';
            btn.style.fontWeight = '600';
        }
    });
    if (contentApi) contentApi.style.display = 'none';
    if (contentTelegram) contentTelegram.style.display = 'none';
    if (contentDisclaimer) contentDisclaimer.style.display = 'none';

    if (tabName === 'disclaimer') {
        if (tabBtnDisclaimer) {
            tabBtnDisclaimer.classList.add('active');
            tabBtnDisclaimer.style.borderColor = 'rgba(245, 158, 11, 0.5)';
            tabBtnDisclaimer.style.background = 'rgba(245, 158, 11, 0.15)';
            tabBtnDisclaimer.style.color = '#fbbf24';
            tabBtnDisclaimer.style.fontWeight = '700';
        }
        if (contentDisclaimer) contentDisclaimer.style.display = 'block';
        if (saveBtn) saveBtn.style.display = 'none';
        updateSettingsDisclaimerStatus();
    } else if (tabName === 'telegram') {
        if (tabBtnTelegram) {
            tabBtnTelegram.classList.add('active');
            tabBtnTelegram.style.borderColor = '#38bdf8';
            tabBtnTelegram.style.background = 'rgba(56, 189, 248, 0.15)';
            tabBtnTelegram.style.color = '#38bdf8';
            tabBtnTelegram.style.fontWeight = '700';
        }
        if (contentTelegram) contentTelegram.style.display = 'block';
        if (saveBtn) saveBtn.style.display = 'inline-block';
        loadTelegramSettings();
    } else {
        if (tabBtnApi) {
            tabBtnApi.classList.add('active');
            tabBtnApi.style.borderColor = '#38bdf8';
            tabBtnApi.style.background = 'rgba(56, 189, 248, 0.15)';
            tabBtnApi.style.color = '#38bdf8';
            tabBtnApi.style.fontWeight = '700';
        }
        if (contentApi) contentApi.style.display = 'block';
        if (saveBtn) saveBtn.style.display = 'inline-block';
    }
}

// ═════════════════════════════════════════════════════════════
// TELEGRAM AUTO-CONNECT & MULTI-USER NOTIFICATION LOGIC
// ═════════════════════════════════════════════════════════════

export function getNovaCutUserId() {
    let uid = localStorage.getItem('novacut_user_id');
    if (!uid || uid.trim() === '') {
        uid = 'user_' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('novacut_user_id', uid);
    }
    return uid;
}
window.getNovaCutUserId = getNovaCutUserId;

let telegramPollingInterval = null;
let telegramCountdownInterval = null;
let currentTelegramConnectSession = null;

function updateTelegramUserUI(profile) {
    const badge = document.getElementById('telegramUserConnectionBadge');
    const statusText = document.getElementById('telegramUserConnectionStatusText');
    const connectedPanel = document.getElementById('telegramConnectedPanel');
    const waitingPanel = document.getElementById('telegramWaitingPanel');
    const disconnectedPanel = document.getElementById('telegramDisconnectedPanel');
    const chatIdEl = document.getElementById('telegramConnectedChatId');
    const timeEl = document.getElementById('telegramConnectedTime');
    const warningBox = document.getElementById('telegramGroupWarningBox');
    const groupNameDisplay = document.getElementById('telegramGroupNameDisplay');

    if (profile && profile.connected) {
        if (badge) {
            badge.style.background = 'rgba(16, 185, 129, 0.15)';
            badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            badge.style.color = '#10b981';
        }
        if (statusText) statusText.textContent = profile.is_group ? 'Đã kết nối nhóm' : 'Đã kết nối';
        if (chatIdEl) chatIdEl.textContent = profile.chat_id || '••••••••';
        if (timeEl) timeEl.textContent = profile.connected_at || '--:--:--';
        if (warningBox) {
            warningBox.style.display = profile.is_group ? 'block' : 'none';
            if (groupNameDisplay) groupNameDisplay.textContent = profile.chat_title || 'Nhóm Telegram';
        }
        if (connectedPanel) connectedPanel.style.display = 'block';
        if (waitingPanel) waitingPanel.style.display = 'none';
        if (disconnectedPanel) disconnectedPanel.style.display = 'none';
    } else {
        if (badge) {
            badge.style.background = 'rgba(148, 163, 184, 0.15)';
            badge.style.borderColor = 'rgba(148, 163, 184, 0.3)';
            badge.style.color = '#94a3b8';
        }
        if (statusText) statusText.textContent = 'Chưa kết nối';
        if (connectedPanel) connectedPanel.style.display = 'none';
        if (waitingPanel) waitingPanel.style.display = 'none';
        if (disconnectedPanel) disconnectedPanel.style.display = 'block';
        if (warningBox) warningBox.style.display = 'none';
    }
}

function stopTelegramConnectTimers() {
    if (telegramPollingInterval) {
        clearInterval(telegramPollingInterval);
        telegramPollingInterval = null;
    }
    if (telegramCountdownInterval) {
        clearInterval(telegramCountdownInterval);
        telegramCountdownInterval = null;
    }
    currentTelegramConnectSession = null;
}

export async function loadTelegramSettings() {
    try {
        // 1. Tải cấu hình chung
        const res = await fetch('/api/telegram/config');
        if (res.ok) {
            const data = await res.json();
            const cfg = data.config || {};
            const enabledEl = document.getElementById('settingsTelegramEnabled');
            const labelEl = document.getElementById('settingsTelegramEnabledLabel');
            const tokenEl = document.getElementById('settingsTelegramBotToken');
            const chatIdEl = document.getElementById('settingsTelegramChatId');
            const perVidEl = document.getElementById('settingsTelegramNotifyPerVideo');
            const batchDoneEl = document.getElementById('settingsTelegramNotifyBatchDone');
            const badgeTextEl = document.getElementById('batchTelegramStatusText');
            const badgeEl = document.getElementById('batchTelegramStatusBadge');

            if (enabledEl) enabledEl.checked = !!cfg.enabled;
            if (labelEl) {
                labelEl.textContent = cfg.enabled ? 'BẬT' : 'TẮT';
                labelEl.style.color = cfg.enabled ? '#10b981' : '#94a3b8';
            }
            if (tokenEl) {
                if (cfg.has_token && cfg.masked_token) {
                    tokenEl.value = cfg.masked_token;
                } else if (!cfg.has_token) {
                    tokenEl.value = '';
                }
            }
            if (chatIdEl && (!chatIdEl.value || chatIdEl.value === '5011367599')) {
                chatIdEl.value = cfg.chat_id || '5011367599';
            }
            if (perVidEl) perVidEl.checked = cfg.notify_per_video !== false;
            if (batchDoneEl) batchDoneEl.checked = cfg.notify_batch_done !== false;

            if (badgeTextEl) {
                badgeTextEl.textContent = cfg.enabled ? 'Đang Bật' : 'Tắt';
                badgeTextEl.style.color = cfg.enabled ? '#10b981' : '#94a3b8';
            }
            if (badgeEl) {
                badgeEl.style.borderColor = cfg.enabled ? 'rgba(16, 185, 129, 0.4)' : 'rgba(148, 163, 184, 0.3)';
                badgeEl.style.background = cfg.enabled ? 'rgba(16, 185, 129, 0.12)' : 'rgba(148, 163, 184, 0.08)';
            }
        }

        // 2. Lấy thông tin Bot Telegram chung
        try {
            const botRes = await fetch('/api/telegram/bot_info');
            if (botRes.ok) {
                const botData = await botRes.json();
                const usernameDisplay = document.getElementById('telegramBotUsernameDisplay');
                const openLink = document.getElementById('telegramOpenBotLink');
                if (botData.success && botData.username) {
                    if (usernameDisplay) usernameDisplay.textContent = '@' + botData.username;
                    if (openLink) openLink.href = 'https://t.me/' + botData.username;
                } else {
                    if (usernameDisplay) usernameDisplay.textContent = '@NovaCutBot';
                }
            }
        } catch (e) {
            // ignore
        }

        // 3. Lấy trạng thái kết nối Telegram của User
        try {
            const uid = getNovaCutUserId();
            const userRes = await fetch(`/api/telegram/user/status?user_id=${encodeURIComponent(uid)}`);
            if (userRes.ok) {
                const userData = await userRes.json();
                if (userData.success) {
                    updateTelegramUserUI(userData.profile);
                }
            }
        } catch (e) {
            // ignore
        }
    } catch (e) {
        console.warn('Lỗi nạp cấu hình Telegram:', e);
    }
}

// Bắt đầu kết nối Telegram
async function handleStartTelegramConnect() {
    try {
        const uid = getNovaCutUserId();
        showToast('🔄 Đang khởi tạo phiên kết nối Telegram...', 'info');
        const res = await fetch('/api/telegram/connect/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: uid })
        });
        const data = await res.json();
        if (!data.success) {
            showToast('❌ ' + (data.error || 'Không thể khởi tạo phiên kết nối'), 'error');
            return;
        }

        currentTelegramConnectSession = data;

        // Cập nhật UI sang trạng thái WAITING
        const waitingPanel = document.getElementById('telegramWaitingPanel');
        const disconnectedPanel = document.getElementById('telegramDisconnectedPanel');
        const connectedPanel = document.getElementById('telegramConnectedPanel');
        const badge = document.getElementById('telegramUserConnectionBadge');
        const statusText = document.getElementById('telegramUserConnectionStatusText');

        if (waitingPanel) waitingPanel.style.display = 'block';
        if (disconnectedPanel) disconnectedPanel.style.display = 'none';
        if (connectedPanel) connectedPanel.style.display = 'none';
        if (badge) {
            badge.style.background = 'rgba(245, 158, 11, 0.15)';
            badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
            badge.style.color = '#fbbf24';
        }
        if (statusText) statusText.textContent = 'Đang chờ tin nhắn...';

        const botNameEl = document.getElementById('telegramWaitingBotName');
        const cmdEl = document.getElementById('telegramCommandToCopy');
        const groupCmdEl = document.getElementById('telegramGroupCmdToCopy');
        const openLink = document.getElementById('telegramOpenBotLink');

        if (botNameEl) botNameEl.textContent = '@' + (data.bot_username || 'Bot');
        if (cmdEl) cmdEl.textContent = `/start ${data.connect_code}`;
        if (groupCmdEl) groupCmdEl.textContent = `/novacut ${data.connect_code}`;
        if (openLink && data.deep_link) openLink.href = data.deep_link;

        // Bắt đầu đếm ngược 5 phút
        const countdownEl = document.getElementById('telegramConnectCountdown');
        stopTelegramConnectTimers();

        const updateTimer = () => {
            const now = Date.now() / 1000;
            const remain = Math.max(0, Math.floor(data.expires_at - now));
            const m = Math.floor(remain / 60);
            const s = remain % 60;
            if (countdownEl) {
                countdownEl.textContent = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
            if (remain <= 0) {
                stopTelegramConnectTimers();
                showToast('⚠️ Phiên kết nối Telegram đã hết hạn. Vui lòng bấm thử lại.', 'warning');
                updateTelegramUserUI({ connected: false });
            }
        };
        updateTimer();
        telegramCountdownInterval = setInterval(updateTimer, 1000);

        // Bắt đầu polling tự động mỗi 3 giây
        telegramPollingInterval = setInterval(async () => {
            await handlePollTelegramConnect(false);
        }, 3000);

    } catch (err) {
        showToast('❌ Lỗi kết nối: ' + err.message, 'error');
    }
}

// Polling kiểm tra tin nhắn kết nối
async function handlePollTelegramConnect(isManual = false) {
    if (!currentTelegramConnectSession) return;
    try {
        const uid = getNovaCutUserId();
        const res = await fetch('/api/telegram/connect/poll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: uid,
                connect_code: currentTelegramConnectSession.connect_code
            })
        });
        const data = await res.json();

        if (data.status === 'CONNECTED') {
            stopTelegramConnectTimers();
            updateTelegramUserUI({
                connected: true,
                chat_id: data.chat_id,
                chat_type: data.chat_type,
                chat_title: data.chat_title,
                is_group: data.is_group,
                connected_at: data.connected_at
            });
            showToast('🎉 Kết nối Telegram thành công!', 'success');
        } else if (data.status === 'EXPIRED') {
            stopTelegramConnectTimers();
            updateTelegramUserUI({ connected: false });
            showToast('⚠️ Phiên kết nối đã hết hạn sau 5 phút.', 'warning');
        } else if (isManual && data.status === 'WAITING') {
            showToast('⏳ Vẫn đang chờ tin nhắn từ bot. Hãy đảm bảo bạn đã gửi lệnh cho bot.', 'info');
        }
    } catch (err) {
        if (isManual) showToast('❌ Lỗi kiểm tra: ' + err.message, 'error');
    }
}

// Ngắt kết nối Telegram
async function handleDisconnectTelegramUser() {
    const confirmed = await showConfirmModal({
        title: 'Ngắt Kết Nối Telegram',
        message: 'Bạn có chắc chắn muốn ngắt kết nối và xóa Chat ID Telegram của bạn khỏi ứng dụng?',
        icon: '🔌',
        confirmText: 'Ngắt Kết Nối',
        cancelText: 'Hủy',
        confirmType: 'danger'
    });
    if (!confirmed) return;

    try {
        const uid = getNovaCutUserId();
        stopTelegramConnectTimers();
        const res = await fetch('/api/telegram/user/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: uid })
        });
        const data = await res.json();
        if (data.success) {
            updateTelegramUserUI({ connected: false });
            showToast('🔌 Đã ngắt kết nối Telegram thành công.', 'info');
        } else {
            showToast('❌ Không thể ngắt kết nối: ' + (data.error || 'Lỗi server'), 'error');
        }
    } catch (err) {
        showToast('❌ Lỗi: ' + err.message, 'error');
    }
}

// Gửi tin nhắn test tới Chat ID của User
async function handleTestTelegramUser() {
    const btn = document.getElementById('btnTestTelegramUser');
    if (btn) btn.disabled = true;
    try {
        const uid = getNovaCutUserId();
        const tokenInput = document.getElementById('settingsTelegramBotToken');
        const rawToken = tokenInput ? tokenInput.value.trim() : '';
        const bodyPayload = { user_id: uid };
        if (rawToken && !rawToken.includes('•') && !rawToken.startsWith('****')) {
            bodyPayload.bot_token = rawToken;
        }

        showToast('🚀 Đang gửi tin nhắn kiểm tra tới Telegram của bạn...', 'info');
        const res = await fetch('/api/telegram/user/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('✅ ' + data.message, 'success');
        } else {
            const errMsg = data.error || 'Gửi tin nhắn thất bại';
            showToast('❌ ' + errMsg, 'error');
            showAlertModal({
                title: '⚠️ Kiểm Tra Thất Bại',
                message: errMsg,
                theme: 'error'
            });
        }
    } catch (err) {
        showToast('❌ Lỗi gửi tin: ' + err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Áp dụng Chat ID thủ công cho User hiện tại
async function handleApplyManualChatId() {
    const btn = document.getElementById('btnApplyManualChatId');
    const inputEl = document.getElementById('settingsTelegramChatId');
    const tokenInput = document.getElementById('settingsTelegramBotToken');
    const chatId = inputEl ? inputEl.value.trim() : '';
    const rawToken = tokenInput ? tokenInput.value.trim() : '';

    if (!chatId) {
        showToast('⚠️ Vui lòng nhập Chat ID hợp lệ (VD: 5011367599 hoặc -100...)', 'warning');
        if (inputEl) inputEl.focus();
        return;
    }

    if (btn) btn.disabled = true;
    try {
        const uid = getNovaCutUserId();
        showToast('🔄 Đang kiểm tra và áp dụng Chat ID...', 'info');
        const bodyPayload = { user_id: uid, chat_id: chatId };
        if (rawToken && !rawToken.includes('•') && !rawToken.startsWith('****')) {
            bodyPayload.bot_token = rawToken;
        }

        const res = await fetch('/api/telegram/user/manual_connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });
        const data = await res.json();
        if (data.success && data.profile) {
            updateTelegramUserUI(data.profile);
            
            // Tự động bật thông báo Telegram nếu đang tắt
            const tgSwitch = document.getElementById('settingsTelegramEnabled');
            const tgLabel = document.getElementById('settingsTelegramEnabledLabel');
            if (tgSwitch && !tgSwitch.checked) {
                tgSwitch.checked = true;
                if (tgLabel) {
                    tgLabel.textContent = 'BẬT';
                    tgLabel.style.color = '#10b981';
                }
            }

            showToast('🎉 ' + data.message, 'success');
            showAlertModal({
                title: '✈️ Đã Áp Dụng Chat ID Thành Công!',
                message: `${data.message}\n\nChat ID: ${data.profile.chat_id}\nLoại: ${data.profile.chat_type}\nTên: ${data.profile.chat_title || 'N/A'}\n\nNovaCut đã sẵn sàng gửi thông báo tự động tới Telegram này.`,
                theme: 'success'
            });
        } else {
            showToast('❌ ' + (data.error || 'Không thể áp dụng Chat ID'), 'error');
            showAlertModal({
                title: '⚠️ Lỗi Áp Dụng Chat ID',
                message: (data.error || 'Không thể áp dụng Chat ID'),
                theme: 'error'
            });
        }
    } catch (err) {
        showToast('❌ Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Gửi thử thông báo mẫu Telegram (ping, video, batch, failure)
async function handleSendSampleNotification(sampleType, label) {
    const btnMap = {
        'ping': document.getElementById('btnTestPing'),
        'video': document.getElementById('btnTestSampleVideo'),
        'batch': document.getElementById('btnTestSampleBatch'),
        'failure': document.getElementById('btnTestSampleFailure')
    };
    const targetBtn = btnMap[sampleType];
    const statusEl = document.getElementById('settingsTelegramTestStatus');

    if (targetBtn) targetBtn.disabled = true;
    if (statusEl) {
        statusEl.textContent = `Đang gửi ${label}...`;
        statusEl.style.color = '#38bdf8';
    }

    try {
        const uid = getNovaCutUserId();
        const fallbackChatId = document.getElementById('settingsTelegramChatId')?.value?.trim() || '';
        const tokenInput = document.getElementById('settingsTelegramBotToken');
        const rawToken = tokenInput ? tokenInput.value.trim() : '';

        showToast(`🚀 Đang gửi ${label} tới Telegram...`, 'info');

        const payload = {
            user_id: uid,
            sample_type: sampleType,
            chat_id: fallbackChatId
        };
        // Truyền token mới nếu người dùng vừa nhập/dán token không bị mask
        if (rawToken && !rawToken.includes('•') && !rawToken.startsWith('****')) {
            payload.bot_token = rawToken;
        }

        const res = await fetch('/api/telegram/test_sample', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            const usedChat = data.chat_id || fallbackChatId;
            if (statusEl) {
                statusEl.textContent = `✅ ${label} đã gửi thành công! (Chat ID: ${usedChat})`;
                statusEl.style.color = '#10b981';
            }
            showToast(`✅ ${label} đã gửi thành công tới Telegram!`, 'success');
        } else {
            const errMsg = data.error || 'Gửi thất bại';
            if (statusEl) {
                statusEl.textContent = `❌ ${errMsg}`;
                statusEl.style.color = '#f87171';
            }
            showToast(`❌ ${errMsg}`, 'error');

            let guidance = '';
            if (errMsg.includes('401') || errMsg.toLowerCase().includes('unauthorized') || errMsg.toLowerCase().includes('token')) {
                guidance = '\n\n💡 Nguyên nhân: Bot Token của bạn không hợp lệ hoặc đã bị thu hồi trên @BotFather.\n👉 Cách sửa: Hãy mở @BotFather trên Telegram, lấy Token mới, dán vào ô "Telegram Bot Token" rồi bấm Lưu Cài Đặt hoặc bấm Thử lại.';
            } else if (errMsg.includes('403') || errMsg.toLowerCase().includes('forbidden')) {
                guidance = '\n\n💡 Nguyên nhân: Bot chưa được cấp quyền nhắn tin hoặc bị chặn.\n👉 Cách sửa: Mở Telegram, tìm bot và nhấn START (nếu là nhóm: hãy thêm bot vào nhóm và cấp quyền nhắn tin).';
            } else if (errMsg.includes('400') || errMsg.toLowerCase().includes('bad request') || errMsg.toLowerCase().includes('chat not found')) {
                guidance = '\n\n💡 Nguyên nhân: Chat ID không hợp lệ hoặc bot chưa từng nhận tin nhắn từ Chat ID này.\n👉 Cách sửa: Nhấn START trên bot Telegram để kích hoạt trước khi gửi tin nhắn.';
            } else {
                guidance = '\n\n💡 Vui lòng kiểm tra lại cấu hình Bot Token và Chat ID.';
            }

            showAlertModal({
                title: '⚠️ Gửi Thông Báo Thử Nghiệm Thất Bại',
                message: `${errMsg}${guidance}`,
                theme: 'error'
            });
        }
    } catch (err) {
        if (statusEl) {
            statusEl.textContent = `❌ Lỗi mạng: ${err.message}`;
            statusEl.style.color = '#f87171';
        }
        showToast(`❌ Lỗi gửi ${label}: ` + err.message, 'error');
    } finally {
        if (targetBtn) targetBtn.disabled = false;
    }
}

// Khởi tạo các event listeners cho Telegram tab
document.addEventListener('DOMContentLoaded', () => {
    const btnStart = document.getElementById('btnStartTelegramConnect');
    if (btnStart) btnStart.addEventListener('click', handleStartTelegramConnect);

    const btnPoll = document.getElementById('btnPollTelegramChatId');
    if (btnPoll) btnPoll.addEventListener('click', () => handlePollTelegramConnect(true));

    const btnCancel = document.getElementById('btnCancelTelegramConnect');
    if (btnCancel) {
        btnCancel.addEventListener('click', () => {
            stopTelegramConnectTimers();
            updateTelegramUserUI({ connected: false });
        });
    }

    const btnCopy = document.getElementById('btnCopyTelegramCommand');
    if (btnCopy) {
        btnCopy.addEventListener('click', () => {
            const cmdEl = document.getElementById('telegramCommandToCopy');
            if (cmdEl && cmdEl.textContent) {
                navigator.clipboard.writeText(cmdEl.textContent.trim()).then(() => {
                    showToast('📋 Đã sao chép lệnh kết nối!', 'success');
                }).catch(() => {
                    showToast('❌ Không thể sao chép, vui lòng copy thủ công', 'error');
                });
            }
        });
    }

    const btnDisconnect = document.getElementById('btnDisconnectTelegramUser');
    if (btnDisconnect) btnDisconnect.addEventListener('click', handleDisconnectTelegramUser);

    const btnTestUser = document.getElementById('btnTestTelegramUser');
    if (btnTestUser) btnTestUser.addEventListener('click', handleTestTelegramUser);

    // Nút áp dụng Chat ID thủ công
    const btnApplyManual = document.getElementById('btnApplyManualChatId');
    if (btnApplyManual) btnApplyManual.addEventListener('click', handleApplyManualChatId);

    // 4 nút test thông báo mẫu
    const btnPing = document.getElementById('btnTestPing');
    if (btnPing) btnPing.addEventListener('click', () => handleSendSampleNotification('ping', 'Kiểm tra Ping'));

    const btnSampleVid = document.getElementById('btnTestSampleVideo');
    if (btnSampleVid) btnSampleVid.addEventListener('click', () => handleSendSampleNotification('video', 'Mẫu Video Hoàn Thành'));

    const btnSampleBatch = document.getElementById('btnTestSampleBatch');
    if (btnSampleBatch) btnSampleBatch.addEventListener('click', () => handleSendSampleNotification('batch', 'Mẫu Báo Cáo Batch'));

    const btnSampleFail = document.getElementById('btnTestSampleFailure');
    if (btnSampleFail) btnSampleFail.addEventListener('click', () => handleSendSampleNotification('failure', 'Mẫu Báo Lỗi Video'));

    const btnToggleToken = document.getElementById('btnToggleTelegramToken');
    const tokenInput = document.getElementById('settingsTelegramBotToken');
    if (btnToggleToken && tokenInput) {
        btnToggleToken.addEventListener('click', () => {
            tokenInput.type = tokenInput.type === 'password' ? 'text' : 'password';
        });
    }

    const tgSwitch = document.getElementById('settingsTelegramEnabled');
    const tgLabel = document.getElementById('settingsTelegramEnabledLabel');
    if (tgSwitch && tgLabel) {
        tgSwitch.addEventListener('change', () => {
            tgLabel.textContent = tgSwitch.checked ? 'BẬT' : 'TẮT';
            tgLabel.style.color = tgSwitch.checked ? '#10b981' : '#94a3b8';
        });
    }
});

const tabBtnSettingsApi = document.getElementById('tabBtnSettingsApi');
if (tabBtnSettingsApi) {
    tabBtnSettingsApi.addEventListener('click', () => switchSettingsTab('api'));
}

const tabBtnSettingsTelegram = document.getElementById('tabBtnSettingsTelegram');
if (tabBtnSettingsTelegram) {
    tabBtnSettingsTelegram.addEventListener('click', () => switchSettingsTab('telegram'));
}

const tabBtnSettingsDisclaimer = document.getElementById('tabBtnSettingsDisclaimer');
if (tabBtnSettingsDisclaimer) {
    tabBtnSettingsDisclaimer.addEventListener('click', () => switchSettingsTab('disclaimer'));
}

const batchTelegramStatusBadge = document.getElementById('batchTelegramStatusBadge');
if (batchTelegramStatusBadge) {
    batchTelegramStatusBadge.addEventListener('click', () => {
        if (settingsModal) {
            settingsModal.style.display = 'flex';
            settingsModal.classList.add('active');
            switchSettingsTab('telegram');
        }
    });
}

const tgToggle = document.getElementById('settingsTelegramEnabled');
if (tgToggle) {
    tgToggle.addEventListener('change', () => {
        const labelEl = document.getElementById('settingsTelegramEnabledLabel');
        if (labelEl) {
            labelEl.textContent = tgToggle.checked ? 'BẬT' : 'TẮT';
            labelEl.style.color = tgToggle.checked ? '#10b981' : '#94a3b8';
        }
    });
}

const btnToggleTgToken = document.getElementById('btnToggleTelegramToken');
if (btnToggleTgToken) {
    btnToggleTgToken.addEventListener('click', () => {
        const tokInput = document.getElementById('settingsTelegramBotToken');
        if (tokInput) {
            if (tokInput.type === 'password') {
                tokInput.type = 'text';
                btnToggleTgToken.textContent = '🙈';
            } else {
                tokInput.type = 'password';
                btnToggleTgToken.textContent = '👁️';
            }
        }
    });
}

const btnTestTg = document.getElementById('btnTestTelegram');
if (btnTestTg) {
    btnTestTg.addEventListener('click', async () => {
        const tokInput = document.getElementById('settingsTelegramBotToken');
        const chatIdInput = document.getElementById('settingsTelegramChatId');
        const statusEl = document.getElementById('settingsTelegramTestStatus');

        let tokVal = tokInput?.value?.trim() || '';
        let chatIdVal = chatIdInput?.value?.trim() || '5011367599';

        btnTestTg.disabled = true;
        const originalText = btnTestTg.innerHTML;
        btnTestTg.innerHTML = '<span>⏳</span> <span>Đang gửi...</span>';
        if (statusEl) {
            statusEl.textContent = 'Đang kết nối tới Telegram API...';
            statusEl.style.color = '#38bdf8';
        }

        try {
            const resp = await fetch('/api/telegram/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bot_token: tokVal, chat_id: chatIdVal })
            });
            const data = await resp.json();
            if (resp.ok && data.success) {
                if (statusEl) {
                    statusEl.textContent = '✅ ' + data.message;
                    statusEl.style.color = '#10b981';
                }
                showToast('✅ Gửi tin nhắn Telegram thành công!', 'success');
                showAlertModal({
                    title: '✈️ Kết Nối Telegram Thành Công!',
                    message: data.message + '\n\nChat ID: ' + chatIdVal + '\n\nNovaCut đã sẵn sàng gửi thông báo tự động cho các tác vụ hàng loạt!',
                    theme: 'success'
                });
            } else {
                const errMsg = data.error || 'Lỗi gửi tin nhắn kiểm tra';
                if (statusEl) {
                    statusEl.textContent = '❌ ' + errMsg;
                    statusEl.style.color = '#f87171';
                }
                showToast('❌ ' + errMsg, 'error');
                showAlertModal({
                    title: '⚠️ Kiểm Tra Telegram Thất Bại',
                    message: errMsg + '\n\nVui lòng kiểm tra:\n1. Bot Token đã tạo từ @BotFather hợp lệ.\n2. Bạn đã nhấn /start trong cuộc trò chuyện với Bot trên Telegram.\n3. Chat ID đã nhập chính xác.',
                    theme: 'error'
                });
            }
        } catch (err) {
            if (statusEl) {
                statusEl.textContent = '❌ Lỗi mạng: ' + err.message;
                statusEl.style.color = '#f87171';
            }
            showToast('❌ Lỗi kết nối mạng', 'error');
        } finally {
            btnTestTg.disabled = false;
            btnTestTg.innerHTML = originalText;
        }
    });
}

const btnOpenPopupDisclaimerFromSettings = document.getElementById('btnOpenPopupDisclaimerFromSettings');
if (btnOpenPopupDisclaimerFromSettings) {
    btnOpenPopupDisclaimerFromSettings.addEventListener('click', () => {
        closeSettingsModal();
        if (modalCopyrightDisclaimer) {
            if (chkAgreeCopyrightDisclaimer) {
                chkAgreeCopyrightDisclaimer.checked = localStorage.getItem('ams_copyright_disclaimer_accepted') === 'true';
                if (chkAgreeCopyrightDisclaimer.checked && btnAcceptCopyrightDisclaimer) {
                    btnAcceptCopyrightDisclaimer.disabled = false;
                    btnAcceptCopyrightDisclaimer.style.background = 'linear-gradient(135deg, #0ea5e9, #06b6d4)';
                    btnAcceptCopyrightDisclaimer.style.color = '#ffffff';
                    btnAcceptCopyrightDisclaimer.style.cursor = 'pointer';
                    btnAcceptCopyrightDisclaimer.style.boxShadow = '0 4px 18px rgba(6, 182, 212, 0.4)';
                }
            }
            modalCopyrightDisclaimer.style.display = 'flex';
        }
    });
}

const closeSettingsFooterBtn = document.getElementById('closeSettingsFooterBtn');
if (closeSettingsFooterBtn) {
    closeSettingsFooterBtn.addEventListener('click', closeSettingsModal);
}

if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
        if (settingsModal) {
            settingsModal.style.display = 'flex';
            settingsModal.classList.add('active');
            updateSettingsModalPermissions(currentLicenseState);
            updateSettingsDisclaimerStatus();
            loadTelegramSettings();
        }
    });
}

function closeSettingsModal() {
    if (settingsModal) {
        settingsModal.style.display = 'none';
        settingsModal.classList.remove('active');
    }
}

if (closeSettingsBtn) {
    closeSettingsBtn.addEventListener('click', closeSettingsModal);
}

const btnFetchSystemApi = document.getElementById('btnFetchSystemApi');
if (btnFetchSystemApi) {
    btnFetchSystemApi.addEventListener('click', async () => {
        btnFetchSystemApi.disabled = true;
        btnFetchSystemApi.textContent = 'Đang tải...';
        try {
            showToast('🔄 Đang kiểm tra API cấp sẵn...', 'info');
            const res = await fetch('/api/license/get_system_api', { method: 'POST' });
            const data = await res.json();
            
            if (data.has_keys) {
                const openaiKey = document.getElementById('openaiKey');
                const openSpeakerApiKey = document.getElementById('openSpeakerApiKey');
                
                if (openaiKey) {
                    openaiKey.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Cấp Sẵn]';
                    openaiKey.readOnly = true;
                    openaiKey.type = 'password';
                    openaiKey.style.background = 'rgba(168, 85, 247, 0.08)';
                    openaiKey.style.borderColor = 'rgba(168, 85, 247, 0.4)';
                    openaiKey.style.color = '#c084fc';
                    openaiKey.style.cursor = 'not-allowed';
                    if (typeof openaiKey.setAttribute === 'function') {
                        openaiKey.setAttribute('oncopy', 'return false;');
                        openaiKey.setAttribute('oncut', 'return false;');
                        openaiKey.setAttribute('oncontextmenu', 'return false;');
                    }
                }
                if (openSpeakerApiKey) {
                    openSpeakerApiKey.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Cấp Sẵn]';
                    openSpeakerApiKey.readOnly = true;
                    openSpeakerApiKey.type = 'password';
                    openSpeakerApiKey.style.background = 'rgba(168, 85, 247, 0.08)';
                    openSpeakerApiKey.style.borderColor = 'rgba(168, 85, 247, 0.4)';
                    openSpeakerApiKey.style.color = '#c084fc';
                    openSpeakerApiKey.style.cursor = 'not-allowed';
                    if (typeof openSpeakerApiKey.setAttribute === 'function') {
                        openSpeakerApiKey.setAttribute('oncopy', 'return false;');
                        openSpeakerApiKey.setAttribute('oncut', 'return false;');
                        openSpeakerApiKey.setAttribute('oncontextmenu', 'return false;');
                    }
                }

                const settingsApiTierBadge = document.getElementById('settingsApiTierBadge');
                if (settingsApiTierBadge) {
                    settingsApiTierBadge.innerHTML = '👑 Đã Dùng API Cấp Sẵn';
                    settingsApiTierBadge.style.color = '#c084fc';
                    settingsApiTierBadge.style.background = 'rgba(168, 85, 247, 0.15)';
                }
                
                if (data.license) updateLicenseUI(data.license);
                showToast('👑 Lấy API cấp sẵn thành công!', 'success');
                appendLog('⭐ Lấy API cấp sẵn thành công!', 'info');
            } else {
                await showAlertModal({
                    title: '⚠️ Chưa Có API Cấp Sẵn',
                    icon: '🔑',
                    type: 'warning',
                    message: data.message || 'Chưa tìm thấy API Key cấp sẵn cho tài khoản này trên máy chủ. Bạn có thể tự nhập API Key cá nhân của mình để sử dụng!',
                    buttons: [
                        {
                            text: '✏️ Nhập Key Cá Nhân',
                            primary: true,
                            onClick: () => {
                                const btnUseCustom = document.getElementById('btnUseCustomApi');
                                if (btnUseCustom) btnUseCustom.click();
                            }
                        }
                    ]
                });
            }
        } catch (err) {
            showToast('❌ Lấy API thất bại: ' + err.message, 'error');
        } finally {
            btnFetchSystemApi.disabled = false;
            btnFetchSystemApi.textContent = '🔄 Lấy API Cấp Sẵn';
        }
    });
}

const btnUseCustomApi = document.getElementById('btnUseCustomApi');
if (btnUseCustomApi) {
    btnUseCustomApi.addEventListener('click', async () => {
        const openaiKey = document.getElementById('openaiKey');
        const openSpeakerApiKey = document.getElementById('openSpeakerApiKey');

        if (openaiKey) {
            if (openaiKey.value.includes('[Bản Quyền VIP') || openaiKey.value.startsWith('•')) openaiKey.value = '';
            openaiKey.readOnly = false;
            openaiKey.type = 'password';
            openaiKey.style.background = '#0f172a';
            openaiKey.style.borderColor = '#334155';
            openaiKey.style.color = '#fff';
            openaiKey.style.cursor = 'text';
            if (typeof openaiKey.removeAttribute === 'function') {
                openaiKey.removeAttribute('oncopy');
                openaiKey.removeAttribute('oncut');
                openaiKey.removeAttribute('oncontextmenu');
            }
            openaiKey.focus();
        }

        if (openSpeakerApiKey) {
            if (openSpeakerApiKey.value.includes('[Bản Quyền VIP') || openSpeakerApiKey.value.startsWith('•')) openSpeakerApiKey.value = '';
            openSpeakerApiKey.readOnly = false;
            openSpeakerApiKey.type = 'password';
            openSpeakerApiKey.style.background = '#0f172a';
            openSpeakerApiKey.style.borderColor = '#334155';
            openSpeakerApiKey.style.color = '#fff';
            openSpeakerApiKey.style.cursor = 'text';
            if (typeof openSpeakerApiKey.removeAttribute === 'function') {
                openSpeakerApiKey.removeAttribute('oncopy');
                openSpeakerApiKey.removeAttribute('oncut');
                openSpeakerApiKey.removeAttribute('oncontextmenu');
            }
        }

        const settingsApiTierBadge = document.getElementById('settingsApiTierBadge');
        if (settingsApiTierBadge) {
            settingsApiTierBadge.innerHTML = '✏️ Đang dùng Key Cá Nhân';
            settingsApiTierBadge.style.color = '#fbbf24';
            settingsApiTierBadge.style.background = 'rgba(245, 158, 11, 0.15)';
        }

        showToast('✏️ Đã mở khóa ô nhập để bạn tự điền API Key cá nhân của mình!', 'info');
    });
}

// Toggle Visibility cho các ô API Key
const btnToggleOpenaiKey = document.getElementById('btnToggleOpenaiKey');
if (btnToggleOpenaiKey) {
    btnToggleOpenaiKey.addEventListener('click', (e) => {
        e.preventDefault();
        const input = document.getElementById('openaiKey');
        if (input) {
            input.type = input.type === 'password' ? 'text' : 'password';
            btnToggleOpenaiKey.textContent = input.type === 'password' ? '👁️' : '🙈';
        }
    });
}

const btnToggleOpenSpeakerKey = document.getElementById('btnToggleOpenSpeakerKey');
if (btnToggleOpenSpeakerKey) {
    btnToggleOpenSpeakerKey.addEventListener('click', (e) => {
        e.preventDefault();
        const input = document.getElementById('openSpeakerApiKey');
        if (input) {
            input.type = input.type === 'password' ? 'text' : 'password';
            btnToggleOpenSpeakerKey.textContent = input.type === 'password' ? '👁️' : '🙈';
        }
    });
}

const btnTestApiKey = document.getElementById('btnTestApiKey');
if (btnTestApiKey) {
    btnTestApiKey.addEventListener('click', async () => {
        const openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
        const modelSelect = document.getElementById('openaiModelSelect');
        const customModelInput = document.getElementById('openaiModelCustomInput');
        let openaiModel = modelSelect?.value || document.getElementById('openaiModel')?.value || 'qwen/qwen3.7-flash';
        if (modelSelect && modelSelect.value === 'custom') {
            openaiModel = customModelInput?.value?.trim() || 'qwen/qwen3.7-flash';
        }
        let openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://openrouter.ai/api/v1';
        if (openaiKey.startsWith('sk-or-')) {
            openaiBaseUrl = 'https://openrouter.ai/api/v1';
        }

        const isVip = (currentLicenseState && (currentLicenseState.tier === 'vip' || currentLicenseState.tier === 'yearly'));
        if (!openaiKey && !isVip) {
            showToast('⚠️ Vui lòng nhập API Key (OpenRouter hoặc OpenAI) trước khi test!', 'warning');
            return;
        }

        btnTestApiKey.disabled = true;
        btnTestApiKey.textContent = 'Đang test...';
        try {
            const res = await fetch('/api/test_openai_key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    openai_key: openaiKey,
                    test_vip: isVip,
                    openai_base_url: openaiBaseUrl,
                    openai_model: openaiModel
                })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message || '🎉 API Key hợp lệ!', 'success');
            } else {
                showToast(data.error || '❌ API Key không hợp lệ!', 'error');
            }
        } catch (err) {
            showToast('Lỗi kết nối khi test API: ' + err.message, 'error');
        } finally {
            btnTestApiKey.disabled = false;
            btnTestApiKey.textContent = 'Test Key';
        }
    });
}

// Model Selector Event Listeners
const modelSelect = document.getElementById('openaiModelSelect');
const openaiModelEl = document.getElementById('openaiModel');
const customModelRow = document.getElementById('openaiModelCustomRow');
const customModelInput = document.getElementById('openaiModelCustomInput');

if (modelSelect) {
    modelSelect.addEventListener('change', () => {
        if (modelSelect.value === 'custom') {
            if (customModelRow) customModelRow.style.display = 'block';
            if (customModelInput) {
                customModelInput.focus();
                if (openaiModelEl) openaiModelEl.value = customModelInput.value.trim() || 'custom';
            }
        } else {
            if (customModelRow) customModelRow.style.display = 'none';
            if (openaiModelEl) openaiModelEl.value = modelSelect.value;
        }
    });
}
if (customModelInput) {
    customModelInput.addEventListener('input', () => {
        if (modelSelect && modelSelect.value === 'custom' && openaiModelEl) {
            openaiModelEl.value = customModelInput.value.trim();
        }
    });
}

const openaiKeyInput = document.getElementById('openaiKey');
const openaiBaseUrlInput = document.getElementById('openaiBaseUrl');
if (openaiKeyInput && openaiBaseUrlInput) {
    openaiKeyInput.addEventListener('input', () => {
        const val = openaiKeyInput.value.trim();
        if (val.startsWith('sk-or-')) {
            openaiBaseUrlInput.value = 'https://openrouter.ai/api/v1';
        } else if (val.startsWith('sk-proj-') || val.startsWith('sk-')) {
            openaiBaseUrlInput.value = 'https://api.openai.com/v1';
        }
    });
}

if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async () => {
        saveSettingsBtn.disabled = true;
        try {
            const mSelect = document.getElementById('openaiModelSelect');
            const customInput = document.getElementById('openaiModelCustomInput');
            let chosenModel = mSelect?.value || document.getElementById('openaiModel')?.value || 'qwen/qwen3.7-flash';
            if (mSelect && mSelect.value === 'custom') {
                chosenModel = customInput?.value?.trim() || 'qwen/qwen3.7-flash';
            }
            let keyVal = document.getElementById('openaiKey')?.value?.trim() || '';
            let baseUrlVal = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://openrouter.ai/api/v1';
            if (keyVal.startsWith('sk-or-') || !baseUrlVal || baseUrlVal === 'https://api.openai.com/v1') {
                baseUrlVal = 'https://openrouter.ai/api/v1';
            }
            const payload = {
                openaiKey: keyVal,
                openaiBaseUrl: baseUrlVal,
                openaiModel: chosenModel,
                openSpeakerApiKey: document.getElementById('openSpeakerApiKey')?.value?.trim() || ''
            };
            await fetch('/api/keys', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            // Lưu cấu hình Telegram
            try {
                const tgEnabled = document.getElementById('settingsTelegramEnabled')?.checked || false;
                const tgToken = document.getElementById('settingsTelegramBotToken')?.value?.trim() || '';
                const tgChatId = document.getElementById('settingsTelegramChatId')?.value?.trim() || '5011367599';
                const tgPerVideo = document.getElementById('settingsTelegramNotifyPerVideo')?.checked ?? true;
                const tgBatchDone = document.getElementById('settingsTelegramNotifyBatchDone')?.checked ?? true;

                const uid = getNovaCutUserId();
                await fetch('/api/telegram/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        enabled: tgEnabled,
                        bot_token: tgToken,
                        chat_id: tgChatId,
                        notify_per_video: tgPerVideo,
                        notify_batch_done: tgBatchDone,
                        user_id: uid
                    })
                });
                loadTelegramSettings();
            } catch (tgErr) {
                console.warn('Lỗi lưu cấu hình Telegram:', tgErr);
            }

            closeSettingsModal();
            showToast('💾 Lưu cài đặt thành công!', 'success');
            appendLog('💾 Lưu cài đặt thành công!', 'info');
        } catch(err) {
            showToast('❌ Lưu cài đặt thất bại: ' + err.message, 'error');
        } finally {
            saveSettingsBtn.disabled = false;
        }
    });
}

if (settingsModal) {
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            closeSettingsModal();
        }
    });
}

// Subtitle Extraction Tabs Logic
const tabSrt = document.getElementById('tabSrt');
const tabOcr = document.getElementById('tabOcr');
const tabAsr = document.getElementById('tabAsr');
const contentSrt = document.getElementById('contentSrt');
const contentOcr = document.getElementById('contentOcr');
const contentAsr = document.getElementById('contentAsr');

function switchExtTab(tabId) {
    [tabSrt, tabOcr, tabAsr].forEach(t => t.classList.remove('active'));
    [contentSrt, contentOcr, contentAsr].forEach(c => c.classList.remove('active'));
    
    if (tabId === 'srt') {
        tabSrt.classList.add('active');
        contentSrt.classList.add('active');
    } else if (tabId === 'ocr') {
        tabOcr.classList.add('active');
        contentOcr.classList.add('active');
    } else if (tabId === 'asr') {
        tabAsr.classList.add('active');
        contentAsr.classList.add('active');
    }
}

if (tabSrt) tabSrt.addEventListener('click', () => switchExtTab('srt'));
if (tabOcr) tabOcr.addEventListener('click', () => switchExtTab('ocr'));
if (tabAsr) tabAsr.addEventListener('click', () => switchExtTab('asr'));

// SRT Upload Logic in Subtitle Extraction block
const btnSelectSrtExt = document.getElementById('btnSelectSrtExt');
const manualSrtPathExt = document.getElementById('manualSrtPath');
if (btnSelectSrtExt) {
    btnSelectSrtExt.addEventListener('click', async () => {
    const path = await selectFile('srt');
    if (path) {
        manualSrtPathExt.value = path;
        const title = btnSelectSrtExt.querySelector('.upload-title');
        title.textContent = path.split('\\\\').pop() || path.split('/').pop();
        title.style.color = '#10b981'; // Green color
        
        if (typeof loadSrtToEditor === 'function') {
            loadSrtToEditor(path);
        }
    }
});
}

// ═════════════════════════════════════════════════════════════
// GENERIC DRAWING & OCR / SUBTITLE REGION LOGIC (ZOOM-AWARE)
// ═════════════════════════════════════════════════════════════
const btnDrawRegion = document.getElementById('btnDrawRegion');
const btnDrawSubRegion = document.getElementById('btnDrawSubRegion');
const videoOverlay = document.getElementById('videoOverlay');
const ocrRegionCoords = document.getElementById('ocrRegionCoords');

let isDrawing = false;
let startX, startY;
let drawBox = null;
let currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 }; // for OCR & Dynamic Blur reference (in % of video frame)
const extraOcrRegions = [];
let extraOcrVideoPath = '';
function renderExtraOcrRegions() {
    const list = document.getElementById('ocrExtraRegions');
    if (!list) return;
    list.replaceChildren();
    extraOcrRegions.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = 'region-item';
        const label = document.createElement('span');
        const r = item.region;
        label.textContent = `${index + 2}. ${r.label} — X:${r.x}% Y:${r.y}% W:${r.w}% H:${r.h}%`;
        const remove = document.createElement('button');
        remove.className = 'btn secondary small';
        remove.textContent = 'Xóa';
        remove.onclick = () => {
            if (isExtractingOCR) return;
            item.box.remove();
            extraOcrRegions.splice(index, 1);
            renderExtraOcrRegions();
        };
        row.append(label, remove);
        list.append(row);
    });
    document.getElementById('ocrRegionCount').textContent = `${1 + extraOcrRegions.length}/8 vùng`;
}
function resetExtraOcrRegionsForVideo() {
    const path = document.getElementById('editorInputVideoPath')?.value || '';
    if (path !== extraOcrVideoPath) {
        extraOcrRegions.forEach(item => item.box.remove());
        extraOcrRegions.length = 0;
        extraOcrVideoPath = path;
        renderExtraOcrRegions();
    }
}
document.getElementById('btnAddOcrRegion')?.addEventListener('click', () => {
    if (isExtractingOCR) return;
    resetExtraOcrRegionsForVideo();
    if (extraOcrRegions.length >= 7) return showToast('Tối đa 8 vùng OCR.', 'warning');
    startDrawMode('ocr_extra');
});
let currentSubRegion = null; // for Subtitle
let drawMode = 'ocr'; // 'ocr' or 'sub'
let subPreviewBox = null; // persistent box for subtitle preview

/**
 * Tính toán hình chữ nhật thực sự được hiển thị của Video bên trong videoZoomWrapper (loại trừ letterbox do object-fit: contain)
 */
function getVideoContentRect() {
    const vp = document.getElementById('videoPlayer');
    const wrapper = document.getElementById('videoZoomWrapper');
    if (!wrapper) return { videoX: 0, videoY: 0, videoW: 100, videoH: 100, wrapperW: 100, wrapperH: 100 };
    
    const wrapperW = wrapper.clientWidth || (videoContainer ? videoContainer.clientWidth : 800);
    const wrapperH = wrapper.clientHeight || (videoContainer ? videoContainer.clientHeight : 450);
    const vW = (vp && vp.videoWidth) ? vp.videoWidth : 0;
    const vH = (vp && vp.videoHeight) ? vp.videoHeight : 0;
    
    if (!vW || !vH || wrapperW <= 0 || wrapperH <= 0) {
        return { videoX: 0, videoY: 0, videoW: wrapperW, videoH: wrapperH, wrapperW, wrapperH };
    }
    
    const videoAR = vW / vH;
    const wrapperAR = wrapperW / wrapperH;
    
    let renderW, renderH, renderX, renderY;
    if (videoAR > wrapperAR) {
        renderW = wrapperW;
        renderH = wrapperW / videoAR;
        renderX = 0;
        renderY = (wrapperH - renderH) / 2;
    } else {
        renderH = wrapperH;
        renderW = wrapperH * videoAR;
        renderX = (wrapperW - renderW) / 2;
        renderY = 0;
    }
    
    return {
        videoX: renderX,
        videoY: renderY,
        videoW: renderW,
        videoH: renderH,
        wrapperW,
        wrapperH
    };
}

/**
 * Đặt vị trí cho Box theo % video zoom wrapper dựa trên % thực của khung hình video
 */
function applyBoxPercentToWrapper(box, pX, pY, pW, pH, vRect) {
    if (!box) return;
    if (!vRect) vRect = getVideoContentRect();
    const boxX = vRect.videoX + (pX / 100) * vRect.videoW;
    const boxY = vRect.videoY + (pY / 100) * vRect.videoH;
    const boxW = (pW / 100) * vRect.videoW;
    const boxH = (pH / 100) * vRect.videoH;
    
    box.style.position = 'absolute';
    box.style.left = `${(boxX / vRect.wrapperW) * 100}%`;
    box.style.top = `${(boxY / vRect.wrapperH) * 100}%`;
    box.style.width = `${(boxW / vRect.wrapperW) * 100}%`;
    box.style.height = `${(boxH / vRect.wrapperH) * 100}%`;
    box.style.bottom = 'auto';
    box.style.right = 'auto';
}

function getActiveZoomLevel() {
    if (typeof videoStudioInstances !== 'undefined' && videoStudioInstances.editor && videoStudioInstances.editor.state) {
        return videoStudioInstances.editor.state.zoom || 1.0;
    }
    return currentVideoZoom || 1.0;
}

function startDrawMode(mode) {
    if (mode === 'ocr') {
        resetExtraOcrRegionsForVideo();
        document.querySelectorAll('.ocr-draw-box:not(.ocr-extra-box)').forEach(box => box.remove());
    }
    drawMode = mode;
    window.isDrawingRegion = true;
    
    const container = document.getElementById('videoContainer') || videoContainer;
    if (container) container.classList.add('is-drawing-region');
    const canvasFrame = document.getElementById('videoCanvasFrame');
    if (canvasFrame) canvasFrame.classList.add('is-drawing-region');
    
    // Tắt và ẩn hoàn toàn CapCut Transform Box & 8-point zoom box
    document.querySelectorAll('.capcut-transform-box').forEach(el => {
        el.classList.remove('active');
        el.style.display = 'none';
    });
    if (typeof videoStudioInstances !== 'undefined') {
        if (videoStudioInstances.editor && typeof videoStudioInstances.editor.hideTransformBox === 'function') {
            videoStudioInstances.editor.hideTransformBox(true);
        }
        if (videoStudioInstances.review && typeof videoStudioInstances.review.hideTransformBox === 'function') {
            videoStudioInstances.review.hideTransformBox(true);
        }
    }
    if (typeof isZoomBoxVisible !== 'undefined' && isZoomBoxVisible && typeof toggleZoomBox === 'function') {
        toggleZoomBox(false);
    }
    
    if (videoOverlay) {
        videoOverlay.style.zIndex = '999';
        videoOverlay.style.pointerEvents = 'auto';
        videoOverlay.style.display = 'block';
    }
    if (drawBox) {
        if (mode !== 'ocr_extra' || !drawBox.classList.contains('ocr-draw-box')) drawBox.remove();
        drawBox = null;
    }
}

if (btnDrawRegion) btnDrawRegion.addEventListener('click', () => startDrawMode('ocr'));
if (btnDrawSubRegion) btnDrawSubRegion.addEventListener('click', () => startDrawMode('sub'));

// Hủy vẽ vùng khi nhấn phím Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && window.isDrawingRegion) {
        isDrawing = false;
        window.isDrawingRegion = false;
        if (videoOverlay) videoOverlay.style.display = 'none';
        
        const container = document.getElementById('videoContainer') || videoContainer;
        if (container) container.classList.remove('is-drawing-region');
        const canvasFrame = document.getElementById('videoCanvasFrame');
        if (canvasFrame) canvasFrame.classList.remove('is-drawing-region');
        
        document.querySelectorAll('.capcut-transform-box').forEach(el => {
            el.style.display = '';
        });
        if (drawBox && !drawBox.parentElement?.classList.contains('video-zoom-wrapper')) {
            drawBox.remove();
            drawBox = null;
        }
    }
});

// Xử lý nút xóa / reset vùng OCR
const btnTrashOcrRegion = document.querySelector('.region-item .trash-btn');
if (btnTrashOcrRegion) {
    btnTrashOcrRegion.addEventListener('click', (e) => {
        e.stopPropagation();
        if (drawBox) {
            drawBox.remove();
            drawBox = null;
        }
        const existingBoxes = document.querySelectorAll('.ocr-draw-box:not(.ocr-extra-box)');
        existingBoxes.forEach(b => b.remove());
        
        currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };
        if (ocrRegionCoords) ocrRegionCoords.textContent = 'Chưa chọn vùng';
        showToast('Đã xóa vùng quét OCR. Bạn có thể bấm "Vẽ vùng mới" để vẽ lại.', 'info');
    });
}

if (videoOverlay) {
    videoOverlay.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        isDrawing = true;
        const rect = videoOverlay.getBoundingClientRect();
        const zoom = getActiveZoomLevel();
        
        // Chuyển tọa độ chuột trên màn hình thành tọa độ unscaled bên trong videoZoomWrapper
        startX = (e.clientX - rect.left) / zoom;
        startY = (e.clientY - rect.top) / zoom;
        
        drawBox = document.createElement('div');
        if (drawMode === 'ocr' || drawMode === 'ocr_extra') {
            drawBox.className = 'ocr-draw-box';
        } else if (drawMode === 'blur' || drawMode === 'review_blur') {
            drawBox.className = 'blur-adjust-box';
            drawBox.innerHTML = '<div class="blur-adjust-badge"><span>📐 Vùng làm mờ</span></div>';
        } else {
            if (subPreviewBox) {
                subPreviewBox.remove();
                subPreviewBox = null;
            }
            drawBox.className = 'sub-preview-box';
            applySubStylesToElement(drawBox);
            drawBox.innerHTML = '<span class="sub-text-inner">Phụ đề mẫu</span>';
        }
        
        drawBox.style.position = 'absolute';
        drawBox.style.left = startX + 'px';
        drawBox.style.top = startY + 'px';
        drawBox.style.width = '0px';
        drawBox.style.height = '0px';
        drawBox.style.pointerEvents = 'none';
        videoOverlay.appendChild(drawBox);
    });

    videoOverlay.addEventListener('mousemove', (e) => {
        if (!isDrawing || !drawBox) return;
        const rect = videoOverlay.getBoundingClientRect();
        const zoom = getActiveZoomLevel();
        
        const wrapper = videoZoomWrapper || videoOverlay;
        const maxW = wrapper.clientWidth || (rect.width / zoom);
        const maxH = wrapper.clientHeight || (rect.height / zoom);
        
        let currentX = (e.clientX - rect.left) / zoom;
        let currentY = (e.clientY - rect.top) / zoom;
        
        currentX = Math.max(0, Math.min(currentX, maxW));
        currentY = Math.max(0, Math.min(currentY, maxH));
        
        const width = Math.abs(currentX - startX);
        const height = Math.abs(currentY - startY);
        const left = Math.min(startX, currentX);
        const top = Math.min(startY, currentY);
        
        drawBox.style.width = width + 'px';
        drawBox.style.height = height + 'px';
        drawBox.style.left = left + 'px';
        drawBox.style.top = top + 'px';
    });

    videoOverlay.addEventListener('mouseup', () => {
        if (!isDrawing) return;
        isDrawing = false;
        videoOverlay.style.display = 'none'; 
        window.isDrawingRegion = false;
        
        const container = document.getElementById('videoContainer') || videoContainer;
        if (container) container.classList.remove('is-drawing-region');
        const canvasFrame = document.getElementById('videoCanvasFrame');
        if (canvasFrame) canvasFrame.classList.remove('is-drawing-region');
        
        document.querySelectorAll('.capcut-transform-box').forEach(el => {
            el.style.display = '';
        });
        
        if (drawBox) {
            const wrapper = videoZoomWrapper || videoContainer;
            wrapper.appendChild(drawBox);
            
            const vRect = getVideoContentRect();
            const unscaledLeft = parseFloat(drawBox.style.left) || 0;
            const unscaledTop = parseFloat(drawBox.style.top) || 0;
            const unscaledWidth = parseFloat(drawBox.style.width) || 0;
            const unscaledHeight = parseFloat(drawBox.style.height) || 0;
            
            // Tránh click chuột vô tình tạo box cực nhỏ (< 6px)
            if (unscaledWidth < 6 || unscaledHeight < 6) {
                drawBox.remove();
                drawBox = null;
                return;
            }
            
            // Quy đổi sang % thực tế của khung hình Video (0..100)
            let pX = ((unscaledLeft - vRect.videoX) / vRect.videoW) * 100;
            let pY = ((unscaledTop - vRect.videoY) / vRect.videoH) * 100;
            let pW = (unscaledWidth / vRect.videoW) * 100;
            let pH = (unscaledHeight / vRect.videoH) * 100;
            
            pX = Math.max(0, Math.min(100, Math.round(pX * 10) / 10));
            pY = Math.max(0, Math.min(100, Math.round(pY * 10) / 10));
            pW = Math.max(1, Math.min(100 - pX, Math.round(pW * 10) / 10));
            pH = Math.max(1, Math.min(100 - pY, Math.round(pH * 10) / 10));
            
            // Định vị lại Box theo % Wrapper để phóng to thu nhỏ Zoom tự động co dãn theo video
            applyBoxPercentToWrapper(drawBox, pX, pY, pW, pH, vRect);
            
            if (drawMode === 'ocr') {
                currentRegion = { x: pX, y: pY, w: pW, h: pH };
                if (ocrRegionCoords) ocrRegionCoords.textContent = `X: ${pX}% • Y: ${pY}% • W: ${pW}% • H: ${pH}%`;
                
                const editorInputVideoPath = document.getElementById('editorInputVideoPath');
                const filename = (editorInputVideoPath && editorInputVideoPath.value) ? (editorInputVideoPath.value.split('\\').pop().split('/').pop()) : 'Chưa chọn video...';
                const ocrRegionFilename = document.getElementById('ocrRegionFilename');
                if (ocrRegionFilename) ocrRegionFilename.textContent = filename;

                // Kích hoạt kéo thả và co giãn 8 hướng độc lập cho OCR draw box
                setupResizableAndDraggableBox(drawBox, (newPx, newPy, newPw, newPh) => {
                    currentRegion = { x: newPx, y: newPy, w: newPw, h: newPh };
                    if (ocrRegionCoords) ocrRegionCoords.textContent = `X: ${newPx}% • Y: ${newPy}% • W: ${newPw}% • H: ${newPh}%`;
                    syncBlurRegionInputs(newPx, newPy, newPw, newPh);
                    updateDynamicBlurOverlayVisibility();
                });
                syncBlurRegionInputs(pX, pY, pW, pH);
                updateDynamicBlurOverlayVisibility();
            } else if (drawMode === 'blur') {
                setManualBlurRegion();
                currentRegion = { x: pX, y: pY, w: pW, h: pH };
                syncBlurRegionInputs(pX, pY, pW, pH);
                drawBox.remove();
                drawBox = null;
                showBlurAdjustBox(true);
                updateDynamicBlurOverlayVisibility();
                showToast(`🎯 Đã lưu vùng làm mờ: X:${pX}% • Y:${pY}% • W:${pW}% • H:${pH}%`, "success");
            } else if (drawMode === 'review_blur') {
                window.reviewBlurRegion = { x: pX, y: pY, w: pW, h: pH };
                syncReviewBlurRegionInputs(pX, pY, pW, pH);
                drawBox.remove();
                drawBox = null;
                showReviewBlurAdjustBox(true);
                if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
                showToast(`🎯 Đã lưu vùng làm mờ Review: X:${pX}% • Y:${pY}% • W:${pW}% • H:${pH}%`, "success");
            } else if (drawMode === 'ocr_extra') {
                const item = {
                    region: { x: pX, y: pY, w: pW, h: pH, label: document.getElementById('ocrExtraRole').value },
                    box: drawBox
                };
                drawBox.classList.add('ocr-extra-box');
                drawBox.style.borderColor = '#c084fc';
                drawBox.title = item.region.label;
                extraOcrRegions.push(item);
                setupResizableAndDraggableBox(drawBox, (x, y, w, h) => {
                    Object.assign(item.region, { x, y, w, h });
                    renderExtraOcrRegions();
                });
                renderExtraOcrRegions();
                drawBox = null;
            } else if (drawMode === 'sub') {
                currentSubRegion = { x: pX, y: pY, w: pW, h: pH, customPos: true };
                subPreviewBox = drawBox;
                const wrapper = document.getElementById('videoZoomWrapper') || videoContainer;
                if (wrapper && subPreviewBox.parentElement !== wrapper) {
                    wrapper.appendChild(subPreviewBox);
                }
                syncSubRegionInputs(pX, pY, pW, pH);
                showSubAdjustBox(true);
                showToast(`🎯 Đã lưu khung phụ đề: X:${pX}% • Y:${pY}% • W:${pW}% • H:${pH}%`, "success");
            }
        }
    });
}

function syncSubRegionInputs(pX, pY, pW, pH) {
    const elW = document.getElementById('subBoxWidth');
    const elH = document.getElementById('subBoxHeight');
    const elX = document.getElementById('subBoxX');
    const elY = document.getElementById('subBoxY');
    
    const valW = document.getElementById('subBoxWidthVal');
    const valH = document.getElementById('subBoxHeightVal');
    const valX = document.getElementById('subBoxXVal');
    const valY = document.getElementById('subBoxYVal');

    if (elW && pW !== undefined) { elW.value = pW; if (valW) valW.textContent = `${pW}%`; }
    if (elH && pH !== undefined) { elH.value = pH; if (valH) valH.textContent = `${pH}%`; }
    if (elX && pX !== undefined) { elX.value = pX; if (valX) valX.textContent = `${pX}%`; }
    if (elY && pY !== undefined) { elY.value = pY; if (valY) valY.textContent = `${pY}%`; }

    if (subPreviewBox) {
        const textEl = subPreviewBox.querySelector('.sub-coords-text');
        if (textEl) textEl.textContent = `X:${pX}% Y:${pY}% W:${pW}% H:${pH}%`;
    }
}

function setupResizableAndDraggableBox(box, onUpdate) {
    if (!box) return;
    
    if (box._resizeMouseDown) box.removeEventListener('mousedown', box._resizeMouseDown);
    // Xóa các handle cũ nếu có
    box.querySelectorAll('.box-resize-handle').forEach(h => h.remove());
    
    // Thêm 8 điểm neo co giãn
    const handlePositions = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
    handlePositions.forEach(pos => {
        const handle = document.createElement('div');
        handle.className = `box-resize-handle handle-${pos}`;
        handle.dataset.handle = pos;
        box.appendChild(handle);
    });

    let activeAction = null;
    let startMouseX = 0, startMouseY = 0;
    let initialBox = { left: 0, top: 0, width: 0, height: 0 };
    let initialVRect = null;

    function onMouseDown(e) {
        if (e.button !== 0) return;
        if (box === subPreviewBox && !isEditingSubBox) {
            showSubAdjustBox(true);
            e.stopPropagation();
            e.preventDefault();
            return;
        }
        if (e.target.closest('button') || e.target.tagName === 'BUTTON') return;
        const handle = e.target.closest('.box-resize-handle');
        if (handle) {
            activeAction = handle.dataset.handle;
        } else if (e.target === box || box.contains(e.target)) {
            activeAction = 'move';
        } else {
            return;
        }

        const wrapper = videoZoomWrapper || document.getElementById('videoZoomWrapper');
        if (!wrapper) return;
        
        initialVRect = getVideoContentRect();
        const zoom = getActiveZoomLevel();
        const wrapperRect = wrapper.getBoundingClientRect();
        const boxRect = box.getBoundingClientRect();

        initialBox = {
            left: (boxRect.left - wrapperRect.left) / zoom,
            top: (boxRect.top - wrapperRect.top) / zoom,
            width: boxRect.width / zoom,
            height: boxRect.height / zoom
        };

        // Lưu lại tỷ lệ phần trăm ban đầu của Box để khi KÉO DI CHUYỂN ('move') kích thước không bị sai lệch hoặc tự phóng to
        let startPW = Math.max(1, Math.round((initialBox.width / (initialVRect.videoW || 1)) * 1000) / 10);
        let startPH = Math.max(1, Math.round((initialBox.height / (initialVRect.videoH || 1)) * 1000) / 10);
        if (box === subPreviewBox && currentSubRegion) {
            startPW = currentSubRegion.w || startPW;
            startPH = currentSubRegion.h || startPH;
        } else if (box === blurAdjustBox && currentRegion) {
            startPW = currentRegion.w || startPW;
            startPH = currentRegion.h || startPH;
        } else if (box === reviewBlurAdjustBox && window.reviewBlurRegion) {
            startPW = window.reviewBlurRegion.w || startPW;
            startPH = window.reviewBlurRegion.h || startPH;
        } else if (box._overlayLayer) {
            startPW = box._overlayLayer.w_pct || startPW;
            startPH = box._overlayLayer.h_pct || startPH;
        }

        startMouseX = e.clientX;
        startMouseY = e.clientY;
        window.isDraggingAnyBox = true;

        let lastPX = Math.max(0, Math.min(100, Math.round(((initialBox.left - initialVRect.videoX) / (initialVRect.videoW || 1)) * 1000) / 10));
        let lastPY = Math.max(0, Math.min(100, Math.round(((initialBox.top - initialVRect.videoY) / (initialVRect.videoH || 1)) * 1000) / 10));
        let lastPW = startPW;
        let lastPH = startPH;

        e.stopPropagation();
        e.preventDefault();

        function onMouseMove(moveEvent) {
            if (!activeAction || !initialVRect) return;
            moveEvent.preventDefault();
            moveEvent.stopPropagation();

            const zoom = getActiveZoomLevel();
            const unscaledDx = (moveEvent.clientX - startMouseX) / zoom;
            const unscaledDy = (moveEvent.clientY - startMouseY) / zoom;

            let newLeft = initialBox.left;
            let newTop = initialBox.top;
            let newWidth = initialBox.width;
            let newHeight = initialBox.height;

            const minW = 16;
            const minH = 10;

            const boundLeft = initialVRect.videoX;
            const boundTop = initialVRect.videoY;
            const boundRight = initialVRect.videoX + initialVRect.videoW;
            const boundBottom = initialVRect.videoY + initialVRect.videoH;

            let pW, pH;
            if (activeAction === 'move') {
                newLeft = Math.max(boundLeft, Math.min(initialBox.left + unscaledDx, boundRight - newWidth));
                newTop = Math.max(boundTop, Math.min(initialBox.top + unscaledDy, boundBottom - newHeight));
                pW = startPW;
                pH = startPH;
            } else {
                if (activeAction.includes('e')) {
                    newWidth = Math.max(minW, Math.min(initialBox.width + unscaledDx, boundRight - initialBox.left));
                }
                if (activeAction.includes('s')) {
                    newHeight = Math.max(minH, Math.min(initialBox.height + unscaledDy, boundBottom - initialBox.top));
                }
                if (activeAction.includes('w')) {
                    const maxDx = initialBox.left - boundLeft;
                    const clampedDx = Math.max(-maxDx, Math.min(unscaledDx, initialBox.width - minW));
                    newLeft = initialBox.left + clampedDx;
                    newWidth = initialBox.width - clampedDx;
                }
                if (activeAction.includes('n')) {
                    const maxDy = initialBox.top - boundTop;
                    const clampedDy = Math.max(-maxDy, Math.min(unscaledDy, initialBox.height - minH));
                    newTop = initialBox.top + clampedDy;
                    newHeight = initialBox.height - clampedDy;
                }
            }

            box.style.bottom = 'auto';
            box.style.right = 'auto';
            box.style.left = `${(newLeft / initialVRect.wrapperW) * 100}%`;
            box.style.top = `${(newTop / initialVRect.wrapperH) * 100}%`;
            if (activeAction !== 'move') {
                box.style.width = `${(newWidth / initialVRect.wrapperW) * 100}%`;
                box.style.height = `${(newHeight / initialVRect.wrapperH) * 100}%`;
            }

            let pX = ((newLeft - initialVRect.videoX) / initialVRect.videoW) * 100;
            let pY = ((newTop - initialVRect.videoY) / initialVRect.videoH) * 100;
            pX = Math.max(0, Math.min(100, Math.round(pX * 10) / 10));
            pY = Math.max(0, Math.min(100, Math.round(pY * 10) / 10));

            if (activeAction !== 'move') {
                pW = (newWidth / initialVRect.videoW) * 100;
                pH = (newHeight / initialVRect.videoH) * 100;
                pW = Math.max(1, Math.min(100 - pX, Math.round(pW * 10) / 10));
                pH = Math.max(1, Math.min(100 - pY, Math.round(pH * 10) / 10));
            }

            lastPX = pX;
            lastPY = pY;
            lastPW = pW;
            lastPH = pH;

            if (onUpdate) {
                onUpdate(pX, pY, pW, pH, false);
            }
        }

        function onMouseUp() {
            if (!activeAction) return;
            activeAction = null;
            window.isDraggingAnyBox = false;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            if (onUpdate && lastPX !== undefined) {
                onUpdate(lastPX, lastPY, lastPW, lastPH, true);
            }
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    box.style.cursor = 'move';
    box.style.pointerEvents = 'auto';
    box.addEventListener('dragstart', (e) => e.preventDefault());
    box._resizeMouseDown = onMouseDown;
    box.addEventListener('mousedown', onMouseDown);
}

// Bắt sự kiện thanh trượt kích thước & vị trí khung phụ đề
['subBoxWidth', 'subBoxHeight', 'subBoxX', 'subBoxY'].forEach(id => {
    const slider = document.getElementById(id);
    if (!slider) return;
    slider.addEventListener('input', () => {
        const w = parseFloat(document.getElementById('subBoxWidth')?.value || 60);
        const h = parseFloat(document.getElementById('subBoxHeight')?.value || 9.5);
        const x = parseFloat(document.getElementById('subBoxX')?.value || 20);
        const y = parseFloat(document.getElementById('subBoxY')?.value || 81.5);
        
        syncSubRegionInputs(x, y, w, h);
        
        currentSubRegion = { x, y, w, h, customPos: true };
        
        if (subPreviewBox) {
            applyBoxPercentToWrapper(subPreviewBox, x, y, w, h);
            applySubStylesToElement(subPreviewBox);
        }
    });
});

const btnCenterSubBox = document.getElementById('btnCenterSubBox');
if (btnCenterSubBox) {
    btnCenterSubBox.addEventListener('click', () => {
        const w = parseFloat(document.getElementById('subBoxWidth')?.value || (currentSubRegion ? currentSubRegion.w : 60));
        const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
        if (!currentSubRegion) {
            currentSubRegion = { x: centeredX, y: 81.5, w: w, h: 9.5, customPos: true };
        } else {
            currentSubRegion.x = centeredX;
            currentSubRegion.customPos = true;
        }
        syncSubRegionInputs(centeredX, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
        if (subPreviewBox) {
            applyBoxPercentToWrapper(subPreviewBox, currentSubRegion.x, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
            applySubStylesToElement(subPreviewBox);
        }
    });
}

// ═════════════════════════════════════════════════════════════
// 📐 DEDICATED ON-SCREEN SUBTITLE BOX ADJUSTMENT ENGINE (8 HANDLES)
// ═════════════════════════════════════════════════════════════
let isEditingSubBox = false;
window.isEditingSubBox = false;

function showSubAdjustBox(show) {
    isEditingSubBox = (show !== undefined) ? !!show : !isEditingSubBox;
    window.isEditingSubBox = isEditingSubBox;

    const vContainer = document.getElementById('videoContainer') || videoContainer;
    const btnToggle = document.getElementById('btnToggleSubBox');
    const btnText = document.getElementById('btnToggleSubBoxText');

    if (vContainer) {
        vContainer.classList.toggle('is-editing-sub', isEditingSubBox);
    }

    if (!isEditingSubBox) {
        if (subPreviewBox) {
            subPreviewBox.classList.remove('is-editing');
            const badge = subPreviewBox.querySelector('.sub-adjust-badge');
            if (badge) badge.style.display = 'none';
        }
        if (btnToggle) {
            btnToggle.classList.remove('primary-cyan');
            btnToggle.classList.add('secondary');
        }
        if (btnText) btnText.textContent = 'Chỉnh khung phụ đề';
        if (typeof updateSubPreview === 'function') updateSubPreview();
        return;
    }

    // Đóng chế độ chỉnh mờ nếu đang mở để tránh chồng chéo thao tác
    if (typeof showBlurAdjustBox === 'function' && isEditingBlurBox) {
        showBlurAdjustBox(false);
    }
    if (typeof showReviewBlurAdjustBox === 'function' && isEditingReviewBlurBox) {
        showReviewBlurAdjustBox(false);
    }

    if (btnToggle) {
        btnToggle.classList.remove('secondary');
        btnToggle.classList.add('primary-cyan');
    }
    if (btnText) btnText.textContent = 'Hoàn tất chỉnh sub ✔️';

    // Đảm bảo Capcut transform box ẩn khi đang chỉnh sub
    document.querySelectorAll('.capcut-transform-box').forEach(el => {
        el.classList.remove('active');
        el.style.display = 'none';
    });

    const wrapper = document.getElementById('videoZoomWrapper') || vContainer;
    if (!wrapper) return;

    if (!subPreviewBox) {
        subPreviewBox = document.createElement('div');
        subPreviewBox.id = 'subPreviewBox';
        subPreviewBox.className = 'sub-preview-box';
        wrapper.appendChild(subPreviewBox);
    } else if (subPreviewBox.parentElement !== wrapper) {
        wrapper.appendChild(subPreviewBox);
    }

    subPreviewBox.classList.add('is-editing');

    if (!currentSubRegion) {
        const sX = parseFloat(document.getElementById('subBoxX')?.value || 20);
        const sY = parseFloat(document.getElementById('subBoxY')?.value || 81.5);
        const sW = parseFloat(document.getElementById('subBoxWidth')?.value || 60);
        const sH = parseFloat(document.getElementById('subBoxHeight')?.value || 9.5);
        currentSubRegion = { x: isNaN(sX) ? 20 : sX, y: isNaN(sY) ? 81.5 : sY, w: isNaN(sW) ? 60 : sW, h: isNaN(sH) ? 9.5 : sH, customPos: true };
    }

    // Gắn badge điều khiển nếu chưa có
    let badge = subPreviewBox.querySelector('.sub-adjust-badge');
    if (!badge) {
        badge = document.createElement('div');
        badge.className = 'sub-adjust-badge';
        badge.innerHTML = `
            <span>💬 Khung sub: <b class="sub-coords-text">X:${currentSubRegion.x}% Y:${currentSubRegion.y}% W:${currentSubRegion.w}% H:${currentSubRegion.h}%</b></span>
            <button type="button" class="btn-sub-center" title="Căn giữa màn hình">🎯 Giữa</button>
            <button type="button" class="btn-sub-close" title="Xong">✔️ Xong</button>
        `;
        subPreviewBox.appendChild(badge);

        badge.querySelector('.btn-sub-close')?.addEventListener('click', (e) => {
            e.stopPropagation();
            showSubAdjustBox(false);
        });

        badge.querySelector('.btn-sub-center')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const w = currentSubRegion ? currentSubRegion.w : 60;
            const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
            if (!currentSubRegion) currentSubRegion = { x: centeredX, y: 81.5, w: 60, h: 9.5, customPos: true };
            else {
                currentSubRegion.x = centeredX;
                currentSubRegion.customPos = true;
            }
            syncSubRegionInputs(centeredX, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
            applyBoxPercentToWrapper(subPreviewBox, currentSubRegion.x, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
            applySubStylesToElement(subPreviewBox);
        });
    }
    badge.style.display = 'flex';

    // Nội dung text phụ đề hiển thị bên trong khung
    let textSpan = subPreviewBox.querySelector('.sub-text-inner');
    if (!textSpan) {
        textSpan = document.createElement('span');
        textSpan.className = 'sub-text-inner';
        subPreviewBox.appendChild(textSpan);
    }
    const currentTime = videoPlayer ? videoPlayer.currentTime : 0;
    let activeSub = null;
    if (srtData && srtData.length > 0) {
        activeSub = srtData.find(s => currentTime >= s.startSeconds && currentTime <= s.endSeconds) || srtData[0];
    }
    textSpan.textContent = activeSub ? (activeSub.translation || activeSub.text) : 'Phụ đề xem trước';
    textSpan.style.whiteSpace = 'pre-line';

    // Thiết lập 8 điểm co giãn neo và kéo thả
    setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
        currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
        syncSubRegionInputs(newPx, newPy, newPw, newPh);
        applySubStylesToElement(subPreviewBox);
    });

    subPreviewBox.style.display = 'flex';
    applyBoxPercentToWrapper(subPreviewBox, currentSubRegion.x, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
    applySubStylesToElement(subPreviewBox);
    syncSubRegionInputs(currentSubRegion.x, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
}

document.getElementById('btnToggleSubBox')?.addEventListener('click', () => showSubAdjustBox());

// ═════════════════════════════════════════════════════════════
// 📐 DEDICATED ON-SCREEN BLUR REGION ADJUSTMENT ENGINE (8 HANDLES)
// ═════════════════════════════════════════════════════════════
let isEditingBlurBox = false;
let blurAdjustBox = null;
let isEditingReviewBlurBox = false;
let reviewBlurAdjustBox = null;
window.reviewBlurRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };

function syncBlurRegionInputs(pX, pY, pW, pH) {
    const elX = document.getElementById('blurXPos');
    const elY = document.getElementById('blurYPos');
    const elW = document.getElementById('blurWidth');
    const elH = document.getElementById('blurHeight');
    const valX = document.getElementById('blurXPosVal');
    const valY = document.getElementById('blurYPosVal');
    const valW = document.getElementById('blurWidthVal');
    const valH = document.getElementById('blurHeightVal');

    if (elX && pX !== undefined) { elX.value = pX; if (valX) valX.textContent = `${pX}%`; }
    if (elY && pY !== undefined) { elY.value = pY; if (valY) valY.textContent = `${pY}%`; }
    if (elW && pW !== undefined) { elW.value = pW; if (valW) valW.textContent = `${pW}%`; }
    if (elH && pH !== undefined) { elH.value = pH; if (valH) valH.textContent = `${pH}%`; }

    if (blurAdjustBox) {
        const textEl = blurAdjustBox.querySelector('.blur-coords-text');
        if (textEl) textEl.textContent = `X:${pX}% Y:${pY}% W:${pW}% H:${pH}%`;
    }
}

function syncReviewBlurRegionInputs(pX, pY, pW, pH) {
    const elX = document.getElementById('reviewTabBlurXPos');
    const elY = document.getElementById('reviewTabBlurYPos');
    const elW = document.getElementById('reviewTabBlurWidth');
    const elH = document.getElementById('reviewTabBlurHeight');
    const valX = document.getElementById('reviewTabBlurXPosVal');
    const valY = document.getElementById('reviewTabBlurYPosVal');
    const valW = document.getElementById('reviewTabBlurWidthVal');
    const valH = document.getElementById('reviewTabBlurHeightVal');

    if (elX && pX !== undefined) { elX.value = pX; if (valX) valX.textContent = `${pX}%`; }
    if (elY && pY !== undefined) { elY.value = pY; if (valY) valY.textContent = `${pY}%`; }
    if (elW && pW !== undefined) { elW.value = pW; if (valW) valW.textContent = `${pW}%`; }
    if (elH && pH !== undefined) { elH.value = pH; if (valH) valH.textContent = `${pH}%`; }

    if (reviewBlurAdjustBox) {
        const textEl = reviewBlurAdjustBox.querySelector('.blur-coords-text');
        if (textEl) textEl.textContent = `X:${pX}% Y:${pY}% W:${pW}% H:${pH}%`;
    }
}

function showBlurAdjustBox(show) {
    isEditingBlurBox = (show !== undefined) ? !!show : !isEditingBlurBox;
    window.isEditingBlurBox = isEditingBlurBox;

    const vContainer = document.getElementById('videoContainer') || videoContainer;
    const btnToggle = document.getElementById('btnToggleBlurBox');
    const btnText = document.getElementById('btnToggleBlurBoxText');

    if (vContainer) {
        vContainer.classList.toggle('is-editing-blur', isEditingBlurBox);
    }

    // Đóng chế độ chỉnh sub nếu đang mở để tránh chồng chéo thao tác
    if (isEditingBlurBox && typeof showSubAdjustBox === 'function' && isEditingSubBox) {
        showSubAdjustBox(false);
    }

    if (!isEditingBlurBox) {
        if (blurAdjustBox) blurAdjustBox.style.display = 'none';
        if (btnToggle) {
            btnToggle.classList.remove('primary-cyan');
            btnToggle.classList.add('secondary');
        }
        if (btnText) btnText.textContent = 'Chỉnh vùng làm mờ';
        updateDynamicBlurOverlayVisibility();
        return;
    }

    if (btnToggle) {
        btnToggle.classList.remove('secondary');
        btnToggle.classList.add('primary-cyan');
    }
    if (btnText) btnText.textContent = 'Hoàn tất chỉnh mờ ✔️';

    // Đảm bảo Capcut transform box ẩn khi đang chỉnh mờ
    document.querySelectorAll('.capcut-transform-box').forEach(el => {
        el.classList.remove('active');
        el.style.display = 'none';
    });

    const wrapper = document.getElementById('videoZoomWrapper') || vContainer;
    if (!wrapper) return;

    if (!blurAdjustBox) {
        blurAdjustBox = document.createElement('div');
        blurAdjustBox.id = 'blurAdjustBox';
        blurAdjustBox.className = 'blur-adjust-box';
        blurAdjustBox.innerHTML = `
            <div class="blur-adjust-badge">
                <span>📐 Vùng mờ: <b class="blur-coords-text">X:20% Y:81.5%</b></span>
                <button type="button" class="btn-blur-center" title="Căn giữa màn hình">🎯 Giữa</button>
                <button type="button" class="btn-blur-close" title="Xong">✔️ Xong</button>
            </div>
        `;
        wrapper.appendChild(blurAdjustBox);

        blurAdjustBox.querySelector('.btn-blur-close')?.addEventListener('click', (e) => {
            e.stopPropagation();
            showBlurAdjustBox(false);
        });

        blurAdjustBox.querySelector('.btn-blur-center')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const w = currentRegion ? currentRegion.w : 60;
            const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
            if (!currentRegion) currentRegion = { x: centeredX, y: 81.5, w: 60, h: 9.5 };
            else currentRegion.x = centeredX;
            syncBlurRegionInputs(centeredX, currentRegion.y, currentRegion.w, currentRegion.h);
            applyBoxPercentToWrapper(blurAdjustBox, currentRegion.x, currentRegion.y, currentRegion.w, currentRegion.h);
            updateDynamicBlurOverlayVisibility();
        });

        setupResizableAndDraggableBox(blurAdjustBox, (newPx, newPy, newPw, newPh) => {
            setManualBlurRegion();
            currentRegion = { x: newPx, y: newPy, w: newPw, h: newPh };
            syncBlurRegionInputs(newPx, newPy, newPw, newPh);
            updateDynamicBlurOverlayVisibility();
        });
    }

    if (!currentRegion) {
        currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };
    }
    const sX = parseFloat(document.getElementById('blurXPos')?.value);
    const sY = parseFloat(document.getElementById('blurYPos')?.value);
    const sW = parseFloat(document.getElementById('blurWidth')?.value);
    const sH = parseFloat(document.getElementById('blurHeight')?.value);
    if (!isNaN(sX)) currentRegion.x = sX;
    if (!isNaN(sY)) currentRegion.y = sY;
    if (!isNaN(sW)) currentRegion.w = sW;
    if (!isNaN(sH)) currentRegion.h = sH;

    blurAdjustBox.style.display = 'flex';
    applyBoxPercentToWrapper(blurAdjustBox, currentRegion.x, currentRegion.y, currentRegion.w, currentRegion.h);
    syncBlurRegionInputs(currentRegion.x, currentRegion.y, currentRegion.w, currentRegion.h);
    updateDynamicBlurOverlayVisibility();
}

function showReviewBlurAdjustBox(show) {
    isEditingReviewBlurBox = (show !== undefined) ? !!show : !isEditingReviewBlurBox;
    window.isEditingReviewBlurBox = isEditingReviewBlurBox;

    const vContainer = document.getElementById('reviewVideoContainer');
    const btnToggle = document.getElementById('reviewTabBtnToggleBlurBox');
    const btnText = document.getElementById('reviewTabBtnToggleBlurBoxText');

    if (vContainer) {
        vContainer.classList.toggle('is-editing-blur', isEditingReviewBlurBox);
    }

    // Đóng chế độ chỉnh sub nếu đang mở để tránh chồng chéo thao tác
    if (isEditingReviewBlurBox && typeof showSubAdjustBox === 'function' && isEditingSubBox) {
        showSubAdjustBox(false);
    }

    if (!isEditingReviewBlurBox) {
        if (reviewBlurAdjustBox) reviewBlurAdjustBox.style.display = 'none';
        if (btnToggle) {
            btnToggle.classList.remove('primary-cyan');
            btnToggle.classList.add('secondary');
        }
        if (btnText) btnText.textContent = 'Chỉnh vùng làm mờ';
        return;
    }

    if (btnToggle) {
        btnToggle.classList.remove('secondary');
        btnToggle.classList.add('primary-cyan');
    }
    if (btnText) btnText.textContent = 'Hoàn tất chỉnh mờ ✔️';

    const wrapper = document.getElementById('reviewVideoContainer');
    if (!wrapper) return;

    if (!window.reviewBlurRegion) {
        window.reviewBlurRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };
    }

    const sX = parseFloat(document.getElementById('reviewTabBlurXPos')?.value);
    const sY = parseFloat(document.getElementById('reviewTabBlurYPos')?.value);
    const sW = parseFloat(document.getElementById('reviewTabBlurWidth')?.value);
    const sH = parseFloat(document.getElementById('reviewTabBlurHeight')?.value);
    if (!isNaN(sX)) window.reviewBlurRegion.x = sX;
    if (!isNaN(sY)) window.reviewBlurRegion.y = sY;
    if (!isNaN(sW)) window.reviewBlurRegion.w = sW;
    if (!isNaN(sH)) window.reviewBlurRegion.h = sH;

    if (!reviewBlurAdjustBox) {
        reviewBlurAdjustBox = document.createElement('div');
        reviewBlurAdjustBox.id = 'reviewBlurAdjustBox';
        reviewBlurAdjustBox.className = 'blur-adjust-box';
        reviewBlurAdjustBox.innerHTML = `
            <div class="blur-adjust-badge">
                <span>📐 Vùng mờ Review: <b class="blur-coords-text">X:20% Y:81.5%</b></span>
                <button type="button" class="btn-blur-center" title="Căn giữa màn hình">🎯 Giữa</button>
                <button type="button" class="btn-blur-close" title="Xong">✔️ Xong</button>
            </div>
        `;
        wrapper.appendChild(reviewBlurAdjustBox);

        reviewBlurAdjustBox.querySelector('.btn-blur-close')?.addEventListener('click', (e) => {
            e.stopPropagation();
            showReviewBlurAdjustBox(false);
        });

        reviewBlurAdjustBox.querySelector('.btn-blur-center')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const w = window.reviewBlurRegion ? window.reviewBlurRegion.w : 60;
            const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
            window.reviewBlurRegion.x = centeredX;
            syncReviewBlurRegionInputs(centeredX, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
            applyBoxPercentToWrapper(reviewBlurAdjustBox, window.reviewBlurRegion.x, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
            if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
        });

        setupResizableAndDraggableBox(reviewBlurAdjustBox, (newPx, newPy, newPw, newPh) => {
            window.reviewBlurRegion = { x: newPx, y: newPy, w: newPw, h: newPh };
            syncReviewBlurRegionInputs(newPx, newPy, newPw, newPh);
            if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
        });
    }

    reviewBlurAdjustBox.style.display = 'flex';
    applyBoxPercentToWrapper(reviewBlurAdjustBox, window.reviewBlurRegion.x, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
    syncReviewBlurRegionInputs(window.reviewBlurRegion.x, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
    if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
}

// Gán sự kiện cho các thanh trượt và nút chỉnh sửa vùng làm mờ Editor
['blurXPos', 'blurYPos', 'blurWidth', 'blurHeight'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
        const x = parseFloat(document.getElementById('blurXPos')?.value ?? 20);
        const y = parseFloat(document.getElementById('blurYPos')?.value ?? 81.5);
        const w = parseFloat(document.getElementById('blurWidth')?.value ?? 60);
        const h = parseFloat(document.getElementById('blurHeight')?.value ?? 9.5);
        currentRegion = { x, y, w, h };
        setManualBlurRegion();
        syncBlurRegionInputs(x, y, w, h);
        if (blurAdjustBox && isEditingBlurBox) {
            applyBoxPercentToWrapper(blurAdjustBox, x, y, w, h);
        }
        updateDynamicBlurOverlayVisibility();
    });
});

document.getElementById('btnToggleBlurBox')?.addEventListener('click', () => showBlurAdjustBox());
document.getElementById('btnDrawBlurRegion')?.addEventListener('click', () => startDrawMode('blur'));
document.getElementById('btnCenterBlurBox')?.addEventListener('click', () => {
    setManualBlurRegion();
    const w = currentRegion ? currentRegion.w : 60;
    const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
    if (!currentRegion) currentRegion = { x: centeredX, y: 81.5, w: 60, h: 9.5 };
    else currentRegion.x = centeredX;
    syncBlurRegionInputs(centeredX, currentRegion.y, currentRegion.w, currentRegion.h);
    if (blurAdjustBox) applyBoxPercentToWrapper(blurAdjustBox, currentRegion.x, currentRegion.y, currentRegion.w, currentRegion.h);
    updateDynamicBlurOverlayVisibility();
});

// Quét câu phụ đề có chiều rộng lớn nhất (Fixed Blur Max Width)
function scanMaxSubtitleWidth(showNotification = true) {
    if (!Array.isArray(srtData) || srtData.length === 0) {
        if (showNotification) showToast('Chưa có danh sách phụ đề để quét câu rộng nhất!', 'warning');
        return null;
    }
    let maxW = 0;
    let bestSub = null;
    srtData.forEach((sub, idx) => {
        let w = 0;
        if (sub.aiBox && typeof sub.aiBox.w_pct === 'number' && sub.aiBox.w_pct > 0) {
            w = sub.aiBox.w_pct;
        } else {
            const txt = sub.original_text || sub.raw_text || sub.text || sub.translation || '';
            if (txt) {
                w = (typeof calculateSubtitleWidthPercent === 'function') ? calculateSubtitleWidthPercent(txt) : (txt.length * 1.8);
            }
        }
        if (w > maxW) {
            maxW = w;
            bestSub = { sub, idx: idx + 1, w };
        }
    });

    if (maxW <= 0) maxW = 55;
    // Thêm đệm an toàn 5% để che kín hai đầu câu chữ
    const finalW = Math.min(98, Math.max(15, Math.ceil(maxW + 5)));
    const finalX = Math.max(0, Math.round(((100 - finalW) / 2) * 10) / 10);
    const curH = parseFloat(document.getElementById('blurHeight')?.value) || 9.5;
    const curY = parseFloat(document.getElementById('blurYPos')?.value) || 81.5;

    syncBlurRegionInputs(finalX, curY, finalW, curH);
    currentRegion = { x: finalX, y: curY, w: finalW, h: curH };
    if (blurAdjustBox) {
        applyBoxPercentToWrapper(blurAdjustBox, finalX, curY, finalW, curH);
    }
    updateDynamicBlurOverlayVisibility();

    if (showNotification && bestSub) {
        const previewTxt = (bestSub.sub.text || bestSub.sub.original_text || bestSub.sub.translation || '').substring(0, 30);
        showToast(`🎯 Đã quét câu dài nhất (#${bestSub.idx}: "${previewTxt}..."): Tự động đặt Rộng: ${finalW}%, Căn giữa X: ${finalX}%. Bạn có thể kéo chỉnh thêm thủ công.`, 'info');
    }
    return { w: finalW, x: finalX, h: curH, y: curY };
}
window.scanMaxSubtitleWidth = scanMaxSubtitleWidth;

document.getElementById('btnScanMaxWidthBlur')?.addEventListener('click', () => {
    scanMaxSubtitleWidth(true);
});

// Chuyển đổi chế độ làm mờ Cố định vs Động
document.querySelectorAll('input[name="blurModeRadio"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        const isFixed = (e.target.value === 'fixed');
        const lblFixed = document.getElementById('lblBlurModeFixed');
        const lblDyn = document.getElementById('lblBlurModeDynamic');
        if (lblFixed && lblDyn) {
            if (isFixed) {
                lblFixed.style.background = 'rgba(14, 165, 233, 0.2)';
                lblFixed.style.border = '1px solid #0ea5e9';
                lblFixed.style.color = '#fff';
                lblDyn.style.background = 'transparent';
                lblDyn.style.border = 'none';
                lblDyn.style.color = '#94a3b8';
                // Tự động quét câu rộng nhất
                scanMaxSubtitleWidth(false);
            } else {
                lblDyn.style.background = 'rgba(14, 165, 233, 0.2)';
                lblDyn.style.border = '1px solid #0ea5e9';
                lblDyn.style.color = '#fff';
                lblFixed.style.background = 'transparent';
                lblFixed.style.border = 'none';
                lblFixed.style.color = '#94a3b8';
            }
        }
        updateDynamicBlurOverlayVisibility();
    });
});

// Gán sự kiện cho các thanh trượt và nút chỉnh sửa vùng làm mờ Review Phim
['reviewTabBlurXPos', 'reviewTabBlurYPos', 'reviewTabBlurWidth', 'reviewTabBlurHeight'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
        const x = parseFloat(document.getElementById('reviewTabBlurXPos')?.value ?? 20);
        const y = parseFloat(document.getElementById('reviewTabBlurYPos')?.value ?? 81.5);
        const w = parseFloat(document.getElementById('reviewTabBlurWidth')?.value ?? 60);
        const h = parseFloat(document.getElementById('reviewTabBlurHeight')?.value ?? 9.5);
        window.reviewBlurRegion = { x, y, w, h };
        syncReviewBlurRegionInputs(x, y, w, h);
        if (reviewBlurAdjustBox && isEditingReviewBlurBox) {
            applyBoxPercentToWrapper(reviewBlurAdjustBox, x, y, w, h);
        }
        if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
    });
});

document.getElementById('reviewTabBtnToggleBlurBox')?.addEventListener('click', () => showReviewBlurAdjustBox());
document.getElementById('reviewTabBtnDrawBlurRegion')?.addEventListener('click', () => startDrawMode('review_blur'));
document.getElementById('reviewTabBtnCenterBlurBox')?.addEventListener('click', () => {
    const w = window.reviewBlurRegion ? window.reviewBlurRegion.w : 60;
    const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
    if (!window.reviewBlurRegion) window.reviewBlurRegion = { x: centeredX, y: 81.5, w: 60, h: 9.5 };
    else window.reviewBlurRegion.x = centeredX;
    syncReviewBlurRegionInputs(centeredX, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
    if (reviewBlurAdjustBox) applyBoxPercentToWrapper(reviewBlurAdjustBox, window.reviewBlurRegion.x, window.reviewBlurRegion.y, window.reviewBlurRegion.w, window.reviewBlurRegion.h);
    if (window.triggerReviewDynamicBlurSync) window.triggerReviewDynamicBlurSync();
});

// ==========================================
// Subtitle Style Preview Logic
// ==========================================
// ==========================================
// Subtitle Style Studio Logic
// ==========================================
let isSubBold = false;
let isSubItalic = false;
let isSubUppercase = false;
let subTextAlign = 'center';

function setSubtitlePreviewText(text) {
    if (!subPreviewBox) return;
    let span = subPreviewBox.querySelector('.sub-text-inner');
    if (!span) {
        span = document.createElement('span');
        span.className = 'sub-text-inner';
        subPreviewBox.appendChild(span);
    }
    span.textContent = text;
    span.style.whiteSpace = 'pre-line';
}

function applySubStylesToElement(el) {
    if (!el) return;
    
    const font = document.getElementById('subFont')?.value || 'Montserrat';
    const color = document.getElementById('subColorPicker')?.value || '#ffffff';
    const outlineColor = document.getElementById('subOutlineColorPicker')?.value || '#000000';
    const shadowColor = document.getElementById('subShadowColorPicker')?.value || '#000000';
    const size = parseInt(document.getElementById('subSize')?.value) || 24;
    const rawOutlineVal = parseInt(document.getElementById('subOutline')?.value);
    const outline = Number.isFinite(rawOutlineVal) ? rawOutlineVal : 1;
    const shadowOffset = parseInt(document.getElementById('subShadowOffset')?.value) || 0;
    const marginY = parseInt(document.getElementById('subMarginY')?.value) || 30;
    const bgStyle = document.getElementById('subBgStyle')?.value || 'none';
    
    let renderedFontSize = size;
    let renderedOutline = outline;
    if (el.id !== 'subLivePreviewBox') {
        const vRect = (typeof getVideoContentRect === 'function') ? getVideoContentRect() : null;
        const contentScale = (vRect && vRect.videoH) ? (vRect.videoH / 720.0) : 1.0;
        renderedFontSize = Math.max(8, Math.round(size * contentScale));
        if (outline > 0) {
            renderedOutline = Math.max(1, Math.round(outline * contentScale));
        }
    }

    el.style.display = 'flex';
    el.style.justifyContent = subTextAlign === 'left' ? 'flex-start' : (subTextAlign === 'right' ? 'flex-end' : 'center');
    el.style.alignItems = 'center';
    el.style.textAlign = subTextAlign;
    el.style.fontFamily = font;
    el.style.fontSize = `${renderedFontSize}px`;
    el.style.color = color;
    el.style.fontWeight = isSubBold ? 'bold' : 'normal';
    el.style.fontStyle = isSubItalic ? 'italic' : 'normal';
    el.style.textTransform = isSubUppercase ? 'uppercase' : 'none';
    const textSpan = el.querySelector('.sub-text-inner');
    if (textSpan) {
        textSpan.style.transform = 'none';
        textSpan.style.width = '100%';
        textSpan.style.maxWidth = '100%';
        textSpan.style.boxSizing = 'border-box';
        textSpan.style.wordBreak = 'break-word';
        textSpan.style.whiteSpace = 'normal';
        textSpan.style.flexShrink = '0';
        textSpan.style.maxHeight = 'none';
        textSpan.style.overflow = 'visible';
        textSpan.style.textAlign = subTextAlign;
    }
    
    // Position handling (Only for on-video overlay, not live preview box):
    if (el.id !== 'subLivePreviewBox') {
        if (currentSubRegion && currentSubRegion.customPos) {
            applyBoxPercentToWrapper(el, currentSubRegion.x, currentSubRegion.y, currentSubRegion.w, currentSubRegion.h);
        } else {
            const vRect = getVideoContentRect();
            const defX = 10, defW = 80, defH = 9.5;
            const defY = Math.max(0, 100 - defH - (marginY / (vRect.videoH || 450)) * 100);
            applyBoxPercentToWrapper(el, defX, defY, defW, defH, vRect);
        }
    }
    
    // Text outline & drop shadow combination
    let shadows = [];
    if (renderedOutline > 0) {
        shadows.push(`-${renderedOutline}px -${renderedOutline}px 0 ${outlineColor}`);
        shadows.push(`${renderedOutline}px -${renderedOutline}px 0 ${outlineColor}`);
        shadows.push(`-${renderedOutline}px ${renderedOutline}px 0 ${outlineColor}`);
        shadows.push(`${renderedOutline}px ${renderedOutline}px 0 ${outlineColor}`);
    }
    if (shadowOffset > 0) {
        shadows.push(`${shadowOffset}px ${shadowOffset}px ${shadowOffset * 2}px ${shadowColor}`);
    }
    el.style.textShadow = shadows.length > 0 ? shadows.join(', ') : 'none';
    
    // Background style
    if (bgStyle === 'none') {
        el.style.backgroundColor = 'transparent';
        el.style.backdropFilter = 'none';
        el.style.webkitBackdropFilter = 'none';
        el.style.borderRadius = '0px';
        el.style.padding = el.id === 'subLivePreviewBox' ? '4px' : '0px';
    } else if (bgStyle === 'color') {
        const bgColor = document.getElementById('subBgColorPicker')?.value || '#000000';
        const opacity = parseInt(document.getElementById('subBgOpacity')?.value) || 50;
        
        let r = parseInt(bgColor.slice(1, 3), 16) || 0,
            g = parseInt(bgColor.slice(3, 5), 16) || 0,
            b = parseInt(bgColor.slice(5, 7), 16) || 0;
            
        el.style.backgroundColor = `rgba(${r}, ${g}, ${b}, ${opacity / 100})`;
        el.style.backdropFilter = 'none';
        el.style.webkitBackdropFilter = 'none';
        el.style.borderRadius = '6px';
        el.style.padding = '4px 12px';
    } else if (bgStyle === 'blur') {
        const blurAmt = parseInt(document.getElementById('subBgBlur')?.value) || 15;
        el.style.backgroundColor = 'rgba(0,0,0,0.3)';
        el.style.backdropFilter = `blur(${blurAmt}px)`;
        el.style.webkitBackdropFilter = `blur(${blurAmt}px)`;
        el.style.borderRadius = '6px';
        el.style.padding = '4px 12px';
    }
}

function updateSubPreview() {
    const isSubEnabled = document.getElementById('subtitlesEnabled')?.checked ?? true;

    // 1. Update Live Preview Box inside the card
    const liveBox = document.getElementById('subLivePreviewBox');
    if (liveBox) {
        if (!isSubEnabled) {
            liveBox.textContent = 'Phụ đề đang TẮT (Video xuất ra sẽ không có phụ đề) 🚫';
            liveBox.style.opacity = '0.45';
            liveBox.style.fontStyle = 'italic';
            liveBox.style.color = '#94a3b8';
            liveBox.style.textShadow = 'none';
        } else {
            liveBox.style.opacity = '1';
            liveBox.style.fontStyle = 'normal';
            applySubStylesToElement(liveBox);
            liveBox.textContent = 'Phụ đề mẫu hiển thị trực tiếp ✨';
        }
    }

    // 2. Update Overlay on Video Player
    const wrapper = document.getElementById('videoZoomWrapper') || document.querySelector('.video-container');
    if (!subPreviewBox && wrapper) {
        subPreviewBox = document.createElement('div');
        subPreviewBox.className = 'sub-preview-box';
        wrapper.appendChild(subPreviewBox);
        if (!currentSubRegion) {
            currentSubRegion = { x: 20, y: 81.5, w: 60, h: 9.5, customPos: true };
        }
        
        setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
            currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
            syncSubRegionInputs(newPx, newPy, newPw, newPh);
        });
    } else if (subPreviewBox && wrapper && subPreviewBox.parentElement !== wrapper) {
        wrapper.appendChild(subPreviewBox);
    }
    
    if (subPreviewBox) {
        if (!isSubEnabled) {
            subPreviewBox.style.display = 'none';
            return;
        }

        applySubStylesToElement(subPreviewBox);
        
        const isEditedMode = btnPreviewEdited && btnPreviewEdited.classList.contains('active');
        const overlay = document.getElementById('videoOverlay');
        const isDrawingMode = overlay && overlay.style.display === 'block' && typeof drawMode !== 'undefined' && drawMode === 'sub';
        
        if (isEditedMode || isDrawingMode || isEditingSubBox) {
            const currentTime = videoPlayer ? videoPlayer.currentTime : 0;
            let activeSub = null;
            if (srtData && srtData.length > 0) {
                activeSub = srtData.find(s => currentTime >= s.startSeconds && currentTime <= s.endSeconds) || srtData[0];
            }
            const displayText = activeSub ? (activeSub.translation || activeSub.text) : 'Phụ đề xem trước';
            
            let textSpan = subPreviewBox.querySelector('.sub-text-inner');
            if (!textSpan) {
                textSpan = document.createElement('span');
                textSpan.className = 'sub-text-inner';
                subPreviewBox.appendChild(textSpan);
            }
            textSpan.textContent = displayText;
            textSpan.style.whiteSpace = 'pre-line';
            
            // Đảm bảo các điểm neo luôn có mặt
            if (!subPreviewBox.querySelector('.box-resize-handle')) {
                setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
                    currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
                    syncSubRegionInputs(newPx, newPy, newPw, newPh);
                    applySubStylesToElement(subPreviewBox);
                });
            }
            
            subPreviewBox.style.display = 'flex';
        } else {
            subPreviewBox.style.display = 'none';
        }
    }
}

// Sub-tabs navigation
const tabSubTypography = document.getElementById('tabSubTypography');
const tabSubColors = document.getElementById('tabSubColors');
const tabSubPosition = document.getElementById('tabSubPosition');
const subTabContentTypography = document.getElementById('subTabContentTypography');
const subTabContentColors = document.getElementById('subTabContentColors');
const subTabContentPosition = document.getElementById('subTabContentPosition');

function switchSubTab(activeTab, activeContent) {
    [tabSubTypography, tabSubColors, tabSubPosition].forEach(t => t?.classList.remove('active'));
    [subTabContentTypography, subTabContentColors, subTabContentPosition].forEach(c => c?.classList.remove('active'));
    activeTab?.classList.add('active');
    activeContent?.classList.add('active');
}

if (tabSubTypography && tabSubColors && tabSubPosition) {
    tabSubTypography.addEventListener('click', () => switchSubTab(tabSubTypography, subTabContentTypography));
    tabSubColors.addEventListener('click', () => switchSubTab(tabSubColors, subTabContentColors));
    tabSubPosition.addEventListener('click', () => switchSubTab(tabSubPosition, subTabContentPosition));
}

// Subtitle Style Presets
function applyPresetStyle(preset) {
    const subFont = document.getElementById('subFont');
    const subColorPicker = document.getElementById('subColorPicker');
    const subColorText = document.getElementById('subColorText');
    const subOutlineColorPicker = document.getElementById('subOutlineColorPicker');
    const subOutlineColorText = document.getElementById('subOutlineColorText');
    const subOutline = document.getElementById('subOutline');
    const subOutlineVal = document.getElementById('subOutlineVal');
    const subShadowColorPicker = document.getElementById('subShadowColorPicker');
    const subShadowColorText = document.getElementById('subShadowColorText');
    const subShadowOffset = document.getElementById('subShadowOffset');
    const subShadowOffsetVal = document.getElementById('subShadowOffsetVal');
    const subBgStyle = document.getElementById('subBgStyle');
    const subBgColorPicker = document.getElementById('subBgColorPicker');
    const subBgColorText = document.getElementById('subBgColorText');
    const subBgOpacity = document.getElementById('subBgOpacity');
    const subBgOpacityVal = document.getElementById('subBgOpacityVal');

    const subBtnBold = document.getElementById('subBtnBold');
    const subBtnUppercase = document.getElementById('subBtnUppercase');
    const subBtnItalic = document.getElementById('subBtnItalic');

    if (preset === 'yellow') {
        if (subFont) subFont.value = 'Montserrat';
        if (subColorPicker) { subColorPicker.value = '#fde047'; subColorText.value = '#fde047'; }
        if (subOutlineColorPicker) { subOutlineColorPicker.value = '#000000'; subOutlineColorText.value = '#000000'; }
        if (subOutline) { subOutline.value = '3'; if(subOutlineVal) subOutlineVal.textContent = '3px'; }
        if (subShadowOffset) { subShadowOffset.value = '3'; if(subShadowOffsetVal) subShadowOffsetVal.textContent = '3px'; }
        if (subShadowColorPicker) { subShadowColorPicker.value = '#000000'; subShadowColorText.value = '#000000'; }
        if (subBgStyle) { subBgStyle.value = 'none'; subBgStyle.dispatchEvent(new Event('change')); }
        isSubBold = true; subBtnBold?.classList.add('active');
        isSubUppercase = false; subBtnUppercase?.classList.remove('active');
        isSubItalic = false; subBtnItalic?.classList.remove('active');
    } else if (preset === 'white') {
        if (subFont) subFont.value = 'Montserrat';
        if (subColorPicker) { subColorPicker.value = '#ffffff'; subColorText.value = '#ffffff'; }
        if (subOutlineColorPicker) { subOutlineColorPicker.value = '#000000'; subOutlineColorText.value = '#000000'; }
        if (subOutline) { subOutline.value = '2'; if(subOutlineVal) subOutlineVal.textContent = '2px'; }
        if (subShadowOffset) { subShadowOffset.value = '2'; if(subShadowOffsetVal) subShadowOffsetVal.textContent = '2px'; }
        if (subShadowColorPicker) { subShadowColorPicker.value = '#000000'; subShadowColorText.value = '#000000'; }
        if (subBgStyle) { subBgStyle.value = 'none'; subBgStyle.dispatchEvent(new Event('change')); }
        isSubBold = true; subBtnBold?.classList.add('active');
        isSubUppercase = false; subBtnUppercase?.classList.remove('active');
        isSubItalic = false; subBtnItalic?.classList.remove('active');
    } else if (preset === 'tiktok') {
        if (subFont) subFont.value = 'Anton';
        if (subColorPicker) { subColorPicker.value = '#ffffff'; subColorText.value = '#ffffff'; }
        if (subOutlineColorPicker) { subOutlineColorPicker.value = '#000000'; subOutlineColorText.value = '#000000'; }
        if (subOutline) { subOutline.value = '0'; if(subOutlineVal) subOutlineVal.textContent = '0px'; }
        if (subShadowOffset) { subShadowOffset.value = '0'; if(subShadowOffsetVal) subShadowOffsetVal.textContent = '0px'; }
        if (subBgStyle) { subBgStyle.value = 'color'; subBgStyle.dispatchEvent(new Event('change')); }
        if (subBgColorPicker) { subBgColorPicker.value = '#000000'; subBgColorText.value = '#000000'; }
        if (subBgOpacity) { subBgOpacity.value = '75'; if(subBgOpacityVal) subBgOpacityVal.textContent = '75%'; }
        isSubBold = true; subBtnBold?.classList.add('active');
        isSubUppercase = true; subBtnUppercase?.classList.add('active');
        isSubItalic = false; subBtnItalic?.classList.remove('active');
    } else if (preset === 'neon') {
        if (subFont) subFont.value = "'Be Vietnam Pro'";
        if (subColorPicker) { subColorPicker.value = '#38bdf8'; subColorText.value = '#38bdf8'; }
        if (subOutlineColorPicker) { subOutlineColorPicker.value = '#0369a1'; subOutlineColorText.value = '#0369a1'; }
        if (subOutline) { subOutline.value = '2'; if(subOutlineVal) subOutlineVal.textContent = '2px'; }
        if (subShadowOffset) { subShadowOffset.value = '6'; if(subShadowOffsetVal) subShadowOffsetVal.textContent = '6px'; }
        if (subShadowColorPicker) { subShadowColorPicker.value = '#00f0ff'; subShadowColorText.value = '#00f0ff'; }
        if (subBgStyle) { subBgStyle.value = 'none'; subBgStyle.dispatchEvent(new Event('change')); }
        isSubBold = true; subBtnBold?.classList.add('active');
        isSubUppercase = false; subBtnUppercase?.classList.remove('active');
        isSubItalic = false; subBtnItalic?.classList.remove('active');
    } else if (preset === 'tag') {
        if (subFont) subFont.value = 'Inter';
        if (subColorPicker) { subColorPicker.value = '#f8fafc'; subColorText.value = '#f8fafc'; }
        if (subOutlineColorPicker) { subOutlineColorPicker.value = '#000000'; subOutlineColorText.value = '#000000'; }
        if (subOutline) { subOutline.value = '0'; if(subOutlineVal) subOutlineVal.textContent = '0px'; }
        if (subShadowOffset) { subShadowOffset.value = '0'; if(subShadowOffsetVal) subShadowOffsetVal.textContent = '0px'; }
        if (subBgStyle) { subBgStyle.value = 'color'; subBgStyle.dispatchEvent(new Event('change')); }
        if (subBgColorPicker) { subBgColorPicker.value = '#0f172a'; subBgColorText.value = '#0f172a'; }
        if (subBgOpacity) { subBgOpacity.value = '85'; if(subBgOpacityVal) subBgOpacityVal.textContent = '85%'; }
        isSubBold = true; subBtnBold?.classList.add('active');
        isSubUppercase = false; subBtnUppercase?.classList.remove('active');
        isSubItalic = false; subBtnItalic?.classList.remove('active');
    }

    updateSubPreview();
}

document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyPresetStyle(btn.getAttribute('data-preset'));
    });
});

// Format Toggle Buttons
const subBtnBold = document.getElementById('subBtnBold');
if (subBtnBold) {
    subBtnBold.addEventListener('click', () => {
        isSubBold = !isSubBold;
        subBtnBold.classList.toggle('active', isSubBold);
        updateSubPreview();
    });
}

const subBtnItalic = document.getElementById('subBtnItalic');
if (subBtnItalic) {
    subBtnItalic.addEventListener('click', () => {
        isSubItalic = !isSubItalic;
        subBtnItalic.classList.toggle('active', isSubItalic);
        updateSubPreview();
    });
}

const subBtnUppercase = document.getElementById('subBtnUppercase');
if (subBtnUppercase) {
    subBtnUppercase.addEventListener('click', () => {
        isSubUppercase = !isSubUppercase;
        subBtnUppercase.classList.toggle('active', isSubUppercase);
        updateSubPreview();
    });
}

// Alignment Buttons
const subAlignLeft = document.getElementById('subAlignLeft');
const subAlignCenter = document.getElementById('subAlignCenter');
const subAlignRight = document.getElementById('subAlignRight');

function setSubAlignment(align, btn) {
    subTextAlign = align;
    [subAlignLeft, subAlignCenter, subAlignRight].forEach(b => b?.classList.remove('active'));
    btn?.classList.add('active');
    updateSubPreview();
}

if (subAlignLeft) subAlignLeft.addEventListener('click', () => setSubAlignment('left', subAlignLeft));
if (subAlignCenter) subAlignCenter.addEventListener('click', () => setSubAlignment('center', subAlignCenter));
if (subAlignRight) subAlignRight.addEventListener('click', () => setSubAlignment('right', subAlignRight));

// Position Snap Buttons
const subPosTop = document.getElementById('subPosTop');
const subPosMiddle = document.getElementById('subPosMiddle');
const subPosBottom = document.getElementById('subPosBottom');

if (subPosTop) {
    subPosTop.addEventListener('click', () => {
        [subPosTop, subPosMiddle, subPosBottom].forEach(b => b?.classList.remove('active'));
        subPosTop.classList.add('active');
        if (!currentSubRegion) currentSubRegion = { x: 10, y: 10, w: 80, h: 15, customPos: true };
        currentSubRegion.y = 8;
        currentSubRegion.customPos = true;
        updateSubPreview();
    });
}

if (subPosMiddle) {
    subPosMiddle.addEventListener('click', () => {
        [subPosTop, subPosMiddle, subPosBottom].forEach(b => b?.classList.remove('active'));
        subPosMiddle.classList.add('active');
        if (!currentSubRegion) currentSubRegion = { x: 10, y: 45, w: 80, h: 15, customPos: true };
        currentSubRegion.y = 45;
        currentSubRegion.customPos = true;
        updateSubPreview();
    });
}

if (subPosBottom) {
    subPosBottom.addEventListener('click', () => {
        [subPosTop, subPosMiddle, subPosBottom].forEach(b => b?.classList.remove('active'));
        subPosBottom.classList.add('active');
        if (currentSubRegion) currentSubRegion.customPos = false;
        const marginY = document.getElementById('subMarginY')?.value || 30;
        if (subPreviewBox) {
            subPreviewBox.style.top = 'auto';
            subPreviewBox.style.bottom = `${marginY}px`;
        }
        updateSubPreview();
    });
}

// Reset Subtitle Style Button
const btnResetSubStyle = document.getElementById('btnResetSubStyle');
if (btnResetSubStyle) {
    btnResetSubStyle.addEventListener('click', () => {
        applyPresetStyle('white');
        showToast('Đã khôi phục phong cách phụ đề mặc định.', 'info');
    });
}

// Master Subtitle Switch Listener (Bật / Tắt Toàn Bộ Phụ Đề & Mờ)
const subtitlesEnabled = document.getElementById('subtitlesEnabled');
const subtitleToggleLabel = document.getElementById('subtitleToggleLabel');
const subtitleCardBody = document.getElementById('subtitleCardBody');

if (subtitlesEnabled) {
    subtitlesEnabled.addEventListener('change', (e) => {
        const isEnabled = e.target.checked;
        if (subtitleToggleLabel) {
            subtitleToggleLabel.textContent = isEnabled ? 'Bật sub' : 'Tắt sub';
            subtitleToggleLabel.style.color = isEnabled ? '#38bdf8' : '#94a3b8';
        }
        if (subtitleCardBody) {
            subtitleCardBody.style.opacity = isEnabled ? '1' : '0.45';
            subtitleCardBody.style.pointerEvents = isEnabled ? 'auto' : 'none';
        }
        if (subPreviewBox && !isEnabled) {
            subPreviewBox.style.display = 'none';
            window._lastPreviewSubId = null;
        }
        if (!isEnabled && dynamicBlurOverlay) {
            dynamicBlurOverlay.style.opacity = '0';
            dynamicBlurOverlay.style.visibility = 'hidden';
            if (typeof _lastBlurState !== 'undefined') {
                _lastBlurState.visible = false;
                _lastBlurState.subId = null;
            }
        }
        updateSubPreview();
        updateDynamicBlurOverlayVisibility();
        showToast(isEnabled ? '✨ Đã BẬT phụ đề & làm mờ.' : '🚫 Đã TẮT toàn bộ phụ đề & làm mờ. Video xuất ra sẽ nguyên bản không có phụ đề hay vệt mờ.', isEnabled ? 'info' : 'warning');
    });
}

// Bind Color Picker <-> Text Inputs
function bindColorPair(pickerId, textId) {
    const picker = document.getElementById(pickerId);
    const text = document.getElementById(textId);
    if (picker && text) {
        picker.addEventListener('input', (e) => {
            text.value = e.target.value;
            updateSubPreview();
        });
        text.addEventListener('input', (e) => {
            if (/^#[0-9A-Fa-f]{6}$/.test(e.target.value)) {
                picker.value = e.target.value;
            }
            updateSubPreview();
        });
    }
}

bindColorPair('subColorPicker', 'subColorText');
bindColorPair('subOutlineColorPicker', 'subOutlineColorText');
bindColorPair('subShadowColorPicker', 'subShadowColorText');
bindColorPair('subBgColorPicker', 'subBgColorText');

// Bind Sliders to display text & preview
function bindSliderVal(sliderId, valId, suffix = 'px') {
    const slider = document.getElementById(sliderId);
    const val = document.getElementById(valId);
    if (slider && val) {
        slider.addEventListener('input', (e) => {
            val.textContent = e.target.value + suffix;
            updateSubPreview();
        });
    }
}

bindSliderVal('subSize', 'subSizeVal', 'px');
bindSliderVal('subOutline', 'subOutlineVal', 'px');
bindSliderVal('subShadowOffset', 'subShadowOffsetVal', 'px');
bindSliderVal('subMarginY', 'subMarginVal', 'px');
bindSliderVal('subBgOpacity', 'subBgOpacityVal', '%');
bindSliderVal('subBgBlur', 'subBgBlurVal', 'px');

const subFontSelect = document.getElementById('subFont');
if (subFontSelect) {
    subFontSelect.addEventListener('change', updateSubPreview);
}

// UI logic for background options
const subBgStyle = document.getElementById('subBgStyle');
const subBgColorConfig = document.getElementById('subBgColorConfig');
const subBgBlurConfig = document.getElementById('subBgBlurConfig');

if (subBgStyle) {
    subBgStyle.addEventListener('change', (e) => {
        if (e.target.value === 'none') {
            if(subBgColorConfig) subBgColorConfig.style.display = 'none';
            if(subBgBlurConfig) subBgBlurConfig.style.display = 'none';
        } else if (e.target.value === 'color') {
            if(subBgColorConfig) subBgColorConfig.style.display = 'block';
            if(subBgBlurConfig) subBgBlurConfig.style.display = 'none';
        } else if (e.target.value === 'blur') {
            if(subBgColorConfig) subBgColorConfig.style.display = 'none';
            if(subBgBlurConfig) subBgBlurConfig.style.display = 'block';
        }
        updateSubPreview();
    });
}

// OCR Scan Logic
let isExtractingOCR = false;
let ocrAbortController = null;

const btnScanOcr = document.getElementById('btnScanOcr');
btnScanOcr.addEventListener('click', async () => {
    if (isExtractingOCR) {
        // User wants to stop
        try {
            await fetch('/api/stop_ocr', { method: 'POST' });
            if (ocrAbortController) {
                ocrAbortController.abort();
            }
        } catch (e) { console.error("Error stopping OCR:", e); }
        return;
    }

    if (!checkFeaturePermission('can_access_editor', 'Trích xuất phụ đề OCR')) return;

    const inputPathEl = document.getElementById('editorInputVideoPath');
    if (!inputPathEl || !inputPathEl.value) {
        showToast("Vui lòng chọn video đầu vào (Nút Cài đặt)!", 'warning');
        return;
    }
    if (!currentRegion) {
        showToast("Vui lòng click 'Vẽ vùng mới' và khoanh vùng chứa phụ đề trên video!", 'warning');
        return;
    }
    
    const fps = document.getElementById('ocrFps').value;
    const threads = document.getElementById('ocrThreads').value;
    const device = document.getElementById('ocrDevice') ? document.getElementById('ocrDevice').value : 'cpu';
    
    resetExtraOcrRegionsForVideo();
    const payload = {
        video_path: inputPathEl.value,
        region: currentRegion,
        regions: [{ ...currentRegion, label: 'Phụ đề' }, ...extraOcrRegions.map(item => ({ ...item.region }))],
        fps: parseFloat(fps),
        threads: parseInt(threads),
        device: device,
        output_dir: (document.getElementById('outputDir')?.value || '').trim()
    };
    
    // Clear terminal and show
    const terminalContent = document.querySelector('.terminal-content');
    const terminalOverlay = document.querySelector('.terminal-overlay');
    if (terminalContent) terminalContent.innerHTML = '';
    if (terminalOverlay) {
        terminalOverlay.classList.remove('collapsed');
        terminalOverlay.classList.add('expanded');
    }
    appendLog('Bắt đầu quá trình trích xuất OCR...', 'info');
    
    try {
        isExtractingOCR = true;
        btnScanOcr.textContent = 'Dừng Trích Xuất';
        btnScanOcr.classList.remove('primary-cyan');
        btnScanOcr.classList.add('btn-danger');
        
        // Lock UI
        document.getElementById('tabSrt').style.pointerEvents = 'none';
        document.getElementById('tabOcr').style.pointerEvents = 'none';
        document.getElementById('tabAsr').style.pointerEvents = 'none';
        document.getElementById('btnDrawRegion').disabled = true;
        document.getElementById('ocrFps').disabled = true;
        document.getElementById('ocrThreads').disabled = true;
        if(document.getElementById('ocrDevice')) document.getElementById('ocrDevice').disabled = true;
        const btnSettings = document.getElementById('btnSettings');
        if(btnSettings) btnSettings.style.pointerEvents = 'none';
        
        ocrAbortController = new AbortController();
        const response = await fetch('/api/ocr_extract', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            signal: ocrAbortController.signal
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `OCR HTTP ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n\n');
            buffer = lines.pop(); // Keep last partial chunk
            
            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    const logMsg = line.substring(6);
                    appendLog(logMsg);
                    
                    if (logMsg.endsWith('_ocr.srt')) {
                        loadSrtToEditor(logMsg.trim());
                    }
                }
            }
        }
        
    } catch (e) {
        if (e.name === 'AbortError') {
            appendLog('Tiến trình OCR đã bị hủy.', 'warning');
        } else {
            appendLog('Lỗi kết nối tới Server: ' + e.message, 'error');
        }
    } finally {
        isExtractingOCR = false;
        btnScanOcr.textContent = 'Trích xuất OCR';
        btnScanOcr.classList.remove('btn-danger');
        btnScanOcr.classList.add('primary-cyan');
        
        // Unlock UI
        document.getElementById('tabSrt').style.pointerEvents = 'auto';
        document.getElementById('tabOcr').style.pointerEvents = 'auto';
        document.getElementById('tabAsr').style.pointerEvents = 'auto';
        document.getElementById('btnDrawRegion').disabled = false;
        document.getElementById('ocrFps').disabled = false;
        document.getElementById('ocrThreads').disabled = false;
        if(document.getElementById('ocrDevice')) document.getElementById('ocrDevice').disabled = false;
        const btnSettings = document.getElementById('btnSettings');
        if(btnSettings) btnSettings.style.pointerEvents = 'auto';
        ocrAbortController = null;
    }
});

// ==========================================
// SRT EDITOR LOGIC
// ==========================================



let srtData = []; // Array of subtitles
const configView = document.getElementById('configView');
const editorView = document.getElementById('editorView');
const srtTableBody = document.getElementById('srtTableBody');
const srtSearchInput = document.getElementById('srtSearchInput');
const srtSelectAll = document.getElementById('srtSelectAll');
const filterRadios = document.querySelectorAll('input[name="srtFilter"]');


let _autoSaveTimer = null;
function triggerAutoSaveEditorCache() {
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = setTimeout(async () => {
        const vid = editorInputVideoPath?.value || '';
        const outDir = (document.getElementById('outputDir')?.value || '').trim();
        if (!vid || !Array.isArray(srtData) || srtData.length === 0) return;
        try {
            await fetch('/api/editor/save_cache_subtitles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: vid,
                    output_dir: outDir,
                    subtitles: srtData
                })
            });
        } catch (e) {}
    }, 1500);
}

async function loadSrtToEditor(path) {
    try {
        window.currentExtractedSrtPath = path;
        const response = await fetch('/api/read_srt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                    output_dir: window.currentTtsOutputDir,srt_path: path})
        });
        const data = await response.json();
        
        if (data.error) {
            showToast('Lỗi đọc file SRT: ' + data.error, 'error');
            return;
        }
        
        srtData = data.subtitles.map(s => {
            let startSec = (typeof s.startSeconds === 'number' && !isNaN(s.startSeconds)) ? s.startSeconds : null;
            let endSec = (typeof s.endSeconds === 'number' && !isNaN(s.endSeconds)) ? s.endSeconds : null;
            if ((startSec === null || endSec === null) && s.time) {
                const timeParts = s.time.split('-');
                if (timeParts[0]) startSec = parseTimeToSeconds(timeParts[0]);
                if (timeParts[1]) endSec = parseTimeToSeconds(timeParts[1]);
            }
            let orig = (s.text || '').trim();
            let trans = (s.translation || '').trim();
            // Nếu là file SRT tiếng Việt đã dịch sẵn (không có chữ Hán): gán sang bản dịch để hiển thị đúng cột
            if (!trans && orig && !/[\u4e00-\u9fff]/.test(orig)) {
                trans = orig;
            }
            return {
                ...s,
                text: orig,
                translation: trans,
                startSeconds: startSec !== null ? startSec : 0,
                endSeconds: endSec !== null ? endSec : 0,
                selected: false
            };
        });
        
        // Swap Views
        if(configView) configView.style.display = 'none';
        if(editorView) editorView.style.display = 'flex';
        
        const btnTransferToReview = document.getElementById('btnTransferToReview');
        if (btnTransferToReview) {
            btnTransferToReview.style.display = (srtData && srtData.length > 0) ? 'inline-flex' : 'none';
        }
        
        renderSrtTable();
        showToast('Đã tải bản SRT thành công!', 'success');

        // Cảnh báo nếu độ dài file phụ đề lệch quá nhiều so với độ dài video
        if (videoPlayer && videoPlayer.duration > 60 && srtData.length > 0) {
            const lastSub = srtData[srtData.length - 1];
            const subMaxSec = lastSub.endSeconds || lastSub.startSeconds || 0;
            const vidSec = videoPlayer.duration;
            if (vidSec > 0 && subMaxSec > 0) {
                const diffSec = Math.abs(vidSec - subMaxSec);
                if (diffSec > 600 && subMaxSec < vidSec * 0.65) {
                    const fmtSub = `${Math.floor(subMaxSec/3600)}h${Math.floor((subMaxSec%3600)/60)}m`;
                    const fmtVid = `${Math.floor(vidSec/3600)}h${Math.floor((vidSec%3600)/60)}m`;
                    showToast(`⚠️ CẢNH BÁO LỆCH PHIM: Phụ đề chỉ dài ${fmtSub} (${srtData.length} câu) nhưng video dài ${fmtVid}. Có thể bạn đang nạp nhầm file phụ đề của phim khác!`, 'warning');
                }
            }
        }

        // Tự động kiểm tra toạ độ AI đã lưu cho video hiện tại nếu srtData chưa có toạ độ
        const currentVid = editorInputVideoPath?.value || '';
        const currentOutDir = (document.getElementById('outputDir')?.value || '').trim();
        if (currentVid && Array.isArray(srtData) && srtData.length > 0 && !srtData.some(s => s.aiBox)) {
            try {
                const boxesRes = await fetch(`/api/editor/cache_ai_boxes?video_path=${encodeURIComponent(currentVid)}&output_dir=${encodeURIComponent(currentOutDir)}`);
                if (boxesRes.ok) {
                    const boxesData = await boxesRes.json();
                    if (boxesData.success && Array.isArray(boxesData.boxes) && boxesData.boxes.length > 0) {
                        let appliedCount = 0;
                        boxesData.boxes.forEach(item => {
                            const idx = item.index;
                            const b = item.box || (Array.isArray(item) && item.length >= 5 ? {
                                x_pct: (item[3] * 100),
                                w_pct: (item[4] * 100),
                                visual_start: item[5],
                                visual_end: item[6]
                            } : null);
                            if (srtData[idx] && b) {
                                srtData[idx].aiBox = b;
                                if (b.visual_start !== undefined) srtData[idx].visual_start = b.visual_start;
                                if (b.visual_end !== undefined) srtData[idx].visual_end = b.visual_end;
                                appliedCount++;
                            }
                        });
                        if (appliedCount > 0) {
                            const chkAi = document.getElementById('blurUseAiScan');
                            if (chkAi) chkAi.checked = true;
                            if (typeof updateAiScanBadge === 'function') updateAiScanBadge();
                            if (typeof updateDynamicBlurIntervals === 'function') updateDynamicBlurIntervals();
                            showToast(`⚡ Đã tự động nạp ${appliedCount} toạ độ quét AI Pixel có sẵn!`, 'info');
                        }
                    }
                }
            } catch (e) {
                console.warn("Lỗi auto-check cache boxes:", e);
            }
        }
        
        // Update Dynamic Blur intervals for preview
        if (typeof updateDynamicBlurIntervals === 'function') {
            updateDynamicBlurIntervals();
            updateDynamicBlurOverlayVisibility();
        }

        // Tự động quét chiều rộng câu lớn nhất nếu đang chọn chế độ làm mờ cố định
        const currentBlurMode = document.querySelector('input[name="blurModeRadio"]:checked')?.value || 'fixed';
        if (currentBlurMode === 'fixed' && typeof scanMaxSubtitleWidth === 'function') {
            scanMaxSubtitleWidth(false);
        }
        
        // Auto activate "Bản sau khi sửa" mode to preview subtitles and styles
        if (btnPreviewEdited) {
            btnPreviewEdited.click();
        }

        triggerAutoSaveEditorCache();
        
    } catch (e) {
        showToast('Lỗi hệ thống: ' + e.message, 'error');
    }
}

// Xuất các hàm điều khiển Video & Phụ đề ra phạm vi window để Batch Editor và các module khác tái sử dụng
window.loadSrtToEditor = loadSrtToEditor;
window.getEditorSrtData = () => (typeof srtData !== 'undefined' && Array.isArray(srtData) ? srtData : []);
window.setEditorSrtData = (data) => {
    if (Array.isArray(data)) {
        srtData = data;
        if (typeof renderSrtTable === 'function') renderSrtTable();
        if (typeof updateBottomBarStats === 'function') updateBottomBarStats();
    }
};

window.loadVideoToEditor = async function(videoPath, srtPath = null) {
    if (!videoPath) return;

    // Nếu chỉ có tên file tương đối, thử tự động phân giải đường dẫn đầy đủ trước
    if (!videoPath.includes('/') && !videoPath.includes('\\')) {
        try {
            const res = await fetch(`/api/resolve_media_path?path=${encodeURIComponent(videoPath)}`);
            if (res.ok) {
                const d = await res.json();
                if (d.success && d.resolved_path) {
                    videoPath = d.resolved_path.replace(/\\/g, '/');
                    if (typeof window.updateActiveBatchItemVideoPath === 'function') {
                        window.updateActiveBatchItemVideoPath(videoPath);
                    }
                }
            }
        } catch (e) {}
    }

    if (editorInputVideoPath) editorInputVideoPath.value = videoPath;
    if (videoPlayer) {
        videoPlayer.src = `/api/video?path=${encodeURIComponent(videoPath)}`;
        videoPlayer.style.display = 'block';
        if (videoPlaceholder) videoPlaceholder.style.display = 'none';
        videoPlayer.load();
    }
    const ocrFilenameEl = document.getElementById('ocrRegionFilename');
    if (ocrFilenameEl) ocrFilenameEl.textContent = videoPath.split(/[\\/]/).pop();

    if (srtPath) {
        await loadSrtToEditor(srtPath);
    } else {
        if (configView) configView.style.display = 'flex';
        if (editorView) editorView.style.display = 'none';
        const tabOcr = document.getElementById('tabOcr');
        if (tabOcr) tabOcr.click();
    }
};

window.returnTopRowToEditor = function() {
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
};

function getSubtitleDuplicateInfo(sub, idx, arr) {
    if (!sub) return null;
    const list = arr || (typeof srtData !== 'undefined' && Array.isArray(srtData) ? srtData : []);
    if (!Array.isArray(list) || list.length < 2) return null;
    const i = (typeof idx === 'number' && idx >= 0) ? idx : list.findIndex(s => s.id === sub.id);
    if (i <= 0) return null; // Dòng đầu tiên trong danh sách giữ làm chuẩn

    // Chuẩn hóa văn bản: lược bỏ khoảng trắng, dấu câu và đưa về chữ thường
    const normText = (s) => (s || '').replace(/[\s\p{P}\p{S}]/gu, '').toLowerCase();
    const curText = normText(sub.text);
    const curTrans = normText(sub.translation);

    // Bắt buộc phải có nội dung câu gốc hoặc bản dịch để so sánh
    if (!curText && !curTrans) return null;

    const getTime = (s, type) => {
        let sec = typeof s[type + 'Seconds'] === 'number' ? s[type + 'Seconds'] : null;
        if (sec === null && s.time) {
            const parts = s.time.split('-');
            const part = type === 'start' ? parts[0] : parts[1];
            if (part && typeof parseTimeToSeconds === 'function') sec = parseTimeToSeconds(part);
        }
        return sec;
    };

    const curStart = getTime(sub, 'start');
    if (curStart === null) return null;

    // Quét ngược các câu phía trước (tối đa 5 câu)
    const scanLimit = Math.max(0, i - 5);
    for (let j = i - 1; j >= scanLimit; j--) {
        const other = list[j];
        if (!other) continue;

        const oStart = getTime(other, 'start');
        const oEnd = getTime(other, 'end');

        // Tính khoảng cách thời gian giữa 2 câu
        let dist = 0;
        if (oEnd !== null) {
            // Nếu câu sau bắt đầu sau khi câu trước kết thúc: dist = curStart - oEnd
            // Nếu câu sau bị đè/chồng lấn lên câu trước (dist <= 0): khoảng cách là 0s
            dist = Math.max(0, curStart - oEnd);
        } else if (oStart !== null) {
            dist = Math.abs(curStart - oStart);
        }

        // ĐIỀU KIỆN BẮT BUỘC: Cách nhau dưới 0.7s (dist <= 0.7s) theo yêu cầu người dùng
        if (dist > 0.7) {
            // Nếu danh sách theo thứ tự thời gian và mốc bắt đầu đã cách quá 2s, dừng quét sớm
            if (oStart !== null && curStart - oStart > 2.0) break;
            continue;
        }

        const oText = normText(other.text);
        const oTrans = normText(other.translation);

        // ĐIỀU KIỆN BẮT BUỘC: Hai câu giống y hệt nhau về câu gốc hoặc bản dịch
        const sameOrig = curText && oText && curText === oText;
        const sameTrans = curTrans && oTrans && curTrans === oTrans;

        if (sameOrig) {
            const distLabel = dist > 0 ? ` (cách ${dist.toFixed(1)}s)` : '';
            return `Trùng câu gốc với câu #${other.id}${distLabel}`;
        }
        if (sameTrans) {
            const distLabel = dist > 0 ? ` (cách ${dist.toFixed(1)}s)` : '';
            return `Trùng bản dịch với câu #${other.id}${distLabel}`;
        }
    }

    return null;
}

function isSubtitleDuplicate(sub, idx, arr) {
    return getSubtitleDuplicateInfo(sub, idx, arr) !== null;
}

function getSubtitleErrorInfo(sub, idx, arr) {
    if (!sub) return null;
    const text = (sub.text || '').trim();
    const trans = (sub.translation || '').trim();

    // 1. Câu gốc bị rỗng hoặc chỉ toàn ký tự rác / dấu câu
    if (!text) {
        return "Câu gốc bị rỗng";
    }
    if (/^[.,\/#!$%\^&\*;:{}=\-_`~() ]+$/.test(text)) {
        return "Câu gốc toàn ký tự rác";
    }

    // 1b. Câu gốc chỉ có 1 chữ cái (Latin) hoặc 1 con số (OCR rác / watermark lỗi)
    const cleanTextCore = text.replace(/[\s\p{P}\p{S}]/gu, '');
    if (cleanTextCore.length === 1 && /^[a-zA-Z0-9]$/.test(cleanTextCore)) {
        return "Câu gốc chỉ có 1 chữ cái/con số (OCR rác)";
    }
    if (cleanTextCore.length > 0 && cleanTextCore.length <= 2 && /^\d+$/.test(cleanTextCore)) {
        return "Câu gốc chỉ toàn con số (OCR rác)";
    }

    // 1c. Bản dịch chỉ có 1 chữ cái hoặc 1 con số (dịch lỗi / cụt ngủn)
    if (trans) {
        const cleanTransCore = trans.replace(/[\s\p{P}\p{S}]/gu, '');
        if (cleanTransCore.length === 1 && /^[\wà-ỹÀ-Ỹ]$/i.test(cleanTransCore)) {
            return "Bản dịch chỉ có 1 chữ cái/con số (dịch lỗi)";
        }
        if (cleanTransCore.length > 0 && cleanTransCore.length <= 2 && /^\d+$/.test(cleanTransCore)) {
            return "Bản dịch chỉ có số (dịch lỗi)";
        }
    }

    // 2. Đã dịch nhưng dịch chưa hết / còn sót tiếng Trung hoặc ngoặc giải nghĩa:
    // a. Còn dính chữ Hán trong bản dịch tiếng Việt
    if (trans && /[\u4e00-\u9fff]/.test(trans)) {
        return "Còn sót chữ Hán (dịch chưa hết)";
    }

    // b. Còn dính ngoặc chú giải từ vựng / giải nghĩa: vd "既然 (vì)", "thật有心 (có tình ý)", "(vì)", "(lại)"
    if (trans && /(?:[\u4e00-\u9fff]+\s*[\(\（][^\)\）]+[\)\）]|[\(\（][^\)\）]+[\)\）]\s*[\u4e00-\u9fff]+|\([a-zà-ỹA-ZÀ-Ỹ\s]{1,20}\)|（[a-zà-ỹA-ZÀ-Ỹ\s]{1,20}）)/.test(trans)) {
        return "Dính chú thích ngoặc đơn";
    }

    // c. Giữ nguyên câu gốc tiếng Trung (chưa dịch thực sự mà copy đè)
    if (trans && trans === text && /[\u4e00-\u9fff]/.test(text)) {
        return "Chưa dịch (trùng câu gốc tiếng Trung)";
    }

    // 3. Chứa chuỗi báo lỗi từ AI hoặc hệ thống
    if (trans && /(?:error|mã lỗi|timeout|rate limit|too many requests|overloaded|bad gateway|500|502|503|504|429|\[TRANSLATE\]|\[CONTEXT\]|\[GLOSSARY\]|<think>|<\/think>|```|undefined|null|NaN)/i.test(trans)) {
        return "Lỗi phản hồi AI / Hệ thống";
    }

    // 4. Sót ID dòng từ LLM ở đầu câu dịch: vd "1291|", "[1291] "
    if (trans && /^(?:\[?\d+\]?\s*\|\s*|\[\d+\]\s*)/.test(trans)) {
        return "Dính mã ID đầu câu";
    }

    // 5. Câu gốc dài nhưng bản dịch cụt ngủn bất thường (chỉ có 1 ký tự dấu câu . , ! ? -)
    if (text.length >= 4 && trans.length > 0 && trans.length <= 2 && /^[.,\-?!]+$/.test(trans)) {
        return "Bản dịch cụt ngủn bất thường";
    }

    // 6. Lặp từ bất thường (vòng lặp suy thoái token AI)
    if (trans && /(?:^|\s)([\wà-ỹ]+)\s+\1\s+\1\s+\1(?:\s|$)/i.test(trans)) {
        return "Bản dịch bị lặp từ liên tiếp";
    }

    // 7. Lỗi thời gian: start >= end hoặc thời lượng <= 0
    let sStart = typeof sub.startSeconds === 'number' ? sub.startSeconds : null;
    let sEnd = typeof sub.endSeconds === 'number' ? sub.endSeconds : null;
    if ((sStart === null || sEnd === null) && sub.time) {
        const parts = sub.time.split('-');
        if (parts[0]) sStart = typeof parseTimeToSeconds === 'function' ? parseTimeToSeconds(parts[0]) : null;
        if (parts[1]) sEnd = typeof parseTimeToSeconds === 'function' ? parseTimeToSeconds(parts[1]) : null;
    }
    if (sStart !== null && sEnd !== null && !isNaN(sStart) && !isNaN(sEnd)) {
        if (sStart >= sEnd || (sEnd - sStart) < 0.05) {
            return "Thời lượng không hợp lệ (<= 0s)";
        }
        if ((sEnd - sStart) > 45) {
            return "Thời lượng quá dài (> 45s)";
        }
    }

    // 8. Trùng lặp với câu phụ đề khác (Trùng câu gốc, trùng bản dịch hoặc trùng mốc thời gian)
    const dupInfo = getSubtitleDuplicateInfo(sub, idx, arr);
    if (dupInfo) {
        return dupInfo;
    }

    return null;
}

function isSubtitleError(sub, idx, arr) {
    return getSubtitleErrorInfo(sub, idx, arr) !== null;
}

function isSubtitleUntranslated(sub) {
    if (!sub) return false;
    const trans = (sub.translation || '').trim();
    if (!trans) return true;
    const text = (sub.text || '').trim();
    // Vẫn dính chữ Hán trong câu dịch -> chưa dịch sang tiếng Việt
    if (/[\u4e00-\u9fff]/.test(trans)) return true;
    // Giữ nguyên câu gốc tiếng Trung
    if (trans === text && /[\u4e00-\u9fff]/.test(text)) return true;
    return false;
}

function updateSrtRowTranslation(id, translation) {
    if (!srtTableBody) return;
    const row = srtTableBody.querySelector(`tr[data-sub-id="${id}"]`);
    if (row) {
        const tdTrans = row.querySelector('.srt-trans-td');
        if (tdTrans && !tdTrans.querySelector('input')) {
            const sub = srtData.find(s => s.id === id);
            if (sub) sub.translation = translation;
            const isUntrans = isSubtitleUntranslated({ translation, text: sub?.text || '' });
            if (translation && translation.trim()) {
                tdTrans.textContent = translation;
                tdTrans.classList.add('translated');
            } else {
                tdTrans.innerHTML = `<span class="srt-untranslated-badge">⚠️ Chưa dịch...</span>`;
                tdTrans.classList.remove('translated');
            }
            const errReason = sub ? getSubtitleErrorInfo(sub) : null;
            if (errReason) {
                tdTrans.classList.add('srt-error-cell');
                const warnBadge = document.createElement('span');
                warnBadge.className = 'srt-error-badge';
                warnBadge.title = errReason;
                warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">${errReason}</small>`;
                tdTrans.appendChild(document.createTextNode(' '));
                tdTrans.appendChild(warnBadge);
                row.classList.add('srt-row-has-error');
                row.classList.remove('srt-row-untranslated');
            } else if (isUntrans) {
                tdTrans.classList.remove('srt-error-cell');
                row.classList.remove('srt-row-has-error');
                row.classList.add('srt-row-untranslated');
            } else {
                tdTrans.classList.remove('srt-error-cell');
                row.classList.remove('srt-row-has-error');
                row.classList.remove('srt-row-untranslated');
            }
        }
    }
}

function renderSrtTable() {
    const btnTransferToReview = document.getElementById('btnTransferToReview');
    if (btnTransferToReview) {
        btnTransferToReview.style.display = (srtData && srtData.length > 0) ? 'inline-flex' : 'none';
    }

    if (srtData.length === 0) {
        if(configView) configView.style.display = 'flex';
        if(editorView) editorView.style.display = 'none';
        return; // Switch back and do not render empty table
    }

    srtTableBody.innerHTML = '';
    
    // Apply filters
    const searchTerm = srtSearchInput.value.toLowerCase();
    const activeFilter = document.querySelector('input[name="srtFilter"]:checked')?.value;
    
    let filtered = srtData.filter(sub => {
        // Search
        if (searchTerm && !sub.text.toLowerCase().includes(searchTerm) && !sub.translation.toLowerCase().includes(searchTerm)) {
            return false;
        }
        
        // Filter
        if (activeFilter === 'long') {
            const tLen = (sub.text || '').length;
            const trLen = (sub.translation || '').length;
            if (tLen < 50 && trLen < 70) return false;
        }
        if (activeFilter === 'untranslated' && !isSubtitleUntranslated(sub)) return false;
        if (activeFilter === 'error' && !isSubtitleError(sub)) return false;
        if (activeFilter === 'duplicate' && !isSubtitleDuplicate(sub)) return false;
        
        return true;
    });
    
    window._currentFilteredSubs = filtered;

    const fragment = document.createDocumentFragment();
    filtered.forEach(sub => {
        const tr = document.createElement('tr');
        tr.setAttribute('data-sub-id', sub.id);
        const errReason = getSubtitleErrorInfo(sub);
        const isUntrans = isSubtitleUntranslated(sub);
        if (errReason) {
            tr.classList.add('srt-row-has-error');
            tr.title = `⚠️ Có thể lỗi: ${errReason}`;
        } else if (isUntrans) {
            tr.classList.add('srt-row-untranslated');
            tr.title = `⚠️ Chưa dịch`;
        }
        
        const tdCheck = document.createElement('td');
        tdCheck.style.textAlign = 'center';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'custom-checkbox-circle';
        checkbox.checked = sub.selected;
        checkbox.addEventListener('change', (e) => {
            sub.selected = e.target.checked;
            updateBottomBarStats();
        });
        tdCheck.appendChild(checkbox);
        
        const tdId = document.createElement('td');
        tdId.style.textAlign = 'center';
        tdId.textContent = sub.id;
        
        const tdTime = document.createElement('td');
        tdTime.style.whiteSpace = 'nowrap';
        let cleanTime = (sub.time || '').trim();
        cleanTime = cleanTime.replace(/\.000/g, '').replace(/ --> /g, ' → ').replace(/ - /g, ' → ');
        tdTime.innerHTML = `<span class="srt-time-tag">${cleanTime}</span>`;
        
        const tdAction = document.createElement('td');
        tdAction.className = 'action-icon-toolbar';
        
        const btnPlay = document.createElement('button');
        btnPlay.className = 'action-icon-btn';
        btnPlay.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
        btnPlay.title = "Phát tại thời điểm này";
        btnPlay.addEventListener('click', (e) => {
            e.stopPropagation();
            let targetSecs = sub.startSeconds;
            if (typeof targetSecs !== 'number' || isNaN(targetSecs)) {
                if (sub.time) {
                    const m = sub.time.match(/(\d{2}):(\d{2}):(\d{2})[.,](\d{1,3})/);
                    if (m) {
                        targetSecs = parseInt(m[1], 10) * 3600 + parseInt(m[2], 10) * 60 + parseInt(m[3], 10) + parseInt(m[4].padEnd(3, '0'), 10) / 1000;
                    } else {
                        targetSecs = 0;
                    }
                } else {
                    targetSecs = 0;
                }
            }
            
            safeSeekVideo(targetSecs, true);
            
            // Switch to Edited mode so the subtitle is visible
            if (btnPreviewEdited && !btnPreviewEdited.classList.contains('active')) {
                btnPreviewEdited.click();
            }
        });
        
        const btnDel = document.createElement('button');
        btnDel.className = 'action-icon-btn delete';
        btnDel.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`;
        btnDel.title = "Xóa dòng này";
        btnDel.addEventListener('click', () => {
            srtData = srtData.filter(s => s.id !== sub.id);
            renderSrtTable();
        });

        const btnVoicePlay = document.createElement('button');
        btnVoicePlay.className = 'action-icon-btn voice-preview-btn';
        btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
        btnVoicePlay.title = "Nghe thử giọng đọc AI câu này";
        btnVoicePlay.style.color = '#38bdf8';
        btnVoicePlay.addEventListener('click', async (e) => {
            e.stopPropagation();
            const textToSpeak = (sub.translation || sub.text || '').trim();
            if (!textToSpeak) {
                showToast("Câu này chưa có nội dung chữ để đọc!", "warning");
                return;
            }
            const voiceId = document.getElementById('dubbingVoiceInput')?.value || 'local_clone_1787245769140';
            const speed = parseFloat(document.getElementById('dubbingSpeed')?.value || 1.1);
            
            btnVoicePlay.innerHTML = `⏳`;
            try {
                const res = await fetch('/api/tts/sentence_preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: textToSpeak, voice_id: voiceId, speed })
                });
                const data = await res.json();
                if (data.success && data.audio_url) {
                    if (window._currentSentenceAudio) {
                        try {
                            window._currentSentenceAudio.pause();
                            window._currentSentenceAudio.currentTime = 0;
                        } catch(e) {}
                        window._currentSentenceAudio = null;
                    }
                    const audio = new Audio(data.audio_url);
                    window._currentSentenceAudio = audio;
                    const voiceVol = parseFloat(document.getElementById('dubbingVoiceVol')?.value || 100);
                    audio.volume = Math.max(0, Math.min(1.0, voiceVol / 100));
                    btnVoicePlay.innerHTML = `🔊`;
                    audio.onended = () => {
                        btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
                        if (window._currentSentenceAudio === audio) window._currentSentenceAudio = null;
                    };
                    audio.onerror = () => {
                        btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
                        if (window._currentSentenceAudio === audio) window._currentSentenceAudio = null;
                    };
                    audio.play();
                } else {
                    showToast("Không thể tạo giọng đọc: " + (data.error || "Lỗi không xác định"), "error");
                    btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
                }
            } catch (err) {
                showToast("Lỗi kết nối tạo giọng đọc: " + err.message, "error");
                btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
            }
        });

        tdAction.appendChild(btnPlay);
        tdAction.appendChild(btnVoicePlay);
        tdAction.appendChild(btnDel);
        
        const tdText = document.createElement('td');
        tdText.textContent = sub.text;
        const isOriginalError = errReason && (errReason.startsWith("Câu gốc") || errReason.includes("Trùng câu gốc") || errReason.includes("Trùng mốc thời gian"));
        if (isOriginalError) {
            tdText.classList.add('srt-error-cell');
            const warnBadge = document.createElement('span');
            warnBadge.className = 'srt-error-badge';
            warnBadge.title = errReason;
            warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">${errReason}</small>`;
            tdText.appendChild(document.createTextNode(' '));
            tdText.appendChild(warnBadge);
        }
        
        const tdTrans = document.createElement('td');
        tdTrans.className = 'srt-trans-td';
        if (sub.translation && sub.translation.trim()) {
            tdTrans.textContent = sub.translation;
            tdTrans.classList.add('translated');
        } else {
            tdTrans.innerHTML = `<span class="srt-untranslated-badge">⚠️ Chưa dịch...</span>`;
            tdTrans.classList.remove('translated');
        }
        if (errReason && !isOriginalError) {
            tdTrans.classList.add('srt-error-cell');
            const warnBadge = document.createElement('span');
            warnBadge.className = 'srt-error-badge';
            warnBadge.title = errReason;
            warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">${errReason}</small>`;
            tdTrans.appendChild(document.createTextNode(' '));
            tdTrans.appendChild(warnBadge);
        } else if (isUntrans && sub.translation && sub.translation.trim()) {
            tdTrans.classList.add('srt-error-cell');
            const warnBadge = document.createElement('span');
            warnBadge.className = 'srt-error-badge';
            warnBadge.title = 'Còn dính tiếng Trung';
            warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">Còn dính tiếng Trung</small>`;
            tdTrans.appendChild(document.createTextNode(' '));
            tdTrans.appendChild(warnBadge);
        }
        
        // Single click to edit text or translation
        const setupInlineEdit = (cell, fieldName) => {
            cell.addEventListener('click', () => {
                if (cell.querySelector('input')) return; // Already editing
                
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'srt-inline-input';
                input.value = sub[fieldName] || '';
                
                cell.innerHTML = '';
                cell.appendChild(input);
                input.focus();
                
                const save = () => {
                    const newVal = input.value;
                    const oldVal = sub[fieldName];
                    sub[fieldName] = newVal;
                    if (newVal !== oldVal && typeof triggerAutoSaveEditorCache === 'function') {
                        triggerAutoSaveEditorCache();
                    }
                    // Cập nhật trực tiếp nội dung cell tại chỗ, tránh xóa & dựng lại cả bảng
                    if (fieldName === 'translation') {
                        const isNowUntrans = isSubtitleUntranslated(sub);
                        if (newVal && newVal.trim()) {
                            cell.textContent = newVal;
                            cell.classList.add('translated');
                        } else {
                            cell.innerHTML = `<span class="srt-untranslated-badge">⚠️ Chưa dịch...</span>`;
                            cell.classList.remove('translated');
                        }
                        const errReason = getSubtitleErrorInfo(sub);
                        if (errReason) {
                            cell.classList.add('srt-error-cell');
                            const warnBadge = document.createElement('span');
                            warnBadge.className = 'srt-error-badge';
                            warnBadge.title = errReason;
                            warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">${errReason}</small>`;
                            cell.appendChild(document.createTextNode(' '));
                            cell.appendChild(warnBadge);
                            tr.classList.add('srt-row-has-error');
                            tr.classList.remove('srt-row-untranslated');
                            tr.title = `⚠️ Có thể lỗi: ${errReason}`;
                        } else if (isNowUntrans) {
                            cell.classList.remove('srt-error-cell');
                            tr.classList.remove('srt-row-has-error');
                            tr.classList.add('srt-row-untranslated');
                            tr.title = `⚠️ Chưa dịch`;
                        } else {
                            cell.classList.remove('srt-error-cell');
                            tr.classList.remove('srt-row-has-error');
                            tr.classList.remove('srt-row-untranslated');
                            tr.title = '';
                        }
                        updateBottomBarStats();
                    } else {
                        cell.textContent = newVal;
                        const errReason = getSubtitleErrorInfo(sub);
                        if (errReason) {
                            if (errReason.startsWith("Câu gốc") || errReason.includes("Trùng câu gốc") || errReason.includes("Trùng mốc thời gian")) {
                                cell.classList.add('srt-error-cell');
                                const warnBadge = document.createElement('span');
                                warnBadge.className = 'srt-error-badge';
                                warnBadge.title = errReason;
                                warnBadge.innerHTML = `⚠️ <small style="opacity:0.9;font-size:10px;color:#fca5a5;">${errReason}</small>`;
                                cell.appendChild(document.createTextNode(' '));
                                cell.appendChild(warnBadge);
                            }
                            tr.classList.add('srt-row-has-error');
                            tr.title = `⚠️ Có thể lỗi: ${errReason}`;
                        } else {
                            cell.classList.remove('srt-error-cell');
                            tr.classList.remove('srt-row-has-error');
                            tr.title = '';
                        }
                        updateBottomBarStats();
                    }
                };
                
                input.addEventListener('blur', save);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') input.blur();
                });
            });
        };
        
        setupInlineEdit(tdText, 'text');
        setupInlineEdit(tdTrans, 'translation');
        
        tr.appendChild(tdCheck);
        tr.appendChild(tdId);
        tr.appendChild(tdTime);
        tr.appendChild(tdAction);
        tr.appendChild(tdText);
        tr.appendChild(tdTrans);
        
        fragment.appendChild(tr);
    });
    
    srtTableBody.appendChild(fragment);
    updateBottomBarStats();
}

function updateBottomBarStats() {
    const selectedCount = srtData.filter(s => s.selected).length;
    const btnDelSelSpan = document.querySelector('#btnDeleteSelected span');
    if (btnDelSelSpan) btnDelSelSpan.innerHTML = `Xóa đã chọn (${selectedCount})`;
    
    const lblTranslateSelected = document.getElementById('lblTranslateSelected');
    if (lblTranslateSelected) lblTranslateSelected.textContent = `Dịch câu đã chọn (${selectedCount})`;
    const btnTranslateSelected = document.getElementById('btnTranslateSelected');
    if (btnTranslateSelected) {
        btnTranslateSelected.style.opacity = selectedCount > 0 ? '1' : '0.65';
    }
    
    const translatedCount = srtData.filter(s => s.translation && s.translation.trim() && !/[\u4e00-\u9fff]/.test(s.translation)).length;
    const btnDelTransSpan = document.querySelector('#btnDeleteTranslation span');
    if (btnDelTransSpan) btnDelTransSpan.innerHTML = `Xóa bản dịch (${translatedCount})`;

    const untranslatedCount = srtData.filter(isSubtitleUntranslated).length;
    const lblUntranslated = document.getElementById('lblSrtFilterUntranslated');
    if (lblUntranslated) {
        lblUntranslated.innerHTML = untranslatedCount > 0 
            ? `Chưa dịch <span style="background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 1px 6px; border-radius: 10px; font-size: 11px; margin-left: 3px; font-weight: 600;">${untranslatedCount}</span>` 
            : 'Chưa dịch';
    }

    const errorCount = srtData.filter(isSubtitleError).length;
    const lblError = document.getElementById('lblSrtFilterError');
    if (lblError) {
        lblError.innerHTML = errorCount > 0 
            ? `Có thể lỗi <span style="background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 1px 6px; border-radius: 10px; font-size: 11px; margin-left: 3px; font-weight: 600;">${errorCount}</span>` 
            : 'Có thể lỗi';
    }

    const duplicateCount = srtData.filter(isSubtitleDuplicate).length;
    const lblDuplicate = document.getElementById('lblSrtFilterDuplicate');
    if (lblDuplicate) {
        lblDuplicate.innerHTML = duplicateCount > 0 
            ? `Trùng lặp <span style="background: rgba(245, 158, 11, 0.25); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); padding: 1px 6px; border-radius: 10px; font-size: 11px; margin-left: 3px; font-weight: 600;">${duplicateCount}</span>` 
            : 'Trùng lặp';
    }

    const btnDeleteDuplicates = document.getElementById('btnDeleteDuplicates');
    if (btnDeleteDuplicates) {
        if (duplicateCount > 0) {
            btnDeleteDuplicates.style.display = 'inline-flex';
            const span = btnDeleteDuplicates.querySelector('span');
            if (span) span.textContent = `Xóa câu trùng (${duplicateCount})`;
        } else {
            btnDeleteDuplicates.style.display = 'none';
        }
    }
}

// Event Listeners for Editor
let _srtSearchDebounceTimer = null;
if (srtSearchInput) {
    srtSearchInput.addEventListener('input', () => {
        clearTimeout(_srtSearchDebounceTimer);
        _srtSearchDebounceTimer = setTimeout(renderSrtTable, 200);
    });
}
filterRadios.forEach(r => r.addEventListener('change', renderSrtTable));

if (srtSelectAll) {
    srtSelectAll.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        if (window._currentFilteredSubs && Array.isArray(window._currentFilteredSubs) && window._currentFilteredSubs.length < srtData.length) {
            const filteredIdSet = new Set(window._currentFilteredSubs.map(s => String(s.id)));
            srtData.forEach(sub => {
                if (filteredIdSet.has(String(sub.id))) {
                    sub.selected = isChecked;
                }
            });
        } else {
            srtData.forEach(sub => sub.selected = isChecked);
        }
        renderSrtTable();
    });
}



const btnDownloadTranslatedSrt = document.getElementById('btnDownloadTranslatedSrt');
if (btnDownloadTranslatedSrt) {
    btnDownloadTranslatedSrt.addEventListener('click', async () => {
        if (!srtData || srtData.length === 0) {
            showToast("Chưa có danh sách phụ đề nào để lưu!", "warning");
            return;
        }
        
        let srtContent = "";
        srtData.forEach((sub, idx) => {
            let timeLine = sub.time;
            if (!timeLine || !timeLine.includes('-->')) {
                const sStart = sub.startSeconds !== undefined ? sub.startSeconds : 0;
                const sEnd = sub.endSeconds !== undefined ? sub.endSeconds : (sStart + 3);
                timeLine = `${formatSrtTimestamp(sStart)} --> ${formatSrtTimestamp(sEnd)}`;
            }
            
            const subText = (sub.translation && sub.translation.trim()) ? sub.translation.trim() : (sub.text || '').trim();
            srtContent += `${idx + 1}\n${timeLine}\n${subText}\n\n`;
        });
        
        let baseName = "subtitles_translated";
        if (editorInputVideoPath && editorInputVideoPath.value) {
            const raw = editorInputVideoPath.value.split(/[\\/]/).pop().replace(/\.[^/.]+$/, "");
            if (raw) baseName = raw + "_vi";
        }
        const defaultFileName = `${baseName}.srt`;
        
        // 1. Try Browser Native File System Save Dialog
        if (window.showSaveFilePicker) {
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: defaultFileName,
                    types: [{
                        description: 'SubRip Subtitles (*.srt)',
                        accept: { 'text/plain': ['.srt'] }
                    }]
                });
                const writable = await handle.createWritable();
                await writable.write(srtContent);
                await writable.close();
                showToast(`Đã lưu file SRT thành công: ${handle.name}`, "success");
                return;
            } catch (err) {
                if (err.name === 'AbortError') {
                    return; // User clicked Cancel
                }
                console.warn('showSaveFilePicker failed, trying desktop save dialog...', err);
            }
        }
        
        // 2. Try Backend Desktop Windows Save Dialog (Tkinter / PowerShell)
        try {
            const res = await fetch('/api/save_file_dialog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: 'Chọn nơi lưu file phụ đề (.srt)',
                    default_name: defaultFileName,
                    content: srtContent
                })
            });
            const resData = await res.json();
            if (resData.success && resData.file_path) {
                showToast(`Đã lưu file SRT tại: ${resData.file_path}`, "success");
                return;
            } else if (resData.cancelled) {
                return; // User cancelled
            }
        } catch (e) {
            console.warn('Backend save dialog error, falling back to direct download...', e);
        }
        
        // 3. Fallback to standard browser download
        const blob = new Blob([srtContent], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = defaultFileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        
        showToast("Đã tải file SRT đã dịch về thư mục Downloads!", "success");
    });
}

// 🎬 Chuyển Video & Phụ Đề đã trích xuất sang Studio Review Phim
const btnTransferToReview = document.getElementById('btnTransferToReview');
if (btnTransferToReview) {
    btnTransferToReview.addEventListener('click', async () => {
        if (!checkFeaturePermission('can_access_review', 'Review Phim')) return;

        const videoPath = (document.getElementById('editorInputVideoPath')?.value || '').trim();
        if (!videoPath) {
            showToast('⚠️ Vui lòng chọn video đầu vào trước khi chuyển sang Review Phim!', 'warning');
            return;
        }

        if (!srtData || srtData.length === 0) {
            showToast('⚠️ Chưa có nội dung phụ đề nào được trích xuất!', 'warning');
            return;
        }

        let targetSrtPath = window.currentExtractedSrtPath || '';

        // Tự động lưu/xuất file SRT chuẩn (bao gồm cả nội dung đã dịch/chỉnh sửa)
        try {
            const res = await fetch('/api/subtitles/export_temp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subtitles: srtData,
                    video_path: videoPath
                })
            });
            const data = await res.json();
            if (data.success && data.srt_path) {
                targetSrtPath = data.srt_path;
                window.currentExtractedSrtPath = targetSrtPath;
            }
        } catch (e) {
            console.warn('Lỗi lưu tạm SRT:', e);
        }

        // Chuyển video sang thẻ Review Phim
        sendVideoToReview(videoPath);

        // Nạp phụ đề vào thẻ Review Phim
        const reviewSrtInput = document.getElementById('reviewInputSrtPath');
        if (reviewSrtInput && targetSrtPath) {
            reviewSrtInput.value = targetSrtPath;
            if (typeof autoParseReviewSrt === 'function') {
                autoParseReviewSrt(targetSrtPath);
            }
        }

        // Chuyển tab sang Review Phim
        const reviewTab = document.querySelector('.nav-tab[data-target="viewReview"]');
        if (reviewTab) {
            reviewTab.click();
        }

        showToast('🎬 Đã chuyển Video & Phụ đề sang Studio Review Phim thành công!', 'success');
    });
}

function showAiTranslateChoiceModal(totalCount) {
    return new Promise((resolve) => {
        const modal = document.getElementById('aiTranslateModal');
        const countEl = document.getElementById('aiTranslateTotalCount');
        const badgeAll = document.getElementById('aiTranslateBadgeAll');
        const btn20 = document.getElementById('btnAiTranslate20');
        const btnAll = document.getElementById('btnAiTranslateAll');
        const cancelBtn = document.getElementById('cancelAiTranslateBtn');
        const closeBtn = document.getElementById('closeAiTranslateBtn');
        
        if (countEl) countEl.textContent = totalCount;
        if (badgeAll) badgeAll.textContent = `${totalCount} câu`;
        
        if (!modal) {
            resolve('all');
            return;
        }
        
        modal.style.display = 'flex';
        modal.classList.add('active');
        
        const cleanup = (choice) => {
            modal.style.display = 'none';
            modal.classList.remove('active');
            if (btn20) btn20.removeEventListener('click', on20);
            if (btnAll) btnAll.removeEventListener('click', onAll);
            if (cancelBtn) cancelBtn.removeEventListener('click', onCancel);
            if (closeBtn) closeBtn.removeEventListener('click', onCancel);
            modal.removeEventListener('click', onOverlay);
            resolve(choice);
        };
        
        const on20 = () => cleanup('20');
        const onAll = () => cleanup('all');
        const onCancel = () => cleanup(null);
        const onOverlay = (e) => { if (e.target === modal) cleanup(null); };
        
        if (btn20) btn20.addEventListener('click', on20);
        if (btnAll) btnAll.addEventListener('click', onAll);
        if (cancelBtn) cancelBtn.addEventListener('click', onCancel);
        if (closeBtn) closeBtn.addEventListener('click', onCancel);
        modal.addEventListener('click', onOverlay);
    });
}

/**
 * Hộp thoại cho phép người dùng lựa chọn:
 * 1. Online (Cloud AI): OpenAI GPT / OpenRouter / Google Dịch
 * 2. Offline (Local GPU): Qwen 2.5 chạy cục bộ trên GPU NVIDIA qua Ollama
 */
export function promptAiExecutionMode(actionTitle = 'Chọn Chế Độ AI', actionSubtitle = 'Chọn dịch vụ Online (Cloud AI - GPT Luna) hoặc chạy 100% Offline trên GPU RTX', options = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById('aiModeSelectionModal');
        if (!modal) {
            resolve({ engine: 'online' });
            return;
        }

        const titleEl = document.getElementById('aiModeModalTitle');
        const subTitleEl = document.getElementById('aiModeModalSubtitle');
        const cardOnline = document.getElementById('cardAiModeOnline');
        const cardOffline = document.getElementById('cardAiModeOffline');
        const closeBtn = document.getElementById('closeAiModeModalBtn');
        const cancelBtn = document.getElementById('cancelAiModeModalBtn');

        const langBox = document.getElementById('aiModeLangSelectionBox');
        const modalSrcEl = document.getElementById('modalSubSourceLang');
        const modalTgtEl = document.getElementById('modalSubTargetLang');
        const mainSrcEl = document.getElementById('subSourceLang');
        const mainTgtEl = document.getElementById('subTargetLang');
        const bottomTgtEl = document.getElementById('bottomSubTargetLang');
        const modalStyleEl = document.getElementById('modalSubTranslationStyle');
        const mainStyleEl = document.getElementById('subTranslationStyle');
        const bottomStyleEl = document.getElementById('bottomSubTranslationStyle');

        const isTranslate = options.showLanguageOptions !== undefined 
            ? options.showLanguageOptions 
            : actionTitle.toLowerCase().includes('dịch');

        if (langBox) langBox.style.display = isTranslate ? 'flex' : 'none';

        if (modalSrcEl && mainSrcEl) {
            modalSrcEl.value = mainSrcEl.value || 'auto';
        }
        if (modalTgtEl) {
            const currentTgt = (bottomTgtEl && bottomTgtEl.value) || (mainTgtEl && mainTgtEl.value) || 'vi';
            modalTgtEl.value = currentTgt;
        }
        if (modalStyleEl) {
            const currentStyle = (mainStyleEl && mainStyleEl.value) || 
                                 (bottomStyleEl && bottomStyleEl.value) || 
                                 localStorage.getItem('novacut_translation_style') || 'cinema';
            modalStyleEl.value = currentStyle;
        }

        const statusText = document.getElementById('localAiStatusText');
        const statusBadge = document.getElementById('localAiStatusBadge');
        const pullBox = document.getElementById('localAiPullBox');
        const pullStatusText = document.getElementById('localAiPullStatusText');
        const pullPercent = document.getElementById('localAiPullPercent');
        const pullBar = document.getElementById('localAiPullBar');
        const actionBox = document.getElementById('localAiActionBox');
        const btnDownloadModel = document.getElementById('btnDownloadQwenModel');
        const btnSelectOffline = document.getElementById('btnSelectOfflineChoice');

        if (titleEl) titleEl.textContent = actionTitle;
        if (subTitleEl) subTitleEl.textContent = actionSubtitle;

        modal.style.display = 'flex';
        modal.classList.add('active');

        let currentLocalStatus = null;
        let isPulling = false;

        const checkStatus = async () => {
            try {
                if (statusText) statusText.textContent = '🔍 Đang kiểm tra Ollama & Mô hình Qwen 2.5...';
                if (statusBadge) {
                    statusBadge.textContent = 'Kiểm tra...';
                    statusBadge.style.background = '#334155';
                    statusBadge.style.color = '#94a3b8';
                }
                const res = await fetch('/api/local_ai/status');
                if (res.ok) {
                    const data = await res.json();
                    currentLocalStatus = data.status || {};
                    renderStatus(currentLocalStatus);
                } else {
                    if (statusText) statusText.textContent = '⚠️ Chưa kết nối được dịch vụ AI Cục bộ.';
                    if (statusBadge) {
                        statusBadge.textContent = 'Chưa sẵn sàng';
                        statusBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                        statusBadge.style.color = '#ef4444';
                    }
                }
            } catch (e) {
                if (statusText) statusText.textContent = '⚠️ Không thể kiểm tra trạng thái Offline.';
            }
        };

        const renderStatus = (st) => {
            if (!st) return;
            if (!st.installed) {
                if (statusText) statusText.innerHTML = '⚠️ Máy chưa cài Ollama. <a href="https://ollama.com/download" target="_blank" style="color: #38bdf8; text-decoration: underline;">Tải Ollama tại đây (ollama.com)</a>';
                if (statusBadge) {
                    statusBadge.textContent = 'Chưa cài Ollama';
                    statusBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                    statusBadge.style.color = '#f59e0b';
                }
                if (actionBox) actionBox.style.display = 'none';
                if (btnSelectOffline) btnSelectOffline.textContent = 'Cần cài Ollama';
                return;
            }

            if (st.has_qwen) {
                const modelName = st.recommended_model || 'qwen2.5:3b';
                if (statusText) statusText.innerHTML = `✅ Mô hình <strong>${modelName}</strong> đã sẵn sàng trên GPU NVIDIA!`;
                if (statusBadge) {
                    statusBadge.textContent = 'Sẵn sàng (GPU)';
                    statusBadge.style.background = 'rgba(34, 197, 94, 0.2)';
                    statusBadge.style.color = '#22c55e';
                }
                if (actionBox) actionBox.style.display = 'none';
                if (pullBox) pullBox.style.display = 'none';
                if (btnSelectOffline) btnSelectOffline.textContent = 'Chọn Offline (GPU)';
            } else {
                if (statusText) statusText.textContent = '💡 Đã có Ollama. Cần tải mô hình Qwen 2.5 3B (1.9GB) siêu tốc để chạy offline.';
                if (statusBadge) {
                    statusBadge.textContent = 'Chưa có Model';
                    statusBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                    statusBadge.style.color = '#f59e0b';
                }
                if (actionBox) actionBox.style.display = 'block';
                if (btnSelectOffline) btnSelectOffline.textContent = 'Tải Model trước';
            }
        };

        const startDownloadModel = async () => {
            if (isPulling) return;
            isPulling = true;
            if (actionBox) actionBox.style.display = 'none';
            if (pullBox) pullBox.style.display = 'flex';
            if (pullStatusText) pullStatusText.textContent = 'Đang tải mô hình Qwen 2.5 3B (1.9 GB)...';

            try {
                const response = await fetch('/api/local_ai/pull_model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name: 'qwen2.5:3b' })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith('data: ')) {
                            try {
                                const evt = JSON.parse(trimmed.slice(6));
                                if (evt.error) {
                                    if (pullStatusText) pullStatusText.textContent = `Lỗi: ${evt.error}`;
                                    break;
                                }
                                const pct = evt.percent || 0;
                                if (pullPercent) pullPercent.textContent = `${pct}%`;
                                if (pullBar) pullBar.style.width = `${pct}%`;
                                if (pullStatusText) pullStatusText.textContent = evt.status ? `${evt.status} (${pct}%)` : `Đang tải... ${pct}%`;
                                if (evt.status === 'success') {
                                    if (pullStatusText) pullStatusText.textContent = '✅ Đã tải xong Qwen 2.5 3B!';
                                    showToast('Tải thành công mô hình Qwen 2.5 3B về máy!', 'success');
                                    await checkStatus();
                                    break;
                                }
                            } catch (parseErr) {}
                        }
                    }
                }
            } catch (err) {
                if (pullStatusText) pullStatusText.textContent = `Lỗi tải: ${err.message}`;
            } finally {
                isPulling = false;
            }
        };

        const cleanup = (res) => {
            modal.style.display = 'none';
            modal.classList.remove('active');
            if (cardOnline) cardOnline.removeEventListener('click', onOnline);
            if (cardOffline) cardOffline.removeEventListener('click', onOffline);
            if (closeBtn) closeBtn.removeEventListener('click', onCancel);
            if (cancelBtn) cancelBtn.removeEventListener('click', onCancel);
            if (btnDownloadModel) btnDownloadModel.removeEventListener('click', onDownloadClick);
            modal.removeEventListener('click', onOverlay);

            if (res) {
                const chosenSrc = modalSrcEl ? modalSrcEl.value : 'auto';
                const chosenTgt = modalTgtEl ? modalTgtEl.value : 'vi';
                const chosenStyle = modalStyleEl ? modalStyleEl.value : 'cinema';
                res.source_lang = chosenSrc;
                res.target_lang = chosenTgt;
                res.translation_style = chosenStyle;

                // Sync with main UI
                if (mainSrcEl) mainSrcEl.value = chosenSrc;
                if (mainTgtEl) mainTgtEl.value = chosenTgt;
                if (bottomTgtEl) bottomTgtEl.value = chosenTgt;
                if (mainStyleEl) mainStyleEl.value = chosenStyle;
                if (bottomStyleEl) bottomStyleEl.value = chosenStyle;
                try { localStorage.setItem('novacut_translation_style', chosenStyle); } catch (e) {}
            }

            resolve(res);
        };

        const onOnline = () => cleanup({ engine: 'online' });
        const onOffline = () => {
            if (currentLocalStatus && currentLocalStatus.has_qwen) {
                cleanup({
                    engine: 'offline',
                    localModel: currentLocalStatus.recommended_model || 'qwen2.5:3b'
                });
            } else if (currentLocalStatus && !currentLocalStatus.installed) {
                if (typeof showAlertModal === 'function') {
                    showAlertModal('Chưa cài đặt Ollama', 'Vui lòng cài đặt Ollama để chạy mô hình AI dịch thuật cục bộ trên GPU. Truy cập: https://ollama.com');
                } else {
                    showToast('Vui lòng cài đặt Ollama để chạy Offline!', 'warning');
                }
            } else {
                startDownloadModel();
            }
        };
        const onCancel = () => cleanup(null);
        const onDownloadClick = (e) => {
            e.stopPropagation();
            startDownloadModel();
        };
        const onOverlay = (e) => { if (e.target === modal) cleanup(null); };

        if (cardOnline) cardOnline.addEventListener('click', onOnline);
        if (cardOffline) cardOffline.addEventListener('click', onOffline);
        if (closeBtn) closeBtn.addEventListener('click', onCancel);
        if (cancelBtn) cancelBtn.addEventListener('click', onCancel);
        if (btnDownloadModel) btnDownloadModel.addEventListener('click', onDownloadClick);
        modal.addEventListener('click', onOverlay);

        checkStatus();
    });
}

/**
 * Kiểm tra và hướng dẫn cấp API Key / Môi trường AI theo từng Gói cước (Pro / VIP / Yearly / Trial)
 */
export async function ensureAiKeyAvailable(keyType = 'openai', featureTitle = 'Tính năng AI') {
    let keyInputId = 'openaiKey';
    let keyName = 'OpenAI API Key (GPT / ChatGPT)';
    if (keyType === 'openspeaker' || keyType === 'tts') {
        keyInputId = 'openSpeakerApiKey';
        keyName = 'OpenSpeaker API Key';
    } else if (keyType === 'gemini') {
        keyInputId = 'geminiApiKey';
        keyName = 'Gemini API Key';
    }

    let keyVal = document.getElementById(keyInputId)?.value?.trim() || '';
    
    // 1. Thử đọc từ backend nếu input rỗng
    if (!keyVal) {
        try {
            const keysRes = await fetch('/api/get_api_keys');
            if (keysRes.ok) {
                const keysData = await keysRes.json();
                keyVal = keysData[keyInputId] || keysData[keyType + '_key'] || keysData[keyType + 'Key'] || '';
                if (keyVal && document.getElementById(keyInputId)) {
                    document.getElementById(keyInputId).value = keyVal;
                }
            }
        } catch (e) {}
    }

    // 2. Nếu là Gói VIP hoặc Gói Năm, tự động đồng bộ từ Google Cloud Sheet về nếu chưa có
    const currentTier = (currentLicenseState && currentLicenseState.tier) ? currentLicenseState.tier : 'unlicensed';
    if (!keyVal && (currentTier === 'vip' || currentTier === 'yearly')) {
        try {
            appendLog('🔄 Đang tự động đồng bộ API Key Gói VIP từ Google Cloud Sheet...', 'info');
            const syncRes = await fetch('/api/license/sync_cloud', { method: 'POST' });
            if (syncRes.ok) {
                const syncData = await syncRes.json();
                if (syncData.license && syncData.license.vip_api_keys) {
                    const vk = syncData.license.vip_api_keys;
                    keyVal = vk[keyInputId] || vk[keyType + '_key'] || vk[keyType + 'Key'] || vk.openaiKey || vk.api_key || '';
                    if (keyVal && document.getElementById(keyInputId)) {
                        document.getElementById(keyInputId).value = keyVal;
                    }
                }
            }
        } catch (syncErr) {}
    }

    // Nếu đã có Key hợp lệ -> Cho phép tiếp tục ngay
    if (keyVal && keyVal.length > 5) {
        return true;
    }

    // 3. Xử lý thông báo chuyên biệt theo từng gói cước
    const planName = (currentLicenseState && currentLicenseState.plan_name) ? currentLicenseState.plan_name : 'Bản quyền';
    const settingsModal = document.getElementById('settingsModal');
    const licenseModal = document.getElementById('licenseModal');

    if (currentTier === 'vip' || currentTier === 'yearly') {
        await showAlertModal({
            title: `⭐ ${planName} - Cấp API Bản Quyền`,
            icon: '⭐',
            type: 'primary',
            message: `Gói <strong>${planName}</strong> của bạn được <strong>tặng kèm trọn bộ API AI bản quyền</strong> hệ thống.<br><br>Hiện tại ứng dụng chưa nhận diện được API Key cấp riêng cho máy bạn hoặc kết nối máy chủ Google Sheet vừa khởi tạo.<br><br>👉 Vui lòng bấm <strong>[Đồng Bộ Bản Quyền]</strong> để tải lại Key, hoặc liên hệ ngay <strong>Admin Zalo/Telegram</strong> để được cấp API Key mới 1-Click ngay lập tức!`,
            buttons: [
                {
                    text: '🔄 Đồng Bộ Bản Quyền Ngay',
                    primary: true,
                    onClick: async () => {
                        showToast('Đang kết nối máy chủ để đồng bộ lại API Key...', 'info');
                        const syncBtn = document.getElementById('btnSyncLicenseCloud');
                        if (syncBtn) syncBtn.click();
                        else if (licenseModal) licenseModal.style.display = 'flex';
                    }
                },
                {
                    text: '💬 Mở Zalo Admin',
                    primary: false,
                    onClick: () => {
                        window.open('https://zalo.me', '_blank');
                    }
                }
            ]
        });
        return false;
    } else if (currentTier === 'pro') {
        await showAlertModal({
            title: `⚠️ Yêu cầu API Key (${featureTitle})`,
            icon: '🔑',
            type: 'warning',
            message: `Gói <strong>Pro</strong> sử dụng API Key cá nhân của bạn để tối ưu chi phí sử dụng.<br><br>Bạn chưa cấu hình <strong>${keyName}</strong> trong ứng dụng.<br><br>👉 Vui lòng vào <strong>Cài đặt (⚙️)</strong> để nhập API Key của bạn (OpenAI GPT, Gemini, Claude, DeepSeek), hoặc nâng cấp lên <strong>Gói VIP / Gói Năm</strong> để được cấp sẵn API Key hệ thống không giới hạn!`,
            buttons: [
                {
                    text: '⚙️ Mở Cài Đặt (Nhập Key)',
                    primary: true,
                    onClick: () => {
                        if (settingsModal) {
                            settingsModal.style.display = 'flex';
                            const inputEl = document.getElementById(keyInputId);
                            if (inputEl) {
                                inputEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                inputEl.focus();
                            }
                        }
                    }
                },
                {
                    text: '⭐ Nâng Cấp Gói VIP',
                    primary: false,
                    onClick: () => {
                        if (licenseModal) licenseModal.style.display = 'flex';
                    }
                }
            ]
        });
        return false;
    } else {
        await showAlertModal({
            title: `⚡ Yêu cầu API Key (${featureTitle})`,
            icon: '🔑',
            type: 'warning',
            message: `Bạn chưa cấu hình <strong>${keyName}</strong>.<br><br>👉 Vui lòng vào <strong>Cài đặt (⚙️)</strong> để nhập API Key cá nhân của bạn, hoặc kích hoạt <strong>Gói VIP / Gói Năm</strong> để được cấp sẵn API Key AI bản quyền không giới hạn!`,
            buttons: [
                {
                    text: '⚙️ Mở Cài Đặt (Nhập Key)',
                    primary: true,
                    onClick: () => {
                        if (settingsModal) settingsModal.style.display = 'flex';
                    }
                },
                {
                    text: '⭐ Bảng Bản Quyền & Nâng Cấp',
                    primary: false,
                    onClick: () => {
                        if (licenseModal) licenseModal.style.display = 'flex';
                    }
                }
            ]
        });
        return false;
    }
}

// --- OPENAI TOKEN TRACKER SYSTEM ---
const tokenTracker = {
    stats: {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        requests: 0,
        history: []
    },
    
    init() {
        try {
            const saved = localStorage.getItem('openai_token_stats');
            if (saved) {
                this.stats = JSON.parse(saved);
            }
        } catch (e) {}
        this.fetchServerQuota();
        this.bindEvents();
    },

    async fetchServerQuota() {
        try {
            const res = await fetch('/api/license/token_quota');
            if (res.ok) {
                const data = await res.json();
                this.stats.prompt_tokens = data.prompt_tokens || 0;
                this.stats.completion_tokens = data.completion_tokens || 0;
                this.stats.total_tokens = data.total_tokens || (this.stats.prompt_tokens + this.stats.completion_tokens);
                this.stats.requests = data.requests || 0;
                this.save();
                this.updateUI();
            }
        } catch (e) {
            this.updateUI();
        }
    },
    
    save() {
        try {
            localStorage.setItem('openai_token_stats', JSON.stringify(this.stats));
        } catch (e) {}
    },
    
    record(taskName, usage, model = 'gpt-5.6-luna') {
        if (!usage || typeof usage !== 'object') return;
        const p = parseInt(usage.prompt_tokens) || 0;
        const c = parseInt(usage.completion_tokens) || 0;
        const t = parseInt(usage.total_tokens) || (p + c);
        
        if (t === 0) return;
        
        this.stats.prompt_tokens += p;
        this.stats.completion_tokens += c;
        this.stats.total_tokens += t;
        this.stats.requests += 1;
        
        // Calculate cost estimate ($0.15/1M input, $0.60/1M output for gpt-4o-mini standard)
        const costUSD = (p * 0.15 / 1000000) + (c * 0.60 / 1000000);
        
        if (!this.stats.history) this.stats.history = [];
        this.stats.history.unshift({
            time: new Date().toLocaleTimeString(),
            task: taskName,
            model: model,
            prompt_tokens: p,
            completion_tokens: c,
            total_tokens: t,
            costUSD: costUSD
        });
        
        if (this.stats.history.length > 50) this.stats.history.pop();
        
        this.save();
        this.updateUI();
        
        // Log to terminal
        appendLog(`[${new Date().toLocaleTimeString()}] > [Token AI] 🪙 ${taskName}: Đã dùng ${t.toLocaleString()} tokens (Prompt: ${p.toLocaleString()}, Output: ${c.toLocaleString()}) ~ $${costUSD.toFixed(5)} USD`, 'info');
    },
    
    async reset() {
        try {
            await fetch('/api/license/token_quota/reset', { method: 'POST' });
        } catch (e) {}
        this.stats = {
            prompt_tokens: 0,
            completion_tokens: 0,
            total_tokens: 0,
            requests: 0,
            history: []
        };
        this.save();
        this.updateUI();
        showToast('Đã đặt lại bộ đếm token về 0!', 'info');
    },
    
    updateUI() {
        const badgeCount = document.getElementById('tokenBadgeCount');
        if (badgeCount) {
            badgeCount.textContent = this.stats.total_tokens.toLocaleString();
        }
        
        const statTotal = document.getElementById('tokenStatTotal');
        if (statTotal) statTotal.textContent = this.stats.total_tokens.toLocaleString();
        
        const statPrompt = document.getElementById('tokenStatPrompt');
        if (statPrompt) statPrompt.textContent = this.stats.prompt_tokens.toLocaleString();
        
        const statCompletion = document.getElementById('tokenStatCompletion');
        if (statCompletion) statCompletion.textContent = this.stats.completion_tokens.toLocaleString();
        
        const statRequests = document.getElementById('tokenStatRequests');
        if (statRequests) statRequests.textContent = `${this.stats.requests.toLocaleString()} lần`;
        
        const costUSD = (this.stats.prompt_tokens * 0.15 / 1000000) + (this.stats.completion_tokens * 0.60 / 1000000);
        const costVND = Math.round(costUSD * 25400);
        const statCost = document.getElementById('tokenStatCost');
        if (statCost) {
            statCost.textContent = `Ước tính chi phí: ~$${costUSD.toFixed(4)} USD (${costVND.toLocaleString()} đ)`;
        }

        // Unlimited Token Quota
        const promptPctElem = document.getElementById('tokenPromptPct');
        if (promptPctElem) promptPctElem.textContent = 'Unlimited';

        const completionPctElem = document.getElementById('tokenCompletionPct');
        if (completionPctElem) completionPctElem.textContent = 'Unlimited';

        const promptPctNum = 100;
        const completionPctNum = 100;

        const promptBar = document.getElementById('tokenPromptProgressBar');
        if (promptBar) {
            promptBar.style.width = `${promptPctNum}%`;
            if (promptPctNum >= 100) {
                promptBar.style.background = '#ef4444';
            } else if (promptPctNum >= 80) {
                promptBar.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
            } else {
                promptBar.style.background = 'linear-gradient(90deg, #0ea5e9, #38bdf8)';
            }
        }

        const completionBar = document.getElementById('tokenCompletionProgressBar');
        if (completionBar) {
            completionBar.style.width = `${completionPctNum}%`;
            if (completionPctNum >= 100) {
                completionBar.style.background = '#ef4444';
            } else if (completionPctNum >= 80) {
                completionBar.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
            } else {
                completionBar.style.background = 'linear-gradient(90deg, #a855f7, #c084fc)';
            }
        }
    },
    
    bindEvents() {
        const badge = document.getElementById('tokenUsageBadge');
        const modal = document.getElementById('tokenStatsModal');
        const closeBtn = document.getElementById('btnCloseTokenStats');
        const closeFooterBtn = document.getElementById('btnCloseTokenStatsFooter');
        const resetBtn = document.getElementById('btnResetTokenStats');
        
        if (badge && modal) {
            badge.addEventListener('click', () => {
                this.fetchServerQuota();
                this.updateUI();
                modal.style.display = 'flex';
            });
        }
        if (closeBtn && modal) {
            closeBtn.addEventListener('click', () => modal.style.display = 'none');
        }
        if (closeFooterBtn && modal) {
            closeFooterBtn.addEventListener('click', () => modal.style.display = 'none');
        }
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.style.display = 'none';
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.reset());
        }
    }
};

tokenTracker.init();

// --- Translate Subtitles Logic ---
const btnTranslateSrt = document.getElementById('btnTranslateSrt');
const btnTranslateAI = document.getElementById('btnTranslateAI');
const btnStopTranslate = document.getElementById('btnStopTranslate');

let translateAbortController = null;
let isTranslatingCancelled = false;

if (btnStopTranslate) {
    btnStopTranslate.addEventListener('click', () => {
        isTranslatingCancelled = true;
        if (translateAbortController) {
            translateAbortController.abort();
        }
        showToast('⏹️ Đang dừng dịch theo yêu cầu...', 'info');
    });
}

/**
 * Hộp thoại lựa chọn 3 phương án:
 * 1. 'translate': Chỉ dịch phụ đề
 * 2. 'clean': Chỉ làm sạch SRT
 * 3. 'both': Cả dịch và làm sạch (Làm sạch trước -> Dịch sau)
 */
function promptTranslateCleanAction() {
    return new Promise((resolve) => {
        const modal = document.getElementById('translateCleanSelectionModal');
        if (!modal) {
            resolve('translate');
            return;
        }

        const cardBoth = document.getElementById('cardChoiceBoth');
        const cardTranslate = document.getElementById('cardChoiceTranslate');
        const cardClean = document.getElementById('cardChoiceClean');
        const closeBtn = document.getElementById('closeTranslateCleanModalBtn');
        const cancelBtn = document.getElementById('cancelTranslateCleanModalBtn');

        modal.style.display = 'flex';
        modal.classList.add('active');

        const cleanup = () => {
            modal.style.display = 'none';
            modal.classList.remove('active');
            if (cardBoth) cardBoth.onclick = null;
            if (cardTranslate) cardTranslate.onclick = null;
            if (cardClean) cardClean.onclick = null;
            if (closeBtn) closeBtn.onclick = null;
            if (cancelBtn) cancelBtn.onclick = null;
            modal.onclick = null;
        };

        if (cardBoth) {
            cardBoth.onclick = () => {
                cleanup();
                resolve('both');
            };
        }
        if (cardTranslate) {
            cardTranslate.onclick = () => {
                cleanup();
                resolve('translate');
            };
        }
        if (cardClean) {
            cardClean.onclick = () => {
                cleanup();
                resolve('clean');
            };
        }

        if (closeBtn) closeBtn.onclick = () => { cleanup(); resolve(null); };
        if (cancelBtn) cancelBtn.onclick = () => { cleanup(); resolve(null); };

        modal.onclick = (e) => {
            if (e.target === modal) {
                cleanup();
                resolve(null);
            }
        };
    });
}

/**
 * Hàm làm sạch phụ đề AI (có thể gọi độc lập hoặc gọi trong luồng 'both')
 * Trả về true nếu làm sạch thành công, false nếu có lỗi hoặc người dùng hủy
 */
async function executeCleanSubtitles(options = {}) {
    if (!checkFeaturePermission('can_access_editor', 'Làm sạch phụ đề')) return false;
    if (!srtData || srtData.length === 0) {
        showToast('Không có phụ đề nào để làm sạch!', 'warning');
        return false;
    }

    let aiChoice = options.aiChoice;
    if (!aiChoice) {
        aiChoice = await promptAiExecutionMode(
            options.promptTitle || 'Làm sạch phụ đề (AI)',
            options.promptSubtitle || 'Lọc trùng OCR, sửa câu và chuẩn hóa mốc thời gian'
        );
        if (!aiChoice) return false;
    }

    const isOffline = aiChoice.engine === 'offline';
    const localModel = aiChoice.localModel || 'qwen2.5:7b';

    let openaiKey = '';
    let openaiBaseUrl = 'https://api.openai.com/v1';
    let openaiModel = 'gpt-5.6-luna-pro-batch';

    if (!isOffline) {
        const hasKey = await ensureAiKeyAvailable('openai', 'Làm sạch phụ đề AI');
        if (!hasKey) return false;
        openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
        openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
        
        // Theo yêu cầu: Phần làm sạch phụ đề Online LUÔN gọi GPT Luna
        if (openaiBaseUrl.includes('openrouter.ai') || openaiKey.startsWith('sk-or-')) {
            openaiModel = 'openai/gpt-5.6-luna-pro';
        } else {
            openaiModel = 'gpt-5.6-luna-pro-batch';
        }
    }

    const totalSubs = srtData.length;
    const timeNow = () => new Date().toLocaleTimeString();
    const btnTarget = btnCleanSrtAI || btnTranslateSrt;
    const origHtml = btnTarget ? btnTarget.innerHTML : '';
    if (btnCleanSrtAI) btnCleanSrtAI.disabled = true;
    if (btnTranslateSrt) btnTranslateSrt.disabled = true;
    if (btnStopCleanSrtAI) {
        btnStopCleanSrtAI.style.display = 'inline-flex';
    }

    if (terminalOverlay && terminalOverlay.classList.contains('collapsed')) {
        terminalOverlay.classList.remove('collapsed');
        terminalOverlay.classList.add('expanded');
        if (toggleTerminalBtn) toggleTerminalBtn.textContent = 'Thu gọn';
    }

    const modeDesc = isOffline ? `Local GPU (${localModel})` : `Cloud AI (GPT-5.6 Luna)`;
    appendLog(`[${timeNow()}] > [Làm sạch SRT] Bắt đầu gộp và làm sạch ${totalSubs} đoạn phụ đề bằng ${modeDesc}...`, 'info');
    showToast(`Bắt đầu làm sạch phụ đề bằng ${modeDesc}...`, 'info');

    cleanSrtAbortController = new AbortController();
    isCleanSrtCancelled = false;

    // ═══════════════════════════════════════════════════════════════════
    //  CÁCH 1: CHIA MẺ THEO KHOẢNG LẶNG & CHẠY SONG SONG 3 LUỒNG
    //  - Tự động cắt mẻ tại khoảng lặng âm thanh (silence gap >= 1.2s)
    //  - Đảm bảo 2 bên điểm cắt không bao giờ bị đứt câu thoại dở
    //  - 3 Worker chạy song song giúp tăng tốc gấp 3 lần!
    // ═══════════════════════════════════════════════════════════════════
    const splitSubtitlesBySilence = (subs, targetSize = 150, minSize = 90, maxSize = 220, silenceThresholdSec = 1.2) => {
        const chunks = [];
        const total = subs.length;
        if (total <= maxSize) {
            return [{ chunkIndex: 0, chunk: subs, from: 1, to: total }];
        }

        let startIdx = 0;
        while (startIdx < total) {
            const remaining = total - startIdx;
            if (remaining <= maxSize) {
                chunks.push({
                    chunkIndex: chunks.length,
                    chunk: subs.slice(startIdx),
                    from: startIdx + 1,
                    to: total
                });
                break;
            }

            let bestCutIdx = Math.min(startIdx + targetSize, total);
            let maxGap = -1;
            const searchEnd = Math.min(startIdx + maxSize, total - 1);

            for (let i = startIdx + minSize; i <= searchEnd; i++) {
                const curSub = subs[i - 1];
                const nextSub = subs[i];
                const curEnd = parseFloat(curSub.endSeconds || curSub.end || 0);
                const nextStart = parseFloat(nextSub.startSeconds || nextSub.start || 0);
                const gap = nextStart - curEnd;

                if (gap >= silenceThresholdSec) {
                    bestCutIdx = i;
                    maxGap = gap;
                    break;
                }
                if (gap > maxGap) {
                    maxGap = gap;
                    bestCutIdx = i;
                }
            }

            chunks.push({
                chunkIndex: chunks.length,
                chunk: subs.slice(startIdx, bestCutIdx),
                from: startIdx + 1,
                to: bestCutIdx
            });
            startIdx = bestCutIdx;
        }
        return chunks;
    };

    const allChunks = splitSubtitlesBySilence(srtData, 150, 90, 220, 1.2);
    const CONCURRENCY = isOffline ? 1 : Math.min(3, allChunks.length);
    const resultsByChunk = new Array(allChunks.length);
    let queueIdx = 0;
    let processedCount = 0;
    let totalCleanTokens = 0;
    let hasError = false;
    let isSuccess = false;

    appendLog(`[${timeNow()}] > [Làm sạch SRT] Đã phân tích timeline thành ${allChunks.length} mẻ theo khoảng lặng cảnh. Kích hoạt ${CONCURRENCY} luồng song song...`, 'info');

    const updateProgressUI = () => {
        const percent = Math.min(99, Math.round((processedCount / totalSubs) * 100));
        const progressHtml = `
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
            <span>Đang làm sạch (${percent}% - ${processedCount}/${totalSubs})...</span>
        `;
        if (btnCleanSrtAI) btnCleanSrtAI.innerHTML = progressHtml;
        if (btnTranslateSrt) btnTranslateSrt.innerHTML = progressHtml;
    };

    const runCleanWorker = async (workerId) => {
        const MAX_CLEAN_RETRIES = 3;
        while (queueIdx < allChunks.length && !isCleanSrtCancelled && !hasError) {
            const task = allChunks[queueIdx++];
            const chunkFrom = task.from;
            const chunkTo = task.to;
            const chunkIndex = task.chunkIndex;

            let chunkSuccess = false;
            for (let attempt = 1; attempt <= MAX_CLEAN_RETRIES; attempt++) {
                if (isCleanSrtCancelled || hasError) break;

                try {
                    const res = await fetch('/api/clean_subtitles_ai', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            subtitles: task.chunk,
                            engine: isOffline ? 'offline' : 'online',
                            local_model: isOffline ? localModel : undefined,
                            openai_key: (!isOffline && openaiKey && !openaiKey.startsWith('•')) ? openaiKey : undefined,
                            openai_base_url: !isOffline ? openaiBaseUrl : undefined,
                            openai_model: !isOffline ? openaiModel : undefined
                        }),
                        signal: cleanSrtAbortController.signal
                    });

                    if (!res.ok) {
                        const errText = await res.text();
                        let errMsg = `Mã lỗi HTTP ${res.status}`;
                        try {
                            const errJson = JSON.parse(errText);
                            if (errJson.error) errMsg = typeof errJson.error === 'string' ? errJson.error : (errJson.error.message || JSON.stringify(errJson.error));
                            else if (errJson.message) errMsg = errJson.message;
                        } catch (e) {
                            if (res.status === 405 || res.status === 404) {
                                errMsg = "Máy chủ Python đang chạy phiên bản cũ. Vui lòng khởi động lại 'python web_app.py'!";
                            } else if (res.status === 500) {
                                errMsg = "Máy chủ AI / OpenRouter tạm thời quá tải (HTTP 500)";
                            }
                        }

                        if (attempt < MAX_CLEAN_RETRIES && !isCleanSrtCancelled) {
                            const waitSec = attempt * 2;
                            appendLog(`[${timeNow()}] > [Làm sạch SRT] ⚠️ Mẻ ${chunkIndex + 1} (${chunkFrom}-${chunkTo}): ${errMsg}. Tự động thử lại lần ${attempt + 1}/${MAX_CLEAN_RETRIES} sau ${waitSec}s...`, 'warning');
                            await new Promise(r => setTimeout(r, waitSec * 1000));
                            continue;
                        } else {
                            appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Mẻ ${chunkIndex + 1} (${chunkFrom}-${chunkTo}): ${errMsg}`, 'error');
                            showToast(`Lỗi làm sạch mẻ ${chunkIndex + 1}: ${errMsg}`, 'error');
                            hasError = true;
                            break;
                        }
                    }

                    const data = await res.json();
                    if (data.error) {
                        if (attempt < MAX_CLEAN_RETRIES && !isCleanSrtCancelled) {
                            const waitSec = attempt * 2;
                            appendLog(`[${timeNow()}] > [Làm sạch SRT] ⚠️ Mẻ ${chunkIndex + 1} (${chunkFrom}-${chunkTo}): ${data.error}. Tự động thử lại lần ${attempt + 1}/${MAX_CLEAN_RETRIES} sau ${waitSec}s...`, 'warning');
                            await new Promise(r => setTimeout(r, waitSec * 1000));
                            continue;
                        } else {
                            appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Mẻ ${chunkIndex + 1} (${chunkFrom}-${chunkTo}): ${data.error}`, 'error');
                            showToast(`Lỗi làm sạch SRT: ${data.error}`, 'error');
                            hasError = true;
                            break;
                        }
                    }

                    if (data.usage && !isOffline) {
                        tokenTracker.record(`Làm sạch mẻ ${chunkIndex + 1}`, data.usage, 'gpt-5.6-luna');
                        totalCleanTokens += (data.usage.total_tokens || 0);
                    }

                    if (data.subtitles && Array.isArray(data.subtitles)) {
                        resultsByChunk[chunkIndex] = data.subtitles;
                        processedCount += task.chunk.length;
                        updateProgressUI();
                        appendLog(`[${timeNow()}] > [Làm sạch SRT] [Luồng ${workerId}] ✅ Xong mẻ ${chunkIndex + 1}/${allChunks.length} (${task.chunk.length} câu vụn -> ${data.subtitles.length} câu hoàn chỉnh)`, 'info');
                    } else {
                        resultsByChunk[chunkIndex] = task.chunk;
                        processedCount += task.chunk.length;
                    }
                    chunkSuccess = true;
                    break;
                } catch (fetchErr) {
                    if (isCleanSrtCancelled || fetchErr.name === 'AbortError') {
                        break;
                    }
                    if (attempt < MAX_CLEAN_RETRIES) {
                        const waitSec = attempt * 2;
                        appendLog(`[${timeNow()}] > [Làm sạch SRT] ⚠️ Luồng ${workerId} mẻ ${chunkIndex + 1} bị ngắt (${fetchErr.message}). Tự động thử lại lần ${attempt + 1}/${MAX_CLEAN_RETRIES} sau ${waitSec}s...`, 'warning');
                        await new Promise(r => setTimeout(r, waitSec * 1000));
                    } else {
                        appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Luồng ${workerId} mẻ ${chunkIndex + 1}: ${fetchErr.message}`, 'error');
                        hasError = true;
                        break;
                    }
                }
            }
        }
    };

    try {
        const workers = [];
        for (let w = 0; w < CONCURRENCY; w++) {
            workers.push(runCleanWorker(w + 1));
        }
        await Promise.all(workers);

        if (isCleanSrtCancelled) {
            let partialCleaned = [];
            for (let c = 0; c < allChunks.length; c++) {
                if (resultsByChunk[c] && resultsByChunk[c].length > 0) {
                    partialCleaned = partialCleaned.concat(resultsByChunk[c]);
                } else {
                    partialCleaned = partialCleaned.concat(allChunks[c].chunk);
                }
            }
            srtData = partialCleaned.map((item, idx) => ({
                ...item,
                id: String(idx + 1)
            }));
            renderSrtTable();
            appendLog(`[${timeNow()}] > [Làm sạch SRT] ⏹️ Đã dừng làm sạch AI theo yêu cầu! Đã giữ lại các đoạn đã làm sạch.`, 'warning');
            showToast(`Đã dừng làm sạch! Đã lưu lại tiến độ.`, 'info');
            isSuccess = false;
        } else if (!hasError && resultsByChunk.some(arr => arr && arr.length > 0)) {
            let finalCleaned = [];
            for (let c = 0; c < allChunks.length; c++) {
                if (resultsByChunk[c] && resultsByChunk[c].length > 0) {
                    finalCleaned = finalCleaned.concat(resultsByChunk[c]);
                } else {
                    finalCleaned = finalCleaned.concat(allChunks[c].chunk);
                }
            }
            const oldCount = srtData.length;
            srtData = finalCleaned.map((item, idx) => ({
                ...item,
                id: String(idx + 1)
            }));
            renderSrtTable();
            const tokenSummary = totalCleanTokens > 0 ? ` (🪙 Tổng token: ${totalCleanTokens.toLocaleString()})` : '';
            appendLog(`[${timeNow()}] > [Làm sạch SRT] 🎉 Hoàn tất siêu tốc! Đã làm sạch song song ${allChunks.length} mẻ: từ ${oldCount} đoạn vụn thành ${srtData.length} câu hoàn chỉnh${tokenSummary}.`, 'success');
            showToast(`Đã làm sạch & gộp thành công ${srtData.length} câu!`, 'success');
            isSuccess = true;
        } else if (!hasError) {
            showToast('Không có câu phụ đề nào được tạo ra!', 'warning');
            isSuccess = false;
        }
    } catch (err) {
        if (!isCleanSrtCancelled && err.name !== 'AbortError') {
            console.error(err);
            appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Lỗi kết nối: ${err.message}`, 'error');
            showToast('Lỗi kết nối khi làm sạch phụ đề: ' + err.message, 'error');
        }
        isSuccess = false;
    } finally {
        isCleanSrtCancelled = false;
        cleanSrtAbortController = null;
        if (btnCleanSrtAI) {
            btnCleanSrtAI.disabled = false;
            btnCleanSrtAI.innerHTML = origHtml;
        }
        if (btnTranslateSrt) {
            btnTranslateSrt.disabled = false;
            btnTranslateSrt.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M5 12h14"></path><path d="M12 5l7 7-7 7"></path></svg><span>🌐 Dịch & Làm sạch SRT</span>`;
        }
        if (btnStopCleanSrtAI) {
            btnStopCleanSrtAI.style.display = 'none';
        }
    }
    return isSuccess;
}

/**
 * Hàm điều phối chung khi người dùng bấm nút '🌐 Dịch & Làm sạch SRT'
 * Cho phép lựa chọn 3 tác vụ:
 * 1. Chỉ dịch phụ đề ('translate')
 * 2. Chỉ làm sạch phụ đề ('clean')
 * 3. Cả dịch và làm sạch ('both')
 */
async function handleTranslateAndCleanUnified() {
    if (!checkFeaturePermission('can_access_editor', 'Dịch & Làm sạch SRT')) return;

    if (!srtData || srtData.length === 0) {
        showToast('Không có phụ đề nào để xử lý!', 'warning');
        return;
    }

    const action = await promptTranslateCleanAction();
    if (!action) return; // Người dùng đóng/hủy modal

    if (action === 'clean') {
        // Tác vụ 2: Chỉ làm sạch SRT (gọi GPT Luna)
        await executeCleanSubtitles();
    } else if (action === 'translate') {
        // Tác vụ 1: Chỉ dịch phụ đề (mặc định Qwen 3.7 Flash)
        await handleTranslateSubtitles('ai');
    } else if (action === 'both') {
        // Tác vụ 3: Cả Dịch và Làm sạch
        // Bước 1: Hỏi cấu hình chế độ AI / Dịch (Offline GPU hay Online Cloud AI)
        const aiChoice = await promptAiExecutionMode(
            'Cả Dịch & Làm Sạch SRT (Khuyên Dùng)',
            'Bước 1: Làm sạch & chuẩn hóa mốc thời gian -> Bước 2: Dịch toàn bộ phụ đề sang ngôn ngữ đích',
            { showLanguageOptions: true }
        );
        if (!aiChoice) return;

        appendLog(`[${new Date().toLocaleTimeString()}] > [Quy trình Đồng Bộ] 🚀 BẮT ĐẦU: Bước 1/2: Làm sạch & Chuẩn hóa SRT bằng GPT Luna...`, 'info');
        showToast('🚀 Bước 1/2: Đang làm sạch và gộp câu phụ đề bằng GPT Luna...', 'info');

        const cleanOk = await executeCleanSubtitles({
            aiChoice: aiChoice
        });

        if (!cleanOk) {
            appendLog(`[${new Date().toLocaleTimeString()}] > [Quy trình Đồng Bộ] ⚠️ Quy trình dừng lại sau Bước 1 (do hủy hoặc có lỗi làm sạch).`, 'warning');
            return;
        }

        // Bước 2: Dịch toàn bộ srtData đã được làm sạch bằng AI (Qwen)
        appendLog(`[${new Date().toLocaleTimeString()}] > [Quy trình Đồng Bộ] 🌐 BẮT ĐẦU: Bước 2/2: Dịch toàn bộ ${srtData.length} câu đã chuẩn hóa bằng Qwen...`, 'info');
        showToast('🌐 Bước 2/2: Đang dịch các câu đã làm sạch bằng Qwen sang ngôn ngữ đích...', 'info');

        await handleTranslateSubtitles('ai', {
            aiChoice: aiChoice,
            skipConfirm: true
        });

        showToast('🎉 Hoàn tất trọn vẹn cả Làm sạch & Dịch phụ đề!', 'success');
    }
}

// Central Translation Configuration
const DEFAULT_TRANSLATION_CONFIG = {
    model: "qwen/qwen3.7-flash",
    chunkSize: 80,
    concurrency: 3,
    maxRetries: 3,
    requestTimeout: 60000,
    contextLines: 6,
    providerRouting: "throughput"
};

async function handleTranslateSubtitles(mode = 'ai', options = {}) {
    if (!checkFeaturePermission('can_access_editor', 'Dịch phụ đề')) return;

    if (!srtData || srtData.length === 0) {
        showToast('Không có phụ đề nào để dịch!', 'warning');
        return;
    }
    
    const selectedSubs = srtData.filter(s => s.selected);
    let targetSubs = selectedSubs.length > 0 ? selectedSubs : srtData;

    // HỎI NGƯỜI DÙNG: ONLINE HAY OFFLINE? (Nếu chưa có aiChoice truyền từ ngoài)
    let aiChoice = options.aiChoice;
    if (!aiChoice) {
        aiChoice = await promptAiExecutionMode('Dịch phụ đề', 'Chọn dịch trực tuyến Online (Qwen3.7 Flash siêu tốc) hoặc dịch cục bộ Offline (Qwen 2.5 trên GPU RTX)', { showLanguageOptions: true });
        if (!aiChoice) return; // Người dùng hủy/đóng modal
    }

    const isOffline = aiChoice.engine === 'offline';
    const localModel = aiChoice.localModel || 'qwen2.5:7b';
    let execMode = isOffline ? 'local' : 'ai';

    const subSourceLangEl = document.getElementById('subSourceLang');
    const subTargetLangEl = document.getElementById('subTargetLang');
    const subTranslationStyleEl = document.getElementById('subTranslationStyle');
    const source_lang = aiChoice.source_lang || (subSourceLangEl ? subSourceLangEl.value : 'auto');
    const target_lang = aiChoice.target_lang || (subTargetLangEl ? subTargetLangEl.value : 'vi');
    const translation_style = aiChoice.translation_style || 
        (subTranslationStyleEl ? subTranslationStyleEl.value : null) || 
        localStorage.getItem('novacut_translation_style') || 'cinema';

    const styleLabels = {
        'cinema': '🎬 Chuẩn Điện Ảnh',
        'street_raw': '🍻 Dân Dã / Đường Phố / Thô Tục Nhẹ',
        'historical': '⚔️ Cổ Trang / Kiếm Hiệp',
        'humorous_bua': '😂 Hài Hước / Bựa / Lầy',
        'romance': '💖 Ngôn Tình / Lãng Mạn',
        'formal': '📜 Nghiêm Túc / Chính Kịch'
    };
    const styleDisplayName = styleLabels[translation_style] || translation_style;
    
    if (isOffline) {
        // Chạy hoàn toàn trên GPU máy tính, không trừ quota token và không cần API Key
    } else if (execMode === 'ai') {
        const hasKey = await ensureAiKeyAvailable('openai', 'Dịch phụ đề AI');
        if (!hasKey) return;

        if (!options.skipConfirm) {
            const choice = await showAiTranslateChoiceModal(targetSubs.length);
            if (!choice) return; // User cancelled
            
            if (choice === '20') {
                targetSubs = targetSubs.slice(0, 20);
            }
        }
    }
    
    const totalSubs = targetSubs.length;
    
    const langNames = {
        'vi': 'Tiếng Việt', 'en': 'Tiếng Anh', 'zh': 'Tiếng Trung', 'ja': 'Tiếng Nhật',
        'ko': 'Tiếng Hàn', 'fr': 'Tiếng Pháp', 'es': 'Tiếng Tây Ban Nha', 'de': 'Tiếng Đức',
        'ru': 'Tiếng Nga', 'th': 'Tiếng Thái'
    };
    const targetLangName = langNames[target_lang] || target_lang;

    const currentConfigModel = document.getElementById('openaiModel')?.value?.trim() || DEFAULT_TRANSLATION_CONFIG.model;
    let displayModelName = 'Qwen 3.7 Flash';
    if (currentConfigModel.toLowerCase().includes('qwen') && !currentConfigModel.includes('3.7-flash')) {
        displayModelName = currentConfigModel;
    }

    let modeLabel = 'Google Dịch (Miễn phí)';
    if (isOffline) {
        modeLabel = `GPU Offline (${localModel})`;
    } else if (execMode === 'ai') {
        modeLabel = totalSubs <= 20 ? `AI (${displayModelName} - 20 câu)` : `AI (${displayModelName})`;
    } else {
        modeLabel = 'Google Dịch (Miễn phí)';
    }

    const targetBtn = execMode === 'free' ? btnTranslateSrt : btnTranslateAI;
    const origHtml = targetBtn ? targetBtn.innerHTML : '';
    
    // Auto-open Terminal / System Log so user sees live progress
    if (terminalOverlay && terminalOverlay.classList.contains('collapsed')) {
        terminalOverlay.classList.remove('collapsed');
        terminalOverlay.classList.add('expanded');
        if (toggleTerminalBtn) toggleTerminalBtn.textContent = 'Thu gọn';
    }
    
    const timeNow = () => new Date().toLocaleTimeString();
    appendLog(`[${timeNow()}] > [Dịch thuật] Bắt đầu dịch ${totalSubs} câu phụ đề sang ${targetLangName} bằng ${modeLabel} [Phong cách: ${styleDisplayName}]...`, 'info');
    
    if (targetBtn) {
        targetBtn.disabled = true;
    }
    if (btnTranslateSrt) btnTranslateSrt.disabled = true;
    if (btnTranslateAI) btnTranslateAI.disabled = true;
    if (btnTranslateSelected) btnTranslateSelected.disabled = true;
    if (btnStopTranslate) {
        btnStopTranslate.style.display = 'inline-flex';
    }
    
    translateAbortController = new AbortController();
    isTranslatingCancelled = false;
    
    try {
        const openaiKeyEl = document.getElementById('openaiKey');
        const openaiBaseUrlEl = document.getElementById('openaiBaseUrl');
        const openaiModelEl = document.getElementById('openaiModel');
        
        const openai_key = openaiKeyEl ? openaiKeyEl.value.trim() : '';
        const openai_base_url = openaiBaseUrlEl ? openaiBaseUrlEl.value.trim() : 'https://api.openai.com/v1';
        
        // Theo yêu cầu: Khi dịch phụ đề Online luôn gọi Qwen (mặc định qwen/qwen3.7-flash)
        let openai_model = DEFAULT_TRANSLATION_CONFIG.model || 'qwen/qwen3.7-flash';
        const configuredModel = openaiModelEl ? openaiModelEl.value.trim() : '';
        if (configuredModel && configuredModel.toLowerCase().includes('qwen')) {
            openai_model = configuredModel;
        }

        // ═══════════════════════════════════════════════════════════════════
        //  PARALLEL TRANSLATION ENGINE — 6 Worker Song Song, Queue-Based
        //  Thiết kế triệt để giải quyết lag UI:
        //  1. Worker chạy ngầm, ghi thẳng vào bộ nhớ mảng srtData
        //  2. Tuyệt đối KHÔNG querySelector, KHÔNG chọc DOM trong lúc worker chạy
        //  3. Chỉ 1 timer heartbeat duy nhất cập nhật số % trên nút bấm
        //  4. Chỉ render lại bảng phụ đề 1 lần duy nhất khi toàn bộ hoàn tất
        // ═══════════════════════════════════════════════════════════════════
        const CONCURRENCY = isOffline ? 1 : 6;
        const BATCH_SIZE = 100;

        // Chia targetSubs thành các mẻ (mặc định 100 câu, nếu là dịch subset câu đã chọn thì dùng mẻ 30 câu để ngữ cảnh chuẩn xác hơn)
        const isSubset = targetSubs.length < srtData.length;
        const actualBatchSize = isSubset ? 30 : BATCH_SIZE;
        const CONTEXT_LINES = 6;

        const allChunks = [];
        for (let i = 0; i < targetSubs.length; i += actualBatchSize) {
            const chunk = targetSubs.slice(i, i + actualBatchSize);
            let ctx = [];
            if (isSubset) {
                // Lấy ngữ cảnh 6 câu trước từ toàn bộ bảng srtData thực tế
                const firstSubId = String(chunk[0].id);
                const globalIdx = srtData.findIndex(s => String(s.id) === firstSubId);
                if (globalIdx > 0) {
                    ctx = srtData.slice(Math.max(0, globalIdx - CONTEXT_LINES), globalIdx).map(s => ({
                        id: s.id,
                        text: s.translation || s.text
                    }));
                }
            } else if (i > 0) {
                ctx = targetSubs.slice(Math.max(0, i - CONTEXT_LINES), i).map(s => ({
                    id: s.id,
                    text: s.translation || s.text
                }));
            }
            allChunks.push({
                chunk,
                ctx,
                from: i + 1,
                to: Math.min(i + actualBatchSize, targetSubs.length)
            });
        }

        let queueIdx = 0;
        let translatedCount = 0;
        const failedChunksList = [];
        let totalTokensAccum = 0;
        let totalPromptTokens = 0;
        let totalCompletionTokens = 0;
        const pipelineStartTime = performance.now();

        const basePayload = {
            mode:              execMode,
            source_lang:       source_lang,
            target_lang:       target_lang,
            translation_style: translation_style,
            openai_key:        openai_key,
            openai_base_url:   openai_base_url,
            openai_model:      openai_model,
            stream:            false,
            engine:            isOffline ? 'offline' : 'online',
            local_model:       isOffline ? localModel : undefined
        };

        // --- Heartbeat cập nhật số % trên nút bấm (800ms/lần, cực kỳ nhẹ) ---
        const uiHeartbeat = setInterval(() => {
            if (!targetBtn) return;
            const percent = totalSubs > 0 ? Math.round((translatedCount / totalSubs) * 100) : 0;
            targetBtn.innerHTML = `
                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"
                     style="vertical-align:middle;animation:spin 1s linear infinite;">
                  <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle>
                </svg>
                <span>Đang dịch (${percent}% — ${translatedCount}/${totalSubs})...</span>
            `;
        }, 800);

        // --- Hàm xử lý kết quả 1 chunk (chỉ ghi vào bộ nhớ, KHÔNG CHỌC DOM) ---
        function applyChunkResult(chunk, data) {
            if (!data || !Array.isArray(data.subtitles)) return 0;
            const transMap = new Map();
            data.subtitles.forEach(s => {
                if (s.translation) transMap.set(String(s.id), s.translation);
            });
            let countOk = 0;
            // Ghi trực tiếp vào srtData (không gọi renderSrtTable hay querySelector)
            srtData.forEach(s => {
                const t = transMap.get(String(s.id));
                if (t) { s.translation = t; countOk++; }
            });
            return countOk;
        }

        // --- Worker: chạy độc lập, tự lấy chunk từ queue, tự phục hồi nếu lỗi ---
        async function translationWorker(workerIdx) {
            while (true) {
                // Lấy chunk kế tiếp từ queue (atomic trong JS single-thread event loop)
                if (isTranslatingCancelled) return;
                const taskIdx = queueIdx++;
                if (taskIdx >= allChunks.length) return;   // Hết việc

                const { chunk, ctx, from, to } = allChunks[taskIdx];
                appendLog(`[${timeNow()}] > [W${workerIdx}] ⏳ Đang dịch nhóm ${from}–${to} (${chunk.length} câu)...`, 'info');
                const payload = Object.assign({}, basePayload, {
                    subtitles:      chunk,
                    context_before: ctx
                });

                let data = null;
                const chunkStart = performance.now();
                const MAX_RETRIES = 5;

                // --- Thử tối đa 5 lần với exponential backoff & jitter ---
                for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
                    if (isTranslatingCancelled) return;
                    const ctrlTimeout = new AbortController();
                    const timeoutId = setTimeout(() => ctrlTimeout.abort(), 90000); // 90s hard timeout
                    const onCancel = () => ctrlTimeout.abort();
                    translateAbortController.signal.addEventListener('abort', onCancel);
                    try {
                        const res = await fetch('/api/translate_subtitles', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload),
                            signal: ctrlTimeout.signal
                        });
                        data = await res.json();
                        if (data && !data.error) break;    // ✅ Thành công
                        // Lỗi API trả về
                        if (attempt < 3 && !isTranslatingCancelled) {
                            const jitter = 1500 + attempt * 800 + Math.random() * 700;
                            appendLog(`[${timeNow()}] > [W${workerIdx}] Nhóm ${from}-${to}: ${data?.error || 'Lỗi'}, thử lại lần ${attempt+1}/3 sau ${(jitter/1000).toFixed(1)}s...`, 'warning');
                            await new Promise(r => setTimeout(r, jitter));
                        }
                    } catch (fetchErr) {
                        if (isTranslatingCancelled || fetchErr.name === 'AbortError') return;
                        if (attempt < 3) {
                            const jitter = 1500 + attempt * 1000 + Math.random() * 500;
                            appendLog(`[${timeNow()}] > [W${workerIdx}] ⚠️ Nhóm ${from}-${to}: ${fetchErr.message}, thử lại sau ${(jitter/1000).toFixed(1)}s...`, 'warning');
                            await new Promise(r => setTimeout(r, jitter));
                        } else {
                            data = { error: fetchErr.message || 'Lỗi kết nối' };
                        }
                    } finally {
                        clearTimeout(timeoutId);
                        translateAbortController.signal.removeEventListener('abort', onCancel);
                    }
                }

                if (isTranslatingCancelled) return;

                // --- Xử lý kết quả ---
                if (!data || data.error) {
                    const errMsg = data?.error || 'Không nhận được phản hồi';
                    failedChunksList.push({ from, to });
                    appendLog(`[${timeNow()}] > [W${workerIdx}] ❌ Nhóm ${from}-${to} bỏ qua: ${errMsg}`, 'warning');
                    if (errMsg.includes('bản quyền') || errMsg.includes('quota') || errMsg.includes('API Key')) {
                        isTranslatingCancelled = true;
                        showToast(errMsg, 'error');
                        return;
                    }
                    continue;
                }

                const chunkDur = Math.max(0.1, (performance.now() - chunkStart) / 1000).toFixed(1);

                // Ghi token stats (chỉ số nguyên, không chọc DOM)
                if (data.usage) {
                    if (isOffline) {
                        const pTok = data.usage.prompt_tokens || Math.round(chunk.reduce((a, s) => a + (s.text || '').length, 0) * 1.3);
                        const cTok = data.usage.completion_tokens || chunk.length * 20;
                        totalTokensAccum     += data.usage.total_tokens || (pTok + cTok);
                        totalPromptTokens    += pTok;
                        totalCompletionTokens += cTok;
                        appendLog(`[${timeNow()}] > [W${workerIdx}] ⚡ GPU ${from}-${to}: ${(data.usage.total_tokens || 0).toLocaleString()} tok | ${chunkDur}s`, 'info');
                    } else if (execMode === 'ai') {
                        tokenTracker.record(`Dịch nhóm ${from}-${to}`, data.usage, openai_model || 'qwen/qwen3.7-flash');
                        totalTokensAccum      += (data.usage.total_tokens || 0);
                        totalPromptTokens     += (data.usage.prompt_tokens || 0);
                        totalCompletionTokens += (data.usage.completion_tokens || 0);
                    }
                }

                // Ghi bản dịch vào bộ nhớ (KHÔNG chọc DOM)
                const applied = applyChunkResult(chunk, data);
                translatedCount += applied;

                // Log tiến độ (appendLog chỉ thêm text vào terminal, không rebuild bảng phụ đề)
                const pct = Math.round((translatedCount / totalSubs) * 100);
                appendLog(`[${timeNow()}] > [W${workerIdx}] ✅ Dịch xong nhóm ${from}–${to} (${pct}% | ${chunkDur}s)`, 'info');
            }
        }

        // --- Khởi động 6 worker với stagger 150ms để tránh burst request đồng loạt ---
        const workers = [];
        const numWorkers = Math.min(CONCURRENCY, allChunks.length);
        for (let w = 0; w < numWorkers; w++) {
            workers.push(
                new Promise(resolve => {
                    setTimeout(() => translationWorker(w + 1).then(resolve).catch(resolve), w * 150);
                })
            );
        }

        // Chờ tất cả worker hoàn thành
        await Promise.all(workers);

        // Dừng heartbeat UI
        clearInterval(uiHeartbeat);

        const totalWallClockSec = Math.max(0.1, (performance.now() - pipelineStartTime) / 1000).toFixed(1);
        const avgSubPerSec = (translatedCount / totalWallClockSec).toFixed(1);

        // ═══ Render lại bảng phụ đề VÀ cập nhật thống kê — DUY NHẤT 1 LẦN Ở ĐÂY ═══
        renderSrtTable();
        updateBottomBarStats();

        if (isTranslatingCancelled) {
            appendLog(`[${timeNow()}] > [Dịch thuật] ⏹️ Đã dừng. Đã lưu ${translatedCount}/${totalSubs} câu đã dịch.`, 'warning');
            showToast(`Đã dừng dịch! Đã lưu lại ${translatedCount} câu.`, 'info');
        } else if (translatedCount > 0) {
            appendLog(`[${timeNow()}] > [Dịch thuật] 🎉 Hoàn tất ${translatedCount}/${totalSubs} câu → ${targetLangName}! (${totalWallClockSec}s | ${avgSubPerSec} câu/s | ${numWorkers} luồng song song)`, 'success');
            if (isOffline && totalTokensAccum > 0) {
                appendLog(`[${timeNow()}] > [Token AI] 📊 GPU Offline: ${totalTokensAccum.toLocaleString()} tokens ~ 0đ`, 'info');
            }
            if (failedChunksList.length > 0) {
                appendLog(`[${timeNow()}] > [Dịch thuật] ⚠️ ${failedChunksList.length} nhóm lỗi (${failedChunksList.map(f => `${f.from}-${f.to}`).join(', ')}). Bấm Dịch lại để bổ sung.`, 'warning');
            }
            showToast(`✅ Đã dịch xong ${translatedCount}/${totalSubs} câu sang ${targetLangName} (${numWorkers} luồng | ${totalWallClockSec}s)!`, 'success');
            if (btnPreviewEdited) btnPreviewEdited.click();
        } else {
            appendLog(`[${timeNow()}] > [Dịch thuật] ⚠️ Chưa dịch được câu nào. Vui lòng kiểm tra lại API Key hoặc mạng.`, 'warning');
            showToast('Chưa dịch được câu nào. Hãy kiểm tra lại API Key hoặc kết nối mạng.', 'warning');
        }
        
    } catch(err) {
        if (!isTranslatingCancelled && err.name !== 'AbortError') {
            appendLog(`[${timeNow()}] > [Dịch thuật - LỖI] Lỗi kết nối: ${err.message}`, 'error');
            showToast('Lỗi kết nối khi dịch: ' + err.message, 'error');
        }
    } finally {
        isTranslatingCancelled = false;
        translateAbortController = null;
        if (targetBtn) {
            targetBtn.disabled = false;
            targetBtn.innerHTML = origHtml;
        }
        if (btnTranslateSrt) btnTranslateSrt.disabled = false;
        if (btnTranslateAI) btnTranslateAI.disabled = false;
        if (btnTranslateSelected) btnTranslateSelected.disabled = false;
        if (btnStopTranslate) {
            btnStopTranslate.style.display = 'none';
        }
        if (typeof triggerAutoSaveEditorCache === 'function') {
            triggerAutoSaveEditorCache();
        }
    }
}

// Xuất các hàm Dịch & Làm sạch AI ra window để Batch Editor và các module khác tái sử dụng
window.executeCleanSubtitles = executeCleanSubtitles;
window.handleTranslateSubtitles = handleTranslateSubtitles;
window.promptTranslateCleanAction = promptTranslateCleanAction;
window.promptAiExecutionMode = promptAiExecutionMode;
window.ensureAiKeyAvailable = ensureAiKeyAvailable;

const btnTranslateSelected = document.getElementById('btnTranslateSelected');
if (btnTranslateSelected) {
    btnTranslateSelected.addEventListener('click', async () => {
        if (!srtData || srtData.length === 0) {
            showToast('Không có phụ đề nào trong bảng!', 'warning');
            return;
        }
        let selectedSubs = srtData.filter(s => s.selected);
        if (selectedSubs.length === 0) {
            // Tự động tìm các câu chưa dịch, còn sót tiếng Trung hoặc bị lỗi nếu người dùng chưa chọn câu nào
            const untranslated = srtData.filter(s => {
                if (!s.translation || s.translation.trim() === '') return true;
                if (/[\u4e00-\u9fff]/.test(s.translation)) return true;
                if (isSubtitleError(s)) return true;
                return false;
            });
            if (untranslated.length > 0) {
                untranslated.forEach(s => s.selected = true);
                renderSrtTable();
                showToast(`Đã tự động chọn ${untranslated.length} câu chưa dịch / có lỗi. Bắt đầu dịch bù...`, 'info');
            } else {
                showToast('Vui lòng tích chọn các câu cần dịch lại hoặc lọc mục "Chưa dịch"!', 'warning');
                return;
            }
        }
        await handleTranslateSubtitles('ai', { skipConfirm: true, useSurroundingContext: true });
    });
}
if (btnTranslateSrt) {
    btnTranslateSrt.addEventListener('click', () => handleTranslateAndCleanUnified());
}
if (btnTranslateAI) {
    btnTranslateAI.addEventListener('click', () => handleTranslateSubtitles('ai'));
}

// ═══════════════════════════════════════════════════════════════════
//  QUẢN LÝ BỘ TỪ ĐIỂN TU TIÊN & DANH XƯNG CỔ TRANG (GLOSSARY)
// ═══════════════════════════════════════════════════════════════════
const glossaryModal = document.getElementById('glossaryModal');
const btnOpenGlossaryModal = document.getElementById('btnOpenGlossaryModal');
const closeGlossaryModalBtn = document.getElementById('closeGlossaryModalBtn');
const glossaryCountBadge = document.getElementById('glossaryCountBadge');
const glossaryTableBody = document.getElementById('glossaryTableBody');
const glossaryNewSrc = document.getElementById('glossaryNewSrc');
const glossaryNewTgt = document.getElementById('glossaryNewTgt');
const btnAddGlossaryTerm = document.getElementById('btnAddGlossaryTerm');
const glossarySearchInput = document.getElementById('glossarySearchInput');
const btnSaveGlossaryModal = document.getElementById('btnSaveGlossaryModal');
const btnResetGlossaryDefault = document.getElementById('btnResetGlossaryDefault');
const btnApplyGlossaryToCurrentSrt = document.getElementById('btnApplyGlossaryToCurrentSrt');

let currentGlossaryData = {};

async function loadGlossaryFromServer() {
    try {
        const res = await fetch('/api/glossary');
        const data = await res.json();
        if (data && data.success && data.glossary) {
            currentGlossaryData = data.glossary;
            renderGlossaryTable();
        }
    } catch (e) {
        console.warn('Lỗi nạp từ điển glossary:', e);
    }
}

function renderGlossaryTable() {
    if (!glossaryTableBody) return;
    glossaryTableBody.innerHTML = '';
    const q = (glossarySearchInput?.value || '').trim().toLowerCase();
    
    const entries = Object.entries(currentGlossaryData);
    if (glossaryCountBadge) {
        glossaryCountBadge.textContent = `${entries.length} từ`;
    }

    const filtered = entries.filter(([src, tgt]) => {
        if (!q) return true;
        return src.toLowerCase().includes(q) || tgt.toLowerCase().includes(q);
    });

    if (filtered.length === 0) {
        glossaryTableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 20px; color: #64748b; font-style: italic;">Không tìm thấy thuật ngữ nào phù hợp.</td></tr>`;
        return;
    }

    const frag = document.createDocumentFragment();
    filtered.forEach(([src, tgt]) => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
        tr.innerHTML = `
            <td style="padding: 7px 12px; color: #fbbf24; font-family: monospace; font-weight: 600;">${escapeHtml(src)}</td>
            <td style="padding: 7px 12px; color: #f8fafc;">
                <input type="text" class="glossary-inline-tgt" value="${escapeHtml(tgt)}" data-src="${escapeHtml(src)}" style="width: 100%; background: transparent; border: none; color: #f8fafc; font-size: 12.5px; outline: none;">
            </td>
            <td style="padding: 7px 12px; text-align: center;">
                <button type="button" class="btn-del-glossary" data-src="${escapeHtml(src)}" style="background: transparent; border: none; color: #ef4444; cursor: pointer; font-size: 14px; padding: 2px 6px;">✕</button>
            </td>
        `;
        frag.appendChild(tr);
    });
    glossaryTableBody.appendChild(frag);

    // Bind inline edit & delete
    glossaryTableBody.querySelectorAll('.glossary-inline-tgt').forEach(inp => {
        inp.addEventListener('change', (e) => {
            const s = e.target.getAttribute('data-src');
            currentGlossaryData[s] = e.target.value.trim();
        });
    });
    glossaryTableBody.querySelectorAll('.btn-del-glossary').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const s = e.target.getAttribute('data-src');
            delete currentGlossaryData[s];
            renderGlossaryTable();
        });
    });
}

if (btnOpenGlossaryModal) {
    btnOpenGlossaryModal.addEventListener('click', () => {
        if (glossaryModal) {
            glossaryModal.style.display = 'flex';
            loadGlossaryFromServer();
        }
    });
}

if (closeGlossaryModalBtn) {
    closeGlossaryModalBtn.addEventListener('click', () => {
        if (glossaryModal) glossaryModal.style.display = 'none';
    });
}

if (glossarySearchInput) {
    glossarySearchInput.addEventListener('input', renderGlossaryTable);
}

if (btnAddGlossaryTerm) {
    btnAddGlossaryTerm.addEventListener('click', () => {
        const src = (glossaryNewSrc?.value || '').trim();
        const tgt = (glossaryNewTgt?.value || '').trim();
        if (!src || !tgt) {
            showToast('Vui lòng nhập đầy đủ cả từ gốc tiếng Trung và bản dịch tiếng Việt!', 'warning');
            return;
        }
        currentGlossaryData[src] = tgt;
        if (glossaryNewSrc) glossaryNewSrc.value = '';
        if (glossaryNewTgt) glossaryNewTgt.value = '';
        renderGlossaryTable();
        showToast(`Đã thêm thuật ngữ: ${src} ➔ ${tgt}`, 'success');
    });
}

if (btnSaveGlossaryModal) {
    btnSaveGlossaryModal.addEventListener('click', async () => {
        try {
            btnSaveGlossaryModal.disabled = true;
            btnSaveGlossaryModal.textContent = 'Đang lưu...';
            const res = await fetch('/api/glossary/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ glossary: currentGlossaryData })
            });
            const data = await res.json();
            if (data.success) {
                showToast('✅ Đã lưu bộ từ điển Tu Tiên thành công!', 'success');
                if (glossaryModal) glossaryModal.style.display = 'none';
            } else {
                showToast('Lỗi lưu từ điển: ' + (data.error || 'Thất bại'), 'error');
            }
        } catch (e) {
            showToast('Lỗi kết nối lưu từ điển: ' + e.message, 'error');
        } finally {
            btnSaveGlossaryModal.disabled = false;
            btnSaveGlossaryModal.textContent = '💾 Lưu Từ Điển';
        }
    });
}

if (btnResetGlossaryDefault) {
    btnResetGlossaryDefault.addEventListener('click', async () => {
        if (confirm('Bạn có chắc muốn đặt lại toàn bộ từ điển về danh sách Tu Tiên & Danh Xưng mặc định không?')) {
            await fetch('/api/glossary/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ glossary: {} })
            });
            await loadGlossaryFromServer();
            showToast('Đã đặt lại từ điển về mặc định chuẩn mực!', 'info');
        }
    });
}

if (btnApplyGlossaryToCurrentSrt) {
    btnApplyGlossaryToCurrentSrt.addEventListener('click', async () => {
        if (!srtData || srtData.length === 0) {
            showToast('Không có phụ đề nào trong bảng để đối chiếu!', 'warning');
            return;
        }
        try {
            btnApplyGlossaryToCurrentSrt.disabled = true;
            btnApplyGlossaryToCurrentSrt.textContent = '⏳ Đang đối chiếu...';
            const res = await fetch('/api/glossary/apply_to_subtitles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subtitles: srtData })
            });
            const data = await res.json();
            if (data.success && Array.isArray(data.subtitles)) {
                srtData = data.subtitles;
                renderSrtTable();
                showToast(`🎉 Đã đối chiếu xong! Tự động chuẩn hóa ${data.updated_count} câu theo từ điển (0 Token)!`, 'success');
                if (glossaryModal) glossaryModal.style.display = 'none';
            } else {
                showToast('Lỗi đối chiếu: ' + (data.error || 'Lỗi không xác định'), 'error');
            }
        } catch (e) {
            showToast('Lỗi kết nối đối chiếu từ điển: ' + e.message, 'error');
        } finally {
            btnApplyGlossaryToCurrentSrt.disabled = false;
            btnApplyGlossaryToCurrentSrt.textContent = '⚡ Đối chiếu & Sửa vào bảng phụ đề hiện tại';
        }
    });
}

// Đồng bộ ngôn ngữ đích giữa Header và Bottom Bar
const bottomSubTargetLang = document.getElementById('bottomSubTargetLang');
const mainSubTargetLang = document.getElementById('subTargetLang');
if (bottomSubTargetLang && mainSubTargetLang) {
    bottomSubTargetLang.addEventListener('change', () => {
        mainSubTargetLang.value = bottomSubTargetLang.value;
    });
    mainSubTargetLang.addEventListener('change', () => {
        bottomSubTargetLang.value = mainSubTargetLang.value;
    });
}

// Đồng bộ và lưu trữ Phong cách dịch thuật giữa Header, Footer và LocalStorage
const savedInitialStyle = localStorage.getItem('novacut_translation_style') || 'cinema';
const subStyleHeaderEl = document.getElementById('subTranslationStyle');
const subStyleFooterEl = document.getElementById('bottomSubTranslationStyle');
const subStyleModalEl = document.getElementById('modalSubTranslationStyle');

if (subStyleHeaderEl) subStyleHeaderEl.value = savedInitialStyle;
if (subStyleFooterEl) subStyleFooterEl.value = savedInitialStyle;
if (subStyleModalEl) subStyleModalEl.value = savedInitialStyle;

function syncAndSaveTranslationStyle(style) {
    if (!style) return;
    try { localStorage.setItem('novacut_translation_style', style); } catch (e) {}
    if (subStyleHeaderEl && subStyleHeaderEl.value !== style) subStyleHeaderEl.value = style;
    if (subStyleFooterEl && subStyleFooterEl.value !== style) subStyleFooterEl.value = style;
    if (subStyleModalEl && subStyleModalEl.value !== style) subStyleModalEl.value = style;
}

if (subStyleHeaderEl) {
    subStyleHeaderEl.addEventListener('change', (e) => syncAndSaveTranslationStyle(e.target.value));
}
if (subStyleFooterEl) {
    subStyleFooterEl.addEventListener('change', (e) => syncAndSaveTranslationStyle(e.target.value));
}
if (subStyleModalEl) {
    subStyleModalEl.addEventListener('change', (e) => syncAndSaveTranslationStyle(e.target.value));
}

// 🔗 Nút Gộp SRT thủ công (Yêu cầu các dòng được chọn phải liên tiếp nhau)
const btnMergeSelectedSrt = document.getElementById('btnMergeSelectedSrt');
if (btnMergeSelectedSrt) {
    btnMergeSelectedSrt.addEventListener('click', () => {
        if (!srtData || srtData.length === 0) {
            showToast('Không có phụ đề nào để gộp!', 'warning');
            return;
        }

        const selectedIndices = [];
        srtData.forEach((sub, idx) => {
            if (sub.selected) {
                selectedIndices.push(idx);
            }
        });

        if (selectedIndices.length < 2) {
            showToast('Vui lòng tích chọn từ 2 dòng phụ đề liên tiếp trở lên để gộp!', 'warning');
            return;
        }

        // Kiểm tra tính liên tiếp của các dòng được chọn
        for (let i = 1; i < selectedIndices.length; i++) {
            if (selectedIndices[i] !== selectedIndices[i - 1] + 1) {
                showToast('⚠️ Các dòng phụ đề cần gộp phải nối tiếp nhau liên tục, không được chọn cách quãng!', 'warning');
                return;
            }
        }

        const firstIdx = selectedIndices[0];
        const lastIdx = selectedIndices[selectedIndices.length - 1];
        const selectedSubs = srtData.slice(firstIdx, lastIdx + 1);

        const startSec = selectedSubs[0].startSeconds;
        const endSec = selectedSubs[selectedSubs.length - 1].endSeconds;

        // Nối nội dung text
        const mergedText = selectedSubs
            .map(s => (s.text || s.original_text || '').trim())
            .filter(Boolean)
            .join(' ');

        // Nối bản dịch (nếu có)
        const mergedTranslation = selectedSubs
            .map(s => (s.translation || '').trim())
            .filter(Boolean)
            .join(' ');

        // Định dạng thời gian
        const startTimeStr = formatSrtTimestamp(startSec).replace(',', '.');
        const endTimeStr = formatSrtTimestamp(endSec).replace(',', '.');
        const timeStr = `${startTimeStr} - ${endTimeStr}`;

        // Gộp aiBox nếu có
        let mergedAiBox = null;
        const subsWithAiBox = selectedSubs.filter(s => s.aiBox && typeof s.aiBox.x_pct === 'number');
        if (subsWithAiBox.length > 0) {
            const minX = Math.min(...subsWithAiBox.map(s => s.aiBox.x_pct));
            const maxXPlusW = Math.max(...subsWithAiBox.map(s => s.aiBox.x_pct + (s.aiBox.w_pct || 0)));
            const minY = Math.min(...subsWithAiBox.map(s => s.aiBox.y_pct || 81.5));
            const maxH = Math.max(...subsWithAiBox.map(s => s.aiBox.h_pct || 9.5));
            mergedAiBox = {
                x_pct: Math.round(minX * 10) / 10,
                y_pct: Math.round(minY * 10) / 10,
                w_pct: Math.round((maxXPlusW - minX) * 10) / 10,
                h_pct: Math.round(maxH * 10) / 10
            };
        }

        const mergedSub = {
            id: String(firstIdx + 1),
            time: timeStr,
            startSeconds: startSec,
            endSeconds: endSec,
            text: mergedText,
            original_text: mergedText,
            translation: mergedTranslation,
            selected: true,
            aiBox: mergedAiBox
        };

        // Thay thế các dòng được chọn bằng 1 dòng đã gộp
        srtData.splice(firstIdx, selectedIndices.length, mergedSub);

        // Đánh số lại ID từ 1 đến N
        srtData.forEach((s, idx) => {
            s.id = String(idx + 1);
        });

        renderSrtTable();

        if (typeof updateDynamicBlurIntervals === 'function') {
            updateDynamicBlurIntervals();
            updateDynamicBlurOverlayVisibility();
        }

        showToast(`🎉 Đã gộp thành công ${selectedIndices.length} dòng phụ đề thành 1 câu!`, 'success');
    });
}

// ✨ Nút Làm sạch SRT (AI) & Nút Dừng
const btnCleanSrtAI = document.getElementById('btnCleanSrtAI');
const btnStopCleanSrtAI = document.getElementById('btnStopCleanSrtAI');

let cleanSrtAbortController = null;
let isCleanSrtCancelled = false;

if (btnStopCleanSrtAI) {
    btnStopCleanSrtAI.addEventListener('click', () => {
        isCleanSrtCancelled = true;
        if (cleanSrtAbortController) {
            cleanSrtAbortController.abort();
        }
        showToast('⏹️ Đang dừng làm sạch AI...', 'info');
    });
}

if (btnCleanSrtAI) {
    btnCleanSrtAI.addEventListener('click', async () => {
        await handleTranslateAndCleanUnified();
    });
}

// ✂️ Nút Rút gọn phụ đề (AI)
const btnCondenseSrtAI = document.getElementById('btnCondenseSrtAI');
if (btnCondenseSrtAI) {
    btnCondenseSrtAI.addEventListener('click', async () => {
        if (!checkFeaturePermission('can_access_editor', 'Rút gọn phụ đề')) return;
        if (!srtData || srtData.length === 0) {
            showToast('Không có phụ đề nào để rút gọn!', 'warning');
            return;
        }

        const aiChoice = await promptAiExecutionMode('Rút gọn phụ đề (AI)', 'Cô đọng lời thoại, loại bỏ câu thừa cho kịch bản tóm tắt phim');
        if (!aiChoice) return;

        const isOffline = aiChoice.engine === 'offline';
        const localModel = aiChoice.localModel || 'qwen2.5:7b';

        let openaiKey = '';
        let openaiBaseUrl = 'https://api.openai.com/v1';
        let openaiModel = document.getElementById('openaiModel')?.value?.trim() || 'gpt-5.6-luna-pro-batch';

        if (!isOffline) {
            const hasKey = await ensureAiKeyAvailable('openai', 'Rút gọn phụ đề AI');
            if (!hasKey) return;
            openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
            openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
            openaiModel = document.getElementById('openaiModel')?.value?.trim() || 'gpt-5.6-luna-pro-batch';
            if (!openaiModel || openaiModel === 'gpt-4o-mini' || openaiModel === 'gpt-4o') {
                openaiModel = 'gpt-5.6-luna-pro-batch';
            }
        }

        const totalSubs = srtData.length;
        const timeNow = () => new Date().toLocaleTimeString();
        const origHtml = btnCondenseSrtAI.innerHTML;
        btnCondenseSrtAI.disabled = true;
        if (btnStopCleanSrtAI) {
            btnStopCleanSrtAI.style.display = 'inline-flex';
        }

        if (terminalOverlay && terminalOverlay.classList.contains('collapsed')) {
            terminalOverlay.classList.remove('collapsed');
            terminalOverlay.classList.add('expanded');
            if (toggleTerminalBtn) toggleTerminalBtn.textContent = 'Thu gọn';
        }

        const modeDesc = isOffline ? `Local GPU (${localModel})` : `Cloud AI (${openaiModel})`;
        appendLog(`[${timeNow()}] > [Rút gọn SRT] Bắt đầu rút gọn ${totalSubs} câu thoại bằng ${modeDesc}...`, 'info');
        showToast(`Bắt đầu rút gọn phụ đề bằng ${modeDesc}...`, 'info');

        cleanSrtAbortController = new AbortController();
        isCleanSrtCancelled = false;

        const batchSize = 200;
        let allCondensedSubtitles = [];
        let processedCount = 0;
        let totalTokens = 0;
        let hasError = false;

        try {
            for (let i = 0; i < totalSubs; i += batchSize) {
                if (isCleanSrtCancelled) {
                    break;
                }
                const chunk = srtData.slice(i, i + batchSize);
                const chunkFrom = i + 1;
                const chunkTo = Math.min(i + batchSize, totalSubs);

                btnCondenseSrtAI.innerHTML = `
                    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
                    <span>Đang rút gọn (${Math.round((chunkTo/totalSubs)*100)}% - ${chunkTo}/${totalSubs})...</span>
                `;

                let res;
                try {
                    res = await fetch('/api/clean_subtitles_ai', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            subtitles: chunk,
                            engine: isOffline ? 'offline' : 'online',
                            local_model: isOffline ? localModel : undefined,
                            openai_key: (!isOffline && openaiKey && !openaiKey.startsWith('•')) ? openaiKey : undefined,
                            openai_base_url: !isOffline ? openaiBaseUrl : undefined,
                            openai_model: !isOffline ? openaiModel : undefined
                        }),
                        signal: cleanSrtAbortController.signal
                    });
                } catch (fetchErr) {
                    if (isCleanSrtCancelled || fetchErr.name === 'AbortError') {
                        break;
                    }
                    throw fetchErr;
                }

                if (!res.ok) {
                    const errText = await res.text();
                    let errMsg = `Mã lỗi HTTP ${res.status}`;
                    try {
                        const errJson = JSON.parse(errText);
                        if (errJson.error) errMsg = errJson.error;
                    } catch (e) {}
                    appendLog(`[${timeNow()}] > [Rút gọn SRT - LỖI] Nhóm câu ${chunkFrom}-${chunkTo}: ${errMsg}`, 'error');
                    showToast(`Lỗi rút gọn nhóm câu ${chunkFrom}-${chunkTo}: ${errMsg}`, 'error');
                    hasError = true;
                    break;
                }

                const data = await res.json();
                if (data.error) {
                    appendLog(`[${timeNow()}] > [Rút gọn SRT - LỖI] Nhóm câu ${chunkFrom}-${chunkTo}: ${data.error}`, 'error');
                    showToast(`Lỗi rút gọn SRT: ${data.error}`, 'error');
                    hasError = true;
                    break;
                }

                if (data.usage && !isOffline) {
                    tokenTracker.record(`Rút gọn nhóm câu ${chunkFrom}-${chunkTo}`, data.usage, openaiModel || 'gpt-5.6-luna');
                    totalTokens += (data.usage.total_tokens || 0);
                }

                if (data.subtitles && Array.isArray(data.subtitles)) {
                    data.subtitles.forEach(item => {
                        allCondensedSubtitles.push({
                            ...item,
                            id: String(allCondensedSubtitles.length + 1)
                        });
                    });
                    processedCount += chunk.length;
                    const percent = Math.round((processedCount / totalSubs) * 100);
                    appendLog(`[${timeNow()}] > [Rút gọn SRT] Đang xử lý: ${processedCount}/${totalSubs} câu (${percent}%)...`, 'info');
                }
            }

            if (isCleanSrtCancelled) {
                if (allCondensedSubtitles.length > 0) {
                    const remainingOriginal = srtData.slice(processedCount);
                    const combined = allCondensedSubtitles.concat(remainingOriginal).map((item, idx) => ({
                        ...item,
                        id: String(idx + 1)
                    }));
                    srtData = combined;
                    renderSrtTable();
                    appendLog(`[${timeNow()}] > [Rút gọn SRT] ⏹️ Đã dừng rút gọn AI. Đã lưu ${allCondensedSubtitles.length} câu.`, 'warning');
                    showToast(`Đã dừng rút gọn! Đã lưu các câu đã xử lý.`, 'info');
                } else {
                    appendLog(`[${timeNow()}] > [Rút gọn SRT] ⏹️ Đã hủy rút gọn AI.`, 'info');
                }
            } else if (allCondensedSubtitles.length > 0) {
                const oldCount = srtData.length;
                srtData = allCondensedSubtitles;
                renderSrtTable();
                const tokenSummary = totalTokens > 0 ? ` (🪙 Tổng token: ${totalTokens.toLocaleString()})` : '';
                appendLog(`[${timeNow()}] > [Rút gọn SRT] 🎉 Hoàn tất! Đã rút gọn từ ${oldCount} câu xuống ${srtData.length} câu súc tích${tokenSummary}.`, 'success');
                showToast(`Đã rút gọn thành công còn ${srtData.length} câu!`, 'success');
            } else if (!hasError) {
                showToast('Không có câu phụ đề nào được tạo ra!', 'warning');
            }
        } catch (err) {
            if (!isCleanSrtCancelled && err.name !== 'AbortError') {
                console.error(err);
                appendLog(`[${timeNow()}] > [Rút gọn SRT - LỖI] Lỗi kết nối: ${err.message}`, 'error');
                showToast('Lỗi kết nối khi rút gọn: ' + err.message, 'error');
            }
        } finally {
            isCleanSrtCancelled = false;
            cleanSrtAbortController = null;
            btnCondenseSrtAI.disabled = false;
            btnCondenseSrtAI.innerHTML = origHtml;
            if (btnStopCleanSrtAI) {
                btnStopCleanSrtAI.style.display = 'none';
            }
        }
    });
}

const btnDeleteDuplicates = document.getElementById('btnDeleteDuplicates');
if (btnDeleteDuplicates) {
    btnDeleteDuplicates.addEventListener('click', async () => {
        const dupCount = srtData.filter((s, idx) => isSubtitleDuplicate(s, idx, srtData)).length;
        if (dupCount === 0) {
            showToast('Không có câu phụ đề nào bị trùng lặp!', 'info');
            return;
        }
        const confirmed = await showConfirmModal(
            'Dọn dẹp câu trùng lặp',
            `Tìm thấy ${dupCount} câu phụ đề bị trùng lặp. Bạn có muốn tự động xóa bỏ các câu trùng này (giữ lại câu đầu tiên và tự động gộp mốc thời gian)?`
        );
        if (confirmed) {
            let removed = 0;
            const newSubs = [];
            for (let i = 0; i < srtData.length; i++) {
                const sub = srtData[i];
                const dupReason = getSubtitleDuplicateInfo(sub, i, srtData);
                if (dupReason && newSubs.length > 0) {
                    const prev = newSubs[newSubs.length - 1];
                    // Tự động mở rộng thời gian kết thúc của câu gốc
                    if (typeof sub.endSeconds === 'number' && (typeof prev.endSeconds !== 'number' || sub.endSeconds > prev.endSeconds)) {
                        prev.endSeconds = sub.endSeconds;
                        if (typeof prev.startSeconds === 'number' && typeof formatSrtTimestamp === 'function') {
                            const sStr = formatSrtTimestamp(prev.startSeconds).replace(',', '.');
                            const eStr = formatSrtTimestamp(prev.endSeconds).replace(',', '.');
                            prev.time = `${sStr} - ${eStr}`;
                        }
                    }
                    // Nếu câu gốc trước chưa có bản dịch mà câu trùng có bản dịch thì copy sang
                    if ((!prev.translation || !prev.translation.trim()) && sub.translation && sub.translation.trim()) {
                        prev.translation = sub.translation;
                    }
                    removed++;
                    continue;
                }
                newSubs.push(sub);
            }
            // Đánh lại số ID theo thứ tự từ 1
            newSubs.forEach((s, idx) => { s.id = idx + 1; });
            srtData = newSubs;
            if (typeof triggerAutoSaveEditorCache === 'function') {
                triggerAutoSaveEditorCache();
            }
            renderSrtTable();
            showToast(`Đã dọn dẹp thành công ${removed} câu phụ đề trùng lặp!`, 'success');
        }
    });
}

const btnDeleteSelected = document.getElementById('btnDeleteSelected');
if (btnDeleteSelected) {
    btnDeleteSelected.addEventListener('click', () => {
        srtData = srtData.filter(s => !s.selected);
        if(srtSelectAll) srtSelectAll.checked = false;
        renderSrtTable();
    });
}

const btnDeleteTranslation = document.getElementById('btnDeleteTranslation');
if (btnDeleteTranslation) {
    btnDeleteTranslation.addEventListener('click', () => {
        srtData.forEach(s => s.translation = '');
        renderSrtTable();
    });
}

const btnDeleteAll = document.getElementById('btnDeleteAll');
if (btnDeleteAll) {
    btnDeleteAll.addEventListener('click', async () => {
        const confirmed = await showConfirmModal('Xóa tất cả', 'Bạn có chắc chắn muốn xóa toàn bộ phụ đề? Hành động này không thể hoàn tác.');
        if (confirmed) {
            srtData = [];
            renderSrtTable();
        }
    });
}


// =========================================================================
// TTS STUDIO (AI TEXT TO SPEECH) ADVANCED CONTROLLER
// =========================================================================
const btnGenerateTTS = document.getElementById('btnGenerateTTS');
const ttsInputText = document.getElementById('ttsInputText');
const ttsVoice = document.getElementById('ttsVoice');
const ttsSpeed = document.getElementById('ttsSpeed');
const ttsSpeedVal = document.getElementById('ttsSpeedVal');
const ttsResultPlaceholder = document.getElementById('ttsResultPlaceholder');
const ttsCharCount = document.getElementById('ttsCharCount');
const ttsWordCount = document.getElementById('ttsWordCount');
const ttsEstTime = document.getElementById('ttsEstTime');
const btnSelectTtsOutputDir = document.getElementById('btnSelectTtsOutputDir');
const ttsOutputDirDisplay = document.getElementById('ttsOutputDirDisplay');
const btnClearTtsHistory = document.getElementById('btnClearTtsHistory');
const ttsHistoryCount = document.getElementById('ttsHistoryCount');

// Initialize saved output directory or default
window.currentTtsOutputDir = localStorage.getItem('tts_output_dir') || '';
if (ttsOutputDirDisplay) {
    if (window.currentTtsOutputDir) {
        ttsOutputDirDisplay.innerText = `Thư mục: ${window.currentTtsOutputDir}`;
        ttsOutputDirDisplay.title = window.currentTtsOutputDir;
    } else {
        ttsOutputDirDisplay.innerText = 'Thư mục: output (Mặc định)';
        ttsOutputDirDisplay.title = 'Thư mục output mặc định trong ứng dụng';
    }
}

// 1. Text Statistics & Real-time Duration Estimation
function updateTtsStats() {
    if (!ttsInputText) return;
    const text = ttsInputText.value || '';
    const charCount = text.length;
    const words = text.trim() ? text.trim().split(/\s+/).filter(Boolean).length : 0;
    
    if (ttsCharCount) ttsCharCount.textContent = charCount;
    if (ttsWordCount) ttsWordCount.textContent = words;
    
    // Estimate reading duration: ~140 words/min at 1.0x speed + pause tokens
    const speed = parseFloat(ttsSpeed ? ttsSpeed.value : 1.0) || 1.0;
    let estSeconds = 0;
    if (words > 0) {
        estSeconds = Math.round((words / 2.3) / speed);
        // Add duration for any [pause X.Xs] tags
        const pauseMatches = text.match(/\[pause\s+([0-9.]+)s?\]/gi);
        if (pauseMatches) {
            pauseMatches.forEach(m => {
                const s = parseFloat(m.replace(/[^0-9.]/g, '')) || 0;
                estSeconds += Math.round(s);
            });
        }
    }
    
    if (ttsEstTime) {
        if (estSeconds >= 60) {
            const m = Math.floor(estSeconds / 60);
            const s = estSeconds % 60;
            ttsEstTime.textContent = `${m}m ${s}s`;
        } else {
            ttsEstTime.textContent = `${estSeconds}s`;
        }
    }
}

if (ttsInputText) {
    ttsInputText.addEventListener('input', updateTtsStats);
}

// 2. Quick Toolbar Handlers
// Pause Inserter Dropdown
const btnTtsInsertPause = document.getElementById('btnTtsInsertPause');
const ttsPauseMenu = document.getElementById('ttsPauseMenu');

if (btnTtsInsertPause && ttsPauseMenu) {
    btnTtsInsertPause.addEventListener('click', (e) => {
        e.stopPropagation();
        const isHidden = ttsPauseMenu.style.display === 'none' || !ttsPauseMenu.style.display;
        ttsPauseMenu.style.display = isHidden ? 'flex' : 'none';
    });

    document.addEventListener('click', (e) => {
        if (!btnTtsInsertPause.contains(e.target) && !ttsPauseMenu.contains(e.target)) {
            ttsPauseMenu.style.display = 'none';
        }
    });

    ttsPauseMenu.querySelectorAll('.pause-opt').forEach(btn => {
        btn.addEventListener('click', () => {
            const pauseCode = btn.getAttribute('data-pause');
            if (pauseCode && ttsInputText) {
                insertTextAtCursor(ttsInputText, ' ' + pauseCode + ' ');
                ttsPauseMenu.style.display = 'none';
                updateTtsStats();
                ttsInputText.focus();
            }
        });
    });
}

function insertTextAtCursor(textarea, text) {
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const val = textarea.value;
    textarea.value = val.substring(0, start) + text + val.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + text.length;
}

// Smart Auto-Rhythm Formatter Button (Nút Tự Ngắt Nhịp Kịch Bản Chuẩn 0.5s)
const btnTtsAutoRhythm = document.getElementById('btnTtsAutoRhythm');
if (btnTtsAutoRhythm && ttsInputText) {
    btnTtsAutoRhythm.addEventListener('click', () => {
        const text = ttsInputText.value.trim();
        if (!text) {
            showToast('Vui lòng nhập hoặc dán văn bản kịch bản trước khi ngắt nhịp.', 'warning');
            ttsInputText.focus();
            return;
        }

        // 1. Remove existing pause tags temporarily to normalize
        let cleaned = text.replace(/\[pause(?:\s+[\d.]+s?)?\]/gi, ' ');

        // 2. Normalize whitespace and punctuation spacing
        cleaned = cleaned.replace(/\s+/g, ' ')
                         .replace(/\s+([,\.\!\?\:\;…])/g, '$1')
                         .replace(/([,\.\!\?\:\;…])([^\s\d,\.\!\?\:\;…])/g, '$1 $2');

        // 3. Split by sentence endings: . ! ? … \n
        const rawClauses = cleaned.split(/(?<=[\.\!\?\…])\s+|\n+/);
        const formattedSentences = [];

        for (let clause of rawClauses) {
            clause = clause.trim();
            if (!clause) continue;

            // Capitalize first letter
            clause = clause.charAt(0).toUpperCase() + clause.slice(1);

            // If sentence doesn't end with a punctuation mark, add a dot
            if (!/[.\!?…]$/.test(clause)) {
                clause += '.';
            }

            // If sentence is excessively long (> 30 words) and has commas, break into balanced parts
            const words = clause.split(' ');
            if (words.length > 30 && clause.includes(',')) {
                const subParts = clause.split(/,\s*/);
                let currentSub = '';
                for (let part of subParts) {
                    if ((currentSub + ' ' + part).split(' ').length > 22) {
                        if (currentSub) formattedSentences.push(currentSub.trim() + ',');
                        currentSub = part;
                    } else {
                        currentSub = currentSub ? currentSub + ', ' + part : part;
                    }
                }
                if (currentSub) formattedSentences.push(currentSub.trim());
            } else {
                formattedSentences.push(clause);
            }
        }

        // 4. Join sentences with clean double newlines for clear readability
        const formattedText = formattedSentences.join('\n\n');
        ttsInputText.value = formattedText;
        updateTtsStats();

        // 5. Visual button feedback and toast
        const origHtml = btnTtsAutoRhythm.innerHTML;
        btnTtsAutoRhythm.style.borderColor = '#10b981';
        btnTtsAutoRhythm.style.color = '#10b981';
        btnTtsAutoRhythm.innerHTML = `<span>✅ Đã ngắt nhịp</span>`;

        setTimeout(() => {
            btnTtsAutoRhythm.style.borderColor = '';
            btnTtsAutoRhythm.style.color = '';
            btnTtsAutoRhythm.innerHTML = origHtml;
        }, 1800);

        showToast(`✨ Đã tự động phân tách ${formattedSentences.length} câu kịch bản (nghỉ 0.5s giữa các câu)!`, 'success');
    });
}

// Paste button
const btnTtsPaste = document.getElementById('btnTtsPaste');
if (btnTtsPaste && ttsInputText) {
    btnTtsPaste.addEventListener('click', async () => {
        try {
            const clipText = await navigator.clipboard.readText();
            if (clipText) {
                if (ttsInputText.value.trim()) {
                    ttsInputText.value += '\n' + clipText;
                } else {
                    ttsInputText.value = clipText;
                }
                updateTtsStats();
                showToast('Đã dán văn bản từ bộ nhớ tạm', 'info');
                ttsInputText.focus();
            } else {
                showToast('Bộ nhớ tạm trống.', 'warning');
            }
        } catch (err) {
            showToast('Không thể truy cập Clipboard, vui lòng nhấn Ctrl+V', 'warning');
        }
    });
}

// Sample text button
const btnTtsSample = document.getElementById('btnTtsSample');
if (btnTtsSample && ttsInputText) {
    btnTtsSample.addEventListener('click', () => {
        const sample = "Chào mừng bạn đến với Studio thuyết minh AI cao cấp. [pause 1.0s] Hệ thống hỗ trợ nhận diện ngắt nghỉ linh hoạt, tạo phụ đề SRT đồng bộ từng câu chính xác và xuất file âm thanh chuẩn phòng thu.";
        ttsInputText.value = sample;
        updateTtsStats();
        showToast('Đã nạp văn bản mẫu', 'info');
        ttsInputText.focus();
    });
}

// Clear button
const btnTtsClear = document.getElementById('btnTtsClear');
if (btnTtsClear && ttsInputText) {
    btnTtsClear.addEventListener('click', () => {
        if (!ttsInputText.value.trim()) return;
        ttsInputText.value = '';
        updateTtsStats();
        showToast('Đã xóa nội dung', 'info');
    });
}

// 3. Speed Slider & Preset Chips
const speedPresetsContainer = document.getElementById('ttsSpeedPresets');
if (ttsSpeed && ttsSpeedVal) {
    ttsSpeed.addEventListener('input', () => {
        const val = parseFloat(ttsSpeed.value);
        ttsSpeedVal.textContent = val.toFixed(2) + 'x';
        updateTtsStats();
        
        // Highlight active preset chip if matching
        if (speedPresetsContainer) {
            speedPresetsContainer.querySelectorAll('.chip-btn').forEach(chip => {
                const s = parseFloat(chip.getAttribute('data-speed'));
                if (Math.abs(s - val) < 0.03) {
                    chip.classList.add('active');
                } else {
                    chip.classList.remove('active');
                }
            });
        }
    });
}

if (speedPresetsContainer && ttsSpeed && ttsSpeedVal) {
    speedPresetsContainer.querySelectorAll('.chip-btn').forEach(chip => {
        chip.addEventListener('click', () => {
            const targetSpeed = parseFloat(chip.getAttribute('data-speed'));
            if (!isNaN(targetSpeed)) {
                ttsSpeed.value = targetSpeed;
                ttsSpeedVal.textContent = targetSpeed.toFixed(2) + 'x';
                if (typeof updateSliderTrack === 'function') {
                    updateSliderTrack(ttsSpeed);
                }
                speedPresetsContainer.querySelectorAll('.chip-btn').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                updateTtsStats();
            }
        });
    });
}

// 3.5 Multi-threading Parallel Workers Slider
const ttsThreads = document.getElementById('ttsThreads');
const ttsThreadsVal = document.getElementById('ttsThreadsVal');
if (ttsThreads && ttsThreadsVal) {
    ttsThreads.addEventListener('input', () => {
        const val = parseInt(ttsThreads.value, 10);
        ttsThreadsVal.textContent = `${val} luồng (${val >= 16 ? 'Siêu tốc' : (val >= 8 ? 'Nhanh' : 'Tiết kiệm')})`;
    });
}

// 4. Output Directory Picker
async function handleSelectTtsOutputDir() {
    try {
        const dir = await selectDirectory('Chọn thư mục lưu file audio TTS');
        if (dir) {
            window.currentTtsOutputDir = dir;
            localStorage.setItem('tts_output_dir', dir);
            if (ttsOutputDirDisplay) {
                ttsOutputDirDisplay.innerText = `Thư mục: ${dir}`;
                ttsOutputDirDisplay.title = dir;
            }
            showToast(`Đã chọn thư mục lưu audio: ${dir}`, 'success');
        }
    } catch (e) {
        console.error("Lỗi chọn thư mục TTS:", e);
    }
}

if (btnSelectTtsOutputDir) {
    btnSelectTtsOutputDir.addEventListener('click', (e) => {
        e.stopPropagation();
        handleSelectTtsOutputDir();
    });
}

const ttsDirPickerContainer = document.getElementById('ttsDirPickerContainer');
if (ttsDirPickerContainer) {
    ttsDirPickerContainer.addEventListener('click', () => {
        handleSelectTtsOutputDir();
    });
}

// 5. History Count & Clear
function updateHistoryCounter() {
    const historyList = document.getElementById('ttsHistoryList');
    if (!historyList) return;
    const items = historyList.querySelectorAll('.history-item');
    if (ttsHistoryCount) {
        ttsHistoryCount.textContent = `${items.length} tác vụ • Nhấp vào sóng âm Waveform để tua và nghe`;
    }
    // Dynamic height threshold: <= 3 cards expand naturally with no scroll, > 3 cards activates scrollbar
    if (items.length > 3) {
        historyList.classList.add('has-scroll');
    } else {
        historyList.classList.remove('has-scroll');
    }
}

if (btnClearTtsHistory) {
    btnClearTtsHistory.addEventListener('click', () => {
        const historyList = document.getElementById('ttsHistoryList');
        const placeholder = document.getElementById('ttsResultPlaceholder');
        if (historyList) {
            const items = historyList.querySelectorAll('.history-item');
            if (items.length === 0) return;
            items.forEach(i => i.remove());
            if (placeholder) placeholder.style.display = 'block';
            updateHistoryCounter();
            showToast('Đã xóa danh sách lịch sử TTS', 'info');
        }
    });
}

// Global active audio / wavesurfer tracker (ensures only one audio plays at a time)
let currentActivePlayer = null;
let currentActiveBtn = null;

// Audio Player & High-Density Vector Waveform Engine
function setupAudioPlayerForHistoryItem(historyItem, audioUrl, defaultDuration = 0) {
    const wfContainer = historyItem.querySelector('.hi-waveform-container');
    const durationEl = historyItem.querySelector('.hi-duration');
    const playBtn = historyItem.querySelector('.btn-play-purple');
    if (!playBtn || !audioUrl || !wfContainer) return;

    function formatTime(sec) {
        if (!sec || isNaN(sec) || sec < 0) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    const barCount = 110;
    const initialHeights = [];
    for (let i = 0; i < barCount; i++) {
        const norm = i / barCount;
        const envelope = Math.sin(norm * Math.PI);
        const speechPattern = Math.sin(i * 0.7) * 0.35 + Math.cos(i * 1.5) * 0.25 + 0.55;
        const h = Math.max(14, Math.min(96, Math.round(envelope * speechPattern * 80 + 14)));
        initialHeights.push(h);
    }

    const uid = 'wf_' + Math.random().toString(36).substr(2, 9);
    const audio = new Audio(audioUrl);
    let knownDuration = defaultDuration || 0;

    wfContainer.innerHTML = `
        <div class="dense-svg-wf" style="width: 100%; height: 36px; position: relative; display: flex; align-items: center; cursor: pointer; user-select: none;">
            <svg viewBox="0 0 ${barCount * 3} 36" preserveAspectRatio="none" style="width: 100%; height: 34px; display: block; overflow: visible;">
                <defs>
                    <linearGradient id="grad_${uid}" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stop-color="#38bdf8"/>
                        <stop offset="100%" stop-color="#a855f7"/>
                    </linearGradient>
                    <clipPath id="clip_${uid}">
                        <rect class="wf-clip-rect" x="0" y="0" width="0" height="36"/>
                    </clipPath>
                </defs>
                <g class="wf-bars-bg" fill="#334155">
                    ${initialHeights.map((h, i) => {
                        const barH = Math.max(4, h * 0.32);
                        const y = (36 - barH) / 2;
                        return `<rect x="${i * 3}" y="${y}" width="2" height="${barH}" rx="1"/>`;
                    }).join('')}
                </g>
                <g class="wf-bars-fg" fill="url(#grad_${uid})" clip-path="url(#clip_${uid})">
                    ${initialHeights.map((h, i) => {
                        const barH = Math.max(4, h * 0.32);
                        const y = (36 - barH) / 2;
                        return `<rect x="${i * 3}" y="${y}" width="2" height="${barH}" rx="1"/>`;
                    }).join('')}
                </g>
            </svg>
            <div class="wf-cursor-handle" style="position: absolute; left: 0%; top: 0px; bottom: 0px; width: 2px; background: #38bdf8; box-shadow: 0 0 8px #38bdf8; pointer-events: none; transition: left 0.04s linear;">
                <div style="position: absolute; top: -1px; left: -3px; width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 6px #38bdf8;"></div>
            </div>
        </div>
    `;

    const svgWrapper = wfContainer.querySelector('.dense-svg-wf');
    const clipRect = wfContainer.querySelector('.wf-clip-rect');
    const cursor = wfContainer.querySelector('.wf-cursor-handle');
    const totalSvgWidth = barCount * 3;

    function updateProgress(pct) {
        pct = Math.max(0, Math.min(1, pct));
        if (clipRect) clipRect.setAttribute('width', (pct * totalSvgWidth).toString());
        if (cursor) cursor.style.left = `${pct * 100}%`;
    }

    // Try background real PCM Audio decode to replace heights with actual voice amplitude
    // BẢO VỆ BỘ NHỚ WEBVIEW2: Chỉ giải mã PCM cho file ngắn (thời lượng <= 45s) để chống tràn RAM/crash WebView2
    if (knownDuration > 0 && knownDuration <= 45) {
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                fetch(audioUrl)
                    .then(r => {
                        const clen = r.headers.get('content-length');
                        if (clen && parseInt(clen, 10) > 6 * 1024 * 1024) {
                            return null; // Bỏ qua file > 6MB để bảo vệ bộ nhớ WebView2
                        }
                        return r.arrayBuffer();
                    })
                    .then(buf => {
                        if (!buf) return null;
                        const actx = new AudioContextClass();
                        const p = actx.decodeAudioData(buf);
                        p.finally(() => {
                            try { actx.close(); } catch(e) {}
                        });
                        return p;
                    })
                    .then(audioBuffer => {
                        if (!audioBuffer) return;
                        const raw = audioBuffer.getChannelData(0);
                        const blockSize = Math.floor(raw.length / barCount);
                        if (blockSize <= 0) return;
                        const newHeights = [];
                        let maxAmp = 0.001;

                        for (let i = 0; i < barCount; i++) {
                            const start = i * blockSize;
                            let peak = 0;
                            const step = Math.max(1, Math.floor(blockSize / 8));
                            for (let j = 0; j < blockSize; j += step) {
                                const val = Math.abs(raw[start + j] || 0);
                                if (val > peak) peak = val;
                            }
                            newHeights.push(peak);
                            if (peak > maxAmp) maxAmp = peak;
                        }

                        const bgG = wfContainer.querySelector('.wf-bars-bg');
                        const fgG = wfContainer.querySelector('.wf-bars-fg');
                        if (bgG && fgG) {
                            const rectsHtml = newHeights.map((p, i) => {
                                const normalized = Math.pow(p / maxAmp, 0.7);
                                const h = Math.max(4, normalized * 32);
                                const y = (36 - h) / 2;
                                return `<rect x="${i * 3}" y="${y}" width="2" height="${h}" rx="1"/>`;
                            }).join('');
                            bgG.innerHTML = rectsHtml;
                            fgG.innerHTML = rectsHtml;
                        }
                    })
                    .catch(err => {
                        console.warn("[Waveform] Skipped dynamic amplitude decoding:", err);
                    });
            }
        } catch (e) {
            console.warn(e);
        }
    }

    let isDragging = false;
    function seekFromEvent(e) {
        const rect = svgWrapper.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const total = audio.duration || knownDuration;
        if (total && !isNaN(total) && total > 0) {
            audio.currentTime = pct * total;
            updateProgress(pct);
            if (durationEl) durationEl.textContent = `${formatTime(audio.currentTime)} / ${formatTime(total)}`;
        }
    }

    svgWrapper.addEventListener('mousedown', (e) => {
        isDragging = true;
        seekFromEvent(e);
    });

    window.addEventListener('mousemove', (e) => {
        if (isDragging) seekFromEvent(e);
    });

    window.addEventListener('mouseup', () => {
        isDragging = false;
    });

    svgWrapper.addEventListener('touchstart', (e) => {
        isDragging = true;
        seekFromEvent(e);
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
        if (isDragging) seekFromEvent(e);
    }, { passive: true });

    window.addEventListener('touchend', () => {
        isDragging = false;
    });

    audio.addEventListener('timeupdate', () => {
        if (isDragging) return;
        const cur = audio.currentTime;
        const total = audio.duration || knownDuration;
        const pct = total > 0 ? cur / total : 0;
        updateProgress(pct);
        if (durationEl) durationEl.textContent = `${formatTime(cur)} / ${formatTime(total)}`;
    });

    audio.addEventListener('loadedmetadata', () => {
        if (audio.duration && !isNaN(audio.duration)) {
            knownDuration = audio.duration;
            if (durationEl) durationEl.textContent = `0:00 / ${formatTime(knownDuration)}`;
        }
    });

    audio.addEventListener('play', () => {
        if (currentActivePlayer && currentActivePlayer !== audio) {
            if (typeof currentActivePlayer.pause === 'function') currentActivePlayer.pause();
            if (currentActiveBtn) {
                currentActiveBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
            }
        }
        currentActivePlayer = audio;
        currentActiveBtn = playBtn;

        playBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>`;
    });

    audio.addEventListener('pause', () => {
        playBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
    });

    audio.addEventListener('ended', () => {
        playBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
        const total = audio.duration || knownDuration;
        if (durationEl) durationEl.textContent = `0:00 / ${formatTime(total)}`;
        updateProgress(0);
    });

    playBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (audio.paused) {
            audio.play().catch(err => console.warn("Audio play error:", err));
        } else {
            audio.pause();
        }
    });

    const delBtn = historyItem.querySelector('.hi-delete');
    if (delBtn) {
        delBtn.addEventListener('click', () => {
            if (!audio.paused) audio.pause();
            audio.src = '';
        });
    }
}

// 6. Generate TTS Execution Handler
if (btnGenerateTTS) {
    btnGenerateTTS.addEventListener('click', async () => {
        if (!checkFeaturePermission('tts_unlimited_local', 'Tạo giọng đọc AI TTS')) return;

        const text = ttsInputText ? ttsInputText.value.trim() : '';
        if (!text) {
            showToast('Vui lòng nhập nội dung văn bản kịch bản cần đọc.', 'warning');
            if (ttsInputText) ttsInputText.focus();
            return;
        }

        const originalBtnHtml = btnGenerateTTS.innerHTML;
        btnGenerateTTS.innerHTML = `<div class="btn-glow-layer"></div><svg class="loading-spin" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg> <span>ĐANG TẠO GIỌNG ĐỌC...</span>`;
        btnGenerateTTS.disabled = true;

        // Hide empty placeholder
        const placeholder = document.getElementById('ttsResultPlaceholder');
        if (placeholder) placeholder.style.display = 'none';

        const historyList = document.getElementById('ttsHistoryList');
        const template = document.getElementById('historyItemTemplate');
        if (!historyList || !template) {
            btnGenerateTTS.innerHTML = originalBtnHtml;
            btnGenerateTTS.disabled = false;
            return;
        }

        // Create new history item
        const clone = template.content.cloneNode(true);
        const historyItem = clone.querySelector('.history-item');
        const promptRowEl = historyItem.querySelector('.hi-prompt-row');
        if (promptRowEl) {
            promptRowEl.textContent = text;
            promptRowEl.title = text; // Hover tooltip showing full text
        }

        // Fill initial data
        const badge = historyItem.querySelector('.hi-badge');
        badge.textContent = 'Đang xử lý';
        badge.className = 'hi-badge badge-processing';

        const selectedVoiceNameEl = document.getElementById('selectedVoiceName');
        const voiceName = selectedVoiceNameEl ? selectedVoiceNameEl.textContent.trim() : (ttsVoice ? ttsVoice.value : 'Ngọc Huyền');
        historyItem.querySelector('.voice-name').textContent = voiceName;

        const now = new Date();
        const timeFormatted = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) + ' • ' + now.toLocaleDateString();
        historyItem.querySelector('.time-text').textContent = timeFormatted;
        historyItem.querySelector('.speed-val').textContent = parseFloat(ttsSpeed ? ttsSpeed.value : 1.0).toFixed(2);

        // Add to DOM
        historyList.insertBefore(historyItem, historyList.firstChild);
        updateHistoryCounter();

        // Remix button (re-use text)
        const btnRemix = historyItem.querySelector('.hi-remix');
        if (btnRemix && ttsInputText) {
            btnRemix.addEventListener('click', () => {
                ttsInputText.value = text;
                updateTtsStats();
                ttsInputText.scrollIntoView({ behavior: 'smooth', block: 'center' });
                ttsInputText.focus();
                showToast('Đã nạp lại văn bản vào ô soạn thảo', 'info');
            });
        }

        // Setup delete button early
        historyItem.querySelector('.hi-delete').addEventListener('click', () => {
            historyItem.remove();
            const items = historyList.querySelectorAll('.history-item');
            if (items.length === 0 && placeholder) {
                placeholder.style.display = 'block';
            }
            updateHistoryCounter();
        });

        // Start progress simulation
        const progressFill = historyItem.querySelector('.hi-progress-fill');
        const progressPct = historyItem.querySelector('.hi-progress-pct');
        let currentPct = 10;
        const progressInterval = setInterval(() => {
            if (currentPct < 90) {
                currentPct += Math.floor(Math.random() * 12) + 5;
                if (currentPct > 90) currentPct = 90;
                if (progressFill) progressFill.style.width = `${currentPct}%`;
                if (progressPct) progressPct.textContent = `${currentPct}%`;
            }
        }, 300);

        try {
            const voiceVal = ttsVoice ? ttsVoice.value : 'ngoc_huyen';
            const isLocalOrFree = ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_heart', 'en_michael', 'en_nicole', 'kokoro'].includes(voiceVal) || voiceVal.startsWith('edge_') || voiceVal.startsWith('rvc_') || voiceVal.startsWith('local_');
            const endpoint = isLocalOrFree ? '/api/tts/kokoro' : '/api/tts/openspeaker';

            const threadsVal = parseInt(ttsThreads ? ttsThreads.value : 16, 10) || 16;
            const payload = {
                text: text,
                voice: voiceVal,
                speed: parseFloat(ttsSpeed ? ttsSpeed.value : 1.0) || 1.0,
                threads: threadsVal,
                tts_threads: threadsVal,
                output_dir: window.currentTtsOutputDir || 'output',
                filename: ttsOutputName && ttsOutputName.value.trim() ? ttsOutputName.value.trim() : null
            };

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            clearInterval(progressInterval);

            if (data.success) {
                if (progressFill) progressFill.style.width = '100%';
                if (progressPct) progressPct.textContent = '100%';

                // Switch states
                setTimeout(() => {
                    const procState = historyItem.querySelector('.hi-processing-state');
                    const compState = historyItem.querySelector('.hi-completed-state');
                    if (procState) procState.style.display = 'none';
                    if (compState) compState.style.display = 'flex';
                    badge.textContent = 'Hoàn tất';
                    badge.className = 'hi-badge badge-completed';

                    // Khởi tạo trình phát và sóng âm waveform tương tác
                    if (data.audio_url) {
                        setupAudioPlayerForHistoryItem(historyItem, data.audio_url, data.duration || 0);
                    }

                    // Direct Audio Download Button
                    const btnDownloadAudio = historyItem.querySelector('.hi-download-audio');
                    if (btnDownloadAudio && data.audio_url) {
                        btnDownloadAudio.style.display = 'inline-flex';
                        btnDownloadAudio.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const a = document.createElement('a');
                            a.href = data.audio_url;
                            let filename = data.filename || 'tts_voice.wav';
                            if (data.absolute_path) {
                                filename = data.absolute_path.split(/[\/\\]/).pop();
                            }
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        });
                    }

                    // SRT Download Button
                    const btnSrt = historyItem.querySelector('.hi-srt');
                    if (btnSrt && data.srt_url) {
                        btnSrt.style.display = 'inline-flex';
                        btnSrt.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const a = document.createElement('a');
                            a.href = data.srt_url;
                            let filename = 'phude_tts.srt';
                            if (data.srt_absolute_path) {
                                filename = data.srt_absolute_path.split(/[\/\\]/).pop();
                            }
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        });
                    }

                    // Open Folder Button
                    const openBtn = historyItem.querySelector('.hi-open');
                    if (openBtn && data.absolute_path) {
                        openBtn.style.display = 'inline-flex';
                        openBtn.addEventListener('click', async (e) => {
                            e.stopPropagation();
                            if (window.pywebview) {
                                await window.pywebview.api.open_in_explorer(data.absolute_path);
                            } else {
                                fetch('/api/open_folder', {
                                    method: 'POST',
                                    headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify({ path: data.absolute_path })
                                }).catch(console.warn);
                            }
                        });
                    }

                    showToast('Đã tạo file giọng đọc AI thành công!', 'success');
                }, 300);
            } else {
                badge.textContent = 'Lỗi tạo giọng';
                badge.className = 'hi-badge';
                badge.style.background = 'rgba(239, 68, 68, 0.15)';
                badge.style.color = '#ef4444';
                badge.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                const procText = historyItem.querySelector('.hi-processing-text');
                if (procText) procText.textContent = 'Lỗi: ' + (data.error || 'Không xác định');
                showToast(data.error || 'Lỗi khi tạo giọng đọc TTS', 'error');
            }
        } catch (e) {
            clearInterval(progressInterval);
            badge.textContent = 'Lỗi kết nối';
            badge.style.color = '#ef4444';
            showToast('Lỗi kết nối máy chủ khi tạo TTS.', 'error');
        } finally {
            btnGenerateTTS.innerHTML = originalBtnHtml;
            btnGenerateTTS.disabled = false;
        }
    });
}

// =========================================================================
// ADVANCED VOICE SELECTION MODAL & LIBRARY CONTROLLER (HIGH PERFORMANCE)
// =========================================================================
let allLoadedVoices = [];
let currentVoiceProviderFilter = '';
let currentPreviewAudio = null;
let currentFilteredVoices = [];
let currentlyRenderedCount = 0;
const VOICE_PAGE_CHUNK = 40;

const voiceModal = document.getElementById('voiceModal');
const btnOpenVoiceModal = document.getElementById('btnOpenVoiceModal');
const btnCloseVoiceModal = document.getElementById('btnCloseVoiceModal');
const btnReloadVoices = document.getElementById('btnReloadVoices');
const voiceGrid = document.getElementById('voiceGrid');
const voiceSearch = document.getElementById('voiceSearch');
const voiceFilterLang = document.getElementById('voiceFilterLang');
const voiceFilterRegion = document.getElementById('voiceFilterRegion');
const voiceFilterGender = document.getElementById('voiceFilterGender');
const voiceFilterAge = document.getElementById('voiceFilterAge');
const voiceFilterStyle = document.getElementById('voiceFilterStyle');
const voiceFilterCount = document.getElementById('voiceFilterCount');
const btnResetVoiceFilters = document.getElementById('btnResetVoiceFilters');
const voiceModalTabs = document.getElementById('voiceModalTabs');

async function fetchAndRenderVoiceLibrary(force = false) {
    if (!force && allLoadedVoices.length > 0) {
        renderFilteredVoices();
        return;
    }
    try {
        const res = await fetch('/api/voices');
        allLoadedVoices = await res.json();
        renderFilteredVoices();
    } catch (e) {
        console.error("Lỗi tải danh sách giọng:", e);
    }
}
window.fetchAndRenderVoiceLibrary = fetchAndRenderVoiceLibrary;

function createVoiceCard(v) {
    const currentActiveVoice = (document.getElementById('reviewVoiceSelect')?.value) || (ttsVoice?.value) || (document.getElementById('dubbingVoiceInput')?.value) || 'ngoc_huyen';
    const isCurrent = (currentActiveVoice === v.id);
    const card = document.createElement('div');
    card.className = `voice-modal-item ${isCurrent ? 'active' : ''}`;
    card.style.cssText = `
        background: #111a2e;
        border: 1px solid ${isCurrent ? '#38bdf8' : '#1e293b'};
        border-radius: 12px;
        padding: 14px 16px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 12px;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: ${isCurrent ? '0 0 16px rgba(56, 189, 248, 0.25)' : '0 2px 8px rgba(0,0,0,0.2)'};
    `;

    let providerBadgeColor = '#0284c7';
    if (v.provider === 'local_voice') providerBadgeColor = '#10b981';
    else if (v.provider === 'rvc') providerBadgeColor = '#c084fc';
    else if (v.provider === 'edge') providerBadgeColor = '#38bdf8';
    else if (v.provider === 'vbee') providerBadgeColor = '#10b981';
    else if (v.provider === 'minimax') providerBadgeColor = '#f59e0b';
    else if (v.provider === 'elevenlabs') providerBadgeColor = '#a855f7';
    else if (v.provider === 'fishaudio') providerBadgeColor = '#f43f5e';

    const styleBadge = v.style === 'review' ? '🎬 Review' : (v.style === 'story' ? '🎙️ Kể chuyện' : (v.style === 'news' ? '📰 Thời sự' : (v.style === 'emotional' ? '💖 Tâm sự' : (v.style === 'action' ? '⚡ Hành động' : (v.style === 'anime' ? '🎀 Anime' : '')))));

    card.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
            <div style="width: 44px; height: 44px; border-radius: 10px; background: #0f172a; border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
                ${escapeHtml(v.avatar || '🎙️')}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
                    <span style="font-size: 14px; font-weight: 700; color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</span>
                    <span style="font-size: 10px; padding: 2px 7px; border-radius: 4px; background: ${providerBadgeColor}18; color: ${providerBadgeColor}; border: 1px solid ${providerBadgeColor}40; text-transform: uppercase; font-weight: 700; white-space: nowrap;">${escapeHtml(v.provider_name || v.provider)}</span>
                </div>
                <div style="font-size: 11.5px; color: #94a3b8; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    ${escapeHtml(v.tag || `${v.region || ''} • ${v.lang}`)}
                </div>
            </div>
        </div>
        
        <div style="display: flex; align-items: center; justify-content: space-between; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px; margin-top: 2px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 11px; color: #64748b;">${v.gender === 'Female' ? 'Nữ' : 'Nam'} • ${escapeHtml(v.region || v.lang)}</span>
                ${styleBadge ? `<span style="font-size: 10px; background: #1e293b; color: #94a3b8; padding: 1px 5px; border-radius: 4px; border: 1px solid #334155;">${styleBadge}</span>` : ''}
            </div>
            
            <div style="display: flex; align-items: center; gap: 8px;">
                <button type="button" class="btn-voice-preview-modal" style="display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; font-size: 11.5px; font-weight: 600; background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 6px; cursor: pointer; transition: all 0.2s;" title="Nghe thử giọng này">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                    <span>Thử</span>
                </button>
                <button type="button" class="btn-select-voice" style="padding: 5px 12px; font-size: 12px; font-weight: 600; background: ${isCurrent ? '#38bdf8' : '#1e293b'}; color: ${isCurrent ? '#0f172a' : '#f8fafc'}; border: 1px solid ${isCurrent ? '#38bdf8' : '#334155'}; border-radius: 6px; cursor: pointer; transition: all 0.2s ease;">
                    ${isCurrent ? '✓ Đang dùng' : 'Chọn'}
                </button>
            </div>
        </div>
    `;

    const btnPreview = card.querySelector('.btn-voice-preview-modal');
    btnPreview.addEventListener('click', (e) => {
        e.stopPropagation();
        window.playPreviewVoice(v.id, btnPreview);
    });

    const btnSelect = card.querySelector('.btn-select-voice');
    btnSelect.addEventListener('click', () => {
        if (ttsVoice) ttsVoice.value = v.id;
        const selectedVoiceNameEl = document.getElementById('selectedVoiceName');
        const selectedVoiceTagEl = document.getElementById('selectedVoiceTag');
        const ttsVoiceAvatarEl = document.getElementById('ttsVoiceAvatar');

        if (selectedVoiceNameEl) selectedVoiceNameEl.textContent = v.name;
        if (selectedVoiceTagEl) selectedVoiceTagEl.textContent = v.tag || `${v.provider_name || v.provider} • ${v.lang}`;
        if (ttsVoiceAvatarEl) ttsVoiceAvatarEl.textContent = v.avatar || '🎙️';

        const reviewVoiceSelect = document.getElementById('reviewVoiceSelect');
        const reviewSelectedVoiceName = document.getElementById('reviewSelectedVoiceName');
        if (reviewVoiceSelect) reviewVoiceSelect.value = v.id;
        if (reviewSelectedVoiceName) reviewSelectedVoiceName.textContent = v.name;

        const comicVoiceSelect = document.getElementById('comicVoiceSelect');
        const comicSelectedVoiceName = document.getElementById('comicSelectedVoiceName');
        const comicVoiceAvatar = document.getElementById('comicVoiceAvatar');
        if (comicVoiceSelect) comicVoiceSelect.value = v.id;
        if (comicSelectedVoiceName) comicSelectedVoiceName.textContent = v.name;
        if (comicVoiceAvatar) comicVoiceAvatar.textContent = v.avatar || '🎙️';

        const dubbingVoiceInput = document.getElementById('dubbingVoiceInput');
        const dubbingSelectedVoiceName = document.getElementById('dubbingSelectedVoiceName');
        if (dubbingVoiceInput) dubbingVoiceInput.value = v.id;
        window.liveDubbingEngine?.stop();
        if (dubbingSelectedVoiceName) dubbingSelectedVoiceName.textContent = v.name;

        const batchDubbingVoiceInput = document.getElementById('batch_dubbingVoiceInput');
        const batchDubbingSelectedVoiceName = document.getElementById('batch_dubbingSelectedVoiceName');
        if (batchDubbingVoiceInput) batchDubbingVoiceInput.value = v.id;
        if (batchDubbingSelectedVoiceName) batchDubbingSelectedVoiceName.textContent = v.name;

        voiceModal.style.display = 'none';
        showToast(`Đã chuyển sang giọng đọc: ${v.name}`, 'success');
    });

    return card;
}

function appendMoreVoices() {
    if (!voiceGrid || currentlyRenderedCount >= currentFilteredVoices.length) return;
    const fragment = document.createDocumentFragment();
    const nextBatch = currentFilteredVoices.slice(currentlyRenderedCount, currentlyRenderedCount + VOICE_PAGE_CHUNK);
    nextBatch.forEach(v => {
        fragment.appendChild(createVoiceCard(v));
    });
    currentlyRenderedCount += nextBatch.length;
    
    // Remove previous load trigger if any
    const oldTrigger = document.getElementById('voiceGridLoadTrigger');
    if (oldTrigger) oldTrigger.remove();
    
    voiceGrid.appendChild(fragment);
    
    if (currentlyRenderedCount < currentFilteredVoices.length) {
        const trigger = document.createElement('div');
        trigger.id = 'voiceGridLoadTrigger';
        trigger.style.cssText = 'grid-column: 1 / -1; text-align: center; padding: 16px;';
        trigger.innerHTML = `<button type="button" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 8px 20px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;">Xem thêm (${currentFilteredVoices.length - currentlyRenderedCount} giọng còn lại)...</button>`;
        trigger.querySelector('button').addEventListener('click', appendMoreVoices);
        voiceGrid.appendChild(trigger);
    }
}

function renderFilteredVoices() {
    if (!voiceGrid) return;
    voiceGrid.innerHTML = '';
    currentlyRenderedCount = 0;

    const searchTerm = voiceSearch ? voiceSearch.value.trim().toLowerCase() : '';
    const selectedLang = voiceFilterLang ? voiceFilterLang.value : '';
    const selectedRegion = voiceFilterRegion ? voiceFilterRegion.value : '';
    const selectedGender = voiceFilterGender ? voiceFilterGender.value : '';
    const selectedAge = voiceFilterAge ? voiceFilterAge.value : '';
    const selectedStyle = voiceFilterStyle ? voiceFilterStyle.value : '';

    currentFilteredVoices = allLoadedVoices.filter(v => {
        if (currentVoiceProviderFilter && v.provider !== currentVoiceProviderFilter) return false;
        if (selectedLang && v.lang !== selectedLang) return false;
        if (selectedRegion && v.region && !v.region.includes(selectedRegion)) return false;
        if (selectedGender && v.gender !== selectedGender) return false;
        if (selectedAge && v.age !== selectedAge) return false;
        if (selectedStyle && v.style !== selectedStyle) return false;
        if (searchTerm) {
            const matchName = v.name && v.name.toLowerCase().includes(searchTerm);
            const matchId = v.id && v.id.toLowerCase().includes(searchTerm);
            const matchTag = v.tag && v.tag.toLowerCase().includes(searchTerm);
            const matchRegion = v.region && v.region.toLowerCase().includes(searchTerm);
            const matchProvider = (v.provider_name || v.provider || '').toLowerCase().includes(searchTerm);
            if (!matchName && !matchId && !matchTag && !matchRegion && !matchProvider) return false;
        }
        return true;
    });

    if (voiceFilterCount) {
        voiceFilterCount.textContent = `${currentFilteredVoices.length} / ${allLoadedVoices.length} giọng`;
    }

    if (currentFilteredVoices.length === 0) {
        voiceGrid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 48px 20px; color: #64748b;">
                <svg viewBox="0 0 24 24" width="40" height="40" stroke="currentColor" stroke-width="1.5" fill="none" style="margin-bottom: 12px; opacity: 0.5;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                <div style="font-size: 15px; font-weight: 600; color: #cbd5e1; margin-bottom: 4px;">Không tìm thấy giọng đọc phù hợp</div>
                <div style="font-size: 13px;">Hãy thử điều chỉnh từ khóa tìm kiếm hoặc bấm "Đặt lại" để xóa các bộ lọc.</div>
            </div>
        `;
        return;
    }

    appendMoreVoices();
}

if (voiceGrid) {
    voiceGrid.addEventListener('scroll', () => {
        if (voiceGrid.scrollTop + voiceGrid.clientHeight >= voiceGrid.scrollHeight - 150) {
            appendMoreVoices();
        }
    });
}

// Voice Modal Global Handler
window.openVoiceLibraryModal = function() {
    const modal = document.getElementById('voiceModal');
    if (modal) {
        modal.style.display = 'flex';
        fetchAndRenderVoiceLibrary();
    }
};

// Voice Modal Event Listeners
if (btnOpenVoiceModal) {
    btnOpenVoiceModal.addEventListener('click', () => {
        window.openVoiceLibraryModal();
    });
}

const btnOpenVoiceModalReview = document.getElementById('btnOpenVoiceModalReview');
if (btnOpenVoiceModalReview) {
    btnOpenVoiceModalReview.addEventListener('click', (e) => {
        if (e.target.closest('.btn-preview-voice') || e.target.closest('.btn-voice-preview')) return;
        window.openVoiceLibraryModal();
    });
}

const btnOpenVoiceModalDubbing = document.getElementById('btnOpenVoiceModalDubbing');
if (btnOpenVoiceModalDubbing) {
    btnOpenVoiceModalDubbing.addEventListener('click', (e) => {
        if (e.target.closest('.btn-preview-voice') || e.target.closest('.btn-voice-preview')) return;
        window.openVoiceLibraryModal();
    });
}

const btnOpenVoiceModalComic = document.getElementById('btnOpenVoiceModalComic');
if (btnOpenVoiceModalComic) {
    btnOpenVoiceModalComic.addEventListener('click', (e) => {
        if (e.target.closest('.btn-preview-voice') || e.target.closest('.btn-voice-preview')) return;
        window.openVoiceLibraryModal();
    });
}

if (btnCloseVoiceModal && voiceModal) {
    btnCloseVoiceModal.addEventListener('click', () => {
        voiceModal.style.display = 'none';
    });
}

if (voiceModal) {
    voiceModal.addEventListener('click', (e) => {
        if (e.target === voiceModal) {
            voiceModal.style.display = 'none';
        }
    });
}

if (btnReloadVoices) {
    btnReloadVoices.addEventListener('click', async () => {
        showToast('Đang kết nối OpenSpeaker API đồng bộ danh sách giọng mới...', 'info');
        btnReloadVoices.disabled = true;
        btnReloadVoices.innerHTML = `&#x21bb; Đang tải...`;
        try {
            const res = await fetch('/api/voices/refresh', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã đồng bộ thành công ${data.count} giọng đọc từ OpenSpeaker!`, 'success');
                fetchAndRenderVoiceLibrary(true);
            }
        } catch (e) {
            console.warn("Lỗi làm mới giọng:", e);
        } finally {
            btnReloadVoices.disabled = false;
            btnReloadVoices.innerHTML = `&#x21bb; Làm mới`;
        }
    });
}

if (voiceModalTabs) {
    voiceModalTabs.querySelectorAll('.voice-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            voiceModalTabs.querySelectorAll('.voice-tab').forEach(t => {
                t.classList.remove('active');
                t.style.borderBottom = 'none';
                t.style.color = '#94a3b8';
            });
            tab.classList.add('active');
            tab.style.borderBottom = '2px solid #38bdf8';
            tab.style.color = '#38bdf8';
            currentVoiceProviderFilter = tab.getAttribute('data-provider') || '';
            renderFilteredVoices();
        });
    });
}

if (btnResetVoiceFilters) {
    btnResetVoiceFilters.addEventListener('click', () => {
        if (voiceSearch) voiceSearch.value = '';
        if (voiceFilterLang) voiceFilterLang.value = '';
        if (voiceFilterRegion) voiceFilterRegion.value = '';
        if (voiceFilterGender) voiceFilterGender.value = '';
        if (voiceFilterAge) voiceFilterAge.value = '';
        if (voiceFilterStyle) voiceFilterStyle.value = '';
        currentVoiceProviderFilter = '';
        if (voiceModalTabs) {
            voiceModalTabs.querySelectorAll('.voice-tab').forEach((t, i) => {
                if (i === 0) {
                    t.classList.add('active');
                    t.style.borderBottom = '2px solid #38bdf8';
                    t.style.color = '#38bdf8';
                } else {
                    t.classList.remove('active');
                    t.style.borderBottom = 'none';
                    t.style.color = '#94a3b8';
                }
            });
        }
        renderFilteredVoices();
        showToast('Đã đặt lại tất cả bộ lọc', 'info');
    });
}

// Debounce helper for instant, lag-free filtering
let voiceFilterTimeout = null;
function debouncedRenderFilteredVoices() {
    if (voiceFilterTimeout) clearTimeout(voiceFilterTimeout);
    voiceFilterTimeout = setTimeout(renderFilteredVoices, 100);
}

if (voiceSearch) {
    voiceSearch.addEventListener('input', debouncedRenderFilteredVoices);
}

[voiceFilterLang, voiceFilterRegion, voiceFilterGender, voiceFilterAge, voiceFilterStyle].forEach(el => {
    if (el) {
        el.addEventListener('change', renderFilteredVoices);
    }
});

// Voice Preview Player Helper
let activePreviewBtn = null;

function setPreviewBtnState(btn, state) {
    if (!btn) return;
    const isRound = btn.hasAttribute('data-target') || btn.classList.contains('btn-voice-preview') || !btn.querySelector('span');
    if (state === 'loading') {
        btn.innerHTML = `<svg class="loading-spin" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path></svg>` + (isRound ? '' : ' <span>Đang nạp...</span>');
    } else if (state === 'playing') {
        btn.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>` + (isRound ? '' : ' <span>Đang phát</span>');
    } else {
        // idle
        btn.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>` + (isRound ? '' : ' <span>Nghe thử</span>');
    }
}

window.playPreviewVoice = async function(voiceId, btnEl) {
    try {
        if (currentPreviewAudio) {
            currentPreviewAudio.pause();
            currentPreviewAudio = null;
            if (activePreviewBtn) {
                setPreviewBtnState(activePreviewBtn, 'idle');
            }
            if (activePreviewBtn === btnEl) {
                activePreviewBtn = null;
                return;
            }
        }

        activePreviewBtn = btnEl;
        if (btnEl) {
            setPreviewBtnState(btnEl, 'loading');
        }

        let sampleUrl = '';

        // 1. Kiểm tra URL nghe thử trực tiếp từ danh sách voice đã nạp
        if (typeof allLoadedVoices !== 'undefined' && Array.isArray(allLoadedVoices)) {
            const found = allLoadedVoices.find(v => v.id === voiceId);
            if (found && found.preview_url && found.preview_url.trim()) {
                sampleUrl = found.preview_url.trim();
            }
        }

        // 2. Mẫu âm thanh tĩnh cục bộ
        if (!sampleUrl) {
            if (voiceId === 'diem_trinh') sampleUrl = '/samples/diem_trinh.wav';
            else if (voiceId === 'mai_linh') sampleUrl = '/samples/mai_linh.wav';
            else if (voiceId === 'ngoc_huyen') sampleUrl = '/samples/ngoc_huyen.wav';
            else if (voiceId === 'manh_dung') sampleUrl = '/samples/manh_dung.wav';
            else if (voiceId === 'thanh_dat') sampleUrl = '/samples/thanh_dat.wav';
            else if (voiceId === 'en_heart') sampleUrl = '/samples/en_heart.wav';
            else if (voiceId === 'rvc_ngochuyen_reviewphim') sampleUrl = '/samples/rvc_ngochuyen_reviewphim.wav';
            else if (voiceId.startsWith('rvc_') || voiceId.startsWith('local_')) sampleUrl = `/samples/${voiceId}.wav`;
        }

        // Hàm helper phát âm thanh an toàn bằng Promise
        const playAudioUrl = (url) => {
            return new Promise((resolve, reject) => {
                const audio = new Audio(url);
                currentPreviewAudio = audio;
                let started = false;

                audio.oncanplay = () => {
                    if (btnEl && activePreviewBtn === btnEl) {
                        setPreviewBtnState(btnEl, 'playing');
                    }
                };

                audio.onended = () => {
                    if (btnEl) setPreviewBtnState(btnEl, 'idle');
                    currentPreviewAudio = null;
                    activePreviewBtn = null;
                    resolve(true);
                };

                audio.onerror = (err) => {
                    reject(err);
                };

                audio.play().then(() => {
                    started = true;
                    if (btnEl && activePreviewBtn === btnEl) {
                        setPreviewBtnState(btnEl, 'playing');
                    }
                }).catch((playErr) => {
                    reject(playErr);
                });
            });
        };

        let playedSuccessfully = false;

        // Thử phát URL mẫu trước nếu có
        if (sampleUrl) {
            try {
                await playAudioUrl(sampleUrl);
                playedSuccessfully = true;
            } catch (err) {
                console.warn(`[playPreviewVoice] Mẫu file tĩnh (${sampleUrl}) không phát được, tự động chuyển sang /api/tts/preview:`, err);
                playedSuccessfully = false;
            }
        }

        // Nếu chưa phát được, gọi API TTS Preview sinh giọng tức thời
        if (!playedSuccessfully) {
            if (btnEl) setPreviewBtnState(btnEl, 'loading');
            const res = await fetch('/api/tts/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ voice: voiceId })
            });
            const data = await res.json();
            if (data.success && data.audio_url) {
                await playAudioUrl(data.audio_url);
            } else {
                throw new Error(data.error || 'Không thể tạo âm thanh mẫu');
            }
        }

    } catch (e) {
        if (btnEl) {
            setPreviewBtnState(btnEl, 'idle');
        }
        currentPreviewAudio = null;
        activePreviewBtn = null;
        showToast('Lỗi nghe thử giọng: ' + e.message, 'warning');
    }
};

// Load voice library on startup
window.addEventListener('DOMContentLoaded', fetchAndRenderVoiceLibrary);

// --- OCR DYNAMIC DEVICE LABEL LOGIC ---
const ocrDeviceSelect = document.getElementById('ocrDevice');
const ocrThreadsLabel = document.getElementById('ocrThreadsLabel');
const ocrThreadsTooltip = document.getElementById('ocrThreadsTooltip');

if (ocrDeviceSelect && ocrThreadsLabel && ocrThreadsTooltip) {
    ocrDeviceSelect.addEventListener('change', () => {
        ocrThreadsLabel.innerText = 'Luồng CPU hỗ trợ OCR';
        ocrThreadsTooltip.innerText = 'Số luồng CPU bên trong ONNX Runtime (1–8), kể cả khi dùng GPU. Không phải số ảnh chạy đồng thời. Có thể thử 2 hoặc 4 và so sánh tốc độ thực tế.';
    });
    ocrDeviceSelect.dispatchEvent(new Event('change'));
}

// ==========================================
// REVIEW PHIM LOGIC (STUDIO AUTO-EDIT)
// ==========================================
let currentReviewScriptMode = 'api';
let reviewAspectRatio = '16:9';
let reviewPacing = 'normal';
let reviewVideoMode = 'api'; // 'api' = recap (auto-edit), 'narration' = kể lại video

// --- Review Mode Toggle (Tóm tắt vs Kể lại) ---
const reviewModeRecap = document.getElementById('reviewModeRecap');
const reviewModeNarration = document.getElementById('reviewModeNarration');
const reviewRecapDurationConfig = document.getElementById('reviewRecapDurationConfig');
const reviewNarrationInfo = document.getElementById('reviewNarrationInfo');
const reviewModeDescription = document.getElementById('reviewModeDescription');

function setReviewMode(mode) {
    reviewVideoMode = mode;
    const isNarration = mode === 'narration';
    
    // Toggle buttons
    if (reviewModeRecap) {
        reviewModeRecap.classList.toggle('active', !isNarration);
        reviewModeRecap.style.borderColor = isNarration ? '' : '#38bdf8';
        reviewModeRecap.style.color = isNarration ? '' : '#38bdf8';
    }
    if (reviewModeNarration) {
        reviewModeNarration.classList.toggle('active', isNarration);
        reviewModeNarration.style.borderColor = isNarration ? '#34d399' : '';
        reviewModeNarration.style.color = isNarration ? '#34d399' : '';
    }
    
    // Show/hide configs
    if (reviewRecapDurationConfig) reviewRecapDurationConfig.style.display = isNarration ? 'none' : 'block';
    if (reviewNarrationInfo) reviewNarrationInfo.style.display = isNarration ? 'block' : 'none';
    
    // Update description text
    if (reviewModeDescription) {
        reviewModeDescription.textContent = isNarration
            ? 'AI sẽ viết kịch bản kể lại phim khớp đúng thời lượng video gốc, sau đó overlay voice-over + phụ đề lên video mà không cắt ghép.'
            : 'Hệ thống sẽ gửi phụ đề đến mô hình AI đã cấu hình trong Cài đặt (OpenAI / ChatGPT) để phân tích cốt truyện, viết kịch bản tóm tắt lôi cuốn và tự sinh timeline khớp cảnh chuẩn xác.';
    }
    
    // Hide/show Scene Detect, Pacing, Crossfade sections (not needed for narration)
    const sceneDetectSection = document.querySelector('.form-group.mb-12:has(#reviewEnableSceneDetect)');
    const pacingSection = document.querySelector('.review-pacing-btn-group');
    if (sceneDetectSection) sceneDetectSection.closest('.form-group').style.display = isNarration ? 'none' : '';
    if (pacingSection) pacingSection.closest('.form-group').style.display = isNarration ? 'none' : '';
}

if (reviewModeRecap) reviewModeRecap.addEventListener('click', () => setReviewMode('api'));
if (reviewModeNarration) reviewModeNarration.addEventListener('click', () => setReviewMode('narration'));

// Original Volume slider for narration mode
const reviewOrigVol = document.getElementById('reviewOrigVol');
const reviewOrigVolVal = document.getElementById('reviewOrigVolVal');
if (reviewOrigVol && reviewOrigVolVal) {
    reviewOrigVol.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        reviewOrigVolVal.textContent = val + '%';
        const rPlayer = document.getElementById('reviewVideoPlayer');
        if (rPlayer) {
            rPlayer.volume = Math.max(0, Math.min(1.0, val / 100));
        }
    });
}

// Target Minutes & Estimated Words (3.5 từ/giây = 210 từ/phút)
const reviewTargetMinutes = document.getElementById('reviewTargetMinutes');
const reviewEstimatedWords = document.getElementById('reviewEstimatedWords');
if (reviewTargetMinutes && reviewEstimatedWords) {
    reviewTargetMinutes.addEventListener('input', (e) => {
        const mins = parseInt(e.target.value) || 5;
        const words = Math.round(mins * 60 * 3.5);
        reviewEstimatedWords.textContent = `~${words.toLocaleString('vi-VN')} từ kịch bản`;
    });
}

// Review Style Selector (Tone & Vibe)
const reviewStyleSelect = document.getElementById('reviewStyleSelect');
const reviewSelectedStyleBadge = document.getElementById('reviewSelectedStyleBadge');
const reviewCustomStyleContainer = document.getElementById('reviewCustomStyleContainer');

const styleBadgeMap = {
    'dramatic': '🎭 Kịch Tính',
    'humorous': '😂 Hài Hước',
    'deep_analysis': '🧠 Triết Lý',
    'fast_paced': '⚡ Mì Ăn Liền',
    'horror': '👻 Kinh Dị',
    'emotional': '💖 Tình Cảm',
    'custom': '✍️ Tùy Chỉnh'
};

if (reviewStyleSelect) {
    reviewStyleSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (reviewSelectedStyleBadge) {
            reviewSelectedStyleBadge.textContent = styleBadgeMap[val] || '🎭 Kịch Tính';
        }
        if (reviewCustomStyleContainer) {
            reviewCustomStyleContainer.style.display = (val === 'custom') ? 'block' : 'none';
        }
    });
}

// Aspect Ratio Toggles & Preview Frame Transformation
function updateReviewPlayerAspectRatio(ratio) {
    reviewAspectRatio = ratio;
    window.reviewAspectRatio = ratio;

    const rVert = document.getElementById('reviewRatioVertical');
    const rHoriz = document.getElementById('reviewRatioHorizontal');
    if (rVert && rHoriz) {
        if (ratio === '9:16') {
            rVert.classList.add('active');
            rVert.style.borderColor = '#38bdf8';
            rVert.style.color = '#38bdf8';
            rHoriz.classList.remove('active');
            rHoriz.style.borderColor = '';
            rHoriz.style.color = '';
        } else if (ratio === '16:9') {
            rHoriz.classList.add('active');
            rHoriz.style.borderColor = '#38bdf8';
            rHoriz.style.color = '#38bdf8';
            rVert.classList.remove('active');
            rVert.style.borderColor = '';
            rVert.style.color = '';
        } else {
            rVert.classList.remove('active');
            rVert.style.borderColor = '';
            rVert.style.color = '';
            rHoriz.classList.remove('active');
            rHoriz.style.borderColor = '';
            rHoriz.style.color = '';
        }
    }

    if (videoStudioInstances && videoStudioInstances.review) {
        if (videoStudioInstances.review.state.aspectRatio !== ratio) {
            videoStudioInstances.review.setAspectRatio(ratio, false);
        } else {
            videoStudioInstances.review.applyAspectRatio();
        }
    }
}

const reviewRatioVertical = document.getElementById('reviewRatioVertical');
const reviewRatioHorizontal = document.getElementById('reviewRatioHorizontal');
if (reviewRatioVertical && reviewRatioHorizontal) {
    reviewRatioVertical.addEventListener('click', () => {
        updateReviewPlayerAspectRatio('9:16');
    });
    reviewRatioHorizontal.addEventListener('click', () => {
        updateReviewPlayerAspectRatio('16:9');
    });
}

// Pacing Toggles
const reviewPacingFast = document.getElementById('reviewPacingFast');
const reviewPacingNormal = document.getElementById('reviewPacingNormal');
if (reviewPacingFast && reviewPacingNormal) {
    reviewPacingFast.addEventListener('click', () => {
        reviewPacingFast.classList.add('active');
        reviewPacingNormal.classList.remove('active');
        reviewPacing = 'fast';
    });
    reviewPacingNormal.addEventListener('click', () => {
        reviewPacingNormal.classList.add('active');
        reviewPacingFast.classList.remove('active');
        reviewPacing = 'normal';
    });
}

// Voice Speed Slider
const reviewVoiceSpeed = document.getElementById('reviewVoiceSpeed');
const reviewVoiceSpeedVal = document.getElementById('reviewVoiceSpeedVal');
if (reviewVoiceSpeed && reviewVoiceSpeedVal) {
    reviewVoiceSpeed.addEventListener('input', (e) => {
        reviewVoiceSpeedVal.textContent = parseFloat(e.target.value).toFixed(2) + 'x';
    });
}

// TTS Threads Slider
const reviewTtsThreads = document.getElementById('reviewTtsThreads');
const reviewTtsThreadsVal = document.getElementById('reviewTtsThreadsVal');
if (reviewTtsThreads && reviewTtsThreadsVal) {
    reviewTtsThreads.addEventListener('input', (e) => {
        reviewTtsThreadsVal.textContent = e.target.value + ' luồng';
    });
}

// Video Zoom Controls
const reviewEnableZoom = document.getElementById('reviewEnableZoom');
const reviewZoomConfigPanel = document.getElementById('reviewZoomConfigPanel');
const reviewVideoZoom = document.getElementById('reviewVideoZoom');
const reviewVideoZoomVal = document.getElementById('reviewVideoZoomVal');

if (reviewEnableZoom && reviewZoomConfigPanel) {
    reviewEnableZoom.addEventListener('change', (e) => {
        reviewZoomConfigPanel.style.display = e.target.checked ? 'flex' : 'none';
    });
}

if (reviewVideoZoom && reviewVideoZoomVal) {
    reviewVideoZoom.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        reviewVideoZoomVal.textContent = val === 105 ? '105% (Khuyên dùng)' : (val === 100 ? '100% (Gốc)' : `${val}%`);
        
        document.querySelectorAll('.btn-review-zoom-preset').forEach(btn => {
            if (parseInt(btn.dataset.zoom) === val) {
                btn.classList.add('active');
                btn.style.borderColor = '#38bdf8';
                btn.style.color = '#38bdf8';
            } else {
                btn.classList.remove('active');
                btn.style.borderColor = '';
                btn.style.color = '';
            }
        });
    });
}

document.querySelectorAll('.btn-review-zoom-preset').forEach(btn => {
    btn.addEventListener('click', () => {
        const zoomVal = parseInt(btn.dataset.zoom) || 105;
        if (reviewVideoZoom) {
            reviewVideoZoom.value = zoomVal;
            reviewVideoZoom.dispatchEvent(new Event('input'));
        }
    });
});

// BGM Controls
const reviewBgmEnabled = document.getElementById('reviewBgmEnabled');
const reviewBgmConfig = document.getElementById('reviewBgmConfig');
const reviewBgmVol = document.getElementById('reviewBgmVol');
const reviewBgmVolVal = document.getElementById('reviewBgmVolVal');
const btnBgmSourcePreset = document.getElementById('btnBgmSourcePreset');
const btnBgmSourceCustom = document.getElementById('btnBgmSourceCustom');
const panelBgmPreset = document.getElementById('panelBgmPreset');
const panelBgmCustom = document.getElementById('panelBgmCustom');
const reviewBgmPresetSelect = document.getElementById('reviewBgmPresetSelect');
const btnPreviewBgm = document.getElementById('btnPreviewBgm');
const btnUploadBgm = document.getElementById('btnUploadBgm');
const reviewBgmFileInput = document.getElementById('reviewBgmFileInput');
const reviewBgmCustomFileName = document.getElementById('reviewBgmCustomFileName');
const btnPreviewCustomBgm = document.getElementById('btnPreviewCustomBgm');
const btnRemoveCustomBgm = document.getElementById('btnRemoveCustomBgm');
const reviewBgmPreviewAudio = document.getElementById('reviewBgmPreviewAudio');

window.currentBgmSourceMode = 'preset';
window.currentCustomBgmPath = '';
window.currentCustomBgmFilename = '';

if (reviewBgmEnabled && reviewBgmConfig) {
    reviewBgmEnabled.addEventListener('change', (e) => {
        reviewBgmConfig.style.opacity = e.target.checked ? '1' : '0.4';
        reviewBgmConfig.style.pointerEvents = e.target.checked ? 'auto' : 'none';
        if (!e.target.checked && reviewBgmPreviewAudio) {
            reviewBgmPreviewAudio.pause();
            if (btnPreviewBgm) btnPreviewBgm.textContent = '▶️';
            if (btnPreviewCustomBgm) btnPreviewCustomBgm.textContent = '▶️';
        }
    });
}
if (reviewBgmVol && reviewBgmVolVal) {
    reviewBgmVol.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        reviewBgmVolVal.textContent = val + '%';
        if (reviewBgmPreviewAudio) {
            reviewBgmPreviewAudio.volume = Math.max(0, Math.min(1.0, val / 100));
        }
    });
}

// BGM Source Tabs Switcher
if (btnBgmSourcePreset && btnBgmSourceCustom && panelBgmPreset && panelBgmCustom) {
    btnBgmSourcePreset.addEventListener('click', () => {
        window.currentBgmSourceMode = 'preset';
        btnBgmSourcePreset.classList.add('active');
        btnBgmSourcePreset.style.borderColor = '#38bdf8';
        btnBgmSourcePreset.style.color = '#38bdf8';
        btnBgmSourcePreset.style.background = 'rgba(56, 189, 248, 0.1)';
        
        btnBgmSourceCustom.classList.remove('active');
        btnBgmSourceCustom.style.borderColor = '';
        btnBgmSourceCustom.style.color = '#94a3b8';
        btnBgmSourceCustom.style.background = '';
        
        panelBgmPreset.style.display = 'flex';
        panelBgmCustom.style.display = 'none';
        
        if (reviewBgmPreviewAudio) {
            reviewBgmPreviewAudio.pause();
            if (btnPreviewCustomBgm) btnPreviewCustomBgm.textContent = '▶️';
        }
    });

    btnBgmSourceCustom.addEventListener('click', () => {
        window.currentBgmSourceMode = 'custom';
        btnBgmSourceCustom.classList.add('active');
        btnBgmSourceCustom.style.borderColor = '#38bdf8';
        btnBgmSourceCustom.style.color = '#38bdf8';
        btnBgmSourceCustom.style.background = 'rgba(56, 189, 248, 0.1)';
        
        btnBgmSourcePreset.classList.remove('active');
        btnBgmSourcePreset.style.borderColor = '';
        btnBgmSourcePreset.style.color = '#94a3b8';
        btnBgmSourcePreset.style.background = '';
        
        panelBgmPreset.style.display = 'none';
        panelBgmCustom.style.display = 'flex';
        
        if (reviewBgmPreviewAudio) {
            reviewBgmPreviewAudio.pause();
            if (btnPreviewBgm) btnPreviewBgm.textContent = '▶️';
        }
    });
}

// Load Preset BGM List from Server
async function loadBgmPresetList() {
    if (!reviewBgmPresetSelect) return;
    try {
        const res = await fetch('/api/bgm/list');
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.files) && data.files.length > 0) {
            const currentVal = reviewBgmPresetSelect.value || 'random';
            reviewBgmPresetSelect.innerHTML = '<option value="random">🎲 Ngẫu nhiên (Random theo tâm trạng)</option>';
            data.files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.filename;
                opt.textContent = `${f.title} (${f.genre})`;
                reviewBgmPresetSelect.appendChild(opt);
            });
            if (data.files.some(f => f.filename === currentVal)) {
                reviewBgmPresetSelect.value = currentVal;
            }
        }
    } catch (err) {
        console.error('Failed to load BGM list:', err);
    }
}
loadBgmPresetList();

// Preset BGM Preview Player
if (btnPreviewBgm && reviewBgmPreviewAudio && reviewBgmPresetSelect) {
    btnPreviewBgm.addEventListener('click', () => {
        if (!reviewBgmPreviewAudio.paused && reviewBgmPreviewAudio.dataset.currentType === 'preset') {
            reviewBgmPreviewAudio.pause();
            btnPreviewBgm.textContent = '▶️';
            return;
        }

        let selected = reviewBgmPresetSelect.value;
        if (selected === 'random') {
            const options = Array.from(reviewBgmPresetSelect.options).map(o => o.value).filter(v => v !== 'random');
            if (options.length > 0) {
                selected = options[Math.floor(Math.random() * options.length)];
            } else {
                showToast('Chưa có file nhạc nền khả dụng để nghe thử', 'warning');
                return;
            }
        }

        reviewBgmPreviewAudio.src = `/api/bgm/stream?type=preset&filename=${encodeURIComponent(selected)}&file=${encodeURIComponent(selected)}`;
        reviewBgmPreviewAudio.dataset.currentType = 'preset';
        reviewBgmPreviewAudio.play().then(() => {
            btnPreviewBgm.textContent = '⏸️';
            if (btnPreviewCustomBgm) btnPreviewCustomBgm.textContent = '▶️';
        }).catch(err => {
            console.error('Audio play failed:', err);
            showToast('Không thể phát nhạc nghe thử', 'error');
        });
    });

    reviewBgmPreviewAudio.addEventListener('ended', () => {
        if (btnPreviewBgm) btnPreviewBgm.textContent = '▶️';
        if (btnPreviewCustomBgm) btnPreviewCustomBgm.textContent = '▶️';
    });
    reviewBgmPreviewAudio.addEventListener('pause', () => {
        if (reviewBgmPreviewAudio.dataset.currentType === 'preset' && btnPreviewBgm) {
            btnPreviewBgm.textContent = '▶️';
        } else if (reviewBgmPreviewAudio.dataset.currentType === 'custom' && btnPreviewCustomBgm) {
            btnPreviewCustomBgm.textContent = '▶️';
        }
    });
}

// Custom BGM Upload & Actions
if (btnUploadBgm && reviewBgmFileInput) {
    btnUploadBgm.addEventListener('click', () => {
        reviewBgmFileInput.click();
    });

    reviewBgmFileInput.addEventListener('change', async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        showToast('Đang tải lên nhạc nền...', 'info');
        try {
            const res = await fetch('/api/bgm/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok && data.status === 'success') {
                window.currentCustomBgmPath = data.path;
                window.currentCustomBgmFilename = data.filename;
                if (reviewBgmCustomFileName) {
                    reviewBgmCustomFileName.textContent = `🎵 ${data.filename}`;
                    reviewBgmCustomFileName.style.color = '#38bdf8';
                }
                if (btnPreviewCustomBgm) btnPreviewCustomBgm.style.display = 'flex';
                if (btnRemoveCustomBgm) btnRemoveCustomBgm.style.display = 'flex';
                showToast('Tải lên nhạc nền thành công!', 'success');
            } else {
                showToast(data.message || 'Lỗi khi tải file nhạc lên', 'error');
            }
        } catch (err) {
            console.error('BGM upload failed:', err);
            showToast('Không thể kết nối máy chủ để tải nhạc', 'error');
        } finally {
            reviewBgmFileInput.value = '';
        }
    });
}

if (btnPreviewCustomBgm && reviewBgmPreviewAudio) {
    btnPreviewCustomBgm.addEventListener('click', () => {
        if (!window.currentCustomBgmFilename) return;

        if (!reviewBgmPreviewAudio.paused && reviewBgmPreviewAudio.dataset.currentType === 'custom') {
            reviewBgmPreviewAudio.pause();
            btnPreviewCustomBgm.textContent = '▶️';
            return;
        }

        reviewBgmPreviewAudio.src = `/api/bgm/stream?type=custom&filename=${encodeURIComponent(window.currentCustomBgmFilename)}&file=${encodeURIComponent(window.currentCustomBgmFilename)}`;
        reviewBgmPreviewAudio.dataset.currentType = 'custom';
        reviewBgmPreviewAudio.play().then(() => {
            btnPreviewCustomBgm.textContent = '⏸️';
            if (btnPreviewBgm) btnPreviewBgm.textContent = '▶️';
        }).catch(err => {
            console.error('Custom audio play failed:', err);
            showToast('Không thể phát file nhạc tải lên', 'error');
        });
    });
}

if (btnRemoveCustomBgm) {
    btnRemoveCustomBgm.addEventListener('click', () => {
        window.currentCustomBgmPath = '';
        window.currentCustomBgmFilename = '';
        if (reviewBgmPreviewAudio && reviewBgmPreviewAudio.dataset.currentType === 'custom') {
            reviewBgmPreviewAudio.pause();
        }
        if (reviewBgmCustomFileName) {
            reviewBgmCustomFileName.textContent = 'Chưa chọn file (.mp3, .wav, .m4a)';
            reviewBgmCustomFileName.style.color = '#94a3b8';
        }
        if (btnPreviewCustomBgm) {
            btnPreviewCustomBgm.style.display = 'none';
            btnPreviewCustomBgm.textContent = '▶️';
        }
        btnRemoveCustomBgm.style.display = 'none';
        showToast('Đã hủy chọn nhạc nền riêng', 'info');
    });
}

// AI Stem Separation Toggle
const reviewStemSeparationEnabled = document.getElementById('reviewStemSeparationEnabled');
const reviewStemConfig = document.getElementById('reviewStemConfig');
if (reviewStemSeparationEnabled && reviewStemConfig) {
    reviewStemSeparationEnabled.addEventListener('change', (e) => {
        reviewStemConfig.style.opacity = e.target.checked ? '1' : '0.4';
        reviewStemConfig.style.pointerEvents = e.target.checked ? 'auto' : 'none';
    });
}

// Anti-Flicker Slider Controls
const reviewSnapThreshold = document.getElementById('reviewSnapThreshold');
const reviewSnapThresholdVal = document.getElementById('reviewSnapThresholdVal');
if (reviewSnapThreshold && reviewSnapThresholdVal) {
    reviewSnapThreshold.addEventListener('input', (e) => {
        reviewSnapThresholdVal.textContent = parseFloat(e.target.value).toFixed(1) + 's';
    });
}

const reviewMinClipDur = document.getElementById('reviewMinClipDur');
const reviewMinClipDurVal = document.getElementById('reviewMinClipDurVal');
if (reviewMinClipDur && reviewMinClipDurVal) {
    reviewMinClipDur.addEventListener('input', (e) => {
        reviewMinClipDurVal.textContent = parseFloat(e.target.value).toFixed(1) + 's';
    });
}

// Video selection & Insight Badge
// reviewInputVideoPath already declared at top
const btnSelectReviewInput = document.getElementById('btnSelectReviewInput');
const reviewVideoInsightBox = document.getElementById('reviewVideoInsightBox');
const reviewInsightDuration = document.getElementById('reviewInsightDuration');

const handleSelectReviewVideo = async () => {
    const path = await selectFile('video');
    if (path) {
        if (reviewInputVideoPath) reviewInputVideoPath.value = path;
        loadReviewVideoPlayer(path);
        if (reviewVideoInsightBox) {
            reviewVideoInsightBox.style.display = 'flex';
            const filename = path.split('\\').pop().split('/').pop();
            if (reviewInsightDuration) reviewInsightDuration.textContent = `🎬 ${filename}`;
        }
    }
};

if (btnSelectReviewInput) {
    btnSelectReviewInput.addEventListener('click', handleSelectReviewVideo);
}

const btnSelectReviewVideoHeader = document.getElementById('btnSelectReviewVideoHeader');
if (btnSelectReviewVideoHeader) {
    btnSelectReviewVideoHeader.addEventListener('click', handleSelectReviewVideo);
}

const btnSelectReviewVideoPlaceholder = document.getElementById('btnSelectReviewVideoPlaceholder');
if (btnSelectReviewVideoPlaceholder) {
    btnSelectReviewVideoPlaceholder.addEventListener('click', handleSelectReviewVideo);
}

// reviewInputSrtPath declaration
const btnSelectReviewSrt = document.getElementById('btnSelectReviewSrt');

if (btnSelectReviewSrt) {
    btnSelectReviewSrt.addEventListener('click', async () => {
        const path = await selectFile('srt');
        if (path) {
            reviewInputSrtPath.value = path;
            autoParseReviewSrt(path);
        }
    });
}

let reviewAbortController = null;

function checkLocalVoiceWarning(voiceId) {
    const isLocal = ['ngoc_huyen', 'diem_trinh', 'mai_linh'].includes(voiceId) ||
                    voiceId.startsWith('rvc_') ||
                    voiceId.startsWith('edge_');
    if (!isLocal) return Promise.resolve('proceed');

    const modal = document.getElementById('modalLocalVoiceWarning');
    const btnContinue = document.getElementById('btnContinueLocalVoice');
    const btnSwitch = document.getElementById('btnSwitchToApiVoice');

    if (!modal || !btnContinue || !btnSwitch) return Promise.resolve('proceed');

    modal.style.display = 'flex';

    return new Promise((resolve) => {
        const handleContinue = () => {
            modal.style.display = 'none';
            cleanup();
            resolve('proceed');
        };
        const handleSwitch = () => {
            modal.style.display = 'none';
            cleanup();
            resolve('switch');
        };
        const cleanup = () => {
            btnContinue.removeEventListener('click', handleContinue);
            btnSwitch.removeEventListener('click', handleSwitch);
        };
        btnContinue.addEventListener('click', handleContinue);
        btnSwitch.addEventListener('click', handleSwitch);
    });
}

const btnStartReview = document.getElementById('btnStartReview');
if (btnStartReview) {
    const btnStopReview = document.getElementById('btnStopReview');
    if (btnStopReview) {
        btnStopReview.addEventListener('click', async () => {
            if (reviewAbortController) {
                reviewAbortController.abort();
            }
            try {
                await fetch('/api/review/stop', { method: 'POST' });
                showToast('Đang gửi lệnh dừng đến máy chủ...', 'info');
            } catch (e) {
                console.error("Failed to call stop API", e);
            }
        });
    }

    btnStartReview.addEventListener('click', async () => {
        if (!checkFeaturePermission('can_access_review', 'Tạo video Review Phim')) return;

        if (!reviewInputVideoPath.value) {
            showToast('Vui lòng chọn video đầu vào!', 'warning');
            return;
        }
        
        const voiceId = document.getElementById('reviewVoiceSelect').value;
        
        // Cảnh báo nếu sử dụng giọng Local (Kokoro / RVC / Edge)
        const warningChoice = await checkLocalVoiceWarning(voiceId);
        if (warningChoice === 'switch') {
            const btnOpenVoice = document.getElementById('btnOpenVoiceModalReview');
            if (btnOpenVoice) {
                btnOpenVoice.click();
                showToast('Vui lòng chọn một giọng đọc Cloud / OpenSpeaker để tự động lấy phụ đề nhanh chóng!', 'info');
            }
            return;
        }
        
        const voiceSpeed = parseFloat(document.getElementById('reviewVoiceSpeed')?.value) || 1.1;
        
        let payload = {
            video_path: reviewInputVideoPath.value,
            mode: reviewVideoMode,
            voice_id: voiceId,
            voice_speed: voiceSpeed,
            tts_threads: parseInt(document.getElementById('reviewTtsThreads')?.value || 8),
            target_minutes: document.getElementById('reviewTargetMinutes') ? (parseInt(document.getElementById('reviewTargetMinutes').value) || 5) : 5,
            review_style: document.getElementById('reviewStyleSelect')?.value || 'dramatic',
            custom_style_prompt: document.getElementById('reviewCustomStylePrompt')?.value || '',
            aspect_ratio: reviewAspectRatio,
            pacing: reviewPacing,
            enable_zoom: (window.videoStudioInstances?.review?.state?.zoom > 1.0) || (document.getElementById('reviewEnableZoom')?.checked ?? true),
            video_zoom: window.videoStudioInstances?.review ? Math.round((window.videoStudioInstances.review.state.zoom || 1.05) * 100) : (parseFloat(document.getElementById('reviewVideoZoom')?.value) || 105),
            blur_original_subtitles: Boolean(document.getElementById('reviewTabBlurOriginalSubtitles')?.checked),
            blur_intensity: parseInt(document.getElementById('reviewTabDynBlurIntensity')?.value) || 15,
            blur_lead_offset: Number.isFinite(parseFloat(document.getElementById('reviewTabBlurLeadOffset')?.value)) ? parseFloat(document.getElementById('reviewTabBlurLeadOffset')?.value) : -180,
            blur_padding: Number.isFinite(parseFloat(document.getElementById('reviewTabBlurPadding')?.value)) ? parseFloat(document.getElementById('reviewTabBlurPadding')?.value) : 220,
            blur_y_pos: parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || 81.5,
            blur_use_ai_scan: document.getElementById('reviewTabBlurUseAiScan')?.checked ?? true,
            ai_boxes: (window.reviewTabScannedAiBoxes && window.reviewTabScannedAiBoxes.length > 0) ? window.reviewTabScannedAiBoxes : null,
            logo: {
                enabled: document.getElementById('reviewEnableLogoWatermark')?.checked ?? false,
                path: document.getElementById('reviewLogoInputPath')?.value || '',
                x_pct: (window.currentReviewLogoState && window.currentReviewLogoState.x_pct) || 5.0,
                y_pct: (window.currentReviewLogoState && window.currentReviewLogoState.y_pct) || 5.0,
                w_pct: (window.currentReviewLogoState && window.currentReviewLogoState.w_pct) || 18.0,
                h_pct: (window.currentReviewLogoState && window.currentReviewLogoState.h_pct) || 12.0,
                opacity: parseInt(document.getElementById('reviewLogoOpacity')?.value || 100)
            },
            auto_subtitles: false,
            enable_scene_detect: document.getElementById('reviewEnableSceneDetect') ? document.getElementById('reviewEnableSceneDetect').checked : true,
            snap_threshold: parseFloat(document.getElementById('reviewSnapThreshold')?.value) || 0.6,
            min_clip_duration: parseFloat(document.getElementById('reviewMinClipDur')?.value) || 1.2,
            max_speed_ratio_deviation: 0.15,
            enable_crossfade: document.getElementById('reviewEnableCrossfade')?.checked || false,
            original_volume: parseInt(document.getElementById('reviewOrigVol')?.value) || 15,
            bgm: {
                enabled: Boolean(document.getElementById('reviewBgmEnabled')?.checked),
                volume: parseInt(document.getElementById('reviewBgmVol')?.value) || 15,
                ducking: Boolean(document.getElementById('reviewBgmDucking')?.checked),
                preset: document.getElementById('reviewBgmPresetSelect')?.value || 'random',
                path: (window.currentBgmSourceMode === 'custom' && window.currentCustomBgmPath) ? window.currentCustomBgmPath : ''
            },
            stem_separation: {
                enabled: Boolean(document.getElementById('reviewStemSeparationEnabled')?.checked),
                remove_vocals: document.getElementById('reviewRemoveVocals')?.checked !== false,
                keep_sfx: document.getElementById('reviewKeepSfx')?.checked !== false,
                mode: document.getElementById('reviewStemMode')?.value || 'mdx_net_hq4',
                device: document.getElementById('reviewStemDevice')?.value || 'auto'
            },
            output_dir: document.getElementById('reviewOutputFolder').value.trim() || window.currentTtsOutputDir || 'output',
            output_name: document.getElementById('reviewOutputFileName').value.trim() || 'video_review.mp4'
        };
        
        // reviewInputSrtPath declaration
        if (reviewInputSrtPath && reviewInputSrtPath.value) {
            payload.srt_path = reviewInputSrtPath.value;
        }
        
        // Kiểm tra API Key cho Review Phim AI
        const hasAiKey = await ensureAiKeyAvailable('openai', 'Tạo kịch bản Review Phim AI');
        if (!hasAiKey) return;

        const openaiKey = document.getElementById('openaiKey')?.value || '';
        if (openaiKey && !openaiKey.startsWith('•')) payload.openai_key = openaiKey;
        payload.openai_base_url = document.getElementById('openaiBaseUrl')?.value || 'https://api.openai.com/v1';
        payload.openai_model = document.getElementById('openaiModel')?.value || 'gpt-5.6-luna-pro-batch';
        
        // CHECK CACHE
        try {
            const cacheRes = await fetch('/api/review/check_cache', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    output_dir: payload.output_dir,
                    video_path: payload.video_path,
                    srt_path: payload.srt_path
                })
            });
            if (cacheRes.ok) {
                const cacheData = await cacheRes.json();
                if (cacheData.has_cache) {
                    const confirm = await showConfirmModal(
                        'Tái sử dụng dữ liệu?',
                        `Hệ thống tìm thấy dữ liệu đang làm dở từ lần chạy trước (${cacheData.files.join(', ')}). Bạn có muốn TÁI SỬ DỤNG chúng để tiết kiệm thời gian (và tiền API) không? Chọn 'Đồng ý' để tiếp tục dùng, hoặc 'Hủy' để làm lại từ đầu.`
                    );
                    payload.use_cache = confirm;
                }
            }
        } catch(e) {
            console.error("Lỗi khi check cache:", e);
        }
        
        // Show terminal and start streaming
        const terminal = document.getElementById('terminal');
        terminal.innerHTML = '';
        const terminalOverlay = document.getElementById('terminalOverlay');
        terminalOverlay.classList.remove('collapsed');
        
        btnStartReview.disabled = true;
        btnStartReview.innerText = 'ĐANG XỬ LÝ...';
        if (btnStopReview) btnStopReview.style.display = 'block';
        const progressText = document.getElementById('reviewProgressText');
        if (progressText) progressText.innerText = 'Đang chuẩn bị...';
        
        updateReviewStepper(1); // Reset and show stepper
        
        const startTime = Date.now();
        
        reviewAbortController = new AbortController();
        
        try {
            const response = await fetch('/api/review/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
                signal: reviewAbortController.signal
            });
            
            if (!response.ok) {
                const errText = await response.text();
                appendLog(`🛑 Lỗi máy chủ (${response.status}): ` + errText.substring(0, 500), 'error');
                throw new Error(`HTTP Error ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let hasError = false;
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, {stream: true});
                const lines = chunk.split('\n\n');
                for (let line of lines) {
                    if (line.startsWith('data: ')) {
                        const msg = line.substring(6);
                        if (msg.startsWith('[PROGRESS] ')) {
                            const progress = parseInt(msg.substring(11).trim());
                            if (progressText && !isNaN(progress) && progress > 0) {
                                const elapsed = Date.now() - startTime;
                                const totalEst = elapsed / (progress / 100);
                                const remainingSec = Math.max(0, Math.round((totalEst - elapsed) / 1000));
                                const mins = Math.floor(remainingSec / 60);
                                const secs = remainingSec % 60;
                                progressText.innerText = `Đã hoàn thành: ${progress}% - Ước tính còn: ${mins}p ${secs}s`;
                                if (progress >= 100) progressText.innerText = 'Hoàn thành 100%';
                            }
                            continue; // Do not print [PROGRESS] to terminal
                        }
                        if (msg.startsWith('[STEP] ')) {
                            const stepStr = msg.substring(7).trim();
                            updateReviewStepper(parseInt(stepStr) || 1);
                            continue; // Do not print [STEP] to terminal
                        }
                        let logType = 'info';
                        if (msg.includes('🛑') || msg.includes('Lỗi')) {
                            hasError = true;
                            logType = 'error';
                        } else if (msg.includes('⚠️')) {
                            logType = 'warning';
                        } else if (msg.includes('✅') || msg.includes('🎉')) {
                            logType = 'success';
                        }
                        appendLog(msg, logType);
                    }
                }
            }
            showToast('Quá trình Review Phim đã hoàn thành!', 'success');
        } catch (e) {
            if (e.name === 'AbortError') {
                showToast('Đã hủy tiến trình.', 'warning');
            } else {
                showToast('Lỗi quá trình: ' + e.message, 'error');
            }
        } finally {
            btnStartReview.disabled = false;
            btnStartReview.innerText = 'BẮT ĐẦU LÀM VIDEO (AUTO-EDIT)';
            if (btnStopReview) btnStopReview.style.display = 'none';
            reviewAbortController = null;
        }
    });
}

function updateReviewStepper(currentStep) {
    const stepper = document.getElementById('reviewStepper');
    if (!stepper) return;
    stepper.style.display = 'flex';
    
    for (let i = 1; i <= 5; i++) {
        const stepEl = stepper.querySelector(`.step[data-step="${i}"]`);
        const lineEl = stepEl ? stepEl.nextElementSibling : null;
        
        if (stepEl) {
            stepEl.classList.remove('active', 'completed');
            if (i < currentStep) stepEl.classList.add('completed');
            else if (i === currentStep) stepEl.classList.add('active');
        }
        
        if (lineEl && lineEl.classList.contains('step-line')) {
            lineEl.classList.remove('completed');
            if (i < currentStep) lineEl.classList.add('completed');
        }
    }
}


// Video Player Loading Spinner Logic
const videoLoadingSpinner = document.getElementById('videoLoadingSpinner');
if(videoPlayer && videoLoadingSpinner) {
    videoPlayer.addEventListener('loadstart', () => {
        videoLoadingSpinner.style.display = 'block';
    });
    
    videoPlayer.addEventListener('waiting', () => {
        videoLoadingSpinner.style.display = 'block';
    });

    videoPlayer.addEventListener('canplay', () => {
        videoLoadingSpinner.style.display = 'none';
    });
    
    videoPlayer.addEventListener('playing', () => {
        videoLoadingSpinner.style.display = 'none';
    });

    videoPlayer.addEventListener('error', () => {
        videoLoadingSpinner.style.display = 'none';
    });
}

// ====== API KEYS TXT BINDING ======
function bindApiKeys() {
    const keys = ['openaiKey', 'openaiBaseUrl', 'openaiModel', 'openSpeakerApiKey'];
    keys.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', async () => {
                const val = el.value.trim();
                if (val.startsWith('•')) return; // Do not save masked keys
                const payload = {};
                payload[id] = val;
                try {
                    await fetch('/api/keys', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                } catch(e) {
                    console.error('Failed to save key', e);
                }
            });
        }
    });
    // Load keys when called
    loadApiKeys();
    loadTelegramSettings();
}
document.addEventListener('DOMContentLoaded', bindApiKeys);

// ====== API KEYS MANAGEMENT & TEST ======
const btnTestOpenSpeakerKey = document.getElementById('btnTestOpenSpeakerKey');
if (btnTestOpenSpeakerKey) {
    btnTestOpenSpeakerKey.addEventListener('click', async () => {
        const apiKey = document.getElementById('openSpeakerApiKey').value.trim();
        if (!apiKey) {
            showToast('Vui lòng nhập OpenSpeaker API Key', 'warning');
            return;
        }
        btnTestOpenSpeakerKey.disabled = true;
        btnTestOpenSpeakerKey.innerText = 'Đang đồng bộ...';
        try {
            // 1. Gọi API Refresh để tải toàn bộ danh sách giọng mới nhất từ OpenSpeaker
            const refreshRes = await fetch('/api/voices/refresh', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ api_key: apiKey })
            });
            const refreshData = await refreshRes.json();
            
            if (refreshData.success) {
                showToast(`Kết nối thành công! Đã đồng bộ ${refreshData.count} giọng đọc từ OpenSpeaker.`, 'success');
                // Tải lại danh sách vào UI nếu modal chọn giọng đang mở
                if (typeof loadAllVoices === 'function') {
                    loadAllVoices();
                }
            } else {
                showToast('Lỗi kết nối OpenSpeaker: ' + (refreshData.error || 'Không rõ lỗi'), 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('Lỗi gọi API: ' + e.message, 'error');
        } finally {
            btnTestOpenSpeakerKey.disabled = false;
            btnTestOpenSpeakerKey.innerText = 'Test API';
        }
    });
}


// --- ASR Model Integration ---
// --- ASR Model Integration ---
const btnScanAsr = document.getElementById("btnScanAsr");
const asrModelSelect = document.getElementById("asrModelSelect");
let isScanningAsr = false;
let asrAbortController = null;

if (btnScanAsr && asrModelSelect) {
    btnScanAsr.addEventListener("click", async () => {
        // 🛑 XỬ LÝ DỪNG KHẨN CẤP KHI NGƯỜI DÙNG BẤM LẦN 2
        if (isScanningAsr) {
            isScanningAsr = false;
            try {
                await fetch("/api/asr/stop", { method: "POST" });
                if (asrAbortController) {
                    asrAbortController.abort();
                }
            } catch (e) {
                console.error("Lỗi khi dừng ASR:", e);
            }
            appendLog("🛑 Đã dừng tiến trình quét phụ đề theo yêu cầu của bạn.", "warning");
            showToast("Đã dừng quét phụ đề!", "info");
            return;
        }

        if (!checkFeaturePermission('can_access_editor', 'Nhận dạng giọng nói ASR')) return;

        const modelName = asrModelSelect.value;
        const modelLabel = asrModelSelect.options[asrModelSelect.selectedIndex].text;
        
        const videoPath = document.getElementById("editorInputVideoPath") ? document.getElementById("editorInputVideoPath").value : "";
        const outputDir = document.getElementById("asrOutputFolder") ? document.getElementById("asrOutputFolder").value : "";
        const outputFilename = document.getElementById("asrOutputFileName") ? document.getElementById("asrOutputFileName").value : "";
        
        if (!videoPath) {
            showToast("Vui lòng chọn Video ở thẻ Cài đặt thông số trước!", "warning");
            appendLog("Lỗi: Chưa chọn video đầu vào.", "error");
            return;
        }

        const originalBtnText = '<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; margin-right: 4px;"><path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z"/><path d="M16 11l-4 4-4-4"/></svg> Quét phụ đề';
        
        // Chuyển nút sang trạng thái DỪNG KHẨN CẤP
        isScanningAsr = true;
        asrAbortController = new AbortController();
        btnScanAsr.disabled = false;
        btnScanAsr.style.background = '#ef4444';
        btnScanAsr.style.color = '#fff';
        btnScanAsr.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" style="vertical-align: middle; margin-right: 4px;"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg> 🛑 Dừng Quét (Khẩn Cấp)';
        
        // Mở rộng Terminal Log để người dùng quan sát trực quan
        const termOverlay = document.getElementById("terminalOverlay");
        if (termOverlay && termOverlay.classList.contains("collapsed")) {
            termOverlay.classList.remove("collapsed");
            termOverlay.classList.add("expanded");
            const toggleBtn = document.getElementById("toggleTerminalBtn");
            if (toggleBtn) toggleBtn.textContent = "Thu gọn";
        }

        appendLog(`═══════════════════════════════════════════════════`, "info");
        appendLog(`🚀 BẮT ĐẦU QUY TRÌNH NHẬN DẠNG PHỤ ĐỀ ASR (${modelLabel})`, "info");
        appendLog(`═══════════════════════════════════════════════════`, "info");
        
        try {
            // 1. Kiểm tra trạng thái môi trường
            appendLog("🔍 Đang kiểm tra môi trường chạy ASR trên máy...");
            const checkRes = await fetch("/api/asr/check", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ model: modelName })
            });
            const checkData = await checkRes.json();
            
            appendLog(`⚡ Lõi Whisper C++ Native: ${checkData.has_cli ? '✅ Đã sẵn sàng' : '📥 Chưa có (Hệ thống sẽ tự động tải ~15MB)...'}`);
            appendLog(`🧠 Model AI Whisper (${modelLabel}): ${checkData.has_model ? '✅ Đã sẵn sàng' : '📥 Chưa có (Hệ thống sẽ tự động tải ~140MB)...'}`);
            
            if (!checkData.installed && !checkData.has_cli && !checkData.has_model) {
                appendLog(`ℹ️ Hệ thống bắt đầu tải tự động các tệp AI còn thiếu. Vui lòng chờ hoàn tất trong giây lát!`, "info");
            }
            
            // 2. Chạy quét phụ đề
            const asrLangSelect = document.getElementById('asrLangSelect');
            const language = asrLangSelect ? asrLangSelect.value : 'auto';
            const asrDevSelect = document.getElementById('asrHardwareDevice');
            const hardwareDevice = asrDevSelect ? asrDevSelect.value : 'auto';
            
            const scanRes = await fetch("/api/asr/scan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                signal: asrAbortController.signal,
                body: JSON.stringify({ 
                    model: modelName,
                    language: language,
                    device: hardwareDevice,
                    videoPath: videoPath,
                    outputDir: outputDir,
                    outputFilename: outputFilename
                })
            });
            
            const reader = scanRes.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (isScanningAsr) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let lines = buffer.split('\n');
                buffer = lines.pop(); // giữ dòng chưa hoàn chỉnh trong buffer

                for (let line of lines) {
                    line = line.trim();
                    if (!line) continue;
                    
                    if (line.startsWith("[PROGRESS]")) {
                        const percentStr = line.replace("[PROGRESS]", "").trim();
                        const percent = parseInt(percentStr);
                        if (!isNaN(percent)) {
                            btnScanAsr.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" style="vertical-align: middle; margin-right: 4px;"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg> 🛑 Dừng (${percent}%)`;
                        }
                        continue;
                    }

                    if (line.startsWith("[RESULT]")) {
                        const jsonStr = line.replace("[RESULT]", "").trim();
                        try {
                            const scanData = JSON.parse(jsonStr);
                            if (scanData.success) {
                                appendLog("✅ Hoàn tất bóc tách phụ đề thành công!", "success");
                                showToast("Quét phụ đề thành công!", "success");
                                if (scanData.srt_path || scanData.srtPath) {
                                    const finalSrt = scanData.srt_path || scanData.srtPath;
                                    window.lastGeneratedSrtPath = finalSrt;
                                    
                                    // Tự động tải vào trình biên tập
                                    if (typeof loadSrtToEditor === 'function') {
                                        loadSrtToEditor(finalSrt);
                                        
                                        // Chuyển sang tab Biên tập
                                        const editorTab = document.querySelector('.nav-tab[data-target="viewEditor"]');
                                        if (editorTab) {
                                            editorTab.click();
                                            showToast('Đã chuyển sang Trình biên tập!', 'success');
                                        }
                                    }
                                }
                            } else {
                                appendLog(`🛑 Lỗi quét phụ đề: ${scanData.error}`, "error");
                                showToast(`Lỗi quét ASR: ${scanData.error}`, "error");
                            }
                        } catch(e) {
                            appendLog("Lỗi phân tích kết quả: " + e.message, "error");
                        }
                    } else {
                        // Hiển thị trực tiếp log ra terminal
                        appendLog(line);
                    }
                }
            }
            
        } catch (e) {
            if (e.name === 'AbortError') {
                appendLog("🛑 Tiến trình đã được dừng an toàn.", "warning");
            } else {
                console.error(e);
                appendLog(`🛑 Có lỗi xảy ra: ${e.message}`, "error");
                showToast("Có lỗi xảy ra: " + e.message, "error");
            }
        } finally {
            isScanningAsr = false;
            btnScanAsr.disabled = false;
            btnScanAsr.innerHTML = originalBtnText;
            btnScanAsr.style.background = '';
            btnScanAsr.style.color = '';
        }
    });
}



// ASR Output Folder Selection
const btnSelectAsrOutputFolder = document.getElementById('btnSelectAsrOutputFolder');
if (btnSelectAsrOutputFolder) {
    btnSelectAsrOutputFolder.addEventListener('click', async () => {
        if (window.pywebview) {
            const dir = await window.pywebview.api.select_output_directory();
            if (dir) {
                document.getElementById('asrOutputFolder').value = dir;
            }
        }
    });
}

// Load generated SRT to editor
const btnLoadAsrSrt = document.getElementById('btnLoadAsrSrt');
if (btnLoadAsrSrt) {
    btnLoadAsrSrt.addEventListener('click', () => {
        if (window.lastGeneratedSrtPath && typeof loadSrtToEditor === 'function') {
            loadSrtToEditor(window.lastGeneratedSrtPath);
            showToast('Đã tải phụ đề vào Trình biên tập', 'success');
        } else {
            showToast('Không tìm thấy file phụ đề hoặc chưa quét xong!', 'error');
        }
    });
}

// --- Export & Hardware Logic ---
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('/api/system/hardware');
        const data = await res.json();
        if (data.success) {
            if (data.encoders) {
                const encoderSelect = document.getElementById('exportEncoder');
                if (encoderSelect) {
                    const currentVal = encoderSelect.value;
                    encoderSelect.innerHTML = '';
                    const autoOpt = document.createElement('option');
                    autoOpt.value = 'auto';
                    autoOpt.textContent = '⚡ Tự động tối ưu phần cứng (GPU Siêu nhanh)';
                    encoderSelect.appendChild(autoOpt);
                    data.encoders.forEach(enc => {
                        const opt = document.createElement('option');
                        opt.value = enc.id;
                        opt.textContent = enc.name + (enc.is_gpu ? ' (Tối ưu)' : '');
                        encoderSelect.appendChild(opt);
                    });
                    if (currentVal && currentVal !== 'auto') {
                        encoderSelect.value = currentVal;
                    } else {
                        encoderSelect.value = 'auto';
                    }
                }
            }
            if (data.ai_devices) {
                const asrDevSelect = document.getElementById('asrHardwareDevice');
                if (asrDevSelect) {
                    asrDevSelect.innerHTML = '';
                    data.ai_devices.forEach(dev => {
                        const opt = document.createElement('option');
                        opt.value = dev.id;
                        opt.textContent = dev.name;
                        if (!dev.available) {
                            opt.disabled = true;
                            opt.style.color = '#64748b';
                        }
                        asrDevSelect.appendChild(opt);
                    });
                }
            }
        }
    } catch(e) {
        console.error("Hardware scan failed", e);
    }
});

document.addEventListener('DOMContentLoaded', () => {
    updateSubPreview();
});

const btnSelectLogo = document.getElementById('btnSelectLogo');
if (btnSelectLogo) {
    btnSelectLogo.addEventListener('click', async () => {
        const path = await selectFile('image');
        if (path) {
            document.getElementById('logoPath').value = path;
            const filename = path.split('\\').pop().split('/').pop();
            document.getElementById('logoPreviewName').textContent = "Đã chọn: " + filename;
            btnSelectLogo.style.borderColor = "#10b981";
        }
    });
}

// ═════════════════════════════════════════════════════════════
// 🎙️ LIVE TTS & DUBBING PREVIEW AUDIO ENGINE
// ═════════════════════════════════════════════════════════════
// ═════════════════════════════════════════════════════════════
// 🎙️ ADVANCED LIVE TTS & DUBBING PREVIEW AUDIO ENGINE (20-SENTENCE SLIDING BUFFER)
// ═════════════════════════════════════════════════════════════
class LiveDubbingEngine {
    constructor() {
        this.cache = new Map();
        this.pendingPromises = new Map();
        this.currentAudio = null;
        this.baseVideoVolume = 1;
        this.generation = 0;
        this.buffering = null;
        this.boundPlayers = new WeakSet();
    }

    stop() {
        this.generation++;
        this.buffering = null;
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio = null;
        }
    }

    restoreVolume(videoEl, targetVol) {
        if (videoEl) videoEl.volume = Math.max(0, Math.min(1, targetVol ?? this.baseVideoVolume));
    }

    timelineKey(subtitles, voiceId, speed) {
        return '';
    }

    async prepare(subtitles, voiceId, speed) {
        // Đã gỡ bỏ tính năng tạo track nghe thử nền theo yêu cầu (quá lâu và không thể nghe trực tiếp)
        return null;
    }

    async preloadChunk(subtitles, startIndex, count, voiceId, speed) {
        // Đã vô hiệu hóa preload nghe thử
        return;
    }

    async syncWithPlayer(videoEl, subtitles, options = {}) {
        // Đã vô hiệu hóa phát âm thanh nghe thử trực tiếp khi tua/phát video
        return;
    }
}

window.liveDubbingEngine = new LiveDubbingEngine();
['dubbingSpeed', 'reviewSpeed', 'reviewVoiceSelect', 'dubbingVoiceInput'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => window.liveDubbingEngine.stop());
});

// --- Live Subtitle Overlay & Audio Sync Logic ---
const globalVideoPlayer = document.getElementById('videoPlayer');
if (globalVideoPlayer) {
    globalVideoPlayer.addEventListener('pause', () => {
        window.liveDubbingEngine.stop();
        window.liveDubbingEngine.restoreVolume(globalVideoPlayer);
    });
    globalVideoPlayer.addEventListener('seeking', () => {
        window.liveDubbingEngine.stop();
        window.liveDubbingEngine.restoreVolume(globalVideoPlayer);
    });
    globalVideoPlayer.addEventListener('ended', () => {
        window.liveDubbingEngine.stop();
        window.liveDubbingEngine.restoreVolume(globalVideoPlayer);
    });

    let _lastPreviewSubId = undefined;
    window._invalidateSubPreviewStyles = () => { _lastPreviewSubId = undefined; };

    globalVideoPlayer.addEventListener('timeupdate', () => {
        const isSubEnabled = document.getElementById('subtitlesEnabled')?.checked ?? true;
        const isEditedMode = btnPreviewEdited && btnPreviewEdited.classList.contains('active');
        const overlay = document.getElementById('videoOverlay');
        const isDrawingMode = overlay && overlay.style.display === 'block' && typeof drawMode !== 'undefined' && drawMode === 'sub';
        
        if (!isSubEnabled || (!isEditedMode && !isDrawingMode && !isEditingSubBox)) {
            if (subPreviewBox && _lastPreviewSubId !== null) {
                subPreviewBox.style.display = 'none';
                _lastPreviewSubId = null;
            }
            if (!isEditedMode && !isDrawingMode && !isEditingSubBox) {
                window.liveDubbingEngine.stop();
                window.liveDubbingEngine.restoreVolume(globalVideoPlayer);
            }
            return;
        }
        
        if (!srtData || srtData.length === 0) {
            if ((isDrawingMode || isEditingSubBox) && subPreviewBox) {
                if (_lastPreviewSubId !== '__placeholder__') {
                    _lastPreviewSubId = '__placeholder__';
                    setSubtitlePreviewText('Phụ đề mẫu');
                    subPreviewBox.style.display = 'flex';
                    applySubStylesToElement(subPreviewBox);
                }
            } else if (subPreviewBox && _lastPreviewSubId !== null) {
                subPreviewBox.style.display = 'none';
                _lastPreviewSubId = null;
            }
            return;
        }
        
        const currentTime = globalVideoPlayer.currentTime;
        const activeSub = srtData.find(s => currentTime >= s.startSeconds && currentTime <= s.endSeconds);
        
        if (!subPreviewBox) {
            subPreviewBox = document.createElement('div');
            subPreviewBox.className = 'sub-preview-box';
            const wrapper = document.getElementById('videoZoomWrapper') || document.querySelector('.video-container');
            if (wrapper) wrapper.appendChild(subPreviewBox);
            
            if (!currentSubRegion) {
                currentSubRegion = { x: 20, y: 81.5, w: 60, h: 9.5, customPos: true };
            }
            
            applySubStylesToElement(subPreviewBox);
            setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
                currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
                syncSubRegionInputs(newPx, newPy, newPw, newPh);
            });
        } else {
            const wrapper = document.getElementById('videoZoomWrapper') || document.querySelector('.video-container');
            if (wrapper && subPreviewBox.parentElement !== wrapper) {
                wrapper.appendChild(subPreviewBox);
            }
        }
        
        // DIFF CHECK: Chỉ tính toán lại Style & Text khi câu phụ đề thực sự thay đổi
        if (activeSub) {
            if (_lastPreviewSubId !== activeSub.id) {
                _lastPreviewSubId = activeSub.id;
                const displayText = activeSub.translation || activeSub.text;
                setSubtitlePreviewText(displayText);
                subPreviewBox.style.display = 'flex';
                applySubStylesToElement(subPreviewBox);
            }
        } else {
            if (isDrawingMode || isEditingSubBox) {
                if (_lastPreviewSubId !== '__placeholder__') {
                    _lastPreviewSubId = '__placeholder__';
                    setSubtitlePreviewText('Phụ đề mẫu');
                    subPreviewBox.style.display = 'flex';
                    applySubStylesToElement(subPreviewBox);
                }
            } else {
                if (_lastPreviewSubId !== null) {
                    _lastPreviewSubId = null;
                    setSubtitlePreviewText('');
                    subPreviewBox.style.display = 'none';
                }
            }
        }
    });
}

// Fullscreen F11 Shortcut Support
window.addEventListener('keydown', (e) => {
    if (e.key === 'F11') {
        e.preventDefault();
        if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) {
            window.pywebview.api.toggle_fullscreen();
        } else {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        }
    }
});

// ==========================================
// VIDEO DOWNLOADER STUDIO LOGIC
// ==========================================
let currentDownloadFormat = 'mp4';
let currentDownloadInfo = null;
let lastDownloadedFile = null;

const downloadInputUrl = document.getElementById('downloadInputUrl');
const btnPasteDownloadUrl = document.getElementById('btnPasteDownloadUrl');
const btnAnalyzeUrl = document.getElementById('btnAnalyzeUrl');
const downloadEmptyPlaceholder = document.getElementById('downloadEmptyPlaceholder');
const downloadInfoBox = document.getElementById('downloadInfoBox');
const downloadMultiVideosBanner = document.getElementById('downloadMultiVideosBanner');
const downloadMultiCountText = document.getElementById('downloadMultiCountText');
const btnDownloadAllMultiVideos = document.getElementById('btnDownloadAllMultiVideos');
const downloadMultiVideosSection = document.getElementById('downloadMultiVideosSection');
const downloadMultiVideosGrid = document.getElementById('downloadMultiVideosGrid');
const downloadMultiSelectedHint = document.getElementById('downloadMultiSelectedHint');
const downloadVideoThumb = document.getElementById('downloadVideoThumb');
const downloadVideoDurationBadge = document.getElementById('downloadVideoDurationBadge');
const downloadVideoTitle = document.getElementById('downloadVideoTitle');
const downloadVideoUploader = document.getElementById('downloadVideoUploader');
const downloadVideoPlatformBadge = document.getElementById('downloadVideoPlatformBadge');
const downloadProgressBox = document.getElementById('downloadProgressBox');
const downloadProgressStatusText = document.getElementById('downloadProgressStatusText');
const downloadProgressSpeedEta = document.getElementById('downloadProgressSpeedEta');
const downloadCompletedActions = document.getElementById('downloadCompletedActions');
const downloadCompletedSpecs = document.getElementById('downloadCompletedSpecs');
const downloadSpecsResolution = document.getElementById('downloadSpecsResolution');
const downloadSpecsFps = document.getElementById('downloadSpecsFps');
const downloadSpecsCodec = document.getElementById('downloadSpecsCodec');
const downloadSpecsRatio = document.getElementById('downloadSpecsRatio');
const btnDownloadFormatVideo = document.getElementById('btnDownloadFormatVideo');
const btnDownloadFormatAudio = document.getElementById('btnDownloadFormatAudio');
const downloadResolutionGroup = document.getElementById('downloadResolutionGroup');
const downloadResolutionSelect = document.getElementById('downloadResolutionSelect');
const downloadOutputDir = document.getElementById('downloadOutputDir');
const btnSelectDownloadDir = document.getElementById('btnSelectDownloadDir');
const btnStartDownload = document.getElementById('btnStartDownload');
const btnSendToEditor = document.getElementById('btnSendToEditor');
const btnSendToReview = document.getElementById('btnSendToReview');
const btnOpenDownloadFolder = document.getElementById('btnOpenDownloadFolder');
const downloadHistoryList = document.getElementById('downloadHistoryList');
const downloadHistoryEmpty = document.getElementById('downloadHistoryEmpty');
const btnClearDownloadHistory = document.getElementById('btnClearDownloadHistory');

// Helper: Open Native Windows Folder Picker Dialog (using shared selectDirectory defined at line 314)


// 1. Paste URL from Clipboard
if (btnPasteDownloadUrl && downloadInputUrl) {
    btnPasteDownloadUrl.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                downloadInputUrl.value = text.trim();
                showToast('Đã dán liên kết từ bộ nhớ tạm!', 'info');
                // Auto trigger analyze if valid url
                if (text.startsWith('http')) {
                    btnAnalyzeUrl?.click();
                }
            }
        } catch (e) {
            showToast('Vui lòng dán thủ công bằng Ctrl+V', 'warning');
        }
    });
}

// 2. Format Switcher (Video MP4 vs Audio MP3)
if (btnDownloadFormatVideo && btnDownloadFormatAudio) {
    btnDownloadFormatVideo.addEventListener('click', () => {
        currentDownloadFormat = 'mp4';
        btnDownloadFormatVideo.classList.add('active');
        btnDownloadFormatVideo.style.borderColor = '#38bdf8';
        btnDownloadFormatVideo.style.color = '#38bdf8';
        btnDownloadFormatAudio.classList.remove('active');
        btnDownloadFormatAudio.style.borderColor = '#334155';
        btnDownloadFormatAudio.style.color = '#cbd5e1';
        if (downloadResolutionGroup) downloadResolutionGroup.style.display = 'block';
    });

    btnDownloadFormatAudio.addEventListener('click', () => {
        currentDownloadFormat = 'mp3';
        btnDownloadFormatAudio.classList.add('active');
        btnDownloadFormatAudio.style.borderColor = '#38bdf8';
        btnDownloadFormatAudio.style.color = '#38bdf8';
        btnDownloadFormatVideo.classList.remove('active');
        btnDownloadFormatVideo.style.borderColor = '#334155';
        btnDownloadFormatVideo.style.color = '#cbd5e1';
        if (downloadResolutionGroup) downloadResolutionGroup.style.display = 'none';
    });
}

// 3. Select Output Directory (Single Video Mode)
if (downloadOutputDir) {
    const savedDir = localStorage.getItem('download_output_dir');
    if (savedDir) {
        downloadOutputDir.value = savedDir;
    }
}

if (btnSelectDownloadDir && downloadOutputDir) {
    btnSelectDownloadDir.addEventListener('click', async () => {
        const path = await selectDirectory('Chọn thư mục lưu video tải về');
        if (path) {
            downloadOutputDir.value = path;
            const batchDirInput = document.getElementById('douyinBatchOutputDir');
            if (batchDirInput) batchDirInput.value = path;
            localStorage.setItem('download_output_dir', path);
            showToast('Đã chọn thư mục lưu: ' + path, 'info');
        }
    });
}

const btnClearDownloadDir = document.getElementById('btnClearDownloadDir');
if (btnClearDownloadDir && downloadOutputDir) {
    btnClearDownloadDir.addEventListener('click', () => {
        downloadOutputDir.value = '';
        const batchDirInput = document.getElementById('douyinBatchOutputDir');
        if (batchDirInput) batchDirInput.value = '';
        localStorage.removeItem('download_output_dir');
        showToast('Đã đặt lại thư mục lưu về mặc định (/downloads)', 'info');
    });
}






// 4. Analyze URL
if (btnAnalyzeUrl && downloadInputUrl) {
    btnAnalyzeUrl.addEventListener('click', async () => {
        const url = downloadInputUrl.value.trim();
        if (!url) {
            showToast('Vui lòng nhập đường dẫn URL video!', 'warning');
            return;
        }

        btnAnalyzeUrl.disabled = true;
        btnAnalyzeUrl.innerHTML = `<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Đang phân tích...`;

        try {
            const res = await fetch('/api/download/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            
            if (res.status === 404) {
                showToast('Máy chủ backend chưa nhận API mới. Vui lòng tắt và khởi động lại ứng dụng!', 'warning');
                return;
            }

            let data;
            try {
                data = await res.json();
            } catch (jsonErr) {
                showToast('Lỗi phản hồi từ máy chủ. Vui lòng khởi động lại ứng dụng!', 'error');
                return;
            }

            if (!res.ok || data.error) {
                showToast(data.error || `Lỗi từ máy chủ (Mã: ${res.status})`, 'error');
                return;
            }

            currentDownloadInfo = data;

            // Render Info UI
            if (downloadEmptyPlaceholder) downloadEmptyPlaceholder.style.display = 'none';
            if (downloadInfoBox) downloadInfoBox.style.display = 'block';
            if (downloadCompletedActions) downloadCompletedActions.style.display = 'none';
            if (downloadProgressBox) downloadProgressBox.style.display = 'none';

            // Helper để chọn 1 video trong danh sách
            function selectVideoFromMultiList(vObj, idx, totalCount) {
                currentDownloadInfo = vObj;
                if (downloadInputUrl && vObj.url) {
                    downloadInputUrl.value = vObj.url;
                }
                if (downloadVideoThumb) downloadVideoThumb.src = vObj.thumbnail || '';
                if (downloadVideoDurationBadge) downloadVideoDurationBadge.textContent = formatDurationStr(vObj.duration);
                if (downloadVideoTitle) downloadVideoTitle.textContent = vObj.title || 'Video không tiêu đề';
                if (downloadVideoUploader) downloadVideoUploader.textContent = `👤 ${vObj.uploader || vObj.author || 'Không rõ'}`;
                if (downloadVideoPlatformBadge) downloadVideoPlatformBadge.textContent = vObj.extractor || 'Web';

                if (downloadResolutionSelect && vObj.resolutions) {
                    downloadResolutionSelect.innerHTML = '';
                    vObj.resolutions.forEach(r => {
                        const opt = document.createElement('option');
                        opt.value = r.format_id;
                        opt.textContent = r.label;
                        downloadResolutionSelect.appendChild(opt);
                    });
                }

                if (downloadMultiSelectedHint) {
                    downloadMultiSelectedHint.textContent = `Đang chọn: Video ${idx + 1}/${totalCount}`;
                }

                // Cập nhật active border cho các card
                if (downloadMultiVideosGrid) {
                    const cards = downloadMultiVideosGrid.querySelectorAll('.multi-video-item-card');
                    cards.forEach((c, cIdx) => {
                        if (cIdx === idx) {
                            c.style.borderColor = '#38bdf8';
                            c.style.background = 'rgba(56, 189, 248, 0.12)';
                        } else {
                            c.style.borderColor = '#334155';
                            c.style.background = '#0f172a';
                        }
                    });
                }
            }

            // 1. Kiểm tra nếu có nhiều video trong link
            const videoList = (data.videos && Array.isArray(data.videos) && data.videos.length > 0) ? data.videos : [data];
            
            if (videoList.length > 1) {
                if (downloadMultiVideosBanner) downloadMultiVideosBanner.style.display = 'flex';
                if (downloadMultiVideosSection) downloadMultiVideosSection.style.display = 'block';
                if (downloadMultiCountText) downloadMultiCountText.textContent = `Tìm thấy ${videoList.length} video trong liên kết này!`;

                if (downloadMultiVideosGrid) {
                    downloadMultiVideosGrid.innerHTML = '';
                    videoList.forEach((v, idx) => {
                        const card = document.createElement('div');
                        card.className = 'multi-video-item-card';
                        card.style.cssText = `
                            background: ${idx === 0 ? 'rgba(56, 189, 248, 0.12)' : '#0f172a'};
                            border: 1px solid ${idx === 0 ? '#38bdf8' : '#334155'};
                            border-radius: 8px;
                            padding: 8px;
                            cursor: pointer;
                            transition: all 0.2s ease;
                            display: flex;
                            flex-direction: column;
                            gap: 6px;
                        `;
                        const thumbnailUrl = safeHttpUrl(v.thumbnail);
                        const videoTitle = v.title || `Video ${idx + 1}`;
                        card.innerHTML = `
                            <div style="position: relative; width: 100%; height: 75px; border-radius: 6px; overflow: hidden; background: #020617;">
                                ${thumbnailUrl ? `<img src="${escapeHtml(thumbnailUrl)}" alt="" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'">` : ''}
                                <span style="position: absolute; bottom: 3px; right: 3px; background: rgba(0,0,0,0.85); color: #fff; font-size: 9.5px; font-weight: 600; padding: 1px 4px; border-radius: 3px;">
                                    ${formatDurationStr(v.duration)}
                                </span>
                                <span style="position: absolute; top: 3px; left: 3px; background: #0284c7; color: #fff; font-size: 9px; font-weight: 700; padding: 1px 4px; border-radius: 3px;">
                                    #${idx + 1}
                                </span>
                            </div>
                            <div style="font-size: 11.5px; font-weight: 600; color: #f8fafc; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${escapeHtml(videoTitle)}">
                                ${escapeHtml(videoTitle)}
                            </div>
                        `;

                        card.addEventListener('click', () => {
                            selectVideoFromMultiList(v, idx, videoList.length);
                        });

                        downloadMultiVideosGrid.appendChild(card);
                    });
                }

                // Nút tải tất cả hàng loạt
                if (btnDownloadAllMultiVideos) {
                    btnDownloadAllMultiVideos.onclick = () => {
                        const isBilibili = (data.extractor === 'Bilibili') || (videoList[0] && videoList[0].extractor === 'Bilibili');
                        if (isBilibili) {
                            // Bilibili: Tải toàn bộ các tập bằng cơ chế -p ALL chuyên biệt của BBDown
                            const baseBiliUrl = (videoList[0].url || url).split('?')[0];
                            const cleanTitle = (data.title || videoList[0].title || 'Bilibili Video').split(' - [P')[0];
                            currentDownloadInfo = {
                                ...videoList[0],
                                page: 'ALL',
                                url: baseBiliUrl,
                                title: `${cleanTitle} (Tải toàn bộ ${videoList.length} tập)`
                            };
                            if (downloadInputUrl) downloadInputUrl.value = baseBiliUrl;
                            if (downloadVideoTitle) downloadVideoTitle.textContent = currentDownloadInfo.title;
                            if (downloadMultiSelectedHint) downloadMultiSelectedHint.textContent = `⚡ Chế độ: Tải toàn bộ ${videoList.length} tập`;
                            showToast(`Đã chọn chế độ tải toàn bộ ${videoList.length} tập! Đang khởi động tải xuống...`, 'info');
                            btnStartDownload.click();
                            return;
                        }

                        scannedDouyinVideos = videoList.map(v => ({
                            aweme_id: v.video_id || `vid_${Math.random()}`,
                            desc: v.title || 'Video Douyin',
                            clean_title: v.title || 'Video Douyin',
                            author: v.uploader || v.author || 'Tác giả',
                            duration: v.duration || 0,
                            duration_formatted: formatDurationStr(v.duration),
                            cover: v.thumbnail || '',
                            url: v.url || url,
                            download_url: (v.video_urls && v.video_urls[0]) || ''
                        }));
                        selectedDouyinVideoIds = new Set(scannedDouyinVideos.map(v => v.aweme_id));

                        if (tabDownloadChannel) tabDownloadChannel.click();
                        if (douyinChannelInfoBanner) douyinChannelInfoBanner.style.display = 'block';
                        if (douyinChannelNickname) douyinChannelNickname.textContent = `Danh sách ${videoList.length} video từ Link`;
                        if (douyinChannelSignature) douyinChannelSignature.textContent = `Đã phân tích toàn bộ ${videoList.length} video từ liên kết bạn cung cấp`;
                        if (douyinChannelVideoCountBadge) douyinChannelVideoCountBadge.textContent = `${videoList.length} Video`;
                        renderDouyinVideoGrid();
                        showToast(`Đã nạp toàn bộ ${videoList.length} video vào bảng tải hàng loạt!`, 'success');
                    };
                }

                showToast(`Phân tích thành công! Đã tìm thấy ${videoList.length} video trong link.`, 'success');
            } else {
                if (downloadMultiVideosBanner) downloadMultiVideosBanner.style.display = 'none';
                if (downloadMultiVideosSection) downloadMultiVideosSection.style.display = 'none';
                showToast('Phân tích video thành công!', 'success');
            }

            // Chọn video đầu tiên làm active
            selectVideoFromMultiList(videoList[0], 0, videoList.length);
        } catch (e) {
            showToast('Lỗi kết nối khi phân tích: ' + e.message, 'error');
        } finally {
            btnAnalyzeUrl.disabled = false;
            btnAnalyzeUrl.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg><span>Phân tích Video</span>`;
        }
    });
}

// 5. Start Download
if (btnStartDownload) {
    btnStartDownload.addEventListener('click', async () => {
        const activeUrl = (currentDownloadInfo && currentDownloadInfo.url) ? currentDownloadInfo.url.trim() : '';
        const inputUrl = downloadInputUrl?.value.trim() || '';
        const url = activeUrl || inputUrl;
        if (!url) {
            showToast('Vui lòng dán liên kết video!', 'warning');
            return;
        }

        btnStartDownload.disabled = true;
        btnStartDownload.innerHTML = `<span>⏳ Đang tải xuống...</span>`;
        if (downloadProgressBox) downloadProgressBox.style.display = 'block';
        if (downloadCompletedActions) downloadCompletedActions.style.display = 'none';
        if (downloadCompletedSpecs) downloadCompletedSpecs.style.display = 'none';
        if (downloadProgressBar) downloadProgressBar.style.width = '0%';
        if (downloadProgressStatusText) downloadProgressStatusText.textContent = 'Khởi tạo tác vụ tải...';
        if (downloadProgressSpeedEta) downloadProgressSpeedEta.textContent = '-- MB/s • Còn --';

        const payload = {
            url: url,
            format_id: downloadResolutionSelect?.value || 'best',
            is_audio: currentDownloadFormat === 'mp3',
            output_dir: downloadOutputDir?.value.trim() || '',
            video_urls: currentDownloadInfo?.video_urls || null,
            info: currentDownloadInfo || null
        };


        try {
            const response = await fetch('/api/download/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep unfinished line

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6).trim();
                        if (!jsonStr) continue;
                        try {
                            const data = JSON.parse(jsonStr);
                            if (data.status === 'downloading') {
                                if (downloadProgressBar) downloadProgressBar.style.width = `${data.percent}%`;
                                if (downloadProgressStatusText) downloadProgressStatusText.textContent = `Đang tải: ${data.percent}%`;
                                if (downloadProgressSpeedEta) downloadProgressSpeedEta.textContent = `${data.speed} • Còn ${data.eta}`;
                            } else if (data.status === 'processing') {
                                if (downloadProgressStatusText) downloadProgressStatusText.textContent = data.message || 'Đang đóng gói FFmpeg...';
                                if (downloadProgressBar) downloadProgressBar.style.width = '99%';
                            } else if (data.status === 'completed') {
                                lastDownloadedFile = data;
                                if (downloadProgressBar) downloadProgressBar.style.width = '100%';

                                const specs = data.specs || {};
                                const resLabel = specs.resolution_label || specs.resolution || data.resolution_label || data.resolution || '';
                                const fpsVal = specs.fps || data.fps || '';
                                const codecVal = specs.vcodec || data.vcodec || '';
                                const ratioVal = specs.aspect_ratio || data.aspect_ratio || '';

                                if (resLabel) {
                                    if (downloadProgressStatusText) downloadProgressStatusText.textContent = `✅ Đã tải xong: ${resLabel}!`;
                                } else {
                                    if (downloadProgressStatusText) downloadProgressStatusText.textContent = '✅ Đã tải xong!';
                                }

                                if (downloadProgressSpeedEta) {
                                    const parts = [];
                                    if (specs.resolution) parts.push(specs.resolution);
                                    if (fpsVal) parts.push(`${fpsVal} FPS`);
                                    if (data.file_size) parts.push(data.file_size);
                                    downloadProgressSpeedEta.textContent = parts.join(' • ') || data.file_size || '';
                                }

                                if (downloadCompletedSpecs && (specs.resolution || specs.summary)) {
                                    if (downloadSpecsResolution) {
                                        downloadSpecsResolution.textContent = specs.resolution ? `${specs.resolution} (${specs.resolution_label || ''})` : (specs.summary || '--');
                                    }
                                    if (downloadSpecsFps) downloadSpecsFps.textContent = fpsVal ? `${fpsVal} FPS` : '--';
                                    if (downloadSpecsCodec) downloadSpecsCodec.textContent = codecVal || '--';
                                    if (downloadSpecsRatio) downloadSpecsRatio.textContent = ratioVal || '--';
                                    downloadCompletedSpecs.style.display = 'block';
                                } else if (downloadCompletedSpecs) {
                                    downloadCompletedSpecs.style.display = 'none';
                                }

                                if (downloadCompletedActions) downloadCompletedActions.style.display = 'block';

                                // Save to download history
                                saveDownloadHistoryItem({
                                    id: Date.now(),
                                    title: data.title || data.file_name,
                                    file_path: data.file_path,
                                    file_name: data.file_name,
                                    file_size: data.file_size,
                                    resolution: resLabel || specs.resolution || '',
                                    fps: fpsVal || '',
                                    thumbnail: data.thumbnail || (currentDownloadInfo ? currentDownloadInfo.thumbnail : ''),
                                    platform: currentDownloadInfo ? currentDownloadInfo.extractor : 'Video',
                                    is_audio: currentDownloadFormat === 'mp3',
                                    timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
                                });

                                const toastMsg = resLabel ? `Tải video thành công (${resLabel})!` : 'Tải video thành công!';
                                showToast(toastMsg, 'success');
                            } else if (data.status === 'error') {
                                showToast('Lỗi tải video: ' + (data.error || 'Không xác định'), 'error');
                                if (downloadProgressStatusText) downloadProgressStatusText.textContent = '❌ Lỗi tải video';
                            }
                        } catch (err) {
                            console.error('SSE parse error:', err);
                        }
                    }
                }
            }
        } catch (e) {
            showToast('Lỗi kết nối máy chủ: ' + e.message, 'error');
            if (downloadProgressStatusText) downloadProgressStatusText.textContent = '❌ Lỗi kết nối';
        } finally {
            btnStartDownload.disabled = false;
            btnStartDownload.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg><span>BẮT ĐẦU TẢI XUỐNG</span>`;
        }
    });
}

// 6. Quick Action: Send to Editor
if (btnSendToEditor) {
    btnSendToEditor.addEventListener('click', () => {
        if (!lastDownloadedFile || !lastDownloadedFile.file_path) {
            showToast('Chưa có file video nào vừa tải!', 'warning');
            return;
        }
        sendVideoToEditor(lastDownloadedFile.file_path);
    });
}

// 7. Quick Action: Send to Review
if (btnSendToReview) {
    btnSendToReview.addEventListener('click', () => {
        if (!lastDownloadedFile || !lastDownloadedFile.file_path) {
            showToast('Chưa có file video nào vừa tải!', 'warning');
            return;
        }
        sendVideoToReview(lastDownloadedFile.file_path);
    });
}

// 8. Quick Action: Open Folder
if (btnOpenDownloadFolder) {
    btnOpenDownloadFolder.addEventListener('click', () => {
        if (lastDownloadedFile && lastDownloadedFile.file_path) {
            openDownloadFileFolder(lastDownloadedFile.file_path);
        } else {
            openDownloadFileFolder('');
        }
    });
}

// =========================================================================
// 9. BILIBILI ACCOUNT & QR LOGIN CONTROLLER (BBDown Engine)
// =========================================================================
const modalBilibiliLogin = document.getElementById('modalBilibiliLogin');
const btnBilibiliLoginModal = document.getElementById('btnBilibiliLoginModal');
const btnCloseBiliModal = document.getElementById('btnCloseBiliModal');
const btnDoneBiliModal = document.getElementById('btnDoneBiliModal');
const bilibiliLoginStatusText = document.getElementById('bilibiliLoginStatusText');
const biliStatusDot = document.getElementById('biliStatusDot');
const biliStatusLabel = document.getElementById('biliStatusLabel');
const tabBtnBiliQr = document.getElementById('tabBtnBiliQr');
const tabBtnBiliCookie = document.getElementById('tabBtnBiliCookie');
const tabContentBiliQr = document.getElementById('tabContentBiliQr');
const tabContentBiliCookie = document.getElementById('tabContentBiliCookie');
const btnGenBiliQr = document.getElementById('btnGenBiliQr');
const biliQrPlaceholder = document.getElementById('biliQrPlaceholder');
const biliQrImg = document.getElementById('biliQrImg');
const biliQrHint = document.getElementById('biliQrHint');
const biliCookieInput = document.getElementById('biliCookieInput');
const btnSaveBiliCookie = document.getElementById('btnSaveBiliCookie');

let biliLoginPollInterval = null;

async function checkBilibiliLoginStatus() {
    try {
        const res = await fetch('/api/download/bilibili/status');
        if (!res.ok) return;
        const data = await res.json();

        if (data.logged_in && data.cookie_valid) {
            // Cookie hợp lệ và server xác nhận đăng nhập thành công
            const vipBadge = data.is_vip ? ' 👑VIP' : '';
            const uname = data.uname ? ` (${data.uname})` : '';
            if (bilibiliLoginStatusText) bilibiliLoginStatusText.textContent = `🟢 Bilibili${vipBadge}${uname}`;
            if (biliStatusDot) biliStatusDot.style.background = '#10b981';
            if (biliStatusLabel) biliStatusLabel.textContent = `Đã đăng nhập Bilibili${vipBadge} - ${data.is_vip ? '4K/1080P 60fps mở khóa' : '1080P mở khóa'}`;
        } else if (data.logged_in && !data.cookie_valid) {
            // Có file cookie nhưng đã hết hạn / bị thu hồi
            if (bilibiliLoginStatusText) bilibiliLoginStatusText.textContent = '⚠️ Cookie Hết Hạn';
            if (biliStatusDot) biliStatusDot.style.background = '#ef4444';
            if (biliStatusLabel) biliStatusLabel.textContent = 'Cookie Bilibili đã hết hạn! Vui lòng đăng nhập lại để tải 1080P';
            // Hiển thị toast cảnh báo (chỉ 1 lần mỗi phiên)
            if (!window._biliCookieWarnShown) {
                window._biliCookieWarnShown = true;
                showToast('⚠️ Cookie Bilibili đã hết hạn. Bấm nút "Tài Khoản Bilibili" để đăng nhập lại nhận 1080P!', 'warning');
            }
        } else {
            if (bilibiliLoginStatusText) bilibiliLoginStatusText.textContent = '📺 Bilibili (Chưa đăng nhập)';
            if (biliStatusDot) biliStatusDot.style.background = '#f59e0b';
            if (biliStatusLabel) biliStatusLabel.textContent = 'Chưa đăng nhập (Chỉ tải phân giải giới hạn)';
        }
    } catch (e) {
        console.error('Error checking Bilibili status:', e);
    }
}


// Kiểm tra trạng thái Bilibili ngay khi mở app
checkBilibiliLoginStatus();

if (btnBilibiliLoginModal && modalBilibiliLogin) {
    btnBilibiliLoginModal.addEventListener('click', () => {
        modalBilibiliLogin.style.display = 'flex';
        checkBilibiliLoginStatus();
    });

    const closeBiliModal = () => {
        modalBilibiliLogin.style.display = 'none';
        if (biliLoginPollInterval) {
            clearInterval(biliLoginPollInterval);
            biliLoginPollInterval = null;
        }
    };

    if (btnCloseBiliModal) btnCloseBiliModal.addEventListener('click', closeBiliModal);
    if (btnDoneBiliModal) btnDoneBiliModal.addEventListener('click', closeBiliModal);
    modalBilibiliLogin.addEventListener('click', (e) => {
        if (e.target === modalBilibiliLogin) closeBiliModal();
    });
}

// Chuyển Tab: QR Code vs Cookie thủ công
if (tabBtnBiliQr && tabBtnBiliCookie && tabContentBiliQr && tabContentBiliCookie) {
    tabBtnBiliQr.addEventListener('click', () => {
        tabContentBiliQr.style.display = 'block';
        tabContentBiliCookie.style.display = 'none';
        tabBtnBiliQr.style.background = 'rgba(56, 189, 248, 0.2)';
        tabBtnBiliQr.style.borderColor = '#38bdf8';
        tabBtnBiliQr.style.color = '#38bdf8';
        tabBtnBiliCookie.style.background = 'transparent';
        tabBtnBiliCookie.style.borderColor = '#334155';
        tabBtnBiliCookie.style.color = '#94a3b8';
    });

    tabBtnBiliCookie.addEventListener('click', () => {
        tabContentBiliQr.style.display = 'none';
        tabContentBiliCookie.style.display = 'block';
        tabBtnBiliCookie.style.background = 'rgba(56, 189, 248, 0.2)';
        tabBtnBiliCookie.style.borderColor = '#38bdf8';
        tabBtnBiliCookie.style.color = '#38bdf8';
        tabBtnBiliQr.style.background = 'transparent';
        tabBtnBiliQr.style.borderColor = '#334155';
        tabBtnBiliQr.style.color = '#94a3b8';
    });
}

// Tạo mã QR Đăng Nhập
if (btnGenBiliQr) {
    btnGenBiliQr.addEventListener('click', async () => {
        btnGenBiliQr.disabled = true;
        btnGenBiliQr.innerHTML = `<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Đang tạo mã QR...`;

        try {
            const res = await fetch('/api/download/bilibili/login_qr', { method: 'POST' });
            const data = await res.json();
            if (!res.ok || data.error) {
                showToast(data.error || 'Không thể tạo mã QR Bilibili', 'error');
                return;
            }

            if (data.qr_image) {
                if (biliQrPlaceholder) biliQrPlaceholder.style.display = 'none';
                if (biliQrImg) {
                    biliQrImg.src = data.qr_image;
                    biliQrImg.style.display = 'block';
                }
                if (biliQrHint) {
                    biliQrHint.innerHTML = `<span style="color: #38bdf8; font-weight: 600;">Đang chờ quét...</span> Mở App Bilibili trên điện thoại và quét mã!`;
                }

                // Khởi động polling kiểm tra trạng thái quét
                if (biliLoginPollInterval) clearInterval(biliLoginPollInterval);
                biliLoginPollInterval = setInterval(async () => {
                    try {
                        const pRes = await fetch('/api/download/bilibili/login_poll');
                        const pData = await pRes.json();
                        if (pData.status === 'success' || pData.logged_in) {
                            clearInterval(biliLoginPollInterval);
                            biliLoginPollInterval = null;
                            showToast('Đăng nhập Bilibili thành công!', 'success');
                            if (biliQrHint) {
                                biliQrHint.innerHTML = `<span style="color: #10b981; font-weight: 700;">✅ Đã đăng nhập thành công!</span>`;
                            }
                            checkBilibiliLoginStatus();
                        } else if (pData.status === 'expired' || pData.status === 'timeout') {
                            clearInterval(biliLoginPollInterval);
                            biliLoginPollInterval = null;
                            if (biliQrHint) {
                                biliQrHint.innerHTML = `<span style="color: #ef4444;">${escapeHtml(pData.message || 'Mã đã hết hạn')}</span>`;
                            }
                        }
                    } catch (pollErr) {
                        console.error('Bilibili poll error:', pollErr);
                    }
                }, 2000);
            }
        } catch (e) {
            showToast('Lỗi kết nối máy chủ: ' + e.message, 'error');
        } finally {
            btnGenBiliQr.disabled = false;
            btnGenBiliQr.innerHTML = `<span>⚡ Tạo Mã QR Đăng Nhập Mới</span>`;
        }
    });
}

// Lưu Cookie thủ công
if (btnSaveBiliCookie && biliCookieInput) {
    btnSaveBiliCookie.addEventListener('click', async () => {
        const val = biliCookieInput.value.trim();
        if (!val) {
            showToast('Vui lòng nhập chuỗi Cookie hoặc SESSDATA!', 'warning');
            return;
        }
        btnSaveBiliCookie.disabled = true;
        try {
            const res = await fetch('/api/download/bilibili/save_cookie', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookie: val })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast(data.message || 'Đã lưu Cookie thành công!', 'success');
                biliCookieInput.value = '';
                checkBilibiliLoginStatus();
            } else {
                showToast(data.error || 'Lỗi lưu Cookie', 'error');
            }
        } catch (e) {
            showToast('Lỗi lưu Cookie: ' + e.message, 'error');
        } finally {
            btnSaveBiliCookie.disabled = false;
        }
    });
}

function sendVideoToEditor(filePath) {
    const editorTab = document.querySelector('.nav-tab[data-target="viewEditor"]');
    if (editorTab) editorTab.click();

    const editorInput = document.getElementById('editorInputVideoPath');
    if (editorInput) {
        editorInput.value = filePath;
    }

    if (videoPlayer) {
        videoPlayer.src = `/api/file?path=${encodeURIComponent(filePath)}`;
        videoPlayer.load();
        if (videoPlaceholder) videoPlaceholder.style.display = 'none';
        videoPlayer.style.display = 'block';
    }

    showToast('Đã nạp video vào Biên tập phim!', 'success');
}

function sendVideoToReview(filePath) {
    const reviewTab = document.querySelector('.nav-tab[data-target="viewReview"]');
    if (reviewTab) reviewTab.click();

    const reviewInput = document.getElementById('reviewInputVideoPath');
    if (reviewInput) {
        reviewInput.value = filePath;
    }

    if (typeof loadReviewVideoPlayer === 'function') {
        loadReviewVideoPlayer(filePath);
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

function openDownloadFileFolder(filePath) {
    const customDir = downloadOutputDir?.value.trim() || '';
    fetch('/api/download/open_folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath || '', folder_path: customDir })
    }).then(() => {
        showToast('Đang mở thư mục trong File Explorer...', 'info');
    }).catch(e => {
        showToast('Lỗi mở thư mục: ' + e.message, 'error');
    });
}

// ==========================================
// DOWNLOAD HISTORY STORAGE & RENDERING
// ==========================================
function getDownloadHistory() {
    try {
        const raw = localStorage.getItem('download_history');
        return raw ? JSON.parse(raw) : [];
    } catch {
        return [];
    }
}

function saveDownloadHistoryItem(item) {
    const history = getDownloadHistory();
    history.unshift(item);
    if (history.length > 20) history.pop(); // Keep top 20
    localStorage.setItem('download_history', JSON.stringify(history));
    renderDownloadHistory();
}

function renderDownloadHistory() {
    if (!downloadHistoryList) return;
    const history = getDownloadHistory();

    if (history.length === 0) {
        downloadHistoryList.innerHTML = `<div id="downloadHistoryEmpty" style="text-align: center; padding: 24px; color: #64748b; font-size: 13px;">Chưa có video nào trong lịch sử tải xuống.</div>`;
        return;
    }

    downloadHistoryList.innerHTML = '';
    history.forEach(item => {
        const row = document.createElement('div');
        row.className = 'download-history-item';

        const thumbSrc = safeHttpUrl(item.thumbnail);
        const thumbHtml = thumbSrc 
            ? `<img src="${escapeHtml(thumbSrc)}" class="download-history-thumb" alt="thumb">`
            : `<div class="download-history-thumb" style="display:flex;align-items:center;justify-content:center;color:#64748b;"><svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" fill="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg></div>`;

        row.innerHTML = `
            ${thumbHtml}
            <div class="download-history-info">
                <div class="download-history-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                <div class="download-history-meta">
                    <span class="platform-pill" style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: #1e293b; color: #38bdf8; border: 1px solid #334155;">${escapeHtml(item.platform || 'Video')}</span>
                    ${item.resolution ? `<span style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-weight: 700;">${escapeHtml(item.resolution)}</span>` : ''}
                    <span>📦 ${escapeHtml(item.file_size || '--')}</span>
                    <span>🕒 ${escapeHtml(item.timestamp || '')}</span>
                </div>
            </div>
            <div class="download-history-actions">
                ${!item.is_audio ? `<button class="btn primary-cyan small btn-hist-editor" title="Nạp vào Biên tập phim" style="padding: 5px 8px; font-size: 11px;">🎬 Biên tập</button>` : ''}
                ${!item.is_audio ? `<button class="btn secondary small btn-hist-review" title="Nạp vào Review Phim" style="padding: 5px 8px; font-size: 11px; border-color: #38bdf8; color: #38bdf8;">🎙️ Review</button>` : ''}
                <button class="btn secondary small btn-hist-folder" title="Mở thư mục" style="padding: 5px 8px; font-size: 11px;">📂</button>
                <button class="btn secondary small btn-hist-del" title="Xóa khỏi lịch sử" style="padding: 5px 8px; font-size: 11px; color: #f87171;">🗑️</button>
            </div>
        `;

        // Attach per-item events
        row.querySelector('.btn-hist-editor')?.addEventListener('click', () => sendVideoToEditor(item.file_path));
        row.querySelector('.btn-hist-review')?.addEventListener('click', () => sendVideoToReview(item.file_path));
        row.querySelector('.btn-hist-folder')?.addEventListener('click', () => openDownloadFileFolder(item.file_path));
        row.querySelector('.btn-hist-del')?.addEventListener('click', () => {
            const updated = getDownloadHistory().filter(h => h.id !== item.id);
            localStorage.setItem('download_history', JSON.stringify(updated));
            renderDownloadHistory();
        });

        downloadHistoryList.appendChild(row);
    });
}

if (btnClearDownloadHistory) {
    btnClearDownloadHistory.addEventListener('click', () => {
        localStorage.removeItem('download_history');
        renderDownloadHistory();
        showToast('Đã xóa toàn bộ lịch sử tải xuống', 'info');
    });
}

// Render history on startup
try {
    renderDownloadHistory();
} catch (e) {
    console.error("Error rendering download history:", e);
}

// ==========================================
// DOUYIN CHANNEL BATCH DOWNLOADER CONTROLLER
// ==========================================
let scannedDouyinVideos = [];
let selectedDouyinVideoIds = new Set();

function initDouyinChannelDownloader() {
    const tabDownloadSingle = document.getElementById('tabDownloadSingle');
    const tabDownloadChannel = document.getElementById('tabDownloadChannel');
    const sectionDownloadSingle = document.getElementById('sectionDownloadSingle');
    const sectionDownloadChannel = document.getElementById('sectionDownloadChannel');

    const douyinChannelInputUrl = document.getElementById('douyinChannelInputUrl');
    const btnPasteChannelUrl = document.getElementById('btnPasteChannelUrl');
    const douyinChannelLimitSelect = document.getElementById('douyinChannelLimitSelect');
    const btnScanDouyinChannel = document.getElementById('btnScanDouyinChannel');

    const douyinChannelInfoBanner = document.getElementById('douyinChannelInfoBanner');
    const douyinChannelAvatar = document.getElementById('douyinChannelAvatar');
    const douyinChannelNickname = document.getElementById('douyinChannelNickname');
    const douyinChannelSignature = document.getElementById('douyinChannelSignature');
    const douyinChannelFollowersBadge = document.getElementById('douyinChannelFollowersBadge');
    const douyinChannelLikesBadge = document.getElementById('douyinChannelLikesBadge');
    const douyinChannelVideoCountBadge = document.getElementById('douyinChannelVideoCountBadge');

    const douyinBatchActionsBar = document.getElementById('douyinBatchActionsBar');
    const douyinSelectAllCheckbox = document.getElementById('douyinSelectAllCheckbox');
    const douyinSelectedSummary = document.getElementById('douyinSelectedSummary');
    const douyinSubfolderCheckbox = document.getElementById('douyinSubfolderCheckbox');
    const btnStartDouyinBatchDownload = document.getElementById('btnStartDouyinBatchDownload');
    const btnStopDouyinBatchDownload = document.getElementById('btnStopDouyinBatchDownload');
    const btnDouyinOpenFolder = document.getElementById('btnDouyinOpenFolder');
    const douyinBatchOutputDir = document.getElementById('douyinBatchOutputDir');
    const btnSelectDouyinBatchDir = document.getElementById('btnSelectDouyinBatchDir');
    const btnClearDouyinBatchDir = document.getElementById('btnClearDouyinBatchDir');

    // Initialize custom directory from localStorage
    if (douyinBatchOutputDir) {
        const savedDir = localStorage.getItem('download_output_dir');
        if (savedDir) {
            douyinBatchOutputDir.value = savedDir;
        }
    }

    if (btnSelectDouyinBatchDir && douyinBatchOutputDir) {
        btnSelectDouyinBatchDir.addEventListener('click', async () => {
            const path = await selectDirectory('Chọn thư mục lưu video tải hàng loạt');
            if (path) {
                douyinBatchOutputDir.value = path;
                if (downloadOutputDir) downloadOutputDir.value = path;
                localStorage.setItem('download_output_dir', path);
                showToast('Đã chọn thư mục lưu: ' + path, 'info');
            }
        });
    }

    if (btnClearDouyinBatchDir && douyinBatchOutputDir) {
        btnClearDouyinBatchDir.addEventListener('click', () => {
            douyinBatchOutputDir.value = '';
            if (downloadOutputDir) downloadOutputDir.value = '';
            localStorage.removeItem('download_output_dir');
            showToast('Đã đặt lại thư mục lưu về mặc định (/downloads)', 'info');
        });
    }

    const douyinVideoSearchInput = document.getElementById('douyinVideoSearchInput');
    const douyinFilterSelect = document.getElementById('douyinFilterSelect');
    const douyinSortSelect = document.getElementById('douyinSortSelect');

    const douyinBatchProgressBox = document.getElementById('douyinBatchProgressBox');
    const douyinBatchProgressText = document.getElementById('douyinBatchProgressText');
    const douyinBatchProgressPct = document.getElementById('douyinBatchProgressPct');
    const douyinBatchProgressBar = document.getElementById('douyinBatchProgressBar');

    const douyinChannelGridContainer = document.getElementById('douyinChannelGridContainer');
    const douyinChannelGrid = document.getElementById('douyinChannelGrid');
    const douyinChannelEmptyPlaceholder = document.getElementById('douyinChannelEmptyPlaceholder');

    let currentScannedChannelInfo = {};
    let isDouyinBatchDownloading = false;

    // 1. Sub-tab toggle (Glassmorphic Segmented Pill Switcher)
    if (tabDownloadSingle && tabDownloadChannel && sectionDownloadSingle && sectionDownloadChannel) {
        tabDownloadSingle.addEventListener('click', () => {
            tabDownloadSingle.classList.add('active');
            tabDownloadChannel.classList.remove('active');

            sectionDownloadSingle.style.display = 'block';
            sectionDownloadChannel.style.display = 'none';
        });

        tabDownloadChannel.addEventListener('click', () => {
            tabDownloadChannel.classList.add('active');
            tabDownloadSingle.classList.remove('active');

            sectionDownloadSingle.style.display = 'none';
            sectionDownloadChannel.style.display = 'block';
        });
    }

    // 2. Paste Channel URL
    if (btnPasteChannelUrl && douyinChannelInputUrl) {
        btnPasteChannelUrl.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                douyinChannelInputUrl.value = text.trim();
                showToast('Đã dán liên kết kênh!', 'info');
            } catch (e) {
                showToast('Không thể đọc clipboard: ' + e.message, 'warning');
            }
        });
    }

    // 2.1. Open Douyin Login Window
    const btnDouyinOpenLogin = document.getElementById('btnDouyinOpenLogin');
    if (btnDouyinOpenLogin) {
        btnDouyinOpenLogin.addEventListener('click', async () => {
            try {
                btnDouyinOpenLogin.disabled = true;
                btnDouyinOpenLogin.innerHTML = `<span>⏳ Đang mở...</span>`;
                const res = await fetch('/api/download/douyin/open_login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                if (data.success) {
                    showToast('🌐 Cửa sổ trình duyệt đang mở. Vui lòng quét mã QR / đăng nhập Douyin (chỉ cần làm 1 lần duy nhất)!', 'success');
                } else {
                    showToast('Lỗi: ' + (data.error || ''), 'error');
                }
            } catch (e) {
                showToast('Lỗi kết nối: ' + e.message, 'error');
            } finally {
                setTimeout(() => {
                    btnDouyinOpenLogin.disabled = false;
                    btnDouyinOpenLogin.innerHTML = `🔑 Đăng Nhập Douyin`;
                }, 3000);
            }
        });
    }

    // 3. Scan Channel Videos
    if (btnScanDouyinChannel && douyinChannelInputUrl) {
        btnScanDouyinChannel.addEventListener('click', async () => {
            const channelUrl = douyinChannelInputUrl.value.trim();
            if (!channelUrl) {
                showToast('Vui lòng dán link kênh hoặc mã sec_uid của Douyin!', 'warning');
                return;
            }

            if (typeof checkFeaturePermission === 'function') {
                const allowed = await checkFeaturePermission('can_access_editor', 'Tải Video Hàng Loạt');
                if (!allowed) return;
            }

            const limit = parseInt(douyinChannelLimitSelect?.value || '30', 10);

            btnScanDouyinChannel.disabled = true;
            btnScanDouyinChannel.innerHTML = `<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Đang phân tích...`;

            if (douyinChannelEmptyPlaceholder) {
                douyinChannelEmptyPlaceholder.style.display = 'block';
                douyinChannelEmptyPlaceholder.innerHTML = `
                    <div style="padding: 24px; max-width: 520px; margin: 0 auto; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.35);">
                        <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(56, 189, 248, 0.2)); border: 1px solid rgba(168, 85, 247, 0.4); display: flex; align-items: center; justify-content: center;">
                                <span class="loading-spinner" style="width:24px;height:24px;border-width:2.5px;"></span>
                            </div>
                        </div>
                        <div id="douyinScanStatusTitle" style="font-size: 15px; font-weight: 600; color: #f8fafc; margin-bottom: 6px;">Đang kết nối & phân tích thông tin kênh...</div>
                        <div id="douyinScanStatusDesc" style="font-size: 12.5px; color: #94a3b8; margin-bottom: 16px;">Hệ thống đang nạp dữ liệu danh sách video theo thời gian thực...</div>
                        
                        <div style="background: rgba(30, 41, 59, 0.8); border-radius: 9999px; height: 8px; overflow: hidden; position: relative; margin-bottom: 10px;">
                            <div id="douyinScanProgressBar" style="width: 8%; height: 100%; background: linear-gradient(90deg, #a855f7, #38bdf8); border-radius: 9999px; transition: width 0.35s ease;"></div>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 11.5px; color: #64748b;">
                            <span id="douyinScanFoundCount">Đã tìm thấy: 0 video</span>
                            <span id="douyinScanPercent">8%</span>
                        </div>
                    </div>
                `;
            }

            const updateScanUI = (pct, msg) => {
                const titleEl = document.getElementById('douyinScanStatusTitle');
                const barEl = document.getElementById('douyinScanProgressBar');
                const pctEl = document.getElementById('douyinScanPercent');
                const countEl = document.getElementById('douyinScanFoundCount');

                if (titleEl && msg) titleEl.textContent = msg;
                if (barEl && pct !== undefined) barEl.style.width = `${Math.min(100, Math.max(5, pct))}%`;
                if (pctEl && pct !== undefined) pctEl.textContent = `${pct}%`;
                
                if (countEl && msg) {
                    const match = msg.match(/(\d+)\s+video/i);
                    if (match) {
                        countEl.textContent = `Đã tìm thấy: ${match[1]} video`;
                    }
                }
            };

            try {
                const sourceType = document.getElementById('douyinSourceTypeSelect')?.value || 'channel';
                const res = await fetch('/api/download/douyin/scan_channel_stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channel_url: channelUrl, limit, source_type: sourceType })
                });

                if (!res.ok) {
                    let errMsg = `Lỗi phản hồi từ máy chủ (Mã: ${res.status})`;
                    try {
                        const errData = await res.json();
                        if (errData.error) errMsg = errData.error;
                    } catch (_) {}
                    throw new Error(errMsg);
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';
                let finalData = null;

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith('data:')) continue;

                        const jsonStr = trimmed.replace(/^data:\s*/, '');
                        try {
                            const eventData = JSON.parse(jsonStr);
                            if (eventData.status === 'progress') {
                                updateScanUI(eventData.pct, eventData.msg);
                            } else if (eventData.status === 'completed') {
                                finalData = eventData.result;
                                updateScanUI(100, 'Đã phân tích hoàn tất toàn bộ danh sách!');
                            } else if (eventData.status === 'error') {
                                throw new Error(eventData.error || 'Quá trình phân tích kênh bị gián đoạn.');
                            }
                        } catch (parseErr) {
                            if (jsonStr.includes('"error"')) {
                                throw parseErr;
                            }
                        }
                    }
                }

                if (!finalData || !finalData.videos) {
                    throw new Error('Không nhận được dữ liệu danh sách video từ kênh.');
                }

                scannedDouyinVideos = finalData.videos || [];
                selectedDouyinVideoIds = new Set(scannedDouyinVideos.map(v => v.aweme_id));

                // Render Channel Info Banner
                const info = finalData.channel_info || {};
                currentScannedChannelInfo = info;
                if (douyinChannelInfoBanner) douyinChannelInfoBanner.style.display = 'block';
                if (douyinChannelAvatar) douyinChannelAvatar.src = info.avatar || '';
                if (douyinChannelNickname) douyinChannelNickname.textContent = info.nickname || 'Kênh Douyin';
                if (douyinChannelSignature) douyinChannelSignature.textContent = info.signature || 'Không có mô tả';
                
                const fmtNum = (num) => {
                    if (!num) return '0';
                    if (num >= 10000000) return (num / 10000000).toFixed(1) + '千万';
                    if (num >= 10000) return (num / 10000).toFixed(1) + 'w';
                    if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
                    return num.toLocaleString();
                };

                if (douyinChannelFollowersBadge) douyinChannelFollowersBadge.textContent = fmtNum(info.follower_count || 0);
                if (douyinChannelLikesBadge) douyinChannelLikesBadge.textContent = fmtNum(info.total_favorited || 0);
                if (douyinChannelVideoCountBadge) douyinChannelVideoCountBadge.textContent = `${scannedDouyinVideos.length} Video`;

                // Render Video Grid
                renderDouyinVideoGrid();

                showToast(`Đã phân tích thành công ${scannedDouyinVideos.length} video từ kênh ${info.nickname || ''}!`, 'success');
            } catch (e) {
                showToast('Lỗi khi phân tích kênh: ' + e.message, 'error');
                if (douyinChannelEmptyPlaceholder) {
                    douyinChannelEmptyPlaceholder.innerHTML = `
                        <div style="font-size: 15px; font-weight: 600; color: #f87171;">❌ Phân tích kênh không thành công</div>
                        <div style="font-size: 12.5px; color: #94a3b8; margin-top: 6px;">${e.message}</div>
                    `;
                }
            } finally {
                btnScanDouyinChannel.disabled = false;
                btnScanDouyinChannel.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg><span>Quét Danh Sách Video</span>`;
            }
        });
    }

    // 4. Filter & Sort Helper
    function getFilteredAndSortedDouyinVideos() {
        if (!scannedDouyinVideos || scannedDouyinVideos.length === 0) return [];
        let list = [...scannedDouyinVideos];

        // Search query
        const query = (douyinVideoSearchInput?.value || '').trim().toLowerCase();
        if (query) {
            list = list.filter(v => (v.title || '').toLowerCase().includes(query));
        }

        // Filter
        const filterVal = douyinFilterSelect?.value || 'all';
        if (filterVal === 'video_only') {
            list = list.filter(v => !v.is_images);
        } else if (filterVal === 'images_only') {
            list = list.filter(v => v.is_images);
        } else if (filterVal === 'likes_10k') {
            list = list.filter(v => (v.digg_count || 0) >= 10000);
        } else if (filterVal === 'likes_100k') {
            list = list.filter(v => (v.digg_count || 0) >= 100000);
        } else if (filterVal === 'dur_60s') {
            list = list.filter(v => (v.duration || 0) >= 60);
        }

        // Sort
        const sortVal = douyinSortSelect?.value || 'original';
        if (sortVal === 'likes_desc') {
            list.sort((a, b) => (b.digg_count || 0) - (a.digg_count || 0));
        } else if (sortVal === 'comments_desc') {
            list.sort((a, b) => (b.comment_count || 0) - (a.comment_count || 0));
        } else if (sortVal === 'dur_desc') {
            list.sort((a, b) => (b.duration || 0) - (a.duration || 0));
        } else if (sortVal === 'dur_asc') {
            list.sort((a, b) => (a.duration || 0) - (b.duration || 0));
        }

        return list;
    }

    // 5. Render Video Grid Function
    function renderDouyinVideoGrid() {
        if (!douyinChannelGrid) return;
        douyinChannelGrid.innerHTML = '';

        const displayVideos = getFilteredAndSortedDouyinVideos();

        if (scannedDouyinVideos.length === 0) {
            if (douyinChannelGridContainer) douyinChannelGridContainer.style.display = 'none';
            if (douyinBatchActionsBar) douyinBatchActionsBar.style.display = 'none';
            if (douyinChannelEmptyPlaceholder) douyinChannelEmptyPlaceholder.style.display = 'block';
            return;
        }

        if (douyinChannelEmptyPlaceholder) douyinChannelEmptyPlaceholder.style.display = 'none';
        if (douyinChannelGridContainer) douyinChannelGridContainer.style.display = 'block';
        if (douyinBatchActionsBar) douyinBatchActionsBar.style.display = 'block';

        updateSelectionSummary();

        if (displayVideos.length === 0) {
            douyinChannelGrid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 40px 20px; color: #94a3b8; font-size: 13px; background: #1e293b; border-radius: 10px; border: 1px dashed #334155;">
                    🔍 Không tìm thấy video nào phù hợp với bộ lọc hoặc từ khóa tìm kiếm.
                </div>
            `;
            return;
        }

        displayVideos.forEach((video, idx) => {
            const isSelected = selectedDouyinVideoIds.has(video.aweme_id);
            const card = document.createElement('div');
            card.className = `douyin-reel-card ${isSelected ? 'selected' : ''}`;

            const thumb = safeHttpUrl(video.cover_url);
            const videoId = escapeHtml(video.aweme_id);
            const videoTitle = video.title || 'Video Douyin';
            const sourceUrl = safeHttpUrl(video.url);
            const diggCount = Number.isFinite(Number(video.digg_count)) ? Number(video.digg_count) : 0;
            const commentCount = Number.isFinite(Number(video.comment_count)) ? Number(video.comment_count) : 0;
            const isViral = diggCount >= 100000;
            const viralBadge = isViral 
                ? `<span style="background: linear-gradient(135deg, #ef4444, #f59e0b); color: #fff; font-size: 9.5px; font-weight: 800; padding: 2px 6px; border-radius: 4px; box-shadow: 0 2px 6px rgba(239, 68, 68, 0.4); display: flex; align-items: center; gap: 2px;">🔥 Viral</span>`
                : '';

            const typeBadge = video.is_images 
                ? `<span style="background: linear-gradient(135deg, #a855f7, #ec4899); color: #fff; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; box-shadow: 0 2px 6px rgba(168,85,247,0.4);">🖼️ ${(video.image_urls || []).length} Ảnh</span>`
                : `<span style="background: rgba(15, 23, 42, 0.85); color: #38bdf8; font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.35); backdrop-filter: blur(4px);">⏱️ ${escapeHtml(video.duration_formatted || '00:00')}</span>`;

            card.innerHTML = `
                <div class="douyin-reel-thumb-box">
                    ${thumb ? `<img src="${escapeHtml(thumb)}" alt="thumb" loading="lazy" onerror="this.style.display='none'">` : ''}
                    <div class="douyin-reel-overlay">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 6px;">
                            <label style="background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(8px); padding: 3px 8px; border-radius: 6px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; border: 1px solid rgba(51, 65, 85, 0.8);" onclick="event.stopPropagation();">
                                <input type="checkbox" class="douyin-item-checkbox" data-id="${videoId}" ${isSelected ? 'checked' : ''} style="width: 15px; height: 15px; accent-color: #38bdf8; cursor: pointer;">
                                <span style="font-size: 11px; font-weight: 800; color: #38bdf8;">#${idx + 1}</span>
                            </label>
                            ${viralBadge}
                        </div>
                        <div style="display: flex; justify-content: flex-end;">
                            ${typeBadge}
                        </div>
                    </div>
                </div>
                <div class="douyin-reel-info">
                    <div class="douyin-reel-title" title="${escapeHtml(videoTitle)}">
                        ${escapeHtml(videoTitle)}
                    </div>
                    <div class="douyin-reel-meta">
                        <span style="display: flex; align-items: center; gap: 4px; color: #f43f5e; font-weight: 600;">
                            ❤️ ${diggCount.toLocaleString()}
                        </span>
                        <span style="display: flex; align-items: center; gap: 4px;">
                            💬 ${commentCount.toLocaleString()}
                        </span>
                        ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" style="color: #38bdf8; text-decoration: none; font-weight: 700; font-size: 11px; display: inline-flex; align-items: center; gap: 2px;" onclick="event.stopPropagation();">
                            Xem ↗
                        </a>` : ''}
                    </div>
                </div>
            `;

            // Click entire card to toggle checkbox
            card.addEventListener('click', (e) => {
                const chk = card.querySelector('.douyin-item-checkbox');
                if (chk) {
                    chk.checked = !chk.checked;
                    if (chk.checked) {
                        selectedDouyinVideoIds.add(video.aweme_id);
                        card.classList.add('selected');
                    } else {
                        selectedDouyinVideoIds.delete(video.aweme_id);
                        card.classList.remove('selected');
                    }
                    updateSelectionSummary();
                }
            });

            // Direct checkbox change
            const chk = card.querySelector('.douyin-item-checkbox');
            chk?.addEventListener('change', (e) => {
                e.stopPropagation();
                const checked = e.target.checked;
                if (checked) {
                    selectedDouyinVideoIds.add(video.aweme_id);
                    card.classList.add('selected');
                } else {
                    selectedDouyinVideoIds.delete(video.aweme_id);
                    card.classList.remove('selected');
                }
                updateSelectionSummary();
            });

            douyinChannelGrid.appendChild(card);
        });
    }

    // Search, Filter & Sort Event Listeners
    if (douyinVideoSearchInput) {
        douyinVideoSearchInput.addEventListener('input', () => {
            renderDouyinVideoGrid();
        });
    }
    if (douyinFilterSelect) {
        douyinFilterSelect.addEventListener('change', () => {
            renderDouyinVideoGrid();
        });
    }
    if (douyinSortSelect) {
        douyinSortSelect.addEventListener('change', () => {
            renderDouyinVideoGrid();
        });
    }

    function updateSelectionSummary() {
        const total = scannedDouyinVideos.length;
        const selected = selectedDouyinVideoIds.size;
        if (douyinSelectedSummary) {
            douyinSelectedSummary.textContent = `Đã chọn: ${selected} / ${total} video`;
        }
        if (douyinSelectAllCheckbox) {
            douyinSelectAllCheckbox.checked = (selected === total && total > 0);
            douyinSelectAllCheckbox.indeterminate = (selected > 0 && selected < total);
        }
    }

    // 6. Select All Checkbox
    if (douyinSelectAllCheckbox) {
        douyinSelectAllCheckbox.addEventListener('change', (e) => {
            const checked = e.target.checked;
            const currentFiltered = getFilteredAndSortedDouyinVideos();
            if (checked) {
                currentFiltered.forEach(v => selectedDouyinVideoIds.add(v.aweme_id));
            } else {
                currentFiltered.forEach(v => selectedDouyinVideoIds.delete(v.aweme_id));
            }
            renderDouyinVideoGrid();
        });
    }

    // 7. Open Folder
    if (btnDouyinOpenFolder) {
        btnDouyinOpenFolder.addEventListener('click', () => {
            const customDir = douyinBatchOutputDir?.value.trim() || '';
            const channelName = douyinSubfolderCheckbox?.checked ? (currentScannedChannelInfo?.nickname || '') : '';
            let folderPath = customDir;
            if (channelName && customDir) {
                folderPath = `${customDir}/Douyin_${channelName}`;
            }
            fetch('/api/download/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: folderPath })
            });
        });
    }

    // 8. Stop Batch Download
    if (btnStopDouyinBatchDownload) {
        btnStopDouyinBatchDownload.addEventListener('click', async () => {
            try {
                btnStopDouyinBatchDownload.disabled = true;
                btnStopDouyinBatchDownload.textContent = '⏳ Đang dừng...';
                await fetch('/api/download/douyin/cancel_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                showToast('🛑 Đã gửi lệnh dừng tiến trình tải!', 'info');
            } catch (e) {
                showToast('Lỗi dừng tải: ' + e.message, 'error');
            }
        });
    }

    // 9. Start Batch Download
    if (btnStartDouyinBatchDownload) {
        btnStartDouyinBatchDownload.addEventListener('click', async () => {
            const selectedList = scannedDouyinVideos.filter(v => selectedDouyinVideoIds.has(v.aweme_id));
            if (selectedList.length === 0) {
                showToast('Vui lòng tích chọn ít nhất 1 video để tải!', 'warning');
                return;
            }

            isDouyinBatchDownloading = true;
            btnStartDouyinBatchDownload.disabled = true;
            btnStartDouyinBatchDownload.innerHTML = `<span>⏳ Đang tải hàng loạt...</span>`;
            if (btnStopDouyinBatchDownload) {
                btnStopDouyinBatchDownload.style.display = 'inline-flex';
                btnStopDouyinBatchDownload.disabled = false;
                btnStopDouyinBatchDownload.textContent = '🛑 DỪNG TẢI';
            }
            if (douyinBatchProgressBox) douyinBatchProgressBox.style.display = 'block';
            if (douyinBatchProgressBar) douyinBatchProgressBar.style.width = '0%';
            if (douyinBatchProgressText) douyinBatchProgressText.textContent = `Bắt đầu tải ${selectedList.length} video...`;
            if (douyinBatchProgressPct) douyinBatchProgressPct.textContent = '0%';

            const channelName = douyinSubfolderCheckbox?.checked ? (currentScannedChannelInfo?.nickname || '') : '';
            const customOutputDir = douyinBatchOutputDir?.value.trim() || '';

            const maxWorkers = parseInt(document.getElementById('douyinWorkersSelect')?.value || '3', 10);
            const connPerFile = parseInt(document.getElementById('douyinConnectionsSelect')?.value || '2', 10);
            const prefixIndex = document.getElementById('douyinPrefixIndexCheckbox')?.checked ?? true;
            const autoMerge = document.getElementById('douyinAutoMergeCheckbox')?.checked ?? false;

            try {
                const response = await fetch('/api/download/douyin/batch_download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        videos: selectedList,
                        output_dir: customOutputDir,
                        channel_name: channelName,
                        max_workers: maxWorkers,
                        connections_per_file: connPerFile,
                        prefix_index: prefixIndex,
                        auto_merge: autoMerge
                    })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonStr = line.slice(6).trim();
                            if (!jsonStr) continue;
                            try {
                                const data = JSON.parse(jsonStr);
                                if (data.status === 'progress') {
                                    if (douyinBatchProgressBar) douyinBatchProgressBar.style.width = `${data.pct}%`;
                                    if (douyinBatchProgressPct) douyinBatchProgressPct.textContent = `${data.pct}%`;
                                    if (douyinBatchProgressText) {
                                        douyinBatchProgressText.textContent = `Đang tải (${data.completed}/${data.total}): ${data.current_title || ''}`;
                                    }
                                } else if (data.status === 'completed') {
                                    if (douyinBatchProgressBar) douyinBatchProgressBar.style.width = '100%';
                                    if (douyinBatchProgressPct) douyinBatchProgressPct.textContent = '100%';
                                    if (douyinBatchProgressText) {
                                        douyinBatchProgressText.textContent = `✅ Đã tải xong toàn bộ ${data.downloaded_count} / ${data.total_requested} video!`;
                                    }

                                    // Add to download history
                                    (data.files || []).forEach(fPath => {
                                        saveDownloadHistoryItem({
                                            id: Date.now() + Math.random(),
                                            title: fPath.split(/[\\/]/).pop(),
                                            file_path: fPath,
                                            file_name: fPath.split(/[\\/]/).pop(),
                                            file_size: '--',
                                            thumbnail: '',
                                            platform: 'Douyin Channel',
                                            is_audio: false,
                                            timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
                                        });
                                    });

                                    showToast(`Đã tải thành công ${data.downloaded_count} video về máy!`, 'success');
                                    if (data.merged_file) {
                                        showToast(`🎬 Đã tự động gộp các tập thành video: ${data.merged_file.split(/[\\/]/).pop()}`, 'success');
                                    }
                                } else if (data.status === 'error') {
                                    showToast('Lỗi tải hàng loạt: ' + (data.error || ''), 'error');
                                }
                            } catch (err) {
                                console.error('SSE parse error:', err);
                            }
                        }
                    }
                }
            } catch (e) {
                showToast('Lỗi kết nối khi tải hàng loạt: ' + e.message, 'error');
            } finally {
                isDouyinBatchDownloading = false;
                btnStartDouyinBatchDownload.disabled = false;
                btnStartDouyinBatchDownload.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg><span>TẢI CÁC VIDEO ĐÃ CHỌN</span>`;
                if (btnStopDouyinBatchDownload) {
                    btnStopDouyinBatchDownload.style.display = 'none';
                    btnStopDouyinBatchDownload.disabled = false;
                }
            }
        });
    }

    // 10. Retry Failed Batch Items
    const btnDouyinRetryFailed = document.getElementById('btnDouyinRetryFailed');
    if (btnDouyinRetryFailed) {
        btnDouyinRetryFailed.addEventListener('click', async () => {
            const customDir = douyinBatchOutputDir?.value.trim() || '';
            const channelName = douyinSubfolderCheckbox?.checked ? (currentScannedChannelInfo?.nickname || '') : '';
            let folderPath = customDir;
            if (channelName && customDir) {
                folderPath = `${customDir}/Douyin_${channelName}`;
            }

            if (!folderPath) {
                showToast('Vui lòng chọn thư mục chứa batch_manifest.json hoặc đã tải video trước đó!', 'warning');
                return;
            }

            btnDouyinRetryFailed.disabled = true;
            btnDouyinRetryFailed.textContent = '⏳ Đang kiểm tra...';

            if (douyinBatchProgressBox) douyinBatchProgressBox.style.display = 'block';
            if (douyinBatchProgressText) douyinBatchProgressText.textContent = 'Đang quét và tải lại các video bị lỗi...';

            try {
                const res = await fetch('/api/download/douyin/retry_failed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ output_dir: folderPath })
                });

                const reader = res.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonStr = line.slice(6).trim();
                            if (!jsonStr) continue;
                            try {
                                const data = JSON.parse(jsonStr);
                                if (data.status === 'progress') {
                                    if (douyinBatchProgressBar) douyinBatchProgressBar.style.width = `${data.pct}%`;
                                    if (douyinBatchProgressPct) douyinBatchProgressPct.textContent = `${data.pct}%`;
                                    if (douyinBatchProgressText) {
                                        douyinBatchProgressText.textContent = `Tải lại (${data.completed}/${data.total}): ${data.current_title || ''}`;
                                    }
                                } else if (data.status === 'completed') {
                                    showToast('Hoàn tất kiểm tra tải lại các mục lỗi!', 'success');
                                    if (douyinBatchProgressText) douyinBatchProgressText.textContent = '✅ Đã hoàn tất tải lại!';
                                } else if (data.status === 'error') {
                                    showToast('Lỗi tải lại: ' + (data.error || ''), 'error');
                                }
                            } catch (_) {}
                        }
                    }
                }
            } catch (err) {
                showToast('Lỗi kết nối retry: ' + err.message, 'error');
            } finally {
                btnDouyinRetryFailed.disabled = false;
                btnDouyinRetryFailed.textContent = '🔄 Tải lại video lỗi';
            }
        });
    }

    // 11. Manual Merge Episodes
    const btnDouyinManualMerge = document.getElementById('btnDouyinManualMerge');
    if (btnDouyinManualMerge) {
        btnDouyinManualMerge.addEventListener('click', async () => {
            const customDir = douyinBatchOutputDir?.value.trim() || '';
            const channelName = douyinSubfolderCheckbox?.checked ? (currentScannedChannelInfo?.nickname || '') : '';
            let folderPath = customDir;
            if (channelName && customDir) {
                folderPath = `${customDir}/Douyin_${channelName}`;
            }

            if (!folderPath) {
                showToast('Vui lòng chọn thư mục chứa các tập video cần ghép!', 'warning');
                return;
            }

            btnDouyinManualMerge.disabled = true;
            btnDouyinManualMerge.textContent = '⏳ Đang ghép nối...';
            showToast('Đang ghép nối các tập video trong thư mục...', 'info');

            try {
                const res = await fetch('/api/download/douyin/merge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ output_dir: folderPath, merge_mode: 'auto' })
                });
                const data = await res.json();
                if (data.success && data.merged_file) {
                    showToast(`🎬 Đã ghép thành công video: ${data.merged_file.split(/[\\/]/).pop()}!`, 'success');
                } else {
                    showToast('Lỗi ghép video: ' + (data.error || 'Thất bại'), 'error');
                }
            } catch (err) {
                showToast('Lỗi kết nối: ' + err.message, 'error');
            } finally {
                btnDouyinManualMerge.disabled = false;
                btnDouyinManualMerge.textContent = '🎬 Ghép tập video';
            }
        });
    }
}

try {
    initDouyinChannelDownloader();
} catch (e) {
    console.error("Error initializing Douyin Channel Downloader:", e);
}

// Initialize Clone Voice Studio
try {
    initCloneVoiceModule();
} catch (e) {
    console.error("Error initializing Clone Voice Module:", e);
}

// ==========================================
// REVIEW TAB DYNAMIC BLUR & AI SCAN CONTROLLERS
// ==========================================
const reviewTabDynamicBlurHeader = document.getElementById('reviewTabDynamicBlurHeader');
const reviewTabDynamicBlurSubConfig = document.getElementById('reviewTabDynamicBlurSubConfig');
const reviewTabDynamicBlurChevron = document.getElementById('reviewTabDynamicBlurChevron');
const reviewTabBlurCheckbox = document.getElementById('reviewTabBlurOriginalSubtitles');
const reviewTabDynamicBlurToggleLabel = document.getElementById('reviewTabDynamicBlurToggleLabel');

function updateReviewTabDynamicBlurUIState(notify = false) {
    if (!reviewTabBlurCheckbox) return;
    const isChecked = reviewTabBlurCheckbox.checked;
    if (reviewTabDynamicBlurToggleLabel) {
        reviewTabDynamicBlurToggleLabel.textContent = isChecked ? 'Bật' : 'Tắt';
        reviewTabDynamicBlurToggleLabel.style.color = isChecked ? '#38bdf8' : '#94a3b8';
    }
    if (reviewTabDynamicBlurSubConfig) {
        reviewTabDynamicBlurSubConfig.style.display = isChecked ? 'flex' : 'none';
    }
    if (reviewTabDynamicBlurChevron) {
        reviewTabDynamicBlurChevron.style.transform = isChecked ? 'rotate(0deg)' : 'rotate(-90deg)';
    }
    if (window.triggerReviewDynamicBlurSync) {
        window.triggerReviewDynamicBlurSync();
    }
    if (notify) {
        showToast(isChecked ? '✨ Đã BẬT làm mờ phụ đề gốc (Review Phim).' : '🚫 Đã TẮT làm mờ phụ đề gốc (Review Phim).', isChecked ? 'info' : 'warning');
    }
}

if (reviewTabDynamicBlurHeader) {
    reviewTabDynamicBlurHeader.addEventListener('click', (e) => {
        if (e.target.id === 'reviewTabBlurOriginalSubtitles' || e.target.closest('.switch')) return;
        if (reviewTabBlurCheckbox) {
            reviewTabBlurCheckbox.checked = !reviewTabBlurCheckbox.checked;
            updateReviewTabDynamicBlurUIState(true);
        }
    });
}

if (reviewTabBlurCheckbox) {
    reviewTabBlurCheckbox.addEventListener('change', () => {
        updateReviewTabDynamicBlurUIState(true);
    });
}

// Sliders listeners in Review Tab
['reviewTabDynBlurIntensity', 'reviewTabBlurLeadOffset', 'reviewTabBlurPadding', 'reviewTabBlurYPos'].forEach(id => {
    const el = document.getElementById(id);
    const valEl = document.getElementById(id + 'Val');
    if (el && valEl) {
        el.addEventListener('input', (e) => {
            const unit = id.includes('Offset') || id.includes('Padding') ? 'ms' : (id.includes('Intensity') ? 'px' : '%');
            valEl.textContent = `${e.target.value}${unit}`;
            if (window.triggerReviewDynamicBlurSync) {
                window.triggerReviewDynamicBlurSync();
            }
        });
    }
});

// Review Tab AI Scan logic
window.reviewTabScannedAiBoxes = [];
let reviewAiScanAbortController = null;

function updateReviewTabAiScanBadge(total, detected) {
    const badge = document.getElementById('reviewTabAiScanBadge');
    const resetBtn = document.getElementById('btnReviewTabResetAiBoxes');
    if (!badge) return;
    
    if (total === 0) {
        badge.textContent = '0 câu đã quét AI';
        badge.style.background = 'rgba(56, 189, 248, 0.12)';
        badge.style.color = '#38bdf8';
        badge.style.borderColor = 'rgba(56, 189, 248, 0.25)';
        if (resetBtn) resetBtn.style.display = 'none';
        return;
    }
    
    const count = detected !== undefined ? detected : window.reviewTabScannedAiBoxes.filter(Boolean).length;
    badge.textContent = `${count}/${total} câu đã quét AI`;
    if (count > 0) {
        badge.style.background = 'rgba(16, 185, 129, 0.18)';
        badge.style.color = '#34d399';
        badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
        if (resetBtn) resetBtn.style.display = 'inline-block';
    } else {
        badge.style.background = 'rgba(56, 189, 248, 0.12)';
        badge.style.color = '#38bdf8';
        badge.style.borderColor = 'rgba(56, 189, 248, 0.25)';
        if (resetBtn) resetBtn.style.display = 'none';
    }
}

async function scanReviewAiAllSubtitles() {
    const videoPath = reviewInputVideoPath?.value?.trim() || '';
    if (!videoPath) {
        showToast("Vui lòng chọn Video phim đầu vào trước khi quét!", "warning");
        return;
    }
    
    const srtPath = reviewInputSrtPath?.value?.trim() || '';
    if (!srtPath && (typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0)) {
        showToast("Vui lòng chọn file phụ đề .srt của phim để AI quét tọa độ!", "warning");
        return;
    }

    const btnAll = document.getElementById('btnReviewTabScanAiAllSubs');
    const btnCur = document.getElementById('btnReviewTabScanAiCurrentFrame');
    const progWrap = document.getElementById('reviewTabAiScanProgressWrapper');
    const progBar = document.getElementById('reviewTabAiScanProgressBar');
    const progText = document.getElementById('reviewTabAiScanPercentText');
    const statusText = document.getElementById('reviewTabAiScanStatusText');

    if (reviewAiScanAbortController) {
        reviewAiScanAbortController.abort();
        reviewAiScanAbortController = null;
        if (btnAll) {
            btnAll.classList.remove('btn-danger');
            btnAll.classList.add('primary-cyan');
            btnAll.innerHTML = `<span>🎯 Quét Toàn Bộ Sub</span>`;
        }
        if (btnCur) btnCur.disabled = false;
        if (progWrap) progWrap.style.display = 'none';
        showToast("Đã dừng quét AI Review Phim.", "warning");
        return;
    }

    // Lấy danh sách sub từ srt file hoặc srtData
    let subEntries = [];
    if (srtPath) {
        try {
            const resSrt = await fetch('/api/subtitles/parse_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ srt_path: srtPath })
            });
            if (resSrt.ok) {
                const srtJson = await resSrt.json();
                subEntries = srtJson.subtitles || [];
            }
        } catch (e) {
            console.warn("Could not parse srt file via API:", e);
        }
    }
    
    if (subEntries.length === 0 && window.reviewParsedSubtitles && Array.isArray(window.reviewParsedSubtitles) && window.reviewParsedSubtitles.length > 0) {
        subEntries = window.reviewParsedSubtitles;
    }
    
    if (subEntries.length === 0 && typeof srtData !== 'undefined' && Array.isArray(srtData) && srtData.length > 0) {
        subEntries = srtData.map((s, idx) => ({
            id: s.id || (idx + 1),
            startSeconds: s.startSeconds,
            endSeconds: s.endSeconds,
            text: s.text || s.original_text || ''
        }));
    }

    if (subEntries.length === 0) {
        showToast("Không đọc được phụ đề để quét. Hãy kiểm tra file .srt!", "warning");
        return;
    }

    reviewAiScanAbortController = new AbortController();

    if (btnAll) {
        btnAll.classList.remove('primary-cyan');
        btnAll.classList.add('btn-danger');
        btnAll.innerHTML = `<span>🛑 Dừng Quét</span>`;
    }
    if (btnCur) btnCur.disabled = true;
    if (progWrap) progWrap.style.display = 'flex';
    if (progBar) progBar.style.width = '0%';
    if (progText) progText.textContent = '0%';
    if (statusText) statusText.textContent = `Đang chuẩn bị quét GPU cho ${subEntries.length} câu...`;

    const sliderY = parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || 81.5;
    const region = { x: 20, y: sliderY, w: 60, h: 9.5 };

    window.reviewTabScannedAiBoxes = [];

    try {
        const res = await fetch('/api/ocr/scan_preview_boxes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: videoPath,
                region: region,
                subtitles: subEntries
            }),
            signal: reviewAiScanAbortController.signal
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (let line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.substring(6));
                        if (event.type === 'progress') {
                            if (event.box) {
                                window.reviewTabScannedAiBoxes[event.index] = event.box;
                            }
                            if (progBar) progBar.style.width = `${event.pct}%`;
                            if (progText) progText.textContent = `${event.pct}%`;
                            if (statusText) statusText.textContent = `Đang quét GPU: ${event.index + 1}/${event.total} câu...`;
                            updateReviewTabAiScanBadge(event.total, window.reviewTabScannedAiBoxes.filter(Boolean).length);
                        } else if (event.type === 'done') {
                            if (progBar) progBar.style.width = '100%';
                            if (progText) progText.textContent = '100%';
                            if (statusText) statusText.textContent = `Hoàn thành (${event.detected_count}/${event.total_scanned} câu)!`;
                            
                            const chkAi = document.getElementById('reviewTabBlurUseAiScan');
                            if (chkAi) chkAi.checked = true;
                            
                            updateReviewTabAiScanBadge(event.total_scanned, event.detected_count);
                            showToast(`🎉 Review Phim: Đã quét xong tọa độ AI cho ${event.detected_count}/${event.total_scanned} câu phụ đề!`, "success");
                            
                            setTimeout(() => {
                                if (progWrap) progWrap.style.display = 'none';
                            }, 2500);
                        } else if (event.type === 'error') {
                            showToast(`Lỗi quét AI: ${event.message}`, "error");
                        }
                    } catch (pe) {
                        console.error("Error parsing review scan SSE event:", pe);
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            showToast(`Lỗi kết nối quét AI: ${err.message}`, "error");
        }
    } finally {
        reviewAiScanAbortController = null;
        if (btnAll) {
            btnAll.classList.remove('btn-danger');
            btnAll.classList.add('primary-cyan');
            btnAll.innerHTML = `<span>🎯 Quét Toàn Bộ Sub</span>`;
        }
        if (btnCur) btnCur.disabled = false;
    }
}

async function scanReviewAiCurrentFrame() {
    const videoPath = reviewInputVideoPath?.value?.trim() || '';
    if (!videoPath) {
        showToast("Vui lòng chọn Video phim đầu vào trước khi quét!", "warning");
        return;
    }
    
    const currentTime = reviewVideoPlayer ? (reviewVideoPlayer.currentTime || 0) : 0;
    const sliderY = parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || 81.5;
    const region = { x: 20, y: sliderY, w: 60, h: 9.5 };
    const btn = document.getElementById('btnReviewTabScanAiCurrentFrame');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-spinner" style="display:inline-block; width:10px; height:10px; border:2px solid #38bdf8; border-top-color:transparent; border-radius:50%; animation:spin 0.6s linear infinite; margin-right:4px;"></span> Quét...`;
    }

    try {
        const res = await fetch('/api/ocr/scan_preview_single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: videoPath,
                timestamp: currentTime,
                region: region
            })
        });
        const data = await res.json();
        if (data.success && data.box) {
            window.reviewTabScannedAiBoxes[0] = data.box;
            const chkAi = document.getElementById('reviewTabBlurUseAiScan');
            if (chkAi) chkAi.checked = true;
            updateReviewTabAiScanBadge(1, 1);
            showToast(`🎯 Quét AI thành công! (X: ${data.box.x_pct}%, W: ${data.box.w_pct}%)`, "success");
        } else {
            showToast(data.message || data.error || "Không phát hiện chữ phụ đề ở frame này.", "info");
        }
    } catch (err) {
        showToast("Lỗi khi quét AI: " + err.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg> <span>Quét Frame Này</span>`;
        }
    }
}

function resetReviewTabAiBoxes() {
    window.reviewTabScannedAiBoxes = [];
    updateReviewTabAiScanBadge(0, 0);
    showToast("Review Phim: Đã xóa toàn bộ tọa độ AI đã quét.", "info");
}

document.getElementById('btnReviewTabScanAiAllSubs')?.addEventListener('click', scanReviewAiAllSubtitles);
document.getElementById('btnReviewTabScanAiCurrentFrame')?.addEventListener('click', scanReviewAiCurrentFrame);
document.getElementById('btnReviewTabResetAiBoxes')?.addEventListener('click', resetReviewTabAiBoxes);

// ==========================================
// 🏷️ INTERACTIVE LOGO / WATERMARK CONTROLLER (8-POINTS)
// ==========================================
let currentLogoState = {
    enabled: false,
    path: '',
    x_pct: 5.0,
    y_pct: 5.0,
    w_pct: 20.0,
    h_pct: 12.0,
    opacity: 100
};

function setupInteractiveVideoLogo() {
    const enableCheckbox = document.getElementById('enableLogoWatermark');
    const configPanel = document.getElementById('logoConfigPanel');
    const logoInput = document.getElementById('logoInputPath');
    const hiddenFileInput = document.getElementById('logoFileInputHidden');
    const btnSelect = document.getElementById('btnSelectLogoFile');
    const btnReset = document.getElementById('btnResetLogo');
    const opacitySlider = document.getElementById('logoOpacity');
    const opacityVal = document.getElementById('logoOpacityVal');
    const coordBadge = document.getElementById('logoCoordBadge');
    const presetBtns = document.querySelectorAll('.btn-logo-preset');
    
    const logoOverlay = document.getElementById('videoLogoOverlay');
    const logoImg = document.getElementById('videoLogoImg');
    const container = document.getElementById('videoContainer');

    function renderLogo() {
        const overlay = document.getElementById('videoLogoOverlay');
        const img = document.getElementById('videoLogoImg');
        const cont = document.getElementById('videoContainer') || document.getElementById('videoZoomWrapper');
        if (!overlay) return;

        if (!currentLogoState.enabled || !currentLogoState.path) {
            overlay.style.display = 'none';
            return;
        }

        const parentEl = overlay.offsetParent || cont || document.body;
        const cW = parentEl.clientWidth || 640;
        const cH = parentEl.clientHeight || 360;

        const leftPx = (currentLogoState.x_pct / 100) * cW;
        const topPx = (currentLogoState.y_pct / 100) * cH;
        const widthPx = (currentLogoState.w_pct / 100) * cW;
        const heightPx = (currentLogoState.h_pct / 100) * cH;

        overlay.style.display = 'block';
        overlay.style.left = `${leftPx}px`;
        overlay.style.top = `${topPx}px`;
        overlay.style.width = `${widthPx}px`;
        overlay.style.height = `${heightPx}px`;
        overlay.style.opacity = `${currentLogoState.opacity / 100}`;

        if (img) {
            if (currentLogoState.dataUrl) {
                if (img.src !== currentLogoState.dataUrl) img.src = currentLogoState.dataUrl;
            } else if (currentLogoState.path) {
                const imgSrc = `/api/image?path=${encodeURIComponent(currentLogoState.path)}`;
                if (!img.src.includes(encodeURIComponent(currentLogoState.path))) {
                    img.src = imgSrc;
                }
            }
        }

        if (coordBadge) {
            coordBadge.textContent = `(x: ${currentLogoState.x_pct.toFixed(1)}%, y: ${currentLogoState.y_pct.toFixed(1)}%, w: ${currentLogoState.w_pct.toFixed(1)}%)`;
        }
    }

    // Checkbox toggle
    if (enableCheckbox) {
        if (enableCheckbox.checked) {
            currentLogoState.enabled = true;
            if (configPanel) configPanel.style.display = 'flex';
        }
        enableCheckbox.addEventListener('change', () => {
            currentLogoState.enabled = enableCheckbox.checked;
            if (configPanel) {
                configPanel.style.display = currentLogoState.enabled ? 'flex' : 'none';
            }
            renderLogo();
        });
    }

    // Opacity slider
    if (opacitySlider) {
        opacitySlider.addEventListener('input', (e) => {
            currentLogoState.opacity = parseInt(e.target.value) || 100;
            if (opacityVal) opacityVal.textContent = `${currentLogoState.opacity}%`;
            renderLogo();
        });
    }

    // Select Logo File
    async function handleLogoSelected(filePath) {
        if (!filePath) return;
        currentLogoState.path = filePath;
        currentLogoState.enabled = true;
        if (logoInput) logoInput.value = filePath;
        if (enableCheckbox) enableCheckbox.checked = true;
        if (configPanel) configPanel.style.display = 'flex';
        renderLogo();
        showToast("Đã tải Logo thành công! Bạn có thể kéo thả trực tiếp trên màn hình xem trước.", "success");
    }

    if (btnSelect) {
        btnSelect.addEventListener('click', async () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.select_image_file) {
                try {
                    const res = await window.pywebview.api.select_image_file();
                    if (res) {
                        handleLogoSelected(res);
                        return;
                    }
                } catch (e) {
                    console.warn("pywebview select_image_file error:", e);
                }
            }

            // Fallback to API
            try {
                const res = await fetch('/api/select_file', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: 'Chọn file ảnh Logo / Watermark',
                        filetypes: [['Image Files', '*.png;*.jpg;*.jpeg;*.webp'], ['All Files', '*.*']]
                    })
                });
                const data = await res.json();
                if (data.success && data.file_path) {
                    handleLogoSelected(data.file_path);
                    return;
                }
            } catch (e) {
                console.warn("API select_file error:", e);
            }

            // Fallback to hidden input
            if (hiddenFileInput) {
                hiddenFileInput.click();
            }
        });
    }

    if (hiddenFileInput) {
        hiddenFileInput.addEventListener('change', (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = async (event) => {
                    const dataUrl = event.target.result;
                    if (logoImg) logoImg.src = dataUrl;
                    currentLogoState.dataUrl = dataUrl;
                    currentLogoState.enabled = true;
                    if (enableCheckbox) enableCheckbox.checked = true;
                    if (configPanel) configPanel.style.display = 'flex';
                    
                    try {
                        const formData = new FormData();
                        formData.append('image', file);
                        const res = await fetch('/api/upload_image', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await res.json();
                        if (data.success && data.file_path) {
                            currentLogoState.path = data.file_path;
                            if (logoInput) logoInput.value = data.file_path;
                        } else {
                            currentLogoState.path = file.path || file.name;
                            if (logoInput) logoInput.value = file.path || file.name;
                        }
                    } catch (err) {
                        currentLogoState.path = file.path || file.name;
                        if (logoInput) logoInput.value = file.path || file.name;
                    }
                    renderLogo();
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Reset Logo
    if (btnReset) {
        btnReset.addEventListener('click', () => {
            currentLogoState.path = '';
            currentLogoState.enabled = false;
            if (logoInput) logoInput.value = '';
            if (enableCheckbox) enableCheckbox.checked = false;
            if (configPanel) configPanel.style.display = 'none';
            if (logoImg) logoImg.src = '';
            renderLogo();
            showToast("Đã xóa logo", "info");
        });
    }

    // Quick Snap Presets
    presetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const pos = btn.dataset.pos;
            const w = currentLogoState.w_pct || 20;
            const h = currentLogoState.h_pct || 12;

            if (pos === 'top-left') {
                currentLogoState.x_pct = 4.0;
                currentLogoState.y_pct = 4.0;
            } else if (pos === 'top-right') {
                currentLogoState.x_pct = Math.max(0, 96.0 - w);
                currentLogoState.y_pct = 4.0;
            } else if (pos === 'bottom-left') {
                currentLogoState.x_pct = 4.0;
                currentLogoState.y_pct = Math.max(0, 96.0 - h);
            } else if (pos === 'bottom-right') {
                currentLogoState.x_pct = Math.max(0, 96.0 - w);
                currentLogoState.y_pct = Math.max(0, 96.0 - h);
            } else if (pos === 'center') {
                currentLogoState.x_pct = Math.max(0, (100.0 - w) / 2);
                currentLogoState.y_pct = Math.max(0, (100.0 - h) / 2);
            }
            renderLogo();
        });
    });

    // 8-Point Drag & Resize Interaction
    let isDragging = false;
    let isResizing = false;
    let activeHandle = null;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;

    logoOverlay.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        e.preventDefault();

        const handle = e.target.closest('.logo-resize-handle');
        const parentEl = logoOverlay.offsetParent || container;
        const cRect = parentEl.getBoundingClientRect();
        const lRect = logoOverlay.getBoundingClientRect();

        startX = e.clientX;
        startY = e.clientY;
        startLeft = lRect.left - cRect.left;
        startTop = lRect.top - cRect.top;
        startWidth = lRect.width;
        startHeight = lRect.height;

        if (handle) {
            isResizing = true;
            activeHandle = handle.dataset.handle;
        } else {
            isDragging = true;
        }

        logoOverlay.classList.add('active');
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDragging && !isResizing) return;
        e.preventDefault();

        const parentEl = logoOverlay.offsetParent || container;
        const cW = parentEl.clientWidth || 640;
        const cH = parentEl.clientHeight || 360;
        if (cW <= 0 || cH <= 0) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (isDragging) {
            let newLeft = Math.max(0, Math.min(cW - startWidth, startLeft + dx));
            let newTop = Math.max(0, Math.min(cH - startHeight, startTop + dy));

            currentLogoState.x_pct = (newLeft / cW) * 100;
            currentLogoState.y_pct = (newTop / cH) * 100;

            logoOverlay.style.left = `${newLeft}px`;
            logoOverlay.style.top = `${newTop}px`;
        } else if (isResizing) {
            let newLeft = startLeft;
            let newTop = startTop;
            let newWidth = startWidth;
            let newHeight = startHeight;

            const minW = 20;
            const minH = 20;

            if (activeHandle.includes('e')) {
                newWidth = Math.max(minW, Math.min(cW - startLeft, startWidth + dx));
            }
            if (activeHandle.includes('s')) {
                newHeight = Math.max(minH, Math.min(cH - startTop, startHeight + dy));
            }
            if (activeHandle.includes('w')) {
                const maxDx = startWidth - minW;
                const actualDx = Math.max(-startLeft, Math.min(maxDx, dx));
                newLeft = startLeft + actualDx;
                newWidth = startWidth - actualDx;
            }
            if (activeHandle.includes('n')) {
                const maxDy = startHeight - minH;
                const actualDy = Math.max(-startTop, Math.min(maxDy, dy));
                newTop = startTop + actualDy;
                newHeight = startHeight - actualDy;
            }

            currentLogoState.x_pct = (newLeft / cW) * 100;
            currentLogoState.y_pct = (newTop / cH) * 100;
            currentLogoState.w_pct = (newWidth / cW) * 100;
            currentLogoState.h_pct = (newHeight / cH) * 100;

            logoOverlay.style.left = `${newLeft}px`;
            logoOverlay.style.top = `${newTop}px`;
            logoOverlay.style.width = `${newWidth}px`;
            logoOverlay.style.height = `${newHeight}px`;
        }

        if (coordBadge) {
            coordBadge.textContent = `(x: ${currentLogoState.x_pct.toFixed(1)}%, y: ${currentLogoState.y_pct.toFixed(1)}%, w: ${currentLogoState.w_pct.toFixed(1)}%)`;
        }
    });

    window.addEventListener('mouseup', () => {
        if (isDragging || isResizing) {
            isDragging = false;
            isResizing = false;
            activeHandle = null;
            logoOverlay.classList.remove('active');
            renderLogo();
        }
    });

    window.addEventListener('resize', renderLogo);
}

// Khởi tạo Video Logo Interactive Controller
setupInteractiveVideoLogo();

// ==========================================
// 🎨 MULTI-REGION BLUR & DYNAMIC TEXT OVERLAY CONTROLLER
// ==========================================
window.customOverlayLayers = []; // Global array of custom blur & text layers


// Helper: Format seconds to mm:ss
function formatSecondsToTime(sec) {
    if (isNaN(sec) || sec < 0) return '00:00';
    const sTotal = Math.floor(sec);
    const m = Math.floor(sTotal / 60);
    const s = sTotal % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function setupMultiOverlayLayers() {
    const btnAddBlur = document.getElementById('btnAddBlurLayer');
    const btnAddText = document.getElementById('btnAddTextLayer');
    const layersList = document.getElementById('overlayLayersList');
    const emptyHint = document.getElementById('overlayLayersEmptyHint');

    function ensureOverlayContainer() {
        const wrapper = document.getElementById('videoZoomWrapper');
        let c = document.getElementById('videoOverlayLayersContainer');
        if (!c && wrapper) {
            c = document.createElement('div');
            c.id = 'videoOverlayLayersContainer';
            c.style.cssText = 'position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 60;';
            wrapper.appendChild(c);
        } else if (c && wrapper && c.parentElement !== wrapper) {
            wrapper.appendChild(c);
        }
        if (c) c.style.zIndex = '60';
        return c;
    }

    function updateLayerSidebarCoords(id, x, y, w, h) {
        const badgeEl = layersList ? layersList.querySelector(`.layer-coords-badge[data-id="${id}"]`) : null;
        if (badgeEl) {
            badgeEl.textContent = `X:${x}% Y:${y}% W:${w}% H:${h}%`;
        }
    }

    function unfocusAllLayers() {
        if (layersList) {
            layersList.querySelectorAll('.overlay-layer-item').forEach(el => {
                el.classList.remove('item-focused');
                const focusBtn = el.querySelector('.btn-focus-layer');
                if (focusBtn) {
                    focusBtn.textContent = '📐 Chỉnh';
                    focusBtn.style.background = 'rgba(56, 189, 248, 0.15)';
                    focusBtn.style.borderColor = 'rgba(56, 189, 248, 0.35)';
                    focusBtn.style.color = '#38bdf8';
                }
            });
        }
        const container = ensureOverlayContainer();
        if (container) {
            container.querySelectorAll('.overlay-interactive-box').forEach(box => {
                box.classList.remove('active');
                box.style.zIndex = '65';
            });
        }
        const vContainer = document.getElementById('videoContainer');
        if (vContainer) vContainer.classList.remove('is-editing-overlay');
        updateOverlayTimingVisibility();
    }

    function focusLayer(id) {
        const vContainer = document.getElementById('videoContainer');
        if (vContainer) vContainer.classList.add('is-editing-overlay');
        // Đảm bảo Capcut transform box ẩn khi đang chỉnh lớp overlay để không cướp sự kiện kéo chuột
        document.querySelectorAll('.capcut-transform-box').forEach(el => {
            el.classList.remove('active');
            el.style.display = 'none';
        });

        if (layersList) {
            layersList.querySelectorAll('.overlay-layer-item').forEach(el => {
                const isMatch = (el.dataset.id === id);
                el.classList.toggle('item-focused', isMatch);
                const focusBtn = el.querySelector('.btn-focus-layer');
                if (focusBtn) {
                    if (isMatch) {
                        focusBtn.textContent = '✔️ Xong';
                        focusBtn.style.background = 'rgba(16, 185, 129, 0.25)';
                        focusBtn.style.borderColor = 'rgba(16, 185, 129, 0.6)';
                        focusBtn.style.color = '#6ee7b7';
                    } else {
                        focusBtn.textContent = '📐 Chỉnh';
                        focusBtn.style.background = 'rgba(56, 189, 248, 0.15)';
                        focusBtn.style.borderColor = 'rgba(56, 189, 248, 0.35)';
                        focusBtn.style.color = '#38bdf8';
                    }
                }
            });
        }
        const container = ensureOverlayContainer();
        if (container) {
            container.querySelectorAll('.overlay-interactive-box').forEach(box => {
                const isMatch = (box.dataset.id === id);
                box.classList.toggle('active', isMatch);
                box.style.zIndex = isMatch ? '75' : '65';
                if (isMatch) {
                    box.style.opacity = '1';
                    box.style.borderStyle = 'solid';
                }
            });
        }
    }

    // Render layers UI in settings card
    function renderLayersListUI() {
        if (!layersList) return;
        layersList.innerHTML = '';
        if (!Array.isArray(window.customOverlayLayers) || window.customOverlayLayers.length === 0) {
            if (emptyHint) emptyHint.style.display = 'block';
            renderOnScreenCanvasOverlays();
            return;
        }
        if (emptyHint) emptyHint.style.display = 'none';

        window.customOverlayLayers.forEach((layer, idx) => {
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
                        <span class="layer-coords-badge" data-id="${layer.id}" style="font-size: 9.5px; font-family: monospace; color: #38bdf8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 4px; padding: 1px 5px; cursor: pointer; transition: all 0.15s ease;" title="Bấm để mở khung canvas chỉnh sửa vị trí">X:${layer.x_pct}% Y:${layer.y_pct}% W:${layer.w_pct}% H:${layer.h_pct}% 📐</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 3px; flex-shrink: 0;">
                        <button type="button" class="btn-focus-layer" data-id="${layer.id}" style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 4px; color: #38bdf8; cursor: pointer; font-size: 10px; padding: 2px 5px; font-weight: 500;" title="Chọn & định vị khung trên video">📐 Chỉnh</button>
                        <button type="button" class="btn-center-layer" data-id="${layer.id}" style="background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.35); border-radius: 4px; color: #cbd5e1; cursor: pointer; font-size: 10px; padding: 2px 5px;" title="Căn giữa màn hình ngang">🎯</button>
                        <button type="button" class="btn-toggle-layer-vis" data-id="${layer.id}" style="background: none; border: none; cursor: pointer; font-size: 12px; color: ${layer.visible !== false ? '#38bdf8' : '#64748b'}; padding: 2px;" title="Ẩn/Hiện">${layer.visible !== false ? '👁️' : '🕶️'}</button>
                        <button type="button" class="btn-delete-layer" data-id="${layer.id}" style="background: none; border: none; cursor: pointer; font-size: 11px; color: #ef4444; padding: 2px;" title="Xóa lớp">🗑️</button>
                    </div>
                </div>

                <!-- Timing Settings -->
                <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(51, 65, 85, 0.5); display: flex; flex-direction: column; gap: 5px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-size: 10.5px; color: #94a3b8;">Thời gian xuất hiện:</span>
                        <select class="layer-timing-mode" data-id="${layer.id}" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10.5px;">
                            <option value="all" ${layer.timing_mode === 'all' ? 'selected' : ''}>Toàn bộ video</option>
                            <option value="custom" ${layer.timing_mode === 'custom' ? 'selected' : ''}>Tự điền mốc (mm:ss)</option>
                            <option value="random" ${layer.timing_mode === 'random' ? 'selected' : ''}>Ngẫu nhiên chu kỳ</option>
                        </select>
                    </div>

                    <!-- Custom Timing Inputs with strict validation -->
                    <div class="layer-custom-timing-wrap" style="display: ${layer.timing_mode === 'custom' ? 'flex' : 'none'}; flex-direction: column; gap: 3px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <span style="font-size: 10px; color: #94a3b8;">Từ:</span>
                            <input type="text" class="layer-start-time text-input" data-id="${layer.id}" value="${layer.start_time || '00:00'}" placeholder="00:00" style="width: 58px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                            <span style="font-size: 10px; color: #94a3b8;">Đến:</span>
                            <input type="text" class="layer-end-time text-input" data-id="${layer.id}" value="${layer.end_time || '00:10'}" placeholder="00:10" style="width: 58px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                            <button type="button" class="btn-set-current-time btn secondary small" data-id="${layer.id}" style="padding: 2px 6px; font-size: 10px;" title="Lấy mốc thời gian của khung hình hiện tại">⏱️ Hiện tại</button>
                        </div>
                        <div class="time-error-msg" id="timeError_${layer.id}">⚠️ Cấu trúc không đúng! Dùng mm:ss hoặc hh:mm:ss và Thời gian đầu phải nhỏ hơn thời gian cuối.</div>
                    </div>

                    <!-- Random Timing Settings -->
                    <div class="layer-random-timing-wrap" style="display: ${layer.timing_mode === 'random' ? 'flex' : 'none'}; align-items: center; gap: 6px;">
                        <span style="font-size: 10px; color: #94a3b8;">Hiện</span>
                        <input type="number" class="layer-random-duration text-input" data-id="${layer.id}" value="${layer.random_duration || 5}" min="1" max="60" style="width: 42px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                        <span style="font-size: 10px; color: #94a3b8;">giây mỗi</span>
                        <input type="number" class="layer-random-interval text-input" data-id="${layer.id}" value="${layer.random_interval || 15}" min="5" max="300" style="width: 48px; padding: 2px 4px; font-size: 10.5px; text-align: center;">
                        <span style="font-size: 10px; color: #94a3b8;">giây</span>
                    </div>

                    <!-- Specific Type Controls -->
                    ${isBlur ? `
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 4px;">
                            <span style="font-size: 10.5px; color: #94a3b8;">Kiểu che:</span>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                <select class="layer-blur-type" data-id="${layer.id}" style="background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10.5px;">
                                    <option value="boxblur" ${layer.blur_type === 'boxblur' ? 'selected' : ''}>Làm mờ (Blur)</option>
                                    <option value="color" ${layer.blur_type === 'color' ? 'selected' : ''}>Khối màu đơn sắc</option>
                                </select>
                                <input type="color" class="layer-mask-color" data-id="${layer.id}" value="${layer.mask_color || '#000000'}" style="width: 20px; height: 20px; border: none; border-radius: 3px; cursor: pointer; display: ${layer.blur_type === 'color' ? 'inline-block' : 'none'};">
                            </div>
                        </div>
                    ` : `
                        <div style="display: flex; flex-direction: column; gap: 4px; margin-top: 4px;">
                            <div style="display: flex; gap: 4px;">
                                <input type="text" class="layer-text-content text-input" data-id="${layer.id}" value="${escapeHtml(layer.text || '')}" placeholder="Nhập nội dung chữ..." style="flex: 1; padding: 3px 6px; font-size: 11px;">
                            </div>
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                                <span style="font-size: 10px; color: #94a3b8;">Hiệu ứng:</span>
                                <select class="layer-text-anim" data-id="${layer.id}" style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; padding: 2px 4px; font-size: 10px;">
                                    <option value="none" ${layer.animation === 'none' ? 'selected' : ''}>Tĩnh (Không hiệu ứng)</option>
                                    <option value="fade" ${layer.animation === 'fade' ? 'selected' : ''}>✨ Ẩn hiện (Fade In/Out)</option>
                                    <option value="marquee" ${layer.animation === 'marquee' ? 'selected' : ''}>🏃 Bay nhảy (Marquee)</option>
                                    <option value="pulse" ${layer.animation === 'pulse' ? 'selected' : ''}>💓 Nhấp nháy chu kỳ (Pulse)</option>
                                </select>
                                <input type="color" class="layer-text-color" data-id="${layer.id}" value="${layer.color || '#ffffff'}" title="Màu chữ" style="width: 20px; height: 20px; border: none; border-radius: 3px; cursor: pointer;">
                            </div>
                        </div>
                    `}
                </div>
            `;

            // Click trên item để focus
            item.addEventListener('click', (e) => {
                if (e.target.closest('button, input, select')) return;
                focusLayer(layer.id);
            });

            layersList.appendChild(item);
        });

        attachLayerEvents();
        renderOnScreenCanvasOverlays();
    }

    // Attach interaction handlers for layer configuration
    function attachLayerEvents() {
        if (!layersList) return;

        // Focus/Unfocus layer button
        layersList.querySelectorAll('.btn-focus-layer').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const item = btn.closest('.overlay-layer-item');
                if (item && item.classList.contains('item-focused')) {
                    unfocusAllLayers();
                } else {
                    focusLayer(btn.dataset.id);
                }
            };
        });

        // Click coords badge to open canvas position picker
        layersList.querySelectorAll('.layer-coords-badge').forEach(badge => {
            badge.onclick = (e) => {
                e.stopPropagation();
                if (typeof window.openOverlayPositionModal === 'function') {
                    window.openOverlayPositionModal(badge.dataset.id);
                }
            };
        });

        // Center horizontally button
        layersList.querySelectorAll('.btn-center-layer').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const layer = window.customOverlayLayers.find(l => l.id === id);
                if (layer) {
                    const centeredX = Math.max(0, Math.round(((100 - layer.w_pct) / 2) * 10) / 10);
                    layer.x_pct = centeredX;
                    const container = ensureOverlayContainer();
                    const box = container ? container.querySelector(`.overlay-interactive-box[data-id="${id}"]`) : null;
                    if (box) {
                        applyBoxPercentToWrapper(box, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct);
                        const coordsText = box.querySelector('.layer-coords-text');
                        if (coordsText) coordsText.textContent = `X:${layer.x_pct}% Y:${layer.y_pct}% W:${layer.w_pct}% H:${layer.h_pct}%`;
                    }
                    updateLayerSidebarCoords(id, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct);
                    focusLayer(id);
                }
            };
        });

        // Toggle visibility
        layersList.querySelectorAll('.btn-toggle-layer-vis').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const layer = window.customOverlayLayers.find(l => l.id === id);
                if (layer) {
                    layer.visible = (layer.visible === false);
                    renderLayersListUI();
                }
            };
        });

        // Delete layer
        layersList.querySelectorAll('.btn-delete-layer').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                window.customOverlayLayers = window.customOverlayLayers.filter(l => l.id !== id);
                renderLayersListUI();
            };
        });

        // Timing mode change
        layersList.querySelectorAll('.layer-timing-mode').forEach(sel => {
            sel.onchange = (e) => {
                const id = sel.dataset.id;
                const layer = window.customOverlayLayers.find(l => l.id === id);
                if (layer) {
                    layer.timing_mode = sel.value;
                    renderLayersListUI();
                }
            };
        });

        // Timing validation
        function validateLayerTiming(id) {
            const layer = window.customOverlayLayers.find(l => l.id === id);
            if (!layer || layer.timing_mode !== 'custom') return true;

            const startInput = layersList.querySelector(`.layer-start-time[data-id="${id}"]`);
            const endInput = layersList.querySelector(`.layer-end-time[data-id="${id}"]`);
            const errEl = document.getElementById(`timeError_${id}`);
            if (!startInput || !endInput) return true;

            const sVal = startInput.value.trim();
            const eVal = endInput.value.trim();

            const sSec = parseTimeToSeconds(sVal);
            const eSec = parseTimeToSeconds(eVal);

            let isValid = true;
            if (isNaN(sSec) || isNaN(eSec) || sSec < 0 || eSec <= sSec) {
                isValid = false;
            }

            if (!isValid) {
                startInput.classList.add('time-input-invalid');
                endInput.classList.add('time-input-invalid');
                if (errEl) errEl.style.display = 'block';
                layer.isTimeValid = false;
            } else {
                startInput.classList.remove('time-input-invalid');
                endInput.classList.remove('time-input-invalid');
                if (errEl) errEl.style.display = 'none';
                layer.start_time = sVal;
                layer.end_time = eVal;
                layer.start_seconds = sSec;
                layer.end_seconds = eSec;
                layer.isTimeValid = true;
            }
            return isValid;
        }

        layersList.querySelectorAll('.layer-start-time, .layer-end-time').forEach(inp => {
            inp.oninput = () => validateLayerTiming(inp.dataset.id);
            inp.onblur = () => {
                const id = inp.dataset.id;
                const sSec = parseTimeToSeconds(inp.value);
                if (!isNaN(sSec)) {
                    inp.value = formatSecondsToTime(sSec);
                }
                validateLayerTiming(id);
                updateOverlayTimingVisibility();
            };
        });

        // Set current frame time button
        layersList.querySelectorAll('.btn-set-current-time').forEach(btn => {
            btn.onclick = () => {
                const id = btn.dataset.id;
                const curT = videoPlayer ? (videoPlayer.currentTime || 0) : 0;
                const startInput = layersList.querySelector(`.layer-start-time[data-id="${id}"]`);
                const endInput = layersList.querySelector(`.layer-end-time[data-id="${id}"]`);
                if (startInput && endInput) {
                    startInput.value = formatSecondsToTime(curT);
                    endInput.value = formatSecondsToTime(curT + 5);
                    validateLayerTiming(id);
                    updateOverlayTimingVisibility();
                }
            };
        });

        // Random duration & interval
        layersList.querySelectorAll('.layer-random-duration').forEach(inp => {
            inp.onchange = () => {
                const layer = window.customOverlayLayers.find(l => l.id === inp.dataset.id);
                if (layer) layer.random_duration = parseFloat(inp.value) || 5;
            };
        });
        layersList.querySelectorAll('.layer-random-interval').forEach(inp => {
            inp.onchange = () => {
                const layer = window.customOverlayLayers.find(l => l.id === inp.dataset.id);
                if (layer) layer.random_interval = parseFloat(inp.value) || 15;
            };
        });

        // Blur specific
        layersList.querySelectorAll('.layer-blur-type').forEach(sel => {
            sel.onchange = () => {
                const layer = window.customOverlayLayers.find(l => l.id === sel.dataset.id);
                if (layer) {
                    layer.blur_type = sel.value;
                    renderLayersListUI();
                }
            };
        });
        layersList.querySelectorAll('.layer-mask-color').forEach(inp => {
            inp.oninput = () => {
                const layer = window.customOverlayLayers.find(l => l.id === inp.dataset.id);
                if (layer) {
                    layer.mask_color = inp.value;
                    renderOnScreenCanvasOverlays();
                }
            };
        });

        // Text specific
        layersList.querySelectorAll('.layer-text-content').forEach(inp => {
            inp.oninput = () => {
                const layer = window.customOverlayLayers.find(l => l.id === inp.dataset.id);
                if (layer) {
                    layer.text = inp.value;
                    const container = ensureOverlayContainer();
                    const textSpan = container ? container.querySelector(`.overlay-interactive-box[data-id="${layer.id}"] .layer-text-span`) : null;
                    if (textSpan) textSpan.textContent = layer.text || 'Nhập nội dung chữ...';
                }
            };
        });
        layersList.querySelectorAll('.layer-text-anim').forEach(sel => {
            sel.onchange = () => {
                const layer = window.customOverlayLayers.find(l => l.id === sel.dataset.id);
                if (layer) {
                    layer.animation = sel.value;
                    renderOnScreenCanvasOverlays();
                }
            };
        });
        layersList.querySelectorAll('.layer-text-color').forEach(inp => {
            inp.oninput = () => {
                const layer = window.customOverlayLayers.find(l => l.id === inp.dataset.id);
                if (layer) {
                    layer.color = inp.value;
                    const container = ensureOverlayContainer();
                    const textSpan = container ? container.querySelector(`.overlay-interactive-box[data-id="${layer.id}"] .layer-text-span`) : null;
                    if (textSpan) textSpan.style.color = layer.color || '#ffffff';
                }
            };
        });
    }

    // Cập nhật độ hiển thị theo timeline mà không phá hủy cây DOM của box
    function updateOverlayTimingVisibility() {
        if (window.isDraggingAnyBox) return;
        const container = ensureOverlayContainer();
        if (!container) return;
        const curT = videoPlayer ? (videoPlayer.currentTime || 0) : 0;

        window.customOverlayLayers.forEach(layer => {
            const box = container.querySelector(`.overlay-interactive-box[data-id="${layer.id}"]`);
            if (!box) return;

            // Nếu box đang được chọn để chỉnh sửa (active), LUÔN LUÔN giữ 100% độ nét, không bao giờ làm mờ!
            if (box.classList.contains('active')) {
                box.style.opacity = '1';
                box.style.borderStyle = 'solid';
                return;
            }

            let isVisibleNow = true;
            if (layer.timing_mode === 'custom') {
                const sSec = parseTimeToSeconds(layer.start_time);
                const eSec = parseTimeToSeconds(layer.end_time);
                if (!isNaN(sSec) && !isNaN(eSec)) {
                    isVisibleNow = (curT >= sSec && curT <= eSec);
                }
            } else if (layer.timing_mode === 'random') {
                const dur = layer.random_duration || 5;
                const interval = layer.random_interval || 15;
                const cycle = Math.floor(curT / interval);
                const timeInCycle = curT - (cycle * interval);
                isVisibleNow = (timeInCycle <= dur);
            }

            if (!isVisibleNow) {
                box.style.opacity = '0.45';
                box.style.borderStyle = 'dashed';
            } else {
                box.style.opacity = '1';
                box.style.borderStyle = 'solid';
            }
        });
    }

    // Render interactive overlay bounding boxes directly on the video player
    function renderOnScreenCanvasOverlays() {
        if (window.isDraggingAnyBox) return; // Bảo vệ: Không vẽ lại đè DOM khi đang kéo thả
        const container = ensureOverlayContainer();
        if (!container) return;

        // Lưu lại id của box đang active nếu có
        const activeBoxId = container.querySelector('.overlay-interactive-box.active')?.dataset?.id;

        container.innerHTML = '';

        const curT = videoPlayer ? (videoPlayer.currentTime || 0) : 0;
        const vRect = getVideoContentRect();

        window.customOverlayLayers.forEach(layer => {
            if (layer.visible === false) return;

            // Check timing condition
            let isVisibleNow = true;
            if (layer.timing_mode === 'custom') {
                const sSec = parseTimeToSeconds(layer.start_time);
                const eSec = parseTimeToSeconds(layer.end_time);
                if (!isNaN(sSec) && !isNaN(eSec)) {
                    isVisibleNow = (curT >= sSec && curT <= eSec);
                }
            } else if (layer.timing_mode === 'random') {
                const dur = layer.random_duration || 5;
                const interval = layer.random_interval || 15;
                const cycle = Math.floor(curT / interval);
                const timeInCycle = curT - (cycle * interval);
                isVisibleNow = (timeInCycle <= dur);
            }

            const isBlur = layer.type === 'blur';
            const box = document.createElement('div');
            box.className = `overlay-interactive-box ${isBlur ? 'blur-box-element' : 'text-box-element'}`;
            box.dataset.id = layer.id;
            box._overlayLayer = layer;

            if (activeBoxId === layer.id) {
                box.classList.add('active');
                box.style.zIndex = '75';
                box.style.opacity = '1';
                box.style.borderStyle = 'solid';
            } else if (!isVisibleNow) {
                box.style.opacity = '0.45';
                box.style.borderStyle = 'dashed';
                box.style.zIndex = '65';
            } else {
                box.style.opacity = '1';
                box.style.borderStyle = 'solid';
                box.style.zIndex = '65';
            }

            // Định vị chính xác theo % khung hình Video thực tế (y hệt blurAdjustBox & subPreviewBox)
            applyBoxPercentToWrapper(box, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct, vRect);

            // Floating badge trên đầu box với nút 🎯 Giữa, ✔️ Xong và 🗑️ Xóa (y hệt subPreviewBox & blurAdjustBox)
            const badge = document.createElement('div');
            badge.className = `overlay-adjust-badge ${isBlur ? 'blur-badge' : 'text-badge'}`;
            badge.innerHTML = `
                <span>${isBlur ? '🌫️ Vùng mờ' : '🔤 Chữ'}: <b class="layer-coords-text">X:${layer.x_pct}% Y:${layer.y_pct}% W:${layer.w_pct}% H:${layer.h_pct}%</b></span>
                <button type="button" class="btn-overlay-center" title="Căn giữa màn hình ngang">🎯 Giữa</button>
                <button type="button" class="btn-overlay-close" title="Hoàn tất chỉnh sửa">✔️ Xong</button>
                <button type="button" class="btn-overlay-delete" title="Xóa lớp">🗑️</button>
            `;
            box.appendChild(badge);

            // Sự kiện nút Căn giữa trên badge
            badge.querySelector('.btn-overlay-center')?.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                const centeredX = Math.max(0, Math.round(((100 - layer.w_pct) / 2) * 10) / 10);
                layer.x_pct = centeredX;
                applyBoxPercentToWrapper(box, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct);
                const coordsText = box.querySelector('.layer-coords-text');
                if (coordsText) coordsText.textContent = `X:${layer.x_pct}% Y:${layer.y_pct}% W:${layer.w_pct}% H:${layer.h_pct}%`;
                updateLayerSidebarCoords(layer.id, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct);
                focusLayer(layer.id);
            });

            // Sự kiện nút Xong trên badge
            badge.querySelector('.btn-overlay-close')?.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                unfocusAllLayers();
            });

            // Sự kiện nút Xóa trên badge
            badge.querySelector('.btn-overlay-delete')?.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                window.customOverlayLayers = window.customOverlayLayers.filter(l => l.id !== layer.id);
                renderLayersListUI();
            });

            // Phần tử hiển thị nội dung bên trong box với pointer-events: none để di chuyển box mượt mà không bị cản
            if (isBlur) {
                const blurInner = document.createElement('div');
                blurInner.style.width = '100%';
                blurInner.style.height = '100%';
                blurInner.style.pointerEvents = 'none';
                blurInner.style.borderRadius = '3px';
                if (layer.blur_type === 'color') {
                    blurInner.style.background = layer.mask_color || '#000000';
                } else {
                    blurInner.style.backdropFilter = 'blur(14px)';
                    blurInner.style.webkitBackdropFilter = 'blur(14px)';
                    blurInner.style.background = 'rgba(0,0,0,0.12)';
                }
                box.appendChild(blurInner);
            } else {
                let animClass = '';
                if (layer.animation === 'fade') animClass = 'anim-fade';
                else if (layer.animation === 'pulse') animClass = 'anim-pulse';
                else if (layer.animation === 'marquee') animClass = 'anim-marquee';

                const textWrap = document.createElement('div');
                textWrap.style.width = '100%';
                textWrap.style.height = '100%';
                textWrap.style.display = 'flex';
                textWrap.style.alignItems = 'center';
                textWrap.style.justifyContent = 'center';
                textWrap.style.pointerEvents = 'none';
                textWrap.style.userSelect = 'none';
                textWrap.style.overflow = 'hidden';

                const textSpan = document.createElement('span');
                textSpan.className = `layer-text-span ${animClass}`;
                textSpan.style.color = layer.color || '#ffffff';
                textSpan.style.fontSize = '13.5px';
                textSpan.style.fontWeight = '700';
                textSpan.style.textShadow = '0 2px 4px rgba(0,0,0,0.85), 0 0 2px #000';
                textSpan.style.whiteSpace = 'nowrap';
                textSpan.style.textOverflow = 'ellipsis';
                textSpan.style.overflow = 'hidden';
                textSpan.style.padding = '2px 4px';
                textSpan.textContent = layer.text || 'Nhập nội dung chữ...';

                textWrap.appendChild(textSpan);
                box.appendChild(textWrap);
            }

            // Gắn bộ điều khiển co giãn 8 điểm neo và kéo thả di chuyển chuẩn setupResizableAndDraggableBox
            setupResizableAndDraggableBox(box, (newPx, newPy, newPw, newPh, isFinished) => {
                layer.x_pct = newPx;
                layer.y_pct = newPy;
                layer.w_pct = newPw;
                layer.h_pct = newPh;

                const coordsText = box.querySelector('.layer-coords-text');
                if (coordsText) {
                    coordsText.textContent = `X:${newPx}% Y:${newPy}% W:${newPw}% H:${newPh}%`;
                }

                updateLayerSidebarCoords(layer.id, newPx, newPy, newPw, newPh);
            });

            // Focus box khi mousedown
            box.addEventListener('mousedown', (e) => {
                if (e.target.closest('button')) return;
                focusLayer(layer.id);
            });

            container.appendChild(box);
        });
    }

    // Tự động định vị lại các box khi kích thước cửa sổ / zoom video thay đổi
    function repositionOverlayBoxes() {
        if (window.isDraggingAnyBox) return;
        const container = ensureOverlayContainer();
        if (!container) return;
        const vRect = getVideoContentRect();
        window.customOverlayLayers.forEach(layer => {
            const box = container.querySelector(`.overlay-interactive-box[data-id="${layer.id}"]`);
            if (box) {
                applyBoxPercentToWrapper(box, layer.x_pct, layer.y_pct, layer.w_pct, layer.h_pct, vRect);
            }
        });
    }

    window.addEventListener('resize', repositionOverlayBoxes);

    // Add Blur Layer Button
    if (btnAddBlur) {
        btnAddBlur.onclick = () => {
            const newLayer = {
                id: 'layer_' + Date.now() + '_' + Math.floor(Math.random() * 1000),
                type: 'blur',
                name: `Vùng mờ #${window.customOverlayLayers.filter(l => l.type === 'blur').length + 1}`,
                x_pct: 15,
                y_pct: 15,
                w_pct: 35,
                h_pct: 15,
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
            window.customOverlayLayers.push(newLayer);
            renderLayersListUI();
            focusLayer(newLayer.id);
            showToast('Đã thêm vùng làm mờ mới! Kéo vị trí & co giãn trên video.', 'success');
        };
    }

    // Add Text Layer Button
    if (btnAddText) {
        btnAddText.onclick = () => {
            const newLayer = {
                id: 'layer_' + Date.now() + '_' + Math.floor(Math.random() * 1000),
                type: 'text',
                text: 'Bản quyền @KenhPhim',
                x_pct: 25,
                y_pct: 10,
                w_pct: 50,
                h_pct: 8,
                timing_mode: 'all',
                start_time: '00:00',
                end_time: '00:10',
                random_duration: 5,
                random_interval: 15,
                font: 'Montserrat',
                font_size: 24,
                color: '#ffffff',
                outline_color: '#000000',
                outline_width: 2,
                animation: 'none',
                visible: true,
                isTimeValid: true
            };
            window.customOverlayLayers.push(newLayer);
            renderLayersListUI();
            focusLayer(newLayer.id);
            showToast('Đã thêm chữ chèn mới! Kéo vị trí & co giãn trên video.', 'success');
        };
    }

    // Update overlay appearance as video plays without destroying DOM
    if (videoPlayer) {
        videoPlayer.addEventListener('timeupdate', () => {
            updateOverlayTimingVisibility();
        });
    }

    // Export render function so it can be re-triggered when opening projects
    window.renderMultiOverlayLayersUI = renderLayersListUI;
    window.repositionOverlayBoxes = repositionOverlayBoxes;
}

// Khởi tạo Multi-Blur & Dynamic Text Overlays
setupMultiOverlayLayers();

// ==========================================
// 📐 CANVAS POSITIONING PICKER MODAL (ĐỊNH VỊ VÙNG MỜ & CHỮ)
// ==========================================
function setupOverlayPositionModal() {
    const modal = document.getElementById('overlayPositionModal');
    const btnOpen = document.getElementById('btnOpenOverlayPositionModal');
    const btnOpenFromHint = document.getElementById('btnOpenOverlayPositionModalFromHint');
    const btnClose = document.getElementById('btnCloseOverlayPositionModal');
    const btnCancel = document.getElementById('btnCancelOverlayPositionModal');
    const btnSave = document.getElementById('btnSaveOverlayPositionModal');
    const canvasContainer = document.getElementById('positionCanvasContainer');
    const layersWrapper = document.getElementById('canvasLayersWrapper');
    const canvasAspectBadge = document.getElementById('canvasAspectBadge');
    const canvasResBadge = document.getElementById('canvasResBadge');
    const ratioBtns = document.querySelectorAll('.btn-canvas-ratio');
    
    const btnAddBlur = document.getElementById('btnModalAddBlur');
    const btnAddText = document.getElementById('btnModalAddText');
    const btnDelete = document.getElementById('btnModalDeleteSelectedLayer');
    const inputX = document.getElementById('inputModalCoordX');
    const inputY = document.getElementById('inputModalCoordY');
    const inputW = document.getElementById('inputModalCoordW');
    const inputH = document.getElementById('inputModalCoordH');
    const titleEl = document.getElementById('modalSelectedLayerTitle');
    const layersListEl = document.getElementById('modalLayersList');
    const layersCountEl = document.getElementById('modalLayersCount');
    const presetBtns = document.querySelectorAll('.btn-canvas-preset');

    let currentRatio = '9/16'; // '9/16', '16/9', '1/1', '4/3'
    let tempLayers = [];
    let selectedLayerId = null;
    let activeOverlayContext = 'editor'; // 'editor' | 'batch_editor'

    function openModal(targetLayerId = null, context = 'editor') {
        if (!modal) return;
        activeOverlayContext = context;
        
        // 1. Nhận diện tỷ lệ khung hình video thực tế
        let detected = false;
        if (context === 'batch_editor') {
            const batchAspect = document.getElementById('batch_editToolAspectRatio')?.value;
            if (batchAspect === '9:16') { currentRatio = '9/16'; detected = true; }
            else if (batchAspect === '16:9') { currentRatio = '16/9'; detected = true; }
            else if (batchAspect === '1:1') { currentRatio = '1/1'; detected = true; }
            else if (batchAspect === '4:3') { currentRatio = '4/3'; detected = true; }
        }

        if (!detected) {
            const video = document.getElementById('videoPlayer');
            if (video && video.videoWidth && video.videoHeight) {
                const r = video.videoWidth / video.videoHeight;
                if (Math.abs(r - (9 / 16)) < 0.1) {
                    currentRatio = '9/16';
                } else if (Math.abs(r - (16 / 9)) < 0.15) {
                    currentRatio = '16/9';
                } else if (Math.abs(r - 1) < 0.1) {
                    currentRatio = '1/1';
                } else if (Math.abs(r - (4 / 3)) < 0.1) {
                    currentRatio = '4/3';
                } else {
                    currentRatio = r < 1 ? '9/16' : '16/9';
                }
            } else {
                currentRatio = '9/16';
            }
        }

        updateRatioButtonsUI();
        applyCanvasAspectRatio();

        // 2. Clone danh sách layers theo context
        const sourceLayers = (context === 'batch_editor')
            ? (Array.isArray(window.batchCustomOverlayLayers) && window.batchCustomOverlayLayers.length > 0 ? window.batchCustomOverlayLayers : window.customOverlayLayers)
            : window.customOverlayLayers;

        if (Array.isArray(sourceLayers) && sourceLayers.length > 0) {
            tempLayers = JSON.parse(JSON.stringify(sourceLayers));
        } else {
            tempLayers = [{
                id: 'layer_' + Date.now(),
                type: 'blur',
                name: 'Vùng mờ #1',
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
                visible: true
            }];
        }

        if (targetLayerId && tempLayers.some(l => l.id === targetLayerId)) {
            selectedLayerId = targetLayerId;
        } else {
            selectedLayerId = tempLayers[0] ? tempLayers[0].id : null;
        }

        renderCanvas();
        renderModalSidebar();

        modal.style.display = 'flex';
    }

    function closeModal() {
        if (modal) modal.style.display = 'none';
    }

    function updateRatioButtonsUI() {
        ratioBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.ratio === currentRatio);
        });
        if (canvasAspectBadge) {
            const labelMap = {
                '9/16': '9:16 (Phim ngắn/Dọc)',
                '16/9': '16:9 (Phim ngang/YouTube)',
                '1/1': '1:1 (Vuông)',
                '4/3': '4:3 (Truyền hình)'
            };
            canvasAspectBadge.textContent = labelMap[currentRatio] || currentRatio;
        }
        if (canvasResBadge) {
            const resMap = {
                '9/16': '1080 × 1920 [9:16]',
                '16/9': '1920 × 1080 [16:9]',
                '1/1': '1080 × 1080 [1:1]',
                '4/3': '1440 × 1080 [4:3]'
            };
            canvasResBadge.textContent = resMap[currentRatio] || currentRatio;
        }
    }

    function applyCanvasAspectRatio() {
        if (!canvasContainer) return;
        const parent = document.getElementById('positionCanvasArea');
        if (!parent) return;

        const maxH = Math.min(500, parent.clientHeight - 60 || 460);
        const maxW = Math.min(600, parent.clientWidth - 40 || 460);

        let w = 270, h = 480;
        if (currentRatio === '9/16') {
            h = Math.min(maxH, maxW * (16 / 9));
            w = h * (9 / 16);
        } else if (currentRatio === '16/9') {
            w = Math.min(maxW, maxH * (16 / 9));
            h = w * (9 / 16);
        } else if (currentRatio === '1/1') {
            const side = Math.min(maxW, maxH);
            w = side;
            h = side;
        } else if (currentRatio === '4/3') {
            w = Math.min(maxW, maxH * (4 / 3));
            h = w * (3 / 4);
        }

        canvasContainer.style.width = Math.round(w) + 'px';
        canvasContainer.style.height = Math.round(h) + 'px';
    }

    function renderCanvas() {
        if (!layersWrapper) return;
        layersWrapper.innerHTML = '';

        tempLayers.forEach(layer => {
            const box = document.createElement('div');
            box.className = `canvas-interactive-box type-${layer.type} ${layer.id === selectedLayerId ? 'active' : ''}`;
            box.dataset.id = layer.id;
            box.style.left = `${layer.x_pct}%`;
            box.style.top = `${layer.y_pct}%`;
            box.style.width = `${layer.w_pct}%`;
            box.style.height = `${layer.h_pct}%`;

            const badge = document.createElement('div');
            badge.className = 'canvas-box-badge';
            const typeIcon = layer.type === 'blur' ? '🌫️' : '🔤';
            badge.textContent = `${typeIcon} ${layer.type === 'blur' ? (layer.name || 'Vùng mờ') : (layer.text ? layer.text.substring(0, 12) : 'Chữ')} (${layer.x_pct}%, ${layer.y_pct}%)`;
            box.appendChild(badge);

            if (layer.type === 'text') {
                const textPreview = document.createElement('span');
                textPreview.style.fontSize = '12px';
                textPreview.style.fontWeight = '700';
                textPreview.style.color = layer.color || '#fff';
                textPreview.style.textShadow = '0 1px 3px #000';
                textPreview.style.whiteSpace = 'nowrap';
                textPreview.style.overflow = 'hidden';
                textPreview.style.textOverflow = 'ellipsis';
                textPreview.style.padding = '2px 6px';
                textPreview.textContent = layer.text || 'Nội dung chữ...';
                box.appendChild(textPreview);
            }

            // Gắn 8 resize handles
            const handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
            handles.forEach(pos => {
                const handle = document.createElement('div');
                handle.className = `canvas-resize-handle canvas-handle-${pos}`;
                handle.dataset.handle = pos;
                box.appendChild(handle);
            });

            // Interactive Drag & Resize
            bindBoxInteraction(box, layer);

            // Click to select
            box.addEventListener('mousedown', (e) => {
                if (e.target.closest('.canvas-resize-handle')) return;
                selectLayer(layer.id);
            });

            layersWrapper.appendChild(box);
        });
    }

    function bindBoxInteraction(box, layer) {
        let isDragging = false;
        let activeHandle = null;
        let startX = 0, startY = 0;
        let initBox = { x: 0, y: 0, w: 0, h: 0 };
        let canvasRect = null;

        box.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.stopPropagation();
            e.preventDefault();

            selectLayer(layer.id);

            const handle = e.target.closest('.canvas-resize-handle');
            if (handle) {
                activeHandle = handle.dataset.handle;
            } else {
                isDragging = true;
            }

            canvasRect = layersWrapper.getBoundingClientRect();
            startX = e.clientX;
            startY = e.clientY;
            initBox = {
                x: layer.x_pct,
                y: layer.y_pct,
                w: layer.w_pct,
                h: layer.h_pct
            };

            const onMouseMove = (moveEvt) => {
                const dxPx = moveEvt.clientX - startX;
                const dyPx = moveEvt.clientY - startY;
                const dxPct = (dxPx / (canvasRect.width || 1)) * 100;
                const dyPct = (dyPx / (canvasRect.height || 1)) * 100;

                if (isDragging) {
                    let newX = Math.round((initBox.x + dxPct) * 10) / 10;
                    let newY = Math.round((initBox.y + dyPct) * 10) / 10;
                    newX = Math.max(0, Math.min(100 - initBox.w, newX));
                    newY = Math.max(0, Math.min(100 - initBox.h, newY));

                    layer.x_pct = newX;
                    layer.y_pct = newY;
                } else if (activeHandle) {
                    let newX = initBox.x;
                    let newY = initBox.y;
                    let newW = initBox.w;
                    let newH = initBox.h;

                    if (activeHandle.includes('e')) newW = initBox.w + dxPct;
                    if (activeHandle.includes('s')) newH = initBox.h + dyPct;
                    if (activeHandle.includes('w')) {
                        newW = initBox.w - dxPct;
                        newX = initBox.x + dxPct;
                    }
                    if (activeHandle.includes('n')) {
                        newH = initBox.h - dyPct;
                        newY = initBox.y + dyPct;
                    }

                    if (newW < 3) newW = 3;
                    if (newH < 2) newH = 2;
                    if (newX < 0) { newW += newX; newX = 0; }
                    if (newY < 0) { newH += newY; newY = 0; }
                    if (newX + newW > 100) newW = 100 - newX;
                    if (newY + newH > 100) newH = 100 - newY;

                    layer.x_pct = Math.round(newX * 10) / 10;
                    layer.y_pct = Math.round(newY * 10) / 10;
                    layer.w_pct = Math.round(newW * 10) / 10;
                    layer.h_pct = Math.round(newH * 10) / 10;
                }

                box.style.left = `${layer.x_pct}%`;
                box.style.top = `${layer.y_pct}%`;
                box.style.width = `${layer.w_pct}%`;
                box.style.height = `${layer.h_pct}%`;

                const badge = box.querySelector('.canvas-box-badge');
                if (badge) {
                    const typeIcon = layer.type === 'blur' ? '🌫️' : '🔤';
                    badge.textContent = `${typeIcon} ${layer.type === 'blur' ? (layer.name || 'Vùng mờ') : (layer.text ? layer.text.substring(0, 12) : 'Chữ')} (${layer.x_pct}%, ${layer.y_pct}%)`;
                }

                updateInputsFromSelectedLayer();
            };

            const onMouseUp = () => {
                isDragging = false;
                activeHandle = null;
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            };

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }

    function selectLayer(id) {
        selectedLayerId = id;
        if (layersWrapper) {
            layersWrapper.querySelectorAll('.canvas-interactive-box').forEach(b => {
                b.classList.toggle('active', b.dataset.id === id);
            });
        }
        renderModalSidebar();
    }

    function updateInputsFromSelectedLayer() {
        const layer = tempLayers.find(l => l.id === selectedLayerId);
        if (!layer) return;
        if (inputX) inputX.value = layer.x_pct;
        if (inputY) inputY.value = layer.y_pct;
        if (inputW) inputW.value = layer.w_pct;
        if (inputH) inputH.value = layer.h_pct;
    }

    function renderModalSidebar() {
        const selected = tempLayers.find(l => l.id === selectedLayerId);
        const card = document.getElementById('modalSelectedLayerCard');
        if (layersCountEl) layersCountEl.textContent = tempLayers.length;

        if (!selected) {
            if (card) card.style.display = 'none';
        } else {
            if (card) card.style.display = 'flex';
            if (titleEl) {
                const typeIcon = selected.type === 'blur' ? '🌫️' : '🔤';
                titleEl.textContent = `Đang chọn: ${typeIcon} ${selected.type === 'blur' ? (selected.name || 'Vùng mờ') : (selected.text || 'Chữ')}`;
                titleEl.style.color = selected.type === 'blur' ? '#f59e0b' : '#38bdf8';
            }
            updateInputsFromSelectedLayer();
        }

        if (layersListEl) {
            layersListEl.innerHTML = '';
            tempLayers.forEach(l => {
                const row = document.createElement('div');
                const isSelected = (l.id === selectedLayerId);
                row.style.cssText = `
                    padding: 8px 10px; background: ${isSelected ? 'rgba(56, 189, 248, 0.15)' : '#1e293b'};
                    border: 1px solid ${isSelected ? '#38bdf8' : '#334155'};
                    border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 6px;
                `;
                const typeIcon = l.type === 'blur' ? '🌫️' : '🔤';
                const label = l.type === 'blur' ? (l.name || 'Vùng mờ') : (l.text || 'Chữ');
                row.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 6px; overflow: hidden;">
                        <span>${typeIcon}</span>
                        <span style="font-size: 11.5px; font-weight: 600; color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;">${escapeHtml(label)}</span>
                    </div>
                    <span style="font-size: 10px; font-family: monospace; color: #94a3b8;">(${l.x_pct}%, ${l.y_pct}%)</span>
                `;
                row.onclick = () => selectLayer(l.id);
                layersListEl.appendChild(row);
            });
        }
    }

    [inputX, inputY, inputW, inputH].forEach(inp => {
        if (!inp) return;
        inp.oninput = () => {
            const layer = tempLayers.find(l => l.id === selectedLayerId);
            if (!layer) return;
            layer.x_pct = parseFloat(inputX.value) || 0;
            layer.y_pct = parseFloat(inputY.value) || 0;
            layer.w_pct = parseFloat(inputW.value) || 10;
            layer.h_pct = parseFloat(inputH.value) || 10;

            const box = layersWrapper ? layersWrapper.querySelector(`.canvas-interactive-box[data-id="${layer.id}"]`) : null;
            if (box) {
                box.style.left = `${layer.x_pct}%`;
                box.style.top = `${layer.y_pct}%`;
                box.style.width = `${layer.w_pct}%`;
                box.style.height = `${layer.h_pct}%`;
            }
        };
    });

    ratioBtns.forEach(btn => {
        btn.onclick = () => {
            currentRatio = btn.dataset.ratio;
            updateRatioButtonsUI();
            applyCanvasAspectRatio();
        };
    });

    presetBtns.forEach(btn => {
        btn.onclick = () => {
            const layer = tempLayers.find(l => l.id === selectedLayerId);
            if (!layer) return;
            const p = btn.dataset.preset;
            if (p === 'top-left') { layer.x_pct = 5; layer.y_pct = 5; layer.w_pct = 35; layer.h_pct = 10; }
            else if (p === 'top-center') { layer.x_pct = 32.5; layer.y_pct = 5; layer.w_pct = 35; layer.h_pct = 10; }
            else if (p === 'top-right') { layer.x_pct = 60; layer.y_pct = 5; layer.w_pct = 35; layer.h_pct = 10; }
            else if (p === 'center') { layer.x_pct = 25; layer.y_pct = 45; layer.w_pct = 50; layer.h_pct = 10; }
            else if (p === 'bottom-center') { layer.x_pct = 25; layer.y_pct = 82; layer.w_pct = 50; layer.h_pct = 12; }
            else if (p === 'sub-strip') { layer.x_pct = 10; layer.y_pct = 80; layer.w_pct = 80; layer.h_pct = 14; }

            renderCanvas();
            renderModalSidebar();
        };
    });

    if (btnAddBlur) {
        btnAddBlur.onclick = () => {
            const newLayer = {
                id: 'layer_' + Date.now(),
                type: 'blur',
                name: `Vùng mờ #${tempLayers.filter(l => l.type === 'blur').length + 1}`,
                x_pct: 20,
                y_pct: 25,
                w_pct: 60,
                h_pct: 12,
                timing_mode: 'all',
                start_time: '00:00',
                end_time: '00:10',
                random_duration: 5,
                random_interval: 15,
                blur_type: 'boxblur',
                blur_intensity: 15,
                mask_color: '#000000',
                visible: true
            };
            tempLayers.push(newLayer);
            selectedLayerId = newLayer.id;
            renderCanvas();
            renderModalSidebar();
        };
    }

    if (btnAddText) {
        btnAddText.onclick = () => {
            const newLayer = {
                id: 'layer_' + Date.now(),
                type: 'text',
                text: 'Bản quyền @KenhPhim',
                x_pct: 25,
                y_pct: 10,
                w_pct: 50,
                h_pct: 8,
                timing_mode: 'all',
                start_time: '00:00',
                end_time: '00:10',
                random_duration: 5,
                random_interval: 15,
                font: 'Montserrat',
                font_size: 24,
                color: '#ffffff',
                outline_color: '#000000',
                outline_width: 2,
                animation: 'none',
                visible: true
            };
            tempLayers.push(newLayer);
            selectedLayerId = newLayer.id;
            renderCanvas();
            renderModalSidebar();
        };
    }

    if (btnDelete) {
        btnDelete.onclick = () => {
            tempLayers = tempLayers.filter(l => l.id !== selectedLayerId);
            selectedLayerId = tempLayers[0] ? tempLayers[0].id : null;
            renderCanvas();
            renderModalSidebar();
        };
    }

    if (btnSave) {
        btnSave.onclick = () => {
            if (activeOverlayContext === 'batch_editor') {
                window.batchCustomOverlayLayers = JSON.parse(JSON.stringify(tempLayers));
                if (typeof window.renderBatchMultiOverlayLayersUI === 'function') {
                    window.renderBatchMultiOverlayLayersUI();
                }
                showToast('Đã cập nhật vị trí vùng làm mờ & chữ động cho Biên tập hàng loạt!', 'success');
            } else {
                window.customOverlayLayers = JSON.parse(JSON.stringify(tempLayers));
                if (typeof window.renderMultiOverlayLayersUI === 'function') {
                    window.renderMultiOverlayLayersUI();
                }
                if (typeof window.repositionOverlayBoxes === 'function') {
                    window.repositionOverlayBoxes();
                }
                showToast('Đã cập nhật vị trí vùng làm mờ & chữ động thành công!', 'success');
            }
            closeModal();
        };
    }

    if (btnOpen) btnOpen.onclick = openModal;
    if (btnOpenFromHint) btnOpenFromHint.onclick = openModal;
    if (btnClose) btnClose.onclick = closeModal;
    if (btnCancel) btnCancel.onclick = closeModal;

    window.openOverlayPositionModal = openModal;
}

// Khởi tạo Canvas Positioning Modal
setupOverlayPositionModal();

// ==========================================
// 🪄 AUTO DELOGO / REMOVE WATERMARK CONTROLLER & LIVE PREVIEW
// ==========================================
function setupAutoDelogoControls() {
    const enableCheckbox = document.getElementById('enableAutoDelogo');
    const configPanel = document.getElementById('delogoConfigPanel');
    const cornerSelect = document.getElementById('delogoCorner');
    const sizeSelect = document.getElementById('delogoSize');
    const methodSelect = document.getElementById('delogoMethod');
    const delogoOverlay = document.getElementById('delogoPreviewOverlay');
    const delogoBadge = document.getElementById('delogoPreviewBadge');
    const btnPreviewFrame = document.getElementById('btnPreviewDelogoFrame');
    const btnPreviewEdited = document.getElementById('btnPreviewEdited');
    const btnPreviewOrig = document.getElementById('btnPreviewOriginal');

    // Modal elements
    const modal = document.getElementById('delogoCompareModal');
    const btnCloseModal = document.getElementById('btnCloseDelogoModal');
    const btnDoneModal = document.getElementById('btnDoneDelogoModal');
    const modalImgOrig = document.getElementById('delogoModalImgOrig');
    const modalImgProc = document.getElementById('delogoModalImgProc');
    const modalBoxOverlay = document.getElementById('delogoModalBoxOverlay');
    const modalSubTitle = document.getElementById('delogoModalSubTitle');
    const modalMethodBadge = document.getElementById('delogoModalMethodBadge');

    if (!enableCheckbox || !configPanel) return;

    function updateDelogoPreview() {
        if (!delogoOverlay) return;

        const isEnabled = enableCheckbox && enableCheckbox.checked;
        const isEditedMode = btnPreviewEdited && btnPreviewEdited.classList.contains('active');

        // If not enabled or in Original view, hide overlay & reset zoom
        if (!isEnabled || !isEditedMode) {
            delogoOverlay.style.opacity = '0';
            delogoOverlay.style.visibility = 'hidden';
            if (videoPlayer && videoPlayer._hasSmartCropZoom) {
                videoPlayer.style.transform = '';
                videoPlayer._hasSmartCropZoom = false;
            }
            return;
        }

        const method = methodSelect ? methodSelect.value : 'delogo';

        // Mode 3: Smart Crop (Zoom tâm +5%)
        if (method === 'smart_crop') {
            delogoOverlay.style.opacity = '0';
            delogoOverlay.style.visibility = 'hidden';
            if (videoPlayer) {
                videoPlayer.style.transform = 'scale(1.05)';
                videoPlayer.style.transformOrigin = 'center center';
                videoPlayer.style.transition = 'transform 0.15s ease';
                videoPlayer._hasSmartCropZoom = true;
            }
            return;
        }

        // Mode 1 & 2: Delogo / Gaussian BoxBlur
        if (videoPlayer && videoPlayer._hasSmartCropZoom) {
            videoPlayer.style.transform = '';
            videoPlayer._hasSmartCropZoom = false;
        }

        const vRect = (typeof getVideoContentRect === 'function') ? getVideoContentRect() : null;
        if (!vRect || vRect.videoW <= 0 || vRect.videoH <= 0) return;

        const corner = cornerSelect ? cornerSelect.value : 'bottom-right';
        const size = sizeSelect ? sizeSelect.value : 'medium';

        let dw, dh;
        if (size === 'small') {
            dw = Math.max(30, vRect.videoW * 0.12);
            dh = Math.max(15, vRect.videoH * 0.055);
        } else if (size === 'large') {
            dw = Math.max(60, vRect.videoW * 0.25);
            dh = Math.max(25, vRect.videoH * 0.11);
        } else {
            dw = Math.max(45, vRect.videoW * 0.18);
            dh = Math.max(20, vRect.videoH * 0.08);
        }

        const m = Math.max(4, 8 * (vRect.videoW / 800));
        let dx, dy;
        if (corner === 'top-left') {
            dx = vRect.videoX + m;
            dy = vRect.videoY + m;
        } else if (corner === 'top-right') {
            dx = vRect.videoX + vRect.videoW - dw - m;
            dy = vRect.videoY + m;
        } else if (corner === 'bottom-left') {
            dx = vRect.videoX + m;
            dy = vRect.videoY + vRect.videoH - dh - m;
        } else { // bottom-right
            dx = vRect.videoX + vRect.videoW - dw - m;
            dy = vRect.videoY + vRect.videoH - dh - m;
        }

        delogoOverlay.style.left = `${dx}px`;
        delogoOverlay.style.top = `${dy}px`;
        delogoOverlay.style.width = `${dw}px`;
        delogoOverlay.style.height = `${dh}px`;

        if (method === 'boxblur') {
            delogoOverlay.style.backdropFilter = 'blur(14px)';
            delogoOverlay.style.webkitBackdropFilter = 'blur(14px)';
            delogoOverlay.style.background = 'rgba(0, 0, 0, 0.08)';
            delogoOverlay.style.border = '1px dashed rgba(245, 158, 11, 0.6)';
            if (delogoBadge) delogoBadge.textContent = '🌫️ Gaussian Blur';
        } else {
            delogoOverlay.style.backdropFilter = 'blur(16px) contrast(1.05) brightness(1.02)';
            delogoOverlay.style.webkitBackdropFilter = 'blur(16px) contrast(1.05) brightness(1.02)';
            delogoOverlay.style.background = 'rgba(255, 255, 255, 0.03)';
            delogoOverlay.style.border = '1px dashed rgba(56, 189, 248, 0.6)';
            if (delogoBadge) delogoBadge.textContent = '🪄 FFmpeg Delogo';
        }

        delogoOverlay.style.opacity = '1';
        delogoOverlay.style.visibility = 'visible';
    }

    // Toggle switch handler
    enableCheckbox.addEventListener('change', () => {
        configPanel.style.display = enableCheckbox.checked ? 'flex' : 'none';
        if (enableCheckbox.checked) {
            // Tự động chuyển sang chế độ "Bản sau khi sửa" để thấy ngay hiệu ứng
            if (btnPreviewOrig && btnPreviewOrig.classList.contains('active') && btnPreviewEdited) {
                btnPreviewEdited.click();
            }
            updateDelogoPreview();
            showToast('Đang hiển thị hiệu ứng Xóa Logo Góc trực tiếp trên video!', 'info');
        } else {
            updateDelogoPreview();
        }
    });

    // Listen to changes in options
    if (cornerSelect) cornerSelect.addEventListener('change', updateDelogoPreview);
    if (sizeSelect) sizeSelect.addEventListener('change', updateDelogoPreview);
    if (methodSelect) methodSelect.addEventListener('change', updateDelogoPreview);

    // Sync with Preview Mode buttons
    if (btnPreviewOrig) {
        btnPreviewOrig.addEventListener('click', () => {
            setTimeout(updateDelogoPreview, 20);
        });
    }
    if (btnPreviewEdited) {
        btnPreviewEdited.addEventListener('click', () => {
            setTimeout(updateDelogoPreview, 20);
        });
    }

    // Video events to keep overlay positioned perfectly
    if (videoPlayer) {
        videoPlayer.addEventListener('loadedmetadata', updateDelogoPreview);
        videoPlayer.addEventListener('timeupdate', () => {
            if (enableCheckbox.checked && delogoOverlay && delogoOverlay.style.visibility === 'visible') {
                updateDelogoPreview();
            }
        });
        videoPlayer.addEventListener('seeked', updateDelogoPreview);
        videoPlayer.addEventListener('play', updateDelogoPreview);
    }
    window.addEventListener('resize', updateDelogoPreview);

    // ==========================================
    // 📸 FFmpeg Frame Snapshot Comparison (A/B Test)
    // ==========================================
    if (btnPreviewFrame && modal) {
        btnPreviewFrame.addEventListener('click', async () => {
            const inputPath = document.getElementById('editorInputVideoPath')?.value?.trim();
            if (!inputPath) {
                showToast('Vui lòng chọn video đầu vào trước để xem mẫu!', 'warning');
                return;
            }

            const origText = btnPreviewFrame.innerHTML;
            btnPreviewFrame.disabled = true;
            btnPreviewFrame.innerHTML = `<span>⏳</span><span>Đang xử lý mẫu qua FFmpeg...</span>`;

            try {
                const currentTime = videoPlayer ? (videoPlayer.currentTime || 0) : 0;
                const corner = cornerSelect ? cornerSelect.value : 'bottom-right';
                const size = sizeSelect ? sizeSelect.value : 'medium';
                const method = methodSelect ? methodSelect.value : 'delogo';

                const res = await fetch('/api/delogo/preview_frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video_path: inputPath,
                        timestamp: currentTime,
                        corner,
                        size,
                        method
                    })
                });

                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.error || 'Lỗi khi trích xuất khung hình');
                }

                if (modalImgOrig) modalImgOrig.src = data.original_image;
                if (modalImgProc) modalImgProc.src = data.processed_image;

                if (modalSubTitle) {
                    const mins = Math.floor(currentTime / 60);
                    const secs = Math.floor(currentTime % 60);
                    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
                    modalSubTitle.textContent = `Mốc thời gian: ${timeStr} | Góc: ${corner} | Kích thước: ${size}`;
                }

                if (modalMethodBadge) {
                    if (method === 'smart_crop') {
                        modalMethodBadge.textContent = '🔍 Zoom tâm (+5%)';
                    } else if (method === 'boxblur') {
                        modalMethodBadge.textContent = '🌫️ Gaussian Blur';
                    } else {
                        modalMethodBadge.textContent = '✨ FFmpeg Delogo';
                    }
                }

                // Vị trí hộp viền đỏ trên khung hình gốc
                if (modalBoxOverlay && data.crop_box) {
                    const b = data.crop_box;
                    const lPct = (b.x / b.vw) * 100;
                    const tPct = (b.y / b.vh) * 100;
                    const wPct = (b.w / b.vw) * 100;
                    const hPct = (b.h / b.vh) * 100;

                    modalBoxOverlay.style.left = `${lPct}%`;
                    modalBoxOverlay.style.top = `${tPct}%`;
                    modalBoxOverlay.style.width = `${wPct}%`;
                    modalBoxOverlay.style.height = `${hPct}%`;
                    modalBoxOverlay.style.display = method === 'smart_crop' ? 'none' : 'block';
                }

                modal.style.display = 'flex';
            } catch (err) {
                showToast(`Không thể trích xuất mẫu: ${err.message}`, 'error');
            } finally {
                btnPreviewFrame.disabled = false;
                btnPreviewFrame.innerHTML = origText;
            }
        });

        const closeModalFunc = () => { modal.style.display = 'none'; };
        if (btnCloseModal) btnCloseModal.addEventListener('click', closeModalFunc);
        if (btnDoneModal) btnDoneModal.addEventListener('click', closeModalFunc);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModalFunc();
        });
    }
}
setupAutoDelogoControls();

// ==========================================
// 📺 REVIEW PHIM VIDEO PLAYER & LIVE FX PREVIEW CONTROLLER
// ==========================================
const reviewVideoPlayer = document.getElementById('reviewVideoPlayer');
const reviewVideoContainer = document.getElementById('reviewVideoContainer');
const reviewDynamicBlurOverlay = document.getElementById('reviewDynamicBlurOverlay');
const reviewVideoLogoOverlay = document.getElementById('reviewVideoLogoOverlay');
const reviewVideoLogoImg = document.getElementById('reviewVideoLogoImg');
const reviewVideoPlaceholder = document.getElementById('reviewVideoPlaceholder');
const reviewPlayerStatusBadge = document.getElementById('reviewPlayerStatusBadge');
const btnReviewPlay = document.getElementById('btnReviewPlay');
const reviewVideoTimeline = document.getElementById('reviewVideoTimeline');
const reviewTimeDisplay = document.getElementById('reviewTimeDisplay');
const reviewVolumeSlider = document.getElementById('reviewVolumeSlider');
const btnReviewPreviewOriginal = document.getElementById('btnReviewPreviewOriginal');
const btnReviewPreviewEdited = document.getElementById('btnReviewPreviewEdited');
const reviewVideoLoadingSpinner = document.getElementById('reviewVideoLoadingSpinner');

let isReviewPreviewEditedMode = true;
let isSeekingReviewTimeline = false;
let _lastReviewBlurState = { visible: false };

window.currentReviewLogoState = {
    enabled: false,
    path: '',
    x_pct: 5.0,
    y_pct: 5.0,
    w_pct: 18.0,
    h_pct: 12.0,
    opacity: 100
};

function loadReviewVideoPlayer(path) {
    if (!path || !reviewVideoPlayer) return;
    
    if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'block';
    
    if (reviewPlayerStatusBadge) {
        reviewPlayerStatusBadge.textContent = '⏳ Đang nạp...';
        reviewPlayerStatusBadge.style.color = '#38bdf8';
        reviewPlayerStatusBadge.style.borderColor = 'rgba(56, 189, 248, 0.3)';
    }

    reviewVideoPlayer.src = `/api/video?path=${encodeURIComponent(path)}`;
    reviewVideoPlayer.style.display = 'block';
    if (reviewVideoPlaceholder) reviewVideoPlaceholder.style.display = 'none';
    reviewVideoPlayer.load();
}

function safeSeekReviewVideo(targetSecs, autoPlay = false) {
    if (!reviewVideoPlayer) return;
    const applySeek = () => {
        try {
            if (!isNaN(targetSecs) && targetSecs >= 0) {
                reviewVideoPlayer.currentTime = targetSecs;
            }
            if (autoPlay) {
                const p = reviewVideoPlayer.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(e => console.log('Review play handled:', e));
                }
            }
        } catch(e) {
            console.error('safeSeekReviewVideo error:', e);
        }
    };

    if (!reviewVideoPlayer.src || reviewVideoPlayer.src === '' || reviewVideoPlayer.src.endsWith('/')) {
        const inp = document.getElementById('reviewInputVideoPath');
        if (inp && inp.value) {
            reviewVideoPlayer.src = `/api/video?path=${encodeURIComponent(inp.value)}`;
            reviewVideoPlayer.addEventListener('loadedmetadata', function onMeta() {
                reviewVideoPlayer.removeEventListener('loadedmetadata', onMeta);
                applySeek();
            });
            reviewVideoPlayer.load();
            return;
        }
    }

    if (reviewVideoPlayer.readyState >= 1) {
        applySeek();
    } else {
        const onMeta = () => {
            reviewVideoPlayer.removeEventListener('loadedmetadata', onMeta);
            applySeek();
        };
        reviewVideoPlayer.addEventListener('loadedmetadata', onMeta);
    }
}

async function autoParseReviewSrt(srtPath) {
    if (!srtPath) return;
    try {
        const res = await fetch('/api/subtitles/parse_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ srt_path: srtPath })
        });
        const data = await res.json();
        if (data.success && data.subtitles && data.subtitles.length > 0) {
            window.reviewParsedSubtitles = data.subtitles;
            if (!window.reviewTabScannedAiBoxes || window.reviewTabScannedAiBoxes.length === 0) {
                window.reviewTabScannedAiBoxes = data.subtitles.map(s => ({
                    startSeconds: s.startSeconds,
                    endSeconds: s.endSeconds,
                    visual_start: s.startSeconds,
                    visual_end: s.endSeconds,
                    x_pct: 20,
                    y_pct: parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || 81.5,
                    w_pct: 60,
                    h_pct: 9.5,
                    text: s.text
                }));
                updateReviewTabAiScanBadge(window.reviewTabScannedAiBoxes.length, window.reviewTabScannedAiBoxes.length);
            }
            showToast(`Đã nạp ${data.subtitles.length} câu phụ đề vào hệ thống Review!`, "success");
        }
    } catch(e) {
        console.warn("autoParseReviewSrt error:", e);
    }
}

function formatVideoTime(seconds) {
    if (isNaN(seconds) || seconds === null || seconds === undefined || seconds < 0) return '00:00';
    const totalSecs = Math.floor(seconds);
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    const pad = (n) => (n < 10 ? '0' + n : n);
    if (hrs > 0) {
        return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
    }
    return `${pad(mins)}:${pad(secs)}`;
}

function toggleContainerFullscreen(container, btn) {
    if (!container) return;
    const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
    if (!isFull) {
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.webkitRequestFullscreen) {
            container.webkitRequestFullscreen();
        } else if (container.mozRequestFullScreen) {
            container.mozRequestFullScreen();
        } else if (container.msRequestFullscreen) {
            container.msRequestFullscreen();
        }
        if (btn) btn.innerHTML = '🗗';
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
        if (btn) btn.innerHTML = '⛶';
    }
}

// Global Fullscreen Event Listeners
['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
    document.addEventListener(evt, () => {
        const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
        const btnRev = document.getElementById('btnReviewFullscreen');
        const btnEd = document.getElementById('btnEditorFullscreen');
        if (btnRev) btnRev.innerHTML = isFull ? '🗗' : '⛶';
        if (btnEd) btnEd.innerHTML = isFull ? '🗗' : '⛶';
        if (window.renderReviewLogo) window.renderReviewLogo();
        if (typeof renderLogo === 'function') renderLogo();
    });
});

// Setup Editor Fullscreen button
const btnEditorFullscreen = document.getElementById('btnEditorFullscreen');
if (btnEditorFullscreen && videoContainer) {
    btnEditorFullscreen.addEventListener('click', () => {
        toggleContainerFullscreen(videoContainer, btnEditorFullscreen);
    });
}

function setupReviewVideoPlayerController() {
    if (!reviewVideoPlayer) return;

    function updateReviewTimeDisplay() {
        const cur = reviewVideoPlayer.currentTime || 0;
        const dur = reviewVideoPlayer.duration || 0;
        if (reviewTimeDisplay) {
            reviewTimeDisplay.textContent = `${formatVideoTime(cur)} / ${formatVideoTime(dur)}`;
        }
        if (dur > 0 && !isSeekingReviewTimeline && reviewVideoTimeline) {
            reviewVideoTimeline.value = (cur / dur) * 100;
        }
    }

    // Loading & Lifecycle Events
    reviewVideoPlayer.addEventListener('waiting', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'block';
    });
    reviewVideoPlayer.addEventListener('seeking', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'block';
    });
    reviewVideoPlayer.addEventListener('canplay', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'none';
        updateReviewTimeDisplay();
    });
    reviewVideoPlayer.addEventListener('playing', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'none';
        if (btnReviewPlay) {
            btnReviewPlay.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`;
        }
        if (reviewPlayerStatusBadge) {
            reviewPlayerStatusBadge.textContent = '▶ Đang phát';
            reviewPlayerStatusBadge.style.color = '#34d399';
            reviewPlayerStatusBadge.style.borderColor = '#10b981';
        }
        updateReviewTimeDisplay();
    });

    reviewVideoPlayer.addEventListener('pause', () => {
        window.liveDubbingEngine.stop();
        window.liveDubbingEngine.restoreVolume(reviewVideoPlayer);
        if (btnReviewPlay) {
            btnReviewPlay.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>`;
        }
        if (reviewPlayerStatusBadge && reviewVideoPlayer.duration) {
            reviewPlayerStatusBadge.textContent = `Sẵn sàng (${reviewVideoPlayer.videoWidth}x${reviewVideoPlayer.videoHeight})`;
            reviewPlayerStatusBadge.style.color = '#38bdf8';
            reviewPlayerStatusBadge.style.borderColor = 'rgba(56, 189, 248, 0.3)';
        }
        updateReviewTimeDisplay();
    });

    reviewVideoPlayer.addEventListener('seeking', () => {
        window.liveDubbingEngine.stop();
        window.liveDubbingEngine.restoreVolume(reviewVideoPlayer);
    });

    reviewVideoPlayer.addEventListener('durationchange', updateReviewTimeDisplay);

    reviewVideoPlayer.addEventListener('loadedmetadata', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'none';
        reviewVideoPlayer.style.display = 'block';
        if (reviewVideoPlaceholder) reviewVideoPlaceholder.style.display = 'none';
        
        updateReviewTimeDisplay();
        if (reviewPlayerStatusBadge) {
            reviewPlayerStatusBadge.textContent = `Sẵn sàng (${reviewVideoPlayer.videoWidth || '1080'}x${reviewVideoPlayer.videoHeight || '1920'})`;
            reviewPlayerStatusBadge.style.color = '#34d399';
            reviewPlayerStatusBadge.style.borderColor = '#10b981';
        }
        updateReviewPlayerAspectRatio(reviewAspectRatio || '16:9');
    });

    reviewVideoPlayer.addEventListener('error', () => {
        if (reviewVideoLoadingSpinner) reviewVideoLoadingSpinner.style.display = 'none';
        if (reviewPlayerStatusBadge) {
            reviewPlayerStatusBadge.textContent = '⚠️ Lỗi video';
            reviewPlayerStatusBadge.style.color = '#ef4444';
            reviewPlayerStatusBadge.style.borderColor = '#ef4444';
        }
        showToast("Không thể phát video này. Hãy kiểm tra định dạng hoặc đường dẫn file!", "error");
    });

    // Play / Pause Button
    if (btnReviewPlay) {
        btnReviewPlay.addEventListener('click', () => {
            if (reviewVideoPlayer.paused) {
                if (!reviewVideoPlayer.src || reviewVideoPlayer.src === '' || reviewVideoPlayer.src.endsWith('/')) {
                    const inp = document.getElementById('reviewInputVideoPath');
                    if (inp && inp.value) {
                        loadReviewVideoPlayer(inp.value);
                    } else {
                        showToast("Vui lòng chọn video phim đầu vào trước!", "warning");
                        return;
                    }
                }
                reviewVideoPlayer.play().catch(e => console.log('Review play err:', e));
            } else {
                reviewVideoPlayer.pause();
            }
        });
    }

    // Time Update & Timeline Seek
    reviewVideoPlayer.addEventListener('timeupdate', () => {
        updateReviewTimeDisplay();
        syncReviewDynamicBlur(reviewVideoPlayer.currentTime);
    });

    if (reviewVideoTimeline) {
        reviewVideoTimeline.addEventListener('mousedown', () => { isSeekingReviewTimeline = true; });
        reviewVideoTimeline.addEventListener('touchstart', () => { isSeekingReviewTimeline = true; });

        reviewVideoTimeline.addEventListener('input', (e) => {
            if (reviewVideoPlayer.duration) {
                const seekTime = (parseFloat(e.target.value) / 100) * reviewVideoPlayer.duration;
                safeSeekReviewVideo(seekTime, false);
                if (reviewTimeDisplay) {
                    reviewTimeDisplay.textContent = `${formatVideoTime(seekTime)} / ${formatVideoTime(reviewVideoPlayer.duration)}`;
                }
            }
        });

        const onReviewSeekEnd = (e) => {
            if (isSeekingReviewTimeline && reviewVideoPlayer.duration) {
                const seekTime = (parseFloat(e.target.value) / 100) * reviewVideoPlayer.duration;
                safeSeekReviewVideo(seekTime, false);
                isSeekingReviewTimeline = false;
            }
        };

        reviewVideoTimeline.addEventListener('change', onReviewSeekEnd);
        reviewVideoTimeline.addEventListener('mouseup', onReviewSeekEnd);
        reviewVideoTimeline.addEventListener('touchend', onReviewSeekEnd);
    }

    // Volume Slider
    if (reviewVolumeSlider) {
        reviewVolumeSlider.addEventListener('input', (e) => {
            reviewVideoPlayer.volume = parseFloat(e.target.value);
        });
    }

    // Subtitle Jump Buttons (Prev / Next Subtitle)
    const btnReviewPrevSub = document.getElementById('btnReviewPrevSub');
    const btnReviewNextSub = document.getElementById('btnReviewNextSub');

    function getReviewSubtitleList() {
        if (window.reviewTabScannedAiBoxes && window.reviewTabScannedAiBoxes.length > 0) {
            return window.reviewTabScannedAiBoxes.map((b, i) => ({
                index: i + 1,
                start: b.visual_start !== undefined ? b.visual_start : (b.startSeconds || 0),
                end: b.visual_end !== undefined ? b.visual_end : (b.endSeconds || 0),
                box: b
            })).filter(s => !isNaN(s.start));
        }
        if (window.reviewParsedSubtitles && window.reviewParsedSubtitles.length > 0) {
            return window.reviewParsedSubtitles.map((s, i) => ({
                index: i + 1,
                start: s.startSeconds || 0,
                end: s.endSeconds || 0,
                text: s.text || ''
            }));
        }
        return [];
    }

    if (btnReviewPrevSub) {
        btnReviewPrevSub.addEventListener('click', () => {
            const list = getReviewSubtitleList();
            if (list.length === 0) {
                showToast("Chưa có danh sách phụ đề để nhảy!", "warning");
                return;
            }
            const cur = reviewVideoPlayer.currentTime || 0;
            // Find subtitle before current time
            let target = null;
            for (let i = list.length - 1; i >= 0; i--) {
                if (list[i].start < cur - 0.25) {
                    target = list[i];
                    break;
                }
            }
            if (!target) target = list[0];
            safeSeekReviewVideo(target.start + 0.05, false);
            syncReviewDynamicBlur(target.start + 0.05, true);
            showToast(`⏮️ Đã chuyển đến câu #${target.index} (${formatVideoTime(target.start)})`, "info");
        });
    }

    if (btnReviewNextSub) {
        btnReviewNextSub.addEventListener('click', () => {
            const list = getReviewSubtitleList();
            if (list.length === 0) {
                showToast("Chưa có danh sách phụ đề để nhảy!", "warning");
                return;
            }
            const cur = reviewVideoPlayer.currentTime || 0;
            // Find subtitle after current time
            let target = null;
            for (let i = 0; i < list.length; i++) {
                if (list[i].start > cur + 0.1) {
                    target = list[i];
                    break;
                }
            }
            if (!target) target = list[list.length - 1];
            safeSeekReviewVideo(target.start + 0.05, false);
            syncReviewDynamicBlur(target.start + 0.05, true);
            showToast(`⏭️ Đã chuyển đến câu #${target.index} (${formatVideoTime(target.start)})`, "info");
        });
    }

    // Toggle Preview Mode (Original vs Edited)
    if (btnReviewPreviewOriginal && btnReviewPreviewEdited) {
        btnReviewPreviewOriginal.addEventListener('click', () => {
            isReviewPreviewEditedMode = false;
            btnReviewPreviewOriginal.classList.add('active');
            btnReviewPreviewEdited.classList.remove('active');
            if (reviewDynamicBlurOverlay) reviewDynamicBlurOverlay.style.visibility = 'hidden';
            if (reviewVideoLogoOverlay) reviewVideoLogoOverlay.style.display = 'none';
            window.liveDubbingEngine.stop();
            window.liveDubbingEngine.restoreVolume(reviewVideoPlayer);
        });

        btnReviewPreviewEdited.addEventListener('click', () => {
            isReviewPreviewEditedMode = true;
            btnReviewPreviewEdited.classList.add('active');
            btnReviewPreviewOriginal.classList.remove('active');
            syncReviewDynamicBlur(reviewVideoPlayer.currentTime || 0, true);
            if (window.renderReviewLogo) window.renderReviewLogo();
        });
    }

    // Fullscreen Toggle for Review Player
    const btnReviewFullscreen = document.getElementById('btnReviewFullscreen');
    if (btnReviewFullscreen && reviewVideoContainer) {
        btnReviewFullscreen.addEventListener('click', () => {
            toggleContainerFullscreen(reviewVideoContainer, btnReviewFullscreen);
        });
    }

    // Click on Video Container to Play/Pause
    if (reviewVideoContainer) {
        reviewVideoContainer.addEventListener('dblclick', (e) => {
            if (e.target.closest('.logo-resize-handle') || e.target.closest('#reviewVideoLogoOverlay')) return;
            toggleContainerFullscreen(reviewVideoContainer, btnReviewFullscreen);
        });

        reviewVideoContainer.addEventListener('click', (e) => {
            if (e.target.closest('.logo-resize-handle') || e.target.closest('#reviewVideoLogoOverlay')) return;
            if (!reviewVideoPlayer.src || reviewVideoPlayer.src === '' || reviewVideoPlayer.src.endsWith('/')) {
                const inp = document.getElementById('reviewInputVideoPath');
                if (inp && inp.value) {
                    loadReviewVideoPlayer(inp.value);
                    reviewVideoPlayer.play().catch(e => console.log(e));
                }
                return;
            }
            if (reviewVideoPlayer.paused) {
                reviewVideoPlayer.play().catch(e => console.log(e));
            } else {
                reviewVideoPlayer.pause();
            }
        });

        // Drag & Drop on Review Player
        reviewVideoContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            reviewVideoContainer.style.borderColor = '#38bdf8';
            reviewVideoContainer.style.background = 'rgba(14, 165, 233, 0.08)';
        });

        reviewVideoContainer.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            reviewVideoContainer.style.borderColor = '';
            reviewVideoContainer.style.background = '#020617';
        });

        reviewVideoContainer.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            reviewVideoContainer.style.borderColor = '';
            reviewVideoContainer.style.background = '#020617';

            const files = e.dataTransfer.files;
            if (!files || files.length === 0) return;
            const file = files[0];
            const name = file.name.toLowerCase();
            const filePath = file.path || file.name;

            if (name.endsWith('.mp4') || name.endsWith('.mkv') || name.endsWith('.mov') || name.endsWith('.avi') || name.endsWith('.webm')) {
                const inp = document.getElementById('reviewInputVideoPath');
                if (inp) inp.value = filePath;
                loadReviewVideoPlayer(filePath);
                showToast(`Đã nạp video phim: ${file.name}`, "success");
            } else if (name.endsWith('.srt') || name.endsWith('.vtt') || name.endsWith('.ass')) {
                const inpSrt = document.getElementById('reviewInputSrtPath');
                if (inpSrt) inpSrt.value = filePath;
                autoParseReviewSrt(filePath);
            } else if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.webp')) {
                const reader = new FileReader();
                reader.onload = async (event) => {
                    const dataUrl = event.target.result;
                    const reviewLogoImg = document.getElementById('reviewVideoLogoImg');
                    if (reviewLogoImg) reviewLogoImg.src = dataUrl;
                    window.currentReviewLogoState.dataUrl = dataUrl;
                    window.currentReviewLogoState.enabled = true;
                    const enableCheckbox = document.getElementById('reviewEnableLogoWatermark');
                    const configPanel = document.getElementById('reviewLogoConfigPanel');
                    const logoInput = document.getElementById('reviewLogoInputPath');
                    if (enableCheckbox) enableCheckbox.checked = true;
                    if (configPanel) configPanel.style.display = 'flex';
                    try {
                        const formData = new FormData();
                        formData.append('image', file);
                        const res = await fetch('/api/upload_image', { method: 'POST', body: formData });
                        const data = await res.json();
                        if (data.success && data.file_path) {
                            window.currentReviewLogoState.path = data.file_path;
                            if (logoInput) logoInput.value = data.file_path;
                        } else {
                            window.currentReviewLogoState.path = file.path || file.name;
                            if (logoInput) logoInput.value = file.path || file.name;
                        }
                    } catch (err) {
                        window.currentReviewLogoState.path = file.path || file.name;
                        if (logoInput) logoInput.value = file.path || file.name;
                    }
                    if (window.renderReviewLogo) window.renderReviewLogo();
                    showToast(`Đã nạp Logo: ${file.name}`, "success");
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Dynamic Blur Overlay high-precision sync
    function syncReviewDynamicBlur(currentTime, forceUpdate = false) {
        if (!reviewDynamicBlurOverlay || !isReviewPreviewEditedMode) {
            if (reviewDynamicBlurOverlay) reviewDynamicBlurOverlay.style.visibility = 'hidden';
            return;
        }

        const isBlurEnabled = document.getElementById('reviewTabBlurOriginalSubtitles')?.checked ?? true;
        if (!isBlurEnabled) {
            if (_lastReviewBlurState.visible || forceUpdate) {
                reviewDynamicBlurOverlay.style.visibility = 'hidden';
                reviewDynamicBlurOverlay.style.opacity = '0';
                _lastReviewBlurState = { visible: false };
            }
            return;
        }

        const rawReviewLead = parseFloat(document.getElementById('reviewTabBlurLeadOffset')?.value);
        const blurLead = (Number.isFinite(rawReviewLead) ? rawReviewLead : -180) / 1000;
        const rawReviewPad = parseFloat(document.getElementById('reviewTabBlurPadding')?.value);
        const blurPad = (Number.isFinite(rawReviewPad) ? rawReviewPad : 220) / 1000;
        const blurVal = parseInt(document.getElementById('reviewTabDynBlurIntensity')?.value) || 15;
        const blurY = parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || 81.5;

        let activeBox = null;
        let activeIdx = -1;
        let isInsideInterval = false;

        // 1. Check AI Scanned Boxes first
        if (window.reviewTabScannedAiBoxes && window.reviewTabScannedAiBoxes.length > 0) {
            for (let idx = 0; idx < window.reviewTabScannedAiBoxes.length; idx++) {
                const b = window.reviewTabScannedAiBoxes[idx];
                if (!b) continue;
                const vStart = (b.visual_start !== undefined ? b.visual_start : (b.startSeconds || 0)) + blurLead;
                const vEnd = (b.visual_end !== undefined ? b.visual_end : (b.endSeconds || 0)) + blurPad;
                if (currentTime >= vStart && currentTime <= vEnd) {
                    activeBox = b;
                    activeIdx = idx + 1;
                    isInsideInterval = true;
                    break;
                }
            }
        }

        // 2. Fallback to Parsed Subtitles if AI scan not done for this frame
        if (!isInsideInterval && window.reviewParsedSubtitles && window.reviewParsedSubtitles.length > 0) {
            for (let idx = 0; idx < window.reviewParsedSubtitles.length; idx++) {
                const s = window.reviewParsedSubtitles[idx];
                if (!s) continue;
                const sStart = (s.startSeconds || 0) + blurLead;
                const sEnd = (s.endSeconds || 0) + blurPad;
                if (currentTime >= sStart && currentTime <= sEnd) {
                    const calcW = calculateSubtitleWidthPercent(s.text);
                    activeBox = {
                        x_pct: Math.max(2, (100 - calcW) / 2),
                        w_pct: calcW,
                        y_pct: blurY,
                        h_pct: 9.5
                    };
                    activeIdx = idx + 1;
                    isInsideInterval = true;
                    break;
                }
            }
        }

        if (!isInsideInterval) {
            if (_lastReviewBlurState.visible || forceUpdate) {
                reviewDynamicBlurOverlay.style.visibility = 'hidden';
                reviewDynamicBlurOverlay.style.opacity = '0';
                _lastReviewBlurState = { visible: false };
            }
            return;
        }

        const sliderW = parseFloat(document.getElementById('reviewTabBlurWidth')?.value) || (window.reviewBlurRegion?.w);
        const sliderH = parseFloat(document.getElementById('reviewTabBlurHeight')?.value) || (window.reviewBlurRegion?.h);
        const sliderX = parseFloat(document.getElementById('reviewTabBlurXPos')?.value) || (window.reviewBlurRegion?.x);
        const sliderY = parseFloat(document.getElementById('reviewTabBlurYPos')?.value) || (window.reviewBlurRegion?.y) || blurY;

        const regionX = (sliderX !== undefined && !isNaN(sliderX)) ? sliderX : 20;
        const regionY = (sliderY !== undefined && !isNaN(sliderY)) ? sliderY : blurY;
        const regionW = (sliderW !== undefined && !isNaN(sliderW)) ? sliderW : 60;
        const regionH = (sliderH !== undefined && !isNaN(sliderH)) ? sliderH : 9.5;

        const centerX = regionX + (regionW / 2.0);
        let leftPct = regionX;
        let topPct = regionY;
        let widthPct = regionW;
        let heightPct = regionH;

        if (activeBox && typeof activeBox.w_pct === 'number' && activeBox.w_pct > 0) {
            const rawBoxW = activeBox.w_pct;
            const rawBoxX = activeBox.x_pct != null ? activeBox.x_pct : (centerX - rawBoxW / 2.0);
            const boxCenterX = rawBoxX + (rawBoxW / 2.0);
            const padW = Math.max(1.5, Math.min(4.0, rawBoxW * 0.05));
            widthPct = Math.min(98, rawBoxW + (padW * 2));
            leftPct = Math.max(0, Math.min(100 - widthPct, boxCenterX - (widthPct / 2.0)));
            if (activeBox.y_pct != null && activeBox.h_pct != null) {
                const rawBoxY = activeBox.y_pct;
                const rawBoxH = activeBox.h_pct;
                const boxCenterY = rawBoxY + (rawBoxH / 2.0);
                const padH = Math.max(0.8, Math.min(2.5, rawBoxH * 0.18));
                heightPct = Math.min(35, Math.max(3.0, rawBoxH + (padH * 2.0)));
                topPct = Math.max(0, Math.min(98 - heightPct, boxCenterY - (heightPct / 2.0)));
            }
        } else {
            widthPct = regionW;
            leftPct = regionX;
        }

        // Diff caching unless forced
        if (
            !forceUpdate &&
            _lastReviewBlurState.visible === true &&
            _lastReviewBlurState.left === leftPct &&
            _lastReviewBlurState.top === topPct &&
            _lastReviewBlurState.width === widthPct &&
            _lastReviewBlurState.height === heightPct &&
            _lastReviewBlurState.blur === blurVal
        ) {
            return;
        }

        _lastReviewBlurState = {
            visible: true,
            left: leftPct,
            top: topPct,
            width: widthPct,
            height: heightPct,
            blur: blurVal
        };

        reviewDynamicBlurOverlay.style.background = 'rgba(15, 23, 42, 0.45)';
        reviewDynamicBlurOverlay.style.backdropFilter = `blur(${blurVal}px)`;
        reviewDynamicBlurOverlay.style.webkitBackdropFilter = `blur(${blurVal}px)`;
        reviewDynamicBlurOverlay.style.border = '1.5px dashed rgba(56, 189, 248, 0.6)';
        reviewDynamicBlurOverlay.style.boxShadow = '0 0 14px rgba(56, 189, 248, 0.35)';
        reviewDynamicBlurOverlay.style.borderRadius = '6px';
        reviewDynamicBlurOverlay.style.top = `${topPct}%`;
        reviewDynamicBlurOverlay.style.height = `${heightPct}%`;
        reviewDynamicBlurOverlay.style.left = `${leftPct}%`;
        reviewDynamicBlurOverlay.style.width = `${widthPct}%`;
        reviewDynamicBlurOverlay.style.visibility = 'visible';
        reviewDynamicBlurOverlay.style.opacity = '1';

        if (reviewPlayerStatusBadge && activeIdx > 0 && reviewVideoPlayer.paused) {
            reviewPlayerStatusBadge.textContent = `🎯 Đang che câu #${activeIdx} (W: ${widthPct.toFixed(1)}%, X: ${leftPct.toFixed(1)}%)`;
            reviewPlayerStatusBadge.style.color = '#38bdf8';
            reviewPlayerStatusBadge.style.borderColor = 'rgba(56, 189, 248, 0.4)';
        }
    }

    if (reviewDynamicBlurOverlay) {
        reviewDynamicBlurOverlay.style.cursor = 'pointer';
        reviewDynamicBlurOverlay.title = 'Bấm vào đây để điều chỉnh vùng làm mờ trên màn hình (8 hướng)';
        reviewDynamicBlurOverlay.addEventListener('click', (e) => {
            e.stopPropagation();
            if (typeof showReviewBlurAdjustBox === 'function') {
                showReviewBlurAdjustBox(true);
            }
        });
    }

    window.triggerReviewDynamicBlurSync = () => {
        syncReviewDynamicBlur(reviewVideoPlayer ? reviewVideoPlayer.currentTime : 0, true);
    };
}

function setupInteractiveReviewLogo() {
    const enableCheckbox = document.getElementById('reviewEnableLogoWatermark');
    const configPanel = document.getElementById('reviewLogoConfigPanel');
    const logoInput = document.getElementById('reviewLogoInputPath');
    const hiddenFileInput = document.getElementById('reviewLogoFileInputHidden');
    const btnSelect = document.getElementById('btnSelectReviewLogoFile');
    const btnReset = document.getElementById('btnResetReviewLogo');
    const opacitySlider = document.getElementById('reviewLogoOpacity');
    const opacityVal = document.getElementById('reviewLogoOpacityVal');
    const coordBadge = document.getElementById('reviewLogoCoordBadge');
    const presetBtns = document.querySelectorAll('.btn-review-logo-preset');

    const logoOverlay = document.getElementById('reviewVideoLogoOverlay');
    const logoImg = document.getElementById('reviewVideoLogoImg');
    const container = document.getElementById('reviewVideoContainer');

    if (!logoOverlay || !container) return;

    window.renderReviewLogo = function() {
        if (!window.currentReviewLogoState.enabled || !window.currentReviewLogoState.path || !isReviewPreviewEditedMode) {
            logoOverlay.style.display = 'none';
            return;
        }

        const cW = container.clientWidth || 640;
        const cH = container.clientHeight || 360;

        const leftPx = (window.currentReviewLogoState.x_pct / 100) * cW;
        const topPx = (window.currentReviewLogoState.y_pct / 100) * cH;
        const widthPx = (window.currentReviewLogoState.w_pct / 100) * cW;
        const heightPx = (window.currentReviewLogoState.h_pct / 100) * cH;

        logoOverlay.style.display = 'block';
        logoOverlay.style.left = `${leftPx}px`;
        logoOverlay.style.top = `${topPx}px`;
        logoOverlay.style.width = `${widthPx}px`;
        logoOverlay.style.height = `${heightPx}px`;
        logoOverlay.style.opacity = `${window.currentReviewLogoState.opacity / 100}`;

        if (logoImg) {
            if (window.currentReviewLogoState.dataUrl) {
                if (logoImg.src !== window.currentReviewLogoState.dataUrl) logoImg.src = window.currentReviewLogoState.dataUrl;
            } else if (window.currentReviewLogoState.path) {
                const imgSrc = `/api/image?path=${encodeURIComponent(window.currentReviewLogoState.path)}`;
                if (!logoImg.src.includes(encodeURIComponent(window.currentReviewLogoState.path))) {
                    logoImg.src = imgSrc;
                }
            }
        }

        if (coordBadge) {
            coordBadge.textContent = `(x: ${window.currentReviewLogoState.x_pct.toFixed(1)}%, y: ${window.currentReviewLogoState.y_pct.toFixed(1)}%, w: ${window.currentReviewLogoState.w_pct.toFixed(1)}%)`;
        }
    };

    if (enableCheckbox) {
        enableCheckbox.addEventListener('change', () => {
            window.currentReviewLogoState.enabled = enableCheckbox.checked;
            if (configPanel) configPanel.style.display = window.currentReviewLogoState.enabled ? 'flex' : 'none';
            window.renderReviewLogo();
        });
    }

    if (opacitySlider) {
        opacitySlider.addEventListener('input', (e) => {
            window.currentReviewLogoState.opacity = parseInt(e.target.value) || 100;
            if (opacityVal) opacityVal.textContent = `${window.currentReviewLogoState.opacity}%`;
            window.renderReviewLogo();
        });
    }

    async function handleReviewLogoSelected(filePath) {
        if (!filePath) return;
        window.currentReviewLogoState.path = filePath;
        window.currentReviewLogoState.enabled = true;
        if (logoInput) logoInput.value = filePath;
        if (enableCheckbox) enableCheckbox.checked = true;
        if (configPanel) configPanel.style.display = 'flex';
        window.renderReviewLogo();
        showToast("Review Phim: Đã tải Logo thành công! Bạn có thể kéo thả trực tiếp trên màn hình xem trước.", "success");
    }

    if (btnSelect) {
        btnSelect.addEventListener('click', async () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.select_image_file) {
                try {
                    const res = await window.pywebview.api.select_image_file();
                    if (res) {
                        handleReviewLogoSelected(res);
                        return;
                    }
                } catch (e) {
                    console.warn("pywebview select error:", e);
                }
            }

            try {
                const res = await fetch('/api/select_file', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: 'Chọn file ảnh Logo / Watermark cho Review Phim',
                        filetypes: [['Image Files', '*.png;*.jpg;*.jpeg;*.webp'], ['All Files', '*.*']]
                    })
                });
                const data = await res.json();
                if (data.success && data.file_path) {
                    handleReviewLogoSelected(data.file_path);
                    return;
                }
            } catch (e) {
                console.warn("API select_file error:", e);
            }

            if (hiddenFileInput) hiddenFileInput.click();
        });
    }

    if (hiddenFileInput) {
        hiddenFileInput.addEventListener('change', (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = async (event) => {
                    const dataUrl = event.target.result;
                    if (logoImg) logoImg.src = dataUrl;
                    window.currentReviewLogoState.dataUrl = dataUrl;
                    window.currentReviewLogoState.enabled = true;
                    if (enableCheckbox) enableCheckbox.checked = true;
                    if (configPanel) configPanel.style.display = 'flex';
                    
                    try {
                        const formData = new FormData();
                        formData.append('image', file);
                        const res = await fetch('/api/upload_image', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await res.json();
                        if (data.success && data.file_path) {
                            window.currentReviewLogoState.path = data.file_path;
                            if (logoInput) logoInput.value = data.file_path;
                        } else {
                            window.currentReviewLogoState.path = file.path || file.name;
                            if (logoInput) logoInput.value = file.path || file.name;
                        }
                    } catch (err) {
                        window.currentReviewLogoState.path = file.path || file.name;
                        if (logoInput) logoInput.value = file.path || file.name;
                    }
                    window.renderReviewLogo();
                };
                reader.readAsDataURL(file);
            }
        });
    }

    if (btnReset) {
        btnReset.addEventListener('click', () => {
            window.currentReviewLogoState.path = '';
            window.currentReviewLogoState.enabled = false;
            if (logoInput) logoInput.value = '';
            if (enableCheckbox) enableCheckbox.checked = false;
            if (configPanel) configPanel.style.display = 'none';
            if (logoImg) logoImg.src = '';
            window.renderReviewLogo();
            showToast("Review Phim: Đã xóa logo", "info");
        });
    }

    presetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const pos = btn.dataset.pos;
            const w = window.currentReviewLogoState.w_pct || 18;
            const h = window.currentReviewLogoState.h_pct || 12;

            if (pos === 'top-left') {
                window.currentReviewLogoState.x_pct = 4.0;
                window.currentReviewLogoState.y_pct = 4.0;
            } else if (pos === 'top-right') {
                window.currentReviewLogoState.x_pct = Math.max(0, 96.0 - w);
                window.currentReviewLogoState.y_pct = 4.0;
            } else if (pos === 'bottom-left') {
                window.currentReviewLogoState.x_pct = 4.0;
                window.currentReviewLogoState.y_pct = Math.max(0, 96.0 - h);
            } else if (pos === 'bottom-right') {
                window.currentReviewLogoState.x_pct = Math.max(0, 96.0 - w);
                window.currentReviewLogoState.y_pct = Math.max(0, 96.0 - h);
            } else if (pos === 'center') {
                window.currentReviewLogoState.x_pct = Math.max(0, (100.0 - w) / 2);
                window.currentReviewLogoState.y_pct = Math.max(0, (100.0 - h) / 2);
            }
            window.renderReviewLogo();
        });
    });

    // 8-point interactive resize and drag on Review Player
    let isDragging = false;
    let isResizing = false;
    let activeHandle = null;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;

    logoOverlay.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        e.preventDefault();

        const handle = e.target.closest('.logo-resize-handle');
        const cRect = container.getBoundingClientRect();
        const lRect = logoOverlay.getBoundingClientRect();

        startX = e.clientX;
        startY = e.clientY;
        startLeft = lRect.left - cRect.left;
        startTop = lRect.top - cRect.top;
        startWidth = lRect.width;
        startHeight = lRect.height;

        if (handle) {
            isResizing = true;
            activeHandle = handle.dataset.handle;
        } else {
            isDragging = true;
        }

        logoOverlay.classList.add('active');
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDragging && !isResizing) return;
        e.preventDefault();

        const cW = container.clientWidth || 640;
        const cH = container.clientHeight || 360;
        if (cW <= 0 || cH <= 0) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (isDragging) {
            let newLeft = Math.max(0, Math.min(cW - startWidth, startLeft + dx));
            let newTop = Math.max(0, Math.min(cH - startHeight, startTop + dy));

            window.currentReviewLogoState.x_pct = (newLeft / cW) * 100;
            window.currentReviewLogoState.y_pct = (newTop / cH) * 100;

            logoOverlay.style.left = `${newLeft}px`;
            logoOverlay.style.top = `${newTop}px`;
        } else if (isResizing) {
            let newLeft = startLeft;
            let newTop = startTop;
            let newWidth = startWidth;
            let newHeight = startHeight;

            const minW = 20;
            const minH = 20;

            if (activeHandle.includes('e')) {
                newWidth = Math.max(minW, Math.min(cW - startLeft, startWidth + dx));
            }
            if (activeHandle.includes('s')) {
                newHeight = Math.max(minH, Math.min(cH - startTop, startHeight + dy));
            }
            if (activeHandle.includes('w')) {
                const maxDx = startWidth - minW;
                const actualDx = Math.max(-startLeft, Math.min(maxDx, dx));
                newLeft = startLeft + actualDx;
                newWidth = startWidth - actualDx;
            }
            if (activeHandle.includes('n')) {
                const maxDy = startHeight - minH;
                const actualDy = Math.max(-startTop, Math.min(maxDy, dy));
                newTop = startTop + actualDy;
                newHeight = startHeight - actualDy;
            }

            window.currentReviewLogoState.x_pct = (newLeft / cW) * 100;
            window.currentReviewLogoState.y_pct = (newTop / cH) * 100;
            window.currentReviewLogoState.w_pct = (newWidth / cW) * 100;
            window.currentReviewLogoState.h_pct = (newHeight / cH) * 100;

            logoOverlay.style.left = `${newLeft}px`;
            logoOverlay.style.top = `${newTop}px`;
            logoOverlay.style.width = `${newWidth}px`;
            logoOverlay.style.height = `${newHeight}px`;
        }

        if (coordBadge) {
            coordBadge.textContent = `(x: ${window.currentReviewLogoState.x_pct.toFixed(1)}%, y: ${window.currentReviewLogoState.y_pct.toFixed(1)}%, w: ${window.currentReviewLogoState.w_pct.toFixed(1)}%)`;
        }
    });

    window.addEventListener('mouseup', () => {
        if (isDragging || isResizing) {
            isDragging = false;
            isResizing = false;
            activeHandle = null;
            logoOverlay.classList.remove('active');
            window.renderReviewLogo();
        }
    });

    window.addEventListener('resize', window.renderReviewLogo);
}

setupReviewVideoPlayerController();
setupInteractiveReviewLogo();
updateReviewPlayerAspectRatio(reviewAspectRatio || '16:9');

// ═════════════════════════════════════════════════════════════
// 👑 HỆ THỐNG BẢN QUYỀN, HWID & THANH TOÁN VIETQR SEPAY
// ═════════════════════════════════════════════════════════════

const headerLicenseBadge = document.getElementById('headerLicenseBadge');
const headerLicenseIcon = document.getElementById('headerLicenseIcon');
const headerLicenseText = document.getElementById('headerLicenseText');
const licenseModal = document.getElementById('licenseModal');
const btnCloseLicenseModal = document.getElementById('btnCloseLicenseModal');

const modalHwidDisplay = document.getElementById('modalHwidDisplay');
const btnCopyHwid = document.getElementById('btnCopyHwid');
const modalStatusBadge = document.getElementById('modalStatusBadge');
const modalExpireDate = document.getElementById('modalExpireDate');
const btnSyncCloudLicense = document.getElementById('btnSyncCloudLicense');

const vietqrImage = document.getElementById('vietqrImage');
const qrSelectedPlanTitle = document.getElementById('qrSelectedPlanTitle');
const qrBankName = document.getElementById('qrBankName');
const qrAccountName = document.getElementById('qrAccountName');
const qrAccountNumber = document.getElementById('qrAccountNumber');
const qrAmountDisplay = document.getElementById('qrAmountDisplay');
const qrTransferContent = document.getElementById('qrTransferContent');
const btnCopyTransferContent = document.getElementById('btnCopyTransferContent');
const btnCheckPaymentNow = document.getElementById('btnCheckPaymentNow');

const btnSelectTierTrial = document.getElementById('btnSelectTierTrial');
const manualLicenseKeyInput = document.getElementById('manualLicenseKeyInput');
const btnSubmitManualKey = document.getElementById('btnSubmitManualKey');

// Pro Mandatory Module Selection DOM Elements
const proModuleRequiredModal = document.getElementById('proModuleRequiredModal');
const cardProChoiceEditor = document.getElementById('cardProChoiceEditor');
const cardProChoiceReview = document.getElementById('cardProChoiceReview');
const radioProMandatoryEditor = document.getElementById('radioProMandatoryEditor');
const radioProMandatoryReview = document.getElementById('radioProMandatoryReview');
const btnConfirmProModuleSelection = document.getElementById('btnConfirmProModuleSelection');

// currentLicenseState is declared at the top of app.js
currentLicenseState = {
    is_valid: false,
    status: 'CHECKING',
    tier: 'unlicensed',
    plan_name: 'Đang kiểm tra...',
    badge_class: 'badge-unlicensed',
    badge_text: '🔒 Kiểm tra bản quyền...',
    features: {}
};
let sepayPollingInterval = null;
let currentSelectedTier = 'vip';

// Startup Cloud Sync (1 lan duy nhat moi phien)
// Backend so sanh ket qua cloud voi .last_sync_state.dat roi tra ve
// was_upgraded / was_renewed. Frontend chi doc flag nay de toast.
let _startupSyncDone = false;

function isLicenseExpiryExtended(previousExpiry, latestExpiry) {
    const previousEpoch = Number(previousExpiry || 0);
    const latestEpoch = Number(latestExpiry || 0);
    if (previousEpoch && latestEpoch) return latestEpoch > previousEpoch;
    return Boolean(previousExpiry) && String(latestExpiry || '') > String(previousExpiry);
}

async function runStartupLicenseSync() {
    if (_startupSyncDone) return;
    _startupSyncDone = true;
    try {
        const res = await fetch('/api/license/sync_cloud', { method: 'POST' });
        if (!res.ok) return;
        const data = await res.json();
        const latestLicense = data && data.license;
        if (!latestLicense) return;
        currentLicenseState = latestLicense;
        updateLicenseUI(latestLicense);
        if (data.new_payment_detected) {
            if (data.was_upgraded) {
                showToast(`🎉 Gói ${latestLicense.plan_name || latestLicense.tier || ''} đã được nâng cấp thành công!`, 'success');
            } else if (data.was_renewed) {
                showToast(`🎉 Bản quyền ${latestLicense.plan_name || latestLicense.tier || ''} đã được gia hạn thành công!`, 'success');
            }
        }
    } catch (err) {
        console.debug('Startup license sync that bai:', err);
    }
}

async function fetchLicenseInfo(sync = false, retryCount = 0) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);

        const res = await fetch(`/api/license/info?sync=${sync}`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data && data.hwid) {
            localStorage.setItem('ams_cached_hwid', data.hwid);
        }
        currentLicenseState = data;
        updateLicenseUI(data);

        if (data.is_first_launch && data.tier === 'trial') {
            showToast('🎉 Chào mừng! Gói Dùng Thử 24h miễn phí đã được tự động kích hoạt để bạn bắt đầu trải nghiệm ngay.', 'success');
        }

        // Tự động kiểm tra hiển thị cam kết bản quyền lần đầu tiên khi cài đặt
        checkAndShowCopyrightDisclaimer();

        // Cache đã có thể hiển thị ngay; cloud được kiểm tra nhẹ sau đó mà
        // không làm chậm lần render đầu tiên.
        if (!sync) {
            // Delay nhe de UI render cache truoc, sau do moi check cloud
            setTimeout(runStartupLicenseSync, 1500);
        }

        return data;
    } catch (err) {
        if (retryCount < 2) {
            console.warn(`Lần tải thông tin bản quyền ${retryCount + 1} chưa thành công, thử lại sau 600ms...`, err);
            await new Promise(r => setTimeout(r, 600));
            return fetchLicenseInfo(sync, retryCount + 1);
        }
        console.warn('Lỗi tải thông tin bản quyền (kích hoạt chế độ bảo vệ offline):', err);
        const fallbackHwid = (currentLicenseState && currentLicenseState.hwid) || localStorage.getItem('ams_cached_hwid') || '';
        currentLicenseState = {
            is_valid: false,
            status: 'UNLICENSED',
            tier: 'unlicensed',
            plan_name: 'Chưa kích hoạt (Offline)',
            badge_class: 'badge-unlicensed',
            badge_text: '🔒 Chưa Kích Hoạt',
            can_activate_trial: true,
            features: {},
            hwid: fallbackHwid
        };
        updateLicenseUI(currentLicenseState);
        if (!fallbackHwid) {
            fetch('/api/license/hwid')
                .then(r => r.json())
                .then(hData => {
                    if (hData && hData.hwid) {
                        localStorage.setItem('ams_cached_hwid', hData.hwid);
                        if (currentLicenseState) currentLicenseState.hwid = hData.hwid;
                        if (modalHwidDisplay) modalHwidDisplay.textContent = hData.hwid;
                    }
                })
                .catch(() => {});
        }
        return null;
    }
}

// Gắn toàn cục để có thể gọi ở bất cứ đâu
export function checkFeaturePermission(featureName, featureTitle = "Tính năng này") {
    if (!currentLicenseState || !currentLicenseState.is_valid) {
        const isExpired = currentLicenseState && currentLicenseState.status === 'EXPIRED';
        const isTampered = currentLicenseState && currentLicenseState.status === 'CLOCK_TAMPERED';
        let msg = '';
        let title = '';

        if (isTampered) {
            title = '⚠️ Lỗi Đồng Hồ Hệ Thống';
            msg = currentLicenseState.clock_error || 'Phát hiện đồng hồ hệ thống bị chỉnh lùi về quá khứ! Vui lòng chỉnh lại ngày giờ chuẩn để tiếp tục.';
        } else if (isExpired) {
            title = '🔒 Bản Quyền Đã Hết Hạn';
            msg = `Bản quyền ${currentLicenseState.plan_name || ''} của bạn đã hết hạn (${currentLicenseState.expire_str || ''}). Vui lòng gia hạn gói để tiếp tục sử dụng ${featureTitle}!`;
        } else {
            title = '⚡ Yêu Cầu Kích Hoạt Bản Quyền';
            msg = `Bạn cần kích hoạt bản quyền hoặc bật gói Dùng Thử 24h để sử dụng ${featureTitle}.`;
        }

        showAlertModal({
            title: title,
            message: msg,
            theme: 'warning'
        }).then(() => {
            const licenseModal = document.getElementById('licenseModal');
            if (licenseModal) {
                licenseModal.style.display = 'flex';
                fetchLicenseInfo(false);
            }
        });
        return false;
    }

    if (featureName && currentLicenseState.features && !currentLicenseState.features[featureName]) {
        showAlertModal({
            title: '⭐ Nâng Cấp Gói Dịch Vụ',
            message: `${featureTitle} không thuộc quyền lợi của gói ${currentLicenseState.plan_name || ''}. Vui lòng nâng cấp lên gói cao hơn để sử dụng!`,
            theme: 'primary'
        }).then(() => {
            const licenseModal = document.getElementById('licenseModal');
            if (licenseModal) {
                licenseModal.style.display = 'flex';
                fetchLicenseInfo(false);
            }
        });
        return false;
    }

    return true;
}

if (typeof window !== 'undefined') {
    window.fetchLicenseInfo = fetchLicenseInfo;
    window.checkFeaturePermission = checkFeaturePermission;
}

function updateLicenseUI(info) {
    if (!info) return;

    // 1. Cập nhật Badge trên Header
    if (headerLicenseBadge && headerLicenseText && headerLicenseIcon) {
        headerLicenseBadge.className = `license-header-badge ${info.badge_class || 'badge-trial'}`;
        headerLicenseText.textContent = info.badge_text || 'Bản quyền';
        
        if (info.tier === 'admin') headerLicenseIcon.textContent = '🛡️';
        else if (info.tier === 'vip') headerLicenseIcon.textContent = '👑';
        else if (info.tier === 'pro') headerLicenseIcon.textContent = '⭐';
        else if (info.tier === 'yearly') headerLicenseIcon.textContent = '💎';
        else if (info.tier === 'trial') headerLicenseIcon.textContent = '⚡';
        else if (info.tier === 'expired') headerLicenseIcon.textContent = '🔒';
        else headerLicenseIcon.textContent = '🔑';
    }

    // 2. Cập nhật trong Modal
    const effectiveHwid = (info && info.hwid) || localStorage.getItem('ams_cached_hwid') || '';
    if (info && info.hwid) {
        localStorage.setItem('ams_cached_hwid', info.hwid);
    }
    if (modalHwidDisplay) {
        if (effectiveHwid) {
            modalHwidDisplay.textContent = effectiveHwid;
        } else {
            fetch('/api/license/hwid')
                .then(r => r.json())
                .then(d => {
                    if (d && d.hwid) {
                        modalHwidDisplay.textContent = d.hwid;
                        localStorage.setItem('ams_cached_hwid', d.hwid);
                    }
                })
                .catch(() => {
                    if (!modalHwidDisplay.textContent || modalHwidDisplay.textContent.includes('XXXX')) {
                        modalHwidDisplay.textContent = 'AMS-XXXX-XXXX-XXXX';
                    }
                });
        }
    }
    if (modalStatusBadge) {
        if (info.status === 'CLOCK_TAMPERED') {
            modalStatusBadge.textContent = '⚠️ Lỗi Đồng Hồ Hệ Thống (Phát hiện lùi giờ)';
            modalStatusBadge.style.color = '#ef4444';
        } else {
            modalStatusBadge.textContent = `${info.plan_name} (${info.status === 'ACTIVE' ? 'Đang hoạt động' : (info.status === 'EXPIRED' ? 'Đã hết hạn' : 'Chưa kích hoạt')})`;
            modalStatusBadge.style.color = info.status === 'ACTIVE' ? (info.tier === 'admin' ? '#ff3366' : (info.tier === 'vip' ? '#c084fc' : (info.tier === 'yearly' ? '#f59e0b' : '#38bdf8'))) : (info.status === 'EXPIRED' ? '#ef4444' : '#94a3b8');
        }
    }
    if (modalExpireDate) {
        if (info.status === 'CLOCK_TAMPERED') {
            modalExpireDate.textContent = info.clock_error || 'Vui lòng chỉnh lại ngày giờ chính xác hoặc kết nối Internet để đồng bộ!';
            modalExpireDate.style.color = '#f87171';
        } else {
            modalExpireDate.textContent = info.status === 'ACTIVE' ? `Hết hạn: ${info.expire_str}` : (info.status === 'EXPIRED' ? `Đã hết hạn lúc: ${info.expire_str}` : 'Chưa kích hoạt');
            modalExpireDate.style.color = '';
        }
    }

    // 3. Cập nhật trạng thái nút Dùng thử
    if (btnSelectTierTrial) {
        if (!info.can_activate_trial && info.status === 'ACTIVE' && info.tier === 'trial') {
            btnSelectTierTrial.textContent = 'Đang dùng thử';
            btnSelectTierTrial.disabled = true;
        } else if (!info.can_activate_trial) {
            btnSelectTierTrial.textContent = 'Đã hết hạn thử';
            btnSelectTierTrial.disabled = true;
        } else {
            btnSelectTierTrial.textContent = 'Kích hoạt Dùng Thử';
            btnSelectTierTrial.disabled = false;
        }
    }

    // 4. Nếu bản quyền Hết Hạn hoặc Chưa Hợp Lệ:
    // Tự động BẬT MODAL LÊN và KHÓA NÚT ĐÓNG (Bắt buộc mua / kích hoạt mới được vào app)
    if (!info.is_valid) {
        if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'none';
        openLicenseModal(currentSelectedTier || 'vip', true);
    } else {
        if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
    }

    // 5. Cập nhật giao diện Tabs cho Gói Pro (Khóa module không chọn)
    const tabEditor = document.querySelector('.nav-tab[data-target="viewEditor"]');
    const tabReview = document.querySelector('.nav-tab[data-target="viewReview"]');

    if (info && info.status === 'ACTIVE' && info.tier === 'pro') {
        const proMod = info.pro_selected_module;
        
        // Nếu gói Pro nhưng chưa chọn Module -> Tự động bật Modal bắt buộc chọn
        if (!proMod) {
            openProModuleRequiredModal('editor');
        }

        const updateNavTabBadge = (tabEl, defaultText, badgeHtml = '', opacity = '1', title = '') => {
            if (!tabEl) return;
            let labelEl = tabEl.querySelector('.nav-tab-label');
            if (!labelEl) {
                // If label was wiped by old code, restore icon and label structure
                const iconHtml = tabEl.getAttribute('data-target') === 'viewEditor'
                    ? '<span class="nav-tab-icon"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg></span>'
                    : '<span class="nav-tab-icon"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="m2 8 20 0"></path><path d="m6 4 3 4"></path><path d="m11 4 3 4"></path><path d="m16 4 3 4"></path><polygon points="10 11 15 14 10 17 10 11" fill="currentColor"></polygon></svg></span>';
                tabEl.innerHTML = iconHtml + `<span class="nav-tab-label">${defaultText}</span>`;
                labelEl = tabEl.querySelector('.nav-tab-label');
            }
            if (labelEl) {
                labelEl.innerHTML = badgeHtml ? `${defaultText} ${badgeHtml}` : defaultText;
            }
            tabEl.style.opacity = opacity;
            if (title) tabEl.title = title;
        };

        if (tabEditor) {
            if (proMod === 'editor') {
                updateNavTabBadge(tabEditor, 'Biên tập phim', '<span style="font-size: 10px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 2px 6px; border-radius: 8px; margin-left: 4px; font-weight: 700;">Đang dùng</span>', '1', 'Module Biên tập phim (Đang chọn)');
            } else if (proMod === 'review') {
                updateNavTabBadge(tabEditor, 'Biên tập phim', '<span style="font-size: 11px; margin-left: 4px;">🔒</span>', '0.55', 'Bị khóa - Gói Pro đã chọn Review Phim (Nâng cấp VIP để mở khóa cả 2)');
            } else {
                updateNavTabBadge(tabEditor, 'Biên tập phim', '<span style="font-size: 11px; margin-left: 4px;">🔒</span>', '0.55', 'Chưa chọn module cho Gói Pro');
            }
        }
        if (tabReview) {
            if (proMod === 'review') {
                updateNavTabBadge(tabReview, 'Review Phim', '<span style="font-size: 10px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 2px 6px; border-radius: 8px; margin-left: 4px; font-weight: 700;">Đang dùng</span>', '1', 'Module Review Phim (Đang chọn)');
            } else if (proMod === 'editor') {
                updateNavTabBadge(tabReview, 'Review Phim', '<span style="font-size: 11px; margin-left: 4px;">🔒</span>', '0.55', 'Bị khóa - Gói Pro đã chọn Biên tập phim (Nâng cấp VIP để mở khóa cả 2)');
            } else {
                updateNavTabBadge(tabReview, 'Review Phim', '<span style="font-size: 11px; margin-left: 4px;">🔒</span>', '0.55', 'Chưa chọn module cho Gói Pro');
            }
        }

        // Tự động chuyển tab đang xem nếu đang đứng ở tab bị khóa
        const activeTab = document.querySelector('.header-tabs .nav-tab.active');
        const activeTarget = activeTab ? activeTab.getAttribute('data-target') : '';
        if (proMod === 'review' && activeTarget === 'viewEditor') {
            if (tabReview) tabReview.click();
        } else if (proMod === 'editor' && activeTarget === 'viewReview') {
            if (tabEditor) tabEditor.click();
        }
    } else {
        const resetNavTab = (tabEl, defaultText, defaultTitle, iconHtml) => {
            if (!tabEl) return;
            let labelEl = tabEl.querySelector('.nav-tab-label');
            if (!labelEl) {
                tabEl.innerHTML = iconHtml + `<span class="nav-tab-label">${defaultText}</span>`;
            } else {
                labelEl.innerHTML = defaultText;
            }
            tabEl.style.opacity = '1';
            tabEl.title = defaultTitle;
        };
        const editorIcon = '<span class="nav-tab-icon"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg></span>';
        const reviewIcon = '<span class="nav-tab-icon"><svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="m2 8 20 0"></path><path d="m6 4 3 4"></path><path d="m11 4 3 4"></path><path d="m16 4 3 4"></path><polygon points="10 11 15 14 10 17 10 11" fill="currentColor"></polygon></svg></span>';
        
        resetNavTab(tabEditor, 'Biên tập phim', 'Biên tập phim & Trích xuất phụ đề', editorIcon);
        resetNavTab(tabReview, 'Review Phim', 'Studio Review Phim Tự Động (AI Auto-Edit)', reviewIcon);
    }

    // 6. Tự động nạp và bảo vệ API Keys cho Gói VIP / Gói Năm (Chống copy / xem trộm key)
    const isVipTier = info && info.status === 'ACTIVE' && (info.tier === 'vip' || info.tier === 'yearly');
    const inputIds = ['openaiKey', 'openSpeakerApiKey', 'geminiApiKey'];
    
    if (isVipTier) {
        inputIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                const hasCustomKey = el.value && !el.value.startsWith('•') && !el.value.includes('[Bản Quyền VIP');
                if (!hasCustomKey) {
                    el.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                    el.readOnly = true;
                    el.type = 'password';
                    el.style.background = 'rgba(168, 85, 247, 0.08)';
                    el.style.borderColor = 'rgba(168, 85, 247, 0.4)';
                    el.style.color = '#c084fc';
                    el.style.cursor = 'not-allowed';
                    el.style.userSelect = 'none';
                    el.style.webkitUserSelect = 'none';
                    if (typeof el.setAttribute === 'function') {
                        el.setAttribute('oncopy', 'return false;');
                        el.setAttribute('oncut', 'return false;');
                        el.setAttribute('oncontextmenu', 'return false;');
                    }

                    const parent = (typeof el.closest === 'function') ? el.closest('div') : el.parentElement;
                    const label = parent && typeof parent.querySelector === 'function' ? parent.querySelector('label') : null;
                    if (label && typeof label.querySelector === 'function' && !label.querySelector('.badge-vip-key') && typeof document.createElement === 'function') {
                        const badge = document.createElement('span');
                        badge.className = 'badge-vip-key';
                        badge.innerHTML = '👑 Đã Kích Hoạt VIP';
                        badge.style.cssText = 'font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(168, 85, 247, 0.25); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.5); margin-left: 6px; font-weight: 600;';
                        label.appendChild(badge);
                    }
                }
            }
        });
        appendLog('⭐ [Bản quyền VIP] Đã kích hoạt chế độ bảo vệ an toàn API Bản Quyền!', 'info');
    } else {
        inputIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                if (el.value && el.value.includes('[Bản Quyền VIP')) {
                    el.value = '';
                }
                el.readOnly = false;
                el.style.background = '';
                el.style.borderColor = '';
                el.style.color = '';
                el.style.cursor = '';
                el.style.userSelect = '';
                el.style.webkitUserSelect = '';
                if (typeof el.removeAttribute === 'function') {
                    el.removeAttribute('oncopy');
                    el.removeAttribute('oncut');
                    el.removeAttribute('oncontextmenu');
                }
            }
            const parent = (el && typeof el.closest === 'function') ? el.closest('div') : (el ? el.parentElement : null);
            const label = parent && typeof parent.querySelector === 'function' ? parent.querySelector('label') : null;
            const badge = label && typeof label.querySelector === 'function' ? label.querySelector('.badge-vip-key') : null;
            if (badge && typeof badge.remove === 'function') badge.remove();
        });
        // Nạp lại API keys cá nhân nếu ô chưa có
        loadApiKeys();
    }
}


async function loadVietQR(tier = 'vip') {
    currentSelectedTier = tier;
    try {
        const res = await fetch(`/api/license/qr_info?tier=${tier}`);
        if (!res.ok) return;
        const data = await res.json();

        if (vietqrImage) vietqrImage.src = data.qr_image_url;
        if (qrBankName) qrBankName.textContent = data.bank_code;
        if (qrAccountName) qrAccountName.textContent = data.bank_account_name;
        if (qrAccountNumber) qrAccountNumber.textContent = data.bank_account;
        if (qrAmountDisplay) qrAmountDisplay.textContent = data.amount_formatted;
        if (qrTransferContent) qrTransferContent.textContent = data.transfer_content;

        const tierNames = {
            'test': '🧪 GÓI THỬ NGHIỆM SEPAY (5.000đ)',
            'pro': '⭐ GÓI PRO (300.000đ / tháng)',
            'vip': '👑 GÓI VIP TOÀN NĂNG (500.000đ / tháng)',
            'yearly': '💎 GÓI 1 NĂM TIẾT KIỆM (3.990.000đ / 12 tháng)'
        };
        if (qrSelectedPlanTitle) qrSelectedPlanTitle.textContent = tierNames[tier] || `GÓI ${tier.toUpperCase()}`;

        // Highlight pricing card
        document.querySelectorAll('.pricing-card').forEach(c => {
            c.classList.remove('active-selected');
            if (c.dataset.tier === tier) c.classList.add('active-selected');
        });
    } catch (err) {
        console.error('Lỗi tạo mã VietQR:', err);
    }
}

let modalOpenedLicenseExpiry = null;
let modalOpenedLicensePlan = null;
let modalOpenedLicenseStatus = null;

function openLicenseModal(defaultTier = 'vip', isLocked = false) {
    if (licenseModal) {
        modalOpenedLicenseExpiry = currentLicenseState ? (currentLicenseState.expire_epoch || currentLicenseState.expire_str || '') : '';
        modalOpenedLicensePlan = currentLicenseState ? (currentLicenseState.tier || '') : '';
        modalOpenedLicenseStatus = currentLicenseState ? currentLicenseState.status : 'UNLICENSED';

        // Đảm bảo HWID luôn hiển thị ngay lập tức khi mở modal, không bị kẹt XXXX
        if (modalHwidDisplay && (!modalHwidDisplay.textContent || modalHwidDisplay.textContent.includes('XXXX'))) {
            const cachedHwid = localStorage.getItem('ams_cached_hwid') || (currentLicenseState && currentLicenseState.hwid);
            if (cachedHwid) {
                modalHwidDisplay.textContent = cachedHwid;
            } else {
                fetch('/api/license/hwid')
                    .then(r => r.json())
                    .then(d => {
                        if (d && d.hwid) {
                            modalHwidDisplay.textContent = d.hwid;
                            localStorage.setItem('ams_cached_hwid', d.hwid);
                        }
                    })
                    .catch(() => {});
            }
        }

        licenseModal.style.display = 'flex';
        loadVietQR(defaultTier);

        // Chỉ bắt đầu polling quét giao dịch SePay nếu máy thực sự CHƯA CÓ BẢN QUYỀN HỢP LỆ
        // hoặc đang dùng thử (cần thanh toán để nâng lên VIP/Pro/Yearly).
        // Nếu đang CHECKING hoặc đã có bản quyền hợp lệ (Admin, VIP, Pro, Yearly active),
        // tuyệt đối không tự động polling để tránh spam request hoặc nổ chúc mừng giả mạo.
        const isAlreadyActive = currentLicenseState && currentLicenseState.is_valid && currentLicenseState.status === 'ACTIVE' && currentLicenseState.tier !== 'trial';
        const isChecking = !currentLicenseState || currentLicenseState.status === 'CHECKING';
        if (!isAlreadyActive && !isChecking) {
            startSepayPolling();
        } else {
            stopSepayPolling();
        }

        if (isLocked || (currentLicenseState && !currentLicenseState.is_valid)) {
            if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'none';
        } else {
            if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
        }
    }
}

function closeLicenseModal() {
    if (currentLicenseState && !currentLicenseState.is_valid) {
        showToast('⚠️ Vui lòng gia hạn hoặc kích hoạt bản quyền để tiếp tục sử dụng ứng dụng!', 'warning');
        return;
    }
    if (licenseModal) {
        licenseModal.style.display = 'none';
        stopSepayPolling();
    }
}

function startSepayPolling() {
    stopSepayPolling();

    // Guard an toàn tối thượng: chỉ chạy polling khi máy thực sự cần kích hoạt/gia hạn (unlicensed, expired, trial).
    // Tuyệt đối không chạy polling khi đang ở trạng thái CHECKING (đang nạp info ban đầu)
    // hoặc khi đã có bản quyền non-trial active (Admin, VIP, Pro, Yearly).
    if (!currentLicenseState || currentLicenseState.status === 'CHECKING') return;
    if (currentLicenseState.is_valid && currentLicenseState.status === 'ACTIVE' && currentLicenseState.tier !== 'trial') return;

    sepayPollingInterval = setInterval(async () => {
        try {
            // 1. Kiểm tra trực tiếp qua SePay API (Chỉ chúc mừng khi backend xác nhận có giao dịch thanh toán mới)
            const sepayRes = await fetch('/api/license/check_sepay_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: currentSelectedTier || 'vip' })
            });
            const sepayData = await sepayRes.json();
            if (sepayData.success && sepayData.new_payment_detected && sepayData.license && sepayData.license.status === 'ACTIVE') {
                currentLicenseState = sepayData.license;
                updateLicenseUI(sepayData.license);
                stopSepayPolling();
                if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
                if (licenseModal) licenseModal.style.display = 'none';
                showLicenseSuccessCelebration(sepayData.license);
                showToast(`🎉 ${sepayData.message || 'Thanh toán thành công!'}`, 'success');
                return;
            }

            // 2. Kiểm tra đồng bộ qua Google Sheet (Chỉ chúc mừng khi backend xác nhận có sự kiện thay đổi mới)
            const res = await fetch('/api/license/sync_cloud', { method: 'POST' });
            const data = await res.json();
            if (data.success && data.new_payment_detected && data.license && data.license.status === 'ACTIVE') {
                currentLicenseState = data.license;
                updateLicenseUI(data.license);
                stopSepayPolling();
                if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
                if (licenseModal) licenseModal.style.display = 'none';
                showLicenseSuccessCelebration(data.license);
                const msg = data.was_renewed
                    ? `🎉 Bản quyền ${data.license.plan_name || ''} đã được gia hạn thành công!`
                    : `🎉 Thanh toán thành công! Gói ${data.license.plan_name || ''} đã được kích hoạt!`;
                showToast(msg, 'success');
            }
        } catch (e) {}
    }, 4000);
}

function stopSepayPolling() {
    if (sepayPollingInterval) {
        clearInterval(sepayPollingInterval);
        sepayPollingInterval = null;
    }
}

// Event Listeners
if (headerLicenseBadge) {
    headerLicenseBadge.addEventListener('click', () => openLicenseModal('vip'));
}
if (btnCloseLicenseModal) {
    btnCloseLicenseModal.addEventListener('click', closeLicenseModal);
}
if (licenseModal) {
    licenseModal.addEventListener('click', (e) => {
        if (e.target === licenseModal) {
            if (currentLicenseState && !currentLicenseState.is_valid) {
                return; // Chặn đóng khi click bên ngoài nếu hết hạn
            }
            closeLicenseModal();
        }
    });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' || e.key === 'Esc') {
            // Khóa cứng Escape khi modal bắt buộc chọn module Gói Pro đang mở
            if (proModuleRequiredModal && proModuleRequiredModal.style.display === 'flex') {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
            if (licenseModal && licenseModal.style.display === 'flex') {
                if (currentLicenseState && !currentLicenseState.is_valid) {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                }
                closeLicenseModal();
            }
        }
    }, true);
}

// Copy HWID
if (btnCopyHwid) {
    btnCopyHwid.addEventListener('click', () => {
        const hwid = modalHwidDisplay ? modalHwidDisplay.textContent.trim() : '';
        if (hwid) {
            navigator.clipboard.writeText(hwid);
            showToast('📋 Đã sao chép mã máy (HWID) vào bộ nhớ tạm!', 'success');
        }
    });
}

// Copy Transfer Content
if (btnCopyTransferContent) {
    btnCopyTransferContent.addEventListener('click', () => {
        const content = qrTransferContent ? qrTransferContent.textContent.trim() : '';
        if (content) {
            navigator.clipboard.writeText(content);
            showToast(`📋 Đã sao chép nội dung: "${content}"`, 'success');
        }
    });
}

// Select Tier Buttons
document.querySelectorAll('.btn-tier-select').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tier = e.currentTarget.dataset.tier || 'vip';
        loadVietQR(tier);
        const qrSec = document.getElementById('vietqrPaymentSection');
        if (qrSec) qrSec.scrollIntoView({ behavior: 'smooth' });
    });
});


// Activate Trial
if (btnSelectTierTrial) {
    btnSelectTierTrial.addEventListener('click', async () => {
        btnSelectTierTrial.disabled = true;
        btnSelectTierTrial.textContent = 'Đang kích hoạt...';
        try {
            const res = await fetch('/api/license/activate_trial', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_name: 'Khách Dùng Thử' })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message || 'Kích hoạt dùng thử thành công!', 'success');
                updateLicenseUI(data.license);
            } else {
                showToast(data.error || 'Không thể kích hoạt dùng thử!', 'error');
            }
        } catch (err) {
            showToast('Lỗi kết nối khi kích hoạt dùng thử: ' + err.message, 'error');
        } finally {
            fetchLicenseInfo();
        }
    });
}

// Check Payment Now Button (Kiểm tra thanh toán SePay API & Cloud)
if (btnCheckPaymentNow) {
    btnCheckPaymentNow.addEventListener('click', async () => {
        btnCheckPaymentNow.disabled = true;
        btnCheckPaymentNow.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
            <span>🔍 Đang quét giao dịch ngân hàng từ SePay...</span>
        `;
        try {
            // 1. Kiểm tra trực tiếp qua SePay API
            const sepayRes = await fetch('/api/license/check_sepay_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: currentSelectedTier || 'vip' })
            });
            const sepayData = await sepayRes.json();
            if (sepayData.success && sepayData.new_payment_detected && sepayData.license) {
                currentLicenseState = sepayData.license;
                updateLicenseUI(sepayData.license);
                if (licenseModal) licenseModal.style.display = 'none';
                showLicenseSuccessCelebration(sepayData.license);
                showToast(`🎉 Chúc mừng! Đã nhận được thanh toán thành công! Gói ${sepayData.license.plan_name} đã được kích hoạt!`, 'success');
                return;
            }

            // 2. Nếu SePay API chưa thấy, kiểm tra qua Google Sheet sync
            const res = await fetch('/api/license/sync_cloud', { method: 'POST' });
            const data = await res.json();
            if (data.success && data.new_payment_detected && data.license && data.license.status === 'ACTIVE') {
                currentLicenseState = data.license;
                updateLicenseUI(data.license);
                if (licenseModal) licenseModal.style.display = 'none';
                showLicenseSuccessCelebration(data.license);
                const msg = data.was_renewed
                    ? `🎉 Bản quyền ${data.license.plan_name || ''} đã được gia hạn thành công!`
                    : `🎉 Chúc mừng! Gói ${data.license.plan_name || ''} đã được kích hoạt thành công!`;
                showToast(msg, 'success');
                return;
            }

            // Nếu không có thanh toán mới
            showToast('⚠️ Chưa nhận được tiền: Hệ thống đã quét SePay nhưng chưa tìm thấy giao dịch chuyển khoản mới khớp với mã máy. Nếu bạn vừa chuyển khoản, vui lòng đợi 15-30 giây để ngân hàng xử lý rồi bấm lại nhé!', 'warning');
        } catch (err) {
            showToast('Lỗi kiểm tra giao dịch: ' + err.message, 'error');
        } finally {
            btnCheckPaymentNow.disabled = false;
            btnCheckPaymentNow.innerHTML = `
                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                <span>Tôi Đã Chuyển Khoản Xong</span>
            `;
            fetchLicenseInfo();
        }
    });
}

// Sync Cloud Button
if (btnSyncCloudLicense) {
    btnSyncCloudLicense.addEventListener('click', async () => {
        btnSyncCloudLicense.disabled = true;
        try {
            const res = await fetch('/api/license/sync_cloud', { method: 'POST' });
            const data = await res.json();
            if (data.license) {
                currentLicenseState = data.license;
                updateLicenseUI(data.license);
            }
            showToast(data.message || 'Đã đồng bộ thông tin bản quyền!', data.success ? 'success' : 'info');
        } catch (err) {
            showToast('Lỗi đồng bộ: ' + err.message, 'error');
        } finally {
            btnSyncCloudLicense.disabled = false;
            fetchLicenseInfo();
        }
    });
}

// Submit Manual License Key
if (btnSubmitManualKey) {
    btnSubmitManualKey.addEventListener('click', async () => {
        const key = manualLicenseKeyInput ? manualLicenseKeyInput.value.trim() : '';
        if (!key) {
            showToast('Vui lòng nhập mã kích hoạt!', 'warning');
            return;
        }
        btnSubmitManualKey.disabled = true;
        try {
            const res = await fetch('/api/license/activate_key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key })
            });
            const data = await res.json();
            if (data.success && data.license) {
                updateLicenseUI(data.license);
                if (manualLicenseKeyInput) manualLicenseKeyInput.value = '';
                showLicenseSuccessCelebration(data.license);
            } else {
                showToast(data.error || 'Mã kích hoạt không hợp lệ!', 'error');
            }
        } catch (err) {
            showToast('Lỗi kết nối khi kích hoạt: ' + err.message, 'error');
        } finally {
            btnSubmitManualKey.disabled = false;
        }
    });
}

// ====== FIREWORKS & CELEBRATION ANIMATION ENGINE ======
class CelebrationFX {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = (this.canvas && typeof this.canvas.getContext === 'function') ? this.canvas.getContext('2d') : null;
        this.particles = [];
        this.fireworks = [];
        this.animationId = null;
        this.isRunning = false;
        this.resize = this.resize.bind(this);
        window.addEventListener('resize', this.resize);
    }

    resize() {
        if (!this.canvas) return;
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    start(durationMs = 6000) {
        if (!this.canvas) return;
        this.resize();
        this.canvas.style.display = 'block';
        this.particles = [];
        this.fireworks = [];
        this.isRunning = true;

        const colors = ['#f59e0b', '#fbbf24', '#38bdf8', '#06b6d4', '#ec4899', '#a855f7', '#10b981', '#ffffff'];

        // Spawn periodic fireworks
        const spawnInterval = setInterval(() => {
            if (!this.isRunning) {
                clearInterval(spawnInterval);
                return;
            }
            // Launch 2-3 fireworks at random bottom locations
            for (let i = 0; i < 2; i++) {
                const startX = Math.random() * (this.canvas.width * 0.8) + this.canvas.width * 0.1;
                const targetX = startX + (Math.random() * 200 - 100);
                const targetY = Math.random() * (this.canvas.height * 0.4) + this.canvas.height * 0.1;
                this.fireworks.push({
                    x: startX,
                    y: this.canvas.height,
                    targetX,
                    targetY,
                    speed: 12 + Math.random() * 5,
                    angle: Math.atan2(targetY - this.canvas.height, targetX - startX),
                    color: colors[Math.floor(Math.random() * colors.length)]
                });
            }

            // Spawn floating confetti from top
            for (let i = 0; i < 15; i++) {
                this.particles.push({
                    x: Math.random() * this.canvas.width,
                    y: -10,
                    vx: (Math.random() - 0.5) * 3,
                    vy: 2 + Math.random() * 3,
                    size: 6 + Math.random() * 6,
                    color: colors[Math.floor(Math.random() * colors.length)],
                    rotation: Math.random() * 360,
                    vRot: (Math.random() - 0.5) * 8,
                    alpha: 1,
                    isConfetti: true
                });
            }
        }, 280);

        this.animate();

        setTimeout(() => {
            this.isRunning = false;
            clearInterval(spawnInterval);
            setTimeout(() => {
                this.stop();
            }, 2500);
        }, durationMs);
    }

    animate() {
        if (!this.canvas || !this.ctx) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Update & draw fireworks rockets
        for (let i = this.fireworks.length - 1; i >= 0; i--) {
            const f = this.fireworks[i];
            const vx = Math.cos(f.angle) * f.speed;
            const vy = Math.sin(f.angle) * f.speed;
            f.x += vx;
            f.y += vy;

            this.ctx.beginPath();
            this.ctx.arc(f.x, f.y, 3, 0, Math.PI * 2);
            this.ctx.fillStyle = f.color;
            this.ctx.shadowBlur = 10;
            this.ctx.shadowColor = f.color;
            this.ctx.fill();
            this.ctx.shadowBlur = 0;

            if (f.y <= f.targetY) {
                // Explode into 45 glittering spark particles
                const colors = ['#f59e0b', '#fbbf24', '#38bdf8', '#06b6d4', '#ec4899', '#a855f7', '#10b981', '#ffffff'];
                const count = 45;
                for (let j = 0; j < count; j++) {
                    const angle = (Math.PI * 2 / count) * j + (Math.random() * 0.2);
                    const speed = 2 + Math.random() * 7;
                    this.particles.push({
                        x: f.x,
                        y: f.y,
                        vx: Math.cos(angle) * speed,
                        vy: Math.sin(angle) * speed,
                        size: 2.5 + Math.random() * 2.5,
                        color: colors[Math.floor(Math.random() * colors.length)],
                        alpha: 1,
                        decay: 0.015 + Math.random() * 0.015,
                        gravity: 0.08,
                        isConfetti: false
                    });
                }
                this.fireworks.splice(i, 1);
            }
        }

        // Update & draw particles
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];
            p.x += p.vx;
            p.y += p.vy;

            if (p.isConfetti) {
                p.rotation += p.vRot;
                p.vy += 0.02;
                if (p.y > this.canvas.height) {
                    this.particles.splice(i, 1);
                    continue;
                }
                this.ctx.save();
                this.ctx.translate(p.x, p.y);
                this.ctx.rotate(p.rotation * Math.PI / 180);
                this.ctx.fillStyle = p.color;
                this.ctx.globalAlpha = p.alpha;
                this.ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
                this.ctx.restore();
            } else {
                p.vy += p.gravity;
                p.alpha -= p.decay;
                if (p.alpha <= 0) {
                    this.particles.splice(i, 1);
                    continue;
                }
                this.ctx.beginPath();
                this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                this.ctx.fillStyle = p.color;
                this.ctx.globalAlpha = p.alpha;
                this.ctx.shadowBlur = 6;
                this.ctx.shadowColor = p.color;
                this.ctx.fill();
                this.ctx.shadowBlur = 0;
            }
        }

        if (this.isRunning || this.fireworks.length > 0 || this.particles.length > 0) {
            this.animationId = requestAnimationFrame(() => this.animate());
        }
    }

    stop() {
        this.isRunning = false;
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) {
            this.canvas.style.display = 'none';
            if (this.ctx) this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
    }
}

const celebrationFX = new CelebrationFX('celebrationCanvas');

function showLicenseSuccessCelebration(licenseData) {
    if (!licenseData) return;

    const modal = document.getElementById('licenseSuccessModal');
    const planEl = document.getElementById('successCelebrationPlan');
    const expireEl = document.getElementById('successCelebrationExpire');
    const daysEl = document.getElementById('successCelebrationDays');
    const planMiniEl = document.getElementById('successCelebrationPlanNameMini');
    const iconEl = document.getElementById('successCelebrationIcon');

    if (planEl) planEl.textContent = licenseData.plan_name || 'Gói VIP Toàn Năng';
    if (planMiniEl) planMiniEl.textContent = licenseData.plan_name || 'Gói VIP';
    if (expireEl) expireEl.textContent = licenseData.expire_str ? `Đến ngày ${licenseData.expire_str}` : 'Đang hoạt động';
    if (daysEl) daysEl.textContent = `Còn ${licenseData.days_left || 30} ngày`;

    if (iconEl) {
        if (licenseData.tier === 'yearly') iconEl.textContent = '💎';
        else if (licenseData.tier === 'vip') iconEl.textContent = '👑';
        else if (licenseData.tier === 'pro') iconEl.textContent = '⭐';
        else iconEl.textContent = '⚡';
    }

    // Đóng modal bản quyền chính nếu đang mở
    const licModal = document.getElementById('licenseModal');
    if (licModal) licModal.classList.remove('active');

    // Mở popup chúc mừng
    if (modal) modal.classList.add('active');

    // Bắn pháo hoa rực rỡ 6 giây!
    celebrationFX.start(6000);
}

// Close Celebration Modal Events
const closeLicenseSuccessBtn = document.getElementById('closeLicenseSuccessBtn');
const btnStartUsingLicense = document.getElementById('btnStartUsingLicense');
const licenseSuccessModal = document.getElementById('licenseSuccessModal');

if (closeLicenseSuccessBtn) {
    closeLicenseSuccessBtn.addEventListener('click', () => {
        if (licenseSuccessModal) licenseSuccessModal.classList.remove('active');
        celebrationFX.stop();
        if (currentLicenseState && currentLicenseState.tier === 'pro' && !currentLicenseState.pro_selected_module) {
            openProModuleRequiredModal('editor');
        }
    });
}

if (btnStartUsingLicense) {
    btnStartUsingLicense.addEventListener('click', () => {
        if (licenseSuccessModal) licenseSuccessModal.classList.remove('active');
        celebrationFX.stop();
        if (currentLicenseState && currentLicenseState.tier === 'pro' && !currentLicenseState.pro_selected_module) {
            openProModuleRequiredModal('editor');
        }
    });
}

if (licenseSuccessModal) {
    licenseSuccessModal.addEventListener('click', (e) => {
        if (e.target === licenseSuccessModal) {
            licenseSuccessModal.classList.remove('active');
            celebrationFX.stop();
            if (currentLicenseState && currentLicenseState.tier === 'pro' && !currentLicenseState.pro_selected_module) {
                openProModuleRequiredModal('editor');
            }
        }
    });
}

// ═════════════════════════════════════════════════════════════
// ⚠️ COPYRIGHT DISCLAIMER & COMMITMENT MODAL CONTROLLER
// ═════════════════════════════════════════════════════════════

const modalCopyrightDisclaimer = document.getElementById('modalCopyrightDisclaimer');
const chkAgreeCopyrightDisclaimer = document.getElementById('chkAgreeCopyrightDisclaimer');
const btnAcceptCopyrightDisclaimer = document.getElementById('btnAcceptCopyrightDisclaimer');
const btnRejectCopyrightDisclaimer = document.getElementById('btnRejectCopyrightDisclaimer');

export async function checkAndShowCopyrightDisclaimer() {
    if (!modalCopyrightDisclaimer) return;

    // 1. Kiểm tra localStorage trước (nhanh nhất)
    if (localStorage.getItem('ams_copyright_disclaimer_accepted') === 'true') {
        return;
    }

    // 2. Kiểm tra từ server license info (lưu vĩnh viễn trên máy)
    if (currentLicenseState && currentLicenseState.disclaimer_accepted) {
        localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');
        return;
    }

    // 3. Nếu cả 2 chưa có (vd: mở tab mới, profile WebView2 sạch), kiểm tra đa tầng trực tiếp qua backend (Windows Registry / Marker file)
    try {
        const res = await fetch('/api/license/disclaimer_status');
        if (res.ok) {
            const data = await res.json();
            if (data && data.disclaimer_accepted) {
                localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');
                if (currentLicenseState) currentLicenseState.disclaimer_accepted = true;
                return;
            }
        }
    } catch (e) {}

    if (chkAgreeCopyrightDisclaimer) chkAgreeCopyrightDisclaimer.checked = false;
    if (btnAcceptCopyrightDisclaimer) {
        btnAcceptCopyrightDisclaimer.disabled = true;
        btnAcceptCopyrightDisclaimer.style.background = '#334155';
        btnAcceptCopyrightDisclaimer.style.color = '#64748b';
        btnAcceptCopyrightDisclaimer.style.cursor = 'not-allowed';
        btnAcceptCopyrightDisclaimer.style.boxShadow = 'none';
    }
    modalCopyrightDisclaimer.style.display = 'flex';
}

if (typeof window !== 'undefined') {
    window.checkAndShowCopyrightDisclaimer = checkAndShowCopyrightDisclaimer;
}

// Bắt sự kiện tích chọn checkbox cam kết
if (chkAgreeCopyrightDisclaimer && btnAcceptCopyrightDisclaimer) {
    chkAgreeCopyrightDisclaimer.addEventListener('change', (e) => {
        if (e.target.checked) {
            btnAcceptCopyrightDisclaimer.disabled = false;
            btnAcceptCopyrightDisclaimer.style.background = 'linear-gradient(135deg, #0ea5e9, #06b6d4)';
            btnAcceptCopyrightDisclaimer.style.color = '#ffffff';
            btnAcceptCopyrightDisclaimer.style.cursor = 'pointer';
            btnAcceptCopyrightDisclaimer.style.boxShadow = '0 4px 18px rgba(6, 182, 212, 0.4)';
        } else {
            btnAcceptCopyrightDisclaimer.disabled = true;
            btnAcceptCopyrightDisclaimer.style.background = '#334155';
            btnAcceptCopyrightDisclaimer.style.color = '#64748b';
            btnAcceptCopyrightDisclaimer.style.cursor = 'not-allowed';
            btnAcceptCopyrightDisclaimer.style.boxShadow = 'none';
        }
    });
}

// Bắt sự kiện bấm "Tôi đồng ý và tiếp tục"
if (btnAcceptCopyrightDisclaimer) {
    btnAcceptCopyrightDisclaimer.addEventListener('click', () => {
        if (!chkAgreeCopyrightDisclaimer || !chkAgreeCopyrightDisclaimer.checked) return;

        localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');
        localStorage.setItem('ams_disclaimer_accepted_at', new Date().toISOString());
        if (currentLicenseState) {
            currentLicenseState.disclaimer_accepted = true;
        }
        fetch('/api/license/accept_disclaimer', { method: 'POST' }).catch(() => {});
        if (typeof updateSettingsDisclaimerStatus === 'function') {
            updateSettingsDisclaimerStatus();
        }

        if (modalCopyrightDisclaimer) modalCopyrightDisclaimer.style.display = 'none';
        showToast('✅ Bạn đã xác nhận cam kết bản quyền & miễn trừ trách nhiệm thành công!', 'success');

        // Nếu là gói Pro chưa chọn module thì mở tiếp modal chọn module
        if (currentLicenseState && currentLicenseState.tier === 'pro' && !currentLicenseState.pro_selected_module) {
            openProModuleRequiredModal('editor');
        } else if (currentLicenseState && currentLicenseState.is_valid && currentLicenseState.tier !== 'trial' && currentLicenseState.tier !== 'unlicensed') {
            showToast('🚀 Chúc bạn tạo ra những video triệu view tuyệt vời!', 'success');
        }
    });
}

// Bắt sự kiện bấm "Không đồng ý – Thoát"
if (btnRejectCopyrightDisclaimer) {
    btnRejectCopyrightDisclaimer.addEventListener('click', async () => {
        await showAlertModal({
            title: '⚠️ Yêu Cầu Cam Kết Bắt Buộc',
            message: 'Để sử dụng các tính năng chỉnh sửa video và tạo nội dung review phim bằng AI của ứng dụng, Bạn bắt buộc phải đọc kỹ và tích chọn xác nhận cam kết miễn trừ trách nhiệm về bản quyền.',
            theme: 'warning'
        });
    });
}

// ═════════════════════════════════════════════════════════════
// ⭐ PRO MANDATORY MODULE SELECTION MODAL CONTROLLER
// ═════════════════════════════════════════════════════════════

function selectProMandatoryCard(mod) {
    if (mod === 'review') {
        if (radioProMandatoryReview) radioProMandatoryReview.checked = true;
        if (cardProChoiceReview) {
            cardProChoiceReview.style.borderColor = '#c084fc';
            cardProChoiceReview.style.background = 'rgba(15, 23, 42, 0.9)';
            cardProChoiceReview.style.boxShadow = '0 0 25px rgba(192, 132, 252, 0.3)';
        }
        if (cardProChoiceEditor) {
            cardProChoiceEditor.style.borderColor = '#334155';
            cardProChoiceEditor.style.background = 'rgba(15, 23, 42, 0.6)';
            cardProChoiceEditor.style.boxShadow = 'none';
        }
    } else {
        if (radioProMandatoryEditor) radioProMandatoryEditor.checked = true;
        if (cardProChoiceEditor) {
            cardProChoiceEditor.style.borderColor = '#38bdf8';
            cardProChoiceEditor.style.background = 'rgba(15, 23, 42, 0.9)';
            cardProChoiceEditor.style.boxShadow = '0 0 25px rgba(56, 189, 248, 0.3)';
        }
        if (cardProChoiceReview) {
            cardProChoiceReview.style.borderColor = '#334155';
            cardProChoiceReview.style.background = 'rgba(15, 23, 42, 0.6)';
            cardProChoiceReview.style.boxShadow = 'none';
        }
    }
}

export function openProModuleRequiredModal(defaultMod = 'editor') {
    if (proModuleRequiredModal) {
        proModuleRequiredModal.style.display = 'flex';
        selectProMandatoryCard(defaultMod);
    }
}

export function closeProModuleRequiredModal() {
    if (proModuleRequiredModal) {
        proModuleRequiredModal.style.display = 'none';
    }
}

if (typeof window !== 'undefined') {
    window.openProModuleRequiredModal = openProModuleRequiredModal;
    window.closeProModuleRequiredModal = closeProModuleRequiredModal;
}

if (cardProChoiceEditor) {
    cardProChoiceEditor.addEventListener('click', () => selectProMandatoryCard('editor'));
}
if (cardProChoiceReview) {
    cardProChoiceReview.addEventListener('click', () => selectProMandatoryCard('review'));
}
if (radioProMandatoryEditor) {
    radioProMandatoryEditor.addEventListener('change', () => selectProMandatoryCard('editor'));
}
if (radioProMandatoryReview) {
    radioProMandatoryReview.addEventListener('change', () => selectProMandatoryCard('review'));
}

// Khóa cứng: Chặn click ra ngoài backdrop để đóng modal
if (proModuleRequiredModal) {
    proModuleRequiredModal.addEventListener('click', (e) => {
        if (e.target === proModuleRequiredModal) {
            e.stopPropagation();
            e.preventDefault();
        }
    });
}

// Xử lý xác nhận lựa chọn Module Gói Pro
if (btnConfirmProModuleSelection) {
    btnConfirmProModuleSelection.addEventListener('click', async () => {
        const checkedRadio = document.querySelector('input[name="pro_mandatory_module"]:checked');
        const chosenMod = checkedRadio ? checkedRadio.value : 'editor';
        
        btnConfirmProModuleSelection.disabled = true;
        btnConfirmProModuleSelection.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
            <span>Đang lưu lựa chọn...</span>
        `;
        try {
            const res = await fetch('/api/license/set_pro_module', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ module: chosenMod })
            });
            const data = await res.json();
            if (data.success && data.license) {
                currentLicenseState = data.license;
                closeProModuleRequiredModal();
                updateLicenseUI(data.license);
                const modTitle = chosenMod === 'review' ? 'Review Phim' : 'Biên tập phim';
                showToast(`🎉 Đã thiết lập Module "${modTitle}" thành công! Bắt đầu sáng tạo ngay.`, 'success');
                
                // Tự động chuyển tab đến module đã chọn
                const targetTab = chosenMod === 'review' 
                    ? document.querySelector('.nav-tab[data-target="viewReview"]')
                    : document.querySelector('.nav-tab[data-target="viewEditor"]');
                if (targetTab) targetTab.click();
            } else {
                showToast(data.error || 'Không thể cập nhật module: ' + data.message, 'error');
            }
        } catch (err) {
            showToast('Lỗi kết nối khi lưu module: ' + err.message, 'error');
        } finally {
            btnConfirmProModuleSelection.disabled = false;
            btnConfirmProModuleSelection.innerHTML = `
                🚀 Xác Nhận Lựa Chọn & Bắt Đầu Sử Dụng
            `;
        }
    });
}

// Khởi tạo kiểm tra bản quyền khi tải trang
fetchLicenseInfo();

// ═════════════════════════════════════════════════════════════
// 📁 HỆ THỐNG QUẢN LÝ DỰ ÁN (.amsproj)
// ═════════════════════════════════════════════════════════════

const projectManager = {
    currentProject: {
        id: null,
        name: 'Du_An_Moi',
        filename: null,
        filepath: null
    },
    autoSaveInterval: null,

    init() {
        this.bindEvents();
        this.startAutoSave();
    },

    collectState() {
        const activeTabEl = document.querySelector('.header-tabs .nav-tab.active');
        const activeTabId = activeTabEl ? activeTabEl.getAttribute('data-target') : 'viewEditor';

        const state = {
            format_version: "1.0",
            app_version: "2026.8",
            project_id: this.currentProject.id || `proj_${Date.now()}`,
            project_name: this.currentProject.name || 'Du_An_Moi',
            created_at: this.currentProject.created_at || new Date().toISOString(),
            updated_at: new Date().toISOString(),
            active_tab: activeTabId,
            video: {
                path: (editorInputVideoPath && editorInputVideoPath.value) || '',
                filename: (editorInputVideoPath && editorInputVideoPath.value) ? editorInputVideoPath.value.split(/[\\/]/).pop() : '',
                duration: (videoPlayer && videoPlayer.duration) || 0
            },
            subtitles: typeof srtData !== 'undefined' ? srtData : [],
            tts_voice: {
                voice_id: (typeof currentSelectedVoiceId !== 'undefined') ? currentSelectedVoiceId : '',
                voice_speed: (typeof currentVoiceSpeed !== 'undefined') ? currentVoiceSpeed : 1.0,
                voice_pitch: (typeof currentVoicePitch !== 'undefined') ? currentVoicePitch : 0,
                voice_volume: (typeof currentVoiceVolume !== 'undefined') ? currentVoiceVolume : 1.0,
                cloned_voice_id: (typeof currentSelectedCloneVoiceId !== 'undefined') ? currentSelectedCloneVoiceId : '',
                audio_path: (typeof currentGeneratedAudioPath !== 'undefined') ? currentGeneratedAudioPath : ''
            },
            logo_overlay: window.currentReviewLogoState ? { ...window.currentReviewLogoState } : null,
            custom_overlay_layers: Array.isArray(window.customOverlayLayers) ? JSON.parse(JSON.stringify(window.customOverlayLayers)) : []
        };
        return state;
    },

    restoreState(proj) {
        if (!proj || typeof proj !== 'object') {
            showToast('Tệp dự án không hợp lệ hoặc bị hỏng!', 'error');
            return false;
        }

        try {
            // 1. Cập nhật thông tin dự án
            this.currentProject.id = proj.project_id || `proj_${Date.now()}`;
            this.currentProject.name = proj.project_name || 'Du_An_Moi';
            this.currentProject.filename = proj.filename || `${proj.project_name}.amsproj`;
            this.currentProject.filepath = proj.filepath || '';
            this.currentProject.created_at = proj.created_at || '';

            // 2. Khôi phục Video
            if (proj.video && proj.video.path && editorInputVideoPath) {
                editorInputVideoPath.value = proj.video.path;
                if (videoPlayer) {
                    videoPlayer.src = `/api/video?path=${encodeURIComponent(proj.video.path)}`;
                    videoPlayer.style.display = 'block';
                }
                if (videoPlaceholder) videoPlaceholder.style.display = 'none';
            }

            // 3. Khôi phục Phụ Đề
            if (Array.isArray(proj.subtitles)) {
                if (typeof srtData !== 'undefined') {
                    srtData.length = 0;
                    proj.subtitles.forEach(s => srtData.push({ ...s }));
                    if (typeof renderSrtTable === 'function') {
                        renderSrtTable();
                    }
                }
            }

            // 4. Khôi phục Logo Overlay
            if (proj.logo_overlay && window.currentReviewLogoState) {
                Object.assign(window.currentReviewLogoState, proj.logo_overlay);
                if (typeof window.renderReviewLogo === 'function') {
                    window.renderReviewLogo();
                }
            }

            // 5. Khôi phục Multi-Region Blur & Dynamic Text Overlays
            if (Array.isArray(proj.custom_overlay_layers)) {
                window.customOverlayLayers = JSON.parse(JSON.stringify(proj.custom_overlay_layers));
                if (typeof window.renderMultiOverlayLayersUI === 'function') {
                    window.renderMultiOverlayLayersUI();
                }
            }

            // 5. Chuyển Tab đang làm dở
            if (proj.active_tab) {
                const targetTab = document.querySelector(`.header-tabs .nav-tab[data-target="${proj.active_tab}"]`);
                if (targetTab) targetTab.click();
            }

            showToast(`🎉 Đã mở dự án "${this.currentProject.name}" thành công!`, 'success');
            appendLog(`[${new Date().toLocaleTimeString()}] > [Dự án] Đã nạp thành công dự án "${this.currentProject.name}" (${(proj.subtitles || []).length} câu phụ đề).`, 'info');
            return true;
        } catch (err) {
            console.error('Lỗi khôi phục dự án:', err);
            showToast(`Lỗi khôi phục dữ liệu dự án: ${err.message}`, 'error');
            return false;
        }
    },

    async save(isSaveAs = false) {
        // Nếu là Lưu thành bản mới (Save As) hoặc dự án chưa từng lưu ra file đường dẫn cụ thể
        if (isSaveAs || !this.currentProject.filepath || this.currentProject.name === 'Du_An_Moi') {
            const defaultName = (this.currentProject.name && this.currentProject.name !== 'Du_An_Moi') 
                ? (isSaveAs ? `${this.currentProject.name}_copy.amsproj` : `${this.currentProject.name}.amsproj`)
                : `Du_An_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.amsproj`;

            const state = this.collectState();
            const jsonStr = JSON.stringify(state, null, 2);

            try {
                const res = await fetch('/api/save_file_dialog', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: isSaveAs ? 'Lưu dự án thành bản mới (.amsproj)' : 'Lưu dự án AI Movie Shorts (.amsproj)',
                        default_name: defaultName,
                        defaultextension: '.amsproj',
                        filter: 'AI Movie Shorts Project (*.amsproj)|*.amsproj|JSON Project (*.json)|*.json|All Files (*.*)|*.*',
                        content: jsonStr
                    })
                });
                const data = await res.json();
                if (data.success && data.file_path) {
                    const savedPath = data.file_path;
                    const fileName = savedPath.split(/[\\/]/).pop();
                    const projName = fileName.replace(/\.(amsproj|json)$/i, '');
                    
                    this.currentProject.filepath = savedPath;
                    this.currentProject.filename = fileName;
                    this.currentProject.name = projName;

                    // Đồng bộ lưu bản sao vào projects/ để quản lý danh sách gần đây
                    state.project_name = projName;
                    state.filepath = savedPath;
                    await fetch('/api/project/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(state)
                    });

                    showToast(`💾 Đã lưu dự án "${projName}" thành công!`, 'success');
                    appendLog(`[${new Date().toLocaleTimeString()}] > [Dự án] 💾 Đã lưu dự án vào ${savedPath}`, 'info');
                } else if (data.cancelled) {
                    showToast('Đã hủy lưu dự án', 'info');
                }
            } catch (err) {
                // Fallback hiển thị Modal nếu gọi dialog hệ thống lỗi
                const modal = document.getElementById('saveProjectModal');
                const titleEl = document.getElementById('saveProjectModalTitle');
                const nameInput = document.getElementById('inputSaveProjectName');
                if (titleEl) titleEl.textContent = isSaveAs ? 'LƯU THÀNH BẢN MỚI' : 'LƯU DỰ ÁN';
                if (nameInput) {
                    nameInput.value = defaultName.replace(/\.amsproj$/i, '');
                    nameInput.focus();
                }
                if (modal) modal.style.display = 'flex';
            }
            return;
        }

        // Lưu đè nhanh vào file hiện tại
        const state = this.collectState();
        state.filepath = this.currentProject.filepath;
        try {
            const res = await fetch('/api/project/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state)
            });
            const data = await res.json();
            if (data.success) {
                this.currentProject.filename = data.filename;
                this.currentProject.filepath = data.filepath;
                showToast(`💾 Đã lưu dự án "${this.currentProject.name}" thành công!`, 'success');
                appendLog(`[${new Date().toLocaleTimeString()}] > [Dự án] 💾 Đã lưu dự án "${this.currentProject.name}" vào ${data.filepath}`, 'info');
            } else {
                showToast(`Lỗi lưu dự án: ${data.error}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi mạng khi lưu dự án: ${e.message}`, 'error');
        }
    },

    async confirmSaveFromModal() {
        const nameInput = document.getElementById('inputSaveProjectName');
        const modal = document.getElementById('saveProjectModal');
        const projectName = nameInput ? nameInput.value.trim() : '';

        if (!projectName) {
            showToast('Vui lòng nhập tên dự án!', 'warning');
            if (nameInput) nameInput.focus();
            return;
        }

        this.currentProject.name = projectName;
        const state = this.collectState();
        state.project_name = projectName;

        try {
            const res = await fetch('/api/project/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state)
            });
            const data = await res.json();
            if (data.success) {
                this.currentProject.filename = data.filename;
                this.currentProject.filepath = data.filepath;
                if (modal) modal.style.display = 'none';
                showToast(`💾 Đã lưu dự án "${projectName}" thành công!`, 'success');
                appendLog(`[${new Date().toLocaleTimeString()}] > [Dự án] 💾 Đã lưu dự án "${projectName}" vào projects/${data.filename}`, 'info');
            } else {
                showToast(`Lỗi lưu dự án: ${data.error}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi lưu dự án: ${e.message}`, 'error');
        }
    },

    async openFromFile() {
        try {
            const res = await fetch('/api/select_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: 'Mở file dự án AI Movie Shorts (.amsproj)',
                    filetypes: [
                        ['AI Movie Shorts Project (*.amsproj)', '*.amsproj'],
                        ['JSON Project (*.json)', '*.json'],
                        ['All Files (*.*)', '*.*']
                    ]
                })
            });
            const data = await res.json();
            if (data.success && data.file_path) {
                await this.loadFromFilepath(data.file_path);
            } else if (data.cancelled) {
                showToast('Đã hủy chọn file dự án', 'info');
            }
        } catch (err) {
            // Fallback mở file input của trình duyệt
            const fileInput = document.getElementById('inputOpenProjectFile');
            if (fileInput) fileInput.click();
        }
    },

    async loadFromFilepath(filepath) {
        try {
            const res = await fetch('/api/project/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: filepath })
            });
            const data = await res.json();
            if (data.success && data.project) {
                data.project.filename = data.filename;
                data.project.filepath = data.filepath;
                this.restoreState(data.project);
            } else {
                showToast(`Lỗi mở dự án: ${data.error}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi nạp dự án: ${e.message}`, 'error');
        }
    },

    async loadFromFilename(filename) {
        try {
            const res = await fetch('/api/project/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            });
            const data = await res.json();
            if (data.success && data.project) {
                data.project.filename = filename;
                data.project.filepath = data.filepath;
                this.restoreState(data.project);
            } else {
                showToast(`Lỗi mở dự án: ${data.error}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi nạp dự án: ${e.message}`, 'error');
        }
    },

    async deleteProject(filename) {
        try {
            const res = await fetch('/api/project/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã xóa dự án ${filename}!`, 'info');
                this.openRecentProjectsModal();
            } else {
                showToast(`Lỗi xóa dự án: ${data.error}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi kết nối khi xóa dự án: ${e.message}`, 'error');
        }
    },

    async exportToFile() {
        const defaultName = `${this.currentProject.name || 'Du_An'}.amsproj`;
        const state = this.collectState();
        const jsonStr = JSON.stringify(state, null, 2);

        try {
            const res = await fetch('/api/save_file_dialog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: 'Xuất tệp dự án .amsproj ra đĩa',
                    default_name: defaultName,
                    defaultextension: '.amsproj',
                    filter: 'AI Movie Shorts Project (*.amsproj)|*.amsproj|JSON Project (*.json)|*.json|All Files (*.*)|*.*',
                    content: jsonStr
                })
            });
            const data = await res.json();
            if (data.success && data.file_path) {
                showToast(`📤 Đã xuất tệp dự án ra: ${data.file_path}`, 'success');
                appendLog(`[${new Date().toLocaleTimeString()}] > [Dự án] 📤 Đã xuất tệp dự án ra đĩa: ${data.file_path}`, 'info');
            } else if (data.cancelled) {
                showToast('Đã hủy xuất tệp dự án', 'info');
            }
        } catch (err) {
            // Fallback tải qua browser
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = defaultName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('📤 Đã tải tệp .amsproj về máy tính!', 'success');
        }
    },

    importFromFile(file) {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const projectData = JSON.parse(e.target.result);
                projectData.filename = file.name;
                this.restoreState(projectData);
            } catch (err) {
                showToast('Tệp dự án không đúng định dạng JSON/amsproj!', 'error');
            }
        };
        reader.readAsText(file);
    },

    startAutoSave() {
        if (this.autoSaveInterval) clearInterval(this.autoSaveInterval);
        // Tự động lưu nháp mỗi 60 giây
        this.autoSaveInterval = setInterval(async () => {
            const hasVideo = editorInputVideoPath && editorInputVideoPath.value;
            const hasSubs = typeof srtData !== 'undefined' && srtData.length > 0;
            if (hasVideo || hasSubs) {
                const state = this.collectState();
                try {
                    await fetch('/api/project/autosave', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(state)
                    });
                } catch (e) {}
            }
        }, 60000);
    },

    bindEvents() {
        const btnMenu = document.getElementById('btnProjectMenu');
        const dropdownContent = document.getElementById('projectDropdownContent');

        // Toggle dropdown menu
        if (btnMenu && dropdownContent) {
            btnMenu.addEventListener('click', (e) => {
                e.stopPropagation();
                const isHidden = dropdownContent.style.display === 'none' || !dropdownContent.style.display;
                dropdownContent.style.display = isHidden ? 'flex' : 'none';
            });

            document.addEventListener('click', (e) => {
                if (!btnMenu.contains(e.target) && !dropdownContent.contains(e.target)) {
                    dropdownContent.style.display = 'none';
                }
            });
        }

        // Project Menu Items
        const btnNew = document.getElementById('btnNewProject');
        const btnSave = document.getElementById('btnSaveProject');
        const btnSaveAs = document.getElementById('btnSaveAsProject');
        const btnOpenFile = document.getElementById('btnOpenFileProject');
        const btnRecent = document.getElementById('btnRecentProjects');
        const btnExport = document.getElementById('btnExportProjectFile');
        const fileInput = document.getElementById('inputOpenProjectFile');

        if (btnNew) btnNew.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.newProject();
        });

        if (btnSave) btnSave.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.save(false);
        });

        if (btnSaveAs) btnSaveAs.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.save(true);
        });

        if (btnOpenFile) btnOpenFile.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.openFromFile();
        });

        if (btnRecent) btnRecent.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.openRecentProjectsModal();
        });

        if (btnExport) btnExport.addEventListener('click', () => {
            if (dropdownContent) dropdownContent.style.display = 'none';
            this.exportToFile();
        });

        if (fileInput) fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                this.importFromFile(e.target.files[0]);
                e.target.value = '';
            }
        });

        // Save Modal Confirm / Cancel
        const btnConfirmSave = document.getElementById('btnConfirmSaveProject');
        const btnCancelSave = document.getElementById('btnCancelSaveProject');
        const btnCloseSaveModal = document.getElementById('btnCloseSaveProjectModal');
        const saveModal = document.getElementById('saveProjectModal');
        const saveNameInput = document.getElementById('inputSaveProjectName');

        if (btnConfirmSave) btnConfirmSave.addEventListener('click', () => this.confirmSaveFromModal());
        if (btnCancelSave && saveModal) btnCancelSave.addEventListener('click', () => saveModal.style.display = 'none');
        if (btnCloseSaveModal && saveModal) btnCloseSaveModal.addEventListener('click', () => saveModal.style.display = 'none');
        if (saveNameInput) {
            saveNameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.confirmSaveFromModal();
                if (e.key === 'Escape' && saveModal) saveModal.style.display = 'none';
            });
        }

        // Recent Modal Close / Refresh / Search
        const btnCloseRecent = document.getElementById('btnCloseRecentProjectsModal');
        const btnCloseRecentFooter = document.getElementById('btnCloseRecentProjectsFooter');
        const btnRefreshRecent = document.getElementById('btnRefreshRecentProjects');
        const btnImportFromRecent = document.getElementById('btnImportFromRecentModal');
        const recentModal = document.getElementById('recentProjectsModal');
        const searchInput = document.getElementById('inputSearchProjects');

        if (btnCloseRecent && recentModal) btnCloseRecent.addEventListener('click', () => recentModal.style.display = 'none');
        if (btnCloseRecentFooter && recentModal) btnCloseRecentFooter.addEventListener('click', () => recentModal.style.display = 'none');
        if (btnRefreshRecent) btnRefreshRecent.addEventListener('click', () => this.openRecentProjectsModal());
        if (btnImportFromRecent) btnImportFromRecent.addEventListener('click', () => {
            if (recentModal) recentModal.style.display = 'none';
            this.openFromFile();
        });

        if (searchInput) {
            let _recentSearchTimer = null;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(_recentSearchTimer);
                const query = e.target.value.toLowerCase().trim();
                _recentSearchTimer = setTimeout(() => {
                    if (!window._cachedRecentProjects) return;
                    const filtered = window._cachedRecentProjects.filter(p => 
                        p.project_name.toLowerCase().includes(query) || 
                        (p.video_name && p.video_name.toLowerCase().includes(query))
                    );
                    this.renderRecentProjectsList(filtered);
                }, 200);
            });
        }

        // Global Keyboard Shortcuts (Ctrl+S, Ctrl+O, Ctrl+N)
        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault();
                this.save(false);
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') {
                e.preventDefault();
                this.openFromFile();
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
                e.preventDefault();
                this.newProject();
            }
        });
    }
};

projectManager.init();

// =============================================================================
// 🚀 HỆ THỐNG AUTO-UPDATER (TỰ ĐỘNG CẬP NHẬT QUA GOOGLE DRIVE & GOOGLE SHEET)
// =============================================================================
const appUpdater = {
    currentUpdateInfo: null,
    pollingInterval: null,

    init() {
        const btnHeaderCheck = document.getElementById('btnCheckUpdateHeader');
        const btnCloseModal = document.getElementById('btnCloseUpdateModal');
        const btnSkip = document.getElementById('btnSkipUpdate');
        const btnStart = document.getElementById('btnStartAppUpdate');
        const modal = document.getElementById('modalAppUpdateNotice');

        if (btnHeaderCheck) {
            btnHeaderCheck.addEventListener('click', () => {
                this.check(false); // manual check with alerts/toasts
            });
        }

        if (btnCloseModal && modal) {
            btnCloseModal.addEventListener('click', () => {
                if (this.currentUpdateInfo && this.currentUpdateInfo.is_mandatory) {
                    showToast('Bản cập nhật này là bắt buộc để tiếp tục sử dụng ứng dụng!', 'warning');
                    return;
                }
                modal.classList.remove('active');
                modal.style.display = 'none';
            });
        }

        if (btnSkip && modal) {
            btnSkip.addEventListener('click', () => {
                if (this.currentUpdateInfo && this.currentUpdateInfo.is_mandatory) {
                    showToast('Bản cập nhật này là bắt buộc để tiếp tục sử dụng ứng dụng!', 'warning');
                    return;
                }
                modal.classList.remove('active');
                modal.style.display = 'none';
            });
        }

        if (btnStart) {
            btnStart.addEventListener('click', () => {
                this.startUpdate();
            });
        }

        // Tự động kiểm tra cập nhật ngầm sau 3 giây khi khởi động app
        setTimeout(() => {
            this.check(true); // silent check
        }, 3000);
    },

    async check(silent = true) {
        const btnHeaderCheck = document.getElementById('btnCheckUpdateHeader');
        if (!silent && btnHeaderCheck) {
            btnHeaderCheck.disabled = true;
            btnHeaderCheck.innerHTML = `<span>⏳</span><span>Đang kiểm tra...</span>`;
        }

        try {
            const res = await fetch('/api/updater/check');
            const data = await res.json();
            this.currentUpdateInfo = data;

            if (data.has_update) {
                // Có bản cập nhật mới
                if (btnHeaderCheck) {
                    btnHeaderCheck.style.borderColor = '#38bdf8';
                    btnHeaderCheck.style.boxShadow = '0 0 12px rgba(56, 189, 248, 0.6)';
                    btnHeaderCheck.innerHTML = `<span style="font-size: 13px;">🚀</span><span style="font-weight: 700; color: #38bdf8;">Cập nhật (v${escapeHtml(data.latest_version)})</span>`;
                }
                this.showUpdateModal(data);
            } else {
                if (!silent) {
                    this.showUpdateModal(data);
                }
            }
        } catch (err) {
            if (!silent) {
                showToast('Lỗi kiểm tra cập nhật: ' + err.message, 'error');
            }
        } finally {
            if (btnHeaderCheck && !this.currentUpdateInfo?.has_update) {
                btnHeaderCheck.disabled = false;
                btnHeaderCheck.innerHTML = `<span style="font-size: 13px;">🚀</span><span style="font-weight: 600;">Cập nhật</span>`;
            }
        }
    },

    showUpdateModal(data) {
        const modal = document.getElementById('modalAppUpdateNotice');
        if (!modal) return;

        const lblCurrent = document.getElementById('lblCurrentAppVersion');
        const lblLatest = document.getElementById('lblLatestAppVersion');
        const changelogContent = document.getElementById('updateChangelogContent');
        const btnSkip = document.getElementById('btnSkipUpdate');
        const btnClose = document.getElementById('btnCloseUpdateModal');
        const progressBox = document.getElementById('updateProgressBox');
        const btnStart = document.getElementById('btnStartAppUpdate');
        const modalTitle = modal.querySelector('h3');
        const modalSubtitle = modal.querySelector('h3 + div');

        const currentVer = data.current_version || '1.0.0';
        const latestVer = data.latest_version || currentVer;
        const hasUpdate = Boolean(data.has_update);

        if (lblCurrent) lblCurrent.textContent = `v${currentVer}`;
        if (lblLatest) lblLatest.textContent = `v${latestVer}`;

        if (progressBox) progressBox.style.display = 'none';

        if (hasUpdate) {
            if (modalTitle) modalTitle.textContent = "🚀 ĐÃ CÓ BẢN NÂNG CẤP MỚI!";
            if (modalSubtitle) modalSubtitle.textContent = "Tự động nâng cấp & bảo toàn nguyên vẹn 100% dữ liệu của bạn";
            if (changelogContent) changelogContent.textContent = data.changelog || '🎉 Bản cập nhật tối ưu hóa hiệu năng & bổ sung tính năng mới.';
            if (btnStart) {
                btnStart.style.display = 'inline-flex';
                btnStart.disabled = false;
                btnStart.innerHTML = `<span>🚀</span><span>Cập Nhật Ngay (v${escapeHtml(latestVer)})</span>`;
            }
            if (btnSkip) {
                btnSkip.textContent = "Để sau";
                btnSkip.style.display = data.is_mandatory ? 'none' : 'inline-block';
            }
        } else {
            if (modalTitle) modalTitle.textContent = "✅ BẢN MỚI NHẤT ĐANG HOẠT ĐỘNG!";
            if (modalSubtitle) modalSubtitle.textContent = "Ứng dụng NovaCut trên máy tính của bạn đang ở phiên bản mới nhất";
            if (changelogContent) changelogContent.textContent = `🎉 Bạn đang sử dụng phiên bản v${currentVer}.\nKhông có bản cập nhật nào mới hơn tại thời điểm này. Khi có tính năng mới, hệ thống sẽ tự động thông báo tại đây!`;
            if (btnStart) {
                btnStart.style.display = 'none';
            }
            if (btnSkip) {
                btnSkip.textContent = "Đóng";
                btnSkip.style.display = 'inline-block';
            }
        }

        if (btnClose) btnClose.style.display = data.is_mandatory ? 'none' : 'block';

        modal.classList.add('active');
        modal.style.display = 'flex';
    },

    async startUpdate() {
        if (!this.currentUpdateInfo || (!this.currentUpdateInfo.download_url && !this.currentUpdateInfo.google_drive_file_id)) {
            showToast('Không tìm thấy link tải bản cập nhật!', 'error');
            return;
        }

        const btnStart = document.getElementById('btnStartAppUpdate');
        const btnSkip = document.getElementById('btnSkipUpdate');
        const progressBox = document.getElementById('updateProgressBox');

        if (btnStart) {
            btnStart.disabled = true;
            btnStart.style.pointerEvents = 'none';
            btnStart.innerHTML = `<span>⏳</span><span>Đang tải bản cập nhật...</span>`;
        }
        if (btnSkip) btnSkip.style.display = 'none';
        if (progressBox) progressBox.style.display = 'block';

        try {
            const res = await fetch('/api/updater/start_update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    download_url: this.currentUpdateInfo.download_url,
                    google_drive_file_id: this.currentUpdateInfo.google_drive_file_id,
                    target_version: this.currentUpdateInfo.latest_version
                })
            });
            const data = await res.json();
            if (!data.success) {
                throw new Error(data.error || 'Không thể bắt đầu cập nhật');
            }

            // Bắt đầu quét tiến trình tải thời gian thực
            this.startProgressPolling();

        } catch (err) {
            showToast('Lỗi cập nhật: ' + err.message, 'error');
            if (btnStart) {
                btnStart.disabled = false;
                btnStart.style.pointerEvents = 'auto';
                btnStart.innerHTML = `<span>🚀</span><span>Thử Lại</span>`;
            }
        }
    },

    startProgressPolling() {
        if (this.pollingInterval) clearInterval(this.pollingInterval);

        const statusText = document.getElementById('updateProgressStatusText');
        const percentText = document.getElementById('updateProgressPercentText');
        const barFill = document.getElementById('updateProgressBarFill');
        const subText = document.getElementById('updateProgressSubText');

        this.pollingInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/updater/progress');
                const p = await res.json();

                const pct = Math.min(100, Math.max(0, parseInt(p.percent) || 0));
                if (statusText) statusText.textContent = p.message || 'Đang cập nhật...';
                if (percentText) percentText.textContent = `${pct}%`;
                if (barFill) barFill.style.width = `${pct}%`;

                if (p.total_bytes > 0 && subText) {
                    const mbDown = (p.downloaded_bytes / (1024 * 1024)).toFixed(1);
                    const mbTotal = (p.total_bytes / (1024 * 1024)).toFixed(1);
                    subText.textContent = `${mbDown} MB / ${mbTotal} MB`;
                }

                if (p.status === 'completed') {
                    clearInterval(this.pollingInterval);
                    showToast(p.message || 'Cập nhật thành công!', 'success');
                    const btnStart = document.getElementById('btnStartAppUpdate');
                    if (btnStart) {
                        btnStart.disabled = false;
                        btnStart.style.pointerEvents = 'auto';
                        btnStart.innerHTML = `<span>✅</span><span>Đã Cập Nhật Thành Công</span>`;
                    }
                } else if (p.status === 'error') {
                    clearInterval(this.pollingInterval);
                    showToast('Lỗi cập nhật: ' + (p.error || 'Không xác định'), 'error');
                    const btnStart = document.getElementById('btnStartAppUpdate');
                    if (btnStart) {
                        btnStart.disabled = false;
                        btnStart.style.pointerEvents = 'auto';
                        btnStart.innerHTML = `<span>🚀</span><span>Thử Lại</span>`;
                    }
                }
            } catch (e) {
                console.error('Lỗi poll update progress:', e);
            }
        }, 600);
    }
};

window.appUpdater = appUpdater;
appUpdater.init();

// Initialize Batch Queue Studio
try {
    initBatchQueueModule();
} catch (e) {
    console.warn('Error initializing Batch Queue Module:', e);
}

// Initialize Universal Video Studio Suite (Toolbar, Aspect Ratio, Stretch & Overlays)
try {
    initVideoStudioSuite();
} catch (e) {
    console.warn('Error initializing Video Studio Suite:', e);
}

// Initialize Batch Video Editor Module (Biên Tập Hàng Loạt)
try {
    initBatchEditorModule();
} catch (e) {
    console.warn('Error initializing Batch Video Editor Module:', e);
}

// Initialize Export History Module (Lịch Sử Xuất Video)
try {
    initExportHistoryModule();
} catch (e) {
    console.warn('Error initializing Export History Module:', e);
}



