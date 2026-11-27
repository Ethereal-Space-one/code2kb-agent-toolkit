"""Build or score a blind, synthetic *source-evidence* review (not a release gate)."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import subprocess
import sys
import tempfile

from . import evidence_snapshot as evidence

VERSION = "code2kb.evidence-trial/1"
VERDICTS = {"supported", "contradicted", "insufficient"}
PURPOSE = "Synthetic controls only. Not production accuracy, independence proof, or release approval."


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def generate(seed, task="review"):
    if task not in {"review", "extract"}: raise ValueError("unknown trial type")
    rng = random.Random(seed)
    # Local, isolated synthetic Git objects. Never read user repos, identity, or hooks.
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory)
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TMPDIR") if k in os.environ}
        env.update(HOME=directory, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_DATE="2025-01-01T00:00:00Z", GIT_COMMITTER_DATE="2025-01-01T00:00:00Z",
                   GIT_AUTHOR_NAME="Fixture", GIT_COMMITTER_NAME="Fixture",
                   GIT_AUTHOR_EMAIL="fixture@example.invalid", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        def git(*args):
            return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull,
                                            "-C", directory, *args], env=env, stderr=subprocess.PIPE)
        git("init", "-q", "--template=")
        names = rng.sample(["iris", "maple", "quartz", "fennel", "willow", "cedar", "alder",
                            "elm", "birch", "spruce", "hazel", "dune", "ash", "cobalt"], 10)
        limits = [rng.randrange(3, 90) for _ in names]
        def revision(limits, title):
            for index, (name, limit) in enumerate(zip(names, limits)):
                operator = ">" if task == "extract" and index % 2 else ">="
                (repo / (name + ".py")).write_text(
                    f"def {name}_is_open(count):\n    return count {operator} {limit}\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", title)
            return git("rev-parse", "HEAD").decode().strip()

        old = revision([n + 1 for n in limits], "baseline")
        new = revision(limits, "revision")
        kinds = (["clean", "contradiction", "wrong_commit", "wrong_evidence", "no_evidence"] * 2)
        rng.shuffle(kinds)
        cases, labels = [], {}
        for i, (name, kind, limit) in enumerate(zip(names, kinds, limits)):
            subject = name if kind != "wrong_evidence" else names[(i + 1) % len(names)]
            target = rng.choice([old, new])
            pinned_limit = limit + (target == old)
            quoted = (new if target == old else old) if kind == "wrong_commit" else target
            observed_limit = limit + (quoted == old)
            value = observed_limit if kind == "wrong_commit" else pinned_limit
            claim = (f"At count {value}, {name}_is_open returns "
                     + ("False." if kind == "contradiction" else "True."))
            snippets = []
            if kind != "no_evidence":
                path = subject + ".py"
                record = evidence.snapshot("fixture:" + path + ":1-2", {"fixture": {"commit": quoted, "path": directory}})
                raw = git("cat-file", "blob", record["blob_oid"])
                snippets.append(dict(record, evidence_id="S1", text=raw.decode("utf-8")))
            verdict = {"clean": "supported", "contradiction": "contradicted"}.get(kind, "insufficient")
            case_id = digest([seed, i, "item"])[:14]
            if task == "extract":
                question = f"What is the smallest integer count for which {name}_is_open returns True?"
                expected = pinned_limit + (i % 2) if verdict != "insufficient" else None
                cited = ["S1"] if expected is not None else []
                if kind == "contradiction":
                    # A second, stale copy of the same function must not displace the target evidence.
                    other = new if target == old else old
                    snap = evidence.snapshot("fixture:" + path + ":1-2", {"fixture": {"commit": other, "path": directory}})
                    decoy = dict(snap, evidence_id="S2", text=git("cat-file","blob",snap["blob_oid"]).decode())
                    snippets.insert(0, decoy)
                    if i % 2:
                        snippets[0]["evidence_id"], snippets[1]["evidence_id"] = "S1", "S2"
                        cited = ["S2"]
                cases.append(dict(case_id=case_id,target_commit=target,question=question,snippets=snippets))
                labels[case_id] = dict(value=expected,evidence_ids=cited,
                                       category="mixed_revisions" if kind == "contradiction" else kind)
                continue
            cases.append(dict(case_id=case_id, target_commit=target, claim=claim, snippets=snippets))
            labels[case_id] = dict(verdict=verdict, evidence_ids=[] if verdict == "insufficient" else ["S1"], category=kind)
    pack = dict(schema=VERSION, instructions=(
        "Review each case independently using only its own snippets at its exact target commit. "
        "Return supported for direct support, contradicted for direct contrary evidence, otherwise insufficient. "
        "For supported/contradicted cite the relevant evidence_ids; otherwise use []. "
        "Return JSON with reviewer, pack_sha256, items (case_id, verdict, evidence_ids)."), cases=cases)
    if task == "extract":
        pack.update(task=task,instructions=(
            "Extract each requested integer rule from its own snippets at the exact target commit. "
            "For insufficient evidence return null and no citations. Otherwise cite only the decisive evidence. "
            "Return JSON with reviewer, pack_sha256, items (case_id, value, evidence_ids)."))
    key = dict(schema=VERSION, pack_sha256=digest(pack), seed=seed, labels=labels)
    if task == "extract": key["task"] = task
    return pack, key


def score(pack, key, answer, *, file_sha256=None):
    if not all(isinstance(x, dict) for x in (pack, key, answer)):
        raise ValueError("inputs must be JSON objects")
    bound = digest(pack)
    if pack.get("schema") != VERSION or key.get("schema") != VERSION or key.get("pack_sha256") != bound or answer.get("pack_sha256") not in (bound, file_sha256) or not answer.get("pack_sha256"):
        raise ValueError("pack/key/answer mismatch")
    if not isinstance(answer.get("reviewer"), str) or not answer["reviewer"].strip():
        raise ValueError("reviewer identity is required")
    labels = key.get("labels")
    if not isinstance(labels, dict) or set(labels) != {c["case_id"] for c in pack["cases"]} or not labels:
        raise ValueError("incomplete labels")
    # Independently regenerate the sealed synthetic key before trusting its verdicts.
    task = key.get("task", "review")
    field = "value" if task == "extract" else "verdict"
    reproduced, actual = generate(key["seed"], task)
    if digest(reproduced) != bound or key != actual:
        raise ValueError("invalid key or modified fixture")
    if not isinstance(answer.get("items"), list):
        raise ValueError("answer items must be a list")
    seen, correct, totals = set(), Counter(), Counter()
    for item in answer["items"]:
        if not isinstance(item, dict) or set(item) != {"case_id", field, "evidence_ids"}:
            raise ValueError("invalid answer item")
        case, verdict, cites = item["case_id"], item[field], item["evidence_ids"]
        valid = (verdict is None or type(verdict) is int) if task == "extract" else isinstance(verdict, str) and verdict in VERDICTS
        if not isinstance(case, str) or case not in labels or case in seen or not valid or not isinstance(cites, list) or not all(isinstance(c, str) for c in cites) or len(cites) != len(set(cites)):
            raise ValueError("duplicate, unknown or malformed answer")
        seen.add(case)
        truth = labels[case]
        totals[truth["category"]] += 1
        correct[truth["category"]] += int(verdict == truth[field] and sorted(cites) == truth["evidence_ids"])
    if seen != set(labels):
        raise ValueError("missing answers")
    return dict(schema=VERSION, pack_sha256=bound, answer_sha256=digest(answer), reviewer=answer["reviewer"],
                answer_pack_binding="canonical_json" if answer["pack_sha256"] == bound else "exact_file_bytes",
                total=len(seen), correct=sum(correct.values()), by_category={
                    k: dict(total=n, correct=correct[k]) for k, n in sorted(totals.items())}, limits=PURPOSE)


def parse(raw):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("duplicate JSON key")
            d[k] = v
        return d
    return json.loads(raw, object_pairs_hook=unique)


def load(path):
    return parse(path.read_text(encoding="utf-8"))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="cmd", required=True)
    prep = sub.add_parser("prepare"); grade = sub.add_parser("score")
    for p in (prep, grade):
        p.add_argument("--pack", required=True, type=Path); p.add_argument("--key", required=True, type=Path)
    prep.add_argument("--task", choices=("review","extract"), default="review")
    prep.add_argument("--seed", type=int); grade.add_argument("--answers", type=Path, required=True)
    args = cli.parse_args()
    try:
        if args.cmd == "prepare":
            if args.pack.resolve().parent in args.key.resolve().parents:
                raise ValueError("keep the key outside the reviewer's input directory")
            if args.pack.exists() or args.key.exists(): raise ValueError("outputs already exist")
            pack, key = generate(args.seed if args.seed is not None else secrets.randbits(64), args.task)
            for path, data in ((args.key, key), (args.pack, pack)):
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2); f.write("\n")
            result = dict(pack_sha256=digest(pack), file_sha256=hashlib.sha256(args.pack.read_bytes()).hexdigest(), total=len(pack["cases"]), state="unscored", limits=PURPOSE)
        else:
            raw = args.pack.read_bytes()
            result = score(parse(raw.decode("utf-8")), load(args.key), load(args.answers), file_sha256=hashlib.sha256(raw).hexdigest())
        print(json.dumps(result, indent=2))
        return int(args.cmd == "score" and result["correct"] != result["total"])
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as e:
        print(str(e), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
