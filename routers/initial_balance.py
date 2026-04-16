"""
Initial Balance Router
Handles CRUD operations for organization initial balance data.
Used by the multi-step questionnaire wizard on the frontend.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from database import OrgInitialBalance, Organization, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/initial-balance", tags=["Initial Balance"])


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class BankAccountBalanceEntry(BaseModel):
    bank_account_id: int
    balance: float = 0.0


class InitialBalanceCreate(BaseModel):
    reference_date: date

    # Ativo Circulante
    cash_and_equivalents: float = 0.0
    short_term_investments: float = 0.0
    accounts_receivable: float = 0.0
    inventory: float = 0.0
    prepaid_expenses: float = 0.0

    # Ativo Não Circulante
    long_term_receivables: float = 0.0
    long_term_investments: float = 0.0

    # Imobilizado
    fixed_assets_land: float = 0.0
    fixed_assets_buildings: float = 0.0
    fixed_assets_machinery: float = 0.0
    fixed_assets_vehicles: float = 0.0
    fixed_assets_furniture: float = 0.0
    fixed_assets_computers: float = 0.0
    fixed_assets_other: float = 0.0
    accumulated_depreciation: float = 0.0

    # Intangível
    intangible_assets: float = 0.0
    accumulated_amortization: float = 0.0

    # Passivo Circulante
    suppliers_payable: float = 0.0
    short_term_loans: float = 0.0
    labor_obligations: float = 0.0
    tax_obligations: float = 0.0
    other_current_liabilities: float = 0.0

    # Passivo Não Circulante
    long_term_loans: float = 0.0
    long_term_financing: float = 0.0
    provisions_long_term: float = 0.0
    deferred_tax_liabilities: float = 0.0

    # Patrimônio Líquido (user inputs)
    reserves_and_adjustments: float = 0.0
    retained_earnings: float = 0.0

    # Bank account balances
    bank_account_balances: Optional[List[BankAccountBalanceEntry]] = None

    # Wizard completion
    is_completed: bool = False


class InitialBalanceResponse(BaseModel):
    id: int
    organization_id: int
    reference_date: date

    # Ativo Circulante
    cash_and_equivalents: float
    short_term_investments: float
    accounts_receivable: float
    inventory: float
    prepaid_expenses: float

    # Ativo Não Circulante
    long_term_receivables: float
    long_term_investments: float

    # Imobilizado
    fixed_assets_land: float
    fixed_assets_buildings: float
    fixed_assets_machinery: float
    fixed_assets_vehicles: float
    fixed_assets_furniture: float
    fixed_assets_computers: float
    fixed_assets_other: float
    accumulated_depreciation: float

    # Intangível
    intangible_assets: float
    accumulated_amortization: float

    # Passivo Circulante
    suppliers_payable: float
    short_term_loans: float
    labor_obligations: float
    tax_obligations: float
    other_current_liabilities: float

    # Passivo Não Circulante
    long_term_loans: float
    long_term_financing: float
    provisions_long_term: float
    deferred_tax_liabilities: float

    # Patrimônio Líquido
    reserves_and_adjustments: float
    retained_earnings: float

    # Bank balances
    bank_account_balances: Optional[List[Dict[str, Any]]] = None

    # Metadata
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InitialBalanceStatusResponse(BaseModel):
    has_initial_balance: bool
    is_completed: bool = False
    reference_date: Optional[date] = None
    initial_balance_id: Optional[int] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_org_id(user: User) -> Optional[int]:
    """Get the active organization ID for the user."""
    return getattr(user, '_active_org_id', None) or user.active_org_id


def _serialize_initial_balance(ib: OrgInitialBalance) -> dict:
    """Convert OrgInitialBalance to response dict."""
    return {
        "id": ib.id,
        "organization_id": ib.organization_id,
        "reference_date": ib.reference_date,
        "cash_and_equivalents": float(ib.cash_and_equivalents or 0),
        "short_term_investments": float(ib.short_term_investments or 0),
        "accounts_receivable": float(ib.accounts_receivable or 0),
        "inventory": float(ib.inventory or 0),
        "prepaid_expenses": float(ib.prepaid_expenses or 0),
        "long_term_receivables": float(ib.long_term_receivables or 0),
        "long_term_investments": float(ib.long_term_investments or 0),
        "fixed_assets_land": float(ib.fixed_assets_land or 0),
        "fixed_assets_buildings": float(ib.fixed_assets_buildings or 0),
        "fixed_assets_machinery": float(ib.fixed_assets_machinery or 0),
        "fixed_assets_vehicles": float(ib.fixed_assets_vehicles or 0),
        "fixed_assets_furniture": float(ib.fixed_assets_furniture or 0),
        "fixed_assets_computers": float(ib.fixed_assets_computers or 0),
        "fixed_assets_other": float(ib.fixed_assets_other or 0),
        "accumulated_depreciation": float(ib.accumulated_depreciation or 0),
        "intangible_assets": float(ib.intangible_assets or 0),
        "accumulated_amortization": float(ib.accumulated_amortization or 0),
        "suppliers_payable": float(ib.suppliers_payable or 0),
        "short_term_loans": float(ib.short_term_loans or 0),
        "labor_obligations": float(ib.labor_obligations or 0),
        "tax_obligations": float(ib.tax_obligations or 0),
        "other_current_liabilities": float(ib.other_current_liabilities or 0),
        "long_term_loans": float(ib.long_term_loans or 0),
        "long_term_financing": float(ib.long_term_financing or 0),
        "provisions_long_term": float(ib.provisions_long_term or 0),
        "deferred_tax_liabilities": float(ib.deferred_tax_liabilities or 0),
        "reserves_and_adjustments": float(ib.reserves_and_adjustments or 0),
        "retained_earnings": float(getattr(ib, 'retained_earnings', 0) or 0),
        "bank_account_balances": ib.bank_account_balances,
        "is_completed": ib.is_completed,
        "completed_at": ib.completed_at,
        "created_at": ib.created_at,
        "updated_at": ib.updated_at,
    }


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/status", response_model=InitialBalanceStatusResponse)
async def get_initial_balance_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Check if the active organization has completed the initial balance questionnaire."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    ib = (
        db.query(OrgInitialBalance)
        .filter(OrgInitialBalance.organization_id == org_id)
        .order_by(OrgInitialBalance.created_at.desc())
        .first()
    )

    if not ib:
        return InitialBalanceStatusResponse(
            has_initial_balance=False,
            is_completed=False,
        )

    return InitialBalanceStatusResponse(
        has_initial_balance=True,
        is_completed=ib.is_completed,
        reference_date=ib.reference_date,
        initial_balance_id=ib.id,
    )


@router.get("", response_model=None)
async def get_initial_balance(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get the initial balance data for the active organization."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    ib = (
        db.query(OrgInitialBalance)
        .filter(OrgInitialBalance.organization_id == org_id)
        .order_by(OrgInitialBalance.created_at.desc())
        .first()
    )

    if not ib:
        return None

    return _serialize_initial_balance(ib)


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def save_initial_balance(
    data: InitialBalanceCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create or update the initial balance for the active organization.
    Upserts by organization_id + reference_date.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    # Check user has admin or owner role
    role = getattr(current_user, 'role', None)
    if role not in ('owner', 'admin', 'accountant'):
        raise HTTPException(
            status_code=403,
            detail="Apenas proprietários, administradores e contadores podem configurar saldos iniciais.",
        )

    # Check if exists for this org + date
    ib = (
        db.query(OrgInitialBalance)
        .filter(
            OrgInitialBalance.organization_id == org_id,
            OrgInitialBalance.reference_date == data.reference_date,
        )
        .first()
    )

    # Prepare bank account balances JSON
    bank_balances = None
    if data.bank_account_balances:
        bank_balances = [
            {"bank_account_id": entry.bank_account_id, "balance": entry.balance}
            for entry in data.bank_account_balances
        ]

    if ib:
        # Update existing
        for field in [
            'cash_and_equivalents', 'short_term_investments', 'accounts_receivable',
            'inventory', 'prepaid_expenses', 'long_term_receivables', 'long_term_investments',
            'fixed_assets_land', 'fixed_assets_buildings', 'fixed_assets_machinery',
            'fixed_assets_vehicles', 'fixed_assets_furniture', 'fixed_assets_computers',
            'fixed_assets_other', 'accumulated_depreciation', 'intangible_assets',
            'accumulated_amortization', 'suppliers_payable', 'short_term_loans',
            'labor_obligations', 'tax_obligations', 'other_current_liabilities',
            'long_term_loans', 'long_term_financing',
            'provisions_long_term', 'deferred_tax_liabilities',
            'reserves_and_adjustments', 'retained_earnings',
        ]:
            setattr(ib, field, Decimal(str(getattr(data, field))))

        ib.bank_account_balances = bank_balances
        ib.is_completed = data.is_completed
        if data.is_completed and not ib.completed_at:
            ib.completed_at = datetime.utcnow()
        ib.updated_at = datetime.utcnow()

    else:
        # Create new
        ib = OrgInitialBalance(
            organization_id=org_id,
            reference_date=data.reference_date,
            cash_and_equivalents=Decimal(str(data.cash_and_equivalents)),
            short_term_investments=Decimal(str(data.short_term_investments)),
            accounts_receivable=Decimal(str(data.accounts_receivable)),
            inventory=Decimal(str(data.inventory)),
            prepaid_expenses=Decimal(str(data.prepaid_expenses)),
            long_term_receivables=Decimal(str(data.long_term_receivables)),
            long_term_investments=Decimal(str(data.long_term_investments)),
            fixed_assets_land=Decimal(str(data.fixed_assets_land)),
            fixed_assets_buildings=Decimal(str(data.fixed_assets_buildings)),
            fixed_assets_machinery=Decimal(str(data.fixed_assets_machinery)),
            fixed_assets_vehicles=Decimal(str(data.fixed_assets_vehicles)),
            fixed_assets_furniture=Decimal(str(data.fixed_assets_furniture)),
            fixed_assets_computers=Decimal(str(data.fixed_assets_computers)),
            fixed_assets_other=Decimal(str(data.fixed_assets_other)),
            accumulated_depreciation=Decimal(str(data.accumulated_depreciation)),
            intangible_assets=Decimal(str(data.intangible_assets)),
            accumulated_amortization=Decimal(str(data.accumulated_amortization)),
            suppliers_payable=Decimal(str(data.suppliers_payable)),
            short_term_loans=Decimal(str(data.short_term_loans)),
            labor_obligations=Decimal(str(data.labor_obligations)),
            tax_obligations=Decimal(str(data.tax_obligations)),
            other_current_liabilities=Decimal(str(data.other_current_liabilities)),
            long_term_loans=Decimal(str(data.long_term_loans)),
            long_term_financing=Decimal(str(data.long_term_financing)),
            provisions_long_term=Decimal(str(data.provisions_long_term)),
            deferred_tax_liabilities=Decimal(str(data.deferred_tax_liabilities)),
            reserves_and_adjustments=Decimal(str(data.reserves_and_adjustments)),
            retained_earnings=Decimal(str(data.retained_earnings)),
            bank_account_balances=bank_balances,
            is_completed=data.is_completed,
            completed_at=datetime.utcnow() if data.is_completed else None,
        )
        db.add(ib)

    db.commit()
    db.refresh(ib)

    logger.info(f"Initial balance saved for org {org_id}, date={data.reference_date}, completed={data.is_completed}")
    return _serialize_initial_balance(ib)


@router.put("/{balance_id}", response_model=None)
async def update_initial_balance(
    balance_id: int,
    data: InitialBalanceCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a specific initial balance record."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Nenhuma organização ativa.")

    role = getattr(current_user, 'role', None)
    if role not in ('owner', 'admin', 'accountant'):
        raise HTTPException(status_code=403, detail="Sem permissão para editar saldos iniciais.")

    ib = (
        db.query(OrgInitialBalance)
        .filter(
            OrgInitialBalance.id == balance_id,
            OrgInitialBalance.organization_id == org_id,
        )
        .first()
    )

    if not ib:
        raise HTTPException(status_code=404, detail="Saldo inicial não encontrado.")

    # Update all fields
    ib.reference_date = data.reference_date
    for field in [
        'cash_and_equivalents', 'short_term_investments', 'accounts_receivable',
        'inventory', 'prepaid_expenses', 'long_term_receivables', 'long_term_investments',
        'fixed_assets_land', 'fixed_assets_buildings', 'fixed_assets_machinery',
        'fixed_assets_vehicles', 'fixed_assets_furniture', 'fixed_assets_computers',
        'fixed_assets_other', 'accumulated_depreciation', 'intangible_assets',
        'accumulated_amortization', 'suppliers_payable', 'short_term_loans',
        'labor_obligations', 'tax_obligations', 'other_current_liabilities',
        'long_term_loans', 'long_term_financing',
        'provisions_long_term', 'deferred_tax_liabilities',
        'reserves_and_adjustments', 'retained_earnings',
    ]:
        setattr(ib, field, Decimal(str(getattr(data, field))))

    if data.bank_account_balances:
        ib.bank_account_balances = [
            {"bank_account_id": entry.bank_account_id, "balance": entry.balance}
            for entry in data.bank_account_balances
        ]

    ib.is_completed = data.is_completed
    if data.is_completed and not ib.completed_at:
        ib.completed_at = datetime.utcnow()
    ib.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ib)

    return _serialize_initial_balance(ib)
