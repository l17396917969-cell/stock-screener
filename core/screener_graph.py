"""LangGraph 选股 Agent — 4 步状态图"""

import logging
import traceback

from langgraph.graph import StateGraph, END

from .screener_state import ScreenerState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# Node: Step 1 — 宏观分析 (DeepSeek)
# ═══════════════════════════════════════════════
def node_macro(state: ScreenerState) -> dict:
    """调用 DeepSeek 进行宏观定调，输出推荐板块。"""
    try:
        from .sector_analyzer import analyze_macro_sectors_with_ai

        ai_analysis = analyze_macro_sectors_with_ai()
        sectors = ai_analysis.get("sectors", [])

        if not sectors:
            return {"error": "AI 未能推导出有效板块", "current_step": 1}

        return {
            "macro_reasoning": ai_analysis.get("reasoning", ""),
            "sectors": sectors,
            "ai_result": ai_analysis,
            "current_step": 1,
        }

    except Exception as e:
        logger.error(f"node_macro 失败: {traceback.format_exc()}")
        return {"error": f"宏观分析失败: {e}", "current_step": 1}


# ═══════════════════════════════════════════════
# Node: Step 2 — 成分股提取
# ═══════════════════════════════════════════════
def node_fetch(state: ScreenerState) -> dict:
    """从 AI 分析结果或数据源提取板块成分股。"""
    sectors = state.get("sectors", [])
    ai_result = state.get("ai_result", {})

    if not sectors:
        return {"error": "无板块可提取成分股", "current_step": 2}

    try:
        from .ai_fallback import get_stocks_from_sectors

        stocks, infos = get_stocks_from_sectors(sectors, ai_result)

        if not stocks:
            return {
                "error": f"板块 {sectors} 下未找到成分股",
                "current_step": 2,
            }

        return {
            "candidate_stocks": stocks,
            "stock_infos": infos,
            "current_step": 2,
        }

    except Exception as e:
        logger.error(f"node_fetch 失败: {traceback.format_exc()}")
        return {"error": f"成分股提取失败: {e}", "current_step": 2}


# ═══════════════════════════════════════════════
# Node: Step 3 — 量化评分 (逐只)
# ═══════════════════════════════════════════════
def node_score(state: ScreenerState) -> dict:
    """对候选股逐只做深筛 + 评分。"""
    candidates = state.get("candidate_stocks", [])
    stock_infos = state.get("stock_infos", {})

    if not candidates:
        return {"error": "无候选股可评分", "current_step": 3}

    try:
        from .data_fetcher import get_index_data
        from .stock_screener import deep_screen_stock
        from .scorer import calculate_score

        index_hist = get_index_data()
        scored = []

        for code in candidates:
            info = stock_infos.get(code, {})
            name = info.get("name", code)

            passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)
            score_report = calculate_score(code, info, yf_data) if yf_data else None

            scored.append({
                "code": code,
                "name": name,
                "passed": passed,
                "reason": reason,
                "pe": score_report.get("pe", 0) if score_report else 0,
                "roe": score_report.get("roe", 0) if score_report else 0,
                "mcap": score_report.get("market_cap", 0) if score_report else 0,
                "score": score_report.get("total_score", 0) if score_report else 0,
                "report": score_report,
            })

        return {
            "scored_stocks": scored,
            "batch_progress": {"total": len(candidates), "current": len(candidates)},
            "current_step": 3,
        }

    except Exception as e:
        logger.error(f"node_score 失败: {traceback.format_exc()}")
        return {"error": f"评分失败: {e}", "current_step": 3}


# ═══════════════════════════════════════════════
# Node: Step 4 — 排序 & 汇总
# ═══════════════════════════════════════════════
def node_rank(state: ScreenerState) -> dict:
    """按评分排序，输出 Top N 精选。"""
    scored = state.get("scored_stocks", [])

    if not scored:
        return {"error": "无评分数据可排序", "current_step": 4}

    try:
        passed = [s for s in scored if s["passed"]]
        failed = [s for s in scored if not s["passed"]]
        passed.sort(key=lambda x: x["score"], reverse=True)

        top_n = min(10, len(passed))

        return {
            "top_picks": passed[:top_n],
            "summary": (
                f"从 {len(scored)} 只候选股中筛选出 {len(passed)} 只达标，"
                f"精选 Top {top_n}"
            ),
            "current_step": 4,
        }

    except Exception as e:
        logger.error(f"node_rank 失败: {traceback.format_exc()}")
        return {"error": f"排序失败: {e}", "current_step": 4}


# ═══════════════════════════════════════════════
# 路由: 遇到错误直接跳到 END
# ═══════════════════════════════════════════════
def _has_error(state: ScreenerState) -> str:
    if state.get("error"):
        return "end"
    return "continue"


# ═══════════════════════════════════════════════
# 构建图
# ═══════════════════════════════════════════════
def build_graph() -> StateGraph:
    builder = StateGraph(ScreenerState)

    builder.add_node("macro", node_macro)
    builder.add_node("fetch", node_fetch)
    builder.add_node("score", node_score)
    builder.add_node("rank", node_rank)

    builder.set_entry_point("macro")

    # 每步后检查 error，有错就停
    builder.add_conditional_edges("macro", _has_error, {"end": END, "continue": "fetch"})
    builder.add_conditional_edges("fetch", _has_error, {"end": END, "continue": "score"})
    builder.add_conditional_edges("score", _has_error, {"end": END, "continue": "rank"})
    builder.add_edge("rank", END)

    return builder
