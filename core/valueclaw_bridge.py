"""
ValueClaw 桥接模块 — 将 buffett-value 投资框架注入 stock-screener 的 LangGraph pipeline。

Adapted from: https://github.com/ericwang915/ValueClaw
Skill: invest-frameworks/buffett-value/buffett_analyze.py

Buffett 6 维评分 (0-100):
  1. Durable Moat (护城河)      — 20 分 | LLM 评估
  2. Consistent Earnings (盈利稳定) — 15 分 | 数据: 营收 5 年一致性
  3. Low Debt (低负债)           — 15 分 | 数据: 债务/权益比
  4. High ROE (高 ROE)          — 15 分 | 数据: 5 年平均 ROE
  5. Reasonable Valuation (合理估值) — 20 分 | 数据: PEG
  6. Management Quality (管理层)  — 15 分 | LLM 评估

桥接策略：
  - 数据驱动因子(2-5): 从 Baostock payload 提取计算
  - LLM 因子(1,6): 注入 ai_thesis prompt → DeepSeek 评估
  - Owner Earnings: netProfit + depreciation - capex
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 核心: 数据驱动部分 (4 因子, 满分 65)
# ═══════════════════════════════════════════


def compute_buffett_score(data: dict) -> dict:
    """基于 Baostock 数据计算巴菲特式评分 (数据驱动部分 65/100)。

    Args:
        data: Baostock payload dict, 包含以下关键字段:
            - roe (float): ROE (小数, 如 0.15 表示 15%)
            - pe_ttm (float): PE(TTM)
            - earnings_growth (float): 利润增速 (小数)
            - revenue_growth (float): 营收增速 (小数)
            - gross_margin (float): 毛利率 (小数)
            - fcf (float): 自由现金流
            - market_cap (float): 总市值
            - net_profit (float): 净利润

    Returns:
        {
            "score": int (0-65, 数据部分),
            "breakdown": {factor: score},
            "owner_earnings": float or None,
            "de_ratio": float or None,
            "fcf_yield": float or None,
            "peg": float or None,
        }
    """
    roe = _safe_val(data.get("roe", 0)) * 100       # 转百分比
    pe = _safe_val(data.get("pe_ttm"))
    earnings_growth = _safe_val(data.get("earnings_growth")) * 100
    fcf = _safe_val(data.get("fcf"))
    market_cap = _safe_val(data.get("market_cap"))

    # 估值
    peg = None
    if pe and earnings_growth and earnings_growth > 0:
        peg = pe / earnings_growth

    # 债务/权益比 (从 Baostock 的 profit.liabilityToAsset 推算, 如有)
    de_ratio = data.get("de_ratio")

    # FCF 收益率
    fcf_yield = None
    if fcf and market_cap and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100

    # ── 评分 ──
    bd = {}

    # 2. Consistent Earnings (营收增速稳定性 5yr) — 15 分
    rev_consistency = data.get("revenue_consistency")
    bd["consistent_earnings"] = (
        15 if rev_consistency and rev_consistency >= 75
        else 8 if rev_consistency and rev_consistency >= 50
        else 0
    )

    # 3. Low Debt — 15 分
    bd["low_debt"] = (
        15 if de_ratio is not None and de_ratio < 0.5
        else 10 if de_ratio is not None and de_ratio < 1.0
        else 5 if de_ratio is not None and de_ratio < 2.0
        else 0
    )

    # 4. High ROE — 15 分
    bd["high_roe"] = (
        15 if roe >= 20
        else 10 if roe >= 15
        else 5 if roe >= 10
        else 0
    )

    # 5. Reasonable Valuation (PEG) — 20 分
    bd["reasonable_valuation"] = (
        20 if peg is not None and peg < 1.0
        else 15 if peg is not None and peg < 1.5
        else 8 if peg is not None and peg < 2.5
        else 0
    )

    # 1/6 → LLM 评估 (不在这里打分)
    bd["durable_moat"] = 0
    bd["management_quality"] = 0

    total = sum(bd.values())

    return {
        "score": total,
        "breakdown": bd,
        "owner_earnings": data.get("owner_earnings"),
        "de_ratio": de_ratio,
        "fcf_yield": fcf_yield,
        "peg": peg,
    }


def compute_owner_earnings(net_profit, depreciation=0, capex=0) -> float | None:
    """巴菲特定义的 Owner Earnings = 净利润 + 折旧摊销 - 资本支出。

    Args:
        net_profit: 净利润
        depreciation: 折旧与摊销
        capex: 资本支出

    Returns:
        Owner Earnings (float) or None if net_profit is None
    """
    if net_profit is None:
        return None
    np_val = _safe_val(net_profit)
    dep_val = _safe_val(depreciation)
    capex_val = _safe_val(capex)
    return np_val + dep_val - abs(capex_val)


def compute_de_ratio(total_liability=0, total_equity=0) -> float | None:
    """债务/权益比 = 总负债 / 总权益。

    Args:
        total_liability: 总负债
        total_equity: 总权益 (净资产)

    Returns:
        D/E ratio or None if equity is 0
    """
    eq = _safe_val(total_equity)
    if eq and eq > 0:
        return _safe_val(total_liability) / eq
    return None


def compute_revenue_consistency(annual_revenues: list[float]) -> float:
    """计算营收 5 年一致性: 营收同比增长的年数占比。

    Args:
        annual_revenues: 按时间倒序的年度营收列表 (最近年在 [0])

    Returns:
        0-100, 营收同比增长的年数占比百分比
    """
    if len(annual_revenues) < 3:
        return 0
    ups = sum(1 for i in range(len(annual_revenues) - 1) if annual_revenues[i] >= annual_revenues[i + 1])
    return round(ups / (len(annual_revenues) - 1) * 100, 0)


def compute_fcf_yield(fcf: float, market_cap: float) -> float | None:
    """FCF 收益率 = 自由现金流 / 总市值 * 100%。

    Args:
        fcf: 自由现金流
        market_cap: 总市值

    Returns:
        FCF yield (%) or None
    """
    mc = _safe_val(market_cap)
    fc = _safe_val(fcf)
    if fc and mc and mc > 0:
        return round((fc / mc) * 100, 2)
    return None


# ═══════════════════════════════════════════
# 增强数据获取: 从 Baostock 拉取扩展字段
# ═══════════════════════════════════════════


def fetch_buffett_extensions(code: str) -> dict:
    """从 Baostock 拉取巴菲特分析所需的扩展财务数据。

    额外拉取: 负债合计、股东权益、折旧摊销、资本支出、多年营收历史。

    Args:
        code: 6 位 A 股代码

    Returns:
        {
            "de_ratio": float or None,
            "owner_earnings": float or None,
            "revenue_consistency": float or None,
            "annual_revenues": [float, ...],
        }
    """
    result = {
        "de_ratio": None,
        "owner_earnings": None,
        "revenue_consistency": None,
        "annual_revenues": [],
    }

    try:
        import baostock as bs
        from .data_fetcher import _to_bs_symbol, _resultset_to_dataframe

        bs_code = _to_bs_symbol(code)
        year = __import__("datetime").datetime.now().year

        # 拉取最新一期的资产负债表 (负债+权益)
        try:
            balance_rs = bs.query_balance_data(code=bs_code, year=year, quarter=1)
            balance_df = _resultset_to_dataframe(balance_rs)
            if not balance_df.empty:
                row = balance_df.iloc[0]
                # 字段可能是: totalLiab (总负债), totalEquity (归属母公司的股东权益)
                total_liability = _safe_val(row.get("totalLiab"))
                total_equity = _safe_val(
                    row.get("totalEquity")
                    or row.get("totalShareholderEquity")
                    or row.get("TSEQUI")
                )
                result["de_ratio"] = compute_de_ratio(total_liability, total_equity)
        except Exception as e:
            logger.debug(f"Balance sheet fetch failed for {code}: {e}")

        # 拉取最新一期的现金流量表 (折旧+资本支出)
        try:
            cf_rs = bs.query_cash_flow_data(code=bs_code, year=year, quarter=1)
            cf_df = _resultset_to_dataframe(cf_rs)
            if not cf_df.empty:
                row = cf_df.iloc[0]
                # 折旧摊销 (常见字段: DepreciationAmortization, DPA)
                depreciation = _safe_val(
                    row.get("DPA")
                    or row.get("depreciationAmortization")
                    or row.get("DAFixedAssetsOliAssets")
                )
                # 资本支出 (常见字段: CAPEX, invInFixedAssets)
                capex = _safe_val(
                    row.get("CAPEX")
                    or row.get("investFixedAssets")
                    or row.get("purchaseFixedAssets")
                )

                # 净利润 — 从利润表获取
                profit_rs = bs.query_profit_data(code=bs_code, year=year, quarter=1)
                profit_df = _resultset_to_dataframe(profit_rs)
                net_profit = None
                if not profit_df.empty:
                    net_profit = _safe_val(profit_df.iloc[0].get("netProfit"))

                result["owner_earnings"] = compute_owner_earnings(
                    net_profit, depreciation, capex
                )
        except Exception as e:
            logger.debug(f"Cash flow fetch failed for {code}: {e}")

        # 拉取多年营收历史 (用于营收一致性)
        try:
            annual_revenues = _fetch_annual_revenues(bs_code, year)
            if len(annual_revenues) >= 3:
                result["revenue_consistency"] = compute_revenue_consistency(annual_revenues)
                result["annual_revenues"] = annual_revenues
        except Exception as e:
            logger.debug(f"Annual revenue fetch failed for {code}: {e}")

    except ImportError:
        logger.warning("baostock not available for Buffett extensions")
    except Exception as e:
        logger.error(f"Buffett extensions fetch failed for {code}: {e}")

    return result


def _fetch_annual_revenues(bs_code: str, current_year: int, years_back: int = 5) -> list[float]:
    """从 Baostock 拉取年度营收数据 (按时间倒序)。

    Args:
        bs_code: Baostock 代码 (如 sh.600519)
        current_year: 当前年份
        years_back: 回溯年数

    Returns:
        [float, ...] 年度营收列表 (最近年在 index 0)
    """
    import baostock as bs
    from .data_fetcher import _resultset_to_dataframe

    revenues = []
    for y in range(current_year, current_year - years_back, -1):
        try:
            rs = bs.query_profit_data(code=bs_code, year=y, quarter=4)
            df = _resultset_to_dataframe(rs)
            if not df.empty:
                # 营收字段: operRev (营业收入)
                rev = _safe_val(
                    df.iloc[0].get("operRev")
                    or df.iloc[0].get("operIncome")
                    or df.iloc[0].get("revenue")
                )
                if rev and rev > 0:
                    revenues.append(rev)
        except Exception:
            continue

    return revenues


# ═══════════════════════════════════════════
# LLM 辅助: 构建巴菲特式研判 prompt
# ═══════════════════════════════════════════


def build_buffett_thesis_section(buffett_data: dict) -> str:
    """构建注入 ai_thesis prompt 的巴菲特框架部分。

    Args:
        buffett_data: compute_buffett_score() 的返回值

    Returns:
        Markdown 格式的提示文本
    """
    bd = buffett_data.get("breakdown", {})
    score = buffett_data.get("score", 0)

    lines = [
        "【巴菲特价值投资框架 — 数据驱动部分 65 分】",
        "",
        f"  总得分 (数据部分): {score}/65",
        "",
        "| 因子 | 满分 | 得分 | 说明 |",
        "|------|------|------|------|",
        f"| 盈利稳定性 | 15 | {bd.get('consistent_earnings', 0)} | 营收 5 年一致性 |",
        f"| 低负债 | 15 | {bd.get('low_debt', 0)} | D/E={buffett_data.get('de_ratio', 'N/A')} |",
        f"| 高 ROE | 15 | {bd.get('high_roe', 0)} | — |",
        f"| 合理估值 | 20 | {bd.get('reasonable_valuation', 0)} | PEG={buffett_data.get('peg', 'N/A')} |",
        f"| 护城河¹ | 20 | 待LLM评估 | — |",
        f"| 管理层¹ | 15 | 待LLM评估 | — |",
        "",
    ]

    oe = buffett_data.get("owner_earnings")
    if oe is not None:
        lines.append(f"  Owner Earnings (所有者收益): {_fmt_num(oe)}")
    fcf_y = buffett_data.get("fcf_yield")
    if fcf_y is not None:
        lines.append(f"  FCF 收益率: {fcf_y:.2f}%")

    lines.append("")
    lines.append("请基于以上数据 + 你对该公司护城河和管理层的了解, 完成 ¹ 标记的两项评分 (0-20 和 0-15), 并给出综合投资判断。")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════


def _safe_val(val) -> float:
    """安全提取数值, NaN/None/0→0.0。"""
    try:
        if val is None:
            return 0.0
        result = float(val)
        import math
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except (TypeError, ValueError):
        return 0.0


def _fmt_num(n) -> str:
    """格式化金额: 亿/万/元。"""
    if n is None:
        return "N/A"
    abs_n = abs(n)
    if abs_n >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if abs_n >= 1e4:
        return f"{n / 1e4:.2f}万"
    return f"{n:,.0f}元"
