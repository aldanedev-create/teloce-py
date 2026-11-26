# Template syntax

Interpolation uses `{{ expression }}`. Bind values with `:attribute="expression"` or `v-bind:attribute`, listen with `@event="handler"` or `v-on:event`, and use `v-if`/`v-for` for control flow.

The original Teloce tags remain valid:

```html
<if condition="loggedIn">Dashboard</if>
<for each="item in items">{{ item.name }}</for>
```

Expressions are evaluated in component state and should remain small and
readable. Move reusable calculations into `computed` values or methods. Use
stable keys for list identity, modifiers for event behavior, and escaped text
by default. Treat `v-html` as an explicit trusted-content escape hatch.

Common patterns:

```html
<button :disabled="saving" @click.prevent="save">{{ saving ? "Saving..." : "Save" }}</button>
<div :class="{ active: selected, muted: disabled }"></div>
<input :model="email" />
```
