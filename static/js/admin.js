// ===== CodeForge Market - Admin JS =====
'use strict';

// ── Toast ─────────────────────────────────────────────
const AdminToast = {
  show(msg, type = 'success') {
    const colors = { success: '#16a34a', error: '#dc2626', warning: '#d97706', info: '#2563eb' };
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;background:white;padding:0.875rem 1.25rem;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.12);border-left:4px solid ${colors[type]||colors.info};font-size:0.875rem;font-weight:500;color:#111827;min-width:250px;animation:slideInRight 0.3s ease`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 3500);
  }
};
window.AdminToast = AdminToast;

// ── API helpers ────────────────────────────────────────
async function adminFetch(url, options = {}) {
  options.headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}
window.adminFetch = adminFetch;

// ── Confirm helper ─────────────────────────────────────
window.adminConfirm = function(msg, callback) {
  const modal = document.getElementById('confirmModal');
  if (modal) {
    document.getElementById('confirmMessage').textContent = msg;
    document.getElementById('confirmBtn').onclick = () => {
      bootstrap.Modal.getInstance(modal).hide();
      callback();
    };
    new bootstrap.Modal(modal).show();
  } else {
    if (window.confirm(msg)) callback();
  }
};

// ── Product CRUD ───────────────────────────────────────
window.openProductModal = function(productId = null) {
  const modal = document.getElementById('productModal');
  if (!modal) return;
  document.getElementById('productForm').reset();
  document.getElementById('productModalTitle').textContent = productId ? 'Edit Product' : 'Add Product';
  document.getElementById('productId').value = productId || '';
  if (productId) {
    adminFetch(`/admin/products/${productId}`).then(({ ok, data }) => {
      if (ok) {
        Object.entries(data).forEach(([k, v]) => {
          const el = document.getElementById(`prod_${k}`);
          if (el) {
            if (Array.isArray(v)) el.value = v.join(k === 'gallery_images' ? '\n' : ', ');
            else el.value = v || '';
          }
        });
      }
    });
  }
  new bootstrap.Modal(modal).show();
};

window.saveProduct = async function() {
  const form = document.getElementById('productForm');
  const formData = new FormData(form);
  const data = Object.fromEntries(formData);
  const productId = data.product_id;
  const url = productId ? `/admin/products/${productId}/update` : '/admin/products/create';
  const { ok, data: res } = await adminFetch(url, { method: 'POST', body: JSON.stringify(data) });
  if (ok) {
    AdminToast.show(productId ? 'Product updated!' : 'Product created!', 'success');
    bootstrap.Modal.getInstance(document.getElementById('productModal')).hide();
    setTimeout(() => location.reload(), 800);
  } else {
    AdminToast.show(res.error || 'Failed to save product', 'error');
  }
};

window.deleteProduct = function(productId) {
  adminConfirm('Delete this product permanently?', async () => {
    const { ok } = await adminFetch(`/admin/products/${productId}/delete`, { method: 'POST' });
    if (ok) { AdminToast.show('Product deleted', 'success'); setTimeout(() => location.reload(), 800); }
    else AdminToast.show('Failed to delete', 'error');
  });
};

window.toggleProduct = async function(productId, btn) {
  const currentStatus = btn.dataset.status;
  const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
  const { ok } = await adminFetch(`/admin/products/${productId}/update`, {
    method: 'POST', body: JSON.stringify({ status: newStatus })
  });
  if (ok) {
    btn.dataset.status = newStatus;
    btn.textContent = newStatus === 'active' ? 'Deactivate' : 'Activate';
    AdminToast.show(`Product ${newStatus}`, 'success');
    setTimeout(() => location.reload(), 800);
  }
};

// ── User toggle ────────────────────────────────────────
window.toggleUser = async function(email) {
  const { ok, data } = await adminFetch(`/admin/users/${encodeURIComponent(email)}/toggle`, { method: 'POST' });
  if (ok) { AdminToast.show(`User ${data.active ? 'activated' : 'deactivated'}`, 'success'); setTimeout(() => location.reload(), 800); }
};

// ── Coupon CRUD ────────────────────────────────────────
window.saveCoupon = async function() {
  const form = document.getElementById('couponForm');
  const data = Object.fromEntries(new FormData(form));
  data.active_status = document.getElementById('couponActive').checked;
  const { ok, data: res } = await adminFetch('/admin/coupons/create', { method: 'POST', body: JSON.stringify(data) });
  if (ok) {
    AdminToast.show('Coupon created!', 'success');
    bootstrap.Modal.getInstance(document.getElementById('couponModal')).hide();
    setTimeout(() => location.reload(), 800);
  } else { AdminToast.show(res.error || 'Failed', 'error'); }
};

window.toggleCoupon = async function(id) {
  const { ok } = await adminFetch(`/admin/coupons/${id}/toggle`, { method: 'POST' });
  if (ok) { AdminToast.show('Coupon status toggled', 'success'); setTimeout(() => location.reload(), 800); }
};

window.deleteCoupon = function(id) {
  adminConfirm('Delete this coupon?', async () => {
    const { ok } = await adminFetch(`/admin/coupons/${id}/delete`, { method: 'POST' });
    if (ok) { AdminToast.show('Deleted', 'success'); setTimeout(() => location.reload(), 800); }
  });
};

// ── Review moderation ──────────────────────────────────
window.approveReview = async function(id) {
  const { ok } = await adminFetch(`/admin/reviews/${id}/approve`, { method: 'POST' });
  if (ok) { AdminToast.show('Review approved', 'success'); document.getElementById(`review-${id}`).remove(); }
};

window.deleteReview = function(id) {
  adminConfirm('Delete this review?', async () => {
    const { ok } = await adminFetch(`/admin/reviews/${id}/delete`, { method: 'POST' });
    if (ok) { AdminToast.show('Review deleted', 'success'); document.getElementById(`review-${id}`).remove(); }
  });
};

// ── Custom Order actions ───────────────────────────────
window.customOrderAction = async function(id, action, extra = {}) {
  const { ok, data } = await adminFetch(`/admin/custom-orders/${id}/action`, {
    method: 'POST', body: JSON.stringify({ action, ...extra })
  });
  if (ok) { AdminToast.show(`Action applied: ${action}`, 'success'); setTimeout(() => location.reload(), 800); }
  else AdminToast.show(data.error || 'Failed', 'error');
};

// ── Settings save ──────────────────────────────────────
window.saveSettings = async function(formId) {
  const form = document.getElementById(formId);
  const data = Object.fromEntries(new FormData(form));
  const toggles = form.querySelectorAll('input[type=checkbox]');
  toggles.forEach(t => { data[t.name] = t.checked; });
  const { ok } = await adminFetch('/admin/settings/update', { method: 'POST', body: JSON.stringify(data) });
  if (ok) AdminToast.show('Settings saved!', 'success');
  else AdminToast.show('Failed to save settings', 'error');
};

// ── Revenue chart ──────────────────────────────────────
window.renderRevenueChart = function(data) {
  const canvas = document.getElementById('revenueChart');
  if (!canvas || !window.Chart) return;
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.map(d => d.date),
      datasets: [{
        label: 'Revenue (₹)',
        data: data.map(d => d.revenue),
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37,99,235,0.06)',
        tension: 0.4, fill: true, pointRadius: 4,
        pointBackgroundColor: '#2563eb',
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
        y: { grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 }, callback: v => '₹' + v } }
      }
    }
  });
};

// ── Admin create ───────────────────────────────────────
window.createAdmin = async function() {
  const form = document.getElementById('adminForm');
  const data = Object.fromEntries(new FormData(form));
  const { ok, data: res } = await adminFetch('/admin/admins/create', { method: 'POST', body: JSON.stringify(data) });
  if (ok) {
    AdminToast.show('Admin created!', 'success');
    bootstrap.Modal.getInstance(document.getElementById('adminModal')).hide();
    setTimeout(() => location.reload(), 800);
  } else { AdminToast.show(res.error || 'Failed', 'error'); }
};

window.toggleAdmin = function(id) {
  adminConfirm('Toggle this admin status?', async () => {
    const { ok } = await adminFetch(`/admin/admins/${id}/toggle`, { method: 'POST' });
    if (ok) { AdminToast.show('Status changed', 'success'); setTimeout(() => location.reload(), 800); }
  });
};

// ── Send Notification ──────────────────────────────────
window.sendNotification = async function() {
  const form = document.getElementById('notifForm');
  const data = Object.fromEntries(new FormData(form));
  const { ok } = await adminFetch('/admin/notifications/send', { method: 'POST', body: JSON.stringify(data) });
  if (ok) AdminToast.show('Notification sent!', 'success');
  else AdminToast.show('Failed to send', 'error');
};

// ── Login form ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('adminLoginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = loginForm.querySelector('[type=submit]');
      btn.disabled = true; btn.textContent = 'Signing in...';
      const data = { email: loginForm.email.value, password: loginForm.password.value };
      const { ok, data: res } = await adminFetch('/admin/login', { method: 'POST', body: JSON.stringify(data) });
      if (ok && res.redirect) { window.location.href = res.redirect; }
      else {
        AdminToast.show(res.error || 'Invalid credentials', 'error');
        btn.disabled = false; btn.textContent = 'Sign In';
      }
    });
  }
});

    
