'use strict';

// ── 상태 ────────────────────────────────────────────────────────────────────
let stream      = null;
let captureLoop = null;
let lastText    = '';
let shotCount   = 0;
let sentCount   = 0;
let activeTab   = 'camera';

// ── DOM ─────────────────────────────────────────────────────────────────────
const video      = document.getElementById('video');
const canvas     = document.getElementById('canvas');
const ctx        = canvas.getContext('2d');
const elTrans    = document.getElementById('translation');
const elOrig     = document.getElementById('original');
const elStatus   = document.getElementById('status');
const elTimer    = document.getElementById('timerLabel');
const elStart    = document.getElementById('btnStart');
const elStop     = document.getElementById('btnStop');

// ── 설정 로드/저장 ─────────────────────────────────────────────────────────
function loadSettings() {
  document.getElementById('misterIp').value = localStorage.getItem('misterIp') || '';
}
function saveSettings() {
  localStorage.setItem('misterIp', document.getElementById('misterIp').value.trim());
}
loadSettings();

// ── 탭 전환 ─────────────────────────────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  document.getElementById('tabCamera').classList.toggle('tab-active', tab === 'camera');
  document.getElementById('tabConfig').classList.toggle('tab-active', tab === 'config');
  document.getElementById('viewCamera').style.display = tab === 'camera' ? '' : 'none';
  document.getElementById('viewConfig').style.display = tab === 'config' ? '' : 'none';
}

// ── Provider 선택 ─────────────────────────────────────────────────────────
let currentProvider = localStorage.getItem('provider') || 'claude';

function selectProvider(p) {
  currentProvider = p;
  localStorage.setItem('provider', p);
  document.getElementById('btnProviderClaude').classList.toggle('provider-active', p === 'claude');
  document.getElementById('btnProviderOpenAI').classList.toggle('provider-active', p === 'openai');

  const ip = document.getElementById('misterIp').value.trim();
  if (!ip) return;
  fetch(`http://${ip}:18765/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: p }),
  }).catch(() => {});
}

// ── API Key 저장 ──────────────────────────────────────────────────────────
async function saveKey(provider) {
  const ip  = document.getElementById('misterIp').value.trim();
  const key = document.getElementById(provider === 'claude' ? 'claudeKeyInput' : 'openaiKeyInput').value.trim();
  if (!ip)  { setConfigStatus('MiSTer IP를 입력하세요', 'err'); return; }
  if (!key) { setConfigStatus('API Key를 입력하세요', 'err'); return; }

  const payload = {};
  payload[provider === 'claude' ? 'claude_api_key' : 'openai_api_key'] = key;

  try {
    const res = await fetch(`http://${ip}:18765/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      document.getElementById(provider === 'claude' ? 'claudeKeyInput' : 'openaiKeyInput').value = '';
      document.getElementById(provider === 'claude' ? 'claudeStatus' : 'openaiStatus').textContent = '✓ 설정됨';
      setConfigStatus('✓ 저장됨', 'ok');
      saveSettings();
    } else {
      setConfigStatus('저장 실패: ' + res.status, 'err');
    }
  } catch (e) {
    setConfigStatus('MiSTer 연결 실패: ' + e.message, 'err');
  }
}

// ── 설정 현황 확인 ─────────────────────────────────────────────────────────
async function checkConfig() {
  const ip = document.getElementById('misterIp').value.trim();
  if (!ip) { setConfigStatus('MiSTer IP를 입력하세요', 'err'); return; }
  saveSettings();

  try {
    const res = await fetch(`http://${ip}:18765/config`);
    if (!res.ok) { setConfigStatus('조회 실패: ' + res.status, 'err'); return; }

    const data = await res.json();

    // provider 반영
    selectProvider(data.provider || 'claude');

    // key 상태 표시
    document.getElementById('claudeStatus').textContent = data.claude_api_key ? '✓ 설정됨' : '';
    document.getElementById('openaiStatus').textContent = data.openai_api_key ? '✓ 설정됨' : '';

    const active = data.provider === 'openai' ? 'OpenAI' : 'Claude';
    setConfigStatus(`✓ 연결됨 — ${active} 사용 중`, 'ok');
  } catch (e) {
    setConfigStatus('MiSTer 연결 실패: ' + e.message, 'err');
  }
}

function setConfigStatus(msg, cls = '') {
  const el = document.getElementById('configStatus');
  el.textContent = msg;
  el.className = 'config-status ' + cls;
}

// 초기 provider 버튼 상태
selectProvider(currentProvider);

// ── 카메라 시작 ─────────────────────────────────────────────────────────────
async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    return true;
  } catch (e) {
    setStatus('카메라 권한이 필요합니다: ' + e.message, 'err');
    return false;
  }
}

// ── 프레임 캡처 → base64 ────────────────────────────────────────────────────
function captureFrame() {
  const w = video.videoWidth  || 1280;
  const h = video.videoHeight || 720;
  canvas.width  = Math.min(w, 960);
  canvas.height = Math.round(h * (canvas.width / w));
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
}

// ── MiSTer /translate 호출 ──────────────────────────────────────────────────
async function translateFrame(base64) {
  const ip = document.getElementById('misterIp').value.trim();
  if (!ip) throw new Error('MiSTer IP 없음');

  const res = await fetch(`http://${ip}:18765/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: base64 }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.status }));
    throw new Error(err.error || `서버 오류 ${res.status}`);
  }

  return res.json();
}

// ── 한 사이클 처리 ──────────────────────────────────────────────────────────
async function processCycle() {
  shotCount++;
  elTimer.textContent = `${shotCount}컷 / ${sentCount}전송`;

  let base64;
  try {
    base64 = captureFrame();
  } catch (e) {
    setStatus('캡처 오류: ' + e.message, 'err');
    return;
  }

  setStatus('<span class="dot"></span>분석 중...');

  try {
    const result = await translateFrame(base64);

    if (!result.found) {
      setStatus('일본어 없음', 'ok');
      elOrig.textContent = '';
      return;
    }

    const translation = result.translation || '';
    const original    = result.original    || '';

    elTrans.textContent = translation;
    elOrig.textContent  = original;

    // OSD 전송은 서버가 처리 — 중복 표시만 막기
    if (translation === lastText) {
      setStatus('중복 — 스킵', '');
      return;
    }
    lastText = translation;

    sentCount++;
    setStatus(`✓ OSD 표시 완료 (${sentCount}회)`, 'ok');

  } catch (e) {
    setStatus('오류: ' + e.message, 'err');
    console.error(e);
  }
}

// ── 시작/정지 ────────────────────────────────────────────────────────────────
async function startCapture() {
  saveSettings();

  const ip = document.getElementById('misterIp').value.trim();
  if (!ip) {
    setStatus('MiSTer IP를 입력하세요', 'err');
    return;
  }

  if (!stream) {
    const ok = await startCamera();
    if (!ok) return;
  }

  if (captureLoop) return;

  const ms = parseInt(document.getElementById('interval').value, 10);

  elStart.disabled = true;
  elStop.classList.add('active');
  setStatus('실행 중...', 'ok');

  await processCycle();
  captureLoop = setInterval(processCycle, ms);
}

function stopCapture() {
  if (captureLoop) { clearInterval(captureLoop); captureLoop = null; }
  elStart.disabled = false;
  elStop.classList.remove('active');
  setStatus('정지됨');
}

// ── 유틸 ─────────────────────────────────────────────────────────────────────
function setStatus(msg, cls = '') {
  elStatus.innerHTML  = msg;
  elStatus.className  = cls;
}
