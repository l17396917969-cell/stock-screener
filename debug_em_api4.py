import requests
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime
import os
import sys

# Test via standard urlib
print("Test 1: urllib eastmoney")
try:
    url = "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&dpt=app.mkt&fs=m:90+t:2+f:!50&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,f140,f141,f207,f208,f209,f222"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=context, timeout=5) as response:
        html = response.read()
        data = json.loads(html.decode('utf-8'))
        items = data.get("data", {}).get("diff", [])
        print("Urllib Success! Got items:", len(items))
except Exception as e:
    print("Urllib fail:", e)

