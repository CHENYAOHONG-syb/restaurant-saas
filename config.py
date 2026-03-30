import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me-please-12345")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    BILLING_PROVIDER = os.getenv("BILLING_PROVIDER", "manual")
    TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "14"))
    SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:5000")
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER")
    STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")
    STRIPE_PRICE_GROWTH = os.getenv("STRIPE_PRICE_GROWTH")
    DUITNOW_RECIPIENT_NAME = os.getenv("DUITNOW_RECIPIENT_NAME")
    DUITNOW_ACCOUNT_ID = os.getenv("DUITNOW_ACCOUNT_ID")
    DUITNOW_ACCOUNT_TYPE = os.getenv("DUITNOW_ACCOUNT_TYPE", "Merchant ID")
    DUITNOW_QR_IMAGE_URL = os.getenv("DUITNOW_QR_IMAGE_URL")
    DUITNOW_REFERENCE_PREFIX = os.getenv("DUITNOW_REFERENCE_PREFIX", "ROS")
    DUITNOW_PAYMENT_NOTE = os.getenv("DUITNOW_PAYMENT_NOTE")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


def normalize_database_url(database_url):
    if not database_url:
        return database_url
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url
