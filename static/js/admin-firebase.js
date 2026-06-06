import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

const app = initializeApp(window.FIREBASE_CONFIG);
const auth = getAuth(app);

const form = document.getElementById('adminLoginForm');
const errorBox = document.getElementById('loginError');
const btnText = document.getElementById('btnText');
const btnSpinner = document.getElementById('btnSpinner');

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove('d-none');
  if (btnText) btnText.textContent = 'Sign In to Admin Panel';
  if (btnSpinner) btnSpinner.classList.add('d-none');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorBox.classList.add('d-none');
  if (btnText) btnText.textContent = 'Verifying...';
  if (btnSpinner) btnSpinner.classList.remove('d-none');

  const email = form.email.value.trim();
  const password = form.password.value;

  try {
    const cred = await signInWithEmailAndPassword(auth, email, password);
    const idToken = await cred.user.getIdToken();

    const res = await fetch('/admin/verify-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idToken })
    });
    const data = await res.json();

    if (res.ok && data.redirect) {
      window.location.href = data.redirect;
    } else {
      await signOut(auth);
      showError(data.error || 'Access denied. You are not an authorized admin.');
    }
  } catch (err) {
    const msgs = {
      'auth/user-not-found': 'No account found with this email.',
      'auth/wrong-password': 'Incorrect password.',
      'auth/invalid-credential': 'Invalid email or password.',
      'auth/too-many-requests': 'Too many attempts. Please try again later.',
    };
    showError(msgs[err.code] || 'Login failed. Please try again.');
  }
});
