from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import safe_compare
from app.schemas.webhook import MetaWebhookEnvelope


router = APIRouter(prefix="/webhooks/meta", tags=["webhooks"])
logger = get_logger(__name__)


@router.get("")
def verify_meta_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hub.mode",
        )

    if not safe_compare(hub_verify_token, settings.meta_verify_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verification token",
        )

    return hub_challenge


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_meta_webhook(
    envelope: Annotated[
        MetaWebhookEnvelope,
        Body(
            examples=[
                {
                    "object": "page",
                    "entry": [
                        {
                            "id": "1234567890",
                            "time": 1710000000,
                            "changes": [
                                {
                                    "field": "messages",
                                    "value": {
                                        "messaging_product": "whatsapp",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
    ],
    request: Request,
) -> dict[str, str]:

    logger.info(
        "meta_webhook_received",
        extra={
            "path": str(request.url.path),
            "environment": settings.app_env,
        },
    )

    return {
        "status": "accepted",
        "object": envelope.object,
    }
