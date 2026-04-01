# ControlladorIA API

REST API for the ControlladorIA platform. Handles authentication, document processing, accounting reports, billing, and multi-org management.

## Tech Stack

- **Python 3.12** + **FastAPI**
- **SQLAlchemy 2** + **Alembic** (PostgreSQL in prod, SQLite locally)
- **AI**: Gemini Flash Lite (primary) / Amazon Nova via Bedrock (secondary) / GPT-5.4 Nano (fallback)
- **Stripe** for billing, **Resend** for email, **AWS S3** for file storage
- **Redis** for caching + Celery broker

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env              # configure your keys
docker compose up -d              # PostgreSQL 16
alembic upgrade head              # run migrations
uvicorn api:app --reload --port 8000
```

API docs at http://localhost:8000/docs (Swagger) or http://localhost:8000/redoc.

## Key Endpoints

| Prefix | Purpose |
|--------|---------|
| `/auth` | Registration, login, MFA, password reset |
| `/documents` | Upload, list, validate, preview, download |
| `/transactions` | Reports (DRE, balance sheet, cash flow), exports |
| `/organizations` | Multi-org management, invitations |
| `/team` | Team members, invitations |
| `/stripe` | Plans, checkout, portal, webhooks |
| `/admin` | Stats, users, audit logs |
| `/sysadmin` | Dashboard, user search, impersonation |

## Deployment

Deployed on **Railway**. CI/CD via GitHub Actions:
- **Dev**: auto-deploy on push to `main`
- **Prod**: manual `workflow_dispatch`

See `docs/DEPLOYMENT.md` for full details.

## Documentation

See the `docs/` folder for detailed guides:
- [Database Setup](docs/DATABASE_SETUP.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Stripe Setup](docs/STRIPE_SETUP.md)
- [AI Integration](docs/AI_DOCUMENTATION.md)
- [Security](docs/security.md)
- [Admin Guide](docs/ADMIN_GUIDE.md)
- [Incident Runbooks](docs/INCIDENT_RUNBOOKS.md)
