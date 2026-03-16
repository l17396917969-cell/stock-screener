import json
import time
from ..db import get_db

class WatchlistRepo:
    def get_all(self, user_id):
        db = get_db()
        rows = db.execute(
            "SELECT * FROM watchlist_items WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
        
        result = {}
        for row in rows:
            result[row['code']] = {
                "name": row['name'],
                "sectors": json.loads(row['sectors_json']) if row['sectors_json'] else [],
                "added_at": row['added_at'],
                "entry_price": row['entry_price'],
                "status": row['status'],
                "cost_price": row['cost_price'],
                "shares": row['shares'],
                "last_audit_report": json.loads(row['last_audit_report_json']) if row['last_audit_report_json'] else None,
                "last_ai_analysis": row['last_ai_analysis_md']
            }
        return result

    def add_stock(self, user_id, code, stock_info):
        db = get_db()
        
        # Check if already exists to decide on entry price fetch
        existing = db.execute(
            "SELECT id, entry_price FROM watchlist_items WHERE user_id = ? AND code = ?",
            (user_id, code)
        ).fetchone()
        
        entry_price = stock_info.get('entry_price')
        if not existing and entry_price is None:
            # Try a quick fetch if possible, though usually it's better to fetch before calling repo
            pass
            
        sectors_json = json.dumps(stock_info.get('sectors', []))
        
        if existing:
            db.execute(
                "UPDATE watchlist_items SET name = ?, sectors_json = ? WHERE id = ?",
                (stock_info.get('name'), sectors_json, existing['id'])
            )
        else:
            db.execute(
                """INSERT INTO watchlist_items 
                (user_id, code, name, sectors_json, added_at, entry_price, status) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, code, stock_info.get('name'), sectors_json, 
                 stock_info.get('added_at', time.time()), entry_price, 'watched')
            )
        db.commit()

    def remove_stock(self, user_id, code):
        db = get_db()
        db.execute("DELETE FROM watchlist_items WHERE user_id = ? AND code = ?", (user_id, code))
        db.commit()
        return True

    def update_position(self, user_id, code, status, cost_price, shares):
        db = get_db()
        db.execute(
            "UPDATE watchlist_items SET status = ?, cost_price = ?, shares = ? WHERE user_id = ? AND code = ?",
            (status, cost_price, shares, user_id, code)
        )
        db.commit()
        return True

    def save_audit_report(self, user_id, code, report_dict):
        db = get_db()
        db.execute(
            "UPDATE watchlist_items SET last_audit_report_json = ? WHERE user_id = ? AND code = ?",
            (json.dumps(report_dict), user_id, code)
        )
        db.commit()

    def save_ai_analysis(self, user_id, code, markdown):
        db = get_db()
        db.execute(
            "UPDATE watchlist_items SET last_ai_analysis_md = ? WHERE user_id = ? AND code = ?",
            (markdown, user_id, code)
        )
        db.commit()

watchlist_repo = WatchlistRepo()
