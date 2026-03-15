from flask import Blueprint, render_template, session, redirect
from flask_sqlalchemy import SQLAlchemy
from services.analytics import (
    most_popular_food,
    worst_food,
    peak_hour,
    average_order_value
)
from services.advisor import generate_advice
from services.subscription import check_subscription

dashboard = Blueprint("dashboard", __name__)


@dashboard.route("/dashboard/<int:restaurant_id>")
def show_dashboard(restaurant_id):

    if "user_id" not in session:
        return redirect("/login")

    if not check_subscription(restaurant_id):
        return "Subscription expired"

    db = get_db()

    popular = most_popular_food(restaurant_id)
    worst = worst_food(restaurant_id)
    peak = peak_hour(restaurant_id)
    avg = average_order_value(restaurant_id)
    advice = generate_advice(restaurant_id)

    rows = db.execute("""
        SELECT strftime('%H',created_at) as hour,
        COUNT(*) as total
        FROM orders
        WHERE restaurant_id=?
        GROUP BY hour
    """,(restaurant_id,)).fetchall()

    hours = []
    counts = []

    for r in rows:
        hours.append(r["hour"])
        counts.append(r["total"])

    return render_template(
        "dashboard.html",
        popular=popular,
        worst=worst,
        peak=peak,
        avg=avg,
        advice=advice,
        hours=hours,
        counts=counts
    )