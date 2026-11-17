#!/usr/bin/env bash
set -euo pipefail

keys() {
  cat <<'KEYS'
SUPER ALT + A → Open or close GitHub Actions
SUPER CTRL ALT + A → GitHub Actions keybindings
↓ / j → Next row (j only outside search editing)
↑ / k → Previous row (k only outside search editing)
Enter / Space → Expand or collapse repository, run or job
→ / l → Open a collapsed row, or enter an open one
← / h → Collapse or select parent
Page Down / Page Up → Move one screenful
Home / End / g / G → First or last row
Click → Select a row and expand or collapse it
/ → Search repositories and workflows; select existing query
↑ / ↓ while searching → Select a result without leaving search
Enter while searching → Expand selected result and resume navigation
Tab while searching → Resume navigation without expanding
Esc while searching → Clear search and resume navigation
Esc → Clear filter, then close
r → Refresh selected repository, expanded run and activity
Shift + R → Rediscover accessible repositories
o → Open selected repository, run or job on GitHub
v → Open the log of the selected failed run, job or step in a terminal
y → Copy the selected row's link (needs wl-copy)
? → This keybindings list
a → Rerun all jobs of the selected finished run (asks y/n)
f → Rerun failed jobs of the selected failed run (asks y/n)
c → Cancel the selected unfinished run (asks y/n)
y / n / Esc → Confirm or cancel a pending action; Enter does nothing
Ctrl / Alt / Meta combinations → Left alone
Search editing → Native cursor movement, selection, Backspace and Delete
KEYS
}

if [[ ${1-} == --print || ${1-} == -p ]]; then
  keys
else
  omarchy-shell shell hide olafkfreund.github-actions
  keys | omarchy-menu-select 'GitHub Actions keybindings' -- --width 1000 --height 650 >/dev/null
fi
