"""
Organization Settings Router
Handles:
- Organization company info (CNPJ data, address, etc.) — editable by owner/admin
- Bank accounts CRUD
- BrasilAPI bank code lookup proxy
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from database import OrgBankAccount, Organization, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/org-settings", tags=["Organization Settings"])

# Cache for BrasilAPI bank list (refreshed hourly)
_banks_cache: Optional[List[Dict[str, Any]]] = None
_banks_cache_time: Optional[datetime] = None
BANKS_CACHE_TTL_SECONDS = 3600  # 1 hour


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class CompanyInfoResponse(BaseModel):
    id: int
    company_name: str
    cnpj: str
    trade_name: Optional[str] = None
    cnae_code: Optional[str] = None
    cnae_description: Optional[str] = None
    company_address_street: Optional[str] = None
    company_address_number: Optional[str] = None
    company_address_complement: Optional[str] = None
    company_address_district: Optional[str] = None
    company_address_city: Optional[str] = None
    company_address_state: Optional[str] = None
    company_address_zip: Optional[str] = None
    capital_social: Optional[float] = None
    company_size: Optional[str] = None
    legal_nature: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_status: Optional[str] = None
    company_opened_at: Optional[str] = None
    is_simples_nacional: Optional[bool] = None
    is_mei: Optional[bool] = None
    regime_tributario: Optional[str] = None
    main_partner_name: Optional[str] = None


class CompanyInfoUpdate(BaseModel):
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    company_address_street: Optional[str] = None
    company_address_number: Optional[str] = None
    company_address_complement: Optional[str] = None
    company_address_district: Optional[str] = None
    company_address_city: Optional[str] = None
    company_address_state: Optional[str] = None
    company_address_zip: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    regime_tributario: Optional[str] = None
    capital_social: Optional[float] = None


class BankAccountCreate(BaseModel):
    bank_code: str
    bank_name: str
    agency: str
    account_number: str
    account_type: str = "checking"  # checking / savings / investment
    account_nickname: Optional[str] = None


class BankAccountUpdate(BaseModel):
    bank_code: Optional[str] = None
    bank_name: Optional[str] = None
    agency: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[str] = None
    account_nickname: Optional[str] = None


class BankAccountResponse(BaseModel):
    id: int
    bank_code: str
    bank_name: str
    agency: str
    account_number: str
    account_type: str
    account_nickname: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BankLookupResponse(BaseModel):
    ispb: str
    name: str
    code: Optional[int] = None
    full_name: str


# =============================================================================
# HELPERS
# =============================================================================


def _get_org_id(user: User) -> Optional[int]:
    """Get the active organization ID for the user."""
    return getattr(user, '_active_org_id', None) or user.active_org_id


def _require_admin(user: User):
    """Require owner or admin role."""
    role = getattr(user, 'role', None)
    if role not in ('owner', 'admin'):
        raise HTTPException(
            status_code=403,
            detail="Apenas proprietários e administradores podem alterar configurações da organização.",
        )


# =============================================================================
# COMPANY INFO ENDPOINTS
# =============================================================================


@router.get("/company", response_model=CompanyInfoResponse)
async def get_company_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get company information for the active organization."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    return CompanyInfoResponse(
        id=org.id,
        company_name=org.company_name,
        cnpj=org.cnpj,
        trade_name=org.trade_name,
        cnae_code=org.cnae_code,
        cnae_description=org.cnae_description,
        company_address_street=org.company_address_street,
        company_address_number=org.company_address_number,
        company_address_complement=org.company_address_complement,
        company_address_district=org.company_address_district,
        company_address_city=org.company_address_city,
        company_address_state=org.company_address_state,
        company_address_zip=org.company_address_zip,
        capital_social=float(org.capital_social) if org.capital_social else None,
        company_size=org.company_size,
        legal_nature=org.legal_nature,
        company_phone=org.company_phone,
        company_email=org.company_email,
        company_status=org.company_status,
        company_opened_at=org.company_opened_at,
        is_simples_nacional=org.is_simples_nacional,
        is_mei=org.is_mei,
        regime_tributario=org.regime_tributario,
        main_partner_name=org.main_partner_name,
    )


@router.put("/company", response_model=CompanyInfoResponse)
async def update_company_info(
    data: CompanyInfoUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update company information for the active organization. Owner/admin only."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    _require_admin(current_user)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)

    org.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(org)

    logger.info(f"Company info updated for org {org_id} by user {current_user.id}")

    return CompanyInfoResponse(
        id=org.id,
        company_name=org.company_name,
        cnpj=org.cnpj,
        trade_name=org.trade_name,
        cnae_code=org.cnae_code,
        cnae_description=org.cnae_description,
        company_address_street=org.company_address_street,
        company_address_number=org.company_address_number,
        company_address_complement=org.company_address_complement,
        company_address_district=org.company_address_district,
        company_address_city=org.company_address_city,
        company_address_state=org.company_address_state,
        company_address_zip=org.company_address_zip,
        capital_social=float(org.capital_social) if org.capital_social else None,
        company_size=org.company_size,
        legal_nature=org.legal_nature,
        company_phone=org.company_phone,
        company_email=org.company_email,
        company_status=org.company_status,
        company_opened_at=org.company_opened_at,
        is_simples_nacional=org.is_simples_nacional,
        is_mei=org.is_mei,
        regime_tributario=org.regime_tributario,
        main_partner_name=org.main_partner_name,
    )


# =============================================================================
# BANK ACCOUNTS ENDPOINTS
# =============================================================================


@router.get("/bank-accounts", response_model=List[BankAccountResponse])
async def list_bank_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all active bank accounts for the active organization."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    accounts = (
        db.query(OrgBankAccount)
        .filter(
            OrgBankAccount.organization_id == org_id,
            OrgBankAccount.is_active == True,
        )
        .order_by(OrgBankAccount.created_at.asc())
        .all()
    )

    return [
        BankAccountResponse(
            id=a.id,
            bank_code=a.bank_code,
            bank_name=a.bank_name,
            agency=a.agency,
            account_number=a.account_number,
            account_type=a.account_type,
            account_nickname=a.account_nickname,
            is_active=a.is_active,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in accounts
    ]


@router.post("/bank-accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_bank_account(
    data: BankAccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a new bank account to the active organization."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    role = getattr(current_user, 'role', None)
    if role not in ('owner', 'admin', 'accountant'):
        raise HTTPException(status_code=403, detail="Sem permissão para adicionar contas bancárias.")

    account = OrgBankAccount(
        organization_id=org_id,
        bank_code=data.bank_code,
        bank_name=data.bank_name,
        agency=data.agency,
        account_number=data.account_number,
        account_type=data.account_type,
        account_nickname=data.account_nickname,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    logger.info(f"Bank account added for org {org_id}: {data.bank_code} - {data.account_number}")

    return BankAccountResponse(
        id=account.id,
        bank_code=account.bank_code,
        bank_name=account.bank_name,
        agency=account.agency,
        account_number=account.account_number,
        account_type=account.account_type,
        account_nickname=account.account_nickname,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.put("/bank-accounts/{account_id}", response_model=BankAccountResponse)
async def update_bank_account(
    account_id: int,
    data: BankAccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a bank account."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    role = getattr(current_user, 'role', None)
    if role not in ('owner', 'admin', 'accountant'):
        raise HTTPException(status_code=403, detail="Sem permissão para editar contas bancárias.")

    account = (
        db.query(OrgBankAccount)
        .filter(
            OrgBankAccount.id == account_id,
            OrgBankAccount.organization_id == org_id,
            OrgBankAccount.is_active == True,
        )
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada.")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)

    return BankAccountResponse(
        id=account.id,
        bank_code=account.bank_code,
        bank_name=account.bank_name,
        agency=account.agency,
        account_number=account.account_number,
        account_type=account.account_type,
        account_nickname=account.account_nickname,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.delete("/bank-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete (deactivate) a bank account."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    role = getattr(current_user, 'role', None)
    if role not in ('owner', 'admin', 'accountant'):
        raise HTTPException(status_code=403, detail="Sem permissão para remover contas bancárias.")

    account = (
        db.query(OrgBankAccount)
        .filter(
            OrgBankAccount.id == account_id,
            OrgBankAccount.organization_id == org_id,
        )
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada.")

    account.is_active = False
    account.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Bank account {account_id} deactivated for org {org_id}")


# =============================================================================
# LOGO UPLOAD ENDPOINTS
# =============================================================================

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


@router.post("/logo", status_code=status.HTTP_200_OK)
async def upload_org_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Upload a custom logo for the organization (owner/admin only, Pro or Max plan required)."""
    _require_admin(current_user)

    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    # Check plan level — logo upload requires Pro (plan_id=2) or Max (plan_id=3)
    from database import Subscription
    sub = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(["active", "trialing"]),
        )
        .first()
    )
    plan_id = sub.plan_id if sub else 1
    if plan_id < 2:
        raise HTTPException(
            status_code=403,
            detail="Upload de logo disponível apenas nos planos Pro e Max.",
        )

    # Validate content type
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Use PNG, JPEG ou WebP.",
        )

    # Read and size-check
    logo_data = await file.read()
    if len(logo_data) > _MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Imagem muito grande. Limite: 2 MB.")

    # Upload to storage using a deterministic filename so it's recognizable
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "png"
    upload_name = f"org_{org_id}_logo.{ext}"

    from storage.s3_service import s3_storage
    try:
        storage_key = s3_storage.upload_file(logo_data, upload_name, content_type=file.content_type)
    except Exception as exc:
        logger.error(f"Logo upload failed: {exc}")
        raise HTTPException(status_code=500, detail="Erro ao salvar logo.")

    # Delete old logo if present
    if org.logo_url:
        try:
            s3_storage.delete_file(org.logo_url)
        except Exception:
            pass

    org.logo_url = storage_key
    org.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Logo uploaded for org {org_id}: {storage_key}")
    return {"logo_url": storage_key, "message": "Logo atualizado com sucesso."}


@router.delete("/logo", status_code=status.HTTP_200_OK)
async def delete_org_logo(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove the custom logo for the organization (owner only)."""
    _require_admin(current_user)

    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    if org.logo_url:
        from storage.s3_service import s3_storage
        try:
            s3_storage.delete_file(org.logo_url)
        except Exception:
            pass
        org.logo_url = None
        org.updated_at = datetime.utcnow()
        db.commit()

    return {"message": "Logo removido com sucesso."}


@router.get("/logo", status_code=status.HTTP_200_OK)
async def get_org_logo_url(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get the current logo URL for the organization."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    logo_url = None
    if org.logo_url:
        from storage.s3_service import s3_storage
        try:
            logo_url = s3_storage.get_file_url(org.logo_url)
        except Exception:
            logo_url = None

    return {"logo_url": logo_url, "has_logo": bool(org.logo_url)}


# =============================================================================
# BANK LOOKUP ENDPOINT (BrasilAPI Proxy)
# =============================================================================


@router.get("/banks/lookup", response_model=List[BankLookupResponse])
async def lookup_banks(
    current_user: User = Depends(get_current_active_user),
):
    """
    Proxy for BrasilAPI /banks/v1 endpoint.
    Returns list of Brazilian banks with codes and names.
    Results are cached for 1 hour.
    """
    global _banks_cache, _banks_cache_time

    # Check cache
    if _banks_cache and _banks_cache_time:
        elapsed = (datetime.utcnow() - _banks_cache_time).total_seconds()
        if elapsed < BANKS_CACHE_TTL_SECONDS:
            return [
                BankLookupResponse(
                    ispb=b.get("ispb", ""),
                    name=b.get("name", ""),
                    code=b.get("code"),
                    full_name=b.get("fullName", b.get("full_name", b.get("name", ""))),
                )
                for b in _banks_cache
                if b.get("code") is not None  # Only banks with valid codes
            ]

    # Fetch from BrasilAPI
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://brasilapi.com.br/api/banks/v1")
            response.raise_for_status()
            banks = response.json()

            # Cache the result
            _banks_cache = banks
            _banks_cache_time = datetime.utcnow()

            return [
                BankLookupResponse(
                    ispb=b.get("ispb", ""),
                    name=b.get("name", ""),
                    code=b.get("code"),
                    full_name=b.get("fullName", b.get("full_name", b.get("name", ""))),
                )
                for b in banks
                if b.get("code") is not None  # Only banks with valid codes
            ]
    except Exception as e:
        logger.error(f"Failed to fetch banks from BrasilAPI: {e}")
        raise HTTPException(
            status_code=502,
            detail="Erro ao consultar lista de bancos. Tente novamente.",
        )
