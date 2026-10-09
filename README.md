# Daily Insider Trading Report

**What are politicians, billionaires, and Wall Street giants buying and selling? Updated every trading day.**

📊 **[Read the latest report →](https://undeterred404.github.io/daily-insider-trades/)**

This project publishes a **daily insider trading report** tracking three kinds of market-moving disclosures:

1. **Congressional stock trades** — every buy and sell disclosed by U.S. House and Senate members in their Periodic Transaction Reports (PTRs). Follow the trades of Nancy Pelosi, Josh Gottheimer, Michael McCaul, Ro Khanna, Dan Crenshaw, Tommy Tuberville, and other active congressional traders.
2. **Corporate insider transactions (SEC Form 4)** — open-market buys and sells by company officers, directors, and 10% owners, flagged when public figures like Elon Musk, Jeff Bezos, Jensen Huang, Tim Cook, Satya Nadella, or Mark Zuckerberg file.
3. **Institutional holdings (SEC 13F)** — quarterly portfolio changes at the funds of legendary investors and major firms: Warren Buffett's Berkshire Hathaway, Bill Ackman's Pershing Square, Citadel, Bridgewater Associates, Renaissance Technologies, plus Michael Burry (Scion), David Tepper (Appaloosa), Stanley Druckenmiller (Duquesne), Seth Klarman (Baupost), and George Soros.

## Latest reports

See the [report archive](https://undeterred404.github.io/daily-insider-trades/) for every daily edition.

## Data sources

All data comes from free, public, primary sources — no paid vendor required:

- [SEC EDGAR](https://www.sec.gov/edgar) — Form 4 insider filings (daily) and 13F institutional holdings (quarterly)
- [House Clerk Financial Disclosures](https://disclosures-clerk.house.gov/) — House Periodic Transaction Reports
- [Senate eFD](https://efdsearch.senate.gov/) — Senate Periodic Transaction Reports

## How it works

```
SEC EDGAR (Form 4, 13F) ──┐
House Clerk PTRs ─────────┼──▶ scripts/ ──▶ reports/YYYY-MM-DD.md ──▶ GitHub Pages
Senate eFD PTRs ──────────┘         ▲
                              watchlists.yaml
```

- `scripts/form4.py` — incremental pull of new SEC Form 4 filings
- `scripts/f13.py` — quarterly 13F bulk dataset loader
- `vendor/scrape_house.py`, `vendor/scrape_senate.py` — congressional PTR scrapers (adapted from the open-source Quantgress project; see `vendor/ATTRIBUTION.md`)
- `scripts/report.py` — matches filings against `watchlists.yaml` and generates the daily markdown report
- `scripts/build_site_index.py` — rebuilds the report archive index for the website

The pipeline runs every morning; each new report is committed to `docs/reports/` and published automatically.

Watchlists (`politicians`, `public_figures`, `investors`, `firms`) are reviewed periodically — names are added or removed based on trading activity and public relevance.

## Methodology & limitations

- **Congressional PTRs disclose amount ranges** (e.g. $1,001–$15,000), not exact values. Trades are shown as filed.
- **Form 4** covers open-market buys (transaction code P) and sells (S) only; routine tax withholdings and option exercises are excluded from highlights.
- **13F is quarterly with a ~45-day lag** — the daily sections are congressional + insider activity; 13F updates appear around filing season (mid-Feb, mid-May, mid-Aug, mid-Nov).
- **Matching:** politicians are matched by last name against congressional filings; 13F filers are matched by filer-name keywords; public figures by reporting-owner name substring.
- Filing delays are inherent to the source data: Form 4s typically appear within ~2 business days, congressional disclosures 30–45 days after the trade.

## Disclaimer

This project is for informational and educational purposes only and is **not financial advice**. Data is presented as filed with primary sources and may contain filing errors or delays. Always verify against the original SEC or congressional disclosure before acting on anything here.

## License

Code in `scripts/` is released under the MIT License. Congressional and SEC filing data is public record.
