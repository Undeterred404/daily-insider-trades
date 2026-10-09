"""Daily insider/congressional trading report generator.

Pulls fresh data from:
  - vendor/congress_trades.duckdb  (House + Senate PTRs)
  - data/insider.db                (Form 4 transactions, 13F holdings)
Filters by watchlists.yaml and emits reports/YYYY-MM-DD.md + .json.

Usage:
    .venv/bin/python scripts/report.py [--date YYYY-MM-DD] [--days N]
"""
import datetime as dt
import json
import os
import sys

import duckdb
import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONGRESS_DB = os.path.join(BASE, "vendor", "congress_trades.duckdb")
INSIDER_DB = os.path.join(BASE, "data", "insider.db")
STATE = os.path.join(BASE, "data", "state.json")
REPORTS = os.path.join(BASE, "reports")


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


def fmt_amt(lo, hi):
    if lo is None:
        return "n/a"
    if hi:
        return f"${lo:,} - ${hi:,}"
    return f"${lo:,}+"


def main():
    os.makedirs(REPORTS, exist_ok=True)
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 1
    rdate = (sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv
             else dt.date.today().isoformat())
    cutoff = (dt.date.fromisoformat(rdate) - dt.timedelta(days=days)).isoformat()

    wl = yaml.safe_load(open(os.path.join(BASE, "watchlists.yaml")))
    pols = [p.lower() for p in wl.get("politicians", [])]
    figs = [p.lower() for p in wl.get("public_figures", [])]
    notable = wl.get("form4_notable_threshold", 500000)
    inv_names = [e["name"] for e in wl.get("investors", [])]
    firm_names = [e["name"] for e in wl.get("firms", [])]

    try:
        ccon = duckdb.connect(CONGRESS_DB, read_only=True)
        senate_n = ccon.execute(
            "SELECT COUNT(*) FROM senate_trades").fetchone()[0]
        ccon.close()
    except Exception:
        senate_n = 0
    chambers = "House Clerk disclosures" + (" + Senate eFD" if senate_n else
                                            " (Senate feed pending)")
    md = [f"# Insider & Political Trading Report — {rdate}",
          f"_Filings newly processed in the last {days} day(s). "
          f"Sources: SEC EDGAR (Form 4, 13F), {chambers}._\n"]

    # ---- 1. Congressional trades ----
    md.append("## 1. Congressional trades (buy/sell)")
    try:
        ccon = duckdb.connect(CONGRESS_DB, read_only=True)
        rows = ccon.execute("""
            SELECT chamber,
                   last_name, first_name,
                   CASE WHEN chamber='S' THEN 'Senate' ELSE office END AS dist,
                   tkr, asset_name, tx_type, amount_low, amount_high,
                   txn_date, filed_date, owner
            FROM (SELECT DISTINCT chamber, last_name, first_name, office,
                                  tkr, asset_name, tx_type, amount_low,
                                  amount_high, txn_date, filed_date, owner
                  FROM trades)
            WHERE filed_date >= ?
            ORDER BY filed_date DESC, amount_high DESC NULLS LAST
        """, [cutoff]).fetchall()
        ccon.close()
    except Exception as e:
        rows = []
        md.append(f"_Congressional data unavailable: {e}_\n")

    watched, others = [], []
    for r in rows:
        name = f"{r[2]} {r[1]}".lower()
        (watched if any(p in name or name in p for p in pols) else others).append(r)

    def cline(r):
        action = r[6] or "?"
        return (f"- **{r[2]} {r[1]}** ({r[3]}, {r[0]}) — **{action}** "
                f"{r[4] or ''} {r[5] or ''} — {fmt_amt(r[7], r[8])} "
                f"(traded {r[9] or '?'}, filed {r[10] or '?'})")

    if watched:
        md.append("### On the watchlist")
        md.extend(cline(r) for r in watched[:40])
    else:
        md.append("_No new trades by watched politicians._")
    if others:
        md.append(f"\n### Other notable congressional trades ({len(others)} total)")
        md.extend(cline(r) for r in others[:15])
    md.append("")

    # ---- 2. Form 4 insider transactions ----
    md.append("## 2. Corporate insider transactions (Form 4)")
    icon = duckdb.connect(INSIDER_DB, read_only=True)
    try:
        big = icon.execute("""
            SELECT owner_name, owner_title, ticker, issuer, tx_code,
                   shares, price, value, tx_date, filed_date
            FROM form4_trades
            WHERE filed_date >= ? AND value >= ?
            ORDER BY value DESC LIMIT 40
        """, [cutoff, notable]).fetchall()
    except Exception:
        big = []
        watched_f4 = []
    try:
        watched_f4 = icon.execute("""
            SELECT owner_name, owner_title, ticker, issuer, tx_code,
                   shares, price, value, tx_date, filed_date
            FROM form4_trades
            WHERE filed_date >= ?
            ORDER BY filed_date DESC, value DESC NULLS LAST LIMIT 500
        """, [cutoff]).fetchall()
    except Exception:
        watched_f4 = []
    figs_hit = [r for r in watched_f4
                if any(f in (r[0] or "").lower() for f in figs)]
    seen_owners = {r[0] for r in figs_hit}
    big = [r for r in big if r[0] not in seen_owners]
    buys = [r for r in big if r[4] == "P"]
    sells = [r for r in big if r[4] == "S"]

    def fline(r):
        side = "**BUY**" if r[4] == "P" else "**SELL**"
        role = f", {r[1]}" if r[1] else ""
        px = f" @ ${r[6]:,.2f}" if r[6] else ""
        val = f"${r[7]:,.0f}" if r[7] else "n/a"
        return (f"- {side} — **{r[0]}**{role} — {r[2] or ''} ({r[3] or ''}): "
                f"{r[5]:,.0f} shares{px} = **{val}** "
                f"(traded {r[8] or '?'}, filed {r[9] or '?'})")

    if figs_hit:
        md.append("### Watched public figures")
        md.extend(fline(r) for r in figs_hit[:15])
    else:
        md.append("_No new filings by watched public figures._")
    if buys:
        md.append("\n### Other notable insider buys (≥$500K)")
        md.extend(fline(r) for r in buys)
    else:
        md.append("_No notable insider buys (≥$500K)._")
    if sells:
        md.append("\n### Other notable insider sells (≥$500K)")
        md.extend(fline(r) for r in sells)
    else:
        md.append("\n_No notable insider sells (≥$500K)._")
    md.append("")

    # ---- 3. 13F updates ----
    md.append("## 3. 13F institutional holdings (quarterly)")
    try:
        qs = [r[0] for r in icon.execute(
            "SELECT DISTINCT quarter FROM f13_holdings ORDER BY quarter DESC"
            " LIMIT 2").fetchall()]
    except Exception:
        qs = []
    if len(qs) == 2:
        new_q, old_q = qs
        md.append(f"_Comparing {new_q} vs {old_q} for watched investors/firms._\n")
        diff = icon.execute("""
            SELECT filer_name, issuer, old_v, new_v, chg, flag FROM (
            WITH n AS (SELECT filer_name, issuer, cusip, shares, value_usd
                       FROM f13_holdings WHERE quarter=? AND putcall=''),
                 o AS (SELECT filer_name, issuer, cusip, shares, value_usd
                       FROM f13_holdings WHERE quarter=? AND putcall='')
            SELECT n.filer_name AS filer_name, n.issuer AS issuer,
                   o.value_usd AS old_v, n.value_usd AS new_v,
                   n.value_usd - COALESCE(o.value_usd,0) AS chg,
                   CASE WHEN o.cusip IS NULL THEN 'NEW' ELSE '' END AS flag
            FROM n LEFT JOIN o USING (filer_name, cusip)
            UNION ALL
            SELECT o.filer_name, o.issuer, o.value_usd, NULL,
                   -o.value_usd, 'EXITED'
            FROM o LEFT JOIN n USING (filer_name, cusip)
            WHERE n.cusip IS NULL
            )
            ORDER BY ABS(chg) DESC LIMIT 30
        """, [new_q, old_q]).fetchall()
        for filer, issuer, old_v, new_v, chg, flag in diff:
            if abs(chg or 0) < 1_000_000:
                continue
            tag = f" **[{flag}]**" if flag else ""
            ov = f"${old_v:,.0f}" if old_v else "—"
            nv = f"${new_v:,.0f}" if new_v else "—"
            md.append(f"- {filer}: {issuer or ''}{tag} — {ov} → {nv} "
                      f"(Δ ${chg:+,.0f})")
    elif len(qs) == 1:
        md.append(f"_Only one quarter loaded ({qs[0]}); diffs appear once two "
                  f"quarters are present. 13F data lags ~45 days after quarter-end._")
    else:
        md.append("_No 13F data loaded yet._")
    icon.close()

    md.append("\n---\n_Methodology: congressional PTRs disclose amount ranges, "
              "not exact values; trades shown are as-filed. Form 4 covers "
              "open-market buys (P) and sells (S) only. 13F is quarterly with "
              "a ~45-day lag — daily sections are congressional + insider; "
              "13F updates appear around filing season._")

    out = "\n".join(md)
    open(os.path.join(REPORTS, f"{rdate}.md"), "w").write(out)
    print(f"wrote reports/{rdate}.md "
          f"({len(watched)} watched congressional, {len(buys)} buys, "
          f"{len(sells)} sells)")


if __name__ == "__main__":
    main()
