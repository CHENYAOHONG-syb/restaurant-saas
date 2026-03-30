from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.exceptions import AppError
from app.services.restaurant_service import create_restaurant
from app.services.subscription_service import list_plans
from app.validation import validate_create_restaurant_input

platform = Blueprint("platform", __name__)


@platform.route("/")
def home():
    return render_template("landing.html", plans=list_plans())


@platform.route("/login_page")
def login_page():
    return redirect(url_for("auth.login"))


@platform.route("/restaurants/new", methods=["GET", "POST"])
def create_restaurant_page():
    if request.method == "GET":
        return render_template("create_restaurant.html")

    data = request.get_json(silent=True) or request.form
    try:
        payload = validate_create_restaurant_input(data)
        restaurant = create_restaurant(name=payload.name, address=payload.address)
    except AppError as exc:
        if request.is_json:
            return jsonify({"error": exc.message}), exc.status_code
        return (
            render_template(
                "create_restaurant.html",
                error=exc.message,
                form_data={"name": (data.get("name") or "").strip(), "address": (data.get("address") or "").strip()},
            ),
            exc.status_code,
        )

    if request.is_json:
        return jsonify({"restaurant_id": restaurant.id, "slug": restaurant.slug}), 201

    flash(f"{restaurant.name} is ready. Create the first owner account to continue.", "success")
    return redirect(url_for("auth.register", restaurant_id=restaurant.id))


@platform.route("/create_restaurant", methods=["POST"])
def create_restaurant_api():
    data = request.get_json(silent=True) or request.form
    try:
        payload = validate_create_restaurant_input(data)
        restaurant = create_restaurant(name=payload.name, address=payload.address)
    except AppError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"restaurant_id": restaurant.id, "slug": restaurant.slug}), 201
