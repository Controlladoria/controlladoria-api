"""
Organizations Router
Handles multi-org endpoints:
- List user's organizations
- Switch active organization
- Invite users to organization (cross-org)
- Accept/decline organization invitations
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.permissions import (
    Permission,
    get_role_permissions,
    has_permission,
    require_permission,
)
from auth.security import create_access_token, create_refresh_token
from config import settings
from database import (
    OrgInvitation,
    OrgMembership,
    Organization,
    Subscription,
    SubscriptionStatus,
    User,
    UserClaim,
    UserSession,
    get_db,
)
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


def _create_org_session(user: User, db: Session) -> UserSession:
    """Create a UserSession with all required fields for org create/switch operations."""
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        device_type="desktop",
        device_os="web",
        device_name="Org Switch",
        browser="API",
        is_active=True,
        created_at=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    db.flush()
    return session


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================


class OrgResponse(BaseModel):
    id: int
    company_name: str
    cnpj: str
    trade_name: str | None = None
    role: str
    is_active: bool
    logo_url: str | None = None


class SwitchOrgResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    organization: OrgResponse


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "bookkeeper"


class InviteResponse(BaseModel):
    message: str
    invitation_id: int
    target_email: str
    role: str
    expires_at: str


class InvitationDetailResponse(BaseModel):
    id: int
    organization_name: str
    organization_cnpj: str
    inviter_name: str
    inviter_email: str
    role: str
    expires_at: str
    is_expired: bool


class AcceptInvitationResponse(BaseModel):
    message: str
    organization: OrgResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CreateOrgRequest(BaseModel):
    """Request to create a new organization from CNPJ data."""
    cnpj: str = Field(..., min_length=14, max_length=50)
    company_name: str = Field(..., max_length=255)
    trade_name: str | None = None
    cnae_code: str | None = None
    cnae_description: str | None = None
    company_address_street: str | None = None
    company_address_number: str | None = None
    company_address_complement: str | None = None
    company_address_district: str | None = None
    company_address_city: str | None = None
    company_address_state: str | None = None
    company_address_zip: str | None = None
    capital_social: float | None = None
    company_size: str | None = None
    legal_nature: str | None = None
    company_phone: str | None = None
    company_email: str | None = None
    company_status: str | None = None
    company_opened_at: str | None = None
    is_simples_nacional: bool | None = None
    is_mei: bool | None = None
    qsa_partners: list[dict] | None = None
    cnaes_secundarios: list[dict] | None = None
    company_address_type: str | None = None
    is_headquarters: bool | None = None
    ibge_code: str | None = None
    regime_tributario: str | None = None
    simples_desde: str | None = None
    simples_excluido_em: str | None = None
    main_partner_name: str | None = None
    main_partner_qualification: str | None = None


# =============================================================================
# CREATE ORGANIZATION
# =============================================================================


@router.post("/create", response_model=SwitchOrgResponse)
async def create_organization(
    data: CreateOrgRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new organization with a different CNPJ.
    Only owners of at least one org can create new orgs.
    Auto-switches to the new org and returns new tokens.
    """
    # Check that user is an owner of at least one org
    owner_membership = (
        db.query(OrgMembership)
        .filter(
            OrgMembership.user_id == current_user.id,
            OrgMembership.role == "owner",
            OrgMembership.is_active == True,
        )
        .first()
    )
    if not owner_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas proprietários podem criar novas empresas.",
        )

    # Validate CNPJ format (strip formatting)
    cnpj_clean = data.cnpj.replace(".", "").replace("/", "").replace("-", "").strip()
    if len(cnpj_clean) != 14 or not cnpj_clean.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CNPJ inválido. Deve conter 14 dígitos.",
        )

    # Format CNPJ consistently for storage: XX.XXX.XXX/XXXX-XX
    cnpj_formatted = (
        f"{cnpj_clean[:2]}.{cnpj_clean[2:5]}.{cnpj_clean[5:8]}"
        f"/{cnpj_clean[8:12]}-{cnpj_clean[12:14]}"
    )

    # Check CNPJ uniqueness (compare digits-only to handle format differences)
    all_orgs = db.query(Organization).all()
    for org_check in all_orgs:
        if org_check.cnpj and org_check.cnpj.replace(".", "").replace("/", "").replace("-", "").strip() == cnpj_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este CNPJ já está cadastrado na plataforma.",
            )

    # Also check User.cnpj for legacy records (compare digits-only)
    all_users_with_cnpj = db.query(User).filter(User.cnpj.isnot(None)).all()
    for user_check in all_users_with_cnpj:
        if user_check.cnpj.replace(".", "").replace("/", "").replace("-", "").strip() == cnpj_clean:
            if user_check.id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Este CNPJ já está associado a outra conta.",
                )

    # Limit max orgs per user (prevent abuse)
    org_count = (
        db.query(OrgMembership)
        .filter(
            OrgMembership.user_id == current_user.id,
            OrgMembership.role == "owner",
            OrgMembership.is_active == True,
        )
        .count()
    )
    if org_count >= 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limite de 20 empresas por conta atingido.",
        )

    # Create Organization (mirrors auth/service.py register_user)
    org = Organization(
        company_name=data.company_name,
        cnpj=cnpj_formatted,
        trade_name=data.trade_name,
        cnae_code=data.cnae_code,
        cnae_description=data.cnae_description,
        company_address_street=data.company_address_street,
        company_address_number=data.company_address_number,
        company_address_complement=data.company_address_complement,
        company_address_district=data.company_address_district,
        company_address_city=data.company_address_city,
        company_address_state=data.company_address_state,
        company_address_zip=data.company_address_zip,
        capital_social=data.capital_social,
        company_size=data.company_size,
        legal_nature=data.legal_nature,
        company_phone=data.company_phone,
        company_email=data.company_email,
        company_status=data.company_status,
        company_opened_at=data.company_opened_at,
        is_simples_nacional=data.is_simples_nacional,
        is_mei=data.is_mei,
        qsa_partners=data.qsa_partners,
        cnaes_secundarios=data.cnaes_secundarios,
        company_address_type=data.company_address_type,
        is_headquarters=data.is_headquarters,
        ibge_code=data.ibge_code,
        regime_tributario=data.regime_tributario,
        simples_desde=data.simples_desde,
        simples_excluido_em=data.simples_excluido_em,
        main_partner_name=data.main_partner_name,
        main_partner_qualification=data.main_partner_qualification,
    )
    db.add(org)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        # Race condition: CNPJ was inserted between our check and flush
        if "unique" in str(e).lower() or "duplicate" in str(e).lower() or "integrity" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este CNPJ já está cadastrado na plataforma.",
            )
        raise

    # Create owner membership
    membership = OrgMembership(
        user_id=current_user.id,
        organization_id=org.id,
        role="owner",
        joined_at=datetime.utcnow(),
    )
    db.add(membership)

    # Create trial subscription (mirrors auth/service.py)
    from plan_features import get_default_plan

    trial_end = datetime.utcnow() + timedelta(days=settings.stripe_trial_days)
    default_plan = get_default_plan(db)
    subscription = Subscription(
        user_id=current_user.id,
        organization_id=org.id,
        stripe_customer_id="",
        stripe_subscription_id=None,
        stripe_price_id=None,
        status=SubscriptionStatus.TRIALING,
        trial_start=datetime.utcnow(),
        trial_end=trial_end,
        current_period_start=datetime.utcnow(),
        current_period_end=trial_end,
        plan_id=default_plan.id if default_plan else None,
        max_users=default_plan.max_users if default_plan else 1,
    )
    db.add(subscription)

    # Switch active org and commit everything together
    current_user.active_org_id = org.id
    try:
        db.commit()
        db.refresh(org)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating organization (commit failed): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar empresa. Tente novamente.",
        )

    # Create new session + tokens (same pattern as switch_organization)
    try:
        session = _create_org_session(current_user, db)
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating org session: {e}")
        # Org was created successfully, just session creation failed
        # Try one more time with a fresh session
        try:
            session = _create_org_session(current_user, db)
            db.commit()
            db.refresh(session)
        except Exception as e2:
            db.rollback()
            logger.error(f"Error creating org session (retry): {e2}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Empresa criada, mas erro ao gerar sessão. Faça login novamente.",
            )

    role_permissions = get_role_permissions("owner")
    user_specific_claims = (
        db.query(UserClaim)
        .filter(UserClaim.user_id == current_user.id)
        .all()
    )
    all_claims = set(p.value for p in role_permissions)
    for claim in user_specific_claims:
        if claim.is_valid and claim.claim_value.lower() == "true":
            all_claims.add(claim.claim_type)

    access_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "email": current_user.email,
            "role": "owner",
            "org_id": org.id,
            "sid": session.id,
        },
        claims=list(all_claims),
    )
    refresh_token = create_refresh_token(user_id=current_user.id)

    logger.info(
        f"🏢 User {current_user.id} ({current_user.email}) created new org {org.id} ({org.company_name}, CNPJ: {org.cnpj})"
    )

    return SwitchOrgResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        organization=OrgResponse(
            id=org.id,
            company_name=org.company_name,
            cnpj=org.cnpj,
            trade_name=org.trade_name,
            role="owner",
            is_active=True,
        ),
    )


# =============================================================================
# LIST ORGANIZATIONS
# =============================================================================


@router.get("/", response_model=list[OrgResponse])
async def list_organizations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    List all organizations the current user belongs to.
    Returns each org with user's role and whether it's the active one.
    """
    memberships = (
        db.query(OrgMembership)
        .filter(
            OrgMembership.user_id == current_user.id,
            OrgMembership.is_active == True,
        )
        .all()
    )

    active_org_id = getattr(current_user, "_active_org_id", None) or current_user.active_org_id

    # Resolve logo URLs for orgs that have them
    from storage.s3_service import s3_storage

    result = []
    for m in memberships:
        org = m.organization
        if org:
            logo_url = None
            if org.logo_url:
                try:
                    logo_url = s3_storage.get_file_url(org.logo_url)
                except Exception:
                    logo_url = None
            result.append(
                OrgResponse(
                    id=org.id,
                    company_name=org.company_name,
                    cnpj=org.cnpj,
                    trade_name=org.trade_name,
                    role=m.role,
                    is_active=(org.id == active_org_id),
                    logo_url=logo_url,
                )
            )

    return result


# =============================================================================
# SWITCH ACTIVE ORGANIZATION
# =============================================================================


@router.post("/{org_id}/switch", response_model=SwitchOrgResponse)
async def switch_organization(
    org_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Switch the user's active organization.
    Returns new JWT tokens scoped to the new org.
    """
    # Verify user is a member of this org
    membership = (
        db.query(OrgMembership)
        .filter_by(
            user_id=current_user.id,
            organization_id=org_id,
            is_active=True,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organização não encontrada ou você não é membro.",
        )

    # Eagerly load the organization to avoid lazy-load issues after commit
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organização não encontrada.",
        )

    # Update active_org_id on user
    current_user.active_org_id = org_id
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error switching org (commit active_org_id): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao trocar empresa. Tente novamente.",
        )

    # Create new session for this org context
    try:
        session = _create_org_session(current_user, db)
        db.commit()
        db.refresh(session)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating session during org switch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar sessão para a empresa. Tente novamente.",
        )

    # Build claims from org role
    role_permissions = get_role_permissions(membership.role)
    user_specific_claims = (
        db.query(UserClaim)
        .filter(UserClaim.user_id == current_user.id)
        .all()
    )
    all_claims = set(p.value for p in role_permissions)
    for claim in user_specific_claims:
        if claim.is_valid and claim.claim_value.lower() == "true":
            all_claims.add(claim.claim_type)

    # Generate new tokens with org_id
    access_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "email": current_user.email,
            "role": membership.role,
            "org_id": org_id,
            "sid": session.id,
        },
        claims=list(all_claims),
    )
    refresh_token = create_refresh_token(user_id=current_user.id)

    logger.info(
        f"👤 User {current_user.id} switched to org {org_id} ({org.company_name}) as {membership.role}"
    )

    return SwitchOrgResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        organization=OrgResponse(
            id=org.id,
            company_name=org.company_name,
            cnpj=org.cnpj,
            trade_name=org.trade_name,
            role=membership.role,
            is_active=True,
        ),
    )


# =============================================================================
# INVITE TO ORGANIZATION
# =============================================================================


@router.post("/{org_id}/invite", response_model=InviteResponse)
async def invite_to_organization(
    org_id: int,
    invite_data: InviteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Invite a user to join this organization.
    Requires TEAM_INVITE permission in the target org.
    If the email belongs to an existing user, a cross-org invitation is created.
    """
    # Verify current user is a member of this org with invite permission
    membership = (
        db.query(OrgMembership)
        .filter_by(
            user_id=current_user.id,
            organization_id=org_id,
            is_active=True,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro desta organização.",
        )

    # Check invite permission based on org role
    role_perms = get_role_permissions(membership.role)
    from auth.permissions import Permission as P

    if P.TEAM_INVITE not in role_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para convidar membros.",
        )

    # Validate role - can't invite as owner
    valid_roles = ["admin", "accountant", "bookkeeper", "viewer", "api_user"]
    if invite_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Função inválida. Opções: {', '.join(valid_roles)}",
        )

    # Can't invite someone who's already a member
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organização não encontrada.",
        )

    existing_membership = (
        db.query(OrgMembership)
        .join(User, OrgMembership.user_id == User.id)
        .filter(
            User.email == invite_data.email,
            OrgMembership.organization_id == org_id,
            OrgMembership.is_active == True,
        )
        .first()
    )
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este usuário já é membro desta organização.",
        )

    # Check for existing pending invitation
    existing_invite = (
        db.query(OrgInvitation)
        .filter(
            OrgInvitation.organization_id == org_id,
            OrgInvitation.target_email == invite_data.email,
            OrgInvitation.accepted_at.is_(None),
            OrgInvitation.declined_at.is_(None),
            OrgInvitation.is_cancelled == False,
            OrgInvitation.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um convite pendente para este email.",
        )

    # Check seat limit
    subscription = (
        db.query(Subscription)
        .filter(Subscription.organization_id == org_id)
        .first()
    )
    if subscription:
        current_members = (
            db.query(OrgMembership)
            .filter(
                OrgMembership.organization_id == org_id,
                OrgMembership.is_active == True,
            )
            .count()
        )
        if current_members >= subscription.max_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Limite de {subscription.max_users} membros atingido. "
                       "Atualize seu plano para convidar mais membros.",
            )

    # Check if target user exists
    target_user = db.query(User).filter(User.email == invite_data.email).first()

    # Create invitation
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)

    invitation = OrgInvitation(
        organization_id=org_id,
        inviter_user_id=current_user.id,
        target_user_id=target_user.id if target_user else None,
        target_email=invite_data.email,
        role=invite_data.role,
        token=token,
        expires_at=expires_at,
        is_cancelled=False,
        created_at=datetime.utcnow(),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # Send invitation email
    try:
        inviter_name = current_user.full_name or current_user.email.split("@")[0]
        import asyncio

        asyncio.create_task(
            email_service.send_org_invitation_email(
                to=invite_data.email,
                inviter_name=inviter_name,
                inviter_email=current_user.email,
                org_name=org.company_name,
                role=invite_data.role,
                invitation_token=token,
                expires_days=7,
            )
        )
    except Exception as e:
        logger.error(f"Failed to send org invitation email: {e}")

    logger.info(
        f"📨 Org invitation created: {current_user.email} invited {invite_data.email} "
        f"to org {org.company_name} as {invite_data.role}"
    )

    return InviteResponse(
        message="Convite enviado com sucesso!",
        invitation_id=invitation.id,
        target_email=invite_data.email,
        role=invite_data.role,
        expires_at=expires_at.isoformat(),
    )


# =============================================================================
# VIEW INVITATION DETAILS (for accept page)
# =============================================================================


@router.get("/invitations/{token}", response_model=InvitationDetailResponse)
async def get_invitation_details(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Get invitation details by token.
    Public endpoint (no auth required) — used by the accept invitation page.
    """
    invitation = (
        db.query(OrgInvitation)
        .filter(OrgInvitation.token == token)
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite não encontrado.",
        )

    if invitation.is_cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite foi cancelado.",
        )

    if invitation.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite já foi aceito.",
        )

    if invitation.declined_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite já foi recusado.",
        )

    org = db.query(Organization).filter(Organization.id == invitation.organization_id).first()
    inviter = db.query(User).filter(User.id == invitation.inviter_user_id).first()

    is_expired = invitation.expires_at < datetime.utcnow()

    return InvitationDetailResponse(
        id=invitation.id,
        organization_name=org.company_name if org else "Desconhecida",
        organization_cnpj=org.cnpj if org else "",
        inviter_name=inviter.full_name if inviter else "Desconhecido",
        inviter_email=inviter.email if inviter else "",
        role=invitation.role,
        expires_at=invitation.expires_at.isoformat(),
        is_expired=is_expired,
    )


# =============================================================================
# ACCEPT INVITATION
# =============================================================================


@router.post("/invitations/{token}/accept", response_model=AcceptInvitationResponse)
async def accept_org_invitation(
    token: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Accept an organization invitation.
    Creates OrgMembership and returns new tokens scoped to the new org.
    """
    invitation = (
        db.query(OrgInvitation)
        .filter(OrgInvitation.token == token)
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite não encontrado.",
        )

    # Validate invitation state
    if invitation.is_cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite foi cancelado.",
        )

    if invitation.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite já foi aceito.",
        )

    if invitation.declined_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite já foi recusado.",
        )

    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite expirou.",
        )

    # Verify the invitation is for this user
    if invitation.target_email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este convite não é para o seu email.",
        )

    # Check if already a member
    existing = (
        db.query(OrgMembership)
        .filter_by(
            user_id=current_user.id,
            organization_id=invitation.organization_id,
        )
        .first()
    )
    if existing and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já é membro desta organização.",
        )

    org = db.query(Organization).filter(Organization.id == invitation.organization_id).first()

    # Reactivate or create membership
    if existing:
        existing.is_active = True
        existing.role = invitation.role
        existing.invited_by_user_id = invitation.inviter_user_id
        existing.joined_at = datetime.utcnow()
    else:
        membership = OrgMembership(
            user_id=current_user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
            invited_by_user_id=invitation.inviter_user_id,
            joined_at=datetime.utcnow(),
            is_active=True,
        )
        db.add(membership)

    # Mark invitation as accepted
    invitation.accepted_at = datetime.utcnow()
    invitation.target_user_id = current_user.id

    # Switch active org to the new one
    current_user.active_org_id = invitation.organization_id
    db.commit()

    # Create new session
    session = _create_org_session(current_user, db)
    db.commit()
    db.refresh(session)

    # Generate new tokens scoped to new org
    role_permissions = get_role_permissions(invitation.role)
    all_claims = set(p.value for p in role_permissions)

    access_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "email": current_user.email,
            "role": invitation.role,
            "org_id": invitation.organization_id,
            "sid": session.id,
        },
        claims=list(all_claims),
    )
    refresh_token = create_refresh_token(user_id=current_user.id)

    logger.info(
        f"✅ User {current_user.email} accepted invitation to org {org.company_name} as {invitation.role}"
    )

    return AcceptInvitationResponse(
        message=f"Você agora é membro da organização {org.company_name}!",
        organization=OrgResponse(
            id=org.id,
            company_name=org.company_name,
            cnpj=org.cnpj,
            trade_name=org.trade_name,
            role=invitation.role,
            is_active=True,
        ),
        access_token=access_token,
        refresh_token=refresh_token,
    )


# =============================================================================
# DECLINE INVITATION
# =============================================================================


@router.post("/invitations/{token}/decline")
async def decline_org_invitation(
    token: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Decline an organization invitation."""
    invitation = (
        db.query(OrgInvitation)
        .filter(OrgInvitation.token == token)
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite não encontrado.",
        )

    if invitation.target_email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este convite não é para o seu email.",
        )

    if invitation.accepted_at or invitation.declined_at or invitation.is_cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite já foi processado.",
        )

    invitation.declined_at = datetime.utcnow()
    db.commit()

    logger.info(f"❌ User {current_user.email} declined invitation to org {invitation.organization_id}")

    return {"message": "Convite recusado."}


# =============================================================================
# LIST PENDING INVITATIONS FOR CURRENT USER
# =============================================================================


@router.get("/invitations", response_model=list[InvitationDetailResponse])
async def list_my_invitations(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    List all pending invitations for the current user.
    Shows invitations that haven't been accepted, declined, or cancelled.
    """
    invitations = (
        db.query(OrgInvitation)
        .filter(
            OrgInvitation.target_email == current_user.email,
            OrgInvitation.accepted_at.is_(None),
            OrgInvitation.declined_at.is_(None),
            OrgInvitation.is_cancelled == False,
        )
        .all()
    )

    result = []
    for inv in invitations:
        org = db.query(Organization).filter(Organization.id == inv.organization_id).first()
        inviter = db.query(User).filter(User.id == inv.inviter_user_id).first()

        result.append(
            InvitationDetailResponse(
                id=inv.id,
                organization_name=org.company_name if org else "Desconhecida",
                organization_cnpj=org.cnpj if org else "",
                inviter_name=inviter.full_name if inviter else "Desconhecido",
                inviter_email=inviter.email if inviter else "",
                role=inv.role,
                expires_at=inv.expires_at.isoformat(),
                is_expired=inv.expires_at < datetime.utcnow(),
            )
        )

    return result


# =============================================================================
# CANCEL INVITATION (for org admins)
# =============================================================================


@router.delete("/{org_id}/invitations/{invitation_id}")
async def cancel_org_invitation(
    org_id: int,
    invitation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cancel a pending org invitation. Requires TEAM_INVITE permission."""
    # Verify membership and permission
    membership = (
        db.query(OrgMembership)
        .filter_by(
            user_id=current_user.id,
            organization_id=org_id,
            is_active=True,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro desta organização.",
        )

    role_perms = get_role_permissions(membership.role)
    if Permission.TEAM_INVITE not in role_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para gerenciar convites.",
        )

    invitation = (
        db.query(OrgInvitation)
        .filter(
            OrgInvitation.id == invitation_id,
            OrgInvitation.organization_id == org_id,
        )
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite não encontrado.",
        )

    if invitation.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Convite já aceito, não pode ser cancelado.",
        )

    invitation.is_cancelled = True
    db.commit()

    logger.info(
        f"🚫 Invitation {invitation_id} cancelled by {current_user.email} for org {org_id}"
    )

    return {"message": "Convite cancelado com sucesso."}


# =============================================================================
# LIST ORG INVITATIONS (for org admins)
# =============================================================================


@router.get("/{org_id}/invitations")
async def list_org_invitations(
    org_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all invitations for an organization. Requires TEAM_VIEW permission."""
    membership = (
        db.query(OrgMembership)
        .filter_by(
            user_id=current_user.id,
            organization_id=org_id,
            is_active=True,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro desta organização.",
        )

    role_perms = get_role_permissions(membership.role)
    if Permission.TEAM_VIEW not in role_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para ver convites.",
        )

    invitations = (
        db.query(OrgInvitation)
        .filter(
            OrgInvitation.organization_id == org_id,
            OrgInvitation.is_cancelled == False,
        )
        .order_by(OrgInvitation.created_at.desc())
        .all()
    )

    result = []
    for inv in invitations:
        inviter = db.query(User).filter(User.id == inv.inviter_user_id).first()
        result.append(
            {
                "id": inv.id,
                "target_email": inv.target_email,
                "role": inv.role,
                "inviter_name": inviter.full_name if inviter else "Desconhecido",
                "inviter_email": inviter.email if inviter else "",
                "created_at": inv.created_at.isoformat(),
                "expires_at": inv.expires_at.isoformat(),
                "is_expired": inv.expires_at < datetime.utcnow(),
                "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
                "declined_at": inv.declined_at.isoformat() if inv.declined_at else None,
                "status": (
                    "accepted"
                    if inv.accepted_at
                    else "declined"
                    if inv.declined_at
                    else "expired"
                    if inv.expires_at < datetime.utcnow()
                    else "pending"
                ),
            }
        )

    return result
