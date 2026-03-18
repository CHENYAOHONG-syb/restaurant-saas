import os
from flask import Flask
from app.extensions import db, jwt

def create_app():
    flask_app = Flask(__name__, instance_relative_config=True)

    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    db_path = os.path.join(BASE_DIR, "instance", "database.db")

    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(flask_app)
    jwt.init_app(flask_app)

    import app.models

    from app.routes.menu import menu
    flask_app.register_blueprint(menu, url_prefix="/menu")

    return flask_app
