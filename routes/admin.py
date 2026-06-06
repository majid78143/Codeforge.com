from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from models.db import get_db, doc_to_dict, query_to_list
from utils.helpers import serialize_doc, log_admin_action, add_notification
from utils.decorators import admin_required, permission_required
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import math

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ── FIREBASE LOGIN ─────────────────────────────────────────────────────────────
@admin_bp.route('/login', methods=['GET'])
def admin_login():
    if session.get('admin_email'):
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html')


@admin_bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify Firebase ID token and create admin session."""
    from firebase_admin import auth as firebase_auth
    from config import Config

    data = request.get_json() or {}
    id_token = data.get('idToken', '')
    if not id_token:
        return jsonify({"error": "Token required"}), 400

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception:
        return jsonify({"error": "Invalid or expired token"}), 401

    email = decoded.get('email', '').lower().strip()
    if email not in [e.lower() for e in Config.SUPER_ADMINS]:
        return jsonify({"error": "You are not authorized as an admin"}), 403

    session.permanent = True
    session['admin_email'] = email
    session['admin_username'] = decoded.get('name', email.split('@')[0])
    session['admin_role'] = 'super_admin'

    db = get_db()
    log_admin_action(db, email, "login", f"Admin logged in via Firebase from {request.remote_addr}")
    return jsonify({"status": "ok", "redirect": url_for('admin.dashboard')})


@admin_bp.route('/logout')
def admin_logout():
    if session.get('admin_email'):
        db = get_db()
        log_admin_action(db, session['admin_email'], "logout", "Admin logged out")
    session.pop('admin_email', None)
    session.pop('admin_username', None)
    session.pop('admin_role', None)
    return redirect(url_for('admin.admin_login'))


# ── DASHBOARD ──────────────────────────────────────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    db = get_db()
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    all_users = query_to_list(db.collection('users'))
    all_products = query_to_list(db.collection('products').where('status', '==', 'active'))
    all_paid_orders = query_to_list(db.collection('orders').where('payment_status', '==', 'paid'))
    pending_reviews = query_to_list(db.collection('reviews').where('approved', '==', False))
    pending_custom = query_to_list(db.collection('custom_orders').where('status', '==', 'pending'))
    all_downloads = query_to_list(db.collection('download_logs'))

    month_orders = [o for o in all_paid_orders if o.get('paid_at') and _to_dt(o['paid_at']) >= month_start]

    stats = {
        "total_users": len(all_users),
        "total_products": len(all_products),
        "total_orders": len(all_paid_orders),
        "total_revenue": sum(o.get('total', 0) for o in all_paid_orders),
        "month_orders": len(month_orders),
        "month_revenue": sum(o.get('total', 0) for o in month_orders),
        "pending_reviews": len(pending_reviews),
        "pending_custom_orders": len(pending_custom),
        "total_downloads": len(all_downloads),
    }

    recent_orders = sorted(all_paid_orders, key=lambda o: o.get('paid_at', ''), reverse=True)[:5]
    recent_users = sorted(all_users, key=lambda u: u.get('created_at', ''), reverse=True)[:5]

    revenue_chart = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_rev = sum(
            o.get('total', 0) for o in all_paid_orders
            if o.get('paid_at') and day_start <= _to_dt(o['paid_at']) < day_end
        )
        revenue_chart.append({"date": day_start.strftime("%b %d"), "revenue": day_rev})

    return render_template('admin/dashboard.html',
        stats=stats,
        recent_orders=[serialize_doc(o) for o in recent_orders],
        recent_users=[serialize_doc(u) for u in recent_users],
        revenue_chart=revenue_chart
    )


def _to_dt(val):
    """Convert Firestore DatetimeWithNanoseconds or ISO string to datetime."""
    if isinstance(val, datetime):
        return val
    if hasattr(val, 'isoformat'):
        return val.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return datetime.min


# ── PRODUCTS ──────────────────────────────────────────────────────────────────
@admin_bp.route('/products')
@admin_required
@permission_required('manage_products')
def products():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    q = request.args.get('q', '').lower()

    all_prods = query_to_list(db.collection('products').order_by('created_at', direction='DESCENDING'))
    if q:
        all_prods = [p for p in all_prods if q in p.get('title', '').lower()]

    total = len(all_prods)
    start = (page - 1) * per_page
    prods = all_prods[start:start + per_page]
    cats = query_to_list(db.collection('categories'))

    return render_template('admin/products.html',
        products=[serialize_doc(p) for p in prods],
        categories=[serialize_doc(c) for c in cats],
        page=page, total=total, total_pages=math.ceil(total / per_page) if total else 1, q=q
    )


@admin_bp.route('/products/create', methods=['POST'])
@admin_required
@permission_required('manage_products')
def create_product():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    gallery = data.get('gallery_images', [])
    if isinstance(gallery, str):
        gallery = [u.strip() for u in gallery.split('\n') if u.strip()]
    features = data.get('features', [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split('\n') if f.strip()]

    product = {
        "title": data.get('title', '').strip(),
        "description": data.get('description', '').strip(),
        "price": float(data.get('price', 0)),
        "discount_price": float(data.get('discount_price', 0)) if data.get('discount_price') else None,
        "category": data.get('category', '').strip(),
        "tags": tags,
        "thumbnail_image_url": data.get('thumbnail_image_url', '').strip(),
        "banner_image_url": data.get('banner_image_url', '').strip(),
        "gallery_images": gallery,
        "features": features,
        "mediafire_download_link": data.get('mediafire_download_link', '').strip(),
        "status": data.get('status', 'active'),
        "sales_count": 0,
        "view_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    _, ref = db.collection('products').add(product)
    log_admin_action(db, session['admin_email'], "create_product", f"Created: {product['title']}")
    return jsonify({"status": "ok", "id": ref.id})


@admin_bp.route('/products/<product_id>', methods=['GET'])
@admin_required
def get_product(product_id):
    db = get_db()
    doc = db.collection('products').document(product_id).get()
    p = doc_to_dict(doc)
    if not p:
        return jsonify({"error": "Not found"}), 404
    return jsonify(serialize_doc(p))


@admin_bp.route('/products/<product_id>/update', methods=['POST'])
@admin_required
@permission_required('manage_products')
def update_product(product_id):
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    gallery = data.get('gallery_images', [])
    if isinstance(gallery, str):
        gallery = [u.strip() for u in gallery.split('\n') if u.strip()]
    features = data.get('features', [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split('\n') if f.strip()]

    db.collection('products').document(product_id).update({
        "title": data.get('title', '').strip(),
        "description": data.get('description', '').strip(),
        "price": float(data.get('price', 0)),
        "discount_price": float(data.get('discount_price', 0)) if data.get('discount_price') else None,
        "category": data.get('category', '').strip(),
        "tags": tags,
        "thumbnail_image_url": data.get('thumbnail_image_url', '').strip(),
        "banner_image_url": data.get('banner_image_url', '').strip(),
        "gallery_images": gallery,
        "features": features,
        "mediafire_download_link": data.get('mediafire_download_link', '').strip(),
        "status": data.get('status', 'active'),
        "updated_at": datetime.utcnow(),
    })
    log_admin_action(db, session['admin_email'], "update_product", f"Updated product {product_id}")
    return jsonify({"status": "ok"})


@admin_bp.route('/products/<product_id>/delete', methods=['POST'])
@admin_required
@permission_required('manage_products')
def delete_product(product_id):
    db = get_db()
    db.collection('products').document(product_id).delete()
    log_admin_action(db, session['admin_email'], "delete_product", f"Deleted product {product_id}")
    return jsonify({"status": "ok"})


# ── CATEGORIES ────────────────────────────────────────────────────────────────
@admin_bp.route('/categories', methods=['GET'])
@admin_required
def categories():
    db = get_db()
    cats = query_to_list(db.collection('categories'))
    return jsonify([serialize_doc(c) for c in cats])


@admin_bp.route('/categories/create', methods=['POST'])
@admin_required
@permission_required('manage_products')
def create_category():
    db = get_db()
    data = request.get_json()
    slug = data.get('slug', data['name'].lower().replace(' ', '-'))
    db.collection('categories').document(slug).set({"name": data['name'], "slug": slug, "active": True})
    return jsonify({"status": "ok"})


# ── ORDERS ────────────────────────────────────────────────────────────────────
@admin_bp.route('/orders')
@admin_required
@permission_required('manage_orders')
def orders():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    status_filter = request.args.get('status', '')

    query = db.collection('orders')
    if status_filter:
        query = query.where('payment_status', '==', status_filter)

    all_orders = query_to_list(query.order_by('created_at', direction='DESCENDING'))
    total = len(all_orders)
    start = (page - 1) * per_page
    order_list = all_orders[start:start + per_page]

    return render_template('admin/orders.html',
        orders=[serialize_doc(o) for o in order_list],
        page=page, total=total, total_pages=math.ceil(total / per_page) if total else 1,
        status_filter=status_filter
    )


@admin_bp.route('/orders/<order_id>')
@admin_required
def order_detail(order_id):
    db = get_db()
    order = doc_to_dict(db.collection('orders').document(order_id).get())
    if not order:
        return render_template('404.html'), 404
    return render_template('admin/order_detail.html', order=serialize_doc(order))


# ── USERS ─────────────────────────────────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
@permission_required('manage_users')
def users():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    q = request.args.get('q', '').lower()

    all_users = query_to_list(db.collection('users').order_by('created_at', direction='DESCENDING'))
    if q:
        all_users = [u for u in all_users if q in u.get('email', '').lower() or q in u.get('display_name', '').lower()]

    total = len(all_users)
    start = (page - 1) * per_page
    user_list = all_users[start:start + per_page]

    return render_template('admin/users.html',
        users=[serialize_doc(u) for u in user_list],
        page=page, total=total, total_pages=math.ceil(total / per_page) if total else 1, q=q
    )


@admin_bp.route('/users/<path:email>/toggle', methods=['POST'])
@admin_required
@permission_required('manage_users')
def toggle_user(email):
    db = get_db()
    safe = email.replace('.', '_').replace('@', '__')
    ref = db.collection('users').document(safe)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Not found"}), 404
    new_status = not doc.to_dict().get('active', True)
    ref.update({"active": new_status})
    log_admin_action(db, session['admin_email'], "toggle_user", f"User {email} active={new_status}")
    return jsonify({"status": "ok", "active": new_status})


# ── COUPONS ───────────────────────────────────────────────────────────────────
@admin_bp.route('/coupons')
@admin_required
@permission_required('manage_coupons')
def coupons():
    db = get_db()
    coupon_list = query_to_list(db.collection('coupons').order_by('created_at', direction='DESCENDING'))
    return render_template('admin/coupons.html', coupons=[serialize_doc(c) for c in coupon_list])


@admin_bp.route('/coupons/create', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def create_coupon():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    code = data.get('coupon_code', '').strip().upper()
    if not code:
        return jsonify({"error": "Coupon code required"}), 400

    existing = query_to_list(db.collection('coupons').where('coupon_code', '==', code).limit(1))
    if existing:
        return jsonify({"error": "Coupon code already exists"}), 400

    expiry = None
    if data.get('expiry_date'):
        try:
            expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d')
        except Exception:
            pass

    db.collection('coupons').document(code).set({
        "coupon_code": code,
        "discount_type": data.get('discount_type', 'percentage'),
        "discount_value": float(data.get('discount_value', 10)),
        "expiry_date": expiry,
        "usage_limit": int(data.get('usage_limit', 0)),
        "per_user_limit": int(data.get('per_user_limit', 1)),
        "minimum_order_value": float(data.get('minimum_order_value', 0)),
        "active_status": data.get('active_status', True) in [True, 'true', '1', 'on'],
        "created_at": datetime.utcnow(),
    })
    log_admin_action(db, session['admin_email'], "create_coupon", f"Created coupon: {code}")
    return jsonify({"status": "ok"})


@admin_bp.route('/coupons/<coupon_id>/toggle', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def toggle_coupon(coupon_id):
    db = get_db()
    ref = db.collection('coupons').document(coupon_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Not found"}), 404
    ref.update({"active_status": not doc.to_dict().get('active_status', True)})
    return jsonify({"status": "ok"})


@admin_bp.route('/coupons/<coupon_id>/delete', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def delete_coupon(coupon_id):
    db = get_db()
    db.collection('coupons').document(coupon_id).delete()
    return jsonify({"status": "ok"})


# ── REVIEWS ───────────────────────────────────────────────────────────────────
@admin_bp.route('/reviews')
@admin_required
def reviews():
    db = get_db()
    status = request.args.get('status', 'pending')
    approved = status == 'approved'
    review_list = query_to_list(
        db.collection('reviews').where('approved', '==', approved).order_by('created_at', direction='DESCENDING')
    )
    return render_template('admin/reviews.html', reviews=[serialize_doc(r) for r in review_list], status=status)


@admin_bp.route('/reviews/<review_id>/approve', methods=['POST'])
@admin_required
def approve_review(review_id):
    db = get_db()
    db.collection('reviews').document(review_id).update({"approved": True})
    return jsonify({"status": "ok"})


@admin_bp.route('/reviews/<review_id>/delete', methods=['POST'])
@admin_required
def delete_review(review_id):
    db = get_db()
    db.collection('reviews').document(review_id).delete()
    return jsonify({"status": "ok"})


# ── CUSTOM ORDERS ─────────────────────────────────────────────────────────────
@admin_bp.route('/custom-orders')
@admin_required
def custom_orders():
    db = get_db()
    status = request.args.get('status', 'pending')
    orders_list = query_to_list(
        db.collection('custom_orders').where('status', '==', status).order_by('created_at', direction='DESCENDING')
    )
    return render_template('admin/custom_orders.html', orders=[serialize_doc(o) for o in orders_list], status=status)


@admin_bp.route('/custom-orders/<order_id>/action', methods=['POST'])
@admin_required
def custom_order_action(order_id):
    db = get_db()
    data = request.get_json()
    action = data.get('action')
    ref = db.collection('custom_orders').document(order_id)
    order_doc = ref.get()
    if not order_doc.exists:
        return jsonify({"error": "Not found"}), 404
    order = order_doc.to_dict()

    update = {"status": action, "updated_at": datetime.utcnow()}
    if action == 'quote_sent':
        update['quotation'] = data.get('quotation', '')
        update['quoted_amount'] = float(data.get('quoted_amount', 0))
    ref.update(update)

    msg_map = {
        "accepted": "Your custom development request has been accepted!",
        "rejected": "Your custom development request was rejected.",
        "quote_sent": f"You have a new quotation: ₹{data.get('quoted_amount', 0)} - {data.get('quotation', '')}",
    }
    if action in msg_map:
        add_notification(db, order.get('user_email', ''), "Custom Order Update", msg_map[action], "info")
    return jsonify({"status": "ok"})


# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@admin_bp.route('/analytics')
@admin_required
def analytics():
    db = get_db()
    now = datetime.utcnow()
    all_paid = query_to_list(db.collection('orders').where('payment_status', '==', 'paid'))

    months = []
    for i in range(5, -1, -1):
        ms = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        me = (ms + timedelta(days=32)).replace(day=1)
        month_orders = [o for o in all_paid if o.get('paid_at') and ms <= _to_dt(o['paid_at']) < me]
        months.append({
            "label": ms.strftime("%b %Y"),
            "revenue": sum(o.get('total', 0) for o in month_orders),
            "orders": len(month_orders)
        })

    top_products = sorted(
        query_to_list(db.collection('products').where('status', '==', 'active')),
        key=lambda p: p.get('sales_count', 0), reverse=True
    )[:10]

    all_usage = query_to_list(db.collection('coupon_usage'))
    coupon_counts = {}
    for u in all_usage:
        c = u.get('coupon_code', '')
        coupon_counts[c] = coupon_counts.get(c, 0) + 1
    coupon_stats = sorted([{"_id": k, "count": v} for k, v in coupon_counts.items()], key=lambda x: x['count'], reverse=True)[:10]

    all_dl = query_to_list(db.collection('download_logs'))
    dl_counts = {}
    for d in all_dl:
        t = d.get('product_title', '')
        dl_counts[t] = dl_counts.get(t, 0) + 1
    download_stats = sorted([{"_id": k, "count": v} for k, v in dl_counts.items()], key=lambda x: x['count'], reverse=True)[:10]

    return render_template('admin/analytics.html',
        months=months,
        top_products=[serialize_doc(p) for p in top_products],
        coupon_stats=coupon_stats,
        download_stats=download_stats
    )


# ── SETTINGS ──────────────────────────────────────────────────────────────────
@admin_bp.route('/settings')
@admin_required
@permission_required('manage_settings')
def settings():
    db = get_db()
    s = doc_to_dict(db.collection('settings').document('store').get()) or {}
    return render_template('admin/settings.html', settings=serialize_doc(s))


@admin_bp.route('/settings/update', methods=['POST'])
@admin_required
@permission_required('manage_settings')
def update_settings():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    allowed = [
        'site_name', 'site_tagline', 'contact_email', 'currency', 'tax_percent',
        'announcement', 'announcement_active', 'seo_title', 'seo_description', 'seo_keywords',
        'homepage_hero_title', 'homepage_hero_subtitle', 'homepage_hero_cta',
        'homepage_featured_limit', 'homepage_trending_limit',
        'razorpay_key_id', 'razorpay_key_secret'
    ]
    update = {k: data[k] for k in allowed if k in data}
    if 'tax_percent' in update:
        update['tax_percent'] = float(update['tax_percent'])
    if 'homepage_featured_limit' in update:
        update['homepage_featured_limit'] = int(update['homepage_featured_limit'])
    if 'homepage_trending_limit' in update:
        update['homepage_trending_limit'] = int(update['homepage_trending_limit'])
    if 'announcement_active' in update:
        update['announcement_active'] = update['announcement_active'] in [True, '1', 'on']
    db.collection('settings').document('store').update(update)
    log_admin_action(db, session['admin_email'], "update_settings", "Store settings updated")
    return jsonify({"status": "ok"})


# ── LOGS ──────────────────────────────────────────────────────────────────────
@admin_bp.route('/logs')
@admin_required
def admin_logs():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 20
    all_logs = query_to_list(db.collection('admin_logs').order_by('timestamp', direction='DESCENDING'))
    total = len(all_logs)
    start = (page - 1) * per_page
    logs = all_logs[start:start + per_page]
    return render_template('admin/logs.html',
        logs=[serialize_doc(l) for l in logs],
        page=page, total=total, total_pages=math.ceil(total / per_page) if total else 1
    )


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
@admin_bp.route('/notifications')
@admin_required
def admin_notifications():
    db = get_db()
    notifs = query_to_list(
        db.collection('notifications').where('user_email', '==', 'admin').order_by('created_at', direction='DESCENDING').limit(50)
    )
    return render_template('admin/notifications.html', notifications=[serialize_doc(n) for n in notifs])
