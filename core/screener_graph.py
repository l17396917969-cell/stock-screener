"""LangGraph 选股 Agent — 2 步状态图 (宏观 -> 查 SQLite 缓存)

node_macro: DeepSeek 宏观定调
node_lookup: 从 scores.db 查分 -> 排序输出
"""

import logging, traceback
from langgraph.graph import StateGraph, END
from .screener_state import ScreenerState
from .score_store import get_by_sector, get_all

logger = logging.getLogger(__name__)

def node_macro(state: ScreenerState) -> dict:
    try:
        from .sector_analyzer import analyze_macro_sectors_with_ai
        ai_analysis = analyze_macro_sectors_with_ai()
        sectors = ai_analysis.get("sectors", [])
        if not sectors:
            return {"error": "AI 未能推导出有效板块", "current_step": 1}
        return {"macro_reasoning": ai_analysis.get("reasoning", ""), "sectors": sectors, "ai_result": ai_analysis, "current_step": 1}
    except Exception as e:
        logger.error(f"node_macro failed: {traceback.format_exc()}")
        return {"error": f"宏观分析失败: {e}", "current_step": 1}

def node_lookup(state: ScreenerState) -> dict:
    sectors = state.get("sectors", [])
    if not sectors:
        return {"error": "无板块可查询", "current_step": 2}
    try:
        matched: dict[str, dict] = {}
        for sector in sectors:
            for r in get_by_sector(sector, limit=50):
                code = r["code"]
                if code not in matched or r.get("score",0) > matched[code].get("score",0):
                    matched[code] = r
        if not matched:
            return {"top_picks": [], "summary": f"缓存中未找到板块 {sectors} 的评分数据", "current_step": 2}
        all_matched = list(matched.values())
        passed = [m for m in all_matched if m.get("passed")]
        passed.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_n = min(10, len(passed))
        return {"top_picks": passed[:top_n], "candidate_stocks": [m["code"] for m in all_matched], "summary": f"从缓存 {len(all_matched)} 只相关股票中精选 Top {top_n}", "current_step": 2}
    except Exception as e:
        logger.error(f"node_lookup failed: {traceback.format_exc()}")
        return {"error": f"缓存查询失败: {e}", "current_step": 2}

def _has_error(state: ScreenerState) -> str:
    return "end" if state.get("error") else "continue"

def build_graph() -> StateGraph:
    builder = StateGraph(ScreenerState)
    builder.add_node("macro", node_macro)
    builder.add_node("lookup", node_lookup)
    builder.set_entry_point("macro")
    builder.add_conditional_edges("macro", _has_error, {"end": END, "continue": "lookup"})
    builder.add_edge("lookup", END)
    return builder
