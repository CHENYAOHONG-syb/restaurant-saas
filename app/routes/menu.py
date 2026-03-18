from flask import Blueprint, render_template
from app.models.menu import Menu

menu = Blueprint("menu", __name__)

@menu.route("/")
def show_menu():
    items = Menu.query.all()
    return render_template("menu.html", items=items)

