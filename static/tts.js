// 首句优先 TTS(design.md §16):把流式文本按句子切分,凑满一句即用浏览器
// speechSynthesis 播报,不等整段。后续 PR 可切百炼高音质 TTS。
'use strict';

window.SentenceSpeaker = class SentenceSpeaker {
  constructor(opts = {}) {
    this.lang = opts.lang || 'zh-CN';
    this.enabled = 'speechSynthesis' in window;
    this._buf = '';
    this._queue = [];
    this._speaking = false;
    this._ENDERS = '。！？!?.';
  }

  reset() {
    this._buf = '';
    this._queue = [];
    this._speaking = false;
    if (this.enabled) window.speechSynthesis.cancel();
  }

  // 持续喂入增量文本;凑满整句即入队播报(首句优先)
  feed(delta) {
    if (!this.enabled || !delta) return;
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

  // 流结束:把残留不足一句的也播出去
  flush() {
    const t = this._buf.trim();
    this._buf = '';
    if (t) this._enqueue(t);
  }

  _enqueue(text) { this._queue.push(text); this._drain(); }

  _drain() {
    if (this._speaking || !this._queue.length) return;
    const u = new SpeechSynthesisUtterance(this._queue.shift());
    u.lang = this.lang;
    u.onend = () => { this._speaking = false; this._drain(); };
    u.onerror = () => { this._speaking = false; this._drain(); };
    this._speaking = true;
    window.speechSynthesis.speak(u);
  }
};
