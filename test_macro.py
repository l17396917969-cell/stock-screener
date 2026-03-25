import sys
import logging
logging.basicConfig(level=logging.DEBUG)
from core.data_fetcher import get_latest_macro_news, get_sector_fund_flow_top, get_sector_snapshot

print("Testing get_latest_macro_news...")
try:
    news = get_latest_macro_news()
    print("Success:", len(news))
except Exception as e:
    print("Error in news:", e)

print("Testing get_sector_fund_flow_top...")
try:
    flows = get_sector_fund_flow_top()
    print("Success:", len(flows))
except Exception as e:
    print("Error in flows:", e)
