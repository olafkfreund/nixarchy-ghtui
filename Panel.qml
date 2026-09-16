import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "Model.js" as Model

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property var targetScreen: null
    property var repositories: ["olafkfreund/nixarchy"]
    property var repos: []
    property var details: ({})
    property var expanded: ({})
    property var entries: []
    property int cursor: 0
    property string filterText: ""
    property bool filtering: false
    property string error: ""
    property string updated: ""
    property double now: Date.now()
    property int failures: 0
    property int jobFailures: 0
    property string jobKey: ""
    property bool loading: summaryProc.running || jobsProc.running
    readonly property var current: entries[cursor] || null
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("actions.py").toString().replace(/^file:\/\//, ""))

    function open(payload) {
        var monitor = Hyprland.focusedMonitor
        targetScreen = null
        for (var i = 0; i < Quickshell.screens.length; i++)
            if (monitor && Quickshell.screens[i].name === monitor.name) targetScreen = Quickshell.screens[i]
        opened = true
        refresh()
        Qt.callLater(function() { keys.forceActiveFocus() })
    }
    function close() {
        opened = false
        summaryTimer.stop()
        jobsTimer.stop()
        summaryProc.running = false
        jobsProc.running = false
    }
    function toggle() { opened ? close() : open("{}") }

    function rebuild() {
        var key = current ? current.key : ""
        entries = Model.rows(repos, expanded, details, filterText, now)
        cursor = Model.selection(entries, key, cursor)
        Qt.callLater(function() { list.positionViewAtIndex(root.cursor, ListView.Contain) })
    }
    function move(delta) {
        cursor = Math.max(0, Math.min(entries.length - 1, cursor + delta))
        list.positionViewAtIndex(cursor, ListView.Contain)
        jobsTimer.restart()
    }
    function expand(collapse) {
        var row = current
        if (!row) return
        var next = Object.assign({}, expanded)
        if (collapse) {
            if (next[row.key]) delete next[row.key]
            else { cursor = Model.selection(entries, row.parent, cursor); return }
        } else if (["repo", "run", "job"].indexOf(row.kind) >= 0) {
            next[row.key] = !next[row.key]
        }
        expanded = next
        rebuild()
        fetchJobs()
    }
    function configure(text) {
        try {
            var config = JSON.parse(text)
            var entry = (config.plugins || []).filter(function(p) { return p.id === "olafkfreund.github-actions" })[0]
            var names = entry && entry.repositories !== undefined ? entry.repositories : ["olafkfreund/nixarchy"]
            if (!Array.isArray(names) || !names.length || names.some(function(name) { return typeof name !== "string" || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(name) }))
                throw new Error("repositories must be a nonempty array of owner/repo names")
            repositories = names
            repos = names.map(function(name) { return repos.filter(function(r) { return r.repo === name })[0] || {repo: name} })
            var next = Object.assign({}, expanded)
            names.forEach(function(name) { if (next["repo:" + name] === undefined) next["repo:" + name] = true })
            expanded = next
            error = ""
            rebuild()
            if (opened) { summaryProc.running = false; refresh() }
        } catch (e) { error = "Configuration: " + e.message }
    }
    function refresh() {
        if (!opened || summaryProc.running) return
        summaryTimer.stop()
        summaryProc.command = ["python3", helper, "summary"].concat(repositories)
        summaryProc.running = true
    }
    function receiveSummary(text) {
        if (!opened) return
        try {
            var data = JSON.parse(text)
            if (data.error) throw new Error(data.error)
            if (!Array.isArray(data.repos)) throw new Error("Invalid workflow response")
            var failed = false
            repos = data.repos.map(function(repo) {
                if (repo.error) {
                    failed = true
                    var old = repos.filter(function(r) { return r.repo === repo.repo })[0]
                    return Object.assign({}, old || {}, repo)
                }
                return repo
            })
            error = failed ? "Some repositories unavailable — showing last known data" : ""
            failures = failed ? Math.min(failures + 1, 4) : 0
            if (!failed) updated = data.updated
            rebuild()
        } catch (e) { error = e.message; failures = Math.min(failures + 1, 4) }
    }
    function fetchJobs() {
        if (!opened || jobsProc.running) return
        var row = current
        if (!row || !row.run) return
        var key = row.repo + ":" + row.run
        if (!expanded[key]) return
        jobKey = key
        jobsProc.command = ["python3", helper, "jobs", row.repo, row.run]
        jobsProc.running = true
    }
    function receiveJobs(text) {
        if (!opened) return
        var next = Object.assign({}, details)
        try {
            var data = JSON.parse(text)
            if (data.error) throw new Error(data.error)
            if (!Array.isArray(data.jobs)) throw new Error("Invalid jobs response")
            next[jobKey] = data
            jobFailures = 0
        } catch (e) {
            next[jobKey] = Object.assign({}, next[jobKey] || {}, {error: e.message})
            jobFailures = Math.min(jobFailures + 1, 4)
        }
        details = next
        rebuild()
    }
    function statusColor(status) {
        if (["failure", "timed_out", "startup_failure", "error"].indexOf(status) >= 0) return Color.urgent
        if (status === "in_progress" || status === "success") return Color.accent
        return Color.menu.text
    }
    function openBrowser() {
        if (current && /^https:\/\/github\.com\//.test(current.url || ""))
            Quickshell.execDetached(["xdg-open", current.url])
    }

    Component.onCompleted: {
        repos = repositories.map(function(repo) { return {repo: repo} })
        expanded = {"repo:olafkfreund/nixarchy": true}
        rebuild()
    }
    FileView {
        path: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
        watchChanges: true
        printErrors: false
        onLoaded: root.configure(text())
        onFileChanged: reload()
    }
    Timer { id: summaryTimer; interval: 30000 * Math.pow(2, root.failures); onTriggered: root.refresh() }
    Timer { id: jobsTimer; interval: 5000 * Math.pow(2, root.jobFailures); onTriggered: { root.fetchJobs(); if (root.opened) restart() } }
    Timer { interval: 1000; running: root.opened; repeat: true; onTriggered: root.now = Date.now() }
    Process {
        id: summaryProc
        stdout: StdioCollector { onStreamFinished: root.receiveSummary(text) }
        stderr: StdioCollector {}
        onExited: { if (root.opened) summaryTimer.restart() }
    }
    Process {
        id: jobsProc
        stdout: StdioCollector { onStreamFinished: root.receiveJobs(text) }
        stderr: StdioCollector {}
        onExited: { if (root.opened) jobsTimer.restart() }
    }

    PanelWindow {
        id: window
        visible: root.opened
        screen: root.targetScreen
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "omarchy-github-actions"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

        BorderSurface {
            id: card
            anchors.centerIn: parent
            width: Math.min(Style.space(900), window.width - Style.gapsOut * 2)
            height: Math.min(Style.space(680), window.height - Style.gapsOut * 2)
            color: Color.menu.background
            radius: Style.cornerRadius
            borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
            padding: Style.spacing.panelPadding

            Item {
                id: keys
                anchors.fill: parent
                anchors.leftMargin: card.contentLeftInset
                anchors.rightMargin: card.contentRightInset
                anchors.topMargin: card.contentTopInset
                anchors.bottomMargin: card.contentBottomInset
                focus: true
                Keys.onPressed: function(event) {
                    event.accepted = true
                    if (root.filtering) {
                        if (event.key === Qt.Key_Escape) { root.filtering = false; root.filterText = "" }
                        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.filtering = false
                        else if (event.key === Qt.Key_Backspace) root.filterText = root.filterText.slice(0, -1)
                        else if (event.text && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) root.filterText += event.text
                        root.rebuild()
                        return
                    }
                    if (event.key === Qt.Key_Escape) {
                        if (root.filterText) { root.filterText = ""; root.rebuild() } else root.close()
                    } else if (event.key === Qt.Key_Down || event.key === Qt.Key_J) root.move(1)
                    else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) root.move(-1)
                    else if (event.key === Qt.Key_PageDown) root.move(8)
                    else if (event.key === Qt.Key_PageUp) root.move(-8)
                    else if (event.key === Qt.Key_Home) root.move(-root.entries.length)
                    else if (event.key === Qt.Key_End) root.move(root.entries.length)
                    else if (event.key === Qt.Key_Left || event.key === Qt.Key_H) root.expand(true)
                    else if ([Qt.Key_Right, Qt.Key_L, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space].indexOf(event.key) >= 0) root.expand(false)
                    else if (event.key === Qt.Key_Slash) root.filtering = true
                    else if (event.key === Qt.Key_R) { root.refresh(); root.fetchJobs() }
                    else if (event.key === Qt.Key_O) root.openBrowser()
                    else event.accepted = false
                }

                Column {
                    anchors.fill: parent
                    spacing: Style.spacing.md
                    Text {
                        width: parent.width
                        text: "GitHub Actions  ·  " + root.repositories.length + " repositories"
                        color: Color.menu.text
                        font { family: Style.font.menuFamily; pixelSize: Style.font.title; bold: true }
                        textFormat: Text.PlainText
                    }
                    Text {
                        width: parent.width
                        text: root.filtering || root.filterText ? "/ " + root.filterText + (root.filtering ? "▏" : "") : root.error || (root.loading ? "Refreshing…" : root.updated ? "Updated " + Math.max(0, Math.floor((root.now - Date.parse(root.updated)) / 1000)) + "s ago" : "Waiting for GitHub…")
                        color: root.error ? Color.urgent : Color.menu.text
                        opacity: 0.75
                        font { family: Style.font.menuFamily; pixelSize: Style.font.caption }
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                    Rectangle { width: parent.width; height: 1; color: Color.menu.border; opacity: 0.4 }
                    ListView {
                        id: list
                        width: parent.width
                        height: Math.max(0, parent.height - y - footer.height - Style.spacing.md)
                        clip: true
                        model: root.entries
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: list.width
                            height: modelData.subtitle ? Style.space(56) : Style.space(34)
                            color: index === root.cursor ? Color.menu.selectedBackground : "transparent"
                            radius: 0
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: Style.space(8) + modelData.depth * Style.space(18)
                                anchors.rightMargin: Style.space(8)
                                spacing: Style.spacing.sm
                                Text {
                                    width: Style.space(18)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Model.icon(modelData.status)
                                    color: root.statusColor(modelData.status)
                                    font { family: Style.font.menuFamily; pixelSize: Style.font.body }
                                }
                                Column {
                                    width: Math.max(0, parent.width - Style.space(26) - info.width - parent.spacing * 2)
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        width: parent.width
                                        text: (["repo", "run", "job"].indexOf(modelData.kind) >= 0 ? (root.expanded[modelData.key] ? "▾ " : "▸ ") : "") + modelData.title
                                        color: index === root.cursor ? Color.menu.selectedText : Color.menu.text
                                        font { family: Style.font.menuFamily; pixelSize: Style.font.body; bold: modelData.kind === "repo" }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                    Text {
                                        visible: !!modelData.subtitle
                                        width: parent.width
                                        text: modelData.subtitle || ""
                                        color: index === root.cursor ? Color.menu.selectedText : Color.menu.text
                                        opacity: 0.65
                                        font { family: Style.font.menuFamily; pixelSize: Style.font.caption }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                }
                                Text {
                                    id: info
                                    width: Math.min(implicitWidth, list.width * 0.35)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.kind === "repo" ? modelData.info : modelData.status + (modelData.info ? " · " + modelData.info : "")
                                    color: root.statusColor(modelData.status)
                                    font { family: Style.font.menuFamily; pixelSize: Style.font.caption }
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: root.entries.length === 0
                            text: "No matching repositories or workflows"
                            color: Color.menu.text
                            font { family: Style.font.menuFamily; pixelSize: Style.font.body }
                        }
                    }
                    Text {
                        id: footer
                        width: parent.width
                        text: "↑↓ / jk move   ←→ expand   / filter   r refresh   o GitHub   Esc close"
                        color: Color.menu.text
                        opacity: 0.65
                        font { family: Style.font.menuFamily; pixelSize: Style.font.caption }
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                }
            }
        }
    }
}
