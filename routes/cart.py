from flask import Blueprint, render_template, request, jsonify, session
from models.db import get_db, doc_to_dict
from utils.helpers import serialize_doc
from utils.decorators import api_login_required, login_required
from datetime import datetime

cart_bp = Blueprint('cart', __name__)


def _safe_email(email):
    return email.replace('.', '_').replace('@', '__')


def _get_or_create_cart(db, email):
    ref = db.collection('carts').document(_safe_email(email))
    doc = ref.get()
    if not doc.exists:
        ref.set({"user_email": email, "items": [], "updated_at": datetime.utcnow()})
        doc = ref.get()
    d = doc.to_dict()
    d['_id'] = doc.id
    return d


@cart_bp.route('/cart')
@login_required
def cart():
    db = get_db()
    cart = _get_or_create_cart(db, session['user_email'])
    items_detail = []
    for item in cart.get('items', []):
        prod_doc = db.collection('products').document(item['product_id']).get()
        prod = doc_to_dict(prod_doc)
        if prod and prod.get('status') == 'active':
            p = serialize_doc(prod)
            p['quantity'] = item.get('quantity', 1)
            items_detail.append(p)
    subtotal = sum((float(i.get('discount_price') or i.get('price', 0))) * i['quantity'] for i in items_detail)
    return render_template('cart.html', items=items_detail, subtotal=subtotal)


@cart_bp.route('/api/cart/add', methods=['POST'])
@api_login_required
def add_to_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if not product_id:
        return jsonify({"error": "Product ID required"}), 400

    prod_doc = db.collection('products').document(product_id).get()
    if not prod_doc.exists:
        return jsonify({"error": "Product not found"}), 404

    ref = db.collection('carts').document(_safe_email(session['user_email']))
    cart = _get_or_create_cart(db, session['user_email'])
    items = cart.get('items', [])

    for item in items:
        if item['product_id'] == product_id:
            item['quantity'] = item.get('quantity', 1) + quantity
            ref.update({"items": items, "updated_at": datetime.utcnow()})
            return jsonify({"status": "ok", "message": "Cart updated", "count": len(items)})

    items.append({"product_id": product_id, "quantity": quantity})
    ref.update({"items": items, "updated_at": datetime.utcnow()})
    return jsonify({"status": "ok", "message": "Added to cart", "count": len(items)})


@cart_bp.route('/api/cart/remove', methods=['POST'])
@api_login_required
def remove_from_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    ref = db.collection('carts').document(_safe_email(session['user_email']))
    cart = _get_or_create_cart(db, session['user_email'])
    items = [i for i in cart.get('items', []) if i['product_id'] != product_id]
    ref.update({"items": items, "updated_at": datetime.utcnow()})
    return jsonify({"status": "ok", "count": len(items)})


@cart_bp.route('/api/cart/update', methods=['POST'])
@api_login_required
def update_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if quantity < 1:
        return jsonify({"error": "Quantity must be >= 1"}), 400
    ref = db.collection('carts').document(_safe_email(session['user_email']))
    cart = _get_or_create_cart(db, session['user_email'])
    items = cart.get('items', [])
    for item in items:
        if item['product_id'] == product_id:
            item['quantity'] = quantity
            break
    ref.update({"items": items, "updated_at": datetime.utcnow()})
    return jsonify({"status": "ok"})


@cart_bp.route('/api/cart/count')
def cart_count():
    if not session.get('user_email'):
        return jsonify({"count": 0})
    db = get_db()
    ref = db.collection('carts').document(_safe_email(session['user_email']))
    doc = ref.get()
    count = len(doc.to_dict().get('items', [])) if doc.exists else 0
    return jsonify({"count": count})
