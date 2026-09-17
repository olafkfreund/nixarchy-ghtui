---
status: approved
issue: 11
intent: intent/2026-09-17-11-apps-menu-default.md
---

# Spec: Register GitHub Actions under Apps when enabled

## Design

Use the existing enabled-panel lifecycle. The installed Omarchy shell's
`shell.qml` computes panel entries from enabled plugins and immediately loads
entries with `keepLoaded: true`. This plugin already declares that flag in
`manifest.json`. The inspected `omarchy-plugin-add` delegates `--enable` to
`omarchy-plugin-enable`, which calls the shell's `enablePlugin` method; neither
command executes an arbitrary plugin installation script.

Extend `ActionsPanel.qml` to run one short-lived registration process when the
component loads, including initial enablement and subsequent session starts.
Reuse `menu.py` with an explicit registration mode that runs before its existing
desktop-session discovery. Keep launcher, keys, and toggle modes compatible.
No timers, background service, host patch, or new dependency are required.
Installation with `--enable` registers automatically. Installing disabled code
does not execute it; registration occurs when it is enabled in a running shell.

Make `menu.example.json` the canonical defaults: `apps.github-actions` for the
launcher and the existing `learn.github-actions-keybindings` entry. Registration
targets the same user menu path consumed by the shell,
`~/.config/omarchy/extensions/omarchy-menu.jsonc`.

Registration must:

- Create a missing extension file and its parent directory.
- Add missing default entries, preserving existing Apps and Learn entry fields.
- Move the legacy `github-actions` or `system.github-actions` entry to
  `apps.github-actions`, retaining customized fields. If both legacy locations
  exist, prefer System over root; an existing Apps entry takes precedence over
  either. Remove only legacy entries whose launcher action identifies this
  plugin. An unrelated action occupying a legacy ID remains untouched.
- Leave unrelated entries, comments, formatting, and string contents unchanged.
  Validate JSONC structure before targeted edits; reject ambiguous duplicate
  keys or malformed input rather than guessing or replacing the document.
- Be idempotent: a second registration with no necessary changes does not write.
- Refuse symlink-managed files and unwritable destinations, with a useful error
  explaining that the menu example must be declared by the host's configuration.
  Never replace a managed symlink or write into the Nix store.
- Write through a temporary sibling and atomic replacement, preserve existing
  permissions, and abort if the original file changed during preparation.

Registration failure is reported through the process result/shell log and must
not prevent the workflow panel from loading or alter the original menu. Menu
changes hot-reload using Omarchy's existing file watcher. Do not bind keys or
change polling as part of registration.

Update `README.md` to describe Apps placement, automatic registration at
enablement, managed-file setup, and removal of the registered entries. Bump the
plugin patch version to 0.3.1. Existing disabled checkouts receive the behavior
when updated and enabled; this release does not remotely update other hosts.

## Alternatives rejected

- Change only the menu example: still requires manual setup on every host.
- Add an install script without a caller: the inspected plugin CLI does not run it.
- Add a service or patch the host: the existing loaded-panel lifecycle suffices.
- Rewrite the entire JSONC document as JSON: loses comments and formatting.
- Register only when opening the popup: the menu is needed to discover it first.

## Risks

JSONC editing could corrupt user configuration if strings or comments are treated
as structural syntax. Cover those cases explicitly and fail without writing on
invalid or ambiguous input. Simultaneous manual edits must not be overwritten.
Hosts with declaratively managed menu files require their own declared entries;
automatic mutation cannot safely override that ownership.

## Verification

Extend the existing Python menu tests with temporary homes/files for fresh setup,
root/System migration, existing Apps precedence, repeated registration, unrelated
custom entries, comments, escaped strings, trailing commas, malformed input,
duplicate keys, managed symlinks, and write failures. Confirm only intended spans
change and failed registration leaves original bytes intact.

Extend the QML smoke check to isolate HOME/menu writes and verify registration
occurs at component load while the panel stays closed. Confirm panel behavior
survives registration failure. Run existing Python, model, scheduler, and QML
checks plus whitespace and manifest validation. Verify Apps placement in the
installed menu after release, retaining the Learn entry and launcher behavior.
