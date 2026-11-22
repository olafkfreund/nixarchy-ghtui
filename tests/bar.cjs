const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = {};
vm.createContext(model);
vm.runInContext(fs.readFileSync('bar-widget/BarModel.js', 'utf8'), model);
const plain = value => JSON.parse(JSON.stringify(value));
const now = new Date(2026, 0, 2, 12, 30).getTime();
const stamp = new Date(2026, 0, 2, 11, 5).getTime();
const clock = value => `${String(new Date(value).getHours()).padStart(2, '0')}:${String(new Date(value).getMinutes()).padStart(2, '0')}`;
const base = {version:1,state:'ok',account:'octocat',running:2,failed:1,countsAt:stamp,cooldownUntil:0,reason:''};
const view = (changes={}, time=now, vertical=false) => plain(model.view(JSON.stringify({...base,...changes}), time, vertical));
const glyph = '\uF09B';
const none = {state:'none',label:glyph,tooltip:'Open GitHub Actions to load',
  accessible:'Open GitHub Actions to load',active:false,dimmed:true,recheckAt:0};
for (const text of ['', '{bad', 'null', '[]', '"text"', JSON.stringify({...base,version:0}), JSON.stringify({...base,state:'unknown'})])
  assert.deepEqual(plain(model.view(text, now, false)), none);
assert.deepEqual(view({state:'none'}), none);
assert.deepEqual(view(), {state:'ok',label:`${glyph} ●2 ✕1`,
  tooltip:`GitHub Actions · octocat\n2 running workflow runs, 1 failing repository\nLast repository activity read at ${clock(stamp)}; watched runs are checked every 30 s, slower when the quota is low`,
  accessible:`GitHub Actions · octocat, 2 running workflow runs, 1 failing repository, Last repository activity read at ${clock(stamp)}; watched runs are checked every 30 s, slower when the quota is low`,
  active:true,dimmed:false,recheckAt:0});
assert.equal(view({},now,true).label,`${glyph}\n●2\n✕1`);
assert.equal(view({running:0,failed:0}).label,glyph);
assert.equal(view({running:0,failed:0}).active,false);
assert.equal(view({running:1,failed:2}).tooltip.includes('1 running workflow run, 2 failing repositories'),true);
assert.equal(view({running:-3.7,failed:'4.9',account:''}).label,`${glyph} ✕4`);
assert.equal(view({running:-3.7,failed:'4.9',account:''}).tooltip.startsWith('GitHub Actions\n'),true);
assert.equal(view({account:42}).tooltip.startsWith('GitHub Actions\n'),true);
assert.equal(view({account:'a'.repeat(105)}).tooltip.startsWith(`GitHub Actions · ${'a'.repeat(100)}\n`),true);
assert.equal(view({running:Infinity,failed:'bad'}).label,glyph);
assert.equal(view({countsAt:0}).tooltip.includes('Last repository activity read at'),false);
assert.equal(view({countsAt:0}).tooltip.includes(':'),false);
const reason='x'.repeat(125);
assert.equal(view({state:'stopped',reason}).label,`${glyph} !`);
assert.equal(view({state:'stopped',reason}).tooltip,`GitHub Actions stopped: ${'x'.repeat(120)}. Open the panel to fix it.`);
assert.equal(view({state:'stopped',reason:''}).tooltip,'GitHub Actions stopped. Open the panel to fix it.');
assert.equal(view({state:'stopped',reason:{message:'bad'}}).tooltip,'GitHub Actions stopped. Open the panel to fix it.');
assert.equal(view({state:'stopped',failed:0}).active,true);
assert.equal(view({state:'stopped',failed:0}).dimmed,false);
const until=now+60000;
const rate=view({state:'rate',cooldownUntil:until});
assert.equal(rate.label,`${glyph} ●2 ✕1`);
assert.equal(rate.tooltip.startsWith(`GitHub paused until ${clock(until)}\nGitHub Actions · octocat`),true);
assert.equal(rate.active,true);
assert.equal(rate.dimmed,true);
assert.equal(rate.recheckAt,until);
assert.equal(view({state:'rate',cooldownUntil:until,failed:0}).active,false);
assert.equal(view({state:'rate',cooldownUntil:until,failed:0}).dimmed,true);
assert.equal(view({state:'rate',cooldownUntil:until,countsAt:0}).tooltip,`GitHub paused until ${clock(until)}`);
assert.equal(view({state:'rate',cooldownUntil:until},until).state,'ok');
assert.deepEqual(view({state:'rate',cooldownUntil:until,countsAt:0},until),none);
console.log('Bar: view states, clamping, vertical and rate expiry passed');
