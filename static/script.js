/* DownTube - Frontend JavaScript */

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const urlInput = document.getElementById('urlInput');
    const pasteBtn = document.getElementById('pasteBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const downloadDirInput = document.getElementById('downloadDirInput');
    const progressSection = document.getElementById('progressSection');
    const progressStage = document.getElementById('progressStage');
    const progressPercent = document.getElementById('progressPercent');
    const progressBar = document.getElementById('progressBar');
    const progressSpeed = document.getElementById('progressSpeed');
    const progressEta = document.getElementById('progressEta');
    const progressSize = document.getElementById('progressSize');
    const subtitleSection = document.getElementById('subtitleSection');
    const subtitleInfo = document.getElementById('subtitleInfo');
    const resultSection = document.getElementById('resultSection');
    const resultContent = document.getElementById('resultContent');
    const videoPreview = document.getElementById('videoPreview');
    const refreshBtn = document.getElementById('refreshBtn');
    const downloadsList = document.getElementById('downloadsList');

    // Status bar elements
    const ffmpegStatus = document.getElementById('ffmpegStatus');
    const ytdlpStatus = document.getElementById('ytdlpStatus');
    const downloadDirText = document.getElementById('downloadDirText');

    let isDownloading = false;
    let eventSource = null;

    // Initialize
    checkStatus();
    loadDownloads();

    // Event Listeners
    urlInput.addEventListener('input', onUrlInput);
    pasteBtn.addEventListener('click', pasteFromClipboard);
    downloadBtn.addEventListener('click', startDownload);
    cancelBtn.addEventListener('click', cancelDownload);
    refreshBtn.addEventListener('click', loadDownloads);

    urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && downloadBtn.disabled === false) {
            startDownload();
        }
    });

    // Functions
    async function checkStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            // Update FFmpeg status
            const ffmpegDot = ffmpegStatus.querySelector('.status-dot');
            if (data.ffmpeg.available) {
                ffmpegDot.classList.add('active');
                ffmpegDot.classList.remove('inactive');
            } else {
                ffmpegDot.classList.add('inactive');
                ffmpegDot.classList.remove('active');
            }

            // Update yt-dlp status
            const ytdlpDot = ytdlpStatus.querySelector('.status-dot');
            if (data.ytdlp.available) {
                ytdlpDot.classList.add('active');
                ytdlpDot.classList.remove('inactive');
            } else {
                ytdlpDot.classList.add('inactive');
                ytdlpDot.classList.remove('active');
            }

            // Update download dir
            if (data.download_dir) {
                downloadDirText.textContent = data.download_dir;
                downloadDirInput.value = data.download_dir;
            }
        } catch (err) {
            console.error('Status check failed:', err);
        }
    }

    function onUrlInput() {
        const url = urlInput.value.trim();
        const isValid = isYouTubeUrl(url);
        downloadBtn.disabled = !isValid || isDownloading;

        // Reset preview and results when URL changes
        videoPreview.classList.add('hidden');
        resultSection.classList.add('hidden');
    }

    function isYouTubeUrl(url) {
        const patterns = [
            /^https?:\/\/(www\.)?youtube\.com\/watch\?v=/,
            /^https?:\/\/(www\.)?youtube\.com\/shorts\//,
            /^https?:\/\/youtu\.be\//,
            /^https?:\/\/(www\.)?youtube\.com\/embed\//,
            /^https?:\/\/m\.youtube\.com\/watch\?v=/,
        ];
        return patterns.some(p => p.test(url));
    }

    async function pasteFromClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            urlInput.value = text;
            onUrlInput();
        } catch (err) {
            // Clipboard API might not be available
            urlInput.focus();
        }
    }

    async function startDownload() {
        const url = urlInput.value.trim();
        if (!url || !isYouTubeUrl(url)) return;

        isDownloading = true;
        downloadBtn.classList.add('hidden');
        cancelBtn.classList.remove('hidden');
        progressSection.classList.remove('hidden');
        subtitleSection.classList.remove('hidden');
        resultSection.classList.add('hidden');
        videoPreview.classList.add('hidden');

        // Reset progress
        updateProgress({
            status: 'downloading',
            progress_percent: 0,
            speed: 0,
            eta: 0,
            downloaded_bytes: 0,
            total_bytes: 0,
            stage: 'جاري التحضير...',
        });

        subtitleInfo.textContent = 'جاري البحث عن الترجمة العربية...';
        subtitleSection.className = 'subtitle-section';

        // Update download dir if changed
        const downloadDir = downloadDirInput.value.trim();

        try {
            const res = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, download_dir: downloadDir || undefined }),
            });

            const data = await res.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            // Start listening for progress events
            startProgressListener();

        } catch (err) {
            showError('فشل الاتصال بالخادم');
        }
    }

    function startProgressListener() {
        if (eventSource) {
            eventSource.close();
        }

        eventSource = new EventSource('/api/progress');

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'done') {
                    eventSource.close();
                    eventSource = null;
                    return;
                }

                updateProgress(data);
                updateSubtitleStatus(data);

                if (data.status === 'complete') {
                    onDownloadComplete(data);
                } else if (data.status === 'error') {
                    showError(data.error);
                }
            } catch (err) {
                console.error('Progress parse error:', err);
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            eventSource = null;
        };
    }

    function updateProgress(data) {
        progressStage.textContent = data.stage || 'جاري التحميل...';
        progressPercent.textContent = data.progress_percent + '%';
        progressBar.style.width = data.progress_percent + '%';
        progressSpeed.textContent = 'السرعة: ' + (data.speed || '--');
        progressEta.textContent = 'المتبقي: ' + (data.eta || '--');
        progressSize.textContent = (data.downloaded_str || '0') + ' / ' + (data.total_str || '--');
    }

    function updateSubtitleStatus(data) {
        if (data.subtitle_status === 'found') {
            subtitleInfo.textContent = data.subtitle_info || 'تم العثور على ترجمة عربية';
            subtitleSection.className = 'subtitle-section found';
        } else if (data.subtitle_status === 'not_found') {
            subtitleInfo.textContent = data.subtitle_info || 'لا توجد ترجمات عربية - سيتم تحميل الفيديو بدون ترجمة';
            subtitleSection.className = 'subtitle-section not-found';
        } else if (data.subtitle_status === 'downloading') {
            subtitleInfo.textContent = 'جاري تحميل الترجمة العربية...';
            subtitleSection.className = 'subtitle-section';
        } else if (data.subtitle_status === 'embedded') {
            subtitleInfo.textContent = data.subtitle_info || 'تم تضمين الترجمة العربية في الفيديو ✅';
            subtitleSection.className = 'subtitle-section embedded';
        }
    }

    function onDownloadComplete(data) {
        isDownloading = false;
        downloadBtn.classList.remove('hidden');
        cancelBtn.classList.add('hidden');
        downloadBtn.disabled = false;

        resultSection.classList.remove('hidden', 'error');
        resultSection.classList.add('success');

        let details = '';
        if (data.video_path) {
            details += `<div>📁 الفيديو: ${data.video_path}</div>`;
        }
        if (data.subtitle_path) {
            details += `<div>🔤 الترجمة: ${data.subtitle_path}</div>`;
        }

        resultContent.innerHTML = `
            <div class="result-icon">✅</div>
            <div class="result-title">اكتمل التحميل بنجاح!</div>
            <div class="result-details">${details}</div>
        `;

        loadDownloads();
    }

    function showError(errorMsg) {
        isDownloading = false;
        downloadBtn.classList.remove('hidden');
        cancelBtn.classList.add('hidden');
        downloadBtn.disabled = false;

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        resultSection.classList.remove('hidden', 'success');
        resultSection.classList.add('error');

        resultContent.innerHTML = `
            <div class="result-icon">❌</div>
            <div class="result-title">فشل التحميل</div>
            <div class="result-details">${errorMsg || 'حدث خطأ غير معروف'}</div>
        `;
    }

    async function cancelDownload() {
        try {
            await fetch('/api/cancel', { method: 'POST' });
        } catch (err) {
            // Ignore
        }

        isDownloading = false;
        downloadBtn.classList.remove('hidden');
        cancelBtn.classList.add('hidden');
        downloadBtn.disabled = false;

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        progressSection.classList.add('hidden');
        resultSection.classList.remove('hidden', 'success');
        resultSection.classList.add('error');

        resultContent.innerHTML = `
            <div class="result-icon">⛔</div>
            <div class="result-title">تم إلغاء التحميل</div>
            <div class="result-details">تم إلغاء التحميل بواسطة المستخدم</div>
        `;
    }

    async function loadDownloads() {
        try {
            const res = await fetch('/api/downloads');
            const data = await res.json();

            if (data.files && data.files.length > 0) {
                downloadsList.innerHTML = data.files.map(f => `
                    <div class="download-item">
                        <span class="download-item-icon">${f.type === 'video' ? '🎬' : '🔤'}</span>
                        <div class="download-item-info">
                            <div class="download-item-name">${f.name}</div>
                            <div class="download-item-meta">${f.size} • ${new Date(f.modified).toLocaleString('ar')}</div>
                        </div>
                    </div>
                `).join('');
            } else {
                downloadsList.innerHTML = '<p class="empty-message">لا توجد ملفات محملة بعد</p>';
            }

            // Update download dir
            if (data.download_dir) {
                downloadDirText.textContent = data.download_dir;
            }
        } catch (err) {
            downloadsList.innerHTML = '<p class="empty-message">فشل تحميل قائمة الملفات</p>';
        }
    }
});
