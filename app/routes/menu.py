from flask import Blueprint, render_template, request

from app.models.menu import Menu
from app.services.order_service import get_cart
from app.services.tenant_service import get_restaurant, get_restaurant_by_slug

menu = Blueprint("menu", __name__)


def _cart_count_for(table_number, restaurant_id):
    if not restaurant_id:
        return 0
    return sum(item.quantity for item in get_cart(table_number, restaurant_id))


@menu.route("/")
def show_menu():
    restaurant_id = request.args.get("restaurant_id", type=int)
    table_number = request.args.get("table", type=int) or 1
    query = Menu.query.order_by(Menu.category.asc(), Menu.name.asc())
    restaurant = None

    if restaurant_id:
        query = query.filter_by(restaurant_id=restaurant_id)
        restaurant = get_restaurant(restaurant_id)

    items = query.all()
    return render_template(
        "menu.html",
        items=items,
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        table=table_number,
        cart_count=_cart_count_for(table_number, restaurant_id),
    )


@menu.route("/r/<slug>")
def restaurant_menu(slug):
    restaurant = get_restaurant_by_slug(slug)

    items = Menu.query.filter_by(restaurant_id=restaurant.id).order_by(Menu.category.asc(), Menu.name.asc()).all()
    table_number = request.args.get("table", type=int) or 1
    return render_template(
        "menu.html",
        items=items,
        restaurant=restaurant,
        restaurant_id=restaurant.id,
        table=table_number,
        cart_count=_cart_count_for(table_number, restaurant.id),
    )
