"""Nonrendering contract tests for the fixed-command Blender worker."""
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "blender_worker_forced_command.py"
if not SCRIPT.exists():
    SCRIPT = Path.home() / ".local/share/dex-video-worker/entry.py"
spec = importlib.util.spec_from_file_location("dvc_restricted_worker", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class WorkerContractTests(unittest.TestCase):
    def setUp(self):
        self.base = {"schema_version":"blender-worker-request.v1",
                     "request_id":"unit_test_001","operation":"health"}

    def test_health_contract(self):
        self.assertEqual(worker.request_check(dict(self.base)), "health")

    def test_extra_fields_rejected(self):
        with self.assertRaises(ValueError):
            worker.request_check({**self.base, "shell":"sh"})

    def test_arbitrary_operation_rejected(self):
        with self.assertRaises(ValueError):
            worker.request_check({**self.base, "operation":"execute"})

    def test_job_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            worker.request_check({**self.base, "operation":"status","job_id":"../other"})

    def test_unapproved_contract_rejected(self):
        req = {**self.base, "operation":"submit-approved-job",
               "job_id":"test001", "approved_contract_id":"unknown",
               "contract_sha256":worker.PINNED["second-light.performance.json"],
               "render_quality":"interaction","frame_start":1,"frame_end":1,
               "director_commit":"a"*40}
        with self.assertRaises(ValueError):
            worker.request_check(req)

    def test_frame_budget_rejected(self):
        req = {**self.base, "operation":"submit-approved-job",
               "job_id":"test002", "approved_contract_id":"the_second_light_v1",
               "contract_sha256":worker.PINNED["second-light.performance.json"],
               "render_quality":"interaction","frame_start":1,"frame_end":49,
               "director_commit":"a"*40}
        with self.assertRaises(ValueError):
            worker.request_check(req)

    def test_forced_command_shell_rejected(self):
        env = os.environ.copy()
        env["SSH_ORIGINAL_COMMAND"] = "sh -c whoami"
        result = subprocess.run([sys.executable,str(SCRIPT)], input=b'{"schema_version":"blender-worker-request.v1","request_id":"unit_test_002","operation":"health"}', env=env, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(result.stdout)
        self.assertIn(b"SSH command execution is forbidden",result.stderr)

if __name__ == "__main__":
    unittest.main()
