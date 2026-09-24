---
status: approved
issue: 24
intent: intent/2026-09-24-24-helper-errors.md
---

# Spec: A failing helper shows its real cause

## Design

### Scope

Only the `page` path changes: `actions.py page`, `requestProc` and
`receivePage()` in ActionsPanel.qml, `reply()` in ActionsModel.js and
`complete()` in Polling.js. The `summary`, `jobs`, `repositories` and
`activity` modes are left alone. They are being removed separately. No new
files, dependencies or GitHub requests.

Approved answers to the intent's open questions:

1. Failures that retrying can't fix stop polling until `r`, Shift+R or
   reopening the panel. This reuses the existing auth stop: `s.auth` is set in
   `complete()`, and `Polling.manual()` and `Polling.open()` clear it.
2. Full stderr goes to the Quickshell log with `console.warn`. The panel only
   ever shows a message from a fixed set.
3. Only `page` mode changes.

### One new errorType: `setup`

The existing types are `rate`, `auth`, `permission` and `network`. None of
them fits "the install is broken":

- `network` retries with backoff forever, which is the bug being fixed.
- `auth` would give the right polling behaviour, but anything that reads
  `errorType` would then treat a missing python3 as "signed out".

`setup` means the local install or the helper is broken. Polling handles it
exactly like `auth`. It is the only new type.

Polling.js:167–168 becomes:

```js
// ponytail: s.auth now means "stopped until manual refresh"; rename if a third stop reason appears
if (reply.errorType==="auth" || reply.errorType==="setup") s.auth=true;
```

The failed task goes through the existing non-permission branch
(`t.failures++`, backoff `due`). After `r`, it runs again once and stops
again if the cause is still there.

### Failure table

| # | Failure | Where it is detected | Panel message | errorType | Polling |
|---|---------|----------------------|---------------|-----------|---------|
| 1 | python3 not on PATH (QProcess FailedToStart, or empty stdout with exit 127) | ActionsPanel.qml `requestProc` → `Model.reply` | `python3 not found` | `setup` | stops until `r` or reopen |
| 2 | Helper printed nothing and exited N (missing actions.py, argparse error, uncaught traceback, killed) | `Model.reply` | `Workflow helper failed (exit N); see the shell log` | `setup` | stops until `r` or reopen |
| 3 | `gh` not on PATH (`FileNotFoundError` from `Popen` in `request()`) | `read_page()` | `Install gh (GitHub CLI)` | `setup` | stops until `r` or reopen |
| 4 | gh not signed in, or HTTP 401 | `read_page()` (unchanged) | `Authenticate with gh auth login` (unchanged) | `auth` | stops (unchanged) |
| 5 | `main()` catches `ValueError` or `KeyError` from a request it could parse, e.g. `page_endpoint` rejects it | `main()`, now with `requestId` | `str(exc)`. These are fixed strings raised by actions.py itself, e.g. `Invalid page operation` | `setup` | stops until `r` or reopen |
| 6 | `main()` catches `DeadlineExceeded`, `TimeoutExpired` or `OSError` for a parseable request | `main()`, now with `requestId` | `GitHub request timed out or returned invalid data` (unchanged) | `network` | backoff retry (unchanged) |
| 7 | Helper JSON has no `requestId` or the wrong one (request not parseable, or helper/panel version skew) | `receivePage()` | `Workflow helper returned invalid data; see the shell log` | `setup` | stops until `r` or reopen |
| 8 | `requestId` is right and there is no error, but `data` has the wrong shape (not an array of objects, or not an object for `run`) | `Polling.complete()` | `Workflow helper returned invalid data` | `setup` | stops until `r` or reopen |
| 9 | Rate limit, permission, network, bad GitHub body | `read_page()` (unchanged) | unchanged | `rate` / `permission` / `network` | unchanged |
| 10 | Helper cancelled by close (SIGTERM → `SystemExit(0)`, empty stdout) | `Model.reply` gives row 2's message | — | — | rejected by `generation` in `complete()` (unchanged) |

Row 4 keeps its current text, which already names the fix. Changing it to
"Run gh auth login" would only change wording and break existing assertions.

### actions.py

`read_page()` (lines 128–192): add a `FileNotFoundError` handler before the
generic one. `FileNotFoundError` is a subclass of `OSError`, so it has to come
first:

```python
    except FileNotFoundError:
        # ponytail: only Popen(["gh", ...]) can raise this; PermissionError stays "network"
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        ...unchanged
```

`main()` (lines 252–295): in page mode, keep the parsed task so the error reply
can carry its `requestId` when that is a positive int. This is the same check
`page_endpoint()` uses.

```python
    task = None
    ...
        if args.mode == "page":
            ...
            task = json.loads(args.targets[0])
            data = read_page(task)
    ...
    except (...) as exc:
        message = ...unchanged
        error = {"error": message}
        if args.mode == "page":
            error["errorType"] = "network" if isinstance(exc, (DeadlineExceeded, subprocess.TimeoutExpired, OSError)) else "setup"
            if isinstance(task, dict) and type(task.get("requestId")) is int and task["requestId"] > 0:
                error["requestId"] = task["requestId"]
        print(json.dumps(error))
        return 1
```

If `json.loads` fails, `task` stays `None`. The reply then has no `requestId`,
and row 7 handles it. Other modes print exactly what they print today.

### ActionsModel.js `reply()`

The new signature is `reply(stdout, code, requestId)`. The stderr parameter is
removed because stderr never reaches the panel again.

```js
function reply(stdout, code, requestId) {
    if (stdout.trim()) return stdout;
    return JSON.stringify({requestId: requestId, errorType: "setup",
        error: code === 127 ? "python3 not found" : "Workflow helper failed (exit " + code + "); see the shell log"});
}
```

QML attaches `requestId` only to replies it creates for its own process that
just finished. It knows which request that process ran (`root.requestInfo`,
set in `pump()` before `running = true`). Only one helper runs at a time
(`workerBusy`), so this reply can't belong to another request. Stale replies
from an older panel session are still rejected by `flight.generation` in
`complete()`.

QProcess doesn't normally report 127 on its own. It shows up only if python3
is reached through a wrapper or `env`. The FailedToStart path below reuses
that code on purpose so both cases share one message.

### ActionsPanel.qml

`requestProc` (lines 203–210):

```qml
onExited: function(code) {
    if (pageErrors.text.trim()) console.warn("GitHub Actions helper (exit " + code + "): " + pageErrors.text.trim())
    root.receivePage(Model.reply(pageOutput.text, code, root.requestInfo.requestId), root.requestInfo)
    root.workerBusy = false
}
// FailedToStart: Quickshell clears running without emitting exited.
onRunningChanged: if (!running && root.workerBusy) Qt.callLater(root.failedToStart)
```

and a small function next to `receivePage()`:

```js
function failedToStart() {
    if (!workerBusy) return            // exited already handled it
    console.warn("GitHub Actions helper: python3 failed to start")
    receivePage(Model.reply("", 127, requestInfo.requestId), requestInfo)
    workerBusy = false
}
```

`Qt.callLater` makes this work whichever order Quickshell emits `exited` and
`runningChanged` in. If `exited` fired, `workerBusy` is already false and
`failedToStart` does nothing. If it never fires, the panel no longer stays
stuck with `workerBusy = true`. Today that case freezes polling with no
message at all.

`receivePage()` (lines 157–170): only the catch branch changes. It uses the
row 7 message and `errorType: "setup"`, and logs the rejected text:

```js
} catch (e) {
    console.warn("GitHub Actions helper reply rejected: " + String(text).slice(0, 300))
    reply = {requestId:request.requestId, error:"Workflow helper returned invalid data; see the shell log", errorType:"setup"}
}
```

The helper's own JSON still has to match `request.requestId`. Nothing that
arrives without a matching identity is applied as data.

### Polling.js `complete()`

After the identity and task checks (line 158), and before any use of
`reply.data`, turn a reply with the right identity but a wrong shape into a
controlled error:

```js
var okData = t.kind==="run" ? !!reply.data && typeof reply.data==="object" && !Array.isArray(reply.data)
    : Array.isArray(reply.data) && reply.data.every(function(x) { return x && typeof x==="object" });
if (!reply.errorType && !reply.error && !okData)
    reply={requestId:reply.requestId, error:"Workflow helper returned invalid data", errorType:"setup"};
```

This runs after the identity check, so a stale malformed reply is still
dropped without an error. The rate and cooldown fields of the replacement are
empty, so the cooldown block doesn't run for it. This check covers every
reply, whether it came from the helper or was built in QML.

## Alternatives rejected

- **Accept replies without a `requestId` in `complete()` as belonging to the
  in-flight request.** This breaks the stale-reply guard the intent requires.
  QML already knows the request for its own process, so it attaches the id
  there instead.
- **Reuse `errorType: "auth"` for setup failures.** It would give the same
  polling behaviour with zero new types, but it gives a missing python3 or gh
  the auth meaning. One `||` is cheaper than that confusion.
- **Keep retrying setup failures, only more slowly.** The user chose to stop
  (open question 1).
- **Show sanitised or truncated stderr in the panel.** Tracebacks and gh
  output can't be reliably cleaned of paths or tokens. A fixed message plus the
  log is safer and shorter.
- **Validate `data` in `receivePage()` (QML).** It can't be tested under node.
  `Polling.complete()` is the single place every reply passes through, and
  `tests/polling.cjs` already exercises it.
- **Run python3 through `sh -c` to get a real 127.** That adds an extra
  process and a quoting surface just to learn something QProcess already
  reports.
- **Rename `s.auth` to `s.stopped`.** It would churn tests and callers for a
  name. A `ponytail:` comment records the new meaning.
- **Apply the same treatment to the old modes.** They are out of scope and
  being removed (open question 3).

## Risks

- **Quickshell FailedToStart signalling.** The design assumes
  `runningChanged` fires when start fails. If a Quickshell version emits
  `exited` instead, the `exited` path handles it with the real code (row 2).
  If it emits neither, nothing gets worse than today, because the panel
  already hangs in that case. This is checked manually on the dev machine
  (Verification).
- **A transient crash stops polling.** An OOM kill or a one-off signal becomes
  row 2 and stops polling until `r`. That is acceptable: the message says what
  happened and one key recovers.
- **Version skew during an upgrade.** A new QML with an old actions.py can
  show row 7 until the next reopen. Both files ship together in the same flake
  output, so this only lasts for one open panel.
- **The meaning of `s.auth` widens.** No UI reads `polling.auth` today
  (checked with grep in ActionsPanel.qml). A future reader has the
  `ponytail:` comment.
- **Wording change for existing tests.** tests/model.cjs currently asserts
  that stderr is shown (`'python3: cannot open helper'`). That assertion is
  the leak being removed, so it is replaced, not kept.

All hosts that use the panel are affected the same way. There is no
per-host configuration.

## Verification

Each new case below fails on the current `main`.

**tests/model.cjs**

- `reply('', 2, 5)` parses to `{requestId:5, errorType:'setup',
  error:'Workflow helper failed (exit 2); see the shell log'}`.
- `reply('', 127, 5).error === 'python3 not found'`.
- The old stderr assertions (lines 25–26) are removed. A reply built from a
  helper that failed with a traceback on stderr never contains `Traceback`,
  because stderr is no longer an argument.
- `reply('{"repos":[]}', 0, 5)` still passes stdout through unchanged.

**tests/polling.cjs**

- A `setup` error on the in-flight request: `complete` returns true,
  `s.error` is the message, `next()` returns null. After `manual()`, `next()`
  returns a request again.
- `data: null`, `data: {}`, `data: [null]` for a `catalogue` or `summary`
  flight with the right id don't throw. Each is a `setup` error and stops
  polling.
- `run` with an object `data` still merges. `run` with `data: []` is a
  `setup` error.
- A malformed or `setup` reply with a stale `requestId`, or after
  close/reopen, returns false and leaves `s.auth` false.

**tests/test_actions.py**

- `read_page` with `request` patched to raise `FileNotFoundError` gives
  `errorType == "setup"` and `error == "Install gh (GitHub CLI)"`.
- End to end: `actions.py page '{"kind":"catalogue","requestId":3}'` with
  an empty `PATH` directory gives JSON with `requestId == 3` and
  `errorType == "setup"`. This mirrors `test_missing_gh_is_json_error`.
- `main` in page mode with `{"kind":"url","requestId":7}` exits 1 and gives
  `{"error":"Invalid page operation","errorType":"setup","requestId":7}`.
- `main` in page mode with `not-json` exits 1 and gives no `requestId`.
- `main` in summary mode with an invalid repository gives exactly
  `{"error": ...}`. The old modes are unchanged.

**Whole suite:** `nix flake check` passes. It runs the Python unittest
discovery, `node tests/model.cjs`, `node tests/polling.cjs` and
`tests/qml-smoke.py`.

**Manual runtime check on the dev machine:**

1. In a local checkout, point `requestProc.command[0]` at a name that
   doesn't exist. The panel shows `python3 not found`, the log shows one
   warning, and polling stops. After `r`, it makes one more attempt and then
   stops again.
2. Open the panel with `gh` removed from PATH. It shows
   `Install gh (GitHub CLI)` and stops.
3. Restore both, press `r`, and the data loads.
