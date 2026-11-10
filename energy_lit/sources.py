"""Metadata discovery and DOI-bound enrichment through public APIs."""

import html
import json
import os
import re
from collections.abc import Iterator
from datetime import date
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request

from ._network import fetch_bytes_with_retry
from .model import doi, safe_url

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
SEMANTIC = "https://api.semanticscholar.org/graph/v1/paper"
TOPIC_QUERIES = (
    'battery OR batteries OR electrode OR dendrite',
    'electrocatalysis OR electrocatalyst OR electroreduction OR "water splitting" OR "oxygen evolution"',
    'electrolyte OR solvation OR "electric double layer" OR "ionic conductivity"',
)
MAX_PAGES = 300
OPENALEX_FIELDS = ("id,doi,title,authorships,primary_location,publication_date,updated_date,"
                   "type,abstract_inverted_index,is_retracted")


class SourceError(RuntimeError):
    pass


def fetch(url, params, source, *, body=None):
    headers = {"User-Agent": "EnergyMaterialsLiterature/1.0", "Accept": "application/json"}
    if source == "Crossref" and (email := os.getenv("CROSSREF_EMAIL")):
        params = {**params, "mailto": email}
    if source == "OpenAlex" and (key := os.getenv("OPENALEX_API_KEY")):
        params = {**params, "api_key": key}
    if source == "Semantic Scholar" and (key := os.getenv("S2_API_KEY")):
        headers["x-api-key"] = key
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url + "?" + urlencode(params), data=body, headers=headers)
    try:
        payload = fetch_bytes_with_retry(
            req, timeout_seconds=35, request_delay_seconds=1.05 if source == "Crossref" else 0.25,
            retry_attempts=3, retry_backoff_seconds=2,
            error_factory=SourceError, operation_description=source,
        )
        return json.loads(payload)
    except (SourceError, ValueError) as exc:
        cause = exc.__cause__
        if isinstance(cause, HTTPError):
            reason = f"HTTP {cause.code}"
        else:
            reason = type(cause or exc).__name__
        raise SourceError(f"{source}: {reason}") from None


def text(value):
    if not isinstance(value, str):
        return ""
    clean = html.unescape(re.sub(r"</?(?:jats:)?[a-zA-Z][^<>]*>", " ", value[:160_000]))
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", clean)
    return " ".join(clean.split())


def strings(values):
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def date_parts(raw):
    try:
        parts = (raw or {}).get("date-parts", [[]])[0]
        if not 1 <= len(parts) <= 3 or not all(type(n) is int for n in parts):
            return None
        full = date(*[parts[i] if i < len(parts) else 1 for i in range(3)]).isoformat()
        return full[:(4, 7, 10)[len(parts) - 1]]
    except (TypeError, ValueError, IndexError, AttributeError):
        return None


def valid_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def crossref_record(item):
    titles = strings(item.get("title"))
    titles_journal = strings(item.get("container-title"))
    authors = [text(" ".join(strings([entry.get("given"), entry.get("family")]))) or text(entry.get("name"))
               for entry in item.get("author") or [] if isinstance(entry, dict)]
    doi_value = doi(item.get("DOI"))
    resource = ((item.get("resource") or {}).get("primary") or {}).get("URL")
    retracts = [target for update in item.get("update-to") or []
                if isinstance(update, dict) and update.get("type") == "retraction"
                and (target := doi(update.get("DOI")))]
    return {
        "doi": doi_value, "source": "Crossref", "source_id": doi_value,
        "title": text(titles[0]) if titles else "",
        "authors": [author for author in authors if author],
        "journal_reported": text(titles_journal[0]) if titles_journal else "",
        "issns": strings(item.get("ISSN")), "journal_id": None,
        "online_date": date_parts(item.get("published-online")),
        "print_date": date_parts(item.get("published-print")),
        "publication_date": date_parts(item.get("published")) or date_parts(item.get("issued")),
        "source_updated": (item.get("indexed") or {}).get("date-time"),
        "type": "retraction" if retracts else item.get("type"), "abstract": text(item.get("abstract")),
        "publisher_url": safe_url(resource),
        "retracts": retracts, "retracted": False,
    }


def openalex_record(item):
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    inverted = item.get("abstract_inverted_index")
    return {
        "doi": doi(item.get("doi")), "source": "OpenAlex", "source_id": safe_url(item.get("id")),
        "title": text(item.get("title")),
        "authors": [name for entry in item.get("authorships") or []
                    if (name := text((entry.get("author") or {}).get("display_name")))],
        "journal_reported": text(source.get("display_name")),
        "issns": strings(source.get("issn")), "journal_id": safe_url(source.get("id"))
            if source.get("type") == "journal" else None,
        "online_date": None, "print_date": None,
        "publication_date": valid_date(item.get("publication_date")),
        "source_updated": item.get("updated_date"),
        "type": item.get("type"), "abstract": text(reconstruct_abstract(inverted)),
        "publisher_url": safe_url(location.get("landing_page_url")) if source.get("type") == "journal" else None,
        "retracted": item.get("is_retracted") is True,
    }


def crossref_pages(journals, start, end, *, indexed=False, publication_floor=None) -> Iterator[list[dict]]:
    # Crossref ORs repeated ISSN filters. Use the full scan for journals that
    # deposit abstracts and for discovery independent of search-engine ranking.
    field = "index-date" if indexed else "pub-date"
    issn_filters = [f"issn:{issn}" for journal in journals for issn in journal["issns"]]
    bounds = [f"from-{field}:{start}", f"until-{field}:{end}"]
    if publication_floor:
        bounds.append(f"from-pub-date:{publication_floor}")
    filters = ",".join([*bounds, "type:journal-article", *issn_filters])
    cursor = "*"
    for _ in range(MAX_PAGES):
        page = fetch(CROSSREF, {"filter": filters, "cursor": cursor, "rows": 250,
                               "select": "DOI,title,author,container-title,ISSN,published-online,published-print,"
                                         "published,issued,indexed,type,abstract,resource,update-to",
                               **({"sort": "indexed", "order": "asc"} if indexed else {})}, "Crossref")
        try:
            message = page["message"]
            items = message["items"]
            if not isinstance(items, list):
                raise TypeError
            yield [crossref_record(item) for item in items]
        except (TypeError, ValueError, KeyError, AttributeError, IndexError):
            raise SourceError("Crossref: malformed works response") from None
        if len(items) < 250:
            return
        cursor = message.get("next-cursor")
        if not cursor:
            raise SourceError("Crossref: full page without next cursor")
    raise SourceError("Crossref: page safety limit reached")


def openalex_pages(journals, start, end) -> Iterator[list[dict]]:
    source_ids = "|".join(journal["openalex"].rsplit("/", 1)[-1] for journal in journals)
    filters = f"primary_location.source.id:{source_ids},from_publication_date:{start},to_publication_date:{end}"
    keyed = bool(os.getenv("OPENALEX_API_KEY"))
    for query in TOPIC_QUERIES:
        cursor = "*"
        seen = 0
        for page_number in range(1, MAX_PAGES + 1):
            paging = {"cursor": cursor} if keyed else {"page": page_number}
            page = fetch(OPENALEX, {"filter": filters, "search": query, "per-page": 100, **paging,
                                   "select": OPENALEX_FIELDS}, "OpenAlex")
            try:
                items = page["results"]
                meta = page["meta"]
                next_cursor = meta.get("next_cursor")
                count = meta["count"]
                if not isinstance(items, list) or type(count) is not int or count < 0:
                    raise TypeError
                if page_number == 1:
                    expected = count
                records = [openalex_record(item) for item in items]
            except (TypeError, ValueError, KeyError, AttributeError, IndexError):
                raise SourceError("OpenAlex: malformed works response") from None
            seen += len(records)
            terminal = (not next_cursor or not items) if keyed else page_number * 100 >= expected
            if (terminal and seen < expected) or (not terminal and len(items) != 100):
                raise SourceError("OpenAlex: truncated page")
            yield records
            if terminal:
                break
            if keyed:
                if not next_cursor or next_cursor == cursor:
                    raise SourceError("OpenAlex: invalid next cursor")
                cursor = next_cursor
            else:
                if expected > 10_000:
                    raise SourceError("OpenAlex: anonymous pagination exceeds 10,000 results")
        else:
            raise SourceError("OpenAlex: page safety limit reached")


def semantic_batch(dois):
    body = json.dumps({"ids": [f"DOI:{value}" for value in dois]}).encode()
    page = fetch(SEMANTIC + "/batch", {"fields": "externalIds,abstract,authors"}, "Semantic Scholar", body=body)
    if not isinstance(page, list) or len(page) != len(dois):
        raise SourceError("Semantic Scholar: malformed batch response")
    return {
        key: item for key, item in zip(dois, page)
        if isinstance(item, dict) and doi((item.get("externalIds") or {}).get("DOI")) == key
    }


def semantic_record(key, row):
    authors = [name for author in row.get("authors") or []
               if isinstance(author, dict) and (name := text(author.get("name")))]
    return {"doi": key, "source": "Semantic Scholar", "source_id": row.get("paperId"),
            "authors": authors, "abstract": text(row.get("abstract"))}


def lookup_record(key, source):
    if source == "Semantic Scholar":
        row = semantic_batch([key]).get(key)
        return semantic_record(key, row) if row else None
    try:
        if source == "Crossref":
            raw = fetch(CROSSREF + "/" + quote(key, safe="/"), {}, source)
            record = crossref_record(raw["message"])
            return record if record["doi"] == key else None
        raw = fetch(OPENALEX, {"filter": "doi:https://doi.org/" + key, "select": OPENALEX_FIELDS}, source)
        matches = [row for item in raw["results"] if (row := openalex_record(item))["doi"] == key]
        return matches[0] if len(matches) == 1 else None
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        raise SourceError(f"{source}: malformed DOI response") from None


# Adapted from Paper Digest (MIT), see LICENSE.paper-digest.
def reconstruct_abstract(value: object) -> str:
    if not isinstance(value, dict):
        return ""

    positions_to_token: dict[int, str] = {}
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        normalized_token = token[:4096].strip()
        if not normalized_token:
            continue
        for position in positions:
            if type(position) is not int or not 0 <= position < 20_000:
                continue
            positions_to_token.setdefault(position, normalized_token)

    if not positions_to_token:
        return ""

    return " ".join(
        positions_to_token[position]
        for position in sorted(positions_to_token)
        if positions_to_token[position]
    )
