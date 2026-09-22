# Payments microservice

Асинхронная обработка платежей: FastAPI + PostgreSQL + RabbitMQ (FastStream), outbox, DLQ.

## Стек

- FastAPI, Pydantic v2
- SQLAlchemy 2.0 (async), Alembic, PostgreSQL
- RabbitMQ, FastStream
- Docker Compose

## Запуск

```bash
docker compose up --build
```

Сервисы: `api` (:8000), `consumer`, `postgres` (:5432), `rabbitmq` (:5672, UI :15672).

API key по умолчанию: `dev-api-key-change-me` (см. `.env.example`).

## API

### Создать платёж

```bash
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-me" \
  -H "Idempotency-Key: key-001" \
  -d "{
    \"amount\": \"100.50\",
    \"currency\": \"RUB\",
    \"description\": \"Test payment\",
    \"metadata\": {\"order_id\": \"42\"},
    \"webhook_url\": \"https://webhook.site/your-id\"
  }"
```

Ответ `202`: `payment_id`, `status`, `created_at`.

Повтор с тем же `Idempotency-Key` возвращает тот же платёж.

### Получить платёж

```bash
curl -s http://localhost:8000/api/v1/payments/<payment_id> \
  -H "X-API-Key: dev-api-key-change-me"
```

## Поток

1. `POST` пишет `payments` + `outbox` в одной транзакции.
2. Outbox-relay в API публикует в очередь `payments.new`.
3. Consumer эмулирует шлюз (2–5 с, 90% success), обновляет статус, шлёт webhook.
4. Ошибка обработки: до 3 попыток с экспоненциальной задержкой, затем `payments.new.dlq`.

## RabbitMQ UI

http://localhost:15672 — `guest` / `guest`.

## Тесты

```bash
pip install -r requirements.txt
pytest -v
```

Нужны поднятые postgres/rabbitmq (`docker compose up -d postgres rabbitmq`). E2E-тесты дополнительно требуют `api`+`consumer`.
