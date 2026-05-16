import asyncio
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import case, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal, get_db, init_db
from app.models import Item, Keyword
from app.monitor import run_monitor_once
from app.schemas import ItemOut, KeywordCreate, KeywordImport, KeywordOut, ProfitInput, ProfitOutput
from sqlalchemy import func as sqlfunc

from app.services.currency import format_price
from app.services.history import price_stats, sku_from_title
from app.services.notifications import send_feishu_test_message
from app.services.profit import calculate_profit
from app.services.proxy import proxy_support

DEFAULT_KEYWORDS = [
    "アンパンマン",
    "アンパンマン 三輪車",
    "アンパンマン 折りたたみ",
    "アンパンマン 乗用",
    "アンパンマン レア",
    "アンパンマン 廃盤",
    "アンパンマン 限定",
    "アンパンマン ジャンク",
    "アンパンマン 美品",
    "アンパンマン ベビーカー",
    "アンパンマン キッズカー",
]


def seed_default_keywords(db: Session) -> None:
    db.query(Keyword).filter(Keyword.text.like("%ã%")).delete(synchronize_session=False)
    db.query(Keyword).filter(Keyword.text.like("%�%")).delete(synchronize_session=False)
    existing_texts = {row[0] for row in db.query(Keyword.text).all()}
    for text in DEFAULT_KEYWORDS:
        if text not in existing_texts:
            db.add(Keyword(text=text, group_name="anpanman"))
    db.commit()


def cleanup_known_bad_prices(db: Session) -> None:
    db.query(Item).filter(Item.platform == "amazon_japan", Item.price_yen < 100, Item.original_currency == "JPY").delete()
    db.commit()


async def monitor_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.monitor_interval_seconds)
        db = SessionLocal()
        try:
            await run_monitor_once(db)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_default_keywords(db)
        cleanup_known_bad_prices(db)
    finally:
        db.close()

    task: asyncio.Task | None = None
    if get_settings().enable_background_monitor:
        task = asyncio.create_task(monitor_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="Anpanman Scarcity Monitor", version="0.2.0", lifespan=lifespan)


def page_shell(content: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Anpanman Monitor</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #202124; background: #f6f7f9; }}
    header {{ background: #1f2937; color: white; padding: 18px 24px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .grid {{ display: grid; grid-template-columns: 360px 1fr; gap: 18px; align-items: start; }}
    .panel, .item {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    .stack {{ display: grid; gap: 14px; }}
    input, textarea, select {{ box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid #cfd4dc; border-radius: 6px; font-size: 14px; }}
    textarea {{ min-height: 120px; resize: vertical; }}
    button, .button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 0 14px; border: 0; border-radius: 6px; background: #2563eb; color: white; text-decoration: none; cursor: pointer; font-size: 14px; }}
    .secondary {{ background: #4b5563; }}
    .danger {{ color: #b91c1c; font-weight: 700; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .keywords {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tag {{ background: #eef2ff; color: #3730a3; padding: 5px 8px; border-radius: 999px; font-size: 13px; }}
    .items {{ display: grid; gap: 12px; }}
    .item h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .meta {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
    .level-A {{ border-left: 5px solid #dc2626; }}
    .level-B {{ border-left: 5px solid #f59e0b; }}
    .level-C {{ border-left: 5px solid #9ca3af; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 16px; }} }}
  </style>
</head>
<body>
  <header><h1>Anpanman 稀缺货监控</h1></header>
  <main>{content}</main>
</body>
</html>"""


PLATFORM_LABELS: dict[str, str] = {
    "mercari_japan": "Mercari",
    "yahoo_auctions_japan": "Yahoo Auctions",
    "rakuma": "Rakuma",
    "rakuten_japan": "Rakuten",
    "amazon_japan": "Amazon Japan",
}


def _platform_count_rows(db: Session) -> str:
    """Build HTML rows showing how many items exist per platform in the DB."""
    rows: list[str] = []
    counts: dict[str, int] = dict(
        db.query(Item.platform, sqlfunc.count(Item.id)).group_by(Item.platform).all()
    )
    # Show all known platforms, even those with 0 items
    for key, label in PLATFORM_LABELS.items():
        cnt = counts.get(key, 0)
        rows.append(f'<span class="tag">{label}: <strong>{cnt}</strong></span>')
    if not rows:
        return '<p class="muted">暂无数据。</p>'
    return '<div class="keywords">' + "".join(rows) + "</div>"


@app.get("/", response_class=HTMLResponse)
def dashboard(
    page: int = Query(1, ge=1),
    platform: str = Query("all"),
    level: str = Query("all"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    settings = get_settings()
    keywords = db.query(Keyword).order_by(Keyword.group_name, Keyword.text).all()
    page_size = 25
    item_query = db.query(Item)
    if platform != "all":
        item_query = item_query.filter(Item.platform == platform)
    if level in {"A", "B", "C"}:
        item_query = item_query.filter(Item.alert_level == level)
    total_items = item_query.count()
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    level_rank = case(
        (Item.alert_level == "A", 3),
        (Item.alert_level == "B", 2),
        (Item.alert_level == "C", 1),
        else_=0,
    )
    items = (
        item_query.order_by(desc(level_rank), desc(Item.scarcity_score), desc(Item.fetch_time))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    feishu_status = "已配置" if settings.feishu_webhook_url else "未配置"
    keyword_tags = "".join(
        f'<span class="tag">{escape(k.group_name)} / {escape(k.text)}</span>' for k in keywords
    )
    item_cards = "".join(render_item(item) for item in items) or '<div class="panel muted">还没有商品。点击“立即监控一次”开始抓取。</div>'
    platform_rows = _platform_count_rows(db)
    platform_filter = render_platform_filter(platform, level)
    level_filter = render_level_filter(platform, level)
    pager = render_pager(page, total_pages, total_items, platform, level)

    content = f"""
<div class="grid">
  <section class="stack">
    <div class="panel">
      <h2>控制台</h2>
      <p class="muted">飞书：{feishu_status}；后台轮询：每 {settings.monitor_interval_seconds} 秒；价格保留原始币种，并约算人民币/日元。</p>
      <div class="row">
        <form method="post" action="/web/monitor/run-once"><button type="submit">立即监控一次</button></form>
        <form method="post" action="/web/alerts/test"><button class="secondary" type="submit">测试飞书提醒</button></form>
      </div>
    </div>
    <div class="panel">
      <h2>各平台数据库存量</h2>
      {platform_rows}
    </div>
    <div class="panel">
      <h2>评分规则</h2>
      <p class="muted">
        A级：80分以上，且命中强稀缺词、低价高价值品类，或可靠历史均价显示明显低价。<br>
        B级：60分以上，或低价高价值品类，或新发布且带稀缺词。<br>
        C级：普通新货。分数来自发布时间、稀缺词、品类价值、价格区间、平台、历史均价和风险词。<br>
        历史均价只有同 SKU 样本达到 5 条后才参与评分；当前早期阶段更看重“早发现”和候选信号。
      </p>
    </div>
    <div class="panel">
      <h2>新增关键词</h2>
      <form method="post" action="/web/keywords" class="stack">
        <input name="text" placeholder="例如：アンパンマン 廃盤" required>
        <input name="group_name" value="anpanman" placeholder="分组">
        <button type="submit">添加</button>
      </form>
    </div>
    <div class="panel">
      <h2>批量导入</h2>
      <form method="post" action="/web/keywords/import" class="stack">
        <textarea name="keywords" placeholder="每行一个关键词"></textarea>
        <input name="group_name" value="anpanman" placeholder="分组">
        <button type="submit">导入</button>
      </form>
    </div>
    <div class="panel">
      <h2>关键词</h2>
      <div class="keywords">{keyword_tags}</div>
    </div>
  </section>
  <section class="stack">
    <div class="panel">
      <h2>实时新货</h2>
      {platform_filter}
      {level_filter}
      <p class="muted">
        <strong>A级</strong>（高稀缺，推送飞书）：<span style="color:#dc2626;">红色左边框</span> — 近期发布 + 低于均价30%以上 + 含稀有词<br>
        <strong>B级</strong>（中稀缺）：<span style="color:#f59e0b;">橙色左边框</span> — 近期发布 + 低于均价15%以上<br>
        <strong>C级</strong>（普通）：<span style="color:#9ca3af;">灰色左边框</span> — 常规商品<br>
        <strong>分数</strong>：右侧数字（1–100），越高越稀缺。
      </p>
      {pager}
    </div>
    <div class="items">{item_cards}</div>
    {pager}
  </section>
</div>
"""
    return HTMLResponse(page_shell(content))


def render_platform_filter(selected: str, level: str) -> str:
    options = [('all', '全部平台')] + list(PLATFORM_LABELS.items())
    links = []
    for value, label in options:
        style = 'background:#2563eb;color:white;' if value == selected else ''
        links.append(f'<a class="tag" style="{style}" href="/?platform={escape(value)}&level={escape(level)}&page=1">{escape(label)}</a>')
    return '<div class="keywords" style="margin-bottom:10px;">' + ''.join(links) + '</div>'


def render_level_filter(platform: str, selected: str) -> str:
    options = [("all", "全部评级"), ("A", "A级优先"), ("B", "B级"), ("C", "C级")]
    links = []
    for value, label in options:
        style = 'background:#2563eb;color:white;' if value == selected else ''
        links.append(f'<a class="tag" style="{style}" href="/?platform={escape(platform)}&level={value}&page=1">{label}</a>')
    return '<div class="keywords" style="margin-bottom:10px;">' + ''.join(links) + '</div>'


def render_pager(page: int, total_pages: int, total_items: int, platform: str, level: str) -> str:
    prev_page = max(page - 1, 1)
    next_page = min(page + 1, total_pages)
    prev_disabled = 'style="pointer-events:none;opacity:.45;"' if page <= 1 else ''
    next_disabled = 'style="pointer-events:none;opacity:.45;"' if page >= total_pages else ''
    return f"""
<div class="row muted" style="justify-content:space-between;margin-top:10px;">
  <span>共 {total_items} 条，第 {page} / {total_pages} 页，每页 25 条。</span>
  <span class="row">
    <a class="button secondary" {prev_disabled} href="/?platform={escape(platform)}&level={escape(level)}&page={prev_page}">上一页</a>
    <a class="button secondary" {next_disabled} href="/?platform={escape(platform)}&level={escape(level)}&page={next_page}">下一页</a>
  </span>
</div>"""


def render_item(item: Item) -> str:
    margin_class = "danger" if item.gross_margin_percent is not None and item.gross_margin_percent < 30 else ""
    margin = "未计算" if item.gross_margin_percent is None else f"{item.gross_margin_percent:.2f}%"
    image = f'<img src="{escape(item.image_url)}" alt="" style="max-width:120px;border-radius:6px;">' if item.image_url else ""
    buyee_supported, zen_supported, proxy_note = proxy_support(item.platform)
    buyee_button = (
        f'<a class="button secondary" href="{escape(item.buyee_url)}" target="_blank" rel="noreferrer">Buyee搜索</a>'
        if buyee_supported else '<span class="tag">Buyee不适用</span>'
    )
    zen_button = (
        f'<a class="button secondary" href="{escape(item.zenmarket_url)}" target="_blank" rel="noreferrer">ZenMarket搜索</a>'
        if zen_supported else '<span class="tag">ZenMarket不适用</span>'
    )
    return f"""
<article class="item level-{escape(item.alert_level)}">
  <div class="row" style="justify-content:space-between;">
    <h3>{escape(item.title)}</h3>
    <strong>{escape(item.alert_level)}级 / {item.scarcity_score}</strong>
  </div>
  <div class="meta muted">
    <span>{escape(item.platform)}</span>
    <span>{escape(format_price(item.original_price, item.original_currency, item.price_yen))}</span>
    <span>{escape(item.keyword)}</span>
    <span>毛利：<span class="{margin_class}">{margin}</span></span>
  </div>
  {image}
  <div class="row" style="margin-top:10px;">
    <a class="button" href="{escape(item.product_url)}" target="_blank" rel="noreferrer">商品链接</a>
    {buyee_button}
    {zen_button}
  </div>
  <p class="muted">{escape(proxy_note)}</p>
</article>"""


@app.post("/web/keywords")
def web_create_keyword(
    text: str = Form(...),
    group_name: str = Form("default"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    keyword = Keyword(text=text.strip(), group_name=group_name.strip() or "default")
    db.add(keyword)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse("/", status_code=303)


@app.post("/web/keywords/import")
def web_import_keywords(
    keywords: str = Form(...),
    group_name: str = Form("default"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    for text in keywords.splitlines():
        text = text.strip()
        if not text:
            continue
        exists = db.query(Keyword).filter(Keyword.text == text, Keyword.group_name == group_name).first()
        if not exists:
            db.add(Keyword(text=text, group_name=group_name.strip() or "default"))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/web/monitor/run-once")
def web_monitor_once(db: Session = Depends(get_db)) -> RedirectResponse:
    asyncio.run(run_monitor_once(db))
    return RedirectResponse("/", status_code=303)


@app.post("/web/alerts/test")
def web_test_alert() -> RedirectResponse:
    asyncio.run(send_feishu_test_message())
    return RedirectResponse("/", status_code=303)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/seed-keywords", response_model=list[KeywordOut])
def seed_keywords(db: Session = Depends(get_db)) -> list[Keyword]:
    seed_default_keywords(db)
    return db.query(Keyword).filter(Keyword.group_name == "anpanman").order_by(Keyword.text).all()


@app.post("/keywords", response_model=KeywordOut)
def create_keyword(payload: KeywordCreate, db: Session = Depends(get_db)) -> Keyword:
    keyword = Keyword(text=payload.text.strip(), group_name=payload.group_name.strip() or "default")
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    return keyword


@app.post("/keywords/import", response_model=list[KeywordOut])
def import_keywords(payload: KeywordImport, db: Session = Depends(get_db)) -> list[Keyword]:
    imported: list[Keyword] = []
    for text in payload.keywords:
        text = text.strip()
        if not text:
            continue
        existing = db.query(Keyword).filter(Keyword.text == text, Keyword.group_name == payload.group_name).first()
        if existing:
            imported.append(existing)
            continue
        keyword = Keyword(text=text, group_name=payload.group_name)
        db.add(keyword)
        imported.append(keyword)
    db.commit()
    return imported


@app.get("/keywords", response_model=list[KeywordOut])
def list_keywords(db: Session = Depends(get_db)) -> list[Keyword]:
    return db.query(Keyword).order_by(Keyword.group_name, Keyword.text).all()


@app.get("/items/realtime", response_model=list[ItemOut])
def realtime_items(limit: int = 100, db: Session = Depends(get_db)) -> list[Item]:
    return db.query(Item).order_by(desc(Item.fetch_time)).limit(limit).all()


@app.get("/items/scarce", response_model=list[ItemOut])
def scarce_items(limit: int = 100, db: Session = Depends(get_db)) -> list[Item]:
    return db.query(Item).filter(Item.alert_level.in_(["A", "B"])).order_by(desc(Item.scarcity_score)).limit(limit).all()


@app.get("/items/profit", response_model=list[ItemOut])
def profit_items(limit: int = 100, db: Session = Depends(get_db)) -> list[Item]:
    return (
        db.query(Item)
        .filter(Item.gross_margin_percent.isnot(None))
        .order_by(desc(Item.gross_margin_percent))
        .limit(limit)
        .all()
    )


@app.post("/items/{item_id}/profit", response_model=ProfitOutput)
def update_profit(item_id: int, payload: ProfitInput, db: Session = Depends(get_db)) -> ProfitOutput:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    result = calculate_profit(item.price_yen, payload)
    item.expected_sell_price = payload.expected_sell_price
    item.landed_cost = result.landed_cost
    item.gross_margin = result.gross_margin
    item.gross_margin_percent = result.gross_margin_percent
    db.commit()
    return result


@app.get("/history/{item_id}")
def item_history(item_id: int, db: Session = Depends(get_db)) -> dict[str, float | int | None]:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return price_stats(db, sku_from_title(item.title))


@app.post("/monitor/run-once")
def monitor_once(db: Session = Depends(get_db)) -> dict:
    """Run one monitor cycle. Returns ingest counts plus per-platform fetch stats."""
    return asyncio.run(run_monitor_once(db))


@app.get("/proxy/buyee")
def proxy_buyee(q: str) -> RedirectResponse:
    return RedirectResponse(f"https://buyee.jp/item/search/query/{quote_plus(q)}")
