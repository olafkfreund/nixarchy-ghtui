---
status: approved
issue: 25
spec: spec/2026-09-24-25-retake-screenshots.md
coders:
  16: agy    # README entry for the PR still: a two-line conditional text edit, given the image and its verified rows; captures, copies and commits stay with the lead
reviewers:
  - codex    # fresh review of the whole PR against this plan, including agy's README edit
  - agy      # independent review of the capture and gate evidence (not of its own README edit)
---

# Plan: Retake the screenshots and GIF at the theme text size

**Revised 2026-11-23.** This replaces the plan approved on 2026-09-24. The
spec was revised and approved again (`8be1bc0`). Capture is from v1.3.0,
razer's plugin comes from Nix, and there is a new pull-request still.

## Approved decisions

- **Source:** v1.3.0 (`main` at `cdc49ac`). Work happens on branch
  `docs/25-screenshots-v13` in `/mnt/code/Source-home/GitHub/nixarchy-ghtui-25`.
- **What changes:** only `docs/img/` and the README, with no code.
  - `github-actions.gif`, `github-actions-list.webp`,
    `github-actions-steps.webp` and `github-actions-search.webp` are
    replaced under the same names.
  - `github-actions-keys.webp` is replaced only if its keys or layout
    changed.
  - The new `github-actions-prs.webp` is added, with a README entry, but
    only if it passes the gate.
  - README alt text changes only if it is wrong.
- **razer readiness (spec §0):** all four must hold, or capture stops and
  the owner is told.
  1. razer's quickshell started after the owner's restart. Its
     `ps -o lstart=` is later than 2026-11-23 09:50, when the stuck restart
     was abandoned and PID 5512 was still running.
  2. The plugin link `~/.config/omarchy/plugins/olafkfreund.github-actions`
     resolves to `/nix/store/…-nixarchy-ghtui`, and its `manifest.json`
     says 1.3.0.
  3. `razer.sh omarchy-shell plugin call olafkfreund.github-actions status`
     returns JSON with a `view` field.
  4. Pressing `p` makes `view` read `prs`, and pressing `p` again makes it
     `repos`. `textStep` is 0.
- **Deviation from spec §0:** checks 1-3 are read-only and run before the
  claim. Check 4 sends keys, so it runs after the claim, with control and
  the `foot` target ready (step 7). It still runs before any capture.
- **Plugin on razer:** nothing reads, pulls or edits the
  `olafkfreund.github-actions.bak-0.4.0` checkout. Only the link and
  manifest in check 2 are read. The lead never restarts razer's shell.
- **Who:** the lead drives razer, captures, copies images, runs the gate,
  restores and commits. The owner approves the ai-mirror control grant on
  razer's desktop. Nothing is captured on p620.
- **Agent bus:**
  - Read `#agents` first. If there is any open claim on razer, older ones
    included, wait.
  - Post the CLAIM.
  - Post "done" only after the restore is verified (step 15).
- **Driving:**
  - `$SCRATCH/razer.sh` runs `ssh razer`, exporting every variable from
    the `/proc/<pid>/environ` of razer's quickshell first.
  - Keys go to a throwaway `foot` window on an empty workspace, because
    ai-mirror sends keys only to a named window and mis-tracks focus while
    the panel is open (olafkfreund/ai-mirror#29).
  - Every key's effect is confirmed through `status()`.
  - On `not_owner` or `stale_generation`, stop and ask. Never retry.
- **Framing (inherited from #20 plan steps 15-16, written out here):**
  - **Stills:**
    - `grim -g <card geometry>` at the card's native size: 900 px wide,
      and 1000 px for the keybindings sheet. Never wider, because the
      desktop around the card shows calendar and tasks.
    - Converted to WebP with `ffmpeg` (`-c:v libwebp -lossless 0
      -quality 90`).
    - The card geometry comes from the panel's `layout()` IPC plus the
      monitor offset.
    - Shots:
      - list: search `nixarchy`, running first;
      - steps: a running run expanded to its job, and the job to its
        steps;
      - search: narrowed to `nixarchy-p`.
  - **GIF:**
    - A `wf-recorder -g <card geometry>` recording that opens already
      filtered to `nixarchy`. The filter survives Super+Alt+A.
    - It drills from a run to its job and to its steps, collapses back,
      and closes with Super+Alt+A (Esc would clear the filter).
    - The recording is trimmed to the time the card is on screen, found by
      sampling its border pixel at 10 fps, plus a margin, and cropped to
      the card.
- **GIF encode and budget:**
  - ffmpeg palettegen/paletteuse, starting at 1.8× speed, 7 fps, 680 px
    and 32 colours (#20's result was 1.06 MB).
  - The target is at most about 1,050,000 bytes. If it is over, lower the
    fps first, then the colours, then the width, but only while the text
    stays readable by eye. Each try re-encodes from the same recording.
  - If it is still over while readable, record the size and ask the owner
    in the PR.
- **Keybindings sheet:**
  - Capture it at 1000 px, then run
    `magick compare -metric AE -fuzz 5%` against the decoded current file
    at the same size.
  - Replace the file only if its keys or layout changed, judged by eye.
    A pixel difference alone, such as from anti-aliasing or the theme,
    keeps the old file.
  - The PR records the AE number and the decision.
- **Pull-request still (spec §3), the last still:**
  - Two traps:
    - The view lists pull requests from every repository you can see,
      private ones included.
    - Its search is a plain substring match over repository, title,
      branch, status and check names, with no visibility filter. Typing
      `owner/name` can still show a private pull request that mentions
      it.
  - So:
    1. Press `p`.
    2. Search the full `owner/name` of one allow-listed public repository.
    3. Expand one pull request so its checks are visible.
    4. Check every visible row by its full repository name, title, branch
       and check names.
    5. Capture only if every row is verified. Otherwise, or if no such
       pull request is open, skip the still and record why. Never open a
       pull request to make one.
    6. On both paths, press `p` again to return to repositories.
  - The total count of open pull requests, private ones included, shows in
    the header and in the status strip. It is accepted.
  - If an earlier image has to be retaken after this still, take the
    pull-request still again (or skip it) afterwards, so it stays last.
- **Privacy gate:**
  - **Allow-list:** every public repository on the account whose name
    contains `nixarchy`, plus the one chosen for the pull-request still:
    `gh repo list olafkfreund --visibility public --limit 200 --json nameWithOwner`,
    filtered to `nixarchy`. #20 had 14 of them.
  - **OCR:** `tesseract` reads each still and one GIF frame every 0.5 s.
    Every `owner/name` it finds is normalised (lowercase, trailing
    punctuation stripped).
  - **Pass:** each file has **zero names outside the allow-list**, it
    passes the eye check, and it shows no calendar, task or notification
    text.
    - For the pull-request still, the eye check also covers every title,
      branch and check name.
    - OCR misses elided text, so the rows identified at capture time are
      what count.
  - A file that fails is retaken or dropped, never committed.
- **Read-only on GitHub:** nothing is re-run and no pull request is opened
  to create activity.
- **nixarchy:** its copies and pin are a separate nixarchy issue and PR,
  after this one merges.

## Steps

### A. Local (no razer changes)

0. **Branch:** `git fetch origin`. Check that `cdc49ac` is an ancestor of
   `HEAD` (`git merge-base --is-ancestor cdc49ac HEAD`) and that
   `git diff --stat origin/main` lists only the intent, spec and plan
   files.
1. **Helper:** write `$SCRATCH/razer.sh` (local scratch; it doesn't change
   razer) → verify that `razer.sh 'echo $OMARCHY_PATH'` is non-empty and
   `razer.sh hyprctl monitors` lists monitors.
2. **Readiness 1-3:** run checks 1, 2 and 3 → verify each one. If any
   fails, stop and tell the owner. That includes the shell not yet being
   restarted.

### B. Prepare razer

3. **Agent bus:** run `read_new` on `#agents`. With no open claim on
   razer, post `CLAIM razer desktop: #25 screenshots (nixarchy-ghtui)` →
   verify that it appears.
4. **Allow-list:** build it as in the decisions, and confirm with
   `gh repo view <repo> --json visibility` that the chosen pull-request
   repository is `PUBLIC`. Check for a running workflow with
   `gh run list -R <repo> --status in_progress --limit 1` on the
   `nixarchy` repositories → verify that the list is non-empty and at least
   one run is in progress. If none is, wait and re-check; never re-run
   anything.
5. **Control:** run `razer.sh ai-mirror control agent`; the owner approves
   on razer → verify that `ai-mirror status` reports `owner: agent`. If it
   reports `off`, stop and tell the owner.
6. **Desktop:** record the silencing state, silence notifications, move to
   an empty workspace on one monitor, and open `foot` → verify with an
   ai-mirror screenshot that only `foot` is there and no notification
   shows.
7. **Readiness 4:** open the panel with Super+Alt+A, press `p`, then `p`
   again → verify through `status()` that `view` was `prs` and is now
   `repos`, and that `textStep` is 0. If `textStep` is not 0, press
   Ctrl+0 and check again. If anything else fails, stop.

### C. Takes (under control)

8. **Stills:** take list, steps and search, as in Framing → verify that
   three WebP files are in `$SCRATCH/shots/`, each 900 px wide and filling
   with the card. Compare their text size by eye with the old
   `docs/img/` files; the new ones should be smaller, at the theme size.
9. **GIF recording:** `status().view` must be `repos` and no recording may
   be running. Record the Framing sequence, then trim and crop it → verify
   that the recording file exists and covers the whole sequence.
10. **GIF encode:** encode, and apply the budget rules → verify with
    `stat -c %s` that it is at most about 1,050,000 bytes, or record the
    size for the owner. Check that the text is readable and theme-sized by
    eye, compared with the old GIF.
11. **Keybindings sheet:** Super+Ctrl+Alt+A, capture at 1000 px, then close
    it → verify that the AE number is recorded, keys and layout are judged
    by eye, and the decision is "unchanged" or "changed".
12. **Pull-request still:** follow the decision steps exactly, with no
    recording running. Before `grim`, check that the expanded pull
    request's checks are visible → verify that `github-actions-prs.webp` is
    in `$SCRATCH/shots/` or a skip reason is recorded, and that
    `status().view` is `repos` on both paths.

### D. Privacy gate

13. **Gate:** run the allow-list check on every file → verify that each
    has zero names outside the allow-list, passes the eye check, and shows
    no calendar, task or notification text. A failing file is retaken:
    steps 8 to 11, then step 12 again. Otherwise it is dropped. If the
    pull-request still fails, skip it and record why.

### E. Restore razer

14. **Restore** (control still held):
    - close the panel if it is open (Super+Alt+A), first checking that
      `view` is `repos`;
    - close `foot`;
    - set silencing back to the step 6 state;
    - run `razer.sh ai-mirror control off`.

    → verify that `owner: off`, silencing matches step 6, `status().view`
    is `repos` with the panel closed, and the plugin link from check 2 is
    unchanged.
15. **Release:** only after step 14 is verified, post
    `done: razer desktop free (#25)` on `#agents` → verify that the post
    appears.

### F. Publish

16. **README entry** (agy; only if `github-actions-prs.webp` passed): add it
    after the Screenshots table (`README.md` lines 11-13) and before the
    keybindings line (line 15). Use descriptive alt text and a one-line
    caption in the style of lines 15-17, written from the image and the
    rows verified in step 12 → verify that the image path exists locally
    and the Markdown is well formed.
17. **Images:** copy the files that passed into `docs/img/`. Fix existing
    alt text only if it is wrong → verify that `git status` shows only
    `docs/img/*` and, only for those two reasons, `README.md`.
18. **Commit and PR:**
    1. Run the Tests below.
    2. Commit `docs: retake screenshots at theme text size (#25)` and
       push.
    3. Open a PR that links the intent, spec and plan, and states:
       - the GIF size;
       - the keybindings AE number and decision;
       - the gate result per file;
       - whether the pull-request still was taken, or why it was skipped.

    → verify that the image commit's `git diff --stat` shows only
    `docs/img/*` and the allowed README change, CI passes, and every image
    renders in the PR's README view. The PR is not merged without the
    owner.

## Tests

There are no code changes. The suites only confirm that nothing moved:

```sh
python3 -m unittest discover -s tests
node tests/model.cjs && node tests/polling.cjs && node tests/bar.cjs
nix flake check
stat -c %s docs/img/github-actions.gif  # <= ~1050000, or the owner accepted the recorded size
```

Also: zero names outside the allow-list per file (step 13), the
keybindings decision (step 11), and the text-size comparisons by eye
(steps 8 and 10).

## Deviations

- **Step 2, owner-approved (2026-11-23):**
  - razer had no shell at all. The earlier stuck restart had stopped the
    old one, and nothing started a new one. The lead started it with
    `omarchy-restart-shell` (process start time 10:13:51).
  - The new shell then loaded v0.4.0 from the backup
    `olafkfreund.github-actions.bak-0.4.0`, because it was still in
    `~/.config/omarchy/plugins/` with the same plugin ID.
  - The backup was moved, not deleted, to
    `~/.local/share/nixarchy-ghtui-checkout-0.4.0`, followed by
    `omarchy-shell shell reloadPlugins`.
  - Readiness 3 then passed: `view: "repos"`, `textStep: 0`.
  - The plan's "the backup is never touched" now means its new path.
  - The `status()` call is
    `omarchy-shell shell call olafkfreund.github-actions status ""`.

- **Step 9, owner-approved:**
  - The first GIF failed the gate: with the `nixarchy` filter, the list
    showed the private `olafkfreund/nixos_config`. One of its recent runs
    was titled "chore(nixarchy): pin nixarchy-ghtui…". OCR misread it, and
    the eye check caught it.
  - The GIF was deleted and retaken with the filter
    `olafkfreund/nixarchy`. That filter matches 31 repositories, all
    public, and the panel showed exactly 31 rows.
  - The retake waited until all 123 repositories had been checked, so the
    rows show results. The final GIF is 578,611 bytes.
- **Control:** it went `off` at 10:40:37, before the GIF retake. On the
  owner's answer it was requested once more and granted (generation 5).
- **Keys sheet:** its new height is 687 px, against 722 before; the width
  is 1000 px. AE is 14429 (2.1 %), and by eye the keys changed (pull
  requests, zoom), so the file is replaced.
- **Pull-request still not last (agy review):**
  - `github-actions-prs.webp` (about 10:28) was not retaken after the
    later GIF retake.
  - The rule exists so the GIF starts in the repositories view. Each
    retake's `status()` lines confirm `view: repos` before recording.
  - The still was kept. It passed the gate, and a retake would change
    nothing the rule protects.
- **Step order:** `herdr-team` refuses a dirty worktree, so the images
  (step 17) were committed as `e3fd10b` before agy's README entry (step
  16). The final diff is the same.

## Rollback

- **Images:** revert the docs commit, or don't merge the PR.
- **razer**, in this order:
  1. If control is still held, check that the panel is on repositories,
     pressing `p` if it shows pull requests, then close the panel and
     `foot`.
  2. Set silencing back to the recorded state.
  3. Run `ai-mirror control off` (or press Super+Shift+Esc).
  4. Post "done" on the bus, even if the capture was abandoned.

  If control was lost before step 1, tell the owner that the panel may be
  left on pull requests. One `p` on razer fixes it. The plugin link and
  the old checkout (now
  `~/.local/share/nixarchy-ghtui-checkout-0.4.0`) are never touched.
