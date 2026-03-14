class Table(db.Model):
    
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id")
    )

    table_number = db.Column(db.Integer)