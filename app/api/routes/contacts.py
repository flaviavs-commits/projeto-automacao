from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactRead


router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactRead])
def list_contacts(db: Session = Depends(get_db)) -> list[Contact]:
    return db.query(Contact).order_by(Contact.created_at.desc()).limit(100).all()
