---
status: draft
issue: 41
spec: spec/2026-11-16-41-polling-reliability.md
coders:
  1: codex     # helper parsing and validation: account login check, step check, error text
  2: codex     # scheduler edge case: the account gate changes seed()/next() and 16 test fixtures
  3: codex     # scheduler edge cases: catalogue stop flag, manual() due handling
  4: codex     # complete() branches: jobs error write, stale queued marking, prune
  5: codex     # small tricky logic: pace() tiers and where the multiplier applies
  6: coder     # rows() argument and subtitle/timer change, mechanical with tests
  7: coder     # QML wiring and smoke test edits
  8: coder     # README text
reviewers:
  - codex      # independent read-only review of the final diff against this plan (scheduler and gate logic is where bugs hide); output is advice only
---

# Plan: Polling stops retry loops, stale runs and stuck loading states

## Base and branch

- Branch `fix/41-polling-reliability`, from `main`. #41 merges first (order: #41 -> #42 -> #43(a) -> #43(b); #44, #45, #47 after #41; #46 after #41-#44). A `feat/42-panel-ui` branch already exists locally. Do not build on it.
- Before any code step (step 0): if `main` has moved because another PR merged, run `git fetch origin && git rebase origin/main`. The branch holds only intent, spec and plan commits at that point, so this can't conflict. Then run the full "Tests" section on the base. All of it must pass. Record the base SHA in the PR.
- Line numbers below are from `main` at `6d42838`. Steps edit the same files, so later steps find their lines by function name and the quoted code.

## Approved decisions (copied from the approved spec)

Scope: nine fixes, one branch, one PR. Files: `Polling.js`, `ActionsModel.js`, `ActionsPanel.qml`, `actions.py`, the README polling section (lines 168-170) and the tests. No new files, dependencies, settings, keys or QML modules. Polling stays as it is: no daemon, no polling while closed, no state file, no token read or stored. Requests are argument arrays pinned to `github.com`. New panel text comes from a fixed set (#24). Untrusted GitHub text goes through `plain()` (#32).

Owner decisions: (1) after the first catalogue permission failure the panel stops asking for the catalogue until `r`/`R` or reopen. (2) The helper rejects the whole jobs reply if any step is not an object, and the user sees an error under that run. (3) The `gh` login is checked when the panel opens, and repos/details/expanded are cleared if it differs; a switch while open is not detected. (4) Background polling slows as remaining quota falls. (5) Stale queued runs are corrected only for expanded or inspected runs of the selected repository (the narrow reading, confirmed by the owner). (6) Expanded runs you left are marked "not refreshing" with their age, and their timers stop. (7) Cached job details for runs no longer listed are dropped. (8) One branch, one PR.

Design, by spec section:

1. **Catalogue 403 (`Polling.js`).**
   - In `complete()`'s `permission` branch (lines 187-191), add a first case `t.kind === "catalogue"`. It sets `s.discover = false` and `s.catalogueBlocked = s.error`. The task is still deleted. Known repositories stay (a failed catalogue never reaches the removal at lines 222-227).
   - `create()` starts `catalogueBlocked:""`.
   - `manual()` (line 41) also re-enables discovery when `s.catalogueBlocked` is set, and clears the flag. A normal `r` must still go on to refresh the selected repository, so it only does the early `return` when the `catalogue` argument is true, as today.
   - `open()` (line 28) clears the flag and sets `s.discover = true` when the flag was set, even if `catalogueComplete` is true and the cache is under 5 minutes old.
   - `adopt()` in the QML shows `polling.error || polling.catalogueBlocked`.
   - Helper (`actions.py:166-167`): for `kind == "catalogue"` a 403/404 gives the fixed text `Repository list unavailable; token cannot read your repositories`. Other kinds keep the old text.
2. **Failed jobs fetch (`Polling.js`).** In `complete()`, when `t.kind === "jobs"` and any error comes back, write the error into the detail entry and keep the existing `jobs`, `updated` and `jobsAt`. Only `permission` also sets `unavailable` and `jobsAt:now`, as today:
   ```js
   if (t.kind==="jobs") { var dk=t.repo+":"+t.run;
       s.details[dk]=Object.assign({},s.details[dk]||{},{error:s.error});
       if (reply.errorType==="permission") Object.assign(s.details[dk],{jobsAt:now,unavailable:true}); }
   ```
   The write goes before the `permission` / `else` split. `ActionsModel.js:67` already renders `detail.error` and then still renders `detail.jobs`, so the model needs no change. A later success replaces the entry (line 241). Retry timing is unchanged.
3. **Stale queued runs (`Polling.js`).** At the end of a full summary (line 235), any kept run that is not `completed` and is missing from `t.all` gets `awaitingFinal = true` and loses its `followupAt`. The existing `run` task then looks it up (line 85). Only the selected repository is covered (a summary runs only for it).
4. **Highlight and polling agree (`ActionsPanel.qml`).** `adopt()` always ends with `selectionChanged(false)` (the condition at line 129 is removed). It also sets `expanded = polling.expanded` before `rebuild()`. `Polling.select()` is already idempotent for the same repository. `status()` gains `pollSelected` and `pollInspected`.
5. **`r` moves a backing-off task (`Polling.js`).** In `manual()`, keep the task each `ensure()` returns and set `t.due = Math.min(t.due, now)`. Leave the failure count alone. `next()` still enforces cooldown, the 1 s gap and 60 a minute.
6. **Bad steps (`actions.py`).** Lines 189-190 become:
   `if kind == "jobs" and any(not isinstance(row.get("steps", []), list) or any(not isinstance(step, dict) for step in row.get("steps", [])) for row in body[key]): raise ValueError("Invalid job steps")`.
   That `ValueError` already becomes the `network` error (line 208). The `isinstance(step, dict)` guard at lines 193-195 is removed, so `plain_fields(step, ("name",))` runs on every step. `"steps": null` is already rejected. The model is not hardened.
7. **Quota (`Polling.js`).**
   - Add to `TIMING`: `quotaEase:1000, quotaTight:300`.
   - `create()` adds `remaining:null, resetAt:0`. `complete()` records both from every reply whose `remaining` is a number, after the identity check and before the data-shape check.
   - `pace(s, now)` returns 1 when `remaining` is not a number or `now >= resetAt`; otherwise 1 when `remaining >= TIMING.quotaEase`, 3 when `remaining >= TIMING.quotaTight`, else 10. `remaining === 0` keeps today's cooldown handling.
   - The multiplier applies to the non-selected activity interval in `seed()` (line 74, `TIMING.active` and `TIMING.idle`) and to the catalogue age check in `open()` (line 30). Selected summary and activity, the inspected run's jobs and `run` lookups keep full pace.
   - `status()` gains `remaining` and `resetAt`. No new display (#42 owns the status line).
8. **Account switch (`actions.py`, `Polling.js`, `ActionsPanel.qml`).**
   - Helper: `page_endpoint()` accepts kind `account` and returns `"user"`; it needs no `repo`. `read_page()`: for `account` the body must be an object with a string `login` fullmatching `[A-Za-z0-9-]+`, otherwise `ValueError`. `result["data"] = {"login": login}` and nothing else from the body.
   - `complete()`'s `okData`: `account` is treated like `run` (the data must be a non-null, non-array object).
   - `create()` adds `account:""` and `accountChecked:false`. `open()` sets `accountChecked = false`.
   - Gate: while `!accountChecked`, `seed()` creates only the `account` task (group `interactive`, due now) and returns, and `next()` returns only the `account` task. No other request starts first.
   - On success: if `s.account` is set and differs from the login, set `s.tasks = {}` and clear `repos`, `details`, `expanded`, `selected`, `inspected`, `catalogueComplete`, `catalogueBlocked`, then `discover = true`. Then set `s.account = login`, `accountChecked = true`, and delete the task. A first-ever check only records the login.
   - `network` and `rate` errors retry through the normal backoff and cooldown. `setup` and `auth` stop polling as today. A `permission` error means "can't tell": mark the check done, clear nothing, show no error.
   - `manual()` also ensures the `account` task when `!accountChecked` and sets `due = Math.min(due, now)`, so `r` releases a backing-off check. Cooldown, gap and ceiling still apply.
   - Cached data still shows at once on reopen.
9. **Expanded runs you left (`ActionsModel.js`, `ActionsPanel.qml`).**
   - `rows(repos, expanded, details, filter, now, live)`: `live` is `polling.selected + ":" + polling.inspected` or `""`. `rebuild()` passes it.
   - For an expanded run with a detail that has `updated`, `fresh` is true when `runKey === live`, or when `run.status === "completed" && detail.finalAttempt === (run.run_attempt || 1)`.
   - When not fresh, the subtitle stamp reads `jobs 4m old, not refreshing` instead of `jobs fetched HH:MM:SS UTC`. Age is `now - Date.parse(detail.updated)`: whole minutes below an hour, `Xh Ym` above. Job and step rows call `duration(item, Date.parse(detail.updated))` instead of `now`.
   - `selectionChanged()` calls `rebuild()` at its end, so the marker follows the cursor at once.
10. **Memory (`Polling.js`).** A helper `prune(s, r)` deletes every `s.details` key with the prefix `r.repo + ":"` whose run ID is not in `r.runs`. Call it after the summary publishes `r.runs` (line 236) and at the end of `activity()` (after line 161). When the catalogue removes a repository (lines 222-224), delete that repository's details by the same prefix. Expanded flags are not cleaned. `close()` is unchanged.

Order and overlap: #42 keeps `rows()`'s new `live` argument. #43 rebases onto this. #44 adds request kinds next to `account` in `page_endpoint()`. #45 reuses `manual()`. #46 reads `s.account`.

## Steps

Each step is one commit made by the session. Tests come first in the same commit and must fail on current code for the stated reason, then pass after the fix. Per #36 there are no reruns: a test that fails is a bug to fix, never a test to run again until it is green. `python3 tests/qml-smoke.py` runs once per change. Each step's coder names the step it is doing. Builds, reviews and commits stay with the session.

0. Session: base check as in "Base and branch" → verify by `git log --oneline -1`, plus the whole "Tests" section green on the base.
   Traps: none.

1. `actions.py` and `tests/test_actions.py` (helper): tests first.
   - `tests/test_actions.py`: in `test_page_text_is_plain`, remove `"not-a-step"` from the `job` fixture (lines 200-203) so valid steps still pass through `plain()`. Add a new test `test_bad_steps_reject_the_page`. A jobs page with `steps: [None]`, `steps: ["x"]`, `steps: [1]` and `steps: null` each gives `errorType == "network"`. A page with valid steps gives `errorType == ""` and the step names are plain. Add `test_account_page`. `page_endpoint({"kind":"account","requestId":1}) == "user"`. A body `{"login":"octo-cat","id":1,"email":"x"}` gives `data == {"login":"octo-cat"}`. A missing, non-string, `"a b"`, `"a\n"` or `""` login gives `network`. A task with no or invalid `requestId` raises `ValueError`. An `account` task with `repo` absent, `None` or `""` returns `user` (the scheduler always sends `repo: ""`, `Polling.js:112`), and one with a non-empty `repo` (such as `a/..`) raises `ValueError`. `nextPage` is 0 even with a `Link: rel="next"` header. Add `test_catalogue_403_message`. A catalogue 403 and a catalogue 404 give `Repository list unavailable; token cannot read your repositories`. A summary 403 keeps `Resource unavailable or Actions read permission missing`.
   - `actions.py:60`: add `"account"` to the allowed kinds. After the `requestId` check (line 66), `if task["kind"] == "account": if task.get("repo") not in (None, ""): raise ValueError("Invalid page operation"); return "user"`.
   - `actions.py:166-167`: choose the message by `task["kind"] == "catalogue"`.
   - `actions.py` kind chain (line 172 onward): add `elif kind == "account":` before `elif kind == "run":`. It validates as in decision 8 and sets `result["data"] = {"login": login}`.
   - `actions.py:189-196`: replace as decision 6; delete the `if isinstance(step, dict):` guard so the call becomes `plain_fields(step, ("name",))`.
   → verify by `python3 -m unittest tests/test_actions.py tests/test_menu.py` (all pass; before the change the three new tests fail).
   Traps: `gh api` stays an argument array with `--hostname github.com` (`request()` is not touched). `plain()` runs on every step name (#32). The `account` data returns only `login`, never other profile fields. The new catalogue text is a fixed string (#24). `nextPage` stays set only for `catalogue` and `jobs`. Ponytail: no new helper function, only the branches above.

2. `Polling.js` and `tests/polling.cjs`: the account gate (decision 8).
   - Tests first. Add a helper `function reopen(s, now) { polling.open(s, now); s.accountChecked = true; }` at the top of `tests/polling.cjs`. Replace every `polling.open(x, t)` (16 calls at lines 26, 69, 82, 87, 91, 100, 120, 142, 145, 165, 170, 180, 205, 212, plus the two close/open pairs) with `reopen(x, t)` so existing fixtures start from a completed check. The old fixtures must pass unchanged in meaning. Extend `response()` (line 19) callers with an `account` data shape `{login:'tester'}` where a test completes an `account` request. Add one lifecycle block, using plain `polling.open`:
     - After `open()`, `next()` returns an `account` request and nothing else, even with a due catalogue, a due summary and a known repository. Ensure that `next()` with an `account` task in flight returns null.
     - A first-ever success records `s.account`, sets `accountChecked`, clears nothing, and the following `next()` returns other work.
     - A different login: `repos`, `details`, `expanded`, `selected`, `inspected`, `catalogueComplete` and `catalogueBlocked` are cleared, `discover` is true, `s.tasks` is empty (queued `activity` and `run` tasks of the old account are gone).
     - The same login clears nothing.
     - A `permission` error on the check: `accountChecked` true, nothing cleared, `s.error === ""`, polling goes on. Also the sequence `network` error, then `permission` on the retry: `s.error` is `""` afterwards.
     - A `network` error: the gate stays shut, the task has a backoff `due` in the future. `manual(s, now, false)` moves it to `now`, and `next()` returns it. With `cooldown` in the future, `manual()` doesn't start it.
     - A stale `account` reply after `close()` then `open()` returns false (generation / requestId).
     - `okData`: an `account` reply with `data: []` or `null` gives the `Workflow helper returned invalid data` / `setup` stop.
   - `Polling.js`: `create()` adds `account:"", accountChecked:false`. `open()` sets `s.accountChecked = false`. `seed()` starts with `if (!s.accountChecked) { ensure(s,"account","","","interactive",now); return; }`. `next()` filters `due` to `kind === "account"` while `!s.accountChecked`. `manual()` ensures the `account` task when `!s.accountChecked` (before the `catalogue` early return) and sets its `due = Math.min(due, now)`. `complete()`: `okData` treats `account` like `run`. Right after the `permission` handling needs to skip the generic error text, add an early branch after the rate/cooldown block: for `t.kind === "account" && reply.errorType === "permission"` set `s.accountChecked = true`, `s.error = ""`, `delete s.tasks[t.key]` and `return true` before `s.error` is assigned from the reply, so an earlier `network` error on the same check does not stay visible. On success, handle `account` right after `s.error=""; ...` (line 200) as in decision 8 and `return true`.
   → verify by `node tests/polling.cjs` (exit 0; the new block fails on current code because `next()` returns a catalogue request first).
   Traps: `seed()` and `next()` change must not alter the 5-slot fairness (`s.slot`) for non-gated runs. `accountChecked` is reset by `open()` but not by `close()`. All 16 fixtures must go through `reopen()`, or they get an `account` request and fail in confusing ways. `account` requests use the same budget (1 s gap, 60 a minute) and cooldown; do not bypass `next()`'s guards. No QML in this step.

3. `Polling.js` and `tests/polling.cjs`: catalogue 403 and `r` moves a backing-off task (decisions 1 and 5).
   - Tests first (all start from `reopen()`):
     - A catalogue `permission` reply sets `discover === false` and `catalogueBlocked` to the reply's text, with known `repos` unchanged. Simulate 60 s with 1 s steps: no catalogue request after the first (current code returns up to 60). `manual(s, now, false)` and `manual(s, now, true)` each start one more catalogue request. `reopen()` also starts one, even with `catalogueComplete` true and `catalogueAt` 1 s ago.
     - `r` (`catalogue` false) with `catalogueBlocked` set clears the flag and still ensures the selected repository's summary (it does not return early).
     - A summary task with `failures` 5 and `due = now + 300000` starts at `now` after `manual(s, now, false)`. With `s.cooldown` in the future it doesn't start. With 60 starts in the window it doesn't start. Its `failures` is unchanged. Same for a `jobs` task of the inspected expanded run.
     - Guard test: `select()` called again with the same repository doesn't move `stableAt` (this passes on current code; it records the contract the QML change relies on).
   - `Polling.js`: `create()` adds `catalogueBlocked:""`. The `permission` branch gets the catalogue case first (decision 1). `open()` and `manual()` as in decisions 1 and 5: `manual()` stores `var t = ensure(...)` and sets `t.due = Math.min(t.due, now)` for the summary and jobs calls at lines 47 and 50.
   → verify by `node tests/polling.cjs` (exit 0; the new cases fail on current code).
   Traps: `s.error` is cleared by any later success, so the QML reads `catalogueBlocked` separately (step 7). The task is still deleted in the permission branch. `manual()` must not set `r.blocked` for the catalogue case. Do not reset `t.failures`.

4. `Polling.js` and `tests/polling.cjs`: jobs error, stale queued runs, prune (decisions 2, 3, 10).
   - Tests first:
     - A `network` error on a `jobs` task writes `details[repo:run].error` and keeps the cached `jobs` and `updated`. With no cache the entry has `error` and no `jobs`. The next success replaces the entry with no `error`. A `permission` error still sets `unavailable` and `jobsAt`, and the run is not marked as a lookup error.
     - A queued run that is expanded (or inspected in the selected repository) and missing from a full six-phase snapshot has `awaitingFinal === true` and no `followupAt`. `next()` returns one `run` request for it. After the lookup returns `completed`, the cached status is `completed`. A queued run that is not kept is dropped, as today. A run present in the snapshot is not marked.
     - After a full summary, `details` keys for run IDs not in `r.runs` are gone, and the details of an expanded run and of the inspected run stay. A collapsed, once-inspected run dropped by `polling.activity()` in an unselected repository loses its details. A repository removed by the catalogue loses all of its details (keys with the `repo:` prefix); a repository named `a/b` must not delete the details of `a/bc`.
   - `Polling.js`: add the jobs error write before the `permission` / `else` split as in decision 2. Keep line 189's branch so jobs errors don't fall into the `else if (r)` run-lookup branch: change it to `else if (t.kind==="jobs") {}` with a short comment that the detail is written above. Add the stale marking after `r.runs=recent(...)` in the summary end, using `t.all` ids. Add `function prune(s,r)` and call it as in decision 10, and delete a removed repository's details before the `s.repos` filter at line 224.
   → verify by `node tests/polling.cjs` (exit 0; the new cases fail on current code).
   Traps: compare run IDs as strings (keys carry strings). Prune by the exact prefix `r.repo + ":"`. The marked run objects must be the ones now in `r.runs` (they are the `keep` references). A `permission` jobs error keeps today's output exactly. `activity()` already deletes `followupAt` for returned items; do not touch that.

5. `Polling.js` and `tests/polling.cjs`: quota pacing (decision 7).
   - Tests first (start from `reopen()`):
     - `complete()` records `remaining` and `resetAt` from a reply with a numeric `remaining`, including an error reply. A reply with `remaining: null` leaves them alone.
     - With `remaining: 400` and a future `resetAt`: a non-selected active repository checked 20 s ago is not due, but is due at 45 s; the selected repository (past `stableAt`) is due at its normal 10 s. With `remaining: 100` the idle interval is 6000000 ms. With `remaining: 5000`, or after `resetAt`, the multiplier is 1. `open()` with a 10-minute-old catalogue and `remaining: 400` does not set `discover`, and does at 15 minutes.
     - Selected summary, the inspected run's jobs and `run` lookups are not slowed.
     - The existing workload simulations (budget, spacing, fairness) still pass.
   - `Polling.js`: add `quotaEase` and `quotaTight` to `TIMING` (line 3-5), the `create()` fields, `pace(s, now)`, the recording in `complete()`, and the two multiplications (line 30 and line 74, applied only to the non-selected branch `r.active > 0 ? TIMING.active : TIMING.idle`).
   → verify by `node tests/polling.cjs` (exit 0; the new cases fail on current code).
   Traps: `remaining === 0` handling at lines 176-181 stays exactly as is. `resetAt` is in milliseconds. Don't touch `status()` here (step 7).

6. `ActionsModel.js` and `tests/model.cjs`: "not refreshing" marker (decision 9).
   - Tests first, in `tests/model.cjs` with a fixed `now`: with `live` set to another run, an expanded in-progress run with a non-final detail (`updated` 4 minutes before `now`) has a subtitle containing `jobs 4m old, not refreshing`, and its in-progress job's `info` is computed at `detail.updated`, so it does not change when `now` advances. With `live` equal to the run's key, the subtitle still reads `jobs fetched ... UTC` and timers use `now`. A completed run whose `detail.finalAttempt` equals its attempt shows no marker. A completed run with a different `finalAttempt` does. A detail 75 minutes old reads `1h 15m old`. A detail with `error` and cached `jobs` shows the message row and the jobs. A detail with only `error` (no `updated`) shows no stamp. A collapsed run with a detail keeps `jobs fetched`. Calling `rows()` with five arguments still works.
   - `ActionsModel.js:35` add the `live` parameter. In the run loop (lines 60-80) compute `fresh` as in decision 9, derive the stamp (line 62) and an `at` time used in the `duration(job, ...)` and `duration(step, ...)` calls (lines 74, 78). Add a small `age(ms)` formatter next to `duration()`; share its hour/minute rule.
   → verify by `node tests/model.cjs` (exit 0; the new cases fail on current code).
   Traps: `shownFields` (line 93) lists `title, subtitle, status, info`. The new text lands in `subtitle` and `info`, so nothing is added to the list. Do not add a field to row objects without adding it there. `Polling.js` and the QML are not touched. Fixed strings only (#24); the age comes from `detail.updated`, which polling wrote (not GitHub text). `duration()` uses `completed_at` first, so completed jobs don't change.

7. `ActionsPanel.qml` and `tests/qml-smoke.py`: wiring (decisions 1, 4, 8, 9).
   - `adopt()` (line 122): set `expanded = polling.expanded` after the `details` copy and before `rebuild()`. Set `error = polling.error || polling.catalogueBlocked`. Replace line 129 with an unconditional `selectionChanged(false)`.
   - `rebuild()` (line 74): `Model.rows(repos, expanded, details, filterText, now, polling.selected && polling.inspected ? polling.selected + ":" + polling.inspected : "")`.
   - `selectionChanged()` (line 118): add `rebuild()` as its last statement.
   - `status()` (line 60): add `pollSelected: polling.selected, pollInspected: polling.inspected, remaining: polling.remaining, resetAt: polling.resetAt`.
   - `tests/qml-smoke.py`:
     - Fake helper (lines 29-37): add `elif kind=='account': data={'login':'tester'}` before the final `else`.
     - Fixture (lines 98-100): set `panel.polling.expanded={"repo:one/repo":true}` instead of `panel.expanded=...`, then `adopt()`.
     - After the "tick keeps scroll" check, add the scenario: with the cursor on run 7, save `panel.polling.repos[0].runs`, set it to `[]`, call `panel.adopt()`, and check that `JSON.parse(panel.status())` has `pollSelected === panel.current.repo` and `pollInspected === (panel.current.run || "")`. Then restore the runs and call `adopt()`. The cursor is now on `two/repo` (selection fell back to a clamped index, and restoring keeps that key), so call `panel.move(-1)` and check `panel.current.kind === "run"` before the later `panel.expand(false)`, which needs the run row.
     - Add a check that `status()` has `remaining` and `resetAt` keys.
   → verify by `node tests/model.cjs && node tests/polling.cjs` (still exit 0), `nix flake check -L`, and then once, on a host with the Omarchy shell (razer), `python3 tests/qml-smoke.py` (prints `QML_CHECKS_PASSED`). The new highlight scenario fails on current code.
   Traps: `panel.move(1)` after the restore would stay on the last row (`two/repo`) and fail the later expand check; use `move(-1)` and the kind check. Quickshell 0.3.1 `Process` quirks (#24): a failed start emits neither `started` nor `exited`, only `running=false`; none of `pump()`, `failedToStart()`, `receivePage()` or `requestProc` is edited, and `account` goes through the same `requestProc`. Do not add `Qt.callLater` gating. `adopt()` must assign `expanded` before `rebuild()`, or an account clear leaves old expanded flags in the QML object. `selectionChanged()` already guards `if (!polling) return`, so adding `rebuild()` after that guard is safe. The #36 no-rerun rule applies to the smoke test: run it once, and fix the cause if it fails. The smoke fake helper keeps the 200 KiB padded chunked reply (#36). nixarchy owns the menu: `menu.py` and `menu.example.json` are not touched.

8. `README.md:168-170`: update the polling text. Say that a catalogue permission failure stops catalogue requests until `r`, `R` or reopen. Describe the quota slowdown (background checks of non-selected repositories slow 3x below 1,000 remaining and 10x below 300, until GitHub's reset time; the selected repository and the inspected run keep full pace). Describe the account check on open (one extra request; cached data shows first and is cleared if the `gh` login differs; a switch while open is not detected). Describe the `jobs N old, not refreshing` marker, jobs errors shown under the run, and that an unfinished expanded run missing from a snapshot gets its final status looked up. Edit the sentence on permission failures so it no longer implies the catalogue retries. Keep the existing `TIMING` references accurate (`quotaEase`, `quotaTight` are new names).
   → verify by `grep -n "not refreshing\|quotaEase\|account" README.md` (each found) and `nix flake check -L`.
   Traps: README only; no new settings or keys are documented because none exist. Fixed wording, no claims about quota that the spec did not make.

9. Session: full "Tests" section, live checks, PR.
   - Run the commands in "Tests". Record each new case failing on `main` and passing on the branch in the PR's evidence table.
   - Live checks on razer, then p620 (the user looks at the panel), from the spec:
     1. `python3 actions.py page '{"kind":"account","requestId":1}'` prints the login and nothing else from the profile.
     2. With a token that can't read `/user/repos`, check from `status()` that the catalogue is requested once. Press `r` and check it is requested once more.
     3. Go offline, expand a run: it shows an error under it, not "Loading jobs…". Come back online and press `r`: the jobs load without waiting for the backoff.
     4. `gh auth switch`, reopen: the old repositories disappear and the new account's load.
     5. Expand two runs and move between them. The one you left shows `not refreshing` with its age and its timers stop.
     6. Record request counts from `status()` before and after, as #30 did.
   - Push and open the PR. It links intent, spec and plan, says which steps the coder and codex did, and lists the base SHA. A fresh `model: "opus"` agent reviews the `git diff` against this plan, and codex reviews read-only (advice only). Merge is the owner's call. Verify that CI (`nix flake check`) is green on the PR.
   Traps: argument arrays and `github.com` pinning for any command run against the helper; no tokens printed; no reruns of failing tests (#36); no commits by codex or coder.

## Tests

Run from the repository root. Each command must pass the first time it is run.

```sh
node tests/model.cjs                                       # exit 0
node tests/polling.cjs                                     # exit 0
python3 -m unittest tests/test_actions.py tests/test_menu.py   # OK, no failures
nix flake check -L                                         # all checks passed (runs unittest discovery, model.cjs, polling.cjs, missing-directory check; not the real smoke test)
python3 tests/qml-smoke.py                                 # prints QML_CHECKS_PASSED, exit 0; needs OMARCHY_PATH and a theme: run once, on razer
```

New cases by file (each fails on current `main`, except the `select()` guard in step 3):
- `tests/polling.cjs`: account gate, switch and permission, stale `account` reply, `manual()` due, catalogue stop and restart, jobs error, stale queued run, prune (full summary, activity, removed repository), quota tiers.
- `tests/model.cjs`: `not refreshing` marker, fresh and final cases, job error with cached jobs.
- `tests/test_actions.py`: bad steps, `account` kind, catalogue 403 text.
- `tests/qml-smoke.py`: `account` branch in the fake helper, highlight and polling target agreement, `remaining` and `resetAt` in `status()`.

## Rollback

All changes are in one PR with one commit per step, so `git revert` of the merge commit restores `main` exactly. There are no new files, settings, stored state or dependencies, so nothing else needs cleaning up. If a live check fails on a host, revert the PR merge and run `omarchy-restart-shell`. A shell restart clears all in-memory polling state, including `account`, `catalogueBlocked`, `remaining` and cached details. Partial rollback: step 2 (the account gate) can be reverted on its own, since it is the only step that changes what request starts first, but steps 3 and 5 use the `reopen()` fixture helper and need their tests adjusted.

## Deviations needing approval

None. The plan implements the spec as approved. One reading to confirm at plan approval:
- Spec Verification says `account` "doesn't accept a repo". The plan rejects a non-empty `repo` on an `account` task and allows an absent or empty one, because the scheduler always sends `repo: ""` (`Polling.js:112`). Rejecting any non-`None` value would stop every scheduled account check. This was a review finding; it follows the spec's wording.
- In step 4 the existing `permission` jobs line stays as an empty branch (`else if (t.kind==="jobs") {}`) so the new shared jobs write doesn't make jobs errors fall into the run-lookup branch. Output is identical to the spec's description.
