#!/usr/bin/env python3
"""Rebuild docs/index.md: latest report link + full archive.

Scans docs/reports/YYYY-MM-DD.md (newest first) and regenerates the homepage.
Run from the repo root after adding a new report:
    python3 scripts/build_site_index.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "docs" / "reports"
INDEX = ROOT / "docs" / "index.md"

INTRO = """---
layout: home
title: Daily Insider Trading Report
---

**What are politicians, billionaires, and Wall Street giants buying and selling?**
Updated every trading day from SEC EDGAR (Form 4, 13F), House Clerk disclosures,
and Senate eFD filings.

"""


def first_bullet(md_path: Path) -> str:
    """Pull a one-line summary: first real trade bullet of the report."""
    try:
        text = md_path.read_text()
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- **") and "No new" not in line and "No notable" not in line:
            # strip markdown bold for the summary line, keep it short
            clean = re.sub(r"\*\*", "", line).lstrip("- ").strip()
            return clean[:160]
    return "No new watched trades filed."


def main() -> None:
    reports = sorted(REPORTS.glob("2*.md"), reverse=True)
    if not reports:
        INDEX.write_text(INTRO + "_No reports yet._\n")
        return

    latest = reports[0]
    date = latest.stem
    summary = first_bullet(latest)

    lines = [INTRO]
    lines.append("## Latest report\n")
    lines.append(f"- **[{date}](reports/{date}.html)** — {summary}\n")
    lines.append("## Archive\n")
    for r in reports:
        lines.append(f"- [{r.stem}](reports/{r.stem}.html)")
    lines.append("")
    lines.append("---")
    lines.append(
        "_Methodology: congressional PTRs disclose amount ranges, not exact values; "
        "trades shown as filed. Form 4 covers open-market buys (P) and sells (S) only. "
        "13F is quarterly with a ~45-day lag. "
        "[How this report is built](../README.md) · "
        "[Data sources: SEC EDGAR, House Clerk, Senate eFD](https://www.sec.gov/edgar)_"
    )
    lines.append("")
    INDEX.write_text("\n".join(lines))
    print(f"index.md rebuilt: {len(reports)} reports, latest {date}")


if __name__ == "__main__":
    main()
