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
    // Preload the whole sequence before advancing the clock. Missing poses are
    // visibly flagged by the editor rather than silently skipped.
    const epoch = ++this.loadEpoch;
    const urls = [...new Set(steps.map(step => step.url || this.assets?.get(step.ref)?.url).filter(Boolean))];
    this.loading = true;
    Promise.all(urls.map(url => {
      const image = this.image(url);
      return image.complete ? Promise.resolve() : new Promise(resolve => {
        image.addEventListener('load', resolve, {once: true});
        image.addEventListener('error', resolve, {once: true});
      });
    })).then(() => { if (epoch === this.loadEpoch) { this.loading = false; this.last = null; this.draw(); } });
    this.onStep(this.index);
    this.draw();
  }
  seek(index) {
    this.index = Math.max(0, Math.min(index, this.steps.length - 1));
    this.elapsed = 0;
    this.last = null;
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
    this.context.drawImage(image, 0, 0, ...this.size);
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
    ctx.strokeStyle = '#b8e77d70';
    ctx.lineWidth = Math.max(1, width / 640);
    ctx.setLineDash([6, 6]);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    ctx.setLineDash([]); ctx.strokeStyle = '#d2f5a9';
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.moveTo(x - 11, y); ctx.lineTo(x + 11, y); ctx.moveTo(x, y - 11); ctx.lineTo(x, y + 11); ctx.stroke();
    ctx.fillStyle = '#b8e77d'; ctx.font = `${Math.max(10, width / 64)}px Consolas`; ctx.fillText('ANCHOR', x + 14, y - 9);
    ctx.restore();
  }
  drawSource() {
    const {url, boxes, selected, draftBox} = this.sourceView;
    const image = this.image(url);
    const ctx = this.context;
    if (image?.complete && image.naturalWidth) ctx.drawImage(image, 0, 0, ...this.size);
    [...boxes, ...(draftBox ? [draftBox] : [])].forEach((box, index) => {
      const active = index === selected || index === boxes.length;
      ctx.strokeStyle = active ? '#b8e77d' : '#e9ba79';
      ctx.lineWidth = Math.max(2, this.size[0] / 400);
      ctx.fillStyle = active ? '#b8e77d15' : '#e9ba7910';
      ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.fillStyle = '#b8e77d'; ctx.font = `${Math.max(12, this.size[0] / 45)}px Consolas`; ctx.fillText(String(index).padStart(3, '0'), box[0] + 6, box[1] + Math.max(20, this.size[0] / 40));
    });
  }
  tick(timestamp) {
    if (this.playing && this.steps.length && !this.sourceView && !this.loading) {
      if (this.last !== null) this.elapsed += (timestamp - this.last) * this.speed;
      let changed = false, guard = 0;
      while (this.elapsed >= this.steps[this.index].duration_ms && guard++ < 10000) {
        this.elapsed -= this.steps[this.index].duration_ms;
        if (this.index + 1 >= this.steps.length) {
          if (this.loop) this.index = 0;
          else { this.playing = false; this.elapsed = 0; changed = true; break; }
        } else this.index++;
        changed = true;
      }
      if (changed) { this.onStep(this.index); this.draw(); }
    }
    this.last = timestamp;
    requestAnimationFrame(t => this.tick(t));
  }
}
