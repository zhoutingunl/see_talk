// 首句优先 TTS(design.md §16):流式文本按句切分,凑满一句即播,不等整段。
// 双模式(design.md §24 免费/付费):
//   browser  = 浏览器 speechSynthesis(免费默认)
//   bailian  = 服务端 CosyVoice 高音质(/api/tts → 播放 mp3,付费)
'use strict';

window.SentenceSpeaker = class SentenceSpeaker {
  constructor(opts = {}) {
    this.lang = opts.lang || 'zh-CN';
    this.mode = opts.mode || 'browser';
    this.browserOk = 'speechSynthesis' in window;
    this._buf = '';
    this._queue = [];
    this._speaking = false;
    this._audio = null;
    this._ENDERS = '。！？!?.';
  }

  setMode(m) { this.mode = m; }

  reset() {
    this._buf = '';
    this._queue = [];
    this._speaking = false;
    if (this.browserOk) window.speechSynthesis.cancel();
    if (this._audio) { try { this._audio.pause(); } catch (e) {} this._audio = null; }
  }

  feed(delta) {
    if (!delta) return;
    this._buf += delta;
    let start = 0;
    const out = [];
    for (let k = 0; k < this._buf.length; k++) {
      if (this._ENDERS.includes(this._buf[k])) {
        out.push(this._buf.slice(start, k + 1));
        start = k + 1;
      }
    }
    if (out.length) {
      this._buf = this._buf.slice(start);
      out.forEach((s) => { const t = s.trim(); if (t) this._enqueue(t); });
    }
  }

  flush() {
    const t = this._buf.trim();
    this._buf = '';
    if (t) this._enqueue(t);
  }

  _enqueue(text) { this._queue.push(text); this._drain(); }

  _drain() {
    if (this._speaking || !this._queue.length) return;
    const text = this._queue.shift();
    this._speaking = true;
    if (this.mode === 'bailian') this._playBailian(text);
    else this._playBrowser(text);
  }

  _next() { this._speaking = false; this._drain(); }

  _playBrowser(text) {
    if (!this.browserOk) return this._next();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = this.lang;
    u.onend = () => this._next();
    u.onerror = () => this._next();
    window.speechSynthesis.speak(u);
  }

  async _playBailian(text) {
    try {
      const r = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!r.ok) return this._playBrowser(text);   // 服务端不可用 → 回退浏览器
      const url = URL.createObjectURL(await r.blob());
      const a = new Audio(url);
      this._audio = a;
      a.onended = () => { URL.revokeObjectURL(url); this._next(); };
      a.onerror = () => { URL.revokeObjectURL(url); this._next(); };
      a.play();
    } catch (e) {
      this._playBrowser(text);
    }
  }
};
