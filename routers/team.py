"""
Team Router
Handles team management endpoints:
- List team members
- Invite new members
- Remove members
- Manage invitations
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.permissions import (
    Permission,
    Role,
    get_role_permissions,
    require_permission,
    require_super_admin,
)
from auth.security import create_access_token, create_refresh_token, get_password_hash
from auth.team_management import (
    accept_invitation,
    cancel_invitation as cancel_invite,
    create_invitation,
    create_invitation_token,
    get_team_members_and_invitations,
    remove_team_member,
    validate_invitation_token,
)
from database import TeamInvitation, User, UserClaim, get_db
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/team", tags=["Team"])


@router.get("/members")
async def get_team_members(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get all team members and pending invitations

    Only accessible by users with team.view permission.
    Returns list of active team members and pending invitations.
    """
    require_permission(current_user, Permission.TEAM_VIEW)

    data = get_team_members_and_invitations(current_user, db)

    # Format response
    members_formatted = [
        {
            "id": m.id,
            "email": m.email,
            "full_name": m.full_name,
            "role": m.role,
            "joined_at": m.created_at.isoformat() + "Z" if m.created_at else None,
            "invited_at": m.invited_at.isoformat() + "Z" if m.invited_at else None,
        }
        for m in data["members"]
    ]

    invitations_formatted = [
        {
            "id": inv.id,
            "email": inv.email,
            "invited_at": inv.created_at.isoformat() + "Z" if inv.created_at else None,
            "expires_at": inv.expires_at.isoformat() + "Z" if inv.expires_at else None,
            "is_expired": inv.is_expired,
        }
        for inv in data["pending_invitations"]
    ]

    return {
        "super_admin": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
        },
        "members": members_formatted,
        "pending_invitations": invitations_formatted,
        "seats": data["seats"],
    }


@router.post("/invite")
async def invite_team_member(
    email: str,
    role: str = "viewer",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Invite a new team member with specific role

    Only accessible by users with team.invite permission.
    Creates an invitation and sends email to the invitee.

    Args:
        email: Email of person to invite
        role: Role to assign (owner, admin, accountant, bookkeeper, viewer, api_user)
    """
    require_permission(current_user, Permission.TEAM_INVITE)

    # Validate role
    valid_roles = [r.value for r in Role]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    # Only owner can invite other owners/admins
    if role in ["owner", "admin"] and current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Only organization owner can invite admins")

    # Create invitation with role
    invitation, error = create_invitation(current_user, email, db, role=role)

    if error:
        raise HTTPException(status_code=400, detail=error)

    # Send invitation email
    try:
        await email_service.send_team_invitation_email(
            to=email,
            inviter_name=current_user.full_name,
            company_name=current_user.company_name,
            invitation_token=invitation.token,
        )
    except Exception as e:
        logger.error(f"Failed to send invitation email: {e}")
        # Don't fail the request, invitation is created
        pass

    return {
        "message": "Convite enviado com sucesso",
        "invitation": {
            "id": invitation.id,
            "email": invitation.email,
            "expires_at": invitation.expires_at.isoformat() + "Z" if invitation.expires_at else None,
        },
    }


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Remove a team member

    Only accessible by users with team.remove permission.
    Marks the user as inactive (soft delete).
    """
    require_permission(current_user, Permission.TEAM_REMOVE)

    success, message = remove_team_member(member_id, current_user, db)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"message": message}


@router.delete("/invitations/{invitation_id}")
async def cancel_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Cancel a pending invitation

    Only accessible by users with team.remove permission.
    """
    require_permission(current_user, Permission.TEAM_REMOVE)

    success, message = cancel_invite(invitation_id, current_user, db)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"message": message}


@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Resend a pending invitation

    Only accessible by super admins.
    Generates a new token and resends the email.
    """
    require_super_admin(current_user)

    invitation = (
        db.query(TeamInvitation)
        .filter_by(id=invitation_id, inviter_user_id=current_user.id)
        .first()
    )

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    if invitation.accepted_at:
        raise HTTPException(status_code=400, detail="Este convite já foi aceito")

    # Generate new token and extend expiration
    invitation.token = create_invitation_token()
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    invitation.is_cancelled = False
    db.commit()

    # Resend email
    try:
        await email_service.send_team_invitation_email(
            to=invitation.email,
            inviter_name=current_user.full_name,
            company_name=current_user.company_name,
            invitation_token=invitation.token,
        )
    except Exception as e:
        logger.error(f"Failed to resend invitation email: {e}")
        raise HTTPException(status_code=500, detail="Falha ao reenviar convite")

    return {
        "message": "Convite reenviado com sucesso",
        "expires_at": invitation.expires_at.isoformat() + "Z" if invitation.expires_at else None,
    }


@router.get("/invitations/{token}")
async def get_invitation_details(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Get invitation details by token

    Public endpoint (no auth required).
    Used to display invitation details on the acceptance page.
    """
    invitation, error = validate_invitation_token(token, db)

    if error:
        raise HTTPException(status_code=400, detail=error)

    inviter = invitation.inviter

    return {
        "valid": True,
        "email": invitation.email,
        "company_name": inviter.company_name,
        "inviter_name": inviter.full_name,
        "expires_at": invitation.expires_at.isoformat() + "Z" if invitation.expires_at else None,
    }


@router.post("/invitations/{token}/accept")
async def accept_team_invitation(
    token: str,
    full_name: str,
    password: str,
    db: Session = Depends(get_db),
):
    """
    Accept team invitation and create member account

    Public endpoint (no auth required).
    Creates a new user with role='member' and logs them in.
    """
    # Validate invitation
    invitation, error = validate_invitation_token(token, db)
    if error:
        raise HTTPException(status_code=400, detail=error)

    inviter = invitation.inviter

    # Check if email already exists (shouldn't happen, but double-check)
    existing_user = db.query(User).filter_by(email=invitation.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Este email já está cadastrado")

    # Create new user with role from invitation
    new_user = User(
        email=invitation.email.lower(),
        password_hash=get_password_hash(password),
        full_name=full_name,
        company_name=inviter.company_name,
        cnpj=inviter.cnpj,
        role=invitation.role,  # Use role from invitation
        parent_user_id=inviter.id,
        invited_by_user_id=inviter.id,
        invited_at=invitation.created_at,
        is_active=True,
        is_verified=True,  # Auto-verify invited users
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Mark invitation as accepted
    accept_invitation(invitation, new_user, db)

    # Load claims for new user (same logic as login)
    role_permissions = get_role_permissions(new_user.role)
    user_specific_claims = db.query(UserClaim).filter(
        UserClaim.user_id == new_user.id
    ).all()

    all_claims = set()
    for perm in role_permissions:
        all_claims.add(perm.value)
    for claim in user_specific_claims:
        if claim.is_valid:
            if claim.claim_value.lower() == "true":
                all_claims.add(claim.claim_type)
            elif claim.claim_value.lower() == "false":
                all_claims.discard(claim.claim_type)

    # Generate auth tokens with claims
    access_token = create_access_token(
        data={"sub": str(new_user.id), "email": new_user.email, "role": new_user.role},
        claims=list(all_claims)
    )
    refresh_token = create_refresh_token(new_user.id)

    return {
        "message": "Conta criada com sucesso",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "company_name": new_user.company_name,
            "role": new_user.role,
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
