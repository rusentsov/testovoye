from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_requires_api_key(client, payment_body):
    resp = await client.post(
        "/api/v1/payments",
        json=payment_body,
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_invalid_api_key(client, payment_body):
    resp = await client.post(
        "/api/v1/payments",
        json=payment_body,
        headers={"X-API-Key": "wrong", "Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_requires_idempotency_key(client, auth_headers, payment_body):
    resp = await client.post("/api/v1/payments", json=payment_body, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_blank_idempotency_key(client, auth_headers, payment_body):
    resp = await client.post(
        "/api/v1/payments",
        json=payment_body,
        headers={**auth_headers, "Idempotency-Key": "   "},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_and_get_payment(client, auth_headers, payment_body):
    create = await client.post(
        "/api/v1/payments",
        json=payment_body,
        headers={**auth_headers, "Idempotency-Key": "api-1"},
    )
    assert create.status_code == 202
    body = create.json()
    assert body["status"] == "pending"
    assert "payment_id" in body
    assert "created_at" in body

    get_resp = await client.get(f"/api/v1/payments/{body['payment_id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["amount"] == "100.50"
    assert detail["currency"] == "RUB"
    assert detail["description"] == "test payment"
    assert detail["metadata"] == {"order_id": "1"}
    assert detail["idempotency_key"] == "api-1"
    assert detail["webhook_url"] == "https://example.com/hook"
    assert detail["status"] == "pending"
    assert detail["processed_at"] is None


@pytest.mark.asyncio
async def test_create_idempotent_returns_same_payment(client, auth_headers, payment_body):
    headers = {**auth_headers, "Idempotency-Key": "api-idem"}
    first = await client.post("/api/v1/payments", json=payment_body, headers=headers)
    second = await client.post("/api/v1/payments", json=payment_body, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["payment_id"] == second.json()["payment_id"]


@pytest.mark.asyncio
async def test_get_unknown_payment(client, auth_headers):
    resp = await client.get(f"/api/v1/payments/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_validation_error(client, auth_headers):
    resp = await client.post(
        "/api/v1/payments",
        json={
            "amount": "-1",
            "currency": "RUB",
            "description": "bad",
            "webhook_url": "https://example.com/hook",
        },
        headers={**auth_headers, "Idempotency-Key": "bad"},
    )
    assert resp.status_code == 422
