import unittest
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import actions


class ActionsTest(unittest.TestCase):
    def test_validation(self):
        for value in ["../x", "a/..", "-R", "a/b/c", "a/b?x", "a/b;touch x"]:
            with self.assertRaises(ValueError):
                actions.repo_name(value)
        self.assertEqual(actions.repo_name("olafkfreund/nixarchy"), "olafkfreund/nixarchy")

    def test_cancellation_reaps_gh(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "gh"
            pidfile = Path(directory) / "pid"
            # The rename is the readiness signal: the pid file is never seen half-written.
            fake.write_text(f"#!{sys.executable}\nimport os,time\nopen({str(pidfile)!r}+'.tmp','w').write(str(os.getpid()))\n"
                            f"os.replace({str(pidfile)!r}+'.tmp',{str(pidfile)!r})\ntime.sleep(30)\n")
            fake.chmod(0o700)
            process = subprocess.Popen([sys.executable, "actions.py", "page", '{"kind":"catalogue","requestId":1}'], env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]}, stdout=subprocess.PIPE)
            try:
                # ponytail: 30 s is a hang guard matching the fake's sleep, not a start-up budget
                deadline = time.monotonic() + 30
                while not pidfile.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists(), "actions.py exited before starting gh" if process.poll() is not None else "Fake gh did not start")
                child = int(pidfile.read_text())
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=3)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()


class PageTest(unittest.TestCase):
    def test_headers_pagination_and_single_call(self):
        # Jobs pages still follow pagination; unfinished-status pages don't (#30).
        task = {"kind":"jobs", "repo":"a/b", "run":"5", "page":1, "requestId":3}
        output = ('HTTP/1.1 100 Continue\r\n\r\nHTTP/2.0 200 OK\r\n'
                  'X-RateLimit-Remaining: 42\r\nX-RateLimit-Reset: 1700000000\r\n'
                  'Authorization: must-not-escape\r\n'
                  'Link: <https://api.github.com/repos/a/b/actions/runs/5/jobs?filter=latest&per_page=100&page=2>; rel="next"\r\n\r\n'
                  '{"jobs":[{"id":7,"status":"in_progress"}]}')
        with patch.object(actions, "request", return_value=(output, "", 0)) as request:
            result = actions.read_page(task)
            self.assertEqual(request.call_count, 1)
            self.assertTrue(request.call_args.kwargs["include"])
            self.assertEqual(result["nextPage"], 2)
            self.assertEqual(result["remaining"], 42)
            self.assertEqual(result["resetAt"], 1700000000000)
            self.assertEqual(result["requestId"], 3)
            self.assertNotIn("must-not-escape", json.dumps(result))

    def test_api_errors_keep_metadata(self):
        for status, message, extra, expected in [
            (403, "API rate limit exceeded", "X-RateLimit-Remaining: 0\nX-RateLimit-Reset: 1700000000\n", "rate"),
            (429, "slow down", "Retry-After: 60\n", "rate"),
            (403, "secondary rate limit", "", "rate"),
            (401, "Bad credentials", "", "auth"),
            (403, "Resource not accessible", "", "permission"),
            (404, "Not found", "", "permission"),
            (502, "Unavailable", "", "network")]:
            with self.subTest(status=status, message=message), patch.object(actions, "request", return_value=(
                    f"HTTP/2.0 {status} Error\n{extra}\n" + json.dumps({"message":message}), "gh failed", 1)):
                result = actions.read_page({"kind":"catalogue", "requestId":1})
                self.assertEqual(result["errorType"], expected)
                self.assertEqual(result["httpStatus"], status)
                if "Retry-After" in extra:
                    self.assertGreater(result["retryAt"], time.time() * 1000)
                if "Remaining" in extra:
                    self.assertEqual(result["remaining"], 0)

    def test_validation_and_broken_responses(self):
        for task in [{"kind":"url"}, {"kind":"catalogue", "page":0, "requestId":1},
                     {"kind":"activity", "repo":"a/..", "requestId":1},
                     {"kind":"jobs", "repo":"a/b", "run":"../x", "requestId":1},
                     {"kind":"summary", "repo":"a/b", "status":"evil", "requestId":1}]:
            with self.assertRaises(ValueError):
                actions.page_endpoint(task)
        for stdout in ["", "garbage", "HTTP/2.0 200 OK\n\ninvalid", "HTTP/2.0 200 OK\n\n{}"]:
            with patch.object(actions, "request", return_value=(stdout, "", 0)):
                self.assertEqual(actions.read_page({"kind":"catalogue", "requestId":1})["errorType"], "network")
        with self.assertRaises(ValueError):
            actions.next_page("user/repos?per_page=100&page=1", {"link":'<https://evil.test/user/repos?per_page=100&page=2>; rel="next"'})

    def test_missing_auth_and_non_json_rate_error(self):
        task = {"kind":"catalogue", "requestId":1}
        with patch.object(actions, "request", return_value=("", "Please run gh auth login", 1)):
            self.assertEqual(actions.read_page(task)["errorType"], "auth")
        with patch.object(actions, "request", return_value=("HTTP/2.0 429 Error\nRetry-After: 60\n\n<html>Slow down</html>", "failed", 1)):
            reply=actions.read_page(task)
            self.assertEqual(reply["errorType"], "rate")
            self.assertGreater(reply["retryAt"], time.time()*1000)

    def test_connection_failure_before_any_reply(self):
        refused = 'Get "https://api.github.com/user/repos": dial tcp: connect: connection refused'
        with patch.object(actions, "request", return_value=("", refused, 1)):
            reply = actions.read_page({"kind":"catalogue", "requestId":1})
        self.assertEqual(reply["errorType"], "network")
        self.assertEqual(reply["error"], "GitHub request failed; check connection and gh auth status")

    def test_missing_gh_is_setup_error(self):
        with patch.object(actions, "request", side_effect=FileNotFoundError("gh")):
            reply = actions.read_page({"kind":"catalogue", "requestId":1})
        self.assertEqual(reply["errorType"], "setup")
        self.assertEqual(reply["error"], "Install gh (GitHub CLI)")

    def test_page_missing_gh_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "actions.py", "page", '{"kind":"catalogue","requestId":3}'], env={**os.environ, "PATH": directory}, capture_output=True, text=True)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["requestId"], 3)
        self.assertEqual(reply["errorType"], "setup")

    def run_main(self, *argv):
        output = io.StringIO()
        with patch.object(sys, "argv", ["actions.py", *argv]), contextlib.redirect_stdout(output):
            code = actions.main()
        return code, json.loads(output.getvalue())

    def test_page_error_echoes_request_id(self):
        self.assertEqual(self.run_main("page", '{"kind":"url","requestId":7}'),
                         (1, {"error": "Invalid page operation", "errorType": "setup", "requestId": 7}))

    def test_page_unparseable_request_has_no_id(self):
        code, reply = self.run_main("page", "not-json")
        self.assertEqual(code, 1)
        self.assertNotIn("requestId", reply)
        self.assertEqual(reply["errorType"], "setup")

    def test_recent_history_does_not_follow_pagination(self):
        with patch.object(actions, "request", return_value=('HTTP/2.0 200 OK\nLink: <https://evil.test/>; rel="next"\n\n{"workflow_runs":[]}', "", 0)):
            result = actions.read_page({"kind":"summary", "repo":"a/b", "status":"recent", "requestId":1})
            self.assertEqual(result["nextPage"], 0)
            self.assertEqual(result["error"], "")

    def status_page(self, task, body):
        status = task.get("status", "in_progress")
        link = f'Link: <https://api.github.com/repos/a/b/actions/runs?status={status}&per_page=100&page=2>; rel="next"\n'
        with patch.object(actions, "request", return_value=("HTTP/2.0 200 OK\n" + link + "\n" + json.dumps(body), "", 0)):
            return actions.read_page(task)

    def test_summary_status_page_does_not_follow_next(self):
        result = self.status_page({"kind":"summary", "repo":"a/b", "status":"queued", "requestId":1},
                                  {"total_count":2000, "workflow_runs":[{"id":7,"status":"queued"}]})
        self.assertEqual((result["errorType"], result["nextPage"], result.get("total")), ("", 0, 2000))

    def test_activity_page_does_not_follow_next(self):
        result = self.status_page({"kind":"activity", "repo":"a/b", "requestId":1},
                                  {"total_count":250, "workflow_runs":[{"id":7,"status":"in_progress"}]})
        self.assertEqual((result["errorType"], result["nextPage"], result.get("total")), ("", 0, 250))

    def test_missing_total_count_is_network_error(self):
        for body in [{"workflow_runs":[]}, {"total_count":-1, "workflow_runs":[]}, {"total_count":"9", "workflow_runs":[]}]:
            with self.subTest(body=body):
                result = self.status_page({"kind":"summary", "repo":"a/b", "status":"queued", "requestId":1}, body)
                self.assertEqual(result["errorType"], "network")

    def test_recent_has_no_total(self):
        result = self.status_page({"kind":"summary", "repo":"a/b", "status":"recent", "requestId":1},
                                  {"total_count":90000, "workflow_runs":[]})
        self.assertEqual(result["errorType"], "")
        self.assertNotIn("total", result)

    def test_bad_steps_reject_the_page(self):
        task = {"kind": "jobs", "repo": "a/b", "run": "7", "requestId": 1}
        for steps in ([None], ["x"], [1], None):
            with self.subTest(steps=steps), patch.object(actions, "request", return_value=(
                    "HTTP/2.0 200 OK\n\n" + json.dumps({"jobs": [{"id": 8, "status": "completed", "steps": steps}]}), "", 0)):
                self.assertEqual(actions.read_page(task)["errorType"], "network")
        with patch.object(actions, "request", return_value=(
                "HTTP/2.0 200 OK\n\n" + json.dumps({"jobs": [{"id": 8, "status": "completed", "steps": [{"name": "a\nb"}]}]}), "", 0)):
            result = actions.read_page(task)
        self.assertEqual(result["errorType"], "")
        self.assertEqual(result["data"][0]["steps"][0]["name"], "a b")

    def test_account_page(self):
        task = {"kind": "account", "requestId": 1}
        for repo in (None, ""):
            with self.subTest(repo=repo):
                self.assertEqual(actions.page_endpoint(dict(task, repo=repo)), "user")
        self.assertEqual(actions.page_endpoint(task), "user")
        for bad in (dict(task, repo="a/.."), {"kind": "account"},
                    dict(task, requestId=None), dict(task, requestId=0), dict(task, requestId=True)):
            with self.subTest(task=bad), self.assertRaises(ValueError):
                actions.page_endpoint(bad)
        link = 'Link: <https://api.github.com/user?page=2>; rel="next"\n'
        for body in ({"login": "octo-cat", "id": 1, "email": "x"}, {"login": "mona-cat_octo", "email": "x"}, {}, {"login": 1},
                     {"login": "a b", "email": "x"}, {"login": "a\n"}, {"login": ""}):
            with self.subTest(body=body), patch.object(actions, "request", return_value=(
                    "HTTP/2.0 200 OK\n" + link + "\n" + json.dumps(body), "", 0)):
                result = actions.read_page(task)
            self.assertEqual(result["nextPage"], 0)
            if body.get("login") in ("octo-cat", "mona-cat_octo"):
                self.assertEqual(result["errorType"], "")
                self.assertEqual(result["data"], {"login": body["login"]})
            else:
                self.assertEqual(result["errorType"], "network")
                self.assertIsNone(result["data"])
        # HTTP 200 but gh exits non-zero: the profile must not ride along on the error.
        with patch.object(actions, "request", return_value=(
                'HTTP/2.0 200 OK\n\n{"login":"octo","email":"x@y"}', "", 1)):
            result = actions.read_page(task)
        self.assertEqual(result["errorType"], "network")
        self.assertIsNone(result["data"])

    def test_catalogue_403_message(self):
        for status in (403, 404):
            with self.subTest(status=status), patch.object(actions, "request", return_value=(
                    f'HTTP/2.0 {status} Error\n\n{{"message":"unavailable"}}', "", 1)):
                result = actions.read_page({"kind": "catalogue", "requestId": 1})
            self.assertEqual(result["errorType"], "permission")
            self.assertEqual(result["error"], "Repository list unavailable; token cannot read your repositories")
        with patch.object(actions, "request", return_value=(
                'HTTP/2.0 403 Error\n\n{"message":"unavailable"}', "", 1)):
            result = actions.read_page({"kind": "summary", "repo": "a/b", "requestId": 1})
        self.assertEqual(result["error"], "Resource unavailable or Actions read permission missing")

    def test_page_text_is_plain(self):
        # #32: fork PRs control these strings; bidi overrides, controls and line breaks must not reach QML.
        emoji, persian = "👨‍👩‍👧", "می‌خواهم"
        run = {"id": 7, "status": "completed", "conclusion": "failure", "html_url": "https://github.com/a/b/actions/runs/7",
               "name": "a\tb", "display_title": "fix‮ sseccus\ntwo", "head_branch": "ma​in\x07"}
        plain_run = {"name": "a b", "display_title": "fix sseccus two", "head_branch": "main"}

        def page(task, body):
            with patch.object(actions, "request", return_value=("HTTP/2.0 200 OK\n\n" + json.dumps(body), "", 0)):
                result = actions.read_page(dict(task, requestId=1))
            self.assertEqual(result["errorType"], "", task)
            return result["data"]

        for task in [{"kind": "activity", "repo": "a/b"}, {"kind": "summary", "repo": "a/b", "status": "queued"},
                     {"kind": "summary", "repo": "a/b", "status": "recent"}]:
            with self.subTest(task=task):
                row = page(task, {"total_count": 1, "workflow_runs": [dict(run)]})[0]
                self.assertEqual(row, dict(run, **plain_run))
        self.assertEqual(page({"kind": "run", "repo": "a/b", "run": "7"}, dict(run)), dict(run, **plain_run))
        self.assertEqual(page({"kind": "run", "repo": "a/b", "run": "7"}, dict(run, display_title=emoji))["display_title"], emoji)

        job = {"id": 8, "status": "completed", "conclusion": "success", "html_url": "https://github.com/a/b/actions/runs/7/job/8",
               "name": "x\x1b[31my", "steps": [{"number": 1, "status": "completed", "name": "s t"}]}
        self.assertEqual(page({"kind": "jobs", "repo": "a/b", "run": "7"}, {"jobs": [job]})[0],
                         dict(job, name="x[31my", steps=[{"number": 1, "status": "completed", "name": "s t"}]))

        repos = page({"kind": "catalogue"}, [{"full_name": "o/r", "description": "d⁦e\r\nf"},
                                              {"full_name": "o/s", "description": persian}])
        self.assertEqual([(r["repo"], r["description"]) for r in repos], [("o/r", "de f"), ("o/s", persian)])


class WriteTest(unittest.TestCase):
    def task(self, action="rerun"):
        return {"action": action, "repo": "o/r", "run": "5", "requestId": 1}

    def reply(self, status, message="", headers="", code=1):
        body = json.dumps({"message": message}) if message else "{}"
        return f"HTTP/2.0 {status} Reply\n{headers}\n{body}", "", code

    def test_each_action_posts_fixed_path(self):
        for action, suffix in (("rerun", "rerun"), ("rerun-failed", "rerun-failed-jobs"), ("cancel", "cancel")):
            with self.subTest(action=action), patch.object(actions, "request", return_value=self.reply(202, code=0)) as request:
                actions.write_action(self.task(action))
                request.assert_called_once_with(f"repos/o/r/actions/runs/5/{suffix}", include=True, method="POST")

    def test_success_is_ok(self):
        for status in (201, 202):
            with self.subTest(status=status), patch.object(actions, "request", return_value=self.reply(status, code=0)):
                result = actions.write_action(self.task())
                self.assertTrue(result["ok"])
                self.assertEqual((result["errorType"], result["error"]), ("", ""))

    def test_refusals(self):
        for status, prefix in ((403, "Needs Actions write on o/r: "), (404, "Needs Actions write on o/r: "),
                               (409, "GitHub refused: "), (422, "GitHub refused: ")):
            with self.subTest(status=status), patch.object(actions, "request", return_value=self.reply(status, "GitHub says no")):
                result = actions.write_action(self.task())
                self.assertEqual(result["errorType"], "refused")
                self.assertEqual(result["error"], prefix + "GitHub says no")
                self.assertNotEqual(result["errorType"], "permission")

    def test_rate_limits(self):
        for status, message, headers in ((403, "secondary rate limit", ""), (429, "slow down", "Retry-After: 60\n"),
                                         (403, "slow down", "X-RateLimit-Remaining: 0\n")):
            with self.subTest(status=status, headers=headers), patch.object(actions, "request", return_value=self.reply(status, message, headers)):
                result = actions.write_action(self.task())
                self.assertEqual(result["errorType"], "rate")
                self.assertEqual(result["error"], "GitHub rate limit")
                if status == 429:
                    self.assertGreater(result["retryAt"], time.time() * 1000)

    def test_auth(self):
        with patch.object(actions, "request", return_value=self.reply(401, "Bad credentials")):
            result = actions.write_action(self.task())
            self.assertEqual((result["errorType"], result["error"]), ("auth", "Authenticate with gh auth login"))
        with patch.object(actions, "request", return_value=("", "Please run gh auth login", 1)):
            result = actions.write_action(self.task())
            self.assertEqual((result["errorType"], result["error"]), ("auth", "Authenticate with gh auth login"))

    def test_unknown_outcomes(self):
        unknown = "Outcome unknown; check GitHub before retrying"
        for response in (self.reply(500, "Server error"), ("", "failed", 1),
                         ("HTTP/2.0 201 Created\n\ninvalid", "", 0), self.reply(302)):
            with self.subTest(response=response), patch.object(actions, "request", return_value=response):
                result = actions.write_action(self.task())
                self.assertEqual((result["errorType"], result["error"]), ("unknown", unknown))
        with patch.object(actions, "request", side_effect=subprocess.TimeoutExpired("gh", 25)):
            result = actions.write_action(self.task())
            self.assertEqual((result["errorType"], result["error"]), ("unknown", unknown))
        with patch.object(actions, "request", side_effect=FileNotFoundError("gh")):
            result = actions.write_action(self.task())
            self.assertEqual((result["errorType"], result["error"]), ("setup", "Install gh (GitHub CLI)"))

    def test_message_is_plain_and_capped(self):
        with patch.object(actions, "request", return_value=self.reply(403, "bad\x1b\n\u202ego")):
            result = actions.write_action(self.task())
            self.assertEqual(result["error"], "Needs Actions write on o/r: bad go")
        with patch.object(actions, "request", return_value=self.reply(403, "x" * 500)):
            result = actions.write_action(self.task())
            self.assertEqual(result["error"], "Needs Actions write on o/r: " + "x" * 120)

    def test_validation(self):
        task = self.task()
        invalid = ([dict(task, action=action) for action in ("other", "../x")] +
                   [dict(task, repo=repo) for repo in ("-R", "a/b;touch x")] +
                   [dict(task, run=run) for run in ("0", "1a", "")] +
                   [{key: value for key, value in task.items() if key != "requestId"}] +
                   [dict(task, requestId=value) for value in (0, True)])
        with patch.object(actions, "request") as request:
            for bad in invalid:
                with self.subTest(task=bad), self.assertRaises(ValueError):
                    actions.write_action(bad)
            request.assert_not_called()

    def test_act_end_to_end_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "gh"
            argv = Path(directory) / "argv"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$GH_ARGV"\nprintf "HTTP/2.0 202 Accepted\\n\\n{}"\n')
            fake.chmod(0o700)
            command = [sys.executable, "actions.py", "act", '{"action":"cancel","repo":"o/r","run":"5","requestId":4}']
            result = subprocess.run(command, env={**os.environ, "PATH": directory, "GH_ARGV": str(argv)}, capture_output=True, text=True)
            reply = json.loads(result.stdout)
            self.assertEqual((reply["requestId"], reply["ok"]), (4, True))
            self.assertEqual(argv.read_text().splitlines(),
                             ["api", "--hostname", "github.com", "--include", "--method", "POST", "repos/o/r/actions/runs/5/cancel"])
            empty = Path(directory) / "empty"
            empty.mkdir()
            result = subprocess.run(command, env={**os.environ, "PATH": str(empty)}, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)["errorType"], "setup")

    def test_act_error_echoes_request_id(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["actions.py", "act", '{"action":"x","repo":"o/r","run":"5","requestId":9}']), contextlib.redirect_stdout(output):
            code = actions.main()
        self.assertEqual((code, json.loads(output.getvalue())),
                         (1, {"error": "Invalid action", "errorType": "setup", "requestId": 9}))


if __name__ == "__main__":
    unittest.main()
