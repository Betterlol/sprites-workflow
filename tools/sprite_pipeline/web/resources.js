// The browser projection of domain/resources.py. No persistence or image IO.
import {clone, merge, roundMs} from './model-values.js';

export const resourceKey = resource => `${resource.kind}:${resource.ref}`;
export const resourceName = (data, resource) => resource.kind === 'sequence'
  ? data.workbench?.reviews?.[resource.ref]?.name || resource.ref : resource.ref;
export const resourceLabel = kind => ({sprite:'单帧',action:'动作',sequence:'序列'}[kind] || kind);
export const newSlot = resource => ({id:globalThis.crypto?.randomUUID?.() || `slot-${Date.now()}-${Math.random().toString(36).slice(2)}`,resource:clone(resource)});
export function ownResource(data, kind, ref) {
  return kind === 'action' ? data.actions?.[ref] : data.workbench?.reviews?.[ref];
}
export function resourceSpec(data, kind, ref) {
  const value = ownResource(data,kind,ref);
  if (!['action','sequence'].includes(kind) || !value) throw new Error(`找不到${resourceLabel(kind)}：${ref}`);
  return kind === 'action' ? merge(data.defaults,value) : value;
}
export function slotsOf(spec, kind) {
  if ('slots' in spec) {
    if (!Array.isArray(spec.slots)) throw new Error('资源槽位必须是列表');
    return spec.slots;
  }
  return kind === 'action'
    ? (spec.sprites || []).map((ref,i)=>({id:`frame-${i}`,resource:{kind:'sprite',ref}}))
    : (spec.clips || []).map((clip,i)=>({...clip,id:`clip-${i}`,resource:{kind:'action',ref:clip.action}}));
}
export function ensureSlots(data, kind, ref) {
  const own = ownResource(data,kind,ref);
  if (!own) throw new Error('请先创建动作或序列');
  if (!('slots' in own)) {
    own.slots = slotsOf(own,kind).map(slot=>clone(slot));
    delete own.sprites; delete own.clips;
  }
  own.slots.forEach((slot,index)=>{ slot.id ||= `slot-${index}`; });
  return own.slots;
}
function integer(value,label,minimum=0) {
  if (!Number.isInteger(value) || value < minimum) throw new Error(`${label} 必须是不小于 ${minimum} 的整数`);
  return value;
}
function positive(value,label) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) throw new Error(`${label} 必须是正数`);
  return value;
}
function targetValid(target) {
  if (!target || !['sprite','action','sequence'].includes(target.kind) || typeof target.ref !== 'string' || !target.ref) throw new Error('槽位必须引用单帧、动作或序列');
  if (target.kind === 'sprite') {
    if (!/\.png$/i.test(target.ref) || target.ref.startsWith('/') || /[\\:]/.test(target.ref) || target.ref.split('/').includes('..')) throw new Error(`单帧路径无效：${target.ref}`);
  } else if (!/^[A-Za-z0-9_-]+$/.test(target.ref)) throw new Error('资源 ID 无效');
}
function displayProjection(spec, base) {
  const animation = spec.animation || {}, order = animation.order || base.map((_,i)=>i);
  if (!Array.isArray(order) || !order.length) throw new Error('展示顺序不能为空');
  const explicit = ['fps','duration_ms','durations_ms'].some(key=>key in animation);
  if (animation.durations_ms && (!Array.isArray(animation.durations_ms) || animation.durations_ms.length !== order.length)) throw new Error('展示时长数量与播放步数不一致');
  const duration = animation.duration_ms ?? roundMs(1000/positive(animation.fps ?? spec.fps ?? 12,'展示 FPS'));
  return order.map((index,position)=>{
    integer(index,'展示帧序号');
    if (index >= base.length) throw new Error('展示帧序号超出组合结果');
    const ms = explicit || !('slots' in spec) ? animation.durations_ms?.[position] ?? duration : base[index].duration_ms;
    integer(ms,'展示时长',1);
    if (ms > 16777215) throw new Error('展示时长超出格式限制');
    return {...clone(base[index]),origin:[...base[index].origin,'@display',String(position)],duration_ms:ms};
  });
}
function expand(data, kind, ref, spec, mode, stack, allowEmpty) {
  if (!['runtime','display'].includes(mode)) throw new Error('播放方式无效');
  const key = `${kind}:${ref}`;
  if (stack.includes(key)) throw new Error(`循环引用：${[...stack,key].join(' → ')}`);
  if (stack.length >= 32) throw new Error('资源嵌套超过 32 层');
  stack = [...stack,key];
  const slots = slotsOf(spec,kind), ids = new Set(), result = [];
  if (slots.length > 10000) throw new Error('资源超过 10,000 个槽位');
  const defaultDuration = Math.max(1,roundMs(1000/positive(spec.fps ?? data.defaults?.fps ?? 12,'FPS')));
  slots.forEach((slot,index)=>{
    if (!slot || typeof slot !== 'object') throw new Error('槽位格式无效');
    const id = slot.id ?? `slot-${index}`;
    if (typeof id !== 'string' || !id || ids.has(id)) throw new Error('槽位 ID 必须唯一');
    ids.add(id); targetValid(slot.resource);
    const target = slot.resource, repeat = integer(slot.repeat ?? 1,'重复次数',1), speed = positive(slot.speed ?? 1,'播放速度');
    if (repeat > 100 || speed < .01 || speed > 100) throw new Error('重复次数上限为 100，速度范围为 0.01–100');
    const childMode = slot.mode ?? (kind === 'sequence' ? mode : 'runtime');
    if (!['runtime','display'].includes(childMode)) throw new Error('引用播放方式无效');
    let children;
    if (target.kind === 'sprite') {
      const ms = integer(slot.duration_ms ?? defaultDuration,'单帧时长',1);
      if (ms > 16777215) throw new Error('单帧时长超出格式限制');
      children = [{ref:target.ref,duration_ms:ms,origin:[],lineage:[]}];
    } else {
      if ('duration_ms' in slot) throw new Error('片段请通过速度或次数调整时长');
      children = expand(data,target.kind,target.ref,resourceSpec(data,target.kind,target.ref),childMode,stack,allowEmpty);
    }
    const start = integer(slot.start ?? 0,'起始步'), end = slot.end == null ? children.length-1 : integer(slot.end,'结束步');
    if (!children.length && allowEmpty) return;
    if (!(0 <= start && start <= end && end < children.length)) throw new Error(`${resourceLabel(kind)} ${ref} 第 ${index+1} 个槽位的范围应在 0–${children.length-1}`);
    for (let repetition=0; repetition<repeat; repetition++) {
      for (const child of children.slice(start,end+1)) {
        const duration_ms = Math.max(1,roundMs(child.duration_ms/speed));
        if (duration_ms > 16777215) throw new Error('展开时长超出格式限制');
        result.push({...clone(child),slot:index,slot_id:id,repetition,duration_ms,
          origin:[id,String(repetition),...child.origin],
          lineage:[{kind,ref,slot:index,slot_id:id,repetition},...child.lineage]});
        if (result.length > 10000) throw new Error('展开结果超过 10,000 帧');
      }
    }
  });
  if (!result.length) {
    if (allowEmpty) return [];
    throw new Error(`${resourceLabel(kind)} ${ref} 尚无可播放素材`);
  }
  result.forEach((step,index)=>{ step.frame=index; step.action=kind === 'action' ? ref : step.action || ref; });
  const projected = kind === 'action' && mode === 'display' ? displayProjection(spec,result) : result;
  if (kind === 'sequence') {
    let previous;
    projected.forEach(step=>{ const marker=`${step.slot}:${step.repetition}`; step.clip=step.slot; step.boundary=marker!==previous; previous=marker; });
  }
  return projected;
}
export function resolveResource(data, kind, ref, mode='runtime', {allowEmpty=true}={}) {
  return expand(data,kind,ref,resourceSpec(data,kind,ref),mode,[],allowEmpty);
}
export function resolveSequence(data, review) {
  const ref = Object.keys(data.workbench?.reviews || {}).find(key=>data.workbench.reviews[key] === review) || 'review';
  return expand(data,'sequence',ref,review,review.mode || 'runtime',[],true);
}
export function allResources(data) {
  return [
    ...Object.keys(data.actions || {}).map(ref=>({kind:'action',ref})),
    ...Object.keys(data.workbench?.reviews || {}).map(ref=>({kind:'sequence',ref})),
  ];
}
export function resourceUsers(data, target) {
  return allResources(data).filter(owner=>slotsOf(resourceSpec(data,owner.kind,owner.ref),owner.kind)
    .some(slot=>slot.resource.kind === target.kind && slot.resource.ref === target.ref));
}
export function validateComposition(data) {
  allResources(data).forEach(({kind,ref})=>{
    resolveResource(data,kind,ref);
    if (kind === 'action') resolveResource(data,kind,ref,'display');
  });
}
export function renameResource(data, kind, previous, next) {
  allResources(data).forEach(owner=>{
    const spec = ownResource(data,owner.kind,owner.ref);
    for (const slot of spec.slots || []) if (slot.resource.kind === kind && slot.resource.ref === previous) slot.resource.ref=next;
    if (kind === 'action') for (const clip of spec.clips || []) if (clip.action === previous) clip.action=next;
  });
}
export function reconcileCompositeAnimations(before, data) {
  for (const [name,spec] of Object.entries(data.actions || {})) {
    if (!spec.slots || !spec.animation?.order || !before.actions?.[name]) continue;
    const old = resolveResource(before,'action',name), next = resolveResource(data,'action',name);
    const positions = new Map(next.map((step,index)=>[JSON.stringify(step.origin),index]));
    const previous = before.actions[name].animation;
    if (!previous?.order || JSON.stringify(spec.animation) !== JSON.stringify(previous)) continue;
    const used = new Set(), order=[], durations=[];
    previous.order.forEach((index,position)=>{
      const mapped = old[index] && positions.get(JSON.stringify(old[index].origin));
      if (mapped !== undefined) { order.push(mapped); used.add(mapped); durations.push(previous.durations_ms?.[position] ?? previous.duration_ms ?? old[index].duration_ms); }
    });
    next.forEach((step,index)=>{ if (!used.has(index)) { order.push(index); durations.push(step.duration_ms); } });
    if (order.length) { spec.animation.order=order; spec.animation.durations_ms=durations; }
    else { delete spec.animation.order; delete spec.animation.durations_ms; }
  }
}
