from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import create_access_token
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.exceptions import AppError, BusinessRuleError
from app.extensions import db
from app.models.user import User
from app.services.access_control import landing_route_for_user
from app.services.team_service import ROLE_LABELS, accept_team_invitation, get_invitation_by_token
from app.services.tenant_service import get_restaurant
from app.validation import validate_accept_invite_input, validate_login_input, validate_register_input

auth = Blueprint("auth", __name__)

PASSWORD_METHOD = "pbkdf2:sha256"
PUBLIC_REGISTRATION_ROLE = "owner"


def _restaurant_id_from_payload(data):
    raw_value = data.get("restaurant_id")
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


@auth.route("/register", methods=["GET", "POST"])
def register():
    from app.models.restaurant import Restaurant

    restaurants = Restaurant.query.order_by(Restaurant.name.asc()).all()
    selected_restaurant_id = request.args.get("restaurant_id", type=int)

    if request.method == "GET":
        return render_template(
            "register.html",
            restaurants=restaurants,
            selected_restaurant_id=selected_restaurant_id,
        )

    data = request.get_json(silent=True) or request.form
    form_data = {
        "username": (data.get("username") or "").strip(),
        "email": (data.get("email") or "").strip(),
    }
    try:
        payload = validate_register_input(data)
        if payload.requested_role and payload.requested_role != PUBLIC_REGISTRATION_ROLE:
            raise BusinessRuleError("Public registration only supports owner accounts")
        get_restaurant(payload.restaurant_id)
        if User.query.filter_by(username=payload.username).first():
            raise BusinessRuleError("Username already exists")
    except AppError as exc:
        if request.is_json:
            return jsonify({"error": exc.message}), exc.status_code
        return (
            render_template(
                "register.html",
                restaurants=restaurants,
                selected_restaurant_id=selected_restaurant_id or _restaurant_id_from_payload(data),
                error=exc.message,
                form_data=form_data,
            ),
            exc.status_code,
        )

    user = User(
        username=payload.username,
        password=generate_password_hash(payload.password, method=PASSWORD_METHOD),
        role=PUBLIC_REGISTRATION_ROLE,
        restaurant_id=payload.restaurant_id,
        email=payload.email,
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)

    if request.is_json:
        return jsonify({"message": "User created", "user_id": user.id}), 201

    flash("Owner account created. You're now signed in.", "success")
    return redirect(landing_route_for_user(user))


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    try:
        payload = validate_login_input(data)
    except AppError as exc:
        if request.is_json:
            return jsonify({"error": exc.message}), exc.status_code
        return render_template("login.html", error=exc.message, form_data={"username": username}), exc.status_code

    user = User.query.filter_by(username=payload.username).first()
    if not user or not check_password_hash(user.password, payload.password):
        error_payload = {"error": "Invalid credentials"}
        if request.is_json:
            return jsonify(error_payload), 401
        return render_template("login.html", error=error_payload["error"], form_data={"username": payload.username}), 401

    login_user(user)
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"restaurant_id": user.restaurant_id, "role": user.role},
    )

    if request.is_json:
        return jsonify({"access_token": token})

    flash(f"Welcome back, {user.username}.", "success")
    return redirect(landing_route_for_user(user))


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("platform.home"))


@auth.route("/accept-invite/<token>", methods=["GET", "POST"])
def accept_invite(token):
    invitation = get_invitation_by_token(token)
    if invitation is None:
        return render_template("accept_invite.html", error="That invitation link is invalid."), 404

    restaurant = get_restaurant(invitation.restaurant_id)
    if request.method == "GET":
        return render_template(
            "accept_invite.html",
            invitation=invitation,
            restaurant=restaurant,
            role_label=ROLE_LABELS.get(invitation.role, invitation.role.title()),
        )

    try:
        payload = validate_accept_invite_input(request.form)
        invitation, user = accept_team_invitation(
            token,
            username=payload.username,
            password_hash=generate_password_hash(payload.password, method=PASSWORD_METHOD),
        )
    except AppError as exc:
        refreshed_invitation = get_invitation_by_token(token) or invitation
        refreshed_restaurant = get_restaurant(refreshed_invitation.restaurant_id) if refreshed_invitation else restaurant
        return (
            render_template(
                "accept_invite.html",
                invitation=refreshed_invitation,
                restaurant=refreshed_restaurant,
                role_label=ROLE_LABELS.get(refreshed_invitation.role, refreshed_invitation.role.title()) if refreshed_invitation else None,
                error=str(exc),
                form_data={"username": (request.form.get("username") or "").strip()},
            ),
            400,
        )

    login_user(user)
    flash(f"Invitation accepted. You're signed in as {ROLE_LABELS.get(invitation.role, invitation.role.title())}.", "success")
    return redirect(landing_route_for_user(user))
