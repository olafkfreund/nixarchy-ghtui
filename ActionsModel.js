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

function icon(status) {
    if (status === "success") return "✓";
    if (["failure", "timed_out", "startup_failure"].indexOf(status) >= 0) return "✕";
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
    return remaining.toLocaleString("en-US") + " API requests left" + (remaining < 500 ? " · resets " + clock(resetAt) : "");
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
    var tail = row.kind === "repo" ? row.info : row.statusText;
    var name = kind + ": " + row.title + (tail ? ", " + tail : "");
    if (["repo", "run", "job"].indexOf(row.kind) >= 0) name += expanded ? ", expanded" : ", collapsed";
    return name;
}

// live is "repo:runId" of the run polling refreshes now, or "" / undefined.
function rows(repos, expanded, details, filter, now, live) {
    var result = [];
    var query = filter.toLowerCase();
    repos.slice().sort(function(a, b) { return (b.active || 0) - (a.active || 0); }).forEach(function(repo) {
        var repoMatch = (repo.repo + " " + (repo.description || "")).toLowerCase().indexOf(query) >= 0;
        var runs = (repo.runs || []).filter(function(run) {
            return repoMatch || [run.name, run.display_title, run.head_branch, state(run)].join(" ").toLowerCase().indexOf(query) >= 0;
        });
        if (query && !repoMatch && !runs.length) return;
        var active = repo.active === undefined ? (repo.runs || []).filter(function(run) { return run.status === "in_progress"; }).length : repo.active;
        var repoKey = "repo:" + repo.repo;
        result.push({key: repoKey, parent: "", kind: "repo", depth: 0, title: repo.repo,
            subtitle: repo.error || repo.description || "", status: repo.error ? "error" : (active ? "in_progress" : "neutral"),
            info: repo.archived ? "archived" : repo.disabled ? "disabled" : repo.error ? "unavailable" : repo.checked || repo.runs ? active + " running" : "not checked",
            repo: repo.repo, url: "https://github.com/" + repo.repo + "/actions"});
        if (!expanded[repoKey]) return;
        // Runs past the first page of each unfinished status are counted, not fetched (#30).
        var hidden = repo.hidden || {};
        var parts = ["in_progress", "queued", "waiting", "pending", "requested"].filter(function(s) { return hidden[s] > 0; })
            .map(function(s) { return "+" + (hidden[s] > 1000 ? "about " : "") + hidden[s] + " more " + s; });
        var more = parts.length && (!query || repoMatch) ? {key: repoKey + ":more", parent: repoKey, kind: "more", depth: 1,
            title: parts.join(" · "), subtitle: "o opens GitHub", status: "", info: "", repo: repo.repo,
            url: "https://github.com/" + repo.repo + "/actions"} : null;
        runs.forEach(function(run) {
            if (more && run.status === "completed") { result.push(more); more = null; }
            var runKey = repo.repo + ":" + run.id;
            var detail = details[runKey];
            var fresh = !!detail && (runKey === live || (run.status === "completed" && detail.finalAttempt === (run.run_attempt || 1)));
            var notRefreshing = !!(detail && detail.updated) && !!expanded[runKey] && !fresh;
            var at = notRefreshing ? Date.parse(detail.updated) : now;
            var stamp = !detail || !detail.updated ? "" : notRefreshing ? " · jobs " + elapsed(now - at) + " old, not refreshing"
                : " · jobs fetched " + detail.updated.slice(11, 19) + " UTC";
            result.push({key: runKey, parent: repoKey, kind: "run", depth: 1, title: run.name || "Workflow",
                subtitle: (run.head_branch || "") + " · #" + run.run_number + stamp + " · " + (run.display_title || ""),
                status: state(run), info: duration(run, now), repo: repo.repo, run: String(run.id), url: run.html_url});
            if (!expanded[runKey]) return;
            if (!detail || detail.error) result.push({key: runKey + ":message", parent: runKey, kind: "message", depth: 2,
                title: detail ? detail.error : "Loading jobs…", subtitle: "", status: detail ? "error" : "queued", info: "", repo: repo.repo, run: String(run.id)});
            ((detail && detail.jobs) || []).forEach(function(job) {
                var jobKey = runKey + ":" + job.id;
                var steps = job.steps || [];
                var done = steps.filter(function(step) { return step.status === "completed"; }).length;
                result.push({key: jobKey, parent: runKey, kind: "job", depth: 2, title: job.name, subtitle: "",
                    status: state(job), info: done + "/" + steps.length + " steps · " + duration(job, at), repo: repo.repo, run: String(run.id), url: job.html_url});
                if (!expanded[jobKey]) return;
                steps.forEach(function(step) {
                    result.push({key: jobKey + ":" + step.number, parent: jobKey, kind: "step", depth: 3, title: step.name, subtitle: "",
                        status: state(step), info: duration(step, at), repo: repo.repo, run: String(run.id), url: job.html_url});
                });
            });
        });
        if (more) result.push(more);
    });
    return result;
}

function selection(rows, key, previous) {
    for (var i = 0; i < rows.length; i++) if (rows[i].key === key) return i;
    return Math.max(0, Math.min(previous, rows.length - 1));
}

// ponytail: the fields the delegate reads that can change for a key; add any new one the delegate reads.
var shownFields = ["title", "subtitle", "status", "info"];

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
