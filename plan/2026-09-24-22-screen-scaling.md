---
status: approved
issue: 22
spec: spec/2026-09-24-22-screen-scaling.md
---

# Plan: The panel uses the theme's text size and fits the screen like the rest of the shell

## Approved decisions

- **No scale factor of the panel's own.** Sizes come only from Omarchy's
  `Style` tokens (the theme's `base-size` and `[spacing] scale`) and
  Hyprland's monitor scale. There are no new files, properties, settings or
  dependencies.
- **Starting point:** `origin/main`'s code. The earlier code commit 08b50ff
  (`fit`, screen-share growth, rejected live as "way too big") is reverted,
  together with its smoke assertion. All line numbers below are
  `origin/main`'s `ActionsPanel.qml`.
- **Delete** `readonly property real textScale: 1.5` (`:35`). Don't set it
  to 1.
- **Text:** `pixelSize: Math.round(Style.font.X * root.textScale)` becomes
  `pixelSize: Style.font.X`. The search field height (`:276`) follows its
  font and is unchanged.

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

- **Row heights** (`:322`):

  ```qml
  height: modelData.subtitle ? Math.max(Style.space(64), Style.font.body + Style.font.caption + Style.space(16)) : Math.max(Style.space(40), Style.font.body + Style.space(12))
  ```

- **Card is unchanged** (`:227-228`). At most 900×680 theme units, shrinking
  to the screen minus the theme's edge gap:

  ```qml
  width: Math.min(Style.space(900), window.width - Style.gapsOut * 2)
  height: Math.min(Style.space(680), window.height - Style.gapsOut * 2)
  ```

- **Divider** (`:309`): `height: 1` becomes `height: Style.spacing.hairline`.
- **Unchanged:**
  - The padding, spacing tokens, margins and icon column
    (`:232, 265, 313, 327-331, 338`).
  - The border and corner radius.
  - The keyboard handling.
- **README line 3:** replace "Text uses 1.5× theme font sizes with matching
  row heights." with "Text, rows and spacing use the theme's sizes, like the
  other Omarchy menus, and the panel shrinks to fit smaller screens."
- **Smoke assertion**, in `tests/qml-smoke.py`'s first `interval: 1000`
  Timer, after the "active Omarchy theme" check:
  `check(panel.textScale===undefined,"no panel scale factor")`.
- **Screenshots:** the images in `docs/img/` and nixarchy's copies are
  retaken in a follow-up issue, not in this PR. Recapturing follows the #20
  razer process. The PR description says the images predate the change.
- **Row minimums** 64/40 stay. Copying Omarchy's 58/50 is only revisited if
  the live look finds rows too tall.

## Steps

1. `git revert --no-edit 08b50ff` → verify that
   `git diff origin/main -- ActionsPanel.qml README.md tests/qml-smoke.py`
   is empty.
2. `tests/qml-smoke.py`: add the assertion → verify that
   `python3 tests/qml-smoke.py` fails with
   `CHECK FAILED: no panel scale factor` (red first).
3. `ActionsPanel.qml:35`: delete `textScale`. At `:270, 278, 335, 344, 354,
   365, 376, 385`, set `pixelSize: Style.font.X` as in the table → verify
   that `grep -n textScale ActionsPanel.qml` prints only the `:322` row
   height, which step 4 removes.
4. `ActionsPanel.qml:322`: the row height expression above → verify that
   `grep -n textScale ActionsPanel.qml` prints nothing.
5. `ActionsPanel.qml:309`: `height: Style.spacing.hairline` → verify that
   `grep -nE 'height: 1\b' ActionsPanel.qml` prints nothing.
6. `README.md:3`: replace the sentence → verify that
   `grep -c '1.5× theme font sizes' README.md` prints `0`.
7. Run the full test list below → verify that everything is green and the
   smoke test prints `QML_CHECKS_PASSED` twice. Commit
   `fix: use the theme's text size in the panel (#22)`. The revert from step
   1 is its own commit.
8. **STOP.** The lead runs the live check with the user on the 2560×1440 and
   1920×1080 monitors → verify that:
   - The text matches the Omarchy menu side by side.
   - The card is at most 900×680 theme units and centred.
   - Reopening on the other monitor sizes it correctly.
   - Keyboard navigation (`/`, `l`/Enter, `h`, `o`, Esc) works.
   - Row height is acceptable.

   If the rows are too tall, update the spec and this plan before changing
   the code.
9. Open a follow-up issue: "Retake screenshots and GIF at theme text size",
   covering `docs/img/` here and nixarchy's `docs/img/plugins/github-actions-*`
   and its pin → verify that the issue URL exists.
10. Push `feat/22-screen-scaling` and open a PR linking the intent, spec and
    plan, closing #22 and naming the follow-up issue for the outdated images
    → verify that the PR URL exists and its checks are green.

## Tests

```sh
python3 -m unittest discover -s tests -p "test_*.py"   # "OK", 23 tests
node tests/model.cjs                                    # exit 0, "Model: … passed"
node tests/polling.cjs                                  # exit 0
python3 tests/qml-smoke.py                              # exit 0, QML_CHECKS_PASSED ×2 (fresh, managed),
                                                        # no CHECK FAILED / TypeError / ReferenceError
nix flake check                                         # "all checks passed!"
grep -n textScale ActionsPanel.qml                      # no output
grep -nE 'height: 1\b' ActionsPanel.qml                 # no output
```

Before step 3, the smoke test fails with `CHECK FAILED: no panel scale
factor`. After step 7 it passes.

## Rollback

- Before the push: `git revert` the `fix:` commit. Its test and README
  changes go with it. The artifacts stay.
- After a merge: revert the merge commit. There is no state, setting or
  migration.
- Installed users update to the previous revision and run
  `omarchy-restart-shell`, because a `keepLoaded` panel isn't reloaded by
  disable and enable.
