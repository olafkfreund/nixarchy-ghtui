---
status: draft
issue: 60
spec: spec/2026-11-20-60-polling-correctness.md
coders:
  1: codex   # restart() and its two callers: small, tricky task-state logic in complete()
  2: codex   # running-total rule: counting logic against union()'s freshness check
  3: codex   # prune in mergeRuns, the once-a-second reseed and drop(): scheduler invariants
  4: codex   # finishRequest in the panel and its CI smoke case: async QML error paths
  5: agy     # menu.py marker, its test, the version bump and README wording: mechanical edits
reviewers:
  - codex    # fresh diff review against this plan
  - agy      # second, independent diff review
---

# Plan: Port the polling correctness fixes from nixarchy-gltui #21

Work in the worktree `/mnt/code/Source-home/GitHub/nixarchy-ghtui-60`,
branch `fix/60-polling-correctness`. Line numbers are from `main` at
`7b6f6f5`; anchor by function name. Codex and agy write the code; the
lead runs the checks, dispatches the reviews (Codex, agy and an Opus
review) and makes every commit. Port by hand from the gltui reference
(`/mnt/code/Source-home/GitHub/nixarchy-gltui/Polling.js`
`restart`/`activeFromTotal`, `PipelinesPanel.qml` `finishRequest`); never
copy files.

## Decisions (from the approved spec)

1. **Keep ghtui #41's decisions:** the failure count is kept on `r`; the
   catalogue stops until `r`, `R` or reopen; stale queued runs are
   corrected only for the selected repository; no lookups for queued runs
   of unselected repositories. Request pacing and what is fetched do not
   change.
2. **`restart(s, t, now)`**: in flight (`s.flight && s.flight.key ===
   t.key`) → `t.restart = true`; otherwise `t.page = 1; t.phase = 0;
   t.items = []; t.all = []; delete t.hidden; delete t.recent; t.due =
   now` (failures kept). In `complete()`, right after `cool()`: if
   `t.restart`, clear it, reset as above, `return true` (the reply is
   discarded).
3. **`manual()`** calls `restart` for the selected repository's `summary`
   (still only when no `more` task exists) and for the inspected expanded
   run's `jobs`, instead of only lowering `due`. Account and catalogue
   handling unchanged.
4. **Attempt change**: in `mergeRuns()`, when the run accepted by the
   merge (read back from `r.runs` after `union()`) has a different
   `run_attempt || 1` than the cached run, delete its details (as
   `invalidateJobs` does) and `restart` its `jobs` task if one exists. A
   stale payload that `union()` rejects changes nothing. A re-run between
   two jobs pages with no other reply in between is out of scope.
5. **Running total**: `activity()` sets `r.activeFromTotal = typeof total
   === "number" && total >= 0` and takes `total` only under that test
   (and only when not `summaryAuthoritative`, as today). The single-run
   branch of `complete()` records before `mergeRuns()` whether the cached
   run was counted (`in_progress` and not `awaitingFinal`); after it: with
   `r.activeFromTotal`, a counted run whose accepted copy is no longer in
   progress gives `r.active = Math.max(running, (r.active || 0) - 1)`,
   else `r.active = Math.max(r.active || 0, running)`; without it,
   `r.active = running` (today). `running` is today's local count.
6. **Prune**: `mergeRuns()` calls the existing `prune(s, r)` after it
   replaces `r.runs`. Retention stays ghtui's `kept()` (expanded,
   inspected, `r.last`); no new retention for watched runs; `s.expanded`
   is not cleaned.
7. **Reseed**: `create()` gains `wakeAt: 0` and a test-only `seeds: 0`.
   `TIMING.reseed = 1000`. In `next()`, call `seed()` only when `now >=
   s.wakeAt`, then set `s.wakeAt = now + TIMING.reseed` and `s.seeds++`.
   Every exported writer sets `s.wakeAt = 0`: `open`, `close`, `watch`,
   `select`, `manual`, `more`, `requestLog`, `touch`, `restart`, `drop`,
   `noteWrite`, and `complete` (right after `s.flight = null`). Queued
   tasks still start at their own `due` because `next()` filters by
   `due`. A queued watch keeps its deadline across a quota reset, as
   today.
8. **`finishRequest(text, code)`** in `ActionsPanel.qml`: `try {
   receivePage(Model.reply(text, code, requestInfo.requestId),
   requestInfo) } catch (e) { console.warn(...); Polling.drop(polling,
   requestInfo.requestId, Date.now()); adopt() } finally { workerBusy =
   false }`. `requestProc.onExited` and `failedToStart()` call it.
   `Polling.drop(s, requestId, now)`: only when `s.flight &&
   s.flight.request.requestId === requestId`, clear `s.flight` and back off
   its task like a failed request (`failures++`, `due = now +
   min(TIMING.retryMax, TIMING.retryBase * 2^(failures-1))`, `page = 1`,
   `phase = 0`, `items = []`, `all = []`); always `s.wakeAt = 0`.
9. **`menu.py`**: `register_menu()` uses `os.path.lexists(...)` for the
   `menu.managed` marker.
10. **Version** `1.0.1` in `manifest.json`.
11. **Rollout**: p620 and razer after release through the pin chain;
    p510 untouched. The QML smoke runs in CI only.

## Steps

1. **Restart** — `Polling.js`, `tests/polling.cjs`.
   - Add `restart` (decision 2) near `touch()`; add the `t.restart` branch
     in `complete()` right after `cool(s,reply,now)`.
   - `manual()` (lines 67-88): decision 3.
   - `mergeRuns()` (lines 204-212) / `invalidateJobs()` (197-203):
     decision 4. Keep `invalidateJobs`'s other condition (completed →
     not completed deletes details) as it is.
   - Tests (each fails before the change): `r` while a summary is between
     phases → next request is phase 0, page 1, and the final summary has
     no items from before `r`; `r` while a summary is in flight → that
     reply is discarded (no merge) and the task is due at once;
     `failures` unchanged; cooldown and the 1 s gap still hold; restart
     clears `hidden` and `recent` (a restarted in-progress phase whose
     reply omits `total` leaves no old hidden count); attempt change
     between jobs pages → next jobs request is page 1 and the final
     details hold only new-attempt jobs; a stale run reply rejected by
     `union()` does not restart jobs. Existing #41 tests (failures kept,
     load-more guard, catalogue stop) still pass.
   - Verify: `node tests/polling.cjs`.
   - Traps: `complete()` deletes the task on several paths; the restart
     branch must come before all of them. `union()` decides freshness;
     compare attempts on what it kept.

2. **Running total** — `Polling.js`, `tests/polling.cjs`.
   - `activity()` (lines 238-259): decision 5's flag. Single-run branch of
     `complete()` (lines 333-339): decision 5.
   - Tests: summary total 250 survives a single-run reply; total 0 rises
     to 1 when a lookup confirms a run in progress; a counted run that
     finishes decrements by one; a stale reply rejected by `union()`
     leaves the total; without a total, today's local count.
   - Verify: `node tests/polling.cjs`.
   - Traps: read the counted flag before `mergeRuns()` mutates the run.

3. **Prune, reseed, drop** — `Polling.js`, `tests/polling.cjs`.
   - Decisions 6, 7 and 8's `drop()`.
   - Tests: a single-run reply and an intermediate summary page each free
     an evicted run's details at once and keep expanded, inspected and
     `r.last` runs (existing last-result tests still pass); ten idle
     `next()` calls within one second seed once (`s.seeds`), a writer
     makes the next call seed, a queued task still starts at its `due`;
     the catalogue stop holds past five minutes; `drop()` clears only the
     matching flight and backs off that task, and leaves a newer flight
     alone.
   - Verify: `node tests/polling.cjs`.
   - Traps: `seed()` has early returns (account check, closed panel); the
     reseed cap is set in `next()`, not in `seed()`, so they need no
     change.

4. **Panel** — `ActionsPanel.qml`, `tests/qml-smoke.py`.
   - Decision 8: `finishRequest`, used by `requestProc.onExited` and
     `failedToStart()`.
   - Smoke (CI only): a throw before `complete()` (for example a
     temporarily overridden reply text that makes `Model.reply` or
     `receivePage` throw) and a throw inside `adopt()` each leave
     `workerBusy` false and a later request starts; the closed-watch
     fixture that sets `watches["one/repo:7"].at = 0` directly also sets
     `panel.polling.wakeAt = 0`.
   - Verify: `node tests/polling.cjs`; `python3 -c "import ast;
     ast.parse(open('tests/qml-smoke.py').read())"`; the lead checks CI.
   - Traps: QML functions cannot be monkey-patched on some objects;
     trigger the throw through data (for example a reply whose handling
     throws) rather than replacing a function, or report how you did it.
     Never run the smoke locally.

5. **Marker, version, docs** — `menu.py`, `tests/test_menu.py`,
   `manifest.json`, `README.md`.
   - Decision 9; extend `test_managed_marker_leaves_menu_untouched` (line
     138) with a dangling `menu.managed` symlink, for an existing and an
     absent menu file.
   - Decision 10.
   - README: if it describes `r` or polling cadence, say that `r` restarts
     the selected repository's summary and the open run's jobs from the
     start; nothing else.
   - Verify: `python3 -m unittest discover -s tests`; the lead runs `nix
     flake check`.

## Tests

- `node tests/polling.cjs`, `node tests/model.cjs`: pass.
- `python3 -m unittest discover -s tests`: pass.
- `nix flake check -L`: pass.
- CI `qml-smoke` job: pass.

## Deviations

None yet.

## Rollback

Revert the squash commit and release 1.0.2; the pin chain moves back.
