"""Pricing service: list prices, discounts and order quotes."""
from flask import request, jsonify

from common import create_service, db, init_db, error

app = create_service("pricing")


class Price(db.Model):
    product_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    price_cents = db.Column(db.Integer, nullable=False)
    discount_pct = db.Column(db.Integer, nullable=False, default=0)

    @property
    def unit_price_cents(self):
        return self.price_cents * (100 - self.discount_pct) // 100

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "list_price_cents": self.price_cents,
            "discount_pct": self.discount_pct,
            "unit_price_cents": self.unit_price_cents,
        }


@app.get("/prices")
def prices():
    ids = [int(i) for i in request.args.get("ids", "").split(",") if i]
    rows = Price.query.filter(Price.product_id.in_(ids)).all() if "ids" in request.args else Price.query.all()
    return jsonify({str(r.product_id): r.to_dict() for r in rows})


@app.put("/prices/<int:product_id>")
def set_price(product_id):
    d = request.get_json(force=True)
    row = db.session.get(Price, product_id) or Price(product_id=product_id, price_cents=0)
    row.price_cents = int(d.get("price_cents", row.price_cents))
    row.discount_pct = int(d.get("discount_pct", row.discount_pct or 0))
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict())


@app.post("/quote")
def quote():
    items = request.get_json(force=True).get("items", [])
    lines, total = [], 0
    for it in items:
        row = db.session.get(Price, int(it["product_id"]))
        if not row:
            return error(f"No price for product {it['product_id']}.", 404)
        qty = int(it["quantity"])
        line = qty * row.unit_price_cents
        total += line
        lines.append({"product_id": row.product_id, "quantity": qty,
                      "unit_price_cents": row.unit_price_cents, "line_cents": line})
    return jsonify(lines=lines, total_cents=total)


def seed():
    if Price.query.first():
        return
    for pid, cents in enumerate([89900, 159900, 64900, 189900, 12900, 5900, 34900, 4500], start=1):
        db.session.add(Price(product_id=pid, price_cents=cents, discount_pct=0))
    db.session.commit()


init_db(app, seed)
