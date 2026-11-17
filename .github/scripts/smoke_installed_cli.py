"""Exercise the installed CLI against a disposable local fixture, never publish."""

import argparse
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def require_installed(module_path, source_root):
    try:
        Path(module_path).resolve().relative_to(source_root.resolve())
    except ValueError:
        return
    raise RuntimeError("CLI smoke imported the source checkout instead of the installed package")


def require_completed(response, command):
    if (response.get("response_schema_version") != "0.1"
            or response.get("command") != command or response.get("status") != "completed"
            or response.get("error_code") is not None
            or not isinstance(response.get("result"), dict)
            or response["result"].get("run_id") != "ci-smoke"):
        raise RuntimeError(f"Installed CLI returned an unexpected {command} response")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    source_root = parser.parse_args().source_root.resolve()
    expected_version = (source_root / "VERSION").read_text(encoding="utf-8").strip()

    import validation

    require_installed(validation.__file__, source_root)
    if version("code2kb-agent-toolkit") != expected_version:
        raise RuntimeError("Installed distribution version does not match VERSION")
    cli = Path(sys.executable).parent / "code2kb"
    if not cli.is_file():
        raise RuntimeError("Installed code2kb console entry point is missing")

    spec = importlib.util.spec_from_file_location("ci_demo_fixture", source_root / "examples/create_demo.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"

    with tempfile.TemporaryDirectory(prefix="code2kb-installed-smoke-", dir=os.environ.get("RUNNER_TEMP")) as temporary:
        root = Path(temporary)
        project = fixture.build(root / "fixture")

        def run(*args):
            return subprocess.check_output(args, cwd=root, env=environment, text=True)

        run(str(cli), "--help")
        if expected_version not in run(str(cli), "--version"):
            raise RuntimeError("Installed CLI reports an unexpected version")
        checked = json.loads(run(str(cli), "check", "--project-root", str(project)))
        if checked.get("outline_modules") != 1 or checked.get("outline_entries") != 1:
            raise RuntimeError("Installed CLI did not check the expected fixture")

        # Exercise fcntl-backed local mutation without approval or publication.
        run("git", "init", "-q", str(project))
        run("git", "-C", str(project), "add", ".")
        run("git", "-C", str(project), "-c", "commit.gpgsign=false", "-c", "user.name=CI Fixture",
            "-c", "user.email=ci@example.invalid", "commit", "-qm", "Installed CLI smoke fixture")
        common = ("--project-root", str(project), "--run-id", "ci-smoke", "--output", "json")
        created = json.loads(run(str(cli), "run-create", *common, "--module-id", "example.order.query",
                                 "--release-id", "ci-smoke-unpublished"))
        status = json.loads(run(str(cli), "run-status", *common))
        require_completed(created, "run-create")
        require_completed(status, "run-status")
        if (project / "发布").exists():
            raise RuntimeError("CLI smoke unexpectedly created published output")
    print("Installed CLI smoke passed: isolated imports, version, check, local run-create/run-status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
