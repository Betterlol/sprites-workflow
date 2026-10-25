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
  constructor(value = '') { this.value = value; this.defaultValue = value; this.classList = new Classes(); this.dataset = {}; this.hidden = false; this.textContent = ''; this.tagName = 'DIV'; this.checked = true; this.open = false; }
  set innerHTML(value) { this.html = value; this.mergeChoices = null; register(value); }
  get innerHTML() { return this.html || ''; }
  querySelectorAll(selector) {
    if (selector === '[data-project]') return [...this.innerHTML.matchAll(/data-project="([^"]+)"/g)].map(([,id]) => {
      const button = new Element(); button.dataset.project = id; return this.projectButtons?.find(b => b.dataset.project === id) || button;
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
    return [];
  }
  setAttribute() {}
  addEventListener() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  reset() { for (const [id, element] of elements) if (id.startsWith('new-project-')) element.value = element.defaultValue; }
  click() { this.onclick?.(); }
}
function register(markup) {
  for (const [,tag,id,attributes] of markup.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"([^>]*)>/g)) {
    if (elements.has(id)) continue;
    const element = new Element(attributes.match(/\bvalue="([^"]*)"/)?.[1] || ''); element.tagName = tag.toUpperCase(); elements.set(id,element);
  }
}
register(html);
const descendants = new Map();
const tabs = ['source','action','review','reference'].map(mode => { const tab = new Element(); tab.dataset.mode = mode; return tab; });
const body = new Element(); body.classList.add('project-home');
const document = {
  body, hidden:false, activeElement:{tagName:'BODY'}, addEventListener() {}, createElement:() => new Element(),
  querySelector(selector) {
    if (selector.startsWith('#') && !selector.includes(' ')) return elements.get(selector.slice(1)) || null;
    if (!descendants.has(selector)) descendants.set(selector,new Element()); return descendants.get(selector);
  },
  querySelectorAll:selector => selector === '[data-mode]' ? tabs : [],
};
class Player {
  constructor(canvas,area,onStep) { this.onStep = onStep; this.steps = []; this.index = 0; this.options = {}; this.images = new Map(); }
  pause() { this.playing = false; }
  reset() { this.pause(); this.steps = []; this.index = 0; this.images.clear(); }
  resize() {}
  draw() {}
  setProject(data) { this.size = data.frame_size; this.anchor = data.anchor.pixels; }
  setSteps(steps,index = 0) { this.steps = steps; this.index = index; this.onStep(index); }
}
const snapshot = id => ({data:{version:2,project:{name:id},character:id,frame_size:[32,32],anchor:{pixels:[16,29]},defaults:{},sources:{},actions:{},workbench:{reviews:{}}},
  revision:'r-' + id,asset_revision:'a-' + id,sources:[],assets:[],references:[],legacy_count:0,project:{id,name:id,directory:'/workspaces/' + id},warnings:[]});
const projects = new Map([['alpha',snapshot('alpha')],['beta',snapshot('beta')]]);
const requests = [];
const intervals = [];
const previewRequests = [];
let releaseSlowPreview = null;
let allowDiscard = true;
let pausedProject = null, resumeSnapshot = null;
const context = {
  ...model, ...mergeModel, Player, document, structuredClone, URL, URLSearchParams, Blob, AbortController,
  FileReader:class { readAsDataURL() { this.result = 'data:image/png;base64,cGl4ZWxz'; queueMicrotask(() => this.onload()); } },
  location:{pathname:'/',search:''}, history:{replaceState() {}},
  window:{addEventListener() {}}, setTimeout:() => 1, clearTimeout() {}, setInterval:(_,delay) => intervals.push(delay),
  confirm:() => allowDiscard, console,
  fetch:async (url, options = {}) => {
    requests.push({url,options});
    let result;
    if (url === '/api/projects') {
      if (options.method === 'POST') { const body = JSON.parse(options.body); const id = body.id || body.name; projects.set(id,snapshot(id)); result = {id}; }
      else result = {token:'session',workspace_root:'/workspaces',projects:[...projects.keys()].map(id => ({id,name:id,character:id,frame_size:[32,32]}))};
    } else {
      const [,id,operation] = url.match(/^\/api\/projects\/([^/]+)(?:\/(\w+))?$/) || [];
      const project = projects.get(decodeURIComponent(id)); assert(project,`Unknown request ${url}`);
      if (operation === 'save') { const payload = JSON.parse(options.body); if (payload.revision !== project.revision) return {ok:false,status:409,json:async () => ({error:'external change'})}; project.data = structuredClone(payload.data); project.revision += '-saved'; result = {revision:project.revision}; }
      else if (operation === 'upload') {
        const payload = JSON.parse(options.body);
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
        if (body.source === 'slow.png') await new Promise(resolve => { releaseSlowPreview = resolve; });
        result = {scale:1,frames:[{id:'000',ref:body.source.replace('.png','/000.png'),box:[0,0,8,8],url:'/preview/' + body.source,bbox:[0,0,8,8]}]};
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
source = source.replace(/^import .*\n/gm,'');
source += '\nglobalThis.hooks = {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player,mode,uploadFile,selectAsset,deleteMaterials,activeSteps,previewSource,restoreHistory};';
vm.runInNewContext(source,context,{filename:'app.js'});
const flush = () => new Promise(resolve => setImmediate(resolve));
await flush();
const {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player} = context.hooks;
assert(intervals.includes(12000),'Background checks should use a longer idle interval');
assert(body.classList.contains('project-home'));
assert.match(elements.get('project-list').innerHTML,/alpha/);
await openProject('alpha');
assert.equal(state.projectId,'alpha'); assert(!body.classList.contains('project-home'));
assert.equal(elements.get('project-name').textContent,'alpha',elements.get('toast').textContent);

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
assert(!body.classList.contains('project-home')); assert.equal(state.mode,'source');

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
await previewSource(); await previewSource();
assert.equal(previewRequests.filter(source => source === 'sheet.png').length,1,'Unchanged preview should be reused');
state.data.sources['sheet.png'].process = {offset:[1,0]};
await previewSource();
assert.equal(previewRequests.filter(source => source === 'sheet.png').length,2,'Recipe edits need a fresh preview');
state.source = 'slow.png'; const slowPreview = previewSource(); await flush();
state.source = 'fast.png'; await previewSource();
releaseSlowPreview(); await slowPreview;
assert.equal(state.previewSource,'fast.png','Late preview must not replace the selected source');
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
console.log('Workbench session: creation, routing, external changes, batch import/selection/deletion and references passed.');
