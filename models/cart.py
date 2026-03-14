from extensions import db


class Cart(db.Model):

    __tablename__ = "cart"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id"),
        nullable=False
    )

    table_number = db.Column(
        db.Integer,
        nullable=False
    )

    food_id = db.Column(
        db.Integer,
        db.ForeignKey("menu.id"),
        nullable=False
    )

    qty = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )