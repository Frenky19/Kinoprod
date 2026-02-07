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

// Universal modal logic (event delegation)
(function initModalDelegation() {
  const openSelector = '[data-open-modal]';
  const closeSelector = '[data-close-modal]';

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
  }

  document.addEventListener('click', (e) => {
    const openBtn = e.target.closest(openSelector);
    if (openBtn) {
      e.preventDefault();
      const id = openBtn.getAttribute('data-open-modal');
      if (id) openModal(id);
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

  // ESC closes any open modal
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const openModalEl = document.querySelector('.modal.is-open');
    if (openModalEl) closeModal(openModalEl);
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
