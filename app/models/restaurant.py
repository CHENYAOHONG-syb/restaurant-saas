from app.extensions import db


class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
