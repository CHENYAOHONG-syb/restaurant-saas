from flask import Flask
import os

from extensions import db
from services.db import close_db

# Blueprints
from routes.platform import platform
from routes.auth import auth
from routes.orders import orders
from routes.dashboard import dashboard
from routes.admin import admin
from routes.menu import menu
from routes.inventory import inventory
from routes.kitchen_api import kitchen_api
from routes.cart import cart


app = Flask(__name__)

# Basic config
app.secret_key = os.environ.get("SECRET_KEY", "dev")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Init database
db.init_app(app)

# Register blueprints
app.register_blueprint(platform)

app.register_blueprint(auth, url_prefix="/auth")

app.register_blueprint(menu, url_prefix="/menu")
app.register_blueprint(inventory, url_prefix="/inventory")

app.register_blueprint(orders)
app.register_blueprint(cart)

app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(dashboard)

app.register_blueprint(kitchen_api)

# Close DB connection
app.teardown_appcontext(close_db)


if __name__ == "__main__":
    app.run(debug=True)