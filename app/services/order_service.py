from app.extensions import db
from app.models.order import Order

def create_order(customer_id, total):

    order = Order(customer_id=customer_id, total=total)

    db.session.add(order)
    db.session.commit()

    return order