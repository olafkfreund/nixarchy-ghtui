# GitHub Actions for Omarchy

A flat, keyboard-driven Quickshell popup for repositories → workflow runs → jobs → steps. Hosted inside `omarchy-shell`, with the current Omarchy menu colours, fonts, spacing, border and corner radius. No buttons, background daemon, database or token storage.

## Requirements

- Omarchy shell with the panel plugin contract and `qs.Commons` / `qs.Ui` components.
- `gh`, authenticated for your repositories with Actions read access.
- Python 3, and `xdg-open` for the optional browser shortcut.

On NixOS, missing dependencies belong in your declarative configuration. Do not install them with pacman or an imperative Nix profile.

## Install

Ensure your running session matches the installed Omarchy generation first. If you rebuilt since login, log out and back in.

```sh
omarchy plugin add https://github.com/olafkfreund/nixarchy-ghtui.git --enable
```

This repository is currently private, so Git must have access to clone it.

Check `omarchy menu keybindings --print` for conflicts, then add the line from `bindings.example.lua` to your writable `~/.config/hypr/bindings.lua`. If Home Manager owns the file, change its declarative source instead. Validate with `hyprctl reload` followed by `hyprctl configerrors`.

Suggested shortcut: **Super + Ctrl + Shift + A**. You can also open directly:

```sh
omarchy-shell shell toggle olafkfreund.github-actions '{}'
```

## Repositories

The default is `olafkfreund/nixarchy`. Merge this entry into the existing `plugins` array in `~/.config/omarchy/shell.json`; preserve your other settings and plugins:

```json
{
  "id": "olafkfreund.github-actions",
  "repositories": ["olafkfreund/nixarchy", "owner/another-repo"]
}
```

All configured repositories appear in one grouped list. The list defines the monitored scope; the plugin does not scan every repository accessible to your account. Currently github.com only. Local checkouts are not required.

## Keyboard

| Key | Action |
| --- | --- |
| ↑ / ↓ or k / j | Select a row |
| Enter / Space / → / l | Expand or collapse a repository, run or job |
| ← / h | Collapse, or move to parent |
| Page Up / Down, Home / End | Move through long lists |
| / | Filter repositories/runs by name, branch or state |
| Enter while filtering | Keep filter and resume navigation |
| Esc | Clear filter, then close |
| r | Refresh summaries and selected expanded run |
| o | Open selected repository/run/job on GitHub |

Icons accompany status text: ✓ success, ✕ failure, ◷ running, ○ queued/waiting, ⊘ cancelled, − skipped/neutral. Job rows show completed/reported step counts. These are not estimates of remaining execution time. Open GitHub for full logs.

## Refresh and errors

While open, summaries refresh 30 seconds after a request completes; selected expanded run details refresh after 5 seconds. Changing selection never redirects a response to another run. Other expanded runs retain their last fetched details. Completed runs are included in the ten most recent runs per repository, alongside all returned active runs. The API's own filtered-search limits still apply.

Requests are sequential within each helper, with at most one summary helper and one job helper. Each request has a 25-second timeout and the whole operation a 90-second timeout. Failures back off exponentially, retaining old data with an error indication. Closing cancels helpers and their `gh` children. No requests run while closed. Manual refresh bypasses the backoff.

## Checks

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
node tests/model.cjs
python3 tests/qml-smoke.py
```

Node is only used by tests. The QML check requires a graphical session, Quickshell and `OMARCHY_PATH`; it loads shared components in a temporary configuration without opening a window or installing the plugin.

## Remove

Remove the keybinding and run `omarchy plugin remove olafkfreund.github-actions`. No NixOS rebuild is required for a user-owned plugin.
