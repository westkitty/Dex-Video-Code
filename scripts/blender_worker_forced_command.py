#!/opt/homebrew/bin/python3
"""Restricted, single-contract Blender preview worker for Dex-Video-Code."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.umask(0o077)
HOME = Path.home()
BASE = HOME / ".local/share/dex-video-worker"
JOBS = BASE / "jobs"
ACTIVE = BASE / "active"
SOURCE = HOME / "Downloads/p7-3-second-light-20261107"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
FFMPEG = HOME / ".local/bin/ffmpeg"
FFPROBE = HOME / ".local/bin/ffprobe"
PINNED = {
    "lantern_sentinel.py": "f24341152923f4c7a625fd871f00c58bd92069456da1b73a4e5079c53f56fe68",
    "second_light.py": "a81d5e5e2b8af063f684b08d4d1a590c50a890fe2300428406db9bee3118a8c1",
    "performance.py": "f5e9fa0714d789762a0f53b35e4f391258eda5b043db77a2cdc1a39afaa21e89",
    "second-light.performance.json": "aedff86178407eff44c1fbff06f7949cddf61facfed1a2cfa20a71e68d2239b3",
}
SCHEMA = "blender-worker-request.v1"
RESPONSE = "blender-worker-response.v1"

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value) is not None

def check_source():
    if not BASE.is_dir() or BASE.is_symlink() or not JOBS.is_dir() or JOBS.is_symlink():
        raise ValueError("worker storage unavailable")
    if not SOURCE.is_dir() or SOURCE.is_symlink() or not BLENDER.is_file():
        raise ValueError("approved Blender installation or source unavailable")
    if not FFMPEG.is_file() or not FFPROBE.is_file():
        raise ValueError("approved media tools unavailable")
    for name, expected in PINNED.items():
        path = SOURCE / name
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise ValueError("approved source changed: " + name)

def identity():
    return {
        "worker_id": "dex_blender_bigmac_v1",
        "hostname": "bigmac",
        "platform": "darwin",
        "arch": "arm64",
        "blender_version": "5.2.3",
        "worker_script_sha256": PINNED["second_light.py"],
        "policy_version": "restricted_ssh_v1",
        "observed_at": stamp(),
    }

def emit(operation, request, state, **extras):
    worker_identity = extras.pop("_worker_identity", None)
    response = {
        "schema_version": RESPONSE,
        "request_id": request["request_id"],
        "operation": operation,
        "state": state,
        "worker": worker_identity if worker_identity is not None else identity(),
    }
    response.update(extras)
    print(json.dumps(response, separators=(",", ":")), flush=True)

def save_json(path, obj):
    handle, temporary = tempfile.mkstemp(prefix=".state-", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("requested job data unavailable")
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)

def job_dir(job_id):
    if not valid_id(job_id):
        raise ValueError("invalid job id")
    path = JOBS / job_id
    if path.is_symlink():
        raise ValueError("job path is a symlink")
    return path

def request_check(req):
    if not isinstance(req, dict) or req.get("schema_version") != SCHEMA:
        raise ValueError("invalid worker schema")
    if not valid_id(req.get("request_id")):
        raise ValueError("invalid request id")
    op = req.get("operation")
    if op == "health":
        if set(req) != {"schema_version", "request_id", "operation"}:
            raise ValueError("unexpected health fields")
    elif op in ("status", "read-receipt"):
        if set(req) != {"schema_version", "request_id", "operation", "job_id"} or not valid_id(req["job_id"]):
            raise ValueError("invalid job lookup")
    elif op == "submit-approved-job":
        required = {"schema_version", "request_id", "operation", "job_id", "approved_contract_id",
                    "contract_sha256", "render_quality", "frame_start", "frame_end", "director_commit"}
        if set(req) != required or not valid_id(req.get("job_id")):
            raise ValueError("invalid submit structure")
        if req["approved_contract_id"] != "the_second_light_v1" or req["contract_sha256"] != PINNED["second-light.performance.json"]:
            raise ValueError("unapproved performance contract")
        if req["render_quality"] not in ("interaction", "preview"):
            raise ValueError("unsupported render quality")
        a, b = req["frame_start"], req["frame_end"]
        if type(a) is not int or type(b) is not int or not 1 <= a <= b <= 144 or b - a + 1 > 48:
            raise ValueError("unsupported frame range")
        if not isinstance(req["director_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", req["director_commit"]):
            raise ValueError("invalid source revision")
    else:
        raise ValueError("unknown worker operation")
    return op

def send_status(req, operation):
    folder = job_dir(req["job_id"])
    state = read_json(folder / "state.json")
    if operation == "status":
        emit(operation, req, state["state"], job_id=req["job_id"])
        return
    if state["state"] != "SUCCEEDED":
        raise ValueError("receipt unavailable for unfinished job")
    receipt = read_json(folder / "receipt.json")
    output = BASE / receipt["output_relative_path"]
    if output.is_symlink() or not output.is_file() or output.stat().st_size != receipt["output_bytes"] or digest(output) != receipt["output_sha256"]:
        raise ValueError("output readback failed")
    receipt["request_id"] = req["request_id"]
    verified_identity = identity()
    receipt["worker"] = verified_identity
    emit(operation, req, "SUCCEEDED", job_id=req["job_id"], receipt=receipt, _worker_identity=verified_identity)

def submit(req):
    check_source()
    if shutil.disk_usage(BASE).free < 5 * 1024 ** 3:
        raise ValueError("worker storage admission failed")
    folder = job_dir(req["job_id"])
    if folder.exists():
        original = read_json(folder / "request.json")
        fields = ["job_id", "approved_contract_id", "contract_sha256", "render_quality",
                  "frame_start", "frame_end", "director_commit"]
        if any(req[x] != original[x] for x in fields):
            raise ValueError("existing job id is bound to another request")
        state = read_json(folder / "state.json")["state"]
        emit("submit-approved-job", req, state, job_id=req["job_id"])
        return
    try:
        ACTIVE.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError("another Blender job is active")
    try:
        folder.mkdir(mode=0o700)
        save_json(folder / "request.json", req)
        save_json(folder / "state.json", {"state": "QUEUED", "updated_at": stamp()})
        (ACTIVE / "job_id").write_text(req["job_id"], encoding="utf-8")
        with (folder / "runner.log").open("ab") as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--run-job", req["job_id"]],
                             cwd=str(BASE), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             close_fds=True, start_new_session=True)
    except Exception:
        # Preserve job evidence; remove only our unlaunched active reservation.
        (ACTIVE / "job_id").unlink(missing_ok=True)
        ACTIVE.rmdir()
        raise
    emit("submit-approved-job", req, "QUEUED", job_id=req["job_id"])

def run_job(job_id):
    folder = job_dir(job_id)
    req = read_json(folder / "request.json")
    request_check(req)
    check_source()
    save_json(folder / "state.json", {"state": "RUNNING", "updated_at": stamp()})
    start, end = req["frame_start"], req["frame_end"]
    frames = folder / "frames"
    frames.mkdir(mode=0o700)
    command = [str(BLENDER), "--background", "--threads", "2", "--python", str(SOURCE / "second_light.py"),
               "--", "--output-root", str(folder), "--output-dir", str(frames),
               "--performance", str(SOURCE / "second-light.performance.json"),
               "--quality", req["render_quality"], "--start-frame", str(start), "--end-frame", str(end)]
    subprocess.run(command, cwd=str(SOURCE), stdin=subprocess.DEVNULL, check=True, timeout=180)
    expected_frames = {f"frame_{frame:04d}.png" for frame in range(start, end + 1)}
    actual_frames = {p.name for p in frames.glob("frame_*.png")}
    if actual_frames != expected_frames:
        raise ValueError("rendered frame inventory mismatch")
    temp_mp4 = folder / "encoded-partial.mp4"
    final_mp4 = folder / "master.mp4"
    subprocess.run([str(FFMPEG), "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-n",
                    "-framerate", "24", "-start_number", str(start), "-i", str(frames / "frame_%04d.png"),
                    "-frames:v", str(end - start + 1), "-c:v", "libx264", "-threads", "2",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temp_mp4)],
                   stdin=subprocess.DEVNULL, check=True, timeout=45)
    metadata = json.loads(subprocess.check_output(
        [str(FFPROBE), "-v", "error", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration",
         "-of", "json", str(temp_mp4)], timeout=15))
    video = [v for v in metadata["streams"] if v.get("codec_name") == "h264"]
    dims = (320, 180) if req["render_quality"] == "interaction" else (640, 360)
    if len(metadata["streams"]) != 1 or len(video) != 1 or (video[0].get("width"), video[0].get("height")) != dims or video[0].get("nb_frames") != str(end-start+1) or video[0].get("r_frame_rate") != "24/1":
        raise ValueError("encoded media properties mismatch")
    subprocess.run([str(FFMPEG), "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
                    "-i", str(temp_mp4), "-f", "null", "-"], stdin=subprocess.DEVNULL, check=True, timeout=40)
    os.link(temp_mp4, final_mp4)
    temp_mp4.unlink()
    receipt = {
        "schema_version": "blender-worker-receipt.v1",
        "job_id": job_id,
        "request_id": req["request_id"],
        "state": "SUCCEEDED",
        "worker": identity(),
        "contract_id": req["approved_contract_id"],
        "contract_sha256": req["contract_sha256"],
        "output_relative_path": f"jobs/{job_id}/master.mp4",
        "output_sha256": digest(final_mp4),
        "output_bytes": final_mp4.stat().st_size,
        "render_quality": req["render_quality"],
        "frame_start": start,
        "frame_end": end,
        "video": {"codec": "h264", "width": dims[0], "height": dims[1], "fps": 24,
                  "frame_count": end - start + 1, "audio": False, "subtitles": False},
        "evidence_scope": "WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK",
    }
    save_json(folder / "receipt.json", receipt)
    save_json(folder / "state.json", {"state": "SUCCEEDED", "updated_at": stamp()})

def main():
    if os.environ.get("SSH_ORIGINAL_COMMAND", ""):
        raise ValueError("SSH command execution is forbidden")
    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        try:
            run_job(sys.argv[2])
        except Exception as error:
            folder = job_dir(sys.argv[2])
            save_json(folder / "state.json", {"state": "FAILED", "updated_at": stamp(),
                                                    "reason": type(error).__name__})
            raise
        finally:
            if ACTIVE.is_dir() and (ACTIVE / "job_id").is_file() and (ACTIVE / "job_id").read_text() == sys.argv[2]:
                (ACTIVE / "job_id").unlink()
                ACTIVE.rmdir()
        return
    if len(sys.argv) != 1:
        raise ValueError("unexpected worker arguments")
    raw = sys.stdin.buffer.read(4097)
    if not raw or len(raw) > 4096:
        raise ValueError("worker request exceeds the strict input limit")
    req = json.loads(raw)
    operation = request_check(req)
    if operation == "health":
        try:
            check_source()
            admitted = shutil.disk_usage(BASE).free >= 5 * 1024 ** 3 and not ACTIVE.exists()
            emit(operation, req, "READY" if admitted else "BLOCKED", admitted=admitted)
        except ValueError:
            emit(operation, req, "BLOCKED", admitted=False, reason="worker source or tool admission failed")
    elif operation == "submit-approved-job":
        submit(req)
    else:
        send_status(req, operation)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("WORKER_REJECTED:" + type(error).__name__ + ":" + str(error), file=sys.stderr)
        sys.exit(3)
