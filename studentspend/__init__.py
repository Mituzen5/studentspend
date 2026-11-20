import csv
import io
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import date, timedelta
from functools import wraps

from flask import Flask, Response, abort, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from .finance import CATEGORY_NAMES, build_dashboard, ensure_months, month_add, user_json
from .models import CategoryLimit, ChallengeDay, Goal, Month, Transaction, User, db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_AMOUNT = 10_000_000


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def create_app(config=None):
    app = Flask(__name__, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")
    db_url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(ROOT, "instance", "studentspend.db"))
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        os.makedirs(os.path.join(ROOT, "instance"), exist_ok=True)
        key_file = os.path.join(ROOT, "instance", "secret_key")
        if not os.path.exists(key_file):
            with open(key_file, "w") as f:
                f.write(secrets.token_hex(32))
        secret = open(key_file).read().strip()
    app.config.update(
        SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        os.makedirs(os.path.dirname(app.config["SQLALCHEMY_DATABASE_URI"][10:]) or ".", exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    login_attempts = defaultdict(deque)

    # ------------------------------------------------------------ helpers
    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError("Invalid request body.")
        return data

    def client_today():
        """Use the browser's local date (so rollover happens at the student's midnight)."""
        raw = request.headers.get("X-Client-Date", "")
        server = date.today()
        try:
            d = date.fromisoformat(raw)
            if abs((d - server).days) <= 1:
                return d
        except ValueError:
            pass
        return server

    def parse_amount(v, allow_zero=False):
        try:
            n = round(float(v), 2)
        except (TypeError, ValueError):
            raise ApiError("Enter a valid amount.")
        if n != n or n < 0 or (n == 0 and not allow_zero) or n > MAX_AMOUNT:
            raise ApiError("Enter a valid amount.")
        return n

    def parse_date(v, today, field="date"):
        try:
            d = date.fromisoformat(str(v))
        except ValueError:
            raise ApiError(f"Enter a valid {field}.")
        if d > today:
            raise ApiError("Dates in the future are not allowed.")
        if d < today - timedelta(days=730):
            raise ApiError("Dates older than two years are not allowed.")
        return d

    def clean_text(v, maxlen, field, required=False):
        s = str(v or "").strip()
        if required and not s:
            raise ApiError(f"Please enter {field}.")
        if len(s) > maxlen:
            raise ApiError(f"{field.capitalize()} must be at most {maxlen} characters.")
        return s

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            uid = session.get("uid")
            user = db.session.get(User, uid) if uid else None
            if not user or session.get("sv") != user.session_version:
                session.pop("uid", None)
                raise ApiError("Please log in.", 401)
            g.user = user
            return fn(*a, **kw)
        return wrapper

    def start_session(user):
        csrf = session.get("csrf") or secrets.token_urlsafe(32)
        session.clear()
        session.permanent = True
        session["uid"], session["sv"], session["csrf"] = user.id, user.session_version, csrf

    def dashboard_payload(month=None):
        today = client_today()
        return build_dashboard(g.user, month or request.args.get("month") or today.strftime("%Y-%m"), today)

    def throttle_key():
        return (request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),)

    def check_throttle(key):
        q, now = login_attempts[key], time.time()
        while q and now - q[0] > 900:
            q.popleft()
        if len(q) >= app.config.get("LOGIN_MAX_ATTEMPTS", 8):
            raise ApiError("Too many attempts. Please wait a few minutes and try again.", 429)

    # ------------------------------------------------------------ hooks
    @app.before_request
    def csrf_protect():
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            token = session.get("csrf")
            if not token or not secrets.compare_digest(token, request.headers.get("X-CSRF-Token", "")):
                return jsonify(error="Your session expired. Please refresh the page."), 403

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error="Request too large."), 413

    # ------------------------------------------------------------ pages
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/healthz")
    def health():
        return {"ok": True}

    # ------------------------------------------------------------ auth
    @app.get("/api/session")
    def get_session():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        uid = session.get("uid")
        user = db.session.get(User, uid) if uid else None
        ok = bool(user and session.get("sv") == user.session_version)
        return jsonify(csrf=session["csrf"], authenticated=ok, user=user_json(user) if ok else None)

    @app.post("/api/register")
    def register():
        data = body()
        check_throttle(throttle_key() + ("register",))
        username = str(data.get("username", "")).strip().lower()
        password = str(data.get("password", ""))
        name = clean_text(data.get("name"), 60, "your name") or username
        if not USERNAME_RE.match(username):
            raise ApiError("Student ID must be 3–30 characters: letters, numbers, dot, dash or underscore.")
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ApiError("Password must be at least 8 characters and include a letter and a number.")
        if len(password) > 128:
            raise ApiError("Password is too long.")
        allowance = parse_amount(data.get("allowance", 0), allow_zero=True)
        if User.query.filter_by(username=username).first():
            login_attempts[throttle_key() + ("register",)].append(time.time())
            raise ApiError("That student ID is already registered.", 409)
        user = User(username=username, name=name, password_hash=generate_password_hash(password),
                    default_allowance=allowance)
        db.session.add(user)
        db.session.commit()
        ensure_months(user, client_today().strftime("%Y-%m"))
        start_session(user)
        return jsonify(user=user_json(user), csrf=session["csrf"]), 201

    @app.post("/api/login")
    def login():
        data = body()
        username = str(data.get("username", "")).strip().lower()
        key = throttle_key() + (username,)
        check_throttle(key)
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, str(data.get("password", ""))):
            login_attempts[key].append(time.time())
            raise ApiError("Student ID or password is incorrect.", 401)
        login_attempts.pop(key, None)
        start_session(user)
        return jsonify(user=user_json(user), csrf=session["csrf"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        session["csrf"] = secrets.token_urlsafe(32)
        return jsonify(ok=True, csrf=session["csrf"])

    # ------------------------------------------------------------ dashboard
    @app.get("/api/dashboard")
    @login_required
    def dashboard():
        m = request.args.get("month")
        if m and not MONTH_RE.match(m):
            raise ApiError("Invalid month.")
        return jsonify(dashboard_payload(m))

    # ------------------------------------------------------------ transactions
    def tx_from_body(data, today, existing=None):
        kind = data.get("type", existing.kind if existing else None)
        if kind not in ("expense", "saving"):
            raise ApiError("Invalid entry type.")
        amount = parse_amount(data.get("amount"))
        d = parse_date(data.get("date"), today)
        note = clean_text(data.get("note"), 120, "note")
        goal_id = None
        if kind == "expense":
            category = data.get("category")
            if category not in CATEGORY_NAMES:
                raise ApiError("Choose a valid category.")
        else:
            category = "Savings"
            if data.get("goalId") not in (None, "", 0):
                try:
                    goal = Goal.query.filter_by(id=int(data["goalId"]), user_id=g.user.id).first()
                except (TypeError, ValueError):
                    goal = None
                if not goal:
                    raise ApiError("That savings goal no longer exists.")
                goal_id = goal.id
        return dict(kind=kind, amount=amount, date=d.isoformat(), month=d.strftime("%Y-%m"), note=note,
                    category=category, goal_id=goal_id)

    @app.post("/api/transactions")
    @login_required
    def add_tx():
        today = client_today()
        fields = tx_from_body(body(), today)
        t = Transaction(user_id=g.user.id, **fields)
        db.session.add(t)
        db.session.commit()
        ensure_months(g.user, fields["month"])
        return jsonify(dashboard_payload(fields["month"])), 201

    @app.put("/api/transactions/<int:tid>")
    @login_required
    def edit_tx(tid):
        t = Transaction.query.filter_by(id=tid, user_id=g.user.id).first_or_404()
        fields = tx_from_body(body(), client_today(), existing=t)
        for k, v in fields.items():
            setattr(t, k, v)
        db.session.commit()
        ensure_months(g.user, fields["month"])
        return jsonify(dashboard_payload(fields["month"]))

    @app.delete("/api/transactions/<int:tid>")
    @login_required
    def delete_tx(tid):
        t = Transaction.query.filter_by(id=tid, user_id=g.user.id).first_or_404()
        month = t.month
        db.session.delete(t)
        db.session.commit()
        return jsonify(dashboard_payload(month))

    # ------------------------------------------------------------ months / allowance
    @app.put("/api/months/<month>")
    @login_required
    def set_allowance(month):
        if not MONTH_RE.match(month):
            raise ApiError("Invalid month.")
        today = client_today()
        cur = today.strftime("%Y-%m")
        if month > cur:
            raise ApiError("You can't edit a future month.")
        data = body()
        allowance = parse_amount(data.get("allowance"), allow_zero=True)
        ensure_months(g.user, month)
        m = Month.query.filter_by(user_id=g.user.id, month=month).first()
        m.allowance = allowance
        if month == cur or data.get("makeDefault"):
            g.user.default_allowance = allowance
        db.session.commit()
        return jsonify(dashboard_payload(month))

    # ------------------------------------------------------------ goals
    def goal_fields(data, today, current_deadline=None):
        name = clean_text(data.get("name"), 60, "a goal name", required=True)
        emoji = clean_text(data.get("emoji") or "🎯", 8, "emoji")
        target = parse_amount(data.get("target"))
        deadline = data.get("deadline") or None
        if deadline:
            try:
                dl = date.fromisoformat(deadline)
            except ValueError:
                raise ApiError("Enter a valid deadline.")
            if dl <= today and dl.isoformat() != current_deadline:
                raise ApiError("The deadline must be in the future.")
            deadline = dl.isoformat()
        return dict(name=name, emoji=emoji, target=target, deadline=deadline)

    @app.post("/api/goals")
    @login_required
    def add_goal():
        if g.user.goals.count() >= 30:
            raise ApiError("You can have up to 30 goals.")
        goal = Goal(user_id=g.user.id, **goal_fields(body(), client_today()))
        db.session.add(goal)
        db.session.commit()
        return jsonify(dashboard_payload()), 201

    @app.put("/api/goals/<int:gid>")
    @login_required
    def edit_goal(gid):
        goal = Goal.query.filter_by(id=gid, user_id=g.user.id).first_or_404()
        for k, v in goal_fields(body(), client_today(), goal.deadline).items():
            setattr(goal, k, v)
        db.session.commit()
        return jsonify(dashboard_payload())

    @app.delete("/api/goals/<int:gid>")
    @login_required
    def delete_goal(gid):
        goal = Goal.query.filter_by(id=gid, user_id=g.user.id).first_or_404()
        Transaction.query.filter_by(goal_id=goal.id, user_id=g.user.id).update({"goal_id": None})
        db.session.delete(goal)
        db.session.commit()
        return jsonify(dashboard_payload())

    # ------------------------------------------------------------ challenge
    @app.post("/api/challenge")
    @login_required
    def challenge():
        today = client_today().isoformat()
        if not ChallengeDay.query.filter_by(user_id=g.user.id, date=today).first():
            db.session.add(ChallengeDay(user_id=g.user.id, date=today))
            db.session.commit()
        return jsonify(dashboard_payload())

    # ------------------------------------------------------------ settings
    @app.put("/api/limits")
    @login_required
    def set_limits():
        data = body()
        limits = data.get("limits")
        if not isinstance(limits, dict):
            raise ApiError("Invalid limits.")
        for cat, val in limits.items():
            if cat not in CATEGORY_NAMES:
                raise ApiError("Unknown category.")
            row = CategoryLimit.query.filter_by(user_id=g.user.id, category=cat).first()
            if val in (None, "", 0, "0"):
                if row:
                    db.session.delete(row)
                continue
            n = parse_amount(val)
            if row:
                row.limit = n
            else:
                db.session.add(CategoryLimit(user_id=g.user.id, category=cat, limit=n))
        db.session.commit()
        return jsonify(dashboard_payload(data.get("month") if MONTH_RE.match(str(data.get("month", ""))) else None))

    @app.put("/api/profile")
    @login_required
    def profile():
        data = body()
        g.user.name = clean_text(data.get("name"), 60, "your name", required=True)
        db.session.commit()
        return jsonify(user=user_json(g.user))

    @app.post("/api/password")
    @login_required
    def change_password():
        data = body()
        if not check_password_hash(g.user.password_hash, str(data.get("current", ""))):
            raise ApiError("Your current password is incorrect.", 403)
        new = str(data.get("new", ""))
        if len(new) < 8 or len(new) > 128 or not re.search(r"[A-Za-z]", new) or not re.search(r"\d", new):
            raise ApiError("New password must be at least 8 characters and include a letter and a number.")
        g.user.password_hash = generate_password_hash(new)
        g.user.session_version += 1
        db.session.commit()
        start_session(g.user)
        return jsonify(ok=True, csrf=session["csrf"])

    @app.delete("/api/account")
    @login_required
    def delete_account():
        data = body()
        if not check_password_hash(g.user.password_hash, str(data.get("password", ""))):
            raise ApiError("Password is incorrect.", 403)
        db.session.delete(g.user)
        db.session.commit()
        session.clear()
        return jsonify(ok=True)

    # ------------------------------------------------------------ export
    @app.get("/api/export.csv")
    @login_required
    def export_csv():
        month = request.args.get("month", "")
        q = g.user.transactions
        if month != "all":
            if not MONTH_RE.match(month):
                raise ApiError("Invalid month.")
            q = q.filter_by(month=month)
        goals = {x.id: x.name for x in g.user.goals.all()}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Description", "Category", "Type", "Amount", "Goal"])
        for t in q.order_by(Transaction.date, Transaction.id).all():
            note = t.note
            if note[:1] in ("=", "+", "-", "@"):
                note = "'" + note
            w.writerow([t.date, note, t.category, "Expense" if t.kind == "expense" else "Saving", f"{t.amount:.2f}",
                        goals.get(t.goal_id, "")])
        name = f"StudentSpend-{month}.csv"
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return app
