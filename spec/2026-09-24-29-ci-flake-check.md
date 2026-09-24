---
status: approved
issue: 29
intent: intent/2026-09-24-29-ci-flake-check.md
---

# Spec: CI runs nix flake check on every push and pull request

## Design

### Scope

Add one workflow file, `.github/workflows/check.yml`, that runs the
existing `nix flake check` on GitHub-hosted `ubuntu-latest`
(`x86_64-linux`). Keep `flake.nix`, `tests/` and the plugin code as they
are. CI runs exactly what developers run locally, so there is nothing
new to maintain beyond the workflow file.

Decisions from the intent review:

- `tests/qml-smoke.py` is not run in CI. It stays a local check.
- Only `x86_64-linux` is checked. `nix flake check` builds checks only for
  the runner's own system, so this needs no extra flag.
- No Nix store cache. The check depends only on nixpkgs `python3` and
  `nodejs`, which come from `cache.nixos.org`. A cache action would add a
  moving part for little time saved.
- The check becomes a required status check on `main` (see below).

### Workflow

```yaml
name: check

on:
  push:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: cachix/install-nix-action@13d8dd58da0234aa297dedd986986ccb8e7f3e24 # v31.11.1
      - run: nix flake check -L
```

- `permissions: contents: read` gives the default token read-only access.
  No secrets are used.
- The concurrency group cancels an older run when a new push lands on the
  same branch or PR.
- A 15-minute timeout caps a hung run. A cold run is expected to take a
  few minutes.
- `-L` prints full build logs, so a red check shows which test failed.
- Both actions are pinned to the full commit SHA of their latest release,
  with the tag in a comment so a reader and Dependabot can see the
  version. Looked up on 2026-09-24 with
  `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (both are lightweight
  tags pointing at commits):
  - `actions/checkout` `v7.0.1` → `3d3c42e5aac5ba805825da76410c181273ba90b1`
  - `cachix/install-nix-action` `v31.11.1` → `13d8dd58da0234aa297dedd986986ccb8e7f3e24`

### Nix installer choice

Use `cachix/install-nix-action`. It installs upstream Nix with the
official installer script, is a small composite action with no JavaScript
runtime, and enables flakes by default. It passes the job's
`github.token` to Nix for GitHub fetches, which avoids anonymous API rate
limits when fetching `nixpkgs`.

### Required status check on main

The workflow does not change repository settings. After the workflow has
run once on a PR (so GitHub knows the `check` context), the lead or the
user enables branch protection on `main` (currently unprotected):

```sh
gh api -X PUT repos/olafkfreund/nixarchy-ghtui/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": { "strict": false, "contexts": ["check"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
EOF
```

The `check` context is the job name. `strict: false` doesn't require
branches to be up to date with `main` before merging. `enforce_admins:
false` leaves the owner able to merge in an emergency. Verify with
`gh api repos/olafkfreund/nixarchy-ghtui/branches/main/protection`.

### README

Add one sentence to the testing section, after the `nix flake check`
paragraph: "CI runs `nix flake check` on every push and pull request;
the QML check runs only locally."

## Alternatives rejected

- `DeterminateSystems/nix-installer-action`: works, but installs
  Determinate's Nix distribution and installer by default and brings
  vendor defaults (FlakeHub, diagnostics) we don't need. Upstream Nix
  matches what developers use locally.
- Running each test command directly (`python3 -m unittest`, `node …`)
  in the workflow instead of `nix flake check`: two lists of tests to keep
  in sync. The flake already runs them in a sandbox.
- Running `tests/qml-smoke.py` headless: needs Quickshell, a virtual
  display and an Omarchy shell checkout. Declined in the intent review.
- An `aarch64-linux` job (ARM runner or QEMU): declined; the package is a
  copy of text files, so architecture-specific breakage is unlikely.
- A Nix store cache (`magic-nix-cache`, `cache-nix-action`): declined; see
  Scope.
- Pinning actions by tag: tags can be moved. The constraint requires SHAs.
- Having the workflow set branch protection: it would need an admin token
  as a secret. It is a one-time manual step instead.

## Risks

- A push to a branch with an open PR runs the check twice (once for
  `push`, once for `pull_request`), because the two refs differ. Accepted:
  the run is short, and dropping either trigger would lose coverage the
  intent asks for.
- `nixpkgs` is fetched from `flake.lock` on each cold run. A GitHub or
  `cache.nixos.org` outage turns the check red without a code problem.
  Re-run the job.
- A PR from a fork gets a read-only token and no secrets. The workflow
  needs neither, so it works the same.
- Pinned SHAs go stale. Updating them is a manual edit (or a later
  Dependabot config, not in scope).
- Once the check is required, a broken runner or outage blocks merging
  until it passes or the owner bypasses it.

## Verification

- `nix flake check -L` passes locally on `x86_64-linux` before the PR.
- The PR shows a green `check` status, and its log shows the unittest,
  `model.cjs`, `polling.cjs`, menu and keybindings output.
- A throwaway commit that breaks a test (for example, a failing assert in
  `tests/model.cjs`) turns the check red, then is reverted. It is not
  merged.
- Two quick pushes to the PR branch: the first run is cancelled.
- The workflow file contains no `secrets.` reference and only
  SHA-pinned `uses:` lines.
- After merge, `gh api repos/olafkfreund/nixarchy-ghtui/branches/main/protection`
  lists `check` under required status checks.
