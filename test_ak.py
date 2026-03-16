import akshare as ak
import pandas as pd

try:
    df_market = ak.stock_zh_a_spot_em()
    print("Market shape:", df_market.shape)
    up = len(df_market[df_market['涨跌幅'] > 0])
    down = len(df_market[df_market['涨跌幅'] < 0])
    limit_up = len(df_market[df_market['涨跌幅'] >= 9.8])
    limit_down = len(df_market[df_market['涨跌幅'] <= -9.8])
    amount = df_market['成交额'].sum() / 1e8
    print(f"Up: {up}, Down: {down}, LU: {limit_up}, LD: {limit_down}, Amount: {amount:.2f} 亿")
except Exception as e:
    print("Market error:", e)

try:
    df_board = ak.stock_board_industry_name_em()
    print("Board columns:", df_board.columns.tolist())
    print(df_board.head(3))
except Exception as e:
    print("Board error:", e)

try:
    df_index = ak.stock_zh_index_spot_em(symbol="上证系列指数")
    sh = df_index[df_index['代码'] == '000001']['最新价'].values[0]
    sh_pct = df_index[df_index['代码'] == '000001']['涨跌幅'].values[0]
    print(f"SH: {sh} ({sh_pct}%)")
except Exception as e:
    print("Index error:", e)

