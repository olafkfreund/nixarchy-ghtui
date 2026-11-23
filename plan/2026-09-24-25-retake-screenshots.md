---
status: approved
issue: 25
spec: spec/2026-09-24-25-retake-screenshots.md
---

# Plan: Retake the screenshots and GIF at the theme text size

## Approved decisions

- **What changes:** only `docs/img/`. `github-actions.gif`,
  `github-actions-list.webp`, `github-actions-steps.webp` and
  `github-actions-search.webp` are replaced under the same names.
  `github-actions-keys.webp` is replaced only if a fresh capture differs.
  The README changes only if its alt text is now wrong. No code changes.
- **When:** after #30 (merged as `065ce6d`) and #32 are on `main`. The
  images are captured once, from that `main`.
- **Who:** the lead runs the captures on razer. You approve the ai-mirror
  control grant on razer's desktop. Nothing is captured on p620.
- **Agent bus:** read `#agents`, then post a CLAIM for razer's desktop for
  #25 before touching razer. Post "done" after razer is restored. If razer
  is claimed by someone else and not released, wait.
- **Driving:** a scratch helper `$SCRATCH/razer.sh` runs `ssh razer` with
  the **whole** environment of razer's quickshell process, imported from
  `/proc/<pid>/environ`. That includes `OMARCHY_PATH`, `WAYLAND_DISPLAY`,
  `XDG_RUNTIME_DIR` and `HYPRLAND_INSTANCE_SIGNATURE`. Keys are sent to a
  throwaway `foot` window on an empty workspace
  (olafkfreund/ai-mirror#29), and the panel's `status()` IPC confirms they
  land. On `not_owner` or `stale_generation`, stop and ask; never retry.
- **Framing (same as #20):** the stills are the card region only, at native
  size, as WebP. The shots are the list (search `nixarchy`, running first),
  a running run expanded to a job's steps, and the search narrowed to
  `nixarchy-p`. The GIF opens already filtered to `nixarchy`, drills from a
  run to its job and on to its steps, collapses back, and closes with
  Super+Alt+A. It is trimmed to the time the card is on screen and cropped
  to the card.
- **Tools:** `nix shell nixpkgs#wf-recorder nixpkgs#ffmpeg nixpkgs#tesseract nixpkgs#imagemagick`
  on razer, with nothing installed. `grim` is already there.
- **GIF budget:** at most about 1 MB. Start from #20's settings: 1.8×
  speed, 7 fps, 680 px, 32 colours. If it's over, lower the fps first, then
  the colours. Make it narrower only if the text stays readable by eye.
- **Keybindings sheet:** compare a fresh capture with the current file
  using `magick compare -metric AE -fuzz 5%` at the same size, and check by
  eye. Replace the file only if it differs, and say which in the PR.
- **Privacy gate:** `tesseract` reads each still and one GIF frame every
  0.5 s. Every `owner/name` found is diffed against the public allow-list,
  and every file is checked by eye. No calendar, task or notification text
  may appear. A file that fails is not committed.
- **Read-only on GitHub:** nothing is re-run to create activity. If no
  `nixarchy` repository has a running workflow, wait for one.
- **nixarchy:** its copies and the pin bump are a separate nixarchy issue
  and PR, opened after this PR merges. They're not part of this plan.

## Steps

### A. Preconditions (this repo, no razer)

0. **Precondition:** #32 is merged → verify that
   `gh issue view 32 --json state` reports `CLOSED` and
   `git log origin/main` shows its merge. #30 is already in
   (`065ce6d`). Until #32 merges, stop here.
1. Rebase this branch onto the new `main`:
   `git fetch origin && git rebase origin/main` → verify that
   `git merge-base --is-ancestor origin/main HEAD` succeeds and only the
   three artifact files differ from `origin/main`.

### B. Prepare razer (lead)

2. Agent bus: `read_new` on `#agents`, then post
   `CLAIM razer desktop: #25 screenshots (nixarchy-ghtui)` → verify that
   the post appears and no open claim for razer is newer than it.
3. Write `$SCRATCH/razer.sh`: find razer's quickshell PID over `ssh razer`,
   export every variable from its `/proc/<pid>/environ`, then run the
   command → verify that `razer.sh 'echo $OMARCHY_PATH'` is non-empty and
   `razer.sh hyprctl monitors` lists monitors.
4. razer checkout: `git status` is clean, then `git pull --ff-only`, then
   `omarchy-restart-shell` → verify that `git log -1` equals
   `origin/main`, and that the panel's card still loads (its `status()`
   IPC answers).
5. `razer.sh ai-mirror control agent`, and **you approve it on razer** →
   verify that `ai-mirror status` reports `owner: agent`. If it reports
   `off`, stop and tell you.
6. Record the notification silencing state, silence notifications, move to
   an empty workspace on one monitor, and open the throwaway `foot` window →
   verify with a screenshot that the workspace is empty apart from `foot`
   and no notification is visible.
7. Allow-list: `gh repo view <repo> --json visibility` for every repository
   matching `nixarchy` → verify that each reports `PUBLIC`, and that at
   least one has a running workflow (otherwise wait; never re-run).

### C. Takes (lead, under control)

8. Stills: `grim` the card region for list, steps and search, then convert
   to WebP at native size → verify that three files exist in
   `$SCRATCH/shots/` and that the card fills each frame.
9. GIF: `wf-recorder` region take of the sequence from "Framing", then
   trim, crop and encode with ffmpeg palettegen/paletteuse at #20's
   settings → verify the size with `stat -c %s`.
10. GIF budget: if the size is over about 1,050,000 bytes, lower the fps,
    then the colours, then the width, re-encoding from the same recording
    each time → verify that it's at most about 1,050,000 bytes and the text
    is readable by eye. If it can't get there, record the size and ask in
    the PR.
11. Keybindings sheet: open it with Super+Ctrl+Alt+A and capture it with #20's
    crop, then run `magick compare -metric AE -fuzz 5%` against the decoded
    current `docs/img/github-actions-keys.webp` at the same size → verify
    that the AE count and an eye check agree. Record "unchanged" (keep the
    old file) or "changed" (use the new one).

### D. Privacy gate

12. Run `tesseract` on each still and on GIF frames every 0.5 s. Extract
    every `owner/name` and diff them against the step 7 allow-list → verify
    that the diff is empty and, by eye, no calendar, task or notification
    text appears in any file. A file that fails is retaken (back to step 8
    or 9) and is not committed.

### E. Restore razer

13. Close `foot`, set silencing back to its recorded state, and run
    `razer.sh ai-mirror control off` → verify that `ai-mirror status`
    reports `owner: off`, that silencing matches step 6, and that the
    checkout is on `main`.
14. Agent bus: post `done: razer desktop free (#25)` → verify that the post
    appears.

### F. Publish

15. Copy the files that passed into `docs/img/`. Fix the README alt text
    only if it's wrong. Commit
    `docs: retake screenshots at theme text size (#25)` → verify that
    `git diff --stat origin/main` shows only `docs/img/*`, the artifacts,
    and the README if it changed.
16. Push and open a PR linking the intent, spec and plan. The PR states the
    GIF size, the keybindings result from step 11, and the gate result from
    step 12 → verify that the images render in the PR's README view. I
    don't merge it.

## Tests

No code changes. The existing suites run only to confirm that nothing
moved:

```sh
python3 -m unittest discover -s tests   # all pass
node tests/model.cjs && node tests/polling.cjs  # exit 0
nix flake check                         # green
stat -c %s docs/img/github-actions.gif  # <= ~1050000
```

Plus the empty OCR allow-list diff from step 12 and the `compare` result
from step 11.

## Rollback

- **Images:** revert the docs commit, or don't merge the PR. The old images
  are in git history.
- **razer:** `ai-mirror control off` (or Super+Shift+Esc), set
  notification silencing back to its recorded state, close `foot`, and run
  `git -C ~/.config/omarchy/plugins/olafkfreund.github-actions checkout main`
  followed by `omarchy-restart-shell`. Post "done" on the bus even if the
  capture was abandoned.
