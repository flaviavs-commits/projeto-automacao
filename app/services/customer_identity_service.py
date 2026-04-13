from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity


class CustomerIdentityService:
    """Resolves a single customer across platform identities."""

    def resolve_or_create_contact(
        self,
        *,
        db: Session,
        platform: str,
        platform_user_id: str,
        profile_name: str | None = None,
    ) -> Contact:
        normalized_platform = self._normalize_platform(platform)
        normalized_value = self._normalize_identity_value(normalized_platform, platform_user_id)
        if not normalized_value:
            raise ValueError("platform_user_id is required")

        identity = (
            db.query(ContactIdentity)
            .filter(
                ContactIdentity.platform == normalized_platform,
                ContactIdentity.platform_user_id == normalized_value,
            )
            .first()
        )
        if identity is not None:
            self._update_contact_name_if_missing(identity.contact, profile_name)
            return identity.contact

        contact = self._find_contact_by_legacy_fields(
            db=db,
            platform=normalized_platform,
            normalized_value=normalized_value,
        )
        if contact is None and profile_name:
            contact = self._find_unique_contact_by_name(db=db, profile_name=profile_name)

        if contact is None:
            contact = Contact(name=profile_name)
            self._set_legacy_identity_field(contact, normalized_platform, normalized_value)
            db.add(contact)
            db.flush()
        else:
            self._update_contact_name_if_missing(contact, profile_name)
            self._set_legacy_identity_field(contact, normalized_platform, normalized_value)

        self.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform=normalized_platform,
            platform_user_id=normalized_value,
        )

        return contact

    def upsert_identity_for_contact(
        self,
        *,
        db: Session,
        contact: Contact,
        platform: str,
        platform_user_id: str,
    ) -> None:
        normalized_platform = self._normalize_platform(platform)
        normalized_value = self._normalize_identity_value(normalized_platform, platform_user_id)
        if not normalized_value:
            return

        existing_identity = (
            db.query(ContactIdentity)
            .filter(
                ContactIdentity.contact_id == contact.id,
                ContactIdentity.platform == normalized_platform,
                ContactIdentity.platform_user_id == normalized_value,
            )
            .first()
        )
        if existing_identity is not None:
            return

        has_identity = (
            db.query(ContactIdentity.id)
            .filter(ContactIdentity.contact_id == contact.id)
            .first()
            is not None
        )
        db.add(
            ContactIdentity(
                contact_id=contact.id,
                platform=normalized_platform,
                platform_user_id=normalized_value,
                normalized_value=normalized_value,
                is_primary=not has_identity,
                metadata_json={},
            )
        )

    def _normalize_platform(self, platform: str) -> str:
        normalized = str(platform or "").strip().lower()
        if normalized in {"instagram_dm", "ig", "insta"}:
            return "instagram"
        if normalized in {"messenger", "facebook_messenger"}:
            return "facebook"
        return normalized or "unknown"

    def _normalize_identity_value(self, platform: str, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""

        if platform == "whatsapp":
            digits = "".join(ch for ch in raw if ch.isdigit())
            return digits or raw

        return raw.lower()

    def _find_contact_by_legacy_fields(
        self,
        *,
        db: Session,
        platform: str,
        normalized_value: str,
    ) -> Contact | None:
        legacy_query_builders: dict[str, Callable[[], Contact | None]] = {
            "instagram": lambda: db.query(Contact)
            .filter(func.lower(Contact.instagram_user_id) == normalized_value)
            .first(),
            "tiktok": lambda: db.query(Contact)
            .filter(func.lower(Contact.tiktok_user_id) == normalized_value)
            .first(),
            "youtube": lambda: db.query(Contact)
            .filter(func.lower(Contact.youtube_channel_id) == normalized_value)
            .first(),
        }
        direct_query = legacy_query_builders.get(platform)
        if direct_query is not None:
            return direct_query()

        if platform == "whatsapp":
            contacts_with_phone = db.query(Contact).filter(Contact.phone.isnot(None)).all()
            for contact in contacts_with_phone:
                maybe_digits = "".join(ch for ch in str(contact.phone or "") if ch.isdigit())
                if maybe_digits and maybe_digits == normalized_value:
                    return contact
                if str(contact.phone or "").strip() == normalized_value:
                    return contact
        return None

    def _find_unique_contact_by_name(self, *, db: Session, profile_name: str) -> Contact | None:
        normalized_name = str(profile_name or "").strip().lower()
        if not normalized_name:
            return None

        matches = (
            db.query(Contact)
            .filter(Contact.name.isnot(None), func.lower(Contact.name) == normalized_name)
            .limit(2)
            .all()
        )
        if len(matches) == 1:
            return matches[0]
        return None

    def _set_legacy_identity_field(self, contact: Contact, platform: str, normalized_value: str) -> None:
        if platform == "whatsapp" and not contact.phone:
            contact.phone = normalized_value
        if platform == "instagram" and not contact.instagram_user_id:
            contact.instagram_user_id = normalized_value

    def _update_contact_name_if_missing(self, contact: Contact, profile_name: str | None) -> None:
        cleaned_name = str(profile_name or "").strip()
        if cleaned_name and not str(contact.name or "").strip():
            contact.name = cleaned_name
