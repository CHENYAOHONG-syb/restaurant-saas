from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.menu import Menu
from app.models.order import Order
from app.models.order_event import OrderEvent
from app.models.order_item import OrderItem
from app.models.table import Table
from app.services.floor_service import get_dashboard_table_metrics, sync_tables_from_orders
from app.services.inventory_service import get_dashboard_inventory_metrics, sync_menu_inventory_requirement
from app.services.order_service import build_order_display_context, format_order_currency, get_allowed_order_transitions
from app.services.pagination import paginate_items, paginate_query
from app.services.tenant_service import get_menu_item_for_restaurant

ORDER_DASHBOARD_ACTIVE_STATUSES = (
    Order.STATUS_SUBMITTED,
    Order.STATUS_PREPARING,
    Order.STATUS_READY,
)
ORDER_DASHBOARD_DELAY_MINUTES = 5


def get_dashboard_snapshot(restaurant):
    foods = list_menu_items(restaurant.id)
    order_rows = list_order_rows(restaurant.id)
    recent_orders = order_rows[:5]
    order_metrics = get_dashboard_order_metrics(restaurant.id)
    today_metrics = get_dashboard_today_metrics(restaurant.id)
    yesterday_metrics = get_dashboard_yesterday_metrics(restaurant.id)
    inventory_metrics = get_dashboard_inventory_metrics(restaurant.id)
    table_metrics = get_dashboard_table_metrics(restaurant.id)
    delayed_orders = get_dashboard_delayed_order_count(restaurant.id)
    today_comparison = build_dashboard_today_comparison(today_metrics, yesterday_metrics)

    return {
        "restaurant": restaurant,
        "menu_count": len(foods),
        "total_orders": order_metrics["total_orders"],
        "total_sales": round(sum(row["total"] for row in order_rows), 2),
        "recent_orders": recent_orders,
        "activity_feed": build_dashboard_activity_feed(order_rows),
        "order_metrics": order_metrics,
        "today_metrics": today_metrics,
        "yesterday_metrics": yesterday_metrics,
        "inventory_metrics": inventory_metrics,
        "table_metrics": table_metrics,
        "today_comparison": today_comparison,
        "service_status": build_dashboard_service_status(
            order_metrics,
            inventory_metrics,
            table_metrics,
            delayed_orders,
        ),
        "today_insights": build_dashboard_today_insights(
            order_metrics,
            today_metrics,
            inventory_metrics,
            table_metrics,
            delayed_orders,
            today_comparison,
        ),
        "needs_attention": build_dashboard_needs_attention(
            order_metrics,
            inventory_metrics,
            table_metrics,
            delayed_orders,
        ),
    }


def get_dashboard_order_metrics(restaurant_id):
    status_rows = (
        db.session.query(Order.status, func.count(Order.id))
        .filter(Order.restaurant_id == restaurant_id)
        .group_by(Order.status)
        .all()
    )
    counts = {status: count for status, count in status_rows}
    total_orders = sum(counts.values())
    paid_orders = counts.get(Order.STATUS_PAID, 0)
    unpaid_orders = max(0, total_orders - paid_orders)
    active_orders = sum(counts.get(status, 0) for status in ORDER_DASHBOARD_ACTIVE_STATUSES)
    return {
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "unpaid_orders": unpaid_orders,
        "active_orders": active_orders,
    }


def get_dashboard_today_metrics(restaurant_id):
    metrics = _get_dashboard_created_day_metrics(restaurant_id, day_offset=0)
    return {
        "today_orders": metrics["orders"],
        "today_paid_orders": metrics["paid_orders"],
        "today_revenue_value": metrics["revenue_value"],
        "today_revenue_display": metrics["revenue_display"],
    }


def get_dashboard_yesterday_metrics(restaurant_id):
    return _get_dashboard_created_day_metrics(restaurant_id, day_offset=-1)


def get_dashboard_delayed_order_count(restaurant_id, *, older_than_minutes=ORDER_DASHBOARD_DELAY_MINUTES, now=None):
    current_time = now or datetime.utcnow()
    cutoff = current_time - timedelta(minutes=older_than_minutes)
    return (
        Order.query.filter(
            Order.restaurant_id == restaurant_id,
            Order.status.in_(ORDER_DASHBOARD_ACTIVE_STATUSES),
            Order.created_at.isnot(None),
            Order.created_at < cutoff,
        )
        .count()
    )


def build_dashboard_today_comparison(today_metrics, yesterday_metrics):
    return [
        _build_dashboard_comparison_item(
            "Orders",
            today_metrics["today_orders"],
            yesterday_metrics["orders"],
        ),
        _build_dashboard_comparison_item(
            "Paid orders",
            today_metrics["today_paid_orders"],
            yesterday_metrics["paid_orders"],
        ),
        _build_dashboard_comparison_item(
            "Revenue",
            today_metrics["today_revenue_value"],
            yesterday_metrics["revenue_value"],
            formatter=format_order_currency,
        ),
    ]


def build_dashboard_service_status(order_metrics, inventory_metrics, table_metrics, delayed_orders):
    facts = []
    if delayed_orders:
        facts.append(f"{delayed_orders} delayed")
    if order_metrics["unpaid_orders"]:
        facts.append(f"{order_metrics['unpaid_orders']} unpaid")
    if inventory_metrics["out_of_stock_count"]:
        facts.append(f"{inventory_metrics['out_of_stock_count']} out of stock")
    elif inventory_metrics["low_stock_count"]:
        facts.append(f"{inventory_metrics['low_stock_count']} low stock")
    if table_metrics["needs_cleaning_tables"]:
        facts.append(f"{table_metrics['needs_cleaning_tables']} need cleaning")

    if delayed_orders:
        title = "Kitchen delays need attention"
        subtitle = "Orders are sitting beyond the service target."
        tone = "danger"
        action_label = "Open kitchen"
        action_key = "kitchen"
    elif inventory_metrics["out_of_stock_count"] or inventory_metrics["low_stock_count"]:
        title = "Stock needs attention"
        subtitle = "Inventory needs a quick review before the next rush."
        tone = "warning"
        action_label = "Open inventory"
        action_key = "inventory_out"
    elif order_metrics["unpaid_orders"]:
        title = "Orders need attention now"
        subtitle = "A few orders still need payment follow-up."
        tone = "warning"
        action_label = "View orders"
        action_key = "orders_unpaid"
    elif table_metrics["needs_cleaning_tables"]:
        title = "Service needs attention"
        subtitle = "Tables need a quick reset before they return to service."
        tone = "warning"
        action_label = "Open tables"
        action_key = "tables_cleaning"
    else:
        title = "Service running smoothly"
        subtitle = "No major blockers need action right now."
        tone = "success"
        action_label = "View live orders"
        action_key = "orders_active"
        facts.append("No urgent blockers")

    return {
        "title": title,
        "subtitle": subtitle,
        "tone": tone,
        "facts": facts[:4],
        "action_label": action_label,
        "action_key": action_key,
    }


def build_dashboard_today_insights(
    order_metrics,
    today_metrics,
    inventory_metrics,
    table_metrics,
    delayed_orders,
    today_comparison,
):
    revenue_trend = today_comparison[2]
    insights = [
        {
            "title": f"{delayed_orders} delayed order(s) (>5 mins)" if delayed_orders else "Kitchen queue is on time",
        },
        {
            "title": (
                f"{inventory_metrics['out_of_stock_count']} item(s) out of stock"
                if inventory_metrics["out_of_stock_count"]
                else (
                    f"{inventory_metrics['low_stock_count']} item(s) low in stock"
                    if inventory_metrics["low_stock_count"]
                    else "Stock levels are stable"
                )
            ),
        },
        {
            "title": (
                f"{table_metrics['needs_cleaning_tables']} table(s) need cleaning"
                if table_metrics["needs_cleaning_tables"]
                else "No tables waiting on cleaning"
            ),
        },
        {
            "title": f"Revenue {revenue_trend['summary'].lower()}",
        },
    ]
    if order_metrics["unpaid_orders"]:
        insights.append(
            {
                "title": f"{order_metrics['unpaid_orders']} unpaid order(s) need follow-up",
            }
        )
    return insights[:5]


def build_dashboard_needs_attention(order_metrics, inventory_metrics, table_metrics, delayed_orders):
    items = []
    if delayed_orders:
        items.append(
            {
                "title": "Delayed kitchen tickets",
                "count": delayed_orders,
                "detail": "Orders older than five minutes in the active queue.",
                "action_label": "Open kitchen",
                "link_key": "kitchen",
                "priority_label": "Urgent",
                "priority_class": "canceled",
            }
        )
    if order_metrics["unpaid_orders"]:
        items.append(
            {
                "title": "Unpaid orders",
                "count": order_metrics["unpaid_orders"],
                "detail": "Orders that still need payment follow-up.",
                "action_label": "View orders",
                "link_key": "orders_unpaid",
                "priority_label": "Attention",
                "priority_class": "pending",
            }
        )
    if inventory_metrics["out_of_stock_count"]:
        items.append(
            {
                "title": "Out of stock items",
                "count": inventory_metrics["out_of_stock_count"],
                "detail": "Ingredients already depleted from service.",
                "action_label": "Open inventory",
                "link_key": "inventory_out",
                "priority_label": "Attention",
                "priority_class": "pending",
            }
        )
    elif inventory_metrics["low_stock_count"]:
        items.append(
            {
                "title": "Low stock items",
                "count": inventory_metrics["low_stock_count"],
                "detail": "Ingredients running low before the next rush.",
                "action_label": "Open inventory",
                "link_key": "inventory_low",
                "priority_label": "Monitor",
                "priority_class": "secondary",
            }
        )
    if table_metrics["needs_cleaning_tables"]:
        items.append(
            {
                "title": "Tables needing cleaning",
                "count": table_metrics["needs_cleaning_tables"],
                "detail": "Tables waiting to return to service.",
                "action_label": "Open tables",
                "link_key": "tables_cleaning",
                "priority_label": "Monitor",
                "priority_class": "secondary",
            }
        )
    return items


def build_dashboard_activity_feed(order_rows, *, limit=6):
    feed = []
    for row in order_rows[:limit]:
        order = row["order"]
        updated_at = row["updated_at"] or order.created_at
        feed.append(
            {
                "headline": f"Order {row['order_reference']} {row['status_label'].lower()} · Table {order.table_number}",
                "meta": row["total_display"],
                "badge_label": row["status_label"],
                "badge_class": row["status_badge_class"],
                "time_ago": _format_relative_timestamp(updated_at),
                "href": row["detail_url"],
            }
        )
    return feed


def _get_dashboard_created_day_metrics(restaurant_id, *, day_offset=0, reference=None):
    start_at, end_at = _today_created_bounds(reference=reference, day_offset=day_offset)
    today_query = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.created_at >= start_at,
        Order.created_at < end_at,
    )
    orders = today_query.count()
    paid_orders = today_query.filter(Order.status == Order.STATUS_PAID).count()
    paid_order_ids = [order_id for order_id, in today_query.with_entities(Order.id).filter(Order.status == Order.STATUS_PAID).all()]
    revenue_value = 0.0
    if paid_order_ids:
        revenue_value = (
            db.session.query(func.coalesce(func.sum(OrderItem.quantity * Menu.price), 0.0))
            .select_from(OrderItem)
            .join(Menu, Menu.id == OrderItem.food_id)
            .filter(OrderItem.order_id.in_(paid_order_ids))
            .scalar()
            or 0.0
        )

    revenue_value = round(revenue_value, 2)
    return {
        "orders": orders,
        "paid_orders": paid_orders,
        "revenue_value": revenue_value,
        "revenue_display": format_order_currency(revenue_value),
    }


def list_menu_items(restaurant_id):
    return (
        Menu.query.filter_by(restaurant_id=restaurant_id)
        .order_by(Menu.category.asc(), Menu.name.asc())
        .all()
    )


def list_menu_categories(restaurant_id):
    from app.services.catalog_service import list_category_names

    return list_category_names(restaurant_id)


def list_menu_items_page(
    restaurant_id,
    *,
    page=1,
    per_page=8,
    search=None,
    category=None,
    sort="category",
    direction="asc",
):
    base_query = Menu.query.filter_by(restaurant_id=restaurant_id)
    normalized_search = (search or "").strip()
    normalized_category = (category or "").strip().lower()
    normalized_direction = "desc" if direction == "desc" else "asc"

    if normalized_search:
        like = f"%{normalized_search}%"
        base_query = base_query.filter(
            or_(
                Menu.name.ilike(like),
                Menu.description.ilike(like),
                Menu.category.ilike(like),
            )
        )

    if normalized_category:
        base_query = base_query.filter(Menu.category == normalized_category)

    if sort == "name":
        order_clauses = [Menu.name.desc() if normalized_direction == "desc" else Menu.name.asc()]
    elif sort == "price":
        order_clauses = [Menu.price.desc() if normalized_direction == "desc" else Menu.price.asc(), Menu.name.asc()]
    else:
        order_clauses = [
            Menu.category.desc() if normalized_direction == "desc" else Menu.category.asc(),
            Menu.name.desc() if normalized_direction == "desc" else Menu.name.asc(),
        ]

    pagination = paginate_query(base_query.order_by(*order_clauses), page=page, per_page=per_page)
    pagination["items"] = pagination["items"]
    return {
        "items": pagination["items"],
        "pagination": pagination,
        "categories": list_menu_categories(restaurant_id),
    }


def get_menu_item(restaurant_id, food_id):
    return get_menu_item_for_restaurant(restaurant_id, food_id)


def create_menu_item(
    restaurant_id,
    *,
    name,
    price,
    category,
    description=None,
    inventory_item_id=None,
    inventory_quantity=None,
):
    from app.services.catalog_service import ensure_menu_category

    item = Menu(
        name=name,
        price=price,
        description=description,
        category=category,
        restaurant_id=restaurant_id,
    )
    db.session.add(item)
    db.session.flush()
    ensure_menu_category(restaurant_id, category)
    sync_menu_inventory_requirement(
        item,
        restaurant_id=restaurant_id,
        inventory_item_id=inventory_item_id,
        quantity_required=inventory_quantity,
    )
    db.session.commit()
    return item


def delete_menu_item(item):
    db.session.delete(item)
    db.session.commit()


def list_order_rows(restaurant_id, *, actor_role=None):
    sync_tables_from_orders(restaurant_id)
    orders = (
        Order.query.filter_by(restaurant_id=restaurant_id)
        .order_by(Order.id.desc())
        .all()
    )
    return _build_order_rows(orders, actor_role=actor_role)


def list_order_rows_page(
    restaurant_id,
    *,
    page=1,
    per_page=8,
    search=None,
    created=None,
    status=None,
    payment=None,
    source=None,
    sort="created_at",
    direction="desc",
    actor_role=None,
):
    sync_tables_from_orders(restaurant_id)
    overall_total = Order.query.filter_by(restaurant_id=restaurant_id).count()
    base_query = Order.query.filter_by(restaurant_id=restaurant_id)
    normalized_search = (search or "").strip()
    normalized_created = (created or "").strip().lower()
    normalized_status = (status or "").strip().lower()
    normalized_payment = (payment or "").strip().lower()
    selected_source = (source or "").strip()
    normalized_direction = "asc" if direction == "asc" else "desc"

    if normalized_search:
        like = f"%{normalized_search}%"
        matching_orders = (
            db.session.query(Order.id.label("id"))
            .outerjoin(OrderItem, OrderItem.order_id == Order.id)
            .outerjoin(Menu, Menu.id == OrderItem.food_id)
            .filter(Order.restaurant_id == restaurant_id)
            .filter(
                or_(
                    cast(Order.id, String).ilike(like),
                    cast(Order.table_number, String).ilike(like),
                    cast(Order.created_at, String).ilike(like),
                    Order.status.ilike(like),
                    Menu.name.ilike(like),
                )
            )
            .distinct()
            .subquery()
        )
        base_query = base_query.filter(Order.id.in_(db.session.query(matching_orders.c.id)))

    if normalized_created == "today":
        start_at, end_at = _today_created_bounds()
        base_query = base_query.filter(
            Order.created_at >= start_at,
            Order.created_at < end_at,
        )

    if normalized_status == "active":
        base_query = base_query.filter(Order.status.in_(ORDER_DASHBOARD_ACTIVE_STATUSES))
    elif normalized_status:
        base_query = base_query.filter(Order.status == normalized_status)

    if normalized_payment == "paid":
        base_query = base_query.filter(Order.status == Order.STATUS_PAID)
    elif normalized_payment == "unpaid":
        base_query = base_query.filter(Order.status != Order.STATUS_PAID)

    sort_map = {
        "id": Order.id,
        "table": Order.table_number,
        "status": Order.status,
        "created_at": Order.created_at,
    }
    sort_column = sort_map.get(sort, Order.created_at)
    ordered_query = base_query.order_by(
        sort_column.asc() if normalized_direction == "asc" else sort_column.desc(),
        Order.id.desc(),
    )
    rows = _build_order_rows(ordered_query.all(), actor_role=actor_role)

    if selected_source:
        rows = [row for row in rows if row["source_label"] == selected_source]

    pagination = paginate_items(rows, page=page, per_page=per_page)
    page_rows = pagination["items"]

    status_counts = Counter(row["order"].status for row in rows)
    active_rows = [row for row in rows if row["order"].status in Order.ACTIVE_STATUSES]
    total_sales = round(sum(row["total"] for row in rows), 2)
    active_tables = len({row["order"].table_number for row in active_rows if row["order"].table_number})

    return {
        "rows": page_rows,
        "pagination": pagination,
        "overall_total": overall_total,
        "total_sales": total_sales,
        "submitted_count": status_counts.get(Order.STATUS_SUBMITTED, 0),
        "preparing_count": status_counts.get(Order.STATUS_PREPARING, 0),
        "ready_count": status_counts.get(Order.STATUS_READY, 0),
        "served_count": status_counts.get(Order.STATUS_SERVED, 0),
        "paid_count": status_counts.get(Order.STATUS_PAID, 0),
        "cancelled_count": status_counts.get(Order.STATUS_CANCELLED, 0),
        "active_count": len(active_rows),
        "active_tables": active_tables,
    }


def _today_created_bounds(reference=None, day_offset=0):
    current_time = reference or datetime.utcnow()
    start_at = datetime(current_time.year, current_time.month, current_time.day) + timedelta(days=day_offset)
    return start_at, start_at + timedelta(days=1)


def _build_dashboard_comparison_item(label, today_value, yesterday_value, formatter=None):
    today_display = formatter(today_value) if formatter else str(today_value)
    yesterday_display = formatter(yesterday_value) if formatter else str(yesterday_value)
    if today_value == yesterday_value:
        summary = "Same as yesterday"
        trend = "neutral"
    else:
        delta = today_value - yesterday_value
        if formatter:
            summary = (
                f"{format_order_currency(abs(delta))} {'up' if delta > 0 else 'down'} vs yesterday"
            )
        else:
            summary = f"{'+' if delta > 0 else '-'}{abs(delta)} vs yesterday"
        trend = "up" if delta > 0 else "down"

    return {
        "label": label,
        "today_display": today_display,
        "yesterday_value": yesterday_value,
        "yesterday_display": yesterday_display,
        "summary": summary,
        "trend": trend,
    }


def _format_relative_timestamp(value, *, reference=None):
    if value is None:
        return "Unknown time"
    current_time = reference or datetime.utcnow()
    delta = max(timedelta(0), current_time - value)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} min{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hr{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def summarize_order_pipeline(rows):
    status_counts = Counter(row["order"].status for row in rows)
    active_rows = [row for row in rows if row["order"].status in Order.ACTIVE_STATUSES]
    return {
        "submitted_count": status_counts.get(Order.STATUS_SUBMITTED, 0),
        "preparing_count": status_counts.get(Order.STATUS_PREPARING, 0),
        "ready_count": status_counts.get(Order.STATUS_READY, 0),
        "served_count": status_counts.get(Order.STATUS_SERVED, 0),
        "paid_count": status_counts.get(Order.STATUS_PAID, 0),
        "cancelled_count": status_counts.get(Order.STATUS_CANCELLED, 0),
        "active_count": len(active_rows),
        "active_tables": len({row["order"].table_number for row in active_rows}),
    }


def get_operations_snapshot(restaurant):
    order_rows = list_order_rows(restaurant.id)
    menu_items = list_menu_items(restaurant.id)
    pipeline = summarize_order_pipeline(order_rows)
    top_items = Counter()
    table_counts = Counter()
    now = datetime.utcnow()
    active_ages = []
    late_count = 0
    orders_by_hour = Counter()
    total_sales = round(sum(row["total"] for row in order_rows), 2)

    for row in order_rows:
        table_counts[row["order"].table_number] += 1
        created_at = row["order"].created_at
        if created_at:
            orders_by_hour[created_at.strftime("%H:00")] += 1
        if row["order"].status in {Order.STATUS_SUBMITTED, Order.STATUS_PREPARING} and created_at:
            age_minutes = max(0, int((now - created_at).total_seconds() // 60))
            active_ages.append(age_minutes)
            if age_minutes >= 5:
                late_count += 1
        for item in row["order_items"]:
            dish_name = item.food.name if item.food else f"Item {item.food_id}"
            top_items[dish_name] += item.quantity or 0

    average_ticket_minutes = round(sum(active_ages) / len(active_ages), 1) if active_ages else 0
    average_order_value = round(total_sales / len(order_rows), 2) if order_rows else 0
    busiest_table, busiest_table_count = table_counts.most_common(1)[0] if table_counts else (None, 0)
    late_rate = round((late_count / pipeline["active_count"]) * 100, 1) if pipeline["active_count"] else 0
    peak_hour = orders_by_hour.most_common(1)[0][0] if orders_by_hour else "No peak yet"
    service_alerts = []
    if late_count:
        service_alerts.append(f"{late_count} active ticket(s) are older than five minutes and may need attention.")
    if pipeline["served_count"]:
        service_alerts.append(
            f"{pipeline['served_count']} ticket(s) have been served and should be closed out at payment."
        )
    if pipeline["ready_count"]:
        service_alerts.append(
            f"{pipeline['ready_count']} ticket(s) are ready for service handoff."
        )
    if pipeline["submitted_count"] > pipeline["preparing_count"] + 2:
        service_alerts.append("Submitted tickets are stacking faster than the kitchen is pulling them forward.")
    if not service_alerts:
        service_alerts.append("Service flow looks balanced right now. Keep monitoring served tickets and payment handoff.")

    return {
        "restaurant": restaurant,
        "menu_count": len(menu_items),
        "recent_orders": order_rows[:6],
        "top_items": top_items.most_common(5),
        "total_sales": total_sales,
        "average_order_value": average_order_value,
        "busiest_table": busiest_table,
        "busiest_table_count": busiest_table_count,
        "late_count": late_count,
        "late_rate": late_rate,
        "average_ticket_minutes": average_ticket_minutes,
        "peak_hour": peak_hour,
        "service_alerts": service_alerts,
        **pipeline,
    }


def get_pos_snapshot(restaurant):
    order_rows = list_order_rows(restaurant.id)
    menu_items = list_menu_items(restaurant.id)
    pipeline = summarize_order_pipeline(order_rows)
    recent_orders = order_rows[:5]
    suggested_tables = []

    seen_tables = {
        row["order"].table_number
        for row in order_rows
        if row["order"].status in Order.ACTIVE_STATUSES
    }
    for number in sorted(seen_tables):
        suggested_tables.append(number)
    candidate = 1
    while len(suggested_tables) < 6:
        if candidate not in suggested_tables:
            suggested_tables.append(candidate)
        candidate += 1

    return {
        "restaurant": restaurant,
        "menu_preview": menu_items[:8],
        "orderable_items": menu_items,
        "recent_orders": recent_orders,
        "table_launchers": suggested_tables[:6],
        "open_ticket_total": pipeline["active_count"],
        "submitted_count": pipeline["submitted_count"],
        "served_count": pipeline["served_count"],
        "ready_count": pipeline["ready_count"],
        "active_tables": pipeline["active_tables"],
        "menu_count": len(menu_items),
    }


def serialize_kitchen_orders(restaurant_id):
    rows = list_order_rows(restaurant_id)
    payload = []
    for row in rows:
        order = row["order"]
        payload.append(
            {
                "order_id": order.id,
                "table": order.table_number,
                "table_number": order.table_number,
                "status": order.status,
                "table_status": row.get("table_status", Table.STATUS_AVAILABLE),
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "items": [
                    {
                        "name": item.food.name if item.food else f"Item {item.food_id}",
                        "quantity": item.quantity,
                    }
                    for item in row["order_items"]
                ],
            }
        )
    return payload


def _build_order_rows(orders, *, actor_role=None):
    order_ids = [order.id for order in orders]
    items_by_order = defaultdict(list)
    events_by_order = defaultdict(list)
    table_status_map = _table_status_map(
        orders[0].restaurant_id if orders else None,
        [order.table_number for order in orders],
    )

    if order_ids:
        order_items = (
            OrderItem.query.options(joinedload(OrderItem.food))
            .filter(OrderItem.order_id.in_(order_ids))
            .all()
        )
        for item in order_items:
            items_by_order[item.order_id].append(item)

    if order_ids and orders:
        order_events = (
            OrderEvent.query.options(joinedload(OrderEvent.actor))
            .filter(
                OrderEvent.restaurant_id == orders[0].restaurant_id,
                OrderEvent.order_id.in_(order_ids),
            )
            .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
            .all()
        )
        for event in order_events:
            events_by_order[event.order_id].append(event)

    rows = []
    for order in orders:
        order_items = items_by_order.get(order.id, [])
        total = round(
            sum((item.food.price if item.food else 0) * item.quantity for item in order_items),
            2,
        )
        events = events_by_order.get(order.id, [])
        display = build_order_display_context(
            order,
            events=events,
            total=total,
        )
        rows.append(
            {
                "order": order,
                "order_items": order_items,
                "total": display["total"],
                "total_display": display["total_display"],
                "currency": display["currency"],
                "table_status": table_status_map.get(order.table_number, Table.STATUS_AVAILABLE),
                "status_label": display["status_label"],
                "status_badge_class": display["status_badge_class"],
                "payment_status": display["payment_status"],
                "payment_badge_class": display["payment_badge_class"],
                "source_context": display["source_context"],
                "source_label": display["source_label"],
                "source_badge_class": display["source_badge_class"],
                "created_at_display": display["created_at_display"],
                "updated_at": display["updated_at"],
                "updated_at_display": display["updated_at_display"],
                "detail_url": display["detail_url"],
                "order_reference": display["order_reference"],
                "allowed_statuses": get_allowed_order_transitions(order.status, actor_role=actor_role),
            }
        )
    return rows


def _table_status_map(restaurant_id, table_numbers):
    if not restaurant_id or not table_numbers:
        return {}
    rows = (
        db.session.query(Table.table_number, Table.status)
        .filter(
            Table.restaurant_id == restaurant_id,
            Table.table_number.in_(set(table_numbers)),
        )
        .all()
    )
    return {table_number: status for table_number, status in rows}
