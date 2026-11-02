"""Order-processing service: drives an order through its lifecycle from events.

payment.completed -> mark CONFIRMED, emit order.confirmed (logistics + notification react)
shipment.created  -> mark SHIPPED
"""
from datetime import datetime

from flask import jsonify

from common import create_service, db, init_db, subscribe, publish, call

app = create_service("order-processing")


class ProcessingStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False, index=True)
    step = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def _log(order_id, step):
    db.session.add(ProcessingStep(order_id=order_id, step=step))
    db.session.commit()


def on_order_created(order):
    _log(order["id"], "order_created")


def on_payment_completed(payment):
    order_id = payment["order_id"]
    if ProcessingStep.query.filter_by(order_id=order_id, step="order_confirmed").first():
        return  # duplicate event
    order = call("order", "GET", f"/orders/{order_id}").json()
    call("order", "PATCH", f"/orders/{order_id}/status", json={"status": "CONFIRMED"})
    _log(order_id, "payment_completed")
    _log(order_id, "order_confirmed")
    publish("order.confirmed", {**order, "order_id": order_id, "status": "CONFIRMED"})


def on_shipment_created(shipment):
    order_id = shipment["order_id"]
    call("order", "PATCH", f"/orders/{order_id}/status", json={"status": "SHIPPED"})
    _log(order_id, "shipped")


@app.get("/processing/<int:order_id>")
def steps(order_id):
    rows = ProcessingStep.query.filter_by(order_id=order_id).order_by(ProcessingStep.id)
    return jsonify([{"step": r.step, "at": r.created_at.isoformat()} for r in rows])


init_db(app)
subscribe(app, {
    "order.created": on_order_created,
    "payment.completed": on_payment_completed,
    "shipment.created": on_shipment_created,
})
