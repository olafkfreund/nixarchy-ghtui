# GitHub Actions for Omarchy

A flat, keyboard-driven Quickshell popup for repositories → workflow runs → jobs → steps. Automatically discover and search repositories visible to your GitHub account, with running workflows first. Hosted inside `omarchy-shell`, with the current Omarchy menu colours, fonts, spacing, border and corner radius. Text uses 1.5× theme font sizes with matching row heights. No buttons, background daemon, database or token storage.

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

Suggested shortcut: **Super + Alt + A**, installed on this desktop. You can also open directly:

```sh
omarchy-shell shell toggle olafkfreund.github-actions '{}'
```

## Repositories

No manual repository list is required. Opening the popup fetches every page of GitHub's authenticated `GET /user/repos` endpoint with owner, collaborator and organisation-member affiliations. This covers repositories associated with your account and visible to the current token, not every public repository on GitHub. Archived and disabled repositories remain searchable but are not polled for activity. Currently github.com only; local checkouts are not required.

Press **/** and type an owner, repository name or description. Use **↑ / ↓** while typing to select a result, then **Enter** to expand it and resume navigation. **Tab** finishes editing without expanding. Search results stay collapsed until you expand them. Repositories with running workflows move to the top as activity is discovered; unchecked repositories say **not checked**. The header shows scan progress. Initial discovery is fast, but a complete activity pass across hundreds of repositories takes several minutes.

The catalogue and known activity stay in memory between openings. After five minutes, reopening refreshes the repository catalogue; **Shift + R** refreshes it immediately when you gain access to another repository. Legacy `repositories` settings are startup hints only and do not limit discovery.

### Authentication / PAT

The plugin uses your existing **`gh auth login`** authentication. It never extracts or stores the token itself. A PAT configured through GitHub CLI works too. Token restrictions still apply: fine-grained PATs need repository Metadata read and Actions read permission for the repositories you select; organisation access may require SSO authorization or approval. If a repository is missing, confirm that the same `gh` login can list it before refreshing the catalogue.

## Keyboard

| Key | Action |
| --- | --- |
| ↑ / ↓ or k / j | Select a row |
| Enter / Space / → / l | Expand or collapse a repository, run or job |
| ← / h | Collapse, or move to parent |
| Page Up / Down, Home / End | Move through long lists |
| / | Filter repositories/runs by name, branch or state |
| ↑ / ↓ while filtering | Select a search result |
| Enter while filtering | Expand selected result and resume navigation |
| Tab while filtering | Resume navigation without expanding |
| Esc | Clear filter, then close |
| r | Refresh summaries and selected expanded run |
| Shift + R | Rediscover repositories from GitHub |
| o | Open selected repository/run/job on GitHub |

Icons accompany status text: ✓ success, ✕ failure, ◷ running, ○ queued/waiting, ⊘ cancelled, − skipped/neutral. Job rows show completed/reported step counts. These are not estimates of remaining execution time. Open GitHub for full logs.

## Refresh and errors

While open, one repository's running workflows are checked every two seconds after the preceding check completes. The scan starts with recently pushed repositories, cycles through all repositories, and periodically rechecks known running repositories. Sorting uses running (`in_progress`) workflows; expanding a repository also includes queued, pending and waiting runs, plus ten recent runs. This avoids six status requests per repository on every discovery pass. The API's own filtered-search limits still apply.

The selected repository's full summary refreshes after 30 seconds; selected expanded run details refresh after 5 seconds. Responses stay associated with the requested repository/run even when selection changes. Other expanded runs retain their last fetched details and show the fetch time.

Requests are sequential within each helper, with at most one discovery, activity, summary and job helper. Each request has a 25-second timeout and each helper operation a 90-second timeout. Failures back off exponentially, retaining old data with an error indication. Individual permission failures do not block scanning other repositories. Closing cancels helpers and their `gh` children. No requests run while closed. Manual refresh bypasses backoff. Empty helper output now reports the process failure instead of a JSON parsing error.

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
