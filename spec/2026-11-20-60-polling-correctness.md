---
status: approved
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

New `restart(s, t, now)`: if `t` is in flight (`s.flight && s.flight.key
=== t.key`) it sets `t.restart = true`; otherwise it resets `t.page = 1`,
`t.phase = 0`, `t.items = []`, `t.all = []`, deletes `t.hidden` and
`t.recent`, and sets `t.due = now`. Unlike gltui it keeps `t.failures`
(intent decision 1). In `complete()`, right after `cool()` and before
any handling of the reply's data or error: if `t.restart`, clear it,
reset as above, and return `true` — the in-flight reply is discarded and
the task runs again at `now`, still subject to the cooldown, the 1 s gap
and the 60-a-minute window in `next()`.

Used by:

- **`manual()` (item 4):** for the selected repository's `summary` and
  the inspected expanded run's `jobs`, call `restart` instead of only
  lowering `due`. The account and catalogue handling stay as today; the
  load-more guard (no summary while a `more` task exists) stays.
- **`mergeRuns()` (item 2):** when the run accepted by the merge (the one
  in `r.runs` after `union()`, so a stale payload that `union()` rejects
  changes nothing) has a different normalized `run_attempt`
  (`run_attempt || 1`) than the cached run, besides deleting its details
  as `invalidateJobs` does today, call `restart` on that run's `jobs` task
  if one exists. Scope: attempt changes the poller observes through a run,
  activity or summary reply. A re-run that GitHub starts between two jobs
  pages with no reply in between cannot be detected from the jobs pages
  (they carry no attempt); that stays as today.

### 2. Server running total (item 3, `Polling.js`)

`activity()` records `r.activeFromTotal = typeof total === "number" &&
total >= 0` and uses that same test to decide whether to take `total`
(only when not `summaryAuthoritative`, as today). The single-run branch
of `complete()` remembers, before `mergeRuns()`, whether the cached run
was counted (`status === "in_progress"` and not `awaitingFinal`). After
the merge it sets:

- when `r.activeFromTotal`: if the run was counted and the **accepted**
  run (read back from `r.runs`) is no longer in progress,
  `r.active = Math.max(running, (r.active || 0) - 1)`; otherwise
  `r.active = Math.max(r.active || 0, running)`;
- otherwise `r.active = running` (today's behaviour),

where `running` is today's local count. So 250 stays 250, 0 rises to 1
when a lookup confirms a run, a finished counted run decrements by one,
and a stale reply that `union()` rejects changes nothing.

### 3. Prune on every path (item 6, `Polling.js`)

`mergeRuns()` calls the existing `prune(s, r)` after it replaces
`r.runs`. `prune()` frees the details of runs no longer in `r.runs`, and
`recent()` already keeps ghtui's retained runs there (`kept()`: expanded,
inspected, and the last default-branch result `r.last`), so ghtui's
retention rule is unchanged. This covers the single-run reply and the
intermediate summary pages; the existing `prune()` calls stay. Watched
runs gain no new retention, and `s.expanded` is not cleaned (as in
gltui).

### 4. Idle scheduler (item 7, `Polling.js`)

`next()` re-runs `seed()` only when something changed or a second has
passed: a new `s.wakeAt` (0 = seed now) is set to `0` by every exported
writer (`open`, `close`, `select`, `manual`, `more`, `requestLog`,
`touch`, `watch`, `restart`, `drop`, `noteWrite`
and `complete`, right after it clears `s.flight`), and after each seed
`next()` sets `s.wakeAt = now + TIMING.reseed` (1000 ms). Tasks already
queued still start exactly at their `due`, because `next()` filters
queued tasks by `due` itself; only the creation of new time-based tasks
(activity, summary, follow-ups, jobs refresh, watch tasks) can run up to
a second late. Those intervals are 5 s or longer. No deadline is
computed, so `pace()`/`resetAt`, the account check, the closed-panel
path, `stableAt` and the catalogue need no special handling, and what is
fetched does not change. A queued watch task keeps the deadline it was
queued with across a quota reset, as today.

This replaces the intent's "no scheduling work between due times" with
"at most one seed a second while nothing changes" — a tenfold cut
without the risk of a missed wake.

### 5. `finishRequest` (item 8, `ActionsPanel.qml`, `Polling.js`)

`requestProc.onExited` and `failedToStart()` both call a new
`finishRequest(text, code)`, which runs `Model.reply(...)` and
`receivePage(...)` inside `try`; on an exception it logs it and calls a
new `Polling.drop(polling, requestInfo.requestId, Date.now())`, and
`finally` clears `workerBusy`. `drop()` clears `s.flight` only when it
is the flight of that request id (so a newer flight is never touched),
backs off that task like a failed request (`failures++`, `due` by the
retry rule, page and phase reset) and sets `s.wakeAt = 0`. A throw after
`complete()` (for example in `adopt()`) finds no matching flight and
only releases `workerBusy`.

### 6. `menu.py` managed marker

`register_menu()` checks the marker with `os.path.lexists(...)` (true
for a dangling symlink) instead of `Path.exists()`.

### 7. Version

`manifest.json` `1.0.0` → `1.0.1`; the flake reads it.

## Alternatives rejected

- **Resetting `failures` on `r`** (gltui's choice): ghtui #41 kept it on
  purpose so repeated `r` during an outage still backs off.
- **Porting gltui's computed `wakeAt` deadline**: ghtui queues watch
  tasks eagerly, returns early from `seed()` for the account check and
  the closed panel, has a quota pace that changes at `resetAt`, and has
  no catalogue age in `seed()`; a computed deadline must model all of
  that and stalls polling if it misses one (both reviewers found such
  cases). The once-a-second reseed with immediate reseed on any change
  has no such failure mode.
- **Copying gltui's files**: they have drifted (GitHub API, watches,
  quota pace, account check); port by hand.
- **Pruning in each caller** instead of in `mergeRuns()`: more places to
  forget.

## Risks

- **A writer that forgets `s.wakeAt = 0`** delays new tasks by at most a
  second (the reseed cap), never stalls them.
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
  - restart of a summary clears `hidden` and `recent` (a restarted phase
    whose reply omits `total` carries no old hidden count);
  - a stale run reply rejected by `union()` neither restarts jobs nor
    lowers the running total;
  - pruning: a single-run reply and an intermediate summary page each
    free an evicted run's details at once and keep expanded, inspected
    and `r.last` runs; the existing last-result tests still pass;
  - reseed: ten idle `next()` calls within a second seed once (a
    test-only `s.seeds` counter); a writer makes the next call seed;
    a queued task still starts at its `due`; the catalogue stop holds
    past five minutes;
  - `drop()`: clears only the matching flight and backs off its task.
- `python3 -m unittest discover -s tests`: a dangling `menu.managed`
  leaves the menu untouched (existing file and absent file).
- `nix flake check` (runs both suites).
- QML smoke in CI only (`qml-smoke` job): a throw before `complete()`
  and a throw in `adopt()` each leave `workerBusy` false and a later
  request starts. The closed-watch fixture that edits `watches[...].at`
  directly also sets `wakeAt = 0`.
