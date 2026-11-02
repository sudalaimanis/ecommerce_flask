# E-commerce microservices (Flask)

A computer-shop storefront split into microservices. Services talk over REST for lookups and
over Redis pub/sub events for everything that happens *after* an order is paid.

## Run locally

```bash
docker compose up --build        # http://localhost:5000
docker compose down -v           # stop and wipe all data
```

## Services

| Service | Role | Owns (DB) |
|---|---|---|
| `web` | Storefront UI, the only public entry point | – |
| `user` | Register / login, issues JWTs | `user_db` |
| `customer` | Customer profile, saved shipping address | `customer_db` |
| `product` | Catalog: categories and products | `product_db` |
| `pricing` | Prices, discounts, order quotes | `pricing_db` |
| `inventory` | Stock; atomic reserve / release | `inventory_db` |
| `cart` | Carts and the checkout orchestration | `cart_db` |
| `order` | Orders and their status | `order_db` |
| `payment` | Payments (mock gateway – always approves) | `payment_db` |
| `order-processing` | Moves an order through its lifecycle from events | `processing_db` |
| `logistics` | Shipments and tracking numbers | `logistics_db` |
| `notification` | Builds and sends emails from events | `notification_db` |

Each service is `services/<name>/app.py`; shared helpers are in `libs/common.py`.
Postgres and Redis are shared infrastructure, but every service has its **own database**.

## Order flow

```
web ──POST /checkout──▶ cart ─▶ pricing   (quote)
                          ├──▶ inventory  (reserve stock; released again on any failure)
                          ├──▶ order      (create, publishes order.created)
                          └──▶ payment    (approve, publishes payment.completed)

payment.completed ─▶ order-processing ─▶ marks CONFIRMED, publishes order.confirmed
order.confirmed   ─▶ logistics (creates shipment, publishes shipment.created)
                  ─▶ notification (order confirmation email)
                  ─▶ customer (remembers shipping address)
shipment.created  ─▶ order-processing (marks SHIPPED) and notification (shipped email)
```

## Emails

The notification service records every email it would send (`GET` its `/notifications`, e.g.
`docker compose exec notification-service python -c "import requests;print(requests.get('http://localhost:5000/notifications').json())"`).
To actually send, set SMTP credentials before starting (Gmail needs an App Password):

```bash
export SMTP_USER=you@gmail.com SMTP_PASSWORD=your-app-password
docker compose up -d notification-service
```

## Kubernetes / CI

- `k8s-files/infra.yml` – secrets, Postgres, Redis. **Replace the `change-me` secrets first.**
- `k8s-files/services.yml` – all service Deployments and Services (only `web` is a LoadBalancer).
- `Jenkinsfile` builds, scans, and pushes `sudalaimmanis/flaskapp-<service>:<build>` for every service
  and writes the new tags into `k8s-files/services.yml`.

## Known limitations

- Redis pub/sub is fire-and-forget: an event is lost if its consumer is down, and running more than
  one replica of a backend service would process every event once per replica. Keep backends at 1
  replica (only `web` scales) or move to Redis Streams / RabbitMQ for durable delivery.
- Internal service APIs are unauthenticated and rely on the private network; only `web` is exposed.
- The payment service is a mock.
