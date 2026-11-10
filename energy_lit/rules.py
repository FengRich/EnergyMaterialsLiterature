"""Deterministic topic, method, and evidence rules."""

import re

from .model import ROOT, load_json


def load_rules():
    config = load_json(ROOT / "config/rules.json")
    for group in ("domains", "methods"):
        config[group] = {name: re.compile(pattern, re.I) for name, pattern in config[group].items()}
    config["ranking"] = {re.compile(pattern, re.I): value for pattern, value in config["ranking"].items()}
    for key in ("strong", "weak", "experimental"):
        config[key] = re.compile(config[key], re.I)
    if type(config["representative_limit"]) is not int or not 10 <= config["representative_limit"] <= 15:
        raise ValueError("Representative limit must be between 10 and 15")
    return config


def classify(title, abstract, rules):
    combined = f"{title}\n{abstract}"
    domains = [name for name, regex in rules["domains"].items() if regex.search(combined)]
    methods = [name for name, regex in rules["methods"].items() if regex.search(combined)]
    # Avoid counting words such as HER, SEI and ORR in unrelated ordinary text.
    if not re.search(r"\b(?:HER|OER|ORR|NRR|CORR|CO2RR|NO3RR)\b", combined):
        stripped = re.sub(r"\b(?:HER|OER|ORR|NRR|CORR|CO2RR|NO3RR)\b", "", combined, flags=re.I)
        if not rules["domains"]["Electrocatalysis"].search(stripped):
            domains = [domain for domain in domains if domain != "Electrocatalysis"]
    if not re.search(r"\b(?:SEI|CEI)\b", combined):
        stripped = re.sub(r"\b(?:SEI|CEI)\b", "", combined, flags=re.I)
        if not rules["domains"]["Battery"].search(stripped):
            domains = [domain for domain in domains if domain != "Battery"]

    if not domains:
        return domains, methods, "Rejected", "No evidence of an in-scope research domain"
    excerpts = [title, *re.split(r"(?<=[.!?])\s+", abstract)]
    strong = any(not rules["weak"].search(excerpt) and rules["strong"].search(excerpt)
                 and any(regex.search(excerpt) for regex in rules["methods"].values())
                 for excerpt in excerpts)
    if methods and strong:
        return domains, methods, "Accepted", None
    if not abstract:
        return domains, methods, "Pending", "Abstract unavailable and title evidence is insufficient"
    if not methods and rules["experimental"].search(abstract):
        return domains, methods, "Rejected", "Experimental evidence only in available metadata"
    return domains, methods, "Pending", "Substantive computation or AI needs verification"


def score(title, abstract, methods, rules):
    evidence = " ".join([title, abstract, *methods])
    return sum(weight for regex, weight in rules["ranking"].items() if regex.search(evidence))
