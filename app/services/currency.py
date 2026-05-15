from app.core.config import get_settings


def yen_to_cny(price_yen: int) -> float:
    return round(price_yen * get_settings().jpy_to_cny_rate, 2)


def cny_to_yen(price_cny: float) -> int:
    return round(price_cny / get_settings().jpy_to_cny_rate)


def hkd_to_cny(price_hkd: float) -> float:
    return round(price_hkd * get_settings().hkd_to_cny_rate, 2)


def hkd_to_yen(price_hkd: float) -> int:
    return cny_to_yen(hkd_to_cny(price_hkd))


def format_yen_cny(price_yen: int) -> str:
    return f"JPY {price_yen:,} / 约 RMB {yen_to_cny(price_yen):,.2f}"


def format_price(original_price: float | None, original_currency: str | None, price_yen: int) -> str:
    currency = (original_currency or "JPY").upper()
    if currency == "HKD" and original_price is not None:
        return f"HKD {original_price:,.2f} / 约 RMB {hkd_to_cny(original_price):,.2f} / 折合 JPY {price_yen:,}"
    return format_yen_cny(price_yen)
