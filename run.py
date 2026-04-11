"""Entry point: run with `python run.py` from the ecommerce_flask directory."""
from app import create_app, db
from app.seed import seed_if_empty

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_if_empty()
    app.run(debug=True, host="127.0.0.1", port=5000)
