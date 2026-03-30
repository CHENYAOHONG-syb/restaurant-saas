import os

from flask import Flask, jsonify, render_template, request
from flask_login import LoginManager

from app.exceptions import AppError
from config import Config, normalize_database_url
from app.extensions import db, jwt, migrate
from app.models.user import User


def create_app(test_config=None):
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    flask_app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=template_dir,
        static_folder=static_dir,
    )
    flask_app.config.from_object(Config)
    if test_config:
        flask_app.config.update(test_config)

    instance_dir = os.path.join(base_dir, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, "database.db")

    configured_database_url = normalize_database_url(flask_app.config.get("SQLALCHEMY_DATABASE_URI"))
    if configured_database_url:
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = configured_database_url
    else:
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(flask_app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    db.init_app(flask_app)
    jwt.init_app(flask_app)
    if migrate:
        migrate.init_app(flask_app, db)

    import app.models  # noqa: F401

    from app.routes.admin import admin
    from app.routes.auth import auth
    from app.routes.menu import menu
    from app.routes.orders import orders
    from app.routes.platform import platform

    flask_app.register_blueprint(platform)
    flask_app.register_blueprint(auth, url_prefix="/auth")
    flask_app.register_blueprint(menu, url_prefix="/menu")
    flask_app.register_blueprint(orders, url_prefix="/orders")
    flask_app.register_blueprint(admin)

    @flask_app.errorhandler(AppError)
    def handle_app_error(error):
        if request.is_json or request.path.startswith("/admin/kitchen/"):
            return jsonify({"error": error.message, "type": error.__class__.__name__}), error.status_code
        return (
            render_template(
                "error.html",
                error_title="Something needs attention",
                error_message=error.message,
                error_status=error.status_code,
            ),
            error.status_code,
        )

    return flask_app
