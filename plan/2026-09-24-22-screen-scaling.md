---
status: approved
issue: 22
spec: spec/2026-09-24-22-screen-scaling.md
---

# Plan: The panel follows the screen size

## Approved decisions

- **One new property, `fit`, in `ActionsPanel.qml`**, next to `textScale`
  (`:35`). There are no new files, settings or dependencies. It is measured
  against the raw logical 900×680, not `Style.space()`, so it depends only on
  the screen, and the theme font size multiplies on top:

  ```qml
  // ponytail: one factor for the card, text and spacing; the reference is today's 900×680 card
  readonly property real fit: Math.max(1, Math.min(2,
      window.width * 0.6 / 900,
      window.height * 0.7 / 680))
  readonly property real textScale: 1.5 * fit
  ```

- **Screen size:** `window` is anchored on all four sides with
  `ExclusionMode.Ignore`, so `window.width` × `window.height` is the logical
  size of the monitor that `open()` picked. That is the size after
  Hyprland's monitor scale. There is no `ShellScreen` lookup and no physical
  pixels. While the window is hidden and has no size, `fit` is 1.
- **Share:** 60% of the width and 70% of the height, whichever runs out
  first. That keeps the 900:680 shape and caps the width on ultra-wide
  screens.
  - **Minimum:** 1, today's size.
  - **Maximum:** 2, which puts text at 3× the theme font.
  - **Expected sizes at the default 12 px `base-size`:**

  | Logical screen | `fit` | Card |
  | --- | --- | --- |
  | 1366×768 | 1 | clamped to the screen minus gaps, as today |
  | 1920×1080 (or 4K at scale 2) | 1.11 | 1000×756 |
  | 2560×1440, 3440×1440 | 1.48 | 1334×1008 |
  | 3840×2160 at scale 1 | 2 | 1800×1360 |

- **Card, with the clamp kept** (`:227-228`):

  ```qml
  width: Math.min(Style.space(900) * root.fit, window.width - Style.gapsOut * 2)
  height: Math.min(Style.space(680) * root.fit, window.height - Style.gapsOut * 2)
  ```

- **Text:** every `pixelSize` already uses `Style.font.* * root.textScale`
  (`:270, 278, 335, 344, 354, 365, 376, 385`), and the search field height
  follows its font (`:276`). These lines are unchanged.
- **Spacing inside the card:**
  - Every fixed `Style.space(n)` becomes `Style.space(n * root.fit)`. That
    covers the row heights (`:322`, `64`, `16`, `40`, `12`), the row margins
    and depth indent (`:327-328`, `8`, `18`, `8`), the icon column (`:331`,
    `18`) and its reserved width (`:338`, `26`).
  - The tokens become `Math.round(Style.spacing.X * root.fit)`:
    `panelPadding` (`:232`), `md` (`:265, :313`) and `sm` (`:329`).
- **Divider** (`:309`): `height: 1` becomes `height: Style.space(root.fit)`.
  That is the hairline grown by `fit`, and it is never below 1 px.
- **Unchanged:**
  - The border width (`:231`) and `Style.cornerRadius` (`:230`).
  - Keyboard handling.
  - Everything outside the card.
- **README line 3:** replace "Text uses 1.5× theme font sizes with matching
  row heights." with "The panel takes up to 60% of the screen's width and
  70% of its height, never smaller than 900×680 theme units where the screen
  allows; text, rows and spacing grow with it, from 1.5× up to 3× the theme
  font sizes."
- **Smoke assertion**, in `tests/qml-smoke.py` stage 1, while the panel is
  open:
  `check(panel.fit>=1 && panel.fit<=2 && panel.textScale===1.5*panel.fit,"screen fit bounded")`.
- **Screenshots in `docs/img/`:** retake them only if the manual check shows
  a visible difference at 1080p.

## Steps

1. `tests/qml-smoke.py`: add the assertion in the `stage===1` branch, after
   `check(...,"jobs and steps arrive")` → verify by running
   `python3 tests/qml-smoke.py`. It must fail with
   `CHECK FAILED: screen fit bounded`, because `fit` doesn't exist yet
   (red first).
2. `ActionsPanel.qml:35`: add `fit` and change `textScale` to `1.5 * fit`,
   exactly as in the decisions above → verify by running
   `python3 tests/qml-smoke.py`, which must print `QML_CHECKS_PASSED` for
   both scenarios.
3. `ActionsPanel.qml:227-228`: card width and height as above → verify by
   running the smoke test again: it passes and prints no binding-loop
   warnings.
4. `ActionsPanel.qml:232, 265, 313, 329`: `Math.round(Style.spacing.X * root.fit)`
   → verify by checking that `grep -n 'Style.spacing\.' ActionsPanel.qml`
   inside the card shows only the multiplied forms.
5. `ActionsPanel.qml:309, 322, 327-328, 331, 338`: the divider becomes
   `Style.space(root.fit)`, and each `Style.space(n)` becomes
   `Style.space(n * root.fit)` → verify by checking that
   `grep -n 'Style.space(' ActionsPanel.qml` shows every call inside the card
   multiplied by `root.fit`, except the border (`:231`). Then check that
   `grep -n 'height: 1\b' ActionsPanel.qml` finds nothing.
6. `README.md:3`: replace the sentence → verify by checking that
   `grep -c '1.5× theme font sizes with matching' README.md` prints `0`.
7. Run the full test list below → verify that everything is green.
8. Manual check on real monitors, driven with `hyprctl keyword monitor …`
   → verify against the table:
   - 1080p at scale 1: about 1000×756.
   - 1440p: about 1334×1008.
   - 4K at scale 1: 1800×1360, with body text about 36 px.
   - 4K at scale 2: the same as 1080p, and sharp.
   - Reopen on a monitor of a different size: the panel resizes to it.
   - Raise `base-size`: the text grows, and the card stays within the screen
     minus the gaps.
   - A laptop-sized screen: the panel fits with its gaps.
   - Keyboard navigation (`/`, `l`/Enter, `h`, `o`, Esc) still works.
   - Retake `docs/img/` only if 1080p looks visibly different.
9. Commit `feat: size the panel to the screen (#22)` with the code, test
   and README changes. Open a PR that links the intent, spec and plan.

## Tests

```sh
python3 -m unittest discover -s tests -p "test_*.py"   # OK, all pass (unchanged)
node tests/model.cjs                                    # exit 0 (unchanged)
node tests/polling.cjs                                  # exit 0 (unchanged)
python3 tests/qml-smoke.py                              # QML_CHECKS_PASSED for fresh and managed,
                                                        # including the new "screen fit bounded" check
nix flake check                                         # green
```

The new assertion fails before step 2 (red first) and passes after. The
smoke test runs `quickshell` on the live session, so it checks only the
monitor that runs it. The other resolutions and scales are covered by the
manual check in step 8.

## Rollback

- Revert the `feat:` commit, or don't merge the PR. The change is limited to
  `ActionsPanel.qml`, `README.md` and `tests/qml-smoke.py`, with no state,
  settings or migrations.
- Installed users: update to the previous revision and restart the Omarchy
  shell (`omarchy-restart-shell`), because a `keepLoaded` panel isn't
  reloaded by disable and enable.
