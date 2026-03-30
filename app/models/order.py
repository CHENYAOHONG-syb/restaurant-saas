from app.extensions import db


class Order(db.Model):
    __tablename__ = "orders"

    STATUS_SUBMITTED = "submitted"
    STATUS_PREPARING = "preparing"
    STATUS_READY = "ready"
    STATUS_SERVED = "served"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"

    STATUS_FLOW = (
        STATUS_SUBMITTED,
        STATUS_PREPARING,
        STATUS_READY,
        STATUS_SERVED,
        STATUS_PAID,
        STATUS_CANCELLED,
    )
    ACTIVE_STATUSES = (
        STATUS_SUBMITTED,
        STATUS_PREPARING,
        STATUS_READY,
        STATUS_SERVED,
    )
    CLOSED_STATUSES = (
        STATUS_PAID,
        STATUS_CANCELLED,
    )

    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    status = db.Column(db.String(50), default=STATUS_SUBMITTED, nullable=False)
    note = db.Column(db.String(255))
    inventory_applied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
