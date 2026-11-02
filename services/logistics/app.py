"""Logistics service: creates shipments for confirmed orders and tracks their status."""
import uuid
from datetime import datetime, timedelta

from flask import request, jsonify

from common import create_service, db, init_db, error, subscribe, publish

app = create_service("logistics")


class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, unique=True, nullable=False)
    shipping_name = db.Column(db.String(120), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    carrier = db.Column(db.String(40), nullable=False)
    tracking_number = db.Column(db.String(40), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="LABEL_CREATED")
    eta = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"order_id": self.order_id, "carrier": self.carrier, "tracking_number": self.tracking_number,
                "status": self.status, "eta": self.eta.date().isoformat() if self.eta else None,
                "shipping_name": self.shipping_name, "shipping_address": self.shipping_address}


def on_order_confirmed(order):
    if Shipment.query.filter_by(order_id=order["order_id"]).first():
        return  # duplicate event
    shipment = Shipment(
        order_id=order["order_id"], shipping_name=order["shipping_name"],
        shipping_address=order["shipping_address"], carrier="DemoExpress",
        tracking_number="TRK" + uuid.uuid4().hex[:12].upper(),
        eta=datetime.utcnow() + timedelta(days=4),
    )
    db.session.add(shipment)
    db.session.commit()
    publish("shipment.created", {**shipment.to_dict(), "email": order.get("email"), "name": order.get("name")})


@app.get("/shipments")
def list_shipments():
    return jsonify([s.to_dict() for s in Shipment.query.order_by(Shipment.id.desc()).limit(100)])


@app.get("/shipments/<int:order_id>")
def get_shipment(order_id):
    s = Shipment.query.filter_by(order_id=order_id).first()
    return jsonify(s.to_dict()) if s else error("No shipment for this order yet.", 404)


@app.patch("/shipments/<int:order_id>")
def update_shipment(order_id):
    s = Shipment.query.filter_by(order_id=order_id).first()
    if not s:
        return error("No shipment for this order yet.", 404)
    s.status = request.get_json(force=True)["status"]
    db.session.commit()
    return jsonify(s.to_dict())


init_db(app)
subscribe(app, {"order.confirmed": on_order_confirmed})
