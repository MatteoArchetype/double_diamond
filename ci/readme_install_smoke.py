"""Exercise the README install and checkpoint recovery from a source ZIP."""
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd, timeout=60):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def python_in(venv):
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    with tempfile.TemporaryDirectory(prefix="double-diamond-install-") as temp:
        root = Path(temp)
        archive = root / "source.zip"
        with archive.open("wb") as output:
            subprocess.run(
                ["git", "archive", "--format=zip", "HEAD"],
                cwd=ROOT,
                stdout=output,
                check=True,
            )
        source = root / "source"
        source.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(source)

        venv = root / ".venv"
        run([sys.executable, "-m", "venv", venv], ROOT)
        app_python = python_in(venv)
        run(
            [app_python, "-m", "pip", "install", "--disable-pip-version-check",
             "-r", source / "requirements.txt"],
            source,
            timeout=180,
        )

        workspace = root / "research workspace"
        created = run(
            [
                app_python,
                "-c",
                "import sys; from dd_research_runtime.local_app import Workspace; "
                "print(Workspace(sys.argv[1]).create({'title':'Install smoke case',"
                "'question':'What remains unknown?','scope':'Test only',"
                "'max_visits':8,'max_alternatives':3}))",
                workspace,
            ],
            source,
        )
        case_id = created.stdout.strip()
        database = workspace / case_id / "research.sqlite"
        original_digest = hashlib.sha256(database.read_bytes()).digest()
        checkpoint = root / "recovery checkpoint.zip"
        run(
            [app_python, "-m", "dd_research_runtime.checkpoint_cli",
             "create", database, checkpoint],
            source,
        )
        inspected = run(
            [app_python, "-m", "dd_research_runtime.checkpoint_cli",
             "inspect", checkpoint],
            source,
        )
        assert json.loads(inspected.stdout)["ok"] is True
        restored = run(
            [app_python, "-m", "dd_research_runtime.checkpoint_cli",
             "restore-case", checkpoint, workspace],
            source,
        )
        restore_result = json.loads(restored.stdout)
        restored_id = restore_result["case_id"]
        assert restore_result["approval_granted"] is False
        assert hashlib.sha256(database.read_bytes()).digest() == original_digest

        process = subprocess.Popen(
            [
                str(app_python),
                "-m",
                "dd_research_runtime.local_app",
                "--workspace",
                str(workspace),
                "--port",
                "0",
                "--no-browser",
            ],
            cwd=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ready = queue.Queue()
        threading.Thread(
            target=lambda: ready.put(process.stdout.readline()),
            daemon=True,
        ).start()
        try:
            try:
                line = ready.get(timeout=30)
            except queue.Empty as exc:
                raise RuntimeError("The README app command did not start in 30 seconds.") from exc
            prefix = "Open your private local research workspace: "
            if not line.startswith(prefix):
                raise RuntimeError(
                    "The README app command failed to start: " + process.stderr.read()
                )
            launch_url = line[len(prefix):].strip()
            parsed = urlsplit(launch_url)
            token = parse_qs(parsed.fragment)["token"][0]
            with urlopen(launch_url, timeout=5) as response:
                assert response.status == 200 and b"Double Diamond" in response.read()
            catalog_url = urlunsplit(
                (parsed.scheme, parsed.netloc, "/api/catalog", "", "")
            )
            request = Request(
                catalog_url,
                headers={"Authorization": "Bearer " + token},
            )
            with urlopen(request, timeout=5) as response:
                catalog = json.load(response)
            assert {case["case_id"] for case in catalog["cases"]} == {
                case_id,
                restored_id,
            }
            assert any(case["case_id"] == restored_id for case in catalog["cases"])
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        print("README source-ZIP install and checkpoint recovery smoke passed.")


if __name__ == "__main__":
    main()
