# =========================================
# MAIN ROUTES
# publiczne strony aplikacji
# =========================================

from flask import (
    Blueprint,
    render_template
)

# =========================================
# BLUEPRINT
# =========================================

main_bp = Blueprint("main", __name__)

# =========================================
# HOME
# =========================================

@main_bp.route("/")
def home():

    return render_template("index.html")


# =========================================
# TECHNOLOGY
# =========================================

@main_bp.route("/technology")
def technology():

    return render_template("technology.html")


# =========================================
# ABOUT
# =========================================

@main_bp.route("/about")
def about():

    return render_template("about.html")


# =========================================
# CONTACT
# =========================================

@main_bp.route("/contact")
def contact():

    return render_template("contact.html")


@main_bp.route("/wellness-start")
def wellness_start():

    return render_template("wellness_start.html")


@main_bp.route("/privacy")
def privacy():

    return render_template("privacy.html")


@main_bp.route("/terms")
def terms():

    return render_template("terms.html")
