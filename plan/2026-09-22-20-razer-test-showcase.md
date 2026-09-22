---
status: approved
issue: 20
spec: spec/2026-09-22-20-razer-test-showcase.md
---

# Plan: Test the panel on razer, fix what breaks, and show it off

## Approved decisions

- **Target:** host razer. The ai-mirror MCP in this session drives p620, so
  razer is driven with `ssh razer ai-mirror <cmd>` (and `hyprctl`,
  `omarchy-shell`, `grim`). The session environment is borrowed from razer's
  quickshell process (`WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`,
  `HYPRLAND_INSTANCE_SIGNATURE`), as `nixarchy/docs/capture-screenshots.sh`
  does.
- **Install route:** razer's Git checkout at
  `~/.config/omarchy/plugins/olafkfreund.github-actions` (clean, at `ec7b31a`).
  It is fast-forwarded to `main` for testing, switched to this branch to
  verify fixes, and returned to `main` at the end. razer's NixOS
  configuration is not touched.
- **Driving:** keyboard only. After every key, `ai-mirror wait` plus a
  screenshot. Notifications are silenced and one monitor is focused. Before
  each scenario, `omarchy-shell -q shell hide olafkfreund.github-actions`.
  On `not_owner` or `stale_generation`, stop and ask again, never retry
  blindly.
- **Read-only:** nothing is re-run, cancelled or written on GitHub.
- **Bugs:** one checklist comment on #20, each entry with its reproduction.
  One commit per fix, with a test in the existing suites that fails before
  the fix and passes after, or a stated reason why that's impossible.
  Upstream bugs (Omarchy or nixarchy) are filed there and marked deferred.
  Each fix adds a line to "Bugs found" below in the same commit.
- **Media:** WebP stills at 1280 px wide, plus one GIF under about 1 MB. No
  video. Tools without permanent installs come from `nix shell`.
- **Privacy gate:** only public repositories appear in published media. The
  unfiltered repository list is never published. Every frame is checked by
  eye and with `tesseract` OCR against a public allow-list before commit.
- **Publishing:** this README gets a Screenshots section with the images in
  `docs/img/`. nixarchy gets its own issue, branch and PR, adding
  `docs/img/features/github-actions.gif` and
  `docs/img/plugins/github-actions-*.webp` to
  `docs/manual/plugins.md#github-actions` and replacing the "Not shown moving"
  line. Its `nixarchy-ghtui` flake pin is bumped only if this branch changes
  the UI.

## Steps

### A. Prepare razer

1. razer checkout: `git status` is clean, then `git pull --ff-only`, which
   moves it to `main` (`dfba799`) → verify with `git log -1`.
2. Reload the running panel so it loads the new files. The method is found
   empirically: first `omarchy plugin disable` then `enable`, and if that
   doesn't reload a `keepLoaded` panel, restart the Omarchy shell. The method
   is recorded here → verify that the `Apps ▸ GitHub Actions` entry from #11
   exists, since only the new code has it.
3. Write a helper `$SCRATCH/razer.sh` that runs a command on razer inside the
   session environment → verify that `razer.sh hyprctl monitors` lists
   monitors.
4. Request control with `razer.sh ai-mirror control agent` and wait for you
   to approve it on razer → verify that `ai-mirror status` reports
   `owner: agent`. If it reports `off`, stop and tell you.
5. Silence notifications, move to an empty workspace on one monitor, and
   note the silencing state so it can be restored.

### B. Test pass (§2 matrix), `main` build

6. Run every row: open/close, keybindings sheet, discovery and sorting,
   navigation, search, refresh and polling, `o` (one check only, then close
   the browser tab), and theme switch and back. Failure states run locally
   in `tests/qml-smoke.py` with a failing fake `gh` → verify that each row
   has pass or fail and a screenshot in `$SCRATCH/test/`.
7. Post the checklist comment on #20 with every failure's reproduction →
   verify that the comment URL exists.
8. Release control (`ai-mirror control off`) while fixing.

### C. Fix loop, once per bug, on this branch

9. Write the failing test → verify that it fails for the stated reason.
10. Fix the root cause in the shared function, not the caller → verify with
    `python3 -m unittest discover -s tests && node tests/model.cjs && node tests/polling.cjs`
    and `nix flake check`.
11. Commit `fix: <bug> (#20)` together with a new line in "Bugs found"
    below.
12. On razer: `git fetch` and check out `test/20-razer-test-showcase` after
    pushing the branch, reload, retest that row under control, and tick it
    on #20.

### D. Full re-run

13. Re-run the whole matrix on razer from this branch → verify that every
    row passes, and record that on #20.

### E. Capture

14. Choose a public repository with a live or recent workflow run for the
    allow-list (for example `olafkfreund/nixarchy`) → verify with `gh repo
    view --json visibility`, which should report `PUBLIC`.
15. Stills with `grim` at the panel region, converted to WebP at 1280 px
    wide (`nix shell nixpkgs#libwebp` or `ffmpeg`): list with a search
    applied, run expanded to its steps, search in progress, and the
    keybindings sheet.
16. GIF: `nix shell nixpkgs#wf-recorder` with a region recording of open →
    `/nixarchy` → expand run → job → steps → collapse → close, then encode
    with ffmpeg palettegen/paletteuse → verify that it's under about 1 MB.
17. Privacy gate: run `tesseract` on the stills and a GIF frame every 0.5 s,
    then diff every `owner/name` found against the allow-list → verify that
    nothing falls outside the list and no notification is visible, and check
    each file by eye.
18. Restore razer: notification silencing as before, the checkout back to
    `main` (or to the merged commit), and control released.

### F. Publish

19. This repo: add `docs/img/*`, add a README "Screenshots" section, commit
    `docs: add screenshots and showcase (#20)`, push, and open a PR linking
    intent, spec and plan → verify that the images render on the PR's
    README view.
20. nixarchy: create an issue and a `docs/<n>-github-actions-showcase`
    branch, following its artifact workflow for a multi-file docs change. Add
    the images, update `docs/manual/plugins.md`, bump the pin if the UI
    changed, and open a PR → verify that the Jekyll page renders locally or
    in the PR preview.
21. Both PRs wait for your review. I don't merge them.

## Tests

```sh
python3 -m unittest discover -s tests -v   # all pass
node tests/model.cjs && node tests/polling.cjs  # exit 0
nix flake check                             # green
```

Plus the razer matrix recorded on #20, and the OCR allow-list check from step
17 printing no leaks.

## Bugs found

(Filled in as fixes land, one line per fix: symptom → root cause → test.)

## Rollback

- razer: `git -C ~/.config/omarchy/plugins/olafkfreund.github-actions checkout main`
  (or `git reset --hard ec7b31a` to go all the way back), then reload.
  Notification silencing is toggled back and control is released with
  Super+Shift+Esc.
- Code: revert individual `fix:` commits, or don't merge the PR.
- Docs: revert the docs commit here, and close or revert the nixarchy PR.
