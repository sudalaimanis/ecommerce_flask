"""Order service: source of truth for orders and their status."""
from datetime import datetime

from flask import request, jsonify

from common import create_service, db, init_db, error, publish

app = create_service("order")


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    email = db.Column(db.String(120))
    name = db.Column(db.String(120))
    shipping_name = db.Column(db.String(120), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="PENDING_PAYMENT")
    reservation_ref = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id, "email": self.email, "name": self.name,
            "shipping_name": self.shipping_name, "shipping_address": self.shipping_address,
            "total_cents": self.total_cents, "status": self.status,
            "created_at": self.created_at.isoformat(),
            "items": [i.to_dict() for i in self.items],
        }


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(200), nullable=False, default="")
    quantity = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            "product_id": self.product_id, "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "product": {"id": self.product_id, "name": self.product_name},
        }


@app.post("/orders")
def create_order():
    d = request.get_json(force=True)
    order = Order(
        user_id=d.get("user_id"), email=d.get("email"), name=d.get("name"),
        shipping_name=d["shipping_name"], shipping_address=d["shipping_address"],
        total_cents=d["total_cents"], reservation_ref=d.get("reservation_ref"),
        items=[OrderItem(product_id=i["product_id"], product_name=i.get("product_name", ""),
                         quantity=i["quantity"], unit_price_cents=i["unit_price_cents"]) for i in d["items"]],
    )
    db.session.add(order)
    db.session.commit()
    publish("order.created", order.to_dict())
    return jsonify(order.to_dict()), 201


@app.get("/orders/<int:order_id>")
def get_order(order_id):
    order = db.session.get(Order, order_id)
    return jsonify(order.to_dict()) if order else error("Order not found.", 404)


@app.get("/orders")
def list_orders():
    q = Order.query
    if request.args.get("user_id"):
        q = q.filter_by(user_id=int(request.args["user_id"]))
    return jsonify([o.to_dict() for o in q.order_by(Order.created_at.desc())])


@app.patch("/orders/<int:order_id>/status")
def set_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return error("Order not found.", 404)
    order.status = request.get_json(force=True)["status"]
    db.session.commit()
    return jsonify(order.to_dict())


init_db(app)
