---
status: draft
issue: 24
spec: spec/2026-09-24-24-helper-errors.md
---

# Plan: A failing helper shows its real cause

## Approved decisions

- **Scope:** only the `page` path changes: `actions.py` (`read_page`, `main`
  in page mode), `ActionsModel.js` (`reply`), `ActionsPanel.qml`
  (`requestProc`, `receivePage`, new `failedToStart`) and `Polling.js`
  (`complete`). The `summary`, `jobs`, `repositories` and `activity` modes
  print exactly what they print today; they are being removed separately. No
  new files, dependencies or GitHub requests.
- **One new errorType, `setup`:** it means the local install or the helper
  is broken. Polling treats it exactly like `auth`: `complete()` sets
  `s.auth=true`, `next()` then returns null, and `Polling.manual()` (`r`,
  Shift+R) or `Polling.open()` (reopen) clears it. `s.auth` isn't renamed; a
  `ponytail:` comment records that it now means "stopped until manual
  refresh". The failed task goes through the existing non-permission branch
  (`t.failures++`, backoff `due`), so after `r` it runs once more and stops
  again if the cause is still there.
- **Fixed messages only:** raw stderr, tracebacks and gh output never reach
  the panel. Everything stderr contains goes to the Quickshell log through
  `console.warn`.
- **Failure table:**

| # | Failure | Detected in | Panel message | errorType | Polling |
|---|---------|-------------|---------------|-----------|---------|
| 1 | python3 not on PATH (Quickshell failed start, or empty stdout with exit 127) | ActionsPanel.qml `failedToStart` → `Model.reply` | `python3 not found` | `setup` | stops until `r` or reopen |
| 2 | Helper printed nothing and exited N (missing actions.py, argparse error, uncaught traceback, killed) | `Model.reply` | `Workflow helper failed (exit N); see the shell log` | `setup` | stops until `r` or reopen |
| 3 | `gh` not on PATH (`FileNotFoundError` from `Popen`) | `read_page()` | `Install gh (GitHub CLI)` | `setup` | stops until `r` or reopen |
| 4 | gh signed out, or HTTP 401 | `read_page()` (unchanged) | `Authenticate with gh auth login` (unchanged) | `auth` | stops (unchanged) |
| 5 | `main()` catches `ValueError` or `KeyError` from a request it could parse | `main()` with `requestId` | `str(exc)`, a fixed actions.py string, e.g. `Invalid page operation` | `setup` | stops until `r` or reopen |
| 6 | `main()` catches `DeadlineExceeded`, `TimeoutExpired` or `OSError` for a parseable request | `main()` with `requestId` | `GitHub request timed out or returned invalid data` (unchanged) | `network` | backoff retry (unchanged) |
| 7 | Helper JSON has no `requestId` or the wrong one | `receivePage()` | `Workflow helper returned invalid data; see the shell log` | `setup` | stops until `r` or reopen |
| 8 | `requestId` is right and there is no error, but `data` is the wrong shape (not an array of objects, or not a plain object for `run`) | `Polling.complete()` | `Workflow helper returned invalid data` | `setup` | stops until `r` or reopen |
| 9 | Rate limit, permission, network, bad GitHub body | `read_page()` (unchanged) | unchanged | `rate` / `permission` / `network` | unchanged |
| 10 | Helper cancelled by close (SIGTERM, exit 15) | `Model.reply` gives row 2's message | — | — | rejected by `generation` (unchanged) |

- **`Model.reply(stdout, code, requestId)`:** the stderr parameter is removed.
  If stdout is non-empty, it is returned unchanged. Otherwise the function
  returns JSON `{requestId, errorType:"setup", error}`, where `error` is row
  1's message for exit code 127 and row 2's message for any other code.
- **Identity:** QML attaches `requestId` only to replies it builds itself for
  its own process that just finished (`root.requestInfo.requestId`, set in
  `pump()` before `running = true`; one helper at a time through
  `workerBusy`). JSON printed by the helper still has to carry the matching
  `requestId`, or `receivePage()` replaces it (row 7). Stale replies are
  still dropped by `flight.generation` and `requestId` in `complete()`.
- **stderr:** `requestProc.onExited` calls `console.warn` with the exit code
  and trimmed stderr whenever stderr is non-empty. `receivePage()` logs up to
  300 characters of a rejected reply. `failedToStart` logs one line.
- **`main()` in page mode:** it keeps the parsed task. Its error reply adds
  `errorType` (`network` for `DeadlineExceeded`, `TimeoutExpired` and
  `OSError`, otherwise `setup`). It also adds `requestId` when
  `task["requestId"]` is an `int` greater than 0, which is the same check
  `page_endpoint()` uses. If the request JSON can't be parsed, there is no
  `requestId`, and row 7 handles it. The other modes don't change.
- **`FileNotFoundError`:** `read_page()` handles it before the generic
  `(OSError, …)` handler, because it is a subclass of `OSError`. It becomes
  row 3. `PermissionError` stays `network`.
- **Data-shape check:** in `Polling.complete()`, after the identity and task
  checks and before anything reads `reply.data`. For `run`, the data must be
  a non-null, non-array object. For every other kind, it must be an array
  whose elements are all non-null objects. If a reply has no error and fails
  this check, it becomes row 8. A stale malformed reply is still dropped
  silently, because the identity check runs first.
- **Failed-start fallback:** this is the approved design with one change,
  justified by the signal-order finding below. The approved spec gated the
  fallback on `Qt.callLater` and `workerBusy`. The plan gates it on "the
  process never emitted `started`" instead, which doesn't depend on
  event-loop timing:

```qml
property bool helperStarted: false            // reset in pump() before running = true
onStarted: root.helperStarted = true
// Quickshell 0.3.1: a failed start emits neither started nor exited, only running=false.
onRunningChanged: if (!running && root.workerBusy && !root.helperStarted) root.failedToStart()
```

```js
function failedToStart() {
    console.warn("GitHub Actions helper: python3 failed to start")
    receivePage(Model.reply("", 127, requestInfo.requestId), requestInfo)
    workerBusy = false
}
```

### Signal order finding (Quickshell 0.3.1, recorded 2026-09-24)

I ran two throwaway QML files with the installed `quickshell -p` (Quickshell
0.3.1, Nixpkgs):

- `/tmp/claude-1000/qs-signal-order/shell.qml`: a binary that doesn't exist,
  and `sh -c "echo out; exit 3"`, each handler also logging a `Qt.callLater`.
- `/tmp/claude-1000/qs-signal-order/reuse.qml`: one `Process` reused in turn
  for a missing binary, another missing binary, `true`, and `sleep 5` that
  is then cancelled with `running = false`. This matches how `requestProc` is
  reused and closed.

```
ORDER 1 missing set running=true
ORDER 2 missing after assignment running=false
WARN: Process failed to start, likely because the binary could not be found. Command: QList("definitely-not-a-binary-xyz")
ORDER 4 missing runningChanged running=false
ORDER 5 missing callLater after runningChanged
   (no "started", no "exited" for the missing binary)
ORDER 6 normal runningChanged running=true
ORDER 7 normal started
ORDER 9 normal stdout streamFinished
ORDER 10 normal exited code=3 status=0 stdout=out
ORDER 11 normal runningChanged running=false

reuse.qml:
ORDER 1 step1 set running=true no-such-binary-1
WARN Process failed to start ... no-such-binary-1
ORDER 2 step1 runningChanged running=false
ORDER 3 step2 set running=true no-such-binary-2
WARN Process failed to start ... no-such-binary-2
ORDER 4 step2 runningChanged running=false
ORDER 5 step3 set running=true true
ORDER 6 step3 runningChanged running=true
ORDER 7 step3 started
ORDER 8 step3 exited code=0
ORDER 9 step3 runningChanged running=false
ORDER 10 step4 set running=true sleep
ORDER 11 step4 runningChanged running=true
ORDER 12 step4 started
ORDER 13 step4 cancel running=false
ORDER 14 step4 exited code=15
ORDER 15 step4 runningChanged running=false
```

- **Failed start:** `exited` never fires, and neither does `started` or
  `runningChanged(true)`. `runningChanged(false)` fires once, in a later
  event-loop turn than the assignment, after Quickshell's own warning. This
  happens again every time the same `Process` is reused. Today this leaves
  `workerBusy = true` forever, so polling freezes with no message.
- **Normal exit and cancel:** `runningChanged(true)` → `started` →
  (stdout finished) → `exited` → `runningChanged(false)`. `exited` always
  comes before `running=false`.

Of the lead's two cases, neither holds exactly. `exited` does not fire on a
failed start, so the fallback stays. `exited` does not arrive after
`running=false` either, but I don't rely on that ordering. Instead the gate
is `!helperStarted`, since a failed start is the only path that never emits
`started`. So the fallback can't fire for a process that ran, whatever the
event-loop order. `Qt.callLater` isn't needed.

## Steps

Each step is one commit. The tests come first in the same commit, and they
must fail before the code change, for the stated reason.

1. `tests/test_actions.py`: add these tests to `PageTest`:
   - `test_missing_gh_is_setup_error`: `request` patched to raise
     `FileNotFoundError`, so `errorType == "setup"` and
     `error == "Install gh (GitHub CLI)"`.
   - `test_page_missing_gh_end_to_end`: runs `actions.py page
     '{"kind":"catalogue","requestId":3}'` with `PATH` set to an empty
     temporary directory (the same pattern as
     `test_missing_gh_is_json_error`). It expects JSON with `requestId == 3`
     and `errorType == "setup"`.

   → verify that both fail today (`errorType` is `network`).
2. `actions.py` `read_page()`: add `except FileNotFoundError` before the
   generic handler, with a `ponytail:` comment. → verify that step 1's tests
   pass and all 23 existing tests still pass.
3. `tests/test_actions.py`: add these tests, calling `main()` with
   `sys.argv` patched and stdout captured:
   - `test_page_error_echoes_request_id`: `page '{"kind":"url","requestId":7}'`
     returns 1 and prints
     `{"error":"Invalid page operation","errorType":"setup","requestId":7}`.
   - `test_page_unparseable_request_has_no_id`: `page not-json` returns 1,
     and the output has no `requestId`.
   - `test_old_mode_error_unchanged`: `jobs a/b x` returns 1 and prints
     exactly `{"error": "jobs requires owner/repo and numeric run ID"}`.

   → verify that the first two fail today and the third passes, which guards
   against regressions.
4. `actions.py` `main()`: add `task = None`, keep the parsed task in page
   mode, and build the error dict with `errorType` and `requestId` in page
   mode only. → verify that step 3's tests and the whole Python suite pass.
5. `tests/model.cjs`: replace lines 24–26 with these assertions:
   - `reply('{"repos":[]}', 0, 5)` returns its input unchanged.
   - `JSON.parse(reply('', 2, 5))` deep-equals
     `{requestId:5, errorType:'setup', error:'Workflow helper failed (exit 2); see the shell log'}`.
   - `JSON.parse(reply('', 127, 5)).error === 'python3 not found'`.

   → verify that it fails today, because the old signature treats `2` as
   stderr.
6. `ActionsModel.js` `reply()`: change it to the new signature and body.
   `ActionsPanel.qml` `requestProc.onExited`: log stderr with `console.warn`,
   then call `Model.reply(pageOutput.text, code, root.requestInfo.requestId)`.
   → verify that `node tests/model.cjs` passes and `grep -n "Model.reply"
   ActionsPanel.qml` shows only the new call.
7. `tests/polling.cjs`: add these cases:
   - A `setup` error on the in-flight request: `complete` returns true,
     `s.error` equals the message, and `next()` returns null. After
     `manual()`, `next()` returns a request.
   - `data: null`, `{}` and `[null]` for a `catalogue` flight and a `summary`
     flight with the right id: none of them throw, each sets `s.error` to
     `'Workflow helper returned invalid data'`, and each sets `s.auth`.
   - `run` with object `data` still merges, and `run` with `data: []` is a
     `setup` error.
   - A malformed or `setup` reply with a stale `requestId`, or after
     `close`/`open`, returns false and leaves `s.auth` false.

   → verify that it fails today (`setup` doesn't stop; `data: null` throws).
8. `Polling.js` `complete()`: set `s.auth` for `auth` or `setup`, with the
   `ponytail:` comment. Add the data-shape check after line 158. → verify
   that `node tests/polling.cjs` passes, including the existing
   baseline/fairness assertions.
9. `ActionsPanel.qml` `receivePage()`: the catch branch logs the rejected
   text (up to 300 characters) with `console.warn` and uses row 7's message
   with `errorType:"setup"`. → verify with `tests/qml-smoke.py`: exit 0, with
   the existing fake helper still loading data.
10. `ActionsPanel.qml`: add the `helperStarted` property, reset in `pump()`
    before `running = true`. Add `onStarted`, the gated `onRunningChanged`
    and `failedToStart()` as shown above. → verify that `tests/qml-smoke.py`
    passes, then do manual check A below.
11. Run the full suite and `nix flake check`. → verify that everything is
    green, then do manual checks B and C.

## Tests

Run from the worktree root:

```sh
python3 -m unittest discover -s tests -p "test_*.py"   # OK; 23 tests before, 23 + 5 new after
node tests/model.cjs                                    # exit 0, "Model: … passed"
node tests/polling.cjs                                  # exit 0, all "Polling: …" lines
python3 tests/qml-smoke.py                              # exit 0 (needs OMARCHY_PATH, set in the session)
nix flake check                                         # green; runs all of the above in the sandbox
```

These were recorded on this branch before any change: 23 Python tests OK,
and model and polling both exit 0.

Manual runtime checks on the dev machine, using a local checkout loaded by
the shell:

- **A. python3 missing:** temporarily set `requestProc.command[0]` in
  `pump()` to `no-such-python3`. Open the panel. It shows
  `python3 not found`, the log has Quickshell's "failed to start" warning
  plus one helper line, and polling stops (`status()` IPC shows the request
  count isn't increasing). Press `r`: exactly one more attempt, then it
  stops. Revert the edit.
- **B. gh missing:** start the shell with a `PATH` that has no `gh`. The
  panel shows `Install gh (GitHub CLI)` and stops.
- **C. Recovery:** restore the normal environment and press `r`. Data loads
  and the error line clears.

## Rollback

- Before merge: don't merge the PR, or `git revert` the individual step
  commits. Each step is self-contained with its tests.
- After merge: `git revert` the merge commit. There are no data, config or
  state migrations. The panel keeps no persisted state, so the old behaviour
  comes back at the next shell reload.
- The throwaway QML under `/tmp/claude-1000/qs-signal-order/` isn't part of
  the repository and can be deleted at any time.
