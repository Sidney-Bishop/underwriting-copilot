# CLAUDE.md

Claude-specific layer. The shared, tool-agnostic instructions live in
`AGENTS.md`; this file imports them and adds anything Claude-only.

@AGENTS.md

<!--
Claude Code extras you can add here (not supported by the AGENTS.md standard):
  - @docs/architecture.md      # pull in extra context on demand
  - path-scoped rules via frontmatter, e.g. rules that only apply in src/
As of 2026-06-17, Claude Code does not read AGENTS.md natively, hence this shim.
If that changes, this file can be reduced to just the @AGENTS.md import or
replaced with a symlink.
-->
