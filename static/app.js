// Mobile menu toggle
const navToggle = document.querySelector('[data-burger]');
const navLinks = document.querySelector('[data-mobile-nav]');

if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const isOpen = navLinks.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  // Close menu when clicking any link inside
  navLinks.querySelectorAll('a').forEach((a) => {
    a.addEventListener('click', () => {
      navLinks.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

// Smooth scroll for anchor links (if any remain)
document.querySelectorAll('a[href^="#"]').forEach((a) => {
  a.addEventListener('click', (e) => {
    const href = a.getAttribute('href');
    if (!href || href === '#') return;
    const target = document.querySelector(href);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

// Universal modal logic (event delegation + focus trap)
(function initModalDelegation() {
  const openSelector = '[data-open-modal]';
  const closeSelector = '[data-close-modal]';
  const focusableSelector =
    'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

  let activeModal = null;
  let lastActiveElement = null;

  function getFocusable(modal) {
    if (!modal) return [];
    return Array.from(modal.querySelectorAll(focusableSelector)).filter(
      (el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true'
    );
  }

  function focusFirst(modal) {
    const focusable = getFocusable(modal);
    const panel = modal ? modal.querySelector('.modal__panel') : null;
    const target = focusable[0] || panel || modal;
    if (target && typeof target.focus === 'function') {
      target.focus({ preventScroll: true });
    }
  }

  function setWorkModalData(trigger) {
    const modal = document.getElementById('workModal');
    if (!modal || !trigger) return;

    const title = trigger.getAttribute('data-work-title') || 'Проект';
    const tag = trigger.getAttribute('data-work-tag') || '';
    const dur = trigger.getAttribute('data-work-dur') || '';
    const note = trigger.getAttribute('data-work-note') || '';
    const videoSrc = trigger.getAttribute('data-work-video') || '';
    const poster = trigger.getAttribute('data-work-poster') || 'static/assets/placeholder.svg';

    const titleEl = modal.querySelector('#workTitle');
    const tagEl = modal.querySelector('[data-work-tag]');
    const durEl = modal.querySelector('[data-work-dur]');
    const noteEl = modal.querySelector('[data-work-note]');
    const videoEl = modal.querySelector('.workModal__video');
    const fallbackEl = modal.querySelector('[data-work-fallback]');

    if (titleEl) titleEl.textContent = title;
    if (tagEl) tagEl.textContent = tag;
    if (durEl) durEl.textContent = dur;
    if (noteEl) noteEl.textContent = note;

    if (videoEl) {
      videoEl.pause();
      if (videoSrc) {
        videoEl.src = videoSrc;
        videoEl.controls = true;
      } else {
        videoEl.removeAttribute('src');
        videoEl.controls = false;
      }
      videoEl.setAttribute('poster', poster);
      videoEl.load();
    }

    if (fallbackEl) {
      fallbackEl.hidden = Boolean(videoSrc);
    }
  }

  function resetWorkModal(modal) {
    if (!modal || modal.id !== 'workModal') return;
    const videoEl = modal.querySelector('.workModal__video');
    const fallbackEl = modal.querySelector('[data-work-fallback]');
    if (videoEl) {
      videoEl.pause();
      videoEl.removeAttribute('src');
      videoEl.controls = false;
      videoEl.load();
    }
    if (fallbackEl) fallbackEl.hidden = false;
  }

  function openModal(id, opener) {
    const modal = document.getElementById(id);
    if (!modal) return;

    const previousModal = activeModal;
    if (previousModal && previousModal !== modal) {
      closeModal(previousModal, { restoreFocus: false });
    }

    const openerInsidePrevious =
      previousModal && opener && previousModal.contains(opener);
    if (!openerInsidePrevious) {
      lastActiveElement = opener || document.activeElement;
    }
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    activeModal = modal;
    focusFirst(modal);
  }

  function closeModal(modal, { restoreFocus = true } = {}) {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    resetWorkModal(modal);

    if (restoreFocus && lastActiveElement && typeof lastActiveElement.focus === 'function') {
      lastActiveElement.focus({ preventScroll: true });
    }

    if (activeModal === modal) activeModal = null;
    if (restoreFocus) lastActiveElement = null;
  }

  document.addEventListener('click', (e) => {
    const openBtn = e.target.closest(openSelector);
    if (openBtn) {
      e.preventDefault();
      const id = openBtn.getAttribute('data-open-modal');
      if (id === 'workModal') setWorkModalData(openBtn);
      if (id) openModal(id, openBtn);
      return;
    }

    const closeBtn = e.target.closest(closeSelector);
    if (closeBtn) {
      e.preventDefault();
      const modal = closeBtn.closest('.modal');
      closeModal(modal);
      return;
    }
  });

  // ESC closes any open modal + focus trap
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (activeModal) closeModal(activeModal);
      return;
    }

    if (e.key !== 'Tab' || !activeModal) return;
    const focusable = getFocusable(activeModal);
    if (!focusable.length) {
      e.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
      return;
    }
    if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });
})();

// Lead form (static mode)
(function initLeadForm() {
  const form = document.querySelector('#leadForm');
  if (!form) return;

  const isStatic = form.dataset.static === '1';
  if (!isStatic) return;

  const statusEl = form.querySelector('.form__status');

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (statusEl) {
      statusEl.textContent =
        'Форма временно отключена. Напишите в Telegram или на email — контакты ниже.';
    }
  });
})();

// Work filter tabs
(function initWorkFilters() {
  const tabs = Array.from(document.querySelectorAll('.tab[data-filter]'));
  const cards = Array.from(document.querySelectorAll('.workCard[data-cat]'));
  if (!tabs.length || !cards.length) return;

  function setActive(tab) {
    tabs.forEach((t) => t.classList.toggle('is-active', t === tab));
  }

  function applyFilter(key) {
    cards.forEach((card) => {
      const show = key === 'all' || card.dataset.cat === key;
      card.style.display = show ? '' : 'none';
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const key = tab.dataset.filter || 'all';
      setActive(tab);
      applyFilter(key);
    });
  });
})();

// Play hero video only when visible
(function initPlayWhenVisibleVideos() {
  const videos = Array.from(document.querySelectorAll('video[data-play-when-visible="1"]'));
  if (!videos.length) return;

  const supportsIO = 'IntersectionObserver' in window;

  const ensureLoad = (video) => {
    if (video.dataset.pwvLoaded === '1') return;
    // Don't download the whole file until we actually need it.
    try {
      video.preload = 'auto';
      video.load();
    } catch (e) {}
    video.dataset.pwvLoaded = '1';
  };

  const safePlay = (video) => {
    // Autoplay works on most browsers only if muted & playsinline are set as *properties* too.
    video.muted = true;
    video.playsInline = true;

    ensureLoad(video);

    const p = video.play();
    if (p && typeof p.catch === 'function') {
      p.catch(() => {
        // Some mobile browsers (or data-saver modes) may block autoplay.
        // In that case we just keep the poster visible (video stays paused).
      });
    }
  };

  const safePause = (video) => {
    try {
      if (!video.paused) video.pause();
    } catch (e) {}
  };

  const isMostlyVisible = (el) => {
    const r = el.getBoundingClientRect();
    const vh = window.innerHeight || document.documentElement.clientHeight;
    const visibleH = Math.min(r.bottom, vh) - Math.max(r.top, 0);
    return visibleH > 0 && (visibleH / Math.min(r.height, vh)) > 0.35;
  };

  // Pause all videos when tab goes to background
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) videos.forEach(safePause);
    else videos.forEach((v) => {
      if (isMostlyVisible(v)) safePlay(v);
    });
  });

  // iOS sometimes needs a user interaction at least once after restore from bfcache
  window.addEventListener('pagehide', () => videos.forEach(safePause));
  window.addEventListener('pageshow', () =>
    videos.forEach((v) => {
      if (isMostlyVisible(v)) safePlay(v);
    })
  );

  if (!supportsIO) {
    // Fallback: just play immediately (best effort)
    videos.forEach(safePlay);
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const video = entry.target;
        if (entry.isIntersecting && entry.intersectionRatio >= 0.35) {
          safePlay(video);
        } else {
          safePause(video);
        }
      }
    },
    {
      root: null,
      threshold: [0, 0.35, 0.6, 1],
      rootMargin: '100px 0px 100px 0px', // start a bit earlier to avoid visible "loading" delay
    }
  );

  videos.forEach((v) => io.observe(v));
})();

// Reveal on scroll
(function initReveals() {
  const items = Array.from(document.querySelectorAll('[data-reveal]'));
  if (!items.length) return;

  const prefersReduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReduce || !('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('is-visible'));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      }
    },
    { root: null, threshold: 0.2, rootMargin: '0px 0px -10% 0px' }
  );

  items.forEach((el) => io.observe(el));
})();

// Typing effect for hero
(function initTyping() {
  const el = document.querySelector('.typed[data-typed]');
  if (!el) return;

  let items = [];
  try {
    items = JSON.parse(el.getAttribute('data-typed') || '[]');
  } catch (e) {
    items = [];
  }
  if (!items.length) return;

  let wordIndex = 0;
  let charIndex = 0;
  let deleting = false;

  const typeSpeed = 70;
  const deleteSpeed = 45;
  const holdDelay = 1100;

  const tick = () => {
    const word = items[wordIndex] || '';
    if (!deleting) {
      charIndex += 1;
      el.textContent = word.slice(0, charIndex);
      if (charIndex >= word.length) {
        deleting = true;
        setTimeout(tick, holdDelay);
        return;
      }
      setTimeout(tick, typeSpeed);
      return;
    }

    charIndex -= 1;
    el.textContent = word.slice(0, charIndex);
    if (charIndex <= 0) {
      deleting = false;
      wordIndex = (wordIndex + 1) % items.length;
      setTimeout(tick, 260);
      return;
    }
    setTimeout(tick, deleteSpeed);
  };

  tick();
})();
