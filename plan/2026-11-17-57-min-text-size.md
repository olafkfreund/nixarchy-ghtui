---
status: approved
issue: 57
spec: spec/2026-11-17-57-min-text-size.md
coders:
  1: session   # two lines of code and their tests; below the handoff threshold
reviewers:
  - codex      # read-only review of the diff
---

# Plan: keep fonts readable at the smallest text step

Approved by the owner's standing pre-approval and "go with recommendations" (2026-11-17).

## Steps

1. `ActionsModel.js` after `zoomed()`: add `fontPx(px, step)` = `Math.max(Math.min(px, 9), zoomed(px, step))`. `ActionsPanel.qml:43-45`: `fTitle`/`fBody`/`fCaption` call `Model.fontPx`. `tests/model.cjs` text size block: cases from the spec. `README.md:142`: note the 9 px floor. → verify by `node tests/model.cjs`.
   Traps: `sp()` keeps `zoomed`; `ActionsModel.js` and `Polling.js` are never loaded into one vm context.
2. Session: `nix flake check -L`, `python3 tests/qml-smoke.py` once, Codex review, PR.

## Tests

`node tests/model.cjs && node tests/polling.cjs && python3 -m unittest tests/test_actions.py tests/test_menu.py`; `nix flake check -L`.

## Rollback

Revert the PR; fonts go back to plain `zoomed`.
