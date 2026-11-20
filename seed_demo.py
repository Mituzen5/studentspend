"""Create a demo account with three months of realistic data.

Usage:  python seed_demo.py            (login: demo / demo1234)
"""
import random
from datetime import date, timedelta

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

from studentspend import create_app  # noqa: E402
from studentspend.finance import ensure_months, month_add  # noqa: E402
from studentspend.models import ChallengeDay, CategoryLimit, Goal, Month, Transaction, User, db  # noqa: E402

ITEMS = [("Food", "Canteen lunch", 60, 180), ("Food", "Chai & snacks", 20, 80), ("Travel", "Bus pass top-up", 50, 200),
         ("Groceries", "Hostel groceries", 150, 600), ("Movies & fun", "Movie with friends", 150, 450),
         ("Shopping", "T-shirt", 250, 600), ("Education", "Notebooks & pens", 80, 350), ("Bills & mobile", "Mobile recharge", 199, 299),
         ("Health", "Pharmacy", 50, 250), ("Other", "Laundry", 60, 150)]


def main():
    app = create_app()
    rnd = random.Random(7)
    with app.app_context():
        old = User.query.filter_by(username="demo").first()
        if old:
            db.session.delete(old)
            db.session.commit()
        u = User(username="demo", name="Aarav", password_hash=generate_password_hash("demo1234"), default_allowance=7000)
        db.session.add(u)
        db.session.commit()
        today = date.today()
        cur = today.strftime("%Y-%m")
        first = month_add(cur, -3)
        db.session.add(Month(user_id=u.id, month=first, allowance=7000))
        db.session.commit()
        ensure_months(u, cur)
        laptop = Goal(user_id=u.id, name="New laptop", emoji="💻", target=20000, deadline=(today + timedelta(days=330)).isoformat())
        trip = Goal(user_id=u.id, name="Goa trip with friends", emoji="✈️", target=6000, deadline=(today + timedelta(days=100)).isoformat())
        fund = Goal(user_id=u.id, name="Emergency fund", emoji="🎁", target=3000)
        db.session.add_all([laptop, trip, fund])
        db.session.commit()
        laptop.created_at = trip.created_at = fund.created_at = date.fromisoformat(first + "-01")
        for m in [first, month_add(first, 1), month_add(first, 2), cur]:
            y, mo = int(m[:4]), int(m[5:])
            last = today.day if m == cur else (date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)).day
            for d in range(1, last + 1):
                for _ in range(rnd.choice([0, 0, 1, 1])):
                    cat, note, lo, hi = rnd.choice(ITEMS)
                    db.session.add(Transaction(user_id=u.id, kind="expense", amount=rnd.randint(lo, hi), category=cat, note=note,
                                               date=f"{m}-{d:02d}", month=m))
            for gid, amt, day in [(laptop.id, 1500, 2), (trip.id, 1000, 3), (fund.id, 300, 5)]:
                if day <= last:
                    db.session.add(Transaction(user_id=u.id, kind="saving", amount=amt, category="Savings", note="Monthly saving",
                                               date=f"{m}-{day:02d}", month=m, goal_id=gid))
        db.session.add_all([CategoryLimit(user_id=u.id, category="Movies & fun", limit=800),
                            CategoryLimit(user_id=u.id, category="Shopping", limit=1000)])
        for i in range(1, 4):
            db.session.add(ChallengeDay(user_id=u.id, date=(today - timedelta(days=i)).isoformat()))
        db.session.commit()
        print("Demo account ready -> Student ID: demo  Password: demo1234")


if __name__ == "__main__":
    main()
