import asyncio
from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors.base import FetchStats
from app.collectors.generic import (
    AmazonJapanCollector,
    LekutaoCollector,
    MerukiCollector,
    MercariCollector,
    RakumaCollector,
    RakutenCollector,
    YahooAuctionsCollector,
)
from app.models import AlertLevel, Item, Keyword
from app.schemas import RawItem
from app.services.dedupe import build_dedupe_key, image_hash_from_url
from app.services.history import record_price, sku_from_title
from app.services.notifications import send_feishu_alert
from app.services.proxy import buyee_url, zenmarket_url
from app.services.scoring import score_item
from app.services.settings import feishu_alerts_enabled


COLLECTORS = [
    MercariCollector(),
    YahooAuctionsCollector(),
    RakumaCollector(),
    RakutenCollector(),
    AmazonJapanCollector(),
    MerukiCollector(),
    LekutaoCollector(),
]


async def collect_for_keywords(keywords: Iterable[Keyword]) -> tuple[list[RawItem], list[FetchStats]]:
    """Fetch items for every (keyword, collector) pair and return (items, per-fetch stats)."""
    tasks = []
    for keyword in keywords:
        for collector in COLLECTORS:
            tasks.append(collector.fetch(keyword.text))

    results = await asyncio.gather(*tasks)
    raw_items: list[RawItem] = []
    all_stats: list[FetchStats] = []

    for result in results:
        # fetch() always returns tuple[list[RawItem], FetchStats] — never raises
        if isinstance(result, Exception):
            continue
        if isinstance(result, tuple) and len(result) == 2:
            items, stats = result
            raw_items.extend(items)
            all_stats.append(stats)
        elif isinstance(result, list):  # legacy safety
            raw_items.extend(result)

    return raw_items, all_stats


def aggregate_fetch_stats(stats: list[FetchStats]) -> dict:
    """Aggregate per-fetch stats into a human-readable summary per platform."""
    by_platform: dict[str, dict] = {}
    for s in stats:
        p = s.platform
        if p not in by_platform:
            by_platform[p] = {
                "attempts": 0,
                "successes": 0,
                "robots_blocked": 0,
                "errors": 0,
                "total_items_found": 0,
                "keywords_attempted": [],
                "error_details": [],
            }
        by_platform[p]["attempts"] += 1
        if s.success:
            by_platform[p]["successes"] += 1
        if s.robots_blocked:
            by_platform[p]["robots_blocked"] += 1
        if s.error:
            by_platform[p]["errors"] += 1
            by_platform[p]["error_details"].append(f"[{s.keyword}] {s.error}")
        by_platform[p]["total_items_found"] += s.items_found
        by_platform[p]["keywords_attempted"].append(s.keyword)

    # Clean up: deduplicate keyword lists, limit error details
    for p in by_platform:
        by_platform[p]["keywords_attempted"] = sorted(set(by_platform[p]["keywords_attempted"]))
        by_platform[p]["error_details"] = by_platform[p]["error_details"][:3]

    return by_platform


async def ingest_items(db: Session, raw_items: Iterable[RawItem]) -> dict[str, int]:
    created = 0
    alerted = 0
    skipped = 0

    for raw in raw_items:
        image_hash = image_hash_from_url(raw.image_url)
        dedupe_key = build_dedupe_key(raw.title, raw.seller, image_hash, raw.price_yen)
        score, level = score_item(db, raw.title, raw.price_yen, raw.publish_time, raw.platform)
        product_url = str(raw.product_url)
        item = Item(
            platform=raw.platform,
            keyword=raw.keyword,
            title=raw.title,
            seller=raw.seller,
            price_yen=raw.price_yen,
            original_price=raw.original_price,
            original_currency=raw.original_currency,
            shipping_fee=raw.shipping_fee,
            publish_time=raw.publish_time,
            seller_rating=raw.seller_rating,
            seller_sales_count=raw.seller_sales_count,
            image_url=raw.image_url,
            image_hash=image_hash,
            product_url=product_url,
            dedupe_key=dedupe_key,
            scarcity_score=score,
            alert_level=level.value,
            buyee_url=buyee_url(product_url, raw.title),
            zenmarket_url=zenmarket_url(product_url, raw.title),
        )
        db.add(item)
        try:
            record_price(db, sku_from_title(raw.title), raw.platform, raw.price_yen, raw.publish_time)
            db.commit()
            db.refresh(item)
            created += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
            continue

        if level == AlertLevel.A and feishu_alerts_enabled(db):
            if await send_feishu_alert(item):
                alerted += 1

    return {"created": created, "skipped": skipped, "alerted": alerted}


async def run_monitor_once(db: Session) -> dict:
    """Run one full monitor cycle and return ingest + fetch statistics."""
    keywords = db.query(Keyword).all()
    raw_items, fetch_stats = await collect_for_keywords(keywords)
    ingest_result = await ingest_items(db, raw_items)
    return {
        **ingest_result,
        "fetch_stats": aggregate_fetch_stats(fetch_stats),
    }
