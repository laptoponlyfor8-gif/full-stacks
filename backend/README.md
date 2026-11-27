# DM Karo Backend Foundation

FastAPI backend for DM Karo. The backend includes real user authentication,
organization authorization, API health checks, environment-based configuration,
asynchronous PostgreSQL/Redis clients, a multi-tenant relational schema,
PostgreSQL row-level security, official Meta account connections, verified
webhook intake, a Redis-stream automation worker, and OpenAI/Gemini assistance.
The unified inbox, contacts, leads, analytics, and Razorpay Test Mode
subscription billing use organization-scoped records.

## Architecture

- `app/api/v1/` contains versioned HTTP routes; the unversioned root health route
  is retained for basic load-balancer probes.
- `app/core/` owns validated settings, structured JSON logging, and HTTP error
  responses.
- `app/db/` owns the SQLAlchemy async engine/session factory, FastAPI session
  dependency, model metadata, and tenant transaction helper.
- `app/services/readiness.py` performs bounded, real dependency checks for
  PostgreSQL and Redis. Public readiness responses expose only `ok` or
  `unavailable`, never connection details.
- `app/services/` also contains configurable SMTP email delivery, rate limits,
  Meta webhook normalization, tenant-scoped automation execution, and
  interchangeable AI provider adapters.
- `app/api/v1/crm.py` provides organization-scoped conversations, manual replies,
  contacts, notes, tags, lead activity, and analytics over persisted Meta events
  and confirmed messages.
- `app/api/v1/ai.py` exposes authenticated AI chat, writing assistance, business
  knowledge, provider preference, and usage routes. Provider credentials remain
  in backend environment configuration and are never stored in the database.
- `app/models/` defines the production PostgreSQL entities and tenant-safe
  foreign-key relationships. `app/schemas/` contains validated entity schemas
  that omit password hashes and social tokens.
- `alembic/` contains the versioned schema migrations and asynchronous
  migration environment. Tenant-owned tables use forced row-level security.

The database URL is validated to require `postgresql+asyncpg://`; no psycopg
driver or synchronous database configuration is used. Secrets use Pydantic
`SecretStr`. API documentation is available only in the development environment.
Local Compose database/cache ports bind to loopback; a production deployment
should use private AWS networking and must not publish these service ports.

## Database schema and tenant isolation

The initial schema consists of these tables:

- `users`: globally unique, case-insensitive email and password hash storage.
- `organizations`: tenant root and owner reference.
- `organization_members`: user-to-organization membership and role.
- `social_accounts`: organization-owned Instagram/Facebook account records.
- `automations`: tenant-owned records tied to a social account.
- `automation_keywords`: keywords tied to an automation in the same tenant.
- `messages`: tenant-owned records tied to an account and, optionally, the
  matching automation; inbox messages also link to a contact and retain their
  provider event time and workspace read state.
- `contacts`, `contact_notes`, `contact_tags`, `contact_tag_assignments`, and
  `lead_activities`: tenant-owned CRM contacts and their notes, tags, and lead
  status history. Conversations are grouped from the existing `messages` table
  rather than duplicating message storage.
- `subscriptions`, `billing_customers`, `payments`, `billing_webhook_events`,
  and `billing_event_logs`: tenant-owned Razorpay subscription lifecycle,
  confirmed payment metadata, and idempotent webhook processing. The singleton
  `billing_plans` table stores the single monthly Test Mode plan identifier.
- `ai_conversations`, `ai_messages`, `ai_usage_records`,
  `ai_provider_configurations`, and `business_knowledge`: tenant-owned AI
  conversations, accounting metadata, provider/model preference without
  secrets, and manually entered business context.

Entity relationships (1:N unless marked N:N):

```text
users ──< organizations (owner_user_id)
users >──< organizations (through organization_members.role)
organizations ──< organization_members
organizations ──< social_accounts ──< automations ──< automation_keywords
organizations ──< automations ──< messages
social_accounts ──< messages
social_accounts ──< contacts ──< messages
contacts ──< contact_notes
contacts >──< contact_tags (through contact_tag_assignments)
contacts ──< lead_activities
organizations ──< subscriptions
```

Organizations, memberships, social accounts, automations, keywords, messages,
CRM records, AI records, and subscriptions carry tenant ownership. Composite foreign keys enforce that
an automation's account, its keywords, any linked message, and each contact's
social account belong to the same organization. Duplicate memberships, platform accounts per organization,
case-insensitive emails/slugs, and duplicate keywords per automation are
constrained in the database. Important parent deletions are restricted rather
than cascading tenant data.

PostgreSQL row-level security is enabled and forced for tenant tables. The API
authenticates the user, checks their membership and role, and establishes the
authorized organization context inside the request's database session:

```python
async with tenant_transaction(session, authorized_organization_id):
    result = await session.execute(statement)
```

The transaction-local setting is cleared automatically when the transaction
ends, which avoids leaking tenant context through pooled connections. The
authentication dependencies establish the user and authorized organization
settings after validating the signed token and live membership. Production
application database credentials must be a non-superuser role
without `BYPASSRLS`. PostgreSQL superusers and roles with `BYPASSRLS` can bypass
row-level policies; the default local Compose bootstrap user is for development
only and must not be used by a production application.

Social access tokens are encrypted by the Meta integration and are never
included in public API schemas or logs.

## Authentication and authorization

Passwords are hashed with Argon2. Access tokens are short-lived signed JWTs and
are held in frontend memory. Refresh JWTs are stored server-side only as SHA-256
hashes, rotated on refresh, and sent to the browser in an HttpOnly cookie. A
separate CSRF cookie/header pair protects refresh and logout. Password reset and
email-verification links use expiring, single-use signed tokens; only their
hashed identifiers are stored. Password reset increments the user's auth
version and revokes existing sessions and refresh tokens. Login is blocked until
the email address is verified.

Sensitive endpoints use Redis-backed rate limits. Rate limiting fails closed
when Redis is unavailable. The configured SMTP provider sends verification and
reset email only when all required SMTP settings exist. Without an email
provider, registration reports that verification email was not sent, and
password-reset responses remain generic to avoid revealing registered addresses.
For local development, the Compose file includes Mailpit on SMTP port `1025`
and its web UI on `8025`; configure `SMTP_HOST=127.0.0.1`,
`SMTP_PORT=1025`, `SMTP_FROM_EMAIL` to a local sender, and
`SMTP_STARTTLS=false`. No real SMTP credentials are required for Mailpit.

Authentication routes (all under `/api/v1`):

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register` | Create user, organization and owner membership; send verification email when configured |
| POST | `/auth/login` | Verify credentials and issue access/refresh tokens |
| POST | `/auth/refresh` | Rotate refresh token (requires HttpOnly cookie and CSRF header) |
| POST | `/auth/logout` | Revoke current refresh session and clear auth cookies |
| GET | `/auth/me` | Return the authenticated user and active organization |
| POST | `/auth/forgot-password` | Request reset email; response does not disclose account existence |
| POST | `/auth/reset-password` | Consume a reset link and revoke existing sessions |
| POST | `/auth/verify-email` | Consume an email-verification link |
| POST | `/auth/resend-verification` | Resend verification email when configured |
| GET | `/auth/organizations` | List organizations belonging to the authenticated user |
| GET | `/organizations/{organization_id}/members` | List members for a user's organization; owner/admin only |

Set `JWT_SECRET_KEY` to a unique random value of at least 32 bytes. In staging
and production, configure HTTPS origins, `AUTH_COOKIE_SECURE=true`, and
non-local PostgreSQL and Redis service URLs. Never commit `.env` or use the
development Compose database credentials in a deployed environment.

## Meta account connections

The Meta connection module uses two distinct official web authorization
products; it does not pretend one OAuth flow works for both platforms:

- **Instagram** uses Business Login for Instagram and the Instagram API with
  Instagram Login. It supports eligible Instagram Professional Business and
  Creator accounts, not personal/consumer accounts. This login method does not
  require a linked Facebook Page. It requests
  `instagram_business_basic`, `instagram_business_manage_comments`, and
  `instagram_business_manage_messages` for supported comment and messaging
  webhook workflows. The app subscribes the connected account to comments and
  messages after OAuth.
- **Facebook** uses Facebook Login for Business. A Meta Dashboard Login
  configuration is required; `META_FACEBOOK_LOGIN_CONFIG_ID` identifies it.
  Configure Page listing, engagement, metadata, and messaging access needed
  for `feed` and `messages` webhooks, comment replies, and Page messages. The
  backend only connects Pages returned by the user authorization and subscribes
  the selected Page to the configured webhook fields.

Meta can change API versions and permissions. `META_GRAPH_API_VERSION` defaults
to `v27.0`, the latest Graph API version shown by Meta's changelog when this
implementation was checked; update it only after confirming the version remains
available and compatible. The implementation uses versioned Graph endpoints,
the documented Instagram Business Login token exchange/refresh endpoints, and
Facebook's `/me/accounts` and `/debug_token` endpoints.

Official references:

- [Instagram API with Instagram Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/)
- [Business Login for Instagram](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login/)
- [Instagram Login get started](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started/)
- [Facebook Login for Business](https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business/)
- [Graph API permissions reference](https://developers.facebook.com/documentation/development/permissions/)
- [Graph API changelog and supported versions](https://developers.facebook.com/docs/graph-api/changelog/)
- [User Pages edge](https://developers.facebook.com/docs/graph-api/reference/user/accounts/)
- [Debug Token edge](https://developers.facebook.com/docs/graph-api/reference/debug_token/)

### Meta environment and app setup

Set these variables in `backend\.env` for local work (placeholders only are
checked in):

- `META_APP_ID` and `META_APP_SECRET`: from the Meta Developer App.
- `META_REDIRECT_URI`: the exact backend URL
  `https://<backend-host>/api/v1/meta/oauth/callback`. For local testing, use a
  public HTTPS development tunnel URL; Meta cannot reach a developer's private
  machine. The exact URI must also be registered in the Meta app. Local HTTP
  loopback is useful for unit tests but is not a publicly testable Meta callback.
- `META_GRAPH_API_VERSION`: a supported version, currently `v27.0`.
- `META_FACEBOOK_LOGIN_CONFIG_ID`: the Facebook Login for Business configuration
  ID used for Page authorization.
- `META_TOKEN_ENCRYPTION_KEY`: URL-safe Base64 for exactly 32 random bytes.
  Generate a local value without writing it into source control:

  ```powershell
  python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  ```

- `META_WEBHOOK_VERIFY_TOKEN`: a random value shared with the Meta Webhooks
  callback configuration. It is required for verification; the App Secret is
  used separately to verify `X-Hub-Signature-256`.

In the Meta Developer Dashboard:

1. Create a Business-type app/use case that supports Instagram API with
   Instagram Login and Facebook Login for Business.
2. Set the Instagram Business Login redirect URI and the app's valid OAuth
   redirect URI to exactly match `META_REDIRECT_URI`. Configure the allowed
   domain and HTTPS URLs for the deployed app.
3. Configure Business Login for Instagram with
   `instagram_business_basic`, `instagram_business_manage_comments`, and
   `instagram_business_manage_messages`. The latter permissions require the
   appropriate Meta review/advanced access for customers outside app roles.
4. Create a Facebook Login for Business configuration that permits Page
   selection and includes only permissions required by the Page listing
   endpoint and the supported Page fields/actions used by the feature. Set the
   Facebook Login for Business configuration's permissions to the minimum
   approved Page permissions for `feed`, `messages`, Page comment management,
   and Page messaging. Copy its configuration ID to
   `META_FACEBOOK_LOGIN_CONFIG_ID`.
5. Add the **Instagram** and **Page** webhook products/objects in the Meta App
   Dashboard. Set the callback URL to
   `https://<backend-host>/api/v1/webhooks/meta`, use the exact
   `META_WEBHOOK_VERIFY_TOKEN`, and subscribe Instagram to `comments` and
   `messages`, and Page to `feed` and `messages`. Meta must be able to reach
   this URL over valid HTTPS.
6. Add developer/tester roles and eligible test assets while the app is in
   Development mode. Test users must accept the relevant invitations and grant
   the requested permissions. Development mode is limited to app-role users and
   test assets; it is not production customer access.
7. For customers/businesses outside your own app roles, request the needed
   Advanced Access through Meta App Review and complete required Business
   Verification and data-use/compliance checks. Review is not automatically
   granted by this implementation.

The backend encrypts Meta access tokens using AES-256-GCM. Refreshable Instagram
long-lived tokens can be refreshed through the Instagram token refresh
endpoint; expired or rejected tokens require reconnection. Facebook Page token
expiration is recorded when the token inspection endpoint supplies a positive
expiry timestamp; no expiry is stored when Meta reports none. Reauthorization
replaces saved tokens. The UI never receives token strings.

Keep the encryption key outside source control. For AWS, store it in a managed
secret/key service with tightly scoped IAM access and inject it only into the
backend at runtime. Key rotation is an operator procedure in this phase: decrypt
and re-encrypt all active account tokens with the new key before retiring the
old one. Token encryption keys are not interchangeable with JWT keys or Meta
app secrets.

Meta endpoints (under `/api/v1`; all connection-management endpoints require an
authenticated user and the active organization):

| Method | Route | Purpose |
|---|---|---|
| POST | `/meta/connect/instagram` | Start Instagram Business Login; returns a Meta authorization URL |
| POST | `/meta/connect/facebook` | Start Facebook Login for Business |
| GET | `/meta/oauth/callback` | Validate/consume one-time state and complete the appropriate provider flow |
| GET | `/meta/accounts` | List accounts belonging only to the active organization; never returns tokens |
| GET | `/meta/facebook/pending/{flow_id}/pages` | List safe Page identifiers/names from a short-lived authorized selection |
| POST | `/meta/facebook/pending/{flow_id}/select` | Connect one of those authorized Pages |
| POST | `/meta/accounts/{account_id}/refresh` | Refresh an Instagram long-lived token when still valid |
| DELETE | `/meta/accounts/{account_id}` | Revoke local connection and erase the saved token |

OAuth state is random, stored server-side with a short TTL, consumed once, and
bound to the initiating user, organization and platform. Facebook Page
selection data is short-lived and its tokens are encrypted while in Redis.
Disconnecting is tenant-scoped and clears the local credential. It does not
revoke permissions inside Meta; users can also revoke access in their Meta
account settings.

Production launch checklist: configure the production HTTPS redirect URI in
both systems; enable the correct Business Login products/configuration; request
only permissions the shipped feature uses; finish App Review/Advanced Access
and Business Verification; use test and production app modes appropriately;
inject secrets and the encryption key from AWS Secrets Manager/KMS-backed
operations; verify database backups and key recovery; and run a real-account
connection plus token refresh/revocation test before launch. A successful
account connection does not mean Meta has approved messaging or automation.

## Webhooks and automation execution

The Meta webhook callback is `GET|POST /api/v1/webhooks/meta`.

- `GET` validates `hub.mode=subscribe` and the configured verification token,
  then returns the challenge.
- `POST` checks the HMAC-SHA256 signature against the unmodified request bytes,
  enforces a Redis-backed per-IP rate limit, validates the payload size and
  supported event shape, resolves the provider account through the internal
  Meta account-route index, then stores a minimal event record and queues it in
  the Redis stream `dm-karo:webhook-events`.
- Unknown/ambiguous account routes are acknowledged without invoking any
  tenant's workflow. Event and execution records are protected by PostgreSQL
  RLS; webhook account routing stores only internal/provider IDs and is never
  exposed by an API.

The separate worker is started from `backend\` after applying migrations:

```powershell
python -m app.worker
```

Or start the Compose worker (after creating `.env` and applying migrations):

```powershell
docker compose --env-file .env up -d automation-worker
docker compose logs -f automation-worker
```

The worker consumes a Redis Stream consumer group, uses database claims and
idempotency constraints, retries transient failures with bounded exponential
backoff, and records terminal failures in `automation_executions`,
`message_delivery_attempts`, the event row, and a bounded dead-letter stream.
The worker also recovers pending database events if Redis enqueueing was
interrupted. Run one or more worker processes; each process has a distinct
consumer identity.

Automation API endpoints are authenticated and scoped to the user's active
organization:

| Method | Route | Purpose |
|---|---|---|
| GET | `/automations` | List tenant automations and actual sent/failure totals |
| POST | `/automations` | Create a draft tied to a connected account; comment permalinks are resolved through Meta |
| GET | `/automations/{automation_id}` | Get one tenant-owned automation |
| PATCH | `/automations/{automation_id}` | Update draft/paused rules, response text, or status |
| DELETE | `/automations/{automation_id}` | Delete only when execution/message history permits |
| GET | `/automations/{automation_id}/executions` | List the latest 100 execution records |

Comment workflows support exact, contains, and phrase keyword matching against
comments for the specific resolved post/Reel. Incoming direct-message workflows
can be created with `trigger_type="direct_message"` and share the keyword and
private-reply configuration; replies are restricted to the platform's 24-hour
messaging window. Comment private replies are limited to one per comment and
the supported seven-day window; Instagram Live comment private replies are
skipped because they are only valid during the live broadcast. Public replies
are optional and target only the triggering comment. Message bodies are plain
text (including ordinary URLs); attachment delivery and sequential message
templates are not enabled. A `sent` status means Meta returned a message
identifier, not that the recipient opened or received it. No delivery claim is
made without a provider response.

The worker does not infer a feature permission from OAuth alone. It records
Meta rejection or invalid-token errors; an invalid/revoked token disconnects
the account locally and pauses its active automations. Reconnect after adding
the approved permissions. Facebook Login for Business permissions are selected
in the Dashboard configuration, not automatically granted by this code.

## Unified inbox, CRM, and analytics

The authenticated routes below are scoped to the current organization; CRM
tables have forced PostgreSQL row-level security and tenant-aware foreign keys.
The inbox groups existing `messages` by account and customer instead of creating
a second conversation-message store.

| Method | Route | Purpose |
|---|---|---|
| GET | `/conversations` | Search/filter and paginate stored direct-message conversations |
| GET | `/conversations/{contact_id}` | Get a contact's captured message history |
| PATCH | `/conversations/{contact_id}/read` | Mark stored incoming messages as read in the workspace |
| POST | `/conversations/{contact_id}/messages` | Send a manual text reply through the connected Meta account |
| GET, POST | `/contacts` | List/search contacts or create a permitted platform contact record |
| GET, PATCH | `/contacts/{contact_id}` | Read or update contact name and custom fields |
| GET, POST | `/contacts/{contact_id}/notes` | List or add private organization notes |
| GET, POST | `/tags` | List or create organization tags |
| PUT | `/contacts/{contact_id}/tags` | Replace a contact's organization-scoped tags |
| GET | `/leads` | Search, filter, and paginate lead/contact records |
| PATCH | `/leads/{contact_id}/status` | Change lead status and record an activity |
| GET | `/leads/{contact_id}/activities` | Read lead status activity |
| GET | `/analytics` | Return date-filtered execution, message, contact, lead, and platform totals |

Owners and admins manage contact details, tags, and lead status; organization
members can view records, add notes, and use eligible manual replies. A manual
reply is sent only inside the supported 24-hour messaging window. The API
stores `sent` only after Meta returns a message identifier; rejected requests
are recorded as failed, and ambiguous network outcomes are recorded as
uncertain so clients should inspect the conversation before retrying.

Inbox data begins with supported, signature-verified webhook events received
after the integration is configured. This implementation does not import
historical conversations from Meta. Customer names and profile details remain
blank when the webhook/API has not provided them; only platform IDs and
account/platform information known to the workspace are displayed. Analytics
are counts of stored records, not estimates of complete account history.

## Database migrations

Configure `.env` and start PostgreSQL before creating additional
autogenerated migrations. Run these commands from `backend\`:

```powershell
python -m alembic current
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "describe schema change"
```

Review autogenerated migrations before applying them. The schema and
authentication migrations are checked in. To inspect their PostgreSQL DDL
without connecting to a database:

```powershell
python -m alembic upgrade head --sql
```

For local development only, `python -m alembic downgrade -1` reverts the latest
migration. Review the migration first; downgrading the initial schema drops its
tables and data.

## Database tests

Run the complete test suite from `backend\`:

```powershell
python -m pytest
```

Model, webhook, and automation tests use a fresh, isolated in-memory SQLite database per
test; they do not connect to or alter PostgreSQL data. Auth tests also use an
isolated SQLite database, fake Redis and captured email. The migration test
compiles migrations as PostgreSQL SQL and checks their tables, policies, and
important constraints. These checks do not prove PostgreSQL row-level security, actual Redis stream
concurrency/rate limiting, SMTP delivery, or live Meta API permissions. The
worker retry, signature, and event-engine logic is tested with isolated
dependencies and mocked provider responses only.

## Requirements

- Windows 10/11 with PowerShell
- Python 3.12 or later (64-bit)
- Docker Desktop with the Compose plugin, for local PostgreSQL and Redis

Verify installations:

```powershell
py -3.12 --version
docker --version
docker compose version
```

If Python 3.12 is not installed, install it from python.org and enable the Python
launcher. Docker Desktop is optional if you already have reachable PostgreSQL and
Redis services.

## Create a virtual environment and install dependencies

Run commands from the backend directory:

```powershell
cd C:\Users\Dell\Desktop\demo\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation for the current process, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

You can avoid activation by using `.venv\Scripts\python.exe -m pip ...` and
`.venv\Scripts\python.exe -m uvicorn ...` explicitly.

## Configure environment variables

Create a local environment file from the placeholders:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace the placeholder values before starting services:

- `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` configure the local
  PostgreSQL container. Use a unique local password.
- `DATABASE_URL` must use `postgresql+asyncpg://` and the same user, password,
  database, and host. Percent-encode reserved characters in credentials (for
  example, `@` as `%40`).
- `REDIS_URL` points to the local Redis service.
- `CORS_ALLOWED_ORIGINS` is a JSON array of frontend origins; do not use `*`.
- `APP_ENV` controls interactive API docs. Only `development` enables them.
- `JWT_SECRET_KEY` must be a unique random value of at least 32 bytes for auth
  endpoints. Configure SMTP variables to send email; otherwise verification
  delivery is explicitly unavailable.
- `LOG_LEVEL` controls structured application log output.

`.env` is ignored by `backend/.gitignore`; do not commit it or put production
secrets in source control. The repository contains no real `.env`.

## Start PostgreSQL and Redis

With Docker Desktop running, from `backend\`:

```powershell
docker compose --env-file .env up -d postgres redis
docker compose ps
```

Compose persists PostgreSQL and Redis data in named volumes and reports container
health. Ports are bound to `127.0.0.1` for local development only. Stop services
without deleting data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless you intend to delete local database
and cache data.

## Run FastAPI

With the virtual environment active and PostgreSQL/Redis healthy:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For local checks, open:

- Root liveness: <http://127.0.0.1:8000/health>
- Versioned liveness: <http://127.0.0.1:8000/api/v1/health>
- Dependency readiness: <http://127.0.0.1:8000/api/v1/ready>
- OpenAPI docs (development only): <http://127.0.0.1:8000/docs>

Liveness does not require the data services. Readiness runs `SELECT 1` against
PostgreSQL and `PING` against Redis; it returns HTTP 503 if either dependency is
unavailable.

The backend Dockerfile builds a non-root container image for future deployment:

```powershell
docker build -t dm-karo-backend:local .
```

The `.dockerignore` file excludes local secrets, virtual environments, caches,
and tests from the build context. The image does not publish ports or contain
credentials. Production deployment, AWS networking, and secrets management are
not configured in this phase.

## Run tests

Run from `backend\` with the virtual environment active:

```powershell
python -m pytest
```

Tests cover root and versioned liveness, readiness outcomes when each dependency
is healthy/unhealthy, response safety, configuration validation, model
relationships, constraints, schema validation, migration SQL generation, and
registration/login/session/password-reset/email-verification/organization
authorization behavior. Readiness tests replace only the external connectivity
probes; no test requires or claims live PostgreSQL or Redis connectivity. Run
services and check `/api/v1/ready` separately to verify local connectivity.

## AI integration (Prompt 12)

The authenticated AI layer uses the official OpenAI Python SDK with the
Responses API and Google's official `google-genai` SDK. Gemini text generation
uses the supported `generateContent` API with a separate system instruction;
Google also documents its newer Interactions API, which can be adopted later
without changing the provider interface. Provider calls are asynchronous,
bounded by a timeout, and retried at most once for transient failures. No
provider is required for the rest of the service to start.

The default model identifiers are `gpt-6-astra` and `gemini-3.8-flash`.
Operators may set `AI_OPENAI_MODEL` and `AI_GEMINI_MODEL` to models available to
their provider account. A customer can select only a server-configured provider
and model. Organization preference records contain provider/model names only;
API keys are never stored in the database, returned by APIs, or sent to the
browser.

Configure at least one key in the backend environment (or inject it using AWS
Secrets Manager/Systems Manager Parameter Store and a narrowly scoped workload
IAM role):

```dotenv
OPENAI_API_KEY=
GEMINI_API_KEY=
AI_OPENAI_MODEL=gpt-6-astra
AI_GEMINI_MODEL=gemini-3.8-flash
AI_REQUEST_TIMEOUT_SECONDS=30
AI_REQUESTS_PER_MINUTE=20
AI_DAILY_REQUEST_LIMIT=100
AI_MAX_INPUT_CHARACTERS=12000
AI_MAX_OUTPUT_TOKENS=1000
```

Create keys in the [OpenAI API platform](https://platform.openai.com/api-keys)
and [Google AI Studio](https://aistudio.google.com/api-keys). Restrict and rotate
keys according to the provider's controls. Never set these as `VITE_*` variables
or paste them into the frontend. The optional
`AI_{OPENAI,GEMINI}_{INPUT,OUTPUT}_COST_PER_MILLION` values are USD rates. Cost
estimates are disabled unless all rates for the selected provider are explicitly
configured from current official pricing. Check the provider's regional, data
retention, and privacy terms before sending customer conversations; never send
passwords, tokens, payment data, or other unnecessary sensitive information.

Organization-owned AI data is stored in PostgreSQL tables
`ai_conversations`, `ai_messages`, `ai_usage_records`,
`ai_provider_configurations`, and `business_knowledge`. PostgreSQL RLS is
enabled and forced for each table. The authenticated principal's organization
is used for every AI operation. Redis enforces per-organization minute and UTC
daily request limits; both limits fail closed if Redis is unavailable. Request
accounting includes successful and provider-failed calls, token counts where
returned, and an optional configured price estimate. Limit rejections are not
provider calls and are not recorded as AI usage.

Business knowledge is customer-entered text only (name, description,
products/services, FAQs, website information, and instructions). This phase
does not crawl sites, build embeddings, or implement retrieval-augmented
generation. The content is passed only as untrusted context for that
organization's generation request. AI chat history is capped to the latest 20
messages per call; clear a conversation to delete its stored messages. Prompt
contents and provider response bodies are not written to application logs.
Prompt-injection defenses are best effort; they are not a security boundary or
a guarantee of factual accuracy. Smart-inbox intent, lead intent, FAQ, and
sentiment outputs are explicitly estimates, not verified facts. AI-generated
automation text is only a draft; it is not sent unless a user separately saves
and activates the existing authorized automation.

Authenticated AI endpoints (all under `/api/v1`):

| Method | Route | Purpose |
|---|---|---|
| GET | `/ai/providers` | List server-configured provider/model availability and current organization preference; no secrets |
| PUT | `/ai/providers` | Set the organization's provider/model preference |
| GET | `/ai/conversations` | List recent organization conversations |
| GET | `/ai/conversations/{conversation_id}` | Get one organization conversation and its messages |
| DELETE | `/ai/conversations/{conversation_id}` | Delete/clear an organization's conversation |
| POST | `/ai/chat` | Send a context-aware chat message and persist the conversation |
| POST | `/ai/assist` | Generate a human-reviewed draft, keyword suggestion, translation, summary, reply, or classification |
| GET/PUT | `/ai/knowledge` | Read or update the organization's manually-entered business knowledge |
| GET | `/ai/usage` | Report the organization's last 30 days of requests, tokens, and configured cost estimates |

### Test AI locally

1. Copy `backend/.env.example` to `backend/.env`, configure PostgreSQL and Redis,
   and add a real provider key only to this backend environment file. Do not
   commit it. The API can start with neither key, but AI requests then return a
   clear `503` configuration error.
2. Install backend requirements, start PostgreSQL and Redis, and run from
   `backend\`:

   ```powershell
   python -m alembic upgrade head
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

3. From the project root run `npm run dev`, register and verify a user, log in,
   and open `/dashboard/ai-assistant`. Select a configured provider, enter
   organization business knowledge, send a chat prompt, and try the draft,
   translation, summary, or classification tools. Use `/docs` in development
   to inspect the request/response schemas.
4. Configure optional provider pricing only after checking the providers'
   current prices. Confirm the AI usage panel reports token counts, and that it
   describes cost as unconfigured otherwise.
5. To run isolated mocked provider and tenant tests:

   ```powershell
   python -m pytest tests\test_ai.py tests\test_migrations.py
   ```

Automated tests mock SDK responses; they do not prove a real key/model is
authorized, provider account billing is enabled, or live provider latency and
quotas. Run a small real request using a valid backend key before production.
AWS Mumbai deployment, AWS secret injection/IAM, provider billing, and data
retention configuration remain operator tasks.

## Razorpay Test Mode billing

DM Karo supports exactly one Razorpay subscription plan: **DM Karo Monthly,
₹299 INR per month**. Razorpay requires a finite `total_count`; the API creates
the subscription for 1,200 monthly cycles (the maximum 100-year duration
supported by Razorpay). The Razorpay plan ID is created once and stored in
`billing_plans`, rather than creating a plan for each checkout.

1. In the official [Razorpay Dashboard](https://dashboard.razorpay.com/), use
   **Test Mode** and generate a Test Mode Key ID and Key Secret. Keep both
   values private. DM Karo rejects non-Test-Mode Key IDs.
   The integration uses Razorpay's official [plan API](https://razorpay.com/docs/api/payments/plans/create-plan/),
   [subscription API](https://razorpay.com/docs/api/payments/subscriptions/create-subscription/),
   [subscription lifecycle](https://razorpay.com/docs/payments/subscriptions/states/),
   and [subscription webhooks](https://razorpay.com/docs/webhooks/subscriptions/).
2. Set these values only in `backend\.env` (never use `VITE_` variables):

   ```dotenv
   RAZORPAY_MODE=test
   RAZORPAY_KEY_ID=rzp_test_your_key_id
   RAZORPAY_KEY_SECRET=your_test_mode_key_secret
   RAZORPAY_WEBHOOK_SECRET=your_webhook_signing_secret
   BILLING_GRACE_PERIOD_DAYS=7
   ```

   Leave the webhook secret blank until creating the webhook in the Dashboard.
   The backend `.env.example` contains blank placeholders; never commit
   `backend\.env`.
3. Configure a Razorpay Test Mode webhook to
   `https://<your-public-https-url>/api/v1/webhooks/razorpay`, using the same
   webhook secret, and enable the subscription lifecycle events
   (`subscription.authenticated`, `subscription.activated`,
   `subscription.charged`, `subscription.pending`, `subscription.halted`,
   `subscription.paused`, `subscription.resumed`, `subscription.cancelled`,
   `subscription.completed`, `subscription.expired`, and
   `subscription.updated`) plus `payment.failed`. For local development, expose
   the API through a public HTTPS tunnel accepted by Razorpay; some tunnel
   provider domains may be blocked. Never expose the local API without valid
   webhook signature verification.
4. With PostgreSQL and Redis running and configured in `backend\.env`, run:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   In another terminal at the project root, run `npm run dev`, log in with an
   organization owner or admin account, and open
   `http://localhost:5173/dashboard/billing`. The first subscribe request
   creates the one monthly plan if it does not yet exist. Use only Razorpay
   Test Mode checkout values; no real charge is made.
5. To run the isolated mocked billing and migration tests:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m pytest tests\test_billing.py tests\test_migrations.py
   ```

Checkout signatures are verified by the backend, then payment and subscription
details are fetched from Razorpay. The browser callback does not activate a
subscription; signed, idempotent provider webhooks update its lifecycle state.
Plan and subscription creation reservations fail closed on ambiguous network
outcomes so a retry cannot silently create duplicate provider records.
Customer records are reused per organization, and Razorpay's `fail_existing`
customer option is used when provisioning the initial customer.
If plan provisioning remains `creation_unknown`, inspect the Test Mode plan in
Razorpay Dashboard and reconcile the `billing_plans` row before retrying.
The billing page distinguishes created, authenticated, active, pending, halted,
cancelled, completed, and expired states. Pending/failed billing receives a
configurable seven-day grace period by default; customer data is retained and
is not deleted when a payment fails. Retry behavior and payment-method updates
are managed by Razorpay.

Razorpay Checkout displays the payment methods enabled for the merchant's
account. DM Karo never collects or stores UPI PINs, card numbers, bank
passwords, secret keys, or bank settlement details. Razorpay handles settlement
to the merchant's approved settlement account, after applicable fees and
settlement processing:

1. Create a Razorpay merchant account and select the business category that
   matches the actual legal/business status.
2. Complete Razorpay's current KYC and merchant onboarding requirements.
3. Add an eligible personal bank account securely in the official Razorpay
   Dashboard, if Razorpay permits it for the selected category and account.
4. Wait for Razorpay to review and approve the settlement account.
5. Razorpay settles eligible payments to the registered account after its
   applicable fees and settlement schedule.

Personal savings accounts are not automatically eligible. Confirm eligibility
and current KYC/settlement requirements with Razorpay; DM Karo does not collect
bank details and cannot guarantee approval. Only Test Mode has been implemented
and tested with mocked provider calls. No live payment, production webhook, or
real settlement has been executed.

## Troubleshooting

- **`py -3.12` cannot find Python:** Install Python 3.12+ and enable the Python
  launcher, or use an installed compatible interpreter with `py -3`.
- **Docker commands are unavailable:** Install and start Docker Desktop with
  Compose support, or connect to separately managed PostgreSQL and Redis.
- **Database URL validation fails:** Confirm it starts with
  `postgresql+asyncpg://`, has a database name, and percent-encodes reserved
  username/password characters.
- **Readiness returns 503:** Check `docker compose ps`, the host/port and
  credentials in `.env`, then inspect container logs with
  `docker compose logs postgres redis`.
- **Tenant-scoped queries return no rows:** Ensure the API has established the
  authorized organization context inside the same transaction before issuing
  tenant queries. Do not work around row-level security by using a
  superuser/BYPASSRLS application credential.
- **Port already in use:** Change `POSTGRES_PORT` or `REDIS_PORT` in `.env` and
  update the local service URLs accordingly.
- **API docs are missing:** Set `APP_ENV=development` in `.env` and restart
  Uvicorn. Docs are intentionally disabled for staging and production.
- **Auth is not configured:** Set `JWT_SECRET_KEY` to a random value of at least
  32 bytes. For verification email, configure SMTP or start Mailpit and use the
  local SMTP settings described above.
- **Auth requests fail while Redis is unavailable:** Authentication rate
  limiting intentionally fails closed. Check Redis connectivity and
  `/api/v1/ready`.
- **PowerShell activation is blocked:** Use the process-scoped execution policy
  command above or call the virtual environment executables directly.
