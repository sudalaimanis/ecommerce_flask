"""Cart/checkout service: stores carts and orchestrates checkout.

Checkout steps: quote (pricing) -> reserve stock (inventory) -> create order (order)
-> take payment (payment). Any failure rolls back the earlier steps.
"""
import uuid

import requests
from flask import request, jsonify

from common import create_service, db, init_db, error, call

app = create_service("cart")


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.String(64), nullable=False, index=True)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint("cart_id", "product_id"),)


def _items(cart_id):
    return [{"product_id": i.product_id, "quantity": i.quantity}
            for i in CartItem.query.filter_by(cart_id=cart_id).order_by(CartItem.id)]


@app.get("/carts/<cart_id>")
def get_cart(cart_id):
    return jsonify(cart_id=cart_id, items=_items(cart_id))


@app.put("/carts/<cart_id>/items/<int:product_id>")
def set_item(cart_id, product_id):
    """Set the absolute quantity of a line (<= 0 removes it)."""
    qty = int(request.get_json(force=True).get("quantity", 0))
    item = CartItem.query.filter_by(cart_id=cart_id, product_id=product_id).first()
    if qty < 1:
        if item:
            db.session.delete(item)
    elif item:
        item.quantity = qty
    else:
        db.session.add(CartItem(cart_id=cart_id, product_id=product_id, quantity=qty))
    db.session.commit()
    return jsonify(cart_id=cart_id, items=_items(cart_id))


@app.delete("/carts/<cart_id>/items/<int:product_id>")
def remove_item(cart_id, product_id):
    CartItem.query.filter_by(cart_id=cart_id, product_id=product_id).delete()
    db.session.commit()
    return jsonify(cart_id=cart_id, items=_items(cart_id))


def _rollback(ref, order_id=None, reason="checkout failed"):
    try:
        call("inventory", "POST", "/release", json={"ref": ref})
        if order_id:
            call("order", "PATCH", f"/orders/{order_id}/status", json={"status": "CANCELLED", "reason": reason})
    except requests.RequestException:
        app.logger.exception("rollback failed for %s", ref)


@app.post("/carts/<cart_id>/checkout")
def checkout(cart_id):
    d = request.get_json(force=True)
    lines = _items(cart_id)
    if not lines:
        return error("Your cart is empty.", 400)

    try:
        q = call("pricing", "POST", "/quote", json={"items": lines})
        if q.status_code != 200:
            return error("Could not price your cart.", 502)
        quote = q.json()

        names = {p["id"]: p["name"] for p in call(
            "product", "GET", "/products", params={"ids": ",".join(str(i["product_id"]) for i in lines)}).json()}

        ref = uuid.uuid4().hex
        r = call("inventory", "POST", "/reserve", json={"ref": ref, "items": lines})
        if r.status_code == 409:
            pid = r.json().get("product_id")
            return error(f"Not enough stock for {names.get(pid, 'an item')}. Please update your cart.", 409)
        if r.status_code >= 400:
            return error("Inventory unavailable.", 502)
    except requests.RequestException:
        return error("A required service is unavailable. Please try again.", 503)

    order_id = None
    try:
        o = call("order", "POST", "/orders", json={
            "user_id": d.get("user_id"),
            "email": d.get("email"),
            "name": d.get("name"),
            "shipping_name": d["shipping_name"],
            "shipping_address": d["shipping_address"],
            "total_cents": quote["total_cents"],
            "reservation_ref": ref,
            "items": [{**ln, "product_name": names.get(ln["product_id"], "")} for ln in quote["lines"]],
        })
        if o.status_code != 201:
            raise RuntimeError(f"order service returned {o.status_code}")
        order_id = o.json()["id"]

        p = call("payment", "POST", "/payments", json={"order_id": order_id, "amount_cents": quote["total_cents"]})
        if p.status_code != 201 or p.json().get("status") != "approved":
            _rollback(ref, order_id, "payment declined")
            return error("Payment was declined.", 402)
    except (requests.RequestException, RuntimeError):
        app.logger.exception("checkout failed")
        _rollback(ref, order_id)
        return error("Checkout failed. Please try again.", 502)

    CartItem.query.filter_by(cart_id=cart_id).delete()
    db.session.commit()
    return jsonify(order_id=order_id, total_cents=quote["total_cents"]), 201


init_db(app)
