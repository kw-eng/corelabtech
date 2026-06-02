from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from auth.user_model import get_user_by_email
from security.limiter import limiter


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():

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

        login_user(user)

        return redirect("/chamber")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect("/login")


@auth_bp.route("/profile")
@login_required
def profile():

    return render_template("profile.html")