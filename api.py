"""
Week 2: FastAPI Backend
Endpoints for document upload, processing, and retrieval
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Union


# Custom JSON encoder to handle Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import is_auth_enabled, verify_api_key
from auth.dependencies import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    get_optional_user,
)
from auth.models import (
    MFAEnableRequest,
    MFAEnableResponse,
    MFARequiredResponse,
    MFASetupResponse,
    MFAStatusResponse,
    MFAVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from auth.service import AuthService
from auth.permissions import get_accessible_user_ids, require_permission, Permission
from config import settings
from database import (
    ContactSubmission,
    Document,
    DocumentStatus,
    Subscription,
    User,
    get_db,
    init_db,
)
from email_service import email_service
from exception_handlers import (
    database_exception_handler,
    controlladoria_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    rate_limit_exception_handler,
    validation_exception_handler,
)
from exceptions import ControlladorIAException
from i18n import msg
from middleware.subscription import require_active_subscription
from models import (
    ContactFormResponse,
    ContactFormSubmission,
    DocumentListResponse,
    DocumentRecord,
    DocumentUploadResponse,
    FinancialDocument,
    TransactionLedger,
)
from storage.s3_service import s3_storage  # S3 file storage for horizontal scaling
from stripe_integration import StripeClient, StripeService, handle_webhook_event
from structured_processor import StructuredDocumentProcessor
from validators import FinancialDataValidator

# System Admin (separate infrastructure for business operators)
from api_sysadmin import router as sysadmin_router

# Import customer routers (modular architecture with SoC/SOLID principles)
from routers import (
    account_router,
    admin_router,
    auth_router,
    billing_router,
    contact_router,
    documents_router,
    initial_balance_router,
    organizations_router,
    org_settings_router,
    sessions_router,
    team_router,
    transactions_router,
)

# Try to import magic for MIME type validation (optional on Windows)
try:
    import magic

    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logging.warning("python-magic not available, using extension-based validation only")

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiter to app state
app.state.limiter = limiter

# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

# Register custom exception handlers
app.add_exception_handler(ControlladorIAException, controlladoria_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)  # Catch-all

# CORS middleware for frontend integration
# CORS Configuration
# Allow customer frontend + sysadmin subdomain
cors_origins = settings.cors_origins.copy() if settings.cors_origins != ["*"] else ["*"]

# Add sysadmin subdomains explicitly (for production)
if settings.environment == "production":
    cors_origins = [
        "https://controllad oria.com.br",
        "https://www.controllad oria.com.br",
        "https://admin.controllad oria.com.br",  # Sysadmin subdomain
        "https://app.controlladoria.com.br",  # Production customer app
    ]
else:
    # Development: Allow both customer (3000) and sysadmin (3001) frontends
    cors_origins = [
        "http://localhost:3000",  # Customer frontend
        "http://localhost:3001",  # Sysadmin frontend
        "*",  # Allow all in dev
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# CSRF protection middleware
# Since this API uses JWT in Authorization header (not cookies), CSRF risk is low.
# This adds defense-in-depth by requiring X-Requested-With on mutating requests
# in production. Browsers block this header on cross-origin form submissions.
@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Block potential CSRF on state-changing requests in production."""
    if settings.environment == "production" and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Allow Stripe webhooks (they send their own signature)
        if request.url.path.startswith("/billing/webhook"):
            return await call_next(request)
        # Allow sysadmin routes (separate auth)
        if request.url.path.startswith("/sysadmin"):
            return await call_next(request)
        # Allow public endpoints that don't need CSRF protection
        if request.url.path in ("/auth/register", "/auth/login", "/auth/password-reset/request", "/auth/password-reset/confirm", "/auth/verify-email"):
            return await call_next(request)

        # Require X-Requested-With header on all other mutating requests
        if not request.headers.get("X-Requested-With"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing X-Requested-With header"},
            )

    return await call_next(request)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS Protection (legacy but still useful)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy
    # Allow Swagger UI CDN resources (jsdelivr.net, fastapi.tiangolo.com)
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net",
        "font-src 'self' data: https://cdn.jsdelivr.net",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Only in production: HSTS
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# Uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize processor
processor = StructuredDocumentProcessor()


# Jobs (cleanup_old_files, cleanup_expired_verification_tokens, retry_failed_documents)
# have been extracted to controlladoria-jobs (AWS Lambda + EventBridge)




# =============================================================================
# HELPER FUNCTIONS FOR AUDIT & VALIDATION
# =============================================================================


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, handling proxies safely.

    Only trusts X-Forwarded-For / X-Real-IP when the direct connection
    comes from a known trusted proxy (configured via TRUSTED_PROXY_IPS).
    This prevents attackers from spoofing their IP via headers.
    """
    direct_ip = request.client.host if request.client else "unknown"

    # Only trust proxy headers if the direct connection is from a trusted proxy
    if direct_ip in settings.trusted_proxy_ips:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    return direct_ip


def log_audit_trail(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    before_value: Optional[dict] = None,
    after_value: Optional[dict] = None,
    changes_summary: Optional[str] = None,
    request: Optional[Request] = None,
    document_id: Optional[int] = None,
):
    """
    Log an action to the audit trail

    Args:
        db: Database session
        user_id: ID of user performing action
        action: Action type (create, update, delete)
        entity_type: Type of entity (document, transaction, etc)
        entity_id: ID of the entity being modified
        before_value: State before change (dict)
        after_value: State after change (dict)
        changes_summary: Human-readable summary
        request: FastAPI request object (for IP/user agent)
        document_id: Document ID if action relates to a document
    """
    from database import AuditLog

    # Extract request context if provided
    ip_address = None
    user_agent = None
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:500]  # Truncate to DB limit

    # Convert dicts to JSON strings (handle Decimal types)
    before_json = json.dumps(before_value, cls=DecimalEncoder) if before_value else None
    after_json = json.dumps(after_value, cls=DecimalEncoder) if after_value else None

    # Create audit log entry
    audit_entry = AuditLog(
        user_id=user_id,
        document_id=document_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_value=before_json,
        after_value=after_json,
        changes_summary=changes_summary,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(audit_entry)
    # Note: Caller is responsible for committing the transaction

    logger.info(
        f"📝 Audit: user={user_id} action={action} entity={entity_type}:{entity_id} from {ip_address}"
    )


# find_or_create_client and process_document_background have been
# moved to controlladoria-jobs (Lambda) — document processing now
# happens via SQS → Lambda instead of in-process background tasks


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduled jobs on startup"""
    # Create database if it doesn't exist (PostgreSQL only)
    try:
        from create_database import create_database_if_not_exists

        create_database_if_not_exists()
    except Exception as e:
        logger.error(f"❌ Database creation error: {e}")
        raise RuntimeError(f"Database creation failed: {e}")

    # Run database migrations on startup (safety check)
    try:
        logger.info("🔄 Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"], capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info("✅ Database migrations completed successfully")
        else:
            logger.error(f"❌ Migration failed: {result.stderr}")
            raise RuntimeError(f"Database migration failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ Migration timeout after 30 seconds")
        raise RuntimeError("Database migration timeout")
    except FileNotFoundError:
        logger.warning("⚠️  Alembic not found - skipping migrations (dev mode?)")
    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        raise RuntimeError(f"Database migration error: {e}")

    init_db()
    logger.info("=== ControlladorIA API Started Successfully ===")
    logger.info(f"Upload directory: {UPLOAD_DIR.absolute()}")
    logger.info(f"AI Provider: {os.getenv('AI_PROVIDER', 'openai')}")
    # Check JWT authentication (modern system), not legacy API_KEY
    jwt_enabled = bool(settings.jwt_secret_key and settings.jwt_secret_key not in ["", "your-random-64-character-hex-string-here"])
    logger.info(f"JWT Authentication: {'ENABLED' if jwt_enabled else 'DISABLED'}")
    logger.info(f"Legacy API Key Auth: {'ENABLED' if is_auth_enabled() else 'DISABLED'}")
    # Background jobs (cleanup, token expiry, retry) run via AWS Lambda + EventBridge


# =============================================================================
# MOUNT SYSADMIN ROUTER
# =============================================================================
# Separate API routes for business operators (admin.controllad oria.com.br)
# Completely isolated from customer API with separate authentication
app.include_router(sysadmin_router)
logger.info("✅ System Admin router mounted at /sysadmin")


# =============================================================================
# MOUNT CUSTOMER ROUTERS (Modular Architecture)
# =============================================================================
# Authentication & Sessions
app.include_router(auth_router)
app.include_router(sessions_router)
logger.info("✅ Auth and Sessions routers mounted")

# Core Features
app.include_router(documents_router)
logger.info("✅ Documents router mounted")

# Team, Organizations & Billing
app.include_router(team_router)
app.include_router(organizations_router)
app.include_router(org_settings_router)
app.include_router(initial_balance_router)
app.include_router(billing_router)
logger.info("Team, Organizations, Org Settings, Initial Balance, and Billing routers mounted")

# Admin & Contact
app.include_router(admin_router)
app.include_router(contact_router)
logger.info("✅ Admin and Contact routers mounted")

# Account Management & Transactions/Reports
app.include_router(account_router)
app.include_router(transactions_router)
logger.info("✅ Account and Transactions routers mounted")


# =============================================================================
# CUSTOMER API ROUTES
# =============================================================================
# All business endpoints have been extracted to modular routers
# Only health checks and system endpoints remain below

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": msg["api_running"],
        "status": "online",
        "version": settings.api_version,
        "language": "pt-BR",
        "environment": settings.environment,
    }


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check endpoint
    Checks database, disk space, and system status
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.api_version,
        "checks": {},
    }

    # Check database connection
    try:
        db.execute("SELECT 1")
        health_status["checks"]["database"] = {"status": "ok", "message": "Connected"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {"status": "failed", "message": str(e)}
        logger.error(f"Health check: Database failed - {e}")

    # Check disk space
    try:
        total, used, free = shutil.disk_usage(UPLOAD_DIR)
        free_gb = free / (1024**3)

        if free_gb < 1:  # Less than 1GB free
            health_status["status"] = "degraded"
            health_status["checks"]["disk_space"] = {
                "status": "low",
                "free_gb": round(free_gb, 2),
                "message": "Low disk space",
            }
        else:
            health_status["checks"]["disk_space"] = {
                "status": "ok",
                "free_gb": round(free_gb, 2),
            }
    except Exception as e:
        health_status["checks"]["disk_space"] = {"status": "unknown", "message": str(e)}

    # Check uploads directory
    try:
        if not UPLOAD_DIR.exists():
            health_status["status"] = "unhealthy"
            health_status["checks"]["uploads_dir"] = {"status": "missing"}
        else:
            health_status["checks"]["uploads_dir"] = {"status": "ok"}
    except Exception as e:
        health_status["checks"]["uploads_dir"] = {"status": "error", "message": str(e)}

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    return {"ready": True, "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"alive": True, "timestamp": datetime.utcnow().isoformat()}


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================




# =============================================================================
# DOCUMENT ENDPOINTS - MOVED TO routers/documents.py
# =============================================================================



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
