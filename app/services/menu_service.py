from app.models.menu import Menu

def get_menu(restaurant_id):
    return Menu.query.filter_by(restaurant_id=restaurant_id).all()