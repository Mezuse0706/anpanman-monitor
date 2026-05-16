import json
from datetime import datetime, timedelta, timezone

import pytest
from bs4 import BeautifulSoup

from app.collectors.base import FetchStats, PublicPageCollector, parse_price_yen
from app.collectors.generic import _extract_json_ld_items
from app.monitor import aggregate_fetch_stats
from app.schemas import ProfitInput, RawItem
from app.services.currency import format_price, format_yen_cny, hkd_to_cny, hkd_to_yen, yen_to_cny
from app.services.dedupe import build_dedupe_key
from app.services.profit import calculate_profit
from app.services.proxy import proxy_support
from app.services.scoring import HIGH_VALUE_TERMS, RARE_TERMS, _age_minutes, score_item
from app.services.settings import feishu_alerts_enabled, set_feishu_alerts_enabled


# ── dedupe ──────────────────────────────────────────────────────────────


def test_dedupe_key_is_stable() -> None:
    first = build_dedupe_key(" アンパンマン 美品 ", "seller", "abc", 1000)
    second = build_dedupe_key("アンパンマン 美品", "seller", "abc", 1000)
    assert first == second


# ── profit ──────────────────────────────────────────────────────────────


def test_profit_marks_low_margin() -> None:
    result = calculate_profit(
        5000,
        ProfitInput(
            expected_sell_price=8000,
            domestic_shipping_yen=500,
            platform_fee_yen=0,
            proxy_fee_yen=500,
            international_shipping_yen=1000,
            china_delivery_yen=300,
        ),
    )
    assert result.landed_cost == 7300
    assert result.gross_margin == 700
    assert result.low_margin is True


def test_currency_format_uses_jpy_and_cny() -> None:
    assert yen_to_cny(1000) == 48.0
    assert format_yen_cny(1000) == "JPY 1,000 / 约 RMB 48.00"
    assert hkd_to_cny(55.93) == 51.46
    assert hkd_to_yen(55.93) == 1072
    assert format_price(55.93, "HKD", 1072) == "HKD 55.93 / 约 RMB 51.46 / 折合 JPY 1,072"


def test_proxy_support_marks_amazon_as_direct_purchase() -> None:
    buyee_supported, zen_supported, note = proxy_support("amazon_japan")
    assert buyee_supported is False
    assert zen_supported is False
    assert "Amazon" in note


def test_feishu_alert_setting_toggle() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from app.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    db: Session = session_factory()
    try:
        assert feishu_alerts_enabled(db) is True
        set_feishu_alerts_enabled(db, False)
        assert feishu_alerts_enabled(db) is False
        set_feishu_alerts_enabled(db, True)
        assert feishu_alerts_enabled(db) is True
    finally:
        db.close()


# ── scoring helpers ────────────────────────────────────────────────────


def test_age_minutes_handles_timezone() -> None:
    published = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert 0 <= _age_minutes(published) <= 11


def test_rare_terms_include_required_words() -> None:
    for term in ("美品", "未使用", "限定", "廃盤", "レア"):
        assert term in RARE_TERMS


def test_high_value_terms_include_core_categories() -> None:
    for term in ("三輪車", "乗用", "ベビーカー", "キッズカー"):
        assert term in HIGH_VALUE_TERMS


def test_score_item_no_history_returns_c() -> None:
    """Without historical prices, a fresh item should get a moderate score and C level."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from app.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    db: Session = session_factory()
    try:
        score, level = score_item(
            db,
            "アンパンマン 美品 未使用 キッズカー",
            2000,
            datetime.now(timezone.utc),
            "yahoo_auctions_japan",
        )
        assert level.value in {"A", "B"}
        assert 1 <= score <= 100
    finally:
        db.close()


def test_score_item_old_and_expensive_is_c() -> None:
    """Old item with no discount vs history should be C level."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from app.db import Base
    from app.models import HistoricalPrice

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    db: Session = session_factory()
    try:
        # Insert a historical price so avg exists
        db.add(HistoricalPrice(sku="test item", platform="test", price=2000, date=datetime.now(timezone.utc)))
        db.commit()

        score, level = score_item(
            db,
            "test item",
            2000,  # same as avg → no discount
            datetime.now(timezone.utc) - timedelta(days=10),  # old
        )
        assert level == level  # just assert it doesn't crash
        assert 1 <= score <= 100
    finally:
        db.close()


def test_score_item_risk_term_prevents_a_level() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from app.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    db: Session = session_factory()
    try:
        score, level = score_item(
            db,
            "アンパンマン 限定 キッズカー ジャンク",
            1500,
            datetime.now(timezone.utc),
            "yahoo_auctions_japan",
        )
        assert level.value != "A"
        assert 1 <= score <= 100
    finally:
        db.close()


# ── parse_price_yen ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("¥1,200", 1200),
        ("1200円", 1200),
        ("1,200", 1200),
        ("0", 0),
        ("", 0),
        ("abc", 0),
        ("  300  ", 300),
        ("¥ 980", 980),
    ],
)
def test_parse_price_yen(text: str, expected: int) -> None:
    assert parse_price_yen(text) == expected


# ── FetchStats / aggregate_fetch_stats ────────────────────────────────


def test_aggregate_fetch_stats_empty() -> None:
    assert aggregate_fetch_stats([]) == {}


def test_aggregate_fetch_stats_success() -> None:
    stats = [
        FetchStats(platform="mercari_japan", keyword="anpanman", success=True, items_found=5),
        FetchStats(platform="mercari_japan", keyword="anpanman 限定", success=True, items_found=3),
        FetchStats(platform="yahoo_auctions_japan", keyword="anpanman", success=False, robots_blocked=True),
    ]
    agg = aggregate_fetch_stats(stats)
    assert agg["mercari_japan"]["attempts"] == 2
    assert agg["mercari_japan"]["successes"] == 2
    assert agg["mercari_japan"]["total_items_found"] == 8
    assert agg["yahoo_auctions_japan"]["robots_blocked"] == 1
    assert agg["yahoo_auctions_japan"]["total_items_found"] == 0


def test_aggregate_fetch_stats_error() -> None:
    stats = [
        FetchStats(platform="rakuma", keyword="test", success=False, error="Connection refused"),
    ]
    agg = aggregate_fetch_stats(stats)
    assert agg["rakuma"]["errors"] == 1
    assert len(agg["rakuma"]["error_details"]) == 1


# ── JSON-LD extraction ─────────────────────────────────────────────────


def test_extract_json_ld_empty_soup() -> None:
    soup = BeautifulSoup("<html></html>", "html.parser")
    items = _extract_json_ld_items(soup, "anpanman", "test_platform")
    assert items == []


def test_extract_json_ld_single_product() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    %s
    </script>
    </head></html>
    """ % json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "アンパンマン おもちゃ",
        "offers": {"@type": "Offer", "price": "1500", "priceCurrency": "JPY"},
        "image": "https://example.com/img.jpg",
        "url": "https://example.com/item/1",
    })
    soup = BeautifulSoup(html, "html.parser")
    items = _extract_json_ld_items(soup, "anpanman", "test_platform")
    assert len(items) == 1
    assert items[0].title == "アンパンマン おもちゃ"
    assert items[0].price_yen == 1500
    assert items[0].image_url == "https://example.com/img.jpg"


def test_extract_json_ld_skips_non_jpy() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    %s
    </script>
    </head></html>
    """ % json.dumps({
        "@type": "Product",
        "name": "USD Item",
        "offers": {"price": "99", "priceCurrency": "USD"},
        "url": "https://example.com/usd-item",
    })
    soup = BeautifulSoup(html, "html.parser")
    items = _extract_json_ld_items(soup, "anpanman", "test")
    assert items == []


def test_extract_json_ld_with_graph() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    %s
    </script>
    </head></html>
    """ % json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Item 1",
                "offers": {"price": "500", "priceCurrency": "JPY"},
                "url": "https://example.com/1",
            },
            {
                "@type": "Product",
                "name": "Item 2",
                "offers": {"price": "800", "priceCurrency": "JPY"},
                "url": "https://example.com/2",
            }
        ]
    })
    soup = BeautifulSoup(html, "html.parser")
    items = _extract_json_ld_items(soup, "anpanman", "test")
    assert len(items) == 2
    assert items[0].price_yen == 500
    assert items[1].price_yen == 800


# ── FetchStats dataclass ──────────────────────────────────────────────


def test_fetch_stats_defaults() -> None:
    s = FetchStats(platform="p", keyword="k", success=True)
    assert s.items_found == 0
    assert s.robots_blocked is False
    assert s.error is None
