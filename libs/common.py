"""Shared helpers for every microservice: app factory, DB init, events, HTTP calls, JWT."""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
import redis
import requests
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError

log = logging.getLogger("common")
db = SQLAlchemy()


# --------------------------------------------------------------------------- app
def create_service(name):
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s [{name}] %(levelname)s %(message)s")
    app = Flask(name)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{name}.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.get("/health")
    def health():
        return jsonify(status="ok", service=name)

    return app


def init_db(app, seed=None):
    """Create tables (retrying while Postgres starts) and optionally seed."""
    for attempt in range(30):
        try:
            with app.app_context():
                db.create_all()
                if seed:
                    seed()
            return
        except OperationalError:
            log.warning("database not ready (attempt %s), retrying...", attempt + 1)
            time.sleep(2)
    raise RuntimeError("database never became ready")


def error(message, status=400, **extra):
    return jsonify(error=message, **extra), status


# ------------------------------------------------------------------------ events
_redis = None


def _client():
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    return _redis


def publish(event, payload):
    """Fire-and-forget event on Redis pub/sub. Never raises into request handling."""
    try:
        _client().publish(event, json.dumps(payload, default=str))
        log.info("published %s", event)
    except Exception:
        log.exception("failed to publish %s", event)


def subscribe(app, handlers):
    """Run handlers {event_name: fn(payload)} in a background thread inside the app context."""

    def run():
        while True:
            try:
                pubsub = _client().pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(*handlers.keys())
                log.info("subscribed to %s", list(handlers))
                for msg in pubsub.listen():
                    try:
                        with app.app_context():
                            handlers[msg["channel"]](json.loads(msg["data"]))
                    except Exception:
                        log.exception("handler for %s failed", msg.get("channel"))
            except Exception:
                log.exception("subscriber connection lost, retrying in 3s")
                time.sleep(3)

    threading.Thread(target=run, daemon=True, name="event-subscriber").start()


# -------------------------------------------------------------------------- http
def service_url(name):
    return os.environ.get(f"{name.upper()}_SERVICE_URL", f"http://{name}-service:5000")


def call(service, method, path, **kwargs):
    """HTTP call to another service, e.g. call('product', 'GET', '/products')."""
    kwargs.setdefault("timeout", 10)
    return requests.request(method, service_url(service) + path, **kwargs)


# --------------------------------------------------------------------------- jwt
def _secret():
    return os.environ.get("JWT_SECRET", "dev-change-me-in-production")


def make_token(payload, hours=12):
    data = dict(payload, exp=datetime.now(timezone.utc) + timedelta(hours=hours))
    return jwt.encode(data, _secret(), algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
