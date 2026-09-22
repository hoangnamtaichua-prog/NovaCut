import { showToast, escapeHtml, appendLog } from '../utils.js';

// Trạng thái cục bộ của module Đăng mạng xã hội
let currentPlatforms = [];
let currentProfiles = [];
let selectedPlatformId = 'youtube';
let selectedProfileId = 'Default';
let selectedVideoPath = '';
let isReviewing = false;

// DOM Elements
const socialPlatformCards = document.getElementById('socialPlatformCards');
const socialProfileSelect = document.getElementById('socialProfileSelect');
const btnRefreshSocialProfiles = document.getElementById('btnRefreshSocialProfiles');
const socialVideoPathInput = document.getElementById('socialVideoPathInput');
const btnBrowseSocialVideo = document.getElementById('btnBrowseSocialVideo');
const btnUseLastExportedVideo = document.getElementById('btnUseLastExportedVideo');
const socialVideoInfoCard = document.getElementById('socialVideoInfoCard');
const socialTitleInput = document.getElementById('socialTitleInput');
const socialTitleCount = document.getElementById('socialTitleCount');
const socialDescInput = document.getElementById('socialDescInput');
const socialDescCount = document.getElementById('socialDescCount');
const socialHashtagsInput = document.getElementById('socialHashtagsInput');
const socialPrivacySelect = document.getElementById('socialPrivacySelect');
const btnSocialReviewAndOpen = document.getElementById('btnSocialReviewAndOpen');
const btnSocialCopyTitle = document.getElementById('btnSocialCopyTitle');
const btnSocialCopyDesc = document.getElementById('btnSocialCopyDesc');
const btnSocialCopyPath = document.getElementById('btnSocialCopyPath');
const socialPreviewContainer = document.getElementById('socialPreviewContainer');
const socialHistoryTableBody = document.getElementById('socialHistoryTableBody');
const btnClearSocialHistory = document.getElementById('btnClearSocialHistory');
const socialHistoryBadge = document.getElementById('socialHistoryBadge');
const socialChromeStatusAlert = document.getElementById('socialChromeStatusAlert');

/**
 * Khởi tạo toàn bộ chức năng Social Publisher
 */
export async function initSocialPublisher() {
    bindSocialEvents();
    await Promise.all([
        loadSocialPlatforms(),
        loadSocialProfiles(),
        loadSocialHistory()
    ]);
}

/**
 * Gắn các sự kiện lắng nghe tương tác người dùng
 */
function bindSocialEvents() {
    if (btnRefreshSocialProfiles) {
        btnRefreshSocialProfiles.addEventListener('click', () => {
            loadSocialProfiles(true);
        });
    }

    if (socialProfileSelect) {
        socialProfileSelect.addEventListener('change', (e) => {
            selectedProfileId = e.target.value || 'Default';
            updatePreview();
        });
    }

    if (socialTitleInput) {
        socialTitleInput.addEventListener('input', () => {
            updateCharCounts();
            updatePreview();
        });
    }

    if (socialDescInput) {
        socialDescInput.addEventListener('input', () => {
            updateCharCounts();
            updatePreview();
        });
    }

    if (socialHashtagsInput) {
        socialHashtagsInput.addEventListener('input', () => {
            updatePreview();
        });
    }

    if (socialPrivacySelect) {
        socialPrivacySelect.addEventListener('change', () => {
            updatePreview();
        });
    }

    // Nút chọn video từ máy tính
    if (btnBrowseSocialVideo) {
        btnBrowseSocialVideo.addEventListener('click', async () => {
            try {
                // Tạo input file ảo để người dùng duyệt file video
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'video/mp4,video/quicktime,video/x-matroska,video/webm,video/*';
                input.onchange = async (e) => {
                    const file = e.target.files[0];
                    if (!file) return;

                    // Đối với pywebview trên Desktop, file có thể có thuộc tính path
                    const path = file.path || file.name;
                    setSocialVideo(path, file.name, file.size);
                };
                input.click();
            } catch (err) {
                showToast('Không thể mở hộp thoại chọn tệp: ' + err.message, 'error');
            }
        });
    }

    // Nhập trực tiếp đường dẫn video
    if (socialVideoPathInput) {
        socialVideoPathInput.addEventListener('change', (e) => {
            const path = e.target.value.trim();
            if (path) {
                setSocialVideo(path);
            }
        });
    }

    // Nút dùng nhanh video vừa xuất gần nhất
    if (btnUseLastExportedVideo) {
        btnUseLastExportedVideo.addEventListener('click', () => {
            useLatestExportedVideo();
        });
    }

    // Nút thao tác mở trình duyệt Chrome
    if (btnSocialReviewAndOpen) {
        btnSocialReviewAndOpen.addEventListener('click', () => {
            handleReviewAndOpenChrome();
        });
    }

    // Các nút sao chép nhanh
    if (btnSocialCopyTitle) {
        btnSocialCopyTitle.addEventListener('click', () => {
            const title = socialTitleInput ? socialTitleInput.value.trim() : '';
            if (!title) {
                showToast('Chưa có tiêu đề để sao chép!', 'warning');
                return;
            }
            copyToClipboard(title, 'Đã sao chép Tiêu đề!');
        });
    }

    if (btnSocialCopyDesc) {
        btnSocialCopyDesc.addEventListener('click', () => {
            const desc = socialDescInput ? socialDescInput.value.trim() : '';
            const tags = socialHashtagsInput ? socialHashtagsInput.value.trim() : '';
            let text = desc;
            if (tags) text = text ? `${text}\n\n${tags}` : tags;
            if (!text) {
                showToast('Chưa có mô tả để sao chép!', 'warning');
                return;
            }
            copyToClipboard(text, 'Đã sao chép Mô tả / Caption!');
        });
    }

    if (btnSocialCopyPath) {
        btnSocialCopyPath.addEventListener('click', () => {
            if (!selectedVideoPath) {
                showToast('Chưa chọn video!', 'warning');
                return;
            }
            copyToClipboard(selectedVideoPath, 'Đã sao chép Đường dẫn Video!');
        });
    }

    // Thêm nhanh hashtag mẫu khi click vào badge tag
    document.querySelectorAll('.btn-quick-hashtag').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tag = e.currentTarget.getAttribute('data-tag');
            if (!tag || !socialHashtagsInput) return;
            let current = socialHashtagsInput.value.trim();
            if (!current.includes(tag)) {
                socialHashtagsInput.value = current ? `${current} ${tag}` : tag;
                updatePreview();
            }
        });
    });

    // Nút xóa lịch sử
    if (btnClearSocialHistory) {
        btnClearSocialHistory.addEventListener('click', async () => {
            if (typeof window.showConfirmModal === 'function') {
                const confirmed = await window.showConfirmModal({
                    title: 'Xóa lịch sử đăng video',
                    message: 'Bạn có chắc chắn muốn xóa toàn bộ lịch sử thao tác đăng mạng xã hội không?',
                    theme: 'danger'
                });
                if (!confirmed) return;
            }
            clearSocialHistory();
        });
    }
}

/**
 * Nạp danh sách các nền tảng từ Backend
 */
export async function loadSocialPlatforms() {
    try {
        const res = await fetch('/api/social/platforms');
        const data = await res.json();
        if (data.success && Array.isArray(data.platforms)) {
            currentPlatforms = data.platforms;
            renderPlatformCards(data.platforms);
            selectPlatform(selectedPlatformId);
        }
    } catch (err) {
        appendLog(`[Social Publisher] Lỗi nạp nền tảng: ${err.message}`, 'error');
    }
}

/**
 * Hiển thị các thẻ chọn mạng xã hội
 */
function renderPlatformCards(platforms) {
    if (!socialPlatformCards) return;
    socialPlatformCards.innerHTML = '';

    platforms.forEach(plat => {
        const card = document.createElement('div');
        card.className = `social-platform-item ${plat.id === selectedPlatformId ? 'active' : ''}`;
        card.setAttribute('data-id', plat.id);
        card.title = `${plat.name} - ${plat.category}`;

        // Icon SVG tương ứng
        let iconSvg = getPlatformIconSvg(plat.id);

        card.innerHTML = `
            <div class="plat-icon-wrap">${iconSvg}</div>
            <div class="plat-info">
                <div class="plat-name">${escapeHtml(plat.name)}</div>
                <div class="plat-cat">${escapeHtml(plat.category)}</div>
            </div>
            ${plat.supports_direct_upload ? '<span class="plat-badge-direct" title="Hỗ trợ mở thẳng trang tải lên">Trực tiếp</span>' : ''}
        `;

        card.addEventListener('click', () => {
            selectPlatform(plat.id);
        });

        socialPlatformCards.appendChild(card);
    });
}

/**
 * Lấy SVG Icon của nền tảng
 */
function getPlatformIconSvg(id) {
    switch (id) {
        case 'youtube':
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="#ef4444"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>`;
        case 'tiktok':
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="#22d3ee"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.24 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>`;
        case 'facebook':
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="#3b82f6"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>`;
        case 'instagram':
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="#e1306c"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>`;
        case 'x_twitter':
            return `<svg viewBox="0 0 24 24" width="20" height="20" fill="#f8fafc"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`;
        case 'linkedin':
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="#0ea5e9"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45a1.64 1.64 0 1 0 0 3.28 1.64 1.64 0 0 0 0-3.28z"/></svg>`;
        default:
            return `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/></svg>`;
    }
}

/**
 * Chọn mạng xã hội hiện tại
 */
export function selectPlatform(platformId) {
    selectedPlatformId = platformId;

    // Cập nhật class active trên các card
    document.querySelectorAll('.social-platform-item').forEach(el => {
        if (el.getAttribute('data-id') === platformId) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });

    const plat = currentPlatforms.find(p => p.id === platformId);
    if (!plat) return;

    // Cập nhật các trường nhập liệu tương ứng
    const titleGroup = document.getElementById('socialTitleGroup');
    const descLabel = document.getElementById('socialDescLabel');
    if (titleGroup) {
        titleGroup.style.display = plat.has_separate_title ? 'block' : 'none';
    }
    if (descLabel) {
        descLabel.textContent = plat.has_separate_title ? 'Mô tả bài đăng (Description)' : 'Nội dung bài đăng (Caption & Nội dung)';
    }

    // Cập nhật danh sách quyền riêng tư
    if (socialPrivacySelect && Array.isArray(plat.privacy_options)) {
        socialPrivacySelect.innerHTML = '';
        plat.privacy_options.forEach(opt => {
            const el = document.createElement('option');
            el.value = opt.id;
            el.textContent = opt.label;
            if (opt.id === plat.default_privacy) el.selected = true;
            socialPrivacySelect.appendChild(el);
        });
    }

    // Cập nhật ghi chú gợi ý
    const tipsBox = document.getElementById('socialPlatformTips');
    if (tipsBox) {
        tipsBox.textContent = plat.tips || '';
    }

    updateCharCounts();
    updatePreview();
}

/**
 * Dò tìm và nạp danh sách Chrome Profile
 */
export async function loadSocialProfiles(showNotify = false) {
    if (!socialProfileSelect) return;
    socialProfileSelect.innerHTML = '<option value="">Đang quét danh sách Chrome Profile...</option>';

    try {
        const res = await fetch('/api/social/profiles');
        const data = await res.json();

        if (data.success) {
            currentProfiles = data.profiles || [];

            if (!data.chrome_installed) {
                if (socialChromeStatusAlert) {
                    socialChromeStatusAlert.style.display = 'flex';
                    socialChromeStatusAlert.innerHTML = `
                        <span>⚠️ Không tìm thấy Google Chrome trên máy tính. Bạn vẫn có thể chuẩn bị nội dung, nhưng vui lòng cài Chrome để mở nhanh profile tự động.</span>
                    `;
                }
                socialProfileSelect.innerHTML = '<option value="Default">Chưa phát hiện Google Chrome</option>';
                return;
            }

            if (socialChromeStatusAlert) {
                socialChromeStatusAlert.style.display = 'none';
            }

            socialProfileSelect.innerHTML = '';
            currentProfiles.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = `👤 ${p.display_name}`;
                if (p.id === data.default_profile || p.is_default) {
                    opt.selected = true;
                    selectedProfileId = p.id;
                }
                socialProfileSelect.appendChild(opt);
            });

            if (showNotify) {
                showToast(`Đã tìm thấy ${currentProfiles.length} Profile Google Chrome!`, 'success');
            }
        }
    } catch (err) {
        socialProfileSelect.innerHTML = '<option value="Default">Lỗi quét Profile Chrome</option>';
        appendLog(`[Social Publisher] Lỗi nạp profile: ${err.message}`, 'error');
    }
}

/**
 * Gán video cần đăng
 */
export function setSocialVideo(path, name = '', sizeBytes = 0) {
    if (!path) return;
    selectedVideoPath = path;

    if (socialVideoPathInput) {
        socialVideoPathInput.value = path;
    }

    const fileName = name || path.split(/[\/\\]/).pop();
    let sizeStr = '';
    if (sizeBytes > 0) {
        const mb = (sizeBytes / (1024 * 1024)).toFixed(1);
        sizeStr = ` • ${mb} MB`;
    }

    if (socialVideoInfoCard) {
        socialVideoInfoCard.style.display = 'flex';
        socialVideoInfoCard.innerHTML = `
            <div style="font-size: 20px;">🎬</div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 700; font-size: 13px; color: #38bdf8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(fileName)}</div>
                <div style="font-size: 11px; color: #94a3b8; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(path)}${sizeStr}</div>
            </div>
            <button type="button" class="btn secondary small" id="btnRemoveSocialVideo" title="Gỡ video này" style="padding: 4px 8px; font-size: 11px;">✕</button>
        `;

        const btnRemove = document.getElementById('btnRemoveSocialVideo');
        if (btnRemove) {
            btnRemove.addEventListener('click', () => {
                selectedVideoPath = '';
                if (socialVideoPathInput) socialVideoPathInput.value = '';
                socialVideoInfoCard.style.display = 'none';
                updatePreview();
            });
        }
    }

    // Tự động gợi ý tiêu đề từ tên file video nếu chưa nhập
    if (socialTitleInput && !socialTitleInput.value.trim()) {
        const cleanTitle = fileName.replace(/\.[^/.]+$/, '').replace(/[_\-+]/g, ' ');
        socialTitleInput.value = cleanTitle;
    }

    updatePreview();
}

/**
 * Tự động lấy video vừa xuất gần nhất từ hệ thống NovaCut
 */
export async function useLatestExportedVideo() {
    // 1. Thử lấy từ biến toàn cục
    if (window.lastExportedVideo && window.lastExportedVideo.path) {
        setSocialVideo(window.lastExportedVideo.path, window.lastExportedVideo.name || '', window.lastExportedVideo.size || 0);
        showToast('Đã nạp video vừa xuất gần nhất!', 'success');
        return;
    }

    // 2. Thử truy vấn từ API lịch sử xuất video
    try {
        const res = await fetch('/api/export/history');
        const data = await res.json();
        if (data.success && Array.isArray(data.items) && data.items.length > 0) {
            const latest = data.items[0];
            if (latest.file_path) {
                setSocialVideo(latest.file_path, latest.file_name || '', latest.file_size || 0);
                showToast(`Đã chọn video: ${latest.file_name || 'Gần nhất'}`, 'success');
                return;
            }
        }
    } catch (e) {
        // bỏ qua
    }

    showToast('Chưa tìm thấy video nào vừa xuất. Vui lòng bấm "Chọn Video" từ máy tính.', 'info');
}

/**
 * Cập nhật số ký tự
 */
function updateCharCounts() {
    const plat = currentPlatforms.find(p => p.id === selectedPlatformId);
    if (!plat) return;

    if (socialTitleInput && socialTitleCount) {
        const tLen = socialTitleInput.value.length;
        const maxT = plat.max_title_len || 100;
        socialTitleCount.textContent = `${tLen} / ${maxT}`;
        socialTitleCount.style.color = tLen > maxT ? '#f87171' : '#94a3b8';
    }

    if (socialDescInput && socialDescCount) {
        const dLen = socialDescInput.value.length;
        const maxD = plat.max_desc_len || 2200;
        socialDescCount.textContent = `${dLen} / ${maxD}`;
        socialDescCount.style.color = dLen > maxD ? '#f87171' : '#94a3b8';
    }
}

/**
 * Cập nhật khung xem trước bài đăng (Social Live Preview)
 */
function updatePreview() {
    if (!socialPreviewContainer) return;

    const plat = currentPlatforms.find(p => p.id === selectedPlatformId) || {
        name: 'Mạng Xã Hội',
        has_separate_title: true
    };

    const title = socialTitleInput ? socialTitleInput.value.trim() : '';
    const desc = socialDescInput ? socialDescInput.value.trim() : '';
    const tags = socialHashtagsInput ? socialHashtagsInput.value.trim() : '';
    const privacy = socialPrivacySelect ? socialPrivacySelect.value : 'public';
    const profileOpt = socialProfileSelect && socialProfileSelect.selectedOptions[0] ? socialProfileSelect.selectedOptions[0].textContent : 'Default';

    const videoName = selectedVideoPath ? selectedVideoPath.split(/[\/\\]/).pop() : 'Chưa chọn video';

    // Tạo HTML xem trước trực quan
    socialPreviewContainer.innerHTML = `
        <div class="social-preview-card ${selectedPlatformId}">
            <div class="preview-header">
                <div class="preview-badge-plat">${getPlatformIconSvg(selectedPlatformId)} <span>${escapeHtml(plat.name)}</span></div>
                <div class="preview-profile-tag">${escapeHtml(profileOpt)}</div>
            </div>

            <div class="preview-video-box">
                <div class="preview-video-mock">
                    <span class="preview-play-icon">▶</span>
                    <span class="preview-video-filename">${escapeHtml(videoName)}</span>
                </div>
            </div>

            <div class="preview-content-box">
                ${plat.has_separate_title && title ? `<div class="preview-title">${escapeHtml(title)}</div>` : ''}
                ${desc ? `<div class="preview-desc">${escapeHtml(desc).replace(/\n/g, '<br>')}</div>` : ''}
                ${tags ? `<div class="preview-tags">${escapeHtml(tags)}</div>` : ''}
                ${(!title && !desc && !tags) ? '<div class="preview-placeholder">Chưa nhập nội dung bài đăng...</div>' : ''}
            </div>

            <div class="preview-footer">
                <div class="preview-privacy-badge">🔒 Quyền riêng tư: <b>${escapeHtml(privacy.toUpperCase())}</b></div>
                <div class="preview-status-indicator">● Sẵn sàng mở Chrome</div>
            </div>
        </div>
    `;
}

/**
 * Xử lý Bước Xem Lại & Mở Chrome
 */
async function handleReviewAndOpenChrome() {
    // 1. Kiểm tra phân quyền bản quyền phía Frontend (Rule bắt buộc)
    if (typeof window.checkFeaturePermission === 'function') {
        const allowed = await window.checkFeaturePermission('can_access_social_publish', 'Đăng video lên mạng xã hội');
        if (!allowed) return;
    }

    // 2. Xác thực dữ liệu
    const title = socialTitleInput ? socialTitleInput.value.trim() : '';
    const desc = socialDescInput ? socialDescInput.value.trim() : '';
    const tags = socialHashtagsInput ? socialHashtagsInput.value.trim() : '';
    const privacy = socialPrivacySelect ? socialPrivacySelect.value : 'public';

    if (!selectedVideoPath) {
        showToast('Vui lòng chọn video trước khi đăng!', 'warning');
        return;
    }

    // 3. Chuẩn bị nội dung với Backend
    try {
        btnSocialReviewAndOpen.disabled = true;
        btnSocialReviewAndOpen.innerHTML = '<span>⏳ Đang chuẩn bị & khởi chạy...</span>';

        const prepRes = await fetch('/api/social/prepare', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform_id: selectedPlatformId,
                video_path: selectedVideoPath,
                title: title,
                description: desc,
                caption: desc,
                hashtags: tags,
                privacy: privacy
            })
        });

        const prepData = await prepRes.json();
        if (!prepData.success) {
            showToast(prepData.error || 'Lỗi chuẩn bị nội dung', 'error');
            btnSocialReviewAndOpen.disabled = false;
            btnSocialReviewAndOpen.innerHTML = '<span>🚀 Xem Lại & Mở Chrome Đăng Video</span>';
            return;
        }

        // Cảnh báo độ dài nếu có
        if (prepData.prepared && prepData.prepared.warnings && prepData.prepared.warnings.length > 0) {
            showToast(prepData.prepared.warnings.join(' '), 'warning');
        }

        // 4. Kích hoạt mở Chrome với Profile đã chọn
        const openRes = await fetch('/api/social/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform_id: selectedPlatformId,
                profile_id: selectedProfileId,
                video_path: selectedVideoPath,
                title: prepData.prepared.title,
                caption: prepData.prepared.combined_text,
                privacy: privacy,
                copy_video_path: true
            })
        });

        const openData = await openRes.json();

        if (openData.success) {
            showToast(`🚀 Đã mở Google Chrome (${selectedProfileId})! Đường dẫn video đã được tự động lưu vào bộ nhớ tạm (Ctrl+V để chọn file).`, 'success');
            appendLog(`[Social Publisher] Đã mở ${openData.platform_name} bằng Chrome Profile: ${selectedProfileId}`, 'success');

            // Cập nhật lại bảng lịch sử
            loadSocialHistory();
        } else {
            showToast(openData.error || 'Không thể mở trình duyệt Chrome', 'error');
            appendLog(`[Social Publisher] Lỗi: ${openData.error}`, 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối máy chủ: ' + err.message, 'error');
    } finally {
        btnSocialReviewAndOpen.disabled = false;
        btnSocialReviewAndOpen.innerHTML = '<span>🚀 Xem Lại & Mở Chrome Đăng Video</span>';
    }
}

/**
 * Nạp lịch sử thao tác đăng video
 */
export async function loadSocialHistory() {
    if (!socialHistoryTableBody) return;

    try {
        const res = await fetch('/api/social/history');
        const data = await res.json();

        if (data.success && Array.isArray(data.history)) {
            if (socialHistoryBadge) {
                socialHistoryBadge.textContent = `${data.history.length} Lượt`;
            }

            if (data.history.length === 0) {
                socialHistoryTableBody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 24px; color: #64748b;">
                            Chưa có lịch sử đăng video nào. Chọn video và bấm "Mở Chrome Đăng Video" để bắt đầu!
                        </td>
                    </tr>
                `;
                return;
            }

            socialHistoryTableBody.innerHTML = '';
            data.history.forEach(item => {
                const tr = document.createElement('tr');
                const isOk = item.status === 'OPENED';

                tr.innerHTML = `
                    <td style="font-family: monospace; font-size: 11.5px; color: #94a3b8;">${escapeHtml(item.time_str || '')}</td>
                    <td>
                        <span class="social-hist-badge ${item.platform_id}">
                            ${escapeHtml(item.platform_name || item.platform_id)}
                        </span>
                    </td>
                    <td style="font-weight: 600; color: #e2e8f0; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.title)}">
                        ${escapeHtml(item.title || 'Video')}
                    </td>
                    <td style="font-size: 11.5px; color: #38bdf8; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.video_path)}">
                        ${escapeHtml(item.video_name || item.video_path)}
                    </td>
                    <td><span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(56, 189, 248, 0.1); color: #38bdf8;">${escapeHtml(item.profile_id)}</span></td>
                    <td>
                        <span class="status-indicator-badge ${isOk ? 'success' : 'error'}">
                            ${isOk ? '✓ Đã mở' : '✕ Thất bại'}
                        </span>
                    </td>
                `;

                socialHistoryTableBody.appendChild(tr);
            });
        }
    } catch (err) {
        appendLog(`[Social Publisher] Lỗi nạp lịch sử: ${err.message}`, 'error');
    }
}

/**
 * Xóa toàn bộ lịch sử thao tác
 */
async function clearSocialHistory() {
    try {
        const res = await fetch('/api/social/history/clear', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Đã xóa sạch lịch sử đăng video!', 'info');
            loadSocialHistory();
        }
    } catch (err) {
        showToast('Lỗi xóa lịch sử: ' + err.message, 'error');
    }
}

/**
 * Tiện ích sao chép văn bản vào Clipboard
 */
function copyToClipboard(text, successMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showToast(successMsg, 'success');
        }).catch(() => {
            fallbackCopy(text, successMsg);
        });
    } else {
        fallbackCopy(text, successMsg);
    }
}

function fallbackCopy(text, successMsg) {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    try {
        document.execCommand('copy');
        showToast(successMsg, 'success');
    } catch (e) {
        showToast('Không thể sao chép văn bản.', 'error');
    }
    document.body.removeChild(el);
}
