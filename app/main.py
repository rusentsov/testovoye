import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.payments import router as payments_router
from app.services.outbox_relay import run_outbox_relay


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_outbox_relay(stop_event))
    yield
    stop_event.set()
    await task


app = FastAPI(title="Payments API", lifespan=lifespan)
app.include_router(payments_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
