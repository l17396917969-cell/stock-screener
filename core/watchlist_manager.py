import os
import json
import logging
from threading import Lock

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_FILE = os.path.join(BASE_DIR, "data", "watchlist.json")

class WatchlistManager:
    def __init__(self, file_path=WATCHLIST_FILE):
        self.file_path = file_path
        self._lock = Lock()
        self._ensure_file()

    def _ensure_file(self):
        """Ensure the watchlist file exists, initializing an empty dict if not."""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)

    def _load(self):
        with self._lock:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading watchlist: {e}")
                return {}

    def _save(self, data):
        with self._lock:
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error saving watchlist: {e}")

    def get_all(self):
        """Returns the full watchlist dict: { "600519": {name, sectors...}, ... }"""
        return self._load()

    def add_stock(self, code, stock_info):
        """Add or update a stock in the watchlist, capturing entry price."""
        data = self._load()
        
        # If stock doesn't exist yet, we initialize holding states and try to fetch entry price
        if code not in data:
            entry_price = None
            try:
                import yfinance as yf
                import pandas as pd
                # Try both suffixes
                suffix = ".SS" if code.startswith("6") else ".SZ"
                symbol = f"{code}{suffix}"
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    entry_price = float(hist['Close'].iloc[-1])
            except Exception as e:
                logger.error(f"Failed to fetch entry price for {code}: {e}")
                
            stock_info['entry_price'] = entry_price
            stock_info['status'] = 'watched' # watched OR holding
            stock_info['cost_price'] = None
            stock_info['shares'] = None
        else:
            # Preserve existing specific fields if we are just re-adding/updating basic info
            existing = data[code]
            stock_info['entry_price'] = existing.get('entry_price')
            stock_info['status'] = existing.get('status', 'watched')
            stock_info['cost_price'] = existing.get('cost_price')
            stock_info['shares'] = existing.get('shares')
            stock_info['last_audit_report'] = existing.get('last_audit_report')
            stock_info['last_ai_analysis'] = existing.get('last_ai_analysis')

        data[code] = stock_info
        self._save(data)

    def update_position(self, code, status, cost_price, shares):
        """Update holding position for a stock."""
        data = self._load()
        if code in data:
            data[code]['status'] = status
            data[code]['cost_price'] = float(cost_price) if cost_price else None
            data[code]['shares'] = int(shares) if shares else None
            self._save(data)
            return True
        return False
        
    def save_audit_report(self, code, report_json):
        """Save the latest quantitative audit report."""
        data = self._load()
        if code in data:
            data[code]['last_audit_report'] = report_json
            self._save(data)
            return True
        return False
        
    def save_ai_analysis(self, code, markdown_content):
        """Save the latest AI analysis."""
        data = self._load()
        if code in data:
            data[code]['last_ai_analysis'] = markdown_content
            self._save(data)
            return True
        return False

    def remove_stock(self, code):
        """Remove a stock from the watchlist"""
        data = self._load()
        if code in data:
            del data[code]
            self._save(data)
            return True
        return False

# Global instance
watchlist_db = WatchlistManager()
