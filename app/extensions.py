from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

try:
    from flask_migrate import Migrate
except ImportError:  # pragma: no cover
    Migrate = None


db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate() if Migrate else None
