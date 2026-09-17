---
status: draft
issue: 13
spec: spec/2026-09-17-13-flake-install.md
---

# Plan: Support Git and pinned flake installation

## Approved decisions

Add `flake.nix` and a committed `flake.lock` with one nixpkgs input. Consumers can
follow their own nixpkgs. Export `packages.<system>.default` for `x86_64-linux`
and `aarch64-linux`. This output is a plugin directory, not a standalone
executable; putting it in `environment.systemPackages` alone does not install it
into Omarchy.

Use a small derivation to copy exactly these runtime files to the output root:
`manifest.json`, `ActionsPanel.qml`, `ActionsModel.js`, `Polling.js`, `actions.py`,
`menu.py`, `menu.example.json`, and `keybindings.sh`. Keep filenames and relative
helper paths intact, and include no internal symlinks. Source and packaged copies
share the same implementation. Bump the manifest to 0.4.0; derive the package
version from that manifest rather than duplicating it.

Reuse the existing Home Manager option
`programs.nixarchy.plugins."olafkfreund.github-actions".src`. Nixarchy validates
the plugin at build time and installs a store-backed link during activation. It
keeps enablement in shell.json and refuses to overwrite a real checkout. Add no
installer module, overlay, daemon, flake-parts dependency, development shell, or
second Quickshell/Omarchy stack.

Document a complete addition to an existing NixOS flake with Nixarchy and Home
Manager already integrated and enabled for the target user. Show the
`github-actions` input, its nixpkgs follows setting, how the module receives
`inputs`, the system-specific default package assigned to the plugin option, and
`home.packages = [ pkgs.gh pkgs.python3 pkgs.xdg-utils pkgs.bash ];`. The existing
desktop supplies compatible Quickshell and Omarchy commands. Explain placeholders
and prerequisite modules; do not hardcode a host or user into outputs.

Keep `omarchy plugin add <repository> --enable` and the root manifest working.
After a NixOS rebuild, users enable a newly installed plugin once through
`omarchy plugin enable olafkfreund.github-actions`; existing enablement persists.
Retain automatic Apps/Learn registration, opt-in shortcut examples, and shared
Omarchy Color/Style behavior. Managed menus require host-declared entries from
the example. Preserve runtime `gh auth login`; never put credentials into the
flake or read them during evaluation. Explain repository access requirements.

Git installations update through the plugin CLI. Nix-managed installations update
through their consumer lock and `nixos-rebuild`, never `home-manager switch`.
Migration checks Git status and preserves the entire old checkout outside the
watched plugin directory before activation. Do not silently remove dirty work,
rewrite shell/menu settings, or edit/rebuild P620/Razer in this repository task.
Those hosts' configuration integration remains a separate follow-up.

## Steps

1. **Establish the baseline.** Confirm the task branch and clean worktree, read
   any applicable repository instructions, and record the current source
   revision. Read the runtime files and their callers, the existing tests, and
   the actual Nixarchy plugin validation/activation contract. Run the source
   checks below once. → Verify the starting Git plugin works and no baseline
   failure is being hidden by packaging changes.

2. **Build the flake output.** Add `flake.nix` with the single nixpkgs input,
   default packages on both Linux architectures, and a copied runtime directory
   using the manifest version. Change `manifest.json` to 0.4.0. Generate and stage
   the lock and new files so Nix sees them. Keep tests, artifacts, and documentation
   out of the runtime output. → Build the native default package, check its exact
   file set/version and absence of symlinks, and validate it with Omarchy's real
   plugin validator. Evaluate the foreign-architecture output without claiming
   it was built unless a builder actually runs it.

3. **Check the packaged implementation.** Add flake checks using a temporary
   writable tree containing the built package and existing test sources. Run the
   Python, model, and polling suites from that tree with the necessary test tools
   supplied by Nix. Exercise menu registration with a temporary HOME. Assert
   runtime file coverage and manifest/package version agreement in the checks.
   → `nix flake check` passes on the native system, tests use packaged files, and
   no check requires authentication, live GitHub API responses, or user-config
   writes. Keep checking other architectures to evaluation when no builder exists.

4. **Verify QML from source and package.** Extend `tests/qml-smoke.py` with only
   an optional plugin-directory argument, preserving its repository default.
   Validate that argument and load its runtime QML/JS/menu files into the existing
   temporary test shell. Continue substituting the fake API helper there rather
   than modifying the package or accessing GitHub. Retain isolated menu writes,
   active theme/font/appearance reads, the theme-colour assertion, fresh and
   managed menu scenarios, and navigation/lifecycle checks. → Source and packaged
   runs pass without Nix-store writes or changes to the real menu.

5. **Document and evaluate consumer wiring.** Update `README.md` with separate
   Git and Nix installation routes, the complete existing-config example,
   dependencies, install-versus-enable behavior, private repository access,
   managed-menu and shortcut handling, migration, updates, and rollback. Evaluate
   the example in a temporary consumer using the actual Nixarchy/Home Manager
   modules, not a hand-written substitute for their options. Check that the
   plugin source resolves to the built output and the runtime packages are
   present. → Consumer configuration evaluates without activating a system or
   changing either host's configuration. Explain that an existing checkout must
   be moved aside before the managed link can take its place.

6. **Review and publish.** Check the final diff against these decisions, run
   whitespace and appropriate Nix syntax/format checks, and repeat only checks
   justified by final edits. Record exact results and architecture/session/network
   limitations in this plan. Commit and push `feat/13-flake-install`, open a PR
   with `Closes #13` and links to intent/spec/plan, and merge after final review
   and required checks pass under the approved delivery workflow. → The published
   revision contains the flake, lock, package checks, and working examples; the
   source worktree is clean. Report host deployment as outstanding rather than
   implying that publishing migrated P620 or Razer.

## Tests

Run the source regression checks with the existing toolchain:

```sh
python3 -m unittest discover -s tests -v
node tests/model.cjs
node tests/polling.cjs
python3 tests/qml-smoke.py
omarchy plugin validate .
git diff --check
```

After adding/staging the flake and lock:

```sh
nix-instantiate --parse flake.nix
nix build .#default --no-link --print-out-paths
nix flake check
nix eval .#packages.x86_64-linux.default.drvPath
nix eval .#packages.aarch64-linux.default.drvPath
```

Pass the built output path to `omarchy plugin validate` and to the smoke test's
new optional directory argument. Run the consumer evaluation against real
Nixarchy/Home Manager modules as described in step 5 and record the exact
reproducible command used. Use an available Nix formatter to check the new Nix
file; do not introduce a project environment or machine package solely to format
it. Expected: all assertions, native builds/checks, consumer evaluation, and
manifest checks succeed. Graphical checks require the active Omarchy session.
Separate pre-existing environmental warnings from actual test failures.

## Rollback

Before publication, undo only this task's changes on its branch. After
publication, use a corrective branch/PR to revert the implementation without
rewriting shared history or removing approval artifacts. Consumers can restore
their previous input lock and rebuild. To return from a managed installation to
Git, remove its declarative plugin entry and rebuild before restoring the saved
checkout; preserve user changes, enablement, authentication, and menu settings.
No P620/Razer migration or system activation is performed by this repository task.
