from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.payment import PaymentCreate


def test_payment_create_valid():
    data = PaymentCreate(
        amount=Decimal("10.50"),
        currency="RUB",
        description="ok",
        webhook_url="https://example.com/hook",
    )
    assert data.amount == Decimal("10.50")
    assert data.currency.value == "RUB"


@pytest.mark.parametrize(
    "amount",
    [Decimal("0"), Decimal("-1"), Decimal("-0.01")],
)
def test_payment_create_rejects_non_positive_amount(amount):
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=amount,
            currency="USD",
            description="x",
            webhook_url="https://example.com/hook",
        )


def test_payment_create_rejects_bad_currency():
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("1.00"),
            currency="GBP",
            description="x",
            webhook_url="https://example.com/hook",
        )


def test_payment_create_rejects_empty_description():
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("1.00"),
            currency="EUR",
            description="",
            webhook_url="https://example.com/hook",
        )


def test_payment_create_rejects_invalid_webhook():
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=Decimal("1.00"),
            currency="EUR",
            description="x",
            webhook_url="not-a-url",
        )
