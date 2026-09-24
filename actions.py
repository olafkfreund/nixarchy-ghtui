"""Read-only GitHub Actions data, using gh's existing authentication."""
import argparse
import json
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, parse_qs


ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")


def repo_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repository must be owner/name")
    if any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Invalid repository")
    return value


def request(endpoint, include=False):
    child = subprocess.Popen(
        ["gh", "api", "--hostname", "github.com"] + (["--include"] if include else []) + [endpoint],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = child.communicate(timeout=25)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    return stdout, stderr, child.returncode


def page_endpoint(task):
    if not isinstance(task, dict) or task.get("kind") not in ("catalogue", "activity", "summary", "jobs", "run"):
        raise ValueError("Invalid page operation")
    number = task.get("page", 1)
    if type(number) is not int or number < 1 or number > 100000:
        raise ValueError("Invalid page number")
    if type(task.get("requestId")) is not int or task["requestId"] < 1:
        raise ValueError("Invalid request identity")
    if task["kind"] == "catalogue":
        return f"user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&direction=desc&per_page=100&page={number}"
    base = "repos/" + repo_name(task.get("repo")) + "/actions/runs"
    if task["kind"] in ("jobs", "run"):
        run = str(task.get("run", ""))
        if not re.fullmatch(r"[0-9]+", run) or int(run) < 1:
            raise ValueError("Invalid run ID")
        if task["kind"] == "run":
            return f"{base}/{run}"
        return f"{base}/{run}/jobs?filter=latest&per_page=100&page={number}"
    status = "in_progress" if task["kind"] == "activity" else task.get("status", "recent")
    if status == "recent":
        return f"{base}?per_page=10"
    if status not in ACTIVE:
        raise ValueError("Invalid workflow status")
    return f"{base}?status={status}&per_page=100&page={number}"


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


def read_page(task):
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
        try:
            body = json.loads(raw_body) if raw_body.strip() else None
        except ValueError:
            if status < 400:
                raise
            body = None
        result["data"] = body
        if status >= 400 or code:
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            if status == 429 or result["remaining"] == 0 or result["retryAt"] or "rate limit" in message.lower() or "secondary rate" in message.lower():
                result.update(errorType="rate", error="GitHub rate limit")
            elif status == 401:
                result.update(errorType="auth", error="Authenticate with gh auth login")
            elif status in (403, 404):
                result.update(errorType="permission", error="Resource unavailable or Actions read permission missing")
            else:
                result.update(errorType="network", error="GitHub request failed")
            return result
        kind = task["kind"]
        if kind == "catalogue":
            if not isinstance(body, list):
                raise ValueError("Invalid repository response")
            if any(not isinstance(row, dict) for row in body):
                raise ValueError("Invalid repository entry")
            result["data"] = [{"repo": repo_name(row["full_name"]), "description": row.get("description") or "",
                               "archived": bool(row.get("archived")), "disabled": bool(row.get("disabled"))} for row in body]
        elif kind == "run":
            if not isinstance(body, dict) or str(body.get("id")) != str(task["run"]) or "status" not in body:
                raise ValueError("Invalid run response")
        else:
            key = "jobs" if kind == "jobs" else "workflow_runs"
            if not isinstance(body, dict) or not isinstance(body.get(key), list):
                raise ValueError("Invalid workflow response")
            if any(not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1 or not isinstance(row.get("status"), str) for row in body[key]):
                raise ValueError("Invalid workflow entry")
            if kind == "jobs" and any(not isinstance(row.get("steps", []), list) for row in body[key]):
                raise ValueError("Invalid job steps")
            result["data"] = body[key]
        if kind != "run" and not (kind == "summary" and task.get("status", "recent") == "recent"):
            result["nextPage"] = next_page(endpoint, headers)
    except FileNotFoundError:
        # ponytail: only Popen(["gh", ...]) raises this; PermissionError stays "network"
        result.update(errorType="setup", error="Install gh (GitHub CLI)")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        result.update(errorType="network", error="GitHub request timed out or returned invalid data")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("page",))
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()

    def cancelled(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, cancelled)
    task = None
    try:
        if len(args.targets) != 1:
            raise ValueError("page requires one JSON request")
        task = json.loads(args.targets[0])
        data = read_page(task)
        data["updated"] = datetime.now(timezone.utc).isoformat()
        print(json.dumps(data))
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "GitHub request timed out or returned invalid data"
        error = {"error": message}
        error["errorType"] = "network" if isinstance(exc, (subprocess.TimeoutExpired, OSError)) else "setup"
        if isinstance(task, dict) and type(task.get("requestId")) is int and task["requestId"] > 0:
            error["requestId"] = task["requestId"]
        print(json.dumps(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
