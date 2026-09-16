import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "ActionsModel.js" as Model

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property var targetScreen: null
    property var repositories: []
    property var repos: []
    property var details: ({})
    property var expanded: ({})
    property var entries: []
    property int cursor: 0
    property string filterText: ""
    property bool filtering: false
    property string error: ""
    property string updated: ""
    property string discoveryError: ""
    property string scanError: ""
    property int nextPage: 1
    property bool discoveryComplete: false
    property int scanCursor: 0
    property int scanTurns: 0
    property int scanFailures: 0
    property string scanningRepo: ""
    property double catalogueUpdated: 0
    property double now: Date.now()
    property int failures: 0
    property int jobFailures: 0
    property string jobKey: ""
    property bool loading: discoveryProc.running || summaryProc.running || jobsProc.running
    readonly property int checkedCount: repos.filter(function(repo) { return !!repo.checked || repo.archived || repo.disabled }).length
    readonly property real textScale: 1.5
    readonly property var current: entries[cursor] || null
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("actions.py").toString().replace(/^file:\/\//, ""))

    function open(payload) {
        var monitor = Hyprland.focusedMonitor
        targetScreen = null
        for (var i = 0; i < Quickshell.screens.length; i++)
            if (monitor && Quickshell.screens[i].name === monitor.name) targetScreen = Quickshell.screens[i]
        opened = true
        if (!discoveryComplete || Date.now() - catalogueUpdated > 300000) {
            nextPage = 1
            discoveryComplete = false
            discover()
        }
        refresh()
        scanTimer.restart()
        Qt.callLater(function() { keys.forceActiveFocus() })
    }
    function close() {
        opened = false
        summaryTimer.stop()
        jobsTimer.stop()
        discoveryTimer.stop()
        scanTimer.stop()
        summaryProc.running = false
        jobsProc.running = false
        discoveryProc.running = false
        activityProc.running = false
    }
    function toggle() { opened ? close() : open("{}") }
    function status() {
        return JSON.stringify({opened: opened, rows: entries.length, repositories: repositories.length,
            checked: checkedCount, discoveryComplete: discoveryComplete, error: error || discoveryError || scanError, updated: updated})
    }

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
        if (row.kind === "repo" && next[row.key]) refresh()
        fetchJobs()
    }
    function configure(text) {
        try {
            var config = JSON.parse(text)
            var entry = (config.plugins || []).filter(function(p) { return p.id === "olafkfreund.github-actions" })[0]
            // Existing configured repos are initial hints; discovery still lists all access.
            var names = entry && Array.isArray(entry.repositories) ? entry.repositories : []
            if (!repos.length && names.length) {
                repositories = names
                repos = names.filter(function(name) { return typeof name === "string" && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(name) }).map(function(name) { return {repo: name} })
            }
            error = ""
            rebuild()
        } catch (e) { error = "Configuration: " + e.message }
    }
    function discover() {
        if (!opened || discoveryProc.running || discoveryComplete) return
        discoveryProc.command = ["python3", helper, "repositories", String(nextPage)]
        discoveryProc.running = true
    }
    function rediscover() {
        if (discoveryProc.running) return
        nextPage = 1
        discoveryComplete = false
        discover()
    }
    function receiveDiscovery(text) {
        if (!opened) return
        try {
            var data = JSON.parse(text)
            if (data.error) throw new Error(data.error)
            if (!Array.isArray(data.repos)) throw new Error("Invalid repository response")
            var old = repos
            var combined = nextPage === 1 ? [] : repos.slice()
            data.repos.forEach(function(repo) {
                var previous = old.filter(function(r) { return r.repo === repo.repo })[0]
                if (!combined.some(function(r) { return r.repo === repo.repo }))
                    combined.push(Object.assign({}, previous || {}, repo))
            })
            repos = combined
            repositories = repos.map(function(repo) { return repo.repo })
            nextPage = data.nextPage
            discoveryComplete = nextPage === 0
            if (discoveryComplete) catalogueUpdated = Date.now()
            discoveryError = ""
            rebuild()
            if (!activityProc.running && !scanTimer.running) scanTimer.restart()
        } catch (e) { discoveryError = e.message }
    }
    function scan() {
        if (!opened || activityProc.running || !repos.length) return
        // One request per turn, alternating active rechecks with round-robin discovery.
        var candidates = repos.filter(function(repo) { return !repo.archived && !repo.disabled })
        if (!candidates.length) return
        var active = candidates.filter(function(repo) { return repo.active > 0 })
            .sort(function(a, b) { return Date.parse(a.checked || 0) - Date.parse(b.checked || 0) })
        var repo
        if (++scanTurns % 3 === 0 && active.length && Date.now() - Date.parse(active[0].checked) >= 30000) repo = active[0]
        else { repo = candidates[scanCursor % candidates.length]; scanCursor++ }
        scanningRepo = repo.repo
        activityProc.command = ["python3", helper, "activity", repo.repo]
        activityProc.running = true
    }
    function receiveActivity(text) {
        if (!opened) return
        try {
            var data = JSON.parse(text)
            if (data.error) throw new Error(data.error)
            if (!Array.isArray(data.runs)) throw new Error("Invalid activity response")
            repos = repos.map(function(repo) { return repo.repo === data.repo ? Model.mergeActivity(repo, data) : repo })
            scanFailures = 0
            scanError = ""
        } catch (e) {
            repos = repos.map(function(repo) { return repo.repo === scanningRepo ? Object.assign({}, repo, {error: e.message, checked: new Date().toISOString()}) : repo })
            var permissionError = e.message.indexOf("permission") >= 0 || e.message.indexOf("Repository unavailable") >= 0
            scanError = permissionError ? "" : e.message
            scanFailures = permissionError ? 0 : Math.min(scanFailures + 1, 7)
        }
        rebuild()
    }
    function refresh() {
        if (!opened || summaryProc.running) return
        if (!current) return
        summaryTimer.stop()
        summaryProc.command = ["python3", helper, "summary", current.repo]
        summaryProc.running = true
    }
    function receiveSummary(text) {
        if (!opened) return
        try {
            var data = JSON.parse(text)
            if (data.error) throw new Error(data.error)
            if (!Array.isArray(data.repos)) throw new Error("Invalid workflow response")
            var failed = false
            var incoming = data.repos.map(function(repo) {
                if (repo.error) {
                    failed = true
                    var old = repos.filter(function(r) { return r.repo === repo.repo })[0]
                    return Object.assign({}, old || {}, repo)
                }
                return Object.assign({}, repo, {active: repo.runs.filter(function(run) { return run.status === "in_progress" }).length,
                    checked: data.updated, history: true})
            })
            repos = repos.map(function(repo) {
                var replacement = incoming.filter(function(r) { return r.repo === repo.repo })[0]
                return replacement ? Object.assign({}, repo, replacement) : repo
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

    Component.onCompleted: rebuild()
    FileView {
        path: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
        watchChanges: true
        printErrors: false
        onLoaded: root.configure(text())
        onFileChanged: reload()
    }
    Timer { id: summaryTimer; interval: 30000 * Math.pow(2, root.failures); onTriggered: root.refresh() }
    Timer { id: discoveryTimer; interval: root.discoveryError ? 30000 : 100; onTriggered: root.discover() }
    Timer { id: scanTimer; interval: 2000 * Math.pow(2, root.scanFailures); onTriggered: root.scan() }
    Timer { id: jobsTimer; interval: 5000 * Math.pow(2, root.jobFailures); onTriggered: { root.fetchJobs(); if (root.opened) restart() } }
    Timer { interval: 1000; running: root.opened; repeat: true; onTriggered: root.now = Date.now() }
    Process {
        id: discoveryProc
        stdout: StdioCollector { id: discoveryOutput }
        stderr: StdioCollector { id: discoveryErrors }
        onExited: function(code) {
            root.receiveDiscovery(Model.reply(discoveryOutput.text, discoveryErrors.text, code))
            if (root.opened && !root.discoveryComplete) discoveryTimer.restart()
        }
    }
    Process {
        id: activityProc
        stdout: StdioCollector { id: activityOutput }
        stderr: StdioCollector { id: activityErrors }
        onExited: function(code) {
            root.receiveActivity(Model.reply(activityOutput.text, activityErrors.text, code))
            if (root.opened) scanTimer.restart()
        }
    }
    Process {
        id: summaryProc
        stdout: StdioCollector { id: summaryOutput }
        stderr: StdioCollector { id: summaryError }
        onExited: function(code) {
            root.receiveSummary(Model.reply(summaryOutput.text, summaryError.text, code))
            if (root.opened) summaryTimer.restart()
        }
    }
    Process {
        id: jobsProc
        stdout: StdioCollector { id: jobsOutput }
        stderr: StdioCollector { id: jobsError }
        onExited: function(code) {
            root.receiveJobs(Model.reply(jobsOutput.text, jobsError.text, code))
            if (root.opened) jobsTimer.restart()
        }
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
                    else if (event.key === Qt.Key_R) {
                        if (event.modifiers & Qt.ShiftModifier) root.rediscover()
                        else { root.refresh(); root.fetchJobs(); root.scan(); if (!root.discoveryComplete) root.discover() }
                    }
                    else if (event.key === Qt.Key_O) root.openBrowser()
                    else event.accepted = false
                }

                Column {
                    anchors.fill: parent
                    spacing: Style.spacing.md
                    Text {
                        width: parent.width
                        text: "GitHub Actions  ·  " + root.repositories.length + (root.repositories.length === 1 ? " repository" : " repositories")
                        color: Color.menu.text
                        font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.title * root.textScale); bold: true }
                        textFormat: Text.PlainText
                    }
                    Text {
                        width: parent.width
                        text: root.filtering || root.filterText ? "/ " + root.filterText + (root.filtering ? "▏" : "") : root.discoveryError || root.error || root.scanError ||
                            (root.discoveryComplete ? "Activity checked " + root.checkedCount + "/" + root.repositories.length + " · running first · / search repositories" : "Discovering repositories… " + root.repositories.length + " found")
                        color: root.error || root.discoveryError || root.scanError ? Color.urgent : Color.menu.text
                        opacity: 0.75
                        font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.caption * root.textScale) }
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
                            height: modelData.subtitle ? Math.max(Style.space(64), (Style.font.body + Style.font.caption) * root.textScale + Style.space(16)) : Math.max(Style.space(40), Style.font.body * root.textScale + Style.space(12))
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
                                    font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.body * root.textScale) }
                                }
                                Column {
                                    width: Math.max(0, parent.width - Style.space(26) - info.width - parent.spacing * 2)
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        width: parent.width
                                        text: (["repo", "run", "job"].indexOf(modelData.kind) >= 0 ? (root.expanded[modelData.key] ? "▾ " : "▸ ") : "") + modelData.title
                                        color: index === root.cursor ? Color.menu.selectedText : Color.menu.text
                                        font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.body * root.textScale); bold: modelData.kind === "repo" }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                    Text {
                                        visible: !!modelData.subtitle
                                        width: parent.width
                                        text: modelData.subtitle || ""
                                        color: index === root.cursor ? Color.menu.selectedText : Color.menu.text
                                        opacity: 0.65
                                        font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.caption * root.textScale) }
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
                                    font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.caption * root.textScale) }
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
                            font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.body * root.textScale) }
                        }
                    }
                    Text {
                        id: footer
                        width: parent.width
                        text: "↑↓ move  ←→ expand  / search  r refresh  R repos  o GitHub  Esc close"
                        color: Color.menu.text
                        opacity: 0.65
                        font { family: Style.font.menuFamily; pixelSize: Math.round(Style.font.caption * root.textScale) }
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                }
            }
        }
    }
}
