"""Fail closed unless every required CI job explicitly succeeded."""

import json
import os
import sys


REQUIRED_JOBS = ("test", "plugin-packages", "macos-smoke")


def failures(needs):
    if not isinstance(needs, dict):
        return ["CI dependency results must be an object"]
    problems = []
    if set(needs) != set(REQUIRED_JOBS):
        problems.append("CI dependency set does not match the required jobs")
    for job in REQUIRED_JOBS:
        details = needs.get(job)
        result = details.get("result") if isinstance(details, dict) else None
        if result != "success":
            problems.append(f"{job}: {result!r} (required: 'success')")
    return problems


def main():
    try:
        needs = json.loads(os.environ["CI_NEEDS_JSON"])
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"CI Gate failed: missing or invalid dependency results: {exc}", file=sys.stderr)
        return 1
    problems = failures(needs)
    if problems:
        print("CI Gate failed:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("CI Gate passed: all required jobs succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
