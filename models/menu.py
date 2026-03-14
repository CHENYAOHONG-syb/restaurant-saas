from extensions import db

class Menu(db.Model):

    __tablename__ = "menu"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id"),
        nullable=False
    )

    name = db.Column(db.String(120))

    price = db.Column(db.Float)

    category = db.Column(db.String(120))