# app-server/src/com/damon/ming/router/account/sql/users_sql.py
"""
users 表 SQL 语句 —— 用户身份层（phone ↔ token）。
"""

# ===========================================================================
# DDL
# ===========================================================================

DDL = """
CREATE TABLE IF NOT EXISTS users (
    token       VARCHAR(64)  PRIMARY KEY,
    phone       VARCHAR(32)  NOT NULL UNIQUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);
"""

# ===========================================================================
# DML
# ===========================================================================

INSERT = """
INSERT INTO users (token, phone, created_at)
VALUES (%s, %s, %s)
ON CONFLICT (token) DO UPDATE SET phone = EXCLUDED.phone;
"""

GET_TOKEN_BY_PHONE = """
SELECT token FROM users WHERE phone = %s;
"""

GET_PHONE_BY_TOKEN = """
SELECT phone FROM users WHERE token = %s;
"""

COUNT = "SELECT COUNT(*) FROM users;"
