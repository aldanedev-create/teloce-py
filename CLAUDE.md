# CLAUDE.md

@AGENTS.md

## Notes for Claude Code

- `AGENTS.md` is the source of truth for this repository. Keep rules there, not here.
- For a bug, reproduce it first (a failing test or a small app), then fix it, then show the test passing.
- Directive and runtime behavior is easy to get wrong from memory. Read the code in `src/teloce/runtime/compiled.js`
  and the matching doc in `docs/` before changing it.
- Run the narrowest tests first (`python -m pytest tests/<area> -q`), then the full suite.
- Ask before changing the public CLI, the file layout of generated projects, or the version number.
