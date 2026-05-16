import re

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("三輪車", ("三輪車", "さんりんしゃ", "tricycle")),
    ("乗用玩具", ("乗用", "キッズカー", "足けり", "足蹴り", "乗り物", "カー")),
    ("ベビーカー", ("ベビーカー", "buggy", "バギー")),
    ("ジャングルジム", ("ジャングルジム", "ブランコ", "すべり台", "滑り台")),
    ("ぬいぐるみ", ("ぬいぐるみ", "人形", "ドール", "ソフビ", "指人形")),
    ("知育玩具", ("知育", "メリー", "ジムメリー", "脳を育む", "おもちゃ")),
    ("本・絵本", ("絵本", "本", "ずかん", "図鑑")),
    ("DVD・メディア", ("dvd", "cd", "blu-ray", "ブルーレイ")),
    ("衣類・雑貨", ("服", "靴", "バッグ", "リュック", "タオル")),
)

NOISE_TERMS = (
    "アンパンマン",
    "anpanman",
    "バンダイ",
    "bandai",
    "美品",
    "未使用",
    "新品",
    "中古",
    "限定",
    "廃盤",
    "レア",
    "ジャンク",
    "送料無料",
    "送料込み",
    "即決",
    "即購入",
    "まとめ売り",
    "セット",
    "大量",
    "格安",
    "セール",
)


def identify_category(title: str) -> str:
    lowered = title.lower()
    for category, terms in CATEGORY_RULES:
        if any(term.lower() in lowered for term in terms):
            return category
    return "その他"


def normalize_title_for_sku(title: str) -> str:
    value = title.lower()
    value = re.sub(r"[【】\[\]（）()~〜!！?？・,，、。/\\|:：;；\"'“”‘’]", " ", value)
    for term in NOISE_TERMS:
        value = value.replace(term.lower(), " ")
    value = re.sub(r"\b\d+\s*(円|yen|jpy|hkd)\b", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def sku_from_title(title: str) -> str:
    category = identify_category(title)
    normalized = normalize_title_for_sku(title)
    return f"{category}:{normalized}"[:200]
