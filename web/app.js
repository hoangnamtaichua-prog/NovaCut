import { loadCapCutDrafts } from './js/features/capcut.js';
import { initCloneVoiceModule, loadClonedVoicesList } from './js/features/clone_voice.js';
import { appendLog, showToast, showConfirmModal, showAlertModal, showPromptModal, formatTimeSec, parseTimeToSeconds, formatSrtTimestamp, formatDurationStr } from './js/utils.js';

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

        // Remove active from all tabs
        mainNavTabs.forEach(t => t.classList.remove('active'));
        // Add active to clicked tab
        tab.classList.add('active');
        
        // Hide all views
        mainViews.forEach(v => {
            v.classList.remove('active');
            v.style.display = 'none';
        });
        
        // Pause players when leaving view
        if (targetId !== 'viewEditor') {
            const vp = document.getElementById('videoPlayer');
            if (vp && !vp.paused) vp.pause();
        }
        if (targetId !== 'viewReview') {
            const rvp = document.getElementById('reviewVideoPlayer');
            if (rvp && !rvp.paused) rvp.pause();
        }
        
        const targetView = document.getElementById(targetId);
        if (targetView) {
            targetView.classList.add('active');
            targetView.style.display = (targetId === 'viewEditor' || targetId === 'viewReview' || targetId === 'viewDownload' || targetId === 'viewCapCut' || targetId === 'viewCloneVoice') ? 'block' : 'flex';
            
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
        } else {
            if (dubbingToggleLabel) {
                dubbingToggleLabel.textContent = 'Tắt';
                dubbingToggleLabel.style.color = '#94a3b8';
            }
            dubbingCard?.classList.add('dubbing-disabled');
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
        dubbingVoiceVolVal.textContent = e.target.value + '%';
    });
}

const dubbingOrigVol = document.getElementById('dubbingOrigVol');
const dubbingOrigVolVal = document.getElementById('dubbingOrigVolVal');
if (dubbingOrigVol && dubbingOrigVolVal) {
    dubbingOrigVol.addEventListener('input', (e) => {
        dubbingOrigVolVal.textContent = e.target.value + '%';
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
    });
}

const btnQuickTestVoice = document.getElementById('btnQuickTestVoice');
if (btnQuickTestVoice) {
    btnQuickTestVoice.addEventListener('click', () => {
        const voiceId = document.getElementById('dubbingVoiceInput')?.value || 'ngoc_huyen';
        const previewBtn = document.querySelector('#btnOpenVoiceModalDubbing .btn-preview-voice');
        if (window.playPreviewVoice && previewBtn) {
            window.playPreviewVoice(voiceId, previewBtn);
        }
    });
}

// AI Stem & Vocal Separation Event Listeners for Editor Tab
const editorStemSeparationEnabled = document.getElementById('editorStemSeparationEnabled');
const editorStemConfig = document.getElementById('editorStemConfig');
if (editorStemSeparationEnabled && editorStemConfig) {
    editorStemSeparationEnabled.addEventListener('change', (e) => {
        editorStemConfig.style.opacity = e.target.checked ? '1' : '0.4';
        editorStemConfig.style.pointerEvents = e.target.checked ? 'auto' : 'none';
    });
}

const btnRunStemSeparationEditor = document.getElementById('btnRunStemSeparationEditor');
if (btnRunStemSeparationEditor) {
    btnRunStemSeparationEditor.addEventListener('click', async () => {
        const videoInput = document.getElementById('editorInputVideoPath')?.value || '';
        if (!videoInput) {
            showToast('⚠️ Vui lòng chọn video đầu vào trước khi tách âm thanh!', 'warning');
            return;
        }

        const hasPerm = await checkFeaturePermission('can_access_editor', 'Tách Âm Thanh AI & Lọc Giọng Thoại');
        if (!hasPerm) return;

        btnRunStemSeparationEditor.disabled = true;
        btnRunStemSeparationEditor.innerHTML = '<span class="loading-spinner-small"></span> Đang tách âm thanh AI...';
        showToast('🎛️ Đang chạy tách lời thoại cũ và bảo lưu tiếng động SFX...', 'info');

        try {
            const mode = document.getElementById('editorStemMode')?.value || 'ai_neural';
            const removeVocals = document.getElementById('editorRemoveVocals')?.checked !== false;
            const keepSfx = document.getElementById('editorKeepSfx')?.checked !== false;

            const res = await fetch('/api/audio/separate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    media_path: videoInput,
                    mode: mode,
                    remove_vocals: removeVocals,
                    keep_sfx: keepSfx
                })
            });

            const data = await res.json();
            if (data.success && data.cleaned_url) {
                showToast('🎉 Đã tách và lọc âm thanh AI thành công!', 'success');
                const resultBox = document.getElementById('editorStemResultAudio');
                const player = document.getElementById('editorStemAudioPlayer');
                if (resultBox && player) {
                    resultBox.style.display = 'block';
                    player.src = data.cleaned_url;
                    player.play().catch(() => {});
                }
            } else {
                showToast(`❌ Lỗi tách âm thanh: ${data.error || 'Thất bại'}`, 'error');
            }
        } catch (err) {
            showToast(`❌ Lỗi kết nối: ${err.message}`, 'error');
        } finally {
            btnRunStemSeparationEditor.disabled = false;
            btnRunStemSeparationEditor.innerHTML = '<span>⚡</span> Tách & Nghe Thử Âm SFX';
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

window.selectFile = selectFile;
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
    } else if (state === 'error') {
        if (statusText) statusText.textContent = 'Có lỗi xảy ra';
        startBtn.disabled = false;
        startBtn.style.display = 'inline-flex';
        startBtn.textContent = 'THỬ LẠI';
        if (stopExportBtn) stopExportBtn.style.display = 'none';
        if (btnEmergencyStop) btnEmergencyStop.style.display = 'none';
    }
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

if (btnSelectModalOutputDir) {
    btnSelectModalOutputDir.addEventListener('click', async () => {
        const path = await selectFile('dir');
        if (path && exportModalOutputDir) exportModalOutputDir.value = path;
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

async function executeExportPipeline() {
    if (isGenerating) return;
    if (!checkFeaturePermission('can_access_editor', 'Xuất video Biên tập phim')) return;
    
    if (!editorInputVideoPath.value) {
        showToast("Vui lòng chọn video đầu vào!", 'warning');
        return;
    }
    
    const isDubbingOn = document.getElementById('dubbingEnabled')?.checked ?? false;
    const isDubbingTtsTab = document.getElementById('tabDubbingTts')?.classList.contains('active') ?? true;
    
    const dubbingConfig = {
        enabled: isDubbingOn,
        mode: isDubbingTtsTab ? 'tts' : 'manual',
        voice_id: document.getElementById('dubbingVoiceInput')?.value || 'ngoc_huyen',
        speed: parseFloat(document.getElementById('dubbingSpeed')?.value || 1.0),
        threads: parseInt(document.getElementById('dubbingThreads')?.value || 16),
        voice_volume: parseInt(document.getElementById('dubbingVoiceVol')?.value || 100) / 100,
        original_volume: parseInt(document.getElementById('dubbingOrigVol')?.value || 30) / 100,
        audio_ducking: document.getElementById('dubbingDucking')?.checked ?? true,
        remove_original_vocals: document.getElementById('editorRemoveVocals')?.checked ?? true,
        stem_separation: {
            enabled: document.getElementById('editorStemSeparationEnabled')?.checked ?? true,
            mode: document.getElementById('editorStemMode')?.value || 'ai_neural',
            remove_vocals: document.getElementById('editorRemoveVocals')?.checked ?? true,
            keep_sfx: document.getElementById('editorKeepSfx')?.checked ?? true
        },
        manual_audio: document.getElementById('manualAudioPath')?.value || '',
        manual_voice_volume: parseInt(document.getElementById('dubbingManualVol')?.value || 100) / 100,
        manual_original_volume: parseInt(document.getElementById('dubbingManualOrigVol')?.value || 30) / 100
    };

    if (isDubbingOn && !isDubbingTtsTab && !dubbingConfig.manual_audio) {
        showToast("Bạn đang bật lồng tiếng thủ công nhưng chưa chọn file Audio!", 'warning');
        return;
    }

    const blurEnabled = document.getElementById('reviewBlurOriginalSubtitles')?.checked ?? false;
    const blurIntensity = parseInt(document.getElementById('dynBlurIntensity')?.value) || parseInt(document.getElementById('subBgBlur')?.value) || 15;

    const outDirVal = (exportModalOutputDir && exportModalOutputDir.value) ? exportModalOutputDir.value : ((outputDirPath && outputDirPath.value) ? outputDirPath.value : 'output');
    const outNameVal = (exportModalFileName && exportModalFileName.value.trim()) ? exportModalFileName.value.trim() : ((outputFileName && outputFileName.value) ? outputFileName.value : "video_tom_tat.mp4");

    const config = {
        mode: isDubbingOn ? (isDubbingTtsTab ? 'tts' : 'manual') : 'none',
        inputVideo: editorInputVideoPath.value,
        outputDir: outDirVal,
        outputName: outNameVal,
        encoder: document.getElementById('exportEncoder')?.value || 'libx264',
        resolution: document.getElementById('exportResolution')?.value || 'original',
        bitrate: parseInt(document.getElementById('exportBitrate')?.value) || 10000,
        bitrate_mode: document.getElementById('exportBitrateMode')?.value || 'VBR',
        video_speed: parseFloat(document.getElementById('editToolSpeedSlider')?.value || 1.0),
        video_zoom: currentVideoZoom || 1.0,
        video_pan_x: videoPanX || 0,
        video_pan_y: videoPanY || 0,
        aspect_ratio: document.getElementById('editToolAspectRatio')?.value || 'original',
        mirror_flip: document.getElementById('editToolMirrorFlip')?.checked || false,
        trim_enabled: document.getElementById('editToolTrimEnabled')?.checked || false,
        trim_start: document.getElementById('editToolTrimStart')?.value || '',
        trim_end: document.getElementById('editToolTrimEnd')?.value || '',
        manualAudio: dubbingConfig.manual_audio,
        manualSrt: manualSrtPath.value,
        dubbing: dubbingConfig,
        subtitles: (typeof srtData !== 'undefined' && Array.isArray(srtData)) ? srtData : [],
        blur_original_subtitles: blurEnabled,
        blur_intensity: blurIntensity,
        blur_use_ai_scan: document.getElementById('blurUseAiScan')?.checked ?? true,
        original_srt_path: manualSrtPath.value || '',
        ocr_region: currentRegion || { x: 20, y: 81.5, w: 60, h: 9.5 },
        blur_lead_offset: parseFloat(document.getElementById('blurLeadOffset')?.value) || -180,
        blur_padding: parseFloat(document.getElementById('blurPadding')?.value) || 220,
        logo: {
            enabled: document.getElementById('enableLogoWatermark')?.checked ?? false,
            path: document.getElementById('logoInputPath')?.value || '',
            x_pct: currentLogoState.x_pct,
            y_pct: currentLogoState.y_pct,
            w_pct: currentLogoState.w_pct,
            h_pct: currentLogoState.h_pct,
            opacity: parseInt(document.getElementById('logoOpacity')?.value || 100)
        }
    };

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

    const blurLabel = blurEnabled ? ' | Dynamic Blur: Bật (' + blurIntensity + 'px)' : '';
    appendLog('> Bắt đầu xuất video... Lồng tiếng AI: ' + (isDubbingOn ? (isDubbingTtsTab ? 'TTS (' + dubbingConfig.voice_id + ')' : 'File thủ công') : 'Tắt') + blurLabel, 'info');
    
    exportAbortController = new AbortController();
    
    // Call Python backend to start process
    try {
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
            signal: exportAbortController.signal
        });
        
        if (!response.ok) throw new Error("Failed to start process");
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            lines.forEach(line => {
                if (line.trim()) {
                    let msg = line.replace('data: ', '');
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
            });
        }
        
        if (isGenerating) {
            appendLog('--- HOÀN THÀNH ---', 'info');
            setStatus('ready');
            isGenerating = false;
            
            // Update player to show output video
            let fullOutPath = config.outputDir ? (config.outputDir + '\\' + config.outputName) : ('output\\' + config.outputName);
            videoPlayer.src = `/api/video?path=${encodeURIComponent(fullOutPath)}`;
            videoPlayer.load();
            videoPlayer.play();
            document.getElementById('btnPreviewEdited').click();
            showToast('Xuất video hoàn tất thành công!', 'success');
        }
        
    } catch (e) {
        if (e.name === 'AbortError') {
            appendLog('🛑 Đã dừng tiến trình xuất video.', 'warning');
        } else {
            console.error(e);
            appendLog('Lỗi kết nối tới Server: ' + e.message, 'error');
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
    
    // Sort and calculate width in advance (zero CPU overhead during 60fps rendering)
    const valid = srtData
        .filter(s => s.startSeconds != null && s.endSeconds != null && s.endSeconds > s.startSeconds)
        .map(s => {
            const rawText = s.text || s.original_text || s.raw_text || '';
            const aiBox = s.aiBox || null;
            let widthPct = calculateSubtitleWidthPercent(rawText);
            let leftPct = null;
            const visualStart = s.visual_start != null ? s.visual_start : (aiBox && aiBox.visual_start != null ? aiBox.visual_start : null);
            const visualEnd = s.visual_end != null ? s.visual_end : (aiBox && aiBox.visual_end != null ? aiBox.visual_end : null);
            
            if (aiBox && typeof aiBox === 'object' && typeof aiBox.w_pct === 'number' && aiBox.w_pct > 0) {
                widthPct = aiBox.w_pct;
                leftPct = aiBox.x_pct;
            }
            
            return {
                id: s.id,
                start: s.startSeconds,
                end: s.endSeconds,
                visualStart: visualStart,
                visualEnd: visualEnd,
                text: rawText,
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
    // offsetMs âm (ví dụ: -500ms = -0.5s) -> vùng làm mờ xuất hiện sớm hơn 0.5s
    const offsetMs = parseFloat(document.getElementById('blurLeadOffset')?.value) ?? -180;
    const paddingMs = parseFloat(document.getElementById('blurPadding')?.value) ?? 220;
    const offsetSec = offsetMs / 1000.0;
    const paddingSec = paddingMs / 1000.0;
    
    // Quét từng câu để bắt chính xác visual frame bounds & nối mờ khoảng trống ngắn
    for (let i = 0; i < _cachedSortedSubs.length; i++) {
        const sub = _cachedSortedSubs[i];
        
        // Mốc bắt đầu: sub.start + offsetSec (kéo -500ms -> bắt đầu sớm hơn 0.5s)
        const baseStart = (sub.visualStart != null) ? Math.min(sub.start, sub.visualStart) : sub.start;
        const effStart = Math.max(0, baseStart + offsetSec);
        
        // Mốc kết thúc: sub.end + paddingSec
        const baseEnd = (sub.visualEnd != null) ? Math.max(sub.end, sub.visualEnd) : sub.end;
        const effEnd = baseEnd + paddingSec;
        
        if (currentTime >= effStart && currentTime <= effEnd) {
            return sub;
        }
        
        // Smart Gap Bridging: Nếu khoảng trống giữa câu hiện tại và câu kế tiếp <= 0.75s, duy trì làm mờ liên tục chống chớp giật
        if (i < _cachedSortedSubs.length - 1) {
            const nextSub = _cachedSortedSubs[i + 1];
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
    const blurCheckbox = document.getElementById('reviewBlurOriginalSubtitles');
    const isBlurEnabled = blurCheckbox && blurCheckbox.checked;
    
    if (!isBlurEnabled || typeof srtData === 'undefined' || !Array.isArray(srtData) || srtData.length === 0) {
        if (_lastBlurState.visible) {
            dynamicBlurOverlay.style.opacity = '0';
            dynamicBlurOverlay.style.visibility = 'hidden';
            _lastBlurState.visible = false;
            _lastBlurState.subId = null;
        }
        return;
    }
    
    const currentTime = videoPlayer ? videoPlayer.currentTime : 0;
    const activeSub = getActiveSubtitleAtTime(currentTime);
    
    if (!activeSub) {
        if (_lastBlurState.visible) {
            dynamicBlurOverlay.style.opacity = '0';
            dynamicBlurOverlay.style.visibility = 'hidden';
            _lastBlurState.visible = false;
            _lastBlurState.subId = null;
        }
        return;
    }
    
    // 1. Lấy chiều rộng và vị trí X (Ưu tiên tọa độ AI Scan nếu có)
    const widthPct = activeSub.widthPct || 35;
    
    // 2. Lấy tọa độ Y & H từ slider hoặc vùng OCR
    const sliderY = parseFloat(document.getElementById('blurYPos')?.value);
    let ocrY = !isNaN(sliderY) ? sliderY : ((currentRegion && typeof currentRegion.y === 'number') ? currentRegion.y : 81.5);
    let ocrH = (currentRegion && typeof currentRegion.h === 'number') ? currentRegion.h : 9.5;
    const ocrX = (currentRegion && typeof currentRegion.x === 'number') ? currentRegion.x : 20;
    const ocrW = (currentRegion && typeof currentRegion.w === 'number') ? currentRegion.w : 60;
    
    // 3. Vị trí X: Nếu có AI box và checkbox AI Scan bật, dùng trực tiếp leftPct; nếu không, căn giữa
    const isAiScanEnabled = document.getElementById('blurUseAiScan')?.checked ?? true;
    let leftPct;
    if (isAiScanEnabled && activeSub.leftPct != null && activeSub.aiBox) {
        leftPct = activeSub.leftPct;
        if (activeSub.aiBox.y_pct != null && isNaN(sliderY)) {
            ocrY = activeSub.aiBox.y_pct;
        }
        if (activeSub.aiBox.h_pct != null) {
            ocrH = Math.max(ocrH, activeSub.aiBox.h_pct);
        }
    } else {
        const centerX = (currentRegion && currentRegion.w) ? (ocrX + ocrW / 2) : 50;
        leftPct = centerX - (widthPct / 2);
        leftPct = Math.max(1, Math.min(99 - widthPct, leftPct));
    }
    
    const blurVal = parseInt(document.getElementById('dynBlurIntensity')?.value) || parseInt(document.getElementById('subBgBlur')?.value) || 15;
    const hasAiBorder = !!(activeSub.aiBox && isAiScanEnabled);

    // STATE DIFF CHECK: Nếu trạng thái giống hệt frame trước, không đụng vào DOM / Shader GPU!
    if (
        _lastBlurState.visible === true &&
        _lastBlurState.subId === activeSub.id &&
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
        subId: activeSub.id,
        left: leftPct,
        top: ocrY,
        width: widthPct,
        height: ocrH,
        blur: blurVal,
        aiBorder: hasAiBorder
    };

    // 4. Cập nhật style cho dynamicBlurOverlay (Zero-Reflow GPU composite)
    dynamicBlurOverlay.style.backdropFilter = `blur(${blurVal}px)`;
    dynamicBlurOverlay.style.webkitBackdropFilter = `blur(${blurVal}px)`;
    dynamicBlurOverlay.style.top = `${ocrY}%`;
    dynamicBlurOverlay.style.height = `${ocrH}%`;
    dynamicBlurOverlay.style.left = `${leftPct}%`;
    dynamicBlurOverlay.style.width = `${widthPct}%`;
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
                subtitles: srtData.map((s, idx) => ({
                    id: s.id || (idx + 1),
                    startSeconds: s.startSeconds,
                    endSeconds: s.endSeconds,
                    text: s.text || s.original_text || ''
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
                            if (statusText) statusText.textContent = `Đang quét ${event.index + 1}/${event.total} câu...`;
                            updateAiScanBadge();
                        } else if (event.type === 'done') {
                            if (progBar) progBar.style.width = '100%';
                            if (progText) progText.textContent = '100%';
                            if (statusText) statusText.textContent = `Hoàn thành (${event.detected_count}/${event.total_scanned} câu)!`;
                            
                            // Auto check blurUseAiScan
                            const chkAi = document.getElementById('blurUseAiScan');
                            if (chkAi) chkAi.checked = true;
                            
                            updateDynamicBlurIntervals();
                            showToast(`🎉 Đã quét xong tọa độ AI cho ${event.detected_count}/${event.total_scanned} câu phụ đề!`, "success");
                            
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

function resetAiBoxes() {
    if (typeof srtData === 'undefined' || !Array.isArray(srtData)) return;
    srtData.forEach(s => {
        delete s.aiBox;
    });
    updateDynamicBlurIntervals();
    updateAiScanBadge();
    showToast("Đã xóa tọa độ AI. Khung làm mờ trở về chế độ tính theo độ dài mặc định.", "info");
}

document.getElementById('btnScanAiCurrentFrame')?.addEventListener('click', scanAiCurrentFrame);
document.getElementById('btnScanAiAllSubs')?.addEventListener('click', scanAiAllSubtitles);
document.getElementById('btnResetAiBoxes')?.addEventListener('click', resetAiBoxes);
document.getElementById('blurUseAiScan')?.addEventListener('change', (e) => {
    updateDynamicBlurIntervals();
});

// Cho phép kéo thả trực tiếp box blur trên video để vi chỉnh vị trí độ cao (Y) theo ý muốn
if (dynamicBlurOverlay) {
    let isDraggingBlur = false;
    let blurDragStartY = 0;
    let blurInitialTop = 81.5;

    dynamicBlurOverlay.style.cursor = 'ns-resize';
    dynamicBlurOverlay.style.pointerEvents = 'auto';

    dynamicBlurOverlay.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        isDraggingBlur = true;
        blurDragStartY = e.clientY;
        const vContainer = document.querySelector('.video-container');
        const rect = vContainer ? vContainer.getBoundingClientRect() : { height: 400 };
        blurInitialTop = (currentRegion && typeof currentRegion.y === 'number') ? currentRegion.y : 81.5;
        
        function onMouseMove(moveEvent) {
            if (!isDraggingBlur) return;
            const deltaY = moveEvent.clientY - blurDragStartY;
            const deltaPercent = (deltaY / rect.height) * 100;
            let newY = Math.round((blurInitialTop + deltaPercent) * 10) / 10;
            newY = Math.max(10, Math.min(95, newY));
            
            if (!currentRegion) {
                currentRegion = { x: 20, y: newY, w: 60, h: 9.5 };
            } else {
                currentRegion.y = newY;
            }
            
            const sliderY = document.getElementById('blurYPos');
            const labelY = document.getElementById('blurYPosVal');
            if (sliderY) sliderY.value = newY;
            if (labelY) labelY.textContent = `${newY}%`;
            
            updateDynamicBlurOverlayVisibility();
        }
        
        function onMouseUp() {
            isDraggingBlur = false;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        }
        
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    });
}

// Smooth Animation Loop (~30-60fps) với state caching giúp loại bỏ 100% hiện tượng nghẽn GPU Compositor
let blurAnimFrameId = null;
let _lastBlurAnimTime = 0;
function syncBlurPreviewHighPrecision(now) {
    if (!now || (now - _lastBlurAnimTime) >= 28) {
        _lastBlurAnimTime = now || performance.now();
        updateDynamicBlurOverlayVisibility();
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
if (dynamicBlurHeader && dynamicBlurSubConfig) {
    dynamicBlurHeader.addEventListener('click', (e) => {
        if (e.target.id === 'reviewBlurOriginalSubtitles') return;
        const isHidden = dynamicBlurSubConfig.style.display === 'none';
        dynamicBlurSubConfig.style.display = isHidden ? 'flex' : 'none';
        if (dynamicBlurChevron) {
            dynamicBlurChevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
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

const reviewBlurCheckbox = document.getElementById('reviewBlurOriginalSubtitles');
if (reviewBlurCheckbox) {
    reviewBlurCheckbox.addEventListener('change', () => {
        if (dynamicBlurSubConfig) {
            dynamicBlurSubConfig.style.display = reviewBlurCheckbox.checked ? 'flex' : 'none';
            if (dynamicBlurChevron) {
                dynamicBlurChevron.style.transform = reviewBlurCheckbox.checked ? 'rotate(0deg)' : 'rotate(-90deg)';
            }
        }
        updateDynamicBlurOverlayVisibility();
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

timeline.addEventListener('mousedown', () => { isSeekingTimeline = true; });
timeline.addEventListener('touchstart', () => { isSeekingTimeline = true; });

timeline.addEventListener('input', (e) => {
    if (videoPlayer.duration) {
        const seekTime = (parseFloat(e.target.value) / 100) * videoPlayer.duration;
        safeSeekVideo(seekTime, false);
        
        let curMins = Math.floor(seekTime / 60);
        let curSecs = Math.floor(seekTime % 60);
        let durMins = Math.floor(videoPlayer.duration / 60);
        let durSecs = Math.floor(videoPlayer.duration % 60);
        curSecs = curSecs < 10 ? '0' + curSecs : curSecs;
        durSecs = durSecs < 10 ? '0' + durSecs : durSecs;
        timeDisplay.textContent = `${curMins}:${curSecs} / ${durMins}:${durSecs}`;
    }
});

const onSeekEnd = (e) => {
    if (isSeekingTimeline && videoPlayer.duration) {
        const seekTime = (parseFloat(e.target.value) / 100) * videoPlayer.duration;
        safeSeekVideo(seekTime, false);
        isSeekingTimeline = false;
    }
};

timeline.addEventListener('change', onSeekEnd);
timeline.addEventListener('mouseup', onSeekEnd);
timeline.addEventListener('touchend', onSeekEnd);

btnPreviewOriginal.addEventListener('click', () => {
    btnPreviewOriginal.classList.add('active');
    btnPreviewEdited.classList.remove('active');
    
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
            if (e.target.closest('#videoZoomHud') || e.target.closest('#dynamicBlurOverlay') || e.target.closest('#videoZoomBox') || e.target.closest('#videoLogoOverlay')) return;
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
    if (!videoZoomBox || !videoContainer) return;
    const cW = videoContainer.clientWidth;
    const cH = videoContainer.clientHeight;
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

function setupInteractiveVideoZoomBox() {
    if (!videoZoomBox || !videoContainer) return;

    let isResizing = false;
    let isDraggingBox = false;
    let currentHandle = null;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0, startWidth = 0, startHeight = 0;

    // 1. Center drag (Pan / Move viewpoint)
    videoZoomBox.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('zoom-resize-handle')) return;
        if (e.button !== 0) return;
        e.stopPropagation();
        e.preventDefault();

        isDraggingBox = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = videoZoomBox.getBoundingClientRect();
        const parentRect = videoContainer.getBoundingClientRect();
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
            const parentRect = videoContainer.getBoundingClientRect();
            startLeft = rect.left - parentRect.left;
            startTop = rect.top - parentRect.top;
            startWidth = rect.width;
            startHeight = rect.height;
        });
    });

    window.addEventListener('mousemove', (e) => {
        if (!isResizing && !isDraggingBox) return;
        e.preventDefault();

        const cW = videoContainer.clientWidth;
        const cH = videoContainer.clientHeight;
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
                if (isVipTier) {
                    openaiKeyEl.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                } else if (data.openaiKey && !data.openaiKey.startsWith('•')) {
                    openaiKeyEl.value = data.openaiKey;
                }
            }
            if (openSpeakerApiKeyEl) {
                if (isVipTier) {
                    openSpeakerApiKeyEl.value = '•••••••••••••••••••••••• [Bản Quyền VIP - Kích Hoạt Sẵn]';
                } else if (data.openSpeakerApiKey && !data.openSpeakerApiKey.startsWith('•')) {
                    openSpeakerApiKeyEl.value = data.openSpeakerApiKey;
                }
            }
            if (openaiBaseUrlEl && data.openaiBaseUrl) {
                openaiBaseUrlEl.value = data.openaiBaseUrl;
            }
            if (openaiModelEl && data.openaiModel) {
                openaiModelEl.value = data.openaiModel;
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
        // Gói VIP / 1 Năm: Hiển thị banner VIP + Hiện đầy đủ các ô API nhưng MASK và BẢO VỆ CHỐNG COPY
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

        // Mask and protect OpenAI Key
        if (openaiKey) {
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

        // Mask and protect OpenSpeaker Key
        if (openSpeakerApiKey) {
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
            if (openaiKey.value.startsWith('•')) openaiKey.value = '';
            openaiKey.readOnly = false;
            openaiKey.type = 'password';
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
            if (openSpeakerApiKey.value.startsWith('•')) openSpeakerApiKey.value = '';
            openSpeakerApiKey.readOnly = false;
            openSpeakerApiKey.type = 'password';
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
            if (openaiKey.value.startsWith('•')) openaiKey.value = '';
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
        }

        if (openSpeakerApiKey) {
            if (openSpeakerApiKey.value.startsWith('•')) openSpeakerApiKey.value = '';
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

        loadApiKeys();
    }
}

if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
        if (settingsModal) {
            settingsModal.style.display = 'flex';
            settingsModal.classList.add('active');
            updateSettingsModalPermissions(currentLicenseState);
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
            if (openaiKey.value.startsWith('•')) openaiKey.value = '';
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
            if (openSpeakerApiKey.value.startsWith('•')) openSpeakerApiKey.value = '';
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

const btnTestApiKey = document.getElementById('btnTestApiKey');
if (btnTestApiKey) {
    btnTestApiKey.addEventListener('click', async () => {
        const openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
        const openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
        const openaiModel = document.getElementById('openaiModel')?.value?.trim() || 'gpt-5.6-luna';

        const isVip = (currentLicenseState && (currentLicenseState.tier === 'vip' || currentLicenseState.tier === 'yearly'));
        if (!openaiKey && !isVip) {
            showToast('⚠️ Vui lòng nhập OpenAI API Key trước khi test!', 'warning');
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
                showToast(data.message || '🎉 API Key OpenAI hợp lệ!', 'success');
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

if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async () => {
        saveSettingsBtn.disabled = true;
        try {
            const payload = {
                openaiKey: document.getElementById('openaiKey')?.value?.trim() || '',
                openaiBaseUrl: document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1',
                openaiModel: document.getElementById('openaiModel')?.value?.trim() || 'gpt-5.6-luna',
                openSpeakerApiKey: document.getElementById('openSpeakerApiKey')?.value?.trim() || ''
            };
            await fetch('/api/keys', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

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

// Generic Drawing Logic
const btnDrawRegion = document.getElementById('btnDrawRegion');
const btnDrawSubRegion = document.getElementById('btnDrawSubRegion');
const videoOverlay = document.getElementById('videoOverlay');
const ocrRegionCoords = document.getElementById('ocrRegionCoords');

let isDrawing = false;
let startX, startY;
let drawBox = null;
let currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 }; // for OCR & Dynamic Blur reference
let currentSubRegion = null; // for Subtitle
let drawMode = 'ocr'; // 'ocr' or 'sub'

let subPreviewBox = null; // persistent box for subtitle preview

function startDrawMode(mode) {
    drawMode = mode;
    videoOverlay.style.display = 'block';
    if(drawBox) {
        drawBox.remove();
        drawBox = null;
    }
}

if (btnDrawRegion) btnDrawRegion.addEventListener('click', () => startDrawMode('ocr'));
if (btnDrawSubRegion) btnDrawSubRegion.addEventListener('click', () => startDrawMode('sub'));

videoOverlay.addEventListener('mousedown', (e) => {
    isDrawing = true;
    const rect = videoOverlay.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;
    
    drawBox = document.createElement('div');
    if (drawMode === 'ocr') {
        drawBox.className = 'ocr-draw-box';
    } else {
        // Remove existing sub preview if drawing a new one
        if (subPreviewBox) {
            subPreviewBox.remove();
            subPreviewBox = null;
        }
        drawBox.className = 'sub-preview-box';
        // Apply current subtitle styles for immediate preview
        applySubStylesToElement(drawBox);
        drawBox.innerHTML = '<span class="sub-text-inner">Phụ đề mẫu</span>';
    }
    
    drawBox.style.left = startX + 'px';
    drawBox.style.top = startY + 'px';
    drawBox.style.width = '0px';
    drawBox.style.height = '0px';
    videoOverlay.appendChild(drawBox);
});

videoOverlay.addEventListener('mousemove', (e) => {
    if (!isDrawing) return;
    const rect = videoOverlay.getBoundingClientRect();
    let currentX = e.clientX - rect.left;
    let currentY = e.clientY - rect.top;
    
    currentX = Math.max(0, Math.min(currentX, rect.width));
    currentY = Math.max(0, Math.min(currentY, rect.height));
    
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
    isDrawing = false;
    videoOverlay.style.display = 'none'; 
    
    if (drawBox) {
        videoContainer.appendChild(drawBox);
        const rect = videoContainer.getBoundingClientRect();
        const left = parseFloat(drawBox.style.left);
        const top = parseFloat(drawBox.style.top);
        const width = parseFloat(drawBox.style.width);
        const height = parseFloat(drawBox.style.height);
        
        const pX = Math.round((left / rect.width) * 100);
        const pY = Math.round((top / rect.height) * 100);
        const pW = Math.round((width / rect.width) * 100);
        const pH = Math.round((height / rect.height) * 100);
        
        if (drawMode === 'ocr') {
            currentRegion = {x: pX, y: pY, w: pW, h: pH};
            if(ocrRegionCoords) ocrRegionCoords.textContent = `X: ${pX}% • Y: ${pY}% • W: ${pW}% • H: ${pH}%`;
            
            const editorInputVideoPath = document.getElementById('editorInputVideoPath');
            const filename = (editorInputVideoPath && editorInputVideoPath.value) ? (editorInputVideoPath.value.split('\\\\').pop().split('/').pop()) : 'Chưa chọn video...';
            const ocrRegionFilename = document.getElementById('ocrRegionFilename');
            if(ocrRegionFilename) ocrRegionFilename.textContent = filename;

            // Kích hoạt kéo thả và co giãn 8 hướng cho OCR draw box
            setupResizableAndDraggableBox(drawBox, (newPx, newPy, newPw, newPh) => {
                currentRegion = { x: newPx, y: newPy, w: newPw, h: newPh };
                if (ocrRegionCoords) ocrRegionCoords.textContent = `X: ${newPx}% • Y: ${newPy}% • W: ${newPw}% • H: ${newPh}%`;
                
                // Đồng bộ sang thanh kéo vị trí Y ở tab Review nếu có
                const sliderY = document.getElementById('blurYPos');
                const labelY = document.getElementById('blurYPosVal');
                if (sliderY) sliderY.value = newPy;
                if (labelY) labelY.textContent = `${newPy}%`;
                updateDynamicBlurOverlayVisibility();
            });
        } else if (drawMode === 'sub') {
            currentSubRegion = {x: pX, y: pY, w: pW, h: pH, customPos: true};
            subPreviewBox = drawBox; // Keep it persistent on the video container
            
            subPreviewBox.style.position = 'absolute';
            subPreviewBox.style.left = `${pX}%`;
            subPreviewBox.style.top = `${pY}%`;
            subPreviewBox.style.width = `${pW}%`;
            subPreviewBox.style.height = `${pH}%`;
            subPreviewBox.style.bottom = 'auto';
            
            // Cập nhật thanh trượt kích thước & vị trí
            syncSubRegionInputs(pX, pY, pW, pH);

            // Kích hoạt kéo thả và co giãn 8 hướng cho subPreviewBox
            setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
                currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
                syncSubRegionInputs(newPx, newPy, newPw, newPh);
            });
            
            applySubStylesToElement(subPreviewBox);
        }
    }
});

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
}

function setupResizableAndDraggableBox(box, onUpdate) {
    if (!box) return;
    
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

    let activeAction = null; // null | 'move' | 'nw' | 'n' | 'ne' | ...
    let startMouseX = 0, startMouseY = 0;
    let initialBox = { left: 0, top: 0, width: 0, height: 0 };
    let containerRect = null;

    function onMouseDown(e) {
        const handle = e.target.closest('.box-resize-handle');
        if (handle) {
            activeAction = handle.dataset.handle;
        } else if (e.target === box || box.contains(e.target)) {
            activeAction = 'move';
        } else {
            return;
        }

        const vContainer = document.querySelector('.video-container') || videoContainer;
        if (!vContainer) return;
        
        containerRect = vContainer.getBoundingClientRect();
        const boxRect = box.getBoundingClientRect();

        initialBox = {
            left: boxRect.left - containerRect.left,
            top: boxRect.top - containerRect.top,
            width: boxRect.width,
            height: boxRect.height
        };

        startMouseX = e.clientX;
        startMouseY = e.clientY;

        e.stopPropagation();
        e.preventDefault();

        function onMouseMove(moveEvent) {
            if (!activeAction || !containerRect) return;

            const dx = moveEvent.clientX - startMouseX;
            const dy = moveEvent.clientY - startMouseY;

            let newLeft = initialBox.left;
            let newTop = initialBox.top;
            let newWidth = initialBox.width;
            let newHeight = initialBox.height;

            const minW = 24; // Tối thiểu 24px
            const minH = 16; // Tối thiểu 16px

            if (activeAction === 'move') {
                newLeft = Math.max(0, Math.min(initialBox.left + dx, containerRect.width - newWidth));
                newTop = Math.max(0, Math.min(initialBox.top + dy, containerRect.height - newHeight));
            } else {
                // Co giãn theo các cạnh và góc
                if (activeAction.includes('e')) {
                    newWidth = Math.max(minW, Math.min(initialBox.width + dx, containerRect.width - initialBox.left));
                }
                if (activeAction.includes('s')) {
                    newHeight = Math.max(minH, Math.min(initialBox.height + dy, containerRect.height - initialBox.top));
                }
                if (activeAction.includes('w')) {
                    const maxDx = initialBox.left;
                    const clampedDx = Math.max(-maxDx, Math.min(dx, initialBox.width - minW));
                    newLeft = initialBox.left + clampedDx;
                    newWidth = initialBox.width - clampedDx;
                }
                if (activeAction.includes('n')) {
                    const maxDy = initialBox.top;
                    const clampedDy = Math.max(-maxDy, Math.min(dy, initialBox.height - minH));
                    newTop = initialBox.top + clampedDy;
                    newHeight = initialBox.height - clampedDy;
                }
            }

            // Gán pixel tạm thời khi đang rê chuột
            box.style.bottom = 'auto';
            box.style.left = `${newLeft}px`;
            box.style.top = `${newTop}px`;
            box.style.width = `${newWidth}px`;
            box.style.height = `${newHeight}px`;

            // Tính tỷ lệ %
            const pX = Math.round((newLeft / containerRect.width) * 1000) / 10;
            const pY = Math.round((newTop / containerRect.height) * 1000) / 10;
            const pW = Math.round((newWidth / containerRect.width) * 1000) / 10;
            const pH = Math.round((newHeight / containerRect.height) * 1000) / 10;

            if (onUpdate) {
                onUpdate(pX, pY, pW, pH, false);
            }
        }

        function onMouseUp() {
            if (!activeAction) return;

            if (containerRect) {
                const boxRect = box.getBoundingClientRect();
                const curLeft = boxRect.left - containerRect.left;
                const curTop = boxRect.top - containerRect.top;
                const curW = boxRect.width;
                const curH = boxRect.height;

                const pX = Math.round((curLeft / containerRect.width) * 1000) / 10;
                const pY = Math.round((curTop / containerRect.height) * 1000) / 10;
                const pW = Math.round((curW / containerRect.width) * 1000) / 10;
                const pH = Math.round((curH / containerRect.height) * 1000) / 10;

                box.style.bottom = 'auto';
                box.style.left = `${pX}%`;
                box.style.top = `${pY}%`;
                box.style.width = `${pW}%`;
                box.style.height = `${pH}%`;

                if (onUpdate) {
                    onUpdate(pX, pY, pW, pH, true);
                }
            }

            activeAction = null;
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    box.style.cursor = 'move';
    box.style.pointerEvents = 'auto';
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
            subPreviewBox.style.left = `${x}%`;
            subPreviewBox.style.top = `${y}%`;
            subPreviewBox.style.width = `${w}%`;
            subPreviewBox.style.height = `${h}%`;
            subPreviewBox.style.bottom = 'auto';
            applySubStylesToElement(subPreviewBox);
        }
    });
});

const btnCenterSubBox = document.getElementById('btnCenterSubBox');
if (btnCenterSubBox) {
    btnCenterSubBox.addEventListener('click', () => {
        const w = parseFloat(document.getElementById('subBoxWidth')?.value || (currentSubRegion ? currentSubRegion.w : 60));
        const centeredX = Math.max(0, Math.round(((100 - w) / 2) * 10) / 10);
        const elX = document.getElementById('subBoxX');
        const valX = document.getElementById('subBoxXVal');
        if (elX) elX.value = centeredX;
        if (valX) valX.textContent = `${centeredX}%`;
        
        if (!currentSubRegion) {
            currentSubRegion = { x: centeredX, y: 81.5, w: w, h: 9.5, customPos: true };
        } else {
            currentSubRegion.x = centeredX;
            currentSubRegion.customPos = true;
        }
        
        if (subPreviewBox) {
            subPreviewBox.style.left = `${centeredX}%`;
            applySubStylesToElement(subPreviewBox);
        }
    });
}

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

function applySubStylesToElement(el) {
    if (!el) return;
    
    const font = document.getElementById('subFont')?.value || 'Montserrat';
    const color = document.getElementById('subColorPicker')?.value || '#ffffff';
    const outlineColor = document.getElementById('subOutlineColorPicker')?.value || '#000000';
    const shadowColor = document.getElementById('subShadowColorPicker')?.value || '#000000';
    const size = parseInt(document.getElementById('subSize')?.value) || 24;
    const outline = parseInt(document.getElementById('subOutline')?.value) || 1;
    const shadowOffset = parseInt(document.getElementById('subShadowOffset')?.value) || 0;
    const marginY = parseInt(document.getElementById('subMarginY')?.value) || 30;
    const bgStyle = document.getElementById('subBgStyle')?.value || 'none';
    
    el.style.display = 'flex';
    el.style.justifyContent = subTextAlign === 'left' ? 'flex-start' : (subTextAlign === 'right' ? 'flex-end' : 'center');
    el.style.alignItems = 'center';
    el.style.textAlign = subTextAlign;
    el.style.fontFamily = font;
    el.style.fontSize = `${size}px`;
    el.style.color = color;
    el.style.fontWeight = isSubBold ? 'bold' : 'normal';
    el.style.fontStyle = isSubItalic ? 'italic' : 'normal';
    el.style.textTransform = isSubUppercase ? 'uppercase' : 'none';
    
    // Position handling (Only for on-video overlay, not live preview box):
    if (el.id !== 'subLivePreviewBox') {
        if (currentSubRegion && currentSubRegion.customPos) {
            if (currentSubRegion.x !== undefined) el.style.left = `${currentSubRegion.x}%`;
            if (currentSubRegion.y !== undefined) {
                el.style.top = `${currentSubRegion.y}%`;
                el.style.bottom = 'auto';
            }
            if (currentSubRegion.w !== undefined) el.style.width = `${currentSubRegion.w}%`;
            if (currentSubRegion.h !== undefined) el.style.height = `${currentSubRegion.h}%`;
        } else {
            el.style.bottom = `${marginY}px`;
            el.style.top = 'auto';
            el.style.left = '10%';
            el.style.width = '80%';
            el.style.height = 'auto';
            el.style.minHeight = '40px';
        }
    }
    
    // Text outline & drop shadow combination
    let shadows = [];
    if (outline > 0) {
        shadows.push(`-${outline}px -${outline}px 0 ${outlineColor}`);
        shadows.push(`${outline}px -${outline}px 0 ${outlineColor}`);
        shadows.push(`-${outline}px ${outline}px 0 ${outlineColor}`);
        shadows.push(`${outline}px ${outline}px 0 ${outlineColor}`);
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
    // 1. Update Live Preview Box inside the card
    const liveBox = document.getElementById('subLivePreviewBox');
    if (liveBox) {
        applySubStylesToElement(liveBox);
    }

    // 2. Update Overlay on Video Player
    const vContainer = document.querySelector('.video-container');
    if (!subPreviewBox && vContainer) {
        subPreviewBox = document.createElement('div');
        subPreviewBox.className = 'sub-preview-box';
        vContainer.appendChild(subPreviewBox);
        if (!currentSubRegion) {
            currentSubRegion = { x: 20, y: 81.5, w: 60, h: 9.5, customPos: true };
        }
        
        setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
            currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
            syncSubRegionInputs(newPx, newPy, newPw, newPh);
        });
    }
    
    if (subPreviewBox) {
        applySubStylesToElement(subPreviewBox);
        
        const isEditedMode = btnPreviewEdited && btnPreviewEdited.classList.contains('active');
        const overlay = document.getElementById('videoOverlay');
        const isDrawingMode = overlay && overlay.style.display === 'block' && typeof drawMode !== 'undefined' && drawMode === 'sub';
        
        if (isEditedMode || isDrawingMode) {
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
            textSpan.innerHTML = displayText.replace(/\n/g, '<br>');
            
            // Đảm bảo các điểm neo luôn có mặt
            if (!subPreviewBox.querySelector('.box-resize-handle')) {
                setupResizableAndDraggableBox(subPreviewBox, (newPx, newPy, newPw, newPh) => {
                    currentSubRegion = { x: newPx, y: newPy, w: newPw, h: newPh, customPos: true };
                    syncSubRegionInputs(newPx, newPy, newPw, newPh);
                });
            }
            
            subPreviewBox.style.display = 'flex';
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
    
    const payload = {
        video_path: inputPathEl.value,
        region: currentRegion,
        fps: parseInt(fps),
        threads: parseInt(threads),
        device: device
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


async function loadSrtToEditor(path) {
    try {
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
            return {
                ...s,
                startSeconds: startSec !== null ? startSec : 0,
                endSeconds: endSec !== null ? endSec : 0,
                selected: false
            };
        });
        
        // Swap Views
        if(configView) configView.style.display = 'none';
        if(editorView) editorView.style.display = 'flex';
        
        renderSrtTable();
        showToast('Đã tải bản SRT thành công!', 'success');
        
        // Update Dynamic Blur intervals for preview
        if (typeof updateDynamicBlurIntervals === 'function') {
            updateDynamicBlurIntervals();
            updateDynamicBlurOverlayVisibility();
        }
        
        // Auto activate "Bản sau khi sửa" mode to preview subtitles and styles
        if (btnPreviewEdited) {
            btnPreviewEdited.click();
        }
        
    } catch (e) {
        showToast('Lỗi hệ thống: ' + e.message, 'error');
    }
}

function renderSrtTable() {
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
        if (activeFilter === 'long' && sub.text.length < 50) return false; // arbitrary length for "too long"
        if (activeFilter === 'untranslated' && sub.translation.trim() !== '') return false;
        if (activeFilter === 'error' && !sub.text.trim()) return false;
        
        return true;
    });
    
    filtered.forEach(sub => {
        const tr = document.createElement('tr');
        
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
        tdTime.textContent = sub.time;
        
        const tdAction = document.createElement('td');
        tdAction.style.textAlign = 'center';
        
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
            const voiceId = document.getElementById('dubbingVoiceInput')?.value || 'local_ngoc_huyen';
            const speed = parseFloat(document.getElementById('dubbingSpeed')?.value || 1.0);
            
            btnVoicePlay.innerHTML = `⏳`;
            try {
                const res = await fetch('/api/tts/sentence_preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: textToSpeak, voice_id: voiceId, speed })
                });
                const data = await res.json();
                if (data.success && data.audio_url) {
                    const audio = new Audio(data.audio_url);
                    btnVoicePlay.innerHTML = `🔊`;
                    audio.onended = () => {
                        btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
                    };
                    audio.onerror = () => {
                        btnVoicePlay.innerHTML = `<svg viewBox="0 0 24 24" width="15" height="15" stroke="#38bdf8" stroke-width="2" fill="none"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
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
        
        const tdTrans = document.createElement('td');
        tdTrans.textContent = sub.translation || 'Chưa dịch...';
        if (sub.translation) tdTrans.classList.add('translated');
        
        // Single click to edit text or translation
        const setupInlineEdit = (cell, fieldName) => {
            cell.addEventListener('click', () => {
                if (cell.querySelector('input')) return; // Already editing
                
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'srt-inline-input';
                input.value = sub[fieldName];
                
                cell.innerHTML = '';
                cell.appendChild(input);
                input.focus();
                
                const save = () => {
                    sub[fieldName] = input.value;
                    renderSrtTable();
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
        
        srtTableBody.appendChild(tr);
    });
    
    updateBottomBarStats();
}

function updateBottomBarStats() {
    const selectedCount = srtData.filter(s => s.selected).length;
    const btnDelSelSpan = document.querySelector('#btnDeleteSelected span');
    if (btnDelSelSpan) btnDelSelSpan.innerHTML = `Xóa đã chọn (${selectedCount})`;
    
    const translatedCount = srtData.filter(s => s.translation).length;
    const btnDelTransSpan = document.querySelector('#btnDeleteTranslation span');
    if (btnDelTransSpan) btnDelTransSpan.innerHTML = `Xóa bản dịch (${translatedCount})`;
}

// Event Listeners for Editor
if (srtSearchInput) srtSearchInput.addEventListener('input', renderSrtTable);
filterRadios.forEach(r => r.addEventListener('change', renderSrtTable));

if (srtSelectAll) {
    srtSelectAll.addEventListener('change', (e) => {
        srtData.forEach(sub => sub.selected = e.target.checked);
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

        // Progress bars & percentages (Quota: 1,000,000 Prompt, 1,000,000 Completion)
        const promptPctNum = Math.min(100, (this.stats.prompt_tokens / 1000000) * 100);
        const completionPctNum = Math.min(100, (this.stats.completion_tokens / 1000000) * 100);

        const promptPctElem = document.getElementById('tokenPromptPct');
        if (promptPctElem) promptPctElem.textContent = `${promptPctNum.toFixed(1)}%`;

        const completionPctElem = document.getElementById('tokenCompletionPct');
        if (completionPctElem) completionPctElem.textContent = `${completionPctNum.toFixed(1)}%`;

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

async function handleTranslateSubtitles(mode) {
    if (!checkFeaturePermission('can_access_editor', 'Dịch phụ đề')) return;

    if (!srtData || srtData.length === 0) {
        showToast('Không có phụ đề nào để dịch!', 'warning');
        return;
    }
    
    const selectedSubs = srtData.filter(s => s.selected);
    let targetSubs = selectedSubs.length > 0 ? selectedSubs : srtData;
    
    if (mode === 'ai') {
        const hasKey = await ensureAiKeyAvailable('openai', 'Dịch phụ đề AI');
        if (!hasKey) return;

        const choice = await showAiTranslateChoiceModal(targetSubs.length);
        if (!choice) return; // User cancelled
        
        if (choice === '20') {
            targetSubs = targetSubs.slice(0, 20);
        }
    }
    
    const totalSubs = targetSubs.length;
    
    const modeLabel = mode === 'free' ? 'Google Dịch (Miễn phí)' : (mode === 'ai' && totalSubs <= 20 ? 'AI (20 câu thử nghiệm)' : 'AI (OpenAI GPT)');
    const targetBtn = mode === 'free' ? btnTranslateSrt : btnTranslateAI;
    const origHtml = targetBtn ? targetBtn.innerHTML : '';
    
    // Auto-open Terminal / System Log so user sees live progress
    if (terminalOverlay && terminalOverlay.classList.contains('collapsed')) {
        terminalOverlay.classList.remove('collapsed');
        terminalOverlay.classList.add('expanded');
        if (toggleTerminalBtn) toggleTerminalBtn.textContent = 'Thu gọn';
    }
    
    const timeNow = () => new Date().toLocaleTimeString();
    appendLog(`[${timeNow()}] > [Dịch thuật] Bắt đầu dịch ${totalSubs} câu phụ đề bằng ${modeLabel}...`, 'info');
    
    if (targetBtn) {
        targetBtn.disabled = true;
    }
    if (btnTranslateSrt && mode !== 'free') btnTranslateSrt.disabled = true;
    if (btnTranslateAI && mode !== 'ai') btnTranslateAI.disabled = true;
    if (btnStopTranslate) {
        btnStopTranslate.style.display = 'inline-flex';
    }
    
    translateAbortController = new AbortController();
    isTranslatingCancelled = false;
    
    // Batch size: 25 for Free, 20 for AI
    const batchSize = mode === 'free' ? 25 : 20;
    let translatedCount = 0;
    let totalTokensAccum = 0;
    
    try {
        const openaiKeyEl = document.getElementById('openaiKey');
        const openaiBaseUrlEl = document.getElementById('openaiBaseUrl');
        const openaiModelEl = document.getElementById('openaiModel');
        
        const openai_key = openaiKeyEl ? openaiKeyEl.value.trim() : '';
        const openai_base_url = openaiBaseUrlEl ? openaiBaseUrlEl.value.trim() : 'https://api.openai.com/v1';
        const openai_model = openaiModelEl ? (openaiModelEl.value.trim() || 'gpt-5.6-luna') : 'gpt-5.6-luna';
        
        const subSourceLangEl = document.getElementById('subSourceLang');
        const subTargetLangEl = document.getElementById('subTargetLang');
        const source_lang = subSourceLangEl ? subSourceLangEl.value : 'auto';
        const target_lang = subTargetLangEl ? subTargetLangEl.value : 'vi';
        
        for (let i = 0; i < totalSubs; i += batchSize) {
            if (isTranslatingCancelled) {
                break;
            }
            const chunk = targetSubs.slice(i, i + batchSize);
            const chunkFrom = i + 1;
            const chunkTo = Math.min(i + batchSize, totalSubs);
            
            const payload = {
                subtitles: chunk,
                mode: mode,
                source_lang: source_lang,
                target_lang: target_lang
            };
            
            if (mode === 'ai') {
                if (openai_key && !openai_key.startsWith('•')) payload.openai_key = openai_key;
                if (openai_base_url) payload.openai_base_url = openai_base_url;
                if (openai_model) payload.openai_model = openai_model;
            }
            
            let res;
            try {
                res = await fetch('/api/translate_subtitles', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                    signal: translateAbortController.signal
                });
            } catch (fetchErr) {
                if (isTranslatingCancelled || fetchErr.name === 'AbortError') {
                    break;
                }
                throw fetchErr;
            }
            
            const data = await res.json();
            if (data.error) {
                appendLog(`[${timeNow()}] > [Dịch thuật - LỖI] Nhóm câu ${chunkFrom}-${chunkTo}: ${data.error}`, 'error');
                showToast(`Lỗi dịch nhóm câu ${chunkFrom}-${chunkTo}: ${data.error}`, 'error');
                break;
            }
            
            if (data.usage && mode === 'ai') {
                tokenTracker.record(`Dịch nhóm câu ${chunkFrom}-${chunkTo}`, data.usage, openai_model || 'gpt-4o-mini');
                totalTokensAccum += (data.usage.total_tokens || 0);
            }
            
            if (data.subtitles && Array.isArray(data.subtitles)) {
                const transMap = new Map();
                data.subtitles.forEach(s => transMap.set(String(s.id), s.translation));
                
                srtData.forEach(s => {
                    const trans = transMap.get(String(s.id));
                    if (trans) s.translation = trans;
                });
                
                translatedCount += data.subtitles.length;
                const percent = Math.round((translatedCount / totalSubs) * 100);
                
                appendLog(`[${timeNow()}] > [Dịch thuật] Đang dịch: ${translatedCount}/${totalSubs} câu (${percent}%)...`, 'info');
                
                if (targetBtn) {
                    targetBtn.innerHTML = `
                        <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
                        <span>Đang dịch (${percent}% - ${translatedCount}/${totalSubs})...</span>
                    `;
                }
                
                // Update table display in real-time as each batch completes
                renderSrtTable();
            }
        }
        
        if (isTranslatingCancelled) {
            appendLog(`[${timeNow()}] > [Dịch thuật] ⏹️ Đã dừng dịch theo yêu cầu. Đã lưu lại ${translatedCount}/${totalSubs} câu đã dịch thành công!`, 'warning');
            showToast(`Đã dừng dịch! Đã lưu lại ${translatedCount} câu đã dịch.`, 'info');
            renderSrtTable();
        } else if (translatedCount > 0) {
            const tokenMsg = totalTokensAccum > 0 ? ` (🪙 Tổng token: ${totalTokensAccum.toLocaleString()})` : '';
            appendLog(`[${timeNow()}] > [Dịch thuật] 🎉 Hoàn tất dịch ${translatedCount}/${totalSubs} câu phụ đề (${Math.round((translatedCount/totalSubs)*100)}%)!${tokenMsg}`, 'success');
            showToast(`Đã dịch xong ${translatedCount}/${totalSubs} câu phụ đề bằng ${modeLabel}!`, 'success');
            if (btnPreviewEdited) {
                btnPreviewEdited.click();
            }
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
        if (btnStopTranslate) {
            btnStopTranslate.style.display = 'none';
        }
    }
}

if (btnTranslateSrt) {
    btnTranslateSrt.addEventListener('click', () => handleTranslateSubtitles('free'));
}
if (btnTranslateAI) {
    btnTranslateAI.addEventListener('click', () => handleTranslateSubtitles('ai'));
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
        if (!srtData || srtData.length === 0) {
            showToast('Không có phụ đề nào để làm sạch!', 'warning');
            return;
        }

        const openaiKey = document.getElementById('openaiKey')?.value?.trim() || '';
        const openaiBaseUrl = document.getElementById('openaiBaseUrl')?.value?.trim() || 'https://api.openai.com/v1';
        const openaiModel = document.getElementById('openaiModel')?.value?.trim() || 'gpt-5.6-luna';

        const totalSubs = srtData.length;
        const timeNow = () => new Date().toLocaleTimeString();
        const origHtml = btnCleanSrtAI.innerHTML;
        btnCleanSrtAI.disabled = true;
        if (btnStopCleanSrtAI) {
            btnStopCleanSrtAI.style.display = 'inline-flex';
        }

        if (terminalOverlay && terminalOverlay.classList.contains('collapsed')) {
            terminalOverlay.classList.remove('collapsed');
            terminalOverlay.classList.add('expanded');
            if (toggleTerminalBtn) toggleTerminalBtn.textContent = 'Thu gọn';
        }

        appendLog(`[${timeNow()}] > [Làm sạch SRT] Bắt đầu gộp và làm sạch ${totalSubs} đoạn phụ đề bằng AI (${openaiModel})...`, 'info');
        showToast(`Bắt đầu làm sạch & gộp ${totalSubs} đoạn phụ đề theo từng nhóm...`, 'info');

        cleanSrtAbortController = new AbortController();
        isCleanSrtCancelled = false;

        const batchSize = 50;
        let allCleanedSubtitles = [];
        let processedCount = 0;
        let totalCleanTokens = 0;
        let hasError = false;

        try {
            for (let i = 0; i < totalSubs; i += batchSize) {
                if (isCleanSrtCancelled) {
                    break;
                }
                const chunk = srtData.slice(i, i + batchSize);
                const chunkFrom = i + 1;
                const chunkTo = Math.min(i + batchSize, totalSubs);

                btnCleanSrtAI.innerHTML = `
                    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" style="vertical-align: middle; animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg>
                    <span>Đang làm sạch (${Math.round((chunkTo/totalSubs)*100)}% - ${chunkTo}/${totalSubs})...</span>
                `;

                let res;
                try {
                    res = await fetch('/api/clean_subtitles_ai', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            subtitles: chunk,
                            openai_key: (openaiKey && !openaiKey.startsWith('•')) ? openaiKey : undefined,
                            openai_base_url: openaiBaseUrl,
                            openai_model: openaiModel
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
                    } catch (e) {
                        if (res.status === 405 || res.status === 404) {
                            errMsg = "Máy chủ Python đang chạy phiên bản cũ. Vui lòng tắt và khởi động lại 'python web_app.py'!";
                        }
                    }
                    appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Nhóm câu ${chunkFrom}-${chunkTo}: ${errMsg}`, 'error');
                    showToast(`Lỗi làm sạch nhóm câu ${chunkFrom}-${chunkTo}: ${errMsg}`, 'error');
                    hasError = true;
                    break;
                }

                const data = await res.json();
                if (data.error) {
                    appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Nhóm câu ${chunkFrom}-${chunkTo}: ${data.error}`, 'error');
                    showToast(`Lỗi làm sạch SRT: ${data.error}`, 'error');
                    hasError = true;
                    break;
                }

                if (data.usage) {
                    tokenTracker.record(`Làm sạch nhóm câu ${chunkFrom}-${chunkTo}`, data.usage, openaiModel || 'gpt-4o-mini');
                    totalCleanTokens += (data.usage.total_tokens || 0);
                }

                if (data.subtitles && Array.isArray(data.subtitles)) {
                    data.subtitles.forEach(item => {
                        allCleanedSubtitles.push({
                            ...item,
                            id: String(allCleanedSubtitles.length + 1)
                        });
                    });
                    processedCount += chunk.length;
                    const percent = Math.round((processedCount / totalSubs) * 100);
                    appendLog(`[${timeNow()}] > [Làm sạch SRT] Đang xử lý: ${processedCount}/${totalSubs} câu (${percent}%)...`, 'info');
                }
            }

            if (isCleanSrtCancelled) {
                if (allCleanedSubtitles.length > 0) {
                    // Ghép các đoạn đã làm sạch với các đoạn gốc chưa xử lý còn lại
                    const remainingOriginal = srtData.slice(processedCount);
                    const combined = allCleanedSubtitles.concat(remainingOriginal).map((item, idx) => ({
                        ...item,
                        id: String(idx + 1)
                    }));
                    srtData = combined;
                    renderSrtTable();
                    appendLog(`[${timeNow()}] > [Làm sạch SRT] ⏹️ Đã dừng làm sạch AI theo yêu cầu! Đã giữ lại ${allCleanedSubtitles.length} đoạn đã làm sạch và ${remainingOriginal.length} đoạn chưa xử lý.`, 'warning');
                    showToast(`Đã dừng làm sạch! Đã lưu lại các đoạn đã xử lý.`, 'info');
                } else {
                    appendLog(`[${timeNow()}] > [Làm sạch SRT] ⏹️ Đã hủy làm sạch AI.`, 'info');
                    showToast('Đã hủy làm sạch AI.', 'info');
                }
            } else if (allCleanedSubtitles.length > 0) {
                const oldCount = srtData.length;
                srtData = allCleanedSubtitles;
                renderSrtTable();
                const tokenSummary = totalCleanTokens > 0 ? ` (🪙 Tổng token: ${totalCleanTokens.toLocaleString()})` : '';
                appendLog(`[${timeNow()}] > [Làm sạch SRT] 🎉 Hoàn tất! Đã gộp từ ${oldCount} đoạn vụn thành ${srtData.length} câu hoàn chỉnh (5-8s/câu)${tokenSummary}.`, 'success');
                showToast(`Đã gộp ${oldCount} đoạn vụn thành ${srtData.length} câu hoàn chỉnh!`, 'success');
            } else if (!hasError) {
                showToast('Không có câu phụ đề nào được tạo ra!', 'warning');
            }
        } catch (err) {
            if (!isCleanSrtCancelled && err.name !== 'AbortError') {
                console.error(err);
                appendLog(`[${timeNow()}] > [Làm sạch SRT - LỖI] Lỗi kết nối: ${err.message}`, 'error');
                showToast('Lỗi kết nối khi làm sạch phụ đề: ' + err.message, 'error');
            }
        } finally {
            isCleanSrtCancelled = false;
            cleanSrtAbortController = null;
            btnCleanSrtAI.disabled = false;
            btnCleanSrtAI.innerHTML = origHtml;
            if (btnStopCleanSrtAI) {
                btnStopCleanSrtAI.style.display = 'none';
            }
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
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
            fetch(audioUrl)
                .then(r => r.arrayBuffer())
                .then(buf => {
                    const actx = new AudioContext();
                    return actx.decodeAudioData(buf);
                })
                .then(audioBuffer => {
                    const raw = audioBuffer.getChannelData(0);
                    const blockSize = Math.floor(raw.length / barCount);
                    const newHeights = [];
                    let maxAmp = 0.001;

                    for (let i = 0; i < barCount; i++) {
                        const start = i * blockSize;
                        let peak = 0;
                        for (let j = 0; j < blockSize; j += 4) {
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
                .catch(console.warn);
        }
    } catch (e) {
        console.warn(e);
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

            const payload = {
                text: text,
                voice: voiceVal,
                speed: parseFloat(ttsSpeed ? ttsSpeed.value : 1.0) || 1.0,
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
                ${v.avatar || '🎙️'}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
                    <span style="font-size: 14px; font-weight: 700; color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${v.name}">${v.name}</span>
                    <span style="font-size: 10px; padding: 2px 7px; border-radius: 4px; background: ${providerBadgeColor}18; color: ${providerBadgeColor}; border: 1px solid ${providerBadgeColor}40; text-transform: uppercase; font-weight: 700; white-space: nowrap;">${v.provider_name || v.provider}</span>
                </div>
                <div style="font-size: 11.5px; color: #94a3b8; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    ${v.tag || `${v.region || ''} • ${v.lang}`}
                </div>
            </div>
        </div>
        
        <div style="display: flex; align-items: center; justify-content: space-between; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px; margin-top: 2px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 11px; color: #64748b;">${v.gender === 'Female' ? 'Nữ' : 'Nam'} • ${v.region || v.lang}</span>
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

        const dubbingVoiceInput = document.getElementById('dubbingVoiceInput');
        const dubbingSelectedVoiceName = document.getElementById('dubbingSelectedVoiceName');
        if (dubbingVoiceInput) dubbingVoiceInput.value = v.id;
        if (dubbingSelectedVoiceName) dubbingSelectedVoiceName.textContent = v.name;

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

        // 1. Check if loaded voice has a direct preview_url (e.g. OpenSpeaker CDN or /samples/...)
        if (typeof allLoadedVoices !== 'undefined' && Array.isArray(allLoadedVoices)) {
            const found = allLoadedVoices.find(v => v.id === voiceId);
            if (found && found.preview_url && found.preview_url.trim()) {
                sampleUrl = found.preview_url.trim();
            }
        }

        // 2. Check local static samples
        if (!sampleUrl) {
            if (voiceId === 'diem_trinh') sampleUrl = '/samples/diem_trinh.wav';
            else if (voiceId === 'mai_linh') sampleUrl = '/samples/mai_linh.wav';
            else if (voiceId === 'ngoc_huyen') sampleUrl = '/samples/ngoc_huyen.wav';
            else if (voiceId === 'manh_dung') sampleUrl = '/samples/manh_dung.wav';
            else if (voiceId === 'thanh_dat') sampleUrl = '/samples/thanh_dat.wav';
            else if (voiceId === 'en_heart') sampleUrl = '/samples/en_heart.wav';
            else if (voiceId === 'rvc_ngochuyen_reviewphim') sampleUrl = '/samples/rvc_ngochuyen_reviewphim.wav';
            else if (voiceId.startsWith('rvc_')) sampleUrl = `/samples/${voiceId}.wav`;
        }

        // 3. Fallback to /api/tts/preview
        if (!sampleUrl) {
            const res = await fetch('/api/tts/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ voice: voiceId })
            });
            const data = await res.json();
            if (data.success && data.audio_url) {
                sampleUrl = data.audio_url;
            } else {
                throw new Error(data.error || 'Không thể tạo âm thanh mẫu');
            }
        }

        currentPreviewAudio = new Audio(sampleUrl);

        currentPreviewAudio.oncanplay = () => {
            if (btnEl && activePreviewBtn === btnEl) {
                setPreviewBtnState(btnEl, 'playing');
            }
        };

        currentPreviewAudio.onended = () => {
            if (btnEl) {
                setPreviewBtnState(btnEl, 'idle');
            }
            currentPreviewAudio = null;
            activePreviewBtn = null;
        };

        currentPreviewAudio.onerror = async () => {
            // Fallback to /api/tts/preview if static file gave 404
            if (!sampleUrl.includes('/api/tts/preview')) {
                try {
                    const fallbackRes = await fetch('/api/tts/preview', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ voice: voiceId })
                    });
                    const fbData = await fallbackRes.json();
                    if (fbData.success && fbData.audio_url) {
                        currentPreviewAudio = new Audio(fbData.audio_url);
                        await currentPreviewAudio.play();
                        if (btnEl) setPreviewBtnState(btnEl, 'playing');
                        currentPreviewAudio.onended = () => {
                            if (btnEl) setPreviewBtnState(btnEl, 'idle');
                            currentPreviewAudio = null;
                            activePreviewBtn = null;
                        };
                        return;
                    }
                } catch(e) {}
            }

            if (btnEl) {
                setPreviewBtnState(btnEl, 'idle');
            }
            currentPreviewAudio = null;
            activePreviewBtn = null;
            showToast('Không thể phát âm thanh nghe thử', 'warning');
        };

        await currentPreviewAudio.play();
        if (btnEl) {
            setPreviewBtnState(btnEl, 'playing');
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
        if (ocrDeviceSelect.value === 'cuda') {
            ocrThreadsLabel.innerText = 'Số luồng quét (GPU)';
            ocrThreadsTooltip.innerText = 'Số luồng nạp ảnh vào GPU cùng lúc. Tăng lên giúp xử lý nhanh hơn nếu GPU có nhiều VRAM, nhưng set cao quá sẽ gây tràn bộ nhớ (Out of Memory). Khuyên dùng: 1-2 cho GPU yếu, 3-4 cho GPU mạnh.';
        } else {
            ocrThreadsLabel.innerText = 'Số luồng quét (CPU)';
            ocrThreadsTooltip.innerText = 'Số lõi CPU chạy song song để nhận dạng chữ. Tăng số này giúp quét nhanh hơn nếu máy có CPU mạnh. Tránh set quá cao gây đơ máy (Khuyên dùng: 2-4).';
        }
    });
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
        reviewOrigVolVal.textContent = e.target.value + '%';
    });
}

// Target Minutes & Estimated Words (4.5 từ/giây = 270 từ/phút)
const reviewTargetMinutes = document.getElementById('reviewTargetMinutes');
const reviewEstimatedWords = document.getElementById('reviewEstimatedWords');
if (reviewTargetMinutes && reviewEstimatedWords) {
    reviewTargetMinutes.addEventListener('input', (e) => {
        const mins = parseInt(e.target.value) || 5;
        const words = Math.round(mins * 60 * 4.5);
        reviewEstimatedWords.textContent = `~${words.toLocaleString('vi-VN')} từ kịch bản`;
    });
}

// Aspect Ratio Toggles & Preview Frame Transformation
function updateReviewPlayerAspectRatio(ratio) {
    const rContainer = document.getElementById('reviewVideoContainer');
    const rPlayer = document.getElementById('reviewVideoPlayer');
    const rBadge = document.getElementById('reviewPlayerStatusBadge');

    if (!rContainer) return;

    if (ratio === '9:16') {
        rContainer.style.aspectRatio = '9 / 16';
        rContainer.style.maxWidth = '280px';
        rContainer.style.maxHeight = '500px';
        rContainer.style.margin = '10px auto';
        rContainer.style.borderRadius = '12px';
        rContainer.style.border = '2px solid rgba(56, 189, 248, 0.4)';
        rContainer.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.6), 0 0 15px rgba(56, 189, 248, 0.15)';
        if (rPlayer) {
            rPlayer.style.objectFit = 'cover';
        }
        if (rBadge && rPlayer && rPlayer.videoWidth) {
            rBadge.textContent = `Dọc 9:16 (${rPlayer.videoWidth}x${rPlayer.videoHeight})`;
            rBadge.style.color = '#38bdf8';
            rBadge.style.borderColor = 'rgba(56, 189, 248, 0.4)';
            rBadge.style.background = 'rgba(56, 189, 248, 0.12)';
        }
    } else {
        rContainer.style.aspectRatio = '16 / 9';
        rContainer.style.maxWidth = '100%';
        rContainer.style.maxHeight = '380px';
        rContainer.style.margin = '0';
        rContainer.style.borderRadius = '0';
        rContainer.style.border = 'none';
        rContainer.style.boxShadow = 'none';
        if (rPlayer) {
            rPlayer.style.objectFit = 'contain';
        }
        if (rBadge && rPlayer && rPlayer.videoWidth) {
            rBadge.textContent = `Ngang 16:9 (${rPlayer.videoWidth}x${rPlayer.videoHeight})`;
            rBadge.style.color = '#94a3b8';
            rBadge.style.borderColor = 'rgba(148, 163, 184, 0.25)';
            rBadge.style.background = 'rgba(148, 163, 184, 0.12)';
        }
    }
}

const reviewRatioVertical = document.getElementById('reviewRatioVertical');
const reviewRatioHorizontal = document.getElementById('reviewRatioHorizontal');
if (reviewRatioVertical && reviewRatioHorizontal) {
    reviewRatioVertical.addEventListener('click', () => {
        reviewRatioVertical.classList.add('active');
        reviewRatioVertical.style.borderColor = '#38bdf8';
        reviewRatioVertical.style.color = '#38bdf8';
        reviewRatioHorizontal.classList.remove('active');
        reviewRatioHorizontal.style.borderColor = '';
        reviewRatioHorizontal.style.color = '';
        reviewAspectRatio = '9:16';
        updateReviewPlayerAspectRatio('9:16');
    });
    reviewRatioHorizontal.addEventListener('click', () => {
        reviewRatioHorizontal.classList.add('active');
        reviewRatioHorizontal.style.borderColor = '#38bdf8';
        reviewRatioHorizontal.style.color = '#38bdf8';
        reviewRatioVertical.classList.remove('active');
        reviewRatioVertical.style.borderColor = '';
        reviewRatioVertical.style.color = '';
        reviewAspectRatio = '16:9';
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

if (reviewBgmEnabled && reviewBgmConfig) {
    reviewBgmEnabled.addEventListener('change', (e) => {
        reviewBgmConfig.style.opacity = e.target.checked ? '1' : '0.4';
        reviewBgmConfig.style.pointerEvents = e.target.checked ? 'auto' : 'none';
    });
}
if (reviewBgmVol && reviewBgmVolVal) {
    reviewBgmVol.addEventListener('input', (e) => {
        reviewBgmVolVal.textContent = e.target.value + '%';
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

if (btnSelectReviewInput) {
    btnSelectReviewInput.addEventListener('click', async () => {
        const path = await selectFile('video');
        if (path) {
            reviewInputVideoPath.value = path;
            loadReviewVideoPlayer(path);
            if (reviewVideoInsightBox) {
                reviewVideoInsightBox.style.display = 'flex';
                const filename = path.split('\\').pop().split('/').pop();
                if (reviewInsightDuration) reviewInsightDuration.textContent = `🎬 ${filename}`;
            }
        }
    });
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
            tts_threads: parseInt(document.getElementById('reviewTtsThreads')?.value || 3),
            target_minutes: document.getElementById('reviewTargetMinutes') ? (parseInt(document.getElementById('reviewTargetMinutes').value) || 5) : 5,
            aspect_ratio: reviewAspectRatio,
            pacing: reviewPacing,
            enable_zoom: document.getElementById('reviewEnableZoom')?.checked ?? true,
            video_zoom: parseFloat(document.getElementById('reviewVideoZoom')?.value || 105),
            blur_original_subtitles: document.getElementById('reviewTabBlurOriginalSubtitles') ? document.getElementById('reviewTabBlurOriginalSubtitles').checked : true,
            blur_intensity: parseInt(document.getElementById('reviewTabDynBlurIntensity')?.value) || 15,
            blur_lead_offset: parseFloat(document.getElementById('reviewTabBlurLeadOffset')?.value) || -180,
            blur_padding: parseFloat(document.getElementById('reviewTabBlurPadding')?.value) || 220,
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
            auto_subtitles: document.getElementById('reviewAutoSubtitles')?.checked || false,
            enable_scene_detect: document.getElementById('reviewEnableSceneDetect') ? document.getElementById('reviewEnableSceneDetect').checked : true,
            snap_threshold: parseFloat(document.getElementById('reviewSnapThreshold')?.value) || 0.6,
            min_clip_duration: parseFloat(document.getElementById('reviewMinClipDur')?.value) || 1.2,
            max_speed_ratio_deviation: 0.15,
            enable_crossfade: document.getElementById('reviewEnableCrossfade')?.checked || false,
            original_volume: parseInt(document.getElementById('reviewOrigVol')?.value) || 15,
            bgm: {
                enabled: document.getElementById('reviewBgmEnabled')?.checked || false,
                volume: parseInt(document.getElementById('reviewBgmVol')?.value) || 15,
                ducking: document.getElementById('reviewBgmDucking')?.checked || false
            },
            stem_separation: {
                enabled: document.getElementById('reviewStemSeparationEnabled')?.checked !== false,
                remove_vocals: document.getElementById('reviewRemoveVocals')?.checked !== false,
                keep_sfx: document.getElementById('reviewKeepSfx')?.checked !== false,
                mode: document.getElementById('reviewStemMode')?.value || 'ai_neural'
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
        payload.openai_model = document.getElementById('openaiModel')?.value || 'gpt-5.6-luna';
        
        // CHECK CACHE
        try {
            const cacheRes = await fetch('/api/review/check_cache', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ output_dir: payload.output_dir })
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
                const p = document.createElement('div');
                p.style.color = '#ef4444';
                p.textContent = `🛑 Lỗi máy chủ (${response.status}): ` + errText.substring(0, 500);
                terminal.appendChild(p);
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
                        if (msg.includes('🛑 Lỗi')) {
                            hasError = true;
                        }
                        const p = document.createElement('div');
                        p.textContent = msg;
                        terminal.appendChild(p);
                        terminal.scrollTop = terminal.scrollHeight;
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
                    encoderSelect.innerHTML = '';
                    data.encoders.forEach(enc => {
                        const opt = document.createElement('option');
                        opt.value = enc.id;
                        opt.textContent = enc.name + (enc.is_gpu ? ' (Tối ưu)' : '');
                        encoderSelect.appendChild(opt);
                    });
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
class LiveDubbingEngine {
    constructor() {
        this.cache = new Map(); // key -> audioUrl
        this.currentAudio = null;
        this.currentSubKey = null;
        this.baseVideoVolume = 1.0;
        this.isDucked = false;
        this.pendingFetch = new Set();
    }

    stop() {
        if (this.currentAudio) {
            try {
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0;
            } catch(e) {}
            this.currentAudio = null;
        }
        this.currentSubKey = null;
    }

    restoreVolume(videoEl) {
        if (this.isDucked && videoEl) {
            videoEl.volume = this.baseVideoVolume;
            this.isDucked = false;
        }
    }

    async preloadSentence(text, voiceId, speed) {
        if (!text || !text.trim()) return null;
        const key = `${voiceId}_${speed}_${text.trim()}`;
        if (this.cache.has(key)) return this.cache.get(key);
        if (this.pendingFetch.has(key)) return null;

        this.pendingFetch.add(key);
        try {
            const res = await fetch('/api/tts/sentence_preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text.trim(), voice_id: voiceId, speed })
            });
            const data = await res.json();
            if (data.success && data.audio_url) {
                this.cache.set(key, data.audio_url);
                return data.audio_url;
            }
        } catch (e) {
            console.warn("Live TTS preload error:", e);
        } finally {
            this.pendingFetch.delete(key);
        }
        return null;
    }

    async syncWithPlayer(videoEl, subtitles, options = {}) {
        if (!videoEl || videoEl.paused || !subtitles || subtitles.length === 0) {
            if (videoEl && videoEl.paused) this.stop();
            return;
        }

        const currentTime = videoEl.currentTime || 0;
        const voiceId = options.voiceId || 'local_ngoc_huyen';
        const speed = options.speed || 1.0;
        const voiceVol = (options.voiceVol !== undefined ? options.voiceVol : 100) / 100.0;
        const origVol = (options.origVol !== undefined ? options.origVol : 30) / 100.0;
        const enableDucking = options.ducking !== false;

        // Find current subtitle
        const activeSub = subtitles.find(s => currentTime >= (s.startSeconds || 0) && currentTime <= (s.endSeconds || 0));
        
        // Preload next 2 upcoming subtitles
        const upcoming = subtitles.filter(s => (s.startSeconds || 0) > currentTime && (s.startSeconds || 0) <= currentTime + 8.0).slice(0, 2);
        upcoming.forEach(s => {
            const nextText = (s.translation || s.text || '').trim();
            if (nextText) this.preloadSentence(nextText, voiceId, speed);
        });

        if (!activeSub) {
            if (this.currentAudio && this.currentAudio.ended) {
                this.currentAudio = null;
                this.restoreVolume(videoEl);
            }
            return;
        }

        const text = (activeSub.translation || activeSub.text || '').trim();
        if (!text) return;

        const subKey = `${activeSub.id || activeSub.startSeconds}_${text}`;
        if (this.currentSubKey === subKey) {
            return; // Already playing or finished for this subtitle
        }

        this.currentSubKey = subKey;
        this.stop();

        const audioUrl = await this.preloadSentence(text, voiceId, speed);
        if (audioUrl && !videoEl.paused) {
            this.currentAudio = new Audio(audioUrl);
            this.currentAudio.volume = Math.min(1.0, Math.max(0.0, voiceVol));

            if (enableDucking) {
                this.baseVideoVolume = videoEl.volume;
                videoEl.volume = Math.max(0.0, Math.min(1.0, origVol));
                this.isDucked = true;
            }

            this.currentAudio.play().catch(e => console.log("Live Dubbing play err:", e));

            this.currentAudio.onended = () => {
                this.restoreVolume(videoEl);
                this.currentAudio = null;
            };
        }
    }
}

window.liveDubbingEngine = new LiveDubbingEngine();

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

    globalVideoPlayer.addEventListener('timeupdate', () => {
        const isEditedMode = btnPreviewEdited && btnPreviewEdited.classList.contains('active');
        const overlay = document.getElementById('videoOverlay');
        const isDrawingMode = overlay && overlay.style.display === 'block' && typeof drawMode !== 'undefined' && drawMode === 'sub';
        
        if (!isEditedMode && !isDrawingMode) {
            if (subPreviewBox) subPreviewBox.style.display = 'none';
            window.liveDubbingEngine.stop();
            window.liveDubbingEngine.restoreVolume(globalVideoPlayer);
            return;
        }
        
        if (!srtData || srtData.length === 0) {
            if (isDrawingMode && subPreviewBox) {
                subPreviewBox.innerHTML = '<span class="sub-text-inner">Phụ đề mẫu</span>';
                subPreviewBox.style.display = 'flex';
                applySubStylesToElement(subPreviewBox);
            } else if (subPreviewBox) {
                subPreviewBox.style.display = 'none';
            }
            return;
        }
        
        const currentTime = globalVideoPlayer.currentTime;
        const activeSub = srtData.find(s => currentTime >= s.startSeconds && currentTime <= s.endSeconds);
        
        if (!subPreviewBox) {
            subPreviewBox = document.createElement('div');
            subPreviewBox.className = 'sub-preview-box';
            const vContainer = document.querySelector('.video-container');
            if (vContainer) vContainer.appendChild(subPreviewBox);
            
            if (!currentSubRegion) {
                currentSubRegion = {x: 10, y: 80, w: 80, h: 15, customPos: false};
            }
            
            applySubStylesToElement(subPreviewBox);
            setupDraggableBox(subPreviewBox, (curLeft, curTop, newPx, newPy) => {
                currentSubRegion.x = newPx;
                currentSubRegion.y = newPy;
                currentSubRegion.customPos = true;
            });
        }
        
        if (activeSub) {
            const displayText = activeSub.translation || activeSub.text;
            subPreviewBox.innerHTML = '<span class="sub-text-inner">' + displayText.replace(/\n/g, '<br>') + '</span>';
            subPreviewBox.style.display = 'flex';
            applySubStylesToElement(subPreviewBox);
        } else {
            if (isDrawingMode) {
                subPreviewBox.innerHTML = '<span class="sub-text-inner">Phụ đề mẫu</span>';
                subPreviewBox.style.display = 'flex';
                applySubStylesToElement(subPreviewBox);
            } else {
                subPreviewBox.innerHTML = '';
                subPreviewBox.style.display = 'none';
            }
        }

        // Live Audio Dubbing Sync
        if (isEditedMode && srtData && srtData.length > 0) {
            const dVoice = document.getElementById('dubbingVoiceInput')?.value || 'local_ngoc_huyen';
            const dSpeed = parseFloat(document.getElementById('dubbingSpeed')?.value || 1.0);
            const dVoiceVol = parseFloat(document.getElementById('dubbingVoiceVol')?.value || 100);
            const dOrigVol = parseFloat(document.getElementById('dubbingOrigVol')?.value || 30);
            const dDucking = document.getElementById('dubbingDucking')?.checked !== false;

            window.liveDubbingEngine.syncWithPlayer(globalVideoPlayer, srtData, {
                voiceId: dVoice,
                speed: dSpeed,
                voiceVol: dVoiceVol,
                origVol: dOrigVol,
                ducking: dDucking
            });
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
const downloadProgressBar = document.getElementById('downloadProgressBar');
const downloadCompletedActions = document.getElementById('downloadCompletedActions');
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

// Helper: Format seconds to MM:SS or HH:MM:SS


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


// 3. Select Output Directory
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
            localStorage.setItem('download_output_dir', path);
            showToast('Đã chọn thư mục lưu: ' + path, 'info');
        }
    });
}

const btnClearDownloadDir = document.getElementById('btnClearDownloadDir');
if (btnClearDownloadDir && downloadOutputDir) {
    btnClearDownloadDir.addEventListener('click', () => {
        downloadOutputDir.value = '';
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
                        card.innerHTML = `
                            <div style="position: relative; width: 100%; height: 75px; border-radius: 6px; overflow: hidden; background: #020617;">
                                <img src="${v.thumbnail || ''}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'">
                                <span style="position: absolute; bottom: 3px; right: 3px; background: rgba(0,0,0,0.85); color: #fff; font-size: 9.5px; font-weight: 600; padding: 1px 4px; border-radius: 3px;">
                                    ${formatDurationStr(v.duration)}
                                </span>
                                <span style="position: absolute; top: 3px; left: 3px; background: #0284c7; color: #fff; font-size: 9px; font-weight: 700; padding: 1px 4px; border-radius: 3px;">
                                    #${idx + 1}
                                </span>
                            </div>
                            <div style="font-size: 11.5px; font-weight: 600; color: #f8fafc; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${v.title || ''}">
                                ${v.title || `Video ${idx + 1}`}
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
        const url = downloadInputUrl?.value.trim();
        if (!url) {
            showToast('Vui lòng dán liên kết video!', 'warning');
            return;
        }

        btnStartDownload.disabled = true;
        btnStartDownload.innerHTML = `<span>⏳ Đang tải xuống...</span>`;
        if (downloadProgressBox) downloadProgressBox.style.display = 'block';
        if (downloadCompletedActions) downloadCompletedActions.style.display = 'none';
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
                                if (downloadProgressStatusText) downloadProgressStatusText.textContent = '✅ Đã tải xong!';
                                if (downloadProgressSpeedEta) downloadProgressSpeedEta.textContent = data.file_size || '';
                                if (downloadCompletedActions) downloadCompletedActions.style.display = 'block';

                                // Save to download history
                                saveDownloadHistoryItem({
                                    id: Date.now(),
                                    title: data.title || data.file_name,
                                    file_path: data.file_path,
                                    file_name: data.file_name,
                                    file_size: data.file_size,
                                    thumbnail: data.thumbnail || (currentDownloadInfo ? currentDownloadInfo.thumbnail : ''),
                                    platform: currentDownloadInfo ? currentDownloadInfo.extractor : 'Video',
                                    is_audio: currentDownloadFormat === 'mp3',
                                    timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
                                });

                                showToast('Tải video thành công!', 'success');
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
    fetch('/api/download/open_folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath })
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

        const thumbSrc = item.thumbnail || '';
        const thumbHtml = thumbSrc 
            ? `<img src="${thumbSrc}" class="download-history-thumb" alt="thumb">`
            : `<div class="download-history-thumb" style="display:flex;align-items:center;justify-content:center;color:#64748b;"><svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" fill="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg></div>`;

        row.innerHTML = `
            ${thumbHtml}
            <div class="download-history-info">
                <div class="download-history-title" title="${item.title}">${item.title}</div>
                <div class="download-history-meta">
                    <span class="platform-pill" style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: #1e293b; color: #38bdf8; border: 1px solid #334155;">${item.platform || 'Video'}</span>
                    <span>📦 ${item.file_size || '--'}</span>
                    <span>🕒 ${item.timestamp || ''}</span>
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
window.addEventListener('DOMContentLoaded', renderDownloadHistory);

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
    const douyinChannelVideoCountBadge = document.getElementById('douyinChannelVideoCountBadge');

    const douyinBatchActionsBar = document.getElementById('douyinBatchActionsBar');
    const douyinSelectAllCheckbox = document.getElementById('douyinSelectAllCheckbox');
    const douyinSelectedSummary = document.getElementById('douyinSelectedSummary');
    const btnStartDouyinBatchDownload = document.getElementById('btnStartDouyinBatchDownload');
    const btnDouyinOpenFolder = document.getElementById('btnDouyinOpenFolder');

    const douyinBatchProgressBox = document.getElementById('douyinBatchProgressBox');
    const douyinBatchProgressText = document.getElementById('douyinBatchProgressText');
    const douyinBatchProgressPct = document.getElementById('douyinBatchProgressPct');
    const douyinBatchProgressBar = document.getElementById('douyinBatchProgressBar');

    const douyinChannelGridContainer = document.getElementById('douyinChannelGridContainer');
    const douyinChannelGrid = document.getElementById('douyinChannelGrid');
    const douyinChannelEmptyPlaceholder = document.getElementById('douyinChannelEmptyPlaceholder');

    // 1. Sub-tab toggle
    if (tabDownloadSingle && tabDownloadChannel && sectionDownloadSingle && sectionDownloadChannel) {
        tabDownloadSingle.addEventListener('click', () => {
            tabDownloadSingle.classList.add('active');
            tabDownloadSingle.style.borderColor = '#38bdf8';
            tabDownloadSingle.style.color = '#38bdf8';
            tabDownloadSingle.style.background = 'rgba(56, 189, 248, 0.1)';

            tabDownloadChannel.classList.remove('active');
            tabDownloadChannel.style.borderColor = '#334155';
            tabDownloadChannel.style.color = '#94a3b8';
            tabDownloadChannel.style.background = 'transparent';

            sectionDownloadSingle.style.display = 'block';
            sectionDownloadChannel.style.display = 'none';
        });

        tabDownloadChannel.addEventListener('click', () => {
            tabDownloadChannel.classList.add('active');
            tabDownloadChannel.style.borderColor = '#a855f7';
            tabDownloadChannel.style.color = '#c084fc';
            tabDownloadChannel.style.background = 'rgba(168, 85, 247, 0.1)';

            tabDownloadSingle.classList.remove('active');
            tabDownloadSingle.style.borderColor = '#334155';
            tabDownloadSingle.style.color = '#94a3b8';
            tabDownloadSingle.style.background = 'transparent';

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
            btnScanDouyinChannel.innerHTML = `<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Đang quét kênh...`;

            if (douyinChannelEmptyPlaceholder) {
                douyinChannelEmptyPlaceholder.style.display = 'block';
                douyinChannelEmptyPlaceholder.innerHTML = `
                    <div style="width: 56px; height: 56px; border-radius: 12px; background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); display: inline-flex; align-items: center; justify-content: center; margin-bottom: 14px;">
                        <span class="loading-spinner" style="width:28px;height:28px;"></span>
                    </div>
                    <div style="font-size: 15px; font-weight: 600; color: #f8fafc;">Đang khởi động trình duyệt ngầm & cào dữ liệu...</div>
                    <div style="font-size: 12.5px; color: #38bdf8; margin-top: 6px;">Vui lòng đợi trong giây lát khi hệ thống tự động cuộn trang phân trang.</div>
                `;
            }

            try {
                const res = await fetch('/api/download/douyin/scan_channel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ channel_url: channelUrl, limit })
                });

                if (res.status === 404) {
                    showToast('Backend chưa nạp API quét kênh mới. Vui lòng tắt và khởi động lại ứng dụng!', 'warning');
                    if (douyinChannelEmptyPlaceholder) {
                        douyinChannelEmptyPlaceholder.innerHTML = `
                            <div style="font-size: 15px; font-weight: 600; color: #f87171;">⚠️ Chưa khởi động lại Backend</div>
                            <div style="font-size: 12.5px; color: #94a3b8; margin-top: 6px;">Vui lòng tắt ứng dụng và chạy lại file <code>run_app.bat</code> để nạp API quét kênh mới.</div>
                        `;
                    }
                    return;
                }

                let data;
                try {
                    data = await res.json();
                } catch (jsonErr) {
                    showToast('Lỗi phản hồi từ máy chủ (Mã: ' + res.status + '). Vui lòng tắt và khởi động lại ứng dụng!', 'error');
                    if (douyinChannelEmptyPlaceholder) {
                        douyinChannelEmptyPlaceholder.innerHTML = `
                            <div style="font-size: 15px; font-weight: 600; color: #f87171;">❌ Phản hồi không hợp lệ (Mã: ${res.status})</div>
                            <div style="font-size: 12.5px; color: #94a3b8; margin-top: 6px;">Vui lòng khởi động lại ứng dụng để cập nhật endpoint.</div>
                        `;
                    }
                    return;
                }

                if (!res.ok || data.error) {
                    showToast(data.error || 'Lỗi khi quét kênh Douyin!', 'error');
                    if (douyinChannelEmptyPlaceholder) {
                        douyinChannelEmptyPlaceholder.innerHTML = `
                            <div style="font-size: 15px; font-weight: 600; color: #f87171;">❌ Quét kênh thất bại</div>
                            <div style="font-size: 12.5px; color: #94a3b8; margin-top: 6px;">${data.error || 'Không thể kết nối kênh Douyin.'}</div>
                        `;
                    }
                    return;
                }

                scannedDouyinVideos = data.videos || [];
                selectedDouyinVideoIds = new Set(scannedDouyinVideos.map(v => v.aweme_id));

                // Render Channel Info Banner
                const info = data.channel_info || {};
                if (douyinChannelInfoBanner) douyinChannelInfoBanner.style.display = 'block';
                if (douyinChannelAvatar) douyinChannelAvatar.src = info.avatar || '';
                if (douyinChannelNickname) douyinChannelNickname.textContent = info.nickname || 'Kênh Douyin';
                if (douyinChannelSignature) douyinChannelSignature.textContent = info.signature || 'Không có mô tả';
                if (douyinChannelVideoCountBadge) douyinChannelVideoCountBadge.textContent = `${scannedDouyinVideos.length} Video`;

                // Render Video Grid
                renderDouyinVideoGrid();

                showToast(`Đã quét thành công ${scannedDouyinVideos.length} video từ kênh!`, 'success');
            } catch (e) {
                showToast('Lỗi kết nối khi quét kênh: ' + e.message, 'error');
            } finally {
                btnScanDouyinChannel.disabled = false;
                btnScanDouyinChannel.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg><span>Quét Danh Sách Video</span>`;
            }
        });
    }

    // 4. Render Video Grid Function
    function renderDouyinVideoGrid() {
        if (!douyinChannelGrid) return;
        douyinChannelGrid.innerHTML = '';

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

        scannedDouyinVideos.forEach((video, idx) => {
            const isSelected = selectedDouyinVideoIds.has(video.aweme_id);
            const card = document.createElement('div');
            card.className = 'card douyin-video-card';
            card.style.cssText = `
                background: #1e293b;
                border: 1px solid ${isSelected ? '#38bdf8' : '#334155'};
                border-radius: 10px;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                transition: all 0.2s;
                position: relative;
            `;

            const thumb = video.cover_url || '';
            card.innerHTML = `
                <div style="position: relative; width: 100%; aspect-ratio: 16/9; background: #0f172a; overflow: hidden;">
                    <img src="${thumb}" alt="thumb" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none';">
                    <span style="position: absolute; bottom: 6px; right: 6px; background: rgba(0,0,0,0.8); color: #fff; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px;">
                        ${video.duration_formatted || '00:00'}
                    </span>
                    <label style="position: absolute; top: 6px; left: 6px; background: rgba(15,23,42,0.85); padding: 4px 8px; border-radius: 6px; display: flex; align-items: center; gap: 5px; cursor: pointer;">
                        <input type="checkbox" class="douyin-item-checkbox" data-id="${video.aweme_id}" ${isSelected ? 'checked' : ''} style="width: 16px; height: 16px; accent-color: #38bdf8; cursor: pointer;">
                        <span style="font-size: 11px; font-weight: 700; color: #38bdf8;">#${idx + 1}</span>
                    </label>
                </div>
                <div style="padding: 12px; flex: 1; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="font-size: 12.5px; font-weight: 600; color: #f8fafc; line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${video.title}">
                        ${video.title || 'Video Douyin'}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #334155; padding-top: 8px;">
                        <span>❤️ ${(video.digg_count || 0).toLocaleString()}</span>
                        <span>💬 ${(video.comment_count || 0).toLocaleString()}</span>
                        <a href="${video.url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 600;">Xem ↗</a>
                    </div>
                </div>
            `;

            // Checkbox change handler
            const chk = card.querySelector('.douyin-item-checkbox');
            chk?.addEventListener('change', (e) => {
                const checked = e.target.checked;
                if (checked) {
                    selectedDouyinVideoIds.add(video.aweme_id);
                    card.style.borderColor = '#38bdf8';
                } else {
                    selectedDouyinVideoIds.delete(video.aweme_id);
                    card.style.borderColor = '#334155';
                }
                updateSelectionSummary();
            });

            douyinChannelGrid.appendChild(card);
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

    // 5. Select All Checkbox
    if (douyinSelectAllCheckbox) {
        douyinSelectAllCheckbox.addEventListener('change', (e) => {
            const checked = e.target.checked;
            if (checked) {
                selectedDouyinVideoIds = new Set(scannedDouyinVideos.map(v => v.aweme_id));
            } else {
                selectedDouyinVideoIds.clear();
            }
            renderDouyinVideoGrid();
        });
    }

    // 6. Open Folder
    if (btnDouyinOpenFolder) {
        btnDouyinOpenFolder.addEventListener('click', () => {
            fetch('/api/download/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
        });
    }

    // 7. Start Batch Download
    if (btnStartDouyinBatchDownload) {
        btnStartDouyinBatchDownload.addEventListener('click', async () => {
            const selectedList = scannedDouyinVideos.filter(v => selectedDouyinVideoIds.has(v.aweme_id));
            if (selectedList.length === 0) {
                showToast('Vui lòng tích chọn ít nhất 1 video để tải!', 'warning');
                return;
            }

            btnStartDouyinBatchDownload.disabled = true;
            btnStartDouyinBatchDownload.innerHTML = `<span>⏳ Đang tải hàng loạt...</span>`;
            if (douyinBatchProgressBox) douyinBatchProgressBox.style.display = 'block';
            if (douyinBatchProgressBar) douyinBatchProgressBar.style.width = '0%';
            if (douyinBatchProgressText) douyinBatchProgressText.textContent = `Bắt đầu tải ${selectedList.length} video...`;
            if (douyinBatchProgressPct) douyinBatchProgressPct.textContent = '0%';

            try {
                const response = await fetch('/api/download/douyin/batch_download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        videos: selectedList,
                        output_dir: ''
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
                btnStartDouyinBatchDownload.disabled = false;
                btnStartDouyinBatchDownload.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg><span>TẢI CÁC VIDEO ĐÃ CHỌN</span>`;
            }
        });
    }
}

window.addEventListener('DOMContentLoaded', initDouyinChannelDownloader);

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
if (reviewTabDynamicBlurHeader && reviewTabDynamicBlurSubConfig) {
    reviewTabDynamicBlurHeader.addEventListener('click', () => {
        const isHidden = reviewTabDynamicBlurSubConfig.style.display === 'none' || !reviewTabDynamicBlurSubConfig.style.display;
        reviewTabDynamicBlurSubConfig.style.display = isHidden ? 'flex' : 'none';
        if (reviewTabDynamicBlurChevron) {
            reviewTabDynamicBlurChevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
        }
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

    if (!logoOverlay || !container) return;

    function renderLogo() {
        if (!currentLogoState.enabled || !currentLogoState.path) {
            logoOverlay.style.display = 'none';
            return;
        }

        const cW = container.clientWidth || 640;
        const cH = container.clientHeight || 360;

        const leftPx = (currentLogoState.x_pct / 100) * cW;
        const topPx = (currentLogoState.y_pct / 100) * cH;
        const widthPx = (currentLogoState.w_pct / 100) * cW;
        const heightPx = (currentLogoState.h_pct / 100) * cH;

        logoOverlay.style.display = 'block';
        logoOverlay.style.left = `${leftPx}px`;
        logoOverlay.style.top = `${topPx}px`;
        logoOverlay.style.width = `${widthPx}px`;
        logoOverlay.style.height = `${heightPx}px`;
        logoOverlay.style.opacity = `${currentLogoState.opacity / 100}`;

        if (logoImg) {
            if (currentLogoState.dataUrl) {
                if (logoImg.src !== currentLogoState.dataUrl) logoImg.src = currentLogoState.dataUrl;
            } else if (currentLogoState.path) {
                const imgSrc = `/api/image?path=${encodeURIComponent(currentLogoState.path)}`;
                if (!logoImg.src.includes(encodeURIComponent(currentLogoState.path))) {
                    logoImg.src = imgSrc;
                }
            }
        }

        if (coordBadge) {
            coordBadge.textContent = `(x: ${currentLogoState.x_pct.toFixed(1)}%, y: ${currentLogoState.y_pct.toFixed(1)}%, w: ${currentLogoState.w_pct.toFixed(1)}%)`;
        }
    }

    // Checkbox toggle
    if (enableCheckbox) {
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

// Khởi tạo Logo Watermark Controller
setupInteractiveVideoLogo();

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

        if (isReviewPreviewEditedMode) {
            const rVoice = document.getElementById('reviewVoiceInput')?.value || 'local_ngoc_huyen';
            const rSpeed = parseFloat(document.getElementById('reviewVoiceSpeed')?.value || 1.0);
            const rOrigVol = parseFloat(document.getElementById('reviewOrigVol')?.value || 30);
            const subsList = window.reviewParsedSubtitles || (window.reviewTabScannedAiBoxes ? window.reviewTabScannedAiBoxes.map(b => ({
                startSeconds: b.visual_start !== undefined ? b.visual_start : b.startSeconds,
                endSeconds: b.visual_end !== undefined ? b.visual_end : b.endSeconds,
                text: b.text || ''
            })) : []);

            if (subsList.length > 0) {
                window.liveDubbingEngine.syncWithPlayer(reviewVideoPlayer, subsList, {
                    voiceId: rVoice,
                    speed: rSpeed,
                    voiceVol: 100,
                    origVol: rOrigVol,
                    ducking: true
                });
            }
        }
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

        const blurLead = (parseFloat(document.getElementById('reviewTabBlurLeadOffset')?.value) || -180) / 1000;
        const blurPad = (parseFloat(document.getElementById('reviewTabBlurPadding')?.value) || 220) / 1000;
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

        const leftPct = activeBox ? (activeBox.x_pct !== undefined ? activeBox.x_pct : 20) : 20;
        const topPct = activeBox ? (activeBox.y_pct !== undefined ? activeBox.y_pct : blurY) : blurY;
        const widthPct = activeBox ? (activeBox.w_pct !== undefined ? activeBox.w_pct : 60) : 60;
        const heightPct = activeBox ? (activeBox.h_pct !== undefined ? activeBox.h_pct : 9.5) : 9.5;

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

async function fetchLicenseInfo(sync = false) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);

        const res = await fetch(`/api/license/info?sync=${sync}`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        currentLicenseState = data;
        updateLicenseUI(data);

        if (data.is_first_launch && data.tier === 'trial') {
            showToast('🎉 Chào mừng! Gói Dùng Thử 24h miễn phí đã được tự động kích hoạt để bạn bắt đầu trải nghiệm ngay.', 'success');
        }

        // Tự động kiểm tra hiển thị cam kết bản quyền lần đầu / khi có gói mới
        checkAndShowCopyrightDisclaimer(false, data);

        return data;
    } catch (err) {
        console.warn('Lỗi tải thông tin bản quyền (kích hoạt chế độ bảo vệ offline):', err);
        currentLicenseState = {
            is_valid: false,
            status: 'UNLICENSED',
            tier: 'unlicensed',
            plan_name: 'Chưa kích hoạt (Offline)',
            badge_class: 'badge-unlicensed',
            badge_text: '🔒 Chưa Kích Hoạt',
            can_activate_trial: true,
            features: {}
        };
        updateLicenseUI(currentLicenseState);
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
    if (modalHwidDisplay) modalHwidDisplay.textContent = info.hwid || 'AMS-XXXX-XXXX-XXXX';
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

        if (tabEditor) {
            if (proMod === 'editor') {
                tabEditor.innerHTML = 'Biên tập phim <span style="font-size: 10px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 2px 6px; border-radius: 8px; margin-left: 4px; font-weight: 700;">Đang dùng</span>';
                tabEditor.style.opacity = '1';
                tabEditor.title = 'Module Biên tập phim (Đang chọn)';
            } else if (proMod === 'review') {
                tabEditor.innerHTML = 'Biên tập phim <span style="font-size: 11px; margin-left: 4px;">🔒</span>';
                tabEditor.style.opacity = '0.55';
                tabEditor.title = 'Bị khóa - Gói Pro đã chọn Review Phim (Nâng cấp VIP để mở khóa cả 2)';
            } else {
                tabEditor.innerHTML = 'Biên tập phim <span style="font-size: 11px; margin-left: 4px;">🔒</span>';
                tabEditor.style.opacity = '0.55';
                tabEditor.title = 'Chưa chọn module cho Gói Pro';
            }
        }
        if (tabReview) {
            if (proMod === 'review') {
                tabReview.innerHTML = 'Review Phim <span style="font-size: 10px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 2px 6px; border-radius: 8px; margin-left: 4px; font-weight: 700;">Đang dùng</span>';
                tabReview.style.opacity = '1';
                tabReview.title = 'Module Review Phim (Đang chọn)';
            } else if (proMod === 'editor') {
                tabReview.innerHTML = 'Review Phim <span style="font-size: 11px; margin-left: 4px;">🔒</span>';
                tabReview.style.opacity = '0.55';
                tabReview.title = 'Bị khóa - Gói Pro đã chọn Biên tập phim (Nâng cấp VIP để mở khóa cả 2)';
            } else {
                tabReview.innerHTML = 'Review Phim <span style="font-size: 11px; margin-left: 4px;">🔒</span>';
                tabReview.style.opacity = '0.55';
                tabReview.title = 'Chưa chọn module cho Gói Pro';
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
        if (tabEditor) {
            tabEditor.textContent = 'Biên tập phim';
            tabEditor.style.opacity = '1';
            tabEditor.title = '';
        }
        if (tabReview) {
            tabReview.textContent = 'Review Phim';
            tabReview.style.opacity = '1';
            tabReview.title = '';
        }
    }

    // 6. Tự động nạp và bảo vệ API Keys cho Gói VIP / Gói Năm (Chống copy / xem trộm key)
    const isVipTier = info && info.status === 'ACTIVE' && (info.tier === 'vip' || info.tier === 'yearly');
    const inputIds = ['openaiKey', 'openSpeakerApiKey', 'geminiApiKey'];
    
    if (isVipTier) {
        inputIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
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
        });
        appendLog('⭐ [Bản quyền VIP] Đã kích hoạt chế độ bảo vệ an toàn API Bản Quyền!', 'info');
    } else {
        inputIds.forEach(id => {
            const el = document.getElementById(id);
            if (el && el.value && el.value.startsWith('•')) {
                el.value = '';
                el.readOnly = false;
                el.type = 'password';
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
    }
}

// Khởi chạy kiểm tra bản quyền tức thì khi load module
fetchLicenseInfo();

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
        modalOpenedLicenseExpiry = currentLicenseState ? (currentLicenseState.expire_timestamp || currentLicenseState.expire_date || '') : '';
        modalOpenedLicensePlan = currentLicenseState ? (currentLicenseState.plan_type || '') : '';
        modalOpenedLicenseStatus = currentLicenseState ? currentLicenseState.status : 'UNLICENSED';

        licenseModal.style.display = 'flex';
        loadVietQR(defaultTier);
        startSepayPolling();

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
    sepayPollingInterval = setInterval(async () => {
        try {
            // 1. Kiểm tra trực tiếp qua SePay API (Chỉ trả về success=True khi phát hiện giao dịch khớp mới)
            const sepayRes = await fetch('/api/license/check_sepay_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: currentSelectedTier || 'vip' })
            });
            const sepayData = await sepayRes.json();
            if (sepayData.success && sepayData.license && sepayData.license.status === 'ACTIVE') {
                currentLicenseState = sepayData.license;
                updateLicenseUI(sepayData.license);
                stopSepayPolling();
                if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
                if (licenseModal) licenseModal.style.display = 'none';
                showLicenseSuccessCelebration(sepayData.license);
                showToast(`🎉 ${sepayData.message || 'Thanh toán thành công!'}`, 'success');
                return;
            }

            // 2. Kiểm tra đồng bộ qua Google Sheet (Chỉ chúc mừng và đóng modal khi có gia hạn mới hoặc nâng cấp gói mới)
            const res = await fetch('/api/license/sync_cloud', { method: 'POST' });
            const data = await res.json();
            if (data.success && data.license && data.license.status === 'ACTIVE') {
                const newExpiry = data.license.expire_timestamp || data.license.expire_date || '';
                const newPlan = data.license.plan_type || '';
                const isNewlyActivated = (modalOpenedLicenseStatus !== 'ACTIVE');
                const isPlanUpgraded = (modalOpenedLicensePlan && newPlan !== modalOpenedLicensePlan);
                const isExpiryExtended = (modalOpenedLicenseExpiry && newExpiry > modalOpenedLicenseExpiry);

                if (isNewlyActivated || isPlanUpgraded || isExpiryExtended) {
                    currentLicenseState = data.license;
                    updateLicenseUI(data.license);
                    stopSepayPolling();
                    if (btnCloseLicenseModal) btnCloseLicenseModal.style.display = 'block';
                    if (licenseModal) licenseModal.style.display = 'none';
                    showLicenseSuccessCelebration(data.license);
                    showToast(`🎉 Thanh toán thành công! Gói ${data.license.plan_name} đã được kích hoạt!`, 'success');
                }
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
            if (sepayData.success && sepayData.license) {
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
            if (data.success && data.license && data.license.status === 'ACTIVE') {
                const newExpiry = data.license.expire_timestamp || data.license.expire_date || '';
                const newPlan = data.license.plan_type || '';
                const isNewlyActivated = (modalOpenedLicenseStatus !== 'ACTIVE');
                const isPlanUpgraded = (modalOpenedLicensePlan && newPlan !== modalOpenedLicensePlan);
                const isExpiryExtended = (modalOpenedLicenseExpiry && newExpiry > modalOpenedLicenseExpiry);

                if (isNewlyActivated || isPlanUpgraded || isExpiryExtended) {
                    currentLicenseState = data.license;
                    updateLicenseUI(data.license);
                    if (licenseModal) licenseModal.style.display = 'none';
                    showLicenseSuccessCelebration(data.license);
                    showToast(`🎉 Chúc mừng! Đã nhận được thanh toán thành công! Gói ${data.license.plan_name} đã được kích hoạt!`, 'success');
                    return;
                }
            }
            
            showToast('⚠️ Chưa nhận được tiền: Hệ thống đã quét SePay nhưng chưa tìm thấy giao dịch chuyển khoản mới khớp với mã máy. Nếu bạn vừa chuyển khoản, vui lòng đợi 5-10 giây để ngân hàng xử lý rồi bấm lại nhé!', 'warning');
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
            if (data.license) updateLicenseUI(data.license);
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
        // Kiểm tra và hiển thị cam kết bản quyền sau khi đóng celebration
        checkAndShowCopyrightDisclaimer(true, currentLicenseState);
    });
}

if (btnStartUsingLicense) {
    btnStartUsingLicense.addEventListener('click', () => {
        if (licenseSuccessModal) licenseSuccessModal.classList.remove('active');
        celebrationFX.stop();
        // Bắt buộc hiển thị cam kết bản quyền sau khi mua/kích hoạt gói thành công
        checkAndShowCopyrightDisclaimer(true, currentLicenseState);
    });
}

if (licenseSuccessModal) {
    licenseSuccessModal.addEventListener('click', (e) => {
        if (e.target === licenseSuccessModal) {
            licenseSuccessModal.classList.remove('active');
            celebrationFX.stop();
            checkAndShowCopyrightDisclaimer(true, currentLicenseState);
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

function getLicenseSignature(licenseData) {
    if (!licenseData) return 'unlicensed';
    return `${licenseData.tier || 'unlicensed'}_${licenseData.expire_epoch || licenseData.created_at || 'sig'}`;
}

export function checkAndShowCopyrightDisclaimer(forceForNewLicense = false, licenseData = null) {
    if (!modalCopyrightDisclaimer) return;

    const lic = licenseData || currentLicenseState;
    const currentSig = getLicenseSignature(lic);
    const hasAgreedGeneral = localStorage.getItem('ams_copyright_disclaimer_accepted') === 'true';
    const lastAgreedSig = localStorage.getItem('ams_disclaimer_license_sig');

    // Điều kiện hiển thị:
    // 1. Lần đầu tiên khi cài app (chưa từng đồng ý cam kết)
    // 2. Lần đầu tiên sau khi kích hoạt/mua gói mới (currentSig khác lastAgreedSig và đang có gói ACTIVE)
    // 3. Được ép gọi trực tiếp (forceForNewLicense === true)
    const isNewPurchasedLicense = lic && lic.is_valid && lic.status === 'ACTIVE' && lic.tier !== 'unlicensed' && lastAgreedSig !== currentSig;

    if (!hasAgreedGeneral || isNewPurchasedLicense || forceForNewLicense) {
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

        const currentSig = getLicenseSignature(currentLicenseState);
        localStorage.setItem('ams_copyright_disclaimer_accepted', 'true');
        localStorage.setItem('ams_disclaimer_accepted_at', new Date().toISOString());
        localStorage.setItem('ams_disclaimer_license_sig', currentSig);

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
            logo_overlay: window.currentReviewLogoState ? { ...window.currentReviewLogoState } : null
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
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.toLowerCase().trim();
                if (!window._cachedRecentProjects) return;
                const filtered = window._cachedRecentProjects.filter(p => 
                    p.project_name.toLowerCase().includes(query) || 
                    (p.video_name && p.video_name.toLowerCase().includes(query))
                );
                this.renderRecentProjectsList(filtered);
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
                    btnHeaderCheck.innerHTML = `<span style="font-size: 13px;">🚀</span><span style="font-weight: 700; color: #38bdf8;">Cập nhật (v${data.latest_version})</span>`;
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
                btnStart.innerHTML = `<span>🚀</span><span>Cập Nhật Ngay (v${latestVer})</span>`;
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

                if (statusText) statusText.textContent = p.message || 'Đang cập nhật...';
                if (percentText) percentText.textContent = `${p.percent || 0}%`;
                if (barFill) barFill.style.width = `${p.percent || 0}%`;

                if (p.total_bytes > 0 && subText) {
                    const mbDown = (p.downloaded_bytes / (1024 * 1024)).toFixed(1);
                    const mbTotal = (p.total_bytes / (1024 * 1024)).toFixed(1);
                    subText.textContent = `${mbDown} MB / ${mbTotal} MB`;
                }

                if (p.status === 'completed') {
                    clearInterval(this.pollingInterval);
                    showToast(p.message || 'Cập nhật thành công! Đang khởi động lại...', 'success');
                } else if (p.status === 'error') {
                    clearInterval(this.pollingInterval);
                    showToast('Lỗi cập nhật: ' + (p.error || 'Không xác định'), 'error');
                    const btnStart = document.getElementById('btnStartAppUpdate');
                    if (btnStart) {
                        btnStart.disabled = false;
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



