import pytest
import respx
from httpx import Response

from app.services.webhook import send_webhook


@pytest.mark.asyncio
@respx.mock
async def test_webhook_success_first_try():
    route = respx.post("https://example.com/hook").mock(return_value=Response(200))
    await send_webhook("https://example.com/hook", {"payment_id": "1"}, max_retries=3)
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_webhook_retries_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.services.webhook.asyncio.sleep", _fake_sleep)

    route = respx.post("https://example.com/hook").mock(
        side_effect=[Response(500), Response(500), Response(200)]
    )
    await send_webhook("https://example.com/hook", {"ok": True}, max_retries=3)
    assert route.call_count == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
@respx.mock
async def test_webhook_fails_after_max_retries(monkeypatch):
    async def _fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.services.webhook.asyncio.sleep", _fake_sleep)

    respx.post("https://example.com/hook").mock(return_value=Response(500))
    with pytest.raises(RuntimeError, match="webhook failed after 3 attempts"):
        await send_webhook("https://example.com/hook", {"ok": True}, max_retries=3)
