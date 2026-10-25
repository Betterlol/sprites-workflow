// Three-way merge for the shared pipeline draft. Arrays are indivisible edits.
const MISSING = Symbol('missing');
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const copy = value => value === MISSING ? MISSING : structuredClone(value);

function equal(left, right) {
  if (left === MISSING || right === MISSING) return left === right;
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => equal(value,right[index]));
  }
  if (plain(left) && plain(right)) {
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right,key) && equal(left[key],right[key]));
  }
  return false;
}

export const conflictKey = path => path.map(key => String(key).replaceAll('~','~0').replaceAll('/','~1')).join('/');

export function mergeDraft(base, local, disk) {
  const conflicts = [];
  function visit(before, ours, theirs, path) {
    if (equal(ours,theirs)) return copy(ours);
    if (equal(ours,before)) return copy(theirs);
    if (equal(theirs,before)) return copy(ours);
    if (plain(ours) && plain(theirs) && (before === MISSING || plain(before))) {
      const merged = Object.create(null);
      const keys = new Set([...Object.keys(before === MISSING ? {} : before),...Object.keys(ours),...Object.keys(theirs)]);
      for (const key of keys) {
        const value = visit(Object.hasOwn(before === MISSING ? {} : before,key) ? before[key] : MISSING,
          Object.hasOwn(ours,key) ? ours[key] : MISSING,
          Object.hasOwn(theirs,key) ? theirs[key] : MISSING,[...path,key]);
        if (value !== MISSING) merged[key] = value;
      }
      return merged;
    }
    conflicts.push({path,base:before === MISSING ? null : copy(before),local:ours === MISSING ? null : copy(ours),
      disk:theirs === MISSING ? null : copy(theirs),baseMissing:before === MISSING,
      localMissing:ours === MISSING,diskMissing:theirs === MISSING});
    return copy(ours);
  }
  return {merged:visit(base,local,disk,[]),conflicts};
}

export function resolveMerge(proposal, choices = {}) {
  let result = structuredClone(proposal.merged);
  for (const conflict of proposal.conflicts) {
    if (choices[conflictKey(conflict.path)] !== 'disk') continue;
    const value = conflict.diskMissing ? MISSING : copy(conflict.disk);
    if (!conflict.path.length) { result = value; continue; }
    let parent = result;
    for (const key of conflict.path.slice(0,-1)) parent = parent[key];
    const key = conflict.path.at(-1);
    if (value === MISSING) delete parent[key];
    else Object.defineProperty(parent,key,{value,configurable:true,writable:true,enumerable:true});
  }
  return result;
}
