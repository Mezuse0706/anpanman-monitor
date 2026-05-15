from datetime import datetime, timedelta, timezone

from app.schemas import ProfitInput
from app.services.dedupe import build_dedupe_key
from app.services.profit import calculate_profit
from app.services.scoring import RARE_TERMS, _age_minutes


def test_dedupe_key_is_stable() -> None:
    first = build_dedupe_key(" アンパンマン 美品 ", "seller", "abc", 1000)
    second = build_dedupe_key("アンパンマン 美品", "seller", "abc", 1000)
    assert first == second


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


def test_age_minutes_handles_timezone() -> None:
    published = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert 0 <= _age_minutes(published) <= 11


def test_rare_terms_include_required_words() -> None:
    for term in ("美品", "未使用", "限定", "廃盤"):
        assert term in RARE_TERMS

