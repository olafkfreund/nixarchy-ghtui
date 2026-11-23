// Row rebuild benchmark for #30; not a test. Usage: node tests/bench-rows.cjs <dir containing ActionsModel.js>
// ponytail: an array stands in for QML ListModel, so these are lower bounds; the operation counts are exact.
const fs = require('node:fs');
const vm = require('node:vm');
const m = {};
vm.createContext(m);
vm.runInContext(fs.readFileSync((process.argv[2] || '.') + '/ActionsModel.js', 'utf8'), m);

let ops = 0;
function Model() { this.a = []; }
Object.defineProperty(Model.prototype, 'count', {get() { return this.a.length; }});
Model.prototype.get = function(i) { return this.a[i]; };
Model.prototype.insert = function(i, o) { ops++; this.a.splice(i, 0, o); };
Model.prototype.move = function(f, t, n) { ops++; const x = this.a.splice(f, n); this.a.splice(t, 0, ...x); };
Model.prototype.setProperty = function(i, k, v) { ops++; this.a[i][k] = v; };
Model.prototype.remove = function(i, n) { ops++; this.a.splice(i, n); };

function repos(n, hidden) {
  const runs = [], t0 = Date.parse('2026-09-24T10:00:00Z');
  for (let i = 0; i < n; i++) runs.push({id: 100000 + i, status: 'queued', name: 'CI', display_title: 'PR #' + i,
    head_branch: 'fork-' + i, run_number: i, run_started_at: new Date(t0 + i * 1000).toISOString(),
    html_url: 'https://github.com/o/r/actions/runs/' + i});
  for (let i = 0; i < 10; i++) runs.push({id: i + 1, status: 'completed', conclusion: 'success', name: 'CI', head_branch: 'main',
    run_number: i, run_started_at: '2026-09-24T09:00:00Z', updated_at: '2026-09-24T09:05:00Z'});
  return [{repo: 'o/r', runs, checked: 'x', active: 0, hidden}, {repo: 'o/other', runs: [], checked: 'x', active: 0}];
}
function median(times) { times.sort((a, b) => a - b); return times[times.length >> 1].toFixed(1); }
function time(setup, f, k) {
  const t = [];
  for (let i = 0; i < k; i++) { const x = setup(i); const s = process.hrtime.bigint(); f(x, i); t.push(Number(process.hrtime.bigint() - s) / 1e6); }
  return median(t);
}
const expanded = {'repo:o/r': true}, now = Date.parse('2026-09-24T12:00:00Z');
function fresh(base) { const x = new Model(); m.syncRows(x, base); return x; }
function removed(base) { const r = base.slice(); r.splice(2, 1); return r; }
function toTop(base) { const r = base.slice(); const [y] = r.splice(r.length - 11, 1); r.splice(1, 0, y); return r; }

console.log('| Queued runs | Rows | Tick | One removed | Moved to top | Reversed |');
console.log('| ---: | ---: | ---: | ---: | ---: | ---: |');
for (const n of [100, 500, 1000, 2000, 5000]) {
  const data = repos(n), base = m.rows(data, expanded, {}, '', now), model = fresh(base);
  const tick = time(() => null, (_, i) => m.syncRows(model, m.rows(data, expanded, {}, '', now + (i + 1) * 1000)), 15);
  const one = time(() => fresh(base), x => m.syncRows(x, removed(base)), 7);
  const top = time(() => fresh(base), x => m.syncRows(x, toTop(base)), 7);
  const rev = time(() => fresh(base), x => m.syncRows(x, base.slice().reverse()), 3);
  console.log(`| ${n} | ${base.length} | ${tick} ms | ${one} ms | ${top} ms | ${rev} ms |`);
}
{
  // The capped workload: 5,000 queued runs, of which one page of 100 is fetched.
  const data = repos(100, {queued: 4900}), base = m.rows(data, expanded, {}, '', now), model = fresh(base);
  const tick = time(() => null, (_, i) => m.syncRows(model, m.rows(data, expanded, {}, '', now + (i + 1) * 1000)), 15);
  console.log(`\nCapped (100 of 5000 queued fetched): ${base.length} rows, tick ${tick} ms`);
}
{
  // #63: 50 pull requests x 50 checks, all expanded (2,550 rows); budget is < 15 ms (1,650-row budget scaled by row count).
  const list = [], open = {};
  for (let i = 0; i < 50; i++) {
    const number = i + 1, repo = 'o/r';
    open[`pr:${repo}#${number}`] = true;
    const items = [];
    for (let j = 0; j < 50; j++) items.push({name: 'check-' + j, status: j % 2 ? 'completed' : 'in_progress',
      conclusion: j % 2 ? 'success' : '', url: `https://github.com/${repo}/runs/${j}`, repo, run: String(j + 1)});
    list.push({repo, number, title: 'PR #' + number, branch: 'feat-' + number, draft: i % 5 === 0,
      url: `https://github.com/${repo}/pull/${number}`, checks: {state: 'pending', total: 50, items}});
  }
  const data = {list, total: 50, at: now - 20000}, base = m.prRows(data, open, '', now), model = fresh(base);
  const tick = time(() => null, (_, i) => m.syncRows(model, m.prRows(data, open, '', now + (i + 1) * 1000)), 15);
  console.log(`PRs (50 of 50 PRs x 50 checks expanded): ${base.length} rows, tick ${tick} ms`);
  if (base.length !== 2550 || Number(tick) >= 15) throw new Error(`PR bench failed: ${base.length} rows, ${tick} ms`);
}
const base = m.rows(repos(5000), expanded, {}, '', now);
for (const [name, next] of [['unchanged', base.slice()], ['one removed', removed(base)], ['one moved to top', toTop(base)]]) {
  const x = fresh(base); ops = 0; m.syncRows(x, next);
  console.log(`Model operations at ${base.length} rows, ${name}: ${ops}`);
}
