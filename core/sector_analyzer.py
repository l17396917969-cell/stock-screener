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
# 主提示词：价值投资视角 → 寻找被低估板块
# ──────────────────────────────────────────────────
def _build_prompt(
    market_data: dict,
    sectors_data: list,
    macro_news: str,
    sector_fund_flow: str,
    sw_sector_names: list[str] | None = None,
) -> str:
    today = datetime.now().strftime("%Y年%m月%d日")

    has_real = (
        market_data is not None and sectors_data is not None and len(sectors_data) > 0
    )

    if has_real:
        rows = []
        for s in sectors_data:
            rows.append(
                "| "
                + s["name"]
                + " | "
                + str(s["pct_change"])
                + "% | "
                + str(s["up_count"])
                + " | "
                + s["leader"]
                + " | "
                + str(s["leader_pct"])
                + "% |"
            )
        sectors_table = (
            "| 行业板块 | 当日涨跌幅 | 上涨家数 | 领涨股票 | 领涨涨跌幅 |\n"
            "|---|---|---|---|---|\n" + "\n".join(rows)
        )
        market_str = (
            "- 大盘指数表现：上证指数 "
            + str(market_data.get("sh_index", ""))
            + "、深成指 "
            + str(market_data.get("sz_index", ""))
            + "、创业板指 "
            + str(market_data.get("cy_index", ""))
            + "\n- 市场情绪：上涨 "
            + str(market_data.get("up_count", 0))
            + " / 下跌 "
            + str(market_data.get("down_count", 0))
            + "，涨停 "
            + str(market_data.get("limit_up", 0))
            + "，跌停 "
            + str(market_data.get("limit_down", 0))
            + "\n- 两市成交额："
            + str(market_data.get("total_amount", 0))
            + " 亿元"
        )
        source_note = "（数据来源于实时行情接口）"
    else:
        sectors_table = "（暂无实时板块数据）"
        market_str = "（实时行情接口暂时无法获取，请基于你的知识进行分析）"
        source_note = "（以下分析基于AI大模型知识库）"

    header = "### A股价值洼地板块寻找任务（" + today + "）" + source_note
    sw_names_ref = (
        ", ".join(sw_sector_names[:50])
        if sw_sector_names
        else "半导体、银行、电子元件等"
    )

    body = (
        "你是一位深谙格雷厄姆/巴菲特式价值投资理念的顶级基本面分析师。"
        "你的任务是基于以下市场数据，寻找当前A股市场中**被低估、基本面扎实、具有长期投资价值**的板块。"
        "不同于短线热点追逐，你需要从「估值安全边际 + 企业质量 + 长期成长空间」三个维度审视每个板块。\n\n"
        "#### 【实盘输入数据】\n\n"
        "**一、全市场概况**\n" + market_str + "\n\n"
        "**二、今日板块表现一览（涨跌幅）**\n" + sectors_table + "\n\n"
        "**三、今日主力资金净流入前10板块（资金动向参考）**\n"
        + sector_fund_flow
        + "\n\n"
        "**四、当日宏观与市场要闻（政策与经济信号）**\n" + macro_news + "\n\n"
        "#### 【分析要求——价值投资视角】\n\n"
        "1. **寻找被低估板块**：关注近期跌幅较大或长期低迷、但基本面并未恶化的板块（逆向投资思维）。\n"
        "2. **识别优质赛道**：从产业趋势、政策支持、市场需求角度，判断哪些板块具备 3-5 年的长期成长逻辑。\n"
        "3. **评估安全边际**：结合板块当前估值水位（PE/PB 历史分位）、ROE水平、现金流质量，判断是否足够便宜。\n"
        "4. **注意风险规避**：排除银行、房地产、白酒、证券、保险板块。警惕政策打压、需求萎缩、竞争恶化的行业。\n"
        "5. **区分板块类型**：\n"
        "   - 「价值洼地」：估值处于历史低位，基本面稳健，等待价值回归\n"
        "   - 「成长折价」：高成长行业遭遇短期错杀，估值已回落到合理区间\n"
        "   - 「稳定红利」：现金流充沛、分红稳定的防御型行业\n"
        "6. 【关键约束】JSON中板块名称必须为申万行业名称，参考范围："
        + sw_names_ref
        + "等。禁止使用题材概念名（如「人工智能」、「低空经济」、「新能源汽车」等），否则系统无法获取成分股数据。\n\n"
        "#### 【输出格式】\n\n"
        "**第一部分：Markdown 研报**\n"
        "严格按以下结构输出：\n"
        "### A股价值洼地板块分析（" + today + "）\n"
        "#### 市场估值水位判断\n"
        "[根据大盘量能、情绪数据判断当前市场所处阶段：低迷/合理/亢奋，以及整体估值水位]\n"
        "#### 板块三维度评分（价值投资版）\n"
        "| 板块名称 | 估值安全边际(40%) | 企业质量(30%) | 长期成长(30%) | 综合得分 | 类型 |\n"
        "|---|---|---|---|---|---|\n"
        "| [板块] | [分] | [分] | [分] | [分] | [价值洼地/成长折价/稳定红利] |\n"
        "#### 被低估板块深度分析\n"
        "[针对前3名高分板块，拆解：低估逻辑 + 产业趋势 + 核心风险]\n"
        "#### 价值投资策略建议\n"
        "[建议仓位配置：核心仓位（确定性高）+ 卫星仓位（弹性大）]\n\n"
        "**第二部分：JSON（必须紧接在Markdown报告之后）**\n"
        "只输出板块名称和看好理由，**不要输出任何股票代码**"
        "（股票代码由系统通过实时行情接口获取）。\n"
        "```json\n"
        "{\n"
        '  "sectors": [\n'
        "    {\n"
        '      "name": "板块名称",\n'
        '      "type": "价值洼地|成长折价|稳定红利",\n'
        '      "reasoning": "被低估的核心逻辑（一句话）"\n'
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
                "你是一位深谙格雷厄姆/巴菲特式价值投资理念的顶级基本面分析师。"
                "你的职责是从估值安全边际、企业质量、长期成长空间三个维度寻找A股被低估的板块。"
                "重要：只输出板块名称和低估理由，不要输出任何股票代码！"
                "核心理念：别人贪婪时恐惧，别人恐惧时贪婪——寻找市场的错误定价。"
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
# 主入口：DeepSeek 价值洼地分析
# ──────────────────────────────────────────────────
def analyze_macro_sectors_with_ai() -> dict:
    """
    调用 DeepSeek AI 进行宏观分析，寻找被低估的价值板块。
    接口签名与旧版完全一致，保持向后兼容。
    """
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
    prompt = _build_prompt(
        md, sd, macro_news_str, sector_fund_flow_str, sw_sector_names
    )

    ds_key = cfg.get("DS_API_KEY", "").strip()
    if not ds_key:
        raise ValueError("请提供 DeepSeek API Key（在设置页面配置）。")

    ds_model = cfg.get("DS_MODEL", "deepseek-chat")
    logger.info("调用 DeepSeek 进行价值洼地宏观分析...")
    raw = _call_deepseek(ds_key, ds_model, prompt)
    return _parse_response(raw)


# ──────────────────────────────────────────────────
# 从 AI 返回的板块名称列表中提取成分股（实时拉取，不走AI幻觉）
# ──────────────────────────────────────────────────
def get_stocks_from_sectors(selected_sectors: list, ai_result: dict) -> tuple:
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
                    raw_code = str(row.get("代码", "")).strip()
                    normalized_code = (
                        raw_code.split(".")[0].replace("SH", "").replace("SZ", "")
                    )
                    normalized_code = normalized_code.zfill(6)
                    if not normalized_code.isdigit() or len(normalized_code) != 6:
                        continue
                    name = str(row.get("名称", normalized_code))
                    all_stocks.add(normalized_code)
                    if normalized_code not in stock_infos:
                        stock_infos[normalized_code] = {
                            "code": normalized_code,
                            "name": name,
                            "sectors": [],
                        }
                    if sector["name"] not in stock_infos[normalized_code]["sectors"]:
                        stock_infos[normalized_code]["sectors"].append(sector["name"])
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
