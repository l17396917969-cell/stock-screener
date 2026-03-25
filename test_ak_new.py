import os
import akshare as ak

os.environ["NO_PROXY"] = "localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.baidu.com,.126.net,.szse.cn,.sse.com.cn,.cninfo.com.cn"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

def test_fund_flow():
    try:
        df = ak.stock_fund_flow_industry(symbol="即时")
        print(df[['行业', '净额', '行业-涨跌幅']].head(5))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_fund_flow()
