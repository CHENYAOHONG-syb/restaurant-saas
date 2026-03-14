from models.order import Order
from models.order_item import OrderItem
from extensions import db

orders = Blueprint("orders", __name__)

@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO orders
        (restaurant_id,table_number,status)
        VALUES (?,?,?)
        """,
        (restaurant_id,table,"pending")
    )

    order_id = cursor.lastrowid

    items = db.execute(
        """
        SELECT food_id,qty
        FROM cart
        WHERE table_number=? AND restaurant_id=?
        """,
        (table,restaurant_id)
    ).fetchall()

    for item in items:

        db.execute(
            """
            INSERT INTO order_items
            (order_id,food_id,qty)
            VALUES (?,?,?)
            """,
            (order_id,item["food_id"],item["qty"])
        )

    db.execute(
        """
        DELETE FROM cart
        WHERE table_number=? AND restaurant_id=?
        """,
        (table,restaurant_id)
    )

    db.commit()

    return redirect(f"/orders/receipt/{order_id}")

@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    order = Order(
        restaurant_id=restaurant_id,
        table_number=table,
        status="pending"
    )

    db.session.add(order)
    db.session.commit()

    return redirect(f"/orders/receipt/{order.id}")

orders_list = Order.query.filter_by(
    restaurant_id=restaurant_id
).all()