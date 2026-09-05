/**
 * Clone Voice Studio Feature Module
 * Integrates Local Voice cloning (VieNeu ONNX engine) with live recording, drag-and-drop, interactive audio playback, real-time logging, full metadata fields & in-place voice editing.
 */

import { appendLog, showToast, showConfirmModal, escapeHtml } from '../utils.js';

let currentSamplePath = null;
let currentSampleUrl = null;
let mediaRecorder = null;
let recordedAudioChunks = [];
let recordTimerInterval = null;
let recordStartTime = 0;
let clonedVoicesCache = [];

export function initCloneVoiceModule() {
    // Mode Switcher
    const btnCloneModeUpload = document.getElementById('btnCloneModeUpload');
    const btnCloneModeRecord = document.getElementById('btnCloneModeRecord');
    const cloneUploadBox = document.getElementById('cloneUploadBox');
    const cloneRecordBox = document.getElementById('cloneRecordBox');

    if (btnCloneModeUpload && btnCloneModeRecord) {
        btnCloneModeUpload.addEventListener('click', () => {
            btnCloneModeUpload.classList.add('active');
            btnCloneModeUpload.style.borderColor = '#38bdf8';
            btnCloneModeUpload.style.color = '#38bdf8';

            btnCloneModeRecord.classList.remove('active');
            btnCloneModeRecord.style.borderColor = '';
            btnCloneModeRecord.style.color = '';

            if (cloneUploadBox) cloneUploadBox.style.display = 'block';
            if (cloneRecordBox) cloneRecordBox.style.display = 'none';
        });

        btnCloneModeRecord.addEventListener('click', () => {
            btnCloneModeRecord.classList.add('active');
            btnCloneModeRecord.style.borderColor = '#38bdf8';
            btnCloneModeRecord.style.color = '#38bdf8';

            btnCloneModeUpload.classList.remove('active');
            btnCloneModeUpload.style.borderColor = '';
            btnCloneModeUpload.style.color = '';

            if (cloneUploadBox) cloneUploadBox.style.display = 'none';
            if (cloneRecordBox) cloneRecordBox.style.display = 'block';
        });
    }

    // Drag and Drop / File Input
    const cloneDropZone = document.getElementById('cloneDropZone');
    const cloneFileInput = document.getElementById('cloneFileInput');
    const btnBrowseCloneFile = document.getElementById('btnBrowseCloneFile');

    if (cloneFileInput) {
        if (cloneDropZone) {
            cloneDropZone.addEventListener('click', (e) => {
                if (e.target !== cloneFileInput) {
                    cloneFileInput.value = '';
                    cloneFileInput.click();
                }
            });

            cloneDropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                cloneDropZone.style.borderColor = '#38bdf8';
                cloneDropZone.style.background = 'rgba(56, 189, 248, 0.12)';
            });

            cloneDropZone.addEventListener('dragleave', (e) => {
                e.preventDefault();
                e.stopPropagation();
                cloneDropZone.style.borderColor = '#334155';
                cloneDropZone.style.background = 'rgba(30, 41, 59, 0.4)';
            });

            cloneDropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                cloneDropZone.style.borderColor = '#334155';
                cloneDropZone.style.background = 'rgba(30, 41, 59, 0.4)';
                cloneFileInput.value = '';
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    uploadSampleFile(e.dataTransfer.files[0]);
                }
            });
        }

        if (btnBrowseCloneFile) {
            btnBrowseCloneFile.addEventListener('click', (e) => {
                e.stopPropagation();
                cloneFileInput.value = '';
                cloneFileInput.click();
            });
        }

        cloneFileInput.addEventListener('change', () => {
            if (cloneFileInput.files && cloneFileInput.files.length > 0) {
                const file = cloneFileInput.files[0];
                cloneFileInput.value = '';
                uploadSampleFile(file);
            }
        });
    }

    // Live Microphone Recording
    const btnStartCloneRecord = document.getElementById('btnStartCloneRecord');
    const btnStopCloneRecord = document.getElementById('btnStopCloneRecord');
    const cloneRecordTimer = document.getElementById('cloneRecordTimer');
    const cloneRecordPulseCircle = document.getElementById('cloneRecordPulseCircle');
    const cloneRecordHelpText = document.getElementById('cloneRecordHelpText');

    if (btnStartCloneRecord && btnStopCloneRecord) {
        btnStartCloneRecord.addEventListener('click', async () => {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                const errMsg = 'Trình duyệt không hỗ trợ ghi âm trực tiếp hoặc kết nối không bảo mật (yêu cầu http://localhost hoặc https://).';
                appendLog(`🛑 [Clone Voice] ${errMsg}`, 'error');
                showToast(errMsg, 'error');
                return;
            }

            try {
                appendLog('ℹ️ [Clone Voice] Đang yêu cầu quyền truy cập Microphone...', 'info');
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                recordedAudioChunks = [];

                let mimeType = 'audio/webm';
                if (window.MediaRecorder && MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
                    mimeType = 'audio/webm;codecs=opus';
                } else if (window.MediaRecorder && MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
                    mimeType = 'audio/ogg;codecs=opus';
                } else if (window.MediaRecorder && MediaRecorder.isTypeSupported('audio/mp4')) {
                    mimeType = 'audio/mp4';
                }

                mediaRecorder = new MediaRecorder(stream, { mimeType });

                mediaRecorder.ondataavailable = (event) => {
                    if (event.data && event.data.size > 0) {
                        recordedAudioChunks.push(event.data);
                    }
                };

                mediaRecorder.onstop = async () => {
                    stream.getTracks().forEach(track => track.stop());
                    clearInterval(recordTimerInterval);
                    if (cloneRecordTimer) cloneRecordTimer.textContent = '00:00';
                    if (cloneRecordPulseCircle) {
                        cloneRecordPulseCircle.style.borderColor = '#ef4444';
                        cloneRecordPulseCircle.style.background = 'rgba(239, 68, 68, 0.15)';
                    }
                    if (cloneRecordHelpText) {
                        cloneRecordHelpText.textContent = 'Đang đóng gói và gửi mẫu ghi âm lên máy chủ...';
                        cloneRecordHelpText.style.color = '#38bdf8';
                    }

                    const audioBlob = new Blob(recordedAudioChunks, { type: mimeType });
                    const ext = mimeType.includes('mp4') ? 'm4a' : (mimeType.includes('ogg') ? 'ogg' : 'webm');
                    const file = new File([audioBlob], `mic_recording_${Date.now()}.${ext}`, { type: mimeType });
                    
                    appendLog(`ℹ️ [Clone Voice] Đã hoàn thành ghi âm (${(audioBlob.size / 1024).toFixed(1)} KB). Đang tải lên chuẩn hóa...`, 'info');
                    await uploadSampleFile(file);
                };

                mediaRecorder.start(200);
                recordStartTime = Date.now();

                if (cloneRecordPulseCircle) {
                    cloneRecordPulseCircle.style.borderColor = '#38bdf8';
                    cloneRecordPulseCircle.style.background = 'rgba(56, 189, 248, 0.25)';
                }
                if (cloneRecordHelpText) {
                    cloneRecordHelpText.textContent = '🔴 Đang thu âm... Hãy nói 1 câu 3-5 giây rõ ràng!';
                    cloneRecordHelpText.style.color = '#ef4444';
                }

                recordTimerInterval = setInterval(() => {
                    const elapsedSec = Math.floor((Date.now() - recordStartTime) / 1000);
                    const mins = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
                    const secs = String(elapsedSec % 60).padStart(2, '0');
                    if (cloneRecordTimer) cloneRecordTimer.textContent = `${mins}:${secs}`;

                    if (elapsedSec >= 15) {
                        btnStopCloneRecord.click();
                    }
                }, 200);

                btnStartCloneRecord.style.display = 'none';
                btnStopCloneRecord.style.display = 'inline-flex';
                showToast('Đang thu âm mic... Hãy nói 1 câu 3-5 giây!', 'info');
                appendLog('🔴 [Clone Voice] Microphone đang ghi âm...', 'info');
            } catch (err) {
                console.error("Microphone Access Error:", err);
                const errMsg = 'Không thể truy cập Microphone: ' + err.message;
                appendLog(`🛑 [Clone Voice] ${errMsg}`, 'error');
                showToast(errMsg, 'error');
            }
        });

        btnStopCloneRecord.addEventListener('click', () => {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            btnStartCloneRecord.style.display = 'inline-flex';
            btnStopCloneRecord.style.display = 'none';
        });
    }

    // Reset Sample Button
    const btnRemoveCloneSample = document.getElementById('btnRemoveCloneSample');
    if (btnRemoveCloneSample) {
        btnRemoveCloneSample.addEventListener('click', () => {
            currentSamplePath = null;
            currentSampleUrl = null;
            if (cloneFileInput) cloneFileInput.value = '';
            const card = document.getElementById('cloneSampleStatusCard');
            if (card) card.style.display = 'none';
            const player = document.getElementById('cloneSampleAudioPlayer');
            if (player) {
                player.pause();
                player.src = '';
            }
            appendLog('ℹ️ [Clone Voice] Đã hủy file âm thanh mẫu hiện tại.', 'info');
            showToast('Đã hủy file âm thanh mẫu', 'info');
        });
    }

    // Preview Test Generation with Full Step-by-Step Logging
    const btnPreviewClonedVoice = document.getElementById('btnPreviewClonedVoice');
    const cloneTestText = document.getElementById('cloneTestText');
    const cloneProcessLogBox = document.getElementById('cloneProcessLogBox');
    const cloneProcessLogLines = document.getElementById('cloneProcessLogLines');
    const cloneProcessTitle = document.getElementById('cloneProcessTitle');
    const cloneProcessPct = document.getElementById('cloneProcessPct');
    const cloneLogSpinner = document.getElementById('cloneLogSpinner');
    const clonePreviewResultContainer = document.getElementById('clonePreviewResultContainer');
    const clonePreviewAudioPlayer = document.getElementById('clonePreviewAudioPlayer');

    if (btnPreviewClonedVoice) {
        btnPreviewClonedVoice.addEventListener('click', async () => {
            if (typeof window.checkFeaturePermission === 'function') {
                if (!window.checkFeaturePermission('can_clone_voice', 'Tạo giọng Clone Voice')) return;
            }

            if (!currentSamplePath) {
                const warn = 'Vui lòng tải lên file âm thanh mẫu hoặc ghi âm trước khi nghe thử!';
                appendLog(`⚠️ [Clone Voice] ${warn}`, 'warning');
                showToast(warn, 'warning');
                return;
            }
            const text = cloneTestText ? cloneTestText.value.trim() : '';
            if (!text) {
                const warn = 'Vui lòng nhập câu văn bản đọc nghe thử!';
                appendLog(`⚠️ [Clone Voice] ${warn}`, 'warning');
                showToast(warn, 'warning');
                return;
            }

            // Setup UI for live process logging
            btnPreviewClonedVoice.disabled = true;
            btnPreviewClonedVoice.style.opacity = '0.6';
            if (cloneProcessLogBox) cloneProcessLogBox.style.display = 'block';
            if (clonePreviewResultContainer) clonePreviewResultContainer.style.display = 'none';
            if (cloneLogSpinner) cloneLogSpinner.style.display = 'inline-block';
            if (cloneProcessPct) {
                cloneProcessPct.textContent = '10%';
                cloneProcessPct.style.color = '#38bdf8';
            }
            if (cloneProcessTitle) cloneProcessTitle.textContent = 'TIẾN TRÌNH TẠO BẢN NGHE THỬ';

            if (cloneProcessLogLines) {
                cloneProcessLogLines.innerHTML = '';
            }

            function addCloneLog(msg, type = 'info') {
                appendLog(msg, type);
                if (cloneProcessLogLines) {
                    const line = document.createElement('div');
                    line.style.color = type === 'error' ? '#ef4444' : (type === 'success' ? '#10b981' : (type === 'warning' ? '#f59e0b' : '#cbd5e1'));
                    line.textContent = msg;
                    cloneProcessLogLines.appendChild(line);
                    cloneProcessLogLines.scrollTop = cloneProcessLogLines.scrollHeight;
                }
            }

            addCloneLog(`[1/3] ℹ️ Bắt đầu xử lý văn bản: "${text.substring(0, 40)}..."`);
            addCloneLog(`[2/3] ℹ️ Nạp mẫu giọng: ${currentSamplePath}`);

            if (cloneProcessPct) cloneProcessPct.textContent = '40%';

            try {
                addCloneLog(`[3/3] ⏳ Đang gọi Local Voice ONNX Turbo (int8 48kHz) để tổng hợp âm thanh...`);
                
                const startTime = Date.now();
                const res = await fetch('/api/clone_voice/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        audio_path: currentSamplePath,
                        speed: 1.0
                    })
                });

                const data = await res.json();
                const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(2);

                if (data.success && data.audio_url) {
                    if (cloneProcessPct) {
                        cloneProcessPct.textContent = '100% Hoàn tất';
                        cloneProcessPct.style.color = '#10b981';
                    }
                    if (cloneLogSpinner) cloneLogSpinner.style.display = 'none';

                    addCloneLog(`✅ [Thành công] Đã phát sinh giọng đọc nghe thử chuẩn 48kHz trong ${elapsedSec}s!`, 'success');
                    
                    if (clonePreviewResultContainer && clonePreviewAudioPlayer) {
                        clonePreviewAudioPlayer.src = data.audio_url;
                        clonePreviewResultContainer.style.display = 'block';
                        clonePreviewAudioPlayer.play().catch(() => {});
                    }

                    showToast(`Tạo bản nghe thử thành công (${elapsedSec}s)!`, 'success');
                } else {
                    const errDetail = data.error || 'Máy chủ trả về kết quả không hợp lệ.';
                    if (cloneProcessPct) {
                        cloneProcessPct.textContent = 'Thất bại';
                        cloneProcessPct.style.color = '#ef4444';
                    }
                    if (cloneLogSpinner) cloneLogSpinner.style.display = 'none';

                    addCloneLog(`🛑 [LỖI PHÁT SINH]: ${errDetail}`, 'error');
                    showToast(`Lỗi tạo giọng: ${errDetail}`, 'error');
                }
            } catch (err) {
                console.error("Preview Clone Error:", err);
                if (cloneProcessPct) {
                    cloneProcessPct.textContent = 'Lỗi kết nối';
                    cloneProcessPct.style.color = '#ef4444';
                }
                if (cloneLogSpinner) cloneLogSpinner.style.display = 'none';

                addCloneLog(`🛑 [LỖI KẾT NỐI MÁY CHỦ]: ${err.message}`, 'error');
                showToast('Lỗi kết nối máy chủ: ' + err.message, 'error');
            } finally {
                btnPreviewClonedVoice.disabled = false;
                btnPreviewClonedVoice.style.opacity = '1';
            }
        });
    }

    // Save Cloned Voice to Library with all fields
    const btnSaveClonedVoice = document.getElementById('btnSaveClonedVoice');
    const cloneVoiceName = document.getElementById('cloneVoiceName');
    const cloneVoiceLang = document.getElementById('cloneVoiceLang');
    const cloneVoiceRegion = document.getElementById('cloneVoiceRegion');
    const cloneVoiceGender = document.getElementById('cloneVoiceGender');
    const cloneVoiceAge = document.getElementById('cloneVoiceAge');
    const cloneVoiceStyle = document.getElementById('cloneVoiceStyle');
    const cloneVoiceTag = document.getElementById('cloneVoiceTag');

    if (btnSaveClonedVoice) {
        btnSaveClonedVoice.addEventListener('click', async () => {
            if (typeof window.checkFeaturePermission === 'function') {
                if (!window.checkFeaturePermission('allow_save_cloned_voice', 'Lưu giọng vào Thư viện')) return;
            }

            const name = cloneVoiceName ? cloneVoiceName.value.trim() : '';
            if (!name) {
                const warn = 'Vui lòng nhập Tên hiển thị cho giọng nói!';
                appendLog(`⚠️ [Clone Voice] ${warn}`, 'warning');
                showToast(warn, 'warning');
                if (cloneVoiceName) cloneVoiceName.focus();
                return;
            }
            if (!currentSamplePath) {
                const warn = 'Vui lòng tải lên file âm thanh mẫu hoặc ghi âm trước khi lưu!';
                appendLog(`⚠️ [Clone Voice] ${warn}`, 'warning');
                showToast(warn, 'warning');
                return;
            }

            btnSaveClonedVoice.disabled = true;
            btnSaveClonedVoice.innerHTML = `<span>⏳ Đang lưu vĩnh viễn vào thư viện...</span>`;
            appendLog(`ℹ️ [Clone Voice] Bắt đầu lưu giọng "${name}" vào Thư viện Local Voice...`, 'info');

            const payload = {
                name: name,
                audio_path: currentSamplePath,
                lang: cloneVoiceLang ? cloneVoiceLang.value : 'Vietnamese',
                region: cloneVoiceRegion ? cloneVoiceRegion.value : 'Miền Bắc',
                gender: cloneVoiceGender ? cloneVoiceGender.value : 'Female',
                age: cloneVoiceAge ? cloneVoiceAge.value : 'young',
                style: cloneVoiceStyle ? cloneVoiceStyle.value : 'review',
                tag: cloneVoiceTag ? cloneVoiceTag.value.trim() : ''
            };

            try {
                const res = await fetch('/api/clone_voice/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    appendLog(`✅ [Clone Voice] Đã lưu thành công giọng "${name}" vào Thư viện! ID: ${data.voice.id}`, 'success');
                    showToast(data.message || `Đã lưu thành công giọng "${name}"!`, 'success');
                    
                    // Reset inputs
                    if (cloneVoiceName) cloneVoiceName.value = '';
                    if (cloneVoiceTag) cloneVoiceTag.value = '';
                    currentSamplePath = null;
                    currentSampleUrl = null;
                    const card = document.getElementById('cloneSampleStatusCard');
                    if (card) card.style.display = 'none';
                    const samplePlayer = document.getElementById('cloneSampleAudioPlayer');
                    if (samplePlayer) {
                        samplePlayer.pause();
                        samplePlayer.src = '';
                    }

                    // Reload lists
                    loadClonedVoicesList();
                    if (typeof window.fetchAndRenderVoiceLibrary === 'function') {
                        window.fetchAndRenderVoiceLibrary(true);
                    }
                } else {
                    const err = data.error || 'Không rõ nguyên nhân.';
                    appendLog(`🛑 [Clone Voice] Lỗi lưu giọng: ${err}`, 'error');
                    showToast('Lỗi lưu giọng nói: ' + err, 'error');
                }
            } catch (err) {
                console.error("Save Clone Error:", err);
                appendLog(`🛑 [Clone Voice] Lỗi khi lưu giọng: ${err.message}`, 'error');
                showToast('Lỗi khi lưu giọng nói: ' + err.message, 'error');
            } finally {
                btnSaveClonedVoice.disabled = false;
                btnSaveClonedVoice.innerHTML = `
                    <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                    <span>LƯU VĨNH VIỄN VÀO THƯ VIỆN GIỌNG NÓI</span>
                `;
            }
        });
    }

    // Modal Edit Voice Event Handlers
    const modalEditClonedVoice = document.getElementById('modalEditClonedVoice');
    const btnCloseEditVoiceModal = document.getElementById('btnCloseEditVoiceModal');
    const btnCancelEditVoice = document.getElementById('btnCancelEditVoice');
    const btnSubmitEditVoice = document.getElementById('btnSubmitEditVoice');

    if (btnCloseEditVoiceModal) {
        btnCloseEditVoiceModal.addEventListener('click', () => {
            if (modalEditClonedVoice) modalEditClonedVoice.style.display = 'none';
        });
    }
    if (btnCancelEditVoice) {
        btnCancelEditVoice.addEventListener('click', () => {
            if (modalEditClonedVoice) modalEditClonedVoice.style.display = 'none';
        });
    }

    if (btnSubmitEditVoice) {
        btnSubmitEditVoice.addEventListener('click', async () => {
            const voiceId = document.getElementById('editVoiceId')?.value;
            const name = document.getElementById('editVoiceName')?.value.trim();
            const lang = document.getElementById('editVoiceLang')?.value;
            const region = document.getElementById('editVoiceRegion')?.value;
            const gender = document.getElementById('editVoiceGender')?.value;
            const age = document.getElementById('editVoiceAge')?.value;
            const style = document.getElementById('editVoiceStyle')?.value;
            const tag = document.getElementById('editVoiceTag')?.value.trim();

            if (!voiceId) return;
            if (!name) {
                showToast('Vui lòng nhập tên hiển thị cho giọng!', 'warning');
                return;
            }

            btnSubmitEditVoice.disabled = true;
            btnSubmitEditVoice.textContent = 'Đang lưu...';

            try {
                const res = await fetch('/api/clone_voice/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        voice_id: voiceId,
                        name: name,
                        lang: lang,
                        region: region,
                        gender: gender,
                        age: age,
                        style: style,
                        tag: tag
                    })
                });

                const data = await res.json();
                if (data.success) {
                    showToast(data.message || 'Đã cập nhật thông tin giọng thành công!', 'success');
                    appendLog(`✅ [Clone Voice] Đã cập nhật thông tin giọng "${name}" (${voiceId})`, 'success');
                    if (modalEditClonedVoice) modalEditClonedVoice.style.display = 'none';

                    // Refresh both lists
                    loadClonedVoicesList();
                    if (typeof window.fetchAndRenderVoiceLibrary === 'function') {
                        window.fetchAndRenderVoiceLibrary(true);
                    }
                } else {
                    showToast('Lỗi cập nhật: ' + (data.error || 'Không rõ'), 'error');
                }
            } catch (err) {
                console.error("Update Clone Voice Error:", err);
                showToast('Lỗi khi cập nhật thông tin: ' + err.message, 'error');
            } finally {
                btnSubmitEditVoice.disabled = false;
                btnSubmitEditVoice.textContent = '💾 CẬP NHẬT THÔNG TIN';
            }
        });
    }

    // Search and Filter for Cloned Voice Collection
    const cloneSearchInput = document.getElementById('cloneSearchInput');
    const cloneGenderFilter = document.getElementById('cloneGenderFilter');

    if (cloneSearchInput) {
        cloneSearchInput.addEventListener('input', () => renderClonedVoiceCollection());
    }
    if (cloneGenderFilter) {
        cloneGenderFilter.addEventListener('change', () => renderClonedVoiceCollection());
    }

    // Initial Load
    loadClonedVoicesList();
}

/**
 * Open Modal to edit Cloned Voice metadata
 */
export function openEditVoiceModal(v) {
    const modal = document.getElementById('modalEditClonedVoice');
    if (!modal) return;

    const editVoiceId = document.getElementById('editVoiceId');
    const editVoiceName = document.getElementById('editVoiceName');
    const editVoiceLang = document.getElementById('editVoiceLang');
    const editVoiceRegion = document.getElementById('editVoiceRegion');
    const editVoiceGender = document.getElementById('editVoiceGender');
    const editVoiceAge = document.getElementById('editVoiceAge');
    const editVoiceStyle = document.getElementById('editVoiceStyle');
    const editVoiceTag = document.getElementById('editVoiceTag');

    const cleanName = (v.name || '').replace(' (Local Voice)', '').replace(' (RVC)', '').trim();

    if (editVoiceId) editVoiceId.value = v.id;
    if (editVoiceName) editVoiceName.value = cleanName;
    if (editVoiceLang) editVoiceLang.value = v.lang || 'Vietnamese';
    if (editVoiceRegion) editVoiceRegion.value = v.region || 'Hà Nội';
    if (editVoiceGender) editVoiceGender.value = v.gender || 'Female';
    if (editVoiceAge) editVoiceAge.value = v.age || 'young';
    if (editVoiceStyle) editVoiceStyle.value = v.style || 'review';
    if (editVoiceTag) editVoiceTag.value = v.tag || '';

    modal.style.display = 'flex';
}

/**
 * Upload sample file to backend for validation & mono 24kHz conversion
 */
async function uploadSampleFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('audio_file', file);
    formData.append('audio', file);

    appendLog(`ℹ️ [Clone Voice] Đang nạp và tối ưu file mẫu "${file.name}" (${(file.size / 1024).toFixed(1)} KB)...`, 'info');
    showToast('Đang tải và tối ưu file âm thanh mẫu...', 'info');

    try {
        const res = await fetch('/api/clone_voice/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            currentSamplePath = data.audio_path;
            currentSampleUrl = data.preview_url;

            const card = document.getElementById('cloneSampleStatusCard');
            const fileNameEl = document.getElementById('cloneSampleFileName');
            const durationEl = document.getElementById('cloneSampleDuration');
            const qualityEl = document.getElementById('cloneSampleQuality');
            const samplePlayer = document.getElementById('cloneSampleAudioPlayer');

            if (fileNameEl) fileNameEl.textContent = data.filename || file.name;
            if (durationEl) {
                if (data.is_trimmed && data.original_duration) {
                    durationEl.textContent = `${data.duration}s (đã tối ưu từ ${data.original_duration}s)`;
                } else {
                    durationEl.textContent = `${data.duration}s`;
                }
            }
            if (qualityEl) {
                const isGood = Number(data.quality_score) >= 80;
                qualityEl.textContent = `${isGood ? '🟢' : '🟡'} Chất lượng: ${data.quality_desc || (isGood ? 'Rất tốt (24kHz Mono)' : 'Ổn định')}`;
                qualityEl.style.color = isGood ? '#10b981' : '#f59e0b';
            }

            if (samplePlayer && currentSampleUrl) {
                samplePlayer.src = currentSampleUrl;
                samplePlayer.load();
            }

            if (card) card.style.display = 'flex';

            if (data.is_trimmed && data.original_duration) {
                appendLog(`✂️ [Clone Voice] Tệp âm thanh gốc dài ${data.original_duration}s đã được tự động cắt & tối ưu đoạn mẫu ${data.duration}s chuẩn phòng thu.`, 'info');
                showToast(`Đã tự động tối ưu & cắt ${data.duration}s giọng mẫu chuẩn (từ tệp ${data.original_duration}s)!`, 'success');
            } else {
                appendLog(`✅ [Clone Voice] Nạp file mẫu thành công: Thời lượng ${data.duration}s • Tần số chuẩn hóa 24kHz Mono.`, 'success');
                showToast(`Nạp âm thanh mẫu thành công (${data.duration}s)! Hãy nghe lại ở khung bên dưới.`, 'success');
            }
        } else {
            const err = data.error || 'Tệp không hợp lệ';
            appendLog(`🛑 [Clone Voice Lỗi File Mẫu]: ${err}`, 'error');
            showToast('Lỗi âm thanh mẫu: ' + err, 'error');
        }
    } catch (err) {
        console.error("Upload Sample Error:", err);
        appendLog(`🛑 [Clone Voice Lỗi Kết Nối]: ${err.message}`, 'error');
        showToast('Lỗi khi tải file mẫu: ' + err.message, 'error');
    }
}

/**
 * Load all cloned voices from API
 */
export async function loadClonedVoicesList() {
    try {
        const res = await fetch('/api/voices');
        const allVoices = await res.json();
        
        const voicesArr = Array.isArray(allVoices) ? allVoices : (allVoices && Array.isArray(allVoices.voices) ? allVoices.voices : []);
        clonedVoicesCache = voicesArr.filter(v => 
            v && v.provider === 'local_voice' && (v.is_custom === true || (v.id && (v.id.startsWith('local_custom_') || v.id.startsWith('local_clone_'))))
        );

        const countBadge = document.getElementById('cloneCollectionCount');
        if (countBadge) {
            countBadge.textContent = `${clonedVoicesCache.length} giọng`;
        }

        renderClonedVoiceCollection();
    } catch (err) {
        console.error("Load Cloned Voices Error:", err);
    }
}

/**
 * Render Cloned Voice Collection in Right Column with Edit, Preview, and Delete
 */
function renderClonedVoiceCollection() {
    const listContainer = document.getElementById('cloneVoiceList');
    if (!listContainer) return;

    const searchTerm = (document.getElementById('cloneSearchInput')?.value || '').trim().toLowerCase();
    const genderFilter = document.getElementById('cloneGenderFilter')?.value || '';

    const filtered = clonedVoicesCache.filter(v => {
        if (genderFilter && v.gender !== genderFilter) return false;
        if (searchTerm) {
            const matchName = (v.name || '').toLowerCase().includes(searchTerm);
            const matchRegion = (v.region || '').toLowerCase().includes(searchTerm);
            const matchTag = (v.tag || '').toLowerCase().includes(searchTerm);
            const matchLang = (v.lang || '').toLowerCase().includes(searchTerm);
            if (!matchName && !matchRegion && !matchTag && !matchLang) return false;
        }
        return true;
    });

    if (filtered.length === 0) {
        listContainer.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #64748b;">
                <div style="font-size: 32px; margin-bottom: 8px;">🎙️</div>
                <div style="font-size: 13px; font-weight: 600; color: #94a3b8;">${clonedVoicesCache.length === 0 ? 'Chưa có giọng nhân bản nào' : 'Không tìm thấy giọng phù hợp'}</div>
                <div style="font-size: 11.5px; color: #64748b; margin-top: 4px;">Tải lên file mẫu 3–5 giây ở cột bên trái để nhân bản giọng đọc mới!</div>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = '';
    filtered.forEach(v => {
        const item = document.createElement('div');
        item.className = 'cloned-voice-item';
        item.style.cssText = `
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 12px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            transition: all 0.2s ease;
        `;

        const styleBadge = v.style === 'review' ? '🎬 Review Phim' : (v.style === 'story' ? '🎙️ Kể chuyện' : (v.style === 'news' ? '📰 Thời sự' : (v.style === 'emotional' ? '💖 Tình cảm' : (v.style === 'action' ? '⚡ Kịch tính' : '🎀 Anime'))));
        const ageBadge = v.age === 'young' ? '🧑 Trẻ' : (v.age === 'middle_aged' ? '👨‍💼 Trung niên' : (v.age === 'old' ? '👴 Lớn tuổi' : '👶 Trẻ em'));
        const cleanName = (v.name || '').replace(' (Local Voice)', '');

        item.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; flex: 1; overflow: hidden;">
                <div style="width: 40px; height: 40px; border-radius: 8px; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.3); display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0;">
                    ${escapeHtml(v.avatar || (v.gender === 'Male' ? '👨' : '👩'))}
                </div>
                <div style="overflow: hidden; flex: 1;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 13.5px; font-weight: 700; color: #f8fafc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${escapeHtml(cleanName)}</span>
                        <span style="font-size: 9.5px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 1px 6px; border-radius: 4px; font-weight: 700; white-space: nowrap;">LOCAL VOICE</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 5px; margin-top: 3px; font-size: 11px; color: #94a3b8; flex-wrap: wrap;">
                        <span>${v.gender === 'Female' ? '👩 Nữ' : '👨 Nam'}</span>
                        <span>•</span>
                        <span style="color: #38bdf8;">${escapeHtml(v.region || 'Miền Bắc')}</span>
                        <span>•</span>
                        <span>${ageBadge}</span>
                        <span>•</span>
                        <span style="color: #cbd5e1;">${styleBadge}</span>
                    </div>
                </div>
            </div>

            <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
                <button type="button" class="btn-preview-clone-item" style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; border-radius: 6px; padding: 6px 9px; font-size: 11.5px; font-weight: 600; display: flex; align-items: center; gap: 4px; cursor: pointer; transition: all 0.2s;" title="Nghe thử file mẫu của giọng này">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                    <span>Nghe</span>
                </button>
                <button type="button" class="btn-edit-clone-item" style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); color: #f59e0b; border-radius: 6px; padding: 6px 9px; font-size: 11.5px; font-weight: 600; display: flex; align-items: center; gap: 4px; cursor: pointer; transition: all 0.2s;" title="Chỉnh sửa thông tin tên, địa phương, phong cách...">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    <span>Sửa</span>
                </button>
                <button type="button" class="btn-delete-clone-item" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; border-radius: 6px; padding: 6px 9px; font-size: 11.5px; font-weight: 600; display: flex; align-items: center; gap: 4px; cursor: pointer; transition: all 0.2s;" title="Xóa giọng này khỏi thư viện">
                    <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                </button>
            </div>
        `;

        // Wire preview
        const btnPrev = item.querySelector('.btn-preview-clone-item');
        btnPrev.addEventListener('click', () => {
            if (typeof window.playPreviewVoice === 'function') {
                window.playPreviewVoice(v.id, btnPrev);
            }
        });

        // Wire edit
        const btnEdit = item.querySelector('.btn-edit-clone-item');
        btnEdit.addEventListener('click', () => {
            openEditVoiceModal(v);
        });

        // Wire delete
        const btnDel = item.querySelector('.btn-delete-clone-item');
        btnDel.addEventListener('click', async () => {
            const confirmed = await showConfirmModal({
                title: 'XÓA GIỌNG CLONE',
                message: `Bạn có chắc chắn muốn xóa vĩnh viễn giọng "${v.name}" khỏi thư viện không?`,
                icon: '🗑️',
                confirmText: 'Xóa Giọng',
                confirmType: 'danger'
            });
            if (!confirmed) return;
            try {
                const res = await fetch('/api/clone_voice/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ voice_id: v.id })
                });
                const data = await res.json();
                if (data.success) {
                    appendLog(`ℹ️ [Clone Voice] Đã xóa giọng "${v.name}" khỏi Thư viện.`, 'info');
                    showToast(data.message || `Đã xóa giọng "${v.name}"!`, 'info');
                    loadClonedVoicesList();
                    if (typeof window.fetchAndRenderVoiceLibrary === 'function') {
                        window.fetchAndRenderVoiceLibrary(true);
                    }
                } else {
                    showToast('Lỗi xóa giọng: ' + (data.error || 'Không rõ'), 'error');
                }
            } catch (err) {
                console.error("Delete Clone Voice Error:", err);
                showToast('Lỗi kết nối khi xóa giọng: ' + err.message, 'error');
            }
        });

        listContainer.appendChild(item);
    });
}
