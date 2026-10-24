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
console.log('Workbench model: timing, review boundaries and display remapping passed.');
