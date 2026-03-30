from werkzeug.utils import secure_filename

from app.exceptions import ValidationError
from app.extensions import db
from app.models.restaurant import Restaurant


def create_restaurant(name, address=None):
    if not (name or "").strip():
        raise ValidationError("Restaurant name is required.")

    base_slug = secure_filename(name or "restaurant").replace("_", "-").lower() or "restaurant"
    slug = base_slug
    suffix = 1

    while Restaurant.query.filter_by(slug=slug).first():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    restaurant = Restaurant(
        name=name,
        address=address,
        slug=slug,
    )

    db.session.add(restaurant)
    db.session.commit()

    return restaurant
