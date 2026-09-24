---
status: draft
issue: 22
author: olafkfreund
---

# Intent: The panel follows the screen size, not only the theme font size

## Problem

The panel's size and text do not change with the screen they open on. In
your words: "the text and the windows needs to follow the desktop size and
scale".

- `ActionsPanel.qml` caps the card at `Style.space(900)` × `Style.space(680)`
  and only shrinks it when the screen is smaller than that.
- Text uses a fixed `textScale: 1.5` on top of the theme font sizes.
- The divider under the header is a fixed `height: 1`.

Two things already carry through. Omarchy's `Style.space()` and
`Style.font.*` scale with the theme's base font size, and Hyprland applies
the monitor scale itself, because layer-shell surfaces use logical pixels.
Only the screen's size is ignored. On a large or high-resolution display the
panel stays 900 × 680 units in the middle of the screen, and the text never
grows with it. The README says the same: "Text uses 1.5× theme font sizes
with matching row heights".

## Proposed outcome

- On a large display the panel takes up a similar share of the screen as it
  does on a laptop, instead of a small fixed box in the middle.
- Text, row heights, padding and the divider grow and shrink with the panel,
  so the proportions look the same on every screen.
- On a small screen the panel still fits, with its gaps, and stays readable.
- Opened on a different monitor, the panel sizes itself to that monitor.
- Changing the theme's font size or the monitor scale still has the effect it
  has today.
- The README describes how the panel sizes itself.

## Affected users and systems

- Anyone running the panel, most visibly on large or high-resolution
  monitors and on multi-monitor desktops with different sizes.
- `ActionsPanel.qml`: card size, `textScale`, row heights and the divider.
- `README.md`: the sizing sentence on line 3.
- `tests/qml-smoke.py`, which loads the panel.
- The screenshots and GIF in `docs/img/` may need retaking if the panel looks
  noticeably different.

## Constraints

- Must keep using Omarchy's `Style` tokens and theme colours, fonts, border
  and corner radius. No hard-coded pixel sizes or fonts.
- Must still work on small screens and on multi-monitor setups with
  different sizes and scales.
- Must not break keyboard navigation (`/`, `l`/Enter, `h`, `o`, Esc) or the
  tests in `tests/qml-smoke.py`.
- Must not stop following the theme font size or the Hyprland monitor scale.

## Open questions

1. How much of the screen should the panel take: a fixed share such as about
   half the width and two thirds of the height, or the current size scaled by
   screen size against a reference screen?
2. Should text scale with the panel, stay tied to the theme font size as now,
   or become a user setting, for example an environment variable or a menu
   option?
3. Are there minimum and maximum sizes? For example, never smaller than
   today's panel where the screen allows it, and never larger than a certain
   share on ultra-wide monitors.
4. Which size counts on a scaled monitor: the logical size Hyprland reports
   after scaling, or the physical resolution?
