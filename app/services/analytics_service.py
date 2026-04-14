from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.message import Message
from app.models.post import Post


class AnalyticsService:
    """Builds dashboard-ready aggregates from the current database state."""

    def _grouped_counts(self, rows: list[tuple[str | None, int]]) -> dict[str, int]:
        grouped: dict[str, int] = {}
        for key, total in rows:
            normalized = str(key or "unknown").strip().lower() or "unknown"
            grouped[normalized] = int(total or 0)
        return grouped

    def get_overview(self) -> dict:
        try:
            with SessionLocal() as db:
                contacts = int(db.scalar(select(func.count()).select_from(Contact)) or 0)
                conversations = int(db.scalar(select(func.count()).select_from(Conversation)) or 0)
                messages = int(db.scalar(select(func.count()).select_from(Message)) or 0)
                posts = int(db.scalar(select(func.count()).select_from(Post)) or 0)
                pending_jobs = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Job)
                        .where(Job.status.in_(("pending", "processing", "retry")))
                    )
                    or 0
                )
                open_conversations = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Conversation)
                        .where(Conversation.status == "open")
                    )
                    or 0
                )
                inbound_messages = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.direction == "inbound")
                    )
                    or 0
                )
                outbound_messages = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.direction == "outbound")
                    )
                    or 0
                )
                ai_generated_messages = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Message)
                        .where(Message.ai_generated.is_(True))
                    )
                    or 0
                )

                posts_by_status_rows = (
                    db.execute(
                        select(Post.status, func.count())
                        .group_by(Post.status)
                        .order_by(func.count().desc())
                    )
                    .tuples()
                    .all()
                )
                jobs_by_status_rows = (
                    db.execute(
                        select(Job.status, func.count())
                        .group_by(Job.status)
                        .order_by(func.count().desc())
                    )
                    .tuples()
                    .all()
                )
                messages_by_platform_rows = (
                    db.execute(
                        select(Message.platform, func.count())
                        .group_by(Message.platform)
                        .order_by(func.count().desc())
                    )
                    .tuples()
                    .all()
                )

                latest_message_at = db.scalar(select(func.max(Message.created_at)))

            return {
                "status": "ok",
                "metrics": {
                    "contacts": contacts,
                    "conversations": conversations,
                    "messages": messages,
                    "posts": posts,
                    "pending_jobs": pending_jobs,
                    "open_conversations": open_conversations,
                    "inbound_messages": inbound_messages,
                    "outbound_messages": outbound_messages,
                    "ai_generated_messages": ai_generated_messages,
                },
                "grouped": {
                    "posts_by_status": self._grouped_counts(posts_by_status_rows),
                    "jobs_by_status": self._grouped_counts(jobs_by_status_rows),
                    "messages_by_platform": self._grouped_counts(messages_by_platform_rows),
                },
                "latest_message_at": latest_message_at.isoformat() if latest_message_at else None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "degraded",
                "metrics": {
                    "contacts": 0,
                    "conversations": 0,
                    "messages": 0,
                    "posts": 0,
                    "pending_jobs": 0,
                },
                "error": f"{exc.__class__.__name__}: {exc}",
            }
