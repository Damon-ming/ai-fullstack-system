# app-server/src/com/damon/ming/router/account/sql/sessions_sql.py
"""
sessions 表 SQL 语句 —— 会话层（token + device 的唯一组合）。
"""

# ===========================================================================
# DDL
# ===========================================================================

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id     VARCHAR(64)  PRIMARY KEY,
    token          VARCHAR(64)  NOT NULL,
    device_id      VARCHAR(64)  NOT NULL,
    issued_ua_hash VARCHAR(64)  NOT NULL DEFAULT '',
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMP    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_token_device
    ON sessions (token, device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires
    ON sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_token
    ON sessions (token);
CREATE INDEX IF NOT EXISTS idx_sessions_device
    ON sessions (device_id);
"""

# ===========================================================================
# DML
# ===========================================================================

INSERT = """
INSERT INTO sessions (session_id, token, device_id, issued_ua_hash, created_at, expires_at)
VALUES (%s, %s, %s, %s, %s, %s);
"""

EXPIRE_OLD = """
UPDATE sessions SET expires_at = %s
WHERE token = %s AND device_id = %s AND expires_at > %s;
"""

GET = """
SELECT session_id, token, device_id, issued_ua_hash, created_at, expires_at
FROM sessions
WHERE session_id = %s AND expires_at > %s;
"""

GET_ACTIVE = """
SELECT session_id, token, device_id, issued_ua_hash, created_at, expires_at
FROM sessions
WHERE token = %s AND device_id = %s AND expires_at > %s;
"""

REVOKE_BY_TOKEN = """
UPDATE sessions SET expires_at = %s
WHERE token = %s AND expires_at > %s;
"""

REVOKE_BY_DEVICE = """
UPDATE sessions SET expires_at = %s
WHERE device_id = %s AND expires_at > %s;
"""

CLEANUP_EXPIRED = """
DELETE FROM sessions WHERE expires_at <= %s;
"""

GET_ALL = """
SELECT session_id, token, device_id, issued_ua_hash, created_at, expires_at
FROM sessions WHERE expires_at > %s;
"""

COUNT = "SELECT COUNT(*) FROM sessions WHERE expires_at > %s;"
