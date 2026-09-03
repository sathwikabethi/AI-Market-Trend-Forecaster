from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.core.settings import settings
from src.data_processing.review_store import PROCESSED_DATA_PATH, initialize_datasets


_RAG_LOCK = RLock()
_RAG_CACHE: Dict[str, Any] = {
    "matrix_word": None,
    "vectorizer_word": None,
    "matrix_char": None,
    "vectorizer_char": None,
    "docs": [],
    "mtime": None,
    "built_at": None,
}

_TOKEN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "have",
    "has",
    "was",
    "were",
    "very",
    "just",
    "into",
    "about",
}

_INJECTION_MARKERS = {
    "ignore previous",
    "system prompt",
    "developer message",
    "jailbreak",
    "do anything now",
    "reveal secrets",
}


def _read_docs() -> List[Dict[str, Any]]:
    initialize_datasets()
    if not PROCESSED_DATA_PATH.exists():
        return []
    df = pd.read_csv(PROCESSED_DATA_PATH)
    if df.empty:
        return []
    for col, default in (
        ("review_id", ""),
        ("product", "general"),
        ("product_name", "General"),
        ("date", ""),
        ("review_text", ""),
        ("cleaned_text", ""),
        ("sentiment_label", "neutral"),
    ):
        if col not in df.columns:
            df[col] = default

    docs: List[Dict[str, Any]] = []
    for row in df.itertuples(index=False):
        review_text = str(getattr(row, "review_text", "") or "").strip()
        cleaned_text = str(getattr(row, "cleaned_text", "") or "").strip()
        compound_text = f"{review_text} {cleaned_text}".strip()
        if not compound_text:
            continue
        docs.append(
            {
                "review_id": str(getattr(row, "review_id", "")),
                "product": str(getattr(row, "product", "general")),
                "product_name": str(getattr(row, "product_name", "General")),
                "date": str(getattr(row, "date", "")),
                "review_text": review_text,
                "cleaned_text": cleaned_text,
                "sentiment_label": str(getattr(row, "sentiment_label", "neutral")),
                "text_for_index": compound_text,
            }
        )
    return docs


def _rebuild_index_if_needed() -> None:
    with _RAG_LOCK:
        mtime = PROCESSED_DATA_PATH.stat().st_mtime if PROCESSED_DATA_PATH.exists() else None
        if (
            _RAG_CACHE["matrix_word"] is not None
            and _RAG_CACHE["vectorizer_word"] is not None
            and _RAG_CACHE["matrix_char"] is not None
            and _RAG_CACHE["vectorizer_char"] is not None
            and _RAG_CACHE["mtime"] == mtime
        ):
            return

        docs = _read_docs()
        if not docs:
            _RAG_CACHE["docs"] = []
            _RAG_CACHE["matrix_word"] = None
            _RAG_CACHE["vectorizer_word"] = None
            _RAG_CACHE["matrix_char"] = None
            _RAG_CACHE["vectorizer_char"] = None
            _RAG_CACHE["mtime"] = mtime
            _RAG_CACHE["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return

        corpus = [str(doc.get("text_for_index", "")) for doc in docs]
        vectorizer_word = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=7000,
            min_df=1,
        )
        matrix_word = vectorizer_word.fit_transform(corpus)
        vectorizer_char = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=12000,
            min_df=1,
        )
        matrix_char = vectorizer_char.fit_transform(corpus)

        _RAG_CACHE["docs"] = docs
        _RAG_CACHE["matrix_word"] = matrix_word
        _RAG_CACHE["vectorizer_word"] = vectorizer_word
        _RAG_CACHE["matrix_char"] = matrix_char
        _RAG_CACHE["vectorizer_char"] = vectorizer_char
        _RAG_CACHE["mtime"] = mtime
        _RAG_CACHE["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def rag_status() -> Dict[str, Any]:
    _rebuild_index_if_needed()
    docs = _RAG_CACHE["docs"] or []
    by_product = Counter(str(doc.get("product", "general")) for doc in docs)
    return {
        "enabled": True,
        "documents_indexed": len(docs),
        "indexed_at": _RAG_CACHE.get("built_at"),
        "products": dict(by_product),
    }


def _extract_topics(snippets: List[str], top_n: int = 5) -> List[str]:
    tokens: list[str] = []
    for text in snippets:
        for token in str(text).lower().split():
            token = token.strip(".,!?;:()[]{}\"'")
            if len(token) < 4 or token in _TOKEN_STOPWORDS:
                continue
            tokens.append(token)
    counts = Counter(tokens)
    return [token for token, _ in counts.most_common(max(1, top_n))]


def ask_rag(question: str, product: str | None = None, top_k: int = 5) -> Dict[str, Any]:
    query = (question or "").strip()
    if len(query) < 3:
        return {
            "question": query,
            "product": product,
            "answer": "Please provide a more specific question.",
            "retrieved": [],
            "summary": {},
        }

    lowered = query.lower()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        return {
            "question": query,
            "product": product,
            "answer": "That request looks unsafe or irrelevant to the review dataset. Please ask a question about product feedback.",
            "retrieved": [],
            "summary": {"documents_matched": 0, "guardrail": "prompt_injection"},
        }

    _rebuild_index_if_needed()
    docs = _RAG_CACHE.get("docs") or []
    matrix_word = _RAG_CACHE.get("matrix_word")
    vectorizer_word = _RAG_CACHE.get("vectorizer_word")
    matrix_char = _RAG_CACHE.get("matrix_char")
    vectorizer_char = _RAG_CACHE.get("vectorizer_char")
    if (
        not docs
        or matrix_word is None
        or vectorizer_word is None
        or matrix_char is None
        or vectorizer_char is None
    ):
        return {
            "question": query,
            "product": product,
            "answer": "No processed review data is available yet for RAG retrieval.",
            "retrieved": [],
            "summary": {"documents_matched": 0},
        }

    if product:
        filtered_indices = [idx for idx, doc in enumerate(docs) if doc.get("product") == product]
    else:
        filtered_indices = list(range(len(docs)))

    if not filtered_indices:
        return {
            "question": query,
            "product": product,
            "answer": "No documents match the selected product.",
            "retrieved": [],
            "summary": {"documents_matched": 0},
        }

    char_weight = float(getattr(settings, "rag_char_weight", 0.25) or 0.25)
    char_weight = max(0.0, min(0.5, char_weight))

    q_word = vectorizer_word.transform([query])
    sims_word = cosine_similarity(q_word, matrix_word).ravel()
    q_char = vectorizer_char.transform([query])
    sims_char = cosine_similarity(q_char, matrix_char).ravel()
    sims_all = ((1.0 - char_weight) * sims_word) + (char_weight * sims_char)
    scored = sorted(
        ((idx, float(sims_all[idx])) for idx in filtered_indices),
        key=lambda item: item[1],
        reverse=True,
    )
    k = max(1, min(int(top_k), int(settings.rag_max_chunks)))
    min_sim = float(getattr(settings, "rag_min_similarity", 0.12) or 0.12)
    picked = [(idx, score) for idx, score in scored if score >= min_sim][:k]

    if not picked:
        return {
            "question": query,
            "product": product,
            "answer": "Insufficient evidence in the current review dataset to answer confidently. Try a more specific question or ingest more reviews.",
            "retrieved": [],
            "summary": {
                "documents_matched": 0,
                "min_similarity": round(min_sim, 4),
                "confidence": 0.0,
                "retriever": "hybrid_tfidf",
                "char_weight": round(char_weight, 3),
            },
        }

    retrieved = []
    snippets = []
    sentiment_counter = Counter()
    for idx, score in picked:
        doc = docs[idx]
        snippets.append(str(doc.get("review_text", "")))
        sentiment_counter[str(doc.get("sentiment_label", "neutral")).lower()] += 1
        retrieved.append(
            {
                "review_id": doc.get("review_id"),
                "product": doc.get("product"),
                "product_name": doc.get("product_name"),
                "date": doc.get("date"),
                "sentiment_label": doc.get("sentiment_label"),
                "score": round(score, 4),
                "snippet": str(doc.get("review_text", ""))[:280],
            }
        )

    topics = _extract_topics(snippets, top_n=5)
    dominant_sentiment = "neutral"
    if sentiment_counter:
        dominant_sentiment = sentiment_counter.most_common(1)[0][0]

    answer = (
        f"Based on {len(retrieved)} retrieved reviews, sentiment is mostly {dominant_sentiment}. "
        f"Recurring themes: {', '.join(topics) if topics else 'insufficient topic signal'}."
    )
    confidence = float(picked[0][1]) if picked else 0.0

    return {
        "question": query,
        "product": product,
        "answer": answer,
        "retrieved": retrieved,
        "summary": {
            "documents_matched": len(retrieved),
            "sentiment_counts": dict(sentiment_counter),
            "topics": topics,
            "confidence": round(confidence, 4),
            "min_similarity": round(min_sim, 4),
            "retriever": "hybrid_tfidf",
            "char_weight": round(char_weight, 3),
        },
    }
