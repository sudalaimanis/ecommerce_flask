"""Customer service: customer profiles and saved shipping details.

Profiles are created from `user.registered` events and the default shipping
address is remembered from `order.confirmed` events.
"""
from flask import request, jsonify

from common import create_service, db, init_db, error, subscribe

app = create_service("customer")


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), default="")
    shipping_name = db.Column(db.String(120), default="")
    shipping_address = db.Column(db.Text, default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


@app.get("/customers/<int:user_id>")
def get_customer(user_id):
    c = Customer.query.filter_by(user_id=user_id).first()
    return jsonify(c.to_dict()) if c else error("Customer not found.", 404)


@app.put("/customers/<int:user_id>")
def update_customer(user_id):
    c = Customer.query.filter_by(user_id=user_id).first()
    if not c:
        return error("Customer not found.", 404)
    d = request.get_json(force=True)
    for field in ("name", "phone", "shipping_name", "shipping_address"):
        if field in d:
            setattr(c, field, d[field])
    db.session.commit()
    return jsonify(c.to_dict())


def on_user_registered(p):
    if not Customer.query.filter_by(user_id=p["id"]).first():
        db.session.add(Customer(user_id=p["id"], name=p["name"], email=p["email"]))
        db.session.commit()


def on_order_confirmed(p):
    if not p.get("user_id"):
        return
    c = Customer.query.filter_by(user_id=p["user_id"]).first()
    if c:
        c.shipping_name = p["shipping_name"]
        c.shipping_address = p["shipping_address"]
        db.session.commit()


init_db(app)
subscribe(app, {"user.registered": on_user_registered, "order.confirmed": on_order_confirmed})
