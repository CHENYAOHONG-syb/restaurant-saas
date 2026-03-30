from app.extensions import db


class MenuCategory(db.Model):
    __tablename__ = "menu_categories"
    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "name", name="uq_menu_categories_restaurant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
