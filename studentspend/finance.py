"""Budget engine: monthly rollover, warnings, daily recommendations, goals and reports."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from .models import ChallengeDay, CategoryLimit, Goal, Month, Transaction, db

CATEGORIES = [
    ("Food", "🍔"), ("Movies & fun", "🎬"), ("Groceries", "🛒"), ("Travel", "🚌"),
    ("Shopping", "🛍️"), ("Education", "📚"), ("Bills & mobile", "📱"), ("Health", "🩺"), ("Other", "📦"),
]
CATEGORY_NAMES = [c[0] for c in CATEGORIES]
WANTS = {"Movies & fun", "Shopping"}


def r2(x):
    return round(float(x or 0) + 0.0, 2)


def parse_month(m):
    y, mo = m.split("-")
    return int(y), int(mo)


def month_add(m, n):
    y, mo = parse_month(m)
    idx = y * 12 + (mo - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_range(start, end):
    out, m = [], start
    while m <= end:
        out.append(m)
        m = month_add(m, 1)
    return out


def days_in(m):
    y, mo = parse_month(m)
    return calendar.monthrange(y, mo)[1]


# ---------------------------------------------------------------- rollover
def ensure_months(user, upto):
    """Create every missing cycle so the user's months are contiguous up to `upto`.

    New cycles inherit the user's default allowance (the allowance renews each month);
    the unused balance of the previous cycle is carried forward automatically.
    """
    existing = {m.month: m for m in user.months.all()}
    if not existing:
        db.session.add(Month(user_id=user.id, month=upto, allowance=user.default_allowance))
        db.session.commit()
        return
    first, last = min(existing), max(existing)
    start = min(first, upto)
    end = max(last, upto)
    changed = False
    for m in month_range(start, end):
        if m not in existing:
            allowance = 0 if m < first else user.default_allowance
            db.session.add(Month(user_id=user.id, month=m, allowance=allowance))
            changed = True
    if changed:
        db.session.commit()


def ledger(user):
    """Return an ordered dict month -> computed totals, chaining carry-forward."""
    months = sorted(user.months.all(), key=lambda m: m.month)
    sums = defaultdict(lambda: {"expense": 0.0, "saving": 0.0, "count": 0})
    for t in user.transactions.all():
        s = sums[t.month]
        s[t.kind] += t.amount
        if t.kind == "expense":
            s["count"] += 1
    out, carry = {}, 0.0
    for m in months:
        s = sums[m.month]
        total = m.allowance + carry
        balance = total - s["expense"] - s["saving"]
        out[m.month] = {
            "month": m.month, "allowance": r2(m.allowance), "carry": r2(carry), "total": r2(total),
            "spent": r2(s["expense"]), "saved": r2(s["saving"]), "balance": r2(balance),
            "used": r2(s["expense"] + s["saving"]), "expenseCount": s["count"],
            "usedPct": round(min(999, (s["expense"] + s["saving"]) / total * 100), 1) if total > 0 else (100.0 if s["expense"] + s["saving"] > 0 else 0.0),
        }
        carry = max(0.0, balance)
    return out


# ---------------------------------------------------------------- goals
def goal_summaries(user, today):
    saved_by_goal = defaultdict(float)
    monthly_by_goal = defaultdict(lambda: defaultdict(float))
    for t in user.transactions.filter_by(kind="saving").all():
        if t.goal_id:
            saved_by_goal[t.goal_id] += t.amount
            monthly_by_goal[t.goal_id][t.month] += t.amount
    out = []
    for g in user.goals.order_by(Goal.created_at).all():
        saved = saved_by_goal[g.id]
        remaining = max(0.0, g.target - saved)
        pct = min(100.0, saved / g.target * 100) if g.target else 0
        info = {"id": g.id, "name": g.name, "emoji": g.emoji, "target": r2(g.target), "saved": r2(saved),
                "remaining": r2(remaining), "pct": round(pct, 1), "deadline": g.deadline,
                "completed": remaining <= 0, "status": "completed" if remaining <= 0 else "active",
                "perDay": None, "perMonth": None, "daysLeft": None, "eta": None}
        if remaining > 0 and g.deadline:
            dl = date.fromisoformat(g.deadline)
            days_left = (dl - today).days
            info["daysLeft"] = days_left
            if days_left <= 0:
                info["status"] = "overdue"
            else:
                months_left = max(1, (dl.year - today.year) * 12 + dl.month - today.month + (1 if dl.day >= today.day else 0))
                info["perDay"] = r2(remaining / days_left)
                info["perMonth"] = r2(remaining / months_left)
        contribs = monthly_by_goal[g.id]
        if remaining > 0 and contribs:
            created = g.created_at.date() if g.created_at else today
            months_active = max(1, (today.year - created.year) * 12 + today.month - created.month + 1)
            avg = saved / months_active
            if avg > 0:
                months_needed = int(-(-remaining // avg))
                info["eta"] = month_add(today.strftime("%Y-%m"), months_needed)
                if g.deadline and info["eta"] > g.deadline[:7] and info["status"] == "active":
                    info["status"] = "behind"
                elif g.deadline and info["status"] == "active":
                    info["status"] = "on-track"
        out.append(info)
    return out


# ---------------------------------------------------------------- dashboard
def build_dashboard(user, month, today):
    cur_month = today.strftime("%Y-%m")
    ensure_months(user, cur_month)
    led = ledger(user)
    if month not in led:
        month = cur_month
    m = led[month]
    txs = user.transactions.filter_by(month=month).order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    expenses = [t for t in txs if t.kind == "expense"]
    is_current = month == cur_month
    dim = days_in(month)

    # categories
    limits = {l.category: l.limit for l in user.limits.all()}
    cat_tot = defaultdict(float)
    for t in expenses:
        cat_tot[t.category] += t.amount
    categories = []
    for name, icon in CATEGORIES:
        val = cat_tot.get(name, 0.0)
        lim = limits.get(name)
        categories.append({"name": name, "icon": icon, "spent": r2(val), "limit": r2(lim) if lim else None,
                           "share": round(val / m["spent"] * 100, 1) if m["spent"] else 0,
                           "limitPct": round(val / lim * 100, 1) if lim else None})

    # daily series
    per_day = defaultdict(float)
    for t in expenses:
        per_day[int(t.date[8:10])] += t.amount
    last_day = today.day if is_current else dim
    cumulative, run = [], 0.0
    for d in range(1, dim + 1):
        run += per_day.get(d, 0.0)
        cumulative.append(r2(run) if d <= last_day else None)
    ideal = [r2(max(0, m["total"] - m["saved"]) / dim * d) for d in range(1, dim + 1)]
    daily = [r2(per_day.get(d, 0.0)) for d in range(1, dim + 1)]

    # daily budget recommendation
    today_s = today.isoformat()
    spent_today = sum(t.amount for t in expenses if t.date == today_s) if is_current else 0.0
    goals = goal_summaries(user, today)
    if is_current:
        remaining_days = dim - today.day + 1
        start_of_day = m["balance"] + spent_today
        daily_limit = max(0.0, start_of_day) / remaining_days
        left_today = daily_limit - spent_today
        goal_need = sum(min(g["perMonth"] or 0, g["remaining"]) for g in goals if g["status"] in ("active", "on-track", "behind") and g["perMonth"])
        saved_toward_goals_this_month = sum(t.amount for t in txs if t.kind == "saving" and t.goal_id)
        goal_need_left = max(0.0, goal_need - saved_toward_goals_this_month)
        goal_daily = max(0.0, start_of_day - goal_need_left) / remaining_days
    else:
        remaining_days, daily_limit, left_today, goal_need_left, goal_daily = 0, 0.0, 0.0, 0.0, 0.0
    days_elapsed = today.day if is_current else dim
    avg_daily = m["spent"] / days_elapsed if days_elapsed else 0
    projected = avg_daily * dim if is_current else m["spent"]
    recommendation = {
        "isCurrent": is_current, "remainingDays": remaining_days, "dailyLimit": r2(daily_limit),
        "spentToday": r2(spent_today), "leftToday": r2(left_today), "weeklyLimit": r2(daily_limit * min(7, remaining_days)),
        "goalAwareDaily": r2(goal_daily), "goalReserve": r2(goal_need_left), "avgDaily": r2(avg_daily),
        "projectedSpend": r2(projected),
    }

    warnings = smart_warnings(m, categories, recommendation, expenses, is_current, dim)
    if is_current and goal_need_left > 0:
        warnings.insert(len([w for w in warnings if w["level"] == "red"]), {
            "level": "info", "icon": "🎯", "title": "Goal savings due",
            "text": f"Save ₹{goal_need_left:,.0f} more this month to keep your savings goals on schedule."})

    # report
    prev = led.get(month_add(month, -1))
    wants = sum(cat_tot.get(c, 0) for c in WANTS)
    needs = m["spent"] - wants
    biggest = max(expenses, key=lambda t: t.amount) if expenses else None
    top = max(categories, key=lambda c: c["spent"]) if m["spent"] else None
    no_spend_days = sum(1 for d in range(1, last_day + 1) if per_day.get(d, 0) == 0)
    challenge_dates = {c.date for c in user.challenges.all()}
    report = {
        "avgDaily": r2(avg_daily), "needs": r2(needs), "wants": r2(wants),
        "wantsPct": round(wants / m["spent"] * 100, 1) if m["spent"] else 0,
        "savingsRate": round(m["saved"] / m["total"] * 100, 1) if m["total"] else 0,
        "biggest": tx_json(biggest) if biggest else None,
        "topCategory": {"name": top["name"], "icon": top["icon"], "spent": top["spent"]} if top else None,
        "noSpendDays": no_spend_days, "daysTracked": last_day,
        "prevSpent": prev["spent"] if prev else None,
        "spendChangePct": round((m["spent"] - prev["spent"]) / prev["spent"] * 100, 1) if prev and prev["spent"] else None,
        "carriedOut": r2(max(0, m["balance"])) if not is_current else None,
        "score": health_score(m, wants, recommendation, is_current, dim),
    }

    months_sorted = sorted(led)
    history = [led[x] for x in months_sorted if x <= month][-6:]

    return {
        "user": user_json(user),
        "today": today_s, "month": month, "currentMonth": cur_month, "months": months_sorted[::-1],
        "summary": m, "categories": categories, "categoryNames": CATEGORY_NAMES,
        "transactions": [tx_json(t) for t in txs],
        "series": {"labels": list(range(1, dim + 1)), "daily": daily, "cumulative": cumulative, "ideal": ideal},
        "history": history, "goals": goals, "recommendation": recommendation, "warnings": warnings,
        "report": report, "challenge": challenge_info(challenge_dates, today, month),
    }


def smart_warnings(m, categories, rec, expenses, is_current, dim):
    w = []
    pct = m["usedPct"]
    if m["total"] <= 0 and not expenses:
        w.append(("amber", "💳", "Set your allowance", "Add this month's allowance so StudentSpend can plan your daily budget."))
    if pct >= 100:
        w.append(("red", "🚨", "Budget exceeded!", "Pause non-essential spending and review your expenses."))
    elif pct >= 80:
        w.append(("red", "⚠️", "High spending alert", f"You have used {round(pct)}% of your monthly money."))
    elif pct >= 60:
        w.append(("amber", "👀", "Heads up", f"You have used {round(pct)}% of your budget. Keep an eye on spending."))
    if is_current and m["total"] > 0:
        available = m["total"] - m["saved"]
        if rec["projectedSpend"] > available and pct < 100 and m["spent"] > 0:
            over = rec["projectedSpend"] - available
            w.append(("amber", "📈", "Spending pace too fast",
                      f"At ₹{rec['avgDaily']:,.0f}/day you'll spend about ₹{rec['projectedSpend']:,.0f} this month — ₹{over:,.0f} more than you have."))
        if rec["spentToday"] > 0 and rec["leftToday"] < 0:
            w.append(("red", "📅", "Over today's limit",
                      f"You spent ₹{rec['spentToday']:,.0f} today, ₹{-rec['leftToday']:,.0f} above your safe-to-spend budget."))
    for c in categories:
        if c["limit"]:
            if c["limitPct"] >= 100:
                w.append(("red", c["icon"], f"{c['name']} limit crossed", f"₹{c['spent']:,.0f} spent of your ₹{c['limit']:,.0f} limit."))
            elif c["limitPct"] >= 80:
                w.append(("amber", c["icon"], f"{c['name']} nearly at limit", f"{round(c['limitPct'])}% of your ₹{c['limit']:,.0f} limit used."))
    wants = sum(c["spent"] for c in categories if c["name"] in WANTS)
    if m["spent"] >= 500 and wants / m["spent"] > 0.4:
        w.append(("amber", "🎬", "Lots of 'wants' this month", f"{round(wants / m['spent'] * 100)}% of spending went to movies & shopping. Try a 70/30 needs-wants split."))
    if expenses and m["total"] > 0:
        big = max(expenses, key=lambda t: t.amount)
        if big.amount >= 0.3 * m["total"]:
            w.append(("amber", "💸", "Big purchase spotted", f"'{big.note or big.category}' used {round(big.amount / m['total'] * 100)}% of this month's money."))
    if not any(x[0] in ("red", "amber") for x in w):
        if m["total"] > 0:
            w.append(("green", "✅", "Healthy spending zone", "You are in a healthy spending zone. Keep it up!"))
    if is_current and m["saved"] == 0 and m["total"] > 0:
        w.append(("info", "🌱", "Pay yourself first", "Move even ₹100 to savings today — small, regular saving builds the habit."))
    return [{"level": a, "icon": b, "title": c, "text": d} for a, b, c, d in w]


def health_score(m, wants, rec, is_current, dim):
    if m["total"] <= 0:
        return 0
    score = 100.0
    pct = m["usedPct"]
    if pct > 100:
        score -= 45
    elif pct > 80:
        score -= 20
    if is_current and rec["projectedSpend"] > m["total"] - m["saved"]:
        score -= 15
    if m["spent"] > 0 and wants / m["spent"] > 0.4:
        score -= 10
    rate = m["saved"] / m["total"]
    score += min(10, rate * 50) - (10 if m["saved"] == 0 else 0)
    return int(max(0, min(100, round(score))))


def challenge_info(dates, today, month):
    streak, d = 0, today
    if today.isoformat() not in dates:
        d = today - timedelta(days=1)
    while d.isoformat() in dates:
        streak += 1
        d -= timedelta(days=1)
    return {"doneToday": today.isoformat() in dates, "streak": streak,
            "thisMonth": sum(1 for x in dates if x.startswith(month)), "total": len(dates)}


def tx_json(t):
    return {"id": t.id, "type": t.kind, "amount": r2(t.amount), "category": t.category, "note": t.note,
            "date": t.date, "goalId": t.goal_id}


def user_json(u):
    return {"id": u.id, "username": u.username, "name": u.name, "defaultAllowance": r2(u.default_allowance),
            "limits": {l.category: r2(l.limit) for l in u.limits.all()}}
