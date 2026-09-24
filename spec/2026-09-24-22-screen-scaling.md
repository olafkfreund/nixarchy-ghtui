---
status: draft
issue: 22
intent: intent/2026-09-24-22-screen-scaling.md
---

# Spec: The panel follows the screen size

## Design

One new property, `fit`, in `ActionsPanel.qml`. It is the factor the panel
grows by over today's size to fill its share of the screen. The card size,
`textScale` and the fixed spacing inside the card all multiply by it. There
are no new files, settings or dependencies.

**Screen size.** `window` (`ActionsPanel.qml:213`) is anchored on all four
sides with `ExclusionMode.Ignore`, so `window.width` × `window.height` is the
logical size of the monitor it opened on, after Hyprland's monitor scale.
`open()` already puts the window on the focused monitor (`:44-48`), and the
card already clamps to `window.width`/`window.height` (`:227-228`). No
`ShellScreen` lookup is needed. Everything is in logical pixels, so a 4K
monitor at scale 2 is sized like a 1080p one, and Hyprland renders it sharp.

**The factor**, next to `textScale` (`:35`):

```qml
// ponytail: one factor for the card, text and spacing; the reference is today's 900×680 card
readonly property real fit: Math.max(1, Math.min(2,
    window.width * 0.6 / 900,
    window.height * 0.7 / 680))
readonly property real textScale: 1.5 * fit
```

- **Share: 60% of the width and 70% of the height, whichever runs out
  first.** Scaling both sides by the same factor keeps today's 900:680
  proportions. On an ultra-wide screen the height runs out first, so the
  height limit is also the width cap: 3440×1440 gets the same panel as
  2560×1440. With the default theme, today's card is 47% × 63% of a
  1920×1080 screen. At 60/70, 1080p stays close to today (×1.11), which keeps
  the screenshots valid, and larger screens grow.
- **Minimum 1: today's size.** The existing clamp to
  `window.width - Style.gapsOut * 2` still applies on screens smaller than
  that.
- **Maximum 2: text at 3× the theme font** (1.5 × 2). At that point a 4K
  monitor at scale 1 gets a 1800×1360 card, 47% × 63% of the screen, the same
  proportion 1080p has today. Past 2× only the empty space would grow. The
  body text would already be 36 px on the default 12 px base.
- **The theme font size and the screen scale multiply.** `fit` is measured
  against the raw logical 900×680, not `Style.space()`, so it depends only on
  the screen. Text is `Style.font.* × 1.5 × fit` and the card is
  `Style.space(900|680) × fit`. Both follow `base-size` exactly as they do
  today, and `fit` multiplies on top. The card is never smaller than it is
  today. The clamp to the screen minus `Style.gapsOut * 2` bounds the card
  when a large theme font and a large screen together would overflow it.

| Logical screen (default 12 px `base-size`; a larger base grows the card and clamps it to the screen) | `fit` | Card |
| --- | --- | --- |
| 1366×768 | 1 (clamped) | 900×680, clamped to the screen minus gaps as today |
| 1920×1080 (or 4K at scale 2) | 1.11 | 1000×756 |
| 2560×1440, 3440×1440 | 1.48 | 1334×1008 |
| 3840×2160 at scale 1 | 2 (cap) | 1800×1360 |

**Card size** (`:227-228`):

```qml
width: Math.min(Style.space(900) * root.fit, window.width - Style.gapsOut * 2)
height: Math.min(Style.space(680) * root.fit, window.height - Style.gapsOut * 2)
```

**Text.** Every `pixelSize` already multiplies by `root.textScale`
(`:270, 278, 335, 344, 354, 365, 376, 385`), and the search field height
follows its font (`:276`). These lines are unchanged.

**Spacing inside the card.** Each fixed `Style.space(n)` becomes
`Style.space(n * root.fit)`: the row heights and their padding (`:322`), the
row margins and depth indent (`:327-328`), the icon column (`:331`) and its
reserved width (`:338`). `Style.space()` accepts fractional input and
rounds, so every call still goes through the theme's spacing scale. The
spacing tokens become `Math.round(Style.spacing.X * root.fit)`: `panelPadding`
(`:232`), `md` (`:265, 313`) and `sm` (`:329`). A token pinned by the theme
therefore still applies, and grows with the panel.

**Divider** (`:309`): `height: 1` becomes `height: Style.space(root.fit)`.
That is `Style.spacing.hairline` (`space(1)`) grown by the same factor, so
it stays at least 1 px.

**Kept as they are:** the border width (`:231`) and `Style.cornerRadius`
(`:230`). They match the other Omarchy menus, and the intent requires the
theme border and corner radius.

**Other monitors.** `fit` is a binding on `window.width`/`height`, so it
updates when `targetScreen` changes on `open()`, or when the monitor's mode
or scale changes while the panel is open. While the window is hidden and has
no size, `fit` is 1, which does no harm.

**README line 3.** Replace "Text uses 1.5× theme font sizes with matching row
heights." with: "The panel takes up to 60% of the screen's width and 70% of
its height, never smaller than 900×680 theme units where the screen allows;
text, rows and spacing grow with it, from 1.5× up to 3× the theme font sizes."

## Alternatives rejected

- **A user setting (environment variable or menu option) for size or text
  scale.** The intent asks the panel to follow the screen, not to be
  configured. The theme's `base-size` and `[spacing] scale` and Hyprland's
  monitor scale are already the controls. A setting would add parsing,
  documentation and a test, with no request for any of them.
- **Keeping `textScale` fixed at 1.5 and growing only the card.** A bigger
  box with the same small text leaves the extra space empty. The intent asks
  for text and rows to keep their proportions.
- **Physical pixels (`devicePixelRatio`, `physicalPixelDensity`).** Hyprland
  already applies the monitor scale to layer-shell surfaces. Sizing in
  physical pixels would apply it a second time: a 4K monitor at scale 2 would
  get a huge panel. Logical size is what the user chose with the monitor
  scale.
- **Separate width and height factors.** They would stretch the card on
  ultra-wide screens, and text can only follow one factor. The smaller of the
  two keeps the proportions and caps the width at the same time.
- **Scaling against a fixed reference resolution such as 1920×1080.** That is
  the same ratio with an arbitrary constant. Today's 900×680 card is the
  natural reference.
- **Measuring `fit` against `Style.space(900|680)`.** `Style.space()`
  includes `Style.fontScale`, so a larger `base-size` would lower `fit` by
  the same amount and cancel out. For 1 < `fit` < 2 the text would not change
  with the theme font size, which breaks an intent constraint.
- **Scaling the border and corner radius as well.** These are theme tokens
  shared with the other Omarchy menus. Scaling them would make this panel
  look different from its siblings.

## Risks

- **Text layout.** Longer workflow names are elided sooner relative to the
  card, because text and card grow by the same factor. That is no worse than
  today. The `info` column is still capped at 35% of the list (`:361`).
- **A large theme font on a large screen.** The theme font and `fit`
  multiply, so the card reaches the screen clamp sooner than it does today.
  Nothing clips. Row heights are computed from the text size, so rows grow
  with the text. The list scrolls, and the header, search hint and footer
  elide. There are fewer rows on screen. With the default font, `fit` alone
  never reaches the clamp.
- **Rounding.** `Math.round` on tokens and `space()` can differ by 1 px from
  an exact product. That is invisible.
- **Screenshots.** At 1080p the panel is 11% larger, so `docs/img/` probably
  still reflects it. Retake them only if the manual check shows a visible
  difference.
- **Multi-monitor.** A binding loop is not possible: `fit` reads `window`
  size, and the window's size comes from its anchors, not from the card.

## Verification

Automated:

- `python3 tests/qml-smoke.py` still prints `QML_CHECKS_PASSED` for both
  scenarios. Keyboard navigation, search and polling are unchanged.
- **New assertion** in the smoke test's stage 1, where the panel is open on
  a real screen:
  `check(panel.fit>=1 && panel.fit<=2 && panel.textScale===1.5*panel.fit,"screen fit bounded")`.
  It fails if the factor is unbounded or if `textScale` stops following it.
  The smoke test runs `quickshell` against the live session, so it covers
  the monitor that runs it. It cannot simulate other resolutions.
- `nix flake check` is green. The `plugin` check's file list does not change.

Manual, because they need real monitors or Hyprland changes (`hyprctl
keyword monitor …`):

- 1920×1080 at scale 1: the card is about 1000×756 and the proportions are
  the same as today.
- 2560×1440 at scale 1: the card is about 1334×1008 and the text is visibly
  larger.
- 3840×2160 at scale 1: the card is 1800×1360 (cap) and the body text is
  about 36 px.
- 3840×2160 at scale 2: the same as 1080p at scale 1, and sharp.
- Open the panel on one monitor, close it, focus a monitor of a different
  size, reopen it: the panel resizes to the second monitor.
- Raise `base-size` in the theme: the text grows and the card never exceeds
  the screen minus gaps.
- On a laptop-sized screen (1366×768 or smaller) the panel fits with its
  gaps, as today.
