import {clone, frames, actionSteps, reviewSteps, editFrames, defaultReviews, reconcileReviewRanges, merge} from './model.js';
import {Player} from './player.js';

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid = prefix => `${prefix}_${Date.now().toString(36)}`;
const label = (name, body) => `<label class="field">${name}${body}</label>`;
const number = (id, value, attributes = '') => `<input id="${id}" type="number" value="${escape(value)}" ${attributes} ${attributes.includes('placeholder=') ? '' : 'required'}>`;
const info = (key, value) => `<div class="info-row"><span>${key}</span><strong>${escape(value)}</strong></div>`;
const section = (title, body) => `<section class="inspector-section"><h3>${title}</h3>${body}</section>`;
const state = {mode:'action', data:null, revision:null, token:null, assets:[], sources:[], action:null, source:null, review:null,
  selected:0, clip:0, playbackMode:'runtime', sourceView:'processed', preview:null, previewSource:null, previewError:null,
  history:[], future:[], saved:null, busy:false, previewEpoch:0};
let previewTimer, toastTimer;

const player = new Player($('#stage'), $('#canvas-area'), onStep);
function toast(message, error = false) {
  const box = $('#toast'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false;
  $('#status-message').textContent = message;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, error ? 10000 : 4000);
}
async function api(path, payload, binary = false) {
  const response = await fetch(`/api/${path}`, payload === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-Workbench-Token':state.token}, body:JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.error || (typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail)) || `请求失败 (${response.status})`);
  }
  return binary ? response : response.json();
}
const payload = extra => ({data:state.data, revision:state.revision, ...extra});
async function task(message, operation) {
  if (state.busy) return;
  state.busy = true; $('#canvas-loading').hidden = false; $('#canvas-loading').textContent = message;
  ['.workspace','.modebar','.top-actions'].forEach(selector => { $(selector).inert = true; });
  try { return await operation(); }
  catch (error) { toast(error.message, true); }
  finally { state.busy = false; $('#canvas-loading').hidden = true; ['.workspace','.modebar','.top-actions'].forEach(selector => { $(selector).inert = false; }); updateSaveStatus(); }
}
function reviews() { return state.data.workbench?.reviews || {}; }
function currentReview() { return reviews()[state.review]; }
function currentAction() { return state.data.actions[state.action]; }
function sourceInfo() { return state.sources.find(source => source.file === state.source); }
function asset(ref) { return state.assets.find(item => item.ref === ref); }
function dirty() { return state.data && JSON.stringify(state.data) !== state.saved; }
function updateSaveStatus() {
  $('#save-status').textContent = state.busy ? '正在处理…' : dirty() ? '● 有未保存的更改' : '✓ 工程已保存';
  $('#save-status').classList.toggle('dirty', !!dirty());
  $('#undo').disabled = !state.history.length; $('#redo').disabled = !state.future.length;
  $('#save').disabled = state.busy || !dirty();
}
function checkpoint() {
  state.history.push(clone(state.data)); if (state.history.length > 60) state.history.shift(); state.future = [];
}
function change(operation, {render = true, preview = false} = {}) {
  checkpoint(); operation(); reconcileReviewRanges(state.data); state.previewEpoch++;
  if (state.mode === 'source' && preview) schedulePreview();
  if (render) renderAll(); else updateSaveStatus();
}
function setSnapshot(snapshot) {
  state.data = snapshot.data; state.revision = snapshot.revision; state.assets = snapshot.assets; state.sources = snapshot.sources;
  state.token = snapshot.token || state.token; state.saved = JSON.stringify(snapshot.data);
  state.legacyCount = snapshot.legacy_count; state.history = []; state.future = [];
  state.action = state.data.actions[state.action] ? state.action : Object.keys(state.data.actions)[0];
  state.source = state.sources.some(s => s.file === state.source) ? state.source : state.sources[0]?.file;
  state.review = reviews()[state.review] ? state.review : Object.keys(reviews())[0];
  state.preview = null; state.previewSource = null; state.previewError = null; state.previewEpoch++;
  player.setProject(state.data, state.assets); renderAll();
}
async function loadProject() {
  const snapshot = await api('project'); setSnapshot(snapshot);
  $('#project-name').textContent = `${snapshot.data.character} / ${snapshot.project_file}`;
  // Suggested review sequences are editable drafts, never silently written.
  if (!snapshot.data.workbench?.reviews) {
    const defaults = defaultReviews(state.data);
    if (Object.keys(defaults).length) {
      checkpoint(); state.data.workbench = {...state.data.workbench, reviews:defaults};
      state.review = Object.keys(defaults)[0]; renderAll();
    }
  }
  if (!state.assets.length) toast('还没有 processed 素材：点击“准备缺失素材”，或“保留已有最终帧”。');
}
async function save() {
  return task('正在保存工程…', async () => {
    const result = await api('save', payload()); state.revision = result.revision; state.saved = JSON.stringify(state.data); toast('工程已保存');
  });
}
function mode(value) {
  state.mode = value; state.selected = 0; state.clip = 0; player.pause();
  if (value === 'source') schedulePreview(); renderAll();
}
function renderAll() {
  if (!state.data) return;
  const actionNames = Object.keys(state.data.actions);
  if (!state.data.actions[state.action]) state.action = actionNames[0];
  if (!reviews()[state.review]) state.review = Object.keys(reviews())[0];
  document.querySelectorAll('[data-mode]').forEach(button => {
    const active = button.dataset.mode === state.mode; button.classList.toggle('active', active); button.setAttribute('aria-selected', active);
  });
  $('#editor-kind').textContent = {source:'SOURCE PROCESSING',action:'ACTION EDITOR',review:'TRANSITION REVIEW'}[state.mode];
  $('#editor-title').textContent = state.mode === 'source' ? state.source || '添加原图' : state.mode === 'action' ? state.action || '新建动作' : currentReview()?.name || '新建 Review';
  $('#sidebar-title').textContent = {source:'原图',action:'动作库',review:'Review 序列'}[state.mode];
  $('#new-item').setAttribute('aria-label', {source:'导入原图',action:'新建动作',review:'新建 Review'}[state.mode]);
  $('#timeline-title').textContent = {source:'处理结果 · 点击查看单帧',action:state.playbackMode === 'runtime' ? '游戏帧时间轴' : '展示播放时间轴',review:'动作衔接时间轴'}[state.mode];
  $('#timeline-help').textContent = {source:'原图模式下拖拽画框 · 点击帧选择单独处理',action:'拖拽排序 · 点击素材添加 · Delete 移除所选帧',review:'拖拽动作片段排序 · 片段按指定次数播放'}[state.mode];
  renderItems(); renderLibraryFilters(); renderLibrary(); renderInspector(); renderTimeline(); refreshPlayer(); updateSaveStatus();
}
function renderItems() {
  const items = state.mode === 'source' ? state.sources.map(source => ({id:source.file,name:source.file,count:source.count,stale:source.stale}))
    : state.mode === 'action' ? Object.entries(state.data.actions).map(([id, action]) => ({id,name:id,count:frames(action).length}))
    : Object.entries(reviews()).map(([id, review]) => ({id,name:review.name || id,count:review.clips.length}));
  const selected = {source:state.source,action:state.action,review:state.review}[state.mode];
  $('#item-list').innerHTML = items.map(item => `<button class="item-row ${item.id === selected ? 'active' : ''}" data-item="${escape(item.id)}" title="${escape(item.name)}"><span class="item-icon">${state.mode === 'review' ? '⇢' : state.mode === 'source' ? '▧' : '▤'}</span><span class="item-name">${escape(item.name)}</span><small class="${item.stale ? 'stale' : ''}">${item.stale ? '待更新' : String(item.count).padStart(2,'0')}</small></button>`).join('') || '<p class="hint" style="padding:12px">点击 ＋ 开始创建</p>';
  $('#item-list').querySelectorAll('[data-item]').forEach(button => {
    button.onclick = () => {
      state[state.mode] = button.dataset.item; state.selected = 0; state.clip = 0; player.pause();
      if (state.mode === 'source') { state.preview = null; state.previewError = null; state.previewEpoch++; schedulePreview(); }
      renderAll();
    };
    if (state.mode === 'action') {
      button.draggable = true; button.ondragstart = event => event.dataTransfer.setData('application/x-action', button.dataset.item);
    }
  });
}
function renderLibraryFilters() {
  const select = $('#asset-source'), value = select.value;
  const groups = [...new Set(state.assets.map(a => a.ref.split('/').slice(0,-1).join('/')))];
  select.innerHTML = '<option value="">全部来源</option>' + groups.map(group => `<option value="${escape(group)}">${escape(group)}</option>`).join('');
  if (groups.includes(value)) select.value = value;
}
function renderLibrary() {
  const search = $('#asset-search').value.toLowerCase(), group = $('#asset-source').value;
  const items = state.assets.filter(a => a.ref.toLowerCase().includes(search) && (!group || a.ref.startsWith(group + '/')));
  $('#asset-count').textContent = state.assets.length;
  $('#asset-library').innerHTML = items.map(a => `<button class="asset-card" data-ref="${escape(a.ref)}" draggable="true" title="${escape(a.ref)} · 点击加入当前动作"><img src="${escape(a.url)}" alt="${escape(a.ref)}" loading="lazy"><span>${escape(a.ref)}</span><span class="asset-add">＋</span></button>`).join('') || '<p class="hint">暂无素材</p>';
  $('#asset-library').querySelectorAll('[data-ref]').forEach(card => {
    card.onclick = () => addAsset(card.dataset.ref);
    card.ondragstart = event => event.dataTransfer.setData('application/x-sprite', card.dataset.ref);
  });
}
function addAsset(ref, at) {
  if (state.mode !== 'action') { toast('切换到“动作编排”，即可将素材加入动作'); return; }
  const action = currentAction(); if (!action) { toast('请先创建一个动作'); return; }
  if (state.playbackMode === 'display') { toast('请切换到游戏帧，再添加素材；展示播放通过重复帧和排序调整'); return; }
  change(() => {
    const refs = [...frames(action)], slots = refs.map((_, i) => i), index = at ?? refs.length;
    refs.splice(index, 0, ref); slots.splice(index, 0, null); editFrames(action, slots, refs, state.data.defaults?.fps || 12); state.selected = index;
  });
}
function activeSteps() {
  if (state.mode === 'source') {
    if (state.preview && state.previewSource === state.source) return state.preview.frames.map((frame, i) => ({...frame, frame:i, duration_ms:100}));
    const prefix = state.source ? state.source.replace(/\.[^.]+$/, '') + '/' : '';
    return state.assets.filter(a => prefix && a.ref.startsWith(prefix)).map((a, i) => ({...a, frame:i, id:a.ref.split('/').pop().replace('.png',''),duration_ms:100}));
  }
  if (state.mode === 'action') return state.action ? actionSteps(state.data, state.action, state.playbackMode) : [];
  return currentReview() ? reviewSteps(state.data, currentReview()) : [];
}
function refreshPlayer({seek = true} = {}) {
  player.sourceView = null; player.setProject(state.data, state.assets);
  const steps = activeSteps();
  if (state.mode === 'source' && state.sourceView === 'original' && sourceInfo()) {
    const source = sourceInfo(); player.size = source.size;
    const boxes = state.previewSource === state.source && state.preview ? state.preview.frames.map(f => f.box) : resolvedSource().extract.boxes || [];
    player.sourceView = {url:source.url,boxes,selected:state.selected}; player.resize();
    $('#canvas-label').textContent = `${source.size.join(' × ')} · 原始像素 · 拖拽框选可切换到手动切图`;
  } else {
    $('#canvas-label').textContent = `${state.data.frame_size.join(' × ')} · 固定锚点 (${state.data.anchor.pixels.join(', ')})`;
  }
  if (seek) player.setSteps(steps, state.mode === 'review' ? Math.min(player.index, Math.max(0,steps.length - 1)) : state.selected);
  $('#empty-canvas').hidden = steps.length > 0 || !!player.sourceView;
  const missing = steps.filter(step => !step.url && !asset(step.ref));
  if (missing.length) { $('#empty-canvas').hidden = false; $('#empty-canvas strong').textContent = '动作引用的素材尚未就绪'; $('#empty-canvas p').textContent = '点击“准备缺失素材”，或从已有最终帧导入'; }
  else { $('#empty-canvas strong').textContent = '从素材开始，编排动作'; $('#empty-canvas p').textContent = '点击左侧素材，或将它拖入下方时间轴'; }
  $('#total-time').textContent = (steps.reduce((sum, step) => sum + step.duration_ms, 0) / 1000).toFixed(2) + 's';
  $('#timeline-stats').textContent = `${steps.length} FRAMES`;
  $('#play').textContent = player.playing ? 'Ⅱ' : '▶';
  $('#play').disabled = !steps.length || !!player.sourceView;
  player.loop = $('#loop-preview').checked;
}
function onStep(index) {
  if (!state.data) return;
  const step = player.steps[index];
  $('#play-position').textContent = `${String(step ? index + 1 : 0).padStart(3,'0')} / ${String(player.steps.length).padStart(3,'0')}`;
  $('#frame-info').textContent = step ? `${step.action ? step.action + ' / ' : ''}${step.ref || step.id} · ${step.duration_ms} ms` : '—';
  $('#play').textContent = player.playing ? 'Ⅱ' : '▶';
  document.querySelectorAll('.timeline-card').forEach(card => {
    const active = state.mode === 'review' ? Number(card.dataset.index) === step?.clip : Number(card.dataset.index) === index;
    card.classList.toggle('playing', active);
  });
}
function renderTimeline() {
  const timeline = $('#timeline'), steps = activeSteps(), scrollLeft = $('#timeline').scrollLeft;
  const cards = state.mode === 'review' ? (currentReview()?.clips || []).map((clip, index) => {
    const first = actionSteps(state.data,clip.action,currentReview().mode)[clip.start || 0];
    return {index, ref:first?.ref, caption:`${clip.repeat}× · ${clip.start || 0}–${clip.end ?? 'END'}`,name:clip.action};
  }) : steps.map((step,index) => ({...step,index,caption:`${step.duration_ms} ms`}));
  timeline.innerHTML = cards.map(card => `<button class="timeline-card ${state.mode === 'review' ? 'clip' : ''} ${card.index === (state.mode === 'review' ? state.clip : state.selected) ? 'selected' : ''}" data-index="${card.index}" draggable="${state.mode !== 'source'}" title="${escape(card.ref || card.name)}">${state.mode === 'review' ? `<span class="clip-name">${escape(card.name)}</span>` : ''}${card.url || asset(card.ref)?.url ? `<img src="${escape(card.url || asset(card.ref).url)}" alt="${escape(card.ref)}">` : '<span style="height:73px;padding:20px;color:#ef9292">缺失</span>'}<span class="frame-caption"><span>${String(card.index).padStart(3,'0')}</span><span>${escape(card.caption)}</span></span></button>`).join('') || '<div class="timeline-empty">将素材或动作拖到这里，开始编排 →</div>';
  timeline.scrollLeft = scrollLeft;
  const tools = state.mode === 'source' ? '<button id="source-preview">刷新预览</button>' : state.mode === 'action' ? '<button id="duplicate-frame">重复帧</button><button id="reverse-frames">倒序</button><button id="remove-frame">移除</button>' : '<button id="add-clip">＋ 动作片段</button><button id="remove-clip">移除</button>';
  $('#timeline-tools').innerHTML = tools;
  timeline.querySelectorAll('[data-index]').forEach(card => {
    card.onclick = () => {
      const index = Number(card.dataset.index); player.pause();
      if (state.mode === 'review') {
        state.clip = index; player.seek(Math.max(0,steps.findIndex(step => step.clip === index)));
      } else { state.selected = index; player.seek(index); }
      renderInspector(); renderTimeline(); onStep(player.index); if (player.sourceView) { player.sourceView.selected = index; player.draw(); }
    };
    card.ondragstart = event => event.dataTransfer.setData('application/x-timeline', card.dataset.index);
    card.ondragover = event => event.preventDefault();
    card.ondrop = event => {
      event.preventDefault(); event.stopPropagation(); const target = Number(card.dataset.index);
      const original = event.dataTransfer.getData('application/x-timeline');
      const ref = event.dataTransfer.getData('application/x-sprite');
      const action = event.dataTransfer.getData('application/x-action');
      if (original !== '') moveTimeline(Number(original), target);
      else if (ref) addAsset(ref,target);
      else if (action && state.mode === 'review') addClip(action,target);
    };
  });
  timeline.ondragover = event => { event.preventDefault(); timeline.classList.add('drop-active'); };
  timeline.ondragleave = () => timeline.classList.remove('drop-active');
  timeline.ondrop = event => {
    event.preventDefault(); timeline.classList.remove('drop-active');
    const ref = event.dataTransfer.getData('application/x-sprite'), action = event.dataTransfer.getData('application/x-action');
    const original = event.dataTransfer.getData('application/x-timeline');
    if (ref) addAsset(ref); else if (action && state.mode === 'review') addClip(action);
    else if (original !== '') moveTimeline(Number(original), cards.length - 1);
  };
  $('#source-preview')?.addEventListener('click', () => previewSource());
  $('#duplicate-frame')?.addEventListener('click', duplicateFrame);
  $('#reverse-frames')?.addEventListener('click', reverseFrames);
  $('#remove-frame')?.addEventListener('click', removeFrame);
  $('#add-clip')?.addEventListener('click', () => addClip($('#clip-add-action')?.value || Object.keys(state.data.actions)[0]));
  $('#remove-clip')?.addEventListener('click', () => change(() => { currentReview()?.clips.splice(state.clip,1); state.clip = Math.max(0,state.clip - 1); }));
}
function moveTimeline(from,to) {
  if (from === to || state.mode === 'source') return;
  change(() => {
    if (state.mode === 'review') {
      const list = currentReview().clips; const [clip] = list.splice(from,1); list.splice(to,0,clip); state.clip = to;
    } else if (state.playbackMode === 'display') {
      const action = currentAction(), steps = actionSteps(state.data,state.action,'display');
      const [step] = steps.splice(from,1); steps.splice(to,0,step); action.animation ||= {};
      action.animation.order = steps.map(s => s.frame); action.animation.durations_ms = steps.map(s => s.duration_ms); state.selected = to;
    } else {
      const action = currentAction(), slots = frames(action).map((_,i) => i);
      const [slot] = slots.splice(from,1); slots.splice(to,0,slot); const refs = slots.map(i => action.sprites[i]);
      editFrames(action,slots,refs,state.data.defaults?.fps || 12); state.selected = to;
    }
  });
}
function duplicateFrame() {
  if (!currentAction() || !activeSteps().length) return;
  if (state.playbackMode === 'runtime') addAsset(frames(currentAction())[state.selected],state.selected + 1);
  else change(() => {
    const action = currentAction(), steps = actionSteps(state.data,state.action,'display');
    steps.splice(state.selected + 1,0,{...steps[state.selected]}); action.animation ||= {};
    action.animation.order = steps.map(s => s.frame); action.animation.durations_ms = steps.map(s => s.duration_ms); state.selected++;
  });
}
function reverseFrames() {
  if (!currentAction()) return;
  change(() => {
    const action = currentAction();
    if (state.playbackMode === 'display') {
      const steps = actionSteps(state.data,state.action,'display').reverse(); action.animation ||= {};
      action.animation.order = steps.map(s => s.frame); action.animation.durations_ms = steps.map(s => s.duration_ms);
    } else { const slots = frames(action).map((_,i) => i).reverse(); editFrames(action,slots,[...frames(action)].reverse(),state.data.defaults?.fps || 12); }
    state.selected = 0;
  });
}
function removeFrame() {
  if (!currentAction() || !activeSteps().length) return;
  change(() => {
    const action = currentAction();
    if (state.playbackMode === 'display') {
      const steps = actionSteps(state.data,state.action,'display'); if (steps.length === 1) return;
      steps.splice(state.selected,1); action.animation ||= {}; action.animation.order = steps.map(s => s.frame); action.animation.durations_ms = steps.map(s => s.duration_ms);
    } else { const slots = frames(action).map((_,i) => i).filter(i => i !== state.selected); editFrames(action,slots,slots.map(i => action.sprites[i]),state.data.defaults?.fps || 12); }
    state.selected = Math.max(0,state.selected - 1);
  });
}
function addClip(name, at) {
  if (!currentReview()) { toast('请先创建一个 Review 序列'); return; }
  if (!name || !frames(state.data.actions[name]).length) { toast('请先为动作添加素材'); return; }
  change(() => { const clips = currentReview().clips; state.clip = at ?? clips.length; clips.splice(state.clip,0,{action:name,repeat:1,start:0,end:null}); });
}

function renderInspector() {
  $('#inspector-content').innerHTML = state.mode === 'source' ? sourceInspector() : state.mode === 'action' ? actionInspector() : reviewInspector();
  if (state.mode === 'source') bindSourceInspector(); else if (state.mode === 'action') bindActionInspector(); else bindReviewInspector();
}
function actionInspector() {
  const action = currentAction();
  if (!action) return '<p class="muted">创建一个动作，然后从素材库添加帧。</p>';
  const spec = merge(state.data.defaults,action), steps = activeSteps(), step = steps[state.selected];
  const refs = frames(action), selectedAsset = asset(step?.ref);
  return section('动作设置', label('动作 ID',`<input id="action-name" value="${escape(state.action)}" pattern="[A-Za-z0-9_-]+">`) +
    `<label class="field-inline">游戏帧率 FPS${number('action-fps',spec.fps || 12,'min="1" max="1000" step="0.5"')}</label><label class="field-inline">游戏内循环<input id="action-loop" type="checkbox" ${spec.loop ? 'checked' : ''}></label>` +
    `<label class="field-inline">图集列数${number('action-columns',spec.pack?.columns || 4,'min="1" max="64"')}</label>`) +
    section('预览播放',`<div class="mode-switch"><button id="runtime-mode" class="${state.playbackMode === 'runtime' ? 'active' : ''}">游戏播放</button><button id="display-mode" class="${state.playbackMode === 'display' ? 'active' : ''}">展示播放</button></div><p class="hint">游戏播放按帧顺序和 FPS 运行。展示播放可单独排序、重复帧和调整停留时间，导出为 WebP。</p>` +
    (state.playbackMode === 'display' ? `<label class="field-inline">WebP 循环次数${number('display-loop',action.animation?.loop ?? (spec.loop ? 0 : 1),'min="0" max="65535"')}</label><p class="hint">0 表示无限循环。</p><button id="reset-display" class="wide">展示配置恢复为游戏播放</button>` : '')) +
    section('所选帧',step ? `<span class="selected-ref">${escape(step.ref)}</span>` + info('帧编号',String(step.frame).padStart(3,'0')) + info('画布',selectedAsset?.size.join(' × ') || '素材尚未就绪') +
      (selectedAsset?.bbox ? info('有效轮廓',`${selectedAsset.bbox[2] - selectedAsset.bbox[0]} × ${selectedAsset.bbox[3] - selectedAsset.bbox[1]}`) : '') +
      (state.playbackMode === 'display' ? `<label class="field-inline">此步停留 ms${number('frame-duration',step.duration_ms,'min="1" max="16777215"')}</label>` : info('游戏帧时长',`${step.duration_ms} ms`)) +
      '<button id="locate-source" class="wide">定位到素材处理 ↗</button>' : '<p class="hint">点击左侧素材，添加第一帧。</p>') +
    section('动作信息',info('素材帧数',refs.length) + info('展示步数',actionSteps(state.data,state.action,'display').length) + info('共享锚点',state.data.anchor.pixels.join(', ')) + '<p class="hint">动作保存素材引用。修改 processed 素材，会更新所有引用它的动作。</p><button id="delete-action" class="wide danger">删除动作</button>');
}
function bindValue(id, operation, options = {}) {
  const input = $('#' + id); if (!input) return;
  input.addEventListener('change', () => {
    if (input.type === 'number' && !input.checkValidity()) { input.reportValidity(); return; }
    const value = input.type === 'checkbox' ? input.checked : input.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value;
    change(() => operation(value),options);
  });
}
function bindActionInspector() {
  if (!currentAction()) return;
  bindValue('action-name', name => {
    if (name === state.action) return;
    if (!/^[A-Za-z0-9_-]+$/.test(name) || state.data.actions[name]) { toast('动作 ID 需唯一，只能包含字母、数字、下划线和短横线',true); return; }
    const previous = state.action; state.data.actions[name] = currentAction(); delete state.data.actions[previous];
    Object.values(reviews()).forEach(review => review.clips.forEach(clip => { if (clip.action === previous) clip.action = name; })); state.action = name;
  });
  bindValue('action-fps', value => { currentAction().fps = value; });
  bindValue('action-loop', value => { currentAction().loop = value; });
  bindValue('action-columns', value => { currentAction().pack = {...currentAction().pack,columns:value}; });
  $('#runtime-mode').onclick = () => { state.playbackMode = 'runtime'; state.selected = 0; player.pause(); renderAll(); };
  $('#display-mode').onclick = () => { state.playbackMode = 'display'; state.selected = 0; player.pause(); renderAll(); };
  bindValue('display-loop', value => { currentAction().animation ||= {}; currentAction().animation.loop = value; });
  bindValue('frame-duration', value => {
    const steps = actionSteps(state.data,state.action,'display'); steps[state.selected].duration_ms = value;
    currentAction().animation ||= {}; currentAction().animation.order = steps.map(s => s.frame); currentAction().animation.durations_ms = steps.map(s => s.duration_ms);
  });
  $('#reset-display')?.addEventListener('click', () => change(() => { delete currentAction().animation; }));
  $('#locate-source')?.addEventListener('click', () => {
    const ref = activeSteps()[state.selected]?.ref;
    const source = state.sources.find(s => ref?.startsWith(s.file.replace(/\.[^.]+$/,'') + '/'));
    if (!source) { toast('此帧是已确认或导入的独立素材，可直接在外部修图后重新导入'); return; }
    state.source = source.file; mode('source');
  });
  $('#delete-action')?.addEventListener('click', () => {
    if (Object.values(reviews()).some(review => review.clips.some(clip => clip.action === state.action))) { toast('此动作仍被 Review 引用，请先移除相应片段',true); return; }
    if (confirm(`删除动作 ${state.action}？素材图片会保留，可撤销。`)) change(() => { delete state.data.actions[state.action]; state.action = Object.keys(state.data.actions)[0]; state.selected = 0; });
  });
}

function resolvedSource() {
  const own = state.data.sources?.[state.source] || {};
  const defaults = state.data.defaults || {};
  return {extract:merge(defaults.extract,own.extract),process:merge(defaults.process,own.process)};
}
function sourceRules() { state.data.sources ||= {}; return state.data.sources[state.source] ||= {}; }
function selectedSlice() { return activeSteps()[state.selected]; }
function sourceInspector() {
  if (!state.source) return '<p class="hint">点击左上角 ＋ 导入原图。</p>';
  const rules = resolvedSource(), extract = rules.extract, process = rules.process, slice = selectedSlice();
  const override = process.overrides?.[slice?.id] || {};
  const method = extract.method || 'components';
  const methods = [['components','自动连通域'],['grid','规则网格'],['boxes','手动区域'],['image','整张单帧']];
  return section('查看方式',`<div class="mode-switch"><button id="view-processed" class="${state.sourceView === 'processed' ? 'active' : ''}">处理结果</button><button id="view-original" class="${state.sourceView === 'original' ? 'active' : ''}">原图 / 切图</button></div>` + info('原图尺寸',sourceInfo().size.join(' × ')) +
    (state.previewError ? `<div class="error-panel">${escape(state.previewError)}</div>` : '') +
    '<p class="hint">预览使用未保存的参数。“应用处理”会更新该原图的 processed 素材，并保存当前工程草稿。</p>') +
    section('切图规则',label('切图方式',`<select id="extract-method">${methods.map(([value,name]) => `<option value="${value}" ${value === method ? 'selected' : ''}>${name}</option>`).join('')}</select>`) +
      (['grid','components'].includes(method) ? `<div class="field-row">${label('列数',number('extract-cols',extract.cols ?? '', 'min="1" placeholder="自动"'))}${label('行数',number('extract-rows',extract.rows ?? '', 'min="1" placeholder="自动"'))}</div>` : '') +
      (method === 'components' ? `<label class="field-inline">透明度阈值${number('extract-alpha',extract.alpha_threshold || 16,'min="1" max="255"')}</label><details><summary>连通域高级参数</summary>${label('最小组件像素',number('extract-min',extract.min_component_pixels || 80,'min="1"'))}${label('主体最少像素',number('extract-major',extract.major_min_pixels || 10000,'min="1"'))}${label('主体占比',number('extract-fraction',extract.major_fraction ?? .02,'min="0" max="1" step="0.01"'))}</details>` : '') +
      (method === 'boxes' ? `<p class="hint">切换到原图，在画布上拖拽添加矩形。坐标顺序为 left, top, right, bottom。</p>${label('切图区域 JSON',`<textarea id="extract-boxes" rows="4">${escape(JSON.stringify(extract.boxes || []))}</textarea>`)}<button id="remove-box" class="wide">移除所选区域</button>` : '') +
      '<details><summary>原图切图规则 JSON</summary><textarea id="extract-json" rows="6" style="width:100%">' + escape(JSON.stringify(extract,null,2)) + '</textarea><button id="apply-extract-json" class="wide" style="margin-top:8px">更新切图规则</button></details>') +
    section('整组处理',label('处理方式',`<select id="process-mode"><option value="anchor" ${process.mode === 'anchor' || !process.mode ? 'selected' : ''}>轮廓裁切 + 锚点对齐</option><option value="contain" ${process.mode === 'contain' ? 'selected' : ''}>完整切片等比容纳</option><option value="copy" ${process.mode === 'copy' ? 'selected' : ''}>原样复制（相同画布）</option></select>`) +
      `<div class="field-row">${label('基础缩放',number('process-scale',process.scale ?? 1,'min="0.01" max="10" step="0.01"'))}${label('目标高度',number('process-height',process.fit_height ?? '', 'min="1" placeholder="不启用"'))}</div>` +
      `<div class="field-row">${label('水平偏移',number('process-x',process.offset?.[0] || 0,'step="1"'))}${label('垂直偏移',number('process-y',process.offset?.[1] || 0,'step="1"'))}</div>` +
      `<label class="field-inline">最大自适应倍率${number('process-max-scale',process.max_scale ?? 1,'min="0.01" max="10" step="0.05"')}</label><label class="field-inline">垂直限制在画布内<input id="process-clamp" type="checkbox" ${process.clamp_y ? 'checked' : ''}></label>` +
      `<label class="field-inline">边缘留白${number('process-padding',process.padding ?? 0,'min="0"')}</label><label class="field-inline">越界处理<select id="process-overflow"><option value="error" ${process.overflow !== 'clip' ? 'selected' : ''}>提示错误</option><option value="clip" ${process.overflow === 'clip' ? 'selected' : ''}>允许裁切</option></select></label>` +
      info('实际组缩放',state.preview?.scale?.toFixed(4) || '预览后显示') + '<p class="hint">目标高度按整组最高轮廓计算共同缩放，保留帧间体型差异。</p>' +
      '<details><summary>处理规则 JSON（含所有帧覆盖）</summary><textarea id="process-json" rows="7" style="width:100%">' + escape(JSON.stringify(process,null,2)) + '</textarea><button id="apply-process-json" class="wide" style="margin-top:8px">更新处理规则</button></details>') +
    section('所选帧覆盖',slice ? `<span class="selected-ref">${escape(slice.ref)}</span><div class="field-row">${label('水平偏移',number('override-x',override.offset?.[0] ?? process.offset?.[0] ?? 0,'step="1"'))}${label('垂直偏移',number('override-y',override.offset?.[1] ?? process.offset?.[1] ?? 0,'step="1"'))}</div>` +
      label('独立绝对缩放',number('override-scale',override.scale ?? '', 'min="0.01" max="10" step="0.01" placeholder="继承整组"')) + '<p class="hint">单帧缩放覆盖整组最终倍率；偏移覆盖整组偏移。</p><button id="clear-override" class="wide">清除此帧覆盖</button>' : '<p class="hint">预览处理后选择一帧。</p>') +
    section('应用处理','<button id="apply-source" class="primary wide">应用处理并保存工程</button><p class="hint">所有引用这些素材的动作会同步更新。原图和已发布的最终帧会保留。</p>');
}
function bindSourceInspector() {
  if (!state.source) return;
  const opts = {preview:true};
  const setExtract = (key,value) => { const rules = sourceRules(); rules.extract ||= {}; rules.extract[key] = value; };
  const setProcess = (key,value) => { const rules = sourceRules(); rules.process ||= {}; rules.process[key] = value; };
  $('#view-original').onclick = () => { state.sourceView = 'original'; player.pause(); renderAll(); };
  $('#view-processed').onclick = () => { state.sourceView = 'processed'; renderAll(); };
  bindValue('extract-method', value => {
    setExtract('method',value);
    if (value === 'boxes') {
      setExtract('boxes',state.preview?.frames.map(frame => frame.box) || resolvedSource().extract.boxes || []); state.sourceView = 'original';
    }
    if (value === 'grid') { setExtract('cols',resolvedSource().extract.cols || 1); setExtract('rows',resolvedSource().extract.rows || 1); }
  },opts);
  const setLayout = (key,value) => {
    setExtract(key,value);
    if (value === null) { const rules = sourceRules(); rules.extract = {...resolvedSource().extract,...rules.extract}; delete rules.extract.cols; delete rules.extract.rows; }
  };
  bindValue('extract-cols',value => setLayout('cols',value),opts); bindValue('extract-rows',value => setLayout('rows',value),opts);
  [['extract-alpha','alpha_threshold'],['extract-min','min_component_pixels'],['extract-major','major_min_pixels'],['extract-fraction','major_fraction']].forEach(([id,key]) => bindValue(id,value => setExtract(key,value),opts));
  bindValue('extract-boxes', value => { try { const boxes = JSON.parse(value); if (!Array.isArray(boxes)) throw new Error(); setExtract('boxes',boxes); } catch { toast('区域必须是矩形坐标数组',true); } },opts);
  $('#apply-extract-json').onclick = () => {
    try { const rules = JSON.parse($('#extract-json').value); if (!rules || Array.isArray(rules) || typeof rules !== 'object') throw new Error(); change(() => { sourceRules().extract = rules; },opts); }
    catch { toast('切图规则必须是有效的 JSON 对象',true); }
  };
  $('#apply-process-json').onclick = () => {
    try { const rules = JSON.parse($('#process-json').value); if (!rules || Array.isArray(rules) || typeof rules !== 'object') throw new Error(); change(() => { sourceRules().process = rules; },opts); }
    catch { toast('处理规则必须是有效的 JSON 对象',true); }
  };
  $('#remove-box')?.addEventListener('click', () => change(() => { const boxes = [...(resolvedSource().extract.boxes || [])]; boxes.splice(state.selected,1); setExtract('boxes',boxes); state.selected = Math.max(0,state.selected - 1); },opts));
  [['process-mode','mode'],['process-scale','scale'],['process-height','fit_height'],['process-max-scale','max_scale'],['process-clamp','clamp_y'],['process-padding','padding'],['process-overflow','overflow']].forEach(([id,key]) => bindValue(id,value => setProcess(key,value),opts));
  ['x','y'].forEach((axis,index) => bindValue('process-' + axis,value => { const offset = [...(resolvedSource().process.offset || [0,0])]; offset[index] = value; setProcess('offset',offset); },opts));
  const setOverride = (key,value) => {
    const id = selectedSlice()?.id; if (!id) return;
    const overrides = clone(resolvedSource().process.overrides || {}); overrides[id] ||= {};
    if (value === null) delete overrides[id][key]; else overrides[id][key] = value; setProcess('overrides',overrides);
  };
  ['x','y'].forEach((axis,index) => bindValue('override-' + axis,value => {
    const process = resolvedSource().process, id = selectedSlice()?.id;
    const offset = [...(process.overrides?.[id]?.offset || process.offset || [0,0])]; offset[index] = value; setOverride('offset',offset);
  },opts));
  bindValue('override-scale',value => setOverride('scale',value),opts);
  $('#clear-override')?.addEventListener('click', () => change(() => {
    const overrides = clone(resolvedSource().process.overrides || {}); delete overrides[selectedSlice().id]; setProcess('overrides',overrides);
  },opts));
  $('#apply-source').onclick = () => task('正在应用处理并保存工程…',async () => {
    const snapshot = await api('apply',payload({source:state.source})); setSnapshot(snapshot); toast('已更新 processed 素材和工程配置'); await previewSource();
  });
}
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(() => previewSource(),350); }
async function previewSource() {
  if (!state.source) return;
  const epoch = ++state.previewEpoch, source = state.source, data = clone(state.data);
  $('#status-message').textContent = '正在预览切图和处理结果…';
  try {
    const result = await api('preview',{data,source});
    if (epoch !== state.previewEpoch || source !== state.source) return;
    state.preview = result; state.previewSource = source; state.previewError = null;
    state.selected = Math.min(state.selected,Math.max(0,result.frames.length - 1));
    if (state.mode === 'source') { renderInspector(); renderTimeline(); refreshPlayer(); }
    $('#status-message').textContent = `处理预览：${result.frames.length} 帧 · 整组倍率 ${result.scale.toFixed(4)} · 尚未应用`;
  } catch (error) {
    if (epoch !== state.previewEpoch) return;
    state.previewError = error.message;
    if (state.mode === 'source') renderInspector();
    $('#status-message').textContent = '预览失败：' + error.message;
  }
}

function reviewInspector() {
  const review = currentReview(); if (!review) return '<p class="hint">创建 Review，再添加动作片段。可将 jump → land、idle → attack 等衔接保存下来反复检查。</p>';
  const clip = review.clips[state.clip], steps = activeSteps();
  const names = Object.keys(state.data.actions);
  return section('Review 设置',label('序列名称',`<input id="review-name" value="${escape(review.name || state.review)}">`) +
    label('播放参数',`<select id="review-mode"><option value="runtime" ${review.mode !== 'display' ? 'selected' : ''}>游戏播放参数</option><option value="display" ${review.mode === 'display' ? 'selected' : ''}>展示播放参数</option></select>`) +
    `<label class="field-inline">导出动画循环<input id="review-loop" type="checkbox" ${review.loop ? 'checked' : ''}></label><p class="hint">每个动作按片段的重复次数播放。动作自身的无限循环不会阻止进入下个片段。</p>`) +
    section('添加片段',label('选择动作',`<select id="clip-add-action">${names.map(name => `<option value="${escape(name)}">${escape(name)}</option>`).join('')}</select>`) + '<button id="inspector-add-clip" class="wide">＋ 添加动作片段</button>') +
    section('所选片段',clip ? label('动作',`<select id="clip-action">${names.map(name => `<option value="${escape(name)}" ${clip.action === name ? 'selected' : ''}>${escape(name)}</option>`).join('')}</select>`) +
      `<label class="field-inline">重复次数${number('clip-repeat',clip.repeat,'min="1" max="100"')}</label><div class="field-row">${label('起始步（0 起）',number('clip-start',clip.start || 0,'min="0"'))}${label('结束步（含）',number('clip-end',clip.end ?? '', 'min="0" placeholder="最后一帧"'))}</div>` +
      '<p class="hint">范围基于所选播放模式中的步骤编号。</p><div class="boundary-controls"><button id="before-boundary">衔接前一帧</button><button id="after-boundary">片段第一帧</button></div><button id="remove-current-clip" class="wide danger">移除此片段</button>' : '<p class="hint">选择一个动作片段。</p>') +
    section('检查辅助','<p class="hint">开启“前帧叠图”，在衔接第一帧对比上个动作的末帧。开启“Idle 参考”，检查身体尺寸和基准位置。</p>' + info('片段数',review.clips.length) + info('播放步数',steps.length) + info('总时长',(steps.reduce((sum,s) => sum + s.duration_ms,0) / 1000).toFixed(2) + 's') + '<button id="delete-review" class="wide danger">删除 Review</button>');
}
function bindReviewInspector() {
  const review = currentReview(); if (!review) return;
  const clip = review.clips[state.clip];
  bindValue('review-name',value => { review.name = value; });
  bindValue('review-mode',value => { review.mode = value; review.clips.forEach(c => { c.start = 0; c.end = null; }); });
  bindValue('review-loop',value => { review.loop = value; });
  $('#inspector-add-clip').onclick = () => addClip($('#clip-add-action').value);
  if (clip) {
    bindValue('clip-action',value => { clip.action = value; clip.start = 0; clip.end = null; });
    [['clip-repeat','repeat'],['clip-start','start'],['clip-end','end']].forEach(([id,key]) => bindValue(id,value => {
      const count = actionSteps(state.data,clip.action,review.mode).length;
      if ((key === 'start' && (value === null || value >= count || value > (clip.end ?? count - 1))) || (key === 'end' && value !== null && (value < clip.start || value >= count))) {
        toast(`片段范围必须位于 0–${count - 1}，起始步不能大于结束步`,true); return;
      }
      clip[key] = value;
    }));
    const seekBoundary = previous => {
      const index = activeSteps().findIndex(step => step.clip === state.clip);
      player.pause(); player.seek(Math.max(0,index - (previous ? 1 : 0))); onStep(player.index);
    };
    $('#before-boundary').onclick = () => seekBoundary(true); $('#after-boundary').onclick = () => seekBoundary(false);
    $('#remove-current-clip').onclick = () => change(() => { review.clips.splice(state.clip,1); state.clip = Math.max(0,state.clip - 1); });
  }
  $('#delete-review').onclick = () => change(() => { delete reviews()[state.review]; state.review = Object.keys(reviews())[0]; state.clip = 0; });
}

// In original-image mode the drag rectangle is authored in source pixels.
let rectangleStart;
const sourcePoint = event => {
  const rect = $('#stage').getBoundingClientRect();
  return [Math.max(0,Math.min(player.size[0],Math.round((event.clientX - rect.left) / rect.width * player.size[0]))),
          Math.max(0,Math.min(player.size[1],Math.round((event.clientY - rect.top) / rect.height * player.size[1])))];
};
$('#stage').addEventListener('pointerdown', event => {
  if (state.mode !== 'source' || !player.sourceView || state.busy) return;
  rectangleStart = sourcePoint(event); $('#stage').setPointerCapture(event.pointerId);
});
$('#stage').addEventListener('pointermove', event => {
  if (!rectangleStart || !player.sourceView) return;
  const end = sourcePoint(event), [x,y] = rectangleStart;
  player.sourceView.draftBox = [Math.min(x,end[0]),Math.min(y,end[1]),Math.max(x,end[0]),Math.max(y,end[1])]; player.draw();
});
$('#stage').addEventListener('pointerup', event => {
  if (!rectangleStart) return;
  const end = sourcePoint(event), [x,y] = rectangleStart; rectangleStart = null;
  const box = [Math.min(x,end[0]),Math.min(y,end[1]),Math.max(x,end[0]),Math.max(y,end[1])];
  if (box[2] - box[0] < 3 || box[3] - box[1] < 3) {
    const found = player.sourceView?.boxes.findIndex(([a,b,c,d]) => a <= x && x <= c && b <= y && y <= d);
    if (found >= 0) { state.selected = found; renderAll(); } else { if (player.sourceView) delete player.sourceView.draftBox; player.draw(); }
    return;
  }
  change(() => {
    const current = resolvedSource().extract, rules = sourceRules();
    rules.extract = {...current,method:'boxes',boxes:[...(current.method === 'boxes' ? current.boxes || [] : []),box]};
    state.selected = rules.extract.boxes.length - 1;
  },{preview:true});
});
$('#stage').addEventListener('pointercancel', () => { rectangleStart = null; if (player.sourceView) delete player.sourceView.draftBox; player.draw(); });

document.querySelectorAll('[data-mode]').forEach(button => { button.onclick = () => mode(button.dataset.mode); });
$('#asset-search').oninput = renderLibrary; $('#asset-source').onchange = renderLibrary;
$('#new-item').onclick = () => {
  if (state.mode === 'source') { $('#source-upload').click(); return; }
  if (state.mode === 'action') {
    const name = prompt('新动作 ID（字母、数字、下划线、短横线）',uid('action'));
    if (!name) return;
    if (!/^[A-Za-z0-9_-]+$/.test(name) || state.data.actions[name]) { toast('动作 ID 无效或已存在',true); return; }
    change(() => { state.data.actions[name] = {fps:12,loop:false,sprites:null}; state.action = name; state.selected = 0; state.playbackMode = 'runtime'; });
  } else {
    const name = prompt('Review 名称','新的衔接检查'); if (!name) return;
    change(() => { state.data.workbench ||= {}; state.data.workbench.reviews ||= {}; const id = uid('review'); reviews()[id] = {name,loop:true,mode:'runtime',clips:[]}; state.review = id; state.clip = 0; });
  }
};
$('#save').onclick = save;
$('#reload').onclick = () => {
  if (dirty() && !confirm('重新载入会放弃当前未保存的草稿。继续？')) return;
  task('正在重新载入…',loadProject);
};
function restoreHistory(redo) {
  const source = redo ? state.future : state.history, target = redo ? state.history : state.future;
  if (!source.length || state.busy) return;
  target.push(clone(state.data)); state.data = source.pop(); state.previewEpoch++; state.preview = null;
  player.pause(); renderAll(); if (state.mode === 'source') schedulePreview();
}
$('#undo').onclick = () => restoreHistory(false); $('#redo').onclick = () => restoreHistory(true);
$('#prepare').onclick = () => task('正在准备缺失素材…',async () => { const snapshot = await api('prepare',payload()); setSnapshot(snapshot); toast('缺失素材已准备，已有 processed 图片保持原样'); });
$('#migrate').onclick = () => task('正在保留最终帧…',async () => {
  const snapshot = await api('migrate',payload()); setSnapshot(snapshot); toast(`已保留 ${snapshot.imported} 张不同于 processed 的最终帧，并更新动作引用`);
});
$('#import-processed').onclick = () => $('#processed-upload').click();
async function uploadFile(input,kind) {
  const file = input.files[0]; if (!file) return;
  await task('正在导入素材…',async () => {
    if (file.size > 40 * 1024 * 1024) throw new Error('单张素材请控制在 40 MiB 以内');
    const content = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); });
    const snapshot = await api('upload',payload({kind,filename:file.name,content})); setSnapshot(snapshot);
    if (kind === 'source') { state.source = file.name; mode('source'); }
    toast('素材已导入，工程已保存');
  });
  input.value = '';
}
$('#source-upload').onchange = () => uploadFile($('#source-upload'),'source');
$('#processed-upload').onchange = () => uploadFile($('#processed-upload'),'processed');
$('#play').onclick = () => { player.toggle(); $('#play').textContent = player.playing ? 'Ⅱ' : '▶'; };
function singleStep(delta) {
  player.pause(); player.seek(player.index + delta);
  if (state.mode !== 'review') { state.selected = player.index; renderInspector(); renderTimeline(); onStep(player.index); }
}
$('#previous').onclick = () => singleStep(-1); $('#next').onclick = () => singleStep(1);
$('#speed').onchange = () => { player.speed = Number($('#speed').value); };
$('#loop-preview').onchange = () => { player.loop = $('#loop-preview').checked; };
['guides','onion','reference'].forEach(id => { $('#' + id).onchange = () => { player.options[id] = $('#' + id).checked; player.draw(); }; });
$('#zoom').onchange = () => { player.options.zoom = $('#zoom').value; player.resize(); };
$('#background').onchange = () => { $('#canvas-area').classList.remove('dark','light'); if ($('#background').value !== 'checker') $('#canvas-area').classList.add($('#background').value); };

function openExport() {
  const list = $('#export-action-list');
  list.innerHTML = Object.entries(state.data.actions).filter(([,action]) => frames(action).length).map(([name]) => `<label><input type="checkbox" value="${escape(name)}" ${name === state.action ? 'checked' : ''}>${escape(name)}</label>`).join('');
  $('#export-format').value = state.mode === 'review' ? 'review' : 'all'; updateExportFormat(); $('#export-dialog').showModal();
}
function updateExportFormat() {
  const format = $('#export-format').value;
  $('#export-actions').hidden = ['project','review'].includes(format);
  $('#export-note').textContent = format === 'review' ? '导出当前 Review，使用片段范围、重复次数及所选播放模式。' : format === 'project' ? '包含全部原图、processed 和工程配置。解压后可用 --config 打开。' : '图集使用游戏帧顺序；WebP 使用独立的展示播放配置。';
}
$('#export-open').onclick = openExport; $('#export-close').onclick = () => $('#export-dialog').close(); $('#export-format').onchange = updateExportFormat;
$('#export-form').onsubmit = async event => {
  event.preventDefault(); const format = $('#export-format').value;
  const actions = [...$('#export-action-list').querySelectorAll('input:checked')].map(input => input.value);
  if (!['project','review'].includes(format) && !actions.length) { toast('请至少选择一个动作',true); return; }
  if (format === 'review' && !currentReview()?.clips.length) { toast('请先创建 Review 并添加动作片段',true); return; }
  const submit = $('#export-submit'); submit.disabled = true; submit.textContent = '正在生成…';
  try {
    const response = await api('export',payload({options:{format,actions,review:currentReview()}}),true);
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'sprites.zip';
    link.click(); setTimeout(() => URL.revokeObjectURL(url),60000); $('#export-dialog').close(); toast('导出完成');
  } catch (error) { toast(error.message,true); }
  finally { submit.disabled = false; submit.textContent = '生成并下载 ZIP ↗'; }
};

document.addEventListener('keydown', event => {
  if (!state.data) return;
  const editable = ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!$('#export-dialog').open) save(); return; }
  if (editable || $('#export-dialog').open) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); restoreHistory(event.shiftKey); }
  else if (event.code === 'Space') { event.preventDefault(); if (!$('#play').disabled) $('#play').click(); }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); singleStep(-1); }
  else if (event.key === 'ArrowRight') { event.preventDefault(); singleStep(1); }
  else if (event.key === 'Delete' && state.mode === 'action') removeFrame();
});
window.addEventListener('beforeunload',event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
loadProject().catch(error => { toast(error.message,true); $('#project-name').textContent = '工程载入失败'; $('#save-status').textContent = '请检查服务日志或重新载入'; });
