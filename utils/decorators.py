from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify
from models.db import get_db

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_email'):
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_email'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            role = session.get('admin_role', '')
            if role == 'super_admin':
                return f(*args, **kwargs)
            db = get_db()
            role_doc = db.admin_roles.find_one({"role": role})
            if not role_doc or (permission not in role_doc.get('permissions', []) and 'all' not in role_doc.get('permissions', [])):
                if request.is_json:
                    return jsonify({"error": "Insufficient permissions"}), 403
                flash('You do not have permission to perform this action.', 'danger')
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_email'):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated
  
