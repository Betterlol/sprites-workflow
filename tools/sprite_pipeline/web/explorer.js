// One persistent project directory shared by every editing mode.
export function createExplorer(api) {
  const {state,$,escape,composition}=api;
  const closed=new Set();
  const folderIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 7V5h7l2 2h9v13H3z"/></svg>';
  function render() {
    const groups=[
      {key:'reference',name:'参考图',items:state.references.map(item=>({id:item.ref,name:item.file,url:item.url}))},
      {key:'source',name:'原图素材',items:state.sources.map(item=>({id:item.file,name:item.file,url:item.url}))},
      {key:'action',name:'动作列表',items:Object.entries(state.data.actions).map(([id,item])=>({id,name:item.name || id}))},
      {key:'review',name:'衔接序列',items:Object.entries(state.data.workbench?.reviews || {}).map(([id,item])=>({id,name:item.name || id}))},
    ];
    $('#project-tree').innerHTML=groups.map(group=>`<details data-folder="${group.key}" ${closed.has(group.key) ? '' : 'open'}><summary>${folderIcon}<span>${group.name}</span><small>${group.items.length}</small><button data-create="${group.key}" title="添加${group.name}" aria-label="添加${group.name}">＋</button></summary><div class="directory-children">${group.items.map(item=>{
      const selected=state.mode === group.key && state[group.key] === item.id;
      const resource=['action','review'].includes(group.key);
      return `<div class="directory-row ${selected ? 'selected' : ''}"><button data-entry="${escape(item.id)}" data-kind="${group.key}" ${resource ? 'draggable="true"' : ''} title="${escape(item.name)}">${item.url ? `<img src="${escape(item.url)}" alt="">` : '<span class="directory-file">▧</span>'}<span>${escape(item.name)}</span></button>${resource ? `<button class="directory-insert" data-insert="${escape(item.id)}" data-kind="${group.key}" title="加入当前组合" aria-label="将 ${escape(item.name)} 加入当前组合">＋</button>` : ''}</div>`;
    }).join('') || '<p class="directory-empty">暂无内容</p>'}</div></details>`).join('');
    $('#directory-project-name').textContent=state.data.project?.name || state.data.character;
    $('#project-tree').querySelectorAll('[data-folder]').forEach(details=>details.ontoggle=()=>{ if (details.open) closed.delete(details.dataset.folder); else closed.add(details.dataset.folder); });
    $('#project-tree').querySelectorAll('[data-create]').forEach(button=>button.onclick=event=>{
      event.preventDefault(); event.stopPropagation(); api.mode(button.dataset.create); $('#new-item').click();
    });
    $('#project-tree').querySelectorAll('[data-entry]').forEach(button=>{
      const kind=button.dataset.kind, ref=button.dataset.entry;
      button.onclick=()=>{
        if (kind === 'action' || kind === 'review') composition.open({kind:kind === 'action' ? 'action' : 'sequence',ref},false);
        else { state[kind]=ref; api.mode(kind,kind === 'source' ? (state.mode === 'source' ? state.sourceView : 'original') : undefined); }
      };
      if (['action','review'].includes(kind)) button.ondragstart=event=>event.dataTransfer.setData('application/x-resource',JSON.stringify({kind:kind === 'action' ? 'action' : 'sequence',ref}));
    });
    $('#project-tree').querySelectorAll('[data-insert]').forEach(button=>button.onclick=()=>composition.insert([{kind:button.dataset.kind === 'action' ? 'action' : 'sequence',ref:button.dataset.insert}]));
  }
  return {render};
}
