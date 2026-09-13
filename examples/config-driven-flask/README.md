# Config-driven Flask build

This is a small real Flask application whose `.vel` build is controlled by
`teloce.config.json`. It intentionally uses `client/` instead of `static/` to
prove that `build.static_dir` controls both source discovery and public output.

```bash
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5002>. `app.py` runs `python -m teloce build` from the
project root, then Flask serves `public-assets/client` at `/static`.

The expected generated files include these stable framework entrypoints and
their hashed implementations:

```text
public-assets/client/js/App.js
public-assets/client/js/components/StatusCard.js
public-assets/client/js/App.<hash>.js
public-assets/client/js/components/StatusCard.<hash>.js
public-assets/client/teloce-runtime.<hash>.js
```

`App.js` and `StatusCard.js` are small stable re-export shims. Their hashed
implementations import the one shared runtime. The normal build is minified
and does not write source maps; use `python -m teloce build --no-minify
--source-map` while debugging.
