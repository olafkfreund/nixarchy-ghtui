---
status: approved
issue: 57
intent: intent/2026-11-17-57-min-text-size.md
---

# Spec: keep fonts readable at the smallest text step

## Design

Add `fontPx(px, step)` to `ActionsModel.js`: `Math.max(Math.min(px, 9), zoomed(px, step))`. `fTitle`, `fBody` and `fCaption` in `ActionsPanel.qml` use it instead of `zoomed`. `sp()` keeps `zoomed`. The step range (70%–150%) and the "Text size N%" notice stay, so Ctrl+- still shrinks spacing and larger fonts.

## Alternatives rejected

- Stop the range at 80%: 10 px captions still become 8 px, and larger themes lose a useful step.
- Floor every `zoomed()` result: spacing would stop shrinking, which #48 wanted.

## Risks

A theme with fonts below 9 px is left as is (the floor never enlarges past the theme size). Row height uses `fBody + fCaption`, so rows stay tall enough for the floored text.

## Verification

`tests/model.cjs`: `fontPx(10,-3) === 9`, `fontPx(8,-3) === 8`, `fontPx(20,-3) === 14`, steps 0..5 equal `zoomed`, monotonic; a source check that the three font properties use `fontPx`. `nix flake check -L`, smoke test once.
