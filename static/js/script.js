(() => {
  // Inline each local SVG so we can animate the actual pupil circles inside their clip paths.
  const pupilTargets = new WeakMap();
  async function makeMascotEyesTrack(container) {
    const image = container.matches('img') ? container : container.querySelector('img');
    if (!image || image.dataset.inlineMascot === '1') return;
    image.dataset.inlineMascot = '1';
    try {
      const response = await fetch(image.currentSrc || image.src);
      if (!response.ok) throw new Error('Mascot SVG unavailable');
      const svgText = await response.text();
      const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
      const svg = doc.documentElement;
      if (svg.localName !== 'svg' || doc.querySelector('parsererror')) throw new Error('Invalid mascot SVG');
      const pupils = [...svg.querySelectorAll('[data-pupil="true"]')];
      if (!pupils.length) return;
      // Preserve the image's layout classes and accessibility while swapping only the rendering element.
      for (const attr of [...image.attributes]) {
        if (['src','srcset','loading','decoding','fetchpriority'].includes(attr.name)) continue;
        svg.setAttribute(attr.name, attr.value);
      }
      svg.removeAttribute('width'); svg.removeAttribute('height');
      svg.style.width = '100%'; svg.style.height = '100%'; svg.style.display = 'block';
      svg.setAttribute('aria-hidden', image.getAttribute('aria-hidden') || 'true');
      const liveSvg = document.importNode(svg, true);
      const livePupils = [...liveSvg.querySelectorAll('[data-pupil="true"]')];
      livePupils.forEach(pupil => {
        pupil.dataset.baseTransform = pupil.getAttribute('transform') || '';
        pupilTargets.set(pupil, { maxX: Math.min(6, parseFloat(pupil.getAttribute('r') || '12') * .42), maxY: Math.min(5, parseFloat(pupil.getAttribute('r') || '12') * .34) });
        pupil.style.transition = 'transform 90ms ease-out';
      });
      image.replaceWith(liveSvg);
      image._inlineMascotSvg = liveSvg;
      container.dataset.eyesReady = '1';
    } catch (error) {
      // Keep the original artwork visible if local SVG loading fails; never add fake eyes.
      delete image.dataset.inlineMascot;
      console.warn('Mascot eye tracking unavailable:', error);
    }
  }
  function trackMascotEyes(container, event) {
    const svg = container.matches('svg') ? container : (container._inlineMascotSvg || container.querySelector('svg'));
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const vb = (svg.getAttribute('viewBox') || `0 0 ${rect.width} ${rect.height}`).trim().split(/[ ,]+/).map(Number);
    const [vx, vy, vw, vh] = vb;
    const x = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - .5) * 2));
    const y = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - .5) * 2));
    svg.querySelectorAll('[data-pupil="true"]').forEach(pupil => {
      const target = pupilTargets.get(pupil) || {maxX: 5, maxY: 4};
      // Use SVG-space translations; clipPaths keep each pupil safely inside its original eye.
      const tx = x * target.maxX, ty = y * target.maxY;
      const base = pupil.dataset.baseTransform || '';
      pupil.setAttribute('transform', `${base} translate(${tx.toFixed(2)} ${ty.toFixed(2)})`);
    });
  }
  function initMascotEyeTracking(selector) {
    const nodes = [...document.querySelectorAll(selector)];
    nodes.forEach(node => { makeMascotEyesTrack(node); });
    if (matchMedia('(pointer:fine)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.addEventListener('pointermove', event => nodes.forEach(node => trackMascotEyes(node, event)), {passive:true});
      document.addEventListener('pointerleave', () => nodes.forEach(node => {
        const svg = node.matches('svg') ? node : (node._inlineMascotSvg || node.querySelector('svg'));
        svg?.querySelectorAll('[data-pupil="true"]').forEach(pupil => pupil.setAttribute('transform', pupil.dataset.baseTransform || ''));
      }));
    }
  }

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mascots = [...document.querySelectorAll('[data-mascot]')];
  initMascotEyeTracking('[data-mascot]');

  // Mascots remain the untouched original Figma SVGs. Animate the complete
  // character wrapper; never paint substitute eyes or pupils over the artwork.
  const finePointer = matchMedia('(pointer:fine)').matches;
  mascots.forEach((mascot, index) => {
    mascot.style.setProperty('--mascot-delay', `${Math.min(index, 5) * 120}ms`);
    mascot.classList.add('mascot-arrive');
    window.setTimeout(() => mascot.classList.remove('mascot-arrive'), 900 + Math.min(index, 5) * 120);
    mascot.setAttribute('aria-pressed', 'false');
    mascot.addEventListener('pointerenter', () => {
      if (!prefersReduced) mascot.classList.add('mascot-curious');
    });
    mascot.addEventListener('pointerleave', () => mascot.classList.remove('mascot-curious'));
    mascot.addEventListener('click', () => {
      if (prefersReduced) return;
      mascot.classList.remove('mascot-shake');
      void mascot.offsetWidth;
      mascot.classList.add('mascot-shake');
      window.setTimeout(() => mascot.classList.remove('mascot-shake'), 720);
    });
  });

  // Occasionally the landing-page crew exchange a tiny nod, like a group
  // reacting together. No additional artwork is layered onto the SVGs.
  if (!prefersReduced && mascots.length > 1) {
    const conversationTargets = mascots.filter(m => m.classList.contains('mascot-hit') || m.classList.contains('cta-mascot'));
    let conversationIndex = 0;
    window.setInterval(() => {
      if (document.hidden || conversationTargets.length < 2) return;
      const first = conversationTargets[conversationIndex % conversationTargets.length];
      const second = conversationTargets[(conversationIndex + 1) % conversationTargets.length];
      first.classList.add('mascot-nod');
      second.classList.add('mascot-nod-soft');
      window.setTimeout(() => { first.classList.remove('mascot-nod'); second.classList.remove('mascot-nod-soft'); }, 900);
      conversationIndex = (conversationIndex + 1) % conversationTargets.length;
    }, 6200);
  }

  // A gentle whole-body lean gives the characters a shared reaction to the
  // cursor without adding any shapes on top of the original SVG artwork.
  if (finePointer && !prefersReduced) {
    document.addEventListener('pointermove', event => {
      mascots.forEach((mascot, index) => {
        if (mascot.classList.contains('mascot-shake')) return;
        const rect = mascot.getBoundingClientRect();
        const dx = (event.clientX - (rect.left + rect.width / 2)) / Math.max(rect.width, 1);
        const dy = (event.clientY - (rect.top + rect.height / 2)) / Math.max(rect.height, 1);
        mascot.style.setProperty('--lean-x', `${Math.max(-1, Math.min(1, dx)) * (index % 2 ? -2.5 : 2.5)}deg`);
        mascot.style.setProperty('--lean-y', `${Math.max(-1, Math.min(1, dy)) * 2.5}px`);
      });
    }, { passive: true });
    document.addEventListener('pointerleave', () => mascots.forEach(m => {
      m.style.removeProperty('--lean-x'); m.style.removeProperty('--lean-y');
    }));
  }

  // Progressive reveal includes the hero on desktop as well as lower sections.
  if (!prefersReduced && 'IntersectionObserver' in window) {
    document.documentElement.classList.add('js-motion');
    const revealItems = [
      ...document.querySelectorAll('.hero-copy > *, .mascot-stage .mascot-hit, .hero-bottom, .portfolio .section-copy > *, .portfolio-card, .rating-section .section-heading > *, .rating-panel, .contests .section-heading > *, .contest-card, .centered-button, .how-section .section-heading > *, .role-card, .steps > div, .final-cta .cta-copy > *, .cta-mascots .cta-mascot, .footer-main > *, .footer-bottom > *')
    ];
    revealItems.forEach((el, i) => {
      el.dataset.reveal = '';
      el.style.setProperty('--reveal-delay', `${Math.min(i % 5, 4) * 75}ms`);
    });
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    }), { threshold: 0.08, rootMargin: '0px 0px -32px 0px' });
    revealItems.forEach(el => observer.observe(el));
  }

  document.querySelectorAll('[data-tab]').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(t => {
      const active = t === tab;
      t.classList.toggle('active', active);
      t.setAttribute('aria-selected', String(active));
    });
    const detail = document.querySelector('#portfolio-detail');
    if (!detail) return;
    detail.setAttribute('aria-labelledby', tab.dataset.tab === 'activity' ? 'tab-activity' : 'tab-achievements');
    detail.classList.toggle('contest-entry', tab.dataset.tab === 'activity');
    detail.innerHTML = tab.dataset.tab === 'activity'
      ? `<div class="achievement-icon contest-entry-icon" aria-hidden="true"><span>₽</span></div><div class="achievement-content"><div class="achievement-heading"><span class="tag">ЭКОНОМИКА</span><span class="achievement-date">2026</span></div><h4>Конкурс "Юный экономист"</h4><p>Школьный этап <span class="achievement-separator">·</span> Участие подтверждено</p><div class="achievement-foot"><span class="award contest-status"><i></i> Участник</span><span class="entry-note">Результат ожидается</span></div></div>`
      : `<div class="achievement-icon" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none"><path d="M24 4.5 29.2 15l11.6 1.7-8.4 8.2 2 11.6L24 31l-10.4 5.5 2-11.6-8.4-8.2L18.8 15 24 4.5Z" fill="currentColor"/><circle cx="24" cy="23" r="6" fill="#fff"/></svg></div><div class="achievement-content"><div class="achievement-heading"><span class="tag">МАТЕМАТИКА</span><span class="achievement-date">18 окт. 2026</span></div><h4>Олимпиада по математике</h4><p>Муниципальный этап <span class="achievement-separator">·</span> Призёр</p><div class="achievement-foot"><span class="award"><i></i> Призёр</span><b>+80 <span>баллов</span></b></div></div>`;
  }));

  document.querySelectorAll('[data-subject]').forEach(btn => btn.addEventListener('click', () => {
    if (!btn.classList.contains('filter')) return;
    document.querySelectorAll('.filter').forEach(b => b.classList.toggle('active', b === btn));
    const subject = btn.dataset.subject;
    document.querySelectorAll('#rating-rows tr').forEach(row => { row.hidden = subject !== 'Все предметы' && row.dataset.subject !== subject; });
  }));

  const contestCards = [...document.querySelectorAll('.contest-card')];
  contestCards.forEach(card => {
    card.setAttribute('aria-pressed', 'false');
    const selectCard = () => {
      contestCards.forEach(other => {
        const selected = other === card;
        other.classList.toggle('selected', selected);
        other.setAttribute('aria-pressed', String(selected));
      });
      const heading = card.querySelector('h3');
      let notice = document.querySelector('#contest-selection');
      if (!notice) {
        notice = document.createElement('p');
        notice.id = 'contest-selection';
        notice.setAttribute('aria-live', 'polite');
        notice.className = 'contest-selection';
        document.querySelector('.contest-grid')?.insertAdjacentElement('afterend', notice);
      }
      if (notice) notice.textContent = `Выбран конкурс: ${heading ? heading.textContent : 'достижение'}`;
    };
    card.addEventListener('click', selectCard);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectCard(); } });
  });

  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.nav');
  if (toggle && nav) {
    const setMenu = open => {
      nav.classList.toggle('open', open);
      toggle.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    };
    toggle.addEventListener('click', () => setMenu(!nav.classList.contains('open')));
    nav.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMenu(false)));
    document.addEventListener('keydown', event => { if (event.key === 'Escape') setMenu(false); });
    document.addEventListener('click', event => {
      if (!nav.contains(event.target) && !toggle.contains(event.target)) setMenu(false);
    });
    window.addEventListener('resize', () => { if (window.innerWidth > 820) setMenu(false); });
  }

})();
