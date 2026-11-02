"""User service: credentials and authentication (issues JWTs)."""
from datetime import datetime

from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from common import create_service, db, init_db, error, publish, make_token, decode_token

app = create_service("user")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def public(self):
        return {"id": self.id, "email": self.email, "name": self.name}


def _auth_response(user, status=200):
    token = make_token({"sub": str(user.id), "email": user.email, "name": user.name})
    return jsonify(user=user.public(), token=token), status


@app.post("/register")
def register():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip().lower()
    name = (d.get("name") or "").strip()
    password = d.get("password") or ""
    if not email or not name or len(password) < 6:
        return error("Please fill all fields; password at least 6 characters.")
    if User.query.filter_by(email=email).first():
        return error("That email is already registered.", 409)
    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    publish("user.registered", user.public())
    return _auth_response(user, 201)


@app.post("/login")
def login():
    d = request.get_json(force=True)
    user = User.query.filter_by(email=(d.get("email") or "").strip().lower()).first()
    if not user or not check_password_hash(user.password_hash, d.get("password") or ""):
        return error("Invalid email or password.", 401)
    return _auth_response(user)


@app.get("/users")
def list_users():
    """Internal: id, email, name and signup date only - never password hashes."""
    users = User.query.order_by(User.id).all()
    return jsonify(count=len(users), users=[{**u.public(), "created_at": u.created_at.isoformat()} for u in users])


@app.get("/me")
def me():
    claims = decode_token(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    if not claims:
        return error("Invalid or expired token.", 401)
    user = db.session.get(User, int(claims["sub"]))
    return jsonify(user.public()) if user else error("User not found.", 404)


init_db(app)
