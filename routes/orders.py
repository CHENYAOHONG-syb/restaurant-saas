from flask import Blueprint, request, redirect, jsonify, render_template
from services.db import get_db

orders = Blueprint("orders", __name__, url_prefix="/orders")


# =========================
# 1️⃣ Add to Cart
# =========================

@orders.route("/add_to_cart", methods=["POST"])
def add_to_cart():

    food_id = request.form["food_id"]
    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute("""
    INSERT INTO cart(food_id, table_number, restaurant_id, qty)
    VALUES (?,?,?,1)
    """,(food_id, table, restaurant_id))

    db.commit()

    return redirect(request.referrer)


# =========================
# 2️⃣ View Cart
# =========================

@orders.route("/cart/<int:restaurant_id>")
def view_cart(restaurant_id):

    table = request.args.get("table")

    db = get_db()

    items = db.execute("""
    SELECT menu.name, cart.qty
    FROM cart
    JOIN menu ON cart.food_id = menu.id
    WHERE cart.restaurant_id=? AND cart.table_number=?
    """,(restaurant_id, table)).fetchall()

    return render_template(
        "cart.html",
        items=items,
        restaurant_id=restaurant_id,
        table=table
    )


# =========================
# 3️⃣ Checkout
# =========================

@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    cursor = db.execute("""
    INSERT INTO orders(restaurant_id, table_number, status)
    VALUES (?,?,?)
    """,(restaurant_id, table, "pending"))

    order_id = cursor.lastrowid

    items = db.execute("""
    SELECT food_id, qty
    FROM cart
    WHERE restaurant_id=? AND table_number=?
    """,(restaurant_id, table)).fetchall()

    for item in items:

        db.execute("""
        INSERT INTO order_items(order_id, food_id, qty)
        VALUES (?,?,?)
        """,(order_id, item["food_id"], item["qty"]))

    db.execute("""
    DELETE FROM cart
    WHERE restaurant_id=? AND table_number=?
    """,(restaurant_id, table))

    db.commit()

    return redirect("/orders/kitchen/"+restaurant_id)


# =========================
# 4️⃣ Kitchen Screen
# =========================

@orders.route("/kitchen/<int:restaurant_id>")
def kitchen(restaurant_id):

    return render_template(
        "kitchen.html",
        restaurant_id=restaurant_id
    )


# =========================
# 5️⃣ Kitchen API
# =========================

@orders.route("/api/orders/<int:restaurant_id>")
def api_orders(restaurant_id):

    db = get_db()

    rows = db.execute("""
    SELECT 
        orders.id,
        orders.table_number,
        orders.created_at,
        orders.status,
        menu.name,
        order_items.qty
    FROM orders
    JOIN order_items ON orders.id = order_items.order_id
    JOIN menu ON order_items.food_id = menu.id
    WHERE orders.restaurant_id=? 
    AND orders.status!='done'
    ORDER BY orders.created_at
    """,(restaurant_id,)).fetchall()

    result = {}

    for r in rows:

        order_id = r["id"]

        if order_id not in result:

            result[order_id] = {
                "table": r["table_number"],
                "created": r["created_at"],
                "status": r["status"],
                "items":[]
            }

        result[order_id]["items"].append({
            "name": r["name"],
            "qty": r["qty"]
        })

    orders_list=[]

    for order_id,data in result.items():

        orders_list.append({
            "order_id":order_id,
            "table":data["table"],
            "created":data["created"],
            "status":data["status"],
            "items":data["items"]
        })

    return jsonify({"orders":orders_list})


# =========================
# 6️⃣ Update Order Status
# =========================

@orders.route("/update_status/<int:order_id>/<status>", methods=["POST"])
def update_status(order_id,status):

    db = get_db()

    db.execute("""
    UPDATE orders
    SET status=?
    WHERE id=?
    """,(status,order_id))

    db.commit()

    return "ok"