from __future__ import annotations

import re
from typing import Dict, List, TypedDict

# Domain-focused aspect terms for skincare/cosmetic product reviews.
ASPECT_KEYWORDS = {
    "texture": [
        "texture",
        "greasy",
        "oily",
        "sticky",
        "lightweight",
        "heavy",
        "smooth",
        "matte",
        "blend",
        "absorbs",
        "absorb",
    ],
    "white_cast": [
        "white cast",
        "whitening",
        "chalky",
        "ashy",
        "residue",
    ],
    "skin_reaction": [
        "acne",
        "breakout",
        "breakouts",
        "irritation",
        "rash",
        "itching",
        "redness",
        "burning",
        "stinging",
        "allergic",
        "allergy",
    ],
    "price": [
        "price",
        "cost",
        "expensive",
        "cheap",
        "affordable",
        "overpriced",
        "value",
        "worth",
    ],
    "trust": [
        "dermatologist",
        "recommended",
        "recommend",
        "safe",
        "trusted",
        "authentic",
        "genuine",
        "brand",
    ],
    "side_effects": [
        "side effect",
        "side effects",
        "no side effects",
        "no side-effect",
        "caused",
        "reaction",
    ],
    "sensitivity": [
        "sensitive",
        "sensitivity",
        "sensitive skin",
        "hypoallergenic",
        "gentle",
    ],
    "scent": [
        "smell",
        "scent",
        "fragrance",
        "odor",
        "odour",
        "perfume",
        "unscented",
    ],
    "effectiveness": [
        "effective",
        "works",
        "worked",
        "result",
        "improve",
        "improved",
        "protection",
        "spf",
        "sunburn",
        "hydrating",
        "moisturizing",
    ],
}


def _normalize_text(text: str) -> str:
    text = (text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def _term_regex(term: str) -> re.Pattern:
    escaped = re.escape(term.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    escaped = escaped.replace(r"\-", r"[-\s]?")
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


ASPECT_PATTERNS = {
    aspect: [_term_regex(term) for term in terms]
    for aspect, terms in ASPECT_KEYWORDS.items()
}


class _AspectEvidence(TypedDict):
    terms: List[str]
    first_position: int


def _collect_evidence(text: str) -> Dict[str, _AspectEvidence]:
    normalized = _normalize_text(text)
    evidence: Dict[str, _AspectEvidence] = {}

    for aspect, patterns in ASPECT_PATTERNS.items():
        matched_terms: List[str] = []
        first_position = len(normalized) + 1

        for pattern in patterns:
            for match in pattern.finditer(normalized):
                term = match.group(0).strip()
                if term and term not in matched_terms:
                    matched_terms.append(term)
                if match.start() < first_position:
                    first_position = match.start()

        if matched_terms:
            evidence[aspect] = {
                "terms": matched_terms,
                "first_position": first_position,
            }

    return evidence


def extract_aspects_with_evidence(text: str) -> Dict[str, List[str]]:
    collected = _collect_evidence(text)
    return {aspect: data["terms"] for aspect, data in collected.items()}


def extract_aspects(text: str) -> List[str]:
    collected = _collect_evidence(text)
    ordered = sorted(
        collected.items(),
        key=lambda item: (
            item[1]["first_position"],
            -len(item[1]["terms"]),
            item[0],
        ),
    )
    return [aspect for aspect, _ in ordered]
