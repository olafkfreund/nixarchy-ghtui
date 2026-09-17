---
status: approved
issue: 13
intent: intent/2026-09-17-13-flake-install.md
---

# Spec: Install the plugin from Git or a pinned flake package

## Design

Add `flake.nix` and commit its `flake.lock`. Use one nixpkgs input with a documented
`inputs.nixpkgs.follows = "nixpkgs"` override for consumers. Export
`packages.<system>.default` for `x86_64-linux` and `aarch64-linux`. The default
package is an Omarchy plugin directory, not a standalone application executable.

Build a plain copied directory containing only the runtime files:

- `manifest.json`, `ActionsPanel.qml`, `ActionsModel.js`, and `Polling.js`.
- `actions.py`, `menu.py`, `menu.example.json`, and `keybindings.sh`.

Keep filenames and the manifest at the package root so existing relative helper
paths and the plugin validator work. Do not put symlinks inside the package: the
Omarchy validator rejects them. Keep source files shared by both installation
routes, without generating a second implementation or changing QML imports.
The package can use a small `runCommand` derivation; no flake-parts, overlay,
custom installer, daemon, development shell, or additional module is needed.

Use the existing Home Manager option
`programs.nixarchy.plugins."olafkfreund.github-actions".src` to install the output.
The inspected Nixarchy `modules/home.nix` validates each plugin during the build
and links it into the user's plugin directory during activation. It deliberately
keeps enablement in the user-owned shell.json. Its activation also leaves a real
directory in place rather than replacing it, which matters for migration.

Document the following additions to an existing NixOS configuration that already
integrates Nixarchy and Home Manager as NixOS modules. Placeholder input and user
names in the example must be explained; they are not hardcoded into outputs.

```nix
# In the existing flake's inputs:
github-actions = {
  url = "github:olafkfreund/nixarchy-ghtui";
  inputs.nixpkgs.follows = "nixpkgs";
};

# In a NixOS module receiving inputs through the configuration's specialArgs:
home-manager.users.<user> = { pkgs, ... }: {
  programs.nixarchy.plugins."olafkfreund.github-actions".src =
    inputs.github-actions.packages.${pkgs.stdenv.hostPlatform.system}.default;
  home.packages = [ pkgs.gh pkgs.python3 pkgs.xdg-utils pkgs.bash ];
};
```

The final README example must be copyable after substituting the user's name and
show where `inputs` comes from, using the enclosing module arguments or flake
output closure. Nixarchy's Home Manager module and desktop must already be
enabled for that user; this plugin does not install an entire desktop or import a
second Home Manager stack. The existing desktop supplies compatible Quickshell
and Omarchy commands. Explicit runtime packages satisfy the helper commands used
by both routes; listing this plugin in `environment.systemPackages` alone does
not register it with Omarchy.

After the NixOS rebuild, enable once using
`omarchy plugin enable olafkfreund.github-actions`. Existing enablement persists.
The loaded panel registers Apps and Learn entries just as with the Git route.
Existing managed-menu limitations remain documented: declare `menu.example.json`
entries through host configuration instead of writing a managed file. Shortcuts
remain opt-in using `bindings.example.lua`; do not rewrite bindings or shell.json.
Authentication continues through the user's runtime `gh auth login` credentials.

Preserve `omarchy plugin add <repository> --enable` and the root manifest so
ordinary Git installation works unchanged. Explain that Git checkouts update
with the plugin CLI, while Nix-managed copies update by changing the consumer's
locked `github-actions` input and rebuilding with `nixos-rebuild`. Never recommend
`home-manager switch` for this NixOS integration. The repository's existing access
requirements also apply when Nix fetches the input; no credentials go in Nix code.

For migration, document checking the existing directory's Git status and backing
it up outside the watched plugins directory before activation installs a managed
link. Preserve dirty changes and the shell/menu configuration. Do not silently
delete an existing checkout or change P620/Razer's system configuration in this
repository task. Describe rollback by restoring the previous consumer lock and
rebuilding; returning to Git also requires removing the declarative entry before
restoring the saved checkout.

Keep shared Omarchy Color/Style usage and Apps placement unchanged. Bump the
manifest version to 0.4.0 to identify the new distribution capability; package
version follows the manifest rather than maintaining a separate version string.

## Alternatives rejected

- A non-flake source input alone: possible with today's module but does not
  provide the requested flake or a checked runtime package.
- A new Home Manager/NixOS installer module: duplicates the existing one-option
  Nixarchy contract without adding needed behavior.
- An overlay or standalone Nix app: the output is loaded by the desktop shell.
- A symlink farm: conflicts with Omarchy plugin validation.
- Pin another Quickshell/Omarchy copy: risks mixing incompatible desktop versions.
- Force activation or overwrite checkouts: conflicts with existing ownership and
  user enablement behavior.

## Risks

Omitting a helper or changing relative paths could make a package build while
breaking launch or registration. Tests must exercise the packaged files.
Installing the plugin alone cannot supply ambient commands, so the documented
consumer dependency list is part of the supported route. Consumers need a
Nixarchy version with the existing plugin option. An existing checkout masks the
managed link until migrated; state this explicitly. Host rebuilds and changes to
their separate configuration repository remain a follow-up task.

## Verification

- Build the default package on the available architecture and validate it with
  Omarchy's plugin validator. Assert the expected runtime file set, no internal
  symlinks, and version agreement with the manifest.
- Add flake checks that run the existing Python, model, and polling tests against
  a temporary tree assembled from the built package plus test sources. Run
  registration with a temporary HOME so checks neither need live GitHub access
  nor modify the user's configuration.
- Evaluate both Linux package outputs. Only claim builds on architectures actually
  built; the other output may be evaluation-only if no builder is available.
- Validate consumer wiring against the actual Nixarchy/Home Manager option
  contract, including resolution of the package and required dependencies,
  without activating or rebuilding P620/Razer.
- Run source regressions and the QML smoke test, retaining isolated menu writes
  and the active Omarchy theme. Extend the smoke harness only as necessary to
  exercise the built plugin while replacing its API helper with the existing fake
  fixture; never write to the Nix store or request real GitHub data in tests.
- Run whitespace and appropriate Nix formatting/evaluation checks. Explain any
  network, graphical-session, or foreign-architecture limits honestly.
