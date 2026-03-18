from flask import Blueprint, request, jsonify,render_template
from app.services.restaurant_service import create_restaurant

platform = Blueprint("platform", __name__)

@platform.route("/")
def home():
    return "Server is working"

@platform.route("/login_page")
def login_page():
    return render_template("login.html")

@platform.route("/create_restaurant", methods=["POST"])
def create_restaurant_api():

    data = request.json

    restaurant = create_restaurant(
        data["name"],
        data.get("address")
    )

    return jsonify({
        "restaurant_id": restaurant.id
    })
