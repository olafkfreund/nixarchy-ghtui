---
status: draft
issue: 24
author: olafkfreund
---

# Intent: A failing helper shows its real cause instead of "invalid data"

## Problem

The panel runs `python3 actions.py page <request>` for every GitHub request.
When the helper fails before it can answer the request, the user sees
"Workflow helper returned invalid data" whatever the cause was.

This happens because:

- When the helper prints nothing to stdout (python3 missing, argparse
  error, an uncaught exception with a traceback), `Model.reply()` in
  `ActionsModel.js` builds `{error: <stderr>}` with no `requestId`.
- When `main()` in `actions.py` catches an error itself (for example a
  malformed request), it prints `{"error": ...}`, also with no `requestId`.
- `receivePage()` in `ActionsPanel.qml` rejects any reply whose `requestId`
  doesn't match the request. It then replaces the reply with
  `{error: "Workflow helper returned invalid data", errorType: "network"}`.

As a result:

- Every such failure looks the same, and the message doesn't say what to fix.
- Because it is classed as a network error, `Polling.complete()` retries it
  with backoff for as long as the panel is open. A broken install is never
  shown as something the user has to fix.
- It can never be classed as an auth or permission error, so the panel never
  stops to say "run gh auth login".

Related problems found in review:

- A missing `gh` binary is caught inside `read_page()` as an `OSError`. It is
  reported as "GitHub request timed out or returned invalid data", which
  suggests a network problem when the fix is to install gh.
- `Model.reply()` puts up to 300 characters of raw stderr into the error
  text. That can include local paths and traceback lines, and the panel
  would show it as is.
- A reply with the right `requestId` but a missing or wrongly shaped `data`
  field goes into `Polling.complete()` unchecked. `complete()` calls
  `data.forEach`, `t.items.concat(data)` and `union(t.items, data)` on it,
  which can throw inside the panel's event handler.

## Proposed outcome

- If the helper can't run or fails, the panel shows a short message that
  names the cause and what to do. For example: "Install gh (GitHub CLI)",
  "python3 not found", "Run gh auth login", or "Workflow helper failed
  (exit 2); see the journal for details".
- Problems that retrying can't fix (python3 or gh missing, a helper crash,
  signed out) stop polling until the user refreshes or reopens the panel,
  as auth errors already do. They are not retried as network errors forever.
- Real network, rate-limit and permission errors behave as they do now.
- Raw stderr and tracebacks don't appear in the panel. The full detail is
  still available to someone debugging, for example in the Quickshell log.
- A reply with the right identity but bad `data` is shown as an error and
  never throws.

## Affected users and systems

- Anyone using the panel, especially on a new install where `gh` isn't
  installed or signed in yet, which is the most likely first experience.
- Files: `ActionsModel.js` (`reply`), `ActionsPanel.qml` (`receivePage`,
  `requestProc`), `Polling.js` (`complete`), `actions.py` (`read_page`,
  `main`).
- Tests: `tests/model.cjs`, `tests/polling.cjs`, `tests/test_actions.py`.

## Constraints

- No token, secret, header or raw `gh` output may appear in the panel.
  Messages come from a fixed set of known texts.
- Stale replies must still be rejected. A reply may only be applied to the
  request with the same `requestId` and the current polling `generation`.
  The fix must not accept a reply without an identity as belonging to the
  current request unless it can be tied to that request some other way.
- The panel stays read-only. Nothing new is sent to GitHub.
- Existing tests in `tests/` keep passing. New behaviour gets tests next to
  them.
- No new dependencies.

## Open questions

1. When a failure can't be fixed by retrying (python3 or gh missing, helper
   crash), should the panel stop polling until a manual refresh (`r`), as
   auth errors do, or keep retrying slowly?
2. Should full stderr be written to the Quickshell log (`console.warn`) so
   the "see the journal" hint is true, or is dropping it fine?
3. Should the helper's other modes (`summary`, `jobs`, `repositories`,
   `activity`) get the same treatment, or only `page`, which is the only
   mode the panel uses?
