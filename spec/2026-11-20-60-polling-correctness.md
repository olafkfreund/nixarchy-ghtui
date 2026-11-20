---
status: draft
issue: 60
intent: intent/2026-11-20-60-polling-correctness.md
---

# Spec: Port the polling correctness fixes from nixarchy-gltui #21

## Design

Seven small changes, each ported by hand from the gltui fix of the same
bug (gltui `Polling.js`, `PipelinesPanel.qml`, `menu.py` at v1.0.1 and
later), adapted to ghtui's code. Approved intent decisions: keep the
failure count on `r` (ghtui #41), include the `menu.py` marker fix, leave
out lookups for queued runs of unselected repositories.

### 1. `restart()` — one way to start a task over (`Polling.js`)

New `restart(s, t, now)`: if `t` is in flight (`s.flight.key === t.key`)
it sets `t.restart = true`; otherwise it resets `t.page = 1`,
`t.phase = 0`, `t.items = []`, `t.all = []`, `t.due = now`. Unlike gltui
it keeps `t.failures` (intent decision 1). In `complete()`, right after
`cool()` and before any handling of the reply's data or error: if
`t.restart`, clear it, reset as above, and return `true` — the in-flight
reply is discarded, and the task runs again at `now`, still subject to
the cooldown, the 1 s gap and the 60-a-minute window in `next()`.

Used by:

- **`manual()` (item 4):** for the selected repository's `summary` and
  the inspected expanded run's `jobs`, call `restart` instead of only
  lowering `due`. The account and catalogue handling stay as today; the
  load-more guard (no summary while a `more` task exists) stays.
- **`mergeRuns()` (item 2):** when an incoming run's `run_attempt`
  differs from the cached one, besides deleting its details as
  `invalidateJobs` does today, call `restart` on that run's `jobs` task
  if one exists, so pages of the old attempt are never stamped with the
  new one.

### 2. Server running total (item 3, `Polling.js`)

`activity()` records `r.activeFromTotal = typeof total === "number" &&
total >= 0` wherever it sets `r.active` (only when not
`summaryAuthoritative`, as today). The single-run branch of `complete()`
(line 338) then sets:

- `r.active = Math.max(r.active || 0, running)` when `r.activeFromTotal`,
  where `running` is today's local count — except that when the cached
  run was counted as in progress and the reply says it is no longer in
  progress, `r.active = Math.max(running, (r.active || 0) - 1)`;
- `r.active = running` otherwise (today's behaviour).

This is gltui's rule (including its later watch fix), so a total of 250
stays 250, 0 rises to 1 when a lookup confirms a run, and a finished
watched run stops counting.

### 3. Prune on every path (item 6, `Polling.js`)

`mergeRuns()` remembers the run ids before it replaces `r.runs` and,
after `recent()`, deletes `s.details[r.repo + ":" + id]` for every id
that is gone, unless `kept()` holds (expanded, inspected or watched).
This covers the single-run reply and intermediate summary pages without
touching their callers; the existing `prune()` calls stay. `s.expanded`
is not cleaned (out of scope, as in gltui).

### 4. Idle scheduler (item 7, `Polling.js`)

Port gltui's `wakeAt`: `seed()` returns early while `now < s.wakeAt`; at
the end of a full seed it sets `s.wakeAt` to the earliest moment any
seeding rule could produce a new task, computed from the same ages
`seed()` already checks (summary and activity intervals with `pace()`,
run follow-ups, jobs refresh, watches, `stableAt`, the catalogue) and
the `due` of every queued task. Because `pace()` changes at the quota
reset, `s.resetAt` is a wake point too. Every function that changes
state the seed rules read sets `s.wakeAt = 0`: `open`, `close`,
`select`, `manual`, `more`, `requestLog`, `touch`, `watch`/`unwatch`,
`restart`, `ensure`, `mergeRuns`, `activity`, `cool`/`noteWrite` and
`complete`. The account check (`!s.accountChecked`) and a closed panel
with watches keep working because `open`, `close` and `complete` reset
it. `next()` keeps its guards.

### 5. `finishRequest` (item 8, `ActionsPanel.qml`)

`requestProc.onExited` and `failedToStart()` both call a new
`finishRequest(text, code)`, which runs `receivePage(...)` inside `try`
and clears `workerBusy` in `finally`, as the action path already does.

### 6. `menu.py` managed marker

`register_menu()` checks the marker with `os.path.lexists(...)` (true
for a dangling symlink) instead of `Path.exists()`.

### 7. Version

`manifest.json` `1.0.0` → `1.0.1`; the flake reads it.

## Alternatives rejected

- **Resetting `failures` on `r`** (gltui's choice): ghtui #41 kept it on
  purpose so repeated `r` during an outage still backs off.
- **Throttling `seed()` to once a second** instead of `wakeAt`: simpler,
  but adds up to a second of latency to selection and `r`, and still
  sorts every repo each second.
- **Copying gltui's files**: they have drifted (GitHub API, watches,
  quota pace, account check); port by hand.
- **Pruning in each caller** instead of in `mergeRuns()`: more places to
  forget.

## Risks

- **`wakeAt` missing a writer** would leave polling stalled until another
  writer runs; mitigated by resetting it in every exported writer and by
  tests that each wake source (selection, `r`, quota reset, watches while
  closed, follow-ups) still starts its request on time.
- **The restart discarding a reply** that also carried a rate-limit
  header: `cool()` runs first, so the cooldown is kept.
- **The `Math.max` count** can briefly over-count until the next
  activity or summary reply; accepted (gltui ships the same).
- Hosts: p620 and razer after release; p510 untouched.

## Verification

- `node tests/polling.cjs`, with a failing-before case for each item:
  - restart: `r` during a summary between phases restarts from phase 0
    with no old items; `r` while it is in flight discards the reply and
    re-runs at once; failures are unchanged; cooldown and the 1 s gap
    still hold;
  - attempt change between jobs pages: the next jobs request is page 1
    and the final details hold only the new attempt's jobs;
  - running total: 250 survives a single-run reply; 0 rises to 1; a
    finished watched run decrements;
  - pruning: a single-run reply and an intermediate summary page each
    free an evicted run's details at once and keep expanded, inspected
    and watched runs;
  - `wakeAt`: idle `next()` calls do not re-seed (count via a test-only
    counter, as gltui's `seeds`); each wake source still starts its
    request when due.
- `python3 -m unittest discover -s tests`: a dangling `menu.managed`
  leaves the menu untouched (existing file and absent file).
- `nix flake check` (runs both suites).
- QML smoke in CI only (`qml-smoke` job): a reply handler that throws
  leaves `workerBusy` false and the next request starts.
