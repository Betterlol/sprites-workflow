// Source-pixel geometry, independent of canvas zoom and frame identity.
const clamp = (value, low, high) => Math.max(low, Math.min(high, Math.round(value)));
export function resizeRegion(box, handle, delta, bounds) {
  let [x,y,right,bottom] = box;
  const [dx,dy] = delta, [width,height] = bounds;
  if (handle === 'move') {
    const shiftX = clamp(dx,-x,width-right), shiftY = clamp(dy,-y,height-bottom);
    return [x+shiftX,y+shiftY,right+shiftX,bottom+shiftY];
  }
  if (handle.includes('w')) x = clamp(x+dx,0,right-1);
  if (handle.includes('e')) right = clamp(right+dx,x+1,width);
  if (handle.includes('n')) y = clamp(y+dy,0,bottom-1);
  if (handle.includes('s')) bottom = clamp(bottom+dy,y+1,height);
  return [x,y,right,bottom];
}
export function regionHandles([x,y,right,bottom]) {
  return {nw:[x,y],n:[(x+right)/2,y],ne:[right,y],e:[right,(y+bottom)/2],
    se:[right,bottom],s:[(x+right)/2,bottom],sw:[x,bottom],w:[x,(y+bottom)/2]};
}
export function hitRegion(boxes, selected, point, tolerance) {
  const [x,y] = point;
  if (boxes[selected]) {
    for (const [handle,[hx,hy]] of Object.entries(regionHandles(boxes[selected]))) {
      if (Math.abs(x-hx)<=tolerance && Math.abs(y-hy)<=tolerance) return {index:selected,handle};
    }
  }
  const order = [selected,...boxes.map((_,i)=>i).reverse().filter(i=>i!==selected)];
  for (const index of order) {
    const box=boxes[index];
    if (box && x>=box[0] && x<=box[2] && y>=box[1] && y<=box[3]) return {index,handle:'move'};
  }
  return null;
}
export function manualExtraction(extract, regions, nextId = 0) {
  return {...extract,method:'boxes',boxes:regions.map(r=>[...r.box]),region_ids:regions.map(r=>r.id),
    identities:regions.map(r=>({file:r.id+'.png',source_box:[...r.box]})),
    next_id:Math.max(nextId,extract.next_id || 0,...regions.map(r=>Number(r.id)+1))};
}
