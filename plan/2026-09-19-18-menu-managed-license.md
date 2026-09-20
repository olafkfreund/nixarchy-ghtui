---
status: approved
issue: 18
spec: spec/2026-09-19-18-menu-managed-license.md
---

# Plan: the panel leaves the menu to nixarchy when nixarchy owns it, and ships its licence

## Approved decisions (from the spec)

- **One guard, first thing in `register_menu()`** (`menu.py:95`):
  `if Path(__file__).with_name('menu.managed').exists(): return`. Presence is
  the contract; the contents are never read. `register` then exits 0, writes
  nothing and creates nothing.
- **With the marker, the legacy-key migration doesn't run either**
  (`registered_menu`, `menu.py:60-80`). That is the intended trade, accepted in
  the intent: nixarchy owns the rows, and its manual tells users to delete
  their own copies. Without the marker, everything behaves as today.
- **`LICENSE` joins `runtimeFiles`** (`flake.nix:15-24`), and the `plugin`
  check gains an explicit `assert (root / 'LICENSE').is_file()`, because the
  existing file-list assertion compares the package against `runtimeFiles`
  itself and cannot catch the licence going missing.
- This is nixarchy-gltui#4's change in the panel the two repos share; nixarchy
  already ships the marker for this plugin (#804).

## Steps

1. `tests/test_menu.py`: add `test_managed_marker_leaves_menu_untouched` to
   `RegistrationTest`. In a temporary `HOME`, write
   `.config/omarchy/extensions/omarchy-menu.jsonc` holding a **legacy**
   `system.github-actions` row whose action points at this plugin's `menu.py`,
   plus one custom row; `patch.object(menu, '__file__', ...)` at a temporary
   directory containing `menu.example.json` (copied from the repo) and an empty
   `menu.managed`; call `register_menu()`; assert the file's bytes and `stat()`
   are unchanged, which proves neither the migration nor the insertion ran. A
   second case, with no menu file, asserts none is created.
   → Verify by running it **before** step 2: `python3 -m unittest
   tests.test_menu -v` must fail, because the legacy row is rewritten to
   `apps.github-actions`. Capture that output for the PR (§1).
2. `menu.py`: add the two-line guard at the top of `register_menu()`.
   → Verify with `python3 -m unittest discover -s tests -v`: the new case
   passes and every existing case, the migration ones included, still passes.
3. `flake.nix`: add `"LICENSE"` to `runtimeFiles`, and
   `assert (root / 'LICENSE').is_file()` to the `plugin` check's python block.
   → Verify with `nix flake check`. Prove the assertion bites by adding it
   first, without the `runtimeFiles` entry: the check must fail on the missing
   licence, then pass once the entry is added.
4. `README.md`: one sentence in the registration paragraph (around `:101`),
   saying a `menu.managed` file beside `menu.py` turns registration off, and
   that nixarchy ships one.
   → Verify by reading it; no test.
5. Open the PR: `Closes #18`, links to the intent, spec and plan, and the red
   output from steps 1 and 3. Note in the body that nixarchy #804 already
   ships the marker, so merging this is what makes it take effect.

## Tests

| Command | Expected | Its §1 break |
|---|---|---|
| `python3 -m unittest tests.test_menu -v` | all pass, including the new case | before step 2: the new case fails, the legacy row was migrated |
| `python3 -m unittest discover -s tests -v` | all pass | — (guards the no-marker path, migration included) |
| `nix flake check` | green | assertion added before the `runtimeFiles` entry: fails on the missing LICENSE |
| `python3 menu.py register` (run inside the check, no marker) | still writes the rows | — |

## Rollback

Revert the commit. The guard is additive: without the marker nothing changes,
so a revert only restores rewriting for nixarchy users, and menus already
written are unaffected. Dropping `LICENSE` from `runtimeFiles` only changes
what the package ships.
