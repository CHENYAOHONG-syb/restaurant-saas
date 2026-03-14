from flask import Blueprint, render_template, request, redirect
from services.db import get_db

platform = Blueprint("platform", __name__)


@platform.route("/platform/admin")
def platform_admin():

    db = get_db()

    restaurants = db.execute(
        "SELECT COUNT(*) as count FROM restaurants"
    ).fetchone()["count"]

    orders = db.execute(
        "SELECT COUNT(*) as count FROM orders"
    ).fetchone()["count"]

    revenue = db.execute("""
        SELECT SUM(menu.price * order_items.qty) as total
        FROM orders
        JOIN order_items ON orders.id = order_items.order_id
        JOIN menu ON order_items.food_id = menu.id
        WHERE orders.status='done'
    """).fetchone()["total"]

    return render_template(
        "platform_admin.html",
        restaurants=restaurants,
        orders=orders,
        revenue=revenue
    )


@platform.route("/subscribe/<plan>", methods=["POST"])
def subscribe(plan):

    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
    """
    INSERT INTO subscriptions
    (restaurant_id,plan,status)
    VALUES (?,?,?)
    """,
    (restaurant_id,plan,"active")
    )

    db.commit()

    return redirect(f"/dashboard/{restaurant_id}")


@platform.route("/")
def landing():
    return render_template("index.html")