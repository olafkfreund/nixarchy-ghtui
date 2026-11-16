---
status: approved
issue: 44
author: olafkfreund
---

# Intent: Read failed logs and get notified when a run finishes

## Problem

The panel shows that a run failed, but not why. It also says nothing when a
run you were waiting for finishes. Two gaps, one issue (#44).

**No log access without the browser.**

- The panel shows runs, jobs and steps with status and timers, and nothing
  more. `ActionsModel.js` builds those rows (lines 60-79). A row carries a
  `url` and no log text.
- The only way out of the panel is `o`, which calls
  `Quickshell.execDetached(["xdg-open", current.url])`
  (`ActionsPanel.qml` line 173). That opens the run or job page on GitHub.
- The README tells the user the same thing: "Open GitHub for full logs"
  (line 148).
- `actions.py` has no log request. Its only GitHub call is
  `gh api --hostname github.com ... <endpoint>` (line 47). No runtime plugin
  code reads a log.
- A job's id appears only inside its row key
  (`runKey + ":" + job.id`, `ActionsModel.js` line 70). The row's own
  fields are `run` and `url`, not the job id.

To find out why a build is red, the user leaves the keyboard-driven panel,
opens a browser, finds the job and scrolls.

**No notification when a run finishes.**

- The panel only learns that a run finished while it is open and polling.
- Closing the panel stops everything: `Polling.close()` clears all tasks and
  the in-flight request (`Polling.js` lines 32-34), and `close()` in
  `ActionsPanel.qml` stops the helper (lines 54-58).
- The README states this as a design rule: "No polling occurs while closed"
  (line 170). It also promises "No buttons, background daemon, database or
  token storage" (line 3).
- No runtime plugin code sends a desktop notification.

So a user who starts a long run, closes the panel and goes back to work has
to remember to come back and look.

Comparable tools (`gh run watch`, lazyactions, cimon) do both, as the issue
says.

## Proposed outcome

Holds whichever way the open questions are answered:

- From a failed run or job in the panel, the user can read its failed log
  without opening a browser, using the keyboard only.
- The user can tell which run or job the log belongs to, and whether the log
  is complete, cut short, or could not be fetched.
- The user can mark a run as watched. When a watched run finishes, the user
  gets a desktop notification that names the repository, the run and the
  result.
- A user who does not use either feature sees no change. Nothing new polls,
  fetches or notifies until they ask.
- Nothing is written to GitHub. Logs and watching are read-only.
- Whatever the user does, requests stay within the existing ceilings (see
  Constraints). This is checkable in the existing polling tests.

Whether the notification must also arrive after the panel is closed is open
question 2.

## Affected users and systems

- Anyone who debugs failing workflows from the panel. This is the main use
  case, and today it ends at the browser.
- Anyone who starts long runs and wants to be told, instead of re-opening
  the panel.
- Files likely touched: `ActionsPanel.qml`, `ActionsModel.js`, `actions.py`,
  `Polling.js`, `keybindings.sh`, `README.md`.
- Tests: `tests/model.cjs`, `tests/polling.cjs`, `tests/test_actions.py`,
  `tests/qml-smoke.py`.
- Runtime dependencies. Today `gh`, `python3` and `xdg-open` (README lines
  22-23). A terminal or a notifier may be added, depending on the answers
  below. `flake.nix` is the packaging point in this repository.
- The Nixarchy consumer repository (`olafkfreund/nixarchy`, its
  `modules/home.nix`) declares runtime dependencies too. Any change there is
  a separate issue and PR, as in #32.
- GitHub API quota. Reading logs and watching runs use extra quota.

## Constraints

Kept from the plugin's design:

- **Keyboard-first.** Both features reachable with keys, shown in the
  status line.
- **Theme-native.** Anything drawn in the panel uses Omarchy's theme colours
  and fonts like the rest of the panel.
- **Argument arrays, not shell strings.** Any process started gets a list of
  arguments. Repository, run id and job id come from validated values only.
  `actions.py` already checks the repository and run id (lines 23 and 73).
- **No token storage.** Authentication stays with `gh auth login`. The
  plugin never extracts, stores or passes the token itself.
- **github.com only.** GitHub requests are pinned to `--hostname github.com`,
  as in `actions.py` line 47.
- **Untrusted GitHub text (#32).** URLs still go through `Model.browsable()`
  before `xdg-open`.
- **Log text is untrusted.** A log is written by whoever controls the
  workflow, which includes a fork's pull request, and by every tool that
  ran. It can contain terminal escape sequences, control characters, bidi
  overrides, extremely long lines, and secrets that GitHub's masking missed.
  Whatever shows a log must not interpret escape sequences, must not run
  anything it finds in the text, and must not let a huge log stall the panel
  (the same worry as #30).
- **Read-only.** No rerun, cancel or dispatch. Those are separate work and
  need broader token permissions.
- **API budget.** Log reads and watching stay within the existing ceilings:
  at least one second between requests, at most 60 a minute, one request in
  flight (`Polling.js` lines 97-115), plus cooldowns and rate-limit
  handling. Any option that makes requests outside that scheduler breaks
  this constraint.
- Existing tests keep passing. New behaviour gets tests next to them.
- No new dependencies beyond what the owner approves under the open
  questions.

What this task may bend:

- **"No polling while closed" (README line 170) and "no background daemon"
  (README line 3)** are bent only if the owner wants notifications after the
  panel is closed (open question 2). Then it must be opt-in, per run, and
  visibly on. Otherwise both rules stay intact.
- **The panel's own view of the log** is bent only if the owner accepts
  showing it outside the panel (open question 1).

Not bent: no token storage, host pinning, argument arrays, keyboard-first.

## Open questions

1. **Where does the user read the log?** In the panel, in the panel's own
   theme, or in a separate terminal window of their own? The panel is safer
   with untrusted text and matches the design, but is more work. A separate
   window is smaller, and gives the user their own scrolling and search, but
   leaves the theme and depends on a terminal. Or both, one after the other?
2. **Must a notification arrive after the panel is closed?** If no, only
   runs seen finishing while the panel is open can notify, and the closed
   rules stay intact, but the main use (start a run, close the panel, get
   told) is not served. If yes, which rule gives way: the plugin keeps
   checking in the background while a run is watched, or something outside
   the plugin watches? An outside watcher uses its own requests and does
   not meet the API budget constraint, so choosing it means the owner
   relaxes that constraint.
3. **How is the notification shown?** Through a new runtime dependency, a
   Quickshell or Omarchy facility, or something else? This has to be checked
   on a real Omarchy install; it is not verified here.
4. **If a terminal window is used (question 1 or 2), how does Omarchy open
   one with a given command?** Not verified. Only matters if a terminal is
   chosen.
5. **What is "the log"?** Failed steps only, or the full job log? Only for a
   failed job, or for any completed job? Previous attempts of a run are out
   of scope unless the owner says otherwise.
6. **What does the user watch, and when does watching end?** The selected
   run only, or any run? Several at once? Does a run already queued or
   running when the panel opens count? How is a run un-watched? What happens
   to watched runs when the shell restarts (README line 168: "A shell restart
   clears local memory")? What happens when a watched run is re-run (same
   run id, new attempt, see `Polling.js` line 124-127)? What does the user
   see if the final lookup fails, for example on a permission error
   (`Polling.js` lines 188-190)?
7. **What does the notification say?** Which results does it distinguish? The
   panel already knows more than success, failure and cancelled (timed out,
   startup failure and others, `ActionsModel.js` lines 15-20). Text comes
   only from the repository name, run number and result. Should clicking it
   open the run on GitHub?
8. **Should it also fire for runs the user did not mark?** For example
   "any failure in a repository I selected". The issue as read here asks for
   watched runs only; this widens scope, so the default is no.
9. **Dependencies and packaging.** If a new tool is needed, should
   `flake.nix` declare it (as #32 did for `gh`, `python3` and `xdg-open`),
   or only the README? The consumer repository follow-up is separate.
10. **Order of work.** Logs and notifications are two features under one
    issue. Should they ship together, or logs first because they need no
    change to the polling rules?
