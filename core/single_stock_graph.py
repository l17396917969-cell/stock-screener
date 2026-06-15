"""个股深度分析 LangGraph — 7 节点

resolve → industry_context → fetch_data → valuation → quality → growth → ai_thesis → END
v2: 产业链从 score_store(SQLite) + board_stocks.json 读取; 去掉 yf_data.info 依赖
"""

import json
import logging
import os
import traceback

from langgraph.graph import StateGraph, END

from .single_stock_state import SingleStockState

logger = logging.getLogger(__name__)

SHARED_DIR = os.environ.get("STOCK_SHARED_DIR", "/opt/stock-screener-shared")
BOARD_CACHE = os.path.join(SHARED_DIR, "board_stocks.json")


# ═══════════════════════════════════════
# Node 1: 解析用户输入 (本地缓存 → LLM 兜底)
# ═══════════════════════════════════════
def node_resolve(state: SingleStockState) -> dict:
    """将 '000858' 或 '茅台' 或 '分析一下立讯精密' 解析为标准代码+名称。

    三级解析:
      1. 6位代码匹配 → 本地查名
      2. 名称本地查 (score_store → board_stocks)
      3. DeepSeek LLM 兜底 → 从自然语言提取股票名, 映射到代码
    """
    user_input = state.get("user_input", "").strip()
    raw_input = user_input  # 保留原始输入给 LLM

    # ── 去掉常见前缀，提取核心查询 ──
    import re
    cleaned = re.sub(r'^(分析一下|分析|看看|查一下|怎么看|帮我|帮我分析|看一下)\s*', '', user_input).strip()

    # ── 第 1 级: 6 位代码 ──
    m = re.search(r"\b(\d{6})\b", cleaned)
    if m:
        code = m.group(1)
        name = _lookup_name(code)
        if name:
            return {"resolved_code": code, "resolved_name": name, "current_step": 1}
        # 本地无名但代码存在 → 用代码直接拉数据(后续 Baostock 会补名)
        return {"resolved_code": code, "resolved_name": code, "current_step": 1}

    # ── 第 2 级: 本地查名称 ──
    code = _lookup_code(cleaned)
    if code:
        return {"resolved_code": code, "resolved_name": cleaned, "current_step": 1}

    # ── 第 3 级: DeepSeek LLM 兜底 ──
    result = _llm_resolve_stock(cleaned, raw_input)
    if result:
        return {"resolved_code": result[0], "resolved_name": result[1], "current_step": 1}

    return {"error": f"无法识别股票: {cleaned}，请直接输入 6 位代码", "current_step": 1}


def _llm_resolve_stock(query: str, raw_input: str = "") -> tuple[str, str] | None:
    """DeepSeek LLM 把自然语言股票名解析为 (代码, 名称)。

    示例输入: "立讯精密" / "分析一下立讯精密"
    示例输出: ("002475", "立讯精密")
    """
    try:
        from .deepseek_analyzer import _call_deepseek
        from config import SCRENNER_CONFIG
        import os

        ds_key = SCRENNER_CONFIG.get("DS_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not ds_key:
            logger.warning("LLM resolve: no DeepSeek API key")
            return None

        prompt = f"""请从以下用户输入中提取 A 股股票名称，并给出其 6 位交易所代码。

用户输入: {raw_input or query}
查询关键词: {query}

请严格按照以下 JSON 格式返回，不要有任何其他文字:
{{"code": "6位数字代码", "name": "股票中文名"}}

如果无法确定是哪只股票，返回:
{{"code": "", "name": ""}}

注意:
- A 股代码是 6 位数字 (上海 60xxxx, 深圳 00xxxx/30xxxx)
- 如果用户输入包含"下"字但没有具体股票名，返回空
- 只返回一只最匹配的股票"""

        response = _call_deepseek(ds_key, "deepseek-chat", prompt, temperature=0.0, timeout=10)
        logger.info(f"LLM resolve response: {response[:200]}")

        # 从响应中提取 JSON
        import re as _re
        match = _re.search(r'\{[^}]+\}', response)
        if match:
            data = json.loads(match.group())
            code = str(data.get("code", "")).strip()
            name = str(data.get("name", "")).strip()
            if code and len(code) == 6 and code.isdigit():
                # 验证: 用 board_stocks.json 确认代码→名称匹配
                cached_name = _lookup_name(code)
                if cached_name:
                    return code, cached_name
                # 本地缓存没有也接受 (Baostock 会实时查)
                return code, name or code

    except Exception as e:
        logger.error(f"LLM resolve failed: {e}")

    return None


def _lookup_name(code: str) -> str:
    """查代码→名称: 先 score_store(SQLite) → board_stocks.json。"""
    try:
        from .score_store import get_by_code
        row = get_by_code(code)
        if row and row.get("name"):
            return row["name"]
    except Exception:
        pass
    try:
        with open(BOARD_CACHE) as f:
            for stocks in json.load(f).values():
                for s in stocks:
                    if str(s.get("code", "")).zfill(6) == code:
                        return str(s.get("name", ""))
    except Exception:
        pass
    return ""


def _lookup_code(name: str) -> str:
    """查名称→代码: 先 score_store(SQLite) → board_stocks.json。"""
    try:
        from .score_store import get_all
        rows, _ = get_all(search=name, limit=5)
        if rows:
            return rows[0]["code"]
    except Exception:
        pass
    try:
        with open(BOARD_CACHE) as f:
            for stocks in json.load(f).values():
                for s in stocks:
                    if name in str(s.get("name", "")):
                        return str(s.get("code", "")).zfill(6)
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════
# Node 2: 产业链上下文 (本地缓存 + LLM 补全)
# ═══════════════════════════════════════
def node_industry_context(state: SingleStockState) -> dict:
    """从 board_stocks.json 获取 CSIC 行业 + 概念板块; 从 score_store 获取同行评分。
    本地数据稀疏时调用 DeepSeek LLM 补全产业链上下文。
    """
    code = state.get("resolved_code", "")
    name = state.get("resolved_name", "")
    try:
        csic = _get_csic_sector(code)
        concepts = _get_concept_boards(code)
        peers = _get_peers_from_store(code, csic)

        # 如果同行数据为空或概念板块少于 2 个，用 LLM 补全
        industry_context = ""
        if not peers or len(concepts) < 2:
            industry_context = _llm_industry_context(code, name, csic, concepts, peers)

        return {
            "csic_sector": csic,
            "concept_boards": concepts,
            "peers": peers,
            "industry_context": industry_context,  # LLM 生成的产业链上下文
            "current_step": 2,
        }
    except Exception as e:
        logger.error(f"industry_context failed: {e}")
        return {"error": f"产业链分析失败: {e}", "current_step": 2}


def _llm_industry_context(code: str, name: str, csic: str, concepts: list[str], peers: list[dict]) -> str:
    """LLM 补全产业链上下文: 上下游、主要竞争对手、行业动态。"""
    try:
        from .deepseek_analyzer import _call_deepseek
        from config import SCRENNER_CONFIG
        import os

        ds_key = SCRENNER_CONFIG.get("DS_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not ds_key:
            return ""

        peer_str = "\n".join(f"{p['name']}({p['code']}) 评分{p['score']}" for p in peers) if peers else "暂无本地评分数据"

        prompt = f"""请分析 A 股股票 {name}({code}) 的产业链地位。

【基本信息】
行业分类: {csic}
概念板块: {', '.join(concepts) if concepts else '无本地数据'}
本地评分同行: {peer_str}

请用中文，150 字以内回答：
1. 产业链位置: 这家公司在产业链中的位置 (上游/中游/下游)，主要产品/服务
2. 核心竞争对手: 列出 3-5 家最直接的 A 股竞争对手 (含代码)
3. 近期行业动态: 该行业近期 1-2 个关键趋势或事件

直接输出分析内容，不需要 JSON 格式。"""

        response = _call_deepseek(ds_key, "deepseek-chat", prompt, temperature=0.3, timeout=15)
        return response.strip() if response else ""

    except Exception as e:
        logger.warning(f"LLM industry context failed: {e}")
        return ""


def _get_csic_sector(code: str) -> str:
    """查 CSIC 行业分类 (board_stocks.json)。"""
    try:
        with open(BOARD_CACHE) as f:
            for sector, stocks in json.load(f).items():
                for s in stocks:
                    if str(s.get("code", "")).zfill(6) == code:
                        return sector
    except Exception:
        pass
    return "未知"


def _get_concept_boards(code: str) -> list[str]:
    """反向索引: 股票属于哪些板块。"""
    concepts = []
    try:
        with open(BOARD_CACHE) as f:
            for sector, stocks in json.load(f).items():
                for s in stocks:
                    if str(s.get("code", "")).zfill(6) == code:
                        concepts.append(sector)
    except Exception:
        pass
    return concepts[:5]


def _get_peers_from_store(code: str, sector: str) -> list[dict]:
    """从 score_store (SQLite) 获取同行业评分对比。"""
    try:
        from .score_store import get_by_sector
        rows = get_by_sector(sector, limit=10)
        peers = []
        for r in rows:
            if r["code"] != code:
                peers.append({"code": r["code"], "name": r["name"], "score": r["score"], "pe": r["pe"], "roe": r["roe"]})
        peers.sort(key=lambda x: x["score"], reverse=True)
        return peers[:5]
    except Exception:
        return []


# ═══════════════════════════════════════
# Node 3: 拉取财务数据 (Baostock 优先)
# ═══════════════════════════════════════
def node_fetch_data(state: SingleStockState) -> dict:
    """Baostock/yfinance 拉行情+财务。"""
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
        logger.error(f"fetch_data failed: {traceback.format_exc()}")
        return {"error": f"数据获取失败: {e}", "current_step": 3}


# ═══════════════════════════════════════
# Node 4: 估值 (复用 calculate_score 取 pe/pb)
# ═══════════════════════════════════════
def node_valuation(state: SingleStockState) -> dict:
    """估值分析 — 从 calculate_score 取 pe/pb。"""
    try:
        from .scorer import calculate_score
        code = state.get("resolved_code", "")
        name = state.get("resolved_name", "")
        yf_data = state.get("price_data", {})
        report = calculate_score(code, {"name": name, "code": code}, yf_data)
        if not report:
            return {"error": "评分计算失败", "current_step": 4}
        return {"pe": report.get("pe", 0), "pb": report.get("pb", 0), "current_step": 4}
    except Exception as e:
        return {"error": f"估值分析失败: {e}", "current_step": 4}


# ═══════════════════════════════════════
# Node 5: 质量 (Baostock 数据在 price_data 顶层, 不用 .info)
# ═══════════════════════════════════════
def node_quality(state: SingleStockState) -> dict:
    """质量分析 — 从 Baostock payload 顶层取 roe/gross_margin。"""
    yf_data = state.get("price_data", {}) or {}
    try:
        roe = float(yf_data.get("roe", 0) or 0) * 100  # Baostock 存小数，转%
        gross_margin = float(yf_data.get("gross_margin", 0) or 0) * 100
        return {"roe": roe, "gross_margin": gross_margin, "current_step": 5}
    except Exception:
        return {"roe": 0, "gross_margin": 0, "current_step": 5}


# ═══════════════════════════════════════
# Node 6: 成长 (Baostock 数据在 price_data 顶层)
# ═══════════════════════════════════════
def node_growth(state: SingleStockState) -> dict:
    """成长分析 — 从 Baostock payload 顶层取 earnings_growth/revenue_growth。"""
    yf_data = state.get("price_data", {}) or {}
    try:
        earnings_growth = float(yf_data.get("earnings_growth", 0) or 0) * 100
        revenue_growth = float(yf_data.get("revenue_growth", 0) or 0) * 100
        return {"earnings_cagr_3y": earnings_growth, "revenue_cagr_3y": revenue_growth, "current_step": 6}
    except Exception:
        return {"earnings_cagr_3y": 0, "revenue_cagr_3y": 0, "current_step": 6}


# ═══════════════════════════════════════
# Node 7: AI 投资论点 + 综合评分
# ═══════════════════════════════════════
def node_ai_thesis(state: SingleStockState) -> dict:
    """DeepSeek 综合研判 + 评分汇总。"""
    try:
        from .deepseek_analyzer import _call_deepseek
        from config import SCRENNER_CONFIG

        pe_val = _score_pe(state.get("pe", 0))
        roe_val = _score_roe(state.get("roe", 0))
        growth_val = _score_growth(state.get("earnings_cagr_3y", 0))
        total = pe_val + roe_val + growth_val

        rec = "强烈推荐" if total >= 80 else "推荐" if total >= 60 else "中性" if total >= 40 else "回避"

        prompt = _build_thesis_prompt(state)
        ds_key = SCRENNER_CONFIG.get("DS_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        ds_model = SCRENNER_CONFIG.get("DS_MODEL", "deepseek-chat")

        ai_text = ""
        if ds_key:
            try:
                ai_text = _call_deepseek(ds_key, ds_model, prompt, system="你是一位价值投资分析师，用中文200字以内回答。")
            except Exception as e:
                logger.warning(f"DeepSeek call failed: {e}")
                ai_text = "AI 分析暂时不可用"
        else:
            ai_text = "未配置 DeepSeek API Key"

        return {
            "total_score": total,
            "score_breakdown": {"估值": pe_val, "质量": roe_val, "成长": growth_val},
            "recommendation": rec,
            "ai_thesis": ai_text,
            "current_step": 7,
        }
    except Exception as e:
        logger.error(f"ai_thesis failed: {traceback.format_exc()}")
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
    industry_ctx = state.get("industry_context", "")
    return f"""你是一位价值投资分析师。请基于以下信息对 {state.get("resolved_name", "")}({state.get("resolved_code", "")}) 做研判。

【产业链】
行业: {state.get("csic_sector", "未知")}
概念板块: {", ".join(state.get("concept_boards", []))}
{chr(10) + industry_ctx if industry_ctx else ""}

【估值】
PE: {state.get("pe", 0):.1f}
PB: {state.get("pb", 0):.1f}

【质量】
ROE: {state.get("roe", 0):.1f}%
毛利率: {state.get("gross_margin", 0):.1f}%

【成长】
营收增速: {state.get("revenue_cagr_3y", 0):.1f}%
利润增速: {state.get("earnings_cagr_3y", 0):.1f}%

【同行对比】
{_format_peers(state.get("peers", []))}

请用中文，200字以内，从价值投资角度分析：
1. 产业链地位与护城河
2. 当前估值是否合理
3. 主要风险
4. 投资建议"""

def _format_peers(peers: list[dict]) -> str:
    if not peers:
        return "无同行数据"
    return "\n".join(f"{p['name']}({p['code']}): PE {p.get('pe',0):.1f} ROE {p.get('roe',0):.1f}% 评分 {p.get('score',0)}" for p in peers)


# ═══════════════════════════════════════
# 构建图
# ═══════════════════════════════════════
def _has_error(state: SingleStockState) -> str:
    return "end" if state.get("error") else "continue"

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
