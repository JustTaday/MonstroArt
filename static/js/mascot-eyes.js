/* MonstroArt: animate the pupils already drawn inside each original Figma SVG.
   If Figma's asset endpoint denies cross-origin fetch, the original image remains untouched. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const imgs = [...document.querySelectorAll('[data-mascot] img, .auth-monster')];
  const svgNS = 'http://www.w3.org/2000/svg';
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  async function inlineMascot(img) {
    const src = img.currentSrc || img.src;
    if (!src || img.dataset.inlineAttempted) return;
    img.dataset.inlineAttempted = '1';
    try {
      const response = await fetch(src, { mode: 'cors', cache: 'force-cache' });
      if (!response.ok) return;
      const text = await response.text();
      const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
      const original = doc.documentElement;
      if (original.nodeName.toLowerCase() !== 'svg' || doc.querySelector('parsererror')) return;
      const svg = document.importNode(original, true);
      svg.removeAttribute('width'); svg.removeAttribute('height');
      svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
      svg.style.display = 'block'; svg.style.overflow = 'visible';
      const circles = [...svg.querySelectorAll('circle, ellipse')];
      const whites = circles.filter(el => {
        const f = (el.getAttribute('fill') || getComputedStyle(el).fill || '').toLowerCase();
        return ['#fff','#ffffff','white','rgb(255, 255, 255)'].includes(f);
      });
      const pupils = circles.filter(el => {
        const f = (el.getAttribute('fill') || '').toLowerCase();
        return ['#000','#000000','#111','#111111','#171719','#1b1b1b','black','#151515'].includes(f);
      });
      const linked = [];
      for (const pupil of pupils) {
        const px = Number(pupil.getAttribute('cx') ?? pupil.getAttribute('x'));
        const py = Number(pupil.getAttribute('cy') ?? pupil.getAttribute('y'));
        const eye = whites.find(w => {
          const ex = Number(w.getAttribute('cx') ?? w.getAttribute('x'));
          const ey = Number(w.getAttribute('cy') ?? w.getAttribute('y'));
          const rx = Number(w.getAttribute('r') ?? w.getAttribute('rx') ?? 0);
          const ry = Number(w.getAttribute('r') ?? w.getAttribute('ry') ?? rx);
          return Math.abs(px-ex) < rx*.8 && Math.abs(py-ey) < ry*.8;
        });
        if (eye) linked.push({ pupil, eye, cx:px, cy:py,
          maxX:Number(eye.getAttribute('r') ?? eye.getAttribute('rx') ?? 0)*.34,
          maxY:Number(eye.getAttribute('r') ?? eye.getAttribute('ry') ?? 0)*.34 });
      }
      // Only replace the remote image if we found actual pupil elements to animate.
      if (!linked.length) return;
      const box = img.getBoundingClientRect();
      const wrapper = img.parentElement;
      svg.className.baseVal = img.getAttribute('class') || '';
      svg.classList.add('mascot-inline-svg');
      if (img.hasAttribute('style')) svg.setAttribute('style', img.getAttribute('style') + ';display:block;overflow:visible');
      svg.setAttribute('aria-hidden', 'true');
      img.replaceWith(svg);
      svg._maEyes = linked;
      svg._maBox = () => svg.getBoundingClientRect();
      svg._maMove = (clientX, clientY) => {
        const r = svg._maBox();
        const vx = ((clientX - (r.left+r.width/2)) / Math.max(r.width/2, 1));
        const vy = ((clientY - (r.top+r.height/2)) / Math.max(r.height/2, 1));
        linked.forEach(e => {
          e.pupil.setAttribute('cx', e.cx + clamp(vx,-1,1)*e.maxX);
          e.pupil.setAttribute('cy', e.cy + clamp(vy,-1,1)*e.maxY);
        });
      };
      svg._maReset = () => linked.forEach(e => { e.pupil.setAttribute('cx',e.cx); e.pupil.setAttribute('cy',e.cy); });
      svg._maWrapper = wrapper;
      if (svg.classList.contains('auth-monster')) svg.addEventListener('click', () => { if (reduce) return; svg.classList.remove('monster-shake'); void svg.getBoundingClientRect(); svg.classList.add('monster-shake'); setTimeout(() => svg.classList.remove('monster-shake'), 720); });
    } catch (_) { /* Cross-origin denied: keep the exact original SVG image. */ }
  }

  imgs.forEach(inlineMascot);
  if (!reduce) {
    document.addEventListener('pointermove', e => {
      document.querySelectorAll('.mascot-inline-svg').forEach(svg => svg._maMove?.(e.clientX, e.clientY));
    }, { passive: true });
    document.addEventListener('pointerleave', () => document.querySelectorAll('.mascot-inline-svg').forEach(svg => svg._maReset?.()));
  }
})();
