// Canvas uses one shared coordinate system. Playback never auto-fits a pose.
export class Player {
  constructor(canvas, area, onStep) {
    this.canvas = canvas;
    this.area = area;
    this.context = canvas.getContext('2d');
    this.onStep = onStep;
    this.images = new Map();
    this.steps = [];
    this.index = 0;
    this.playing = false;
    this.elapsed = 0;
    this.last = null;
    this.speed = 1;
    this.loop = true;
    this.options = {guides: true, onion: false, reference: false, zoom: 'fit', background: 'checker'};
    this.size = [640, 640];
    this.anchor = [320, 570];
    this.loadEpoch = 0;
    new ResizeObserver(() => this.resize()).observe(area);
    document.addEventListener('visibilitychange', () => { this.last = null; });
    requestAnimationFrame(t => this.tick(t));
  }
  image(url) {
    if (!url) return null;
    if (!this.images.has(url)) {
      const image = new Image();
      image.onload = () => this.draw();
      image.src = url;
      this.images.set(url, image);
      if (this.images.size > 500) this.images.delete(this.images.keys().next().value);
    }
    return this.images.get(url);
  }
  reset() {
    this.pause(); this.loadEpoch++; this.images.clear(); this.steps = [];
    this.index = 0; this.elapsed = 0; this.sourceView = null; this.idle = null; this.assets = new Map();
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }
  setProject(data, assets) {
    this.size = data.frame_size;
    this.anchor = data.anchor.pixels;
    this.assets = new Map(assets.map(a => [a.ref, a]));
    this.idle = (data.actions.idle?.sprites || [])[0];
    this.resize();
  }
  setSteps(steps, index = 0) {
    this.steps = steps;
    this.index = Math.min(Math.max(0, index), Math.max(0, steps.length - 1));
    this.elapsed = 0;
    this.last = null;
    const epoch = ++this.loadEpoch;
    this.prefetch(this.index);
    this.waitForCurrent(epoch);
    this.onStep(this.index);
    this.draw();
  }
  stepImage(index) {
    const step = this.steps[index];
    return step ? this.image(step.url || this.assets?.get(step.ref)?.url) : null;
  }
  prefetch(index) {
    for (let offset = 0; offset < Math.min(8, this.steps.length); offset++) {
      const next = index + offset;
      if (next >= this.steps.length && !this.loop) break;
      this.stepImage(next % this.steps.length);
    }
  }
  waitForCurrent(epoch) {
    const image = this.stepImage(this.index);
    this.loading = !!image && !image.complete;
    if (!this.loading) { this.last = null; this.draw(); return; }
    const ready = () => {
      if (epoch === this.loadEpoch) { this.loading = false; this.last = null; this.draw(); }
    };
    image.addEventListener('load', ready, {once: true});
    image.addEventListener('error', ready, {once: true});
  }
  seek(index) {
    this.index = Math.max(0, Math.min(index, this.steps.length - 1));
    this.elapsed = 0;
    this.last = null;
    const epoch = ++this.loadEpoch;
    this.prefetch(this.index);
    this.waitForCurrent(epoch);
    this.onStep(this.index);
    this.draw();
  }
  toggle() { this.playing = !this.playing; this.last = null; return this.playing; }
  pause() { this.playing = false; this.last = null; }
  resize() {
    const [width, height] = this.size;
    const factor = this.options.zoom === 'fit' ? Math.min((this.area.clientWidth - 64) / width, (this.area.clientHeight - 64) / height) : Number(this.options.zoom);
    this.canvas.width = width;
    this.canvas.height = height;
    this.canvas.style.width = Math.max(1, width * Math.max(.05, factor)) + 'px';
    this.canvas.style.height = Math.max(1, height * Math.max(.05, factor)) + 'px';
    this.draw();
  }
  paint(step, opacity = 1) {
    if (!step) return;
    const image = this.image(step.url || this.assets?.get(step.ref)?.url);
    if (!image?.complete || !image.naturalWidth) return;
    this.context.globalAlpha = opacity;
    // Keep stored pixels at their actual size while canvas settings are a draft.
    this.context.drawImage(image, ...(step.previewOffset || [0, 0]));
    this.context.globalAlpha = 1;
  }
  draw() {
    const ctx = this.context;
    const [width, height] = this.size;
    ctx.clearRect(0, 0, width, height);
    if (this.sourceView) {
      this.drawSource();
      return;
    }
    if (this.options.reference && this.idle) this.paint({ref: this.idle}, .22);
    if (this.options.onion && this.steps.length > 1 && this.index > 0) this.paint(this.steps[this.index - 1], .28);
    this.paint(this.steps[this.index]);
    if (this.options.guides) this.drawGuides();
  }
  drawGuides() {
    const ctx = this.context, [width, height] = this.size, [x, y] = this.anchor;
    ctx.save();
    ctx.strokeStyle = '#77cab970';
    ctx.lineWidth = Math.max(1, width / 640);
    ctx.setLineDash([6, 6]);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    ctx.setLineDash([]); ctx.strokeStyle = '#a6e7d8';
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.moveTo(x - 11, y); ctx.lineTo(x + 11, y); ctx.moveTo(x, y - 11); ctx.lineTo(x, y + 11); ctx.stroke();
    ctx.fillStyle = '#5fddc8'; ctx.font = `${Math.max(10, width / 64)}px Consolas`; ctx.fillText('锚点', x + 14, y - 9);
    ctx.restore();
  }
  drawSource() {
    const {url, boxes, selected, draftBox} = this.sourceView;
    const image = this.image(url);
    const ctx = this.context;
    if (image?.complete && image.naturalWidth) ctx.drawImage(image, 0, 0, ...this.size);
    [...boxes, ...(draftBox ? [draftBox] : [])].forEach((box, index) => {
      const active = index === selected || index === boxes.length;
      ctx.strokeStyle = active ? '#5fddc8' : '#d4e1d9';
      ctx.lineWidth = Math.max(2, this.size[0] / 400);
      ctx.fillStyle = active ? '#5fddc815' : '#d4e1d905';
      ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.fillStyle = '#5fddc8'; ctx.font = `${Math.max(12, this.size[0] / 45)}px Consolas`; ctx.fillText(String(index + 1).padStart(2, '0'), box[0] + 6, box[1] + Math.max(20, this.size[0] / 40));
    });
  }
  tick(timestamp) {
    if (this.playing && this.steps.length && !this.sourceView && !this.loading) {
      if (this.last !== null) this.elapsed += (timestamp - this.last) * this.speed;
      let changed = false, guard = 0;
      while (this.elapsed >= this.steps[this.index].duration_ms && guard++ < 10000) {
        const duration = this.steps[this.index].duration_ms;
        if (this.index + 1 >= this.steps.length && !this.loop) {
          this.playing = false; this.elapsed = 0; changed = true; break;
        }
        const nextIndex = (this.index + 1) % this.steps.length;
        const nextImage = this.stepImage(nextIndex);
        if (nextImage && !nextImage.complete) {
          this.elapsed = duration;
          this.waitForCurrentFrame(nextImage);
          break;
        }
        this.elapsed -= duration;
        this.index = nextIndex;
        this.prefetch(this.index);
        changed = true;
      }
      if (changed) { this.onStep(this.index); this.draw(); }
    }
    this.last = timestamp;
    requestAnimationFrame(t => this.tick(t));
  }
  waitForCurrentFrame(image) {
    this.loading = true;
    const epoch = this.loadEpoch;
    const ready = () => {
      if (epoch === this.loadEpoch) { this.loading = false; this.last = null; }
    };
    image.addEventListener('load', ready, {once: true});
    image.addEventListener('error', ready, {once: true});
  }
}
