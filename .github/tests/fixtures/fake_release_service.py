#!/usr/bin/env python3
"""Strictly local test doubles for the release CLIs. Unknown calls fail, never delegate."""

import base64
import hashlib
import json
import os
from pathlib import Path
import sys


root = Path(os.environ["FAKE_SERVICE"])
state = json.loads((root / "state.json").read_bytes())
version = state["version"]
tag = "v" + version
package = "code2kb-dsh"
dist_tag = "release-" + version
filename = f"{package}-{version}.tgz"
registry = "https://registry.npmjs.org"
repository = "Ethereal-Space-one/code2kb-agent-toolkit"
repo = "repos/" + repository
release_id = 71
endpoint = repo + f"/releases/{release_id}"
published = root / "registry" / filename
release = root / "release.json"
assets = root / "assets"
cmd, args = Path(sys.argv[0]).name, sys.argv[1:]


def journal(*event):
    with (root / "events.jsonl").open("a", encoding="utf-8") as out:
        print(json.dumps(event), file=out)


def npm():
    if args == ["--version"]:
        return print("11.12.1")
    journal("npm-write", *args)
    archive = Path(args[1])
    assert args == ["publish", str(archive), "--ignore-scripts", "--provenance",
                    "--access=public", "--registry=" + registry, "--tag=" + dist_tag]
    assert os.environ.get("npm_config_fetch_retries") == "0"
    assert archive.name == filename
    published.parent.mkdir(exist_ok=True)
    with published.open("xb") as output:  # write once; no overwrite
        output.write(archive.read_bytes())
    if state.get("npm_response_lost"):
        sys.exit(1)  # Service received the bytes, but the client saw failure.


def curl():
    assert "--output" in args and "--write-out" in args
    url = args[-1]
    if "--request" in args:
        journal("github-write", *args)
        name_arg = args[args.index("--data-binary") + 1]
        assert name_arg.startswith("@")
        p = Path(name_arg[1:])
        assert url == f"https://uploads.github.com/{endpoint}/assets?name={p.name}"
        assert args[args.index("--request") + 1] == "POST" and "@-" in args
        assert sys.stdin.readline().strip().lower() == "authorization: bearer fake"
        assert json.loads(release.read_bytes())["draft"]
        with (assets / p.name).open("xb") as dest:
            dest.write(p.read_bytes())
        obj = {"name": p.name, "size": p.stat().st_size, "state": "uploaded"}
        Path(args[args.index("--output") + 1]).write_text(json.dumps(obj))
        return print("201", end="")
    assert not ({"--data", "--data-binary", "-X"} & set(args))
    data, status = {}, "200"
    if url == registry + f"/-/package/{package}/dist-tags":
        data = {"latest": state["latest"]}
        if published.exists():
            data[dist_tag] = version
        data.update(state.get("extra_tags", {}))
    elif url == registry + f"/{package}/{version}":
        if state.get("registry_unavailable") or (published.exists() and state.get("post_write_read_fails")):
            status = "503"
        elif not published.exists():
            status = "404"
        else:
            integrity = "sha512-" + base64.b64encode(hashlib.sha512(published.read_bytes()).digest()).decode()
            data = {"name": package, "version": version, "gitHead": state["commit"],
                    "dist": {"integrity": integrity, "tarball": registry + f"/{package}/-/{filename}"}}
    elif url == registry + f"/{package}/-/{filename}" and published.exists():
        data = published.read_bytes()
    else:
        raise ValueError(f"Unexpected fake GET: {url}")
    Path(args[args.index("--output") + 1]).write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    print(status, end="")


def git():
    ref = "refs/tags/" + tag
    assert args == ["ls-remote", "--exit-code", f"https://github.com/{repository}.git", ref, ref + "^{}"]
    # Only output simulated annotated-tag data; no local or remote tag is made.
    print("1" * 40 + "\t" + ref)
    print(state.get("tag_commit", state["commit"]) + "\t" + ref + "^{}")


def records():
    return [{"id": i, "name": p.name, "size": p.stat().st_size, "state": "uploaded",
             "digest": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()}
            for i, p in enumerate(sorted(assets.iterdir()), start=100)]


def gh():
    assert args[0] == "api" and os.environ.get("GH_TOKEN") == "fake"
    a = args[1:]
    if "--method" in a:
        journal("github-write", *a)
    if a == [repo]:
        return {"permissions": {"push": state.get("push", True)}}
    if a == ["--paginate", "--slurp", repo + "/releases?per_page=100"]:
        # Match on page 2, not just the first page.
        return [[], [json.loads(release.read_bytes())] if release.exists() else []]
    if a == [repo + "/git/ref/tags/" + tag]:
        return {"object": {"type": "commit", "sha": state.get("tag_commit", state["commit"])}}
    if a == ["--method", "POST", repo + "/releases", "--input", "-"]:
        obj = json.load(sys.stdin)
        assert obj["draft"] is True and obj["make_latest"] == "false" and obj["tag_name"] == tag
        assert obj["target_commitish"] == state["commit"]
        obj.update({"id": release_id, "assets": [], "immutable": False})
        with release.open("x", encoding="utf-8") as out:
            json.dump(obj, out)
        assets.mkdir()
        return obj
    if a == [endpoint]:
        return json.loads(release.read_bytes())
    if a == ["--paginate", "--slurp", endpoint + "/assets?per_page=100"]:
        r = records()
        return [r[:2], r[2:]]
    if a[:2] == ["-H", "Accept: application/octet-stream"]:
        record, = (r for r in records() if a[2:] == [repo + "/releases/assets/" + str(r["id"])])
        phase = "draft" if json.loads(release.read_bytes())["draft"] else "public"
        journal("read-bytes", phase, record["name"])
        data = (assets / record["name"]).read_bytes()
        return data + b"bad" if state.get("corrupt_readback") else data
    if a == ["--method", "PATCH", endpoint, "--input", "-"]:
        assert json.load(sys.stdin) == {"draft": False, "make_latest": "false"}
        obj = json.loads(release.read_bytes())
        assert obj["draft"] is True
        obj.update({"draft": False, "immutable": True})
        release.write_text(json.dumps(obj), encoding="utf-8")
        return obj
    raise ValueError(f"Unexpected fake gh command: {a}")


if cmd == "gh":
    result = gh()
    sys.stdout.buffer.write(result if isinstance(result, bytes) else json.dumps(result).encode())
else:
    {"git": git, "curl": curl, "npm": npm}[cmd]()
