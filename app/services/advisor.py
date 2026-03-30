from app.services.analytics_service import (
    most_popular_food,
    worst_food,
    peak_hour,
    average_order_value
)

def generate_advice(restaurant_id):

    advice = []

    popular = most_popular_food(restaurant_id)
    worst = worst_food(restaurant_id)
    peak = peak_hour(restaurant_id)
    avg = average_order_value(restaurant_id)

    if popular:
        advice.append(
        f"{popular['name']} is very popular. Consider increasing price."
        )

    if worst and worst["total"] < 5:
        advice.append(
        f"{worst['name']} sells poorly. Consider removing it."
        )

    if peak:
        advice.append(
        f"Peak hour is {peak['hour']}:00. Prepare more staff."
        )

    if avg and avg["avg_value"]:
        if avg["avg_value"] < 15:
            advice.append(
            "Average order value is low. Consider combo meals."
            )

    return advice
