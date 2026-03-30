import re
from dataclasses import dataclass
from typing import List, Optional

from app.exceptions import ValidationError

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _required_string(data, key, *, label, max_length=None):
    value = (data.get(key) or "").strip()
    if not value:
        raise ValidationError(f"{label} is required.")
    if max_length and len(value) > max_length:
        raise ValidationError(f"{label} must be {max_length} characters or fewer.")
    return value


def _optional_string(data, key, *, max_length=None):
    value = (data.get(key) or "").strip()
    if not value:
        return None
    if max_length and len(value) > max_length:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be {max_length} characters or fewer.")
    return value


def _required_int(data, key, *, label, minimum=None):
    raw = data.get(key)
    if raw in (None, ""):
        raise ValidationError(f"{label} is required.")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def _required_float(data, key, *, label, minimum=None):
    raw = data.get(key)
    if raw in (None, ""):
        raise ValidationError(f"{label} is required.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a number.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def _optional_float(data, key, *, label, minimum=None):
    raw = data.get(key)
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a number.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def _optional_int(data, key, *, label, minimum=None):
    raw = data.get(key)
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def _choice(data, key, *, label, choices, default=None):
    value = (data.get(key) or default or "").strip().lower()
    if value not in choices:
        raise ValidationError(f"{label} must be one of: {', '.join(choices)}.")
    return value


def _email(data, key, *, required=False):
    value = (data.get(key) or "").strip().lower()
    if not value:
        if required:
            raise ValidationError("Email is required.")
        return None
    if not EMAIL_PATTERN.match(value):
        raise ValidationError("Email address is not valid.")
    return value


@dataclass
class CreateRestaurantInput:
    name: str
    address: Optional[str]


@dataclass
class RegisterInput:
    username: str
    password: str
    restaurant_id: int
    email: Optional[str]
    requested_role: Optional[str]


@dataclass
class LoginInput:
    username: str
    password: str


@dataclass
class MenuItemInput:
    name: str
    price: float
    category: str
    description: Optional[str]
    inventory_item_id: Optional[int]
    inventory_quantity: Optional[float]


@dataclass
class MenuCategoryInput:
    name: str


@dataclass
class InventoryItemInput:
    name: str
    stock: float
    unit: str
    cost: Optional[float]


@dataclass
class PosOrderInput:
    table_number: int
    line_items: List[dict]
    note: Optional[str]


@dataclass
class OrderStatusInput:
    status: str


@dataclass
class TableStatusInput:
    status: str


@dataclass
class TableBatchInput:
    starting_at: Optional[int]
    count: int


@dataclass
class TeamInvitationInput:
    email: str
    role: str


@dataclass
class MemberRoleInput:
    role: str


@dataclass
class AcceptInviteInput:
    username: str
    password: str


@dataclass
class BillingPaymentSubmissionInput:
    payment_reference: str


def validate_create_restaurant_input(data):
    return CreateRestaurantInput(
        name=_required_string(data, "name", label="Restaurant name", max_length=120),
        address=_optional_string(data, "address", max_length=255),
    )


def validate_register_input(data):
    return RegisterInput(
        username=_required_string(data, "username", label="Username", max_length=100),
        password=_required_string(data, "password", label="Password", max_length=255),
        restaurant_id=_required_int(data, "restaurant_id", label="Restaurant", minimum=1),
        email=_email(data, "email"),
        requested_role=(data.get("role") or "").strip().lower() or None,
    )


def validate_login_input(data):
    return LoginInput(
        username=_required_string(data, "username", label="Username", max_length=100),
        password=_required_string(data, "password", label="Password", max_length=255),
    )


def validate_menu_item_input(data):
    return MenuItemInput(
        name=_required_string(data, "name", label="Dish name", max_length=150),
        price=_required_float(data, "price", label="Price", minimum=0),
        category=_required_string(data, "category", label="Category", max_length=80).lower(),
        description=_optional_string(data, "description", max_length=255),
        inventory_item_id=_optional_int(data, "inventory_item_id", label="Inventory item", minimum=1),
        inventory_quantity=_optional_float(data, "inventory_quantity", label="Inventory quantity", minimum=0),
    )


def validate_menu_category_input(data):
    return MenuCategoryInput(
        name=_required_string(data, "name", label="Category name", max_length=80).lower(),
    )


def validate_inventory_item_input(data):
    return InventoryItemInput(
        name=_required_string(data, "name", label="Inventory item name", max_length=120),
        stock=_required_float(data, "stock", label="Stock", minimum=0),
        unit=_optional_string(data, "unit", max_length=40) or "unit",
        cost=_optional_float(data, "cost", label="Unit cost", minimum=0),
    )


def validate_add_to_cart_input(data):
    return {
        "food_id": _required_int(data, "food_id", label="Dish", minimum=1),
        "table_number": _required_int(data, "table", label="Table", minimum=1),
        "restaurant_id": _required_int(data, "restaurant_id", label="Restaurant", minimum=1),
    }


def validate_checkout_input(data):
    return {
        "table_number": _required_int(data, "table", label="Table", minimum=1),
        "restaurant_id": _required_int(data, "restaurant_id", label="Restaurant", minimum=1),
        "note": _optional_string(data, "note", max_length=255),
    }


def validate_pos_order_input(data):
    table_number = _required_int(data, "table_number", label="Table", minimum=1)
    food_ids = data.getlist("food_id") if hasattr(data, "getlist") else data.get("food_id", [])
    quantities = data.getlist("quantity") if hasattr(data, "getlist") else data.get("quantity", [])
    line_items = []
    for food_id, quantity in zip(food_ids, quantities):
        if food_id in (None, "") and quantity in (None, ""):
            continue
        try:
            normalized_food_id = int(food_id)
            normalized_quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError("Each ticket line needs a valid menu item and quantity.")
        if normalized_food_id < 1 or normalized_quantity < 1:
            raise ValidationError("Each ticket line must use a valid menu item and quantity greater than zero.")
        line_items.append(
            {
                "food_id": normalized_food_id,
                "quantity": normalized_quantity,
            }
        )
    if not line_items:
        raise ValidationError("Add at least one menu item to create a ticket.")
    return PosOrderInput(
        table_number=table_number,
        line_items=line_items,
        note=_optional_string(data, "note", max_length=255),
    )


def validate_order_status_input(data, *, allowed_statuses):
    return OrderStatusInput(
        status=_choice(data, "status", label="Order status", choices=allowed_statuses),
    )


def validate_table_status_input(data, *, allowed_statuses):
    return TableStatusInput(
        status=_choice(data, "status", label="Table status", choices=allowed_statuses),
    )


def validate_table_batch_input(data):
    return TableBatchInput(
        starting_at=_optional_int(data, "starting_at", label="Starting table number", minimum=1),
        count=_required_int(data, "count", label="Table count", minimum=1),
    )


def validate_team_invitation_input(data, *, allowed_roles):
    return TeamInvitationInput(
        email=_email(data, "email", required=True),
        role=_choice(data, "role", label="Role", choices=allowed_roles),
    )


def validate_member_role_input(data, *, allowed_roles):
    return MemberRoleInput(
        role=_choice(data, "role", label="Role", choices=allowed_roles),
    )


def validate_accept_invite_input(data):
    return AcceptInviteInput(
        username=_required_string(data, "username", label="Username", max_length=100),
        password=_required_string(data, "password", label="Password", max_length=255),
    )


def validate_billing_payment_submission_input(data):
    return BillingPaymentSubmissionInput(
        payment_reference=_required_string(data, "payment_reference", label="Payment reference", max_length=120),
    )
