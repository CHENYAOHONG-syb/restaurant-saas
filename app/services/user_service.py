from werkzeug.security import generate_password_hash, check_password_hash
from app.models.user import User
from app import db


def create_user(email, password):

    hashed_password = generate_password_hash(password)

    user = User(
        email=email,
        password=hashed_password
    )

    db.session.add(user)
    db.session.commit()

    return user


def authenticate(email, password):

    user = User.query.filter_by(email=email).first()

    if not user:
        return None

    if check_password_hash(user.password, password):
        return user

    return None