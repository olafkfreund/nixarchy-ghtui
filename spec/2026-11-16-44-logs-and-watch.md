---
status: draft
issue: 44
intent: intent/2026-11-16-44-logs-and-watch.md
---

# Spec: Read failed logs and get notified when a run finishes

## Design

### Scope

Two features, two PRs, logs first. This is the owner's order (decision 10).

1. **PR A, logs.** Press `v` on a failed run, a job or a step. The panel fetches the log through the existing scheduler, then opens it in a terminal.
2. **PR B, watch.** Press `w` on an unfinished run. When it finishes, a desktop notification says so. This works with the panel closed.

New keys are `v` (view log) and `w` (watch). Both are free in `ActionsPanel.qml` lines 234-253. #42 takes `y ? g G`, so there is no clash. #45 has not chosen its keys. `v` and `w` are reserved here.

The plugin's rules stay:

- Argument arrays, never shell strings.
- Host pinned to github.com.
- No token storage.
- Read-only.
- Theme-native: the panel itself draws nothing new, apart from one marker on watched runs.
- Keyboard-first.

New runtime commands: `omarchy-launch-tui`, `less` and `notify-send`. All three are declared in `flake.nix` and the README (decision 9).

### Owner decisions (binding)

1. **Logs open in a terminal**, using Omarchy's own terminal launcher.
2. **A notification arrives even after the panel is closed.** This bends "no polling while closed" and "no background daemon" (README lines 3 and 170). The rest of this spec makes the bend opt-in, per run, bounded and visible.
3. **Notifications are shown with `notify-send`.**
4. **The terminal comes from Omarchy's launcher.** Verified below: `omarchy-launch-tui`.
5. **A failed job shows its failed steps only. Any other completed job shows the full log.**
6. **The user marks a run to watch. Watching ends when the run completes.**
7. **The notification says repository, workflow and result.**
8. **Only runs the user marked** notify. No "any failure in this repository".
9. **New runtime dependencies go in `flake.nix` `runtimeDeps` and the README.**
10. **Logs ship first, then watch.**

### What I checked

On 2026-11-16, with gh 2.104.0 against `olafkfreund/nixarchy-ghtui`, and on this Omarchy install:

- **Omarchy's launcher.** `$OMARCHY_PATH/bin/omarchy-launch-tui [--app-id=<id>] <command> [args...]` ends in `exec setsid uwsm-app -- xdg-terminal-exec --app-id=$APP_ID -e "$1" "${@:2}"`. Arguments pass through as an array. It opens the user's default terminal with Omarchy styling.
  - `omarchy-launch-terminal` also takes a command. It copies the working directory of the active window through `hyprctl`. The panel is a layer-shell surface, so that lookup is meaningless here.
  - `omarchy-launch-floating-terminal-with-presentation` joins its arguments into a `bash -c` string, which breaks the argument-array rule.
  - `omarchy-launch-tui` is the right one.
- **Notification service.** `org.freedesktop.Notifications` is owned on the session bus by the running Quickshell process (`busctl --user list`). `notify-send` is on PATH.
  - Omarchy also ships `omarchy-notification-send`. The owner chose `notify-send`, so I did not use it.
  - I did not send a test notification, so how this shell draws one is unverified.
- **`gh run view` flags.** `--job <id>`, `--log`, `--log-failed` and `-R [HOST/]OWNER/REPO` exist.
  - `-R github.com/olafkfreund/nixarchy-ghtui --job 107727818137 --log-failed` printed only the failed step (step 4, "Run nix flake check -L"), as `job<TAB>step<TAB>line` rows. It needs no run id.
  - `--log-failed` on a passing job exits 0 with empty output.
  - An unknown job exits non-zero with `failed to get job: HTTP 404`.
  - The output contains raw escape sequences (`^[[36;1m`), a BOM and `\r` line endings are possible, and every line has a timestamp. The panel must clean it.
- **Request cost.** `GH_DEBUG=api` showed three metadata GETs (job, run, workflow). The log download itself is not listed in that trace, so it is at least four requests per log. I could not see the log download in the trace.
- **`gh api .../jobs/<id>/logs`** returns 200 and plain text through a redirect. `gh api` refuses to print it unless `--allow-escape-sequences` is passed. A log fetched with the current `request()` helper would come back empty. That is one reason not to use it.
- **Not verified:**
  - What `gh run view --log` says for a job that is still running.
  - How Hyprland places an `org.omarchy.*` app id, floating or tiled.
  - How the shell's notification popup treats markup in the body.
  - `less` behaviour inside Omarchy's terminal under real use.

### Logs (PR A)

#### Which log, for which row

| Row | Rule |
| --- | --- |
| Job or step, job failed | `--log-failed` for that job: failed steps only (decision 5). |
| Job or step, job completed and not failed | `--log` for that job: the full log. |
| Job or step, job not completed | No fetch. The status line says logs are available when the job finishes. |
| Run, run failed | `--log-failed` for the whole run: every failed step in every failed job. |
| Run, not failed | No fetch. The status line says to select a job. |
| Repository, "more" or message rows | `v` does nothing. |

"Failed" means `failure`, `timed_out` or `startup_failure`. This is the same set `icon()` uses (`ActionsModel.js` line 19) and the same set #43 decision 4 uses. A step row uses its job's rule. I do not slice one step out of a log. See Alternatives.

For a failed run, the run-level command lists failed steps across jobs, so the run row needs no job ids.

#### Rows: `ActionsModel.js`

`rows()` adds a `job` field (the job id as a string) to job rows (line 73) and step rows (line 77). Today a job id appears only inside the row key (line 70). `key`, `kind` and `depth` are fixed by the key, so `shownFields` (line 93) does not change. No new field is read by the delegate.

A new pure function `logTarget(row, details, runs)` returns `{repo, run, job, mode}` or `{error: "<fixed text>"}`. `mode` is `failed` or `full`. It holds the table above, so it can be tested in Node. The run's conclusion comes from the cached run in `r.runs`. The job's comes from `details[...].jobs`.

#### Helper: `actions.py log` and `actions.py view`

Two new modes beside `page`. The `choices` tuple in `main()` (line 215) grows to `("page", "log", "view")`.

**`log '<json>'`** does one fetch and writes one cleaned file:

- The request is `{requestId, repo, run, job?, mode}`. It is validated with the same checks `page_endpoint` already makes: `repo_name` (line 19) and a positive-integer run id and, when present, job id (as at lines 71-73). `job` may be absent only for the run-level form, which requires `mode` `failed`. `mode` must be `failed` or `full`. `full` without a job is rejected.
- It runs `gh run view [--job <id> | <run>] --log-failed|--log -R github.com/<repo>`. All arguments are in an array. `github.com/` pins the host. This is the same rule as `--hostname github.com` at line 47.
- It reads stdout in 64 KiB chunks and keeps only the last 1 MiB. It keeps reading after that so `gh` never blocks on a full pipe. It reads stderr concurrently, as `communicate()` does today (line 48). It records whether it cut anything.
  - The tail is kept because the failure is at the end.
  - A hard timeout of 90 seconds replaces the 25 seconds `request()` uses (line 51), because it downloads a zip. It kills `gh` the same way `request()` does (lines 53-55).
- It cleans the text (below), prepends a header, and writes the result with `tempfile.mkstemp` in `$XDG_RUNTIME_DIR/nixarchy-ghtui/`. That directory is created with mode `0700`. The file is `0600` and its name is random.
  - The header is `repo`, run id, job id, mode and a line saying `complete`, `cut short: showing the last 1 MiB of N MiB`, or `lines cut: N lines longer than 2,000 characters were shortened`. Both cuts can apply. `complete` is written only when neither cut happened. The header uses only validated values. It never uses a job name.
  - If the cleaned output is empty, there is no file. The reply says "No failed steps in this log."
- The reply is the existing JSON shape plus `data: {path, mode, cutShort, lineCut}`. Errors use the existing `errorType` words, mapped from `gh`'s stderr, because there are no HTTP headers here. The checks run in this order, as the helper does for `page` (`actions.py` line 162), so a rate-limited 403 is a rate error:
  - `rate limit`, `HTTP 429` or `secondary rate` → `rate`.
  - `auth login` → `auth`.
  - `HTTP 401` → `auth`.
  - `HTTP 403` or `HTTP 404` → `permission`.
  - A missing `gh` → `setup`.
  - Anything else → `network`.
  - The text shown is fixed. Raw stderr goes to the shell log only, as in `Model.reply` (`ActionsModel.js` line 1).

**`view <path>`** is what the terminal runs. It checks the path is a regular file directly inside the runtime log directory, then runs `less -- <path>`, and deletes the file in a `finally`. Anything else exits with an error. The terminal command therefore carries no GitHub text at all, only a path the helper made.

Old files are removed too. Each `log` call deletes files in that directory older than one day, which covers a terminal that was killed before `view` could clean up.

#### Cleaning untrusted log text

The log is written by whoever controls the workflow, including a fork's pull request. Cleaning is done in `actions.py`, so nothing unclean reaches the terminal:

1. Decode as UTF-8 with replacement.
2. Remove ANSI sequences whole: CSI (`ESC [ ... final`), OSC (`ESC ] ... BEL` or `ESC \`), and a lone `ESC` plus one character. This is the step that makes `less` safe. Removing only the `ESC` byte would leave visible junk, and stripping only control characters would leave the sequence body.
3. Drop `\r`. Keep `\n` and `\t`.
4. For every line, drop `Cc` and `Cf` characters except ZWNJ and ZWJ (`JOINERS`, line 16). That removes bidi overrides and the BOM. It is the `plain()` rule (lines 27-32) applied per line. `plain()` itself cannot be reused, because it joins lines and turns tabs into spaces.
5. Cut any line over 2,000 characters and end it with `…`. Count the cut lines for the header.

`less` is run without `-R`, so even a missed sequence is shown as text, not obeyed. Secrets that GitHub's masking missed are not detectable here. They were already readable in the browser. The file is private (`0600`, runtime directory) and removed after viewing.

#### Scheduler: `Polling.js`

The log fetch is one more task kind, `log`. This keeps it under every ceiling the intent requires (gap, 60 a minute, one in flight, cooldown).

- **Task.** `Polling.requestLog(s, target, now)` calls `ensure(s, "log", repo, run, "interactive", now)` and then sets `t.job` and `t.mode` on the returned task. `ensure()` stores `t.run = String(run)` (line 22) and `next()` copies it into the request (line 112), so the run field must stay the plain run id. The composite `run:job` is not used. Only one `log` task exists at a time, so `key("log", repo, run)` is unique enough. `next()` adds `job` and `mode` to the request for `log`. A run-level request has no job: `job` is absent and `mode` is `failed`.
- **QML argv.** `pump()` (line 143) runs `["python3", helper, "page", ...]`. For `log` it runs `["python3", helper, "log", json]`. The mode word comes from the request kind, not from GitHub.
- **One shot.** A `log` task never retries on its own. `complete()` treats any error from a `log` task as final: it records `s.log = {error}`, deletes the task, and returns. The existing retry branch (lines 192-197) does not apply.
  - A `permission` error on a log (an expired log, or a log the token cannot read) must not set `r.blocked`. The branch at lines 187-191 would block the whole repository. The `log` check goes first.
  - `rate` still sets the cooldown (lines 176-181). `auth` and `setup` still stop polling (line 186), as for any task.
- **Result.** On success `s.log = {path, mode, cutShort, lineCut, repo, run, job}`. `adopt()` in `ActionsPanel.qml` (line 122) reads `polling.log` once, clears it, and acts on it.
- **`okData`.** The array check added by #24 must also accept `log`, as it does for `run`. Without that, the reply becomes a `setup` error. #24 is the approved design, so this is a one-word change when the code is rebased.
- **Cost per log.** `gh run view` makes at least four API calls per start (see What I checked), and the scheduler cannot space calls made inside one `gh` process. So a `log` start is charged as four slots: it pushes four entries onto `s.starts`, and the next start of any kind waits four gaps (4 seconds) after it. This keeps the 60-a-minute count honest and the average pace at one request a second, though the four calls inside the process are not spaced. The intent's "one second between requests" cannot be met exactly with `gh run view`. This is flagged for the owner under Risks. The multiplier of four is replaced by the figure measured in the live check.
- **One at a time.** `v` while a `log` task exists does nothing. The status line says a log is already being fetched.

#### Panel: `ActionsPanel.qml`

- `Keys.onPressed` (lines 234-253) gets `else if (event.key === Qt.Key_V) root.viewLog()`.
- `viewLog()` calls `Model.logTarget(...)`. On `error` it shows the fixed text in the status line. Otherwise it calls `Polling.requestLog`, shows "Fetching log…", and calls `pump()`.
- When `adopt()` finds `polling.log.path`:

  ```
  Quickshell.execDetached(["omarchy-launch-tui", "--app-id=org.omarchy.github-actions-log",
      "python3", helper, "view", path])
  ```
- If `polling.log.error` is set, it is shown. If the panel was closed in the meantime, the fetch result is dropped: `Polling.close()` clears `flight` and tasks (lines 33-35), and `close()` stops the helper (lines 54-58).
- The footer (line 372) gains `v log`. `keybindings.sh` (lines 5-24) and the README table gain the same line. #42's `?` sheet must list it too.

Where the message goes: #42 decision 1 adds an always-visible status line, and this work needs it. The landing order already puts #42 first, so #42 is a prerequisite for #44. The current search placeholder is not a fallback: it is hidden while a filter is typed (`ActionsPanel.qml` line 291), and `adopt()` overwrites `error` from `polling.error` (line 125). A `v` on a running job under a filter would show nothing. If #42 is not merged, #44 waits.

### Watch (PR B)

#### What the user sees

- `w` on an unfinished run marks it as watched. `w` again un-watches it. `w` on a finished run does nothing, and the status line says it has already finished with its result.
- A watched run row shows `watching` in its `info` (after the timer). `info` is already in `shownFields`, so the row updates without any change to `syncRows`.
- The header reads `… · 2 watched` while any run is watched. This is the only always-on sign inside the panel.
- Up to **5** runs can be watched at once. The sixth is refused, and the status line says so. This caps closed-panel traffic (see the budget below).
- A watch ends when the run completes, when the user un-watches it, or when the shell restarts. Nothing is written to disk (README line 3: "no database or token storage"). Marks live in the plugin's memory, as README line 168 already says for everything else.

#### Why this can run with the panel closed

`manifest.json` line 6 has `"keepLoaded": true`, so the QML item stays alive when the window is hidden. Its `Timer` and `Process` objects can keep working with `root.opened` false. So no daemon, service or second program is added. This bends one rule: the plugin now polls while closed, but only for runs the user marked.

#### Scheduler: `Polling.js`

Today `next()` returns null when closed (line 98) and `complete()` rejects replies when closed (line 169). `close()` wipes everything (lines 33-35). The change is small:

- **State.** `create()` gets `watches: {}` and `notices: []`. A watch is `{repo, run, name, at}`.
- **`Polling.watch(s, repo, run, name, now)`** adds or removes a watch. It refuses a sixth.
- **`next()`** continues when `s.opened` or `watches` is not empty. While closed, it considers only `run` tasks that belong to a watch. Today `next()` picks from every queued task, and an early return in `seed()` does not delete the tasks already queued, so the filter lives in `next()`.
- **`seed()`** (line 54) has one new rule. When the panel is closed, it creates only the watch tasks and returns early: no catalogue, summary, activity or jobs tasks.
- **Watch task.** One existing `run` task per watch: `ensure(s, "run", repo, id, "active", age(w.at, TIMING.watch))`. `w.at` is the time of the last lookup. `complete()` sets `w.at = now` on every `run` reply for a watched run, and the watch is also stamped when it is created. Without this the deadline never moves and `seed()` would recreate an already-due task on every tick, so one watch could use the whole 60 a minute. The existing 15-second follow-up (line 85) applies to runs that the panel itself is waiting on. A watched run uses the later of the two deadlines, so a run is not fetched twice in a row.
  - It uses the `run` lookup (`GET repos/<repo>/actions/runs/<id>`), which `complete()` already merges into `r.runs` (lines 203-212).
  - The group is `active`, because `next()` only knows the groups `interactive`, `active` and `background` (lines 105-108). A new group would never be picked.
  - `TIMING.watch` is 30,000 ms. This is my choice, not an owner decision. A notification up to 30 seconds late is acceptable, and it keeps the traffic low.
- **`complete()`** accepts replies when `s.opened` or `watches` is not empty.
  - While closed, a `run` reply does not queue a `jobs` task (the code at line 208 does this for the inspected run). Unwatching also deletes that run's queued `run` task unless the panel is open and is waiting on it.
  - On a `run` reply whose status is `completed` and which has a watch, it pushes `{kind: "done", repo, name, conclusion}` onto `s.notices` and deletes the watch.
  - Re-run of a watched run: the watch ends only when the run is `completed`. If the run id comes back unfinished with a higher `run_attempt`, it is still the same watch. A re-run after the watch ended needs a new `w`. This matches decision 6.
  - An `auth` or `setup` error while closed pushes one `{kind: "paused"}` notice. The watches stay. Polling stays stopped until the panel is opened, because `open()` clears `s.auth` (line 29). Without this, the feature would fail in silence, which is the worst result for a notify tool.
  - A `permission` error on a watched run pushes `{kind: "lost", repo, name}` and drops that watch. The existing branch sets `lookupError` on the run (line 190). The panel shows "unavailable" for it, as it does today.
  - Network and rate errors use the existing backoff and cooldown (lines 176-181 and 192-197). They need no new code.
- **`close()`** is unchanged. It clears tasks and cancels the flight, and `seed()` recreates the watch tasks on the next tick. It does not clear `watches`.
- **Account change.** #41 decision 3 clears repos, details and expanded when the gh login differs on open. It must clear `watches` too, because the new account may not see those runs. This is a one-line addition to #41's reset.
- **Quota slowdown.** #41 decision 4 slows background polling as remaining quota falls. Watch tasks are background polling and must use the same multiplier on `TIMING.watch`. Whichever lands second wires this in.

#### Budget while closed

The scheduler's ceilings are unchanged. All watch lookups go through `next()`, so the 1-second gap, 60 a minute and one-in-flight limits still hold. The intent's "stay within the existing ceilings" is kept.

The new steady cost is `2 × watched` requests a minute when closed: 10 a minute at most, from the cap of 5. That is one sixth of the 60 a minute ceiling, and it shares the account quota with `gh` and everything else, as README line 172 already says.

While the panel is open, watch lookups run on top of the normal polling. That is up to 10 extra requests a minute, within the same ceilings.

#### Panel: `ActionsPanel.qml`

- A `readonly property bool watching: Object.keys(polling.watches).length > 0`.
- The `pump` timer (line 189) runs when `root.opened || root.watching`. `pump()` (line 137) and `receivePage` allow the same condition. The one-second `now` timer (line 190) stays `opened` only, so the full rebuild at 1 Hz does not run while closed.
- `adopt()` (line 122) skips `rebuild()` when closed. `open()` (line 43) calls `rebuild()` so the rows are fresh on reopen. Without that, reopening would show rows from before the closed period.
- `adopt()` drains `polling.notices`. For each one it calls:

  ```
  Quickshell.execDetached(["notify-send", "--app-name", "GitHub Actions", "--", title, body])
  ```

  `Model.notice(n)` builds `title` and `body`.
- `w` calls `root.toggleWatch()`.
- `w` and `v` go in the footer, `keybindings.sh` and the README.

#### Notification text: `ActionsModel.js`

`Model.notice(n)` is a pure function:

- **Done.** Title is the result. Body is `<owner/repo> · <workflow>`.
- **Paused.** Title is "Watching paused". Body is "Run gh auth login, then open the panel".
- **Lost.** Title is "Watch stopped". Body is `<owner/repo> · <workflow>` and "GitHub no longer shows this run."
- **Result words are fixed.** The conclusion maps to a table:

  | Conclusion | Words |
  | --- | --- |
  | `success` | succeeded |
  | `failure` | failed |
  | `cancelled` | cancelled |
  | `timed_out` | timed out |
  | `startup_failure` | failed to start |
  | `skipped` | skipped |
  | `neutral`, `action_required`, `stale` | finished |
  | anything else | finished |

  This is a wider split than #43's "failed" set, because decision 7 only fixes the three fields. It is a table, so the owner can reduce it by editing one object.
- **Only two strings from GitHub reach the text.** The repository name passes `repo_name`. The workflow name was cleaned by `plain_fields` in the helper (lines 35-39 and 192). The notification daemon may read markup in a body, such as `<b>` or `<a href>`, and I could not verify this shell's behaviour. So `notice()` also replaces `<`, `>` and `&` with a space and cuts the name to 80 characters. A workflow name such as `R&D build` becomes `R D build`. That is cosmetic and safe in both cases: a daemon that shows plain text, and one that reads markup.
- **Clicking.** Plain `notify-send` has no click action. Decision 3 chose it, so clicking does nothing. See Alternatives.

#### Interactions with #41-#47

- **Order.** #41, then #42, then #43, then #44, then #46 (decision 10 in #46: it lands after #41 to #44). #47 is independent and lands when it is ready.
- **#41 (polling).** Same file region: `seed()`, `complete()`, `close()`. One branch and one PR for #41 means #44 rebases onto it. #41's catalogue stop after a 403, its account check and its quota slowdown each need one line for watches (above). If #44 lands first, #41 inherits the watch rules.
- **#42 (panel UI).** Same region: the run-row `subtitle` (`ActionsModel.js` lines 63-65), the footer and the key handler. #42 changes what the subtitle says, and this work adds `watching` to `info` only, so the only conflict is textual. #42's status line is where `v` and `w` print their messages, which makes #42 a prerequisite. #42's accessibility properties must cover the `watching` marker (decision 11), and its smoke test covers it.
- **#43 (repo health).** It adds a last-result request per repository. A watched run could reuse that, but this work does not depend on it. Same files, no semantic overlap.
- **#45 (run actions).** Rerun and cancel use keys #45 picks, so it must avoid `v` and `w`. A rerun of a watched run that already finished has no watch left, so the user presses `w` again once the new attempt is queued. `w` works on queued runs. #45's writes do not count toward the budget and `log` tasks do. That is deliberate: a log fetch is a read.
- **#46 (beyond the popup).** The detail pane shows what the run already carries. It has no log and no watch state, so no conflict. A bar indicator for "watching" would give closed-state visibility. It is a separate issue by #46 decision 1, and `watches` is the one field it would read.
- **#47 (CI smoke test).** Its stubs and real-key tests can later drive `v` and `w` through the same PATH stubs used here.

## Alternatives rejected

- **Fetch the log inside the terminal.** `view` would call `gh` itself and pipe to `less`. That removes the temp file. It also makes a request the scheduler never counts, with no cooldown check and no gap. The intent says any option outside the scheduler breaks the budget constraint, and the owner did not relax it. A temp file is the price of staying inside it.
- **Show the log inside the panel.** The intent notes it is safer but more work. The owner chose the terminal (decision 1). It also gives the user their own search and scrollback.
- **`omarchy-launch-terminal` or `xdg-terminal-exec` directly.** `omarchy-launch-terminal` looks up the active window's working directory, which is wrong for a layer-shell panel. `xdg-terminal-exec` alone skips Omarchy's wrapper and app id. `omarchy-launch-tui` is the launcher Omarchy provides for this.
- **`omarchy-launch-floating-terminal-with-presentation`.** It builds a `bash -c` string from its arguments. That breaks the argument-array rule.
- **`gh api .../jobs/<id>/logs` for full logs, and `gh run view` only for failed ones.** One API call instead of four for the full-log case, and it would let the scheduler space each call. But `gh api` needs `--allow-escape-sequences`, the existing `request()` has a 25-second timeout and no size cap, the run-level form has no single endpoint, and two code paths double the tests. One `gh run view` path is smaller. The extra requests are the cost, and the risks list them. If the owner wants exact one-second spacing, this is the route.
- **Cut the failed step out of the job log by timestamp.** Each log line carries a time, and a failed step has `started_at` and `completed_at` in whole seconds. Lines near a boundary would land in the wrong step. `gh run view --log-failed` already gets this right from GitHub's per-step files.
- **Slice one step for a step row.** `gh` has no per-step flag. A step row therefore opens its job's log. The header says which.
- **A full-log key for failed jobs.** Decision 5 says failed steps only. If the owner later wants both, the same helper mode takes `full`, and one more key is a small change.
- **Zip logs from `actions/runs/<id>/logs`.** It needs an unzip and a size policy. `gh run view` does it already.
- **An outside watcher** (a systemd user timer, or a separate program running `gh run watch`). It would add a second program with its own requests that bypass the scheduler. The `keepLoaded` plugin already stays alive, so nothing outside is needed.
- **Watching every run in a repository, or every failure** (intent question 8). The owner said no (decision 8).
- **Persist watches in a file** so they survive a shell restart. It adds storage the README says does not exist, and a stale watch can outlive the run. The owner did not ask for it.
- **A new `watch` task kind and group.** The `run` lookup already returns exactly what is needed, and `next()` only schedules the three existing groups.
- **`omarchy-notification-send`** (it has a click action and glyphs). Not chosen. Decision 3 is `notify-send`.
- **Show the notification on every status change.** The request is for "finished" only.
- **Poll a watch at 5 or 10 seconds.** That makes closed-panel traffic up to six times higher for no gain.

## Risks

- **A request that costs more than one (owner to confirm).** A log fetch is at least four API calls (three metadata calls plus the log download) inside one `gh` process. The intent requires one second between requests, and the scheduler cannot space calls inside `gh`. The design charges four slots per log start and waits four gaps afterwards (Scheduler section), so the rate over time is honest, but the four calls themselves go out back to back. Meeting the intent exactly would need one `gh api` call per request, each scheduled alone: the metadata calls are not needed for a `--job` log, but `gh api` needs `--allow-escape-sequences` and a path for the run-level form that has none. This spec does not take that route without the owner's say. A rate error stops everything through the existing cooldown.
- **Closed-panel polling is now a feature.** It is opt-in and capped at 5 runs, and 10 requests a minute at most. While closed, the only visible sign is the notification. There is no bar indicator (that is #46's separate issue). A user who forgets a watch has the shell polling for it until the run finishes. A run in a repository where the token loses access ends with the "Watch stopped" notice, not silently.
- **Auth failure while closed.** Polling stops until the panel is opened. A "Watching paused" notice is sent once. If the user ignores it, no notification will come. Documented in the README.
- **Shell restart loses all watches** (README line 168). A watched run then finishes unannounced. Stated in the README and in the status line when a watch is set.
- **Notification markup.** If this shell's popup reads markup, an unescaped workflow name could inject links or formatting. Stripping `<`, `>` and `&` covers it. Unverified on the real shell, so it is in the live check.
- **Terminal placement.** Hyprland may tile the `org.omarchy.github-actions-log` window instead of floating it. I did not verify the window rules. This is cosmetic. If it is wrong, the app id changes to one the rules already float, such as `TUI.float`.
- **`less` and `omarchy-launch-tui` missing.** `less` is in the Nixarchy base system here, but the flake lists it anyway (decision 9). `omarchy-launch-tui` comes from Omarchy, as `omarchy-shell` does. If it is missing, `execDetached` fails silently, so `viewLog()` shows "Terminal launcher not found" when the process cannot start. It should not leave the temp file behind: the one-day cleanup removes it.
- **Large or hostile logs.** A 1 MiB tail and 2,000-character lines bound memory and the terminal. A log made of one enormous line is cut, and the header says so. A log with ANSI in every line is cleaned in one pass of three regexes, which is fast enough for 1 MiB. A log full of look-alike text can still mislead the reader, as in the browser.
- **Expired or unreadable logs.** GitHub deletes logs after the repository's retention period. That, and a token without Actions read, give the same `permission` error and the same fixed message: "Log unavailable or expired". They cannot be told apart from here.
- **Merge conflicts.** `Polling.js` (`seed`, `complete`, `close`) and `ActionsPanel.qml` are touched by #41, #42 and #44. Whoever lands later rebases, reruns all tests and re-checks the budget tests.
- **The run is "failed" per the panel's own data.** If the run's conclusion is stale, `v` may refuse or fetch the wrong mode. Polling refreshes it, and a manual `r` fixes it.
- **Two PRs.** PR A adds `Polling.js` changes that PR B extends. The `log` task must not assume `watches` exist.

## Verification

Run these, in this order, from the repository root. The `qml-smoke.py` step needs an Omarchy host with a graphical session; `nix flake check` covers the Python and Node tests only.

```
python3 -m unittest tests/test_actions.py tests/test_menu.py
node tests/model.cjs
node tests/polling.cjs
python3 tests/qml-smoke.py
nix flake check
```

### New and changed tests

**`tests/test_actions.py`** (PR A):

- `log` rejects a bad repository, a missing, zero or non-numeric run, a non-numeric or zero job, `full` without a job, and a mode other than `failed` or `full`. The run-level form (no job, `failed`) is accepted.
- With a fake `gh` on PATH, as `test_cancellation_reaps_gh` does (line 20):
  - The command is exactly `gh run view --job <id> --log-failed -R github.com/<repo>`, an array. Same for `--log`, and the run-level form.
  - ANSI CSI and OSC sequences are removed, and a bare `ESC` is removed.
  - Bidi overrides and the BOM are removed.
  - `\r` is removed.
  - ZWJ survives.
  - A line over 2,000 characters is cut, and a log under 1 MiB with such a line gets the `lines cut` header and `lineCut` true, not `complete`.
  - An output of 3 MiB leaves 1 MiB, the tail, and the header says `cut short`. The fake keeps writing after the cap, so a test also proves the helper keeps draining.
  - Empty output makes no file, with the "No failed steps" reply.
- Error mapping from stderr: `auth login` → `auth`, `HTTP 404` → `permission`, `HTTP 429` → `rate`, a missing `gh` → `setup`, anything else → `network`. Stderr containing both `HTTP 403` and `rate limit` (or `secondary rate`) gives `rate`. The reply never contains raw stderr.
- The file is in the runtime directory, mode `0600`, and the directory is `0700`.
- `view` refuses a path outside that directory, a symlink, and a directory. It deletes the file after `less` exits. With a fake `less`, it passes `--` and the path as separate arguments.
- Files older than one day are removed by `log`.
- Cancelling a `log` request kills `gh` and reaps it, as `test_cancellation_reaps_gh` does for `page` (line 31). A silent `gh` that never exits is killed at the 90-second timeout (the test shortens the timeout). A fake `gh` that writes more stderr than a pipe buffer holds does not hang the helper while stdout is drained: stderr is read concurrently, as `communicate()` does today (line 48).

**`tests/model.cjs`**:

- Job and step rows carry `job`. `syncRows` behaviour does not change.
- `logTarget` returns the right `mode` for each row in the table: failed job, passing job, running job, failed run, passing run, step of a failed job, repository row.
- A cancelled job gets `full`, not `failed`.
- `notice` builds fixed result words, strips `<`, `>` and `&`, and cuts a long name. Each conclusion maps as in the table, and an unknown one is "finished".
- A watched run row shows `watching` in `info`. A row without a watch is unchanged.

**`tests/polling.cjs`**:

- A `log` task starts once, is charged four slots, and the next start waits four gaps. A workload test counts slots, not helper starts, and the 60-a-minute window holds with logs in the mix.
- The `log` task keeps the plain run id in `t.run` and the request carries `job` and `mode` separately. A run-level request has no `job`.
- A `log` error does not retry, does not set `r.blocked` on `permission`, and a `rate` error sets the cooldown.
- A `log` reply is accepted by the `okData` check.
- `v` while a `log` task is queued adds no second one.
- Watch (PR B):
  - A watched run on a closed state still starts a `run` request, and nothing else.
  - A closed state with no watches starts nothing, as today.
  - Six watches: the sixth is refused.
  - Two watches, one of them the inspected and expanded run: when it completes while closed, no `jobs` request starts and the other watch keeps polling. Unwatching a run removes its queued task.
  - A `completed` reply creates one `done` notice and removes the watch. A second reply creates none.
  - A `permission` reply creates a `lost` notice. A closed `auth` reply creates one `paused` notice and keeps the watches.
  - A re-run (same id, higher attempt, unfinished) keeps the watch.
  - Five watches over five simulated minutes with the panel closed start about 50 `run` requests, not more than `2 × watched` a minute. This asserts the watch rate itself, not only the global ceiling.
  - Reopening restores `s.auth = false` and the watch tasks continue.
  - The existing scheduler workload checks (budget, spacing, fairness) still pass, and a new workload adds 5 watches and checks the 60-a-minute ceiling holds.
  - Watch tasks use the quota multiplier from #41 once it exists.

**`tests/qml-smoke.py`** (local, on an Omarchy host; not run by `nix flake check`):

- The fake `actions.py` (lines 22-34) answers `log` with a path to a small file. The test puts a temp directory first on PATH holding stub `omarchy-launch-tui` and `notify-send` scripts that write their argv to a file. The panel is never allowed to launch a real terminal or notification.
- It checks that `viewLog()` makes one `log` request, that the stub got `["--app-id=org.omarchy.github-actions-log", "python3", <helper>, "view", <path>]`, and that nothing else was launched.
- With a filter typed, `v` on a running job still shows its message in the status line.
- It marks a run with `w`, calls `close()`, and checks that polling continues for the watch. This replaces the assumption in the existing stage-2 check (line 143) that a closed panel starts no requests. That check keeps its meaning with no watches: it still runs first.
- It lets the fake report the run `completed`, and checks that the stub `notify-send` got one call with `--app-name GitHub Actions --` and the expected title and body, and that polling stops afterwards.
- The existing invalid-directory check in `flake.nix` (lines 80-83) stays. #47 owns its removal.

### Flake and packaging

- `flake.nix` `passthru.runtimeDeps` (lines 34-38) gains `pkgs.less` and `pkgs.libnotify` (the `notify-send` package). `omarchy-launch-tui` comes from Omarchy and is not packaged here, the same as `omarchy-shell`.
- `flake.nix` `checks` run `python3 -m unittest discover` and the Node tests (lines 75-77), so the Python and Node tests above run under `nix flake check` with no change. The QML smoke test does not: the flake only runs it against a missing directory (lines 80-83). The real run needs `OMARCHY_PATH`, host theme files and a graphical session (`tests/qml-smoke.py` line 16, README line 205), so it is a local check on an Omarchy host and is listed as such. The package file list (lines 15-25) does not change, because no new files are added.
- README: the requirements (lines 22-23), the install block (line 62) and the `passthru.runtimeDeps` sentence (line 67) gain `less`, `libnotify` and a note on `omarchy-launch-tui`. Line 148's "Open GitHub for full logs" is changed to say `v` opens the log. Lines 3, 168 and 170 are updated for the closed-panel watch. The key table gains `v` and `w`.
- The Nixarchy consumer's `modules/home.nix` needs the same two packages. That is a separate issue and PR, as in #32.

### Live checks (on razer, then on a second Omarchy host)

- Run `python3 actions.py log '{"requestId":1,"repo":"olafkfreund/nixarchy-ghtui","run":"36027551384","job":"107727818137","mode":"failed"}'`. It should return a file path under `$XDG_RUNTIME_DIR/nixarchy-ghtui/`, and the file's first lines should be the header, then the failed step only. Then run `python3 actions.py view <path>` in a terminal and check the file is gone after `q`.
- Open the panel, press `v` on that failed run, then on the failed job, then on a step. A terminal opens each time. Check how Hyprland places it.
- Press `v` on a passing job. The full log opens.
- Press `v` on a running job and on a passing run. The status line says why nothing happened.
- Start a short workflow, press `w` on it, close the panel, and wait. A notification appears with the repository, workflow and result. Check how this shell draws it, and that a workflow named `<b>x</b> & y` shows safely.
- Watch a run, then restart the shell. Confirm the notification does not arrive, as documented.
- Watch a run, then remove `gh` auth. Confirm "Watching paused" is sent once.
- Count requests from `status()` (line 60) over five idle minutes with five watches and the panel closed. It should be about 50, not more than the 10 a minute from the cap.
- Count requests for one `v` press, to replace the estimate "at least four" and the four-slot charge with a measured figure.

### Not checked here

- The shell's notification markup behaviour and how it looks.
- The exact words `gh` prints for a running job's log.
- Hyprland rules for the terminal app id.
- That `gh run view` needs the same four calls for every log size.
- The step-anchor link question belongs to #42 and is not touched here.
