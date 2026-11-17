---
status: approved
issue: 46
spec: spec/2026-11-16-46-beyond-the-popup.md
coders:
  2: codex      # helper cleaning: null/odd `actor` shapes and control/format characters are small tricky validation logic
  3: codex      # detail() fallbacks (type guards, hex check, unknown, triggering-differs) and the pane-height rule are small tricky pure logic
  4: codex      # account state edge cases in Polling.js (pending, failed, permission, switch, cache owner) are scheduler-state logic
  5: coder      # QML pane, title, Esc order and layout wiring: the rest of the work, one file
  6: coder      # smoke-test fake and checks: the rest of the work, one file
  7: coder      # keybindings.sh and README text
reviewers:
  - codex       # independent read-only review of the diff against this plan: untrusted-text paths, Esc order, layout overlap
---

# Plan: Run detail pane and active account display (#46)

## Approved decisions (copied from the approved spec)

You do not need the intent or the spec to implement this. Do not widen it.

**Scope.** Two things ship, nothing else from umbrella #46:

1. A **run detail pane**: press `i` on a run, job or step row and a read-only
   pane shows what the parent run already carries.
2. The **active `gh` account**: the panel title shows `login@github.com`.

Out of scope, do not build: bar indicator, PR checks, pins, GitHub Enterprise,
annotations, a log tail (that is #44), account switching from the panel,
"open log" buttons, a fetch on `i`, the `head_commit` message. No new file,
dependency, setting, storage, GitHub request kind or flake `runtimeFiles`
entry. `Polling.js` gains no new task kind. The README promise "No polling
occurs while closed" stays.

**Pane lines**, in this order (`label` / value):

| Label | Value |
| --- | --- |
| Workflow | `name` and `path`, e.g. `CI · .github/workflows/check.yml` |
| Result | the same word the row shows (see step 3 trap on #42) |
| Branch | `head_branch` |
| Commit | first 7 characters of `head_sha`, only if `head_sha` matches `/^[0-9a-f]{40}$/`, else `unknown` |
| Event | `event` |
| Actor | `actor_login`, plus ` (triggered by <triggering_login>)` only when `triggering_login` is non-empty and differs |
| Attempt | `run_attempt` (integer >= 1), e.g. `2` |
| Started | `run_started_at` as an age, e.g. `3m ago` |
| Duration | `Model.duration(run, now)` |

Any missing or odd field shows the word `unknown`. `detail()` never throws.
SHA and attempt stay out of the row (#42 decision 2); this pane is where they
live.

**Which row opens it.** Rows of kind `run`, `job` or `step` show their parent
run, found with `Polling.runFor(polling, row.repo, row.run)` (reads only the
in-memory list). Every other row (`repo`, `message`, `more`, or no row) shows
one line, value `Select a run`. `o` still opens the selected row's URL.

**Keys.** `i` toggles the pane. `Esc` closes the pane first, then follows the
existing order (clear filter, then close the popup). Two Esc paths change: the
navigation handler and the search-field handler. In the search field, Esc with
the pane open closes the pane, keeps the filter text, keeps the popup open and
leaves focus in the search field. While searching, `i` is typed into the field
(the field takes key events first; nothing to do). The pane state is
`property bool detail` in QML, not stored, and is reset to false in `close()`.

**Layout.** The pane sits between the list and the footer in the existing
`Column`. The list height must subtract the pane height or the rows overlap.
The pane is `visible: root.detail`, so closed it costs nothing. It uses the
same `Style` sizes and `Color.menu` colours as the footer and rows,
`textFormat: Text.PlainText`, and elides long values. Its content is a
`Flickable` (scrolls vertically) so all nine lines are reachable. **Share
fixed by this plan:** the pane is capped at 40% of the column height
(`keys.height`); the list keeps a minimum of three rows
(`3 * rowMin`, `rowMin = Math.max(Style.space(40), Style.font.body + Style.space(12))`,
the no-subtitle row height); the pane shrinks first when space is short; the
pane is never shorter than one line. Read-only: no buttons.

**Where the logic lives.** Two pure functions in `ActionsModel.js`, no Qt:
`detail(run, now)` returns an array of `{label, value}`, and
`paneHeight(total, avail, content, minList, line)` returns the pane height
(rule above). `detail()` reads only the cleaned flat fields `actor_login` and
`triggering_login`, never the nested `actor.login` (`plain_fields()` does not
clean nested objects). It does not touch `rows()`, `shownFields` or
`syncRows`; row delegates and the 1 Hz rebuild are unchanged.

**Untrusted text (#32).** The pane is a new place where GitHub text reaches
QML. `event`, `path` and the logins must go through `plain()` in the helper.
The helper copies the logins from the nested objects into flat fields
`actor_login` and `triggering_login` (after `plain()`; an empty string when
the object is missing, `null`, or not a dict) on **both** reply paths: the
single-run reply (kind `run`) and the run-list reply (activity and summary
kinds). Test each field with control and format characters.

**Account display.** Title becomes
`GitHub Actions  ·  12 repositories  ·  olafkfreund@github.com`. The host is
the literal `github.com` already pinned in `actions.py`; it is never read from
`gh`. The login comes only from #41's account check (kind `account`, endpoint
`user`, reply `data = {login}`), kept in `polling.account` with
`polling.accountChecked` (and the `accountVerified` flag step 4 adds). #46 adds
**no** second lookup and no request.
Rules: before the first verified reply on this open (`accountVerified` false),
or after a failed lookup, the title is unchanged (no `…@github.com`). When
#41 clears data on a login change, the title changes in the same `adopt()`
call. A switch while the popup is open is not detected (accepted, #41
decision 3), so the title can show the old account until the next open; the
README says so in one line.

**Repo traps that apply to every step.**

- Argument arrays only for any process; no shell strings. This change adds no
  process.
- GitHub text reaches QML only through `plain()` (#32). Delegates and the pane
  use `textFormat: Text.PlainText`.
- `github.com` stays pinned; never show or build a host from input (#32).
- Fixed UI strings only (#24): raw stderr, tracebacks and `gh` output never
  reach the panel. The new strings are `Select a run`, `unknown`,
  `(triggered by …)`, `Run details`.
- Qt 0.3.1 `Process` quirks (#24): this change adds no `Process`. Do not touch
  `requestProc`, `failedToStart`, `helperStarted` or `onRunningChanged`.
- `shownFields` in `ActionsModel.js` (line 93) must list every row field a
  delegate reads. This change adds **no** row field and no delegate change, so
  it stays `["title", "subtitle", "status", "info"]` plus whatever #42 added.
  If you find yourself adding a field to a row, stop: the pane reads the run
  object, not the row.
- #36 no-rerun rule: a failing smoke run is a failure to investigate, never a
  reason to rerun or add a retry. Do not add retry loops, longer sleeps or
  wider timeouts to `tests/qml-smoke.py`. Do every new check in the existing
  synchronous seed block (the 1000 ms timer) or the stage-1 success branch, so
  no new wait is added. The inner timeout stays 18 s and the outer 25 s.
- Ponytail: the smallest correct change; no new abstraction beyond the two
  functions named above.
- nixarchy owns the menu: `menu.py`, `menu.example.json` and the Omarchy menu
  entries are not touched. `keybindings.sh` is the key reference and is edited
  in step 7.

## Base and order

Merge order is fixed by the owner: **#41, #42, #43(a), #43(b)**; #44, #45 and
#47 follow #41; **#46 lands after #41 to #44**. All branches start from
`main`. This branch is `feat/46-beyond-the-popup`. **Before any implementation
edit, rebase it onto `main` once #41, #42, #43 and #44 have merged** (and
re-run the full suites on the rebased tree). If a predecessor has not merged,
stop and report; do not code against its spec.

The line numbers below are from `main` at `6d42838` (before #41 to #44). They
will have moved. Find each place by the quoted anchor text, then cite the real
line in the commit and in the PR.

## Steps

Each step's test and its fix go in one commit. Run each new test before the fix
and record that it fails (evidence goes into the PR). Name the step in the
commit body ("plan step N").

1. **Session, no edits: confirm the merged contracts.** Rebase (see Base). Read
   the merged code and write the answers into the PR notes, because steps 2 to
   7 depend on them:
   - (a) #41 account: `actions.py` `page_endpoint()` accepts kind `account` and
     maps it to `user`; `read_page()` returns `data = {login}`; the pattern it
     enforces; `Polling.js` has `s.account` and `s.accountChecked`, `open()`
     resets `accountChecked`, a changed login clears `repos`, `details`,
     `expanded`, `selected`, `inspected`, `catalogueComplete`, and what the
     `permission` branch does for kind `account`; where `s.accountVerified`
     (step 4) is added.
   - (b) #42: whether `clean_run()` exists in `actions.py` and whether it
     replaced `actor` (object) by a login string; the name of the function
     that produces the row's result word (`statusText`); whether `Model.age()`
     exists; the current footer text; the current Esc handlers; the modifier
     guard at the top of `Keys.onPressed`; the accessibility properties
     pattern.
   - (c) #44/#45: any new key or confirmation state that Esc must also
     cancel, and any key that already uses `i`.
   - (d) #47: whether `tests/stubs/` and a real-key harness exist, and the
     layout-check function it added to `ActionsPanel.qml`.
   Check: `git log --oneline main..HEAD` shows only the #46 docs commits;
   `grep -n "Qt.Key_I\b" ActionsPanel.qml` finds nothing.
   Traps: none (read-only). If any answer contradicts this plan, stop and put it
   under "Deviations needing approval" instead of improvising.

2. **`actions.py` and `tests/test_actions.py`: clean and flatten the run text.**
   `RUN_TEXT` (line 42): add `"event"` and `"path"` if #42 has not already
   added `event`. Add or extend `clean_run(row)` (create it only if #42 did
   not) so that, **before** any `actor` flattening, it sets
   `row["actor_login"]` and `row["triggering_login"]` to
   `plain(obj["login"])` when the source is a dict whose `login` is a string,
   else `""` (covers `null`, missing, a string, a list). Then it calls
   `plain_fields(row, RUN_TEXT)`. Call it in both places that call
   `plain_fields(..., RUN_TEXT)` today: the `run` branch (line 182) and the run
   list loop (line 192). Do not change the jobs path (`("name",)`). Do not
   delete or rewrite nested `actor` unless #42 already does.
   Tests first, in `tests/test_actions.py` (pattern of
   `test_page_text_is_plain`, line 179, reusing its `page()` helper):
   - new `test_run_detail_text_is_plain`: a run with `event="pu\x07sh"`,
     `path=".github/‮workflows/x.yml\n"`,
     `actor={"login":"al\x07ice"}`,
     `triggering_actor={"login":"bo‮b"}` comes back on the list reply
     (activity, summary queued, summary recent) and on the `run` reply with
     `event="push"`, `path=".github/workflows/x.yml"` (line break becomes a
     space, bidi controls removed; assert the exact `plain()` output),
     `actor_login="alice"`, `triggering_login="bob"`;
   - missing `actor`, `actor: None`, `actor: "x"` and `actor: {}` give
     `actor_login == ""` and no error (`errorType == ""`), on both reply
     paths; same for `triggering_actor`;
   - **update** the existing assertions in `test_page_text_is_plain` (lines
     196-197) that compare the whole dict: they now also carry
     `actor_login=""` and `triggering_login=""`, so extend their expected
     dict (`dict(run, **plain_run, actor_login="", triggering_login="")`);
   - if #41's account pattern is looser than
     `^[A-Za-z0-9-]{1,39}(\[bot\])?$`, tighten it to that pattern in
     `read_page()` and add `test_account_login_pattern`: `"octo-cat"` and
     `"dependabot[bot]"` pass through as `data == {"login": ...}`; `""`,
     `"a b"`, `"x/y"`, a 40-character name, `"a\nb"` give an error reply whose
     `errorType` is asserted explicitly. Keep #41's error type for a bad login
     (see Deviations).
   → verify by `python3 -m unittest tests/test_actions.py` (all OK) and
   `git diff --stat` touching only `actions.py` and `tests/test_actions.py`.
   Traps: `plain()` for every GitHub string (#32); do not echo raw bodies; do
   not change `request()` (argument array, `--hostname github.com` stays); a
   failure here must not change `errorType` of any existing reply.

3. **`ActionsModel.js` and `tests/model.cjs`: `detail()` and `paneHeight()`.**
   Add after `duration()` (line 33):
   - `detail(run, now)`: if `run` is not an object, return
     `[{label: "", value: "Select a run"}]`. Otherwise the nine
     `{label, value}` lines in the table order. Helpers inside: a `text(v)`
     that returns `v` when it is a non-empty string, else `"unknown"`. Every
     field is type-guarded (`typeof === "string"`) before the regex, `slice`,
     `state()` or `duration()` touch it, because the run object comes from
     JSON and a field can be an array or object; the whole body of each line
     is also wrapped so a line that throws becomes `unknown` (`detail()` never
     throws, also for `{run_started_at:{toString:null}}`). Result uses
     `state(run)` only when it returns a string, else `unknown`. Started and
     Duration are computed only when `run_started_at` is a string.
     Workflow = the non-empty of `name`/`path` joined with ` · `, else
     `unknown`. Result = the same function the row uses for its word (after
     #42 that is its `statusText` producer; before, `state(run)`). Commit =
     `/^[0-9a-f]{40}$/.test(run.head_sha)` ? first 7 : `unknown`. Actor =
     `text(run.actor_login)`, and when `run.triggering_login` is a non-empty
     string different from `run.actor_login`, append
     ` (triggered by ` + login + `)`. Attempt = `run.run_attempt` when it is an
     integer >= 1, else `unknown`. Started = the age of `run_started_at`
     (reuse #42's `Model.age(run, now)`; if it is absent, do not add a second
     age function: use `run.run_started_at` only, same wording
     `now` / `5m ago` / `3h ago` / `2d ago`, `unknown` when unparsable).
     Duration = `duration(run, now)` or `unknown` when empty. No call to
     `JSON.stringify`, no `eval`, no string built from nested objects.
   - `paneHeight(total, avail, content, minList, line)`:
     `var cap = Math.min(0.4 * total, avail - minList); return Math.max(line, Math.min(content, cap));`
   Tests first, in `tests/model.cjs` (it loads `ActionsModel.js` into the `vm`
   context as `model`; add before the last `console.log`):
   - full run (`head_sha` of 40 hex, `event:'push'`, `actor_login:'a'`,
     `run_attempt:1`, `run_started_at` 3 minutes before a fixed `now`,
     `name:'CI'`, `path:'.github/workflows/check.yml'`,
     `head_branch:'main'`, `status:'completed'`, `conclusion:'success'`):
     labels in the exact order above, commit has length 7, Started
     `3m ago`;
   - run with no `head_sha`, no `actor_login`, no `event`: those three values
     are `unknown`, no throw;
   - bad `head_sha`: 40 non-hex characters, 7 characters, a 40-character
     string containing `\u001b[31m` and uppercase hex: each gives `unknown`;
   - `triggering_login` equal to `actor_login` shows no suffix; different shows
     `a (triggered by b)`; empty shows no suffix;
   - `run_attempt:2` shows `2`; `0`, `"2"`, missing show `unknown`;
   - malformed JSON shapes give `unknown` and no throw: `head_sha` as an array
     holding a valid 40-hex string, `run_started_at:{toString:null}`,
     `conclusion:{}`, `name:[]`;
   - `detail(null, now)`, `detail(undefined, now)` and `detail("x", now)` give
     exactly the one `Select a run` line; and from `rows()` output, a `repo`
     row and a `message` row map to that line (build the repo and message
     rows with the existing test data; apply the same `kind` rule the QML uses:
     only `run`, `job`, `step` pass a run);
   - `paneHeight` at the viewports this plan fixes (rowMin 40, line 20, nine
     lines so content 180): normal `(total 400, avail 280, content 180, minList 120)`
     returns 160 (cap `min(160, 160)`), so the pane scrolls; small
     `(total 240, avail 150, content 180, minList 120)` returns 30; tiny
     `(total 100, avail 40, content 180, minList 120)` returns 20 (the
     one-line floor); large `(total 800, avail 700, content 180, minList 120)`
     returns 180 (content fits).
   → verify by `node tests/model.cjs` (exit 0, prints its last line) and
   `grep -n "shownFields" ActionsModel.js` unchanged.
   Traps: `shownFields` untouched (no row field added); pure function, no Qt
   or Date.now() (time injected as `now`); do not read `run.actor` or
   `run.triggering_actor` (nested, uncleaned); `Model.state()` and
   `rows()` unchanged.

4. **`Polling.js` and `tests/polling.cjs`: only what the title needs from
   #41.** Expected change: one field. #41 keeps `s.account` (the owner of the
   cached data) and `s.accountChecked` (the gate). `accountChecked` is also true
   after a `permission` error, so it cannot say "this login was verified on this
   open". Add `s.accountVerified`: `create()` sets `false`, `open()` sets
   `false`, the account success path sets `true` (in the same call that sets
   `s.account`), the `permission` path leaves it `false`. Do **not** clear
   `s.account` anywhere: it stays the cache owner, so A's cache is still
   cleared when B's login arrives after a permission failure (see Deviations).
   Nothing else in `Polling.js` changes.
   Add to `tests/polling.cjs`, reusing its `response()` helper and the pattern
   used by #41's tests, one block "account title contract". Build a **fresh
   state** for each case (no case depends on the one before):
   - account A loaded (`s.account="a"`, `accountChecked=true`,
     `accountVerified=true`, repos present), `close`, `open`:
     `accountChecked===false`, `accountVerified===false`, `s.account==="a"`
     still (cached data kept until the reply, per #41);
   - fresh state with `s.account="a"`: `complete()` of the account reply
     `{login:"b"}`: in that one call `s.account==="b"`, `accountChecked===true`,
     `accountVerified===true` and `repos`, `details`, `expanded` are cleared;
   - fresh state with `s.account="a"`: account reply `{login:"a"}`: nothing
     cleared, `accountVerified===true`;
   - fresh state with `s.account="a"`: `permission` error for the account task:
     `accountChecked===true`, `accountVerified===false`, `s.account==="a"`,
     data not cleared; then `close`, `open`, account reply `{login:"b"}`:
     data **is** cleared (A's cache never survives under B);
   - fresh state: `network` error reply: `accountChecked===false`,
     `accountVerified===false`, `account` unchanged.
   → verify by `node tests/polling.cjs` (exit 0, its existing benchmark numbers
   unchanged: `baseline()` still `{requests:902, coldScanMs:411000}`).
   Traps: no new task kind; no new request; do not touch the scheduler's
   budget or cooldown; account display must not add polling while the popup is
   closed; if #41's shape differs from the contract in step 1, adapt the test
   to the merged shape and note it in the PR.

5. **`ActionsPanel.qml`: pane, title, keys, layout.** Anchors are the quoted
   text; lines are `main` at `6d42838`.
   - Properties near line 33 (`readonly property var current`):
     `property bool detail: false`; `property string account: ""`;
     `readonly property real rowMin: Math.max(Style.space(40), Style.font.body + Style.space(12))`;
     `readonly property var detailRun: current && ["run", "job", "step"].indexOf(current.kind) >= 0 ? Polling.runFor(polling, current.repo, current.run) : null`;
     `readonly property var detailRows: detail ? Model.detail(detailRun, now) : []`;
     `readonly property string titleText: "GitHub Actions  ·  " + repos.length + (repos.length === 1 ? " repository" : " repositories") + (account ? "  ·  " + account + "@github.com" : "")`;
     `readonly property string detailAccessibleName: "Run details: " + detailRows.map(function(r) { return (r.label ? r.label + " " : "") + r.value }).join(", ")`;
     `property alias listView: list`, `property alias detailPane: pane`,
     `property alias footerItem: footer` (read-only geometry for the smoke
     test; skip any alias #47 already added for the same purpose).
   - Functions after `selectionChanged()` (line 121):
     `function toggleDetail() { detail = !detail }` and
     `function escape(searching) { if (detail) detail = false; else if (searching) { filterText = ""; keys.forceActiveFocus() } else if (filterText) filterText = ""; else close() }`.
     In the search-field path (`searching` true) with the pane open, the
     filter stays and focus stays in the field; only the pane closes. If #44 or
     #45 added a state Esc must cancel first (step 1c), put it before
     `detail` in `escape()`.
   - `open()` (line 43): after `Polling.open(...)` set `account = ""`.
     `close()` (line 54): set `detail = false`.
   - `adopt()` (line 122): first line after `repos = ...`:
     `account = polling.accountVerified && polling.account ? polling.account : ""`
     in the same function, before the `polling = Object.assign({}, polling)`
     line, so data and title change in the same call.
   - Navigation handler (line 236): replace the Escape branch body with
     `root.escape(false)` and add
     `else if (event.key === Qt.Key_I) root.toggleDetail()` next to
     `Qt.Key_O` (line 251). The #42 modifier guard stays first.
   - Search field Escape (line 281): replace its two lines with
     `root.escape(true)`; keep `event.accepted = true` flow as is.
   - Title (line 260): `text: root.titleText`.
   - Pane: new `Flickable { id: pane }` between the `ListView` (ends line 370)
     and `Text { id: footer }` (line 371):
     `visible: root.detail`, `width: parent.width`,
     `readonly property real avail: parent.height - list.y - footer.height - Style.spacing.md * (visible ? 2 : 1)`,
     `readonly property real line: Math.ceil(Style.font.caption * 1.4)`,
     `height: visible ? Model.paneHeight(parent.height, avail, paneBody.implicitHeight, 3 * root.rowMin, line) : 0`,
     `contentHeight: paneBody.implicitHeight`, `clip: true`,
     `boundsBehavior: Flickable.StopAtBounds`,
     `Accessible.role: Accessible.Pane`, `Accessible.name: root.detailAccessibleName`.
     Body: `Column { id: paneBody; width: pane.width }` with a
     `Repeater { model: root.detailRows }` of a `Row` holding two `Text`
     items: the label (fixed `width: Style.space(90)`, `opacity: 0.65`,
     `Style.font.caption`, `Color.menu.text`) and the value (width
     `paneBody.width - Style.space(90) - spacing`, `elide: Text.ElideRight`,
     `Style.font.caption`, `Color.menu.text`), both
     `textFormat: Text.PlainText`. Use `modelData.label` / `modelData.value`.
   - List height (line 305): `height: Math.max(0, parent.height - y - footer.height - Style.spacing.md - (pane.visible ? pane.height + Style.spacing.md : 0))`.
   - Footer (line 374): add `i details` to the key hint list (after `o GitHub`,
     before `Esc close`) in whatever form #42/#44 left it; keep
     `root.cooldownText ||` only if #42 did not move it.
   → verify by `python3 tests/qml-smoke.py` after step 6 (this step is
   verified together with it) and a first load check
   `quickshell -p <tmp root with the panel> --no-color` showing no
   `ERROR:`/`TypeError`/`ReferenceError`.
   Traps: Quickshell Qt 0.3.1: no new `Process`; do not add handlers to
   `requestProc`. Fixed strings only; every new `Text` is
   `Text.PlainText`. `Column` skips invisible items, which is why the spacing
   term in `avail` and the list height use `pane.visible`. `Style` sizes only,
   no hard-coded pixels (the `0.4` share and the `3` rows are the only
   constants). No `Color` shadowing: keep the existing `qs.Commons` import
   (#40). Do not add a delegate field or change `shownFields`.

6. **`tests/qml-smoke.py`: fake data and checks.** All edits in the heredoc of
   the fake `actions.py` and in `shell.qml`; no new waits (#36).
   - Fake run (line 30): add `'head_sha':'0123456789abcdef0123456789abcdef01234567'`,
     `'event':'push'`, `'actor_login':'octo'`, `'triggering_login':'octo'`,
     `'path':'.github/workflows/ci.yml'`. Add before the final `else`:
     `elif kind=='account': data={'login':'fake-user'}` (skip if #41's smoke
     change already serves `account`).
   - In the 1000 ms seed block (the panel is still closed there: line 93 checks
     `!panel.opened`, so no check in this block may read `panel.opened`), after
     `check(panel.current.kind==="run","keyboard selection")` (line 103) and
     before `panel.expand(false)`, only property checks that do not need an
     open popup or a layout pass:
     `check(panel.titleText.indexOf("@github.com")<0,"no account before the first reply")`;
     `check(!panel.detail,"pane starts closed")`;
     `panel.toggleDetail()`;
     `check(panel.detailRows.length===9 && panel.detailRows[3].value==="0123456","pane shows the 7-character commit")`;
     `check(panel.detailRows[2].value==="main" || panel.detailRows[2].value==="unknown","branch line")`
     (the seeded run has no `head_branch` before line 104; the seeded object
     at line 99 needs `head_sha`, `event`, `actor_login` added to prove the
     lines, so add them there too);
     `check(panel.detailAccessibleName.indexOf("Run details")===0,"pane accessible name")`;
     `panel.toggleDetail()` again, then `panel.move(-1)`, `panel.toggleDetail()`,
     `check(panel.detailRows.length===1 && panel.detailRows[0].value==="Select a run","repo row")`,
     `panel.toggleDetail()`, `panel.move(1)`.
   - Search-field Esc, in the same block after `panel.filterText="repo"` (line
     117): `panel.toggleDetail(); panel.escape(true)`;
     `check(!panel.detail && panel.filterText==="repo","search Esc closes the pane, keeps the filter")`.
     (Later lines keep working because the filter is unchanged.)
   - Last line before `panel.open()` (line 123): `panel.toggleDetail()` so the pane
     is open when the existing 1000 ms stage timer fires: layout has been
     positioned by then and no wait is added.
   - Stage-1 success branch (popup open, layout settled, same `check()`
     helper): geometry with
     `var lv=panel.listView, pn=panel.detailPane, ft=panel.footerItem`,
     `check(panel.opened && panel.detail && lv.height>0,"list non-empty with pane open")`,
     `check(lv.y+lv.height<=pn.y && pn.y+pn.height<=ft.y,"list, pane and footer do not overlap")`,
     `check(pn.height<=0.4*lv.parent.height+1,"pane within its share")`,
     and when the room the pane itself computes allows three rows
     (`pn.avail>=3*panel.rowMin+pn.line`),
     `check(lv.height>=3*panel.rowMin,"list keeps three rows")` (uses the same
     `avail` as the pane, so the title, search and spacing above the list are
     counted); read `pn.Accessible.role` and `pn.Accessible.name` the way #42's
     check does; if the attached read fails on this Qt, keep the string check
     and record that in the PR (same fallback #42 decision 11 uses). Then Esc
     order: `panel.escape(false)` and
     `check(!panel.detail && panel.opened,"Esc closes the pane first, popup stays")`;
     `panel.escape(false)` once more and `check(!panel.opened,"second Esc closes the popup")`
     as the last check of the branch, only if no later check needs the popup.
   - Account title adoption: right after the seed `panel.adopt()` calls,
     `panel.polling.account="alice"; panel.polling.accountVerified=false; panel.adopt()`
     then `check(panel.titleText.indexOf("alice")<0,"pending lookup shows no account")`;
     `panel.polling.account="bob"; panel.polling.accountVerified=true; panel.polling.repos=[]; panel.adopt()`
     then `check(panel.titleText.indexOf("bob@github.com")>=0 && panel.entries.length===0,"title follows the verified account and the cleared data in one adopt()")`
     (this proves the rendering from polling state; that a real reply clears and
     verifies in one `complete()` is proven by `tests/polling.cjs`, and the
     stage-1 check below proves the real reply path);
     then restore the seed (`panel.polling.account=""; panel.polling.accountVerified=false`
     and re-seed repos as lines 96-97 do) before the rest of the block.
   - Stage-1 success branch (line 131 area): add
     `check(panel.titleText.indexOf("fake-user@github.com")>=0,"title shows the account from the fake reply")`
     (requires #41's account check to have run in the real flow; this is the
     check that goes through the real reply path; the existing `requests>=6`
     threshold may need `+1` for the account request: adjust the number and the
     timeout message at line 72 together, and record why in the PR).
   - If #47's stubs and real-key harness are merged (step 1d): use its stub
     viewport as the "small fixed viewport", send real `i` and `Escape` keys
     through it instead of calling `toggleDetail()` / `escape()`, and add a
     small-viewport case that opens the pane and asserts the three-row list and
     non-overlap. If they are not merged, the small-viewport rule is covered
     by the `paneHeight` cases of step 3 (viewports 240/150 and 100/40) and
     the smoke test checks the real window; say so in the PR (see Deviation 2).
   → verify by `python3 tests/qml-smoke.py` (needs `OMARCHY_PATH` and a theme,
   so run it on the razer host; prints `QML_CHECKS_PASSED`, exit 0). One
   failure is a failure: investigate, do not rerun (#36).
   Traps: #36 no-rerun rule and no new waits; the test calls panel functions
   directly because QML cannot send synthetic key events to the `keys` item
   (see Deviations); the check list must still pass when run twice in a row
   by hand, but do not add reruns to the script or CI; do not edit
   `required` (line 12): no file is added.

7. **`keybindings.sh`, `README.md`: docs.**
   - `keybindings.sh`: after the `o →` line (line 22) add
     `i → Show or hide run details`. Change line 19 to
     `Esc → Close run details, then clear filter, then close` and line 18 to
     `Esc while searching → Close run details, otherwise clear search and resume navigation`.
   - `README.md`: keyboard table (line 143) `Esc` row becomes
     `Close run details, then clear filter, then close`; add a row after `o`
     (line 146): `| i | Show or hide run details (commit, event, actor, attempt, start, duration) |`;
     in the short intro (line 9) no change. Add one line near the
     Authentication section (after line 129) stating that the panel title
     shows the active `gh` login with `@github.com`, and that a
     `gh auth switch` while the popup is open is not noticed until the next
     open.
   → verify by `bash keybindings.sh --print | grep -F "i → Show or hide run details"`
   (one match) and `python3 -m unittest tests/test_menu.py` (OK).
   Traps: `flake.nix` `runtimeFiles` (lines 15-25) and `tests/qml-smoke.py`
   `required` are not edited, because no file is added; check by
   `git diff --name-status main..HEAD` showing no `A` lines outside `plan/`,
   `spec/` and `intent/`. Do not touch `menu.py` or `menu.example.json`
   (nixarchy owns the menu).

8. **Session, no coder: build, review, evidence, PR.** Run every command in
   Tests. Review the whole diff with a fresh `model: "opus"` agent given only
   this plan path and `git diff main...HEAD`, and send the same to the
   `codex` reviewer (read-only). Commit each step as in the rules above.
   Update `plan/` in the same commit as any deviation from it. Push, open the
   PR linking intent, spec and this plan, with the evidence table (test
   failing before, passing after, per step), the step-5 and step-6 results
   (including the Accessible read result and the viewport used), and which
   steps the coder and codex did. Then the owner's runtime check (below).
   Traps: builds, reviews and commits stay with the session; reviewer output
   is advice only and approves nothing; do not merge.

## Tests

Run from the repository root, on the rebased tree.

```sh
node tests/model.cjs                                        # exit 0, prints its last line; detail() and paneHeight() cases included
node tests/polling.cjs                                      # exit 0; baseline still {requests:902, coldScanMs:411000}
python3 -m unittest tests/test_actions.py tests/test_menu.py  # OK; new run-detail text and (if tightened) login pattern tests included
python3 -m unittest discover -s tests -v                    # OK (what the flake runs)
bash keybindings.sh --print | grep -F "i → Show or hide run details"   # one line
nix flake check -L                                          # all checks passed (runs the above plus keybindings --print)
python3 tests/qml-smoke.py                                  # QML_CHECKS_PASSED, exit 0; razer host only (needs OMARCHY_PATH and a theme); with #47 merged: nix develop -c python3 tests/qml-smoke.py
```

`nix flake check` does not run the QML smoke test (it only checks that an
invalid directory is refused), so `tests/qml-smoke.py` must be run by hand.
Never rerun a failing smoke run to get a pass (#36).

New tests by file:

- `tests/test_actions.py`: control and format characters in `event`, `path`,
  `actor.login`, `triggering_actor.login` are removed on the list and single
  run replies; missing, `null`, string and `{}` actors give empty flat fields
  and no error; (if needed) the account login pattern, with the error type
  asserted.
- `tests/model.cjs`: `detail()` order, 7-character commit, `unknown`
  fallbacks, bad `head_sha`, malformed JSON shapes without a throw, triggering
  shown only when different, attempt 2, `Select a run` for a null run and for
  repo and message rows; `paneHeight()` at the 400/280, 240/150, 100/40 and
  800/700 viewports.
- `tests/polling.cjs`: account contract with fresh states per case (pending
  keeps cached data and no verified account; switch clears in one
  `complete()`; same login clears nothing; `permission` leaves the title
  unverified and still clears A's cache when B arrives; `network` retries).
- `tests/qml-smoke.py`: `i` opens the pane with the commit; no overlap and a
  non-empty list (checked in the stage-1 branch, popup open); Esc closes the
  pane first and the popup stays; search Esc keeps the filter; repo row shows
  `Select a run`; title has no account before the reply and shows
  `fake-user@github.com` after; title and cleared data change in one
  `adopt()`; the pane's accessibility name (and attached properties if
  readable).

**Owner runtime check on the real desktop (not run by agents):** open the
popup, select a run, press `i`, compare each line with
`gh api repos/<repo>/actions/runs/<id>`; compare the title login with
`gh api user --jq .login`; press Esc once (pane closes, popup stays), again
(popup closes). Layout and `Accessible` properties are verified on the razer
host only; other hosts are untried.

## Rollback

- **Code:** revert the step commits in reverse order (7, 6, 5, 4, 3, 2), or do
  not merge the PR. There is no data, setting, storage or migration: the pane
  state is a QML property, the account display reads polling state that #41
  already keeps (plus the `accountVerified` flag, which is in memory only).
  Reverting step 5 alone removes the pane and the title suffix and leaves the
  helper's extra flat fields (`actor_login`, `triggering_login`, cleaned
  `event` and `path`) harmlessly in the replies.
- **Live copy on the razer host (run by the lead):** in
  `~/.config/omarchy/plugins/olafkfreund.github-actions` run
  `git status --short`; if it shows changes you did not make, stop and report
  (do not discard them); otherwise `git checkout main` (the previously
  deployed revision), then `omarchy-restart-shell`.

## Deviations needing approval

1. **`actor_login` versus #42's flattened `actor`.** The approved spec says the
   helper adds flat `actor_login` and `triggering_login`. #42's spec flattens
   `actor` itself to a login string in `clean_run()`. If #42 has merged that
   way, `actor_login` duplicates `actor`. This plan keeps the spec's names
   (step 2 sets both, reading the object before #42 flattens it) because the
   spec is approved. Alternative for the owner: read `actor` (string) in
   `detail()` and add only `triggering_login`. Needs a yes before step 2 if
   you prefer the smaller change.
2. **No synthetic key events, reduced verification.** The spec asks for a
   minimal key-event helper if none exists, real `i`/Esc presses and a named
   small viewport. QML cannot inject key events into the `keys` item from the
   smoke test (not verified against the merged #47 harness), so this plan routes
   the keys through two new functions (`toggleDetail()`, `escape(searching)`)
   that the test calls directly, the same way it calls `panel.move(1)` today.
   The mapping `i` to `toggleDetail()` and `Esc` to `escape()` is then checked
   by #47's real key events if #47 has merged (step 6), otherwise only by the
   owner's runtime check and a `grep -n "Qt.Key_I" ActionsPanel.qml` in review.
   Without #47 this delivers less than the spec asks for, so the owner must
   accept the reduced verification (or wait for #47) before step 6.
3. **"A's cached data is not shown under B" while the lookup is pending.** The
   spec's account-isolation test says that, but #41 (decision 3) keeps cached
   data visible on reopen until the first account reply, and cannot know it is
   B before then. This plan tests what is true: while pending or failed the
   title shows no account name, and when B's login arrives the title and the
   cleared data change in the same `adopt()` call. Needs the owner to accept
   the reworded test.
4. **One extra field in #41's code.** `s.accountVerified` (step 4) is in
   neither spec. `accountChecked` is also true after a `permission` error, so
   the title cannot use it to tell "verified on this open" from "can't tell".
   Clearing `s.account` on `permission` instead was rejected: it would drop the
   cache owner, and a later reply for B would then look like a first-ever check
   and leave A's cached data under B. If you prefer no change to #41's code,
   the title would have to show a possibly stale login after a `permission`
   error.
5. **Error type for a bad login.** The spec says an invalid login is a `setup`
   error; #41's approved spec turns the same `ValueError` into the generic
   `network` error (`setup` stops polling, `network` retries, so the choice
   matters). Step 2 keeps whatever #41 merged (only the pattern is tightened)
   and tests that type explicitly. Change to `setup` only if you want it.
6. **Extra doc lines.** Besides the spec's "one line" for `i`, step 7 also
   edits the existing Esc lines in `keybindings.sh` and the README table,
   because the Esc order changes and the references would be wrong otherwise.
7. **Pane share and floor.** The spec leaves the share to the plan: this plan
   fixes 40% of the column height, a three-row list minimum and a one-line
   floor for the pane. On a card too small for a one-line pane plus three
   rows, the list shrinks below three rows rather than hiding the pane.

## Owner answers (2026-11-16, "approve all plans as recommended")

These override any step text they contradict. Merge order: #41 -> #42 -> #43(a) -> #43(b); #44 after #42; #45 and #47 after #41; #46 after #44 and #47.

- Deviation 1: **the smaller change.** Step 2 does not add `actor_login`. `detail()` reads #42's flattened `actor` string; the helper adds only `triggering_login` (same cleaning rule: `plain(obj["login"])` when it is a dict with a string `login`, else `""`). Adjust step 2's and step 3's tests to match.
- Deviation 2: **#46 waits for #47.** Step 1 confirms #47 is merged; step 6 uses #47's real key events for `i` and Esc. `toggleDetail()` and `escape()` may still exist, but the test drives them by key presses.
- Deviations 3, 4, 6, 7: accepted as written.
- Deviation 5: keep #41's `network` type for an invalid login, and test it.

## Deviations during implementation (2026-11-17)

- **Step 5: `escape(searching)` is named `handleEscape(searching)`.** QML refuses `escape` as a method name ("Illegal method name": it clashes with the global JS `escape()`); the first smoke run failed to load the panel with that error.
- **Step 5: sizes follow the text-size keys (#48, merged after this plan).** `rowMin` is `Math.max(sp(40), fBody + sp(12))`, the same formula the row delegate uses now; the pane line height uses `root.fCaption` and the label width `root.sp(90)`, so the pane scales with Ctrl+=/Ctrl+- like the rest of the panel.
- **Step 5: the title keeps #44's "N watched" suffix** after the account part, and `layout()` (the #47 test hook) also reports the pane's and the footer's position relative to the list, so the key run can check that list, pane and footer do not overlap.
