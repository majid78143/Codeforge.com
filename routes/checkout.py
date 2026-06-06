from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models.db import get_db, doc_to_dict, query_to_list
from utils.helpers import serialize_doc, add_notification
from utils.decorators import login_required, api_login_required
from datetime import datetime
import razorpay
import uuid

checkout_bp = Blueprint('checkout', __name__)


def _safe_email(email):
    return email.replace('.', '_').replace('@', '__')


def _get_razorpay_client(db):
    settings = doc_to_dict(db.collection('settings').document('store').get()) or {}
    key_id = settings.get('razorpay_key_id', '')
    key_secret = settings.get('razorpay_key_secret', '')
    if not key_id or not key_secret:
        return None, None, None
    return razorpay.Client(auth=(key_id, key_secret)), key_id, key_secret


@checkout_bp.route('/checkout')
@login_required
def checkout():
    db = get_db()
    cart_ref = db.collection('carts').document(_safe_email(session['user_email']))
    cart_doc = cart_ref.get()
    if not cart_doc.exists or not cart_doc.to_dict().get('items'):
        return redirect(url_for('cart.cart'))

    items_detail = []
    for item in cart_doc.to_dict().get('items', []):
        prod = doc_to_dict(db.collection('products').document(item['product_id']).get())
        if prod and prod.get('status') == 'active':
            p = serialize_doc(prod)
            p['quantity'] = item.get('quantity', 1)
            items_detail.append(p)

    subtotal = sum((float(i.get('discount_price') or i.get('price', 0))) * i['quantity'] for i in items_detail)
    settings = doc_to_dict(db.collection('settings').document('store').get()) or {}
    tax = subtotal * (settings.get('tax_percent', 0) / 100)
    return render_template('checkout.html', items=items_detail, subtotal=subtotal, tax=tax,
                           total=subtotal + tax, settings=serialize_doc(settings))


@checkout_bp.route('/api/coupon/validate', methods=['POST'])
@api_login_required
def validate_coupon():
    db = get_db()
    data = request.get_json()
    code = data.get('coupon_code', '').strip().upper()
    order_total = float(data.get('order_total', 0))

    coupons = query_to_list(
        db.collection('coupons').where('coupon_code', '==', code).where('active_status', '==', True).limit(1)
    )
    if not coupons:
        return jsonify({"valid": False, "message": "Invalid coupon code"})
    coupon = coupons[0]

    now = datetime.utcnow()
    expiry = coupon.get('expiry_date')
    if expiry and hasattr(expiry, 'replace'):
        if expiry < now:
            return jsonify({"valid": False, "message": "Coupon has expired"})

    if coupon.get('minimum_order_value', 0) > order_total:
        return jsonify({"valid": False, "message": f"Minimum order ₹{coupon['minimum_order_value']} required"})

    usage = query_to_list(db.collection('coupon_usage').where('coupon_code', '==', code))
    if coupon.get('usage_limit', 0) > 0 and len(usage) >= coupon['usage_limit']:
        return jsonify({"valid": False, "message": "Coupon usage limit reached"})

    user_usage = [u for u in usage if u.get('user_email') == session['user_email']]
    if coupon.get('per_user_limit', 0) > 0 and len(user_usage) >= coupon['per_user_limit']:
        return jsonify({"valid": False, "message": "You have already used this coupon"})

    if coupon['discount_type'] == 'percentage':
        discount = order_total * (coupon['discount_value'] / 100)
    else:
        discount = min(coupon['discount_value'], order_total)

    return jsonify({"valid": True, "discount": round(discount, 2),
                    "message": f"Coupon applied! Saved ₹{discount:.2f}"})


@checkout_bp.route('/api/payment/create-order', methods=['POST'])
@api_login_required
def create_payment_order():
    db = get_db()
    data = request.get_json()
    coupon_code = data.get('coupon_code', '').strip().upper()

    cart_doc = db.collection('carts').document(_safe_email(session['user_email'])).get()
    if not cart_doc.exists or not cart_doc.to_dict().get('items'):
        return jsonify({"error": "Cart is empty"}), 400

    items_detail = []
    for item in cart_doc.to_dict().get('items', []):
        prod = doc_to_dict(db.collection('products').document(item['product_id']).get())
        if prod and prod.get('status') == 'active':
            p = serialize_doc(prod)
            p['quantity'] = item.get('quantity', 1)
            items_detail.append(p)

    subtotal = sum((float(i.get('discount_price') or i.get('price', 0))) * i['quantity'] for i in items_detail)
    settings = doc_to_dict(db.collection('settings').document('store').get()) or {}
    tax = subtotal * (settings.get('tax_percent', 0) / 100)
    discount = 0
    coupon_doc = None

    if coupon_code:
        coupons = query_to_list(
            db.collection('coupons').where('coupon_code', '==', coupon_code).where('active_status', '==', True).limit(1)
        )
        if coupons:
            coupon_doc = coupons[0]
            if coupon_doc['discount_type'] == 'percentage':
                discount = (subtotal + tax) * (coupon_doc['discount_value'] / 100)
            else:
                discount = min(coupon_doc['discount_value'], subtotal + tax)

    total = subtotal + tax - discount
    amount_paise = int(total * 100)

    rz_client, key_id, key_secret = _get_razorpay_client(db)
    if not rz_client:
        return jsonify({"error": "Payment gateway not configured. Contact support."}), 503

    receipt_id = f"order_{uuid.uuid4().hex[:12]}"
    try:
        rz_order = rz_client.order.create({
            "amount": amount_paise,
            "currency": settings.get('currency', 'INR'),
            "receipt": receipt_id,
            "payment_capture": 1
        })
    except Exception as e:
        return jsonify({"error": f"Payment gateway error: {str(e)}"}), 500

    order_doc = {
        "order_id": receipt_id,
        "razorpay_order_id": rz_order['id'],
        "user_email": session['user_email'],
        "items": items_detail,
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "discount": round(discount, 2),
        "coupon_code": coupon_code if coupon_code else None,
        "total": round(total, 2),
        "payment_status": "pending",
        "created_at": datetime.utcnow(),
    }
    db.collection('orders').document(receipt_id).set(order_doc)

    return jsonify({
        "key_id": key_id,
        "order_id": rz_order['id'],
        "amount": amount_paise,
        "currency": settings.get('currency', 'INR'),
        "receipt": receipt_id,
        "prefill": {"email": session['user_email'], "name": session.get('user_name', '')}
    })


@checkout_bp.route('/api/payment/verify', methods=['POST'])
@api_login_required
def verify_payment():
    db = get_db()
    data = request.get_json()
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')

    rz_client, key_id, key_secret = _get_razorpay_client(db)
    if not rz_client:
        return jsonify({"error": "Gateway not configured"}), 503

    try:
        rz_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
    except razorpay.errors.SignatureVerificationError:
        db.collection('payments').add({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "status": "failed",
            "user_email": session['user_email'],
            "timestamp": datetime.utcnow()
        })
        return jsonify({"status": "failed", "message": "Payment verification failed"}), 400

    # Find order by razorpay_order_id
    orders = query_to_list(
        db.collection('orders').where('razorpay_order_id', '==', razorpay_order_id).limit(1)
    )
    order = orders[0] if orders else None

    if order:
        db.collection('orders').document(order['order_id']).update({
            "payment_status": "paid",
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
            "paid_at": datetime.utcnow()
        })
        if order.get('coupon_code'):
            db.collection('coupon_usage').add({
                "coupon_code": order['coupon_code'],
                "user_email": session['user_email'],
                "order_id": order['order_id'],
                "used_at": datetime.utcnow()
            })
        # Increment product sales count
        from firebase_admin import firestore as fs
        for item in order.get('items', []):
            pid = item.get('product_id') or item.get('_id')
            if pid:
                db.collection('products').document(pid).update({
                    'sales_count': fs.Increment(item.get('quantity', 1))
                })
        # Clear cart
        db.collection('carts').document(
            session['user_email'].replace('.', '_').replace('@', '__')
        ).update({"items": []})

        db.collection('payments').add({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
            "amount": order.get('total'),
            "status": "success",
            "user_email": session['user_email'],
            "order_id": order['order_id'],
            "timestamp": datetime.utcnow()
        })
        add_notification(db, session['user_email'], "Payment Successful!",
                         f"Order #{order['order_id']} confirmed.", "success")

    return jsonify({"status": "ok", "order_id": order['order_id'] if order else ""})


@checkout_bp.route('/order-success/<order_id>')
@login_required
def order_success(order_id):
    db = get_db()
    order_doc = db.collection('orders').document(order_id).get()
    order = doc_to_dict(order_doc)
    if not order or order.get('user_email') != session['user_email']:
        return render_template('404.html'), 404
    return render_template('order_success.html', order=serialize_doc(order))
