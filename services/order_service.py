from services.db import get_db
from datetime import datetime

class InsufficientStockError(Exception):
    pass

# CREATE ORDER (atomic: uses transaction, rollbacks on error)
def create_order(restaurant_id, table_number, items):
    """
    items: list of {"food_id": int, "qty": int}
    returns: order_id (int)
    """

    db = get_db()

    try:
        # Begin: calculate total
        total = 0.0
        for item in items:
            food = db.execute(
                "SELECT id, price FROM menu WHERE id=? AND restaurant_id=?",
                (item["food_id"], restaurant_id)
            ).fetchone()

            if not food:
                raise ValueError(f"Food id {item['food_id']} not found for restaurant {restaurant_id}")

            price = food["price"] or 0.0
            total += price * int(item["qty"])

        # Insert order and get id
        cursor = db.execute(
            """
            INSERT INTO orders (restaurant_id, table_number, total, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (restaurant_id, table_number, total, "pending", datetime.utcnow().isoformat())
        )
        order_id = cursor.lastrowid

        # Insert order_items and adjust inventory per item
        for item in items:
            # record item price at time of order for audit
            food = db.execute(
                "SELECT price FROM menu WHERE id=? AND restaurant_id=?",
                (item["food_id"], restaurant_id)
            ).fetchone()
            item_price = food["price"] or 0.0

            db.execute(
                """
                INSERT INTO order_items (order_id, food_id, qty, price)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, item["food_id"], int(item["qty"]), item_price)
            )

            # reduce inventory for this menu item (will check stock and raise if insufficient)
            reduce_inventory(db, item["food_id"], int(item["qty"]), reason=f"order#{order_id}")

        # commit transaction
        db.commit()
        return order_id

    except Exception:
        db.rollback()
        raise


# REDUCE INVENTORY (uses provided db connection when possible)
def reduce_inventory(db_or_conn, food_id, qty, reason=None):
    """
    Reduce inventory based on recipes for a food item.
    - db_or_conn: either a db connection (preferred when called from create_order) or None (then will call get_db()).
    - food_id: menu id
    - qty: how many of the food item were ordered
    - reason: optional string to insert to inventory_logs
    Raises InsufficientStockError if any ingredient stock would go negative.
    """

    # Accept either a connection object or create one
    if hasattr(db_or_conn, "execute"):
        db = db_or_conn
    else:
        db = get_db()

    # Fetch recipe rows: expected columns: inventory_id, qty (per one food)
    recipes = db.execute(
        "SELECT inventory_id, qty FROM recipes WHERE food_id=?",
        (food_id,)
    ).fetchall()

    # First pass: check stock availability for all ingredients
    shortages = []
    for r in recipes:
        inv_id = r["inventory_id"]
        needed = (r["qty"] or 0) * qty

        inv = db.execute(
            "SELECT stock FROM inventory WHERE id=?",
            (inv_id,)
        ).fetchone()

        if not inv:
            shortages.append(f"Inventory id {inv_id} not found")
            continue

        current = inv["stock"] or 0

        if current < needed:
            shortages.append(f"inventory_id {inv_id} stock {current} < needed {needed}")

    if shortages:
        # Reject the whole operation rather than creating partial orders
        raise InsufficientStockError("Insufficient stock: " + "; ".join(shortages))

    # Second pass: apply updates and write logs
    for r in recipes:
        inv_id = r["inventory_id"]
        needed = (r["qty"] or 0) * qty

        db.execute(
            """
            UPDATE inventory
            SET stock = stock - ?
            WHERE id = ?
            """,
            (needed, inv_id)
        )

        # insert inventory log for audit
        db.execute(
            """
            INSERT INTO inventory_logs (inventory_id, change_amount, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (inv_id, -needed, reason or f"reduce_for_food_{food_id}", datetime.utcnow().isoformat())
        )

    # Note: do not commit here if db was provided from outer transaction;
    # commit should be done by the caller (create_order). If this function
    # was called standalone (with no outer transaction), caller must commit.
    return True


# GET ORDERS
def get_orders(restaurant_id, limit=100):
    db = get_db()
    return db.execute(
        """
        SELECT *
        FROM orders
        WHERE restaurant_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (restaurant_id, limit)
    ).fetchall()


# GET ORDER BY ID (helper)
def get_order_by_id(order_id, restaurant_id=None):
    db = get_db()
    if restaurant_id:
        return db.execute(
            "SELECT * FROM orders WHERE id=? AND restaurant_id=?",
            (order_id, restaurant_id)
        ).fetchone()
    else:
        return db.execute(
            "SELECT * FROM orders WHERE id=?",
            (order_id,)
        ).fetchone()