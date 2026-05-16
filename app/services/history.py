from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HistoricalPrice
from app.services.catalog import sku_from_title


def record_price(db: Session, sku: str, platform: str, price: int, date: datetime | None = None) -> None:
    db.add(HistoricalPrice(sku=sku, platform=platform, price=price, date=date or datetime.now(timezone.utc)))


def price_stats(db: Session, sku: str) -> dict[str, float | int | None]:
    stmt = select(
        func.avg(HistoricalPrice.price),
        func.min(HistoricalPrice.price),
        func.max(HistoricalPrice.price),
    ).where(HistoricalPrice.sku == sku)
    avg_price, min_price, max_price = db.execute(stmt).one()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    trend_stmt = select(func.avg(HistoricalPrice.price)).where(
        HistoricalPrice.sku == sku,
        HistoricalPrice.date >= since,
    )
    trend_30d = db.execute(trend_stmt).scalar()
    return {
        "average": round(float(avg_price), 2) if avg_price else None,
        "min": int(min_price) if min_price else None,
        "max": int(max_price) if max_price else None,
        "trend_30d_average": round(float(trend_30d), 2) if trend_30d else None,
    }
