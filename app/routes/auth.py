from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.user import User
from flask_jwt_extended import create_access_token

auth = Blueprint("auth", __name__)

@auth.route("/register", methods=["POST"])
def register():

    data = request.json

    user = User(
        username=data["username"],
        password=data["password"],  # 先简单做，后面再hash
        role="owner",
        restaurant_id=data["restaurant_id"]
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User created"})

@auth.route("/login", methods=["POST"])
def login():

    data = request.json

    user = User.query.filter_by(username=data["username"]).first()

    if not user or user.password != data["password"]:
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(
        identity={
            "user_id": user.id,
            "restaurant_id": user.restaurant_id
        }
    )

    return jsonify({
        "access_token": token
    })