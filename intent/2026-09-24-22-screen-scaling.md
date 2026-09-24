---
status: approved
issue: 22
author: olafkfreund
---

# Intent: The panel uses the theme's text size and fits the screen like the rest of the shell

## Problem

The panel does not look like the rest of the Omarchy shell. As the request
put it: "the text and the windows needs to follow the desktop size and
scale".

- Text uses a fixed `textScale: 1.5` on top of the theme font sizes
  (`ActionsPanel.qml:35`). The row heights follow it, so the panel looks
  oversized next to the other Omarchy menus, which use the theme sizes as
  they are.
- The divider under the header is a fixed `height: 1` rather than the
  theme's hairline.

Growing the panel and its text with the screen size was tried and rejected
in a live check. On a 2560×1440 screen the card was about 1330 px wide with
about 27 px body text, and the verdict was "way too big". The extra
multiplier is the problem, not a missing link to screen size.

Two things already carry through. Omarchy's `Style.space()` and
`Style.font.*` scale with the theme's base font size. Hyprland applies the
monitor scale itself, because layer-shell surfaces use logical pixels.

## Proposed outcome

- Text is exactly the Omarchy theme size, like the other menus. There is no
  extra 1.5× and no growth with screen size.
- Row heights follow the theme text size.
- The card is at most `Style.space(900)` × `Style.space(680)`. On smaller
  screens it shrinks to fit, keeping the existing gap to the screen edges
  (`Style.gapsOut`).
- The divider uses the theme's hairline (`Style.spacing.hairline`).
- Changing the theme's font size or the monitor scale still has the effect
  it has today.
- The README describes the panel's sizing as theme-sized text.

## Affected users and systems

- Everyone running the panel. The text and rows get smaller, down to the
  theme size.
- `ActionsPanel.qml`: `textScale`, row heights, the card size and the
  divider.
- `README.md`: the sizing sentence on line 3.
- `tests/qml-smoke.py`, which loads the panel.
- The screenshots and GIF in `docs/img/` show 1.5× text and will need
  retaking.

## Constraints

- Scale always follows the Omarchy theme and desktop: the theme font and
  spacing sizes (`Style` tokens) and the Hyprland monitor scale. The panel
  adds no scale factor of its own. As the request put it: "keep the scale
  always as the omarchy theme or omarchy desktop scale".
- Must keep using Omarchy's `Style` tokens and theme colours, fonts, border
  and corner radius. No hard-coded pixel sizes or fonts.
- Must still work on small screens and on multi-monitor setups with
  different sizes and scales.
- Must not break keyboard navigation (`/`, `l`/Enter, `h`, `o`, Esc) or the
  tests in `tests/qml-smoke.py`.
- Must not stop following the theme font size or the Hyprland monitor scale.

## Open questions

None.
