# ControlladorIA — Monolith to Microservices Migration Plan

## Context

The ControlladorIA codebase is a monolith: 1 Next.js frontend (29 pages, 40+ components), 1 sysadmin frontend (already partially separated in `frontend-sysadmin/`), and 1 FastAPI backend (12 router files, 89+ endpoints, 8,245 lines across 6 core files). All business logic lives inline in routers with no service/repository separation.

**Goal**: Split into 6 repositories (5 services + 1 shared library) with proper service/repository layers, deployed independently. Phased approach starting with frontends (lowest risk), ending with API refactoring (highest complexity).

---

## Target Repositories

| # | Repository | Purpose | Tech |
|---|-----------|---------|------|
| 0 | `controlladoria-shared` | Shared Python package (models, schemas, config, auth deps) | Python package |
| 1 | `controlladoria-ui` | Regular user frontend | Next.js 16 |
| 2 | `controlladoria-sysadmin-ui` | Platform admin frontend | Next.js 16 |
| 3 | `controlladoria-auth` | Auth microservice (login, MFA, sessions, email verification) | FastAPI |
| 4 | `controlladoria-jobs` | Scheduled background jobs | Python + APScheduler |
| 5 | `controlladoria-api` | Business API (documents, reports, billing, clients) | FastAPI |

---

## Current Backend File Inventory

### Routers (`routers/`)
| File | Lines | Destination |
|------|-------|-------------|
| `auth.py` | 749 | `controlladoria-auth` |
| `sessions.py` | 117 | `controlladoria-auth` |
| `team.py` | 355 | `controlladoria-auth` |
| `account.py` | 181 | `controlladoria-auth` |
| `documents.py` | 3,179 | `controlladoria-api` |
| `transactions.py` | 2,278 | `controlladoria-api` |
| `billing.py` | 167 | `controlladoria-api` |
| `admin.py` | 362 | `controlladoria-api` |
| `contact.py` | 150 | `controlladoria-api` |
| `dependencies.py` | 51 | `controlladoria-shared` |

### Auth Module (`auth/`)
| File | Destination |
|------|-------------|
| `dependencies.py` (160 lines) | `controlladoria-shared` (JWT verification needed by all services) |
| `permissions.py` | `controlladoria-shared` |
| `security.py` | `controlladoria-shared` |
| `models.py` | `controlladoria-shared` (Pydantic schemas) |
| `service.py` | `controlladoria-auth` |
| `mfa_service.py` | `controlladoria-auth` |
| `session_manager.py` | `controlladoria-auth` |
| `team_management.py` | `controlladoria-auth` |
| `encryption.py` | `controlladoria-auth` |
| `api_key.py` | `controlladoria-auth` |
| `sysadmin_auth.py` | `controlladoria-api` (sysadmin routes stay in API) |

### Core Files
| File | Lines | Destination |
|------|-------|-------------|
| `api.py` | 888 | Stripped down → `controlladoria-api/main.py` (jobs extracted, background tasks to services) |
| `database.py` | 991 | Split → `controlladoria-shared/models/` (individual model files) |
| `config.py` | — | `controlladoria-shared` |
| `api_sysadmin.py` | 581 | `controlladoria-api` |
| `database_sysadmin.py` | 401 | `controlladoria-shared/models/sysadmin.py` |
| `email_service.py` | — | `controlladoria-shared` |
| `storage.py` | — | `controlladoria-api` |

### Accounting Module (`accounting/` — 14 files)
All stay in `controlladoria-api`:
`accounting_engine.py`, `balance_sheet_calculator.py`, `balance_sheet_exports.py`, `cash_flow.py`, `cash_flow_calculator.py`, `cash_flow_daily.py`, `cash_flow_exports.py`, `categories.py`, `chart_of_accounts.py`, `dre_calculator.py`, `dre_exports.py`, `dre_models.py`

---

## Key Architectural Decisions

### 1. Shared Database (Single PostgreSQL)
All services share the same PostgreSQL database. Rationale:
- Models have extensive foreign key relationships (User → Document → Client → KnownItem)
- Splitting the DB would replace FK joins with HTTP calls, adding latency to every report query
- `get_accessible_user_ids` multi-tenant function JOINs the `users` table and is called by nearly every endpoint
- Accounting engine queries span `documents`, `chart_of_accounts`, `journal_entries` in single transactions

**Mitigation**: Each service imports only the models it needs. Pool sizes distributed: API=30, Auth=10, Jobs=5.

### 2. JWT Tokens Are Self-Contained (No inter-service HTTP calls)
The `verify_token` function only needs `JWT_SECRET_KEY` and `JWT_ALGORITHM` from config. Both services can validate tokens independently using the shared `security.py`. Session validation works because both services read from the same `user_sessions` table.

**Result**: This is a "modular monolith deployed as separate processes" — independently deployable but no HTTP inter-service calls needed.

### 3. Billing Stays in API (Not a Separate Service)
`routers/billing.py` (167 lines, 6 endpoints) is tightly coupled to:
- User registration (trial creation in `auth/service.py`)
- Business endpoints (`require_active_subscription` middleware on documents/transactions)
- Webhook handler updating `Subscription` table

Separating billing would add complexity without proportional benefit.

### 4. `/admin/*` Pages Stay in `controlladoria-ui`
The `/admin/*` pages are **organization admin** (tenant-scoped, use `get_accessible_user_ids`), NOT platform sysadmin. The `frontend-sysadmin/` is the platform-wide sysadmin interface. These are fundamentally different concerns.

### 5. Alembic Migrations Stay Centralized
Only ONE service runs `alembic upgrade head` on startup (the API service). Migration chain stays in `controlladoria-shared` or `controlladoria-api`.

---

## Phase 0: Extract Shared Package (1-2 days)

**Goal**: Create `controlladoria-shared` as a pip-installable Python package. No changes to the monolith yet.

### Structure
```
controlladoria-shared/
  controlladoria_shared/
    __init__.py
    database.py           # Engine, SessionLocal, Base, get_db (from database.py, strip init_db)
    config.py             # Settings (from config.py)
    security.py           # JWT create/verify, password hash (from auth/security.py)
    permissions.py        # Permission enum, Role enum, ROLE_PERMISSIONS (from auth/permissions.py)
    dependencies.py       # get_current_user, get_admin_user (from auth/dependencies.py)
    categories.py         # DRE categories (from accounting/categories.py)
    email_service.py      # EmailService class (from email_service.py)
    exceptions.py         # Custom exceptions (from exceptions.py)
    exception_handlers.py # Error handlers (from exception_handlers.py)
    i18n.py               # Translations (from i18n.py)
    i18n_errors.py        # Error translations (from i18n_errors.py)
    models/
      __init__.py         # Re-exports all models
      user.py             # User, UserSession, UserClaim, APIKey
      document.py         # Document, DocumentValidationRow, DocumentStatus
      subscription.py     # Subscription, SubscriptionStatus, Plan
      client.py           # Client, KnownItem
      accounting.py       # ChartOfAccountsEntry, JournalEntry, JournalEntryLine
      audit.py            # AuditLog
      contact.py          # ContactSubmission
      auth.py             # PasswordReset, TeamInvitation
      sysadmin.py         # SystemAdmin, ImpersonationSession, etc.
    schemas/
      __init__.py
      auth.py             # Pydantic schemas (from auth/models.py)
      documents.py        # Document schemas (from models.py Pydantic classes)
  setup.py / pyproject.toml
```

### Steps
1. Create new repository with the structure above
2. Copy (NOT move) files from monolith into shared package
3. Split `database.py` model classes into individual files under `models/`
4. Ensure `models/__init__.py` re-exports everything: `from controlladoria_shared.models.user import User, UserSession` etc.
5. Verify: `pip install -e .` and `python -c "from controlladoria_shared.models import User, Document"` works
6. Do NOT modify the monolith yet

### Installation Strategy
```bash
# Development: editable install
pip install -e ../controlladoria-shared

# Production: install from git
controlladoria-shared @ git+https://github.com/org/controlladoria-shared.git@v0.1.0
```

**Deliverable**: Working pip-installable shared package. Monolith unchanged.

---

## Phase 1: Split the Two Frontends (2 days)

Lowest risk — frontends communicate with backend only via HTTP. No shared runtime state.

### Phase 1A: Extract `controlladoria-sysadmin-ui` (0.5 days)

This is nearly done — `frontend-sysadmin/` already has its own `package.json`, `next.config.js`, pages, and components.

**Steps**:
1. Create new repository `controlladoria-sysadmin-ui/`
2. Copy entire `frontend-sysadmin/` directory into it
3. Verify: `npm install && npm run build`
4. Set up deployment (Vercel) with `NEXT_PUBLIC_API_URL` → same backend
5. Remove `frontend-sysadmin/` from monolith

**Files to copy**:
- `frontend-sysadmin/app/` — all pages (login, dashboard, users, etc.)
- `frontend-sysadmin/components/` — ImpersonationBanner.tsx, Sidebar.tsx
- `frontend-sysadmin/contexts/`
- `frontend-sysadmin/lib/api.ts`
- All config files: package.json, next.config.js, tsconfig.json, tailwind.config.ts, postcss.config.js

### Phase 1B: Extract `controlladoria-ui` (1.5 days)

**Steps**:
1. Create new repository `controlladoria-ui/`
2. Copy entire `frontend/` directory into it
3. `/admin/*` pages STAY (they are org-admin, not sysadmin)
4. Remove `lib/sysadmin-api.ts` if present (not needed in user UI)
5. Verify: `npm install && npm run build`
6. Set up deployment with `NEXT_PUBLIC_API_URL` → same backend

**Files to copy** (everything under `frontend/`):
- `app/` — all 23+ page directories
- `components/` — all 40+ components
- `contexts/` — AuthContext, SubscriptionContext, ThemeContext, FontSizeContext, ClientContext
- `lib/` — api.ts, auth-api.ts, subscription-api.ts, stripe.ts, utils.ts, etc.
- `public/` — logos, favicon
- Config files: package.json, next.config.ts, tsconfig.json, tailwind.config.ts

**Deliverable**: Both frontends running independently, both pointing to the monolith API. Frontend directories removed from monolith.

---

## Phase 2: Extract `controlladoria-auth` (3-5 days)

Auth is the most clearly bounded context — well-defined inputs (credentials) and outputs (JWT tokens).

### Structure
```
controlladoria-auth/
  auth_app/
    __init__.py
    main.py                 # FastAPI app, CORS, health check
    routers/
      __init__.py
      auth.py               # Register, login, logout, MFA, email verification, password reset
      sessions.py           # Session management
      account.py            # Profile update, preferences, password change
      team.py               # Team invitations, member management
    services/
      __init__.py
      auth_service.py       # From auth/service.py (668 lines)
      mfa_service.py        # From auth/mfa_service.py
      session_service.py    # From auth/session_manager.py
      team_service.py       # From auth/team_management.py
      encryption_service.py # From auth/encryption.py
      api_key_service.py    # From auth/api_key.py
    middleware/
      rate_limiting.py
  requirements.txt
  Procfile / Dockerfile
```

### File Migration Map
| Source (monolith) | Destination |
|---|---|
| `routers/auth.py` (749 lines) | Split: `auth_app/routers/auth.py` (thin controller ~200 lines) + `auth_app/services/auth_service.py` |
| `routers/sessions.py` (117 lines) | `auth_app/routers/sessions.py` |
| `routers/account.py` (181 lines) | `auth_app/routers/account.py` |
| `routers/team.py` (355 lines) | Split: `auth_app/routers/team.py` (thin ~100 lines) + `auth_app/services/team_service.py` |
| `auth/service.py` (668 lines) | `auth_app/services/auth_service.py` |
| `auth/mfa_service.py` | `auth_app/services/mfa_service.py` |
| `auth/session_manager.py` | `auth_app/services/session_service.py` |
| `auth/team_management.py` | `auth_app/services/team_service.py` |
| `auth/encryption.py` | `auth_app/services/encryption_service.py` |
| `auth/api_key.py` | `auth_app/services/api_key_service.py` |

### Endpoints Moving to Auth Service
- `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/refresh-token`
- `POST /auth/verify-email`, `/auth/resend-verification`
- `POST /auth/password-reset/request`, `/auth/password-reset/confirm`
- `GET /auth/me`, `PUT /auth/me`, `PUT /auth/me/change-password`
- `PUT /auth/me/theme`, `/auth/me/font-size`, `/auth/me/report-tab-order`
- MFA: `POST /auth/mfa/setup`, `/auth/mfa/enable`, `/auth/mfa/verify`, `/auth/mfa/disable`
- `GET /auth/mfa/backup-codes`, `POST /auth/mfa/verify-login`
- Sessions: `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions`
- Team: `GET /team/members`, `POST /team/invite`, `DELETE /team/members/{id}`, `POST /team/invitations/{token}/accept`

### Import Changes
```python
# Old (monolith)
from auth.dependencies import get_current_active_user
from auth.permissions import get_accessible_user_ids
from database import User, get_db
from config import settings

# New (all services)
from controlladoria_shared.dependencies import get_current_active_user
from controlladoria_shared.permissions import get_accessible_user_ids
from controlladoria_shared.models import User
from controlladoria_shared.database import get_db
from controlladoria_shared.config import settings
```

### Frontend API Routing Update
```typescript
// frontend/lib/auth-api.ts
const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL || 'http://localhost:8001';
const authApi = axios.create({ baseURL: AUTH_API_URL });
```

### Transition Strategy
1. Deploy `controlladoria-auth` on its own URL (e.g., `auth.controlladoria.com.br`)
2. Keep auth routes in monolith during transition (deprecation logging)
3. Add feature flag: `NEXT_PUBLIC_AUTH_SEPARATE=true` to toggle frontend routing
4. Update frontend to point auth calls to new service
5. Verify all auth flows work (login, register, MFA, password reset, email verification)
6. Remove auth routes from monolith

**Deliverable**: Auth microservice running independently. Frontend authenticates against auth service. API validates tokens locally via shared JWT secret.

---

## Phase 3: Extract `controlladoria-jobs` (1-2 days)

Simplest extraction — self-contained functions with no HTTP interface.

### Structure
```
controlladoria-jobs/
  jobs/
    __init__.py
    main.py               # APScheduler setup (from api.py lines 703-737)
    file_cleanup.py        # From api.py cleanup_old_files() (lines 271-338)
    token_cleanup.py       # From api.py cleanup_expired_verification_tokens() (lines 342-377)
    trial_expiry.py        # From api.py check_expired_trials (if exists)
  requirements.txt
  Procfile / Dockerfile
```

### Implementation
```python
# jobs/main.py
from apscheduler.schedulers.blocking import BlockingScheduler
from controlladoria_shared.config import settings

scheduler = BlockingScheduler()

from jobs.file_cleanup import cleanup_old_files
from jobs.token_cleanup import cleanup_expired_tokens

scheduler.add_job(cleanup_old_files, 'cron', hour=settings.cleanup_schedule_hour)
scheduler.add_job(cleanup_expired_tokens, 'interval', hours=6)

scheduler.start()
```

### Deployment
```
# Procfile
worker: python -m jobs.main
```

Remove APScheduler and all job functions from monolith's `api.py`.

**Deliverable**: Jobs running as separate process. API server no longer runs scheduled tasks.

---

## Phase 4: Refactor Monolith into `controlladoria-api` with Service/Repository Pattern (5-7 days)

The remaining monolith (minus auth, jobs, frontends) gets restructured with proper service/repository layers.

### Target Structure
```
controlladoria-api/
  api_app/
    __init__.py
    main.py                       # Lean FastAPI app (~150 lines, from 888)
    routers/                      # Thin controllers (HTTP concerns only)
      documents.py                # ~200 lines (from 3,179)
      transactions.py             # ~150 lines (from 2,278)
      reports.py                  # ~200 lines (split from transactions.py)
      billing.py                  # ~80 lines (from 167)
      admin.py                    # ~100 lines (from 362)
      contact.py                  # ~60 lines (from 150)
      sysadmin.py                 # From api_sysadmin.py
    services/                     # Business logic
      document_service.py         # Upload, process, validate, CRUD (~800 lines)
      report_service.py           # DRE, balance sheet, cash flow, summaries
      transaction_service.py      # Stats, category management, known items, AI categorization
      billing_service.py          # Stripe checkout, webhook, portal
      client_service.py           # Client CRUD, merge, transfer
      contact_service.py          # Contact form, notifications
      admin_service.py            # Org admin stats, user management
      sysadmin_service.py         # Platform admin operations
    repositories/                 # Data access only
      document_repository.py      # Document queries
      transaction_repository.py   # Transaction aggregation queries
      client_repository.py        # Client queries
      subscription_repository.py  # Subscription queries
      audit_repository.py         # Audit log queries
      contact_repository.py       # Contact submission queries
  accounting/                     # Full accounting module (unchanged)
    accounting_engine.py
    balance_sheet_calculator.py, balance_sheet_exports.py
    cash_flow_calculator.py, cash_flow_exports.py, cash_flow.py, cash_flow_daily.py
    dre_calculator.py, dre_exports.py, dre_models.py
    chart_of_accounts.py, categories.py
  processors/
    document_processor.py         # From structured_processor.py
  storage/
    s3_service.py
  tasks/
    queue_manager.py
  middleware/
    subscription.py
  requirements.txt
  Procfile / Dockerfile
```

### Router → Service → Repository Pattern Example

**Thin Router** (HTTP concerns only):
```python
# routers/documents.py - ~200 lines total
@router.post("/upload")
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return await document_service.upload(file, current_user, background_tasks, db)
```

**Service** (business logic):
```python
# services/document_service.py
class DocumentService:
    def __init__(self, repo: DocumentRepository, processor, storage):
        self.repo = repo
        self.processor = processor
        self.storage = storage

    async def upload(self, file, user, background_tasks, db):
        # Validation, file storage, queue management, background processing
        doc = self.repo.create(db, filename=file.filename, user_id=user.id, ...)
        background_tasks.add_task(self.process_background, doc.id)
        return doc
```

**Repository** (data access only):
```python
# repositories/document_repository.py
class DocumentRepository:
    def get_by_id(self, db, doc_id, user_ids) -> Document | None
    def list_filtered(self, db, user_ids, filters, skip, limit) -> tuple[list, int]
    def create(self, db, **kwargs) -> Document
    def update_status(self, db, doc_id, status) -> Document
```

### Refactoring Map for `routers/documents.py` (3,179 lines)

| Approx Lines | Functionality | → Service | → Repository |
|---|---|---|---|
| 100-400 | Upload (single, bulk) | `document_service.upload()` | `document_repository.create()` |
| 400-600 | List documents | `document_service.list()` | `document_repository.list_filtered()` |
| 600-800 | Get/update/delete | `document_service.get/update/delete()` | `document_repository.get_by_id()` |
| 800-1100 | Validation flow | `document_service.validate()` | `document_repository.get_validation_rows()` |
| 1100-1500 | CSV upload | `document_service.upload_csv()` | Same |
| 1500-2000 | Reprocess, NFe cancel | `document_service.reprocess()` | Same |
| 2000-2500 | Known items, audit | `document_service.audit_trail()` | `audit_repository.get_for_document()` |
| 2500-3179 | Download, preview | `document_service.download()` | `document_repository.get_file_path()` |

### Refactoring Map for `routers/transactions.py` (2,278 lines)

| Approx Lines | Functionality | → Service | → Repository |
|---|---|---|---|
| 1-93 | `/stats` | `transaction_service.get_stats()` | `transaction_repository.count_by_status()` |
| 96-250 | `/reports/summary` | `report_service.get_financial_summary()` | `transaction_repository.aggregate_by_date_range()` |
| 253-400 | `/reports/by-category` | `report_service.get_category_breakdown()` | `transaction_repository.aggregate_by_category()` |
| 403-550 | `/reports/monthly` | `report_service.get_monthly_report()` | `transaction_repository.aggregate_monthly()` |
| 553-700 | `/reports/chart-data` | `report_service.get_chart_data()` | Same repos |
| 700-1100 | DRE endpoints (5) | `report_service.calculate_dre()` | Uses `accounting/dre_calculator.py` |
| 1100-1400 | Balance sheet (5) | `report_service.calculate_balance_sheet()` | Uses `accounting/balance_sheet_calculator.py` |
| 1400-1700 | Cash flow (5) | `report_service.calculate_cash_flow()` | Uses `accounting/cash_flow_calculator.py` |
| 1700-1950 | Ledger/accounting | `report_service.get_trial_balance()` | `transaction_repository.get_journal_entries()` |
| 1950-2278 | Categories, known items, AI | `transaction_service.manage_categories()` | `transaction_repository.get_known_items()` |

### `api.py` Cleanup (888 → ~150 lines)

Move out of `api.py`:
- Job functions (~100 lines) → already extracted in Phase 3
- `process_document_background` (~130 lines) → `document_service.process_background()`
- `find_or_create_client` (~70 lines) → `client_service.find_or_create()`
- `log_audit_trail` (~50 lines) → `audit_repository.log()`
- `get_client_ip` (~15 lines) → utility function

Keep in `main.py`:
- FastAPI app creation, CORS config, security middleware, health endpoints, router mounting

**Deliverable**: Clean API service with service/repository layers. Every router under 300 lines. Business logic testable in isolation.

---

## Environment & Deployment

### Service Configuration

| Service | Command | Port | Deploy |
|---|---|---|---|
| `controlladoria-api` | `uvicorn api_app.main:app --host 0.0.0.0 --port $PORT` | 8000 | Railway |
| `controlladoria-auth` | `uvicorn auth_app.main:app --host 0.0.0.0 --port $PORT` | 8001 | Railway |
| `controlladoria-jobs` | `python -m jobs.main` | N/A | Railway (worker) |
| `controlladoria-ui` | Next.js | N/A | Vercel |
| `controlladoria-sysadmin-ui` | Next.js | N/A | Vercel |

### Shared Environment Variables (all backend services)
```env
DATABASE_URL=postgresql://...        # Same DB for all
JWT_SECRET_KEY=...                   # Same secret for token verification
ENVIRONMENT=production
```

### Service-Specific Variables
```env
# Auth
RESEND_API_KEY=...
STRIPE_TRIAL_DAYS=15

# API
OPENAI_API_KEY=...
AWS_ACCESS_KEY_ID=..., AWS_SECRET_ACCESS_KEY=..., S3_BUCKET_NAME=...
STRIPE_API_KEY=..., STRIPE_WEBHOOK_SECRET=...

# Frontend
NEXT_PUBLIC_API_URL=https://api.controlladoria.com.br
NEXT_PUBLIC_AUTH_API_URL=https://auth.controlladoria.com.br
```

---

## Risk Mitigation & Rollback

| Risk | Mitigation |
|---|---|
| Shared package version drift | Semver. All services pin same version. CI checks. |
| DB connection pool exhaustion | Split pool sizes: API=30, Auth=10, Jobs=5. |
| Frontend routing confusion | Feature flag `NEXT_PUBLIC_AUTH_SEPARATE=true` to toggle. |
| Import path changes break things | Automated find-and-replace per phase. Full test suite after each step. |
| Token incompatibility | Both services use identical JWT_SECRET_KEY from shared config. |
| Deployment ordering | Deploy order: Auth → API → Jobs. Frontends anytime. |

### Rollback Per Phase
- **Phase 0**: Delete shared package. Monolith unchanged.
- **Phase 1**: Re-deploy monolith frontend.
- **Phase 2**: Toggle frontend back to monolith auth URL. Remove auth service.
- **Phase 3**: Re-add APScheduler to API startup. Remove jobs service.
- **Phase 4**: Standard git revert (internal refactoring).

---

## Timeline

| Phase | Duration | Risk | Can Parallelize With |
|---|---|---|---|
| Phase 0: Shared package | 1-2 days | Low | Phase 1 |
| Phase 1A: Sysadmin UI | 0.5 days | Very Low | Phase 0 |
| Phase 1B: User UI | 1.5 days | Low | Phase 0 |
| Phase 2: Auth service | 3-5 days | Medium | Phase 3 |
| Phase 3: Jobs service | 1-2 days | Low | Phase 2 |
| Phase 4: API refactor | 5-7 days | Medium | — (depends on 0, 2, 3) |
| **Total** | **12-18 days** | | |

---

## Verification Checklist

- [ ] Phase 0: `pip install -e .` works, `from controlladoria_shared.models import User, Document` succeeds
- [ ] Phase 1: Both frontends build (`npm run build`) and connect to monolith API
- [ ] Phase 2: Auth service handles full login → MFA → session flow. API validates tokens from auth service.
- [ ] Phase 3: Jobs run on schedule. Check logs for cleanup/expiry activity.
- [ ] Phase 4: `pytest tests/` passes. All endpoints return correct responses. Routers < 300 lines each.
- [ ] End-to-end: User can register (auth) → login (auth) → upload document (API) → view reports (API) → manage subscription (API)
