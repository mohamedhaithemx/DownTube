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
    document.getElementById('new-download-btn').addEventListener('click', () => this.resetUI());
    document.getElementById('retry-btn').addEventListener('click', () => this.resetUI());
    document.getElementById('url-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.videoInfo.fetch();
    });
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
    document.getElementById('subtitle-status').textContent = '';
    document.getElementById('subtitle-status').className = 'subtitle-badge';
    document.getElementById('subtitle-options').classList.add('card-hidden');
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
  }

  reset() {
    this.data = null;
    this.controller = null;
  }

  async fetch() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) {
      this.app.showError('يرجى إدخال رابط يوتيوب');
      return;
    }

    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com|youtu\.be)\/.+/;
    if (!ytRegex.test(url)) {
      this.app.showError('رابط يوتيوب غير صالح');
      return;
    }

    this.app.hideError();
    this.app.showSection('progress');
    this.app.ui.showLoading(true);

    this.controller = new AbortController();
    const timeout = setTimeout(() => this.controller.abort(), 30000);

    try {
      const resp = await fetch(`/api/v1/info?url=${encodeURIComponent(url)}`, {
        signal: this.controller.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'خطأ في الاتصال' }));
        throw new Error(err.detail || `خطأ ${resp.status}`);
      }

      this.data = await resp.json();
      this.display(this.data);
    } catch (err) {
      if (err.name === 'AbortError') {
        this.app.showError('انتهت مهلة الاتصال، يرجى المحاولة مجدداً');
      } else {
        this.app.showError(err.message || 'حدث خطأ أثناء جلب المعلومات');
      }
      this.app.showSection('input');
    } finally {
      clearTimeout(timeout);
      this.app.ui.showLoading(false);
      this.controller = null;
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

    // Quality options
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

    // Subtitle status
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
    document.getElementById('subtitle-options').classList.remove('card-hidden');

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
    const includeSubs = document.getElementById('include-subtitles').checked;
    const autoGenerate = document.getElementById('auto-generate').checked;
    const embedSubs = document.querySelector('input[name="embed-mode"]:checked')?.value === 'embed';

    this.taskId = crypto.randomUUID ? crypto.randomUUID() : self.crypto.randomUUID();

    this.app.hideError();
    this.app.showSection('progress');
    this.app.ui.resetProgress();

    this.controller = new AbortController();
    const timeout = setTimeout(() => this.controller.abort(), 300000);

    try {
      const resp = await fetch('/api/v1/download/video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          format_id: formatId,
          include_subtitles: includeSubs,
          auto_generate: autoGenerate,
          embed_subtitles: embedSubs,
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
        this.app.showError('تم إلغاء التحميل');
      } else {
        this.app.showError(err.message || 'حدث خطأ أثناء بدء التحميل');
      }
      this.app.showSection('input');
    } finally {
      clearTimeout(timeout);
    }
  }

  async cancel() {
    if (!this.taskId) return;
    if (this.controller) this.controller.abort();
    try {
      await fetch(`/api/v1/download/cancel/${this.taskId}`, { method: 'POST' });
    } catch (err) {
      // ignore
    }
    this.app.progressTracker.disconnect();
    this.app.showError('تم إلغاء التحميل');
    this.app.showSection('input');
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
        this.app.ui.setProgress(0, data.message || 'جاري التجهيز...');
        break;

      case 'downloading':
        this.app.ui.setProgress(data.percent, data.message || 'جاري التحميل...', data.speed, data.eta);
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
    const filesizeBytes = data.filesize_bytes || 0;

    document.getElementById('result-icon').textContent = '✅';
    document.getElementById('result-filename').textContent = filename;
    document.getElementById('result-filesize').textContent = filesize;

    const dlVideo = document.getElementById('download-video-btn');
    dlVideo.onclick = () => this._downloadFile(data.video_file);
    dlVideo.style.display = '';

    const dlSub = document.getElementById('download-subtitle-btn');
    if (data.subtitle_file) {
      dlSub.onclick = () => this._downloadFile(data.subtitle_file);
      dlSub.style.display = '';
      const subType = data.subtitle_type === 'official' ? 'رسمية'
        : data.subtitle_type === 'generated' ? 'AI'
        : 'تلقائية';
      dlSub.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> تحميل الترجمة (${subType})`;
    } else {
      dlSub.style.display = 'none';
    }

    this.app.showSection('result');
  }

  _downloadFile(filepath) {
    if (!filepath) return;
    const a = document.createElement('a');
    a.href = `/api/v1/download/file/${this.app.downloader.taskId}?file_type=${filepath.endsWith('.srt') || filepath.endsWith('.vtt') ? 'subtitle' : 'video'}`;
    a.download = filepath.split('/').pop() || 'download';
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
