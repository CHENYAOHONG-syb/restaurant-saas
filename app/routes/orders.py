from flask import Blueprint, jsonify, request, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.order_service import add_to_cart, checkout

@orders.route("/add_to_cart", methods=["POST"])
def add():
    add_to_cart(
        food_id=request.form.get("food_id"),
        table_number=request.form.get("table"),
        restaurant_id=1
    )
    return redirect("/orders/cart")


@orders.route("/checkout", methods=["POST"])
def do_checkout():
    checkout(
        table_number=request.form.get("table"),
        restaurant_id=1
    )
    return redirect("/orders")