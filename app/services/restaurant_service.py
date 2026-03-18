from app.extensions import db
from app.models.restaurant import Restaurant

def create_restaurant(name, address):

    restaurant = Restaurant(
        name=name,
        address=address
    )

    db.session.add(restaurant)
    db.session.commit()

    return restaurant