// Playback calculations shared by the editor and the frame-accurate canvas.
export const clone = value => structuredClone(value);
export const frames = action => action?.sprites || [];
// Match Python's millisecond rounding, including 1000 / 16 == 62.5.
export const roundMs = value => {
  const floor = Math.floor(value);
  return value - floor === .5 ? floor + floor % 2 : Math.round(value);
};
export function merge(base, override) {
  const result = clone(base || {});
  for (const [key,value] of Object.entries(override || {})) {
    result[key] = value && typeof value === 'object' && !Array.isArray(value) && result[key] && typeof result[key] === 'object' && !Array.isArray(result[key])
      ? merge(result[key],value) : clone(value);
  }
  return result;
}

export function actionSteps(data, name, mode = 'runtime') {
  const action = merge(data.defaults, data.actions[name]);
  const refs = frames(action);
  if (!refs.length) return [];
  const animation = action.animation || {};
  const order = mode === 'display' ? (animation.order || refs.map((_, i) => i)) : refs.map((_, i) => i);
  const defaultDuration = Math.max(1, roundMs(1000 / (mode === 'display' ? animation.fps || action.fps || 12 : action.fps || 12)));
  return order.map((index, position) => ({
    ref: refs[index], action: name, frame: index, position,
    duration_ms: mode === 'display' ? animation.durations_ms?.[position] ?? animation.duration_ms ?? defaultDuration : defaultDuration,
  }));
}

export function reviewSteps(data, review) {
  const result = [];
  for (const [clipIndex, clip] of (review?.clips || []).entries()) {
    if (!data.actions[clip.action]) continue;
    const all = actionSteps(data, clip.action, review.mode || 'runtime');
    const end = clip.end ?? all.length - 1;
    const selected = all.slice(clip.start || 0, end + 1);
    for (let repetition = 0; repetition < (clip.repeat || 1); repetition++) {
      selected.forEach((step, position) => result.push({...step, clip: clipIndex, repetition, boundary: position === 0}));
      if (result.length > 10000) throw new Error('Review 超过 10,000 帧，请减少重复次数');
    }
  }
  return result;
}

export function reconcileReviewRanges(data) {
  // A shortened action should not leave an existing review impossible to save.
  for (const review of Object.values(data.workbench?.reviews || {})) {
    for (const clip of review.clips) {
      if (!data.actions[clip.action]) continue;
      const count = actionSteps(data,clip.action,review.mode || 'runtime').length;
      clip.start = Math.min(clip.start || 0, Math.max(0,count - 1));
      if (clip.end !== null && clip.end !== undefined) clip.end = Math.max(clip.start,Math.min(clip.end,Math.max(0,count - 1)));
      if (!count) clip.end = null;
    }
  }
}

// Preserve the independent display sequence when editing runtime frame slots.
// `slots` contains old slot indices; null entries introduce new asset references.
export function editFrames(action, slots, references, defaultFps = 12) {
  const old = frames(action);
  const animation = action.animation;
  if (animation) {
    const oldOrder = animation.order || old.map((_, i) => i);
    const remap = new Map(slots.flatMap((slot, index) => slot === null ? [] : [[slot, index]]));
    const duration = animation.duration_ms ?? Math.max(1, roundMs(1000 / (animation.fps || action.fps || defaultFps)));
    const order = [], durations = [];
    oldOrder.forEach((slot, i) => {
      if (remap.has(slot)) { order.push(remap.get(slot)); durations.push(animation.durations_ms?.[i] ?? duration); }
    });
    slots.forEach((slot, index) => { if (slot === null) { order.push(index); durations.push(duration); } });
    if (order.length) {
      animation.order = order;
      animation.durations_ms = durations;
    } else {
      delete animation.order;
      delete animation.durations_ms;
    }
  }
  action.sprites = references.length ? references : null;
}

export function defaultReviews(data) {
  const reviews = {};
  if (['jump', 'land', 'idle'].every(name => data.actions[name])) {
    reviews.jump_land_idle = {name: '跳跃 → 落地 → 待机', mode: 'runtime', loop: true,
      clips: ['jump', 'land', 'idle'].map(action => ({action, repeat: action === 'idle' ? 2 : 1, start: 0, end: null}))};
  }
  if (['idle', 'attack'].every(name => data.actions[name])) {
    reviews.idle_attack_idle = {name: '待机 → 攻击 → 待机', mode: 'runtime', loop: true,
      clips: ['idle', 'attack', 'idle'].map(action => ({action, repeat: action === 'idle' ? 2 : 1, start: 0, end: null}))};
  }
  return reviews;
}
