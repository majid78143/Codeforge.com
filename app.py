import os
from flask import Flask, render_template, session
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs('/tmp/flask_sessions', exist_ok=True)
    Session(app)
    csrf = CSRFProtect(app)

    from routes.auth import auth_bp
    from routes.marketplace import marketplace_bp
    from routes.cart import cart_bp
    from routes.checkout import checkout_bp
    from routes.user import user_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(marketplace_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template('500.html'), 500

    @app.context_processor
    def inject_globals():
        cart_count = 0
        notif_count = 0
        site_settings = {}

        try:
            from models.db import get_db, doc_to_dict, query_to_list
            db = get_db()

            if session.get('user_email'):
                safe = session['user_email'].replace('.', '_').replace('@', '__')
                cart_doc = db.collection('carts').document(safe).get()
                cart_count = len(cart_doc.to_dict().get('items', [])) if cart_doc.exists else 0

                notifs = query_to_list(
                    db.collection('notifications')
                    .where('user_email', '==', session['user_email'])
                    .where('read', '==', False)
                )
                notif_count = len(notifs)

            site_settings = doc_to_dict(db.collection('settings').document('store').get()) or {}
        except Exception:
            pass

        return dict(
            cart_count=cart_count,
            notif_count=notif_count,
            site_settings=site_settings,
            firebase_config=Config.FIREBASE_CONFIG,
            current_user_email=session.get('user_email'),
            current_user_name=session.get('user_name'),
            current_user_photo=session.get('user_photo'),
            admin_email=session.get('admin_email'),
            admin_role=session.get('admin_role'),
        )

    csrf.exempt(auth_bp)
    csrf.exempt(admin_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
