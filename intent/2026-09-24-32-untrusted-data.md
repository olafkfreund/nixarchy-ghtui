---
status: draft
issue: 32
author: olafkfreund
---

# Intent: Harden handling of untrusted GitHub data and declare runtime dependencies

## Problem

The panel shows text that other people control, and it passes one value
to a program outside itself. It also depends on three programs that the
flake package does not declare.

1. **The browser URL is barely checked.** `openBrowser()` in
   `ActionsPanel.qml` (around line 176) checks only
   `^https://github\.com/` before it calls
   `Quickshell.execDetached(["xdg-open", current.url])`. Whitespace,
   newlines and control characters after that prefix still pass.
   `xdg-open` is a shell script that hands the URL to whichever desktop
   helper is set up. The URL comes from GitHub's `html_url` for a run or
   job, so it is trustworthy today. This check is defence in depth, in
   case that assumption stops holding.
2. **Row text can misrepresent a row.** `ActionsModel.js` builds row
   titles and subtitles from `run.display_title`, `run.head_branch`,
   `run.name` and the repository `description`. `actions.py` passes these
   through unchanged. The panel renders them with `Text.PlainText`, so no
   markup is interpreted. Bidi overrides such as U+202E, other Unicode
   Cc/Cf characters, and newlines still reach the screen. A fork's pull
   request controls its branch name and title, so it can make a row seem
   to show a different branch or status. For example, reversed text can
   appear to say "success" next to a failing run. Job and step names come
   from the workflow file, which a fork pull request can also change.
3. **Runtime dependencies are not declared.** The flake's `default`
   package (`flake.nix`, lines 24–31) only copies files. The QML calls
   `python3` (for `actions.py` and `menu.py`) and `xdg-open`, and
   `actions.py` calls `gh`. All three are looked up on `PATH`. The README
   tells users to install them, but a Nix consumer gets no help from the
   package. nixarchy works around this in `modules/home.nix` (around
   line 1664) by listing `pkgs.gh`, `pkgs.python3` and `pkgs.xdg-utils`
   in its plugin `packages` option, which puts them on the session
   `PATH`.

## Proposed outcome

- The panel opens a URL only if it is a well-formed `https://github.com/`
  URL with no whitespace or control characters. Anything else is refused
  quietly, as a non-matching URL is now.
- Text from GitHub has bidi controls, other Cc/Cf characters and line
  breaks removed or replaced before it is shown or searched. A row always
  shows its real branch and status. Ordinary non-ASCII text, such as
  accented letters, CJK and emoji, is left alone.
- The Nix package states what it needs at runtime, `gh`, `python3` and
  `xdg-utils`, so a consumer can find it without reading the README.
- Tests cover a hostile title or branch and a malformed URL.
- The Git installation (`omarchy plugin install`, no Nix) works exactly
  as it does now.

## Affected users and systems

- Everyone who uses the panel, especially maintainers of public
  repositories that accept fork pull requests.
- This repository: `ActionsPanel.qml`, `ActionsModel.js` and/or
  `actions.py`, `flake.nix`, the tests, and possibly the README's
  requirements section.
- **nixarchy** (`olafkfreund/nixarchy`, `modules/home.nix`). It
  consumes `packages.<system>.default` by `cp -r` into its own
  `runCommand` (around line 305) and adds a `menu.managed` marker, so
  attributes such as `passthru` on our package do not carry over to that
  copy. It separately passes gh, python3 and xdg-utils through its
  plugin `packages` list (around line 1664). If this work changes the
  package, nixarchy may need a follow-up, such as reading our declared
  dependencies instead of repeating them, with its own issue and PR.
- `nixarchy-gltui`, the GitLab fork of this panel, has the same pattern
  (`modules/home.nix` around line 297). Any fix here is a candidate to
  port there, but that is out of scope for this issue.
- Open PR #28 also touches `actions.py` and `ActionsPanel.qml`.
  Implementation starts after it merges, to avoid conflicts.

## Constraints

- No new dependencies beyond nixpkgs. No third-party Python or JS
  libraries. The Python standard library (`unicodedata`) and plain JS are
  enough.
- The Git installation without Nix must keep working. Its files are
  copied as they are, so they cannot rely on store paths that only a Nix
  build puts in place.
- The panel stays read-only. It makes no writes to GitHub and does not
  change which API endpoints it calls.
- Stripping or replacing characters must not change the data the panel
  uses for identity or matching (IDs, `repo` names used in API paths,
  keys). It changes only what is displayed.
- nixarchy's current consumption (`cp -r` of the package, plus its own
  `packages` list) must keep building and working unchanged until
  nixarchy chooses to adopt anything new.
- The flake checks (`nix flake check`) must still pass, including the
  check that the package contains exactly the `runtimeFiles` list.

## Open questions

1. **Where should text be cleaned?** In `actions.py`, once, before the
   JSON reaches QML, or in `ActionsModel.js` when rows are built? Python
   has `unicodedata.category` for Cc/Cf. JS would need a regex over
   Unicode property escapes (`\p{Cc}`, `\p{Cf}`), which the QML JS engine
   must support. Cleaning in Python keeps one choke point. Cleaning in JS
   also covers any future data path that bypasses the helper.
2. **Remove or make visible?** Should removed characters vanish, or be
   replaced with a visible marker such as U+FFFD, so that tampering can be
   seen?
3. **Which fields?** Only `display_title`, `head_branch` and
   `description`, or every string from GitHub, including workflow, job
   and step names and error text?
4. **How strict should the URL check be?** A tighter regex in QML (for
   example `^https://github\.com/[^\s\x00-\x1f\x7f]+$`), or parse and
   rebuild the URL in `actions.py` and pass only known-good URLs to QML?
5. **How should runtime dependencies be declared?**
   - (a) `passthru.runtimeDeps = [ gh python3 xdg-utils ]` on the
     package. It only documents them, and `PATH` lookup stays as it is.
     nixarchy's `cp -r` drops it, but nixarchy could read it from
     `inputs.nixarchy-ghtui.packages.<system>.default.runtimeDeps`.
   - (b) Replace bare `python3`, `gh` and `xdg-open` with store paths
     during the Nix build. This makes the package self-contained, but the
     files then differ between the Nix and Git installations, the
     `runtimeFiles` check must allow it, and the closure grows.
   - (c) Both.
6. **Should nixarchy change?** Should nixarchy be updated in a companion
   PR to use whatever this package declares, or should that be left as a
   separate follow-up?
