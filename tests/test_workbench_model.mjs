// No npm dependencies: run with node tests/test_workbench_model.mjs.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const dragPlayerSource = await readFile(new URL('../tools/sprite_pipeline/web/player.js',import.meta.url),'utf8');
const {Player:DragPlayer} = await import('data:text/javascript;base64,' + Buffer.from(dragPlayerSource).toString('base64'));
const paints = [];
const canvasPlayer = Object.create(DragPlayer.prototype);
Object.assign(canvasPlayer,{size:[32,32],index:1,options:{reference:true,onion:true,guides:false},idle:'idle',
  steps:[{url:'previous'},{url:'current',previewOffset:[12,-5]}],assets:new Map([['idle',{url:'idle'}]]),
  images:new Map(['idle','previous','current'].map(name => [name,{name,complete:true,naturalWidth:32}])),
  context:{clearRect() {},drawImage(image,x,y) { paints.push([image.name,x,y,this.globalAlpha]); }}});
canvasPlayer.draw();
assert.deepEqual(paints,[['idle',0,0,0.22],['previous',0,0,0.28],['current',12,-5,1]],
  'Single-frame movement translates the current sprite while idle and previous-frame alignment references stay fixed');
const {actionSteps,reviewSteps,editFrames,roundMs,reconcileReviewRanges} = await import(new URL('../tools/sprite_pipeline/web/model.js',import.meta.url));

// Unified resource contracts; added with this feature, intentionally not run at delivery.
const {resolveResource,reconcileCompositeAnimations,validateComposition,ensureSlots} = await import(new URL('../tools/sprite_pipeline/web/resources.js',import.meta.url));
const composed = {defaults:{fps:12},actions:{
  base:{fps:20,loop:true,sprites:['red.png','green.png']},
  combo:{slots:[{id:'begin',resource:{kind:'action',ref:'base'}},{id:'middle',resource:{kind:'sequence',ref:'bridge'},speed:2},{id:'hold',resource:{kind:'sprite',ref:'red.png'},duration_ms:80,repeat:2}]},
},workbench:{reviews:{bridge:{mode:'runtime',slots:[
  {id:'pose',resource:{kind:'sprite',ref:'blue.png'},duration_ms:120},
  {id:'finish',resource:{kind:'action',ref:'base'},start:1,end:1,repeat:2,speed:2},
]}}}};
assert.deepEqual(resolveResource(composed,'action','combo').map(s=>s.ref),['red.png','green.png','blue.png','green.png','green.png','red.png','red.png']);
assert.deepEqual(resolveResource(composed,'action','combo').map(s=>s.duration_ms),[50,50,60,12,12,80,80]);
const remapped={actions:{part:{fps:20,sprites:['red.png','green.png']},main:{slots:[{id:'kept',resource:{kind:'action',ref:'part'}}],animation:{order:[1]}}}};
const previous=structuredClone(remapped);
remapped.actions.part.fps=10;
reconcileCompositeAnimations(previous,remapped);
assert.deepEqual(remapped.actions.main.animation.order,[1],'Intentional display omissions survive changes to inherited timing');
assert.deepEqual(resolveResource(remapped,'action','main','display').map(s=>s.duration_ms),[100],'An order alone does not freeze inherited durations');
composed.actions.base={slots:[{id:'cycle',resource:{kind:'sequence',ref:'bridge'}}]};
assert.throws(()=>validateComposition(composed),/循环/);
const trimmedDisplay={actions:{part:{sprites:['red.png','green.png'],animation:{order:[0]}}},workbench:{reviews:{cut:{mode:'display',slots:[{id:'cut',resource:{kind:'action',ref:'part'},start:1}]}}}};
assert.throws(()=>validateComposition(trimmedDisplay),/范围/,'Validate a sequence using its authored playback mode before rendering');
const parentFirst={actions:{
  parent:{slots:[{id:'child-use',resource:{kind:'action',ref:'child'},mode:'display'}],animation:{order:[1,0]}},
  child:{sprites:['red.png','green.png'],animation:{order:[1,0]}},
}};
const parentBefore=structuredClone(parentFirst);
ensureSlots(parentFirst,'action','child').splice(0,1);
reconcileCompositeAnimations(parentBefore,parentFirst);
assert.deepEqual(resolveResource(parentFirst,'action','parent','display').map(s=>s.ref),['green.png'],'Reconcile children before display-dependent parents, independently of collection insertion order');

const data = {defaults:{fps:16},actions:{
  walk:{loop:true,sprites:['red.png','green.png','blue.png'],animation:{order:[2,0,2],durations_ms:[40,90,130]}},
  rest:{fps:10,sprites:['red.png']},
}};
assert.deepEqual([roundMs(62.5),roundMs(83.5)],[62,84]);
assert.deepEqual(actionSteps(data,'walk').map(s => s.duration_ms),[62,62,62]);
assert.deepEqual(actionSteps(data,'walk','display').map(s => [s.ref,s.duration_ms]),[['blue.png',40],['red.png',90],['blue.png',130]]);
const review = {mode:'runtime',clips:[{action:'walk',repeat:2,start:1,end:2},{action:'rest',repeat:1}]};
assert.deepEqual(reviewSteps(data,review).map(s => [s.ref,s.duration_ms]),[['green.png',62],['blue.png',62],['green.png',62],['blue.png',62],['red.png',100]]);
assert.deepEqual(reviewSteps(data,review).filter(s => s.boundary).map(s => s.clip),[0,0,1]);
const action = structuredClone(data.actions.walk);
editFrames(action,[2,0],['blue.png','red.png']);
assert.deepEqual(action.animation.order,[0,1,0]);
assert.deepEqual(action.animation.durations_ms,[40,90,130]);
editFrames(action,[0,null,1],['blue.png','new','red.png']);
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
const settingsBase = {frame_size:[32,32],anchor:{x:0.5,y:0.5,pixels:[16,16]}};
const settingsLocal = {frame_size:[64,64],anchor:{x:0.5,y:0.5,pixels:[32,32]}};
const settingsDisk = {frame_size:[32,32],anchor:{x:0.25,y:0.5,pixels:[8,16]}};
const settingsMerge = mergeModule.mergeDraft(settingsBase,settingsLocal,settingsDisk);
assert.equal(settingsMerge.conflicts.length,0,'Derived anchor pixels cannot create a false conflict');
assert.deepEqual(mergeModule.resolveMerge(settingsMerge).anchor.pixels,[16,32],
  'Merged pixels must be derived from the resolved canvas and normalized anchor');
let layoutModule;
try {
  const layoutSource = await readFile(new URL('../tools/sprite_pipeline/web/layout.js',import.meta.url),'utf8');
  layoutModule = await import('data:text/javascript;base64,' + Buffer.from(layoutSource).toString('base64'));
} catch {}
assert.equal(typeof layoutModule?.clampPanel,'function','Adjustable panels need shared geometry');
assert.equal(layoutModule.clampPanel(900,1100,300,'left'),364,'Canvas must keep 420 px at 1100 px');
assert.equal(layoutModule.clampPanel(100,1440,300,'left'),210,'Materials keep a usable minimum');
assert.equal(layoutModule.clampPanel(900,1440,260,'right'),460,'Inspector has a readable maximum');
assert.equal(layoutModule.clampTimeline(400,500),240,'Timeline leaves enough room for canvas and controls');
assert.equal(layoutModule.savedSize('broken',260),260,'Malformed saved widths use defaults');
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
const slicingText = await (await import('node:fs/promises')).readFile(new URL('../tools/sprite_pipeline/web/slicing.js',import.meta.url),'utf8');
const slicing = await import('data:text/javascript;base64,' + Buffer.from(slicingText).toString('base64'));
assert.deepEqual(slicing.resizeRegion([10,10,30,30],'move',[100,-50],[60,60]),[40,0,60,20]);
assert.deepEqual(slicing.resizeRegion([10,10,30,30],'se',[100,100],[60,60]),[10,10,60,60]);
assert.deepEqual(slicing.resizeRegion([10,10,30,30],'nw',[50,50],[60,60]),[29,29,30,30]);
assert.deepEqual(slicing.hitRegion([[10,10,30,30]],0,[30,30],2),{index:0,handle:'se'});
assert.deepEqual(slicing.hitRegion([[10,10,30,30]],0,[20,20],2),{index:0,handle:'move'});
assert.equal(slicing.hitRegion([[10,10,30,30]],0,[40,40],2),null);
console.log('Workbench model: timing, review boundaries, display remapping and slice geometry passed.');

const adjustmentText = await readFile(new URL('../tools/sprite_pipeline/web/adjustment.js',import.meta.url),'utf8');
const adjustment = await import('data:text/javascript;base64,' + Buffer.from(adjustmentText).toString('base64'));
const ordered = [{ref:'a/001.png',duration_ms:83,frame:0},{ref:'b/000.png',duration_ms:125,frame:1},{ref:'a/001.png',duration_ms:42,frame:2}];
const previewFrames = [{ref:'a/001.png',id:'001',url:'draft-a',version:'new'}];
const adjusted = adjustment.composeAdjustmentSteps(ordered,previewFrames,[{ref:'b/000.png',url:'saved-b'}]);
assert.deepEqual(adjusted.map(step=>[step.ref,step.duration_ms,step.url]),[['a/001.png',83,'draft-a'],['b/000.png',125,'saved-b'],['a/001.png',42,'draft-a']]);
const merged = adjustment.mergePreviewFrames({frames:[{ref:'a',version:'1',url:'old'},{ref:'b',version:'3',url:'b-old'}]},
  {frames:[{ref:'a',version:'1'},{ref:'b',version:'4',url:'b-new'}]});
assert.equal(merged.frames[0].url,'old'); assert.equal(merged.frames[1].url,'b-new');
assert.throws(()=>adjustment.mergePreviewFrames({frames:[]},{frames:[{ref:'a',version:'1'}]}));
player.index=1; player.elapsed=37; player.last=200; player.playing=true;
player.updateSteps(player.steps.map((step,i)=>i===1 ? {...step,url:'/changed'} : step));
assert.equal(player.index,1); assert.equal(player.elapsed,37); assert.equal(player.playing,true);
console.log('Adjustment model: ordered repeats, cross-source frames, delta merge and uninterrupted playback passed.');
