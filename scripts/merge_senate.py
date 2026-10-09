"""One-time merge: senate_tmp/congress_trades.duckdb -> vendor/congress_trades.duckdb.

Merges senate_trades and senate_filings (dedup by link), then the tmp dir
can be deleted. Safe to re-run (INSERT OR IGNORE on link).
"""
import os
import sys

import duckdb

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(BASE, "vendor", "congress_trades.duckdb")
TMP = os.path.join(BASE, "vendor", "senate_tmp", "congress_trades.duckdb")

sys.path.insert(0, os.path.join(BASE, "vendor"))
from schema import ensure_schema  # noqa: E402


def main():
    if not os.path.exists(TMP):
        print("no tmp db, nothing to merge")
        return
    main_con = duckdb.connect(MAIN)
    ensure_schema(main_con)
    main_con.execute(f"ATTACH '{TMP}' AS tmp (READ_ONLY)")
    # discover columns to merge generically
    for tbl in ("senate_trades", "senate_filings"):
        try:
            cols = [r[1] for r in main_con.execute(
                f"PRAGMA table_info('{tbl}')").fetchall()]
        except Exception:
            # table may only exist in tmp; copy schema
            main_con.execute(
                f"CREATE TABLE {tbl} AS SELECT * FROM tmp.{tbl} LIMIT 0")
            cols = [r[1] for r in main_con.execute(
                f"PRAGMA table_info('{tbl}')").fetchall()]
        collist = ", ".join(cols)
        if "link" in cols:
            main_con.execute(f"""
                INSERT INTO {tbl} ({collist})
                SELECT {collist} FROM tmp.{tbl} t
                WHERE t.link IS NULL
                   OR NOT EXISTS (SELECT 1 FROM {tbl} m WHERE m.link = t.link)
            """)
        else:
            main_con.execute(f"""
                INSERT INTO {tbl} ({collist})
                SELECT {collist} FROM tmp.{tbl}
            """)
        n = main_con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"{tbl}: {n} rows after merge")
    main_con.execute("DETACH tmp")
    main_con.close()
    print("merge done")


if __name__ == "__main__":
    main()
