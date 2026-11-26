# Lesson 43: scrollytelling and chart annotations

`v-scrolly` observes child elements marked with `v-step`. The active step is
also exposed as `data-teloce-active-step`, and a `teloce:step` event bubbles
for application state.

```html
<template>
  <main v-scrolly @step="step = $event.detail.name">
    <article v-step="intro" tabindex="0">Introduce the finding.</article>
    <article v-step="peak" tabindex="0">Explain the peak.</article>
    <p>Current step: {{ step }}</p>
  </main>
</template>
<script>export default { data() { return { step: "intro" }; } };</script>
```

Add a library-independent callout to a chart container:

```html
<div class="chart" v-chart-annotation="{ text: 'Peak in July', x: 64, position: 'top' }"></div>
```

The annotation is an accessible `aside` overlay. Its `x` value is a percent
from the left; chart libraries still own drawing and scales. Provide a
fallback layout because IntersectionObserver is not available in every test
environment.
