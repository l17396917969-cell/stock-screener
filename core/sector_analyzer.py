import logging
import json
from datetime import datetime
from config import SCRENNER_CONFIG

logger = logging.getLogger(__name__)


from .data_fetcher import (
    get_market_overview,
    get_sector_snapshot,
    get_latest_macro_news,
    get_sector_fund_flow_top,
    _load_sw_sector_map,
)


# ──────────────────────────────────────────────────
# 主提示词：四维数据 + AI只输出板块名称（无股票代码）
# ──────────────────────────────────────────────────
def _build_prompt(
    market_data: dict,
    sectors_data: list,
    macro_news: str,
    sector_fund_flow: str,
    sw_sector_names: list[str] | None = None,
) -> str:
    today = datetime.now().strftime("%Y年%m月%d日")

    has_real = (market_data is not None and sectors_data is not None and len(sectors_data) > 0)

    if has_real:
        rows = []
        for s in sectors_data:
            rows.append(
                "| " + s["name"] + " | " + str(s["pct_change"])
            + "% | " + str(s["up_count"]) + " | " + s["leader"]
            + " | " + str(s["leader_pct"]) + "% |"
            )
        sectors_table = (
            "| 行业板块 | 当日涨跌幅 | 上涨家数 | 领涨股票 | 领涨涨跌幅 |\n"
            "|---|---|---|---|---|\n" + "\n".join(rows)
        )
        market_str = (
            "- 大盘指数表现：上证指数 " + str(market_data.get("sh_index", ""))
            + "、深成指 " + str(market_data.get("sz_index", ""))
            + "、创业板指 " + str(market_data.get("cy_index", ""))
            + "\n- 市场情绪：上涨 " + str(market_data.get("up_count", 0))
            + " / 下跌 " + str(market_data.get("down_count", 0))
            + "，涨停 " + str(market_data.get("limit_up", 0))
            + "，跌停 " + str(market_data.get("limit_down", 0))
            + "\n- 两市成交额：" + str(market_data.get("total_amount", 0)) + " 亿元"
        )
        source_note = "（数据来源于实时行情接口）"
    else:
        sectors_table = "（暂无实时板块数据）"
        market_str = "（实时行情接口暂时无法获取，请基于你的知识进行分析）"
        source_note = "（以下分析基于AI大模型知识库）"

    header = "### A股宏观热点与板块选择任务（" + today + "）" + source_note
    sw_names_ref = (", ".join(sw_sector_names[:50]) if sw_sector_names else "半导体、银行、电子元件等")

    body = (
        "你是一位深谙中国A股市场、宏观经济与产业政策的顶尖量化战略科学家。"
        "你的任务是基于以下四维数据，对A股热点板块进行“政策底+资金底+技术面”三重共振分析，"
        "筛选出最可能走出持续性行情的主线板块。\n\n"
        "#### 【实盘输入数据】\n\n"
        "**一、全市场概况**\n" + market_str + "\n\n"
        "**二、今日涨幅前20板块（表象热点）**\n" + sectors_table + "\n\n"
        "**三、今日主力资金净流入前10板块（内在资金轨迹）**\n" + sector_fund_flow + "\n\n"
        "**四、当日宏观与市场要闻（政策催化信号）**\n" + macro_news + "\n\n"
        "#### 【分析要求】\n\n"
        "1. 结合涨幅前20和资金净流入前10，寻找表象和内在共振的板块。\n"
        "2. 用新闻验证资金流向是否与政策主线一致。\n"
        "3. 绝对排除防守型板块：银行、房地产，白酒、证券、保险不在推荐范围内。\n"
        "4. 【关键约束】JSON中板块名称必须为申万行业名称，参考范围：" + sw_names_ref + "等。禁止使用题材概念名（如“人工智能”、“低空经济”、“新能源汽车”等），否则系统无法获取成分股数据。\n\n"
        "#### 【输出格式】\n\n"
        "**第一部分：Markdown 研报**\n"
        "严格按以下结构输出，不废话，直接写标题：\n"
        "### A股热点板块实盘分析（" + today + "）\n"
        "#### 市场情绪概览\n"
        "[根据大盘量能数据判断市场所处阶段：启动/高潮/退潮/冰点]\n"
        "#### 板块三维度评分\n"
        "| 板块名称 | 短期热度(40%) | 中期趋势(30%) | 长期确定性(30%) | 综合得分 | 评级 |\n"
        "|---|---|---|---|---|---|\n"
        "| [板块] | [分] | [分] | [分] | [分] | [强烈关注/中性/回避] |\n"
        "#### 主线板块深度分析\n"
        "[针对前3名高分板块，拆解：核心驱动逻辑 + 板块梯队 + 风险提示]\n"
        "#### 投资策略建议\n"
        "[核心仓位/卫星仓位配置建议]\n\n"
        "**第二部分：JSON（必须紧接在Markdown报告之后）**\n"
        "只输出板块名称和看好理由，**不要输出任何股票代码**"
        "（股票代码由系统通过实时行情接口获取）。\n"
        "```json\n"
        "{\n"
        '  "sectors": [\n'
        "    {\n"
        '      "name": "板块名称",\n'
        '      "type": "短线热点|长线趋势|两者兼具",\n'
        '      "reasoning": "核心看好逻辑（一句话）"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
        "JSON的key必须使用英文，禁止使用中文key！"
    )

    return header + "\n\n" + body



# ──────────────────────────────────────────────────
# 方案A：DeepSeek（OpenAI 兼容接口）
# ──────────────────────────────────────────────────
def _call_deepseek(api_key: str, model_name: str, prompt: str) -> str:
    from openai import OpenAI

    logger.info("[Backend: DeepSeek] Using model: " + model_name)
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=180,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是一位深谙中国A股市场、宏观经济与产业政策的顶尖量化战略科学家。"
                "你的职责是综合政策、资金、技术三维度筛选A股热点主线板块。"
                "重要：只输出板块名称和理由，不要输出任何股票代码！"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.1,
        stream=False,
    )
    return response.choices[0].message.content


# ──────────────────────────────────────────────────
# 方案B：Gemini（支持 Google Search grounding）
# ──────────────────────────────────────────────────
def _call_gemini(api_key: str, model_name: str, prompt: str) -> str:
    from google import genai
    from google.genai import types

    logger.info("[Backend: Gemini] Using model: " + model_name)
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=120000)
    )
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[google_search_tool],
        temperature=0.1,
    )
    response = client.models.generate_content(
        model=model_name, contents=prompt, config=config
    )
    return response.text


# ──────────────────────────────────────────────────
# 解析 AI 返回（板块名称+理由，无股票代码）
# ──────────────────────────────────────────────────
def _parse_response(text: str) -> dict:
    json_start = text.rfind("```json")
    if json_start == -1:
        json_start = text.rfind("{")
        clean_json = text[json_start:]
        reasoning_md = text[:json_start].strip()
    else:
        reasoning_md = text[:json_start].strip()
        json_end = text.find("```", json_start + 7)
        clean_json = (
            text[json_start + 7 : json_end].strip()
            if json_end > -1
            else text[json_start + 7 :].strip()
        )

    try:
        result = json.loads(clean_json)
        sectors_raw = result.get("sectors", [])
    except Exception as e:
        logger.error("JSON解析失败: " + str(e) + ", raw: " + clean_json[:200])
        raise ValueError("AI返回的JSON格式无法解析。")

    if not sectors_raw:
        raise ValueError("AI没有返回有效的板块列表。")

    sectors_parsed = []
    for s in sectors_raw:
        sectors_parsed.append(
            {
                "name": s.get("name", "未知板块"),
                "type": s.get("type", ""),
                "reasoning": s.get("reasoning", ""),
            }
        )

    logger.info(
        "解析完成：" + str(len(sectors_parsed)) + " 个板块，股票代码由系统实时拉取"
    )
    return {
        "sectors": [s["name"] for s in sectors_parsed],
        "sectors_detail": sectors_parsed,
        "reasoning": reasoning_md,
        "stock_infos": {},
    }


# ──────────────────────────────────────────────────
# 主入口：自动选择 backend
# ──────────────────────────────────────────────────
def analyze_macro_sectors_with_ai() -> dict:
    cfg = SCRENNER_CONFIG

    md = get_market_overview()
    sd = get_sector_snapshot()
    macro_news = get_latest_macro_news()
    sector_fund_flow = get_sector_fund_flow_top()
    macro_news_str = (
        "\n".join(macro_news) if isinstance(macro_news, list) else str(macro_news)
    )
    sector_fund_flow_str = (
        "\n".join(sector_fund_flow)
        if isinstance(sector_fund_flow, list)
        else str(sector_fund_flow)
    )
    sw_sector_names = list(_load_sw_sector_map().keys())
    prompt = _build_prompt(md, sd, macro_news_str, sector_fund_flow_str, sw_sector_names)

    ds_key = cfg.get("DS_API_KEY", "").strip()
    if ds_key:
        ds_model = cfg.get("DS_MODEL", "deepseek-chat")
        try:
            logger.info("Trying DeepSeek backend...")
            raw = _call_deepseek(ds_key, ds_model, prompt)
            return _parse_response(raw)
        except Exception as e:
            logger.error("DeepSeek 调用失败: " + str(e) + "，尝试 Gemini...")

    gemini_key = cfg.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise ValueError("请提供 Gemini API Key 或 DeepSeek API Key 中的至少一个。")

    gemini_model = cfg.get("GEMINI_MODEL", "gemini-2.5-pro-preview-06-05")
    raw = _call_gemini(gemini_key, gemini_model, prompt)
    return _parse_response(raw)


# ──────────────────────────────────────────────────
# 从 AI 返回的板块名称列表中提取成分股（实时拉取，不走AI幻觉）
# ──────────────────────────────────────────────────
def get_stocks_from_sectors(selected_sectors: list, ai_result: dict) -> tuple:
    """
    根据 AI 返回的板块名称，通过东方财富接口实时拉取真实成分股。
    不依赖 AI 生成股票代码，彻底杜绝幻觉。
    """
    from .data_fetcher import get_board_stocks

    sectors_detail = ai_result.get("sectors_detail", [])
    all_stocks = set()
    stock_infos = {}

    for sector in sectors_detail:
        if sector["name"] not in selected_sectors:
            continue
        try:
            df = get_board_stocks(sector["name"])
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get("代码", "")).zfill(6)
                    if not code.isdigit() or len(code) != 6:
                        continue
                    name = str(row.get("名称", code))
                    all_stocks.add(code)
                    if code not in stock_infos:
                        stock_infos[code] = {"code": code, "name": name, "sectors": []}
                    if sector["name"] not in stock_infos[code]["sectors"]:
                        stock_infos[code]["sectors"].append(sector["name"])
        except Exception as e:
            logger.warning("拉取板块[" + sector["name"] + "]成分股失败: " + str(e))
            continue

    logger.info(
        "从 "
        + str(len(selected_sectors))
        + " 个板块中实时拉取到 "
        + str(len(all_stocks))
        + " 只股票"
    )
    return list(all_stocks), stock_infos
