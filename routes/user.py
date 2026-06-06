from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models.db import get_db, doc_to_dict, query_to_list
from utils.helpers import serialize_doc, add_notification
from utils.decorators import login_required, api_login_required
from datetime import datetime
import math

user_bp = Blueprint('user', __name__)


def _safe_email(email):
    return email.replace('.', '_').replace('@', '__')


@user_bp.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    email = session['user_email']

    orders = query_to_list(
        db.collection('orders')
        .where('user_email', '==', email)
        .where('payment_status', '==', 'paid')
        .order_by('paid_at', direction='DESCENDING')
        .limit(5)
    )
    downloads = query_to_list(
        db.collection('download_logs')
        .where('user_email', '==', email)
        .order_by('downloaded_at', direction='DESCENDING')
        .limit(5)
    )
    user_doc = db.collection('users').document(_safe_email(email)).get()
    wishlist_count = len(user_doc.to_dict().get('wishlist', [])) if user_doc.exists else 0

    notifs = query_to_list(
        db.collection('notifications')
        .where('user_email', '==', email)
        .where('read', '==', False)
    )
    notif_count = len(notifs)

    return render_template('dashboard.html',
        orders=[serialize_doc(o) for o in orders],
        downloads=[serialize_doc(d) for d in downloads],
        wishlist_count=wishlist_count,
        notif_count=notif_count
    )


@user_bp.route('/orders')
@login_required
def orders():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 10
    email = session['user_email']

    all_orders = query_to_list(
        db.collection('orders')
        .where('user_email', '==', email)
        .order_by('created_at', direction='DESCENDING')
    )
    total = len(all_orders)
    start = (page - 1) * per_page
    order_list = all_orders[start:start + per_page]

    return render_template('orders.html',
        orders=[serialize_doc(o) for o in order_list],
        page=page, total=total, total_pages=math.ceil(total / per_page) if total else 1
    )


@user_bp.route('/downloads')
@login_required
def downloads():
    db = get_db()
    email = session['user_email']
    paid_orders = query_to_list(
        db.collection('orders')
        .where('user_email', '==', email)
        .where('payment_status', '==', 'paid')
    )
    products_purchased = {}
    for order in paid_orders:
        for item in order.get('items', []):
            pid = item.get('product_id') or item.get('_id')
            if pid and pid not in products_purchased:
                products_purchased[pid] = item
    return render_template('downloads.html', products=list(products_purchased.values()), orders=paid_orders)


@user_bp.route('/api/download/<product_id>')
@api_login_required
def download_product(product_id):
    db = get_db()
    email = session['user_email']

    paid_orders = query_to_list(
        db.collection('orders')
        .where('user_email', '==', email)
        .where('payment_status', '==', 'paid')
    )
    paid = any(
        any(item.get('product_id') == product_id for item in o.get('items', []))
        for o in paid_orders
    )
    if not paid:
        return jsonify({"error": "Purchase required to download"}), 403

    prod_doc = db.collection('products').document(product_id).get()
    product = doc_to_dict(prod_doc)
    if not product or not product.get('mediafire_download_link'):
        return jsonify({"error": "Download link not available"}), 404

    db.collection('download_logs').add({
        "user_email": email,
        "product_id": product_id,
        "product_title": product.get('title'),
        "downloaded_at": datetime.utcnow()
    })
    return jsonify({"url": product['mediafire_download_link']})


@user_bp.route('/wishlist')
@login_required
def wishlist():
    db = get_db()
    user_doc = db.collection('users').document(_safe_email(session['user_email'])).get()
    wishlist_ids = user_doc.to_dict().get('wishlist', []) if user_doc.exists else []
    products = []
    for wid in wishlist_ids:
        prod_doc = db.collection('products').document(wid).get()
        prod = doc_to_dict(prod_doc)
        if prod and prod.get('status') == 'active':
            products.append(serialize_doc(prod))
    return render_template('wishlist.html', products=products)


@user_bp.route('/api/wishlist/toggle', methods=['POST'])
@api_login_required
def toggle_wishlist():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({"error": "Product ID required"}), 400

    ref = db.collection('users').document(_safe_email(session['user_email']))
    user_doc = ref.get()
    wishlist = user_doc.to_dict().get('wishlist', []) if user_doc.exists else []

    if product_id in wishlist:
        wishlist.remove(product_id)
        action = 'removed'
    else:
        wishlist.append(product_id)
        action = 'added'
    ref.update({"wishlist": wishlist})
    return jsonify({"status": "ok", "action": action, "count": len(wishlist)})


@user_bp.route('/notifications')
@login_required
def notifications():
    db = get_db()
    email = session['user_email']
    notifs = query_to_list(
        db.collection('notifications')
        .where('user_email', '==', email)
        .order_by('created_at', direction='DESCENDING')
        .limit(50)
    )
    # Mark all as read
    for n in notifs:
        if not n.get('read'):
            db.collection('notifications').document(n['_id']).update({"read": True})
    return render_template('notifications.html', notifications=[serialize_doc(n) for n in notifs])


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    ref = db.collection('users').document(_safe_email(session['user_email']))
    if request.method == 'POST':
        data = request.get_json() or request.form.to_dict()
        update = {}
        if data.get('display_name'):
            update['display_name'] = data['display_name']
        if data.get('phone'):
            update['phone'] = data['phone']
        if update:
            ref.update(update)
        return jsonify({"status": "ok", "message": "Profile updated"})
    user = doc_to_dict(ref.get())
    return render_template('profile.html', user=serialize_doc(user) if user else {})


@user_bp.route('/reviews')
@login_required
def my_reviews():
    db = get_db()
    reviews = query_to_list(
        db.collection('reviews')
        .where('user_email', '==', session['user_email'])
        .order_by('created_at', direction='DESCENDING')
    )
    return render_template('reviews.html', reviews=[serialize_doc(r) for r in reviews])


@user_bp.route('/api/reviews/submit', methods=['POST'])
@api_login_required
def submit_review():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    rating = int(data.get('rating', 5))
    comment = data.get('comment', '').strip()

    if not product_id or not comment:
        return jsonify({"error": "Product and comment required"}), 400
    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be 1-5"}), 400

    existing = query_to_list(
        db.collection('reviews')
        .where('user_email', '==', session['user_email'])
        .where('product_id', '==', product_id)
        .limit(1)
    )
    if existing:
        return jsonify({"error": "You have already reviewed this product"}), 400

    db.collection('reviews').add({
        "user_email": session['user_email'],
        "user_name": session.get('user_name', 'Anonymous'),
        "product_id": product_id,
        "rating": rating,
        "comment": comment,
        "approved": False,
        "created_at": datetime.utcnow()
    })
    return jsonify({"status": "ok", "message": "Review submitted for approval"})
