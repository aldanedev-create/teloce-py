# Flask YouTube SSR library

A small Flask application that stores approved YouTube links in memory and
renders the video library with Teloce SSR before hydration.

Install and run from this directory:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5003>. Add a normal YouTube watch, short, `youtu.be`, or
embed URL. The server validates the host and video ID, then emits only a
privacy-enhanced `youtube-nocookie.com/embed/<id>` iframe URL. Arbitrary iframe
URLs are rejected by both the Flask input validator and Teloce's SSR renderer.

The app uses `pathlib.Path`, UTF-8 files, and URL paths built with `url_for`, so
it works from Windows PowerShell, Command Prompt, or a POSIX shell.
