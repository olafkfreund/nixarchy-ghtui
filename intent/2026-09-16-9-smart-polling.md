---
status: approved
issue: 9
author: olafkfreund
---

# Intent: Prioritize selected repositories and running workflows

## Problem

The panel discovers all accessible repositories, but freshness does not consistently follow what the user is inspecting. Moving selection does not immediately request the selected repository’s summary. Activity checks wait two seconds after each preceding request, and known running repositories only receive occasional priority once their data is at least thirty seconds old. Scanning a large catalogue can therefore take several minutes.

The current summary helper makes at least six API calls per repository (five active status queries and recent history). Job refresh timing restarts during navigation. Independently shortening these timers could increase API traffic or defer important updates while the user moves through rows.

These observations come from ActionsPanel.qml (move, scan, refresh, fetchJobs and timers) and actions.py (runs, activity and api).

## Proposed outcome

- Selecting or expanding a repository makes stale data for that repository a priority; inspecting a run similarly prioritizes its jobs and steps. Cached data stays usable while fresh data arrives.
- Known running workflows receive timely checks, including their transition to completion. Priority follows the current selection rather than an obsolete selection after rapid navigation.
- Other accessible repositories continue to receive checks, so new running workflows outside the selected repository are eventually discovered. A large active set cannot indefinitely starve this discovery.
- Idle or completed data causes less unnecessary traffic. Selection, active-workflow checks, repository discovery and manual refresh share bounded API usage and honor rate-limit cooldowns.
- Search text, selected identity, expansion and viewport remain stable during updates; running repositories retain their existing ranking behavior.
- The spec sets measurable freshness targets under normal network conditions and a defined workload. Verification compares request counts and selected/active update latency against the current implementation, including a catalogue of at least 137 repositories.
- Closing the panel cancels work and prevents further polling. Reopening shows cached results promptly and prioritizes stale data that matters now.

## Affected users and systems

Users of nixarchy-ghtui; the existing Quickshell panel and Python helper; GitHub API usage under the user's existing gh authentication. No change to other Omarchy plugins, desktop shortcuts, menus or machine configuration is requested.

## Constraints

- Planning only at this stage. Do not edit or deploy runtime code until the planning artifacts are approved.
- Keep direct GitHub API access through gh and its existing authentication. No MCP dependency, new credentials, background service or webhook infrastructure.
- Preserve the minimal themed keyboard interface, stable list updates, read-only access, timeout handling and cancellation.
- Count actual API requests, including pagination and multi-request summaries; helper invocation counts alone are not a sufficient budget measure.
- Avoid duplicate work across selected and active priorities, do not let manual refresh evade server-imposed cooldowns, and retain usable cached data on errors.
- Polling cannot guarantee immediate discovery across every repository. Define attainable freshness and fairness targets without promising an end-to-end latency the network cannot guarantee.
- Keep verification small: deterministic scheduler/request-budget checks, existing lifecycle/navigation regressions, and a focused MCP desktop test after implementation approval.

## Open questions

None blocking review of the outcome. The spec must propose exact freshness targets, fairness rules, request limits, selection debounce behavior and completion refresh behavior, with their traffic tradeoffs. These are design decisions to review at the next stage, not implementation commitments in this intent.
