---
status: draft
issue: 46
author: olafkfreund
---

# Intent: Beyond the popup: bar indicator, PR checks view and run detail pane

## Problem

The panel only helps while it is open. It shows nothing on the bar, no
pull-request checks, and no single-run detail. It also can't tell you which
GitHub account it is reading, and it works only on github.com. Issue #46
lists six ideas. Each one bends a rule the plugin was built on, so the
owner has to choose which rules to bend before any design starts.

What the code does today:

- **Nothing runs while the panel is closed.** `close()` in the panel sets
  `opened = false`, calls `Polling.close` and stops the helper
  (`ActionsPanel.qml` lines 54-58). `Polling.close` clears every queued
  task and the request in flight (`Polling.js` line 34). The scheduler only
  hands out work when `s.opened` is true (`Polling.js` line 98). Both timers
  run only while `root.opened` (`ActionsPanel.qml` lines 189-190). The
  README states the same promise: "No polling occurs while closed"
  (line 170). So a failing build is invisible until you open the popup.
- **The plugin is a panel only.** `manifest.json` has `"kinds": ["panel"]`
  and one entry point, `panel` (lines 9-14). It also sets
  `"keepLoaded": true` (line 6), so the panel's QML stays loaded between
  opens. That is why caches survive a close.
  - Two sibling plugins on this machine declare
    `"kinds": ["menu", "bar-widget"]` with
    `entryPoints.barWidget: "Panel.qml"` (`nixarchy.podman` and
    `nixarchy.microvm`, read from their built manifests in the Nix store).
    So a bar widget kind exists in some Omarchy shell build. I could not
    find the contract text itself, so I do not know whether one plugin can
    offer both a panel and a bar item.
- **Only workflow runs, jobs and steps are fetched.** The helper builds
  endpoints for the repository catalogue, activity, runs, a single run, and
  jobs (`actions.py` `page_endpoint`, lines 59-82). There is no pull-request
  endpoint and no GraphQL call anywhere in the code.
  A pull request's checks are not a list of Actions runs: they come from
  check suites that GitHub rolls up per commit, and they include checks that
  are not Actions at all. The panel can't show them today.
- **Run detail is one line.** A run row's subtitle holds branch, number,
  fetch time and title, elided into one line, and the payload fields for
  actor, event, SHA and attempt are not shown (the Codex review, finding on
  "no detail view or tooltip", and the roadmap's UI list; I confirmed the
  row fields are built in `ActionsModel.js` `rows()`, lines 35-85). A failed
  job's log tail and annotations are not fetched at all.
- **Repository order is fixed, and there are no pins.** The list comes from
  `user/repos`, sorted by `pushed` (`actions.py` line 68), then the panel
  re-sorts it with running repositories first (`ActionsModel.js` line 38). The
  list holds only repositories associated with your account (README line
  121). You can't mark a repository to keep at the top. Any pin needs a place
  to live, and the README promises "no ... database or token storage"
  (line 3).
- **The account is invisible.** The helper uses whichever `gh` login is
  active and never asks which one it is. The Codex review notes that caches
  are not split by account, so after you switch `gh` accounts the old
  account's private repositories can stay on screen. I found no account
  field in `Polling.js` state or in `actions.py`.
- **github.com is pinned on purpose.** The helper always passes
  `--hostname github.com` (`actions.py` line 47). Pagination links are
  accepted only for `api.github.com` over https (`next_page`, lines
  108-123). The "open on GitHub" key accepts only `https://github.com/`
  URLs with no whitespace or control characters (`ActionsModel.js`
  `browsable`, lines 9-11), and the repo row URLs are built from the same
  literal host (lines 49 and 57). This came from #32 and is a security
  choice, not an omission. The README says "Currently github.com only"
  (line 121).
- **The helper is read-only, and GitHub text is cleaned.** It only issues
  `gh api` reads (`actions.py` line 1 and `request`, lines 45-56). The
  text fields the panel shows or searches go through `plain()`, which
  removes control and format characters (lines 27-32; `plain_fields`, lines
  35-43, 182-195; #32). The panel also renders them as plain text
  (`ActionsPanel.qml` lines 263 and 298).

## Proposed outcome

The owner picks which of these six stay in scope. For each one that stays,
this is what a user can see and do. How each is built is for the spec.

1. **Bar indicator.** Without opening the popup, a user can see on the
   Omarchy bar whether any repository has a running workflow and whether any
   has a failing one, and can open the popup from it by mouse and by key.
   Which repositories count is an open question (2).
2. **PR checks view.** A user can see the checks of a pull request, each with
   its name and a result (pass, fail or running), and open one on GitHub.
   Whether non-Actions checks are included is an open question (4).
3. **Run detail.** A user can select a run and read more about it than one
   row holds: commit, actor, event, attempt and age. How much more, for
   failed jobs, is an open question (6).
4. **Pins.** A user can keep chosen repositories at the top of the list. How
   a pin is chosen and kept is an open question (7).
5. **Active account shown.** A user can see which `gh` account (and host) the
   panel is reading, and after switching `gh` accounts the panel never shows
   the previous account's private repositories.
6. **GitHub Enterprise.** If allowed (question 9), a user on a GitHub
   Enterprise Server host can use the panel against that host, and the
   panel still refuses links to any other host.

A user who turns on none of the optional items sees the same popup, request
rate and polling as today. Items 4 and 5 may change what the popup shows
(order, a visible account), so they are not "off" by default unless the
owner says so (question 7, 8).

## Affected users and systems

- Users who want to see CI state without opening the popup (item 1), who
  review pull requests (2), who debug a failed run (3), who work in many
  repositories (4), who use several `gh` accounts (5), or who work on
  GitHub Enterprise (6).
- Code areas: the manifest, the panel QML, the model, the polling
  scheduler and the helper; a new QML file for item 1; `menu.py`,
  `keybindings.sh` and the example menu and key files for new keys; the
  README; and `flake.nix`, whose `runtimeFiles` list (lines 15-20) names
  every shipped file and whose check (line 69) requires each manifest entry
  point to be in the package.
- Tests: `tests/polling.cjs`, `tests/model.cjs`, `tests/test_actions.py`,
  `tests/qml-smoke.py`, and the flake smoke test from #36.
- Shared GitHub quota. Item 1 may spend it while the popup is closed. The
  existing limits are one request in flight, a one-second gap and 60
  requests a minute (`Polling.js` `TIMING`, lines 3-5).
- Related open issues touch the same code: #41 (polling retries), #42 (panel
  UI and keys), #43 (repo health, last result per repo) and #44 (logs and
  watch). Item 3 overlaps #42 and #44, and item 1 overlaps #44's
  background-watch idea. The owner should decide the order.
- Omarchy shell itself, for item 1: how it loads a second kind from one
  plugin.

## Constraints

Rules that must hold for every item:

- **Keep: no independent background service.** The plugin already starts
  `python3` and `gh` and hands links to `xdg-open` (`ActionsPanel.qml` lines
  143 and 173; `actions.py` line 46). That stays. Nothing may keep running
  once the Omarchy shell stops.
- **Keep: no token handling.** The plugin keeps using `gh`'s own login. It
  never reads, copies or stores a token (README lines 129 and 170).
- **Keep: theme-native and keyboard-first.** New views use the shared
  `qs.Commons` / `qs.Ui` look, and everything reachable by mouse is also
  reachable by key. A bar item needs a key-driven way to open the popup.
- **Keep: argument arrays, never shell strings.** Every new `gh` call is
  built as an argument list, as `request` does today (`actions.py` line 47).
- **Keep: untrusted GitHub text is cleaned.** Every string from GitHub that
  the panel shows or searches (check names, annotation messages, log lines,
  actor names, account names) is cleaned, as `plain_fields` does for the
  run fields today, before it reaches QML (#32). Log text is the riskiest:
  it is long, free-form and can carry escape sequences.
- **Keep: request budget.** New calls obey the same one-in-flight, 1 s gap,
  60 per minute limit and the rate-limit cooldown. They must not starve the
  checks the popup already does: a refresh the popup owes is never held back
  indefinitely by new work. (One request can still take up to 25 s, so some
  delay under load is already normal; README line 170.)
- **No new dependencies.** QML, Python standard library and `gh`.

Rules this task would bend, per item (the owner decides which bends are
acceptable):

| Item | Bends | How |
| --- | --- | --- |
| 1 Bar indicator | no polling while closed | Work happens while the popup is closed, which the README promises not to do. |
| 1 Bar indicator | panel-only manifest | The plugin would have to be something besides a panel. |
| 2 PR checks | workflow-runs-only data | The helper has no pull-request or check-rollup call today, and its allowed endpoints are fixed. |
| 3 Run detail | row-per-run view | Needs extra fetches (annotations, log), which must be bounded and cleaned. |
| 4 Pins | read-only, no storage | Pins need a place to live. If that place is on GitHub and can be changed from the panel, the helper makes its first write (the question #45 asks for reruns). |
| 5 Account shown | none, but touches caching | The panel needs to learn the account and keep one account's data apart from another's. |
| 6 GitHub Enterprise | host pinning from #32 | The host becomes variable. Every place that assumes github.com (helper host, pagination check, open-on-GitHub check, repo URLs) must still refuse another host. |

## Open questions

1. **Which items are in scope for this issue?** Options: all six as one
   piece of work; split into one issue each; or take first the items that
   bend the fewest rules (5, and 2 or 3 if the data stays read-only) and
   park the rest. My suggestion, for the owner to accept or reject, is to
   split, because items 1 and 6 change the design promises, and items 2, 3
   and 4 each bend a smaller one (see the table).
2. **Bar indicator: may the plugin work while the popup is closed?**
   Options: no (drop item 1); yes, with an opt-in; or show only what the
   popup last fetched, with no new work, which is cheap but goes stale.
   If yes: which repositories count (all, or only those last seen
   running), how often, and what "failing" means when the code today keeps
   a running count per repository but no failure count. How is the opt-in
   given, when the plugin has no settings file and no storage?
3. **Bar indicator: can this be one plugin?** Can one plugin be both a panel
   and a bar item, and what must the bar file offer? I could not verify
   this. If it can't, options are a second plugin for the bar item, or drop
   item 1.
4. **PR checks: which data?** Options: include checks that don't come from
   Actions (needs a new kind of call and more requests); or show only
   Actions checks and reuse the runs already fetched, matching them to a PR
   by commit.
5. **PR checks: where does it start?** Options: a new top section listing
   open PRs you authored or were asked to review; a per-repository
   pull-request row; or the checks of the selected branch only.
6. **Run detail: how much?** Options: what the run already carries (commit,
   actor, event, attempt, age; no new requests); that plus the failure
   annotations of failed jobs; or that plus a bounded tail of the log. A log
   tail needs an upper size and overlaps #44. Does it belong here or in #44?
7. **Pins: where do they live, and who changes them?** Options: pins are
   shared with GitHub (for example stars) and changed only on GitHub; the
   panel can also change them, with a confirmation; or the plugin keeps its
   own list (this breaks "no storage"). Shared pins also touch your normal
   GitHub use, so some people won't want that. Also: does a pinned
   repository stay above running ones, or do running ones still come first?
8. **Account display: how deep?** Options: show the login and host only; also
   clear the previous account's data when the login changes; or also let you
   switch accounts from the panel (this changes `gh`'s state outside the
   plugin, so likely out of scope). If the clearing is in, is it fixed here
   or in #41?
9. **GitHub Enterprise: allowed at all?** Options: no, github.com stays the
   only host (drop item 6); one host chosen by the owner's setting (see
   question 2 for the missing settings place); or the host `gh` is logged in
   to by default. If allowed, the owner must confirm that relaxing the #32
   pin is acceptable and that tests will prove a link to another host is
   still refused. I could not test against an Enterprise server, so the work
   would ship unverified on real hosts unless the owner can provide one.
10. **Order against the neighbours.** Should #41, #42, #43 and #44 land
    first, since items 2, 3 and 5 reuse their changes, or does this issue
    go ahead and rebase later?

What I could not verify: the Omarchy bar-item contract (only two sibling
manifests were readable); whether a plugin may combine kinds; how Omarchy
passes settings to a plugin; the text of issue #46 and the neighbouring
issues as written on GitHub; behaviour on a GitHub Enterprise host.
