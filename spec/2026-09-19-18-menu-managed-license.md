---
status: draft
issue: 18
intent: intent/2026-09-19-18-menu-managed-license.md
---

# Spec: the panel leaves the menu to nixarchy when nixarchy owns it, and ships its licence

## Design

The same change as nixarchy-gltui#4, whose code this panel shares.

**The marker check goes first in `register_menu()`** (`menu.py:95`), before
anything reads the menu file:

```python
if Path(__file__).with_name('menu.managed').exists():
    return
```

The panel runs `menu.py register` on every load (`ActionsPanel.qml:187`), and
the `__main__` dispatch (`menu.py:142`) is the only route into `register_menu`,
so this one guard covers every caller. With the marker present, `register`
exits 0, writes nothing and creates nothing. Presence is the contract; the
contents are never read. Without the marker, nothing changes: the symlink and
`/nix/store` refusal (`menu.py:98-99`), the legacy-key migration in
`registered_menu` (`:60-80`) and the row insertion all run as today.

**LICENSE is added to `runtimeFiles`** (`flake.nix:15-24`), so the package ships
it. The `plugin` check's file-list assertion (`flake.nix:51`) compares the
package against that same list, so it can't notice LICENSE going missing. The
check therefore gets one explicit line, `assert (root / 'LICENSE').is_file()`.

## Alternatives rejected

- **An environment variable set by nixarchy.** The panel's environment comes
  from the shell, not the package. The file travels with the package, and
  nixarchy already ships it (#804).
- **Removing `register`.** Standalone installs rely on it, including the legacy
  migration for users upgrading from `system.github-actions`.

## Risks

- **With the marker, the legacy migration doesn't run either.** A nixarchy user
  who still has an old `system.github-actions` or `github-actions` row keeps it
  next to nixarchy's `apps.github-actions`. That's the intended trade: nixarchy
  owns the rows, and its manual tells users to delete their own copies (as
  #786 did for gltui).
- **A stray `menu.managed` in a standalone checkout** silences registration. The
  README names the marker.

## Verification

- **New test** in `tests/test_menu.py` `RegistrationTest`,
  `test_managed_marker_leaves_menu_untouched`: in a temporary `HOME`, write a
  menu file containing a legacy `system.github-actions` row pointing at this
  plugin's `menu.py`, plus a custom row. Point `menu.__file__` at a temporary
  directory holding `menu.managed`, call `register_menu()`, and assert the file
  is byte-for-byte unchanged, so neither the migration nor the insertion ran. A
  second case with no menu file asserts none is created.
  - **Red first:** on today's `menu.py` it fails, because the legacy row is
    renamed and the bytes differ.
- **Package:** the `plugin` check with the explicit `LICENSE` assertion.
  - **Red first:** add the assertion before adding `LICENSE` to `runtimeFiles`,
    and the check fails.
- `nix flake check` green; `python3 -m unittest discover -s tests` green.
