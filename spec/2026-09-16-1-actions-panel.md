---
status: approved
issue: 1
intent: intent/2026-09-16-1-actions-panel.md
---
# Spec: GitHub Actions popup

## Design
A namespaced panel plugin with manifest.json and ActionsPanel.qml, hosted by omarchy-shell. Use qs.Commons Color/Style and qs.Ui BorderSurface. Grouped repository/run/job/step rows follow the screenshot, theme radius and spacing. Arrow keys or j/k move; Enter/right expands; left collapses; slash filters; r refreshes; Esc clears filtering or closes. No buttons.

Use a Python standard-library helper invoking gh api through argv for paginated active run summaries and selected-run jobs. Python is already installed. Include the ten most recent runs alongside active runs. QML Process runs asynchronously; a single request per process, timeouts, errors, backoff, no polling while closed. Repository discovery uses authenticated GitHub API pagination; legacy inline shell.json repositories are startup hints only. No token extraction.

## Alternatives rejected
Embedding a terminal TUI cannot provide the native theme/layout contract. A web service, database and extra dependencies are unnecessary. Scanning every run status on every repository would use too many API calls; incrementally scan in-progress runs, then fetch complete summaries on selection.

## Risks
GitHub rate limits and unavailable authentication; preserve stale data and label errors. Step counts are not completion-time estimates. Logs are opened on GitHub rather than claiming live log streaming. Large run/job sets need pagination. Desktop session is 4.0.3 while installed package is 4.0.4; the user explicitly authorized live testing anyway. Clear stale component caches before verifying the installed update.

## Verification
Python unittest with fake API including pagination/errors; JS row/selection tests; real read-only GitHub requests; isolated Quickshell load when possible; review lifecycle and keyboard behavior. Verify the installed plugin through shell IPC in addition to isolated tests.

## Authorization
Covered by the user’s end-to-end implementation instruction recorded in intent.

## Revised design for #3

Automatic, paginated GET /user/repos discovery through existing gh authentication replaces the explicit monitored-list scope. Include owner, collaborator and organisation-member affiliations visible to the token. Keep archived/disabled repositories searchable without polling them. No PAT extraction/storage. A filtered token cannot reveal repositories it lacks access to.

List repositories immediately; check one repository’s paginated in-progress workflow runs every two seconds after completion. Round-robin traversal starts with GitHub’s pushed-descending catalogue, with periodic rechecks of known active repositories. Show checked/total progress, unknown state for unchecked repositories, permission errors per repository and rate/network backoff. Sort running repositories first without changing the selected row’s identity. Fetch complete active/recent run summaries only for the selected repository, then selected-run jobs. Retain catalogue/activity in a keepLoaded panel with zero polling while closed. Reopening after five minutes refreshes access; Shift+R refreshes it immediately.

Use 1.5 times native theme font sizes and adequate row heights. Consume stdout/stderr at process exit through a shared response helper, report empty-output startup failures, and avoid cancelling/restarting the first request during configuration loading. Rename QML/model entry files to ActionsPanel.qml/ActionsModel.js; this session still required a full shell restart to clear its component/file cache.
