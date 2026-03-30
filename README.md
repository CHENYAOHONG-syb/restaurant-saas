# Restaurant SaaS

A QR ordering and restaurant management system with a demoable owner dashboard, customer ordering flow, and Stripe-ready billing scaffold for paid trials.

## Current MVP

- Restaurant creation and owner signup
- Owner login with session + JWT support
- Customer-facing menu by restaurant slug
- Cart and checkout flow by table
- Owner dashboard for menu and order management
- Billing page with subscription state and Stripe checkout entry points
- Demo database seeding

## Local Run

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`
3. Apply schema migrations: `python3 -m flask --app run.py db upgrade --directory migrations`
4. Seed demo data: `python3 init_db.py`
5. Start the app: `python3 run.py`

If `DATABASE_URL` is not set, the app falls back to the local SQLite file in `instance/database.db`.

## Database And Deploy

- `DATABASE_URL` now expects Postgres in production
- `postgres://...` URLs are normalized automatically to `postgresql://...`
- `gunicorn` is configured in [Procfile](/Users/chenyaohong/Downloads/代码/restaurant_system/Procfile), [Dockerfile](/Users/chenyaohong/Downloads/代码/restaurant_system/Dockerfile), and [render.yaml](/Users/chenyaohong/Downloads/代码/restaurant_system/render.yaml)
- `psycopg2-binary` is included so SQLAlchemy can talk to Postgres
- `Flask-Migrate` is wired into the app factory and the initial migration lives in [migrations/versions/afde1e2733c9_initial_schema.py](/Users/chenyaohong/Downloads/代码/restaurant_system/migrations/versions/afde1e2733c9_initial_schema.py)
- [init_db.py](/Users/chenyaohong/Downloads/代码/restaurant_system/init_db.py) is now an idempotent demo seed script and no longer creates or drops tables

## Render Deploy

The project is prepared for Render in two ways:

1. Blueprint deploy with [render.yaml](/Users/chenyaohong/Downloads/代码/restaurant_system/render.yaml)
2. Manual web service setup using the same build and start commands

### Recommended Render setup

- Build command: `pip install -r requirements.txt`
- Pre-deploy command: `python3 -m flask --app run.py db upgrade --directory migrations`
- Start command: `gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- Health check path: `/`

### Required environment variables

- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `SITE_URL` set to your Render service URL, for example `https://restaurant-saas.onrender.com`

### First trial store: minimum env vars

If you only want to launch the first live trial store, these are the minimum values to fill:

- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `SITE_URL`

### Optional environment variables

- `BILLING_PROVIDER` default is `manual`; this repo's Render blueprint sets it to `duitnow_manual`
- `TRIAL_DAYS`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_GROWTH`
- `DUITNOW_RECIPIENT_NAME`
- `DUITNOW_ACCOUNT_ID`
- `DUITNOW_ACCOUNT_TYPE`
- `DUITNOW_QR_IMAGE_URL`
- `DUITNOW_REFERENCE_PREFIX`
- `DUITNOW_PAYMENT_NOTE`

### Shortest manual Render steps

1. Create a new Postgres database on Render
2. Create a new Python web service from this repo
3. Set the build, pre-deploy, and start commands shown above
4. Add the required environment variables
5. Deploy once
6. Run `python3 init_db.py` in a Render shell if you want demo data
7. Open the live URL and walk through restaurant creation, owner signup, and the guest menu

## Stripe Connection

- Set `BILLING_PROVIDER=stripe`
- Set `STRIPE_SECRET_KEY`
- Set `STRIPE_WEBHOOK_SECRET`
- Optionally set `STRIPE_PRICE_PRO` and `STRIPE_PRICE_GROWTH`
- If no Stripe price ids are set, the app builds recurring price data inline for checkout
- After Stripe redirects back to `/billing/<restaurant_id>/success`, the subscription is synced into the local database
- Point Stripe webhooks to `/stripe/webhook`
- Listen for at least `checkout.session.completed`, `customer.subscription.updated`, and `customer.subscription.deleted`

## Production Hardening Added

- `config.py` for environment-driven settings
- Optional `Flask-Migrate` integration when installed
- `Subscription` model and billing service scaffold
- Billing provider and trial configuration via environment variables
- Stripe checkout session creation and billing success sync

## Still Needed Before Real Customer Launch

- Managed Postgres deployment and backup strategy
- Role-based permissions beyond single owner access
- Automated tests and monitoring
