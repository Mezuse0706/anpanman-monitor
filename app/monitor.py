import asyncio
from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors.generic import (
    AmazonJapanCollector,
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


COLLECTORS = [
    MercariCollector(),
    YahooAuctionsCollector(),
    RakumaCollector(),
    RakutenCollector(),
    AmazonJapanCollector(),
]


async def collect_for_keywords(keywords: Iterable[Keyword]) -> list[RawItem]:
    tasks = []
    for keyword in keywords:
        for collector in COLLECTORS:
            tasks.append(collector.fetch(keyword.text))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    raw_items: list[RawItem] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        raw_items.extend(result)
    return raw_items


async def ingest_items(db: Session, raw_items: Iterable[RawItem]) -> dict[str, int]:
    created = 0
    alerted = 0
    skipped = 0

    for raw in raw_items:
        image_hash = image_hash_from_url(raw.image_url)
        dedupe_key = build_dedupe_key(raw.title, raw.seller, image_hash, raw.price_yen)
        score, level = score_item(db, raw.title, raw.price_yen, raw.publish_time)
        product_url = str(raw.product_url)
        item = Item(
            platform=raw.platform,
            keyword=raw.keyword,
            title=raw.title,
            seller=raw.seller,
            price_yen=raw.price_yen,
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

        if level == AlertLevel.A:
            if await send_feishu_alert(item):
                alerted += 1

    return {"created": created, "skipped": skipped, "alerted": alerted}


async def run_monitor_once(db: Session) -> dict[str, int]:
    keywords = db.query(Keyword).all()
    raw_items = await collect_for_keywords(keywords)
    return await ingest_items(db, raw_items)
