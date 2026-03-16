from flask_login import UserMixin
from .db import get_db
import time

class User(UserMixin):
    def __init__(self, user_id, username, is_admin=False, is_active=True, must_change_password=False):
        self.id = user_id
        self.username = username
        self.is_admin = bool(is_admin)
        self._is_active = bool(is_active)
        self.must_change_password = bool(must_change_password)

    @property
    def is_active(self):
        return self._is_active

    @staticmethod
    def get(user_id):
        db = get_db()
        user = db.execute(
            "SELECT id, username, is_admin, is_active, must_change_password FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if user:
            return User(user['id'], user['username'], user['is_admin'], user['is_active'], user['must_change_password'])
        return None

    @staticmethod
    def find_by_username(username):
        db = get_db()
        user = db.execute(
            "SELECT id, username, is_admin, is_active, must_change_password FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if user:
            return User(user['id'], user['username'], user['is_admin'], user['is_active'], user['must_change_password'])
        return None
