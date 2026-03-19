from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.cart import Cart
from app.extensions import db


def add_to_cart(food_id, table_number, restaurant_id):

    item = Cart.query.filter_by(
        food_id=food_id,
        table_number=table_number
    ).first()

    if item:
        item.quantity += 1
    else:
        item = Cart(
            food_id=food_id,
            table_number=table_number,
            restaurant_id=restaurant_id,
            quantity=1
        )
        db.session.add(item)

    db.session.commit()

    return item


def get_cart(table_number):
    return Cart.query.filter_by(table_number=table_number).all()


def remove_from_cart(cart_id):
    Cart.query.filter_by(id=cart_id).delete()
    db.session.commit()


def clear_cart(table_number):
    Cart.query.filter_by(table_number=table_number).delete()
    db.session.commit()


def checkout(table_number, restaurant_id):

    items = get_cart(table_number)

    if not items:
        return None

    order = Order(
        table_number=table_number,
        restaurant_id=restaurant_id,
        status="pending"
    )

    db.session.add(order)
    db.session.flush()

    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            food_id=item.food_id,
            quantity=item.quantity
        )
        db.session.add(order_item)

    clear_cart(table_number)

    db.session.commit()

    return order