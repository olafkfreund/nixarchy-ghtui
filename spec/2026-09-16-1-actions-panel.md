---
status: approved
issue: 1
intent: intent/2026-09-16-1-actions-panel.md
---
# Spec: GitHub Actions popup

## Design
A namespaced panel plugin with manifest.json and Panel.qml, hosted by omarchy-shell. Use qs.Commons Color/Style and qs.Ui BorderSurface. Grouped repository/run/job/step rows follow the screenshot, theme radius and spacing. Arrow keys or j/k move; Enter/right expands; left collapses; slash filters; r refreshes; Esc clears filtering or closes. No buttons.

Use a Python standard-library helper invoking gh api through argv for paginated active run summaries and selected-run jobs. Python is already installed. Include the ten most recent runs alongside active runs. QML Process runs asynchronously; a single request per process, timeouts, errors, backoff, no polling while closed. Repository configuration lives inline in shell.json. Default olafkfreund/nixarchy. No token extraction.

## Alternatives rejected
Embedding a terminal TUI cannot provide the native theme/layout contract. A web service, database and extra dependencies are unnecessary. Automatic discovery of every accessible repository would cause surprising API traffic; explicitly configured repositories define the monitored set.

## Risks
GitHub rate limits and unavailable authentication; preserve stale data and label errors. Step counts are not completion-time estimates. Logs are opened on GitHub rather than claiming live log streaming. Large run/job sets need pagination. Desktop session is 4.0.3 while installed package is 4.0.4; defer live activation until fresh login as required by nixarchy skill.

## Verification
Python unittest with fake API including pagination/errors; JS row/selection tests; real read-only GitHub requests; isolated Quickshell load when possible; review lifecycle and keyboard behavior. Live activation remains explicitly unverified until session mismatch resolves.

## Authorization
Covered by the user’s end-to-end implementation instruction recorded in intent.
