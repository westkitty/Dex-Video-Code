import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "transfer_verified_file.py"
FAKE_SSH = r'''#!/usr/bin/env python3
import base64,hashlib,json,os,sys
args=sys.argv[1:]
if "StrictHostKeyChecking=yes" not in args or "BatchMode=yes" not in args:
    raise SystemExit("strict SSH options missing")
marker=os.environ.get("SSH_CALLED_MARKER")
if marker: open(marker,"w").write("yes")
if os.environ.get("SSH_MODE")=="symlink":
    raise SystemExit("remote source contains a symlink")
data=base64.b64decode(os.environ["REMOTE_BYTES_B64"])
print(json.dumps({"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}))
'''
FAKE_SCP = r'''#!/usr/bin/env python3
import base64,os,sys
args=sys.argv[1:]
if "StrictHostKeyChecking=yes" not in args or "BatchMode=yes" not in args:
    raise SystemExit("strict SCP options missing")
marker=os.environ.get("SCP_CALLED_MARKER")
if marker: open(marker,"w").write("yes")
destination=args[-1]
data=base64.b64decode(os.environ["REMOTE_BYTES_B64"])
mode=os.environ.get("SCP_MODE","success")
if mode=="corrupt": data += b"corrupt"
if mode=="interrupt":
    open(destination,"wb").write(data[:max(1,len(data)//2)])
    raise SystemExit(42)
open(destination,"wb").write(data)
'''


class VerifiedTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.write_executable(self.bin / "ssh", FAKE_SSH)
        self.write_executable(self.bin / "scp", FAKE_SCP)
        self.destination_root = self.base / "downloads"
        self.destination_root.mkdir()
        self.data = b"original exact master bytes\x00\x01" * 128
        self.env = os.environ.copy()
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["REMOTE_BYTES_B64"] = base64.b64encode(self.data).decode()
        self.env.pop("SCP_MODE", None)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_executable(path, content):
        path.write_text(content)
        path.chmod(0o700)

    @property
    def destination(self):
        return self.destination_root / "master.mp4"

    @property
    def receipt(self):
        return self.destination_root / "master.mp4.transfer-receipt.json"

    def command(self, **overrides):
        values = {
            "--source-host": "testhost",
            "--source-user": "andrew",
            "--source-root": "/approved/export",
            "--source-path": "/approved/export/master.mp4",
            "--destination-root": str(self.destination_root),
            "--destination": str(self.destination),
            "--sha256": hashlib.sha256(self.data).hexdigest(),
            "--bytes": str(len(self.data)),
        }
        values.update(overrides)
        args = [sys.executable, str(SCRIPT)]
        for key, value in values.items():
            args.extend((key, str(value)))
        return args

    def run_helper(self, *, env=None, **overrides):
        return subprocess.run(
            self.command(**overrides), env=env or self.env,
            capture_output=True, text=True, timeout=20,
        )

    def test_verified_scp_finalizes_without_overwrite_and_writes_receipt(self):
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o600)
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["status"], "SCP_VERIFIED")
        self.assertEqual(receipt["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertIn("StrictHostKeyChecking=yes", receipt["host_key_policy"])

        rerun = self.run_helper()
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(json.loads(rerun.stdout)["status"], "SCP_VERIFIED")

    def test_remote_checksum_mismatch_stops_before_scp(self):
        marker = self.base / "scp-called"
        env = self.env.copy()
        env["SCP_CALLED_MARKER"] = str(marker)
        result = self.run_helper(env=env, **{"--sha256": "0" * 64})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote source byte count or SHA-256", result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(self.destination.exists())

    def test_corrupt_download_is_not_finalized(self):
        env = self.env.copy()
        env["SCP_MODE"] = "corrupt"
        result = self.run_helper(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("downloaded bytes do not match", result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(list(self.destination_root.glob(".master.mp4.transfer-*")), [])

    def test_interrupted_scp_can_be_retried_cleanly(self):
        interrupted = self.env.copy()
        interrupted["SCP_MODE"] = "interrupt"
        result = self.run_helper(env=interrupted)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination_root.glob(".master.mp4.transfer-*")), [])

        retried = self.run_helper()
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(self.destination.read_bytes(), self.data)

    def test_remote_path_traversal_is_rejected_before_ssh(self):
        marker = self.base / "ssh-called"
        env = self.env.copy()
        env["SSH_CALLED_MARKER"] = str(marker)
        result = self.run_helper(env=env, **{"--source-path": "/approved/export/../secret.mp4"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical absolute path", result.stderr)
        self.assertFalse(marker.exists())

    def test_remote_symlink_probe_failure_stops_before_scp(self):
        marker = self.base / "scp-called"
        env = self.env.copy()
        env["SSH_MODE"] = "symlink"
        env["SCP_CALLED_MARKER"] = str(marker)
        result = self.run_helper(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote source probe failed", result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(self.destination.exists())

    def test_symlink_destination_root_is_rejected(self):
        real_root = self.base / "real-downloads"
        real_root.mkdir()
        link_root = self.base / "linked-downloads"
        link_root.symlink_to(real_root, target_is_directory=True)
        result = self.run_helper(**{
            "--destination-root": str(link_root),
            "--destination": str(link_root / "master.mp4"),
        })
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("destination root", result.stderr)
        self.assertEqual(list(real_root.iterdir()), [])

    def test_existing_different_destination_is_never_overwritten(self):
        original = b"user's unrelated existing file"
        self.destination.write_bytes(original)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing overwrite", result.stderr)
        self.assertEqual(self.destination.read_bytes(), original)

    def test_matching_existing_destination_can_receive_recovery_receipt(self):
        self.destination.write_bytes(self.data)
        marker = self.base / "scp-called"
        env = self.env.copy()
        env["SCP_CALLED_MARKER"] = str(marker)
        result = self.run_helper(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(json.loads(self.receipt.read_text())["status"], "DESTINATION_ALREADY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
