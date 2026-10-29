// Run manually with node tests/test_resource_deletion.mjs; not run by the agent.
import assert from 'node:assert/strict';
import {deletionImpact,detachForDeletion} from '../tools/sprite_pipeline/web/resource-deletion.js';
import {resolveResource,validateComposition} from '../tools/sprite_pipeline/web/resources.js';

const original={actions:{
  leaf:{fps:10,sprites:['walk/000.png','walk/001.png','other/000.png'],animation:{order:[2,0,1,2],durations_ms:[50,60,70,80]}},
  parent:{slots:[{id:'part',resource:{kind:'action',ref:'leaf'},start:1,end:2}],animation:{order:[1,0]}},
  independent:{sprites:['other/000.png']},
},workbench:{reviews:{
  legacy:{mode:'display',clips:[{action:'leaf',start:2,end:3}]},
  mixed:{slots:[{id:'leaf',resource:{kind:'action',ref:'leaf'}},{id:'keep',resource:{kind:'sprite',ref:'other/000.png'}}]},
}}};
const untouched=structuredClone(original);
const targets=[{kind:'sprite',ref:'walk/001.png'}];
assert.deepEqual(new Set(deletionImpact(original,targets).map(item=>`${item.kind}:${item.ref}`)),
  new Set(['action:leaf','action:parent','sequence:legacy','sequence:mixed']));
const detached=detachForDeletion(original,targets);
validateComposition(detached);
assert.deepEqual(original,untouched,'Preparing a deletion must not change the live draft');
assert.deepEqual(resolveResource(detached,'action','leaf').map(step=>step.ref),['walk/000.png','other/000.png']);
assert.deepEqual(resolveResource(detached,'action','leaf','display').map(step=>[step.ref,step.duration_ms]),
  [['other/000.png',50],['walk/000.png',60],['other/000.png',80]]);
assert.deepEqual(detached.actions.independent,original.actions.independent);
assert.equal(detached.actions.parent.slots[0].id,'part','Surviving slots retain their identity');
assert.equal(detached.actions.parent.slots[0].end,1,'Dependent ranges shrink to the surviving child');

const removedAction=detachForDeletion(original,[{kind:'action',ref:'leaf'}]);
validateComposition(removedAction);
assert(!removedAction.actions.leaf);
assert.deepEqual(removedAction.actions.parent.slots,[]);
assert.deepEqual(resolveResource(removedAction,'sequence','legacy'),[]);
assert.deepEqual(resolveResource(removedAction,'sequence','mixed').map(step=>step.ref),['other/000.png']);

const removedSource=detachForDeletion(original,[],['walk/']);
validateComposition(removedSource);
assert.deepEqual(resolveResource(removedSource,'action','leaf').map(step=>step.ref),['other/000.png']);
assert.deepEqual(original,untouched);

const inherited={defaults:{sprites:['walk/000.png','other/000.png']},actions:{idle:{fps:10}}};
const inheritedRemoved=detachForDeletion(inherited,[{kind:'sprite',ref:'walk/000.png'}]);
validateComposition(inheritedRemoved);
assert.deepEqual(resolveResource(inheritedRemoved,'action','idle').map(step=>step.ref),['other/000.png']);

const nestedDisplay={actions:{
  parent:{slots:[{id:'child',resource:{kind:'action',ref:'child'},mode:'display',start:1,end:2}],animation:{order:[1,0]}},
  child:{sprites:['a.png','b.png','c.png'],animation:{order:[2,1,0],durations_ms:[30,50,70]}},
}};
validateComposition(detachForDeletion(nestedDisplay,[{kind:'sprite',ref:'a.png'}]));
const withoutAll=detachForDeletion(nestedDisplay,[{kind:'sprite',ref:'a.png'},{kind:'sprite',ref:'b.png'},{kind:'sprite',ref:'c.png'}]);
validateComposition(withoutAll);
assert.deepEqual(resolveResource(withoutAll,'action','parent'),[]);

const sequences={actions:{use:{slots:[{id:'sequence',resource:{kind:'sequence',ref:'bridge'}}]}},
  workbench:{reviews:{bridge:{slots:[{id:'frame',resource:{kind:'sprite',ref:'a.png'}}]}}}};
const withoutSequence=detachForDeletion(sequences,[{kind:'sequence',ref:'bridge'}]);
validateComposition(withoutSequence);
assert(!withoutSequence.workbench.reviews.bridge);
assert.deepEqual(withoutSequence.actions.use.slots,[]);

const ranged={actions:{
  child:{sprites:['a.png','b.png','c.png','d.png']},
  parent:{slots:[{id:'cut',resource:{kind:'action',ref:'child'},start:1,end:2}]},
  onlyDeleted:{slots:[{id:'only',resource:{kind:'action',ref:'child'},start:0,end:0}]},
}};
const rangedRemoved=detachForDeletion(ranged,[{kind:'sprite',ref:'a.png'}]);
validateComposition(rangedRemoved);
assert.deepEqual(resolveResource(rangedRemoved,'action','parent').map(step=>step.ref),['b.png','c.png'],
  'Deleting a preceding frame must not shift a trim onto outside frames');
assert.deepEqual(rangedRemoved.actions.onlyDeleted.slots,[],
  'A trim with no surviving frames is removed instead of playing a different pose');

const inheritedDisplay={actions:{
  leaf:{sprites:['a.png','b.png','c.png','d.png'],animation:{order:[0,1]}},
  parent:{slots:[{id:'sequence',resource:{kind:'sequence',ref:'cut'},mode:'display'}]},
},workbench:{reviews:{cut:{mode:'runtime',slots:[{id:'trim',resource:{kind:'action',ref:'leaf'},start:1,end:1}]}}}};
const inheritedDisplayRemoved=detachForDeletion(inheritedDisplay,[{kind:'sprite',ref:'b.png'}]);
validateComposition(inheritedDisplayRemoved);
assert.deepEqual(resolveResource(inheritedDisplayRemoved,'action','parent'),[],
  'A sequence must also respect display mode inherited from its parent');

const timedParent={actions:{
  removed:{sprites:['a.png']},
  leaf:{slots:[{id:'a',resource:{kind:'action',ref:'removed'}},{id:'b',resource:{kind:'sprite',ref:'b.png'}}],animation:{order:[0,1]}},
  parent:{slots:[{id:'cut',resource:{kind:'action',ref:'leaf'},mode:'display',start:1,end:1}],animation:{order:[0],durations_ms:[777]}},
}};
const timedParentRemoved=detachForDeletion(timedParent,[{kind:'action',ref:'removed'}]);
validateComposition(timedParentRemoved);
assert.deepEqual(resolveResource(timedParentRemoved,'action','parent','display').map(step=>[step.ref,step.duration_ms]),[['b.png',777]],
  'A changed nested display position must preserve the authored parent hold');
console.log('Resource deletion: references, ranges, display timing, empty parents and draft isolation passed.');
