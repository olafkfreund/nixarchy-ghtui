"""Exercise the real QML worker with a temporary fake API; no live GitHub requests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('plugin_dir', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
source = parser.parse_args().plugin_dir.resolve()
required = ('manifest.json', 'ActionsPanel.qml', 'ActionsModel.js', 'Polling.js',
            'actions.py', 'menu.py', 'menu.example.json', 'keybindings.sh')
if not source.is_dir() or any(not (source / name).is_file() for name in required):
    parser.error('plugin_dir must contain the complete GitHub Actions plugin')
shell = Path(os.environ['OMARCHY_PATH']) / 'shell'
colors = tomllib.loads((Path.home() / '.local/state/omarchy/current/theme/colors.toml').read_text())
for scenario in ('fresh', 'managed'):
    with tempfile.TemporaryDirectory(prefix='actions-qml-') as directory:
        root = Path(directory)
        for name in ('Commons', 'Ui'):
            (root / name).symlink_to(shell / name)
        for name in ('ActionsPanel.qml', 'ActionsModel.js', 'Polling.js', 'menu.py', 'menu.example.json'):
            (root / name).symlink_to(source / name)
        # The fake replies with ~200 KiB (over the 64 KiB pipe buffer) in 4 KiB chunks and exits at once,
        # so every run checks that a reply written right before exit reaches the panel whole (#36).
        (root / 'actions.py').write_text('''import json, os, sys, time
request=json.loads(sys.argv[2])
if sys.argv[1]=='act':
    open(os.environ['HOME']+'/act.log','a').write(sys.argv[2]+'\\n')
    time.sleep(0.1)
    os.write(1,(json.dumps({'requestId':request['requestId'],'action':request['action'],'httpStatus':202,'ok':True,'error':'','errorType':'','retryAt':0,'remaining':4000})+'\\n').encode())
    os._exit(0)
kind=request['kind']
time.sleep(0.1)
run={'id':7,'name':'CI','status':'in_progress','run_attempt':1,'head_branch':'main','run_number':1}
if kind=='catalogue': data=[{'repo':'one/repo'},{'repo':'two/repo'}]
elif kind=='jobs': data=[{'id':8,'name':'build','status':'in_progress','steps':[{'number':1,'name':'Checkout','status':'completed','conclusion':'success'}]}]
elif kind=='run': data=run
elif kind=='account': data={'login':'tester'}
else: data=[run] if request['repo']=='one/repo' and request.get('status','in_progress') in ('recent','in_progress') else []
reply=json.dumps({'requestId':request['requestId'],'data':data,'nextPage':0,'error':'','errorType':'','remaining':4000,'padding':'x'*200000}).encode()+b'\\n'
for i in range(0,len(reply),4096): os.write(1,reply[i:i+4096])
os._exit(0)
''')
        home = root / 'home'
        home.mkdir()
        theme = home / '.local/state/omarchy/current/theme'
        theme.parent.mkdir(parents=True)
        theme.symlink_to(Path.home() / '.local/state/omarchy/current/theme')
        (home / '.config').mkdir()
        (home / '.config/fontconfig').symlink_to(Path.home() / '.config/fontconfig')
        (home / '.config/omarchy').mkdir()
        (home / '.config/omarchy/shell.toml').symlink_to(Path.home() / '.config/omarchy/shell.toml')
        menu_path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        if scenario == 'managed':
            menu_path.parent.mkdir(parents=True)
            (home / 'managed-menu').write_text('{}\n')
            menu_path.symlink_to(home / 'managed-menu')
        (root / 'shell.qml').write_text('''
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
        interval: 18000; running: true
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
    function ensureRun9() {
        var runs = panel.polling.repos[0].runs
        if (!runs.some(function(run) { return run.id === 9 }))
            runs.push({id:9,name:"Lint",status:"completed",conclusion:"failure",run_number:2,head_branch:"main"})
        panel.adopt()
    }
    function check(value, label) { if (!value) throw new Error("CHECK FAILED: " + label) }
    Timer {
        interval: 1000; running: true
        onTriggered: {
            check(Commons.Color.background.toString()===Quickshell.env("EXPECTED_BACKGROUND"),"active Omarchy theme")
            check(panel.textScale===undefined,"no panel scale factor")
            menuFile.reload()
            check(!panel.opened && panel.polling.requests===0,"registration does not open or poll")
            if (Quickshell.env("MENU_SCENARIO") === "fresh")
                check(menuFile.text().indexOf('"apps.github-actions"') >= 0,"registered while closed")
            panel.polling=Polling.create()
            panel.polling.repos=[{repo:"one/repo"},{repo:"two/repo"}]; panel.adopt()
            check(panel.entries.length===2,"seeded repositories")
            panel.polling.repos[0].runs=[{id:7,name:"CI",status:"in_progress",run_attempt:1}]
            panel.polling.expanded={"repo:one/repo":true}
            panel.adopt()
            panel.move(1)
            check(panel.current.kind==="run","keyboard selection")
            panel.polling.repos[0].runs[0].run_started_at=new Date(panel.now-5000).toISOString()
            panel.adopt()
            var tickKey=panel.current.key, tickCursor=panel.cursor, tickScroll=JSON.parse(panel.status()).scrollY
            panel.now=panel.now+3000
            check(panel.current.info==="8s","running duration ticks with now")
            check(panel.current.key===tickKey && panel.cursor===tickCursor,"tick keeps selection")
            check(JSON.parse(panel.status()).scrollY===tickScroll,"tick keeps scroll")
            var savedRuns=panel.polling.repos[0].runs
            panel.polling.repos[0].runs=[]
            panel.adopt()
            var poll=JSON.parse(panel.status())
            check(poll.pollSelected===panel.current.repo && poll.pollInspected===(panel.current.run||""),"polling follows the highlight")
            check("remaining" in poll && "resetAt" in poll,"status has quota fields")
            panel.polling.repos[0].runs=savedRuns
            panel.adopt()
            panel.move(-1)
            check(panel.current.kind==="run","cursor back on the run")
            panel.expand(false)
            check(panel.entries[2].title==="Loading jobs…","expand run")
            panel.expand(true)
            check(panel.entries.length===3,"collapse run retains other repository")
            panel.filterText="no-match"
            check(panel.entries.length===0,"filter")
            panel.filterText="repo"
            check(panel.cursor===0 && panel.entries.length===2,"search resets collapsed results")
            panel.expand(false)
            panel.move(1)
            panel.expand(false)
            selected=panel.current.key
            panel.open()
            stage=1
        }
    }
    Timer {
        interval: 250; running: true; repeat: true
        onTriggered: {
            if(stopped()) return
            if(stage===1 && panel.polling.requests>=6 && panel.details["one/repo:7"] && panel.polling.catalogueComplete) {
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
                panel.close()
                stage=3
            } else if(stage===3 && !panel.workerBusy) {
                console.log("QML_CHECKS_PASSED")
                Qt.quit()
            }
        }
    }
}
''')
        try:
            result=subprocess.run(['quickshell','-p',str(root),'--no-color'],capture_output=True,text=True,timeout=25,
                                  env={**os.environ, 'HOME':str(home), 'MENU_SCENARIO':scenario, 'EXPECTED_BACKGROUND':colors['background'].lower()})
        except subprocess.TimeoutExpired as error:
            print(error.stdout, error.stderr)
            raise
        output=result.stdout+result.stderr
        print(output)
        if result.returncode or 'QML_CHECKS_PASSED' not in output or any(term in output for term in ('ERROR:', 'ReferenceError','TypeError','CHECK FAILED')):
            raise SystemExit('QML smoke check failed')
        sent = [json.loads(line) for line in (home / 'act.log').read_text().splitlines()]
        assert [(task['action'], task['repo'], task['run']) for task in sent] == [('cancel', 'one/repo', '7'), ('rerun', 'one/repo', '9')], sent
        if scenario == 'managed':
            assert 'GitHub Actions menu registration failed:' in output and 'Menu is managed:' in output
            assert menu_path.is_symlink() and menu_path.read_text() == '{}\n'
        else:
            assert 'menu registration failed' not in output
            assert '"apps.github-actions"' in menu_path.read_text()
