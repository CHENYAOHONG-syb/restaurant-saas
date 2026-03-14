from flask import Blueprint, request, redirect, jsonify, render_template
from services.db import get_db

orders = Blueprint("orders", __name__)


# ==============================
# 1️⃣ 客人 Checkout 下单
# ==============================

@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    # 创建订单
    cursor = db.execute(
        """
        INSERT INTO orders
        (restaurant_id, table_number, status)
        VALUES (?,?,?)
        """,
        (restaurant_id, table, "pending")
    )

    order_id = cursor.lastrowid

    # 获取购物车
    items = db.execute(
        """
        SELECT food_id, qty
        FROM cart
        WHERE table_number=? AND restaurant_id=?
        """,
        (table, restaurant_id)
    ).fetchall()

    # 写入 order_items
    for item in items:

        db.execute(
            """
            INSERT INTO order_items (order_id, food_id, qty)
            VALUES (?,?,?)
            """,
            (order_id, item["food_id"], item["qty"])
        )

    # 清空购物车
    db.execute(
        """
        DELETE FROM cart
        WHERE table_number=? AND restaurant_id=?
        """,
        (table, restaurant_id)
    )

    db.commit()

    return redirect(f"/orders/receipt/{order_id}")


# ==============================
# 2️⃣ 厨房 API
# ==============================

@orders.route("/api/orders/<int:restaurant_id>")
def api_orders(restaurant_id):

    db = get_db()

    rows = db.execute("""
    SELECT 
        orders.id,
        orders.table_number,
        orders.created_at,
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
                "items":[]
            }

        result[order_id]["items"].append({
            "name": r["name"],
            "qty": r["qty"]
        })

    orders_list = []

    for order_id,data in result.items():

        orders_list.append({
            "order_id":order_id,
            "table":data["table"],
            "created":data["created"],
            "items":data["items"]
        })

    return jsonify({"orders":orders_list})


# ==============================
# 3️⃣ Kitchen Screen
# ==============================

@orders.route("/kitchen/<int:restaurant_id>")
def kitchen(restaurant_id):

    return render_template(
        "kitchen.html",
        restaurant_id=restaurant_id
    )


# ==============================
# 4️⃣ Customer QR Menu
# ==============================

@orders.route("/r/<slug>")
def restaurant_menu(slug):

    table = request.args.get("table", "1")

    db = get_db()

    restaurant = db.execute(
        "SELECT * FROM restaurants WHERE slug=?",
        (slug,)
    ).fetchone()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant["id"],)
    ).fetchall()

    return render_template(
        "menu.html",
        foods=foods,
        table=table,
        restaurant_id=restaurant["id"],
        restaurant=restaurant
    )


# ==============================
# 5️⃣ Receipt 页面
# ==============================

@orders.route("/receipt/<int:order_id>")
def receipt(order_id):

    db = get_db()

    items = db.execute("""
    SELECT menu.name, order_items.qty
    FROM order_items
    JOIN menu ON order_items.food_id = menu.id
    WHERE order_items.order_id=?
    """,(order_id,)).fetchall()

    return render_template(
        "receipt.html",
        items=items,
        order_id=order_id
    )
# ==============================
# ADD TO CART
# ==============================
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