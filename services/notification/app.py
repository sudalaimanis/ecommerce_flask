"""Notification service: turns events into customer emails.

Every notification is stored. If SMTP_USER / SMTP_PASSWORD are not set the email is
only recorded (status "skipped"), so email delivery can be configured later without code changes.
"""
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from flask import request, jsonify

from common import create_service, db, init_db, subscribe

app = create_service("notification")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True)
    event = db.Column(db.String(40), nullable=False)
    to_email = db.Column(db.String(120))
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {c.name: (getattr(self, c.name).isoformat() if c.name == "created_at" else getattr(self, c.name))
                for c in self.__table__.columns}


def _money(cents):
    return f"${cents / 100:,.2f}"


def _send_email(to_email, subject, body):
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not (user and password):
        return "skipped (SMTP not configured)"
    if not to_email:
        return "skipped (no recipient)"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ.get("MAIL_FROM", user), to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587")),
                          timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return "sent"
    except Exception:
        app.logger.exception("email to %s failed", to_email)
        return "failed"


def _notify(event, order_id, to_email, subject, body):
    status = _send_email(to_email, subject, body)
    db.session.add(Notification(order_id=order_id, event=event, to_email=to_email,
                                subject=subject, body=body, status=status))
    db.session.commit()
    app.logger.info("notification %s for order %s -> %s: %s", event, order_id, to_email, status)


def on_order_confirmed(o):
    lines = [f"Hi {o.get('name') or o['shipping_name']},", "",
             f"Thank you! Your order #{o['order_id']} has been placed.", "", "Items:"]
    for it in o["items"]:
        lines.append(f"  - {it['product']['name']} x {it['quantity']} @ {_money(it['unit_price_cents'])} "
                     f"= {_money(it['quantity'] * it['unit_price_cents'])}")
    lines += ["", f"Total: {_money(o['total_cents'])}", "", "Shipping to:",
              f"  {o['shipping_name']}", f"  {o['shipping_address']}", "", "Thanks for shopping with us!"]
    _notify("order.confirmed", o["order_id"], o.get("email"), f"Order #{o['order_id']} confirmed", "\n".join(lines))


def on_shipment_created(s):
    body = (f"Hi {s.get('name') or s['shipping_name']},\n\n"
            f"Good news - your order #{s['order_id']} has shipped with {s['carrier']}.\n"
            f"Tracking number: {s['tracking_number']}\nEstimated delivery: {s['eta']}\n")
    _notify("shipment.created", s["order_id"], s.get("email"), f"Order #{s['order_id']} has shipped", body)


@app.get("/notifications")
def list_notifications():
    q = Notification.query
    if request.args.get("order_id"):
        q = q.filter_by(order_id=int(request.args["order_id"]))
    return jsonify([n.to_dict() for n in q.order_by(Notification.id.desc()).limit(100)])


init_db(app)
subscribe(app, {"order.confirmed": on_order_confirmed, "shipment.created": on_shipment_created})
