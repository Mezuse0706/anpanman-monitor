from urllib.parse import quote_plus, urlparse


def proxy_support(platform: str) -> tuple[bool, bool, str]:
    if platform == "yahoo_auctions_japan":
        return True, True, "Yahoo Auctions 可通过代理搜索购买。"
    if platform == "mercari_japan":
        return True, True, "Mercari 优先通过 Buyee 搜索同款。"
    if platform == "rakuma":
        return False, True, "Rakuma 暂无稳定 Buyee 入口，可用 ZenMarket 搜索。"
    if platform == "rakuten_japan":
        return True, True, "Rakuten 可通过代理搜索。"
    if platform == "amazon_japan":
        return False, False, "Amazon 通常直接在 Amazon 页面购买，代理按钮不适用。"
    return False, True, "未知平台，仅提供搜索入口。"


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
