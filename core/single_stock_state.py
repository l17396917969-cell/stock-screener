"""个股深度分析 — 状态定义"""

from typing import TypedDict


class SingleStockState(TypedDict, total=False):
    # ── 输入 ──
    user_input: str          # "000858" 或 "茅台"
    resolved_code: str       # 6 位代码
    resolved_name: str       # 股票名

    # ── 产业链 ──
    csic_sector: str         # CSIC 行业分类
    concept_boards: list[str]  # 概念板块
    chain_position: str      # 上游/中游/下游
    peers: list[dict]        # 同行业对比 [{code, name, pe, roe, score}]
    industry_context: str    # LLM 生成的产业链分析文本
    web_news: list[dict]     # Web 搜索最新新闻 [{title, url, snippet}]

    # ── 财务数据 ──
    price_data: dict         # yfinance 行情
    financials: dict         # 财务数据

    # ── 估值 ──
    pe: float
    pe_percentile: float
    pb: float
    peg: float
    dividend_yield: float

    # ── 质量 ──
    roe: float
    roic: float
    gross_margin: float
    debt_ratio: float
    fcf_yield: float

    # ── 成长 ──
    revenue_cagr_3y: float
    earnings_cagr_3y: float
    rd_ratio: float

    # ── AI ──
    ai_thesis: str
    ai_risks: list[str]

    # ── ValueClaw 巴菲特框架 ──
    buffett_data: dict        # 巴菲特数据驱动评分结果
    buffett_score: int        # 巴菲特总分 (0-100)
    buffett_breakdown: dict   # 6维评分明细
    owner_earnings: float     # Owner Earnings (所有者收益)
    de_ratio: float           # 债务/权益比

    # ── 输出 ──
    total_score: int
    score_breakdown: dict   # {valuation, quality, growth}
    recommendation: str     # 强烈推荐/推荐/中性/回避

    # ── 控制 ──
    error: str | None
    current_step: int
