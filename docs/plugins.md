# Plugins, filters, and directives

Plugins extend compilation or the browser runtime. A plugin can register components, filters, helpers, directives, AST transforms, or lifecycle hooks.

Filters are useful for presentation transformations:

```html
<p>{{ price | currency }}</p>
```

Keep security-sensitive work in Python. A browser plugin must not contain secrets, and a compiler plugin should be deterministic so CI and local builds produce the same output.

When migrating from npm, port Node-only plugin code to the Python plugin API or expose a browser-only helper with the same public behavior.

## Plugin design rules

- make transforms deterministic;
- validate options and report source locations;
- avoid network access and secrets during compilation;
- keep browser plugins small and tree-shakable where possible;
- document whether a plugin runs during Python compilation or in the browser;
- add a fixture `.vel` file and a browser test for every public feature.

Filters should be presentation helpers, not authorization or data-access
functions. Directives should define how they transform or bind DOM behavior.
Components registered by a plugin should follow the same props and event
contract as local components.

## Optional first-party modules

See [First-party plugins](first-party-plugins.md) for Forms, PWA, internationalization,
accessibility and Head/SEO configuration, APIs, Flaxon setup and other framework integration.
