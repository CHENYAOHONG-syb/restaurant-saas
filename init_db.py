from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models.menu import Menu
from app.models.restaurant import Restaurant
from app.services.subscription import get_or_create_subscription

import app.models  # noqa: F401

DEMO_RESTAURANT = {
    "name": "Demo Restaurant",
    "slug": "demo-restaurant",
    "address": "Kuala Lumpur",
}

DEMO_MENU = [
    {
        "name": "Nasi Lemak",
        "description": "Coconut rice with sambal and crispy anchovies",
        "price": 12.5,
        "category": "main",
    },
    {
        "name": "Char Kway Teow",
        "description": "Wok-fried noodles with prawns and bean sprouts",
        "price": 14.0,
        "category": "main",
    },
    {
        "name": "Teh Tarik",
        "description": "Pulled milk tea",
        "price": 4.5,
        "category": "drink",
    },
]

REQUIRED_TABLES = {"restaurants", "menu", "subscriptions"}


def ensure_schema_ready():
    existing_tables = set(inspect(db.engine).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - existing_tables)
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise RuntimeError(
            "Database schema is missing required tables: "
            f"{missing}. Run `python3 -m flask --app run.py db upgrade --directory migrations` first."
        )


def seed_demo_restaurant():
    restaurant = Restaurant.query.filter_by(slug=DEMO_RESTAURANT["slug"]).first()
    created_restaurant = restaurant is None

    if created_restaurant:
        restaurant = Restaurant(**DEMO_RESTAURANT)
        db.session.add(restaurant)
        db.session.flush()
    else:
        restaurant.name = DEMO_RESTAURANT["name"]
        restaurant.address = DEMO_RESTAURANT["address"]

    existing_menu = {
        item.name: item
        for item in Menu.query.filter_by(restaurant_id=restaurant.id).all()
    }

    for menu_item in DEMO_MENU:
        item = existing_menu.get(menu_item["name"])
        if item is None:
            item = Menu(restaurant_id=restaurant.id, **menu_item)
            db.session.add(item)
            continue

        item.description = menu_item["description"]
        item.price = menu_item["price"]
        item.category = menu_item["category"]

    db.session.commit()
    subscription = get_or_create_subscription(restaurant.id)
    return restaurant, subscription, created_restaurant


app = create_app()

with app.app_context():
    ensure_schema_ready()
    restaurant, subscription, created_restaurant = seed_demo_restaurant()
    status = "created" if created_restaurant else "updated"
    print(
        f"Demo data {status} for {restaurant.slug} "
        f"(plan={subscription.plan}, status={subscription.status})"
    )
