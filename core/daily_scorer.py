"""每日全量股票评分 — Cron 脚本

遍历 board_stocks.json 中所有行业成分股，
逐只 deep_screen_stock + calculate_score，
输出 scored_stocks.json 供对话查询。

用法: python core/daily_scorer.py
"""

import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path

# 确保项目路径可用
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SCRENNER_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_scorer")

# 输出路径 — 放在 shared 目录，与数据库同级
SHARED_DIR = os.environ.get(
    "STOCK_SHARED_DIR",
    "/opt/stock-screener-shared",
)
OUTPUT_FILE = os.path.join(SHARED_DIR, "scored_stocks.json")

# 预设评分行业列表 (价值投资关注的主要板块)
DEFAULT_SECTORS = [
    "元件", "光学光电子", "电子化学品Ⅱ",
    "白酒Ⅱ", "食品加工", "调味品Ⅱ",
    "化学制药", "医疗器械", "生物制品",
    "电池", "光伏设备", "电网设备",
    "半导体", "消费电子", "通信设备",
    "乘用车", "汽车零部件",
    "工业金属", "能源金属",
    "银行", "证券Ⅱ", "保险Ⅱ",
    "电力", "煤炭开采", "石油化工",
]

# 单次运行最多评分只数 (防止超时)
MAX_STOCKS = 500


def load_existing_scores() -> dict:
    """加载已有评分结果。"""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_scores(scores: dict) -> None:
    """原子写入评分结果。"""
    tmp = OUTPUT_FILE + ".tmp"
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUTPUT_FILE)
    logger.info(f"Saved {len(scores)} stocks → {OUTPUT_FILE}")


def load_board_stocks() -> dict[str, dict]:
    """加载全量成分股缓存。"""
    cache_path = os.path.join(SHARED_DIR, "board_stocks.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            data = json.load(f)
        logger.info(f"Loaded board_stocks.json: {len(data)} boards")
        return data
    logger.warning("board_stocks.json not found")
    return {}


def collect_stocks(board_data: dict, sectors: list[str]) -> list[tuple[str, str]]:
    """从板块数据中提取候选股 (code, name)。"""
    seen = set()
    stocks = []
    for sector in sectors:
        board = board_data.get(sector, [])
        for item in board:
            code = str(item.get("code", "")).zfill(6)
            name = str(item.get("name", ""))
            if code and code not in seen and len(code) == 6:
                seen.add(code)
                stocks.append((code, name))
    logger.info(f"Collected {len(stocks)} unique stocks from {len(sectors)} sectors")
    return stocks


def score_one_stock(code: str, name: str) -> dict | None:
    """对单只股票评分。"""
    try:
        from core.stock_screener import deep_screen_stock
        from core.scorer import calculate_score
        from core.data_fetcher import get_index_data

        index_hist = get_index_data()
        passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)

        if yf_data is None:
            return {"code": code, "name": name, "passed": False, "reason": reason, "score": 0}

        score_report = calculate_score(code, {"name": name, "code": code}, yf_data)

        return {
            "code": code,
            "name": name,
            "passed": passed,
            "reason": reason,
            "score": score_report.get("total_score", 0) if score_report else 0,
            "pe": score_report.get("pe", 0) if score_report else 0,
            "pb": score_report.get("pb", 0) if score_report else 0,
            "roe": score_report.get("roe", 0) if score_report else 0,
            "mcap": score_report.get("market_cap", 0) if score_report else 0,
            "sector": score_report.get("sector", "") if score_report else "",
            "scored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception:
        logger.error(f"Score {code} {name} failed: {traceback.format_exc()}")
        return {"code": code, "name": name, "passed": False, "reason": "评分异常", "score": 0}


def main():
    logger.info("=== Daily Scorer Start ===")
    t0 = time.time()

    # 加载已有评分
    scores = load_existing_scores()
    logger.info(f"Existing scores: {len(scores)} stocks")

    # 加载板块数据
    board_data = load_board_stocks()
    if not board_data:
        logger.error("No board data — abort")
        return

    # 收集候选股
    candidates = collect_stocks(board_data, DEFAULT_SECTORS)
    if not candidates:
        logger.error("No candidates — abort")
        return

    # 只评分新股票 或 更新全部 (先做增量，保底上限)
    to_score = [(c, n) for c, n in candidates[:MAX_STOCKS]]

    scored = 0
    for i, (code, name) in enumerate(to_score):
        result = score_one_stock(code, name)
        if result:
            scores[code] = result
            scored += 1
            if scored % 20 == 0:
                logger.info(f"Progress: {scored}/{len(to_score)}")

        # 限速: yfinance 5 分钟内最多 ~30 次，所以间隔 12s
        time.sleep(12)

        # 每 50 只存一次
        if scored % 50 == 0:
            save_scores(scores)

    save_scores(scores)

    elapsed = time.time() - t0
    logger.info(f"=== Done: {scored} stocks in {elapsed:.0f}s ===")


if __name__ == "__main__":
    main()
