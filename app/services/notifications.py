import httpx

from app.core.config import get_settings
from app.models import Item
from app.services.currency import format_yen_cny


def format_feishu_text(item: Item) -> str:
    margin = "N/A"
    if item.gross_margin_percent is not None:
        margin = f"{item.gross_margin_percent:.2f}%"

    return (
        f"[Anpanman {item.alert_level}级提醒] {item.title}\n"
        f"平台: {item.platform}\n"
        f"价格: {format_yen_cny(item.price_yen)}\n"
        f"发布时间: {item.publish_time or '未知'}\n"
        f"稀缺分: {item.scarcity_score}\n"
        f"预估毛利: {margin}\n"
        f"商品链接: {item.product_url}\n"
        f"Buyee: {item.buyee_url}\n"
        f"ZenMarket: {item.zenmarket_url}"
    )


async def send_feishu_alert(item: Item) -> bool:
    settings = get_settings()
    if not settings.feishu_webhook_url:
        return False

    payload = {"msg_type": "text", "content": {"text": format_feishu_text(item)}}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.feishu_webhook_url, json=payload)
        response.raise_for_status()
    return True


async def send_feishu_test_message() -> bool:
    settings = get_settings()
    if not settings.feishu_webhook_url:
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": "Anpanman 稀缺货监控已连接飞书。"},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(settings.feishu_webhook_url, json=payload)
        response.raise_for_status()
    return True
