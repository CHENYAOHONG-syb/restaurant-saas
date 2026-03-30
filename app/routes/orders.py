from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.exceptions import AppError
from app.services.order_service import (
    add_to_cart,
    checkout,
    clear_cart,
    get_cart,
    remove_from_cart,
)
from app.services.tenant_service import get_restaurant
from app.validation import validate_add_to_cart_input, validate_checkout_input

orders = Blueprint("orders", __name__)


def _get_restaurant_id():
    if getattr(current_user, "is_authenticated", False):
        return current_user.restaurant_id

    return request.values.get("restaurant_id", type=int)


def _menu_url(restaurant_id, table_number):
    restaurant = None
    if restaurant_id:
        try:
            restaurant = get_restaurant(restaurant_id)
        except AppError:
            restaurant = None
    if restaurant and restaurant.slug:
        return url_for("menu.restaurant_menu", slug=restaurant.slug, table=table_number)
    if restaurant_id:
        return url_for("menu.show_menu", restaurant_id=restaurant_id, table=table_number)
    return url_for("platform.home")


def _cart_url(table_number, restaurant_id):
    if not restaurant_id:
        return url_for("platform.home")
    return url_for("orders.cart", table=table_number, restaurant_id=restaurant_id)


@orders.route("/add_to_cart", methods=["POST"])
def add():
    restaurant_id = _get_restaurant_id()

    if not restaurant_id:
        flash("Choose a restaurant before adding items to the cart.", "error")
        return redirect(url_for("platform.home"))

    try:
        payload = validate_add_to_cart_input(
            {
                "food_id": request.form.get("food_id"),
                "table": request.form.get("table"),
                "restaurant_id": restaurant_id,
            }
        )
        add_to_cart(
            food_id=payload["food_id"],
            table_number=payload["table_number"],
            restaurant_id=payload["restaurant_id"],
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
        return redirect(_menu_url(restaurant_id, request.form.get("table", type=int) or 1))

    flash("Item added to cart.", "success")
    return redirect(_cart_url(payload["table_number"], restaurant_id))


@orders.route("/cart")
def cart():
    table_number = request.args.get("table", type=int) or 1
    restaurant_id = request.args.get("restaurant_id", type=int) or _get_restaurant_id()
    if not restaurant_id:
        flash("Choose a restaurant before opening a cart.", "warning")
        return redirect(url_for("platform.home"))
    items = get_cart(table_number=table_number, restaurant_id=restaurant_id)
    restaurant = get_restaurant(restaurant_id) if restaurant_id else None
    return render_template(
        "cart.html",
        items=items,
        table=table_number,
        restaurant_id=restaurant_id,
        restaurant=restaurant,
        menu_url=_menu_url(restaurant_id, table_number),
    )


@orders.route("/remove_from_cart", methods=["POST"])
def remove():
    cart_id = request.form.get("cart_id", type=int)
    table_number = request.form.get("table", type=int) or 1
    restaurant_id = _get_restaurant_id()

    if not restaurant_id:
        flash("Choose a restaurant before editing the cart.", "error")
        return redirect(url_for("platform.home"))

    try:
        if cart_id:
            remove_from_cart(cart_id, restaurant_id)
            flash("Item removed from cart.", "success")
        else:
            flash("We could not find that cart item.", "warning")
    except AppError as exc:
        flash(exc.message, exc.flash_category)

    return redirect(_cart_url(table_number, restaurant_id))


@orders.route("/clear_cart", methods=["POST"])
def clear():
    table_number = request.form.get("table", type=int)
    restaurant_id = _get_restaurant_id()

    if not restaurant_id:
        flash("Choose a restaurant before clearing the cart.", "error")
        return redirect(url_for("platform.home"))

    if not table_number:
        flash("Pick a table before clearing the cart.", "error")
        return redirect(_menu_url(restaurant_id, 1))

    clear_cart(table_number, restaurant_id)
    flash("Cart cleared.", "success")
    return redirect(_cart_url(table_number, restaurant_id))


@orders.route("/checkout", methods=["POST"])
def do_checkout():
    table_number = request.form.get("table", type=int)
    restaurant_id = _get_restaurant_id()

    if not restaurant_id:
        flash("Choose a restaurant before checkout.", "error")
        return redirect(url_for("platform.home"))

    try:
        payload = validate_checkout_input(
            {
                "table": request.form.get("table"),
                "restaurant_id": restaurant_id,
            }
        )
        order = checkout(
            table_number=payload["table_number"],
            restaurant_id=payload["restaurant_id"],
            actor_user_id=current_user.id if getattr(current_user, "is_authenticated", False) else None,
            note=payload["note"],
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
        return redirect(_menu_url(restaurant_id, table_number or 1))

    if order is None:
        flash("The cart is empty, so there is nothing to check out.", "warning")
    else:
        flash(f"Order #{order.id} has been sent to the kitchen.", "success")
    return redirect(_cart_url(payload["table_number"], restaurant_id))
