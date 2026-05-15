import hashlib
import re


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def image_hash_from_url(image_url: str) -> str:
    if not image_url:
        return ""
    return stable_hash(image_url)[:32]


def build_dedupe_key(title: str, seller: str, image_hash: str, price_yen: int) -> str:
    raw = "|".join([normalize_text(title), normalize_text(seller), image_hash, str(price_yen)])
    return stable_hash(raw)

