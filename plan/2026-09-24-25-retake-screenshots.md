---
status: draft
issue: 25
spec: spec/2026-09-24-25-retake-screenshots.md
coders:
  16: agy    # README Screenshots entry for the PR still: mechanical text; the lead copies images and runs every capture
reviewers:
  - codex    # fresh review of the image commit against this plan
  - agy      # second, independent review
---

# Plan: Retake the screenshots and GIF at the theme text size

**Revised 2026-11-23.** This replaces the plan approved on 2026-09-24. The
spec was revised and approved again (`8be1bc0`). Capture is from v1.3.0,
the plugin on razer comes from Nix, and there is a new pull-request still.

## Approved decisions

- **Source:** v1.3.0 (`main` at `cdc49ac`). Work happens on branch
  `docs/25-screenshots-v13` in `/mnt/code/Source-home/GitHub/nixarchy-ghtui-25`.
- **What changes:** only `docs/img/` and the README.
  - `github-actions.gif`, `github-actions-list.webp`,
    `github-actions-steps.webp` and `github-actions-search.webp` are
    replaced under the same names.
  - `github-actions-keys.webp` is replaced only if a fresh capture
    differs.
  - The new `github-actions-prs.webp` is added, together with a README
    entry, but only if it passes the gate.
  - The README alt text changes only if it is wrong. There are no code
    changes.
- **razer readiness (spec §0):** capture starts only when all four hold.
  1. razer's quickshell started after the owner's restart.
  2. The plugin link's `manifest.json` says 1.3.0.
  3. `status()` has a `view` field.
  4. `p` switches `view` to `prs` and back to `repos`, and `textStep` is 0.

  The lead never restarts razer's shell; the owner does.
- **Plugin on razer:** `~/.config/omarchy/plugins/olafkfreund.github-actions`
  is the Nix link. Nothing pulls or edits it, or the
  `olafkfreund.github-actions.bak-0.4.0` checkout.
- **Who:** the lead runs the captures on razer. The owner approves the
  ai-mirror control grant on razer's desktop. Nothing is captured on p620.
- **Agent bus:** read `#agents`, then post a CLAIM for razer's desktop.
  Post "done" only at the end of the restore (step 14). If razer is
  claimed and not released, wait.
- **Driving:**
  - A scratch helper, `$SCRATCH/razer.sh`, runs `ssh razer` with the whole
    environment of razer's quickshell, read from `/proc/<pid>/environ`.
  - Keys go to a throwaway `foot` window on an empty workspace
    (olafkfreund/ai-mirror#29). `status()` over IPC confirms that they
    landed.
  - On `not_owner` or `stale_generation`, stop and ask. Never retry.
- **Framing of the existing four** is the same as #20:
  - the stills are the card region at native size, as WebP;
  - list: search `nixarchy`, running first;
  - steps: a running run expanded to a job's steps;
  - search: narrowed to `nixarchy-p`;
  - GIF: opens filtered to `nixarchy`, drills from a run to its job and on
    to its steps, collapses back, and closes with Super+Alt+A. It is
    trimmed and cropped to the card.
- **Pull-request still (spec §3)**, taken last of the stills with no
  recording running:
  1. Press `p`, then search the full `owner/name` of one public repository
     on the allow-list. Expand one pull request to its checks.
  2. Before taking it, check every visible row: its full repository name is
     on the allow-list, and no title, branch or check name shows anything
     private.
  3. If any row cannot be verified, or no such pull request is open, skip
     the still and say so in the PR. Never open a pull request to make one.
  4. Then press `p` to go back to repositories.

  The total count of open pull requests in the header is accepted.
- **Tools:**
  `nix shell nixpkgs#wf-recorder nixpkgs#ffmpeg nixpkgs#tesseract nixpkgs#imagemagick`
  on razer, with nothing installed. `grim` is already there.
- **GIF budget:** at most about 1 MB.
  - Start from #20's settings: 1.8× speed, 7 fps, 680 px, 32 colours.
  - If it's over, lower the fps first, then the colours.
  - Make it narrower only if the text stays readable by eye.
- **Keybindings sheet:** compare a fresh capture with the current file using
  `magick compare -metric AE -fuzz 5%` at the same size, and check by eye.
  Replace the file only if it differs, and say which in the PR.
- **Privacy gate:**
  - `tesseract` reads each still and one GIF frame every 0.5 s. Every
    `owner/name` it finds is diffed against the public allow-list.
  - Every file is checked by eye. For the pull-request still, that
    includes every title, branch and check name.
  - No calendar, task or notification text may appear.
  - A file that fails is not committed.
- **Read-only on GitHub:** nothing is re-run and no pull request is opened
  to create activity.
- **nixarchy:** its copies and pin are a separate nixarchy issue and PR,
  after this one merges.

## Steps

### A. Preconditions (no razer changes)

0. **Readiness:** run readiness checks 1 to 3 over `ssh razer` → verify
   that each holds. Until the owner has restarted razer's shell, stop here
   and tell the owner. Check 4 needs control, so it runs in step 5.
1. **Branch:** `git fetch origin` and check that the branch is based on
   `origin/main` → verify with `git merge-base --is-ancestor origin/main HEAD`.
   Only the three artifact files differ from `origin/main`.

### B. Prepare razer (lead)

2. **Agent bus:** `read_new` on `#agents`, then post
   `CLAIM razer desktop: #25 screenshots (nixarchy-ghtui)` → verify that
   it appears and no newer open claim exists for razer.
3. **Helper:** write `$SCRATCH/razer.sh`, which takes razer's quickshell
   PID and exports every variable in its `/proc/<pid>/environ` → verify
   that `razer.sh 'echo $OMARCHY_PATH'` is non-empty and
   `razer.sh hyprctl monitors` lists monitors.
4. **Plugin:** read the plugin link and its `manifest.json` → verify that
   it is the Nix store link at 1.3.0, and that the `.bak-0.4.0` checkout
   is untouched (same mtime as before).
5. **Control:** run `razer.sh ai-mirror control agent`; the owner approves
   on razer → verify that `owner: agent`. If it is `off`, stop and tell
   the owner. Then run readiness check 4.
6. **Desktop:** record the silencing state, silence notifications, move to
   an empty workspace on one monitor, and open `foot` → verify with a
   screenshot: only `foot`, no notification.
7. **Allow-list:** run `gh repo view <repo> --json visibility` for each
   `nixarchy` repository, and for the one public repository chosen for the
   pull-request still → verify that each is `PUBLIC`, and that at least one
   `nixarchy` repository has a running workflow. If none does, wait; never
   re-run anything.

### C. Takes (lead, under control)

8. **Stills (list, steps, search):** `grim` the card region of each, then
   convert to WebP at native size → verify that three files are in
   `$SCRATCH/shots/` and the card fills each.
9. **GIF:** check that `status().view` is `repos`, then take the
   `wf-recorder` region recording of the Framing sequence. Trim, crop and
   encode with ffmpeg palettegen/paletteuse at #20's settings → verify the
   size with `stat -c %s`.
10. **GIF budget:** if it is over about 1,050,000 bytes, lower the fps, then
    the colours, then the width, re-encoding from the same recording each
    time → verify that it is at most about 1,050,000 bytes and readable by
    eye. Otherwise record the size and ask in the PR.
11. **Keybindings sheet:** open it with Super+Ctrl+Alt+A and capture it with
    #20's crop. Run `magick compare -metric AE -fuzz 5%` against the decoded
    current file at the same size → verify that the AE count and the eye
    check agree, then record "unchanged" or "changed".
12. **Pull-request still,** last, with no recording running:
    1. Press `p` and search the chosen full `owner/name`.
    2. Expand one pull request.
    3. Check every visible row by its full repository name, title, branch
       and check names (see the decision above). Then `grim` the card and
       convert it to WebP.
    4. Press `p` to go back.

    → verify that `status().view` is `repos`, and that the still exists or
    a skip reason is recorded.

### D. Privacy gate

13. **Gate:** run `tesseract` on each still and on GIF frames every 0.5 s,
    extract every `owner/name`, and diff them against the step 7
    allow-list. Check every file by eye; for the pull-request still that
    includes titles, branches and check names → verify that the diff is
    empty and the eye check passes. A file that fails goes back to its
    step and is not committed.

### E. Restore razer

14. **Restore:**
    - close `foot`;
    - set silencing back to the step 6 state;
    - leave the panel in the repositories view;
    - run `razer.sh ai-mirror control off`;
    - then post `done: razer desktop free (#25)` on `#agents`.

    → verify that `owner: off`, silencing matches step 6, `status().view`
    is `repos`, the plugin link and `.bak-0.4.0` are unchanged, and the
    post appears.

### F. Publish

15. **Images:** copy the files that passed into `docs/img/`. Fix the README
    alt text only if it is wrong → verify that `git status` shows only
    `docs/img/*` and possibly `README.md`.
16. **README entry** (agy): only if `github-actions-prs.webp` passed, add it
    under the Screenshots table, with descriptive alt text and a one-line
    caption, as the keybindings sheet is shown (`README.md` lines 13-17)
    → verify that the image path exists and the Markdown renders in the PR
    view.
17. **Commit:** commit `docs: retake screenshots at theme text size (#25)`,
    push, and open a PR. The PR links the intent, spec and plan, and states
    the GIF size, the keys result from step 11, the gate result from step
    13, and whether the pull-request still was taken → verify that the
    image commit's `git diff --stat` shows only `docs/img/*` and the README,
    and that CI passes. The PR is not merged without the owner.

## Tests

There are no code changes. The existing suites only confirm that nothing
moved:

```sh
python3 -m unittest discover -s tests
node tests/model.cjs && node tests/polling.cjs && node tests/bar.cjs
nix flake check
stat -c %s docs/img/github-actions.gif  # <= ~1050000
```

Also: the empty OCR allow-list diff (step 13) and the `compare` result
(step 11).

## Rollback

- **Images:** revert the docs commit, or don't merge the PR.
- **razer:**
  - run `ai-mirror control off` (or press Super+Shift+Esc);
  - set silencing back to the recorded state;
  - close `foot`;
  - press `p` if the panel is left on pull requests;
  - post "done" on the bus even if the capture was abandoned.

  The plugin link and the `.bak-0.4.0` checkout are never touched.
