from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any, Dict, List, Tuple, cast

try:
    from transformers import AutoModelForSequenceClassification as _AutoModelForSequenceClassification
    from transformers import AutoTokenizer as _AutoTokenizer

    AutoModelForSequenceClassification: Any = _AutoModelForSequenceClassification
    AutoTokenizer: Any = _AutoTokenizer
    _TRANSFORMERS_AVAILABLE = True
except Exception:
    AutoModelForSequenceClassification: Any = None
    AutoTokenizer: Any = None
    _TRANSFORMERS_AVAILABLE = False


_tokenizer: Any | None = None
_model: Any | None = None
_model_initialized = False
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
HF_LOCAL_FILES_ONLY = os.environ.get("HF_LOCAL_FILES_ONLY", "1") == "1"

if _TRANSFORMERS_AVAILABLE:
    try:
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
    except Exception:
        pass

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}

_DOMAIN_TERMS = {
    "greasy",
    "oily",
    "sticky",
    "smooth",
    "lightweight",
    "irritation",
    "rash",
    "itching",
    "burning",
    "breakout",
    "expensive",
    "cheap",
    "affordable",
    "recommended",
    "safe",
    "effective",
    "fragrance",
    "scent",
    "white",
    "cast",
}


def _ensure_model() -> bool:
    global _tokenizer, _model, _model_initialized

    if _model_initialized:
        return _tokenizer is not None and _model is not None

    _model_initialized = True
    if not _TRANSFORMERS_AVAILABLE or AutoTokenizer is None or AutoModelForSequenceClassification is None:
        return False

    try:
        tokenizer_cls = cast(Any, AutoTokenizer)
        model_cls = cast(Any, AutoModelForSequenceClassification)
        tokenizer = tokenizer_cls.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english",
            local_files_only=HF_LOCAL_FILES_ONLY,
        )
        model = model_cls.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english",
            output_attentions=True,
            local_files_only=HF_LOCAL_FILES_ONLY,
            use_safetensors=False,
        )
        model.eval()
        _tokenizer = tokenizer
        _model = model
    except Exception:
        _tokenizer = None
        _model = None
        return False

    return True


def _clean_token(token: str) -> str:
    token = token.replace("##", "")
    token = token.replace("\u0120", "")
    token = token.replace("\u2581", "")
    token = token.strip().lower()
    token = re.sub(r"[^a-z0-9'-]+", "", token)
    return token


def _attention_explain(text: str, top_k: int) -> List[Tuple[str, float]]:
    if not _ensure_model():
        return []

    tokenizer = _tokenizer
    model = _model
    if tokenizer is None or model is None:
        return []

    tokenizer = cast(Any, tokenizer)
    model = cast(Any, model)

    try:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        outputs = model(**inputs)
        attentions = outputs.attentions
    except Exception:
        return []

    if not attentions:
        return []

    token_scores = attentions[-1].mean(dim=1).mean(dim=1)[0].tolist()
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

    merged_scores: Dict[str, float] = {}
    for token, score in zip(tokens, token_scores):
        cleaned = _clean_token(token)
        if not cleaned:
            continue
        if cleaned in _STOPWORDS:
            continue
        if cleaned in {"[cls]", "[sep]", "[pad]", "[unk]", "cls", "sep", "pad", "unk"}:
            continue

        value = float(score)
        if cleaned in merged_scores:
            merged_scores[cleaned] = max(merged_scores[cleaned], value)
        else:
            merged_scores[cleaned] = value

    if not merged_scores:
        return []

    ranked = sorted(merged_scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def _lexical_explain(text: str, top_k: int) -> List[Tuple[str, float]]:
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z'-]*", text)]
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
    if not tokens:
        return []

    counts = Counter(tokens)
    scores: Dict[str, float] = {}

    for token, count in counts.items():
        base = 0.3 * count
        if token in _DOMAIN_TERMS:
            base += 1.0
        scores[token] = base

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def explain_prediction(text: str, top_k: int = 5) -> List[Tuple[str, float]]:
    text = (text or "").strip()
    if not text:
        return []

    k = max(1, min(int(top_k or 5), 20))

    attention_result = _attention_explain(text, k)
    if attention_result:
        return [(token, round(score, 4)) for token, score in attention_result]

    lexical_result = _lexical_explain(text, k)
    return [(token, round(score, 4)) for token, score in lexical_result]
