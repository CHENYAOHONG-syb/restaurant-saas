from services.db import get_db

def get_restaurant_stats(restaurant_id):

    db = get_db()

    total_orders = db.execute(
        "SELECT COUNT(*) as count FROM orders WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchone()["count"]

    revenue = db.execute("""
        SELECT SUM(menu.price * order_items.qty) as total
        FROM orders
        JOIN order_items ON orders.id = order_items.order_id
        JOIN menu ON order_items.food_id = menu.id
        WHERE orders.restaurant_id=? AND orders.status='done'
    """,(restaurant_id,)).fetchone()["total"]

    return {
        "orders": total_orders,
        "revenue": revenue
    }
    
def most_popular_food(restaurant_id):
    
    db = get_db()

    food = db.execute("""
    SELECT menu.name, COUNT(order_items.id) as total
    FROM order_items
    JOIN orders ON order_items.order_id = orders.id
    JOIN menu ON order_items.food_id = menu.id
    WHERE orders.restaurant_id=?
    GROUP BY menu.id
    ORDER BY total DESC
    LIMIT 1
    """,(restaurant_id,)).fetchone()

    return food

def worst_food(restaurant_id):
    
    db = get_db()

    food = db.execute("""
    SELECT menu.name, COUNT(order_items.id) as total
    FROM order_items
    JOIN orders ON order_items.order_id = orders.id
    JOIN menu ON order_items.food_id = menu.id
    WHERE orders.restaurant_id=?
    GROUP BY menu.id
    ORDER BY total ASC
    LIMIT 1
    """,(restaurant_id,)).fetchone()

    return food

def peak_hour(restaurant_id):
    
    db = get_db()

    hour = db.execute("""
    SELECT strftime('%H', created_at) as hour,
    COUNT(*) as total
    FROM orders
    WHERE restaurant_id=?
    GROUP BY hour
    ORDER BY total DESC
    LIMIT 1
    """,(restaurant_id,)).fetchone()

    return hour

def average_order_value(restaurant_id):
    
    db = get_db()

    avg = db.execute("""
    SELECT AVG(total) as avg_value
    FROM orders
    WHERE restaurant_id=? AND status='done'
    """,(restaurant_id,)).fetchone()

    return avg