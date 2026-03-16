import pandas as pd
import numpy as np
import logging
from config import SCORING_WEIGHTS
from .data_fetcher import get_stock_data_yf

logger = logging.getLogger(__name__)

def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except:
        return default

def calculate_score(code: str, stock_info: dict, yf_data: dict | None) -> dict | None:
    """
    19 维度量化审计深度评分逻辑 (v2.0)
    按照 0-10 分阶梯进行逐项审计，并应用 SCORING_WEIGHTS 权重。
    结果中包含具体数值，证据中体现具体的数据溯源。
    """
    if yf_data is None:
        return None

    audit_report = []
    weighted_total = 0
    
    # 提取预先数据 (来自 data_fetcher 计算出的指标)
    current_price = safe_float(yf_data.get("price"))
    ma = yf_data.get("ma", {})
    ma5, ma10, ma20, ma60 = ma.get("ma5", 0), ma.get("ma10", 0), ma.get("ma20", 0), ma.get("ma60", 0)
    vwap = safe_float(yf_data.get("vwap"))
    vcp_ratio = safe_float(yf_data.get("vcp_ratio", 1.0))
    rps = safe_float(yf_data.get("rps", 1.0))
    adx = safe_float(yf_data.get("adx", 0))
    boll_pct_b = safe_float(yf_data.get("boll_pct_b", 0.5))
    hist = yf_data.get("hist")
    
    # 证据源常数
    EV_TECH = "YFinance 历史K线演算"
    EV_INDEX = "YFinance 市场大盘对比"
    EV_FUND = "YFinance 公司基本面报表"
    
    # --- 1. 技术面审计 (30%) ---
    # 1.1 均线趋势
    if ma5 > ma10 > ma20 > ma60 and ma60 > 0: s1, res1 = 10, f"[PASS] 完全多头排列 (MA20:{ma20:.2f})"
    elif ma5 > ma20 and ma20 > ma60: s1, res1 = 7, f"[WARN] 部分多头排列 (MA20:{ma20:.2f}, MA60:{ma60:.2f})"
    elif ma5 > ma20: s1, res1 = 4, f"⏸ 均线缠绕 (MA5:{ma5:.2f}, MA20:{ma20:.2f})"
    else: s1, res1 = 0, f"[FAIL] 空头排列 (MA20:{ma20:.2f})"
    ev1 = EV_TECH
    
    # 1.2 VWAP
    if current_price > vwap and vwap > 0: s2, res2 = 10, f"[PASS] 现价 > VWAP ({vwap:.2f})"
    else: s2, res2 = 0, f"[FAIL] 现价 < VWAP ({vwap:.2f})"
    ev2 = EV_TECH
    
    # 1.3 VCP 波动收缩
    if vcp_ratio < 0.8: s3, res3 = 10, f"[PASS] 波动强烈收缩 ({vcp_ratio:.2%})"
    elif 0.8 <= vcp_ratio <= 1.0: s3, res3 = 6, f"🆗 波动相对稳定 ({vcp_ratio:.2%})"
    else: s3, res3 = 0, f"[FAIL] 波动异常放大 ({vcp_ratio:.2%})"
    ev3 = EV_TECH
    
    # 1.4 RPS 相对强度
    if rps > 1.2: s4, res4 = 10, f"🚀 极强 (RPS={rps:.2f})"
    elif 1.0 < rps <= 1.2: s4, res4 = 7, f"[UP] 走强 (RPS={rps:.2f})"
    elif 0.8 <= rps <= 1.0: s4, res4 = 3, f"[DOWN] 走弱 (RPS={rps:.2f})"
    else: s4, res4 = 0, f"[FAIL] 极弱 (RPS={rps:.2f})"
    ev4 = EV_INDEX
    
    # 1.5 成交量结构 (简易价量配合判定)
    vol_ratio = 1.0
    if hist is not None and len(hist) >= 2:
        price_up = hist['Close'].iloc[-1] > hist['Close'].iloc[-2]
        vol_up = hist['Volume'].iloc[-1] > hist['Volume'].iloc[-2]
        vol_val = hist['Volume'].iloc[-1]
        vol_5ma = hist['Volume'].iloc[-5:].mean() if len(hist) >= 5 else vol_val
        vol_mult = vol_val / vol_5ma if vol_5ma > 0 else 1.0
        
        if (price_up and vol_up) or (not price_up and not vol_up): s5, res5 = 10, f"[PASS] 量价配合健康 ({vol_mult:.1f}x均量)"
        elif price_up and not vol_up: s5, res5 = 5, f"[WARN] 缩量上涨 ({vol_mult:.1f}x均量)"
        else: s5, res5 = 0, f"[FAIL] 量价背离 ({vol_mult:.1f}x均量)"
    else: s5, res5 = 5, "⏸ 数据不足"
    ev5 = EV_TECH
    
    # 1.6 ADX 趋势强度
    if adx > 30: s6, res6 = 10, f"🔥 趋势强劲 (ADX={adx:.1f})"
    elif 20 <= adx <= 30: s6, res6 = 6, f"🆗 趋势温和 (ADX={adx:.1f})"
    else: s6, res6 = 0, f"⏸ 无明显趋势 (ADX={adx:.1f})"
    ev6 = EV_TECH
    
    # 1.7 布林带位置 (pct_b: 0下轨, 1上轨)
    if boll_pct_b < 0.3: s7, res7 = 10, f"💎 低位超卖 (布林PctB={boll_pct_b:.2f})"
    elif 0.3 <= boll_pct_b <= 0.7: s7, res7 = 5, f"🆗 均衡位置 (布林PctB={boll_pct_b:.2f})"
    else: s7, res7 = 0, f"[WARN] 高位超买 (布林PctB={boll_pct_b:.2f})"
    ev7 = EV_TECH
    
    # --- 2. 基本面审计 (40%) ---
    # 2.1 ROE 阶梯评分
    roe_val = safe_float(yf_data.get("roe")) * 100
    if roe_val > 20: s8, res8 = 10, f"[PASS] 优秀 ({roe_val:.1f}%)"
    elif 10 <= roe_val <= 20: s8, res8 = 6, f"🆗 良好 ({roe_val:.1f}%)"
    else: s8, res8 = 0, f"[FAIL] 较低 ({roe_val:.1f}%)"
    ev8 = EV_FUND
    
    # 2.2 净利增速
    gr_val = safe_float(yf_data.get("earnings_growth")) * 100
    if gr_val > 30: s9, res9 = 10, f"🚀 高增长 ({gr_val:+.1f}%)"
    elif 10 <= gr_val <= 30: s9, res9 = 6, f"[UP] 稳健 ({gr_val:+.1f}%)"
    else: s9, res9 = 0, f"[FAIL] 负增长/缓慢 ({gr_val:+.1f}%)"
    ev9 = EV_FUND
    
    # 2.3 PEG
    pe = safe_float(yf_data.get("pe_ttm"))
    peg = pe / gr_val if gr_val > 0 else 99
    if peg < 1.0: s10, res10 = 10, f"[PASS] 低估 (PEG={peg:.2f})"
    elif 1.0 <= peg <= 2.0: s10, res10 = 5, f"🆗 合理 (PEG={peg:.2f})"
    else: s10, res10 = 0, f"[WARN] 高估/无法计算 (PEG={peg:.2f})"
    ev10 = EV_FUND
    
    # 2.4 毛利率趋势 (简化为当前毛利率水平)
    gm = safe_float(yf_data.get("gross_margin")) * 100
    if gm > 30: s11, res11 = 10, f"[PASS] 护城河深盾 ({gm:.1f}%)"
    elif gm > 15: s11, res11 = 5, f"🆗 盈利中等 ({gm:.1f}%)"
    else: s11, res11 = 0, f"[FAIL] 盈利薄弱 ({gm:.1f}%)"
    ev11 = EV_FUND
    
    # 2.5 ROIC
    roic = safe_float(yf_data.get("roic")) * 100
    if roic > 15: s12, res12 = 10, f"[PASS] 高效率 ({roic:.1f}%)"
    elif 10 <= roic <= 15: s12, res12 = 6, f"🆗 中等 ({roic:.1f}%)"
    else: s12, res12 = 0, f"[FAIL] 低效 ({roic:.1f}%)"
    ev12 = EV_FUND
    
    # 2.6 FCF
    fcf = safe_float(yf_data.get("fcf"))
    if fcf > 0: s13, res13 = 10, f"[PASS] 净流出为正 ({fcf/1e8:.1f}亿)"
    else: s13, res13 = 0, "[FAIL] 现金流为负"
    ev13 = EV_FUND
    
    # 2.7 行业地位
    cap = safe_float(yf_data.get("market_cap"))
    if cap > 1000e8: s14, res14 = 10, f"👑 巨头 (市值{cap/1e8:.0f}亿)"
    elif cap > 300e8: s14, res14 = 6, f"🐄 中坚 (市值{cap/1e8:.0f}亿)"
    else: s14, res14 = 0, f"🐜 小盘 (市值{cap/1e8:.0f}亿)"
    ev14 = EV_FUND
    
    # 2.8 PE百分位 
    if pe > 0 and pe < 15: s15, res15 = 10, f"[PASS] 底部 (PE={pe:.1f})"
    elif 15 <= pe < 30: s15, res15 = 5, f"🆗 适中 (PE={pe:.1f})"
    else: s15, res15 = 0, f"[WARN] 高位/亏损 (PE={pe:.1f})"
    ev15 = EV_FUND

    # --- 3. 资金面审计 (30%) ---
    # 3.1 换手率
    to = safe_float(yf_data.get("turnover_rate"))
    if 3 <= to <= 8: s16, res16 = 10, f"[PASS] 温和活跃 ({to:.1f}%)"
    elif 1 <= to < 3 or 8 < to <= 15: s16, res16 = 5, f"🆗 交易适度 ({to:.1f}%)"
    else: s16, res16 = 0, f"[WARN] 冷清或过热 ({to:.1f}%)"
    ev16 = EV_TECH
    
    # 获取真实量化资金流动口径
    mf_data = yf_data.get("money_flow", {})

    # 3.2 陆股通/北向资金流 (历史测算)
    hsgt = mf_data.get("hsgt_hold_change")
    ev17 = "AKShare 行情·陆股通明细"
    if hsgt is not None:
        if hsgt > 0: s17, res17 = 10, f"[PASS] 外资增仓偏好 (+{hsgt/1e8:.2f}亿)"
        elif hsgt < 0: s17, res17 = 0, f"[WARN] 外资减持迹象 ({hsgt/1e8:.2f}亿)"
        else: s17, res17 = 5, f"⏸ 外资持平 (0.00)"
    else:
         s17, res17 = 5, "⏸ 北向资金(暂无数据)"

    # 3.3 融券变 / 杠杆资金偏好 (利用 YF ShortRatio 或置空)
    ev18 = "YFinance 交易者行为"
    sr = safe_float(yf_data.get("short_ratio"), -1)
    if sr >= 0:
        if sr > 5: s18, res18 = 0, f"[WARN] 空头占优 (Short={sr:.1f})"
        else: s18, res18 = 10, f"[PASS] 杠杆常态 (Short={sr:.1f})"
    else:
        s18, res18 = 5, "⏸ 融资融券(数据受限)"

    # 3.4 主力单净流入金额
    ev19 = "AKShare 东方财富·主力资金流"
    main_in = mf_data.get("main_net_in")
    if main_in is not None:
        if main_in > 0: s19, res19 = 10, f"🔥 主力大单流入 (+{main_in/1e4:.0f}万)"
        elif main_in < 0: s19, res19 = 0, f"[WARN] 主力大单流出 ({main_in/1e4:.0f}万)"
        else: s19, res19 = 5, f"⏸ 主力震荡盘整 (0.00)"
    else:
        s19, res19 = 5, "⏸ 主力资金(暂无数据)"


    # 计算加权分
    # tech_score = (s1+s2+s3+s4+s5+s6+s7) / 70 * 10
    # fund_score = (s8+s9+s10+s11+s12+s13+s14+s15) / 80 * 10
    # flow_score = (s16+s17+s18+s19) / 40 * 10
    
    # 应用 config 中的权重
    weighted_total = (
        s1/10 * SCORING_WEIGHTS["MA_TREND"] +
        s2/10 * SCORING_WEIGHTS["VWAP"] +
        s3/10 * SCORING_WEIGHTS["VCP"] +
        s4/10 * SCORING_WEIGHTS["RPS"] +
        s5/10 * SCORING_WEIGHTS["VOLUME_STR"] +
        s6/10 * SCORING_WEIGHTS["ADX"] +
        s7/10 * SCORING_WEIGHTS["BOLL"] +
        s8/10 * SCORING_WEIGHTS["ROE"] +
        s9/10 * SCORING_WEIGHTS["PROFIT_GROWTH"] +
        s10/10 * SCORING_WEIGHTS["PEG"] +
        s11/10 * SCORING_WEIGHTS["GROSS_MARGIN"] +
        s12/10 * SCORING_WEIGHTS["ROIC"] +
        s13/10 * SCORING_WEIGHTS["FCF"] +
        s14/10 * SCORING_WEIGHTS["INDUSTRY_RANK"] +
        s15/10 * SCORING_WEIGHTS["PE_PERCENTILE"] +
        s16/10 * SCORING_WEIGHTS["TURNOVER"] +
        s17/10 * SCORING_WEIGHTS["NORTH_MONEY"] +
        s18/10 * SCORING_WEIGHTS["MARGIN_TRADE"] +
        s19/10 * SCORING_WEIGHTS["MAIN_MONEY"]
    )
    
    # 构建报告格式
    dim_map = {
        "1.1 均线": ("技术面", s1, res1, ev1),
        "1.2 VWAP": ("", s2, res2, ev2),
        "1.3 VCP": ("", s3, res3, ev3),
        "1.4 RPS": ("", s4, res4, ev4),
        "1.5 成交量": ("", s5, res5, ev5),
        "1.6 ADX": ("", s6, res6, ev6),
        "1.7 布林带": ("", s7, res7, ev7),
        "2.1 ROE": ("基本面", s8, res8, ev8),
        "2.2 净利速": ("", s9, res9, ev9),
        "2.3 PEG": ("", s10, res10, ev10),
        "2.4 毛利趋势": ("", s11, res11, ev11),
        "2.5 ROIC": ("", s12, res12, ev12),
        "2.6 现金流": ("", s13, res13, ev13),
        "2.7 行业位": ("", s14, res14, ev14),
        "2.8 PE分位": ("", s15, res15, ev15),
        "3.1 换手率": ("资金面", s16, res16, ev16),
        "3.2 北向流": ("", s17, res17, ev17),
        "3.3 融券变": ("", s18, res18, ev18),
        "3.4 主力流": ("", s19, res19, ev19),
    }
    
    report = []
    for name, (dim, s, res, ev) in dim_map.items():
        report.append({
            "dim": dim,
            "name": name,
            "res": res,
            "evidence": ev,
            "score": round(s, 1)
        })

    return {
        "symbol": code,
        "name": yf_data.get("name", code),
        "sectors": ", ".join(stock_info.get("sectors", [])),
        "total_score": round(weighted_total),
        "report": report,
        "latest_price": current_price
    }

def score_and_rank_stocks(passed_symbols: list, stock_infos: dict, passed_data: dict = None) -> list:
    if passed_data is None: passed_data = {}
    results = []
    for code in passed_symbols:
        res = calculate_score(code, stock_infos.get(code, {}), passed_data.get(code))
        if res: results.append(res)
    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results
