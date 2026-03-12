from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import os

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# MENU PAGE
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


# CART PAGE
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


# CHECKOUT
@app.route("/checkout", methods=["POST"])
def checkout():

    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    items = db.execute(
        "SELECT * FROM cart WHERE table_number=?",
        (table,)
    ).fetchall()

    for item in items:

        db.execute(
            "INSERT INTO orders (restaurant_id,food_id,table_number,status) VALUES (?,?,?,?)",
            (restaurant_id,item["food_id"],table,"pending")
        )

    db.execute(
        "DELETE FROM cart WHERE table_number=?",
        (table,)
    )

    db.commit()

    return redirect(f"/restaurant/{restaurant_id}?table={table}")


# KITCHEN SCREEN
@app.route("/kitchen/<int:restaurant_id>")
def kitchen(restaurant_id):

    return render_template(
        "kitchen.html",
        restaurant_id=restaurant_id
    )


# API FOR KITCHEN AUTO REFRESH
@app.route("/api/orders/<int:restaurant_id>")
def api_orders(restaurant_id):

    db = get_db()

    orders = db.execute("""
        SELECT orders.id, menu.name, orders.table_number
        FROM orders
        JOIN menu ON orders.food_id = menu.id
        WHERE orders.restaurant_id=? AND orders.status='pending'
    """,(restaurant_id,)).fetchall()

    result=[]

    for order in orders:

        result.append({
            "id":order["id"],
            "name":order["name"],
            "table":order["table_number"]
        })

    return {"orders":result}


# MARK ORDER DONE
@app.route("/done/<int:order_id>", methods=["POST"])
def done(order_id):

    db = get_db()

    db.execute(
        "UPDATE orders SET status='done' WHERE id=?",
        (order_id,)
    )

    db.commit()

    return redirect(request.referrer)


# DASHBOARD REDIRECT
@app.route("/dashboard")
def dashboard_redirect():
    return redirect("/dashboard/1")

# DASHBOARD PAGE
@app.route("/dashboard/<int:restaurant_id>")
def dashboard(restaurant_id):

    db = get_db()

    total_orders = db.execute(
        "SELECT COUNT(*) as count FROM orders WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchone()["count"]

    total_sales = db.execute("""
        SELECT SUM(menu.price) as total
        FROM orders
        JOIN menu ON orders.food_id = menu.id
        WHERE orders.restaurant_id=? AND orders.status='done'
    """,(restaurant_id,)).fetchone()["total"]

    return render_template(
        "dashboard.html",
        total_orders=total_orders,
        total_sales=total_sales
    )


# ADMIN PANEL
@app.route("/admin/<int:restaurant_id>")
def admin(restaurant_id):

    db = get_db()

    foods = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()

    return render_template(
        "admin.html",
        foods=foods,
        restaurant_id=restaurant_id
    )


# ADD MENU ITEM
@app.route("/add_food", methods=["POST"])
def add_food():

    name = request.form["name"]
    price = request.form["price"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
        "INSERT INTO menu (restaurant_id,name,price) VALUES (?,?,?)",
        (restaurant_id,name,price)
    )

    db.commit()

    return redirect(f"/admin/{restaurant_id}")


# LOGIN
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method=="POST":

        username=request.form["username"]
        password=request.form["password"]

        db=get_db()

        user=db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username,password)
        ).fetchone()

        if user:
            return redirect("/admin/1")

    return render_template("login.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
