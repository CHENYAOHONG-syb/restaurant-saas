from app.extensions import db


class Menu(db.Model):
    __tablename__ = "menu"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    category = db.Column(db.String(80), default="main")
    image = db.Column(db.String(255))
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
