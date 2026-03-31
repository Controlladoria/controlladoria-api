"""
Contact Router
Handles contact form submissions
- Submit contact form (public, rate-limited)
- List submissions (admin only)
- Mark submissions as read (admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from auth import verify_api_key
from config import settings
from database import ContactSubmission, get_db
from email_service import email_service
from models import ContactFormResponse, ContactFormSubmission

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("", response_model=ContactFormResponse)
@limiter.limit(
    settings.contact_rate_limit if settings.rate_limit_enabled else "100/hour"
)
async def submit_contact_form(
    request: Request, form: ContactFormSubmission, db: Session = Depends(get_db)
):
    """
    Submit a contact form message

    Stores contact form submissions in the database for later review
    Rate limited to prevent spam
    """
    try:
        # Create contact submission record
        contact = ContactSubmission(
            name=form.name, email=form.email, phone=form.phone, message=form.message
        )

        db.add(contact)
        db.commit()
        db.refresh(contact)

        # Send email notification to admin (async, non-blocking)
        try:
            import asyncio

            asyncio.create_task(
                email_service.send_contact_notification(
                    admin_email=settings.admin_email,
                    name=form.name,
                    email=form.email,
                    phone=form.phone or "N/A",
                    message=form.message,
                )
            )
        except Exception as e:
            # Log email error but don't block submission
            logger.warning(f"Failed to send contact notification email: {str(e)}")


        return ContactFormResponse(
            success=True,
            message="Mensagem enviada com sucesso! Entraremos em contato em breve.",
            submission_id=contact.id,
        )

    except Exception as e:
        logger.error(f"❌ Error submitting contact form: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao enviar mensagem: {str(e)}"
        )


@router.get("/submissions")
async def list_contact_submissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    unread_only: bool = Query(False, description="Show only unread messages"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    List contact form submissions (admin only)

    Requires authentication if API_KEY is set in environment
    """
    query = db.query(ContactSubmission)

    if unread_only:
        query = query.filter(ContactSubmission.read == 0)

    total = query.count()
    submissions = (
        query.order_by(ContactSubmission.submitted_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "submissions": [
            {
                "id": sub.id,
                "name": sub.name,
                "email": sub.email,
                "phone": sub.phone,
                "message": sub.message,
                "submitted_date": sub.submitted_date,
                "read": bool(sub.read),
                "replied": bool(sub.replied),
            }
            for sub in submissions
        ],
    }


@router.patch("/submissions/{submission_id}/mark-read")
async def mark_contact_as_read(
    submission_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Mark a contact submission as read (admin only)

    Requires authentication if API_KEY is set in environment
    """
    submission = (
        db.query(ContactSubmission)
        .filter(ContactSubmission.id == submission_id)
        .first()
    )

    if not submission:
        raise HTTPException(status_code=404, detail="Envio não encontrado")

    submission.read = 1
    db.commit()

    return {"message": "Marked as read", "id": submission_id}
