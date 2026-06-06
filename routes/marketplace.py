from flask import Blueprint, render_template, request, jsonify, session
from models.db import get_db, doc_to_dict, query_to_list
from utils.helpers import serialize_doc
from datetime import datetime
import math

marketplace_bp = Blueprint('marketplace', __name__)


def _get_settings(db):
    doc = db.collection('settings').document('store').get()
    return doc_to_dict(doc) or {}


@marketplace_bp.route('/')
def index():
    db = get_db()
    settings = _get_settings(db)

    featured_limit = settings.get('homepage_featured_limit', 6)
    trending_limit = settings.get('homepage_trending_limit', 4)

    featured = query_to_list(
        db.collection('products')
        .where('status', '==', 'active')
        .where('tags', 'array_contains', 'featured')
        .limit(featured_limit)
    )
    trending = query_to_list(
        db.collection('products')
        .where('status', '==', 'active')
        .where('tags', 'array_contains', 'trending')
        .limit(trending_limit)
    )
    new_arrivals = query_to_list(
        db.collection('products')
        .where('status', '==', 'active')
        .order_by('created_at', direction='DESCENDING')
        .limit(4)
    )
    categories = query_to_list(
        db.collection('categories').where('active', '==', True)
    )
    return render_template('index.html',
        featured=[serialize_doc(p) for p in featured],
        trending=[serialize_doc(p) for p in trending],
        new_arrivals=[serialize_doc(p) for p in new_arrivals],
        categories=[serialize_doc(c) for c in categories],
        settings=serialize_doc(settings)
    )


@marketplace_bp.route('/marketplace')
def marketplace():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 12
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    sort = request.args.get('sort', 'latest')

    query = db.collection('products').where('status', '==', 'active')
    if category:
        query = query.where('category', '==', category)
    if tag:
        query = query.where('tags', 'array_contains', tag)

    sort_field_map = {
        'latest': ('created_at', 'DESCENDING'),
        'popular': ('sales_count', 'DESCENDING'),
        'price_asc': ('price', 'ASCENDING'),
        'price_desc': ('price', 'DESCENDING'),
    }
    sort_field, sort_dir = sort_field_map.get(sort, ('created_at', 'DESCENDING'))
    query = query.order_by(sort_field, direction=sort_dir)

    all_products = query_to_list(query)
    total = len(all_products)
    start = (page - 1) * per_page
    products = all_products[start:start + per_page]

    categories = query_to_list(db.collection('categories').where('active', '==', True))
    total_pages = math.ceil(total / per_page) if total else 1

    return render_template('marketplace.html',
        products=[serialize_doc(p) for p in products],
        categories=[serialize_doc(c) for c in categories],
        page=page, total=total, total_pages=total_pages,
        current_category=category, current_tag=tag, current_sort=sort,
        per_page=per_page
    )


@marketplace_bp.route('/product/<product_id>')
def product_detail(product_id):
    db = get_db()
    prod_doc = db.collection('products').document(product_id).get()
    product = doc_to_dict(prod_doc)
    if not product or product.get('status') != 'active':
        return render_template('404.html'), 404

    reviews = query_to_list(
        db.collection('reviews')
        .where('product_id', '==', product_id)
        .where('approved', '==', True)
        .order_by('created_at', direction='DESCENDING')
        .limit(10)
    )
    avg_rating = round(sum(r.get('rating', 0) for r in reviews) / len(reviews), 1) if reviews else 0

    related = query_to_list(
        db.collection('products')
        .where('status', '==', 'active')
        .where('category', '==', product.get('category', ''))
        .limit(5)
    )
    related = [r for r in related if r['_id'] != product_id][:4]

    # Increment view count
    db.collection('products').document(product_id).update({'view_count': firestore_increment(1)})

    purchased = False
    in_wishlist = False
    if session.get('user_email'):
        orders = query_to_list(
            db.collection('orders')
            .where('user_email', '==', session['user_email'])
            .where('payment_status', '==', 'paid')
        )
        purchased = any(
            any(item.get('product_id') == product_id for item in o.get('items', []))
            for o in orders
        )
        safe_email = session['user_email'].replace('.', '_').replace('@', '__')
        user_doc = db.collection('users').document(safe_email).get()
        if user_doc.exists:
            in_wishlist = product_id in (user_doc.to_dict().get('wishlist', []))

    return render_template('product_detail.html',
        product=serialize_doc(product),
        reviews=[serialize_doc(r) for r in reviews],
        avg_rating=avg_rating,
        related=[serialize_doc(p) for p in related],
        purchased=purchased,
        in_wishlist=in_wishlist
    )


def firestore_increment(n):
    from firebase_admin import firestore
    return firestore.Increment(n)


@marketplace_bp.route('/api/search')
def live_search():
    db = get_db()
    q = request.args.get('q', '').strip().lower()
    if len(q) < 2:
        return jsonify({"results": []})
    all_products = query_to_list(
        db.collection('products').where('status', '==', 'active').limit(200)
    )
    results = [
        p for p in all_products
        if q in p.get('title', '').lower() or q in p.get('description', '').lower()
    ][:8]
    return jsonify({"results": [serialize_doc(r) for r in results]})


@marketplace_bp.route('/about')
def about():
    return render_template('about.html')


@marketplace_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        db = get_db()
        db.collection('notifications').add({
            "user_email": "admin",
            "title": f"Contact from {request.form.get('name')}",
            "message": request.form.get('message'),
            "type": "contact",
            "email": request.form.get('email'),
            "read": False,
            "created_at": datetime.utcnow()
        })
        return jsonify({"status": "ok", "message": "Message sent successfully!"})
    return render_template('contact.html')


@marketplace_bp.route('/faq')
def faq():
    return render_template('faq.html')


@marketplace_bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy.html')


@marketplace_bp.route('/terms-and-conditions')
def terms():
    return render_template('terms.html')


@marketplace_bp.route('/refund-policy')
def refund_policy():
    return render_template('refund.html')


@marketplace_bp.route('/digital-delivery-policy')
def digital_delivery():
    return render_template('digital_delivery.html')


@marketplace_bp.route('/license-agreement')
def license():
    return render_template('license.html')


@marketplace_bp.route('/support-policy')
def support_policy():
    return render_template('support_policy.html')


@marketplace_bp.route('/custom-development', methods=['GET', 'POST'])
def custom_development():
    if request.method == 'POST':
        if not session.get('user_email'):
            return jsonify({"error": "Login required"}), 401
        db = get_db()
        data = request.get_json() or request.form.to_dict()
        db.collection('custom_orders').add({
            "user_email": session['user_email'],
            "discord_username": data.get('discord_username'),
            "project_name": data.get('project_name'),
            "bot_type": data.get('bot_type'),
            "required_features": data.get('required_features'),
            "budget": data.get('budget'),
            "delivery_time": data.get('delivery_time'),
            "reference_links": data.get('reference_links', ''),
            "status": "pending",
            "created_at": datetime.utcnow(),
        })
        return jsonify({"status": "ok", "message": "Your request has been submitted!"})
    return render_template('custom_dev.html')
