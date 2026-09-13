"""
Create command - creates a new project.

Scaffolds a new Teloce project with a template.
"""

import subprocess
from pathlib import Path
from typing import Any
import json
import re


SUPPORTED_TEMPLATES = {'flask', 'fastapi', 'django', 'flaxon', 'basic'}
PROJECT_NAME_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')


def create_command(args: Any) -> int:
    """
    Create a new Teloce project.
    
    Args:
        args: Command-line arguments.
        
    Returns:
        Exit code.
    """
    print("🚀 Teloce Create")
    print("=" * 40)
    
    project_name = args.name
    template_name = args.template.lower()
    install_deps = not args.no_install
    init_git = not args.no_git

    if not PROJECT_NAME_PATTERN.fullmatch(project_name):
        print("❌ Invalid project name. Use letters, numbers, '_' or '-' and start with a letter.")
        return 1
    if template_name not in SUPPORTED_TEMPLATES:
        print(f"❌ Unknown template '{args.template}'. Choose one of: {', '.join(sorted(SUPPORTED_TEMPLATES))}")
        return 1
    
    project_path = Path.cwd() / project_name
    
    if project_path.exists():
        print(f"❌ Directory '{project_name}' already exists")
        return 1
    
    print(f"📁 Creating project: {project_name}")
    print(f"📋 Template: {template_name}")
    
    # Create project directory
    project_path.mkdir(parents=True)
    
    # Create template files
    if template_name == 'flask':
        create_flask_template(project_path)
    elif template_name == 'django':
        create_django_template(project_path)
    elif template_name == 'fastapi':
        create_fastapi_template(project_path)
    elif template_name == 'flaxon':
        create_flaxon_template(project_path)
    elif template_name == 'basic':
        create_basic_template(project_path)

    create_teloce_config(project_path)
    
    # Create package.json
    create_package_json(project_path, project_name)
    
    # Initialize git
    if init_git:
        print("🔧 Initializing git...")
        try:
            subprocess.run(['git', 'init'], cwd=project_path, capture_output=True)
            subprocess.run(['git', 'add', '.'], cwd=project_path, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=project_path, capture_output=True)
            print("✅ Git initialized")
        except Exception:
            print("⚠️  Git initialization skipped")
    
    # Install dependencies
    if install_deps:
        print("📦 Installing dependencies...")
        try:
            result = subprocess.run(['pip', 'install', '-r', 'requirements.txt'], cwd=project_path, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors='replace'))
            # Teloce-Py is Python-native; generated projects must not require
            # npm or Node.js. Python dependencies are installed above.
            print("✅ Python dependencies installed")
        except Exception:
            print("⚠️  Dependency installation failed")
    
    print()
    print("✅ Project created successfully!")
    print()
    print(f"📁 Location: {project_path}")
    print()
    print("🚀 Next steps:")
    print(f"   cd {project_name}")
    print("   teloce dev")
    print("   teloce build")
    print("   teloce debug")
    
    return 0


def create_basic_template(project_path: Path) -> None:
    """Create a basic project template."""
    
    # Create directories
    (project_path / 'static' / 'js').mkdir(parents=True)
    (project_path / 'static' / 'css').mkdir(parents=True)
    (project_path / 'templates').mkdir(parents=True)
    
    # Create app.py
    app_py = project_path / 'app.py'
    app_py.write_text("""
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent

app = Flask(__name__, static_folder=str(ROOT / 'dist' / 'static'), template_folder=str(ROOT / 'templates'))

@app.route('/')
def home():
    return render_template('index.html', name='Teloce')

if __name__ == '__main__':
    build_project(ROOT, options={'dev': True, 'source_maps': True})
    app.run(debug=True)
""".strip())
    
    # Create index.html
    index_html = project_path / 'templates' / 'index.html'
    index_html.write_text("""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Teloce App</title></head>
<body>
    <div id="app"></div>
    <script type="module">
        import { mount } from "{{ url_for('static', filename='js/App.js') }}";
        mount("#app");
    </script>
</body>
</html>
""".strip())
    
    # Create App.vel
    app_vel = project_path / 'static' / 'js' / 'App.vel'
    app_vel.write_text("""
<template>
    <div class="app">
        <h1>{{ title }}</h1>
        <p>Count: {{ count }}</p>
        <button @click="increment">+</button>
    </div>
</template>

<script>
export default {
    data() {
        return {
            title: 'Hello Teloce',
            count: 0
        };
    },
    methods: {
        increment() {
            this.count++;
        }
    }
};
</script>

<style scoped>
.app { padding: 20px; }
button { background: #6366f1; color: white; border: none; padding: 8px 16px; }
</style>
""".strip())


def create_flask_template(project_path: Path) -> None:
    """Create a Flask project template."""
    create_basic_template(project_path)
    
    # Create requirements.txt
    (project_path / 'requirements.txt').write_text(
        "teloce-py>=0.2.4\nflask>=2.3.0\n"
    )


def create_django_template(project_path: Path) -> None:
    """Create a Django project template."""
    create_basic_template(project_path)
    (project_path / 'app.py').unlink(missing_ok=True)
    (project_path / 'manage.py').write_text("""#!/usr/bin/env python
import os
import sys
from pathlib import Path

if __name__ == '__main__':
    from teloce.build import build_project
    build_project(Path(__file__).parent, options={'dev': True, 'source_maps': True})
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'site.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
""".strip())
    (project_path / 'requirements.txt').write_text("teloce-py>=0.2.0b1\n")
    site = project_path / 'site'
    site.mkdir(exist_ok=True)
    (site / '__init__.py').write_text('')
    (site / 'settings.py').write_text("""from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'development-only-change-me'
DEBUG = True
ROOT_URLCONF = 'site.urls'
ALLOWED_HOSTS = ['*']
INSTALLED_APPS = ['django.contrib.staticfiles']
MIDDLEWARE = []
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True}]
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'dist' / 'static']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
""".strip())
    (site / 'urls.py').write_text("""from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [path('', TemplateView.as_view(template_name='index.html'))]
""".strip())
    (site / 'wsgi.py').write_text("""import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'site.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
""".strip())
    (project_path / 'templates' / 'index.html').write_text("""{% load static %}
<!doctype html><html><body><div id="app"></div><script type="module">import { mount } from "{% static 'js/App.js' %}"; mount('#app');</script></body></html>
""".strip())
    (project_path / 'requirements.txt').write_text("teloce-py>=0.2.0b1\nDjango>=4.2.0\n")


def create_fastapi_template(project_path: Path) -> None:
    """Create a FastAPI project template."""
    create_basic_template(project_path)
    (project_path / 'app.py').write_text("""from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from teloce.build import build_project

ROOT = Path(__file__).parent
build_project(ROOT, options={'dev': True, 'source_maps': True})
app = FastAPI()
app.mount('/static', StaticFiles(directory=ROOT / 'dist' / 'static'), name='static')
templates = Jinja2Templates(directory=ROOT / 'templates')

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'name': 'Teloce'})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
""".strip())
    (project_path / 'templates' / 'index.html').write_text("""
<!doctype html><html><body><div id="app"></div><script type="module">import { mount } from "{{ url_for('static', path='js/App.js') }}"; mount('#app');</script></body></html>
""".strip())
    (project_path / 'requirements.txt').write_text("""
teloce-py>=0.2.4
fastapi>=0.100.0
uvicorn>=0.23.0
jinja2>=3.1.0
""".strip() + "\n")


def create_flaxon_template(project_path: Path) -> None:
    """Create a Flaxon + Jinax application with a compiled .vel frontend."""
    create_basic_template(project_path)
    (project_path / 'app.py').write_text('''
import mimetypes
from pathlib import Path

from flaxon import Flaxon
from flaxon.http.response import Response
from flaxon.jinax import Jinax
from teloce.build import build_project

ROOT = Path(__file__).resolve().parent
DIST = (ROOT / "dist").resolve()
app = Flaxon("teloce-flaxon-app", debug=True)
app.use_templates(Jinax(str(ROOT / "templates"), auto_reload=True))


def build_and_register_assets():
    build_project(ROOT, options={"dev": True, "source_maps": True})
    for path in DIST.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(DIST).as_posix()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        async def serve_asset(request, file_path=path, content_type=media_type):
            return Response(file_path.read_bytes(), media_type=content_type)

        app.get(f"/assets/{relative}")(serve_asset)


build_and_register_assets()


@app.get("/")
async def home(request):
    return await request.render("index.html", {"title": "Flaxon + Teloce"})


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "teloce-flaxon-app"}


if __name__ == "__main__":
    print("Run: python -m flaxon run app:app --reload")
'''.strip())
    (project_path / 'templates' / 'index.html').write_text('''
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title></head>
<body><div id="app"></div><script type="module">import { mount } from "/assets/static/js/App.js"; mount("#app");</script></body>
</html>
'''.strip())
    (project_path / 'requirements.txt').write_text(
        "teloce-py>=0.2.4\nflaxon>=0.2,<1\n"
    )


def create_teloce_config(project_path: Path) -> None:
    """Create explicit, documented defaults for a new project."""
    config = {
        'compiler': {
            'source_maps': True,
            'minify': False,
            'dev': True,
            'target': 'es2020',
        },
        'build': {
            'out_dir': 'dist',
            'static_dir': 'static',
            'clean': True,
            'minify': True,
            'shared_runtime': True,
            'spa': 'auto',
            'tree_shake': True,
            'bundler': 'teloce',
        },
        'server': {
            'host': '127.0.0.1',
            'port': 5173,
            'hmr': True,
        },
        'watch': {
            'enabled': True,
            'debounce': 300,
        },
    }
    (project_path / 'teloce.config.json').write_text(
        json.dumps(config, indent=2) + '\n', encoding='utf-8'
    )


def create_package_json(project_path: Path, project_name: str) -> None:
    """Create package.json."""
    import json
    
    package_json = {
        "name": project_name,
        "version": "1.0.0",
        "private": True,
        "scripts": {
            "dev": "teloce dev",
            "build": "teloce build",
            "debug": "teloce debug",
            "watch": "teloce watch",
        },
        "dependencies": {}
    }
    
    with open(project_path / 'package.json', 'w') as f:
        json.dump(package_json, f, indent=2)
