from app.extensions import db

class Table(db.Model):

    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)

    table_number = db.Column(db.Integer)

    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"))