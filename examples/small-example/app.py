from pathlib import Path
from flask import Flask, jsonify, render_template, request
from teloce.build import build_project

ROOT = Path(__file__).parent
build_project(ROOT, out_dir=ROOT / "dist", options={"dev": True})
app = Flask(__name__, static_folder="dist/static", static_url_path="/static")
messages = []

@app.get("/")
def home():
    return render_template("app.html")

@app.get("/api/messages")
def list_messages():
    return jsonify(messages)

@app.post("/api/messages")
def create_message():
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
    if not text or len(text) > 500:
        return jsonify({"error": "Message must contain 1-500 characters"}), 400
    message = {"id": len(messages) + 1, "text": text}
    messages.append(message)
    return jsonify(message), 201

if __name__ == "__main__":
    app.run(debug=True)