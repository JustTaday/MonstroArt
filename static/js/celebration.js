(() => {
  const success = document.querySelector('.toast-success');
  if (!success || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  // Fire only when Flask confirms a successful login or registration.
  const canvas = document.createElement('canvas');
  canvas.className = 'celebration-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  Object.assign(canvas.style, {position:'fixed',inset:'0',width:'100%',height:'100%',pointerEvents:'none',zIndex:'100',overflow:'hidden'});
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  if (!ctx) { canvas.remove(); return; }
  let w = 0, h = 0;
  const resize = () => { w = canvas.width = window.innerWidth * devicePixelRatio; h = canvas.height = window.innerHeight * devicePixelRatio; ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); };
  resize();
  const colors = ['#ff5787','#78ced2','#329bef','#ffd166','#8f7cf6'];
  const bits = Array.from({length:115}, (_,i) => ({x:window.innerWidth*.5+(Math.random()-.5)*90,y:window.innerHeight*.58,vx:(Math.random()-.5)*9,vy:-Math.random()*10-3,g:.22+Math.random()*.16,size:4+Math.random()*5,rot:Math.random()*6.28,vr:(Math.random()-.5)*.22,color:colors[i%colors.length],life:100+Math.random()*35}));
  let frame = 0;
  const draw = () => {
    ctx.clearRect(0,0,w,h);
    bits.forEach(b => { b.x+=b.vx; b.y+=b.vy; b.vy+=b.g; b.rot+=b.vr; b.life--; ctx.save();ctx.translate(b.x,b.y);ctx.rotate(b.rot);ctx.fillStyle=b.color;ctx.fillRect(-b.size/2,-b.size/2,b.size,b.size*.68);ctx.restore(); });
    if (bits.some(b => b.life>0 && b.y<window.innerHeight+20) && frame++<180) requestAnimationFrame(draw); else canvas.remove();
  };
  requestAnimationFrame(draw);
  window.setTimeout(() => canvas.remove(), 3500);
})();
