# Host StudentSpend on Netlify (no GitHub needed)

Netlify only serves web pages; it cannot run the Python backend or store the database.
So the site is split in two, both free and both uploaded by hand:

| Part | Where | What you upload |
|---|---|---|
| Website (what visitors open) | Netlify | `StudentSpend-netlify-site.zip` (unzipped folder) |
| Backend + database (logins, transactions) | PythonAnywhere | `StudentSpend-backend.zip` |

Netlify forwards every `/api/...` request to PythonAnywhere (the `_redirects` file), so visitors only ever see
your `netlify.app` address and logins work normally.

---

## Part 1 — Backend on PythonAnywhere (about 10 minutes)

1. Sign up for a free **Beginner** account at <https://www.pythonanywhere.com>.
   Your username becomes your backend address: `https://YOUR-USERNAME.pythonanywhere.com`.
2. Open the **Files** tab → **Upload a file** → upload `StudentSpend-backend.zip`.
3. Open the **Consoles** tab → **Bash**, and run these lines one by one:
   ```bash
   unzip -o StudentSpend-backend.zip
   cd studentspend
   python3.10 -m venv venv
   source venv/bin/activate
   pip install Flask==3.0.3 Flask-SQLAlchemy==3.1.1 SQLAlchemy==2.0.36 Werkzeug==3.1.3 python-dotenv==1.0.1
   python seed_demo.py        # optional: demo account  demo / demo1234
   pwd                        # shows /home/YOUR-USERNAME/studentspend
   ```
4. Open the **Web** tab → **Add a new web app** → **Next** → **Manual configuration** → **Python 3.10** → **Next**.
5. On the web app page:
   - **Virtualenv:** enter `/home/YOUR-USERNAME/studentspend/venv`
   - **Static files:** URL `/static/` → Directory `/home/YOUR-USERNAME/studentspend/static`
   - **Force HTTPS:** turn on
6. Click the **WSGI configuration file** link (`/var/www/YOUR-USERNAME_pythonanywhere_com_wsgi.py`),
   delete everything in it, paste this (replace `YOUR-USERNAME`), and click **Save**:
   ```python
   import os, sys
   project = "/home/YOUR-USERNAME/studentspend"
   sys.path.insert(0, project)
   os.chdir(project)
   os.environ["SESSION_COOKIE_SECURE"] = "1"
   from app import app as application
   ```
7. Back on the **Web** tab click the green **Reload** button.
8. Test: open `https://YOUR-USERNAME.pythonanywhere.com/healthz` → you should see `{"ok": true}`.
   (The full app also works directly at `https://YOUR-USERNAME.pythonanywhere.com`.)

The database is the file `studentspend/instance/studentspend.db`, and PythonAnywhere keeps it permanently.
A secret key for logins is generated automatically on first start.

## Part 2 — Website on Netlify (2 minutes)

1. Unzip `StudentSpend-netlify-site.zip`. You get a folder `netlify-site`.
2. Open `netlify-site/_redirects` in Notepad / TextEdit and replace **both** `YOUR-USERNAME` with your
   PythonAnywhere username. Save. It should look like:
   ```
   /api/*    https://aarav123.pythonanywhere.com/api/:splat    200!
   /healthz  https://aarav123.pythonanywhere.com/healthz       200!
   ```
3. Log in at <https://app.netlify.com> (free) → **Sites** (or **Projects**) → **Add new site → Deploy manually**,
   or go straight to <https://app.netlify.com/drop>.
4. Drag the whole `netlify-site` folder onto the page. In a few seconds you get a link like
   `https://lucky-otter-123.netlify.app`. Open it and register an account.
5. Optional: **Site configuration → Change site name** → e.g. `studentspend-aarav` →
   `https://studentspend-aarav.netlify.app`.

To update the website later: **Deploys** tab → drag the folder again.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Something went wrong" when logging in on Netlify | Check `_redirects` has your exact PythonAnywhere username, then drag the folder again |
| `/healthz` on PythonAnywhere shows an error | Web tab → open the **Error log**; usually a typo in the WSGI file or the virtualenv path |
| Page looks unstyled on PythonAnywhere | Check the `/static/` mapping in step 5, then Reload |
| Site stopped working after ~3 months | Free PythonAnywhere apps must be extended: Web tab → **Run until 3 months from today** |
