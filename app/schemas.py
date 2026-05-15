from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class KeywordCreate(BaseModel):
    text: str = Field(min_length=1, max_length=160)
    group_name: str = "default"


class KeywordImport(BaseModel):
    keywords: list[str]
    group_name: str = "default"


class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    group_name: str
    created_at: datetime


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    keyword: str
    title: str
    seller: str
    price_yen: int
    original_price: float | None
    original_currency: str
    shipping_fee: int
    publish_time: datetime | None
    seller_rating: float | None
    seller_sales_count: int | None
    image_url: str
    product_url: str
    fetch_time: datetime
    scarcity_score: int
    alert_level: str
    expected_sell_price: int | None
    landed_cost: int | None
    gross_margin: int | None
    gross_margin_percent: float | None
    buyee_url: str
    zenmarket_url: str


class ProfitInput(BaseModel):
    expected_sell_price: int = Field(gt=0)
    domestic_shipping_yen: int = Field(default=0, ge=0)
    platform_fee_yen: int = Field(default=0, ge=0)
    proxy_fee_yen: int = Field(default=500, ge=0)
    international_shipping_yen: int = Field(default=2500, ge=0)
    china_delivery_yen: int = Field(default=500, ge=0)


class ProfitOutput(BaseModel):
    landed_cost: int
    gross_margin: int
    gross_margin_percent: float
    low_margin: bool


class RawItem(BaseModel):
    platform: str
    keyword: str
    title: str
    price_yen: int
    original_price: float | None = None
    original_currency: str = "JPY"
    shipping_fee: int = 0
    publish_time: datetime | None = None
    seller: str = ""
    seller_rating: float | None = None
    seller_sales_count: int | None = None
    image_url: str = ""
    product_url: HttpUrl | str
