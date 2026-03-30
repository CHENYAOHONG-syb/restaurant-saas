from pathlib import Path

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app(tmp_path):
    database_path = Path(tmp_path) / "test.db"
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-1234567890-abcdefghijk",
            "JWT_SECRET_KEY": "test-jwt-secret-key-1234567890-abcdefghijk",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "BILLING_PROVIDER": "stripe",
            "STRIPE_SECRET_KEY": "sk_test_123",
            "STRIPE_WEBHOOK_SECRET": "whsec_test_123",
            "SITE_URL": "http://localhost",
        }
    )

    with flask_app.app_context():
        db.drop_all()
        db.create_all()

    yield flask_app

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
