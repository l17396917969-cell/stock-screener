import os
import requests

# Fake bad proxy
os.environ['http_proxy'] = 'http://127.0.0.1:11111'
os.environ['https_proxy'] = 'http://127.0.0.1:11111'

os.environ['no_proxy'] = 'localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.126.net'

try:
    res = requests.get('https://quote.eastmoney.com', timeout=5)
    print("Success bypassing proxy for eastmoney. Status:", res.status_code)
except Exception as e:
    print("Failed eastmoney:", e)

try:
    # Google should fail because it goes through the bad proxy
    res = requests.get('https://www.google.com', timeout=3)
    print("Success for Google?")
except Exception as e:
    print("Failed Google (Expected):", type(e).__name__)

