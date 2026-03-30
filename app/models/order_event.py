from app.extensions import db


class OrderEvent(db.Model):
    __tablename__ = "order_events"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    from_status = db.Column(db.String(50))
    to_status = db.Column(db.String(50))
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    order = db.relationship("Order")
    actor = db.relationship("User")
