import json

from bs4 import BeautifulSoup

from app.collectors.base import PlatformConfig, PublicPageCollector, now_utc, parse_price_yen
from app.schemas import RawItem


def _extract_json_ld_items(soup: BeautifulSoup, keyword: str, platform: str) -> list[RawItem]:
    """Extract items from JSON-LD script[type='application/ld+json'] blocks."""
    items: list[RawItem] = []
    for script in soup.select("script[type='application/ld+json']"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        entries: list[dict] = []
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                entries = data["@graph"]
            else:
                entries = [data]

        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") not in ("Product",):
                continue
            name = entry.get("name", "").strip()
            if not name:
                continue

            offers = entry.get("offers", {})
            if isinstance(offers, dict):
                price_str = str(offers.get("price", "0")).replace(",", "")
                currency = offers.get("priceCurrency", "")
            elif isinstance(offers, list) and offers:
                price_str = str(offers[0].get("price", "0")).replace(",", "")
                currency = offers[0].get("priceCurrency", "")
            else:
                price_str = "0"
                currency = ""

            if currency and currency not in ("JPY", "JP", ""):
                continue

            price = parse_price_yen(price_str)
            if price <= 0:
                continue

            image = ""
            img_data = entry.get("image", "")
            if isinstance(img_data, str):
                image = img_data
            elif isinstance(img_data, dict):
                image = img_data.get("url", "")

            url = entry.get("url", "")
            if not url:
                continue

            items.append(RawItem(
                platform=platform,
                keyword=keyword,
                title=name,
                price_yen=price,
                shipping_fee=0,
                publish_time=now_utc(),
                seller="",
                image_url=image,
                product_url=url,
            ))
    return items


class GenericCardCollector(PublicPageCollector):
    card_selectors = (
        "article", "[data-testid*=item]", ".item", ".Product", ".product",
        ".s-result-item",            # Amazon
        ".searchresultitem",         # Rakuten
        ".items-box",               # Rakuma fallback
    )
    title_selectors = (
        "h2", "h3", "[data-testid*=title]", ".title", ".Product__title",
        ".item-name", ".items-box-name",
        "h2 a.a-text-normal",       # Amazon
        ".product-name",
    )
    price_selectors = (
        "[data-testid*=price]", ".price", ".Product__price", ".item-price",
        ".a-price-whole",           # Amazon
        ".important-price",         # Rakuten
        ".items-box-price",         # Rakuma
        ".price-value",
    )
    image_selectors = ("img",)
    link_selectors = ("a[href]",)

    def parse(self, keyword: str, soup: BeautifulSoup, source_url: str) -> list[RawItem]:
        items: list[RawItem] = []

        # First pass: JSON-LD structured data (Product + Offer)
        try:
            ld_items = _extract_json_ld_items(soup, keyword, self.config.name)
            items.extend(ld_items)
        except Exception:
            pass

        # Second pass: HTML card / selector-based extraction
        cards = []
        for selector in self.card_selectors:
            cards = soup.select(selector)
            if cards:
                break

        for card in cards[:30]:
            title_el = next((card.select_one(s) for s in self.title_selectors if card.select_one(s)), None)
            price_el = next((card.select_one(s) for s in self.price_selectors if card.select_one(s)), None)
            link_el = next((card.select_one(s) for s in self.link_selectors if card.select_one(s)), None)
            image_el = next((card.select_one(s) for s in self.image_selectors if card.select_one(s)), None)
            if not title_el or not price_el or not link_el:
                continue

            price = parse_price_yen(price_el.get_text(" ", strip=True))
            href = link_el.get("href", "")
            if not href or price <= 0:
                continue
            product_url = href if href.startswith("http") else self.config.base_url.rstrip("/") + "/" + href.lstrip("/")
            image_url = ""
            if image_el:
                image_url = image_el.get("src") or image_el.get("data-src") or ""

            items.append(
                RawItem(
                    platform=self.config.name,
                    keyword=keyword,
                    title=title_el.get_text(" ", strip=True),
                    price_yen=price,
                    shipping_fee=0,
                    publish_time=now_utc(),
                    seller="",
                    image_url=image_url,
                    product_url=product_url,
                )
            )
        return items


class MercariCollector(GenericCardCollector):
    config = PlatformConfig("mercari_japan", "https://jp.mercari.com", "/search?keyword={keyword}")


class YahooAuctionsCollector(GenericCardCollector):
    config = PlatformConfig("yahoo_auctions_japan", "https://auctions.yahoo.co.jp", "/search/search?p={keyword}")


class RakumaCollector(GenericCardCollector):
    config = PlatformConfig("rakuma", "https://fril.jp", "/search/{keyword}")


class RakutenCollector(GenericCardCollector):
    config = PlatformConfig("rakuten_japan", "https://search.rakuten.co.jp", "/search/mall/{keyword}/")


class AmazonJapanCollector(GenericCardCollector):
    config = PlatformConfig("amazon_japan", "https://www.amazon.co.jp", "/s?k={keyword}")

