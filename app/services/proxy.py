from urllib.parse import quote_plus, urlparse


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

