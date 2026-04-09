"""SQLite database operations for account, observability, and security events."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import string

from backend.config import DB_PATH


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _with_schema_retry(write_op):
    """Retry once after initializing schema when an observability table is missing."""
    try:
        return write_op()
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "no such table" not in message:
            raise
        init_db()
        return write_op()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _pick_device(*values: str | None) -> str | None:
    for value in values:
        clean = (value or "").strip()
        if clean:
            return clean
    return None


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT UNIQUE NOT NULL,
            tenant_name TEXT NOT NULL,
            admin_username TEXT UNIQUE NOT NULL,
            admin_password_hash TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS phone_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT DEFAULT 'default',
            phone TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT '',
            password_hash TEXT DEFAULT NULL,
            must_change_password INTEGER DEFAULT 1,
            device_a TEXT DEFAULT NULL,
            device_b TEXT DEFAULT NULL,
            balance INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            last_login TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for col, definition in [
        ("tenant_id", "TEXT DEFAULT 'default'"),
        ("display_name", "TEXT DEFAULT ''"),
        ("password_hash", "TEXT DEFAULT NULL"),
        ("must_change_password", "INTEGER DEFAULT 1"),
        ("device_a", "TEXT DEFAULT NULL"),
        ("device_b", "TEXT DEFAULT NULL"),
        ("balance", "INTEGER DEFAULT 0"),
        ("enabled", "INTEGER DEFAULT 1"),
        ("last_login", "TIMESTAMP DEFAULT NULL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE phone_accounts ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass

    legacy_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='auth_keys'"
    ).fetchone()
    if legacy_exists:
        legacy_rows = conn.execute(
            """
            SELECT phone, SUM(balance) AS total_balance,
                   MIN(created_at) AS created_at,
                   GROUP_CONCAT(device_a) AS device_as,
                   GROUP_CONCAT(device_b) AS device_bs
            FROM auth_keys
            WHERE phone IS NOT NULL AND phone != ''
            GROUP BY phone
            """
        ).fetchall()
        for row in legacy_rows:
            phone = row["phone"]
            exists = conn.execute(
                "SELECT id FROM phone_accounts WHERE phone = ?",
                (phone,),
            ).fetchone()
            if exists:
                continue
            device_a = _pick_device(*(row["device_as"] or "").split(","))
            device_b = _pick_device(*(row["device_bs"] or "").split(","))
            if device_b == device_a:
                device_b = None
            conn.execute(
                """
                INSERT INTO phone_accounts
                (phone, balance, device_a, device_b, created_at, must_change_password)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), 1)
                """,
                (phone, row["total_balance"] or 0, device_a, device_b, row["created_at"]),
            )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'draft',
            enabled INTEGER DEFAULT 1,
            avatar TEXT DEFAULT '',
            welcome_message TEXT DEFAULT '',
            input_placeholder TEXT DEFAULT '',
            recommended_questions TEXT DEFAULT '[]',
            prompt_override TEXT DEFAULT '',
            workflow_id TEXT DEFAULT '',
            knowledge_scope TEXT DEFAULT '{}',
            model_override TEXT DEFAULT '{}',
            tool_scope TEXT DEFAULT '[]',
            mcp_servers TEXT DEFAULT '[]',
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, agent_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_user_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, agent_id, phone)
        )
        """
    )
    for col, definition in [
        ("tool_scope", "TEXT DEFAULT '[]'"),
        ("mcp_servers", "TEXT DEFAULT '[]'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            tenant_id TEXT DEFAULT 'default',
            agent_id TEXT DEFAULT '',
            phone TEXT NOT NULL,
            title TEXT DEFAULT '新对话',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN agent_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            tenant_id TEXT DEFAULT 'default',
            agent_id TEXT DEFAULT '',
            phone TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            knowledge_hits TEXT DEFAULT '[]',
            retrieval_trace TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        conn.execute("ALTER TABLE chat_logs ADD COLUMN request_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE chat_logs ADD COLUMN session_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE chat_logs ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE chat_logs ADD COLUMN agent_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE chat_logs ADD COLUMN retrieval_trace TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            tenant_id TEXT DEFAULT 'default',
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            duration_ms INTEGER NOT NULL,
            client_ip TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            cache_status TEXT DEFAULT '',
            model_name TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        conn.execute("ALTER TABLE request_logs ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS guardrail_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            tenant_id TEXT DEFAULT 'default',
            phone TEXT DEFAULT '',
            stage TEXT NOT NULL,
            action TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crawler_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT DEFAULT 'default',
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            status TEXT NOT NULL,
            tier TEXT DEFAULT '',
            items_count INTEGER DEFAULT 0,
            detail TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT DEFAULT 'default',
            name TEXT NOT NULL,
            total_questions INTEGER DEFAULT 0,
            hit_at_1 INTEGER DEFAULT 0,
            hit_at_3 INTEGER DEFAULT 0,
            hit_at_5 INTEGER DEFAULT 0,
            avg_top_score REAL DEFAULT 0,
            detail TEXT DEFAULT '[]',
            config_snapshot TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        conn.execute("ALTER TABLE guardrail_events ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE crawler_runs ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    _ensure_default_tenant(conn)
    conn.commit()
    conn.close()


def _ensure_default_tenant(conn: sqlite3.Connection) -> None:
    """确保平台默认租户存在，避免空库无法启动租户能力。"""
    row = conn.execute(
        "SELECT tenant_id FROM tenants WHERE tenant_id = 'default'"
    ).fetchone()
    if row:
        return
    conn.execute(
        """
        INSERT INTO tenants (tenant_id, tenant_name, admin_username, admin_password_hash, enabled)
        VALUES (?, ?, ?, ?, 1)
        """,
        ("default", "默认租户", "tenant_default", _hash_password("tenant2026")),
    )


def _ensure_phone_row(conn: sqlite3.Connection, phone: str) -> None:
    row = conn.execute("SELECT id FROM phone_accounts WHERE phone = ?", (phone,)).fetchone()
    if row:
        return
    conn.execute(
        "INSERT INTO phone_accounts (phone, balance, must_change_password) VALUES (?, 0, 1)",
        (phone,),
    )


def save_tenant_phone_account(
    *,
    tenant_id: str,
    phone: str,
    display_name: str = "",
    password: str = "",
    enabled: bool = True,
) -> dict:
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM phone_accounts WHERE phone = ?",
        (phone,),
    ).fetchone()
    if existing and existing["tenant_id"] not in {tenant_id, None, ""}:
        conn.close()
        return {"ok": False, "msg": "该手机号已被其他企业占用"}
    if existing:
        params = [tenant_id, display_name.strip(), 1 if enabled else 0]
        sql = "UPDATE phone_accounts SET tenant_id = ?, display_name = ?, enabled = ?"
        if password.strip():
            sql += ", password_hash = ?, must_change_password = 1"
            params.extend([_hash_password(password.strip())])
        sql += " WHERE phone = ?"
        params.append(phone)
        conn.execute(sql, tuple(params))
        conn.commit()
        conn.close()
        return {"ok": True, "msg": f"已更新成员账号 {phone}"}
    conn.execute(
        """
        INSERT INTO phone_accounts (
            tenant_id, phone, display_name, password_hash, must_change_password, enabled, balance
        )
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            tenant_id,
            phone,
            display_name.strip(),
            _hash_password(password.strip()) if password.strip() else None,
            1,
            1 if enabled else 0,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": f"已创建成员账号 {phone}"}


def list_tenant_phone_accounts(tenant_id: str, page: int = 1, per_page: int = 50) -> tuple[list[dict], int]:
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    rows = conn.execute(
        """
        SELECT tenant_id, phone, display_name, enabled, must_change_password, last_login, created_at
        FROM phone_accounts
        WHERE tenant_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (tenant_id, per_page, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM phone_accounts WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()["c"]
    conn.close()
    items = []
    for row in rows:
        items.append(
            {
                "tenant_id": row["tenant_id"],
                "username": row["phone"],
                "display_name": row["display_name"] or "",
                "enabled": bool(row["enabled"]),
                "must_change_password": bool(row["must_change_password"]),
                "last_login": row["last_login"] or "",
                "created_at": row["created_at"] or "",
            }
        )
    return items, total


def _row_to_agent(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    item = dict(row)
    for key, fallback in [
        ("recommended_questions", []),
        ("knowledge_scope", {}),
        ("model_override", {}),
        ("tool_scope", []),
        ("mcp_servers", []),
    ]:
        try:
            item[key] = json.loads(item.get(key) or json.dumps(fallback, ensure_ascii=False))
        except Exception:
            item[key] = fallback
    if isinstance(item.get("model_override"), dict):
        item["model"] = str(item["model_override"].get("model") or "").strip()
    else:
        item["model"] = ""
    item["enabled"] = bool(item.get("enabled", 1))
    item["is_default"] = bool(item.get("is_default", 0))
    return item


def list_agents(tenant_id: str, include_disabled: bool = True) -> list[dict]:
    conn = get_conn()
    sql = """
        SELECT tenant_id, agent_id, name, description, status, enabled, avatar,
               welcome_message, input_placeholder, recommended_questions,
               prompt_override, workflow_id, knowledge_scope, model_override,
               tool_scope, mcp_servers,
               is_default, created_at, updated_at
        FROM agents
        WHERE tenant_id = ?
    """
    params: list = [tenant_id]
    if not include_disabled:
        sql += " AND enabled = 1"
    sql += " ORDER BY is_default DESC, datetime(updated_at) DESC, id DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [_row_to_agent(row) for row in rows if row]


def get_agent(tenant_id: str, agent_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT tenant_id, agent_id, name, description, status, enabled, avatar,
               welcome_message, input_placeholder, recommended_questions,
               prompt_override, workflow_id, knowledge_scope, model_override,
               tool_scope, mcp_servers,
               is_default, created_at, updated_at
        FROM agents
        WHERE tenant_id = ? AND agent_id = ?
        """,
        (tenant_id, agent_id),
    ).fetchone()
    conn.close()
    return _row_to_agent(row)


def save_agent(
    *,
    tenant_id: str,
    agent_id: str = "",
    name: str,
    description: str = "",
    status: str = "draft",
    enabled: bool = True,
    avatar: str = "",
    welcome_message: str = "",
    input_placeholder: str = "",
    recommended_questions: list[str] | None = None,
    prompt_override: str = "",
    workflow_id: str = "",
    knowledge_scope: dict | list | None = None,
    model_override: dict | None = None,
    tool_scope: list[str] | None = None,
    mcp_servers: list[str] | None = None,
    is_default: bool = False,
) -> dict:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("智能体名称不能为空")
    clean_agent_id = str(agent_id or "").strip() or f"agent_{secrets.token_hex(6)}"
    clean_status = "published" if str(status or "").strip() == "published" else "draft"
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM agents WHERE tenant_id = ? AND agent_id = ?",
        (tenant_id, clean_agent_id),
    ).fetchone()
    if is_default:
        conn.execute("UPDATE agents SET is_default = 0 WHERE tenant_id = ?", (tenant_id,))
    payload = (
        tenant_id,
        clean_agent_id,
        clean_name,
        str(description or "").strip(),
        clean_status,
        1 if enabled else 0,
        str(avatar or "").strip(),
        str(welcome_message or "").strip(),
        str(input_placeholder or "").strip(),
        json.dumps(recommended_questions or [], ensure_ascii=False),
        str(prompt_override or ""),
        str(workflow_id or "").strip(),
        json.dumps(knowledge_scope or {}, ensure_ascii=False),
        json.dumps(model_override or {}, ensure_ascii=False),
        json.dumps(tool_scope or [], ensure_ascii=False),
        json.dumps(mcp_servers or [], ensure_ascii=False),
        1 if is_default else 0,
    )
    if existing:
        conn.execute(
            """
            UPDATE agents
            SET name = ?, description = ?, status = ?, enabled = ?, avatar = ?,
                welcome_message = ?, input_placeholder = ?, recommended_questions = ?,
                prompt_override = ?, workflow_id = ?, knowledge_scope = ?,
                model_override = ?, tool_scope = ?, mcp_servers = ?,
                is_default = ?, updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = ? AND agent_id = ?
            """,
            (
                clean_name,
                str(description or "").strip(),
                clean_status,
                1 if enabled else 0,
                str(avatar or "").strip(),
                str(welcome_message or "").strip(),
                str(input_placeholder or "").strip(),
                json.dumps(recommended_questions or [], ensure_ascii=False),
                str(prompt_override or ""),
                str(workflow_id or "").strip(),
                json.dumps(knowledge_scope or {}, ensure_ascii=False),
                json.dumps(model_override or {}, ensure_ascii=False),
                json.dumps(tool_scope or [], ensure_ascii=False),
                json.dumps(mcp_servers or [], ensure_ascii=False),
                1 if is_default else 0,
                tenant_id,
                clean_agent_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO agents (
                tenant_id, agent_id, name, description, status, enabled, avatar,
                welcome_message, input_placeholder, recommended_questions,
                prompt_override, workflow_id, knowledge_scope, model_override,
                tool_scope, mcp_servers, is_default
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    conn.commit()
    conn.close()
    return get_agent(tenant_id, clean_agent_id) or {}


def toggle_agent(*, tenant_id: str, agent_id: str, enabled: bool) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM agents WHERE tenant_id = ? AND agent_id = ?",
        (tenant_id, agent_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "智能体不存在"}
    conn.execute(
        "UPDATE agents SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND agent_id = ?",
        (1 if enabled else 0, tenant_id, agent_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": f"已{'启用' if enabled else '停用'}智能体"}


def delete_agent(*, tenant_id: str, agent_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT is_default FROM agents WHERE tenant_id = ? AND agent_id = ?",
        (tenant_id, agent_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "智能体不存在"}
    conn.execute(
        "DELETE FROM agent_user_bindings WHERE tenant_id = ? AND agent_id = ?",
        (tenant_id, agent_id),
    )
    conn.execute(
        "DELETE FROM agents WHERE tenant_id = ? AND agent_id = ?",
        (tenant_id, agent_id),
    )
    if bool(row["is_default"]):
        next_row = conn.execute(
            """
            SELECT agent_id
            FROM agents
            WHERE tenant_id = ? AND enabled = 1
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if next_row:
            conn.execute(
                "UPDATE agents SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND agent_id = ?",
                (tenant_id, str(next_row["agent_id"] or "").strip()),
            )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "智能体已删除"}


def list_user_agent_bindings(*, tenant_id: str, phone: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT agent_id
        FROM agent_user_bindings
        WHERE tenant_id = ? AND phone = ?
        ORDER BY id ASC
        """,
        (tenant_id, phone),
    ).fetchall()
    conn.close()
    return [str(row["agent_id"] or "").strip() for row in rows if str(row["agent_id"] or "").strip()]


def save_user_agent_bindings(*, tenant_id: str, phone: str, agent_ids: list[str]) -> dict:
    clean_agent_ids = []
    seen: set[str] = set()
    for item in agent_ids or []:
        agent_id = str(item or "").strip()
        if not agent_id or agent_id in seen:
            continue
        clean_agent_ids.append(agent_id)
        seen.add(agent_id)
    conn = get_conn()
    account = conn.execute(
        "SELECT id FROM phone_accounts WHERE tenant_id = ? AND phone = ?",
        (tenant_id, phone),
    ).fetchone()
    if not account:
        conn.close()
        return {"ok": False, "msg": "成员账号不存在"}
    if clean_agent_ids:
        placeholders = ",".join("?" for _ in clean_agent_ids)
        valid_rows = conn.execute(
            f"SELECT agent_id FROM agents WHERE tenant_id = ? AND agent_id IN ({placeholders})",
            (tenant_id, *clean_agent_ids),
        ).fetchall()
        valid_ids = {str(row["agent_id"] or "").strip() for row in valid_rows}
        missing = [item for item in clean_agent_ids if item not in valid_ids]
        if missing:
            conn.close()
            return {"ok": False, "msg": f"智能体不存在: {', '.join(missing)}"}
    conn.execute(
        "DELETE FROM agent_user_bindings WHERE tenant_id = ? AND phone = ?",
        (tenant_id, phone),
    )
    for agent_id in clean_agent_ids:
        conn.execute(
            """
            INSERT INTO agent_user_bindings (tenant_id, agent_id, phone)
            VALUES (?, ?, ?)
            """,
            (tenant_id, agent_id, phone),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "账号智能体绑定已更新", "agent_ids": clean_agent_ids}


def get_default_agent(tenant_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT tenant_id, agent_id, name, description, status, enabled, avatar,
               welcome_message, input_placeholder, recommended_questions,
               prompt_override, workflow_id, knowledge_scope, model_override,
               tool_scope, mcp_servers,
               is_default, created_at, updated_at
        FROM agents
        WHERE tenant_id = ? AND enabled = 1
        ORDER BY is_default DESC, datetime(updated_at) DESC, id DESC
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    conn.close()
    return _row_to_agent(row)


def toggle_tenant_phone_account(*, tenant_id: str, phone: str, enabled: bool) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM phone_accounts WHERE tenant_id = ? AND phone = ?",
        (tenant_id, phone),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "成员账号不存在"}
    conn.execute(
        "UPDATE phone_accounts SET enabled = ? WHERE tenant_id = ? AND phone = ?",
        (1 if enabled else 0, tenant_id, phone),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": f"已{'启用' if enabled else '停用'}成员账号 {phone}"}


def generate_temp_password(phone: str, length: int = 10) -> dict:
    conn = get_conn()
    _ensure_phone_row(conn, phone)
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    conn.execute(
        """
        UPDATE phone_accounts
        SET password_hash = ?, must_change_password = 1
        WHERE phone = ?
        """,
        (_hash_password(password), phone),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "phone": phone, "password": password, "msg": f"已为 {phone} 生成临时密码"}


def verify_phone_login(phone: str, password: str, uuid: str = "") -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM phone_accounts WHERE phone = ? AND enabled = 1",
        (phone,),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "code": 401, "msg": "手机号未开通，请先在后台创建账号并生成密码"}

    password_hash = (row["password_hash"] or "").strip()
    if not password_hash:
        conn.close()
        return {"ok": False, "code": 403, "msg": "该手机号尚未生成初始密码，请联系后台处理"}
    if password_hash != _hash_password(password):
        conn.close()
        return {"ok": False, "code": 403, "msg": "手机号或密码错误"}

    balance = row["balance"] or 0
    must_change = bool(row["must_change_password"])
    display_name = str(row["display_name"] or "").strip()
    conn.execute("UPDATE phone_accounts SET last_login = CURRENT_TIMESTAMP WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "登录成功", "balance": balance, "must_change_password": must_change, "display_name": display_name}


def change_password(phone: str, old_password: str, new_password: str) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM phone_accounts WHERE phone = ? AND enabled = 1", (phone,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "手机号未开通"}
    if (row["password_hash"] or "").strip() != _hash_password(old_password):
        conn.close()
        return {"ok": False, "msg": "旧密码错误"}
    if len(new_password.strip()) < 6:
        conn.close()
        return {"ok": False, "msg": "新密码至少 6 位"}
    conn.execute(
        "UPDATE phone_accounts SET password_hash = ?, must_change_password = 0 WHERE phone = ?",
        (_hash_password(new_password.strip()), phone),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "密码修改成功，请使用新密码登录"}


def check_balance(phone: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT balance FROM phone_accounts WHERE phone = ? AND enabled = 1",
        (phone,),
    ).fetchone()
    conn.close()
    return row["balance"] if row else -1


def deduct_balance(phone: str) -> dict:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT balance FROM phone_accounts WHERE phone = ? AND enabled = 1",
            (phone,),
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return {"ok": False, "msg": "手机号无效"}
        if row["balance"] <= 0:
            conn.rollback()
            conn.close()
            return {"ok": False, "balance": 0, "msg": "余额不足"}
        new_balance = row["balance"] - 1
        conn.execute("UPDATE phone_accounts SET balance = ? WHERE phone = ?", (new_balance, phone))
        conn.commit()
        conn.close()
        return {"ok": True, "balance": new_balance}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"ok": False, "msg": f"扣费失败: {e}"}


def add_balance_by_phone(phone: str, amount: int = 500) -> dict:
    conn = get_conn()
    _ensure_phone_row(conn, phone)
    row = conn.execute("SELECT balance FROM phone_accounts WHERE phone = ?", (phone,)).fetchone()
    new_balance = (row["balance"] or 0) + amount
    conn.execute("UPDATE phone_accounts SET balance = ? WHERE phone = ?", (new_balance, phone))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": f"已为 {phone} 增加 {amount} 次会话，当前余额 {new_balance}", "updated": 1, "balance": new_balance}


def reset_device_binding(phone: str) -> bool:
    conn = get_conn()
    cur = conn.execute("UPDATE phone_accounts SET device_a = NULL, device_b = NULL WHERE phone = ?", (phone,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def get_phone_info(phone: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM phone_accounts WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _normalize_session_title(title: str, fallback: str = "新对话") -> str:
    clean = " ".join(str(title or "").strip().split())
    if not clean:
        return fallback
    return clean[:40]


def create_chat_session(*, phone: str, tenant_id: str = "default", agent_id: str = "", title: str = "新对话") -> dict:
    """创建一个新的会话分组，用于把多轮消息串成一条独立对话。"""
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    if not phone:
        raise ValueError("缺少手机号")
    session_id = f"chat_{secrets.token_hex(8)}"
    clean_title = _normalize_session_title(title)
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO chat_sessions (session_id, tenant_id, agent_id, phone, title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, tenant_id, str(agent_id or "").strip(), phone, clean_title),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT session_id, tenant_id, agent_id, phone, title, created_at, updated_at
        FROM chat_sessions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def touch_chat_session(
    *,
    session_id: str,
    phone: str,
    tenant_id: str = "default",
    agent_id: str = "",
    title_hint: str = "",
) -> None:
    """刷新会话更新时间，并在首问时用问题生成标题。"""
    session_id = str(session_id or "").strip()
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    if not session_id or not phone:
        return
    conn = get_conn()
    row = conn.execute(
        """
        SELECT title
        FROM chat_sessions
        WHERE session_id = ? AND tenant_id = ? AND phone = ? AND agent_id = ?
        """,
        (session_id, tenant_id, phone, str(agent_id or "").strip()),
    ).fetchone()
    if not row:
        conn.close()
        return
    next_title = str(row["title"] or "").strip()
    hint = _normalize_session_title(title_hint, "")
    if hint and next_title in {"", "新对话"}:
        next_title = hint
    conn.execute(
        """
        UPDATE chat_sessions
        SET title = ?, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ? AND tenant_id = ? AND phone = ? AND agent_id = ?
        """,
        (next_title or "新对话", session_id, tenant_id, phone, str(agent_id or "").strip()),
    )
    conn.commit()
    conn.close()


def list_chat_sessions(*, phone: str, tenant_id: str = "default", agent_id: str | None = None, limit: int = 50) -> list[dict]:
    """列出某个用户的会话列表，按最近活跃时间倒序。"""
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    if not phone:
        return []
    conn = get_conn()
    if agent_id is None:
        rows = conn.execute(
            """
            SELECT session_id, tenant_id, agent_id, phone, title, created_at, updated_at
            FROM chat_sessions
            WHERE tenant_id = ? AND phone = ?
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (tenant_id, phone, max(1, int(limit or 1))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT session_id, tenant_id, agent_id, phone, title, created_at, updated_at
            FROM chat_sessions
            WHERE tenant_id = ? AND phone = ? AND agent_id = ?
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (tenant_id, phone, str(agent_id or "").strip(), max(1, int(limit or 1))),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def cleanup_empty_chat_sessions(*, phone: str, tenant_id: str = "default", keep_latest: int = 1) -> int:
    """清理重复的空会话，只保留最近若干个占位新对话。"""
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    keep_latest = max(0, int(keep_latest or 0))
    if not phone:
        return 0
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.session_id, s.title, s.updated_at, COUNT(l.id) AS message_count
        FROM chat_sessions s
        LEFT JOIN chat_logs l ON l.session_id = s.session_id
        WHERE s.tenant_id = ? AND s.phone = ?
        GROUP BY s.session_id, s.title, s.updated_at
        ORDER BY datetime(s.updated_at) DESC, s.id DESC
        """,
        (tenant_id, phone),
    ).fetchall()
    empty_ids: list[str] = []
    for row in rows:
        title = str(row["title"] or "").strip()
        message_count = int(row["message_count"] or 0)
        if message_count == 0 and title in {"", "新对话"}:
            empty_ids.append(str(row["session_id"] or "").strip())
    redundant = [item for item in empty_ids[keep_latest:] if item]
    deleted = 0
    for session_id in redundant:
        cur = conn.execute(
            "DELETE FROM chat_sessions WHERE session_id = ? AND tenant_id = ? AND phone = ?",
            (session_id, tenant_id, phone),
        )
        deleted += cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def list_chat_session_messages(
    *,
    session_id: str,
    phone: str,
    tenant_id: str = "default",
    agent_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """读取某个会话下的完整问答消息。"""
    session_id = str(session_id or "").strip()
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    if not session_id or not phone:
        return []
    conn = get_conn()
    if agent_id is None:
        rows = conn.execute(
            """
            SELECT id, request_id, session_id, tenant_id, agent_id, question, answer, knowledge_hits, retrieval_trace, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ? AND session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (tenant_id, phone, session_id, max(1, int(limit or 1))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, request_id, session_id, tenant_id, agent_id, question, answer, knowledge_hits, retrieval_trace, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ? AND session_id = ? AND agent_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (tenant_id, phone, session_id, str(agent_id or "").strip(), max(1, int(limit or 1))),
        ).fetchall()
    conn.close()
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["knowledge_hits"] = json.loads(item.get("knowledge_hits") or "[]")
        except Exception:
            item["knowledge_hits"] = []
        try:
            item["retrieval_trace"] = json.loads(item.get("retrieval_trace") or "{}")
        except Exception:
            item["retrieval_trace"] = {}
        result.append(item)
    return result


def list_phone_accounts(page=1, per_page=20):
    conn = get_conn()
    offset = (page - 1) * per_page
    rows = conn.execute(
        "SELECT * FROM phone_accounts ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM phone_accounts").fetchone()[0]
    conn.close()
    return [dict(r) for r in rows], total


def record_chat_log(
    phone: str,
    question: str,
    answer: str,
    knowledge_hits: list[dict] | None = None,
    retrieval_trace: dict | None = None,
    tenant_id: str = "default",
    agent_id: str = "",
    request_id: str = "",
    session_id: str = "",
) -> None:
    """写入聊天日志，支持按租户隔离。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO chat_logs (request_id, session_id, tenant_id, agent_id, phone, question, answer, knowledge_hits, retrieval_trace)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            session_id,
            tenant_id,
            str(agent_id or "").strip(),
            phone,
            question,
            answer,
            json.dumps(knowledge_hits or [], ensure_ascii=False),
            json.dumps(retrieval_trace or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    if session_id:
        touch_chat_session(
            session_id=session_id,
            phone=phone,
            tenant_id=tenant_id,
            agent_id=agent_id,
            title_hint=question,
        )


def list_chat_logs(
    page: int = 1,
    per_page: int = 20,
    phone: str = "",
    tenant_id: str | None = None,
    agent_id: str | None = None,
):
    """分页查询聊天日志，可按租户与手机号过滤。"""
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    phone = phone.strip()
    params: list = []
    where_parts: list[str] = []
    if tenant_id:
        where_parts.append("tenant_id = ?")
        params.append(tenant_id)
    if agent_id is not None:
        where_parts.append("agent_id = ?")
        params.append(str(agent_id or "").strip())
    if phone:
        where_parts.append("phone LIKE ?")
        params.append(f"%{phone}%")
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    if where_sql:
        rows = conn.execute(
            """
            SELECT id, request_id, session_id, tenant_id, agent_id, phone, question, answer, knowledge_hits, retrieval_trace, created_at
            FROM chat_logs
            """ + where_sql + """
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, per_page, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM chat_logs " + where_sql,
            tuple(params),
        ).fetchone()["c"]
    else:
        rows = conn.execute(
            """
            SELECT id, request_id, session_id, tenant_id, agent_id, phone, question, answer, knowledge_hits, retrieval_trace, created_at
            FROM chat_logs
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS c FROM chat_logs").fetchone()["c"]
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["knowledge_hits"] = json.loads(item.get("knowledge_hits") or "[]")
        except Exception:
            item["knowledge_hits"] = []
        try:
            item["retrieval_trace"] = json.loads(item.get("retrieval_trace") or "{}")
        except Exception:
            item["retrieval_trace"] = {}
        result.append(item)
    return result, total


def list_recent_chat_pairs(
    *,
    phone: str,
    tenant_id: str = "default",
    agent_id: str | None = None,
    session_id: str = "",
    limit: int = 6,
) -> list[dict]:
    """读取某个用户最近若干轮问答，用于短期记忆。

    只返回问答正文，避免把整个日志分页接口逻辑搬到工作流里。
    """
    phone = str(phone or "").strip()
    tenant_id = str(tenant_id or "default").strip() or "default"
    session_id = str(session_id or "").strip()
    if not phone:
        return []
    conn = get_conn()
    if session_id and agent_id is None:
        rows = conn.execute(
            """
            SELECT question, answer, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ? AND session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tenant_id, phone, session_id, max(1, int(limit or 1))),
        ).fetchall()
    elif session_id:
        rows = conn.execute(
            """
            SELECT question, answer, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ? AND session_id = ? AND agent_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tenant_id, phone, session_id, str(agent_id or "").strip(), max(1, int(limit or 1))),
        ).fetchall()
    elif agent_id is None:
        rows = conn.execute(
            """
            SELECT question, answer, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tenant_id, phone, max(1, int(limit or 1))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT question, answer, created_at
            FROM chat_logs
            WHERE tenant_id = ? AND phone = ? AND agent_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (tenant_id, phone, str(agent_id or "").strip(), max(1, int(limit or 1))),
        ).fetchall()
    conn.close()
    result = []
    for row in reversed(rows):
        result.append(
            {
                "question": str(row["question"] or "").strip(),
                "answer": str(row["answer"] or "").strip(),
                "created_at": str(row["created_at"] or ""),
            }
        )
    return result


def record_request_log(
    request_id: str,
    path: str,
    method: str,
    status_code: int,
    duration_ms: int,
    client_ip: str = "",
    phone: str = "",
    cache_status: str = "",
    model_name: str = "",
    error_message: str = "",
    tenant_id: str = "default",
) -> None:
    """写入请求日志，支持租户维度观测。"""
    def _write():
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO request_logs (
                    request_id, tenant_id, path, method, status_code, duration_ms, client_ip, phone,
                    cache_status, model_name, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    tenant_id,
                    path,
                    method,
                    status_code,
                    duration_ms,
                    client_ip,
                    phone,
                    cache_status,
                    model_name,
                    error_message,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    _with_schema_retry(_write)


def record_guardrail_event(
    request_id: str,
    stage: str,
    action: str,
    rule_name: str,
    detail: str = "",
    phone: str = "",
    tenant_id: str = "default",
) -> None:
    """记录护栏事件，支持租户维度隔离。"""
    def _write():
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO guardrail_events (request_id, tenant_id, phone, stage, action, rule_name, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (request_id, tenant_id, phone, stage, action, rule_name, detail),
            )
            conn.commit()
        finally:
            conn.close()

    _with_schema_retry(_write)


def get_observability_summary(tenant_id: str | None = None) -> dict:
    """读取观测汇总，可按租户隔离。"""
    conn = get_conn()
    req_where = "WHERE created_at >= datetime('now', '-24 hours')"
    req_params: list = []
    guard_where = "WHERE action = 'block' AND created_at >= datetime('now', '-24 hours')"
    guard_params: list = []
    if tenant_id:
        req_where = "WHERE tenant_id = ? AND created_at >= datetime('now', '-24 hours')"
        req_params.append(tenant_id)
        guard_where = "WHERE tenant_id = ? AND action = 'block' AND created_at >= datetime('now', '-24 hours')"
        guard_params.append(tenant_id)
    req_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               AVG(duration_ms) AS avg_duration_ms,
               SUM(CASE WHEN cache_status = 'hit' THEN 1 ELSE 0 END) AS cache_hits,
               SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS server_errors
        FROM request_logs
        """ + req_where,
        tuple(req_params),
    ).fetchone()
    guard_row = conn.execute(
        """
        SELECT COUNT(*) AS blocked
        FROM guardrail_events
        """ + guard_where,
        tuple(guard_params),
    ).fetchone()
    conn.close()
    return {
        "requests_24h": int(req_row["total"] or 0),
        "avg_duration_ms": round(float(req_row["avg_duration_ms"] or 0), 2),
        "cache_hits_24h": int(req_row["cache_hits"] or 0),
        "server_errors_24h": int(req_row["server_errors"] or 0),
        "guardrail_blocks_24h": int(guard_row["blocked"] or 0),
    }


def list_request_logs(page: int = 1, per_page: int = 20, tenant_id: str | None = None):
    """分页查询请求日志，可按租户过滤。"""
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    where_sql = "WHERE tenant_id = ?" if tenant_id else ""
    params = [tenant_id] if tenant_id else []
    rows = conn.execute(
        """
        SELECT * FROM request_logs
        """ + where_sql + """
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM request_logs " + where_sql,
        tuple(params),
    ).fetchone()["c"]
    conn.close()
    return [dict(row) for row in rows], total


def list_guardrail_events(page: int = 1, per_page: int = 20, tenant_id: str | None = None):
    """分页查询护栏事件，可按租户过滤。"""
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    where_sql = "WHERE tenant_id = ?" if tenant_id else ""
    params = [tenant_id] if tenant_id else []
    rows = conn.execute(
        """
        SELECT * FROM guardrail_events
        """ + where_sql + """
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM guardrail_events " + where_sql,
        tuple(params),
    ).fetchone()["c"]
    conn.close()
    return [dict(row) for row in rows], total


def search_by_phone(phone: str) -> list[dict]:
    row = get_phone_info(phone)
    return [row] if row else []


def record_crawler_run(
    source_id: str,
    source_name: str,
    status: str,
    tier: str = "",
    items_count: int = 0,
    detail: str = "",
    tenant_id: str = "default",
) -> None:
    """记录采集任务执行结果，供后台监控使用。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO crawler_runs (tenant_id, source_id, source_name, status, tier, items_count, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, source_id, source_name, status, tier, items_count, detail),
    )
    conn.commit()
    conn.close()


def list_crawler_runs(page: int = 1, per_page: int = 20, tenant_id: str | None = None) -> tuple[list[dict], int]:
    """分页查询采集执行历史。"""
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    params: list = []
    where_sql = ""
    if tenant_id:
        where_sql = "WHERE tenant_id = ?"
        params.append(tenant_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM crawler_runs
        {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset),
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM crawler_runs {where_sql}",
        tuple(params),
    ).fetchone()["c"]
    conn.close()
    return [dict(row) for row in rows], total


def clear_crawler_runs(tenant_id: str | None = None) -> int:
    conn = get_conn()
    try:
        if tenant_id:
            cur = conn.execute("DELETE FROM crawler_runs WHERE tenant_id = ?", (tenant_id,))
        else:
            cur = conn.execute("DELETE FROM crawler_runs")
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def record_evaluation_run(
    *,
    name: str,
    total_questions: int,
    hit_at_1: int,
    hit_at_3: int,
    hit_at_5: int,
    avg_top_score: float,
    detail: list[dict] | None = None,
    config_snapshot: dict | None = None,
    tenant_id: str = "default",
) -> None:
    """记录一次检索评测结果，供后台对比配置效果。"""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO evaluation_runs (
            tenant_id, name, total_questions, hit_at_1, hit_at_3, hit_at_5,
            avg_top_score, detail, config_snapshot
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            name,
            int(total_questions or 0),
            int(hit_at_1 or 0),
            int(hit_at_3 or 0),
            int(hit_at_5 or 0),
            float(avg_top_score or 0),
            json.dumps(detail or [], ensure_ascii=False),
            json.dumps(config_snapshot or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def list_evaluation_runs(page: int = 1, per_page: int = 20, tenant_id: str | None = None) -> tuple[list[dict], int]:
    """分页读取评测记录，支持平台和租户两侧查看。"""
    conn = get_conn()
    offset = (max(page, 1) - 1) * per_page
    where_sql = "WHERE tenant_id = ?" if tenant_id else ""
    params = [tenant_id] if tenant_id else []
    rows = conn.execute(
        """
        SELECT *
        FROM evaluation_runs
        """ + where_sql + """
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM evaluation_runs " + where_sql,
        tuple(params),
    ).fetchone()["c"]
    conn.close()
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["detail"] = json.loads(item.get("detail") or "[]")
        except Exception:
            item["detail"] = []
        try:
            item["config_snapshot"] = json.loads(item.get("config_snapshot") or "{}")
        except Exception:
            item["config_snapshot"] = {}
        result.append(item)
    return result, total


def list_tenants() -> list[dict]:
    """列出租户，用于平台总后台。"""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT tenant_id, tenant_name, admin_username, enabled, created_at
        FROM tenants
        ORDER BY id ASC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_tenant(tenant_id: str, tenant_name: str, admin_username: str, admin_password: str) -> dict:
    """创建租户及其后台管理员。"""
    clean_tenant_id = (tenant_id or "").strip().lower()
    clean_name = (tenant_name or "").strip()
    clean_username = (admin_username or "").strip()
    clean_password = (admin_password or "").strip()
    if not clean_tenant_id or not clean_name or not clean_username or len(clean_password) < 6:
        raise ValueError("租户 ID、名称、管理员账号不能为空，且密码至少 6 位")
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO tenants (tenant_id, tenant_name, admin_username, admin_password_hash, enabled)
            VALUES (?, ?, ?, ?, 1)
            """,
            (clean_tenant_id, clean_name, clean_username, _hash_password(clean_password)),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.close()
        raise ValueError(f"租户创建失败：{exc}") from exc
    conn.close()
    return {
        "tenant_id": clean_tenant_id,
        "tenant_name": clean_name,
        "admin_username": clean_username,
    }


def update_tenant(
    tenant_id: str,
    tenant_name: str,
    admin_username: str,
    enabled: bool,
    admin_password: str = "",
) -> dict:
    """更新租户基础信息，支持重置租户后台密码。"""
    clean_tenant_id = (tenant_id or "").strip().lower()
    clean_name = (tenant_name or "").strip()
    clean_username = (admin_username or "").strip()
    if not clean_tenant_id or not clean_name or not clean_username:
        raise ValueError("租户 ID、名称、管理员账号不能为空")
    conn = get_conn()
    row = conn.execute("SELECT tenant_id FROM tenants WHERE tenant_id = ?", (clean_tenant_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("租户不存在")
    if (admin_password or "").strip():
        conn.execute(
            """
            UPDATE tenants
            SET tenant_name = ?, admin_username = ?, enabled = ?, admin_password_hash = ?
            WHERE tenant_id = ?
            """,
            (clean_name, clean_username, 1 if enabled else 0, _hash_password(admin_password.strip()), clean_tenant_id),
        )
    else:
        conn.execute(
            """
            UPDATE tenants
            SET tenant_name = ?, admin_username = ?, enabled = ?
            WHERE tenant_id = ?
            """,
            (clean_name, clean_username, 1 if enabled else 0, clean_tenant_id),
        )
    conn.commit()
    conn.close()
    return {
        "tenant_id": clean_tenant_id,
        "tenant_name": clean_name,
        "admin_username": clean_username,
        "enabled": enabled,
    }


def verify_tenant_admin(admin_username: str, password: str) -> dict:
    """租户后台登录验证。"""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT tenant_id, tenant_name, admin_username, admin_password_hash, enabled
        FROM tenants
        WHERE admin_username = ?
        """,
        ((admin_username or "").strip(),),
    ).fetchone()
    conn.close()
    if not row or not row["enabled"]:
        return {"ok": False, "msg": "租户管理员不存在或已停用"}
    if (row["admin_password_hash"] or "").strip() != _hash_password(password or ""):
        return {"ok": False, "msg": "账号或密码错误"}
    return {
        "ok": True,
        "tenant_id": row["tenant_id"],
        "tenant_name": row["tenant_name"],
        "admin_username": row["admin_username"],
    }
