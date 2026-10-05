# Production checklist

Compile at build time and deploy the generated artifact:

```bash
teloce build --out-dir dist --bundle --source-map --hash-assets
```

MinifyJS is the default production minifier and bundle backend; it requires no
Node.js. See [native MinifyJS builds](minifyjs.md) for configuration, source maps,
external dependencies, and build reports.

Before deploying:

1. pin the Teloce-Py version and Python version;
2. run the Python test suite and browser tests for critical flows;
3. serve hashed assets with immutable cache headers;
4. keep source maps private if they reveal source or internal paths;
5. configure a strict Content Security Policy appropriate for your app;
6. sanitize any value used by `v-html`;
7. add CSRF protection to state-changing APIs;
8. authenticate and authorize every API route;
9. add error reporting for both Python and browser errors;
10. test the compiled output in the browsers you support.

The examples intentionally use in-memory data and development servers. They are teaching examples, not a security boundary or a deployment configuration.

## Release process

1. Install pinned dependencies in a clean environment.
2. Run linting, unit tests, compiler tests, and browser tests.
3. Run `teloce build --out-dir dist --source-map --hash-assets --bundle`.
4. Inspect the build report and fail CI if any component fails.
5. Publish only the generated assets and required Python application files.
6. Serve hashed assets with long-lived cache headers.
7. Roll back the complete application and asset set together.

Do not expose debug servers, source maps, development HMR endpoints, or
development secrets in a public deployment. The Django scanner example needs
additional SSRF and egress controls before it can be internet-facing.
