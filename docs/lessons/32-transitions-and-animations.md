# Lesson 32: Transitions and animation directives

Teloce-Py can animate elements as they enter, exit, and reorder without a
JavaScript animation library. Four directives cover this:

- `transition:name` — same animation on enter and exit.
- `in:name` / `out:name` — different animations for enter and exit.
- `animate:flip` — animates a `v-for` row to its new position when a list
  reorders.

These compile through the normal `.vel` -> compiler -> served JavaScript
path from [Lesson 1](01-first-vel.md). There is nothing extra to install or
configure, and a component that never uses these directives ships none of
the animation code — the compiler only inlines the helpers a component
actually references.

## A banner that slides in and fades out

```html
<!-- static/js/App.vel -->
<template>
  <main class="page">
    <button @click="showBanner = !showBanner">Toggle banner</button>

    <div v-if="showBanner"
         in:slide="{ axis: 'y', duration: 200 }"
         out:fade="{ duration: 100 }">
      Saved!
    </div>
  </main>
</template>

<script>
export default {
  data() {
    return { showBanner: false };
  }
};
</script>

<style scoped>
.page { max-width: 32rem; margin: 3rem auto; font: 1rem system-ui; }
</style>
```

`in:slide` runs when the `<div>` is inserted (`showBanner` becomes true).
`out:fade` runs when it's removed (`showBanner` becomes false) — the
compiled runtime keeps a clone of the element in place just long enough for
the fade to finish before actually detaching it, so the exit is visible
instead of instant.

## Animating a reordering list

`animate:flip` pairs naturally with `v-for` and a stable `:key`:

```html
<template>
  <ul>
    <li v-for="item in sortedItems" :key="item.id"
        transition:fade="{ duration: 150 }"
        animate:flip>
      {{ item.text }}
    </li>
  </ul>
  <button @click="sortedItems = [...sortedItems].sort((a, b) => a.text.localeCompare(b.text))">
    Sort A-Z
  </button>
</template>

<script>
export default {
  data() {
    return {
      sortedItems: [
        { id: 1, text: "Bananas" },
        { id: 2, text: "Apples" },
        { id: 3, text: "Cherries" }
      ]
    };
  }
};
</script>
```

`transition:fade` animates rows in and out when the list gains or loses
items. `animate:flip` measures each row's position before the reorder and
animates it to its new position after, instead of letting rows jump.

## Built-in helpers and params

| Helper | What it does | Params |
| --- | --- | --- |
| `fade` | Animates opacity 0 → 1 | `duration`, `easing` |
| `slide` | Slides in from an offset while fading | `axis` (`'x'` \| `'y'`), `distance`, `duration`, `easing` |
| `scale` | Scales up from a smaller size while fading | `start`, `duration`, `easing` |
| `flip` (via `animate:flip`) | Animates a reordered element from its old position to its new one | `duration`, `easing` |

Params are a plain JS-style object literal, not JSON — unquoted keys and
single-quoted strings are both fine:

```html
<div transition:slide="{ axis: 'x', duration: 250, easing: 'ease-out' }">
```

Omit params entirely for the defaults: `<div transition:fade>`.

## Custom transitions

Define your own animation in the component's `<script>` block and reference
it by name the same way as a built-in:

```html
<template>
  <div v-if="open" transition:bounce>Menu</div>
</template>

<script>
export default {
  data() { return { open: false }; },
  transitions: {
    bounce(node, { duration = 300 } = {}) {
      return node.animate(
        [{ transform: "scale(0.85)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
        { duration, easing: "cubic-bezier(.36,1.5,.64,1)", fill: "forwards" }
      );
    }
  }
};
</script>
```

A transition function receives the DOM node and the parsed params object,
and should return the `Animation` object from `node.animate(...)` (or
`undefined`/`null` if it doesn't animate) so the runtime knows when an exit
animation has finished.

## Beginner project: a Flask todo list with animated rows

```text
todo-transitions/
├── app.py
├── templates/index.html
└── static/js/App.vel
```

```bash
python -m pip install Flask teloce-py
```

`static/js/App.vel`:

```html
<template>
  <main class="app">
    <h1>Todo</h1>
    <form @submit.prevent="add">
      <input v-model="draft" placeholder="New task" />
      <button type="submit">Add</button>
    </form>
    <ul>
      <li v-for="task in tasks" :key="task.id"
          transition:fade="{ duration: 150 }"
          animate:flip>
        <span>{{ task.text }}</span>
        <button @click="remove(task.id)">Done</button>
      </li>
    </ul>
  </main>
</template>

<script>
export default {
  data() {
    return { draft: "", tasks: [], nextId: 1 };
  },
  methods: {
    add() {
      if (!this.draft.trim()) return;
      this.tasks = [...this.tasks, { id: this.nextId++, text: this.draft.trim() }];
      this.draft = "";
    },
    remove(id) {
      this.tasks = this.tasks.filter((task) => task.id !== id);
    }
  }
};
</script>

<style scoped>
.app { max-width: 28rem; margin: 3rem auto; font: 1rem system-ui; }
li { display: flex; justify-content: space-between; padding: .4rem 0; }
</style>
```

`templates/index.html`:

```html
<main id="app"></main>
<script type="module">
  import { mount } from '/static/js/App.js';
  mount('#app');
</script>
```

`app.py`:

```python
from pathlib import Path
from flask import Flask, render_template
from teloce.build import build_project

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder="dist/static", static_url_path="/static")


@app.get('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    build_project(ROOT, options={'dev': True, 'source_maps': True})
    app.run(debug=True, port=5000)
```

Run `python app.py` and open `http://127.0.0.1:5000`. Adding a task fades a
new row in; marking one done fades it out; the remaining rows slide (FLIP)
into their new positions.

## Production notes

- Prefer `transform`/`opacity` animations (what `fade`/`slide`/`scale`/`flip`
  already use) — they run on the compositor and avoid layout thrash, unlike
  animating `width`/`height`/`top`/`left` directly.
- Keep durations short (100–250ms) for UI feedback; longer animations read
  as sluggish rather than polished.
- Respect `prefers-reduced-motion` for custom transitions by checking
  `window.matchMedia('(prefers-reduced-motion: reduce)').matches` inside the
  transition function and skipping or shortening the animation.
- `animate:flip` measures every managed child on each patch of that parent.
  For very large lists (hundreds of rows reordering together), profile
  before shipping — batch state updates so reorders happen once per user
  action, not once per item.
- Don't rely on `out:`/`transition:` exit animations to gate real work
  (saving data, navigation) — they're visual only. Await the actual
  operation before triggering the state change that starts the exit.