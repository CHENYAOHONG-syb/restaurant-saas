from app.exceptions import NotFoundError
from app.models.billing_event import BillingEvent
from app.models.customer import Customer
from app.models.inventory_item import InventoryItem
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription
from app.models.table import Table
from app.models.team_invitation import TeamInvitation
from app.models.user import User


def get_restaurant(restaurant_id):
    restaurant = Restaurant.query.filter_by(id=restaurant_id).first()
    if restaurant is None:
        raise NotFoundError("Restaurant not found.")
    return restaurant


def get_restaurant_by_slug(slug):
    restaurant = Restaurant.query.filter_by(slug=(slug or "").strip()).first()
    if restaurant is None:
        raise NotFoundError("Restaurant not found.")
    return restaurant


def get_menu_item_for_restaurant(restaurant_id, menu_id):
    item = Menu.query.filter_by(id=menu_id, restaurant_id=restaurant_id).first()
    if item is None:
        raise NotFoundError("Menu item not found for this restaurant.")
    return item


def get_category_for_restaurant(restaurant_id, category_id):
    category = MenuCategory.query.filter_by(id=category_id, restaurant_id=restaurant_id).first()
    if category is None:
        raise NotFoundError("Category not found for this restaurant.")
    return category


def get_category_by_name_for_restaurant(restaurant_id, name):
    category = MenuCategory.query.filter_by(
        restaurant_id=restaurant_id,
        name=(name or "").strip().lower(),
    ).first()
    if category is None:
        raise NotFoundError("Category not found for this restaurant.")
    return category


def get_inventory_item_for_restaurant(restaurant_id, inventory_item_id):
    item = InventoryItem.query.filter_by(id=inventory_item_id, restaurant_id=restaurant_id).first()
    if item is None:
        raise NotFoundError("Inventory item not found for this restaurant.")
    return item


def get_order_for_restaurant(restaurant_id, order_id):
    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()
    if order is None:
        raise NotFoundError("Order not found for this restaurant.")
    return order


def get_order_item_for_restaurant(restaurant_id, order_item_id):
    order_item = (
        OrderItem.query.join(Order, Order.id == OrderItem.order_id)
        .filter(OrderItem.id == order_item_id, Order.restaurant_id == restaurant_id)
        .first()
    )
    if order_item is None:
        raise NotFoundError("Order item not found for this restaurant.")
    return order_item


def get_table_for_restaurant(restaurant_id, table_id):
    table = Table.query.filter_by(id=table_id, restaurant_id=restaurant_id).first()
    if table is None:
        raise NotFoundError("Table not found for this restaurant.")
    return table


def get_table_by_number_for_restaurant(restaurant_id, table_number):
    table = Table.query.filter_by(restaurant_id=restaurant_id, table_number=table_number).first()
    if table is None:
        raise NotFoundError("Table not found for this restaurant.")
    return table


def get_customer_for_restaurant(restaurant_id, customer_id):
    customer = Customer.query.filter_by(id=customer_id, restaurant_id=restaurant_id).first()
    if customer is None:
        raise NotFoundError("Customer not found for this restaurant.")
    return customer


def get_team_invitation_for_restaurant(restaurant_id, invitation_id):
    invitation = TeamInvitation.query.filter_by(id=invitation_id, restaurant_id=restaurant_id).first()
    if invitation is None:
        raise NotFoundError("Invitation not found for this restaurant.")
    return invitation


def get_team_member_for_restaurant(restaurant_id, user_id):
    member = User.query.filter_by(id=user_id, restaurant_id=restaurant_id).first()
    if member is None:
        raise NotFoundError("Team member not found for this restaurant.")
    return member


def get_subscription_for_restaurant(restaurant_id):
    subscription = Subscription.query.filter_by(restaurant_id=restaurant_id).first()
    if subscription is None:
        raise NotFoundError("Subscription not found for this restaurant.")
    return subscription


def get_billing_event_for_restaurant(restaurant_id, event_id):
    event = BillingEvent.query.filter_by(id=event_id, restaurant_id=restaurant_id).first()
    if event is None:
        raise NotFoundError("Billing event not found for this restaurant.")
    return event
