from flask import Blueprint, request, redirect, render_template
from app.extensions import db
from app.models.cart import Cart
from app.models.menu import Menu
from app.models.order import Order
from app.models.order_item import OrderItem


orders = Blueprint("orders", __name__)

@orders.route("/orders")
def view_orders():

    orders = Order.query.order_by(Order.created_at.desc()).all()

    return render_template("orders.html", orders=orders)

@orders.route("/add_to_cart", methods=["POST"])
def add_to_cart():

    food_id = request.form["food_id"]
    table = request.form["table"]

    # 👉 查有没有同样的 item
    existing = Cart.query.filter_by(
        food_id=food_id,
        table=table
    ).first()

    if existing:
        existing.quantity += 1
    else:
        cart = Cart(
            food_id=food_id,
            table=table,
            restaurant_id=1   # 👉 下一步换 JWT
        )
        db.session.add(cart)

    db.session.commit()

    return redirect(request.referrer)

@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]

    cart_items = Cart.query.filter_by(table=table).all()

    if not cart_items:
        return "Cart is empty"

    # 👉 创建订单
    order = Order(
        table=table,
        restaurant_id=1  # 👉 下一步换 JWT
    )

    db.session.add(order)
    db.session.commit()

    # 👉 把 cart → order_items
    for item in cart_items:
        order_item = OrderItem(
            order_id=order.id,
            food_id=item.food_id,
            quantity=item.quantity
        )
        db.session.add(order_item)

    # 👉 清空 cart
    Cart.query.filter_by(table=table).delete()

    db.session.commit()

    return redirect("/orders")