"""Render accessible static pages and a stable, DOI-keyed RSS feed."""

import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from email.utils import format_datetime
from html import escape
from urllib.parse import urlsplit

from .model import ROOT, SHANGHAI, safe_url

NAME = "AI & Computational Energy Materials Literature Hub"
DOMAINS = ("Battery", "Electrocatalysis", "Electrolyte")
NAV = {"index": "This week", "library": "Library", "archive": "Weekly archive",
       "pending": "Pending review", "about": "About"}
ASSETS = ROOT / "web"


def e(value):
    return escape(str(value or ""), quote=True)


def link(url, label):
    return f'<a href="{e(url)}">{e(label)}</a>' if safe_url(url) else e(label)


def document(page, body):
    navigation = "".join(f'<a href="{name}.html"{" aria-current=page" if page == name else ""}>{label}</a>'
                         for name, label in NAV.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Computational and AI research across batteries, electrocatalysis, and electrolytes.">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{NAV[page]} · {e(NAME)}</title>
<link rel="alternate" type="application/rss+xml" title="Weekly representatives" href="feed.xml">
<link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="style.css"><script src="filters.js" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a>
<header class="masthead"><div class="frame masthead-inner">
<a class="brand" href="index.html"><span class="mark" aria-hidden="true">E</span><span>Energy Materials<span class="brand-subtitle">LITERATURE HUB</span></span></a>
<nav aria-label="Main navigation">{navigation}</nav>
</div></header>
<main id="main" class="frame">{body}</main>
<footer class="frame footer"><span>Energy Materials Literature Hub</span><a href="feed.xml">Weekly RSS ↗</a></footer>
</body></html>
"""


def tags(values, css):
    return "".join(f'<span class="tag {css}">{e(value)}</span>' for value in values)


def card(paper):
    journal = paper["journal"] or paper["reported_journal"] or "Journal unverified"
    authors = ", ".join(paper["authors"]) or "Author metadata unavailable"
    date = paper["publication_date"]
    source_links = []
    for name, source in paper["sources"].items():
        identifier = source.get("source_id")
        url = identifier if name == "OpenAlex" else paper["doi_url"] if name == "Crossref" else None
        source_links.append(link(url, name))
    doi = link(paper["doi_url"], paper["doi"] or "DOI unavailable")
    if paper["abstract"]:
        abstract = (f'<p class="abstract">{e(paper["abstract"])}</p>'
                    f'<p>{link(paper["abstract_evidence"], paper["abstract_license"])} · '
                    f'{e(paper["abstract_source"])}</p>')
    else:
        label = "Abstract withheld pending republication rights." if paper["abstract_source"] else "Abstract unavailable."
        abstract = f'<p class="muted">{label}</p>'
    reason = f'<p class="reason">{e(paper["reason"])}</p>' if paper["status"] == "Pending" else ""
    review = paper.get("review")
    review_link = f'<p>Review evidence · {link(review["evidence"], review["date"])}</p>' if review else ""
    publisher = f' · {link(paper["publisher_url"], "Publisher record ↗")}' if paper["publisher_url"] else ""
    dates = " · ".join(f"{label} {e(value)}" for label, value in
                       (("Online", paper["online_date"]), ("Print", paper["print_date"])) if value)
    return f"""<article class="paper" data-paper data-journal="{e(paper["journal"])}"
 data-domains="{e('|'.join(paper["domains"]))}" data-date="{e(date)}">
<p class="paper-meta"><span>{e(journal)}</span><span>{e(date or "Date unavailable")}</span></p>
<h3>{e(paper["title"] or "Original title unavailable")}</h3>
<div class="tags">{tags(paper["domains"], "domain")}{tags(paper["methods"], "method")}</div>
<p class="doi">{doi}</p>{reason}
<details><summary>Paper details</summary><p>{e(authors)}</p>{abstract}
<p>Sources · {" · ".join(source_links)}{publisher}</p>
<p>{e(paper["type"] or "Article type unavailable")}{' · ' + dates if dates else ''}
 · First found {e(paper["first_seen"][:10])}</p>{review_link}</details></article>"""


def cards(papers):
    return "".join(map(card, papers)) or '<p class="empty">No papers in this view.</p>'


def header(kicker, heading, description):
    return f'<div class="hero"><p class="eyebrow">{kicker}</p><h1>{heading}</h1><p>{description}</p></div>'


def distribution(title, values):
    total = max(values.values(), default=1)
    rows = "".join(f'<li><span>{e(label)}</span><meter min="0" max="{total}" value="{value}" '
                   f'aria-label="{e(label)}"></meter><strong>{value}</strong></li>'
                   for label, value in sorted(values.items(), key=lambda item: (-item[1], item[0])))
    return f'<section class="panel"><h2>{title}</h2><ul class="distribution">{rows or "<li>No papers yet.</li>"}</ul></section>'


def source_summary(state):
    latest = state["last_success"]
    time = datetime.fromisoformat(latest).astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M Beijing") if latest else "Awaiting first sync"
    sources = "".join(f'<li><strong>{e(name)}</strong> · {e(status["state"])}'
                      f'{(" · " + e(status["detail"])) if status.get("detail") else ""}</li>'
                      for name, status in sorted(state["sources"].items()))
    failures = state.get("backfill_issues", [])
    gaps = ""
    if failures:
        rows = "".join(f'<li>{e(row["source"])} · {e(row["from"])} to {e(row["to"])} · {e(row.get("detail"))}</li>'
                       for row in failures)
        gaps = f'<details><summary>{len(failures)} partial historical windows</summary><ul>{rows}</ul></details>'
    return f'<section class="panel" id="retrieval-status"><p class="eyebrow">Retrieval status</p><h2>{time}</h2><ul>{sources}</ul>{gaps}</section>'


def filters(journals):
    journal_options = "".join(f'<option>{e(journal["name"])}</option>' for journal in journals)
    domains = "".join(f'<option>{name}</option>' for name in DOMAINS)
    return f"""<div class="filters" aria-label="Filter papers">
<label>Search papers<input id="query" type="search" placeholder="Title, author, method, or DOI"></label>
<label>Journal<select id="journal"><option value="">All journals</option>{journal_options}</select></label>
<label>Research area<select id="domain"><option value="">All areas</option>{domains}</select></label>
<label>Sort<select id="order"><option value="desc">Newest first</option><option value="asc">Oldest first</option></select></label>
</div><p id="result-count" class="muted" role="status"></p>"""


def rss(reports, papers, site_url):
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = NAME + " · Weekly representatives"
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = "Representative papers from the weekly literature update"
    ET.SubElement(channel, "language").text = "en"
    seen = set()
    for report in reports:
        for key in report["representative"]:
            if key in seen:
                continue
            seen.add(key)
            paper = papers[key]
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = paper["title"]
            ET.SubElement(item, "link").text = paper["doi_url"]
            ET.SubElement(item, "guid", isPermaLink="true").text = paper["doi_url"]
            ET.SubElement(item, "description").text = " · ".join([paper["journal"], *paper["domains"], *paper["methods"]])
            ET.SubElement(item, "pubDate").text = format_datetime(datetime.fromisoformat(paper["first_seen"]))
            for category in [*paper["domains"], *paper["methods"]]:
                ET.SubElement(item, "category").text = category
    ET.indent(root)
    return ET.ElementTree(root)


def build(state, output, journals, site_url, repository):
    parts = urlsplit(site_url)
    if not safe_url(site_url) and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}):
        raise ValueError("Provide an HTTPS Pages URL or a loopback preview URL")
    papers = state["papers"]
    reports = [state["reports"][key] for key in sorted(state["reports"], reverse=True)]
    latest = reports[0] if reports else {"edition": None, "papers": [], "representative": []}
    accepted = sorted((p for p in papers.values() if p["status"] == "Accepted"),
                      key=lambda p: (p["publication_date"] or "", p["id"]), reverse=True)
    pending = sorted((p for p in papers.values() if p["status"] == "Pending"),
                     key=lambda p: (p["publication_date"] or "", p["id"]), reverse=True)
    domain_counts = Counter(domain for p in accepted for domain in p["domains"])
    journal_counts = Counter(p["journal"] for p in accepted)
    edition_label = f'Edition · {e(latest["edition"])}' if latest["edition"] else "Weekly research watch"
    home = header(edition_label, e(NAME), "Follow computational and AI research in batteries, "
                  "electrocatalysis, and electrolytes across 27 journals.")
    metrics = [(len(latest["papers"]), "This week's additions"), (len(accepted), "Papers in the library"),
               (len(pending), "Awaiting review")]
    home += '<div class="metrics">' + "".join(f'<div><strong>{num}</strong><span>{label}</span></div>'
                                              for num, label in metrics) + "</div>"
    degraded = [name for name, status in state["sources"].items() if status["state"] in {"failed", "degraded"}]
    if degraded:
        home += ('<p class="notice">Retrieval issue · ' + e(", ".join(sorted(degraded)))
                 + ' · <a href="#retrieval-status">Status details</a></p>')
    home += f"""<section><h2>Representative papers</h2>
<p class="muted">Selected by configurable rules for interfaces, electrolytes, and computational methods.</p>
<div class="paper-list">{cards(papers[key] for key in latest["representative"])}</div></section>
<section><h2>All additions this week</h2><div class="paper-list">{cards(papers[key] for key in latest["papers"])}</div></section>
<div class="dashboard">{source_summary(state)}{distribution("Research areas", domain_counts)}
{distribution("Journals", journal_counts)}</div>"""
    library = header("Research index", "Paper library", "Browse and filter the full collection of accepted papers.")
    library += f'{filters(journals)}<div id="paper-list" class="paper-list">{cards(accepted)}</div>'
    archive = header("Weekly editions", "Archive", "Editions open on Mondays at 09:00 Beijing time.")
    for report in reports:
        archive += f'<details class="edition"><summary>Week of {e(report["edition"])} · {len(report["papers"])} papers</summary>'
        picks = "".join(f'<li>{link(papers[key]["doi_url"], papers[key]["title"])}</li>'
                        for key in report["representative"])
        if picks:
            archive += f'<h3>Representative papers</h3><ol>{picks}</ol>'
        archive += f'<div class="paper-list">{cards(papers[key] for key in report["papers"])}</div></details>'
    if not reports:
        archive += '<p class="empty">No weekly editions yet.</p>'
    queue = header("Editorial review", "Pending review", "Papers with incomplete identity or insufficient research evidence.")
    queue += f'{filters(journals)}<div id="paper-list" class="paper-list">{cards(pending)}</div>'
    journal_list = "".join(f'<li>{e(j["name"])} <span class="muted">{e(", ".join(j["issns"]))}</span></li>'
                           for j in journals)
    repo = link(repository, "GitHub repository ↗") if repository else "Repository link is available after publication."
    about = header("Methods and coverage", "About the hub", "A weekly index of published computational energy materials research.")
    about += f"""<div class="about-grid"><section class="panel"><h2>Scope and editorial rules</h2>
<p>The index covers Battery, Electrocatalysis, and Electrolyte. Exact ISSNs and OpenAlex journal identifiers
establish eligibility. Title, abstract, and article type support a rule-based screen for substantive
computation, simulation, or AI. Relevant papers with insufficient evidence enter Pending Review.</p>
<h2>Sources and schedule</h2><p>{link("https://openalex.org", "OpenAlex")} and
{link("https://www.crossref.org", "Crossref")} support discovery and metadata checks.
{link("https://www.semanticscholar.org", "Semantic Scholar")} helps fill abstract and author gaps by DOI.
Updates are scheduled for Mondays at 09:00 Beijing time.</p>
<h2>Coverage and copyright</h2><p>Indexing delays, incomplete deposits, API limits, and rule-based screening
can affect coverage. Publication dates and first discovery times are retained separately.
Abstracts are displayed only with recorded republication permission. Rights remain with the respective holders.</p>
<p>{repo}</p></section><section class="panel"><h2>Journal whitelist</h2><ol>{journal_list}</ol></section></div>"""
    output.mkdir(parents=True, exist_ok=True)
    for page, body in {"index": home, "library": library, "archive": archive, "pending": queue, "about": about}.items():
        (output / f"{page}.html").write_text(document(page, body), encoding="utf-8")
    rss(reports, papers, site_url).write(output / "feed.xml", encoding="utf-8", xml_declaration=True)
    for asset in ("style.css", "filters.js", "favicon.svg"):
        shutil.copyfile(ASSETS / asset, output / asset)
    (output / ".nojekyll").touch()
