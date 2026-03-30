from app.extensions import db


class BillingEvent(db.Model):
    __tablename__ = "billing_events"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    event_type = db.Column(db.String(120), nullable=False)
    source = db.Column(db.String(50), nullable=False, default="system")
    status = db.Column(db.String(50))
    summary = db.Column(db.String(255))
    provider_event_id = db.Column(db.String(120))
    plan_key = db.Column(db.String(50))
    payment_reference = db.Column(db.String(120))
    attachment_path = db.Column(db.String(255))
    amount_cents = db.Column(db.Integer)
    currency = db.Column(db.String(12))
    reference_url = db.Column(db.String(255))
    occurred_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    created_at = db.Column(db.DateTime, server_default=db.func.now())
