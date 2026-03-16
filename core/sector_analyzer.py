import logging
import json
import re
from datetime import datetime
from config import SCRENNER_CONFIG
from .master_data import stock_master

logger = logging.getLogger(__name__)


from .data_fetcher import get_market_overview, get_sector_snapshot

# ──────────────────────────────────────────────────
# 主提示词：综合双输出（Markdown研报 + JSON配置表）
# ──────────────────────────────────────────────────
def _build_prompt(market_data: dict, sectors_data: list) -> str:
    today = datetime.now().strftime('%Y年%m月%d日')
    
    # 检查数据源是否可用
    has_real_time_data = market_data is not None and sectors_data is not None and len(sectors_data) > 0
    
    if has_real_time_data:
        # 使用真实数据
        sectors_table = "| 行业板块 | 当日涨跌幅 | 上涨家数 | 领涨股票 | 领涨涨跌幅 |\n|---|---|---|---|---|\n"
        for s in sectors_data:
            sectors_table += f"| {s['name']} | {s['pct_change']}% | {s['up_count']} | {s['leader']} | {s['leader_pct']}% |\n"
        
        market_str = (
            f"- 大盘指数表现：上证指数 {market_data.get('sh_index', '')}、"
            f"深成指 {market_data.get('sz_index', '')}、创业板指 {market_data.get('cy_index', '')}\n"
            f"- 市场情绪：上涨家数 {market_data.get('up_count', 0)} / 下跌家数 {market_data.get('down_count', 0)}，"
            f"涨停家数 {market_data.get('limit_up', 0)}，跌停家数 {market_data.get('limit_down', 0)}\n"
            f"- 两市成交额：{market_data.get('total_amount', 0)} 亿元"
        )
        data_source_note = "（以下数据来源于实时行情接口）"
    else:
        # AkShare 不可用，提示词让 DeepSeek 依靠自身知识
        sectors_table = "（暂无实时板块数据，请根据你的知识进行分析）"
        market_str = (
            "（实时行情接口暂时无法获取，请基于你对当前A股市场的了解进行分析）\n"
            "你可以根据以下角度进行分析：\n"
            "1. 近期政策动向和市场热点\n"
            "2. 资金流向和成交量变化\n"
            "3. 热门概念和题材\n"
            "4. 机构持仓和北向资金动向"
        )
        data_source_note = "（以下分析基于AI大模型知识库，如与实际有出入请以实际行情为准）"
        
    return f"""### A股热门板块分析任务 (截至 {today}) {data_source_note}

请根据以下输入数据，对当前A股市场的热点板块进行专业分析。你需要基于"短期热度+中期趋势+长期确定性"的三维框架，筛选出具备持续性的主线板块，并给出具体的投资策略建议。

**重要提示：如果实时行情数据无法获取，请联网搜索获取最新的A股市场数据，包括：今日涨跌停数量、成交量、热门板块、资金流向、北向资金动向等。**

#### 【实盘输入数据】
**一、全市场概况**
{market_str}

**二、板块表现数据（按今日涨幅排行前20）**
{sectors_table}

#### 【分析任务与输出格式要求】
请严格运用系统化的板块分析方法论（短期热度40%+中期趋势30%+长期确定性30%权重）进行实盘级打分和推理。
绝对排除防守型板块：严禁推荐'银行'、'房地产'、'白酒'、'证券'、'保险'。

必须要输出两部分内容：

**第一部分：直达核心的 Markdown 研报。请严格按照以下结构输出，不需要寒暄，直接写标题：**
### A股热门板块实盘分析报告（截至{today}）
#### 一、市场情绪概览
[基于上述大盘和量能数据的概括]
#### 二、板块三维度评分表
| 板块名称 | 短期热度(40%) | 中期趋势(30%) | 长期确定性(30%) | 综合得分 | 评级 |
|---|---|---|---|---|---|
| [板块名称] | [分数] | [分数] | [分数] | [分数] | [强烈关注/中性等] |
#### 三、主线板块深度分析
[针对选出的前3名高分板块，拆解核心驱动逻辑、板块梯队结构、风险提示]
#### 四、投资策略建议
[写出仓位配置建议，如核心仓位买什么、卫星仓位买什么]

**第二部分：JSON 机器识别代码（必须放在报告最末尾！）**
在 Markdown 报告完成后，你必须为报告中所有被评为"强烈关注"和"关注"的板块，凭借你的A股知识库手工列出 **每个板块 30-50只** 代表性主板成分股代码（6位纯数字）。

**JSON格式必须严格按以下格式，禁止使用其他格式：**
```json
{{
  "sectors": [
    {{
      "name": "板块名称",
      "type": "短线热点|长线趋势|两者兼具",
      "stocks": ["600123", "000456"]
    }}
  ]
}}
```
注意：JSON的key必须使用英文"name"、"type"、"stocks"，禁止使用中文！
"""


# ──────────────────────────────────────────────────
# 方案A：DeepSeek（OpenAI 兼容接口）
# ──────────────────────────────────────────────────
def _call_deepseek(api_key: str, model_name: str, prompt: str) -> str:
    from openai import OpenAI
    logger.info(f"[Backend: DeepSeek] Using model: {model_name}")
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
                "你具备完整的A股上市公司代码知识，能够准确给出6位股票代码。"
                "当实时行情数据不可用时，请联网搜索获取最新数据进行分析。"
                "重要：JSON输出必须使用英文key：sectors, name, type, stocks，不允许使用中文key！"
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.1,  # 低温度确保股票代码准确
        stream=False,
    )
    return response.choices[0].message.content


# ──────────────────────────────────────────────────
# 方案B：Gemini（支持 Google Search grounding）
# ──────────────────────────────────────────────────
def _call_gemini(api_key: str, model_name: str, prompt: str) -> str:
    from google import genai
    from google.genai import types
    logger.info(f"[Backend: Gemini] Using model: {model_name}")
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120000)
    )
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[google_search_tool],
        temperature=0.1,
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config
    )
    return response.text


# ──────────────────────────────────────────────────
# 解析 AI 返回的新格式 JSON
# ──────────────────────────────────────────────────
def _parse_response(text: str) -> dict:
    """
    解析 AI 返回的混合格式（Markdown + 尾部 JSON）
    """
    # 尝试找到最后一个 ```json
    json_start = text.rfind('```json')
    if json_start == -1:
        # 兼容处理
        json_start = text.rfind('{')
        clean_json = text[json_start:]
        reasoning_md = text[:json_start].strip()
    else:
        # 截取 markdown 和 json
        reasoning_md = text[:json_start].strip()
        json_end = text.find('```', json_start + 7)
        if json_end > -1:
            clean_json = text[json_start + 7:json_end].strip()
        else:
            clean_json = text[json_start + 7:].strip()
            
    try:
        result = json.loads(clean_json)
        sectors_raw = result.get('sectors', [])
    except Exception as e:
        logger.error(f"JSON Parsing failed. Raw JSON expected string: {clean_json}")
        raise ValueError("AI 返回的 JSON 格式无法被解析。")

    if not sectors_raw:
        raise ValueError("AI没有返回有效的板块列表。")

    # 标准化格式
    sectors_parsed = []
    all_stocks = {}  # code -> {name, sectors}

    for s in sectors_raw:
        sector_name = s.get('name', '未知板块')
        stocks = s.get('stocks', [])
        # 确保格式：6位字符串
        cleaned_stocks = []
        for code in stocks:
            code_str = str(code).strip().zfill(6)
            if re.match(r'^\d{6}$', code_str):
                cleaned_stocks.append(code_str)
                if code_str not in all_stocks:
                    # 从本地主数据获取名称
                    name = stock_master.get_name(code_str)
                    all_stocks[code_str] = {'code': code_str, 'name': name, 'sectors': []}
                all_stocks[code_str]['sectors'].append(sector_name)

        sectors_parsed.append({
            'name': sector_name,
            'type': s.get('type', ''),
            'stocks': cleaned_stocks,
        })

    logger.info(f"Parsed {len(sectors_parsed)} sectors, {len(all_stocks)} unique stocks total.")
    return {
        "sectors": [s['name'] for s in sectors_parsed],
        "sectors_detail": sectors_parsed,
        "reasoning": reasoning_md, # The Markdown report goes directly to reasoning
        "stock_infos": all_stocks,
    }


# ──────────────────────────────────────────────────
# 主入口：自动选择 backend
# ──────────────────────────────────────────────────
def analyze_macro_sectors_with_ai() -> dict:
    """
    分析当前A股最值得关注的 5-8 个板块，并直接返回每个板块的代表性成分股。
    优先使用 DeepSeek，否则使用 Gemini。
    """
    cfg = SCRENNER_CONFIG
    
    # 实时获取市场数据注入提示词
    md = get_market_overview()
    sd = get_sector_snapshot()
    prompt = _build_prompt(md, sd)

    # ── DeepSeek 优先 ──
    ds_key = cfg.get("DS_API_KEY", "").strip()
    if ds_key:
        ds_model = cfg.get("DS_MODEL", "deepseek-reasoner")
        try:
            logger.info("Trying DeepSeek backend...")
            raw = _call_deepseek(ds_key, ds_model, prompt)
            return _parse_response(raw)
        except Exception as e:
            logger.error(f"DeepSeek call failed: {e}, falling back to Gemini...")

    # ── Gemini 兜底 ──
    gemini_key = cfg.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise ValueError("请提供 Gemini API Key 或 DeepSeek API Key 中的至少一个。")

    gemini_model = cfg.get("GEMINI_MODEL", "gemini-3.1-pro-preview-customtools")
    raw = _call_gemini(gemini_key, gemini_model, prompt)
    return _parse_response(raw)


# ──────────────────────────────────────────────────
# 从 AI 返回结果中提取成分股（无需外部API）
# ──────────────────────────────────────────────────
def get_stocks_from_sectors(selected_sectors: list, ai_result: dict) -> tuple[list, dict]:
    """
    从 AI 分析结果中直接取出用户选中板块的成分股，无需外部 API。

    Args:
        selected_sectors: 用户勾选的板块名称列表
        ai_result: analyze_macro_sectors_with_ai() 返回的完整结果

    Returns:
        (all_stock_codes: list, stock_infos: dict)
    """
    sectors_detail = ai_result.get("sectors_detail", [])
    all_stocks = set()
    stock_infos = {}

    for sector in sectors_detail:
        if sector['name'] not in selected_sectors:
            continue
        for code in sector.get('stocks', []):
            all_stocks.add(code)
            if code not in stock_infos:
                stock_infos[code] = {
                    'code': code,
                    'name': ai_result.get('stock_infos', {}).get(code, {}).get('name', ''),
                    'sectors': []
                }
            if sector['name'] not in stock_infos[code]['sectors']:
                stock_infos[code]['sectors'].append(sector['name'])

    logger.info(f"Extracted {len(all_stocks)} unique stocks from selected sectors {selected_sectors}")
    return list(all_stocks), stock_infos
