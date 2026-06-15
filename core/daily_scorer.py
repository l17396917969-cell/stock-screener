"""每日全量股票评分 — Cron 脚本 (SQLite 版)

遍历 board_stocks.json 中所有行业成分股，逐只评分写入 scores.db。
用法: python core/daily_scorer.py [--limit N] [--force]
"""

import json, logging, os, sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SCRENNER_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_scorer")

SHARED_DIR = os.environ.get("STOCK_SHARED_DIR", "/opt/stock-screener-shared")
BOARD_CACHE = os.path.join(SHARED_DIR, "board_stocks.json")

DEFAULT_SECTORS = [
    "白酒", "食品加工", "调味品", "化学制药", "医疗器械", "生物制品",
    "电池", "光伏", "电网", "半导体", "消费电子", "通信设备",
    "乘用车", "汽车零部件", "工业金属", "能源金属",
    "银行", "证券", "保险", "电力", "煤炭", "石油",
    "元件", "光学光电子", "电子化学品", "家电", "化妆品", "中药", "软件", "计算机",
]

def load_board_stocks():
    if os.path.exists(BOARD_CACHE):
        with open(BOARD_CACHE) as f:
            data = json.load(f)
        logger.info(f"Loaded board_stocks.json: {len(data)} boards")
        return data
    return {}

def build_name_map(board_data):
    nm = {}
    for stocks in board_data.values():
        for item in stocks:
            code = str(item.get("code","")).zfill(6)
            name = str(item.get("name","")).strip()
            if code and name: nm[code] = name
    logger.info(f"Name map: {len(nm)} codes")
    return nm

def collect_stocks(board_data, sectors, name_map, existing_codes):
    seen, stocks = set(), []
    for kw in sectors:
        for bk in [k for k in board_data if kw in k]:
            for item in board_data[bk]:
                code = str(item.get("code","")).zfill(6)
                if code and code not in seen and len(code) == 6:
                    seen.add(code)
                    stocks.append((code, name_map.get(code, item.get("name","")), bk))
    if existing_codes:
        new = [(c,n,s) for c,n,s in stocks if c not in existing_codes]
        logger.info(f"Candidates: {len(stocks)} total, {len(stocks)-len(new)} scored -> {len(new)} to go")
        return new
    logger.info(f"Collected {len(stocks)} unique stocks")
    return stocks

def score_one_stock(code, name, sector, index_hist=None):
    try:
        from core.stock_screener import deep_screen_stock
        from core.scorer import calculate_score
        passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)
        if yf_data is None:
            return {"code":code,"name":name,"sector":sector,"passed":False,"reason":reason or "数据获取失败","score":0,"scored_at":time.strftime("%Y-%m-%d %H:%M:%S")}
        sr = calculate_score(code, {"name":name,"code":code}, yf_data)
        return {"code":code,"name":name,"passed":passed,"reason":reason or "","score":sr.get("total_score",0) if sr else 0,"pe":sr.get("pe",0) if sr else 0,"pb":sr.get("pb",0) if sr else 0,"roe":sr.get("roe",0) if sr else 0,"mcap":sr.get("market_cap",0) if sr else 0,"sector":sector,"scored_at":time.strftime("%Y-%m-%d %H:%M:%S")}
    except Exception:
        logger.error(f"Score {code} {name} failed: {traceback.format_exc()}")
        return {"code":code,"name":name,"sector":sector,"passed":False,"reason":"评分异常","score":0,"scored_at":time.strftime("%Y-%m-%d %H:%M:%S")}

def main(limit=50, force=False):
    logger.info("=== Daily Scorer Start (SQLite) ===")
    t0 = time.time()
    board_data = load_board_stocks()
    if not board_data: return logger.error("No board data")
    name_map = build_name_map(board_data)
    from core.score_store import count as db_count, get_all, upsert_score
    existing = set()
    if not force:
        try:
            rows, _ = get_all(limit=99999)
            existing = {r["code"] for r in rows}
        except: pass
    candidates = collect_stocks(board_data, DEFAULT_SECTORS, name_map, set() if force else existing)
    if not candidates: return logger.info("All scored -- nothing to do")
    to_score = candidates[:limit]
    # 缓存指数数据，整个批次复用
    from core.data_fetcher import get_index_data
    index_hist = get_index_data()
    scored = 0
    for i, (code, name, sector) in enumerate(to_score):
        r = score_one_stock(code, name, sector, index_hist=index_hist)
        if r: upsert_score(r); scored += 1
        if scored % 10 == 0: logger.info(f"Progress: {scored}/{len(to_score)}")
        time.sleep(2)  # Baostock 不需要长间隔，2s 足够
    logger.info(f"=== Done: {scored} new in {time.time()-t0:.0f}s, db total={db_count()} ===")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    main(limit=args.limit, force=args.force)
