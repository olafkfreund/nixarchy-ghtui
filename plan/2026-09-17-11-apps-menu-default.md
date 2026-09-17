---
status: draft
issue: 11
spec: spec/2026-09-17-11-apps-menu-default.md
---

# Plan: Register GitHub Actions under Apps when enabled

## Approved decisions

Use the existing enabled-panel lifecycle, not a new service, dependency, timer,
host patch, or unsupported installation hook. The shell loads enabled panels
with `keepLoaded: true`, already declared by this plugin. Installation using
`omarchy plugin add ... --enable`, later enablement, and subsequent session starts
therefore load `ActionsPanel.qml` and run one short-lived registration process.
Installing disabled code does not execute registration; a running shell must
enable it. This release does not remotely update other hosts.

Reuse `menu.py` with a registration mode handled before desktop-session
discovery. Preserve existing launch, keys, and toggle modes. Keep polling and
keyboard bindings unchanged. Use `menu.example.json` as the canonical defaults:
`apps.github-actions` and `learn.github-actions-keybindings`.

Target `~/.config/omarchy/extensions/omarchy-menu.jsonc`, the path read by the
shell. Create missing parents/file and add missing default entries. Preserve
existing Apps and Learn fields. Migrate plugin-owned `github-actions` and
`system.github-actions` entries, preserving customized fields. Prefer an existing
Apps entry, then System, then root. Remove legacy entries only when their action
identifies this plugin; preserve unrelated actions occupying a legacy ID.

Preserve unrelated entries, comments, formatting, and string contents through
targeted edits. Validate JSONC before editing and reject malformed input or
ambiguous duplicate keys. Registration must be idempotent without rewriting an
unchanged file. Refuse symlink-managed files and unwritable destinations with
guidance to declare the menu example in the host configuration; do not replace
managed symlinks or write into the Nix store. Preserve permissions, use a temporary
sibling and atomic replacement, and abort if the original changes during
preparation. Failures must leave original bytes intact, report a useful process
error in the shell log, and never prevent panel loading. Use the shell's existing
menu file watcher for hot reload.

Document automatic enablement registration, Apps placement, managed-file setup,
and removal. Release as 0.3.1. A documentation-only example change, an uncalled
installer, whole-document JSON rewriting, and registration only on popup opening
do not meet the approved requirements.

## Steps

1. **Establish the baseline.** Check branch/worktree and any applicable repository
   instructions. Record source and installed revisions and whether the installed
   checkout is clean. Read `menu.py`, `menu.example.json`, the panel's completion
   hook and all menu helper callers, plus the existing Python/QML tests. Run the
   existing checks below before edits. Confirm installed shell enablement loads
   `keepLoaded` panels. → Verify baseline checks pass or explain any failure
   before proceeding; preserve user changes in either checkout.

2. **Implement and check registration.** Change the example launcher ID to
   `apps.github-actions`. Extend `menu.py` with explicit registration dispatch and
   the JSONC-preserving migration/write behavior above, using Python stdlib and
   existing repository patterns. Validate the resulting document before writing.
   Extend `tests/test_menu.py` with temporary files covering fresh creation,
   root/System migration, both legacy entries, existing Apps precedence,
   customized fields, unrelated actions/entries, comments, escaped strings,
   trailing commas, malformed input, duplicate keys, managed symlinks, write
   failures, concurrent modification, and idempotence. → Verify intended entries
   are present exactly once, only intended text changes, unchanged input is not
   rewritten, and failure paths preserve original bytes. Existing launcher tests
   must continue passing.

3. **Wire the existing lifecycle.** In `ActionsPanel.qml`, start registration
   once at component load, retaining the current row rebuild. Use the established
   relative helper-path pattern and a separate short-lived `Process`; collect its
   failure result for logging without affecting the API worker or panel opening.
   Update `tests/qml-smoke.py` to include the real menu helper/example and isolate
   HOME/menu files in its temporary test environment, preserving required display
   and runtime environment. Exercise successful registration while closed and a
   deliberate registration failure; retain navigation/polling checks. → Verify
   automatic registration precedes popup use, failure leaves the panel usable,
   and no real user menu is written by tests.

4. **Document and validate the release.** Update `README.md` for automatic setup
   and Apps placement, the managed-file exception, update/enable behavior, and
   removal of the canonical entries. Set `manifest.json` to 0.3.1. Run the full
   relevant suite and manifest validation below. Review the diff against every
   approved requirement, especially preservation and lifecycle behavior. Record
   actual results in this plan. → Verify all checks pass; do not claim all hosts
   have been updated or that disabled installations execute registration.

5. **Publish and verify installation.** Commit on `feat/11-apps-menu-default`,
   push, and open a PR with `Closes #11`, links to all three artifacts, and the
   validation evidence. Review and wait for required checks; merge under the
   user's existing authorization only after they pass. Update this host's clean
   installed checkout to the merged revision without overwriting user changes.
   Verify registration and idempotence on the installed plugin and confirm
   Apps → GitHub Actions and Learn → GitHub Actions keybindings work. Use the
   current shell session and supported reload/enable behavior; do not restart a
   locked session. If desktop MCP control is used, acquire and release it
   explicitly. → Verify installed/source release match, root/System duplicates
   are absent, unrelated menu entries survive, and working trees are clean.

## Tests

Run from the repository with its existing toolchain:

```sh
python3 -m unittest discover -s tests -v
node tests/model.cjs
node tests/polling.cjs
python3 tests/qml-smoke.py
omarchy plugin validate .
git diff --check
```

Expected: all assertions and manifest validation pass, no unexpected QML errors,
and no whitespace errors. The smoke test needs the graphical session and
`OMARCHY_PATH`; its temporary HOME must isolate registration writes. Expected
registration-error fixtures must be checked specifically, not hidden by ignoring
all errors. Repeat targeted checks after fixes; do not rerun unrelated checks for
documentation-only edits.

## Rollback

Record the installed revision and user menu bytes before deployment. If runtime
verification fails, stop this plugin's new registration by restoring its recorded
clean revision using the supported plugin reload path. Restore the menu backup
only if it has not acquired unrelated edits; otherwise reverse only this task's
entry changes. Keep shortcuts and unrelated plugins intact. Revert published
implementation through a corrective branch/PR rather than rewriting shared
history; preserve intent/spec/plan approval commits. Verify the restored launcher
works and report the failed checkpoint. No NixOS rebuild or data migration is
required.
