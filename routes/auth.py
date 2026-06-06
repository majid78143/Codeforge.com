from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models.db import get_db, doc_to_dict
from utils.helpers import add_notification
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET'])
def login():
    if session.get('user_email'):
        return redirect(url_for('marketplace.index'))
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET'])
def register():
    if session.get('user_email'):
        return redirect(url_for('marketplace.index'))
    return render_template('register.html')


@auth_bp.route('/forgot-password', methods=['GET'])
def forgot_password():
    return render_template('forgot_password.html')


@auth_bp.route('/api/auth/sync', methods=['POST'])
def sync_session():
    """Called from frontend after Firebase auth — syncs user into Firestore and Flask session."""
    data = request.get_json()
    if not data or not data.get('email'):
        return jsonify({"error": "Invalid data"}), 400

    db = get_db()
    email = data['email'].lower().strip()
    safe_email = email.replace('.', '_').replace('@', '__')
    user_ref = db.collection('users').document(safe_email)
    user_doc = user_ref.get()
    now = datetime.utcnow()

    if not user_doc.exists:
        user_ref.set({
            "email": email,
            "display_name": data.get('displayName', email.split('@')[0]),
            "photo_url": data.get('photoURL', ''),
            "firebase_uid": data.get('uid', ''),
            "role": "user",
            "active": True,
            "wishlist": [],
            "created_at": now,
            "last_login": now,
        })
        add_notification(db, email, "Welcome to CodeForge Market!", "Your account has been created successfully.", "success")
    else:
        user_ref.update({"last_login": now, "firebase_uid": data.get('uid', '')})

    session.permanent = True
    session['user_email'] = email
    session['user_name'] = data.get('displayName', email.split('@')[0])
    session['user_photo'] = data.get('photoURL', '')
    session['user_role'] = 'user'
    return jsonify({"status": "ok", "redirect": url_for('user.dashboard')})


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@auth_bp.route('/logout')
def logout_page():
    session.clear()
    from flask import flash
    flash('You have been logged out.', 'info')
    return redirect(url_for('marketplace.index'))
