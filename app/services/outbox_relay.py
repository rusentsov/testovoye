import asyncio
import json
import logging
from datetime import datetime, timezone

from aio_pika import Message, connect_robust
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.messaging import declare_topology
from app.models.outbox import Outbox

logger = logging.getLogger(__name__)


async def run_outbox_relay(stop_event: asyncio.Event) -> None:
    connection = None
    for attempt in range(1, 31):
        if stop_event.is_set():
            return
        try:
            connection = await connect_robust(settings.rabbitmq_url)
            break
        except Exception as exc:
            logger.warning("outbox relay: rabbitmq not ready (%s/30): %s", attempt, exc)
            await asyncio.sleep(2)
    if connection is None:
        raise RuntimeError("rabbitmq unavailable for outbox relay")

    channel = await connection.channel()
    await declare_topology(channel)

    try:
        while not stop_event.is_set():
            try:
                await _publish_batch(channel)
            except Exception:
                logger.exception("outbox relay tick failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=settings.outbox_poll_interval_sec)
            except asyncio.TimeoutError:
                pass
    finally:
        await connection.close()


async def _publish_batch(channel) -> None:
    for _ in range(50):
        async with SessionLocal() as session:
            result = await session.execute(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return

            body = json.dumps(row.payload).encode()
            await channel.default_exchange.publish(
                Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=2,
                    headers={"x-attempt": 0},
                ),
                routing_key=settings.payments_queue,
            )
            row.published_at = datetime.now(timezone.utc)
            await session.commit()
