/**
 * Video Studio Suite - CapCut-Style Interactive Video Player Canvas & Studio Toolbar
 * Hệ thống Preview Canvas chuẩn CapCut Desktop:
 * 1. Sân khấu Stage (videoContainer): Cố định, mượt mà, tông rạp phim đen tối đẳng cấp.
 * 2. Khung Canvas (capcut-canvas-frame): Nằm chính giữa, tự động biến đổi 9:16 / 16:9 / 1:1 / 4:3 / 21:9 có viền sáng sắc nét.
 * 3. Video & Overlays: Tự động bám khít 100% bên trong khung canvas, hỗ trợ Fit / Cover / Stretch, Safe Zone TikTok và Lưới 3x3.
 * 4. Thanh công cụ Docked Toolbar cố định 100% trên thanh timeline.
 */

import { showToast } from '../utils.js';

export class VideoStudioSuite {
    constructor(options) {
        this.type = options.type || 'editor'; // 'editor' | 'review'
        this.container = typeof options.container === 'string' ? document.querySelector(options.container) : options.container;
        this.canvasFrame = this.container ? (this.container.querySelector('.capcut-canvas-frame') || this.container) : null;
        this.video = typeof options.video === 'string' ? document.querySelector(options.video) : options.video;
        this.zoomWrapper = typeof options.zoomWrapper === 'string' ? document.querySelector(options.zoomWrapper) : options.zoomWrapper;
        this.playerControls = typeof options.playerControls === 'string' ? document.querySelector(options.playerControls) : options.playerControls;
        this.onConfigChange = options.onConfigChange || null;

        // State
        this.state = {
            aspectRatio: 'original', // 'original' | '9:16' | '16:9' | '1:1' | '4:3' | '21:9'
            fitMode: 'contain',      // 'contain' | 'cover' | 'fill'
            flipH: false,
            flipV: false,
            rotation: 0,             // 0 | 90 | 180 | 270
            safeZone: false,
            grid3x3: false,
            playbackRate: 1.0,
            zoom: 1.0,
            panX: 0,
            panY: 0
        };

        this.aspectRatios = [
            { id: 'original', label: '🔘 Gốc', desc: 'Tỷ lệ video gốc', ratio: null },
            { id: '9:16', label: '📱 9:16', desc: 'Dọc TikTok / Shorts / Reels', ratio: 9 / 16 },
            { id: '16:9', label: '🖥️ 16:9', desc: 'Ngang YouTube / Phim', ratio: 16 / 9 },
            { id: '1:1', label: '⬛ 1:1', desc: 'Vuông Instagram / Feed', ratio: 1 / 1 },
            { id: '4:3', label: '📺 4:3', desc: 'Cổ điển / TV Box', ratio: 4 / 3 },
            { id: '21:9', label: '🎬 21:9', desc: 'Điện ảnh Ultrawide', ratio: 21 / 9 },
        ];

        this.fitModes = [
            { id: 'contain', label: 'Fit', title: 'Vừa vặn (Giữ tỷ lệ gốc, hiển thị viền đen)' },
            { id: 'cover', label: 'Cover', title: 'Cắt tràn viền (Lấp đầy khung canvas CapCut, cắt mép thừa)' },
            { id: 'fill', label: 'Stretch', title: 'Kéo dãn toàn khung (Lấp đầy 100% canvas tỷ lệ đã chọn)' }
        ];

        this.speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

        if (this.container && this.video) {
            this.init();
        }
    }

    init() {
        this.canvasFrame = this.container ? (this.container.querySelector('.capcut-canvas-frame') || this.container) : null;
        this.renderOverlays();
        this.renderTransformBox();
        this.renderToolbar();
        this.enhancePlayerControls();
        this.bindEvents();
        this.bindTransformEvents();
        this.applyTransforms();
        this.applyAspectRatio();
    }

    renderOverlays() {
        if (!this.container) return;
        const targetParent = this.canvasFrame || this.zoomWrapper || this.container;

        // 1. Safe Zone Overlay for TikTok / Reels UI
        let safeZone = targetParent.querySelector('.studio-safe-zone-overlay');
        if (!safeZone) {
            safeZone = document.createElement('div');
            safeZone.className = 'studio-safe-zone-overlay';
            safeZone.style.display = 'none';
            safeZone.innerHTML = `
                <div class="safe-zone-box">
                    <div class="safe-zone-inner-guide">
                        <span class="safe-zone-label">VÙNG AN TOÀN NỘI DUNG (SAFE ZONE)</span>
                    </div>
                    <!-- Right Action Bar Mockup (Like, Comment, Share) -->
                    <div class="safe-zone-rail-right">
                        <div class="rail-item"><div class="rail-icon">👤</div><span>Avatar</span></div>
                        <div class="rail-item"><div class="rail-icon">❤️</div><span>Thích</span></div>
                        <div class="rail-item"><div class="rail-icon">💬</div><span>Bình luận</span></div>
                        <div class="rail-item"><div class="rail-icon">⭐</div><span>Lưu</span></div>
                        <div class="rail-item"><div class="rail-icon">↗️</div><span>Chia sẻ</span></div>
                        <div class="rail-item"><div class="rail-disc">🎵</div></div>
                    </div>
                    <!-- Bottom Caption Area -->
                    <div class="safe-zone-bottom-bar">
                        <div class="safe-caption-mock">@TênKênh • Tiêu đề video & mô tả hashtag...</div>
                        <div class="safe-sound-mock">🎵 Âm thanh gốc - Nhạc nền xu hướng</div>
                    </div>
                    <!-- Top Navigation Area -->
                    <div class="safe-zone-top-bar">
                        <span>Đang theo dõi | Dành cho bạn 🔍</span>
                    </div>
                </div>
            `;
            targetParent.appendChild(safeZone);
        }
        this.safeZoneEl = safeZone;

        // 2. Rule of Thirds 3x3 Grid Overlay
        let grid = targetParent.querySelector('.studio-grid-overlay');
        if (!grid) {
            grid = document.createElement('div');
            grid.className = 'studio-grid-overlay';
            grid.style.display = 'none';
            grid.innerHTML = `
                <div class="grid-line grid-v1"></div>
                <div class="grid-line grid-v2"></div>
                <div class="grid-line grid-h1"></div>
                <div class="grid-line grid-h2"></div>
                <div class="grid-point point-tl"></div>
                <div class="grid-point point-tr"></div>
                <div class="grid-point point-bl"></div>
                <div class="grid-point point-br"></div>
            `;
            targetParent.appendChild(grid);
        }
        this.gridEl = grid;
    }

    renderToolbar() {
        if (!this.container) return;

        const card = this.container.closest('.video-player-card') || this.container.parentElement;

        // Xóa toolbar cũ nếu có
        let oldToolbar = card ? card.querySelector(`.studio-docked-toolbar[data-player="${this.type}"]`) : null;
        if (oldToolbar) oldToolbar.remove();
        let oldFloating = this.container.querySelector('.studio-floating-toolbar');
        if (oldFloating) oldFloating.remove();

        const toolbar = document.createElement('div');
        toolbar.className = 'studio-docked-toolbar';
        toolbar.dataset.player = this.type;
        toolbar.innerHTML = `
            <!-- Left: Aspect Ratio Dropdown -->
            <div class="studio-tool-group">
                <div class="studio-dropdown-wrap" id="${this.type}_aspectDropdownWrap">
                    <button type="button" class="studio-btn studio-aspect-btn" id="${this.type}_btnAspectSelect" title="Tỷ lệ khung hình Canvas (Aspect Ratio - CapCut Style)">
                        <span class="aspect-current-label">🔘 Gốc</span>
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
                    </button>
                    <div class="studio-dropdown-menu" id="${this.type}_aspectDropdownMenu" style="display: none;">
                        ${this.aspectRatios.map(a => `
                            <div class="studio-dropdown-item ${this.state.aspectRatio === a.id ? 'active' : ''}" data-aspect="${a.id}">
                                <span>${a.label}</span>
                                <span class="sub-desc">${a.desc}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>

            <!-- Center: Fit / Stretch Mode Segmented Pills -->
            <div class="studio-tool-group studio-fit-group" title="Chế độ hiển thị CapCut: Fit (vừa vặn), Cover (cắt tràn viền), Stretch (kéo dãn)">
                ${this.fitModes.map(m => `
                    <button type="button" class="studio-fit-btn ${this.state.fitMode === m.id ? 'active' : ''}" data-fit="${m.id}" title="${m.title}">
                        ${m.label}
                    </button>
                `).join('')}
                <button type="button" class="studio-fit-btn" id="${this.type}_btnResetZoom" title="🎯 Khôi phục vị trí & thu phóng về chuẩn 100% Fit (Phím tắt: R / DblClick)">
                    🎯 100%
                </button>
            </div>

            <!-- Right: Visual Quick Toggles -->
            <div class="studio-tool-group studio-action-group">
                <button type="button" class="studio-btn icon-btn ${this.state.flipH ? 'active' : ''}" id="${this.type}_btnFlipH" title="Lật gương ngang (Flip Horizontal - Chống bản quyền)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
                </button>
                <button type="button" class="studio-btn icon-btn" id="${this.type}_btnRotate" title="Xoay 90 độ (Rotate)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                </button>
                <button type="button" class="studio-btn icon-btn ${this.state.safeZone ? 'active' : ''}" id="${this.type}_btnSafeZone" title="Bật/Tắt Lưới vùng an toàn TikTok/Reels Safe Zone">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </button>
                <button type="button" class="studio-btn icon-btn ${this.state.grid3x3 ? 'active' : ''}" id="${this.type}_btnGrid" title="Bật/Tắt Lưới 3x3 Tỷ lệ vàng (Rule of Thirds)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/></svg>
                </button>
                <button type="button" class="studio-btn icon-btn" id="${this.type}_btnSnapshot" title="📸 Chụp ảnh khung hình hiện tại (Snapshot Thumbnail)">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                </button>
            </div>
        `;

        // Đặt cố định ngay trên player-controls (trên thanh điều chỉnh thời gian)
        if (this.playerControls && card) {
            card.insertBefore(toolbar, this.playerControls);
        } else if (card) {
            card.appendChild(toolbar);
        } else {
            this.container.after(toolbar);
        }
        this.toolbarEl = toolbar;
    }

    enhancePlayerControls() {
        if (!this.playerControls) return;

        // Bổ sung nút Nhảy Frame & Bộ điều tốc vào thanh điều khiển dưới
        let extraTools = this.playerControls.querySelector('.studio-extra-controls');
        if (extraTools) extraTools.remove();

        extraTools = document.createElement('div');
        extraTools.className = 'studio-extra-controls';
        extraTools.style.display = 'inline-flex';
        extraTools.style.alignItems = 'center';
        extraTools.style.gap = '4px';

        extraTools.innerHTML = `
            <button type="button" class="btn secondary small studio-frame-btn" id="${this.type}_btnStepBack" style="padding: 4px 7px; font-size: 11px; font-weight: 600;" title="Lùi chính xác 1 khung hình (1 Frame Back - Phím ◀)">
                ◀ 1F
            </button>
            <button type="button" class="btn secondary small studio-frame-btn" id="${this.type}_btnStepForward" style="padding: 4px 7px; font-size: 11px; font-weight: 600;" title="Tiến chính xác 1 khung hình (1 Frame Forward - Phím ▶)">
                1F ▶
            </button>
            <div class="studio-speed-wrap" style="position: relative;">
                <button type="button" class="btn secondary small studio-speed-btn" id="${this.type}_btnSpeed" style="padding: 4px 8px; font-size: 11px; font-weight: 700; color: #38bdf8; min-width: 38px;" title="Tốc độ phát">
                    1.0x
                </button>
                <div class="studio-dropdown-menu speed-menu" id="${this.type}_speedMenu" style="display: none; bottom: calc(100% + 6px); top: auto; right: 0;">
                    ${this.speeds.map(s => `
                        <div class="studio-dropdown-item speed-item ${this.state.playbackRate === s ? 'active' : ''}" data-speed="${s}">
                            <span>${s}x ${s === 1.0 ? '(Chuẩn)' : ''}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Chèn trước Toggle Group hoặc nút Fullscreen
        const toggleGroup = this.playerControls.querySelector('.toggle-group') || this.playerControls.querySelector('.volume-control');
        if (toggleGroup) {
            this.playerControls.insertBefore(extraTools, toggleGroup);
        } else {
            this.playerControls.appendChild(extraTools);
        }
    }

    bindEvents() {
        if (!this.toolbarEl) return;

        // Aspect Ratio Dropdown toggle
        const btnAspect = this.toolbarEl.querySelector(`#${this.type}_btnAspectSelect`);
        const menuAspect = this.toolbarEl.querySelector(`#${this.type}_aspectDropdownMenu`);
        if (btnAspect && menuAspect) {
            btnAspect.addEventListener('click', (e) => {
                e.stopPropagation();
                menuAspect.style.display = (menuAspect.style.display === 'none' || !menuAspect.style.display) ? 'block' : 'none';
            });

            menuAspect.querySelectorAll('.studio-dropdown-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const aspect = item.dataset.aspect;
                    this.setAspectRatio(aspect);
                    menuAspect.style.display = 'none';
                });
            });
        }

        // Fit mode buttons
        this.toolbarEl.querySelectorAll('.studio-fit-btn[data-fit]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const fit = btn.dataset.fit;
                this.setFitMode(fit);
            });
        });

        // Quick Reset Zoom button
        const btnResetZoom = this.toolbarEl.querySelector(`#${this.type}_btnResetZoom`);
        if (btnResetZoom) {
            btnResetZoom.addEventListener('click', (e) => {
                e.stopPropagation();
                this.resetTransform();
            });
        }

        // Visual action buttons
        const btnFlipH = this.toolbarEl.querySelector(`#${this.type}_btnFlipH`);
        if (btnFlipH) {
            btnFlipH.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleFlipH();
            });
        }

        const btnRotate = this.toolbarEl.querySelector(`#${this.type}_btnRotate`);
        if (btnRotate) {
            btnRotate.addEventListener('click', (e) => {
                e.stopPropagation();
                this.rotate();
            });
        }

        const btnSafeZone = this.toolbarEl.querySelector(`#${this.type}_btnSafeZone`);
        if (btnSafeZone) {
            btnSafeZone.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleSafeZone();
            });
        }

        const btnGrid = this.toolbarEl.querySelector(`#${this.type}_btnGrid`);
        if (btnGrid) {
            btnGrid.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleGrid3x3();
            });
        }

        const btnSnapshot = this.toolbarEl.querySelector(`#${this.type}_btnSnapshot`);
        if (btnSnapshot) {
            btnSnapshot.addEventListener('click', (e) => {
                e.stopPropagation();
                this.takeSnapshot();
            });
        }

        // Player controls extra buttons
        if (this.playerControls) {
            const btnStepBack = this.playerControls.querySelector(`#${this.type}_btnStepBack`);
            if (btnStepBack) {
                btnStepBack.addEventListener('click', () => this.stepFrame(-1));
            }

            const btnStepForward = this.playerControls.querySelector(`#${this.type}_btnStepForward`);
            if (btnStepForward) {
                btnStepForward.addEventListener('click', () => this.stepFrame(1));
            }

            const btnSpeed = this.playerControls.querySelector(`#${this.type}_btnSpeed`);
            const menuSpeed = this.playerControls.querySelector(`#${this.type}_speedMenu`);
            if (btnSpeed && menuSpeed) {
                btnSpeed.addEventListener('click', (e) => {
                    e.stopPropagation();
                    menuSpeed.style.display = (menuSpeed.style.display === 'none' || !menuSpeed.style.display) ? 'block' : 'none';
                });

                menuSpeed.querySelectorAll('.speed-item').forEach(item => {
                    item.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const spd = parseFloat(item.dataset.speed);
                        this.setPlaybackRate(spd);
                        menuSpeed.style.display = 'none';
                    });
                });
            }
        }

        // Đóng dropdown khi click ra ngoài
        document.addEventListener('click', () => {
            if (menuAspect) menuAspect.style.display = 'none';
            const menuSpeed = this.playerControls ? this.playerControls.querySelector(`#${this.type}_speedMenu`) : null;
            if (menuSpeed) menuSpeed.style.display = 'none';
        });

        // Lắng nghe video metadata loaded để tự cập nhật tỷ lệ gốc
        if (this.video) {
            this.video.addEventListener('loadedmetadata', () => {
                if (this.state.aspectRatio === 'original') {
                    this.applyAspectRatio();
                }
            });
        }

        // Phím tắt toàn cầu (Hotkeys)
        this.setupHotkeys();
    }

    setupHotkeys() {
        document.addEventListener('keydown', (e) => {
            // Không nhận phím tắt khi người dùng đang nhập văn bản trong input/textarea
            const tag = (e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;

            // Kiểm tra tab hiện tại có đang hiển thị player này không
            const isEditorTab = document.getElementById('viewEditor')?.classList.contains('active');
            const isReviewTab = document.getElementById('viewReview')?.classList.contains('active');

            if (this.type === 'editor' && !isEditorTab) return;
            if (this.type === 'review' && !isReviewTab) return;

            if (!this.video || !this.video.src || this.video.style.display === 'none') return;

            switch (e.code) {
                case 'Space':
                    e.preventDefault();
                    if (this.video.paused) this.video.play();
                    else this.video.pause();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    if (e.shiftKey) {
                        this.video.currentTime = Math.max(0, this.video.currentTime - 5);
                    } else {
                        this.stepFrame(-1);
                    }
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    if (e.shiftKey) {
                        this.video.currentTime = Math.min(this.video.duration || 0, this.video.currentTime + 5);
                    } else {
                        this.stepFrame(1);
                    }
                    break;
                case 'KeyJ':
                    e.preventDefault();
                    this.video.currentTime = Math.max(0, this.video.currentTime - 5);
                    break;
                case 'KeyK':
                    e.preventDefault();
                    if (this.video.paused) this.video.play();
                    else this.video.pause();
                    break;
                case 'KeyL':
                    e.preventDefault();
                    this.video.currentTime = Math.min(this.video.duration || 0, this.video.currentTime + 5);
                    break;
                case 'KeyF':
                    e.preventDefault();
                    this.toggleFullscreen();
                    break;
                case 'KeyM':
                    e.preventDefault();
                    this.video.muted = !this.video.muted;
                    showToast(this.video.muted ? '🔇 Đã tắt tiếng' : '🔊 Đã mở tiếng', 'info', 1500);
                    break;
                case 'KeyS':
                    if (!e.ctrlKey && !e.metaKey) {
                        e.preventDefault();
                        this.takeSnapshot();
                    }
                    break;
            }
        });
    }

    setAspectRatio(aspectId, notifyToast = true) {
        this.state.aspectRatio = aspectId;
        const item = this.aspectRatios.find(a => a.id === aspectId) || this.aspectRatios[0];
        
        // Update label in toolbar
        const btnAspect = this.toolbarEl ? this.toolbarEl.querySelector(`#${this.type}_btnAspectSelect .aspect-current-label`) : null;
        if (btnAspect) btnAspect.textContent = item.label;

        // Update active class in menu
        const menuAspect = this.toolbarEl ? this.toolbarEl.querySelector(`#${this.type}_aspectDropdownMenu`) : null;
        if (menuAspect) {
            menuAspect.querySelectorAll('.studio-dropdown-item').forEach(it => {
                it.classList.toggle('active', it.dataset.aspect === aspectId);
            });
        }

        this.applyAspectRatio();
        this.notifyChange();
        if (notifyToast) {
            showToast(`Khung Canvas: ${item.label}`, 'info', 1800);
        }
    }

    applyAspectRatio() {
        if (!this.container) return;
        this.canvasFrame = this.container.querySelector('.capcut-canvas-frame') || this.container;

        const isVertical = this.state.aspectRatio === '9:16' || (this.video && this.video.videoHeight > this.video.videoWidth && this.state.aspectRatio === 'original');

        // Áp dụng định dạng Khung Canvas CapCut (CapCut Canvas Frame)
        if (this.canvasFrame && this.canvasFrame !== this.container) {
            switch (this.state.aspectRatio) {
                case '9:16':
                    this.canvasFrame.style.height = 'calc(100% - 24px)';
                    this.canvasFrame.style.aspectRatio = '9 / 16';
                    this.canvasFrame.style.width = 'auto';
                    this.canvasFrame.style.maxWidth = '100%';
                    this.canvasFrame.style.maxHeight = '';
                    this.canvasFrame.style.border = '1px solid rgba(56, 189, 248, 0.7)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9), 0 0 12px rgba(56, 189, 248, 0.25)';
                    break;
                case '16:9':
                    this.canvasFrame.style.width = 'calc(100% - 32px)';
                    this.canvasFrame.style.aspectRatio = '16 / 9';
                    this.canvasFrame.style.height = 'auto';
                    this.canvasFrame.style.maxWidth = '';
                    this.canvasFrame.style.maxHeight = 'calc(100% - 24px)';
                    this.canvasFrame.style.border = '1px solid rgba(255, 255, 255, 0.2)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9)';
                    break;
                case '1:1':
                    this.canvasFrame.style.height = 'calc(100% - 24px)';
                    this.canvasFrame.style.aspectRatio = '1 / 1';
                    this.canvasFrame.style.width = 'auto';
                    this.canvasFrame.style.maxWidth = '100%';
                    this.canvasFrame.style.maxHeight = '';
                    this.canvasFrame.style.border = '1px solid rgba(255, 255, 255, 0.2)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9)';
                    break;
                case '4:3':
                    this.canvasFrame.style.height = 'calc(100% - 24px)';
                    this.canvasFrame.style.aspectRatio = '4 / 3';
                    this.canvasFrame.style.width = 'auto';
                    this.canvasFrame.style.maxWidth = '100%';
                    this.canvasFrame.style.maxHeight = 'calc(100% - 24px)';
                    this.canvasFrame.style.border = '1px solid rgba(255, 255, 255, 0.2)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9)';
                    break;
                case '21:9':
                    this.canvasFrame.style.width = 'calc(100% - 32px)';
                    this.canvasFrame.style.aspectRatio = '21 / 9';
                    this.canvasFrame.style.height = 'auto';
                    this.canvasFrame.style.maxWidth = '';
                    this.canvasFrame.style.maxHeight = 'calc(100% - 24px)';
                    this.canvasFrame.style.border = '1px solid rgba(255, 255, 255, 0.2)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9)';
                    break;
                case 'original':
                default:
                    if (this.video && this.video.videoWidth && this.video.videoHeight) {
                        const vw = this.video.videoWidth;
                        const vh = this.video.videoHeight;
                        this.canvasFrame.style.aspectRatio = `${vw} / ${vh}`;
                        if (vh > vw) {
                            this.canvasFrame.style.height = 'calc(100% - 24px)';
                            this.canvasFrame.style.width = 'auto';
                            this.canvasFrame.style.maxHeight = '';
                            this.canvasFrame.style.maxWidth = '100%';
                        } else {
                            this.canvasFrame.style.width = 'calc(100% - 32px)';
                            this.canvasFrame.style.height = 'auto';
                            this.canvasFrame.style.maxWidth = '';
                            this.canvasFrame.style.maxHeight = 'calc(100% - 24px)';
                        }
                    } else {
                        this.canvasFrame.style.width = 'calc(100% - 32px)';
                        this.canvasFrame.style.aspectRatio = '16 / 9';
                        this.canvasFrame.style.height = 'auto';
                        this.canvasFrame.style.maxHeight = 'calc(100% - 24px)';
                    }
                    this.canvasFrame.style.border = '1px solid rgba(255, 255, 255, 0.2)';
                    this.canvasFrame.style.boxShadow = '0 0 30px rgba(0, 0, 0, 0.9)';
                    break;
            }
        }

        // Inner Zoom Wrapper & Video styling
        if (this.zoomWrapper) {
            this.zoomWrapper.style.width = '100%';
            this.zoomWrapper.style.height = '100%';
            this.zoomWrapper.style.aspectRatio = '';
            this.zoomWrapper.style.border = 'none';
            this.zoomWrapper.style.borderRadius = '0';
            this.zoomWrapper.style.boxShadow = 'none';
        }

        // Cập nhật object-fit theo fitMode (CapCut Fit / Cover / Stretch)
        if (this.video) {
            this.video.style.width = '100%';
            this.video.style.height = '100%';
            this.video.style.objectFit = this.state.fitMode || 'contain';
        }

        // Đồng bộ Safe Zone hiển thị phù hợp
        if (this.safeZoneEl) {
            this.safeZoneEl.classList.toggle('is-vertical', isVertical);
        }

        // Cập nhật badge Review nếu là review player
        if (this.type === 'review') {
            const rBadge = document.getElementById('reviewPlayerStatusBadge');
            if (rBadge && this.video && this.video.videoWidth) {
                if (this.state.aspectRatio === '9:16') {
                    rBadge.textContent = `Dọc 9:16 (${this.video.videoWidth}x${this.video.videoHeight})`;
                    rBadge.style.color = '#38bdf8';
                    rBadge.style.borderColor = 'rgba(56, 189, 248, 0.4)';
                    rBadge.style.background = 'rgba(56, 189, 248, 0.12)';
                } else if (this.state.aspectRatio === '16:9') {
                    rBadge.textContent = `Ngang 16:9 (${this.video.videoWidth}x${this.video.videoHeight})`;
                    rBadge.style.color = '#94a3b8';
                    rBadge.style.borderColor = 'rgba(148, 163, 184, 0.25)';
                    rBadge.style.background = 'rgba(148, 163, 184, 0.12)';
                } else {
                    rBadge.textContent = `${this.state.aspectRatio} (${this.video.videoWidth}x${this.video.videoHeight})`;
                }
            }
        }
    }

    setFitMode(fitModeId) {
        this.state.fitMode = fitModeId;

        // Update fit buttons active state in toolbar
        if (this.toolbarEl) {
            this.toolbarEl.querySelectorAll('.studio-fit-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.fit === fitModeId);
            });
        }

        if (this.video) {
            this.video.style.objectFit = fitModeId; // 'contain' | 'cover' | 'fill'
        }

        const modeObj = this.fitModes.find(m => m.id === fitModeId);
        this.notifyChange();
        showToast(`Chế độ khung hình: ${modeObj ? modeObj.title : fitModeId}`, 'info', 1800);
    }

    toggleFlipH() {
        this.state.flipH = !this.state.flipH;
        if (this.toolbarEl) {
            const btn = this.toolbarEl.querySelector(`#${this.type}_btnFlipH`);
            if (btn) btn.classList.toggle('active', this.state.flipH);
        }

        this.applyTransforms();
        this.notifyChange();
        showToast(this.state.flipH ? '🔄 Đã bật Lật gương ngang (Flip H)' : 'Đã tắt Lật gương ngang', 'info', 1800);
    }

    toggleFlipV() {
        this.state.flipV = !this.state.flipV;
        this.applyTransforms();
        this.notifyChange();
    }

    rotate() {
        this.state.rotation = (this.state.rotation + 90) % 360;
        this.applyTransforms();
        this.notifyChange();
        showToast(`↪️ Đã xoay góc: ${this.state.rotation}°`, 'info', 1800);
    }

    toggleSafeZone() {
        this.state.safeZone = !this.state.safeZone;
        if (this.toolbarEl) {
            const btn = this.toolbarEl.querySelector(`#${this.type}_btnSafeZone`);
            if (btn) btn.classList.toggle('active', this.state.safeZone);
        }

        if (this.safeZoneEl) {
            this.safeZoneEl.style.display = this.state.safeZone ? 'block' : 'none';
        }
        showToast(this.state.safeZone ? '🛡️ Đã bật Lưới vùng an toàn TikTok/Reels' : 'Đã tắt Lưới vùng an toàn', 'info', 1800);
    }

    toggleGrid3x3() {
        this.state.grid3x3 = !this.state.grid3x3;
        if (this.toolbarEl) {
            const btn = this.toolbarEl.querySelector(`#${this.type}_btnGrid`);
            if (btn) btn.classList.toggle('active', this.state.grid3x3);
        }

        if (this.gridEl) {
            this.gridEl.style.display = this.state.grid3x3 ? 'block' : 'none';
        }
        showToast(this.state.grid3x3 ? '📐 Đã bật Lưới tỷ lệ vàng 3x3' : 'Đã tắt Lưới 3x3', 'info', 1800);
    }

    setPlaybackRate(speed) {
        this.state.playbackRate = speed;
        if (this.video) {
            this.video.playbackRate = speed;
        }

        const btnSpeed = this.playerControls ? this.playerControls.querySelector(`#${this.type}_btnSpeed`) : null;
        if (btnSpeed) btnSpeed.textContent = `${speed}x`;

        const menuSpeed = this.playerControls ? this.playerControls.querySelector(`#${this.type}_speedMenu`) : null;
        if (menuSpeed) {
            menuSpeed.querySelectorAll('.speed-item').forEach(it => {
                it.classList.toggle('active', parseFloat(it.dataset.speed) === speed);
            });
        }
        showToast(`⏱️ Tốc độ phát: ${speed}x`, 'info', 1500);
    }

    stepFrame(deltaFrames = 1) {
        if (!this.video || !this.video.duration) return;
        if (!this.video.paused) this.video.pause();

        const frameDuration = 1 / 30; // 30fps standard
        const targetTime = Math.max(0, Math.min(this.video.duration, this.video.currentTime + (deltaFrames * frameDuration)));
        this.video.currentTime = targetTime;
    }

    renderTransformBox() {
        if (!this.container) return;
        const targetParent = this.canvasFrame || this.container;

        let box = targetParent.querySelector('.capcut-transform-box');
        if (!box) {
            box = document.createElement('div');
            box.className = 'capcut-transform-box';
            box.id = `${this.type}CapcutTransformBox`;
            box.innerHTML = `
                <div class="capcut-guide-line capcut-guide-v"></div>
                <div class="capcut-guide-line capcut-guide-h"></div>
                <div class="capcut-transform-badge">Zoom: 100% • (0, 0) • 0°</div>
                <div class="capcut-transform-frame">
                    <!-- 4 Corner Handles (Proportional Zoom) -->
                    <div class="capcut-anchor-corner handle-tl" data-anchor="tl" title="Kéo góc để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-corner handle-tr" data-anchor="tr" title="Kéo góc để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-corner handle-bl" data-anchor="bl" title="Kéo góc để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-corner handle-br" data-anchor="br" title="Kéo góc để Phóng to / Thu nhỏ"></div>
                    <!-- 4 Edge Midpoint Handles (Edge Stretch / Zoom) -->
                    <div class="capcut-anchor-edge handle-tc" data-anchor="tc" title="Kéo cạnh trên để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-edge handle-bc" data-anchor="bc" title="Kéo cạnh dưới để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-edge handle-lc" data-anchor="lc" title="Kéo cạnh trái để Phóng to / Thu nhỏ"></div>
                    <div class="capcut-anchor-edge handle-rc" data-anchor="rc" title="Kéo cạnh phải để Phóng to / Thu nhỏ"></div>
                    <!-- Bottom Rotation Handle -->
                    <div class="capcut-anchor-rotate-wrap" title="Kéo để Xoay góc 360°">
                        <div class="capcut-rotate-line"></div>
                        <div class="capcut-anchor-rotate" data-anchor="rot">🔄</div>
                    </div>
                </div>
            `;
            targetParent.appendChild(box);
        }
        this.transformBoxEl = box;
        this.transformFrameEl = box.querySelector('.capcut-transform-frame');
        this.transformBadgeEl = box.querySelector('.capcut-transform-badge');
        this.guideV = box.querySelector('.capcut-guide-v');
        this.guideH = box.querySelector('.capcut-guide-h');
    }

    updateTransformBadge(visible = true) {
        if (!this.transformBadgeEl) return;
        const zoomPct = Math.round((this.state.zoom || 1.0) * 100);
        const panX = Math.round(this.state.panX || 0);
        const panY = Math.round(this.state.panY || 0);
        const rot = Math.round(this.state.rotation || 0);

        this.transformBadgeEl.textContent = `🔍 ${zoomPct}% • (X: ${panX}px, Y: ${panY}px) • 🔄 ${rot}° (Cuộn chuột để Zoom • DblClick để Reset)`;
        this.transformBadgeEl.classList.toggle('visible', visible);
    }

    bindTransformEvents() {
        if (!this.transformBoxEl || !this.container) return;

        const frame = this.transformFrameEl;
        const container = this.container;

        let isInteracting = false;
        let activeAction = null; // 'pan' | 'scale-corner' | 'scale-edge-y' | 'scale-edge-x' | 'rotate'
        let startX = 0, startY = 0;
        let startPanX = 0, startPanY = 0;
        let startZoom = 1.0;
        let startRotation = 0;
        let centerScreenX = 0, centerScreenY = 0;
        let startDist = 1;
        let startDistX = 1;
        let startDistY = 1;
        let initialAngleRad = 0;
        let badgeTimeout = null;

        // Bật / Tắt hiển thị transform box
        const showTransformBox = () => {
            if (this.transformBoxEl) {
                this.transformBoxEl.classList.add('active');
                this.state.isTransformBoxVisible = true;
            }
        };

        const hideTransformBox = () => {
            if (this.transformBoxEl && !isInteracting) {
                this.transformBoxEl.classList.remove('active');
                this.state.isTransformBoxVisible = false;
                if (this.transformBadgeEl) this.transformBadgeEl.classList.remove('visible');
            }
        };

        container.addEventListener('mouseenter', showTransformBox);
        container.addEventListener('click', (e) => {
            if (!e.target.closest('.studio-docked-toolbar') && !e.target.closest('.player-controls')) {
                showTransformBox();
            }
        });

        // Mouse Wheel Zoom (Cuộn chuột để Phóng to / Thu nhỏ tức thời)
        container.addEventListener('wheel', (e) => {
            if (this.state.isTransformBoxVisible || e.ctrlKey || e.altKey) {
                e.preventDefault();
                showTransformBox();
                const factor = e.deltaY < 0 ? 1.08 : 0.92;
                let newZoom = (this.state.zoom || 1.0) * factor;
                newZoom = Math.max(0.15, Math.min(5.0, Math.round(newZoom * 100) / 100));

                this.state.zoom = newZoom;
                this.applyTransforms();
                this.updateTransformBadge(true);
                this.notifyChange();

                if (badgeTimeout) clearTimeout(badgeTimeout);
                badgeTimeout = setTimeout(() => {
                    if (this.transformBadgeEl && !isInteracting) {
                        this.transformBadgeEl.classList.remove('visible');
                    }
                }, 2000);
            }
        }, { passive: false });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideTransformBox();
            } else if (e.key.toLowerCase() === 'r' && (e.ctrlKey || e.metaKey)) {
                // Keep default browser reload
            } else if (e.key.toLowerCase() === 'r' && this.state.isTransformBoxVisible && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                this.resetTransform();
            }
        });

        const getCenterScreenCoords = () => {
            const rect = (this.canvasFrame || container).getBoundingClientRect();
            return {
                x: rect.left + (rect.width / 2) + (this.state.panX || 0),
                y: rect.top + (rect.height / 2) + (this.state.panY || 0)
            };
        };

        // 1. Kéo 4 góc neo tròn trắng (Corner Proportional Scale Dragging)
        const corners = this.transformBoxEl.querySelectorAll('.capcut-anchor-corner');
        corners.forEach(corner => {
            corner.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                e.preventDefault();

                isInteracting = true;
                activeAction = 'scale-corner';
                startX = e.clientX;
                startY = e.clientY;
                startZoom = this.state.zoom || 1.0;

                const center = getCenterScreenCoords();
                centerScreenX = center.x;
                centerScreenY = center.y;
                startDist = Math.hypot(startX - centerScreenX, startY - centerScreenY) || 1;

                this.updateTransformBadge(true);
            });
        });

        // 2. Kéo 4 mốc cạnh trung tâm (Edge Midpoint Scale Dragging)
        const edges = this.transformBoxEl.querySelectorAll('.capcut-anchor-edge');
        edges.forEach(edge => {
            edge.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                e.preventDefault();

                const anchor = edge.dataset.anchor;
                isInteracting = true;
                activeAction = (anchor === 'tc' || anchor === 'bc') ? 'scale-edge-y' : 'scale-edge-x';
                startX = e.clientX;
                startY = e.clientY;
                startZoom = this.state.zoom || 1.0;

                const center = getCenterScreenCoords();
                centerScreenX = center.x;
                centerScreenY = center.y;
                startDistY = Math.abs(startY - centerScreenY) || 1;
                startDistX = Math.abs(startX - centerScreenX) || 1;

                this.updateTransformBadge(true);
            });
        });

        // 3. Kéo neo xoay đáy (Rotate Dragging 360°)
        const rotateAnchor = this.transformBoxEl.querySelector('.capcut-anchor-rotate');
        if (rotateAnchor) {
            rotateAnchor.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                e.preventDefault();

                isInteracting = true;
                activeAction = 'rotate';
                startX = e.clientX;
                startY = e.clientY;
                startRotation = this.state.rotation || 0;

                const center = getCenterScreenCoords();
                centerScreenX = center.x;
                centerScreenY = center.y;
                initialAngleRad = Math.atan2(startY - centerScreenY, startX - centerScreenX);

                this.updateTransformBadge(true);
            });
        }

        // 4. Kéo thân video (Pan / Translate Freely - Tràn ra ngoài khung)
        if (frame) {
            frame.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return;
                if (e.target.closest('.capcut-anchor-corner') || e.target.closest('.capcut-anchor-edge') || e.target.closest('.capcut-anchor-rotate-wrap')) return;
                e.stopPropagation();
                e.preventDefault();

                isInteracting = true;
                activeAction = 'pan';
                startX = e.clientX;
                startY = e.clientY;
                startPanX = this.state.panX || 0;
                startPanY = this.state.panY || 0;

                this.updateTransformBadge(true);
            });

            // Double click reset
            frame.addEventListener('dblclick', (e) => {
                if (e.target.closest('.capcut-anchor-corner') || e.target.closest('.capcut-anchor-edge') || e.target.closest('.capcut-anchor-rotate-wrap')) return;
                e.stopPropagation();
                this.resetTransform();
            });
        }

        // Mousemove & Mouseup toàn cục
        window.addEventListener('mousemove', (e) => {
            if (!isInteracting || !activeAction) return;
            e.preventDefault();

            if (activeAction === 'pan') {
                const dx = e.clientX - startX;
                const dy = e.clientY - startY;
                let newPanX = startPanX + dx;
                let newPanY = startPanY + dy;

                // Snapping to center
                if (Math.abs(newPanX) < 8) {
                    newPanX = 0;
                    if (this.guideV) this.guideV.style.display = 'block';
                } else if (this.guideV) {
                    this.guideV.style.display = 'none';
                }

                if (Math.abs(newPanY) < 8) {
                    newPanY = 0;
                    if (this.guideH) this.guideH.style.display = 'block';
                } else if (this.guideH) {
                    this.guideH.style.display = 'none';
                }

                this.state.panX = newPanX;
                this.state.panY = newPanY;
                this.applyTransforms();
                this.updateTransformBadge(true);
            } else if (activeAction === 'scale-corner') {
                const currentDist = Math.hypot(e.clientX - centerScreenX, e.clientY - centerScreenY);
                let newZoom = startZoom * (currentDist / startDist);
                newZoom = Math.max(0.15, Math.min(5.0, Math.round(newZoom * 100) / 100));

                this.state.zoom = newZoom;
                this.applyTransforms();
                this.updateTransformBadge(true);
            } else if (activeAction === 'scale-edge-y') {
                const currentDistY = Math.abs(e.clientY - centerScreenY);
                let newZoom = startZoom * (currentDistY / startDistY);
                newZoom = Math.max(0.15, Math.min(5.0, Math.round(newZoom * 100) / 100));

                this.state.zoom = newZoom;
                this.applyTransforms();
                this.updateTransformBadge(true);
            } else if (activeAction === 'scale-edge-x') {
                const currentDistX = Math.abs(e.clientX - centerScreenX);
                let newZoom = startZoom * (currentDistX / startDistX);
                newZoom = Math.max(0.15, Math.min(5.0, Math.round(newZoom * 100) / 100));

                this.state.zoom = newZoom;
                this.applyTransforms();
                this.updateTransformBadge(true);
            } else if (activeAction === 'rotate') {
                const currentAngleRad = Math.atan2(e.clientY - centerScreenY, e.clientX - centerScreenX);
                let deltaDeg = (currentAngleRad - initialAngleRad) * (180 / Math.PI);
                let newRot = Math.round((startRotation + deltaDeg) % 360);
                if (newRot < 0) newRot += 360;

                // Snapping at 0, 90, 180, 270 degrees
                if (Math.abs(newRot - 0) < 4 || Math.abs(newRot - 360) < 4) newRot = 0;
                else if (Math.abs(newRot - 90) < 4) newRot = 90;
                else if (Math.abs(newRot - 180) < 4) newRot = 180;
                else if (Math.abs(newRot - 270) < 4) newRot = 270;

                this.state.rotation = newRot;
                this.applyTransforms();
                this.updateTransformBadge(true);
            }
        });

        window.addEventListener('mouseup', () => {
            if (isInteracting) {
                isInteracting = false;
                activeAction = null;
                if (this.guideV) this.guideV.style.display = 'none';
                if (this.guideH) this.guideH.style.display = 'none';
                this.notifyChange();

                if (badgeTimeout) clearTimeout(badgeTimeout);
                badgeTimeout = setTimeout(() => {
                    if (this.transformBadgeEl && !isInteracting) {
                        this.transformBadgeEl.classList.remove('visible');
                    }
                }, 2000);
            }
        });
    }

    resetTransform() {
        this.state.zoom = 1.0;
        this.state.panX = 0;
        this.state.panY = 0;
        this.state.rotation = 0;
        this.applyTransforms();
        this.updateTransformBadge(true);
        this.notifyChange();
        showToast('🎯 Đã khôi phục khung hình video về vị trí chuẩn tâm (Fit 100%)', 'info', 2000);
    }

    applyTransforms() {
        const flipX = this.state.flipH ? -1 : 1;
        const flipY = this.state.flipV ? -1 : 1;
        const zoom = this.state.zoom || 1.0;
        const panX = this.state.panX || 0;
        const panY = this.state.panY || 0;
        const rot = this.state.rotation || 0;

        // 1. Áp dụng cho Zoom Wrapper / Video
        if (this.zoomWrapper) {
            this.zoomWrapper.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom * flipX}, ${zoom * flipY}) rotate(${rot}deg)`;
            this.zoomWrapper.style.transformOrigin = 'center center';
        } else if (this.video) {
            this.video.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom * flipX}, ${zoom * flipY}) rotate(${rot}deg)`;
            this.video.style.transformOrigin = 'center center';
        }

        // 2. Đồng bộ Khung Neo Bounding Box & 4 Góc Neo theo Video
        if (this.transformFrameEl) {
            this.transformFrameEl.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom}) rotate(${rot}deg)`;
            this.transformFrameEl.style.transformOrigin = 'center center';
        }
    }

    takeSnapshot() {
        if (!this.video || !this.video.videoWidth || !this.video.videoHeight) {
            showToast('Vui lòng nạp video trước khi chụp ảnh khung hình!', 'warning');
            return;
        }

        try {
            const canvas = document.createElement('canvas');
            const vw = this.video.videoWidth;
            const vh = this.video.videoHeight;

            // Xử lý góc xoay 90/270 độ hoán đổi chiều dài rộng
            const is90or270 = this.state.rotation === 90 || this.state.rotation === 270;
            canvas.width = is90or270 ? vh : vw;
            canvas.height = is90or270 ? vw : vh;

            const ctx = canvas.getContext('2d');
            ctx.save();
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate((this.state.rotation * Math.PI) / 180);
            ctx.scale(this.state.flipH ? -1 : 1, this.state.flipV ? -1 : 1);
            ctx.drawImage(this.video, -vw / 2, -vh / 2, vw, vh);
            ctx.restore();

            const timestampStr = new Date().toISOString().replace(/[-:T.]/g, '').substring(0, 14);
            const filename = `snapshot_${this.type}_${timestampStr}.png`;

            // Tải xuống file PNG
            const dataUrl = canvas.toDataURL('image/png');
            const link = document.createElement('a');
            link.download = filename;
            link.href = dataUrl;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            showToast(`📸 Đã chụp và tải ảnh Thumbnail: ${filename}`, 'success', 3000);
        } catch (err) {
            console.error('Snapshot Error:', err);
            showToast(`Lỗi khi chụp ảnh: ${err.message}`, 'error');
        }
    }

    toggleFullscreen() {
        if (!this.container) return;
        if (!document.fullscreenElement) {
            this.container.requestFullscreen().catch(err => {
                console.log('Fullscreen error:', err);
            });
        } else {
            document.exitFullscreen().catch(() => {});
        }
    }

    notifyChange() {
        if (typeof this.onConfigChange === 'function') {
            this.onConfigChange({ ...this.state });
        }
    }
}

// Global registry for quick access
export const videoStudioInstances = {
    editor: null,
    review: null
};

export function initVideoStudioSuite() {
    // 1. Initialize for Editor Tab
    const editorContainer = document.getElementById('videoContainer');
    const editorVideo = document.getElementById('videoPlayer');
    const editorZoomWrapper = document.getElementById('videoZoomWrapper');
    const editorControls = editorContainer ? editorContainer.closest('.video-player-card')?.querySelector('.player-controls') : null;

    if (editorContainer && editorVideo) {
        videoStudioInstances.editor = new VideoStudioSuite({
            type: 'editor',
            container: editorContainer,
            video: editorVideo,
            zoomWrapper: editorZoomWrapper,
            playerControls: editorControls,
            onConfigChange: (config) => {
                // Đồng bộ sang các input trong form Biên tập nếu có
                const editAspect = document.getElementById('editToolAspectRatio');
                if (editAspect && config.aspectRatio) {
                    editAspect.value = config.aspectRatio;
                }
            }
        });
    }

    // 2. Initialize for Review Tab
    const reviewContainer = document.getElementById('reviewVideoContainer');
    const reviewVideo = document.getElementById('reviewVideoPlayer');
    const reviewZoomWrapper = document.getElementById('reviewVideoZoomWrapper');
    const reviewControls = reviewContainer ? reviewContainer.closest('#reviewVideoPlayerCard')?.querySelector('.player-controls') : null;

    if (reviewContainer && reviewVideo) {
        videoStudioInstances.review = new VideoStudioSuite({
            type: 'review',
            container: reviewContainer,
            video: reviewVideo,
            zoomWrapper: reviewZoomWrapper,
            playerControls: reviewControls,
            onConfigChange: (config) => {
                // Đồng bộ sang biến toàn cục Review config
                if (config.aspectRatio) {
                    window.reviewAspectRatio = config.aspectRatio;
                }

                // Đồng bộ trạng thái active với 2 nút ở Phần 4: CẤU HÌNH DỰNG PHIM & XUẤT FILE
                const rVert = document.getElementById('reviewRatioVertical');
                const rHoriz = document.getElementById('reviewRatioHorizontal');
                if (rVert && rHoriz) {
                    if (config.aspectRatio === '9:16') {
                        rVert.classList.add('active');
                        rVert.style.borderColor = '#38bdf8';
                        rVert.style.color = '#38bdf8';
                        rHoriz.classList.remove('active');
                        rHoriz.style.borderColor = '';
                        rHoriz.style.color = '';
                    } else if (config.aspectRatio === '16:9') {
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
            }
        });
    }

    console.log('[VideoStudioSuite] Universal CapCut-Style Video Studio Suite initialized for Editor & Review players.');
}
