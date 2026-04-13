from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.services.customer_identity_service import CustomerIdentityService


router = APIRouter(prefix="/contacts", tags=["contacts"])
identity_service = CustomerIdentityService()


def _sync_contact_identities(db: Session, contact: Contact) -> None:
    if contact.phone:
        identity_service.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform="whatsapp",
            platform_user_id=contact.phone,
        )
    if contact.instagram_user_id:
        identity_service.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform="instagram",
            platform_user_id=contact.instagram_user_id,
        )
    if contact.tiktok_user_id:
        identity_service.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform="tiktok",
            platform_user_id=contact.tiktok_user_id,
        )
    if contact.youtube_channel_id:
        identity_service.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform="youtube",
            platform_user_id=contact.youtube_channel_id,
        )


@router.get("", response_model=list[ContactRead])
def list_contacts(db: Session = Depends(get_db)) -> list[Contact]:
    return db.query(Contact).order_by(Contact.created_at.desc()).limit(100).all()


@router.get("/{contact_id}", response_model=ContactRead)
def get_contact(contact_id: UUID, db: Session = Depends(get_db)) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)) -> Contact:
    contact = Contact(
        name=payload.name,
        phone=payload.phone,
        instagram_user_id=payload.instagram_user_id,
        youtube_channel_id=payload.youtube_channel_id,
        tiktok_user_id=payload.tiktok_user_id,
        email=payload.email,
    )
    db.add(contact)
    db.flush()
    _sync_contact_identities(db, contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactRead)
def update_contact(contact_id: UUID, payload: ContactUpdate, db: Session = Depends(get_db)) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    for field, value in updates.items():
        setattr(contact, field, value)

    _sync_contact_identities(db, contact)
    db.commit()
    db.refresh(contact)
    return contact
