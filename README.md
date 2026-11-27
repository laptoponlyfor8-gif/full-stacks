# DM Karo

**DM Karo — Automate. Connect. Grow.** is a React and TypeScript application
with a FastAPI backend for organization-scoped social automation, customer
engagement, CRM, AI assistance, and Razorpay Test Mode subscription billing.
External integrations require credentials and account permissions; listing a
feature here does not imply that it is configured or live.

## Project structure

```text
.
├── backend/
│   ├── app/                 # FastAPI routes, models, schemas, services
│   ├── alembic/versions/    # Database migrations
│   ├── tests/               # Backend Pytest suite
│   ├── .env.example         # Blank server-side configuration template
│   ├── docker-compose.yml   # Local PostgreSQL, Redis, Mailpit, worker
│   └── README.md            # Backend setup, API, integrations and security
├── public/                  # Public static assets
├── src/
│   ├── auth/                # Frontend authentication context
│   ├── components/          # Shared UI and dashboard components
│   ├── pages/               # Landing, auth and dashboard routes
│   └── services/            # Typed API clients
├── package.json
└── README.md
```

## Requirements

- Node.js and npm compatible with the versions in `package-lock.json`.
- Python 3.12 or newer and Windows PowerShell for the commands below.
- PostgreSQL (not MySQL) and Redis for authenticated backend operations and
  background jobs. On AWS, use RDS for PostgreSQL and a Redis-compatible
  ElastiCache service. Docker Desktop is optional if those services are already
  available.
- Meta, OpenAI, Gemini, and Razorpay credentials only for the corresponding
  integrations. Razorpay is restricted to Test Mode in this application.

## Frontend setup

From the project root:

```powershell
npm ci
npm run dev
```

Open `http://localhost:5173`. Quality checks:

```powershell
npm run build
npm run lint
```

The current package scripts do not include a separate frontend test runner.

## Backend setup

Copy the example only when a local environment file does not already exist:

```powershell
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
```

Edit `backend\.env` locally. Provide a persistent random `JWT_SECRET_KEY` of at
least 32 bytes and valid PostgreSQL/Redis URLs. Add integration credentials
only when needed, and keep all secrets server-side. Never put provider keys in
`VITE_*` variables or commit `.env` files.

Install dependencies and run the API from `backend`:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, run the frontend from the project root. The API health
URL is `http://localhost:8000/health`. Development API documentation is
available at `http://localhost:8000/docs`; it is disabled outside development.

## Database and Redis

The existing Compose configuration starts local PostgreSQL, Redis, Mailpit,
and the automation worker. First configure `backend\.env`, then, from
`backend`:

```powershell
docker compose up -d postgres redis mailpit
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Start the worker only after PostgreSQL and Redis are healthy:

```powershell
docker compose up -d automation-worker
```

Do not run migrations against a production database without a separately
reviewed backup and release procedure. PostgreSQL row-level security expects
tenant context set by authenticated backend requests.

## Configuration

The complete variable list and defaults are in
[`backend/.env.example`](./backend/.env.example); configuration behavior and
integration setup are documented in [`backend/README.md`](./backend/README.md).
Important groups include:

- App/API: `APP_ENV`, `PUBLIC_APP_URL`, CORS and request limits.
- Database/cache: `DATABASE_URL`, `REDIS_URL`, and Compose bootstrap variables.
- Authentication/email: `JWT_SECRET_KEY`, cookie settings, and optional SMTP.
- Meta: app ID/secret, callback URL, token-encryption key, and webhook token.
- AI: server-side `OPENAI_API_KEY`, `GEMINI_API_KEY`, model names, and limits.
- Billing: `RAZORPAY_MODE=test`, Test Mode keys, webhook secret, and grace
  period. Do not configure live payments.

`.env.example` keeps credentials blank or marked as local placeholders and
contains non-secret development defaults. Do not paste credentials into source
code, issue reports, or chat.

## Routes and integrations

Public routes include `/`, `/login`, `/register`, `/forgot-password`,
`/reset-password`, `/verify-email`, `/privacy`, and `/terms`. Authenticated
dashboard routes include `/dashboard`, `/dashboard/accounts`,
`/dashboard/automations`, `/dashboard/inbox`, `/dashboard/contacts`,
`/dashboard/leads`, `/dashboard/analytics`, `/dashboard/ai-assistant`, and
`/dashboard/billing`. See `src/App.tsx` for the full route list.

Backend API routes use `/api/v1`; the OpenAPI page in development lists the
available endpoints. Meta OAuth/webhooks, AI provider calls, and Razorpay
checkout/webhooks require their own valid configuration. Razorpay billing is
Test Mode only. Real payment, Meta messaging, and provider availability are not
guaranteed by the source code alone.

## Tests

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite uses isolated SQLite and mocks external provider calls;
passing tests do not prove PostgreSQL/Redis deployment readiness or real
third-party credentials. For full backend behavior, run PostgreSQL and Redis
and apply migrations. For frontend static verification, run `npm run build`
and `npm run lint` at the project root.

## License and service status

No license granting third-party reuse is included. This repository is source
code, not a deployment. External accounts, permissions, infrastructure,
security review, monitoring, and operational configuration are still required
before production use.
