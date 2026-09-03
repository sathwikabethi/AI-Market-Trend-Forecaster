from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd

from src.data_processing.review_store import PROCESSED_DATA_PATH, initialize_datasets


_REGION_BUCKETS = [
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("CA", "Canada"),
    ("AU", "Australia"),
    ("IN", "India"),
]

_SOURCE_CATEGORIES = [
    ("reddit", "Reddit", "warm"),
    ("twitter", "Twitter", "cool"),
    ("reviews", "Product Reviews", "gold"),
    ("news", "News Articles", "slate"),
]
_SOURCE_KEYS = [key for key, _, _ in _SOURCE_CATEGORIES]

_SENTIMENT_COLORS = {
    "positive": "#22c55e",
    "neutral": "#6b7280",
    "negative": "#ef4444",
}

_PALETTE = ["#22d3ee", "#a855f7", "#34d399", "#f59e0b", "#94a3b8", "#38bdf8"]

# Products highlighted in the TrendForecast-style dashboard UI. We keep the
# IDs stable so the frontend can filter without fetching /products first.
_DASHBOARD_PRODUCTS = [
    ("neutrogena", "Neutrogena"),
    ("la_roche_posay", "La Roche-Posay"),
    ("cerave", "CeraVe"),
    ("supergoop", "Supergoop!"),
]
_DASHBOARD_PRODUCT_IDS = {pid for pid, _ in _DASHBOARD_PRODUCTS}

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
    "your",
    "skin",
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _as_date(value: Any) -> datetime | None:
    try:
        return pd.to_datetime(value, errors="coerce").to_pydatetime()
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _percent_distribution(counts: List[int]) -> List[int]:
    total = sum(max(0, int(c)) for c in counts)
    if total <= 0:
        return [0 for _ in counts]
    raw = [100.0 * max(0, int(c)) / total for c in counts]
    rounded = [int(round(x)) for x in raw]
    # Fix rounding drift so the final sum is 100 (best-effort).
    drift = 100 - sum(rounded)
    if drift != 0:
        idx = max(range(len(rounded)), key=lambda i: raw[i]) if rounded else 0
        if 0 <= idx < len(rounded):
            rounded[idx] = max(0, rounded[idx] + drift)
    return rounded


def _format_number(n: int) -> str:
    return f"{int(n):,}"


def _sentiment_percent(avg_score: float) -> int:
    # sentiment_score in [-1, 1] -> 0..100
    return int(round(_clamp((avg_score + 1.0) / 2.0, 0.0, 1.0) * 100))


def _day_labels(days: int) -> List[str]:
    today = datetime.now().date()
    start = today - timedelta(days=max(1, int(days)) - 1)
    result = []
    for offset in range(max(1, int(days))):
        current = start + timedelta(days=offset)
        result.append(current.strftime("%m/%d"))
    return result


def _hash_bucket(value: str, modulo: int) -> int:
    digest = hashlib.sha1((value or "").encode("utf-8")).digest()
    return int(digest[0]) % max(1, int(modulo))


def _source_bucket(source: str) -> str:
    s = (source or "").strip().lower()
    if "reddit" in s:
        return "reddit"
    if "twitter" in s or s == "x":
        return "twitter"
    if "news" in s:
        return "news"
    return "reviews"


def _stable_seed(value: str) -> int:
    digest = hashlib.sha1((value or "").encode("utf-8")).digest()
    # Keep within 32-bit int range for pandas random_state.
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _parse_source_mix(value: Any) -> Dict[str, int] | None:
    """Parse a source mix query value into normalized percentages (sum to 100).

    Accepts:
    - dict-like {"reddit": 35, "twitter": 25, ...}
    - string "reddit:35,twitter:25,reviews:30,news:10" (also supports "=")
    """
    if value is None:
        return None

    raw: Dict[str, int] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            key = str(k or "").strip().lower()
            if not key:
                continue
            try:
                raw[key] = int(round(float(v)))
            except Exception:
                continue
    else:
        text = str(value or "").strip()
        if not text:
            return None
        parts = [p.strip() for p in re.split(r"[,;]", text) if p.strip()]
        for part in parts:
            sep = ":" if ":" in part else ("=" if "=" in part else None)
            if not sep:
                continue
            k, v = part.split(sep, 1)
            key = str(k or "").strip().lower()
            if not key:
                continue
            v = re.sub(r"[^0-9.+-]", "", str(v or ""))
            if not v:
                continue
            try:
                raw[key] = int(round(float(v)))
            except Exception:
                continue

    if not raw:
        return None

    # Normalize keys onto our four supported buckets.
    normalized: Dict[str, int] = {key: 0 for key in _SOURCE_KEYS}
    for k, v in raw.items():
        bucket = _source_bucket(k)
        if bucket not in normalized:
            continue
        normalized[bucket] = int(max(0, min(100, int(v))))

    total = sum(int(normalized.get(k, 0)) for k in _SOURCE_KEYS)
    if total <= 0:
        return None

    # Scale to 100, keep drift on the last key.
    result: Dict[str, int] = {}
    used = 0
    for idx, key in enumerate(_SOURCE_KEYS):
        value_int = int(max(0, normalized.get(key, 0)))
        if idx == len(_SOURCE_KEYS) - 1:
            result[key] = max(0, 100 - used)
        else:
            pct = int(round(100.0 * value_int / total))
            pct = max(0, min(100 - used, pct))
            result[key] = pct
            used += pct
    drift = 100 - sum(result.values())
    if drift != 0:
        last = _SOURCE_KEYS[-1]
        result[last] = max(0, min(100, int(result.get(last, 0)) + drift))
    return result


def _mix_to_counts(total: int, mix: Dict[str, int]) -> Dict[str, int]:
    total_int = max(0, int(total))
    if total_int <= 0:
        return {key: 0 for key in _SOURCE_KEYS}

    safe = {key: int(max(0, min(100, int(mix.get(key, 0))))) for key in _SOURCE_KEYS}
    # Use percentages even if they don't sum to 100 by scaling.
    pct_total = sum(safe.values())
    if pct_total <= 0:
        return {key: 0 for key in _SOURCE_KEYS}
    scaled = {key: (safe[key] / pct_total) for key in _SOURCE_KEYS}

    counts = {key: int(round(total_int * scaled[key])) for key in _SOURCE_KEYS}
    drift = total_int - sum(counts.values())
    if drift != 0:
        ordered = sorted(_SOURCE_KEYS, key=lambda k: scaled.get(k, 0.0), reverse=True)
        idx = 0
        while drift != 0 and ordered:
            key = ordered[idx % len(ordered)]
            if drift > 0:
                counts[key] += 1
                drift -= 1
            else:
                if counts[key] > 0:
                    counts[key] -= 1
                    drift += 1
            idx += 1
    return counts


def _apply_source_mix(df: pd.DataFrame, mix: Dict[str, int], *, seed: int) -> pd.DataFrame:
    """Resample rows to approximate a desired source mix (demo/what-if support)."""
    if df.empty:
        return df

    frame = df.copy()
    frame["source_bucket"] = frame["source"].astype(str).map(_source_bucket)
    total = int(len(frame))
    desired = _mix_to_counts(total, mix)

    sampled: list[pd.DataFrame] = []
    used = 0
    for key in _SOURCE_KEYS:
        want = int(desired.get(key, 0))
        if want <= 0:
            continue
        subset = frame.loc[frame["source_bucket"] == key].copy()
        if subset.empty:
            continue
        state = _stable_seed(f"{seed}:{key}")
        replace = int(len(subset)) < want
        sampled.append(subset.sample(n=want, replace=replace, random_state=state))
        used += want

    if not sampled:
        return df

    out = pd.concat(sampled, ignore_index=True)
    if int(len(out)) < total:
        # If we couldn't satisfy the requested mix (missing buckets), fill
        # remaining rows from the overall frame to keep counts stable.
        remaining = total - int(len(out))
        state = _stable_seed(f"{seed}:fill")
        out = pd.concat(
            [out, frame.sample(n=remaining, replace=int(len(frame)) < remaining, random_state=state)],
            ignore_index=True,
        )

    return out


def _extract_topics(texts: List[str], top_n: int = 12) -> List[str]:
    tokens: list[str] = []
    for text in texts:
        for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", str(text or "").lower()):
            token = token.strip("-'")
            if len(token) < 4 or token in _TOKEN_STOPWORDS:
                continue
            tokens.append(token)
    counts = Counter(tokens)
    return [token for token, _ in counts.most_common(max(1, int(top_n)))]


def _normalize_query(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\\s]", " ", str(value or "").lower())
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    return cleaned


def _apply_topic_filter(df: pd.DataFrame, topic: str | None) -> pd.DataFrame:
    if df.empty:
        return df
    query = _normalize_query(topic or "")
    if not query:
        return df
    col = "cleaned_text" if "cleaned_text" in df.columns else "review_text"
    series = df[col].astype(str).str.lower()
    mask = series.str.contains(query, regex=False)
    return df.loc[mask].copy()


def _window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return df
    end = datetime.now().date()
    start = end - timedelta(days=max(1, int(days)) - 1)
    mask = (df["date_dt"].dt.date >= start) & (df["date_dt"].dt.date <= end)
    return df.loc[mask].copy()


def _previous_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return df
    end = datetime.now().date() - timedelta(days=max(1, int(days)))
    start = end - timedelta(days=max(1, int(days)) - 1)
    mask = (df["date_dt"].dt.date >= start) & (df["date_dt"].dt.date <= end)
    return df.loc[mask].copy()


def _daily_sentiment_series(df: pd.DataFrame, days: int) -> List[Dict[str, Any]]:
    labels = _day_labels(days)
    if df.empty:
        return [{"day": day, "value": 50.0} for day in labels]

    frame = df.dropna(subset=["date_dt"]).copy()
    frame["day"] = frame["date_dt"].dt.strftime("%m/%d")
    daily = (
        frame.groupby("day", as_index=False)
        .agg(sentiment=("sentiment_score", "mean"))
    )
    by_day = {str(row.day): float(row.sentiment) for row in daily.itertuples(index=False)}
    series = []
    last_value = 50.0
    for day in labels:
        if day in by_day and pd.notna(by_day[day]):
            last_value = float(_sentiment_percent(float(by_day[day])))
        series.append({"day": day, "value": float(last_value)})
    return series


def _ensure_processed_df() -> pd.DataFrame:
    initialize_datasets()
    if not PROCESSED_DATA_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(PROCESSED_DATA_PATH)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    if "date" not in df.columns:
        df["date"] = datetime.now().strftime("%Y-%m-%d")
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_dt"])
    for col, default in (
        ("product", "general"),
        ("product_name", "General"),
        ("review_id", ""),
        ("review_text", ""),
        ("cleaned_text", ""),
        ("source", "reviews"),
        ("sentiment_label", "neutral"),
        ("sentiment_score", 0.0),
    ):
        if col not in df.columns:
            df[col] = default
    return df


def dashboard_overview(
    *,
    product: str | None = None,
    days: int = 7,
    topic: str | None = None,
    source_mix: Any | None = None,
) -> Dict[str, Any]:
    safe_days = max(1, min(int(days or 7), 60))
    df = _ensure_processed_df()
    df_win_all = _window(df, safe_days)
    df_prev_all = _previous_window(df, safe_days)

    safe_product = (product or "").strip().lower() or None
    if safe_product == "all":
        safe_product = None

    # Prefer dashboard products for the aggregated view so the UI matches the
    # brand tabs even if the dataset contains additional categories.
    df_win_dash = df_win_all
    df_prev_dash = df_prev_all
    if not safe_product and not df_win_all.empty and "product" in df_win_all.columns:
        dash_mask = df_win_all["product"].astype(str).str.lower().str.strip().isin(_DASHBOARD_PRODUCT_IDS)
        df_win_dash = df_win_all.loc[dash_mask].copy()
        df_prev_dash = df_prev_all.loc[
            df_prev_all["product"].astype(str).str.lower().str.strip().isin(_DASHBOARD_PRODUCT_IDS)
        ].copy()
        if df_win_dash.empty:
            # Fall back to all products if none of the dashboard IDs are present.
            df_win_dash = df_win_all
            df_prev_dash = df_prev_all

    if safe_product:
        df_win = df_win_all[df_win_all["product"].astype(str).str.lower().str.strip() == safe_product].copy()
        df_prev = df_prev_all[df_prev_all["product"].astype(str).str.lower().str.strip() == safe_product].copy()
    else:
        df_win = df_win_dash
        df_prev = df_prev_dash

    df_win = _apply_topic_filter(df_win, topic)
    df_prev = _apply_topic_filter(df_prev, topic)

    mix = _parse_source_mix(source_mix)
    if mix:
        seed = _stable_seed(f"{safe_product or 'all'}:{safe_days}:{topic or ''}:{mix}")
        df_win = _apply_source_mix(df_win, mix, seed=seed)
        df_prev = _apply_source_mix(df_prev, mix, seed=seed + 19)

    mentions = int(len(df_win))
    prev_mentions = int(len(df_prev))
    growth_pct = 0.0
    if prev_mentions > 0:
        growth_pct = 100.0 * (mentions - prev_mentions) / prev_mentions

    avg_sent = float(df_win["sentiment_score"].mean()) if mentions else 0.0
    sentiment_score = _sentiment_percent(avg_sent)

    helper = f"Last {safe_days} days"
    mentions_progress = 0.0
    if mentions + prev_mentions > 0:
        mentions_progress = 100.0 * mentions / (mentions + prev_mentions)
    growth_progress = _clamp(50.0 + (growth_pct * 1.25), 0.0, 100.0)

    kpis = [
        {
            "helper": helper,
            "label": "Overall Sentiment Score",
            "value": str(sentiment_score),
            "progress": float(sentiment_score),
            "accent": "#22d3ee",
        },
        {
            "helper": helper,
            "label": "Total Mentions",
            "value": _format_number(mentions),
            "progress": float(round(_clamp(mentions_progress, 0.0, 100.0), 1)),
            "accent": "#22d3ee",
        },
        {
            "helper": helper,
            "label": "Avg Growth Rate",
            "value": f"{'+' if growth_pct >= 0 else ''}{growth_pct:.1f}%",
            "progress": float(round(growth_progress, 1)),
            "accent": "#22d3ee",
        },
    ]

    title = "Aggregated Market Trend"
    subtitle = f"{safe_days}-Day Trailing Overview"

    # Trend series.
    if safe_product:
        product_name = (
            str(df_win["product_name"].iloc[0])
            if mentions and "product_name" in df_win.columns
            else safe_product.replace("_", " ").title()
        )
        trend = {
            "mode": "single",
            "line": {
                "key": safe_product,
                "label": product_name,
                "color": _PALETTE[0],
                "data": _daily_sentiment_series(df_win, safe_days),
            },
        }
        title = f"{product_name} Sentiment Trend"
    else:
        product_rows = (
            df_win_dash[["product", "product_name"]]
            .drop_duplicates()
            .sort_values("product_name")
            .to_dict("records")
            if not df_win_dash.empty
            else []
        )
        lines = []
        for idx, row in enumerate(product_rows[:6]):
            pid = str(row.get("product", "") or "").strip().lower()
            if not pid:
                continue
            name = str(row.get("product_name", "") or pid.replace("_", " ").title())
            df_pid = df_win_dash[df_win_dash["product"].astype(str).str.lower().str.strip() == pid].copy()
            lines.append(
                {
                    "key": pid,
                    "label": name,
                    "color": _PALETTE[idx % len(_PALETTE)],
                    "data": _daily_sentiment_series(df_pid, safe_days),
                }
            )
        trend = {"mode": "multi", "lines": lines}

    # Sentiment distribution.
    if safe_product:
        counts = Counter(str(x or "neutral").lower() for x in df_win.get("sentiment_label", []))
        pos = int(counts.get("positive", 0))
        neu = int(counts.get("neutral", 0))
        neg = int(counts.get("negative", 0))
        perc = _percent_distribution([pos, neu, neg])
        positive_pct = perc[0] if perc else 0
        sentiment = {
            "center_value": f"{positive_pct}%",
            "center_label": "Positive",
            "items": [
                {"label": "Positive", "value": int(perc[0]), "color": _SENTIMENT_COLORS["positive"]},
                {"label": "Neutral", "value": int(perc[1]), "color": _SENTIMENT_COLORS["neutral"]},
                {"label": "Negative", "value": int(perc[2]), "color": _SENTIMENT_COLORS["negative"]},
            ],
        }
    else:
        items = []
        by_product = (
            df_win_dash.groupby(["product", "product_name"])
            .agg(avg=("sentiment_score", "mean"))
            .reset_index()
            .sort_values("product_name")
        ) if not df_win_dash.empty else pd.DataFrame()
        for idx, row in by_product.iterrows():
            name = str(row.get("product_name") or row.get("product") or "General")
            pct = _sentiment_percent(_safe_float(row.get("avg", 0.0)))
            items.append({"label": name, "value": int(pct), "color": _PALETTE[int(idx) % len(_PALETTE)]})
        avg_pct = int(round(sum(item["value"] for item in items) / max(1, len(items)))) if items else sentiment_score
        sentiment = {
            "center_value": f"{avg_pct}%",
            "center_label": "Avg Sentiment",
            "items": items[:6],
        }

    # Regions: deterministic buckets from review ids.
    region_counts = [0 for _ in _REGION_BUCKETS]
    for rid in df_win.get("review_id", []):
        idx = _hash_bucket(str(rid or ""), len(_REGION_BUCKETS))
        region_counts[idx] += 1
    region_perc = _percent_distribution(region_counts)
    regions = [
        {"code": code, "label": label, "value": int(region_perc[idx])}
        for idx, (code, label) in enumerate(_REGION_BUCKETS)
    ]

    # Sources: either simulated mix or derived from source strings.
    if mix:
        sources = []
        for key, label, tone in _SOURCE_CATEGORIES:
            sources.append({"key": key, "label": label, "value": int(mix.get(key, 0)), "tone": tone})
    else:
        source_counts = Counter(_source_bucket(str(s or "")) for s in df_win.get("source", []))
        source_perc = _percent_distribution([int(source_counts.get(k, 0)) for k in _SOURCE_KEYS])
        sources = []
        for idx, (key, label, tone) in enumerate(_SOURCE_CATEGORIES):
            sources.append(
                {"key": key, "label": label, "value": int(source_perc[idx]), "tone": tone}
            )

    # Topics: extracted from review texts.
    topics_raw = _extract_topics(list(df_win.get("review_text", [])[:500]), top_n=12)
    topics = []
    for idx, token in enumerate(topics_raw[:12]):
        label = token.replace("_", " ").title()
        topics.append({"label": label, "highlighted": idx < 3})

    return {
        "range_days": safe_days,
        "product": safe_product,
        "title": title,
        "subtitle": subtitle,
        "kpis": kpis,
        "trend": trend,
        "sentiment": sentiment,
        "regions": regions,
        "sources": sources,
        "topics": topics,
    }


def list_dashboard_reviews(
    *,
    product: str | None = None,
    days: int = 7,
    topic: str | None = None,
    source: str | None = None,
    region: str | None = None,
    limit: int = 60,
) -> List[Dict[str, Any]]:
    safe_days = max(1, min(int(days or 7), 60))
    safe_limit = max(1, min(int(limit or 60), 200))

    df = _ensure_processed_df()
    df_win_all = _window(df, safe_days)

    safe_product = (product or "").strip().lower() or None
    if safe_product == "all":
        safe_product = None

    df_win = df_win_all
    if safe_product:
        df_win = df_win_all[df_win_all["product"].astype(str).str.lower().str.strip() == safe_product].copy()
    else:
        if not df_win_all.empty and "product" in df_win_all.columns:
            dash_mask = df_win_all["product"].astype(str).str.lower().str.strip().isin(_DASHBOARD_PRODUCT_IDS)
            df_win = df_win_all.loc[dash_mask].copy()
            if df_win.empty:
                df_win = df_win_all

    df_win = _apply_topic_filter(df_win, topic)

    safe_source = (source or "").strip().lower() or None
    if safe_source:
        df_win["source_bucket"] = df_win["source"].astype(str).map(_source_bucket)
        df_win = df_win.loc[df_win["source_bucket"] == safe_source].copy()

    safe_region = (region or "").strip().upper() or None
    if safe_region:
        idx = None
        for pos, (code, _) in enumerate(_REGION_BUCKETS):
            if code.upper() == safe_region:
                idx = pos
                break
        if idx is not None and not df_win.empty:
            df_win = df_win.loc[
                df_win["review_id"].astype(str).map(
                    lambda rid: _hash_bucket(str(rid or ""), len(_REGION_BUCKETS)) == idx
                )
            ].copy()

    if df_win.empty:
        return []

    frame = df_win.dropna(subset=["date_dt"]).copy()
    frame = frame.sort_values(["date_dt", "review_id"], ascending=[False, False])

    result: List[Dict[str, Any]] = []
    for row in frame.head(safe_limit).itertuples(index=False):
        result.append(
            {
                "review_id": str(getattr(row, "review_id", "")),
                "date": str(getattr(row, "date", "")),
                "product": str(getattr(row, "product", "")),
                "product_name": str(getattr(row, "product_name", "")),
                "source": str(getattr(row, "source", "")),
                "rating": _safe_int(getattr(row, "rating", 3), default=3),
                "sentiment_label": str(getattr(row, "sentiment_label", "neutral")),
                "sentiment_score": _safe_float(getattr(row, "sentiment_score", 0.0), default=0.0),
                "review_text": str(getattr(row, "review_text", "")),
            }
        )

    return result
