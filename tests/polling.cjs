const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
// Baseline 0.2.2 / 91f6bde: activity waits 2s after each 1s response;
// selected summaries issue six sequential pages, then wait 30s. No inspected job.
function baseline(duration = 1800000) {
  let requests = 2; // catalogue pages
  for (let start = 2000; start < duration; start += 3000) requests++;
  for (let start = 0; start < duration; start += 36000)
    for (let page = 0; page < 6; page++) if (start + page * 1000 < duration) requests++;
  return {requests, coldScanMs: 2000 + 136 * 3000 + 1000};
}
assert.deepEqual(baseline(), {requests:902, coldScanMs:411000});
console.log('Baseline (137 repos, 1s responses, 30min idle):', baseline());
if (!fs.existsSync('Polling.js')) process.exit(0);
const polling = {};
vm.createContext(polling);
vm.runInContext(fs.readFileSync('Polling.js', 'utf8'), polling);
function response(request, data=[], nextPage=0, total) {
  const reply={requestId:request.requestId,data,nextPage,error:'',errorType:'',remaining:4000};
  if (total!==undefined) reply.total=total;
  return reply;
}
function reopen(s, now) { polling.open(s, now); s.accountChecked = true; }
// An auth or setup error on the account check stops polling until r, then r recovers.
for (const errorType of ['auth','setup']) {
  const gate=polling.create(); polling.open(gate,0);
  const first=polling.next(gate,0); assert.equal(first.kind,'account');
  polling.complete(gate,{requestId:first.requestId,error:'stop',errorType},100);
  assert.equal(gate.accountChecked,false); assert.equal(polling.next(gate,5000),null,errorType+' stops the gate');
  polling.manual(gate,6000,false);
  const retry=polling.next(gate,6000); assert.equal(retry.kind,'account',errorType+': r retries the check');
  polling.complete(gate,response(retry,{login:'tester'}),6100);
  assert.equal(gate.accountChecked,true); assert.equal(polling.next(gate,7100).kind,'catalogue',errorType+': polling resumes');
}
// The account check gates all cached work on each open.
const account=polling.create();
account.repos=[{repo:'a/b',runs:[{id:7,status:'in_progress'}]}];
account.details={'a/b:7':{jobs:[]}}; account.expanded={'a/b:7':true};
account.selected='a/b'; account.inspected='7'; account.catalogueComplete=true;
polling.ensure(account,'catalogue','','','background',0);
polling.ensure(account,'summary','a/b','','interactive',0);
polling.open(account,0);
let accountReq=polling.next(account,0);
assert.equal(accountReq.kind,'account');
assert.equal(polling.next(account,1000),null,'in-flight account check blocks other work');
assert.equal(polling.complete(account,response(accountReq,{login:'tester'}),100),true);
assert.equal(account.account,'tester'); assert.equal(account.accountChecked,true);
assert.equal(account.repos.length,1); assert.ok(account.details['a/b:7']);
assert.equal(polling.next(account,1000).kind,'summary','cached work resumes after first check');
polling.close(account); polling.open(account,2000);
accountReq=polling.next(account,2000); assert.equal(accountReq.kind,'account');
polling.complete(account,response(accountReq,{login:'tester'}),2100);
assert.equal(account.repos.length,1); assert.equal(account.selected,'a/b');
assert.ok(account.details['a/b:7']); assert.equal(account.expanded['a/b:7'],true);
assert.equal(account.inspected,'7'); assert.equal(account.catalogueComplete,true);
polling.close(account); polling.open(account,3000);
polling.ensure(account,'activity','a/b','','active',3000);
polling.ensure(account,'run','a/b','7','active',3000);
account.catalogueBlocked='permission'; account.discover=false;
accountReq=polling.next(account,3000); assert.equal(accountReq.kind,'account');
polling.complete(account,response(accountReq,{login:'other'}),3100);
assert.equal(account.account,'other'); assert.equal(account.accountChecked,true);
assert.equal(account.repos.length,0); assert.equal(Object.keys(account.details).length,0); assert.equal(Object.keys(account.expanded).length,0);
assert.equal(account.selected,''); assert.equal(account.inspected,'');
assert.equal(account.catalogueComplete,false); assert.equal(account.catalogueBlocked,'');
assert.equal(account.discover,true); assert.equal(Object.keys(account.tasks).length,0);

const uncertain=polling.create(); uncertain.account='tester'; uncertain.repos=[{repo:'a/b'}];
polling.open(uncertain,0);
let uncertainReq=polling.next(uncertain,0);
polling.complete(uncertain,{...response(uncertainReq),error:'offline',errorType:'network'},100);
assert.equal(uncertain.accountChecked,false);
assert.ok(uncertain.tasks[polling.key('account')].due>100);
assert.equal(polling.next(uncertain,1000),null);
polling.manual(uncertain,1000,false);
assert.equal(uncertain.tasks[polling.key('account')].due,1000);
uncertain.cooldown=2000; assert.equal(polling.next(uncertain,1000),null);
uncertain.cooldown=0; uncertainReq=polling.next(uncertain,1000); assert.equal(uncertainReq.kind,'account');
polling.complete(uncertain,{...response(uncertainReq),error:'forbidden',errorType:'permission'},1100);
assert.equal(uncertain.accountChecked,true); assert.equal(uncertain.error,'');
assert.equal(uncertain.account,'tester'); assert.equal(uncertain.repos.length,1);
assert.equal(polling.next(uncertain,2000).kind,'catalogue');

const forbidden=polling.create(); polling.open(forbidden,0);
let forbiddenReq=polling.next(forbidden,0);
polling.complete(forbidden,{...response(forbiddenReq),error:'forbidden',errorType:'permission'},100);
assert.equal(forbidden.accountChecked,true); assert.equal(forbidden.error,'');

for (const data of [[],null]) {
  const bad=polling.create(); polling.open(bad,0);
  const check=polling.next(bad,0); assert.equal(check.kind,'account');
  polling.complete(bad,response(check,data),100);
  assert.equal(bad.error,'Workflow helper returned invalid data'); assert.equal(bad.auth,true);
}
const staleAccount=polling.create(); polling.open(staleAccount,0);
const staleReq=polling.next(staleAccount,0);
polling.close(staleAccount); polling.open(staleAccount,1000);
const currentReq=polling.next(staleAccount,1000); assert.equal(currentReq.kind,'account');
assert.equal(polling.complete(staleAccount,response(staleReq,{login:'tester'}),1000),false);
assert.equal(staleAccount.accountChecked,false);
assert.equal(staleAccount.flight.request.requestId,currentReq.requestId);
function simulation(activeCount=0, duration=1800000, pageBuilder) {
  const s=polling.create(), repos=Array.from({length:137},(_,i)=>({repo:`org/r${i}`}));
  reopen(s,0); polling.select(s,'org/r0',activeCount ? '1' : '',activeCount ? {'org/r0:1':true} : {},0,false);
  let flight=null, cold=null, summary=null, catalogue=null;
  const history=[], ages={jobs:0,selected:0,active:0};
  function run(i) { return {id:i+1,status:'in_progress',run_attempt:1,name:'CI'}; }
  for(let now=0; now<duration; now+=250) {
    if(flight && now>=flight.end) {
      const req=flight.req; let data=[],next=0;
      const i=Number(req.repo.split('r').pop());
      if(req.kind==='catalogue') { data=req.page===1?repos.slice(0,100):repos.slice(100); next=req.page===1?2:0; }
      else if(req.kind==='activity' && pageBuilder) data=pageBuilder(req,i,activeCount);
      else if(req.kind==='activity' || req.kind==='summary' && ['recent','in_progress'].includes(req.status)) data=i<activeCount?[run(i)]:[];
      else if(req.kind==='jobs') data=[{id:1,status:'in_progress',steps:[]}];
      polling.complete(s,response(req,data,next),now); flight=null;
      if(!catalogue && s.catalogueComplete) catalogue=now;
      if(!cold && s.repos.length===137 && s.repos.every(r=>r.activityAt!==undefined)) cold=now;
      if(!summary && s.repos[0]?.summaryAt!==undefined) summary=now;
    }
    if(now>60000 && activeCount) {
      const r=s.repos.find(r=>r.repo==='org/r0'), d=s.details['org/r0:1'];
      if(d) ages.jobs=Math.max(ages.jobs,now-d.jobsAt);
      if(r?.activityAt!==undefined) ages.selected=Math.max(ages.selected,now-r.activityAt);
      for(const r of s.repos.slice(1,activeCount)) if(r.activityAt!==undefined) ages.active=Math.max(ages.active,now-r.activityAt);
    }
    const req=polling.next(s,now);
    if(req) { assert.equal(flight,null); history.push({at:now,...req,group:s.tasks[s.flight.key].group}); flight={req,end:now+1000}; }
  }
  for(let i=0;i<history.length;i++) {
    if(i) assert.ok(history[i].at-history[i-1].at>=1000);
    if(i>=60) assert.ok(history[i].at-history[i-60].at>=60000);
  }
  return {s,history,cold,summary,catalogue,ages};
}
const idle=simulation();
assert.ok(idle.history.length<baseline().requests, `${idle.history.length} idle requests must beat baseline`);
assert.ok(idle.cold<baseline().coldScanMs);
const busy=simulation(4,180000);
assert.ok(busy.catalogue<=20000,`catalogue ${busy.catalogue}`);
assert.ok(busy.summary<=20000,`summary ${busy.summary}`);
assert.ok(busy.ages.jobs<=10000,`jobs age ${busy.ages.jobs}`);
assert.ok(busy.ages.selected<=15000,`selected age ${busy.ages.selected}`);
assert.ok(busy.ages.active<=25000,`active age ${busy.ages.active}`);
console.log('Candidate:', {idleRequests:idle.history.length,coldScanMs:idle.cold,summaryMs:busy.summary,warmAges:busy.ages});

// Continuous work in all classes, including page continuations, cannot starve either reserved class.
const fair=polling.create(); reopen(fair,0); fair.discover=false; fair.catalogueComplete=true;
for(const [group,kind] of [['interactive','jobs'],['active','run'],['background','catalogue']])
  polling.ensure(fair,kind,'a/b','1',group,0);
fair.selected='a/b'; fair.inspected='1'; fair.expanded={'a/b:1':true};
const served=[];
for(let now=0;now<20000;now+=1000) {
  const req=polling.next(fair,now); assert.ok(req);
  const task=fair.tasks[fair.flight.key]; served.push(task.group);
  // Keep all three tasks due without requiring resource fixtures.
  fair.flight=null; task.page++; task.due=now; task.order=++fair.order;
}
for(let i=0;i<served.length;i+=5) assert.deepEqual(served.slice(i,i+5),['interactive','interactive','interactive','active','background']);

const limited=polling.create(); reopen(limited,0);
let req=polling.next(limited,0);
polling.complete(limited,{...response(req),errorType:'rate',error:'rate',retryAt:90000,remaining:0,resetAt:120000},1000);
assert.equal(limited.cooldown,120000);
polling.manual(limited,2000,true); assert.equal(polling.next(limited,119999),null);
polling.close(limited); reopen(limited,4000); assert.equal(polling.next(limited,119999),null);
req=polling.next(limited,120000); assert.ok(req);
polling.complete(limited,{...response(req),errorType:'rate',error:'rate'},121000);
assert.equal(limited.cooldown,241000); // second secondary-limit fallback doubles
const old=req; polling.close(limited); reopen(limited,250000);
req=polling.next(limited,250000); assert.ok(req);
assert.equal(polling.complete(limited,response(old),251000),false);
assert.equal(limited.flight.request.requestId,req.requestId);
polling.complete(limited,{...response(req),remaining:0,resetAt:300000},251000);
assert.equal(limited.catalogueComplete,true); assert.equal(polling.next(limited,299999),null);

// Debounce, same-run navigation, completion reconciliation, final cache and rerun invalidation.
const s=polling.create(); s.repos=[{repo:'a/b',runs:[{id:7,status:'in_progress',run_attempt:1}],activityAt:0,summaryAt:0,active:1}];
s.catalogueComplete=true; s.discover=false; reopen(s,0);
polling.select(s,'a/b','7',{'a/b:7':true},0,false);
assert.equal(polling.next(s,200),null);
req=polling.next(s,250); assert.equal(req.kind,'jobs');
polling.complete(s,response(req,[{id:1,status:'in_progress'}]),500);
polling.select(s,'a/b','7',{'a/b:7':true},4500,false);
req=polling.next(s,5500); assert.equal(req.kind,'jobs');
polling.complete(s,response(req,[{id:1,status:'in_progress'}]),5600);
polling.activity(s,s.repos[0],[],6000);
assert.equal(s.repos[0].active,0); assert.equal(s.repos[0].runs[0].awaitingFinal,true);
req=polling.next(s,6500); assert.equal(req.kind,'run');
polling.complete(s,response(req,{id:7,status:'completed',conclusion:'success',run_attempt:1}),6600);
req=polling.next(s,7500); assert.equal(req.kind,'jobs');
polling.complete(s,response(req,[{id:1,status:'completed'}]),7600);
assert.equal(s.details['a/b:7'].finalAttempt,1);
assert.equal(polling.next(s,13000),null);
assert.equal(polling.next(s,16000)?.kind,'activity');
polling.mergeRuns(s,s.repos[0],[{id:7,status:'in_progress',run_attempt:2}]);
assert.equal(s.details['a/b:7'],undefined);
console.log('Polling: fairness, budgets, cooldown, debounce, lifecycle, completion and rerun checks passed');
const partial=polling.create(); reopen(partial,0); partial.discover=false; partial.catalogueComplete=true;
partial.repos=[{repo:'a/b',summaryAt:0,runs:[{id:7,status:'in_progress'}]}, {repo:'other/repo',summaryAt:0}];
polling.select(partial,'a/b','',{},0,true);
req=polling.next(partial,0); assert.equal(req.kind,'activity');
polling.complete(partial,response(req,[],2),100);
assert.equal(partial.repos[0].checked,undefined);
assert.equal(partial.repos[0].runs[0].status,'in_progress');
req=polling.next(partial,1000);
polling.complete(partial,{...response(req),error:'offline',errorType:'network'},1100);
assert.equal(partial.repos[0].checked,undefined);
assert.equal(partial.repos[0].runs[0].awaitingFinal,undefined);
req=polling.next(partial,2000); assert.equal(req.repo,'other/repo','one failed repository does not freeze background work');
polling.complete(partial,response(req),2100);
assert.equal(polling.next(partial,6000),null);
req=polling.next(partial,6100); assert.equal(req.page,1,'retry starts a fresh complete snapshot');
polling.complete(partial,{...response(req),error:'permission',errorType:'permission'},6200);
assert.equal(partial.repos[0].blocked,true);
assert.equal(polling.next(partial,15000),null);
polling.manual(partial,15000,false); assert.equal(partial.repos[0].blocked,false);
req=polling.next(partial,15000); assert.equal(req.kind,'summary');
polling.complete(partial,{...response(req),error:'login',errorType:'auth'},15100);
assert.equal(polling.next(partial,40000),null);
polling.close(partial); reopen(partial,41000);
assert.equal(partial.auth,false);

const churn=polling.create(); reopen(churn,0); churn.discover=false; churn.catalogueComplete=true;
churn.repos=Array.from({length:20},(_,i)=>({repo:`x/r${i}`,activityAt:0}));
for(let now=0;now<1000;now+=50) {
  polling.select(churn,`x/r${now/50}`,'',{},now,false);
  assert.equal(polling.next(churn,now),null,'rapid navigation should not fetch intermediate repositories');
}
req=polling.next(churn,1250); assert.equal(req.repo,'x/r19');
assert.equal(req.kind,'summary');
const taskCount=Object.keys(churn.tasks).length;
for(let n=0;n<50;n++) polling.manual(churn,1300,false);
assert.equal(Object.keys(churn.tasks).length,taskCount,'manual refresh coalesces work');
polling.select(churn,'x/r0','',{},1400,false);
polling.complete(churn,response(req,[{id:1,status:'completed'}]),1500);
req=polling.next(churn,2250); assert.equal(req.repo,'x/r0','obsolete summary continuation loses priority');
assert.equal(Object.values(churn.tasks).some(t=>t.repo==='x/r19'),false);
console.log('Polling: partial snapshots, permission isolation, auth retry and rapid navigation passed');

const overload=simulation(30,300000);
assert.ok(overload.ages.active>25000,'overload stretches freshness rather than bypassing the budget');
assert.ok(overload.history.filter(x=>x.group==='background').length>=Math.floor(overload.history.length/5));
const ordered=polling.create(); reopen(ordered,0); ordered.discover=false; ordered.catalogueComplete=true;
ordered.repos=[{repo:'newer/check',activityAt:1000},{repo:'oldest/check',activityAt:0}];
req=polling.next(ordered,700000); assert.equal(req.repo,'oldest/check','idle background checks oldest data first');
console.log('Polling: overload preserves budget/fairness; idle data ordered by freshness');

const overlap=polling.create(); reopen(overlap,0); overlap.discover=false; overlap.catalogueComplete=true;
overlap.repos=[{repo:'a/b',summaryAt:0,active:1}]; polling.select(overlap,'a/b','',{},0,true);
req=polling.next(overlap,0); polling.complete(overlap,response(req,[{id:7,status:'in_progress'}],2),100);
assert.equal(overlap.repos[0].checked,undefined);
req=polling.next(overlap,1000); polling.complete(overlap,response(req,[{id:7,status:'in_progress'}]),1100);
assert.equal(overlap.repos[0].active,1,'overlapping pages cannot double-count active workflows');
assert.equal(overlap.repos[0].runs.length,1,'overlapping pages keep one copy of each run');
console.log('Polling: overlapping pages deduplicate workflow IDs');

// Setup errors and malformed data stop polling until a manual refresh; stale ones are ignored.
function flight(kind) {
  const f=polling.create(); reopen(f,0); f.discover=false; f.catalogueComplete=true;
  f.repos=[{repo:'a/b',runs:[{id:7,status:'in_progress',run_attempt:1}]}]; f.selected='a/b';
  polling.ensure(f,kind,kind==='catalogue' ? '' : 'a/b',kind==='run' ? '7' : '','interactive',0);
  const r=polling.next(f,0); assert.equal(r.kind,kind); return {f,r};
}
let {f:setup,r:setupReq}=flight('catalogue');
assert.equal(polling.complete(setup,{...response(setupReq),error:'python3 not found',errorType:'setup'},1000),true);
assert.equal(setup.error,'python3 not found');
assert.equal(polling.next(setup,100000),null,'setup error stops polling');
polling.manual(setup,100000,false); assert.ok(polling.next(setup,100000),'manual refresh resumes');
for(const kind of ['catalogue','summary']) for(const data of [null,{},[null]]) {
  const {f,r}=flight(kind);
  assert.equal(polling.complete(f,response(r,data),1000),true);
  assert.equal(f.error,'Workflow helper returned invalid data');
  assert.equal(f.auth,true);
}
let {f:runOk,r:runReq}=flight('run');
polling.complete(runOk,response(runReq,{id:7,status:'completed',run_attempt:1}),1000);
assert.equal(runOk.error,''); assert.equal(polling.runFor(runOk,'a/b',7).status,'completed');
({f:runOk,r:runReq}=flight('run'));
polling.complete(runOk,response(runReq,[]),1000);
assert.equal(runOk.error,'Workflow helper returned invalid data'); assert.equal(runOk.auth,true);
({f:setup,r:setupReq}=flight('catalogue'));
assert.equal(polling.complete(setup,{...response(setupReq),requestId:setupReq.requestId+1,error:'x',errorType:'setup'},1000),false);
assert.equal(polling.complete(setup,{...response(setupReq,null),requestId:setupReq.requestId+1},1000),false);
polling.close(setup); reopen(setup,2000);
assert.equal(polling.complete(setup,{...response(setupReq),error:'x',errorType:'setup'},2000),false);
assert.equal(setup.auth,false,'stale setup or malformed replies change nothing');
console.log('Polling: setup errors and malformed data stop until manual refresh');

// #30: one page per unfinished status; the rest is counted, never fetched.
function selectedRepo(runs=[]) {
  const c=polling.create(); reopen(c,0); c.discover=false; c.catalogueComplete=true;
  c.repos=[{repo:'a/b',runs}]; return c;
}
const queued=Array.from({length:100},(_,i)=>({id:1000+i,status:'queued'}));
const big=selectedRepo([{id:5,status:'queued'}]);
polling.select(big,'a/b','5',{},0,true);
let starts=0, clock=0;
for (const phase of ['recent','in_progress','queued','waiting','pending','requested']) {
  req=polling.next(big,clock); starts++;
  assert.equal(req.kind,'summary'); assert.equal(req.status,phase); assert.equal(req.page,1);
  assert.equal((big.repos[0].hidden || {}).queued,undefined,'hidden counts wait for the whole snapshot');
  polling.complete(big,response(req,phase==='queued' ? queued : [],0,phase==='recent' ? undefined : phase==='queued' ? 2000 : 0),clock+100);
  clock+=1000;
}
assert.equal(starts,6);
assert.equal(big.repos[0].hidden.queued,1900);
assert.ok(polling.runFor(big,'a/b',5),'the inspected run survives a snapshot that did not return it');
assert.equal(big.repos[0].runs.filter(r=>r.status==='queued').length,101);

const act=selectedRepo([]);
polling.ensure(act,'activity','a/b','','active',0); req=polling.next(act,0);
assert.equal(req.kind,'activity');
polling.complete(act,response(req,Array.from({length:100},(_,i)=>({id:i+1,status:'in_progress'})),0,250),100);
assert.equal(act.repos[0].active,250); assert.equal(Object.keys(act.repos[0].hidden).length,0);
assert.equal(act.requests,1);

const full=selectedRepo([]);
polling.ensure(full,'activity','a/b','','active',0); req=polling.next(full,0);
assert.doesNotThrow(()=>polling.complete(full,response(req,Array.from({length:30},(_,i)=>({id:i+1,status:'completed'}))),100));
assert.equal(full.repos[0].runs.filter(r=>r.status==='completed').length,10);

function missingFromActivity(status, count) {
  const p=selectedRepo([{id:1,status}]);
  polling.ensure(p,'activity','a/b','','active',0);
  const request=polling.next(p,0);
  const page=Array.from({length:count},(_,i)=>({id:i+2,status:'completed'}));
  polling.complete(p,response(request,page),100);
  return p;
}
for (const status of ['queued','in_progress']) {
  const p=missingFromActivity(status,30);
  assert.equal(polling.runFor(p,'a/b',1),undefined,`${status} missing from a full page is dropped`);
  assert.equal(Object.values(p.tasks).some(t=>t.kind==='run'),false);
}
const shortPage=missingFromActivity('queued',1);
assert.equal(polling.runFor(shortPage,'a/b',1).awaitingFinal,true);
const completedOnPage=selectedRepo([{id:1,status:'in_progress'}]);
polling.ensure(completedOnPage,'activity','a/b','','active',0); req=polling.next(completedOnPage,0);
polling.complete(completedOnPage,response(req,[{id:1,status:'completed'}]),100);
assert.equal(Object.values(completedOnPage.tasks).some(t=>t.kind==='run'),false);
const filtered=selectedRepo([{id:1,status:'queued'}]);
polling.activity(filtered,filtered.repos[0],[],100,0,false);
assert.equal(polling.runFor(filtered,'a/b',1).status,'queued');
assert.equal(polling.runFor(filtered,'a/b',1).awaitingFinal,undefined);

const idleFull=simulation(0,1800000,()=>Array.from({length:30},(_,i)=>({id:i+1,status:'completed'})));
assert.equal(idleFull.history.length,idle.history.length,'full idle pages cost the same as empty pages');
const pageVisits={};
const mixedPage=(_,i,activeCount)=>{
  if (i===0) return [{id:1,status:'in_progress',run_attempt:1,name:'CI'}];
  if (i>=activeCount) return [];
  const offset=100*(pageVisits[i] || 0);
  pageVisits[i]=(pageVisits[i] || 0)+1;
  return Array.from({length:30},(_,n)=>({id:n+1+offset,
    status:n===29?'queued':n<19?'in_progress':'completed'}));
};
const mixed=simulation(4,180000,mixedPage);
assert.equal(mixed.history.filter(h=>h.kind==='run').length,0,'full mixed pages need no lookups');
assert.equal(mixed.history.length,busy.history.length,'mixed running pages keep the same request count');

function partialActivity(total) {
  const p=selectedRepo([1,2,3].map(id=>({id,status:'in_progress'})));
  polling.select(p,'a/b','2',{'a/b:1':true},0,true);
  polling.activity(p,p.repos[0],[{id:4,status:'in_progress'}],1000,total);
  return id=>polling.runFor(p,'a/b',id);
}
let run=partialActivity(50);
assert.equal(run(1).awaitingFinal,true,'expanded run is looked up');
assert.equal(run(2).awaitingFinal,true,'inspected run is looked up');
assert.equal(run(3),undefined,'a plain run past the first page is counted, not looked up');
run=partialActivity(1);
assert.deepEqual([1,2,3].map(id=>run(id).awaitingFinal),[true,true,true],'a complete page keeps today\'s behaviour');

const keep=selectedRepo(Array.from({length:12},(_,i)=>({id:i+1,status:'completed'})));
polling.select(keep,'a/b','1',{},0,true);
polling.mergeRuns(keep,keep.repos[0],[]);
assert.ok(polling.runFor(keep,'a/b',1),'recent() keeps the inspected run past the ten completed');
assert.equal(keep.repos[0].runs.length,11);

const plain=selectedRepo([]);
polling.ensure(plain,'activity','a/b','','active',0); req=polling.next(plain,0);
polling.complete(plain,response(req,[{id:1,status:'in_progress'}]),100);
assert.equal(Object.keys(plain.repos[0].hidden || {}).length,0); assert.equal(plain.repos[0].active,1);
const summaryCounts=selectedRepo(Array.from({length:100},(_,i)=>({id:i+1,status:'in_progress'}))
  .concat(Array.from({length:40},(_,i)=>({id:i+101,status:'queued'}))));
summaryCounts.repos[0].summaryAt=100; summaryCounts.repos[0].active=250;
summaryCounts.repos[0].hidden={in_progress:150,queued:0};
const queuedPage=Array.from({length:30},(_,i)=>({id:i+300,status:'queued'}));
polling.select(summaryCounts,'a/b','',{'repo:a/b':true},0,true);
polling.activity(summaryCounts,summaryCounts.repos[0],queuedPage,10000,undefined,true);
assert.equal(summaryCounts.repos[0].active,250,'selected summary running total survives activity');
assert.deepEqual({...summaryCounts.repos[0].hidden},{in_progress:150,queued:0});
assert.equal(summaryCounts.repos[0].runs.length,170,'selected activity does not drop held runs');
assert.ok(polling.runFor(summaryCounts,'a/b',1));
polling.select(summaryCounts,'other/repo','',{},11000,true);
polling.activity(summaryCounts,summaryCounts.repos[0],queuedPage,20000,undefined,true);
assert.equal(summaryCounts.repos[0].active,0,'non-selected activity uses its page count');
assert.equal(Object.keys(summaryCounts.repos[0].hidden).length,0,'non-selected activity clears stale summary counts');
assert.equal(summaryCounts.repos[0].runs.length,30,'non-selected activity drops missing unfinished runs');
console.log('Polling: one page per unfinished status, hidden counts and kept runs');

// The latest completed default-branch run is the repository's last result.
function result(id, branch='main', conclusion='success', updated_at='2026-01-01T00:00:00Z') {
  return {id,status:'completed',head_branch:branch,conclusion,updated_at,html_url:`https://github.com/a/b/actions/runs/${id}`};
}
const health=selectedRepo([]); health.repos[0].default_branch='main';
polling.activity(health,health.repos[0],[result(4),result(9,'feature'),result(7,'main','cancelled'),
  {id:10,status:'queued',head_branch:'main'}, {id:11,status:'in_progress',head_branch:'main'}],100,undefined,true);
assert.equal(health.repos[0].last.id,7);
assert.equal(health.repos[0].last.conclusion,'cancelled');
assert.equal(health.repos[0].last.branch,'main');
assert.equal(health.repos[0].last.url,'https://github.com/a/b/actions/runs/7');
assert.equal(health.repos[0].last.confirmedAt,100);
polling.activity(health,health.repos[0],[result(15,'feature')],200,undefined,true);
assert.equal(health.repos[0].last.id,7,'a page without a default-branch result keeps the old result');
polling.activity(health,health.repos[0],[result(3)],300,undefined,true);
assert.equal(health.repos[0].last.id,7,'an older id never replaces a newer result');
polling.activity(health,health.repos[0],[result(7,'main','failure','2026-01-02T00:00:00Z')],400,undefined,true);
assert.equal(health.repos[0].last.conclusion,'failure','a rerun can change the same id');
polling.activity(health,health.repos[0],[result(7,'main','success','2025-12-31T00:00:00Z')],500,undefined,true);
assert.equal(health.repos[0].last.conclusion,'failure','an older update cannot undo a rerun');

const stale=selectedRepo([]); stale.repos[0].default_branch='main';
stale.repos[0].last={id:5,branch:'main',conclusion:'failure',confirmedAt:10};
const featurePage=Array.from({length:30},(_,i)=>result(i+6,'feature'));
for (const now of [100,200]) {
  polling.activity(stale,stale.repos[0],featurePage,now,undefined,true);
  assert.equal(stale.repos[0].last.confirmedAt,10,'full newer feature pages do not confirm the result');
  assert.equal(stale.repos[0].activityAt,now);
}
polling.activity(stale,stale.repos[0],[...featurePage.slice(0,29),result(5,'feature')],300,undefined,true);
assert.equal(stale.repos[0].last.confirmedAt,300,'a page reaching the last id confirms it');
polling.activity(stale,stale.repos[0],featurePage.slice(0,29),400,undefined,true);
assert.equal(stale.repos[0].last.confirmedAt,400,'a short page confirms it');
polling.activity(stale,stale.repos[0],[...featurePage.slice(0,29),result(40)],500,undefined,true);
assert.equal(stale.repos[0].last.id,40);
assert.equal(stale.repos[0].last.confirmedAt,500,'a qualifying result confirms it');

const retained=selectedRepo([]); retained.repos[0].default_branch='main';
polling.activity(retained,retained.repos[0],[result(1),...Array.from({length:10},(_,i)=>result(i+2,'feature'))],100,undefined,true);
assert.ok(polling.runFor(retained,'a/b',1),'last result survives the ten newer completed runs');
assert.equal(retained.repos[0].runs.length,11);
const noBranch=selectedRepo([]);
polling.activity(noBranch,noBranch.repos[0],[result(1)],100,undefined,true);
assert.equal(noBranch.repos[0].last,undefined,'an empty default branch has no result');

const catalogueLast=polling.create(); reopen(catalogueLast,0);
catalogueLast.repos=[{repo:'a/b',default_branch:'main',last:{id:1,branch:'main'}}];
req=polling.next(catalogueLast,0); assert.equal(req.kind,'catalogue');
polling.complete(catalogueLast,response(req,[{repo:'a/b',default_branch:'develop'}]),100);
assert.equal(catalogueLast.repos[0].last,undefined,'catalogue refresh clears a changed default branch immediately');

const lookedUp=selectedRepo([{id:7,status:'queued',head_branch:'main'}]);
lookedUp.repos[0].default_branch='main';
for (const conclusion of ['failure','success']) {
  polling.ensure(lookedUp,'run','a/b',7,'interactive',0);
  req=polling.next(lookedUp,conclusion==='failure'?0:1000); assert.equal(req.kind,'run');
  polling.complete(lookedUp,response(req,result(7,'main',conclusion,conclusion==='failure'?'2026-01-01T00:00:00Z':'2026-01-02T00:00:00Z')),conclusion==='failure'?100:1100);
  assert.equal(lookedUp.repos[0].last.conclusion,conclusion,'single-run lookup updates the result');
}
lookedUp.repos[0].last.confirmedAt=1100;
polling.ensure(lookedUp,'run','a/b',6,'interactive',2000);
req=polling.next(lookedUp,2000); assert.equal(req.kind,'run');
polling.complete(lookedUp,response(req,result(6,'main','failure')),2100);
assert.equal(lookedUp.repos[0].last.id,7);
assert.equal(lookedUp.repos[0].last.confirmedAt,1100,'older lookup does not confirm newest result');

const summaryLast=selectedRepo([]); summaryLast.repos[0].default_branch='main';
summaryLast.repos[0].last={id:0,branch:'main',conclusion:'failure',confirmedAt:5};
polling.select(summaryLast,'a/b','',{},0,true);
let summaryNow=0;
for (const phase of polling.phases) {
  req=polling.next(summaryLast,summaryNow); assert.equal(req.status,phase);
  const data=phase==='recent' ? [result(1),...Array.from({length:10},(_,i)=>result(i+2,'feature'))]
    : phase==='in_progress' ? [{id:30,status:'in_progress',head_branch:'main'}] : [];
  polling.complete(summaryLast,response(req,data,0,phase==='in_progress'?1:undefined),summaryNow+100);
  if (phase==='in_progress') {
    assert.equal(summaryLast.repos[0].last.id,0,'filtered phase cannot set a result');
    assert.equal(summaryLast.repos[0].last.confirmedAt,5,'filtered phase cannot confirm a result');
  }
  summaryNow+=1000;
}
assert.equal(summaryLast.repos[0].last.id,1,'summary uses all runs');
assert.ok(polling.runFor(summaryLast,'a/b',1),'summary protects the last result before trimming');

// Catalogue permission stops discovery until a manual refresh or reopen.
function blockedCatalogue() {
  const c=polling.create(); reopen(c,0);
  c.repos=[{repo:'a/b',archived:true}];
  const request=polling.next(c,0); assert.equal(request.kind,'catalogue');
  polling.complete(c,{...response(request),error:'catalogue forbidden',errorType:'permission'},100);
  assert.equal(c.discover,false); assert.equal(c.catalogueBlocked,'catalogue forbidden');
  assert.equal(c.repos.length,1);
  for(let now=1000;now<=60000;now+=1000) assert.equal(polling.next(c,now),null);
  return c;
}
const blocked=blockedCatalogue();
polling.manual(blocked,61000,false);
assert.equal(blocked.catalogueBlocked,'');
assert.equal(polling.next(blocked,61000).kind,'catalogue');
const blockedAgain=blockedCatalogue();
polling.manual(blockedAgain,61000,true);
assert.equal(blockedAgain.catalogueBlocked,'');
assert.equal(polling.next(blockedAgain,61000).kind,'catalogue');
const reopened=blockedCatalogue();
reopened.catalogueComplete=true; reopened.catalogueAt=60000;
reopen(reopened,61000);
assert.equal(reopened.catalogueBlocked,'');
assert.equal(polling.next(reopened,61000).kind,'catalogue');
const selectedBlocked=blockedCatalogue();
selectedBlocked.repos[0].archived=false;
selectedBlocked.selected='a/b';
polling.manual(selectedBlocked,61000,false);
assert.equal(selectedBlocked.catalogueBlocked,'');
assert.ok(selectedBlocked.tasks[polling.key('summary','a/b')]);

// Manual refresh advances an existing retry without erasing its failure count.
for(const kind of ['summary','jobs']) {
  const retry=selectedRepo([{id:7,status:'in_progress'}]);
  polling.select(retry,'a/b',kind==='jobs' ? '7' : '',kind==='jobs' ? {'a/b:7':true} : {},0,true);
  retry.repos[0].summaryAt=0;
  const task=polling.ensure(retry,kind,'a/b',kind==='jobs' ? '7' : '','interactive',301000);
  task.failures=5;
  polling.manual(retry,1000,false);
  assert.equal(task.due,1000);
  assert.equal(task.failures,5);
  retry.cooldown=2000;
  assert.equal(polling.next(retry,1000),null);
  retry.cooldown=0;
  retry.starts=Array.from({length:60},()=>1000);
  assert.equal(polling.next(retry,1000),null);
  retry.starts=[];
  assert.equal(polling.next(retry,1000).kind,kind);
}
const stable=selectedRepo();
polling.select(stable,'a/b','',{},1000,false);
const stableAt=stable.stableAt;
polling.select(stable,'a/b','',{},2000,false);
assert.equal(stable.stableAt,stableAt);

// Failed jobs keep cached rows visible and clear their error on success.
function jobsFixture(cached) {
  const j=selectedRepo([{id:7,status:'in_progress'}]);
  j.repos[0].summaryAt=0; j.repos[0].activityAt=0;
  polling.select(j,'a/b','7',{'a/b:7':true},0,true);
  if (cached) j.details['a/b:7']={jobs:[{id:1,status:'in_progress'}],updated:'2026-01-01T00:00:00.000Z',jobsAt:0};
  polling.ensure(j,'jobs','a/b','7','interactive',0);
  return j;
}
const jobsCached=jobsFixture(true);
req=polling.next(jobsCached,0); assert.equal(req.kind,'jobs');
polling.complete(jobsCached,{...response(req),error:'offline',errorType:'network'},100);
assert.equal(jobsCached.details['a/b:7'].error,'offline');
assert.equal(jobsCached.details['a/b:7'].jobs.length,1);
assert.equal(jobsCached.details['a/b:7'].updated,'2026-01-01T00:00:00.000Z');
assert.equal(jobsCached.details['a/b:7'].jobsAt,0);
jobsCached.tasks[polling.key('jobs','a/b','7')].due=1000;
req=polling.next(jobsCached,1000); assert.equal(req.kind,'jobs');
polling.complete(jobsCached,response(req,[{id:2,status:'completed'}]),1100);
assert.equal(jobsCached.details['a/b:7'].error,undefined);
assert.equal(jobsCached.details['a/b:7'].jobs[0].id,2);
const jobsEmpty=jobsFixture(false);
req=polling.next(jobsEmpty,0); assert.equal(req.kind,'jobs');
polling.complete(jobsEmpty,{...response(req),error:'offline',errorType:'network'},100);
assert.equal(jobsEmpty.details['a/b:7'].error,'offline');
assert.equal(jobsEmpty.details['a/b:7'].jobs,undefined);
const jobsDenied=jobsFixture(true);
req=polling.next(jobsDenied,0); assert.equal(req.kind,'jobs');
polling.complete(jobsDenied,{...response(req),error:'forbidden',errorType:'permission'},100);
assert.equal(jobsDenied.details['a/b:7'].error,'forbidden');
assert.equal(jobsDenied.details['a/b:7'].unavailable,true);
assert.equal(jobsDenied.details['a/b:7'].jobsAt,100);
assert.equal(jobsDenied.details['a/b:7'].jobs.length,1);
assert.equal(polling.runFor(jobsDenied,'a/b',7).lookupError,undefined);

// A full snapshot looks up kept queued runs that vanished and drops stale details.
const snapshot=selectedRepo([5,6,7,8].map(id=>({id,status:'queued',followupAt:0})));
polling.select(snapshot,'a/b','6',{'a/b:5':true},0,true);
snapshot.details={'a/b:5':{unavailable:true},'a/b:6':{unavailable:true},'a/b:7':{jobs:[]},'a/b:8':{jobs:[]}};
let snapNow=0;
for (const phase of polling.phases) {
  req=polling.next(snapshot,snapNow); assert.equal(req.kind,'summary'); assert.equal(req.status,phase);
  polling.complete(snapshot,response(req,phase==='queued' ? [{id:8,status:'queued'}] : []),snapNow+100);
  snapNow+=1000;
}
for (const id of [5,6]) {
  assert.equal(polling.runFor(snapshot,'a/b',id).awaitingFinal,true);
  assert.equal(polling.runFor(snapshot,'a/b',id).followupAt,undefined);
  assert.ok(snapshot.details[`a/b:${id}`]);
}
assert.equal(polling.runFor(snapshot,'a/b',7),undefined);
assert.equal(snapshot.details['a/b:7'],undefined);
assert.equal(polling.runFor(snapshot,'a/b',8).awaitingFinal,undefined);
assert.ok(snapshot.details['a/b:8']);
req=polling.next(snapshot,snapNow); assert.equal(req.kind,'run');
polling.complete(snapshot,response(req,{id:Number(req.run),status:'completed'}),snapNow+100);
assert.equal(polling.runFor(snapshot,'a/b',req.run).status,'completed');

const activityPrune=selectedRepo(Array.from({length:12},(_,i)=>({id:i+1,status:'completed'})));
activityPrune.repos[0].repo='other/repo';
polling.select(activityPrune,'other/repo','1',{},0,true);
polling.select(activityPrune,'','',{},1000,true);
activityPrune.details={'other/repo:1':{jobs:[]},'other/repo:12':{jobs:[]}};
polling.activity(activityPrune,activityPrune.repos[0],[],1000,0);
assert.equal(activityPrune.details['other/repo:1'],undefined);
assert.ok(activityPrune.details['other/repo:12']);

const cataloguePrune=polling.create(); reopen(cataloguePrune,0);
cataloguePrune.repos=[{repo:'a/b',archived:true},{repo:'a/bc',archived:true}];
cataloguePrune.details={'a/b:5':{jobs:[]},'a/bc:5':{jobs:[]}};
req=polling.next(cataloguePrune,0); assert.equal(req.kind,'catalogue');
polling.complete(cataloguePrune,response(req,[{repo:'a/bc',archived:true}]),100);
assert.equal(cataloguePrune.details['a/b:5'],undefined);
assert.ok(cataloguePrune.details['a/bc:5']);

// Quota metadata paces background checks, while selected work keeps its normal interval.
const quotaReply=polling.create(); reopen(quotaReply,0);
req=polling.next(quotaReply,0); assert.equal(req.kind,'catalogue');
polling.complete(quotaReply,{...response(req),error:'offline',errorType:'network',remaining:400,resetAt:900000},100);
assert.equal(quotaReply.remaining,400); assert.equal(quotaReply.resetAt,900000);
quotaReply.tasks[polling.key('catalogue')].due=1000;
req=polling.next(quotaReply,1000);
polling.complete(quotaReply,{...response(req),remaining:null,resetAt:1000000},1100);
assert.equal(quotaReply.remaining,400); assert.equal(quotaReply.resetAt,900000);

function pacedRepo(remaining, active, activityAt=0) {
  const p=polling.create(); reopen(p,0); p.discover=false; p.catalogueComplete=true;
  p.remaining=remaining; p.resetAt=7000000;
  p.repos=[{repo:'a/b',active,activityAt}];
  return p;
}
const eased=pacedRepo(400,1);
assert.equal(polling.next(eased,20000),null);
req=polling.next(eased,45000); assert.equal(req.kind,'activity'); assert.equal(req.repo,'a/b');
const tight=pacedRepo(100,0);
assert.equal(polling.next(tight,5999999),null);
req=polling.next(tight,6000000); assert.equal(req.kind,'activity');
const ample=pacedRepo(5000,1);
req=polling.next(ample,15000); assert.equal(req.kind,'activity');
const reset=pacedRepo(100,1);
reset.resetAt=10000;
req=polling.next(reset,15000); assert.equal(req.kind,'activity');

const catalogueAge=polling.create(); reopen(catalogueAge,0);
catalogueAge.catalogueComplete=true; catalogueAge.catalogueAt=0; catalogueAge.discover=false;
catalogueAge.remaining=400; catalogueAge.resetAt=1200000;
reopen(catalogueAge,600000); assert.equal(catalogueAge.discover,false);
reopen(catalogueAge,900000); assert.equal(catalogueAge.discover,true);

const selectedPace=pacedRepo(100,1);
selectedPace.repos[0].summaryAt=0;
polling.select(selectedPace,'a/b','',{},0,true);
req=polling.next(selectedPace,10000); assert.equal(req.kind,'activity');
const summaryPace=pacedRepo(100,0);
summaryPace.repos[0].summaryAt=0;
polling.select(summaryPace,'a/b','',{},0,true);
req=polling.next(summaryPace,60000); assert.equal(req.kind,'summary');
const jobsPace=pacedRepo(100,0);
jobsPace.repos[0].summaryAt=0; jobsPace.repos[0].runs=[{id:7,status:'in_progress'}];
jobsPace.details={'a/b:7':{jobsAt:0}};
polling.select(jobsPace,'a/b','7',{'a/b:7':true},0,true);
req=polling.next(jobsPace,5000); assert.equal(req.kind,'jobs');
const lookupPace=pacedRepo(100,0);
lookupPace.repos[0].runs=[{id:7,status:'queued',followupAt:0}];
req=polling.next(lookupPace,15000); assert.equal(req.kind,'run');

// Writes can extend read cooldown without changing read errors, work or request budgets.
for (const [reply,deadline] of [
  [{retryAt:5000},5000],
  [{remaining:0,resetAt:7000},7000],
  [{errorType:'rate'},62000]
]) {
  const write=selectedRepo([{id:7,status:'in_progress'}]);
  write.error='existing error'; write.repos[0].blocked=false; write.repos[0].error='repo error';
  write.cooldown=1000; write.starts=[100,200];
  polling.ensure(write,'run','a/b','7','interactive',9000);
  const before={error:write.error,auth:write.auth,blocked:write.repos[0].blocked,
    repoError:write.repos[0].error,tasks:Object.keys(write.tasks),starts:write.starts.slice()};
  polling.noteWrite(write,reply,2000);
  assert.equal(write.cooldown,deadline);
  assert.deepEqual({error:write.error,auth:write.auth,blocked:write.repos[0].blocked,
    repoError:write.repos[0].error,tasks:Object.keys(write.tasks),starts:write.starts},before);
}
const refusedWrite=selectedRepo([{id:7,status:'in_progress'}]);
refusedWrite.repos[0].activityAt=0;
polling.ensure(refusedWrite,'run','a/b','7','interactive',1000);
polling.noteWrite(refusedWrite,{errorType:'refused',error:'Needs Actions write'},1000);
assert.equal(refusedWrite.repos[0].blocked,undefined);
assert.equal(refusedWrite.auth,false);
assert.equal(polling.next(refusedWrite,1000).kind,'run');

const touched=selectedRepo([{id:7,status:'in_progress'}]);
touched.repos[0].activityAt=0; touched.repos[0].summaryAt=0;
polling.touch(touched,'a/b','7',1000);
const runKey=polling.key('run','a/b','7');
assert.deepEqual(Object.keys(touched.tasks),[runKey]);
assert.equal(touched.tasks[runKey].due,1000);
assert.equal(touched.tasks[runKey].group,'interactive');
assert.equal(touched.repos[0].summaryAt,undefined);
touched.cooldown=2000;
assert.equal(polling.next(touched,1999),null);
req=polling.next(touched,2000); assert.equal(req.kind,'run'); assert.equal(req.run,'7');

const backedOff=selectedRepo([{id:7,status:'in_progress'}]);
backedOff.repos[0].summaryAt=0;
const retryRun=polling.ensure(backedOff,'run','a/b','7','active',9000);
retryRun.failures=3;
polling.touch(backedOff,'a/b','7',1000);
assert.equal(retryRun.due,1000);
assert.equal(retryRun.group,'interactive');
assert.equal(retryRun.failures,3);
assert.equal(backedOff.repos[0].summaryAt,undefined);

const inFlight=selectedRepo([{id:7,status:'in_progress'}]);
inFlight.repos[0].activityAt=0; inFlight.repos[0].summaryAt=0;
polling.ensure(inFlight,'run','a/b','7','interactive',1000);
const older=polling.next(inFlight,1000); assert.equal(older.kind,'run');
polling.touch(inFlight,'a/b','7',1100);
assert.equal(inFlight.tasks[runKey].again,true);
assert.equal(polling.complete(inFlight,response(older,{id:7,status:'completed',run_attempt:1}),1200),true);
assert.ok(inFlight.tasks[runKey]);
assert.ok(inFlight.tasks[runKey].due<=1200);
assert.ok(!inFlight.tasks[runKey].again);
const newer=polling.next(inFlight,2000); assert.equal(newer.kind,'run');
assert.notEqual(newer.requestId,older.requestId);
assert.equal(polling.complete(inFlight,response(newer,{id:7,status:'completed',run_attempt:2}),2100),true);
assert.equal(inFlight.tasks[runKey],undefined);

// #44 step 3: log fetches reserve four slots and always finish after one reply.
function logState() {
  const s=selectedRepo([{id:7,status:'completed'}]);
  s.repos[0].activityAt=0;
  polling.ensure(s,'run','a/b','7','active',0);
  return s;
}
const log=logState();
assert.equal(log.log,null);
assert.equal(polling.requestLog(log,{repo:'a/b',run:'7',job:'9',mode:'failed'},0),true);
assert.equal(polling.requestLog(log,{repo:'a/b',run:'8',job:'10',mode:'full'},0),false);
assert.equal(Object.values(log.tasks).filter(t=>t.kind==='log').length,1);
req=polling.next(log,0);
assert.equal(req.kind,'log'); assert.equal(req.run,'7'); assert.equal(req.job,'9'); assert.equal(req.mode,'failed');
assert.deepEqual(Array.from(log.starts),[0,1000,2000,3000]);
assert.equal(log.requests,1);
assert.equal(polling.complete(log,response(req,{path:'/tmp/log',mode:'failed',cutShort:false,lineCut:false}),100),true);
assert.equal(log.auth,false); assert.equal(log.log.path,'/tmp/log');
assert.equal(log.log.repo,'a/b'); assert.equal(log.log.run,'7'); assert.equal(log.log.job,'9');
assert.equal(log.tasks[polling.key('log','a/b','7')],undefined);
assert.equal(polling.next(log,3999),null,'four charged slots delay all other work');
assert.equal(polling.next(log,4000).kind,'run');
polling.close(log); assert.equal(log.log,null);

const runLog=logState();
assert.equal(polling.requestLog(runLog,{repo:'a/b',run:'7',mode:'failed'},0),true);
req=polling.next(runLog,0);
assert.equal(req.kind,'log'); assert.equal(req.run,'7'); assert.equal('job' in req,false);
assert.equal(req.mode,'failed');

for (const [type,deadline,auth] of [
  ['network',0,false],['permission',0,false],['rate',60100,false],['auth',0,true],['setup',0,true]
]) {
  const s=logState();
  polling.requestLog(s,{repo:'a/b',run:'7',job:'9',mode:'full'},0);
  const request=polling.next(s,0);
  assert.equal(polling.complete(s,{...response(request),error:'log failed',errorType:type},100),true);
  assert.equal(s.log.error,'log failed',type);
  assert.equal(Object.keys(s.tasks).some(k=>s.tasks[k].kind==='log'),false,type+' is final');
  assert.equal(s.repos[0].blocked,undefined,type+' does not block repository');
  assert.equal(s.auth,auth,type);
  if (auth) assert.equal(s.error,'log failed',type);
  if (deadline) assert.equal(s.cooldown,deadline);
}
const malformedLog=logState();
polling.requestLog(malformedLog,{repo:'a/b',run:'7',mode:'failed'},0);
req=polling.next(malformedLog,0);
polling.complete(malformedLog,response(req,[]),100);
assert.equal(malformedLog.log.error,'Workflow helper returned invalid data');
assert.equal(malformedLog.auth,true);
assert.equal(malformedLog.error,'Workflow helper returned invalid data');

const blockedLog=logState(); blockedLog.repos[0].blocked=true;
polling.requestLog(blockedLog,{repo:'a/b',run:'7',mode:'failed'},0);
req=polling.next(blockedLog,0); assert.equal(req.kind,'log');
polling.complete(blockedLog,{...response(req),error:'unavailable',errorType:'permission'},100);
assert.equal(blockedLog.log.error,'unavailable'); assert.equal(blockedLog.repos[0].blocked,true);

for (const occupied of [56,57,58,59]) {
  const s=logState();
  s.starts=Array.from({length:occupied},(_,i)=>i*1000);
  polling.requestLog(s,{repo:'a/b',run:'7',mode:'failed'},0);
  const request=polling.next(s,59999);
  if (occupied===56) {
    assert.equal(request.kind,'log'); assert.equal(s.starts.length,60);
  } else {
    assert.equal(request.kind,'run','ordinary work uses the remaining slot');
    assert.equal(s.starts.length,occupied+1);
    assert.ok(s.tasks[polling.key('log','a/b','7')]);
  }
}

const budget=logState();
let logStarts=0, otherStarts=0;
for (let now=0;now<60000;now+=1000) {
  if (now%8000===0 && !budget.tasks[polling.key('log','a/b','7')])
    polling.requestLog(budget,{repo:'a/b',run:'7',mode:'failed'},now);
  if (now%5000===0) polling.ensure(budget,'run','a/b','7','active',now);
  const request=polling.next(budget,now);
  if (request) {
    if (request.kind==='log') logStarts++;
    else otherStarts++;
    polling.complete(budget,response(request,request.kind==='log' ? {path:'/tmp/log'} : {id:7,status:'completed'}),now+100);
  }
  assert.ok(budget.starts.length<=60,'mixed workload stays within the 60-slot window');
}
assert.ok(logStarts>0 && otherStarts>0);
assert.equal(budget.starts.length,budget.requests+3*logStarts,'four slots per log, one per other request');
console.log('Polling: logs reserve four slots, finish once and preserve blocked repositories');

// #44 step 8: only marked runs poll with the panel closed.
function watchState(count=1) {
  const s=selectedRepo(Array.from({length:count},(_,i)=>({id:i+1,status:'in_progress',name:`Build ${i+1}`,run_attempt:1})));
  s.discover=true;
  for (let i=1;i<=count;i++) assert.equal(polling.watch(s,'a/b',String(i),`Build ${i}`,0),'on');
  polling.close(s);
  return s;
}
const quiet=selectedRepo(); polling.close(quiet);
assert.equal(polling.hasWatches(quiet),false);
assert.equal(polling.next(quiet,60000),null);
const watched=watchState();
assert.equal(polling.hasWatches(watched),true);
assert.equal(polling.next(watched,29999),null);
req=polling.next(watched,30000);
assert.equal(req.kind,'run'); assert.equal(req.run,'1');
assert.equal(Object.keys(watched.tasks).filter(k=>watched.tasks[k].kind!=='run').length,0);
assert.equal(polling.complete(watched,response(req,{id:1,status:'in_progress',name:'Build 1'}),30100),true);
assert.equal(watched.watches['a/b:1'].at,30100);
assert.equal(polling.next(watched,60099),null);
assert.equal(polling.next(watched,60100).kind,'run');
const unchecked=watchState(); unchecked.accountChecked=false;
assert.equal(polling.next(unchecked,30000).kind,'run','a marked run survives closing during the account check');

const capped=watchState(5);
assert.equal(polling.watch(capped,'a/b','6','Build 6',0),'full');
assert.equal(Object.keys(capped.watches).length,5);
const unmarked=watchState();
polling.next(unmarked,30000);
assert.equal(polling.watch(unmarked,'a/b','1','Build 1',30001),'off');
assert.equal(polling.hasWatches(unmarked),false);
assert.equal(polling.next(unmarked,60000),null);
const filterWatch=watchState();
polling.ensure(filterWatch,'jobs','a/b','1','interactive',0);
assert.equal(polling.next(filterWatch,30000).kind,'run','closed polling skips queued non-watch work');
const queuedWatch=watchState();
assert.equal(polling.next(queuedWatch,29999),null);
assert.ok(queuedWatch.tasks[polling.key('run','a/b','1')]);
assert.equal(polling.watch(queuedWatch,'a/b','1','Build 1',1),'off');
assert.equal(queuedWatch.tasks[polling.key('run','a/b','1')],undefined);
const finalLookup=watchState();
finalLookup.repos[0].runs[0].awaitingFinal=true;
polling.next(finalLookup,29999);
polling.open(finalLookup,30000);
assert.equal(polling.watch(finalLookup,'a/b','1','Build 1',30000),'off');
assert.ok(finalLookup.tasks[polling.key('run','a/b','1')],'unwatch keeps an ordinary final lookup while open');

const two=watchState(2);
two.selected='a/b'; two.inspected='1'; two.expanded={'a/b:1':true};
req=polling.next(two,30000); assert.equal(req.run,'1');
polling.complete(two,response(req,{id:1,status:'completed',name:'Finished build',conclusion:'success'}),30100);
assert.deepEqual(JSON.parse(JSON.stringify(two.notices)),[{kind:'done',repo:'a/b',name:'Finished build',conclusion:'success'}]);
assert.equal(two.watches['a/b:1'],undefined);
assert.equal(Object.values(two.tasks).some(t=>t.kind==='jobs'),false,'closed completion never queues jobs');
assert.equal(polling.complete(two,response(req,{id:1,status:'completed'}),30200),false);
assert.equal(two.notices.length,1);
req=polling.next(two,31000); assert.equal(req.kind,'run'); assert.equal(req.run,'2');

const staleWatch=watchState();
const staleRun=polling.next(staleWatch,30000);
polling.open(staleWatch,30100);
assert.equal(polling.complete(staleWatch,response(staleRun,{id:1,status:'completed'}),30200),false);
staleWatch.accountChecked=true;
assert.equal(polling.next(staleWatch,31000).kind,'run','reopen clears a closed in-flight request');

const lost=watchState();
req=polling.next(lost,30000);
polling.complete(lost,{...response(req),error:'gone',errorType:'permission'},30100);
assert.deepEqual(JSON.parse(JSON.stringify(lost.notices)),[{kind:'lost',repo:'a/b',name:'Build 1'}]);
assert.equal(polling.hasWatches(lost),false);
assert.equal(polling.next(lost,60000),null);

for (const type of ['auth','setup']) {
  const paused=watchState(2);
  req=polling.next(paused,30000);
  polling.complete(paused,{...response(req),error:'login',errorType:type},30100);
  assert.deepEqual(JSON.parse(JSON.stringify(paused.notices)),[{kind:'paused'}]);
  assert.equal(Object.keys(paused.watches).length,2);
  assert.equal(paused.paused,true);
  assert.equal(polling.next(paused,60000),null);
  polling.open(paused,61000);
  assert.equal(paused.paused,false);
  paused.accountChecked=true;
  assert.equal(polling.next(paused,61000).kind,'run');
}
const rated=watchState();
req=polling.next(rated,30000);
polling.complete(rated,{...response(req),error:'slow',errorType:'rate',retryAt:90000},30100);
assert.equal(rated.cooldown,90000);
assert.equal(rated.watches['a/b:1'].at,30100);
assert.equal(polling.next(rated,89999),null);
assert.equal(polling.next(rated,90000).kind,'run');

const rerun=watchState();
req=polling.next(rerun,30000);
polling.complete(rerun,response(req,{id:1,status:'in_progress',run_attempt:2,name:'Build 1'}),30100);
assert.equal(polling.hasWatches(rerun),true);
assert.equal(rerun.notices.length,0);

// Five watches stay within ten requests in every rolling minute, even on network errors.
for (const fail of [false,true]) {
  const s=watchState(5), times=[], failed=new Set();
  for (let now=0;now<300000;now+=100) {
    const request=polling.next(s,now);
    if (!request) continue;
    assert.equal(request.kind,'run');
    times.push(now);
    const firstFailure=fail && !failed.has(request.run);
    if (firstFailure) failed.add(request.run);
    const reply=firstFailure ? {...response(request),error:'offline',errorType:'network'}
      : response(request,{id:Number(request.run),status:'in_progress',name:'Build'});
    polling.complete(s,reply,now+50);
    assert.ok(times.filter(t=>now-t<60000).length<=10,'at most ten watch requests per rolling minute');
    assert.ok(s.starts.length<=60,'watch workload respects the shared request budget');
  }
  assert.ok(times.length>=40 && times.length<=50,`five watches recover and poll about 50 times in five minutes (got ${times.length}, errors: ${fail})`);
}
console.log('Polling: closed-panel watches are capped, finish once and recover');

// #44 step 11: #41 hooks. An account change drops watches; low quota stretches the watch interval.
{
  const acct=watchState(); acct.account='tester'; polling.open(acct,0);
  const a=polling.next(acct,0); assert.equal(a.kind,'account');
  polling.complete(acct,response(a,{login:'other'}),100);
  assert.equal(polling.hasWatches(acct),false,'an account change clears watches');
  const slow=watchState(); slow.remaining=400; slow.resetAt=900000;
  assert.equal(polling.next(slow,60000),null,'quotaTight stretches the watch interval 10x');
  assert.equal(polling.next(slow,300000).kind,'run');
}
console.log('Polling: account change clears watches, low quota stretches them');
