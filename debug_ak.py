import akshare as ak
import logging
logging.basicConfig(level=logging.INFO)

try:
    print("--- Testing stock_board_industry_name_th ---")
    df_board = ak.stock_board_industry_summary_ths()
    print("THS Board head:", df_board.head(2))
except Exception as e:
    print("THS Board error:", getattr(e, 'message', str(e)))

try:
    print("\n--- Testing stock_board_industry_name_em ---")
    df_em = ak.stock_board_industry_name_em()
    print("EM Board head:", df_em.head(2))
except Exception as e:
    print("EM Board error:", getattr(e, 'message', str(e)))
