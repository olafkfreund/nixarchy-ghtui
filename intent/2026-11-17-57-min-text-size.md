---
status: approved
issue: 57
author: olafkfreund
---

# Intent: keep fonts readable at the smallest text step

## Problem

#48's smallest step is 70% of the theme size. The theme's captions are 10 px, so the status line, subtitles and footer become 7 px, which is hard to read.

## Proposed outcome

At every text step, no font in the panel is smaller than 9 px, unless the theme's own size is already smaller. Bigger steps and the reset are unchanged.

## Affected users and systems

Everyone who uses Ctrl+- in the panel. `ActionsModel.js`, `ActionsPanel.qml`, tests, README.

## Constraints

Spacing and row sizes keep scaling as #48 decided; only font pixel sizes get the floor. No setting.

## Open questions

None. Owner chose "add a minimum size" on 2026-11-17 ("go with recommendations").
