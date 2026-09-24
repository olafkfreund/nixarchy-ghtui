---
status: approved
issue: 29
spec: spec/2026-09-24-29-ci-flake-check.md
---

# Plan: CI runs nix flake check on every push and pull request

## Approved decisions

- **Scope:** one new file, `.github/workflows/check.yml`, plus one README
  sentence. `flake.nix`, `tests/` and the plugin code are unchanged. CI runs
  the existing `nix flake check`, the same command developers run locally.
- **Not in CI:** `tests/qml-smoke.py` (needs Quickshell and a display),
  `aarch64-linux` (only the runner's `x86_64-linux` is checked, the default
  for `nix flake check`), and any Nix store cache.
- **Runner:** GitHub-hosted `ubuntu-latest`. No self-hosted runner.
- **Token:** `permissions: contents: read`. No secrets.
- **Cost:** one job, 15-minute timeout, and a newer push to the same ref
  cancels the older run.
- **Actions**, pinned to full commit SHAs of their latest release tags
  (looked up 2026-09-24 with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`):
  - `actions/checkout` `v7.0.1` → `3d3c42e5aac5ba805825da76410c181273ba90b1`
  - `cachix/install-nix-action` `v31.11.1` → `13d8dd58da0234aa297dedd986986ccb8e7f3e24`

  `cachix/install-nix-action` was chosen because it installs upstream Nix,
  is a small composite shell action, enables flakes, and passes the job
  token to Nix for GitHub fetches. `DeterminateSystems/nix-installer-action`
  was rejected because it installs Determinate's distribution with vendor
  defaults we don't need.
- **Workflow file**, exactly:

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

- **README line**, a new paragraph at the end of the testing section, just
  before `## Remove`, so it sits next to the paragraph about the QML check:

  > CI runs `nix flake check` on every push and pull request; the QML check
  > runs only locally.

- **Required check on `main`** (currently unprotected). The workflow never
  changes repository settings. After merge, and only after the user approves
  that step, the lead runs:

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

  `check` is the job name. `strict: false` means a branch doesn't have to
  be up to date with `main`. `enforce_admins: false` keeps an emergency
  bypass for the owner.
- **Accepted risk:** a push to a branch with an open PR runs twice (push and
  pull_request refs differ). The run is short, so this is accepted.
- **Merge order:** independent of #26–#28 and #30–#32. It touches only
  `.github/` and one README paragraph, so it can merge at any time. If
  another PR edits the README testing section first, rebase and keep both.

## Steps

1. Local baseline: `nix flake check -L` on this branch → verify that it
   exits 0, which proves the check the workflow will run is green before CI
   exists.
2. `.github/workflows/check.yml`: create it with the exact content above →
   verify with `nix run nixpkgs#actionlint -- .github/workflows/check.yml`
   (actionlint 1.7.12 is in nixpkgs), which should print nothing and exit 0,
   and with `grep -n 'secrets\.' .github/workflows/check.yml`, which should
   find nothing.
3. Commit `ci: run nix flake check on push and pull request (#29)`, push
   `ci/29-flake-check`, and open a PR linking the intent, spec and plan →
   verify with `gh pr checks <pr> --watch`, which should show `check`
   passing. `gh run view <id> --log` should show the unittest,
   `model.cjs`, `polling.cjs`, menu and keybindings output.
4. `tests/model.cjs`: throwaway red commit that adds
   `throw new Error('ci red check (#29), reverted next commit');` at the end,
   commit `test: temporary failing check (#29)`, push → verify that
   `gh pr checks <pr> --watch` shows `check` failing and the log shows that
   error.
5. Revert it with `git revert --no-edit HEAD` and push. Within a few
   seconds, before that run finishes, do step 6 and push again.
6. `README.md`: add the README line above, commit
   `docs: note that CI runs nix flake check (#29)`, push → verify with
   `gh run list --branch ci/29-flake-check --limit 5`. The run for the
   revert commit should be `cancelled`, and the run for this commit should
   pass. This checks cancel-on-push and confirms the revert restored green.
   If the revert run finished before the push landed, repeat the cancel
   check with two quick pushes of an empty commit
   (`git commit --allow-empty -m "ci: re-trigger (#29)"`).
7. Stop for review. The user merges the PR; I don't merge it.
8. **STOP. Needs the user's approval before this step.** After merge, and
   only when the user approves, the lead runs the branch-protection command
   above → verify with
   `gh api repos/olafkfreund/nixarchy-ghtui/branches/main/protection --jq '.required_status_checks.contexts'`,
   which should print `["check"]`.

## Tests

```sh
nix flake check -L                                         # exit 0 locally
nix run nixpkgs#actionlint -- .github/workflows/check.yml  # no output, exit 0
grep -n 'secrets\.' .github/workflows/check.yml            # no match
grep -c '@[0-9a-f]\{40\} #' .github/workflows/check.yml    # 2: every uses: is SHA-pinned
gh pr checks <pr>                                          # check: pass
gh run list --branch ci/29-flake-check --limit 5           # one cancelled, then pass
```

Plus the red run from step 4, recorded as a link in the PR description.

## Rollback

- Before merge: close the PR and delete the branch.
- After merge: `git revert` the merge commit, or delete
  `.github/workflows/check.yml` and the README paragraph.
- Branch protection, if it was enabled:
  `gh api -X DELETE repos/olafkfreund/nixarchy-ghtui/branches/main/protection`.
  Remove protection before removing the workflow, or every PR stays blocked
  waiting for a `check` that never runs.
