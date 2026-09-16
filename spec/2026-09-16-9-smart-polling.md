---
status: approved
issue: 9
intent: intent/2026-09-16-9-smart-polling.md
---

# Spec: Prioritize selected repositories and running workflows

## Design

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
