---
status: draft
issue: 25
intent: intent/2026-09-24-25-retake-screenshots.md
---

# Spec: Retake the screenshots and GIF at the theme text size

**Revised 2026-11-23** (the owner chose to re-plan on current `main` and add
a still of the pull-request view). Three changes from the version approved
on 2026-09-24:

1. The images are captured from v1.3.0 (`main` at `cdc49ac`), not from the
   release after #30 and #32. Both have long since merged.
2. razer runs the plugin from Nix, not from a git checkout (§2).
3. A fifth image shows the pull-request view (§3), and the README shows it.

## Design

This reuses #20's capture unchanged except where noted:
`spec/2026-09-22-20-razer-test-showcase.md` §4, and
`plan/2026-09-22-20-razer-test-showcase.md` steps 3–5 and 14–18, including
their recorded deviations. Only the differences and the approved decisions
are spelled out here.

### 0. When

The images are taken once, from v1.3.0. Capture starts only when razer's
running shell has loaded v1.3.0. On 2026-11-23 razer still ran v0.4.0 from
memory: its shell ignored `quickshell kill`, and the owner chose to restart
it themselves. The check is that the loaded panel reports the pull-request
view: `status()` over IPC has a `view` field.

### 1. Claim razer

Before touching razer, post a claim in `#agents` on the agent bus, saying
that razer's desktop is in use for #25 screenshots. Read the room first. If
someone else has claimed razer and not released it, wait. When step 6 is
finished, post "done" in the same room.

### 2. Drive razer only

Nothing is captured on p620. razer is driven with `ssh razer`, by a
scratch helper `razer.sh` (as in #20 plan step 3). The helper imports the
**whole** environment of razer's running quickshell process from
`/proc/<pid>/environ`, not the three variables #20 picked. That brings
`OMARCHY_PATH` along with `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` and
`HYPRLAND_INSTANCE_SIGNATURE`, because `omarchy-shell` and the theme lookup
need it. Driving follows #20 plan step 4: `ai-mirror control agent`, wait
for your grant, keys to a throwaway `foot` window (olafkfreund/ai-mirror#29),
and the panel's `status()` IPC to confirm them. On `not_owner` or
`stale_generation`, stop.

Preparation (#20 plan steps 1, 2 and 5):

- razer's `~/.config/omarchy/plugins/olafkfreund.github-actions` is
  nixarchy's link to the Nix store, and its `manifest.json` says 1.3.0.
  The old checkout stays in `olafkfreund.github-actions.bak-0.4.0`, and
  nothing reads it or changes it.
- No `git pull`. The shell is not restarted by the lead; that is the
  owner's call (§0).
- Record the silencing state, silence notifications, and move to an empty
  workspace on one monitor.

### 3. Take sequence and framing

These are the same as #20 so that only the text size differs. The allow-list
is re-checked with `gh repo view --json visibility`.

- **Stills** (`grim` of the card region, then WebP at the card's native
  size, #20 plan step 15). The files replace the existing ones under the
  same names:
  - `github-actions-list.webp`: search `nixarchy`, the repository with a
    running workflow first.
  - `github-actions-steps.webp`: a running run expanded to its jobs, and a
    job to its steps.
  - `github-actions-search.webp`: search narrowed to `nixarchy-p`.
  - **New:** `github-actions-prs.webp`, the pull-request view (`p`), with
    one pull request expanded to its checks.
    - The view lists your pull requests across all of github.com, private
      repositories included. So the search is narrowed first to public
      repositories on the allow-list (for example `nixarchy`), and the
      §7 gate also reads every pull-request title and branch by eye.
    - If no open pull request on a public allow-listed repository exists
      at capture time, the still is skipped and the PR says so. No pull
      request is opened to create one.
- **GIF** (`github-actions.gif`, #20 plan step 16): the panel opens already
  filtered to `nixarchy`, a run is expanded to its job and then to its steps,
  everything is collapsed again, and Super+Alt+A closes it (Esc would clear
  the filter). The recording is trimmed to the card's time on screen and
  cropped to the card.

### 4. Tools

Everything comes from `nix shell nixpkgs#…` on razer, and nothing is
installed: `wf-recorder`, `ffmpeg` (palettegen/paletteuse and WebP),
`tesseract`, and `imagemagick` for the comparison in §6. `grim` is already
on razer.

### 5. GIF size budget

The GIF must be at most about 1 MB. Start from #20's settings (1.8× speed,
7 fps, 680 px wide, 32 colours, 1.06 MB). If it is over, lower the fps first
and the colours second. Make it narrower only if the smaller text stays
readable at that width, checked by eye.

### 6. Keybindings sheet comparison

Capture the sheet (Super+Ctrl+Alt+A) with the same crop as #20. Then
compare it with the current `github-actions-keys.webp`, using
`magick compare -metric AE -fuzz 5%` after both are the same size, and
check it by eye as well.

- If the sheet is unchanged, keep the old file.
- If it differs (the keys or layout), replace the file.

The PR says which one happened.

### 7. Privacy gate

The #20 gate (plan step 17) runs unchanged on every file that will be
published. `tesseract` reads each still, and a GIF frame every 0.5 s. Every
`owner/name` it finds is diffed against the public allow-list, then every
file is checked by eye. No calendar, task or notification text may appear.
If any check fails, that file is not committed.

### 8. Restore razer

- Set notification silencing back to its recorded state.
- The plugin link and the `.bak-0.4.0` checkout are left as they are.
- Close the throwaway `foot` window and run `ai-mirror control off`.
- Post "done" in `#agents` (§1).

### 9. Publish

- Commit the images: `docs: retake screenshots at theme text size (#25)`.
  Fix the README alt text only if it is now wrong.
- Add `github-actions-prs.webp` to the README's Screenshots section, under
  the table, with alt text that describes it, the way the keybindings
  sheet is shown.
- Open a PR linking the intent, spec and plan. I don't merge it.
- nixarchy (the copies and the pin bump) is a separate nixarchy issue and
  PR, opened after this PR merges (intent question 2). It's not part of this
  change.

## Alternatives rejected

- **Retaking only the same images (owner's choice, 2026-11-23):** the
  pull-request view is the biggest feature since #20 and deserves one
  still. The bar widget is not shown: it is a separate plugin.
- **Updating razer's old checkout instead of using the Nix link:** future
  deploys would skip it again.

- **Capturing now, before #30 and #32:** you chose to capture once, after
  both have merged.
- **Changing framing, repositories or sequence:** readers should see only
  the text-size change, and #20's framing already passed the privacy gate.
- **Always retaking the keybindings sheet:** it's Omarchy's own sheet, so
  a new capture without a difference is churn.
- **Importing only #20's three variables:** that misses `OMARCHY_PATH`.
  Importing the whole environment is simpler and complete.
- **p620 or the demo VM:** razer only, and the VM is unauthenticated.

## Risks

- **razer:** another agent or you using the desktop at the same time. The
  bus claim prevents it, and the ai-mirror grant makes you consent to it.
- **Privacy:** a private repository or a personal widget in a frame. The
  §7 gate and the card-only crop prevent it.
- **Private pull requests in the pull-request view:** it lists pull requests
  from every repository you can see. The narrowed search, the OCR
  allow-list diff and the eye check of titles and branches prevent it.
- **razer's shell still on v0.4.0:** §0 blocks the capture until the owner
  restarts it.
- **No running workflow on a `nixarchy` repository at capture time:** the
  list and steps shots need one. Wait for natural activity. Nothing is
  re-run to create it.
- **GIF over budget with readable text:** §5 order. If it's still over, the
  PR says so and asks.

## Verification

- `git diff --stat` shows only `docs/img/*` and the README.
- The OCR allow-list diff prints nothing for every published file, and every
  file was checked by eye.
- `stat -c %s docs/img/github-actions.gif` is at most about 1,050,000.
- The stills and GIF show theme-sized text, compared by eye with the old
  files.
- The PR says whether the keybindings sheet changed, with the `compare`
  result.
- The README renders the images in the PR view.
- razer is back to its recorded notification state, the plugin link is
  unchanged, control is released, and "done" is posted on the bus.
