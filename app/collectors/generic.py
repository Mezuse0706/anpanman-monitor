from bs4 import BeautifulSoup

from app.collectors.base import PlatformConfig, PublicPageCollector, now_utc, parse_price_yen
from app.schemas import RawItem


class GenericCardCollector(PublicPageCollector):
    card_selectors = ("article", "[data-testid*=item]", ".item", ".Product", ".product")
    title_selectors = ("h2", "h3", "[data-testid*=title]", ".title", ".Product__title")
    price_selectors = ("[data-testid*=price]", ".price", ".Product__price")
    image_selectors = ("img",)
    link_selectors = ("a[href]",)

    def parse(self, keyword: str, soup: BeautifulSoup, source_url: str) -> list[RawItem]:
        items: list[RawItem] = []
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

