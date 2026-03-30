from app.extensions import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    stock = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(40), nullable=False, default="unit")
    cost = db.Column(db.Float)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
