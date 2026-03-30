from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.exceptions import AppError, ValidationError
from app.models.order import Order
from app.services.access_control import (
    BILLING_ROLES,
    DASHBOARD_ROLES,
    KITCHEN_ROLES,
    MENU_ROLES,
    OPERATIONS_ROLES,
    ORDER_ROLES,
    OVERVIEW_ROLES,
    POS_ROLES,
    TABLE_ROLES,
    TEAM_ROLES,
    authorize_restaurant_access,
)
from app.services.team_service import (
    INVITABLE_ROLES,
    ROLE_LABELS,
    create_team_invitation,
    get_team_invitation,
    list_team_invitations_page,
    list_team_members_page,
    revoke_team_invitation,
    update_team_member_role,
)
from app.services.admin_service import (
    create_menu_item,
    delete_menu_item,
    get_menu_item,
    get_dashboard_snapshot,
    get_operations_snapshot,
    get_pos_snapshot,
    list_menu_items_page,
    list_order_rows_page,
    serialize_kitchen_orders,
)
from app.services.inventory_service import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    create_inventory_item,
    list_inventory_items,
    list_inventory_items_page,
)
from app.services.order_service import (
    KITCHEN_VISIBLE_STATUSES,
    ORDER_ACTION_LABELS,
    ORDER_PAYMENT_FILTER_OPTIONS,
    ORDER_SOURCE_FILTER_OPTIONS,
    ORDER_STATUS_LABELS,
    create_manual_order,
    get_allowed_order_transitions,
    get_order_detail_context,
    get_order_receipt_context,
    transition_order_status,
)
from app.services.pagination import build_page_window, normalize_direction, normalize_page
from app.services.subscription_service import (
    BillingConfigurationError,
    DUITNOW_MANUAL_PROVIDER,
    billing_provider_enabled,
    change_plan,
    current_billing_provider,
    create_checkout_session,
    create_customer_portal_session,
    get_billing_provider_label,
    get_or_create_subscription,
    get_duitnow_payment_context,
    handle_webhook,
    latest_pending_verification,
    list_billing_events_page,
    list_plans,
    prepare_duitnow_payment_request,
    serialize_payment_submission,
    submit_duitnow_payment_submission,
    sync_subscription_from_checkout_session,
)
from app.services.catalog_service import (
    create_category,
    delete_category,
    get_category,
    list_category_names,
    list_category_records_page,
)
from app.services.floor_service import (
    TABLE_STATUS_OPTIONS,
    build_qr_code_image,
    create_tables,
    get_table,
    get_table_by_number,
    list_tables,
    update_table_status,
)
from app.validation import (
    validate_billing_payment_submission_input,
    validate_inventory_item_input,
    validate_member_role_input,
    validate_menu_category_input,
    validate_menu_item_input,
    validate_order_status_input,
    validate_pos_order_input,
    validate_table_batch_input,
    validate_table_status_input,
    validate_team_invitation_input,
)

admin = Blueprint("admin", __name__)

MENU_QUERY_PARAMS = ("page", "q", "category", "sort", "dir")
CATEGORY_QUERY_PARAMS = ("page", "q", "sort", "dir")
INVENTORY_QUERY_PARAMS = ("page", "q", "stock", "sort", "dir")
ORDER_QUERY_PARAMS = ("page", "q", "created", "status", "payment", "source", "sort", "dir")
TABLE_QUERY_PARAMS = ("status",)
TEAM_QUERY_PARAMS = (
    "member_page",
    "member_q",
    "member_role",
    "member_sort",
    "member_dir",
    "invite_page",
    "invite_q",
    "invite_status",
    "invite_sort",
    "invite_dir",
)


@admin.route("/dashboard/<int:restaurant_id>")
@login_required
def dashboard(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=OVERVIEW_ROLES)
    dashboard_order_links = {
        "total_orders": url_for("admin.order_manager", restaurant_id=restaurant_id),
        "paid_orders": url_for("admin.order_manager", restaurant_id=restaurant_id, payment="Paid"),
        "unpaid_orders": url_for("admin.order_manager", restaurant_id=restaurant_id, payment="Unpaid"),
        "active_orders": url_for("admin.order_manager", restaurant_id=restaurant_id, status="active"),
    }
    dashboard_today_links = {
        "today_orders": url_for("admin.order_manager", restaurant_id=restaurant_id, created="today"),
        "today_paid_orders": url_for(
            "admin.order_manager",
            restaurant_id=restaurant_id,
            created="today",
            payment="Paid",
        ),
        "today_revenue": url_for(
            "admin.order_manager",
            restaurant_id=restaurant_id,
            created="today",
            payment="Paid",
        ),
    }
    dashboard_inventory_links = {
        "low_stock": url_for("admin.inventory_manager", restaurant_id=restaurant_id, stock="low"),
        "out_of_stock": url_for("admin.inventory_manager", restaurant_id=restaurant_id, stock="out"),
    }
    dashboard_table_links = {
        "available_tables": url_for("admin.table_manager", restaurant_id=restaurant_id, status="available"),
        "occupied_tables": url_for("admin.table_manager", restaurant_id=restaurant_id, status="occupied"),
        "needs_cleaning_tables": url_for("admin.table_manager", restaurant_id=restaurant_id, status="needs_cleaning"),
    }
    dashboard_action_links = {
        "kitchen": url_for("admin.kitchen_workspace", restaurant_id=restaurant_id),
        "orders_active": dashboard_order_links["active_orders"],
        "orders_unpaid": dashboard_order_links["unpaid_orders"],
        "inventory_out": dashboard_inventory_links["out_of_stock"],
        "inventory_low": dashboard_inventory_links["low_stock"],
        "tables_cleaning": dashboard_table_links["needs_cleaning_tables"],
    }
    snapshot = dict(get_dashboard_snapshot(restaurant))
    service_status = dict(snapshot.pop("service_status", {}))
    service_status["href"] = dashboard_action_links.get(service_status.get("action_key"))
    raw_attention = snapshot.pop("needs_attention", [])
    needs_attention = []
    for item in raw_attention:
        attention_item = dict(item)
        attention_item["href"] = dashboard_action_links.get(item.get("link_key"))
        needs_attention.append(attention_item)

    return render_template(
        "dashboard.html",
        restaurant_id=restaurant_id,
        **snapshot,
        service_status=service_status,
        needs_attention=needs_attention,
        dashboard_inventory_links=dashboard_inventory_links,
        dashboard_order_links=dashboard_order_links,
        dashboard_today_links=dashboard_today_links,
        dashboard_table_links=dashboard_table_links,
        dashboard_action_links=dashboard_action_links,
        menu_link=url_for("menu.restaurant_menu", slug=restaurant.slug, table=1),
    )


@admin.route("/admin/operations/<int:restaurant_id>")
@login_required
def operations_workspace(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=OPERATIONS_ROLES)
    snapshot = get_operations_snapshot(restaurant)
    return render_template("operations.html", restaurant_id=restaurant_id, **snapshot)


@admin.route("/admin/menu/<int:restaurant_id>")
@login_required
def menu_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    page = normalize_page(request.args.get("page"), default=1)
    search = _request_text("q")
    category = _request_text("category").lower()
    sort = _request_choice("sort", {"category", "name", "price"}, default="category")
    direction = normalize_direction(request.args.get("dir"), default="asc")
    result = list_menu_items_page(
        restaurant_id,
        page=page,
        per_page=8,
        search=search,
        category=category,
        sort=sort,
        direction=direction,
    )
    category_names = list_category_names(restaurant_id)
    category_options = [{"value": "", "label": "All categories"}] + [
        {"value": item, "label": item.title()} for item in category_names
    ]
    if category and category not in {option["value"] for option in category_options}:
        category_options.append({"value": category, "label": category.title()})
    menu_state = _build_list_state(
        endpoint="admin.menu_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="menu",
        page_param="page",
        pagination=result["pagination"],
        search_name="q",
        search_value=search,
        search_placeholder="Search dishes, categories, or descriptions",
        sort_name="sort",
        sort_value=sort,
        sort_options=[
            {"value": "category", "label": "Category"},
            {"value": "name", "label": "Name"},
            {"value": "price", "label": "Price"},
        ],
        direction_name="dir",
        direction_value=direction,
        filters=[
            {
                "name": "category",
                "label": "Category",
                "value": category,
                "options": category_options,
            }
        ],
    )
    return render_template(
        "admin_menu.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        foods=result["items"],
        menu_state=menu_state,
        category_names=category_names,
        inventory_items=list_inventory_items(restaurant_id),
    )


@admin.route("/admin/menu/<int:restaurant_id>/add", methods=["POST"])
@login_required
def add_food(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    try:
        payload = validate_menu_item_input(request.form)
        create_menu_item(
            restaurant_id,
            name=payload.name,
            price=payload.price,
            description=payload.description,
            category=payload.category,
            inventory_item_id=payload.inventory_item_id,
            inventory_quantity=payload.inventory_quantity,
        )
        flash(f"{payload.name} is now live on the menu.", "success")
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    return redirect(url_for("admin.menu_manager", restaurant_id=restaurant_id, **_posted_query_params(*MENU_QUERY_PARAMS)))


@admin.route("/admin/menu/<int:restaurant_id>/delete/<int:food_id>", methods=["POST"])
@login_required
def delete_food(restaurant_id, food_id):
    _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    try:
        target = get_menu_item(restaurant_id, food_id)
        target_name = target.name
        delete_menu_item(target)
        flash(f"{target_name} was removed from the menu.", "success")
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    return redirect(url_for("admin.menu_manager", restaurant_id=restaurant_id, **_posted_query_params(*MENU_QUERY_PARAMS)))


@admin.route("/admin/categories/<int:restaurant_id>")
@login_required
def category_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    page = normalize_page(request.args.get("page"), default=1)
    search = _request_text("q")
    sort = _request_choice("sort", {"name", "items", "created_at"}, default="name")
    direction = normalize_direction(request.args.get("dir"), default="asc")
    result = list_category_records_page(
        restaurant_id,
        page=page,
        per_page=10,
        search=search,
        sort=sort,
        direction=direction,
    )
    category_state = _build_list_state(
        endpoint="admin.category_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="categories",
        page_param="page",
        pagination=result["pagination"],
        search_name="q",
        search_value=search,
        search_placeholder="Search category names",
        sort_name="sort",
        sort_value=sort,
        sort_options=[
            {"value": "name", "label": "Name"},
            {"value": "items", "label": "Menu items"},
            {"value": "created_at", "label": "Created"},
        ],
        direction_name="dir",
        direction_value=direction,
    )
    return render_template(
        "admin_categories.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        categories=result["items"],
        category_state=category_state,
    )


@admin.route("/admin/categories/<int:restaurant_id>/add", methods=["POST"])
@login_required
def add_category(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    try:
        payload = validate_menu_category_input(request.form)
        category = create_category(restaurant_id, payload.name)
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"{category.name.title()} is now available in Menu Studio.", "success")
    return redirect(
        url_for(
            "admin.category_manager",
            restaurant_id=restaurant_id,
            **_posted_query_params(*CATEGORY_QUERY_PARAMS),
        )
    )


@admin.route("/admin/categories/<int:restaurant_id>/delete/<int:category_id>", methods=["POST"])
@login_required
def remove_category(restaurant_id, category_id):
    _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    try:
        category = get_category(restaurant_id, category_id)
        delete_category(category)
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"{category.name.title()} was removed.", "success")
    return redirect(
        url_for(
            "admin.category_manager",
            restaurant_id=restaurant_id,
            **_posted_query_params(*CATEGORY_QUERY_PARAMS),
        )
    )


@admin.route("/admin/inventory/<int:restaurant_id>")
@login_required
def inventory_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    page = normalize_page(request.args.get("page"), default=1)
    search = _request_text("q")
    stock = _request_choice("stock", {"low", "out"}, default="")
    sort = _request_choice("sort", {"name", "stock", "cost", "created_at"}, default="name")
    direction = normalize_direction(request.args.get("dir"), default="asc")
    result = list_inventory_items_page(
        restaurant_id,
        page=page,
        per_page=10,
        search=search,
        stock=stock,
        sort=sort,
        direction=direction,
    )
    inventory_state = _build_list_state(
        endpoint="admin.inventory_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="inventory",
        page_param="page",
        pagination=result["pagination"],
        search_name="q",
        search_value=search,
        search_placeholder="Search ingredient, unit, stock, or cost",
        sort_name="sort",
        sort_value=sort,
        sort_options=[
            {"value": "name", "label": "Name"},
            {"value": "stock", "label": "Stock"},
            {"value": "cost", "label": "Unit Cost"},
            {"value": "created_at", "label": "Created"},
        ],
        direction_name="dir",
        direction_value=direction,
        filters=[
            {
                "name": "stock",
                "label": "Stock",
                "value": stock,
                "options": [
                    {"value": "", "label": "All stock levels"},
                    {"value": "low", "label": "Low stock"},
                    {"value": "out", "label": "Out of stock"},
                ],
            }
        ],
    )
    return render_template(
        "admin_inventory.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        items=result["items"],
        inventory_state=inventory_state,
        stock_filter=stock,
        low_stock_threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        total_inventory_items=result["overall_total"],
    )


@admin.route("/admin/inventory/<int:restaurant_id>/add", methods=["POST"])
@login_required
def add_inventory(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=MENU_ROLES)
    try:
        payload = validate_inventory_item_input(request.form)
        item = create_inventory_item(
            restaurant_id,
            name=payload.name,
            stock=payload.stock,
            unit=payload.unit,
            cost=payload.cost,
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"{item.name} was added to inventory.", "success")
    return redirect(
        url_for(
            "admin.inventory_manager",
            restaurant_id=restaurant_id,
            **_posted_query_params(*INVENTORY_QUERY_PARAMS),
        )
    )


@admin.route("/admin/orders/<int:restaurant_id>")
@login_required
def order_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=ORDER_ROLES)
    page = normalize_page(request.args.get("page"), default=1)
    search = _request_text("q")
    created = _request_choice("created", {"today"}, default="")
    status = _request_text("status").lower()
    payment = _request_choice("payment", set(ORDER_PAYMENT_FILTER_OPTIONS), default="")
    source = _request_choice("source", set(ORDER_SOURCE_FILTER_OPTIONS), default="")
    sort = _request_choice("sort", {"created_at", "id", "table", "status"}, default="created_at")
    direction = normalize_direction(request.args.get("dir"), default="desc")
    result = list_order_rows_page(
        restaurant_id,
        page=page,
        per_page=8,
        search=search,
        created=created,
        status=status,
        payment=payment,
        source=source,
        sort=sort,
        direction=direction,
        actor_role=current_user.role,
    )
    order_state = _build_list_state(
        endpoint="admin.order_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="orders",
        page_param="page",
        pagination=result["pagination"],
        search_name="q",
        search_value=search,
        search_placeholder="Search order, table, item, or date",
        sort_name="sort",
        sort_value=sort,
        sort_options=[
            {"value": "created_at", "label": "Created"},
            {"value": "id", "label": "Order ID"},
            {"value": "table", "label": "Table"},
            {"value": "status", "label": "Status"},
        ],
        direction_name="dir",
        direction_value=direction,
        filters=[
            {
                "name": "created",
                "label": "Created",
                "value": created,
                "options": [
                    {"value": "", "label": "All time"},
                    {"value": "today", "label": "Today"},
                ],
            },
            {
                "name": "status",
                "label": "Status",
                "value": status,
                "options": [
                    {"value": "", "label": "All statuses"},
                    {"value": "active", "label": "Active"},
                    {"value": Order.STATUS_SUBMITTED, "label": "Submitted"},
                    {"value": Order.STATUS_PREPARING, "label": "Preparing"},
                    {"value": Order.STATUS_READY, "label": "Ready"},
                    {"value": Order.STATUS_SERVED, "label": "Served"},
                    {"value": Order.STATUS_PAID, "label": "Paid"},
                    {"value": Order.STATUS_CANCELLED, "label": "Cancelled"},
                ],
            },
            {
                "name": "payment",
                "label": "Payment",
                "value": payment,
                "options": [{"value": "", "label": "All payments"}]
                + [{"value": label, "label": label} for label in ORDER_PAYMENT_FILTER_OPTIONS],
            },
            {
                "name": "source",
                "label": "Source",
                "value": source,
                "options": [{"value": "", "label": "All sources"}]
                + [{"value": label, "label": label} for label in ORDER_SOURCE_FILTER_OPTIONS],
            },
        ],
    )
    return render_template(
        "admin_orders.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        rows=result["rows"],
        total_order_count=result["overall_total"],
        order_action_labels=ORDER_ACTION_LABELS,
        total_sales=result["total_sales"],
        order_state=order_state,
        submitted_count=result["submitted_count"],
        preparing_count=result["preparing_count"],
        ready_count=result["ready_count"],
        served_count=result["served_count"],
        paid_count=result["paid_count"],
        cancelled_count=result["cancelled_count"],
        active_count=result["active_count"],
        active_tables=result["active_tables"],
    )


@admin.route("/admin/pos/<int:restaurant_id>")
@login_required
def pos_workspace(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=POS_ROLES)
    snapshot = get_pos_snapshot(restaurant)
    return render_template("pos.html", restaurant_id=restaurant_id, **snapshot)


@admin.route("/admin/pos/<int:restaurant_id>/create-order", methods=["POST"])
@login_required
def create_pos_order(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=POS_ROLES)
    try:
        payload = validate_pos_order_input(request.form)
        order = create_manual_order(
            restaurant_id,
            payload.table_number,
            payload.line_items,
            actor_user_id=current_user.id,
            note=payload.note,
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"Manual ticket #{order.id} created for table {order.table_number}.", "success")

    return redirect(url_for("admin.pos_workspace", restaurant_id=restaurant_id))


@admin.route("/admin/orders/<int:restaurant_id>/<int:order_id>")
@login_required
def order_detail(restaurant_id, order_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=ORDER_ROLES)
    detail = get_order_detail_context(
        restaurant_id,
        order_id,
        actor_role=current_user.role,
    )
    detail.pop("restaurant", None)
    return render_template(
        "order_detail.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        **detail,
    )


@admin.route("/admin/orders/<int:restaurant_id>/<int:order_id>/receipt")
@login_required
def order_receipt(restaurant_id, order_id):
    _authorize_restaurant(restaurant_id, allowed_roles=ORDER_ROLES)
    receipt = get_order_receipt_context(restaurant_id, order_id)
    return render_template(
        "receipt.html",
        **receipt,
    )


@admin.route("/admin/tables/<int:restaurant_id>")
@login_required
def table_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=TABLE_ROLES)
    status = _request_choice("status", set(TABLE_STATUS_OPTIONS), default="")
    all_tables = list_tables(restaurant_id)
    filtered_tables = list_tables(restaurant_id, status=status) if status else all_tables
    return render_template(
        "tables.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        tables=filtered_tables,
        table_statuses=TABLE_STATUS_OPTIONS,
        table_status_filter=status,
        total_tables_count=len(all_tables),
    )


@admin.route("/admin/tables/<int:restaurant_id>/add", methods=["POST"])
@login_required
def add_tables(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=TABLE_ROLES)
    try:
        payload = validate_table_batch_input(request.form)
        created = create_tables(restaurant_id, count=payload.count, starting_at=payload.starting_at)
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        if len(created) == 1:
            flash(f"Table {created[0].table_number} is available for service.", "success")
        else:
            flash(f"Added {len(created)} tables starting from {created[0].table_number}.", "success")
    return redirect(url_for("admin.table_manager", restaurant_id=restaurant_id, **_posted_query_params(*TABLE_QUERY_PARAMS)))


@admin.route("/admin/tables/<int:restaurant_id>/status/<int:table_id>", methods=["POST"])
@login_required
def update_table(restaurant_id, table_id):
    _authorize_restaurant(restaurant_id, allowed_roles=TABLE_ROLES)
    return_order_id = request.form.get("return_order_id", type=int)
    try:
        payload = validate_table_status_input(request.form, allowed_statuses=TABLE_STATUS_OPTIONS)
        table = get_table(restaurant_id, table_id)
        update_table_status(table, payload.status, actor_user_id=current_user.id)
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"Table {table.table_number} is now marked {table.status}.", "success")
    if return_order_id:
        return redirect(url_for("admin.order_detail", restaurant_id=restaurant_id, order_id=return_order_id))
    return redirect(url_for("admin.table_manager", restaurant_id=restaurant_id, **_posted_query_params(*TABLE_QUERY_PARAMS)))


@admin.route("/admin/tables/<int:restaurant_id>/qr")
@login_required
def table_qr_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=TABLE_ROLES)
    tables = list_tables(restaurant_id)
    qr_rows = [
        {
            "table": table,
            "guest_url": url_for("menu.restaurant_menu", slug=restaurant.slug, table=table.table_number, _external=True),
            "image_url": url_for(
                "admin.generate_table_qr",
                restaurant_id=restaurant_id,
                table_number=table.table_number,
            ),
        }
        for table in tables
    ]
    return render_template(
        "qr_tables.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        qr_rows=qr_rows,
    )


@admin.route("/admin/tables/<int:restaurant_id>/qr/<int:table_number>.png")
@login_required
def generate_table_qr(restaurant_id, table_number):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=TABLE_ROLES)
    table = get_table_by_number(restaurant_id, table_number)
    guest_url = url_for("menu.restaurant_menu", slug=restaurant.slug, table=table.table_number, _external=True)
    return send_file(
        build_qr_code_image(guest_url),
        mimetype="image/png",
        download_name=f"{restaurant.slug}-table-{table.table_number}.png",
    )


@admin.route("/admin/kitchen/<int:restaurant_id>")
@login_required
def kitchen_workspace(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=KITCHEN_ROLES)
    return render_template(
        "kitchen.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        orders_api_url=url_for("admin.kitchen_orders_api", restaurant_id=restaurant_id),
        update_status_base=url_for("admin.kitchen_update_status", restaurant_id=restaurant_id, order_id=0, status=Order.STATUS_SUBMITTED),
        orders_url=url_for("admin.order_manager", restaurant_id=restaurant_id),
    )


@admin.route("/admin/kitchen/<int:restaurant_id>/orders")
@login_required
def kitchen_orders_api(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=KITCHEN_ROLES)
    orders = [
        order
        for order in serialize_kitchen_orders(restaurant_id)
        if order["status"] in KITCHEN_VISIBLE_STATUSES
    ]
    for order in orders:
        order["allowed_transitions"] = list(
            get_allowed_order_transitions(order["status"], actor_role=current_user.role)
        )
    return jsonify({"orders": orders})


@admin.route("/admin/kitchen/<int:restaurant_id>/orders/<int:order_id>/<status>", methods=["POST"])
@login_required
def kitchen_update_status(restaurant_id, order_id, status):
    _authorize_restaurant(restaurant_id, allowed_roles=KITCHEN_ROLES)
    normalized_status = (status or "").strip().lower()
    try:
        order = transition_order_status(
            restaurant_id,
            order_id,
            normalized_status,
            actor_role=current_user.role,
            actor_user_id=current_user.id,
        )
    except AppError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"ok": True, "order_id": order.id, "status": order.status})


@admin.route("/admin/team/<int:restaurant_id>")
@login_required
def team_manager(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=TEAM_ROLES)
    member_page = normalize_page(request.args.get("member_page"), default=1)
    member_search = _request_text("member_q")
    member_role = _request_text("member_role").lower()
    member_sort = _request_choice("member_sort", {"username", "email", "role"}, default="role")
    member_dir = normalize_direction(request.args.get("member_dir"), default="asc")

    invite_page = normalize_page(request.args.get("invite_page"), default=1)
    invite_search = _request_text("invite_q")
    invite_status = _request_text("invite_status").lower()
    invite_sort = _request_choice("invite_sort", {"created_at", "email", "role", "status"}, default="created_at")
    invite_dir = normalize_direction(request.args.get("invite_dir"), default="desc")

    members_result = list_team_members_page(
        restaurant_id,
        page=member_page,
        per_page=8,
        search=member_search,
        role=member_role,
        sort=member_sort,
        direction=member_dir,
    )
    invitations_result = list_team_invitations_page(
        restaurant_id,
        page=invite_page,
        per_page=8,
        search=invite_search,
        status=invite_status,
        sort=invite_sort,
        direction=invite_dir,
    )

    member_preserved = _clean_query_params(
        {
            "invite_page": invitations_result["pagination"]["page"],
            "invite_q": invite_search,
            "invite_status": invite_status,
            "invite_sort": invite_sort,
            "invite_dir": invite_dir,
        }
    )
    invite_preserved = _clean_query_params(
        {
            "member_page": members_result["pagination"]["page"],
            "member_q": member_search,
            "member_role": member_role,
            "member_sort": member_sort,
            "member_dir": member_dir,
        }
    )
    members_state = _build_list_state(
        endpoint="admin.team_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="members",
        page_param="member_page",
        pagination=members_result["pagination"],
        search_name="member_q",
        search_value=member_search,
        search_placeholder="Search username, email, or role",
        sort_name="member_sort",
        sort_value=member_sort,
        sort_options=[
            {"value": "role", "label": "Role"},
            {"value": "username", "label": "Username"},
            {"value": "email", "label": "Email"},
        ],
        direction_name="member_dir",
        direction_value=member_dir,
        filters=[
            {
                "name": "member_role",
                "label": "Role",
                "value": member_role,
                "options": [{"value": "", "label": "All roles"}]
                + [{"value": key, "label": label} for key, label in ROLE_LABELS.items()],
            }
        ],
        preserved_params=member_preserved,
    )
    invitations_state = _build_list_state(
        endpoint="admin.team_manager",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="invitations",
        page_param="invite_page",
        pagination=invitations_result["pagination"],
        search_name="invite_q",
        search_value=invite_search,
        search_placeholder="Search email, role, or status",
        sort_name="invite_sort",
        sort_value=invite_sort,
        sort_options=[
            {"value": "created_at", "label": "Created"},
            {"value": "email", "label": "Email"},
            {"value": "role", "label": "Role"},
            {"value": "status", "label": "Status"},
        ],
        direction_name="invite_dir",
        direction_value=invite_dir,
        filters=[
            {
                "name": "invite_status",
                "label": "Status",
                "value": invite_status,
                "options": [
                    {"value": "", "label": "All statuses"},
                    {"value": "pending", "label": "Pending"},
                    {"value": "accepted", "label": "Accepted"},
                    {"value": "revoked", "label": "Revoked"},
                    {"value": "expired", "label": "Expired"},
                ],
            }
        ],
        preserved_params=invite_preserved,
    )
    team_return_fields = members_state["return_fields"] + invitations_state["return_fields"]
    return render_template(
        "staff.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        role_labels=ROLE_LABELS,
        members=members_result["items"],
        invitations=invitations_result["items"],
        members_state=members_state,
        invitations_state=invitations_state,
        team_return_fields=team_return_fields,
    )


@admin.route("/admin/team/<int:restaurant_id>/invite", methods=["POST"])
@login_required
def invite_team_member(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=TEAM_ROLES)
    try:
        payload = validate_team_invitation_input(request.form, allowed_roles=INVITABLE_ROLES)
        invitation = create_team_invitation(
            restaurant_id,
            email=payload.email,
            role=payload.role,
            invited_by_user_id=current_user.id,
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"Invitation created for {invitation.email}. Share the acceptance link with your team member.", "success")

    return redirect(url_for("admin.team_manager", restaurant_id=restaurant_id, **_posted_query_params(*TEAM_QUERY_PARAMS)))


@admin.route("/admin/team/<int:restaurant_id>/members/<int:user_id>/role", methods=["POST"])
@login_required
def change_member_role(restaurant_id, user_id):
    _authorize_restaurant(restaurant_id, allowed_roles=TEAM_ROLES)
    try:
        payload = validate_member_role_input(request.form, allowed_roles=ROLE_LABELS.keys())
        member = update_team_member_role(
            restaurant_id,
            user_id=user_id,
            new_role=payload.role,
            actor_id=current_user.id,
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    else:
        flash(f"{member.username} is now assigned as {ROLE_LABELS.get(member.role, member.role.title())}.", "success")
    return redirect(url_for("admin.team_manager", restaurant_id=restaurant_id, **_posted_query_params(*TEAM_QUERY_PARAMS)))


@admin.route("/admin/team/<int:restaurant_id>/invites/<int:invite_id>/revoke", methods=["POST"])
@login_required
def revoke_team_invite(restaurant_id, invite_id):
    _authorize_restaurant(restaurant_id, allowed_roles=TEAM_ROLES)
    try:
        invitation = get_team_invitation(restaurant_id, invite_id)
        revoke_team_invitation(invitation)
        flash(f"Invitation for {invitation.email} was revoked.", "success")
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    return redirect(url_for("admin.team_manager", restaurant_id=restaurant_id, **_posted_query_params(*TEAM_QUERY_PARAMS)))


@admin.route("/billing/<int:restaurant_id>")
@login_required
def billing(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = get_or_create_subscription(restaurant_id)
    billing_provider = (request.args.get("provider") or current_billing_provider(subscription)).strip().lower()
    if billing_provider not in {"manual", "stripe", DUITNOW_MANUAL_PROVIDER}:
        billing_provider = current_billing_provider(subscription)

    duitnow_plan = _request_text("duitnow_plan").lower()
    duitnow_payment = None
    if billing_provider == DUITNOW_MANUAL_PROVIDER and duitnow_plan:
        try:
            duitnow_payment = get_duitnow_payment_context(restaurant, duitnow_plan)
        except (BillingConfigurationError, ValidationError):
            duitnow_payment = None
    recent_payment_submission = serialize_payment_submission(latest_pending_verification(restaurant_id))

    return render_template(
        "billing.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        subscription=subscription,
        plans=list_plans(),
        billing_provider=billing_provider,
        billing_provider_label=get_billing_provider_label(billing_provider),
        subscription_provider_label=get_billing_provider_label(subscription.billing_provider),
        duitnow_manual_provider=DUITNOW_MANUAL_PROVIDER,
        duitnow_payment=duitnow_payment,
        recent_payment_submission=recent_payment_submission,
        stripe_ready=bool(current_app.config.get("STRIPE_SECRET_KEY")),
    )


@admin.route("/billing/<int:restaurant_id>/status")
@login_required
def billing_status(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = get_or_create_subscription(restaurant_id)
    from app.services.subscription_service import latest_billing_issue, list_billing_events  # local import to avoid long import line

    events = list_billing_events(restaurant_id, limit=8)
    return render_template(
        "billing_status.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        subscription=subscription,
        latest_issue=latest_billing_issue(restaurant_id),
        events=events,
        billing_provider=request.args.get("provider") or ("stripe" if billing_provider_enabled("stripe") else "manual"),
        stripe_ready=bool(current_app.config.get("STRIPE_SECRET_KEY")),
    )


@admin.route("/billing/<int:restaurant_id>/history")
@login_required
def billing_history(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    page = normalize_page(request.args.get("page"), default=1)
    search = _request_text("q")
    source = _request_text("source").lower()
    status = _request_text("status").lower()
    sort = _request_choice("sort", {"occurred_at", "event_type", "source", "status"}, default="occurred_at")
    direction = normalize_direction(request.args.get("dir"), default="desc")
    result = list_billing_events_page(
        restaurant_id,
        page=page,
        per_page=10,
        search=search,
        source=source,
        status=status,
        sort=sort,
        direction=direction,
    )
    history_state = _build_list_state(
        endpoint="admin.billing_history",
        route_values={"restaurant_id": restaurant_id},
        id_prefix="billing-history",
        page_param="page",
        pagination=result["pagination"],
        search_name="q",
        search_value=search,
        search_placeholder="Search event, summary, or reference",
        sort_name="sort",
        sort_value=sort,
        sort_options=[
            {"value": "occurred_at", "label": "Occurred"},
            {"value": "event_type", "label": "Event"},
            {"value": "source", "label": "Source"},
            {"value": "status", "label": "Status"},
        ],
        direction_name="dir",
        direction_value=direction,
        filters=[
            {
                "name": "source",
                "label": "Source",
                "value": source,
                "options": [
                    {"value": "", "label": "All sources"},
                    {"value": "manual", "label": "Manual"},
                    {"value": "stripe", "label": "Stripe"},
                    {"value": DUITNOW_MANUAL_PROVIDER, "label": "DuitNow Manual"},
                    {"value": "system", "label": "System"},
                ],
            },
            {
                "name": "status",
                "label": "Status",
                "value": status,
                "options": [
                    {"value": "", "label": "All statuses"},
                    {"value": "active", "label": "Active"},
                    {"value": "trialing", "label": "Trialing"},
                    {"value": "pending_verification", "label": "Pending Verification"},
                    {"value": "past_due", "label": "Past Due"},
                    {"value": "canceled", "label": "Canceled"},
                ],
            },
        ],
    )

    return render_template(
        "billing_history.html",
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        subscription=get_or_create_subscription(restaurant_id),
        events=result["items"],
        history_state=history_state,
    )


@admin.route("/billing/<int:restaurant_id>/subscribe/<plan_key>", methods=["POST"])
@login_required
def subscribe(restaurant_id, plan_key):
    _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = change_plan(restaurant_id, plan_key)
    flash(f"Plan updated to {list_plans()[subscription.plan]['name']}.", "success")
    return redirect(url_for("admin.billing", restaurant_id=restaurant_id))


@admin.route("/billing/<int:restaurant_id>/checkout/<plan_key>", methods=["POST"])
@login_required
def billing_checkout(restaurant_id, plan_key):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = get_or_create_subscription(restaurant_id)

    if plan_key == "starter":
        change_plan(restaurant_id, plan_key)
        flash("Switched back to Starter plan.", "success")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id))

    try:
        session = create_checkout_session(restaurant, subscription, plan_key)
    except BillingConfigurationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id))

    return redirect(session.url, code=303)


@admin.route("/billing/<int:restaurant_id>/duitnow/<plan_key>", methods=["POST"])
@login_required
def billing_duitnow(restaurant_id, plan_key):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)

    if plan_key == "starter":
        change_plan(restaurant_id, plan_key)
        flash("Switched back to Starter plan.", "success")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id, provider=DUITNOW_MANUAL_PROVIDER))

    try:
        prepare_duitnow_payment_request(restaurant, plan_key)
    except BillingConfigurationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id, provider=DUITNOW_MANUAL_PROVIDER))

    flash(
        "DuitNow payment details are ready. Complete the transfer and confirm the payment manually before the plan changes.",
        "success",
    )
    return redirect(
        url_for(
            "admin.billing",
            restaurant_id=restaurant_id,
            provider=DUITNOW_MANUAL_PROVIDER,
            duitnow_plan=plan_key,
        )
    )


@admin.route("/billing/<int:restaurant_id>/duitnow/<plan_key>/submit", methods=["POST"])
@login_required
def billing_duitnow_submit(restaurant_id, plan_key):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)

    try:
        submission = validate_billing_payment_submission_input(request.form)
        submit_duitnow_payment_submission(
            restaurant,
            plan_key,
            submission.payment_reference,
            screenshot_file=request.files.get("payment_screenshot"),
        )
    except (BillingConfigurationError, ValidationError) as exc:
        flash(str(exc), "error")
    else:
        flash(
            "Payment submitted. Your subscription stays unchanged until the platform owner verifies the transfer.",
            "success",
        )

    return redirect(
        url_for(
            "admin.billing",
            restaurant_id=restaurant_id,
            provider=DUITNOW_MANUAL_PROVIDER,
            duitnow_plan=plan_key,
        )
    )


@admin.route("/billing/<int:restaurant_id>/success")
@login_required
def billing_success(restaurant_id):
    _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Missing Stripe session id.", "error")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id))

    try:
        sync_subscription_from_checkout_session(restaurant_id, session_id)
        flash("Subscription updated successfully.", "success")
    except BillingConfigurationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.billing", restaurant_id=restaurant_id))


@admin.route("/billing/<int:restaurant_id>/portal", methods=["POST"])
@login_required
def billing_portal(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = get_or_create_subscription(restaurant_id)

    try:
        session = create_customer_portal_session(restaurant, subscription)
    except BillingConfigurationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.billing", restaurant_id=restaurant_id))

    return redirect(session.url, code=303)


@admin.route("/billing/<int:restaurant_id>/cancel", methods=["POST"])
@login_required
def billing_cancel(restaurant_id):
    restaurant = _authorize_restaurant(restaurant_id, allowed_roles=BILLING_ROLES)
    subscription = get_or_create_subscription(restaurant_id)

    from app.services.subscription_service import cancel_subscription  # local import to avoid long import line

    try:
        cancel_subscription(restaurant, subscription)
    except BillingConfigurationError as exc:
        flash(str(exc), "error")
    else:
        flash("Subscription cancellation has been scheduled.", "success")

    return redirect(url_for("admin.billing_status", restaurant_id=restaurant_id))


@admin.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    signature = request.headers.get("Stripe-Signature")
    if not signature:
        return {"error": "Missing Stripe-Signature header"}, 400

    try:
        event = handle_webhook(request.data, signature)
    except BillingConfigurationError as exc:
        return {"error": str(exc)}, 400
    except Exception:
        return {"error": "Webhook verification failed"}, 400

    return {"received": True, "type": event.get("type")}, 200


@admin.route("/admin/orders/<int:restaurant_id>/update/<int:order_id>", methods=["POST"])
@login_required
def update_order(restaurant_id, order_id):
    _authorize_restaurant(restaurant_id, allowed_roles=ORDER_ROLES)
    try:
        payload = validate_order_status_input(request.form, allowed_statuses=Order.STATUS_FLOW)
        order = transition_order_status(
            restaurant_id,
            order_id,
            payload.status,
            actor_role=current_user.role,
            actor_user_id=current_user.id,
        )
        flash(
            f"Order #{order.id} moved to {ORDER_STATUS_LABELS.get(order.status, order.status)}.",
            "success",
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    return redirect(url_for("admin.order_manager", restaurant_id=restaurant_id, **_posted_query_params(*ORDER_QUERY_PARAMS)))


@admin.route("/admin/orders/<int:restaurant_id>/<int:order_id>/transition", methods=["POST"])
@login_required
def update_order_from_detail(restaurant_id, order_id):
    _authorize_restaurant(restaurant_id, allowed_roles=ORDER_ROLES)
    try:
        payload = validate_order_status_input(request.form, allowed_statuses=Order.STATUS_FLOW)
        order = transition_order_status(
            restaurant_id,
            order_id,
            payload.status,
            actor_role=current_user.role,
            actor_user_id=current_user.id,
        )
        flash(
            f"Order #{order.id} moved to {ORDER_STATUS_LABELS.get(order.status, order.status)}.",
            "success",
        )
    except AppError as exc:
        flash(exc.message, exc.flash_category)
    return redirect(url_for("admin.order_detail", restaurant_id=restaurant_id, order_id=order_id))


def _authorize_restaurant(restaurant_id, allowed_roles=None):
    return authorize_restaurant_access(restaurant_id, allowed_roles=allowed_roles)


def _request_text(name, default=""):
    return (request.args.get(name) or default).strip()


def _request_choice(name, allowed, default):
    value = _request_text(name, default=default)
    return value if value in allowed else default


def _clean_query_params(params):
    return {key: value for key, value in (params or {}).items() if value not in (None, "", [])}


def _posted_query_params(*names):
    return _clean_query_params({name: (request.form.get(f"return_{name}") or "").strip() for name in names})


def _build_list_state(
    *,
    endpoint,
    route_values,
    id_prefix,
    page_param,
    pagination,
    search_name,
    search_value,
    search_placeholder,
    sort_name,
    sort_value,
    sort_options,
    direction_name,
    direction_value,
    filters=None,
    preserved_params=None,
):
    filters = filters or []
    preserved = _clean_query_params(preserved_params)
    current_params = _clean_query_params(
        {
            search_name: search_value,
            sort_name: sort_value,
            direction_name: direction_value,
            **{filter_config["name"]: filter_config.get("value", "") for filter_config in filters},
        }
    )
    action_url = url_for(endpoint, **route_values)
    reset_url = url_for(endpoint, **route_values, **preserved)
    pagination_ui = _build_pagination_ui(
        endpoint=endpoint,
        route_values=route_values,
        page_param=page_param,
        pagination=pagination,
        params={**preserved, **current_params},
    )
    return {
        "id_prefix": id_prefix,
        "action_url": action_url,
        "reset_url": reset_url,
        "search_name": search_name,
        "search_value": search_value,
        "search_placeholder": search_placeholder,
        "sort_name": sort_name,
        "sort_value": sort_value,
        "sort_options": sort_options,
        "direction_name": direction_name,
        "direction_value": direction_value,
        "direction_options": [
            {"value": "asc", "label": "Ascending"},
            {"value": "desc", "label": "Descending"},
        ],
        "filters": filters,
        "hidden_fields": [{"name": key, "value": value} for key, value in preserved.items()],
        "return_fields": [
            {"name": f"return_{key}", "value": value}
            for key, value in {**preserved, **current_params, page_param: pagination["page"]}.items()
        ],
        "pagination": pagination_ui,
    }


def _build_pagination_ui(*, endpoint, route_values, page_param, pagination, params):
    cleaned_params = _clean_query_params(params)
    current_page = pagination["page"]

    def page_url(page_number):
        return url_for(endpoint, **route_values, **{**cleaned_params, page_param: page_number})

    page_links = [
        {
            "number": page_number,
            "url": page_url(page_number),
            "active": page_number == current_page,
        }
        for page_number in build_page_window(current_page, pagination["pages"])
    ]
    return {
        "page": current_page,
        "pages": pagination["pages"],
        "total": pagination["total"],
        "start_index": pagination["start_index"],
        "end_index": pagination["end_index"],
        "prev_url": page_url(current_page - 1) if pagination["has_prev"] else None,
        "next_url": page_url(current_page + 1) if pagination["has_next"] else None,
        "page_links": page_links,
    }
