from app.extensions import db


class MenuInventoryRequirement(db.Model):
    __tablename__ = "menu_inventory_requirements"
    __table_args__ = (
        db.UniqueConstraint(
            "menu_id",
            "inventory_item_id",
            name="uq_menu_inventory_requirement",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    menu_id = db.Column(db.Integer, db.ForeignKey("menu.id"), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    quantity_required = db.Column(db.Float, nullable=False, default=1)

    menu_item = db.relationship("Menu")
    inventory_item = db.relationship("InventoryItem")
