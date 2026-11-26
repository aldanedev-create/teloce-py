# Components

Components can be imported locally and mounted by the generated entry module. Use `props` for inputs, `emits` for outputs, and slots for content supplied by the parent.

```html
<script>
import UserCard from "./components/UserCard.vel";
export default { components: { UserCard } };
</script>
<template><UserCard :user="user" /></template>
```

Keep reusable components small. Put server data access in Python endpoints and pass data through JSON or props rather than embedding secrets in browser code.

## Props

Props are inputs owned by the parent:

```html
<script>
export default {
  props: {
    title: { type: String, required: true },
    compact: { type: Boolean, default: false }
  }
};
</script>
```

Do not mutate a prop in the child. Copy it into local state when the child must
edit it, or emit an event and let the parent update the source of truth.

## Events and slots

```html
<button @click="$emit('select', user.id)">Select</button>
<slot></slot>
```

Use events for child-to-parent communication and slots for parent-provided
markup. Keep server mutations in explicit API calls so loading and error states
are visible in the UI.

## Import rules

Use relative local `.vel` imports. The builder resolves dependencies and
reports missing or escaping imports. Test an entry component and its imported
components together rather than compiling only the leaf component.
