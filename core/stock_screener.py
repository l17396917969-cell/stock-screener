import pandas as pd
import numpy as np
import logging
import time
from .data_fetcher import get_stock_data_yf
from config import SCRENNER_CONFIG

logger = logging.getLogger(__name__)


def pre_screen_stocks(stock_list: list, stock_infos: dict = None) -> list:
    """
    第一层粗筛：剔除明显的垃圾股 (ST)。
    信任 AI 的宏观选择，不再强制剔除创业板/科创板/北交所，
    只要 AI 认为该股符合当前宏观/行业逻辑即可进入深筛。
    """
    logger.info(f"Pre-screening {len(stock_list)} stocks (AI Trust Mode)...")

    candidates = []
    for code in stock_list:
        code_str = str(code).zfill(6)
        
        # 仅根据名称剔除 ST
        if stock_infos:
            name = stock_infos.get(code_str, {}).get('name', '')
            if 'ST' in name.upper():
                logger.debug(f"Filtered ST stock: {code_str} {name}")
                continue
        
        candidates.append(code_str)

    logger.info(f"Level 1 pre-screening passed: {len(candidates)} / {len(stock_list)} stocks.")
    return candidates


def deep_screen_stock(code: str, index_hist=None) -> tuple[bool, str, dict | None]:
    """
    第二层深筛：通过 yfinance 获取财务+技术数据，进行严格排雷。
    返回 (passed: bool, reason: str, data: dict | None)
    """
    data = get_stock_data_yf(code, index_hist=index_hist)
    if data is None:
        return False, "yfinance无数据", None

    cfg = SCRENNER_CONFIG

    # ── 基本面排雷 ──────────────────────────────────────────────
    roe = data.get("roe")
    if roe is None or roe < cfg["MIN_ROE"] / 100:
        return False, f"ROE低 ({roe:.1%})" if roe is not None else "ROE数据缺失", data

    gross_margin = data.get("gross_margin")
    if gross_margin is None or gross_margin < cfg["MIN_GROSS_MARGIN"] / 100:
        return False, f"毛利率低 ({gross_margin:.1%})" if gross_margin is not None else "毛利率数据缺失", data

    # OCF: 经营现金流
    ocf = data.get("operating_cashflow")
    if ocf is None or ocf <= 0:
        return False, f"经营现金流为负 ({ocf})", data

    earnings_growth = data.get("earnings_growth")
    if earnings_growth is None or earnings_growth < cfg["MIN_PROFIT_GROWTH"] / 100:
        val = f"{earnings_growth:.1%}" if earnings_growth is not None else "N/A"
        return False, f"净利增速低 ({val})", data

    # ── 技术面排雷 ──────────────────────────────────────────────
    hist = data.get("hist")
    if hist is None or len(hist) < 20:
        return False, "历史K线不足20日", data

    current_price = data.get("price", 0)
    ma20 = (data.get("ma") or {}).get("ma20", 0)

    if current_price < ma20:
        return False, f"跌破20日均线 (现价{current_price:.2f} < MA20 {ma20:.2f})", data

    # 52周内最高回撤
    high_52w = hist["High"].max()
    drawdown = (high_52w - current_price) / high_52w * 100
    if drawdown > cfg["MAX_DRAWDOWN"]:
        return False, f"历史回撤过大 ({drawdown:.1f}%)", data

    return True, "通过", data


def screen_stocks(stock_infos, index_hist=None, emit_log=None):
    """执行完整的选股流程"""
    def _log(msg, status="info"):
        if emit_log:
            emit_log(msg, status)

    all_stocks = list(stock_infos.keys())

    # 粗筛
    candidates = pre_screen_stocks(all_stocks, stock_infos)
    _log(f"[SCAN] 第一轮粗筛完成，{len(candidates)} 只进入深度财务排雷...", "info")

    passed_stocks = []
    passed_data   = {}   # 保存通过股票的数据供后续评分用

    logger.info(f"Starting Level 2 deep screening for {len(candidates)} stocks...")
    for i, code in enumerate(candidates, 1):
        name = stock_infos.get(code, {}).get("name", code)
        passed, reason, data = deep_screen_stock(code, index_hist=index_hist)

        if passed:
            logger.info(f"[PASS] [PASS] {code} ({name})")
            _log(f"[PASS] {name} ({code}) 通过全部关卡", "pass")
            passed_stocks.append(code)
            passed_data[code] = data
        else:
            logger.debug(f"[FAIL] [DROP] {code} - {reason}")
            _log(f"[FAIL] {name} ({code}) 淘汰 — {reason}", "fail")

        # 每10只略作停顿，防止被限速
        if i % 10 == 0:
            time.sleep(0.5)

    logger.info(f"Screening complete. {len(passed_stocks)} stocks passed.")
    return passed_stocks, passed_data
