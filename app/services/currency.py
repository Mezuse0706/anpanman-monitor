from app.core.config import get_settings


def yen_to_cny(price_yen: int) -> float:
    return round(price_yen * get_settings().jpy_to_cny_rate, 2)


def format_yen_cny(price_yen: int) -> str:
    return f"JPY {price_yen:,} / 约 RMB {yen_to_cny(price_yen):,.2f}"
