import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.outbox import Outbox
from app.models.payment import Currency, Payment, PaymentStatus
from app.services.outbox_relay import _publish_batch


@pytest.mark.asyncio
async def test_outbox_publish_marks_published(session_factory):
    import app.services.outbox_relay as relay

    relay.SessionLocal = session_factory

    payment_id = uuid4()
    async with session_factory() as session:
        session.add(
            Payment(
                id=payment_id,
                amount=Decimal("1.00"),
                currency=Currency.RUB,
                description="o",
                status=PaymentStatus.pending,
                idempotency_key=f"outbox-{payment_id}",
                webhook_url="https://example.com/hook",
            )
        )
        session.add(
            Outbox(
                aggregate_type="payment",
                aggregate_id=payment_id,
                event_type="payments.new",
                payload={"payment_id": str(payment_id)},
            )
        )
        await session.commit()

    published = []

    class FakeExchange:
        async def publish(self, message, routing_key):
            published.append((json.loads(message.body), routing_key, dict(message.headers)))

    channel = MagicMock()
    channel.default_exchange = FakeExchange()

    await _publish_batch(channel)

    assert len(published) == 1
    assert published[0][0] == {"payment_id": str(payment_id)}
    assert published[0][1] == "payments.new"
    assert published[0][2]["x-attempt"] == 0

    async with session_factory() as session:
        row = (await session.scalars(select(Outbox))).one()
        assert row.published_at is not None


@pytest.mark.asyncio
async def test_outbox_skips_already_published(session_factory):
    import app.services.outbox_relay as relay

    relay.SessionLocal = session_factory

    async with session_factory() as session:
        session.add(
            Outbox(
                aggregate_type="payment",
                aggregate_id=uuid4(),
                event_type="payments.new",
                payload={"payment_id": "x"},
                published_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    channel = MagicMock()
    channel.default_exchange = MagicMock()
    channel.default_exchange.publish = AsyncMock()

    await _publish_batch(channel)
    channel.default_exchange.publish.assert_not_awaited()
