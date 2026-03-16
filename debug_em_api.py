import requests

def fetch_em_board():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "50",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "dpt": "app.mkt",
        "fs": "m:90 t:2+f:!50",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,f140,f141,f207,f208,f209,f222"
    }
    # Pretend to be a browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        items = data.get("data", {}).get("diff", [])
        print("Success! Got", len(items), "items.")
        
        # Parse output
        sectors = []
        for item in items[:3]: # top 3
            sectors.append({
                "name": item.get('f14', ''),
                "pct_change": item.get('f3', 0),
                "up_count": item.get('f104', 0), 
                "leader": item.get('f128', ''), 
                "leader_pct": item.get('f136', 0)
            })
        print(sectors)
        
    except Exception as e:
        print("Failed:", e)

fetch_em_board()
