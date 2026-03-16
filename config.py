import os

# 基础配置
DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-for-stock-screener'

# 核心选股参数 (对应提示词的排雷标准)
SCRENNER_CONFIG = {
    "MIN_MARKET_CAP": 300_00_00_0000,  # 市值下限 (300亿元)
    "MIN_ROE": 8.0,                    # ROE 门槛 (%)
    "MIN_GROSS_MARGIN": 15.0,          # 毛利率门槛 (%)
    "MIN_PROFIT_GROWTH": 5.0,          # 扣非净利润增速门槛 (%)
    "MAX_DRAWDOWN": 40.0,              # 最大回撤 (%)
    "EXCLUDED_SECTORS": ["银行", "房地产", "白酒", "证券", "保险"], # 排除板块
    "TARGET_STOCK_COUNT": 5,             # 最终筛选目标数量 3-5只
    "GEMINI_API_KEY": os.environ.get('GEMINI_API_KEY') or '', # Google Gemini API 密钥
    "GEMINI_MODEL": "gemini-3.1-pro-preview-customtools", # 支持 Google Search grounding
    "DS_API_KEY": os.environ.get('DEEPSEEK_API_KEY') or '', # DeepSeek API 密钥
    "DS_MODEL": "deepseek-reasoner", # R1深度思考；改为 deepseek-chat 可用 V3（更快）
}

# 指标评分权重总和100分 (v2.0 - 19指标体系)
SCORING_WEIGHTS = {
    # 维度 1: 技术面 (共 30分)
    "MA_TREND": 5,        # 1. 均线趋势
    "VWAP": 4,            # 2. VWAP均价支撑
    "VCP": 4,             # 3. VCP波动收缩
    "RPS": 5,             # 4. RPS相对强度
    "VOLUME_STR": 4,      # 5. 成交量结构
    "ADX": 4,             # 6. ADX趋势强度
    "BOLL": 4,            # 7. 布林带位置
    
    # 维度 2: 基本面 (共 40分)
    "ROE": 6,             # 8. ROE水平
    "PROFIT_GROWTH": 6,   # 9. 净利润增速
    "PEG": 6,             # 10. PEG估值性价比
    "GROSS_MARGIN": 4,    # 11. 毛利率趋势
    "ROIC": 6,            # 12. ROIC资本回报
    "FCF": 4,             # 13. FCF自由现金流
    "INDUSTRY_RANK": 4,   # 14. 行业地位
    "PE_PERCENTILE": 4,   # 15. PE历史分位
    
    # 维度 3: 资金面 (共 30分)
    "NORTH_MONEY": 10,    # 16. 北向资金
    "MARGIN_TRADE": 5,    # 17. 融资融券
    "TURNOVER": 5,        # 18. 换手率
    "MAIN_MONEY": 10      # 19. 主力资金流
}
