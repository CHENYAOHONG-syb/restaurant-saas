from sqlalchemy.orm import joinedload

from app.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.extensions import db
from app.models.cart import Cart
from app.models.menu_inventory_requirement import MenuInventoryRequirement
from app.models.order import Order
from app.models.order_event import OrderEvent
from app.models.order_item import OrderItem
from app.models.table import Table
from app.services.floor_service import (
    mark_table_occupied,
    release_table_after_cancellation,
    release_table_after_payment,
    table_has_active_orders,
)
from app.services.inventory_service import apply_inventory, restore_inventory
from app.services.tenant_service import get_menu_item_for_restaurant, get_order_for_restaurant, get_restaurant

ORDER_STATUS_LABELS = {
    Order.STATUS_SUBMITTED: "Submitted",
    Order.STATUS_PREPARING: "Preparing",
    Order.STATUS_READY: "Ready",
    Order.STATUS_SERVED: "Served",
    Order.STATUS_PAID: "Paid",
    Order.STATUS_CANCELLED: "Cancelled",
}

ORDER_ACTION_LABELS = {
    Order.STATUS_PREPARING: "Start Preparation",
    Order.STATUS_READY: "Mark Ready",
    Order.STATUS_SERVED: "Mark Served",
    Order.STATUS_PAID: "Mark Paid",
    Order.STATUS_CANCELLED: "Cancel Order",
}

ORDER_ALLOWED_TRANSITIONS = {
    Order.STATUS_SUBMITTED: (Order.STATUS_PREPARING, Order.STATUS_CANCELLED),
    Order.STATUS_PREPARING: (Order.STATUS_READY, Order.STATUS_CANCELLED),
    Order.STATUS_READY: (Order.STATUS_SERVED,),
    Order.STATUS_SERVED: (Order.STATUS_PAID,),
    Order.STATUS_PAID: (),
    Order.STATUS_CANCELLED: (),
}

ROLE_TRANSITION_OVERRIDES = {
    "owner": ORDER_ALLOWED_TRANSITIONS,
    "manager": ORDER_ALLOWED_TRANSITIONS,
    "kitchen": {
        Order.STATUS_SUBMITTED: (Order.STATUS_PREPARING,),
        Order.STATUS_PREPARING: (Order.STATUS_READY,),
    },
    "staff": {
        Order.STATUS_READY: (Order.STATUS_SERVED,),
    },
    "cashier": {
        Order.STATUS_READY: (Order.STATUS_SERVED,),
        Order.STATUS_SERVED: (Order.STATUS_PAID,),
        Order.STATUS_SUBMITTED: (Order.STATUS_CANCELLED,),
    },
}

KITCHEN_VISIBLE_STATUSES = (
    Order.STATUS_SUBMITTED,
    Order.STATUS_PREPARING,
    Order.STATUS_READY,
)

DEFAULT_CURRENCY = "RM"

ACTOR_ROLE_LABELS = {
    "owner": "Owner",
    "manager": "Manager",
    "cashier": "Cashier",
    "staff": "Staff",
    "kitchen": "Kitchen",
}

SOURCE_BADGE_CLASSES = {
    "customer_qr_order": "secondary",
    "pos_order": "secondary",
    "admin_created": "secondary",
    "staff_created": "secondary",
    "unknown": "secondary",
}

ORDER_PAYMENT_FILTER_OPTIONS = ("Paid", "Unpaid")
ORDER_SOURCE_FILTER_OPTIONS = (
    "Customer QR Order",
    "POS Order",
    "Admin Created",
    "Staff Created",
    "Unknown",
)


class OrderValidationError(ValidationError):
    pass


def get_allowed_order_transitions(current_status, actor_role=None):
    normalized_role = (actor_role or "").strip().lower()
    role_map = ROLE_TRANSITION_OVERRIDES.get(normalized_role)
    if role_map is None:
        return ORDER_ALLOWED_TRANSITIONS.get(current_status, ())
    return role_map.get(current_status, ())


def get_order_status_label(status):
    normalized_status = (status or "").strip()
    return ORDER_STATUS_LABELS.get(normalized_status, normalized_status.replace("_", " ").title())


def format_order_currency(amount, *, currency=DEFAULT_CURRENCY):
    normalized_amount = round(float(amount or 0), 2)
    return f"{currency} {normalized_amount:.2f}"


def format_order_timestamp(value, *, include_seconds=False, empty_label="—"):
    if value is None:
        return empty_label
    timestamp_format = "%Y-%m-%d %H:%M:%S" if include_seconds else "%Y-%m-%d %H:%M"
    return value.strftime(timestamp_format)


def _record_order_event(
    order,
    event_type,
    *,
    actor_user_id=None,
    from_status=None,
    to_status=None,
    note=None,
):
    db.session.add(
        OrderEvent(
            order_id=order.id,
            restaurant_id=order.restaurant_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            note=note,
        )
    )


def _load_order_items(order_id):
    return (
        OrderItem.query.options(joinedload(OrderItem.food))
        .filter(OrderItem.order_id == order_id)
        .order_by(OrderItem.id.asc())
        .all()
    )


def _build_line_items(order):
    order_items = _load_order_items(order.id)
    line_items = []
    total_amount = 0
    for item in order_items:
        unit_price = item.food.price if item.food else 0
        quantity = item.quantity or 0
        subtotal = round(unit_price * quantity, 2)
        total_amount += subtotal
        line_items.append(
            {
                "name": item.food.name if item.food else f"Deleted item #{item.food_id}",
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
            }
        )
    return order_items, line_items, round(total_amount, 2)


def _build_amount_context(line_items, *, currency=DEFAULT_CURRENCY):
    subtotal = round(sum(item["subtotal"] for item in line_items), 2)
    total = subtotal
    return {
        "currency": currency,
        "subtotal": subtotal,
        "total": total,
    }


def _inventory_requirements_for_order_items(order_items):
    if not order_items:
        return []
    menu_ids = sorted({item.food_id for item in order_items if item.food_id})
    if not menu_ids:
        return []
    requirements = (
        MenuInventoryRequirement.query.options(joinedload(MenuInventoryRequirement.inventory_item))
        .filter(MenuInventoryRequirement.menu_id.in_(menu_ids))
        .order_by(MenuInventoryRequirement.id.asc())
        .all()
    )
    grouped = {}
    for requirement in requirements:
        grouped.setdefault(requirement.menu_id, []).append(requirement)

    rows = []
    for item in order_items:
        linked = grouped.get(item.food_id, [])
        for requirement in linked:
            rows.append(
                {
                    "menu_name": item.food.name if item.food else f"Item {item.food_id}",
                    "inventory_name": requirement.inventory_item.name if requirement.inventory_item else "Inventory item",
                    "unit": requirement.inventory_item.unit if requirement.inventory_item else "unit",
                    "per_item_quantity": requirement.quantity_required,
                    "ordered_quantity": item.quantity or 0,
                    "total_required": (item.quantity or 0) * requirement.quantity_required,
                    "current_stock": requirement.inventory_item.stock if requirement.inventory_item else None,
                }
            )
    return rows


def _build_inventory_context(order, order_items):
    rows = _inventory_requirements_for_order_items(order_items)
    has_mapping = bool(rows)
    events = (
        OrderEvent.query.filter_by(order_id=order.id, restaurant_id=order.restaurant_id)
        .filter(OrderEvent.event_type.in_(("inventory_applied", "inventory_restored")))
        .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
        .all()
    )
    applied_event = next((event for event in events if event.event_type == "inventory_applied"), None)
    restored_event = next((event for event in reversed(events) if event.event_type == "inventory_restored"), None)

    if restored_event:
        summary = "Inventory was deducted earlier and restored after the order was cancelled."
        status = "restored"
    elif order.inventory_applied_at:
        summary = "Inventory has been deducted because the order entered preparation."
        status = "applied"
    elif not has_mapping:
        summary = "No inventory mappings are attached to the menu items in this order yet."
        status = "unmapped"
    elif order.status == Order.STATUS_CANCELLED:
        summary = "The order was cancelled before stock deduction was required."
        status = "not_applied"
    else:
        summary = "Inventory will deduct when the order moves from Submitted to Preparing."
        status = "pending"

    return {
        "status": status,
        "summary": summary,
        "has_mapping": has_mapping,
        "lines": rows,
        "applied_at": order.inventory_applied_at,
        "applied_event": applied_event,
        "restored_event": restored_event,
    }


def _build_table_context(order, actor_role=None):
    if not order.table_number:
        return {
            "has_table": False,
            "summary": "This order is not linked to a dine-in table.",
        }

    table = Table.query.filter_by(
        restaurant_id=order.restaurant_id,
        table_number=order.table_number,
    ).first()
    if table is None:
        return {
            "has_table": False,
            "summary": f"Table {order.table_number} is no longer configured, but the order still keeps the original reference.",
        }

    normalized_role = (actor_role or "").strip().lower()
    active_orders_on_table = table_has_active_orders(order.restaurant_id, table.table_number)
    can_mark_available = (
        table.status == Table.STATUS_NEEDS_CLEANING
        and normalized_role in {"owner", "manager", "cashier", "staff"}
        and not active_orders_on_table
    )

    if order.status in Order.ACTIVE_STATUSES:
        summary = "This order is actively occupying the table."
        holding_table = True
    elif order.status == Order.STATUS_PAID and table.status == Table.STATUS_NEEDS_CLEANING:
        summary = "Payment is complete. The table is waiting for cleaning before it returns to service."
        holding_table = False
    elif order.status == Order.STATUS_CANCELLED and table.status == Table.STATUS_AVAILABLE:
        summary = "The order was cancelled and the table was released back to service."
        holding_table = False
    elif table.status == Table.STATUS_AVAILABLE:
        summary = "The table is available for the next guest."
        holding_table = False
    else:
        summary = "The table state is linked to broader floor operations."
        holding_table = False

    release_reason = None
    if table.status == Table.STATUS_NEEDS_CLEANING and not can_mark_available:
        if active_orders_on_table:
            release_reason = "Another active order still exists on this table."
        elif normalized_role not in {"owner", "manager", "cashier", "staff"}:
            release_reason = "Your role cannot release tables back to available."

    return {
        "has_table": True,
        "table": table,
        "summary": summary,
        "holding_table": holding_table,
        "can_mark_available": can_mark_available,
        "release_reason": release_reason,
    }


def _actor_label_for_event(event):
    actor = getattr(event, "actor", None)
    if actor is None:
        return "System"
    normalized_role = (getattr(actor, "role", "") or "").strip().lower()
    return ACTOR_ROLE_LABELS.get(normalized_role, "Staff Member")


def _build_source_context(events):
    created_event = next((event for event in events if event.event_type == "created"), None)
    if created_event is None:
        return {
            "key": "unknown",
            "label": "Unknown",
            "summary": "The original order source is unavailable for this record.",
        }

    note = (created_event.note or "").strip().lower()
    actor_role = (
        getattr(getattr(created_event, "actor", None), "role", "") or ""
    ).strip().lower()

    if "guest checkout" in note:
        return {
            "key": "customer_qr_order",
            "label": "Customer QR Order",
            "summary": "Placed from the guest ordering flow after the table menu was opened.",
        }
    if "pos created" in note:
        return {
            "key": "pos_order",
            "label": "POS Order",
            "summary": "Captured from the cashier POS workspace for an in-person guest.",
        }
    if actor_role in {"owner", "manager"}:
        return {
            "key": "admin_created",
            "label": "Admin Created",
            "summary": "Created by a restaurant admin user from the back office.",
        }
    if actor_role in {"cashier", "staff", "kitchen"}:
        return {
            "key": "staff_created",
            "label": "Staff Created",
            "summary": "Created internally by a restaurant team member.",
        }
    return {
        "key": "unknown",
        "label": "Unknown",
        "summary": "The order source could not be determined with confidence.",
    }


def build_order_source_context(events):
    context = _build_source_context(events)
    context["badge_class"] = SOURCE_BADGE_CLASSES.get(context["key"], "secondary")
    return context


def _build_note_context(order):
    note = (order.note or "").strip()
    return {
        "has_note": bool(note),
        "text": note or "No notes provided.",
    }


def _build_payment_context(order, events, *, updated_at=None):
    paid_event = next(
        (
            event
            for event in reversed(events)
            if event.event_type == "status_changed" and event.to_status == Order.STATUS_PAID
        ),
        None,
    )
    payment_status = "Paid" if order.status == Order.STATUS_PAID else "Unpaid"
    paid_at = None
    if order.status == Order.STATUS_PAID:
        paid_at = paid_event.created_at if paid_event is not None else updated_at

    return {
        "payment_status": payment_status,
        "payment_method": "Manual",
        "paid_at": paid_at,
        "payment_badge_class": "paid" if payment_status == "Paid" else "secondary",
    }


def build_order_payment_context(order, events, *, updated_at=None):
    return _build_payment_context(order, events, updated_at=updated_at)


def build_order_display_context(order, *, events=None, total=0, updated_at=None):
    timeline_anchor = updated_at
    if timeline_anchor is None:
        timeline_anchor = events[-1].created_at if events else order.created_at

    source_context = build_order_source_context(events or [])
    payment_context = build_order_payment_context(order, events or [], updated_at=timeline_anchor)
    total_amount = round(total or 0, 2)

    return {
        "order_reference": f"#{order.id}",
        "status_label": get_order_status_label(order.status),
        "status_badge_class": order.status,
        "source_context": source_context,
        "source_label": source_context["label"],
        "source_badge_class": source_context["badge_class"],
        "currency": DEFAULT_CURRENCY,
        "total": total_amount,
        "total_display": format_order_currency(total_amount),
        "created_at_display": format_order_timestamp(order.created_at),
        "updated_at": timeline_anchor,
        "updated_at_display": format_order_timestamp(timeline_anchor),
        "detail_url": f"/admin/orders/{order.restaurant_id}/{order.id}",
        **payment_context,
    }


def _build_timeline_entry(event):
    actor_label = _actor_label_for_event(event)

    if event.event_type == "created":
        title = "Order submitted"
        status = event.to_status or Order.STATUS_SUBMITTED
        description = event.note or "The order entered the live service workflow."
    elif event.event_type == "status_changed":
        title = ORDER_STATUS_LABELS.get(event.to_status, "Status updated")
        status = event.to_status or "secondary"
        description = (
            event.note
            or f"Order moved from {ORDER_STATUS_LABELS.get(event.from_status, event.from_status)} "
            f"to {ORDER_STATUS_LABELS.get(event.to_status, event.to_status)}."
        )
    elif event.event_type == "table_occupied":
        title = "Table occupied"
        status = Table.STATUS_OCCUPIED
        description = event.note or "A dine-in table was assigned and marked occupied."
    elif event.event_type == "table_cleaning_required":
        title = "Table needs cleaning"
        status = Table.STATUS_NEEDS_CLEANING
        description = event.note or "The table moved into cleaning after payment."
    elif event.event_type == "table_marked_available":
        title = "Table available again"
        status = Table.STATUS_AVAILABLE
        description = event.note or "Staff completed cleaning and marked the table available again."
    elif event.event_type == "table_released":
        title = "Table released"
        status = Table.STATUS_AVAILABLE
        description = event.note or "The table returned to available service."
    elif event.event_type == "inventory_applied":
        title = "Inventory deducted"
        status = "secondary"
        description = event.note or "Stock was deducted as preparation began."
    elif event.event_type == "inventory_restored":
        title = "Inventory restored"
        status = "secondary"
        description = event.note or "Stock was restored after cancellation."
    else:
        title = "Order activity"
        status = "secondary"
        description = event.note or "Order activity recorded."

    return {
        "title": title,
        "status": status,
        "description": description,
        "timestamp": event.created_at,
        "actor_label": actor_label,
    }


def _build_derived_timeline(order):
    entries = [
        {
            "title": "Order submitted",
            "status": order.status,
            "description": "This timeline is derived because no explicit order events have been recorded for this order yet.",
            "timestamp": order.created_at,
            "actor_label": None,
        }
    ]
    if order.inventory_applied_at:
        entries.append(
            {
                "title": "Inventory deducted",
                "status": "secondary",
                "description": "Stock was deducted when the order entered preparation.",
                "timestamp": order.inventory_applied_at,
                "actor_label": None,
            }
        )
    return entries


def get_order_detail_context(restaurant_id, order_id, *, actor_role=None):
    order = get_order_for_restaurant(restaurant_id, order_id)
    restaurant = get_restaurant(restaurant_id)
    order_items, line_items, _ = _build_line_items(order)
    amounts = _build_amount_context(line_items)

    events = (
        OrderEvent.query.options(joinedload(OrderEvent.actor))
        .filter_by(order_id=order.id, restaurant_id=restaurant_id)
        .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
        .all()
    )
    timeline = [_build_timeline_entry(event) for event in events] if events else _build_derived_timeline(order)
    updated_at = timeline[-1]["timestamp"] if timeline else order.created_at
    allowed_statuses = get_allowed_order_transitions(order.status, actor_role=actor_role)
    source_context = build_order_source_context(events)
    note_context = _build_note_context(order)
    payment_context = build_order_payment_context(order, events, updated_at=updated_at)

    return {
        "restaurant": restaurant,
        "order": order,
        "line_items": line_items,
        "subtotal": amounts["subtotal"],
        "total": amounts["total"],
        "currency": amounts["currency"],
        "amounts": amounts,
        "total_amount": amounts["total"],
        "status_label": get_order_status_label(order.status),
        "customer_label": "Walk-in guest",
        "dining_mode": "Dine-in" if order.table_number else "Takeaway",
        "source_context": source_context,
        "note_context": note_context,
        **payment_context,
        "allowed_statuses": allowed_statuses,
        "action_labels": ORDER_ACTION_LABELS,
        "table_context": _build_table_context(order, actor_role=actor_role),
        "inventory_context": _build_inventory_context(order, order_items),
        "timeline": timeline,
        "updated_at": updated_at,
        "is_terminal": order.status in Order.CLOSED_STATUSES,
        "receipt_url": f"/admin/orders/{restaurant_id}/{order.id}/receipt",
    }


def get_order_receipt_context(restaurant_id, order_id):
    order = get_order_for_restaurant(restaurant_id, order_id)
    restaurant = get_restaurant(restaurant_id)
    events = (
        OrderEvent.query.options(joinedload(OrderEvent.actor))
        .filter_by(order_id=order.id, restaurant_id=restaurant_id)
        .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
        .all()
    )
    _, line_items, _ = _build_line_items(order)
    amounts = _build_amount_context(line_items)
    updated_at = events[-1].created_at if events else order.created_at
    source_context = build_order_source_context(events)
    payment_context = build_order_payment_context(order, events, updated_at=updated_at)
    return {
        "restaurant": restaurant,
        "restaurant_id": restaurant_id,
        "order": order,
        "items": line_items,
        "subtotal": amounts["subtotal"],
        "total": amounts["total"],
        "currency": amounts["currency"],
        "amounts": amounts,
        "total_amount": amounts["total"],
        "status_label": get_order_status_label(order.status),
        "customer_label": "Walk-in guest",
        "source_context": source_context,
        "note_context": _build_note_context(order),
        **payment_context,
        "detail_url": f"/admin/orders/{restaurant_id}/{order.id}",
    }


def add_to_cart(food_id, table_number, restaurant_id):
    if not table_number or table_number < 1:
        raise OrderValidationError("Choose a valid table before adding to cart.")

    get_menu_item_for_restaurant(restaurant_id, food_id)

    item = Cart.query.filter_by(
        food_id=food_id,
        table_number=table_number,
        restaurant_id=restaurant_id,
    ).first()

    if item:
        item.quantity += 1
    else:
        item = Cart(
            food_id=food_id,
            table_number=table_number,
            restaurant_id=restaurant_id,
            quantity=1,
        )
        db.session.add(item)

    db.session.commit()
    return item


def get_cart(table_number, restaurant_id):
    return Cart.query.filter_by(
        table_number=table_number,
        restaurant_id=restaurant_id,
    ).all()


def remove_from_cart(cart_id, restaurant_id):
    deleted = Cart.query.filter_by(id=cart_id, restaurant_id=restaurant_id).delete()
    if not deleted:
        raise NotFoundError("Cart item not found for this restaurant.")
    db.session.commit()


def clear_cart(table_number, restaurant_id):
    Cart.query.filter_by(
        table_number=table_number,
        restaurant_id=restaurant_id,
    ).delete()
    db.session.commit()


def checkout(table_number, restaurant_id, *, actor_user_id=None, note=None):
    items = get_cart(table_number, restaurant_id)
    if not items:
        return None

    order = Order(
        table_number=table_number,
        restaurant_id=restaurant_id,
        status=Order.STATUS_SUBMITTED,
        note=(note or "").strip() or None,
    )
    db.session.add(order)
    db.session.flush()
    mark_table_occupied(restaurant_id, table_number)

    for item in items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                food_id=item.food_id,
                quantity=item.quantity,
            )
        )

    Cart.query.filter_by(
        table_number=table_number,
        restaurant_id=restaurant_id,
    ).delete(synchronize_session=False)
    _record_order_event(
        order,
        "created",
        actor_user_id=actor_user_id,
        to_status=order.status,
        note="Guest checkout submitted the order.",
    )
    _record_order_event(
        order,
        "table_occupied",
        actor_user_id=actor_user_id,
        note=f"Table {order.table_number} was marked occupied for this dine-in order.",
    )
    db.session.commit()
    return order


def create_manual_order(restaurant_id, table_number, line_items, *, actor_user_id=None, note=None):
    if not table_number:
        raise OrderValidationError("Table number is required for a manual ticket.")

    normalized_items = []
    for line in line_items:
        food_id = int(line.get("food_id") or 0)
        quantity = int(line.get("quantity") or 0)
        if not food_id or quantity <= 0:
            continue
        menu_item = get_menu_item_for_restaurant(restaurant_id, food_id)
        normalized_items.append((menu_item, quantity))

    if not normalized_items:
        raise OrderValidationError("Choose at least one menu item for the manual ticket.")

    order = Order(
        table_number=table_number,
        restaurant_id=restaurant_id,
        status=Order.STATUS_SUBMITTED,
        note=(note or "").strip() or None,
    )
    db.session.add(order)
    db.session.flush()
    mark_table_occupied(restaurant_id, table_number)

    for menu_item, quantity in normalized_items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                food_id=menu_item.id,
                quantity=quantity,
            )
        )

    _record_order_event(
        order,
        "created",
        actor_user_id=actor_user_id,
        to_status=order.status,
        note="POS created a manual order.",
    )
    _record_order_event(
        order,
        "table_occupied",
        actor_user_id=actor_user_id,
        note=f"Table {order.table_number} was marked occupied for this dine-in order.",
    )
    db.session.commit()
    return order


def transition_order_status(restaurant_id, order_id, next_status, *, actor_role=None, actor_user_id=None):
    order = get_order_for_restaurant(restaurant_id, order_id)
    allowed_statuses = get_allowed_order_transitions(order.status, actor_role=actor_role)
    if next_status not in allowed_statuses:
        raise BusinessRuleError(
            f"Order #{order.id} cannot move from {ORDER_STATUS_LABELS.get(order.status, order.status)} "
            f"to {ORDER_STATUS_LABELS.get(next_status, next_status)}."
        )

    previous_status = order.status
    inventory_applied = False
    inventory_restored = False
    if previous_status == Order.STATUS_SUBMITTED and next_status == Order.STATUS_PREPARING:
        apply_inventory(order)
        inventory_applied = True
    elif next_status == Order.STATUS_CANCELLED:
        inventory_restored = bool(order.inventory_applied_at)
        restore_inventory(order)

    order.status = next_status
    table_event_type = None
    table_event_note = None

    if next_status in Order.ACTIVE_STATUSES:
        mark_table_occupied(order.restaurant_id, order.table_number)
    elif next_status == Order.STATUS_PAID:
        table = release_table_after_payment(order.restaurant_id, order.table_number)
        if table is not None:
            if table.status == Table.STATUS_NEEDS_CLEANING:
                table_event_type = "table_cleaning_required"
                table_event_note = f"Table {table.table_number} is now waiting for cleaning."
            elif table.status == Table.STATUS_OCCUPIED:
                table_event_type = "table_occupied"
                table_event_note = f"Table {table.table_number} remains occupied because other active orders still exist."
    elif next_status == Order.STATUS_CANCELLED:
        table = release_table_after_cancellation(order.restaurant_id, order.table_number)
        if table is not None:
            if table.status == Table.STATUS_AVAILABLE:
                table_event_type = "table_released"
                table_event_note = f"Table {table.table_number} returned to available service."
            elif table.status == Table.STATUS_OCCUPIED:
                table_event_type = "table_occupied"
                table_event_note = f"Table {table.table_number} remains occupied because another active order is still open."

    _record_order_event(
        order,
        "status_changed",
        actor_user_id=actor_user_id,
        from_status=previous_status,
        to_status=next_status,
        note=f"Status changed from {ORDER_STATUS_LABELS.get(previous_status, previous_status)} "
        f"to {ORDER_STATUS_LABELS.get(next_status, next_status)}.",
    )
    if inventory_applied:
        _record_order_event(
            order,
            "inventory_applied",
            actor_user_id=actor_user_id,
            note="Inventory was deducted as the order entered preparation.",
        )
    if inventory_restored:
        _record_order_event(
            order,
            "inventory_restored",
            actor_user_id=actor_user_id,
            note="Inventory was restored after the order was cancelled.",
        )
    if table_event_type:
        _record_order_event(
            order,
            table_event_type,
            actor_user_id=actor_user_id,
            note=table_event_note,
        )

    db.session.commit()
    return order
