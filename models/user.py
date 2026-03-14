class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurants.id"),
        nullable=False
    )

    email = db.Column(db.String(120))
    password = db.Column(db.String(255))