from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from services.db import get_db
import uuid

auth = Blueprint("auth", __name__)


@auth.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        existing = db.execute(
            "SELECT id FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if existing:
            return "Username already exists"

        hashed = generate_password_hash(password)

        db.execute(
            "INSERT INTO users (username,password) VALUES (?,?)",
            (username, hashed)
        )

        db.commit()

        return redirect("/login")

    return render_template("register.html")


@auth.route("/login", methods=["GET","POST"])
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

            restaurant = db.execute(
                "SELECT id FROM restaurants WHERE owner_id=?",
                (session["user_id"],)
            ).fetchone()

            if restaurant:
                return redirect(f"/dashboard/{restaurant['id']}")
            else:
                return redirect("/onboarding")

    return render_template("login.html")


@auth.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

@auth.route("/create_restaurant", methods=["GET","POST"])
def create_restaurant():

    if request.method=="POST":

        name=request.form["name"]

        slug = name.lower().replace(" ","-") + "-" + str(uuid.uuid4())[:6]

        db=get_db()

        db.execute(
        """
        INSERT INTO restaurants (name,slug,owner_id)
        VALUES (?,?,?)
        """,
        (name,slug,session["user_id"])
        )

        db.commit()

        if restaurant:
          return redirect(f"/dashboard/{restaurant['id']}")
        else:
          return redirect("/onboarding")

    return render_template("create_restaurant.html")

@auth.route("/onboarding", methods=["GET","POST"])
def onboarding():

    if request.method=="POST":

        name=request.form["name"]
        slug=request.form["slug"]

        db=get_db()

        db.execute(
        """
        INSERT INTO restaurants
        (name,slug,owner_id)
        VALUES (?,?,?)
        """,
        (name,slug,session["user_id"])
        )

        db.commit()

        restaurant=db.execute(
        "SELECT id FROM restaurants WHERE slug=?",
        (slug,)
        ).fetchone()

        return redirect(f"/admin/menu/{restaurant['id']}")

    return render_template("onboarding.html")
