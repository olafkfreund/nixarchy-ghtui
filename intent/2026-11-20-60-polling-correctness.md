---
status: approved
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
| 1 | A stage named `constructor`, `__proto__` or `toString` crashes stage grouping | Not applicable: jobs are listed without stage grouping (`ActionsModel.js` 233) and label lookups use `hasOwnProperty` (line 75) |
| 2 | A job list saved as final while it mixes two run attempts | **Present.** `invalidateJobs` (`Polling.js` 197-203) deletes the cached jobs when the attempt changes, but a multi-page jobs task that is between pages keeps the pages it already merged into `t.items` and stamps the result with the new `run_attempt` (lines 353, 394-397) |
| 3 | The server's running total overwritten by a smaller local count | **Present.** The `in_progress` summary phase passes GitHub's total to `activity()` (line 379); a later single-run reply sets `r.active` to the locally listed in-progress count (line 338), so a project with 250 running shows the few it has listed. A server total of 0 must still rise when a lookup confirms a run has started, or the project stays on the idle schedule (gltui #21 step 8) |
| 4 | `r` does not cut short a retry wait | **Partly fixed.** `manual()` already moves a backing-off summary or jobs task's `due` to now (ghtui #41, decision 5 in its step 3). Missing: a multi-page or multi-phase task that is between requests, or in flight, keeps its partial data and carries on from where it was, instead of starting again from the first page and phase. ghtui #41 deliberately kept the failure count |
| 5 | Polling follows a row no longer highlighted | Already fixed: `adopt()` always calls `selectionChanged` (`ActionsPanel.qml` 240-241) |
| 6 | Job caches never freed | **Mostly fixed** by ghtui #41's `prune()`. Gaps: a single-run reply (`Polling.js` 335-337) and an intermediate summary page or phase (line 361, which returns before the prune at line 391) can drop a run from the list without freeing its jobs until a later full summary or activity reply |
| 7 | The scheduler re-sorts every project ten times a second while idle | **Present.** On each eligible 100 ms pump tick `next()` calls `seed()`, which sorts every repo (`Polling.js` 163, 127; `ActionsPanel.qml` 418). ghtui has more inputs to wake on than gltui: the quota pace (`pace`, `resetAt`), closed-panel watches, load-more and the account check |
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
- A project row keeps at least the server's running count after a single
  run reply, instead of dropping to the runs the panel has listed; a
  confirmed new run still raises a count of 0.
- `r` restarts the selected repository's summary and the inspected run's
  jobs from their first phase and page: partial data is dropped, and a
  reply that was in flight when `r` was pressed is discarded and the task
  starts again (still within the cooldown, the 1 s gap and the rate
  limit, and with the failure count kept).
- Job details of a run that drops out of the list are freed at once, on
  every reply path, except for the expanded and inspected runs.
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
3. **Unselected queued runs** (gltui #21 item 4, step 7: follow-up
   lookups for queued runs of other projects; here activity already
   marks a missing run for a final lookup, and watches have their own). ghtui #41 chose the narrow reading.
   Recommended: leave it out.
