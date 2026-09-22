import asyncio
import logging

from aio_pika import connect_robust
from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage, RabbitQueue

from app.config import settings
from app.consumer.handler import process_payment
from app.messaging import DLX_NAME, declare_topology

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

payments_queue = RabbitQueue(
    settings.payments_queue,
    durable=True,
    arguments={
        "x-dead-letter-exchange": DLX_NAME,
        "x-dead-letter-routing-key": settings.payments_dlq,
    },
)


@broker.subscriber(payments_queue, no_ack=True)
async def handle_payment(body: dict, msg: RabbitMessage) -> None:
    headers = dict(msg.headers or {})
    attempt = int(headers.get("x-attempt", 0))

    try:
        await process_payment(body["payment_id"])
        await msg.ack()
    except Exception:
        logger.exception("processing failed, attempt=%s", attempt)
        if attempt + 1 >= settings.max_retries:
            await msg.reject(requeue=False)
            return

        delay = 2**attempt
        await asyncio.sleep(delay)
        await broker.publish(
            body,
            queue=settings.payments_queue,
            persist=True,
            headers={**headers, "x-attempt": attempt + 1},
        )
        await msg.ack()


async def _prepare_topology() -> None:
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            connection = await connect_robust(settings.rabbitmq_url)
            try:
                channel = await connection.channel()
                await declare_topology(channel)
            finally:
                await connection.close()
            return
        except Exception as exc:
            last_error = exc
            logger.warning("rabbitmq not ready (%s/30): %s", attempt, exc)
            await asyncio.sleep(2)
    raise RuntimeError("rabbitmq unavailable") from last_error


async def main() -> None:
    await _prepare_topology()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
