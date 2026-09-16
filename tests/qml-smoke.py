"""Exercise the real QML worker with a temporary fake API; no live GitHub requests."""
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
shell = Path(os.environ['OMARCHY_PATH']) / 'shell'
with tempfile.TemporaryDirectory(prefix='actions-qml-') as directory:
    root = Path(directory)
    for name in ('Commons', 'Ui'):
        (root / name).symlink_to(shell / name)
    for name in ('ActionsPanel.qml', 'ActionsModel.js', 'Polling.js'):
        (root / name).symlink_to(source / name)
    (root / 'actions.py').write_text('''import json, sys, time
request=json.loads(sys.argv[2]); kind=request['kind']
time.sleep(0.1)
run={'id':7,'name':'CI','status':'in_progress','run_attempt':1,'head_branch':'main','run_number':1}
if kind=='catalogue': data=[{'repo':'one/repo'},{'repo':'two/repo'}]
elif kind=='jobs': data=[{'id':8,'name':'build','status':'in_progress','steps':[{'number':1,'name':'Checkout','status':'completed','conclusion':'success'}]}]
elif kind=='run': data=run
else: data=[run] if request['repo']=='one/repo' and request.get('status','in_progress') in ('recent','in_progress') else []
print(json.dumps({'requestId':request['requestId'],'data':data,'nextPage':0,'error':'','errorType':'','remaining':4000}))
''')
    (root / 'shell.qml').write_text('''
import QtQuick
import Quickshell
import "Polling.js" as Polling
ShellRoot {
    ActionsPanel { id: panel }
    property int stage: 0
    property string selected: ""
    property double closedAt: 0
    property int closedRequests: 0
    function check(value, label) { if (!value) throw new Error("CHECK FAILED: " + label) }
    Timer {
        interval: 1000; running: true
        onTriggered: {
            panel.polling=Polling.create()
            panel.configure('{"plugins":[{"id":"olafkfreund.github-actions","repositories":["one/repo","two/repo"]}]}')
            check(panel.entries.length===2,"configured repositories")
            panel.polling.repos[0].runs=[{id:7,name:"CI",status:"in_progress",run_attempt:1}]
            panel.expanded={"repo:one/repo":true}
            panel.adopt()
            panel.move(1)
            check(panel.current.kind==="run","keyboard selection")
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
            panel.open("{}")
            stage=1
        }
    }
    Timer {
        interval: 250; running: true; repeat: true
        onTriggered: {
            if(stage===1 && panel.polling.requests>=6 && panel.details["one/repo:7"] && panel.polling.catalogueComplete) {
                check(panel.error==="","async API has no error")
                check(panel.current.key===selected && panel.filterText==="repo","poll preserves searched selection")
                check(panel.details["one/repo:7"].jobs[0].steps.length===1,"jobs and steps arrive")
                check(panel.polling.catalogueComplete,"catalogue completed")
                panel.close()
                closedRequests=panel.polling.requests
                closedAt=Date.now()
                stage=2
            } else if(stage===2 && Date.now()-closedAt>1200) {
                check(!panel.loading && !panel.polling.flight,"close settles worker")
                check(panel.polling.requests===closedRequests,"closed panel starts no requests")
                var history=panel.polling.starts.length
                panel.open("{}")
                check(panel.polling.starts.length>=history,"reopen preserves budget")
                panel.close()
                stage=3
            } else if(stage===3 && !panel.loading) {
                console.log("QML_CHECKS_PASSED")
                Qt.quit()
            }
        }
    }
}
''')
    result=subprocess.run(['quickshell','-p',str(root),'--no-color'],capture_output=True,text=True,timeout=25)
    output=result.stdout+result.stderr
    print(output)
    if result.returncode or 'QML_CHECKS_PASSED' not in output or any(term in output for term in ('ERROR:', 'ReferenceError','TypeError','CHECK FAILED')):
        raise SystemExit('QML smoke check failed')
