import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "ActionsModel.js" as Model
import "Polling.js" as Polling

Item {
    id: root
    property var shell: null
    property bool opened: false
    property var targetScreen: null
    property var repos: []
    property var details: ({})
    property var expanded: ({})
    property var entries: []
    property int cursor: 0
    property string view: "repos"
    property var viewState: ({repos: {filter: "", key: ""}, prs: {filter: "", key: ""}})
    property bool switching: false
    property string jumpKey: ""
    property string adoptedAccount: ""
    property alias filterText: searchField.text
    readonly property bool filtering: searchField.activeFocus
    property string error: ""
    property string statusPath: {
        var runtime = Quickshell.env("XDG_RUNTIME_DIR")
        var display = Quickshell.env("WAYLAND_DISPLAY")
        return runtime && display ? runtime + "/omarchy-github-actions-" + display + ".json" : ""
    }
    property string statusInstance: ""
    property string lastStatus: ""
    property string pendingStatus: ""
    onStatusPathChanged: { lastStatus = ""; pendingStatus = "" }
    property string updated: ""
    property var polling: Polling.create()
    readonly property bool watching: Object.keys(polling.watches).length > 0
    property var noticeQueue: []
    property bool noticeBusy: false
    property bool noticeStarted: false
    property var requestInfo: null
    property bool workerBusy: false
    property bool helperStarted: false
    property var confirm: null
    property bool actionBusy: false
    property bool actionStarted: false
    property string actionText: ""
    property bool actionError: false
    property int actionId: 0
    property var actionInfo: null
    property double now: Date.now()
    property int textStep: 0
    readonly property int fTitle: Model.fontPx(Style.font.title, textStep)
    readonly property int fBody: Model.fontPx(Style.font.body, textStep)
    readonly property int fCaption: Model.fontPx(Style.font.caption, textStep)
    function sp(n) { return Model.zoomed(Style.space(n), textStep) }
    function textKey(event) {
        var m = event.modifiers
        if (!(m & Qt.ControlModifier) || (m & (Qt.AltModifier | Qt.MetaModifier))) return false
        if (event.key === Qt.Key_Equal || event.key === Qt.Key_Plus) setTextStep(textStep + 1)
        else if (event.key === Qt.Key_Minus) setTextStep(textStep - 1)
        else if (event.key === Qt.Key_0) setTextStep(0)
        else return false
        return true
    }
    function setTextStep(n) {
        textStep = Model.clampStep(n)
        // After the new row heights are laid out, or the selected row can end up partly below the view.
        Qt.callLater(function() { list.forceLayout(); list.positionViewAtIndex(cursor, ListView.Contain) })
        showNotice("Text size " + (100 + 10 * textStep) + "%")
    }
    readonly property bool discoveryComplete: polling.catalogueComplete
    property string notice: ""
    property double noticeUntil: 0
    readonly property var statusInfo: view === "prs" ? Model.prStatusLine({notice: notice, noticeUntil: noticeUntil,
        prs: polling.accountVerified ? polling.prs : {list: null, total: 0, error: ""}, cooldown: polling.cooldown,
        gqlRemaining: polling.accountVerified ? polling.gqlRemaining : null, gqlResetAt: polling.gqlResetAt}, now) : Model.statusLine({notice: notice, noticeUntil: noticeUntil, error: root.error, repos: repos,
        cooldown: polling.cooldown, discoveryComplete: discoveryComplete, checkedCount: checkedCount, repoCount: repos.length,
        remaining: polling.remaining, resetAt: polling.resetAt}, now)
    readonly property var coverage: Model.coverage(repos)
    function showNotice(text) { notice = text; noticeUntil = Date.now() + 3000 }
    readonly property int checkedCount: repos.filter(function(repo) { return !!repo.checked || repo.archived || repo.disabled }).length
    readonly property var current: entries[cursor] || null
    // #46: the run detail pane and the verified gh login in the title.
    property bool detail: false
    property string account: ""
    // Same as a row without a subtitle, so it follows the text size keys (#48).
    readonly property real rowMin: Math.max(sp(40), fBody + sp(12))
    readonly property var detailRun: current && ["run", "job", "step"].indexOf(current.kind) >= 0 ? Polling.runFor(polling, current.repo, current.run) : null
    readonly property var detailRows: detail ? Model.detail(detailRun, now) : []
    readonly property string titleText: view === "prs" ? "Pull requests" + (polling.accountVerified && polling.prs.list ? "  ·  " + polling.prs.total + " open" : "") + (account ? "  ·  " + account : "")
        : "GitHub Actions  ·  " + repos.length + (repos.length === 1 ? " repository" : " repositories") + (account ? "  ·  " + account + "@github.com" : "") + (watching ? "  ·  " + Object.keys(polling.watches).length + " watched" : "")
    readonly property string detailAccessibleName: "Run details: " + detailRows.map(function(r) { return (r.label ? r.label + " " : "") + r.value }).join(", ")
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("actions.py").toString().replace(/^file:\/\//, ""))
    onFilterTextChanged: {
        if (switching) return
        jumpKey = ""  // typing takes over the selection from a pending jump
        rebuild(filterText !== "")
        if (filterText === "") list.positionViewAtIndex(cursor, ListView.Contain)
        selectionChanged(false)
    }
    // ponytail: full rebuild at 1 Hz (~7 ms at 1650 rows in Node); skip when no entry has an open-ended duration if it ever shows in a profile
    onNowChanged: rebuild()

    function open() {
        var monitor = Hyprland.focusedMonitor
        targetScreen = null
        for (var i = 0; i < Quickshell.screens.length; i++)
            if (monitor && Quickshell.screens[i].name === monitor.name) targetScreen = Quickshell.screens[i]
        if (!opened) {
            Polling.open(polling, Date.now()); Polling.view(polling, view === "prs", Date.now()); account = ""
            polling = Object.assign({}, polling)  // notify bindings such as the empty state that the login is unchecked again
            publishStatus()
        }
        opened = true
        rebuild()
        selectionChanged(true)
        pump()
        Qt.callLater(function() { keys.forceActiveFocus() })
    }
    function close() {
        // Polling.close() drops the reply; the watch is polled again.
        opened = false
        Polling.close(polling)
        requestProc.running = false
        confirm = null
        detail = false
        jumpKey = ""
    }
    function toggle() { opened ? close() : open() }
    function publishStatus() {
        if (!statusPath || !statusInstance) return
        var previous = lastStatus ? JSON.parse(lastStatus) : undefined
        var payload = Model.barStatus(polling, statusInstance, Date.now(), previous)
        var writtenAt = payload.writtenAt
        delete payload.writtenAt
        var next = JSON.stringify(payload)
        if (next === lastStatus) return
        pendingStatus = next
        payload.writtenAt = writtenAt
        statusFile.setText(JSON.stringify(payload) + "\n")
    }
    function status() {
        return JSON.stringify({opened: opened, rows: entries.length, repositories: repos.length,
            checked: checkedCount, discoveryComplete: discoveryComplete, error: error, updated: updated,
            requests: polling.requests, inFlight: workerBusy, cooldown: polling.cooldown,
            lastRequest: polling.lastRequest, lastStarted: polling.lastStarted,
            filter: filterText, editing: filtering, selected: current ? current.key : "", scrollY: list.contentY,
            view: view, prs: polling.accountVerified && polling.prs.list ? polling.prs.list.length : -1, jumpKey: jumpKey,
            textStep: textStep, pollSelected: polling.selected, pollInspected: polling.inspected, remaining: polling.remaining, resetAt: polling.resetAt,
            action: actionText, actionBusy: actionBusy,
            confirm: confirm ? {action: confirm.action, repo: confirm.repo, run: confirm.run} : null})
    }
    function layout() {  // test hook: geometry of the delegates that exist
        var rows = []
        for (var i = 0; i < list.count; i++) { var item = list.itemAtIndex(i); if (item) rows.push({i: i, key: entries[i].key, x: item.x, y: item.y - list.contentY, w: item.width, h: item.height}) }
        return JSON.stringify({listWidth: list.width, listHeight: list.height, contentHeight: list.contentHeight, count: list.count, rows: rows,
            pane: pane.visible ? {y: pane.y - list.y, h: pane.height} : null, footerY: footer.y - list.y})
    }

    function switchView(target, filter, key) {
        viewState[view] = {filter: filterText, key: current ? current.key : ""}
        detail = false
        switching = true
        try {
            view = target
            Polling.view(polling, target === "prs", Date.now())
            filterText = filter
        } finally { switching = false }
        rebuild(false, key)
    }
    function rebuild(resetSelection, selectKey) {
        if (jumpKey) selectKey = jumpKey
        var key = selectKey || (current ? current.key : "")
        var topIndex = list.indexAt(1, list.contentY + 1)
        var topItem = list.itemAtIndex(topIndex)
        var topKey = entries[topIndex] ? entries[topIndex].key : ""
        var topOffset = topItem ? topItem.y - list.contentY : 0
        var next = view === "prs" ? Model.prRows(polling.accountVerified ? polling.prs : null, expanded, filterText, now)
            : Model.rows(repos, expanded, details, filterText, now,
                polling.selected && polling.inspected ? polling.selected + ":" + polling.inspected : "", polling.watches)
        var structureChanged = Model.syncRows(visibleRows, next)
        entries = next
        cursor = selectKey ? Math.max(0, entries.findIndex(function(row) { return row.key === selectKey }))
            : resetSelection ? 0 : Model.selection(entries, key, cursor)
        if (selectKey) {
            list.forceLayout()
            list.positionViewAtIndex(cursor, ListView.Contain)
        } else if (resetSelection) {
            list.forceLayout()
            list.positionViewAtBeginning()
        } else if (structureChanged && topKey) {
            var index = entries.findIndex(function(row) { return row.key === topKey })
            list.forceLayout()
            if (index >= 0) {
                list.positionViewAtIndex(index, ListView.Beginning)
                list.forceLayout()
                var item = list.itemAtIndex(index)
                if (item) list.contentY = item.y - topOffset
                list.returnToBounds()
            }
        }
        if (jumpKey && entries.some(function(row) { return row.key === jumpKey })) {
            jumpKey = ""
            selectionChanged(true)
        }
    }
    function move(delta) {
        jumpKey = ""
        cursor = Math.max(0, Math.min(entries.length - 1, cursor + delta))
        list.positionViewAtIndex(cursor, ListView.Contain)
        selectionChanged(false)
    }
    function page(dir) {
        var top = list.indexAt(1, list.contentY)
        var bottom = list.indexAt(1, list.contentY + list.height - 1)
        if (top < 0) top = 0
        if (bottom < 0) bottom = entries.length - 1
        move(dir * Math.max(1, bottom - top))
    }
    function click(index) {
        if (confirm) return
        jumpKey = ""
        cursor = index
        selectionChanged(false)
        keys.forceActiveFocus()
        expand(false)
    }
    function itemAt(index) { return list.itemAtIndex(index) }
    readonly property alias listView: list
    readonly property alias detailPane: pane
    readonly property alias footerItem: footer
    function enter() {
        var row = current
        if (row && row.kind === "check") { jump(); return }
        if (!row || ["repo", "pr", "run", "job"].indexOf(row.kind) < 0) return
        if (!expanded[row.key]) { expand(false); return }
        if (entries[cursor + 1] && entries[cursor + 1].parent === row.key) {
            jumpKey = ""
            cursor++
            list.positionViewAtIndex(cursor, ListView.Contain)
            selectionChanged(false)
        }
    }
    function expand(collapse) {
        var row = current
        if (!row) return
        if (!collapse && row.kind === "check") { jump(); return }
        var next = Object.assign({}, expanded)
        if (collapse) {
            if (next[row.key]) delete next[row.key]
            else {
                cursor = Model.selection(entries, row.parent, cursor)
                list.positionViewAtIndex(cursor, ListView.Contain)
                selectionChanged(false)
                return
            }
        } else if (["repo", "pr", "run", "job"].indexOf(row.kind) >= 0) {
            next[row.key] = !next[row.key]
        }
        expanded = next
        rebuild()
        selectionChanged(true)
        pump()
    }
    function toggleDetail() {
        detail = !detail
        // The pane resizes the list; keep the selected row in view, as setTextStep() does.
        Qt.callLater(function() { list.forceLayout(); list.positionViewAtIndex(cursor, ListView.Contain) })
    }
    // Esc closes run details first; then the search field clears and returns to the list, else the filter clears, else the popup closes.
    function handleEscape(searching) {
        if (detail) detail = false
        else if (searching) { filterText = ""; keys.forceActiveFocus() }
        else if (filterText) filterText = ""
        else close()
    }
    function selectionChanged(immediate) {
        if (!polling) return
        Polling.select(polling, view === "prs" ? "" : current ? current.repo : "",
            view === "prs" ? "" : current ? current.run : "", expanded, Date.now(), immediate)
        rebuild()
    }
    function adopt() {
        // The first verified login is not a change; only a different login resets the views.
        var accountChanged = !!adoptedAccount && !!polling.account && polling.account !== adoptedAccount
        if (polling.account) adoptedAccount = polling.account
        if (accountChanged) {
            viewState = {repos: {filter: "", key: ""}, prs: {filter: "", key: ""}}
            switching = true
            try { filterText = "" } finally { switching = false }
            jumpKey = ""
            detail = false
        }
        repos = polling.repos.slice()
        account = polling.accountVerified && polling.account ? polling.account : ""
        details = Object.assign({}, polling.details)
        expanded = polling.expanded
        error = polling.error || polling.catalogueBlocked
        var log = polling.log
        polling.log = null
        if (log) openLog(log)
        var notices = polling.notices
        polling.notices = []
        notices.forEach(function(n) { noticeQueue.push(Model.notice(n)) })
        drainNotices()
        // Reassign the state reference to notify bindings after pure-JS mutations.
        polling = Object.assign({}, polling)
        publishStatus()
        if (!opened) return
        rebuild()
        if (jumpKey) {
            var jumpRepo = jumpKey.slice(0, jumpKey.lastIndexOf(":"))
            var jumpRun = jumpKey.slice(jumpKey.lastIndexOf(":") + 1)
            var run = Polling.runFor(polling, jumpRepo, jumpRun)
            if ((run && run.lookupError) || !polling.tasks["run:" + jumpRepo + ":" + jumpRun]) {
                jumpKey = ""
                showNotice("Run unavailable")
            }
        }
        if (!jumpKey) selectionChanged(false)
    }
    function jump() {
        var row = current
        if (!row || row.kind !== "check") return
        if (!row.run) { showNotice("Not an Actions check" + (Model.browsable(row.url) ? "; o opens it" : "")); return }
        var repo = Polling.repoFor(polling, row.repo)
        if (!repo) { showNotice("Repository not in your list"); return }
        if (repo.archived || repo.disabled || repo.blocked) { showNotice("Repository is archived, disabled or unavailable"); return }
        var next = Object.assign({}, expanded)
        next["repo:" + row.repo] = true
        next[row.repo + ":" + row.run] = true
        expanded = next
        Polling.jump(polling, row.repo, row.run, expanded, Date.now())
        jumpKey = row.repo + ":" + row.run
        switchView("repos", "", jumpKey)
        adopt()
        pump()
    }
    // One notify-send at a time; the argv is an array, never a shell string.
    function drainNotices() {
        if (noticeBusy || noticeQueue.length === 0) return
        var m = noticeQueue.shift()
        noticeBusy = true
        noticeStarted = false
        noticeProc.command = ["notify-send", "--app-name=GitHub Actions", "--", m.title, m.body]
        noticeProc.running = true
    }
    function refresh(catalogue) {
        selectionChanged(true)
        Polling.manual(polling, Date.now(), !!catalogue)
        publishStatus()
        pump()
    }
    function loadMore() {
        if (!current || !current.repo) return
        if (!Polling.more(polling, current.repo, Date.now())) showNotice("Refreshing; press m again in a moment")
        adopt()
        pump()
    }
    function pump() {
        if ((!opened && !watching) || workerBusy) return
        var request = Polling.next(polling, Date.now())
        if (!request) return
        requestInfo = request
        workerBusy = true
        helperStarted = false
        requestProc.command = ["python3", helper, request.kind === "log" ? "log" : "page", JSON.stringify(request)]
        requestProc.running = true
    }
    function failedToStart() {
        console.warn("GitHub Actions helper: python3 failed to start")
        finishRequest("", 127)
    }
    function finishRequest(text, code) {
        try { receivePage(Model.reply(text, code, requestInfo.requestId), requestInfo) }
        catch (e) {
            console.warn("GitHub Actions reply handling failed: " + (e && e.message))
            Polling.drop(polling, requestInfo.requestId, Date.now())
        } finally { workerBusy = false }
    }
    function receivePage(text, request) {
        var reply
        try {
            reply = JSON.parse(text)
            if (!reply || reply.requestId !== request.requestId)
                throw new Error("Workflow helper returned an invalid request identity")
        } catch (e) {
            console.warn("GitHub Actions helper reply rejected: " + String(text).slice(0, 300))
            reply = {requestId:request.requestId, error:"Workflow helper returned invalid data; see the shell log", errorType:"setup"}
        }
        if (Polling.complete(polling, reply, Date.now())) {
            if (!reply.error) updated = new Date().toISOString()
            adopt()
        }
    }
    function statusColor(status) {
        if (["failure", "timed_out", "startup_failure", "error"].indexOf(status) >= 0) return Commons.Color.urgent
        if (status === "in_progress") return Commons.Color.accent
        return Commons.Color.menu.text
    }
    function openBrowser() {
        if (current && current.kind === "check" && current.external) {
            showNotice("Link is not on github.com; o on the pull request opens it")
            return
        }
        if (current && current.kind === "check" && !Model.browsable(current.url)) {
            showNotice("No link")
            return
        }
        if (current && Model.browsable(current.url))
            Quickshell.execDetached(["xdg-open", current.url])
    }
    function viewLog() {
        if (viewProc.running) { showNotice("A log is already open"); return }
        var t = current ? Model.logTarget(current, details, (Polling.repoFor(polling, current.repo) || {}).runs || []) : null
        if (!t) return
        if (t.error) { showNotice(t.error); return }
        if (!Polling.requestLog(polling, t, Date.now())) { showNotice("A log is already being fetched"); return }
        showNotice("Fetching log…")
        pump()
    }
    function openLog(log) {
        if (log.error) showNotice(log.error)
        else if (!log.path) showNotice("This log is empty.")
        else if (viewProc.running) showNotice("A log is already open")
        else {
            viewProc.viewStarted = false
            viewProc.viewing = true
            viewProc.command = ["omarchy-launch-tui", "--app-id=org.omarchy.github-actions-log", "python3", helper, "view", log.path]
            viewProc.running = true
        }
    }
    function toggleWatch() {
        if (!current || current.kind !== "run") return
        var run = Polling.runFor(polling, current.repo, current.run)
        if (!run) return
        if (run.status === "completed") {
            showNotice("Already finished: " + Model.notice({kind: "done", repo: "", name: "", conclusion: run.conclusion}).title)
            return
        }
        var name = run.name || "run"
        var r = Polling.watch(polling, current.repo, current.run, name, Date.now())
        showNotice(r === "full" ? "At most 5 runs can be watched" : r === "on" ? "Watching this run; lost if the shell restarts" : "Stopped watching")
        adopt()
        pump()
    }
    function copyLink() {
        if (copyProc.copyBusy) { showNotice("Copy in progress"); return }
        if (current && current.kind === "check" && current.external) {
            showNotice("Link is not on github.com; o on the pull request opens it")
            return
        }
        if (current && current.kind === "check" && !Model.browsable(current.url)) {
            showNotice("No link")
            return
        }
        if (!current || current.kind === "message" || current.kind === "more" || !Model.browsable(current.url)) {
            showNotice("Nothing to copy")
            return
        }
        copyProc.copyBusy = true
        copyProc.copyStarted = false
        copyProc.command = ["wl-copy", "--", current.url]
        copyProc.running = true
    }
    function say(text, error) {
        actionText = text
        actionError = !!error
        actionTimer.restart()
    }
    function gate() {
        if (Date.now() < polling.cooldown) return "GitHub paused until " + new Date(polling.cooldown).toLocaleTimeString() + ". Try again then."
        return actionBusy ? "An action is already running" : ""
    }
    function askAction(action) {
        if (confirm) return
        var row = current
        var run = row && row.kind === "run" ? Polling.runFor(polling, row.repo, row.run) : null
        var why = Model.unavailable(action, run) || gate()
        if (why) { say(why, true); return }
        var d = Model.describe(action, row.repo, run)
        actionText = ""
        // Strings only: polling may rebuild or reorder rows before y arrives.
        confirm = {action: action, repo: row.repo, run: row.run, text: d.confirm, done: d.done}
    }
    function answer(yes) {
        var target = confirm
        confirm = null
        if (!yes || !target) return
        var why = gate()
        if (why) { say(why, true); return }
        actionBusy = true
        actionStarted = false
        actionInfo = {requestId: ++actionId, repo: target.repo, run: target.run, done: target.done}
        actionProc.command = ["python3", helper, "act", JSON.stringify({action: target.action, repo: target.repo, run: target.run, requestId: actionId})]
        actionProc.running = true
    }
    function actionFailedToStart() {
        console.warn("GitHub Actions helper: python3 failed to start")
        actionBusy = false
        receiveAction(Model.actionReply("", 127, actionInfo.requestId), actionInfo)
    }
    function receiveAction(text, info) {
        var reply
        try {
            reply = JSON.parse(text)
            if (!reply || reply.requestId !== info.requestId)
                throw new Error("Workflow helper returned an invalid request identity")
        } catch (e) {
            console.warn("GitHub Actions helper reply rejected: " + String(text).slice(0, 300))
            reply = JSON.parse(Model.actionReply("", 1, info.requestId))
        }
        Polling.noteWrite(polling, reply, Date.now())
        publishStatus()
        if (reply.ok === true && !reply.errorType) {
            say(info.done + (Date.now() < polling.cooldown ? " · refresh waits until " + new Date(polling.cooldown).toLocaleTimeString() : ""), false)
            if (opened) {
                Polling.touch(polling, info.repo, info.run, Date.now())
                adopt()
                pump()
            }
        } else say(String(reply.error || "Outcome unknown; check GitHub before retrying"), true)
    }

    Component.onCompleted: {
        statusInstance = String(Date.now()) + "-" + Math.random().toString(36).slice(2)
        publishStatus()
        rebuild()
        registrationProc.running = true
    }
    Component.onDestruction: {
        if (statusPath) {
            var payload = Model.barStatus(polling, statusInstance, Date.now())
            payload.state = "none"
            var writtenAt = payload.writtenAt
            delete payload.writtenAt
            pendingStatus = JSON.stringify(payload)
            payload.writtenAt = writtenAt
            statusFile.setText(JSON.stringify(payload) + "\n")
        }
    }
    Process {
        id: registrationProc
        command: ["python3", decodeURIComponent(Qt.resolvedUrl("menu.py").toString().replace(/^file:\/\//, "")), "register"]
        stderr: StdioCollector { id: registrationErrors }
        onExited: function(code) {
            if (code !== 0) console.warn("GitHub Actions menu registration failed: " + registrationErrors.text.trim())
        }
    }
    ListModel { id: visibleRows; dynamicRoles: true }
    FileView {
        id: statusFile
        path: root.statusPath
        atomicWrites: true
        blockWrites: true
        printErrors: false
        onSaved: root.lastStatus = root.pendingStatus
    }
    Timer { interval: 100; running: root.opened || root.watching; repeat: true; onTriggered: root.pump() }
    Timer { interval: 1000; running: root.opened; repeat: true; triggeredOnStart: true; onTriggered: root.now = Date.now() }
    Process {
        id: requestProc
        stdout: StdioCollector { id: pageOutput }
        stderr: StdioCollector { id: pageErrors }
        onExited: function(code) {
            if (pageErrors.text.trim()) console.warn("GitHub Actions helper (exit " + code + "): " + pageErrors.text.trim())
            root.finishRequest(pageOutput.text, code)
        }
        onStarted: root.helperStarted = true
        // Quickshell 0.3.1: a failed start emits neither started nor exited, only running=false.
        onRunningChanged: if (!running && root.workerBusy && !root.helperStarted) root.failedToStart()
    }
    Process {
        id: noticeProc
        onStarted: root.noticeStarted = true
        onExited: { root.noticeBusy = false; Qt.callLater(root.drainNotices) }
        // Quickshell 0.3.1: a failed start emits neither started nor exited, only running=false.
        onRunningChanged: if (!running && root.noticeBusy && !root.noticeStarted) {
            console.warn("GitHub Actions: notify-send failed to start")
            root.noticeBusy = false
            root.drainNotices()
        }
    }
    Process {
        id: viewProc
        property bool viewing: false
        property bool viewStarted: false
        onStarted: viewStarted = true
        onExited: viewing = false
        // Quickshell 0.3.1: a failed start emits neither started nor exited, only running=false.
        onRunningChanged: if (!running && viewing && !viewStarted) {
            viewing = false
            root.showNotice("Terminal launcher not found")
        }
    }
    Process {
        id: copyProc
        property bool copyBusy: false
        property bool copyStarted: false
        onStarted: copyStarted = true
        onExited: function(code) {
            copyBusy = false
            root.showNotice(code === 0 ? "Copied link" : "Copy failed (exit " + code + ")")
        }
        onRunningChanged: if (!running && copyBusy && !copyStarted) {
            copyBusy = false
            root.showNotice("Install wl-clipboard to copy links")
        }
    }
    // Writes have their own process: close() must not kill one in flight, and its reply must not be dropped.
    Process {
        id: actionProc
        stdout: StdioCollector { id: actionOutput }
        stderr: StdioCollector { id: actionErrors }
        onExited: function(code) {
            if (actionErrors.text.trim()) console.warn("GitHub Actions helper (exit " + code + "): " + actionErrors.text.trim())
            // finally: an exception in receiveAction must not block later actions
            try { root.receiveAction(Model.actionReply(actionOutput.text, code, root.actionInfo.requestId), root.actionInfo) }
            finally { root.actionBusy = false }
        }
        onStarted: root.actionStarted = true
        onRunningChanged: if (!running && root.actionBusy && !root.actionStarted) root.actionFailedToStart()
    }
    Timer { id: actionTimer; interval: 10000; onTriggered: root.actionText = "" }

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
            color: Commons.Color.menu.background
            radius: Style.cornerRadius
            borderSpec: Border.surfaceSpec("menu", "border", Commons.Color.menu.border, Math.max(1, Style.space(2)))
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
                    if (root.confirm) {
                        event.accepted = true
                        if (!event.isAutoRepeat && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) {
                            if (event.key === Qt.Key_Y) root.answer(true)
                            else if (event.key === Qt.Key_N || event.key === Qt.Key_Escape) root.answer(false)
                        }
                        return
                    }
                    if (root.textKey(event)) { event.accepted = true; return }
                    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) {
                        event.accepted = false
                        return
                    }
                    event.accepted = true
                    if (event.isAutoRepeat && (event.text === "y" || event.text === "?" || event.text === "m" || event.text === "w" || event.text === "p")) return
                    if (event.key === Qt.Key_Escape) root.handleEscape(false)
                    else if (event.key === Qt.Key_Down || event.key === Qt.Key_J) root.move(1)
                    else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) root.move(-1)
                    else if (event.key === Qt.Key_PageDown) root.page(1)
                    else if (event.key === Qt.Key_PageUp) root.page(-1)
                    else if (event.key === Qt.Key_Home) root.move(-root.entries.length)
                    else if (event.key === Qt.Key_End) root.move(root.entries.length)
                    else if (event.key === Qt.Key_Left || event.key === Qt.Key_H) root.expand(true)
                    else if (event.key === Qt.Key_Right || event.key === Qt.Key_L) root.enter()
                    else if ([Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space].indexOf(event.key) >= 0) root.expand(false)
                    else if (event.text === "g") root.move(-root.entries.length)
                    else if (event.text === "G") root.move(root.entries.length)
                    else if (event.text === "p") {
                        root.jumpKey = ""
                        var target = root.view === "prs" ? "repos" : "prs"
                        var saved = root.viewState[target]
                        root.switchView(target, saved.filter, saved.key)
                        root.selectionChanged(true)
                        root.pump()
                    }
                    else if (event.text === "y") root.copyLink()
                    else if (event.text === "w") root.view === "prs" ? root.showNotice("Not available on pull requests") : root.toggleWatch()
                    else if (event.text === "?") Quickshell.execDetached(["bash", decodeURIComponent(Qt.resolvedUrl("keybindings.sh").toString().replace(/^file:\/\//, ""))])
                    else if (event.key === Qt.Key_Slash) { searchField.forceActiveFocus(); searchField.selectAll() }
                    else if (event.key === Qt.Key_R) {
                        root.refresh(!!(event.modifiers & Qt.ShiftModifier))
                    }
                    else if (event.key === Qt.Key_O) root.openBrowser()
                    else if (root.view === "prs" && (event.key === Qt.Key_I || event.key === Qt.Key_V || event.key === Qt.Key_A || event.key === Qt.Key_F || event.key === Qt.Key_C || event.text === "m")) root.showNotice("Not available on pull requests")
                    else if (event.key === Qt.Key_I) root.toggleDetail()
                    else if (event.key === Qt.Key_V) root.viewLog()
                    else if (event.key === Qt.Key_A) root.askAction("rerun")
                    else if (event.key === Qt.Key_F) root.askAction("rerun-failed")
                    else if (event.key === Qt.Key_C) root.askAction("cancel")
                    else if (event.text === "m") root.loadMore()
                    else event.accepted = false
                }

                Column {
                    anchors.fill: parent
                    spacing: Style.spacing.md
                    Text {
                        width: parent.width
                        text: root.titleText
                        color: Commons.Color.menu.text
                        font { family: Style.font.menuFamily; pixelSize: root.fTitle; bold: true }
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }
                    TextInput {
                        id: searchField
                        width: parent.width
                        height: Math.ceil(font.pixelSize * 1.4)
                        color: Commons.Color.menu.text
                        font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                        clip: true
                        selectByMouse: true
                        selectionColor: Commons.Color.menu.selectedBackground
                        selectedTextColor: Commons.Color.menu.selectedText
                        Accessible.name: root.view === "prs" ? "Search pull requests…" : "Search repositories"
                        rightPadding: coverageNote.visible ? coverageNote.implicitWidth + Style.spacing.md : 0
                        Keys.onPressed: function(event) {
                            if (root.textKey(event)) { event.accepted = true; return }
                            if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                                root.move(event.key === Qt.Key_Up ? -1 : 1)
                            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                keys.forceActiveFocus()
                                root.expand(false)
                            } else if (event.key === Qt.Key_Escape) {
                                root.handleEscape(true)
                            } else if (event.key === Qt.Key_Tab) {
                                keys.forceActiveFocus()
                            } else return
                            event.accepted = true
                        }
                        Text {
                            anchors.fill: parent
                            visible: searchField.text.length === 0
                            text: root.view === "prs" ? "Search pull requests…" : "Search repositories…"
                            color: Commons.Color.menu.text
                            opacity: 0.75
                            font: searchField.font
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                        Text {
                            id: coverageNote
                            visible: root.view !== "prs"
                            anchors.right: parent.right
                            text: "recent runs loaded for " + root.coverage.loaded + " of " + root.coverage.total + " repositories"
                            color: Commons.Color.menu.text
                            opacity: 0.65
                            font: searchField.font
                            textFormat: Text.PlainText
                        }
                    }
                    Item {
                        width: parent.width
                        height: Math.ceil(searchField.font.pixelSize * 1.4)
                        Text {
                            width: parent.width - quotaNote.implicitWidth - (quotaNote.text ? Style.spacing.md : 0)
                            text: root.statusInfo.text
                            color: root.statusInfo.urgent ? Commons.Color.urgent : Commons.Color.menu.text
                            font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                        Text {
                            id: quotaNote
                            anchors.right: parent.right
                            text: root.statusInfo.quota
                            color: Commons.Color.menu.text
                            opacity: 0.65
                            font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                            textFormat: Text.PlainText
                        }
                    }
                    Rectangle { width: parent.width; height: Style.spacing.hairline; color: Commons.Color.menu.border; opacity: 0.4 }
                    ListView {
                        id: list
                        width: parent.width
                        height: Math.max(0, parent.height - y - footer.height - Style.spacing.md - (pane.visible ? pane.height + Style.spacing.md : 0))
                        clip: true
                        model: visibleRows
                        boundsBehavior: Flickable.StopAtBounds
                        Accessible.role: Accessible.List
                        delegate: Rectangle {
                            required property var rowData
                            readonly property var modelData: rowData
                            required property int index
                            readonly property string accessibleName: Model.accessibleName(modelData, !!root.expanded[modelData.key])
                            Accessible.role: Accessible.ListItem
                            Accessible.name: accessibleName
                            Accessible.selected: index === root.cursor
                            Accessible.focusable: true
                            width: list.width
                            height: modelData.subtitle ? Math.max(root.sp(64), root.fBody + root.fCaption + root.sp(16)) : Math.max(root.sp(40), root.fBody + root.sp(12))
                            color: index === root.cursor ? Commons.Color.menu.selectedBackground : "transparent"
                            radius: 0
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: root.sp(8) + modelData.depth * root.sp(18)
                                anchors.rightMargin: root.sp(8)
                                spacing: Style.spacing.sm
                                Text {
                                    width: root.sp(18)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: Model.icon(modelData.status)
                                    color: root.statusColor(modelData.status)
                                    font { family: Style.font.menuFamily; pixelSize: root.fBody }
                                }
                                Column {
                                    width: Math.max(0, parent.width - root.sp(26) - info.width - parent.spacing * 2)
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text {
                                        width: parent.width
                                        text: (["repo", "pr", "run", "job"].indexOf(modelData.kind) >= 0 ? (root.expanded[modelData.key] ? "▾ " : "▸ ") : "") + modelData.title
                                        color: index === root.cursor ? Commons.Color.menu.selectedText : Commons.Color.menu.text
                                        font { family: Style.font.menuFamily; pixelSize: root.fBody; bold: modelData.kind === "repo" || modelData.kind === "pr" }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                    Text {
                                        visible: !!modelData.subtitle
                                        width: parent.width
                                        text: modelData.subtitle || ""
                                        color: index === root.cursor ? Commons.Color.menu.selectedText : Commons.Color.menu.text
                                        opacity: 0.65
                                        font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                }
                                Text {
                                    id: info
                                    width: Math.min(implicitWidth, list.width * 0.35)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.kind === "repo" ? modelData.info : modelData.statusText + (modelData.info ? " · " + modelData.info : "")
                                    color: root.statusColor(modelData.status)
                                    font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                                    elide: Text.ElideRight
                                    textFormat: Text.PlainText
                                }
                            }
                            MouseArea { anchors.fill: parent; onClicked: root.click(index) }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: root.entries.length === 0
                            text: root.view === "prs" ? Model.prEmptyText(root.polling, root.filterText)
                                : Model.emptyText({repoCount: root.repos.length, error: root.error, discoveryComplete: root.discoveryComplete, filter: root.filterText})
                            color: Commons.Color.menu.text
                            font { family: Style.font.menuFamily; pixelSize: root.fBody }
                            textFormat: Text.PlainText
                        }
                    }
                    Flickable {
                        id: pane
                        visible: root.detail && root.view !== "prs"
                        width: parent.width
                        // Column skips invisible items, so the spacing term depends on visibility.
                        readonly property real avail: parent.height - list.y - footer.height - Style.spacing.md * (visible ? 2 : 1)
                        readonly property real line: Math.ceil(root.fCaption * 1.4)
                        height: visible ? Model.paneHeight(parent.height, avail, paneBody.implicitHeight, 3 * root.rowMin, line) : 0
                        contentHeight: paneBody.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Accessible.role: Accessible.Pane
                        Accessible.name: root.detailAccessibleName
                        Column {
                            id: paneBody
                            width: pane.width
                            Repeater {
                                model: root.detailRows
                                Row {
                                    required property var modelData
                                    spacing: Style.spacing.sm
                                    Text {
                                        width: root.sp(90)
                                        text: modelData.label
                                        color: Commons.Color.menu.text
                                        opacity: 0.65
                                        font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                    Text {
                                        width: paneBody.width - root.sp(90) - parent.spacing
                                        text: modelData.value
                                        color: Commons.Color.menu.text
                                        font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        id: footer
                        width: parent.width
                        text: root.confirm ? root.confirm.text : root.actionText || (root.view === "prs"
                            ? "↑↓ move  ←→ expand  / search  p repositories  r refresh  o GitHub  y copy  ? keys  Esc close"
                            : "↑↓ move  ←→ expand  / search  p pull requests  r refresh  R repos  o GitHub  i details  v log  w watch  y copy  ? keys  Esc close")
                        color: root.actionError && !root.confirm && root.actionText ? Commons.Color.urgent : Commons.Color.menu.text
                        opacity: root.confirm || root.actionText ? 1 : 0.65
                        font { family: Style.font.menuFamily; pixelSize: root.fCaption }
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        wrapMode: root.textStep > 0 ? Text.WordWrap : Text.NoWrap
                        textFormat: Text.PlainText
                    }
                }
            }
        }
    }
}
