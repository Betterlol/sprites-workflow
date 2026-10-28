// Preserve action slots: duplicate refs and references to other sources are intentional.
export function sourceForFrame(sources, ref) {
  return sources.find(source=>{
    const prefix=source.file.replace(/\.[^.]+$/,'')+'/';
    return ref?.startsWith(prefix) && /^\d+\.png$/.test(ref.slice(prefix.length));
  });
}
export function composeAdjustmentSteps(steps, previews, assets, offsets={}) {
  const images=new Map(assets.map(frame=>[frame.ref,frame]));
  for (const frame of previews) images.set(frame.ref,frame);
  return steps.map(step=>({...images.get(step.ref),...step,id:step.ref.split('/').pop().replace(/\.png$/,''),
    ...(offsets[step.ref] ? {previewOffset:offsets[step.ref]} : {})}));
}
export function mergePreviewFrames(previous, result) {
  const old=new Map((previous?.frames || []).map(frame=>[frame.ref,frame]));
  return {...result,frames:result.frames.map(frame=>{
    if (frame.url) return frame;
    const cached=old.get(frame.ref);
    if (!cached?.url || !frame.version || cached.version!==frame.version) throw new Error('预览缓存已过期，请刷新预览');
    return {...frame,url:cached.url};
  })};
}
