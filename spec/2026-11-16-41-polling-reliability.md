---
status: approved
issue: 41
intent: intent/2026-11-16-41-polling-reliability.md
---

# Spec: Polling stops retry loops, stale runs and stuck loading states

## Design

### Scope

Nine fixes land on one branch as one PR. This was the owner's call (decision 8). They touch `Polling.js`, `ActionsModel.js`, `ActionsPanel.qml` and `actions.py`, plus the README polling section (lines 168-170) and the tests.

There are no new files, dependencies, settings, keys or QML modules. Polling stays as it is. There is no daemon, no polling while the panel is closed, no state file, and no token read or stored. Requests are still argument arrays pinned to `github.com`. All new text shown in the panel comes from a fixed set (#24). Untrusted GitHub text still goes through `plain()` (#32).

All line numbers below are from the current `main` (after #24, #30, #32, #36).

### Decisions (binding, from the owner)

1. **Catalogue 403.** After the first permission failure the panel stops asking for the catalogue until a manual refresh (`r` or `R`) or a reopen.
2. **Bad steps.** The helper rejects the whole jobs reply if any step is not an object. The user sees an error under that run.
3. **Account switch.** The panel checks the `gh` login when it opens, and clears repos, details and expanded flags if the login differs. A switch while the panel stays open is not detected.
4. **Quota.** Background polling slows down as remaining quota falls. This spec sets the thresholds.
5. **Stale queued runs.** They are corrected for the selected repository and for expanded or inspected runs.
6. **Expanded runs you left.** They are marked "not refreshing" with their age, and their timers stop.
7. **Memory.** Cached job details for runs that are no longer listed are dropped.
8. **Scope.** One branch, one PR.

### 1. A catalogue 403 stops the loop (`Polling.js`)

**What happens today.** In `complete()` the `permission` branch (lines 187-191) only blocks tasks that have a repository (line 188). It then deletes the task. A catalogue task has no repository, and `s.discover` stays true. The next `seed()` recreates the task (line 64), up to 60 times a minute.

**The change.**

- In the `permission` branch, add a first case for `t.kind === "catalogue"`. It sets `s.discover = false` and `s.catalogueBlocked = s.error`. The task is still deleted.
- `manual()` (line 41) re-enables discovery when `catalogue` is true, as it does now. It does the same when `s.catalogueBlocked` is set, so `r` also retries a blocked catalogue (decision 1 says `r` / `R`). It clears the flag.
- `open()` (line 28) clears the flag and sets `s.discover = true`. It does this even when `catalogueComplete` is true and the cache is under 5 minutes old, because the earlier failure is the reason to try again.
- Repositories already known stay listed. A failed catalogue never reaches the removal step at lines 222-227.
- **Message.** `s.error` is cleared by any later successful request (line 200). So `adopt()` shows `polling.error || polling.catalogueBlocked`, and the message stays up while the catalogue is blocked. The helper gives the catalogue its own fixed text, `Repository list unavailable; token cannot read your repositories`. It replaces the generic 403/404 text only for `kind == "catalogue"` (`actions.py:166-167`).

### 2. A failed jobs fetch is never "Loading jobs…" (`Polling.js`)

**What happens today.** Only a `permission` error writes `details[...].error` (line 189). Other errors go to the `else` branch (lines 192-197), which sets only the backoff and the repository error. `Model.rows()` shows "Loading jobs…" whenever there is no detail (`ActionsModel.js:67-68`).

**The change.** In `complete()`, when `t.kind === "jobs"` and any error comes back, write the error into the detail entry. Keep the existing `jobs`, `updated` and `jobsAt`. Set `unavailable` only for `permission`, as today.

```js
if (t.kind==="jobs") { var dk=t.repo+":"+t.run;
    s.details[dk]=Object.assign({},s.details[dk]||{},{error:s.error});
    if (reply.errorType==="permission") Object.assign(s.details[dk],{jobsAt:now,unavailable:true}); }
```

- The `permission` code path keeps its current output. The new write sits before the `permission` / `else` split, so one write serves both.
- `ActionsModel.js:67` already renders `detail.error` as a message row and then still renders `detail.jobs`. So cached jobs stay visible with the error above them, and no model change is needed.
- A later successful fetch replaces the whole entry (line 241), which clears the error.
- Retry timing is unchanged. The task keeps its backoff `due`, and `ensure()` doesn't touch an existing task's `due`.
- This is also the path the owner's decision 2 relies on: a rejected jobs reply becomes a visible error under the run.

### 3. Queued and waiting runs get corrected (`Polling.js`)

**What happens today.** A run cached as `queued` has no `followupAt` and isn't `in_progress`, so it never gets a single-run lookup (lines 85-86). `kept()` (lines 146-148) keeps it through a summary (lines 235-236). If GitHub has stopped listing it, nothing refreshes it.

**The change.** At the end of a full summary (the `keep` filter at line 235), any kept run that is not `completed` and is missing from this snapshot (`t.all`) gets `awaitingFinal = true` and loses its `followupAt`. The existing run task then looks it up (line 85). This is the same mechanism `activity()` uses at line 158.

- **Which runs.** `kept()` means expanded in any repository, or the inspected run. A summary only runs for the selected repository. So in practice this covers the selected repository's unfinished runs that you have expanded or inspected. Unkept runs missing from the snapshot are already dropped at line 236.
- **Cost.** One lookup per such run, through the existing `run` task, with the existing 15 s spacing. The ceiling is the number of runs you have expanded in the selected repository. It is zero when none are stale.
- **What the user sees.** `state()` (`ActionsModel.js:14`) already shows "awaiting final status" for `awaitingFinal` runs.
- Runs in repositories that aren't selected are not corrected. **This is the spec's reading of decision 5** ("selected repository and expanded/inspected runs" read as: expanded or inspected runs of the selected repository). The wider reading (an expanded queued run in any repository) would need the background `activity()` path (`Polling.js:154-161`) to mark kept queued runs. Its request filters `in_progress` (`actions.py:77`), so a queued run is never in its reply and would be looked up on every pass, one request per 15 s per such run, indefinitely. The owner is asked to confirm the narrower reading at approval. See Risks.

### 4. The highlight and the polling target agree (`ActionsPanel.qml`)

**What happens today.** `adopt()` calls `selectionChanged(false)` only when the selected repository no longer exists (line 129). If the selected run disappears but its repository remains, the highlight moves to another row and `polling.selected` / `inspected` are not updated.

**The change.** `adopt()` always ends with `selectionChanged(false)`, and the condition is removed.

- `Polling.select()` (line 36) is idempotent when the repository hasn't changed. It only moves `stableAt` when the repository changes, and then by the normal settle time. So calling it on every reply costs nothing when nothing moved.
- `selectionChanged()` hands polling the QML `expanded` object. After an account clear (section 8) this has to be the cleared one, so `adopt()` also sets `expanded = polling.expanded`.
- **Check.** `status()` (line 60) gains `pollSelected` and `pollInspected`, so the smoke test can assert that they match the highlighted row after a reply that drops the selected run.

### 5. `r` moves a backing-off task (`Polling.js`)

**What happens today.** `ensure()` only updates `group` on an existing task (line 25). `manual()` passes `due = now` (lines 47, 50), which is ignored for a task that already exists. A failed summary or jobs task keeps `now + up to 5 minutes` (line 193).

**The change.** In `manual()`, keep the task returned by each `ensure()` call and set `t.due = Math.min(t.due, now)`. The failure count is left alone, because it resets on success (line 200).

- **What stays.** `next()` still returns null while `now < s.cooldown` (line 98), and still enforces the 1 s gap and 60 a minute (lines 99-100). So `r` never overrides a GitHub cooldown or the ceiling. A `rate` task's `due` is `s.cooldown` (line 193), so moving it earlier can't start it early.
- **Blocked catalogue.** `r` also re-enables the catalogue (section 1).
- **Account check.** `r` also moves a backing-off `account` task (section 8).

### 6. A bad step is rejected by the helper (`actions.py`)

- **Where.** `read_page()` lines 189-190 check that `steps` is a list. Extend the check to reject any step that is not a `dict`:
  `any(not isinstance(row.get("steps", []), list) or any(not isinstance(step, dict) for step in row.get("steps", [])) for row in body[key])`.
  This raises `ValueError("Invalid job steps")`, which the existing handler (line 208) turns into a `network` error.
- **The `isinstance(step, dict)` guard** at lines 193-195 is no longer needed and is removed.
- **What the user sees.** Today's message for invalid data is "GitHub request timed out or returned invalid data". With section 2 it shows under the run. The task retries with the normal backoff.
- **`null` steps.** `"steps": null` is already rejected, because `row.get("steps", [])` returns `None`, which is not a list.
- **Test change.** The string-step assertion at `tests/test_actions.py:201-203` flips to expect the error.
- **The model is not hardened.** After this, `ActionsModel.js:72` can't see a non-object step from the helper. #24 already guards the other side: `Polling.complete()` rejects any non-object item (lines 172-175).

### 7. Background polling slows as quota falls (`Polling.js`)

**What the helper gives us.** `read_page()` already returns `remaining` and `resetAt` on every reply, including errors. This was checked live on 2026-11-16 (`gh api --include user`): `X-Ratelimit-Limit`, `-Remaining`, `-Reset` and `-Resource: core` are all present.

**The change.**

- `complete()` records `s.remaining` and `s.resetAt` from every reply whose `remaining` is a number. `create()` starts them as `null` and `0`.
- A function `pace(s, now)` returns a multiplier. It is 1 when `remaining` is unknown or `now >= resetAt`. Otherwise it is 1 when `remaining >= 1000`, 3 when `remaining >= 300`, and 10 below that. `remaining === 0` keeps its existing cooldown handling (lines 176-181).
- **What is multiplied.** In `seed()` the interval for non-selected activity checks (line 74, the `TIMING.active` and `TIMING.idle` values) and the catalogue age check in `open()` (line 30) get `* pace(s, now)`.
- **What isn't.** Selected summary and activity, the inspected run's jobs, and single-run lookups keep full pace. Those are what the user is looking at, and they are bounded by what is on screen. At the tiers above, active repositories are checked every 45 s, then 150 s. Idle repositories are checked every 30 minutes, then 100 minutes.
- **Display.** Nothing new is shown. `status()` gains `remaining` and `resetAt`, so #42's status line can read them from polling state. A status line is #42's job (its decision 1), not this issue's.
- **Why those numbers.** GitHub's usual limit is 5,000 an hour (`X-Ratelimit-Limit: 5000` on the live check). The first tier starts at 20% of that. At the 60 a minute ceiling, 1,000 requests is under 17 minutes of one panel running flat out. Other limits exist (Enterprise Cloud has a higher one). Absolute numbers still work there. They only start slowing sooner relative to the limit.

### 8. A `gh` account switch clears cached data (`actions.py`, `Polling.js`, `ActionsPanel.qml`)

**One new request kind: `account`.** It is one extra request each time the panel opens (decision 3 accepts this). It goes through the same scheduler and budget as everything else.

- `actions.py` `page_endpoint()` (line 59): `account` is a valid kind and maps to `user`. It needs no `repo`.
- `read_page()`: for `account`, the body must be an object with a string `login` matching `[A-Za-z0-9-]+`. Otherwise it raises `ValueError`, which becomes the usual `network` error. `result["data"] = {"login": ...}`. Nothing else from the body is returned. `/user` carries a lot of profile data that the panel has no use for.
- `Polling.complete()` `okData`: `account` is treated like `run`, so the data must be an object (line 172).

**Polling state.**

- `create()` adds `account:""` and `accountChecked:false`.
- `open()` sets `accountChecked = false`.
- `seed()` creates the `account` task (group `interactive`, due now) whenever `!s.accountChecked`.
- **No other work is queued before the check.** While `!accountChecked`, `seed()` creates only the `account` task and nothing else, and `next()` only returns the `account` task. No catalogue, summary, activity or run request starts first, so a reply from the previous account can't be mixed with the new one, and no task from the previous account can exist when the login changes. On a switch, polling also sets `s.tasks = {}` before clearing the data, so no activity or run task for a repository of the old account survives.
- On success: if `s.account` is set and differs from the login, polling clears `repos`, `details`, `expanded`, `selected`, `inspected`, `catalogueComplete` and `catalogueBlocked`, and sets `discover = true`. Then it sets `s.account` and `accountChecked`, and deletes the task. A first-ever check just records the login.
- **`r` releases a backing-off check.** `manual()` also ensures the `account` task when `!accountChecked` and sets its `due = Math.min(due, now)`, like the summary and jobs tasks in section 5. Cooldown, the 1 s gap and the 60 a minute ceiling still apply. Without this, a failed check followed by reconnecting and pressing `r` would leave the whole panel waiting up to 5 minutes.
- **A failed check.** `network` or `rate` errors retry through the normal backoff and cooldown. `setup` and `auth` stop polling, as today. A `permission` error (some token types may not read `/user`) is treated as "can't tell". The check is marked done and nothing is cleared.

**Cached data on reopen.** Cached data is still shown straight away, as `spec/2026-09-16-9-smart-polling.md` decided. It is cleared only if the first reply shows a different account. The owner's decision 3 keeps this order.

**QML.** `adopt()` sets `expanded = polling.expanded` (see section 4) and calls `selectionChanged(false)`. After a clear, `rebuild()` leaves the cursor on a valid row.

**Side effect for #46.** `s.account` holds the active login for free. #46's account display can read it, and shouldn't make its own request.

### 9. Expanded runs you left are marked, and their timers stop (`ActionsModel.js`, `ActionsPanel.qml`)

**The idea.** Only the inspected run (selected repository, `polling.inspected`) is refreshed (`Polling.js:88-93`). Other expanded runs show data that is not updating.

**The change in `rows()`.**

- `rows()` gets one more argument, `live`, the key `repo:runId` of the inspected run (`polling.selected + ":" + polling.inspected`, or `""`). The call in `rebuild()` passes it.
- For an expanded run with a detail, `fresh` is true when the run is the live one, or when its jobs are final. Final means `run.status === "completed" && detail.finalAttempt === (run.run_attempt || 1)`, which is the test `seed()` already uses at line 92. Final data doesn't change, so it needs no marker.
- When `fresh` is false:
  - The run subtitle's stamp (line 62) reads `jobs 4m old, not refreshing` instead of `jobs fetched HH:MM:SS UTC`. The age is `now - Date.parse(detail.updated)`, in whole minutes below an hour and hours and minutes above, like `duration()`.
  - The job and step rows call `duration(item, Date.parse(detail.updated))` instead of using `now`, so the open-ended timers stop at the time of the last fetch. Completed jobs aren't affected, because `duration()` uses `completed_at` first (line 29).
- **Responsiveness.** Today `move()` doesn't rebuild. The marker would lag by up to one second (the `now` tick). `selectionChanged()` therefore calls `rebuild()` at the end, so the marker follows the cursor at once. A rebuild is cheap (about 1 ms at the largest displayed repository, from `spec/2026-09-24-30-large-repos.md`). `onFilterTextChanged` already calls `rebuild(true)` first, so the second rebuild there is harmless.
- **Not a regression of #23.** Live timers (`intent/2026-09-24-23-live-timers.md`) stay for everything being refreshed. Only data that has stopped refreshing stops ticking.

### 10. Cached job details for runs that are gone are dropped (`Polling.js`)

- A small helper `prune(s, r)` deletes every `s.details` key with the prefix `r.repo + ":"` whose run ID isn't in `r.runs`. It is called wherever `r.runs` is reassigned: when a full summary publishes `r.runs` (line 236), and at the end of `activity()` (lines 157-162), which also drops runs (partial pages, and the completed-history trim in `recent()`). `kept()` runs stay in `r.runs`, so the details of anything expanded or inspected stay, while a collapsed run that was once inspected loses its details when it goes, in an unselected repository too.
- When the catalogue removes a repository (lines 222-224), delete that repository's details by the same prefix.
- An account clear (section 8) already empties `details`.
- `adopt()` copies `polling.details` into the QML property (line 124), so deletions reach the panel.
- **Not done.** `expanded` flags for runs that have gone are not cleaned. They are small, inert keys, and they would need a second walk over the QML object. Decision 7 only asked for job details. See Risks.
- `close()` (line 33) is not changed. Reopening still shows cached data (`spec/2026-09-16-9-smart-polling.md`).

### Order and overlap with other open issues

#41 lands first (#42's decision 12).

- **#42 (panel UI).** It builds on #41. Its status line reads `polling.error`, `polling.catalogueBlocked`, `polling.remaining` and `polling.resetAt`, which this change makes available. Its decision 10 (failed or stale job data shown under the run) is sections 2 and 9. Section 9 changes the run subtitle that #42 decision 2 reformats (branch · event · actor · age · title). Whichever lands second reworks that line. #42 rebuilds the row list too, so `rows()`'s new `live` argument should be kept.
- **#43 (repo health).** It changes the per-repo request (no `in_progress` filter) and `activity()` in `Polling.js`. It will conflict textually with sections 3, 7 and 10. It rebases onto this. The `pace()` multiplier applies to whatever intervals it keeps.
- **#44 (logs and watch).** It adds new helper request kinds, so it touches `page_endpoint()` next to the `account` kind. A textual conflict only. Its watch notifications need polling for runs the user marked, which should use the same pace rule if they're background polling.
- **#45 (run actions).** Its writes "do not count toward the polling budget but respect a GitHub cooldown". The quota fields recorded here (section 7) should also be updated from write replies. That belongs to #45. Its "refresh the run immediately" can use the `manual()` change in section 5.
- **#46 (beyond the popup).** It wants the active login on screen. It should read `s.account` (section 8) and not add a second request. It lands after #41-#44.
- **#47 (CI smoke test).** It rewrites `tests/qml-smoke.py` with stubs and a headless compositor. The fake helper in the smoke test needs an `account` branch (see Verification). That change moves to #47's stubs if #47 lands first.

## Alternatives rejected

- **Catalogue 403: retry at a slower pace.** Retrying can't fix a missing permission, and the owner chose to stop (decision 1).
- **Catalogue 403: a `blocked` flag on a fake repository.** The catalogue has no repository, and the extra object would show up in the row list. One flag on the polling state is smaller.
- **Jobs error in a new per-run field.** `details[...].error` is already rendered by `rows()`, including with cached jobs. A second place would need a second render path.
- **Run lookups for every unfinished run in every repository** (the larger reading of intent question 5). The owner chose the selected repository plus expanded and inspected runs. The all-repositories option costs one request per unfinished run, every snapshot, for repositories nobody is looking at.
- **Drop a retained run that GitHub no longer lists** (intent question 5). This breaks the rule from #30 that the inspected run never disappears. A lookup keeps the run and corrects it.
- **Keep the step and drop only the bad entry** (intent question 2). The owner chose to reject the whole reply (decision 2). It is also the smaller helper change, and it makes bad data visible.
- **Tolerate bad steps in `rows()`.** It hides the bad reply from the user and leaves the helper's contract unclear.
- **Account switch detected while open.** This would need a periodic `/user` request. The owner chose open-time only (decision 3).
- **Learn the account from `gh auth status --json hosts`.** It works locally and shows the active login (checked with gh 2.104.0). But it also tests every stored account against the API, takes a second process shape, and bypasses the scheduler's budget and cooldown. A single `/user` request goes through the existing path.
- **Clear all data on every reopen.** This loses the instant cached view that #9 decided on. The check clears only when the account differs.
- **Slow down all polling, including the selected repository.** The owner decided that interactive data keeps full pace (decision 4 says background).
- **A fraction-of-limit threshold** (for example 20% of `X-Ratelimit-Limit`). It needs the limit header kept as well. The absolute numbers work for the 5,000 limit that applies here and degrade safely elsewhere.
- **A quota line in this change.** It belongs to #42's status line (decision 1 there). This change only exposes the numbers.
- **Cap cached details at a number of recently viewed runs** (intent question 7). The owner chose to drop details for runs no longer listed. Details for runs that are still listed are bounded by what the summary keeps.
- **Refresh expanded runs in the background** (intent question 6). It multiplies jobs requests by the number of expanded runs. The owner chose to mark them.
- **Collapse a run when you leave it.** It destroys the view you built up and conflicts with #42's decision 5 (expansion survives filtering).
- **A `now` rebuild per tick for every expanded run** to show ages. Ages only need to move with the existing 1 Hz rebuild.

## Risks

- **Unselected repositories keep stale queued runs (owner to confirm).** Section 3 corrects only the selected repository's expanded and inspected runs, which is the spec's reading of decision 5. If the owner meant expanded runs in any repository, section 3 has to change (see the note there) before approval. A queued run you expanded in a repository you then left stays as it was until you select that repository again. The `jobs N old, not refreshing` marker (section 9) covers job data only, not the run's own status.
- **Follow-up polling of a hidden queued run.** After a lookup, a still-queued run keeps `followupAt` and is re-checked every 15 s (line 85) until it starts. With the new marking this applies to kept queued runs that are hidden beyond the first 100. The count is bounded by what you have expanded.
- **A permanent bad step keeps retrying.** A jobs reply that always has a bad step is a `network` error that retries every 5 minutes at most (`retryMax`). GitHub never sends one in practice. It is bounded by the backoff.
- **`/user` may not work for every token.** A GitHub App installation token can't call `/user`. A fine-grained PAT can. Those cases fall under the `permission` rule (nothing cleared, polling goes on). This was not tested against an app token.
- **A switch while the panel is open is not seen** (decision 3). The panel then polls as the new account while showing the old account's repositories until the next open or `R`.
- **A request more on every open.** Toggling the panel quickly costs one extra request each time. The scheduler's 1 s gap and 60 a minute still apply.
- **The account gate delays all data on open.** Until `/user` replies, nothing else starts (cached data still shows). On a slow network that is one round trip. If `/user` keeps failing with `network`, the whole panel waits with it, even if other endpoints are healthy. This is worse than the other requests failing too, and is why `r` releases the gate (section 8) and a `permission` error marks the check done. It is bounded by the backoff (5 minutes at most).
- **Quota thresholds are guesses.** They are absolute (1,000 and 300), not tied to `X-Ratelimit-Limit`. Idle repositories can show data up to 100 minutes old in the lowest tier. `remaining` is only as fresh as the last reply, and resets at `resetAt`.
- **`rebuild()` on every selection change.** This is a few more rebuilds per key press. At the worst case (about 512 rows) a rebuild is about 1.3 ms.
- **Expanded flags are not cleaned** (decision 7 covers details only). A flag for a run that is gone stays in the object until the filter changes or an account clear. It costs a few bytes and does nothing.
- **Merge order** with #42-#47 (see the overlap section). All of them touch `ActionsPanel.qml`, `Polling.js` or `tests/qml-smoke.py`. Each rebases onto this PR, and the tests run again.
- **Hosts.** The helper and `Polling.js` behave the same on every host. Only the real-QML smoke test and the live checks need a host with the Omarchy shell, such as razer or p620.

## Verification

Each new case fails on current `main`.

**Commands**

```
node tests/model.cjs
node tests/polling.cjs
python3 -m unittest tests/test_actions.py tests/test_menu.py
nix flake check
python3 tests/qml-smoke.py
```

`nix flake check` runs the unittest discovery, `model.cjs`, `polling.cjs` and the missing-directory check on `qml-smoke.py`. It does not run the real smoke test, so `python3 tests/qml-smoke.py` is run on its own on a host with the Omarchy shell.

**tests/polling.cjs**

- **Catalogue 403 (section 1).** A catalogue `permission` error sets `discover` false and `catalogueBlocked`. Over 60 simulated seconds `next()` returns no more catalogue requests (the current code returns up to 60). `manual(s, now, false)` and `manual(s, now, true)` both start one again. `open()` does too.
- **Known repositories survive** the failed catalogue.
- **Jobs error (section 2).** A `network` error on a jobs task writes `details[...].error` and keeps the cached `jobs`. With no cache the entry has an error and no jobs. The next success removes it. A `permission` error still sets `unavailable`.
- **Stale queued run (section 3).** A queued run that is expanded or inspected and missing from a full snapshot gets `awaitingFinal` and one `run` request. After the lookup returns `completed`, the cached status is `completed`. A queued run that isn't kept is dropped, as today. A run present in the snapshot is not marked.
- **`manual()` (section 5).** A summary task with `due = now + 300000` after repeated failures starts at `now` after `manual()`. With `cooldown` in the future it doesn't start. With 60 starts in the window it doesn't start.
- **`select()` is idempotent (section 4).** Calling it again with the same repository doesn't move `stableAt`.
- **Quota (section 7).** `remaining` and `resetAt` are recorded. With `remaining: 400` and a future `resetAt`, a non-selected active repository checked 20 s ago is not due, but the selected repository is. With `remaining: 100` the idle interval is 10 times longer. After `resetAt` the multiplier is 1.
- **Account (section 8).**
  - After `open()`, `next()` returns only the `account` request.
  - A different login clears `repos`, `details`, `expanded`, `selected` and `inspected` and sets `discover`.
  - The same login clears nothing.
  - A `permission` error on the check clears nothing and releases the gate.
  - A stale `account` reply after close/reopen is rejected by `requestId` / `generation`.
  - `manual()` moves a backing-off `account` task to `now`, but not past a cooldown.
  - On a switch, queued activity and run tasks of the old account are gone.
- **Memory (section 10).** After a full summary, `details` for run IDs not in `r.runs` are gone and details for an expanded or inspected run stay. A removed repository loses its details.
- **Prune on activity (section 10).** A previously inspected, now collapsed run dropped by `activity()` in an unselected repository loses its details.
- The existing scheduler workload checks (budget, spacing, fairness) still pass. The test helper that builds replies gets an `account` branch. Fixtures that expect a first request of another kind (`tests/polling.cjs:102`, `:183`) start from a completed account check (`accountChecked = true`). Only the lifecycle tests exercise the real gate.

**tests/model.cjs**

- With `live` set to another run, an expanded run with non-final details shows `not refreshing` and its age in the subtitle. Its in-progress job's `info` uses the fetch time, so it doesn't change when `now` advances.
- For the live run, the subtitle still reads `jobs fetched ... UTC` and timers still use `now`.
- A completed run with `finalAttempt` equal to its attempt shows no marker.
- A jobs detail with `error` and cached jobs shows the message row and the jobs.

**tests/test_actions.py**

- A jobs page with `steps: [None]`, `steps: ["x"]` and `steps: [1]` returns `errorType == "network"`. This replaces the assertion at lines 201-203.
- A jobs page with valid steps passes, with names still run through `plain()`.
- The `account` kind: `page_endpoint` returns `user`. A valid body gives `data == {"login": "..."}` and nothing else from the body. A missing or non-string login, or a login with a space or control character, gives the `network` error.
- A catalogue 403 gives the new fixed message. A summary 403 keeps the old one.
- `account` still needs a valid `requestId`, and doesn't accept a `repo`.

**tests/qml-smoke.py**

- The fake helper gets an `account` branch, returning `{'login': 'tester'}`. Without it the existing run shape fails the `okData` check.
- The fixture sets `panel.expanded` only (`tests/qml-smoke.py:98-100`), and `adopt()` now assigns `expanded = polling.expanded`. The fixture sets `panel.polling.expanded` instead, so the expansion is kept.
- A scenario where a reply drops the selected run asserts that `status()`'s `pollSelected` and `pollInspected` match the highlighted row's repository and run. The current code fails this.
- `status()` also reports `remaining` and `resetAt`.

**Live checks (razer, then p620)**

1. Run `python3 actions.py page '{"kind":"account","requestId":1}'`. It should print the login and nothing else from the profile.
2. Open the panel with a token that can't read `/user/repos`. Check from `status()` that the catalogue is requested once. Press `r`, and check it is requested once more.
3. Go offline, expand a run, and check that the run shows an error under it, not "Loading jobs…". Come back online and press `r`. Jobs load without waiting for the backoff.
4. Run `gh auth switch`, reopen the panel, and check that the old account's repositories disappear and the new account's load.
5. Expand two runs and move between them. The one you left shows `not refreshing` with its age, and its timers stop.
6. Record the request counts from `status()` before and after, as #30 did.

**Docs.** README lines 168-170 now say that a catalogue permission failure stops catalogue requests until `r`, `R` or reopen, and describe the quota slowdown, the account check on open, and the "not refreshing" marker. The PR links the intent, spec and plan.

## What I could not verify

- Whether `GET /user` works for every token type. It works for the classic token in use here (checked live on 2026-11-16, and the rate headers are present). GitHub's documentation says fine-grained tokens work. I did not check app installation tokens, so the `permission` fallback is defensive.
- Exact GitHub behaviour when a queued run vanishes from the status lists. The design relies on the existing single-run lookup (`runs/{id}`), which #24 and #30 already use.
- Quota behaviour on GitHub Enterprise. Out of scope, since the host is pinned to `github.com`.
- The quota thresholds (1,000 and 300) are a judgement. They have not been tuned against real use. The numbers are named constants in `TIMING`, so they are easy to change.
- Real QML behaviour of `selectionChanged()` calling `rebuild()` was not run. The smoke test covers it on a host with the Omarchy shell.
- The Codex review (gpt-6.1-sol) did not run the proposed implementation, real QML, `nix flake check` or live GitHub checks, and neither did this revision.
