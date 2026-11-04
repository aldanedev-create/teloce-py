# Python-only SSR example

This example uses Teloce's framework-neutral Python SSR renderer and only the
Python standard library for HTTP serving. It does not require Node.js, Flask,
FastAPI, Django, or a framework adapter.

From this directory:

```powershell
python app.py --build-only
python app.py
```

On Windows, `py app.py` works when the Python launcher is installed. Open the
printed URL in a browser. The build writes to `dist/`, renders `ui/App.html`
with `Renderer`, and serves the hashed browser module and CSS assets from the
same directory.

The example deliberately uses `pathlib.Path` for filesystem paths and converts
paths to POSIX form only when constructing URLs. It is safe to run from any
current working directory because `app.py` resolves its own directory first.
