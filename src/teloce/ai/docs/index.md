# Teloce docs for AI assistants

These files are an offline copy of the Teloce-Py documentation, written for teloce-py @@TELOCE_VERSION@@. They live in
your project so an AI assistant can read them without internet access. Links to files that are not in this
folder point to the full online docs: https://github.com/aldanedev-create/teloce-py/tree/main/docs

Refresh the copies with `teloce ai-docs --force`. Do not edit them by hand.

## Which file for which task

| Task | Read |
| --- | --- |
| Quick syntax reminder | `cheatsheet.md` |
| Shape of a `.vel` file | `vel-syntax.md` |
| Template expressions, filters, events | `template-syntax.md` |
| Directives (complete list) | `directives.md` |
| Write a custom directive | `directive-contracts.md` |
| Components, props, slots, emits | `components.md` |
| State, computed values, watchers | `reactivity.md` |
| Pages and navigation | `router.md` |
| Requests, retries, caching, actions, sockets | `network-api.md` |
| Scrolling stories | `lesson-scrollytelling.md` |
| Live data and polling | `lesson-live-data.md` |
| Element behavior with `use:` | `lesson-use-actions.md` |
| CSV export and sharing | `lesson-sharing-and-exports.md` |
| Plugins | `plugins.md`, `first-party-plugins.md` |
| Server rendering and hydration | `ssr-and-hydration.md` |
| Security review | `security.md` |
| Deploying | `production.md` |
| Commands | `cli.md` |
| Something is broken | `known-issues.md`, then `troubleshooting.md` and `errors.md` |

## Reading order for a new feature

1. `cheatsheet.md` for the syntax.
2. The file for the specific feature from the table.
3. `known-issues.md` before you debug.
