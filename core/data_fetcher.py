import akshare as ak
import yfinance as yf
import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── yfinance 限流控制 ─────────────────────────────────────────
_yf_last_request_time = 0
_yf_rate_limit_seconds = 2.0  # 每次请求间隔2秒，防止被限流
_yf_rate_limited_until = None  # 如果被限流，记录恢复时间

def _yf_rate_limit_wait():
    """确保 yfinance 请求间隔，防止被限流"""
    global _yf_last_request_time, _yf_rate_limited_until
    
    # 检查是否还在限流中
    if _yf_rate_limited_until and datetime.now() < _yf_rate_limited_until:
        wait_seconds = (_yf_rate_limited_until - datetime.now()).total_seconds()
        logger.info(f"yfinance rate limited, waiting {wait_seconds:.1f}s...")
        time.sleep(wait_seconds)
    
    # 确保请求间隔
    now = time.time()
    elapsed = now - _yf_last_request_time
    if elapsed < _yf_rate_limit_seconds:
        time.sleep(_yf_rate_limit_seconds - elapsed)
    
    _yf_last_request_time = time.time()

def _check_yf_rate_limit(error_msg: str) -> bool:
    """检查是否触发限流，如果是设置冷却时间"""
    global _yf_rate_limited_until
    error_lower = error_msg.lower()
    if 'rate limit' in error_lower or 'too many request' in error_lower:
        _yf_rate_limited_until = datetime.now() + timedelta(minutes=5)
        logger.warning("yfinance rate limit detected, cooling down for 5 minutes")
        return True
    return False

# ── 重试装饰器 ────────────────────────────────────────────────
def retry_on_failure(retries=3, delay=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Error in {func.__name__} (attempt {attempt+1}/{retries}): {e}")
                    if attempt < retries - 1:
                        time.sleep(delay)
                    else:
                        logger.error(f"Failed to execute {func.__name__} after {retries} attempts.")
                        return None
        return wrapper
    return decorator

# ── 辅助：将A股代码转换为 yfinance 格式 ──────────────────────
def _to_yf_symbol(code: str) -> str:
    """
    将6位A股代码转为 yfinance ticker。
    沪市(600xxx/601xxx/603xxx/605xxx) → .SS
    深市(000xxx/001xxx/002xxx/003xxx/300xxx/688xxx) → .SZ
    """
    code = str(code).zfill(6)
    if code.startswith(('6', '9')):
        return f"{code}.SS"
    else:
        return f"{code}.SZ"

# ── 全量实时行情（新浪接口，无需 Eastmoney 代理） ─────────────
@retry_on_failure(retries=3, delay=3)
def get_all_stocks_spot():
    """全量A股实时行情 (新浪接口)"""
    logger.info("Fetching real-time A-share spot data (Sina)...")
    df = ak.stock_zh_a_spot()
    if df is not None and len(df) > 2000:
        df['代码'] = df['代码'].astype(str).str.replace(r'^[a-z]+', '', regex=True).str.zfill(6)
        logger.info(f"Successfully fetched {len(df)} spot records.")
        return df
    raise Exception("Failed to fetch complete spot data.")

# ── 板块列表 ───────────────────────────────────────────────────
@retry_on_failure(retries=3)
def get_industry_boards():
    """获取同花顺行业板块数据"""
    logger.info("Fetching industry boards data (THS)...")
    df = ak.stock_board_industry_summary_ths()
    if df is not None and not df.empty:
        df = df.rename(columns={'板块': '板块名称'})
        return df
    return None

# ── 申万行业代码映射 ──────────────────────────────────────────
_SW_SECTOR_MAP = None

def _load_sw_sector_map():
    global _SW_SECTOR_MAP
    if _SW_SECTOR_MAP is None:
        try:
            df = ak.sw_index_second_info()
            _SW_SECTOR_MAP = {row['行业名称']: row['行业代码'] for _, row in df.iterrows()}
            logger.info(f"Loaded {len(_SW_SECTOR_MAP)} SW sector codes.")
        except Exception as e:
            logger.error(f"Failed to load SW sector map: {e}")
            _SW_SECTOR_MAP = {}
    return _SW_SECTOR_MAP

def _fuzzy_match_sw_code(board_name):
    sector_map = _load_sw_sector_map()
    if not sector_map:
        return None
    clean_name = board_name.rstrip('ⅠⅡⅢⅣ').strip()
    for sw_name, code in sector_map.items():
        if clean_name in sw_name or sw_name.rstrip('Ⅱ').strip() in clean_name:
            logger.info(f"Matched '{board_name}' → '{sw_name}' ({code})")
            return code
    logger.warning(f"No SW code match found for board: '{board_name}'")
    return None

@retry_on_failure(retries=3)
def get_board_stocks(board_name):
    """获取指定板块的成分股 (申万行业)"""
    logger.info(f"Fetching stocks for board: {board_name}...")
    sw_code = _fuzzy_match_sw_code(board_name)
    if not sw_code:
        logger.warning(f"Skipping '{board_name}': no matching SW industry code found.")
        return None
    df = ak.sw_index_third_cons(symbol=sw_code)
    if df is not None and not df.empty:
        df = df.rename(columns={'股票代码': '代码', '股票简称': '名称'})
        logger.info(f"Board '{board_name}' ({sw_code}) → {len(df)} stocks")
        return df
    return None

# ── 大盘与热门板块快照 (For AI Sector Analysis) ───────────────

@retry_on_failure(retries=3)
def get_market_overview():
    """获取全市场情绪概况"""
    logger.info("Fetching market overview...")
    try:
        # Fallback to local calculation if akshare fails entirely due to local network proxy
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty: 
            return None
        
        up_count = len(df[df['涨跌额'] > 0])
        down_count = len(df[df['涨跌额'] < 0])
        limit_up = len(df[df['涨跌幅'] >= 9.8])
        limit_down = len(df[df['涨跌幅'] <= -9.8])
        total_amount = df['成交额'].sum() / 1e8  # 亿元
        
        # 指数情况 - suppress errors if index data fails independently
        sh_idx, sz_idx, cy_idx = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        try:
            idx_df = ak.stock_zh_index_spot_em(symbol="上证系列指数")
            sh_idx = idx_df[idx_df['代码'] == '000001'] if not idx_df.empty else pd.DataFrame()
        except: pass
        
        try:
            sz_df = ak.stock_zh_index_spot_em(symbol="深证系列指数")
            sz_idx = sz_df[sz_df['代码'] == '399001'] if not sz_df.empty else pd.DataFrame()
            cy_idx = sz_df[sz_df['代码'] == '399006'] if not sz_df.empty else pd.DataFrame()
        except: pass

        def _format_idx(row):
            if row.empty: return "获取失败"
            return f"{row['最新价'].values[0]} ({row['涨跌幅'].values[0]}%)"

        return {
            "up_count": up_count,
            "down_count": down_count,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "total_amount": round(total_amount, 2),
            "sh_index": _format_idx(sh_idx),
            "sz_index": _format_idx(sz_idx),
            "cy_index": _format_idx(cy_idx)
        }
    except Exception as e:
        logger.error(f"Market overview failed: {e}")
        return None

@retry_on_failure(retries=3)
def get_sector_snapshot():
    """获取热门板块快照 (Top 20 涨幅榜)"""
    logger.info("Fetching sector snapshot...")
    try:
        # 尝试通过新浪接口获取行业板块行情 (绕过东方财富可能出现的连接重置)
        df = ak.stock_board_industry_summary_ths() # 同花顺备用
        if df is None or df.empty: 
            df = ak.stock_board_industry_name_em()
            
        if df is None or df.empty: 
            return None
            
        # Unified column names across variants
        pct_col = '涨跌幅' if '涨跌幅' in df.columns else '涨跌幅'
        name_col = '板块' if '板块' in df.columns else '板块名称'
        
        df_sorted = df.sort_values(by=pct_col, ascending=False).head(20)
        
        sectors_data = []
        for _, row in df_sorted.iterrows():
            sectors_data.append({
                "name": row[name_col],
                "pct_change": row[pct_col],
                "up_count": row.get('上涨家数', 0),
                "leader": row.get('领涨股票', '无'),
                "leader_pct": row.get('领涨股票-涨跌幅', 0)
            })
        return sectors_data
    except Exception as e:
        logger.error(f"Sector snapshot failed: {e}")
        return None


# ── 指标计算工具 (Technical Indicators) ────────────────────────

def calculate_adx(df, period=14):
    """计算 14 日 ADX (趋向指标)"""
    if len(df) < 2 * period: return 0
    df = df.copy()
    df['tr'] = np.maximum(df['High'] - df['Low'], 
                          np.maximum(abs(df['High'] - df['Close'].shift(1)), 
                                     abs(df['Low'] - df['Close'].shift(1))))
    df['dm_plus'] = np.where((df['High'] - df['High'].shift(1)) > (df['Low'].shift(1) - df['Low']),
                             np.maximum(df['High'] - df['High'].shift(1), 0), 0)
    df['dm_minus'] = np.where((df['Low'].shift(1) - df['Low']) > (df['High'] - df['High'].shift(1)),
                              np.maximum(df['Low'].shift(1) - df['Low'], 0), 0)
    
    tr_smooth = df['tr'].rolling(window=period).sum()
    dm_plus_smooth = df['dm_plus'].rolling(window=period).sum()
    dm_minus_smooth = df['dm_minus'].rolling(window=period).sum()
    
    di_plus = 100 * (dm_plus_smooth / tr_smooth)
    di_minus = 100 * (dm_minus_smooth / tr_smooth)
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
    adx = dx.rolling(window=period).mean()
    return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0

def calculate_bollinger_bands(df, period=20):
    """计算布林带位置 (0: 极度低位, 0.5: 中轴, 1: 极度高位)"""
    if len(df) < period: return 0.5
    close = df['Close']
    ma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    current = close.iloc[-1]
    
    # 返回相对位置 (Percent B)
    if upper.iloc[-1] == lower.iloc[-1]: return 0.5
    pct_b = (current - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
    return float(pct_b)

def calculate_rps(df, index_df, period=20):
    """计算 RPS 相对强度 (个股 20日涨幅 / 指数 20日涨幅)"""
    if len(df) < period or len(index_df) < period: return 1.0
    stock_ret = df['Close'].iloc[-1] / df['Close'].iloc[-period]
    index_ret = index_df['Close'].iloc[-1] / index_df['Close'].iloc[-period]
    return float(stock_ret / index_ret)

def calculate_vcp(df, period=5):
    """计算 VCP 波动对比 (今日振幅 / 近 5日平均振幅)"""
    if len(df) < period + 1: return 1.0
    df = df.copy()
    df['amp'] = (df['High'] - df['Low']) / df['Close'].shift(1)
    today_amp = df['amp'].iloc[-1]
    avg_amp = df['amp'].iloc[-period-1:-1].mean()
    if avg_amp == 0: return 1.0
    return float(today_amp / avg_amp)

def calculate_macd(df, fast=12, slow=26, signal=9):
    """计算 MACD，返回 (MACD线, 信号线, 柱状图状态)"""
    if len(df) < slow + signal: return "N/A"
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    macdp = float(macd_line.iloc[-1])
    sigp = float(signal_line.iloc[-1])
    histp = float(macd_hist.iloc[-1])
    
    if macdp > sigp and histp > 0 and macd_hist.iloc[-2] <= 0:
        return f"MACD零轴{'上' if macdp>0 else '下'}金叉"
    elif macdp < sigp and histp < 0 and macd_hist.iloc[-2] >= 0:
        return f"MACD零轴{'上' if macdp>0 else '下'}死叉"
    elif macdp > sigp:
        return f"MACD多头区(柱状图{'扩大' if histp > macd_hist.iloc[-2] else '缩小'})"
    else:
        return f"MACD空头区(柱状图{'扩大' if histp < macd_hist.iloc[-2] else '缩小'})"

def calculate_kdj(df, n=9, m1=3, m2=3):
    """计算KDJ指标，主要关注J值"""
    if len(df) < n: return "N/A"
    low_list = df['Low'].rolling(window=n, min_periods=1).min()
    high_list = df['High'].rolling(window=n, min_periods=1).max()
    rsv = (df['Close'] - low_list) / (high_list - low_list + 1e-8) * 100
    
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3 * k - 2 * d
    
    jp = float(j.iloc[-1])
    return f"{jp:.1f}"

def calculate_support_resistance(df):
    """提取简单的压力位和支撑位 (20日线，前高等)"""
    if len(df) < 20: return {"support": "N/A", "resistance": "N/A"}
    ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
    high_20d = df['High'].rolling(window=20).max().iloc[-1]
    low_20d = df['Low'].rolling(window=20).min().iloc[-1]
    return {
        "support": f"{ma20:.2f}(20日线), {low_20d:.2f}(前低)",
        "resistance": f"{high_20d:.2f}(前高)"
    }


def get_money_flow_data(code: str) -> dict:
    """获取资金面真实数据 (主力流向、北向历史等，包含短线研判所需的5日均值)"""
    flow_data = {
        "main_net_in": None,       # 今日主力净流入 (万元)
        "main_net_in_5d": None,    # 近5日主力净流入累计 (万元)
        "hsgt_hold_change": None,  # 北向持股市值变化 (万元)
        "hsgt_net_in_5d": None     # 北向近5日净流入 (暂无直接接口，尽量用持股变化代理)
    }
    
    # 1. 主力资金流向 (今日 + 近5日累计)
    try:
        market = "sh" if str(code).startswith(('6', '9')) else "sz"
        df1 = ak.stock_individual_fund_flow(stock=str(code), market=market)
        if df1 is not None and not df1.empty:
            col_name = "主力净流入-净额"
            if col_name in df1.columns:
                # 东方财富接口返回的是“元”，提示词要求“万元”
                latest_inflow = float(df1[col_name].iloc[-1]) / 10000.0
                flow_data["main_net_in"] = latest_inflow
                
                # 计算近5日累计
                if len(df1) >= 5:
                    inflow_5d = df1[col_name].iloc[-5:].sum() / 10000.0
                    flow_data["main_net_in_5d"] = float(inflow_5d)
                else:
                    flow_data["main_net_in_5d"] = float(df1[col_name].sum() / 10000.0)
    except Exception as e:
        logger.debug(f"Fund flow fetch error for {code}: {e}")
        
    # 2. 北向资金 (陆股通历史)
    try:
        df2 = ak.stock_hsgt_individual_em(symbol=str(code))
        if df2 is not None and not df2.empty:
            col_name = "今日持股市值变化"
            if col_name in df2.columns:
                # 换算成万元
                flow_data["hsgt_hold_change"] = float(df2[col_name].iloc[-1]) / 10000.0
                
                # 尝试代理计算近5日市值变化总和作为流入近似
                if len(df2) >= 5:
                    change_5d = df2[col_name].iloc[-5:].sum() / 10000.0
                    flow_data["hsgt_net_in_5d"] = float(change_5d)
    except Exception as e:
        logger.debug(f"HSGT fetch error for {code}: {e}")
        
    return flow_data

# ── yfinance 核心财务&技术数据 ────────────────────────────────

@retry_on_failure(retries=2)
def get_index_data(symbol="000001.SS"):
    """获取指数数据用于 RPS 计算"""
    _yf_rate_limit_wait()  # 添加限流等待
    t = yf.Ticker(symbol)
    return t.history(period="1mo")

def get_stock_data_yf(code: str, index_hist=None) -> dict | None:
    """
    通过 yfinance 获取单只股票 19 个指标所需的原始数据，并计算部分技术指标。
    """
    _yf_rate_limit_wait()  # 添加限流等待，避免被限流
    
    ticker = _to_yf_symbol(code)
    try:
        t = yf.Ticker(ticker)
        
        # 先检查是否被限流
        try:
            info = t.info or {}
        except Exception as e:
            if _check_yf_rate_limit(str(e)):
                return None
            raise

        # 始终优先获取 K线历史，若 K线不足 60 天则放弃
        try:
            hist = t.history(period="1y") 
        except Exception as e:
            if _check_yf_rate_limit(str(e)):
                return None
            logger.debug(f"{code} hist fetch error: {e}")
            return None
            
        if hist is None or len(hist) < 60:
            logger.debug(f"{code} hist is None or too short: {len(hist) if hist is not None else 0}")
            return None

        # 计算技术指标
        ma5 = hist['Close'].rolling(5).mean().iloc[-1]
        ma10 = hist['Close'].rolling(10).mean().iloc[-1]
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        ma60 = hist['Close'].rolling(60).mean().iloc[-1]
        
        # 今日数据 (增强鲁棒性，yfinance有时拿不到 currentPrice)
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or float(hist['Close'].iloc[-1])
        vwap_approx = (float(hist['High'].iloc[-1]) + float(hist['Low'].iloc[-1]) + float(hist['Close'].iloc[-1])) / 3
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
        
        # 量比计算：今日成交量 / 过去5日平均成交量
        vol_today = hist['Volume'].iloc[-1]
        vol_5d_avg = hist['Volume'].iloc[-6:-1].mean() if len(hist) > 5 else vol_today
        volume_ratio = vol_today / vol_5d_avg if vol_5d_avg and vol_5d_avg > 0 else 1.0
        
        # 尝试通过 Akshare 获取准确的中文名称
        stock_name = code
        try:
            spot_df = ak.stock_zh_a_spot_em()
            match = spot_df[spot_df['代码'] == code]
            if not match.empty:
                stock_name = match.iloc[0]['名称']
            else:
                stock_name = info.get("shortName") or info.get("longName") or code
        except:
            stock_name = info.get("shortName") or info.get("longName") or code

        return {
            "code": code,
            "ticker": ticker,
            "name": stock_name,
            
            # 基础数据
            "price": current_price,
            "prev_close": prev_close,
            "high": hist['High'].iloc[-1],
            "low": hist['Low'].iloc[-1],
            "volume": vol_today / 100, # 转换为手
            "amount": (vol_today * vwap_approx) / 10000, # 转换为万元 (近似)
            "change_pct": ((current_price - prev_close) / prev_close) * 100 if prev_close else 0,
            
            "market_cap": info.get("marketCap"),
            "pe_ttm": info.get("trailingPE"),
            "turnover_rate": info.get("floatShares") and (vol_today / info.get("floatShares") * 100),
            "volume_ratio": volume_ratio,
            
            # ... 基本面与技术面保持不变
            "roe": info.get("returnOnEquity"),
            "roic": info.get("returnOnAssets"), 
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "gross_margin": info.get("grossMargins"),
            "fcf": info.get("freeCashflow"),
            "operating_cashflow": info.get("operatingCashflow"),
            
            "ma": {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60},
            "vwap": vwap_approx,
            "adx": calculate_adx(hist),
            "boll_pct_b": calculate_bollinger_bands(hist),
            "vcp_ratio": calculate_vcp(hist),
            "rps": calculate_rps(hist, index_hist) if index_hist is not None else 1.0,
            
            # Additional Indicators for DeepSeek short-term AI
            "macd_status": calculate_macd(hist),
            "kdj_j": calculate_kdj(hist),
            "sr_levels": calculate_support_resistance(hist),
            

            # 资金面 API 真实数据
            "money_flow": get_money_flow_data(code),
            # 历史数据保留以供后续更复杂的计算
            "hist": hist
        }
    except Exception as e:
        import traceback
        logger.error(f"yfinance error for {code}:\n{traceback.format_exc()}")
        return None
