from sqlalchemy import func

from app.exceptions import BusinessRuleError, ValidationError
from app.extensions import db
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.services.pagination import paginate_query
from app.services.tenant_service import get_category_for_restaurant

DEFAULT_MENU_CATEGORIES = ("main", "drink", "dessert")


def normalize_category_name(name):
    return (name or "").strip().lower()


def list_category_names(restaurant_id):
    ensure_default_categories(restaurant_id)
    sync_categories_from_menu(restaurant_id)
    rows = (
        MenuCategory.query.filter_by(restaurant_id=restaurant_id)
        .order_by(MenuCategory.name.asc())
        .all()
    )
    return [row.name for row in rows]


def ensure_default_categories(restaurant_id):
    existing_count = (
        db.session.query(func.count(MenuCategory.id))
        .filter(MenuCategory.restaurant_id == restaurant_id)
        .scalar()
        or 0
    )
    if existing_count:
        return
    db.session.add_all(
        [MenuCategory(restaurant_id=restaurant_id, name=name) for name in DEFAULT_MENU_CATEGORIES]
    )
    db.session.commit()


def sync_categories_from_menu(restaurant_id):
    menu_categories = {
        normalize_category_name(name)
        for name, in db.session.query(Menu.category)
        .filter(Menu.restaurant_id == restaurant_id, Menu.category.isnot(None))
        .distinct()
        .all()
        if normalize_category_name(name)
    }
    if not menu_categories:
        return

    existing = {
        name
        for name, in db.session.query(MenuCategory.name)
        .filter(MenuCategory.restaurant_id == restaurant_id)
        .all()
        if name
    }
    missing = sorted(menu_categories - existing)
    if not missing:
        return

    db.session.add_all(
        [MenuCategory(restaurant_id=restaurant_id, name=name) for name in missing]
    )
    db.session.commit()


def ensure_menu_category(restaurant_id, name):
    normalized_name = normalize_category_name(name)
    if not normalized_name:
        return None
    existing = MenuCategory.query.filter_by(
        restaurant_id=restaurant_id,
        name=normalized_name,
    ).first()
    if existing:
        return existing
    category = MenuCategory(restaurant_id=restaurant_id, name=normalized_name)
    db.session.add(category)
    db.session.commit()
    return category


def list_category_records_page(
    restaurant_id,
    *,
    page=1,
    per_page=10,
    search=None,
    sort="name",
    direction="asc",
):
    ensure_default_categories(restaurant_id)
    sync_categories_from_menu(restaurant_id)

    normalized_search = (search or "").strip()
    normalized_direction = "desc" if direction == "desc" else "asc"
    item_count = func.coalesce(func.count(Menu.id), 0).label("item_count")
    query = (
        db.session.query(MenuCategory, item_count)
        .outerjoin(
            Menu,
            (Menu.restaurant_id == MenuCategory.restaurant_id)
            & (func.lower(Menu.category) == func.lower(MenuCategory.name)),
        )
        .filter(MenuCategory.restaurant_id == restaurant_id)
        .group_by(MenuCategory.id)
    )

    if normalized_search:
        like = f"%{normalized_search}%"
        query = query.filter(MenuCategory.name.ilike(like))

    sort_map = {
        "name": MenuCategory.name,
        "items": item_count,
        "created_at": MenuCategory.created_at,
    }
    sort_column = sort_map.get(sort, MenuCategory.name)
    ordered = query.order_by(
        sort_column.desc() if normalized_direction == "desc" else sort_column.asc(),
        MenuCategory.name.asc(),
    )
    pagination = paginate_query(ordered, page=page, per_page=per_page)

    rows = []
    for category, item_total in pagination["items"]:
        category.item_count = int(item_total or 0)
        rows.append(category)
    pagination["items"] = rows

    return {
        "items": rows,
        "pagination": pagination,
    }


def create_category(restaurant_id, name):
    normalized_name = normalize_category_name(name)
    if not normalized_name:
        raise ValidationError("Category name is required.")

    existing = MenuCategory.query.filter_by(
        restaurant_id=restaurant_id,
        name=normalized_name,
    ).first()
    if existing:
        raise BusinessRuleError("That category already exists.")

    category = MenuCategory(restaurant_id=restaurant_id, name=normalized_name)
    db.session.add(category)
    db.session.commit()
    return category


def get_category(restaurant_id, category_id):
    return get_category_for_restaurant(restaurant_id, category_id)


def delete_category(category):
    in_use_count = (
        Menu.query.filter(
            Menu.restaurant_id == category.restaurant_id,
            func.lower(Menu.category) == func.lower(category.name),
        ).count()
    )
    if in_use_count:
        raise BusinessRuleError("Remove or reassign menu items in that category before deleting it.")
    db.session.delete(category)
    db.session.commit()
