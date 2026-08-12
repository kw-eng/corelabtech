"""Flask application factory-style entrypoint for CoreLabTech.

This module wires security extensions, blueprints and Flask-Login together.
It is imported by Docker/Gunicorn and can also be run directly for local dev.
"""

import os
import time
from datetime import timedelta

from flask import g, redirect, render_template, request, url_for
from flask_login import LoginManager
from auth.auth_routes import auth_bp
from auth.user_model import get_user_by_id
from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from security.limiter import limiter
from security.headers import configure_security_headers
from security.csrf import csrf
from services.logger_service import access_logger, app_logger, error_logger
from services.i18n_service import (
    LOCALE_COOKIE_NAME,
    SUPPORTED_LOCALES,
    catalog_for,
    current_locale,
    locale_from_request,
    normalize_locale,
    translate,
)
from services.public_media_service import resolve_public_media

# =========================
# BLUEPRINTS
# =========================
from routes.main_routes import main_bp
from routes.research_routes import research_bp
from routes.ai_routes import ai_bp
from routes.ai_qa_routes import ai_qa_bp
from routes.qa_routes import qa_bp
from routes.publication_routes import pub_bp
#  from routes.user_routes import user_bp
from routes.telemetry_routes import telemetry_bp
from routes.performance_routes import performance_bp
from routes.health_routes import health_bp
from routes.content_studio_routes import content_studio_bp
from routes.public_media_routes import public_media_bp


def ensure_runtime_directories():
    """Create folders that the app writes to at runtime.

    Docker images may start with an empty mounted volume, so uploads, logs and
    performance result directories must exist before the first request.
    """

    for path in (
        "logs",
        "data",
        "data/uploads",
        "data/uploads/fit",
        "data/uploads/csv",
        "data/uploads/temp",
        "data/performance",
    ):
        os.makedirs(path, exist_ok=True)


# =========================
# APP
# =========================
ensure_runtime_directories()
app = Flask(__name__)
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
)

APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).lower()
IS_PRODUCTION = APP_ENV == "production"

PRODUCTION_SECRET_KEY_PLACEHOLDERS = {
    "dev-secret-change-me",
    "change-me",
    "change_me",
    "corelabtech",
}


def validate_secret_key_for_environment(
    secret_key: str | None, *, is_production: bool
) -> None:
    """Fail closed for weak Flask signing keys in production only."""

    if not is_production:
        return

    normalized_secret_key = (secret_key or "").strip()
    if (
        len(normalized_secret_key) < 32
        or normalized_secret_key.lower() in PRODUCTION_SECRET_KEY_PLACEHOLDERS
    ):
        raise RuntimeError(
            "SECRET_KEY must be set to a strong, non-default value in production."
        )


secret_key = os.getenv("SECRET_KEY")
validate_secret_key_for_environment(secret_key, is_production=IS_PRODUCTION)

app.secret_key = secret_key or "dev-secret-change-me"
app.config["DEBUG_ROUTES_ENABLED"] = (
    os.getenv("DISABLE_DEBUG_ROUTES", "true").lower() != "true"
)
app.config["INTERNAL_TOOLS_ENABLED"] = (
    os.getenv("INTERNAL_TOOLS_ENABLED", "false").lower() == "true"
)
# =========================================================
# CSRF
# =========================================================
csrf.init_app(app)
# =========================================================
# RATE LIMITER
# =========================================================
limiter.init_app(app)

# =========================================================
# SECURITY HEADERS
# =========================================================

configure_security_headers(app)





cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

if cors_origins:
    CORS(
        app,
        origins=cors_origins,
        supports_credentials=True,
    )
elif not IS_PRODUCTION:
    CORS(app)

# =========================
# REGISTER BLUEPRINTS
# =========================
app.register_blueprint(main_bp)
app.register_blueprint(research_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(pub_bp)
app.register_blueprint(content_studio_bp)
app.register_blueprint(public_media_bp)
# app.register_blueprint(user_bp)
app.register_blueprint(telemetry_bp)
if app.config["INTERNAL_TOOLS_ENABLED"]:
    app.register_blueprint(ai_qa_bp)
    app.register_blueprint(qa_bp)
    app.register_blueprint(performance_bp)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "True" if IS_PRODUCTION else "False") == "True"
)
app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config["REMEMBER_COOKIE_SAMESITE"] = os.getenv("REMEMBER_COOKIE_SAMESITE", "Lax")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", "480"))
)
app.register_blueprint(auth_bp)
app.register_blueprint(health_bp)


@app.before_request
def start_request_timer():
    """Capture request start time for access logging."""

    g.request_started_at = time.time()
    g.locale = locale_from_request(request)
    g.persist_locale = bool(request.args.get("lang"))


@app.after_request
def log_request(response):
    """Write compact access logs for operational monitoring."""

    duration_ms = round(
        (time.time() - getattr(g, "request_started_at", time.time())) * 1000,
        2,
    )

    access_logger.info(
        "%s %s %s %s %.2fms",
        request.remote_addr or "-",
        request.method,
        request.path,
        response.status_code,
        duration_ms,
    )

    if getattr(g, "persist_locale", False):
        response.set_cookie(
            LOCALE_COOKIE_NAME,
            current_locale(),
            max_age=60 * 60 * 24 * 365,
            samesite="Lax",
            secure=IS_PRODUCTION,
        )

    return response


@app.context_processor
def inject_i18n():
    """Expose translation helpers and frontend catalog to templates."""

    locale = current_locale()
    def public_media(role: str, media_type: str | None = None):
        media = resolve_public_media(role, locale, media_type)
        if media is None:
            return None
        return {
            "url": url_for("public_media.serve_public_media", role=role),
            # Poster role support is intentionally deferred until a curated
            # mapping model can reference a separately served public role.
            "poster_url": None,
            "media_type": media["media_type"],
            "mime_type": media.get("mime_type"),
            "alt_text": media["alt_text"],
            "width": media.get("width"),
            "height": media.get("height"),
        }

    return {
        "t": translate,
        "current_locale": locale,
        "supported_locales": SUPPORTED_LOCALES,
        "i18n_catalog": catalog_for(locale),
        "public_media": public_media,
    }


@app.route("/set-language/<locale>")
def set_language(locale: str):
    """Persist a preferred interface language and return to the current page."""

    selected_locale = normalize_locale(locale)
    next_url = request.args.get("next") or request.referrer or url_for("main.home")
    response = redirect(next_url)
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        selected_locale,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        secure=IS_PRODUCTION,
    )
    return response
# =========================
# LOGIN MANAGER
# =========================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."


@login_manager.user_loader
def load_user(user_id):
    """Resolve Flask-Login's session user id into a User object."""

    return get_user_by_id(user_id)
                          
                          
# =========================
# PAGES
# =========================
@app.route("/ai")
def ai_monitoring():
    """Public alias for the physiology monitoring view."""

    return render_template("physiology_monitoring.html")


@app.errorhandler(403)
def forbidden(e):
    """Render the role/permission error page."""

    return render_template("unauthorized.html"), 403


@app.errorhandler(401)
def unauthorized(e):
    """Redirect anonymous users to login instead of returning raw 401 HTML."""

    return redirect(url_for("auth.login"))


@app.errorhandler(500)
def internal_error(e):
    """Log unexpected errors and avoid exposing stack traces to users."""

    error_logger.exception(
        "Unhandled server error on %s %s",
        request.method,
        request.path,
    )

    if request.path.startswith("/api/"):
        return {
            "status": "error",
            "error": "internal_server_error",
        }, 500

    return render_template("unauthorized.html"), 500


app_logger.info(
    "CoreLabTech app configured env=%s debug_routes=%s cors_origins=%s",
    APP_ENV,
    app.config["DEBUG_ROUTES_ENABLED"],
    bool(cors_origins),
)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "False") == "True"

    app.run(
        debug=debug_enabled,
        use_reloader=debug_enabled
    )
