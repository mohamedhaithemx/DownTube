/**
 * YouTube Downloader - Desktop Web UI
 * واجهة المستخدم لتحميل فيديوهات يوتيوب
 */

class YouTubeDownloaderApp {
    constructor() {
        this.ws = null;
        this.currentVideoUrl = '';
        this.isDownloading = false;
        this.reconnectAttempts = 0;

        this.initElements();
        this.initWebSocket();
        this.bindEvents();
    }

    initElements() {
        // URL Input
        this.urlInput = document.getElementById('videoUrl');
        this.btnPaste = document.getElementById('btnPaste');
        this.btnFetchInfo = document.getElementById('btnFetchInfo');

        // Video Info
        this.videoInfoSection = document.getElementById('videoInfoSection');
        this.videoThumbnail = document.getElementById('videoThumbnail');
        this.videoDuration = document.getElementById('videoDuration');
        this.videoTitle = document.getElementById('videoTitle');
        this.videoUploader = document.getElementById('videoUploader');
        this.videoViews = document.getElementById('videoViews');
        this.videoDescription = document.getElementById('videoDescription');

        // Download Options
        this.downloadOptionsSection = document.getElementById('downloadOptionsSection');
        this.autoSubtitle = document.getElementById('autoSubtitle');

        // Progress
        this.progressSection = document.getElementById('progressSection');
        this.progressTitle = document.getElementById('progressTitle');
        this.progressFill = document.getElementById('progressFill');
        this.progressPercent = document.getElementById('progressPercent');
        this.progressSpeed = document.getElementById('progressSpeed');
        this.progressEta = document.getElementById('progressEta');
        this.progressMessage = document.getElementById('progressMessage');

        // Steps
        this.steps = {
            step1: document.getElementById('step1'),
            step2: document.getElementById('step2'),
            step3: document.getElementById('step3'),
            step4: document.getElementById('step4'),
        };
        this.connectors = document.querySelectorAll('.step-connector');

        // Buttons
        this.btnDownloadFull = document.getElementById('btnDownloadFull');
        this.btnDownloadSubtitleOnly = document.getElementById('btnDownloadSubtitleOnly');
        this.btnDownloadVideoOnly = document.getElementById('btnDownloadVideoOnly');
        this.btnCancel = document.getElementById('btnCancel');
        this.btnViewDownloads = document.getElementById('btnViewDownloads');
        this.btnAntiBanStatus = document.getElementById('btnAntiBanStatus');

        // Completed
        this.completedSection = document.getElementById('completedSection');
        this.completedFiles = document.getElementById('completedFiles');

        // Modals
        this.downloadsModal = document.getElementById('downloadsModal');
        this.antiBanModal = document.getElementById('antiBanModal');
        this.downloadsList = document.getElementById('downloadsList');
        this.antiBanInfo = document.getElementById('antiBanInfo');

        // Cookies
        this.cookiesPasteArea = document.getElementById('cookiesPasteArea');
        this.btnCookiesSave = document.getElementById('btnCookiesSave');
        this.btnCookiesClear = document.getElementById('btnCookiesClear');
        this.btnCookiesChooseFile = document.getElementById('btnCookiesChooseFile');
        this.btnCookiesPaste = document.getElementById('btnCookiesPaste');
        this.cookiesFileInput = document.getElementById('cookiesFileInput');
        this.cookiesFileName = document.getElementById('cookiesFileName');
        this.cookiesBadge = document.getElementById('cookiesBadge');
        this.cookiesStatusBar = document.getElementById('cookiesStatusBar');
        this.cookiesStatusText = document.getElementById('cookiesStatusText');
        this.cookiesStatusSize = document.getElementById('cookiesStatusSize');
        this.cookiesDetectMessage = document.getElementById('cookiesDetectMessage');
    }

    initWebSocket() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            // Keep alive
            this.wsPing = setInterval(() => {
                if (this.ws?.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (e) {
                console.error('WS message parse error:', e);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket closed');
            clearInterval(this.wsPing);
            this.ws = null;
            // Reconnect after delay
            setTimeout(() => {
                this.reconnectAttempts++;
                if (this.reconnectAttempts < 10) {
                    this.initWebSocket();
                }
            }, 3000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'progress':
                this.updateProgress(data);
                break;
            case 'download_complete':
                this.onDownloadComplete(data);
                break;
            case 'download_error':
                this.onDownloadError(data.error);
                break;
            case 'pong':
                break;
        }
    }

    bindEvents() {
        // Paste button
        this.btnPaste.addEventListener('click', () => this.pasteFromClipboard());

        // Fetch info
        this.btnFetchInfo.addEventListener('click', () => this.fetchVideoInfo());
        this.urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.fetchVideoInfo();
        });

        // Download buttons
        this.btnDownloadFull.addEventListener('click', () => this.startDownload('full'));
        this.btnDownloadSubtitleOnly.addEventListener('click', () => this.startDownload('subtitle'));
        this.btnDownloadVideoOnly.addEventListener('click', () => this.startDownload('video'));
        this.btnCancel.addEventListener('click', () => this.cancelDownload());

        // Modals
        this.btnViewDownloads.addEventListener('click', () => this.showDownloadsModal());
        document.getElementById('btnCloseModal').addEventListener('click', () => {
            this.downloadsModal.style.display = 'none';
        });
        this.btnAntiBanStatus.addEventListener('click', () => this.showAntiBanModal());
        document.getElementById('btnCloseAntiBan').addEventListener('click', () => {
            this.antiBanModal.style.display = 'none';
        });
        document.getElementById('btnResetAntiBan').addEventListener('click', () => this.resetAntiBan());

        // Close modal on backdrop click
        this.downloadsModal.addEventListener('click', (e) => {
            if (e.target === this.downloadsModal) this.downloadsModal.style.display = 'none';
        });
        this.antiBanModal.addEventListener('click', (e) => {
            if (e.target === this.antiBanModal) this.antiBanModal.style.display = 'none';
        });

        // Cookies
        this.btnCookiesSave.addEventListener('click', () => this.saveCookies());
        this.btnCookiesClear.addEventListener('click', () => this.clearCookies());
        this.btnCookiesChooseFile.addEventListener('click', () => this.cookiesFileInput.click());
        this.btnCookiesPaste.addEventListener('click', () => this.pasteCookiesFromClipboard());
        this.cookiesFileInput.addEventListener('change', (e) => this.uploadCookiesFile(e));
        this.cookiesPasteArea.addEventListener('input', () => this.detectCookiesContent());
    }

    async pasteFromClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            this.urlInput.value = text;
            this.urlInput.focus();
        } catch {
            this.showToast('لا يمكن الوصول إلى الحافظة', 'error');
        }
    }

    async fetchVideoInfo() {
        const url = this.urlInput.value.trim();
        if (!url) {
            this.showToast('الرجاء إدخال رابط يوتيوب', 'error');
            return;
        }

        if (!this.isValidYouTubeUrl(url)) {
            this.showToast('رابط يوتيوب غير صالح', 'error');
            return;
        }

        this.currentVideoUrl = url;
        this.btnFetchInfo.disabled = true;
        this.btnFetchInfo.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>جاري البحث...</span>';

        try {
            const response = await fetch(`/api/video/info?url=${encodeURIComponent(url)}`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'فشل جلب معلومات الفيديو');
            }

            const info = await response.json();
            this.displayVideoInfo(info);
            this.showToast('تم جلب معلومات الفيديو بنجاح', 'success');

        } catch (error) {
            this.showToast(error.message || 'فشل جلب المعلومات', 'error');
        } finally {
            this.btnFetchInfo.disabled = false;
            this.btnFetchInfo.innerHTML = '<i class="fas fa-search"></i> <span>بحث</span>';
        }
    }

    displayVideoInfo(info) {
        this.videoThumbnail.src = info.thumbnail || '';
        this.videoDuration.textContent = this.formatDuration(info.duration);
        this.videoTitle.textContent = info.title;
        this.videoUploader.textContent = info.uploader || '';
        this.videoViews.textContent = info.view_count ? this.formatViews(info.view_count) : '';
        this.videoDescription.textContent = info.description || '';

        this.videoInfoSection.style.display = 'block';
        this.downloadOptionsSection.style.display = 'block';

        // Smooth scroll to info
        this.videoInfoSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async startDownload(type) {
        if (!this.currentVideoUrl) {
            this.showToast('الرجاء البحث عن فيديو أولاً', 'error');
            return;
        }

        const subtitleLang = document.querySelector('input[name="subtitleLang"]:checked')?.value || 'ar';
        const subtitleFormat = document.querySelector('input[name="subtitleFormat"]:checked')?.value || 'srt';
        const videoQuality = document.querySelector('input[name="videoQuality"]:checked')?.value || 'best';

        this.isDownloading = true;
        this.resetSteps();

        // Show progress section
        this.progressSection.style.display = 'block';
        this.completedSection.style.display = 'none';
        this.progressSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Disable download buttons
        this.btnDownloadFull.disabled = true;
        this.btnDownloadSubtitleOnly.disabled = true;
        this.btnDownloadVideoOnly.disabled = true;

        try {
            if (type === 'full') {
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: this.currentVideoUrl,
                        subtitle_lang: subtitleLang,
                        subtitle_format: subtitleFormat,
                        quality: videoQuality,
                        auto_subtitle: this.autoSubtitle.checked,
                    }),
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'فشل بدء التحميل');
                }
            } else if (type === 'video') {
                const params = new URLSearchParams({ url: this.currentVideoUrl, quality: videoQuality });
                const response = await fetch(`/api/download/video?${params}`, { method: 'POST' });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'فشل تحميل الفيديو');
                }

                const result = await response.json();
                this.onDownloadComplete({ video: result.file });
            } else {
                // Subtitle only
                const params = new URLSearchParams({
                    url: this.currentVideoUrl,
                    lang: subtitleLang,
                    format: subtitleFormat,
                    auto: this.autoSubtitle.checked,
                });

                const response = await fetch(`/api/download/subtitle?${params}`, { method: 'POST' });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'فشل تحميل الترجمة');
                }

                const result = await response.json();
                this.onDownloadComplete({ subtitle: result.file });
            }
        } catch (error) {
            this.onDownloadError(error.message);
        } finally {
            this.isDownloading = false;
            this.btnDownloadFull.disabled = false;
            this.btnDownloadSubtitleOnly.disabled = false;
        }
    }

    async cancelDownload() {
        try {
            await fetch('/api/cancel', { method: 'POST' });
            this.showToast('تم إلغاء التحميل', 'info');
            this.progressSection.style.display = 'none';
            this.isDownloading = false;
            this.btnDownloadFull.disabled = false;
            this.btnDownloadSubtitleOnly.disabled = false;
            this.btnDownloadVideoOnly.disabled = false;
        } catch (error) {
            this.showToast('فشل إلغاء التحميل', 'error');
        }
    }

    updateProgress(data) {
        // Update progress bar
        this.progressFill.style.width = `${data.percent}%`;
        this.progressPercent.textContent = `${Math.round(data.percent)}%`;
        this.progressSpeed.textContent = data.speed || '';
        this.progressEta.textContent = data.eta ? `الوقت المتبقي: ${data.eta}` : '';
        this.progressMessage.textContent = data.message || '';

        // Update steps based on status
        this.updateSteps(data.status);
    }

    updateSteps(status) {
        const stepMap = {
            'fetching_info': 1,
            'downloading_subtitle': 2,
            'waiting_anti_ban': 3,
            'downloading_video': 4,
        };

        const currentStep = stepMap[status] || 0;

        Object.entries(this.steps).forEach(([key, el], index) => {
            const stepNum = index + 1;
            el.classList.remove('active', 'completed');

            if (stepNum < currentStep) {
                el.classList.add('completed');
            } else if (stepNum === currentStep) {
                el.classList.add('active');
            }
        });

        this.connectors.forEach((conn, index) => {
            conn.classList.remove('active', 'completed');
            if (index + 1 < currentStep) {
                conn.classList.add('completed');
            } else if (index + 1 === currentStep) {
                conn.classList.add('active');
            }
        });
    }

    resetSteps() {
        Object.values(this.steps).forEach(el => {
            el.classList.remove('active', 'completed');
        });
        this.connectors.forEach(conn => {
            conn.classList.remove('active', 'completed');
        });
        this.progressFill.style.width = '0%';
        this.progressPercent.textContent = '0%';
        this.progressSpeed.textContent = '';
        this.progressEta.textContent = '';
        this.progressMessage.textContent = '';
    }

    onDownloadComplete(data) {
        this.progressSection.style.display = 'none';
        this.completedSection.style.display = 'block';
        this.completedFiles.innerHTML = '';

        if (data.video) {
            this.addFileItem(data.video, 'video');
        }
        if (data.subtitle) {
            this.addFileItem(data.subtitle, 'subtitle');
        }

        this.showToast('تم التحميل بنجاح!', 'success');
    }

    addFileItem(filepath, type) {
        const filename = filepath.split('/').pop();
        const isVideo = type === 'video';

        const item = document.createElement('div');
        item.className = 'file-item';

        const fileIcon = document.createElement('div');
        fileIcon.className = `file-icon ${type}`;
        const iconEl = document.createElement('i');
        iconEl.className = `fas ${isVideo ? 'fa-film' : 'fa-closed-captioning'}`;
        fileIcon.appendChild(iconEl);

        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        const h4 = document.createElement('h4');
        h4.textContent = filename;
        const p = document.createElement('p');
        p.textContent = isVideo ? 'ملف فيديو' : 'ملف ترجمة';
        fileInfo.appendChild(h4);
        fileInfo.appendChild(p);

        const fileActions = document.createElement('div');
        fileActions.className = 'file-actions';
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn-save';
        const saveIcon = document.createElement('i');
        saveIcon.className = 'fas fa-save';
        saveBtn.appendChild(saveIcon);
        saveBtn.appendChild(document.createTextNode(' حفظ باسم'));
        saveBtn.addEventListener('click', () => this.saveFile(filepath));
        fileActions.appendChild(saveBtn);

        item.appendChild(fileIcon);
        item.appendChild(fileInfo);
        item.appendChild(fileActions);

        this.completedFiles.appendChild(item);
    }

    async saveFile(filepath) {
        // فتح نافذة حفظ باسم عبر تحميل الملف
        const link = document.createElement('a');
        link.href = `/api/download/file?path=${encodeURIComponent(filepath)}`;
        link.download = filepath.split('/').pop();
        link.click();

        this.showToast('جاري حفظ الملف...', 'info');
    }

    onDownloadError(error) {
        this.progressSection.style.display = 'none';
        this.isDownloading = false;
        this.btnDownloadFull.disabled = false;
        this.btnDownloadSubtitleOnly.disabled = false;
        this.btnDownloadVideoOnly.disabled = false;
        this.showToast(error || 'حدث خطأ أثناء التحميل', 'error');
    }

    async showDownloadsModal() {
        try {
            const response = await fetch('/api/downloads');
            const data = await response.json();

            this.downloadsList.innerHTML = '';

            if (data.files.length === 0) {
                this.downloadsList.innerHTML = `
                    <div style="text-align:center; padding:40px; color:var(--text-muted);">
                        <i class="fas fa-inbox" style="font-size:40px; margin-bottom:12px; display:block;"></i>
                        <p>لا توجد ملفات محملة</p>
                    </div>
                `;
            } else {
                data.files.forEach(file => {
                    const isVideo = file.type === 'video';
                    const sizeStr = this.formatFileSize(file.size);

                    const item = document.createElement('div');
                    item.className = 'download-item';

                    const iconDiv = document.createElement('div');
                    iconDiv.className = 'download-item-icon';
                    iconDiv.style.background = isVideo ? 'rgba(255,68,68,0.15)' : 'rgba(68,138,255,0.15)';
                    iconDiv.style.color = isVideo ? 'var(--primary)' : 'var(--info)';
                    const iconI = document.createElement('i');
                    iconI.className = `fas ${isVideo ? 'fa-film' : 'fa-closed-captioning'}`;
                    iconDiv.appendChild(iconI);

                    const infoDiv = document.createElement('div');
                    infoDiv.className = 'download-item-info';
                    const nameH = document.createElement('h4');
                    nameH.textContent = file.name;
                    const sizeP = document.createElement('p');
                    sizeP.textContent = sizeStr;
                    infoDiv.appendChild(nameH);
                    infoDiv.appendChild(sizeP);

                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'download-item-actions';
                    const saveBtn = document.createElement('button');
                    saveBtn.className = 'btn-sm save';
                    const saveI = document.createElement('i');
                    saveI.className = 'fas fa-download';
                    saveBtn.appendChild(saveI);
                    saveBtn.addEventListener('click', () => this.saveFile(file.path));
                    const delBtn = document.createElement('button');
                    delBtn.className = 'btn-sm delete';
                    const delI = document.createElement('i');
                    delI.className = 'fas fa-trash';
                    delBtn.appendChild(delI);
                    delBtn.addEventListener('click', () => this.deleteFile(file.path));
                    actionsDiv.appendChild(saveBtn);
                    actionsDiv.appendChild(delBtn);

                    item.appendChild(iconDiv);
                    item.appendChild(infoDiv);
                    item.appendChild(actionsDiv);

                    this.downloadsList.appendChild(item);
                });
            }

            this.downloadsModal.style.display = 'flex';

        } catch (error) {
            this.showToast('فشل تحميل قائمة الملفات', 'error');
        }
    }

    async deleteFile(filepath) {
        try {
            await fetch(`/api/download/file?path=${encodeURIComponent(filepath)}`, { method: 'DELETE' });
            this.showToast('تم حذف الملف', 'success');
            this.showDownloadsModal();
        } catch {
            this.showToast('فشل حذف الملف', 'error');
        }
    }

    async showAntiBanModal() {
        try {
            const response = await fetch('/api/anti-ban/status');
            const data = await response.json();

            this.antiBanInfo.innerHTML = `
                <div class="anti-ban-item">
                    <label>عدد الطلبات</label>
                    <span>${data.request_count}</span>
                </div>
                <div class="anti-ban-item">
                    <label>محاولات فاشلة</label>
                    <span class="${data.failed_attempts > 0 ? 'status-warning' : 'status-active'}">${data.failed_attempts}</span>
                </div>
                <div class="anti-ban-item">
                    <label>حالة الجلسة</label>
                    <span class="${data.session_active ? 'status-active' : 'status-warning'}">
                        ${data.session_active ? 'نشطة' : 'تحتاج تبريد'}
                    </span>
                </div>
                <div class="anti-ban-item">
                    <label>User-Agent</label>
                    <span style="font-size:11px; max-width:200px; overflow:hidden; text-overflow:ellipsis;">${data.current_user_agent}</span>
                </div>
            `;

            this.antiBanModal.style.display = 'flex';

        } catch {
            this.showToast('فشل جلب حالة الحماية', 'error');
        }
    }

    async resetAntiBan() {
        try {
            await fetch('/api/anti-ban/reset', { method: 'POST' });
            this.showToast('تم إعادة تعيين الجلسة', 'success');
            this.showAntiBanModal();
        } catch {
            this.showToast('فشل إعادة التعيين', 'error');
        }
    }

    // Cookies methods
    async updateCookiesStatus() {
        try {
            const response = await fetch('/api/cookies/status');
            const info = await response.json();

            if (info.active && info.has_youtube) {
                this.cookiesBadge.textContent = 'نشطة ✓';
                this.cookiesBadge.className = 'badge badge-active';
                this.cookiesStatusBar.style.display = 'flex';
                this.cookiesStatusBar.className = 'cookies-status';
                this.cookiesStatusText.textContent = `🍪 كوكيز يوتيوب نشطة — ${info.lines} سطر`;
                this.cookiesStatusSize.textContent = info.size > 0 ? this.formatFileSize(info.size) : '';
            } else {
                this.cookiesBadge.textContent = 'غير نشطة';
                this.cookiesBadge.className = 'badge badge-inactive';
                this.cookiesStatusBar.style.display = 'none';
            }
        } catch {
            this.cookiesBadge.textContent = 'خطأ';
        }
    }

    async pasteCookiesFromClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                this.cookiesPasteArea.value = text;
                this.detectCookiesContent();
                this.showToast('تم لصق المحتوى من الحافظة', 'info');
            }
        } catch {
            this.showToast('لا يمكن الوصول إلى الحافظة', 'error');
        }
    }

    detectCookiesContent() {
        const content = this.cookiesPasteArea.value.trim();
        if (!content) {
            this.cookiesDetectMessage.style.display = 'none';
            return;
        }

        const hasYoutube = content.split('\n').some(line =>
            line.includes('youtube.com') || line.includes('.youtube.com')
        );

        if (hasYoutube) {
            this.cookiesDetectMessage.className = 'cookies-detect success';
            this.cookiesDetectMessage.innerHTML = '🍪 تم الكشف عن كوكيز يوتيوب ✓ جاهز للحفظ';
            this.cookiesDetectMessage.style.display = 'block';
        } else {
            this.cookiesDetectMessage.className = 'cookies-detect error';
            this.cookiesDetectMessage.innerHTML = '⚠️ هذا المحتوى لا يبدو أنه كوكيز يوتيوب';
            this.cookiesDetectMessage.style.display = 'block';
        }
    }

    async saveCookies() {
        const content = this.cookiesPasteArea.value.trim();
        if (!content) {
            this.showToast('الرجاء لصق محتويات الكوكيز أولاً', 'error');
            return;
        }

        this.btnCookiesSave.disabled = true;
        this.btnCookiesSave.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الحفظ...';

        try {
            const response = await fetch('/api/cookies/set', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content }),
            });

            if (response.ok) {
                this.showToast('✅ تم حفظ الكوكيز بنجاح! حد 429 مرتفع الآن', 'success');
                this.cookiesPasteArea.value = '';
                this.cookiesDetectMessage.style.display = 'none';
                await this.updateCookiesStatus();
            } else {
                const err = await response.json();
                this.showToast(err.detail || 'فشل حفظ الكوكيز', 'error');
            }
        } catch {
            this.showToast('خطأ في الاتصال بالخادم', 'error');
        } finally {
            this.btnCookiesSave.disabled = false;
            this.btnCookiesSave.innerHTML = '<i class="fas fa-save"></i> حفظ الكوكيز';
        }
    }

    async clearCookies() {
        try {
            const response = await fetch('/api/cookies/remove', { method: 'DELETE' });
            if (response.ok) {
                this.showToast('🗑️ تم حذف الكوكيز', 'info');
                await this.updateCookiesStatus();
            }
        } catch {
            this.showToast('فشل حذف الكوكيز', 'error');
        }
    }

    async uploadCookiesFile(event) {
        const file = event.target.files[0];
        if (!file) return;

        this.cookiesFileName.textContent = file.name;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/cookies/upload', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                this.showToast('✅ تم رفع الكوكيز بنجاح!', 'success');
                await this.updateCookiesStatus();
            } else {
                const err = await response.json();
                this.showToast(err.detail || 'فشل رفع الكوكيز', 'error');
            }
        } catch {
            this.showToast('خطأ في رفع الملف', 'error');
        }

        // Reset file input
        this.cookiesFileInput.value = '';
    }

    // Utility methods
    isValidYouTubeUrl(url) {
        const patterns = [
            /^https?:\/\/(www\.)?youtube\.com\/watch\?v=/,
            /^https?:\/\/youtu\.be\//,
            /^https?:\/\/(www\.)?youtube\.com\/shorts\//,
            /^https?:\/\/(www\.)?youtube\.com\/embed\//,
            /^https?:\/\/m\.youtube\.com\/watch\?v=/,
        ];
        return patterns.some(pattern => pattern.test(url));
    }

    formatDuration(seconds) {
        if (!seconds) return '0:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    formatViews(count) {
        if (!count) return '0';
        if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
        if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
        return count.toString();
    }

    formatFileSize(bytes) {
        if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`;
        if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
        if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${bytes} B`;
    }

    showToast(message, type = 'info') {
        // Remove existing toast
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            info: 'fa-info-circle',
        };

        toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i> ${message}`;
        document.body.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Initialize app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new YouTubeDownloaderApp();
    // تأخير صغير عشان WebSocket يشتغل أولاً
    setTimeout(() => app.updateCookiesStatus(), 1000);
});
