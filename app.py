from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    return redirect("/restaurant/1?table=1")


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


@app.route("/order", methods=["POST"])
def order():

    food_id = request.form["food_id"]
    table = request.form["table"]
    restaurant_id = request.form["restaurant_id"]

    db = get_db()

    db.execute(
        "INSERT INTO orders (restaurant_id,food_id,table_number,status) VALUES (?,?,?,?)",
        (restaurant_id,food_id,table,"pending")
    )

    db.commit()

    return redirect(f"/restaurant/{restaurant_id}?table={table}")


@app.route("/kitchen/<int:restaurant_id>")
def kitchen(restaurant_id):
    return render_template("kitchen.html", restaurant_id=restaurant_id)


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


@app.route("/done/<int:order_id>", methods=["POST"])
def done(order_id):

    db = get_db()

    db.execute(
        "UPDATE orders SET status='done' WHERE id=?",
        (order_id,)
    )

    db.commit()

    return redirect(request.referrer)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
