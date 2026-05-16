from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AlertLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("text", "group_name", name="uq_keyword_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(160), index=True)
    group_name: Mapped[str] = mapped_column(String(80), default="default", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_item_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(60), index=True)
    keyword: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(Text)
    seller: Mapped[str] = mapped_column(String(160), default="")
    price_yen: Mapped[int] = mapped_column(Integer)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_currency: Mapped[str] = mapped_column(String(12), default="JPY")
    shipping_fee: Mapped[int] = mapped_column(Integer, default=0)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    seller_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    seller_sales_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str] = mapped_column(Text, default="")
    image_hash: Mapped[str] = mapped_column(String(64), default="")
    product_url: Mapped[str] = mapped_column(Text)
    fetch_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True)
    scarcity_score: Mapped[int] = mapped_column(Integer, default=1, index=True)
    alert_level: Mapped[str] = mapped_column(String(1), default=AlertLevel.C.value, index=True)
    expected_sell_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    landed_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_margin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_margin_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    buyee_url: Mapped[str] = mapped_column(Text, default="")
    zenmarket_url: Mapped[str] = mapped_column(Text, default="")


class HistoricalPrice(Base):
    __tablename__ = "historical_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(200), index=True)
    platform: Mapped[str] = mapped_column(String(60), index=True)
    price: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
