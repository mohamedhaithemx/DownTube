// DownTube — ZET Dev
// Pure vanilla JS — no frameworks

class App {
  constructor() {
    this.sections = {
      input: document.getElementById('section-input'),
      info: document.getElementById('section-info'),
      progress: document.getElementById('section-progress'),
      result: document.getElementById('section-result'),
      error: document.getElementById('section-error'),
    };
    this.errorCard = document.getElementById('error-card');
    this.errorMessageEl = document.getElementById('error-message');
    this.init();
  }

  init() {
    this.videoInfo = new VideoInfo(this);
    this.downloader = new Downloader(this);
    this.progressTracker = new ProgressTracker(this);
    this.ui = new UIManager(this);
    this.showSection('input');
    this.setupPasteButton();
    document.getElementById('fetch-btn').addEventListener('click', () => this.videoInfo.fetch());
    document.getElementById('download-btn').addEventListener('click', () => this.downloader.start());
    document.getElementById('cancel-btn').addEventListener('click', () => this.downloader.cancel());
    document.getElementById('restart-btn').addEventListener('click', () => this.downloader.restart());
    document.getElementById('result-restart-btn').addEventListener('click', () => this.downloader.restart());
    // زر 'تحميل فيديو جديد' تم حذفه
    document.getElementById('clear-btn').addEventListener('click', () => this._clearVideo());
    document.getElementById('retry-btn').addEventListener('click', () => this.resetUI());
    document.getElementById('url-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.videoInfo.fetch();
    });

    document.getElementById('include-subtitles').addEventListener('change', (e) => {
      const opts = document.getElementById('subtitle-options');
      const mode = document.querySelector('input[name="embed-mode"]:checked')?.value || 'separate';
      if (mode === 'video-only') {
        opts.classList.add('card-hidden');
        return;
      }
      opts.classList.toggle('card-hidden', !e.target.checked);
    });

    document.querySelectorAll('input[name="embed-mode"]').forEach(el => {
      el.addEventListener('change', (e) => this._onEmbedModeChange(e.target.value));
    });

    const initialMode = document.querySelector('input[name="embed-mode"]:checked')?.value || 'separate';
    this._onEmbedModeChange(initialMode);

    // 3D tilt on cards
    document.querySelectorAll('.card').forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const rx = ((y - cy) / cy) * -6;
        const ry = ((x - cx) / cx) * 6;
        card.style.transform = `perspective(800px) rotateX(${rx}deg) rotateY(${ry}deg)`;
      });
      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  }

  _onEmbedModeChange(mode) {
    const qSec = document.getElementById('quality-section');
    const btnText = document.getElementById('download-btn-text');
    const subOptions = document.getElementById('subtitle-options');
    if (mode === 'subtitle-only') {
      qSec.classList.add('hidden');
      btnText.textContent = 'تحميل الترجمة';
      subOptions.classList.remove('card-hidden');
    } else if (mode === 'video-only') {
      qSec.classList.remove('hidden');
      btnText.textContent = 'تحميل الفيديو';
      subOptions.classList.add('card-hidden');
    } else {
      qSec.classList.remove('hidden');
      btnText.textContent = 'تحميل الآن';
      const subChecked = document.getElementById('include-subtitles').checked;
      subOptions.classList.toggle('card-hidden', !subChecked);
    }
    if (this.videoInfo && this.videoInfo.data) {
      this._updateDurationWarning(this.videoInfo.data);
    }
  }

  _updateDurationWarning(data) {
    if (!data) return;
    const durWarn = document.getElementById('duration-warning');
    const curMode = document.querySelector('input[name="embed-mode"]:checked')?.value || 'separate';
    const isSingleMode = curMode === 'video-only' || curMode === 'subtitle-only';
    const maxDur = isSingleMode
      ? (data.max_duration_single || 0)
      : (data.max_duration_video_subtitle || 14400);
    if (maxDur > 0 && data.duration >= maxDur) {
      const hours = Math.floor(data.duration / 3600);
      const maxHours = Math.floor(maxDur / 3600);
      durWarn.textContent = isSingleMode
        ? `⚠ هذا الفيديو طويل (${hours} ساعات).`
        : `⚠ هذا الفيديو طويل (${hours} ساعات). الحد الأقصى للتحميل مع الترجمة ${maxHours} ساعات.`;
      durWarn.style.display = '';
    } else {
      durWarn.style.display = 'none';
    }
  }

  _clearVideo() {
    this.videoInfo.data = null;
    this.videoInfo.cache = new Map();
    document.getElementById('quality-selector').innerHTML = '';
    document.getElementById('quality-section').classList.remove('hidden');
    document.getElementById('subtitle-status').textContent = '';
    document.getElementById('subtitle-status').className = 'subtitle-badge';
    document.getElementById('subtitle-options').classList.add('card-hidden');
    document.getElementById('download-btn-text').textContent = 'تحميل الآن';
    this.showSection('input');
  }

  showSection(id) {
    Object.keys(this.sections).forEach((key) => {
      const el = this.sections[key];
      if (key === id) {
        el.classList.remove('card-hidden');
      } else {
        el.classList.add('card-hidden');
      }
    });
  }

  showError(msg) {
    this.errorMessageEl.textContent = msg;
    this.errorCard.classList.remove('card-hidden');
    this.showSection('error');
  }

  hideError() {
    this.errorCard.classList.add('card-hidden');
  }

  resetUI() {
    this.hideError();
    this.videoInfo.reset();
    this.downloader.reset();
    this.progressTracker.disconnect();
    document.getElementById('url-input').value = '';
    document.getElementById('fetch-btn').disabled = false;
    document.getElementById('quality-selector').innerHTML = '';
    document.getElementById('quality-section').classList.remove('hidden');
    document.getElementById('subtitle-status').textContent = '';
    document.getElementById('subtitle-status').className = 'subtitle-badge';
    document.getElementById('subtitle-options').classList.add('card-hidden');
    document.getElementById('restart-btn').style.display = 'none';
    document.getElementById('result-restart-btn').style.display = 'none';
    document.getElementById('download-btn-text').textContent = 'تحميل الآن';
    this.showSection('input');
  }

  setupPasteButton() {
    const pasteBtn = document.getElementById('paste-btn');
    if (navigator.clipboard) {
      pasteBtn.addEventListener('click', async () => {
        try {
          const text = await navigator.clipboard.readText();
          document.getElementById('url-input').value = text;
        } catch (err) {
          // fallback
        }
      });
    } else {
      pasteBtn.style.display = 'none';
    }
  }
}

class VideoInfo {
  constructor(app) {
    this.app = app;
    this.data = null;
    this.controller = null;
    this.cache = new Map();
    this._fetching = false;
  }

  reset() {
    this.data = null;
    this.controller = null;
    this.cache = new Map();
    this._fetching = false;
  }

  async fetch() {
    if (this._fetching) return;
    this._fetching = true;

    const url = document.getElementById('url-input').value.trim();
    if (!url) {
      this._fetching = false;
      this.app.showError('يرجى إدخال رابط يوتيوب');
      return;
    }

    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com|youtu\.be)\/.+/;
    if (!ytRegex.test(url)) {
      this._fetching = false;
      this.app.showError('رابط يوتيوب غير صالح');
      return;
    }

    // Cache hit — show instantly
    if (this.cache.has(url)) {
      this._fetching = false;
      this.data = this.cache.get(url);
      this.display(this.data);
      return;
    }

    // Abort previous request if still in-flight
    if (this.controller) {
      this.controller.abort();
      this.controller = null;
    }

    this.app.hideError();
    this.app.showSection('progress');
    this.app.ui.showLoading(true);

    this.controller = new AbortController();
    const timeout = setTimeout(() => this.controller.abort(), 90000);

    try {
      const resp = await fetch(`/api/v1/info?url=${encodeURIComponent(url)}`, {
        signal: this.controller.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'خطأ في الاتصال' }));
        throw new Error(err.detail || `خطأ ${resp.status}`);
      }

      this.data = await resp.json();
      this.cache.set(url, this.data);
      if (this.cache.size > 5) {
        const first = this.cache.keys().next().value;
        this.cache.delete(first);
      }
      this.display(this.data);

      // Phase 2: if formats not loaded yet, fetch them in background
      if (!this.data.formats_loaded) {
        this._loadFormatsInBackground(url);
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        this.app.showError('انتهت مهلة الاتصال، يرجى المحاولة مجدداً');
      } else {
        this.app.showError(err.message || 'حدث خطأ أثناء جلب المعلومات');
      }
    } finally {
      clearTimeout(timeout);
      this.app.ui.showLoading(false);
      this.controller = null;
      this._fetching = false;
    }
  }

  async _loadFormatsInBackground(url) {
    const qSel = document.getElementById('quality-selector');
    const qSec = document.getElementById('quality-section');
    qSel.innerHTML = '<div class="quality-option"><span class="spinner"></span> جاري تحميل خيارات الجودة...</div>';
    qSec.classList.remove('hidden');

    try {
      const resp = await fetch(`/api/v1/info/formats?url=${encodeURIComponent(url)}`);
      if (!resp.ok) return;
      const formatsData = await resp.json();
      Object.assign(this.data, formatsData);
      this.data.formats_loaded = true;
      this.cache.set(url, this.data);
      this._renderQualityOptions(this.data);
      this._renderSubtitleStatus(this.data);
    } catch (err) {
      qSel.innerHTML = '<div class="quality-option">تعذر تحميل خيارات الجودة، سيتم استخدام أفضل جودة متاحة</div>';
    }
  }

  display(data) {
    // Thumbnail
    const thumb = document.getElementById('video-thumbnail');
    thumb.innerHTML = `
      <img src="${this._escapeHtml(data.thumbnail)}" alt="${this._escapeHtml(data.title)}" loading="lazy" onerror="this.style.display='none'">
      <div class="video-thumbnail-overlay"></div>
      <span class="video-duration">${this._formatDuration(data.duration)}</span>
    `;

    document.getElementById('video-title').textContent = data.title;
    document.getElementById('video-channel').innerHTML = data.channel_url
      ? `<a href="${this._escapeHtml(data.channel_url)}" target="_blank" rel="noopener">${this._escapeHtml(data.channel)}</a>`
      : this._escapeHtml(data.channel);

    document.getElementById('video-views').textContent = `${this._formatNumber(data.view_count)} مشاهدة`;

    // Quality options (or placeholder if formats not loaded yet)
    if (data.formats_loaded) {
      this._renderQualityOptions(data);
    } else {
      const qSel = document.getElementById('quality-selector');
      qSel.innerHTML = '<div class="quality-option"><span class="spinner"></span> جاري تحميل خيارات الجودة...</div>';
      document.getElementById('quality-section').classList.remove('hidden');
    }

    // Subtitle status
    this._renderSubtitleStatus(data);
    document.getElementById('subtitle-options').classList.toggle('card-hidden', !document.getElementById('include-subtitles').checked);

    this.app._updateDurationWarning(data);

    const curMode = document.querySelector('input[name="embed-mode"]:checked')?.value || 'separate';
    this.app._onEmbedModeChange(curMode);

    this.app.showSection('info');
  }

  _formatDuration(seconds) {
    if (!seconds) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  _formatNumber(num) {
    if (!num) return '0';
    if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return String(num);
  }

  _formatSize(bytes) {
    if (!bytes) return '';
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
      if (bytes < 1024) return `${bytes.toFixed(1)} ${unit}`;
      bytes /= 1024;
    }
    return `${bytes.toFixed(1)} TB`;
  }

  _renderQualityOptions(data) {
    const qSel = document.getElementById('quality-selector');
    qSel.innerHTML = '';
    const allFormats = [...(data.formats || []), ...(data.audio_formats || [])];
    if (allFormats.length === 0) {
      allFormats.push({ format_id: 'best', label: 'أفضل جودة', ext: 'mp4', size: 0 });
    }
    allFormats.forEach((f, idx) => {
      const div = document.createElement('div');
      div.className = 'quality-option';
      const checked = idx === 0 ? 'checked' : '';
      const sizeText = f.size ? ` (${this._formatSize(f.size)})` : '';
      const extText = f.ext ? ` .${f.ext}` : '';
      div.innerHTML = `
        <input type="radio" name="quality" id="q-${idx}" value="${this._escapeHtml(f.format_id)}" ${checked}>
        <label for="q-${idx}">${this._escapeHtml(f.label)}${extText}<span class="quality-size">${sizeText}</span></label>
      `;
      qSel.appendChild(div);
    });
  }

  _renderSubtitleStatus(data) {
    const subStatus = document.getElementById('subtitle-status');
    if (data.has_arabic_subtitles) {
      subStatus.textContent = '✓ الترجمة العربية متوفرة';
      subStatus.className = 'subtitle-badge available';
    } else if (data.has_auto_subtitles) {
      subStatus.textContent = '⚡ الترجمة التلقائية متوفرة';
      subStatus.className = 'subtitle-badge pending';
    } else {
      subStatus.textContent = '⚡ سيتم التوليد تلقائياً';
      subStatus.className = 'subtitle-badge pending';
    }
  }

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}

class Downloader {
  constructor(app) {
    this.app = app;
    this.taskId = null;
    this.controller = null;
  }

  reset() {
    this.taskId = null;
    this.controller = null;
  }

  async start() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) return;

    const qualityEl = document.querySelector('input[name="quality"]:checked');
    const formatId = qualityEl ? qualityEl.value : 'best';
    const embedMode = document.querySelector('input[name="embed-mode"]:checked')?.value || 'separate';
    const videoOnly = embedMode === 'video-only';
    const subtitleOnly = embedMode === 'subtitle-only';
    const includeSubs = videoOnly ? false : document.getElementById('include-subtitles').checked;
    const actualIncludeSubs = includeSubs || subtitleOnly;

    this.app.hideError();
    this.app.showSection('progress');
    this.app.ui.resetProgress();

    const btn = document.getElementById('download-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> جاري البدء...';

    this.controller = new AbortController();
    const timeout = setTimeout(() => this.controller.abort(), subtitleOnly ? 120000 : 300000);

    try {
      this.taskId = (crypto.randomUUID && crypto.randomUUID()) ||
                    (self.crypto.randomUUID && self.crypto.randomUUID()) ||
                    Date.now().toString(36) + Math.random().toString(36).slice(2);

      const resp = await fetch('/api/v1/download/video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          format_id: formatId,
          include_subtitles: actualIncludeSubs,
          auto_generate: true,
          embed_subtitles: false,
          subtitle_only: subtitleOnly,
          task_id: this.taskId,
        }),
        signal: this.controller.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'فشل بدء التحميل' }));
        throw new Error(err.detail || `خطأ ${resp.status}`);
      }

      const result = await resp.json();
      this.taskId = result.task_id;
      this.app.progressTracker.connect(this.taskId);
    } catch (err) {
      if (err.name === 'AbortError') {
        this.app.showSection('input');
      } else {
        this.app.showError(err.message || 'حدث خطأ أثناء بدء التحميل');
      }
    } finally {
      clearTimeout(timeout);
      const dlBtn = document.getElementById('download-btn');
      const dlText = document.getElementById('download-btn-text');
      if (dlBtn.disabled) {
        dlBtn.disabled = false;
        dlBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> <span id="download-btn-text">${dlText ? dlText.textContent : 'تحميل الآن'}</span>`;
      }
    }
  }

  cancel() {
    if (!this.taskId) return;
    // Instant feedback — no await
    document.getElementById('cancel-btn').disabled = true;
    document.getElementById('restart-btn').style.display = '';
    document.getElementById('progress-message').textContent = 'جاري الإلغاء...';
    this.app.progressTracker.disconnect();
    if (this.controller) this.controller.abort();
    // Fire-and-forget — لا ننتظر الرد
    fetch(`/api/v1/download/cancel/${this.taskId}`, { method: 'POST' }).catch(() => {});
  }

  restart() {
    window.location.reload();
  }
}

class ProgressTracker {
  constructor(app) {
    this.app = app;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnect = 3;
  }

  connect(taskId) {
    this.disconnect();
    this.reconnectAttempts = 0;
    this._doConnect(taskId);
  }

  _doConnect(taskId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/download/ws/${taskId}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._handleMessage(data);
      } catch (err) {
        // ignore parse errors
      }
    };

    this.ws.onclose = () => {
      if (this.reconnectAttempts < this.maxReconnect) {
        this.reconnectAttempts++;
        setTimeout(() => this._doConnect(taskId), 2000 * this.reconnectAttempts);
      }
    };

    this.ws.onerror = () => {
      // handled by onclose
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  _handleMessage(data) {
    const status = data.status;

    switch (status) {
      case 'info':
        this.app.ui.setProgress(data.percent || 0, data.message || 'جاري التجهيز...');
        break;

      case 'progress':
      case 'downloading':
      case 'embedding':
      case 'transcribing':
      case 'translating':
        this.app.ui.setProgress(data.percent, data.message || 'جاري المعالجة...', data.speed, data.eta);
        break;

      case 'done':
        this.app.ui.setProgress(100, 'اكتمل التحميل!');
        this.app.ui.showResult(data);
        this.disconnect();
        break;

      case 'error':
        this.app.showError(data.message || 'حدث خطأ أثناء التحميل');
        this.disconnect();
        break;

      case 'cancelled':
        document.getElementById('cancel-btn').disabled = true;
        document.getElementById('restart-btn').style.display = '';
        document.getElementById('progress-message').textContent = 'تم الإلغاء';
        this.disconnect();
        break;
    }
  }
}

class UIManager {
  constructor(app) {
    this.app = app;
  }

  showLoading(show) {
    const btn = document.getElementById('fetch-btn');
    btn.disabled = show;
    btn.innerHTML = show
      ? '<span class="spinner"></span> جاري الجلب...'
      : '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg> جلب معلومات الفيديو';
  }

  resetProgress() {
    document.getElementById('progress-percent').textContent = '0%';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-message').textContent = 'جاري البدء...';
    document.getElementById('progress-speed').textContent = '';
    document.getElementById('progress-eta').textContent = '';
    document.getElementById('cancel-btn').disabled = false;
    document.getElementById('cancel-btn').style.display = '';
    document.getElementById('restart-btn').style.display = 'none';
  }

  setProgress(pct, message, speed, eta) {
    const pctEl = document.getElementById('progress-percent');
    const barEl = document.getElementById('progress-bar');
    const msgEl = document.getElementById('progress-message');
    const speedEl = document.getElementById('progress-speed');
    const etaEl = document.getElementById('progress-eta');

    const clamped = Math.min(100, Math.max(0, pct));
    pctEl.textContent = `${Math.round(clamped)}%`;
    barEl.style.width = `${clamped}%`;
    if (message) msgEl.textContent = message;

    if (speed !== undefined && speed > 0) {
      speedEl.textContent = `⬇ ${this._formatSpeed(speed)}`;
    }
    if (eta !== undefined && eta > 0) {
      etaEl.textContent = `⏱ ${this._formatTime(eta)} متبقية`;
    }
  }

  showResult(data) {
    document.getElementById('cancel-btn').disabled = true;

    const filename = data.filename || 'video.mp4';
    const filesize = data.filesize || '';
    const badge = document.getElementById('result-badge');
    document.getElementById('result-filename').textContent = filename;
    document.getElementById('result-filesize').textContent = filesize;
    document.getElementById('result-restart-btn').style.display = '';

    const dlVideo = document.getElementById('download-video-btn');
    const dlSub = document.getElementById('download-subtitle-btn');
    const subText = document.getElementById('download-subtitle-text');
    dlVideo.style.display = 'none';
    dlSub.style.display = 'none';

    if (data.subtitle_only) {
      document.getElementById('result-icon').textContent = '📝';
      badge.textContent = 'ترجمة فقط';
      badge.className = 'result-badge subtitle-only';
      badge.style.display = '';
      if (data.subtitle_file) {
        dlSub.onclick = () => this._downloadFile(data.subtitle_file, data.task_id);
        dlSub.style.display = '';
        dlSub.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> تحميل الترجمة';
      }
    } else if (data.embedded) {
      document.getElementById('result-icon').textContent = '🎬';
      badge.textContent = 'الترجمة مدمجة في الفيديو';
      badge.className = 'result-badge embedded';
      badge.style.display = '';
      if (data.video_file) {
        dlVideo.onclick = () => this._downloadFile(data.video_file, data.task_id);
        dlVideo.style.display = '';
        dlVideo.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> تحميل الفيديو (مع الترجمة)';
      }
    } else {
      document.getElementById('result-icon').textContent = '✅';
      badge.style.display = 'none';
      if (data.video_file) {
        dlVideo.onclick = () => this._downloadFile(data.video_file, data.task_id);
        dlVideo.style.display = '';
      }
      if (data.subtitle_file) {
        dlSub.onclick = () => this._downloadFile(data.subtitle_file, data.task_id);
        dlSub.style.display = '';
        const subType = data.subtitle_type === 'official' ? 'رسمية'
          : data.subtitle_type === 'generated' ? 'AI' : '';
        subText.textContent = subType ? `تحميل الترجمة (${subType})` : 'تحميل الترجمة';
      }
    }

    this.app.showSection('result');
  }

  _downloadFile(filepath, taskId) {
    if (!filepath) return;
    const filename = filepath.split('/').pop() || 'download';
    const isSubtitle = filepath.endsWith('.srt') || filepath.endsWith('.vtt');
    const tid = taskId || this.app.downloader.taskId;
    if (!tid) return;
    const a = document.createElement('a');
    a.href = `/api/v1/download/file/${tid}?file_type=${isSubtitle ? 'subtitle' : 'video'}&filename=${encodeURIComponent(filename)}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  _formatSpeed(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec <= 0) return '';
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
      if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(1)} ${unit}/ث`;
      bytesPerSec /= 1024;
    }
    return `${bytesPerSec.toFixed(1)} TB/ث`;
  }

  _formatTime(seconds) {
    if (!seconds || seconds <= 0) return '';
    if (seconds < 60) return `${Math.round(seconds)} ثانية`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m} دقيقة ${s} ثانية`;
  }
}

// ── Bootstrap ──
document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
