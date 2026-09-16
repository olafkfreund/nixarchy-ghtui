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

Check `omarchy menu keybindings --print` for conflicts, then add the lines from `bindings.example.lua` to your writable `~/.config/hypr/bindings.lua`. If Home Manager owns the file, change its declarative source instead. Validate with `hyprctl reload` followed by `hyprctl configerrors`.

Suggested shortcut: **Super + Alt + A**, installed on this desktop. You can also open directly:

```sh
omarchy-shell shell toggle olafkfreund.github-actions '{}'
```

## Omarchy menus

Merge the entries from `menu.example.json` into `~/.config/omarchy/extensions/omarchy-menu.jsonc`, preserving existing entries. Omarchy reloads this file automatically. The main menu gets **GitHub Actions** (also searchable as workflows/pipelines); **Learn → GitHub Actions keybindings** opens a searchable native reference for every panel control.

**Super+K** opens Omarchy’s keyboard menu: search **GitHub Actions** to find the launcher and **GitHub Actions keybindings**. The latter also opens directly with **Super+Ctrl+Alt+A**. Panel-local keys are documented in this reference; they only act inside the popup. The two bindings and menu entries are installed on this desktop.

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

While open, one scheduler fetches a single API page at a time. Selecting a repository settles for 250 ms before prioritizing missing or stale data; rapid navigation coalesces requests. Moving among a run’s jobs and steps does not restart its refresh deadline.

| Data | Refresh target |
| --- | --- |
| Inspected unfinished run’s jobs/steps | 5 seconds |
| Selected repository activity | 10 seconds |
| Other known running repositories | 15 seconds |
| Selected full workflow summary | 60 seconds |
| Previously checked idle repositories | 10 minutes |

Unchecked repositories are scanned first in catalogue order. Three request slots serve selected data, one serves known running workflows, and one serves background discovery; spare slots serve other due work. Pagination yields between requests. All paths, including manual refresh, share a maximum of 60 requested pages per rolling minute, at least one second between starts, and one request in flight. These are ceilings: missing work, slow responses and cooldowns reduce request frequency.

Cached data remains usable during refresh. Recent history arrives first; full summaries include all five active states and ten recent runs. Only complete snapshots reconcile removals or mark activity checked. When a running workflow disappears, the panel fetches its final status rather than assuming success. Inspected completed runs receive a final jobs fetch, then reuse the result until refresh or a detected rerun.

GitHub retry/reset headers pause all work. Secondary rate limits without a deadline start with a one-minute wait and back off up to fifteen minutes. Network/server errors back off the affected resource from five seconds up to five minutes; permission failures leave that repository unavailable until catalogue/manual refresh. Authentication failures pause polling until retry/reopen. Manual refresh never bypasses a server cooldown. Closing cancels the helper and its gh child; reopening retains cached data, local request history and cooldowns. A shell restart clears local memory; GitHub’s quota remains authoritative.

A request can take up to 25 seconds before timeout, and shares the account’s GitHub quota with other tools. Refresh targets can therefore stretch under load, network failures or rate limits. No polling occurs while closed, and no token is extracted or stored by the plugin.

### Measured polling comparison

Deterministic simulation with 137 repositories and one-second responses (not a live-network speed guarantee):

| Measure | 0.2.2 baseline | 0.3.0 |
| --- | --- | --- |
| API requests over 30 idle minutes | 902 | 713 |
| Initial activity pass | 411 seconds | 168 seconds |

With four active repositories and one inspected run, the simulation completes the selected summary in 9 seconds. Maximum data ages after warm-up are 8.75 seconds for jobs, 11.75 seconds for selected activity and 20.75 seconds for other active activity. The reproducible workload is in `tests/polling.cjs`; overload tests verify fairness and limits when those freshness targets cannot be met.

## Checks

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
node tests/model.cjs
node tests/polling.cjs
python3 tests/qml-smoke.py
```

Node is only used by tests. The QML check requires a graphical session, Quickshell and `OMARCHY_PATH`; it uses shared components and a fake API in a temporary configuration, briefly exercising the panel window without installing the plugin or requesting live GitHub data.

## Remove

Remove both keybindings and the two entries from `menu.example.json`, then run `omarchy plugin remove olafkfreund.github-actions`. No NixOS rebuild is required for a user-owned plugin.
