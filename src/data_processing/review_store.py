from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List
import hashlib
import re
import uuid

import pandas as pd
from sqlalchemy import delete, desc, func, select

from src.core.database import (
    DATA_DIR,
    DatasetVersion,
    PreprocessingAudit,
    Product,
    ReviewProcessed,
    ReviewRaw,
    ensure_database,
    now_utc_iso,
    session_scope,
)
from src.core.settings import settings


RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
VERSIONS_DIR = PROCESSED_DIR / "versions"

RAW_DATA_PATH = RAW_DIR / "reviews_raw.csv"
PROCESSED_DATA_PATH = PROCESSED_DIR / "cleaned_reviews.csv"
PREPROCESS_AUDIT_PATH = PROCESSED_DIR / "preprocessing_audit_log.csv"

_STORE_LOCK = RLock()
_LAST_STATUS: "DatasetStatus | None" = None
_LAST_REFRESH_TS: float = 0.0

DEFAULT_PRODUCTS = [
    ("sunscreen", "Sunscreen"),
    ("moisturizer", "Moisturizer"),
    ("cleanser", "Cleanser"),
    ("serum", "Serum"),
]

# Products featured in the TrendForecast-style dashboard UI (brand tabs).
DASHBOARD_PRODUCTS = [
    ("neutrogena", "Neutrogena"),
    ("la_roche_posay", "La Roche-Posay"),
    ("cerave", "CeraVe"),
    ("supergoop", "Supergoop!"),
]

SEED_PRODUCTS = DEFAULT_PRODUCTS + DASHBOARD_PRODUCTS
SEED_VERSION = "v3"

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "its",
    "my",
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


@dataclass
class DatasetStatus:
    raw_path: str
    processed_path: str
    raw_rows: int
    processed_rows: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw_path": self.raw_path,
            "processed_path": self.processed_path,
            "raw_rows": self.raw_rows,
            "processed_rows": self.processed_rows,
        }


def _ensure_data_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _clean_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"http\S+|www\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in text.split() if token and token not in _STOPWORDS]
    return " ".join(tokens)


def _sentiment_label_from_rating(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "neutral"


def _sentiment_score_from_rating(rating: int) -> float:
    mapping = {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.5, 5: 1.0}
    return float(mapping.get(int(rating), 0.0))


def _display_name(product_id: str) -> str:
    by_id = dict(SEED_PRODUCTS)
    return by_id.get(product_id, product_id.replace("_", " ").title())


def _seed_int(key: str, modulo: int) -> int:
    digest = hashlib.sha1((key or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % max(1, int(modulo))


def _seed_records() -> List[Dict[str, Any]]:
    templates = {
        "sunscreen": [
            ("Lightweight sunscreen and no white cast.", 5),
            ("Decent protection but slightly greasy in humid weather.", 3),
            ("Caused irritation and felt heavy.", 1),
            ("Good daily SPF, absorbs quickly.", 4),
            ("No white cast, but reapplication is messy on makeup.", 3),
            ("Great for daily wear, feels weightless.", 5),
        ],
        "moisturizer": [
            ("Hydrating and gentle for my sensitive skin.", 5),
            ("Average hydration and a bit sticky.", 3),
            ("Too oily and caused breakouts.", 2),
            ("Great value and smooth texture.", 4),
            ("Absorbs fast and helps my dry patches.", 5),
            ("Not enough for winter, but good layering.", 3),
        ],
        "cleanser": [
            ("Cleans well without drying my skin.", 5),
            ("Works okay but fragrance is strong.", 3),
            ("Made my skin tight and itchy.", 2),
            ("Good everyday cleanser for oily skin.", 4),
            ("Gentle, but struggled to remove sunscreen.", 3),
            ("Broke me out and felt harsh on my cheeks.", 2),
        ],
        "serum": [
            ("Improved texture and visible glow.", 5),
            ("Good results but expensive for quantity.", 3),
            ("No noticeable effect and caused redness.", 2),
            ("Absorbs fast and works under makeup.", 4),
            ("Helped with dark spots over a few weeks.", 4),
            ("Too strong for me, tingled a lot.", 2),
        ],
        "neutrogena": [
            ("Dry-touch finish, great for oily skin and acne-prone days.", 4),
            ("Good value but a bit of white cast on deeper skin tones.", 3),
            ("Lightweight SPF that layers well under makeup.", 5),
            ("Irritated my skin and felt heavy by afternoon.", 2),
            ("Works well for daily sunscreen, but can pill with moisturizer.", 3),
            ("Great for acne-prone skin, no breakouts so far.", 5),
            ("Finish is matte, but stings around my eyes.", 2),
            ("Solid protection and easy to reapply.", 4),
        ],
        "la_roche_posay": [
            ("Soothing for sensitive skin, texture feels premium.", 5),
            ("Barrier repair feels solid but price is high.", 4),
            ("A little greasy in humid weather, still effective.", 3),
            ("Broke me out after a week, had to stop.", 2),
            ("Calms redness quickly and feels gentle.", 5),
            ("Great for sensitive skin, but can feel heavy mid-day.", 3),
            ("Helped my barrier, fewer irritations this week.", 4),
            ("Did not work for my acne, caused clogged pores.", 2),
        ],
        "cerave": [
            ("Ceramides helped my dry skin, very gentle cleanser.", 5),
            ("Good everyday hydration and fragrance-free.", 4),
            ("Texture is okay, but it pills with sunscreen.", 3),
            ("Stung around my nose, not for me.", 2),
            ("Barrier feels stronger, less dryness overall.", 5),
            ("Reliable and gentle, no irritation.", 4),
            ("Works well, but the finish is a bit tacky.", 3),
            ("Love the ceramides, great for winter skin.", 5),
        ],
        "supergoop": [
            ("No white cast, works like a primer with a soft glow.", 5),
            ("Easy to reapply, but the scent is noticeable.", 4),
            ("Nice finish but feels pricey for the size.", 3),
            ("Too shiny on my skin, had to blot often.", 2),
            ("Great under makeup, but breaks me out sometimes.", 2),
            ("Finish looks nice, but feels oily after a few hours.", 3),
            ("Love the glow, but wish it was less fragranced.", 4),
            ("Good primer feel, but too expensive to repurchase.", 3),
        ],
    }

    source_mix = {
        "neutrogena": [("reddit", 38), ("twitter", 22), ("reviews", 25), ("news", 15)],
        "la_roche_posay": [("reviews", 40), ("news", 22), ("reddit", 20), ("twitter", 18)],
        "cerave": [("reviews", 45), ("reddit", 25), ("twitter", 15), ("news", 15)],
        "supergoop": [("twitter", 32), ("reddit", 28), ("reviews", 25), ("news", 15)],
    }
    volume_base = {
        "sunscreen": 4,
        "moisturizer": 3,
        "cleanser": 3,
        "serum": 2,
        "neutrogena": 6,
        "la_roche_posay": 4,
        "cerave": 5,
        "supergoop": 3,
    }
    volume_trend = {
        "neutrogena": 2,
        "la_roche_posay": 1,
        "cerave": 2,
        "supergoop": -1,
    }
    sentiment_trend = {
        "neutrogena": 1,
        "la_roche_posay": 0,
        "cerave": 1,
        "supergoop": -1,
    }
    source_bias = {
        # Make source-mix simulations visible in the UI (what-if mode).
        "reviews": 1,
        "reddit": -1,
        "twitter": -1,
        "news": 0,
    }

    max_days = 60
    now = datetime.now()
    rows: List[Dict[str, Any]] = []

    # Generate deterministic daily demo data so "Last 7 days" dashboard views are never empty
    # and the brand tabs have distinct curves/volumes/distributions.
    for day_offset in range(0, 60):
        day_date = (now - timedelta(days=day_offset)).replace(hour=12, minute=0, second=0, microsecond=0)
        t = (max_days - 1 - day_offset) / max(1, max_days - 1)  # 0..1 (oldest->newest)
        for product_index, (product_id, _) in enumerate(SEED_PRODUCTS):
            items = templates.get(product_id) or [("Good experience overall.", 4)]

            base = int(volume_base.get(product_id, 2))
            strength = int(volume_trend.get(product_id, 0))
            trend_adjust = int(round((t - 0.5) * 2.0 * strength))
            jitter = int(_seed_int(f"{product_id}:{day_date.strftime('%Y%m%d')}:vol", 5)) - 2  # -2..2
            volume = max(1, base + trend_adjust + jitter)

            mix = source_mix.get(product_id) or [("reviews", 40), ("reddit", 25), ("twitter", 20), ("news", 15)]
            mix_total = sum(weight for _, weight in mix) or 100

            s_strength = int(sentiment_trend.get(product_id, 0))
            s_adjust = int(round((t - 0.5) * 2.0 * s_strength))

            for idx in range(volume):
                choice = _seed_int(
                    f"{product_id}:{day_date.strftime('%Y%m%d')}:{idx}:tmpl:{product_index}",
                    len(items),
                )
                text, base_rating = items[int(choice) % len(items)]
                noise = int(_seed_int(f"{product_id}:{day_date.strftime('%Y%m%d')}:{idx}:noise", 3)) - 1  # -1..1
                rating = max(1, min(5, int(base_rating) + int(s_adjust) + int(noise)))

                roll = int(_seed_int(f"{product_id}:{day_date.strftime('%Y%m%d')}:{idx}:src", mix_total))
                acc = 0
                chosen_source = mix[0][0]
                for key, weight in mix:
                    acc += int(weight)
                    if roll < acc:
                        chosen_source = key
                        break

                rating = max(1, min(5, int(rating) + int(source_bias.get(chosen_source, 0))))

                rows.append(
                    {
                        "review_id": f"seed-{SEED_VERSION}-{product_id}-{day_date.strftime('%Y%m%d')}-{idx}",
                        "date": day_date.strftime("%Y-%m-%d"),
                        "product": product_id,
                        "product_name": _display_name(product_id),
                        "source": chosen_source,
                        "rating": int(rating),
                        "review_text": text,
                        "request_id": None,
                        "created_at": now_utc_iso(),
                    }
                )
    return rows


def _ensure_seed_data() -> bool:
    if settings.app_env.strip().lower() == "production":
        return False

    seed_rows = _seed_records()
    seed_ids = [row["review_id"] for row in seed_rows]
    if not seed_ids:
        return False

    with session_scope() as session:
        # Keep demo data deterministic: if seed IDs differ (version change), replace all seed rows.
        existing_seed_ids = set(
            session.execute(
                select(ReviewRaw.review_id).where(ReviewRaw.review_id.like("seed-%"))
            ).scalars().all()
        )
        desired = set(seed_ids)
        if existing_seed_ids == desired:
            return False

        session.execute(delete(ReviewRaw).where(ReviewRaw.review_id.like("seed-%")))
        session.bulk_save_objects(
            [
                ReviewRaw(
                    review_id=row["review_id"],
                    date=row["date"],
                    product=row["product"],
                    product_name=row["product_name"],
                    source=row["source"],
                    rating=int(row["rating"]),
                    review_text=row["review_text"],
                    request_id=row["request_id"],
                    created_at=row["created_at"],
                )
                for row in seed_rows
            ]
        )
        return True


def _raw_df_from_db() -> pd.DataFrame:
    with session_scope() as session:
        rows = session.execute(
            select(ReviewRaw).order_by(ReviewRaw.date.asc(), ReviewRaw.review_id.asc())
        ).scalars().all()
    data = [
        {
            "review_id": row.review_id,
            "date": row.date,
            "product": row.product,
            "product_name": row.product_name,
            "source": row.source,
            "rating": row.rating,
            "review_text": row.review_text,
            "request_id": row.request_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return pd.DataFrame(data)


def _process_raw_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame(
            columns=[
                "review_id",
                "date",
                "product",
                "product_name",
                "source",
                "rating",
                "review_text",
                "cleaned_text",
                "sentiment_label",
                "sentiment_score",
                "processed_at",
            ]
        )

    processed = raw_df.copy()
    processed["rating"] = (
        pd.to_numeric(processed.get("rating"), errors="coerce")
        .fillna(3)
        .astype(int)
        .clip(lower=1, upper=5)
    )
    processed["review_text"] = processed.get("review_text", "").fillna("").astype(str)
    processed["product"] = (
        processed.get("product", "general").fillna("general").astype(str).str.lower().str.strip()
    )
    processed["product_name"] = processed.apply(
        lambda row: str(row.get("product_name", "")).strip() or _display_name(row["product"]),
        axis=1,
    )
    processed["date"] = pd.to_datetime(processed.get("date"), errors="coerce").fillna(
        pd.Timestamp(datetime.now().date())
    )
    processed["date"] = processed["date"].dt.strftime("%Y-%m-%d")
    processed["cleaned_text"] = processed["review_text"].map(_clean_text)
    processed["sentiment_label"] = processed["rating"].map(_sentiment_label_from_rating)
    processed["sentiment_score"] = processed["rating"].map(_sentiment_score_from_rating)
    processed["processed_at"] = now_utc_iso()

    return processed[
        [
            "review_id",
            "date",
            "product",
            "product_name",
            "source",
            "rating",
            "review_text",
            "cleaned_text",
            "sentiment_label",
            "sentiment_score",
            "processed_at",
        ]
    ]


def _store_processed_in_db(processed_df: pd.DataFrame) -> None:
    with session_scope() as session:
        session.execute(delete(ReviewProcessed))
        if processed_df.empty:
            return
        session.bulk_save_objects(
            [
                ReviewProcessed(
                    review_id=str(row.review_id),
                    date=str(row.date),
                    product=str(row.product),
                    product_name=str(row.product_name),
                    source=str(row.source),
                    rating=int(row.rating),
                    review_text=str(row.review_text),
                    cleaned_text=str(row.cleaned_text),
                    sentiment_label=str(row.sentiment_label),
                    sentiment_score=float(row.sentiment_score),
                    processed_at=str(row.processed_at),
                )
                for row in processed_df.itertuples(index=False)
            ]
        )


def _record_dataset_version(raw_rows: int, processed_rows: int, note: str = "") -> None:
    version_id = f"v-{uuid.uuid4().hex[:12]}"
    created_at = now_utc_iso()
    with session_scope() as session:
        session.add(
            DatasetVersion(
                version_id=version_id,
                created_at=created_at,
                raw_rows=int(raw_rows),
                processed_rows=int(processed_rows),
                note=note,
            )
        )

    if PROCESSED_DATA_PATH.exists():
        snapshot_path = VERSIONS_DIR / f"cleaned_reviews_{version_id}.csv"
        snapshot_path.write_bytes(PROCESSED_DATA_PATH.read_bytes())
        snapshots = sorted(
            VERSIONS_DIR.glob("cleaned_reviews_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_snapshot in snapshots[30:]:
            old_snapshot.unlink(missing_ok=True)


def _record_preprocessing_audit(raw_rows: int, processed_df: pd.DataFrame, note: str = "") -> None:
    run_id = f"prep-{uuid.uuid4().hex[:12]}"
    created_at = now_utc_iso()
    processed_rows = int(len(processed_df))
    empty_text_rows = (
        int((processed_df["review_text"].astype(str).str.strip() == "").sum())
        if not processed_df.empty
        else 0
    )
    avg_tokens = 0.0

    if not processed_df.empty and "cleaned_text" in processed_df.columns:
        token_counts = (
            processed_df["cleaned_text"]
            .fillna("")
            .astype(str)
            .map(lambda text: len([tok for tok in text.split(" ") if tok]))
        )
        avg_tokens = float(token_counts.mean()) if len(token_counts) else 0.0

    with session_scope() as session:
        session.add(
            PreprocessingAudit(
                run_id=run_id,
                created_at=created_at,
                raw_rows=int(raw_rows),
                processed_rows=processed_rows,
                rows_with_empty_text=empty_text_rows,
                avg_clean_token_count=round(avg_tokens, 3),
                note=note,
            )
        )

    audit_row = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "created_at": created_at,
                "raw_rows": int(raw_rows),
                "processed_rows": processed_rows,
                "rows_with_empty_text": empty_text_rows,
                "avg_clean_token_count": round(avg_tokens, 3),
                "note": note,
            }
        ]
    )
    write_header = not PREPROCESS_AUDIT_PATH.exists()
    audit_row.to_csv(PREPROCESS_AUDIT_PATH, mode="a", header=write_header, index=False)


def initialize_datasets(force_refresh: bool = False) -> DatasetStatus:
    global _LAST_STATUS, _LAST_REFRESH_TS
    with _STORE_LOCK:
        ensure_database()
        _ensure_data_dirs()
        seed_changed = _ensure_seed_data()
        if seed_changed:
            force_refresh = True
            _LAST_STATUS = None
            _LAST_REFRESH_TS = 0.0

        now_ts = datetime.now().timestamp()
        if _LAST_STATUS and not force_refresh and now_ts - _LAST_REFRESH_TS < 3:
            return _LAST_STATUS

        raw_df = _raw_df_from_db()
        processed_df = _process_raw_dataframe(raw_df)

        raw_df.to_csv(RAW_DATA_PATH, index=False)
        processed_df.to_csv(PROCESSED_DATA_PATH, index=False)
        _store_processed_in_db(processed_df)
        _record_preprocessing_audit(len(raw_df), processed_df, note="refresh")

        status = DatasetStatus(
            raw_path=str(RAW_DATA_PATH),
            processed_path=str(PROCESSED_DATA_PATH),
            raw_rows=int(len(raw_df)),
            processed_rows=int(len(processed_df)),
        )

        should_version = True
        if _LAST_STATUS:
            should_version = (
                _LAST_STATUS.raw_rows != status.raw_rows
                or _LAST_STATUS.processed_rows != status.processed_rows
            )
        if should_version:
            _record_dataset_version(status.raw_rows, status.processed_rows, note="refresh")

        _LAST_STATUS = status
        _LAST_REFRESH_TS = now_ts
        return status


def append_review(
    text: str,
    product: str = "general",
    source: str = "api",
    rating: int = 3,
    request_id: str | None = None,
) -> DatasetStatus:
    review_text = (text or "").strip()
    if not review_text:
        return initialize_datasets()

    with _STORE_LOCK:
        ensure_database()
        _ensure_data_dirs()
        _ensure_seed_data()

        safe_product = (product or "general").strip().lower() or "general"
        safe_rating = max(1, min(int(rating), 5))
        review_id = f"{source}-{uuid.uuid4().hex[:12]}"
        today = datetime.now().strftime("%Y-%m-%d")

        with session_scope() as session:
            session.add(
                ReviewRaw(
                    review_id=review_id,
                    date=today,
                    product=safe_product,
                    product_name=_display_name(safe_product),
                    source=source,
                    rating=safe_rating,
                    review_text=review_text,
                    request_id=request_id,
                    created_at=now_utc_iso(),
                )
            )

    return initialize_datasets(force_refresh=True)


def append_reviews_bulk(
    reviews: List[Dict[str, Any]],
    *,
    source: str = "ingestion",
    request_id: str | None = None,
) -> DatasetStatus:
    rows = list(reviews or [])
    if not rows:
        return initialize_datasets()

    with _STORE_LOCK:
        ensure_database()
        _ensure_data_dirs()
        _ensure_seed_data()

        objects: List[ReviewRaw] = []
        today = datetime.now().strftime("%Y-%m-%d")
        for item in rows:
            review_text = str(item.get("text") or item.get("review_text") or "").strip()
            if not review_text:
                continue
            safe_product = str(item.get("product") or "general").strip().lower() or "general"
            safe_rating = max(1, min(int(item.get("rating", 3) or 3), 5))
            review_id = f"{source}-{uuid.uuid4().hex[:12]}"
            date_value = str(item.get("date") or today)[:20]
            objects.append(
                ReviewRaw(
                    review_id=review_id,
                    date=date_value,
                    product=safe_product,
                    product_name=_display_name(safe_product),
                    source=str(item.get("source") or source)[:80],
                    rating=safe_rating,
                    review_text=review_text,
                    request_id=(request_id or None),
                    created_at=now_utc_iso(),
                )
            )

        if objects:
            with session_scope() as session:
                session.bulk_save_objects(objects)

    return initialize_datasets(force_refresh=True)


def list_products() -> List[Dict[str, str]]:
    initialize_datasets()
    with session_scope() as session:
        rows = session.execute(select(Product).order_by(Product.name.asc())).scalars().all()

    products = [{"id": row.id, "name": row.name} for row in rows]
    if products:
        return products
    return [{"id": pid, "name": name} for pid, name in DEFAULT_PRODUCTS]


def product_trends(product: str) -> List[Dict[str, Any]]:
    initialize_datasets()
    if not PROCESSED_DATA_PATH.exists():
        return []
    df = pd.read_csv(PROCESSED_DATA_PATH)
    if df.empty:
        return []

    df["product"] = df["product"].astype(str).str.lower().str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    safe_product = (product or "").strip().lower()
    if safe_product:
        df = df[df["product"] == safe_product]
    if df.empty:
        return []

    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    grouped = (
        df.groupby("month")
        .agg(sentiment_score=("sentiment_score", "mean"), volume=("review_id", "count"))
        .reset_index()
        .sort_values("month")
    )
    grouped["date"] = grouped["month"].dt.strftime("%Y-%m-%d")
    grouped["sentiment_score"] = grouped["sentiment_score"].round(3)

    return [
        {
            "date": str(row.date),
            "sentiment_score": float(row.sentiment_score),
            "volume": int(row.volume),
        }
        for row in grouped.itertuples(index=False)
    ]


def dataset_versions(limit: int = 25) -> List[Dict[str, Any]]:
    initialize_datasets()
    with session_scope() as session:
        rows = session.execute(
            select(DatasetVersion)
            .order_by(desc(DatasetVersion.created_at))
            .limit(max(1, int(limit)))
        ).scalars().all()
    return [
        {
            "version_id": row.version_id,
            "created_at": row.created_at,
            "raw_rows": int(row.raw_rows),
            "processed_rows": int(row.processed_rows),
            "note": row.note,
        }
        for row in rows
    ]


def list_preprocessing_audits(limit: int = 25) -> List[Dict[str, Any]]:
    initialize_datasets()
    with session_scope() as session:
        rows = session.execute(
            select(PreprocessingAudit)
            .order_by(desc(PreprocessingAudit.created_at))
            .limit(max(1, int(limit)))
        ).scalars().all()
    return [
        {
            "run_id": row.run_id,
            "created_at": row.created_at,
            "raw_rows": int(row.raw_rows),
            "processed_rows": int(row.processed_rows),
            "rows_with_empty_text": int(row.rows_with_empty_text),
            "avg_clean_token_count": float(row.avg_clean_token_count),
            "note": row.note,
        }
        for row in rows
    ]
