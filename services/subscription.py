from services.db import get_db
from datetime import datetime

def check_subscription(restaurant_id):

    db = get_db()

    sub = db.execute(
    "SELECT * FROM subscriptions WHERE restaurant_id=?",
    (restaurant_id,)
    ).fetchone()

    if not sub:
        return False

    if sub["status"] != "active":
        return False

    if sub["expires_at"]:

        exp = datetime.fromisoformat(sub["expires_at"])

        if exp < datetime.now():
            return False

    return True