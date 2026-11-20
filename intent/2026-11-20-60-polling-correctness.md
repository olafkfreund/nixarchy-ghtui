---
status: draft
issue: 60
author: olafkfreund
---

# Intent: Port the polling correctness fixes from nixarchy-gltui #21

## Problem

nixarchy-gltui fixed thirteen correctness bugs in its #21 (PR #23,
v1.0.1). This plugin shares most of that polling and model code, but the
copies have drifted, so nobody knew which bugs it still has. Issue #60
names eight to check. A read of the current code on `main` (`7b6f6f5`)
gives:

| # | Bug | Here today |
|---|---|---|
| 1 | A stage named `constructor`, `__proto__` or `toString` crashes stage grouping | Not applicable: there is no stage grouping, keys always carry a prefix (`Polling.js` `key`, `ActionsModel.js` `"repo:"`), and label lookups use `hasOwnProperty` |
| 2 | A job list saved as final while it mixes two run attempts | **Present.** `invalidateJobs` (`Polling.js` 197-203) deletes the cached jobs on an attempt change, but an in-flight multi-page jobs task keeps merging pages into `t.items` and stamps the result with the new `run_attempt` (lines 353, 394-397) |
| 3 | The server's running total overwritten by a smaller local count | **Present.** A single-run reply sets `r.active` to the local in-progress count (line 338), replacing the total from the activity page (lines 254, 379); the row then shows too few running |
| 4 | `r` does not cut short a retry wait | **Partly fixed.** `manual()` already moves a backing-off task's `due` to now (ghtui #41). Missing: a task already in flight when `r` is pressed is not re-run after its reply. ghtui #41 deliberately kept the failure count (its plan step 5) |
| 5 | Polling follows a row no longer highlighted | Already fixed: `adopt()` always calls `selectionChanged` (`ActionsPanel.qml` 240-241) |
| 6 | Job caches never freed | **Mostly fixed** by ghtui #41's `prune()`. Gap: a single-run reply that drops a completed run from the list (`Polling.js` 335-337) does not prune its jobs until the next activity or summary reply |
| 7 | The scheduler re-sorts every project ten times a second while idle | **Present.** `next()` calls `seed()`, which sorts every repo, on each 100 ms pump tick (`Polling.js` 163, 127; `ActionsPanel.qml` 418) |
| 8 | A busy flag left stuck when handling a reply throws | **Present.** `requestProc.onExited` clears `workerBusy` after `receivePage` without `finally` (`ActionsPanel.qml` 424-428); `failedToStart` has the same shape. The action path already uses `try/finally` |

Of the other gltui #21 items, one applies and is present: `menu.py`
(line 97) checks the `menu.managed` marker with `.exists()`, which is
false for a dangling symlink, so registration writes the user's menu
file when nixarchy manages it. The rest do not apply (GitLab-only
statuses, the host switch) or were decided differently here by ghtui #41
(the catalogue stop until `r`/`R`/reopen; stale queued runs corrected
only for the selected repository).

## Proposed outcome

When this is done:

- A re-run that starts while its jobs are loading never shows a job list
  that mixes the old and the new attempt.
- A project row keeps the server's running count after a single run
  reply, instead of dropping to the runs the panel has listed.
- `r` pressed while a request for the selected run or repository is in
  flight makes that request run again once its reply arrives, instead of
  waiting for the next normal interval.
- Job details of a run that drops out of the list are freed at once.
- An idle panel does no sorting or scheduling work between due times.
- A reply that throws while being handled never leaves the panel stuck
  waiting; polling carries on.
- `menu.py register` leaves the menu file alone when the `menu.managed`
  marker is a dangling symlink.
- Each fix has a test that fails without it (`tests/polling.cjs`,
  `tests/test_menu.py`, or the QML smoke for the panel).
- The version goes to the next patch release.

## Affected users and systems

- Users of the GitHub Actions panel (`olafkfreund.github-actions`).
- Files: `Polling.js`, `ActionsPanel.qml`, `menu.py`, `manifest.json`,
  `tests/polling.cjs`, `tests/test_menu.py`, `tests/qml-smoke.py`; README
  only if a described behaviour changes.
- Hosts: p620 and razer through the release and pin chain (nixarchy and
  nixos_config pin ghtui). p510 is not touched.

## Constraints

- Port by hand: the files have drifted, so no file copying.
- Keep ghtui #41's owner decisions: the catalogue stops until `r`, `R`
  or reopen; stale queued runs are corrected only for the selected
  repository; the failure count is kept on `r` (unless the owner decides
  otherwise below).
- No change to request pacing (60 a minute, the 1 s gap, the quota
  slowdown) or to what is fetched.
- The QML smoke runs only in CI or in a VM, never on the desktop.

## Open questions

1. **Failure count on `r`.** gltui resets a task's failure count when you
   press `r`; ghtui #41 chose to keep it, so the next failure still backs
   off long. Recommended: keep ghtui's choice and port only the in-flight
   re-run.
2. **`menu.py` dangling marker.** Not in the issue's list but the same
   bug. Recommended: include it (one line and a test).
3. **Unselected queued runs** (gltui #21 item 7, follow-up lookups for
   queued runs of other projects). ghtui #41 chose the narrow reading.
   Recommended: leave it out.
