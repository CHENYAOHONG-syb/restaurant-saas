from extensions import db

class Order(db.Model):

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id"),
        nullable=False
    )

    table_number = db.Column(db.Integer)

    status = db.Column(db.String(50))

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )