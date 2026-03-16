import logging
from core.data_fetcher import get_stock_data_yf

logging.basicConfig(level=logging.DEBUG)
print("Testing 000400...")
res = get_stock_data_yf("000400")
print("Result for 000400:", res is not None)
if res is None:
    print("Function returned None")
