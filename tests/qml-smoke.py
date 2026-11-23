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
if os.path.exists(os.environ['HOME']+'/run-done') and not os.path.exists(os.environ['HOME']+'/reopened'): open(os.environ['HOME']+'/closed-kinds.log','a').write(kind+'\\n')
time.sleep(0.1)
run={'id':7,'name':'CI','status':'in_progress','run_attempt':1,'head_branch':'main','run_number':1,'html_url':'https://github.com/one/repo/actions/runs/7',
     'head_sha':'0123456789abcdef0123456789abcdef01234567','event':'push','actor':'octo','triggering_login':'octo','path':'.github/workflows/ci.yml'}
started=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-5))
runs=[run] if not os.environ.get('FAKE_RUNS') else [dict(run,id=i,run_number=i,run_started_at=started,html_url='https://github.com/one/repo/actions/runs/%d'%i) for i in range(7,7+int(os.environ['FAKE_RUNS']))]
error=''; error_type=''; resource='rest'; remaining=4000; reset_at=0
if kind=='catalogue': data=[{'repo':'one/repo'},{'repo':'two/repo'}]
elif kind=='jobs': data=[{'id':8,'name':'build','status':'in_progress','html_url':'https://github.com/one/repo/actions/runs/7/job/8','steps':[{'number':1,'name':'Checkout','status':'completed','conclusion':'success'}]}]
elif kind=='prs':
    resource='graphql'; remaining=4500; reset_at=int(time.time()*1000)+3600000
    login=open(os.environ['HOME']+'/account-login').read() if os.path.exists(os.environ['HOME']+'/account-login') else 'tester'
    if login!='tester': time.sleep(0.6)  # Let the 250 ms feature timer inspect the cleared state before this reply.
    if login=='tester':
        data={'list':[
            {'repo':'one/repo','number':101,'title':'Feature','branch':'feature','draft':False,'url':'https://github.com/one/repo/pull/101','sha':'a'*40,
             'checks':{'state':'pending','total':3,'items':[
                 {'name':'CI 9001','status':'completed','conclusion':'success','url':'https://github.com/one/repo/actions/runs/9001','repo':'one/repo','run':'9001'},
                 {'name':'CI 9002','status':'completed','conclusion':'failure','url':'https://github.com/one/repo/actions/runs/9002','repo':'one/repo','run':'9002'},
                 {'name':'External','status':'pending','conclusion':'','url':'https://example.com/check','repo':'','run':''}]}},
            {'repo':'two/repo','number':102,'title':'Draft work','branch':'draft','draft':True,'url':'https://github.com/two/repo/pull/102','sha':'b'*40,'checks':{'state':'none'}}],
              'total':2,'partial':False}
    else:
        data={'list':[{'repo':'one/repo','number':201,'title':'Other login','branch':'other','draft':False,'url':'https://github.com/one/repo/pull/201','sha':'c'*40,'checks':{'state':'none'}}], 'total':1,'partial':False}
elif kind=='run' and request.get('run')=='9002':
    data=None; error='Run unavailable'; error_type='permission'
elif kind=='run' and request.get('run')=='9001':
    data=dict(run,id=9001,run_number=9001,html_url='https://github.com/one/repo/actions/runs/9001',status='completed',conclusion='success')
elif kind=='run': data=dict(run,status='completed',conclusion='success') if os.path.exists(os.environ['HOME']+'/run-done') else runs[0]
elif kind=='account':
    switch=os.environ['HOME']+'/switch-login'
    login=open(switch).read().strip() if os.path.exists(switch) else 'tester'
    open(os.environ['HOME']+'/account-login','w').write(login)
    data={'login':login}
else: data=runs if request['repo']=='one/repo' and request.get('status','in_progress') in ('recent','in_progress') else []
reply=json.dumps({'requestId':request['requestId'],'data':data,'nextPage':0,'error':error,'errorType':error_type,
                  'resource':resource,'remaining':remaining,'resetAt':reset_at,'padding':'x'*200000}).encode()+b'\\n'
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
    FileView { id: requestLog; path: Quickshell.env("FAKE_LOG"); printErrors: false }
    // The fake answers the account request with this login once the file exists.
    // Ends the closed-panel request log before the pull-request stages reopen the panel.
    FileView { id: reopenedMark; path: Quickshell.env("HOME") + "/reopened"; blockWrites: true; printErrors: false }
    FileView { id: switchLogin; path: Quickshell.env("HOME") + "/switch-login"; blockWrites: true; printErrors: false }
    function requested(run) {
        requestLog.reload()
        return requestLog.text().split("\\n").some(function(line) {
            try { var entry=JSON.parse(line); return entry.kind==="run" && entry.run===run } catch (e) { return false }
        })
    }
    function switchTo(target) {
        var saved=panel.viewState[target]
        panel.switchView(target,saved.filter,saved.key)
        panel.selectionChanged(true)
        panel.pump()
    }
    function notified() { notifyFile.reload(); return notifyFile.text().split("\\n").length > 3 }
    FileView { id: notifyFile; path: Quickshell.env("HOME") + "/notify-send.log"; printErrors: false }
    property bool flagReady: false
    Process {
        id: flagProc
        command: ["python3", "-c", "import os;open(os.environ['HOME']+'/run-done','w')"]
        onExited: { panel.polling.watches["one/repo:7"].at = 0; panel.polling.wakeAt = 0; var task = panel.polling.tasks["run:one/repo:7"]; if (task) task.due = 0; var run = panel.polling.repos[0].runs.filter(function(r) { return r.id === 7 })[0]; if (run) delete run.followupAt; flagReady = true }  // both clocks: the watch and the 15 s follow-up
    }
    function launched() { launchFile.reload(); return launchFile.text().split("\\n").length > 5 }
    function check(value, label) { if (!value) throw new Error("CHECK FAILED: " + label) }
    function replyFaults() {
        var state = Polling.create()
        state.opened = true; state.generation = 1
        var task = Polling.ensure(state,"account","","","interactive",0)
        state.flight = {key:task.key,request:{requestId:900},generation:1}
        panel.polling = state; panel.requestInfo = {requestId:900}; panel.workerBusy = true
        panel.finishRequest({trim:function() { throw new Error("before complete fault") }},0)
        check(!panel.workerBusy && !state.flight && task.failures===1,"reply fault before complete clears the worker and retries")

        state = Polling.create()
        state.opened = true; state.generation = 1
        task = Polling.ensure(state,"account","","","interactive",0)
        state.flight = {key:task.key,request:{requestId:901},generation:1}
        state.notices = [{kind:"done",repo:"one/repo",name:{toString:function() { throw new Error("adopt fault") }}}]
        panel.polling = state; panel.requestInfo = {requestId:901}; panel.workerBusy = true
        panel.finishRequest(JSON.stringify({requestId:901,data:{login:"tester"},error:"",errorType:""}),0)
        check(!panel.workerBusy && !state.flight && state.accountChecked && state.notices.length===0,
            "reply fault inside adopt clears the worker without handling it twice")
    }
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
            replyFaults()
            panel.polling=Polling.create()
            panel.polling.repos=[{repo:"one/repo"},{repo:"two/repo"}]; reseed()
            check(panel.entries.length===2,"seeded repositories")
            // #46: the title shows a login only once this open verified it, and changes with the data in one adopt().
            panel.polling.account="alice"; panel.polling.accountVerified=false; panel.adopt()
            check(panel.titleText.indexOf("alice")<0,"pending lookup shows no account")
            panel.polling.account="bob"; panel.polling.accountVerified=true; panel.polling.repos=[]; panel.adopt()
            check(panel.titleText.indexOf("bob@github.com")>=0 && panel.repos.length===0,"title follows the verified account and the cleared data in one adopt()")
            panel.polling.account=""; panel.polling.accountVerified=false
            panel.adoptedAccount=""  // the synthetic logins above are not a real account change for later stages
            panel.polling.repos=[{repo:"one/repo"},{repo:"two/repo"}]; reseed()
            check(panel.entries.length===2 && panel.titleText.indexOf("@github.com")<0,"seed restored")
            panel.polling.repos[0].runs=[{id:7,name:"CI",status:"in_progress",run_attempt:1,html_url:"https://github.com/one/repo/actions/runs/7"}]
            panel.polling.expanded={"repo:one/repo":true}
            reseed()
            panel.move(1)
            check(panel.current.kind==="run","keyboard selection")
            check(!panel.detail,"pane starts closed")
            var seedRun=panel.polling.repos[0].runs[0]
            seedRun.head_sha="0123456789abcdef0123456789abcdef01234567"; seedRun.event="push"; seedRun.actor="octo"; seedRun.head_branch="main"
            panel.toggleDetail()
            check(panel.detailRows.length===9 && panel.detailRows[3].value==="0123456","pane shows the 7-character commit")
            check(panel.detailRows[2].value==="main" && panel.detailRows[4].value==="push" && panel.detailRows[5].value==="octo","branch, event and actor lines")
            check(panel.detailAccessibleName.indexOf("Run details")===0,"pane accessible name")
            panel.toggleDetail()
            panel.move(-1)
            panel.toggleDetail()
            check(panel.detailRows.length===1 && panel.detailRows[0].value==="Select a run","repo row shows Select a run")
            panel.toggleDetail()
            panel.move(1)
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
            panel.toggleDetail(); panel.handleEscape(true)
            check(!panel.detail && panel.filterText==="repo","search Esc closes the pane, keeps the filter")
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
            panel.toggleDetail()  // open while the popup opens, so its layout has settled by the stage-1 checks
            panel.open()
            check(panel.workerBusy && panel.polling.requests>0,"a later request starts after reply faults")
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
                var lv=panel.listView, pn=panel.detailPane, ft=panel.footerItem
                check(panel.opened && panel.detail && lv.height>0,"list non-empty with pane open")
                check(lv.y+lv.height<=pn.y && pn.y+pn.height<=ft.y,"list, pane and footer do not overlap")
                check(pn.height<=0.4*lv.parent.height+1,"pane within its share")
                // The stub card (680 px on a 1280x720 output) always has room, so the three-row rule is never skipped.
                check(pn.avail>=3*panel.rowMin+pn.line,"stub viewport has room for three rows and a pane line")
                check(lv.height>=3*panel.rowMin,"list keeps three rows")
                check(pn.Accessible.role===Accessible.Pane && pn.Accessible.name===panel.detailAccessibleName,"pane accessibility")
                check(panel.titleText.indexOf("tester@github.com")>=0,"title shows the account from the fake reply")
                panel.handleEscape(false)
                check(!panel.detail && panel.opened,"Esc closes the pane first, popup stays")
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
                reopenedMark.setText("1")
                panel.open()
                check(JSON.parse(panel.status()).view==="repos" && JSON.parse(panel.status()).prs===-1,"reopen starts in repositories before login")
                stage=30
            } else if(stage===30 && panel.polling.accountVerified && !panel.workerBusy) {
                at("one/repo:7")
                panel.filterText="repo"
                var repoKey=panel.current.key
                switchTo("prs")
                check(panel.view==="prs" && !panel.detail && panel.polling.selected==="","switch to pull requests clears repository selection")
                stage=31
            } else if(stage===31 && panel.polling.prs.list && panel.polling.prs.list.length===2) {
                var prState=JSON.parse(panel.status())
                check(prState.view==="prs" && prState.prs===2 && panel.titleText.indexOf("Pull requests")===0 && panel.titleText.indexOf("tester")>0,"pull request header and status")
                check(panel.statusInfo.quota.indexOf("GraphQL points")>0,"GraphQL quota shown")
                panel.filterText="Feature"
                at("pr:one/repo#101")
                switchTo("repos")
                check(panel.filterText==="repo" && panel.current.key==="one/repo:7","repository filter and key restored")
                panel.detail=true
                switchTo("prs")
                check(!panel.detail && panel.filterText==="Feature" && panel.current.key==="pr:one/repo#101","pull request filter and key restored; details closed")
                // p typed in search is covered with real keys in the keys run.
                at("pr:one/repo#101")
                panel.expand(false)
                at("pr:one/repo#101:2:External")
                panel.expand(false)
                check(panel.notice==="Not an Actions check","non-Actions check cannot jump")
                panel.openBrowser()
                check(panel.notice.indexOf("Link is not on github.com")===0,"external check link is refused")
                at("pr:one/repo#101:0:CI 9001")
                panel.expand(false)
                check(panel.view==="repos" && panel.jumpKey==="one/repo:9001","Actions check starts jump")
                stage=32
            } else if(stage===32 && requested("9001") && panel.jumpKey==="" && panel.current && panel.current.key==="one/repo:9001") {
                panel.listView.forceLayout()
                var item=panel.itemAt(panel.cursor)
                check(item && item.y>=panel.listView.contentY && item.y<panel.listView.contentY+panel.listView.height,"jumped run is visible")
                switchTo("prs")
                at("pr:one/repo#101:1:CI 9002")
                panel.enter()
                check(panel.jumpKey==="one/repo:9002","second Actions check starts jump")
                stage=33
            } else if(stage===33 && requested("9002") && panel.jumpKey==="" && panel.notice==="Run unavailable") {
                switchTo("prs")
                panel.filterText="Feature"
                check(panel.entries.some(function(row) { return row.key==="pr:one/repo#101" }),"old login rows present before reopen")
                switchLogin.setText("other")
                panel.close()
                panel.open()
                panel.jumpKey="old:9001"
                check(panel.view==="prs" && JSON.parse(panel.status()).prs===-1,"reopen retains pull request view but hides cached rows")
                stage=34
            } else if(stage===34 && panel.polling.accountVerified && panel.polling.account==="other" && panel.polling.prs.list===null) {
                check(panel.filterText==="" && panel.jumpKey==="" && panel.entries.length===0,"account change clears filter, jump and old rows before refresh")
                check(panel.viewState.repos.filter==="" && panel.viewState.prs.filter==="","account change clears both saved views")
                check(JSON.parse(panel.status()).prs===-1,"new login is loading")
                stage=35
            } else if(stage===35 && panel.polling.prs.list && panel.polling.prs.list.length===1) {
                check(panel.view==="prs" && panel.current.key==="pr:one/repo#201" && JSON.parse(panel.status()).prs===1,"new login rows replace old rows in same view")
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
                notice: panel.notice, title: panel.titleText, quota: panel.statusInfo.quota,
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

WIDGET_QML = r'''
import QtQuick
import Quickshell
import Quickshell.Io
import "Polling.js" as Polling
import "bar-widget" as BarPlugin
ShellRoot {
    QtObject { id: horizontal; property bool vertical: false }
    QtObject { id: verticalBar; property bool vertical: true }
    BarPlugin.BarWidget { id: a; bar: horizontal; statusPath: Quickshell.env("WIDGET_STATUS_PATH") }
    BarPlugin.BarWidget { id: b; bar: verticalBar; statusPath: Quickshell.env("WIDGET_STATUS_PATH") }
    Loader {
        id: fixture
        active: false
        sourceComponent: Component { ActionsPanel { statusPath: Quickshell.env("WIDGET_STATUS_PATH") } }
    }
    FileView { id: file; path: Quickshell.env("WIDGET_STATUS_PATH"); blockLoading: true; printErrors: false }
    FileView { id: writer; path: Quickshell.env("WIDGET_STATUS_PATH"); atomicWrites: true; blockWrites: true; printErrors: false }
    FileView { id: toggleLog; path: Quickshell.env("TOGGLE_LOG"); blockLoading: true; printErrors: false }
    Process {
        id: removeFile
        command: ["python3", "-c", "import os,sys; os.unlink(sys.argv[1])", Quickshell.env("WIDGET_STATUS_PATH")]
    }
    Process {
        id: pathChange
        property bool restore: false
        command: ["python3", "-c",
            "import os,sys; p=sys.argv[1]; os.rmdir(p) if sys.argv[2]=='restore' else (os.unlink(p),os.mkdir(p))",
            Quickshell.env("WIDGET_STATUS_PATH"), restore ? "restore" : "block"]
    }
    property int stage: 0
    property double entered: Date.now()
    property double countsAt: 0
    property double writtenAt: 0
    property string savedStatus: ""
    function check(ok, label) { if (!ok) { console.log("CHECK FAILED: " + label); Qt.exit(1); throw new Error("CHECK FAILED: " + label) } }
    function status() { file.reload(); try { return JSON.parse(file.text()) } catch (e) { return null } }
    function payload(state, stamp, cooldown) {
        return {version:1,instance:"test",account:"tester",state:state,running:2,failed:1,
            countsAt:stamp,cooldownUntil:cooldown || 0,reason:"",writtenAt:Date.now()}
    }
    function write(value) { writer.setText(JSON.stringify(value)+"\n") }
    function next() { stage++; entered=Date.now() }
    function ready(ok) {
        if (ok) return true
        check(Date.now()-entered<5000,"widget stage " + stage + " timeout")
        return false
    }
    Timer { interval: 50; running: true; repeat: true
        onTriggered: {
            var s=status(), p=fixture.item, button=a.children[0]
            if (stage===0) {
                check(a.statusView.state==="none" && b.statusView.state==="none","widgets start empty")
                check(button.text==="\uF09B" && button.dimmed,"empty widget label")
                fixture.active=true; next()
            } else if (stage===1) {
                if (!ready(p && s && s.state==="none" && s.instance)) return
                check(p.statusPath===Quickshell.env("WIDGET_STATUS_PATH"),"panel status path is isolated")
                p.workerBusy=true
                countsAt=Date.now()
                p.polling.countsAt=countsAt
                p.polling.repos=[{repo:"one/repo",active:2,checked:"x",
                    runs:[{id:7,status:"completed",conclusion:"failure"}],
                    last:{id:7,conclusion:"failure",at:new Date().toISOString(),confirmedAt:Date.now()}}]
                p.adopt(); next()
            } else if (stage===2) {
                if (!ready(s && s.state==="ok" && s.running===2 && s.failed===1 &&
                           a.statusView.state==="ok" && b.statusView.state==="ok")) return
                check(button.text==="\uF09B ●2 ✕1" && b.children[0].text==="\uF09B\n●2\n✕1","both widget labels")
                check(button.active && !button.dimmed && button.tooltipText.indexOf("2 running workflow runs, 1 failing repository")>=0,"widget counts and tooltip")
                check(button.Accessible.name===a.statusView.accessible,"widget accessible name")
                writtenAt=s.writtenAt
                p.adopt(); next()
            } else if (stage===3) {
                if (!ready(Date.now()-entered>300)) return
                check(status().writtenAt===writtenAt,"unchanged payload keeps writtenAt")
                p.polling.auth=true; p.polling.error="Bad credentials"; p.adopt(); next()
            } else if (stage===4) {
                if (!ready(s && s.state==="stopped" && a.statusView.state==="stopped")) return
                check(button.active && button.text.indexOf("!")>=0,"stopped is urgent")
                p.polling.auth=false; p.polling.error=""; p.polling.cooldown=Date.now()+10000; p.adopt(); next()
            } else if (stage===5) {
                if (!ready(s && s.state==="rate" && a.statusView.state==="rate")) return
                check(button.dimmed && s.running===2 && s.failed===1,"rate keeps last counts")
                p.polling.cooldown=0; p.adopt(); next()
            } else if (stage===6) {
                if (!ready(s && s.state==="ok" && a.statusView.state==="ok")) return
                var state=Polling.create(), now=Date.now()
                state.opened=false; state.discover=false; state.catalogueComplete=true
                state.catalogueAt=now; state.countsAt=now
                state.repos=[{repo:"one/repo",checked:"x",active:1,activeFromTotal:true,
                    runs:[{id:7,name:"CI",status:"in_progress"}]}]
                p.polling=state; p.noticeBusy=true
                check(Polling.watch(state,"one/repo","7","CI",now)==="on","closed watch starts")
                p.adopt(); countsAt=state.countsAt
                var request=Polling.next(p.polling,now+31000)
                check(request && request.kind==="run","closed watch requests a run")
                p.receivePage(JSON.stringify({requestId:request.requestId,data:{id:7,name:"CI",status:"completed",
                    conclusion:"success"},nextPage:0,error:"",errorType:"",remaining:4000}),request)
                check(p.polling.countsAt===countsAt,"closed run preserves countsAt")
                next()
            } else if (stage===7) {
                if (!ready(s && s.state==="ok" && s.running===0 && s.countsAt===countsAt &&
                           a.statusView.state==="ok")) return
                p.receiveAction(JSON.stringify({requestId:91,ok:false,error:"Rate limited",errorType:"rate",
                    retryAt:Date.now()+10000,remaining:0}),{requestId:91,done:"Rerun",repo:"one/repo",run:"7"})
                next()
            } else if (stage===8) {
                if (!ready(s && s.state==="rate" && a.statusView.state==="rate")) return
                p.polling.cooldown=0; p.polling.auth=true; p.polling.error="Stopped"; p.adopt(); next()
            } else if (stage===9) {
                if (!ready(s && s.state==="stopped")) return
                p.workerBusy=true; p.open(); next()
            } else if (stage===10) {
                if (!ready(s && s.state!=="stopped")) return
                p.close()
                savedStatus=p.lastStatus
                pathChange.restore=false; pathChange.running=true; next()
            } else if (stage===11) {
                if (!ready(!pathChange.running)) return
                p.polling.repos[0].active=3; p.adopt(); next()
            } else if (stage===12) {
                if (!ready(Date.now()-entered>400)) return
                check(p.lastStatus===savedStatus,"failed save remains unrecorded")
                pathChange.restore=true; pathChange.running=true; next()
            } else if (stage===13) {
                if (!ready(!pathChange.running)) return
                p.publishStatus(); next()
            } else if (stage===14) {
                if (!ready(s && s.running===3 && a.statusView.label.indexOf("●3")>=0)) return
                p.polling.auth=true; p.polling.error="Stopped"; p.adopt(); next()
            } else if (stage===15) {
                if (!ready(s && s.state==="stopped")) return
                fixture.active=false; next()
            } else if (stage===16) {
                if (!ready(!fixture.item && s && s.state==="none")) return
                write(payload("ok",Date.now(),0)); next()
            } else if (stage===17) {
                if (!ready(a.statusView.state==="ok" && b.statusView.state==="ok")) return
                write(payload("unknown",Date.now(),0)); next()
            } else if (stage===18) {
                if (!ready(a.statusView.state==="none" && b.statusView.state==="none")) return
                write(payload("rate",Date.now(),Date.now()+500)); next()
            } else if (stage===19) {
                if (!ready(a.statusView.state==="rate" && b.statusView.state==="rate")) return
                next()
            } else if (stage===20) {
                if (!ready(a.statusView.state==="ok" && b.statusView.state==="ok")) return
                removeFile.running=true; next()
            } else if (stage===21) {
                if (!ready(!removeFile.running && a.statusView.state==="none" && b.statusView.state==="none")) return
                button.triggerPress(Qt.RightButton); button.triggerPress(Qt.MiddleButton)
                toggleLog.reload()
                check(toggleLog.text().trim()==="","other buttons do not toggle")
                button.triggerPress(Qt.LeftButton); next()
            } else if (stage===22) {
                toggleLog.reload()
                if (!ready(toggleLog.text().trim()!=="")) return
                check(toggleLog.text().trim()==="shell toggle olafkfreund.github-actions {}","one left click toggles once")
                console.log("WIDGET_CHECKS_PASSED"); Qt.quit()
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
    pane = lay.get('pane')
    if pane and not (pane['h'] > 0 and lay['listHeight'] <= pane['y'] + 0.5 and pane['y'] + pane['h'] <= lay['footerY'] + 0.5):
        return f"layout: list, pane and footer overlap: list height {lay['listHeight']}, pane {pane}, footer y {lay['footerY']}"
    ordered = sorted(lay['rows'], key=lambda row: row['i'])
    for a, b in zip(ordered, ordered[1:]):
        if a['y'] + a['h'] > b['y'] + 0.5:
            return f'layout: rows overlap: {a} {b}'
    return None


def check_layout(state, fail):
    error = layout_error(state)
    if error:
        fail(error)


def read_log(path):
    """The fake's request log; a last line still being written is skipped."""
    lines = path.read_text().splitlines() if path.exists() else []
    entries = []
    for i, line in enumerate(lines):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
    return entries


WALK_ROWS = 27  # one/repo, its 25 runs, two/repo
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
        widget_available = (source / 'bar-widget').is_dir()
        if widget_available:
            widget_dir = root / 'bar-widget'
            widget_dir.mkdir()
            for name in ('BarWidget.qml', 'BarModel.js'):
                (widget_dir / name).symlink_to(source / 'bar-widget' / name)
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
        (bin_dir / 'omarchy-shell').write_text(
            '#!/usr/bin/env python3\nimport os,sys\n'
            'open(os.environ["TOGGLE_LOG"],"a").write(" ".join(sys.argv[1:])+"\\n")\n')
        (bin_dir / 'omarchy-shell').chmod(0o755)
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
        sway_lines = []
        try:
            directory, session, sway_lines, ipc, base_env = start_session(home, os.environ['PATH'], deadline)
            menu_path_env = {'MENU_SCENARIO': scenario}

            # --- Run 1: programmatic feature checks ---
            (root / 'shell.qml').write_text(FEATURES_QML)
            env = {**base_env, **menu_path_env, 'EXPECTED_BACKGROUND': STUB_BACKGROUND, 'FAKE_LOG': str(root / 'fake.log'),
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

            if widget_available:
                (root / 'shell.qml').write_text(WIDGET_QML)
                widget_env = {**env, 'WIDGET_STATUS_PATH': str(root / 'widget-status.json'),
                              'TOGGLE_LOG': str(root / 'omarchy-shell.log')}
                try:
                    widget_result = subprocess.run([QUICKSHELL, '-p', str(root), '--no-color'],
                                                   capture_output=True, text=True, timeout=30, env=widget_env)
                except subprocess.TimeoutExpired as hung:
                    print(*(part.decode() if isinstance(part, bytes) else part or '' for part in (hung.stdout, hung.stderr)))
                    raise SystemExit(f'{scenario}: QML widget checks timed out')
                widget_output = widget_result.stdout + widget_result.stderr
                if widget_result.returncode or 'WIDGET_CHECKS_PASSED' not in widget_output or any(
                        term in widget_output for term in ('ERROR:', 'ReferenceError', 'TypeError',
                                                          'CHECK FAILED', 'binding loop')):
                    print(widget_output)
                    raise SystemExit(f'{scenario}: QML widget checks failed')
                print(f'{scenario}: widget checks passed')
            else:
                print(f'{scenario}: widget stage skipped (no bar-widget directory)')

            # --- Run 2 (and failure runs): real key presses ---
            (root / 'shell.qml').write_text(KEYS_QML)

            def run_keys(label, extra_env, body):
                TIMELINE.clear()
                shell_lines = []
                states = queue.Queue()
                last = [None]
                env = {**base_env, **menu_path_env, 'PATH': str(bin_dir) + os.pathsep + base_env['PATH'], **extra_env}
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
                    ('p to pull requests', K('p'), lambda p, s: s['view'] == 'prs' and s['prs'] >= 0 and s['title'].startswith('Pull requests') and 'GraphQL points' in s['quota'], 2200),
                    ('v in pull requests', K('v'), lambda p, s: s['notice'] == 'Not available on pull requests', 300),
                    ('p back to repositories', K('p'), lambda p, s: s['view'] == 'repos' and s['selected'] == one, 400),
                    ('readiness: probe j', K('j'), lambda p, s: s['cursor'] == 1 and s['selected'] == two, 500),
                    ('readiness: probe k', K('k'), lambda p, s: s['cursor'] == 0 and s['selected'] == one, 2000),
                    # r and R change no state line by themselves; the request log checks them after the run.
                    ('r', K('r'), None, 1500),
                    ('R', ['-M', 'shift', '-k', 'r', '-m', 'shift'], None, 1500),
                    ('Down', K('Down'), sel(two), 400),
                    ('Up', K('Up'), sel(one), 400),
                    ('End', K('End'), sel(two), 400),
                    ('Home', K('Home'), sel(one), 400),
                    ('Right', K('Right'), lambda p, s: s['rows'] > 2 and s['selected'] == one, 500),
                    ('Left', K('Left'), lambda p, s: s['rows'] == 2 and s['selected'] == one, 500),
                    ('Return', K('Return'), lambda p, s: s['rows'] > 2 and s['selected'] == one, 500),
                    ('Left again', K('Left'), lambda p, s: s['rows'] == 2, 500),
                    ('/', K('slash'), lambda p, s: s['editing'], 400),
                    ('p in search', K('p'), lambda p, s: s['editing'] and s['filter'] == 'p' and s['view'] == 'repos', 300),
                    ('clear search p', K('BackSpace'), lambda p, s: s['editing'] and s['filter'] == '', 300),
                    ('type one', K('o', 'n', 'e'), lambda p, s: s['filter'] == 'one' and s['editing'], 400),
                    ('Escape in search', K('Escape'), lambda p, s: s['filter'] == '' and not s['editing'] and s['opened'], 400),
                    ('/ one Return', K('slash', 'o', 'n', 'e', 'Return'),
                     lambda p, s: s['filter'] == 'one' and not s['editing'] and s['rows'] > 1, 500),
                    ('i', K('i'), lambda p, s: s['layout']['pane'] is not None and s['filter'] == 'one', 500),
                    ('p closes details', K('p'), lambda p, s: s['view'] == 'prs' and s['layout']['pane'] is None, 500),
                    ('p restores filtered repositories', K('p'), lambda p, s: s['view'] == 'repos' and s['filter'] == 'one', 500),
                    ('i again', K('i'), lambda p, s: s['layout']['pane'] is not None, 500),
                    ('Escape closes the pane first', K('Escape'),
                     lambda p, s: s['layout']['pane'] is None and s['filter'] == 'one' and s['opened'], 500),
                    ('Escape with filter', K('Escape'), lambda p, s: s['filter'] == '' and s['opened'] and s['rows'] > 2, 500),
                    # Search-field Esc with the pane open closes only the pane: the text and the search stay.
                    ('i before search', K('i'), lambda p, s: s['layout']['pane'] is not None and not s['editing'], 500),
                    ('/ x', K('slash', 'x'), lambda p, s: s['editing'] and s['filter'] == 'x' and s['layout']['pane'] is not None, 500),
                    ('Escape in search closes the pane', K('Escape'),
                     lambda p, s: s['layout']['pane'] is None and s['filter'] == 'x' and s['editing'] and s['opened'], 500),
                    ('Escape leaves search', K('Escape'), lambda p, s: s['filter'] == '' and not s['editing'] and s['opened'], 500),
                    ('Ctrl+=', CTRL('equal'), lambda p, s: s['textStep'] == 1, 500),
                    ('Ctrl+0', CTRL('0'), lambda p, s: s['textStep'] == 0, 500),
                    ('End before g', K('End'), lambda p, s: s['cursor'] == s['rows'] - 1 and s['rows'] > 2, 300),
                    ('g', K('g'), lambda p, s: s['cursor'] == 0, 300),
                    ('walk j', [], None, 150),
                    ('Home after walk', K('Home'), lambda p, s: s['cursor'] == 0, 400),
                    ('End after walk', K('End'), lambda p, s: s['cursor'] == s['rows'] - 1
                     and s['layout']['contentHeight'] > s['layout']['listHeight'] and s['scrollY'] > 0, 400),
                    # The pane shrinks the list; the selected last row must stay inside it (layout check).
                    ('i at the last row', K('i'), lambda p, s: s['layout']['pane'] is not None and s['cursor'] == s['rows'] - 1, 500),
                    ('Escape closes the pane at the last row', K('Escape'),
                     lambda p, s: s['layout']['pane'] is None and s['opened'] and s['cursor'] == s['rows'] - 1, 500),
                    ('Home before G', K('Home'), lambda p, s: s['cursor'] == 0, 400),
                    # wtype's -k G types "g" (case-insensitive name, one-level keymap); text mode types "G".
                    # Keep it the only text argument: wtype prefixes later text arguments with a space.
                    ('G', ['G'], lambda p, s: s['cursor'] == s['rows'] - 1, 400),
                    ('j to run', K('g', 'j'), lambda p, s: s['cursor'] == 1 and s['selected'].startswith('one/repo:'), 400),
                    # p changes no state during a confirmation, so it rides with c; n then proves the view stayed.
                    ('c then p', K('c', 'p'), lambda p, s: s['confirm'] is not None and s['view'] == 'repos', 300),
                    ('n dismisses confirmation', K('n'), lambda p, s: s['confirm'] is None and s['view'] == 'repos', 300),
                    ('Return on run', K('Return'), lambda p, s: s['rows'] > p['rows'] and s['selected'] == p['selected'], 4500),
                    ('Escape closes', K('Escape'), lambda p, s: not s['opened'], 2000),
                ]
                # Plan step 4: r must not land inside the opening summary chain (its pages run 1 s apart),
                # so start typing once that chain has finished and the request log is quiet.
                log_path = root / 'fake.log'
                end = time.monotonic() + 30
                while True:
                    entries = read_log(log_path)
                    done = any(e['kind'] == 'summary' and e['status'] == 'requested' for e in entries)
                    if done and time.time() - entries[-1]['t'] >= 1.5:
                        break
                    if time.monotonic() > end:
                        fail('opening summary chain did not finish')
                    time.sleep(0.2)
                while True:
                    try:
                        last[0] = states.get_nowait()
                    except queue.Empty:
                        break
                steady = last[0]
                if steady['inFlight'] or steady['selected'] != 'repo:one/repo' or steady['rows'] != 2:
                    steady = wait_state('steady after opening chain', lambda s: not s['inFlight'] and s['rows'] == 2
                                        and s['selected'] == 'repo:one/repo', steady['seq'] - 1, timeout=5)
                assert len({step[0] for step in steps}) == len(steps), 'stage labels must be unique'
                # One wtype for the whole run: one virtual keyboard and one keymap (plan: option B).
                # The walk sends exactly one j per move from the top to the last of the 27 rows,
                # so a lost key leaves the cursor short of the last row.
                argv = ['wtype', '-s', '300']
                times, offset = {}, 0.3
                for label, keys, pred, pause in steps:
                    times[label] = offset
                    if label == 'walk j':
                        for _ in range(WALK_ROWS - 1):
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
                            if cur['rows'] != WALK_ROWS or cur['cursor'] != WALK_ROWS - 1:
                                fail(f"walk: ended on row {cur['cursor']} of {cur['rows']}; expected the last of {WALK_ROWS} "
                                     "(two repositories and the expanded repository's 25 runs)")
                            prev = cur
                            print(f'{scenario}: key walk j: {cur["rows"]} rows, layout checked on each')
                            continue
                        if pred is None:
                            TIMELINE.append(f'{label}: sent ~{times[label]:.1f}s, checked in the request log')
                            print(f'{scenario}: key {label} sent')
                            continue
                        prev = wait_state(f'key {label}', lambda s, p=prev, f=pred: f(p, s), prev['seq'],
                                          timeout=max(times[label] - (time.time() - start) + 6, 2))
                        if (label.startswith('Ctrl+') or label.startswith('i ') or label == 'i') and layout_error(prev):
                            # A size change (text size, pane) relayouts on the next frame (Qt.callLater); judge the settled state.
                            first, matched = layout_error(prev), prev
                            try:
                                prev = wait_state(f'key {label}: settled layout', lambda s, p=prev, f=pred, m=matched: f(p, s)
                                                  and s['textStep'] == m['textStep'] and not layout_error(s), prev['seq'], timeout=2)
                            except AssertionError:
                                fail(first)
                        check_layout(prev, fail)
                        # Open loop: a dead key shows up as a later stage failing; the timeline says which key it was.
                        TIMELINE.append(f"{label}: sent ~{times[label]:.1f}s, matched {prev['t'] - start:.1f}s")
                        print(f'{scenario}: key {label}')
                        if label == 'Return on run':
                            run_key, opened = prev['selected'], prev
                            # Jobs arrived: the job row replaced "Loading jobs…" (the Return state may already show it).
                            arrived = lambda s: s['error'] == '' and any(r['key'] == run_key + ':8' for r in s['layout']['rows']) \
                                and not any(r['key'] == run_key + ':message' for r in s['layout']['rows'])
                            if not arrived(opened):
                                opened = wait_state('jobs arrive under the run', arrived, opened['seq'], timeout=5)
                            check_layout(opened, fail)
                            # Duration tick: the selected run's info changes while selection and scroll stay.
                            ticked = wait_state('running duration ticks', lambda s: s['selected'] == run_key
                                                and s['scrollY'] == opened['scrollY'] and s['info'] != opened['info']
                                                and s['t'] - opened['t'] >= 1, opened['seq'], timeout=5)
                            prev = ticked
                    closed = prev
                    time.sleep(6)  # longer than the 5 s jobs interval, the shortest polling interval
                    while True:
                        try:
                            last[0] = states.get_nowait()
                        except queue.Empty:
                            break
                except AssertionError as error:
                    stop(typist)
                    raise AssertionError(f'{error}\nwtype exit={typist.returncode} output:\n{typist.stdout.read()}') from None
                finally:
                    stop(typist)
                if typist.returncode != 0:
                    fail(f'wtype exit {typist.returncode}: {typist.stdout.read()}')
                log = read_log(root / 'fake.log')
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

                def read_pid():
                    try:
                        return int(pid_file.read_text())
                    except (FileNotFoundError, ValueError):
                        return None  # not written yet, or half written

                def blocked(env, wait_state, fail, last, states):
                    busy = wait_state('request in flight', lambda s: s['opened'] and s['inFlight'] and read_pid() is not None, timeout=15)
                    pid = read_pid()
                    typed = subprocess.run(['wtype', '-s', '300', '-k', 'Escape'], env=env, timeout=10,
                                           capture_output=True, text=True)
                    if typed.returncode:
                        fail(f'wtype exit {typed.returncode}: {typed.stdout}{typed.stderr}')
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
                    if settle(states, last, 6)['requests'] != shut['requests']:
                        fail('closed panel started requests')
                    print('fresh: failure: close while a request runs')
                try:
                    run_keys('close during request', {'FAKE_MODE': 'block', 'FAKE_PID': str(pid_file),
                                                      'FAKE_LOG': str(root / 'block.log')}, blocked)
                finally:
                    # The file is unlinked once the helper is seen dead; a live blocked helper is always killed.
                    end = time.monotonic() + 1
                    while pid_file.exists() and read_pid() is None and time.monotonic() < end:
                        time.sleep(0.05)
                    if read_pid() is not None:
                        try:
                            os.kill(read_pid(), 9)
                        except ProcessLookupError:
                            pass
            print('QML_CHECKS_PASSED')
        finally:
            stop(session)
            if session is not None:
                shutil.rmtree(directory)
