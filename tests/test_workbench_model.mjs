// No npm dependencies: run with node tests/test_workbench_model.mjs.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../tools/sprite_pipeline/web/model.js',import.meta.url),'utf8');
const {actionSteps,reviewSteps,editFrames,roundMs,reconcileReviewRanges} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const data = {defaults:{fps:16},actions:{
  walk:{loop:true,sprites:['red','green','blue'],animation:{order:[2,0,2],durations_ms:[40,90,130]}},
  rest:{fps:10,sprites:['red']},
}};
assert.deepEqual([roundMs(62.5),roundMs(83.5)],[62,84]);
assert.deepEqual(actionSteps(data,'walk').map(s => s.duration_ms),[62,62,62]);
assert.deepEqual(actionSteps(data,'walk','display').map(s => [s.ref,s.duration_ms]),[['blue',40],['red',90],['blue',130]]);
const review = {mode:'runtime',clips:[{action:'walk',repeat:2,start:1,end:2},{action:'rest',repeat:1}]};
assert.deepEqual(reviewSteps(data,review).map(s => [s.ref,s.duration_ms]),[['green',62],['blue',62],['green',62],['blue',62],['red',100]]);
assert.deepEqual(reviewSteps(data,review).filter(s => s.boundary).map(s => s.clip),[0,0,1]);
const action = structuredClone(data.actions.walk);
editFrames(action,[2,0],['blue','red']);
assert.deepEqual(action.animation.order,[0,1,0]);
assert.deepEqual(action.animation.durations_ms,[40,90,130]);
editFrames(action,[0,null,1],['blue','new','red']);
assert.deepEqual(action.animation.order,[0,2,0,1]);
assert.equal(action.animation.durations_ms.at(-1),83); // No action FPS: uses the default 12 FPS.
editFrames(action,[0,1,2,null],[...action.sprites,'another'],16);
assert.equal(action.animation.durations_ms.at(-1),62);
data.workbench = {reviews:{sample:{mode:'runtime',clips:[{action:'rest',start:9,end:10,repeat:1}]}}};
reconcileReviewRanges(data);
assert.deepEqual(data.workbench.reviews.sample.clips[0],{action:'rest',start:0,end:0,repeat:1});
let mergeModule;
try {
  const mergeSource = await readFile(new URL('../tools/sprite_pipeline/web/merge.js',import.meta.url),'utf8');
  mergeModule = await import('data:text/javascript;base64,' + Buffer.from(mergeSource).toString('base64'));
} catch {}
assert.equal(typeof mergeModule?.mergeDraft,'function','Three-way merge model is available');
const base = {project:{name:'Old'},actions:{idle:{fps:8,sprites:['a','b']}},remove:'value'};
const local = structuredClone(base); local.project.name = 'Local'; delete local.remove;
const disk = structuredClone(base); disk.actions.idle.fps = 12;
const independent = mergeModule.mergeDraft(base,local,disk);
assert.equal(independent.conflicts.length,0);
assert.equal(independent.merged.project.name,'Local');
assert.equal(independent.merged.actions.idle.fps,12);
assert(!('remove' in independent.merged));
assert.equal(base.project.name,'Old','Merge must not mutate its inputs');
const diskConflict = structuredClone(base); diskConflict.project.name = 'Disk'; diskConflict.remove = null;
diskConflict.actions.idle.sprites = ['b','a'];
const localConflict = structuredClone(local); localConflict.actions.idle.sprites = ['a','c'];
const conflicted = mergeModule.mergeDraft(base,localConflict,diskConflict);
assert.deepEqual(conflicted.conflicts.map(item => item.path.join('/')).sort(),['actions/idle/sprites','project/name','remove']);
assert.equal(conflicted.conflicts.find(item => item.path[0] === 'remove').localMissing,true);
const resolved = mergeModule.resolveMerge(conflicted,{"project/name":"disk","actions/idle/sprites":"disk","remove":"disk"});
assert.equal(resolved.project.name,'Disk');
assert.deepEqual(resolved.actions.idle.sprites,['b','a']);
assert.equal(resolved.remove,null,'Explicit null differs from deletion');
const unusualKey = mergeModule.mergeDraft({},JSON.parse('{"__proto__":{"safe":true}}'),{other:1});
assert.equal(Object.hasOwn(unusualKey.merged,'__proto__'),true,'Own config keys must survive a merge');
const playerSource = await readFile(new URL('../tools/sprite_pipeline/web/player.js',import.meta.url),'utf8');
const {Player} = await import('data:text/javascript;base64,' + Buffer.from(playerSource).toString('base64'));
let imageCount = 0;
globalThis.Image = class {
  constructor() { imageCount++; this.complete = false; this.naturalWidth = 0; this.listeners = {}; }
  set src(value) { this.url = value; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  load() { this.complete = true; this.naturalWidth = 16; this.naturalHeight = 16; for (const callback of this.listeners.load || []) callback(); }
};
globalThis.ResizeObserver = class { observe() {} };
globalThis.document = {addEventListener() {}};
globalThis.requestAnimationFrame = () => 1;
const draws = [];
const context2d = {clearRect() {},drawImage(...args) { draws.push(args); },save() {},restore() {},setLineDash() {},beginPath() {},moveTo() {},lineTo() {},stroke() {},arc() {},fillText() {}};
const canvas = {getContext:() => context2d,style:{},width:16,height:16};
const player = new Player(canvas,{clientWidth:300,clientHeight:300},() => {});
player.options.guides = false;
const longSteps = Array.from({length:100},(_,i) => ({url:`/frame/${i}`,duration_ms:100}));
player.setSteps(longSteps);
assert(imageCount <= 8,`Long sequence eagerly loaded ${imageCount} images`);
player.images.get('/frame/0').load();
await Promise.resolve();
assert.equal(player.loading,false,'Playback should start when the current frame is ready');
player.size = [32,32]; player.paint({url:'/frame/0'});
assert.equal(draws.at(-1).length,3,'Old pixels must not stretch into a newly edited canvas');
player.toggle();
player.tick(0); player.tick(100);
assert.equal(player.index,0,'Playback must hold the visible frame while the next image loads');
assert.equal(player.loading,true);
player.images.get('/frame/1').load();
player.tick(200);
assert.equal(player.index,1,'Playback resumes at the next frame after it loads');
console.log('Workbench model: timing, review boundaries and display remapping passed.');
