---
status: approved
issue: 9
spec: spec/2026-09-16-9-smart-polling.md
---

# Plan: Prioritize selected repositories and running workflows

Replace independently timed polling with one serial, page-aware scheduler. Reuse gh authentication, Python stdlib, Quickshell and the existing stable row model. Prioritize selected data and known running workflows while reserving background discovery capacity. No new service, dependency, credentials, menus, bindings or machine configuration.

This plan is self-contained: the approved design, constraints and acceptance criteria are reproduced below. The specification remains in spec/; it is not replaced by this file. Implementation begins only after this plan is approved in its own commit.

## Steps

Execute these in order, checking each checkpoint before continuing. Cite the active step in progress updates. Keep implementation and any necessary plan corrections in the same commit; do not silently relax an approved acceptance criterion. A change to the approved design requires review.

1. **Capture the baseline and add the deterministic workload.**
   - Start from this task branch and confirm a clean working tree. Record the exact pre-implementation commit; the current installed release is 0.2.2, with main merge 91f6bde.
   - Read all callers of selection, scan, refresh, jobs, close/open and row rebuilding in ActionsPanel.qml, plus actions.py transport/pagination and ActionsModel.js merges. Read any newly applicable repository instructions before edits.
   - Run the existing Python, model and QML checks once. Capture current cold-discovery time, selected-data delay and 30-minute idle request counts using a fake clock and fixed responses, counting the six summary requests and every page rather than helper invocations.
   - Add tests/polling.cjs using the existing Node/vm/assert approach. Keep its baseline model small and tied to the pre-change timers; use identical workloads and response times for both implementations. Include the normal-load and overloaded workloads described below.
   - **Checkpoint:** existing checks pass, and the reproducible baseline reports request counts and timing without making live GitHub requests. If an unrelated baseline check fails, diagnose and document it before proceeding.

2. **Add one-page API operations in actions.py and tests/test_actions.py.**
   - Add a typed page operation for catalogue, activity, summary recent/status pages, jobs and one run. Construct only the approved github.com GET endpoints from validated resource arguments; avoid a generic arbitrary-URL interface.
   - Route one page through the shared API transport using gh api --include, preserving timeout, cancellation and valid error metadata. No --paginate, hidden retry loop or multiple status requests inside the page operation.
   - Return resource/request identity, HTTP status, body, validated next-page information and allowlisted retry/quota metadata. Keep the legacy whole-operation modes compatible for existing callers, but move live panel polling entirely to the page operation in step 4.
   - Test successful and failed HTTP envelopes, multiple header blocks, empty/malformed output, authentication versus permission versus rate-limit errors, next-page validation, resource validation and exactly one requested page per invocation. Reuse the current timeout/cancellation checks rather than introducing another framework.
   - **Checkpoint:** the helper tests pass; later-page errors remain distinguishable from a complete snapshot; no token or unrestricted response headers appear in output.

3. **Implement Polling.js and exercise it in tests/polling.cjs.**
   - Keep scheduling independent of Qt and row rendering. Pass time and normalized responses into the scheduler so deterministic tests require no real timers or network.
   - Represent resumable resource tasks by identity, due time, class and continuation; track one in-flight request, request-start history, the five-slot allocation, cooldowns and the current selection/open generation in one state object. Avoid separate queues or schedulers per endpoint family.
   - Implement every refresh target below, repository-level selection debounce, same-run navigation behavior, per-page fairness, task deduplication, priority changes, complete-snapshot freshness and bounded retries.
   - Separate server cooldowns from per-resource retry deadlines. Keep request-budget history/cooldowns through close/reopen, invalidate cancelled-generation work, and coalesce manual refresh without bypassing limits.
   - **Checkpoint:** deterministic tests meet normal-load freshness targets, reserve active/background slots under continuous interactive work, cap all requests including pagination/retries, and show the required before/after idle and cold-discovery improvements. If targets fail, fix scheduling before UI integration; report any necessary design revision rather than modifying test expectations to hide it.

4. **Integrate one worker and snapshot assembly in ActionsPanel.qml / ActionsModel.js.**
   - Replace the independent discovery/activity/summary/jobs Process and polling-timer decisions with one Process using the page operation and a scheduler wake-up timer. Preserve keepLoaded caching; remove superseded timer/backoff/cursor state once the scheduler owns it.
   - Feed explicit navigation, search-result selection, expansion, manual refresh and open/close into the scheduler. Moving within one repository/run must not reset its deadline; background sorting must not create a new user-selection event.
   - Associate every response with its original resource, task snapshot and open generation. Merge useful early history without evicting cached runs; publish complete activity/job snapshots only once pagination completes. Do not let a late page overwrite a newer snapshot or replace the current selection.
   - Reconcile disappeared running IDs using a run lookup, display awaiting-final-status honestly, fetch final jobs when relevant and invalidate completed-job cache on reruns. Preserve expanded completed rows while bounding unrelated history.
   - Retain Model.syncRows, keyed selection and viewport preservation. Reuse the existing header for refresh/stale/error/cooldown state and count repositories as checked only after complete successful activity information. Extend the existing status response only as needed to observe queue/in-flight/request timing in tests; do not add a telemetry service or secrets to logs.
   - **Checkpoint:** model regressions pass; partial/error responses do not remove cached data or falsely mark it fresh; stale/cancelled responses cannot affect the newly opened panel.

5. **Verify QML integration and the real popup before release.**
   - Update tests/qml-smoke.py to link Polling.js into its isolated shell. Add a deterministic fake-helper path in the temporary test host, preserving production defaults, to exercise asynchronous selection, paginated responses, cooldown and close/reopen without dependence on live workflow timing.
   - Run the complete relevant suite once after integration. Test rapid typing/navigation, expansion to jobs/steps, selected-run changes, normal polling and completion/rerun transitions. Verify only one helper runs and close cancels its gh child; keep the existing keyboard/search/viewport regressions.
   - Through MCP, launch an isolated candidate using the current session's Omarchy imports. Use keyboard input and screenshots to verify response timing and stable search/viewport during updates, plus a controlled completion transition. Then use read-only real gh data to confirm the API contract, recording measured timing and request counts without sensitive headers. Do not claim a live completion was observed if only the controlled fixture covered it.
   - Acquire and release MCP desktop control explicitly; respect any revocation. Avoid a full shell restart during development, and leave unrelated desktop settings alone.
   - **Checkpoint:** deterministic acceptance criteria and QML checks pass, and live screenshots/API responses confirm the candidate behaves correctly. Record any limits imposed by the real network or workload.

6. **Document, review, release and verify the installed plugin.**
   - Update README.md with the approved intervals, selection debounce, fairness, budget, cache/completion behavior, error cooldowns and practical limits. Document the new test command and actual measured before/after results. Bump manifest.json to 0.3.0 for this polling-engine change; keep the plugin ID, menu integration and shortcuts.
   - Review the final diff against this plan. Run git diff --check and any checks justified by final code changes; avoid repeating unrelated tests when only documentation changed.
   - Commit on feat/9-smart-polling and push that branch. Open a PR with Closes #9, links to intent/spec/plan, meaningful validation and timing evidence. Merge only after the required checks and final review pass, under the user's existing end-to-end delivery authorization once this plan is approved.
   - Verify the installed checkout is clean; preserve any user changes rather than overwriting them. Update it to the reviewed release. Use the running session's tree if a shell reload is necessary; do not hardcode a Nix store path or touch unrelated plugin/config files. Do not restart a locked session.
   - After any shell/plugin reload finishes, verify the installed popup through its normal menu/shortcut and MCP: selected data becomes prioritized, search/selection/viewport remain stable, helper concurrency is one, and closing stops work. Release desktop control when finished.
   - **Checkpoint:** source and installed version match the reviewed release, checks and runtime results are recorded, and the working tree is clean. If installation fails, use the rollback below and report the failed checkpoint honestly.

## Tests

Run from the repository root with the existing toolchain:

```sh
python3 -m unittest discover -s tests -v
node tests/model.cjs
node tests/polling.cjs
python3 tests/qml-smoke.py
git diff --check
```

Expected: all assertions pass, no plugin QML errors, deterministic before/after metrics satisfy the acceptance criteria below, and no whitespace errors. The QML check requires the graphical session and its OMARCHY_PATH. Do not install tools imperatively; if an environment tool is missing, inspect the applicable project-environment instructions first.

Use fixed fake HTTP durations (including one second for the normal-load acceptance workload) and report cold-start and warm-cache results separately. Record baseline/candidate API request counts, selection-to-first-request delay, summary completion delay and maximum warm-up-adjusted data ages. Include an overload case where freshness degrades while fairness and the ceiling still hold. Live network measurements are supporting evidence, not substitutes for deterministic checks.

## Rollback

- Record the source/installed commit before implementation/deployment. If the new release fails runtime verification, close this panel, cancel its helper and restore only this plugin to that recorded clean revision; reload the plugin through the current session shell if needed. Keep existing authentication, menus, shortcuts and unrelated plugins/configuration.
- No database migration, credential migration, system service or NixOS rebuild is involved. In-memory polling state is discarded on shell reload.
- Preserve any uncommitted installed changes before replacement. For published source, revert the polling implementation commits on a corrective branch/PR rather than rewriting shared history; retain the intent/spec/plan audit trail.
- Confirm the restored version opens, searches, expands workflows and stops polling on close. Report the unsuccessful release and restored version.

## Approved design and acceptance criteria


### Scope and existing behavior

Keep Quickshell, Python stdlib, gh authentication, the current theme and keyboard controls. Replace the independent polling decisions in ActionsPanel.qml with one request scheduler. Reuse ActionsModel.js row identity and incremental updates. No new service, database, dependency, credential handling or desktop configuration change.

Current activity scanning waits two seconds after each response. Moving selection restarts the jobs timer but does not immediately refresh the selected repository. actions.py runs() consumes at least six requests for a full summary, so budgeting helper launches would undercount traffic.

### Refresh policy

These intervals are freshness targets measured from the last successful complete response, not promises during congestion, network errors or server cooldowns.

| Data | When it becomes due |
| --- | --- |
| Newly selected repository | After selection stays on that repository for 250 ms, if its summary is missing or older than 60 seconds |
| Explicitly expanded repository | Immediately eligible for missing/stale summary; reuse an already queued or running refresh |
| Selected repository activity | Every 10 seconds while selected, unless an equivalent fresh full summary already covers it |
| Inspected unfinished run jobs/steps | Immediately if missing/stale, then every 5 seconds while that run is inspected and expanded |
| Other repositories with known running workflows | Every 15 seconds, oldest successful check first |
| Selected repository full summary | Every 60 seconds; include active statuses and the ten most recent runs |
| Unchecked repositories | First background pass, preserving existing pushed-descending catalogue order |
| Checked idle repositories | Due again after 10 minutes, oldest check first |
| Repository catalogue | Existing 5-minute reopen freshness rule, plus explicit Shift+R |
| Completed run jobs | One final fetch after completion, then reuse until explicit refresh or a changed run attempt/status invalidates the result |

Selecting a run, job or step refers to the same repository/run identity. Moving between its rows must not restart its refresh deadline. Changing a search query or moving rapidly between repositories coalesces selection work; only the final stable selection receives interactive priority. Background replies never count as user navigation.

### Scheduling and request budget

Use a small pure-JavaScript scheduler, kept separate from row rendering, with three work classes: interactive (current selection and explicit refresh), known active, and background (catalogue and unchecked/idle activity). It selects a single HTTP page at a time. A full summary and a paginated result are resumable tasks, not indivisible helper calls.

- Only one gh API request may be in flight for this panel.
- Start requests at least one second apart and allow no more than 60 requests in any rolling 60-second window. Count failures, retries and every requested page. These are plugin ceilings, not additional GitHub quota.
- Use a repeating allocation of three interactive slots, one active slot and one background slot. Empty classes lend their slots to due work. Advance allocation only when a request actually starts, including failed requests. This reserves progress for active and undiscovered repositories even under continuous navigation.
- Within a class, use the oldest due task. Requeue continuations with a new eligible timestamp after each page, so an old multi-page summary cannot repeatedly jump ahead of newly due jobs. A newly stable selection supersedes obsolete selection-only tasks. Use one task identity per endpoint, resource, status and page; selected/active overlaps share results rather than issuing duplicate requests.
- Treat one page as the scheduling unit so a many-page catalogue or summary cannot monopolize the worker. Yield between pages and status queries. Do not abort a healthy in-flight page merely because the cursor moved; keep its valid result in that resource’s cache, then choose the next request using current priorities.
- Manual r/Shift+R makes matching work due and coalesces repeated presses. It cannot bypass the global request budget or a server cooldown.
- Keep the budget, cooldown and cached results in the existing keep-loaded panel across close/reopen. A shell restart loses the local budget history; GitHub response headers remain authoritative. Do not persist credentials or introduce a state database.

### Helper contract and API responses

Extend actions.py with an explicit one-page operation used by the new scheduler. Typed resource arguments construct allowlisted github.com GET endpoints for repository discovery, activity, summary status/recent pages, jobs, and an individual run. Validate repository names, run IDs, page numbers and status values; do not accept arbitrary URLs from QML. Existing whole-operation modes may remain for compatibility and existing tests, but live polling must use the bounded page operation.

Use gh api --include without --paginate to expose response status and headers. Each helper invocation starts exactly one requested page; no automatic retries in the helper. Return a structured JSON envelope containing request identity, HTTP status, parsed body, next-page information and only the rate-limit/retry metadata needed by the scheduler. Never return authentication headers. Handle nonzero gh exits without discarding available HTTP metadata, and distinguish malformed/empty output from a valid API error. Parse headers and body separately, including intermediate header blocks if emitted by gh.

Follow pagination links only by validated page information for the same allowlisted resource. Do not treat a partial multi-page response as a complete snapshot or remove cached rows because a later page failed. Keep the existing 25-second per-request timeout and child cancellation. A single slow request can therefore delay higher-priority work by its remaining timeout; the UI must retain cached data rather than imply guaranteed real-time service.

Full summaries fetch recent history first so useful information can arrive early, then fetch the existing five active statuses. Merge additions/updates as pages arrive, but only reconcile removals after a complete successful snapshot. Discard obsolete continuation work when its resource is no longer needed; keep already fetched valid cache data. Request IDs and a panel-open generation distinguish valid replies from cancelled sessions.

### Completion and errors

An in-progress run disappearing from a complete activity snapshot is not sufficient evidence of success. Stop counting it as known running, retain its last row as awaiting final status, and queue one individual-run lookup. That lookup establishes completion, cancellation, or another nonterminal state. Fetch final jobs for an inspected completed run, then stop periodic job polling. Preserve the run while its details are expanded; bound other cached completed history to the existing recent-history behavior.

Honor Retry-After and exhausted X-RateLimit-Remaining/X-RateLimit-Reset headers across every work class. If both provide deadlines, use the later one. For a secondary rate limit without a supplied deadline, pause for at least 60 seconds and increase repeated waits exponentially, capped at 15 minutes; show the pause and its retry time. If remaining quota reaches zero on a successful response, retain the result and pause subsequent requests until reset. An unqualified permission 403 is not automatically a rate-limit response; classify from headers and the API error body.

Network/server failures back off the affected task (5, 10, 20, 40 seconds, capped at 5 minutes) without freezing unrelated work. Repository permission/404 failures retain a per-repository unavailable state and leave automatic activity scanning until catalogue refresh or explicit refresh requests another attempt. Authentication failure pauses all polling until explicit retry/reopen. All retries still obey shared limits. A run/job 404 affects that resource, not the entire repository.

### User-visible behavior and lifecycle

Keep the current flat layout, icons, fonts, keys, running-first ranking, search query, expansion, selected row identity and viewport preservation. Reuse the header/status area for refreshing, unchecked, stale/error and global cooldown information; no new controls.

On close, cancel the helper and its gh child, stop scheduler timers and invalidate partial responses from that open generation. On reopen, render cached data immediately, then prioritize stale selected/inspected data. Successful older requests may update their own resource cache but must never replace the current selection. Only complete activity snapshots advance a repository’s checked timestamp/count; failed or partial requests must not imply fresh knowledge.

## Alternatives rejected

- Shorten every existing timer: duplicates work, undercounts multi-request summaries and allows priority inversion during pagination.
- Add parallel scanning workers: raises API pressure and complicates ordering; GitHub recommends serial requests to reduce secondary rate-limit exposure.
- Poll only selected or already active repositories: cannot discover new activity elsewhere.
- Always fetch full summaries: six or more requests are unnecessary for a lightweight activity check.
- MCP, webhooks, a persistent service, database or token extraction: unnecessary for an on-demand desktop panel and outside the approved scope.
- ETag caching in this change: useful later for unchanged response bodies, but it does not remove polling requests or solve selection priority. Reuse the existing in-memory data first.

## Risks

More requests may occur during initial discovery than with the current two-second-after-response delay, but the single worker and 60/minute ceiling bound that increase. Other gh clients share account quota, so this plugin cannot guarantee account-wide headroom. Large numbers of active repositories, many pages, slow requests and GitHub cooldowns can exceed freshness targets; fairness must remain intact rather than spawning extra workers.

Changing summary assembly risks stale overwrites or premature removal. Preserve complete-snapshot semantics, request identities and the existing stable list model. Run retries can reuse a run ID: a changed run_attempt or transition back to an unfinished status invalidates completed-job caching.

## Verification

Use a fake monotonic clock and fake page responses for deterministic scheduler tests. Include 137 repositories, up to four with one-page activity results, one inspected run with one page of jobs, and selected summaries with six one-page requests. Assume each fake request completes within one second and no API errors/cooldown for the normal-load targets:

- After a stable selection change, its first missing/stale request starts within 5 seconds; recent results arrive before the complete summary. The selected full summary completes within 20 seconds under this workload.
- Inspected unfinished jobs remain no more than 10 seconds old; selected activity no more than 15 seconds old; other known-active activity no more than 25 seconds old after warm-up.
- Under continuously due work in all classes, background work receives at least one of every five request starts; active work likewise receives its reserved slot. Repeated cursor changes cannot starve either class.
- Every requested page counts against the 60-per-rolling-minute ceiling, only one request is in flight, and start spacing stays at least one second. Overload stretches freshness instead of violating the ceiling.
- A 30-minute idle workload reduces API request count versus the current implementation. A cold catalogue pass under low interactive load completes faster than the existing two-second-after-response scan with the same fake response times. Record actual before/after figures rather than asserting savings from timer values alone.

Also cover rapid selection/search changes, deduplication, large paginated summaries, partial failures, late replies after close/reopen, completion lookup and final job fetch, rerun invalidation, quota exhaustion on successful responses, Retry-After/reset precedence, secondary-rate-limit fallback, permission errors, and manual refresh during cooldown. Keep tests within the existing Node and Python tooling; no new test framework.

Run existing model and QML lifecycle/navigation checks. After implementation approval, verify through MCP that selection/expansion is responsive, background updates preserve the viewport/search, completing runs show final status, and closing stops requests. Record workload and request timing without tokens or sensitive headers. Code and installed-plugin verification are separate from this specification review.

## References

- [GitHub REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
- [GitHub CLI API options](https://cli.github.com/manual/gh_api)

Reviewed 2026-09-16: serial requests, retry/reset handling, and gh response-header support inform this design. Proposed intervals and the plugin request ceiling are our design choices, not GitHub guarantees.

## Implementation record

- Baseline recorded from 0.2.2 behavior: 902 requested pages over 30 idle minutes and 411 seconds for the initial activity pass with 137 repositories and one-second responses.
- Background activity enqueues its next oldest candidate on demand; pre-enqueuing every unchecked repository delayed catalogue continuation pages. Summary order is recent history, in-progress, then the other active states, so the selected activity deadline is maintained. Both choices preserve the approved per-page fairness and recent-first design.
- Candidate simulation: 713 idle requests, 168-second initial pass, 9-second selected summary; maximum warmed data ages 8.75/11.75/20.75 seconds for inspected jobs, selected activity and other active activity. Overload retains request limits and background fairness.
- Real MCP candidate: 137 repositories discovered, search and selection stable through running workflow → jobs → 26 reported steps. Closing left no helper in flight. Completion is verified with a clearly labelled simulated workflow, separately from real GitHub monitoring.
- Final validation includes 15 Python checks, model checks, deterministic scheduler scenarios and an asynchronous QML fake-API test. Paginated workflow/job snapshots deduplicate overlapping IDs. The labelled MCP completion fixture reached success and retained its final jobs timestamp while later summary polling continued.
