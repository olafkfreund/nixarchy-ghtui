---
status: approved
issue: 1
author: olafkfreund
---
# Intent: GitHub Actions popup

## Problem
Following workflows across GitHub repositories requires switching browser pages.

## Proposed outcome
A keyboard-operated Omarchy popup shows repositories, workflow runs, jobs and steps, following the installed Omarchy theme and UI. Start with olafkfreund/nixarchy.

## Affected users and systems
This desktop, omarchy-shell, GitHub API and this independent plugin repository.

## Constraints
Flat themed design, icons, no buttons. Reuse gh authentication. Read-only monitoring. No secrets in source. No changes to the Nix store.

## Open questions
None blocking implementation. Additional repositories are configurable.

## Authorization
User confirmed the separate repository, screenshot direction and Omarchy theme requirement, then instructed: “start this and run it all the way to the end. review the plan and implement this”. This later instruction authorizes proceeding through the stages without the earlier per-stage pauses; no separate approvals are claimed.
