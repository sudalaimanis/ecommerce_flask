"""Product service: catalog (categories and products). Prices live in pricing, stock in inventory."""
from datetime import datetime

from flask import request, jsonify

from common import create_service, db, init_db, error

app = create_service("product")


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {"id": self.id, "slug": self.slug, "name": self.name}


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), default="")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    category = db.relationship("Category")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "image_url": self.image_url,
            "category": self.category.to_dict(),
        }


@app.get("/categories")
def categories():
    return jsonify([c.to_dict() for c in Category.query.order_by(Category.name)])


@app.get("/products")
def products():
    q = Product.query
    if request.args.get("category"):
        q = q.join(Category).filter(Category.slug == request.args["category"])
    if request.args.get("ids"):
        q = q.filter(Product.id.in_([int(i) for i in request.args["ids"].split(",") if i]))
    q = q.order_by(Product.id.desc()) if request.args.get("sort") == "new" else q.order_by(Product.name)
    if request.args.get("limit"):
        q = q.limit(int(request.args["limit"]))
    return jsonify([p.to_dict() for p in q])


@app.get("/products/slug/<slug>")
def product_by_slug(slug):
    p = Product.query.filter_by(slug=slug).first()
    return jsonify(p.to_dict()) if p else error("Product not found.", 404)


@app.get("/categories/<slug>")
def category_by_slug(slug):
    c = Category.query.filter_by(slug=slug).first()
    return jsonify(c.to_dict()) if c else error("Category not found.", 404)


def seed():
    if Category.query.first():
        return
    cats = {s: Category(slug=s, name=n) for s, n in
            [("laptops", "Laptops"), ("desktops", "Desktops & PCs"), ("accessories", "Computer Accessories")]}
    db.session.add_all(cats.values())
    db.session.flush()
    u = "https://images.unsplash.com/"
    # Ids are fixed: pricing and inventory seed their rows by the same product ids.
    rows = [
        (1, "ProBook 14\" Ultrabook", "probook-14-ultrabook",
         "14\" FHD display, 16GB RAM, 512GB NVMe SSD. Ideal for work and light creative tasks.",
         "laptops", "photo-1496181133206-80ce9b88a853"),
        (2, "DevStation 16\" Creator Laptop", "devstation-16-creator",
         "High-color gamut display, 32GB RAM, dedicated GPU. Built for developers and designers.",
         "laptops", "photo-1525547719571-a2d4ac8944e2"),
        (3, "Compact Tower — Office Pro", "compact-tower-office-pro",
         "Small form factor desktop with fast SSD, quiet cooling, and plenty of USB ports.",
         "desktops", "photo-1587831990711-23ca6441447b"),
        (4, "Gaming Rig — Apex", "gaming-rig-apex",
         "RGB case, liquid cooling, latest-gen CPU and GPU. Ready for 1440p gaming.",
         "desktops", "photo-1593640408182-31bd4aa8df37"),
        (5, "Mechanical Keyboard — Tactile", "mechanical-keyboard-tactile",
         "Hot-swappable switches, PBT keycaps, USB-C. Satisfying tactile feedback for coding.",
         "accessories", "photo-1587829741301-dc798b83add3"),
        (6, "Wireless Ergonomic Mouse", "wireless-ergonomic-mouse",
         "Precision sensor, long battery life, comfortable grip for all-day use.",
         "accessories", "photo-1527814050087-3793815479db"),
        (7, "27\" 4K USB-C Monitor", "27-4k-usbc-monitor",
         "IPS panel, 99% sRGB, single-cable laptop docking via USB-C.",
         "accessories", "photo-1527443224154-c4a3942d3acf"),
        (8, "USB-C Hub — 7-in-1", "usb-c-hub-7in1",
         "HDMI, SD, USB-A, pass-through charging. Perfect laptop companion.",
         "accessories", "photo-1625948515291-69613efd103f"),
    ]
    for pid, name, slug, desc, cat, img in rows:
        db.session.add(Product(id=pid, name=name, slug=slug, description=desc,
                               category_id=cats[cat].id, image_url=f"{u}{img}?w=600"))
    db.session.commit()
    # keep the Postgres id sequence ahead of the fixed ids
    if db.engine.dialect.name == "postgresql":
        db.session.execute(db.text("SELECT setval(pg_get_serial_sequence('product','id'), 8)"))
        db.session.commit()


init_db(app, seed)
