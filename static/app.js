// Mobile menu toggle
const navToggle = document.querySelector('.nav__toggle');
const navLinks = document.querySelector('.nav__links');

if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const isOpen = navLinks.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });
}

// Close menu when clicking a link (mobile)
document.querySelectorAll('.nav__links a').forEach((a) => {
  a.addEventListener('click', () => {
    navLinks?.classList.remove('is-open');
    navToggle?.setAttribute('aria-expanded', 'false');
  });
});

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
  const openSelector = '[data-modal-open]';
  const closeSelector = '[data-modal-close]';

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
      const id = openBtn.getAttribute('data-modal-open');
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

    // Click on overlay closes
    const modalOverlay = e.target.classList?.contains('modal') ? e.target : null;
    if (modalOverlay && modalOverlay.classList.contains('is-open')) {
      closeModal(modalOverlay);
    }
  });

  // ESC closes any open modal
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const openModalEl = document.querySelector('.modal.is-open');
    if (openModalEl) closeModal(openModalEl);
  });
})();

// Lead form (if present) - basic handler
(function initLeadForm() {
  const form = document.querySelector('#leadForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn?.setAttribute('disabled', 'true');

    try {
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());

      const resp = await fetch('/lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) throw new Error('Request failed');

      form.reset();
      alert('Спасибо! Мы свяжемся с вами в течение рабочего дня.');
      // If form is inside modal, close it
      const modal = form.closest('.modal');
      if (modal) {
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
      }
    } catch (err) {
      console.error(err);
      alert('Не удалось отправить. Попробуйте ещё раз чуть позже.');
    } finally {
      submitBtn?.removeAttribute('disabled');
    }
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
