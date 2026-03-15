from flask import Blueprint, request, redirect
from models.order import Order
from models.order_item import OrderItem
from models.cart import Cart
from extensions import db

orders = Blueprint("orders", __name__)


@orders.route("/checkout", methods=["POST"])
def checkout():

    table = request.form.get("table")
    restaurant_id = request.form.get("restaurant_id")

    # 创建订单
    order = Order(
        restaurant_id=restaurant_id,
        table_number=table,
        status="pending"
    )

    db.session.add(order)
    db.session.commit()

    # 获取购物车
    items = Cart.query.filter_by(
        table_number=table,
        restaurant_id=restaurant_id
    ).all()

    # 写入 order_items
    for item in items:

        order_item = OrderItem(
            order_id=order.id,
            food_id=item.food_id,
            qty=item.qty
        )

        db.session.add(order_item)

    # 清空购物车
    Cart.query.filter_by(
        table_number=table,
        restaurant_id=restaurant_id
    ).delete()

    db.session.commit()

    return redirect(f"/orders/receipt/{order.id}")