from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.consumer.handler import process_payment
from app.consumer.main import handle_payment
from app.config import settings
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services import payment_service


@pytest.mark.asyncio
@respx.mock
async def test_process_payment_success(session_factory, monkeypatch):
    import app.consumer.handler as handler_module

    handler_module.SessionLocal = session_factory
    monkeypatch.setattr("app.consumer.handler.random.random", lambda: 0.0)
    monkeypatch.setattr("app.consumer.handler.random.uniform", lambda a, b: 0.0)

    route = respx.post("https://example.com/hook").mock(return_value=Response(200))

    async with session_factory() as session:
        payment, _ = await payment_service.create_payment(
            session,
            PaymentCreate(
                amount=Decimal("10.00"),
                currency="RUB",
                description="proc",
                webhook_url="https://example.com/hook",
            ),
            "proc-1",
        )
        payment_id = str(payment.id)

    await process_payment(payment_id, delay_range=None, success_rate=1.0)

    async with session_factory() as session:
        updated = await session.get(Payment, payment.id)
        assert updated.status == PaymentStatus.succeeded
        assert updated.processed_at is not None

    assert route.call_count == 1
    assert route.calls[0].request.content
    import json

    payload = json.loads(route.calls[0].request.content)
    assert payload["payment_id"] == payment_id
    assert payload["status"] == "succeeded"
    assert payload["amount"] == "10.00"
    assert payload["currency"] == "RUB"


@pytest.mark.asyncio
@respx.mock
async def test_process_payment_failure_path(session_factory, monkeypatch):
    import app.consumer.handler as handler_module

    handler_module.SessionLocal = session_factory
    respx.post("https://example.com/hook").mock(return_value=Response(200))

    async with session_factory() as session:
        payment, _ = await payment_service.create_payment(
            session,
            PaymentCreate(
                amount=Decimal("10.00"),
                currency="USD",
                description="fail",
                webhook_url="https://example.com/hook",
            ),
            "proc-fail",
        )
        payment_id = str(payment.id)

    await process_payment(payment_id, delay_range=None, success_rate=0.0)

    async with session_factory() as session:
        updated = await session.get(Payment, payment.id)
        assert updated.status == PaymentStatus.failed


@pytest.mark.asyncio
@respx.mock
async def test_process_payment_idempotent_status(session_factory, monkeypatch):
    import app.consumer.handler as handler_module

    handler_module.SessionLocal = session_factory
    route = respx.post("https://example.com/hook").mock(return_value=Response(200))

    async with session_factory() as session:
        payment, _ = await payment_service.create_payment(
            session,
            PaymentCreate(
                amount=Decimal("10.00"),
                currency="EUR",
                description="once",
                webhook_url="https://example.com/hook",
            ),
            "proc-once",
        )
        payment_id = str(payment.id)

    await process_payment(payment_id, delay_range=None, success_rate=1.0)
    await process_payment(payment_id, delay_range=None, success_rate=0.0)

    async with session_factory() as session:
        updated = await session.get(Payment, payment.id)
        assert updated.status == PaymentStatus.succeeded

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_handle_payment_acks_on_success(monkeypatch):
    msg = AsyncMock()
    msg.headers = {"x-attempt": 0}
    msg.ack = AsyncMock()
    msg.reject = AsyncMock()

    monkeypatch.setattr(
        "app.consumer.main.process_payment",
        AsyncMock(return_value=None),
    )

    await handle_payment({"payment_id": str(uuid4())}, msg)
    msg.ack.assert_awaited_once()
    msg.reject.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_payment_retries_then_republishes(monkeypatch):
    msg = AsyncMock()
    msg.headers = {"x-attempt": 0}
    msg.ack = AsyncMock()
    msg.reject = AsyncMock()

    monkeypatch.setattr(
        "app.consumer.main.process_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr("app.consumer.main.asyncio.sleep", AsyncMock())
    publish = AsyncMock()
    monkeypatch.setattr("app.consumer.main.broker.publish", publish)

    await handle_payment({"payment_id": "p1"}, msg)

    msg.reject.assert_not_awaited()
    msg.ack.assert_awaited_once()
    publish.assert_awaited_once()
    kwargs = publish.await_args.kwargs
    assert kwargs["headers"]["x-attempt"] == 1
    assert kwargs["queue"] == settings.payments_queue


@pytest.mark.asyncio
async def test_handle_payment_rejects_to_dlq_after_max_retries(monkeypatch):
    msg = AsyncMock()
    msg.headers = {"x-attempt": settings.max_retries - 1}
    msg.ack = AsyncMock()
    msg.reject = AsyncMock()

    monkeypatch.setattr(
        "app.consumer.main.process_payment",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    publish = AsyncMock()
    monkeypatch.setattr("app.consumer.main.broker.publish", publish)

    await handle_payment({"payment_id": "p1"}, msg)

    msg.reject.assert_awaited_once_with(requeue=False)
    msg.ack.assert_not_awaited()
    publish.assert_not_awaited()
