# Lesson 45: polling and live data

Use `poll` for a JSON endpoint and `live` for a WebSocket URL or a named
adapter. Polling pauses while the document is hidden and retries with bounded
backoff after failures.

```html
<template>
  <section poll="/api/summary" interval="10000" poll-target="summary">
    <strong>{{ summary.total | number }}</strong>
  </section>
</template>
<script>export default { data() { return { summary: { total: 0 } }; } };</script>
```

For a WebSocket:

```html
<div live="wss://example.test/events" live-target="latest"></div>
```

For a host-controlled adapter:

```js
globalThis.__teloceLiveAdapters = {
  prices(apply) {
    const timer = setInterval(() => apply({ value: Date.now() }), 5000);
    return () => clearInterval(timer);
  }
};
```

Use authentication and origin checks in the API/WebSocket server. Teloce does
not turn an unauthenticated endpoint into a secure one.
