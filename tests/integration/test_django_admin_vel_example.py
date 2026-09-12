"""End-to-end verification for the Django admin + compiled `.vel` example."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for emitted module validation")
def test_django_admin_example_builds_registers_model_and_serves_staff_dashboard(tmp_path: Path) -> None:
    pytest.importorskip("django")
    project = tmp_path / "django-admin-vel"
    shutil.copytree(
        ROOT / "examples" / "django-admin-vel",
        project,
        ignore=shutil.ignore_patterns("db.sqlite3", "dist", "__pycache__"),
    )

    _run(project, "build.py")
    module = project / "dist" / "static" / "js" / "AdminDashboard.js"
    runtime = project / "dist" / "static" / "teloce-runtime.js"
    assert module.is_file()
    assert runtime.is_file()
    _run(project, "-m", "django", "check", "--settings=config.settings")
    _run(project, "manage.py", "migrate", "--noinput")

    verification = """
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client
from dashboard.models import Product
assert Product in admin.site._registry
user = get_user_model().objects.create_user('admin', password='safe-password', is_staff=True)
Product.objects.create(name='Keyboard', sku='KEY-1', stock=3)
client = Client()
assert client.login(username='admin', password='safe-password')
home = client.get('/')
assert home.status_code == 200 and b'AdminDashboard.js' in home.content
summary = client.get('/api/dashboard/summary/')
assert summary.status_code == 200
data = summary.json()
assert data['total_products'] == 1 and data['units_in_stock'] == 3
assert data['low_stock'][0]['sku'] == 'KEY-1'
"""
    _run(project, "manage.py", "shell", "-c", verification)
    checked = subprocess.run(
        [shutil.which("node") or "node", "--check", str(module)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
