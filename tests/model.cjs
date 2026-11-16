const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = {};
vm.createContext(model);
vm.runInContext(fs.readFileSync('ActionsModel.js', 'utf8'), model);
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
assert.equal(ranked[0].info, '2 running');
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
  assert.ok(view(run, stale, 'o/r:9')[1].subtitle.includes('jobs 4m old, not refreshing'));
  const frozen = view(run, stale, 'o/r:9')[2].info;
  assert.equal(view(run, stale, 'o/r:9', undefined, now + 600000)[2].info, frozen, 'timer stays at the last fetch');
  const fresh = view(run, stale, 'o/r:7');
  assert.ok(fresh[1].subtitle.includes('jobs fetched 00:56:00 UTC') && !fresh[1].subtitle.includes('not refreshing'));
  assert.notEqual(view(run, stale, 'o/r:7', undefined, now + 600000)[2].info, fresh[2].info, 'live timer uses now');
  const done = {...run, status: 'completed', conclusion: 'success'};
  assert.ok(!view(done, {...stale, finalAttempt: 1}, '')[1].subtitle.includes('not refreshing'));
  assert.ok(view(done, {...stale, finalAttempt: 2}, '')[1].subtitle.includes('not refreshing'));
  assert.ok(view(run, {...stale, updated: at(75 * 60000)}, '')[1].subtitle.includes('jobs 1h 15m old'));
  const err = view(run, {...stale, error: 'rate limited'}, '');
  assert.deepEqual([err[2].kind, err[2].title, err[3].kind], ['message', 'rate limited', 'job']);
  assert.ok(!view(run, {error: 'rate limited'}, '')[1].subtitle.includes('jobs '), 'no stamp without updated');
  assert.ok(view(run, stale, '', {'repo:o/r': true})[1].subtitle.includes('jobs fetched'), 'collapsed run keeps jobs fetched');
  assert.equal(view(run, stale)[1].subtitle.includes('not refreshing'), true, 'five arguments still work');
}
console.log('Model: not-refreshing marker passed');
