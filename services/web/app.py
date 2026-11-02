"""Web service: storefront UI. Talks to the backend microservices over REST."""
import os
import uuid
from functools import wraps
from datetime import datetime

import requests
from flask import (Blueprint, Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)

from common import call

login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message_category = "info"
bp = Blueprint("main", __name__)


class SessionUser(UserMixin):
    """Logged-in user, rebuilt from the signed session cookie (identity lives in user-service)."""

    def __init__(self, data):
        self.id = str(data["id"])
        self.email = data["email"]
        self.name = data["name"]


@login_manager.user_loader
def load_user(user_id):
    data = session.get("user")
    return SessionUser(data) if data and str(data["id"]) == user_id else None


# ------------------------------------------------------------------ data helpers
def _enrich(products):
    """Attach effective price and stock (from pricing + inventory) to product dicts."""
    if not products:
        return products
    ids = ",".join(str(p["id"]) for p in products)
    prices = call("pricing", "GET", "/prices", params={"ids": ids}).json()
    stock = call("inventory", "GET", "/stock", params={"ids": ids}).json()
    for p in products:
        p["price_cents"] = prices.get(str(p["id"]), {}).get("unit_price_cents", 0)
        p["stock"] = stock.get(str(p["id"]), 0)
    return products


def _cart_id():
    return session.setdefault("cart_id", uuid.uuid4().hex)


def _cart_items():
    lines = call("cart", "GET", f"/carts/{_cart_id()}").json()["items"]
    if not lines:
        return [], 0
    products = call("product", "GET", "/products", params={"ids": ",".join(str(l["product_id"]) for l in lines)}).json()
    by_id = {p["id"]: p for p in _enrich(products)}
    items, subtotal = [], 0
    for l in lines:
        p = by_id.get(l["product_id"])
        if not p or p["stock"] < 1:
            continue
        q = min(l["quantity"], p["stock"])
        line = q * p["price_cents"]
        subtotal += line
        items.append({"product": p, "quantity": q, "line_cents": line})
    return items, subtotal


def _safe(service, path, default, **kw):
    """GET json from a service; fall back to `default` if it is down or returns an error."""
    try:
        r = call(service, "GET", path, timeout=4, **kw)
        return r.json() if r.status_code == 200 else default
    except requests.RequestException:
        return default


def _money(cents):
    return f"${cents / 100:,.2f}"


def _with_dates(order):
    order["created_at"] = datetime.fromisoformat(order["created_at"])
    return order


@bp.app_context_processor
def inject_categories():
    try:
        return {"nav_categories": call("product", "GET", "/categories").json()}
    except requests.RequestException:
        return {"nav_categories": []}


# ----------------------------------------------------------------------- catalog
@bp.route("/")
def index():
    featured = call("product", "GET", "/products", params={"sort": "new", "limit": 6}).json()
    return render_template("index.html", featured=_enrich(featured))


@bp.route("/category/<slug>")
def category(slug):
    r = call("product", "GET", f"/categories/{slug}")
    if r.status_code == 404:
        return render_template("base.html"), 404
    products = call("product", "GET", "/products", params={"category": slug}).json()
    return render_template("category.html", category=r.json(), products=_enrich(products))


@bp.route("/product/<slug>")
def product_detail(slug):
    r = call("product", "GET", f"/products/slug/{slug}")
    if r.status_code == 404:
        return render_template("base.html"), 404
    return render_template("product.html", product=_enrich([r.json()])[0])


# -------------------------------------------------------------------------- cart
@bp.route("/cart", methods=["GET", "POST"])
def cart():
    if request.method == "POST":
        action = request.form.get("action")
        pid = request.form.get("product_id", type=int)
        cid = _cart_id()
        if pid and action == "add":
            p = _enrich(call("product", "GET", "/products", params={"ids": pid}).json())
            if p and p[0]["stock"] > 0:
                current = {l["product_id"]: l["quantity"]
                           for l in call("cart", "GET", f"/carts/{cid}").json()["items"]}
                qty = current.get(pid, 0) + request.form.get("quantity", 1, type=int)
                qty = max(1, min(qty, p[0]["stock"]))
                call("cart", "PUT", f"/carts/{cid}/items/{pid}", json={"quantity": qty})
                flash("Added to cart.", "success")
            return redirect(request.referrer or url_for("main.cart"))
        if pid and action == "update":
            q = request.form.get("quantity", 1, type=int)
            p = _enrich(call("product", "GET", "/products", params={"ids": pid}).json())
            if p:
                call("cart", "PUT", f"/carts/{cid}/items/{pid}", json={"quantity": min(q, p[0]["stock"])})
        if pid and action == "remove":
            call("cart", "DELETE", f"/carts/{cid}/items/{pid}")
        return redirect(url_for("main.cart"))

    items, subtotal = _cart_items()
    return render_template("cart.html", items=items, subtotal_cents=subtotal)


# ---------------------------------------------------------------------- accounts
def _start_session(data):
    session["user"] = data["user"]
    session["token"] = data["token"]
    login_user(SessionUser(data["user"]))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        r = call("user", "POST", "/register", json={
            "email": request.form.get("email"), "name": request.form.get("name"),
            "password": request.form.get("password")})
        if r.status_code == 201:
            _start_session(r.json())
            flash("Account created. Welcome!", "success")
            return redirect(url_for("main.index"))
        flash(r.json().get("error", "Registration failed."), "danger")
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        r = call("user", "POST", "/login", json={
            "email": request.form.get("email"), "password": request.form.get("password")})
        if r.status_code == 200:
            _start_session(r.json())
            flash("Logged in.", "success")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("main.index"))
        flash(r.json().get("error", "Invalid email or password."), "danger")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("user", None)
    session.pop("token", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------------------- checkout
@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, subtotal = _cart_items()
    if not items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("main.cart"))

    if request.method == "POST":
        name = (request.form.get("shipping_name") or "").strip()
        address = (request.form.get("shipping_address") or "").strip()
        guest_email = (request.form.get("guest_email") or "").strip().lower()
        if not name or not address:
            flash("Name and shipping address are required.", "danger")
        elif not current_user.is_authenticated and not guest_email:
            flash("Please enter an email for order confirmation, or log in.", "danger")
        else:
            authed = current_user.is_authenticated
            r = call("cart", "POST", f"/carts/{_cart_id()}/checkout", timeout=30, json={
                "user_id": int(current_user.id) if authed else None,
                "email": current_user.email if authed else guest_email,
                "name": current_user.name if authed else name,
                "shipping_name": name, "shipping_address": address})
            if r.status_code == 201:
                flash("Thank you! Your order has been placed.", "success")
                return redirect(url_for("main.order_confirmation", order_id=r.json()["order_id"]))
            flash(r.json().get("error", "Checkout failed."), "danger")
            if r.status_code == 409:
                return redirect(url_for("main.cart"))
    profile = _safe("customer", f"/customers/{current_user.id}", {}) if current_user.is_authenticated else {}
    return render_template("checkout.html", items=items, subtotal_cents=subtotal, profile=profile)


@bp.route("/order/<int:order_id>")
def order_confirmation(order_id):
    r = call("order", "GET", f"/orders/{order_id}")
    if r.status_code == 404:
        return render_template("base.html"), 404
    order = _with_dates(r.json())
    if current_user.is_authenticated:
        if order["user_id"] != int(current_user.id):
            flash("You cannot view this order.", "danger")
            return redirect(url_for("main.index"))
    else:
        flash("Save your order number for your records.", "info")
    order["shipment"] = _safe("logistics", f"/shipments/{order_id}", None)
    order["payments"] = _safe("payment", f"/payments/order/{order_id}", [])
    order["timeline"] = _safe("order-processing", f"/processing/{order_id}", [])
    order["notifications"] = _safe("notification", "/notifications", [], params={"order_id": order_id})
    return render_template("order_confirmation.html", order=order)


@bp.route("/account/orders")
@login_required
def my_orders():
    orders = call("order", "GET", "/orders", params={"user_id": current_user.id}).json()
    return render_template("my_orders.html", orders=[_with_dates(o) for o in orders])


# ----------------------------------------------------------------------- profile
@bp.route("/account/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = int(current_user.id)
    if request.method == "POST":
        r = call("customer", "PUT", f"/customers/{uid}", json={
            f: (request.form.get(f) or "").strip()
            for f in ("name", "phone", "shipping_name", "shipping_address")})
        flash("Profile saved." if r.status_code == 200 else "Could not save profile.",
              "success" if r.status_code == 200 else "danger")
        return redirect(url_for("main.profile"))
    return render_template("profile.html", profile=_safe("customer", f"/customers/{uid}", {}))


# ------------------------------------------------------------------------- admin
SERVICE_NAMES = ["user", "customer", "product", "pricing", "inventory", "cart",
                 "order", "payment", "order-processing", "logistics", "notification"]


def admin_required(view):
    """Logged-in users only; if ADMIN_EMAILS is set, only those emails (unset = any user, for local dev)."""
    @wraps(view)
    @login_required
    def wrapper(*a, **kw):
        allowed = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
        if allowed and current_user.email.lower() not in allowed:
            abort(403)
        return view(*a, **kw)
    return wrapper


def _product_names():
    return {p["id"]: p["name"] for p in _safe("product", "/products", [])}


def _admin_page(section, title, headers, rows):
    return render_template("admin.html", section=section, title=title, headers=headers, rows=rows, health=None)


@bp.route("/admin")
@admin_required
def admin():
    health = []
    for name in SERVICE_NAMES:
        try:
            r = call(name, "GET", "/health", timeout=2)
            health.append((name + "-service", "UP" if r.status_code == 200 else f"ERROR {r.status_code}"))
        except requests.RequestException:
            health.append((name + "-service", "DOWN"))
    return render_template("admin.html", section="services", title="Services", headers=["Service", "Status"],
                           rows=health, health=True)


@bp.route("/admin/inventory")
@admin_required
def admin_inventory():
    names, stock = _product_names(), _safe("inventory", "/stock", {})
    rows = [(pid, names.get(int(pid), "?"), qty) for pid, qty in sorted(stock.items(), key=lambda kv: int(kv[0]))]
    return _admin_page("inventory", "Inventory", ["Product ID", "Product", "In stock"], rows)


@bp.route("/admin/pricing")
@admin_required
def admin_pricing():
    names, prices = _product_names(), _safe("pricing", "/prices", {})
    rows = [(pid, names.get(int(pid), "?"), _money(p["list_price_cents"]), f"{p['discount_pct']}%",
             _money(p["unit_price_cents"])) for pid, p in sorted(prices.items(), key=lambda kv: int(kv[0]))]
    return _admin_page("pricing", "Pricing", ["Product ID", "Product", "List price", "Discount", "Selling price"], rows)


@bp.route("/admin/payments")
@admin_required
def admin_payments():
    rows = [(p["id"], f"#{p['order_id']}", _money(p["amount_cents"]), p["status"], p["created_at"][:19].replace("T", " "))
            for p in _safe("payment", "/payments", [])]
    return _admin_page("payments", "Payments", ["Payment", "Order", "Amount", "Status", "Created (UTC)"], rows)


@bp.route("/admin/shipments")
@admin_required
def admin_shipments():
    rows = [(f"#{s['order_id']}", s["carrier"], s["tracking_number"], s["status"], s["eta"], s["shipping_name"])
            for s in _safe("logistics", "/shipments", [])]
    return _admin_page("shipments", "Shipments", ["Order", "Carrier", "Tracking", "Status", "ETA", "Ship to"], rows)


@bp.route("/admin/notifications")
@admin_required
def admin_notifications():
    rows = [(f"#{n['order_id']}", n["event"], n["to_email"] or "-", n["subject"], n["status"],
             n["created_at"][:19].replace("T", " ")) for n in _safe("notification", "/notifications", [])]
    return _admin_page("notifications", "Notifications (emails)",
                       ["Order", "Event", "To", "Subject", "Delivery", "Created (UTC)"], rows)


# --------------------------------------------------------------------------- app
def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    login_manager.init_app(app)
    app.register_blueprint(bp)

    @app.errorhandler(requests.RequestException)
    def backend_down(_):
        return "A backend service is temporarily unavailable. Please try again shortly.", 503

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "web"}

    return app


app = create_app()
