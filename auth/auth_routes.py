"""Authentication routes for browser login, logout and profile views."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from auth.user_model import get_user_by_email
from security.limiter import limiter


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    """Authenticate a user by email/password and start a Flask-Login session."""

    if current_user.is_authenticated:
        return redirect("/chamber")

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = get_user_by_email(email)

        if not user:
            flash("Invalid email or password")
            return render_template("login.html")

        if not user.password_hash:
            flash("Account has no password configured")
            return render_template("login.html")

        if not check_password_hash(user.password_hash, password):
            flash("Invalid email or password")
            return render_template("login.html")

        if not user.is_active:
            flash("Account is inactive")
            return render_template("login.html")

        session.permanent = True
        login_user(user)

        return redirect("/chamber")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Clear the current Flask-Login session through a CSRF-protected request."""

    logout_user()

    return redirect("/login")


@auth_bp.route("/profile")
@login_required
def profile():
    """Render the profile page for the authenticated user."""

    return render_template("profile.html")
