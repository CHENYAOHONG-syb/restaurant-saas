from extensions import db


class OrderItem(db.Model):

    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id"),
        nullable=False
    )

    food_id = db.Column(
        db.Integer,
        db.ForeignKey("menu.id"),
        nullable=False
    )

    qty = db.Column(
        db.Integer,
        nullable=False,
        default=1
    )