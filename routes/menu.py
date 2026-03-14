from flask import Blueprint, render_template, request, redirect
from services.db import get_db

menu = Blueprint("menu", __name__)


@menu.route("/menu/<int:restaurant_id>")
def show_menu(restaurant_id):

    db = get_db()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "menu.html",
        foods=foods,
        restaurant_id=restaurant_id
    )