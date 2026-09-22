from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.outbox import Outbox
from app.models.payment import PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services import payment_service


@pytest.mark.asyncio
async def test_create_payment_writes_outbox(session):
    data = PaymentCreate(
        amount=Decimal("12.34"),
        currency="USD",
        description="svc",
        metadata={"a": 1},
        webhook_url="https://example.com/hook",
    )
    payment, created = await payment_service.create_payment(session, data, "key-1")
    assert created is True
    assert payment.status == PaymentStatus.pending
    assert payment.idempotency_key == "key-1"

    outbox = (await session.scalars(select(Outbox))).all()
    assert len(outbox) == 1
    assert outbox[0].payload == {"payment_id": str(payment.id)}
    assert outbox[0].published_at is None


@pytest.mark.asyncio
async def test_create_payment_idempotent(session):
    data = PaymentCreate(
        amount=Decimal("1.00"),
        currency="RUB",
        description="idem",
        webhook_url="https://example.com/hook",
    )
    first, created1 = await payment_service.create_payment(session, data, "same-key")
    second, created2 = await payment_service.create_payment(session, data, "same-key")
    assert created1 is True
    assert created2 is False
    assert first.id == second.id

    outbox = (await session.scalars(select(Outbox))).all()
    assert len(outbox) == 1


@pytest.mark.asyncio
async def test_get_payment(session):
    data = PaymentCreate(
        amount=Decimal("5.00"),
        currency="EUR",
        description="get",
        webhook_url="https://example.com/hook",
    )
    payment, _ = await payment_service.create_payment(session, data, "get-key")
    found = await payment_service.get_payment(session, payment.id)
    assert found is not None
    assert found.id == payment.id
    missing = await payment_service.get_payment(session, uuid4())
    assert missing is None
