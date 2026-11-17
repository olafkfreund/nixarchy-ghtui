// Fixed text only: stderr can hold paths and tracebacks, so it goes to the log, never the panel.
function reply(stdout, code, requestId) {
    if (stdout.trim()) return stdout;
    return JSON.stringify({requestId: requestId, errorType: "setup",
        error: code === 127 ? "python3 not found" : "Workflow helper failed (exit " + code + "); see the shell log"});
}

// The trailing slash pins the host; no whitespace or Cc control may reach xdg-open's helpers (#32).
function browsable(url) {
    return typeof url === "string" && /^https:\/\/github\.com\/[^\s\x00-\x1f\x7f-\x9f]+$/.test(url);
}

function state(item) {
    return item.awaitingFinal ? "awaiting final status" : item.lookupError ? "unavailable" : item.conclusion || item.status || "unknown";
}

var FAILED = ["failure", "timed_out", "startup_failure"];
// ponytail: 3 * Polling TIMING.idle, kept equal by tests/model.cjs.
var STALE = 1800000;

function icon(status) {
    if (status === "success") return "✓";
    if (FAILED.indexOf(status) >= 0) return "✕";
    if (status === "in_progress") return "◷";
    if (status === "cancelled") return "⊘";
    if (["skipped", "neutral"].indexOf(status) >= 0) return "−";
    return "○";
}

function duration(item, now) {
    var start = Date.parse(item.started_at || item.run_started_at || "");
    if (!isFinite(start)) return "";
    var end = Date.parse(item.completed_at || (item.status === "completed" ? item.updated_at : "") || "");
    var seconds = Math.max(0, Math.floor(((isFinite(end) ? end : now) - start) / 1000));
    if (seconds >= 3600) return Math.floor(seconds / 3600) + "h " + Math.floor(seconds % 3600 / 60) + "m";
    return seconds >= 60 ? Math.floor(seconds / 60) + "m " + seconds % 60 + "s" : seconds + "s";
}

var labels = {in_progress: "running", queued: "queued", requested: "queued", pending: "queued", waiting: "waiting",
    success: "passed", failure: "failed", timed_out: "timed out", startup_failure: "startup failed",
    cancelled: "cancelled", skipped: "skipped", neutral: "neutral", action_required: "needs action",
    "awaiting final status": "checking result", unavailable: "unavailable"};
function label(status) {
    return Object.prototype.hasOwnProperty.call(labels, status) ? labels[status] : "unknown";
}

// Whole minutes below an hour, then "Xh Ym": #41's not-refreshing marker.
function elapsed(ms) {
    var minutes = Math.floor(Math.max(0, ms) / 60000);
    return minutes >= 60 ? Math.floor(minutes / 60) + "h " + minutes % 60 + "m" : minutes + "m";
}

function age(run, now) {
    var start = Date.parse(run.run_started_at || run.created_at || "");
    if (!isFinite(start)) return "";
    var seconds = Math.max(0, Math.floor((now - start) / 1000));
    if (seconds < 60) return "now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    return Math.floor(seconds / 86400) + "d ago";
}

function clampStep(n) { return Math.max(-3, Math.min(5, Math.round(Number(n) || 0))) }
function zoomed(px, step) { return px > 0 ? Math.max(1, Math.round(px * (10 + clampStep(step)) / 10)) : 0 }
// Fonts stop at 9 px (or the theme size if smaller): 7 px captions at 70% were unreadable (#57).
function fontPx(px, step) { return Math.max(Math.min(px, 9), zoomed(px, step)) }

// Compact age of a result: Ns, Nm or Nh, floored.
function ago(at, now) {
    var start = Date.parse(at || "");
    if (!isFinite(start)) return "";
    var seconds = Math.max(0, Math.floor((now - start) / 1000));
    return seconds < 60 ? seconds + "s" : seconds < 3600 ? Math.floor(seconds / 60) + "m" : Math.floor(seconds / 3600) + "h";
}

// Repository row status and text from its last default-branch result (#43).
function health(repo, now, active) {
    if (repo.archived) return {status: "neutral", info: "archived"};
    if (repo.disabled) return {status: "neutral", info: "disabled"};
    if (repo.error) return {status: "error", info: "unavailable"};
    if (!repo.checked && !repo.runs) return {status: "neutral", info: "not checked"};
    var last = repo.last, running = active + " running";
    if (!last) return {status: "neutral", info: "no result · " + running};
    var failed = FAILED.indexOf(last.conclusion) >= 0, stale = !(now - last.confirmedAt < STALE);
    var glyph = failed ? "✕" : last.conclusion === "success" ? "✓" : "⊘";
    return {status: failed ? "failure" : last.conclusion === "success" && !stale ? "success" : "neutral",
        info: [glyph + " " + ago(last.at, now), running, stale ? "stale" : ""].filter(Boolean).join(" · ")};
}

function cap(text, n) {
    if (typeof text !== "string") return "";
    return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

function clock(ms, seconds) {
    var date = new Date(ms);
    var time = [date.getHours(), date.getMinutes()];
    if (seconds) time.push(date.getSeconds());
    return time.map(function(part) { return ("0" + part).slice(-2); }).join(":");
}

function quotaText(remaining, resetAt, now) {
    if (typeof remaining !== "number" || !(now < resetAt)) return "";
    return String(remaining).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + " API requests left" + (remaining < 500 ? " · resets " + clock(resetAt) : "");
}

function statusLine(s, now) {
    var parts = [];
    if (s.notice && now < s.noticeUntil) parts.push(s.notice);
    var error = s.error || "";
    if (!error) for (var i = 0; i < s.repos.length; i++) {
        if (s.repos[i].error) { error = s.repos[i].repo + ": " + s.repos[i].error; break; }
    }
    if (error) parts.push(error);
    var paused = now < s.cooldown;
    if (paused) parts.push("GitHub paused until " + clock(s.cooldown, true));
    if (!error && !paused) parts.push(s.discoveryComplete ? "Activity checked " + s.checkedCount + "/" + s.repoCount
        : "Discovering repositories… " + s.repoCount + " found");
    return {text: parts.join(" · "), urgent: !!(error || paused), quota: quotaText(s.remaining, s.resetAt, now)};
}

function emptyText(s) {
    if (!s.repoCount && s.error) return s.error;
    if (!s.repoCount && !s.discoveryComplete) return "Discovering repositories…";
    if (!s.repoCount) return "No repositories found for this account";
    return 'No match for "' + s.filter + '" · search covers loaded runs only';
}

function coverage(repos) {
    return {loaded: repos.filter(function(repo) { return !!repo.summaryAt; }).length, total: repos.length};
}

function accessibleName(row, expanded) {
    var kind = row.kind === "repo" ? "repository" : row.kind;
    var tail = row.kind === "repo" ? [row.statusText, row.info].filter(Boolean).join(", ") : row.statusText;
    var name = kind + ": " + row.title + (tail ? ", " + tail : "");
    if (row.kind === "run" && /watching$/.test(row.info || "")) name += ", watching";
    if (["repo", "run", "job"].indexOf(row.kind) >= 0) name += expanded ? ", expanded" : ", collapsed";
    return name;
}

function parseFilter(filter) {
    var tokens = [], words = [];
    filter.toLowerCase().split(/\s+/).forEach(function(word) {
        var match = /^(branch|actor):(.+)$/.exec(word);
        if (match) tokens.push({kind: match[1], value: match[2]});
        else if (word === "is:failed") tokens.push({kind: "failed"});
        else if (word) words.push(word);
    });
    return {text: tokens.length ? words.join(" ") : filter.toLowerCase(), tokens: tokens};
}

// live is "repo:runId" of the run polling refreshes now, or "" / undefined.
function rows(repos, expanded, details, filter, now, live, watches) {
    var result = [];
    var parsed = parseFilter(filter), query = parsed.text, tokens = parsed.tokens;
    watches = watches || {};
    // Failing first, then running (most first), then the rest in catalogue order; never by time, so rows do not jump.
    repos.map(function(repo, i) {
        var active = repo.active === undefined ? (repo.runs || []).filter(function(run) { return run.status === "in_progress"; }).length : repo.active;
        var h = health(repo, now, active);
        return {repo: repo, active: active, h: h, rank: h.status === "failure" ? 0 : active > 0 ? 1 : 2, i: i};
    }).sort(function(a, b) { return a.rank - b.rank || (a.rank === 1 ? b.active - a.active : 0) || a.i - b.i; }).forEach(function(entry) {
        var repo = entry.repo, active = entry.active, h = entry.h;
        var repoMatch = (repo.repo + " " + (repo.description || "")).toLowerCase().indexOf(query) >= 0;
        var runs = (repo.runs || []).filter(function(run) {
            return tokens.every(function(token) {
                if (token.kind === "failed") return FAILED.indexOf(run.conclusion) >= 0;
                return (token.kind === "branch" ? run.head_branch || "" : run.actor || "").toLowerCase().indexOf(token.value) >= 0;
            }) && (repoMatch || [run.name, run.display_title, run.head_branch, run.event, run.actor, state(run), label(state(run))].join(" ").toLowerCase().indexOf(query) >= 0);
        });
        if ((tokens.length || query && !repoMatch) && !runs.length) return;
        var repoKey = "repo:" + repo.repo;
        result.push({key: repoKey, parent: "", kind: "repo", depth: 0, title: repo.repo,
            subtitle: repo.error || repo.description || "", status: h.status, info: h.info,
            statusText: label(h.status),
            repo: repo.repo, url: "https://github.com/" + repo.repo + "/actions"});
        if (!expanded[repoKey]) return;
        // Runs past the first page of each unfinished status are counted, not fetched (#30).
        var hidden = repo.hidden || {};
        var parts = ["in_progress", "queued", "waiting", "pending", "requested"].filter(function(s) { return hidden[s] > 0; })
            .map(function(s) { return "+" + (hidden[s] > 1000 ? "about " : "") + hidden[s] + " more " + s; });
        var beforeRuns = !!parts.length;
        if (repo.recentFetched >= (repo.recentLimit || 10))
            parts.push("last " + repo.recentFetched + " runs fetched" + (repo.recentFetched < 100 ? " · m loads 30 more" : ""));
        var more = !tokens.length && parts.length && (!query || repoMatch) ? {key: repoKey + ":more", parent: repoKey, kind: "more", depth: 1,
            title: parts.join(" · "), subtitle: "o opens GitHub", status: "", statusText: "", info: "", repo: repo.repo,
            url: "https://github.com/" + repo.repo + "/actions"} : null;
        runs.forEach(function(run) {
            if (more && beforeRuns && run.status === "completed") { result.push(more); more = null; }
            var runKey = repo.repo + ":" + run.id;
            var detail = details[runKey];
            var fresh = !!detail && (runKey === live || (run.status === "completed" && detail.finalAttempt === (run.run_attempt || 1)));
            var notRefreshing = !!(detail && detail.updated) && !!expanded[runKey] && !fresh;
            var at = notRefreshing ? Date.parse(detail.updated) : now;
            result.push({key: runKey, parent: repoKey, kind: "run", depth: 1, title: run.name || "Workflow",
                subtitle: [cap(run.head_branch, 28), cap(run.event, 14), cap(run.actor, 16), age(run, now),
                    notRefreshing ? "jobs " + elapsed(now - at) + " old, not refreshing" : "", run.display_title]
                    .filter(Boolean).join(" · "),
                status: state(run), statusText: label(state(run)), info: [duration(run, now), watches[runKey] ? "watching" : ""].filter(Boolean).join(" · "),
                repo: repo.repo, run: String(run.id), url: run.html_url});
            if (!expanded[runKey]) return;
            if (!detail || detail.error) result.push({key: runKey + ":message", parent: runKey, kind: "message", depth: 2,
                title: detail ? detail.error : "Loading jobs…", subtitle: "", status: detail ? "error" : "queued", statusText: "", info: "", repo: repo.repo, run: String(run.id)});
            ((detail && detail.jobs) || []).forEach(function(job) {
                var jobKey = runKey + ":" + job.id;
                var steps = job.steps || [];
                var done = steps.filter(function(step) { return step.status === "completed"; }).length;
                result.push({key: jobKey, parent: runKey, kind: "job", depth: 2, title: job.name, subtitle: "",
                    status: state(job), statusText: label(state(job)), info: done + "/" + steps.length + " steps · " + duration(job, at), repo: repo.repo, run: String(run.id), job: String(job.id), url: job.html_url});
                if (!expanded[jobKey]) return;
                steps.forEach(function(step) {
                    result.push({key: jobKey + ":" + step.number, parent: jobKey, kind: "step", depth: 3, title: step.name, subtitle: "",
                        status: state(step), statusText: label(state(step)), info: duration(step, at), repo: repo.repo, run: String(run.id), job: String(job.id), url: job.html_url});
                });
            });
        });
        if (more) result.push(more);
        else if (!(repo.runs || []).length && !repo.error && !repo.archived && !repo.disabled && !repo.blocked) result.push({key: repoKey + ":message", parent: repoKey, kind: "message", depth: 1,
            title: repo.summaryAt ? "No workflow runs" : "Loading runs…", subtitle: "", status: "", statusText: "", info: "", repo: repo.repo});
    });
    return result;
}

function logTarget(row, details, runs) {
    if (!row) return null;
    if (row.kind === "job" || row.kind === "step") {
        var detail = details[row.repo + ":" + row.run];
        var job = ((detail && detail.jobs) || []).find(function(item) { return String(item.id) === row.job; });
        if (!job || job.status !== "completed") return {error: "Logs are available when the job finishes"};
        var run = runs.find(function(item) { return String(item.id) === row.run; });
        if (!run || run.status !== "completed") return {error: "Logs are available when the run finishes"};
        return {repo: row.repo, run: row.run, job: row.job,
            mode: FAILED.indexOf(job.conclusion) >= 0 ? "failed" : "full"};
    }
    if (row.kind === "run") {
        var run = runs.find(function(item) { return String(item.id) === row.run; });
        return run && run.status === "completed" && FAILED.indexOf(run.conclusion) >= 0
            ? {repo: row.repo, run: row.run, mode: "failed"} : {error: "Select a job to read its log"};
    }
    return null;
}

var conclusionWords = {success: "succeeded", failure: "failed", cancelled: "cancelled", timed_out: "timed out",
    startup_failure: "failed to start", skipped: "skipped"};
function notice(n) {
    if (n.kind === "paused") return {title: "Watching paused", body: "Run gh auth login, then open the panel"};
    var body = n.repo + " · " + String(n.name || "").replace(/[<>&]/g, " ").slice(0, 80);
    if (n.kind === "lost") return {title: "Watch stopped", body: body + " GitHub no longer shows this run."};
    return {title: Object.prototype.hasOwnProperty.call(conclusionWords, n.conclusion) ? conclusionWords[n.conclusion] : "finished", body: body};
}

function selection(rows, key, previous) {
    for (var i = 0; i < rows.length; i++) if (rows[i].key === key) return i;
    return Math.max(0, Math.min(previous, rows.length - 1));
}

// ponytail: the fields the delegate reads that can change for a key; add any new one the delegate reads.
var shownFields = ["title", "subtitle", "status", "statusText", "info"];

// Keep delegates alive when polling changes a status or inserts a running repo.
// Removing gone rows first keeps one removal from cascading into a move per later row.
function syncRows(model, rows) {
    var structureChanged = false, wanted = {}, present = {}, i, j;
    for (i = 0; i < rows.length; i++) wanted[rows[i].key] = true;
    for (j = model.count - 1; j >= 0; j--)
        if (!wanted[model.get(j).rowKey]) { model.remove(j, 1); structureChanged = true; }
    for (j = 0; j < model.count; j++) present[model.get(j).rowKey] = true;
    for (i = 0; i < rows.length; i++) {
        var key = rows[i].key;
        if (i >= model.count || model.get(i).rowKey !== key) {
            structureChanged = true;
            if (!present[key]) { model.insert(i, {rowKey: key, rowData: rows[i]}); continue; }
            for (j = i + 1; model.get(j).rowKey !== key; j++);
            model.move(j, i, 1);
        }
        var old = model.get(i).rowData;
        if (shownFields.some(function(field) { return old[field] !== rows[i][field]; }))
            model.setProperty(i, "rowData", rows[i]);
    }
    return structureChanged;
}

// Run actions (#45). The raw run decides what is offered; a row only carries a mapped status.
var failedConclusions = ["failure", "timed_out", "startup_failure", "cancelled"];
function actionsFor(run) {
    if (!run) return [];
    if (run.status !== "completed") return ["cancel"];
    return failedConclusions.indexOf(run.conclusion) >= 0 ? ["rerun", "rerun-failed"] : ["rerun"];
}
function unavailable(action, run) {
    if (!run) return "Select a run to rerun or cancel";
    if (actionsFor(run).indexOf(action) >= 0) return "";
    return action === "rerun" ? "Only a finished run can be rerun"
        : action === "rerun-failed" ? "Rerun failed needs a failed run" : "Only an unfinished run can be cancelled";
}
function describe(action, repo, run) {
    function cut(text) {
        text = String(text).replace(/[\x00-\x1f\x7f-\x9f]/g, " ");
        return text.length > 30 ? text.slice(0, 29) + "…" : text;
    }
    var target = repo + " #" + run.run_number + " " + cut(run.name || "Workflow") + " (" + cut(run.head_branch || "") + ")";
    var ask = action === "rerun" ? "Rerun all jobs? y yes · n no"
        : action === "rerun-failed" ? "Rerun failed jobs? y yes · n no" : "Cancel run? y yes · n no · cannot be undone";
    var done = action === "rerun" ? "Rerun requested: "
        : action === "rerun-failed" ? "Rerun of failed jobs requested: " : "Cancel requested: ";
    return {confirm: ask + " — " + target, done: done + target};
}
// Like reply(), but an empty answer after a possible send is "unknown", never "setup" (except a missing python3).
function actionReply(stdout, code, requestId) {
    if (stdout.trim()) return stdout;
    return JSON.stringify(code === 127 ? {requestId: requestId, ok: false, errorType: "setup", error: "python3 not found"}
        : {requestId: requestId, ok: false, errorType: "unknown", error: "Outcome unknown; check GitHub before retrying"});
}
