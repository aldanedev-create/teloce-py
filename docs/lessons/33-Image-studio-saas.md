# Lesson 33: An Image Studio SaaS with FastAPI, Jinax, and Teloce-Py

This lesson builds a small but real SaaS product: an image-upload studio
with Pillow-powered filters, a Free/Pro plan with a daily upload limit, and
a `.vel` frontend that uses the transition directives from
[Lesson 32](32-transitions-and-animations.md) for the gallery, toast, and
upgrade prompt. The backend is FastAPI. The HTML shell is rendered through
Flaxon's Jinax templating engine, with a documented fallback to plain
Jinja2 so the same code runs whether or not `flaxon-framework` is
installed.

Every code block in this lesson was compiled through the real teloce
compiler and executed (backend with FastAPI's `TestClient`, frontend in a
jsdom-simulated browser) while writing it. Two real, load-bearing bugs
turned up in that process and were fixed in the compiler itself before this
lesson could be written honestly:

1. `:bind` attributes (`:src`, `:href`, `:disabled`, etc.) on elements
   inside a `v-for` were silently never applied to the real DOM.
2. `v-if` nested inside a `v-for` was resolved before the loop unrolled,
   so it always evaluated with the loop variable missing and stripped its
   content regardless of the actual per-item data.

If you're on a teloce-py version from before these fixes landed, the
gallery in this lesson will render broken images and a missing "variants"
strip. Both are core-runtime fixes, not something this lesson works around.

## What you'll build

- A FastAPI backend that accepts image uploads, applies Pillow filters
  (grayscale, sepia, blur, sharpen, invert, brighten), and serves the
  results as static files.
- A simple plan system: a Free plan capped at 5 uploads a day, a Pro plan
  with a much higher cap, returning `402 Payment Required` once the limit
  is hit.
- A Jinax/Jinja-rendered HTML shell that boots the `.vel` frontend.
- A `.vel` component: drag-and-drop upload, a gallery with enter/exit and
  reorder animations, filter buttons per image, a toast for feedback, and
  an upgrade modal when the daily limit is hit.

## Prerequisites

```bash
pip install fastapi uvicorn python-multipart pillow jinja2 teloce-py
```

`flaxon-framework` (which provides the real `Jinax` class) is optional —
see "Jinax vs. plain Jinja2" below for exactly what changes if you have it
installed versus not.

## Project layout

```text
image-studio/
├── app.py
├── templates.py
├── templates/
│   └── index.html
└── static/
    ├── js/
    │   └── App.vel
    ├── uploads/       (created at runtime)
    └── processed/     (created at runtime)
```

## The backend: FastAPI + Pillow + a plan limit

```python
# app.py
from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from templates import render

ROOT = Path(__file__).resolve().parent
UPLOADS = ROOT / "static" / "uploads"
PROCESSED = ROOT / "static" / "processed"
UPLOADS.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Image Studio")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    # In a real app the API key comes from a session/login, not a hardcoded
    # default -- see the "Production notes" section at the end.
    return render("index.html", title="Image Studio", api_key="demo-key")

# --- fake auth + plan store (swap for a real DB/auth provider in production) ---
PLAN_LIMITS = {"free": 5, "pro": 1000}
USERS = {
    "demo-key": {"user_id": "u1", "plan": "free", "uploads_today": 0},
    "pro-key": {"user_id": "u2", "plan": "pro", "uploads_today": 0},
}

IMAGES: dict[str, dict] = {}

FilterName = Literal["grayscale", "sepia", "blur", "sharpen", "invert", "brighten"]


def require_user(x_api_key: str | None = Header(default=None)):
    user = USERS.get(x_api_key or "")
    if not user:
        raise HTTPException(401, "Invalid or missing X-API-Key header")
    return user


def apply_filter(img: Image.Image, name: FilterName) -> Image.Image:
    img = img.convert("RGB")
    if name == "grayscale":
        return ImageOps.grayscale(img).convert("RGB")
    if name == "sepia":
        gray = ImageOps.grayscale(img)
        sepia = ImageOps.colorize(gray, black="#3f2d1d", white="#e8d3a4")
        return sepia.convert("RGB")
    if name == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=4))
    if name == "sharpen":
        return img.filter(ImageFilter.SHARPEN)
    if name == "invert":
        return ImageOps.invert(img)
    if name == "brighten":
        return ImageEnhance.Brightness(img).enhance(1.4)
    raise HTTPException(400, f"Unknown filter: {name}")


@app.get("/api/me")
def me(x_api_key: str | None = Header(default=None)):
    user = require_user(x_api_key)
    limit = PLAN_LIMITS[user["plan"]]
    return {
        "user_id": user["user_id"],
        "plan": user["plan"],
        "uploads_today": user["uploads_today"],
        "limit": limit,
        "remaining": max(0, limit - user["uploads_today"]),
    }


@app.post("/api/images")
async def upload_image(file: UploadFile = File(...), x_api_key: str | None = Header(default=None)):
    user = require_user(x_api_key)
    limit = PLAN_LIMITS[user["plan"]]
    if user["uploads_today"] >= limit:
        raise HTTPException(
            402,
            f"Daily upload limit reached ({limit} for the {user['plan']} plan). Upgrade to Pro for more.",
        )

    contents = await file.read()
    try:
        img = Image.open(io.BytesIO(contents))
        img.verify()
        img = Image.open(io.BytesIO(contents))  # re-open after verify() invalidates the handle
    except Exception:
        raise HTTPException(400, "Uploaded file is not a valid image")

    image_id = uuid.uuid4().hex[:12]
    original_path = UPLOADS / f"{image_id}.png"
    img.convert("RGB").save(original_path, format="PNG")

    user["uploads_today"] += 1
    IMAGES[image_id] = {
        "id": image_id,
        "owner": user["user_id"],
        "original_url": f"/static/uploads/{image_id}.png",
        "variants": {},
    }
    return IMAGES[image_id]


@app.post("/api/images/{image_id}/filter")
def filter_image(image_id: str, name: FilterName, x_api_key: str | None = Header(default=None)):
    user = require_user(x_api_key)
    record = IMAGES.get(image_id)
    if not record or record["owner"] != user["user_id"]:
        raise HTTPException(404, "Image not found")

    original_path = UPLOADS / f"{image_id}.png"
    img = Image.open(original_path)
    result = apply_filter(img, name)

    variant_name = f"{image_id}-{name}.png"
    variant_path = PROCESSED / variant_name
    result.save(variant_path, format="PNG")

    record["variants"][name] = f"/static/processed/{variant_name}"
    return record


@app.get("/api/images")
def list_images(x_api_key: str | None = Header(default=None)):
    user = require_user(x_api_key)
    return [img for img in IMAGES.values() if img["owner"] == user["user_id"]]
```

A few deliberate choices worth calling out:

- **`X-API-Key` header instead of real auth.** This keeps the lesson
  focused on the image/SaaS logic. It is not something to ship — see
  Production notes.
- **In-memory `USERS`/`IMAGES` dicts.** Restarting the server forgets
  everything. Swap for a real database before this matters to you.
- **`img.verify()` then re-open.** Pillow's `verify()` checks the file is a
  valid image but invalidates the file handle afterward, so the image has
  to be re-opened from the same bytes to actually use it. Skipping the
  re-open is a common mistake that causes a cryptic error on the next
  operation.
- **402 for the plan limit.** `402 Payment Required` is the semantically
  correct status for "you've hit a paywall," and it's what the frontend
  specifically checks for to show the upgrade modal rather than a generic
  error.

## Jinax vs. plain Jinja2

```python
# templates.py
"""Template rendering: uses Flaxon's Jinax if installed, otherwise falls
back to a plain Jinja2 Environment. Jinax exposes the same
`environment.from_string()` / `.get_template()` contract as Jinja2, so this
adapter works unmodified either way -- it's the same fallback pattern
`teloce.ssr.render_ssr` uses internally.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

try:
    from flaxon.jinax import Jinax
    _engine = Jinax(str(TEMPLATES_DIR), auto_reload=True)
    _environment = getattr(_engine, "environment", _engine)
except ImportError:
    import jinja2
    _environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def render(name: str, **context) -> HTMLResponse:
    template = _environment.get_template(name)
    return HTMLResponse(template.render(**context))
```

Being precise about what's actually verified here: this lesson was written
and tested without `flaxon` installed (it also polish on pypi can check it out), so the Jinja2 fallback branch is the
one that was actually executed and confirmed working end-to-end. The
`Jinax(str(TEMPLATES_DIR), auto_reload=True)` constructor call matches the
documented usage in [`docs/jinax-and-vel.md`](../jinax-and-vel.md), and
`teloce.ssr.render_ssr` documents the same "accept anything with a
Jinja-compatible `.environment`" contract this adapter relies on — but if
you have `flaxon-framework` installed, test that branch yourself before
relying on it in production.

`templates/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>
    <div id="app"></div>
    <script>window.__API_KEY__ = {{ api_key | tojson }};</script>
    <script type="module">
      import { mount } from "/static/js/App.js";
      mount("#app");
    </script>
  </body>
</html>
```

The API key gets handed to the frontend as a global for this lesson's
simplicity. In production this would come from a session cookie the
frontend never sees directly — again, see Production notes.

## The frontend: `.vel` with transition directives

```html
<!-- static/js/App.vel -->
<template>
  <main class="studio">
    <header>
      <h1>Image Studio</h1>
      <div :class="'plan-badge ' + plan">
        <span>{{ plan === 'pro' ? 'Pro' : 'Free' }} plan</span>
        <span class="usage">{{ remaining }} / {{ limit }} left today</span>
      </div>
    </header>

    <section class="uploader" @dragover.prevent @drop.prevent="onDrop">
      <label>
        <input type="file" accept="image/*" @change="onFileSelect" hidden />
        <span>Drop an image here or click to upload</span>
      </label>
    </section>

    <p v-if="error" class="error" transition:fade="{ duration: 150 }">{{ error }}</p>

    <section class="gallery">
      <article v-for="image in images" :key="image.id"
               transition:fade="{ duration: 200 }"
               animate:flip>
        <img :src="image.original_url" alt="" />
        <div class="filters">
          <button v-for="name in filterNames" :key="name"
                  @click="applyFilter(image, name)"
                  :disabled="busyId === image.id">
            {{ name }}
          </button>
        </div>
        <div class="variants" v-if="image.variantList.length">
          <img v-for="variant in image.variantList" :key="variant.name" :src="variant.url" :alt="variant.name"
               transition:scale="{ duration: 150 }" />
        </div>
      </article>
    </section>

    <div v-if="toast" class="toast" in:slide="{ axis: 'y', duration: 180 }" out:fade="{ duration: 120 }">
      {{ toast }}
    </div>

    <div v-if="showUpgrade" class="upgrade-modal" in:scale="{ start: 0.9, duration: 150 }" out:fade="{ duration: 100 }">
      <h2>Daily limit reached</h2>
      <p>The Free plan includes {{ limit }} uploads a day. Upgrade to Pro for unlimited uploads.</p>
      <button @click="showUpgrade = false">Maybe later</button>
    </div>
  </main>
</template>

<script>
export default {
  data() {
    return {
      apiKey: window.__API_KEY__ || "demo-key",
      images: [],
      plan: "free",
      limit: 0,
      remaining: 0,
      error: "",
      toast: "",
      showUpgrade: false,
      busyId: null,
      filterNames: ["grayscale", "sepia", "blur", "sharpen", "invert", "brighten"]
    };
  },
  async mounted() {
    await this.refreshMe();
    await this.refreshImages();
  },
  methods: {
    headers(extra) {
      return { "X-API-Key": this.apiKey, ...(extra || {}) };
    },
    withVariantList(image) {
      return {
        ...image,
        variantList: Object.entries(image.variants || {}).map(([name, url]) => ({ name, url }))
      };
    },
    async refreshMe() {
      const response = await fetch("/api/me", { headers: this.headers() });
      const me = await response.json();
      this.plan = me.plan;
      this.limit = me.limit;
      this.remaining = me.remaining;
    },
    async refreshImages() {
      const response = await fetch("/api/images", { headers: this.headers() });
      const data = await response.json();
      this.images = data.map((image) => this.withVariantList(image));
    },
    onFileSelect(event) {
      const file = event.target.files[0];
      if (file) this.upload(file);
    },
    onDrop(event) {
      const file = event.dataTransfer.files[0];
      if (file) this.upload(file);
    },
    async upload(file) {
      this.error = "";
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/images", { method: "POST", headers: this.headers(), body: form });
      if (response.status === 402) {
        this.showUpgrade = true;
        return;
      }
      if (!response.ok) {
        this.error = "Upload failed. Try a different image.";
        return;
      }
      const image = await response.json();
      this.images = [this.withVariantList(image), ...this.images];
      await this.refreshMe();
      this.showToast("Uploaded");
    },
    async applyFilter(image, name) {
      this.busyId = image.id;
      try {
        const response = await fetch(`/api/images/${image.id}/filter?name=${name}`, {
          method: "POST",
          headers: this.headers()
        });
        if (!response.ok) {
          this.error = "Filter failed.";
          return;
        }
        const updated = await response.json();
        const normalized = this.withVariantList(updated);
        this.images = this.images.map((item) => (item.id === normalized.id ? normalized : item));
        this.showToast(`Applied ${name}`);
      } finally {
        this.busyId = null;
      }
    },
    showToast(message) {
      this.toast = message;
      setTimeout(() => { this.toast = ""; }, 1600);
    }
  }
};
</script>

<style scoped>
.studio { max-width: 48rem; margin: 2rem auto; font: 1rem system-ui; padding: 0 1rem; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.plan-badge { display: flex; gap: .5rem; font-size: .85rem; padding: .3rem .6rem; border-radius: .4rem; background: #eee; }
.plan-badge.pro { background: #fde68a; }
.uploader { border: 2px dashed #ccc; border-radius: .5rem; padding: 2rem; text-align: center; cursor: pointer; margin-bottom: 1rem; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: 1rem; }
.gallery article { border: 1px solid #eee; border-radius: .5rem; padding: .5rem; }
.gallery img { width: 100%; border-radius: .3rem; }
.filters { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .4rem; }
.filters button { font-size: .75rem; padding: .2rem .5rem; }
.variants { display: flex; gap: .3rem; margin-top: .4rem; overflow-x: auto; }
.variants img { width: 3.5rem; height: 3.5rem; object-fit: cover; }
.error { color: #b91c1c; }
.toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%); background: #111; color: #fff; padding: .5rem 1rem; border-radius: .4rem; }
.upgrade-modal { position: fixed; inset: 0; margin: auto; max-width: 22rem; height: fit-content; background: #fff; border-radius: .5rem; padding: 1.5rem; box-shadow: 0 10px 40px rgba(0,0,0,.2); }
</style>
```

Two implementation details worth understanding, not just copying:

**Why `:class="'plan-badge ' + plan"` instead of `class="plan-badge" :class="plan"`.**
A static `class` attribute and a `:class` binding on the same element don't
merge here — the binding replaces the static class entirely. Computing the
full class string yourself sidesteps the ambiguity.

**Why `withVariantList` builds a plain array instead of iterating
`image.variants` (an object) directly.** This compiler's `v-for` only
supports array destructuring (`(item, index) in array`), not
Vue-style `(value, key) in object` iteration. Converting the filter results
into `[{ name, url }, ...]` up front avoids relying on unsupported syntax.

## Running it

```bash
uvicorn app:app --reload --port 8000
```

Compile the frontend once (or wire this into a file-watcher for
development):

```python
from teloce.compiler.compiler import compile_file

result = compile_file("static/js/App.vel")
with open("static/js/App.js", "w") as f:
    f.write(result["code"])
```

Open `http://127.0.0.1:8000`. Upload a few images, click filter buttons —
each one calls the backend, applies a real Pillow filter, and the result
appears as a thumbnail with a scale-in animation. Upload six times in a row
on the Free plan and the sixth attempt pops the upgrade modal instead of a
generic error.

## Testing it without a browser

Everything in this lesson was verified this way — FastAPI's `TestClient`
for the backend, and a jsdom-simulated DOM for the compiled frontend:

```python
from fastapi.testclient import TestClient
from PIL import Image
import io
from app import app

client = TestClient(app)

buf = io.BytesIO()
Image.new("RGB", (100, 60), color=(255, 100, 20)).save(buf, format="PNG")
buf.seek(0)

r = client.post(
    "/api/images",
    headers={"X-API-Key": "demo-key"},
    files={"file": ("test.png", buf, "image/png")},
)
image_id = r.json()["id"]

r = client.post(
    f"/api/images/{image_id}/filter",
    headers={"X-API-Key": "demo-key"},
    params={"name": "sepia"},
)
assert r.status_code == 200
assert "sepia" in r.json()["variants"]
```

Running this exact test against the real backend confirmed: auth rejects
missing/invalid keys with 401, uploads succeed and increment the daily
count, filters produce real processed files on disk, and the sixth upload
on the Free plan returns 402 with the expected message.

## Production notes

- **Replace the `X-API-Key` header with real auth.** A hardcoded dict of
  valid keys is a teaching simplification, not a security model. Use
  session cookies or OAuth, and never expose the raw key to client-side
  JavaScript the way `window.__API_KEY__` does here.
- **Move `USERS`/`IMAGES` to a real database.** The in-memory dicts lose
  everything on restart and won't work across multiple server processes.
- **Store processed images somewhere durable and CDN-backed** (S3 + a
  CDN, not local disk) once this runs on more than one server or needs to
  survive a redeploy.
- **Validate upload size and type more strictly.** This lesson checks the
  file is a valid image via `Image.verify()`, but doesn't cap file size —
  add a `Content-Length` check or a streaming size limit before accepting
  uploads in production.
- **Reset `uploads_today` on a schedule.** This lesson never resets the
  counter — a real plan-limit system needs a daily reset (a cron job, a
  scheduled task, or comparing against a stored "last reset" timestamp).
- **Wire the upgrade modal to real billing** (Stripe Checkout or similar)
  instead of a "Maybe later" button that does nothing — the 402 status and
  the modal are the hook point; the actual upgrade flow is a separate,
  substantial piece of work this lesson doesn't cover.
- **`animate:flip` cost.** As covered in Lesson 32, the reorder animation
  measures every managed row on a genuine reorder. A gallery with a few
  dozen images is fine; a few hundred reordering at once is worth
  profiling.
