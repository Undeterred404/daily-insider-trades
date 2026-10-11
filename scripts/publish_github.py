#!/usr/bin/env python3
"""Publish a daily report to the GitHub Pages site.

Copies reports/<date>.md into the repo mirror, rebuilds the standalone
HTML site in-process, and pushes changed files to
Undeterred404/daily-insider-trades via the GitHub Contents API.

All GitHub calls go through gh_client (in-process urllib), never a
subprocess, so this is safe on detached cron runs.

Usage: publish_github.py --date YYYY-MM-DD
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gh_client  # noqa: E402
import render_site  # noqa: E402

OWNER, REPO = "Undeterred404", "daily-insider-trades"
TRACKER = Path.home() / "workspace/insider-tracker"
MIRROR = TRACKER / "github-mirror"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    src = TRACKER / "reports" / f"{args.date}.md"
    if not src.exists():
        print(f"ERROR: report not found: {src}", file=sys.stderr)
        return 1
    dst = MIRROR / "docs" / "reports" / f"{args.date}.md"
    body = src.read_text()
    # Prepend Jekyll front matter so the .md copy renders if ever viewed raw.
    # Strip any existing front matter first (idempotent re-runs).
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end != -1:
            body = body[end + 5:].lstrip("\n")
    title = body.splitlines()[0].lstrip("# ").strip().replace('"', "'")
    front = f'---\nlayout: report\ntitle: "{title}"\n---\n\n'
    dst.write_text(front + body)

    # Rebuild the standalone HTML site in-process (no subprocess).
    render_site.main(str(MIRROR))

    ok = True
    msg = f"Daily insider trading report {args.date}"
    for rel in (
        f"docs/reports/{args.date}.md",
        f"docs/reports/{args.date}.html",
        "docs/index.html",
        "docs/.nojekyll",
    ):
        data = (MIRROR / rel).read_bytes()
        ok &= gh_client.put_file(OWNER, REPO, rel, data, msg)
    print("PUBLISH OK" if ok else "PUBLISH HAD FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
