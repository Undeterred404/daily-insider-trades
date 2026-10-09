#!/usr/bin/env python3
"""Publish a daily report to the GitHub Pages site.

Copies reports/<date>.md into the repo mirror, rebuilds docs/index.md,
and pushes changed files to Undeterred404/daily-insider-trades via the
GitHub Contents API (handles create vs update via sha lookup).

Usage: publish_github.py --date YYYY-MM-DD
"""
import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

GH_API = str(Path.home() / "workspace/skills/github/bin/gh-api")
OWNER, REPO = "Undeterred404", "daily-insider-trades"
TRACKER = Path.home() / "workspace/insider-tracker"
MIRROR = TRACKER / "github-mirror"
TMP = Path("/tmp/gh-publish.json")


def gh(method, api_path, data=None):
    cmd = [GH_API, method, api_path]
    if data is not None:
        TMP.write_text(json.dumps(data))
        cmd += ["--data", f"@{TMP}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, r.stderr


def get_sha(rel):
    code, out, _ = gh("GET", f"/repos/{OWNER}/{REPO}/contents/{rel}")
    if code != 0:
        return None
    try:
        return json.loads(out).get("sha")
    except json.JSONDecodeError:
        return None


def push_file(rel, message):
    local = MIRROR / rel
    content = base64.b64encode(local.read_bytes()).decode()
    payload = {"message": message, "content": content}
    sha = get_sha(rel)
    if sha:
        payload["sha"] = sha
    code, out, err = gh("PUT", f"/repos/{OWNER}/{REPO}/contents/{rel}", payload)
    if code != 0:
        print(f"FAIL {rel}: {err.strip()[:300]}")
        return False
    print(f"pushed {rel}" + (" (updated)" if sha else " (new)"))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    src = TRACKER / "reports" / f"{args.date}.md"
    if not src.exists():
        print(f"ERROR: report not found: {src}", file=sys.stderr)
        return 1
    dst = MIRROR / "docs" / "reports" / f"{args.date}.md"
    dst.write_bytes(src.read_bytes())

    r = subprocess.run(
        [sys.executable, str(MIRROR / "scripts" / "build_site_index.py")],
        capture_output=True, text=True,
    )
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"index build failed: {r.stderr.strip()[:300]}", file=sys.stderr)
        return 1

    ok = True
    msg = f"Daily insider trading report {args.date}"
    ok &= push_file(f"docs/reports/{args.date}.md", msg)
    ok &= push_file("docs/index.md", msg)
    print("PUBLISH OK" if ok else "PUBLISH HAD FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
