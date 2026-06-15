"""评分缓存 SQLite 存储层

替代 scored_stocks.json，提供：
- upsert_score: 写入/更新单只股票评分
- get_by_sector: 按板块查询（模糊匹配）
- get_by_code: 按代码精确查
- get_all: 全量查询（支持排序/分页/搜索）
- count: 统计条数

数据文件: /opt/stock-screener-shared/scores.db
"""

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

SHARED_DIR = os.environ.get("STOCK_SHARED_DIR", "/opt/stock-screener-shared")
DB_PATH = os.path.join(SHARED_DIR, "scores.db")

_INIT_DONE = False


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def _conn(write: bool = False):
    """获取 scores.db 连接，自动关闭。"""
    global _INIT_DONE
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if write:
        conn.execute("PRAGMA busy_timeout=5000")
    if not _INIT_DONE:
        _init_table(conn)
        _INIT_DONE = True
    try:
        yield conn
    finally:
        conn.close()


def _init_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scored_stocks (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            passed      INTEGER NOT NULL DEFAULT 0,
            score       INTEGER NOT NULL DEFAULT 0,
            pe          REAL NOT NULL DEFAULT 0,
            pb          REAL NOT NULL DEFAULT 0,
            roe         REAL NOT NULL DEFAULT 0,
            mcap        REAL NOT NULL DEFAULT 0,
            sector      TEXT NOT NULL DEFAULT '',
            reason      TEXT NOT NULL DEFAULT '',
            scored_at   TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scores_sector ON scored_stocks(sector)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scores_score  ON scored_stocks(score DESC)
    """)
    conn.commit()
    logger.info(f"scores.db ready at {DB_PATH}")


# ── CRUD ─────────────────────────────────────────────────

def upsert_score(data: dict) -> bool:
    """写入/更新单只股票评分。data 需包含 code 字段。"""
    code = data.get("code", "")
    if not code:
        return False
    try:
        with _conn(write=True) as db:
            db.execute(
                """INSERT OR REPLACE INTO scored_stocks
                   (code, name, passed, score, pe, pb, roe, mcap, sector, reason, scored_at, details_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    code,
                    data.get("name", ""),
                    int(data.get("passed", False)),
                    int(data.get("score", 0)),
                    float(data.get("pe", 0)),
                    float(data.get("pb", 0)),
                    float(data.get("roe", 0)),
                    float(data.get("mcap", 0)),
                    data.get("sector", ""),
                    data.get("reason", ""),
                    data.get("scored_at", time.strftime("%Y-%m-%d %H:%M:%S")),
                    data.get("details_json", "{}"),
                ),
            )
            db.commit()
        return True
    except Exception:
        logger.exception(f"upsert_score failed for {code}")
        return False


def upsert_batch(rows: list[dict]) -> int:
    """批量写入评分。返回成功条数。"""
    if not rows:
        return 0
    count = 0
    try:
        with _conn(write=True) as db:
            db.execute("BEGIN")
            for data in rows:
                db.execute(
                    """INSERT OR REPLACE INTO scored_stocks
                       (code, name, passed, score, pe, pb, roe, mcap, sector, reason, scored_at, details_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        data.get("code", ""),
                        data.get("name", ""),
                        int(data.get("passed", False)),
                        int(data.get("score", 0)),
                        float(data.get("pe", 0)),
                        float(data.get("pb", 0)),
                        float(data.get("roe", 0)),
                        float(data.get("mcap", 0)),
                        data.get("sector", ""),
                        data.get("reason", ""),
                        data.get("scored_at", ""),
                        data.get("details_json", "{}"),
                    ),
                )
                count += 1
            db.commit()
    except Exception:
        logger.exception(f"upsert_batch failed after {count}")
    return count


def get_by_code(code: str) -> dict | None:
    """按股票代码精确查询。"""
    try:
        with _conn() as db:
            row = db.execute("SELECT * FROM scored_stocks WHERE code = ?", (code,)).fetchone()
            return dict(row) if row else None
    except Exception:
        logger.exception(f"get_by_code failed: {code}")
        return None


def get_by_sector(sector: str, limit: int = 50) -> list[dict]:
    """按板块模糊查询 (LIKE %sector%)，按 score DESC 排序。"""
    try:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM scored_stocks WHERE sector LIKE ? ORDER BY score DESC LIMIT ?",
                (f"%{sector}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        logger.exception(f"get_by_sector failed: {sector}")
        return []


def get_all(
    search: str = "",
    sector: str = "",
    sort_by: str = "score",
    sort_dir: str = "DESC",
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """全量查询，支持搜索/筛选/排序/分页。

    Returns:
        (rows, total_count)
    """
    try:
        with _conn() as db:
            where_clauses = []
            params = []

            if search:
                where_clauses.append("(code LIKE ? OR name LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            if sector:
                where_clauses.append("sector LIKE ?")
                params.append(f"%{sector}%")

            where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # 白名单排序列，防注入
            allowed_sort = {"score", "pe", "pb", "roe", "mcap", "scored_at", "name", "code"}
            sort_col = sort_by if sort_by in allowed_sort else "score"
            sort_dir_val = "ASC" if sort_dir.upper() == "ASC" else "DESC"

            # total
            total = db.execute(
                f"SELECT COUNT(*) FROM scored_stocks {where}", params
            ).fetchone()[0]

            # rows
            rows = db.execute(
                f"SELECT * FROM scored_stocks {where} ORDER BY {sort_col} {sort_dir_val} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [dict(r) for r in rows], total
    except Exception:
        logger.exception("get_all failed")
        return [], 0


def count() -> int:
    """返回缓存股票总数。"""
    try:
        with _conn() as db:
            return db.execute("SELECT COUNT(*) FROM scored_stocks").fetchone()[0]
    except Exception:
        return 0


def get_stats() -> dict:
    """统计概览。"""
    try:
        with _conn() as db:
            total = db.execute("SELECT COUNT(*) FROM scored_stocks").fetchone()[0]
            passed = db.execute("SELECT COUNT(*) FROM scored_stocks WHERE passed = 1").fetchone()[0]
            avg_score = db.execute("SELECT AVG(score) FROM scored_stocks").fetchone()[0] or 0
            max_score = db.execute("SELECT MAX(score) FROM scored_stocks").fetchone()[0] or 0
            latest = db.execute(
                "SELECT MAX(scored_at) FROM scored_stocks"
            ).fetchone()[0] or ""
            sectors = db.execute(
                "SELECT sector, COUNT(*) as cnt FROM scored_stocks WHERE sector != '' GROUP BY sector ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            return {
                "total": total,
                "passed": passed,
                "avg_score": round(avg_score, 1),
                "max_score": max_score,
                "latest_scored_at": latest,
                "top_sectors": [{"name": r["sector"], "count": r["cnt"]} for r in sectors],
            }
    except Exception:
        return {"total": 0, "passed": 0, "avg_score": 0, "max_score": 0, "latest_scored_at": "", "top_sectors": []}
