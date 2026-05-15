import asyncio
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal, get_db, init_db
from app.models import Item, Keyword
from app.monitor import run_monitor_once
from app.schemas import ItemOut, KeywordCreate, KeywordImport, KeywordOut, ProfitInput, ProfitOutput
from sqlalchemy import func as sqlfunc

from app.services.currency import format_yen_cny
from app.services.history import price_stats, sku_from_title
from app.services.notifications import send_feishu_test_message
from app.services.profit import calculate_profit

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
    if db.query(Keyword).count() > 0:
        return
    for text in DEFAULT_KEYWORDS:
        db.add(Keyword(text=text, group_name="anpanman"))
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
def dashboard(db: Session = Depends(get_db)) -> HTMLResponse:
    settings = get_settings()
    keywords = db.query(Keyword).order_by(Keyword.group_name, Keyword.text).all()
    items = db.query(Item).order_by(desc(Item.fetch_time)).limit(50).all()
    feishu_status = "已配置" if settings.feishu_webhook_url else "未配置"
    keyword_tags = "".join(
        f'<span class="tag">{escape(k.group_name)} / {escape(k.text)}</span>' for k in keywords
    )
    item_cards = "".join(render_item(item) for item in items) or '<div class="panel muted">还没有商品。点击“立即监控一次”开始抓取。</div>'
    platform_rows = _platform_count_rows(db)

    content = f"""
<div class="grid">
  <section class="stack">
    <div class="panel">
      <h2>控制台</h2>
      <p class="muted">飞书：{feishu_status}；后台轮询：每 {settings.monitor_interval_seconds} 秒；价格显示为日元并按汇率约算人民币。</p>
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
      <p class="muted">
        <strong>A级</strong>（高稀缺，推送飞书）：<span style="color:#dc2626;">红色左边框</span> — 近期发布 + 低于均价30%以上 + 含稀有词<br>
        <strong>B级</strong>（中稀缺）：<span style="color:#f59e0b;">橙色左边框</span> — 近期发布 + 低于均价15%以上<br>
        <strong>C级</strong>（普通）：<span style="color:#9ca3af;">灰色左边框</span> — 常规商品<br>
        <strong>分数</strong>：右侧数字（1–100），越高越稀缺。
      </p>
    </div>
    <div class="items">{item_cards}</div>
  </section>
</div>
"""
    return HTMLResponse(page_shell(content))


def render_item(item: Item) -> str:
    margin_class = "danger" if item.gross_margin_percent is not None and item.gross_margin_percent < 30 else ""
    margin = "未计算" if item.gross_margin_percent is None else f"{item.gross_margin_percent:.2f}%"
    image = f'<img src="{escape(item.image_url)}" alt="" style="max-width:120px;border-radius:6px;">' if item.image_url else ""
    return f"""
<article class="item level-{escape(item.alert_level)}">
  <div class="row" style="justify-content:space-between;">
    <h3>{escape(item.title)}</h3>
    <strong>{escape(item.alert_level)}级 / {item.scarcity_score}</strong>
  </div>
  <div class="meta muted">
    <span>{escape(item.platform)}</span>
    <span>{escape(format_yen_cny(item.price_yen))}</span>
    <span>{escape(item.keyword)}</span>
    <span>毛利：<span class="{margin_class}">{margin}</span></span>
  </div>
  {image}
  <div class="row" style="margin-top:10px;">
    <a class="button" href="{escape(item.product_url)}" target="_blank" rel="noreferrer">商品链接</a>
    <a class="button secondary" href="{escape(item.buyee_url)}" target="_blank" rel="noreferrer">Buy via Buyee</a>
    <a class="button secondary" href="{escape(item.zenmarket_url)}" target="_blank" rel="noreferrer">Buy via ZenMarket</a>
  </div>
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
