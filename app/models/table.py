from app.extensions import db


class Table(db.Model):
    __tablename__ = "tables"
    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "table_number", name="uq_tables_restaurant_table_number"),
    )

    STATUS_AVAILABLE = "available"
    STATUS_OCCUPIED = "occupied"
    STATUS_RESERVED = "reserved"
    STATUS_NEEDS_CLEANING = "needs_cleaning"
    STATUS_OPTIONS = (
        STATUS_AVAILABLE,
        STATUS_OCCUPIED,
        STATUS_RESERVED,
        STATUS_NEEDS_CLEANING,
    )

    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(40), nullable=False, default=STATUS_AVAILABLE)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
