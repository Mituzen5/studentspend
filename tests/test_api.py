from datetime import date

import pytest

from studentspend import create_app
from studentspend.finance import month_add
from studentspend.models import Month, User, db


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db", "SECRET_KEY": "test"})
    yield app


class Client:
    def __init__(self, app, today=None):
        self.c = app.test_client()
        self.today = today or date.today().isoformat()
        self.csrf = self.c.get("/api/session").get_json()["csrf"]

    def h(self):
        return {"X-CSRF-Token": self.csrf, "X-Client-Date": self.today}

    def get(self, url):
        return self.c.get(url, headers=self.h())

    def send(self, method, url, json=None):
        r = getattr(self.c, method)(url, json=json if json is not None else {}, headers=self.h())
        data = r.get_json(silent=True) or {}
        if "csrf" in data:
            self.csrf = data["csrf"]
        return r


def register(app, username="alex23", password="secret123", allowance=5000):
    c = Client(app)
    r = c.send("post", "/api/register", {"username": username, "password": password, "name": "Alex", "allowance": allowance})
    assert r.status_code == 201, r.get_json()
    return c


def test_register_login_logout(app):
    c = register(app)
    assert c.get("/api/dashboard").status_code == 200
    with app.app_context():
        u = User.query.filter_by(username="alex23").first()
        assert u.password_hash != "secret123" and "secret123" not in u.password_hash
    c.send("post", "/api/logout")
    assert c.get("/api/dashboard").status_code == 401
    assert c.send("post", "/api/login", {"username": "alex23", "password": "wrongpass1"}).status_code == 401
    assert c.send("post", "/api/login", {"username": "ALEX23", "password": "secret123"}).status_code == 200
    assert c.get("/api/dashboard").status_code == 200


def test_validation_and_duplicates(app):
    register(app)
    c = Client(app)
    assert c.send("post", "/api/register", {"username": "alex23", "password": "secret123"}).status_code == 409
    assert c.send("post", "/api/register", {"username": "bob", "password": "short"}).status_code == 400
    assert c.send("post", "/api/register", {"username": "a b", "password": "secret123"}).status_code == 400


def test_csrf_required(app):
    c = register(app)
    r = c.c.post("/api/transactions", json={"type": "expense", "amount": 10, "category": "Food", "date": c.today})
    assert r.status_code == 403


def test_login_throttle(app):
    register(app)
    c = Client(app)
    for _ in range(8):
        c.send("post", "/api/login", {"username": "alex23", "password": "nopenope1"})
    assert c.send("post", "/api/login", {"username": "alex23", "password": "secret123"}).status_code == 429


def test_transactions_and_summary(app):
    c = register(app, allowance=3000)
    r = c.send("post", "/api/transactions", {"type": "expense", "amount": 600, "category": "Food", "date": c.today, "note": "Lunch"})
    assert r.status_code == 201
    d = r.get_json()
    assert d["summary"]["spent"] == 600 and d["summary"]["balance"] == 2400
    assert d["categories"][0]["spent"] == 600
    tid = d["transactions"][0]["id"]
    d = c.send("put", f"/api/transactions/{tid}", {"type": "expense", "amount": 900, "category": "Travel", "date": c.today}).get_json()
    assert d["summary"]["spent"] == 900
    assert c.send("post", "/api/transactions", {"type": "expense", "amount": -5, "category": "Food", "date": c.today}).status_code == 400
    assert c.send("post", "/api/transactions", {"type": "expense", "amount": 5, "category": "Nope", "date": c.today}).status_code == 400
    assert c.send("post", "/api/transactions", {"type": "expense", "amount": 5, "category": "Food", "date": "2999-01-01"}).status_code == 400
    d = c.send("delete", f"/api/transactions/{tid}").get_json()
    assert d["summary"]["spent"] == 0


def test_users_are_isolated(app):
    a = register(app, "alice")
    tid = a.send("post", "/api/transactions", {"type": "expense", "amount": 50, "category": "Food", "date": a.today}).get_json()["transactions"][0]["id"]
    b = register(app, "bobby")
    assert b.send("delete", f"/api/transactions/{tid}").status_code == 404
    assert b.get("/api/dashboard").get_json()["transactions"] == []


def test_monthly_rollover(app):
    c = register(app, allowance=5000)
    cur = date.fromisoformat(c.today).strftime("%Y-%m")
    prev = month_add(cur, -2)
    with app.app_context():
        u = User.query.filter_by(username="alex23").first()
        Month.query.filter_by(user_id=u.id).delete()
        db.session.add(Month(user_id=u.id, month=prev, allowance=4000))
        db.session.commit()
    c.send("post", "/api/transactions", {"type": "expense", "amount": 1000, "category": "Food", "date": prev + "-05"})
    d = c.get("/api/dashboard").get_json()
    assert d["months"][:3] == [cur, month_add(cur, -1), prev]
    # prev: 4000 - 1000 = 3000 carried; middle month: 5000 + 3000 = 8000 carried; current 5000 + 8000
    mid = c.get(f"/api/dashboard?month={month_add(cur, -1)}").get_json()["summary"]
    assert mid["carry"] == 3000 and mid["total"] == 8000
    assert d["summary"]["carry"] == 8000 and d["summary"]["total"] == 13000
    # overspending never carries negative balance
    c.send("post", "/api/transactions", {"type": "expense", "amount": 9000, "category": "Shopping", "date": prev + "-06"})
    d = c.get("/api/dashboard").get_json()
    assert c.get(f"/api/dashboard?month={month_add(cur, -1)}").get_json()["summary"]["carry"] == 0
    assert d["summary"]["carry"] == 5000


def test_goals_and_savings(app):
    c = register(app, allowance=10000)
    d = c.send("post", "/api/goals", {"name": "Laptop", "target": 4000, "emoji": "💻"}).get_json()
    gid = d["goals"][0]["id"]
    d = c.send("post", "/api/transactions", {"type": "saving", "amount": 1000, "date": c.today, "goalId": gid}).get_json()
    g = d["goals"][0]
    assert g["saved"] == 1000 and g["pct"] == 25 and d["summary"]["saved"] == 1000
    d = c.send("delete", f"/api/goals/{gid}").get_json()
    assert d["goals"] == [] and d["summary"]["saved"] == 1000


def test_warnings_and_daily_budget(app):
    c = register(app, allowance=1000)
    d = c.send("post", "/api/transactions", {"type": "expense", "amount": 950, "category": "Shopping", "date": c.today}).get_json()
    titles = [w["title"] for w in d["warnings"]]
    assert "High spending alert" in titles
    assert d["recommendation"]["spentToday"] == 950
    c.send("put", "/api/limits", {"limits": {"Shopping": 500}})
    d = c.get("/api/dashboard").get_json()
    assert any("limit crossed" in w["title"] for w in d["warnings"])


def test_challenge_allowance_export(app):
    c = register(app)
    d = c.send("post", "/api/challenge").get_json()
    assert d["challenge"]["doneToday"] and d["challenge"]["streak"] == 1
    cur = date.fromisoformat(c.today).strftime("%Y-%m")
    d = c.send("put", f"/api/months/{cur}", {"allowance": 7000}).get_json()
    assert d["summary"]["allowance"] == 7000 and d["user"]["defaultAllowance"] == 7000
    c.send("post", "/api/transactions", {"type": "expense", "amount": 10, "category": "Food", "date": c.today, "note": "=cmd"})
    r = c.get(f"/api/export.csv?month={cur}")
    assert r.status_code == 200 and "'=cmd" in r.get_data(as_text=True)


def test_password_change_invalidates_other_sessions(app):
    c = register(app)
    other = Client(app)
    other.send("post", "/api/login", {"username": "alex23", "password": "secret123"})
    assert c.send("post", "/api/password", {"current": "secret123", "new": "newpass456"}).status_code == 200
    assert c.get("/api/dashboard").status_code == 200
    assert other.get("/api/dashboard").status_code == 401
