from flask import Flask
import os

from services.db import close_db

from routes.platform import platform
from routes.auth import auth
from routes.orders import orders
from routes.dashboard import dashboard
from routes.admin import admin
from routes.menu import menu
from routes.inventory import inventory
from routes.kitchen_api import kitchen_api
from flask import render_template

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev")

# Blueprints
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(platform)

app.register_blueprint(menu, url_prefix="/menu")
app.register_blueprint(inventory, url_prefix="/inventory")

app.register_blueprint(orders)

app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(dashboard)

app.register_blueprint(kitchen_api)

# DB close
app.teardown_appcontext(close_db)

if __name__ == "__main__":
    app.run(debug=True)