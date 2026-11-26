# Lesson 46: direct DOM behavior with `use:`

`use:` is a small escape hatch for behavior that needs the actual element.
An action can return a cleanup function or `{ update, destroy }`.

```html
<template><input use:autofocus="{ select: true }" placeholder="Name"></template>
<script>
function autofocus(node, params) {
  queueMicrotask(() => { node.focus(); if (params?.select) node.select(); });
  return { destroy() { node.blur(); } };
}
export default {};
</script>
```

An action with changing parameters can update without being recreated:

```html
<button use:tooltip="{ text: hint }">Help</button>
```

```js
function tooltip(node, params) {
  const tip = document.createElement("span");
  node.append(tip);
  const update = next => { tip.textContent = next?.text || ""; };
  update(params);
  return { update, destroy() { tip.remove(); } };
}
```

Keep actions small and clean every listener, observer, timer, and child node.
Never use an action to bypass Teloce's HTML sanitization for untrusted input.
