import { showToast } from '../utils.js';

let capcutDraftsCache = [];
let capcutCurrentTracks = [];

const capcutDraftSelect = document.getElementById('capcutDraftSelect');
const capcutTrackSelect = document.getElementById('capcutTrackSelect');
const btnCapCutRefreshDrafts = document.getElementById('btnCapCutRefreshDrafts');
const btnCapCutOpenDraftFolder = document.getElementById('btnCapCutOpenDraftFolder');
const btnCapCutStartSync = document.getElementById('btnCapCutStartSync');
const capcutDraftCountBadge = document.getElementById('capcutDraftCountBadge');
const capcutStatVideos = document.getElementById('capcutStatVideos');
const capcutStatPhotos = document.getElementById('capcutStatPhotos');
const capcutStatSubs = document.getElementById('capcutStatSubs');
const capcutAutoRelaunch = document.getElementById('capcutAutoRelaunch');

export async function loadCapCutDrafts(selectFirst = true) {
    if (!capcutDraftSelect) return;
    capcutDraftSelect.innerHTML = '<option value="">Đang quét danh sách dự án CapCut...</option>';
    if (capcutDraftCountBadge) capcutDraftCountBadge.textContent = 'Đang quét...';
    
    try {
        const res = await fetch('/api/capcut/drafts');
        const data = await res.json();
        
        if (data.success && Array.isArray(data.drafts)) {
            capcutDraftsCache = data.drafts;
            if (capcutDraftCountBadge) capcutDraftCountBadge.textContent = `${data.drafts.length} Dự án`;
            
            if (data.drafts.length === 0) {
                capcutDraftSelect.innerHTML = '<option value="">Không tìm thấy dự án CapCut nào</option>';
                if (capcutTrackSelect) capcutTrackSelect.innerHTML = '<option value="">Chưa có dự án nào</option>';
                updateCapCutStats(0, 0, 0);
                return;
            }
            
            capcutDraftSelect.innerHTML = '<option value="">-- Chọn một Dự án CapCut --</option>';
            data.drafts.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.path;
                opt.textContent = `🎬 ${d.name} (${d.time_str})`;
                opt.dataset.duration = d.duration;
                capcutDraftSelect.appendChild(opt);
            });
            
            // Tự động chọn dự án mới nhất
            if (selectFirst && data.drafts.length > 0) {
                capcutDraftSelect.value = data.drafts[0].path;
                loadCapCutTracks(data.drafts[0].path);
            }
        } else {
            capcutDraftSelect.innerHTML = '<option value="">Lỗi nạp danh sách dự án</option>';
            showToast('Không thể lấy danh sách dự án CapCut: ' + (data.error || 'Lỗi không xác định'), 'error');
        }
    } catch (err) {
        capcutDraftSelect.innerHTML = '<option value="">Lỗi kết nối máy chủ</option>';
        showToast('Lỗi khi tải dự án CapCut: ' + err.message, 'error');
    }
}

async function loadCapCutTracks(draftPath) {
    if (!draftPath) {
        if (capcutTrackSelect) capcutTrackSelect.innerHTML = '<option value="">Vui lòng chọn Dự án trước...</option>';
        updateCapCutStats(0, 0, 0);
        return;
    }
    
    if (capcutTrackSelect) capcutTrackSelect.innerHTML = '<option value="">Đang phân tích cấu trúc Track...</option>';
    
    try {
        const res = await fetch('/api/capcut/tracks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft_path: draftPath })
        });
        const data = await res.json();
        
        if (data.success && Array.isArray(data.tracks)) {
            capcutCurrentTracks = data.tracks;
            const subCount = data.total_subtitles || 0;
            
            if (data.tracks.length === 0) {
                capcutTrackSelect.innerHTML = '<option value="">Dự án này không có track video nào</option>';
                updateCapCutStats(0, 0, subCount);
                return;
            }
            
            capcutTrackSelect.innerHTML = '';
            let bestTrack = null;
            let maxSegments = -1;
            
            data.tracks.forEach((t, idx) => {
                const opt = document.createElement('option');
                opt.value = t.id;
                const totalClips = t.segment_count || 0;
                opt.textContent = `Track ${idx + 1} (${totalClips} clip: ${t.video_count || 0} video, ${t.photo_count || 0} ảnh)`;
                capcutTrackSelect.appendChild(opt);
                
                if (totalClips > maxSegments) {
                    maxSegments = totalClips;
                    bestTrack = t;
                }
            });
            
            if (bestTrack) {
                capcutTrackSelect.value = bestTrack.id;
                updateCapCutStats(bestTrack.video_count || 0, bestTrack.photo_count || 0, subCount);
            }
        } else {
            capcutTrackSelect.innerHTML = '<option value="">Không thể đọc track video</option>';
            showToast('Lỗi khi đọc track: ' + (data.error || 'Lỗi không xác định'), 'error');
        }
    } catch (err) {
        capcutTrackSelect.innerHTML = '<option value="">Lỗi kết nối máy chủ</option>';
        showToast('Lỗi khi nạp track: ' + err.message, 'error');
    }
}

function updateCapCutStats(videos, photos, subs) {
    if (capcutStatVideos) capcutStatVideos.textContent = videos;
    if (capcutStatPhotos) capcutStatPhotos.textContent = photos;
    if (capcutStatSubs) capcutStatSubs.textContent = subs;
}

if (capcutDraftSelect) {
    capcutDraftSelect.addEventListener('change', () => {
        loadCapCutTracks(capcutDraftSelect.value);
    });
}

if (capcutTrackSelect) {
    capcutTrackSelect.addEventListener('change', () => {
        const selectedId = capcutTrackSelect.value;
        const found = capcutCurrentTracks.find(t => String(t.id) === String(selectedId));
        if (found) {
            updateCapCutStats(found.video_count || 0, found.photo_count || 0, parseInt(capcutStatSubs?.textContent || '0'));
        }
    });
}

if (btnCapCutRefreshDrafts) {
    btnCapCutRefreshDrafts.addEventListener('click', () => {
        loadCapCutDrafts(true);
        showToast('Đã quét lại danh sách dự án CapCut', 'info');
    });
}

if (btnCapCutOpenDraftFolder) {
    btnCapCutOpenDraftFolder.addEventListener('click', async () => {
        const draftPath = capcutDraftSelect?.value || '';
        try {
            await fetch('/api/capcut/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ draft_path: draftPath })
            });
        } catch (e) {}
    });
}

if (btnCapCutStartSync) {
    btnCapCutStartSync.addEventListener('click', async () => {
        if (typeof window.checkFeaturePermission === 'function') {
            if (!window.checkFeaturePermission('can_access_editor', 'Đồng bộ CapCut')) return;
        }

        const draftPath = capcutDraftSelect?.value;
        const targetTrackId = capcutTrackSelect?.value;
        
        if (!draftPath) {
            showToast('Vui lòng chọn một Dự án CapCut', 'warning');
            return;
        }
        if (!targetTrackId) {
            showToast('Vui lòng chọn Track Video cần đồng bộ', 'warning');
            return;
        }
        
        const shortActionRadio = document.querySelector('input[name="capcut_short_action"]:checked');
        const shortAction = shortActionRadio ? shortActionRadio.value : 'slow';
        
        const longActionRadio = document.querySelector('input[name="capcut_long_action"]:checked');
        const longAction = longActionRadio ? longActionRadio.value : 'cut';
        
        const subSourceRadio = document.querySelector('input[name="capcut_sub_source"]:checked');
        const subSource = subSourceRadio ? subSourceRadio.value : 'internal';
        
        const relaunch = capcutAutoRelaunch ? capcutAutoRelaunch.checked : true;
        
        let customSubtitles = null;
        if (subSource === 'editor') {
            if (window.subtitles && window.subtitles.length > 0) {
                customSubtitles = window.subtitles;
            } else {
                showToast('Tab Biên tập phim chưa có dữ liệu phụ đề. Hệ thống sẽ tự động dùng phụ đề trong CapCut.', 'info');
            }
        }
        
        const origBtnText = btnCapCutStartSync.innerHTML;
        btnCapCutStartSync.disabled = true;
        btnCapCutStartSync.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:16px;height:16px;margin-right:8px;vertical-align:middle;"></span> Đang đồng bộ Timeline CapCut...';
        
        try {
            const res = await fetch('/api/capcut/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    draft_path: draftPath,
                    target_track_id: targetTrackId,
                    short_video_action: shortAction,
                    long_video_action: longAction,
                    subtitles: customSubtitles,
                    relaunch: relaunch
                })
            });
            
            const data = await res.json();
            if (data.success) {
                showToast(data.message || 'Đồng bộ CapCut thành công!', 'success');
                loadCapCutTracks(draftPath);
            } else {
                showToast('Lỗi đồng bộ: ' + (data.error || 'Không thể đồng bộ timeline'), 'error');
            }
        } catch (err) {
            showToast('Lỗi khi gửi yêu cầu đồng bộ: ' + err.message, 'error');
        } finally {
            btnCapCutStartSync.disabled = false;
            btnCapCutStartSync.innerHTML = origBtnText;
        }
    });
}

// =========================================================================
// CUSTOM RVC VOICE CONTROLLER
// =========================================================================
const addRvcVoiceModal = document.getElementById('addRvcVoiceModal');
const btnOpenAddRvcModal = document.getElementById('btnOpenAddRvcModal');
const btnCloseAddRvcModal = document.getElementById('btnCloseAddRvcModal');
const btnCancelAddRvc = document.getElementById('btnCancelAddRvc');
const btnBrowseRvcModel = document.getElementById('btnBrowseRvcModel');
const btnBrowseRvcIndex = document.getElementById('btnBrowseRvcIndex');
const addRvcName = document.getElementById('addRvcName');
const addRvcModelPath = document.getElementById('addRvcModelPath');
const addRvcIndexPath = document.getElementById('addRvcIndexPath');
const addRvcGender = document.getElementById('addRvcGender');
const addRvcStyle = document.getElementById('addRvcStyle');
const addRvcBaseVoice = document.getElementById('addRvcBaseVoice');
const addRvcPitch = document.getElementById('addRvcPitch');
const addRvcPitchVal = document.getElementById('addRvcPitchVal');
const btnSaveAddRvc = document.getElementById('btnSaveAddRvc');

if (btnOpenAddRvcModal && addRvcVoiceModal) {
    btnOpenAddRvcModal.addEventListener('click', () => {
        addRvcVoiceModal.style.display = 'flex';
    });
}

function closeAddRvcModal() {
    if (addRvcVoiceModal) addRvcVoiceModal.style.display = 'none';
}

if (btnCloseAddRvcModal) btnCloseAddRvcModal.addEventListener('click', closeAddRvcModal);
if (btnCancelAddRvc) btnCancelAddRvc.addEventListener('click', closeAddRvcModal);
if (addRvcVoiceModal) {
    addRvcVoiceModal.addEventListener('click', (e) => {
        if (e.target === addRvcVoiceModal) closeAddRvcModal();
    });
}

// Pitch slider live update
if (addRvcPitch && addRvcPitchVal) {
    addRvcPitch.addEventListener('input', () => {
        const val = parseInt(addRvcPitch.value) || 0;
        addRvcPitchVal.textContent = (val > 0 ? `+${val}` : `${val}`);
    });
}

// Gender change auto update base voice
if (addRvcGender && addRvcBaseVoice) {
    addRvcGender.addEventListener('change', () => {
        if (addRvcGender.value === 'Female') {
            addRvcBaseVoice.value = 'edge_vi-VN-HoaiMyNeural';
        } else {
            addRvcBaseVoice.value = 'edge_vi-VN-NamMinhNeural';
        }
    });
}

// Browse .pth Model
if (btnBrowseRvcModel && addRvcModelPath) {
    btnBrowseRvcModel.addEventListener('click', async () => {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.select_model_file) {
            const path = await window.pywebview.api.select_model_file();
            if (path) {
                addRvcModelPath.value = path;
                if (!addRvcName.value.trim()) {
                    const filename = path.split(/[\/\\]/).pop().replace(/\.pth$/i, '');
                    addRvcName.value = filename.charAt(0).toUpperCase() + filename.slice(1);
                }
            }
        } else {
            showToast('Tính năng chọn file chỉ khả dụng trên ứng dụng Desktop.', 'info');
        }
    });
}

// Browse .index file
if (btnBrowseRvcIndex && addRvcIndexPath) {
    btnBrowseRvcIndex.addEventListener('click', async () => {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.select_rvc_index_file) {
            const path = await window.pywebview.api.select_rvc_index_file();
            if (path) addRvcIndexPath.value = path;
        } else {
            showToast('Tính năng chọn file chỉ khả dụng trên ứng dụng Desktop.', 'info');
        }
    });
}

// Save RVC Voice
if (btnSaveAddRvc) {
    btnSaveAddRvc.addEventListener('click', async () => {
        const name = addRvcName ? addRvcName.value.trim() : '';
        const modelPath = addRvcModelPath ? addRvcModelPath.value.trim() : '';
        const indexPath = addRvcIndexPath ? addRvcIndexPath.value.trim() : '';
        const gender = addRvcGender ? addRvcGender.value : 'Female';
        const style = addRvcStyle ? addRvcStyle.value : 'review';
        const baseVoice = addRvcBaseVoice ? addRvcBaseVoice.value : 'edge_vi-VN-HoaiMyNeural';
        const pitch = addRvcPitch ? parseInt(addRvcPitch.value) || 0 : 0;

        if (!name) {
            showToast('Vui lòng nhập tên giọng đọc hiển thị.', 'error');
            return;
        }
        if (!modelPath) {
            showToast('Vui lòng chọn file mô hình RVC (.pth).', 'error');
            return;
        }

        const originalBtnText = btnSaveAddRvc.innerHTML;
        btnSaveAddRvc.disabled = true;
        btnSaveAddRvc.innerHTML = 'Đang lưu...';

        try {
            const res = await fetch('/api/custom-voices', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: name,
                    model_path: modelPath,
                    index_path: indexPath,
                    gender: gender,
                    style: style,
                    base_voice: baseVoice,
                    pitch: pitch
                })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Đã thêm thành công giọng RVC: ${name}!`, 'success');
                closeAddRvcModal();
                if (typeof fetchAndRenderVoiceLibrary === 'function') {
                    fetchAndRenderVoiceLibrary();
                }
            } else {
                showToast(`Lỗi: ${data.error || 'Không thể lưu giọng RVC'}`, 'error');
            }
        } catch (e) {
            showToast(`Lỗi kết nối khi lưu giọng: ${e.message}`, 'error');
        } finally {
            btnSaveAddRvc.disabled = false;
            btnSaveAddRvc.innerHTML = originalBtnText;
        }
    });
}
