// Resource library and slot editing share one controller for actions and sequences.
import {clone,merge} from './model-values.js';
import {allResources,ensureSlots,newSlot,ownResource,resourceKey,resourceLabel,resourceName,resourceSpec,resourceUsers,resolveResource,slotsOf} from './resources.js';

const parseKey = key => ({kind:key.slice(0,key.indexOf(':')),ref:key.slice(key.indexOf(':')+1)});
export function createCompositionUI(api) {
  const {state,$,escape,player,confirm} = api;
  const expanded = new Set(), trail = [];
  let projectId;
  const isEditing = () => ['action','review'].includes(state.mode);
  const owner = () => state.mode === 'action' ? {kind:'action',ref:state.action} : state.mode === 'review' ? {kind:'sequence',ref:state.review} : null;
  const current = () => { const target=owner(); return target?.ref ? ownResource(state.data,target.kind,target.ref) : null; };
  const selected = () => state.mode === 'action' ? state.slot || 0 : state.clip || 0;
  const selectIndex = index => { if (state.mode === 'action') state.slot=index; else state.clip=index; };
  const slots = () => { const target=owner(); return current() ? slotsOf(current(),target.kind) : []; };
  const writable = () => { const target=owner(); return ensureSlots(state.data,target.kind,target.ref); };
  const targetSteps = target => target.kind === 'sprite' ? [{ref:target.ref}] : resolveResource(state.data,target.kind,target.ref,target.kind === 'sequence' ? ownResource(state.data,target.kind,target.ref)?.mode || 'runtime' : 'runtime');
  const number = (id,value,attrs='') => `<input id="${id}" type="number" value="${value ?? ''}" ${attrs}>`;
  const label = (name,html) => `<label class="field">${name}${html}</label>`;
  const section = (name,html) => `<section class="inspector-section"><h3>${name}</h3>${html}</section>`;
  const total = steps => steps.reduce((sum,step)=>sum+(step.duration_ms || 0),0);
  const title = target => resourceName(state.data,target);

  function catalog() {
    const images=state.assets.map(image=>({...image,kind:'sprite',name:image.ref,count:1,resource:{kind:'sprite',ref:image.ref}}));
    const clips=allResources(state.data).map(resource=>{
      try {
        const steps=targetSteps(resource);
        return {kind:resource.kind,ref:resource.ref,resource,name:title(resource),count:steps.length,duration:total(steps),url:api.asset(steps[0]?.ref)?.url};
      } catch (error) { return {kind:resource.kind,ref:resource.ref,resource,name:title(resource),count:0,duration:0,error:error.message}; }
    });
    return [...images,...clips];
  }
  function visible() {
    const search=$('#asset-search').value.toLowerCase(), type=$('#asset-kind').value, group=$('#asset-source').value;
    return catalog().filter(item=>(!type || item.kind === type) && `${item.name} ${item.ref}`.toLowerCase().includes(search) &&
      (!group || item.kind === 'sprite' && item.ref.startsWith(group+'/')));
  }
  function selection() { return catalog().filter(item=>state.assetSelection.has(resourceKey(item.resource))); }
  function canReference(target) {
    const parent=owner();
    if (!parent?.ref || target.kind === 'sprite') return true;
    const seen=new Set();
    const visit = item => {
      if (resourceKey(item) === resourceKey(parent)) return true;
      if (item.kind === 'sprite' || seen.has(resourceKey(item))) return false;
      seen.add(resourceKey(item));
      return slotsOf(resourceSpec(state.data,item.kind,item.ref),item.kind).some(slot=>visit(slot.resource));
    };
    return !visit(target);
  }
  function renderLibrary() {
    if (projectId !== state.projectId) { projectId=state.projectId; trail.length=0; expanded.clear(); }
    const items=visible(), all=catalog(), chosen=selection();
    $('#asset-count').textContent=all.length;
    $('#asset-multiselect').checked=state.libraryMulti;
    $('#asset-selection-actions').hidden=!state.libraryMulti || !chosen.length;
    $('#asset-selection-count').textContent=`已选 ${chosen.length} 项`;
    $('#assets-add').textContent=state.mode === 'review' ? '加入序列' : '加入动作';
    $('#asset-library').innerHTML=items.map(item=>{
      const key=resourceKey(item.resource), active=state.assetSelection.has(key), blocked=isEditing() && !state.libraryMulti && !canReference(item.resource);
      const note=item.error || (blocked ? '此引用会形成循环' : item.kind === 'sprite' ? item.ref : `${item.count} 帧 · ${(item.duration/1000).toFixed(2)}s`);
      return `<div class="resource-card ${active ? 'selected' : ''}" data-kind="${item.kind}"><button class="resource-insert" data-resource="${escape(key)}" draggable="true" aria-pressed="${active}" title="${escape(note)}" ${blocked ? 'disabled' : ''}>${item.url ? `<img src="${escape(item.url)}" alt="" loading="lazy">` : '<span class="resource-placeholder">▧</span>'}<span class="resource-type">${resourceLabel(item.kind)}</span><strong>${escape(item.name)}</strong><small>${escape(item.kind === 'sprite' ? '单帧图片' : note)}</small></button><button class="resource-open text-button" data-open-resource="${escape(key)}">${item.kind === 'sprite' ? '定位原图' : '打开编辑'}</button></div>`;
    }).join('') || '<p class="hint">没有符合条件的资源</p>';
    $('#asset-library').querySelectorAll('[data-resource]').forEach(card=>{
      card.onclick=(event={})=>{
        if (state.libraryMulti || event.ctrlKey || event.metaKey || event.shiftKey) toggleSelection(card.dataset.resource,event);
        else if (isEditing()) insert([parseKey(card.dataset.resource)]);
        else open(parseKey(card.dataset.resource));
      };
      card.ondragstart=event=>event.dataTransfer.setData('application/x-resource',JSON.stringify(parseKey(card.dataset.resource)));
    });
    $('#asset-library').querySelectorAll('[data-open-resource]').forEach(button=>button.onclick=()=>open(parseKey(button.dataset.openResource)));
    api.updateSaveStatus(); renderNavigation();
  }
  function toggleSelection(key,event={}) {
    state.libraryMulti=true;
    const items=visible(), from=items.findIndex(item=>resourceKey(item.resource) === state.lastAsset), to=items.findIndex(item=>resourceKey(item.resource) === key);
    if (event.shiftKey && from>=0 && to>=0) items.slice(Math.min(from,to),Math.max(from,to)+1).forEach(item=>state.assetSelection.add(resourceKey(item.resource)));
    else if (state.assetSelection.has(key)) state.assetSelection.delete(key); else state.assetSelection.add(key);
    state.lastAsset=key; renderLibrary();
  }
  function insert(resources,at) {
    if (!current()) { api.toast('请先选择或创建一个动作、序列'); return; }
    if (resources.some(target=>!canReference(target))) { api.toast('该资源会形成循环引用',true); return; }
    try { for (const target of resources) if (!targetSteps(target).length) throw new Error('请先为所引用的组合添加素材'); }
    catch(error) { api.toast(error.message,true); return; }
    api.change(()=>{ const list=writable(), index=at ?? list.length; list.splice(index,0,...resources.map(newSlot)); selectIndex(index); state.selected=0; });
    api.showPane('canvas',true);
  }
  function open(target,remember=true) {
    const parent=owner(), previousIndex=state.selected;
    const preserveOccurrence=parent?.kind === 'action' && api.steps()[previousIndex]?.ref === target.ref;
    if (remember && isEditing() && current()) trail.push({mode:state.mode,action:state.action,review:state.review,slot:state.slot,clip:state.clip,selected:state.selected,playbackMode:state.playbackMode});
    if (target.kind === 'sprite') {
      const source=api.sourceForFrame(state.sources,target.ref);
      if (!source) { if (remember && trail.length) trail.pop(); api.toast('此帧是独立导入的图片，可在外部修改后重新导入'); return; }
      state.source=source.file;
      if (parent?.kind === 'action') { state.adjustAction=parent.ref; state.adjustPlaybackMode=state.playbackMode; }
      api.mode('source','processed');
      let steps=api.steps(), index=preserveOccurrence && state.adjustAction === parent.ref && steps[previousIndex]?.ref === target.ref
        ? previousIndex : steps.findIndex(step=>step.ref === target.ref);
      if (index < 0) { state.adjustAction=''; steps=api.steps(); index=steps.findIndex(step=>step.ref === target.ref); }
      if (index>=0) { state.selected=index; player.seek(index); }
    } else {
      state.slot=0; state.expandedLeaf=null;
      if (target.kind === 'action') { state.action=target.ref; state.playbackMode='runtime'; api.mode('action'); }
      else { state.review=target.ref; api.mode('review'); }
    }
    api.renderAll(); renderNavigation(); api.showPane('canvas',true);
  }
  function renderNavigation() {
    $('#resource-navigation').hidden=!trail.length;
    $('#resource-navigation-label').textContent=trail.length ? '正在编辑被引用的原资源；保存后所有引用同步更新' : '';
    $('#resource-back').onclick=()=>{ const previous=trail.pop(); if (!previous) return; Object.assign(state,previous); player.pause(); api.renderAll(); renderNavigation(); };
  }
  function selectedStep(index,leafIndex) {
    selectIndex(index);
    const steps=api.steps(), first=leafIndex ?? steps.findIndex(step=>step.slot === index);
    state.selected=Math.max(0,first); player.pause(); player.seek(state.selected);
    api.renderInspector(); renderTimeline(); api.onStep(player.index);
  }
  function drop(event,at) {
    event.preventDefault(); event.stopPropagation();
    const moved=event.dataTransfer.getData('application/x-composition-slot');
    if (moved) { const payload=JSON.parse(moved); if (payload.owner === resourceKey(owner())) move(payload.index,at); return; }
    const resource=event.dataTransfer.getData('application/x-resource');
    if (resource) return insert([JSON.parse(resource)],at);
    const sprite=event.dataTransfer.getData('application/x-sprite'), action=event.dataTransfer.getData('application/x-action');
    if (sprite) insert([{kind:'sprite',ref:sprite}],at); else if (action) insert([{kind:'action',ref:action}],at);
  }
  function renderTimeline() {
    const steps=api.steps(), list=slots(), timeline=$('#timeline'), scroll=timeline.scrollLeft;
    selectIndex(Math.max(0,Math.min(selected(),list.length-1)));
    timeline.classList.add('composition-timeline');
    timeline.innerHTML=list.map((slot,index)=>{
      const target=slot.resource, leaves=steps.map((step,position)=>({...step,position})).filter(step=>step.slot === index);
      const key=`${resourceKey(owner())}:${slot.id}`, unfolded=expanded.has(key), thumbnail=api.asset(leaves[0]?.ref)?.url;
      return `<div class="composition-slot"><button class="timeline-card clip ${selected() === index ? 'selected' : ''}" data-index="${index}" data-ref="${escape(leaves[0]?.ref || '')}" data-duration="${total(leaves)}" draggable="true" title="${escape(title(target))}"><span class="clip-name">${resourceLabel(target.kind)} · ${escape(title(target))}</span>${thumbnail ? `<img src="${escape(thumbnail)}" alt="">` : '<span class="slot-empty">空资源</span>'}<span class="frame-caption"><span>${String(index+1).padStart(2,'0')}</span><span>${leaves.length} 帧 · ${(total(leaves)/1000).toFixed(2)}s</span></span><small>${slot.repeat || 1} 次 · ${slot.speed || 1}×</small></button><div class="slot-tools"><button data-expand="${index}" class="text-button" aria-expanded="${unfolded}">${unfolded ? '收起' : '展开帧'}</button>${target.kind !== 'sprite' ? `<button data-open-slot="${index}" class="text-button">编辑原资源</button>` : ''}</div>${unfolded ? `<div class="slot-leaves">${leaves.map(step=>`<button data-leaf="${step.position}" data-parent="${index}" title="${escape(step.lineage.map(item=>`${resourceLabel(item.kind)} ${item.ref} / ${item.slot+1}`).join(' → '))}"><span>${step.position+1}. ${escape(step.ref)}</span><small>${step.duration_ms}ms</small></button>`).join('') || '<span class="hint">此资源暂无可播放帧</span>'}</div>` : ''}</div>`;
    }).join('') || '<div class="timeline-empty">从素材库点击或拖入单帧、动作、序列，开始组合</div>';
    timeline.scrollLeft=scroll;
    timeline.querySelectorAll('[data-index]').forEach(card=>{
      card.onclick=()=>selectedStep(Number(card.dataset.index));
      card.ondragstart=event=>event.dataTransfer.setData('application/x-composition-slot',JSON.stringify({owner:resourceKey(owner()),index:Number(card.dataset.index)}));
      card.ondragover=event=>event.preventDefault(); card.ondrop=event=>drop(event,Number(card.dataset.index));
    });
    timeline.querySelectorAll('[data-expand]').forEach(button=>button.onclick=()=>{
      const slot=list[Number(button.dataset.expand)], key=`${resourceKey(owner())}:${slot.id}`;
      if (expanded.has(key)) expanded.delete(key); else expanded.add(key); renderTimeline();
    });
    timeline.querySelectorAll('[data-open-slot]').forEach(button=>button.onclick=()=>open(list[Number(button.dataset.openSlot)].resource));
    timeline.querySelectorAll('[data-leaf]').forEach(button=>button.onclick=()=>selectedStep(Number(button.dataset.parent),Number(button.dataset.leaf)));
    timeline.ondragover=event=>event.preventDefault(); timeline.ondrop=event=>drop(event,list.length);
    $('#timeline-tools').innerHTML='<button id="duplicate-slot">重复槽位</button><button id="reverse-slots">倒序槽位</button><button id="remove-slot">移除槽位</button>';
    $('#duplicate-slot').onclick=duplicate; $('#reverse-slots').onclick=()=>api.change(()=>writable().reverse()); $('#remove-slot').onclick=remove;
    $('#timeline-help').textContent='槽位可引用任意资源 · 展开查看实际帧 · 编辑原资源会更新所有引用';
    $('#timeline-stats').textContent=`${list.length} 个槽位 / ${steps.length} 帧`;
    api.onStep(player.index);
  }
  function move(from,to) {
    if (from === to) return;
    api.change(()=>{ const list=writable(), [slot]=list.splice(from,1); const at=Math.min(to,list.length); list.splice(at,0,slot); selectIndex(at); });
  }
  function duplicate() {
    if (!slots()[selected()]) return;
    api.change(()=>{ const list=writable(), copy={...clone(list[selected()]),id:newSlot(list[selected()].resource).id}; list.splice(selected()+1,0,copy); selectIndex(selected()+1); });
  }
  function remove() {
    if (!slots()[selected()]) return;
    api.change(()=>{ writable().splice(selected(),1); selectIndex(Math.max(0,selected()-1)); state.selected=0; });
  }
  function inspector() {
    const spec=current(), parent=owner();
    if (!spec) return '<p class="hint">先新建或选择一个动作、序列，再从素材库加入资源。</p>';
    const action=parent.kind === 'action', merged=action ? merge(state.data.defaults,spec) : spec, step=api.steps()[state.selected];
    const slot=slots()[selected()], users=resourceUsers(state.data,parent);
    let html=section(action ? '动作设置' : '序列设置',
      action ? label('动作 ID',`<input id="composition-name" value="${escape(parent.ref)}">`) : label('序列名称',`<input id="composition-name" value="${escape(spec.name || parent.ref)}">`));
    html+=section('播放设置',(action ? label('单帧默认 FPS',number('composition-fps',merged.fps || 12,'min="1" max="1000" step="0.5"'))+
      label('图集列数',number('composition-columns',merged.pack?.columns || 4,'min="1" max="64"')) : '')+
      `<label class="field-inline">循环播放<input id="composition-loop" type="checkbox" ${merged.loop ? 'checked' : ''}></label>`+
      (action ? '' : '<details><summary>高级引用设置</summary>'+label('引用默认播放',`<select id="composition-mode"><option value="runtime" ${spec.mode !== 'display' ? 'selected' : ''}>游戏播放</option><option value="display" ${spec.mode === 'display' ? 'selected' : ''}>展示播放</option></select>`)+'</details>')+
      '<p class="hint">单帧使用默认 FPS。引用片段保留自身时长；每个槽位可单独调速、截取和重复。子资源的无限循环只展开一遍。</p>');
    if (slot) {
      const target=slot.resource;
      const options=catalog().filter(item=>canReference(item.resource) || resourceKey(item.resource) === resourceKey(target));
      html+=section(`槽位 ${selected()+1}`,label('引用资源',`<select id="slot-resource">${options.map(item=>`<option value="${escape(resourceKey(item.resource))}" ${resourceKey(item.resource) === resourceKey(target) ? 'selected' : ''}>${resourceLabel(item.kind)} · ${escape(item.name)}</option>`).join('')}</select>`)+
        `<div class="field-row">${label('重复次数',number('slot-repeat',slot.repeat ?? 1,'min="1" max="100"'))}${label('播放速度',number('slot-speed',slot.speed ?? 1,'min="0.01" max="100" step="0.05"'))}</div>`+
        (target.kind === 'sprite' ? label('单帧停留 ms',number('slot-duration',slot.duration_ms,'min="1" max="16777215" placeholder="继承默认 FPS"')) :
          '<details><summary>高级引用设置</summary>'+label('引用播放',`<select id="slot-mode"><option value="" ${!slot.mode ? 'selected' : ''}>继承当前资源默认</option><option value="runtime" ${slot.mode === 'runtime' ? 'selected' : ''}>游戏播放</option><option value="display" ${slot.mode === 'display' ? 'selected' : ''}>展示播放</option></select>`)+'</details>')+
        `<div class="field-row">${label('起始步（0 起）',number('slot-start',slot.start ?? 0,'min="0"'))}${label('结束步（含）',number('slot-end',slot.end,'min="0" placeholder="最后一步"'))}</div>`+
        '<p class="hint">范围作用于所选引用播放方式展开后的帧。这里的调整仅影响本次引用。</p>'+
        `<button id="slot-open" class="wide">${target.kind === 'sprite' ? '定位到原图调整' : '编辑原资源'}</button><button id="slot-remove" class="wide danger">移除此槽位</button>`);
    }
    if (step) html+=section('当前展开帧',`<span class="selected-ref">${escape(step.ref)}</span><p class="hint">${step.duration_ms} ms</p><button id="locate-source" class="wide">定位到单帧调整</button>`);
    html+=section('引用关系',`<p class="hint">${users.length ? '此资源被 '+users.map(item=>escape(title(item))).join('、')+' 引用。修改原资源会同步到这些组合。' : '此资源可以作为素材加入其他动作或序列。'}</p>`+
      `<button id="composition-delete" class="wide danger">删除${resourceLabel(parent.kind)}</button>`);
    return html;
  }
  function bindInspector() {
    const spec=current(); if (!spec) return;
    const bind=(id,operation)=>{
      const input=$('#'+id); if (!input) return;
      input.onchange=()=>{
        if (input.type === 'number' && !input.checkValidity()) { input.reportValidity(); return; }
        const value=input.type === 'checkbox' ? input.checked : input.type === 'number' ? input.value === '' ? null : Number(input.value) : input.value;
        api.change(()=>operation(value));
      };
    };
    bind('composition-name',value=>{
      const parent=owner(); if (parent.kind === 'sequence') { spec.name=value; return; }
      if (value === parent.ref) return;
      if (!/^[A-Za-z0-9_-]+$/.test(value) || state.data.actions[value]) throw new Error('动作 ID 必须唯一，使用字母、数字、下划线和短横线');
      api.renameResource(state.data,'action',parent.ref,value); state.data.actions[value]=spec; delete state.data.actions[parent.ref]; state.action=value;
    });
    bind('composition-fps',value=>{ if (value === null) delete spec.fps; else spec.fps=value; });
    bind('composition-columns',value=>{ spec.pack ||= {}; if (value === null) delete spec.pack.columns; else spec.pack.columns=value; });
    bind('composition-loop',value=>{ spec.loop=value; }); bind('composition-mode',value=>{ spec.mode=value; });
    ['runtime','display'].forEach(mode=>{ const button=$('#composition-'+mode); if (button) button.onclick=()=>{ state.playbackMode=mode; state.selected=0; player.pause(); api.renderAll(); }; });
    const mutate=operation=>{ const slot=writable()[selected()]; if (slot) operation(slot); };
    bind('slot-resource',value=>mutate(slot=>{ slot.resource=parseKey(value); delete slot.duration_ms; delete slot.mode; slot.start=0; slot.end=null; }));
    for (const [id,key] of [['slot-repeat','repeat'],['slot-speed','speed'],['slot-start','start'],['slot-end','end'],['slot-duration','duration_ms']]) {
      bind(id,value=>mutate(slot=>{ if (value === null) delete slot[key]; else slot[key]=value; }));
    }
    bind('slot-mode',value=>mutate(slot=>{ if (!value) delete slot.mode; else slot.mode=value; slot.start=0; slot.end=null; }));
    $('#slot-open')?.addEventListener('click',()=>open(slots()[selected()].resource)); $('#slot-remove')?.addEventListener('click',remove);
    bind('composition-frame-duration',value=>{
      const steps=api.steps(); steps[state.selected].duration_ms=value;
      spec.animation ||= {}; spec.animation.order=steps.map(step=>step.frame); spec.animation.durations_ms=steps.map(step=>step.duration_ms);
    });
    bind('composition-display-loop',value=>{ spec.animation ||= {}; if (value === null) delete spec.animation.loop; else spec.animation.loop=value; });
    $('#composition-reset-display')?.addEventListener('click',()=>api.change(()=>{ delete spec.animation; }));
    $('#locate-source')?.addEventListener('click',()=>{ const step=api.steps()[state.selected]; if (step) open({kind:'sprite',ref:step.ref}); });
    $('#composition-delete').onclick=()=>api.deleteSequence(state.mode);
  }
  function deleteSelected() {
    const chosen=selection(); if (!chosen.length) return;
    if (chosen.every(item=>item.kind === 'sprite')) return api.deleteMaterials('processed',chosen.map(item=>item.ref));
    if (chosen.some(item=>item.kind === 'sprite')) { api.toast('请按资源类型筛选，分别删除图片或组合',true); return; }
    const keys=new Set(chosen.map(item=>resourceKey(item.resource)));
    for (const item of chosen) {
      const used=resourceUsers(state.data,item.resource).filter(resource=>!keys.has(resourceKey(resource)));
      if (used.length) { api.toast(`${item.name} 仍被 ${used.map(title).join('、')} 引用`,true); return; }
    }
    if (!confirm(`删除 ${chosen.length} 个组合资源？素材图片会保留，可撤销；保存工程后生效。`)) return;
    api.change(()=>{ chosen.forEach(item=>{ const collection=item.kind === 'action' ? state.data.actions : state.data.workbench.reviews; delete collection[item.ref]; }); state.assetSelection.clear(); });
  }
  return {isEditing,owner,current,slots,selection,visible,renderLibrary,renderTimeline,inspector,bindInspector,insert,open,remove,duplicate,move,deleteSelected,renderNavigation,selectIndex,toggleSelection};
}
