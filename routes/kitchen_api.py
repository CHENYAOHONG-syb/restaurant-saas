from flask import Blueprint, jsonify
from flask_sqlalchemy import SQLAlchemy
from utils.security import login_required

kitchen_api = Blueprint('kitchen_api', __name__)


@kitchen_api.route('/api/orders/<int:restaurant_id>')
# remove login_required
def api_get_orders(restaurant_id):

    db = get_db()

    orders = db.execute(
        """
        SELECT id, table_number, status, created_at
        FROM orders
        WHERE restaurant_id=?
        AND status != 'done'
        ORDER BY created_at ASC
        """,
        (restaurant_id,)
    ).fetchall()

    result = []

    for order in orders:

        items = db.execute(
            """
            SELECT oi.qty, m.name
            FROM order_items oi
            JOIN menu m ON oi.food_id = m.id
            WHERE oi.order_id=?
            """,
            (order["id"],)
        ).fetchall()

        result.append({
            "order_id": order["id"],
            "table": order["table_number"],
            "status": order["status"],
            "created": order["created_at"],
            "items": [
                {"qty": i["qty"], "name": i["name"]}
                for i in items
            ]
        })

    return jsonify({"orders": result})