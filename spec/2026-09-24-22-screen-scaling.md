---
status: draft
issue: 22
intent: intent/2026-09-24-22-screen-scaling.md
---

# Spec: The panel uses the theme's text size and fits the screen like the rest of the shell

## Design

The panel gets no scale factor of its own. `textScale` is deleted, not set
to 1, and nothing replaces it. Every size comes from Omarchy's `Style` tokens,
which follow the theme's `base-size` and `[spacing] scale`. Hyprland applies
the monitor scale to the layer-shell surface. There are no new files,
properties, settings or dependencies.

Line numbers refer to `origin/main`'s `ActionsPanel.qml`. This branch's
earlier code commit (08b50ff, `fit`) is reverted first. Its smoke assertion
goes with it.

**Delete** `readonly property real textScale: 1.5` (`:35`).

**Text: the theme size, as is.** Each `pixelSize: Math.round(Style.font.X * root.textScale)`
becomes `pixelSize: Style.font.X`. `Style.font.*` values are already integers,
so there's no rounding.

| Line | Element | New `pixelSize` |
| --- | --- | --- |
| `:270` | header | `Style.font.title` |
| `:278` | search field | `Style.font.caption` |
| `:335` | row status icon | `Style.font.body` |
| `:344` | row title | `Style.font.body` |
| `:354` | row subtitle | `Style.font.caption` |
| `:365` | row info | `Style.font.caption` |
| `:376` | empty-list message | `Style.font.body` |
| `:385` | footer | `Style.font.caption` |

The search field height (`:276`, `Math.ceil(font.pixelSize * 1.4)`) follows
its font and is unchanged.

**Row heights: theme text plus theme spacing** (`:322`). Only the `textScale`
multipliers go:

```qml
height: modelData.subtitle ? Math.max(Style.space(64), Style.font.body + Style.font.caption + Style.space(16)) : Math.max(Style.space(40), Style.font.body + Style.space(12))
```

`Style.space()` scales with the theme font (`spacingScaleWithFont`), so the
minimums grow and shrink with `base-size` too. This is the same pattern as
Omarchy's own menu: `Math.max(Style.space(58), Style.font.body + Style.font.caption + …)`
in `shell/plugins/menu/Menu.qml:103`.

**Card: today's expression, unchanged** (`:227-228`):

```qml
width: Math.min(Style.space(900), window.width - Style.gapsOut * 2)
height: Math.min(Style.space(680), window.height - Style.gapsOut * 2)
```

At most 900×680 theme units. On smaller screens it shrinks to the logical
screen size minus the theme's edge gap. `window` is anchored on all four
sides, so its size is the logical size of the monitor `open()` picked. That
covers different monitors and scales without further code.

**Divider** (`:309`): `height: 1` becomes `height: Style.spacing.hairline`,
as Omarchy's menu divider does (`Menu.qml:1195`).

**Unchanged:** the padding, spacing tokens, margins and icon column
(`:232, 265, 313, 327-331, 338`), which are already `Style` tokens without
`textScale`. The border and corner radius are unchanged too, and so is the
keyboard handling.

**README line 3.** Replace "Text uses 1.5× theme font sizes with matching row
heights." with: "Text, rows and spacing use the theme's sizes, like the other
Omarchy menus, and the panel shrinks to fit smaller screens."

## Alternatives rejected

- **Growing the panel with the screen** (the previous design: up to 60% ×
  70% of the screen, text 1.5–3× the theme). This was built and checked live.
  On 2560×1440 the card was about 1330 px wide with about 27 px body text,
  and the verdict was "way too big". It also adds a scale factor of the
  panel's own, which the intent now rules out.
- **Keeping the 1.5× text multiplier.** That is the oversized look this issue
  is about. It is a scale factor the rest of the shell doesn't apply.
- **A user setting (environment variable or menu option) for text or panel
  scale.** This breaks the constraint "keep the scale always as the omarchy
  theme or omarchy desktop scale". The theme's `base-size` and
  `[spacing] scale` and the Hyprland monitor scale are the controls, and they
  apply to every Omarchy surface at once.
- **Setting `textScale` to 1 instead of deleting it.** That keeps a knob
  nobody should turn and eight multiplications that do nothing.
- **Copying Omarchy's menu row minimums (58/50) as well.** That changes the
  row layout beyond the scale fix. The current 64/40 minimums already follow
  the theme through `Style.space()`. Revisit only if the live look shows rows
  too tall.

## Risks

- **Smaller text for existing users.** With the default 12 px `base-size`,
  body text drops from 18 to 12 px and the header from 21 to 14 px. That is
  intended and matches the other menus. Users who want larger text raise the
  theme's `base-size`, which enlarges every Omarchy surface.
- **Rows may look roomy.** With the default theme, the 64/40 minimums apply,
  since 12 + 10 + 16 < 64. They were set when the text was 1.5×. The live
  check decides whether that is acceptable (see the last alternative).
- **Outdated screenshots.** The screenshots and GIF in `docs/img/` and the
  README's Screenshots section show 1.5× text. **Recommendation: retake them
  in a follow-up issue, not in this PR.** Capturing follows the #20 process
  on razer: ai-mirror control, OCR privacy gate, WebP and GIF encoding. That
  is a separate, larger change than this few-line fix. The PR description
  says the images predate it. The follow-up also covers nixarchy's copies
  (`docs/img/plugins/github-actions-*`) and its flake pin.
- **Text and card no longer grow together.** The card keeps its 900×680
  maximum while the text shrinks, so more rows fit. There is no clipping
  risk: the card was sized for larger text.

## Verification

- **New smoke assertion** in `tests/qml-smoke.py`, in the first `Timer`
  (panel loaded, before `open`):
  `check(panel.textScale===undefined,"no panel scale factor")`.
  **Red first:** on `origin/main`'s code `textScale` is `1.5`, so the check
  fails with `CHECK FAILED: no panel scale factor`. It passes once the
  property is deleted. Any leftover `root.textScale` reference would also
  raise a `TypeError`/`ReferenceError` warning, which the smoke test already
  fails on.
- **Full suite, all green:**

  ```sh
  python3 -m unittest discover -s tests -p "test_*.py"
  node tests/model.cjs
  node tests/polling.cjs
  python3 tests/qml-smoke.py          # QML_CHECKS_PASSED for fresh and managed
  nix flake check
  ```

- **Grep:** `grep -n textScale ActionsPanel.qml` prints nothing, and
  `grep -n 'height: 1\b' ActionsPanel.qml` prints nothing.
- **Live look, by the user**, on the 2560×1440 and 1920×1080 monitors:
  - The text matches the Omarchy menu, side by side.
  - The card is at most 900×680 theme units and centred.
  - Reopening on the other monitor sizes it correctly.
  - Keyboard navigation (`/`, `l`/Enter, `h`, `o`, Esc) works.
  - Row height is acceptable.
