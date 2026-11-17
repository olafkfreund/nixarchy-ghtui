"""Exercise the real QML worker with a temporary fake API in a private headless sway; no live GitHub requests."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('plugin_dir', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
source = parser.parse_args().plugin_dir.resolve()
required = ('manifest.json', 'ActionsPanel.qml', 'ActionsModel.js', 'Polling.js',
            'actions.py', 'menu.py', 'menu.example.json', 'keybindings.sh')
if not source.is_dir() or any(not (source / name).is_file() for name in required):
    parser.error('plugin_dir must contain the complete GitHub Actions plugin')
QUICKSHELL = shutil.which('quickshell')
STUB_BACKGROUND = '#101315'

# The fake replies with ~200 KiB (over the 64 KiB pipe buffer) in 4 KiB chunks and exits at once,
# so every run checks that a reply written right before exit reaches the panel whole (#36).
FAKE = '''import json, os, signal, sys, time
request=json.loads(sys.argv[2])
if sys.argv[1]=='act':
    open(os.environ['HOME']+'/act.log','a').write(sys.argv[2]+'\\n')
    time.sleep(0.1)
    os.write(1,(json.dumps({'requestId':request['requestId'],'action':request['action'],'httpStatus':202,'ok':True,'error':'','errorType':'','retryAt':0,'remaining':4000})+'\\n').encode())
    os._exit(0)
if sys.argv[1]=='log':
    open(os.environ['HOME']+'/log-req.log','a').write(sys.argv[2]+'\\n')
    path=os.environ['HOME']+'/fake-log.txt'
    open(path,'w').write('log\\n')
    os.write(1,(json.dumps({'requestId':request['requestId'],'data':{'path':path,'mode':'failed','cutShort':False,'lineCut':False},'error':'','errorType':'','remaining':4000})+'\\n').encode())
    os._exit(0)
kind=request['kind']
if os.environ.get('FAKE_LOG'):
    with open(os.environ['FAKE_LOG'],'a') as log: log.write(json.dumps({'t':time.time(),'kind':kind,'repo':request.get('repo',''),'run':str(request.get('run','')),'status':request.get('status','')})+'\\n')
if os.environ.get('FAKE_MODE')=='block':
    with open(os.environ['FAKE_PID'],'w') as pid: pid.write(str(os.getpid()))
    signal.pause()
if os.path.exists(os.environ['HOME']+'/run-done'): open(os.environ['HOME']+'/closed-kinds.log','a').write(kind+'\\n')
time.sleep(0.1)
run={'id':7,'name':'CI','status':'in_progress','run_attempt':1,'head_branch':'main','run_number':1,'html_url':'https://github.com/one/repo/actions/runs/7'}
started=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-5))
runs=[run] if not os.environ.get('FAKE_RUNS') else [dict(run,id=i,run_number=i,run_started_at=started,html_url='https://github.com/one/repo/actions/runs/%d'%i) for i in range(7,7+int(os.environ['FAKE_RUNS']))]
if kind=='catalogue': data=[{'repo':'one/repo'},{'repo':'two/repo'}]
elif kind=='jobs': data=[{'id':8,'name':'build','status':'in_progress','html_url':'https://github.com/one/repo/actions/runs/7/job/8','steps':[{'number':1,'name':'Checkout','status':'completed','conclusion':'success'}]}]
elif kind=='run': data=dict(run,status='completed',conclusion='success') if os.path.exists(os.environ['HOME']+'/run-done') else runs[0]
elif kind=='account': data={'login':'tester'}
else: data=runs if request['repo']=='one/repo' and request.get('status','in_progress') in ('recent','in_progress') else []
reply=json.dumps({'requestId':request['requestId'],'data':data,'nextPage':0,'error':'','errorType':'','remaining':4000,'padding':'x'*200000}).encode()+b'\\n'
for i in range(0,len(reply),4096): os.write(1,reply[i:i+4096])
os._exit(0)
'''

# Programmatic feature checks (#41-#48): they call panel functions directly (plan deviation 3).
FEATURES_QML = '''
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import "Polling.js" as Polling
ShellRoot {
    ActionsPanel { id: panel }
    FileView {
        id: menuFile
        path: Quickshell.env("HOME") + "/.config/omarchy/extensions/omarchy-menu.jsonc"
        watchChanges: true
        blockLoading: true
        printErrors: false
        onFileChanged: reload()
    }
    Timer {
        interval: 40000; running: true
        onTriggered: {
            var missing = stage === 1 ? [panel.polling.requests>=6 ? "" : "requests>=6", panel.details["one/repo:7"] ? "" : "jobs one/repo:7",
                panel.polling.catalogueComplete ? "" : "catalogueComplete"].filter(Boolean).join(",") : ""
            console.error("CHECK FAILED: timeout stage=" + stage + (missing ? " missing=" + missing : "") + " " + panel.status()); Qt.quit()
        }
    }
    function stopped() {
        if (!panel.polling.auth) return false
        console.error("CHECK FAILED: polling stopped: " + panel.error + " " + panel.status()); Qt.quit()
        return true
    }
    property int stage: 0
    property string selected: ""
    property double closedAt: 0
    property int closedRequests: 0
    property bool touchSeen: false
    property bool copyChecked: false
    property bool accChecked: false
    property bool healthChecked: false
    property int zoomStage: 0
    property string zoomKey: ""
    property string zoomExpanded: ""
    property string zoomFilter: ""
    property var zoomRepos: []
    property var zoomOriginalExpanded: ({})
    function checkZoomLayout() {
        var view=panel.listView, item=view.itemAtIndex(panel.cursor), previous=null
        check(panel.current.key===zoomKey && JSON.stringify(panel.expanded)===zoomExpanded && panel.filterText===zoomFilter,"zoom keeps selection, expansion and filter")
        check(view.height>0 && item && item.y>=view.contentY && item.y<view.contentY+view.height && (item.height>view.height || item.y+item.height<=view.contentY+view.height),"zoom keeps selected row visible (fully, when it fits)")
        for (var i=0; i<panel.entries.length; i++) {
            var row=view.itemAtIndex(i)
            if (row && previous) check(row.y>=previous.y+previous.height,"zoom rows do not overlap")
            previous=row
        }
        if (panel.textStep===-3 || panel.textStep===0 || panel.textStep===5)
            console.log("TEXT_SIZE_LAYOUT step=" + panel.textStep + " list=" + view.height + " row=" + item.height)
    }
    function textWith(item, text) {
        if (item.text === text) return item
        for (var i = 0; i < item.children.length; i++) {
            var found = textWith(item.children[i], text)
            if (found) return found
        }
        return null
    }
    // Fires inside the reply handler, right after touch(): the run task still exists or is in flight.
    Connections {
        target: panel
        function onActionBusyChanged() {
            if (!panel.actionBusy && stage === 5)
                touchSeen = !!(panel.polling.tasks["run:one/repo:7"] || (panel.polling.flight && panel.polling.flight.key === "run:one/repo:7"))
        }
    }
    function at(key) {
        var i = panel.entries.findIndex(function(row) { return row.key === key })
        check(i >= 0, "row " + key)
        panel.cursor = i
    }
    // The panel is closed here, so adopt() skips the rebuild and the selection update.
    function reseed() { panel.adopt(); panel.rebuild(); panel.selectionChanged(false) }
    function ensureRun9() {
        var runs = panel.polling.repos[0].runs
        if (!runs.some(function(run) { return run.id === 9 }))
            runs.push({id:9,name:"Lint",status:"completed",conclusion:"failure",run_number:2,head_branch:"main",html_url:"https://github.com/one/repo/actions/runs/9"})
        panel.adopt()
    }
    FileView { id: launchFile; path: Quickshell.env("HOME") + "/omarchy-launch-tui.log"; printErrors: false }
    function notified() { notifyFile.reload(); return notifyFile.text().split("\\n").length > 3 }
    FileView { id: notifyFile; path: Quickshell.env("HOME") + "/notify-send.log"; printErrors: false }
    property bool flagReady: false
    Process {
        id: flagProc
        command: ["python3", "-c", "import os;open(os.environ['HOME']+'/run-done','w')"]
        onExited: { panel.polling.watches["one/repo:7"].at = 0; var run = panel.polling.repos[0].runs.filter(function(r) { return r.id === 7 })[0]; if (run) delete run.followupAt; flagReady = true }  // both clocks: the watch and the 15 s follow-up
    }
    function launched() { launchFile.reload(); return launchFile.text().split("\\n").length > 5 }
    function check(value, label) { if (!value) throw new Error("CHECK FAILED: " + label) }
    Timer {
        interval: 1000; running: true
        onTriggered: {
            check(Commons.Color.background.toString()===Quickshell.env("EXPECTED_BACKGROUND"),"active Omarchy theme")
            check(panel.textStep===0 && panel.fTitle===Style.font.title && panel.fBody===Style.font.body && panel.fCaption===Style.font.caption && panel.sp(18)===Style.space(18) && panel.sp(64)===Style.space(64),"default text size is the theme size")
            check(panel.textKey({key:Qt.Key_Equal,modifiers:Qt.ControlModifier}) && panel.textStep===1 && panel.notice==="Text size 110%","Ctrl+= grows text")
            check(panel.textKey({key:Qt.Key_Plus,modifiers:Qt.ControlModifier|Qt.ShiftModifier}) && panel.textStep===2 && panel.notice==="Text size 120%","Ctrl+Shift+= grows text")
            check(panel.textKey({key:Qt.Key_Minus,modifiers:Qt.ControlModifier}) && panel.textStep===1 && panel.notice==="Text size 110%","Ctrl+- shrinks text")
            check(panel.textKey({key:Qt.Key_0,modifiers:Qt.ControlModifier}) && panel.textStep===0 && panel.notice==="Text size 100%","Ctrl+0 restores text")
            check(!panel.textKey({key:Qt.Key_Equal,modifiers:0}) && panel.textStep===0,"plain = ignored")
            check(!panel.textKey({key:Qt.Key_Plus,modifiers:Qt.ShiftModifier}) && panel.textStep===0,"plain + ignored")
            check(!panel.textKey({key:Qt.Key_Minus,modifiers:0}) && panel.textStep===0,"plain - ignored")
            check(!panel.textKey({key:Qt.Key_0,modifiers:0}) && panel.textStep===0,"plain 0 ignored")
            check(!panel.textKey({key:Qt.Key_Equal,modifiers:Qt.ControlModifier|Qt.AltModifier}) && panel.textStep===0,"Ctrl+Alt ignored")
            check(!panel.textKey({key:Qt.Key_Equal,modifiers:Qt.ControlModifier|Qt.MetaModifier}) && panel.textStep===0,"Ctrl+Meta ignored")
            check(!panel.textKey({key:Qt.Key_R,modifiers:Qt.ControlModifier}) && panel.textStep===0,"other Ctrl key ignored")
            panel.setTextStep(99)
            check(panel.textStep===5 && panel.fBody===Math.round(Style.font.body*1.5) && panel.notice==="Text size 150%","upper text size bound")
            panel.setTextStep(-99)
            check(panel.textStep===-3 && panel.notice==="Text size 70%","lower text size bound")
            panel.setTextStep(-4)
            check(panel.textStep===-3 && panel.notice==="Text size 70%","minus four clamps to minus three")
            panel.setTextStep(0)
            check(panel.fBody===Style.font.body && panel.notice==="Text size 100%","reset restores theme body")
            menuFile.reload()
            check(!panel.opened && panel.polling.requests===0,"registration does not open or poll")
            if (Quickshell.env("MENU_SCENARIO") === "fresh")
                check(menuFile.text().indexOf('"apps.github-actions"') >= 0,"registered while closed")
            panel.polling=Polling.create()
            panel.polling.repos=[{repo:"one/repo"},{repo:"two/repo"}]; reseed()
            check(panel.entries.length===2,"seeded repositories")
            panel.polling.repos[0].runs=[{id:7,name:"CI",status:"in_progress",run_attempt:1,html_url:"https://github.com/one/repo/actions/runs/7"}]
            panel.polling.expanded={"repo:one/repo":true}
            reseed()
            panel.move(1)
            check(panel.current.kind==="run","keyboard selection")
            panel.polling.repos[0].runs[0].run_started_at=new Date(panel.now-5000).toISOString()
            reseed()
            var tickKey=panel.current.key, tickCursor=panel.cursor, tickScroll=JSON.parse(panel.status()).scrollY
            panel.now=panel.now+3000
            check(panel.current.info==="8s","running duration ticks with now")
            check(panel.current.key===tickKey && panel.cursor===tickCursor,"tick keeps selection")
            check(JSON.parse(panel.status()).scrollY===tickScroll,"tick keeps scroll")
            var savedRuns=panel.polling.repos[0].runs
            panel.polling.repos[0].runs=[]
            reseed()
            var poll=JSON.parse(panel.status())
            check(poll.pollSelected===panel.current.repo && poll.pollInspected===(panel.current.run||""),"polling follows the highlight")
            check("remaining" in poll && "resetAt" in poll,"status has quota fields")
            panel.polling.repos[0].runs=savedRuns
            reseed()
            // #42: an emptied expanded repo shows a "Loading runs…" row, so the cursor may already be back on the run.
            if (panel.current.kind!=="run") panel.move(-1)
            check(panel.current.kind==="run","cursor back on the run")
            panel.enter()
            check(panel.entries[2].title==="Loading jobs…","enter opens collapsed run")
            panel.enter()
            check(panel.current.parent==="one/repo:7","enter moves to first child")
            var child=panel.current.key
            panel.enter()
            check(panel.current.key===child,"enter leaves a message row alone")
            panel.move(-1)
            panel.expand(true)
            panel.expand(false)
            check(panel.entries[2].title==="Loading jobs…","expand run")
            panel.expand(true)
            check(panel.entries.length===3,"collapse run retains other repository")
            panel.filterText="no-match"
            check(panel.entries.length===0,"filter")
            panel.filterText="repo"
            check(panel.cursor===0 && panel.entries.length===3 && panel.entries[1].key==="one/repo:7","expansion survives filtering")
            panel.polling.error=""
            panel.polling.catalogueBlocked="Catalogue blocked"
            reseed()
            check(panel.statusInfo.text.indexOf("Catalogue blocked")>=0 && panel.statusInfo.urgent,"blocked catalogue remains urgent while filtering")
            panel.polling.catalogueBlocked=""
            reseed()
            panel.move(1)
            panel.filterText=""
            check(panel.current.key==="one/repo:7","clearing the filter keeps the selected row")
            panel.click(1)
            check(panel.cursor===1 && panel.entries[2].title==="Loading jobs…","click selects and opens a run")
            panel.click(1)
            check(panel.entries.length===3,"second click collapses it")
            panel.click(0)
            check(panel.cursor===0 && panel.entries.length===2,"click toggles a repository")
            panel.filterText="repo"
            panel.expand(false)
            check(panel.entries.length===3,"expand repository again")
            panel.move(1)
            panel.expand(false)
            panel.page(1)
            check(panel.cursor>1 && panel.cursor<panel.entries.length,"page down moves within short list")
            panel.page(-1)
            check(panel.cursor>=0 && panel.cursor<panel.entries.length,"page up stays in range")
            var originalRuns=panel.polling.repos[0].runs
            panel.polling.repos[0].runs=Array.from({length:40},function(_,i) { return {id:100+i,name:"Long run " + i,status:"completed",conclusion:"success",head_branch:i%2 ? "main" : ""} })
            reseed()
            panel.cursor=0
            panel.page(1)
            check(panel.cursor>0 && panel.cursor<panel.entries.length,"page down advances on long list")
            panel.move(panel.entries.length)
            check(panel.cursor===panel.entries.length-1,"move reaches long-list bottom")
            panel.page(1)
            check(panel.cursor===panel.entries.length-1,"page down stays at bottom")
            panel.page(-1)
            check(panel.cursor<panel.entries.length-1 && panel.cursor>=0,"page up advances through mixed row heights")
            panel.filterText="Long run 39"
            panel.move(1)
            var lowKey=panel.current.key
            panel.filterText=""
            var view=panel.listView
            view.forceLayout()
            var lowItem=panel.itemAt(panel.cursor)
            check(panel.current.key===lowKey && lowItem && lowItem.y>=view.contentY && lowItem.y<view.contentY+Math.max(1,view.height),
                "clearing a filter keeps a low selected row visible")
            panel.filterText="repo"
            panel.polling.repos[0].runs=originalRuns
            reseed()
            panel.move(-panel.entries.length)
            at("one/repo:7")
            selected=panel.current.key
            panel.open()
            stage=1
        }
    }
    Timer {
        interval: 250; running: true; repeat: true
        onTriggered: {
            if(stopped()) return
            if(stage===1 && !copyChecked && panel.polling.requests>=6 && panel.details["one/repo:7"] && panel.polling.catalogueComplete) {
                at("one/repo:7")
                panel.enter()
                check(panel.current.kind==="job","enter moves into loaded run")
                // Like Right: the first press opens a collapsed job, the next one enters it.
                if (!panel.expanded[panel.current.key]) panel.enter()
                panel.enter()
                check(panel.current.kind==="step","enter moves into loaded job")
                var step=panel.current.key
                panel.enter()
                check(panel.current.key===step,"enter leaves step alone")
                var stepIndex=panel.cursor
                at("one/repo:7")
                panel.click(stepIndex)
                check(panel.current.key===step && !panel.expanded[step],"click selects a step without toggling")
                panel.confirm={text:"x",repo:"one/repo",run:"7"}
                panel.click(0)
                check(panel.current.key===step,"click does nothing while a confirmation is open")
                panel.confirm=null
                at("one/repo:7")
                panel.copyLink()
                if (Quickshell.env("MENU_SCENARIO") === "fresh") {
                    panel.copyLink()
                    check(panel.notice==="Copy in progress","second copy refused while running")
                    stage=6
                } else {
                    stage=8
                }
            } else if(stage===6 && panel.notice==="Copied link") {
                at("one/repo:7")
                panel.copyLink()
                stage=7
            } else if(stage===7 && panel.notice==="Copy failed (exit 3)") {
                at("repo:two/repo")
                panel.enter()
                at("repo:two/repo:message")
                panel.copyLink()
                check(panel.notice==="Nothing to copy","message has no copyable link")
                panel.polling.repos[0].hidden={queued:1}
                panel.adopt()
                at("repo:one/repo:more")
                panel.copyLink()
                check(panel.notice==="Nothing to copy","more row has no copyable link")
                panel.polling.repos[0].hidden={}
                panel.polling.repos[0].recentFetched=10
                panel.adopt()
                at("repo:one/repo")
                // Polling.more() waits while a summary is queued for the repo (step 9); clear it so m is tested alone.
                delete panel.polling.tasks["summary:one/repo:"]
                panel.loadMore()
                check(!!(panel.polling.tasks["more:one/repo:"] || (panel.polling.flight && panel.polling.flight.key === "more:one/repo:")),"m queues one more task")
                at(selected)
                copyChecked=true
                stage=1
            } else if(stage===8 && panel.notice==="Install wl-clipboard to copy links") {
                at(selected)
                copyChecked=true
                stage=1
            } else if(stage===1 && copyChecked) {
                if (zoomStage===0) {
                    zoomRepos=panel.polling.repos
                    zoomOriginalExpanded=panel.polling.expanded
                    panel.filterText="o/r"
                    panel.polling.repos=zoomRepos.concat(Array.from({length:40},function(_,i) { return {repo:"o/r"+i} }))
                    panel.polling.expanded={"repo:one/repo":true}
                    panel.adopt()
                    panel.move(panel.entries.length)
                    zoomKey=panel.current.key
                    zoomExpanded=JSON.stringify(panel.expanded)
                    zoomFilter=panel.filterText
                    panel.setTextStep(5)
                    zoomStage=1
                    stage=20  // #48 zoom stage; 10-12 belong to #44's watch stages
                    return
                }
                if (!accChecked) {
                    panel.move(0)
                    var item=panel.itemAt(panel.cursor)
                    if (!item) return
                    check(item.accessibleName.indexOf(panel.current.title)>=0,"accessible name holds the title")
                    check(item.Accessible.role===Accessible.ListItem && item.Accessible.name===item.accessibleName,"delegate accessibility role and name")
                    check(item.Accessible.selected===true && item.Accessible.focusable===true,"selected row is accessible-selected")
                    var other=panel.itemAt(panel.cursor===0 ? 1 : 0)
                    check(!other || other.Accessible.selected===false,"other rows are not selected")
                    accChecked=true
                }
                if (!healthChecked) {
                    // #43: a failing repository sorts first. Seeded and undone inside one turn so polling never sees it.
                    var two=panel.polling.repos[1], expect="✕ 3h · 12 running · stale"
                    two.checked=Date.now(); two.active=12
                    two.last={id:1,conclusion:"failure",at:new Date(panel.now-3*3600000-300000).toISOString(),confirmedAt:panel.now-31*60000}
                    panel.adopt()
                    var failing=panel.entries.find(function(row) { return row.key==="repo:two/repo" })
                    check(panel.entries[0].key==="repo:two/repo" && failing.info===expect && failing.status==="failure","failing repository first with its result")
                    panel.listView.forceLayout()
                    var failItem=panel.itemAt(0), infoText=failItem && textWith(failItem, expect)
                    check(infoText,"failing row rendered")
                    // The info Text caps at 0.35 of the list width; 640 px leaves 224 px.
                    check(infoText.implicitWidth<=0.35*640,"longest repository info fits a 640 px panel (" + infoText.implicitWidth + ")")
                    delete two.last; delete two.active; delete two.checked
                    panel.adopt()
                    check(panel.current.key===selected,"seeding the failing row keeps the selection")
                    healthChecked=true
                }
                check(panel.error==="","async API has no error")
                check(panel.current.key===selected && panel.filterText==="repo","poll preserves searched selection")
                check(panel.details["one/repo:7"].jobs[0].steps.length===1,"jobs and steps arrive")
                check(panel.polling.catalogueComplete,"catalogue completed")
                ensureRun9()
                // Offered keys come from the raw run, not the row status.
                at("one/repo:9")
                panel.askAction("cancel")
                check(panel.confirm===null && panel.actionText==="Only an unfinished run can be cancelled","cancel refused on a finished run")
                at("one/repo:7")
                panel.askAction("rerun")
                check(panel.confirm===null && panel.actionText==="Only a finished run can be rerun","rerun refused on a running run")
                panel.askAction("rerun-failed")
                check(panel.confirm===null && panel.actionText==="Rerun failed needs a failed run","rerun-failed refused on a running run")
                at("repo:one/repo")
                panel.askAction("rerun")
                check(panel.confirm===null && panel.actionText==="Select a run to rerun or cancel","repo row refused")
                at("one/repo:9")
                panel.polling.repos[0].runs=panel.polling.repos[0].runs.filter(function(run) { return run.id!==9 })
                panel.askAction("rerun")
                check(panel.confirm===null && panel.actionText==="Select a run to rerun or cancel","missing run refused")
                ensureRun9()
                // The confirmation is pinned to strings: moving and rebuilding cannot change the target.
                at("one/repo:9")
                panel.askAction("rerun-failed")
                check(panel.confirm && panel.confirm.repo==="one/repo" && panel.confirm.run==="9","confirmation pinned to run 9")
                at("one/repo:7")
                panel.adopt()
                panel.rebuild()
                check(panel.confirm && panel.confirm.run==="9","pin survives polling and cursor moves")
                panel.answer(false)
                check(panel.confirm===null && !panel.actionBusy,"n clears the confirmation")
                panel.polling.cooldown=Date.now()+60000
                at("one/repo:9")
                panel.askAction("rerun")
                check(panel.confirm===null && panel.actionText.indexOf("GitHub paused until")===0,"cooldown refuses a write")
                panel.polling.cooldown=0
                // Open-panel success on run 7, then move away so touch() must use the pinned strings.
                at("one/repo:7")
                panel.askAction("cancel")
                check(panel.confirm && panel.confirm.run==="7","cancel asks first")
                panel.answer(true)
                check(panel.actionBusy && panel.confirm===null,"write is running")
                panel.askAction("cancel")
                check(panel.actionText==="An action is already running","second write refused while busy")
                at("repo:one/repo")
                stage=5
            } else if(stage===20) {
                checkZoomLayout()
                if (zoomStage===1) { panel.now=panel.now+3000; zoomStage=2; return }
                if (zoomStage===2) { panel.setTextStep(-3); zoomStage=3; return }
                if (zoomStage===3) { panel.setTextStep(0); zoomStage=4; return }
                panel.polling.repos=zoomRepos
                panel.polling.expanded=zoomOriginalExpanded
                panel.adopt()
                panel.filterText="repo"
                at(selected)
                stage=1
            } else if(stage===5 && !panel.actionBusy) {
                check(panel.actionText.indexOf("Cancel requested")===0 && !panel.actionError,"cancel result shown")
                check(touchSeen,"touch used the pinned repository and run")
                panel.receiveAction('{"requestId":999,"ok":true}', {requestId:1,repo:"one/repo",run:"55",done:"x"})
                check(panel.actionError && panel.actionText.indexOf("Outcome unknown")===0 && !panel.polling.tasks["run:one/repo:55"],"wrong request id is unknown")
                panel.receiveAction("not json", {requestId:1,repo:"one/repo",run:"55",done:"x"})
                check(panel.actionError && panel.actionText.indexOf("Outcome unknown")===0 && !panel.polling.tasks["run:one/repo:55"],"bad json is unknown")
                panel.actionInfo={requestId:50,repo:"one/repo",run:"9",done:"x"}
                panel.actionBusy=true
                panel.actionFailedToStart()
                check(!panel.actionBusy && panel.actionError && panel.actionText==="python3 not found","failed start reports setup")
                ensureRun9()
                at("one/repo:9")
                panel.askAction("rerun")
                check(panel.confirm!==null,"not busy after a failed start")
                panel.answer(false)
                // A write in flight when the panel closes still finishes.
                panel.askAction("rerun")
                panel.answer(true)
                check(panel.actionBusy,"second write running")
                panel.close()
                stage=4
            } else if(stage===4 && !panel.actionBusy) {
                panel.open()
                check(panel.actionText.indexOf("Rerun requested")===0 && !panel.actionError,"result of a write sent before close is kept")
                check(JSON.parse(panel.status()).actionBusy===false,"status shows no write")
                panel.setTextStep(2)
                panel.close()
                closedRequests=panel.polling.requests
                closedAt=Date.now()
                stage=2
            } else if(stage===2 && Date.now()-closedAt>1200) {
                check(!panel.workerBusy && !panel.polling.flight,"close settles worker")
                check(panel.polling.requests===closedRequests,"closed panel starts no requests")
                var history=panel.polling.starts.length
                panel.open()
                check(panel.polling.starts.length>=history,"reopen preserves budget")
                check(panel.textStep===2,"reopen preserves text size")
                panel.setTextStep(0)
                ensureRun9()
                at("one/repo:7")
                panel.viewLog()
                check(panel.notice==="Select a job to read its log","v on a running run says so with a filter set")
                at("one/repo:9")
                panel.viewLog()
                check(panel.notice==="Fetching log…","v starts a log fetch")
                stage=9
            } else if(stage===9 && panel.polling.log===null && !panel.workerBusy && launched()) {
                // #44: a watched run keeps polling with the panel closed, and only run requests start.
                at("one/repo:7")
                panel.toggleWatch()
                check(panel.notice==="Watching this run; lost if the shell restarts" && panel.watching,"w watches an unfinished run")
                var watchedItem=panel.itemAt(panel.cursor)
                check(!!watchedItem && watchedItem.accessibleName.indexOf(", watching")>0,"watched row is described as watching")
                panel.polling.watches["one/repo:7"].at=0
                panel.close()
                closedRequests=panel.polling.requests
                stage=10
            } else if(stage===10 && panel.polling.requests>closedRequests && !panel.workerBusy) {
                check(panel.watching && !notified(),"a running watched run keeps its watch")
                flagProc.running=true
                stage=11
            } else if(stage===11 && flagReady && !panel.workerBusy && notified()) {
                check(!panel.watching && !panel.opened,"the watch ends when the run completes")
                closedRequests=panel.polling.requests
                closedAt=Date.now()
                stage=12
            } else if(stage===12 && Date.now()-closedAt>1200) {
                check(panel.polling.requests===closedRequests,"polling stops once nothing is watched")
                stage=3
            } else if(stage===3 && !panel.workerBusy) {
                console.log("QML_CHECKS_PASSED")
                Qt.quit()
            }
        }
    }
}
'''

# Key run: the panel is driven only by real key presses; QML just reports its state.
KEYS_QML = '''
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
ShellRoot {
    ActionsPanel { id: panel }
    FileView {
        id: menuFile
        path: Quickshell.env("HOME") + "/.config/omarchy/extensions/omarchy-menu.jsonc"
        watchChanges: true
        blockLoading: true
        printErrors: false
        onFileChanged: reload()
    }
    property int seq: 0
    property string previous: ""
    property bool seeded: false
    Timer {
        interval: 50; running: true; repeat: true
        onTriggered: {
            if (!seeded) {
                menuFile.reload()
                if (Quickshell.env("MENU_SCENARIO") === "fresh" && menuFile.text().indexOf('"apps.github-actions"') < 0) return
                if (panel.opened || panel.polling.requests !== 0) throw new Error("registration opened or polled")
                seeded = true
                panel.polling.repos = [{repo:"one/repo"},{repo:"two/repo"}]
                panel.adopt()
                panel.open()
            }
            var state = Object.assign(JSON.parse(panel.status()), {
                cursor: panel.cursor, info: panel.current ? panel.current.info : "",
                auth: panel.polling.auth, layout: JSON.parse(panel.layout()),
                stubBackground: Commons.Color.background.toString()
            })
            var body = JSON.stringify(state)
            if (body !== previous) {
                previous = body
                state.seq = ++seq
                state.t = Date.now() / 1000
                console.log("STATE " + JSON.stringify(state))
            }
        }
    }
}
'''


def collect(proc, lines, states=None):
    def read():
        for line in proc.stdout:
            lines.append(line.rstrip())
            if states is not None and 'STATE ' in line:
                try:
                    states.put(json.loads(line.split('STATE ', 1)[1]))
                except json.JSONDecodeError:
                    pass
    threading.Thread(target=read, daemon=True).start()


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def start_session(home, path, deadline):
    directory = Path(tempfile.mkdtemp(prefix='actions-sway-'))
    os.chmod(directory, 0o700)
    conf = directory / 'sway.conf'
    conf.write_text('output HEADLESS-1 resolution 1280x720 position 0 0\n')
    env = {'XDG_RUNTIME_DIR': str(directory), 'HOME': str(home), 'PATH': path,
           'WLR_BACKENDS': 'headless', 'WLR_RENDERER': 'pixman',
           'WLR_LIBINPUT_NO_DEVICES': '1'}
    sway_lines = []
    sway = None
    try:
        sway = subprocess.Popen(['sway', '-c', str(conf)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        collect(sway, sway_lines)
        while time.monotonic() < deadline:
            wayland = [p for p in directory.glob('wayland-*') if p.is_socket()]
            ipc = [p for p in directory.glob('sway-ipc.*.sock') if p.is_socket()]
            if wayland and ipc:
                for socket in (wayland[0], ipc[0]):
                    if socket.resolve().parent != directory.resolve():
                        raise RuntimeError('refusing to run: compositor socket outside the private directory')
                child_env = {**env, 'WAYLAND_DISPLAY': wayland[0].name,
                             'QT_QPA_PLATFORM': 'wayland', 'QT_QUICK_BACKEND': 'software'}
                return directory, sway, sway_lines, ipc[0], child_env
            if sway.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError('timeout starting private sway: ' + '\n'.join(sway_lines[-30:]))
    except BaseException:
        stop(sway)
        shutil.rmtree(directory)
        raise


def layout_error(state):
    lay, rows = state['layout'], state['rows']
    if rows <= 0:
        return None
    if not (lay['listWidth'] > 0 and lay['listHeight'] > 0):
        return 'layout: empty (zero-size) list'
    if lay['count'] != rows:
        return f"layout: list count {lay['count']} != rows {rows}"
    mine = [r for r in lay['rows'] if r['key'] == state['selected']]
    if not mine:
        return 'layout: selected row has no delegate'
    r = mine[0]
    if not (r['w'] > 0 and r['h'] > 0 and r['x'] >= 0 and r['x'] + r['w'] <= lay['listWidth']
            and r['y'] >= -0.5 and r['y'] + r['h'] <= lay['listHeight'] + 0.5):
        return f'layout: selected row outside the list: {r}'
    ordered = sorted(lay['rows'], key=lambda row: row['i'])
    for a, b in zip(ordered, ordered[1:]):
        if a['y'] + a['h'] > b['y'] + 0.5:
            return f'layout: rows overlap: {a} {b}'
    return None


def check_layout(state, fail):
    error = layout_error(state)
    if error:
        fail(error)


TIMELINE = []  # key run: when each stage was scheduled and when its state matched


def K(*names):
    return [arg for name in names for arg in ('-k', name)]


def CTRL(name):
    return ['-M', 'ctrl', '-k', name, '-m', 'ctrl']


for scenario in ('fresh', 'managed'):
    deadline = time.monotonic() + 150
    with tempfile.TemporaryDirectory(prefix='actions-qml-') as temporary:
        root = Path(temporary)
        stubs = Path(__file__).resolve().parent / 'stubs'
        for name in ('Commons', 'Ui'):
            (root / name).symlink_to(stubs / name)
        for name in ('ActionsPanel.qml', 'ActionsModel.js', 'Polling.js', 'menu.py', 'menu.example.json'):
            (root / name).symlink_to(source / name)
        (root / 'actions.py').write_text(FAKE)
        home = root / 'home'
        home.mkdir()
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'python3').symlink_to(shutil.which('python3'))
        # Stubs record their argv, one argument per line; the test never launches a terminal or notification.
        for stub in ('omarchy-launch-tui', 'notify-send'):
            (bin_dir / stub).write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$HOME/' + stub + '.log"\n')
            (bin_dir / stub).chmod(0o755)
        if scenario == 'fresh':
            (bin_dir / 'wl-copy').write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$HOME/wl-copy.log"
sleep 0.6
if test "$(wc -l < "$HOME/wl-copy.log")" -eq 1; then exit 0; else exit 3; fi
''')
            (bin_dir / 'wl-copy').chmod(0o755)
        menu_path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        if scenario == 'managed':
            menu_path.parent.mkdir(parents=True)
            (home / 'managed-menu').write_text('{}\n')
            menu_path.symlink_to(home / 'managed-menu')
        session = None
        quickshell = None
        sway_lines = []
        try:
            directory, session, sway_lines, ipc, base_env = start_session(home, os.environ['PATH'], deadline)
            menu_path_env = {'MENU_SCENARIO': scenario}

            # --- Run 1: programmatic feature checks ---
            (root / 'shell.qml').write_text(FEATURES_QML)
            env = {**base_env, **menu_path_env, 'EXPECTED_BACKGROUND': STUB_BACKGROUND,
                   'PATH': str(bin_dir) + (os.pathsep + base_env['PATH'] if scenario == 'fresh' else '')}
            try:
                result = subprocess.run([QUICKSHELL, '-p', str(root), '--no-color'], capture_output=True, text=True,
                                        timeout=50, env=env)
            except subprocess.TimeoutExpired as error:
                print(error.stdout, error.stderr, '\n'.join(sway_lines[-30:]))
                raise
            output = result.stdout + result.stderr
            if result.returncode or 'QML_CHECKS_PASSED' not in output or any(
                    term in output for term in ('ERROR:', 'ReferenceError', 'TypeError', 'CHECK FAILED')):
                print(output)
                raise SystemExit(f'{scenario}: QML feature checks failed')
            assert len((home / 'log-req.log').read_text().splitlines()) == 1
            assert (home / 'omarchy-launch-tui.log').read_text().splitlines() == ['--app-id=org.omarchy.github-actions-log', 'python3', str(root / 'actions.py'), 'view', str(home / 'fake-log.txt')], (home / 'omarchy-launch-tui.log').read_text()
            assert (home / 'notify-send.log').read_text().splitlines() == ['--app-name=GitHub Actions', '--', 'succeeded', 'one/repo · CI'], (home / 'notify-send.log').read_text()
            assert (home / 'closed-kinds.log').read_text().splitlines() == ['run'], (home / 'closed-kinds.log').read_text()
            sent = [json.loads(line) for line in (home / 'act.log').read_text().splitlines()]
            if scenario == 'fresh':
                assert (home / 'wl-copy.log').read_text().splitlines() == ['-- https://github.com/one/repo/actions/runs/7'] * 2
            assert [(task['action'], task['repo'], task['run']) for task in sent] == [('cancel', 'one/repo', '7'), ('rerun', 'one/repo', '9')], sent
            if scenario == 'managed':
                assert 'GitHub Actions menu registration failed:' in output and 'Menu is managed:' in output
                assert menu_path.is_symlink() and menu_path.read_text() == '{}\n'
            else:
                assert 'menu registration failed' not in output
                assert '"apps.github-actions"' in menu_path.read_text()
            (home / 'run-done').unlink(missing_ok=True)
            print(f'{scenario}: feature checks passed')

            # --- Run 2 (and failure runs): real key presses ---
            (root / 'shell.qml').write_text(KEYS_QML)

            def run_keys(label, extra_env, body):
                TIMELINE.clear()
                shell_lines = []
                states = queue.Queue()
                last = [None]
                env = {**base_env, **menu_path_env, **extra_env}
                proc = subprocess.Popen([QUICKSHELL, '-p', str(root), '--no-color'], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                collect(proc, shell_lines, states)

                def fail(what):
                    raise AssertionError(f'{scenario}/{label}: {what}; last state={last[0]!r}\n'
                                         f'sway output:\n{chr(10).join(sway_lines[-30:])}\n'
                                         f'quickshell output:\n{chr(10).join(shell_lines[-40:])}'
                                         + ('\nkey timeline (scheduled vs matched):\n' + '\n'.join(TIMELINE) if TIMELINE else ''))

                def wait_state(what, pred, after_seq=0, timeout=10):
                    end = min(deadline, time.monotonic() + timeout)
                    while time.monotonic() < end:
                        try:
                            state = states.get(timeout=0.1)
                        except queue.Empty:
                            if proc.poll() is not None:
                                fail(what + ': quickshell exited')
                            continue
                        last[0] = state
                        if state['seq'] > after_seq and pred(state):
                            return state
                    fail(what + ': timeout')

                try:
                    body(env, wait_state, fail, last, states)
                finally:
                    stop(proc)
                return shell_lines

            def main_keys(env, wait_state, fail, last, states):
                steady = wait_state('stubs load', lambda s: s['stubBackground'] == STUB_BACKGROUND and s['opened']
                                    and s['rows'] == 2 and s['selected'] == 'repo:one/repo' and s['requests'] >= 2
                                    and not s['inFlight'] and s['layout']['listHeight'] > 0, timeout=20)
                print(f'{scenario}: stubs load')
                # get_tree may omit layer-shell surfaces; the probe key transition is the focus check.
                subprocess.run(['swaymsg', '-s', str(ipc), '-t', 'get_tree'], env=env, capture_output=True,
                               text=True, timeout=3)
                one, two = 'repo:one/repo', 'repo:two/repo'
                sel = lambda key: lambda p, s: s['selected'] == key
                steps = [
                    ('readiness: probe j', K('j'), lambda p, s: s['cursor'] == 1 and s['selected'] == two, 500),
                    ('readiness: probe k', K('k'), lambda p, s: s['cursor'] == 0 and s['selected'] == one, 2000),
                    ('r', K('r'), lambda p, s: s['requests'] > p['requests'], 1500),
                    ('R', ['-M', 'shift', '-k', 'r', '-m', 'shift'], lambda p, s: s['requests'] > p['requests'], 1500),
                    ('Down', K('Down'), sel(two), 400),
                    ('Up', K('Up'), sel(one), 400),
                    ('End', K('End'), sel(two), 400),
                    ('Home', K('Home'), sel(one), 400),
                    ('Right', K('Right'), lambda p, s: s['rows'] > 2 and s['selected'] == one, 500),
                    ('Left', K('Left'), lambda p, s: s['rows'] == 2 and s['selected'] == one, 500),
                    ('Return', K('Return'), lambda p, s: s['rows'] > 2 and s['selected'] == one, 500),
                    ('Left again', K('Left'), lambda p, s: s['rows'] == 2, 500),
                    ('/', K('slash'), lambda p, s: s['editing'], 400),
                    ('type one', K('o', 'n', 'e'), lambda p, s: s['filter'] == 'one' and s['editing'], 400),
                    ('Escape in search', K('Escape'), lambda p, s: s['filter'] == '' and not s['editing'] and s['opened'], 400),
                    ('/ one Return', K('slash', 'o', 'n', 'e', 'Return'),
                     lambda p, s: s['filter'] == 'one' and not s['editing'] and s['rows'] > 1, 500),
                    ('Escape with filter', K('Escape'), lambda p, s: s['filter'] == '' and s['opened'] and s['rows'] > 2, 500),
                    ('Ctrl+=', CTRL('equal'), lambda p, s: s['textStep'] == 1, 500),
                    ('Ctrl+0', CTRL('0'), lambda p, s: s['textStep'] == 0, 500),
                    ('g', K('End') + ['-s', '300'] + K('g'), lambda p, s: s['cursor'] == 0, 300),
                    ('walk j', K(*['j'] * 35), None, 150),
                    ('Home', K('Home'), lambda p, s: s['cursor'] == 0, 400),
                    ('End', K('End'), lambda p, s: s['cursor'] == s['rows'] - 1
                     and s['layout']['contentHeight'] > s['layout']['listHeight'] and s['scrollY'] > 0, 400),
                    ('G', K('Home') + ['-s', '300'] + K('G'), lambda p, s: s['cursor'] == s['rows'] - 1, 400),
                    ('j to run', K('g', 'j'), lambda p, s: s['cursor'] == 1 and s['selected'].startswith('one/repo:'), 400),
                    ('Return on run', K('Return'), lambda p, s: s['rows'] > p['rows'] and s['selected'] == p['selected'], 4500),
                    ('Escape closes', K('Escape'), lambda p, s: not s['opened'], 2000),
                ]
                # One wtype for the whole run: one virtual keyboard and one keymap (plan: option B).
                # The walk sends one j per pause; extra presses at the bottom change nothing.
                argv = ['wtype', '-s', '300']
                times, offset = {}, 0.3
                for label, keys, pred, pause in steps:
                    times[label] = offset
                    if label == 'walk j':
                        for _ in range(35):
                            argv += ['-k', 'j', '-s', str(pause)]
                            offset += pause / 1000
                    else:
                        argv += keys + ['-s', str(pause)]
                        offset += sum(int(keys[i + 1]) for i in range(len(keys)) if keys[i] == '-s') / 1000 + pause / 1000
                start = time.time()
                TIMELINE.clear()
                typist = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                try:
                    prev = steady
                    for label, keys, pred, pause in steps:
                        if label == 'walk j':
                            cur = prev
                            while cur['cursor'] < cur['rows'] - 1:
                                # Two presses can land between 50 ms samples, so any forward move counts.
                                nxt = wait_state('key walk j', lambda s, c=cur: s['cursor'] != c['cursor']
                                                 or s['layout'] != c['layout'], cur['seq'], timeout=3)
                                if nxt['cursor'] < cur['cursor']:
                                    fail(f"key walk j: cursor went back {cur['cursor']} -> {nxt['cursor']}")
                                check_layout(nxt, fail)
                                cur = nxt
                            if cur['rows'] < 27:
                                fail(f"walk: only {cur['rows']} rows; expected the expanded repository's 25 runs")
                            prev = cur
                            print(f'{scenario}: key walk j: {cur["rows"]} rows, layout checked on each')
                            continue
                        prev = wait_state(f'key {label}', lambda s, p=prev, f=pred: f(p, s), prev['seq'],
                                          timeout=times[label] - (time.time() - start) + 6)
                        if label.startswith('Ctrl+') and layout_error(prev):
                            # A size change relayouts on the next frame (Qt.callLater); judge the settled state.
                            step, first = prev['textStep'], layout_error(prev)
                            try:
                                prev = wait_state(f'key {label}: settled layout', lambda s: s['textStep'] == step
                                                  and not layout_error(s), prev['seq'], timeout=2)
                            except AssertionError:
                                fail(first)
                        check_layout(prev, fail)
                        # Open loop: a dead key shows up as a later stage failing; the timeline says which key it was.
                        TIMELINE.append(f"{label}: sent ~{times[label]:.1f}s, matched {prev['t'] - start:.1f}s")
                        print(f'{scenario}: key {label}')
                        if label == 'Return on run':
                            run_key, opened = prev['selected'], prev
                            # Duration tick: the selected run's info changes while selection and scroll stay.
                            ticked = wait_state('running duration ticks', lambda s: s['selected'] == run_key
                                                and s['scrollY'] == opened['scrollY'] and s['info'] != opened['info']
                                                and s['t'] - opened['t'] >= 1, opened['seq'], timeout=5)
                            wait_state('async arrival', lambda s: s['error'] == '' and not s['inFlight'], ticked['seq'] - 1, timeout=5)
                            prev = last[0]
                    closed = prev
                    time.sleep(1.5)
                    while True:
                        try:
                            last[0] = states.get_nowait()
                        except queue.Empty:
                            break
                finally:
                    stop(typist)
                log = [json.loads(line) for line in (root / 'fake.log').read_text().splitlines()]
                # A summary is a chain of pages; only its first page (status "recent") marks a new summary.
                chain = lambda e: e['kind'] == 'summary' and e['repo'] == 'one/repo' and e['status'] == 'recent'
                for label, match in (('r', chain), ('R', lambda e: e['kind'] == 'catalogue')):
                    t0 = start + times[label]
                    if not any(match(e) and t0 - 0.1 <= e['t'] <= t0 + 5 for e in log):
                        fail(f'key {label}: expected a new request within 5 s of the key; log={log[-12:]}')
                t0 = start + times['r']
                # Automatic summaries come 60 s apart, so one started in the 55 s before r rules them out of the window.
                if not any(chain(e) and t0 - 55 <= e['t'] < t0 - 0.1 for e in log):
                    fail('key r: no summary started before r, so an automatic one could explain the window')
                run_id = run_key.split(':')[-1]
                if not any(e['kind'] == 'jobs' and e['run'] == run_id for e in log):
                    fail(f'jobs for run {run_id} were never requested; log={log[-12:]}')
                if any(e['t'] > closed['t'] + 0.5 for e in log):
                    fail(f'closed panel started requests: {[e for e in log if e["t"] > closed["t"] + 0.5]}')
                if last[0]['requests'] != closed['requests'] or last[0]['opened']:
                    fail('closed panel changed its request count or reopened')
                print(f'{scenario}: refresh keys, jobs, duration tick and close checked')

            shell_lines = run_keys('keys', {'FAKE_LOG': str(root / 'fake.log'), 'FAKE_RUNS': '25'}, main_keys)
            if scenario == 'managed':
                assert any('GitHub Actions menu registration failed:' in line and 'Menu is managed:' in line
                           for line in shell_lines)
            if scenario == 'fresh':
                def settle(states, last, seconds):
                    time.sleep(seconds)
                    while True:
                        try:
                            last[0] = states.get_nowait()
                        except queue.Empty:
                            return last[0]

                def no_python(env, wait_state, fail, last, states):
                    seen = wait_state('helper cannot start', lambda s: s['opened'] and s['error'] == 'python3 not found'
                                      and not s['inFlight'] and s['auth'], timeout=15)
                    if settle(states, last, 2)['requests'] != seen['requests']:
                        fail('requests kept rising after the helper failed to start')
                    print('fresh: failure: helper cannot start')
                empty_bin = root / 'empty-bin'
                empty_bin.mkdir()
                run_keys('no python3', {'PATH': str(empty_bin)}, no_python)

                pid_file = root / 'fake.pid'

                def blocked(env, wait_state, fail, last, states):
                    busy = wait_state('request in flight', lambda s: s['opened'] and s['inFlight'] and pid_file.exists(), timeout=15)
                    pid = int(pid_file.read_text())
                    subprocess.run(['wtype', '-s', '300', '-k', 'Escape'], env=env, timeout=10, check=True)
                    shut = wait_state('Escape closes during a request', lambda s: not s['opened'] and not s['inFlight'], busy['seq'])
                    end = time.monotonic() + 3
                    while time.monotonic() < end:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            break
                        time.sleep(0.05)
                    else:
                        fail(f'helper {pid} still running after close')
                    pid_file.unlink()  # dead: never signal a pid that may be reused
                    if settle(states, last, 1.5)['requests'] != shut['requests']:
                        fail('closed panel started requests')
                    print('fresh: failure: close while a request runs')
                try:
                    run_keys('close during request', {'FAKE_MODE': 'block', 'FAKE_PID': str(pid_file),
                                                      'FAKE_LOG': str(root / 'block.log')}, blocked)
                finally:
                    if pid_file.exists():
                        try:
                            os.kill(int(pid_file.read_text()), 9)
                        except (ProcessLookupError, ValueError):
                            pass
            print('QML_CHECKS_PASSED')
        finally:
            stop(quickshell)
            stop(session)
            if session is not None:
                shutil.rmtree(directory)
