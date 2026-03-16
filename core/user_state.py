import time
import threading
from threading import Lock

class UserStateManager:
    def __init__(self):
        self._states = {} # { user_id: { "state": {}, "lock": Lock() } }
        self._global_lock = Lock()

    def _get_user_entry(self, user_id):
        with self._global_lock:
            if user_id not in self._states:
                self._states[user_id] = {
                    "state": self._get_initial_state(),
                    "lock": Lock()
                }
            return self._states[user_id]

    def _get_initial_state(self):
        return {
            "step": 0,
            "is_analyzing": False,
            "capital": 10000,
            "error": None,
            "logs": [],
            "ai_sectors": [],
            "ai_reasoning": "",
            "selected_sectors": [],
            "candidate_stocks": [],
            "stock_infos": {},
            "analysis_results": {},
            "batch_progress": {
                "total": 0,
                "current": 0
            }
        }

    def get_state(self, user_id):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            # Return a shallow copy of the state to avoid external modification issues
            return dict(entry["state"])

    def update_state(self, user_id, updates):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            entry["state"].update(updates)

    def reset_state(self, user_id, capital=10000):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            new_state = self._get_initial_state()
            new_state["capital"] = capital
            entry["state"] = new_state

    def emit_log(self, user_id, message, status="info"):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            entry["state"]["logs"].append({
                "time": time.strftime('%H:%M:%S'),
                "msg": message,
                "status": status
            })

    def get_field(self, user_id, field, default=None):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            return entry["state"].get(field, default)

    def set_field(self, user_id, field, value):
        entry = self._get_user_entry(user_id)
        with entry["lock"]:
            entry["state"][field] = value

user_state_manager = UserStateManager()
