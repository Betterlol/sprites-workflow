import {createExportDisplay} from './export-display.js';
import {createExplorer} from './explorer.js';
import {clone, actionSteps, reviewSteps, defaultReviews, merge, roundMs} from './model.js';
import {createCompositionUI} from './composition.js';
import {allResources,resourceKey,resourceUsers,slotsOf,renameResource,reconcileCompositeAnimations,validateComposition} from './resources.js';
import {mergeDraft, resolveMerge, conflictKey} from './merge.js';
import {clampPanel, clampTimeline, savedSize} from './layout.js';
import {Player} from './player.js';
import {resizeRegion, hitRegion, manualExtraction} from './slicing.js';
import {composeAdjustmentSteps, mergePreviewFrames, sourceForFrame} from './adjustment.js';

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid = prefix => `${prefix}_${Date.now().toString(36)}`;
const label = (name, body) => `<label class="field">${name}${body}</label>`;
const number = (id, value, attributes = '') => `<input id="${id}" type="number" value="${escape(value)}" ${attributes} ${attributes.includes('placeholder=') ? '' : 'required'}>`;
const info = (key, value) => `<div class="info-row"><span>${key}</span><strong>${escape(value)}</strong></div>`;
const section = (title, body) => `<section class="inspector-section"><h3>${title}</h3>${body}</section>`;
const state = {mode:'action', data:null, revision:null, token:null, assets:[], sources:[], references:[], action:null, source:null, review:null, reference:null,
  selected:0, slot:0, clip:0, playbackMode:'runtime', sourceView:'processed', preview:null, previewSource:null, previewKey:null, previewError:null,
  history:[], future:[], saved:null, savedData:null, busy:false, previewEpoch:0, projectId:null, assetRevision:null, externalChange:false,
  assetSelection:new Set(), libraryMulti:false, lastAsset:null, previewOffsets:{}};
let previewTimer, toastTimer, previewRequest;
let mergeContext;
let frameDrag = null;
let regionDrag = null;
let sliceTool = 'select';
const sliceAllocations = new Map();
const previewCache = new Map();
const processedPreviews = new Map();
state.adjustAction = '';
state.adjustPlaybackMode = 'runtime';

const player = new Player($('#stage'), $('#canvas-area'), onStep);
const composition = createCompositionUI({state,$,escape,player,asset,change,renderAll,renderInspector,showPane,mode,steps:activeSteps,onStep,sourceForFrame,deleteMaterials,deleteSequence,renameResource,toast,updateSaveStatus,confirm:message=>confirm(message)});
const explorer = createExplorer({state,$,escape,composition,mode});
const exportDisplay = createExportDisplay({$,state,change,toast,escape});
const LAYOUT_KEY = 'sprite-workbench-layout';
let storedLayout = {};
try { storedLayout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}') || {}; } catch {}
const preferredLayout = {left:savedSize(storedLayout.left,260),right:savedSize(storedLayout.right,300),
  timeline:savedSize(storedLayout.timeline,140)};
const renderedLayout = {...preferredLayout};
function applyLayout() {
  const width = window.innerWidth || $('#workspace').clientWidth || 1440;
  if (width > 1100) {
    renderedLayout.left = clampPanel(preferredLayout.left,width,preferredLayout.right,'left');
    renderedLayout.right = clampPanel(preferredLayout.right,width,renderedLayout.left,'right');
  }
  const editorHeight = $('#canvas-pane').clientHeight;
  if (editorHeight > 0) renderedLayout.timeline = clampTimeline(preferredLayout.timeline,editorHeight);
  $('#workspace').style.setProperty('--materials-width',`${renderedLayout.left}px`);
  $('#workspace').style.setProperty('--properties-width',`${renderedLayout.right}px`);
  $('#canvas-pane').style.setProperty('--timeline-height',`${renderedLayout.timeline}px`);
  for (const [id,value,minimum,maximum] of [
    ['left-splitter',renderedLayout.left,210,Math.max(renderedLayout.left,210,Math.min(420,width - 16 - 420 - renderedLayout.right))],
    ['right-splitter',renderedLayout.right,250,Math.max(renderedLayout.right,250,Math.min(460,width - 16 - 420 - renderedLayout.left))],
    ['timeline-splitter',renderedLayout.timeline,110,Math.max(renderedLayout.timeline,110,Math.min(320,(editorHeight || 800) - 260))],
  ]) {
    const handle = $(`#${id}`);
    handle.setAttribute('aria-valuemin',minimum);
    handle.setAttribute('aria-valuemax',maximum);
    handle.setAttribute('aria-valuenow',value);
  }
}
function persistLayout() { try { localStorage.setItem(LAYOUT_KEY,JSON.stringify(preferredLayout)); } catch {} }
function bindSplitter(id,key,axis,sign) {
  const handle = $(`#${id}`);
  handle.onkeydown = event => {
    const delta = axis === 'x' ? {ArrowLeft:-24,ArrowRight:24}[event.key] : {ArrowUp:-24,ArrowDown:24}[event.key];
    if (delta === undefined) return;
    event.preventDefault(); event.stopPropagation();
    preferredLayout[key] = renderedLayout[key] + delta * sign;
    applyLayout(); preferredLayout[key] = renderedLayout[key]; persistLayout();
  };
  handle.onpointerdown = event => {
    if (event.button !== 0) return;
    event.preventDefault(); handle.setPointerCapture(event.pointerId);
    document.body.classList.add('resizing');
    const start = axis === 'x' ? event.clientX : event.clientY, initial = renderedLayout[key];
    handle.onpointermove = move => {
      preferredLayout[key] = initial + ((axis === 'x' ? move.clientX : move.clientY) - start) * sign;
      applyLayout();
    };
    const finish = () => {
      handle.onpointermove = null; handle.onpointerup = null; handle.onpointercancel = null;
      document.body.classList.remove('resizing');
      preferredLayout[key] = renderedLayout[key]; persistLayout();
    };
    handle.onpointerup = finish; handle.onpointercancel = finish;
  };
}
bindSplitter('left-splitter','left','x',1);
bindSplitter('right-splitter','right','x',-1);
bindSplitter('timeline-splitter','timeline','y',-1);
window.addEventListener('resize',() => applyLayout());
new ResizeObserver(() => applyLayout()).observe($('#workspace'));
function showPane(value, focus = false) {
  document.body.dataset.pane = value;
  for (const button of document.querySelectorAll('[data-pane]')) {
    const active = button.dataset.pane === value;
    button.setAttribute('aria-pressed',active);
    button.classList.toggle('active',active);
  }
  if (value === 'canvas') {
    applyLayout(); player.resize();
    if (focus && window.innerWidth <= 1100) $('#canvas-pane').focus();
  }
}
document.querySelectorAll('[data-pane]').forEach(button => { button.onclick = () => showPane(button.dataset.pane); });
showPane('canvas');
function toast(message, error = false) {
  const box = $('#toast'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false;
  $('#status-message').textContent = message;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, error ? 10000 : 4000);
}
async function api(path, payload, binary = false, signal) {
  const route = path.startsWith('projects') || !state.projectId ? path
    : `projects/${encodeURIComponent(state.projectId)}${path === 'project' ? '' : '/' + path}`;
  const options = payload === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-Workbench-Token':state.token}, body:JSON.stringify(payload),
  };
  if (signal) options.signal = signal;
  const response = await fetch(`/api/${route}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const error = new Error(detail.error || (typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail)) || `请求失败 (${response.status})`);
    error.status = response.status; throw error;
  }
  return binary ? response : response.json();
}
const payload = extra => ({data:state.data, revision:state.revision, asset_revision:state.assetRevision, ...extra});
async function task(message, operation) {
  if (state.busy) return;
  cancelRegionDrag();
  cancelFrameDrag();
  state.busy = true; $('#canvas-loading').hidden = false; $('#canvas-loading').textContent = message;
  $('#activity-state').textContent = message; $('#activity-state').hidden = false;
  ['.workspace','.modebar','.top-actions','.pane-switch'].forEach(selector => { $(selector).inert = true; });
  try { return await operation(); }
  catch (error) { toast(error.message, true); }
  finally { state.busy = false; $('#canvas-loading').hidden = true; $('#activity-state').hidden = true; ['.workspace','.modebar','.top-actions','.pane-switch'].forEach(selector => { $(selector).inert = false; }); updateSaveStatus(); }
}
function reviews() { return state.data?.workbench?.reviews || {}; }
function currentReview() { return reviews()[state.review]; }
function currentAction() { return state.data.actions[state.action]; }
function ownCompositionSpec(target) { return target.kind === 'action' ? state.data.actions[target.ref] : reviews()[target.ref]; }
function sourceInfo() { return state.sources.find(source => source.file === state.source); }
function referenceInfo() { return state.references.find(image => image.ref === state.reference); }
function asset(ref) { return state.assets.find(item => item.ref === ref); }
function dirty() { return state.data && JSON.stringify(state.data) !== state.saved; }
function sourceRecipe(data, source) {
  return [data?.frame_size,data?.anchor,data?.defaults?.extract,data?.defaults?.process,data?.sources?.[source]];
}
function updateSaveStatus() {
  const draft = !!dirty();
  $('#save-status').textContent = state.busy ? '正在处理…' : state.externalChange ? '● 磁盘内容已变化' : draft ? '● 有未保存的更改' : '✓ 工程已保存';
  $('#save-status').classList.toggle('dirty', draft);
  $('#draft-state').textContent = state.externalChange ? '工程：磁盘有新修改' : draft ? '工程：草稿待保存' : '工程：已保存';
  $('#draft-state').dataset.state = state.externalChange || draft ? 'pending' : 'ready';
  const sourceChanged = state.mode === 'source' && state.source && state.savedData &&
    JSON.stringify(sourceRecipe(state.data,state.source)) !== JSON.stringify(sourceRecipe(state.savedData,state.source));
  const currentPreview = state.data && state.preview && state.previewSource === state.source && state.previewKey === previewKey(state.source);
  const preview = state.mode !== 'source' || !state.source ? '未选择原图' : state.previewError ? '预览失败' :
    sourceChanged ? (currentPreview ? '预览待应用' : '参数待预览') : '当前参数';
  $('#preview-state').textContent = state.mode === 'source' && state.sourceView === 'original'
    ? `切割预览：${state.previewError ? '预览失败' : currentPreview ? `${state.preview.frames.length} 个区域` : '等待预览'}` : `处理预览：${preview}`;
  $('#preview-state').dataset.state = state.previewError ? 'error' : sourceChanged ? 'pending' : 'quiet';
  const stale = state.sources.filter(source => source.stale).length;
  $('#material-state').textContent = stale ? `素材：${stale} 张待更新` : '素材：已同步';
  $('#material-state').dataset.state = stale ? 'pending' : 'ready';
  $('#undo').disabled = !state.history.length; $('#redo').disabled = !state.future.length;
  $('#save').disabled = state.busy || !dirty();
  $('#prepare').disabled = state.busy || !state.sources.length;
  $('#migrate').disabled = state.busy || !state.legacyCount;
  $('#delete-item').disabled = state.busy || !state[state.mode];
  $('#assets-delete').disabled = state.busy || !state.assetSelection.size;
  $('#assets-add').disabled = state.busy || !state.assetSelection.size || !composition.isEditing() || !state.data || !composition.current();
}
function checkpoint() {
  state.history.push(clone(state.data)); if (state.history.length > 60) state.history.shift(); state.future = [];
}
function change(operation, {render = true, preview = false} = {}) {
  const before=clone(state.data), selection={action:state.action,review:state.review,selected:state.selected,slot:state.slot,clip:state.clip};
  try {
    operation();
    const graph = data => JSON.stringify([data.actions,data.workbench?.reviews,Object.fromEntries(Object.entries(data.defaults || {}).filter(([key])=>!['process','extract'].includes(key)))]);
    if (graph(before) !== graph(state.data)) {
      reconcileCompositeAnimations(before,state.data); validateComposition(state.data);
    }
  } catch (error) {
    state.data=before; Object.assign(state,selection); toast(error.message,true); renderAll(); return;
  }
  state.history.push(before); if (state.history.length > 60) state.history.shift(); state.future=[]; state.previewEpoch++;
  if (state.mode === 'source' && state.sourceView === 'processed' && preview) {
    schedulePreview(); if (render) renderInspector(); updateSaveStatus(); return;
  }
  if (state.mode === 'source' && preview) { state.preview = null; state.previewKey = null; schedulePreview(); }
  if (render) renderAll(); else updateSaveStatus();
}
function setSnapshot(snapshot) {
  cancelRegionDrag(false); cancelFrameDrag(false);
  previewRequest?.controller.abort(); previewRequest = null;
  state.data = snapshot.data; state.revision = snapshot.revision; state.assets = snapshot.assets; state.sources = snapshot.sources;
  state.references = snapshot.references || []; reconcileMaterials();
  state.assetRevision = snapshot.asset_revision; state.externalChange = false; $('#external-change').hidden = true; $('#external-merge').hidden = true;
  state.token = snapshot.token || state.token; state.saved = JSON.stringify(snapshot.data); state.savedData = clone(snapshot.data);
  state.legacyCount = snapshot.legacy_count; state.history = []; state.future = [];
  state.action = state.data.actions[state.action] ? state.action : Object.keys(state.data.actions)[0];
  state.review = reviews()[state.review] ? state.review : Object.keys(reviews())[0];
  state.preview = null; state.previewSource = null; state.previewKey = null; state.previewError = null; state.previewOffsets = {}; state.previewEpoch++;
  player.setProject(state.data, state.assets); renderAll();
  const name = snapshot.project?.name || state.data.project?.name || state.data.character;
  $('#project-name').textContent = name;
  $('#project-name').title = snapshot.project?.directory || '';
  if (snapshot.warnings?.length) toast(snapshot.warnings.join('\n'),true);
  if (state.mode === 'source' && state.source) schedulePreview();
}
function reconcileMaterials() {
  state.source = state.sources.some(s => s.file === state.source) ? state.source : state.sources[0]?.file;
  state.reference = state.references.some(image => image.ref === state.reference) ? state.reference : state.references[0]?.ref;
  const availableResources=new Set([...state.assets.map(item=>`sprite:${item.ref}`),...allResources(state.data).map(resourceKey)]);
  state.assetSelection = new Set([...state.assetSelection].filter(ref=>availableResources.has(ref)));
}
async function loadProject() {
  const snapshot = await api('project'); setSnapshot(snapshot);
  suggestReviews();
  if (!state.assets.length && !snapshot.warnings?.length) toast(state.sources.length ? '点击“准备缺失素材”开始处理，或保留已有最终帧。' : '工程已就绪：点击原图旁的 ＋ 导入图片，也可以先导入单帧素材。');
}
function suggestReviews() {
  // Suggested review sequences are editable drafts, never silently written.
  if (!state.data.workbench?.reviews) {
    const defaults = defaultReviews(state.data);
    if (Object.keys(defaults).length) {
      checkpoint(); state.data.workbench = {...state.data.workbench, reviews:defaults};
      state.review = Object.keys(defaults)[0]; renderAll();
    }
  }
}

async function listProjects() {
  const result = await api('projects'); state.token = result.token;
  $('#workspace-location').textContent = result.workspace_root;
  $('#project-list').innerHTML = result.projects.map(project => `<article class="project-card">
    <span class="eyebrow">${project.external ? 'OPENED WITH CONFIG' : escape(project.id)}</span>
    <h2>${escape(project.name)}</h2>
    <p class="hint">${project.error ? escape(project.error) : `${project.frame_size.join(' × ')} · ${escape(project.character)}`}</p>
    <button class="${project.error ? '' : 'primary'}" data-project="${escape(project.id)}" ${project.error ? 'disabled' : ''}>打开工程 →</button>
    </article>`).join('') || '<div class="projects-empty"><h2>还没有工程</h2><p class="muted">点击“新建工程”，开始导入素材和制作动作。</p></div>';
  $('#project-list').querySelectorAll('[data-project]').forEach(button => { button.onclick = () => openProject(button.dataset.project); });
  return result;
}

async function openProject(projectId) {
  if (state.busy || (dirty() && !confirm('切换工程会放弃当前未保存的草稿。继续？'))) return;
  await task('正在打开工程…',async () => {
    const snapshot = await api('projects/' + encodeURIComponent(projectId));
    clearTimeout(previewTimer); state.previewEpoch++; cancelRegionDrag(false);
    player.reset(); state.projectId = projectId;
    processedPreviews.clear(); state.adjustAction = ''; state.adjustPlaybackMode = 'runtime';
    state.action = null; state.source = null; state.review = null; state.reference = null; state.selected = 0; state.slot = 0; state.clip = 0;
    state.assetSelection.clear(); state.libraryMulti = false; state.lastAsset = null;
    state.mode = snapshot.sources.length ? 'source' : snapshot.assets.length ? 'action' : 'reference';
    state.sourceView = 'original'; state.playbackMode = 'runtime';
    $('#asset-search').value = ''; $('#asset-source').value = '';
    $('#source-upload').value = ''; $('#processed-upload').value = ''; $('#reference-upload').value = '';
    document.body.classList.remove('project-home'); setSnapshot(snapshot); suggestReviews(); showPane('canvas');
    history.replaceState(null,'','?project=' + encodeURIComponent(projectId));
    applyLayout(); player.resize();
    if (state.mode === 'source') schedulePreview();
    if (!snapshot.assets.length && !snapshot.sources.length) toast('工程已就绪，先导入角色参考，或切换到切割页导入原图。');
  });
}

async function showProjects() {
  if (state.busy || (dirty() && !confirm('返回工程列表会放弃当前未保存的草稿。继续？'))) return;
  await task('正在读取工程…',async () => {
    await listProjects(); clearTimeout(previewTimer); state.previewEpoch++; cancelRegionDrag(false);
    player.reset(); state.data = null; state.saved = null; state.savedData = null; state.projectId = null;
    processedPreviews.clear();
    previewRequest?.controller.abort(); previewRequest = null;
    state.preview = null; state.previewSource = null; state.previewKey = null; state.source = null;
    state.externalChange = false; $('#external-change').hidden = true;
    document.body.classList.add('project-home'); $('#project-name').textContent = '工程列表';
    history.replaceState(null,'',location.pathname);
  });
}

function showExternalChange(message, configChanged = false) {
  state.externalChange = true; $('#external-change').hidden = false;
  $('#external-merge').hidden = !configChanged;
  $('#external-message').textContent = message; updateSaveStatus();
}

async function refreshExternal() {
  if (state.busy || !state.projectId) return;
  await task('正在刷新工程…',async () => {
    const snapshot = await api('project');
    if (dirty() && snapshot.revision !== state.revision) {
      if (!confirm('配置已被外部修改。重新载入会放弃页面草稿；可先取消并下载配置草稿。继续？')) return;
      player.pause(); setSnapshot(snapshot);
    } else if (dirty()) {
      // Refresh pixels while keeping the user's recipe, history and selection.
      state.assets = snapshot.assets; state.sources = snapshot.sources; state.assetRevision = snapshot.asset_revision;
      state.references = snapshot.references || []; reconcileMaterials();
      state.legacyCount = snapshot.legacy_count; state.externalChange = false; $('#external-change').hidden = true; $('#external-merge').hidden = true;
      state.preview = null; state.previewSource = null; state.previewEpoch++;
      player.pause(); renderAll();
      if (snapshot.warnings?.length) toast(snapshot.warnings.join('\n'),true);
    } else { player.pause(); setSnapshot(snapshot); }
    if (state.mode === 'source') schedulePreview();
  });
}

let checkingDisk = false;
async function checkExternalChanges() {
  if (checkingDisk || state.busy || frameDrag || regionDrag || !state.projectId || document.hidden || document.body.classList.contains('project-home') || $('#project-dialog').open || $('#settings-dialog').open || $('#export-dialog').open || $('#merge-dialog').open) return;
  checkingDisk = true;
  const projectId = state.projectId;
  try {
    const changes = await api('changes');
    if (projectId !== state.projectId || state.busy || $('#settings-dialog').open) return;
    if (changes.revision === state.revision && changes.asset_revision === state.assetRevision) {
      if (state.externalChange) { state.externalChange = false; $('#external-change').hidden = true; updateSaveStatus(); }
      return;
    }
    if (dirty()) showExternalChange(changes.revision !== state.revision
      ? '配置已被外部修改，当前草稿已保留。可以合并双方修改。'
      : '素材已被外部修改。点击刷新可更新素材，并保留当前配置草稿。',changes.revision !== state.revision);
    else {
      const snapshot = await api('project');
      // A user may have edited or switched projects while the request was in flight.
      if (projectId === state.projectId && !state.busy && !frameDrag && !regionDrag && !dirty() && !$('#settings-dialog').open) { player.pause(); setSnapshot(snapshot); }
    }
  } catch (error) {
    if (projectId === state.projectId) showExternalChange('无法读取磁盘工程：' + error.message);
  } finally { checkingDisk = false; }
}

$('#projects-open').onclick = showProjects;
$('#projects-refresh').onclick = () => task('正在刷新列表…',listProjects);
$('#project-new').onclick = () => { $('#project-create-error').hidden = true; $('#project-form').reset(); $('#project-dialog').showModal(); };
$('#project-close').onclick = () => $('#project-dialog').close();
$('#project-form').onsubmit = async event => {
  event.preventDefault(); const submit = $('#project-create'); submit.disabled = true; $('#project-create-error').hidden = true;
  try {
    const id = $('#new-project-id').value.trim();
    const project = await api('projects',{name:$('#new-project-name').value.trim(), ...(id ? {id} : {}),
      frame_size:[Number($('#new-project-width').value),Number($('#new-project-height').value)],
      anchor:[Number($('#new-project-anchor-x').value),Number($('#new-project-anchor-y').value)]});
    $('#project-dialog').close(); await openProject(project.id);
  } catch (error) { $('#project-create-error').textContent = error.message; $('#project-create-error').hidden = false; }
  finally { submit.disabled = false; }
};
$('#external-refresh').onclick = refreshExternal;
$('#external-merge').onclick = async () => {
  if (!state.projectId || !dirty() || state.busy) return;
  const projectId = state.projectId, saved = state.saved, local = JSON.stringify(state.data);
  try {
    const snapshot = await api('project');
    if (projectId !== state.projectId || saved !== state.saved || local !== JSON.stringify(state.data)) {
      toast('读取磁盘配置期间草稿发生了变化，请重试合并',true); return;
    }
    if (snapshot.revision === state.revision) { await refreshExternal(); return; }
    const proposal = mergeDraft(JSON.parse(saved),state.data,snapshot.data);
    mergeContext = {projectId,saved,local,snapshot,proposal};
    $('#merge-summary').textContent = proposal.conflicts.length
      ? `有 ${proposal.conflicts.length} 处双方都修改过的字段；未选择时保留当前草稿值。`
      : '双方修改了不同字段，可直接应用合并结果。';
    $('#merge-conflicts').innerHTML = proposal.conflicts.map(conflict => {
      const key = conflictKey(conflict.path), label = conflict.path.join(' / ') || '整个配置';
      const localValue = conflict.localMissing ? '〈已删除〉' : JSON.stringify(conflict.local,null,2);
      const diskValue = conflict.diskMissing ? '〈已删除〉' : JSON.stringify(conflict.disk,null,2);
      return `<section class="merge-conflict"><h3>${escape(label)}</h3><div class="merge-values"><div><strong>当前草稿</strong><pre>${escape(localValue)}</pre></div><div><strong>磁盘版本</strong><pre>${escape(diskValue)}</pre></div></div><label>采用<select data-merge-choice="${escape(key)}"><option value="local">当前草稿</option><option value="disk">磁盘版本</option></select></label></section>`;
    }).join('');
    $('#merge-dialog').showModal();
  } catch (error) { toast('无法合并配置：' + error.message,true); }
};
$('#merge-close').onclick = () => $('#merge-dialog').close();
$('#merge-apply').onclick = () => {
  const context = mergeContext;
  if (!context || context.projectId !== state.projectId || context.saved !== state.saved ||
      context.local !== JSON.stringify(state.data)) { toast('草稿已变化，请重新打开合并窗口',true); return; }
  const choices = Object.fromEntries([...$('#merge-conflicts').querySelectorAll('[data-merge-choice]')]
    .map(select => [select.dataset.mergeChoice,select.value]));
  const merged = resolveMerge(context.proposal,choices);
  player.pause(); setSnapshot(context.snapshot);
  state.data = merged;
  if (JSON.stringify(merged) !== state.saved) state.history = [clone(context.snapshot.data)];
  mergeContext = null; $('#merge-dialog').close(); renderAll();
  toast('修改已合并到草稿；请检查后保存工程');
};
$('#draft-download').onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(state.data,null,2) + '\n'],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'pipeline-draft.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
};
window.addEventListener('focus',checkExternalChanges);
setInterval(checkExternalChanges,12000);
async function save() {
  return task('正在保存工程…', async () => {
    const result = await api('save', payload());
    state.revision = result.revision; state.saved = JSON.stringify(state.data); state.savedData = clone(state.data);
    try {
      const snapshot = await api('project');
      if (snapshot.revision === state.revision && snapshot.asset_revision === state.assetRevision) {
        state.sources = snapshot.sources; state.assets = snapshot.assets; state.references = snapshot.references || [];
        state.legacyCount = snapshot.legacy_count; reconcileMaterials(); renderAll();
      }
      toast('工程已保存');
    } catch (error) { toast('工程已保存，但素材状态暂未刷新：' + error.message,true); }
  });
}
function mode(value, sourceView = 'processed') {
  cancelRegionDrag();
  cancelFrameDrag(false);
  $('#inspector-content').scrollTop = 0;
  if (value === 'source' && sourceView !== state.sourceView) {
    state.preview = null; state.previewKey = null; state.previewError = null;
  }
  if (value === 'source') state.sourceView = sourceView;
  state.playbackMode='runtime'; state.adjustPlaybackMode='runtime';
  state.mode = value; state.selected = 0; state.slot = 0; state.clip = 0; player.pause();
  if (value === 'source' && sourceView === 'processed') chooseAdjustmentAction();
  clearTimeout(previewTimer); state.previewEpoch++; cancelRegionDrag(false);
  if (value === 'source') schedulePreview(); renderAll();
}
function renderAll() {
  if (!state.data) return;
  cancelRegionDrag(false);
  cancelFrameDrag(false);
  $('#project-name').textContent = state.data.project?.name || state.data.character;
  const actionNames = Object.keys(state.data.actions);
  if (!state.data.actions[state.action]) state.action = actionNames[0];
  if (!state.data.actions[state.adjustAction]) state.adjustAction = '';
  if (!reviews()[state.review]) state.review = Object.keys(reviews())[0];
  document.querySelectorAll('button[data-mode]').forEach(button => {
    const active = (button.dataset.mode === state.mode || button.dataset.mode === 'action' && state.mode === 'review') && (!button.dataset.view || button.dataset.view === state.sourceView);
    button.classList.toggle('active', active); button.setAttribute('aria-selected', active);
  });
  $('#editor-kind').textContent = {source:'SOURCE PROCESSING',action:'ACTION EDITOR',review:'TRANSITION REVIEW',reference:'REFERENCE IMAGES'}[state.mode];
  $('#editor-title').textContent = state.mode === 'source' ? state.source || '添加原图' : state.mode === 'action' ? state.action || '新建动作' : state.mode === 'reference' ? referenceInfo()?.file || '添加参考图' : currentReview()?.name || '新建预览';
  $('#sidebar-title').textContent = {source:'原图',action:'动作库',review:'Review 序列',reference:'参考图'}[state.mode];
  $('#new-item').setAttribute('aria-label', {source:'批量导入原图',action:'新建动作',review:'新建预览',reference:'批量导入参考图'}[state.mode]);
  $('#delete-item').hidden = false;
  $('#delete-item').textContent = {source:'删除原图',reference:'删除参考图',action:'删除动作',review:'删除序列'}[state.mode];
  $('#delete-item').setAttribute('aria-label', {source:'删除所选原图',reference:'删除所选参考图',action:'删除所选动作',review:'删除所选 Review 序列'}[state.mode]);
  $('#timeline-title').textContent = {source:'处理结果 · 点击查看单帧',action:state.playbackMode === 'runtime' ? '游戏帧时间轴' : '展示播放时间轴',review:'动作衔接时间轴',reference:'参考资料'}[state.mode];
  $('#timeline-help').textContent = {source:'处理结果中拖动图片微调位置 · 原图模式下拖拽画框',action:'拖拽排序 · 点击素材添加 · Delete 移除所选帧',review:'拖拽动作片段排序 · 片段按指定次数播放',reference:'参考图独立保存，不参与切图；完整工程备份会包含参考资料'}[state.mode];
  renderItems(); renderLibraryFilters(); renderLibrary(); renderInspector(); renderTimeline(); refreshPlayer(); updateSaveStatus();
  renderWorkflow();
}
function renderWorkflow() {
  const slicing = state.mode === 'source' && state.sourceView === 'original';
  document.body.dataset.mode = state.mode;
  document.body.dataset.sourceView = state.sourceView;
  $('#editor-kind').textContent = {reference:'角色资料',source:slicing ? '切割原帧' : '调整与对齐',action:'动作编排',review:'衔接检查'}[state.mode];
  $('#sidebar-title').textContent = '工作目录';
  $('#inspector-title').textContent = {reference:'角色约定',source:slicing ? '切割设置' : '帧调整',action:'动作设置',review:'衔接设置'}[state.mode];
  $('#inspector-step').textContent = state.mode === 'source' ? slicing ? '02 / 05' : '03 / 05' : '';
  $('#timeline-title').textContent = state.mode === 'source' ? slicing ? '原帧预览 · 保留原始尺寸' : '调整预览 · 点击选择单帧' : $('#timeline-title').textContent;
  $('#timeline-help').textContent = state.mode === 'source' ? slicing ? '选择 / 移动 · 拖动边角缩放 · 方向键微移 · Esc 取消' : '拖动当前帧调整位置 · 应用后同步到动作' : $('#timeline-help').textContent;
  $('#reference-board').hidden = state.mode !== 'reference';
  $('#slice-tools').hidden = !slicing;
  $('#adjustment-context').hidden = state.mode !== 'source' || slicing;
  $('#adjust-action').innerHTML = '<option value="">素材检查（非动作编排）</option>' + Object.keys(state.data.actions).map(name=>`<option value="${escape(name)}" ${name === state.adjustAction ? 'selected' : ''}>${escape(name)}</option>`).join('');

  $('#adjust-context-note').textContent = state.adjustAction ? '按动作完整顺序播放 · 重复素材同步更新' : `原帧顺序 · ${state.data.defaults?.fps || 12} FPS`;
  if (state.mode === 'source' && !slicing) $('#timeline-title').textContent = state.adjustAction ? `${state.adjustAction} · ${state.adjustPlaybackMode === 'runtime' ? '游戏播放' : '展示播放'}` : '素材检查 · 非动作编排';
  $('#slice-select').classList.toggle('active',sliceTool === 'select');
  $('#slice-create').classList.toggle('active',sliceTool === 'create');
  $('#action-navigation').hidden = !['action','review'].includes(state.mode);
  $('#action-edit').classList.toggle('active',state.mode === 'action');
  $('#action-review').classList.toggle('active',state.mode === 'review');
  const idle = asset(state.data.actions.idle ? actionSteps(state.data,'idle')[0]?.ref : null);
  if (state.mode === 'reference') {
    const ref = referenceInfo();
    $('#reference-board').innerHTML = `<div class="reference-heading"><span class="eyebrow">CHARACTER REFERENCE</span><h1>先对齐角色，再开始创作</h1><p>对照人设与当前 IDLE，检查形象、比例和配色。</p></div><div class="reference-comparison"><section><header><h2>人设参考</h2><button id="board-import" class="text-button">＋ 导入参考图</button></header><div class="reference-art">${ref ? `<img src="${escape(ref.url)}" alt="${escape(ref.file)}">` : '<div class="reference-empty">还没有参考图<br><small>导入人设图，开始建立角色</small></div>'}</div><footer>${escape(ref?.file || '支持 PNG、WebP 等图片')}</footer></section><section><header><h2>当前 IDLE 首帧</h2><span class="badge">播放参考</span></header><div class="reference-art checker">${idle ? `<img src="${escape(idle.url)}" alt="当前 IDLE 首帧">` : '<div class="reference-empty">尚未建立 idle 动作<br><small>完成切割和调整后，在动作页添加帧</small></div>'}</div><footer>${escape(idle?.ref || '当前未绑定可播放的 IDLE')}</footer></section></div><div class="reference-next"><p>参考图用于对照；要制作动画，请另行导入动作原图。</p><button id="board-next" class="primary">开始切割原图 →</button></div>`;
    $('#board-import').onclick = () => $('#reference-upload').click();
    $('#board-next').onclick = () => mode('source','original');
  }
}
function renderItems() { explorer.render(); }
function renderLibraryFilters() {
  const select = $('#asset-source'), value = select.value;
  const groups = [...new Set(state.assets.map(a => a.ref.split('/').slice(0,-1).join('/')))];
  select.innerHTML = '<option value="">全部来源</option>' + groups.map(group => `<option value="${escape(group)}">${escape(group)}</option>`).join('');
  if (groups.includes(value)) select.value = value;
}
function visibleAssets() { return composition.visible(); }
function renderLibrary() { $('#asset-kind').value='sprite'; composition.renderLibrary(); $('#directory-frame-count').textContent=state.assets.length; }
function selectAsset(ref,event={}) { composition.toggleSelection(`sprite:${ref}`,event); }
function addAsset(ref,at) { composition.insert([{kind:'sprite',ref}],at); }
function addAssets(refs,at) { composition.insert(refs.map(ref=>({kind:'sprite',ref})),at); }

function activeSteps() {
  if (state.mode === 'reference') return [];
  if (state.mode === 'source') {
    if (state.sourceView === 'processed') {
      const available = adjustmentFrames();
      const order = state.adjustAction && state.data.actions[state.adjustAction]
        ? actionSteps(state.data,state.adjustAction,'runtime')
        : (state.preview?.stage === 'process' && state.previewSource === state.source ? state.preview.frames : state.assets.filter(frame=>sourceForFrame(state.sources,frame.ref)?.file === state.source))
          .map((frame,index)=>({ref:frame.ref,frame:index,duration_ms:Math.max(1,roundMs(1000/(state.data.defaults?.fps || 12)))}));
      const offsets = Object.fromEntries(Object.entries(state.previewOffsets).map(([id,value])=>[state.source?.replace(/\.[^.]+$/,'')+'/'+id+'.png',value]));
      return composeAdjustmentSteps(order,available,state.assets,offsets);
    }
    if (state.preview && state.previewSource === state.source) return state.preview.frames.map((frame, i) => ({...frame, frame:i, duration_ms:100,
      ...(state.previewOffsets[frame.id] ? {previewOffset:state.previewOffsets[frame.id]} : {})}));
    if (state.sourceView === 'original') return [];
    const prefix = state.source ? state.source.replace(/\.[^.]+$/, '') + '/' : '';
    return state.assets.filter(a => prefix && a.ref.startsWith(prefix)).map((a, i) => ({...a, frame:i, id:a.ref.split('/').pop().replace('.png',''),duration_ms:100}));
  }
  if (state.mode === 'action') return state.action ? actionSteps(state.data, state.action, 'runtime') : [];
  return currentReview() ? reviewSteps(state.data, currentReview()) : [];
}
function chooseAdjustmentAction() {
  const names=Object.keys(state.data.actions).filter(name=>actionSteps(state.data,name).some(step=>sourceForFrame(state.sources,step.ref)?.file === state.source));
  state.adjustAction = names.includes(state.adjustAction) ? state.adjustAction : names.includes(state.action) ? state.action : names[0] || '';
  if (!state.source && state.data.actions[state.action]) state.adjustAction = state.action;
  if (state.adjustAction) $('#loop-preview').checked = !!merge(state.data.defaults,state.data.actions[state.adjustAction]).loop;
  if (state.adjustAction) state.selected = Math.max(0,actionSteps(state.data,state.adjustAction,'runtime').findIndex(step=>sourceForFrame(state.sources,step.ref)?.file === state.source));
}
function adjustmentFrames() {
  const result=[];
  for (const [source,entry] of processedPreviews) {
    if (entry.key === previewKey(source,'processed')) result.push(...entry.result.frames);
  }
  // Keep the last visible pixels while a newer recipe is computing.
  if (state.preview?.stage === 'process' && state.previewSource === state.source) result.push(...state.preview.frames);
  return result;
}
function selectAdjustmentStep(index) {
  const step=activeSteps()[index], owner=sourceForFrame(state.sources,step?.ref);
  state.selected=index;
  if (owner && owner.file !== state.source) {
    state.source=owner.file; state.preview=null; state.previewKey=null; state.previewError=null; state.previewOffsets={};
    state.previewEpoch++; schedulePreview();
  }
}
function refreshPlayer({seek = true} = {}) {
  player.sourceView = null; player.setProject(state.data, state.assets);
  player.idle = state.data.actions.idle ? actionSteps(state.data,'idle')[0]?.ref : null;
  const steps = activeSteps();
  if (state.mode === 'reference' && referenceInfo()) {
    const image = referenceInfo(); player.size = image.size;
    player.sourceView = {url:image.url,boxes:[],selected:0}; player.resize();
    $('#canvas-label').textContent = `${image.size.join(' × ')} · 参考图`;
  } else if (state.mode === 'source' && state.sourceView === 'original' && sourceInfo()) {
    const source = sourceInfo(); player.size = source.size;
    const regions = regionFrames(), boxes = regions.map(frame => frame.box);
    player.sourceView = {url:source.url,boxes,selected:state.selected}; player.resize();
    player.sourceView.ids = regions.map(frame=>frame.id);
    $('#canvas-label').textContent = `${source.size.join(' × ')} · 原始像素 · ${sliceTool === 'create' ? '拖拽新增区域' : '拖动区域或边角直接编辑'}`;
  } else {
    $('#canvas-label').textContent = `${state.data.frame_size.join(' × ')} · 固定锚点 (${state.data.anchor.pixels.join(', ')})`;
  }
  if (seek) player.setSteps(steps, state.selected);
  else player.updateSteps(steps);
  $('#stage').classList.toggle('frame-movable',canDragFrame());
  $('#empty-canvas').hidden = steps.length > 0 || !!player.sourceView;
  const missing = steps.filter(step => !step.url && !asset(step.ref));
  if (missing.length) { $('#empty-canvas').hidden = false; $('#empty-canvas strong').textContent = '动作引用的素材尚未就绪'; $('#empty-canvas p').textContent = '点击“准备缺失素材”，或从已有最终帧导入'; }
  else { $('#empty-canvas strong').textContent = state.mode === 'reference' ? '添加角色参考图' : state.mode === 'source' ? '导入原图，开始处理素材' : '从素材开始，编排动作'; $('#empty-canvas p').textContent = state.mode === 'reference' ? '点击参考图旁的 ＋，可一次选择多张图片' : state.mode === 'source' ? '点击原图旁的 ＋，选择图片后预览并应用处理' : '点击左侧素材，或将它拖入下方时间轴'; }
  $('#total-time').textContent = (steps.reduce((sum, step) => sum + step.duration_ms, 0) / 1000).toFixed(2) + 's';
  $('#timeline-stats').textContent = composition.isEditing() ? `${composition.slots().length} 个槽位 / ${steps.length} 帧` : `${steps.length} FRAMES`;
  $('#play').textContent = player.playing ? 'Ⅱ' : '▶';
  $('#play').disabled = !steps.length || !!player.sourceView || (state.mode === 'source' && state.sourceView === 'processed' && steps.some(step=>!step.url));
  player.loop = $('#loop-preview').checked;
}
function onStep(index) {
  if (!state.data) return;
  const step = player.steps[index];
  $('#play-position').textContent = `${String(step ? index + 1 : 0).padStart(3,'0')} / ${String(player.steps.length).padStart(3,'0')}`;
  $('#frame-info').textContent = state.mode === 'source' && state.sourceView === 'original' ? `区域 ${String(index + 1).padStart(2,'0')} · 原始尺寸` : step ? `${step.action ? step.action + ' / ' : ''}${step.ref || step.id} · ${step.duration_ms} ms` : '—';
  $('#play').textContent = player.playing ? 'Ⅱ' : '▶';
  document.querySelectorAll('.timeline-card').forEach(card => {
    const active = composition.isEditing() ? Number(card.dataset.index) === step?.slot : Number(card.dataset.index) === index;
    card.classList.toggle('playing', active);
  });
}
function renderTimeline() {
  if (composition.isEditing()) return composition.renderTimeline();
  const timeline=$('#timeline'), scroll=timeline.scrollLeft, steps=activeSteps();
  timeline.classList.remove('composition-timeline');
  timeline.innerHTML=steps.map((step,index)=>`<button class="timeline-card ${index === state.selected ? 'selected' : ''}" data-index="${index}" data-ref="${escape(step.ref)}" data-duration="${step.duration_ms}">${step.url || asset(step.ref)?.url ? `<img src="${escape(step.url || asset(step.ref).url)}" alt="${escape(step.ref)}">` : '<span class="slot-empty">缺失图片</span>'}<span class="frame-caption"><span>${String(index+1).padStart(2,'0')}</span><span>${escape(step.ref)}</span></span></button>`).join('') || '<div class="timeline-empty">当前没有可预览的帧</div>';
  timeline.scrollLeft=scroll;
  timeline.querySelectorAll('[data-index]').forEach(card=>card.onclick=()=>{
    const index=Number(card.dataset.index); player.pause();
    if (state.mode === 'source' && state.sourceView === 'processed') selectAdjustmentStep(index); else state.selected=index;
    player.seek(index); renderInspector(); renderTimeline(); onStep(player.index);
    if (player.sourceView) { player.sourceView.selected=index; player.draw(); }
    if (state.mode === 'source' && state.sourceView === 'processed') { renderItems(); renderWorkflow(); }
  });
  timeline.ondragover=null; timeline.ondrop=null;
  $('#timeline-tools').innerHTML=state.mode === 'source' ? '<button id="source-preview">刷新预览</button>' : '';
  $('#source-preview')?.addEventListener('click',()=>previewSource(true));
}
function moveTimeline(from,to) { if (composition.isEditing()) composition.move(from,to); }
function duplicateFrame() { if (composition.isEditing()) composition.duplicate(); }
function removeFrame() { if (composition.isEditing()) composition.remove(); }

function renderInspector() {
  $('#inspector-actions').innerHTML = '';
  if (state.mode === 'reference') {
    const image = referenceInfo();
    $('#inspector-content').innerHTML = section('工程画布',info('尺寸',state.data.frame_size.join(' × ')) + info('锚点',state.data.anchor.pixels.join(', ')) + '<button id="reference-settings" class="wide">修改工程设置</button>') + (image ? section('所选参考',info('文件',image.file) + info('尺寸',image.size.join(' × '))) : '<p class="hint">点击 ＋ 导入人设图或已确认的角色参考。</p>') + section('对照要点','<ul class="reference-checklist"><li>角色朝向与头身比例</li><li>配色、服装与道具状态</li><li>身体大小与脚底位置</li></ul><p class="hint">当前 IDLE 首帧来自已有动作，不代表已经通过视觉验收。</p>');
    $('#reference-settings').onclick = () => $('#settings-open').click();
    return;
  }
  const markup = state.mode === 'source' ? sourceInspector() : state.mode === 'action' ? actionInspector() : reviewInspector();
  const footer = state.mode === 'source' ? markup.indexOf('<div class="inspector-next">') : -1;
  $('#inspector-content').innerHTML = footer < 0 ? markup : markup.slice(0,footer);
  if (footer >= 0) $('#inspector-actions').innerHTML = markup.slice(footer);
  if (state.mode === 'source') bindSourceInspector(); else if (state.mode === 'action') bindActionInspector(); else bindReviewInspector();
}
function actionInspector() { return composition.inspector(); }
function bindValue(id, operation, options = {}) {
  const input = $('#' + id); if (!input) return;
  input.addEventListener('change', () => {
    if (input.type === 'number' && !input.checkValidity()) { input.reportValidity(); return; }
    const value = input.type === 'checkbox' ? input.checked : input.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value;
    change(() => operation(value),options);
  });
}
function bindActionInspector() { composition.bindInspector(); }
function resolvedSource() {
  const own = state.data.sources?.[state.source] || {};
  const defaults = state.data.defaults || {};
  return {extract:merge(defaults.extract,own.extract),process:merge(defaults.process,own.process)};
}
function sourceRules() { state.data.sources ||= {}; return state.data.sources[state.source] ||= {}; }
function selectedSlice() { return activeSteps()[state.selected]; }
function regionFrames() {
  if (!state.source) return [];
  const extract = resolvedSource().extract, prefix = state.source.replace(/\.[^.]+$/,'') + '/';
  if (extract.method === 'boxes' && Array.isArray(extract.region_ids) && Array.isArray(extract.boxes) && extract.region_ids.length === extract.boxes.length)
    return extract.boxes.map((box,i)=>({id:extract.region_ids[i],box:[...box],ref:prefix+extract.region_ids[i]+'.png'}));
  return state.previewSource === state.source && state.previewKey === previewKey(state.source) && state.preview?.stage === 'extract'
    ? state.preview.frames.map(frame=>({...frame,box:[...frame.box]})) : [];
}
function sliceNextId() {
  const key = state.projectId + '/' + state.source;
  const next = Math.max(sliceAllocations.get(key) || 0,resolvedSource().extract.next_id || 0,
    state.savedData?.sources?.[state.source]?.extract?.next_id || 0,...regionFrames().map(frame=>Number(frame.id)+1));
  sliceAllocations.set(key,next); return next;
}
function setManualRegions(regions, nextId = sliceNextId()) {
  sourceRules().extract = manualExtraction(resolvedSource().extract,regions,nextId);
  sliceAllocations.set(state.projectId + '/' + state.source,sourceRules().extract.next_id);
}
async function saveSlices() {
  if (!state.source || state.busy || regionDrag) return;
  await task('正在保存当前切割…',async () => {
    if (state.previewKey !== previewKey(state.source)) await previewSource();
    if (state.previewError || state.previewKey !== previewKey(state.source)) throw new Error('请先修正切割预览中的错误');
    const regions = regionFrames(), available = new Set(regions.map(frame=>frame.ref));
    const prefix = state.source.replace(/\.[^.]+$/,'') + '/';
    const broken = allResources(state.data).flatMap(target=>slotsOf(ownCompositionSpec(target),target.kind)).filter(slot=>slot.resource.kind === 'sprite').map(slot=>slot.resource.ref).filter(ref=>ref.startsWith(prefix) && !available.has(ref));
    if (broken.length) throw new Error('区域仍被当前动作草稿引用，请先移除或替换：' + [...new Set(broken)].join('、'));
    const keys = new Set(regions.map(frame=>frame.id));
    if (Object.keys(resolvedSource().process.overrides || {}).some(key=>!keys.has(key))) throw new Error('被移除区域仍有单帧调整，请先重置这些帧');
    const source = state.source, local = clone(state.data), history = state.history, future = state.future, selected = state.selected;
    const extract = {...clone(resolvedSource().extract),next_id:sliceNextId(),
      identities:regions.map(frame=>({file:frame.id+'.png',source_box:[...frame.box]}))};
    const snapshot = await api('save-slices',{source,extract,revision:state.revision,asset_revision:state.assetRevision});
    setSnapshot(snapshot);
    local.sources ||= {}; local.sources[source] ||= {};
    local.sources[source].extract = clone(snapshot.data.sources[source].extract);
    state.data = local; state.history = history; state.future = future; state.selected = selected;
    renderAll(); schedulePreview();
    toast(dirty() ? '当前切割已保存，其他修改仍保留在草稿中' : '当前切割与原始切片已保存');
  });
}
function sourceInspector() {
  if (!state.source) return '<div class="inspector-empty"><h3>从一张原图开始</h3><p>点击左上角 ＋ 导入动作原图，再选择自动识别、网格或手动框选。</p></div>';
  const {extract,process} = resolvedSource(), slice = state.sourceView === 'original' ? regionFrames()[state.selected] : selectedSlice();
  const override = process.overrides?.[slice?.id] || {};
  const error = state.previewError ? `<div class="error-panel">${escape(state.previewError)}</div>` : '';
  if (state.sourceView === 'processed' && slice && sourceForFrame(state.sources,slice.ref)?.file !== state.source)
    return error + section('只读素材',info('引用',slice.ref) + '<p class="hint">此帧没有可直接调整的原图切片。可以播放对照，选择有原图的帧后再调整。</p>');
  if (state.sourceView === 'original') {
    const method = extract.method || 'components';
    const methods = [['components','自动识别'],['grid','规则网格'],['boxes','手动区域'],['image','整张单帧']];
    const box = slice?.box || extract.boxes?.[state.selected];
    return error + section('切割方式',label('识别方式',`<select id="extract-method">${methods.map(([value,name]) => `<option value="${value}" ${value === method ? 'selected' : ''}>${name}</option>`).join('')}</select>`) +
      (['grid','components'].includes(method) ? `<div class="field-row">${label('列数',number('extract-cols',extract.cols ?? '', 'min="1" placeholder="自动"'))}${label('行数',number('extract-rows',extract.rows ?? '', 'min="1" placeholder="自动"'))}</div>` : '') +
      (method === 'components' ? `<details><summary>识别参数</summary>${label('透明度阈值',number('extract-alpha',extract.alpha_threshold || 16,'min="1" max="255"'))}${label('最小组件像素',number('extract-min',extract.min_component_pixels || 80,'min="1"'))}${label('主体最少像素',number('extract-major',extract.major_min_pixels || 10000,'min="1"'))}${label('主体占比',number('extract-fraction',extract.major_fraction ?? .02,'min="0" max="1" step="0.01"'))}</details>` : '') + '<button id="detect-slices" class="wide">重新预览切割</button>') +
      section(`所选区域 ${String(state.selected + 1).padStart(2,'0')} · ID ${escape(slice?.id || '—')}`,box ? `<div class="field-row">${label('X',number('slice-x',box[0],'min="0"'))}${label('Y',number('slice-y',box[1],'min="0"'))}</div><div class="field-row">${label('宽度',number('slice-width',box[2]-box[0],'min="1"'))}${label('高度',number('slice-height',box[3]-box[1],'min="1"'))}</div><p class="hint">修改范围会切换为手动区域。坐标使用原图像素。</p><button id="remove-box" class="wide danger">移除此区域</button>` : '<p class="hint">预览后选择一帧，或在原图上拖拽新增区域。</p>') +
      section('原帧',info('原图尺寸',sourceInfo().size.join(' × ')) + '<p class="hint">保留原始尺寸与透明像素。此处只切割，不缩放或对齐。</p>') +
      `<details class="advanced-rules"><summary>高级切割规则</summary><textarea id="extract-json" rows="6">${escape(JSON.stringify(extract,null,2))}</textarea><button id="apply-extract-json" class="wide">更新切割规则</button></details>` +
      '<div class="inspector-next"><button id="save-slices" class="wide">保存当前切割</button><button id="view-processed" class="primary wide">下一步：调整帧 →</button><p class="hint">仅保存当前原图的切割与原始切片；其他草稿保持未保存。</p></div>';
  }
  return error + section('单帧微调',slice ? `<span class="selected-ref">${escape(slice.ref)}</span><div class="field-row">${label('水平偏移',number('override-x',override.offset?.[0] ?? process.offset?.[0] ?? 0,'step="1"'))}${label('垂直偏移',number('override-y',override.offset?.[1] ?? process.offset?.[1] ?? 0,'step="1"'))}</div>` +
      label('独立缩放倍率',number('override-scale',override.scale ?? '', 'min="0.01" max="10" step="0.01" placeholder="继承整组"')) + '<p class="hint">可直接拖动画面中的当前帧。单帧设置覆盖整组值；留空缩放可继承整组。</p><button id="clear-override" class="wide">重置本帧</button>' : '<p class="hint">正在准备预览。选择下方原帧后可单独调整。</p>') +
    section('整组基准',label('对齐方式',`<select id="process-mode"><option value="anchor" ${process.mode === 'anchor' || !process.mode ? 'selected' : ''}>轮廓裁切 + 锚点对齐</option><option value="contain" ${process.mode === 'contain' ? 'selected' : ''}>完整切片等比容纳</option><option value="copy" ${process.mode === 'copy' ? 'selected' : ''}>原样复制（相同画布）</option></select>`) +
      `<div class="field-row">${label('缩放倍率',number('process-scale',process.scale ?? 1,'min="0.01" max="10" step="0.01"'))}${label('目标高度',number('process-height',process.fit_height ?? '', 'min="1" placeholder="不启用"'))}</div>` +
      `<div class="field-row">${label('水平偏移',number('process-x',process.offset?.[0] || 0,'step="1"'))}${label('垂直偏移',number('process-y',process.offset?.[1] || 0,'step="1"'))}</div>` +
      info('实际组缩放',state.preview?.scale?.toFixed(4) || '预览后显示') +
      `<details><summary>边界与高级设置</summary><label class="field-inline">最大自适应倍率${number('process-max-scale',process.max_scale ?? 1,'min="0.01" max="10" step="0.05"')}</label><label class="field-inline">垂直限制在画布内<input id="process-clamp" type="checkbox" ${process.clamp_y ? 'checked' : ''}></label><label class="field-inline">边缘留白${number('process-padding',process.padding ?? 0,'min="0"')}</label><label class="field-inline">越界处理<select id="process-overflow"><option value="error" ${process.overflow !== 'clip' ? 'selected' : ''}>提示错误</option><option value="clip" ${process.overflow === 'clip' ? 'selected' : ''}>允许裁切</option></select></label><p class="hint">目标高度按整组最高轮廓计算，不逐帧拉成同高。</p></details>`) +
    `<details class="advanced-rules"><summary>高级处理规则</summary><textarea id="process-json" rows="7">${escape(JSON.stringify(process,null,2))}</textarea><button id="apply-process-json" class="wide">更新处理规则</button></details>` +
    '<div class="inspector-next"><button id="apply-source" class="primary wide">应用调整并保存工程</button><p class="hint">只写入变化的帧，并保存整个工程草稿。动作页与导出使用已应用结果。</p><div class="boundary-controls"><button id="view-original">← 返回切割</button><button id="next-actions">编排动作 →</button></div></div>';
}
function bindSourceInspector() {
  if (!state.source) return;
  const opts = {preview:true};
  const setExtract = (key,value) => { const rules = sourceRules(); rules.extract ||= {}; rules.extract[key] = value; };
  const setProcess = (key,value) => { const rules = sourceRules(); rules.process ||= {}; rules.process[key] = value; };
  $('#view-original')?.addEventListener('click',() => mode('source','original'));
  $('#view-processed')?.addEventListener('click',() => mode('source','processed'));
  $('#detect-slices')?.addEventListener('click',() => previewSource(true));
  $('#save-slices')?.addEventListener('click',saveSlices);
  $('#next-actions')?.addEventListener('click',() => mode('action'));
  bindValue('extract-method', value => {
    const regions = regionFrames(), nextId = sliceNextId();
    if (value === 'boxes' && regions.length) { setManualRegions(regions,nextId); return; }
    const extract = {...resolvedSource().extract,method:value,next_id:nextId};
    delete extract.region_ids;
    if (value === 'boxes') { extract.boxes = []; extract.region_ids = []; }
    if (regions.length) extract.identities = regions.map(frame=>({file:frame.id+'.png',source_box:frame.box}));
    if (value === 'grid') { extract.cols ||= 1; extract.rows ||= 1; }
    sourceRules().extract = extract;
  },opts);
  const setLayout = (key,value) => {
    setExtract(key,value);
    if (value === null) { const rules = sourceRules(); rules.extract = {...resolvedSource().extract,...rules.extract}; delete rules.extract.cols; delete rules.extract.rows; }
  };
  bindValue('extract-cols',value => setLayout('cols',value),opts); bindValue('extract-rows',value => setLayout('rows',value),opts);
  [['extract-alpha','alpha_threshold'],['extract-min','min_component_pixels'],['extract-major','major_min_pixels'],['extract-fraction','major_fraction']].forEach(([id,key]) => bindValue(id,value => setExtract(key,value),opts));
  bindValue('extract-boxes', value => { try { const boxes = JSON.parse(value); if (!Array.isArray(boxes)) throw new Error(); setExtract('boxes',boxes); } catch { toast('区域必须是矩形坐标数组',true); } },opts);
  if ($('#apply-extract-json')) $('#apply-extract-json').onclick = () => {
    try { const rules = JSON.parse($('#extract-json').value); if (!rules || Array.isArray(rules) || typeof rules !== 'object') throw new Error(); change(() => { sourceRules().extract = rules; },opts); }
    catch { toast('切图规则必须是有效的 JSON 对象',true); }
  };
  if ($('#apply-process-json')) $('#apply-process-json').onclick = () => {
    try { const rules = JSON.parse($('#process-json').value); if (!rules || Array.isArray(rules) || typeof rules !== 'object') throw new Error(); change(() => { sourceRules().process = rules; },opts); }
    catch { toast('处理规则必须是有效的 JSON 对象',true); }
  };
  ['x','y','width','height'].forEach(key => bindValue('slice-' + key,value => {
    const regions = regionFrames(), frame = regions[state.selected]; if (!frame || value === null) return;
    const [x,y,right,bottom] = frame.box;
    const next = key === 'x' ? [value,y,value+right-x,bottom] : key === 'y' ? [x,value,right,value+bottom-y] : key === 'width' ? [x,y,x+value,bottom] : [x,y,right,y+value];
    const [width,height] = sourceInfo().size;
    if (next[2] > width || next[3] > height) { toast('区域不能超出原图边界',true); return; }
    frame.box = next; setManualRegions(regions);
  },opts));
  $('#remove-box')?.addEventListener('click',removeRegion);
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
  if ($('#apply-source')) $('#apply-source').onclick = () => task('正在应用处理并保存工程…',async () => {
    const snapshot = await api('apply',payload({source:state.source}));
    const playback={index:player.index,elapsed:player.elapsed,playing:player.playing};
    setSnapshot(snapshot); player.seek(playback.index); player.elapsed=playback.elapsed; player.playing=playback.playing;
    toast('已更新变化的帧并保存工程'); await previewSource();
  });
}
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(() => previewSource(),350); }
function previewKey(source, view = state.sourceView) {
  return JSON.stringify([state.projectId, source, view, state.sources.find(item=>item.file === source)?.url, state.assetRevision,
    state.data.frame_size, state.data.anchor, state.data.defaults?.extract, state.data.defaults?.process,
    state.data.sources?.[source]]);
}
function previewKnown(result) {
  return Object.fromEntries((result?.frames || []).filter(frame=>frame.url && frame.version).map(frame=>[frame.ref,frame.version]));
}
function rememberPreview(key,result) {
  previewCache.delete(key); previewCache.set(key,result);
  if (previewCache.size > 4) previewCache.delete(previewCache.keys().next().value);
}
function patchAdjustmentTimeline() {
  const steps=activeSteps(), cards=[...$('#timeline').querySelectorAll('[data-index]')];
  if (cards.length !== steps.length || cards.some((card,i)=>card.dataset.ref !== steps[i].ref || Number(card.dataset.duration) !== steps[i].duration_ms)) {
    renderTimeline(); return;
  }
  cards.forEach((card,i)=>{
    const image=card.querySelector('img');
    if (!image && steps[i].url) { renderTimeline(); return; }
    if (image && image.getAttribute('src') !== steps[i].url) image.setAttribute('src',steps[i].url || '');
    card.classList.toggle('selected',i === state.selected);
  });
}
function refreshAdjustment() {
  const editingField = ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName) && $('#inspector-content').contains?.(document.activeElement);
  if (!editingField) renderInspector();
  patchAdjustmentTimeline(); refreshPlayer({seek:false}); updateSaveStatus();
}
function showPreview(result, source, key) {
  const selectedId = state.sourceView === 'original' ? regionFrames()[state.selected]?.id : null;
  sliceAllocations.set(state.projectId + '/' + source,Math.max(sliceAllocations.get(state.projectId + '/' + source) || 0,result.next_id || 0));
  if (result.stage === 'process') processedPreviews.set(source,{key,result});
  state.preview = result; state.previewSource = source; state.previewKey = key; state.previewError = null; state.previewOffsets = {};
  if (selectedId && result.frames.some(frame=>frame.id === selectedId)) state.selected = result.frames.findIndex(frame=>frame.id === selectedId);
  state.selected = Math.min(state.selected,Math.max(0,activeSteps().length - 1));
  if (state.mode === 'source') {
    if (state.sourceView === 'processed') refreshAdjustment();
    else { renderInspector(); renderTimeline(); refreshPlayer(); updateSaveStatus(); }
  }
  $('#status-message').textContent = result.stage === 'extract' ? `切割预览：${result.frames.length} 帧 · 原始尺寸 · 未改写素材` : `调整预览已更新 · 整组倍率 ${result.scale.toFixed(4)} · 尚未应用`;
}
async function prepareActionPreviews(epoch) {
  if (!state.adjustAction || !state.data.actions[state.adjustAction] || state.sourceView !== 'processed') return;
  const sources=[...new Set(actionSteps(state.data,state.adjustAction,'runtime').map(step=>sourceForFrame(state.sources,step.ref)?.file).filter(Boolean))];
  for (const source of sources) {
    if (epoch !== state.previewEpoch || state.mode !== 'source') return;
    const key=previewKey(source,'processed'), previous=processedPreviews.get(source)?.result;
    if (processedPreviews.get(source)?.key === key) continue;
    const result = previewCache.get(key) || mergePreviewFrames(previous,await api('preview',{data:clone(state.data),source,stage:'process',known:previewKnown(previous)}));
    if (epoch !== state.previewEpoch || state.mode !== 'source') return;
    rememberPreview(key,result); processedPreviews.set(source,{key,result});
    refreshAdjustment();
  }
}
async function previewSource(force = false) {
  if (!state.source || !state.data || !state.projectId || state.mode !== 'source') return;
  const epoch = ++state.previewEpoch, source = state.source, key = previewKey(source);
  if (force) previewCache.delete(key);
  $('#status-message').textContent = state.sourceView === 'original' ? '正在预览切割…' : '正在更新调整预览…';
  try {
    let result=previewCache.get(key);
    if (!result) {
      let request=previewRequest;
      if (!request || request.key !== key || force) {
        request?.controller.abort();
        const controller=new AbortController(), previous=state.sourceView === 'processed' ? processedPreviews.get(source)?.result : null;
        request={key,controller,previous,promise:api('preview',{data:clone(state.data),source,
          stage:state.sourceView === 'original' ? 'extract' : 'process',known:force ? {} : previewKnown(previous)},false,controller.signal)};
        previewRequest=request;
      }
      result=mergePreviewFrames(request.previous,await request.promise);
      rememberPreview(key,result);
      if (previewRequest === request) previewRequest=null;
    }
    if (epoch !== state.previewEpoch || source !== state.source) return;
    showPreview(result,source,key);
    await prepareActionPreviews(epoch);
  } catch (error) {
    if (error.name === 'AbortError' || epoch !== state.previewEpoch) return;
    state.previewError=error.message;
    if (state.sourceView === 'processed') { player.pause(); $('#play').disabled=true; $('#play').textContent='▶'; }
    if (state.mode === 'source') { renderInspector(); updateSaveStatus(); }
    $('#status-message').textContent='预览失败：'+error.message;
    if (previewRequest?.key === key) previewRequest=null;
  }
}

function reviewInspector() { return composition.inspector(); }
function bindReviewInspector() { composition.bindInspector(); }

// Drag only the selected preview image; stored PNGs and alignment overlays stay put.
function canDragFrame() {
  if (state.mode !== 'source' || state.sourceView !== 'processed' || state.busy || !state.preview || state.previewSource !== state.source) return false;
  const step = player.steps[player.index], process = resolvedSource().process;
  return sourceForFrame(state.sources,step?.ref)?.file === state.source && !!step?.bbox && (process.overrides?.[step.id]?.mode || process.mode || 'anchor') !== 'copy';
}
function releaseFramePointer(id) {
  const stage = $('#stage');
  if (stage.hasPointerCapture(id)) stage.releasePointerCapture(id);
  stage.classList.remove('frame-dragging');
}
function cancelFrameDrag(render = true) {
  if (!frameDrag) return;
  const drag = frameDrag; frameDrag = null;
  if (drag.previous) state.previewOffsets[drag.id] = drag.previous;
  else delete state.previewOffsets[drag.id];
  player.steps.forEach(step=>{ if (step.ref === drag.ref) step.previewOffset=drag.previous; });
  releaseFramePointer(drag.pointerId);
  if (render) { renderInspector(); player.draw(); }
  if (state.previewKey !== previewKey(state.source)) schedulePreview();
}
function moveFrameDrag(event) {
  if (!frameDrag || event.pointerId !== frameDrag.pointerId) return;
  const drag = frameDrag;
  drag.delta = [Math.round((event.clientX - drag.start[0]) * drag.ratio[0]),Math.round((event.clientY - drag.start[1]) * drag.ratio[1])];
  const translation = drag.delta.map((value,i) => value + (drag.previous?.[i] || 0));
  state.previewOffsets[drag.id] = translation;
  player.steps.forEach(step=>{ if (step.ref === drag.ref) step.previewOffset=translation; });
  ['x','y'].forEach((axis,i) => { $('#override-' + axis).value = drag.offset[i] + drag.delta[i]; });
  player.draw();
}
$('#stage').addEventListener('pointerdown', event => {
  if (frameDrag || event.button !== 0 || !canDragFrame()) return;
  const step = player.steps[player.index], stage = $('#stage'), rect = stage.getBoundingClientRect();
  // The stage's symmetric CSS border is outside the image coordinate system.
  const ratio = [player.size[0] / (rect.width - 2 * stage.clientLeft),player.size[1] / (rect.height - 2 * stage.clientTop)];
  const point = [(event.clientX - rect.left - stage.clientLeft) * ratio[0],(event.clientY - rect.top - stage.clientTop) * ratio[1]];
  const previous = state.previewOffsets[step.id], [dx,dy] = previous || [0,0], [left,top,right,bottom] = step.bbox;
  if (point[0] < left + dx || point[0] > right + dx || point[1] < top + dy || point[1] > bottom + dy) return;
  event.preventDefault(); player.pause(); state.selected = player.index;
  renderInspector(); renderTimeline(); onStep(player.index);
  // Invalidate any preview in flight before using this image as the drag baseline.
  clearTimeout(previewTimer); state.previewEpoch++; previewRequest?.controller.abort(); previewRequest = null;
  const process = resolvedSource().process;
  frameDrag = {pointerId:event.pointerId,id:step.id,ref:step.ref,index:player.index,previous,
    offset:[...(process.overrides?.[step.id]?.offset || process.offset || [0,0])],
    start:[event.clientX,event.clientY],ratio,delta:[0,0]};
  $('#stage').setPointerCapture(event.pointerId); $('#stage').classList.add('frame-dragging');
});
$('#stage').addEventListener('pointermove', moveFrameDrag);
$('#stage').addEventListener('pointerup', event => {
  if (!frameDrag || event.pointerId !== frameDrag.pointerId) return;
  moveFrameDrag(event);
  const drag = frameDrag; frameDrag = null;
  releaseFramePointer(drag.pointerId);
  if (!drag.delta.some(value => value !== 0)) {
    if (drag.previous) state.previewOffsets[drag.id] = drag.previous;
    else delete state.previewOffsets[drag.id];
    player.steps.forEach(step=>{ if (step.ref === drag.ref) step.previewOffset=drag.previous; });
    renderInspector(); player.draw();
    if (state.previewKey !== previewKey(state.source)) schedulePreview();
    return;
  }
  change(() => {
    const process = resolvedSource().process, rules = sourceRules(); rules.process ||= {};
    const overrides = clone(process.overrides || {}); overrides[drag.id] ||= {};
    overrides[drag.id].offset = drag.offset.map((value,i) => value + drag.delta[i]);
    rules.process.overrides = overrides;
  },{render:false,preview:true});
  schedulePreview();
});
for (const type of ['pointercancel','lostpointercapture']) $('#stage').addEventListener(type,event => {
  if (event.pointerId === frameDrag?.pointerId) cancelFrameDrag();
});

// Region gestures stay in source pixels and commit one undo step on release.
function sourcePoint(event) {
  const stage=$('#stage'), rect=stage.getBoundingClientRect();
  const ratio=[player.size[0]/(rect.width-2*stage.clientLeft),player.size[1]/(rect.height-2*stage.clientTop)];
  return {point:[Math.max(0,Math.min(player.size[0],Math.round((event.clientX-rect.left-stage.clientLeft)*ratio[0]))),
    Math.max(0,Math.min(player.size[1],Math.round((event.clientY-rect.top-stage.clientTop)*ratio[1])))],ratio};
}
function cancelRegionDrag(redraw = true) {
  if (!regionDrag) return;
  const drag=regionDrag; regionDrag=null;
  const stage=$('#stage');
  if (stage.hasPointerCapture(drag.pointerId)) stage.releasePointerCapture(drag.pointerId);
  if (player.sourceView) { player.sourceView.boxes=drag.regions.map(frame=>[...frame.box]); delete player.sourceView.draftBox; }
  if (redraw && state.data) { renderInspector(); player.draw(); }
  if (state.data && state.mode === 'source' && state.previewKey !== previewKey(state.source)) schedulePreview();
}
function removeRegion() {
  const regions=regionFrames(), frame=regions[state.selected]; if (!frame) return;
  if (regions.length<=1) { toast('至少保留一个区域；也可删除整张原图',true); return; }
  const used=resourceUsers(state.data,{kind:'sprite',ref:frame.ref}).map(item=>item.ref);
  if (used.length) { toast('此区域被资源引用：' + used.join('、') + '。请先移除或替换引用。',true); return; }
  if (resolvedSource().process.overrides?.[frame.id]) { toast('此区域仍有单帧调整，请先在调整页重置',true); return; }
  const nextId=sliceNextId();
  change(()=>{ regions.splice(state.selected,1); setManualRegions(regions,nextId); state.selected=Math.min(state.selected,regions.length-1); },{preview:true});
}
function moveRegionDrag(event) {
  const drag=regionDrag; if (!drag || event.pointerId!==drag.pointerId) return;
  const {point}=sourcePoint(event), [x,y]=drag.start;
  drag.box=drag.handle === 'create' ? [Math.min(x,point[0]),Math.min(y,point[1]),Math.max(x,point[0]),Math.max(y,point[1])]
    : resizeRegion(drag.regions[drag.index].box,drag.handle,[point[0]-x,point[1]-y],player.size);
  if (drag.handle==='create') player.sourceView.draftBox=drag.box;
  else {
    player.sourceView.boxes=drag.regions.map((frame,i)=>i===drag.index ? drag.box : frame.box);
    const values={x:drag.box[0],y:drag.box[1],width:drag.box[2]-drag.box[0],height:drag.box[3]-drag.box[1]};
    for (const [key,value] of Object.entries(values)) { const input=$('#slice-'+key); if (input) input.value=value; }
  }
  player.draw();
}
$('#stage').addEventListener('pointerdown', event=>{
  if (event.button!==0 || state.mode!=='source' || state.sourceView!=='original' || state.busy || !player.sourceView) return;
  const regions=regionFrames(), {point,ratio}=sourcePoint(event);
  if (!regions.length && resolvedSource().extract.method !== 'boxes') { toast('请等待切割预览，或先选择手动区域',true); return; }
  const hit=sliceTool==='create' ? {index:regions.length,handle:'create'} : hitRegion(regions.map(frame=>frame.box),state.selected,point,6*Math.max(...ratio));
  if (!hit) return;
  event.preventDefault(); player.pause(); $('#stage').focus();
  clearTimeout(previewTimer); state.previewEpoch++; previewRequest?.controller.abort(); previewRequest=null;
  if (hit.handle!=='create') { state.selected=hit.index; player.sourceView.selected=hit.index; renderInspector(); renderTimeline(); }
  regionDrag={pointerId:event.pointerId,start:point,regions,index:hit.index,handle:hit.handle,box:null};
  $('#stage').setPointerCapture(event.pointerId); player.draw();
});
$('#stage').addEventListener('pointermove',event=>{
  if (regionDrag) { moveRegionDrag(event); return; }
  if (state.mode!=='source' || state.sourceView!=='original' || !player.sourceView) return;
  const {point,ratio}=sourcePoint(event), hit=hitRegion(regionFrames().map(frame=>frame.box),state.selected,point,6*Math.max(...ratio));
  $('#stage').style.cursor=sliceTool==='create' ? 'crosshair' : hit ? hit.handle==='move' ? 'move' : hit.handle+'-resize' : 'default';
});
$('#stage').addEventListener('pointerup',event=>{
  if (!regionDrag || event.pointerId!==regionDrag.pointerId) return;
  moveRegionDrag(event);
  const drag=regionDrag; regionDrag=null;
  if ($('#stage').hasPointerCapture(event.pointerId)) $('#stage').releasePointerCapture(event.pointerId);
  delete player.sourceView.draftBox;
  const regions=drag.regions;
  if (drag.handle==='create') {
    if (drag.box[2]-drag.box[0]<3 || drag.box[3]-drag.box[1]<3) { player.draw(); if (state.previewKey !== previewKey(state.source)) schedulePreview(); return; }
    const next=sliceNextId(); regions.push({id:String(next).padStart(3,'0'),box:drag.box});
    change(()=>{ setManualRegions(regions,next+1); state.selected=regions.length-1; },{preview:true});
  } else if (JSON.stringify(drag.box)!==JSON.stringify(regions[drag.index].box)) {
    regions[drag.index].box=drag.box;
    change(()=>setManualRegions(regions),{preview:true});
  } else { renderInspector(); player.draw(); if (state.previewKey !== previewKey(state.source)) schedulePreview(); }
});
for (const type of ['pointercancel','lostpointercapture']) $('#stage').addEventListener(type,event=>{
  if (regionDrag?.pointerId===event.pointerId) cancelRegionDrag();
});
$('#slice-select').onclick=()=>{ cancelRegionDrag(); sliceTool='select'; renderAll(); };
$('#slice-create').onclick=()=>{ cancelRegionDrag(); sliceTool='create'; renderAll(); };
$('#adjust-action').onchange=()=>{
  player.pause(); state.adjustAction=$('#adjust-action').value; state.selected=0;
  const first = state.adjustAction ? actionSteps(state.data,state.adjustAction,'runtime')[0] : null;
  const owner=sourceForFrame(state.sources,first?.ref);
  if (owner && owner.file !== state.source) { state.source=owner.file; state.preview=null; state.previewKey=null; state.previewOffsets={}; }
  if (state.adjustAction) $('#loop-preview').checked=!!merge(state.data.defaults,state.data.actions[state.adjustAction]).loop;
  state.previewEpoch++; renderAll(); schedulePreview();
};
document.querySelectorAll('button[data-mode]').forEach(button => { button.onclick = () => mode(button.dataset.mode,button.dataset.view); });
$('#action-edit').onclick = () => mode('action');
$('#action-review').onclick = () => mode('review');
$('#asset-kind').onchange = () => { $('#asset-source').value=''; renderLibrary(); };
$('#asset-search').oninput = renderLibrary; $('#asset-source').onchange = renderLibrary;
$('#asset-multiselect').onchange = () => { state.libraryMulti = $('#asset-multiselect').checked; if (!state.libraryMulti) state.assetSelection.clear(); renderLibrary(); };
$('#assets-select-visible').onclick = () => { state.libraryMulti = true; visibleAssets().forEach(a => state.assetSelection.add(resourceKey(a.resource))); renderLibrary(); };
$('#assets-clear').onclick = () => { state.assetSelection.clear(); state.lastAsset = null; renderLibrary(); };
$('#assets-add').onclick = () => composition.insert(composition.selection().map(item=>item.resource));
function deleteSequence(kind) {
  if (state.busy || !state.data || !['action','review'].includes(kind)) return;
  const ref=state[kind], collection=kind === 'action' ? state.data.actions : reviews();
  if (!ref || !collection[ref]) return;
  const target={kind:kind === 'action' ? 'action' : 'sequence',ref};
  const users=resourceUsers(state.data,target);
  if (users.length) { toast(`此资源仍被 ${users.map(item=>ownCompositionSpec(item)?.name || item.ref).join('、')} 引用，请先移除相应槽位`,true); return; }
  if (!confirm(`删除 ${collection[ref].name || ref}？素材图片会保留，可撤销；保存工程后生效。`)) return;
  player.pause();
  change(()=>{ delete collection[ref]; state[kind]=Object.keys(collection)[0]; state.slot=0; state.clip=0; state.selected=0; });
}
async function deleteMaterials(kind, references) {
  if (state.busy || !references.length) return;
  const message = kind === 'source' ? `删除原图 ${references.join('、')}？将同时删除对应切片和 processed，并保存当前工程。`
    : kind === 'reference' ? `删除 ${references.length} 张参考图并保存当前工程？`
    : `删除选中的 ${references.length} 张素材并保存当前工程？仍被动作使用的素材会阻止删除。自动生成帧在重新应用原图后可能恢复。`;
  if (!confirm(message)) return;
  await task('正在删除素材…',async () => {
    const snapshot = await api('delete',payload({kind,references})); player.pause(); setSnapshot(snapshot);
    toast(`已删除 ${snapshot.deleted} 项，工程已保存`);
  });
}
$('#assets-delete').onclick = () => composition.deleteSelected();
$('#delete-item').onclick = () => {
  if (['action','review'].includes(state.mode)) return deleteSequence(state.mode);
  return state.mode === 'source' ? deleteMaterials('source',state.source ? [state.source] : []) : deleteMaterials('reference',state.reference ? [state.reference] : []);
};
$('#new-item').onclick = () => {
  if (state.mode === 'source') { $('#source-upload').click(); return; }
  if (state.mode === 'reference') { $('#reference-upload').click(); return; }
  if (state.mode === 'action') {
    const name = prompt('新动作 ID（字母、数字、下划线、短横线）',uid('action'));
    if (!name) return;
    if (!/^[A-Za-z0-9_-]+$/.test(name) || state.data.actions[name]) { toast('动作 ID 无效或已存在',true); return; }
    change(() => { state.data.actions[name] = {fps:12,loop:false,slots:[]}; state.action = name; state.slot=0; state.selected = 0; state.playbackMode = 'runtime'; });
  } else {
    const name = prompt('Review 名称','新的衔接检查'); if (!name) return;
    change(() => { state.data.workbench ||= {}; state.data.workbench.reviews ||= {}; const id = uid('review'); reviews()[id] = {name,loop:true,mode:'runtime',slots:[]}; state.review = id; state.clip = 0; });
  }
};
$('#save').onclick = save;
$('#settings-open').onclick = () => {
  if (!state.data) return;
  $('#settings-name').value = state.data.project?.name || state.data.character;
  $('#settings-width').value = state.data.frame_size[0];
  $('#settings-height').value = state.data.frame_size[1];
  $('#settings-anchor-x').value = state.data.anchor.x;
  $('#settings-anchor-y').value = state.data.anchor.y;
  $('#settings-error').hidden = true;
  const manual = state.assets.filter(asset => /^(imports|_approved)\//.test(asset.ref)).length;
  $('#settings-impact').textContent = `改变画布或锚点后，${state.sources.length} 张原图的处理结果需要逐张重新应用。${manual ? `${manual} 张手工素材不会自动改动，画布尺寸变化时需重新制作或导入。` : ''}保存工程只保存参数，不会改写现有图片。`;
  $('#settings-dialog').showModal();
};
$('#settings-close').onclick = () => $('#settings-dialog').close();
$('#settings-form').onsubmit = event => {
  event.preventDefault();
  const name = $('#settings-name').value.trim();
  const width = Number($('#settings-width').value), height = Number($('#settings-height').value);
  const x = Number($('#settings-anchor-x').value), y = Number($('#settings-anchor-y').value);
  if (!name || name.length > 120 || !Number.isInteger(width) || !Number.isInteger(height) ||
      width < 1 || height < 1 || width > 4096 || height > 4096 ||
      !Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) {
    $('#settings-error').textContent = '请检查名称、1–4096 的画布尺寸和 0–1 的锚点。';
    $('#settings-error').hidden = false; return;
  }
  const canvasChanged = width !== state.data.frame_size[0] || height !== state.data.frame_size[1];
  if (canvasChanged && state.assets.length && !confirm('改变画布后，现有图片不会自动缩放。原图需重新应用，手工素材需按新画布重新制作或导入；继续加入草稿？')) return;
  change(() => {
    state.data.project ||= {}; state.data.project.name = name;
    state.data.frame_size = [width,height];
    state.data.anchor = {...state.data.anchor,x,y,pixels:[roundMs(width * x),roundMs(height * y)]};
  },{preview:true});
  $('#settings-dialog').close();
  toast('工程设置已加入草稿；保存工程只保存参数，不会改写图片');
};
$('#history-open').onclick = async () => {
  const dialog = $('#history-dialog');
  $('#history-list').textContent = '正在读取版本记录…';
  dialog.showModal();
  try {
    const {versions} = await api('history');
    $('#history-list').innerHTML = versions.map(version => `<div class="history-row" role="listitem"><div><strong>${escape(version.operation)}</strong><small>${escape(new Date(version.created_at * 1000).toLocaleString('zh-CN'))} · ${version.files} 个文件</small></div><button data-version="${escape(version.id)}">恢复此版本</button></div>`).join('') || '<p class="hint">还没有已完成的图片操作。</p>';
    $('#history-list').querySelectorAll('[data-version]').forEach(button => {
      button.onclick = async () => {
        if (dirty() && !confirm('恢复会放弃当前未保存的草稿。继续？')) return;
        if (!confirm('恢复该操作之前的图片与配置？此操作本身也会留下可恢复版本。')) return;
        dialog.close();
        await task('正在恢复版本…',async () => {
          const snapshot = await api('restore',payload({version:button.dataset.version}));
          player.pause(); setSnapshot(snapshot); toast('版本已恢复，工程已保存');
        });
      };
    });
  } catch (error) { $('#history-list').textContent = error.message; }
};
$('#history-close').onclick = () => $('#history-dialog').close();
$('#reload').onclick = () => {
  if (dirty() && !confirm('重新载入会放弃当前未保存的草稿。继续？')) return;
  task('正在重新载入…',loadProject);
};
function restoreHistory(redo) {
  cancelRegionDrag(); cancelFrameDrag(false);
  const source = redo ? state.future : state.history, target = redo ? state.history : state.future;
  if (!source.length || state.busy) return;
  target.push(clone(state.data)); state.data = source.pop(); state.previewEpoch++; state.preview = null;
  player.pause(); renderAll(); if (state.mode === 'source') schedulePreview();
}
$('#undo').onclick = () => restoreHistory(false); $('#redo').onclick = () => restoreHistory(true);
let prepareJobId = null;
$('#job-cancel').onclick = async () => {
  if (!prepareJobId) return;
  $('#job-cancel').disabled = true;
  $('#job-status').textContent = '正在取消，当前原图处理结束后停止…';
  try { await api(`jobs/${prepareJobId}/cancel`,{}); }
  catch (error) { $('#job-cancel').disabled = false; toast(error.message,true); }
};
$('#prepare').onclick = () => task('正在准备缺失素材…',async () => {
  $('#job-banner').hidden = false; $('#job-cancel').disabled = true;
  $('#job-status').textContent = '正在启动素材准备…';
  $('#job-progress').value = 0;
  try {
    const job = await api('jobs/prepare',payload());
    prepareJobId = job.id; $('#job-cancel').disabled = false;
    let status;
    do {
      status = await api(`jobs/${job.id}`);
      if (!$('#job-cancel').disabled || ['done','failed','cancelled'].includes(status.status))
        $('#job-status').textContent = `${status.phase} · ${status.completed}/${status.total || '?'} 张`;
      $('#job-progress').max = Math.max(1,status.total);
      $('#job-progress').value = status.completed;
      if (['done','failed','cancelled'].includes(status.status)) break;
      await new Promise(resolve => setTimeout(resolve,400));
    } while (true);
    if (status.status === 'cancelled') { toast('素材准备已取消，工程未改动'); return; }
    if (status.status === 'failed') throw new Error(status.error || '素材准备失败');
    setSnapshot(status.result); toast('缺失素材已准备，已有 processed 图片保持原样');
  } finally {
    prepareJobId = null; $('#job-banner').hidden = true; $('#job-progress').value = 0;
  }
});
$('#migrate').onclick = () => task('正在保留最终帧…',async () => {
  const snapshot = await api('migrate',payload()); setSnapshot(snapshot); toast(`已保留 ${snapshot.imported} 张不同于 processed 的最终帧，并更新动作引用`);
});
$('#import-processed').onclick = () => $('#processed-upload').click();
async function uploadFile(input,kind) {
  const files = Array.from(input.files || []); if (!files.length || state.busy) return;
  await task('正在导入素材…',async () => {
    const imported = [], failures = []; let skipped = 0;
    for (const [index,file] of files.entries()) {
      const message = `正在导入 ${index + 1}/${files.length} · ${file.name}`;
      $('#canvas-loading').textContent = message; $('#activity-state').textContent = message;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error('单张素材请控制在 40 MiB 以内');
        const content = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(reader.error || new Error('图片读取失败')); reader.readAsDataURL(file); });
        const snapshot = await api('upload',payload({kind,filename:file.name,content})); setSnapshot(snapshot); imported.push(file.name);
      } catch (error) {
        failures.push(`${file.name}：${error.message}`);
        if (error.status === 409 || error.status === 403) { skipped = files.length - index - 1; break; }
      }
    }
    if (imported.length && kind === 'source') { state.source = imported[0]; mode('source','original'); }
    if (imported.length && kind === 'reference') { state.reference = 'references/' + imported[0]; mode('reference'); }
    toast(`已导入 ${imported.length}/${files.length} 张${skipped ? `，未处理 ${skipped} 张` : ''}${failures.length ? '\n' + failures.join('\n') : '，工程已保存'}`,failures.length > 0);
  });
  input.value = '';
}
$('#source-upload').onchange = () => uploadFile($('#source-upload'),'source');
$('#processed-upload').onchange = () => uploadFile($('#processed-upload'),'processed');
$('#reference-upload').onchange = () => uploadFile($('#reference-upload'),'reference');
$('#play').onclick = () => { player.toggle(); $('#play').textContent = player.playing ? 'Ⅱ' : '▶'; };
function singleStep(delta) {
  player.pause(); player.seek(player.index + delta);
  if (composition.isEditing()) { state.selected=player.index; composition.selectIndex(player.steps[player.index]?.slot || 0); renderInspector(); renderTimeline(); onStep(player.index); }
  else { if (state.mode === 'source' && state.sourceView === 'processed') selectAdjustmentStep(player.index); else state.selected = player.index; renderInspector(); renderTimeline(); onStep(player.index); }
}
$('#previous').onclick = () => singleStep(-1); $('#next').onclick = () => singleStep(1);
$('#speed').onchange = () => { player.speed = Number($('#speed').value); };
$('#loop-preview').onchange = () => { player.loop = $('#loop-preview').checked; };
['guides','onion','reference'].forEach(id => { $('#' + id).onchange = () => { player.options[id] = $('#' + id).checked; player.draw(); }; });
$('#zoom').onchange = () => { player.options.zoom = $('#zoom').value; player.resize(); };
$('#background').onchange = () => { $('#canvas-area').classList.remove('dark','light'); if ($('#background').value !== 'checker') $('#canvas-area').classList.add($('#background').value); };

function openExport() {
  const list = $('#export-action-list');
  list.innerHTML = Object.entries(state.data.actions).filter(([name]) => actionSteps(state.data,name).length).map(([name]) => `<label><input type="checkbox" value="${escape(name)}" ${name === state.action ? 'checked' : ''}>${escape(name)}</label>`).join('');
  $('#export-format').value = state.mode === 'review' ? 'review' : 'all'; updateExportFormat(); $('#export-dialog').showModal();
}
function updateExportFormat() {
  exportDisplay.render();
  const format = $('#export-format').value;
  $('#export-actions').hidden = ['project','review'].includes(format);
  $('#export-note').textContent = format === 'review' ? '导出当前 Review 的 WebP、GIF 和逐步记录，使用所选片段范围与播放模式。' :
    format === 'project' ? '包含原图、processed、参考资料、说明和工程配置。解压到工作区即可重新打开。' :
    format === 'gif' ? 'GIF 使用展示播放顺序；每帧最多 256 色，透明度为二值，时长按 10 ms 取整。' :
    '图集使用游戏帧顺序；WebP 与 GIF 使用独立的展示播放配置。';
}
$('#export-open').onclick = openExport; $('#export-close').onclick = () => $('#export-dialog').close(); $('#export-format').onchange = updateExportFormat;
let exportJobId = null;
$('#export-dialog').addEventListener('cancel', event => { if (exportJobId) event.preventDefault(); });
$('#export-cancel').onclick = async () => {
  if (!exportJobId) return;
  $('#export-cancel').disabled = true;
  $('#export-progress').textContent = '正在取消，当前步骤结束后停止…';
  try { await api(`jobs/${exportJobId}/cancel`,{}); }
  catch (error) { $('#export-cancel').disabled = false; toast(error.message,true); }
};
$('#export-form').onsubmit = async event => {
  event.preventDefault(); if (exportJobId) return;
  const format = $('#export-format').value;
  if (!$('#export-display-settings').hidden && !exportDisplay.apply()) return;
  const actions = [...$('#export-action-list').querySelectorAll('input:checked')].map(input => input.value);
  if (!['project','review'].includes(format) && !actions.length) { toast('请至少选择一个动作',true); return; }
  if (format === 'review' && !reviewSteps(state.data,currentReview()).length) { toast('请先创建序列并添加资源槽位',true); return; }
  const submit = $('#export-submit'); submit.disabled = true; submit.textContent = '正在生成…';
  $('#export-close').disabled = true; $('#export-format').disabled = true; $('#export-display-settings').disabled=true;
  $('#export-progress-box').hidden = false; $('#export-cancel').disabled = false;
  $('#export-progress').textContent = '正在准备导出…';
  try {
    const job = await api('jobs/export',payload({options:{format,actions,review:currentReview()}}));
    exportJobId = job.id;
    let status;
    do {
      status = await api(`jobs/${job.id}`);
      $('#export-progress').textContent = `${status.phase} · ${status.completed}/${status.total || '?'} 项`;
      $('#export-progress-bar').max = Math.max(1,status.total);
      $('#export-progress-bar').value = status.completed;
      if (['done','failed','cancelled'].includes(status.status)) break;
      await new Promise(resolve => setTimeout(resolve,400));
    } while (true);
    if (status.status === 'cancelled') { toast('导出已取消'); return; }
    if (status.status === 'failed') throw new Error(status.error || '导出失败');
    const response = await api(`jobs/${job.id}/download`,undefined,true);
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'sprites.zip';
    link.click(); setTimeout(() => URL.revokeObjectURL(url),60000); $('#export-dialog').close(); toast('导出完成');
  } catch (error) { toast(error.message,true); }
  finally {
    exportJobId = null; submit.disabled = false; submit.textContent = '生成并下载 ZIP ↗';
    $('#export-close').disabled = false; $('#export-format').disabled = false; $('#export-display-settings').disabled=false;
    $('#export-progress-box').hidden = true; $('#export-progress-bar').value = 0;
  }
};

document.addEventListener('keydown', event => {
  if (!state.data || state.busy || event.defaultPrevented || $('#project-dialog').open) return;
  if (regionDrag) {
    if (event.key === 'Escape') { event.preventDefault(); cancelRegionDrag(); }
    return;
  }
  if (frameDrag) {
    if (event.key === 'Escape') { event.preventDefault(); cancelFrameDrag(); }
    return;
  }
  const editable = ['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement?.tagName);
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!$('#export-dialog').open) save(); return; }
  if (editable || $('#export-dialog').open) return;
  if (state.mode === 'source' && state.sourceView === 'original' && !event.ctrlKey && !event.metaKey) {
    if (event.key === 'Delete') { event.preventDefault(); removeRegion(); return; }
    const direction = {ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
    if (direction) {
      event.preventDefault(); const regions = regionFrames(), frame = regions[state.selected]; if (!frame) return;
      const delta = direction.map(v=>v*(event.shiftKey ? 10 : 1));
      change(()=>{ frame.box = resizeRegion(frame.box,'move',delta,sourceInfo().size); setManualRegions(regions); },{preview:true}); return;
    }
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); restoreHistory(event.shiftKey); }
  else if (event.code === 'Space') { event.preventDefault(); if (!$('#play').disabled) $('#play').click(); }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); singleStep(-1); }
  else if (event.key === 'ArrowRight') { event.preventDefault(); singleStep(1); }
  else if (event.key === 'Delete' && composition.isEditing()) removeFrame();
});
window.addEventListener('beforeunload',event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
async function start() {
  $('#project-name').textContent = '工程列表';
  const listing = await listProjects();
  const requested = new URLSearchParams(location.search).get('project') || listing.initial_project;
  if (requested) await openProject(requested);
}
start().catch(error => { toast(error.message,true); $('#project-list').textContent = '工程列表载入失败，请刷新重试。'; });
