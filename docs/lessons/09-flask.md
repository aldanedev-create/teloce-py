# Lesson 9: Flask with imported .vel components

Flask owns routing and JSON responses. Teloce owns interactive state and presentation.

## Component import

static/js/components/Message.vel:

    <template><li><strong>{{ message.author }}</strong><span>{{ message.body }}</span></li></template>
    <script>export default { props: { message: Object } };</script>

static/js/App.vel:

    <template>
      <main><h1>Flask messages</h1><ul>

      <Message v-for="message in messages" :key="message.id" :message="message" /></ul>
        <form @submit.prevent="send"><input v-model="draft" /><button :disabled="!draft.trim()">Send</button></form>
        <p v-if="error">{{ error }}</p>
      </main>
    </template>
    <script>
    import Message from "./components/Message.vel";
    export default { components: { Message }, data() { return { messages: [], draft: "", error: "" }; },
      mounted() { this.load(); }, methods: {
        async load() { this.messages = await fetch("/api/messages").then(r => r.json()); },
        async send() { const response = await fetch("/api/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body: this.draft }) }); if (!response.ok) { this.error = "Message failed"; return; } this.draft = ""; await this.load(); }
      }
    };
    </script>

The original <for item="message" in="messages"> and <if condition="error"> syntax remains compatible with v-for and v-if aliases.

## Flask host

    from pathlib import Path
    from flask import Flask, jsonify, render_template, request
    ROOT = Path(__file__).parent
    app = Flask(__name__, static_folder=str(ROOT / "dist" / "static"), template_folder=str(ROOT / "templates"))
    messages = [{"id": 1, "author": "system", "body": "Welcome."}]

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/messages")
    def list_messages():
        return jsonify(messages)

    @app.post("/api/messages")
    def create_message():
        data = request.get_json(silent=True) or {}
        body = str(data.get("body", "")).strip()
        if not body:
            return jsonify(error="Message is required"), 400
        item = {"id": len(messages) + 1, "author": "visitor", "body": body}
        messages.append(item)
        return jsonify(item), 201

templates/index.html:

    <div id="app"></div>
    <script type="module">import { mount } from "{{ url_for('static', filename='js/App.js') }}"; mount("#app");</script>

Run `teloce doctor --verbose`, `teloce lint --strict`, `teloce build --out-dir dist`, and `python app.py`. For production use Gunicorn or another WSGI server, validate and rate-limit JSON endpoints, add CSRF protection for cookie-authenticated writes, and serve hashed assets through a proxy/CDN.
