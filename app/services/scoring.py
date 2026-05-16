from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertLevel, HistoricalPrice
from app.services.history import sku_from_title

RARE_TERMS = ("美品", "未使用", "限定", "廃盤", "レア")
STRONG_RARE_TERMS = ("未使用", "限定", "廃盤", "レア")
HIGH_VALUE_TERMS = ("三輪車", "乗用", "ベビーカー", "キッズカー", "ジャングルジム", "ブランコ")
RISK_TERMS = ("ジャンク", "難あり", "破損", "部品取り")
DEAL_PRICE_MAX_YEN = 3000
HISTORY_MIN_SAMPLES = 5


def _age_minutes(publish_time: datetime | None) -> float | None:
    if publish_time is None:
        return None
    now = datetime.now(timezone.utc)
    if publish_time.tzinfo is None:
        publish_time = publish_time.replace(tzinfo=timezone.utc)
    return max((now - publish_time).total_seconds() / 60, 0)


def historical_price_summary(db: Session, title: str) -> tuple[float | None, int]:
    sku = sku_from_title(title)
    avg_price, sample_count = db.execute(
        select(func.avg(HistoricalPrice.price), func.count(HistoricalPrice.id)).where(HistoricalPrice.sku == sku)
    ).one()
    return (float(avg_price) if avg_price else None, int(sample_count or 0))


def historical_average(db: Session, title: str) -> float | None:
    avg_price, _ = historical_price_summary(db, title)
    return avg_price


def score_item(
    db: Session,
    title: str,
    price_yen: int,
    publish_time: datetime | None,
    platform: str = "",
) -> tuple[int, AlertLevel]:
    avg_price, sample_count = historical_price_summary(db, title)
    age = _age_minutes(publish_time)
    rare_hits = sum(1 for term in RARE_TERMS if term in title)
    has_strong_rare_term = any(term in title for term in STRONG_RARE_TERMS)
    has_high_value_term = any(term in title for term in HIGH_VALUE_TERMS)
    has_risk_term = any(term in title for term in RISK_TERMS)

    score = 20
    discount = 0.0
    has_reliable_history = bool(avg_price and sample_count >= HISTORY_MIN_SAMPLES)

    if has_reliable_history and avg_price:
        discount = 1 - (price_yen / avg_price)
        if discount >= 0.30:
            score += 30
        elif discount >= 0.15:
            score += 18
        score += min(max(int(discount * 80), 0), 18)

    if age is not None:
        if age < 30:
            score += 20
        elif age < 120:
            score += 10

    score += min(rare_hits * 10, 25)

    if has_high_value_term:
        score += 18

    if 500 <= price_yen <= DEAL_PRICE_MAX_YEN:
        score += 12
    elif price_yen <= 5000:
        score += 6

    if platform in {"yahoo_auctions_japan", "mercari_japan", "rakuma"}:
        score += 8
    elif platform in {"amazon_japan", "rakuten_japan"}:
        score -= 5

    if has_risk_term:
        score -= 15

    score = max(1, min(score, 100))

    if (
        score >= 80
        and (
            has_strong_rare_term
            or (has_high_value_term and price_yen <= DEAL_PRICE_MAX_YEN)
            or (has_reliable_history and discount >= 0.25)
        )
        and not has_risk_term
    ):
        level = AlertLevel.A
    elif (
        score >= 60
        or (price_yen <= DEAL_PRICE_MAX_YEN and has_high_value_term)
        or (rare_hits > 0 and age is not None and age < 120)
        or (has_reliable_history and discount >= 0.15)
    ):
        level = AlertLevel.B
    else:
        level = AlertLevel.C

    return score, level
