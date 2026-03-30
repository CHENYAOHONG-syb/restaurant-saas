from app.extensions import db


class TeamInvitation(db.Model):
    __tablename__ = "team_invitations"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="staff")
    token = db.Column(db.String(255), nullable=False, unique=True)
    status = db.Column(db.String(50), nullable=False, default="pending")
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    accepted_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
