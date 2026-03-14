from flask import Blueprint, render_template, request, redirect
from services.db import get_db

inventory = Blueprint("inventory", __name__)


@inventory.route("/admin/inventory/<int:restaurant_id>")
def show_inventory(restaurant_id):

    db = get_db()

    items = db.execute(
        "SELECT * FROM inventory WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin_inventory.html",
        items=items,
        restaurant_id=restaurant_id
    )