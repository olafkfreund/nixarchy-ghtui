const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = {};
vm.createContext(model);
vm.runInContext(fs.readFileSync('ActionsModel.js', 'utf8'), model);
{
  const now=Date.now(), last=conclusion => ({conclusion,confirmedAt:now,at:new Date(now).toISOString()});
  const repos=[{active:2,last:last('failure'),checked:'x'}, {runs:[{status:'in_progress'}],last:last('timed_out'),checked:'x'},
    {active:3,last:last('startup_failure'),checked:'x'}, {active:1,last:last('success'),checked:'x'},
    ...['archived','disabled','blocked','error'].map(flag => ({[flag]:true,active:10,last:last('failure'),checked:'x'}))];
  assert.deepEqual({...model.barCounts(repos,now)},{running:7,failed:3});
  const base={repos,account:'tester',accountVerified:true,cooldown:0,countsAt:0,error:'transient'};
  const status=(changes={},previous) => ({...model.barStatus({...base,...changes},'instance',now,previous)});
  const keys=['version','instance','account','state','running','failed','countsAt','cooldownUntil','reason','writtenAt'];
  const ok=status();
  assert.deepEqual(Object.keys(ok),keys);
  assert.deepEqual(ok,{version:1,instance:'instance',account:'tester',state:'ok',running:7,failed:3,
    countsAt:0,cooldownUntil:0,reason:'',writtenAt:now});
  assert.deepEqual(status({countsAt:undefined,accountVerified:false}),{...ok,account:'',state:'none',countsAt:0});
  assert.deepEqual(status({auth:true,error:'login',catalogueBlocked:'catalogue',cooldown:now+1}),
    {...ok,state:'stopped',reason:'login'});
  assert.deepEqual(status({catalogueBlocked:'catalogue',cooldown:now+1}),
    {...ok,state:'stopped',reason:'catalogue'});
  assert.deepEqual(status({cooldown:now+1}),{...ok,state:'rate',cooldownUntil:now+1});
  assert.deepEqual(status({cooldown:now+1,countsAt:undefined}),
    {...ok,state:'rate',countsAt:0,cooldownUntil:now+1});
  assert.deepEqual(status({cooldown:now+1,repos:[{error:'rate',active:9}]},{account:'tester',running:7,failed:3,countsAt:42}),
    {...ok,state:'rate',countsAt:42,cooldownUntil:now+1});
  // A previous payload from another account is never reused (a failed reset write).
  assert.deepEqual(status({cooldown:now+1,repos:[]},{account:'other',running:7,failed:3,countsAt:42}),
    {...ok,state:'rate',running:0,failed:0,cooldownUntil:now+1});
  assert.deepEqual(status({cooldown:now+1,repos:[],countsAt:undefined,account:'new'},
    {running:7,failed:3,countsAt:42}),
    {...ok,account:'new',state:'rate',running:0,failed:0,countsAt:0,cooldownUntil:now+1});
}
const repos = [{repo: 'owner/repo', runs: [{id: 7, status: 'in_progress', name: 'CI', head_branch: 'main', run_number: 3}]}];
const expanded = {'repo:owner/repo': true, 'owner/repo:7': true, 'owner/repo:7:8': true};
const details = {'owner/repo:7': {jobs: [{id: 8, name: 'build', status: 'in_progress', steps: [{number: 1, name: 'Checkout', status: 'completed', conclusion: 'success'}]}]}};
const rows = model.rows(repos, expanded, details, '', Date.now());
assert.equal(rows.length, 4);
assert.equal(rows[3].title, 'Checkout');
assert.equal(rows[3].status, 'success');
assert.equal(rows[2].info.startsWith('1/1 steps'), true);
assert.equal(model.selection(rows, 'owner/repo:7:8', 0), 2);
assert.equal(model.selection([], 'missing', 5), 0);
assert.equal(model.rows(repos, {}, details, '', Date.now()).length, 1);
assert.equal(model.rows(repos, {}, {}, 'main', Date.now()).length, 1);
assert.equal(model.rows(repos, expanded, details, 'missing', Date.now()).length, 0);
assert.equal(model.rows(repos, expanded, {}, '', Date.now())[2].title, 'Loading jobs…');
assert.equal(model.duration({started_at:'2026-01-01T00:00:00Z'}, Date.parse('2026-01-01T00:01:15Z')), '1m 15s');
const labels = {in_progress:'running', queued:'queued', requested:'queued', pending:'queued', waiting:'waiting',
  success:'passed', failure:'failed', timed_out:'timed out', startup_failure:'startup failed',
  cancelled:'cancelled', skipped:'skipped', neutral:'neutral', action_required:'needs action',
  'awaiting final status':'checking result', unavailable:'unavailable'};
for (const [status, expected] of Object.entries(labels)) assert.equal(model.label(status), expected, status);
for (const status of ['', undefined, 'error', 'constructor']) assert.equal(model.label(status), 'unknown');
const now = new Date(2026, 0, 2, 0, 0, 0).getTime();
for (const [seconds, expected] of [[0,'now'], [59,'now'], [60,'1m ago'], [59*60,'59m ago'],
  [60*60,'1h ago'], [23*3600,'23h ago'], [24*3600,'1d ago']])
  assert.equal(model.age({created_at:new Date(now-seconds*1000).toISOString()}, now), expected);
assert.equal(model.age({}, now), '');
assert.equal(model.age({created_at:new Date(now+60000).toISOString()}, now), 'now');
assert.equal(model.age({created_at:'invalid'}, now), '');
assert.equal(model.age({created_at:new Date(now-3600000).toISOString(), run_started_at:new Date(now-60000).toISOString()}, now), '1m ago');
assert.equal(model.cap('abc', 4), 'abc');
assert.equal(model.cap('abcd', 4), 'abcd');
assert.equal(model.cap('abcde', 4), 'abc…');
assert.equal(model.cap(null, 4), '');
const resetAt = new Date(2026, 0, 2, 3, 4, 5).getTime();
assert.equal(model.clock(resetAt), '03:04');
assert.equal(model.clock(resetAt, true), '03:04:05');
assert.equal(model.quotaText(499, resetAt, resetAt-1), '499 API requests left · resets 03:04');
assert.equal(model.quotaText(500, resetAt, resetAt-1), '500 API requests left');
assert.equal(model.quotaText(1234, resetAt, resetAt-1), '1,234 API requests left');
assert.equal(model.quotaText(null, resetAt, resetAt-1), '');
assert.equal(model.quotaText(499, resetAt, resetAt), '');
assert.equal(model.quotaText(499, undefined, resetAt-1), '');
const baseStatus = {notice:'n', noticeUntil:now+1, error:'global error', repos:[{repo:'o/r', error:'repo error'}],
  cooldown:now+60000, discoveryComplete:true, checkedCount:2, repoCount:3, remaining:499, resetAt};
const status = model.statusLine(baseStatus, now);
assert.equal(status.text, 'n · global error · GitHub paused until 00:01:00');
assert.equal(status.urgent, true);
assert.equal(status.quota, '499 API requests left · resets 03:04');
assert.equal(model.statusLine({...baseStatus, cooldown:0}, now).text, 'n · global error');
assert.equal(model.statusLine({...baseStatus, error:'', cooldown:0}, now).text, 'n · o/r: repo error');
assert.equal(model.statusLine({...baseStatus, noticeUntil:now, error:'', repos:[], cooldown:0}, now).text, 'Activity checked 2/3');
assert.equal(model.statusLine({...baseStatus, notice:'', error:'', repos:[], cooldown:now+60000}, now).text, 'GitHub paused until 00:01:00');
assert.equal(model.statusLine({...baseStatus, notice:'', error:'', repos:[], cooldown:0, discoveryComplete:false}, now).text,
  'Discovering repositories… 3 found');
assert.equal(model.statusLine({...baseStatus, notice:'', error:'', repos:[], cooldown:0, remaining:500, resetAt:now+1}, now).urgent, false);
assert.equal(model.emptyText({repoCount:0, error:'oops', discoveryComplete:false, filter:''}), 'oops');
assert.equal(model.emptyText({repoCount:0, error:'', discoveryComplete:false, filter:''}), 'Discovering repositories…');
assert.equal(model.emptyText({repoCount:0, error:'', discoveryComplete:true, filter:''}), 'No repositories found for this account');
assert.equal(model.emptyText({repoCount:2, error:'oops', discoveryComplete:true, filter:'ci'}), 'No match for "ci" · search covers loaded runs only');
assert.deepEqual(JSON.parse(JSON.stringify(model.coverage([{summaryAt:'now'}, {runs:[{}]}, {summaryAt:0}, {summaryAt:'later'}]))),
  {loaded:2, total:4});
assert.equal(model.accessibleName({kind:'repo', title:'o/r', statusText:'failed', info:'✕ 3h · 12 running · stale'}, false),
  'repository: o/r, failed, ✕ 3h · 12 running · stale, collapsed');
assert.equal(model.accessibleName({kind:'run', title:'CI', statusText:'running'}, true), 'run: CI, running, expanded');
assert.equal(model.accessibleName({kind:'run', title:'CI', statusText:'running', info:'1m 0s · watching'}, true), 'run: CI, running, watching, expanded');
assert.equal(model.accessibleName({kind:'step', title:'Checkout', statusText:'passed'}, false), 'step: Checkout, passed');
assert.equal(model.accessibleName({kind:'message', title:'Loading jobs…', statusText:''}, false), 'message: Loading jobs…');
assert.equal(model.accessibleName({kind:'more', title:'More runs', statusText:''}, false), 'more: More runs');
assert.equal(model.icon('cancelled'), '⊘');
assert.equal(model.icon('failure'), '✕');
assert.equal(model.reply('{"repos":[]}', 0, 5), '{"repos":[]}');
assert.deepEqual(JSON.parse(model.reply('', 2, 5)), {requestId:5, errorType:'setup', error:'Workflow helper failed (exit 2); see the shell log'});
assert.equal(JSON.parse(model.reply('', 127, 5)).error, 'python3 not found');
// #45: run actions. Polling.js has its own `age`, so it gets its own context.
{
  const poll = {};
  vm.createContext(poll);
  vm.runInContext(fs.readFileSync('Polling.js', 'utf8'), poll);
  const s = poll.create();
  const mk = (id, status, conclusion) => ({id, status, conclusion, name: 'CI', head_branch: 'main', run_number: id});
  s.repos = [{repo: 'o/r', checked: 'now', active: 0, runs: [mk(1, 'completed', 'failure'), mk(2, 'completed', 'timed_out'),
    mk(3, 'completed', 'cancelled'), mk(4, 'completed', 'success'), mk(5, 'in_progress'), mk(6, 'queued')]}];
  const list = model.rows(s.repos, {'repo:o/r': true}, {}, '', Date.now());
  const rowFor = id => list.find(row => row.kind === 'run' && row.run === String(id));
  const offered = id => { const row = rowFor(id); return JSON.parse(JSON.stringify(model.actionsFor(poll.runFor(s, row.repo, row.run)))); };
  assert.deepEqual(offered(4), ['rerun']);
  for (const id of [1, 2, 3]) assert.deepEqual(offered(id), ['rerun', 'rerun-failed']);
  for (const id of [5, 6]) assert.deepEqual(offered(id), ['cancel']);
  assert.deepEqual(JSON.parse(JSON.stringify(model.actionsFor(poll.runFor(s, 'o/r', '99')))), []);
  assert.equal(rowFor(1).status, 'failure', 'the row status is mapped, not "completed"');
  const failed = poll.runFor(s, 'o/r', '1'), good = poll.runFor(s, 'o/r', '4'), live = poll.runFor(s, 'o/r', '5');
  assert.equal(model.unavailable('rerun', failed), '');
  assert.equal(model.unavailable('rerun-failed', failed), '');
  assert.equal(model.unavailable('cancel', live), '');
  assert.equal(model.unavailable('rerun', live), 'Only a finished run can be rerun');
  assert.equal(model.unavailable('rerun-failed', good), 'Rerun failed needs a failed run');
  assert.equal(model.unavailable('cancel', good), 'Only an unfinished run can be cancelled');
  for (const action of ['rerun', 'rerun-failed', 'cancel']) assert.equal(model.unavailable(action, null), 'Select a run to rerun or cancel');
  const long = {...failed, name: 'N'.repeat(200), head_branch: 'B'.repeat(200)};
  const questions = {rerun: 'Rerun all jobs?', 'rerun-failed': 'Rerun failed jobs?', cancel: 'Cancel run?'};
  const wording = {rerun: 'Rerun requested: ', 'rerun-failed': 'Rerun of failed jobs requested: ', cancel: 'Cancel requested: '};
  for (const action of Object.keys(questions)) {
    const d = model.describe(action, 'o/r', long);
    assert.ok(d.confirm.startsWith(questions[action]), d.confirm);
    assert.ok(d.confirm.indexOf('y yes · n no') < d.confirm.indexOf('o/r') && d.confirm.indexOf('o/r') < d.confirm.indexOf('NNN'), d.confirm);
    assert.equal(d.confirm.includes('cannot be undone'), action === 'cancel');
    assert.ok(d.done.startsWith(wording[action]) && d.done.includes('o/r #1 '), d.done);
    for (const text of [d.confirm, d.done]) {
      assert.ok(!/N{31}/.test(text) && !/B{31}/.test(text), 'name and branch are cut to 30 characters');
      assert.ok(/N{20}/.test(text) && /B{20}/.test(text));
    }
  }
  const dirty = model.describe('rerun', 'o/r', {...failed, name: 'a\x1bb\nc', head_branch: 'm\x07'});
  assert.ok(!/[\x00-\x1f\x7f-\x9f]/.test(dirty.confirm + dirty.done), 'control characters are removed');
  assert.ok(dirty.confirm.includes('a b c'));
  assert.equal(model.actionReply('{"ok":true}', 0, 3), '{"ok":true}');
  assert.deepEqual(JSON.parse(model.actionReply('', 127, 3)), {requestId: 3, ok: false, errorType: 'setup', error: 'python3 not found'});
  assert.deepEqual(JSON.parse(model.actionReply('', 1, 3)), {requestId: 3, ok: false, errorType: 'unknown', error: 'Outcome unknown; check GitHub before retrying'});
  // A SIGTERM'd helper exits 0 with no output: the write may have been sent.
  assert.deepEqual(JSON.parse(model.actionReply('', 0, 3)), {requestId: 3, ok: false, errorType: 'unknown', error: 'Outcome unknown; check GitHub before retrying'});
}
const ranked = model.rows([{repo:'z/idle', checked:'now', active:0}, {repo:'a/unchecked'}, {repo:'b/running', active:2, checked:'now'}], {}, {}, '', Date.now());
assert.equal(ranked[0].title, 'b/running');
assert.equal(ranked[0].info, 'no result · 2 running');
assert.equal(ranked[1].info, 'no result · 0 running');
assert.equal(ranked[2].info, 'not checked');
assert.equal(model.rows([{repo:'a/b', description:'find this project'}], {}, {}, 'find this', Date.now()).length, 1);
const backing = [];
let edits = 0;
const list = {
  get count() { return backing.length; },
  get(i) { return backing[i]; },
  insert(i, value) { backing.splice(i, 0, value); edits++; },
  move(from, to) { backing.splice(to, 0, ...backing.splice(from, 1)); edits++; },
  remove(i, count) { backing.splice(i, count); edits++; },
  setProperty(i, role, value) { backing[i][role] = value; edits++; }
};
const first = [{key:'a',title:'A',status:'queued'}, {key:'b',title:'B',status:'queued'}];
assert.equal(model.syncRows(list, first), true);
const originalA = backing[0];
edits = 0;
assert.equal(model.syncRows(list, first), false);
assert.equal(edits, 0, 'Identical polling result must not reset or update delegates');
assert.equal(model.syncRows(list, [{...first[0],status:'in_progress'}, first[1]]), false);
assert.equal(backing[0], originalA, 'Status update preserves existing row');
assert.equal(model.syncRows(list, [first[1], first[0]]), true);
assert.equal(backing[1], originalA, 'Reordering moves the row instead of recreating it');
model.syncRows(list, [first[0]]);
assert.equal(list.count, 1);
assert.equal(backing[0].rowKey, 'a');
console.log('Model: hierarchy, filtering, progress, selection and duration passed');

// #30: runs past the first page per status show as one "more" row.
const busy = {repo:'a/b', checked:'now', active:0, hidden:{queued:900, waiting:12, pending:0},
  runs:[{id:11, status:'queued', name:'CI', head_branch:'fork-x'}, {id:10, status:'queued', name:'CI'}, {id:1, status:'completed', conclusion:'success', name:'CI'}]};
const open = {'repo:a/b': true};
let shown = model.rows([busy], open, {}, '', Date.now());
assert.deepEqual(Array.from(shown, row => row.key), ['repo:a/b', 'a/b:11', 'a/b:10', 'repo:a/b:more', 'a/b:1']);
const more = shown[3];
assert.equal(more.title, '+900 more queued · +12 more waiting');
assert.deepEqual([more.kind, more.parent, more.depth, more.url, more.run, more.repo],
  ['more', 'repo:a/b', 1, 'https://github.com/a/b/actions', undefined, 'a/b']);
assert.equal(model.rows([{...busy, hidden:{queued:4000}}], open, {}, '', Date.now())[3].title, '+about 4000 more queued');
assert.equal(model.rows([{...busy, hidden:{queued:1000}}], open, {}, '', Date.now())[3].title, '+1000 more queued');
assert.equal(model.rows([{...busy, runs:[busy.runs[2]]}], open, {}, '', Date.now())[1].key, 'repo:a/b:more', 'before completed runs even with no unfinished run shown');
assert.equal(model.rows([busy], {}, {}, '', Date.now()).length, 1, 'collapsed repository has no more row');
assert.ok(!model.rows([{...busy, hidden:{queued:0}}], open, {}, '', Date.now()).some(row => row.kind === 'more'));
assert.ok(!model.rows([busy], open, {}, 'fork-x', Date.now()).some(row => row.kind === 'more'), 'search covers visible runs only');
assert.ok(model.rows([busy], open, {}, 'a/b', Date.now()).some(row => row.kind === 'more'));

function counted() {
  const store = [], stub = {ops: 0, store,
    get count() { return store.length; }, get(i) { return store[i]; },
    insert(i, v) { store.splice(i, 0, v); this.ops++; }, move(f, t) { store.splice(t, 0, ...store.splice(f, 1)); this.ops++; },
    remove(i, n) { store.splice(i, n); this.ops++; }, setProperty(i, k, v) { store[i][k] = v; this.ops++; }};
  return stub;
}
const many = {repo:'o/r', checked:'x', active:0, runs:Array.from({length:5000}, (_, i) => ({id:100000 + i, status:'queued', name:'CI', run_number:i}))
  .concat(Array.from({length:10}, (_, i) => ({id:i + 1, status:'completed', name:'CI'})))};
const big = model.rows([many, {repo:'o/other', checked:'x', active:0}], {'repo:o/r': true}, {}, '', 0);
assert.equal(big.length, 5012);
function opsFor(next) { const l = counted(); model.syncRows(l, big); l.ops = 0; model.syncRows(l, next); return l; }
assert.equal(opsFor(big.slice()).ops, 0);
const withoutOne = big.slice(); withoutOne.splice(2, 1);
assert.equal(opsFor(withoutOne).ops, 1, 'one removed row is one remove, not a cascade of moves');
const jumped = big.slice(); jumped.splice(1, 0, ...jumped.splice(big.length - 11, 1));
assert.equal(opsFor(jumped).ops, 1);
assert.equal(opsFor(big.map((row, i) => i === 5 ? {...row, info:'1m 0s'} : row)).ops, 1, 'a changed field updates the row');
assert.equal(opsFor(big.map((row, i) => i === 5 ? {...row, url:'https://github.com/x'} : row)).ops, 0, 'fields the delegate does not read are ignored');

let seed = 30;
function random(n) { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; }
const pool = Array.from({length:60}, (_, i) => 'k' + i), synced = counted();
for (let round = 0; round < 200; round++) {
  const next = pool.filter(() => random(3)).map(key => ({key, title:key, subtitle:'', status:['queued', 'in_progress'][random(2)], info:String(random(4))}));
  for (let i = next.length - 1; i > 0; i--) { if (random(4)) continue; const j = random(i + 1); [next[i], next[j]] = [next[j], next[i]]; }
  model.syncRows(synced, next);
  assert.deepEqual(synced.store.map(x => x.rowKey), next.map(row => row.key));
  assert.deepEqual(synced.store.map(x => [x.rowData.status, x.rowData.info]), next.map(row => [row.status, row.info]));
}
// #32: only a plain github.com URL reaches xdg-open.
assert.equal(model.browsable('https://github.com/o/r/actions/runs/1'), true);
for (const url of ['https://github.com.evil.example/', 'https://github.com@evil.example', 'https://github.com/',
                   'https://github.com/o/r x', 'https://github.com/o/r\n', 'https://github.com/o r',
                   'https://github.com/o\x85r', 'http://github.com/o', undefined, 5])
    assert.equal(model.browsable(url), false, JSON.stringify(url));
console.log('Model: more row, linear syncRows and random-order equivalence passed');

// #41: an expanded run that polling no longer refreshes says so and freezes its timers.
{
  const now = Date.parse('2026-01-01T01:00:00Z'), at = ms => new Date(now - ms).toISOString().replace('.000Z', 'Z');
  const job = {id: 8, name: 'build', status: 'in_progress', started_at: '2026-01-01T00:00:00Z', steps: []};
  const run = {id: 7, status: 'in_progress', name: 'CI', run_number: 3, run_attempt: 1};
  const view = (r, d, live, open = {'repo:o/r': true, 'o/r:7': true}, t = now) =>
    model.rows([{repo: 'o/r', runs: [r]}], open, d ? {'o/r:7': d} : {}, '', t, live);
  const stale = {jobs: [job], updated: at(4 * 60000)};
  assert.equal(view(run, stale, 'o/r:9')[1].subtitle, 'jobs 4m old, not refreshing');
  const frozen = view(run, stale, 'o/r:9')[2].info;
  assert.equal(view(run, stale, 'o/r:9', undefined, now + 600000)[2].info, frozen, 'timer stays at the last fetch');
  const fresh = view(run, stale, 'o/r:7');
  assert.ok(!fresh[1].subtitle.includes('jobs ') && !fresh[1].subtitle.includes('not refreshing'));
  assert.notEqual(view(run, stale, 'o/r:7', undefined, now + 600000)[2].info, fresh[2].info, 'live timer uses now');
  const done = {...run, status: 'completed', conclusion: 'success'};
  assert.ok(!view(done, {...stale, finalAttempt: 1}, '')[1].subtitle.includes('not refreshing'));
  assert.ok(view(done, {...stale, finalAttempt: 2}, '')[1].subtitle.includes('not refreshing'));
  assert.ok(view(run, {...stale, updated: at(75 * 60000)}, '')[1].subtitle.includes('jobs 1h 15m old'));
  const err = view(run, {...stale, error: 'rate limited'}, '');
  assert.deepEqual([err[2].kind, err[2].title, err[3].kind], ['message', 'rate limited', 'job']);
  assert.ok(!view(run, {error: 'rate limited'}, '')[1].subtitle.includes('jobs '), 'no stamp without updated');
  assert.ok(!view(run, stale, '', {'repo:o/r': true})[1].subtitle.includes('jobs '), 'collapsed run has no marker');
  assert.equal(view(run, stale)[1].subtitle.includes('not refreshing'), true, 'five arguments still work');
}
console.log('Model: not-refreshing marker passed');

// #42: run subtitle, statusText, message row and search by label.
{
  const t = Date.parse('2026-01-01T01:00:00Z');
  const run = {id: 7, status: 'completed', conclusion: 'failure', name: 'CI', head_branch: 'main', event: 'push', actor: 'bob',
    run_number: 3, run_started_at: '2026-01-01T00:55:00Z', display_title: 'Fix'};
  const view = (r, open = {}, filter = '', repo = {}) =>
    model.rows([{repo: 'o/r', ...repo, runs: [r]}], {'repo:o/r': true, ...open}, {}, filter, t);
  assert.equal(view(run)[1].subtitle, 'main · push · bob · 5m ago · Fix');
  const staleSubtitle = model.rows([{repo: 'o/r', runs: [run]}], {'repo:o/r': true, 'o/r:7': true},
    {'o/r:7': {jobs: [], updated: new Date(t - 4 * 60000).toISOString()}}, '', t, 'o/r:9')[1].subtitle;
  assert.equal(staleSubtitle, 'main · push · bob · 5m ago · jobs 4m old, not refreshing · Fix');
  assert.ok(!view(run)[1].subtitle.includes('#') && !view(run)[1].subtitle.includes('jobs fetched'));
  const long = {...run, head_branch: 'b'.repeat(40), actor: 'a'.repeat(30), event: 'e'.repeat(30)};
  assert.deepEqual(view(long)[1].subtitle.split(' · ').slice(0, 3), ['b'.repeat(27) + '…', 'e'.repeat(13) + '…', 'a'.repeat(15) + '…']);
  assert.equal(view({...run, event: '', actor: undefined})[1].subtitle, 'main · 5m ago · Fix', 'empty parts leave no separators');
  for (const q of ['failed', 'failure', 'a'.repeat(30), 'e'.repeat(30), 'b'.repeat(40)])
    assert.equal(view(long, {}, q).length, 2, q);
  assert.equal(view({...run, status: 'in_progress', conclusion: null}, {}, 'in_progress').length, 2);
  const job = {id: 8, name: 'build', status: 'completed', conclusion: 'success', html_url: 'https://github.com/o/r/job/8',
    steps: [{number: 4, name: 'Go', status: 'completed', conclusion: 'failure'}]};
  const full = model.rows([{repo: 'o/r', runs: [run]}], {'repo:o/r': true, 'o/r:7': true, 'o/r:7:8': true}, {'o/r:7': {jobs: [job]}}, '', t);
  assert.deepEqual([...full.map(row => row.kind)], ['repo', 'run', 'job', 'step']);
  assert.equal(full[3].url, job.html_url);
  assert.deepEqual([...full.map(row => row.statusText)], ['neutral', 'failed', 'passed', 'failed']);
  const msg = model.rows([{repo: 'o/r', runs: [run]}], {'repo:o/r': true, 'o/r:7': true}, {}, '', t);
  assert.deepEqual([msg[2].kind, msg[2].statusText], ['message', '']);
  // message row for an expanded repository without runs
  const empty = (repo, filter = '') => model.rows([{repo: 'o/r', ...repo}], {'repo:o/r': true}, {}, filter, t);
  assert.deepEqual([empty({runs: []})[1].kind, empty({runs: []})[1].title, empty({runs: []})[1].statusText], ['message', 'Loading runs…', '']);
  assert.equal(empty({runs: [], summaryAt: 1})[1].title, 'No workflow runs');
  for (const flag of ['archived', 'disabled', 'blocked'])
    assert.equal(empty({runs: [], [flag]: true}).length, 1, flag + ' repositories have no loading row');
  assert.equal(empty({}, 'o/r').length, 2, 'filter-matched empty repository keeps its message');
  assert.equal(empty({runs: [], error: 'boom'}).length, 1);
  assert.equal(empty({runs: [], hidden: {queued: 2}})[1].kind, 'more');
  assert.equal(empty({runs: [], hidden: {queued: 2}}).length, 2);
  // statusText is a shown field: a change is one setProperty
  assert.ok(model.shownFields.includes('statusText'));
  const list = model.rows([{repo: 'o/r', runs: [run]}], {'repo:o/r': true}, {}, '', t);
  let ops = 0;
  const l = {rows: [], get count() { return this.rows.length; }, get(i) { return this.rows[i]; },
    insert(i, v) { this.rows.splice(i, 0, v); }, remove(i) { this.rows.splice(i, 1); }, move() {},
    setProperty(i, k, v) { ops++; this.rows[i][k] = v; }};
  model.syncRows(l, list); ops = 0;
  model.syncRows(l, list.map((row, i) => i === 1 ? {...row, statusText: 'passed'} : row));
  assert.equal(ops, 1);
}
console.log('Model: rows subtitle, statusText and message row passed');

// #43(b) step 10: search tokens match one held run; the fetched count shares the more row.
{
  const t = Date.now(), open = {'repo:o/r': true};
  const failed = {id: 1, status: 'completed', conclusion: 'failure', name: 'Build', head_branch: 'main', actor: 'alice', event: 'push'};
  const passed = {id: 2, status: 'completed', conclusion: 'success', name: 'Release', head_branch: 'feature', actor: 'bob', event: 'schedule'};
  const repo = {repo: 'o/r', description: 'release project', runs: [failed, passed]};
  const view = (filter, r = repo) => model.rows([r], open, {}, filter, t);
  const runIds = filter => Array.from(view(filter).filter(row => row.kind === 'run'), row => row.run);
  assert.deepEqual(runIds('branch:main'), ['1']);
  assert.deepEqual(runIds('Branch:MAIN actor:AL is:failed'), ['1']);
  assert.deepEqual(runIds('actor:bob'), ['2']);
  assert.deepEqual(runIds('is:failed'), ['1']);
  assert.deepEqual(runIds('IS:FAILED'), ['1']);
  assert.deepEqual(runIds('is:failed branch:feature'), [], 'success is not failed');
  assert.deepEqual(Array.from(view('actor:alice', {...repo, runs: [{...failed, actor_login: 'wrong'}]})
    .filter(row => row.kind === 'run'), row => row.run), ['1'], 'actor token uses the flattened actor from #42');
  assert.equal(view('actor:wrong', {...repo, runs: [{...failed, actor_login: 'wrong'}]}).length, 0);
  assert.deepEqual(runIds('branch:main actor:bob'), [], 'tokens must match the same run');
  assert.equal(view('branch:feature is:failed').length, 0);
  assert.deepEqual(runIds('branch:main release'), ['1'], 'plain text may match the repository');
  assert.equal(view('branch:main schedule').length, 0, 'plain text must still match');
  assert.deepEqual(runIds('branch:main Build'), ['1'], 'plain text may match the run');
  assert.equal(view('branch:feature o/r is:failed').length, 0, 'repository name cannot lift tokens');
  assert.equal(view('actor:alice', {repo: 'o/r'}).length, 0, 'unchecked repository has no matching run');
  assert.deepEqual(runIds('push'), ['1'], '#42 plain event search survives');
  assert.deepEqual(runIds('alice'), ['1'], '#42 plain actor search survives');
  assert.deepEqual(runIds('failed'), ['1'], '#42 plain state label search survives');
  assert.equal(view('branch:').length, 0, 'empty token value is plain text');
  assert.equal(view('is:open').length, 0, 'unknown is value is plain text');
  assert.equal(view('foo:bar').length, 0, 'unknown prefix is plain text');

  const moreRows = r => model.rows([r], open, {}, '', t);
  const more = r => moreRows(r).filter(row => row.kind === 'more');
  assert.equal(more({...repo, recentFetched: 10})[0].title, 'last 10 runs fetched · m loads 30 more');
  assert.equal(more({...repo, recentLimit: 40, recentFetched: 40})[0].title, 'last 40 runs fetched · m loads 30 more');
  assert.equal(more({...repo, recentLimit: 100, recentFetched: 100})[0].title, 'last 100 runs fetched');
  assert.equal(more({...repo, recentLimit: 40, recentFetched: 39}).length, 0);
  assert.equal(moreRows({...repo, recentFetched: 10}).at(-1).kind, 'more', 'fetched-only row follows runs');
  const withHidden = {...repo, hidden: {queued: 2}, recentFetched: 10};
  assert.equal(more(withHidden).length, 1);
  assert.equal(more(withHidden)[0].title, '+2 more queued · last 10 runs fetched · m loads 30 more');
  assert.equal(moreRows(withHidden)[1].kind, 'more', 'hidden count stays before completed runs');
  assert.equal(more({...repo, runs: [{...failed, status: 'queued'}, passed], recentFetched: 10})[0].title,
    'last 10 runs fetched · m loads 30 more', 'unfinished runs still count toward the fetched page');
  assert.ok(!view('branch:main', withHidden).some(row => row.kind === 'more'));
}
console.log('Model: search tokens and fetched-count row passed');
// #44 step 2: a selected row resolves to the whole job log or a failed run log.
{
  const repo = 'o/r', run = '7';
  const runs = [{id: 7, status: 'completed', conclusion: 'failure'}, {id: 9, status: 'completed', conclusion: 'success'}];
  const jobs = [
    {id: 8, name: 'failed', status: 'completed', conclusion: 'failure', steps: [{number: 1, name: 'Fail', status: 'completed'}]},
    {id: 10, name: 'passed', status: 'completed', conclusion: 'success'},
    {id: 11, name: 'cancelled', status: 'completed', conclusion: 'cancelled'},
    {id: 12, name: 'running', status: 'in_progress'}
  ];
  const detail = {[repo + ':' + run]: {jobs}};
  const open = {['repo:' + repo]: true};
  open[repo + ':' + run] = true;
  open[repo + ':' + run + ':8'] = true;
  const rows = model.rows([{repo, runs}], open, detail, '', Date.now());
  const row = (kind, job) => rows.find(r => r.kind === kind && (job === undefined || r.key === repo + ':' + run + ':' + job));
  const target = r => JSON.parse(JSON.stringify(model.logTarget(r, detail, runs)));
  assert.equal(row('job', 8).job, '8');
  assert.equal(row('step').job, '8');
  assert.deepEqual(target(row('job', 8)), {repo, run, job: '8', mode: 'failed'});
  assert.deepEqual(target(row('job', 10)), {repo, run, job: '10', mode: 'full'});
  assert.deepEqual(target(row('job', 11)), {repo, run, job: '11', mode: 'full'});
  assert.deepEqual(target(row('job', 12)), {error: 'Logs are available when the job finishes'});
  assert.deepEqual(target(row('step')), {repo, run, job: '8', mode: 'failed'});
  for (const kind of ['job', 'step']) {
    const selected = kind === 'step' ? row('step') : row('job', 8);
    assert.equal(model.logTarget(selected, detail, [{id: 7, status: 'in_progress'}]).error,
      'Logs are available when the run finishes');
    assert.equal(model.logTarget(selected, detail, []).error,
      'Logs are available when the run finishes');
  }
  assert.deepEqual(target(row('run')), {repo, run, mode: 'failed'});
  assert.deepEqual(target({...row('run'), run: '9'}), {error: 'Select a job to read its log'});
  assert.equal(target(row('repo')), null);
  assert.equal(target({kind: 'more', repo}), null);
  const list = counted();
  model.syncRows(list, rows);
  list.ops = 0;
  model.syncRows(list, rows.map(r => r.kind === 'job' || r.kind === 'step' ? {...r, job: 'other'} : r));
  assert.equal(list.ops, 0, 'job is not a delegate field');
}
console.log('Model: log targets passed');

{
  const body = fs.readFileSync('ActionsPanel.qml', 'utf8').split('    function viewLog() {')[1].split('    function openLog(')[0];
  const calls = [];
  const viewLog = vm.runInNewContext('(function() {' + body + ')',
    {viewProc:{running:true}, showNotice:message => calls.push(message),
      Polling:{requestLog:() => calls.push('fetch')}});
  viewLog();
  assert.deepEqual(calls, ['A log is already open']);
}
console.log('Model: view guard passed');

{
  for (let px = 0; px <= 40; px++) assert.equal(model.zoomed(px, 0), px);
  assert.equal(model.zoomed(12, 5), 18);
  assert.equal(model.zoomed(12, -3), 8);
  assert.equal(model.zoomed(10, -3), 7);
  assert.equal(model.zoomed(10, 5), 15);
  for (let px = 1; px <= 40; px++) {
    let previous = 0;
    for (let step = -3; step <= 5; step++) {
      const size = model.zoomed(px, step);
      assert.ok(size >= 1);
      assert.ok(size >= previous);
      previous = size;
    }
  }
  for (let step = -3; step <= 5; step++) assert.equal(model.zoomed(0, step), 0);
  assert.equal(model.clampStep(9), 5);
  assert.equal(model.clampStep(-9), -3);
  assert.equal(model.clampStep(-4), -3);
  assert.equal(model.clampStep(NaN), 0);
  assert.equal(model.clampStep('3'), 3);
  assert.equal(model.clampStep(undefined), 0);
  assert.equal(model.zoomed(12, 99), model.zoomed(12, 5));
  assert.equal(model.zoomed(12, -99), model.zoomed(12, -3));
  let step = 0;
  for (let i = 0; i < 5; i++) step = model.clampStep(step + 1);
  assert.equal(step, 5);
  assert.equal(model.clampStep(step + 1), step);
  for (let i = 0; i < 5; i++) step = model.clampStep(step - 1);
  assert.equal(step, 0);
  for (let i = 0; i < 3; i++) step = model.clampStep(step - 1);
  assert.equal(step, -3);
  assert.equal(model.clampStep(step - 1), step);
  assert.equal(model.fontPx(10, -3), 9);
  assert.equal(model.fontPx(8, -3), 8);
  assert.equal(model.fontPx(20, -3), 14);
  for (let px = 1; px <= 40; px++) {
    let previous = 0;
    for (let s = -3; s <= 5; s++) {
      const size = model.fontPx(px, s);
      assert.ok(size >= Math.min(px, 9) && size >= previous);
      if (s >= 0) assert.equal(size, model.zoomed(px, s));
      previous = size;
    }
  }
  const panelQml = fs.readFileSync('ActionsPanel.qml', 'utf8');
  for (const n of ['title', 'body', 'caption']) assert.ok(panelQml.includes(`Model.fontPx(Style.font.${n}, textStep)`));
}
console.log('Model: text size passed');
// #44 step 9: watched run marker and notification text.
{
  const run = {id: 7, status: 'in_progress', name: 'Build'};
  const repo = [{repo: 'o/r', runs: [run]}], open = {'repo:o/r': true};
  const row = (watches, item = run) => model.rows([{...repo[0], runs: [item]}], open, {}, '', 0, '', watches)[1];
  assert.equal(row().info, '');
  assert.equal(row({}).info, '');
  assert.equal(row({'o/r:7': true}).info, 'watching');
  const timed = {...run, started_at: '2026-01-01T00:00:00Z'};
  const at = Date.parse('2026-01-01T00:01:00Z');
  assert.equal(model.rows([{repo: 'o/r', runs: [timed]}], open, {}, '', at, '', {'o/r:7': true})[1].info, '1m 0s · watching');
  assert.equal(model.rows([{repo: 'o/r', runs: [timed]}], open, {}, '', at)[1].info, '1m 0s');

  const words = {success:'succeeded', failure:'failed', cancelled:'cancelled', timed_out:'timed out',
    startup_failure:'failed to start', skipped:'skipped', neutral:'finished', action_required:'finished', stale:'finished',
    anything_else:'finished', constructor:'finished'};
  for (const [conclusion, title] of Object.entries(words))
    assert.deepEqual(JSON.parse(JSON.stringify(model.notice({kind:'done', repo:'o/r', name:'Build', conclusion}))),
      {title, body:'o/r · Build'}, conclusion);
  assert.deepEqual(JSON.parse(JSON.stringify(model.notice({kind:'done', repo:'o/r', name:'R&D <build>', conclusion:'success'}))),
    {title:'succeeded', body:'o/r · R D  build '});
  assert.deepEqual(JSON.parse(JSON.stringify(model.notice({kind:'done', repo:'o/r', name:'x'.repeat(81), conclusion:'success'}))),
    {title:'succeeded', body:'o/r · ' + 'x'.repeat(80)});
  assert.deepEqual(JSON.parse(JSON.stringify(model.notice({kind:'paused'}))),
    {title:'Watching paused', body:'Run gh auth login, then open the panel'});
  assert.deepEqual(JSON.parse(JSON.stringify(model.notice({kind:'lost', repo:'o/r', name:'R&D build'}))),
    {title:'Watch stopped', body:'o/r · R D build GitHub no longer shows this run.'});
}
// #46 step 3: the pane reads only the cleaned parent run and injected time.
{
  const now = Date.parse('2026-01-01T01:00:00Z');
  const run = {name:'CI', path:'.github/workflows/check.yml', status:'completed', conclusion:'success',
    head_branch:'main', head_sha:'a'.repeat(40), event:'push', actor:'a', triggering_login:'b',
    run_attempt:1, run_started_at:'2026-01-01T00:57:00Z'};
  const lines = item => JSON.parse(JSON.stringify(model.detail(item, now)));
  const values = item => Object.fromEntries(lines(item).map(line => [line.label, line.value]));
  assert.deepEqual(lines(run), [
    {label:'Workflow', value:'CI · .github/workflows/check.yml'},
    {label:'Result', value:'passed'}, {label:'Branch', value:'main'},
    {label:'Commit', value:'aaaaaaa'}, {label:'Event', value:'push'},
    {label:'Actor', value:'a (triggered by b)'}, {label:'Attempt', value:'1'},
    {label:'Started', value:'3m ago'}, {label:'Duration', value:'3m 0s'}]);
  assert.equal(values(run).Commit.length, 7);
  const missing = values({status:'queued'});
  for (const field of ['Commit', 'Actor', 'Event']) assert.equal(missing[field], 'unknown');
  for (const sha of ['z'.repeat(40), 'a'.repeat(7), 'a'.repeat(32) + '\u001b[31m' + 'a'.repeat(3), 'A'.repeat(40)])
    assert.equal(values({...run, head_sha:sha}).Commit, 'unknown');
  assert.equal(values({...run, triggering_login:'a'}).Actor, 'a');
  assert.equal(values({...run, triggering_login:''}).Actor, 'a');
  assert.equal(values({...run, triggering_login:5}).Actor, 'a');
  assert.equal(values({...run, actor:{login:'a'}}).Actor, 'unknown (triggered by b)');
  assert.equal(values({...run, run_attempt:2}).Attempt, '2');
  for (const attempt of [0, '2', undefined]) assert.equal(values({...run, run_attempt:attempt}).Attempt, 'unknown');
  assert.equal(values({...run, head_sha:['a'.repeat(40)]}).Commit, 'unknown');
  assert.equal(values({...run, run_started_at:{toString:null}}).Started, 'unknown');
  assert.equal(values({...run, run_started_at:{toString:null}}).Duration, 'unknown');
  assert.equal(values({...run, conclusion:{}}).Result, 'unknown');
  assert.equal(values({...run, name:[]}).Workflow, '.github/workflows/check.yml');
  assert.equal(values({...run, name:[], path:[]}).Workflow, 'unknown');
  assert.equal(values({...run, run_started_at:'bad'}).Started, 'unknown');
  assert.equal(values({...run, run_started_at:'bad'}).Duration, 'unknown');
  assert.equal(values({...run, head_branch:{toString:null}}).Branch, 'unknown');
  assert.equal(values({...run, event:{toString:null}}).Event, 'unknown');
  const throwing = {...run};
  Object.defineProperty(throwing, 'event', {get() { throw Error('bad field'); }});
  assert.equal(values(throwing).Event, 'unknown');
  for (const item of [null, undefined, 'x']) assert.deepEqual(lines(item), [{label:'', value:'Select a run'}]);
  const rows = model.rows([{repo:'o/r', runs:[]}], {'repo:o/r':true}, {}, '', now);
  for (const row of rows) {
    assert.ok(['repo', 'message'].includes(row.kind));
    assert.deepEqual(lines(['run', 'job', 'step'].includes(row.kind) ? run : null), [{label:'', value:'Select a run'}]);
  }
  for (const [total, avail, expected] of [[400, 280, 160], [240, 150, 30], [100, 40, 20], [800, 700, 180]])
    assert.equal(model.paneHeight(total, avail, 180, 120, 20), expected);
  assert.equal(model.paneHeight(60, 10, 180, 120, 20), 10);  // less room than one line: never past avail
  assert.equal(model.paneHeight(40, -5, 180, 120, 20), 0);
}
console.log('Model: detail and pane height passed');
console.log('Model: watched rows and notices passed');

// Exercise the QML key handler as JavaScript without a display.
{
  const body = fs.readFileSync('ActionsPanel.qml', 'utf8').split('Keys.onPressed: function(event) {')[1]
    .split('\n                }\n\n                Column {')[0];
  const calls = [];
  const root = {confirm:null, textKey:event => { if (event.key === 61 && event.modifiers === 1) { calls.push('zoom'); return true; } return false; },
    copyLink:() => calls.push('copy'), toggleWatch:() => calls.push('watch'), loadMore:() => calls.push('more'), answer:yes => calls.push(yes ? 'yes' : 'no')};
  const Qt = {ControlModifier:1, AltModifier:2, MetaModifier:4, Key_W:87, Key_Y:89, Key_N:78, Key_Escape:27};
  const handler = vm.runInNewContext('(function(event) {' + body + '\n})',
    {root, Qt, Quickshell:{execDetached:() => calls.push('keys')}});
  const press = (key, text, modifiers = 0, isAutoRepeat = false) => { const event = {key, text, modifiers, isAutoRepeat, accepted:false}; handler(event); return event.accepted; };
  press(Qt.Key_Y, 'y', 0, true);
  press(0, '?', 0, true);
  press(Qt.Key_W, 'w', 0, true);
  press(77, 'm', 0, true);
  assert.deepEqual(calls, []);
  assert.equal(press(77, 'm'), true);
  assert.deepEqual(calls, ['more']);
  assert.equal(press(77, 'm', Qt.ControlModifier), false);
  assert.deepEqual(calls, ['more']);
  assert.equal(press(61, '=', Qt.ControlModifier), true);
  assert.deepEqual(calls, ['more', 'zoom']);
  const searchBody = fs.readFileSync('ActionsPanel.qml', 'utf8').split('id: searchField')[1]
    .split('Keys.onPressed: function(event) {')[1].split('\n                        }\n                        Text {')[0];
  const searchHandler = vm.runInNewContext('(function(event) {' + searchBody + '\n})', {root, Qt});
  const searchEvent = {key:61, text:'=', modifiers:Qt.ControlModifier, accepted:false};
  searchHandler(searchEvent);
  assert.equal(searchEvent.accepted, true, 'search field accepts Ctrl+=');
  assert.deepEqual(calls, ['more', 'zoom', 'zoom'], 'search field calls textKey');
  assert.equal(press(77, 'M'), false, 'Shift+M passes through');
  press(Qt.Key_Y, 'y');
  press(Qt.Key_W, 'w');
  assert.deepEqual(calls, ['more', 'zoom', 'zoom', 'copy', 'watch']);
  const ctrlWatch = {key:Qt.Key_W, text:'w', modifiers:Qt.ControlModifier, isAutoRepeat:false};
  handler(ctrlWatch);
  assert.equal(ctrlWatch.accepted,false);
  root.confirm = {text:'confirm'};
  press(Qt.Key_W, 'w');
  assert.equal(press(77, 'm'), true);
  press(Qt.Key_Y, 'y', Qt.ControlModifier);
  press(Qt.Key_Y, 'y', 0, true);
  assert.deepEqual(calls, ['more', 'zoom', 'zoom', 'copy', 'watch']);
  press(Qt.Key_Y, 'y');
  press(Qt.Key_N, 'n');
  press(Qt.Key_Escape, '');
  assert.deepEqual(calls, ['more', 'zoom', 'zoom', 'copy', 'watch', 'yes', 'no', 'no']);
}

{
  const qml = fs.readFileSync('ActionsPanel.qml', 'utf8');
  assert.doesNotMatch(qml, /pixelSize:\s*Style\.font\b/);
  assert.deepEqual(qml.split('\n').filter(line => line.includes('Style.space(')).map(line => line.trim()), [
    'function sp(n) { return Model.zoomed(Style.space(n), textStep) }',
    'width: Math.min(Style.space(900), window.width - Style.gapsOut * 2)',
    'height: Math.min(Style.space(680), window.height - Style.gapsOut * 2)',
    'borderSpec: Border.surfaceSpec("menu", "border", Commons.Color.menu.border, Math.max(1, Style.space(2)))'
  ]);
}

// Exercise the panel lifecycle and fixed watch messages without a display.
{
  const qml=fs.readFileSync('ActionsPanel.qml','utf8');
  const closeBody=qml.split('    function close() {')[1].split('\n    }\n    function toggle()')[0];
  const state={opened:true, polling:{watches:{'a/b:1':{}}}, requestProc:{running:true},
    workerBusy:true, requestInfo:{kind:'run',repo:'a/b',run:'1'}, confirm:{},
    Polling:{close:() => {}}, root:null};
  vm.runInNewContext('(function(){'+closeBody+'\n})',state)();
  assert.equal(state.requestProc.running,false,'closing stops a watched run request');
  const watchBody=qml.split('    function toggleWatch() {')[1].split('\n    }\n    function copyLink()')[0];
  const notices=[];
  const watchState={current:{kind:'run',repo:'a/b',run:'1'}, polling:{}, Date:{now:()=>0},
    Polling:{runFor:()=>({status:'in_progress',name:'Build'}),watch:()=> 'on'},
    Model:{notice:()=>({title:'succeeded'})}, showNotice:t=>notices.push(t), adopt:()=>{}, pump:()=>{}};
  const toggle=vm.runInNewContext('(function(){'+watchBody+'\n})',watchState);
  toggle();
  watchState.Polling.watch=()=> 'off'; toggle();
  watchState.Polling.watch=()=> 'full'; toggle();
  assert.deepEqual(notices,['Watching this run; lost if the shell restarts','Stopped watching','At most 5 runs can be watched']);
  assert.match(qml,/onExited: \{ root\.noticeBusy = false; Qt\.callLater\(root\.drainNotices\) \}/);
  assert.match(qml,/\["notify-send", "--app-name=GitHub Actions", "--", m\.title, m\.body\]/);
}

{
  const body = fs.readFileSync('ActionsPanel.qml', 'utf8').split('    function loadMore() {')[1]
    .split('\n    function pump() {')[0];
  const calls = [];
  const context = {current:{repo:'a/b'}, polling:{}, Date, Polling:{more:() => false},
    showNotice:text => calls.push(text), adopt:() => calls.push('adopt'), pump:() => calls.push('pump')};
  const loadMore = vm.runInNewContext('(function() {' + body + ')', context);
  loadMore();
  assert.deepEqual(calls, ['Refreshing; press m again in a moment', 'adopt', 'pump']);
  calls.length = 0;
  context.Polling.more = () => true;
  loadMore();
  assert.deepEqual(calls, ['adopt', 'pump']);
}

// #43: repository health row and sort.
{
  const t = Date.UTC(2026, 0, 2, 12, 0, 0), h = 3600000, min = 60000;
  const last = (conclusion, confirmedAt = t) => ({id: 1, conclusion, at: new Date(t - 3 * h - 40 * min).toISOString(), confirmedAt});
  const one = repo => { const r = model.rows([{checked: 'x', active: 0, ...repo}], {}, {}, '', t)[0]; return [r.status, r.info]; };
  assert.deepEqual(one({repo: 'a/a', active: 2, last: last('failure')}), ['failure', '✕ 3h · 2 running']);
  assert.deepEqual(one({repo: 'a/a', last: last('timed_out')}), ['failure', '✕ 3h · 0 running']);
  assert.deepEqual(one({repo: 'a/a', last: last('success')}), ['success', '✓ 3h · 0 running']);
  assert.deepEqual(one({repo: 'a/a', last: last('success', t - 31 * min)}), ['neutral', '✓ 3h · 0 running · stale']);
  assert.deepEqual(one({repo: 'a/a', last: last('success', t - 29 * min)}), ['success', '✓ 3h · 0 running']);
  assert.deepEqual(one({repo: 'a/a', last: last('failure', t - 31 * min)}), ['failure', '✕ 3h · 0 running · stale']);
  assert.deepEqual(one({repo: 'a/a', last: last('cancelled')}), ['neutral', '⊘ 3h · 0 running']);
  assert.deepEqual(one({repo: 'a/a'}), ['neutral', 'no result · 0 running']);
  assert.deepEqual(one({repo: 'a/a', error: 'x', last: last('failure')}), ['error', 'unavailable']);
  assert.deepEqual(one({repo: 'a/a', archived: true, last: last('failure')}), ['neutral', 'archived']);
  assert.deepEqual(one({repo: 'a/a', disabled: true}), ['neutral', 'disabled']);
  assert.deepEqual(one({repo: 'a/a', checked: undefined}), ['neutral', 'not checked']);
  assert.equal(model.rows([{repo: 'a/a', checked: 'x', last: last('failure')}], {}, {}, '', t)[0].statusText, 'failed');
  assert.equal(model.rows([{repo: 'a/a', checked: 'x', last: last('success')}], {}, {}, '', t)[0].statusText, 'passed');
  assert.equal(model.rows([{repo: 'a/a', checked: 'x'}], {}, {}, '', t)[0].statusText, 'neutral');
  for (const [seconds, expected] of [[59, '59s'], [60, '1m'], [3600, '1h'], [3 * 3600 + 40 * 60, '3h']])
    assert.equal(model.ago(new Date(t - seconds * 1000).toISOString(), t), expected);
  const order = (list, now = t) => Array.from(model.rows(list, {}, {}, '', now), row => row.title).join(' ');
  const mix = [{repo: 'a/idle', checked: 'x', active: 0}, {repo: 'b/run1', checked: 'x', active: 1}, {repo: 'c/fail', checked: 'x', active: 0, last: last('failure')},
    {repo: 'd/run3', checked: 'x', active: 3}, {repo: 'e/fail', checked: 'x', active: 0, last: last('failure')}, {repo: 'f/failrun', checked: 'x', active: 1, last: last('failure')},
    {repo: 'g/new'}];
  assert.equal(order(mix), 'c/fail e/fail f/failrun d/run3 b/run1 a/idle g/new');
  assert.equal(order(mix, t + 40 * min), order(mix), 'time never reorders');
  vm.runInContext('var nativeSort = Array.prototype.sort; Array.prototype.sort = function(compare) { this.reverse(); return nativeSort.call(this, compare); }', model);
  try { assert.equal(order(mix), 'c/fail e/fail f/failrun d/run3 b/run1 a/idle g/new', 'ties follow catalogue order even with unstable sort'); }
  finally { vm.runInContext('Array.prototype.sort = nativeSort', model); }
  const vmPoll = {};
  vm.createContext(vmPoll);
  vm.runInContext(fs.readFileSync('Polling.js', 'utf8'), vmPoll);
  assert.equal(model.STALE, 3 * vmPoll.TIMING.idle);
  assert.equal(model.PR_REFRESH, vmPoll.TIMING.prs);
  assert.equal(model.PR_REFRESH_ACTIVE, vmPoll.TIMING.prsActive);
  // syncRows: a repository turning failing gives the same rows as a fresh build.
  const healthy = [{repo: 'a/a', checked: 'x', active: 0, last: last('success')}, {repo: 'b/b', checked: 'x', active: 0}];
  const failing = [{...healthy[0], last: last('failure')}, healthy[1]];
  const sync = counted();
  model.syncRows(sync, model.rows(healthy, {}, {}, '', t));
  model.syncRows(sync, model.rows(failing, {}, {}, '', t));
  assert.deepEqual(JSON.parse(JSON.stringify(sync.store.map(r => r.rowData))), JSON.parse(JSON.stringify(model.rows(failing, {}, {}, '', t))));
}

// #63: pull request rows, check rows, more rows, filtering, empty text, status line and accessible names.
{
  const now = new Date(2026, 0, 2, 0, 0, 0).getTime();
  const resetAt = new Date(2026, 0, 2, 3, 4, 5).getTime();
  assert.equal(model.quotaText(499, resetAt, resetAt - 1), '499 API requests left · resets 03:04');
  assert.equal(model.quotaText(499, resetAt, resetAt - 1, 'GraphQL points'), '499 GraphQL points left · resets 03:04');
  assert.equal(model.quotaText(1234, resetAt, resetAt - 1, 'GraphQL points'), '1,234 GraphQL points left');

  const pr1 = {
    repo: 'o/r', number: 12, title: 'Add checks', branch: 'feat/checks', draft: false,
    url: 'https://github.com/o/r/pull/12',
    checks: {
      state: 'failure', total: 4,
      items: [
        {name: 'build', status: 'completed', conclusion: 'success', url: 'https://github.com/o/r/actions/runs/9001/job/1', repo: 'o/r', run: '9001'},
        {name: 'test', status: 'completed', conclusion: 'failure', url: 'https://ci.example.com/build/2', repo: '', run: ''},
        {name: 'lint', status: 'in_progress', conclusion: '', url: '', repo: 'o/r', run: '9002'}
      ]
    }
  };
  const pr2 = {
    repo: 'o/r', number: 13, title: 'WIP work', branch: 'draft-branch', draft: true,
    url: '',
    checks: {
      state: 'pending', total: 2,
      items: [
        {name: 'ci/check', status: 'pending', conclusion: '', url: 'https://github.com/o/r/runs/1', repo: 'o/r', run: ''}
      ]
    }
  };
  const prPass = {repo: 'a/b', number: 1, title: 'Green', branch: 'main', draft: false, url: 'https://github.com/a/b/pull/1',
    checks: {state: 'success', total: 1, items: []}};
  const prNone = {repo: 'a/b', number: 2, title: 'Docs', branch: 'docs', draft: false, url: 'https://github.com/a/b/pull/2',
    checks: {state: 'none'}};
  const prUnavail = {repo: 'a/b', number: 3, title: 'SSO', branch: 'sso', draft: false, url: 'https://evil.example/pull/3',
    checks: {state: 'unavailable'}};

  assert.deepEqual(JSON.parse(JSON.stringify(model.prRows(null, {}, '', now))), []);
  assert.deepEqual(JSON.parse(JSON.stringify(model.prRows({list: null, total: 0}, {}, '', now))), []);

  const allStates = model.prRows({list: [prPass, pr1, pr2, prNone, prUnavail], total: 5, at: now}, {}, '', now);
  assert.deepEqual(Array.from(allStates, r => [r.key, r.title, r.subtitle, r.status, r.statusText, r.info, r.url]), [
    ['pr:a/b#1', 'a/b #1 Green', 'main', 'success', 'passed', '1 checks', 'https://github.com/a/b/pull/1'],
    ['pr:o/r#12', 'o/r #12 Add checks', 'feat/checks', 'failure', 'failed', '4 checks', 'https://github.com/o/r/pull/12'],
    ['pr:o/r#13', 'Draft · o/r #13 WIP work', 'draft-branch', 'in_progress', 'running', '2 checks', ''],
    ['pr:a/b#2', 'a/b #2 Docs', 'docs', '', 'no checks', '', 'https://github.com/a/b/pull/2'],
    ['pr:a/b#3', 'a/b #3 SSO', 'sso', 'error', 'checks unavailable', '', '']
  ]);

  // Age in seconds (when a PR is pending, interval is 15s) and minutes (when >= 60s or interval is 60s).
  assert.equal(model.prRows({list: [pr2], total: 1, at: now - 15000}, {}, '', now)[0].info, '2 checks');
  assert.equal(model.prRows({list: [pr2], total: 1, at: now - 40000}, {}, '', now)[0].info, '2 checks · checked 40s ago');
  assert.equal(model.prRows({list: [pr2], total: 1, at: now - 180000}, {}, '', now)[0].info, '2 checks · checked 3m ago');
  assert.equal(model.prRows({list: [prPass], total: 1, at: now - 40000}, {}, '', now)[0].info, '1 checks', 'no pending PR uses 60s interval');
  assert.equal(model.prRows({list: [prPass], total: 1, at: now - 60000}, {}, '', now)[0].info, '1 checks');
  assert.equal(model.prRows({list: [prPass], total: 1, at: now - 180000}, {}, '', now)[0].info, '1 checks · checked 3m ago');

  // Expanded check rows, both "more" rows (with and without PR link), parent and depth.
  const open = {'pr:o/r#12': true, 'pr:o/r#13': true};
  const expandedRows = JSON.parse(JSON.stringify(model.prRows({list: [pr1, pr2], total: 5, at: now}, open, '', now)));
  assert.deepEqual(expandedRows.map(r => [r.kind, r.key, r.parent, r.depth]), [
    ['pr', 'pr:o/r#12', '', 0],
    ['check', 'pr:o/r#12:0:build', 'pr:o/r#12', 1],
    ['check', 'pr:o/r#12:1:test', 'pr:o/r#12', 1],
    ['check', 'pr:o/r#12:2:lint', 'pr:o/r#12', 1],
    ['more', 'pr:o/r#12:more', 'pr:o/r#12', 1],
    ['pr', 'pr:o/r#13', '', 0],
    ['check', 'pr:o/r#13:0:ci/check', 'pr:o/r#13', 1],
    ['more', 'pr:o/r#13:more', 'pr:o/r#13', 1],
    ['more', 'prs:more', '', 0]
  ]);
  assert.deepEqual(expandedRows[1], {
    kind: 'check', key: 'pr:o/r#12:0:build', parent: 'pr:o/r#12', depth: 1,
    title: 'build', subtitle: '', status: 'success', statusText: 'passed', info: '',
    repo: 'o/r', run: '9001', url: 'https://github.com/o/r/actions/runs/9001/job/1', external: false
  });
  assert.deepEqual(expandedRows[2], {
    kind: 'check', key: 'pr:o/r#12:1:test', parent: 'pr:o/r#12', depth: 1,
    title: 'test', subtitle: '', status: 'failure', statusText: 'failed', info: '',
    repo: '', run: '', url: '', external: true
  });
  assert.deepEqual(expandedRows[3], {
    kind: 'check', key: 'pr:o/r#12:2:lint', parent: 'pr:o/r#12', depth: 1,
    title: 'lint', subtitle: '', status: 'in_progress', statusText: 'running', info: '',
    repo: 'o/r', run: '9002', url: '', external: false
  });
  assert.equal(expandedRows[4].title, '1 more checks on GitHub');
  assert.equal(expandedRows[4].url, 'https://github.com/o/r/pull/12/checks');
  assert.equal(expandedRows[7].title, '1 more checks on GitHub');
  assert.equal(expandedRows[7].url, '', 'pull request without a link gives an empty checks-more url');
  assert.equal(expandedRows[8].title, '3 more on GitHub');
  assert.equal(expandedRows[8].url, 'https://github.com/pulls');

  // Filter on repository, title, branch, status and check name.
  const filterRows = q => Array.from(model.prRows({list: [pr1, pr2, prNone], total: 5, at: now}, open, q, now), r => r.key);
  assert.deepEqual(filterRows('Add checks'), ['pr:o/r#12', 'pr:o/r#12:0:build', 'pr:o/r#12:1:test', 'pr:o/r#12:2:lint', 'pr:o/r#12:more']);
  assert.deepEqual(filterRows('draft-branch'), ['pr:o/r#13', 'pr:o/r#13:0:ci/check', 'pr:o/r#13:more']);
  assert.deepEqual(filterRows('no checks'), ['pr:a/b#2']);
  assert.deepEqual(filterRows('lint'), ['pr:o/r#12', 'pr:o/r#12:2:lint'], 'PR with a matching check is shown with that check');
  assert.deepEqual(filterRows('queued'), ['pr:o/r#13', 'pr:o/r#13:0:ci/check']);
  assert.deepEqual(filterRows('nomatch'), []);

  // prEmptyText states.
  assert.equal(model.prEmptyText({accountChecked: false, accountVerified: false, prs: {list: null, error: 'err'}}),
    'Verifying your GitHub login…');
  assert.equal(model.prEmptyText({accountChecked: true, accountVerified: false, prs: {list: null, error: 'err'}}),
    'Pull requests need a verified GitHub login; check gh auth status');
  assert.equal(model.prEmptyText({accountChecked: true, accountVerified: true, prs: {list: null, error: 'token refused'}}),
    'token refused');
  assert.equal(model.prEmptyText({accountChecked: true, accountVerified: true, prs: {list: null, error: ''}}),
    'Loading pull requests…');
  assert.equal(model.prEmptyText({accountChecked: true, accountVerified: true, prs: {list: [], error: ''}}),
    'No open pull requests');
  assert.equal(model.prEmptyText({accountChecked: true, accountVerified: true, prs: {list: [pr1], error: ''}, filter: 'xyz'}),
    'No match for "xyz"');

  // prStatusLine with notice, error, cooldown and GraphQL quota label.
  const prBase = {notice: 'note', noticeUntil: now + 1, cooldown: 0,
    prs: {list: [pr1, pr2], total: 5, error: ''}, gqlRemaining: 499, gqlResetAt: resetAt};
  assert.deepEqual(JSON.parse(JSON.stringify(model.prStatusLine(prBase, now))), {
    text: 'note · 5 open pull requests',
    urgent: false,
    quota: '499 GraphQL points left · resets 03:04'
  });
  assert.equal(model.prStatusLine({...prBase, notice: '', prs: {list: null, total: 0, error: ''}}, now).text, '',
    'no count before the first list');
  assert.deepEqual(JSON.parse(JSON.stringify(model.prStatusLine({...prBase, notice: '', prs: {...prBase.prs, error: 'Some checks could not be read'}}, now))), {
    text: 'Some checks could not be read',
    urgent: true,
    quota: '499 GraphQL points left · resets 03:04'
  });
  assert.deepEqual(JSON.parse(JSON.stringify(model.prStatusLine({...prBase, cooldown: now + 60000, prs: {...prBase.prs, error: 'GitHub rate limit'}}, now))), {
    text: 'note · GitHub rate limit · GitHub paused until 00:01:00',
    urgent: true,
    quota: '499 GraphQL points left · resets 03:04'
  });
  assert.equal(model.prStatusLine({...prBase, notice: '', cooldown: now + 60000}, now).urgent, true);

  // accessibleName for pr and check rows.
  assert.equal(model.accessibleName(expandedRows[0], false), 'pull request: o/r #12 Add checks, failed, collapsed');
  assert.equal(model.accessibleName(expandedRows[0], true), 'pull request: o/r #12 Add checks, failed, expanded');
  assert.equal(model.accessibleName(expandedRows[1], false), 'check: build, passed');
}
console.log('Model: pull request rows, filter, empty text, status line and accessible names passed');
