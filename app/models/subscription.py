from app.extensions import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False, unique=True)
    plan = db.Column(db.String(50), nullable=False, default="starter")
    status = db.Column(db.String(50), nullable=False, default="trialing")
    billing_provider = db.Column(db.String(50), nullable=False, default="manual")
    provider_customer_id = db.Column(db.String(120))
    provider_subscription_id = db.Column(db.String(120))
    current_period_end = db.Column(db.DateTime)
    trial_ends_at = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
