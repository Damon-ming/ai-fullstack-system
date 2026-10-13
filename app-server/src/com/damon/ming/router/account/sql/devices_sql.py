# app-server/src/com/damon/ming/router/account/sql/devices_sql.py
"""
devices 表 SQL 语句 —— 设备指纹层（独立于用户存在）。
"""

# ===========================================================================
# DDL
# ===========================================================================

DDL = """
CREATE TABLE IF NOT EXISTS devices (
    device_id   VARCHAR(64)  PRIMARY KEY,
    ua_hash     VARCHAR(64)  NOT NULL,
    raw_ua      TEXT         NOT NULL DEFAULT '',
    platform    VARCHAR(32)  NOT NULL DEFAULT '',
    screen      VARCHAR(16)  NOT NULL DEFAULT '',
    lang        VARCHAR(16)  NOT NULL DEFAULT '',
    tz          VARCHAR(32)  NOT NULL DEFAULT '',
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);
"""

# ===========================================================================
# DML
# ===========================================================================

UPSERT = """
INSERT INTO devices (device_id, ua_hash, raw_ua, platform, screen, lang, tz, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (device_id) DO UPDATE SET
    ua_hash  = EXCLUDED.ua_hash,
    raw_ua   = EXCLUDED.raw_ua,
    platform = EXCLUDED.platform,
    screen   = EXCLUDED.screen,
    lang     = EXCLUDED.lang,
    tz       = EXCLUDED.tz;
"""

GET = """
SELECT device_id, ua_hash, raw_ua, platform, screen, lang, tz, created_at
FROM devices WHERE device_id = %s;
"""

DELETE = """
DELETE FROM devices WHERE device_id = %s;
"""

GET_ALL = """
SELECT device_id, ua_hash, raw_ua, platform, screen, lang, tz, created_at
FROM devices;
"""

COUNT = "SELECT COUNT(*) FROM devices;"
