from app import db
from app.models import Category, Product


def seed_if_empty():
    if Category.query.first():
        return

    cats = [
        ("laptops", "Laptops"),
        ("desktops", "Desktops & PCs"),
        ("accessories", "Computer Accessories"),
    ]
    for slug, name in cats:
        db.session.add(Category(slug=slug, name=name))
    db.session.commit()

    laptop = Category.query.filter_by(slug="laptops").first()
    desktop = Category.query.filter_by(slug="desktops").first()
    acc = Category.query.filter_by(slug="accessories").first()

    products = [
        {
            "name": "ProBook 14\" Ultrabook",
            "slug": "probook-14-ultrabook",
            "description": "14\" FHD display, 16GB RAM, 512GB NVMe SSD. Ideal for work and light creative tasks.",
            "price_cents": 89900,
            "stock": 12,
            "category_id": laptop.id,
            "image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600",
        },
        {
            "name": "DevStation 16\" Creator Laptop",
            "slug": "devstation-16-creator",
            "description": "High-color gamut display, 32GB RAM, dedicated GPU. Built for developers and designers.",
            "price_cents": 159900,
            "stock": 6,
            "category_id": laptop.id,
            "image_url": "https://images.unsplash.com/photo-1525547719571-a2d4ac8944e2?w=600",
        },
        {
            "name": "Compact Tower — Office Pro",
            "slug": "compact-tower-office-pro",
            "description": "Small form factor desktop with fast SSD, quiet cooling, and plenty of USB ports.",
            "price_cents": 64900,
            "stock": 15,
            "category_id": desktop.id,
            "image_url": "https://images.unsplash.com/photo-1587831990711-23ca6441447b?w=600",
        },
        {
            "name": "Gaming Rig — Apex",
            "slug": "gaming-rig-apex",
            "description": "RGB case, liquid cooling, latest-gen CPU and GPU. Ready for 1440p gaming.",
            "price_cents": 189900,
            "stock": 4,
            "category_id": desktop.id,
            "image_url": "https://images.unsplash.com/photo-1593640408182-31bd4aa8df37?w=600",
        },
        {
            "name": "Mechanical Keyboard — Tactile",
            "slug": "mechanical-keyboard-tactile",
            "description": "Hot-swappable switches, PBT keycaps, USB-C. Satisfying tactile feedback for coding.",
            "price_cents": 12900,
            "stock": 40,
            "category_id": acc.id,
            "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600",
        },
        {
            "name": "Wireless Ergonomic Mouse",
            "slug": "wireless-ergonomic-mouse",
            "description": "Precision sensor, long battery life, comfortable grip for all-day use.",
            "price_cents": 5900,
            "stock": 60,
            "category_id": acc.id,
            "image_url": "https://images.unsplash.com/photo-1527814050087-3793815479db?w=600",
        },
        {
            "name": "27\" 4K USB-C Monitor",
            "slug": "27-4k-usbc-monitor",
            "description": "IPS panel, 99% sRGB, single-cable laptop docking via USB-C.",
            "price_cents": 34900,
            "stock": 20,
            "category_id": acc.id,
            "image_url": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=600",
        },
        {
            "name": "USB-C Hub — 7-in-1",
            "slug": "usb-c-hub-7in1",
            "description": "HDMI, SD, USB-A, pass-through charging. Perfect laptop companion.",
            "price_cents": 4500,
            "stock": 100,
            "category_id": acc.id,
            "image_url": "https://images.unsplash.com/photo-1625948515291-69613efd103f?w=600",
        },
    ]
    for p in products:
        db.session.add(Product(**p))
    db.session.commit()
