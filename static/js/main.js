// ===== CodeForge Market - Main JS =====
'use strict';

// ── Toast System ─────────────────────────────────────
const Toast = {
  container: null,
  init() {
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  },
  show(message, type = 'info', duration = 3500) {
    this.init();
    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    const el = document.createElement('div');
    el.className = `toast-item ${type}`;
    el.innerHTML = `<span style="font-size:1.1rem">${icons[type] || icons.info}</span><span>${message}</span>`;
    this.container.appendChild(el);
    setTimeout(() => { el.style.animation = 'fadeOut 0.3s forwards'; setTimeout(() => el.remove(), 300); }, duration);
  }
};
window.Toast = Toast;

// ── Cart API ─────────────────────────────────────────
const Cart = {
  async add(productId, quantity = 1) {
    try {
      const res = await fetch('/api/cart/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId, quantity })
      });
      const data = await res.json();
      if (res.ok) {
        Toast.show('Added to cart!', 'success');
        Cart.updateBadge(data.count);
        return true;
      } else {
        Toast.show(data.error || 'Failed to add to cart', 'error');
        return false;
      }
    } catch { Toast.show('Network error', 'error'); return false; }
  },
  async remove(productId) {
    const res = await fetch('/api/cart/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId })
    });
    const data = await res.json();
    if (res.ok) Cart.updateBadge(data.count);
    return res.ok;
  },
  async update(productId, quantity) {
    const res = await fetch('/api/cart/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, quantity })
    });
    return res.ok;
  },
  updateBadge(count) {
    document.querySelectorAll('.cart-count-badge').forEach(el => { el.textContent = count; el.style.display = count > 0 ? 'flex' : 'none'; });
  },
  async refreshBadge() {
    try {
      const res = await fetch('/api/cart/count');
      const data = await res.json();
      Cart.updateBadge(data.count);
    } catch {}
  }
};
window.Cart = Cart;

// ── Wishlist API ──────────────────────────────────────
const Wishlist = {
  async toggle(productId, btn) {
    try {
      const res = await fetch('/api/wishlist/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId })
      });
      if (res.status === 401) { window.location.href = '/login'; return; }
      const data = await res.json();
      if (res.ok) {
        if (data.action === 'added') { btn.classList.add('active'); Toast.show('Added to wishlist', 'success'); }
        else { btn.classList.remove('active'); Toast.show('Removed from wishlist', 'info'); }
      }
    } catch { Toast.show('Network error', 'error'); }
  }
};
window.Wishlist = Wishlist;

// ── Live Search ────────────────────────────────────────
function initLiveSearch() {
  const input = document.getElementById('globalSearch');
  const dropdown = document.getElementById('searchDropdown');
  if (!input || !dropdown) return;
  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { dropdown.style.display = 'none'; return; }
    timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (!data.results.length) { dropdown.style.display = 'none'; return; }
        dropdown.innerHTML = data.results.map(p => {
          const price = p.discount_price || p.price;
          const img = p.thumbnail_image_url || 'https://placehold.co/42x42/e2e8f0/94a3b8?text=IMG';
          return `<a href="/product/${p._id}" class="search-result-item">
            <img src="${img}" alt="${p.title}">
            <div><div class="title">${p.title}</div><div class="price">₹${parseFloat(price).toFixed(2)}</div></div>
          </a>`;
        }).join('');
        dropdown.style.display = 'block';
      } catch {}
    }, 300);
  });
  document.addEventListener('click', e => { if (!input.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display = 'none'; });
}

// ── Scroll Reveal ──────────────────────────────────────
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
  }, { threshold: 0.1 });
  els.forEach(el => obs.observe(el));
}

// ── Skeleton → Real Content ────────────────────────────
function initSkeletonLoad() {
  document.querySelectorAll('img[data-src]').forEach(img => {
    const wrapper = img.closest('.card-img-wrapper');
    if (wrapper) wrapper.classList.add('skeleton');
    img.onload = () => { if (wrapper) wrapper.classList.remove('skeleton'); };
    img.onerror = () => { img.src = 'https://placehold.co/400x225/e2e8f0/94a3b8?text=No+Image'; if (wrapper) wrapper.classList.remove('skeleton'); };
    img.src = img.dataset.src;
  });
}

// ── Flash messages auto-dismiss ────────────────────────
function initFlashDismiss() {
  document.querySelectorAll('.alert-dismissible').forEach(el => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.5s'; setTimeout(() => el.remove(), 500); }, 4000);
  });
}

// ── Confirmation dialogs ───────────────────────────────
window.confirmAction = function(message, callback) {
  if (window.confirm(message)) callback();
};

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initLiveSearch();
  initReveal();
  initSkeletonLoad();
  initFlashDismiss();
  Cart.refreshBadge();
  // Delegate add-to-cart clicks
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-add-cart]');
    if (btn) Cart.add(btn.dataset.addCart);
    const wbtn = e.target.closest('[data-wishlist]');
    if (wbtn) Wishlist.toggle(wbtn.dataset.wishlist, wbtn);
  });
});
