from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertLevel, HistoricalPrice
from app.services.history import sku_from_title

RARE_TERMS = ("美品", "未使用", "限定", "廃盤")


def _age_minutes(publish_time: datetime | None) -> float | None:
    if publish_time is None:
        return None
    now = datetime.now(timezone.utc)
    if publish_time.tzinfo is None:
        publish_time = publish_time.replace(tzinfo=timezone.utc)
    return max((now - publish_time).total_seconds() / 60, 0)


def historical_average(db: Session, title: str) -> float | None:
    sku = sku_from_title(title)
    avg_price = db.execute(select(func.avg(HistoricalPrice.price)).where(HistoricalPrice.sku == sku)).scalar()
    return float(avg_price) if avg_price else None


def score_item(db: Session, title: str, price_yen: int, publish_time: datetime | None) -> tuple[int, AlertLevel]:
    avg_price = historical_average(db, title)
    age = _age_minutes(publish_time)
    has_rare_term = any(term in title for term in RARE_TERMS)

    score = 20
    level = AlertLevel.C

    if avg_price:
        discount = 1 - (price_yen / avg_price)
        if discount >= 0.30:
            score += 45
        elif discount >= 0.15:
            score += 25
        score += min(max(int(discount * 100), 0), 20)
    else:
        discount = 0

    if age is not None:
        if age < 30:
            score += 20
        elif age < 120:
            score += 10

    if has_rare_term:
        score += 15

    score = max(1, min(score, 100))

    if age is not None and age < 30 and avg_price and discount >= 0.30 and has_rare_term:
        level = AlertLevel.A
        score = max(score, 90)
    elif age is not None and age < 120 and avg_price and discount >= 0.15:
        level = AlertLevel.B
        score = max(score, 70)

    return score, level

