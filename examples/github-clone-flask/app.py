"""A small GitHub-style repository browser with Flask-Admin."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_sqlalchemy import SQLAlchemy


ROOT = Path(__file__).resolve().parent
db = SQLAlchemy()


class Repository(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    owner = db.Column(db.String(80), nullable=False, default="local")
    description = db.Column(db.String(500), nullable=False, default="")
    language = db.Column(db.String(40), nullable=False, default="Python")
    stars = db.Column(db.Integer, nullable=False, default=0)
    forks = db.Column(db.Integer, nullable=False, default=0)
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    issues = db.relationship("Issue", back_populates="repository", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<{self.owner}/{self.name}>"


class Issue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open")
    author = db.Column(db.String(80), nullable=False, default="local-user")
    repository_id = db.Column(db.Integer, db.ForeignKey("repository.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    repository = db.relationship("Repository", back_populates="issues")

    def __repr__(self) -> str:
        return f"#{self.id} {self.title}"


class PullRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    author = db.Column(db.String(80), nullable=False, default="local-user")
    repository_id = db.Column(db.Integer, db.ForeignKey("repository.id"), nullable=False)

    def __repr__(self) -> str:
        return f"PR #{self.id} {self.title}"


def _repository_json(repository: Repository) -> dict:
    return {
        "id": repository.id,
        "name": repository.name,
        "owner": repository.owner,
        "description": repository.description,
        "language": repository.language,
        "stars": repository.stars,
        "forks": repository.forks,
        "is_public": repository.is_public,
        "issue_count": len(repository.issues),
    }


def _issue_json(issue: Issue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "body": issue.body,
        "status": issue.status,
        "author": issue.author,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
    }


def _safe_next(value: str | None) -> str:
    """Accept only local paths after admin login to prevent open redirects."""
    if not value:
        return "/admin/"
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return "/admin/"
    return value


class ProtectedAdminIndexView(AdminIndexView):
    def is_accessible(self) -> bool:
        return session.get("github_clone_admin") is True

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_login", next=request.url))


class ProtectedModelView(ModelView):
    def is_accessible(self) -> bool:
        return session.get("github_clone_admin") is True

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_login", next=request.url))


def _seed_database() -> None:
    if Repository.query.count():
        return
    teloce = Repository(
        name="teloce-examples",
        owner="flaxon-labs",
        description="Copy-paste examples for Python teams building with .vel components.",
        language="Python",
        stars=42,
        forks=8,
    )
    forge = Repository(
        name="forge-notes",
        owner="local-user",
        description="A tiny notes API used to demonstrate Flask and Teloce together.",
        language="Flask",
        stars=18,
        forks=3,
    )
    scanner = Repository(
        name="safe-scan-lab",
        owner="security-team",
        description="A training project for documenting safe, defensive web checks.",
        language="Python",
        stars=27,
        forks=5,
    )
    db.session.add_all([teloce, forge, scanner])
    db.session.flush()
    db.session.add_all(
        [
            Issue(repository_id=teloce.id, title="Add a router lesson", body="Document hash routing for Flask deployments."),
            Issue(repository_id=forge.id, title="Add pagination", body="Paginate repository results in the API."),
        ]
    )
    db.session.commit()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        static_folder=str(ROOT / "dist" / "static"),
        template_folder=str(ROOT / "templates"),
        instance_relative_config=True,
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    default_database = f"sqlite:///{Path(app.instance_path) / 'github_clone.sqlite3'}"
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("GITHUB_CLONE_SECRET_KEY", "local-development-secret"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", default_database),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        ADMIN_PASSWORD=os.environ.get("GITHUB_CLONE_ADMIN_PASSWORD", "dev-admin"),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    admin = Admin(
        app,
        name="ForgeHub Admin",
        template_mode="bootstrap4",
        index_view=ProtectedAdminIndexView(name="Dashboard", url="/admin"),
    )
    admin.add_view(ProtectedModelView(Repository, db.session, category="Content"))
    admin.add_view(ProtectedModelView(Issue, db.session, category="Content"))
    admin.add_view(ProtectedModelView(PullRequest, db.session, category="Content"))

    with app.app_context():
        db.create_all()
        _seed_database()

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "service": "forgehub"})

    @app.get("/api/repositories")
    def repositories():
        query = request.args.get("q", "").strip()
        statement = db.select(Repository).order_by(Repository.stars.desc(), Repository.name.asc())
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                db.or_(
                    Repository.name.ilike(pattern),
                    Repository.owner.ilike(pattern),
                    Repository.description.ilike(pattern),
                )
            )
        rows = db.session.scalars(statement).all()
        return jsonify({"items": [_repository_json(row) for row in rows], "total": len(rows), "query": query})

    @app.get("/api/repositories/<int:repository_id>")
    def repository_detail(repository_id: int):
        repository = db.get_or_404(Repository, repository_id)
        payload = _repository_json(repository)
        payload["issues"] = [_issue_json(issue) for issue in sorted(repository.issues, key=lambda item: item.id, reverse=True)]
        return jsonify(payload)

    @app.post("/api/repositories/<int:repository_id>/issues")
    def create_issue(repository_id: int):
        repository = db.get_or_404(Repository, repository_id)
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "")).strip()
        body = str(payload.get("body", "")).strip()
        if not title or len(title) > 160:
            return jsonify({"error": "Issue title must contain 1-160 characters."}), 400
        if len(body) > 5000:
            return jsonify({"error": "Issue body must be 5,000 characters or fewer."}), 400
        issue = Issue(repository=repository, title=title, body=body)
        db.session.add(issue)
        db.session.commit()
        return jsonify(_issue_json(issue)), 201

    @app.route("/admin-login", methods=["GET", "POST"])
    def admin_login():
        error = None
        if request.method == "POST":
            supplied = request.form.get("password", "")
            expected = str(app.config["ADMIN_PASSWORD"])
            if hmac.compare_digest(supplied, expected):
                session["github_clone_admin"] = True
                return redirect(_safe_next(request.form.get("next")))
            error = "Incorrect admin password."
        return render_template("admin_login.html", error=error, next=_safe_next(request.args.get("next")))

    @app.post("/admin-logout")
    def admin_logout():
        session.pop("github_clone_admin", None)
        return redirect(url_for("home"))

    return app


app = create_app()


if __name__ == "__main__":
    from build import build_assets

    build_assets()
    app.run(debug=True, port=5010)
