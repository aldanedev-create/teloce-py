# Reactivity

Component data is reactive. Event handlers update state, and the runtime updates dependent DOM nodes. Use computed values for derived state and watchers for side effects.

```html
<button @click="count++">{{ count }}</button>
<p v-if="count > 0">You interacted with the app.</p>
```

Use stable keys in repeated lists so the runtime can preserve DOM identity:

```html
<li v-for="item in items" :key="item.id">{{ item.name }}</li>
```

## Explicit signals

Explicit signals are optional. In a normal `.vel` component, values returned by
`data()` are already made reactive, so this is enough:

```html
<script>
export default {
  data() { return { count: 0 }; },
  methods: { increment() { this.count++; } }
};
</script>
```

Use the standalone signal API when several browser modules need to share a
small piece of state or when writing runtime helpers. Serve the packaged
browser runtime file from your static directory, then import it from the URL
your application exposes:

```js
import { createSignal, createComputed, createEffect, batch } from "/static/teloce/signals.js";

export const online = createSignal(false);
export const status = createComputed(() => online() ? "Online" : "Offline");

const logger = createEffect(() => console.log(status()));
online.set(true);
batch(() => {
  online.set(false);
  online.set(true);
});
// logger.stop() removes the effect when it is no longer needed.
```

A signal is callable (`online()`), and also supports `.get()`, `.set(value)`,
`.update(fn)`, `.peek()`, and `.subscribe(listener)`. Tuple-style npm usage is
also supported:

```js
const [count, setCount] = createSignal(0);
setCount(count() + 1);
```

Signals are browser-side state. Do not put passwords, private database data,
or authorization decisions in them; keep those on the Python server.
