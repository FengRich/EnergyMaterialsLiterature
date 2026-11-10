"""Resumable discovery, conservative metadata reconciliation, and weekly editions."""

import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .model import (ROOT, SHANGHAI, STATUSES, abstract_digest, doi, doi_url, empty_state,
                    journal_match, load_json, load_journals, months_before, safe_url, week, write_json)
from .rules import classify, load_rules, score
from .sources import (SourceError, crossref_pages, lookup_record, openalex_pages,
                      semantic_batch, semantic_record, text)

SEVERITY = {"Accepted": 2, "Pending": 1, "Rejected": 0}
LOOKBACK = timedelta(days=21)
BACKFILL_BATCH = timedelta(days=7)
MAX_NEW_PAPERS = 12_000
RETRY_DELAY = timedelta(days=7)
ARTICLE_TYPES = {"article", "journal-article", "review"}
COVER = re.compile(r"^(?:front|back|inside) cover\b|\(Adv\. [^()]+ \d+/\d{4}\)$", re.I)
OPEN_LICENSES = {"CC BY 4.0", "CC BY 3.0", "CC0 1.0"}
SOURCES = ("Crossref", "OpenAlex", "Semantic Scholar")


def load_decisions(path, *, licensing=False):
    entries = load_json(path)
    if not isinstance(entries, dict):
        raise ValueError("Decision files must be keyed by canonical DOI")
    for key, entry in entries.items():
        if doi(key) != key or not isinstance(entry, dict) or not safe_url(entry.get("evidence")):
            raise ValueError(f"Invalid decision record for {key}")
        date.fromisoformat(entry["date"])
        if licensing:
            digest = entry.get("sha256", "")
            if (entry.get("license") not in OPEN_LICENSES or entry.get("source") not in SOURCES
                    or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
                raise ValueError(f"Invalid abstract license for {key}")
        elif entry.get("decision") not in STATUSES or not text(entry.get("reason")):
            raise ValueError(f"Invalid review for {key}")
    return entries


def read_state(path):
    return load_json(path) if path.exists() else empty_state()


def validate_state(state, journals, licenses=None):
    if state.get("version") != 1 or not all(isinstance(state.get(key), dict)
                                            for key in ("papers", "reports", "sources")):
        raise ValueError("Unknown or invalid state schema")
    if state.get("last_success") is not None:
        datetime.fromisoformat(state["last_success"])
    journal_names = {j["name"] for j in journals}
    allowed_domains = {"Battery", "Electrocatalysis", "Electrolyte"}
    for key, paper in state["papers"].items():
        if key != paper["id"] or paper["status"] not in STATUSES:
            raise ValueError(f"Invalid paper identity or status for {key}")
        value = paper["doi"]
        if value and (doi(value) != key or value != key or paper["doi_url"] != doi_url(value)):
            raise ValueError(f"Invalid DOI record for {key}")
        if not value and not key.startswith("openalex:W"):
            raise ValueError(f"Unresolvable source identity for {key}")
        if paper["status"] == "Accepted" and (not value or paper["journal"] not in journal_names
                                                or not paper["title"]):
            raise ValueError(f"Accepted paper lacks verified metadata for {key}")
        if paper["status"] == "Accepted":
            matched, _ = journal_match(journals, set(paper["issns"]), set(paper["journal_ids"]))
            if matched != paper["journal"]:
                raise ValueError(f"Journal identity mismatch for {key}")
        if not isinstance(paper["authors"], list) or not set(paper["domains"]) <= allowed_domains:
            raise ValueError(f"Invalid authors or domains for {key}")
        if not isinstance(paper["sources"], dict) or not set(paper["sources"]) <= set(SOURCES):
            raise ValueError(f"Invalid provenance for {key}")
        datetime.fromisoformat(paper["first_seen"])
        datetime.fromisoformat(paper["last_updated"])
        if paper["edition"]:
            edition = date.fromisoformat(paper["edition"])
            if edition.weekday() != 0:
                raise ValueError(f"Invalid paper edition for {key}")
        if paper["publisher_url"] and not safe_url(paper["publisher_url"]):
            raise ValueError(f"Unsafe publisher link for {key}")
        if paper["abstract"]:
            if (paper["abstract_status"] != "Licensed" or not safe_url(paper["abstract_evidence"])
                    or abstract_digest(paper["abstract"]) != paper["abstract_hash"]):
                raise ValueError(f"Unverified public abstract for {key}")
            if licenses is not None and not license_matches(licenses.get(key), paper):
                raise ValueError(f"Public abstract has no active approval for {key}")
        if any("abstract" in source for source in paper["sources"].values()):
            raise ValueError(f"Unredacted upstream observation for {key}")
    for edition, report in state["reports"].items():
        if date.fromisoformat(edition).weekday() != 0 or report["edition"] != edition:
            raise ValueError(f"Invalid report edition {edition}")
        papers, picks = report["papers"], report["representative"]
        if len(set(papers)) != len(papers) or len(set(picks)) != len(picks) or not set(picks) <= set(papers):
            raise ValueError(f"Duplicate or invalid report membership for {edition}")
        if any(state["papers"][key]["status"] != "Accepted" or state["papers"][key]["edition"] != edition
               for key in papers):
            raise ValueError(f"Report includes an ineligible paper for {edition}")


def store_state(path, state, previous, journals, licenses=None):
    validate_state(state, journals, licenses)
    old, new = previous["papers"], state["papers"]
    migrated = {paper.get("supersedes") for paper in new.values()}
    if set(old) - set(new) - migrated or len(set(new) - set(old)) > MAX_NEW_PAPERS:
        raise ValueError("Anomalous paper-count change. State was not replaced")
    if set(previous["reports"]) - set(state["reports"]):
        raise ValueError("Report history disappeared")
    previously_accepted = {key for key, paper in old.items() if paper["status"] == "Accepted"}
    automated_loss = sum(new[key]["status"] != "Accepted" and not new[key]["review"]
                         for key in previously_accepted & set(new))
    if automated_loss > max(20, 0.3 * len(previously_accepted)):
        raise ValueError("Anomalous loss of accepted records. State was not replaced")
    for key in set(old) & set(new):
        if old[key]["first_seen"] != new[key]["first_seen"]:
            raise ValueError(f"Discovery timestamp changed for {key}")
    write_json(path, state)


def license_matches(approval, paper):
    return bool(approval and approval["source"] == paper["abstract_source"]
                and approval["sha256"] == paper["abstract_hash"]
                and approval["license"] == paper["abstract_license"]
                and approval["evidence"] == paper["abstract_evidence"])


def record_key(row):
    if row["doi"]:
        return row["doi"]
    if row["source"] == "OpenAlex" and row["source_id"]:
        identifier = row["source_id"].rsplit("/", 1)[-1]
        if identifier.startswith("W") and identifier[1:].isdigit():
            return "openalex:" + identifier
    return None


def evidence_for(row, title, rules):
    abstract = row.get("abstract") or ""
    domains, methods, status, reason = classify(title, abstract, rules)
    return {
        "domains": domains, "methods": methods, "auto_status": status, "auto_reason": reason,
        "rank": score(title, abstract, methods, rules),
        "abstract_hash": abstract_digest(abstract) if abstract else None,
    }


def reconcile(key, previous, rows, journals, rules, reviews, licenses, now, historical, retractions):
    instant = now.isoformat(timespec="seconds")
    previous = previous or {}
    sources = dict(previous.get("sources", {}))
    raw_abstracts = {}
    for row in rows:
        source = row["source"]
        # Multiple search groups can return the same DOI. Keep the more informative
        # observation in this batch while retaining prior evidence if a source is sparse.
        abstract = row.get("abstract")
        if abstract:
            raw_abstracts[source] = abstract
        old = sources.get(source, {})
        metadata = {field: value for field, value in row.items() if field not in {"abstract", "doi", "retracts"}}
        metadata = {field: value for field, value in metadata.items() if value or value is False}
        if old.get("retracted"):
            metadata["retracted"] = True
        sources[source] = {**old, **metadata}

    ordered = [sources[name] for name in SOURCES if name in sources]
    if not ordered:
        return None

    def first(field, default=None):
        return next((obs[field] for obs in ordered if obs.get(field)), default)

    title = first("title", "")
    for obs in ordered:
        source = obs["source"]
        if source in raw_abstracts:
            obs = {**obs, "evidence": evidence_for({"abstract": raw_abstracts[source]}, title, rules),
                   "evidence_title": title}
            sources[source] = obs

    title_evidence = evidence_for({}, title, rules)
    options = [("Title", title_evidence)]
    options.extend((name, sources[name]["evidence"]) for name in SOURCES
                   if name in sources and sources[name].get("evidence_title") == title)
    evidence_source, evidence = max(options, key=lambda entry: (
        SEVERITY[entry[1]["auto_status"]], bool(entry[1]["abstract_hash"]), len(entry[1]["methods"]),
    ))
    available = [name for name in SOURCES if name in sources and sources[name].get("evidence", {}).get("abstract_hash")]
    approval = licenses.get(key)
    preferred = approval["source"] if approval and approval["source"] in available else evidence_source
    abstract_source = preferred if preferred in available else next(iter(available), None)
    abstract_hash = sources[abstract_source]["evidence"]["abstract_hash"] if abstract_source else None
    abstract = raw_abstracts.get(abstract_source) or previous.get("abstract")
    permitted = bool(abstract and approval and approval["source"] == abstract_source
                     and approval["sha256"] == abstract_hash == abstract_digest(abstract))

    issns = {issn.upper() for obs in ordered for issn in obs.get("issns", [])}
    journal_ids = {obs["journal_id"] for obs in ordered if obs.get("journal_id")}
    journal, issue = journal_match(journals, issns, journal_ids)
    value = doi(key)
    status, reason = evidence["auto_status"], evidence["auto_reason"]
    # A pending result based only on title should not override an experimental
    # negative established by an available abstract.
    if evidence_source == "Title" and status == "Pending" and available:
        abstract_evidence = sources[available[0]]["evidence"]
        if abstract_evidence["auto_status"] == "Rejected" and abstract_evidence["domains"]:
            status, reason = abstract_evidence["auto_status"], abstract_evidence["auto_reason"]
    article_type = next((sources[name].get("type") for name in ("OpenAlex", "Crossref")
                         if name in sources and sources[name].get("type") not in (None, "article", "journal-article")),
                        first("type"))
    review = reviews.get(key)
    if review and review["decision"] != "Accepted":
        status, reason = review["decision"], review["reason"]
    elif issue == "Journal outside whitelist":
        status, reason = "Rejected", issue
    elif key in retractions or any(obs.get("retracted") for obs in ordered):
        status, reason = "Rejected", "Source reports a retraction"
    elif issue:
        status, reason = "Pending", issue
    elif not value or not title:
        status, reason = "Pending", "DOI or original title unavailable"
    elif review:
        status, reason = review["decision"], review["reason"]
    elif article_type == "retraction" or COVER.search(title):
        status, reason = "Rejected", "Non-research publication metadata"
    elif not article_type:
        status, reason = "Pending", "Publication type unavailable"
    elif article_type not in ARTICLE_TYPES:
        status, reason = "Rejected", "Publication type outside scope"
    if not evidence["domains"] and not review and not previous:
        return None
    if status == "Rejected" and reason == "Journal outside whitelist" and not previous and not review:
        return None

    online, print_date = first("online_date"), first("print_date")
    paper = {
        "id": key, "doi": value, "doi_url": doi_url(value) if value else None,
        "title": title, "authors": first("authors", []), "journal": journal,
        "reported_journal": first("journal_reported"), "journal_ids": sorted(journal_ids), "issns": sorted(issns),
        "online_date": online, "print_date": print_date,
        "publication_date": online or first("publication_date") or print_date,
        "publisher_url": first("publisher_url"), "type": article_type,
        "first_seen": previous.get("first_seen", instant),
        "last_updated": instant, "edition": previous.get("edition", None if historical else week(now).isoformat()),
        "status": status, "reason": reason, "review": review,
        "domains": evidence["domains"], "methods": evidence["methods"], "rank": evidence["rank"],
        "abstract": abstract if permitted else None, "abstract_source": abstract_source, "abstract_hash": abstract_hash,
        "abstract_status": "Licensed" if permitted else "Withheld" if abstract_source else "Missing",
        "abstract_license": approval["license"] if permitted else None,
        "abstract_evidence": approval["evidence"] if permitted else None,
        "sources": sources, "abstract_retry_at": previous.get("abstract_retry_at"),
        "supersedes": previous.get("supersedes"),
        "license_retry_at": previous.get("license_retry_at"),
        "extensions": previous.get("extensions", {}),
    }
    if previous and all(paper[field] == previous.get(field) for field in paper if field != "last_updated"):
        paper["last_updated"] = previous["last_updated"]
    return paper


def apply_batch(state, rows, journals, rules, reviews, licenses, now, *, historical=False):
    grouped = defaultdict(list)
    papers = state["papers"]
    retractions = set(state.get("retractions", []))
    aliases = {}
    for key, paper in papers.items():
        openalex = paper["sources"].get("OpenAlex")
        if paper["doi"] and openalex and openalex.get("source_id"):
            alias = record_key({**openalex, "doi": None})
            if alias:
                aliases[alias] = key
    for row in rows:
        retractions.update(row.get("retracts", []))
        key = record_key(row)
        if key:
            grouped[key].append(row)
        if row["doi"] and row["source"] == "OpenAlex" and row["source_id"]:
            alias = record_key({**row, "doi": None})
            if alias:
                if alias in aliases and aliases[alias] != row["doi"]:
                    raise ValueError("Conflicting DOI values for one OpenAlex identifier")
                aliases[alias] = row["doi"]
    for alias, key in aliases.items():
        if alias in papers:
            old = papers.pop(alias)
            if key not in papers:
                papers[key] = {**old, "supersedes": alias}
        if alias in grouped:
            grouped[key].extend(grouped.pop(alias))
    if retractions:
        state["retractions"] = sorted(retractions)
    for key in sorted(set(grouped) | set(papers)):
        paper = reconcile(key, papers.get(key), grouped[key], journals, rules, reviews, licenses,
                          now, historical, retractions)
        if paper:
            papers[key] = paper


def make_reports(state, rules, edition=None):
    reports = state["reports"]
    grouped = {key: [] for key in reports}
    if edition:
        grouped.setdefault(edition.isoformat(), [])
    for key, paper in state["papers"].items():
        if paper["edition"] and paper["status"] == "Accepted":
            grouped.setdefault(paper["edition"], []).append(key)
    for key, papers in grouped.items():
        papers.sort(key=lambda paper_id: (state["papers"][paper_id]["publication_date"] or "", paper_id), reverse=True)
        representative = sorted(papers, key=lambda paper_id: -state["papers"][paper_id]["rank"])
        reports[key] = {"edition": key, "papers": papers,
                        "representative": representative[:rules["representative_limit"]]}


def enrich(state, journals, rules, reviews, licenses, now, *, limit=100):
    pending = [paper for paper in state["papers"].values()
               if paper["doi"] and paper["journal"] and paper["status"] != "Rejected"
               and not paper["abstract_source"]
               and (not paper["abstract_retry_at"] or datetime.fromisoformat(paper["abstract_retry_at"]) < now - RETRY_DELAY)]
    pending.sort(key=lambda paper: (paper["abstract_retry_at"] or "", paper["first_seen"], paper["id"]))
    if not pending:
        return {"state": "no candidates", "count": 0}
    batch = pending[:limit]
    try:
        results = semantic_batch([paper["doi"] for paper in batch])
    except SourceError as exc:
        return {"state": "degraded", "detail": str(exc), "count": 0}
    observations = [semantic_record(key, row) for key, row in results.items()]
    apply_batch(state, observations, journals, rules, reviews, licenses, now)
    for paper in batch:
        state["papers"][paper["id"]]["abstract_retry_at"] = now.isoformat(timespec="seconds")
    return {"state": "ok", "count": len(results)}


def refresh_approved_abstracts(state, journals, rules, reviews, licenses, now):
    papers = state["papers"]
    candidates = sorted((key for key in licenses if key in papers and not papers[key]["abstract"]),
                        key=lambda key: (papers[key].get("license_retry_at") or "", key))
    rows = []
    attempted = []
    for key in candidates[:10]:
        attempted.append(key)
        try:
            row = lookup_record(key, licenses[key]["source"])
        except SourceError:
            continue
        if row:
            rows.append(row)
    if attempted:
        apply_batch(state, rows, journals, rules, reviews, licenses, now)
        for key in attempted:
            papers[key]["license_retry_at"] = now.isoformat(timespec="seconds")
        released = sum(bool(papers[key]["abstract"]) for key in attempted)
        if released < len(attempted):
            return {"state": "degraded", "detail": "Some approved text was unavailable or did not match its approved digest.",
                    "count": released}
    return None


def discover(journals, start, end, *, indexed_since=None, indexed_until=None, only=None):
    rows = []
    statuses = {}
    plans = {
        "Crossref": lambda: crossref_pages(journals, indexed_since or start, indexed_until or end,
                                          indexed=indexed_since is not None,
                                          publication_floor=months_before(end, 3) if indexed_since else None),
        "OpenAlex": lambda: openalex_pages(journals, start, end),
    }

    def collect(pages):
        return [row for page in pages() for row in page]

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = {name: pool.submit(collect, pages) for name, pages in plans.items() if not only or name == only}
        for name, future in running.items():
            try:
                records = future.result()
            except SourceError as exc:
                statuses[name] = {"state": "degraded", "detail": str(exc), "count": 0}
            else:
                rows.extend(records)
                statuses[name] = {"state": "ok", "count": len(records)}
    if not any(status["state"] == "ok" and status["count"] for status in statuses.values()):
        detail = ", ".join(status.get("detail", name + ": empty") for name, status in statuses.items())
        raise SourceError("Discovery produced no usable rows: " + detail)
    return rows, statuses


@contextmanager
def exclusive_sync(path):
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"Sync lock already exists: {lock}") from None
    try:
        with os.fdopen(descriptor, "w") as file:
            file.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def synchronize(path: Path, *, now=None):
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(SHANGHAI).date()
    edition = week(now)
    journals, rules = load_journals(), load_rules()
    reviews = load_decisions(ROOT / "config/reviews.json")
    licenses = load_decisions(ROOT / "config/abstract-licenses.json", licensing=True)
    with exclusive_sync(path):
        original = read_state(path)
        validate_state(original, journals)
        state = read_state(path)
        checkpoint = path.with_suffix(".bootstrap.json")
        if not state["last_success"]:
            if checkpoint.exists():
                saved = load_json(checkpoint)
                state = saved["state"]
                cursor = date.fromisoformat(saved["next"])
                cutoff = date.fromisoformat(saved["cutoff"])
                validate_state(state, journals)
            else:
                cursor, cutoff = months_before(day, 3), edition
            historical_issues = state.get("backfill_issues", [])
            while cursor < cutoff:
                end = min(cursor + BACKFILL_BATCH, cutoff) - timedelta(days=1)
                rows, statuses = discover(journals, cursor, end)
                apply_batch(state, rows, journals, rules, reviews, licenses, now, historical=True)
                historical_issues.extend({"from": str(cursor), "to": str(end), "source": name, **status}
                                         for name, status in statuses.items() if status["state"] != "ok")
                state["backfill_issues"] = historical_issues
                cursor = end + timedelta(days=1)
                validate_state(state, journals, licenses)
                write_json(checkpoint, {"state": state, "next": str(cursor), "cutoff": str(cutoff)})
                print(f"Historical window through {end}: {len(state['papers'])} records", flush=True)
            start, indexed_since = cutoff, None
        else:
            issues = state.get("backfill_issues", [])
            unresolved = []
            for issue in issues[:2]:
                try:
                    recovered, _ = discover(journals, issue["from"], issue["to"], only=issue["source"])
                except SourceError:
                    unresolved.append(issue)
                else:
                    apply_batch(state, recovered, journals, rules, reviews, licenses, now, historical=True)
            state["backfill_issues"] = [*issues[2:], *unresolved]
            start = min(day - LOOKBACK, datetime.fromisoformat(state["last_success"]).date() - LOOKBACK)
            crossref_ok = state.get("last_source_success", {}).get("Crossref")
            indexed_since = min(start, date.fromisoformat(crossref_ok) - LOOKBACK) if crossref_ok else None
            openalex_ok = state.get("last_source_success", {}).get("OpenAlex")
            if openalex_ok:
                start = min(start, date.fromisoformat(openalex_ok) - LOOKBACK)
        indexed_until = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if indexed_since else None
        rows, statuses = discover(journals, start, day, indexed_since=indexed_since, indexed_until=indexed_until)
        apply_batch(state, rows, journals, rules, reviews, licenses, now)
        statuses["Semantic Scholar"] = enrich(state, journals, rules, reviews, licenses, now)
        licensing_status = refresh_approved_abstracts(state, journals, rules, reviews, licenses, now)
        if licensing_status:
            statuses["Abstract licenses"] = licensing_status
        make_reports(state, rules, edition)
        state["sources"] = statuses
        state["last_success"] = now.isoformat(timespec="seconds")
        source_success = state.setdefault("last_source_success", {})
        for name in ("Crossref", "OpenAlex"):
            if statuses[name]["state"] == "ok":
                source_success[name] = day.isoformat()
            else:
                source_success.setdefault(name, start.isoformat())
        store_state(path, state, original, journals, licenses)
        checkpoint.unlink(missing_ok=True)
        return state
