---
status: approved
issue: 32
spec: spec/2026-09-24-32-untrusted-data.md
---

# Plan: Harden handling of untrusted GitHub data and declare runtime dependencies

## Approved decisions

- **Scope:** the change touches `actions.py`, `ActionsModel.js`,
  `ActionsPanel.qml`, `flake.nix`, one README sentence, and tests. There are
  no new dependencies, no new endpoints and no writes to GitHub. The Git
  install is unchanged.
- **Text cleaning** happens in `actions.py`, once, before the JSON reaches
  QML, using the standard library only:

  ```python
  import unicodedata

  JOINERS = "‌‍"  # ZWNJ, ZWJ: kept, see below

  def plain(value):
      if not isinstance(value, str):
          return value
      text = " ".join(value.replace("\t", " ").splitlines())
      return "".join(c for c in text if c in JOINERS or unicodedata.category(c) not in ("Cc", "Cf"))
  ```

  - Line breaks (everything `splitlines()` splits on, including `\x85`,
    U+2028 and U+2029) and tabs become spaces.
  - All other Cc and Cf characters are removed silently, with no marker.
  - Values that aren't strings pass through unchanged.
- **ZWJ (U+200D) and ZWNJ (U+200C) are kept.**
  - Emoji sequences and Indic, Persian and Arabic text need them.
  - They can't reorder text.
  - Hiding one in a branch name gains an attacker nothing, since a fork's
    pull request can already call its branch `main`.
- **Where cleaning applies:** `read_page()` calls `plain` only when the
  request succeeds, after the existing shape checks, on exactly these fields:

  | Page kind | Container | Fields cleaned |
  | --- | --- | --- |
  | `catalogue` | each built repo dict | `description` |
  | `activity`, `summary` | each row of `workflow_runs` | `name`, `display_title`, `head_branch` |
  | `run` | the run dict | `name`, `display_title`, `head_branch` |
  | `jobs` | each row of `jobs`, and each dict in its `steps` | job `name`, step `name` |

- **Fields never touched:** `id`, `run_number`, step `number`, `repo`,
  `html_url`, `status`, `conclusion`, timestamps, and error text (which is
  already fixed).
- **URL check:** `ActionsModel.js` gains `browsable(url)`, and
  `openBrowser()` in `ActionsPanel.qml` calls it before `xdg-open`. It
  replaces the current prefix-only test. The regex:

  ```js
  function browsable(url) {
      return typeof url === "string" && /^https:\/\/github\.com\/[^\s\x00-\x1f\x7f-\x9f]+$/.test(url);
  }
  ```

  - The trailing `/` pins the host.
  - `\s` blocks Unicode whitespace and line separators.
  - The explicit ranges cover every Cc control character.
  - `+$` without the `m` flag requires a path and anchors at the end of the
    whole string.
  - A URL that fails the check is ignored silently, as it is today.
- **Runtime dependencies:** `flake.nix` adds
  `passthru.runtimeDeps = [ pkgs.gh pkgs.python3 pkgs.xdg-utils ];` to the
  package's attribute set.
  - There's no store-path substitution.
  - The `runtimeFiles` check is unchanged.
  - `bash` stays out, because it is part of every NixOS system.
  - The README's Nix example gains one sentence about `runtimeDeps` and
    keeps its explicit `home.packages` line.
- **nixarchy:** changing nixarchy to read `runtimeDeps` is a separate
  follow-up issue in `olafkfreund/nixarchy`, not part of this work.
- **Old helper modes:** the spec left them alone. The PR for #31 deletes
  them, so after step 0 that note no longer applies. Only `read_page()` is
  left to change.
- **Accepted risks:**
  - Naturally right-to-left text still reorders within the run subtitle.
  - Tag-character flags show as a plain black flag.
  - Titles with deliberate line breaks show on one line.

## Steps

0. **Precondition: land the earlier PRs, then rebase.**
   - These must be merged into `main`:
     - #26 (theme text size)
     - #27 (live timers)
     - #28 (helper errors)
     - the PR closing #31, which removes the old `actions.py` modes
   - Ideally the PR closing #30 is merged too, because it changes
     `read_page()`. If #30 is still open, go ahead and note the expected
     conflict on #30.
   - Then run `git fetch origin && git rebase origin/main` on
     `fix/32-untrusted-data`.
   - Verify:
     - `gh pr view 26 27 28 --json state` (one at a time) reports `MERGED`,
       and so do the #31 PR and, ideally, the #30 PR.
     - `git log origin/main..` shows only the artifact commits for #32.
     - `grep -n '"summary", "jobs", "repositories", "activity"' actions.py`
       finds nothing, which confirms the old modes are gone.
     - `python3 -m unittest discover -s tests` passes on the rebased tree.
1. **`tests/test_actions.py`: add the failing text-cleaning test.** Add
   `test_page_text_is_plain`, which patches `actions.request` to return one
   `HTTP/2 200` reply for each page kind (`catalogue`, `summary`, `run`,
   `jobs`) and uses these hostile values:

   | Field | Value |
   | --- | --- |
   | `display_title` | `"fix‮ sseccus\ntwo"` |
   | `head_branch` | `"ma​in\x07"` |
   | run `name` | `"a\tb"` |
   | job `name` | `"x\x1b[31my"` |
   | step `name` | `"s t"` |
   | `description` | `"d⁦e\r\nf"` |

   It asserts:
   - The cleaned values are `"fix sseccus two"`, `"main"`, `"a b"`,
     `"x[31my"`, `"s t"` and `"de f"`.
   - `"👨‍👩‍👧"` and `"می‌خواهم"` in `display_title` and
     `description` come through unchanged.
   - `id`, `html_url`, `status`, `conclusion` and the catalogue `repo` are
     identical to the input.

   Verify by `python3 -m unittest tests.test_actions -k plain`, which fails
   on the unchanged values.
2. **`actions.py`: add cleaning.**
   - Add `import unicodedata`, plus `JOINERS` and `plain()` next to
     `repo_name()`.
   - In `read_page()`, on the success path only, clean the fields in the
     table:
     - `catalogue`: `"description": plain(row.get("description") or "")`.
     - Run rows (`summary`, `activity`) and the `run` dict: clean `name`,
       `display_title` and `head_branch` when the key is present.
     - Jobs: clean each row's `name`, and for each `step` that is a dict,
       its `name`.
   - Verify by the step 1 test passing, and the whole suite with
     `python3 -m unittest discover -s tests -v`.
3. **`tests/model.cjs`: add the failing URL test.** Assert that
   `model.browsable`:
   - accepts `https://github.com/o/r/actions/runs/1`
   - rejects `https://github.com.evil.example/`,
     `https://github.com@evil.example`, `https://github.com/`,
     `https://github.com/o/r x`, `"https://github.com/o/r\n"`,
     `"https://github.com/o r"`, `"https://github.com/o\x85r"`,
     `http://github.com/o`, `undefined` and `5`

   Verify by `node tests/model.cjs`, which fails because `browsable` is not
   a function.
4. **`ActionsModel.js`: add `browsable(url)`.** Use the exact function from
   the approved decisions. Verify by `node tests/model.cjs` exiting 0.
5. **`ActionsPanel.qml`: use `browsable` in `openBrowser()`.** Change it to
   `if (current && Model.browsable(current.url)) Quickshell.execDetached(["xdg-open", current.url])`.
   Verify:
   - `grep -n 'github\\.com' ActionsPanel.qml` shows no regex left in QML.
   - `python3 tests/qml-smoke.py <plugin dir>` passes. It runs through
     `nix flake check` in step 7.
6. **`flake.nix` and `README.md`: declare `runtimeDeps`.**
   - `flake.nix`: add
     `passthru.runtimeDeps = [ pkgs.gh pkgs.python3 pkgs.xdg-utils ];`
     next to `inherit version;`.
   - `README.md`: after the Nix example, add "The package lists these as
     `passthru.runtimeDeps` (`gh`, `python3`, `xdg-utils`)."
   - Verify by
     `nix eval --json .#packages.x86_64-linux.default.runtimeDeps --apply 'map (p: p.pname)'`,
     which prints `["gh","python3","xdg-utils"]`, and by
     `nix build .#packages.x86_64-linux.default` producing the same file
     list as before (`ls result`).
7. **Full checks.** Verify by `nix flake check`, which should be green. It
   runs the unit tests, the Node tests, the `runtimeFiles` assertion and the
   QML smoke test.
8. **Commit and open the PR.**
   - Commit with `fix: harden untrusted GitHub text and URL, declare runtime deps (#32)`.
   - Push `fix/32-untrusted-data`, then open a PR that links the intent,
     spec and plan and says `Closes #32`.
   - Verify by `gh pr view --json url`.
9. **Open the nixarchy follow-up issue.**
   - Run `gh issue create --repo olafkfreund/nixarchy` with the title "Read
     nixarchy-ghtui's runtimeDeps instead of repeating gh/python3/xdg-utils".
   - The body says that `modules/home.nix` copies the package with `cp -r`,
     which drops `passthru`. The `github` plugin's `packages` list (around
     line 1664) can use
     `inputs.nixarchy-ghtui.packages.${system}.default.runtimeDeps`. The same
     applies to `nixarchy-gltui` once it ports this.
   - Link it from the #32 PR. Verify by the issue URL.
10. **Live check, run by the lead.** On a desktop running this branch, open
    the panel. Then:
    - Select a run and press `o`. Its Actions run page opens in the browser.
    - Select a job and press `o`. The job page opens.
    - Ordinary titles, branches and descriptions look the same as before.

    Record the result on the PR. Verify by the lead's comment on the PR.

## Deviations

1. **Host (user rule).** All desktop testing happens on razer, never on
   p620. The step 5 `tests/qml-smoke.py` run with a real plugin directory
   takes place on razer:
   - from a scratch `/tmp` clone of this branch
   - inside razer's session environment, by importing the whole `environ`
     of the `.quickshell-wrapped_ -n` process, including `OMARCHY_PATH`
   - after checking `#agents` for claims and posting a CLAIM, with "done"
     posted afterwards

   razer's shell is never restarted, and its `~/.config/omarchy/plugins` is
   never touched. `nix flake check` on p620 still runs the sandboxed
   invalid-directory smoke case, which needs no desktop.
2. **#30 landed before this work.** Status pages (`activity`, and `summary`
   with an unfinished status) now return `total` and never follow next
   links. Only `catalogue` and `jobs` still do. Cleaning is independent of
   this. The step 1 test covers `activity`, `summary`/`queued` and
   `summary`/`recent` pages, each carrying `total_count`.
3. **#31 landed before this work.** `main()` accepts only `page`. Step 0's
   check is therefore `grep -n 'choices=("page",)' actions.py`, which should
   match.
4. **Implementation detail.** A small `plain_fields(row, fields)` and
   `RUN_TEXT = ("name", "display_title", "head_branch")` avoid repeating
   the field list for run rows and the run dict. Steps that aren't dicts are
   skipped. The step 1 test includes one such step, because `read_page`
   checks only that `steps` is a list.
5. **Commits.** There are three commits, not one: steps 1–2 (with this plan
   update), steps 3–5, and step 6. This keeps red/green evidence per
   change. The PR is the same.

## Tests

```sh
python3 -m unittest discover -s tests -v            # all pass, including test_page_text_is_plain
node tests/model.cjs && node tests/polling.cjs      # exit 0, including browsable cases
nix eval --json .#packages.x86_64-linux.default.runtimeDeps --apply 'map (p: p.pname)'
                                                    # ["gh","python3","xdg-utils"]
nix flake check                                     # green
```

The lead's `o` check on a run and a job (step 10) is recorded on the PR.

## Rollback

- Code: revert the `fix:` commit or don't merge the PR. No state, config or
  data is migrated, so a revert is complete.
- `runtimeDeps` is additive. Nothing reads it until the nixarchy follow-up
  lands, so removing it breaks nothing here. If nixarchy has adopted it by
  then, revert that nixarchy change first or keep the attribute.
- nixarchy follow-up: close the issue if this PR is not merged.
