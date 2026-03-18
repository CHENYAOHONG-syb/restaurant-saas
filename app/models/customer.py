from app.extensions import db


class Customer(db.Model):

    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id"),
        nullable=False
    )

    name = db.Column(db.String(120))

    phone = db.Column(
        db.String(50),
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )
