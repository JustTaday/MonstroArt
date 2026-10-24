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
    // When password is revealed, hold pupils at a deliberate side-glance.
    // The characters stay still; only the real pupil circles move inside their SVG eyes.
    const lookingAway = document.querySelector('.mascot-scene')?.classList.contains('mascots-looking-away');
    const x = lookingAway ? -1 : Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - .5) * 2));
    const y = lookingAway ? 0 : Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - .5) * 2));
    svg.querySelectorAll('[data-pupil="true"]').forEach(pupil => {
      const target = pupilTargets.get(pupil) || {maxX: 5, maxY: 4};
      // Use SVG-space translations; clipPaths keep each pupil safely inside its original eye.
      const tx = lookingAway ? -15 : x * target.maxX, ty = y * target.maxY;
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

  const root = document.documentElement;
  const toggle = document.querySelector('.theme-toggle');
  const storedTheme = (() => { try { return localStorage.getItem('monstroart-theme'); } catch (_) { return null; } })();
  if (storedTheme === 'dark' || storedTheme === 'light') root.dataset.theme = storedTheme;
  const paintThemeButton = () => {
    if (!toggle) return;
    const dark = root.dataset.theme === 'dark';
    toggle.querySelector('.theme-icon').textContent = dark ? '☀' : '☾';
    toggle.setAttribute('aria-label', dark ? 'Включить светлую тему' : 'Включить тёмную тему');
  };
  paintThemeButton();
  toggle?.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('monstroart-theme', root.dataset.theme); } catch (_) {}
    paintThemeButton();
  });

  const scene = document.querySelector('.mascot-scene');
  const monsters = [...document.querySelectorAll('.auth-monster')];
  initMascotEyeTracking('.auth-monster');
  const form = document.querySelector('.auth-form');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Staggered spawn: the original SVGs enter as complete characters.
  monsters.forEach((monster, i) => {
    monster.style.setProperty('--spawn-delay', `${i * 130}ms`);
    monster.classList.add('monster-spawn');
    // The IMG is replaced asynchronously by an inline SVG; remove the spawn
    // class from the currently rendered element too, otherwise typing animation
    // stays blocked by :not(.monster-spawn) forever.
    window.setTimeout(() => {
      monster.classList.remove('monster-spawn');
      const live = monster._inlineMascotSvg || scene?.querySelector(`.auth-monster:nth-of-type(${i + 1})`);
      live?.classList.remove('monster-spawn');
    }, 950 + i * 130);
    monster.addEventListener('click', () => {
      if (reducedMotion) return;
      monster.classList.remove('monster-shake');
      void monster.offsetWidth;
      monster.classList.add('monster-shake');
      setTimeout(() => monster.classList.remove('monster-shake'), 720);
    });
  });

  document.querySelectorAll('.password-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input');
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
      document.body.classList.toggle('password-visible', show);
      scene?.classList.toggle('mascots-looking-away', show);
      clearTimeout(typingTimer);
      if (show) {
        scene?.classList.remove('mascots-chatting');
        setTypingShake(false);
      }
      // Immediately set a fixed side-glance, independent of the current cursor position.
      monsters.forEach(monster => {
        const svg = monster.matches('svg') ? monster : (monster._inlineMascotSvg || monster.querySelector('svg'));
        svg?.querySelectorAll('[data-pupil="true"]').forEach(pupil => {
          const target = pupilTargets.get(pupil) || {maxX: 5, maxY: 4};
          const base = pupil.dataset.baseTransform || '';
          pupil.setAttribute('transform', show ? `${base} translate(-15 0)` : base);
        });
      });
    });
  });

  // While the user types, animate the actual rendered mascot SVGs.
  // The original IMG nodes are replaced asynchronously by inline SVGs, so
  // always resolve the live elements instead of toggling classes on stale IMG nodes.
  let typingTimer;
  const getLiveMonsters = () => [...document.querySelectorAll('.mascot-scene .auth-monster')];
  const setTypingShake = enabled => {
    getLiveMonsters().forEach(monster => monster.classList.toggle('monster-typing', enabled));
  };
  // Only actual text-entry fields should trigger the mascots; checkbox/radio
  // toggles and other controls must never start the typing reaction.
  form?.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"]') .forEach(input => {
    input.addEventListener('input', () => {
      // Typing reaction is temporary and must stay off while a password is revealed.
      clearTimeout(typingTimer);
      if (document.body.classList.contains('password-visible') || !input.value) {
        scene?.classList.remove('mascots-chatting');
        setTypingShake(false);
        return;
      }
      scene?.classList.add('mascots-chatting');
      setTypingShake(true);
      typingTimer = setTimeout(() => {
        scene?.classList.remove('mascots-chatting');
        setTypingShake(false);
      }, 550);
    });
    input.addEventListener('focus', () => scene?.classList.add('mascots-attentive'));
    input.addEventListener('blur', () => scene?.classList.remove('mascots-attentive'));
  });
  document.querySelectorAll('[data-static-link]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    const isForgot = link.getAttribute('href') === '#forgot';
    window.alert(isForgot
      ? 'Восстановление пароля подключим следующим этапом. Пока обратись к администратору портала.'
      : 'Страницу условий и политики конфиденциальности добавим перед публикацией портала.');
  }));

  form?.addEventListener('submit', event => {
    if (event.submitter?.formAction?.includes('/oauth/google')) return;
    const password = form.querySelector('input[name="password"]');
    const confirm = form.querySelector('input[name="confirm_password"]');
    if (confirm && password.value !== confirm.value) {
      event.preventDefault();
      confirm.setCustomValidity('Пароли не совпадают');
      confirm.reportValidity();
      confirm.addEventListener('input', () => confirm.setCustomValidity(''), { once: true });
    }
  });

})();
