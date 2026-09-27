# db.py - Kết nối SQLite, schema, helper, migration
# Tác giả: MADE BY Bao Huy
# Phụ thuộc: sqlite3 (built-in)
# FIX: fetchone/fetchall trả dict thay vì sqlite3.Row

import os
import json
import time
import sqlite3
import threading
from datetime import datetime

# ============================================================
# BIẾN TOÀN CỤC
# ============================================================

_lock = threading.RLock()
_local = threading.local()
_initialized = False


def _resolve_data_dir():
    """Xác định thư mục dữ liệu."""
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return env_dir
    try:
        import key as keymod
        return getattr(keymod, "DATA_DIR", "./data")
    except Exception:
        return "./data"


DATA_DIR = _resolve_data_dir()
DB_FILE = os.path.join(DATA_DIR, "keyserver.db")


# ============================================================
# TIỆN ÍCH THỜI GIAN
# ============================================================

def now_ms():
    """Trả timestamp mili giây."""
    return int(time.time() * 1000)


def fmt_time(ms):
    """Định dạng mili giây thành chuỗi."""
    if not ms:
        return "-"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def parse_time(s):
    """Chuyển chuỗi thành mili giây."""
    if not s:
        return 0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return 0


# ============================================================
# HELPER CHUYỂN sqlite3.Row → dict
# ============================================================

def _row_to_dict(row):
    """Chuyển sqlite3.Row → dict. None → None."""
    if row is None:
        return None
    try:
        # sqlite3.Row hỗ trợ .keys() và __getitem__ theo tên cột
        return {k: row[k] for k in row.keys()}
    except Exception:
        pass
    try:
        return dict(row)
    except Exception:
        return None


def _rows_to_dicts(rows):
    """Chuyển list[sqlite3.Row] → list[dict]."""
    if not rows:
        return []
    result = []
    for r in rows:
        d = _row_to_dict(r)
        if d is not None:
            result.append(d)
    return result


def _row_get_value(row, default=None):
    """Lấy giá trị cột đầu tiên từ Row hoặc dict."""
    if row is None:
        return default
    try:
        if isinstance(row, dict):
            return next(iter(row.values())) if row else default
        # sqlite3.Row
        return row[0]
    except Exception:
        return default


# ============================================================
# KẾT NỐI
# ============================================================

def _ensure_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        print(f"[DB] Không tạo được thư mục {DATA_DIR}: {e}")


def get_db():
    """Trả connection SQLite cho thread hiện tại."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        _ensure_dir()
        conn = sqlite3.connect(
            DB_FILE,
            check_same_thread=False,
            timeout=30,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA cache_size=-20000")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=134217728")
        except Exception as e:
            print(f"[DB] PRAGMA lỗi: {e}")
        _local.conn = conn
    return conn


def close_db():
    """Đóng connection của thread hiện tại."""
    conn = getattr(_local, "conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


# ============================================================
# TRUY VẤN — TẤT CẢ TRẢ VỀ DICT
# ============================================================

def execute(query, params=()):
    """Thực thi một câu lệnh, trả cursor."""
    with _lock:
        db = get_db()
        cur = db.execute(query, params)
        return cur


def executemany(query, seq):
    """Thực thi nhiều câu lệnh."""
    with _lock:
        db = get_db()
        cur = db.executemany(query, seq)
        return cur


def executescript(script):
    """Chạy script SQL nhiều câu."""
    with _lock:
        db = get_db()
        return db.executescript(script)


def fetchone(query, params=()):
    """Trả một dòng dạng dict hoặc None."""
    db = get_db()
    cur = db.execute(query, params)
    return _row_to_dict(cur.fetchone())


def fetchall(query, params=()):
    """Trả danh sách dòng dạng dict."""
    db = get_db()
    cur = db.execute(query, params)
    return _rows_to_dicts(cur.fetchall())


def fetchvalue(query, params=(), default=None):
    """Trả giá trị cột đầu tiên của dòng đầu tiên."""
    db = get_db()
    cur = db.execute(query, params)
    return _row_get_value(cur.fetchone(), default)


def insert(table, data):
    """Chèn một dict vào table, trả lastrowid."""
    if not data:
        return None
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    cur = execute(query, tuple(data.values()))
    return cur.lastrowid


def insert_or_ignore(table, data):
    """Chèn nếu chưa có."""
    if not data:
        return None
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    query = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
    cur = execute(query, tuple(data.values()))
    return cur.lastrowid


def insert_or_replace(table, data):
    """Chèn hoặc thay thế."""
    if not data:
        return None
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    query = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"
    cur = execute(query, tuple(data.values()))
    return cur.lastrowid


def update(table, data, where, where_params=()):
    """Cập nhật theo điều kiện."""
    if not data:
        return 0
    sets = ", ".join(f"{k} = ?" for k in data.keys())
    query = f"UPDATE {table} SET {sets} WHERE {where}"
    cur = execute(query, tuple(data.values()) + tuple(where_params))
    return cur.rowcount


def delete(table, where, params=()):
    """Xóa theo điều kiện."""
    cur = execute(f"DELETE FROM {table} WHERE {where}", params)
    return cur.rowcount


def upsert(table, data, conflict_cols, update_cols=None):
    """Upsert dựa trên conflict_cols."""
    if not data:
        return None
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    conflict = ", ".join(conflict_cols)
    if update_cols is None:
        update_cols = [c for c in data.keys() if c not in conflict_cols]
    if update_cols:
        update_sql = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        query = (f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
                 f"ON CONFLICT({conflict}) DO UPDATE SET {update_sql}")
    else:
        query = (f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
                 f"ON CONFLICT({conflict}) DO NOTHING")
    cur = execute(query, tuple(data.values()))
    return cur.lastrowid


def row_to_dict(row):
    """Public helper: Row hoặc dict → dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return _row_to_dict(row)


def rows_to_list(rows):
    """Public helper: list[Row] → list[dict]."""
    if not rows:
        return []
    result = []
    for r in rows:
        d = row_to_dict(r)
        if d is not None:
            result.append(d)
    return result


def count(table, where="", params=()):
    query = f"SELECT COUNT(*) AS c FROM {table}"
    if where:
        query += f" WHERE {where}"
    row = fetchone(query, params)
    return row["c"] if row else 0


def exists(table, where, params=()):
    return count(table, where, params) > 0


def paginate(query_base, params, page=1, limit=20):
    """Phân trang đơn giản."""
    page = max(1, int(page))
    limit = max(1, min(int(limit), 200))
    offset = (page - 1) * limit
    total = fetchvalue(
        f"SELECT COUNT(*) FROM ({query_base}) AS sub", params, 0
    )
    rows = fetchall(f"{query_base} LIMIT ? OFFSET ?",
                    tuple(params) + (limit, offset))
    return {
        "items": rows_to_list(rows),
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit if total else 0,
    }


# ============================================================
# SCHEMA
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    owner TEXT,
    user_id TEXT,
    created_by TEXT,
    parent TEXT,
    max_devices INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    blocked INTEGER DEFAULT 0,
    expires_at INTEGER,
    created_at INTEGER,
    signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_keys_user ON keys(user_id);
CREATE INDEX IF NOT EXISTS idx_keys_owner ON keys(owner);
CREATE INDEX IF NOT EXISTS idx_keys_active ON keys(active);
CREATE INDEX IF NOT EXISTS idx_keys_expires ON keys(expires_at);
CREATE INDEX IF NOT EXISTS idx_keys_parent ON keys(parent);
CREATE INDEX IF NOT EXISTS idx_keys_created ON keys(created_at DESC);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT,
    key TEXT,
    ip TEXT,
    user_agent TEXT,
    first_seen INTEGER,
    last_seen INTEGER,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (device_id, key)
);
CREATE INDEX IF NOT EXISTS idx_devices_key ON devices(key);
CREATE INDEX IF NOT EXISTS idx_devices_last ON devices(last_seen DESC);

CREATE TABLE IF NOT EXISTS blocked (
    type TEXT,
    id TEXT,
    key TEXT,
    reason TEXT,
    time INTEGER,
    PRIMARY KEY (type, id)
);
CREATE INDEX IF NOT EXISTS idx_blocked_type ON blocked(type);
CREATE INDEX IF NOT EXISTS idx_blocked_time ON blocked(time DESC);

CREATE TABLE IF NOT EXISTS accounts (
    uid TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    role TEXT DEFAULT 'user',
    active INTEGER DEFAULT 1,
    key TEXT,
    telegram_id TEXT,
    created_at INTEGER,
    last_login INTEGER,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username);
CREATE INDEX IF NOT EXISTS idx_accounts_role ON accounts(role);
CREATE INDEX IF NOT EXISTS idx_accounts_tg ON accounts(telegram_id);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    uid TEXT,
    created_at INTEGER,
    expires_at INTEGER,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_uid ON sessions(uid);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time INTEGER,
    event TEXT,
    data TEXT,
    uid TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(time DESC);
CREATE INDEX IF NOT EXISTS idx_logs_event ON logs(event);
CREATE INDEX IF NOT EXISTS idx_logs_uid ON logs(uid);

CREATE TABLE IF NOT EXISTS ctv (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    max_keys INTEGER DEFAULT 50,
    max_days INTEGER DEFAULT 30,
    keys_created INTEGER DEFAULT 0,
    added_at INTEGER,
    active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ctv_active ON ctv(active);

CREATE TABLE IF NOT EXISTS api_keys (
    hash TEXT PRIMARY KEY,
    name TEXT,
    scopes TEXT,
    role TEXT DEFAULT 'client',
    rate_limit INTEGER DEFAULT 60,
    usage_count INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at INTEGER,
    last_used_at INTEGER,
    preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_apikeys_active ON api_keys(active);
CREATE INDEX IF NOT EXISTS idx_apikeys_name ON api_keys(name);

CREATE TABLE IF NOT EXISTS api_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time INTEGER,
    client TEXT,
    method TEXT,
    path TEXT,
    status INTEGER,
    ip TEXT,
    duration INTEGER
);
CREATE INDEX IF NOT EXISTS idx_apilogs_time ON api_logs(time DESC);
CREATE INDEX IF NOT EXISTS idx_apilogs_client ON api_logs(client);

CREATE TABLE IF NOT EXISTS telegram_users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    first_seen INTEGER,
    last_seen INTEGER,
    notify INTEGER DEFAULT 1,
    blocked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tgusers_last ON telegram_users(last_seen DESC);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db():
    """Khởi tạo schema, chỉ chạy một lần."""
    global _initialized
    if _initialized:
        return
    with _lock:
        db = get_db()
        db.executescript(SCHEMA)
        _initialized = True
        print(f"[DB] Khởi tạo schema tại {DB_FILE}")


def _table_count(table):
    try:
        row = fetchone(f"SELECT COUNT(*) AS c FROM {table}")
        return row["c"] if row else 0
    except Exception:
        return 0


# ============================================================
# MIGRATION TỪ JSON
# ============================================================

def _load_json(name):
    path = os.path.join(DATA_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def migrate_from_json():
    """Chuyển dữ liệu từ JSON cũ sang SQLite."""
    if _table_count("keys") > 0:
        print("[DB] Đã có dữ liệu, bỏ qua migration.")
        return

    keys = _load_json("keys.json")
    devices = _load_json("devices.json")
    accounts = _load_json("accounts.json")
    ctv = _load_json("ctv.json")
    apikeys = _load_json("apikeys.json")

    if not any([keys, devices, accounts, ctv, apikeys]):
        print("[DB] Không có JSON để migrate.")
        return

    print("[DB] Bắt đầu migrate từ JSON...")

    if keys:
        for k, rec in keys.items():
            try:
                insert_or_ignore("keys", {
                    "key": k,
                    "owner": rec.get("owner", ""),
                    "user_id": rec.get("userId"),
                    "created_by": rec.get("createdBy"),
                    "parent": rec.get("parent"),
                    "max_devices": rec.get("maxDevices", 1),
                    "active": 1 if rec.get("active") else 0,
                    "blocked": 1 if rec.get("blocked") else 0,
                    "expires_at": rec.get("expiresAt", 0),
                    "created_at": rec.get("createdAt", now_ms()),
                    "signature": rec.get("signature"),
                })
            except Exception as e:
                print(f"[DB] migrate key lỗi: {e}")

    if devices:
        for k, devs in devices.items():
            for dev_id, info in devs.items():
                try:
                    insert_or_ignore("devices", {
                        "device_id": dev_id,
                        "key": k,
                        "ip": info.get("ip", ""),
                        "user_agent": info.get("userAgent", ""),
                        "first_seen": info.get("firstSeen", 0),
                        "last_seen": info.get("lastSeen", 0),
                        "count": info.get("count", 0),
                    })
                except Exception:
                    pass

    if accounts:
        for uid, rec in accounts.items():
            try:
                insert_or_ignore("accounts", {
                    "uid": uid,
                    "username": rec.get("username", uid),
                    "password_hash": rec.get("passwordHash", ""),
                    "role": rec.get("role", "user"),
                    "active": 1 if rec.get("active", True) else 0,
                    "key": rec.get("key"),
                    "telegram_id": rec.get("telegramId"),
                    "created_at": rec.get("createdAt", now_ms()),
                    "last_login": rec.get("lastLogin"),
                    "ip": rec.get("ip", ""),
                })
            except Exception:
                pass

    if ctv:
        for uid, rec in ctv.items():
            try:
                insert_or_ignore("ctv", {
                    "user_id": uid,
                    "name": rec.get("name", ""),
                    "max_keys": rec.get("maxKeys", 50),
                    "max_days": rec.get("maxDays", 30),
                    "keys_created": rec.get("keysCreated", 0),
                    "added_at": rec.get("addedAt", now_ms()),
                    "active": 1 if rec.get("active", True) else 0,
                })
            except Exception:
                pass

    if apikeys:
        for h, rec in apikeys.items():
            try:
                insert_or_ignore("api_keys", {
                    "hash": h,
                    "name": rec.get("name", ""),
                    "scopes": json.dumps(rec.get("scopes", []), ensure_ascii=False),
                    "role": rec.get("role", "client"),
                    "rate_limit": rec.get("rateLimit", 60),
                    "usage_count": rec.get("usageCount", 0),
                    "active": 1 if rec.get("active", True) else 0,
                    "created_at": rec.get("createdAt", now_ms()),
                    "last_used_at": rec.get("lastUsedAt"),
                    "preview": rec.get("preview", ""),
                })
            except Exception:
                pass

    print("[DB] Migration hoàn tất.")


# ============================================================
# META HELPERS
# ============================================================

def meta_get(key, default=None):
    row = fetchone("SELECT value FROM meta WHERE key = ?", (key,))
    return row["value"] if row else default


def meta_set(key, value):
    upsert("meta", {"key": key, "value": str(value)}, ["key"])


# ============================================================
# VACUUM / BACKUP
# ============================================================

def vacuum():
    try:
        db = get_db()
        db.execute("VACUUM")
        print("[DB] VACUUM hoàn tất.")
    except Exception as e:
        print(f"[DB] VACUUM lỗi: {e}")


def backup_to(path):
    try:
        import shutil
        db = get_db()
        db.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy(DB_FILE, path)
        return True
    except Exception as e:
        print(f"[DB] Backup lỗi: {e}")
        return False


# ============================================================
# TƯƠNG THÍCH NGƯỢC — WRAPPER CHO AI CÒN DÙNG sqlite3.Row
# ============================================================

class RowWrapper(dict):
    """Dict subclass hỗ trợ truy cập index số như Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            try:
                return list(self.values())[key]
            except IndexError:
                raise IndexError(f"Index {key} ngoài phạm vi")
        return super().__getitem__(key)
    
    def keys(self):
        return super().keys()


# ============================================================
# KHỞI TẠO TỰ ĐỘNG KHI IMPORT
# ============================================================

_ensure_dir()
init_db()
try:
    migrate_from_json()
except Exception as e:
    print(f"[DB] migrate lỗi tổng: {e}")
