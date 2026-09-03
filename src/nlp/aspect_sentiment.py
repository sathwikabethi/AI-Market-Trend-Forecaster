from __future__ import annotations

import re
from typing import Any, Dict, List, cast

from src.nlp.aspect_extractor import (
    ASPECT_KEYWORDS,
    extract_aspects,
    extract_aspects_with_evidence,
)
from src.nlp.bert_sentiment import get_sentiment


SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
CONTRAST_PATTERN = re.compile(r"\b(?:but|however|though|although|whereas|yet)\b", re.IGNORECASE)


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_SPLIT_PATTERN.split((text or "").strip()) if s.strip()]


def _contains_term(sentence: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    escaped = escaped.replace(r"\-", r"[-\s]?")
    return re.search(rf"(?<!\w){escaped}(?!\w)", sentence.lower()) is not None


def _snippet_around_term(sentence: str, term: str) -> List[str]:
    escaped = re.escape(term.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    escaped = escaped.replace(r"\-", r"[-\s]?")
    pattern = re.compile(rf"(?<!\w){escaped}(?!\w)")

    snippets: List[str] = []
    lowered = sentence.lower()
    punctuation = ".!?,;"
    for match in pattern.finditer(lowered):
        left_boundary = -1
        for p in punctuation:
            left_boundary = max(left_boundary, sentence.rfind(p, 0, match.start()))

        right_boundary = len(sentence)
        right_hits = [sentence.find(p, match.end()) for p in punctuation]
        right_hits = [idx for idx in right_hits if idx != -1]
        if right_hits:
            right_boundary = min(right_hits)

        start = left_boundary + 1 if left_boundary >= 0 else 0
        end = right_boundary if right_boundary >= 0 else len(sentence)

        for connector in CONTRAST_PATTERN.finditer(sentence, start, end):
            if connector.end() <= match.start():
                start = max(start, connector.end())
            elif connector.start() >= match.end():
                end = min(end, connector.start())
                break

        snippet = sentence[start:end].strip(" ,;")
        if snippet and snippet not in snippets:
            snippets.append(snippet)

    return snippets


def _context_for_aspect(text: str, aspect: str, evidence_terms: List[str]) -> List[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return [text]

    candidate_terms = evidence_terms or ASPECT_KEYWORDS.get(aspect, [])
    matched_contexts: List[str] = []

    for sentence in sentences:
        for term in candidate_terms:
            if _contains_term(sentence, term):
                snippets = _snippet_around_term(sentence, term)
                if snippets:
                    for snippet in snippets:
                        if snippet not in matched_contexts:
                            matched_contexts.append(snippet)
                elif sentence not in matched_contexts:
                    matched_contexts.append(sentence)

    if not matched_contexts:
        return [text]
    return list(dict.fromkeys(matched_contexts))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(cast(Any, value))
    except Exception:
        return default


def _aggregate_sentiments(sentiments: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not sentiments:
        return {
            "label": "NEUTRAL",
            "confidence": 0.0,
            "scores": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
        }

    total_weight = 0.0
    pos_sum = 0.0
    neg_sum = 0.0
    neutral_sum = 0.0

    for sentiment in sentiments:
        confidence = _safe_float(sentiment.get("confidence", 0.0))
        weight = max(0.2, confidence)
        scores = sentiment.get("scores", {}) if isinstance(sentiment, dict) else {}
        if not isinstance(scores, dict):
            scores = {}
        pos = _safe_float(scores.get("positive", 0.0))
        neg = _safe_float(scores.get("negative", 0.0))
        neutral = max(0.0, 1.0 - min(1.0, pos + neg))

        pos_sum += pos * weight
        neg_sum += neg * weight
        neutral_sum += neutral * weight
        total_weight += weight

    if total_weight <= 0:
        return {
            "label": "NEUTRAL",
            "confidence": 0.0,
            "scores": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
        }

    pos_avg = pos_sum / total_weight
    neg_avg = neg_sum / total_weight
    neutral_avg = neutral_sum / total_weight

    margin = abs(pos_avg - neg_avg)
    if margin < 0.08 and neutral_avg >= max(pos_avg, neg_avg):
        label = "NEUTRAL"
    elif pos_avg >= neg_avg:
        label = "POSITIVE"
    else:
        label = "NEGATIVE"

    if label == "NEUTRAL":
        confidence = max(neutral_avg, 1.0 - max(pos_avg, neg_avg))
    else:
        confidence = max(pos_avg, neg_avg)

    return {
        "label": label,
        "confidence": round(min(max(confidence, 0.0), 1.0), 3),
        "scores": {
            "positive": round(min(max(pos_avg, 0.0), 1.0), 3),
            "negative": round(min(max(neg_avg, 0.0), 1.0), 3),
            "neutral": round(min(max(neutral_avg, 0.0), 1.0), 3),
        },
    }


def aspect_sentiment_analysis(text: str) -> Dict[str, Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return {"overall": get_sentiment("")}

    evidence_map = extract_aspects_with_evidence(text)
    aspects = list(evidence_map.keys()) or extract_aspects(text)
    if not aspects:
        aspects = ["overall"]

    results: Dict[str, Dict[str, Any]] = {}

    for aspect in aspects:
        aspect_terms = evidence_map.get(aspect, [])
        contexts = _context_for_aspect(text, aspect, aspect_terms) if aspect != "overall" else [text]
        per_context = [get_sentiment(context) for context in contexts if context.strip()]
        aggregated = _aggregate_sentiments(per_context)

        if aspect != "overall":
            aggregated["evidence"] = {
                "terms": aspect_terms[:10],
                "samples": contexts[:2],
            }

        results[aspect] = aggregated

    return results
