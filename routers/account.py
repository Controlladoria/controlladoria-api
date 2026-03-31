"""
Account Router
Handles client/supplier/customer management and account settings:
- List clients (suppliers, customers)
- Create/update/delete clients
- Multi-tenant isolation on all queries
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.permissions import get_accessible_user_ids
from database import Client, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["Account"])


@router.get("")
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    client_type: Optional[str] = Query(None, description="Filter by type: supplier, customer, both"),
    search: Optional[str] = Query(None, description="Search by name or tax ID"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    List all clients/suppliers/customers for the current user

    Multi-tenant isolation: Only shows clients belonging to accessible users
    """
    # Multi-tenant: Filter by accessible user IDs
    query = db.query(Client).filter(
        Client.user_id.in_(get_accessible_user_ids(current_user, db)),
        Client.is_active == True
    )

    if client_type:
        query = query.filter(Client.client_type == client_type)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Client.name.ilike(search_term)) | (Client.tax_id.ilike(search_term))
        )

    total = query.count()
    clients = query.order_by(Client.name).offset(skip).limit(limit).all()

    return {
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "legal_name": c.legal_name,
                "tax_id": c.tax_id,
                "email": c.email,
                "phone": c.phone,
                "address": c.address,
                "client_type": c.client_type,
                "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
            }
            for c in clients
        ],
        "total": total,
    }


@router.post("", status_code=201)
async def create_client(
    client_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new client/supplier/customer

    Automatically associates with current user for multi-tenant isolation
    """
    new_client = Client(
        user_id=current_user.id,  # Multi-tenant: associate with current user
        name=client_data.get("name"),
        legal_name=client_data.get("legal_name"),
        tax_id=client_data.get("tax_id"),
        email=client_data.get("email"),
        phone=client_data.get("phone"),
        address=client_data.get("address"),
        client_type=client_data.get("client_type", "customer"),
        notes=client_data.get("notes"),
        is_active=True,
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)


    return {
        "id": new_client.id,
        "name": new_client.name,
        "message": "Client created successfully",
    }


@router.patch("/{client_id}")
async def update_client(
    client_id: int,
    client_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Update a client

    Multi-tenant isolation: Only allows updating own clients
    """
    # Multi-tenant: Verify ownership
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.user_id == current_user.id
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Update fields
    if "name" in client_data:
        client.name = client_data["name"]
    if "legal_name" in client_data:
        client.legal_name = client_data["legal_name"]
    if "tax_id" in client_data:
        client.tax_id = client_data["tax_id"]
    if "email" in client_data:
        client.email = client_data["email"]
    if "phone" in client_data:
        client.phone = client_data["phone"]
    if "address" in client_data:
        client.address = client_data["address"]
    if "client_type" in client_data:
        client.client_type = client_data["client_type"]
    if "notes" in client_data:
        client.notes = client_data["notes"]

    db.commit()


    return {"message": "Client updated successfully"}


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Delete (deactivate) a client

    Multi-tenant isolation: Only allows deleting own clients
    Soft delete - marks as inactive instead of removing from database
    """
    # Multi-tenant: Verify ownership
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.user_id == current_user.id
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Soft delete
    client.is_active = False
    db.commit()


    return {"message": "Client deleted successfully", "id": client_id}
