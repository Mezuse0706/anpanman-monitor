from app.schemas import ProfitInput, ProfitOutput


def calculate_profit(item_price_yen: int, payload: ProfitInput) -> ProfitOutput:
    landed_cost = (
        item_price_yen
        + payload.domestic_shipping_yen
        + payload.platform_fee_yen
        + payload.proxy_fee_yen
        + payload.international_shipping_yen
        + payload.china_delivery_yen
    )
    gross_margin = payload.expected_sell_price - landed_cost
    gross_margin_percent = 0.0 if payload.expected_sell_price == 0 else gross_margin / payload.expected_sell_price * 100
    return ProfitOutput(
        landed_cost=landed_cost,
        gross_margin=gross_margin,
        gross_margin_percent=round(gross_margin_percent, 2),
        low_margin=gross_margin_percent < 30,
    )

