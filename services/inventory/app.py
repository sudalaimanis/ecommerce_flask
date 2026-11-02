"""Inventory service: stock levels with atomic, idempotent reserve/release."""
from flask import request, jsonify

from common import create_service, db, init_db, error

app = create_service("inventory")


class Stock(db.Model):
    product_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(64), nullable=False, index=True)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    released = db.Column(db.Boolean, nullable=False, default=False)


@app.get("/stock")
def stock():
    ids = [int(i) for i in request.args.get("ids", "").split(",") if i]
    rows = Stock.query.filter(Stock.product_id.in_(ids)).all() if "ids" in request.args else Stock.query.all()
    return jsonify({str(r.product_id): r.quantity for r in rows})


@app.put("/stock/<int:product_id>")
def set_stock(product_id):
    row = db.session.get(Stock, product_id) or Stock(product_id=product_id)
    row.quantity = int(request.get_json(force=True)["quantity"])
    db.session.add(row)
    db.session.commit()
    return jsonify(product_id=product_id, quantity=row.quantity)


@app.post("/reserve")
def reserve():
    """All-or-nothing: either every line is reserved or none is."""
    d = request.get_json(force=True)
    ref, items = d["ref"], d["items"]
    if Reservation.query.filter_by(ref=ref).first():
        return jsonify(ref=ref, status="already_reserved")
    try:
        for it in items:
            pid, qty = int(it["product_id"]), int(it["quantity"])
            updated = Stock.query.filter(Stock.product_id == pid, Stock.quantity >= qty).update(
                {Stock.quantity: Stock.quantity - qty}, synchronize_session=False)
            if not updated:
                db.session.rollback()
                return error("Not enough stock.", 409, product_id=pid)
            db.session.add(Reservation(ref=ref, product_id=pid, quantity=qty))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify(ref=ref, status="reserved"), 201


@app.post("/release")
def release():
    ref = request.get_json(force=True)["ref"]
    rows = Reservation.query.filter_by(ref=ref, released=False).all()
    for r in rows:
        Stock.query.filter_by(product_id=r.product_id).update({Stock.quantity: Stock.quantity + r.quantity})
        r.released = True
    db.session.commit()
    return jsonify(ref=ref, released=len(rows))


def seed():
    if Stock.query.first():
        return
    for pid, qty in enumerate([12, 6, 15, 4, 40, 60, 20, 100], start=1):
        db.session.add(Stock(product_id=pid, quantity=qty))
    db.session.commit()


init_db(app, seed)
