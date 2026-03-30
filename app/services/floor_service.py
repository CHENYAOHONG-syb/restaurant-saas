from io import BytesIO

import qrcode

from app.exceptions import BusinessRuleError, ValidationError
from app.extensions import db
from app.models.order import Order
from app.models.order_event import OrderEvent
from app.models.table import Table
from app.services.tenant_service import get_table_by_number_for_restaurant, get_table_for_restaurant

TABLE_STATUS_OPTIONS = Table.STATUS_OPTIONS


def get_dashboard_table_metrics(restaurant_id):
    rows = (
        db.session.query(Table.status, db.func.count(Table.id))
        .filter(Table.restaurant_id == restaurant_id)
        .group_by(Table.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    return {
        "available_tables": counts.get(Table.STATUS_AVAILABLE, 0),
        "occupied_tables": counts.get(Table.STATUS_OCCUPIED, 0),
        "needs_cleaning_tables": counts.get(Table.STATUS_NEEDS_CLEANING, 0),
    }


def sync_tables_from_orders(restaurant_id):
    existing_numbers = {
        table_number
        for table_number, in db.session.query(Table.table_number)
        .filter(Table.restaurant_id == restaurant_id)
        .all()
    }
    active_numbers = {
        table_number
        for table_number, in db.session.query(Order.table_number)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.table_number.isnot(None),
            Order.status.in_(Order.ACTIVE_STATUSES),
        )
        .distinct()
        .all()
        if table_number is not None
    }
    order_numbers = {
        table_number
        for table_number, in db.session.query(Order.table_number)
        .filter(Order.restaurant_id == restaurant_id, Order.table_number.isnot(None))
        .distinct()
        .all()
        if table_number is not None
    }
    missing = sorted(order_numbers - existing_numbers)
    if not missing:
        return
    db.session.add_all(
        [
            Table(
                restaurant_id=restaurant_id,
                table_number=number,
                status=Table.STATUS_OCCUPIED if number in active_numbers else Table.STATUS_AVAILABLE,
            )
            for number in missing
        ]
    )
    db.session.commit()


def list_tables(restaurant_id, *, status=None):
    sync_tables_from_orders(restaurant_id)
    query = Table.query.filter_by(restaurant_id=restaurant_id)
    normalized_status = (status or "").strip().lower()
    if normalized_status:
        query = query.filter(Table.status == normalized_status)
    return query.order_by(Table.table_number.asc()).all()


def create_tables(restaurant_id, *, count=1, starting_at=None):
    if count is None or count < 1:
        raise ValidationError("Choose at least one table to create.")
    if count > 50:
        raise ValidationError("Create at most 50 tables at a time.")

    existing_numbers = {
        table_number
        for table_number, in db.session.query(Table.table_number)
        .filter(Table.restaurant_id == restaurant_id)
        .all()
    }
    candidate = max(1, starting_at or 1)
    created = []
    while len(created) < count:
        if candidate not in existing_numbers:
            created.append(
                Table(
                    restaurant_id=restaurant_id,
                    table_number=candidate,
                    status=Table.STATUS_AVAILABLE,
                )
            )
            existing_numbers.add(candidate)
        candidate += 1

    db.session.add_all(created)
    db.session.commit()
    return created


def get_table(restaurant_id, table_id):
    return get_table_for_restaurant(restaurant_id, table_id)


def get_table_by_number(restaurant_id, table_number):
    return get_table_by_number_for_restaurant(restaurant_id, table_number)


def ensure_table(restaurant_id, table_number):
    if not table_number:
        return None
    table = Table.query.filter_by(
        restaurant_id=restaurant_id,
        table_number=table_number,
    ).first()
    if table is None:
        table = Table(
            restaurant_id=restaurant_id,
            table_number=table_number,
            status=Table.STATUS_AVAILABLE,
        )
        db.session.add(table)
        db.session.flush()
    return table


def mark_table_occupied(restaurant_id, table_number):
    table = ensure_table(restaurant_id, table_number)
    if table is not None:
        if table.status == Table.STATUS_NEEDS_CLEANING:
            raise BusinessRuleError("This table still needs cleaning before it can be seated again.")
        table.status = Table.STATUS_OCCUPIED
    return table


def table_has_active_orders(restaurant_id, table_number):
    return (
        db.session.query(Order.id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.table_number == table_number,
            Order.status.in_(Order.ACTIVE_STATUSES),
        )
        .first()
        is not None
    )


def release_table_after_payment(restaurant_id, table_number):
    table = ensure_table(restaurant_id, table_number)
    if table is None:
        return None
    has_active_orders = table_has_active_orders(restaurant_id, table_number)
    table.status = Table.STATUS_OCCUPIED if has_active_orders else Table.STATUS_NEEDS_CLEANING
    return table


def release_table_after_cancellation(restaurant_id, table_number):
    table = ensure_table(restaurant_id, table_number)
    if table is None:
        return None
    has_active_orders = table_has_active_orders(restaurant_id, table_number)
    if has_active_orders:
        table.status = Table.STATUS_OCCUPIED
    elif table.status != Table.STATUS_NEEDS_CLEANING:
        table.status = Table.STATUS_AVAILABLE
    return table


def _get_order_for_manual_table_release(restaurant_id, table_number):
    event = (
        db.session.query(OrderEvent)
        .join(Order, Order.id == OrderEvent.order_id)
        .filter(
            OrderEvent.restaurant_id == restaurant_id,
            Order.table_number == table_number,
            OrderEvent.event_type == "table_cleaning_required",
        )
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .first()
    )
    if event is not None:
        return Order.query.filter_by(id=event.order_id, restaurant_id=restaurant_id).first()

    return (
        Order.query.filter_by(
            restaurant_id=restaurant_id,
            table_number=table_number,
            status=Order.STATUS_PAID,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .first()
    )


def update_table_status(table, status, *, actor_user_id=None):
    previous_status = table.status
    normalized_status = (status or "").strip().lower()
    if normalized_status not in TABLE_STATUS_OPTIONS:
        raise ValidationError("Choose a valid table status.")
    if table_has_active_orders(table.restaurant_id, table.table_number) and normalized_status != Table.STATUS_OCCUPIED:
        raise BusinessRuleError("This table still has active orders and must remain occupied.")
    table.status = normalized_status

    if (
        previous_status == Table.STATUS_NEEDS_CLEANING
        and normalized_status == Table.STATUS_AVAILABLE
    ):
        order = _get_order_for_manual_table_release(table.restaurant_id, table.table_number)
        if order is not None:
            db.session.add(
                OrderEvent(
                    order_id=order.id,
                    restaurant_id=order.restaurant_id,
                    event_type="table_marked_available",
                    actor_user_id=actor_user_id,
                    note=f"Table {table.table_number} was marked available after cleaning.",
                )
            )

    db.session.commit()
    return table


def build_qr_code_image(payload):
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
