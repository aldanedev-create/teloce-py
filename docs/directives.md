# Directives

Teloce-Py keeps the original Teloce API. The npm-style `v-*` forms are
additional aliases, not replacements.

## Conditions

Original Teloce API:

```html
<if condition="user">Welcome {{ user.name }}</if>
```

Compatibility API:

```html
<p v-if="user">Welcome {{ user.name }}</p>
<p v-else>Please sign in.</p>
```

The aliases `v-if`, `v-else-if`, and `v-else` can be mixed with normal HTML.

## Lists

Original Teloce API:

```html
<for each="item in items" :key="item.id">{{ item.name }}</for>
```

Compatibility API:

```html
<li v-for="item in items" :key="item.id">{{ item.name }}</li>
```

Use a stable `:key` whenever list items have an identity. The aliases also
support an index when needed:

```html
<li v-for="(item, index) in items">{{ index }}: {{ item.name }}</li>
```

## Events

Original Teloce API:

```html
<button @click="save">Save</button>
<form @submit.prevent="submit">...</form>
```

The `@event` form is the original shorthand. The equivalent npm-style form is:

```html
<button v-on:click="save">Save</button>
<form v-on:submit.prevent="submit">...</form>
```

Supported modifiers include `.prevent`, `.stop`, `.once`, `.self`, and key
modifiers such as `.enter` where applicable.

## Attributes and classes

Original Teloce API:

```html
<div :class="className" :show="visible" :title="title"></div>
```

Compatibility API:

```html
<div v-bind:class="className" v-show="visible" :title="title"></div>
```

The shorthand `:attribute` remains valid and is equivalent to
`v-bind:attribute`.

## Forms

Original Teloce API:

```html
<input :model="email" />
```

Compatibility API:

```html
<input v-model="email" />
```

Both forms keep the component state synchronized with the input value.

## Text and HTML

The compatibility aliases are:

```html
<p v-text="message"></p>
<div v-html="trustedHtml"></div>
```

`v-text` writes escaped text. `v-html` writes HTML and must only receive trusted,
sanitized content. Never pass raw user input to `v-html`.

## Transitions and animations

Use `transition:`, `in:`, `out:`, and `animate:` to animate elements on
enter, exit, and reorder. These have no npm/Vue equivalent in this doc's
compatibility table — they're a Teloce-native addition.

```html
<li v-for="item in items" :key="item.id"
    transition:fade="{ duration: 150 }"
    animate:flip>
  {{ item.text }}
</li>

<div v-if="showBanner"
     in:slide="{ axis: 'y', duration: 200 }"
     out:fade="{ duration: 100 }">
  Saved!
</div>
```

- `transition:name` runs the same animation on both enter and exit.
- `in:name` / `out:name` let enter and exit use different animations.
- `animate:flip` animates a `v-for` row to its new position when the list
  reorders (measured before the DOM update, applied after).
- Built-in helpers: `fade`, `slide` (`axis: 'x' | 'y'`), `scale`.
- Params are a JS-style object literal, e.g. `{ duration: 150, easing: 'ease-out' }`.

Only the helpers a component actually references are compiled into its
output — a component with no directives ships no transition code at all.

Custom transitions can be registered from the component's script:

```html
<script>
export default {
  transitions: {
    bounce(node, { duration = 300 } = {}) {
      return node.animate(
        [{ transform: "scale(0.9)" }, { transform: "scale(1)" }],
        { duration, easing: "cubic-bezier(.36,1.5,.64,1)" }
      );
    }
  }
};
</script>
```

then reference it the same way: `<div transition:bounce>`.

## Data and DOM directives

The following opt-in directives are implemented by the shared project runtime:

```html
<div v-virtual-for="row in rows" :key="row.id" item-height="40" overscan="5">{{ row.name }}</div>
<div v-memo="record.id + ':' + record.version">{{ record.title }}</div>
<div v-data-table="{ rows: rows, columns: columns, pageSize: 20 }"></div>
<section v-scrolly @step="active = $event.detail.name">
  <article v-step="intro">Intro</article>
</section>
<div v-chart-annotation="{ text: note, x: 50 }"></div>
<div poll="/api/summary" interval="10000" poll-target="summary"></div>
<div live="wss://example.test/events" live-target="latest"></div>
<input use:autofocus="{ select: true }">
```

`v-for` remains the compatible general-purpose loop. `v-virtual-for` uses a
fixed row-height estimate and stable `:key` to bound DOM work. `v-memo` skips
unchanged subtrees. `v-scrolly` observes `v-step` children and emits
`teloce:step`; `v-chart-annotation` creates an accessible overlay. `poll`
pauses while the page is hidden and retries safely. `live` supports WebSocket
URLs and named host adapters. `use:` actions receive a DOM node and must
return cleanup or `{ update, destroy }`. All of these are automatically
cleaned when the owning branch/component unmounts.

## Quick reference

| Feature | Original Teloce API | npm-style alias |
|---|---|---|
| Conditional rendering | `<if condition="ready">` | `v-if`, `v-else-if`, `v-else` |
| Lists | `<for each="item in items">` | `v-for="item in items"` |
| Events | `@click="save"` | `v-on:click="save"` |
| Bound attributes | `:class="classes"` | `v-bind:class="classes"` |
| Visibility | `:show="visible"` | `v-show="visible"` |
| Forms | `:model="email"` | `v-model="email"` |
| Text | interpolation or normal text | `v-text="message"` |
| HTML | — | `v-html="trustedHtml"` |
