---
status: approved
issue: 32
intent: intent/2026-09-24-32-untrusted-data.md
---

# Spec: Harden handling of untrusted GitHub data and declare runtime dependencies

## Design

### Scope

This design targets the code after PR #28 (`fix/24-helper-errors`) merges. That PR changes the helper's error envelope and the start-failure handling in `ActionsPanel.qml`. It does not change the success path of `read_page()` or `openBrowser()`, so nothing below depends on its details. No new dependencies are added, the panel remains read-only, the API endpoints stay the same, and the Git install is unchanged. The work touches four code files plus tests: `actions.py`, `ActionsModel.js`, `ActionsPanel.qml` and `flake.nix`.

### Cleaning text in actions.py

Add one standard-library helper next to `repo_name()`:

```python
JOINERS = "‌‍"  # ZWNJ, ZWJ: kept, see below

def plain(value):
    if not isinstance(value, str):
        return value
    text = " ".join(value.replace("\t", " ").splitlines())
    return "".join(c for c in text if c in JOINERS or unicodedata.category(c) not in ("Cc", "Cf"))
```

- `str.splitlines()` splits on every Unicode line boundary: `\n`, `\r`, `\r\n`, `\v`, `\f`, `\x1c`–`\x1e`, `\x85`, U+2028 and U+2029. Joining the parts with a space turns each line break into a space, and a tab also becomes a space. Neither change joins two words together.
- Everything else in Cc (C0, DEL, C1) and Cf is removed, with no visible marker. Cf covers the bidi embeddings, overrides and isolates U+202A–U+202E and U+2066–U+2069, the marks LRM, RLM and ALM, the BOM, the soft hyphen, and tag characters.
- Non-strings pass through unchanged, so a missing or `null` field keeps its current meaning.

`read_page()` applies `plain` once, on the success path only, after the existing shape checks and before `result["data"]` is returned. It cleans exactly these fields for each page kind:

| Page kind | Container | Fields cleaned |
| --- | --- | --- |
| `catalogue` | each built repo dict | `description` |
| `activity`, `summary` | each row of `workflow_runs` | `name`, `display_title`, `head_branch` |
| `run` | the run dict | `name`, `display_title`, `head_branch` |
| `jobs` | each row of `jobs`, and each dict in its `steps` | job `name`, step `name` |

These are the only GitHub strings that `ActionsModel.rows()` shows or searches. The helper never cleans identity or control fields:
- `id`, `run_number` and `number`
- `repo`, which `repo_name()` already limits to `[A-Za-z0-9_.-]`
- `html_url`, which is checked separately below
- `status`, `conclusion` and the timestamps, which are GitHub enums or values the model compares

Error text is already fixed in the helper. `ActionsModel.js` searches the cleaned values, so the text that matches a search is the same text the row displays.

The helper's older whole-operation modes (`repositories`, `activity`, `summary`, `jobs`) are not used by the panel, which calls only `page`. They are left unchanged.

### Keeping ZWJ and ZWNJ

U+200D (ZWJ) and U+200C (ZWNJ) are in Cf, but they are kept:

- ZWJ joins emoji sequences such as 👨‍👩‍👧 and 🏳️‍🌈. Both characters are also needed to spell words correctly in Indic scripts, Persian and Arabic.
- They cannot reorder text. At most, they change how two neighbouring glyphs join.
- They could hide inside a branch name, so that `ma‍in` looks like `main`. That gives an attacker nothing new: a fork's pull request can already name its branch `main`.

Every other Cf character is removed.

### Browser URL check

Move the check out of `ActionsPanel.qml` into `ActionsModel.js`, where Node can test it:

```js
function browsable(url) {
    return typeof url === "string" && /^https:\/\/github\.com\/[^\s\x00-\x1f\x7f-\x9f]+$/.test(url);
}
```

`openBrowser()` then calls `Model.browsable(current.url)` before `Quickshell.execDetached(["xdg-open", current.url])`. Each part of the regex has a reason:

- **The trailing `/` in the prefix.** It ends the host, so `https://github.com.evil.example/` and `https://github.com@evil.example` are rejected. Anything after it belongs to the path on github.com.
- **`[^\s ...]`.** JS `\s` matches ASCII whitespace plus U+00A0, U+FEFF, U+2028/U+2029 and the other Unicode spaces. A desktop helper that re-splits its argument, for example by substituting `%s` into a command line, can't be handed a second word or a second line.
- **`\x00-\x1f\x7f-\x9f`.** These are all the Cc controls: C0, DEL and C1. `\s` covers only some of them, so they are listed explicitly. This is the same set the Python side removes as Cc.
- **`+$` with no `m` flag.** The path can't be empty, and `$` anchors to the end of the whole string, not the end of a line.

Repository rows build their URL as `"https://github.com/" + repo + "/actions"` from a validated name, so they always pass. Run and job rows use GitHub's `html_url`. A URL that fails the check is ignored silently, as it is today.

### Declaring runtime dependencies

In `flake.nix`, the package's attribute set gains one line:

```nix
default = pkgs.runCommand "nixarchy-ghtui-${version}" {
  inherit version;
  passthru.runtimeDeps = [ pkgs.gh pkgs.python3 pkgs.xdg-utils ];
} '' ... '';
```

The package is otherwise unchanged:
- The copied files stay byte-for-byte the same, with no store-path substitution.
- The `runtimeFiles` check and the Git install are unchanged.
- `bash`, which runs `keybindings.sh`, is left out because it is part of every NixOS system.

In the README's Nix example, one sentence notes that the package exposes this list as `runtimeDeps`. The explicit `home.packages` line stays.

Changing nixarchy to read `runtimeDeps` is a separate follow-up issue in `olafkfreund/nixarchy`. nixarchy copies our package with `cp -r`, which drops `passthru`. It will need to read `inputs.nixarchy-ghtui.packages.<system>.default.runtimeDeps` directly.

## Alternatives rejected

- **Cleaning in `ActionsModel.js`:** every row build and search would repeat the work. It would also need Unicode property escapes in the QML JS engine. Python's `unicodedata` does it once, before the data crosses into QML.
- **A visible replacement such as U+FFFD:** this was the user's choice. The marker would clutter titles that use harmless formatting characters, such as a soft hyphen.
- **Cleaning every string in the reply recursively:** this would touch identity and enum fields, such as `html_url`, `status` and `conclusion`. An explicit field list keeps the change auditable.
- **Also removing Co, Cn and Cs:** private-use and unassigned characters can't reorder text or fake a status. Keeping to Cc/Cf follows the approved scope.
- **Rebuilding the URL in Python:** the regex in QML is the only place a URL reaches `xdg-open`, which makes it the smallest boundary to guard.
- **Substituting store paths for `python3`, `gh` and `xdg-open`:** the Nix and Git installs would stop matching, the `runtimeFiles` check would need exceptions, and the closure would grow. This was rejected with the intent.

## Risks

- **Remaining RTL reordering.** A branch or title in naturally right-to-left script, such as Hebrew or Arabic, still gets normal Unicode reordering within its own `Text`. Only override and isolate characters are removed. Status and duration are drawn in separate `Text` items, so reordering can't move a status into the subtitle. The run subtitle joins branch, number and title in one string, so its order may look different with RTL text. This is accepted.
- **Lost tag-character flags.** Removing Cf also removes tag characters, so subdivision flags such as 🏴󠁧󠁢󠁳󠁣󠁴󠁿 show as a plain black flag. This is accepted.
- **Changed text for users.** A title with an intentional line break now shows on one line. Searching for text that only matched across a removed control character no longer finds it.
- **Merge overlap with #28.** Both touch `actions.py` and `ActionsPanel.qml`. Implementation starts from `main` after #28 merges, so the diff is made against the new code.
- **An unused `runtimeDeps`.** Nothing reads it until nixarchy's follow-up lands, and a `cp -r` consumer never sees it. It documents the dependencies but enforces nothing.

## Verification

- **`tests/test_actions.py`:** patch `actions.request` to return one HTTP reply for each page kind. Use `display_title` = `"fix‮ sseccus\ntwo"`, `head_branch` = `"ma​in\x07"`, a job name containing `\x1b[31m` and a step name containing ` `. Assert that each cleaned field has no Cc/Cf characters and no line breaks, and that line breaks became spaces. Assert that `"👨‍👩‍👧"` and `"می‌خواهم"` come through unchanged. Assert that `id`, `html_url`, `status` and the `repo` of a catalogue row are unchanged.
- **`tests/model.cjs`:**
  - `browsable` accepts `https://github.com/o/r/actions/runs/1`.
  - It rejects `https://github.com.evil.example/`, `https://github.com/`, `https://github.com/o/r x`, `https://github.com/o/r\n`, `https://github.com/o r`, `https://github.com/o\x85r`, `http://github.com/o`, and non-string values.
- **`nix eval --json .#packages.x86_64-linux.default.runtimeDeps --apply 'map (p: p.pname)'`** prints `["gh","python3","xdg-utils"]`.
- **`nix flake check`** passes unchanged. This covers the unit tests, the Node tests, the `runtimeFiles` list and the QML smoke test.
- **Manual:** on a desktop with the panel installed, press `o` on a run row and a job row to open them in the browser. Confirm that ordinary titles, branches and descriptions look the same as before.
