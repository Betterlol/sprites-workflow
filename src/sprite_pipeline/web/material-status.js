// Saved processing evidence plus unsaved material rules, independent of the UI.
import {merge} from './model-values.js';

const labels = {synced:'已同步',pending:'待更新',unprocessed:'未处理',unknown:'未核验'};
const status = (key,reason) => ({key,label:labels[key],reason,pending:key === 'pending' || key === 'unprocessed'});

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])]));
  }
  return value;
}
const equal = (left,right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));

function recipe(data,filename) {
  const defaults = data?.defaults || {};
  const local = data?.sources?.[filename] || {};
  const extract = merge(defaults.extract,local.extract);
  // Identity bookkeeping written while saving slices is not a new pixel recipe.
  delete extract.identities;
  delete extract.next_id;
  return {
    extract,
    process:merge(defaults.process,local.process),
    canvas:{frame_size:data?.frame_size,anchor:data?.anchor},
    paths:{source:data?.paths?.source || 'source',processed:data?.paths?.processed_sprites || 'processed_sprites'},
  };
}

function savedStatus(source) {
  const saved = source?.material_status;
  if (saved && Object.hasOwn(labels,saved.key)) return status(saved.key,saved.reason || '');
  if (source?.stale) return status('pending','原图或已保存规则与上次应用时不同；旧快照未提供详细原因。');
  if (source?.count === 0) return status('unprocessed','尚无处理后的素材帧，请准备素材或应用原图处理。');
  return status('unknown','旧快照未提供处理核验信息，无法确认已有素材是否同步。');
}

export function sourceMaterialStatus(source,data,savedData) {
  const saved = savedStatus(source);
  if (!data || !savedData || !source?.file) return saved;
  const current = recipe(data,source.file), baseline = recipe(savedData,source.file);
  const changed = [];
  if (!equal(current.extract,baseline.extract)) changed.push('切割规则');
  if (!equal(current.process,baseline.process)) changed.push('处理规则');
  if (!equal(current.canvas,baseline.canvas)) changed.push('画布或锚点');
  if (!equal(current.paths,baseline.paths)) changed.push('素材目录');
  if (!changed.length) return saved;
  const reason = `当前草稿的${changed.join('、')}有变化，尚未应用到素材。`;
  if (saved.key === 'synced') return status('pending',reason);
  return status(saved.key === 'unprocessed' ? 'unprocessed' : 'pending',`${saved.reason} ${reason}`);
}

export function summarizeMaterials(sources,data,savedData) {
  const items = (sources || []).map(source => ({source,status:sourceMaterialStatus(source,data,savedData)}));
  return {
    items,
    pendingCount:items.filter(item => item.status.pending).length,
    unknownCount:items.filter(item => item.status.key === 'unknown').length,
  };
}
