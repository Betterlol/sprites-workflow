// Exercise the actual app module with a minimal DOM and an in-memory HTTP API.
// Browser installation is unnecessary; pixel rendering is tested by Python.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const html = await readFile(new URL('../tools/sprite_pipeline/web/index.html',import.meta.url),'utf8');
const modelSource = await readFile(new URL('../tools/sprite_pipeline/web/model.js',import.meta.url),'utf8');
const model = await import('data:text/javascript;base64,' + Buffer.from(modelSource).toString('base64'));
const mergeSource = await readFile(new URL('../tools/sprite_pipeline/web/merge.js',import.meta.url),'utf8');
const mergeModel = await import('data:text/javascript;base64,' + Buffer.from(mergeSource).toString('base64'));
const elements = new Map();
class Classes {
  constructor(values = []) { this.values = new Set(values); }
  add(...values) { values.forEach(v => this.values.add(v)); }
  remove(...values) { values.forEach(v => this.values.delete(v)); }
  contains(value) { return this.values.has(value); }
  toggle(value, enabled) { enabled ??= !this.contains(value); enabled ? this.add(value) : this.remove(value); }
}
class Element {
  constructor(value = '') { this.value = value; this.defaultValue = value; this.classList = new Classes(); this.dataset = {}; this.hidden = false; this.textContent = ''; this.tagName = 'DIV'; this.checked = true; this.open = false; this.attributes = new Map(); this.styles = new Map(); this.style = {setProperty:(key,val) => this.styles.set(key,val),getPropertyValue:key => this.styles.get(key)}; }
  set innerHTML(value) { this.html = value; this.mergeChoices = null; this.itemButtons = null; register(value); }
  get innerHTML() { return this.html || ''; }
  querySelectorAll(selector) {
    if (selector === '[data-project]') return [...this.innerHTML.matchAll(/data-project="([^"]+)"/g)].map(([,id]) => {
      const button = new Element(); button.dataset.project = id; return this.projectButtons?.find(b => b.dataset.project === id) || button;
    });
    if (selector === '[data-item]') return this.itemButtons ||= [...this.innerHTML.matchAll(/data-item="([^"]+)"/g)].map(([,id]) => {
      const button = new Element(); button.dataset.item = id; return button;
    });
    if (selector === '[data-version]') {
      this.historyButtons ||= [...this.innerHTML.matchAll(/data-version="([^"]+)"/g)].map(([,id]) => {
        const button = new Element(); button.dataset.version = id; return button;
      });
      return this.historyButtons;
    }
    if (selector === '[data-merge-choice]') {
      this.mergeChoices ||= [...this.innerHTML.matchAll(/data-merge-choice="([^"]+)"/g)].map(([,key]) => {
        const select = new Element('local'); select.dataset.mergeChoice = key; return select;
      });
      return this.mergeChoices;
    }
    if (selector === 'input:checked') return [...this.innerHTML.matchAll(/<input[^>]*value="([^"]+)"[^>]*checked/g)].map(([,value]) => new Element(value));
    return [];
  }
  setAttribute(name,value) { this.attributes.set(name,String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type,handler) { this.listeners ||= new Map(); (this.listeners.get(type) || this.listeners.set(type,[]).get(type)).push(handler); }
  dispatch(type,event) { for (const handler of this.listeners?.get(type) || []) handler(event); }
  getBoundingClientRect() { return {left:100,top:50,width:66,height:66}; }
  setPointerCapture(id) { this.pointerId = id; }
  hasPointerCapture(id) { return this.pointerId === id; }
  releasePointerCapture() { this.pointerId = null; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() { document.activeElement = this; }
  reset() { for (const [id, element] of elements) if (id.startsWith('new-project-')) element.value = element.defaultValue; }
  click() { this.onclick?.(); }
}
function register(markup) {
  for (const [,tag,id,attributes] of markup.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"([^>]*)>/g)) {
    const element = new Element(attributes.match(/\bvalue="([^"]*)"/)?.[1] || ''); element.tagName = tag.toUpperCase(); elements.set(id,element);
  }
}
register(html);
const descendants = new Map();
const documentListeners = new Map(), windowListeners = new Map();
const tabs = [...html.matchAll(/<button[^>]*data-mode="([^"]+)"([^>]*)>/g)].map(([,mode,attrs]) => {
  const tab = new Element(); tab.dataset.mode = mode;
  const view = attrs.match(/data-view="([^"]+)"/); if (view) tab.dataset.view = view[1];
  return tab;
});
const paneButtons = ['materials','canvas','properties'].map(pane => { const button = elements.get('pane-' + pane); button.dataset.pane = pane; return button; });
const body = new Element(); body.classList.add('project-home');
const document = {
  body, hidden:false, activeElement:{tagName:'BODY'}, addEventListener(type,handler) { (documentListeners.get(type) || documentListeners.set(type,[]).get(type)).push(handler); }, createElement:() => new Element(),
  querySelector(selector) {
    if (selector.startsWith('#') && !selector.includes(' ')) return elements.get(selector.slice(1)) || null;
    if (!descendants.has(selector)) descendants.set(selector,new Element()); return descendants.get(selector);
  },
  querySelectorAll:selector => ['[data-mode]','button[data-mode]'].includes(selector) ? tabs : selector === '[data-pane]' ? paneButtons : [],
};
class Player {
  constructor(canvas,area,onStep) { this.onStep = onStep; this.steps = []; this.index = 0; this.options = {}; this.images = new Map(); }
  pause() { this.playing = false; }
  toggle() { this.playing = !this.playing; return this.playing; }
  reset() { this.pause(); this.steps = []; this.index = 0; this.images.clear(); }
  resize() {}
  draw() {}
  setProject(data) { this.size = data.frame_size; this.anchor = data.anchor.pixels; }
  setSteps(steps,index = 0) { this.steps = steps; this.index = index; this.onStep(index); }
  seek(index) { this.index = index; this.onStep(index); }
}
const snapshot = id => ({data:{version:2,project:{name:id},character:id,frame_size:[32,32],anchor:{x:0.5,y:0.90625,pixels:[16,29]},defaults:{},sources:{},actions:{},workbench:{reviews:{}}},
  revision:'r-' + id,asset_revision:'a-' + id,sources:[],assets:[],references:[],legacy_count:0,project:{id,name:id,directory:'/workspaces/' + id},warnings:[]});
const projects = new Map([['alpha',snapshot('alpha')],['beta',snapshot('beta')]]);
const requests = [];
const intervals = [];
const previewRequests = [];
const stored = new Map();
const observedResizes = new Map();
let releaseSlowPreview = null;
let releaseHeldUpload = null;
let allowDiscard = true;
const confirmationMessages = [];
let pausedProject = null, resumeSnapshot = null;
let holdDragPreview = false, releaseDragPreview;
let holdExtractPreview = false, releaseExtractPreview;
const context = {
  ...model, ...mergeModel, Player, document, structuredClone, URL, URLSearchParams, Blob, AbortController,
  ResizeObserver:class { constructor(callback) { this.callback = callback; } observe(element) { observedResizes.set(element,this.callback); } },
  FileReader:class { readAsDataURL() { this.result = 'data:image/png;base64,cGl4ZWxz'; queueMicrotask(() => this.onload()); } },
  location:{pathname:'/',search:''}, history:{replaceState() {}},
  window:{innerWidth:1440,innerHeight:900,addEventListener(type,handler) { (windowListeners.get(type) || windowListeners.set(type,[]).get(type)).push(handler); }}, localStorage:{getItem:key => stored.get(key) ?? null,setItem:(key,value) => stored.set(key,String(value))},
  setTimeout:() => 1, clearTimeout() {}, setInterval:(_,delay) => intervals.push(delay),
  confirm:message => { confirmationMessages.push(message); return allowDiscard; }, console,
  fetch:async (url, options = {}) => {
    requests.push({url,options});
    let result;
    if (url.endsWith('/jobs/job-1/download')) return {ok:true,blob:async () => new Blob(['zip']),headers:{get:() => 'attachment; filename="test.zip"'}};
    if (url === '/api/projects') {
      if (options.method === 'POST') { const body = JSON.parse(options.body); const id = body.id || body.name; projects.set(id,snapshot(id)); result = {id}; }
      else result = {token:'session',workspace_root:'/workspaces',projects:[...projects.keys()].map(id => ({id,name:id,character:id,frame_size:[32,32]}))};
    } else if (url.endsWith('/jobs/export')) result = {id:'job-1',status:'queued',completed:0,total:1,phase:'等待开始'};
    else if (url.endsWith('/jobs/job-1')) result = {id:'job-1',status:'done',completed:1,total:1,phase:'已完成'};
    else if (url.endsWith('/jobs/prepare')) result = {id:'prep-1',status:'queued',completed:0,total:1,phase:'等待开始'};
    else if (url.endsWith('/jobs/prep-1')) result = {id:'prep-1',status:'done',completed:1,total:1,phase:'已完成',result:projects.get(url.match(/projects\/([^/]+)/)[1])};
    else {
      const [,id,operation] = url.match(/^\/api\/projects\/([^/]+)(?:\/(\w+))?$/) || [];
      const project = projects.get(decodeURIComponent(id)); assert(project,`Unknown request ${url}`);
      if (operation === 'save') { const payload = JSON.parse(options.body); if (payload.revision !== project.revision) return {ok:false,status:409,json:async () => ({error:'external change'})}; project.data = structuredClone(payload.data); project.revision += '-saved'; result = {revision:project.revision}; }
      else if (operation === 'upload') {
        const payload = JSON.parse(options.body);
        if (payload.filename === 'hold.png') await new Promise(resolve => { releaseHeldUpload = resolve; });
        assert.equal(payload.revision,project.revision,'Batch imports must use the latest config revision');
        assert.equal(payload.asset_revision,project.asset_revision,'Batch imports must use the latest material revision');
        if (payload.filename === 'bad.png') return {ok:false,status:400,json:async () => ({error:'invalid test image'})};
        if (payload.filename === 'conflict.png') return {ok:false,status:409,json:async () => ({error:'external change'})};
        project.data = structuredClone(payload.data);
        if (payload.kind === 'processed') project.assets.push({ref:'imports/' + payload.filename,url:'/pixels/' + payload.filename,size:[32,32]});
        else if (payload.kind === 'reference') project.references.push({ref:'references/' + payload.filename,file:payload.filename,url:'/refs/' + payload.filename,size:[64,48]});
        else { project.sources.push({file:payload.filename,url:'/sources/' + payload.filename,size:[16,16],count:0}); project.data.sources[payload.filename] = {}; }
        project.revision += '-import'; project.asset_revision += '-import'; result = project;
      }
      else if (operation === 'delete') {
        const payload = JSON.parse(options.body);
        if (payload.kind === 'processed' && Object.values(payload.data.actions).some(action => (action.sprites || []).some(ref => payload.references.includes(ref)))) return {ok:false,status:400,json:async () => ({error:'idle still uses these sprites'})};
        project.data = structuredClone(payload.data);
        if (payload.kind === 'processed') project.assets = project.assets.filter(a => !payload.references.includes(a.ref));
        else if (payload.kind === 'reference') project.references = project.references.filter(a => !payload.references.includes(a.ref));
        project.revision += '-delete'; project.asset_revision += '-delete'; result = {...project,deleted:payload.references.length};
      }
      else if (operation === 'changes') result = {revision:project.revision,asset_revision:project.asset_revision};
      else if (operation === 'history') result = {versions:[{id:'version-one',operation:'apply',created_at:1,files:2}]};
      else if (operation === 'restore') {
        project.revision += '-restored'; project.asset_revision += '-restored'; result = project;
      }
      else if (operation === 'preview') {
        const body = JSON.parse(options.body);
        previewRequests.push(body.source);
        if (holdExtractPreview && body.stage === 'extract') await new Promise(resolve => { releaseExtractPreview = resolve; });
        if (body.source === 'slow.png') await new Promise(resolve => { releaseSlowPreview = resolve; });
        if (body.source === 'drag.png' && holdDragPreview) await new Promise(resolve => { releaseDragPreview = resolve; });
        result = {stage:body.stage || 'process',scale:1,frames:[{id:'000',ref:body.source.replace('.png','/000.png'),box:[0,0,8,8],url:'/preview/' + body.source,bbox:[0,0,8,8]}]};
        if (body.source === 'drag.png') result.frames = ['000','001'].map(id => ({id,ref:`drag/${id}.png`,box:[0,0,8,8],url:`/preview/drag-${id}`,bbox:[4,5,14,17]}));
      }
      else if (operation === 'apply') {
        const payload = JSON.parse(options.body);
        assert.equal(payload.revision,project.revision);
        assert.equal(payload.asset_revision,project.asset_revision);
        project.data = structuredClone(payload.data); project.revision += '-applied'; project.asset_revision += '-applied'; result = project;
      }
      else {
        assert(!operation,`Unexpected operation ${operation}`);
        if (pausedProject === id) await new Promise(resolve => { resumeSnapshot = resolve; });
        result = project;
      }
    }
    return {ok:true,json:async () => structuredClone(result)};
  },
};
let source = await readFile(new URL('../tools/sprite_pipeline/web/app.js',import.meta.url),'utf8');
let layoutSource;
try { layoutSource = await readFile(new URL('../tools/sprite_pipeline/web/layout.js',import.meta.url),'utf8'); } catch {}
if (layoutSource) Object.assign(context,await import('data:text/javascript;base64,' + Buffer.from(layoutSource).toString('base64')));
source = source.replace(/^import [^\r\n]*\r?\n/gm,'');
source += '\nglobalThis.hooks = {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player,mode,uploadFile,selectAsset,deleteMaterials,activeSteps,previewSource,restoreHistory,renderAll};';
vm.runInNewContext(source,context,{filename:'app.js'});
const flush = () => new Promise(resolve => setImmediate(resolve));
await flush();
const {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player,renderAll} = context.hooks;
assert(intervals.includes(12000),'Background checks should use a longer idle interval');
assert(body.classList.contains('project-home'));
assert.match(elements.get('project-list').innerHTML,/alpha/);
await openProject('alpha');
assert.equal(state.projectId,'alpha'); assert(!body.classList.contains('project-home'));
assert.equal(elements.get('project-name').textContent,'alpha',elements.get('toast').textContent);
assert(elements.get('draft-state'),'The workbench needs a visible draft state');
assert.match(elements.get('draft-state').textContent,/已保存/);
assert(elements.get('left-splitter'),'Materials and canvas need an adjustable separator');
const leftBefore = Number(elements.get('left-splitter').getAttribute('aria-valuenow'));
elements.get('left-splitter').onkeydown({key:'ArrowRight',preventDefault() {},stopPropagation() {}});
assert(Number(elements.get('left-splitter').getAttribute('aria-valuenow')) > leftBefore,
  'Keyboard adjustment should enlarge the materials pane');
assert(stored.has('sprite-workbench-layout'),'Layout size should survive a reload');
elements.get('canvas-pane').clientHeight = 900;
for (let i=0;i<8;i++) elements.get('timeline-splitter').onkeydown({key:'ArrowUp',preventDefault() {},stopPropagation() {}});
assert.equal(Number(elements.get('timeline-splitter').getAttribute('aria-valuenow')),320);
context.window.innerWidth = 667; context.window.innerHeight = 375;
elements.get('canvas-pane').clientHeight = 0;
windowListeners.get('resize').forEach(callback => callback());
context.window.innerWidth = 1440; context.window.innerHeight = 900;
elements.get('canvas-pane').clientHeight = 900;
windowListeners.get('resize').forEach(callback => callback());
assert.equal(Number(elements.get('timeline-splitter').getAttribute('aria-valuenow')),320,
  'Returning from a hidden narrow canvas must restore the preferred timeline height');
for (let i=0;i<8;i++) elements.get('left-splitter').onkeydown({key:'ArrowRight',preventDefault() {},stopPropagation() {}});
for (let i=0;i<7;i++) elements.get('right-splitter').onkeydown({key:'ArrowLeft',preventDefault() {},stopPropagation() {}});
assert.equal(Number(elements.get('left-splitter').getAttribute('aria-valuenow')),420);
assert.equal(Number(elements.get('right-splitter').getAttribute('aria-valuenow')),460);
context.window.innerWidth = 1101; elements.get('workspace').clientWidth = 1101;
windowListeners.get('resize').forEach(callback => callback());
context.window.innerWidth = 1440; // The resize event may run before clientWidth has caught up.
windowListeners.get('resize').forEach(callback => callback());
assert.equal(Number(elements.get('left-splitter').getAttribute('aria-valuenow')),420,
  'Restoring desktop width must restore the preferred materials pane despite stale clientWidth');
assert.equal(Number(elements.get('right-splitter').getAttribute('aria-valuenow')),460);
elements.get('workspace').clientWidth = undefined;
assert(observedResizes.has(elements.get('workspace')),
  'Workbench widths should react when the workspace resizes without a window event');
context.window.innerWidth = 1101; elements.get('workspace').clientWidth = 1101;
observedResizes.get(elements.get('workspace'))();
assert.equal(Number(elements.get('left-splitter').getAttribute('aria-valuenow')),210);
context.window.innerWidth = 1440; elements.get('workspace').clientWidth = 1440;
observedResizes.get(elements.get('workspace'))();
assert.equal(Number(elements.get('left-splitter').getAttribute('aria-valuenow')),420);
elements.get('workspace').clientWidth = undefined;
assert(elements.get('pane-materials'),'Narrow screens need a visible Materials work-area choice');
elements.get('pane-materials').onclick();
assert.equal(body.dataset.pane,'materials');
assert.equal(elements.get('pane-materials').getAttribute('aria-pressed'),'true');
elements.get('pane-canvas').onclick();
assert.equal(body.dataset.pane,'canvas');

state.data.notes = ['human draft'];
projects.get('alpha').asset_revision = 'new-pixels';
await checkExternalChanges();
assert(state.externalChange); assert(dirty());
await refreshExternal();
assert.deepEqual(state.data.notes,['human draft']); assert.equal(state.assetRevision,'new-pixels'); assert(dirty());
projects.get('alpha').data.notes = ['agent config']; projects.get('alpha').revision = 'agent-config';
await checkExternalChanges(); assert(state.externalChange);
allowDiscard = false; await refreshExternal();
assert.deepEqual(state.data.notes,['human draft']);
await openProject('beta'); assert.equal(state.projectId,'alpha');
allowDiscard = true; await openProject('beta');
assert.equal(state.projectId,'beta'); assert.equal(state.history.length,0); assert.equal(state.data.notes,undefined);
assert.equal(player.steps.length,0);
state.data.notes = ['beta edit']; await save();
const saved = requests.findLast(request => request.options.method === 'POST');
assert.equal(saved.url,'/api/projects/beta/save');
assert.equal(JSON.parse(saved.options.body).asset_revision,'a-beta');
assert(!dirty());

projects.get('beta').asset_revision = 'background-update'; pausedProject = 'beta';
const refreshing = checkExternalChanges(); await flush();
assert.equal(typeof resumeSnapshot,'function');
state.data.notes = ['typed while refresh was pending'];
pausedProject = null; resumeSnapshot(); await refreshing;
assert.deepEqual(state.data.notes,['typed while refresh was pending']);
await refreshExternal(); assert(dirty()); await save();

projects.get('beta').asset_revision = 'another-update'; pausedProject = 'beta'; resumeSnapshot = null;
const previousProjectRefresh = checkExternalChanges(); await flush();
assert.equal(typeof resumeSnapshot,'function');
await openProject('alpha');
pausedProject = null; resumeSnapshot(); await previousProjectRefresh;
assert.equal(state.projectId,'alpha'); assert.equal(state.data.character,'alpha');
await showProjects(); assert(body.classList.contains('project-home')); assert.equal(state.data,null);

elements.get('project-new').onclick();
elements.get('new-project-name').value = 'new'; elements.get('new-project-id').value = 'new-id';
await elements.get('project-form').onsubmit({preventDefault() {}});
assert.equal(state.projectId,'new-id'); assert(!elements.get('project-dialog').open);
assert(!body.classList.contains('project-home')); assert.equal(state.mode,'reference');

const {mode,uploadFile,selectAsset,deleteMaterials,activeSteps} = context.hooks;
state.data.actions.idle = {fps:12,sprites:null}; state.action = 'idle'; mode('action');
const imageFile = name => ({name,size:64});
const processedInput = elements.get('processed-upload');
processedInput.files = [imageFile('a.png'),imageFile('bad.png'),imageFile('b.png')];
await uploadFile(processedInput,'processed');
assert.equal(state.assets.length,2,elements.get('toast').textContent);
assert.match(elements.get('toast').textContent,/2\/3/);
assert.match(elements.get('toast').textContent,/bad.png/);
selectAsset('imports/a.png'); selectAsset('imports/b.png',{shiftKey:true});
assert.equal(state.assetSelection.size,2);
elements.get('assets-add').onclick();
assert.deepEqual([...state.data.actions.idle.sprites],['imports/a.png','imports/b.png']);
assert.equal(state.history.length,1,'Adding a selection is one undo operation');
await deleteMaterials('processed',[...state.assetSelection]);
assert.equal(state.assets.length,2); assert.match(elements.get('toast').textContent,/idle/);
state.data.actions.idle.sprites = null;
await deleteMaterials('processed',[...state.assetSelection]);
assert.equal(state.assets.length,0); assert.equal(state.assetSelection.size,0);

processedInput.files = [imageFile('conflict.png'),imageFile('skipped.png')];
await uploadFile(processedInput,'processed');
assert.equal(state.assets.length,0); assert.match(elements.get('toast').textContent,/未处理 1/);
const refInput = elements.get('reference-upload');
refInput.files = [imageFile('identity.png'),imageFile('style.png')];
await uploadFile(refInput,'reference');
assert.equal(state.mode,'reference',elements.get('toast').textContent);
assert.equal(state.references.length,2); assert.equal(state.reference,'references/identity.png');
assert.equal(activeSteps().length,0); assert.equal(player.sourceView.url,'/refs/identity.png');
await elements.get('delete-item').onclick();
assert.equal(state.references.length,1); assert.equal(state.reference,'references/style.png');
const requestCountBeforeSettings = requests.length;
elements.get('settings-open').onclick();
assert(elements.get('settings-dialog').open);
elements.get('settings-name').value = '改名后的工程';
elements.get('settings-width').value = '5'; elements.get('settings-height').value = '7';
elements.get('settings-anchor-x').value = '0.5'; elements.get('settings-anchor-y').value = '0.5';
elements.get('settings-form').onsubmit({preventDefault() {}});
assert.deepEqual([...state.data.frame_size],[5,7]);
assert.deepEqual([...state.data.anchor.pixels],[2,4]);
assert.equal(state.data.project.name,'改名后的工程');
assert.equal(elements.get('project-name').textContent,'改名后的工程');
assert.equal(requests.length,requestCountBeforeSettings,'Settings remain a local draft until Save');
context.hooks.restoreHistory(false);
assert.deepEqual([...state.data.frame_size],[32,32]);
assert.equal(elements.get('project-name').textContent,'new-id');
await elements.get('history-open').onclick();
assert(elements.get('history-dialog').open);
assert.match(elements.get('history-list').innerHTML,/version-one/);
await elements.get('history-list').querySelectorAll('[data-version]')[0].onclick();
assert.match(state.revision,/restored/);
assert(!elements.get('history-dialog').open);
const {previewSource} = context.hooks;
state.sources = ['sheet.png','slow.png','fast.png'].map(file => ({file,url:'/sources/' + file,size:[16,16]}));
for (const source of state.sources) state.data.sources[source.file] = {};
state.source = 'sheet.png'; mode('source');
context.window.innerWidth = 375;
elements.get('pane-materials').onclick();
elements.get('item-list').querySelectorAll('[data-item]')[0].onclick();
assert.equal(body.dataset.pane,'canvas','Choosing source material should reveal its canvas on narrow screens');
assert.equal(document.activeElement,elements.get('canvas-pane'),'Keyboard focus should follow the opened work area');
context.window.innerWidth = 1440;
await previewSource(); await previewSource();
assert.equal(previewRequests.filter(source => source === 'sheet.png').length,1,'Unchanged preview should be reused');
state.data.sources['sheet.png'].process = {offset:[1,0]};
renderAll();
assert.match(elements.get('draft-state').textContent,/待保存/);
assert.match(elements.get('preview-state').textContent,/待预览|待应用/);
await previewSource();
assert.match(elements.get('preview-state').textContent,/待应用/);
assert.equal(previewRequests.filter(source => source === 'sheet.png').length,2,'Recipe edits need a fresh preview');
state.data.sources['sheet.png'].process = {offset:[2,0]};
renderAll();
assert.match(elements.get('preview-state').textContent,/待预览/,
  'A preview from an older recipe cannot be described as ready to apply');
await previewSource();
assert.match(elements.get('preview-state').textContent,/待应用/);
state.source = 'slow.png'; const slowPreview = previewSource(); await flush();
state.source = 'fast.png'; await previewSource();
releaseSlowPreview(); await slowPreview;
assert.equal(state.previewSource,'fast.png','Late preview must not replace the selected source');
await elements.get('prepare').onclick();
assert(requests.some(request => request.url.endsWith('/jobs/prepare')),'Source preparation should report progress through a job');
await openProject('alpha');
state.data.project.name = 'Local title';
projects.get('alpha').data.notes = ['disk note']; projects.get('alpha').revision = 'disk-merge';
await checkExternalChanges();
assert(state.externalChange);
await elements.get('external-merge').onclick();
assert(elements.get('merge-dialog').open);
await elements.get('merge-apply').onclick();
assert.equal(state.data.project.name,'Local title');
assert.deepEqual([...state.data.notes],['disk note']);
assert.equal(state.revision,'disk-merge'); assert(dirty());
projects.get('alpha').revision = 'disk-changed-again';
await save(); assert(dirty(),'Another disk change must still block Save after merge');
projects.get('alpha').data.project.name = 'Disk title'; projects.get('alpha').revision = 'newer-disk';
await checkExternalChanges(); await elements.get('external-merge').onclick();
const choice = elements.get('merge-conflicts').querySelectorAll('[data-merge-choice]').find(input => input.dataset.mergeChoice === 'project/name');
assert(choice,'Same-field changes must be shown for explicit selection');
choice.value = 'disk'; elements.get('merge-apply').onclick();
assert.equal(state.data.project.name,'Disk title');
assert.equal(state.revision,'newer-disk');
elements.get('export-open').onclick();
elements.get('export-format').value = 'project';
await elements.get('export-form').onsubmit({preventDefault() {}});
assert(requests.some(request => request.url.endsWith('/jobs/export')),'Export must start a progress job');
assert(requests.some(request => request.url.endsWith('/jobs/job-1/download')),'Completed job must download its ZIP');
assert(!elements.get('export-dialog').open);
await openProject('beta');
state.sources = [{file:'sheet.png',url:'/sources/sheet.png',size:[16,16],stale:false}];
projects.get('beta').sources = [{file:'sheet.png',url:'/sources/sheet.png',size:[16,16],stale:true}];
state.data.project.name = 'Metadata refresh';
await save();
assert.match(elements.get('material-state').textContent,/1 张待更新/,
  'Saving a recipe must refresh stale material labels without applying images');
const settingsRevision = state.revision;
projects.get('beta').data.frame_size = [64,64];
projects.get('beta').data.anchor.pixels = [32,58];
projects.get('beta').revision = 'disk-settings';
pausedProject = 'beta'; resumeSnapshot = null;
const pendingSettingsRefresh = checkExternalChanges(); await flush();
assert.equal(typeof resumeSnapshot,'function');
elements.get('settings-open').onclick();
elements.get('settings-name').value = 'Local rename';
pausedProject = null; resumeSnapshot(); await pendingSettingsRefresh;
await checkExternalChanges();
assert.equal(state.revision,settingsRevision,'Open settings must not adopt a newer disk revision behind the form');
assert.equal(elements.get('settings-name').value,'Local rename');
elements.get('settings-form').onsubmit({preventDefault() {}});
assert.equal(state.data.project.name,'Local rename');
assert(dirty());
assert.equal(projects.get('beta').revision,'disk-settings');
await save();
assert(dirty(),'A stale settings form must encounter a revision conflict');
assert.deepEqual(projects.get('beta').data.frame_size,[64,64],'External canvas changes must survive');
await openProject('alpha');
state.data.actions.idle = {fps:12,sprites:['a.png','b.png']}; state.action = 'idle';
state.assets = [{ref:'a.png',url:'/a.png',size:[32,32]},{ref:'b.png',url:'/b.png',size:[32,32]}];
mode('action');
const frameBeforeResize = state.selected;
elements.get('left-splitter').focus();
const resizeKey = {key:'ArrowRight',code:'ArrowRight',defaultPrevented:false,preventDefault() { this.defaultPrevented = true; },stopped:false,stopPropagation() { this.stopped = true; }};
elements.get('left-splitter').onkeydown(resizeKey);
if (!resizeKey.stopped) documentListeners.get('keydown').forEach(callback => callback(resizeKey));
assert.equal(state.selected,frameBeforeResize,'Resizing with an arrow key must not step playback');
player.pause(); elements.get('pane-materials').focus();
documentListeners.get('keydown').forEach(callback => callback({key:' ',code:'Space',preventDefault() {}}));
assert.equal(player.playing,false,'Space on a work-area button must not start playback');
elements.get('pane-materials').onclick();
processedInput.files = [imageFile('hold.png')];
const heldImport = uploadFile(processedInput,'processed'); await flush();
assert(elements.get('activity-state'),'Narrow tasks need a visible progress message outside the hidden canvas');
assert.equal(elements.get('activity-state').hidden,false);
assert.match(elements.get('activity-state').textContent,/1\/1.*hold.png/);
releaseHeldUpload(); await heldImport;
assert.equal(elements.get('activity-state').hidden,true);
elements.get('export-open').onclick();
elements.get('export-format').value = 'gif';
elements.get('export-format').onchange();
assert.match(elements.get('export-note').textContent,/256 色/,'GIF choice should explain its color limit');
await elements.get('export-form').onsubmit({preventDefault() {}});
assert(requests.some(request => request.url.endsWith('/jobs/export') &&
  JSON.parse(request.options.body).options?.format === 'gif'),
  'GIF choice should start the same tracked export flow');
console.log('Workbench session: creation, routing, external changes, batch import/selection/deletion and references passed.');

// Dragging edits only the selected frame draft, measured in canvas pixels.
await openProject('beta');
state.sources = [{file:'drag.png',url:'/sources/drag.png',size:[16,16]}];
state.data.frame_size = [32,32];
state.data.defaults.process = {offset:[3,-2]};
state.data.sources = {'drag.png':{process:{overrides:{'001':{scale:0.75}}}}};
state.source = 'drag.png'; mode('source'); await previewSource();
state.selected = 1; renderAll();
state.saved = JSON.stringify(state.data); state.savedData = structuredClone(state.data);
state.history = []; state.future = [];
const stage = elements.get('stage');
stage.clientLeft = 1; stage.clientTop = 1;
const pointer = (clientX,clientY,extra = {}) => ({clientX,clientY,pointerId:7,button:0,preventDefault() {},...extra});
const sendPointer = (type,x,y,extra) => stage.dispatch(type,pointer(x,y,extra));
const requestsBeforeDrag = requests.length;
sendPointer('pointerdown',116,66);
sendPointer('pointermove',136,56);
assert.equal(Number(elements.get('override-x').value),13,'A 20-screen-pixel move at 200% adds 10 canvas pixels to the inherited offset');
assert.equal(Number(elements.get('override-y').value),-7);
assert.deepEqual([...player.steps[1].previewOffset],[10,-5]);
assert(!player.steps[0].previewOffset,'Other frames keep their own positions');
assert.equal(dirty(),false,'Movement is transient until pointer release');
assert.equal(requests.length,requestsBeforeDrag,'Dragging must not process or save on every pointer movement');
sendPointer('pointerup',136,56);
assert.deepEqual([...state.data.sources['drag.png'].process.overrides['001'].offset],[13,-7]);
assert.equal(state.data.sources['drag.png'].process.overrides['001'].scale,0.75);
assert.equal(state.history.length,1,'A complete drag is one undo step');
assert(dirty());
assert.equal(requests.length,requestsBeforeDrag,'Release schedules a read-only preview, never an implicit save/apply');

// A second adjustment accumulates even before the server preview returns.
sendPointer('pointerdown',140,62); sendPointer('pointermove',144,68); sendPointer('pointerup',144,68);
assert.deepEqual([...state.data.sources['drag.png'].process.overrides['001'].offset],[15,-4]);
assert.deepEqual([...player.steps[1].previewOffset],[12,-2]);
assert.equal(state.history.length,2);
const dataBeforeCancel = JSON.stringify(state.data);
sendPointer('pointerdown',144,68); sendPointer('pointermove',154,64);
sendPointer('pointercancel',154,64);
assert.equal(JSON.stringify(state.data),dataBeforeCancel);
assert.deepEqual([...player.steps[1].previewOffset],[12,-2]);
assert.equal(Number(elements.get('override-x').value),15);
assert.equal(state.history.length,2,'Cancelled movement does not enter undo history');
sendPointer('pointerdown',144,68); sendPointer('pointermove',184,68);
assert.equal(Number(elements.get('override-x').value),35,'Canvas borders are excluded when converting screen movement to image pixels');
sendPointer('pointercancel',184,68);
sendPointer('pointerdown',144,68); sendPointer('pointermove',148,68);
documentListeners.get('keydown').forEach(callback => callback({key:'Escape',preventDefault() {}}));
assert.equal(Number(elements.get('override-x').value),15,'Escape restores the pre-drag offset');
sendPointer('pointerup',148,68);
assert.equal(state.history.length,2);
sendPointer('pointerdown',144,68); sendPointer('pointerup',144,68);
assert.equal(state.history.length,2,'A click without movement does not add an undo step');
sendPointer('pointerdown',144,68,{button:2}); sendPointer('pointermove',150,68); sendPointer('pointerup',150,68);
assert.equal(JSON.stringify(state.data),dataBeforeCancel,'Secondary-button drags cannot edit offsets');
sendPointer('pointerdown',144,68); sendPointer('pointermove',214,68,{pointerId:8});
assert.equal(Number(elements.get('override-x').value),15,'Other pointers cannot move an active drag');
sendPointer('pointermove',214,68);
assert.equal(Number(elements.get('override-x').value),50,'Captured movement outside the canvas is not clamped to its edge');
sendPointer('lostpointercapture',214,68);
assert.equal(Number(elements.get('override-x').value),15);
sendPointer('pointerdown',144,68); sendPointer('pointermove',150,68);
mode('action'); sendPointer('pointerup',150,68);
assert.equal(JSON.stringify(state.data),dataBeforeCancel,'Switching modes cancels movement rather than applying it to another view');
mode('source'); state.selected = 1; renderAll();

// Background responses started before a drag cannot replace its baseline.
holdDragPreview = true;
const staleDragPreview = previewSource(true); await flush();
const dragBaseline = state.preview;
sendPointer('pointerdown',144,68); sendPointer('pointermove',146,68);
releaseDragPreview(); await staleDragPreview;
assert.equal(state.preview,dragBaseline);
assert.deepEqual([...player.steps[1].previewOffset],[13,-2]);
sendPointer('pointerup',146,68); holdDragPreview = false;
assert.deepEqual([...state.data.sources['drag.png'].process.overrides['001'].offset],[16,-4]);
context.hooks.restoreHistory(false);
assert.deepEqual([...state.data.sources['drag.png'].process.overrides['001'].offset],[15,-4]);
context.hooks.restoreHistory(true);
assert.deepEqual([...state.data.sources['drag.png'].process.overrides['001'].offset],[16,-4]);
await previewSource();
assert(!player.steps[1].previewOffset,'Authoritative server preview removes the temporary translation');

// Copy mode and empty-canvas clicks must not simulate unappliable movement.
state.data.sources['drag.png'].process.overrides['001'].mode = 'copy'; renderAll();
const beforeCopyDrag = JSON.stringify(state.data);
sendPointer('pointerdown',116,66); sendPointer('pointermove',120,70); sendPointer('pointerup',120,70);
assert.equal(JSON.stringify(state.data),beforeCopyDrag);
delete state.data.sources['drag.png'].process.overrides['001'].mode; renderAll();
sendPointer('pointerdown',160,110); sendPointer('pointermove',162,112); sendPointer('pointerup',162,112);
assert.equal(JSON.stringify(state.data),beforeCopyDrag.replace(',"mode":"copy"',''));
const projectBeforeApply = JSON.stringify(projects.get('beta').data);
assert.notEqual(JSON.stringify(state.data),projectBeforeApply,'Disk configuration remains unchanged before explicit apply');
projects.get('beta').sources = structuredClone(state.sources);
await elements.get('apply-source').onclick();
const applied = requests.filter(request => request.url.endsWith('/apply')).at(-1);
assert(applied);
assert.deepEqual(JSON.parse(applied.options.body).data.sources['drag.png'].process.overrides['001'].offset,[16,-4]);
assert(!dirty());
console.log('Workbench drag preview: scaled movement, accumulation, cancellation, stale responses, undo and explicit apply passed.');

// Sequence deletion is available beside the list and changes only the draft.
const deletionProject = snapshot('alpha');
deletionProject.assets = [{ref:'a.png',url:'/a.png',size:[32,32]},{ref:'b.png',url:'/b.png',size:[32,32]}];
deletionProject.data.actions = {
  idle:{fps:12,sprites:['a.png']},wave:{fps:12,sprites:['a.png','b.png']},
};
deletionProject.data.workbench.reviews = {
  transition:{name:'挥手衔接',mode:'runtime',loop:false,clips:[{action:'wave',repeat:1,start:0,end:null}]},
  remaining:{name:'待机检查',mode:'runtime',loop:false,clips:[{action:'idle',repeat:3,start:0,end:null}]},
};
projects.set('alpha',deletionProject); await openProject('alpha');
state.action = 'wave'; mode('action');
const deleteItem = elements.get('delete-item');
assert.equal(deleteItem.hidden,false,'Action deletion must be visible above the action list');
assert.equal(deleteItem.disabled,false,'Actions can be deleted even when there are no reference images');
const requestsBeforeSequenceDelete = requests.length;
const assetsBeforeSequenceDelete = JSON.stringify(state.assets);
const projectBeforeSequenceDelete = JSON.stringify(deletionProject.data);
await deleteItem.onclick();
assert(state.data.actions.wave,'An action used by a Review must survive deletion attempts');
assert.match(elements.get('toast').textContent,/挥手衔接/,'Explain which Review still uses the action');
assert.equal(state.history.length,0,'Blocked deletion must not create an undo step');

state.data.actions.empty = {fps:12,loop:false,sprites:null}; // A newly created, unsaved action.
state.action = 'empty'; renderAll(); player.playing = true;
allowDiscard = false; await deleteItem.onclick();
assert(state.data.actions.empty,'Cancelling the confirmation preserves the action');
assert.equal(player.playing,true); assert.equal(state.history.length,0);
allowDiscard = true; await deleteItem.onclick();
assert(!state.data.actions.empty,'Empty actions can be deleted through the list');
assert.equal(player.playing,false,'Successful deletion stops playback');
assert.equal(state.history.length,1); assert(!dirty(),'Deleting a newly added, unsaved action restores the saved configuration');
context.hooks.restoreHistory(false); assert(state.data.actions.empty);
context.hooks.restoreHistory(true); assert(!state.data.actions.empty);

state.review = 'transition'; mode('review'); player.index = 1; player.playing = true;
assert.equal(deleteItem.hidden,false,'Review deletion must be visible above the Review list');
assert.equal(deleteItem.disabled,false);
allowDiscard = false; await deleteItem.onclick();
assert(state.data.workbench.reviews.transition,'Cancelling preserves the complete Review');
assert.equal(player.playing,true);
allowDiscard = true; await deleteItem.onclick();
assert(!state.data.workbench.reviews.transition);
assert(dirty(),'Deleting a saved Review marks the project as an unsaved draft');
assert(state.data.workbench.reviews.remaining,'Deleting a Review must preserve other sequences');
assert(state.data.actions.wave,'Deleting a Review must preserve its actions');
assert.equal(player.playing,false); assert.equal(player.index,0,'The next Review starts at its first step');
assert.equal(state.clip,0);
assert(confirmationMessages.some(message => /挥手衔接/.test(message)),'Review confirmation identifies the selected sequence');
context.hooks.restoreHistory(false); assert(state.data.workbench.reviews.transition);
context.hooks.restoreHistory(true); assert(!state.data.workbench.reviews.transition);

state.action = 'wave'; mode('action');
state.busy = true; renderAll(); assert.equal(deleteItem.disabled,true);
await deleteItem.onclick(); assert(state.data.actions.wave,'Busy operations block deletion');
state.busy = false; renderAll();
elements.get('delete-action').click();
assert(!state.data.actions.wave,'The inspector uses the same deletion behavior as the list');
assert(state.data.actions.idle);
state.review = 'remaining'; mode('review');
elements.get('delete-review').click();
assert.deepEqual(Object.keys(state.data.workbench.reviews),[]);
assert.equal(deleteItem.disabled,true,'Deleting the final Review leaves an inert delete button');
const historyAfterLastReview = state.history.length;
await deleteItem.onclick(); assert.equal(state.history.length,historyAfterLastReview);
assert.equal(player.steps.length,0);
mode('action'); await deleteItem.onclick();
assert.deepEqual(Object.keys(state.data.actions),[],'Deleting the final action is supported');
assert.equal(deleteItem.disabled,true); assert.equal(player.steps.length,0);
assert.equal(JSON.stringify(state.assets),assetsBeforeSequenceDelete,'Deleting sequences preserves all sprite materials');
assert.equal(JSON.stringify(deletionProject.data),projectBeforeSequenceDelete,'Sequence deletion is not saved implicitly');
assert.equal(requests.length,requestsBeforeSequenceDelete,'Draft deletion does not call material deletion or save endpoints');
await save();
assert.deepEqual(Object.keys(projects.get('alpha').data.actions),[]);
assert.deepEqual(Object.keys(projects.get('alpha').data.workbench.reviews),[]);
assert.equal(JSON.stringify(projects.get('alpha').assets),assetsBeforeSequenceDelete);
assert(!dirty(),'Explicit saving persists action and Review deletion');
console.log('Workbench sequence deletion: list/inspector access, reference protection, confirmation, empty states, undo and explicit save passed.');

// Slicing and adjustment are distinct working views of the same unsaved source.
state.sources = [{file:'workflow.png',url:'/sources/workflow.png',size:[16,16],count:0}];
state.source = 'workflow.png';
state.data.sources['workflow.png'] = {extract:{method:'grid',cols:2,rows:1},process:{scale:0.8}};
const workflowDraft = JSON.stringify(state.data);
mode('source','original');
await context.hooks.previewSource();
assert.equal(state.sourceView,'original');
assert.equal(state.preview.stage,'extract','Slicing must request native slices rather than processed pixels');
assert(!elements.get('inspector-content').innerHTML.includes('id="process-scale"'),'Slicing hides processing controls');
assert.match(elements.get('timeline-title').textContent,/原帧/);
mode('source','processed');
await context.hooks.previewSource();
assert.equal(state.preview.stage,'process','Adjustment must not reuse cached raw slices');
assert(!elements.get('inspector-content').innerHTML.includes('id="extract-method"'),'Adjustment hides cutting controls');
assert.equal(JSON.stringify(state.data),workflowDraft,'Moving between stages does not discard or save edits');
mode('source','original');
await context.hooks.previewSource();
assert.equal(state.preview.stage,'extract');
assert.equal(JSON.stringify(state.data),workflowDraft);
assert.equal(tabs.filter(tab => tab.classList.contains('active')).length,1);
assert.equal(tabs.find(tab => tab.classList.contains('active')).dataset.view,'original');
holdExtractPreview = true;
const pendingExtraction = context.hooks.previewSource(true);
await flush();
mode('source','processed'); await context.hooks.previewSource(true);
releaseExtractPreview(); await pendingExtraction; holdExtractPreview = false;
assert.equal(state.preview.stage,'process','Late extraction must not replace adjustment preview');
assert.equal(tabs.filter(tab => tab.classList.contains('active')).length,1);
assert.equal(tabs.find(tab => tab.classList.contains('active')).dataset.view,'processed');
console.log('Workbench workflow: isolated slicing/adjustment previews and preserved drafts passed.');
await showProjects();
assert.equal(state.data,null);
assert.equal(state.preview,null,'Returning home releases the previous preview before updating status');
