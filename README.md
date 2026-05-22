# controlladoria-api

Core REST API for the ControlladorIA platform. Handles authentication, document ingestion, AI extraction, financial report generation, multi-org management, and Stripe billing.

- **Runtime:** Python 3.12 + FastAPI 0.109+
- **Database:** PostgreSQL 16 (prod) / SQLite (dev) via SQLAlchemy 2 + Alembic
- **Deployed on:** Railway (auto-deploy on push to `main`; manual `workflow_dispatch` for prod)
- **API docs:** `/docs` (Swagger UI) · `/redoc` (ReDoc)

---

## Architecture

```
HTTP Request
    │
    ├── CORS middleware (CORSMiddleware)
    ├── CSRF check (production only, state-changing methods)
    ├── HSTS header injection (production only)
    ├── Rate limiter (slowapi)
    │
    ├── /auth/*          ← JWT auth, MFA, password reset
    ├── /documents/*     ← upload, extraction, validation
    ├── /transactions/*  ← reports, exports, accounting
    ├── /organizations/* ← multi-org management
    ├── /team/*          ← team membership
    ├── /stripe/*        ← billing, checkout, webhooks
    ├── /admin/*         ← org admin tools
    ├── /sysadmin/*      ← platform operator console
    ├── /account/*       ← profile, security, sessions
    ├── /sessions/*      ← session management
    ├── /clients/*       ← supplier/customer CRUD
    ├── /initial-balance/* ← opening balances
    ├── /org-settings/*  ← org-level configuration
    └── /contact         ← public contact form
```

Document processing runs as a background task (FastAPI `BackgroundTasks`) or via SQS → Lambda (controlled by `controlladoria-jobs`). Both paths use the same `StructuredDocumentProcessor`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.109+ |
| Language | Python 3.12 |
| ORM | SQLAlchemy 2 |
| Migrations | Alembic (17 migrations as of v0.4.0) |
| Auth | JWT (HS256) + refresh tokens + MFA (TOTP/OTP) |
| AI — primary | Google Gemini Flash Lite (`gemini-flash-lite-latest`) |
| AI — secondary | Amazon Nova 2 Lite via Bedrock (`us.amazon.nova-2-lite-v1:0`) |
| AI — fallback | OpenAI GPT-5.4 Nano (`gpt-5.4-nano`) |
| File storage | AWS S3 (prod) / local filesystem (dev) |
| Queue | AWS SQS → Lambda (doc processing) |
| Cache | Redis (optional; AI response cache + Celery broker) |
| Email | Resend |
| Billing | Stripe (BRL — PIX, boleto, cartão) |
| Rate limiting | slowapi |
| Validation | Pydantic v2 |
| CNPJ lookup | BrasilAPI (free) / SERPRO (premium) |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET_KEY and DATABASE_URL

# 3. Start PostgreSQL (optional; SQLite used by default in dev)
docker compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Start server
uvicorn api:app --reload --port 8000
```

SQLite is the default in dev (`DATABASE_URL=sqlite:///./controlladoria.db`) — no Postgres needed locally.

---

## Key Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ENVIRONMENT` | yes | `development` or `production` |
| `DATABASE_URL` | yes | PostgreSQL or SQLite connection string |
| `JWT_SECRET_KEY` | yes | 64-char hex (`openssl rand -hex 32`) |
| `ENCRYPTION_KEY` | rec. | Fernet key for MFA secrets |
| `AI_PROVIDER` | yes | `gemini`, `nova`, or `openai` (default: `gemini`) |
| `GEMINI_API_KEYS` | yes* | Comma-separated Gemini keys |
| `OPENAI_API_KEYS` | yes* | Comma-separated OpenAI keys (fallback) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | prod | S3, SQS, Bedrock (Nova) |
| `S3_BUCKET_NAME` | prod | Document file storage |
| `USE_S3` | prod | `true` in prod, `false` for local dev |
| `SQS_DOCUMENT_QUEUE_URL` | prod | SQS queue for Lambda processing |
| `STRIPE_API_KEY` | prod | Stripe secret key (live or test) |
| `STRIPE_WEBHOOK_SECRET` | prod | Webhook signing secret |
| `STRIPE_PRICE_ID_BASIC/PRO/MAX` | prod | Stripe price IDs per plan |
| `RESEND_API_KEY` | prod | Email delivery |
| `FROM_EMAIL` | prod | Sender address |
| `FRONTEND_URL` | prod | Customer UI URL (for email links) |
| `CORS_ORIGINS` | prod | Comma-separated allowed origins |
| `REDIS_URL` | opt. | Redis for AI cache + Celery |
| `FREE_DEMO_MODE` | opt. | `true` bypasses all subscription checks |

*At least one AI provider key must be set.

---

## API Routes

### `/auth` — Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create account (5/hour rate limit) |
| POST | `/auth/login` | Email + password → JWT |
| POST | `/auth/logout` | Invalidate refresh token |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| POST | `/auth/forgot-password` | Send reset email (3/hour) |
| POST | `/auth/reset-password` | Confirm password reset |
| POST | `/auth/verify-email` | Verify email with token |
| GET | `/auth/me` | Current user profile |
| PUT | `/auth/me` | Update profile |
| POST | `/auth/mfa/setup` | Begin TOTP setup |
| POST | `/auth/mfa/enable` | Confirm TOTP with code |
| POST | `/auth/mfa/verify` | Verify MFA during login |
| POST | `/auth/mfa/disable` | Disable MFA |
| GET | `/auth/mfa/status` | MFA enabled/method |
| GET | `/auth/cnpj/{cnpj}` | Lookup company data |

### `/documents` — Document Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents/upload` | Upload single document (PDF/Excel/XML/OFX/image) |
| POST | `/documents/upload/bulk` | Upload multiple documents |
| POST | `/documents/upload/csv` | Upload from CSV manifest |
| GET | `/documents` | List documents (paginated, filtered) |
| GET | `/documents/{id}` | Document detail + extraction status |
| DELETE | `/documents/{id}` | Delete document |
| GET | `/documents/{id}/preview` | Preview extracted data |
| GET | `/documents/{id}/download` | Download original file |
| POST | `/documents/{id}/validate` | Accept extracted rows |
| GET | `/documents/{id}/validation-rows` | List extracted rows |
| PUT | `/documents/{id}/validation-rows/{row_id}` | Edit a row |
| DELETE | `/documents/{id}/validation-rows/{row_id}` | Delete a row |
| POST | `/documents/manual-entry` | Create manual transaction |
| GET | `/documents/queue-status` | Processing queue state |

### `/transactions` — Reports & Exports

| Method | Path | Description |
|--------|------|-------------|
| GET | `/transactions/stats` | Summary stats for dashboard |
| GET | `/transactions/reports/summary` | Totals by category |
| GET | `/transactions/reports/by-category` | Breakdown by accounting category |
| GET | `/transactions/reports/monthly` | Month-by-month trend |
| GET | `/transactions/dre` | DRE (Income Statement) |
| GET | `/transactions/balance-sheet` | Balanço Patrimonial |
| GET | `/transactions/cash-flow` | Fluxo de Caixa |
| GET | `/transactions/trial-balance` | Trial balance |
| GET | `/transactions/ledger` | General ledger |
| GET | `/transactions/chart-of-accounts` | Chart of accounts |
| GET/POST/PUT/DELETE | `/transactions/journal-entries` | Manual journal entries |
| GET/POST/PUT | `/transactions/opening-balances` | Opening balances |
| GET | `/transactions/dashboard-metrics` | Dashboard KPIs |
| GET | `/transactions/dre/export/{format}` | Export DRE (pdf/excel/csv) |
| GET | `/transactions/balance-sheet/export/{format}` | Export balance sheet |
| GET | `/transactions/cash-flow/export/{format}` | Export cash flow |

### Other Routers

| Router | Base | Purpose |
|--------|------|---------|
| Organizations | `/organizations` | Create, list, switch org; send/accept/decline invitations |
| Team | `/team` | List members, invite by email, remove, accept invitation |
| Stripe | `/stripe` | Plans, create-checkout-session, create-portal-session, subscription-status, cancel, webhook |
| Admin | `/admin` | Org stats, user list, recent activity, audit logs, AI pool stats |
| Sysadmin | `/sysadmin` | Platform dashboard, user search, impersonation, error logs |
| Account | `/account` | Profile update, API key management |
| Sessions | `/sessions` | List active sessions, revoke session, trust device |
| Clients | `/clients` | CRUD for suppliers/customers |
| Initial Balance | `/initial-balance` | Status, list, create, update opening balances |
| Org Settings | `/org-settings` | Bank accounts, org preferences |
| Contact | `/contact` | Public contact form submission; admin listing |

---

## Database Entities

| Entity | Purpose |
|--------|---------|
| `User` | Account with MFA, theme prefs, active org pointer |
| `Organization` | Multi-tenant company (CNPJ, address, logo, bank accounts) |
| `OrgMembership` | User ↔ org role mapping |
| `OrgInvitation` | Cross-org invite tokens |
| `Document` | Uploaded file with AI extraction status and S3 key |
| `DocumentValidationRow` | Individual extracted transaction row pending review |
| `ChartOfAccountsEntry` | Accounting ledger structure (52 categories) |
| `JournalEntry` / `JournalEntryLine` | Manual double-entry records |
| `Client` | Supplier/customer per org |
| `KnownItem` | AI categorization cache keyed by description |
| `Subscription` / `Plan` | Stripe billing state, plan tier, seat limits |
| `OrgBankAccount` | Bank accounts per org |
| `OrgInitialBalance` | Opening balances per fiscal year |
| `UserSession` | Active session tracking (device, IP, trusted) |
| `UserClaim` | Custom permission grants |
| `APIKey` | Programmatic access tokens |
| `AuditLog` | Compliance trail for sensitive actions |
| `ContactSubmission` | Website contact form data |
| `PasswordReset` | Reset tokens |

---

## Document Processing Flow

```
POST /documents/upload
  └── Validate (size ≤ 30MB, extension, MIME type, CNPJ if NFe)
      └── Save to S3 (or local /uploads)
          └── Create Document record (status: PENDING)
              └── Enqueue to DocumentQueueManager (max 3 concurrent)
                      OR send SQS message → Lambda (controlladoria-jobs)
                  └── StructuredDocumentProcessor:
                      ├── Detect format (PDF / Excel / XML / OFX / image)
                      ├── AI extraction (primary → secondary → fallback)
                      ├── Parse: dates, amounts, descriptions, categories
                      ├── Create DocumentValidationRows (status: PENDING_VALIDATION)
                      ├── Batch categorize remaining "nao_categorizado" rows
                      └── AI audit pass (review all categories before user sees them)
                  └── Status → PENDING_VALIDATION
User → /validation → review rows → bulk accept/edit/reject
  └── Status → COMPLETED → transactions available in reports
```

### Supported Formats

| Format | Details |
|--------|---------|
| PDF | Bank statements, invoices, receipts — OCR + structured extraction |
| Excel (.xlsx/.xls) | Bank exports, spreadsheets |
| XML | NFe, NFSe, CTe (official Brazilian fiscal documents) |
| OFX / OFC | Bank extract format (Open Financial Exchange) — transfer detection included |
| Images | JPG, PNG, WEBP — OCR extraction |
| Word | .doc, .docx |
| Text | .txt |

### AI Pipeline

Three providers form a cascade. If all keys for provider N fail, the system auto-switches to provider N+1:

```
Gemini Flash Lite (google.genai)  ← primary, cheapest
       ↓ on failure
Nova 2 Lite (AWS Bedrock)         ← secondary, IAM auth
       ↓ on failure
GPT-5.4 Nano (openai)             ← tertiary fallback
```

Each provider has a key pool (comma-separated in env) with per-key health tracking. Keys are marked unhealthy after 3 consecutive errors and recover after 5 minutes.

---

## Financial Reports

All reports are generated on-the-fly from validated `DocumentValidationRow` records:

| Report | Endpoint | Exports |
|--------|----------|---------|
| DRE (Income Statement) | `GET /transactions/dre` | PDF, Excel, CSV |
| Balanço Patrimonial (Balance Sheet) | `GET /transactions/balance-sheet` | PDF, Excel, CSV |
| Fluxo de Caixa (Cash Flow) | `GET /transactions/cash-flow` | PDF, Excel, CSV |

All reports support `?start_date=&end_date=` filtering and are org-scoped. The DRE maps 52 accounting categories to standard Brazilian accounting structure.

---

## Authorization Model

### Org Roles

| Role | Access |
|------|--------|
| `owner` | Full access including billing and org deletion |
| `admin` | All operations except org deletion |
| `accountant` | Documents, reports, validation, team view |
| `bookkeeper` | Upload + validate documents only |
| `viewer` | Read-only reports |
| `api_user` | Programmatic access via API key |

### Auth Dependencies (FastAPI)

| Dependency | Purpose |
|------------|---------|
| `get_current_active_user` | Validates JWT, returns `User` |
| `get_current_admin_user` | Requires admin/owner role |
| `require_active_subscription` | Enforces billing (skipped if `FREE_DEMO_MODE=true`) |

---

## Deployment

### Railway (CI/CD via GitHub Actions)

```
Push to main → deploy-dev.yml → Railway dev service
workflow_dispatch ("deploy") → deploy-prod.yml → Railway prod service
```

`railway.json` start command:
```
python create_database.py && alembic upgrade head && uvicorn api:app --host 0.0.0.0 --port $PORT
```

Migrations run automatically on every deploy before the server starts.

### Required GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `RAILWAY_TOKEN_DEV` | Dev Railway token |
| `RAILWAY_TOKEN_PROD` | Prod Railway token |

### First-Time Setup

```bash
# After first deploy, create the platform admin account:
python create_sysadmin.py
```

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /auth/register` | 5/hour per IP |
| `POST /auth/forgot-password` | 3/hour per IP |
| `POST /documents/upload` | 300/minute |
| `POST /contact` | 5/hour per IP |

---

## Documentation

| Guide | Path |
|-------|------|
| Database Setup | `docs/DATABASE_SETUP.md` |
| Deployment | `docs/DEPLOYMENT.md` |
| Stripe Setup | `docs/STRIPE_SETUP.md` |
| AI Integration | `docs/AI_DOCUMENTATION.md` |
| Security | `docs/security.md` |
| Admin Guide | `docs/ADMIN_GUIDE.md` |
| Incident Runbooks | `docs/INCIDENT_RUNBOOKS.md` |
| Financial Reports | `docs/financial-reports.md` |
| Project Charter | `docs/PROJECT_CHARTER.md` |
| Maintenance Plan | `docs/MAINTENANCE_PLAN.md` |
| Risk Register | `docs/RISK_REGISTER.md` |
