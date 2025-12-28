// Mobile menu
const burger = document.querySelector('[data-burger]');
const mobileNav = document.querySelector('[data-mobile-nav]');
if (burger && mobileNav) {
  burger.addEventListener('click', () => {
    const open = mobileNav.style.display === 'block';
    mobileNav.style.display = open ? 'none' : 'block';
    burger.classList.toggle('is-open', !open);
  });

  mobileNav.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => { mobileNav.style.display = 'none'; });
  });
}

// Universal modal logic (event delegation)
function openModalById(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.classList.add('is-open');
  m.setAttribute('aria-hidden', 'false');
}

function closeModalEl(m) {
  if (!m) return;
  m.classList.remove('is-open');
  m.setAttribute('aria-hidden', 'true');
}

document.addEventListener('click', (e) => {
  const target = e.target;

  // Open modal
  const openBtn = target?.closest?.('[data-open-modal]');
  if (openBtn) {
    const id = openBtn.getAttribute('data-open-modal');
    if (id) openModalById(id);
    return;
  }

  // Close modal
  const closeBtn = target?.closest?.('[data-close-modal]');
  if (closeBtn) {
    closeModalEl(closeBtn.closest('.modal'));
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  document.querySelectorAll('.modal.is-open').forEach(m => closeModalEl(m));
});


// Work filtering
const tabs = document.querySelectorAll('.tab');
const workGrid = document.getElementById('workGrid');
function setActiveTab(activeBtn) {
  tabs.forEach(t => t.classList.remove('is-active'));
  activeBtn.classList.add('is-active');
}
function filterWorks(cat) {
  if (!workGrid) return;
  const cards = workGrid.querySelectorAll('[data-cat]');
  cards.forEach(card => {
    const matches = (cat === 'all') || (card.getAttribute('data-cat') === cat);
    card.style.display = matches ? 'block' : 'none';
  });
}
tabs.forEach(btn => {
  btn.addEventListener('click', () => {
    const cat = btn.getAttribute('data-filter');
    setActiveTab(btn);
    filterWorks(cat);
  });
});

// Lead form AJAX (keeps non-JS fallback working)
const leadForm = document.getElementById('leadForm');
if (leadForm) {
  const status = leadForm.querySelector('.form__status');

  leadForm.addEventListener('submit', async (e) => {
    // If fetch fails, allow default POST fallback
    e.preventDefault();

    const fd = new FormData(leadForm);
    const payload = Object.fromEntries(fd.entries());
    if (status) status.textContent = 'Отправляем…';

    try {
      const res = await fetch('/api/lead', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data?.error || 'Не удалось отправить. Проверьте поля и попробуйте ещё раз.';
        if (status) status.textContent = msg;
        return;
      }

      if (status) status.textContent = 'Готово! Мы получили заявку ✅';
      leadForm.reset();
      setTimeout(() => closeModalEl(document.getElementById('leadModal')), 800);
    } catch (err) {
      // network error → degrade gracefully: normal form POST
      if (status) status.textContent = 'Пробуем отправить обычным способом…';
      leadForm.submit();
    }
  });
}