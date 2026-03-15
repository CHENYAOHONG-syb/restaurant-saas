from flask import Blueprint, request, redirect
from models.cart import Cart
from extensions import db

cart = Blueprint("cart", __name__)


@cart.route("/add_to_cart", methods=["POST"])
def add_to_cart():

    food_id = request.form.get("food_id")
    table = request.form.get("table")
    restaurant_id = request.form.get("restaurant_id")

    item = Cart(
        food_id=food_id,
        table_number=table,
        restaurant_id=restaurant_id,
        qty=1
    )

    db.session.add(item)
    db.session.commit()

    return redirect(request.referrer)