from urllib.parse import quote_plus, urlparse


DOMESTIC_PROXY_NOTE = "国内用户建议优先用挖煤姬等国内平台成交；Buyee/ZenMarket 仅作备用入口。"


def proxy_support(platform: str) -> tuple[bool, bool, str]:
    if platform == "amazon_japan":
        return False, False, "Amazon 通常直接在 Amazon 页面购买，代理搜索仅作参考。"
    if platform == "rakuma":
        return False, True, f"Rakuma 可先尝试国内平台搜索；{DOMESTIC_PROXY_NOTE}"
    if platform in {"yahoo_auctions_japan", "mercari_japan", "rakuten_japan"}:
        return True, True, DOMESTIC_PROXY_NOTE
    return False, True, f"未知平台，优先打开原商品链接核对；{DOMESTIC_PROXY_NOTE}"


def meruki_url(product_url: str, title: str) -> str:
    host = urlparse(product_url).netloc
    query = quote_plus(title)
    if "mercari" in host:
        return f"https://meruki.cn/mall/mercari?keyword={query}"
    if "yahoo" in host or "auctions" in host:
        return f"https://meruki.cn/mall/yahoo?keyword={query}"
    if "rakuten" in host:
        return f"https://meruki.cn/mall/rakuten?keyword={query}"
    return f"https://meruki.cn/search/pool?keyword={query}"


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
