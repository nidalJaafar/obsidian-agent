import sqlite3

from core.config import get_setting

import psycopg


class SQLiteHistoryStore:
    def __init__(self, path):
        self._path = path
        self._ensure_schema()

    def append_message(self, session_id, role, content):
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (session_id, role, content),
            )
            conn.commit()

    def get_messages(self, session_id, limit=200, offset=0):
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC LIMIT ?
                OFFSET ?
                """,
                (session_id, limit, offset),
            )
            return cursor.fetchall()

    def get_recent_messages(self, session_id, limit=200):
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit),
            )
            rows = cursor.fetchall()
        return list(reversed(rows))

    def list_sessions(self, limit=100, offset=0):
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    session_id,
                    MIN(created_at) AS started_at,
                    MAX(created_at) AS last_at,
                    (
                        SELECT content
                        FROM chat_messages m2
                        WHERE m2.session_id = m1.session_id
                            AND m2.role = 'user'
                        ORDER BY id ASC
                        LIMIT 1
                    ) AS title
                FROM chat_messages m1
                GROUP BY session_id
                ORDER BY last_at DESC LIMIT ?
                OFFSET ?
                """,
                (limit, offset),
            )
            return cursor.fetchall()

    def _ensure_schema(self):
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
               CREATE TABLE
                    IF NOT EXISTS chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id "
                "ON chat_messages (session_id, id)"
            )
            conn.commit()


class PostgresHistoryStore:
    def __init__(self, dsn):
        self._dsn = dsn
        self._ensure_schema()

    def append_message(self, session_id, role, content):
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO chat_messages (session_id, role, content)
                    VALUES (%s, %s, %s)
                    """,
                    (session_id, role, content),
                )
                conn.commit()

    def get_messages(self, session_id, limit=200, offset=0):
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY id ASC
                        LIMIT %s
                    OFFSET %s
                    """,
                    (session_id, limit, offset),
                )
                return cursor.fetchall()

    def get_recent_messages(self, session_id, limit=200):
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                rows = cursor.fetchall()
        return list(reversed(rows))

    def list_sessions(self, limit=100, offset=0):
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        session_id,
                        MIN(created_at) AS started_at,
                        MAX(created_at) AS last_at,
                        (
                            SELECT content
                            FROM chat_messages m2
                            WHERE m2.session_id = m1.session_id
                                AND m2.role = 'user'
                            ORDER BY id ASC
                            LIMIT 1
                        ) AS title
                    FROM chat_messages m1
                    GROUP BY session_id
                    ORDER BY last_at DESC
                        LIMIT %s
                    OFFSET %s
                    """,
                    (limit, offset),
                )
                return cursor.fetchall()

    def _ensure_schema(self):
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE
                        IF NOT EXISTS chat_messages (
                            id SERIAL PRIMARY KEY,
                            session_id TEXT NOT NULL,
                            role TEXT NOT NULL,
                            content TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW ()
                        )
                    """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id "
                    "ON chat_messages (session_id, id)"
                )
                conn.commit()


def create_history_store():
    store_type = get_setting("history_store", default="sqlite")
    if store_type == "postgres":
        dsn = get_setting("postgres_dsn", required=True)
        return PostgresHistoryStore(dsn)
    if store_type == "sqlite":
        path = get_setting("sqlite_path", default="./chat_history.db")
        return SQLiteHistoryStore(path)
    return None
