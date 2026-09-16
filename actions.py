"""Read-only GitHub Actions data, using gh's existing authentication."""
import argparse
import json
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone


ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")


class DeadlineExceeded(Exception):
    pass


def repo_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repository must be owner/name")
    if any(part in (".", "..") for part in value.split("/")):
        raise ValueError("Invalid repository")
    return value


def api(endpoint):
    child = subprocess.Popen(
        ["gh", "api", "--hostname", "github.com", endpoint],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = child.communicate(timeout=25)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    if child.returncode:
        error = stderr.lower()
        if "rate limit" in error or "http 429" in error:
            raise RuntimeError("GitHub rate limit; refresh will back off")
        if "auth login" in error or "http 401" in error:
            raise RuntimeError("Authenticate with gh auth login")
        if "http 403" in error or "http 404" in error:
            raise RuntimeError("Repository unavailable or Actions read permission missing")
        raise RuntimeError("GitHub request failed; check connection and gh auth status")
    return json.loads(stdout)


def pages(endpoint, key):
    page = 1
    while True:
        separator = "&" if "?" in endpoint else "?"
        data = api(f"{endpoint}{separator}per_page=100&page={page}")
        rows = data[key]
        if not isinstance(rows, list):
            raise ValueError("Unexpected GitHub response")
        yield from rows
        if len(rows) < 100:
            break
        page += 1


def runs(repo):
    base = f"repos/{repo_name(repo)}/actions/runs"
    found = {}
    for status in ACTIVE:
        for run in pages(f"{base}?status={status}", "workflow_runs"):
            found[run["id"]] = run
    # Include recent completions; querying them last resolves completion races.
    for run in api(f"{base}?per_page=10")["workflow_runs"]:
        found[run["id"]] = run
    return sorted(found.values(), key=lambda run: (run["status"] == "completed", -run["id"]))


def summary(repos):
    result = []
    for repo in dict.fromkeys(repo_name(value) for value in repos):
        try:
            result.append({"repo": repo, "runs": runs(repo), "error": ""})
        except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
            message = str(exc) if isinstance(exc, RuntimeError) else "Unable to read GitHub workflow data"
            result.append({"repo": repo, "error": message})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("summary", "jobs"))
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()
    # Bound the complete request, including all pages/repositories.
    def timed_out(*_):
        raise DeadlineExceeded()

    def cancelled(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGALRM, timed_out)
    signal.signal(signal.SIGTERM, cancelled)
    signal.alarm(90)
    try:
        if args.mode == "summary":
            data = {"repos": summary(args.targets)}
        else:
            if len(args.targets) != 2 or not args.targets[1].isdigit():
                raise ValueError("jobs requires owner/repo and numeric run ID")
            repo, run = repo_name(args.targets[0]), args.targets[1]
            data = {"jobs": list(pages(f"repos/{repo}/actions/runs/{run}/jobs?filter=latest", "jobs"))}
        data["updated"] = datetime.now(timezone.utc).isoformat()
        print(json.dumps(data))
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired, DeadlineExceeded) as exc:
        message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "GitHub request timed out or returned invalid data"
        print(json.dumps({"error": message}))
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
