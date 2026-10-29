// Added for later verification; do not run while the user is testing the app.
import assert from 'node:assert/strict';
import {sourceMaterialStatus,summarizeMaterials} from '../tools/sprite_pipeline/web/material-status.js';

const saved = {
  frame_size:[16,16],anchor:{pixels:[8,16],x:.5,y:1},
  defaults:{process:{mode:'anchor',offset:[0,0]},fps:12},
  sources:{'sheet.png':{extract:{method:'image'},process:{scale:1}}},
  actions:{idle:{sprites:['sheet/000.png']}},
};
const source = {file:'sheet.png',count:1,stale:false,
  material_status:{key:'synced',label:'已同步',reason:'处理记录匹配。',pending:false}};
const evaluate = draft => sourceMaterialStatus(source,draft,saved);
assert.equal(evaluate(structuredClone(saved)).key,'synced');
const process = structuredClone(saved);
process.sources['sheet.png'].process.scale_x = 1.2;
assert.equal(evaluate(process).key,'pending');
assert.match(evaluate(process).reason,/处理规则/);
const extract = structuredClone(saved);
extract.sources['sheet.png'].extract.method = 'boxes';
assert.match(evaluate(extract).reason,/切割规则/);
const canvas = structuredClone(saved);
canvas.anchor.pixels[0] = 9;
assert.match(evaluate(canvas).reason,/画布或锚点/);
const identities = structuredClone(saved);
identities.sources['sheet.png'].extract.identities = [{file:'000.png',source_box:[0,0,4,4]}];
identities.sources['sheet.png'].extract.next_id = 5;
assert.equal(evaluate(identities).key,'synced');
const composition = structuredClone(saved);
composition.defaults.fps = 20;
composition.actions.idle = {slots:[],animation:{order:[]}};
composition.workbench = {reviews:{cut:{slots:[]}}};
assert.equal(evaluate(composition).key,'synced');
const defaults = structuredClone(saved);
defaults.defaults.process.scale = 2;
assert.equal(evaluate(defaults).key,'synced','Local scale overrides a changed default scale');
defaults.defaults.process.offset = [1,0];
assert.equal(evaluate(defaults).key,'pending','An inherited default offset changes material processing');
const reordered = structuredClone(saved);
reordered.anchor = {y:1,x:.5,pixels:[8,16]};
assert.equal(evaluate(reordered).key,'synced','Object key order is not a recipe change');
const unprocessed = {...source,count:0,material_status:{key:'unprocessed',reason:'尚无素材。'}};
assert.equal(sourceMaterialStatus(unprocessed,process,saved).key,'unprocessed');
const unknown = {...source,material_status:{key:'unknown',reason:'没有处理记录。'}};
assert.equal(sourceMaterialStatus(unknown,saved,saved).key,'unknown');
assert.equal(sourceMaterialStatus(unknown,process,saved).key,'pending');
assert.match(sourceMaterialStatus(unknown,process,saved).reason,/没有处理记录/);
assert.equal(sourceMaterialStatus({file:'old.png',stale:true},null,null).key,'pending');
assert.equal(sourceMaterialStatus({file:'old.png',stale:false,count:0},null,null).key,'unprocessed');
assert.equal(sourceMaterialStatus({file:'old.png',stale:false,count:1},null,null).key,'unknown');
assert.equal(sourceMaterialStatus({file:'old.png'},null,null).key,'unknown');
const summary = summarizeMaterials([source,unprocessed,unknown],saved,saved);
assert.equal(summary.items.length,3);
assert.equal(summary.pendingCount,1);
assert.equal(summary.unknownCount,1);
assert.equal(summary.items[0].source,source);
assert.deepEqual(summarizeMaterials([],saved,saved),{items:[],pendingCount:0,unknownCount:0});
assert.equal(source.material_status.key,'synced','Status calculations do not mutate snapshot evidence');
console.log('Material status model checks passed.');
