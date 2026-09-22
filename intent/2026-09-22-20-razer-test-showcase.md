---
status: approved
issue: 20
author: olafkfreund
---

# Intent: Test the panel on razer, fix what breaks, and show it off

## Problem

The GitHub Actions panel has unit tests (`tests/test_actions.py`,
`tests/test_menu.py`, `tests/*.cjs`) and a QML smoke test, but nobody has
driven it end to end on a real, authenticated Nixarchy desktop. Any bugs in
keyboard navigation, drill-down (repositories → runs → jobs → steps),
search, polling, the menu entry or the keybindings have not been recorded.

There are also no images of the panel anywhere:

- This repository's README has no screenshots. It has no GitHub Pages site,
  so the README is its public page.
- The GitHub Actions section of the nixarchy site
  (`olafkfreund/nixarchy` `docs/manual/plugins.md`, served at
  https://olafkfreund.github.io/nixarchy/manual/plugins) has no screenshots.
  Its note says the panel was left out because, unauthenticated, it only
  shows a static message.

A new user can't see what the panel does or how to use it before
installing it.

## Proposed outcome

- A written list of the bugs found on razer, one issue each or one checklist
  in #20, each with how to reproduce it, and each fixed or explicitly
  deferred.
- Fixes merged here with tests where the logic allows.
- Current screenshots of the main views, plus a short showcase recording that
  opens the panel, searches, drills into a run to its steps, and goes back.
- The README shows them.
- The nixarchy plugins page shows them, and the "Not shown moving" note is
  replaced.

## Affected users and systems

- Host **razer**, driven remotely through ai-mirror. This session runs on
  p620, so you have to grant control on razer.
- Your `gh` account on razer. Screenshots will show real repository names
  and workflow runs.
- This repository: plugin code, tests and README.
- `olafkfreund/nixarchy`: `docs/manual/plugins.md`, `docs/img/plugins/`, and
  possibly the flake input pin for `nixarchy-ghtui`. That repo needs its own
  issue, branch and PR.

## Constraints

- You must be able to take control back at any time. If control is
  revoked, stop and don't retry.
- Testing must not change anything on GitHub. The panel only reads, so no
  re-runs, cancellations or other writes.
- No tokens, private repository names you don't want public, or
  notifications may appear in published images.
- Fixes are declarative. No imperative installs on razer.
- Image sizes follow the existing nixarchy docs conventions (JPEG/GIF under
  `docs/img/plugins/`).

## Open questions

1. Is the razer desktop running the ghtui version from `main`, or should
   I switch it to this branch while testing fixes?
2. Which account or repositories can appear in the screenshots? Your real
   ones, or a public demo org or repository with active workflows?
3. Should the showcase be a GIF, like the other plugins on the nixarchy
   site, or also a video, such as WebM or MP4?
4. For the nixarchy site, should I update the `nixarchy-ghtui` flake pin in
   the same PR, or only the docs?
