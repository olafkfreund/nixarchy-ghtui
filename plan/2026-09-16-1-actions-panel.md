---
status: approved
issue: 1
spec: spec/2026-09-16-1-actions-panel.md
---
# Plan: GitHub Actions popup

User authorized end-to-end implementation and plan review. Implement a read-only Omarchy panel using existing Quickshell, gh, Python stdlib and native theme components. Automatically discover account-accessible repositories and rank running workflows first; see the authorized #3 revision below. Grouped keyboard-only rows with status icons, runs, jobs and steps. No buttons or new service.

## Steps
1. Write manifest, Python API helper and data tests. Paginate active runs/jobs, add recent runs, validate arguments, use timeouts and report errors without secrets. Verify with unittest and a real gh request.
2. Write QML panel and small JS tree helper. Use Color.menu, Style, BorderSurface; arrow/jk navigation, expand/collapse, search, refresh, escape, open on GitHub. Async processes, stale indication, exponential backoff, selection by ID, stop polling closed. Verify tree tests and isolated QML load.
3. Review correctness, lifecycle, themes and keyboard behavior; fix findings and record checks. Write README, bindings example and reproducible installation instructions.
4. Commit and push task branch; open PR linking artifacts and Closes #1. Review the diff against this plan and merge after checks pass, completing repository delivery under the user’s end-to-end authorization. The user subsequently authorized installation in the current session; use the session’s tree and verify the installed plugin as described in #3 below.

## Tests
python3 -m unittest discover -s tests -v; node tests/model.cjs. Real helper calls must return valid JSON without mutating GitHub. Isolated QML host must load without plugin errors, using the running shell import paths. Record any unavailable visual verification honestly.

## Rollback
Disable/remove plugin via omarchy plugin commands and remove its one keybinding. No system rebuild or system service change. Revert source commit to undo development.

## Implementation review

- Recent history is the ten newest runs plus paginated active runs; no session-long history cache. This avoids preserving obsolete active states or adding individual reconciliation requests. Spec wording aligned in the implementation commit.
- Cached expanded runs show when jobs were fetched; only the selected expanded run refreshes every five seconds. Summary refresh is thirty seconds after completion. Both back off on errors.
- Elapsed labels rebuild on data refresh; a separate lightweight clock updates the global freshness label without rebuilding the list every second.
- Seven Python checks (including child cancellation and a whole-scan deadline), JS tree checks and an isolated QML lifecycle/navigation check pass. Read-only real requests return nixarchy workflows, two jobs and thirteen steps. A temporary populated popup was visually inspected with the current theme. An asynchronous refresh through the panel also passed.
- Initial installation and shortcut activation were deferred because the running Omarchy tree resolves to 4.0.3 while the installed package is 4.0.4. The user subsequently authorized activation; Super+Alt+A is installed and Hyprland validation passed.

## Authorized revision and review: #3

1. actions.py: add paginated repository catalogue and lightweight paginated in-progress activity modes → test affiliations, page boundaries and status filtering.
2. ActionsPanel.qml / ActionsModel.js / manifest.json: consume completed process results with visible errors, increase theme-relative fonts and row heights, discover all accessible repositories, search names/descriptions, rank known running repositories first, show scan progress and unchecked/error states, preserve selection/cache, stop all requests closed. Keep the panel loaded for caching; no service. Shift+R refreshes catalogue. → test transport failures, ranking, transitions, QML lifecycle and live API flow.
3. README and binding example: document discovery, token visibility, scan latency, PAT access through gh, and actual installed Super+Alt+A shortcut. → compare with implemented behavior.
4. Commit and open PR with Closes #3 and artifact links; merge only tested code. Preserve diagnostic installed changes in a git stash, fast-forward the installed plugin, restart the same session shell to clear stale QML caches, and open the updated popup. The user explicitly overrode the earlier activation pause. → query live status and confirm visible surface and successful repository/job data.

Review: scanning all statuses across every repository would consume six requests per repository per pass. One lightweight in-progress query finds running repositories; selected-repository expansion still fetches pending/queued/waiting states. A full activity pass takes minutes for hundreds of repositories; the UI must not pretend unchecked means idle. Nine Python tests, model tests and QML checks pass. Live discovery found 137 repositories and placed running nixarchy first.

Final follow-up validation: live end-to-end discovery → active repository → workflow → jobs → 26 steps passed with 137 repositories and no application error. The expanded QML regression checks also cover discovery pagination, active-first sorting and permission-error handling.

## Authorized interaction fix: #5

The user requested direct MCP desktop testing after repeated refresh jumps and unusable search.

1. Replace the simulated search editor with native Qt TextInput. Arrow keys select results during editing; Enter expands the selected result and returns to navigation; Tab returns without expanding. Search does not automatically expand matching trees.
2. Update a persistent ListModel by row key, preserving delegates, selected identity and viewport position during background responses. Reset selection and viewport when the query changes.
3. Verify model updates and QML search/selection across polling, then exercise the visible popup through MCP keyboard input and screenshots. The user confirmed the live candidate works.
4. Document controls, release 0.2.1, open a PR closing #5 with artifact links, merge after checks, and update the installed plugin.

Rollback: revert this fix and restart the session shell to reload the previous plugin version.

## Authorized menu integration: #7

The user requested menu discovery and all keyboard controls in Omarchy’s keyboard UI.

1. Add a main-menu launcher and Learn keyboard-reference entry using the native user JSONC extension; preserve unrelated entries. Ship the mergeable entries with the plugin.
2. Reuse omarchy-menu-select for a searchable reference covering global launcher/help shortcuts, navigation, expansion, search editing, refresh and GitHub opening. Add the free Super+Ctrl+Alt+A reference shortcut beside Super+Alt+A; both appear in the existing global keyboard menu. Do not register panel-local keys as global actions.
3. Verify shell syntax, reference content, JSON, binding conflicts and Hyprland config errors; test menu launcher and keyboard reference through MCP. Publish tested 0.2.2 and install the files and user extension. No shell restart is required for menu-only changes.

Rollback: remove the two documented extension entries and help binding, and revert the source commit.

Runtime review: Omarchy executes menu actions in a login shell, which can select a newer NixOS generation than the active desktop. A small menu.py wrapper reads Quickshell’s JSON instance list for the current display and resolves the running Omarchy tree before invoking the existing launcher or key reference. Reject missing or ambiguous trees. This avoids hardcoded store paths; uwsm-app inherited the incorrect login-shell override too. Verify tree detection and failure paths with temporary directories, then retest the real menu.
