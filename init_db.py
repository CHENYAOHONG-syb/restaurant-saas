from app import create_app
from app.extensions import db

# 🔥 强制加载所有 models（关键！）
from app.models.menu import Menu
from app.models.user import User
from app.models.restaurant import Restaurant
from app.models.order import Order
from app.models.order_item import OrderItem

app = create_app()

with app.app_context():
    db.drop_all()   # 🔥 先清掉
    db.create_all() # 🔥 再重建

    print("Database created!")