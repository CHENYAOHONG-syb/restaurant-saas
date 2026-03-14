from services.db import get_db
from werkzeug.utils import secure_filename
import os
import uuid

def get_menu(restaurant_id):

    db = get_db()

    return db.execute(
        "SELECT * FROM menu WHERE restaurant_id=?",
        (restaurant_id,)
    ).fetchall()


def create_food(request):

    name = request.form["name"]
    price = float(request.form["price"])
    category = request.form["category"]
    restaurant_id = request.form["restaurant_id"]

    image = request.files.get("image")

    path = ""

    if image and image.filename != "":

        filename = str(uuid.uuid4()) + "_" + secure_filename(image.filename)

        os.makedirs("static/uploads", exist_ok=True)

        path = "static/uploads/" + filename

        image.save(path)

    db = get_db()

    db.execute(
        """
        INSERT INTO menu (restaurant_id,name,price,category,image)
        VALUES (?,?,?,?,?)
        """,
        (restaurant_id,name,price,category,path)
    )

    db.commit()