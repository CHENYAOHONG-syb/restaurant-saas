from flask import Blueprint, render_template, request, redirect
from models.menu import Menu
from extensions import db

menu = Blueprint("menu", __name__)


@menu.route("/menu/<int:restaurant_id>")
def show_menu(restaurant_id):

    foods = Menu.query.filter_by(
        restaurant_id=restaurant_id
    ).all()

    return render_template(
        "menu.html",
        foods=foods,
        restaurant_id=restaurant_id
    )


@menu.route("/add_food", methods=["POST"])
def add_food():

    name = request.form.get("name")
    price = request.form.get("price")
    restaurant_id = request.form.get("restaurant_id")

    food = Menu(
        name=name,
        price=price,
        restaurant_id=restaurant_id
    )

    db.session.add(food)
    db.session.commit()

    return redirect(request.referrer)