// Exercise the actual app module with a minimal DOM and an in-memory HTTP API.
// Browser installation is unnecessary; pixel rendering is tested by Python.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const html = await readFile(new URL('../tools/sprite_pipeline/web/index.html',import.meta.url),'utf8');
const modelSource = await readFile(new URL('../tools/sprite_pipeline/web/model.js',import.meta.url),'utf8');
const model = await import('data:text/javascript;base64,' + Buffer.from(modelSource).toString('base64'));
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
  set innerHTML(value) { this.html = value; register(value); }
  get innerHTML() { return this.html || ''; }
  querySelectorAll(selector) {
    if (selector === '[data-project]') return [...this.innerHTML.matchAll(/data-project="([^"]+)"/g)].map(([,id]) => {
      const button = new Element(); button.dataset.project = id; return this.projectButtons?.find(b => b.dataset.project === id) || button;
    });
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
const tabs = ['source','action','review'].map(mode => { const tab = new Element(); tab.dataset.mode = mode; return tab; });
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
  revision:'r-' + id,asset_revision:'a-' + id,sources:[],assets:[],legacy_count:0,project:{id,name:id,directory:'/workspaces/' + id},warnings:[]});
const projects = new Map([['alpha',snapshot('alpha')],['beta',snapshot('beta')]]);
const requests = [];
let allowDiscard = true;
let pausedProject = null, resumeSnapshot = null;
const context = {
  ...model, Player, document, structuredClone, URL, URLSearchParams, Blob,
  location:{pathname:'/',search:''}, history:{replaceState() {}},
  window:{addEventListener() {}}, setTimeout:() => 1, clearTimeout() {}, setInterval() {},
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
      if (operation === 'save') { const payload = JSON.parse(options.body); project.data = structuredClone(payload.data); project.revision += '-saved'; result = {revision:project.revision}; }
      else if (operation === 'changes') result = {revision:project.revision,asset_revision:project.asset_revision};
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
source += '\nglobalThis.hooks = {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player};';
vm.runInNewContext(source,context,{filename:'app.js'});
const flush = () => new Promise(resolve => setImmediate(resolve));
await flush();
const {state,openProject,showProjects,checkExternalChanges,refreshExternal,save,dirty,player} = context.hooks;
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
console.log('Workbench session: creation, routing, tab isolation and external-change draft protection passed.');
