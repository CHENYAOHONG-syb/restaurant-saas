from flask import url_for
from flask_login import current_user

from app.exceptions import NotFoundError, PermissionDeniedError
from app.services.tenant_service import get_restaurant

OWNER_ROLES = {"owner"}
OVERVIEW_ROLES = {"owner"}
OPERATIONS_ROLES = {"owner", "manager"}
DASHBOARD_ROLES = OPERATIONS_ROLES
MENU_ROLES = {"owner", "manager"}
ORDER_ROLES = {"owner", "manager", "staff", "cashier", "kitchen"}
POS_ROLES = {"owner", "manager", "cashier"}
KITCHEN_ROLES = {"owner", "manager", "staff", "kitchen"}
TABLE_ROLES = {"owner", "manager", "cashier", "staff"}
BILLING_ROLES = {"owner"}
TEAM_ROLES = {"owner"}
ALL_TEAM_ROLES = ("owner", "manager", "cashier", "staff", "kitchen")


def authorize_restaurant_access(restaurant_id, *, allowed_roles=None):
    if not getattr(current_user, "is_authenticated", False):
        raise PermissionDeniedError("Sign in to access this workspace.", status_code=401)

    if current_user.restaurant_id != restaurant_id:
        raise PermissionDeniedError("You do not have access to this restaurant workspace.")

    normalized_role = (getattr(current_user, "role", "") or "").strip().lower()
    if allowed_roles and normalized_role not in allowed_roles:
        raise PermissionDeniedError("Your role does not allow this action.")

    try:
        return get_restaurant(restaurant_id)
    except NotFoundError:
        raise


def current_user_role():
    return (getattr(current_user, "role", "") or "").strip().lower()


def landing_route_for_user(user):
    role = (getattr(user, "role", "") or "").strip().lower()
    restaurant_id = getattr(user, "restaurant_id", None)

    if not restaurant_id:
        return url_for("platform.home")
    if role in OWNER_ROLES:
        return url_for("admin.dashboard", restaurant_id=restaurant_id)
    if role == "manager":
        return url_for("admin.operations_workspace", restaurant_id=restaurant_id)
    if role == "cashier":
        return url_for("admin.pos_workspace", restaurant_id=restaurant_id)
    if role in {"staff", "kitchen"}:
        return url_for("admin.kitchen_workspace", restaurant_id=restaurant_id)
    return url_for("platform.home")
