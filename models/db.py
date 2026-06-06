import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

_db = None


def get_db():
    global _db
    if _db is None:
        if not firebase_admin._apps:
            sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
            if sa_json:
                cred = credentials.Certificate(json.loads(sa_json))
                firebase_admin.initialize_app(cred)
            else:
                raise RuntimeError(
                    "FIREBASE_SERVICE_ACCOUNT environment variable not set. "
                    "Add your Firebase service account JSON to this env var."
                )
        _db = firestore.client()
        _seed_defaults(_db)
    return _db


def doc_to_dict(doc):
    """Convert a Firestore DocumentSnapshot to a plain dict with _id field."""
    if doc is None or not doc.exists:
        return None
    d = doc.to_dict()
    d['_id'] = doc.id
    return d


def query_to_list(query):
    """Stream a Firestore query and return list of dicts."""
    return [doc_to_dict(d) for d in query.stream()]


def _seed_defaults(db):
    settings_ref = db.collection('settings').document('store')
    if not settings_ref.get().exists:
        settings_ref.set({
            "key": "store",
            "site_name": "CodeForge Market",
            "site_tagline": "Premium Discord Bots & Automation Tools",
            "contact_email": "support@codeforgemarket.com",
            "razorpay_key_id": "",
            "razorpay_key_secret": "",
            "currency": "INR",
            "tax_percent": 0,
            "announcement": "",
            "announcement_active": False,
            "seo_title": "CodeForge Market - Premium Discord Bots",
            "seo_description": "Buy premium Discord bots, automation scripts, APIs and tools",
            "seo_keywords": "discord bot, automation, scripts, api, tools",
            "homepage_hero_title": "Premium Discord Bots & Automation Tools",
            "homepage_hero_subtitle": "Professional-grade bots, scripts, and tools for Discord servers",
            "homepage_hero_cta": "Browse Marketplace",
            "homepage_featured_limit": 6,
            "homepage_trending_limit": 4,
        })

    roles_col = db.collection('admin_roles')
    if not list(roles_col.limit(1).stream()):
        default_roles = [
            {"role": "super_admin",      "label": "Super Admin",      "permissions": ["all"]},
            {"role": "product_manager",  "label": "Product Manager",  "permissions": ["manage_products"]},
            {"role": "order_manager",    "label": "Order Manager",    "permissions": ["manage_orders"]},
            {"role": "support_manager",  "label": "Support Manager",  "permissions": ["manage_users", "manage_coupons"]},
        ]
        for r in default_roles:
            roles_col.document(r['role']).set(r)

