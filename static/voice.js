// 语音输入(design.md §13):免手 VAD + ASR 分层。
//   - webspeech:桌面默认,浏览器内置 SpeechRecognition(免费,自带断句)。
//   - bailian  :移动端默认,getUserMedia 录音 + 能量 VAD 切句 → 16k PCM → /api/asr。
// 自动选择 + 可手动切换(免费/付费产品线)。
'use strict';

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const HAS_WEBSPEECH = !!SR;
const IS_MOBILE = /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

window.VoiceInput = class VoiceInput {
  constructor({ onTranscript, onState } = {}) {
    this.onTranscript = onTranscript || (() => {});
    this.onState = onState || (() => {});      // 'listening' | 'speech' | 'thinking' | 'idle' | 'error'
    this.provider = HAS_WEBSPEECH && !IS_MOBILE ? 'webspeech' : 'bailian';
    this.active = false;
    // bailian 路径运行时
    this._stream = null; this._ctx = null; this._node = null;
    this._buffers = []; this._speaking = false; this._silenceMs = 0;
    // webspeech 路径
    this._rec = null;
  }

  get providerLabel() {
    return this.provider === 'webspeech' ? '浏览器 Web Speech（免费）' : '百炼 ASR（移动/付费）';
  }

  setProvider(p) {
    if (p === this.provider) return;
    const wasActive = this.active;
    this.stop();
    this.provider = p;
    if (wasActive) this.start();
  }

  async start() {
    if (this.active) return;
    this.active = true;
    if (this.provider === 'webspeech' && HAS_WEBSPEECH) await this._startWebSpeech();
    else await this._startBailian();
  }

  stop() {
    this.active = false;
    if (this._rec) { try { this._rec.onend = null; this._rec.stop(); } catch (e) {} this._rec = null; }
    if (this._node) { try { this._node.disconnect(); } catch (e) {} this._node = null; }
    if (this._ctx) { try { this._ctx.close(); } catch (e) {} this._ctx = null; }
    if (this._stream) { this._stream.getTracks().forEach((t) => t.stop()); this._stream = null; }
    this._buffers = []; this._speaking = false; this._silenceMs = 0;
    this.onState('idle');
  }

  // ---------- 桌面:浏览器内置 ASR(自带 VAD/断句) ----------
  async _startWebSpeech() {
    const rec = new SR();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (ev) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) {
          const text = r[0].transcript.trim();
          if (text) { this.onState('thinking'); this.onTranscript(text); }
        }
      }
    };
    rec.onerror = (e) => this.onState(e.error === 'no-speech' ? 'listening' : 'error');
    rec.onend = () => { if (this.active) { try { rec.start(); } catch (e) {} } }; // 免手:自动续听
    this._rec = rec;
    try { rec.start(); this.onState('listening'); } catch (e) { this.onState('error'); }
  }

  // ---------- 移动端:录 PCM + 能量 VAD → 百炼 ----------
  async _startBailian() {
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
      this.onState('error'); this.active = false;
      console.warn('麦克风不可用:非安全上下文,请用 https 或 localhost');
      return;
    }
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) { this.onState('error'); this.active = false; return; }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this._ctx = new Ctx();
    const source = this._ctx.createMediaStreamSource(this._stream);
    const node = this._ctx.createScriptProcessor(4096, 1, 1);
    const SILENCE_MS = 800, THRESH = 0.012;
    const frameMs = (4096 / this._ctx.sampleRate) * 1000;

    node.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);

      if (rms > THRESH) {
        if (!this._speaking) { this._speaking = true; this.onState('speech'); }
        this._silenceMs = 0;
        this._buffers.push(new Float32Array(input));
      } else if (this._speaking) {
        this._buffers.push(new Float32Array(input));
        this._silenceMs += frameMs;
        if (this._silenceMs >= SILENCE_MS) this._flushUtterance();
      }
    };
    source.connect(node);
    node.connect(this._ctx.destination);
    this._node = node;
    this.onState('listening');
  }

  _flushUtterance() {
    const chunks = this._buffers;
    this._buffers = []; this._speaking = false; this._silenceMs = 0;
    if (!chunks.length) return;
    const pcm = this._encode16k(chunks, this._ctx.sampleRate);
    this.onState('thinking');
    this._sendToBailian(pcm);
  }

  // Float32 多块 → 16k 单声道 Int16 LE 字节
  _encode16k(chunks, srcRate) {
    let len = 0; chunks.forEach((c) => (len += c.length));
    const flat = new Float32Array(len);
    let off = 0; chunks.forEach((c) => { flat.set(c, off); off += c.length; });
    const ratio = srcRate / 16000;
    const outLen = Math.floor(flat.length / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const s = Math.max(-1, Math.min(1, flat[Math.floor(i * ratio)]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out.buffer;
  }

  async _sendToBailian(pcmBuffer) {
    try {
      const r = await fetch('/api/asr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: pcmBuffer,
      });
      const j = await r.json();
      if (r.ok && j.text) this.onTranscript(j.text);
      else this.onState(this.active ? 'listening' : 'idle');
    } catch (e) {
      this.onState('error');
    }
  }
};
