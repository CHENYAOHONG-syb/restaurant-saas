from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="owner")
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
