"""End-to-end against running docker compose stack."""

import json
import os
import time
import urllib.error
import urllib.request
import uuid

import pytest

API = os.getenv("E2E_API_URL", "http://localhost:8000")
API_KEY = os.getenv("E2E_API_KEY", "dev-api-key-change-me")


def _request(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            **(headers or {}),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"raw": payload}


def _stack_up() -> bool:
    try:
        status, body = _request("GET", "/health")
        return status == 200 and body.get("status") == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _stack_up(), reason="API stack not running")


def test_e2e_create_process_and_idempotency():
    idem = f"e2e-{uuid.uuid4().hex[:8]}"
    status, created = _request(
        "POST",
        "/api/v1/payments",
        body={
            "amount": "15.25",
            "currency": "RUB",
            "description": "e2e",
            "metadata": {"e2e": True},
            "webhook_url": "https://httpbin.org/post",
        },
        headers={"Idempotency-Key": idem},
    )
    assert status == 202
    assert created["status"] == "pending"
    payment_id = created["payment_id"]

    status2, again = _request(
        "POST",
        "/api/v1/payments",
        body={
            "amount": "15.25",
            "currency": "RUB",
            "description": "e2e",
            "webhook_url": "https://httpbin.org/post",
        },
        headers={"Idempotency-Key": idem},
    )
    assert status2 == 202
    assert again["payment_id"] == payment_id

    final = None
    for _ in range(20):
        time.sleep(1)
        st, detail = _request("GET", f"/api/v1/payments/{payment_id}")
        assert st == 200
        if detail["status"] in ("succeeded", "failed"):
            final = detail
            break

    assert final is not None
    assert final["status"] in ("succeeded", "failed")
    assert final["processed_at"] is not None
    assert final["amount"] == "15.25"
    assert final["currency"] == "RUB"


def test_e2e_unauthorized():
    req = urllib.request.Request(
        f"{API}/api/v1/payments/{uuid.uuid4()}",
        headers={"X-API-Key": "nope"},
        method="GET",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 401
