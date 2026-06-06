from datetime import datetime
import re


def serialize_doc(doc):
    """Convert a Firestore dict (with possible DatetimeWithNanoseconds) to JSON-safe dict."""
    if doc is None:
        return None
    result = {}
    for k, v in doc.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = [serialize_doc(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            result[k] = serialize_doc(v)
        else:
            result[k] = v
    return result


def log_admin_action(db, admin_email, action, details=""):
    from flask import request as flask_request
    try:
        ip = flask_request.remote_addr
    except Exception:
        ip = None
    db.collection('admin_logs').add({
        "admin_email": admin_email,
        "action": action,
        "details": details,
        "ip": ip,
        "timestamp": datetime.utcnow(),
    })


def add_notification(db, user_email, title, message, ntype="info"):
    db.collection('notifications').add({
        "user_email": user_email,
        "title": title,
        "message": message,
        "type": ntype,
        "read": False,
        "created_at": datetime.utcnow(),
    })


def format_currency(amount, currency="INR"):
    symbol = {"INR": "₹", "USD": "$", "EUR": "€"}.get(currency, "₹")
    return f"{symbol}{amount:,.2f}"


def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')
