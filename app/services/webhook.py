import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def send_webhook(url: str, payload: dict, max_retries: int = 3) -> None:
    delay = 1.0
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return
            except Exception as exc:
                last_error = exc
                logger.warning("webhook attempt %s/%s failed: %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2

    raise RuntimeError(f"webhook failed after {max_retries} attempts") from last_error
