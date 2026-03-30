from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app, url_for
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app.exceptions import ValidationError
from app.extensions import db
from app.models.billing_event import BillingEvent
from app.models.subscription import Subscription
from app.services.pagination import paginate_query

PLAN_CATALOG = {
    "starter": {
        "name": "Starter",
        "price": 0,
        "interval": "month",
        "description": "Best for pilots and demos: one location, guest ordering, and the core owner workflow.",
        "tagline": "Pilot the guest journey before you turn on paid rollout.",
        "highlights": [
            "One restaurant workspace with owner login",
            "Live guest ordering flow and order capture",
            "Manual billing mode for assisted onboarding",
        ],
        "stripe_price_env": "STRIPE_PRICE_STARTER",
    },
    "pro": {
        "name": "Pro",
        "price": 39,
        "interval": "month",
        "description": "Best for one live location running menu updates, live orders, and a real upgrade path.",
        "tagline": "The most credible first paid tier for a single live venue.",
        "highlights": [
            "Everything in Starter plus live menu operations",
            "Stripe checkout path for commercial upgrades",
            "Clean owner workflow for daily service",
        ],
        "featured": True,
        "stripe_price_env": "STRIPE_PRICE_PRO",
    },
    "growth": {
        "name": "Growth",
        "price": 99,
        "interval": "month",
        "description": "Best for expanding operators who want a stronger operations layer and room to add staff workflows.",
        "tagline": "Room to sell a broader operations story as locations grow.",
        "highlights": [
            "Stronger billing story for multi-location conversations",
            "More headroom for staff and kitchen workflow expansion",
            "Best fit when the owner wants one ops layer to scale",
        ],
        "stripe_price_env": "STRIPE_PRICE_GROWTH",
    },
}


class BillingConfigurationError(RuntimeError):
    pass


DUITNOW_MANUAL_PROVIDER = "duitnow_manual"
DEFAULT_DUITNOW_QR_ASSET = "images/duitnow/chen-yao-hong-tng-qr.jpg"
DEFAULT_DUITNOW_RECIPIENT_NAME = "CHEN YAO HONG"
DEFAULT_DUITNOW_ACCOUNT_TYPE = "Touch 'n Go eWallet"
PENDING_VERIFICATION_STATUS = "pending_verification"
BILLING_PROVIDER_LABELS = {
    "manual": "Manual",
    "stripe": "Stripe",
    DUITNOW_MANUAL_PROVIDER: "DuitNow Manual",
}


def list_plans():
    return PLAN_CATALOG


def current_billing_provider(subscription=None):
    provider = (current_app.config.get("BILLING_PROVIDER") or "manual").strip().lower()
    if provider in BILLING_PROVIDER_LABELS:
        return provider

    subscription_provider = (getattr(subscription, "billing_provider", None) or "").strip().lower()
    if subscription_provider in BILLING_PROVIDER_LABELS:
        return subscription_provider
    return "manual"


def get_billing_provider_label(provider_name=None):
    normalized = (provider_name or current_billing_provider()).strip().lower()
    return BILLING_PROVIDER_LABELS.get(normalized, "Manual")


def get_or_create_subscription(restaurant_id):
    subscription = Subscription.query.filter_by(restaurant_id=restaurant_id).first()
    if subscription:
        return subscription

    trial_days = current_app.config.get("TRIAL_DAYS", 14)
    subscription = Subscription(
        restaurant_id=restaurant_id,
        plan="starter",
        status="trialing",
        billing_provider=current_app.config.get("BILLING_PROVIDER", "manual"),
        trial_ends_at=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.session.add(subscription)
    db.session.commit()
    return subscription


def change_plan(restaurant_id, plan_key):
    if plan_key not in PLAN_CATALOG:
        raise ValidationError(f"Unknown plan: {plan_key}")

    subscription = get_or_create_subscription(restaurant_id)
    subscription.plan = plan_key
    subscription.status = "active" if plan_key != "starter" else "trialing"
    subscription.billing_provider = current_app.config.get("BILLING_PROVIDER", "manual")
    subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
    if plan_key != "starter":
        subscription.trial_ends_at = None
    subscription.cancel_at_period_end = False
    subscription.canceled_at = None
    db.session.commit()
    record_billing_event(
        restaurant_id=restaurant_id,
        event_type="manual.plan_changed",
        status=subscription.status,
        source="manual",
        summary=f"Plan changed to {PLAN_CATALOG[plan_key]['name']}.",
    )
    return subscription


def billing_provider_enabled(provider_name):
    provider = current_billing_provider()
    return provider == provider_name


def get_duitnow_payment_context(restaurant, plan_key):
    if plan_key not in PLAN_CATALOG:
        raise ValidationError(f"Unknown plan: {plan_key}")
    if plan_key == "starter":
        raise BillingConfigurationError("Starter plan does not require a DuitNow payment request.")
    if current_billing_provider() != DUITNOW_MANUAL_PROVIDER:
        raise BillingConfigurationError("DuitNow manual collection is not enabled for this workspace.")

    qr_image_url = (current_app.config.get("DUITNOW_QR_IMAGE_URL") or "").strip() or _default_duitnow_qr_url()
    recipient_name = (current_app.config.get("DUITNOW_RECIPIENT_NAME") or "").strip()
    if not recipient_name and qr_image_url:
        recipient_name = DEFAULT_DUITNOW_RECIPIENT_NAME
    account_id = (current_app.config.get("DUITNOW_ACCOUNT_ID") or "").strip()
    if not recipient_name:
        raise BillingConfigurationError("Missing DUITNOW_RECIPIENT_NAME for manual DuitNow billing.")
    if not account_id and not qr_image_url:
        raise BillingConfigurationError("Provide DUITNOW_ACCOUNT_ID or DUITNOW_QR_IMAGE_URL for manual DuitNow billing.")

    plan = PLAN_CATALOG[plan_key]
    amount_value = float(plan["price"])
    reference_prefix = (current_app.config.get("DUITNOW_REFERENCE_PREFIX") or "ROS").strip().upper() or "ROS"
    reference = f"{reference_prefix}-{restaurant.id}-{plan_key}".upper()
    note = (
        current_app.config.get("DUITNOW_PAYMENT_NOTE")
        or "After you complete the transfer, confirm payment with the restaurant admin team before switching plans."
    )

    return {
        "plan_key": plan_key,
        "plan_name": plan["name"],
        "amount_value": amount_value,
        "amount_display": _format_ringgit(amount_value),
        "reference": reference,
        "recipient_name": recipient_name,
        "account_id": account_id or None,
        "account_type": (
            (current_app.config.get("DUITNOW_ACCOUNT_TYPE") or "").strip()
            or (DEFAULT_DUITNOW_ACCOUNT_TYPE if qr_image_url and not account_id else "Merchant ID")
        ),
        "qr_image_url": qr_image_url or None,
        "note": note,
    }


def prepare_duitnow_payment_request(restaurant, plan_key):
    payment_context = get_duitnow_payment_context(restaurant, plan_key)
    record_billing_event(
        restaurant_id=restaurant.id,
        event_type="duitnow.instructions_requested",
        status="pending",
        source=DUITNOW_MANUAL_PROVIDER,
        summary=(
            f"DuitNow payment details opened for the {payment_context['plan_name']} plan. "
            f"Reference: {payment_context['reference']}."
        ),
        amount_cents=int(payment_context["amount_value"] * 100),
        currency="MYR",
        reference_url=payment_context["qr_image_url"],
    )
    return payment_context


def submit_duitnow_payment_submission(restaurant, plan_key, payment_reference, screenshot_file=None):
    payment_context = get_duitnow_payment_context(restaurant, plan_key)
    attachment_path = _save_billing_attachment(
        screenshot_file,
        restaurant_id=restaurant.id,
        payment_reference=payment_reference,
    )
    return record_billing_event(
        restaurant_id=restaurant.id,
        event_type="payment_submitted",
        status=PENDING_VERIFICATION_STATUS,
        source=DUITNOW_MANUAL_PROVIDER,
        summary=(
            f"Manual subscription payment submitted for the {payment_context['plan_name']} plan. "
            f"Reference: {payment_reference}."
        ),
        plan_key=plan_key,
        payment_reference=payment_reference,
        attachment_path=attachment_path,
        amount_cents=int(payment_context["amount_value"] * 100),
        currency="MYR",
    )


def latest_pending_verification(restaurant_id):
    return (
        BillingEvent.query.filter_by(
            restaurant_id=restaurant_id,
            source=DUITNOW_MANUAL_PROVIDER,
            status=PENDING_VERIFICATION_STATUS,
            event_type="payment_submitted",
        )
        .order_by(BillingEvent.occurred_at.desc(), BillingEvent.id.desc())
        .first()
    )


def serialize_payment_submission(event):
    if not event:
        return None
    plan_name = PLAN_CATALOG.get(event.plan_key, {}).get("name", (event.plan_key or "Plan").title())
    return {
        "plan_key": event.plan_key,
        "plan_name": plan_name,
        "amount_display": _format_amount_from_event(event),
        "payment_reference": event.payment_reference,
        "submitted_at": event.occurred_at,
        "status": event.status,
        "attachment_name": Path(event.attachment_path).name if event.attachment_path else None,
    }


def create_checkout_session(restaurant, subscription, plan_key):
    if plan_key not in PLAN_CATALOG:
        raise ValidationError(f"Unknown plan: {plan_key}")
    if plan_key == "starter":
        raise BillingConfigurationError("Starter plan does not require Stripe checkout.")

    stripe = _get_stripe_client()
    current_app.config.get("STRIPE_SECRET_KEY")

    success_url = current_app.config["SITE_URL"].rstrip("/") + url_for(
        "admin.billing_success",
        restaurant_id=restaurant.id,
    ) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = current_app.config["SITE_URL"].rstrip("/") + url_for(
        "admin.billing",
        restaurant_id=restaurant.id,
    )

    session = stripe.checkout.Session.create(
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(restaurant.id),
        customer=subscription.provider_customer_id or None,
        customer_email=None if subscription.provider_customer_id else _restaurant_billing_email(restaurant),
        metadata={
            "restaurant_id": str(restaurant.id),
            "plan_key": plan_key,
        },
        subscription_data={
            "metadata": {
                "restaurant_id": str(restaurant.id),
                "plan_key": plan_key,
            }
        },
        line_items=[_build_line_item(plan_key)],
    )
    return session


def create_customer_portal_session(restaurant, subscription):
    if not billing_provider_enabled("stripe"):
        raise BillingConfigurationError("Stripe billing mode is not enabled for this workspace.")
    if not subscription.provider_customer_id:
        raise BillingConfigurationError("No Stripe customer is attached yet. Complete a paid checkout first.")

    stripe = _get_stripe_client()
    return_url = current_app.config["SITE_URL"].rstrip("/") + url_for(
        "admin.billing",
        restaurant_id=restaurant.id,
    )

    return stripe.billing_portal.Session.create(
        customer=subscription.provider_customer_id,
        return_url=return_url,
    )


def cancel_subscription(restaurant, subscription):
    if subscription.billing_provider == "stripe" and subscription.provider_subscription_id:
        stripe = _get_stripe_client()
        stripe_subscription = stripe.Subscription.modify(
            subscription.provider_subscription_id,
            cancel_at_period_end=True,
        )
        _sync_from_subscription_object(stripe_subscription, canceled=False)
        subscription.cancel_at_period_end = True
        db.session.commit()
        record_billing_event(
            restaurant_id=restaurant.id,
            event_type="customer.subscription.cancel_requested",
            status=subscription.status,
            source="stripe",
            summary="Cancellation scheduled for the end of the current billing period.",
        )
        return subscription

    subscription.status = "canceled"
    subscription.cancel_at_period_end = False
    subscription.canceled_at = datetime.utcnow()
    subscription.current_period_end = datetime.utcnow()
    db.session.commit()
    record_billing_event(
        restaurant_id=restaurant.id,
        event_type="manual.subscription.canceled",
        status=subscription.status,
        source="manual",
        summary="Subscription canceled from the owner console.",
    )
    return subscription


def sync_subscription_from_checkout_session(restaurant_id, session_id):
    stripe = _get_stripe_client()
    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=["subscription", "customer"],
    )

    plan_key = session.get("metadata", {}).get("plan_key") or _plan_from_subscription_session(session)
    subscription = get_or_create_subscription(restaurant_id)
    subscription.plan = plan_key if plan_key in PLAN_CATALOG else subscription.plan
    subscription.status = "active"
    subscription.billing_provider = "stripe"
    subscription.provider_customer_id = _extract_id(session.get("customer"))
    subscription.provider_subscription_id = _extract_id(session.get("subscription"))

    stripe_subscription = session.get("subscription")
    period_end = _subscription_period_end(stripe_subscription)
    if period_end:
        subscription.current_period_end = period_end
    subscription.trial_ends_at = None
    subscription.cancel_at_period_end = False
    subscription.canceled_at = None
    db.session.commit()
    record_billing_event(
        restaurant_id=restaurant_id,
        event_type="checkout.session.completed",
        status=subscription.status,
        source="stripe",
        summary=f"Checkout completed for the {PLAN_CATALOG.get(subscription.plan, {}).get('name', subscription.plan)} plan.",
    )
    return subscription


def handle_webhook(payload, signature_header):
    stripe = _get_stripe_client()
    webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise BillingConfigurationError("Missing STRIPE_WEBHOOK_SECRET.")

    event = stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
    event_type = event.get("type")
    event_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        restaurant_id = _restaurant_id_from_metadata(event_object.get("metadata", {}))
        if restaurant_id:
            _sync_from_checkout_object(restaurant_id, event_object, provider_event_id=event.get("id"))
    elif event_type in {"customer.subscription.updated", "customer.subscription.created"}:
        _sync_from_subscription_object(event_object, canceled=False, provider_event_id=event.get("id"))
    elif event_type == "customer.subscription.deleted":
        _sync_from_subscription_object(event_object, canceled=True, provider_event_id=event.get("id"))
    elif event_type == "invoice.payment_failed":
        _sync_from_invoice_object(event_object, failed=True, provider_event_id=event.get("id"))
    elif event_type == "invoice.payment_succeeded":
        _sync_from_invoice_object(event_object, failed=False, provider_event_id=event.get("id"))

    return event


def list_billing_events(restaurant_id, limit=20):
    return (
        BillingEvent.query.filter_by(restaurant_id=restaurant_id)
        .order_by(BillingEvent.occurred_at.desc(), BillingEvent.id.desc())
        .limit(limit)
        .all()
    )


def list_billing_events_page(
    restaurant_id,
    *,
    page=1,
    per_page=10,
    search=None,
    source=None,
    status=None,
    sort="occurred_at",
    direction="desc",
):
    base_query = BillingEvent.query.filter_by(restaurant_id=restaurant_id)
    normalized_search = (search or "").strip()
    normalized_source = (source or "").strip().lower()
    normalized_status = (status or "").strip().lower()
    normalized_direction = "asc" if direction == "asc" else "desc"

    if normalized_search:
        like = f"%{normalized_search}%"
        base_query = base_query.filter(
            or_(
                BillingEvent.event_type.ilike(like),
                BillingEvent.summary.ilike(like),
                BillingEvent.provider_event_id.ilike(like),
                BillingEvent.plan_key.ilike(like),
                BillingEvent.payment_reference.ilike(like),
                BillingEvent.reference_url.ilike(like),
            )
        )

    if normalized_source:
        base_query = base_query.filter(BillingEvent.source == normalized_source)

    if normalized_status:
        base_query = base_query.filter(BillingEvent.status == normalized_status)

    sort_map = {
        "occurred_at": BillingEvent.occurred_at,
        "event_type": BillingEvent.event_type,
        "source": BillingEvent.source,
        "status": BillingEvent.status,
    }
    sort_column = sort_map.get(sort, BillingEvent.occurred_at)
    ordered_query = base_query.order_by(
        sort_column.asc() if normalized_direction == "asc" else sort_column.desc(),
        BillingEvent.id.desc(),
    )
    pagination = paginate_query(ordered_query, page=page, per_page=per_page)
    return {"items": pagination["items"], "pagination": pagination}


def latest_billing_issue(restaurant_id):
    failure_types = {"invoice.payment_failed", "customer.subscription.deleted", "manual.subscription.canceled"}
    return (
        BillingEvent.query.filter(
            BillingEvent.restaurant_id == restaurant_id,
            BillingEvent.event_type.in_(failure_types),
        )
        .order_by(BillingEvent.occurred_at.desc(), BillingEvent.id.desc())
        .first()
    )


def _get_stripe_client():
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover
        raise BillingConfigurationError("Stripe SDK is not installed. Run pip install -r requirements.txt.") from exc

    secret_key = current_app.config.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise BillingConfigurationError("Missing STRIPE_SECRET_KEY.")
    stripe.api_key = secret_key
    return stripe


def _sync_from_checkout_object(restaurant_id, session_object, provider_event_id=None):
    subscription = get_or_create_subscription(restaurant_id)
    plan_key = session_object.get("metadata", {}).get("plan_key")
    if plan_key in PLAN_CATALOG:
        subscription.plan = plan_key
    subscription.status = "active"
    subscription.billing_provider = "stripe"
    subscription.provider_customer_id = _extract_id(session_object.get("customer"))
    subscription.provider_subscription_id = _extract_id(session_object.get("subscription"))
    subscription.trial_ends_at = None
    subscription.cancel_at_period_end = False
    subscription.canceled_at = None
    db.session.commit()
    record_billing_event(
        restaurant_id=restaurant_id,
        event_type="checkout.session.completed",
        status=subscription.status,
        source="stripe",
        provider_event_id=provider_event_id,
        summary=f"Stripe checkout completed for the {PLAN_CATALOG.get(subscription.plan, {}).get('name', subscription.plan)} plan.",
    )
    return subscription


def _sync_from_subscription_object(subscription_object, canceled=False, provider_event_id=None):
    metadata = subscription_object.get("metadata", {})
    restaurant_id = _restaurant_id_from_metadata(metadata)
    provider_subscription_id = _extract_id(subscription_object)
    provider_customer_id = _extract_id(subscription_object.get("customer"))

    subscription = None
    if provider_subscription_id:
        subscription = Subscription.query.filter_by(provider_subscription_id=provider_subscription_id).first()
    if not subscription and provider_customer_id:
        subscription = Subscription.query.filter_by(provider_customer_id=provider_customer_id).first()
    if not subscription and restaurant_id:
        subscription = get_or_create_subscription(restaurant_id)
    if not subscription:
        return None

    plan_key = metadata.get("plan_key")
    if plan_key in PLAN_CATALOG:
        subscription.plan = plan_key

    subscription.billing_provider = "stripe"
    subscription.provider_customer_id = provider_customer_id or subscription.provider_customer_id
    subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
    subscription.current_period_end = _subscription_period_end(subscription_object)
    subscription.status = "canceled" if canceled else _status_from_subscription_object(subscription_object)
    subscription.cancel_at_period_end = _cancel_at_period_end(subscription_object)
    subscription.canceled_at = _subscription_canceled_at(subscription_object) if canceled or subscription.cancel_at_period_end else None
    subscription.trial_ends_at = None
    db.session.commit()
    record_billing_event(
        restaurant_id=subscription.restaurant_id,
        event_type="customer.subscription.deleted" if canceled else "customer.subscription.updated",
        status=subscription.status,
        source="stripe",
        provider_event_id=provider_event_id,
        summary=_subscription_event_summary(subscription, canceled=canceled),
    )
    return subscription


def _sync_from_invoice_object(invoice_object, *, failed, provider_event_id=None):
    provider_subscription_id = _extract_id(invoice_object.get("subscription"))
    provider_customer_id = _extract_id(invoice_object.get("customer"))
    subscription = None
    if provider_subscription_id:
        subscription = Subscription.query.filter_by(provider_subscription_id=provider_subscription_id).first()
    if not subscription and provider_customer_id:
        subscription = Subscription.query.filter_by(provider_customer_id=provider_customer_id).first()
    if not subscription:
        return None

    subscription.billing_provider = "stripe"
    subscription.provider_customer_id = provider_customer_id or subscription.provider_customer_id
    subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
    subscription.status = "past_due" if failed else "active"
    db.session.commit()
    amount_cents = invoice_object.get("amount_due") if failed else invoice_object.get("amount_paid")
    record_billing_event(
        restaurant_id=subscription.restaurant_id,
        event_type="invoice.payment_failed" if failed else "invoice.payment_succeeded",
        status=subscription.status,
        source="stripe",
        provider_event_id=provider_event_id,
        amount_cents=amount_cents,
        currency=invoice_object.get("currency"),
        reference_url=invoice_object.get("hosted_invoice_url") or invoice_object.get("invoice_pdf"),
        summary="Payment failed and the account may need attention." if failed else "Payment succeeded and the subscription remains in good standing.",
    )
    return subscription


def _build_line_item(plan_key):
    plan = PLAN_CATALOG[plan_key]
    price_id = current_app.config.get(plan["stripe_price_env"])
    if price_id:
        return {"price": price_id, "quantity": 1}
    return {
        "price_data": {
            "currency": "myr",
            "unit_amount": int(plan["price"] * 100),
            "recurring": {"interval": plan["interval"]},
            "product_data": {
                "name": f"Restaurant OS {plan['name']}",
                "description": plan["description"],
            },
        },
        "quantity": 1,
    }


def _restaurant_billing_email(restaurant):
    return getattr(restaurant, "billing_email", None) or "owner@example.com"


def _extract_id(value):
    if isinstance(value, dict):
        return value.get("id")
    return value


def _restaurant_id_from_metadata(metadata):
    raw_value = (metadata or {}).get("restaurant_id")
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _subscription_period_end(stripe_subscription):
    if not stripe_subscription:
        return None
    if isinstance(stripe_subscription, dict):
        timestamp = stripe_subscription.get("current_period_end")
    else:
        timestamp = getattr(stripe_subscription, "current_period_end", None)
    if not timestamp:
        return None
    return datetime.utcfromtimestamp(timestamp)


def _plan_from_subscription_session(session):
    items = session.get("line_items") if isinstance(session, dict) else None
    if not items:
        return "pro"
    return "pro"


def _status_from_subscription_object(subscription_object):
    if isinstance(subscription_object, dict):
        status = subscription_object.get("status")
    else:
        status = getattr(subscription_object, "status", None)
    return status or "active"


def _cancel_at_period_end(subscription_object):
    if isinstance(subscription_object, dict):
        return bool(subscription_object.get("cancel_at_period_end"))
    return bool(getattr(subscription_object, "cancel_at_period_end", False))


def _subscription_canceled_at(subscription_object):
    if isinstance(subscription_object, dict):
        timestamp = subscription_object.get("canceled_at")
    else:
        timestamp = getattr(subscription_object, "canceled_at", None)
    if not timestamp:
        return None
    return datetime.utcfromtimestamp(timestamp)


def _subscription_event_summary(subscription, *, canceled):
    if canceled:
        return "Stripe marked the subscription as canceled."
    if subscription.cancel_at_period_end:
        return "Subscription will cancel at the end of the current billing period."
    return f"Subscription synced with Stripe and is now {subscription.status}."


def _format_ringgit(amount):
    return f"RM {amount:.2f}"


def _format_amount_from_event(event):
    if event.amount_cents is None:
        return None
    return _format_ringgit(event.amount_cents / 100)


def _default_duitnow_qr_url():
    asset_path = Path(current_app.static_folder) / DEFAULT_DUITNOW_QR_ASSET
    if asset_path.exists():
        return url_for("static", filename=DEFAULT_DUITNOW_QR_ASSET)
    return None


def _save_billing_attachment(file_storage, *, restaurant_id, payment_reference):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    extension = Path(file_storage.filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp", ".pdf"}:
        raise ValidationError("Screenshot must be a PNG, JPG, WEBP, or PDF file.")

    uploads_dir = Path(current_app.config.get("BILLING_UPLOAD_DIR") or (Path(current_app.instance_path) / "billing_uploads"))
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file_storage.filename) or "payment-proof"
    stem = Path(safe_name).stem or "payment-proof"
    reference_slug = secure_filename(payment_reference).replace("_", "-").lower() or "payment"
    filename = f"restaurant-{restaurant_id}-{reference_slug}-{stem}{extension}"
    destination = uploads_dir / filename
    file_storage.save(destination)
    try:
        return str(destination.relative_to(Path(current_app.instance_path)))
    except ValueError:
        return str(destination)


def record_billing_event(
    *,
    restaurant_id,
    event_type,
    status=None,
    source="system",
    provider_event_id=None,
    plan_key=None,
    payment_reference=None,
    attachment_path=None,
    summary=None,
    amount_cents=None,
    currency=None,
    reference_url=None,
    occurred_at=None,
):
    if provider_event_id:
        existing = BillingEvent.query.filter_by(provider_event_id=provider_event_id).first()
        if existing:
            return existing

    event = BillingEvent(
        restaurant_id=restaurant_id,
        event_type=event_type,
        status=status,
        source=source,
        provider_event_id=provider_event_id,
        plan_key=plan_key,
        payment_reference=payment_reference,
        attachment_path=attachment_path,
        summary=summary,
        amount_cents=amount_cents,
        currency=(currency or "").upper() or None,
        reference_url=reference_url,
        occurred_at=occurred_at or datetime.utcnow(),
    )
    db.session.add(event)
    db.session.commit()
    return event
