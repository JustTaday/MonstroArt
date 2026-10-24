(() => {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mascots = [...document.querySelectorAll('[data-mascot]')];

  // The original Figma SVGs stay in place. We cover ONLY their existing eye
  // areas with matching white circles and move the pupil inside those circles;
  // no extra eyes are added and the mascot bodies never move.
  const eyeSpecs = {
    'mascot-pink': { eyes: [{ x: 53.50, y: 28.30, size: 31.25, pupil: 14.69 }] },
    'mascot-smile': { eyes: [
      { x: 38.90, y: 5.12, size: 15.40, pupil: 7.24 },
      { x: 54.57, y: 4.49, size: 15.40, pupil: 7.24 }
    ] },
    'mascot-fluff': { eyes: [
      { x: 40.34, y: 21.29, size: 21.51, pupil: 10.11 },
      { x: 65.25, y: 20.46, size: 21.51, pupil: 10.11 }
    ] },
    'mascot-round': { eyes: [
      { x: 37.15, y: 26.85, size: 23.83, pupil: 11.20 },
      { x: 64.82, y: 26.85, size: 23.83, pupil: 11.20 }
    ] }
  };

  function mascotKind(el) {
    const names = [...el.classList];
    if (names.some(n => n.includes('smile'))) return 'mascot-smile';
    if (names.some(n => n.includes('fluff'))) return 'mascot-fluff';
    if (names.some(n => n.includes('round'))) return 'mascot-round';
    if (names.some(n => n.includes('pink'))) return 'mascot-pink';
    return null;
  }

  const trackedEyes = [];
  mascots.forEach((mascot, index) => {
    const kind = mascotKind(mascot);
    const spec = eyeSpecs[kind];
    mascot.style.setProperty('--mascot-delay', `${Math.min(index, 4) * 90}ms`);
    mascot.setAttribute('aria-pressed', 'false');
    if (spec) {
      mascot.classList.add('has-tracking-eyes');
      const eyeLayer = document.createElement('span');
      eyeLayer.className = 'eye-tracking-layer';
      eyeLayer.setAttribute('aria-hidden', 'true');
      spec.eyes.forEach((eye, eyeIndex) => {
        const white = document.createElement('span');
        white.className = 'tracked-eye';
        white.style.left = `${eye.x}%`;
        white.style.top = `${eye.y}%`;
        white.style.width = `${eye.size}%`;
        white.style.setProperty('--pupil-size', `${eye.pupil / eye.size * 100}%`);
        white.dataset.eyeIndex = String(eyeIndex);
        const pupil = document.createElement('span');
        pupil.className = 'tracked-pupil';
        white.appendChild(pupil);
        eyeLayer.appendChild(white);
        trackedEyes.push({ mascot, eye: white, pupil, baseX: eye.x, baseY: eye.y, eyeIndex });
      });
      mascot.appendChild(eyeLayer);
    }

    mascot.addEventListener('pointerenter', () => {
      if (prefersReduced) return;
      mascot.classList.add('mascot-hovered');
    });
    mascot.addEventListener('pointerleave', () => mascot.classList.remove('mascot-hovered'));
    mascot.addEventListener('click', () => {
      if (prefersReduced) return;
      mascot.classList.remove('mascot-react');
      // Restart the tiny eye-squish interaction without moving the character.
      void mascot.offsetWidth;
      mascot.classList.add('mascot-react');
      window.setTimeout(() => mascot.classList.remove('mascot-react'), 460);
    });
  });

  let pointerX = window.innerWidth * .5;
  let pointerY = window.innerHeight * .45;
  let rafPending = false;
  function updateEyes() {
    rafPending = false;
    trackedEyes.forEach(({ mascot, eye, pupil }) => {
      const rect = mascot.getBoundingClientRect();
      const eyeRect = eye.getBoundingClientRect();
      const cx = eyeRect.left + eyeRect.width / 2;
      const cy = eyeRect.top + eyeRect.height / 2;
      const dx = pointerX - cx;
      const dy = pointerY - cy;
      const angle = Math.atan2(dy, dx);
      const distance = Math.min(1, Math.hypot(dx, dy) / 220);
      const maxTravel = eyeRect.width * .19;
      const tx = Math.cos(angle) * maxTravel * distance;
      const ty = Math.sin(angle) * maxTravel * distance;
      pupil.style.transform = `translate(calc(-50% + ${tx}px), calc(-50% + ${ty}px))`;
    });
  }
  document.addEventListener('pointermove', event => {
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (!rafPending && !prefersReduced) {
      rafPending = true;
      requestAnimationFrame(updateEyes);
    }
  }, { passive: true });
  window.addEventListener('resize', () => { if (!prefersReduced) updateEyes(); }, { passive: true });
  if (!prefersReduced) updateEyes();

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
      ? `<div class="achievement-icon contest-entry-icon" aria-hidden="true"><span>₽</span></div><div class="achievement-content"><div class="achievement-heading"><span class="tag">ЭКОНОМИКА</span><span class="achievement-date">2026</span></div><h4>Конкурс «Юный экономист»</h4><p>Школьный этап <span class="achievement-separator">·</span> Участие подтверждено</p><div class="achievement-foot"><span class="award contest-status"><i></i> Участник</span><span class="entry-note">Результат ожидается</span></div></div>`
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
