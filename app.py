import os
import time
from datetime import timedelta
from flask import Flask, jsonify, redirect, session, url_for, flash, request

from models.db import get_db
from utils.logging_config import setup_logging
from utils.time_utils import IST

# Constants
INACTIVITY_LIMIT_SECONDS = 600

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secure_secret_key")

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
    )

    setup_logging()

    # Initialize DB
    get_db()

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.transactions import transactions_bp
    from routes.accounts import accounts_bp
    from routes.admin import admin_bp
    from routes.support import support_bp
    from routes.notifications import notifications_bp
    from routes.beneficiaries import beneficiaries_bp
    from routes.scheduled import scheduled_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(beneficiaries_bp)
    app.register_blueprint(scheduled_bp)

    @app.before_request
    def refresh_session_activity():
        if request.endpoint == "static":
            return None
        if "user_id" not in session:
            return None

        last_activity = session.get("last_activity")
        now_ts = time.time()
        if last_activity and now_ts - last_activity > INACTIVITY_LIMIT_SECONDS:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "Session expired due to inactivity."}), 401
            flash("Session expired due to inactivity.", "error")
            return redirect(url_for("auth.login_page"))

        session["last_activity"] = now_ts
        session.modified = True
        return None

    @app.errorhandler(404)
    def page_not_found(e):
        return redirect(url_for("main.home_page"))

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
