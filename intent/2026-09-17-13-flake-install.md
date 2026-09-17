---
status: draft
issue: 13
author: olafkfreund
---

# Intent: Support Git and Nix flake installation

## Problem

The plugin currently ships no flake.nix. P620 and Razer use independent Git
checkouts under their user plugin directories, so the NixOS configuration does
not pin or reproduce their installed plugin versions. Users of an existing
NixOS flake need a supported way to include this plugin as an input.

## Proposed outcome

The repository supports both installation routes:

- Existing Omarchy users can continue using `omarchy plugin add ... --enable`.
- NixOS users can add this repository as a flake input and install a pinned
  plugin through their existing configuration, with a complete documented example.

Both routes provide the same GitHub Actions panel, Apps launcher, Learn reference,
and active Omarchy theme. Documentation explains dependencies, installation versus
enablement, updates and rollback, and safe migration from an existing Git checkout.
Two hosts consuming the same locked input can reproduce the same plugin version.

## Affected users and systems

This plugin repository, its installation documentation and checks, and users
consuming it from NixOS configurations. P620 and Razer are the motivating hosts.
Changing or rebuilding those hosts' system configurations is a subsequent
consumer integration task, not an automatic side effect of publishing a flake.

## Constraints

- Add a real flake.nix while preserving the root Omarchy manifest and Git install.
- Reuse Nixarchy's existing plugin installation contract rather than inventing
  another installer, daemon, or plugin enablement mechanism.
- Use the consumer's existing Nixarchy and Home Manager integration; Home Manager
  is a NixOS flake module and must not be applied with `home-manager switch`.
- Account for gh, Python, and browser-launch dependencies and actual helper paths
  when installed from the Nix store. Preserve the existing runtime gh login;
  never put credentials in a flake or read them during evaluation.
- Keep host/user names out of reusable outputs. Allow consumers to follow their
  own nixpkgs input if this flake uses nixpkgs.
- Respect user-owned shell/menu settings, managed files, and existing Git
  checkouts; migration must not silently delete or overwrite local changes.
- Preserve Apps placement and shared Omarchy Color/Style theme behavior.
- Verify the flake and the built plugin, not merely the existence of flake.nix;
  keep the existing Python, model, polling, and QML behavior working.

## Open questions

None for problem framing. The specification will select the smallest public
flake outputs and consumer wiring supported by the existing Nixarchy contract.
