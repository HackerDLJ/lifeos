"""Tiny SQLite store: one JSON document holding all problems, tasks and chats."""
import json, sqlite3, threading
from pathlib import Path

_PATH = Path(__file__).parent / "lifeos.db"
_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(_PATH)
    c.execute("create table if not exists kv(k text primary key, v text)")
    return c

def load() -> dict:
    default = {"problems": [], "chat": {}}
    with _lock, _conn() as c:
        row = c.execute("select v from kv where k='state'").fetchone()
    if not row:
        return default
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    problems = data.get("problems", [])
    chat = data.get("chat", {})
    if not isinstance(problems, list):
        problems = []
    if not isinstance(chat, dict):
        chat = {}
    return {"problems": problems, "chat": chat}

def save(state: dict) -> None:
    with _lock, _conn() as c:
        c.execute("insert or replace into kv values('state', ?)", (json.dumps(state),))
