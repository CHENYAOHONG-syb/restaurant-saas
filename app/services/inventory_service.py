from datetime import datetime

from sqlalchemy import String, cast, or_

from app.exceptions import BusinessRuleError, ValidationError
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.menu_inventory_requirement import MenuInventoryRequirement
from app.models.order_item import OrderItem
from app.services.pagination import paginate_query
from app.services.tenant_service import get_inventory_item_for_restaurant

DEFAULT_LOW_STOCK_THRESHOLD = 5


def get_dashboard_inventory_metrics(restaurant_id, *, low_stock_threshold=DEFAULT_LOW_STOCK_THRESHOLD):
    query = InventoryItem.query.filter_by(restaurant_id=restaurant_id)
    out_of_stock_count = query.filter(InventoryItem.stock <= 0).count()
    low_stock_count = query.filter(
        InventoryItem.stock > 0,
        InventoryItem.stock <= low_stock_threshold,
    ).count()
    return {
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
    }


def list_inventory_items_page(
    restaurant_id,
    *,
    page=1,
    per_page=10,
    search=None,
    stock=None,
    sort="name",
    direction="asc",
    low_stock_threshold=DEFAULT_LOW_STOCK_THRESHOLD,
):
    query = InventoryItem.query.filter_by(restaurant_id=restaurant_id)
    overall_total = query.count()
    normalized_search = (search or "").strip()
    normalized_stock = (stock or "").strip().lower()
    normalized_direction = "desc" if direction == "desc" else "asc"

    if normalized_search:
        like = f"%{normalized_search}%"
        query = query.filter(
            or_(
                InventoryItem.name.ilike(like),
                InventoryItem.unit.ilike(like),
                cast(InventoryItem.stock, String).ilike(like),
                cast(InventoryItem.cost, String).ilike(like),
            )
        )

    if normalized_stock == "out":
        query = query.filter(InventoryItem.stock <= 0)
    elif normalized_stock == "low":
        query = query.filter(
            InventoryItem.stock > 0,
            InventoryItem.stock <= low_stock_threshold,
        )

    sort_map = {
        "name": InventoryItem.name,
        "stock": InventoryItem.stock,
        "cost": InventoryItem.cost,
        "created_at": InventoryItem.created_at,
    }
    sort_column = sort_map.get(sort, InventoryItem.name)
    ordered = query.order_by(
        sort_column.desc() if normalized_direction == "desc" else sort_column.asc(),
        InventoryItem.name.asc(),
    )
    pagination = paginate_query(ordered, page=page, per_page=per_page)
    return {
        "items": pagination["items"],
        "pagination": pagination,
        "overall_total": overall_total,
        "stock_filter": normalized_stock,
        "low_stock_threshold": low_stock_threshold,
    }


def list_inventory_items(restaurant_id):
    return (
        InventoryItem.query.filter_by(restaurant_id=restaurant_id)
        .order_by(InventoryItem.name.asc())
        .all()
    )


def create_inventory_item(restaurant_id, *, name, stock, unit=None, cost=None):
    normalized_name = (name or "").strip()
    normalized_unit = (unit or "").strip() or "unit"
    if not normalized_name:
        raise ValidationError("Inventory item name is required.")
    if stock is None or stock < 0:
        raise ValidationError("Stock level must be zero or greater.")
    if cost is not None and cost < 0:
        raise ValidationError("Unit cost must be zero or greater.")
    duplicate = InventoryItem.query.filter(
        InventoryItem.restaurant_id == restaurant_id,
        InventoryItem.name.ilike(normalized_name),
    ).first()
    if duplicate:
        raise BusinessRuleError("An inventory item with that name already exists for this restaurant.")

    item = InventoryItem(
        restaurant_id=restaurant_id,
        name=normalized_name,
        stock=stock,
        unit=normalized_unit,
        cost=cost,
    )
    db.session.add(item)
    db.session.commit()
    return item


def sync_menu_inventory_requirement(menu_item, *, restaurant_id, inventory_item_id=None, quantity_required=None):
    MenuInventoryRequirement.query.filter_by(menu_id=menu_item.id).delete()
    if inventory_item_id and quantity_required and quantity_required > 0:
        inventory_item = get_inventory_item_for_restaurant(restaurant_id, inventory_item_id)
        requirement = MenuInventoryRequirement(
            menu_id=menu_item.id,
            inventory_item_id=inventory_item.id,
            quantity_required=quantity_required,
        )
        db.session.add(requirement)
    db.session.flush()


def list_menu_requirements(menu_id):
    return (
        MenuInventoryRequirement.query.filter_by(menu_id=menu_id)
        .order_by(MenuInventoryRequirement.id.asc())
        .all()
    )


def ensure_inventory_available(order):
    shortages = []
    for order_item in _order_items_with_requirements(order.id):
        for requirement in order_item["requirements"]:
            needed = requirement.quantity_required * order_item["quantity"]
            if requirement.inventory_item.stock < needed:
                shortages.append(
                    f"{requirement.inventory_item.name} needs {needed:g} {requirement.inventory_item.unit}, "
                    f"but only {requirement.inventory_item.stock:g} {requirement.inventory_item.unit} remain."
                )
    if shortages:
        raise BusinessRuleError("Inventory is too low to start preparation: " + " ".join(shortages))


def apply_inventory(order):
    if order.inventory_applied_at:
        return order
    ensure_inventory_available(order)
    for order_item in _order_items_with_requirements(order.id):
        for requirement in order_item["requirements"]:
            requirement.inventory_item.stock -= requirement.quantity_required * order_item["quantity"]
    order.inventory_applied_at = datetime.utcnow()
    db.session.flush()
    return order


def restore_inventory(order):
    if not order.inventory_applied_at:
        return order
    for order_item in _order_items_with_requirements(order.id):
        for requirement in order_item["requirements"]:
            requirement.inventory_item.stock += requirement.quantity_required * order_item["quantity"]
    order.inventory_applied_at = None
    db.session.flush()
    return order


def _order_items_with_requirements(order_id):
    rows = (
        db.session.query(OrderItem)
        .filter(OrderItem.order_id == order_id)
        .order_by(OrderItem.id.asc())
        .all()
    )
    payload = []
    for row in rows:
        requirements = list_menu_requirements(row.food_id)
        payload.append(
            {
                "order_item": row,
                "quantity": row.quantity or 0,
                "requirements": requirements,
            }
        )
    return payload
