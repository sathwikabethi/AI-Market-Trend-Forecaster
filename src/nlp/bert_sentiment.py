from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Tuple, cast

try:
    from transformers import pipeline as _hf_pipeline

    pipeline: Any = _hf_pipeline
    _TRANSFORMERS_AVAILABLE = True
except Exception:
    pipeline: Any = None
    _TRANSFORMERS_AVAILABLE = False


MODEL_NAME = os.environ.get("SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
HF_LOCAL_FILES_ONLY = os.environ.get("HF_LOCAL_FILES_ONLY", "1") == "1"

if _TRANSFORMERS_AVAILABLE:
    try:
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
    except Exception:
        pass

_pipeline_instance: Any | None = None
_pipeline_initialized = False
_vader_analyzer = None
_vader_initialized = False

_NEGATORS = {
    "not",
    "no",
    "never",
    "hardly",
    "barely",
    "without",
    "none",
    "dont",
    "don't",
    "isnt",
    "isn't",
    "wasnt",
    "wasn't",
    "cant",
    "can't",
    "cannot",
    "wont",
    "won't",
}

_INTENSIFIERS = {
    "very": 1.3,
    "extremely": 1.6,
    "really": 1.2,
    "highly": 1.4,
    "too": 1.2,
    "super": 1.3,
    "quite": 1.1,
}

_POSITIVE_TERMS = {
    "good",
    "great",
    "excellent",
    "amazing",
    "love",
    "loved",
    "like",
    "liked",
    "smooth",
    "lightweight",
    "gentle",
    "effective",
    "works",
    "worked",
    "recommend",
    "recommended",
    "safe",
    "hydrating",
    "affordable",
    "value",
    "best",
}

_NEGATIVE_TERMS = {
    "bad",
    "poor",
    "terrible",
    "awful",
    "hate",
    "hated",
    "greasy",
    "sticky",
    "heavy",
    "irritation",
    "irritated",
    "rash",
    "itching",
    "acne",
    "breakout",
    "burning",
    "stinging",
    "expensive",
    "overpriced",
    "worst",
}

_POSITIVE_PHRASES = {
    "no side effects": 1.4,
    "without side effects": 1.4,
    "without any side effects": 1.6,
    "without side-effect": 1.4,
    "without any side-effect": 1.6,
    "highly recommended": 1.6,
    "worth the price": 1.2,
    "works well": 1.3,
    "very effective": 1.5,
    "no white cast": 1.4,
}

_NEGATIVE_PHRASES = {
    "white cast": 1.2,
    "caused irritation": 1.8,
    "too expensive": 1.5,
    "not worth": 1.5,
    "broke me out": 1.8,
    "side effects": 1.4,
}

_NON_NEGATIVE_SIDE_EFFECT_PATTERNS = (
    "no side effects",
    "without side effects",
    "without any side effects",
    "no side-effect",
    "without side-effect",
    "without any side-effect",
)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(cast(Any, value))
    except Exception:
        return default


def _get_pipeline() -> Any | None:
    global _pipeline_instance, _pipeline_initialized
    if _pipeline_initialized:
        return _pipeline_instance

    _pipeline_initialized = True
    if not _TRANSFORMERS_AVAILABLE:
        _pipeline_instance = None
        return _pipeline_instance

    try:
        _pipeline_instance = pipeline(
            "sentiment-analysis",
            model=MODEL_NAME,
            return_all_scores=True,
            model_kwargs={
                "local_files_only": HF_LOCAL_FILES_ONLY,
                "use_safetensors": False,
            },
        )
    except Exception:
        _pipeline_instance = None

    return _pipeline_instance


def _split_into_chunks(text: str, max_chars: int = 350) -> List[str]:
    text = (text or "").strip()
    if not text:
        return [""]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    if not sentences:
        return [text]

    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def _call_pipeline(sentiment_pipeline, text: str):
    try:
        return sentiment_pipeline(text, truncation=True)
    except TypeError:
        return sentiment_pipeline(text)


def _label_to_bucket(label: str) -> str:
    tag = (label or "").upper().strip()
    if "POS" in tag or tag in {"LABEL_2", "5 STARS", "4 STARS"}:
        return "positive"
    if "NEG" in tag or tag in {"LABEL_0", "1 STAR", "2 STARS"}:
        return "negative"
    if "NEU" in tag or tag in {"LABEL_1", "3 STARS"}:
        return "neutral"
    return "neutral"


def _extract_score_rows(raw_output: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_output, list) and raw_output:
        if isinstance(raw_output[0], list):
            return [row for row in raw_output[0] if isinstance(row, dict)]
        if isinstance(raw_output[0], dict):
            return [row for row in raw_output if isinstance(row, dict)]
    if isinstance(raw_output, dict):
        return [raw_output]
    return []


def _normalize_scores(score_rows: List[Dict[str, Any]]) -> Tuple[float, float, float]:
    pos = neg = neutral = 0.0
    for row in score_rows:
        bucket = _label_to_bucket(str(row.get("label", "")))
        score = _safe_float(row.get("score", 0.0))
        if bucket == "positive":
            pos += score
        elif bucket == "negative":
            neg += score
        else:
            neutral += score

    total = pos + neg + neutral
    if total <= 0:
        return 0.0, 0.0, 1.0
    return pos / total, neg / total, neutral / total


def _build_result(pos: float, neg: float, neutral: float) -> Dict[str, Any]:
    pos = min(max(pos, 0.0), 1.0)
    neg = min(max(neg, 0.0), 1.0)
    neutral = min(max(neutral, 0.0), 1.0)

    margin = abs(pos - neg)
    if margin < 0.08 and neutral >= max(pos, neg):
        label = "NEUTRAL"
    elif pos >= neg:
        label = "POSITIVE"
    else:
        label = "NEGATIVE"

    if label == "NEUTRAL":
        confidence = max(neutral, 1.0 - max(pos, neg))
    else:
        confidence = max(pos, neg)

    return {
        "label": label,
        "confidence": round(min(max(confidence, 0.0), 1.0), 3),
        "scores": {
            "positive": round(pos, 3),
            "negative": round(neg, 3),
            "neutral": round(neutral, 3),
        },
    }


def _vader_fallback(text: str):
    global _vader_analyzer, _vader_initialized

    if not _vader_initialized:
        _vader_initialized = True
        try:
            import nltk
            from nltk.sentiment import SentimentIntensityAnalyzer

            try:
                nltk.data.find("sentiment/vader_lexicon.zip")
            except LookupError:
                if os.environ.get("ALLOW_NLTK_DOWNLOAD", "0") == "1":
                    nltk.download("vader_lexicon", quiet=True)
                else:
                    _vader_analyzer = None
                    return None

            _vader_analyzer = SentimentIntensityAnalyzer()
        except Exception:
            _vader_analyzer = None

    if _vader_analyzer is None:
        return None

    try:
        compound = _safe_float(_vader_analyzer.polarity_scores(text).get("compound", 0.0))
        pos = max(compound, 0.0)
        neg = max(-compound, 0.0)
        neutral = max(0.0, 1.0 - abs(compound))
        return _build_result(pos, neg, neutral)
    except Exception:
        return None


def _lexicon_fallback(text: str) -> Dict[str, Any]:
    text = (text or "").lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z'-]*", text)

    if not tokens:
        return _build_result(0.0, 0.0, 1.0)

    score = 0.0
    for i, token in enumerate(tokens):
        token_score = 0.0
        if token in _POSITIVE_TERMS:
            token_score += 1.0
        if token in _NEGATIVE_TERMS:
            token_score -= 1.0

        if token_score == 0.0:
            continue

        window = tokens[max(0, i - 3):i]
        has_negation = any(w in _NEGATORS for w in window)
        intensity = 1.0
        for w in window:
            intensity *= _INTENSIFIERS.get(w, 1.0)

        if has_negation:
            token_score *= -0.9

        score += token_score * intensity

    for phrase, weight in _POSITIVE_PHRASES.items():
        if phrase in text:
            score += weight
    for phrase, weight in _NEGATIVE_PHRASES.items():
        if phrase == "white cast" and "no white cast" in text:
            continue
        if phrase == "side effects" and any(p in text for p in _NON_NEGATIVE_SIDE_EFFECT_PATTERNS):
            continue
        if phrase in text:
            score -= weight

    if "!" in text:
        score *= 1.1

    normalized = score / max(1.0, math.sqrt(len(tokens)))
    compound = math.tanh(normalized / 2.0)
    pos = max(compound, 0.0)
    neg = max(-compound, 0.0)
    neutral = max(0.0, 1.0 - abs(compound))
    return _build_result(pos, neg, neutral)


def _blend_results(primary: Dict[str, Any], secondary: Dict[str, Any], alpha: float = 0.75) -> Dict[str, Any]:
    alpha = min(max(alpha, 0.0), 1.0)
    p_scores = primary.get("scores", {}) if isinstance(primary, dict) else {}
    s_scores = secondary.get("scores", {}) if isinstance(secondary, dict) else {}
    if not isinstance(p_scores, dict):
        p_scores = {}
    if not isinstance(s_scores, dict):
        s_scores = {}

    pos = alpha * _safe_float(p_scores.get("positive", 0.0)) + (1.0 - alpha) * _safe_float(s_scores.get("positive", 0.0))
    neg = alpha * _safe_float(p_scores.get("negative", 0.0)) + (1.0 - alpha) * _safe_float(s_scores.get("negative", 0.0))
    neutral = alpha * _safe_float(p_scores.get("neutral", 0.0)) + (1.0 - alpha) * _safe_float(s_scores.get("neutral", 0.0))
    return _build_result(pos, neg, neutral)


def _model_sentiment(text: str):
    sentiment_pipeline = _get_pipeline()
    if sentiment_pipeline is None:
        return None

    chunks = _split_into_chunks(text, max_chars=350)
    chunk_scores: List[Tuple[float, float, float]] = []

    for chunk in chunks:
        try:
            raw_output = _call_pipeline(sentiment_pipeline, chunk)
        except Exception:
            continue

        rows = _extract_score_rows(raw_output)
        if not rows:
            continue
        chunk_scores.append(_normalize_scores(rows))

    if not chunk_scores:
        return None

    pos = sum(s[0] for s in chunk_scores) / len(chunk_scores)
    neg = sum(s[1] for s in chunk_scores) / len(chunk_scores)
    neutral = sum(s[2] for s in chunk_scores) / len(chunk_scores)
    return _build_result(pos, neg, neutral)


def get_sentiment(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return _build_result(0.0, 0.0, 1.0)

    model_result = _model_sentiment(text)
    if model_result is not None:
        lexicon_result = _lexicon_fallback(text)
        return _blend_results(model_result, lexicon_result, alpha=0.75)

    vader_result = _vader_fallback(text)
    if vader_result is not None:
        return vader_result

    return _lexicon_fallback(text)
