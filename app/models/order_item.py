from app.extensions import db

class OrderItem(db.Model):

    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))

    food_id = db.Column(db.Integer, db.ForeignKey("menu.id"))

    quantity = db.Column(db.Integer)

    food = db.relationship("Menu")