# GitHub Clone — Flask + Teloce router

This is a small, working GitHub-style project browser. It is intentionally
local and self-contained: repositories and issues are stored in SQLite,
the `.vel` files render the interface, Teloce generates the client router,
and Flask-Admin provides protected CRUD screens for staff.

It is not a connection to GitHub.com and it does not copy GitHub's branding.
It is a useful example of building a repository dashboard with Flask and
Teloce.

## Run it

```bash
cd examples/github-clone-flask
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Optional but recommended: choose a private admin password.
# Windows PowerShell: $env:GITHUB_CLONE_ADMIN_PASSWORD = "change-this"
# macOS/Linux: export GITHUB_CLONE_ADMIN_PASSWORD=change-this
python app.py
```

If this environment previously installed WTForms 3.2.x, refresh the pinned
dependencies before starting:

```bash
python -m pip install --upgrade --force-reinstall -r requirements.txt
```

The WTForms pin is required because Flask-Admin 1.6.x still uses the older
validator-flags contract. Without it, opening an admin edit form can raise
`AttributeError: 'tuple' object has no attribute 'items'`.

Open <http://127.0.0.1:5010/>. The first run compiles every `.vel` file into
`dist/static/js/` and creates a local SQLite database in `instance/`.

Open <http://127.0.0.1:5010/admin-login> to access the Flask-Admin panel.
The development password is `dev-admin` only when
`GITHUB_CLONE_ADMIN_PASSWORD` is not set. Always set a strong password before
deploying.

## What to try

- Search the seeded repositories on the home page.
- Open a repository. The URL changes to `#/repo/<id>` through the generated
  Teloce router without a full page reload.
- Create an issue from the repository page. The form sends a real POST request
  to Flask and the new issue is returned from the API.
- Sign in at `/admin-login`, then use `/admin/` to create, edit, or delete
  repositories and issues. Refresh the frontend to see the same database data.

## Project shape

```text
github-clone-flask/
├── app.py                    # Flask app, API, database models, admin setup
├── build.py                  # Teloce build + generated router
├── teloce.config.json        # One custom detail-route override
├── requirements.txt
├── templates/index.html      # Mounts the compiled App.js
├── static/js/
│   ├── App.vel
│   ├── components/
│   └── pages/
├── dist/static/js/router.js   # Generated; do not hand-edit
└── tests/                    # Example-local checks are in the main repo suite
```

The source of truth is `static/js/`. Build output belongs in `dist/` and is
ignored by this repository's normal workflow. The router uses hash mode so
Flask only needs to serve `/`; direct browser refreshes do not require a
history-mode catch-all route.

The router is generated from the pages directory. No route table is needed
for conventional page names:

```text
static/js/pages/HomePage.vel       /
static/js/pages/SettingsPage.vel   /settings
static/js/pages/projects/[id].vel  /projects/:id
```

This example needs one explicit override because the detail page uses the
descriptive filename RepoPage.vel. SPA discovery itself is automatic:

```python
"spa_routes": {"RepoPage.js": "/repo/:id"},
```

Teloce compiles the pages, derives the imports, validates the routes, and
writes router.js for you.
