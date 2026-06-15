"""LangGraph 选股 Agent — 2 步状态图 (宏观 → 查缓存)

node_macro: DeepSeek 宏观定调
node_lookup: 从 scored_stocks.json 查分 → 排序输出
"""

import json
import logging
import os
import traceback

from langgraph.graph import StateGraph, END

from .screener_state import ScreenerState

logger = logging.getLogger(__name__)

SHARED_DIR = os.environ.get("STOCK_SHARED_DIR", "/opt/stock-screener-shared")
SCORED_CACHE = os.path.join(SHARED_DIR, "scored_stocks.json")


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
# Node: Step 2 — 查缓存 + 排序输出
# ═══════════════════════════════════════════════
def node_lookup(state: ScreenerState) -> dict:
    """从 scored_stocks.json 查询板块成分股评分，排序输出 Top 10。"""
    sectors = state.get("sectors", [])
    if not sectors:
        return {"error": "无板块可查询", "current_step": 2}

    try:
        # 加载缓存
        if not os.path.exists(SCORED_CACHE):
            return {"error": "评分缓存尚未生成，请等待每日 Cron 或先触发一次评分", "current_step": 2}

        with open(SCORED_CACHE) as f:
            all_scores = json.load(f)

        # 按板块筛选
        matched = []
        for code, info in all_scores.items():
            stock_sector = info.get("sector", "")
            for s in sectors:
                if s in stock_sector or stock_sector in s:
                    info["code"] = code
                    matched.append(info)
                    break

        if not matched:
            return {
                "top_picks": [],
                "summary": f"缓存中未找到板块 {sectors} 的评分数据",
                "current_step": 2,
            }

        # 排序：passed 优先，score 降序
        passed = [m for m in matched if m.get("passed")]
        passed.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_n = min(10, len(passed))

        return {
            "top_picks": passed[:top_n],
            "candidate_stocks": [m["code"] for m in matched],
            "summary": f"从缓存 {len(matched)} 只相关股票中精选 Top {top_n}",
            "current_step": 2,
        }

    except Exception as e:
        logger.error(f"node_lookup 失败: {traceback.format_exc()}")
        return {"error": f"缓存查询失败: {e}", "current_step": 2}


# ═══════════════════════════════════════════════
# 路由: 遇到错误直接跳到 END
# ═══════════════════════════════════════════════
def _has_error(state: ScreenerState) -> str:
    if state.get("error"):
        return "end"
    return "continue"


# ═══════════════════════════════════════════════
# 构建图 (2 节点: macro → lookup)
# ═══════════════════════════════════════════════
def build_graph() -> StateGraph:
    builder = StateGraph(ScreenerState)

    builder.add_node("macro", node_macro)
    builder.add_node("lookup", node_lookup)

    builder.set_entry_point("macro")
    builder.add_conditional_edges("macro", _has_error, {"end": END, "continue": "lookup"})
    builder.add_edge("lookup", END)

    return builder
