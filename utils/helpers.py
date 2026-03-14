from flask_login import current_user

def tenant_filter(query):
    return query.filter_by(
        restaurant_id=current_user.restaurant_id
    )