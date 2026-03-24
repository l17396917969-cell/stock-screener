import logging
import os
import requests
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# DeepSeek 提示词模板
PROMPT_TEMPLATE = """### A股多专家联合诊断系统 (CIO 决策模式)

你现在是顶尖A股游资机构的首席投资官(CIO)。你需要主持一场针对【{stock_name}】（【{stock_code}】）的盘中/盘后战术会议。
你的团队有三位顶尖专家，他们将分别从自己的专业领域给出独立判断，最后由你(CIO)进行汇总，给出最终的交易决策。

#### 【输入数据（当前分时实时快照）】

**一、大盘与板块环境**
- 大盘走势参考：{market_proxy}
- 所属板块：{sectors}

**二、个股量价与技术面**
- 当前股价：{current_price}元 (今日涨跌幅：{change_pct}%)
- 涨跌停状态：{limit_up_status}
- 均线数据：MA5={ma5}、MA10={ma10}、MA20={ma20}、MA60={ma60}
- 股价与20日线关系：偏离度 {price_vs_ma20}%
- 成交量数据：今日成交量{volume}手、量比{volume_ratio}、换手率{turnover_rate}%
- 标志K线状态：最高价 {high}, 最低价 {low}
- 相对强度（RPS）：{rps}
- 技术指标：KDJ的J值{kdj_j}、MACD状态：{macd_status}

**三、资金面与关键价位**
- 主力资金：今日净流入{main_net_inflow_today}万元、近5日累计净流入{main_net_inflow_5d}万元
- 北向资金（如有）：近5日持股市值变化{north_holding_change_5d}万元
- 融资融券状态：{short_ratio}
- 近期支撑位：{support}
- 近期压力位：{resistance}

---

#### 【会议流程与专家发言要求】

**专家1：威廉·欧奈尔 (成长/动量派)**
- 关注点：RPS相对强度、量比突破、均线多头排列、VCP收敛形态。
- 任务：判断该股是否具备强劲的右侧动量？是否处于主升浪或即将突破？

**专家2：霍华德·马克斯 (周期/左侧/均值回归派)**
- 关注点：股价与MA20/MA60的偏离度、KDJ超卖/超买、支撑位测试、缩量洗盘。
- 任务：判断该股当前是否处于极度悲观的错杀位置？安全边际如何？下行风险是否已充分释放？

**专家3：A股一线游资 (情绪/资金流/博弈派)**
- 关注点：涨跌停状态({limit_up_status})、主力资金净流入、换手率、板块热度。
- 任务：判断当前盘口资金是真金白银在抢筹，还是诱多出货？情绪周期处于冰点、发酵还是高潮？

**CIO (你) 的最终决策**
- 任务：综合三位专家的意见，结合A股T+1交易规则和10%/20%涨跌幅限制，给出最终的战术指令。

---

#### 【输出格式要求】

请严格以此格式输出（只输出 markdown 文本，不要含有其他无关内容）：

### 【{stock_name}】（【{stock_code}】）多专家联合诊断报告（截至【{analysis_date}】）

#### 一、专家独立研判

**1. 欧奈尔 (动量派) 的意见：**
【基于量价突破和RPS的分析，给出1-2句话的核心观点】

**2. 马克斯 (左侧派) 的意见：**
【基于偏离度、支撑位和安全边际的分析，给出1-2句话的核心观点】

**3. 一线游资 (情绪派) 的意见：**
【基于资金流向、涨跌停状态和换手率的分析，给出1-2句话的核心观点】

#### 二、CIO 综合评估与风险收益比

- **核心矛盾分析**：【指出当前盘面的核心博弈点，例如：动量极强但偏离度过高，或左侧安全但资金未介入】
- **当前价位**：【{current_price}元】
- **止损位**：【XX元】（基于【如：20日线/前低】）
- **目标位**：【XX元】（基于【如：前高/整数关口】）
- **风险收益比**：【X:Y】（【满足/不满足】>3:1的要求）

#### 三、最终操作指令

- **定性分类**：【右侧突破 / 左侧潜伏 / 震荡洗盘 / 破位下行】
- **买点评级**：【强烈买入 / 推荐买入 / 中性观望 / 卖出回避】
- **操作策略**：【具体短线介入及止盈操作细节，必须明确具体价格区间】
- **仓位建议**：【如：空仓防守 / 轻仓（1-2成）等】
"""


def generate_short_term_analysis(api_key: str, data: dict) -> str:
    """
    调用 DeepSeek API 生成短线分析报告
    """
    if not api_key:
        return "[WARN] 未配置 DeepSeek API Key，请在页面顶部配置。"

    try:
        # 安全取值格式化
        def fmt(val, fmt_str="{:.2f}"):
            if val is None:
                return "暂无数据"
            try:
                return fmt_str.format(float(val))
            except:
                return str(val)

        mf = data.get("money_flow", {})
        ma = data.get("ma", {})
        st = data.get("sr_levels", {})

        # Calculate price vs MA20 difference for proxy
        current_price_raw = data.get("price", 0)
        ma20_raw = ma.get("ma20", 1)
        price_vs_ma20_pct = (
            ((current_price_raw - ma20_raw) / ma20_raw * 100) if ma20_raw else 0
        )

        prompt = PROMPT_TEMPLATE.format(
            stock_code=data.get("ticker", "").replace(".SS", "").replace(".SZ", ""),
            stock_name=data.get("name", "未知"),
            analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Added time
            current_price=fmt(data.get("price")),
            limit_up_status=data.get("limit_up_status", "未知"),
            ma5=fmt(ma.get("ma5")),
            ma10=fmt(ma.get("ma10")),
            ma20=fmt(ma.get("ma20")),
            ma60=fmt(ma.get("ma60")),
            price_vs_ma20=fmt(price_vs_ma20_pct),
            volume_ratio=fmt(data.get("volume_ratio")),
            turnover_rate=fmt(data.get("turnover_rate")),
            volume=fmt(data.get("volume")),
            change_pct=fmt(data.get("change_pct")),
            rps=fmt(data.get("rps")),
            high=fmt(data.get("high")),
            low=fmt(data.get("low")),
            main_net_inflow_today=fmt(mf.get("main_net_in")),
            main_net_inflow_5d=fmt(mf.get("main_net_in_5d")),
            north_holding_change_5d=fmt(
                mf.get("hsgt_net_in_5d", mf.get("hsgt_hold_change"))
            ),
            short_ratio=fmt(data.get("short_ratio", "暂无融资融券可用数据"), "{}"),
            kdj_j=data.get("kdj_j", "N/A"),
            macd_status=data.get("macd_status", "N/A"),
            support=st.get("support", "N/A"),
            resistance=st.get("resistance", "N/A"),
            market_proxy="当前大盘处于宏观震荡蓄势或局部活跃周期，资金偏好热点轮动",
            sectors="、".join(data.get("sectors", ["热点板块"])),  # 简易回退
        )

        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 为了更严谨的分析推荐使用 deepseek-reasoner 或 deepseek-chat
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位拥有超过 20 年实战经验的A股顶级短线游资操盘手和量化分析师。你熟练使用顶级买点四维分析框架评估高胜率交易机会。请按照用户严格的模板直接输出最终报告，不需要寒暄。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }

        logger.info(f"Calling DeepSeek API for {data.get('name')}...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return content

    except Exception as e:
        logger.error(f"DeepSeek call failed: {e}")
        return f"[FAIL] 调用 DeepSeek 服务失败: {str(e)}"


# ==========================================
# 高级自选/持仓 AI 诊断 (Watchlist/Holdings)
# ==========================================

WATCHLIST_PROMPT_TEMPLATE = """### 【优化版】股票战术诊断与调仓指令系统

#### **【A股交易规则铁律（必须严格遵守）】**
1. **T+1 交易制度**：当日买入的股票，必须到下一个交易日才能卖出。**绝对禁止**建议用户在同一天内完成“先买后卖”的日内做T操作（除非用户已有底仓，可以“先卖老仓，再买新仓”或“先买新仓，再卖老仓”进行滚动做T）。
2. **涨跌幅限制**：主板（60开头、00开头）涨跌幅限制为10%，创业板（300开头）和科创板（688开头）为20%，ST股为5%。**绝对禁止**给出超出该股票当日涨跌幅限制的目标价或止损价。

#### **【任务指令】**

请立即对用户持有的 **【{stock_name} ({stock_code})】** 进行战术级诊断。你的唯一目标是：**深入穿透当前分时盘口意图，结合绝对实时的股价波动与量能分布**，结合用户的持仓成本，给出“继续持有”、“做T降本”或“清仓卖出”的最终指令。

#### **【输入数据】**

**一、 战场态势（个股实时数据）**
*   **现价与日内表现**：{current_price}元（{change_pct}%）
*   **均线系统（短线生命线）**：MA5 = {ma5}，MA20 = {ma20}，MA60 = {ma60}
*   **量能与主力意图**：成交量比 = {volume_ratio}，近5日主力净流入 = {main_net_inflow_5d}万元
*   **多空堡垒**：近期支撑位 = {support}，近期压力位 = {resistance}

**二、 我方情况（用户持仓状态）**
*   **持仓状态**：{holding_status}（【真实持仓】或【纯观察】）
*   **成本与盈亏**：建仓成本 = {cost_price}，当前盈亏幅度 = {profit_pct}%
*   **仓位规模**：{shares}股

---

#### **【分析流程与指令生成】**

**0. 实时分时战术定位**
*   **盘口定调**：基于现价 {current_price} 元及内盘/外盘博弈（量比 {volume_ratio}），判定当前盘中是“主力强势封锁”、“资金分歧出货”还是“缩量极致洗盘”。

根据用户的持仓状态，启动不同的诊断逻辑：

**🔴 情景一：若为【纯观察/未持仓】**
*你的任务是给出“是否参战”及“如何参战”的精确指令。*

1.  **买点狙击分析**：基于当前支撑/压力位及均线系统，判断是“左侧埋伏”还是“右侧突破”。给出具体的**狙击区间**（例如：回踩XX元不破可建仓，或放量突破XX元是进场信号）。
2.  **风控与赔率计算**：评估现价介入的**盈亏比**。明确指出第一目标止盈位（{resistance}附近或更高）和绝对止损线（跌破哪里必须无条件离场）。
3.  **最终指令**：输出“**建议建仓**”、“**等待观望**”或“**放弃关注**”的明确结论。

**🟢 情景二：若为【真实持仓】**
*你的任务是作为“战场指挥官”，根据当前战局和士兵（用户）的成本，下达具体的作战指令。*

1.  **持仓体检（诊断战局）**：
    *   结合{profit_pct}%盈亏和当前量价形态，判断这笔交易的健康度：是“盈利丰厚，处于安全区”、“成本线附近，处于洗盘区”，还是“深度亏损，处于套牢区”。
2.  **战术推演（制定对策）**：
    *   **技术面验证**：当前价格站上/跌破哪条重要均线？量能是否支持上涨？主力是在洗盘还是出货？
    *   **成本锚定分析**：以用户成本价{cost_price}为基准，结合支撑位{support}和压力位{resistance}，判断当前是加仓/做T的时机，还是最后的逃命机会。
3.  **最终指令（必须三选一）**：
    *   **指令A - 继续持有**：触发条件是什么（如：股价在XX均线上方运行，趋势完好）？
    *   **指令B - 做T降本**：给出具体的“做T”策略。例如：“明日若冲高至{resistance}附近无量，则先T出部分仓位；若回踩{support}不破，则接回。T完即止，底仓不动。”
    *   **指令C - 清仓卖出**：这是最冷酷的指令。必须明确指出最后的卖出底线。例如：“无论盈亏，现价就是卖点”、“反弹至XX元是最后的出局机会”或“跌破{support}，核按钮清仓，不要有任何幻想”。

**【系统硬性要求】**
*   你的所有建议必须基于数据，最终输出一个清晰、冷酷、可执行的**战术指令**，并且使用 Markdown 格式漂亮排版，重点结论可以加粗。
*   一定要附带一句对散户心态的辛辣点评，以起到警示或鼓励作用。
"""


def generate_watchlist_diagnosis(api_key: str, data: dict, stock_info: dict) -> str:
    """
    针对 Watchlist 中的股票状态（持有或观察）生成专属的持仓诊断。
    """
    if not api_key:
        return "[WARN] 未配置 DeepSeek API Key，无法生成 AI 诊断。"

    def fmt(val, fmt_str="{:.2f}"):
        if val is None or val == "":
            return "空"
        try:
            return fmt_str.format(float(val))
        except:
            return str(val)

    # Calculate profit metrics
    current_price = data.get("price", 0)
    cost_price = stock_info.get("cost_price")
    shares = stock_info.get("shares", "空")

    status_str = "纯自选观察"
    profit_pct_str = "N/A"
    profit_color = "var(--text-muted)"

    if cost_price and str(stock_info.get("status")) == "holding":
        status_str = "真实持仓"
        try:
            profit = ((current_price - float(cost_price)) / float(cost_price)) * 100
            profit_pct_str = f"{profit:.2f}"
            profit_color = (
                "var(--red)"
                if profit > 0
                else ("var(--green)" if profit < 0 else "var(--text-primary)")
            )
            cost_price_str = f"{float(cost_price):.2f}元"
        except:
            profit_pct_str = "计算错误"
            cost_price_str = str(cost_price)
    else:
        cost_price_str = "无持仓/纯观察"

    mf = data.get("money_flow", {})
    ma = data.get("ma", {})
    st = data.get("sr_levels", {})

    prompt = WATCHLIST_PROMPT_TEMPLATE.format(
        stock_code=data.get("ticker", "").replace(".SS", "").replace(".SZ", ""),
        stock_name=stock_info.get("name", data.get("name", "未知")),
        current_price=fmt(current_price),
        change_pct=fmt(data.get("change_pct")),
        ma5=fmt(ma.get("ma5")),
        ma20=fmt(ma.get("ma20")),
        ma60=fmt(ma.get("ma60")),
        volume_ratio=fmt(data.get("volume_ratio")),
        main_net_inflow_5d=fmt(mf.get("main_net_in_5d")),
        support=st.get("support", "N/A"),
        resistance=st.get("resistance", "N/A"),
        holding_status=status_str,
        cost_price=cost_price_str,
        profit_pct=profit_pct_str,
        profit_color=profit_color,
        shares=shares,
    )

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一位在A股市场沉浮20余年的顶级游资核心操盘手，兼具量化风控的冷酷与对散户心理的深刻洞察。你的语言风格必须直接、冷酷、一针见血，给出的指令具备极强的可操作性，摒弃一切模棱两可的废话。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Generate Watchlist Diagnosis failed: {e}")
        return f"[FAIL] 调用 DeepSeek 服务生成持仓诊断失败: {str(e)}"
