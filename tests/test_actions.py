import unittest
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
    def test_pagination(self):
        with patch.object(actions, "api", side_effect=[{"jobs": list(range(100))}, {"jobs": [100]}]) as api:
            self.assertEqual(list(actions.pages("endpoint?filter=latest", "jobs")), list(range(101)))
            self.assertIn("&per_page=100&page=2", api.call_args.args[0])

    def test_repository_discovery_pages_and_affiliations(self):
        rows = [{"full_name": f"org/repo{i}", "description": None} for i in range(100)]
        with patch.object(actions, "api", side_effect=[rows, []]) as api:
            first = actions.repositories_page("1")
            self.assertEqual(first["nextPage"], 2)
            self.assertEqual(first["repos"][0]["repo"], "org/repo0")
            self.assertEqual(first["repos"][0]["description"], "")
            self.assertIn("affiliation=owner,collaborator,organization_member", api.call_args.args[0])
            self.assertEqual(actions.repositories_page("2")["nextPage"], 0)
        with self.assertRaises(ValueError):
            actions.repositories_page("0")

    def test_activity_uses_paginated_running_filter(self):
        with patch.object(actions, "pages", return_value=iter([{"id": 1}])) as pages:
            self.assertEqual(actions.activity("owner/repo"), {"repo": "owner/repo", "runs": [{"id": 1}], "active": 1})
            self.assertEqual(pages.call_args.args, ("repos/owner/repo/actions/runs?status=in_progress", "workflow_runs"))

    def test_active_runs_and_completion_race(self):
        active = {"id": 1, "status": "in_progress"}
        completed = {"id": 1, "status": "completed"}
        queued = {"id": 2, "status": "queued"}
        with patch.object(actions, "pages", side_effect=[[queued], [active], [], [], []]), patch.object(actions, "api", return_value={"workflow_runs": [completed]}):
            self.assertEqual(actions.runs("owner/repo"), [queued, completed])

    def test_partial_failure_preserves_other_repos(self):
        with patch.object(actions, "runs", side_effect=[RuntimeError("offline"), []]):
            data = actions.summary(["a/one", "b/two", "b/two"])
            self.assertEqual(data, [{"repo": "a/one", "error": "offline"}, {"repo": "b/two", "runs": [], "error": ""}])

    def test_deadline_stops_entire_scan(self):
        with patch.object(actions, "runs", side_effect=actions.DeadlineExceeded) as runs:
            with self.assertRaises(actions.DeadlineExceeded):
                actions.summary(["a/one", "b/two"])
            self.assertEqual(runs.call_count, 1)

    def test_validation(self):
        for value in ["../x", "a/..", "-R", "a/b/c", "a/b?x", "a/b;touch x"]:
            with self.assertRaises(ValueError):
                actions.repo_name(value)
        self.assertEqual(actions.repo_name("olafkfreund/nixarchy"), "olafkfreund/nixarchy")

    def test_cancellation_reaps_gh(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "gh"
            pidfile = Path(directory) / "pid"
            fake.write_text(f"#!{sys.executable}\nimport os,time\nopen({str(pidfile)!r},'w').write(str(os.getpid()))\ntime.sleep(30)\n")
            fake.chmod(0o700)
            process = subprocess.Popen([sys.executable, "actions.py", "summary", "owner/repo"], env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]}, stdout=subprocess.PIPE)
            try:
                for _ in range(100):
                    if pidfile.exists() and pidfile.read_text():
                        break
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists(), "Fake gh did not start")
                child = int(pidfile.read_text())
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=3)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_missing_gh_is_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "actions.py", "summary", "owner/repo"], env={**os.environ, "PATH": directory}, capture_output=True, text=True, check=True)
            self.assertIn("error", json.loads(result.stdout)["repos"][0])


if __name__ == "__main__":
    unittest.main()
