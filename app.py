import os
import secrets
import time
from datetime import timedelta
from flask import Flask, jsonify, redirect, session, url_for, flash, request, g

from models.db import get_db
from utils.logging_config import setup_logging
from utils.time_utils import IST

# Constants
INACTIVITY_LIMIT_SECONDS = 600

def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        app.logger.warning("FLASK_SECRET_KEY not set. Using random key — sessions will not persist across restarts.")

    app.secret_key = secret_key

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
    )

    @app.before_request
    def generate_csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(32)
        g.csrf_token = session["_csrf_token"]

    @app.template_global()
    def csrf_token():
        return g.get("csrf_token", session.get("_csrf_token", ""))

    def validate_csrf():
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        token = request.headers.get("X-CSRFToken") or request.form.get("_csrf_token")
        if not token or not session.get("_csrf_token") or token != session["_csrf_token"]:
            return jsonify({"error": "Invalid CSRF token."}), 403
        return None

    @app.before_request
    def check_csrf():
        if request.endpoint and request.endpoint.startswith("static"):
            return None
        return validate_csrf()

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
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
