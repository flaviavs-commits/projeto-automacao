from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.contact import Contact


class ScheduleService:
    """Minimal appointment scheduling service for dashboard OP."""
    _LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

    def list_appointments(
        self,
        *,
        db: Session,
        include_next: bool = False,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(self._LOCAL_TZ)
        if start_date is None and end_date is None:
            start_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            end_day_local = start_day_local + timedelta(days=7)
        else:
            effective_start = start_date or end_date
            effective_end = end_date or effective_start
            if effective_start is None or effective_end is None:
                start_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                end_day_local = start_day_local + timedelta(days=7)
            else:
                if effective_end < effective_start:
                    effective_start, effective_end = effective_end, effective_start
                start_day_local = datetime.combine(effective_start, datetime.min.time(), tzinfo=self._LOCAL_TZ)
                end_day_local = datetime.combine(effective_end, datetime.min.time(), tzinfo=self._LOCAL_TZ) + timedelta(days=1)
        start_day_utc = start_day_local.astimezone(timezone.utc)
        end_day_utc = end_day_local.astimezone(timezone.utc)

        rows = (
            db.execute(
                select(Appointment)
                .where(
                    and_(
                        Appointment.start_time >= start_day_utc,
                        Appointment.start_time < end_day_utc,
                    )
                )
                .order_by(Appointment.start_time.asc())
            )
            .scalars()
            .all()
        )
        range_days = max(1, (end_day_local - start_day_local).days)
        range_days = min(range_days, 93)
        slots = self._build_slots(start_day_local=start_day_local, days=range_days, reserved=rows)

        payload = {
            "appointments": [self._serialize(item) for item in rows],
            "slots": slots,
            "range_start_date": start_day_local.date().isoformat(),
            "range_end_date": (end_day_local - timedelta(days=1)).date().isoformat(),
        }

        if include_next:
            next_rows = (
                db.execute(
                    select(Appointment)
                    .where(
                        and_(
                            Appointment.start_time >= now_utc,
                            Appointment.status == "reserved",
                        )
                    )
                    .order_by(Appointment.start_time.asc())
                    .limit(5)
                )
                .scalars()
                .all()
            )
            payload["next_appointments"] = [self._serialize(item) for item in next_rows]
            payload["next_appointments_message"] = (
                ""
                if next_rows
                else "Nao ha agendamentos proximos."
            )
        return payload

    def create_appointment(
        self,
        *,
        db: Session,
        contact_id: UUID | None,
        conversation_id: UUID | None,
        customer_name: str | None,
        customer_phone: str | None,
        start_time: datetime,
        end_time: datetime,
        status: str = "reserved",
        notes: str | None = None,
    ) -> dict:
        contact_name = str(customer_name or "").strip()
        contact_phone_clean = str(customer_phone or "").strip()
        if contact_id:
            contact = db.get(Contact, contact_id)
            if contact is not None:
                if not contact_name:
                    contact_name = str(contact.name or "").strip()
                if not contact_phone_clean:
                    contact_phone_clean = str(contact.phone or "").strip()

        appt = Appointment(
            contact_id=contact_id,
            conversation_id=conversation_id,
            customer_name=contact_name or None,
            customer_phone=contact_phone_clean or None,
            start_time=start_time,
            end_time=end_time,
            status=str(status or "reserved").strip().lower() or "reserved",
            notes=str(notes or "").strip() or None,
        )
        db.add(appt)
        db.flush()
        db.add(
            AuditLog(
                entity_type="appointment",
                entity_id=appt.id,
                event_type="appointment_created",
                details={"appointment_id": str(appt.id)},
            )
        )
        db.commit()
        db.refresh(appt)
        return self._serialize(appt)

    def update_appointment(
        self,
        *,
        db: Session,
        appointment_id: UUID,
        status: str | None = None,
        notes: str | None = None,
    ) -> dict | None:
        appt = db.get(Appointment, appointment_id)
        if appt is None:
            return None
        if status is not None:
            appt.status = str(status or "").strip().lower() or appt.status
        if notes is not None:
            appt.notes = str(notes or "").strip() or None
        db.add(
            AuditLog(
                entity_type="appointment",
                entity_id=appt.id,
                event_type="appointment_updated",
                details={"appointment_id": str(appt.id)},
            )
        )
        db.commit()
        db.refresh(appt)
        return self._serialize(appt)

    def _build_slots(self, *, start_day_local: datetime, days: int, reserved: list[Appointment]) -> list[dict]:
        slot_map: dict[str, str] = {}
        for item in reserved:
            key = self._to_local(item.start_time).strftime("%Y-%m-%dT%H:00")
            slot_map[key] = "reserved"

        slots: list[dict] = []
        for day in range(days):
            for hour in range(8, 21):
                slot_time = start_day_local + timedelta(days=day, hours=hour)
                key = slot_time.strftime("%Y-%m-%dT%H:00")
                slots.append(
                    {
                        "start_time": slot_time.isoformat(),
                        "status": slot_map.get(key, "free"),
                    }
                )
        return slots

    def _serialize(self, item: Appointment) -> dict:
        return {
            "id": str(item.id),
            "contact_id": str(item.contact_id) if item.contact_id else None,
            "conversation_id": str(item.conversation_id) if item.conversation_id else None,
            "customer_name": item.customer_name,
            "customer_phone": item.customer_phone,
            "start_time": self._to_local(item.start_time).isoformat() if item.start_time else None,
            "end_time": self._to_local(item.end_time).isoformat() if item.end_time else None,
            "status": item.status,
            "notes": item.notes,
        }

    def _to_local(self, value: datetime) -> datetime:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(self._LOCAL_TZ)
