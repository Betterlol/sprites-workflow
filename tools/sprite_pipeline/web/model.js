// Playback calculations shared by the editor and the frame-accurate canvas.
import {clone,merge,roundMs} from './model-values.js';
import {resolveResource,resolveSequence} from './resources.js';
export {clone,merge,roundMs};
export const frames = action => action?.sprites || [];

export function actionSteps(data, name, mode = 'runtime') {
  return resolveResource(data,'action',name,mode);
}
export function reviewSteps(data, review) {
  return review ? resolveSequence(data,review) : [];
}

export function reconcileReviewRanges(data) {
  // A shortened action should not leave an existing review impossible to save.
  for (const review of Object.values(data.workbench?.reviews || {})) {
    for (const clip of review.clips || []) {
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
