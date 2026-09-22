import asyncio
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.payment import Payment, PaymentStatus
from app.services.webhook import send_webhook

logger = logging.getLogger(__name__)


def _webhook_payload(payment: Payment) -> dict:
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }


async def process_payment(
    payment_id: str,
    *,
    delay_range: tuple[float, float] | None = (2.0, 5.0),
    success_rate: float = 0.9,
) -> None:
    pid = UUID(payment_id)

    async with SessionLocal() as session:
        payment = await session.scalar(select(Payment).where(Payment.id == pid).with_for_update())
        if payment is None:
            logger.error("payment not found: %s", payment_id)
            return
        if payment.status != PaymentStatus.pending:
            payload = _webhook_payload(payment)
            webhook_url = payment.webhook_url
        else:
            payload = None
            webhook_url = payment.webhook_url

    if payload is not None:
        await send_webhook(webhook_url, payload, max_retries=settings.max_retries)
        return

    if delay_range is not None:
        await asyncio.sleep(random.uniform(*delay_range))

    async with SessionLocal() as session:
        payment = await session.scalar(select(Payment).where(Payment.id == pid).with_for_update())
        if payment is None:
            return
        if payment.status == PaymentStatus.pending:
            payment.status = (
                PaymentStatus.succeeded if random.random() < success_rate else PaymentStatus.failed
            )
            payment.processed_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(payment)
        payload = _webhook_payload(payment)
        webhook_url = payment.webhook_url

    await send_webhook(webhook_url, payload, max_retries=settings.max_retries)
