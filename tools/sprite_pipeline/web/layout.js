// Limits keep the editor usable while allowing each work area to grow.
export function savedSize(raw, fallback) {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function clampPanel(desired, width, opposite, side) {
  const minimum = side === 'left' ? 210 : 250;
  const maximum = side === 'left' ? 420 : 460;
  const room = Math.max(minimum, Math.min(maximum, width - 16 - 420 - opposite));
  return Math.min(room, Math.max(minimum, Math.round(savedSize(desired, minimum))));
}

export function clampTimeline(desired, editorHeight) {
  const maximum = Math.max(110, Math.min(320, editorHeight - 260));
  return Math.min(maximum, Math.max(110, Math.round(savedSize(desired, 140))));
}
