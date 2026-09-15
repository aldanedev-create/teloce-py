from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder="dist/static", static_url_path="/static")

@app.get('/')
def home():
    return render_template('app.html')

if __name__ == '__main__':
    build_project(ROOT, options={'dev': True, 'source_maps': True})
    app.run(debug=True, port=5000)