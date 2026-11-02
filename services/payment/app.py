"""Payment service: mock payment gateway.

Approves every positive amount. Replace `_charge` with a real provider (Stripe, etc.) later.
Set `simulate: "decline"` in the request body to test the declined path.
"""
from datetime import datetime

from flask import request, jsonify

from common import create_service, db, init_db, error, publish

app = create_service("payment")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "order_id": self.order_id, "amount_cents": self.amount_cents,
                "status": self.status, "created_at": self.created_at.isoformat()}


def _charge(amount_cents, simulate=None):
    return amount_cents > 0 and simulate != "decline"


@app.post("/payments")
def create_payment():
    d = request.get_json(force=True)
    approved = _charge(int(d["amount_cents"]), d.get("simulate"))
    payment = Payment(order_id=d["order_id"], amount_cents=d["amount_cents"],
                      status="approved" if approved else "declined")
    db.session.add(payment)
    db.session.commit()
    publish("payment.completed" if approved else "payment.failed", payment.to_dict())
    return jsonify(payment.to_dict()), 201


@app.get("/payments")
def list_payments():
    return jsonify([p.to_dict() for p in Payment.query.order_by(Payment.id.desc()).limit(100)])


@app.get("/payments/order/<int:order_id>")
def payments_for_order(order_id):
    rows = Payment.query.filter_by(order_id=order_id).all()
    return jsonify([p.to_dict() for p in rows]) if rows else error("No payments for order.", 404)


init_db(app)
