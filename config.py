import os

# 基础配置
DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-for-stock-screener'

# 核心选股参数 (对应提示词的排雷标准)
SCRENNER_CONFIG = {
    "MIN_MARKET_CAP": 100_00_00_0000,   # 市值下限 (100亿元，不只看大盘)
    "MIN_ROE": 12.0,                     # ROE 门槛 (%)，价值投资要求>12%
    "MIN_GROSS_MARGIN": 15.0,           # 毛利率门槛 (%)
    "MIN_PROFIT_GROWTH": 5.0,           # 扣非净利润增速门槛 (%)
    "MAX_DRAWDOWN": 40.0,               # 最大回撤 (%)
    "MAX_PE": 50,                        # PE上限，排除过度高估
    "MAX_PB": 8,                         # PB上限，排除资产泡沫
    "MIN_DIVIDEND": 0,                   # 最低股息率 (0表示股息可选)
    "EXCLUDED_SECTORS": ["银行", "房地产", "白酒", "证券", "保险"], # 排除板块
    "TARGET_STOCK_COUNT": 5,             # 最终筛选目标数量 3-5只
    "DS_API_KEY": os.environ.get('DEEPSEEK_API_KEY') or '',  # DeepSeek API 密钥
    "DS_MODEL": "deepseek-chat",                             # DeepSeek 模型
}

# ── 价值投资评分体系 (总分100分) ─────────────────────────────
# 估值30分 + 质量40分 + 成长30分 = 100分
VALUE_SCORING_WEIGHTS = {
    # 维度 1: 估值维度 (共 30分) —— 寻找被低估的标的
    "PE_HISTORY": 6,         # PE历史分位：越低越便宜
    "PB": 5,                 # PB市净率：资产折价程度
    "PEG": 6,                # PEG估值性价比：成长对价
    "DIVIDEND": 5,           # 股息率：现金回报，防御性指标
    "FCF_YIELD": 8,          # 自由现金流收益率：真金白银回报率

    # 维度 2: 质量维度 (共 40分) —— 寻找好公司
    "ROE": 8,                # ROE水平(加权多年)：股东回报核心
    "ROIC": 7,               # ROIC资本回报率：剔除杠杆后的真实盈利能力
    "GROSS_MARGIN_STABILITY": 6,  # 毛利率稳定性：护城河宽度
    "FCF_NP_RATIO": 7,       # FCF/净利润比：利润含金量
    "DEBT_RATIO": 6,         # 负债率：财务健康度
    "OP_CASHFLOW": 6,        # 经营现金流：造血能力

    # 维度 3: 成长维度 (共 30分) —— 寻找有未来的公司
    "DEDUCTED_NP_3Y_CAGR": 10,   # 扣非净利润 3年复合增速
    "REVENUE_GROWTH": 8,         # 营收增速：业务扩张
    "RD_RATIO": 6,               # 研发投入占比：创新驱动
    "INDUSTRY_CEILING": 6,       # 行业天花板：市场空间
}

# ── 向后兼容：保留旧版 SCORING_WEIGHTS 作为别名 ─────────────
# 旧版使用者可能直接 import SCORING_WEIGHTS，此处保留确保不报错
SCORING_WEIGHTS = VALUE_SCORING_WEIGHTS
