from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel

from app.config import settings

DLX_NAME = "payments.dlx"


async def declare_topology(channel: AbstractChannel) -> None:
    dlx = await channel.declare_exchange(DLX_NAME, ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(settings.payments_dlq, durable=True)
    await dlq.bind(dlx, routing_key=settings.payments_dlq)

    await channel.declare_queue(
        settings.payments_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": settings.payments_dlq,
        },
    )
