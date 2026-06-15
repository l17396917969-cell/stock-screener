"""个股深度分析 LangGraph — 7 节点

resolve → industry_context → fetch_data → valuation → quality → growth → ai_thesis → END
"""

import json
import logging
import os
import traceback

from langgraph.graph import StateGraph, END

from .single_stock_state import SingleStockState

logger = logging.getLogger(__name__)

SHARED_DIR = os.environ.get("STOCK_SHARED_DIR", "/opt/stock-screener-shared")
SCORED_CACHE = os.path.join(SHARED_DIR, "scored_stocks.json")
BOARD_CACHE = os.path.join(SHARED_DIR, "board_stocks.json")


# ═══════════════════════════════════════
# Node 1: 解析用户输入
# ═══════════════════════════════════════
def node_resolve(state: SingleStockState) -> dict:
    """将 '000858' 或 '茅台' 解析为标准代码+名称。"""
    user_input = state.get("user_input", "").strip()

    # 尝试匹配 6 位代码
    import re
    m = re.search(r"\b(\d{6})\b", user_input)
    if m:
        code = m.group(1)
        name = _lookup_name(code)
        if name:
            return {"resolved_code": code, "resolved_name": name, "current_step": 1}
        return {"error": f"未找到代码 {code} 对应的股票", "current_step": 1}

    # 尝试模糊匹配名称
    name = user_input
    code = _lookup_code(name)
    if code:
        return {"resolved_code": code, "resolved_name": name, "current_step": 1}

    return {"error": f"无法识别股票: {user_input}", "current_step": 1}


def _lookup_name(code: str) -> str:
    """从缓存查代码→名称。"""
    try:
        with open(SCORED_CACHE) as f:
            scores = json.load(f)
        if code in scores:
            return scores[code].get("name", "")
    except Exception:
        pass

    try:
        with open(BOARD_CACHE) as f:
            boards = json.load(f)
        for sector, stocks in boards.items():
            for s in stocks:
                if str(s.get("code", "")).zfill(6) == code:
                    return str(s.get("name", ""))
    except Exception:
        pass

    return ""


def _lookup_code(name: str) -> str:
    """从缓存查名称→代码 (模糊)。"""
    try:
        with open(SCORED_CACHE) as f:
            scores = json.load(f)
        for code, info in scores.items():
            if name in info.get("name", ""):
                return code
    except Exception:
        pass

    try:
        with open(BOARD_CACHE) as f:
            boards = json.load(f)
        for sector, stocks in boards.items():
            for s in stocks:
                if name in str(s.get("name", "")):
                    return str(s.get("code", "")).zfill(6)
    except Exception:
        pass

    return ""


# ═══════════════════════════════════════
# Node 2: 产业链上下文
# ═══════════════════════════════════════
def node_industry_context(state: SingleStockState) -> dict:
    """获取 CSIC 行业分类、概念板块、同行对比。"""
    code = state.get("resolved_code", "")

    try:
        # CSIC 行业
        csic = _get_csic_sector(code)

        # 概念板块
        concepts = _get_concept_boards(code)

        # 同行对比
        peers = _get_peers(code, csic)

        return {
            "csic_sector": csic,
            "concept_boards": concepts,
            "peers": peers,
            "current_step": 2,
        }
    except Exception as e:
        logger.error(f"industry_context 失败: {e}")
        return {"error": f"产业链分析失败: {e}", "current_step": 2}


def _get_csic_sector(code: str) -> str:
    """查 CSIC 行业分类。"""
    try:
        with open(BOARD_CACHE) as f:
            boards = json.load(f)
        for sector, stocks in boards.items():
            for s in stocks:
                if str(s.get("code", "")).zfill(6) == code:
                    return sector
    except Exception:
        pass
    return "未知"


def _get_concept_boards(code: str) -> list[str]:
    """查概念板块 (从 board_stocks.json 反向索引)。"""
    concepts = []
    try:
        with open(BOARD_CACHE) as f:
            boards = json.load(f)
        for sector, stocks in boards.items():
            for s in stocks:
                if str(s.get("code", "")).zfill(6) == code:
                    concepts.append(sector)
    except Exception:
        pass
    return concepts[:5]  # 最多 5 个


def _get_peers(code: str, sector: str) -> list[dict]:
    """获取同行业评分对比。"""
    peers = []
    try:
        with open(SCORED_CACHE) as f:
            scores = json.load(f)
        for c, info in scores.items():
            if info.get("sector") == sector and c != code:
                peers.append({
                    "code": c,
                    "name": info.get("name", ""),
                    "score": info.get("score", 0),
                    "pe": info.get("pe", 0),
                    "roe": info.get("roe", 0),
                })
        peers.sort(key=lambda x: x["score"], reverse=True)
    except Exception:
        pass
    return peers[:5]


# ═══════════════════════════════════════
# Node 3: 拉取财务数据
# ═══════════════════════════════════════
def node_fetch_data(state: SingleStockState) -> dict:
    """yfinance 拉 5 年行情 + 财务。"""
    code = state.get("resolved_code", "")
    try:
        from .stock_screener import deep_screen_stock
        from .data_fetcher import get_index_data

        index_hist = get_index_data()
        passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)

        if yf_data is None:
            return {"error": f"无法获取 {code} 数据: {reason}", "current_step": 3}

        return {"price_data": yf_data, "current_step": 3}

    except Exception as e:
        logger.error(f"fetch_data 失败: {traceback.format_exc()}")
        return {"error": f"数据获取失败: {e}", "current_step": 3}


# ═══════════════════════════════════════
# Node 4-6: 估值 / 质量 / 成长
# ═══════════════════════════════════════
def node_valuation(state: SingleStockState) -> dict:
    """估值分析。"""
    try:
        from .scorer import calculate_score
        code = state.get("resolved_code", "")
        name = state.get("resolved_name", "")
        yf_data = state.get("price_data", {})

        report = calculate_score(code, {"name": name, "code": code}, yf_data)
        if not report:
            return {"error": "评分计算失败", "current_step": 4}

        return {
            "pe": report.get("pe", 0),
            "pb": report.get("pb", 0),
            "current_step": 4,
        }
    except Exception as e:
        return {"error": f"估值分析失败: {e}", "current_step": 4}


def node_quality(state: SingleStockState) -> dict:
    """质量分析。"""
    yf_data = state.get("price_data", {})
    try:
        info = yf_data.get("info", {}) if isinstance(yf_data, dict) else {}
        return {
            "roe": float(info.get("returnOnEquity", 0) or 0) * 100,
            "gross_margin": float(info.get("grossMargins", 0) or 0) * 100,
            "debt_ratio": float(info.get("debtToEquity", 0) or 0),
            "current_step": 5,
        }
    except Exception:
        return {"roe": 0, "gross_margin": 0, "debt_ratio": 0, "current_step": 5}


def node_growth(state: SingleStockState) -> dict:
    """成长分析。"""
    try:
        yf_data = state.get("price_data", {})
        info = yf_data.get("info", {}) if isinstance(yf_data, dict) else {}
        return {
            "revenue_cagr_3y": float(info.get("revenueGrowth", 0) or 0) * 100,
            "earnings_cagr_3y": float(info.get("earningsGrowth", 0) or 0) * 100,
            "current_step": 6,
        }
    except Exception:
        return {"revenue_cagr_3y": 0, "earnings_cagr_3y": 0, "current_step": 6}


# ═══════════════════════════════════════
# Node 7: AI 投资论点 + 综合评分
# ═══════════════════════════════════════
def node_ai_thesis(state: SingleStockState) -> dict:
    """DeepSeek 综合研判 + 评分汇总。"""
    try:
        from .deepseek_analyzer import _call_deepseek
        from config import SCRENNER_CONFIG

        # 计算综合评分
        pe_val = _score_pe(state.get("pe", 0))
        roe_val = _score_roe(state.get("roe", 0))
        growth_val = _score_growth(state.get("earnings_cagr_3y", 0))
        total = pe_val + roe_val + growth_val

        rec = "强烈推荐" if total >= 80 else "推荐" if total >= 60 else "中性" if total >= 40 else "回避"

        # 构建 DeepSeek prompt
        prompt = _build_thesis_prompt(state)
        ds_key = SCRENNER_CONFIG.get("DS_API_KEY", "")
        ds_model = SCRENNER_CONFIG.get("DS_MODEL", "deepseek-chat")

        ai_text = ""
        if ds_key:
            try:
                ai_text = _call_deepseek(ds_key, ds_model, prompt)
            except Exception as e:
                logger.warning(f"DeepSeek call failed: {e}")
                ai_text = "AI 分析暂时不可用"

        return {
            "total_score": total,
            "score_breakdown": {
                "估值": pe_val,
                "质量": roe_val,
                "成长": growth_val,
            },
            "recommendation": rec,
            "ai_thesis": ai_text,
            "current_step": 7,
        }
    except Exception as e:
        logger.error(f"ai_thesis 失败: {traceback.format_exc()}")
        return {"error": f"AI 分析失败: {e}", "current_step": 7}


def _score_pe(pe: float) -> int:
    if pe <= 0: return 5
    if pe < 10: return 28
    if pe < 15: return 25
    if pe < 20: return 20
    if pe < 30: return 15
    if pe < 50: return 10
    return 5


def _score_roe(roe: float) -> int:
    if roe >= 25: return 38
    if roe >= 20: return 34
    if roe >= 15: return 28
    if roe >= 10: return 20
    if roe >= 5: return 12
    return 5


def _score_growth(growth: float) -> int:
    if growth >= 30: return 28
    if growth >= 20: return 24
    if growth >= 15: return 20
    if growth >= 10: return 15
    if growth >= 5: return 10
    return 5


def _build_thesis_prompt(state: SingleStockState) -> str:
    return f"""你是一位价值投资分析师。请基于以下信息对 {state.get("resolved_name", "")}({state.get("resolved_code", "")}) 做研判。

【产业链】
行业: {state.get("csic_sector", "未知")}
概念板块: {", ".join(state.get("concept_boards", []))}

【估值】
PE: {state.get("pe", 0):.1f}
PB: {state.get("pb", 0):.1f}

【质量】
ROE: {state.get("roe", 0):.1f}%
毛利率: {state.get("gross_margin", 0):.1f}%
负债率: {state.get("debt_ratio", 0):.1f}

【成长】
营收 CAGR(3y): {state.get("revenue_cagr_3y", 0):.1f}%
利润 CAGR(3y): {state.get("earnings_cagr_3y", 0):.1f}%

【同行对比】
{_format_peers(state.get("peers", []))}

请用中文，200 字以内，从价值投资角度分析：
1. 产业链地位与护城河
2. 当前估值是否合理
3. 主要风险
4. 投资建议"""


def _format_peers(peers: list[dict]) -> str:
    if not peers:
        return "无同行数据"
    lines = []
    for p in peers:
        lines.append(f"{p['name']}({p['code']}): PE {p.get('pe',0):.1f} ROE {p.get('roe',0):.1f}% 评分 {p.get('score',0)}")
    return "\n".join(lines)


# ═══════════════════════════════════════
# 构建图
# ═══════════════════════════════════════
def _has_error(state: SingleStockState) -> str:
    if state.get("error"):
        return "end"
    return "continue"


def build_single_stock_graph() -> StateGraph:
    builder = StateGraph(SingleStockState)

    builder.add_node("resolve", node_resolve)
    builder.add_node("industry_context", node_industry_context)
    builder.add_node("fetch_data", node_fetch_data)
    builder.add_node("valuation", node_valuation)
    builder.add_node("quality", node_quality)
    builder.add_node("growth", node_growth)
    builder.add_node("ai_thesis", node_ai_thesis)

    builder.set_entry_point("resolve")

    builder.add_conditional_edges("resolve", _has_error, {"end": END, "continue": "industry_context"})
    builder.add_conditional_edges("industry_context", _has_error, {"end": END, "continue": "fetch_data"})
    builder.add_conditional_edges("fetch_data", _has_error, {"end": END, "continue": "valuation"})
    builder.add_edge("valuation", "quality")
    builder.add_edge("quality", "growth")
    builder.add_edge("growth", "ai_thesis")
    builder.add_edge("ai_thesis", END)

    return builder
