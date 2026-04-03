// Mobile menu toggle
const navToggle = document.querySelector('[data-burger]');
const navLinks = document.querySelector('[data-mobile-nav]');
const FIRST_FRAME_TIME = 0.05;

function getVideoPreviewTime(video) {
  const duration = Number.isFinite(video.duration) ? video.duration : 0;
  if (duration <= 0) return 0;
  const explicitPreviewTime = Number.parseFloat(video.dataset.previewTime || '');
  if (Number.isFinite(explicitPreviewTime) && explicitPreviewTime >= 0) {
    return Math.min(explicitPreviewTime, Math.max(duration - 0.01, 0));
  }
  if (video.dataset.previewFrame === 'middle') {
    return Math.min(duration * 0.5, Math.max(duration - 0.01, 0));
  }
  return Math.min(FIRST_FRAME_TIME, Math.max(duration - 0.01, 0));
}

function setVideoPreviewState(video, isPreview) {
  if (!video || video.dataset.previewBlur !== '1') return;
  video.classList.toggle('is-preview-frame', isPreview);
}

function setVideoPreviewReady(video, isReady) {
  if (!video) return;
  video.classList.toggle('is-preview-ready', isReady);
}

function primeVideoPreviewFrame(video) {
  if (!video) return;
  const hasSource =
    Boolean(video.getAttribute('src')) ||
    Array.from(video.querySelectorAll('source')).some((source) =>
      Boolean(source.getAttribute('src'))
    );
  if (!hasSource) return;

  const seekToFrame = () => {
    const targetTime = getVideoPreviewTime(video);
    const finalizePreview = () => {
      setVideoPreviewState(video, true);
      setVideoPreviewReady(video, true);
    };

    try {
      video.pause();
      setVideoPreviewReady(video, false);
      if (targetTime > 0 && Math.abs(video.currentTime - targetTime) > 0.02) {
        video.addEventListener('seeked', finalizePreview, { once: true });
        video.currentTime = targetTime;
        return;
      }
      finalizePreview();
    } catch (err) {}
  };

  if (video.dataset.previewInit !== '1') {
    video.addEventListener('play', () => {
      setVideoPreviewState(video, false);
      setVideoPreviewReady(video, true);
    });
    video.addEventListener('playing', () => {
      setVideoPreviewState(video, false);
      setVideoPreviewReady(video, true);
      video.dataset.previewPlayedOnce = '1';
    });
    video.addEventListener('pause', () => setVideoPreviewState(video, true));
    video.dataset.previewInit = '1';
  }

  if (video.readyState >= 2) {
    seekToFrame();
    return;
  }

  video.addEventListener('loadeddata', seekToFrame, { once: true });
  try {
    if (video.dataset.previewTime && video.preload !== 'auto') {
      video.preload = 'auto';
    } else if (video.preload === 'none') {
      video.preload = 'metadata';
    }
    video.load();
  } catch (err) {}
}

function resetPreviewFrameBeforeFirstPlay(video) {
  if (!video || video.dataset.previewResetOnPlay !== '1') return false;
  if (video.dataset.previewPlayedOnce === '1') return false;
  try {
    video.currentTime = 0;
    return true;
  } catch (err) {
    return false;
  }
}

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
    const note = trigger.getAttribute('data-work-note') || '';
    const webmSrc = trigger.getAttribute('data-work-video-webm') || '';
    const mp4Src =
      trigger.getAttribute('data-work-video-mp4') ||
      trigger.getAttribute('data-work-video') ||
      '';
    const posterAttr = trigger.getAttribute('data-work-poster') || '';
    const poster =
      posterAttr && !posterAttr.endsWith('placeholder.svg') ? posterAttr : '';

    const titleEl = modal.querySelector('#workTitle');
    const noteEl = modal.querySelector('[data-work-note]');
    const videoEl = modal.querySelector('.workModal__video');
    const fallbackEl = modal.querySelector('[data-work-fallback]');

    if (titleEl) titleEl.textContent = title;
    if (noteEl) {
      noteEl.textContent = note;
      noteEl.hidden = !note;
    }

    const setSource = (type, src) => {
      if (!videoEl) return;
      const sourceEl = videoEl.querySelector(`source[data-work-source="${type}"]`);
      if (!sourceEl) return;
      if (src) {
        sourceEl.setAttribute('src', src);
      } else {
        sourceEl.removeAttribute('src');
      }
    };

    if (videoEl) {
      videoEl.pause();
      const hasAny = Boolean(webmSrc || mp4Src);
      if (hasAny) {
        videoEl.removeAttribute('src');
        setSource('webm', webmSrc);
        setSource('mp4', mp4Src);
        videoEl.controls = true;
      } else {
        videoEl.removeAttribute('src');
        setSource('webm', '');
        setSource('mp4', '');
        videoEl.controls = false;
      }
      if (poster) {
        videoEl.setAttribute('poster', poster);
      } else {
        videoEl.removeAttribute('poster');
      }
      videoEl.load();
      primeVideoPreviewFrame(videoEl);
    }

    if (fallbackEl) {
      fallbackEl.hidden = Boolean(webmSrc || mp4Src);
    }
  }

  function resetWorkModal(modal) {
    if (!modal || modal.id !== 'workModal') return;
    const videoEl = modal.querySelector('.workModal__video');
    const fallbackEl = modal.querySelector('[data-work-fallback]');
    const noteEl = modal.querySelector('[data-work-note]');
    if (videoEl) {
      videoEl.pause();
      videoEl.removeAttribute('src');
      const sources = videoEl.querySelectorAll('source[data-work-source]');
      sources.forEach((s) => s.removeAttribute('src'));
      videoEl.controls = false;
      videoEl.removeAttribute('poster');
      videoEl.load();
    }
    if (fallbackEl) fallbackEl.hidden = false;
    if (noteEl) {
      noteEl.textContent = '';
      noteEl.hidden = false;
    }
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
      document.querySelectorAll('video[data-hover-preview="1"]').forEach((video) => {
        try {
          video.pause();
          video.currentTime = 0;
        } catch (err) {}
      });
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

// Static forms (no backend yet)
(function initStaticForms() {
  const forms = Array.from(document.querySelectorAll('form[data-static="1"]'));
  if (!forms.length) return;

  forms.forEach((form) => {
    const statusEl = form.querySelector('.form__status');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (statusEl) {
        statusEl.textContent = '';
      }
    });
  });
})();

// Static video previews use a real frame from the file instead of the SVG placeholder.
(function initFirstFrameVideos() {
  const videos = Array.from(
    document.querySelectorAll('video[data-first-frame-video="1"], video[data-preview-video="1"]')
  );
  if (!videos.length) return;

  videos.forEach((video) => primeVideoPreviewFrame(video));
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
    const resetPreview = resetPreviewFrameBeforeFirstPlay(video);
    setVideoPreviewState(video, false);

    const p = video.play();
    if (p && typeof p.catch === 'function') {
      p.catch(() => {
        // Some mobile browsers (or data-saver modes) may block autoplay.
        // In that case we just keep the poster visible (video stays paused).
        if (resetPreview) {
          primeVideoPreviewFrame(video);
        } else {
          setVideoPreviewState(video, true);
        }
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

// Preview cards load and play only on hover/focus.
(function initHoverPreviews() {
  const previews = Array.from(document.querySelectorAll('video[data-hover-preview="1"]'));
  if (!previews.length) return;

  const ensureLoad = (video) => {
    if (video.dataset.previewLoaded === '1') return;
    try {
      video.preload = 'metadata';
      video.load();
    } catch (e) {}
    video.dataset.previewLoaded = '1';
  };

  const playPreview = (video) => {
    video.muted = true;
    video.playsInline = true;
    ensureLoad(video);
    const promise = video.play();
    if (promise && typeof promise.catch === 'function') {
      promise.catch(() => {});
    }
  };

  const stopPreview = (video) => {
    try {
      video.pause();
      video.currentTime = getVideoPreviewTime(video);
    } catch (e) {}
  };

  previews.forEach((video) => {
    const card = video.closest('.previewCard') || video;
    card.addEventListener('mouseenter', () => playPreview(video));
    card.addEventListener('mouseleave', () => stopPreview(video));
    card.addEventListener('focusin', () => playPreview(video));
    card.addEventListener('focusout', () => stopPreview(video));
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) previews.forEach(stopPreview);
  });
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
