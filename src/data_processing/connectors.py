from __future__ import annotations

import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.core.database import DATA_DIR
from src.data_processing.review_store import append_reviews_bulk


def _parse_connector_list(raw: str | None) -> List[str]:
    items = [item.strip().lower() for item in (raw or "").split(",")]
    return [item for item in items if item]


def _synthetic_rows(batch_size: int, source: str) -> List[Dict[str, Any]]:
    products = ["sunscreen", "moisturizer", "cleanser", "serum"]
    templates = [
        "Great {product} texture and visible improvement.",
        "{product} feels heavy and caused mild irritation.",
        "Decent {product}, but price feels high.",
        "Best {product} for daily routine so far.",
        "{product} works but the fragrance is strong.",
    ]

    rows: List[Dict[str, Any]] = []
    today = datetime.now().strftime("%Y-%m-%d")
    for _ in range(max(1, int(batch_size))):
        product = random.choice(products)
        text = random.choice(templates).format(product=product)
        rating = random.choice([2, 3, 4, 5])
        rows.append(
            {
                "date": today,
                "product": product,
                "rating": int(rating),
                "review_text": text,
                "source": f"{source}_synthetic",
            }
        )
    return rows


def _local_csv_rows(batch_size: int, source: str, path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    if df.empty:
        return []

    # Normalise column options.
    if "review_text" not in df.columns and "text" in df.columns:
        df["review_text"] = df["text"]
    if "product" not in df.columns:
        df["product"] = "general"
    if "rating" not in df.columns:
        df["rating"] = 3
    if "date" not in df.columns:
        df["date"] = datetime.now().strftime("%Y-%m-%d")
    if "source" not in df.columns:
        df["source"] = f"{source}_local_csv"

    n = max(1, min(int(batch_size), int(len(df))))
    sample = df.sample(n=n, replace=len(df) < n, random_state=random.randint(1, 1_000_000))

    rows: List[Dict[str, Any]] = []
    for row in sample.itertuples(index=False):
        review_text = str(getattr(row, "review_text", "") or "").strip()
        if not review_text:
            continue
        rows.append(
            {
                "date": str(getattr(row, "date", ""))[:20],
                "product": str(getattr(row, "product", "general") or "general"),
                "rating": int(getattr(row, "rating", 3) or 3),
                "review_text": review_text,
                "source": str(getattr(row, "source", f"{source}_local_csv"))[:80],
            }
        )
    return rows


def available_connectors() -> List[str]:
    return ["synthetic", "local_csv"]


def ingest_reviews(
    *,
    source: str,
    batch_size: int = 4,
    connector: str | None = None,
) -> Dict[str, Any]:
    safe_source = (source or "ingestion").strip()[:50] or "ingestion"
    safe_batch = max(1, min(int(batch_size or 4), 1000))

    connectors = [str(connector).strip().lower()] if connector else _parse_connector_list(os.environ.get("INGESTION_CONNECTORS"))
    if not connectors:
        connectors = ["synthetic"]

    external_dir = DATA_DIR / "external"
    local_csv_path = Path(
        os.environ.get("INGESTION_LOCAL_CSV_PATH", str(external_dir / "reviews.csv"))
    )

    selected_rows: List[Dict[str, Any]] = []
    stats: List[Dict[str, Any]] = []
    for name in connectors:
        remaining = safe_batch - len(selected_rows)
        if remaining <= 0:
            break
        if name == "synthetic":
            rows = _synthetic_rows(remaining, safe_source)
        elif name == "local_csv":
            rows = _local_csv_rows(remaining, safe_source, local_csv_path)
        else:
            rows = []
        stats.append({"connector": name, "selected": int(len(rows))})
        selected_rows.extend(rows)

    selected_rows = selected_rows[:safe_batch]
    status = append_reviews_bulk(selected_rows, source=f"{safe_source}_ingestion")
    return {
        "requested": safe_batch,
        "inserted_reviews": int(len(selected_rows)),
        "connectors": stats,
        "dataset": status.as_dict(),
    }
