# app-server/src/com/damon/ming/router/encryption/encryption_sql.py
"""
加密会话 SQL 语句 —— encryption_sessions 表的全部 DML + DDL。

本文件只包含 SQL 字符串常量，零业务逻辑，便于查阅和维护。

表结构：
  encryption_sessions (
    key_id       VARCHAR(64)  PRIMARY KEY,
    aes_key_enc  TEXT         NOT NULL,  -- KEK 加密后的 AES 密钥 (base64)
    session_id   VARCHAR(128) NOT NULL DEFAULT '',  -- 业务字段：会话标识（关联 sessions 表）
    created_at   TIMESTAMP    NOT NULL,
    expires_at   TIMESTAMP    NOT NULL
  )

安全说明：
  - aes_key_enc 是 KEK 加密后的密文，DB 泄露不会直接暴露 AES 密钥
  - KEK 从 MASTER_KEY 环境变量派生，不落盘
"""

# ===========================================================================
# DDL — 建表语句
# ===========================================================================

DDL_ENCRYPTION_SESSIONS = """
CREATE TABLE IF NOT EXISTS encryption_sessions (
    key_id       VARCHAR(64)  PRIMARY KEY,
    aes_key_enc  TEXT         NOT NULL,
    session_id   VARCHAR(128) NOT NULL DEFAULT '',
    created_at   TIMESTAMP    NOT NULL,
    expires_at   TIMESTAMP    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enc_sessions_session_id ON encryption_sessions (session_id);
CREATE INDEX IF NOT EXISTS idx_enc_sessions_expires ON encryption_sessions (expires_at);
"""

# ===========================================================================
# DML — 数据操作
# ===========================================================================

SAVE_OR_UPDATE = """
INSERT INTO encryption_sessions (key_id, aes_key_enc, session_id, created_at, expires_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (key_id) DO UPDATE SET
    aes_key_enc = EXCLUDED.aes_key_enc,
    session_id  = EXCLUDED.session_id,
    created_at  = EXCLUDED.created_at,
    expires_at  = EXCLUDED.expires_at;
"""

GET_BY_KEY = """
SELECT key_id, aes_key_enc, session_id, created_at, expires_at
FROM encryption_sessions
WHERE key_id = %s AND expires_at > NOW();
"""

DELETE_BY_KEY = """
DELETE FROM encryption_sessions WHERE key_id = %s;
"""

DELETE_BY_SESSION = """
DELETE FROM encryption_sessions WHERE session_id = %s;
"""

CLEANUP_EXPIRED = """
DELETE FROM encryption_sessions WHERE expires_at <= NOW();
"""

COUNT = """
SELECT COUNT(*) FROM encryption_sessions;
"""

GET_BINDING = """
SELECT session_id FROM encryption_sessions WHERE key_id = %s;
"""

BIND_SESSION = """
UPDATE encryption_sessions SET session_id = %s WHERE key_id = %s;
"""
