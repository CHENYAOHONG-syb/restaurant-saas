from flask import Blueprint, render_template, request, redirect, session
from services.db import get_db
import os
from werkzeug.utils import secure_filename
from services.subscription import check_subscription
from utils.security import login_required
import uuid

admin = Blueprint("admin", __name__)


@admin.route("/admin/menu/<int:restaurant_id>")
@login_required
def admin_menu(restaurant_id):

    if not check_subscription(restaurant_id):
        return "Subscription expired"

    db = get_db()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin_menu.html",
        foods=foods,
        restaurant_id=restaurant_id
    )
    
@admin.route("/add_food", methods=["POST"])
@login_required
def add_food():

    name = request.form["name"]
    price = float(request.form["price"])
    category = request.form["category"]
    restaurant_id = request.form["restaurant_id"]

    image = request.files.get("image")

    filename = ""

    if image and image.filename != "":
      filename = secure_filename(image.filename)

      os.makedirs("static/uploads", exist_ok=True)

      path = "static/uploads/" + filename

      image.save(path)

    else:
       path = ""

    db = get_db()

    db.execute(
        """
        INSERT INTO menu (restaurant_id,name,price,category,image)
        VALUES (?,?,?,?,?)
        """,
        (restaurant_id,name,price,category,path)
    )

    db.commit()

    return redirect(f"/admin/menu/{restaurant_id}")

@admin.route("/delete_food/<int:food_id>", methods=["POST"])
@login_required
def delete_food(food_id):

    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
        "DELETE FROM menu WHERE id=? AND restaurant_id=?",
        (food_id, restaurant_id)
    )

    db.commit()

    return redirect(request.referrer)
    
@admin.route("/edit_food/<int:food_id>", methods=["GET","POST"])
@login_required
def edit_food(food_id):

    db = get_db()

    food = db.execute(
        "SELECT * FROM menu WHERE id=?",
        (food_id,)
    ).fetchone()

    if request.method == "POST":

        name = request.form["name"]
        price = float(request.form["price"])
        category = request.form["category"]

        image = request.files.get("image")

        if image and image.filename != "":

            filename = str(uuid.uuid4()) + "_" + secure_filename(image.filename)

            os.makedirs("static/uploads", exist_ok=True)

            path = "static/uploads/" + filename

            image.save(path)

            db.execute(
                "UPDATE menu SET image=? WHERE id=?",
                (path,food_id)
            )

        db.execute(
        """
        UPDATE menu
        SET name=?, price=?, category=?
        WHERE id=?
        """,
        (name,price,category,food_id)
        )

        db.commit()

        return redirect(request.referrer)

    return render_template(
        "edit_food.html",
        food=food
    )
    
@admin.route("/admin/categories/<int:restaurant_id>")
@login_required
def categories(restaurant_id):

    db = get_db()

    categories = db.execute(
        "SELECT * FROM categories WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin_categories.html",
        categories=categories,
        restaurant_id=restaurant_id
    )

@admin.route("/add_category", methods=["POST"])
@login_required
def add_category():

    name = request.form["name"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
    "INSERT INTO categories (restaurant_id,name) VALUES (?,?)",
    (restaurant_id,name)
    )

    db.commit()

    return redirect(request.referrer)

@admin.route("/delete_category/<int:cat_id>", methods=["POST"])
@login_required
def delete_category(cat_id):

    db = get_db()

    db.execute(
    "DELETE FROM categories WHERE id=?",
    (cat_id,)
    )

    db.commit()

    return redirect(request.referrer)

@admin.route("/admin/inventory/<int:restaurant_id>")
@login_required
def inventory(restaurant_id):

    db = get_db()

    items = db.execute(
        "SELECT * FROM inventory WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin_inventory.html",
        items=items,
        restaurant_id=restaurant_id
    )
    
@admin.route("/add_inventory", methods=["POST"])
@login_required
def add_inventory():

    name = request.form["name"]
    stock = request.form["stock"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
    """
    INSERT INTO inventory
    (restaurant_id,name,stock)
    VALUES (?,?,?)
    """,
    (restaurant_id,name,stock)
    )

    db.commit()

    return redirect(request.referrer)

@admin.route("/admin/settings/<int:restaurant_id>", methods=["GET","POST"])
@login_required
def settings(restaurant_id):

    db = get_db()

    restaurant = db.execute(
        "SELECT * FROM restaurants WHERE id=?",
        (restaurant_id,)
    ).fetchone()

    if request.method == "POST":
    
      name = request.form["name"]
      theme_color = request.form["theme_color"]

      db.execute(
        """
        UPDATE restaurants
        SET name=?, theme_color=?
        WHERE id=?
        """,
        (name, theme_color, restaurant_id)
      )

    logo = request.files.get("logo")

    if logo and logo.filename != "":
        filename = secure_filename(logo.filename)

        os.makedirs("static/uploads", exist_ok=True)

        path = "static/uploads/" + filename

        logo.save(path)

        db.execute(
            "UPDATE restaurants SET logo=? WHERE id=?",
            (path, restaurant_id)
        )

        db.commit()

        return redirect(request.referrer)

    return render_template(
    "admin_settings.html",
    restaurant=restaurant
    )
    
@admin.route("/admin/orders/<int:restaurant_id>")
@login_required
def admin_orders(restaurant_id):

    db = get_db()

    orders = db.execute(
        """
        SELECT *
        FROM orders
        WHERE restaurant_id=?
        ORDER BY created_at DESC
        """,
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin_orders.html",
        orders=orders,
        restaurant_id=restaurant_id
    )
    
@admin.route("/update_order/<int:order_id>", methods=["POST"])
@login_required
def update_order(order_id):

    status = request.form["status"]

    db = get_db()

    db.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status,order_id)
    )

    db.commit()

    return redirect(request.referrer)
    
@admin.route("/admin/order/<int:order_id>")
@login_required
def order_detail(order_id):

    db = get_db()

    order = db.execute(
        "SELECT * FROM orders WHERE id=?",
        (order_id,)
    ).fetchone()

    items = db.execute(
        """
        SELECT order_items.*, menu.name, menu.price
        FROM order_items
        JOIN menu
        ON order_items.food_id = menu.id
        WHERE order_items.order_id=?
        """,
        (order_id,)
    ).fetchall()

    return render_template(
        "order_detail.html",
        order=order,
        items=items
    )