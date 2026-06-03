/* DownTube v2.0 - Frontend JavaScript */

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const urlInput = document.getElementById('urlInput');
    const pasteBtn = document.getElementById('pasteBtn');
    const infoBtn = document.getElementById('infoBtn');
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
    const videoThumbnail = document.getElementById('videoThumbnail');
    const videoTitle = document.getElementById('videoTitle');
    const videoDuration = document.getElementById('videoDuration');
    const videoQuality = document.getElementById('videoQuality');
    const videoSubtitles = document.getElementById('videoSubtitles');
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
    infoBtn.addEventListener('click', fetchVideoInfo);
    downloadBtn.addEventListener('click', startDownload);
    cancelBtn.addEventListener('click', cancelDownload);
    refreshBtn.addEventListener('click', loadDownloads);

    urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            if (isDownloading) return;
            const url = urlInput.value.trim();
            if (isYouTubeUrl(url)) {
                startDownload();
            }
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
            urlInput.focus();
        }
    }

    async function fetchVideoInfo() {
        const url = urlInput.value.trim();
        if (!url || !isYouTubeUrl(url)) return;

        infoBtn.textContent = '⏳';
        infoBtn.disabled = true;

        try {
            const res = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            const data = await res.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            // Show video preview
            videoPreview.classList.remove('hidden');
            if (data.thumbnail) {
                videoThumbnail.src = data.thumbnail;
                videoThumbnail.onerror = () => { videoThumbnail.style.display = 'none'; };
            }
            videoTitle.textContent = data.title || 'بدون عنوان';
            videoDuration.textContent = data.duration_str || '';
            videoQuality.textContent = data.best_quality || '';

            // Subtitle info
            const subs = data.subtitles || {};
            if (subs.has_manual_arabic) {
                videoSubtitles.textContent = 'ترجمة عربية يدوية ✅';
                videoSubtitles.className = 'sub-badge available';
            } else if (subs.has_auto_arabic) {
                videoSubtitles.textContent = 'ترجمة عربية تلقائية ✅';
                videoSubtitles.className = 'sub-badge available';
            } else {
                videoSubtitles.textContent = 'لا توجد ترجمة عربية ⚠️';
                videoSubtitles.className = 'sub-badge';
            }

            // Enable download button
            downloadBtn.disabled = false;

        } catch (err) {
            showError('فشل فحص الفيديو');
        } finally {
            infoBtn.textContent = '🔍';
            infoBtn.disabled = false;
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
        const pct = Math.min(data.progress_percent || 0, 100);
        progressPercent.textContent = pct.toFixed(1) + '%';
        progressBar.style.width = pct + '%';
        progressSpeed.textContent = 'السرعة: ' + (data.speed || '--');
        progressEta.textContent = 'المتبقي: ' + (data.eta || '--');
        progressSize.textContent = (data.downloaded_str || '0') + ' / ' + (data.total_str || '--');
    }

    function updateSubtitleStatus(data) {
        if (!data.subtitle_status) return;

        if (data.subtitle_status === 'found') {
            subtitleInfo.textContent = data.subtitle_info || 'تم العثور على ترجمة عربية';
            subtitleSection.className = 'subtitle-section found';
        } else if (data.subtitle_status === 'not_found') {
            subtitleInfo.textContent = data.subtitle_info || 'لا توجد ترجمات عربية - سيتم تحميل الفيديو بدون ترجمة';
            subtitleSection.className = 'subtitle-section not-found';
        } else if (data.subtitle_status === 'downloading') {
            subtitleInfo.textContent = 'جاري تحميل الترجمة العربية مع الفيديو...';
            subtitleSection.className = 'subtitle-section';
        } else if (data.subtitle_status === 'embedded') {
            subtitleInfo.textContent = data.subtitle_info || 'تم تضمين الترجمة العربية في الفيديو ✅';
            subtitleSection.className = 'subtitle-section embedded';
        } else if (data.subtitle_status === 'failed') {
            subtitleInfo.textContent = data.subtitle_info || 'فشل تحميل الترجمة العربية';
            subtitleSection.className = 'subtitle-section not-found';
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
            details += `<div class="result-detail">📁 الفيديو: <code>${data.video_path}</code></div>`;
        }
        if (data.subtitle_path) {
            details += `<div class="result-detail">🔤 الترجمة: <code>${data.subtitle_path}</code></div>`;
        }
        if (data.subtitle_info) {
            const subClass = data.subtitle_status === 'embedded' ? 'success' : 'warning';
            details += `<div class="result-detail result-${subClass}">📝 ${data.subtitle_info}</div>`;
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
                            <div class="download-item-meta">
                                ${f.size} • ${new Date(f.modified).toLocaleString('ar')}
                                ${f.is_arabic ? ' • 🇸🇦 ترجمة عربية' : ''}
                            </div>
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
