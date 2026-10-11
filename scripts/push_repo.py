#!/usr/bin/env python3
"""Push every file in the mirror dir to the GitHub repo via Contents API.

All GitHub calls go through gh_client (in-process urllib), never a
subprocess, so this is safe on detached cron runs.

Usage: push_repo.py [mirror_dir]   (default: ~/workspace/insider-tracker/github-mirror)
One commit per file. Skips __pycache__ and dotfiles.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gh_client  # noqa: E402

OWNER, REPO = "Undeterred404", "daily-insider-trades"


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
        ok &= gh_client.put_file(OWNER, REPO, rel, p.read_bytes(), f"Add {rel}")
    print("ALL DONE" if ok else "SOME FAILURES")


if __name__ == "__main__":
    main()
