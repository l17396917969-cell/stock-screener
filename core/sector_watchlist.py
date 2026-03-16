import json
import os
import logging
import threading

logger = logging.getLogger(__name__)

WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'sector_watchlist.json')

class SectorWatchlistManager:
    def __init__(self, file_path=WATCHLIST_FILE):
        self.file_path = file_path
        self._lock = threading.Lock()
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self._sectors = self._load()

    def _load(self):
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load sector watchlist: {e}")
            return []

    def _save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self._sectors, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sector watchlist: {e}")

    def get_all(self):
        with self._lock:
            return list(self._sectors)

    def add_sector(self, sector_name: str) -> bool:
        with self._lock:
            if sector_name and sector_name not in self._sectors:
                self._sectors.append(sector_name)
                self._save()
                return True
            return False

    def remove_sector(self, sector_name: str) -> bool:
        with self._lock:
            if sector_name in self._sectors:
                self._sectors.remove(sector_name)
                self._save()
                return True
            return False

sector_watchlist_db = SectorWatchlistManager()
