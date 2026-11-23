"""GitHub Actions data and a closed set of run actions, using gh's existing authentication."""
import argparse
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, parse_qs


ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")
ACTIONS = {"rerun": "rerun", "rerun-failed": "rerun-failed-jobs", "cancel": "cancel"}
UNKNOWN = "Outcome unknown; check GitHub before retrying"
PRS_SEARCH = "is:pr is:open archived:false sort:updated-desc (author:@me OR user-review-requested:@me)"
PRS_QUERY = """query($q: String!) {
  search(query: $q, type: ISSUE_ADVANCED, first: 50) {
    issueCount
    nodes { ... on PullRequest {
      number title isDraft headRefName headRefOid url
      repository { nameWithOwner }
      commits(last: 1) { nodes { commit { oid statusCheckRollup { state
        contexts(first: 50) { totalCount nodes { __typename
          ... on CheckRun { name status conclusion detailsUrl
            checkSuite { repository { nameWithOwner } workflowRun { databaseId } } }
          ... on StatusContext { context state targetUrl } } } } } } }
    } }
  }
}"""
# ZWNJ and ZWJ are Cf but kept: emoji sequences and several scripts need them, and they cannot reorder text (#32).
JOINERS = "\u200c\u200d"


def repo_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repository must be owner/name")
    if any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Invalid repository")
    return value


def plain(value):
    """Display text from GitHub: line breaks and tabs become spaces, other Cc/Cf characters go (#32)."""
    if not isinstance(value, str):
        return value
    text = " ".join(value.replace("\t", " ").splitlines())
    return "".join(c for c in text if c in JOINERS or unicodedata.category(c) not in ("Cc", "Cf"))


def plain_fields(row, fields):
    for field in fields:
        if field in row:
            row[field] = plain(row[field])
    return row


RUN_TEXT = ("name", "display_title", "head_branch", "event", "path")


def clean_run(row):
    plain_fields(row, RUN_TEXT)
    triggering_actor = row.get("triggering_actor")
    triggering_login = triggering_actor.get("login") if isinstance(triggering_actor, dict) else None
    row["triggering_login"] = plain(triggering_login) if isinstance(triggering_login, str) else ""
    row.pop("triggering_actor", None)  # flattened above; the nested object never reaches QML uncleaned
    actor = row.get("actor")
    login = actor.get("login") if isinstance(actor, dict) else None
    row["actor"] = plain(login) if isinstance(login, str) else ""
    return row


def request(endpoint, include=False, method=None, fields=None):
    child = subprocess.Popen(
        ["gh", "api", "--hostname", "github.com"] + (["--include"] if include else [])
        + (["--method", method] if method else []) + [endpoint]
        + [part for name, value in (fields or {}).items() for part in ("-f", f"{name}={value}")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = child.communicate(timeout=25)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    return stdout, stderr, child.returncode


def run_id(task):
    run = str(task.get("run", ""))
    if not re.fullmatch(r"[0-9]+", run) or int(run) < 1:
        raise ValueError("Invalid run ID")
    return run


def page_endpoint(task):
    if not isinstance(task, dict) or task.get("kind") not in ("catalogue", "activity", "summary", "more", "jobs", "run", "account"):
        raise ValueError("Invalid page operation")
    number = task.get("page", 1)
    if type(number) is not int or number < 1 or number > 100000:
        raise ValueError("Invalid page number")
    if type(task.get("requestId")) is not int or task["requestId"] < 1:
        raise ValueError("Invalid request identity")
    if task["kind"] == "account":
        if task.get("repo") not in (None, ""):
            raise ValueError("Invalid page operation")
        return "user"
    if task["kind"] == "catalogue":
        return f"user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&direction=desc&per_page=100&page={number}"
    base = "repos/" + repo_name(task.get("repo")) + "/actions/runs"
    if task["kind"] in ("jobs", "run"):
        run = run_id(task)
        if task["kind"] == "run":
            return f"{base}/{run}"
        return f"{base}/{run}/jobs?filter=latest&per_page=100&page={number}"
    if task["kind"] == "activity":
        return f"{base}?per_page=30"  # Polling.js ACTIVITY_PAGE must match
    status = "recent" if task["kind"] == "more" else task.get("status", "recent")
    if status == "recent":
        limit = task.get("limit", 10)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid page limit")
        return f"{base}?per_page={limit}"
    if status not in ACTIVE:
        raise ValueError("Invalid workflow status")
    return f"{base}?status={status}&per_page=100&page={number}"


def write_endpoint(task):
    if not isinstance(task, dict) or not isinstance(task.get("action"), str) or task["action"] not in ACTIONS:
        raise ValueError("Invalid action")
    if type(task.get("requestId")) is not int or task["requestId"] < 1:
        raise ValueError("Invalid request identity")
    repo = repo_name(task.get("repo"))
    run = run_id(task)
    return f"repos/{repo}/actions/runs/{run}/{ACTIONS[task['action']]}"


def http_reply(stdout):
    text = stdout.replace("\r\n", "\n")
    headers = {}
    status = None
    while text.startswith("HTTP/"):
        head, separator, text = text.partition("\n\n")
        if not separator:
            raise ValueError("Malformed HTTP response")
        lines = head.splitlines()
        match = re.fullmatch(r"HTTP/\S+ (\d{3})(?: .*)?", lines[0])
        if not match:
            raise ValueError("Malformed HTTP status")
        status = int(match[1])
        headers = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if separator:
                headers[name.lower()] = value.strip()
    if status is None:
        raise ValueError("Missing HTTP response")
    return status, headers, text


def next_page(endpoint, headers):
    for link in headers.get("link", "").split(","):
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if not match:
            continue
        target = urlsplit(match[1])
        source = urlsplit("https://api.github.com/" + endpoint)
        query, expected = parse_qs(target.query), parse_qs(source.query)
        page = query.pop("page", [])
        previous = expected.pop("page", ["1"])
        if (target.scheme != "https" or target.netloc != "api.github.com"
                or target.path != source.path or target.fragment or query != expected
                or len(page) != 1 or not page[0].isdigit() or int(page[0]) != int(previous[0]) + 1):
            raise ValueError("Invalid pagination link")
        return int(page[0])
    return 0


def rate_headers(result, status, headers):
    result["httpStatus"] = status
    if headers.get("x-ratelimit-remaining", "").isdigit():
        result["remaining"] = int(headers["x-ratelimit-remaining"])
    if headers.get("x-ratelimit-reset", "").isdigit():
        result["resetAt"] = int(headers["x-ratelimit-reset"]) * 1000
    retry = headers.get("retry-after", "")
    if retry:
        try:
            result["retryAt"] = ((datetime.now(timezone.utc).timestamp() + int(retry)) * 1000
                                 if retry.isdigit() else parsedate_to_datetime(retry).timestamp() * 1000)
        except (ValueError, TypeError, OverflowError):
            pass


def rate_limited(result, status, body):
    message = str(body.get("message", "")) if isinstance(body, dict) else ""
    return (status == 429 or result["remaining"] == 0 or result["retryAt"]
            or "rate limit" in message.lower() or "secondary rate" in message.lower())


def pull_request(node, unavailable=False):
    if not isinstance(node, dict) or type(node.get("number")) is not int or node["number"] < 1:
        return None
    repository = node.get("repository")
    try:
        repo = repo_name(repository.get("nameWithOwner") if isinstance(repository, dict) else None)
    except ValueError:
        return None
    number = node["number"]
    url = node.get("url")
    sha = node.get("headRefOid")
    sha = sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{40}", sha) else ""
    row = {"repo": repo, "number": number,
           "title": plain(node.get("title"))[:200] if isinstance(node.get("title"), str) else "",
           "branch": plain(node.get("headRefName"))[:100] if isinstance(node.get("headRefName"), str) else "",
           "draft": node.get("isDraft") is True,
           "url": url if url == f"https://github.com/{repo}/pull/{number}" else "",
           "sha": sha}
    commits = node.get("commits")
    commit_nodes = commits.get("nodes") if isinstance(commits, dict) else None
    last = commit_nodes[0] if isinstance(commit_nodes, list) and commit_nodes else None
    commit = last.get("commit") if isinstance(last, dict) else None
    if unavailable or not sha or not isinstance(commit, dict) or commit.get("oid") != sha:
        row["checks"] = {"state": "unavailable"}
        return row
    if "statusCheckRollup" in commit and commit["statusCheckRollup"] is None:
        row["checks"] = {"state": "none"}
        return row
    rollup = commit.get("statusCheckRollup")
    contexts = rollup.get("contexts") if isinstance(rollup, dict) else None
    if contexts is not None and (not isinstance(contexts, dict) or not isinstance(contexts.get("nodes"), list)):
        raise ValueError("Invalid check contexts")
    nodes = contexts["nodes"] if contexts else []
    items = []
    for check in nodes:
        if not isinstance(check, dict):
            continue
        kind = check.get("__typename")
        if kind not in ("CheckRun", "StatusContext"):
            continue
        if kind == "CheckRun":
            name = check.get("name")
            status = check.get("status")
            conclusion = check.get("conclusion")
            suite = check.get("checkSuite")
            suite = suite if isinstance(suite, dict) else {}
            check_repo = suite.get("repository")
            try:
                check_repo = repo_name(check_repo.get("nameWithOwner") if isinstance(check_repo, dict) else None)
            except ValueError:
                check_repo = ""
            workflow = suite.get("workflowRun")
            run = workflow.get("databaseId") if isinstance(workflow, dict) else None
            status = status.lower() if isinstance(status, str) else ""
            conclusion = conclusion.lower() if isinstance(conclusion, str) else ""
            status = status if status in ("queued", "in_progress", "completed", "waiting", "pending", "requested") else "unknown"
            conclusion = conclusion if conclusion in ("success", "failure", "neutral", "cancelled", "timed_out", "action_required", "skipped", "stale", "startup_failure") else ""
            link = check.get("detailsUrl")
        else:
            name = check.get("context")
            state = check.get("state")
            status = "completed" if state in ("SUCCESS", "FAILURE", "ERROR") else "pending" if state in ("PENDING", "EXPECTED") else "unknown"
            conclusion = "success" if state == "SUCCESS" else "failure" if state in ("FAILURE", "ERROR") else ""
            check_repo, run = "", None
            link = check.get("targetUrl")
        items.append({"name": plain(name)[:100] if isinstance(name, str) else "",
                      "status": status, "conclusion": conclusion,
                      "url": link if isinstance(link, str) and plain(link) == link else "",
                      "repo": check_repo,
                      "run": str(run) if type(run) is int and run >= 1 else ""})
    state = rollup.get("state") if isinstance(rollup, dict) else None
    state = "success" if state == "SUCCESS" else "failure" if state in ("FAILURE", "ERROR") else "pending" if state in ("PENDING", "EXPECTED") else "unavailable"
    total = contexts.get("totalCount") if contexts else None
    row["checks"] = {"state": state, "total": total if type(total) is int and total >= 0 else len(items), "items": items}
    return row


def read_prs(task):
    if (set(task) != {"kind", "page", "requestId"} or task["kind"] != "prs"
            or type(task["page"]) is not int or task["page"] != 1
            or type(task["requestId"]) is not int or task["requestId"] < 1):
        raise ValueError("Invalid page operation")
    result = {"requestId": task["requestId"], "httpStatus": 0, "nextPage": 0,
              "data": None, "error": "", "errorType": "", "retryAt": 0,
              "remaining": None, "resetAt": 0, "resource": "graphql"}
    try:
        stdout, stderr, code = request("graphql", include=True, fields={"query": PRS_QUERY, "q": PRS_SEARCH})
        if not stdout.strip() and "auth login" in stderr.lower():
            result.update(errorType="auth", error="Authenticate with gh auth login")
            return result
        if not stdout.strip() and code:
            result.update(errorType="network", error="GitHub request failed; check connection and gh auth status")
            return result
        status, headers, raw_body = http_reply(stdout)
        rate_headers(result, status, headers)
        try:
            body = json.loads(raw_body) if raw_body.strip() else None
        except ValueError:
            body = None
        if status >= 400:
            if rate_limited(result, status, body):
                result.update(errorType="rate", error="GitHub rate limit")
            elif status == 401:
                result.update(errorType="auth", error="Authenticate with gh auth login")
            elif status in (403, 404):
                result.update(errorType="permission", error="Pull requests unavailable; token cannot search them")
            else:
                result.update(errorType="network", error="GitHub request failed")
            return result
        if status != 200 or not isinstance(body, dict):
            raise ValueError("Invalid pull request response")
        errors = body.get("errors", [])
        if not isinstance(errors, list) or any(not isinstance(error, dict) for error in errors):
            raise ValueError("Invalid GraphQL errors")
        data = body.get("data")
        search = data.get("search") if isinstance(data, dict) else None
        usable = isinstance(search, dict) and isinstance(search.get("nodes"), list)
        def error_kind(error):
            kind = error.get("type")
            kind = kind if isinstance(kind, str) else ""
            message = error.get("message")
            message = message if isinstance(message, str) else ""
            return "rate" if kind == "RATE_LIMITED" else "permission" if kind == "FORBIDDEN" or "SAML" in kind.upper() or "SAML" in message.upper() else "network"
        if not usable:
            if errors:
                kind = error_kind(errors[0])
                result.update(errorType=kind, error={"rate": "GitHub rate limit", "permission": "Pull requests unavailable; token or SSO refused", "network": "GitHub returned an error for pull requests"}[kind])
                return result
            raise ValueError("Invalid pull request data")
        unavailable = set()
        partial = False
        for error in errors:
            kind = error_kind(error)
            if kind == "rate":
                result.update(errorType="rate", error="GitHub rate limit")
            path = error.get("path")
            if isinstance(path, list) and len(path) >= 3 and path[:2] == ["search", "nodes"] and type(path[2]) is int:
                unavailable.add(path[2])  # only that row; partial is for errors with no row
            elif kind != "rate":
                partial = True
        rows = []
        for i, node in enumerate(search["nodes"][:50]):
            row = pull_request(node, i in unavailable)
            if row is not None:
                rows.append(row)
        total = search.get("issueCount")
        result["data"] = {"list": rows, "total": total if type(total) is int and total >= 0 else len(rows), "partial": partial}
    except FileNotFoundError:
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        result.update(errorType="network", error="GitHub request timed out or returned invalid data", data=None)
    return result


def read_page(task):
    if isinstance(task, dict) and task.get("kind") == "prs":
        return read_prs(task)
    endpoint = page_endpoint(task)
    result = {"requestId": task["requestId"], "httpStatus": 0, "nextPage": 0,
              "data": None, "error": "", "errorType": "", "retryAt": 0,
              "remaining": None, "resetAt": 0}
    try:
        stdout, stderr, code = request(endpoint, include=True)
        if not stdout.strip() and "auth login" in stderr.lower():
            result.update(errorType="auth", error="Authenticate with gh auth login")
            return result
        if not stdout.strip() and code:
            # gh failed before any HTTP reply: offline, DNS or proxy.
            result.update(errorType="network", error="GitHub request failed; check connection and gh auth status")
            return result
        status, headers, raw_body = http_reply(stdout)
        rate_headers(result, status, headers)
        try:
            body = json.loads(raw_body) if raw_body.strip() else None
        except ValueError:
            if status < 400:
                raise
            body = None
        result["data"] = body
        if status >= 400 or code:
            if task["kind"] == "account":
                result["data"] = None  # never pass on the /user profile, only the login
            if rate_limited(result, status, body):
                result.update(errorType="rate", error="GitHub rate limit")
            elif status == 401:
                result.update(errorType="auth", error="Authenticate with gh auth login")
            elif status in (403, 404):
                result.update(errorType="permission", error=("Repository list unavailable; token cannot read your repositories"
                                                              if task["kind"] == "catalogue" else "Resource unavailable or Actions read permission missing"))
            else:
                result.update(errorType="network", error="GitHub request failed")
            return result
        kind = task["kind"]
        if kind == "catalogue":
            if not isinstance(body, list):
                raise ValueError("Invalid repository response")
            if any(not isinstance(row, dict) for row in body):
                raise ValueError("Invalid repository entry")
            result["data"] = [{"repo": repo_name(row["full_name"]), "description": plain(row.get("description") or ""),
                               "default_branch": plain(row.get("default_branch") or ""),
                               "archived": bool(row.get("archived")), "disabled": bool(row.get("disabled"))} for row in body]
        elif kind == "account":
            result["data"] = None
            login = body.get("login") if isinstance(body, dict) else None
            if not isinstance(login, str) or not re.fullmatch(r"^[A-Za-z0-9_-]{1,39}(\[bot\])?$", login):
                raise ValueError("Invalid account response")
            result["data"] = {"login": login}
        elif kind == "run":
            if not isinstance(body, dict) or str(body.get("id")) != str(task["run"]) or "status" not in body:
                raise ValueError("Invalid run response")
            clean_run(body)
        else:
            key = "jobs" if kind == "jobs" else "workflow_runs"
            if not isinstance(body, dict) or not isinstance(body.get(key), list):
                raise ValueError("Invalid workflow response")
            if any(not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1 or not isinstance(row.get("status"), str) for row in body[key]):
                raise ValueError("Invalid workflow entry")
            if kind == "jobs" and any(not isinstance(row.get("steps", []), list) or any(not isinstance(step, dict) for step in row.get("steps", [])) for row in body[key]):
                raise ValueError("Invalid job steps")
            for row in body[key]:
                if kind == "jobs":
                    plain_fields(row, ("name",))
                else:
                    clean_run(row)
                for step in row.get("steps", []) if kind == "jobs" else []:
                    plain_fields(step, ("name",))
            result["data"] = body[key]
            if kind == "summary" and task.get("status") in ACTIVE:
                # One page per unfinished status (#30); total_count says how many runs were left out.
                total = body.get("total_count")
                if type(total) is not int or total < 0:
                    raise ValueError("Invalid workflow total")
                result["total"] = total
        if kind in ("catalogue", "jobs"):
            result["nextPage"] = next_page(endpoint, headers)
    except FileNotFoundError:
        # ponytail: only Popen(["gh", ...]) raises this; PermissionError stays "network"
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        result.update(errorType="network", error="GitHub request timed out or returned invalid data")
    return result


def clean_log(text):
    text = re.sub(r"\x1b\][^\x07\x1b\n]*(?:\x07|\x1b\\)?", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b.?", "", text, flags=re.DOTALL).replace("\r", "")
    lines = []
    cut = 0
    for line in text.split("\n"):
        line = "".join(c for c in line if c in "\n\t" or c in JOINERS
                       or unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"))
        if len(line) > 2000:
            line = line[:2000] + "…"
            cut += 1
        lines.append(line)
    return "\n".join(lines), cut


def log_dir():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not os.path.isabs(runtime):
        raise ValueError("Log directory unavailable")
    directory = os.path.join(runtime, "nixarchy-ghtui")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    info = os.lstat(directory)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Log directory unavailable")
    return directory


def read_log(task, timeout=90):
    if not isinstance(task, dict) or type(task.get("requestId")) is not int or task["requestId"] < 1:
        raise ValueError("Invalid request identity")
    repo = repo_name(task.get("repo"))
    run = run_id(task)
    job = task.get("job")
    if job is not None:
        if not re.fullmatch(r"[0-9]+", str(job)) or int(job) < 1:
            raise ValueError("Invalid job ID")
        job = str(job)
    mode = task.get("mode")
    if mode not in ("failed", "full") or mode == "full" and not job:
        raise ValueError("Invalid log mode")
    directory = log_dir()
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        try:
            info = os.lstat(path)
            if stat.S_ISREG(info.st_mode) and info.st_mtime < time.time() - 86400:
                os.unlink(path)
        except FileNotFoundError:
            pass
    result = {"requestId": task["requestId"], "httpStatus": 0, "nextPage": 0,
              "data": None, "error": "", "errorType": "", "retryAt": 0,
              "remaining": None, "resetAt": 0}
    command = ["gh", "run", "view"] + (["--job", job] if job else [run]) + [
        "--log-failed" if mode == "failed" else "--log", "-R", "github.com/" + repo]
    try:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
        return result
    tail = bytearray()
    errors = bytearray()
    total = 0

    def read_stdout():
        nonlocal total
        while chunk := os.read(child.stdout.fileno(), 65536):
            total += len(chunk)
            tail.extend(chunk)
            if len(tail) > 1048576:
                del tail[:-1048576]

    def read_stderr():
        while chunk := os.read(child.stderr.fileno(), 65536):
            errors.extend(chunk)

    readers = [threading.Thread(target=read_stdout), threading.Thread(target=read_stderr)]
    for reader in readers:
        reader.start()
    try:
        code = child.wait(timeout=timeout)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        for reader in readers:
            reader.join()
        child.stdout.close()
        child.stderr.close()
    if code:
        stderr = errors.decode("utf-8", "replace").lower()
        if any(term in stderr for term in ("rate limit", "http 429", "secondary rate")):
            result.update(errorType="rate", error="GitHub rate limit")
        elif "auth login" in stderr or "http 401" in stderr:
            result.update(errorType="auth", error="Authenticate with gh auth login")
        elif "http 403" in stderr or "http 404" in stderr:
            result.update(errorType="permission", error="Log unavailable or expired")
        else:
            result.update(errorType="network", error="GitHub log request failed")
        return result
    text, lines_cut = clean_log(tail.decode("utf-8", "replace"))
    result["data"] = {"path": "", "mode": mode, "cutShort": total > 1048576, "lineCut": bool(lines_cut)}
    if not text:
        result["error"] = "No failed steps in this log." if mode == "failed" else "This log is empty."
        return result
    cuts = []
    if total > 1048576:
        cuts.append(f"cut short: showing the last 1 MiB of {(total + 1048575) // 1048576} MiB")
    if lines_cut:
        cuts.append(f"lines cut: {lines_cut} lines longer than 2,000 characters were shortened")
    header = f"{repo} · run {run}" + (f" · job {job}" if job else "") + f" · {mode}\n"
    header += "; ".join(cuts) if cuts else "complete"
    fd, path = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(header + "\n\n" + text)
    except BaseException:
        os.unlink(path)
        raise
    result["data"]["path"] = path
    return result


def view(argv):
    if len(argv) != 1:
        return 1
    path = argv[0]
    try:
        directory = log_dir()
        if os.path.dirname(path) != directory or not stat.S_ISREG(os.lstat(path).st_mode):
            return 1
    except (OSError, ValueError):
        return 1
    def hangup(*_):
        raise SystemExit(1)

    signal.signal(signal.SIGHUP, hangup)
    env = {key: value for key, value in os.environ.items() if not key.startswith("LESS")}
    env.update(LESSSECURE="1", LESS="")
    try:
        try:
            return subprocess.run(["less", "--", path], check=False, env=env).returncode
        except FileNotFoundError:
            print("Install less to view logs", file=sys.stderr)
            return 1
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def write_action(task):
    endpoint = write_endpoint(task)
    result = {"requestId": task["requestId"], "action": task["action"], "httpStatus": 0,
              "ok": False, "error": "", "errorType": "", "retryAt": 0,
              "remaining": None, "resetAt": 0}
    try:
        stdout, stderr, code = request(endpoint, include=True, method="POST")
        if not stdout.strip() and "auth login" in stderr.lower():
            result.update(errorType="auth", error="Authenticate with gh auth login")
            return result
        status, headers, raw_body = http_reply(stdout)
        rate_headers(result, status, headers)
        try:
            body = json.loads(raw_body) if raw_body.strip() else None
        except ValueError:
            if status < 400:
                raise
            body = None
        # Success and "unknown" first: rate headers on an accepted write still set a cooldown, never a failure (#45).
        if 200 <= status < 300 and code == 0:
            result["ok"] = True
        elif not 400 <= status < 500:
            result.update(errorType="unknown", error=UNKNOWN)
        elif rate_limited(result, status, body):
            result.update(errorType="rate", error="GitHub rate limit")
        elif status == 401:
            result.update(errorType="auth", error="Authenticate with gh auth login")
        else:
            message = plain(str(body.get("message", "")))[:120] if isinstance(body, dict) else ""
            prefix = f"Needs Actions write on {task['repo']}" if status in (403, 404) else "GitHub refused"
            result.update(errorType="refused", error=prefix + (": " + message if message else ""))
    except FileNotFoundError:
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
    except (subprocess.TimeoutExpired, OSError, ValueError, RecursionError):
        result.update(errorType="unknown", error=UNKNOWN)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("page", "act", "log", "view"))
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()
    if args.mode == "view":
        return view(args.targets)

    def cancelled(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, cancelled)
    task = None
    try:
        if len(args.targets) != 1:
            raise ValueError(f"{args.mode} requires one JSON request")
        task = json.loads(args.targets[0])
        data = read_page(task) if args.mode == "page" else read_log(task) if args.mode == "log" else write_action(task)
        data["updated"] = datetime.now(timezone.utc).isoformat()
        print(json.dumps(data))
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        message = (UNKNOWN if args.mode == "act" and isinstance(exc, (subprocess.TimeoutExpired, OSError))
                   else str(exc) if isinstance(exc, (RuntimeError, ValueError))
                   else "GitHub request timed out or returned invalid data")
        error = {"error": message}
        error["errorType"] = ("unknown" if args.mode == "act" else "network") if isinstance(exc, (subprocess.TimeoutExpired, OSError)) else "setup"
        if isinstance(task, dict) and type(task.get("requestId")) is int and task["requestId"] > 0:
            error["requestId"] = task["requestId"]
        print(json.dumps(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
