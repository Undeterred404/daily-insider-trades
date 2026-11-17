"""Patched form4.py — prepared 2026-11-13, NOT yet applied to live scripts/form4.py.

Changes vs live scripts/form4.py (read 2026-11-13):
1. New table form4_accessions(accession PK, filed_date, cik, status, tx_count, processed_at).
   After parse_filing returns a doc (even with zero P/S txns), the accession is recorded
   status='parsed'. Future runs skip accessions in form4_accessions OR form4_trades,
   so zero-trade filings are not re-fetched every day.
   Unparsed filings (doc is None, e.g. SGML) are recorded status='unparsed' in a
   separate attempt only if --record-unparsed is passed; by default they are NOT
   marked processed, so a future SGML parser can re-try them. This preserves the
   17 Nov 12 SGML filings as recoverable.
2. Parallel fallback integrated: fetch_day_parallel(filings, workers) using
   ProcessPoolExecutor + parse_filing, mirroring data/tmp/parallel_form4.py.
   Auto-used when --parallel is passed, or when a day has >400 filings
   (threshold that produced the Nov 12 timeout/kill class of failure).
   Sequential path unchanged for normal days.

Apply on user approval: copy this file over scripts/form4.py (keep a .bak), then
run: .venv/bin/python scripts/form4.py --days 1  (smoke test on a light day)
and verify: SELECT status, count(*) FROM form4_accessions GROUP BY 1;
SGML parser for the 17 Nov 12 filings is NOT in this patch — still open.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import duckdb
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
DB = os.path.join(DATA, "insider.db")
STATE = os.path.join(DATA, "state.json")
UA = {"User-Agent": "Muse Research contact@example.com", "Accept-Encoding": "gzip"}
PARALLEL_THRESHOLD = 400

DDL = """CREATE TABLE IF NOT EXISTS form4_trades (
    filed_date DATE, tx_date DATE, cik VARCHAR, issuer VARCHAR, ticker VARCHAR,
    owner_name VARCHAR, owner_title VARCHAR, is_officer BOOLEAN,
    is_director BOOLEAN, is_ten_pct BOOLEAN,
    tx_code VARCHAR, shares DOUBLE, price DOUBLE, value DOUBLE,
    accession VARCHAR,
    PRIMARY KEY (accession, owner_name, tx_code, shares, tx_date)
)"""

DDL_ACC = """CREATE TABLE IF NOT EXISTS form4_accessions (
    accession VARCHAR PRIMARY KEY, filed_date DATE, cik VARCHAR,
    status VARCHAR, tx_count INTEGER, processed_at TIMESTAMP
)"""


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


def trading_days_since(last):
    days, d = [], dt.date.today() - dt.timedelta(days=1)
    start = dt.date.fromisoformat(last) if last else d - dt.timedelta(days=7)
    while d >= start:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return sorted(days)


def fetch_master(day):
    qtr = (day.month - 1) // 3 + 1
    url = (f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/"
           f"QTR{qtr}/master.{day:%Y%m%d}.idx")
    r = requests.get(url, headers=UA, timeout=30)
    if r.status_code != 200:
        return []
    out = []
    for line in r.text.splitlines():
        parts = line.split("|")
        if len(parts) == 5 and parts[2].strip() in ("4", "4/A"):
            out.append({"cik": parts[0].strip(), "form": parts[2].strip(),
                        "file": parts[4].strip()})
    return out


def parse_filing(path):
    r = requests.get(f"https://www.sec.gov/Archives/{path}", headers=UA,
                     timeout=30)
    if r.status_code != 200:
        return None
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>",
                  r.text, re.S)
    if not m:
        return None
    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return None

    def txt(el, tag):
        n = el.find(tag)
        return (n.text.strip() if n is not None and n.text else "")

    def num(el, *tags):
        for tag in tags:
            n = el.find(tag)
            if n is not None:
                v = n.find("value")
                raw = (v.text if v is not None and v.text else n.text) or ""
                raw = raw.replace(",", "").strip()
                try:
                    return float(raw)
                except ValueError:
                    return None
        return None

    def txdate(t):
        n = t.find("transactionDate")
        if n is None:
            return None
        v = n.find("value")
        return (v.text if v is not None else n.text or "").strip() or None

    issuer_el = root.find("issuer")
    issuer = txt(issuer_el if issuer_el is not None else ET.Element("x"),
                 "issuerName")
    ticker = txt(issuer_el if issuer_el is not None else ET.Element("x"),
                 "issuerTradingSymbol")
    txns = []
    for owner in root.findall("reportingOwner"):
        oid = owner.find("reportingOwnerId")
        rel = owner.find("reportingOwnerRelationship")
        oid = oid if oid is not None else ET.Element("x")
        rel = rel if rel is not None else ET.Element("x")
        name = txt(oid, "rptOwnerName")
        title = txt(rel, "officerTitle")
        flags = {k: txt(rel, k) == "1" for k in
                 ("isDirector", "isOfficer", "isTenPercentOwner")}
        tbl = root.find("nonDerivativeTable")
        if tbl is None:
            continue
        for t in tbl.findall("nonDerivativeTransaction"):
            coding = t.find("transactionCoding")
            code = txt(coding if coding is not None else ET.Element("x"),
                       "transactionCode")
            if code not in ("P", "S"):
                continue
            amt = t.find("transactionAmounts")
            amt = amt if amt is not None else ET.Element("x")
            shares = num(amt, "transactionShares")
            price = num(amt, "transactionPricePerShare")
            if not shares:
                continue
            txns.append({
                "owner_name": name, "owner_title": title,
                "is_officer": flags["isOfficer"],
                "is_director": flags["isDirector"],
                "is_ten_pct": flags["isTenPercentOwner"],
                "issuer": issuer, "ticker": ticker,
                "tx_code": code, "shares": shares, "price": price,
                "value": shares * price if price else None,
                "tx_date": txdate(t),
            })
    return {"issuer": issuer, "ticker": ticker, "txns": txns}


def _fetch_one(args):
    path, cik = args
    acc = path.split("/")[-1].replace(".txt", "")
    for attempt in range(2):
        try:
            doc = parse_filing(path)
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            return acc, cik, None, f"exc:{e}"
        if doc is None:
            return acc, cik, None, "no-doc"
        return acc, cik, doc, None
    return acc, cik, None, "failed"


def _already_done(con, acc):
    if con.execute("SELECT 1 FROM form4_accessions WHERE accession=? LIMIT 1",
                   [acc]).fetchone():
        return True
    return bool(con.execute(
        "SELECT 1 FROM form4_trades WHERE accession=? LIMIT 1",
        [acc]).fetchone())


def _store(con, day, acc, cik, doc):
    n = 0
    for t in doc["txns"]:
        try:
            con.execute(
                """INSERT OR IGNORE INTO form4_trades VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [day.isoformat(), t["tx_date"], cik, t["issuer"],
                 t["ticker"], t["owner_name"], t["owner_title"],
                 t["is_officer"], t["is_director"], t["is_ten_pct"],
                 t["tx_code"], t["shares"], t["price"], t["value"],
                 acc])
            n += 1
        except Exception:
            pass
    con.execute(
        "INSERT OR REPLACE INTO form4_accessions VALUES (?,?,?,?,?,?)",
        [acc, day.isoformat(), cik, "parsed", n,
         dt.datetime.now(dt.timezone.utc).isoformat()])
    return n


def fetch_day_sequential(con, day, filings, record_unparsed=False):
    total = 0
    for f in filings:
        acc = f["file"].split("/")[-1].replace(".txt", "")
        if _already_done(con, acc):
            continue
        try:
            doc = parse_filing(f["file"])
        except Exception as e:
            print(f"  warn {acc}: {e}", flush=True)
            continue
        if not doc:
            if record_unparsed:
                con.execute(
                    "INSERT OR REPLACE INTO form4_accessions VALUES (?,?,?,?,?,?)",
                    [acc, day.isoformat(), f["cik"], "unparsed", 0,
                     dt.datetime.now(dt.timezone.utc).isoformat()])
            continue
        total += _store(con, day, acc, f["cik"], doc)
        time.sleep(0.15)
    return total


def fetch_day_parallel(con, day, filings, workers=8, record_unparsed=False):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    todo = []
    for f in filings:
        acc = f["file"].split("/")[-1].replace(".txt", "")
        if not _already_done(con, acc):
            todo.append((f["file"], f["cik"]))
    print(f"  parallel: {len(todo)} to fetch with {workers} workers",
          flush=True)
    total = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, t): t for t in todo}
        for fut in as_completed(futs):
            acc, cik, doc, warn = fut.result()
            if warn:
                print(f"  warn {acc}: {warn}", flush=True)
                if record_unparsed and warn == "no-doc":
                    con.execute(
                        "INSERT OR REPLACE INTO form4_accessions "
                        "VALUES (?,?,?,?,?,?)",
                        [acc, day.isoformat(), cik, "unparsed", 0,
                         dt.datetime.now(dt.timezone.utc).isoformat()])
                continue
            total += _store(con, day, acc, cik, doc)
    return total


def main():
    os.makedirs(DATA, exist_ok=True)
    con = duckdb.connect(DB)
    con.execute(DDL)
    con.execute(DDL_ACC)
    state = load_state()
    days = trading_days_since(state.get("last_form4_date"))
    if "--days" in sys.argv:
        n = int(sys.argv[sys.argv.index("--days") + 1])
        days = trading_days_since(
            (dt.date.today() - dt.timedelta(days=n)).isoformat())
    force_parallel = "--parallel" in sys.argv
    record_unparsed = "--record-unparsed" in sys.argv
    total = 0
    for day in days:
        filings = fetch_master(day)
        if force_parallel or len(filings) > PARALLEL_THRESHOLD:
            total += fetch_day_parallel(con, day, filings,
                                        record_unparsed=record_unparsed)
        else:
            total += fetch_day_sequential(con, day, filings,
                                          record_unparsed=record_unparsed)
        state["last_form4_date"] = day.isoformat()
        save_state(state)
        print(f"{day}: {len(filings)} filings, {total} txns total", flush=True)
    con.close()
    print(f"done: {total} new transactions")


if __name__ == "__main__":
    main()
