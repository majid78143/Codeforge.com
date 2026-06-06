// ===== CodeForge Market - Firebase Auth =====
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword,
  signInWithPopup, GoogleAuthProvider, signOut, sendPasswordResetEmail,
  onAuthStateChanged, updateProfile } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

const app = initializeApp(window.FIREBASE_CONFIG);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

async function syncSession(user) {
  const res = await fetch('/api/auth/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: user.email,
      displayName: user.displayName || user.email.split('@')[0],
      photoURL: user.photoURL || '',
      uid: user.uid
    })
  });
  const data = await res.json();
  if (data.redirect) window.location.href = data.redirect;
}

// ── Email Login ──────────────────────────────────────
window.loginWithEmail = async function(email, password) {
  try {
    const cred = await signInWithEmailAndPassword(auth, email, password);
    await syncSession(cred.user);
  } catch (err) {
    const msgs = {
      'auth/user-not-found': 'No account with this email.',
      'auth/wrong-password': 'Incorrect password.',
      'auth/invalid-credential': 'Invalid email or password.',
      'auth/too-many-requests': 'Too many attempts. Please try again later.',
      'auth/user-disabled': 'This account has been disabled.',
    };
    throw new Error(msgs[err.code] || 'Login failed. Please try again.');
  }
};

// ── Email Register ────────────────────────────────────
window.registerWithEmail = async function(email, password, displayName) {
  try {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(cred.user, { displayName });
    await syncSession(cred.user);
  } catch (err) {
    const msgs = {
      'auth/email-already-in-use': 'An account with this email already exists.',
      'auth/weak-password': 'Password must be at least 6 characters.',
      'auth/invalid-email': 'Please enter a valid email address.',
    };
    throw new Error(msgs[err.code] || 'Registration failed. Please try again.');
  }
};

// ── Google Login ─────────────────────────────────────
window.loginWithGoogle = async function() {
  try {
    const result = await signInWithPopup(auth, provider);
    await syncSession(result.user);
  } catch (err) {
    if (err.code === 'auth/popup-closed-by-user') return;
    throw new Error('Google sign-in failed. Please try again.');
  }
};

// ── Password Reset ────────────────────────────────────
window.resetPassword = async function(email) {
  try {
    await sendPasswordResetEmail(auth, email);
    return true;
  } catch (err) {
    const msgs = {
      'auth/user-not-found': 'No account found with this email.',
      'auth/invalid-email': 'Please enter a valid email address.',
    };
    throw new Error(msgs[err.code] || 'Failed to send reset email.');
  }
};

// ── Logout ────────────────────────────────────────────
window.firebaseLogout = async function() {
  await signOut(auth);
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/';
};

