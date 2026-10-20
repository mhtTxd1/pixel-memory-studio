// Framework-independent renderer. Use separately for each partner.
export class AvatarPlayer {
  constructor(canvas, image, manifest) {
    this.canvas=canvas; this.ctx=canvas.getContext('2d'); this.image=image; this.manifest=manifest;
    canvas.width=manifest.cellWidth; canvas.height=manifest.cellHeight;
    canvas.style.imageRendering='pixelated'; this.state='idle'; this.started=performance.now();
    this.gaze=null; this.stopped=false; this.tick=this.tick.bind(this); this.tick(this.started);
  }
  play(state) {
    if (!this.manifest.animations[state]) throw new Error(`Unknown animation: ${state}`);
    this.state=state; this.started=performance.now(); this.gaze=null;
  }
  lookAt(dx,dy,deadzone=12) {
    if (Math.hypot(dx,dy)<deadzone) { this.gaze=null; return; }
    const angle=(Math.atan2(dx,-dy)*180/Math.PI+360)%360;
    this.gaze=Math.round(angle/22.5)%16;
  }
  neutral() { this.gaze=null; }
  tick(now) {
    if(this.stopped) return;
    let row,col;
    if(this.gaze!==null) ({row,column:col}=this.manifest.gaze[this.gaze]);
    else {
      const a=this.manifest.animations[this.state]; row=a.row;
      let t=(now-this.started)%a.durations.reduce((x,y)=>x+y,0); col=0;
      while(col<a.frames-1 && t>=a.durations[col]) t-=a.durations[col++];
      if(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) col=0;
    }
    const {cellWidth:w,cellHeight:h}=this.manifest;
    this.ctx.clearRect(0,0,w,h); this.ctx.imageSmoothingEnabled=false;
    this.ctx.drawImage(this.image,col*w,row*h,w,h,0,0,w,h);
    this.raf=requestAnimationFrame(this.tick);
  }
  destroy() { this.stopped=true; cancelAnimationFrame(this.raf); }
}
