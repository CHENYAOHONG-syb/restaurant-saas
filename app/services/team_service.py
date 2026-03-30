import secrets
from datetime import datetime, timedelta

from sqlalchemy import or_

from app.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.extensions import db
from app.models.team_invitation import TeamInvitation
from app.models.user import User
from app.services.access_control import ALL_TEAM_ROLES
from app.services.pagination import paginate_query
from app.services.tenant_service import get_team_invitation_for_restaurant, get_team_member_for_restaurant

INVITABLE_ROLES = tuple(role for role in ALL_TEAM_ROLES if role != "owner")
ROLE_LABELS = {
    "owner": "Owner",
    "manager": "Manager",
    "cashier": "Cashier",
    "staff": "Service Staff",
    "kitchen": "Kitchen",
}


def list_team_members(restaurant_id):
    return (
        User.query.filter_by(restaurant_id=restaurant_id)
        .order_by(User.role.asc(), User.username.asc())
        .all()
    )


def list_team_members_page(
    restaurant_id,
    *,
    page=1,
    per_page=8,
    search=None,
    role=None,
    sort="role",
    direction="asc",
):
    base_query = User.query.filter_by(restaurant_id=restaurant_id)
    normalized_search = (search or "").strip()
    normalized_role = (role or "").strip().lower()
    normalized_direction = "desc" if direction == "desc" else "asc"

    if normalized_search:
        like = f"%{normalized_search}%"
        base_query = base_query.filter(
            or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.role.ilike(like),
            )
        )

    if normalized_role:
        base_query = base_query.filter(User.role == normalized_role)

    sort_map = {
        "username": User.username,
        "email": User.email,
        "role": User.role,
    }
    sort_column = sort_map.get(sort, User.role)
    ordered_query = base_query.order_by(
        sort_column.asc() if normalized_direction == "asc" else sort_column.desc(),
        User.username.asc(),
    )
    pagination = paginate_query(ordered_query, page=page, per_page=per_page)
    return {"items": pagination["items"], "pagination": pagination}


def list_team_invitations(restaurant_id):
    return (
        TeamInvitation.query.filter_by(restaurant_id=restaurant_id)
        .order_by(TeamInvitation.created_at.desc())
        .all()
    )


def list_team_invitations_page(
    restaurant_id,
    *,
    page=1,
    per_page=8,
    search=None,
    status=None,
    sort="created_at",
    direction="desc",
):
    base_query = TeamInvitation.query.filter_by(restaurant_id=restaurant_id)
    normalized_search = (search or "").strip()
    normalized_status = (status or "").strip().lower()
    normalized_direction = "asc" if direction == "asc" else "desc"

    if normalized_search:
        like = f"%{normalized_search}%"
        base_query = base_query.filter(
            or_(
                TeamInvitation.email.ilike(like),
                TeamInvitation.role.ilike(like),
                TeamInvitation.status.ilike(like),
                TeamInvitation.token.ilike(like),
            )
        )

    if normalized_status:
        base_query = base_query.filter(TeamInvitation.status == normalized_status)

    sort_map = {
        "created_at": TeamInvitation.created_at,
        "email": TeamInvitation.email,
        "role": TeamInvitation.role,
        "status": TeamInvitation.status,
    }
    sort_column = sort_map.get(sort, TeamInvitation.created_at)
    ordered_query = base_query.order_by(
        sort_column.asc() if normalized_direction == "asc" else sort_column.desc(),
        TeamInvitation.id.desc(),
    )
    pagination = paginate_query(ordered_query, page=page, per_page=per_page)
    return {"items": pagination["items"], "pagination": pagination}


def get_team_invitation(restaurant_id, invite_id):
    return get_team_invitation_for_restaurant(restaurant_id, invite_id)


def get_invitation_by_token(token):
    return TeamInvitation.query.filter_by(token=token).first()


def create_team_invitation(restaurant_id, *, email, role, invited_by_user_id):
    normalized_email = (email or "").strip().lower()
    normalized_role = (role or "").strip().lower()

    if not normalized_email:
        raise ValidationError("Team member email is required.")
    if normalized_role not in INVITABLE_ROLES:
        raise ValidationError("Choose a valid team role for the invitation.")
    if User.query.filter_by(email=normalized_email).first():
        raise BusinessRuleError("That email is already attached to an existing user.")

    invitation = TeamInvitation.query.filter_by(
        restaurant_id=restaurant_id,
        email=normalized_email,
        status="pending",
    ).first()
    if invitation is None:
        invitation = TeamInvitation(
            restaurant_id=restaurant_id,
            email=normalized_email,
            invited_by_user_id=invited_by_user_id,
            status="pending",
        )
        db.session.add(invitation)

    invitation.role = normalized_role
    invitation.token = secrets.token_urlsafe(24)
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    invitation.accepted_at = None
    invitation.accepted_user_id = None
    invitation.status = "pending"
    db.session.commit()
    return invitation


def revoke_team_invitation(invitation):
    invitation.status = "revoked"
    db.session.commit()
    return invitation


def accept_team_invitation(token, *, username, password_hash):
    invitation = get_invitation_by_token(token)
    if invitation is None:
        raise NotFoundError("That invitation link is invalid.")
    if invitation.status != "pending":
        raise BusinessRuleError("That invitation is no longer active.")
    if invitation.expires_at and invitation.expires_at < datetime.utcnow():
        invitation.status = "expired"
        db.session.commit()
        raise BusinessRuleError("That invitation has expired.")

    normalized_username = (username or "").strip()
    if not normalized_username:
        raise ValidationError("Username is required.")
    if User.query.filter_by(username=normalized_username).first():
        raise BusinessRuleError("Username already exists.")

    user = User(
        username=normalized_username,
        email=invitation.email,
        password=password_hash,
        role=invitation.role,
        restaurant_id=invitation.restaurant_id,
    )
    db.session.add(user)
    db.session.flush()

    invitation.status = "accepted"
    invitation.accepted_user_id = user.id
    invitation.accepted_at = datetime.utcnow()
    db.session.commit()
    return invitation, user


def update_team_member_role(restaurant_id, *, user_id, new_role, actor_id):
    normalized_role = (new_role or "").strip().lower()
    if normalized_role not in ALL_TEAM_ROLES:
        raise ValidationError("Choose a valid role.")

    member = get_team_member_for_restaurant(restaurant_id, user_id)
    if member.id == actor_id:
        raise BusinessRuleError("Update another team member from this screen to avoid locking yourself out.")
    if member.role == "owner" and normalized_role != "owner":
        owner_count = User.query.filter_by(restaurant_id=restaurant_id, role="owner").count()
        if owner_count <= 1:
            raise BusinessRuleError("Keep at least one owner on the workspace before changing this role.")

    member.role = normalized_role
    db.session.commit()
    return member
