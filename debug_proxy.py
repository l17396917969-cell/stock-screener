import requests
print("Testing Sina board...")
try:
    resp = requests.get("http://vip.stock.finance.sina.com.cn/q/view/new_v_bk_list.php", timeout=5)
    print("Sina Status:", resp.status_code)
except Exception as e:
    print("Sina Error:", e)

print("Testing Xueqiu board...")
try:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    # Get session cookie first
    session = requests.Session()
    session.get('https://xueqiu.com', headers=headers)
    resp = session.get("https://stock.xueqiu.com/v5/stock/plate/list.json?ext=1&order_by=percent&order=desc", headers=headers, timeout=5)
    print("Xueqiu Status:", resp.status_code)
    data = resp.json()
    print("Got", len(data.get('data', {}).get('list', [])), "sectors")
except Exception as e:
    print("Xueqiu Error:", e)
