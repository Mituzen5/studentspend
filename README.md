# StudentSpend — Smart Student Money Manager (Full-Stack Edition)

StudentSpend helps students track every rupee, know exactly how much they can safely spend today,
roll unused money into next month automatically, and reach their savings goals.

![Dashboard](docs/screenshots/02-dashboard.png)

## Features

| Area | What it does |
|---|---|
| Secure accounts | Register/login backed by a database. Passwords hashed (Werkzeug scrypt/pbkdf2), HttpOnly + SameSite session cookies, CSRF protection, login rate-limiting, security headers (CSP, X-Frame-Options), password change (signs out other devices), account deletion |
| Dashboard | Monthly money, spent, saved, balance, budget health bar, category breakdown with limits, recent activity (search, filter, edit, delete, CSV export) |
| Monthly rollover | Every new month is created automatically with your default allowance **plus the unused balance of the previous month**. Carry-forward is recalculated live if you edit an older month. Overspending never carries a negative balance |
| Smart warnings | Budget-used alerts (60 / 80 / 100 %), spending-pace projection, over-today's-limit, category limits (80 % / 100 %), too many "wants", big purchases, goal savings due, "pay yourself first" nudges |
| Daily budget | Today's safe-to-spend, spent today, left today, weekly allowance, and a goal-friendly daily budget |
| Reports | Interactive Chart.js charts: category doughnut, daily spending bars, 6-month history, needs vs wants, cumulative trend vs ideal pace. KPIs, written monthly summary, month-by-month table, Print / Save as PDF, CSV export (month or all-time) |
| Savings goals | Emoji, target, optional deadline, progress bar, amount needed per day/month, estimated completion, status (on track / behind / overdue / completed), add money, edit, delete |
| Extras | No-spend challenge with streaks, money health score (0–100), dark mode, mobile bottom navigation and quick-add button, fully responsive |

## Tech stack

- **Backend:** Python 3.10+ · Flask · SQLAlchemy
- **Database:** SQLite locally (zero setup) · PostgreSQL in production (set `DATABASE_URL`)
- **Frontend:** HTML, CSS, vanilla JavaScript, Chart.js (bundled locally — no CDN needed)
- **Server:** Gunicorn

```
studentspend/
├── app.py                  # entry point (python app.py / gunicorn app:app)
├── studentspend/
│   ├── __init__.py         # Flask app, REST API, auth & security
│   ├── models.py           # database tables
│   └── finance.py          # rollover, warnings, daily budget, goals, reports
├── static/                 # index.html, css/, js/, vendor/chart.umd.min.js
├── tests/test_api.py       # automated tests
├── seed_demo.py            # creates a demo account with sample data
├── requirements.txt
├── Dockerfile · Procfile · render.yaml
└── .env.example
```

### Database tables

`users` (hashed password) · `months` (one row per budget cycle + allowance) · `transactions` (expenses & savings) ·
`goals` · `category_limits` · `challenge_days`. Tables are created automatically on first start.

---

## 1. Run it on your computer

**Requirements:** Python 3.10 or newer ([download](https://www.python.org/downloads/)). Check with `python --version`.

```bash
# 1. Open a terminal in the project folder
cd studentspend

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) create a demo account with 3 months of sample data
python seed_demo.py          # login: demo / demo1234

# 5. Start the website
python app.py
```

Open **http://localhost:5000** and create an account (or log in with the demo account).

The database is stored in `instance/studentspend.db`. Delete that file to start fresh.

### Run the tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

### Configuration (optional)

Copy `.env.example` to `.env` and edit:

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies. **Set a long random value in production** (`python -c "import secrets; print(secrets.token_hex(32))"`) | auto-generated in `instance/secret_key` |
| `DATABASE_URL` | Database connection. Use PostgreSQL in production | local SQLite file |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS | `0` |
| `PORT` | Port to listen on | `5000` |

---

## 2. Deploy it online

> Use PostgreSQL in production. Free hosts usually wipe the local disk on every restart, which would delete a SQLite database.

### Option A — Render (free, easiest, includes a free PostgreSQL database)

1. Push this folder to a GitHub repository:
   ```bash
   git init && git add . && git commit -m "StudentSpend"
   git branch -M main
   git remote add origin https://github.com/<you>/studentspend.git
   git push -u origin main
   ```
2. Sign in at [render.com](https://render.com) → **New → Blueprint** → choose your repository.
3. Render reads `render.yaml` and creates the web service and a PostgreSQL database, then sets
   `DATABASE_URL`, `SECRET_KEY` and `SESSION_COOKIE_SECURE` for you. Click **Apply**.
4. Wait for the build to finish, then open the `https://studentspend-xxxx.onrender.com` URL.
5. (Optional) To add the demo account: open the service → **Shell** → run `python seed_demo.py`.

Manual setup instead of the blueprint: create a **PostgreSQL** database, then a **Web Service** with
build command `pip install -r requirements.txt`, start command `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT`,
and environment variables `DATABASE_URL` (the database's Internal URL), `SECRET_KEY` (random) and `SESSION_COOKIE_SECURE=1`.

### Option B — Railway

1. Push to GitHub (step 1 above). At [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**.
2. In the project click **+ New → Database → PostgreSQL**.
3. Open the web service → **Variables**: add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`, `SECRET_KEY` = a random string, `SESSION_COOKIE_SECURE` = `1`.
4. Railway uses the `Procfile` to start Gunicorn. Under **Settings → Networking** click **Generate Domain**.

### Option C — Docker (any VPS, AWS, Azure, Google Cloud Run, Fly.io)

```bash
docker build -t studentspend .
docker run -p 8000:8000 \
  -e SECRET_KEY=<random-string> \
  -e DATABASE_URL=postgresql://user:pass@host:5432/studentspend \
  -e SESSION_COOKIE_SECURE=1 \
  studentspend
```

For a quick single-server setup with SQLite, mount a volume instead of setting `DATABASE_URL`:
`docker run -p 8000:8000 -e SECRET_KEY=... -v studentspend-data:/app/instance studentspend`

### Option D — PythonAnywhere (free, SQLite is fine here because the disk is persistent)

1. Upload the project (or `git clone` it) in a **Bash console**, then:
   `python3.10 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. **Web → Add a new web app → Manual configuration → Python 3.10**. Set the virtualenv path to the `venv` folder.
3. Edit the WSGI file so it contains:
   ```python
   import sys, os
   sys.path.insert(0, "/home/<you>/studentspend")
   os.environ["SECRET_KEY"] = "<random-string>"
   os.environ["SESSION_COOKIE_SECURE"] = "1"
   from app import app as application
   ```
4. Add a static files mapping: URL `/static/` → `/home/<you>/studentspend/static/`. Click **Reload**.

### Production checklist

- [ ] `SECRET_KEY` set to a long random value
- [ ] `DATABASE_URL` points to PostgreSQL (or a persistent disk for SQLite)
- [ ] Site served over HTTPS and `SESSION_COOKIE_SECURE=1`
- [ ] Health check: `GET /healthz` returns `{"ok": true}`

---

## API reference

All endpoints are JSON. State-changing requests need the `X-CSRF-Token` header (returned by `GET /api/session`).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/session` | CSRF token + current user |
| POST | `/api/register` · `/api/login` · `/api/logout` | Authentication |
| GET | `/api/dashboard?month=YYYY-MM` | Full computed dashboard (summary, warnings, recommendation, charts, goals, report) |
| POST / PUT / DELETE | `/api/transactions[/id]` | Add / edit / delete expenses and savings |
| PUT | `/api/months/YYYY-MM` | Set the allowance for a month |
| POST / PUT / DELETE | `/api/goals[/id]` | Savings goals |
| POST | `/api/challenge` | Complete today's no-spend challenge |
| PUT | `/api/limits` | Category spending limits |
| PUT | `/api/profile` · POST `/api/password` · DELETE `/api/account` | Account settings |
| GET | `/api/export.csv?month=YYYY-MM\|all` | CSV export |

## Notes

- The browser sends its local date, so the monthly rollover happens at the student's own midnight.
- Login rate-limiting is kept in memory per server process. For multi-server deployments, put it behind a shared store such as Redis.
