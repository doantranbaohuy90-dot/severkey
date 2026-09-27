# key.py
# Module quản lý key: tạo, xác thực, cây key, thiết bị, block, dylib
# Tài khoản mặc định: baohuy / baohuy

import os
import json
import hmac
import hashlib
import secrets
import time
import threading
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
KEY_FILE = os.path.join(DATA_DIR, "keys.json")
DEVICE_FILE = os.path.join(DATA_DIR, "devices.json")
BLOCK_FILE = os.path.join(DATA_DIR, "blocked.json")
LOG_FILE = os.path.join(DATA_DIR, "logs.json")
TREE_FILE = os.path.join(DATA_DIR, "keytree.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

lock = threading.Lock()

SECRET = os.environ.get("KEY_SECRET", "doi_thanh_bien_moi_truong")
DEFAULT_MAX_DEVICES = int(os.environ.get("DEFAULT_MAX_DEVICES", "1"))
DEFAULT_DAYS = int(os.environ.get("DEFAULT_DAYS", "1"))

ALLOWED_DYLIB_HASHES = set(
    h.strip().lower() for h in os.environ.get("ALLOWED_DYLIB_HASHES", "").split(",") if h.strip()
)
BLOCKED_DYLIB_SIGNATURES = set(
    s.strip().lower() for s in os.environ.get("BLOCKED_DYLIB_SIGNATURES", "").split(",") if s.strip()
)


# ---------------- IO ----------------


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def now_ms():
    return int(time.time() * 1000)


def fmt_time(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_keys():
    return read_json(KEY_FILE, {})


def save_keys(k):
    write_json(KEY_FILE, k)


def load_devices():
    return read_json(DEVICE_FILE, {})


def save_devices(d):
    write_json(DEVICE_FILE, d)


def load_blocked():
    return read_json(BLOCK_FILE, {"keys": {}, "devices": {}})


def save_blocked(b):
    write_json(BLOCK_FILE, b)


def load_tree():
    return read_json(TREE_FILE, {"roots": {}, "nodes": {}})


def save_tree(t):
    write_json(TREE_FILE, t)


def append_log(event, data):
    logs = read_json(LOG_FILE, [])
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": data,
    })
    if len(logs) > 5000:
        logs = logs[-5000:]
    write_json(LOG_FILE, logs)


# ---------------- TIEN ICH ----------------


def generate_key():
    raw = secrets.token_hex(12).upper()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def sign_key(key, expires_at):
    payload = f"{key}|{expires_at}".encode("utf-8")
    return hmac.new(SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def get_days_left(key):
    r = load_keys().get(key)
    if not r:
        return None
    ms = r["expiresAt"] - now_ms()
    return max(0, ms // (24 * 60 * 60 * 1000))


# ---------------- DYLIB ----------------


def check_dylib_list(dylibs):
    blocked, unknown, allowed = [], [], []
    for d in dylibs:
        name = str(d.get("name", "")).lower()
        h = str(d.get("hash", "")).lower()
        is_blocked = any(sig and (sig in name or sig in h) for sig in BLOCKED_DYLIB_SIGNATURES)
        if is_blocked:
            blocked.append({"name": name, "hash": h, "reason": "signature_blocked"})
            continue
        if ALLOWED_DYLIB_HASHES:
            if h in ALLOWED_DYLIB_HASHES:
                allowed.append({"name": name, "hash": h})
            else:
                unknown.append({"name": name, "hash": h})
        else:
            allowed.append({"name": name, "hash": h})
    injected = len(blocked) > 0
    return {
        "ok": not injected and len(unknown) == 0,
        "blocked": blocked, "unknown": unknown, "allowed": allowed,
        "injected": injected,
    }


# ---------------- BLOCK ----------------


def block_device(key, device_id, reason):
    b = load_blocked()
    b.setdefault("devices", {})[device_id] = {"key": key, "reason": reason, "time": now_ms()}
    save_blocked(b)
    append_log("device_block", {"key": key, "device": device_id, "reason": reason})


def unblock_device(device_id):
    b = load_blocked()
    if device_id in b.get("devices", {}):
        del b["devices"][device_id]
        save_blocked(b)
        append_log("device_unblock", {"device": device_id})
        return True
    return False


def block_key(key, reason):
    b = load_blocked()
    b.setdefault("keys", {})[key] = {"reason": reason, "time": now_ms()}
    save_blocked(b)
    append_log("key_block", {"key": key, "reason": reason})


def unblock_key(key):
    b = load_blocked()
    if key in b.get("keys", {}):
        del b["keys"][key]
        save_blocked(b)
        append_log("key_unblock", {"key": key})
        return True
    return False


def is_device_blocked(device_id):
    return device_id in load_blocked().get("devices", {})


def is_key_blocked(key):
    return key in load_blocked().get("keys", {})


# ---------------- CAY KEY ----------------


def add_tree_node(key, parent_key=None, owner=None, meta=None):
    # Thêm key vào cây, parent_key=None nghĩa là gốc
    tree = load_tree()
    node = {
        "key": key,
        "parent": parent_key,
        "owner": owner,
        "createdAt": now_ms(),
        "children": [],
        "meta": meta or {},
    }
    tree.setdefault("nodes", {})[key] = node
    if parent_key and parent_key in tree["nodes"]:
        tree["nodes"][parent_key]["children"].append(key)
    else:
        tree.setdefault("roots", {})[key] = True
    save_tree(tree)
    return node


def remove_tree_node(key):
    # Xóa nút và gán con lên cha
    tree = load_tree()
    nodes = tree.get("nodes", {})
    if key not in nodes:
        return False
    node = nodes[key]
    parent = node.get("parent")
    for child in node.get("children", []):
        if child in nodes:
            nodes[child]["parent"] = parent
            if parent and parent in nodes:
                nodes[parent]["children"].append(child)
            else:
                tree.setdefault("roots", {})[child] = True
    if parent and parent in nodes:
        nodes[parent]["children"] = [c for c in nodes[parent]["children"] if c != key]
    tree.get("roots", {}).pop(key, None)
    del nodes[key]
    save_tree(tree)
    return True


def get_tree():
    return load_tree()


def build_tree_view():
    # Trả về cây dạng nested dict để render
    tree = load_tree()
    nodes = tree.get("nodes", {})
    roots = tree.get("roots", {})

    def build(k):
        node = nodes.get(k, {})
        return {
            "key": k,
            "owner": node.get("owner"),
            "createdAt": node.get("createdAt"),
            "meta": node.get("meta", {}),
            "children": [build(c) for c in node.get("children", []) if c in nodes],
        }

    return [build(k) for k in roots if k in nodes]


def render_tree_text(node_list, prefix="", is_last=True):
    # Sinh text ASCII cho cây
    lines = []
    for i, node in enumerate(node_list):
        last = i == len(node_list) - 1
        branch = "└── " if last else "├── "
        key = node["key"]
        owner = node.get("owner") or "-"
        days = get_days_left(key)
        lines.append(f"{prefix}{branch}{key} [{owner}] {days}d")
        child_prefix = prefix + ("    " if last else "│   ")
        if node.get("children"):
            lines.extend(render_tree_text(node["children"], child_prefix, last))
    return lines


# ---------------- NGHIEP VU KEY ----------------


def create_key(days, owner, max_devices=DEFAULT_MAX_DEVICES, user_id=None, created_by=None,
               account_uid=None, parent_key=None):
    key = generate_key()
    expires_at = now_ms() + days * 24 * 60 * 60 * 1000
    signature = sign_key(key, expires_at)
    keys = load_keys()
    keys[key] = {
        "owner": owner,
        "expiresAt": expires_at,
        "signature": signature,
        "active": True,
        "maxDevices": int(max_devices),
        "createdAt": now_ms(),
        "userId": user_id,
        "createdBy": str(created_by) if created_by else None,
        "accountUid": account_uid,
        "parent": parent_key,
    }
    save_keys(keys)

    # Thêm vào cây key
    add_tree_node(
        key,
        parent_key=parent_key,
        owner=owner,
        meta={
            "userId": user_id,
            "createdBy": str(created_by) if created_by else None,
            "accountUid": account_uid,
            "days": days,
        },
    )

    append_log("key_create", {
        "key": key, "owner": owner, "days": days, "maxDevices": max_devices,
        "userId": user_id, "createdBy": str(created_by) if created_by else None,
        "accountUid": account_uid, "parent": parent_key,
    })
    return key, expires_at, signature


def add_days(key, days):
    keys = load_keys()
    if key not in keys:
        return None
    base = max(keys[key]["expiresAt"], now_ms())
    new_exp = base + days * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_adddays", {"key": key, "days": days, "newExpiresAt": new_exp})
    return new_exp


def set_expiry(key, days_from_now):
    keys = load_keys()
    if key not in keys:
        return None
    new_exp = now_ms() + days_from_now * 24 * 60 * 60 * 1000
    keys[key]["expiresAt"] = new_exp
    keys[key]["signature"] = sign_key(key, new_exp)
    keys[key]["active"] = True
    save_keys(keys)
    append_log("key_setexp", {"key": key, "daysFromNow": days_from_now, "newExpiresAt": new_exp})
    return new_exp


def revoke_key(key):
    keys = load_keys()
    if key not in keys:
        return False
    keys[key]["active"] = False
    save_keys(keys)
    append_log("key_revoke", {"key": key})
    return True


def reset_devices(key):
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    append_log("device_reset", {"key": key})
    return True


def delete_key(key):
    keys = load_keys()
    if key not in keys:
        return False
    user_id = keys[key].get("userId")
    account_uid = keys[key].get("accountUid")
    del keys[key]
    save_keys(keys)
    devices = load_devices()
    if key in devices:
        del devices[key]
        save_devices(devices)
    # Xóa khỏi cây
    remove_tree_node(key)
    append_log("key_delete", {"key": key, "userId": user_id, "accountUid": account_uid})
    return True


def verify_key(key, device_id, ip, user_agent, dylibs=None):
    if is_key_blocked(key):
        append_log("verify_fail", {"key": key, "reason": "key_blocked", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_blocked"}
    if is_device_blocked(device_id):
        append_log("verify_fail", {"key": key, "reason": "device_blocked", "device": device_id, "ip": ip})
        return {"ok": False, "error": "device_blocked"}
    keys = load_keys()
    record = keys.get(key)
    if not record:
        append_log("verify_fail", {"key": key, "reason": "not_found", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_not_found"}
    if not record.get("active"):
        append_log("verify_fail", {"key": key, "reason": "disabled", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_disabled"}
    if now_ms() > record["expiresAt"]:
        append_log("verify_fail", {"key": key, "reason": "expired", "device": device_id, "ip": ip})
        return {"ok": False, "error": "key_expired"}

    dylib_result = None
    if dylibs is not None:
        dylib_result = check_dylib_list(dylibs)
        if dylib_result["injected"]:
            block_device(key, device_id, "dylib_injected")
            append_log("dylib_injected", {"key": key, "device": device_id, "blocked": dylib_result["blocked"]})
            return {"ok": False, "error": "dylib_injected", "detail": dylib_result, "device_blocked": True}
        if dylib_result["unknown"]:
            append_log("dylib_unknown", {"key": key, "device": device_id, "unknown": dylib_result["unknown"]})
            return {"ok": False, "error": "dylib_unknown", "detail": dylib_result}

    devices = load_devices()
    key_devices = devices.get(key, {})
    max_dev = record.get("maxDevices", DEFAULT_MAX_DEVICES)
    if device_id not in key_devices:
        if len(key_devices) >= max_dev:
            append_log("verify_fail", {"key": key, "reason": "device_limit", "device": device_id, "ip": ip})
            return {"ok": False, "error": "device_limit_reached", "maxDevices": max_dev}
        key_devices[device_id] = {
            "firstSeen": now_ms(), "lastSeen": now_ms(), "ip": ip,
            "userAgent": user_agent, "count": 1,
            "dylibHash": [d.get("hash") for d in (dylibs or [])],
        }
    else:
        key_devices[device_id]["lastSeen"] = now_ms()
        key_devices[device_id]["ip"] = ip
        key_devices[device_id]["userAgent"] = user_agent
        key_devices[device_id]["count"] = key_devices[device_id].get("count", 0) + 1
        key_devices[device_id]["dylibHash"] = [d.get("hash") for d in (dylibs or [])]
    devices[key] = key_devices
    save_devices(devices)
    append_log("verify_ok", {"key": key, "device": device_id, "ip": ip})
    remaining_days = (record["expiresAt"] - now_ms()) // (24 * 60 * 60 * 1000)
    return {
        "ok": True, "owner": record["owner"],
        "expiresAt": record["expiresAt"], "expiresAtText": fmt_time(record["expiresAt"]),
        "remainingDays": remaining_days, "signature": record["signature"],
        "devicesUsed": len(key_devices), "maxDevices": max_dev,
        "dylib": dylib_result,
    }


def get_key_info(key):
    kr = load_keys().get(key)
    if not kr:
        return None
    devices = load_devices().get(key, {})
    return {
        "key": key,
        "owner": kr["owner"],
        "active": kr.get("active", False),
        "blocked": is_key_blocked(key),
        "expiresAt": kr["expiresAt"],
        "expiresAtText": fmt_time(kr["expiresAt"]),
        "daysLeft": get_days_left(key),
        "maxDevices": kr.get("maxDevices", DEFAULT_MAX_DEVICES),
        "devicesUsed": len(devices),
        "signature": kr.get("signature"),
        "createdAt": kr.get("createdAt"),
        "createdBy": kr.get("createdBy"),
        "userId": kr.get("userId"),
        "accountUid": kr.get("accountUid"),
        "parent": kr.get("parent"),
    }


def list_keys():
    keys = load_keys()
    devices = load_devices()
    result = []
    for k, v in keys.items():
        result.append({
            "key": k,
            "owner": v["owner"],
            "active": v.get("active", False),
            "blocked": is_key_blocked(k),
            "expiresAt": v["expiresAt"],
            "expiresAtText": fmt_time(v["expiresAt"]),
            "daysLeft": get_days_left(k),
            "maxDevices": v.get("maxDevices", DEFAULT_MAX_DEVICES),
            "devicesUsed": len(devices.get(k, {})),
            "userId": v.get("userId"),
            "createdBy": v.get("createdBy"),
            "accountUid": v.get("accountUid"),
            "parent": v.get("parent"),
        })
    return result
