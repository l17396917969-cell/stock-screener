"""LangGraph 选股 Agent 状态定义"""

from typing import TypedDict


class ScreenerState(TypedDict, total=False):
    # ── 用户输入 ──
    user_query: str
    user_id: int

    # ── Step 1: 宏观分析产出 ──
    macro_reasoning: str
    sectors: list[str]
    ai_result: dict  # 完整 AI 分析结果，传给 Step 2

    # ── Step 2: 成分股提取产出 ──
    candidate_stocks: list[str]
    stock_infos: dict[str, dict]  # {code: {name, sectors[], ...}}

    # ── Step 3: 量化评分产出 (渐进式) ──
    scored_stocks: list[dict]
    batch_progress: dict  # {total, current}

    # ── Step 4: 排序输出 ──
    top_picks: list[dict]
    summary: str

    # ── 控制 ──
    error: str | None
    current_step: int
    is_analyzing: bool
