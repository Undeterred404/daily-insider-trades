#!/usr/bin/env python3
"""Push every file in the mirror dir to the GitHub repo via Contents API.

Usage: push_repo.py [mirror_dir]   (default: ~/workspace/insider-tracker/github-mirror)
One commit per file. Skips __pycache__ and dotfiles.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

GH_API = str(Path.home() / "workspace/skills/github/bin/gh-api")
OWNER, REPO = "Undeterred404", "daily-insider-trades"


def get_sha(rel):
    r = subprocess.run(
        [GH_API, "GET", f"/repos/{OWNER}/{REPO}/contents/{rel}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout).get("sha")
    except json.JSONDecodeError:
        return None


def put(rel: str, data: bytes, message: str):
    payload = {"message": message, "content": base64.b64encode(data).decode()}
    sha = get_sha(rel)
    if sha:
        payload["sha"] = sha
    tmp = Path("/tmp/gh-put.json")
    tmp.write_text(json.dumps(payload))
    r = subprocess.run(
        [GH_API, "PUT", f"/repos/{OWNER}/{REPO}/contents/{rel}", "--data", f"@{tmp}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"FAIL {rel}: {r.stderr.strip()[:300]}")
        return False
    print(f"ok {rel}")
    return True


def main():
    mirror = Path(sys.argv[1] if len(sys.argv) > 1 else
                  str(Path.home() / "workspace/insider-tracker/github-mirror"))
    files = sorted(
        p for p in mirror.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")
    )
    ok = True
    for p in files:
        rel = p.relative_to(mirror).as_posix()
        ok &= put(rel, p.read_bytes(), f"Add {rel}")
    print("ALL DONE" if ok else "SOME FAILURES")


if __name__ == "__main__":
    main()
