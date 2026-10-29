export const clone = value => structuredClone(value);
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
