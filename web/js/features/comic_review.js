/**
 * Comic Review Studio Feature Module
 * Phân hệ Review Truyện Tranh (Crawl -> Slicing -> AI Script -> TTS -> 4-Col Grid -> Video Render)
 */

class ComicReviewManager {
    constructor() {
        const savedSession = localStorage.getItem('novacut_comic_session_id');
        this.sessionId = savedSession || ('comic_' + Math.random().toString(36).substring(2, 10));
        localStorage.setItem('novacut_comic_session_id', this.sessionId);

        this.panels = [];
        this.segments = [];
        this.activePickingSegmentId = null;
        this.isProcessing = false;
        this.abortController = null;
        this.playingAudio = null;

        this.initDOMElements();
        this.bindEvents();

        // Tự động kiểm tra và phục hồi dự án đã có trên đĩa
        setTimeout(() => this.autoRestoreExistingProject(), 300);
    }

    initDOMElements() {
        // Inputs & Buttons
        this.inputUrl = document.getElementById('comicChapterUrl');
        this.btnCrawl = document.getElementById('btnCrawlComic');
        this.btnSelectFolder = document.getElementById('btnSelectComicFolder');
        this.folderPicker = document.getElementById('comicLocalFolderPicker');
        this.selectStyle = document.getElementById('comicStyleSelect');
        this.selectChapterScope = document.getElementById('comicChapterScope');
        this.inputCustomChapterCount = document.getElementById('comicCustomChapterCount');
        this.selectVoice = document.getElementById('comicVoiceSelect');
        this.voiceSpeed = document.getElementById('comicVoiceSpeed');
        this.voiceSpeedVal = document.getElementById('comicVoiceSpeedVal');
        this.speedChips = document.querySelectorAll('.comic-speed-chip');
        this.btnStartAnalysis = document.getElementById('btnStartComicAnalysis');
        this.btnStopTask = document.getElementById('btnStopComicTask');
        this.chkFilterTextHeavy = document.getElementById('comicFilterTextHeavy');
        this.chkInpaintBubbles = document.getElementById('comicInpaintBubbles');

        // Thư mục lưu trữ & Tên dự án
        this.inputCustomSaveDir = document.getElementById('comicCustomSaveDir');
        this.btnBrowseSaveDir = document.getElementById('btnBrowseComicSaveDir');
        this.btnClearSaveDir = document.getElementById('btnClearComicSaveDir');
        this.inputProjectFolderName = document.getElementById('comicProjectFolderName');
        this.btnOpenProjectFolder = document.getElementById('btnOpenComicProjectFolder');

        const savedDir = localStorage.getItem('novacut_comic_save_dir');
        if (savedDir && this.inputCustomSaveDir) {
            this.inputCustomSaveDir.value = savedDir;
        }

        const savedProjName = localStorage.getItem('novacut_comic_project_name');
        if (savedProjName && this.inputProjectFolderName) {
            this.inputProjectFolderName.value = savedProjName;
        }

        const savedUrl = localStorage.getItem('novacut_comic_chapter_url');
        if (savedUrl && this.inputUrl) {
            this.inputUrl.value = savedUrl;
        }

        // Badges & Progress
        this.sessionBadge = document.getElementById('comicSessionBadge');
        this.crawlStatusBadge = document.getElementById('comicCrawlStatusBadge');
        this.stageBadge = document.getElementById('comicStageBadge');
        this.progressBox = document.getElementById('comicProgressBox');
        this.progressBar = document.getElementById('comicProgressBar');
        this.progressPct = document.getElementById('comicProgressPct');
        this.progressText = document.getElementById('comicProgressText');
        this.logOutput = document.getElementById('comicLogOutput');

        // Render Progress Dashboard (Step 3)
        this.renderProgressBox = document.getElementById('comicRenderProgressBox');
        this.renderProgressBar = document.getElementById('comicRenderProgressBar');
        this.renderProgressPct = document.getElementById('comicRenderProgressPct');
        this.renderProgressText = document.getElementById('comicRenderProgressText');
        this.renderStageBadge = document.getElementById('comicRenderStageBadge');
        this.renderLogOutput = document.getElementById('comicRenderLogOutput');

        // 4-Column Workspace
        this.summaryBadge = document.getElementById('comicSegmentSummaryBadge');
        this.btnAddSegment = document.getElementById('btnAddComicSegment');
        this.btnRecreateAllVoice = document.getElementById('btnRecreateAllComicVoice');
        this.segmentsList = document.getElementById('comicSegmentsList');
        this.emptyPlaceholder = document.getElementById('comicEmptyPlaceholder');

        // Export Dashboard
        this.selectAspect = document.getElementById('comicAspectRatio');
        this.selectKenBurns = document.getElementById('comicKenBurns');
        this.selectBurnSubs = document.getElementById('comicBurnSubs');
        this.inputOutputName = document.getElementById('comicOutputFileName');
        this.btnRenderVideo = document.getElementById('btnRenderComicVideo');
        this.btnStopRender = document.getElementById('btnStopComicRender');
        this.resultContainer = document.getElementById('comicResultContainer');
        this.resultPlayer = document.getElementById('comicResultVideoPlayer');
        this.btnOpenOutputDir = document.getElementById('btnOpenComicOutputDir');

        // Modal Gallery
        this.galleryModal = document.getElementById('comicGalleryModal');
        this.galleryGrid = document.getElementById('comicGalleryGrid');
        this.btnCloseGallery = document.getElementById('btnCloseComicGallery');

        // Modal Crop Ô Tranh
        this.initCropToolElements();
    }

    bindEvents() {
        if (this.btnCrawl) {
            this.btnCrawl.addEventListener('click', () => this.startCrawl(false, '', true));
        }

        if (this.btnSelectFolder) {
            this.btnSelectFolder.addEventListener('click', async () => {
                try {
                    const resp = await fetch('/api/select_folder', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: 'Chọn thư mục ảnh truyện hoặc thư mục dự án đã cào' })
                    });
                    const data = await resp.json();
                    if (data.success && data.folder_path) {
                        await this.handleDirectFolderPicked(data.folder_path);
                        return;
                    }
                } catch (e) {}
                if (this.folderPicker) this.folderPicker.click();
            });
        }

        if (this.inputUrl) {
            this.inputUrl.addEventListener('input', () => {
                localStorage.setItem('novacut_comic_chapter_url', this.inputUrl.value.trim());
            });
        }

        if (this.inputProjectFolderName) {
            this.inputProjectFolderName.addEventListener('input', () => {
                localStorage.setItem('novacut_comic_project_name', this.inputProjectFolderName.value.trim());
                this.loadPanels();
            });
        }

        if (this.voiceSpeed && this.voiceSpeedVal) {
            this.voiceSpeed.addEventListener('input', (e) => {
                const val = parseFloat(e.target.value);
                this.voiceSpeedVal.textContent = val.toFixed(2) + 'x';
                this.updateSpeedChips(val);
            });
        }

        if (this.speedChips && this.speedChips.length > 0) {
            this.speedChips.forEach(chip => {
                chip.addEventListener('click', (e) => {
                    e.preventDefault();
                    const speed = parseFloat(chip.dataset.speed);
                    if (this.voiceSpeed) this.voiceSpeed.value = speed;
                    if (this.voiceSpeedVal) this.voiceSpeedVal.textContent = speed.toFixed(2) + 'x';
                    this.updateSpeedChips(speed);
                });
            });
        }

        if (this.selectChapterScope && this.inputCustomChapterCount) {
            this.selectChapterScope.addEventListener('change', () => {
                if (this.selectChapterScope.value === 'custom') {
                    this.inputCustomChapterCount.style.display = 'block';
                    this.inputCustomChapterCount.focus();
                } else {
                    this.inputCustomChapterCount.style.display = 'none';
                }
            });
        }

        if (this.folderPicker) {
            this.folderPicker.addEventListener('change', (e) => this.handleFolderSelected(e));
        }

        if (this.btnStartAnalysis) {
            this.btnStartAnalysis.addEventListener('click', () => this.startAnalysisAndScript());
        }

        if (this.btnStopTask) {
            this.btnStopTask.addEventListener('click', () => this.stopCurrentTask());
        }

        if (this.btnAddSegment) {
            this.btnAddSegment.addEventListener('click', () => this.addNewSegment());
        }

        if (this.btnRecreateAllVoice) {
            this.btnRecreateAllVoice.addEventListener('click', () => this.recreateAllVoice());
        }

        if (this.btnRenderVideo) {
            this.btnRenderVideo.addEventListener('click', () => this.startRenderVideo());
        }

        if (this.btnStopRender) {
            this.btnStopRender.addEventListener('click', () => this.stopCurrentTask());
        }

        if (this.btnBrowseSaveDir) {
            this.btnBrowseSaveDir.addEventListener('click', () => this.browseSaveDir());
        }

        if (this.btnClearSaveDir) {
            this.btnClearSaveDir.addEventListener('click', () => this.clearSaveDir());
        }

        if (this.btnOpenProjectFolder) {
            this.btnOpenProjectFolder.addEventListener('click', () => this.openProjectFolder());
        }

        if (this.inputUrl && this.inputProjectFolderName) {
            this.inputUrl.addEventListener('change', () => {
                if (!this.inputProjectFolderName.value.trim()) {
                    const u = this.inputUrl.value.trim();
                    try {
                        const parts = u.split('/').filter(Boolean);
                        let last = parts[parts.length - 1] || '';
                        last = last.replace(/\.html|\.htm|\.php/i, '');
                        if (last) this.inputProjectFolderName.value = last;
                    } catch (e) {}
                }
            });
        }

        if (this.btnCloseGallery) {
            this.btnCloseGallery.addEventListener('click', () => this.closeGalleryModal());
        }

        if (this.btnOpenOutputDir) {
            this.btnOpenOutputDir.addEventListener('click', () => this.openOutputFolder());
        }

        // Close modal when clicking backdrop
        if (this.galleryModal) {
            this.galleryModal.addEventListener('click', (e) => {
                if (e.target === this.galleryModal) this.closeGalleryModal();
            });
        }

        // Khởi tạo các sự kiện cho Crop Tool
        this.initCropToolEvents();
    }

    updateSpeedChips(val) {
        if (!this.speedChips || this.speedChips.length === 0) return;
        this.speedChips.forEach(chip => {
            const speed = parseFloat(chip.dataset.speed);
            if (Math.abs(speed - val) < 0.03) {
                chip.classList.add('active');
                chip.style.color = '#38bdf8';
                chip.style.borderColor = '#38bdf8';
                chip.style.fontWeight = '600';
            } else {
                chip.classList.remove('active');
                chip.style.color = '#94a3b8';
                chip.style.borderColor = '#334155';
                chip.style.fontWeight = '500';
            }
        });
    }

    getStorageInfo() {
        return {
            custom_save_dir: this.inputCustomSaveDir ? this.inputCustomSaveDir.value.trim() : '',
            project_folder_name: this.inputProjectFolderName ? this.inputProjectFolderName.value.trim() : ''
        };
    }

    async browseSaveDir() {
        try {
            const resp = await fetch('/api/select_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: 'Chọn thư mục lưu dự án Review Truyện' })
            });
            const data = await resp.json();
            if (data.success && data.folder_path) {
                if (this.inputCustomSaveDir) this.inputCustomSaveDir.value = data.folder_path;
                localStorage.setItem('novacut_comic_save_dir', data.folder_path);
                if (typeof showToast === 'function') {
                    showToast(`Đã chọn thư mục lưu: ${data.folder_path}`, 'info');
                }
            }
        } catch (e) {
            console.error('Lỗi chọn thư mục:', e);
        }
    }

    clearSaveDir() {
        if (this.inputCustomSaveDir) this.inputCustomSaveDir.value = '';
        localStorage.removeItem('novacut_comic_save_dir');
        if (typeof showToast === 'function') {
            showToast('Đã đặt lại thư mục lưu về mặc định.', 'info');
        }
    }

    async openProjectFolder() {
        const storage = this.getStorageInfo();
        try {
            const resp = await fetch('/api/comic_review/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name,
                    type: 'project'
                })
            });
            const data = await resp.json();
            if (data.success) {
                if (typeof showToast === 'function') {
                    showToast(`Đã mở thư mục: ${data.folder_path}`, 'success');
                }
            } else {
                if (typeof showAlertModal === 'function') {
                    showAlertModal('Thông báo', data.error || 'Chưa thể mở thư mục');
                }
            }
        } catch (e) {
            console.error('Lỗi mở thư mục:', e);
        }
    }

    async openOutputFolder() {
        const storage = this.getStorageInfo();
        try {
            const resp = await fetch('/api/comic_review/open_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name,
                    type: 'output'
                })
            });
            const data = await resp.json();
            if (data.success && typeof showToast === 'function') {
                showToast(`Đã mở thư mục xuất: ${data.folder_path}`, 'success');
            }
        } catch (e) {
            console.error('Lỗi mở thư mục output:', e);
        }
    }

    getChapterScopeInfo() {
        const scope = this.selectChapterScope ? this.selectChapterScope.value : '5';
        let count = 5;
        let isAll = false;
        if (scope === 'all') {
            count = 999;
            isAll = true;
        } else if (scope === 'custom') {
            count = parseInt(this.inputCustomChapterCount ? this.inputCustomChapterCount.value : 15) || 5;
        } else {
            count = parseInt(scope) || 1;
        }
        return { chapter_scope: scope, chapter_count: count, is_all: isAll };
    }

    showProgress(visible, text = "Đang xử lý...", pct = 0, stage = "TIẾN TRÌNH") {
        if (!this.progressBox) return;
        this.progressBox.style.display = visible ? 'block' : 'none';
        if (visible) {
            if (this.progressText) {
                this.progressText.textContent = text;
                this.progressText.title = text;
            }
            if (this.progressPct) this.progressPct.textContent = pct + '%';
            if (this.progressBar) this.progressBar.style.width = pct + '%';
            if (this.stageBadge && stage) this.stageBadge.textContent = stage;
            if (pct === 0 && this.logOutput) this.logOutput.innerHTML = '';
        }
    }

    _formatLog(msg) {
        let raw = String(msg ?? '');
        if (/^\s*\[\d{1,2}:\d{2}(?::\d{2})?/.test(raw)) return raw;
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        return `[${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}] ${raw}`;
    }

    appendLog(msg) {
        if (!this.logOutput) return;
        const line = document.createElement('div');
        line.textContent = this._formatLog(msg);
        this.logOutput.appendChild(line);
        this.logOutput.scrollTop = this.logOutput.scrollHeight;
    }

    showRenderProgress(visible, text = "Đang xử lý...", pct = 0, stage = "[1/4 DỰNG CẢNH]") {
        if (!this.renderProgressBox) return;
        this.renderProgressBox.style.display = visible ? 'block' : 'none';
        if (visible) {
            if (this.renderProgressText) {
                this.renderProgressText.textContent = text;
                this.renderProgressText.title = text;
            }
            if (this.renderProgressPct) this.renderProgressPct.textContent = pct + '%';
            if (this.renderProgressBar) this.renderProgressBar.style.width = pct + '%';
            if (this.renderStageBadge && stage) this.renderStageBadge.textContent = stage;
            if (pct === 0 && this.renderLogOutput) this.renderLogOutput.innerHTML = '';
        }
    }

    appendRenderLog(msg) {
        if (!this.renderLogOutput) return;
        const line = document.createElement('div');
        line.textContent = this._formatLog(msg);
        this.renderLogOutput.appendChild(line);
        this.renderLogOutput.scrollTop = this.renderLogOutput.scrollHeight;
    }

    updateProgressUI(content, isRender = false) {
        if (!content) return;

        // Check for progress percentage tag
        if (content.startsWith('[PROGRESS]')) {
            const pct = parseInt(content.split(' ')[1]) || 0;
            if (this.progressPct) this.progressPct.textContent = pct + '%';
            if (this.progressBar) this.progressBar.style.width = pct + '%';
            if (this.renderProgressPct) this.renderProgressPct.textContent = pct + '%';
            if (this.renderProgressBar) this.renderProgressBar.style.width = pct + '%';
            return;
        }

        // Tự động nhận diện nhãn giai đoạn trong dấu ngoặc vuông (vd: [Cắt Ô Tranh], [AI OCR], [1/4 Dựng Cảnh]...)
        const stageMatch = content.match(/\[([^\]]+)\]/);
        if (stageMatch && stageMatch[1]) {
            const stageTag = stageMatch[1].trim().toUpperCase();
            if (this.stageBadge) {
                this.stageBadge.textContent = stageTag;
            }
            if (this.renderStageBadge && isRender) {
                this.renderStageBadge.textContent = `[${stageTag}]`;
            }
        }

        // Cập nhật câu trạng thái chi tiết đang làm gì
        if (this.progressText) {
            this.progressText.textContent = content;
            this.progressText.title = content;
        }
        if (this.renderProgressText && isRender) {
            this.renderProgressText.textContent = content;
            this.renderProgressText.title = content;
        }

        this.appendLog(content);
        if (isRender) {
            this.appendRenderLog(content);
        }
    }

    async startCrawl(isFolder = false, folderPath = '', autoProceedToScript = true) {
        const url = this.inputUrl.value.trim();
        if (!isFolder && !url) {
            if (typeof showAlertModal === 'function') {
                showAlertModal('Thiếu thông tin', 'Vui lòng nhập Link web đọc truyện tranh hoặc chọn thư mục ảnh!');
            } else {
                alert('Vui lòng nhập Link web đọc truyện tranh!');
            }
            return;
        }

        if (typeof checkFeaturePermission === 'function') {
            const allowed = await checkFeaturePermission('can_access_review', 'Review Truyện Tranh');
            if (!allowed) return;
        }

        const scopeInfo = this.getChapterScopeInfo();
        const storage = this.getStorageInfo();
        const scopeDesc = scopeInfo.is_all ? 'Toàn bộ truyện' : `${scopeInfo.chapter_count} chap`;
        this.showProgress(true, `Đang kết nối tới trang truyện (${scopeDesc})...`, 5);
        this.btnStopTask.style.display = 'inline-block';
        this.btnStartAnalysis.disabled = true;

        try {
            const resp = await fetch('/api/comic_review/crawl_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: isFolder ? '' : url,
                    folder_path: isFolder ? folderPath : '',
                    session_id: this.sessionId,
                    chapter_scope: scopeInfo.chapter_scope,
                    chapter_count: scopeInfo.chapter_count,
                    is_all: scopeInfo.is_all,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name
                })
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const block of lines) {
                    const line = block.trim();
                    if (!line.startsWith('data: ')) continue;
                    const content = line.substring(6).trim();

                    if (content.startsWith('[SESSION_DIR]')) {
                        const sDir = content.substring(13).trim();
                        if (this.sessionBadge) {
                            const baseName = sDir.split(/[\\/]/).pop();
                            this.sessionBadge.textContent = '📁 ' + baseName;
                            this.sessionBadge.title = sDir;
                        }
                    } else if (content.startsWith('[PANELS_READY]')) {
                        const count = parseInt(content.split(' ')[1]) || 0;
                        this.crawlStatusBadge.textContent = `Đã cắt ${count} ô tranh`;
                        this.crawlStatusBadge.style.color = '#34d399';
                        this.crawlStatusBadge.style.borderColor = '#10b981';
                        await this.loadPanels();
                    } else {
                        this.updateProgressUI(content, false);
                    }
                }
            }

            // Xử lý buffer còn lại nếu có
            if (buffer && buffer.trim()) {
                const line = buffer.trim();
                if (line.startsWith('data: ')) {
                    const content = line.substring(6).trim();
                    if (content.startsWith('[PANELS_READY]')) {
                        const count = parseInt(content.split(' ')[1]) || 0;
                        this.crawlStatusBadge.textContent = `Đã cắt ${count} ô tranh`;
                    }
                    this.updateProgressUI(content, false);
                }
            }

            // Nạp danh sách ô tranh đã cắt
            await this.loadPanels();

            // TỰ ĐỘNG CHẠY TIẾP BƯỚC VIẾT KỊCH BẢN & SINH VOICE NẾU ĐÃ CÓ Ô TRANH
            if (autoProceedToScript && this.panels && this.panels.length > 0) {
                this.appendLog(`🎉 Đã tạo ${this.panels.length} ô tranh! Đang tự động chuyển sang AI viết kịch bản review...`);
                await new Promise(r => setTimeout(r, 600));
                await this.startScriptGeneration();
            }
        } catch (err) {
            this.appendLog('🛑 Lỗi: ' + err.message);
        } finally {
            this.btnStopTask.style.display = 'none';
            this.btnStartAnalysis.disabled = false;
        }
    }

    async handleFolderSelected(e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        
        // Lấy đường dẫn folder đại diện nếu có
        const firstFile = files[0];
        const folderName = firstFile.webkitRelativePath ? firstFile.webkitRelativePath.split('/')[0] : 'Thư mục đã chọn';
        this.crawlStatusBadge.textContent = `Nạp từ ${folderName} (${files.length} ảnh)`;
        if (!this.inputProjectFolderName.value.trim()) {
            this.inputProjectFolderName.value = folderName.replace(/[\\/*?:"<>|]/g, '_');
        }
        
        if (typeof showToast === 'function') {
            showToast(`Đã nhận diện ${files.length} file ảnh từ ${folderName}`, 'info');
        }

        // Tự động trigger nạp và tự động viết kịch bản luôn
        await this.startCrawl(true, '', true);
    }

    async handleDirectFolderPicked(folderPath) {
        if (!folderPath) return;
        try {
            const resp = await fetch('/api/comic_review/detect_project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: folderPath,
                    project_folder_name: ''
                })
            });
            const data = await resp.json();
            if (data.success && data.found) {
                if (this.inputCustomSaveDir) {
                    this.inputCustomSaveDir.value = folderPath;
                    localStorage.setItem('novacut_comic_save_dir', folderPath);
                }
                if (data.project_folder_name && this.inputProjectFolderName) {
                    this.inputProjectFolderName.value = data.project_folder_name;
                    localStorage.setItem('novacut_comic_project_name', data.project_folder_name);
                }
                await this.loadPanels();
                if (typeof showToast === 'function') {
                    showToast(`✅ Đã nạp thành công ${this.panels.length} ô tranh từ ${data.project_folder_name}!`, 'success');
                }
                return;
            }
        } catch (e) {
            console.error('Lỗi kiểm tra thư mục đã chọn:', e);
        }

        // Nếu là thư mục chứa ảnh thô chưa cắt, tiến hành nạp và cắt
        if (this.crawlStatusBadge) this.crawlStatusBadge.textContent = `Nạp từ: ${folderPath}`;
        if (typeof showToast === 'function') {
            showToast(`Bắt đầu nạp và xử lý ảnh từ thư mục đã chọn...`, 'info');
        }
        await this.startCrawl(false, folderPath, true);
    }

    async autoRestoreExistingProject() {
        try {
            const storage = this.getStorageInfo();
            if (!storage.custom_save_dir && !storage.project_folder_name) {
                return false;
            }
            const resp = await fetch('/api/comic_review/detect_project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name
                })
            });
            const data = await resp.json();
            if (data.success && data.found) {
                if (data.project_folder_name && this.inputProjectFolderName) {
                    if (!this.inputProjectFolderName.value.trim() || this.inputProjectFolderName.value.trim() !== data.project_folder_name) {
                        this.inputProjectFolderName.value = data.project_folder_name;
                        localStorage.setItem('novacut_comic_project_name', data.project_folder_name);
                    }
                }
                const loaded = await this.loadPanels();
                if (loaded && loaded.length > 0) {
                    if (this.crawlStatusBadge) {
                        this.crawlStatusBadge.textContent = `Đã có ${loaded.length} ô tranh (${data.project_folder_name || 'Dự án'})`;
                        this.crawlStatusBadge.style.color = '#34d399';
                        this.crawlStatusBadge.style.borderColor = '#10b981';
                    }
                    if (typeof showToast === 'function') {
                        showToast(`⚡ Đã tự động khôi phục dự án: ${data.project_folder_name} (${loaded.length} ô tranh)`, 'success');
                    }
                    return true;
                }
            }
        } catch (e) {
            console.error('Lỗi tự động khôi phục dự án:', e);
        }
        return false;
    }

    async loadPanels() {
        try {
            const storage = this.getStorageInfo();
            const url = new URL('/api/comic_review/panels', window.location.origin);
            url.searchParams.set('session_id', this.sessionId);
            if (storage.custom_save_dir) url.searchParams.set('custom_save_dir', storage.custom_save_dir);
            if (storage.project_folder_name) url.searchParams.set('project_folder_name', storage.project_folder_name);

            const resp = await fetch(url.toString());
            const data = await resp.json();
            if (data.success && data.panels && data.panels.length > 0) {
                this.panels = data.panels;
                this.crawlStatusBadge.textContent = `Đã có ${this.panels.length} ô tranh`;
                this.crawlStatusBadge.style.color = '#34d399';
                this.crawlStatusBadge.style.borderColor = '#10b981';
                this.renderGalleryGrid();
                return this.panels;
            }
        } catch (e) {
            console.error('Lỗi tải danh sách ô tranh:', e);
        }
        return this.panels;
    }

    async startAnalysisAndScript() {
        // 1. Thử nạp lại panels từ đĩa (nếu đã có trong RAM hoặc cache)
        if (this.panels.length === 0) {
            await this.loadPanels();
        }

        // 2. Thử tự động phát hiện dự án từ thư mục lưu trữ tùy chỉnh
        if (this.panels.length === 0) {
            await this.autoRestoreExistingProject();
        }

        // 3. Nếu vẫn chưa có panels nào, kiểm tra xem có link URL để tự động cào không
        if (this.panels.length === 0) {
            if (this.inputUrl && this.inputUrl.value.trim()) {
                await this.startCrawl(false, '', true);
                return;
            } else {
                if (typeof showAlertModal === 'function') {
                    showAlertModal('Chưa nạp truyện', 'Vui lòng dán Link web truyện tranh hoặc nạp thư mục ảnh trước khi phân tích!');
                } else {
                    alert('Vui lòng nạp truyện trước!');
                }
                return;
            }
        }

        // 4. Đã có panels -> Bắt đầu viết kịch bản luôn
        await this.startScriptGeneration();
    }

    async startScriptGeneration() {
        if (typeof checkFeaturePermission === 'function') {
            const allowed = await checkFeaturePermission('can_access_review', 'Review Truyện Tranh');
            if (!allowed) return;
        }

        this.showProgress(true, "AI đang đọc lời thoại và lên kịch bản review...", 10);
        this.btnStopTask.style.display = 'inline-block';
        this.btnStartAnalysis.disabled = true;

        const scopeInfo = this.getChapterScopeInfo();
        const storage = this.getStorageInfo();
        const filterTextHeavy = this.chkFilterTextHeavy ? this.chkFilterTextHeavy.checked : true;
        const inpaintBubbles = this.chkInpaintBubbles ? this.chkInpaintBubbles.checked : false;

        const payload = {
            session_id: this.sessionId,
            style: this.selectStyle ? this.selectStyle.value : 'badass',
            chapter_scope: scopeInfo.chapter_scope,
            chapter_count: scopeInfo.chapter_count,
            is_all: scopeInfo.is_all,
            custom_save_dir: storage.custom_save_dir,
            project_folder_name: storage.project_folder_name,
            voice_id: this.selectVoice ? this.selectVoice.value : 'ngoc_huyen',
            speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10,
            voice_speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10,
            filter_text_heavy: filterTextHeavy,
            inpaint_bubbles: inpaintBubbles
        };

        try {
            const resp = await fetch('/api/comic_review/generate_script_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const block of lines) {
                    const line = block.trim();
                    if (!line.startsWith('data: ')) continue;
                    const content = line.substring(6).trim();

                    if (content.startsWith('[SEGMENTS_READY]')) {
                        const jsonStr = content.substring(16).trim();
                        try {
                            this.segments = JSON.parse(jsonStr);
                            this.render4ColumnTable();
                            if (typeof showToast === 'function') {
                                showToast(`🎉 Đã tạo xong ${this.segments.length} phân cảnh kịch bản và giọng đọc!`, 'success');
                            }
                        } catch (err) {
                            console.error('Lỗi parse segments:', err);
                        }
                    } else {
                        this.updateProgressUI(content, false);
                    }
                }
            }
        } catch (err) {
            this.appendLog('🛑 Lỗi tạo kịch bản: ' + err.message);
        } finally {
            this.btnStopTask.style.display = 'none';
            this.btnStartAnalysis.disabled = false;
        }
    }

    formatTime(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        const ms = Math.floor((sec - Math.floor(sec)) * 10);
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms}`;
    }

    recalculateTimestamps() {
        let curr = 0.0;
        for (const seg of this.segments) {
            seg.start_time = Number(curr.toFixed(2));
            seg.end_time = Number((curr + seg.duration).toFixed(2));
            curr = seg.end_time;
        }
        if (this.summaryBadge) {
            const totalDur = curr;
            const m = Math.floor(totalDur / 60);
            const s = Math.floor(totalDur % 60);
            this.summaryBadge.textContent = `${this.segments.length} phân cảnh • Tổng thời lượng: ${m}:${s.toString().padStart(2, '0')}`;
        }
    }

    render4ColumnTable() {
        if (!this.segmentsList) return;
        this.segmentsList.innerHTML = '';

        if (!this.segments || this.segments.length === 0) {
            if (this.emptyPlaceholder) this.segmentsList.appendChild(this.emptyPlaceholder);
            return;
        }

        this.recalculateTimestamps();

        this.segments.forEach((seg, idx) => {
            const row = document.createElement('div');
            row.className = 'comic-segment-row';
            row.id = `comicSegRow_${seg.id}`;
            row.style.cssText = `
                display: grid;
                grid-template-columns: 140px 220px 1fr 240px;
                padding: 12px 14px;
                background: ${idx % 2 === 0 ? '#0f172a' : 'rgba(30, 41, 59, 0.4)'};
                border-bottom: 1px solid #1e293b;
                align-items: center;
                gap: 12px;
                transition: background 0.15s ease;
            `;

            // CỘT 1: TIMELINE
            const col1 = document.createElement('div');
            col1.style.cssText = "display: flex; flex-direction: column; gap: 4px;";
            col1.innerHTML = `
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="font-size: 11px; font-weight: 800; background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff; padding: 2px 6px; border-radius: 4px;">#${idx + 1}</span>
                    <span style="font-size: 11.5px; font-weight: 700; color: #38bdf8;">${this.formatTime(seg.start_time)} - ${this.formatTime(seg.end_time)}</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8; display: flex; align-items: center; gap: 4px;">
                    <span>⏱️ Thời lượng:</span>
                    <strong style="color: #fbbf24;">${seg.duration.toFixed(1)}s</strong>
                </div>
            `;

            // CỘT 2: HÌNH ẢNH (Ô TRANH)
            const col2 = document.createElement('div');
            col2.style.cssText = "display: flex; align-items: center; gap: 10px;";
            const imgUrl = seg.panel_url || '/static/logo.png';
            col2.innerHTML = `
                <div style="width: 70px; height: 70px; border-radius: 6px; overflow: hidden; background: #000; border: 1px solid #334155; flex-shrink: 0; position: relative; cursor: pointer;" title="Nhấp để xem rõ hoặc cắt lại khung ảnh">
                    <img src="${imgUrl}" alt="Panel" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='/static/logo.png'">
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px; overflow: hidden;">
                    <span style="font-size: 11px; color: #cbd5e1; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;" title="${seg.panel_filename || 'Chưa chọn ảnh'}">${seg.panel_filename || 'Ô tranh'}</span>
                    <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
                        <button type="button" class="btn secondary small btn-change-panel" data-id="${seg.id}" style="padding: 3px 6px; font-size: 10.5px; font-weight: 600; display: flex; align-items: center; gap: 3px; width: fit-content;" title="Chọn ô tranh khác">
                            <span>🖼️ Đổi</span>
                        </button>
                        <button type="button" class="btn secondary small btn-crop-panel" data-id="${seg.id}" style="padding: 3px 6px; font-size: 10.5px; font-weight: 600; display: flex; align-items: center; gap: 3px; width: fit-content; color: #f59e0b; border-color: rgba(245, 158, 11, 0.4);" title="Chỉnh sửa lại khung cắt của ô tranh hoặc cắt từ trang truyện gốc">
                            <span>✂️ Cắt lại</span>
                        </button>
                        <button type="button" class="btn secondary small btn-inpaint-panel" data-id="${seg.id}" style="padding: 3px 6px; font-size: 10.5px; font-weight: 600; display: flex; align-items: center; gap: 3px; width: fit-content; color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);" title="Tự động xóa bong bóng thoại / chữ trên ảnh này bằng AI Inpainting">
                            <span>🪄 Xóa chữ</span>
                        </button>
                    </div>
                </div>
            `;

            // CỘT 3: KỊCH BẢN REVIEW (EDITABLE)
            const col3 = document.createElement('div');
            col3.style.cssText = "display: flex; flex-direction: column; gap: 4px;";
            const textarea = document.createElement('textarea');
            textarea.className = 'text-input';
            textarea.rows = 2;
            textarea.value = seg.script_text;
            textarea.style.cssText = "width: 100%; padding: 8px 10px; background: #0b1120; border: 1px solid #334155; border-radius: 6px; color: #f8fafc; font-size: 12.5px; resize: vertical; line-height: 1.4;";

            const wordCountBadge = document.createElement('div');
            wordCountBadge.style.cssText = "font-size: 10.5px; color: #64748b; text-align: right;";
            const updateWordCount = (txt) => {
                const words = txt.trim() ? txt.trim().split(/\s+/).length : 0;
                wordCountBadge.textContent = `${words} từ • ${txt.length} ký tự`;
            };
            updateWordCount(seg.script_text);

            textarea.addEventListener('input', (e) => {
                seg.script_text = e.target.value;
                updateWordCount(e.target.value);
                // Đổi nút tạo voice sang màu vàng báo hiệu cần tạo lại voice
                const btnRecreate = row.querySelector('.btn-recreate-voice');
                if (btnRecreate) {
                    btnRecreate.style.background = 'linear-gradient(135deg, #d97706, #f59e0b)';
                    btnRecreate.style.color = '#fff';
                    btnRecreate.title = 'Nội dung đã sửa, bấm để tạo lại audio khớp câu!';
                }
            });

            col3.appendChild(textarea);
            col3.appendChild(wordCountBadge);

            // CỘT 4: VOICE ĐI KÈM & THAO TÁC
            const col4 = document.createElement('div');
            col4.style.cssText = "display: flex; flex-direction: column; gap: 6px;";
            col4.innerHTML = `
                <div style="display: flex; align-items: center; gap: 6px;">
                    <audio id="audioPlay_${seg.id}" src="${seg.audio_url || ''}" preload="none"></audio>
                    <button type="button" class="btn secondary small btn-play-beat" data-id="${seg.id}" style="padding: 5px 9px; font-size: 11px; font-weight: 600; display: flex; align-items: center; gap: 4px; background: #1e293b;" title="Nghe thử voice câu này">
                        <span>▶️ Nghe</span>
                    </button>
                    <button type="button" class="btn secondary small btn-recreate-voice" data-id="${seg.id}" style="padding: 5px 9px; font-size: 11px; font-weight: 600; display: flex; align-items: center; gap: 4px;" title="Tạo lại giọng đọc cho câu này">
                        <span>🎙️ Cập nhật</span>
                    </button>
                    <button type="button" class="btn danger small btn-delete-beat" data-id="${seg.id}" style="padding: 5px 8px; font-size: 11px;" title="Xóa phân cảnh này">
                        <span>🗑️</span>
                    </button>
                </div>
            `;

            row.appendChild(col1);
            row.appendChild(col2);
            row.appendChild(col3);
            row.appendChild(col4);

            this.segmentsList.appendChild(row);

            // Gắn sự kiện cho row
            const btnPlay = col4.querySelector('.btn-play-beat');
            const audioElem = col4.querySelector(`#audioPlay_${seg.id}`);
            btnPlay.addEventListener('click', () => {
                if (!audioElem.src || audioElem.src.endsWith('/')) return;
                if (audioElem.paused) {
                    if (this.playingAudio && this.playingAudio !== audioElem) {
                        this.playingAudio.pause();
                        this.playingAudio.currentTime = 0;
                    }
                    audioElem.play();
                    this.playingAudio = audioElem;
                    btnPlay.innerHTML = '<span>⏸️ Dừng</span>';
                    audioElem.onended = () => { btnPlay.innerHTML = '<span>▶️ Nghe</span>'; };
                } else {
                    audioElem.pause();
                    btnPlay.innerHTML = '<span>▶️ Nghe</span>';
                }
            });

            const btnRecreate = col4.querySelector('.btn-recreate-voice');
            btnRecreate.addEventListener('click', () => this.recreateSingleVoice(seg.id, textarea.value, btnRecreate));

            const btnDelete = col4.querySelector('.btn-delete-beat');
            btnDelete.addEventListener('click', () => this.deleteSegment(seg.id));

            const btnChangePanel = col2.querySelector('.btn-change-panel');
            btnChangePanel.addEventListener('click', () => this.openGalleryModal(seg.id));

            const btnCrop = col2.querySelector('.btn-crop-panel');
            if (btnCrop) {
                btnCrop.addEventListener('click', () => this.openCropModal(seg, row));
            }

            const imgPreview = col2.querySelector('div[style*="cursor: pointer"]');
            if (imgPreview) {
                imgPreview.addEventListener('click', () => this.openCropModal(seg, row));
            }

            const btnInpaint = col2.querySelector('.btn-inpaint-panel');
            if (btnInpaint) {
                btnInpaint.addEventListener('click', () => this.inpaintBeatPanel(seg, row));
            }
        });
    }

    async inpaintBeatPanel(seg, row) {
        if (!seg.panel_path) {
            if (typeof showToast === 'function') showToast('Không tìm thấy đường dẫn tệp ảnh gốc!', 'error');
            return;
        }
        const btnInpaint = row ? row.querySelector('.btn-inpaint-panel') : null;
        if (btnInpaint) {
            btnInpaint.disabled = true;
            btnInpaint.innerHTML = '<span>⏳ Đang xóa...</span>';
        }
        try {
            const storage = this.getStorageInfo();
            const resp = await fetch('/api/comic_review/inpaint_beat_panel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name,
                    panel_path: seg.panel_path,
                    beat_id: seg.id
                })
            });
            const data = await resp.json();
            if (data.success && data.clean_url) {
                seg.panel_filename = data.clean_filename;
                seg.panel_path = data.clean_path;
                seg.panel_url = data.clean_url;
                if (row) {
                    const img = row.querySelector('img');
                    if (img) img.src = data.clean_url;
                    const nameSpan = row.querySelector('span[title]');
                    if (nameSpan) {
                        nameSpan.textContent = data.clean_filename;
                        nameSpan.title = data.clean_filename;
                    }
                }
                if (typeof showToast === 'function') {
                    showToast(`✨ Đã xóa chữ thoại phân cảnh #${seg.id} thành công!`, 'success');
                }
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.error || 'Không thể xóa chữ', 'error');
                }
            }
        } catch (err) {
            if (typeof showToast === 'function') {
                showToast('Lỗi: ' + err.message, 'error');
            }
        } finally {
            if (btnInpaint) {
                btnInpaint.disabled = false;
                btnInpaint.innerHTML = '<span>🪄 Xóa chữ</span>';
            }
        }
    }

    async recreateSingleVoice(beatId, text, btnElement) {
        if (!text.trim()) return;
        btnElement.disabled = true;
        btnElement.innerHTML = '<span>⏳ Đang tạo...</span>';

        try {
            const resp = await fetch('/api/comic_review/generate_beat_voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    beat_id: beatId,
                    script_text: text,
                    voice_id: this.selectVoice ? this.selectVoice.value : 'ngoc_huyen',
                    speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10,
                    voice_speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10
                })
            });
            const res = await resp.json();
            if (res.success) {
                const seg = this.segments.find(s => s.id === beatId);
                if (seg) {
                    seg.duration = res.duration;
                    seg.audio_url = res.audio_url;
                }
                this.render4ColumnTable();
                if (typeof showToast === 'function') {
                    showToast(`Đã tạo xong voice phân cảnh #${beatId} (${res.duration}s)`, 'success');
                }
            } else {
                alert('Lỗi tạo voice: ' + res.error);
            }
        } catch (e) {
            alert('Lỗi kết nối: ' + e.message);
        } finally {
            btnElement.disabled = false;
            btnElement.innerHTML = '<span>🎙️ Cập nhật</span>';
        }
    }

    async recreateAllVoice() {
        if (!this.segments || this.segments.length === 0) return;
        this.showProgress(true, "Đang đồng loạt tạo lại voice cho toàn bộ phân cảnh...", 10);

        for (let i = 0; i < this.segments.length; i++) {
            const seg = this.segments[i];
            const pct = Math.round(((i + 1) / this.segments.length) * 100);
            this.progressPct.textContent = pct + '%';
            this.progressBar.style.width = pct + '%';
            this.progressText.textContent = `Tạo voice phân cảnh ${i + 1}/${this.segments.length}...`;

            try {
                const resp = await fetch('/api/comic_review/generate_beat_voice', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.sessionId,
                        beat_id: seg.id,
                        script_text: seg.script_text,
                        voice_id: this.selectVoice ? this.selectVoice.value : 'ngoc_huyen',
                        speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10,
                        voice_speed: this.voiceSpeed ? parseFloat(this.voiceSpeed.value) : 1.10
                    })
                });
                const res = await resp.json();
                if (res.success) {
                    seg.duration = res.duration;
                    seg.audio_url = res.audio_url;
                }
            } catch (e) {
                console.error(e);
            }
        }

        this.render4ColumnTable();
        this.showProgress(false);
        if (typeof showToast === 'function') {
            showToast('Đã tạo lại thành công toàn bộ giọng đọc!', 'success');
        }
    }

    addNewSegment() {
        const nextId = this.segments.length > 0 ? Math.max(...this.segments.map(s => s.id)) + 1 : 1;
        const defaultPanel = this.panels.length > 0 ? this.panels[0] : null;

        const newSeg = {
            id: nextId,
            panel_id: defaultPanel ? defaultPanel.id : nextId,
            panel_filename: defaultPanel ? defaultPanel.filename : '',
            panel_url: defaultPanel ? defaultPanel.thumb_url : '',
            script_text: 'Nhập nội dung lời bình thoại cho phân cảnh này...',
            duration: 3.5,
            start_time: 0,
            end_time: 3.5,
            voice_id: this.selectVoice.value
        };

        this.segments.push(newSeg);
        this.render4ColumnTable();
    }

    deleteSegment(beatId) {
        this.segments = this.segments.filter(s => s.id !== beatId);
        this.render4ColumnTable();
    }

    openGalleryModal(beatId) {
        this.activePickingSegmentId = beatId;
        if (this.galleryModal) {
            this.galleryModal.style.display = 'flex';
        }
    }

    closeGalleryModal() {
        if (this.galleryModal) {
            this.galleryModal.style.display = 'none';
        }
        this.activePickingSegmentId = null;
    }

    renderGalleryGrid() {
        if (!this.galleryGrid) return;
        this.galleryGrid.innerHTML = '';

        this.panels.forEach(p => {
            const card = document.createElement('div');
            card.style.cssText = `
                border-radius: 8px;
                overflow: hidden;
                background: #1e293b;
                border: 1px solid #334155;
                cursor: pointer;
                transition: transform 0.15s, border-color 0.15s;
                position: relative;
            `;
            card.innerHTML = `
                <div style="width: 100%; aspect-ratio: 3/4; overflow: hidden; background: #000;">
                    <img src="${p.thumb_url}" alt="${p.filename}" style="width: 100%; height: 100%; object-fit: cover;" loading="lazy">
                </div>
                <div style="padding: 6px; font-size: 10.5px; color: #94a3b8; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    #${p.id} (${p.width}x${p.height})
                </div>
            `;

            card.onmouseenter = () => { card.style.borderColor = '#38bdf8'; card.style.transform = 'scale(1.02)'; };
            card.onmouseleave = () => { card.style.borderColor = '#334155'; card.style.transform = 'scale(1)'; };

            card.onclick = () => {
                if (this.activePickingSegmentId !== null) {
                    const seg = this.segments.find(s => s.id === this.activePickingSegmentId);
                    if (seg) {
                        seg.panel_id = p.id;
                        seg.panel_filename = p.filename;
                        seg.panel_url = p.thumb_url;
                        this.render4ColumnTable();
                    }
                    this.closeGalleryModal();
                }
            };

            this.galleryGrid.appendChild(card);
        });
    }

    async startRenderVideo() {
        if (!this.segments || this.segments.length === 0) {
            if (typeof showAlertModal === 'function') {
                showAlertModal('Chưa có phân cảnh', 'Vui lòng hoàn thành kịch bản review ở Bước 2 trước khi bấm tạo video!');
            } else {
                alert('Vui lòng tạo kịch bản phân cảnh trước!');
            }
            return;
        }

        if (typeof checkFeaturePermission === 'function') {
            const allowed = await checkFeaturePermission('can_access_review', 'Xuất Video Review Truyện Tranh');
            if (!allowed) return;
        }

        this.showProgress(true, "Đang khởi tạo luồng ghép ảnh, voice và render video...", 2, "DỰNG PHIM");
        this.showRenderProgress(true, "Đang khởi tạo luồng dựng phim và render video...", 2, "[1/4 DỰNG CẢNH]");
        this.btnRenderVideo.disabled = true;
        this.btnStopRender.style.display = 'inline-block';
        if (this.resultContainer) this.resultContainer.style.display = 'none';

        const storage = this.getStorageInfo();
        const payload = {
            session_id: this.sessionId,
            segments: this.segments,
            aspect_ratio: this.selectAspect.value,
            ken_burns: this.selectKenBurns.value === 'true',
            burn_subs: this.selectBurnSubs.value === 'true',
            output_name: this.inputOutputName.value.trim() || 'comic_review_final.mp4',
            custom_save_dir: storage.custom_save_dir,
            project_folder_name: storage.project_folder_name
        };

        try {
            const resp = await fetch('/api/comic_review/render_video_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const block of lines) {
                    const line = block.trim();
                    if (!line.startsWith('data: ')) continue;
                    const content = line.substring(6).trim();

                    if (content.startsWith('[RENDER_FINISHED]')) {
                        const videoPath = content.substring(17).trim();
                        this.showRenderProgress(true, "🎉 Dựng video hoàn tất thành công!", 100, "[HOÀN TẤT]");
                        this.showProgress(true, "🎉 Dựng video hoàn tất thành công!", 100, "HOÀN TẤT");
                        this.onRenderFinished(videoPath);
                    } else {
                        this.updateProgressUI(content, true);
                    }
                }
            }

            // Xử lý buffer còn lại nếu có
            if (buffer && buffer.trim()) {
                const line = buffer.trim();
                if (line.startsWith('data: ')) {
                    const content = line.substring(6).trim();
                    if (content.startsWith('[RENDER_FINISHED]')) {
                        const videoPath = content.substring(17).trim();
                        this.showRenderProgress(true, "🎉 Dựng video hoàn tất thành công!", 100, "[HOÀN TẤT]");
                        this.showProgress(true, "🎉 Dựng video hoàn tất thành công!", 100, "HOÀN TẤT");
                        this.onRenderFinished(videoPath);
                    } else {
                        this.updateProgressUI(content, true);
                    }
                }
            }
        } catch (err) {
            this.appendLog('🛑 Lỗi render: ' + err.message);
            this.appendRenderLog('🛑 Lỗi render: ' + err.message);
        } finally {
            this.btnRenderVideo.disabled = false;
            this.btnStopRender.style.display = 'none';
        }
    }

    onRenderFinished(videoPath) {
        if (this.resultContainer && this.resultPlayer) {
            this.resultContainer.style.display = 'block';
            this.resultPlayer.src = `/api/download_file?path=${encodeURIComponent(videoPath)}`;
            this.resultPlayer.play().catch(() => {});
            this.resultContainer.scrollIntoView({ behavior: 'smooth' });
        }
        if (typeof showToast === 'function') {
            showToast('🎉 Tạo video Review Truyện thành công!', 'success');
        }
    }

    // ==========================================
    // CROP TOOL & RE-CROP WORKSPACE
    // ==========================================
    initCropToolElements() {
        this.cropModal = document.getElementById('comicCropModal');
        this.cropViewport = document.getElementById('comicCropViewport');
        this.cropWrapper = document.getElementById('comicCropWrapper');
        this.cropImg = document.getElementById('comicCropImg');
        this.cropBox = document.getElementById('comicCropBox');
        this.cropDimBadge = document.getElementById('comicCropDimBadge');
        this.cropBeatBadge = document.getElementById('comicCropBeatBadge');
        this.btnCropSourcePanel = document.getElementById('btnCropSourcePanel');
        this.btnCropSourceRawPage = document.getElementById('btnCropSourceRawPage');
        this.btnCloseCrop = document.getElementById('btnCloseComicCrop');
        this.btnCancelCrop = document.getElementById('btnCancelComicCrop');
        this.btnApplyCrop = document.getElementById('btnApplyComicCrop');
        this.btnCropRotate = document.getElementById('btnCropRotate');
        this.btnCropReset = document.getElementById('btnCropReset');
        this.cropRatioButtons = document.querySelectorAll('.crop-ratio-btn');

        this.cropActiveSeg = null;
        this.cropActiveRow = null;
        this.cropSourceType = 'panel';
        this.cropSourcePage = '';
        this.cropRatio = 'free';
        this.cropRotation = 0;

        this.boxState = {
            left: 0,
            top: 0,
            width: 100,
            height: 100
        };

        this.dragState = {
            isDragging: false,
            type: null,
            startX: 0,
            startY: 0,
            origLeft: 0,
            origTop: 0,
            origWidth: 0,
            origHeight: 0
        };
    }

    initCropToolEvents() {
        if (this.btnCloseCrop) this.btnCloseCrop.addEventListener('click', () => this.closeCropModal());
        if (this.btnCancelCrop) this.btnCancelCrop.addEventListener('click', () => this.closeCropModal());
        if (this.btnApplyCrop) this.btnApplyCrop.addEventListener('click', () => this.applyCrop());
        if (this.btnCropRotate) this.btnCropRotate.addEventListener('click', () => this.rotateCrop());
        if (this.btnCropReset) this.btnCropReset.addEventListener('click', () => this.resetCropBoxToFull());

        if (this.btnCropSourcePanel) {
            this.btnCropSourcePanel.addEventListener('click', () => this.switchCropSource('panel'));
        }
        if (this.btnCropSourceRawPage) {
            this.btnCropSourceRawPage.addEventListener('click', () => this.switchCropSource('raw_page'));
        }

        if (this.cropRatioButtons) {
            this.cropRatioButtons.forEach(btn => {
                btn.addEventListener('click', () => {
                    this.cropRatioButtons.forEach(b => {
                        b.classList.remove('active');
                        b.style.background = '#0b1120';
                        b.style.color = '#cbd5e1';
                        b.style.borderColor = '#334155';
                    });
                    btn.classList.add('active');
                    btn.style.background = '#1e293b';
                    btn.style.color = '#38bdf8';
                    btn.style.borderColor = '#38bdf8';
                    this.cropRatio = btn.dataset.ratio;
                    this.applyRatioConstraint();
                });
            });
        }

        if (this.cropBox) {
            this.cropBox.addEventListener('pointerdown', (e) => {
                e.preventDefault();
                e.stopPropagation();

                const handle = e.target.closest('.crop-handle');
                const dragType = handle ? handle.dataset.handle : 'move';

                this.dragState.isDragging = true;
                this.dragState.type = dragType;
                this.dragState.startX = e.clientX;
                this.dragState.startY = e.clientY;
                this.dragState.origLeft = this.boxState.left;
                this.dragState.origTop = this.boxState.top;
                this.dragState.origWidth = this.boxState.width;
                this.dragState.origHeight = this.boxState.height;

                try { this.cropBox.setPointerCapture(e.pointerId); } catch (_) {}
            });

            this.cropBox.addEventListener('pointermove', (e) => {
                if (!this.dragState.isDragging) return;
                this.handleCropPointerMove(e);
            });

            this.cropBox.addEventListener('pointerup', (e) => {
                if (this.dragState.isDragging) {
                    this.dragState.isDragging = false;
                    try { this.cropBox.releasePointerCapture(e.pointerId); } catch (_) {}
                }
            });

            this.cropBox.addEventListener('pointercancel', () => {
                this.dragState.isDragging = false;
            });
        }

        if (this.cropModal) {
            this.cropModal.addEventListener('click', (e) => {
                if (e.target === this.cropModal) this.closeCropModal();
            });
        }
    }

    handleCropPointerMove(e) {
        if (!this.cropImg) return;
        const dx = e.clientX - this.dragState.startX;
        const dy = e.clientY - this.dragState.startY;

        const maxW = this.cropImg.clientWidth;
        const maxH = this.cropImg.clientHeight;
        if (!maxW || !maxH) return;

        const minSize = 24;
        let { origLeft, origTop, origWidth, origHeight } = this.dragState;

        if (this.dragState.type === 'move') {
            let newL = Math.max(0, Math.min(maxW - origWidth, origLeft + dx));
            let newT = Math.max(0, Math.min(maxH - origHeight, origTop + dy));
            this.setBoxState(newL, newT, origWidth, origHeight);
            return;
        }

        let newL = origLeft;
        let newT = origTop;
        let newW = origWidth;
        let newH = origHeight;

        const type = this.dragState.type;

        if (type.includes('e')) newW = Math.max(minSize, Math.min(maxW - origLeft, origWidth + dx));
        if (type.includes('s')) newH = Math.max(minSize, Math.min(maxH - origTop, origHeight + dy));
        if (type.includes('w')) {
            const rawL = origLeft + dx;
            newL = Math.max(0, Math.min(origLeft + origWidth - minSize, rawL));
            newW = origWidth + (origLeft - newL);
        }
        if (type.includes('n')) {
            const rawT = origTop + dy;
            newT = Math.max(0, Math.min(origTop + origHeight - minSize, rawT));
            newH = origHeight + (origTop - newT);
        }

        if (this.cropRatio !== 'free') {
            const [rw, rh] = this.getRatioNumbers(this.cropRatio);
            const targetRatio = rw / rh;

            if (type === 'e' || type === 'w') {
                newH = newW / targetRatio;
                if (newT + newH > maxH) {
                    newH = maxH - newT;
                    newW = newH * targetRatio;
                }
            } else {
                newW = newH * targetRatio;
                if (newL + newW > maxW) {
                    newW = maxW - newL;
                    newH = newW / targetRatio;
                }
            }
        }

        this.setBoxState(newL, newT, newW, newH);
    }

    getRatioNumbers(ratioStr) {
        if (ratioStr === '9:16') return [9, 16];
        if (ratioStr === '16:9') return [16, 9];
        if (ratioStr === '1:1') return [1, 1];
        if (ratioStr === '3:4') return [3, 4];
        if (ratioStr === '4:3') return [4, 3];
        return [1, 1];
    }

    applyRatioConstraint() {
        if (this.cropRatio === 'free' || !this.cropImg) return;
        const [rw, rh] = this.getRatioNumbers(this.cropRatio);
        const targetR = rw / rh;

        const maxW = this.cropImg.clientWidth;
        const maxH = this.cropImg.clientHeight;
        if (!maxW || !maxH) return;

        let curW = this.boxState.width;
        let curH = curW / targetR;

        if (curH > maxH || this.boxState.top + curH > maxH) {
            curH = Math.min(maxH, this.boxState.height);
            curW = curH * targetR;
        }
        if (curW > maxW) {
            curW = maxW;
            curH = curW / targetR;
        }

        let curL = Math.max(0, Math.min(maxW - curW, this.boxState.left));
        let curT = Math.max(0, Math.min(maxH - curH, this.boxState.top));

        this.setBoxState(curL, curT, curW, curH);
    }

    setBoxState(left, top, width, height) {
        this.boxState.left = Math.round(left);
        this.boxState.top = Math.round(top);
        this.boxState.width = Math.round(width);
        this.boxState.height = Math.round(height);

        if (this.cropBox) {
            this.cropBox.style.left = `${this.boxState.left}px`;
            this.cropBox.style.top = `${this.boxState.top}px`;
            this.cropBox.style.width = `${this.boxState.width}px`;
            this.cropBox.style.height = `${this.boxState.height}px`;
        }

        this.updateCropDimBadge();
    }

    updateCropDimBadge() {
        if (!this.cropDimBadge || !this.cropImg) return;
        const nw = this.cropImg.naturalWidth || 1;
        const nh = this.cropImg.naturalHeight || 1;
        const cw = this.cropImg.clientWidth || 1;
        const ch = this.cropImg.clientHeight || 1;

        const realW = Math.round(this.boxState.width * (nw / cw));
        const realH = Math.round(this.boxState.height * (nh / ch));
        this.cropDimBadge.textContent = `${realW} × ${realH} px`;
    }

    openCropModal(seg, row) {
        this.cropActiveSeg = seg;
        this.cropActiveRow = row;
        this.cropSourceType = 'panel';
        this.cropRotation = 0;

        if (this.cropBeatBadge) {
            this.cropBeatBadge.textContent = `Phân cảnh #${seg.id}`;
        }

        let sourcePage = seg.source_page || '';
        if (!sourcePage && this.panels) {
            const p = this.panels.find(x => x.id === seg.panel_id || x.filename === seg.panel_filename);
            if (p && p.source_page) sourcePage = p.source_page;
        }
        this.cropSourcePage = sourcePage;

        if (this.btnCropSourceRawPage) {
            if (this.cropSourcePage) {
                this.btnCropSourceRawPage.style.display = 'inline-block';
                this.btnCropSourceRawPage.title = `Cắt lại từ trang gốc: ${this.cropSourcePage}`;
            } else {
                this.btnCropSourceRawPage.style.display = 'none';
            }
        }

        this.updateSourceButtonsState();
        this.loadCropImage();

        if (this.cropModal) {
            this.cropModal.style.display = 'flex';
        }
    }

    closeCropModal() {
        if (this.cropModal) {
            this.cropModal.style.display = 'none';
        }
        this.cropActiveSeg = null;
        this.cropActiveRow = null;
    }

    updateSourceButtonsState() {
        if (!this.btnCropSourcePanel || !this.btnCropSourceRawPage) return;
        if (this.cropSourceType === 'panel') {
            this.btnCropSourcePanel.style.background = '#38bdf8';
            this.btnCropSourcePanel.style.color = '#020617';
            this.btnCropSourceRawPage.style.background = 'transparent';
            this.btnCropSourceRawPage.style.color = '#cbd5e1';
        } else {
            this.btnCropSourceRawPage.style.background = '#38bdf8';
            this.btnCropSourceRawPage.style.color = '#020617';
            this.btnCropSourcePanel.style.background = 'transparent';
            this.btnCropSourcePanel.style.color = '#cbd5e1';
        }
    }

    switchCropSource(type) {
        if (type === 'raw_page' && !this.cropSourcePage) {
            if (typeof showToast === 'function') showToast('Không tìm thấy tệp trang truyện gốc!', 'warning');
            return;
        }
        this.cropSourceType = type;
        this.cropRotation = 0;
        this.updateSourceButtonsState();
        this.loadCropImage();
    }

    loadCropImage() {
        if (!this.cropActiveSeg || !this.cropImg) return;
        const storage = this.getStorageInfo();
        const extraQ = [];
        if (storage.custom_save_dir) extraQ.push(`custom_save_dir=${encodeURIComponent(storage.custom_save_dir)}`);
        if (storage.project_folder_name) extraQ.push(`project_folder_name=${encodeURIComponent(storage.project_folder_name)}`);
        const extraStr = extraQ.length ? ('?' + extraQ.join('&')) : '';

        let srcUrl = '';
        if (this.cropSourceType === 'raw_page' && this.cropSourcePage) {
            srcUrl = `/api/comic_review/media/${this.sessionId}/raw_pages/${this.cropSourcePage}${extraStr}`;
        } else {
            const filename = this.cropActiveSeg.panel_filename;
            const sep = extraStr ? '&' : '?';
            srcUrl = `/api/comic_review/media/${this.sessionId}/panels/${filename}${extraStr}${sep}t=${Date.now()}`;
        }

        if (this.cropBox) this.cropBox.style.display = 'none';
        this.cropImg.style.transform = `rotate(${this.cropRotation}deg)`;
        this.cropImg.onload = () => {
            requestAnimationFrame(() => {
                this.resetCropBoxToFull();
                if (this.cropBox) this.cropBox.style.display = 'block';
            });
        };
        this.cropImg.src = srcUrl;
    }

    resetCropBoxToFull() {
        if (!this.cropImg) return;
        const cw = this.cropImg.clientWidth;
        const ch = this.cropImg.clientHeight;
        if (!cw || !ch) return;

        const marginW = Math.round(cw * 0.05);
        const marginH = Math.round(ch * 0.05);
        const w = cw - marginW * 2;
        const h = ch - marginH * 2;

        this.setBoxState(marginW, marginH, w, h);
        if (this.cropRatio !== 'free') {
            this.applyRatioConstraint();
        }
    }

    rotateCrop() {
        this.cropRotation = (this.cropRotation + 90) % 360;
        if (this.cropImg) {
            this.cropImg.style.transform = `rotate(${this.cropRotation}deg)`;
        }
    }

    async applyCrop() {
        if (!this.cropActiveSeg || !this.cropImg) return;
        const seg = this.cropActiveSeg;
        const row = this.cropActiveRow;

        const cw = this.cropImg.clientWidth || 1;
        const ch = this.cropImg.clientHeight || 1;
        const nw = this.cropImg.naturalWidth || 1;
        const nh = this.cropImg.naturalHeight || 1;

        const scaleX = nw / cw;
        const scaleY = nh / ch;

        const cropX = this.boxState.left * scaleX;
        const cropY = this.boxState.top * scaleY;
        const cropW = this.boxState.width * scaleX;
        const cropH = this.boxState.height * scaleY;

        if (this.btnApplyCrop) {
            this.btnApplyCrop.disabled = true;
            this.btnApplyCrop.innerHTML = '<span>⏳ Đang cắt...</span>';
        }

        try {
            const storage = this.getStorageInfo();
            const sourceFilename = (this.cropSourceType === 'raw_page') ? this.cropSourcePage : seg.panel_filename;

            const resp = await fetch('/api/comic_review/crop_panel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    custom_save_dir: storage.custom_save_dir,
                    project_folder_name: storage.project_folder_name,
                    beat_id: seg.id,
                    source_type: this.cropSourceType,
                    source_filename: sourceFilename,
                    panel_path: seg.panel_path,
                    x: Math.round(cropX),
                    y: Math.round(cropY),
                    width: Math.round(cropW),
                    height: Math.round(cropH),
                    rotate: this.cropRotation
                })
            });

            const data = await resp.json();
            if (data.success && data.panel_url) {
                seg.panel_filename = data.panel_filename;
                seg.panel_path = data.panel_path;
                seg.panel_url = data.panel_url;

                if (row) {
                    const img = row.querySelector('img');
                    if (img) img.src = data.panel_url;
                    const nameSpan = row.querySelector('span[title]');
                    if (nameSpan) {
                        nameSpan.textContent = data.panel_filename;
                        nameSpan.title = data.panel_filename;
                    }
                }

                if (typeof showToast === 'function') {
                    showToast(`✨ Đã cắt & cập nhật khung ô tranh phân cảnh #${seg.id} thành công!`, 'success');
                }
                this.closeCropModal();
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.error || 'Lỗi khi cắt ảnh', 'error');
                }
            }
        } catch (e) {
            if (typeof showToast === 'function') {
                showToast('Lỗi: ' + e.message, 'error');
            }
        } finally {
            if (this.btnApplyCrop) {
                this.btnApplyCrop.disabled = false;
                this.btnApplyCrop.innerHTML = '<span>💾 Áp Dụng Khung Cắt</span>';
            }
        }
    }

    async stopCurrentTask() {
        try {
            await fetch('/api/comic_review/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.sessionId })
            });
            this.appendLog('🛑 Đã gửi lệnh dừng xử lý...');
        } catch (e) {
            console.error(e);
        }
    }

    async openOutputFolder() {
        try {
            await fetch('/api/open_output_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subfolder: 'comic_reviews' })
            });
        } catch (e) {
            console.error(e);
        }
    }
}

// Khởi tạo khi DOM sẵn sàng
document.addEventListener('DOMContentLoaded', () => {
    window.comicReviewManager = new ComicReviewManager();
});
