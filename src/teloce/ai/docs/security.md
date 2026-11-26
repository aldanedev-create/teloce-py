# Security guide

Teloce is a UI compiler, not a security boundary. Treat every browser value
as untrusted and enforce security in Python and at the deployment edge.

## Required rules

- Validate and authorize every API request on the server.
- Use CSRF protection for cookie-authenticated state changes.
- Configure restrictive CORS; never use `*` with credentials.
- Keep secrets, database URLs, and deployment tokens out of `.vel`, IndexedDB,
  generated JavaScript, and public source maps.
- Escape server values in Jinax/Jinja templates.
- Prefer normal text interpolation over `v-html`.
- Sanitize HTML before using `v-html`, even when it came from an API.
- Set a Content Security Policy appropriate for your CDN and asset strategy.
- Limit uploads by size, type, filename, and storage location.
- Rate-limit search, crawler, and expensive API endpoints.

The generated expression runtime rejects dangerous property paths and does not
use `eval()` or `Function()`. This reduces accidental code execution, but it
does not make untrusted application code safe. Do not run user-provided Python
or JavaScript in the server process; use an isolated sandbox or a separate
execution service with resource limits.

Debug dashboards, HMR endpoints, detailed source maps, crawler controls, and
development error traces must be disabled or protected in public deployments.
Client routing does not protect an admin page. The Python route and every data
endpoint must authenticate and authorize independently.
