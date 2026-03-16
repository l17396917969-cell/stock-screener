import yfinance as yf
import logging

logging.basicConfig(level=logging.DEBUG)
t = yf.Ticker("000400.SZ")
hist = t.history(period="1y")
print(hist)
