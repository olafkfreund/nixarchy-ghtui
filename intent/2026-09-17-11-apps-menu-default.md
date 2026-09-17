---
status: draft
issue: 11
author: olafkfreund
---

# Intent: Put GitHub Actions under Apps by default

## Problem

The plugin documents manual menu setup and its example places GitHub Actions at
the root. Moving one host's entry does not establish the requested default for
other hosts. System is also the wrong location for this application.

## Proposed outcome

Installing or enabling the plugin makes Apps → GitHub Actions available on every
host without manual menu editing. Repeated installation or enablement creates no
duplicates. Existing root or System launcher entries migrate to Apps.

## Affected users and systems

New and existing users of the GitHub Actions Omarchy plugin, its installation and
enablement integration, menu examples, and setup documentation. This host's user
menu already places the launcher under Apps.

## Constraints

- Preserve unrelated menu entries and user customizations.
- Preserve the launcher behavior, keyboard shortcuts, and Learn keybindings entry.
- Work with supported Omarchy plugin lifecycle capabilities; do not assume hooks
  exist without checking the actual contract.
- Respect declaratively managed files and never write into the Nix store.
- No new service or dependency solely for menu placement.
- Verify fresh setup, repeated enablement, and migration from both old locations.

## Open questions

None for problem framing. Confirm the supported installation/enablement mechanism
during specification work and identify any host integration needed to deliver the
automatic behavior.
