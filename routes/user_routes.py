from flask import Blueprint, request, jsonify
import os, json, uuid

user_bp = Blueprint("user_bp", __name__)

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ================= GET USERS =================
@user_bp.route("/api/users", methods=["GET"])
def get_users():
    return jsonify(load_users())

# ================= CREATE USER =================
@user_bp.route("/api/users", methods=["POST"])
def create_user():
    data = request.json

    if not data or not data.get("name"):
        return jsonify({"error": "Name required"}), 400

    users = load_users()

    new_user = {
        "user_id": "user_" + uuid.uuid4().hex[:6],
        "name": data.get("name"),
        "age": data.get("age"),
        "weight": data.get("weight"),
        "height": data.get("height"),
        "vo2": data.get("vo2")
    }

    users.append(new_user)
    save_users(users)

    return jsonify(new_user)