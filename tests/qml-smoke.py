"""Exercise the real QML worker with a temporary fake API; no live GitHub requests."""
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


for scenario in ('fresh', 'managed'):
    deadline = time.monotonic() + 25
    with tempfile.TemporaryDirectory(prefix='actions-qml-') as temporary:
        root = Path(temporary)
        stubs = Path(__file__).resolve().parent / 'stubs'
        for name in ('Commons', 'Ui'):
            (root / name).symlink_to(stubs / name)
        for name in ('ActionsPanel.qml', 'ActionsModel.js', 'Polling.js', 'menu.py', 'menu.example.json'):
            (root / name).symlink_to(source / name)
        # A reply larger than the pipe buffer must be read whole even as the helper exits (#36).
        (root / 'actions.py').write_text('''import json, os, signal, sys, time
request=json.loads(sys.argv[2]); kind=request['kind']
with open(os.environ['FAKE_LOG'],'a') as log: log.write(f"{kind} {request['requestId']} {request['repo']}\\n")
if os.environ.get('FAKE_MODE')=='block':
    with open(os.environ['FAKE_PID'],'w') as pid: pid.write(str(os.getpid()))
    signal.pause()
time.sleep(0.1)
runs=[{'id':i,'name':'CI','status':'in_progress','run_attempt':1,'head_branch':'main','run_number':i,
       'run_started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()-5))} for i in range(7,32)]
if kind=='catalogue': data=[{'repo':'one/repo'},{'repo':'two/repo'}]
elif kind=='jobs': data=[{'id':8,'name':'build','status':'in_progress','steps':[{'number':1,'name':'Checkout','status':'completed','conclusion':'success'}]}]
elif kind=='run': data=runs[0]
elif kind=='account': data={'login':'tester'}
else: data=runs if request['repo']=='one/repo' and request.get('status','in_progress') in ('recent','in_progress') else []
reply=json.dumps({'requestId':request['requestId'],'data':data,'nextPage':0,'error':'','errorType':'','remaining':4000,'padding':'x'*200000}).encode()+b'\\n'
for i in range(0,len(reply),4096): os.write(1,reply[i:i+4096])
os._exit(0)
''')
        home = root / 'home'
        home.mkdir()
        menu_path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
        if scenario == 'managed':
            menu_path.parent.mkdir(parents=True)
            (home / 'managed-menu').write_text('{}\n')
            menu_path.symlink_to(home / 'managed-menu')
        (root / 'shell.qml').write_text('''
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
                console.log("STATE " + JSON.stringify(state))
            }
        }
    }
}
''')
        session = None
        quickshell = None
        sway_lines = []
        shell_lines = []
        states = queue.Queue()
        last = [None]
        try:
            directory, session, sway_lines, ipc, env = start_session(home, os.environ['PATH'], deadline)
            env.update({'MENU_SCENARIO': scenario, 'FAKE_LOG': str(root / 'fake.log')})
            quickshell = subprocess.Popen(['quickshell', '-p', str(root), '--no-color'], env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            collect(quickshell, shell_lines, states)

            def failure(label):
                raise AssertionError(f'{scenario}: {label}; last state={last[0]!r}\n'
                                     f'sway output:\n{chr(10).join(sway_lines[-30:])}\n'
                                     f'quickshell output:\n{chr(10).join(shell_lines[-30:])}')

            def wait_state(label, pred, after_seq=0, timeout=18):
                end = min(deadline, time.monotonic() + timeout)
                while time.monotonic() < end:
                    try:
                        state = states.get(timeout=min(0.1, max(0.01, end - time.monotonic())))
                    except queue.Empty:
                        if quickshell.poll() is not None:
                            failure(label + ': quickshell exited')
                        continue
                    last[0] = state
                    if state['seq'] > after_seq and pred(state):
                        return state
                failure(label + ': timeout')

            def key(label, args):
                while True:
                    try:
                        last[0] = states.get_nowait()
                    except queue.Empty:
                        break
                before = last[0]
                if before is None:
                    failure(label + ': no state before key')
                result = subprocess.run(['wtype', *args], env=env, capture_output=True, text=True,
                                        timeout=max(0.1, deadline - time.monotonic()))
                if result.returncode:
                    failure(label + ': wtype failed: ' + result.stderr)
                return before

            wait_state('stubs load', lambda s: s['stubBackground'] == '#101315' and s['opened'] and
                       s['rows'] >= 2 and s['layout']['listWidth'] > 0 and s['layout']['listHeight'] > 0)
            print(f'{scenario}: stubs load')
            # get_tree may omit layer-shell surfaces; the key transition is the focus check.
            subprocess.run(['swaymsg', '-s', str(ipc), '-t', 'get_tree'], env=env,
                           capture_output=True, text=True, timeout=3)
            before = key('readiness: probe', ['-s', '300', '-k', 'j', '-s', '300', '-k', 'k'])
            moved = wait_state('readiness: probe j',
                               lambda s: s['cursor'] == before['cursor'] + 1, before['seq'])
            wait_state('readiness: probe key not delivered',
                       lambda s: s['cursor'] == before['cursor'], moved['seq'])
            print(f'{scenario}: readiness: probe key delivered')
            if scenario == 'managed':
                assert any('GitHub Actions menu registration failed:' in line and 'Menu is managed:' in line
                           for line in shell_lines)
                assert menu_path.is_symlink() and menu_path.read_text() == '{}\n'
            else:
                assert not any('menu registration failed' in line for line in shell_lines)
                assert '"apps.github-actions"' in menu_path.read_text()
            print('QML_CHECKS_PASSED')
        finally:
            stop(quickshell)
            stop(session)
            if session is not None:
                shutil.rmtree(directory)
