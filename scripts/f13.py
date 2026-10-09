"""Quarterly 13F holdings tracker for watched investors/firms.

Downloads the SEC 13F bulk data set for the latest quarter (if not already
processed), extracts holdings for watched filers (keyword match on filer
name), and stores them in DuckDB. On report runs, diffs the newest quarter
against the previous one to surface new/exited/increased/decreased positions.

Usage:
    .venv/bin/python scripts/f13.py

State: data/state.json (f13_quarters_processed). DB: data/insider.db
"""
import io
import json
import os
import re
import sys
import zipfile

import duckdb
import requests
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
DB = os.path.join(DATA, "insider.db")
STATE = os.path.join(DATA, "state.json")
UA = {"User-Agent": "Muse Research contact@example.com", "Accept-Encoding": "gzip"}
PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"

DDL = """CREATE TABLE IF NOT EXISTS f13_holdings (
    quarter VARCHAR, filer_name VARCHAR, cusip VARCHAR, putcall VARCHAR,
    issuer VARCHAR, shares DOUBLE, value_usd DOUBLE,
    PRIMARY KEY (quarter, filer_name, cusip, putcall)
)"""


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


# Explicit quarter registry: (label, url). The SEC page mixes two URL
# schemes and alphabetical sorting does not reflect recency, so we pin the
# quarters we care about instead of discovering them.
QUARTERS = [
    ("01mar2026",  # Q1 2026, filed by mid-May 2026
     "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip"),
    ("01jun2026",  # Q2 2026, filed by mid-Aug 2026 (latest available)
     "https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip"),
]


def latest_quarters(n=2):
    # Kept for compatibility; discovery proved unreliable (mixed URL schemes
    # + alphabetical sort != recency). Return the pinned registry instead.
    return QUARTERS[-n:]


def watched_keywords():
    wl = yaml.safe_load(open(os.path.join(BASE, "watchlists.yaml")))
    kws = []
    for section in ("investors", "firms"):
        for e in wl.get(section, []):
            kws.append((e["name"], [k.upper() for k in e["filer_keywords"]]))
    return kws


def tsv_rows(z, name):
    """Stream TSV rows from a zip member without loading it all into RAM."""
    with z.open(name) as f:
        header = None
        ci = None
        buf = b""
        for chunk in iter(lambda: f.read(1 << 20), b""):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace")
                if header is None:
                    header = text.split("\t")
                    ci = {c: i for i, c in enumerate(header)}
                    continue
                cols = text.split("\t")
                if len(cols) > len(header) // 2:
                    yield ci, cols
        if buf.strip():
            text = buf.decode("utf-8", "replace")
            cols = text.split("\t")
            if header is not None and len(cols) > len(header) // 2:
                yield ci, cols


def process_quarter(url, qlabel, con, local_zip=None):
    kws = watched_keywords()
    if local_zip:
        z = zipfile.ZipFile(local_zip)
    else:
        print(f"downloading {qlabel} ...", flush=True)
        r = requests.get(url, headers=UA, timeout=600)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
    # accession -> (filer_name, filing_date); keep latest filing per filer
    sub_date = {}
    for ci, cols in tsv_rows(z, "SUBMISSION.tsv"):
        sub_date[cols[ci["ACCESSION_NUMBER"]]] = cols[ci["FILING_DATE"]]
    best = {}  # wname -> (date, accession, filer_name)
    for ci, cols in tsv_rows(z, "COVERPAGE.tsv"):
        acc = cols[ci["ACCESSION_NUMBER"]]
        fname = cols[ci["FILINGMANAGER_NAME"]].upper()
        # longest keyword wins: "BERKSHIRE HATHAWAY INC" beats "BERKSHIRE HATHAWAY"
        # so the operating company maps to the firm entry, not the investor entry
        match = None
        for wname, keys in kws:
            for k in keys:
                if k in fname and (match is None or len(k) > len(match[1])):
                    match = (wname, k)
        if match:
            wname = match[0]
            d = sub_date.get(acc, "")
            cur = best.get(wname)
            if cur is None or d > cur[0]:
                best[wname] = (d, acc, cols[ci["FILINGMANAGER_NAME"]])
    wanted = {acc: (wname, filer_name) for wname, (_, acc, filer_name)
              in best.items()}
    print(f"  matched {len(wanted)} watched filings for {qlabel}", flush=True)
    rows, n = [], 0
    for ci, cols in tsv_rows(z, "INFOTABLE.tsv"):
        acc = cols[ci["ACCESSION_NUMBER"]]
        if acc not in wanted:
            continue
        wname, filer_name = wanted[acc]
        try:
            # NOTE: since Jan 2023 the SEC reports VALUE rounded to the nearest
            # dollar (previously thousands) -- do NOT multiply.
            rows.append((qlabel, f"{wname} ({filer_name})",
                         cols[ci["CUSIP"]],
                         cols[ci["PUTCALL"]].strip(),
                         cols[ci["NAMEOFISSUER"]],
                         float(cols[ci["SSHPRNAMT"]].replace(",", "") or 0),
                         float(cols[ci["VALUE"]].replace(",", "") or 0)))
        except (ValueError, IndexError):
            continue
        n += 1
        if len(rows) >= 5000:
            con.executemany(
                "INSERT OR REPLACE INTO f13_holdings VALUES (?,?,?,?,?,?,?)",
                rows)
            rows = []
    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO f13_holdings VALUES (?,?,?,?,?,?,?)", rows)
    print(f"  stored {n} holdings rows", flush=True)


def main():
    os.makedirs(DATA, exist_ok=True)
    con = duckdb.connect(DB)
    con.execute(DDL)
    state = load_state()
    done = set(state.get("f13_quarters", []))
    for qlabel, url in latest_quarters(2):
        if qlabel in done:
            print(f"{qlabel}: already processed", flush=True)
            continue
        local = os.path.join(DATA, f"f13_{qlabel}.zip")
        process_quarter(url, qlabel, con,
                        local_zip=local if os.path.exists(local) else None)
        done.add(qlabel)
        state["f13_quarters"] = sorted(done)
        save_state(state)
    con.close()
    print("done")


if __name__ == "__main__":
    main()
