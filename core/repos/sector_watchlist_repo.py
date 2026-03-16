import time
from ..db import get_db

class SectorWatchlistRepo:
    def get_all(self, user_id):
        db = get_db()
        rows = db.execute(
            "SELECT sector_name FROM sector_watchlist WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,)
        ).fetchall()
        return [row['sector_name'] for row in rows]

    def add_sector(self, user_id, sector_name):
        db = get_db()
        try:
            db.execute(
                "INSERT INTO sector_watchlist (user_id, sector_name, created_at) VALUES (?, ?, ?)",
                (user_id, sector_name, time.time())
            )
            db.commit()
            return True
        except:
            return False

    def remove_sector(self, user_id, sector_name):
        db = get_db()
        db.execute(
            "DELETE FROM sector_watchlist WHERE user_id = ? AND sector_name = ?",
            (user_id, sector_name)
        )
        db.commit()
        return True

sector_watchlist_repo = SectorWatchlistRepo()
