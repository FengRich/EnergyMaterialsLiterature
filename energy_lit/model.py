"""Identity, journal verification, and durable state primitives."""

import calendar
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
DOI_RE = re.compile(r"10\.\d{4,9}/[!-~]+")
ISSN_RE = re.compile(r"\d{4}-\d{3}[\dX]")
STATUSES = {"Accepted", "Pending", "Rejected"}


def doi(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
    value = unquote(value).lower()
    return value if DOI_RE.fullmatch(value) else None


def doi_url(value):
    return "https://doi.org/" + quote(value, safe="/")


def safe_url(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        return value if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password else None
    except ValueError:
        return None


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
            tmp = Path(file.name)
            json.dump(value, file, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


def load_journals():
    journals = load_json(ROOT / "config/journals.json")
    seen = set()
    names = set()
    sources = set()
    for journal in journals:
        issns = journal["issns"]
        if (not issns or journal["issn_l"] not in issns or seen.intersection(issns)
                or journal["name"] in names or journal["openalex"] in sources
                or any(not valid_issn(issn) for issn in issns)
                or not re.fullmatch(r"https://openalex.org/S\d+", journal["openalex"])):
            raise ValueError("Invalid or duplicated journal identifier")
        seen.update(issns)
        names.add(journal["name"])
        sources.add(journal["openalex"])
    if len(journals) != 27:
        raise ValueError("V1 requires 27 journals")
    return journals


def valid_issn(value):
    if not ISSN_RE.fullmatch(value):
        return False
    digits = value.replace("-", "").replace("X", "A")
    return sum(int(digit, 16) * weight for digit, weight in zip(digits, range(8, 0, -1))) % 11 == 0


def journal_match(journals, issns, source_ids):
    issns = {value for value in issns if valid_issn(value)}
    matches = [journal for journal in journals
               if set(journal["issns"]) & issns or journal["openalex"] in source_ids]
    if not matches:
        return None, "Journal outside whitelist" if issns or source_ids else "Journal identifiers unavailable"
    journal = matches[0]
    if len(matches) != 1 or issns - set(journal["issns"]) or source_ids - {journal["openalex"]}:
        return None, "Conflicting journal identifiers"
    return journal["name"], None


def week(now):
    local = now.astimezone(SHANGHAI) - timedelta(hours=9)
    return local.date() - timedelta(days=local.weekday())


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def abstract_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def empty_state():
    return {"version": 1, "papers": {}, "reports": {}, "sources": {}, "last_success": None}
