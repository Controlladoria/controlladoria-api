"""
Sessions Router
Handles session management endpoints:
- List active sessions
- Revoke specific sessions
- Revoke all sessions
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.session_manager import SessionManager
from database import User, UserSession, get_db

router = APIRouter(prefix="/auth/sessions", tags=["Sessions"])


@router.get("")
async def get_active_sessions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get all active sessions for current user

    Returns list of sessions with device info, last activity, etc.
    """
    sessions = SessionManager.get_active_sessions(
        user_id=current_user.id,
        db=db
    )

    return {
        "sessions": [
            {
                "id": session.id,
                "device_type": session.device_type,
                "device_os": session.device_os,
                "device_name": session.device_name,
                "browser": session.browser,
                "ip_address": session.ip_address,
                "created_at": session.created_at.isoformat() + "Z" if session.created_at else None,
                "last_activity": session.last_activity.isoformat() + "Z" if session.last_activity else None,
                "expires_at": session.expires_at.isoformat() + "Z" if session.expires_at else None,
                "is_active": session.is_active,
                "is_trusted_device": session.is_trusted_device,
                "trusted_until": session.trusted_until.isoformat() + "Z" if session.trusted_until else None,
            }
            for session in sessions
        ]
    }


@router.delete("/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Revoke a specific session

    User can only revoke their own sessions.
    """
    # Verify session belongs to current user
    session = db.query(UserSession).filter_by(id=session_id).first()
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada"
        )

    # Revoke session
    success = SessionManager.revoke_session(session_id, db)

    if success:
        return {"message": "Sessão revogada com sucesso"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada"
        )


@router.delete("")
async def revoke_all_sessions(
    request: Request,
    except_current: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Revoke all sessions for current user

    Args:
        except_current: If True, keeps current session active
    """
    current_session_id = None
    if except_current:
        from auth.security import verify_token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = verify_token(token, token_type="access")
            current_session_id = payload.get("sid") if payload else None

    count = SessionManager.revoke_all_sessions(
        user_id=current_user.id,
        db=db,
        except_session_id=current_session_id
    )

    return {
        "message": f"{count} sessões revogadas com sucesso",
        "count": count
    }
