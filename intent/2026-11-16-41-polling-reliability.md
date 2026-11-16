---
status: approved
issue: 41
author: olafkfreund
---

# Intent: Polling stops retry loops, stale runs and stuck loading states

## Problem

The panel polls GitHub on a timer. Several failure paths either keep
hammering GitHub, or leave the screen saying something that is no longer
true. All line numbers below are from the current code (after #24 and #30).
The Codex review of 2026-11-16 found them; I re-read each one in the code.

1. **A catalogue 403 retries every second.** On a `permission` error,
   `complete()` deletes the failed task (`Polling.js:187-191`). Only
   repository tasks get marked `blocked` (line 188), and a catalogue task has
   no repository. `s.discover` stays true, so the next `seed()` recreates the
   task straight away (line 64). The scheduler allows one start a second and
   60 a minute (`TIMING.gap`, `TIMING.perWindow`, line 4; `next`, lines
   97-100). So a token that can't read `/user/repos` makes the open panel call
   it up to 60 times a minute, until it is closed or rate-limited. The README
   (line 168) says permission failures stay unavailable "until
   catalogue/manual refresh", which is not true for the catalogue itself.
2. **A failed jobs fetch can show "Loading jobs…" for good.** Only a
   `permission` error writes `details[...].error` (`Polling.js:189`). A
   network or server error goes to the `else` branch (lines 192-197), which
   sets only the task's backoff and the repository error (line 196). That
   error shows on the repository row, not under the run. `Model.rows()`
   shows "Loading jobs…" whenever there is no detail entry
   (`ActionsModel.js:67-68`). So the first jobs fetch failing offline leaves
   that line up through every retry. If jobs were cached, the old rows stay
   with no sign under the run that the refresh is failing.
3. **A queued or waiting run can stay queued for good.** Only runs that were
   `in_progress`, or that have a `followupAt`, get a single-run lookup
   (`Polling.js:85-86`, `153-159`). A run cached as `queued` has neither.
   `kept()` (lines 146-148) protects expanded and inspected runs from the
   completed-run trim, and the summary adds them back each time (lines
   235-236). If that run finishes and drops out of GitHub's recent results,
   nothing refreshes it. It keeps its old status, even after a full summary.
   Background activity only asks for `in_progress` runs
   (`actions.py:77`), so an unfinished run in a repository that is not
   selected has the same gap.
4. **The highlighted row and the polling target can disagree.** `rebuild()`
   keeps the selected key, or falls back to the old row number
   (`ActionsPanel.qml:77`, `ActionsModel.js:87-90`). `adopt()` tells polling
   about the new selection only when the selected repository no longer exists
   (`ActionsPanel.qml:129`). If the selected run disappears while a reply is
   adopted, the highlight moves to a different repository's row.
   `polling.selected` and `inspected` still name the old one, so priority
   refresh goes to the wrong place until the next key press. (A typed filter
   change already re-syncs, `ActionsPanel.qml:35-38`; only a reply that
   changes which rows match has this gap.)
5. **Manual refresh doesn't move a task that is backing off.** `ensure()`
   only updates `group` on an existing task (`Polling.js:25`).
   `manual()` calls it with `due = now` (lines 47, 50), which is ignored
   for a task that already has one. A failed summary or jobs task sits at
   `now + up to 5 minutes` (line 193, `retryMax`), so pressing `r` after the
   network is back can still wait minutes. This is separate from the rule
   that refresh must respect a GitHub cooldown, which is right.
6. **A `null` step passes the helper and breaks the panel.**
   `actions.py:193-195` only sanitises steps that are objects. It doesn't
   reject the others, and line 189 only checks that `steps` is a list. The
   model then reads `step.status` (`ActionsModel.js:72`), which throws on
   `null`. One bad jobs reply can stop the whole row rebuild. A test accepts
   a string step as intended (`tests/test_actions.py:201-203`), so that
   behaviour is deliberate today and needs a decision.
7. **Polling doesn't slow down as quota runs low.** The helper reads
   `x-ratelimit-remaining` (`actions.py:142-143`), but the scheduler only
   acts when it is exactly `0` (`Polling.js:176`). The value is not kept or
   shown. At the ceiling, one open panel can use 3,600 requests an hour
   (60 a minute), out of a quota other tools on the account share.
8. **Cached data is never cleaned up, and survives a `gh` account switch.**
   `s.details` is only deleted when a run's attempt changes
   (`Polling.js:129`). `close()` clears tasks and the in-flight request but
   not `repos`, `details` or `expanded` (line 34), and `manifest.json:6` keeps
   the plugin loaded (`keepLoaded`). Nothing in the code looks at which
   account `gh` is using. A catalogue refresh updates repositories both
   accounts can see in place and keeps their runs (`Polling.js:216-217`); it
   only drops repositories that vanished (lines 223-225) and never touches
   `details`. So after `gh auth switch`, the previous account's runs and job
   details can stay in memory and on screen, and a switch while the panel
   stays open is not seen at all. Job and step data for runs you once opened
   is kept for the life of the shell.
9. **Expanded runs stop updating without saying so.** Only the inspected run
   gets job refreshes (`Polling.js:88-93`). Move to another row and the jobs
   you left stay on screen. Their durations keep counting up from `now`
   (`ActionsModel.js:26-33`, no `completed_at`), even if the job has
   finished. The only age cue is "jobs fetched HH:MM UTC" in the run's
   subtitle (`ActionsModel.js:62`).

## Proposed outcome

What holds whichever way the open questions are answered:

- A token that can't read the repository catalogue does not make the panel
  call the catalogue once a second. In a test, the open panel's catalogue
  requests stay within the existing 60 a minute ceiling and drop well below it
  after the first failure.
- A failed jobs fetch is never shown as "Loading jobs…". The run shows that
  the fetch failed, and cached jobs stay visible.
- A queued or waiting run that has finished on GitHub is not left showing its
  old status after a full summary. Which runs this covers is open question 5.
- After every rebuild, the highlighted row and the repository and run that
  polling refreshes first are the same.
- Pressing `r` retries the selected summary and jobs even if they were backing
  off. It still never overrides a GitHub cooldown or the 60 a minute ceiling.
- A jobs reply with a `null` or otherwise bad step can't break the row
  rebuild.
- Data from a previous `gh` account is not shown as current. When it is
  cleared is open question 3.
- Job rows you expanded and then left are not presented as live. How is open
  question 6.

Slowing down as quota falls, and any cap on cached data, are decided in open
questions 4 and 7.

## Affected users and systems

- Anyone using the panel with a restricted token, a flaky network, several
  `gh` accounts, or a shell that stays up for days.
- Anyone sharing the account's hourly request quota with other tools (CI
  scripts, `gh` in terminals, other apps).
- Files: `Polling.js` (`complete`, `ensure`, `manual`, `seed`, `close`,
  `kept`), `ActionsModel.js` (`rows`, `duration`), `ActionsPanel.qml`
  (`rebuild`, `adopt`, status text), `actions.py` (`read_page`, and the
  rate-limit headers it already returns).
- Tests: `tests/polling.cjs`, `tests/model.cjs`, `tests/test_actions.py`,
  `tests/qml-smoke.py`. The README polling section changes too (lines
  168-170).

## Constraints

- **Design stays as it is.** No daemon, no polling while the panel is closed,
  no token read or stored by the plugin, no state file or database.
  Keyboard-first, theme-native colours and sizes, no buttons.
- **Safe by construction.** `gh`, Python and `xdg-open` still receive
  argument arrays, never shell strings. Untrusted GitHub text still goes
  through the sanitising from #32, and requests stay pinned to `github.com`.
  New messages come from a fixed set of known texts, not from raw GitHub or
  stderr text (#24).
- **API budget doesn't grow.** At least one second between requests, at most
  60 a minute, existing cooldown handling. A fix may only reduce requests,
  except where it needs a bounded number of extra lookups; the owner sets
  that bound in open questions 3 and 5.
- **Earlier decisions may be revisited.** Some options below change approved
  earlier rules: live-ticking elapsed times (`intent/2026-09-24-23-live-timers.md`),
  never dropping inspected runs (`spec/2026-09-24-30-large-repos.md`), and
  showing cached data at once on reopen (`spec/2026-09-16-9-smart-polling.md`).
  Each question says which one it touches.
- No new dependencies. Existing tests keep passing, and each fix adds a test
  next to the current ones.
- Stale replies are still rejected by `requestId` and `generation`.

## Open questions

1. **Catalogue 403.** After the first permission failure, should the panel
   stop asking until you refresh or reopen, with a message, or keep retrying
   at a slower pace like other network errors? Should repositories already
   known stay listed either way?
2. **Null and non-object steps.** Should one bad step make the whole jobs
   reply count as invalid, or should the bad entry be dropped and the rest
   kept? The string-step test (`tests/test_actions.py:201-203`) has to change
   either way.
3. **Account switch.** Must the panel notice a switch while it stays open, or
   only when it is opened or the catalogue is refreshed? Is one extra request
   to learn which account is in use acceptable? Does showing cached data at
   once on reopen still win over clearing it?
4. **Quota slowdown.** Should background polling slow down as quota falls, or
   should the panel only show remaining quota and reset time? If it slows
   down, how far, and should interactive work (selected and inspected data)
   keep full pace? Is a persistent status line for quota and errors wanted
   here, or left to a separate UI issue?
5. **Stale queued runs.** Which runs must be corrected: only those in the
   selected or expanded repository, or unfinished runs in every repository?
   How many extra lookups per summary are acceptable? Is it acceptable to
   drop a retained run that GitHub no longer lists, even though the inspected
   run is meant to stay?
6. **Expanded runs you left.** Should they be marked as not refreshing, with
   their age; refreshed in the background; or collapsed when you leave? Is it
   acceptable that their durations stop ticking?
7. **Memory growth.** Should cached job details, retained runs and expanded
   flags for runs that are gone be cleaned up, or capped at a number of
   recently viewed runs? What number?
8. **Scope.** Should these land together on one branch, or should some become
   their own issues? Quota (item 7) and accounts (item 8) are the most likely
   to grow.
