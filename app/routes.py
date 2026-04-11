from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Category, Product, Order, OrderItem

bp = Blueprint("main", __name__)


def _cart():
    return session.setdefault("cart", {})


def _cart_items():
    cart = _cart()
    items = []
    subtotal = 0
    for pid_str, qty in list(cart.items()):
        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            continue
        p = Product.query.get(pid)
        if not p or p.stock < 1:
            continue
        q = min(int(qty), p.stock)
        if q < 1:
            continue
        line = q * p.price_cents
        subtotal += line
        items.append({"product": p, "quantity": q, "line_cents": line})
    return items, subtotal


@bp.app_context_processor
def inject_categories():
    return {"nav_categories": Category.query.order_by(Category.name).all()}


@bp.route("/")
def index():
    featured = Product.query.order_by(Product.created_at.desc()).limit(6).all()
    return render_template("index.html", featured=featured)


@bp.route("/category/<slug>")
def category(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    products = Product.query.filter_by(category_id=cat.id).order_by(Product.name).all()
    return render_template("category.html", category=cat, products=products)


@bp.route("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    return render_template("product.html", product=product)


@bp.route("/cart", methods=["GET", "POST"])
def cart():
    if request.method == "POST":
        action = request.form.get("action")
        pid = request.form.get("product_id")
        cart_dict = _cart()
        if action == "add" and pid:
            p = Product.query.get(int(pid))
            if p and p.stock > 0:
                cur = int(cart_dict.get(str(p.id), 0))
                new_qty = cur + int(request.form.get("quantity", 1))
                new_qty = max(1, min(new_qty, p.stock))
                cart_dict[str(p.id)] = new_qty
                session.modified = True
                flash("Added to cart.", "success")
            return redirect(request.referrer or url_for("main.cart"))
        if action == "update" and pid:
            q = int(request.form.get("quantity", 1))
            p = Product.query.get(int(pid))
            if p:
                if q < 1:
                    cart_dict.pop(str(pid), None)
                else:
                    cart_dict[str(pid)] = min(q, p.stock)
                session.modified = True
        if action == "remove" and pid:
            cart_dict.pop(str(pid), None)
            session.modified = True
        return redirect(url_for("main.cart"))

    items, subtotal = _cart_items()
    return render_template("cart.html", items=items, subtotal_cents=subtotal)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()
        password = request.form.get("password") or ""
        if not email or not name or len(password) < 6:
            flash("Please fill all fields; password at least 6 characters.", "danger")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
            return render_template("register.html")
        u = User(email=email, name=name)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        login_user(u)
        flash("Account created. Welcome!", "success")
        return redirect(url_for("main.index"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash("Logged in.", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("main.index"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


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
            return render_template(
                "checkout.html",
                items=items,
                subtotal_cents=subtotal,
            )
        if not current_user.is_authenticated and not guest_email:
            flash("Please enter an email for order confirmation, or log in.", "danger")
            return render_template(
                "checkout.html",
                items=items,
                subtotal_cents=subtotal,
            )

        order = Order(
            user_id=current_user.id if current_user.is_authenticated else None,
            guest_email=None if current_user.is_authenticated else guest_email,
            shipping_name=name,
            shipping_address=address,
            total_cents=subtotal,
        )
        db.session.add(order)
        db.session.flush()

        for row in items:
            p = row["product"]
            q = row["quantity"]
            if p.stock < q:
                db.session.rollback()
                flash(f"Not enough stock for {p.name}. Please update your cart.", "danger")
                return redirect(url_for("main.cart"))
            p.stock -= q
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=p.id,
                    quantity=q,
                    unit_price_cents=p.price_cents,
                )
            )
        db.session.commit()
        session["cart"] = {}
        session.modified = True
        flash("Thank you! Your order has been placed.", "success")
        return redirect(url_for("main.order_confirmation", order_id=order.id))

    return render_template(
        "checkout.html",
        items=items,
        subtotal_cents=subtotal,
    )


@bp.route("/order/<int:order_id>")
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    if current_user.is_authenticated:
        if order.user_id != current_user.id:
            flash("You cannot view this order.", "danger")
            return redirect(url_for("main.index"))
    else:
        flash("Save your order number for your records.", "info")
    return render_template("order_confirmation.html", order=order)


@bp.route("/account/orders")
@login_required
def my_orders():
    orders = (
        Order.query.filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("my_orders.html", orders=orders)
