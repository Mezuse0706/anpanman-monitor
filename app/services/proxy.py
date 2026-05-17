from urllib.parse import quote, quote_plus, urlparse


DOMESTIC_PROXY_NOTE = "国内用户建议优先用挖煤姬等国内平台成交；Buyee/ZenMarket 仅作备用入口。"


def proxy_support(platform: str) -> tuple[bool, bool, str]:
    if platform == "amazon_japan":
        return False, False, "Amazon 通常直接在 Amazon 页面购买，代理搜索仅作参考。"
    if platform == "rakuma":
        return False, True, f"Rakuma 可先尝试国内平台搜索；{DOMESTIC_PROXY_NOTE}"
    if platform == "meruki":
        return False, False, "这条来自挖煤姬补充源，优先打开商品链接在挖煤姬内核对。"
    if platform == "lekutao_app":
        return False, False, "乐酷淘目前作为 App/成交入口记录，公开 Web 搜索源暂不可用。"
    if platform in {"yahoo_auctions_japan", "mercari_japan", "rakuten_japan"}:
        return True, True, DOMESTIC_PROXY_NOTE
    return False, True, f"未知平台，优先打开原商品链接核对；{DOMESTIC_PROXY_NOTE}"


def meruki_url(product_url: str, title: str) -> str:
    parsed = urlparse(product_url)
    host = parsed.netloc
    path_parts = [part for part in parsed.path.split("/") if part]
    encoded_url = quote(product_url, safe="")
    query = quote_plus(title)
    if "mercari" in host:
        item_id = path_parts[-1] if path_parts else ""
        if item_id:
            return f"https://meruki.cn/mall/mercari/detail/{quote(item_id, safe='')}"
        return f"https://meruki.cn/search?keywords={query}"
    if "yahoo" in host or "auctions" in host:
        return f"https://meruki.cn/mall/yahoo/detail/{encoded_url}"
    if "fril" in host:
        item_id = path_parts[-1] if path_parts else ""
        if item_id:
            return f"https://meruki.cn/mall/rakuma/detail/{quote(item_id, safe='')}"
        return f"https://meruki.cn/search?keywords={query}"
    if "rakuten" in host:
        return f"https://meruki.cn/mall/rakuten/detail/{encoded_url}"
    return f"https://meruki.cn/search?keywords={query}"


def buyee_url(product_url: str, title: str) -> str:
    host = urlparse(product_url).netloc
    if "mercari" in host:
        return f"https://buyee.jp/mercari/search?keyword={quote_plus(title)}"
    if "yahoo" in host or "auctions" in host:
        return f"https://buyee.jp/yahoo/auction/search?keyword={quote_plus(title)}"
    if "rakuten" in host:
        return f"https://buyee.jp/rakuten/search?keyword={quote_plus(title)}"
    return f"https://buyee.jp/item/search/query/{quote_plus(title)}"


def zenmarket_url(product_url: str, title: str) -> str:
    return f"https://zenmarket.jp/search.aspx?q={quote_plus(title)}"
