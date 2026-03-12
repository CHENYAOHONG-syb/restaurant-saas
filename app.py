from flask import Flask, render_template, request, redirect, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import stripe

app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE = "database.db"

stripe.api_key = "YOUR_STRIPE_SECRET_KEY"


# DATABASE
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# REGISTER
@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        hashed = generate_password_hash(password)

        db = get_db()

        db.execute(
            "INSERT INTO users (username,password) VALUES (?,?)",
            (username, hashed)
        )

        db.commit()

        return redirect("/login")

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]

            return redirect("/dashboard/1")

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# HOME
@app.route("/")
def home():

    db = get_db()

    restaurants = db.execute(
        "SELECT * FROM restaurants"
    ).fetchall()

    return render_template(
        "restaurants.html",
        restaurants=restaurants
    )


# MENU
@app.route("/restaurant/<int:restaurant_id>")
def menu(restaurant_id):

    table = request.args.get("table", "1")

    db = get_db()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "menu.html",
        foods=foods,
        table=table,
        restaurant_id=restaurant_id
    )


# ADD TO CART
@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():

    food_id = request.form["food_id"]
    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
        "INSERT INTO cart (food_id, table_number) VALUES (?,?)",
        (food_id, table)
    )

    db.commit()

    return redirect(f"/cart?table={table}&restaurant_id={restaurant_id}")


# CART
@app.route("/cart")
def cart():

    table = request.args.get("table")
    restaurant_id = request.args.get("restaurant_id")

    db = get_db()

    cart = db.execute("""
        SELECT cart.id, menu.name, menu.price
        FROM cart
        JOIN menu ON cart.food_id = menu.id
        WHERE cart.table_number=?
    """,(table,)).fetchall()

    total = sum(item["price"] for item in cart)

    return render_template(
        "cart.html",
        cart=cart,
        total=total,
        table=table,
        restaurant_id=restaurant_id
    )


# KITCHEN
@app.route("/kitchen/<int:restaurant_id>")
def kitchen(restaurant_id):

    return render_template(
        "kitchen.html",
        restaurant_id=restaurant_id
    )


# API ORDERS
@app.route("/api/orders/<int:restaurant_id>")
def api_orders(restaurant_id):

    db = get_db()

    rows = db.execute("""
        SELECT
        orders.id as order_id,
        orders.table_number,
        menu.name,
        order_items.qty
        FROM orders
        JOIN order_items ON orders.id = order_items.order_id
        JOIN menu ON order_items.food_id = menu.id
        WHERE orders.restaurant_id=? 
        AND orders.status='pending'
    """,(restaurant_id,)).fetchall()

    grouped = {}

    for row in rows:

        order_id = row["order_id"]

        if order_id not in grouped:
            grouped[order_id] = {
                "order_id": order_id,
                "table": row["table_number"],
                "items": []
            }

        grouped[order_id]["items"].append({
            "name": row["name"],
            "qty": row["qty"]
        })

    return jsonify({"orders": list(grouped.values())})


# DONE ORDER
@app.route("/done/<int:order_id>", methods=["POST"])
def done(order_id):

    db = get_db()

    db.execute(
        "UPDATE orders SET status='done' WHERE id=?",
        (order_id,)
    )

    db.commit()

    return redirect(request.referrer)


# DASHBOARD
@app.route("/dashboard/<int:restaurant_id>")
def dashboard(restaurant_id):

    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    total_orders = db.execute(
        "SELECT COUNT(*) as count FROM orders WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchone()["count"]

    total_sales = db.execute("""
        SELECT SUM(menu.price) as total
        FROM orders
        JOIN order_items ON orders.id = order_items.order_id
        JOIN menu ON order_items.food_id = menu.id
        WHERE orders.restaurant_id=? AND orders.status='done'
    """,(restaurant_id,)).fetchone()["total"]

    if total_sales is None:
        total_sales = 0

    return render_template(
        "dashboard.html",
        total_orders=total_orders,
        total_sales=total_sales
    )


# POS
@app.route("/pos/<int:restaurant_id>")
def pos(restaurant_id):

    db = get_db()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "pos.html",
        foods=foods,
        restaurant_id=restaurant_id
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
