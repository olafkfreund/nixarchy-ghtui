---
status: approved
issue: 1
spec: spec/2026-09-16-1-actions-panel.md
---
# Plan: GitHub Actions popup

User authorized end-to-end implementation and plan review. Implement a read-only Omarchy panel using existing Quickshell, gh, Python stdlib and native theme components. Default repository olafkfreund/nixarchy; explicit additional repositories in shell.json. Grouped keyboard-only rows with status icons, runs, jobs and steps. No buttons or new service.

## Steps
1. Write manifest, Python API helper and data tests. Paginate active runs/jobs, add recent runs, validate arguments, use timeouts and report errors without secrets. Verify with unittest and a real gh request.
2. Write QML panel and small JS tree helper. Use Color.menu, Style, BorderSurface; arrow/jk navigation, expand/collapse, search, refresh, escape, open on GitHub. Async processes, stale indication, exponential backoff, selection by ID, stop polling closed. Verify tree tests and isolated QML load.
3. Review correctness, lifecycle, themes and keyboard behavior; fix findings and record checks. Write README, bindings example and reproducible installation instructions.
4. Commit and push task branch; open PR linking artifacts and Closes #1. Live installation waits for fresh login: running tree 4.0.3 differs from installed 4.0.4. Do not bypass the mismatch through installed absolute paths.

## Tests
python3 -m unittest discover -s tests -v; node tests/model.cjs. Real helper calls must return valid JSON without mutating GitHub. Isolated QML host must load without plugin errors, using the running shell import paths. Record any unavailable visual verification honestly.

## Rollback
Disable/remove plugin via omarchy plugin commands and remove its one keybinding. No system rebuild or system service change. Revert source commit to undo development.
