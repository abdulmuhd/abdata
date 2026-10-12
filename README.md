# Zaply

Airtime · Data · Electricity · Cable TV payments behind a secure wallet — FastAPI backend + mobile-first web SPA.

## Quick start (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # defaults are fine for sandbox/mock mode
uvicorn app.main:app --reload
```

- App:        http://127.0.0.1:8000
- Swagger:    http://127.0.0.1:8000/docs
- Demo login: `demo@zaply.ng` / `Demo1234!` (transaction PIN `1234`)

In development the app creates tables automatically and seeds networks, data plans,
cable packages, discos and the demo user (`SEED_DEMO_DATA=true`).

## Ru nning tests

```bash
python -m pytest
```

Tests run against a throwaway SQLite file — they never touch your dev database.

## Configuration (.env)

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` disables CORS wildcard + demo seeding |
| `SECRET_KEY` | dev value | **set a long random string in production** |
| `DATABASE_URL` | `sqlite:///./zaply.db` | use PostgreSQL in production |
| `VTU_PROVIDER` | `mock` | swap for a real VTU aggregator |
| `PAYMENT_GATEWAY` | `mock` | swap for Paystack/Flutterwave |
| `PAYMENT_WEBHOOK_SECRET` | dev value | HMAC-SHA256 key for `/webhooks/payment` |

Server-side secrets (`PAYMENT_SECRET_KEY`, webhook secret) are never exposed to the client;
only `PAYMENT_PUBLIC_KEY` reaches the browser.

## Database migrations

Development uses auto `create_all`; deployments apply Alembic revisions:

```bash
alembic upgrade head
```

## API overview (prefix `/api/v1`)

- **Auth** — register, login (email *or* phone), refresh, logout, forgot/reset password
- **Users** — profile, dashboard aggregate, change password, set/change transaction PIN
- **Wallet** — balance, funding intents, mock settlement, funding status, wallet ledger
- **Services** — airtime networks, data plans, electricity discos, cable providers/packages
- **Purchases** — airtime / data / electricity / cable, each PIN-protected with optional idempotency key
- **Transactions** — unified history (purchases + funding + refunds), receipts, re-verify
- **Notifications** — list, mark read, mark all read
- **Webhooks** — HMAC-signed payment gateway callbacks (idempotent settlement)

All responses share the envelope `{"success": bool, "message": str, "data": ...}`;
errors add a machine-readable `code`.

## Docker deployment

```bash
docker build -t zaply .
docker run -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e DATABASE_URL='postgresql+psycopg://user:pass@host/db' \
  -e PAYMENT_GATEWAY=paystack \
  -e PAYMENT_SECRET_KEY=sk_live_... \
  zaply
```

The container entrypoint applies `alembic upgrade head`, then starts uvicorn
(behind your TLS-terminating reverse proxy).

## Security model

- Passwords hashed (PBKDF2); JWT access + refresh tokens with server-side revocation on logout
- Transaction PIN hashed separately; purchases verify PIN and enforce lockout after repeated failures
- Wallet ledger is double-entry style with per-row balance tracking; refunds are first-class transactions
- Webhooks verified with constant-time HMAC comparison; settlement is idempotent
- Sliding-window rate limiting on auth endpoints; per-IP throttling returns 429 with retry hints
...   ,,