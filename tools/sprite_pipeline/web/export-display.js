// Display playback belongs to export configuration, outside daily editing.
export function createExportDisplay({$,state,change,toast,escape}) {
  const fields=['fps','loop','order','durations','hold'];
  function fill() {
    const animation=state.data.actions[$('#export-display-action').value]?.animation || {};
    for (const field of fields) {
      const key={durations:'durations_ms',hold:'duration_ms'}[field] || field;
      $('#export-display-'+field).value=Array.isArray(animation[key]) ? animation[key].join(', ') : animation[key] ?? '';
    }
  }
  function render() {
    const select=$('#export-display-action'), selected=select.value;
    select.innerHTML=Object.keys(state.data.actions).map(name=>`<option value="${escape(name)}">${escape(name)}</option>`).join('');
    select.value=state.data.actions[selected] ? selected : state.data.actions[state.action] ? state.action : Object.keys(state.data.actions)[0] || '';
    $('#export-display-settings').hidden=!['all','webp','gif'].includes($('#export-format').value) || !select.value;
    fill();
  }
  $('#export-display-action').onchange=fill;
  function apply() {
    const name=$('#export-display-action').value;
    if (!state.data.actions[name]) return false;
    const animation={...state.data.actions[name].animation};
    try {
      for (const field of fields) {
        const input=$('#export-display-'+field), value=input.value.trim(), key={durations:'durations_ms',hold:'duration_ms'}[field] || field;
        if (!input.checkValidity()) { input.reportValidity(); return false; }
        if (!value) { delete animation[key]; continue; }
        if (field === 'order' || field === 'durations') {
          const values=value.split(/[,，\s]+/).map(Number);
          if (!values.every(number=>Number.isInteger(number) && number >= (field === 'order' ? 0 : 1))) throw new Error('顺序填写从 0 起的整数，时长填写正整数');
          animation[key]=values;
        } else {
          const number=Number(value);
          if (!Number.isFinite(number) || (field === 'loop' && !Number.isInteger(number)) || (field === 'hold' && !Number.isInteger(number))) throw new Error('请检查展示参数');
          animation[key]=number;
        }
      }
      if (JSON.stringify(state.data.actions[name].animation || {}) === JSON.stringify(animation)) return true;
      change(()=>{ state.data.actions[name].animation=animation; });
      if (JSON.stringify(state.data.actions[name]?.animation) === JSON.stringify(animation)) toast('展示设置已加入草稿，导出使用此配置；保存工程可保留设置');
      const applied=JSON.stringify(state.data.actions[name]?.animation) === JSON.stringify(animation);
      fill(); return applied;
    } catch(error) { toast(error.message,true); return false; }
  }
  $('#export-display-apply').onclick=apply;
  $('#export-display-reset').onclick=()=>{
    const name=$('#export-display-action').value;
    if (state.data.actions[name]) change(()=>{ delete state.data.actions[name].animation; });
    fill();
  };
  return {render,apply};
}
