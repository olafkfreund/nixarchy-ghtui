"""Load the plugin in isolation; no visible window or desktop configuration edits."""
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
shell = Path(os.environ["OMARCHY_PATH"]) / "shell"
with tempfile.TemporaryDirectory(prefix="actions-qml-") as directory:
    root = Path(directory)
    for name in ("Commons", "Ui"):
        (root / name).symlink_to(shell / name)
    for name in ("ActionsPanel.qml", "ActionsModel.js", "actions.py"):
        (root / name).symlink_to(source / name)
    (root / "shell.qml").write_text('''
import QtQuick
import Quickshell
ShellRoot {
    ActionsPanel { id: panel }
    function check(value, label) { if (!value) throw new Error("CHECK FAILED: " + label) }
    Timer {
        interval: 1000; running: true
        onTriggered: {
            panel.configure('{"plugins":[{"id":"olafkfreund.github-actions","repositories":["one/repo","two/repo"]}]}')
            check(panel.entries.length === 2, "configured repositories")
            panel.repos = [{repo:"one/repo", runs:[{id:7, name:"CI", status:"in_progress", head_branch:"main", run_number:1}]}]
            panel.expanded = {"repo:one/repo":true}
            panel.rebuild()
            panel.move(1)
            check(panel.current.kind === "run", "keyboard selection")
            panel.expand(false)
            check(panel.entries[2].title === "Loading jobs…", "expand run")
            panel.expand(true)
            check(panel.entries.length === 2, "collapse run")
            panel.filterText = "no-match"
            panel.rebuild()
            check(panel.entries.length === 0, "filter")
            panel.filterText = ""
            panel.opened = true
            panel.nextPage = 1
            panel.receiveDiscovery('{"repos":[{"repo":"one/repo"}],"nextPage":2}')
            check(panel.nextPage === 2 && !panel.discoveryComplete, "repository pagination")
            panel.receiveDiscovery('{"repos":[{"repo":"two/repo"}],"nextPage":0}')
            check(panel.repositories.length === 2 && panel.discoveryComplete, "complete catalogue")
            panel.receiveActivity('{"repo":"two/repo","runs":[{"id":9,"name":"CI","status":"in_progress"}],"active":1,"updated":"2026-09-16T10:00:00Z"}')
            check(panel.entries[0].repo === "two/repo", "running repository first")
            panel.filterText = "repo"
            check(panel.cursor === 0 && panel.entries.length === 2, "search starts at first collapsed result")
            panel.move(1)
            var selected = panel.current.key
            panel.receiveActivity('{"repo":"two/repo","runs":[],"active":0,"updated":"2026-09-16T10:00:05Z"}')
            check(panel.current.key === selected && panel.filterText === "repo", "poll preserves searched selection")
            panel.expand(false)
            check(panel.expanded[selected], "searched result can expand")
            panel.receiveActivity('{"error":"Repository unavailable or Actions read permission missing"}')
            check(panel.scanFailures === 0, "permission error does not back off entire scan")
            panel.close()
            check(!panel.opened && !panel.loading, "close stops processes")
            console.log("QML_CHECKS_PASSED")
            Qt.quit()
        }
    }
}
''')
    result = subprocess.run(["quickshell", "-p", str(root), "--no-color"], capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    print(output)
    if result.returncode or "QML_CHECKS_PASSED" not in output or "ERROR:" in output or "ReferenceError" in output or "TypeError" in output:
        raise SystemExit("QML smoke check failed")
