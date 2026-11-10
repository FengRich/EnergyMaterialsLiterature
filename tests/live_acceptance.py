"""Run from the project root: python -m tests.live_acceptance."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from energy_lit.model import ROOT, doi, empty_state, journal_match, load_journals, week, write_json
from energy_lit.rules import load_rules
from energy_lit.sources import CROSSREF, OPENALEX, SourceError, crossref_record, fetch, openalex_record, semantic_batch
from energy_lit.sync import apply_batch, make_reports, validate_state

FIELDS = "id,doi,title,authorships,primary_location,publication_date,type,abstract_inverted_index,is_retracted"
DUPLICATE = "10.1021/jacs.4c12174"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-state", type=Path, help="Write redacted sample metadata for browser QA")
    args = parser.parse_args()
    cases = json.loads((ROOT / "tests/real-papers.json").read_text(encoding="utf-8"))
    expected = {key: (journal, status) for group in cases.values() for key, journal, status in group}
    assert 30 <= len(expected) <= 50
    journals, rules = load_journals(), load_rules()
    items = {}
    dois = list(expected)
    for index in range(0, len(dois), 15):
        query = "|".join(f"https://doi.org/{value}" for value in dois[index:index + 15])
        data = fetch(OPENALEX, {"filter": f"doi:{query}", "per-page": 30, "select": FIELDS}, "OpenAlex")
        for raw in data["results"]:
            row = openalex_record(raw)
            assert row["doi"] not in items, f"Duplicate OpenAlex work for {row['doi']}"
            items[row["doi"]] = row
    assert set(expected) == set(items), f"Missing DOI records: {set(expected) - set(items)}"

    now = datetime.now(timezone.utc)
    state = empty_state()
    apply_batch(state, list(items.values()), journals, rules, {}, {}, now)
    mismatches = []
    for key, (expected_journal, expected_status) in expected.items():
        row = items[key]
        actual_journal, _ = journal_match(journals, set(row["issns"]), {row["journal_id"]} - {None})
        actual = state["papers"].get(key, {}).get("status", "Excluded")
        if (actual_journal, actual) != (expected_journal, expected_status):
            mismatches.append(f"{key}: {actual_journal}, {actual}; expected {expected_journal}, {expected_status}")
    for mismatch in mismatches:
        print(mismatch, flush=True)

    raw = fetch(CROSSREF + "/" + quote(DUPLICATE, safe="/"), {}, "Crossref")["message"]
    duplicate = crossref_record(raw)
    assert duplicate["doi"] == DUPLICATE and duplicate["title"]
    prior = state["papers"][DUPLICATE]["first_seen"]
    count = len(state["papers"])
    apply_batch(state, [duplicate, items[DUPLICATE]], journals, rules, {}, {}, now)
    assert len(state["papers"]) == count
    assert state["papers"][DUPLICATE]["first_seen"] == prior
    assert set(state["papers"][DUPLICATE]["sources"]) == {"Crossref", "OpenAlex"}

    probe = "10.1038/s41560-019-0356-8"
    semantic_failure = None
    try:
        semantic = semantic_batch([probe])[probe]
        assert doi(semantic["externalIds"]["DOI"]) == probe
    except SourceError as exc:
        semantic_failure = str(exc)
    assert all(not p["abstract"] for p in state["papers"].values())
    assert all(not source.get("abstract") for p in state["papers"].values() for source in p["sources"].values())
    make_reports(state, rules, week(now))
    validate_state(state, journals)
    print(f"{len(expected)} live DOI samples, {len(mismatches)} mismatches, two-source dedup, S2: {semantic_failure or 'DOI checked'}", flush=True)
    assert not mismatches
    if args.preview_state:
        state["last_success"] = now.isoformat()
        state["sources"] = {
            "OpenAlex": {"state": "ok", "count": len(expected)},
            "Crossref": {"state": "ok", "count": 1},
            "Semantic Scholar": ({"state": "degraded", "detail": semantic_failure, "count": 0}
                                 if semantic_failure else {"state": "ok", "count": 1}),
        }
        write_json(args.preview_state, state)
    if semantic_failure:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
