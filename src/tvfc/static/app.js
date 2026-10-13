'use strict';
const $ = id => document.getElementById(id);
const sensitivityLabel = value => ({high: '標準設定', standard: '低感度'})[value] || value;
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has('token')) {
  sessionStorage.setItem('tvfc-token', fragment.get('token'));
  history.replaceState(null, '', location.pathname);
}
const token = sessionStorage.getItem('tvfc-token') || '';
let busy = false;
let timer = null;
let loaded = false;
let copying = false;
let copyCancelled = false;
let quitting = false;
let lastAnnouncement = '';
let playbackObjectUrl = null;
let playbackReady = false;
let playbackDuration = 0;
let playbackGeneration = 0;
let chartPlayhead = null;
let overviewPlayhead = null;
let overviewWindow = null;
let currentReport = null;
let chartWindowDuration = 0;
let chartWindowStart = 0;
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-TVFC-Token', token);
  const response = await fetch(path, {...options, headers, cache: 'no-store'});
  if (!response.ok) {
    let message = '操作に失敗しました。アプリから開いた画面か確認してください。';
    try { message = (await response.json()).error || message; } catch (_) { /* HTML error page */ }
    throw new Error(message);
  }
  return response;
}
function setBusy(value) {
  busy = value;
  for (const id of ['start', 'video', 'youtube-url', 'sensitivity', 'region-mode',
    'open-file', 'open-url', 'menu-file-open', 'menu-url-open']) $(id).disabled = value;
  document.querySelectorAll('[name="source"]').forEach(node => node.disabled = value);
  $('cancel').disabled = !value;
  $('save-main').disabled = value || !loaded;
  document.querySelectorAll('[data-format]').forEach(node => node.disabled = value || !loaded);
  $('menu-show-candidates').disabled = !loaded || !currentReport?.candidates.length;
}
function chooseSource() {
  const youtube = document.querySelector('[name="source"]:checked').value === 'youtube';
  $('file-source').hidden = youtube;
  $('youtube-source').hidden = !youtube;
  $('video').required = !youtube;
  $('youtube-url').required = youtube;
  $('source-name').textContent = youtube ? 'YouTube URL' :
    ($('video').files[0]?.name || '動画未選択');
}
document.querySelectorAll('[name="source"]').forEach(node => node.addEventListener('change', chooseSource));
$('video').addEventListener('change', chooseSource);
function closeMenus() {
  document.querySelectorAll('.app-menu .menu').forEach(menu => menu.open = false);
}
const menus = [...document.querySelectorAll('.app-menu .menu')];
function enabledMenuItems(menu) {
  return [...menu.querySelectorAll('.menu-items button:not(:disabled)')];
}
function focusMenuItem(menu, last = false) {
  const items = enabledMenuItems(menu);
  items[last ? items.length - 1 : 0]?.focus();
}
function switchMenu(index) {
  closeMenus();
  const menu = menus[(index + menus.length) % menus.length];
  menu.open = true;
  focusMenuItem(menu);
}
function openFile() {
  if (busy) return;
  $('source-details').open = true;
  document.querySelector('[name="source"][value="file"]').checked = true;
  chooseSource();
  $('video').click();
}
function openUrl() {
  if (busy) return;
  $('source-details').open = true;
  document.querySelector('[name="source"][value="youtube"]').checked = true;
  chooseSource();
  $('youtube-url').focus();
}
for (const id of ['open-file', 'menu-file-open']) $(id).addEventListener('click', openFile);
for (const id of ['open-url', 'menu-url-open']) $(id).addEventListener('click', openUrl);
$('save-main').addEventListener('click', () => document.querySelector('[data-format="html"]').click());
$('menu-show-source').addEventListener('click', () => {
  $('source-details').open = true;
  $('source-details').scrollIntoView({block:'start'});
  $('source-details').querySelector('summary').focus();
});
$('menu-show-settings').addEventListener('click', () => {
  $('source-details').open = true;
  $('settings-details').open = true;
  $('settings-details').scrollIntoView({block:'start'});
  $('settings-details').querySelector('summary').focus();
});
$('menu-show-candidates').addEventListener('click', () => {
  $('candidate-index').scrollIntoView({block:'start'});
  $('candidate-select').focus();
});
function showDialog(id) {
  if (!$(id).open) $(id).showModal();
}
$('menu-help-guide').addEventListener('click', () => showDialog('guide-dialog'));
$('menu-help-detection').addEventListener('click', () => showDialog('detection-dialog'));
async function showLicenses() {
  showDialog('license-dialog');
  try {
    const [mainLicense, notices, index] = await Promise.all([
      fetch('/legal/license', {cache: 'no-store'}),
      fetch('/legal/notices', {cache: 'no-store'}),
      fetch('/legal/licenses', {cache: 'no-store'})
    ]);
    if (!mainLicense.ok || !notices.ok || !index.ok) throw new Error('ライセンス情報を読み込めませんでした。');
    $('app-license').textContent = await mainLicense.text();
    $('license-notices').textContent = await notices.text();
    const {files} = await index.json();
    $('license-file').replaceChildren(new Option('原文を選択', ''));
    for (const file of files) $('license-file').add(new Option(file, file));
    $('license-error').textContent = '';
  } catch (error) {
    $('app-license').textContent = 'MITライセンス原文を表示できませんでした。';
    $('license-notices').textContent = '一覧を表示できませんでした。';
    $('license-error').textContent = error.message;
  }
}
$('menu-help-license').addEventListener('click', showLicenses);
$('license-file').addEventListener('change', async () => {
  const name = $('license-file').value;
  $('license-content').hidden = !name;
  if (!name) return;
  $('license-content').textContent = '読み込み中…';
  try {
    const response = await fetch(`/legal/licenses/${name.split('/').map(encodeURIComponent).join('/')}`,
      {cache: 'no-store'});
    if (!response.ok) throw new Error('ライセンス原文を読み込めませんでした。');
    const content = await response.text();
    if ($('license-file').value === name) $('license-content').textContent = content;
    $('license-error').textContent = '';
  } catch (error) {
    $('license-content').textContent = '';
    $('license-error').textContent = error.message;
  }
});
$('menu-help-about').addEventListener('click', () => showDialog('about-dialog'));
menus.forEach((menu, index) => {
  const summary = menu.querySelector('summary');
  menu.addEventListener('keydown', event => {
    const onSummary = event.target === summary;
    const key = event.key;
    if (key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenus();
      summary.focus();
      return;
    }
    if (key === 'ArrowRight' || key === 'ArrowLeft') {
      event.preventDefault();
      switchMenu(index + (key === 'ArrowRight' ? 1 : -1));
      return;
    }
    if (onSummary && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(key)) {
      event.preventDefault();
      menu.open = true;
      focusMenuItem(menu, key === 'ArrowUp');
      return;
    }
    if (!onSummary && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) {
      event.preventDefault();
      const items = enabledMenuItems(menu);
      const position = items.indexOf(event.target);
      const next = key === 'Home' ? 0 : key === 'End' ? items.length - 1 :
        (position + (key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }
  });
  menu.addEventListener('toggle', () => {
    if (menu.open) menus.forEach(other => {
      if (other !== menu) other.open = false;
    });
  });
  menu.querySelectorAll('button').forEach(button => button.addEventListener('click', closeMenus));
});
document.addEventListener('focusin', event => {
  if (!event.target.closest('.app-menu')) closeMenus();
});
document.addEventListener('click', event => {
  if (!event.target.closest('.app-menu')) closeMenus();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') { closeMenus(); return; }
  if (event.key === 'F1') {
    event.preventDefault();
    showDialog('guide-dialog');
    return;
  }
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === 'q') { event.preventDefault(); quitApp(); }
  else if (key === 'o') { event.preventDefault(); openFile(); }
  else if (key === 's') {
    event.preventDefault();
    if (!$('save-main').disabled) $('save-main').click();
  } else if (key === 'enter') {
    event.preventDefault();
    if (!$('start').disabled) $('start').click();
  }
});
function element(tag, text, parent) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (parent) parent.append(node);
  return node;
}
function formatTime(seconds) {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${String(Math.floor(safe % 60)).padStart(2, '0')}.${String(Math.floor(safe * 1000) % 1000).padStart(3, '0')}`;
}
function updatePlaybackPosition(seconds) {
  const value = Math.max(0, Math.min(playbackDuration, seconds));
  $('playback-position').value = String(value);
  $('playback-time').textContent = formatTime(value);
  if (chartPlayhead && playbackDuration > 0) {
    if (value < chartWindowStart || value > chartWindowStart + chartWindowDuration) {
      setChartWindowStart(value - chartWindowDuration / 2);
    }
    const x = (value - chartWindowStart) / chartWindowDuration * 1000;
    chartPlayhead.setAttribute('x1', x);
    chartPlayhead.setAttribute('x2', x);
  }
  if (overviewPlayhead && playbackDuration > 0) {
    const x = value / playbackDuration * 1000;
    overviewPlayhead.setAttribute('x1', x);
    overviewPlayhead.setAttribute('x2', x);
  }
}
function seekTo(seconds) {
  if (!playbackReady) return;
  const video = $('playback-video');
  video.pause();
  video.currentTime = Math.max(0, Math.min(playbackDuration, seconds));
  setChartWindowStart(video.currentTime - chartWindowDuration / 2);
  updatePlaybackPosition(video.currentTime);
}
function clearPlayback() {
  playbackGeneration += 1;
  playbackReady = false;
  playbackDuration = 0;
  chartPlayhead = null;
  overviewPlayhead = null;
  overviewWindow = null;
  currentReport = null;
  chartWindowStart = 0;
  chartWindowDuration = 0;
  const video = $('playback-video');
  video.pause();
  video.removeAttribute('src');
  video.load();
  video.hidden = true;
  $('playback-position').disabled = true;
  $('playback-position').max = '0';
  $('playback-time').textContent = '0:00.000';
  document.querySelectorAll('.seek-button').forEach(button => button.disabled = true);
  if (playbackObjectUrl) URL.revokeObjectURL(playbackObjectUrl);
  playbackObjectUrl = null;
}
async function setupPlayback(report) {
  const generation = playbackGeneration;
  const video = $('playback-video');
  $('playback-status').textContent = '再生元を準備しています。';
  let source;
  if (report.source_url) {
    try { source = (await (await api('/api/playback')).json()).url; }
    catch (_) { source = null; }
  } else {
    const file = $('video').files[0];
    if (file && file.name === report.filename && file.size === report.metadata.size_bytes) {
      playbackObjectUrl = URL.createObjectURL(file);
      source = playbackObjectUrl;
    }
  }
  if (generation !== playbackGeneration) return;
  if (!source) {
    $('playback-status').textContent = '再生元がありません。端末内の動画は、同じファイルを選び直して再解析してください。';
    return;
  }
  video.hidden = false;
  video.src = source;
  video.load();
}
function svgElement(parent, tag, attributes, className) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (className) node.setAttribute('class', className);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  parent.append(node);
  return node;
}
function firstPointAtOrAfter(points, time) {
  let low = 0, high = points.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (points[middle].time < time) low = middle + 1;
    else high = middle;
  }
  return low;
}
function setChartWindowStart(start, moveScroll = true) {
  if (!currentReport) return;
  const duration = currentReport.metadata.duration;
  chartWindowStart = Math.max(0, Math.min(duration - chartWindowDuration, start));
  if (moveScroll) {
    const scroller = $('chart-scroll');
    const maximum = scroller.scrollWidth - scroller.clientWidth;
    scroller.scrollLeft = maximum * chartWindowStart / Math.max(1, duration - chartWindowDuration);
  }
  renderDetailChart();
  const map = $('overview-map');
  map.setAttribute('aria-valuenow', chartWindowStart.toFixed(3));
  map.setAttribute('aria-valuetext', `${formatTime(chartWindowStart)}から${formatTime(chartWindowStart + chartWindowDuration)}`);
  if (overviewWindow) overviewWindow.setAttribute('x', chartWindowStart / duration * 1000);
  $('chart-duration').textContent = `詳細表示：${formatTime(chartWindowStart)}〜${formatTime(chartWindowStart + chartWindowDuration)}。グラフをクリックすると動画の時刻へ移動します。`;
}
function renderDetailChart() {
  if (!currentReport) return;
  const report = currentReport;
  const target = $('chart');
  target.replaceChildren();
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 1000 160');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '表示区間の明暗と赤色指標の変化。候補の正確な時刻は下の一覧にあります。');
  if (playbackReady) svg.classList.add('seekable');
  const startTime = chartWindowStart;
  const endTime = startTime + chartWindowDuration;
  for (const candidate of report.candidates) {
    if (candidate.end < startTime || candidate.start > endTime) continue;
    const start = Math.max(0, (candidate.start - startTime) / chartWindowDuration * 1000);
    const end = Math.min(1000, (candidate.end - startTime) / chartWindowDuration * 1000);
    svgElement(svg, 'rect', {x:start, y:0, width:Math.max(2, end-start), height:150}, 'candidate-band');
  }
  svgElement(svg, 'line', {x1:0, y1:150, x2:1000, y2:150}, 'baseline');
  const points = report.detail_timeline || report.timeline || [];
  const first = firstPointAtOrAfter(points, startTime);
  const last = firstPointAtOrAfter(points, endTime);
  for (const [field, className] of [['luminance','luminance'], ['red','red']]) {
    const segments = points.slice(first, last).map(point => {
      const x = Math.max(0, Math.min(1000, (point.time - startTime) / chartWindowDuration * 1000));
      const y = 150 - Math.max(0, Math.min(1, point[field])) * 145;
      return `M${x.toFixed(2)} 150L${x.toFixed(2)} ${y.toFixed(2)}`;
    });
    svgElement(svg, 'path', {d:segments.join(''), fill:'none'}, className);
  }
  const time = $('playback-video').currentTime || 0;
  const head = (time - startTime) / chartWindowDuration * 1000;
  svgElement(svg, 'line', {x1:head, y1:0, x2:head, y2:150}, 'playhead');
  chartPlayhead = svg.querySelector('.playhead');
  svg.addEventListener('click', event => {
    if (!playbackReady) return;
    const rect = svg.getBoundingClientRect();
    seekTo(startTime + (event.clientX - rect.left) / rect.width * chartWindowDuration);
  });
  target.append(svg);
}
function renderChart(report) {
  currentReport = report;
  const duration = report.metadata.duration;
  chartWindowDuration = Math.min(30, duration);
  const map = $('overview-map');
  map.replaceChildren();
  map.setAttribute('aria-valuemax', Math.max(0, duration - chartWindowDuration).toFixed(3));
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 1000 36');
  svg.setAttribute('aria-hidden', 'true');
  svgElement(svg, 'rect', {x:0, y:0, width:1000, height:36}, 'map-background');
  for (const point of report.timeline || []) {
    const x = Math.max(0, Math.min(1000, point.time / duration * 1000));
    const intensity = Math.max(point.luminance, point.red);
    svgElement(svg, 'rect', {x, y:3, width:Math.max(1, 1000 / 1200), height:22,
      opacity:(.12 + .88 * intensity).toFixed(3)}, 'map-change');
  }
  for (const candidate of report.candidates) {
    const x = Math.max(0, Math.min(1000, candidate.start / duration * 1000));
    const end = Math.max(x, Math.min(1000, candidate.end / duration * 1000));
    svgElement(svg, 'rect', {x, y:27, width:Math.max(2, end-x), height:7}, 'map-candidate');
  }
  overviewWindow = svgElement(svg, 'rect', {x:0, y:0,
    width:Math.max(2, chartWindowDuration / duration * 1000), height:36}, 'map-window');
  overviewPlayhead = svgElement(svg, 'line', {x1:0, y1:0, x2:0, y2:36}, 'map-playhead');
  map.append(svg);
  const scroller = $('chart-scroll');
  const width = Math.max(1, scroller.clientWidth);
  $('chart').style.width = `${width}px`;
  $('chart-track').style.width = `${Math.max(width, Math.round(duration / chartWindowDuration * width))}px`;
  setChartWindowStart(0);
}
$('overview-map').addEventListener('click', event => {
  if (!currentReport) return;
  const bounds = $('overview-map').getBoundingClientRect();
  setChartWindowStart((event.clientX - bounds.left) / bounds.width * currentReport.metadata.duration - chartWindowDuration / 2);
});
$('overview-map').addEventListener('keydown', event => {
  if (!currentReport) return;
  const step = Math.max(1, chartWindowDuration / 5);
  let start = chartWindowStart;
  if (event.key === 'ArrowLeft') start -= step;
  else if (event.key === 'ArrowRight') start += step;
  else if (event.key === 'PageUp') start -= chartWindowDuration;
  else if (event.key === 'PageDown') start += chartWindowDuration;
  else if (event.key === 'Home') start = 0;
  else if (event.key === 'End') start = currentReport.metadata.duration;
  else return;
  event.preventDefault();
  setChartWindowStart(start);
});
$('chart-scroll').addEventListener('scroll', () => {
  if (!currentReport) return;
  const scroller = $('chart-scroll');
  const maximum = scroller.scrollWidth - scroller.clientWidth;
  setChartWindowStart(maximum ? scroller.scrollLeft / maximum *
    (currentReport.metadata.duration - chartWindowDuration) : 0, false);
});
window.addEventListener('resize', () => {
  if (!currentReport) return;
  const scroller = $('chart-scroll');
  const width = Math.max(1, scroller.clientWidth);
  $('chart').style.width = `${width}px`;
  $('chart-track').style.width = `${Math.max(width, Math.round(currentReport.metadata.duration / chartWindowDuration * width))}px`;
  setChartWindowStart(chartWindowStart);
});
async function render(report) {
  clearPlayback();
  playbackDuration = report.metadata.duration;
  $('results-panel').hidden = false;
  $('empty-state').hidden = true;
  $('source-details').open = false;
  $('summary').textContent = report.candidates.length ? `要確認候補 ${report.candidates.length}件：${report.filename}` : `今回の検出条件では候補なし：${report.filename}`;
  $('measurement').textContent = `${report.frames}フレーム ／ 動画 ${report.metadata.duration.toFixed(2)}秒 ／ 解析 ${report.elapsed.toFixed(2)}秒`;
  $('conditions').textContent = JSON.stringify({動画: report.metadata, 取得元URL: report.source_url || null,
    感度: sensitivityLabel(report.settings.sensitivity), 設定: report.settings, 解析版: report.app_version}, null, 2);
  $('limitations').replaceChildren();
  for (const text of report.limitations) element('li', text, $('limitations'));
  $('candidates').replaceChildren();
  $('candidate-select').replaceChildren();
  $('candidate-index').hidden = report.candidates.length === 0;
  renderChart(report);
  report.candidates.forEach((candidate, index) => {
    const option = element('option', `候補 ${index + 1}：${formatTime(candidate.start)}`, $('candidate-select'));
    option.value = String(index);
    const section = element('section', undefined, $('candidates'));
    section.className = 'candidate';
    section.id = `candidate-${index + 1}`;
    element('h3', `候補 ${index + 1}：${candidate.start.toFixed(3)}〜${candidate.end.toFixed(3)}秒`, section);
    const jump = element('button', `候補 ${index + 1} の開始時刻へ移動`, section);
    jump.type = 'button';
    jump.className = 'secondary seek-button';
    jump.disabled = true;
    jump.addEventListener('click', () => seekTo(candidate.start));
    const preview = element('div', undefined, section);
    preview.className = 'preview';
    const img = element('img', undefined, preview);
    img.src = `data:image/png;base64,${candidate.thumbnail}`;
    img.alt = `候補${index+1}の静止画。検出領域の説明は以下にあります。`;
    const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 100 100');
    svg.setAttribute('preserveAspectRatio','none');
    svg.setAttribute('aria-hidden','true');
    preview.append(svg);
    const seen = new Set();
    for (const evidence of candidate.evidence) {
      if (seen.has(evidence.region)) continue;
      seen.add(evidence.region);
      const [x0,y0,x1,y1] = evidence.box;
      const rect = document.createElementNS(svg.namespaceURI,'rect');
      for (const [key,value] of Object.entries({x:x0*100,y:y0*100,width:(x1-x0)*100,height:(y1-y0)*100})) rect.setAttribute(key, value);
      svg.append(rect);
    }
    element('p', `静止画：${candidate.thumbnail_time.toFixed(3)}秒。枠は区間内で検出した領域です。`, section).className = 'hint';
    const details = element('details', undefined, section);
    element('summary', '検出領域と理由を見る', details);
    const list = element('ul', undefined, details);
    for (const evidence of candidate.evidence) {
      const kind = evidence.kind === 'red' ? '赤色の反復（簡易指標）' : '明暗の反復';
      element('li', `${evidence.label}：${kind}、${evidence.count}回／移動する1秒窓、変化量 ${evidence.change.toFixed(3)}（${sensitivityLabel(evidence.profile)}）`, list);
    }
  });
  $('results-title').focus();
  await setupPlayback(report);
}
$('candidate-go').addEventListener('click', () => {
  const index = Number($('candidate-select').value);
  const candidate = currentReport?.candidates[index];
  if (!candidate) return;
  $(`candidate-${index + 1}`).scrollIntoView({block:'start'});
  if (playbackReady) seekTo(candidate.start);
});
$('playback-video').addEventListener('loadedmetadata', () => {
  const duration = $('playback-video').duration;
  if (!Number.isFinite(duration) || duration <= 0) return;
  playbackReady = true;
  playbackDuration = duration;
  $('playback-position').max = String(duration);
  $('playback-position').disabled = false;
  document.querySelectorAll('.seek-button').forEach(button => button.disabled = false);
  $('chart').querySelector('svg')?.classList.add('seekable');
  $('playback-status').textContent = '再生位置を選べます。動画は一時停止しています。';
  updatePlaybackPosition($('playback-video').currentTime);
});
$('playback-video').addEventListener('timeupdate', () => updatePlaybackPosition($('playback-video').currentTime));
$('playback-video').addEventListener('seeked', () => updatePlaybackPosition($('playback-video').currentTime));
$('playback-video').addEventListener('error', () => {
  if ($('playback-video').getAttribute('src')) {
    playbackReady = false;
    $('playback-position').disabled = true;
    document.querySelectorAll('.seek-button').forEach(button => button.disabled = true);
    $('playback-status').textContent = 'この環境では動画を再生できません。静止画と時刻は引き続き確認できます。';
  }
});
$('playback-position').addEventListener('input', () => {
  $('playback-time').textContent = formatTime(Number($('playback-position').value));
});
$('playback-position').addEventListener('change', () => seekTo(Number($('playback-position').value)));
async function poll() {
  clearTimeout(timer);
  try {
    const state = await (await api('/api/status')).json();
    const active = ['uploading','downloading','running','cancelling'].includes(state.state);
    setBusy(active || copying);
    if (state.state === 'downloading' && !state.progress.total_bytes) {
      $('progress').removeAttribute('value');
    } else {
      $('progress').value = state.state === 'completed' ? 100 : state.progress.percent || 0;
    }
    $('elapsed').textContent = `経過時間：${Math.floor(state.elapsed)}秒`;
    const bucket = Math.floor((state.progress.percent || 0) / 10) * 10;
    const announcement = `${state.state}:${bucket}`;
    if (lastAnnouncement !== announcement) {
      const hasPercent = state.state === 'running' ||
        (state.state === 'downloading' && state.progress.total_bytes);
      $('status').textContent = state.message + (hasPercent ? ` 約${bucket}%` : '');
      lastAnnouncement = announcement;
    }
    if (['failed','unsupported'].includes(state.state)) $('error').textContent = state.message;
    if (state.state === 'completed' && !loaded) {
      await render(await (await api('/api/result')).json());
      loaded = true;
      setBusy(false);
    }
    if (active) timer = setTimeout(poll, 500);
  } catch (error) { $('error').textContent = error.message; setBusy(false); }
}
$('analysis-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const youtube = document.querySelector('[name="source"]:checked').value === 'youtube';
  const file = $('video').files[0];
  if (!youtube && !file) return;
  if (!youtube && (file.size > 4 * 1024**3 || file.size === 0)) {
    $('error').textContent = '空でない4GiB以内の動画を選択してください。'; return;
  }
  $('error').textContent = '';
  clearPlayback();
  $('results-panel').hidden = true;
  $('empty-state').hidden = true;
  $('progress').value = 0;
  loaded = false;
  setBusy(true);
  $('status').textContent = youtube ? 'YouTubeから動画を取得しています。' : '動画を端末内の作業領域へコピーしています。';
  try {
    if (youtube) {
      await api('/api/youtube', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:$('youtube-url').value,sensitivity:$('sensitivity').value,
          region_mode:$('region-mode').value})});
      await poll();
      return;
    }
    copying = true;
    copyCancelled = false;
    const reservation = await (await api('/api/uploads', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:file.name,size:file.size,sensitivity:$('sensitivity').value,
        region_mode:$('region-mode').value})
    })).json();
    if (copyCancelled) {
      await api('/api/cancel', {method:'POST'});
      throw new Error('コピーを中止しました。');
    }
    for (let offset=0; offset<file.size; offset+=1024**2) {
      if (copyCancelled) throw new Error('コピーを中止しました。');
      await api(`/api/uploads/${reservation.upload_id}/chunk?offset=${offset}`, {
        method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file.slice(offset,offset+1024**2)
      });
      $('status').textContent = `端末内へコピー中：${Math.min(100,Math.floor((offset+1024**2)*100/file.size))}%`;
    }
    if (copyCancelled) throw new Error('コピーを中止しました。');
    await api(`/api/uploads/${reservation.upload_id}/finish`, {method:'POST'});
    copying = false;
    await poll();
  } catch (error) {
    if (!copyCancelled) $('error').textContent = error.message;
    try { await api('/api/cancel', {method:'POST'}); } catch (_) { /* connection may be closed */ }
    copying = false; setBusy(false); clearTimeout(timer); await poll();
  }
});
$('cancel').addEventListener('click', async () => {
  copyCancelled = true;
  try { await api('/api/cancel', {method:'POST'}); await poll(); }
  catch (error) { $('error').textContent = error.message; }
});
function reportFilename(format) {
  const source = String(currentReport?.filename || 'video').split(/[/\\]/).pop();
  let stem = source.replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_')
    .replace(/[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/g, '')
    .trim().replace(/[. ]+$/g, '');
  const characters = Array.from(stem).slice(0, 120);
  while (new TextEncoder().encode(characters.join('')).length > 200) characters.pop();
  stem = characters.join('') || 'video';
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(stem)) stem = `_${stem}`;
  return `${stem}.${format}`;
}
for (const button of document.querySelectorAll('[data-format]')) {
  button.addEventListener('click', async () => {
    try {
      const format = button.dataset.format;
      const filename = reportFilename(format);
      if (window.webkit?.messageHandlers?.tvfc) {
        window.webkit.messageHandlers.tvfc.postMessage(JSON.stringify({format, filename}));
        return;
      }
      const response = await api(`/api/report/${format}`);
      const url = URL.createObjectURL(await response.blob());
      const link = element('a');
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (error) { $('error').textContent = error.message; }
  });
}
async function quitApp() {
  if (quitting) return;
  quitting = true;
  closeMenus();
  copyCancelled = true;
  clearTimeout(timer);
  try {
    clearPlayback();
    let state = await (await api('/api/status')).json();
    const active = ['uploading', 'downloading', 'running', 'cancelling'];
    if (active.includes(state.state) || copying) {
      $('status').textContent = '処理を中止して終了しています。';
      await api('/api/cancel', {method:'POST'});
      for (let attempt = 0; attempt < 200; attempt++) {
        state = await (await api('/api/status')).json();
        if (!active.includes(state.state)) break;
        await new Promise(resolve => setTimeout(resolve, 300));
      }
      if (active.includes(state.state)) throw new Error('中止の完了を待っています。終了操作をもう一度お試しください。');
    }
    const result = await (await api('/api/shutdown', {method:'POST'})).json();
    $('status').textContent = result.message;
    document.querySelectorAll('button,input,select').forEach(node => node.disabled = true);
    sessionStorage.removeItem('tvfc-token');
  } catch (error) { quitting = false; $('error').textContent = error.message; }
}
$('quit').addEventListener('click', quitApp);
if (token) poll();
else { $('error').textContent = 'アプリを起動して表示されたURLから開いてください。'; $('start').disabled = true; }
