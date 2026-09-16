function state(item) {
    return item.conclusion || item.status || "unknown";
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
    repos.forEach(function(repo) {
        var repoMatch = repo.repo.toLowerCase().indexOf(query) >= 0;
        var runs = (repo.runs || []).filter(function(run) {
            return repoMatch || [run.name, run.display_title, run.head_branch, state(run)].join(" ").toLowerCase().indexOf(query) >= 0;
        });
        if (query && !repoMatch && !runs.length) return;
        var active = (repo.runs || []).filter(function(run) { return run.status !== "completed"; }).length;
        var repoKey = "repo:" + repo.repo;
        result.push({key: repoKey, parent: "", kind: "repo", depth: 0, title: repo.repo,
            subtitle: repo.error || (repo.runs ? "" : "Loading workflows…"), status: repo.error ? "error" : (active ? "in_progress" : "neutral"),
            info: active + " active", repo: repo.repo, url: "https://github.com/" + repo.repo + "/actions"});
        if (!expanded[repoKey] && !query) return;
        runs.forEach(function(run) {
            var runKey = repo.repo + ":" + run.id;
            var detail = details[runKey];
            var stamp = detail && detail.updated ? " · jobs fetched " + new Date(detail.updated).toLocaleTimeString() : "";
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
    });
    return result;
}

function selection(rows, key, previous) {
    for (var i = 0; i < rows.length; i++) if (rows[i].key === key) return i;
    return Math.max(0, Math.min(previous, rows.length - 1));
}
