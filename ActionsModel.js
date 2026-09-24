// Fixed text only: stderr can hold paths and tracebacks, so it goes to the log, never the panel.
function reply(stdout, code, requestId) {
    if (stdout.trim()) return stdout;
    return JSON.stringify({requestId: requestId, errorType: "setup",
        error: code === 127 ? "python3 not found" : "Workflow helper failed (exit " + code + "); see the shell log"});
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

function rows(repos, expanded, details, filter, now) {
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
            var stamp = detail && detail.updated ? " · jobs fetched " + detail.updated.slice(11, 19) + " UTC" : "";
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
                    status: state(job), info: done + "/" + steps.length + " steps · " + duration(job, now), repo: repo.repo, run: String(run.id), url: job.html_url});
                if (!expanded[jobKey]) return;
                steps.forEach(function(step) {
                    result.push({key: jobKey + ":" + step.number, parent: jobKey, kind: "step", depth: 3, title: step.name, subtitle: "",
                        status: state(step), info: duration(step, now), repo: repo.repo, run: String(run.id), url: job.html_url});
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
