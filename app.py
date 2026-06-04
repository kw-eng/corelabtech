# app.py
import os
from flask import render_template, redirect, url_for
from flask_login import LoginManager
from auth.auth_routes import auth_bp
from auth.user_model import get_user_by_id
from flask import Flask, render_template
from flask_cors import CORS
from security.limiter import limiter
from security.headers import configure_security_headers
from security.csrf import csrf

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
from routes.upload_routes import upload_bp
from routes.performance_routes import performance_bp
from routes.health_routes import health_bp

# =========================
# APP
# =========================
from init_db import *
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
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





CORS(app)

# =========================
# REGISTER BLUEPRINTS
# =========================
app.register_blueprint(main_bp)
app.register_blueprint(research_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(ai_qa_bp)
app.register_blueprint(qa_bp)
app.register_blueprint(pub_bp)
# app.register_blueprint(user_bp)
app.register_blueprint(telemetry_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(performance_bp)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False") == "True"
app.register_blueprint(auth_bp)
app.register_blueprint(health_bp)
# =========================
# LOGIN MANAGER
# =========================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)
                          
                          
# =========================
# PAGES
# =========================
@app.route("/research")
def research_dashboard():
    return render_template("research_dashboard.html")


@app.route("/ai")
def ai_monitoring():
    return render_template("physiology_monitoring.html")


@app.route("/qa")
def qa_dashboard():
    return render_template("ai_qa_lab.html")


# =========================
# DEBUG
# =========================
print(app.url_map)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
    
@app.errorhandler(403)
def forbidden(e):
    return render_template("unauthorized.html"), 403


@app.errorhandler(401)
def unauthorized(e):
    return redirect(url_for("auth.login"))