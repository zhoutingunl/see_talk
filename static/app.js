// SeeTalk PR1 前端:开摄像头 → 提问瞬间抓 1 帧 → POST /api/ask → 显示回答。
// 按需抓帧(design.md §3/§12):平时只预览,不上行;点"提问"才抓当前帧。
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

let stream = null;

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
    const r = await fetch('/api/health');
    const j = await r.json();
    badge.textContent = j.vision_live ? 'M3 已接入' : 'Mock 模式（未配 Key）';
    badge.classList.toggle('live', j.vision_live);
  } catch {
    badge.textContent = '后端不可达';
  }
}

startCam.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = stream;
    startCam.disabled = true;
    stopCam.disabled = false;
  } catch (e) {
    addLine('系统', '无法打开摄像头：' + e.message, 'err');
  }
});

stopCam.addEventListener('click', () => {
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
  video.srcObject = null;
  startCam.disabled = false;
  stopCam.disabled = true;
});

// 抓当前帧 → 降分到宽 512(design.md §14 图像降分辨率)→ jpeg dataURL
function grabFrame() {
  if (!stream || !video.videoWidth) return null;
  const maxW = 512;
  const scale = Math.min(1, maxW / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.8);
}

askForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const question = questionEl.value.trim();
  if (!question) return;

  const image = grabFrame();
  addLine('我', question + (image ? ' 📷' : ''), 'me');
  questionEl.value = '';
  askBtn.disabled = true;
  const pending = addLine('AI', '思考中…', 'ai');

  try {
    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, image }),
    });
    const j = await r.json();
    const txt = pending.querySelector('.txt');
    if (!r.ok) {
      txt.textContent = '错误：' + (j.error || r.status);
      pending.classList.add('err');
    } else {
      const tag = j.source === 'mock' ? '（Mock）' : '';
      const tok = j.tokens ? ` · token ${j.tokens.input}/${j.tokens.output}` : '';
      txt.textContent = j.answer + tag;
      const meta = document.createElement('span');
      meta.className = 'meta';
      meta.textContent = tag ? '降级示例' + tok : '来源 M3' + tok;
      pending.appendChild(meta);
    }
  } catch (e) {
    pending.querySelector('.txt').textContent = '请求失败：' + e.message;
    pending.classList.add('err');
  } finally {
    askBtn.disabled = false;
  }
});

refreshHealth();
