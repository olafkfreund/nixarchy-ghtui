---
status: draft
issue: 20
intent: intent/2026-09-22-20-razer-test-showcase.md
---

# Spec: Test the panel on razer, fix what breaks, and show it off

## What was found before designing

- **The ai-mirror MCP in this session drives p620, not razer.** Its monitor
  layout matches p620's `hyprctl monitors`. razer has its own `ai-mirror`
  CLI (`/etc/profiles/per-user/olafkfreund/bin/ai-mirror`) and is reachable
  by `ssh razer`. razer is driven by running `ssh razer ai-mirror <command>`,
  using the environment of razer's quickshell process, the way
  `nixarchy/docs/capture-screenshots.sh` borrows the session environment.
- **razer runs an old copy of the panel.** `~/.config/omarchy/plugins/olafkfreund.github-actions`
  is a real Git checkout at `ec7b31a` (#9), so it predates #11 (Apps menu),
  #13 (flake) and #18. Testing that copy would report bugs that are already
  fixed.
- razer's `gh` is authenticated as `olafkfreund`, and the repository list
  comes from `user/repos?affiliation=owner,collaborator,organization_member`,
  so private repositories are listed.
- The nixarchy site has no GitHub Actions image. Its other plugin GIFs live in
  `docs/img/features/<name>.gif` and its stills in `docs/img/plugins/*.webp|jpg`.
  They were recorded from the demo VM, which is unauthenticated for GitHub.
  That is why the GitHub Actions section says "Not shown moving".

## Design

### 1. Bring razer up to date, reversibly

Checking `git status` in razer's checkout showed it clean, so there's nothing
local to lose. Fast-forward it to `main` (`git pull --ff-only`) and test there.
Fixes are tested by checking out this branch in the same directory and
reloading the panel. At the end, return it to `main`.

This is the **Git installation** route that the README documents. It doesn't
touch razer's NixOS configuration. Moving razer to the flake-managed route is
out of scope.

### 2. Test pass, on razer, keyboard-only

The shell exposes no accessibility tree, so the panel is driven by its
keybindings (`keybindings.sh`). State is confirmed with `ai-mirror wait` and
a screenshot after every key, following the ai-mirror gotchas. Before
starting: silence notifications (`omarchy-toggle-notification-silencing`),
focus one monitor, and close the panel with
`omarchy-shell -q shell hide olafkfreund.github-actions` before each scenario.

Test matrix, each item with pass/fail and evidence:

| Area | Checks |
|---|---|
| Open/close | Super+Alt+A opens and closes it. Esc clears the filter first, then closes. Apps ▸ GitHub Actions opens it. |
| Keybindings | Super+Ctrl+Alt+A shows the list, and it matches `keybindings.sh`. |
| Discovery | Repositories load, running workflows sort first, and Shift+R rediscovers. |
| Navigation | j/k, arrows, PgUp/PgDn, Home/End, and expand/collapse with Enter/Space/l/h through repo → run → job → step. |
| Search | `/` focuses search. Typing filters. Arrows move without leaving search. Enter expands. Tab resumes. Esc clears. |
| Refresh/polling | `r` refreshes, and a running run's status updates without a keypress. |
| Browser | `o` opens the selected repo, run or job in the browser. |
| Failure states | Offline (`gh` failing), and an unauthenticated `GH_CONFIG_DIR` in the QML smoke harness rather than logging razer out. |
| Theme | Colours, font and radius follow a theme switch. |

The panel only reads data. No test re-runs, cancels or writes anything on
GitHub.

### 3. Bugs are recorded, then fixed

Each bug gets one checklist entry in a comment on #20, with the reproduction
steps, what was expected, what happened, and a screenshot kept locally. After
you approve the plan, each fix is one commit on this branch. When the logic
allows, the fix comes with a failing-then-passing test in the existing suites
(`tests/test_actions.py`, `tests/test_menu.py`, `tests/model.cjs`,
`tests/polling.cjs`, `tests/qml-smoke.py`). Nothing new is added to the test
setup. If a bug belongs to Omarchy or nixarchy rather than this plugin, it is
filed there and marked deferred here.

The **plan** can't list the fixes in advance because they aren't known yet.
The plan fixes the procedure. Each bug found is added to `plan/` in the same
commit as its fix, as the workflow requires for deviations.

### 4. Screenshots and showcase

Recorded on razer after the fixes, from this branch:

- **Stills (WebP, 1280 px wide):** the repository list with a running
  workflow, a run expanded to its jobs and steps, search in progress, and the
  keybindings sheet.
- **Showcase GIF, under about 1 MB:** open → search → drill into a run to
  its steps → back out → `o` hint → close. Captured with `grim` frames or
  `wf-recorder`, then encoded with `ffmpeg` (palettegen). Neither
  `wf-recorder` nor `gifski` is installed, so they run through `nix run` or
  `nix shell` without being installed permanently.

**Privacy gate (default, please confirm):** only public repositories appear
in anything published. The recording starts with a search already narrowing
the list to public repositories (for example `nixarchy`). The unfiltered
repository list is not published. Every published frame is checked by eye
and with OCR (`tesseract`, via `nix shell`) for private names, tokens and
notifications before commit.

### 5. Publishing

- **This repo:** images go in `docs/img/` and the README gets a
  "Screenshots" section near the top with the GIF and stills.
- **nixarchy:** a new issue and branch in `olafkfreund/nixarchy`, with its
  own artifacts if its workflow requires them. It adds
  `docs/img/features/github-actions.gif` and
  `docs/img/plugins/github-actions-*.webp`, links them from
  `docs/manual/plugins.md#github-actions`, and replaces the "Not shown
  moving" line. **Default:** if this branch changes the panel's UI, the same
  PR bumps nixarchy's `nixarchy-ghtui` flake pin so the site matches what
  ships. If it doesn't, only the docs change.

## Alternatives rejected

- **Driving p620 instead of razer:** you asked for razer, and p620 is where
  this session and its terminal live.
- **The nixarchy demo VM:** it's unauthenticated, so it can only show the
  one-message screen the site already explains.
- **Moving razer to the flake-managed install for testing:** it changes
  razer's system configuration, which is more than this task needs.
- **A fake API for the screenshots:** it would show real UI with invented
  data, which misrepresents the panel. It's still used in `qml-smoke.py` for
  the failure states only.
- **Video (WebM/MP4) in addition to the GIF (default, please confirm):**
  GitHub READMEs and the nixarchy site already use GIFs, so a second format
  adds size and nothing else.

## Risks

- **razer:** desktop takeover happens only with your consent. The grant ends
  after 10 minutes idle. On `not_owner`, stop and ask again rather than retry.
- **razer:** your own work on razer during the test session could be
  disturbed. Work on an empty workspace.
- **Privacy:** private repository names leaking into images. Mitigated by the
  gate in §4.
- **Stale results:** testing the old checkout would give them. Mitigated by
  §1.
- **Rate limits:** repeated Shift+R on a large account can hit GitHub's
  limit. The panel already backs off, and this is a check in the matrix.

## Verification

- `nix flake check` passes on this branch, and so does
  `python3 -m unittest discover -s tests` plus both `node tests/*.cjs`.
- Every matrix row in §2 has a pass result recorded on #20 after the fixes,
  on razer, from this branch.
- Every bug has a test that failed before its fix, or a stated reason why
  one isn't possible.
- The README renders the images on GitHub, and the nixarchy Pages build shows
  them at `/manual/plugins#github-actions`.
- OCR of every published image finds no repository outside the public
  allow-list.
