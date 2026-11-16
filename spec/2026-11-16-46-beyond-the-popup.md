---
status: draft
issue: 46
intent: intent/2026-11-16-46-beyond-the-popup.md
---

# Spec: Run detail pane and active account display

## Design

### Scope

The owner approved a narrow first change for the umbrella issue #46. Two
things ship now:

1. A **run detail pane**: press `i` on a run (or a job or step under it) and a
   pane shows what the run already carries.
2. The **active `gh` account**: the panel title shows `login@github.com`.

Nothing else from the intent ships here. Bar indicator and PR checks become
separate issues later. Pins and GitHub Enterprise are out.

It adds no new files, dependencies, settings or storage. It adds no new GitHub
request apart from the one account lookup described below. `Polling.js` gains
no new task kind.

### Owner decisions on the intent's open questions

Binding, from the 2026-11-16 approval ("approve all as recommended"):

1. **Scope.** The umbrella is split. In scope now: run detail pane and active
   account display. Bar indicator and PR checks become separate issues. Pins
   and GitHub Enterprise are out.
2. **Bar indicator allowed to work while closed.** Out of scope now. The README
   promise "No polling occurs while closed" (line 170) stays.
3. **Bar indicator as one plugin.** Out of scope now.
4. **PR checks data.** Out of scope now.
5. **PR checks entry point.** Out of scope now.
6. **Run detail depth.** The pane shows only what the run already carries. No
   annotations and no log tail (logs belong to #44).
7. **Pins.** Out of scope now. No storage, no GitHub write.
8. **Account display depth.** Login and host only. No account switching from
   the panel.
9. **GitHub Enterprise.** Out of scope now. The #32 host pin stays as it is.
10. **Order.** This lands after #41, #42, #43 and #44.

Nothing here conflicts with the plugin's rules. All six "bends" in the intent's
table are avoided, except that the account lookup is one extra read.

### Run detail pane

**What it shows.** The run payload from `actions/runs` already has everything,
checked on 2026-11-16 against this repository with `gh api`:
`head_sha` (40 hex characters), `event` (`push`), `run_attempt` (1),
`run_number`, `actor.login`, `triggering_actor.login`, `created_at`,
`run_started_at`, `updated_at`, `path` (`.github/workflows/check.yml`),
`head_branch`, `display_title`, `html_url`. `Polling.js` stores run objects as
received (`mergeRuns`, `union`, lines 120-143), so no field is dropped between
the helper and QML.

The pane lists these lines, in this order:

| Line | Source |
| --- | --- |
| Workflow | `name` and `path` |
| Result | `Model.state(run)` (same word as the row) |
| Branch | `head_branch` |
| Commit | first 7 characters of `head_sha` |
| Event | `event` |
| Actor | `actor_login` (cleaned flat field), plus `triggering_login` when it differs |
| Attempt | `run_attempt` |
| Started | `run_started_at`, as an age ("3m ago") |
| Duration | `Model.duration(run, now)` (existing, line 26) |

#42 decision 2 keeps SHA and attempt out of the row. This pane is where they
live, so the two issues fit together.

**Which row opens it.** Any row of kind `run`, `job` or `step` shows its parent
run, found with `Polling.runFor(polling, row.repo, row.run)`. Repo and message
rows show one line: "Select a run". `runFor` already exists (`Polling.js` line
15) and reads only the in-memory list.

**Key.** `i` toggles the pane. `Esc` closes the pane first, then follows the
existing order (clear filter, then close the popup). There are two Esc paths
and both change: the navigation handler (`ActionsPanel.qml` line 236) and the
search-field handler (line 281, which today clears the filter). In the search
field, Esc with the pane open closes the pane, keeps the filter text and keeps
the popup open. `i` does not clash with
any key in `ActionsPanel.qml` lines 236-251 or with the keys #42 adds
(`y`, `?`, `g`, `G`, Right, Left). The pane state is a QML property
(`property bool detail`), not stored. While searching, `i` is typed into the
field as today, because the search field takes key events first.

**Layout.** The pane sits between the list and the footer in the existing
`Column` (`ActionsPanel.qml` lines 255-381). The list height is
`parent.height - y - footer.height - spacing` (line 305). It must subtract the
pane height too, or the list overlaps the pane. When the pane is closed its
height is 0. The pane uses the same `Style` sizes and `Color.menu` colours as
the footer and the rows, `textFormat: Text.PlainText`, and elides long values.
The pane height is capped at a share of the card height. All nine lines stay
reachable under the cap: the pane content scrolls vertically (`Flickable`);
the list keeps a minimum height of three rows, and the pane shrinks first
when space is short. The plan fixes the share and the small viewport used by
the smoke test.
There are no buttons: the pane is read-only text, and `o` still opens the
selected row's URL.

**Where the logic lives.** One new pure function in `ActionsModel.js`:
`detail(run, now)` returns an array of `{label, value}`. It has no Qt
dependency, so `tests/model.cjs` can test it. It reads only the cleaned flat fields `actor_login` and `triggering_login`, never the nested `actor.login`, which `plain_fields()` does not clean (`actions.py` line 35; `Polling.js` keeps the nested originals). It validates the commit with
`/^[0-9a-f]{40}$/` and shows `unknown` otherwise. It does not touch `rows()`,
`shownFields` or `syncRows`, so row delegates and the 1 Hz rebuild are
unchanged.

**Untrusted text (#32).** The pane is an extra place where GitHub text reaches
QML. Today `RUN_TEXT` in `actions.py` line 42 cleans `name`, `display_title`
and `head_branch`. This change makes sure these are cleaned too, in the same
`plain_fields` call (lines 182 and 192): `event`, `path`, and the logins. The
logins are nested (`actor.login`), so the helper copies them into the run as
flat fields, `actor_login` and `triggering_login`, after `plain()`. #42 also
needs `event` and `actor` in the row and lands first, so it will probably have
added them. This spec says: add whichever is missing, and test each field
with a control character. The flat fields are set on both reply paths: the
single-run reply (`actions.py` line 182) and the list reply (line 192).

### Active account display

**What it shows.** The title line becomes
`GitHub Actions · 12 repositories · olafkfreund@github.com` (line 260). Host is
the literal `github.com` already pinned in `actions.py` line 47. It is not
read from `gh`, so it cannot be spoofed and needs no new request.

**Where the login comes from.** #41 decision 3 already adds a check of the `gh`
login on panel open, and clears repos, details and expanded if it differs.
That check is the only source. #46 does not add a second one. It reads the
login #41 keeps in the polling state and shows it. This is why #46 lands after
#41.

Shape of the helper side (owned by #41, checked here): a `page` request of
kind `account` for the endpoint `user` returns `data` = `{login}` after
`plain()` and a check that the login matches `^[A-Za-z0-9-]{1,39}(\[bot\])?$`.
`gh api user` returned a `login` field on 2026-11-16 (the account was
`olafkfreund`), and the `/user` reply is a normal 200 reply with the existing
rate-limit headers. If #41 lands with a different shape, the plan adapts to it.

**Display rules.**

- Before the first reply: `…@github.com` is not shown. The title is unchanged.
- After a failed lookup: the title is unchanged. The failure already goes to
  the status line from #42.
- When #41 clears data on a login change, the title changes in the same
  `adopt()` call (`ActionsPanel.qml` line 122), so the old and new data never
  show next to the wrong account name.
- No account switching from the panel. Switching stays `gh auth switch`
  outside the plugin (decision 8).

**What this does not do.** A switch while the popup is open is not detected
(#41 decision 3). The title therefore can show the old account until the next
open. The README should say so in one line.

### Docs and key reference

- `keybindings.sh` (the `--print` list, line 20 area) gets one line:
  `i → Show or hide run details`. `tests/test_menu.py` and the flake check
  (`bash keybindings.sh --print`) cover that it still prints.
- `ActionsPanel.qml` footer text (line 374) gets `i details`. With #42's
  status line and `?` sheet, the footer may already be shortened; add `i` to
  whatever list is there.
- README: one line for the key, one line for the account display and its
  limit.
- `flake.nix` `runtimeFiles` (lines 15-25) does not change, because no file is
  added. This is a check, not a risk: if the plan ends up adding a file, the
  list and `tests/qml-smoke.py` `required` (line 11) must change together.

### Interactions with the other in-flight issues

| Issue | Interaction |
| --- | --- |
| #41 | Owns the account lookup and the clear-on-switch. #46 only displays it. Lands first. |
| #42 | Row shows branch, event, actor, age, title. The pane adds commit, attempt, path. `Esc` order and the footer text touch the same lines. Lands first. #42 decision 11 (accessibility properties) applies to the pane too: set `Accessible.role` and `Accessible.name` on it and cover it in the smoke test. |
| #43 | Changes row order and `rows()`. The pane reads the run object, not the row, so it does not conflict. |
| #44 | Logs and watch. The pane could later offer "open log", but it does not here (decision 6). Same area: `o`, `y`, and the terminal launcher. |
| #45 | Writes. Not related. Any rerun key must not use `i`. |
| #47 | The CI smoke test checks layout (row outside the list, zero-height list, overlap). The pane must keep the list non-empty and non-overlapping when open on a small screen; the test should open the pane. |

## Alternatives rejected

- **A second `gh` login lookup in #46.** Duplicates #41's check and spends a
  request twice. Rejected: one source of truth.
- **Read the account from `gh auth status`.** It prints status to stderr in a
  human format that can change, and it does not tell which account the API
  call uses. `gh api user` asks the same pipe the panel already uses.
- **Read the host from gh.** Not needed. The host is pinned (#32). Showing the
  pinned literal is honest and cannot be changed by input.
- **Detail as extra child rows under the run.** Rows are keyed and synced
  (`syncRows`), and run children are jobs. Mixing key/value rows in would
  change the tree, search results and the `shownFields` rule for no gain.
- **A modal or a side-by-side pane.** The card is a single column and keyboard
  focus is on one item (`keys`, line 227). A modal needs a second focus
  scope. A side pane shrinks the already narrow list. A bottom pane reuses
  the layout.
- **Always-visible pane.** Costs list height on small screens for users who do
  not want it. A toggle is cheap and matches "a user who turns on nothing sees
  the same popup".
- **Fetch annotations or a log tail for failed jobs.** Decision 6: the pane
  shows only what the run carries. Logs are #44.
- **Fetch the single run on `i`.** The list already carries the fields. A
  fetch would add a request and a loading state for nothing. The existing
  `run` task is for the final status only.
- **Show the commit message from `head_commit`.** It is free-form, can be
  large and multi-line, and `display_title` already covers the title. Skipped
  to keep the clean-up surface small.

## Risks

- **Layout on small screens (any host).** A fixed-height pane could squeeze the
  list to nothing. Mitigation: cap the pane at a share of the card height,
  scroll its content vertically, elide long values horizontally, and keep a
  minimum list height (see Layout). #47's zero-height-list check must cover it. Until #47 lands,
  `tests/qml-smoke.py` checks it directly.
- **Stale detail.** The pane reads the in-memory run, which can lag by one
  poll. The pane shows no freshness indicator of its own: the result word
  matches the row, so it has the same freshness as the row. `updated_at` is
  not a fetch time (`Polling.js` records fetch times separately), so the pane
  does not claim it is.
- **Missing fields.** Older or partial run objects (the QML smoke fake
  returns only `id`, `name`, `status`, `run_attempt`) lack `head_sha` or
  `actor`. `detail()` must show `unknown` instead of throwing.
- **Untrusted text.** New fields (`event`, `path`, logins) are new input to QML.
  A missed `plain()` breaks #32. Covered by tests below.
- **Login lookup shape differs from the plan.** #41 may land with another
  reply shape. The plan must be written against merged #41, not this spec.
- **Stale account name.** A `gh auth switch` while the popup is open is not
  seen until the next open (accepted, decision #41-3).
- **Key clash.** `i` is free today. If a later issue wants it, the key sheet
  (`keybindings.sh`) is the place to settle it.
- **Not verified on every host.** Layout and the `Accessible` properties are
  checked on the Razer host only (the #36 smoke host). No other host was
  tried.

## Verification

Existing suites must stay green:

```
node tests/model.cjs
node tests/polling.cjs
python3 -m unittest tests/test_actions.py tests/test_menu.py
nix flake check
python3 tests/qml-smoke.py
```

New tests:

- `tests/model.cjs`: `detail()` on a full run returns the lines in order, with
  a 7-character commit; on a run with no `head_sha`, no `actor` and no
  `event` it returns `unknown` for each and does not throw; a bad
  `head_sha` (non-hex, 7 characters, an escape sequence) shows `unknown`;
  `triggering` is shown only when it differs from the actor; attempt 2 shows
  `2`. A repo row and a message row give the "Select a run" line.
- `tests/test_actions.py`: a run reply whose `event`, `path`,
  `actor.login` and `triggering_actor.login` hold control and format
  characters comes back with them removed (reuses the #32 test pattern); a
  missing `actor` (a deleted user, `null`) produces an empty flat field, not
  an error.
- If #41's account reply lacks them: a test that a login failing the pattern
  is rejected as a `setup` error, and a valid login passes through.
- `tests/qml-smoke.py`: press `i` on a run with the fake API (extend the fake
  run with `head_sha`, `event`, `actor`); check the pane is visible, shows the
  commit, and the list height is at least the minimum (three rows) and pane, list and
  footer do not overlap, at a small fixed viewport named in the plan; press `Esc` and check the pane
  closes first and the popup stays open; press `i` on the repo row and check
  the "Select a run" text; check the title shows the account from the fake
  `account` reply and does not show one before it. Add the pane's
  accessibility properties to the existing accessibility check (#42 decision
  11). Today `qml-smoke.py` calls panel functions directly (for example
  `panel.move(1)`, line 102) and has no key-event driver or accessibility
  check. Those come from #42 or #47 if merged by then; otherwise the plan adds
  a minimal key-event helper (synthetic key events on the `keys` item) and
  must not assume one exists. Also test Esc inside the search field: pane
  closes, filter text and popup stay.
- Account isolation (integration, `tests/polling.cjs` or the smoke test): with
  account A's data loaded, close, switch to B, reopen. While the lookup is
  pending or failed, the title shows no account and A's cached data is not
  shown under B; when B's login arrives, the title and the cleared data change
  in the same `adopt()` call.
- `tests/test_actions.py` and `tests/model.cjs` together: a run with a `null`
  actor goes through the helper (list reply and single-run reply) and
  `detail()` shows `unknown`, not an error.
- Runtime check on the real desktop (owner): open the popup, select a run, press
  `i`, compare each line with `gh api repos/<repo>/actions/runs/<id>`, check
  the title login against `gh api user --jq .login`.
- `bash keybindings.sh --print` lists the `i` line (already inside the flake
  check).

What I could not verify:

- #41's final account request shape: it is an approved decision, but the code
  is not written. This spec states the contract it needs.
- That Omarchy's menu or Hyprland binds a global key that clashes with `i`
  inside the popup. Panel keys only act inside the popup (README line 117),
  so a clash is not expected, but I did not test it.
- Behaviour on GitHub Enterprise (out of scope).
- No Omarchy terminal launcher or step-anchor facts were needed here.
  Those belong to #44 and #42.

Skipped: a `gh` flag check for any new command, because none is added; the
account lookup is the same `gh api <endpoint>` call the helper already makes.
