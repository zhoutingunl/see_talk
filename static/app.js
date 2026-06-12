// SeeTalk 前端主流程(PR2):摄像头 + 免手语音 → 抓帧 → 流式回答 + 首句优先 TTS。
// 按需抓帧(design.md §3/§12):提问瞬间才抓 1 帧;语音由 VAD 触发(design.md §13)。
'use strict';

const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const logEl = document.getElementById('log');
const badge = document.getElementById('badge');
const startCam = document.getElementById('startCam');
const stopCam = document.getElementById('stopCam');
const askForm = document.getElementById('askForm');
const questionEl = document.getElementById('question');
const askBtn = document.getElementById('askBtn');
const micBtn = document.getElementById('micBtn');
const voiceState = document.getElementById('voiceState');
const asrToggle = document.getElementById('asrToggle');
const ttsToggle = document.getElementById('ttsToggle');

let stream = null;
const speaker = new window.SentenceSpeaker({ lang: 'zh-CN' });
const voice = new window.VoiceInput({ onTranscript: handleUtterance, onState: setVoiceState });

function addLine(who, text, cls) {
  const div = document.createElement('div');
  div.className = 'line ' + (cls || who);
  div.innerHTML = `<span class="who">${who}</span><span class="txt"></span>`;
  div.querySelector('.txt').textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  return div;
}

async function refreshHealth() {
  try {
    const j = await (await fetch('/api/health')).json();
    badge.textContent = j.vision_live ? 'M3 已接入' : 'Mock 模式（未配 Key）';
    badge.classList.toggle('live', j.vision_live);
    window.__asrLive = j.asr_live;
    window.__ttsLive = j.tts_live;
  } catch { badge.textContent = '后端不可达'; }
}

// ---------- 摄像头 ----------
startCam.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = stream;
    startCam.disabled = true; stopCam.disabled = false;
  } catch (e) { addLine('系统', '无法打开摄像头：' + e.message, 'err'); }
});
stopCam.addEventListener('click', () => {
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null; video.srcObject = null;
  startCam.disabled = false; stopCam.disabled = true;
});

// 抓当前帧 → 降分到宽 512(design.md §14)→ jpeg dataURL
function grabFrame() {
  if (!stream || !video.videoWidth) return null;
  const scale = Math.min(1, 512 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.8);
}

// ---------- 流式问答(文字 / 语音共用)----------
async function ask(question) {
  const image = grabFrame();
  addLine('我', question + (image ? ' 📷' : ''), 'me');
  const pending = addLine('AI', '', 'ai');
  const txt = pending.querySelector('.txt');
  txt.textContent = '思考中…';
  speaker.reset();
  let first = true;

  try {
    const r = await fetch('/api/ask_stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, image }),
    });
    if (!r.ok) { txt.textContent = '错误：HTTP ' + r.status; pending.classList.add('err'); return; }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
        const line = block.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === 'delta') {
          if (first) { txt.textContent = ''; first = false; }
          txt.textContent += ev.text;
          speaker.feed(ev.text);              // 首句优先:边收边播
          logEl.scrollTop = logEl.scrollHeight;
        } else if (ev.type === 'done') {
          speaker.flush();
          const meta = document.createElement('span');
          meta.className = 'meta';
          meta.textContent = (ev.source === 'mock' ? '降级示例' : '来源 M3')
            + (ev.output_tokens ? ` · token ${ev.input_tokens}/${ev.output_tokens}` : '');
          pending.appendChild(meta);
        } else if (ev.type === 'error') {
          txt.textContent = '出错：' + ev.message; pending.classList.add('err');
        }
      }
    }
  } catch (e) {
    txt.textContent = '请求失败：' + e.message; pending.classList.add('err');
  } finally {
    if (voice.active) setVoiceState('listening');
  }
}

// ---------- 文字提问 ----------
askForm.addEventListener('submit', (ev) => {
  ev.preventDefault();
  const q = questionEl.value.trim();
  if (!q) return;
  questionEl.value = '';
  ask(q);
});

// ---------- 语音提问 ----------
function handleUtterance(text) { ask(text); }

function setVoiceState(state) {
  const map = {
    listening: '🎤 聆听中…', speech: '🗣 说话中…', thinking: '💭 识别中…',
    idle: '已停止', error: '⚠️ 语音出错',
  };
  voiceState.textContent = map[state] || state;
}

micBtn.addEventListener('click', async () => {
  if (voice.active) {
    voice.stop();
    micBtn.textContent = '🎤 开始语音';
    micBtn.classList.remove('on');
  } else {
    await voice.start();
    micBtn.textContent = '⏹ 停止语音';
    micBtn.classList.add('on');
    asrToggle.textContent = 'ASR：' + voice.providerLabel;
  }
});

asrToggle.addEventListener('click', () => {
  voice.setProvider(voice.provider === 'webspeech' ? 'bailian' : 'webspeech');
  asrToggle.textContent = 'ASR：' + voice.providerLabel;
});

ttsToggle.addEventListener('click', () => {
  if (speaker.mode === 'browser') {
    if (!window.__ttsLive) { addLine('系统', '高音质 TTS 未配置（需百炼 Key）', 'err'); return; }
    speaker.setMode('bailian');
    ttsToggle.textContent = 'TTS：百炼高音质';
  } else {
    speaker.setMode('browser');
    ttsToggle.textContent = 'TTS：浏览器';
  }
});

asrToggle.textContent = 'ASR：' + voice.providerLabel;
refreshHealth();
