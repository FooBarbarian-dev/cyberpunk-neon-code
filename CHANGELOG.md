# Changelog

## 0.1.0 — 2026-08-18

Initial release.

- Dark theme "Cyberpunk Neon" ported from Roboron3042's Cyberpunk-Neon palette
  (role mapping shared with the Zed port).
- Full workbench coverage: editor, sidebar, activity/status/title bars, tabs,
  panel, terminal (verbatim ANSI table), lists, inputs, widgets, peek view,
  notifications, diff/merge, git decorations, minimap, breadcrumbs, bracket
  pair colorization, and the markdown-preview `text*` keys.
- TextMate `tokenColors` and mirrored `semanticTokenColors` so LSP-highlighted
  files match TextMate-highlighted ones.
- Opaque surfaces by policy (window transparency is GlassIt's job); alpha only
  on stacking decorations such as selections and highlights.
- `scripts/check_theme.py`: registry, alpha-policy, contrast, parity, and ANSI
  checks, with a `--selftest` that proves each rule can fail.
