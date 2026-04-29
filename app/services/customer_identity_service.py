from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity


class CustomerIdentityService:
    """Resolves a single customer across platform identities."""

    _EVOLUTION_WHATSAPP_SUFFIXES = ("@s.whatsapp.net", "@c.us")
    _WHATSAPP_LID_SUFFIX = "@lid"

    def resolve_or_create_contact(
        self,
        *,
        db: Session,
        platform: str,
        platform_user_id: str,
        profile_name: str | None = None,
        alternate_platform_user_ids: list[str] | None = None,
        preferred_phone_number: str | None = None,
        resolution_meta: dict | None = None,
    ) -> Contact:
        normalized_platform = self._normalize_platform(platform)
        self._init_resolution_meta(resolution_meta)
        if normalized_platform == "whatsapp":
            return self._resolve_whatsapp_contact(
                db=db,
                platform_user_id=platform_user_id,
                profile_name=profile_name,
                alternate_platform_user_ids=alternate_platform_user_ids or [],
                preferred_phone_number=preferred_phone_number,
                resolution_meta=resolution_meta,
            )
        return self._resolve_non_whatsapp_contact(
            db=db,
            platform=normalized_platform,
            platform_user_id=platform_user_id,
            profile_name=profile_name,
            alternate_platform_user_ids=alternate_platform_user_ids or [],
        )

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

    def _resolve_whatsapp_contact(
        self,
        *,
        db: Session,
        platform_user_id: str,
        profile_name: str | None,
        alternate_platform_user_ids: list[str],
        preferred_phone_number: str | None,
        resolution_meta: dict | None,
    ) -> Contact:
        primary_value = self._normalize_identity_value("whatsapp", platform_user_id)
        if not primary_value:
            raise ValueError("platform_user_id is required")

        normalized_alternate_values = self._normalize_identity_values("whatsapp", alternate_platform_user_ids)
        normalized_alternate_values = [
            value for value in normalized_alternate_values if value != primary_value
        ]
        all_values = [primary_value, *normalized_alternate_values]
        preferred_phone = self._normalize_whatsapp_phone_number(str(preferred_phone_number or ""))
        phone_candidates = self._extract_whatsapp_phone_candidates(
            values=all_values,
            preferred_phone_number=preferred_phone,
        )
        lid_candidates = self._extract_whatsapp_lid_candidates(values=all_values)

        phone_contact = self._find_contact_by_whatsapp_phone_candidates(
            db=db,
            phone_candidates=phone_candidates,
        )
        lid_contact = self._find_contact_by_whatsapp_lid_candidates(
            db=db,
            lid_candidates=lid_candidates,
        )

        if phone_contact is not None and resolution_meta is not None:
            resolution_meta["matched_by_phone"] = True
        if lid_contact is not None and resolution_meta is not None:
            resolution_meta["matched_by_lid"] = True

        if phone_contact is not None and lid_contact is not None and phone_contact.id != lid_contact.id:
            self._register_identity_conflict(
                resolution_meta=resolution_meta,
                phone_contact_id=str(phone_contact.id),
                lid_contact_id=str(lid_contact.id),
                phone_candidates=phone_candidates,
                lid_candidates=lid_candidates,
                strategy="phone_priority_no_auto_merge",
            )

        if phone_contact is not None:
            contact = phone_contact
        elif lid_contact is not None:
            contact = lid_contact
        else:
            contact = Contact(name=None, is_temporary=True)
            db.add(contact)
            db.flush()
            if resolution_meta is not None:
                resolution_meta["temporary_created"] = True

        self._update_contact_name_if_missing(
            contact=contact,
            profile_name=profile_name,
            platform="whatsapp",
        )
        self._apply_preferred_phone_number(contact, "whatsapp", preferred_phone)
        self._set_legacy_identity_field(contact, "whatsapp", primary_value)

        if self._contact_has_reliable_whatsapp_identity(contact):
            contact.is_temporary = False
        elif preferred_phone:
            contact.is_temporary = False
            if resolution_meta is not None:
                resolution_meta["identity_enriched"] = True

        identity_values_to_link: list[str] = []
        for candidate in [primary_value, *normalized_alternate_values, *phone_candidates, *lid_candidates]:
            normalized_candidate = self._normalize_identity_value("whatsapp", candidate)
            if normalized_candidate and normalized_candidate not in identity_values_to_link:
                identity_values_to_link.append(normalized_candidate)

        for identity_value in identity_values_to_link:
            self._upsert_whatsapp_identity_with_conflict_guard(
                db=db,
                contact=contact,
                platform_user_id=identity_value,
                resolution_meta=resolution_meta,
            )

        if preferred_phone and not contact.phone:
            contact.phone = preferred_phone
            contact.is_temporary = False
            if resolution_meta is not None:
                resolution_meta["identity_enriched"] = True

        return contact

    def _resolve_non_whatsapp_contact(
        self,
        *,
        db: Session,
        platform: str,
        platform_user_id: str,
        profile_name: str | None,
        alternate_platform_user_ids: list[str],
    ) -> Contact:
        normalized_value = self._normalize_identity_value(platform, platform_user_id)
        if not normalized_value:
            raise ValueError("platform_user_id is required")

        normalized_alternate_values = self._normalize_identity_values(platform, alternate_platform_user_ids)
        normalized_alternate_values = [
            value for value in normalized_alternate_values if value != normalized_value
        ]
        lookup_values = self._build_lookup_values(platform, [normalized_value, *normalized_alternate_values])
        identity = self._find_identity_by_platform_user_ids(
            db=db,
            platform=platform,
            normalized_values=lookup_values,
        )
        if identity is not None:
            contact = identity.contact
            self._update_contact_name_if_missing(
                contact=contact,
                profile_name=profile_name,
                platform=platform,
            )
            self._set_legacy_identity_field(contact, platform, normalized_value)
            self.upsert_identity_for_contact(
                db=db,
                contact=contact,
                platform=platform,
                platform_user_id=normalized_value,
            )
            for alternate_value in normalized_alternate_values:
                self.upsert_identity_for_contact(
                    db=db,
                    contact=contact,
                    platform=platform,
                    platform_user_id=alternate_value,
                )
            return contact

        contact = self._find_contact_by_legacy_fields(
            db=db,
            platform=platform,
            normalized_values=lookup_values,
        )
        if contact is None and profile_name:
            contact = self._find_unique_contact_by_name(db=db, profile_name=profile_name)

        if contact is None:
            initial_name = profile_name if self._should_persist_profile_name(platform) else None
            contact = Contact(name=initial_name, is_temporary=False)
            db.add(contact)
            db.flush()
        else:
            self._update_contact_name_if_missing(
                contact=contact,
                profile_name=profile_name,
                platform=platform,
            )

        self._set_legacy_identity_field(contact, platform, normalized_value)
        self.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform=platform,
            platform_user_id=normalized_value,
        )
        for alternate_value in normalized_alternate_values:
            self.upsert_identity_for_contact(
                db=db,
                contact=contact,
                platform=platform,
                platform_user_id=alternate_value,
            )
        return contact

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
            normalized_whatsapp = raw
            lowered_whatsapp = normalized_whatsapp.lower()
            for suffix in self._EVOLUTION_WHATSAPP_SUFFIXES:
                if lowered_whatsapp.endswith(suffix):
                    normalized_whatsapp = normalized_whatsapp[: -len(suffix)]
                    digits = "".join(ch for ch in normalized_whatsapp if ch.isdigit())
                    return digits or normalized_whatsapp
            if lowered_whatsapp.endswith(self._WHATSAPP_LID_SUFFIX):
                normalized_whatsapp = normalized_whatsapp[: -len(self._WHATSAPP_LID_SUFFIX)]
                digits = "".join(ch for ch in normalized_whatsapp if ch.isdigit())
                return f"{digits}{self._WHATSAPP_LID_SUFFIX}" if digits else lowered_whatsapp
            if "@" in lowered_whatsapp:
                return lowered_whatsapp
            digits = "".join(ch for ch in normalized_whatsapp if ch.isdigit())
            return digits or normalized_whatsapp

        return raw.lower()

    def _find_contact_by_legacy_fields(
        self,
        *,
        db: Session,
        platform: str,
        normalized_values: list[str],
    ) -> Contact | None:
        legacy_query_builders: dict[str, Callable[[], Contact | None]] = {
            "instagram": lambda: db.query(Contact)
            .filter(func.lower(Contact.instagram_user_id).in_(normalized_values))
            .first(),
            "tiktok": lambda: db.query(Contact)
            .filter(func.lower(Contact.tiktok_user_id).in_(normalized_values))
            .first(),
            "youtube": lambda: db.query(Contact)
            .filter(func.lower(Contact.youtube_channel_id).in_(normalized_values))
            .first(),
        }
        direct_query = legacy_query_builders.get(platform)
        if direct_query is not None:
            return direct_query()

        if platform == "whatsapp":
            normalized_phone_values = {
                phone
                for phone in (
                    self._normalize_whatsapp_phone_number(value) for value in normalized_values
                )
                if phone
            }
            if not normalized_phone_values:
                return None
            contacts_with_phone = db.query(Contact).filter(Contact.phone.isnot(None)).all()
            for contact in contacts_with_phone:
                maybe_digits = self._normalize_whatsapp_phone_number(str(contact.phone or ""))
                if maybe_digits and maybe_digits in normalized_phone_values:
                    return contact
        return None

    def _find_identity_by_platform_user_ids(
        self,
        *,
        db: Session,
        platform: str,
        normalized_values: list[str],
    ) -> ContactIdentity | None:
        values = [value for value in normalized_values if value]
        if not values:
            return None
        return (
            db.query(ContactIdentity)
            .filter(
                ContactIdentity.platform == platform,
                ContactIdentity.platform_user_id.in_(values),
            )
            .order_by(ContactIdentity.is_primary.desc(), ContactIdentity.created_at.asc())
            .first()
        )

    def _normalize_identity_values(self, platform: str, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        for value in values:
            normalized = self._normalize_identity_value(platform, value)
            if normalized and normalized not in normalized_values:
                normalized_values.append(normalized)
        return normalized_values

    def _build_lookup_values(self, platform: str, normalized_values: list[str]) -> list[str]:
        lookup_values: list[str] = []
        for value in normalized_values:
            cleaned = str(value or "").strip()
            if not cleaned:
                continue
            if cleaned not in lookup_values:
                lookup_values.append(cleaned)
            if platform == "whatsapp" and cleaned.endswith(self._WHATSAPP_LID_SUFFIX):
                legacy_digits = "".join(ch for ch in cleaned if ch.isdigit())
                if legacy_digits and legacy_digits not in lookup_values:
                    lookup_values.append(legacy_digits)
        return lookup_values

    def _normalize_whatsapp_phone_number(self, value: str) -> str:
        normalized = self._normalize_identity_value("whatsapp", value)
        if not normalized or normalized.endswith(self._WHATSAPP_LID_SUFFIX) or "@" in normalized:
            return ""
        digits = "".join(ch for ch in normalized if ch.isdigit())
        return digits or ""

    def _apply_preferred_phone_number(
        self,
        contact: Contact,
        platform: str,
        preferred_phone_number: str | None,
    ) -> None:
        if platform != "whatsapp":
            return
        normalized_phone = self._normalize_whatsapp_phone_number(str(preferred_phone_number or ""))
        if normalized_phone:
            contact.phone = normalized_phone

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
        if (
            platform == "whatsapp"
            and normalized_value
            and not normalized_value.endswith(self._WHATSAPP_LID_SUFFIX)
            and "@" not in normalized_value
            and not contact.phone
        ):
            contact.phone = normalized_value
        if platform == "instagram" and not contact.instagram_user_id:
            contact.instagram_user_id = normalized_value

    def _should_persist_profile_name(self, platform: str) -> bool:
        return platform != "whatsapp"

    def _update_contact_name_if_missing(
        self,
        *,
        contact: Contact,
        profile_name: str | None,
        platform: str,
    ) -> None:
        if not self._should_persist_profile_name(platform):
            return
        cleaned_name = str(profile_name or "").strip()
        if cleaned_name and not str(contact.name or "").strip():
            contact.name = cleaned_name

    def _extract_whatsapp_phone_candidates(
        self,
        *,
        values: list[str],
        preferred_phone_number: str,
    ) -> list[str]:
        candidates: list[str] = []
        if preferred_phone_number:
            candidates.append(preferred_phone_number)
        for value in values:
            normalized_phone = self._normalize_whatsapp_phone_number(value)
            if normalized_phone and normalized_phone not in candidates:
                candidates.append(normalized_phone)
        return candidates

    def _extract_whatsapp_lid_candidates(self, *, values: list[str]) -> list[str]:
        candidates: list[str] = []
        for value in values:
            cleaned = str(value or "").strip().lower()
            if cleaned.endswith(self._WHATSAPP_LID_SUFFIX) and cleaned not in candidates:
                candidates.append(cleaned)
        return candidates

    def _find_contact_by_whatsapp_phone_candidates(
        self,
        *,
        db: Session,
        phone_candidates: list[str],
    ) -> Contact | None:
        if not phone_candidates:
            return None
        identity = self._find_identity_by_platform_user_ids(
            db=db,
            platform="whatsapp",
            normalized_values=phone_candidates,
        )
        if identity is not None:
            return identity.contact
        return self._find_contact_by_legacy_fields(
            db=db,
            platform="whatsapp",
            normalized_values=phone_candidates,
        )

    def _find_contact_by_whatsapp_lid_candidates(
        self,
        *,
        db: Session,
        lid_candidates: list[str],
    ) -> Contact | None:
        if not lid_candidates:
            return None
        lookup_values = self._build_lookup_values("whatsapp", lid_candidates)
        identity = self._find_identity_by_platform_user_ids(
            db=db,
            platform="whatsapp",
            normalized_values=lookup_values,
        )
        return identity.contact if identity is not None else None

    def _upsert_whatsapp_identity_with_conflict_guard(
        self,
        *,
        db: Session,
        contact: Contact,
        platform_user_id: str,
        resolution_meta: dict | None,
    ) -> None:
        normalized_value = self._normalize_identity_value("whatsapp", platform_user_id)
        if not normalized_value:
            return
        lookup_values = self._build_lookup_values("whatsapp", [normalized_value])
        existing_identity = self._find_identity_by_platform_user_ids(
            db=db,
            platform="whatsapp",
            normalized_values=lookup_values,
        )
        if existing_identity is not None and existing_identity.contact_id != contact.id:
            self._register_identity_conflict(
                resolution_meta=resolution_meta,
                phone_contact_id=str(contact.id),
                lid_contact_id=str(existing_identity.contact_id),
                phone_candidates=[normalized_value],
                lid_candidates=[normalized_value],
                strategy="identity_already_owned",
            )
            return
        self.upsert_identity_for_contact(
            db=db,
            contact=contact,
            platform="whatsapp",
            platform_user_id=normalized_value,
        )

    def _contact_has_reliable_whatsapp_identity(self, contact: Contact) -> bool:
        if self._normalize_whatsapp_phone_number(str(contact.phone or "")):
            return True
        return False

    def _init_resolution_meta(self, resolution_meta: dict | None) -> None:
        if resolution_meta is None:
            return
        resolution_meta.setdefault("matched_by_phone", False)
        resolution_meta.setdefault("matched_by_lid", False)
        resolution_meta.setdefault("temporary_created", False)
        resolution_meta.setdefault("identity_enriched", False)
        resolution_meta.setdefault("identity_conflicts", [])

    def _register_identity_conflict(
        self,
        *,
        resolution_meta: dict | None,
        phone_contact_id: str,
        lid_contact_id: str,
        phone_candidates: list[str],
        lid_candidates: list[str],
        strategy: str,
    ) -> None:
        if resolution_meta is None:
            return
        conflict = {
            "phone_contact_id": phone_contact_id,
            "lid_contact_id": lid_contact_id,
            "phone_candidates": phone_candidates,
            "lid_candidates": lid_candidates,
            "strategy": strategy,
        }
        resolution_meta["identity_conflicts"].append(conflict)
