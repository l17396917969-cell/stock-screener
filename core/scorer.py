"""
价值投资评分引擎 (Value Investing Scoring Engine)
格雷厄姆/巴菲特式选股：找被低估、有未来、值得长期持有的 A 股潜力股。

评分体系：估值30分 + 质量40分 + 成长30分 = 100分
"""
import pandas as pd
import numpy as np
import logging
from config import VALUE_SCORING_WEIGHTS

logger = logging.getLogger(__name__)


def safe_float(val, default=0.0):
    """安全转换数值，处理 None/NaN"""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except Exception:
        return default


def score_with_sparse_fallback(value, missing_score, scorer):
    """
    数据缺失时给予默认分 + 标记，有数据时走 scorer(value)。
    scorer 返回 (score_0_10, result_str) 元组。
    """
    if value is None:
        return missing_score, "⏸ 数据稀疏(供应商未覆盖)"
    return scorer(float(value))


def _compute_pe_percentile_from_hist(hist, current_pe):
    """
    从历史K线数据中的 PETTM 列计算当前 PE 的历史分位（百分位）。
    分位越低 = 估值越便宜 = 得分越高。
    返回 (score_0_10, reason_str) 或 (None, None) 若无法计算。
    """
    if hist is None or hist.empty:
        return None, None
    if "PETTM" not in hist.columns:
        return None, None

    pe_series = pd.to_numeric(hist["PETTM"], errors="coerce").dropna()
    if len(pe_series) < 60 or current_pe is None or current_pe <= 0:
        return None, None

    # 计算当前PE在历史中的分位（越低越便宜）
    percentile = (pe_series < current_pe).sum() / len(pe_series) * 100

    if percentile <= 20:
        return 10, f"[PASS] PE处于历史底部 ({percentile:.0f}%分位, PE={current_pe:.1f})"
    elif percentile <= 40:
        return 7, f"📉 PE偏低 ({percentile:.0f}%分位, PE={current_pe:.1f})"
    elif percentile <= 60:
        return 5, f"🆗 PE适中 ({percentile:.0f}%分位, PE={current_pe:.1f})"
    elif percentile <= 80:
        return 3, f"📈 PE偏高 ({percentile:.0f}%分位, PE={current_pe:.1f})"
    else:
        return 1, f"[WARN] PE处于历史高位 ({percentile:.0f}%分位, PE={current_pe:.1f})"


def calculate_score(code: str, stock_info: dict, yf_data: dict | None) -> dict | None:
    """
    价值投资量化评分 (v3.0)
    估值30分 + 质量40分 + 成长30分 = 100分

    与旧版 calculate_score() 保持相同的函数签名以维持向后兼容。
    """
    if yf_data is None:
        return None

    audit_report = []
    weighted_total = 0
    W = VALUE_SCORING_WEIGHTS  # 权重缩写

    # ── 提取基础数据 ─────────────────────────────────────
    current_price = safe_float(yf_data.get("price"))
    pe_ttm = safe_float(yf_data.get("pe_ttm"), None)
    if pe_ttm is None:
        pe_ttm = None  # 保持 None 语义
    pb_val = safe_float(yf_data.get("pb"), None)
    dividend_yield = safe_float(yf_data.get("dividend_yield"), 0) or 0
    market_cap = safe_float(yf_data.get("market_cap"), None)
    fcf = safe_float(yf_data.get("fcf"), None)
    op_cf = safe_float(yf_data.get("operating_cashflow"), None)
    roe = safe_float(yf_data.get("roe"), None)
    roic = safe_float(yf_data.get("roic"), None)
    gross_margin = safe_float(yf_data.get("gross_margin"), None)
    earnings_growth = safe_float(yf_data.get("earnings_growth"), None)
    revenue_growth = safe_float(yf_data.get("revenue_growth"), None)
    net_profit = safe_float(yf_data.get("net_profit"), None)
    hist = yf_data.get("hist")

    EV_FUND = "YFinance/Baostock 基本面报表"

    # ═════════════════════════════════════════════════════
    # 维度 1: 估值维度 (共 30分)
    # ═════════════════════════════════════════════════════

    # 1.1 PE历史分位 (6分) —— 越低越便宜
    pe_hist_score, pe_hist_res = _compute_pe_percentile_from_hist(hist, pe_ttm)
    if pe_hist_score is None:
        # 回退到绝对PE估值
        if pe_ttm is None:
            s1, res1 = 3, "⏸ 数据稀疏(PE暂缺)"
        elif pe_ttm < 15:
            s1, res1 = 10, f"[PASS] PE底部区域 (PE={pe_ttm:.1f})"
        elif pe_ttm < 25:
            s1, res1 = 7, f"📉 PE偏低 (PE={pe_ttm:.1f})"
        elif pe_ttm < 35:
            s1, res1 = 5, f"🆗 PE适中 (PE={pe_ttm:.1f})"
        elif pe_ttm < 50:
            s1, res1 = 3, f"📈 PE偏高 (PE={pe_ttm:.1f})"
        else:
            s1, res1 = 1, f"[WARN] PE高位 (PE={pe_ttm:.1f})"
    else:
        s1, res1 = pe_hist_score, pe_hist_res
    ev1 = EV_FUND

    # 1.2 PB 市净率 (5分) —— 资产折价程度
    if pb_val is None:
        s2, res2 = 3, "⏸ 数据稀疏(PB暂缺)"
    elif pb_val < 1:
        s2, res2 = 10, f"[PASS] 破净！资产折价 (PB={pb_val:.2f})"
    elif pb_val < 2:
        s2, res2 = 8, f"📉 低估值 (PB={pb_val:.2f})"
    elif pb_val < 3:
        s2, res2 = 6, f"🆗 合理估值 (PB={pb_val:.2f})"
    elif pb_val < 5:
        s2, res2 = 4, f"📈 偏高 (PB={pb_val:.2f})"
    elif pb_val < 8:
        s2, res2 = 2, f"[WARN] 高估 (PB={pb_val:.2f})"
    else:
        s2, res2 = 0, f"[FAIL] 严重高估 (PB={pb_val:.2f})"
    ev2 = EV_FUND

    # 1.3 PEG 估值性价比 (6分)
    gr_val = (earnings_growth or 0) * 100  # 转为百分比
    if pe_ttm is None or earnings_growth is None or gr_val <= 0:
        s3, res3 = 3, "⏸ 数据稀疏(PEG暂不可比)"
    else:
        peg = pe_ttm / gr_val if gr_val > 0 else 99
        if peg < 1.0:
            s3, res3 = 10, f"[PASS] 低估成长 (PEG={peg:.2f})"
        elif peg < 1.5:
            s3, res3 = 7, f"📉 较便宜 (PEG={peg:.2f})"
        elif peg < 2.0:
            s3, res3 = 5, f"🆗 合理 (PEG={peg:.2f})"
        elif peg < 3.0:
            s3, res3 = 3, f"📈 偏贵 (PEG={peg:.2f})"
        else:
            s3, res3 = 0, f"[WARN] 高估/无法计算 (PEG={peg:.2f})"
    ev3 = EV_FUND

    # 1.4 股息率 (5分) —— 现金回报，防御性指标
    div_pct = dividend_yield * 100 if dividend_yield else 0
    if dividend_yield is None or dividend_yield == 0:
        s4, res4 = 3, "🆗 不分红(成长型公司可接受)"
    elif div_pct > 4:
        s4, res4 = 10, f"[PASS] 高股息 ({div_pct:.1f}%)"
    elif div_pct > 3:
        s4, res4 = 8, f"📈 丰厚股息 ({div_pct:.1f}%)"
    elif div_pct > 2:
        s4, res4 = 6, f"🆗 有分红 ({div_pct:.1f}%)"
    elif div_pct > 1:
        s4, res4 = 4, f"📉 微薄分红 ({div_pct:.1f}%)"
    else:
        s4, res4 = 2, f"⏸ 象征性分红 ({div_pct:.1f}%)"
    ev4 = EV_FUND

    # 1.5 自由现金流收益率 (8分) —— 真金白银回报率
    if fcf is not None and market_cap is not None and market_cap > 0:
        fcf_yield = fcf / market_cap * 100
        if fcf_yield > 10:
            s5, res5 = 10, f"[PASS] 极高FCF收益 ({fcf_yield:.1f}%)"
        elif fcf_yield > 5:
            s5, res5 = 8, f"📈 高FCF收益 ({fcf_yield:.1f}%)"
        elif fcf_yield > 2:
            s5, res5 = 6, f"🆗 合理FCF收益 ({fcf_yield:.1f}%)"
        elif fcf_yield > 0:
            s5, res5 = 4, f"📉 低FCF收益 ({fcf_yield:.1f}%)"
        else:
            s5, res5 = 0, f"[FAIL] FCF为负 ({fcf_yield:.1f}%)"
    else:
        s5, res5 = 3, "⏸ 数据稀疏(FCF/市值暂缺)"
    ev5 = EV_FUND

    # ═════════════════════════════════════════════════════
    # 维度 2: 质量维度 (共 40分)
    # ═════════════════════════════════════════════════════

    # 2.1 ROE 水平 (8分) —— 股东回报核心
    s6, res6 = score_with_sparse_fallback(
        roe,
        3,
        lambda raw: (
            (10, f"[PASS] 卓越 ({raw * 100:.1f}%)")
            if raw * 100 > 20
            else (8, f"📈 优秀 ({raw * 100:.1f}%)")
            if raw * 100 > 15
            else (6, f"🆗 良好 ({raw * 100:.1f}%)")
            if raw * 100 > 12
            else (4, f"📉 及格 ({raw * 100:.1f}%)")
            if raw * 100 > 8
            else (0, f"[FAIL] 偏低 ({raw * 100:.1f}%)")
        ),
    )
    ev6 = EV_FUND

    # 2.2 ROIC 资本回报率 (7分) —— 剔除杠杆后的真实盈利能力
    s7, res7 = score_with_sparse_fallback(
        roic,
        3,
        lambda raw: (
            (10, f"[PASS] 高效率 ({raw * 100:.1f}%)")
            if raw * 100 > 15
            else (7, f"📈 较好 ({raw * 100:.1f}%)")
            if raw * 100 > 10
            else (5, f"🆗 中等 ({raw * 100:.1f}%)")
            if raw * 100 > 8
            else (2, f"[WARN] 偏低 ({raw * 100:.1f}%)")
        ),
    )
    ev7 = EV_FUND

    # 2.3 毛利率稳定性 (6分) —— 护城河宽度
    s8, res8 = score_with_sparse_fallback(
        gross_margin,
        3,
        lambda raw: (
            (10, f"[PASS] 宽护城河 ({raw * 100:.1f}%)")
            if raw * 100 > 40
            else (7, f"📈 较强定价权 ({raw * 100:.1f}%)")
            if raw * 100 > 30
            else (5, f"🆗 盈利中等 ({raw * 100:.1f}%)")
            if raw * 100 > 20
            else (2, f"[WARN] 盈利薄弱 ({raw * 100:.1f}%)")
        ),
    )
    ev8 = EV_FUND

    # 2.4 FCF/净利润比 (7分) —— 利润含金量
    if net_profit is not None and net_profit > 0 and fcf is not None:
        fcf_np_ratio = fcf / net_profit
        if fcf_np_ratio > 1.0:
            s9, res9 = 10, f"[PASS] 利润含金量极高 (FCF/NP={fcf_np_ratio:.2f})"
        elif fcf_np_ratio > 0.8:
            s9, res9 = 8, f"📈 利润质量好 (FCF/NP={fcf_np_ratio:.2f})"
        elif fcf_np_ratio > 0.5:
            s9, res9 = 6, f"🆗 利润含金量一般 (FCF/NP={fcf_np_ratio:.2f})"
        elif fcf_np_ratio > 0:
            s9, res9 = 4, f"📉 利润含金量低 (FCF/NP={fcf_np_ratio:.2f})"
        else:
            s9, res9 = 0, f"[FAIL] 现金流亏损 (FCF/NP={fcf_np_ratio:.2f})"
    else:
        s9, res9 = 3, "⏸ 数据稀疏(FCF/NP暂缺)"
    ev9 = EV_FUND

    # 2.5 负债率/财务健康度 (6分) —— 从PB推测资产结构
    # 注：完整负债率需资产负债数据，当前以PB作为代理指标
    # PB低 + 盈利好 → 财务稳健；PB极高 → 可能杠杆过高
    if pb_val is not None:
        if pb_val < 1.5:
            s10, res10 = 10, f"[PASS] 资产扎实 (PB={pb_val:.2f}, 低杠杆)"
        elif pb_val < 3:
            s10, res10 = 7, f"📈 财务稳健 (PB={pb_val:.2f})"
        elif pb_val < 5:
            s10, res10 = 5, f"🆗 杠杆适中 (PB={pb_val:.2f})"
        elif pb_val < 8:
            s10, res10 = 3, f"📉 杠杆偏高 (PB={pb_val:.2f})"
        else:
            s10, res10 = 1, f"[WARN] 高杠杆/轻资产 (PB={pb_val:.2f})"
    else:
        s10, res10 = 3, "⏸ 数据稀疏(负债率暂缺)"
    ev10 = EV_FUND

    # 2.6 经营现金流 (6分) —— 造血能力
    if op_cf is not None and op_cf > 0:
        if market_cap is not None and market_cap > 0:
            cf_ratio = op_cf / market_cap * 100
            if cf_ratio > 5:
                s11, res11 = 10, f"[PASS] 强劲造血 ({cf_ratio:.1f}% 市值)"
            elif cf_ratio > 2:
                s11, res11 = 8, f"📈 良好造血 ({cf_ratio:.1f}% 市值)"
            elif cf_ratio > 1:
                s11, res11 = 6, f"🆗 正常造血 ({cf_ratio:.1f}% 市值)"
            else:
                s11, res11 = 4, f"📉 造血偏弱 ({cf_ratio:.1f}% 市值)"
        else:
            s11, res11 = 7, f"[PASS] 经营现金流为正"
    elif op_cf is not None and op_cf <= 0:
        s11, res11 = 0, f"[FAIL] 经营现金流为负"
    else:
        s11, res11 = 3, "⏸ 数据稀疏(经营现金流暂缺)"
    ev11 = EV_FUND

    # ═════════════════════════════════════════════════════
    # 维度 3: 成长维度 (共 30分)
    # ═════════════════════════════════════════════════════

    # 3.1 扣非净利润 3年复合增速 (10分) —— 用单年增速作为代理
    s12, res12 = score_with_sparse_fallback(
        earnings_growth,
        3,
        lambda raw: (
            (10, f"🚀 高增长 ({raw * 100:+.1f}%)")
            if raw * 100 > 30
            else (7, f"📈 稳健增长 ({raw * 100:+.1f}%)")
            if raw * 100 > 20
            else (5, f"🆗 中速增长 ({raw * 100:+.1f}%)")
            if raw * 100 > 10
            else (3, f"📉 低速增长 ({raw * 100:+.1f}%)")
            if raw * 100 > 5
            else (1, f"[WARN] 停滞/负增长 ({raw * 100:+.1f}%)")
        ),
    )
    ev12 = EV_FUND

    # 3.2 营收增速 (8分) —— 业务扩张能力
    s13, res13 = score_with_sparse_fallback(
        revenue_growth,
        3,
        lambda raw: (
            (10, f"📈 高速扩张 ({raw * 100:+.1f}%)")
            if raw * 100 > 20
            else (7, f"📈 稳健扩张 ({raw * 100:+.1f}%)")
            if raw * 100 > 10
            else (5, f"🆗 温和增长 ({raw * 100:+.1f}%)")
            if raw * 100 > 5
            else (3, f"📉 增长放缓 ({raw * 100:+.1f}%)")
            if raw * 100 > 0
            else (0, f"[WARN] 营收萎缩 ({raw * 100:+.1f}%)")
        ),
    )
    ev13 = EV_FUND

    # 3.3 研发投入占比 (6分) —— 创新驱动
    # 注：完整研发数据需从财报附注提取，当前以毛利率作为创新能力的代理
    # 高毛利率通常意味着高研发/品牌壁垒
    if gross_margin is not None:
        gm_pct = gross_margin * 100
        if gm_pct > 50:
            s14, res14 = 10, f"[PASS] 极高毛利暗示强研发/品牌壁垒 ({gm_pct:.1f}%)"
        elif gm_pct > 35:
            s14, res14 = 7, f"📈 高毛利，创新投入可期 ({gm_pct:.1f}%)"
        elif gm_pct > 25:
            s14, res14 = 5, f"🆗 中等毛利 ({gm_pct:.1f}%)"
        elif gm_pct > 15:
            s14, res14 = 3, f"📉 低毛利，研发空间有限 ({gm_pct:.1f}%)"
        else:
            s14, res14 = 1, f"[WARN] 薄利，创新投入困难 ({gm_pct:.1f}%)"
    else:
        s14, res14 = 3, "⏸ 数据稀疏(研发/毛利暂缺)"
    ev14 = EV_FUND

    # 3.4 行业天花板 (6分) —— 用市值的行业相对位置作为代理
    # 中小市值 + 高成长 = 更大空间；大市值 + 低成长 = 接近天花板
    if market_cap is not None:
        mc_yi = market_cap / 1e8  # 转为亿元
        if mc_yi < 100:
            s15, res15 = 10, f"🌱 小市值，成长空间大 ({mc_yi:.0f}亿)"
        elif mc_yi < 300:
            s15, res15 = 8, f"📈 中小市值，空间充足 ({mc_yi:.0f}亿)"
        elif mc_yi < 1000:
            s15, res15 = 6, f"🆗 中市值，仍有空间 ({mc_yi:.0f}亿)"
        elif mc_yi < 3000:
            s15, res15 = 4, f"📉 大市值，空间收窄 ({mc_yi:.0f}亿)"
        else:
            s15, res15 = 2, f"🏢 超大市值，接近天花板 ({mc_yi:.0f}亿)"
    else:
        s15, res15 = 3, "⏸ 数据稀疏(市值暂缺)"
    ev15 = EV_FUND

    # ── 加权汇总 (直接使用 VALUE_SCORING_WEIGHTS) ─────────
    weighted_total = (
        s1 / 10 * W["PE_HISTORY"]
        + s2 / 10 * W["PB"]
        + s3 / 10 * W["PEG"]
        + s4 / 10 * W["DIVIDEND"]
        + s5 / 10 * W["FCF_YIELD"]
        + s6 / 10 * W["ROE"]
        + s7 / 10 * W["ROIC"]
        + s8 / 10 * W["GROSS_MARGIN_STABILITY"]
        + s9 / 10 * W["FCF_NP_RATIO"]
        + s10 / 10 * W["DEBT_RATIO"]
        + s11 / 10 * W["OP_CASHFLOW"]
        + s12 / 10 * W["DEDUCTED_NP_3Y_CAGR"]
        + s13 / 10 * W["REVENUE_GROWTH"]
        + s14 / 10 * W["RD_RATIO"]
        + s15 / 10 * W["INDUSTRY_CEILING"]
    )

    # ── 构建报告 (按三大维度组织) ─────────────────────────
    dim_map = {
        "1.1 PE历史分位": ("估值维度", s1, res1, ev1),
        "1.2 PB市净率": ("", s2, res2, ev2),
        "1.3 PEG性价比": ("", s3, res3, ev3),
        "1.4 股息率": ("", s4, res4, ev4),
        "1.5 FCF收益率": ("", s5, res5, ev5),
        "2.1 ROE水平": ("质量维度", s6, res6, ev6),
        "2.2 ROIC回报": ("", s7, res7, ev7),
        "2.3 毛利率": ("", s8, res8, ev8),
        "2.4 FCF/净利比": ("", s9, res9, ev9),
        "2.5 财务健康": ("", s10, res10, ev10),
        "2.6 经营现金流": ("", s11, res11, ev11),
        "3.1 净利增速": ("成长维度", s12, res12, ev12),
        "3.2 营收增速": ("", s13, res13, ev13),
        "3.3 研发/创新": ("", s14, res14, ev14),
        "3.4 行业天花板": ("", s15, res15, ev15),
    }

    report = []
    for name, (dim, s, res, ev) in dim_map.items():
        report.append(
            {"dim": dim, "name": name, "res": res, "evidence": ev, "score": round(s, 1)}
        )

    return {
        "symbol": code,
        "name": yf_data.get("name", code),
        "sectors": ", ".join(stock_info.get("sectors", [])),
        "total_score": round(weighted_total),
        "report": report,
        "latest_price": current_price,
        # ── 原始指标 (供缓存/前端展示) ──
        "pe": pe_ttm if pe_ttm else 0,
        "pb": pb_val if pb_val else 0,
        "roe": round(roe * 100, 1) if roe else 0,
        "roic": round(roic * 100, 1) if roic else 0,
        "market_cap": market_cap if market_cap else 0,
        "gross_margin": round(gross_margin * 100, 1) if gross_margin else 0,
        "dividend_yield": round(dividend_yield * 100, 2) if dividend_yield else 0,
        "earnings_growth": round(earnings_growth * 100, 1) if earnings_growth else 0,
        "revenue_growth": round(revenue_growth * 100, 1) if revenue_growth else 0,
    }


def score_and_rank_stocks(
    passed_symbols: list, stock_infos: dict, passed_data: dict = None
) -> list:
    """
    对通过初筛的股票进行评分并排序。
    接口签名与旧版完全一致，保持向后兼容。
    """
    if passed_data is None:
        passed_data = {}
    results = []
    for code in passed_symbols:
        res = calculate_score(code, stock_infos.get(code, {}), passed_data.get(code))
        if res:
            results.append(res)
    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results
