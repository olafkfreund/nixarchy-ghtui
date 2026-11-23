---
status: approved
issue: 25
author: olafkfreund
---

# Intent: Retake the screenshots and GIF at the theme text size

## Problem

#22 (merged in #26) removed the panel's own `textScale: 1.5`, so the panel
now uses the Omarchy theme's text sizes, like the other menus. The images
were captured for #20 before that change, so they show the old, larger text
and taller rows. They no longer match what users get when they install the
panel.

In this repository, the README's Screenshots section uses these files in
`docs/img/`:

- `github-actions.gif`
- `github-actions-list.webp`
- `github-actions-steps.webp`
- `github-actions-search.webp`
- `github-actions-keys.webp`: this is Omarchy's keybindings sheet, not the
  panel. #22 probably didn't change it, but nobody has checked.

nixarchy has its own copies: `docs/img/features/github-actions.gif` and
`docs/img/plugins/github-actions-*.webp`, used in
`docs/manual/plugins.md#github-actions`. Its `nixarchy-ghtui` flake input is
pinned to `4f51f7f`, which is older than #22. So the nixarchy site shows the
old text, and nixarchy installs the old panel.

## Proposed outcome

- The GIF and the three panel stills in `docs/img/` show the panel at the
  theme text size. They keep the same file names, so the README needs no
  change unless its alt text or captions are now wrong.
- The keybindings sheet is compared against a fresh capture. It is replaced
  only if it differs, and the PR says which one happened.
- The nixarchy copies are replaced with the same images, and nixarchy's
  `nixarchy-ghtui` pin moves to a `main` commit that includes #22. There are
  no tags or releases, so a commit is the only thing to pin.
- Every published frame passes the privacy gate from #20.

## Affected users and systems

- Anyone reading this repo's README or the nixarchy manual's GitHub Actions
  section.
- This repository: `docs/img/` and possibly the README's alt text.
- **razer**: the capture host. It's driven with `ssh razer ai-mirror` in the
  session environment, keyboard only, as in #20. Its plugin checkout
  (`~/.config/omarchy/plugins/olafkfreund.github-actions`) must be on a
  commit that includes #22, and it must be reloaded with
  `omarchy-restart-shell`.
- `olafkfreund/nixarchy`: `docs/img/features/`, `docs/img/plugins/`,
  `docs/manual/plugins.md` if captions change, and the `nixarchy-ghtui` input
  in `flake.nix` and `flake.lock`. Anyone who updates nixarchy gets the new
  panel code through that pin, which includes every other fix merged here
  since `4f51f7f`, not only #22.

## Constraints

- Captures happen only on razer, never on p620. Control is granted on razer
  and can be taken back at any time. On `not_owner` or `stale_generation`,
  stop and ask again, never retry.
- Privacy gate from #20: published media shows public repositories only.
  The take opens already filtered (for example `nixarchy`), and the
  unfiltered list is never published. Every still, and a GIF frame every
  0.5 s, is OCR'd with `tesseract` and every `owner/name` is checked against
  the public allow-list, then checked by eye. No calendar, task or
  notification text may appear. Notifications are silenced during capture.
- The framing, repositories and sequence match #20 where possible, so the
  only change a reader notices is the text size. That means the same
  `nixarchy` search, a running workflow drilled down to its job's steps and
  back, stills cropped to the card at native size, and the keybindings sheet
  as it is.
- The GIF stays under about 1 MB. Tools come from `nix shell`, with nothing
  installed permanently on razer.
- Read-only on GitHub: nothing is re-run or cancelled to create activity.
- razer's checkout and notification state are restored afterwards.

## Open questions

1. **Timing against #30 and #32.** #30 (PR #35, open) adds a
   "+N more queued" row. It appears only when a repository has more than 100
   unfinished runs of one status, which is unlikely in the public `nixarchy`
   repositories, so the shots probably won't show it. #32 changes how
   untrusted titles and URLs are handled, which normally changes nothing
   visible. Default: wait until both have merged, then capture once. The
   shots then show the final UI, and nixarchy's pin is bumped once, to a
   commit that has all three fixes. The alternative is to capture now and
   accept a second pin bump later.
2. **Is the nixarchy update part of this issue?** The images can't change
   there until they exist here. Default, as in #20: a separate nixarchy
   issue, branch and PR, under nixarchy's own workflow, carrying the copied
   images and the pin bump. It's opened after this repo's PR merges. #25
   stays open until that PR merges, or is closed with a link to it. Either
   way, which should it be?
