import json
import sys
from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

from app.routes.auth import PASSWORD_METHOD
from app.extensions import db
from app.models.billing_event import BillingEvent
from app.models.cart import Cart
from app.models.inventory_item import InventoryItem
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.models.menu_inventory_requirement import MenuInventoryRequirement
from app.models.order import Order
from app.models.order_event import OrderEvent
from app.models.order_item import OrderItem
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription
from app.models.table import Table
from app.models.team_invitation import TeamInvitation
from app.models.user import User
from app.services.admin_service import (
    get_dashboard_snapshot,
    get_dashboard_order_metrics,
    get_dashboard_today_metrics,
    list_order_rows_page,
)
from app.services.floor_service import get_dashboard_table_metrics
from app.services.inventory_service import get_dashboard_inventory_metrics
from app.services.order_service import get_order_detail_context, get_order_receipt_context


def create_restaurant(name, slug):
    restaurant = Restaurant(name=name, slug=slug, address=f"{name} Address")
    db.session.add(restaurant)
    db.session.flush()
    snapshot = SimpleNamespace(id=restaurant.id, slug=restaurant.slug, name=restaurant.name)
    db.session.commit()
    return snapshot


def create_user(restaurant_id, username, password="password123", role="owner"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        password=generate_password_hash(password, method=PASSWORD_METHOD),
        role=role,
        restaurant_id=restaurant_id,
    )
    db.session.add(user)
    db.session.flush()
    snapshot = SimpleNamespace(id=user.id, username=user.username, role=user.role, restaurant_id=user.restaurant_id)
    db.session.commit()
    return snapshot


def create_menu_item(restaurant_id, name, price):
    item = Menu(
        name=name,
        price=price,
        description=f"{name} description",
        category="main",
        restaurant_id=restaurant_id,
    )
    db.session.add(item)
    db.session.flush()
    snapshot = SimpleNamespace(id=item.id, restaurant_id=item.restaurant_id, name=item.name)
    db.session.commit()
    return snapshot


def create_inventory_item_record(restaurant_id, name, *, stock, unit="unit", cost=None):
    item = InventoryItem(
        restaurant_id=restaurant_id,
        name=name,
        stock=stock,
        unit=unit,
        cost=cost,
    )
    db.session.add(item)
    db.session.flush()
    snapshot = SimpleNamespace(id=item.id, restaurant_id=item.restaurant_id, name=item.name)
    db.session.commit()
    return snapshot


def login(client, username, password="password123"):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_registration_and_login_create_owner_session(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")

    response = client.post(
        "/auth/register",
        data={
            "username": "alpha_owner",
            "password": "password123",
            "email": "alpha@example.com",
            "restaurant_id": restaurant.id,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/dashboard/{restaurant.id}")

    with app.app_context():
        user = User.query.filter_by(username="alpha_owner").first()
        assert user is not None
        assert user.role == "owner"

    logout_response = client.post("/auth/logout", follow_redirects=False)
    assert logout_response.status_code == 302

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith(f"/dashboard/{restaurant.id}")


def test_cross_tenant_admin_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        create_user(beta.id, "beta_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    dashboard_response = client.get(f"/dashboard/{beta.id}")
    billing_response = client.get(f"/billing/{beta.id}")

    assert dashboard_response.status_code == 403
    assert billing_response.status_code == 403


def test_dashboard_order_metrics_counts_and_links(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)

        submitted_order = Order(table_number=61, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        preparing_order = Order(table_number=62, restaurant_id=restaurant.id, status=Order.STATUS_PREPARING)
        ready_order = Order(table_number=63, restaurant_id=restaurant.id, status=Order.STATUS_READY)
        paid_order = Order(table_number=64, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        cancelled_order = Order(table_number=65, restaurant_id=restaurant.id, status=Order.STATUS_CANCELLED)
        db.session.add_all([submitted_order, preparing_order, ready_order, paid_order, cancelled_order])
        db.session.flush()
        for order in (submitted_order, preparing_order, ready_order, paid_order, cancelled_order):
            db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.commit()
        paid_order_id = paid_order.id

        metrics = get_dashboard_order_metrics(restaurant.id)
        assert metrics["total_orders"] == 5
        assert metrics["paid_orders"] == 1
        assert metrics["unpaid_orders"] == 4
        assert metrics["active_orders"] == 3

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    dashboard_response = client.get(f"/dashboard/{restaurant.id}")
    dashboard_page = dashboard_response.get_data(as_text=True)

    assert dashboard_response.status_code == 200
    assert "Service Status" in dashboard_page
    assert "Today Insights" in dashboard_page
    assert "Needs Attention" in dashboard_page
    assert "Latest Activity" in dashboard_page
    assert "Unpaid Orders" in dashboard_page
    assert "Active Orders" in dashboard_page
    assert f"/admin/orders/{restaurant.id}?payment=Unpaid" in dashboard_page
    assert f"/admin/orders/{restaurant.id}?status=active" in dashboard_page
    assert f"/admin/orders/{restaurant.id}/{paid_order_id}" in dashboard_page


def test_dashboard_shows_empty_state_and_operational_messages_without_data(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/dashboard/{restaurant.id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Service Status" in page
    assert "Today Insights" in page
    assert "Needs Attention" in page
    assert "Today vs Yesterday" in page
    assert "No orders yet" in page
    assert "Start by creating your first order or sharing your menu QR code with customers." in page
    assert "Nothing urgent right now" in page
    assert "Stock levels are stable" in page
    assert "No tables waiting on cleaning" in page


def test_dashboard_today_metrics_and_created_today_filters(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        now = datetime.utcnow().replace(microsecond=0)
        yesterday = now - timedelta(days=1)

        today_unpaid = Order(
            table_number=71,
            restaurant_id=restaurant.id,
            status=Order.STATUS_SUBMITTED,
            created_at=now,
        )
        today_paid = Order(
            table_number=72,
            restaurant_id=restaurant.id,
            status=Order.STATUS_PAID,
            created_at=now,
        )
        yesterday_paid = Order(
            table_number=73,
            restaurant_id=restaurant.id,
            status=Order.STATUS_PAID,
            created_at=yesterday,
        )
        db.session.add_all([today_unpaid, today_paid, yesterday_paid])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=today_unpaid.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=today_paid.id, food_id=dish.id, quantity=2),
                OrderItem(order_id=yesterday_paid.id, food_id=dish.id, quantity=3),
            ]
        )
        db.session.commit()

        today_metrics = get_dashboard_today_metrics(restaurant.id)
        today_unpaid_id = today_unpaid.id
        today_paid_id = today_paid.id
        yesterday_paid_id = yesterday_paid.id

        assert today_metrics["today_orders"] == 2
        assert today_metrics["today_paid_orders"] == 1
        assert today_metrics["today_revenue_value"] == 25.0
        assert today_metrics["today_revenue_display"] == "RM 25.00"
        snapshot = get_dashboard_snapshot(db.session.get(Restaurant, restaurant.id))
        assert snapshot["today_comparison"][0]["summary"] == "+1 vs yesterday"
        assert snapshot["today_comparison"][1]["summary"] == "Same as yesterday"
        assert snapshot["today_comparison"][2]["summary"] == "RM 12.50 down vs yesterday"

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    dashboard_response = client.get(f"/dashboard/{restaurant.id}")
    dashboard_page = dashboard_response.get_data(as_text=True)

    assert dashboard_response.status_code == 200
    assert "Service Status" in dashboard_page
    assert "Today Insights" in dashboard_page
    assert "Today vs Yesterday" in dashboard_page
    assert "RM 25.00" in dashboard_page
    assert "+1 vs yesterday" in dashboard_page
    assert f"/admin/orders/{restaurant.id}?created=today" in dashboard_page

    today_response = client.get(f"/admin/orders/{restaurant.id}?created=today")
    today_page = today_response.get_data(as_text=True)
    assert today_response.status_code == 200
    assert f"/admin/orders/{restaurant.id}/{today_unpaid_id}" in today_page
    assert f"/admin/orders/{restaurant.id}/{today_paid_id}" in today_page
    assert f"/admin/orders/{restaurant.id}/{yesterday_paid_id}" not in today_page

    today_paid_response = client.get(f"/admin/orders/{restaurant.id}?created=today&payment=Paid")
    today_paid_page = today_paid_response.get_data(as_text=True)
    assert today_paid_response.status_code == 200
    assert f"/admin/orders/{restaurant.id}/{today_paid_id}" in today_paid_page
    assert f"/admin/orders/{restaurant.id}/{today_unpaid_id}" not in today_paid_page
    assert f"/admin/orders/{restaurant.id}/{yesterday_paid_id}" not in today_paid_page


def test_dashboard_inventory_metrics_and_inventory_filters(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        low_item = create_inventory_item_record(restaurant.id, "Lemongrass", stock=3, unit="kg")
        out_item = create_inventory_item_record(restaurant.id, "Coconut milk", stock=0, unit="ltr")
        healthy_item = create_inventory_item_record(restaurant.id, "Palm sugar", stock=12, unit="kg")

        metrics = get_dashboard_inventory_metrics(restaurant.id)
        assert metrics["low_stock_count"] == 1
        assert metrics["out_of_stock_count"] == 1

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    dashboard_response = client.get(f"/dashboard/{restaurant.id}")
    dashboard_page = dashboard_response.get_data(as_text=True)

    assert dashboard_response.status_code == 200
    assert "Service Status" in dashboard_page
    assert "Low Stock Items" in dashboard_page
    assert f"/admin/inventory/{restaurant.id}?stock=low" in dashboard_page
    assert f"/admin/inventory/{restaurant.id}?stock=out" in dashboard_page
    assert "Needs Attention" in dashboard_page

    low_response = client.get(f"/admin/inventory/{restaurant.id}?stock=low")
    low_page = low_response.get_data(as_text=True)
    assert low_response.status_code == 200
    assert "Showing low stock items" in low_page
    assert "Lemongrass" in low_page
    assert "Coconut milk" not in low_page
    assert "Palm sugar" not in low_page

    out_response = client.get(f"/admin/inventory/{restaurant.id}?stock=out")
    out_page = out_response.get_data(as_text=True)
    assert out_response.status_code == 200
    assert "Showing out of stock items" in out_page
    assert "Coconut milk" in out_page
    assert "Lemongrass" not in out_page
    assert "Palm sugar" not in out_page


def test_cross_tenant_inventory_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        create_inventory_item_record(beta.id, "Laksa paste", stock=0, unit="jar")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/inventory/{beta.id}?stock=out")
    assert response.status_code == 403


def test_inventory_empty_states_cover_no_items_and_empty_stock_filters(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    empty_response = client.get(f"/admin/inventory/{restaurant.id}")
    empty_page = empty_response.get_data(as_text=True)
    assert empty_response.status_code == 200
    assert "No inventory items yet" in empty_page
    assert "Add items to start tracking stock usage." in empty_page

    with app.app_context():
        create_inventory_item_record(restaurant.id, "Rice", stock=12, unit="kg")

    low_response = client.get(f"/admin/inventory/{restaurant.id}?stock=low")
    low_page = low_response.get_data(as_text=True)
    assert low_response.status_code == 200
    assert "No low stock items" in low_page
    assert "All tracked items are above the current low-stock threshold." in low_page

    out_response = client.get(f"/admin/inventory/{restaurant.id}?stock=out")
    out_page = out_response.get_data(as_text=True)
    assert out_response.status_code == 200
    assert "No out-of-stock items" in out_page
    assert "All tracked items currently have available stock." in out_page


def test_dashboard_table_metrics_and_table_filters(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        db.session.add_all(
            [
                Table(table_number=81, restaurant_id=restaurant.id, status=Table.STATUS_AVAILABLE),
                Table(table_number=82, restaurant_id=restaurant.id, status=Table.STATUS_AVAILABLE),
                Table(table_number=83, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=84, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
            ]
        )
        db.session.commit()

        metrics = get_dashboard_table_metrics(restaurant.id)
        assert metrics["available_tables"] == 2
        assert metrics["occupied_tables"] == 1
        assert metrics["needs_cleaning_tables"] == 1

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    dashboard_response = client.get(f"/dashboard/{restaurant.id}")
    dashboard_page = dashboard_response.get_data(as_text=True)

    assert dashboard_response.status_code == 200
    assert "Service Status" in dashboard_page
    assert "Today Insights" in dashboard_page
    assert "Needs Cleaning Tables" in dashboard_page
    assert f"/admin/tables/{restaurant.id}?status=needs_cleaning" in dashboard_page

    available_response = client.get(f"/admin/tables/{restaurant.id}?status=available")
    available_page = available_response.get_data(as_text=True)
    assert available_response.status_code == 200
    assert "Showing available tables" in available_page
    assert "Table 81" in available_page
    assert "Table 82" in available_page
    assert "Table 83" not in available_page
    assert "Table 84" not in available_page

    occupied_response = client.get(f"/admin/tables/{restaurant.id}?status=occupied")
    occupied_page = occupied_response.get_data(as_text=True)
    assert occupied_response.status_code == 200
    assert "Showing occupied tables" in occupied_page
    assert "Table 83" in occupied_page
    assert "Table 81" not in occupied_page
    assert "Table 84" not in occupied_page

    cleaning_response = client.get(f"/admin/tables/{restaurant.id}?status=needs_cleaning")
    cleaning_page = cleaning_response.get_data(as_text=True)
    assert cleaning_response.status_code == 200
    assert "Showing tables that need cleaning" in cleaning_page
    assert "Table 84" in cleaning_page
    assert "Table 81" not in cleaning_page
    assert "Table 83" not in cleaning_page


def test_dashboard_snapshot_builds_attention_and_activity_feed(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        now = datetime.utcnow().replace(microsecond=0)
        delayed_time = now - timedelta(minutes=8)

        delayed_order = Order(
            table_number=91,
            restaurant_id=restaurant.id,
            status=Order.STATUS_SUBMITTED,
            created_at=delayed_time,
        )
        paid_order = Order(
            table_number=92,
            restaurant_id=restaurant.id,
            status=Order.STATUS_PAID,
            created_at=now,
        )
        db.session.add_all([delayed_order, paid_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=delayed_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=paid_order.id, food_id=dish.id, quantity=2),
                InventoryItem(restaurant_id=restaurant.id, name="Coconut milk", stock=0, unit="ltr"),
                Table(table_number=93, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
            ]
        )
        db.session.commit()

        snapshot = get_dashboard_snapshot(db.session.get(Restaurant, restaurant.id))
        assert snapshot["service_status"]["title"] == "Kitchen delays need attention"
        assert any("delayed order" in item["title"] for item in snapshot["today_insights"])
        assert any(item["link_key"] == "kitchen" for item in snapshot["needs_attention"])
        assert any(item["link_key"] == "inventory_out" for item in snapshot["needs_attention"])
        assert snapshot["activity_feed"]
        assert snapshot["activity_feed"][0]["headline"].startswith("Order #")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/dashboard/{restaurant.id}")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Service Status" in page
    assert "Kitchen delays need attention" in page
    assert "Today Insights" in page
    assert "Needs Attention" in page
    assert "Open kitchen" in page
    assert "Open inventory" in page
    assert "Latest Activity" in page
    assert f"/admin/orders/{restaurant.id}/{paid_order.id}" in page


def test_cross_tenant_table_page_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        db.session.add(Table(table_number=91, restaurant_id=beta.id, status=Table.STATUS_AVAILABLE))
        db.session.commit()

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/tables/{beta.id}?status=available")
    assert response.status_code == 403


def test_tables_empty_states_cover_no_tables_and_filter_miss(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    empty_response = client.get(f"/admin/tables/{restaurant.id}")
    empty_page = empty_response.get_data(as_text=True)
    assert empty_response.status_code == 200
    assert "No tables configured" in empty_page
    assert "Add tables to start managing dine-in operations." in empty_page

    with app.app_context():
        db.session.add(Table(table_number=96, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()

    available_response = client.get(f"/admin/tables/{restaurant.id}?status=available")
    available_page = available_response.get_data(as_text=True)
    assert available_response.status_code == 200
    assert "No available tables" in available_page
    assert "All current tables are in another service state." in available_page


def test_staff_role_cannot_open_owner_billing_console(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_staff", role="staff")

    login_response = login(client, "alpha_staff")
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith(f"/admin/kitchen/{restaurant.id}")

    kitchen_response = client.get(f"/admin/kitchen/{restaurant.id}")
    dashboard_response = client.get(f"/dashboard/{restaurant.id}")
    billing_response = client.get(f"/billing/{restaurant.id}")

    assert kitchen_response.status_code == 200
    assert dashboard_response.status_code == 403
    assert billing_response.status_code == 403


def test_guest_order_flow_rejects_cross_restaurant_menu_item(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        alpha_item = create_menu_item(alpha.id, "Nasi Lemak", 12.5)
        beta_item = create_menu_item(beta.id, "Laksa", 15.0)

    invalid_response = client.post(
        "/orders/add_to_cart",
        data={"food_id": beta_item.id, "table": 7, "restaurant_id": alpha.id},
        follow_redirects=False,
    )
    assert invalid_response.status_code == 302

    with app.app_context():
        assert Cart.query.count() == 0

    add_response = client.post(
        "/orders/add_to_cart",
        data={"food_id": alpha_item.id, "table": 7, "restaurant_id": alpha.id},
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    checkout_response = client.post(
        "/orders/checkout",
        data={"table": 7, "restaurant_id": alpha.id},
        follow_redirects=False,
    )
    assert checkout_response.status_code == 302

    with app.app_context():
        order = Order.query.one()
        order_item = OrderItem.query.one()
        table = Table.query.filter_by(restaurant_id=alpha.id, table_number=7).one()
        assert order.restaurant_id == alpha.id
        assert order.table_number == 7
        assert order.status == Order.STATUS_SUBMITTED
        assert order_item.order_id == order.id
        assert order_item.food_id == alpha_item.id
        assert table.status == Table.STATUS_OCCUPIED
        assert Cart.query.count() == 0


def test_pos_manual_ticket_creation_and_kitchen_status_updates(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_cashier", role="cashier")
        create_user(restaurant.id, "alpha_kitchen", role="kitchen")
        nasi = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        teh = create_menu_item(restaurant.id, "Teh Tarik", 4.5)

    cashier_login = login(client, "alpha_cashier")
    assert cashier_login.status_code == 302
    assert cashier_login.headers["Location"].endswith(f"/admin/pos/{restaurant.id}")

    pos_page = client.get(f"/admin/pos/{restaurant.id}")
    assert pos_page.status_code == 200
    assert "Manual ticket builder" in pos_page.get_data(as_text=True)

    create_response = client.post(
        f"/admin/pos/{restaurant.id}/create-order",
        data={
            "table_number": 14,
            "food_id": [nasi.id, teh.id],
            "quantity": [2, 1],
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(f"/admin/pos/{restaurant.id}")

    with app.app_context():
        order = Order.query.filter_by(restaurant_id=restaurant.id).one()
        table = Table.query.filter_by(restaurant_id=restaurant.id, table_number=14).one()
        items = OrderItem.query.filter_by(order_id=order.id).order_by(OrderItem.food_id.asc()).all()
        assert order.table_number == 14
        assert order.status == Order.STATUS_SUBMITTED
        assert table.status == Table.STATUS_OCCUPIED
        assert {(item.food_id, item.quantity) for item in items} == {(teh.id, 1), (nasi.id, 2)}

    client.post("/auth/logout", follow_redirects=False)
    kitchen_login = login(client, "alpha_kitchen")
    assert kitchen_login.status_code == 302
    assert kitchen_login.headers["Location"].endswith(f"/admin/kitchen/{restaurant.id}")

    kitchen_page = client.get(f"/admin/kitchen/{restaurant.id}")
    assert kitchen_page.status_code == 200

    orders_response = client.get(f"/admin/kitchen/{restaurant.id}/orders")
    assert orders_response.status_code == 200
    payload = orders_response.get_json()
    assert payload["orders"][0]["order_id"] == order.id
    assert payload["orders"][0]["status"] == Order.STATUS_SUBMITTED
    assert payload["orders"][0]["table_status"] == Table.STATUS_OCCUPIED

    update_response = client.post(f"/admin/kitchen/{restaurant.id}/orders/{order.id}/preparing")
    assert update_response.status_code == 200
    assert update_response.get_json()["status"] == Order.STATUS_PREPARING

    with app.app_context():
        order = Order.query.filter_by(id=order.id, restaurant_id=restaurant.id).one()
        table = Table.query.filter_by(restaurant_id=restaurant.id, table_number=14).one()
        assert order.status == Order.STATUS_PREPARING
        assert table.status == Table.STATUS_OCCUPIED

    ready_response = client.post(f"/admin/kitchen/{restaurant.id}/orders/{order.id}/ready")
    assert ready_response.status_code == 200
    assert ready_response.get_json()["status"] == Order.STATUS_READY

    client.post("/auth/logout", follow_redirects=False)
    cashier_login = login(client, "alpha_cashier")
    assert cashier_login.status_code == 302
    assert cashier_login.headers["Location"].endswith(f"/admin/pos/{restaurant.id}")

    served_response = client.post(
        f"/admin/orders/{restaurant.id}/update/{order.id}",
        data={"status": Order.STATUS_SERVED},
        follow_redirects=False,
    )
    assert served_response.status_code == 302

    paid_response = client.post(
        f"/admin/orders/{restaurant.id}/update/{order.id}",
        data={"status": Order.STATUS_PAID},
        follow_redirects=False,
    )
    assert paid_response.status_code == 302

    with app.app_context():
        order = Order.query.filter_by(id=order.id, restaurant_id=restaurant.id).one()
        table = Table.query.filter_by(restaurant_id=restaurant.id, table_number=14).one()
        assert order.status == Order.STATUS_PAID
        assert table.status == Table.STATUS_NEEDS_CLEANING


def test_illegal_order_status_jump_is_blocked(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=9, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=9, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/orders/{restaurant.id}/update/{order_id}",
        data={"status": Order.STATUS_PAID},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "cannot move" in response.get_data(as_text=True).lower()

    with app.app_context():
        order = Order.query.filter_by(id=order_id, restaurant_id=restaurant.id).one()
        table = Table.query.filter_by(restaurant_id=restaurant.id, table_number=9).one()
        assert order.status == Order.STATUS_SUBMITTED
        assert table.status == Table.STATUS_OCCUPIED


def test_order_detail_page_loads_for_current_restaurant_order(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=5, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=2))
        db.session.add(Table(table_number=5, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{restaurant.id}/{order_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Order summary" in page
    assert "Walk-in guest" in page
    assert "Table 5" in page
    assert "Amount summary" in page
    assert "Payment status" in page
    assert "Unpaid" in page
    assert "Subtotal" in page
    assert "Total" in page
    assert "This order is actively occupying the table." in page
    assert "This timeline is derived because no explicit order events have been recorded" in page


def test_order_detail_displays_order_note_and_empty_state(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)

        noted_order = Order(
            table_number=20,
            restaurant_id=restaurant.id,
            status=Order.STATUS_SUBMITTED,
            note="Birthday table. Avoid peanuts in the sauce.",
        )
        blank_order = Order(
            table_number=21,
            restaurant_id=restaurant.id,
            status=Order.STATUS_SUBMITTED,
        )
        db.session.add_all([noted_order, blank_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=noted_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=blank_order.id, food_id=dish.id, quantity=1),
                Table(table_number=20, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=21, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
            ]
        )
        db.session.commit()
        noted_order_id = noted_order.id
        blank_order_id = blank_order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    noted_page = client.get(f"/admin/orders/{restaurant.id}/{noted_order_id}").get_data(as_text=True)
    blank_page = client.get(f"/admin/orders/{restaurant.id}/{blank_order_id}").get_data(as_text=True)

    assert "Birthday table. Avoid peanuts in the sauce." in noted_page
    assert "No notes provided." in blank_page


def test_order_detail_source_labels_cover_guest_qr_and_pos_orders(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_cashier", role="cashier")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)

    guest_add = client.post(
        "/orders/add_to_cart",
        data={"food_id": dish.id, "table": 30, "restaurant_id": restaurant.id},
        follow_redirects=False,
    )
    assert guest_add.status_code == 302

    guest_checkout = client.post(
        "/orders/checkout",
        data={"table": 30, "restaurant_id": restaurant.id},
        follow_redirects=False,
    )
    assert guest_checkout.status_code == 302

    cashier_login = login(client, "alpha_cashier")
    assert cashier_login.status_code == 302

    pos_create = client.post(
        f"/admin/pos/{restaurant.id}/create-order",
        data={"table_number": 31, "food_id": [dish.id], "quantity": [1]},
        follow_redirects=False,
    )
    assert pos_create.status_code == 302

    with app.app_context():
        guest_order = Order.query.filter_by(restaurant_id=restaurant.id, table_number=30).one()
        pos_order = Order.query.filter_by(restaurant_id=restaurant.id, table_number=31).one()
        guest_context = get_order_detail_context(restaurant.id, guest_order.id, actor_role="owner")
        pos_context = get_order_detail_context(restaurant.id, pos_order.id, actor_role="cashier")

        assert guest_context["source_context"]["label"] == "Customer QR Order"
        assert pos_context["source_context"]["label"] == "POS Order"


def test_order_detail_timeline_actor_role_labels_and_system_fallback(app):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        manager = create_user(restaurant.id, "alpha_manager", role="manager")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=22, restaurant_id=restaurant.id, status=Order.STATUS_READY)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=22, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.add_all(
            [
                OrderEvent(
                    order_id=order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    actor_user_id=manager.id,
                    to_status=Order.STATUS_SUBMITTED,
                    note="POS created a manual order.",
                ),
                OrderEvent(
                    order_id=order.id,
                    restaurant_id=restaurant.id,
                    event_type="inventory_applied",
                    note="Inventory was deducted as the order entered preparation.",
                ),
            ]
        )
        db.session.commit()

        context = get_order_detail_context(restaurant.id, order.id, actor_role="manager")
        actor_labels = [entry["actor_label"] for entry in context["timeline"]]

        assert "Manager" in actor_labels
        assert "System" in actor_labels


def test_cross_tenant_order_detail_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        dish = create_menu_item(beta.id, "Laksa", 15.0)
        order = Order(table_number=2, restaurant_id=beta.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.commit()
        beta_order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{beta.id}/{beta_order_id}")
    assert response.status_code == 403


def test_order_receipt_entry_and_route_stay_inside_current_restaurant(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        owner = create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(
            table_number=23,
            restaurant_id=restaurant.id,
            status=Order.STATUS_SUBMITTED,
            note="Split bill at the counter.",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=2))
        db.session.add(Table(table_number=23, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.add(
            OrderEvent(
                order_id=order.id,
                restaurant_id=restaurant.id,
                event_type="created",
                actor_user_id=owner.id,
                to_status=Order.STATUS_SUBMITTED,
                note="POS created a manual order.",
            )
        )
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    detail_response = client.get(f"/admin/orders/{restaurant.id}/{order_id}")
    detail_page = detail_response.get_data(as_text=True)

    assert detail_response.status_code == 200
    assert f"/admin/orders/{restaurant.id}/{order_id}/receipt" in detail_page
    assert "Print Receipt" in detail_page

    receipt_response = client.get(f"/admin/orders/{restaurant.id}/{order_id}/receipt")
    receipt_page = receipt_response.get_data(as_text=True)

    assert receipt_response.status_code == 200
    assert "Order Receipt" in receipt_page
    assert "Use your browser print dialog for paper receipts." in receipt_page
    assert "Alpha House" in receipt_page
    assert "POS Order" in receipt_page
    assert "Restaurant Admin Receipt" in receipt_page
    assert "Line Items" in receipt_page
    assert "Items Total (Subtotal)" in receipt_page
    assert "Total" in receipt_page
    assert "Payment Status" in receipt_page
    assert "Payment Method" in receipt_page
    assert "Unpaid" in receipt_page
    assert "RM 25.00" in receipt_page
    assert "Split bill at the counter." in receipt_page
    assert "Print This Page" in receipt_page
    assert "onclick=\"window.print()\"" in receipt_page
    assert f"/admin/orders/{restaurant.id}/{order_id}" in receipt_page


def test_cross_tenant_receipt_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        dish = create_menu_item(beta.id, "Laksa", 15.0)
        order = Order(table_number=24, restaurant_id=beta.id, status=Order.STATUS_PAID)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.commit()
        beta_order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{beta.id}/{beta_order_id}/receipt")
    assert response.status_code == 403


def test_order_detail_shows_only_legal_actions_for_current_role(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_kitchen", role="kitchen")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=8, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=8, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_kitchen")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{restaurant.id}/{order_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Start Preparation" in page
    assert "Mark Paid" not in page
    assert "Cancel Order" not in page


def test_order_amount_context_includes_subtotal_total_and_currency(app):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        nasi = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        teh = create_menu_item(restaurant.id, "Teh Tarik", 4.5)
        order = Order(table_number=26, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=order.id, food_id=nasi.id, quantity=2),
                OrderItem(order_id=order.id, food_id=teh.id, quantity=1),
                Table(table_number=26, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
            ]
        )
        db.session.commit()

        detail_context = get_order_detail_context(restaurant.id, order.id, actor_role="owner")
        receipt_context = get_order_receipt_context(restaurant.id, order.id)

        assert detail_context["subtotal"] == 29.5
        assert detail_context["total"] == 29.5
        assert detail_context["currency"] == "RM"
        assert detail_context["total_amount"] == detail_context["total"]

        assert receipt_context["subtotal"] == 29.5
        assert receipt_context["total"] == 29.5
        assert receipt_context["currency"] == "RM"
        assert receipt_context["total_amount"] == receipt_context["total"]


def test_order_payment_context_includes_status_method_and_paid_at(app):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        unpaid_order = Order(table_number=27, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        paid_order = Order(table_number=28, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        db.session.add_all([unpaid_order, paid_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=unpaid_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=paid_order.id, food_id=dish.id, quantity=1),
                Table(table_number=27, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=28, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
            ]
        )
        paid_time = datetime.utcnow().replace(microsecond=0)
        db.session.add(
            OrderEvent(
                order_id=paid_order.id,
                restaurant_id=restaurant.id,
                event_type="status_changed",
                from_status=Order.STATUS_SERVED,
                to_status=Order.STATUS_PAID,
                note="Status changed from Served to Paid.",
                created_at=paid_time,
            )
        )
        db.session.commit()

        unpaid_detail = get_order_detail_context(restaurant.id, unpaid_order.id, actor_role="owner")
        paid_detail = get_order_detail_context(restaurant.id, paid_order.id, actor_role="owner")
        paid_receipt = get_order_receipt_context(restaurant.id, paid_order.id)

        assert unpaid_detail["payment_status"] == "Unpaid"
        assert unpaid_detail["payment_method"] == "Manual"
        assert unpaid_detail["paid_at"] is None

        assert paid_detail["payment_status"] == "Paid"
        assert paid_detail["payment_method"] == "Manual"
        assert paid_detail["paid_at"] is not None

        assert paid_receipt["payment_status"] == "Paid"
        assert paid_receipt["payment_method"] == "Manual"
        assert paid_receipt["paid_at"] is not None


def test_admin_orders_list_context_includes_payment_source_total_and_detail_url(app):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        submitted_order = Order(table_number=41, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        paid_order = Order(table_number=42, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        db.session.add_all([submitted_order, paid_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=submitted_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=paid_order.id, food_id=dish.id, quantity=2),
                Table(table_number=41, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=42, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
                OrderEvent(
                    order_id=submitted_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="Guest checkout submitted the order.",
                ),
                OrderEvent(
                    order_id=paid_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="POS created a manual order.",
                ),
                OrderEvent(
                    order_id=paid_order.id,
                    restaurant_id=restaurant.id,
                    event_type="status_changed",
                    from_status=Order.STATUS_SERVED,
                    to_status=Order.STATUS_PAID,
                    note="Status changed from Served to Paid.",
                ),
            ]
        )
        db.session.commit()

        result = list_order_rows_page(restaurant.id, actor_role="owner")
        rows_by_id = {row["order"].id: row for row in result["rows"]}

        assert rows_by_id[submitted_order.id]["payment_status"] == "Unpaid"
        assert rows_by_id[submitted_order.id]["source_label"] == "Customer QR Order"
        assert rows_by_id[paid_order.id]["payment_status"] == "Paid"
        assert rows_by_id[paid_order.id]["source_label"] == "POS Order"
        assert rows_by_id[paid_order.id]["total_display"] == "RM 25.00"
        assert rows_by_id[paid_order.id]["detail_url"] == f"/admin/orders/{restaurant.id}/{paid_order.id}"


def test_admin_orders_list_shows_payment_source_total_and_detail_entry(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        submitted_order = Order(table_number=43, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        paid_order = Order(table_number=44, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        db.session.add_all([submitted_order, paid_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=submitted_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=paid_order.id, food_id=dish.id, quantity=2),
                Table(table_number=43, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=44, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
                OrderEvent(
                    order_id=submitted_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="Guest checkout submitted the order.",
                ),
                OrderEvent(
                    order_id=paid_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="POS created a manual order.",
                ),
                OrderEvent(
                    order_id=paid_order.id,
                    restaurant_id=restaurant.id,
                    event_type="status_changed",
                    from_status=Order.STATUS_SERVED,
                    to_status=Order.STATUS_PAID,
                    note="Status changed from Served to Paid.",
                ),
            ]
        )
        db.session.commit()
        submitted_order_id = submitted_order.id
        paid_order_id = paid_order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{restaurant.id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Payment Status" in page
    assert "Source" in page
    assert "Total" in page
    assert "Paid" in page
    assert "Unpaid" in page
    assert "POS Order" in page
    assert "Customer QR Order" in page
    assert "RM 25.00" in page
    assert "View Details" in page
    assert f"/admin/orders/{restaurant.id}/{submitted_order_id}" in page
    assert f"/admin/orders/{restaurant.id}/{paid_order_id}" in page
    assert "Start Preparation" in page


def test_admin_orders_filters_cover_status_payment_source_and_combinations(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        owner = create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)

        guest_order = Order(table_number=51, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        paid_pos_order = Order(table_number=52, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        admin_order = Order(table_number=53, restaurant_id=restaurant.id, status=Order.STATUS_READY)
        db.session.add_all([guest_order, paid_pos_order, admin_order])
        db.session.flush()
        db.session.add_all(
            [
                OrderItem(order_id=guest_order.id, food_id=dish.id, quantity=1),
                OrderItem(order_id=paid_pos_order.id, food_id=dish.id, quantity=2),
                OrderItem(order_id=admin_order.id, food_id=dish.id, quantity=1),
                Table(table_number=51, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=52, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING),
                Table(table_number=53, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                OrderEvent(
                    order_id=guest_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="Guest checkout submitted the order.",
                ),
                OrderEvent(
                    order_id=paid_pos_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    to_status=Order.STATUS_SUBMITTED,
                    note="POS created a manual order.",
                ),
                OrderEvent(
                    order_id=paid_pos_order.id,
                    restaurant_id=restaurant.id,
                    event_type="status_changed",
                    from_status=Order.STATUS_SERVED,
                    to_status=Order.STATUS_PAID,
                    note="Status changed from Served to Paid.",
                ),
                OrderEvent(
                    order_id=admin_order.id,
                    restaurant_id=restaurant.id,
                    event_type="created",
                    actor_user_id=owner.id,
                    to_status=Order.STATUS_SUBMITTED,
                    note="Created from admin console.",
                ),
            ]
        )
        db.session.commit()

        unfiltered = list_order_rows_page(restaurant.id, actor_role="owner")
        submitted_only = list_order_rows_page(restaurant.id, status=Order.STATUS_SUBMITTED, actor_role="owner")
        paid_only = list_order_rows_page(restaurant.id, payment="Paid", actor_role="owner")
        guest_only = list_order_rows_page(restaurant.id, source="Customer QR Order", actor_role="owner")
        active_only = list_order_rows_page(restaurant.id, status="active", actor_role="owner")
        combined = list_order_rows_page(
            restaurant.id,
            status=Order.STATUS_PAID,
            payment="Paid",
            source="POS Order",
            actor_role="owner",
        )

        guest_order_id = guest_order.id
        paid_pos_order_id = paid_pos_order.id
        admin_order_id = admin_order.id

        assert unfiltered["pagination"]["total"] == 3
        assert {row["order"].id for row in unfiltered["rows"]} == {guest_order_id, paid_pos_order_id, admin_order_id}
        assert {row["order"].id for row in submitted_only["rows"]} == {guest_order_id}
        assert {row["order"].id for row in paid_only["rows"]} == {paid_pos_order_id}
        assert {row["order"].id for row in guest_only["rows"]} == {guest_order_id}
        assert {row["order"].id for row in active_only["rows"]} == {guest_order_id, admin_order_id}
        assert {row["order"].id for row in combined["rows"]} == {paid_pos_order_id}

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    filtered_response = client.get(
        f"/admin/orders/{restaurant.id}?status=paid&payment=Paid&source=POS+Order"
    )
    filtered_page = filtered_response.get_data(as_text=True)

    assert filtered_response.status_code == 200
    assert f"/admin/orders/{restaurant.id}/{paid_pos_order_id}" in filtered_page
    assert f"/admin/orders/{restaurant.id}/{guest_order_id}" not in filtered_page
    assert f"/admin/orders/{restaurant.id}/{admin_order_id}" not in filtered_page


def test_cross_tenant_admin_orders_list_access_is_forbidden(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        dish = create_menu_item(beta.id, "Laksa", 15.0)
        order = Order(table_number=45, restaurant_id=beta.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.commit()

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{beta.id}")
    assert response.status_code == 403


def test_admin_orders_empty_states_cover_no_orders_and_filter_miss(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    empty_response = client.get(f"/admin/orders/{restaurant.id}")
    empty_page = empty_response.get_data(as_text=True)
    assert empty_response.status_code == 200
    assert "No orders yet" in empty_page
    assert "Create your first order to start managing your restaurant." in empty_page

    with app.app_context():
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=95, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.commit()

    filtered_response = client.get(f"/admin/orders/{restaurant.id}?payment=Paid")
    filtered_page = filtered_response.get_data(as_text=True)
    assert filtered_response.status_code == 200
    assert "No orders match your filters" in filtered_page
    assert "Try adjusting your filters or create a new order." in filtered_page


def test_terminal_order_detail_hides_next_actions_and_can_release_table(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=11, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=11, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING))
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.get(f"/admin/orders/{restaurant.id}/{order_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Order is complete. No further workflow actions are available." in page
    assert "Mark Table Available" in page
    assert "Start Preparation" not in page


def test_order_detail_inventory_context_covers_pending_applied_and_restored(app):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        dish = create_menu_item(restaurant.id, "Signature Rice", 19.0)
        stock_item = create_inventory_item_record(restaurant.id, "Chicken stock", stock=10, unit="portion")
        db.session.add(
            MenuInventoryRequirement(
                menu_id=dish.id,
                inventory_item_id=stock_item.id,
                quantity_required=2,
            )
        )

        pending_order = Order(table_number=1, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        applied_order = Order(table_number=2, restaurant_id=restaurant.id, status=Order.STATUS_PREPARING)
        restored_order = Order(table_number=3, restaurant_id=restaurant.id, status=Order.STATUS_CANCELLED)
        db.session.add_all([pending_order, applied_order, restored_order])
        db.session.flush()
        for order in (pending_order, applied_order, restored_order):
            db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))

        db.session.add_all(
            [
                OrderEvent(order_id=applied_order.id, restaurant_id=restaurant.id, event_type="inventory_applied", note="Applied"),
                OrderEvent(order_id=restored_order.id, restaurant_id=restaurant.id, event_type="inventory_applied", note="Applied"),
                OrderEvent(order_id=restored_order.id, restaurant_id=restaurant.id, event_type="inventory_restored", note="Restored"),
            ]
        )
        applied_order.inventory_applied_at = datetime.utcnow()
        db.session.commit()

        pending_context = get_order_detail_context(restaurant.id, pending_order.id, actor_role="owner")
        applied_context = get_order_detail_context(restaurant.id, applied_order.id, actor_role="owner")
        restored_context = get_order_detail_context(restaurant.id, restored_order.id, actor_role="owner")

        assert pending_context["inventory_context"]["status"] == "pending"
        assert "will deduct" in pending_context["inventory_context"]["summary"]
        assert applied_context["inventory_context"]["status"] == "applied"
        assert "has been deducted" in applied_context["inventory_context"]["summary"]
        assert restored_context["inventory_context"]["status"] == "restored"
        assert "restored after the order was cancelled" in restored_context["inventory_context"]["summary"]


def test_order_events_are_written_for_status_transitions(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_cashier", role="cashier")
        create_user(restaurant.id, "alpha_kitchen", role="kitchen")
        dish = create_menu_item(restaurant.id, "Signature Rice", 19.0)
        stock_item = create_inventory_item_record(restaurant.id, "Chicken stock", stock=10, unit="portion")
        db.session.add(
            MenuInventoryRequirement(
                menu_id=dish.id,
                inventory_item_id=stock_item.id,
                quantity_required=1,
            )
        )
        order = Order(table_number=12, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=12, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()
        order_id = order.id

    kitchen_login = login(client, "alpha_kitchen")
    assert kitchen_login.status_code == 302
    client.post(f"/admin/kitchen/{restaurant.id}/orders/{order_id}/preparing")
    client.post(f"/admin/kitchen/{restaurant.id}/orders/{order_id}/ready")
    client.post("/auth/logout", follow_redirects=False)

    cashier_login = login(client, "alpha_cashier")
    assert cashier_login.status_code == 302
    client.post(
        f"/admin/orders/{restaurant.id}/{order_id}/transition",
        data={"status": Order.STATUS_SERVED},
        follow_redirects=False,
    )
    client.post(
        f"/admin/orders/{restaurant.id}/{order_id}/transition",
        data={"status": Order.STATUS_PAID},
        follow_redirects=False,
    )

    with app.app_context():
        events = (
            OrderEvent.query.filter_by(order_id=order_id, restaurant_id=restaurant.id)
            .order_by(OrderEvent.id.asc())
            .all()
        )
        event_types = [event.event_type for event in events]
        transitions = [(event.from_status, event.to_status) for event in events if event.event_type == "status_changed"]
        assert "inventory_applied" in event_types
        assert "table_cleaning_required" in event_types
        assert (Order.STATUS_SUBMITTED, Order.STATUS_PREPARING) in transitions
        assert (Order.STATUS_READY, Order.STATUS_SERVED) in transitions
        assert (Order.STATUS_SERVED, Order.STATUS_PAID) in transitions


def test_inventory_shortage_blocks_order_from_entering_preparation(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_kitchen", role="kitchen")
        dish = create_menu_item(restaurant.id, "Signature Rice", 19.0)
        stock_item = create_inventory_item_record(restaurant.id, "Chicken stock", stock=1, unit="portion")
        db.session.add(
            MenuInventoryRequirement(
                menu_id=dish.id,
                inventory_item_id=stock_item.id,
                quantity_required=2,
            )
        )
        order = Order(table_number=6, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        db.session.add(Table(table_number=6, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED))
        db.session.commit()
        order_id = order.id

    login_response = login(client, "alpha_kitchen")
    assert login_response.status_code == 302

    response = client.post(f"/admin/kitchen/{restaurant.id}/orders/{order_id}/preparing")
    assert response.status_code == 409
    assert "Inventory is too low" in response.get_json()["error"]

    with app.app_context():
        order = Order.query.filter_by(id=order_id, restaurant_id=restaurant.id).one()
        stock_item = InventoryItem.query.filter_by(restaurant_id=restaurant.id, name="Chicken stock").one()
        assert order.status == Order.STATUS_SUBMITTED
        assert stock_item.stock == 1


def test_paid_table_can_be_manually_released_after_cleaning(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        table = Table(table_number=4, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING)
        db.session.add(table)
        db.session.commit()
        table_id = table.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/tables/{restaurant.id}/status/{table_id}",
        data={"status": Table.STATUS_AVAILABLE},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).one()
        assert table.status == Table.STATUS_AVAILABLE


def test_manual_table_release_after_cleaning_writes_order_event_and_shows_in_timeline(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        owner = create_user(restaurant.id, "alpha_owner")
        dish = create_menu_item(restaurant.id, "Nasi Lemak", 12.5)
        order = Order(table_number=15, restaurant_id=restaurant.id, status=Order.STATUS_PAID)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        table = Table(table_number=15, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING)
        db.session.add(table)
        db.session.flush()
        db.session.add(
            OrderEvent(
                order_id=order.id,
                restaurant_id=restaurant.id,
                event_type="table_cleaning_required",
                actor_user_id=owner.id,
                note="Table 15 is now waiting for cleaning.",
            )
        )
        db.session.commit()
        order_id = order.id
        table_id = table.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/tables/{restaurant.id}/status/{table_id}",
        data={"status": Table.STATUS_AVAILABLE, "return_order_id": order_id},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/admin/orders/{restaurant.id}/{order_id}")

    with app.app_context():
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).one()
        event = (
            OrderEvent.query.filter_by(
                order_id=order_id,
                restaurant_id=restaurant.id,
                event_type="table_marked_available",
            )
            .order_by(OrderEvent.id.desc())
            .first()
        )
        assert table.status == Table.STATUS_AVAILABLE
        assert event is not None
        assert event.actor_user_id == owner.id
        assert "marked available after cleaning" in event.note

    detail_response = client.get(f"/admin/orders/{restaurant.id}/{order_id}")
    detail_page = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Table available again" in detail_page
    assert "marked available after cleaning" in detail_page


def test_manual_table_release_without_matching_order_does_not_fail_or_create_event(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        table = Table(table_number=16, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING)
        db.session.add(table)
        db.session.commit()
        table_id = table.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/tables/{restaurant.id}/status/{table_id}",
        data={"status": Table.STATUS_AVAILABLE},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).one()
        events = OrderEvent.query.filter_by(restaurant_id=restaurant.id, event_type="table_marked_available").all()
        assert table.status == Table.STATUS_AVAILABLE
        assert events == []


def test_kitchen_role_cannot_manually_release_cleaning_table(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_kitchen", role="kitchen")
        table = Table(table_number=17, restaurant_id=restaurant.id, status=Table.STATUS_NEEDS_CLEANING)
        db.session.add(table)
        db.session.commit()
        table_id = table.id

    login_response = login(client, "alpha_kitchen")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/tables/{restaurant.id}/status/{table_id}",
        data={"status": Table.STATUS_AVAILABLE},
        follow_redirects=False,
    )
    assert response.status_code == 403

    with app.app_context():
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant.id).one()
        events = OrderEvent.query.filter_by(restaurant_id=restaurant.id, event_type="table_marked_available").all()
        assert table.status == Table.STATUS_NEEDS_CLEANING
        assert events == []


def test_cross_tenant_table_release_does_not_write_event_to_other_restaurant_order(app, client):
    with app.app_context():
        alpha = create_restaurant("Alpha House", "alpha-house")
        beta = create_restaurant("Beta House", "beta-house")
        create_user(alpha.id, "alpha_owner")
        beta_owner = create_user(beta.id, "beta_owner")
        dish = create_menu_item(beta.id, "Laksa", 15.0)
        order = Order(table_number=18, restaurant_id=beta.id, status=Order.STATUS_PAID)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, food_id=dish.id, quantity=1))
        table = Table(table_number=18, restaurant_id=beta.id, status=Table.STATUS_NEEDS_CLEANING)
        db.session.add(table)
        db.session.flush()
        db.session.add(
            OrderEvent(
                order_id=order.id,
                restaurant_id=beta.id,
                event_type="table_cleaning_required",
                actor_user_id=beta_owner.id,
                note="Table 18 is now waiting for cleaning.",
            )
        )
        db.session.commit()
        beta_table_id = table.id
        beta_order_id = order.id

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    response = client.post(
        f"/admin/tables/{beta.id}/status/{beta_table_id}",
        data={"status": Table.STATUS_AVAILABLE, "return_order_id": beta_order_id},
        follow_redirects=False,
    )
    assert response.status_code == 403

    with app.app_context():
        table = Table.query.filter_by(id=beta_table_id, restaurant_id=beta.id).one()
        events = OrderEvent.query.filter_by(
            order_id=beta_order_id,
            restaurant_id=beta.id,
            event_type="table_marked_available",
        ).all()
        assert table.status == Table.STATUS_NEEDS_CLEANING
        assert events == []


def test_operations_workspace_shows_business_metrics(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_manager", role="manager")
        nasi = create_menu_item(restaurant.id, "Nasi Lemak", 10.0)
        teh = create_menu_item(restaurant.id, "Teh Tarik", 5.0)

        now = datetime.utcnow()
        order_one = Order(table_number=3, restaurant_id=restaurant.id, status=Order.STATUS_SUBMITTED, created_at=now - timedelta(minutes=8))
        order_two = Order(table_number=3, restaurant_id=restaurant.id, status=Order.STATUS_PREPARING, created_at=now - timedelta(minutes=4))
        order_three = Order(table_number=8, restaurant_id=restaurant.id, status=Order.STATUS_READY, created_at=now - timedelta(minutes=2))
        db.session.add_all([order_one, order_two, order_three])
        db.session.flush()
        db.session.add_all(
            [
                Table(table_number=3, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
                Table(table_number=8, restaurant_id=restaurant.id, status=Table.STATUS_OCCUPIED),
            ]
        )
        db.session.add_all(
            [
                OrderItem(order_id=order_one.id, food_id=nasi.id, quantity=2),
                OrderItem(order_id=order_two.id, food_id=teh.id, quantity=1),
                OrderItem(order_id=order_three.id, food_id=nasi.id, quantity=1),
                OrderItem(order_id=order_three.id, food_id=teh.id, quantity=2),
            ]
        )
        db.session.commit()

    login_response = login(client, "alpha_manager")
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith(f"/admin/operations/{restaurant.id}")

    response = client.get(f"/admin/operations/{restaurant.id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Average check" in page
    assert "RM 15.00" in page
    assert "Table 3" in page
    assert "33.3%" in page


def test_team_invitation_acceptance_and_role_management(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        owner = create_user(restaurant.id, "alpha_owner")

    login_response = login(client, owner.username)
    assert login_response.status_code == 302

    invite_response = client.post(
        f"/admin/team/{restaurant.id}/invite",
        data={"email": "manager@alpha.com", "role": "manager"},
        follow_redirects=False,
    )
    assert invite_response.status_code == 302

    with app.app_context():
        invitation = TeamInvitation.query.filter_by(email="manager@alpha.com").one()
        invite_token = invitation.token
        assert invitation.role == "manager"

    accept_page = client.get(f"/auth/accept-invite/{invite_token}")
    assert accept_page.status_code == 200

    accept_response = client.post(
        f"/auth/accept-invite/{invite_token}",
        data={"username": "alpha_manager", "password": "password123"},
        follow_redirects=False,
    )
    assert accept_response.status_code == 302
    assert accept_response.headers["Location"].endswith(f"/admin/operations/{restaurant.id}")

    client.post("/auth/logout", follow_redirects=False)
    login(client, owner.username)

    with app.app_context():
        invited_user = User.query.filter_by(username="alpha_manager").one()

    role_update = client.post(
        f"/admin/team/{restaurant.id}/members/{invited_user.id}/role",
        data={"role": "cashier"},
        follow_redirects=False,
    )
    assert role_update.status_code == 302

    with app.app_context():
        invited_user = User.query.filter_by(username="alpha_manager").one()
        invitation = TeamInvitation.query.filter_by(token=invite_token).one()
        assert invited_user.role == "cashier"
        assert invitation.status == "accepted"

    client.post("/auth/logout", follow_redirects=False)
    cashier_login = login(client, "alpha_manager")
    assert cashier_login.status_code == 302
    assert cashier_login.headers["Location"].endswith(f"/admin/pos/{restaurant.id}")

    pos_response = client.get(f"/admin/pos/{restaurant.id}")
    menu_response = client.get(f"/admin/menu/{restaurant.id}")
    assert pos_response.status_code == 200
    assert menu_response.status_code == 403


def test_billing_portal_and_webhook_sync_subscription_state(app, client, monkeypatch):
    class FakePortalSession:
        url = "https://billing.example/session"

    class FakeBillingPortalSession:
        @staticmethod
        def create(customer, return_url):
            assert customer == "cus_123"
            assert return_url.endswith("/billing/1")
            return FakePortalSession()

    class FakeStripeSubscription:
        @staticmethod
        def modify(subscription_id, cancel_at_period_end):
            assert subscription_id == "sub_123"
            assert cancel_at_period_end is True
            return {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "active",
                "cancel_at_period_end": True,
                "current_period_end": 1893456000,
                "metadata": {
                    "restaurant_id": "1",
                    "plan_key": "pro",
                },
            }

    class FakeWebhook:
        @staticmethod
        def construct_event(payload, signature_header, webhook_secret):
            assert signature_header == "sig_test"
            assert webhook_secret == "whsec_test_123"
            return json.loads(payload.decode("utf-8"))

    fake_stripe = SimpleNamespace(
        api_key=None,
        billing_portal=SimpleNamespace(Session=FakeBillingPortalSession),
        Subscription=FakeStripeSubscription,
        Webhook=FakeWebhook,
    )
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)

    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        subscription = Subscription(
            restaurant_id=restaurant.id,
            plan="pro",
            status="active",
            billing_provider="stripe",
            provider_customer_id="cus_123",
            provider_subscription_id="sub_123",
        )
        db.session.add(subscription)
        db.session.commit()

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    portal_response = client.post(f"/billing/{restaurant.id}/portal", follow_redirects=False)
    assert portal_response.status_code == 303
    assert portal_response.headers["Location"] == "https://billing.example/session"

    cancel_response = client.post(f"/billing/{restaurant.id}/cancel", follow_redirects=False)
    assert cancel_response.status_code == 302
    assert cancel_response.headers["Location"].endswith(f"/billing/{restaurant.id}/status")

    payload = {
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "subscription": "sub_123",
                "customer": "cus_123",
                "amount_due": 9900,
                "currency": "myr",
                "hosted_invoice_url": "https://billing.example/invoice/123",
            }
        },
    }
    webhook_response = client.post(
        "/stripe/webhook",
        data=json.dumps(payload),
        headers={"Stripe-Signature": "sig_test"},
        content_type="application/json",
    )
    assert webhook_response.status_code == 200

    history_response = client.get(f"/billing/{restaurant.id}/history")
    status_response = client.get(f"/billing/{restaurant.id}/status")
    assert history_response.status_code == 200
    assert status_response.status_code == 200
    assert "invoice.payment_failed" in history_response.get_data(as_text=True)
    assert "Latest billing issue" in status_response.get_data(as_text=True)

    with app.app_context():
        subscription = Subscription.query.filter_by(restaurant_id=restaurant.id).one()
        assert subscription.status == "past_due"
        assert subscription.provider_customer_id == "cus_123"
        assert subscription.provider_subscription_id == "sub_123"
        assert subscription.cancel_at_period_end is True
        events = BillingEvent.query.filter_by(restaurant_id=restaurant.id).all()
        assert len(events) >= 2


def test_billing_page_can_prepare_duitnow_manual_payment_details(app, client):
    app.config.update(
        BILLING_PROVIDER="duitnow_manual",
        DUITNOW_RECIPIENT_NAME="Restaurant OS Sdn Bhd",
        DUITNOW_ACCOUNT_ID="DNT-998877",
        DUITNOW_ACCOUNT_TYPE="Merchant ID",
        DUITNOW_REFERENCE_PREFIX="ROS",
        DUITNOW_PAYMENT_NOTE="Complete the transfer and confirm it manually before changing plans.",
    )

    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    details_response = client.post(f"/billing/{restaurant.id}/duitnow/pro", follow_redirects=False)
    assert details_response.status_code == 302
    assert details_response.headers["Location"].endswith(f"/billing/{restaurant.id}?provider=duitnow_manual&duitnow_plan=pro")

    billing_response = client.get(details_response.headers["Location"])
    billing_page = billing_response.get_data(as_text=True)

    assert billing_response.status_code == 200
    assert "DuitNow payment details" in billing_page
    assert "DuitNow Manual" in billing_page
    assert "RM 39.00" in billing_page
    assert "ROS-1-PRO" in billing_page
    assert "Restaurant OS Sdn Bhd" in billing_page
    assert "Get DuitNow Payment Details" in billing_page or "DuitNow Details Ready" in billing_page

    with app.app_context():
        event = BillingEvent.query.filter_by(source="duitnow_manual").order_by(BillingEvent.id.desc()).first()
        subscription = Subscription.query.filter_by(restaurant_id=restaurant.id).first()
        assert event is not None
        assert event.event_type == "duitnow.instructions_requested"
        assert event.amount_cents == 3900
        assert subscription is not None
        assert subscription.billing_provider == "duitnow_manual"


def test_billing_page_can_use_bundled_duitnow_qr_defaults(app, client):
    app.config.update(
        BILLING_PROVIDER="duitnow_manual",
        DUITNOW_RECIPIENT_NAME="",
        DUITNOW_ACCOUNT_ID="",
        DUITNOW_QR_IMAGE_URL="",
        DUITNOW_ACCOUNT_TYPE="",
    )

    with app.app_context():
        restaurant = create_restaurant("Beta House", "beta-house")
        create_user(restaurant.id, "beta_owner")

    login_response = login(client, "beta_owner")
    assert login_response.status_code == 302

    details_response = client.post(f"/billing/{restaurant.id}/duitnow/pro", follow_redirects=False)
    assert details_response.status_code == 302

    billing_response = client.get(details_response.headers["Location"])
    billing_page = billing_response.get_data(as_text=True)

    assert billing_response.status_code == 200
    assert "CHEN YAO HONG" in billing_page
    assert "Touch &#39;n Go eWallet" in billing_page or "Touch 'n Go eWallet" in billing_page
    assert "chen-yao-hong-tng-qr.jpg" in billing_page


def test_billing_payment_submission_records_pending_verification_without_upgrading_plan(app, client):
    app.config.update(
        BILLING_PROVIDER="duitnow_manual",
        DUITNOW_RECIPIENT_NAME="Restaurant OS Sdn Bhd",
        DUITNOW_ACCOUNT_ID="DNT-998877",
        DUITNOW_ACCOUNT_TYPE="Merchant ID",
        BILLING_UPLOAD_DIR="/tmp/restaurant-system-billing-uploads",
    )

    with app.app_context():
        restaurant = create_restaurant("Gamma House", "gamma-house")
        create_user(restaurant.id, "gamma_owner")

    login_response = login(client, "gamma_owner")
    assert login_response.status_code == 302

    submit_response = client.post(
        f"/billing/{restaurant.id}/duitnow/pro/submit",
        data={
            "payment_reference": "TNG-123456",
            "payment_screenshot": (BytesIO(b"fake-image"), "proof.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert submit_response.status_code == 302
    assert submit_response.headers["Location"].endswith(f"/billing/{restaurant.id}?provider=duitnow_manual&duitnow_plan=pro")

    billing_response = client.get(submit_response.headers["Location"])
    billing_page = billing_response.get_data(as_text=True)
    assert billing_response.status_code == 200
    assert "Payment submitted" in billing_page
    assert "Pending verification" in billing_page
    assert "TNG-123456" in billing_page
    assert "proof.png" in billing_page

    with app.app_context():
        event = (
            BillingEvent.query.filter_by(
                restaurant_id=restaurant.id,
                event_type="payment_submitted",
                status="pending_verification",
            )
            .order_by(BillingEvent.id.desc())
            .first()
        )
        subscription = Subscription.query.filter_by(restaurant_id=restaurant.id).first()
        assert event is not None
        assert event.plan_key == "pro"
        assert event.payment_reference == "TNG-123456"
        assert event.attachment_path is not None
        assert subscription is not None
        assert subscription.plan == "starter"
        assert subscription.status == "trialing"


def test_billing_payment_submission_requires_reference(app, client):
    app.config.update(
        BILLING_PROVIDER="duitnow_manual",
        DUITNOW_RECIPIENT_NAME="Restaurant OS Sdn Bhd",
        DUITNOW_ACCOUNT_ID="DNT-998877",
    )

    with app.app_context():
        restaurant = create_restaurant("Delta House", "delta-house")
        create_user(restaurant.id, "delta_owner")

    login_response = login(client, "delta_owner")
    assert login_response.status_code == 302

    submit_response = client.post(
        f"/billing/{restaurant.id}/duitnow/pro/submit",
        data={"payment_reference": ""},
        follow_redirects=True,
    )
    submit_page = submit_response.get_data(as_text=True)

    assert submit_response.status_code == 200
    assert "Payment reference is required." in submit_page

    with app.app_context():
        event = BillingEvent.query.filter_by(restaurant_id=restaurant.id, event_type="payment_submitted").first()
        assert event is None


def test_server_side_menu_and_order_lists_support_sorting_and_pagination(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")
        menu_items = []
        for index in range(1, 10):
            menu_items.append(
                create_menu_item(
                    restaurant.id,
                    f"Dish {index:02d}",
                    float(index),
                )
            )
            item = Menu.query.filter_by(id=menu_items[-1].id).one()
            item.category = "drink" if index % 2 == 0 else "main"
        db.session.commit()

        now = datetime.utcnow()
        for index, item in enumerate(menu_items, start=1):
            order = Order(
                table_number=index,
                restaurant_id=restaurant.id,
                status=Order.STATUS_READY if index % 3 == 0 else Order.STATUS_SUBMITTED,
                created_at=now - timedelta(minutes=index),
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(OrderItem(order_id=order.id, food_id=item.id, quantity=1))
        db.session.commit()

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    menu_page = client.get(f"/admin/menu/{restaurant.id}?page=2&sort=name&dir=asc")
    menu_html = menu_page.get_data(as_text=True)
    assert menu_page.status_code == 200
    assert "Dish 09" in menu_html
    assert "Dish 01" not in menu_html
    assert "Showing 9-9 of 9" in menu_html

    filtered_menu = client.get(f"/admin/menu/{restaurant.id}?category=drink&sort=price&dir=desc")
    filtered_menu_html = filtered_menu.get_data(as_text=True)
    assert filtered_menu.status_code == 200
    assert "Dish 08" in filtered_menu_html
    assert "Dish 07" not in filtered_menu_html

    ready_orders = client.get(f"/admin/orders/{restaurant.id}?status=ready&sort=table&dir=asc")
    ready_orders_html = ready_orders.get_data(as_text=True)
    assert ready_orders.status_code == 200
    assert '">#3</a>' in ready_orders_html
    assert '">#6</a>' in ready_orders_html
    assert '">#1</a>' not in ready_orders_html
    assert "Showing 1-3 of 3" in ready_orders_html


def test_team_and_billing_history_lists_support_server_side_filters(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        owner = create_user(restaurant.id, "alpha_owner")
        create_user(restaurant.id, "anna_cashier", role="cashier")
        create_user(restaurant.id, "zoe_manager", role="manager")

        pending_invitation = TeamInvitation(
            restaurant_id=restaurant.id,
            email="cashier@alpha.com",
            role="cashier",
            token="pending-token",
            status="pending",
            invited_by_user_id=owner.id,
            expires_at=datetime.utcnow() + timedelta(days=3),
        )
        accepted_invitation = TeamInvitation(
            restaurant_id=restaurant.id,
            email="manager@alpha.com",
            role="manager",
            token="accepted-token",
            status="accepted",
            invited_by_user_id=owner.id,
            expires_at=datetime.utcnow() + timedelta(days=3),
        )
        db.session.add_all([pending_invitation, accepted_invitation])

        db.session.add_all(
            [
                BillingEvent(
                    restaurant_id=restaurant.id,
                    event_type="invoice.payment_failed",
                    source="stripe",
                    status="past_due",
                    summary="Stripe payment failed for April.",
                    occurred_at=datetime.utcnow(),
                ),
                BillingEvent(
                    restaurant_id=restaurant.id,
                    event_type="manual.plan_changed",
                    source="manual",
                    status="active",
                    summary="Moved to Pro plan.",
                    occurred_at=datetime.utcnow() - timedelta(days=1),
                ),
            ]
        )
        db.session.commit()

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    team_page = client.get(
        f"/admin/team/{restaurant.id}?member_role=cashier&member_sort=username&member_dir=asc&invite_status=pending&invite_sort=email&invite_dir=asc"
    )
    team_html = team_page.get_data(as_text=True)
    assert team_page.status_code == 200
    assert "anna_cashier" in team_html
    assert "zoe_manager" not in team_html
    assert "cashier@alpha.com" in team_html
    assert "manager@alpha.com" not in team_html

    billing_page = client.get(f"/billing/{restaurant.id}/history?source=stripe&status=past_due&sort=occurred_at&dir=desc")
    billing_html = billing_page.get_data(as_text=True)
    assert billing_page.status_code == 200
    assert "invoice.payment_failed" in billing_html
    assert "Stripe payment failed for April." in billing_html
    assert "manual.plan_changed" not in billing_html


def test_catalog_inventory_and_table_admin_pages_are_backed_by_real_data(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    categories_page = client.get(f"/admin/categories/{restaurant.id}")
    assert categories_page.status_code == 200
    categories_html = categories_page.get_data(as_text=True)
    assert "Current categories" in categories_html
    assert "Main" in categories_html

    add_category_response = client.post(
        f"/admin/categories/{restaurant.id}/add",
        data={"name": "seasonal"},
        follow_redirects=False,
    )
    assert add_category_response.status_code == 302

    inventory_response = client.post(
        f"/admin/inventory/{restaurant.id}/add",
        data={
            "name": "Chicken thigh",
            "stock": "8",
            "unit": "kg",
            "cost": "18.50",
        },
        follow_redirects=False,
    )
    assert inventory_response.status_code == 302

    add_tables_response = client.post(
        f"/admin/tables/{restaurant.id}/add",
        data={"starting_at": 10, "count": 2},
        follow_redirects=False,
    )
    assert add_tables_response.status_code == 302

    with app.app_context():
        seasonal = MenuCategory.query.filter_by(restaurant_id=restaurant.id, name="seasonal").one()
        inventory_item = InventoryItem.query.filter_by(restaurant_id=restaurant.id, name="Chicken thigh").one()
        table_ten = Table.query.filter_by(restaurant_id=restaurant.id, table_number=10).one()
        table_eleven = Table.query.filter_by(restaurant_id=restaurant.id, table_number=11).one()
        assert seasonal.name == "seasonal"
        assert inventory_item.unit == "kg"
        assert inventory_item.cost == 18.5
        assert table_ten.status == Table.STATUS_AVAILABLE
        assert table_eleven.status == Table.STATUS_AVAILABLE

    table_update_response = client.post(
        f"/admin/tables/{restaurant.id}/status/{table_ten.id}",
        data={"status": "occupied"},
        follow_redirects=False,
    )
    assert table_update_response.status_code == 302

    inventory_page = client.get(f"/admin/inventory/{restaurant.id}?q=chicken")
    tables_page = client.get(f"/admin/tables/{restaurant.id}")
    qr_page = client.get(f"/admin/tables/{restaurant.id}/qr")
    qr_image = client.get(f"/admin/tables/{restaurant.id}/qr/10.png")

    assert inventory_page.status_code == 200
    assert tables_page.status_code == 200
    assert qr_page.status_code == 200
    assert qr_image.status_code == 200
    assert qr_image.content_type == "image/png"
    assert "Chicken thigh" in inventory_page.get_data(as_text=True)
    assert "Table 10" in tables_page.get_data(as_text=True)
    assert "http://localhost/menu/r/alpha-house?table=10" in qr_page.get_data(as_text=True)

    with app.app_context():
        table_ten = Table.query.filter_by(restaurant_id=restaurant.id, table_number=10).one()
        assert table_ten.status == "occupied"


def test_owner_can_create_menu_item_with_category_and_inventory_link(app, client):
    with app.app_context():
        restaurant = create_restaurant("Alpha House", "alpha-house")
        create_user(restaurant.id, "alpha_owner")

    login_response = login(client, "alpha_owner")
    assert login_response.status_code == 302

    category_response = client.post(
        f"/admin/categories/{restaurant.id}/add",
        data={"name": "grill"},
        follow_redirects=False,
    )
    assert category_response.status_code == 302

    inventory_response = client.post(
        f"/admin/inventory/{restaurant.id}/add",
        data={
            "name": "Beef patty",
            "stock": "12",
            "unit": "piece",
            "cost": "8.00",
        },
        follow_redirects=False,
    )
    assert inventory_response.status_code == 302

    with app.app_context():
        inventory_item = InventoryItem.query.filter_by(restaurant_id=restaurant.id, name="Beef patty").one()

    menu_response = client.post(
        f"/admin/menu/{restaurant.id}/add",
        data={
            "name": "Smash Burger",
            "price": "24.50",
            "category": "grill",
            "description": "House burger with fries.",
            "inventory_item_id": inventory_item.id,
            "inventory_quantity": "1",
        },
        follow_redirects=False,
    )
    assert menu_response.status_code == 302

    with app.app_context():
        category = MenuCategory.query.filter_by(restaurant_id=restaurant.id, name="grill").one()
        menu_item = Menu.query.filter_by(restaurant_id=restaurant.id, name="Smash Burger").one()
        requirement = MenuInventoryRequirement.query.filter_by(menu_id=menu_item.id, inventory_item_id=inventory_item.id).one()
        assert category.name == "grill"
        assert menu_item.category == "grill"
        assert requirement.quantity_required == 1
