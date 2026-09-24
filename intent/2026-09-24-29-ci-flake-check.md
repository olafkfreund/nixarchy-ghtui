---
status: draft
issue: 29
author: olafkfreund
---

# Intent: CI runs nix flake check on every push and pull request

## Problem

The repository has no `.github/` directory, so no tests run on GitHub.
They only run when someone remembers to run `nix flake check` locally.
A pull request can be merged with broken tests, and a reviewer can't tell
from the PR whether they pass.

The checks already exist. `checks.plugin` in `flake.nix` builds the
package, checks its file list and manifest, and then runs in the Nix
sandbox:

- the Python unit tests (`python3 -m unittest discover -s tests`, which
  covers `tests/test_actions.py` and `tests/test_menu.py`)
- `node tests/model.cjs`
- `node tests/polling.cjs`
- menu registration (`python3 menu.py register`)
- the keybindings check (`bash keybindings.sh --print`)
- the argument check of `tests/qml-smoke.py` (it must reject a missing
  plugin directory)

It needs no network access, no GitHub token and no graphical session.

`tests/qml-smoke.py` itself is not run by `nix flake check`. It needs a
graphical session, Quickshell and `OMARCHY_PATH`, so it still runs only
locally.

## Proposed outcome

- Every push to any branch and every pull request runs `nix flake check`
  on GitHub.
- A PR shows a green check when the checks pass and a red one when they
  fail, with a log that shows which test failed.
- Nothing changes for local development. `nix flake check` stays the one
  command, locally and in CI.

## Affected users and systems

- This repository: a new workflow file under `.github/workflows/`, and
  maybe a line in the README testing section.
- Contributors and reviewers, who see the result on every PR.
- GitHub Actions runners (GitHub-hosted, Linux).
- No hosts, NixOS modules or the nixarchy repository are affected.

## Constraints

- No secrets. The checks make no GitHub API calls, so the workflow needs
  only the default read-only token.
- Pin every third-party action to a full commit SHA, not a tag.
- Must run on GitHub-hosted runners. No self-hosted runner.
- Keep it cheap: one job, a short timeout, and cancel older runs on the
  same branch when a new push arrives.
- Must not change what `nix flake check` tests. CI runs the existing
  checks as they are.

## Open questions

1. Should CI also run `tests/qml-smoke.py`? That needs Quickshell running
   headless (for example under a virtual display) plus an Omarchy shell
   checkout for `OMARCHY_PATH`. It adds cost and setup, and could be a
   separate issue.
2. Should the check be a required status check on `main` (branch
   protection), so a red PR can't be merged?
3. `nix flake check` only builds checks for the runner's own system,
   `x86_64-linux`. Is that enough, or should `aarch64-linux` also run, on
   an ARM runner or through emulation?
4. Should CI cache the Nix store between runs (for example with a cache
   action), or is a cold run fast enough for a repository this small?
