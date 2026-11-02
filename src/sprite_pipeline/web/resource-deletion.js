// Prepare forced deletions on a copy. Disk mutations remain in the existing API transaction.
import {clone} from './model-values.js';
import {allResources,ownResource,resourceKey,resourceSpec,resourceUsers,resolveResource,slotsOf,validateComposition} from './resources.js';

function deletionMatcher(targets,prefixes) {
  const keys=new Set(targets.map(resourceKey));
  return target=>keys.has(resourceKey(target)) || target.kind === 'sprite' && prefixes.some(prefix=>target.ref.startsWith(prefix));
}

function frameIdentity(step) {
  const origin=[];
  for (let index=0; index<step.origin.length; index++) {
    if (step.origin[index] === '@display') { index++; continue; }
    origin.push(step.origin[index]);
  }
  return JSON.stringify([step.ref,origin]);
}

function survivingPositions(before,after) {
  const positions=new Map(), consumed=new Map(), result=new Map();
  after.forEach((step,index)=>{
    const key=frameIdentity(step);
    if (!positions.has(key)) positions.set(key,[]);
    positions.get(key).push(index);
  });
  before.forEach((step,index)=>{
    const key=frameIdentity(step), occurrence=consumed.get(key) || 0;
    const mapped=positions.get(key)?.[occurrence];
    consumed.set(key,occurrence+1);
    if (mapped !== undefined) result.set(index,mapped);
  });
  return result;
}

function referencedModes(data) {
  const modes=new Map(), queue=[];
  allResources(data).forEach(owner=>{
    for (const mode of owner.kind === 'action' ? ['runtime','display'] : [resourceSpec(data,owner.kind,owner.ref).mode || 'runtime']) queue.push({...owner,mode});
  });
  for (let index=0; index<queue.length; index++) {
    const owner=queue[index], key=resourceKey(owner);
    if (!modes.has(key)) modes.set(key,new Set());
    if (modes.get(key).has(owner.mode)) continue;
    modes.get(key).add(owner.mode);
    for (const slot of slotsOf(resourceSpec(data,owner.kind,owner.ref),owner.kind)) {
      if (slot.resource.kind !== 'sprite') queue.push({...slot.resource,mode:slot.mode || (owner.kind === 'sequence' ? owner.mode : 'runtime')});
    }
  }
  return modes;
}

export function deletionImpact(data,targets,spritePrefixes=[]) {
  const matches=deletionMatcher(targets,spritePrefixes), affected=new Map();
  const queue=[...targets];
  for (const owner of allResources(data)) {
    if (slotsOf(resourceSpec(data,owner.kind,owner.ref),owner.kind).some(slot=>matches(slot.resource))) queue.push(owner);
  }
  for (let index=0; index<queue.length; index++) {
    const target=queue[index], key=resourceKey(target);
    if (affected.has(key)) continue;
    affected.set(key,target);
    queue.push(...resourceUsers(data,target));
  }
  return [...affected.values()].filter(target=>target.kind !== 'sprite' && !matches(target));
}

export function detachForDeletion(before,targets,spritePrefixes=[]) {
  const data=clone(before), matches=deletionMatcher(targets,spritePrefixes);
  const affected=deletionImpact(before,targets,spritePrefixes);
  const modes=referencedModes(before);
  const changed=new Set(affected.map(resourceKey));
  for (const target of targets) {
    if (target.kind === 'action') delete data.actions[target.ref];
    if (target.kind === 'sequence') delete data.workbench.reviews[target.ref];
  }
  // Materialize affected legacy or inherited lists as slots before removing entries,
  // so surviving frame/clip IDs do not shift when earlier entries disappear.
  for (const owner of affected) {
    const spec=ownResource(data,owner.kind,owner.ref);
    spec.slots=clone(slotsOf(resourceSpec(before,owner.kind,owner.ref),owner.kind))
      .map((slot,index)=>({...slot,id:slot.id || `slot-${index}`}))
      .filter(slot=>!matches(slot.resource));
    delete spec.sprites; delete spec.clips;
    if (owner.kind === 'action' && before.defaults?.sprites) spec.sprites=null;
  }
  const visited=new Set(), active=new Set();
  const visit=owner=>{
    const key=resourceKey(owner);
    if (!changed.has(key) || visited.has(key)) return;
    if (active.has(key)) throw new Error('循环引用：'+key);
    active.add(key);
    const spec=ownResource(data,owner.kind,owner.ref);
    for (const slot of spec.slots) if (slot.resource.kind !== 'sprite') visit(slot.resource);
    spec.slots=spec.slots.filter(slot=>{
      if (slot.resource.kind === 'sprite') return true;
      const child=slot.resource;
      const contexts=slot.mode ? [slot.mode] : owner.kind === 'sequence' ? [...modes.get(key)] : ['runtime'];
      let allowed;
      const counts=[];
      for (const mode of contexts) {
        const old=resolveResource(before,child.kind,child.ref,mode), next=resolveResource(data,child.kind,child.ref,mode);
        const positions=survivingPositions(old,next), kept=new Set();
        for (let index=slot.start || 0; index<=(slot.end ?? old.length-1); index++) {
          if (positions.has(index)) kept.add(positions.get(index));
        }
        allowed=allowed ? new Set([...allowed].filter(index=>kept.has(index))) : kept;
        counts.push(next.length);
      }
      if (!allowed?.size) return false;
      // One authored range must remain valid in every inherited playback mode.
      // Keep its longest surviving contiguous run; never substitute an outside frame.
      const indexes=[...allowed].sort((a,b)=>a-b);
      let first=indexes[0], last=first, start=first, end=first;
      for (const index of indexes.slice(1)) {
        if (index !== last+1) first=index;
        last=index;
        if (last-first > end-start) { start=first; end=last; }
      }
      slot.start=start;
      slot.end=slot.end == null && counts.every(count=>count === end+1) ? null : end;
      return true;
    });
    if (owner.kind === 'action') {
      const previous=resourceSpec(before,owner.kind,owner.ref).animation;
      if (previous && (previous.order || previous.durations_ms)) {
        const old=resolveResource(before,'action',owner.ref), next=resolveResource(data,'action',owner.ref);
        const positions=survivingPositions(old,next), mappedNext=new Set(positions.values()), order=[], durations=[];
        (previous.order || old.map((_,index)=>index)).forEach((index,position)=>{
          const mapped=positions.get(index);
          if (mapped !== undefined) { order.push(mapped); durations.push(previous.durations_ms?.[position] ?? old[index].duration_ms); }
        });
        next.forEach((step,index)=>{
          if (!mappedNext.has(index)) { order.push(index); durations.push(step.duration_ms); }
        });
        // If the display selected only deleted frames, use the surviving runtime order.
        spec.animation={...clone(previous),order:order.length ? order : next.map((_,index)=>index)};
        if (previous.durations_ms) spec.animation.durations_ms=order.length ? durations : next.map(step=>step.duration_ms);
      }
    }
    active.delete(key); visited.add(key);
  };
  affected.forEach(visit);
  validateComposition(data);
  return data;
}
