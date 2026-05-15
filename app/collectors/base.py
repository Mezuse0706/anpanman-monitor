from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.schemas import RawItem


@dataclass(frozen=True)
class PlatformConfig:
    name: str
    base_url: str
    search_path: str


class PublicPageCollector(ABC):
    config: PlatformConfig

    def search_url(self, keyword: str) -> str:
        return self.config.base_url + self.config.search_path.format(keyword=quote_plus(keyword))

    async def allowed_by_robots(self, url: str) -> bool:
        robots_url = self.config.base_url.rstrip("/") + "/robots.txt"
        parser = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(robots_url)
            parser.parse(response.text.splitlines())
            return parser.can_fetch(get_settings().http_user_agent, url)
        except httpx.HTTPError:
            return False

    async def fetch(self, keyword: str) -> list[RawItem]:
        url = self.search_url(keyword)
        if not await self.allowed_by_robots(url):
            return []

        settings = get_settings()
        headers = {"User-Agent": settings.http_user_agent, "Accept-Language": "ja,en;q=0.8"}
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return self.parse(keyword, soup, url)

    @abstractmethod
    def parse(self, keyword: str, soup: BeautifulSoup, source_url: str) -> list[RawItem]:
        raise NotImplementedError


def parse_price_yen(text: str) -> int:
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

