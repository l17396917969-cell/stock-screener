import sqlite3
import os
import time
from flask import g, current_app

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "app.db")

def get_db():
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    
    # Enable Foreign Keys
    db.execute("PRAGMA foreign_keys = ON")
    
    # Create Tables
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0,
        must_change_password INTEGER DEFAULT 0,
        created_at REAL NOT NULL,
        last_login_at REAL
    );

    CREATE TABLE IF NOT EXISTS user_secrets (
        user_id INTEGER PRIMARY KEY,
        ds_key_enc TEXT,
        gemini_key_enc TEXT,
        updated_at REAL NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS watchlist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        name TEXT,
        sectors_json TEXT,
        added_at REAL NOT NULL,
        entry_price REAL,
        status TEXT DEFAULT 'watched',
        cost_price REAL,
        shares INTEGER,
        last_audit_report_json TEXT,
        last_ai_analysis_md TEXT,
        UNIQUE(user_id, code),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sector_watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        sector_name TEXT NOT NULL,
        created_at REAL NOT NULL,
        UNIQUE(user_id, sector_name),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
