#!/usr/bin/env python3
"""Render the GitHub Pages site as standalone HTML (no Jekyll).

Reads docs/reports/*.md + watchlists.yaml from the repo mirror and writes:
  docs/index.html               — homepage with latest report + archive
  docs/reports/YYYY-MM-DD.html  — one styled page per report
  docs/.nojekyll                — disables Jekyll so raw HTML is served

Each report page replicates the original report design: tabs for
Politicians / Public Figures / Investors / Firms / Watchlist,
All-Buys-Sells filter, text search, and an archive nav.

Usage: render_site.py [mirror_dir]
"""
import html
import re
import sys
import yaml
from pathlib import Path

MIRROR = Path(sys.argv[1] if len(sys.argv) > 1 else
              str(Path.home() / "workspace/insider-tracker/github-mirror"))
DOCS = MIRROR / "docs"
REPORTS_DIR = DOCS / "reports"

CSS = """
:root{--bg:#f3f6fa;--card:#fff;--ink:#16233a;--muted:#5c6f88;--accent:#0b5fff;
--buy:#0e7a3d;--buy-bg:#e7f6ec;--sell:#c03221;--sell-bg:#fdecea;--line:#dfe6f0}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.hero{background:linear-gradient(135deg,#081c36 0%,#0f3a75 100%);color:#fff;padding:2.6rem 1.25rem 2rem}
.hero-inner{max-width:1000px;margin:0 auto}
.hero h1{margin:0 0 .4rem;font-size:1.9rem;letter-spacing:-.01em}
.hero .sub{margin:0 0 1rem;opacity:.88}
.hero nav{font-size:.9rem;opacity:.92}.hero nav a{color:#a9c6ff;margin-right:1.2rem}
.wrap{max-width:1000px;margin:0 auto;padding:0 1.25rem 3.5rem}
.controls{position:sticky;top:0;background:var(--bg);padding:1rem 0 .8rem;z-index:5}
.tabs{display:flex;gap:.55rem;flex-wrap:wrap;margin-bottom:.8rem}
.tab-btn{border:1px solid var(--line);background:var(--card);padding:.6rem 1.15rem;border-radius:999px;cursor:pointer;font-size:.95rem;color:var(--ink)}
.tab-btn:hover{border-color:var(--accent);color:var(--accent)}
.tab-btn.active{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.tab-btn .count{display:inline-block;min-width:1.5em;text-align:center;background:rgba(0,0,0,.08);border-radius:999px;font-size:.8em;padding:.05em .4em;margin-left:.45em}
.tab-btn.active .count{background:rgba(255,255,255,.25)}
.filters{display:flex;gap:.8rem;flex-wrap:wrap;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:var(--card)}
.seg button{border:0;background:transparent;padding:.5rem 1rem;cursor:pointer;font-size:.9rem;color:var(--muted)}
.seg button.active{background:var(--ink);color:#fff;font-weight:600}
#search{flex:1;min-width:220px;border:1px solid var(--line);border-radius:999px;padding:.55rem 1.1rem;font-size:.95rem;background:var(--card)}
.tab-panel{display:none}.tab-panel.active{display:block}
.tab-panel h3{font-size:1.05rem;margin:1.4rem 0 .6rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;font-size:.85rem}
ul.trades{list-style:none;padding:0;margin:0;display:grid;gap:.7rem}
ul.trades li{background:var(--card);border:1px solid var(--line);border-left:5px solid #9fb0c7;border-radius:10px;padding:.85rem 1.05rem;box-shadow:0 1px 2px rgba(16,35,58,.05)}
ul.trades li.buy-side{border-left-color:var(--buy)}
ul.trades li.sell-side{border-left-color:var(--sell)}
ul.trades li.hidden{display:none}
p.note{color:var(--muted);font-style:italic;background:var(--card);border:1px dashed var(--line);border-radius:10px;padding:.8rem 1rem}
strong.buy{color:var(--buy);background:var(--buy-bg);padding:.1em .5em;border-radius:6px;font-size:.85em}
strong.sell{color:var(--sell);background:var(--sell-bg);padding:.1em .5em;border-radius:6px;font-size:.85em}
.tag-new{color:var(--buy);font-weight:700}.tag-exit{color:var(--sell);font-weight:700}
.watch-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.9rem}
.watch-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem}
.watch-card h4{margin:0 0 .5rem;font-size:.95rem}
.watch-card ul{margin:0;padding-left:1.1rem;font-size:.92rem;color:var(--muted)}
.archive{margin-top:2.5rem}.archive ul{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.5rem}
.archive li a{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:.4rem .95rem;font-size:.9rem}
footer.site{border-top:1px solid var(--line);margin-top:2.5rem;padding-top:1.2rem;color:var(--muted);font-size:.85rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:.9rem;margin-top:1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.25rem}
.card .date{font-weight:700;font-size:1.05rem}
.card .sum{color:var(--muted);font-size:.9rem;margin:.4rem 0 .8rem}
.card.featured{border-left:5px solid var(--accent)}
h2.sec{font-size:1.3rem;margin:2.2rem 0 .4rem}
@media(max-width:640px){.hero h1{font-size:1.45rem}.controls{position:static}}
"""

JS_TABS = """
(function(){
  var tabs=document.querySelectorAll('.tab-btn'),panels=document.querySelectorAll('.tab-panel');
  tabs.forEach(function(btn){btn.addEventListener('click',function(){
    tabs.forEach(function(b){b.classList.remove('active')});
    panels.forEach(function(p){p.classList.remove('active')});
    btn.classList.add('active');
    document.getElementById('panel-'+btn.dataset.tab).classList.add('active');
    applyFilters();
  });});
  var side='all',q='';
  function applyFilters(){
    document.querySelectorAll('.tab-panel.active ul.trades li').forEach(function(li){
      var okSide=(side==='all')||(li.dataset.side===side);
      var okQ=!q||li.dataset.text.indexOf(q)!==-1;
      li.classList.toggle('hidden',!(okSide&&okQ));
    });
    window.applyFilters=applyFilters;
  }
  document.querySelectorAll('#side-filter button').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('#side-filter button').forEach(function(x){x.classList.remove('active')});
      b.classList.add('active');side=b.dataset.side;applyFilters();
    });
  });
  document.getElementById('search').addEventListener('input',function(e){q=e.target.value.trim().toLowerCase();applyFilters();});
  window.applyFilters=applyFilters;
})();
"""


def inline_md(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def plain(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = s.strip("_").strip()
    return s


def detect_side(text):
    t = text
    if "**Purchase**" in t or "**BUY**" in t or "**[NEW]**" in t or "(Δ $+" in t:
        return "buy"
    if "**Sale**" in t or "**SELL**" in t or "**[EXITED]**" in t or "(Δ $-" in t:
        return "sell"
    return "neutral"


def parse_report(md_path):
    """Return (title, lede, sections) where sections = [(h2, [(h3, [bullets]|[note])])]."""
    text = md_path.read_text()
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else md_path.stem
    lede = ""
    sections = []
    cur_h2 = None
    cur_h3 = None
    i = 0
    # lede: first italic line after h1
    for j, ln in enumerate(lines[1:], 1):
        s = ln.strip()
        if s.startswith("_") and s.endswith("_") and len(s) > 2:
            lede = s.strip("_")
            i = j + 1
            break
        if s.startswith("## "):
            i = j
            break
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if s.startswith("## "):
            cur_h2 = (s[3:].strip(), [])
            sections.append(cur_h2)
            cur_h3 = None
        elif s.startswith("### "):
            cur_h3 = (s[4:].strip(), [])
            cur_h2[1].append(cur_h3)
        elif s.startswith("- ") and cur_h2 is not None:
            if cur_h3 is None:
                cur_h3 = ("", [])
                cur_h2[1].append(cur_h3)
            cur_h3[1].append(("bullet", s[2:].strip()))
        elif s.startswith("_") and s.endswith("_") and len(s) > 2 and cur_h2 is not None:
            if cur_h3 is None:
                cur_h3 = ("", [])
                cur_h2[1].append(cur_h3)
            cur_h3[1].append(("note", s.strip("_")))
        elif s == "---":
            break
        i += 1
    return title, lede, sections


def load_watchlists():
    wl = yaml.safe_load((MIRROR / "watchlists.yaml").read_text())
    return wl


def match_13f(filer, wl):
    """Return (investor_names, firm_names) matched by filer keywords (longest wins per list)."""
    f = filer.lower()
    inv = [(e["name"], k) for e in wl.get("investors", [])
           for k in e.get("filer_keywords", []) if k.lower() in f]
    frm = [(e["name"], k) for e in wl.get("firms", [])
           for k in e.get("filer_keywords", []) if k.lower() in f]
    inv_names = sorted({n for n, k in inv}, key=lambda n: -max(len(k) for n, k in inv if n == n))
    frm_names = sorted({n for n, k in frm}, key=lambda n: -max(len(k) for n, k in frm if n == n))
    return inv_names, frm_names


def bullet_li(raw):
    side = detect_side(raw)
    h = inline_md(raw)
    h = h.replace("<strong>[NEW]</strong>", '<strong class="tag-new">[NEW]</strong>')
    h = h.replace("<strong>[EXITED]</strong>", '<strong class="tag-exit">[EXITED]</strong>')
    # color-code buy/sell markers (must run before escaping concerns; operate on html)
    h = re.sub(r"<strong>(Purchase|BUY)</strong>", r'<strong class="buy">\1</strong>', h)
    h = re.sub(r"<strong>(Sale|SELL)</strong>", r'<strong class="sell">\1</strong>', h)
    cls = "buy-side" if side == "buy" else ("sell-side" if side == "sell" else "")
    return (f'<li class="{cls}" data-side="{side}" '
            f'data-text="{html.escape(plain(raw).lower())}">{h}</li>')


def render_report_page(date, title, lede, sections, wl, all_dates):
    # Split into the four content tabs
    pol, figs, inv13, frm13 = [], [], [], []
    for h2, subs in sections:
        low = h2.lower()
        if low.startswith("1."):
            pol = subs
        elif low.startswith("2."):
            figs = subs
        elif low.startswith("3."):
            for h3, items in subs:
                for kind, raw in items:
                    if kind != "bullet":
                        continue
                    filer = raw.split(":", 1)[0].strip()
                    inames, fnames = match_13f(filer, wl)
                    if inames:
                        inv13.append((filer, inames, raw))
                    if fnames:
                        frm13.append((filer, fnames, raw))
                    if not inames and not fnames:
                        inv13.append((filer, [], raw))
                        frm13.append((filer, [], raw))

    def subsection_html(subs):
        parts = []
        for h3, items in subs:
            if h3:
                parts.append(f"<h3>{html.escape(h3)}</h3>")
            bullets = [b for k, b in items if k == "bullet"]
            notes = [b for k, b in items if k == "note"]
            if bullets:
                parts.append('<ul class="trades">\n' + "\n".join(bullet_li(b) for b in bullets) + "\n</ul>")
            for n in notes:
                parts.append(f'<p class="note">{html.escape(n)}</p>')
        return "\n".join(parts) or '<p class="note">No data in this section.</p>'

    def f13_html(entries):
        if not entries:
            return '<p class="note">No 13F changes for this group this quarter.</p>'
        parts = ['<ul class="trades">']
        for filer, names, raw in entries:
            li = bullet_li(raw)
            if names:
                # annotate which watchlist entry it matched
                tag = html.escape(", ".join(names))
                li = li.replace("</li>", f' <span style="color:var(--muted);font-size:.8em">[{tag}]</span></li>')
            parts.append(li)
        parts.append("</ul>")
        return "\n".join(parts)

    def count(subs):
        return sum(1 for _, items in subs for k, _ in items if k == "bullet")

    tabs = [
        ("politicians", "Politicians", count(pol), subsection_html(pol)),
        ("figures", "Public Figures", count(figs), subsection_html(figs)),
        ("investors", "Investors", len(inv13), f13_html(inv13)),
        ("firms", "Firms", len(frm13), f13_html(frm13)),
        ("watchlist", "Watchlist", 0, ""),  # filled below
    ]

    # Watchlist tab content
    wparts = ['<div class="watch-grid">']
    wparts.append("<div class='watch-card'><h4>Politicians</h4><ul>" +
                  "".join(f"<li>{html.escape(p)}</li>" for p in wl.get("politicians", [])) + "</ul></div>")
    wparts.append("<div class='watch-card'><h4>Public Figures</h4><ul>" +
                  "".join(f"<li>{html.escape(p)}</li>" for p in wl.get("public_figures", [])) + "</ul></div>")
    wparts.append("<div class='watch-card'><h4>Investors</h4><ul>" +
                  "".join(f"<li>{html.escape(e['name'])}</li>" for e in wl.get("investors", [])) + "</ul></div>")
    wparts.append("<div class='watch-card'><h4>Firms</h4><ul>" +
                  "".join(f"<li>{html.escape(e['name'])}</li>" for e in wl.get("firms", [])) + "</ul></div>")
    wparts.append("</div>")
    tabs[4] = ("watchlist", "Watchlist", 0, "\n".join(wparts))

    tab_btns = []
    panels = []
    for i, (key, label, n, body_html) in enumerate(tabs):
        active = " active" if i == 0 else ""
        cnt = f' <span class="count">{n}</span>' if n else ""
        tab_btns.append(f'<button class="tab-btn{active}" data-tab="{key}">{html.escape(label)}{cnt}</button>')
        panels.append(f'<div class="tab-panel{active}" id="panel-{key}">\n{body_html}\n</div>')

    archive_items = "\n".join(
        f'<li><a href="{d}.html">{d}</a></li>' for d in all_dates)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)} — Daily Insider Trading Report</title>
<meta name="description" content="Daily congressional stock trades, SEC Form 4 insider transactions, and 13F institutional holdings for top politicians, billionaires, and investment firms."/>
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
<h1>{html.escape(title)}</h1>
<p class="sub">{html.escape(lede)}</p>
<nav><a href="../index.html">← All reports</a><a href="https://github.com/Undeterred404/daily-insider-trades">GitHub</a></nav>
</div></header>
<div class="wrap">
<div class="controls">
<div class="tabs" role="tablist">
{"".join(tab_btns)}
</div>
<div class="filters">
<div class="seg" id="side-filter">
<button data-side="all" class="active">All</button><button data-side="buy">Buys</button><button data-side="sell">Sells</button>
</div>
<input id="search" type="search" placeholder="Filter by name, ticker, company…"/>
</div>
</div>
{"".join(panels)}
<section class="archive"><h2 class="sec">Archive</h2><ul>
{archive_items}
</ul></section>
<footer class="site">
Methodology: congressional PTRs disclose amount ranges, not exact values; trades shown as filed.
Form 4 covers open-market buys (P) and sells (S) only. 13F is quarterly with a ~45-day lag.<br/>
For informational purposes only — not financial advice. Data: SEC EDGAR, House Clerk, Senate eFD.
</footer>
</div>
<script>{JS_TABS}</script>
</body>
</html>
"""


def first_bullet_summary(md_path):
    title, _, sections = parse_report(md_path)
    for _, subs in sections:
        for _, items in subs:
            for kind, raw in items:
                if kind == "bullet":
                    t = plain(raw)
                    return t[:170]
    return "No new watched trades filed."


def main():
    wl = load_watchlists()
    report_mds = sorted(REPORTS_DIR.glob("2*.md"), reverse=True)
    all_dates = [p.stem for p in report_mds]
    for md in report_mds:
        date = md.stem
        title, lede, sections = parse_report(md)
        out = REPORTS_DIR / f"{date}.html"
        out.write_text(render_report_page(date, title, lede, sections, wl, all_dates))
        print(f"rendered {out.name}")
    # index.html
    cards = []
    for i, md in enumerate(report_mds):
        date = md.stem
        summary = first_bullet_summary(md)
        feat = " featured" if i == 0 else ""
        cards.append(
            f'<div class="card{feat}"><div class="date">{date}</div>'
            f'<div class="sum">{html.escape(summary)}</div>'
            f'<a href="reports/{date}.html">Read report →</a></div>')
    index = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Daily Insider Trading Report</title>
<meta name="description" content="Daily insider trading report tracking congressional stock trades, SEC Form 4 insider transactions, and 13F institutional holdings for top politicians, billionaires, and investment firms."/>
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
<h1>Daily Insider Trading Report</h1>
<p class="sub">What are politicians, billionaires, and Wall Street giants buying and selling? Updated every trading day.</p>
<p class="sub" style="font-size:.85rem">Sources: SEC EDGAR (Form 4, 13F) · House Clerk disclosures · Senate eFD</p>
<nav><a href="https://github.com/Undeterred404/daily-insider-trades">GitHub</a></nav>
</div></header>
<div class="wrap">
<h2 class="sec">Reports</h2>
<div class="cards">
{"".join(cards) if cards else '<p class="note">No reports yet.</p>'}
</div>
<footer class="site">
For informational purposes only — not financial advice.
<a href="https://github.com/Undeterred404/daily-insider-trades">How this report is built</a>
</footer>
</div>
</body>
</html>
"""
    (DOCS / "index.html").write_text(index)
    (DOCS / ".nojekyll").write_text("")
    print(f"index.html written ({len(report_mds)} reports)")


if __name__ == "__main__":
    main()
