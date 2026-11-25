"""Parameterized MySQL access. Keep SQL visible for database coursework."""
import os
import re
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")


def schema_files():
    return [BASE / "schema.sql", *sorted((BASE / "migrations").glob("*.sql"))]


def schema_statements(sql):
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [stmt.strip() for stmt in re.split(r";\s*(?:\n|$)", sql) if stmt.strip()]


def initialize_schema():
    """Upgrade the configured database before accepting requests, preserving rows.

    CREATE TABLE IF NOT EXISTS does not add columns to existing tables. Apply
    the column migrations too, including when started directly with uvicorn.
    Keep the connection's database selected instead of the SQL files' default.
    """
    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            for path in schema_files():
                for statement in schema_statements(path.read_text(encoding="utf-8")):
                    if re.match(r"(?:CREATE\s+DATABASE|USE)\b", statement, re.IGNORECASE):
                        continue
                    cursor.execute(statement)
                    if cursor.with_rows:
                        cursor.fetchall()
                connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


def connect():
    host = os.getenv("DB_HOST", "").strip()
    if not host:
        raise ValueError(".env의 DB_HOST에 MySQL 서버 주소를 설정해 주세요.")
    return mysql.connector.connect(
        host=host,
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "instagram_term_2026"),
        charset="utf8mb4",
        connection_timeout=5,
    )


@contextmanager
def cursor_for(write=False):
    connection = connect()
    cursor = connection.cursor(dictionary=True)
    try:
        yield cursor
        if write:
            connection.commit()
    except Exception:
        if write:
            connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def one(sql, params=()):
    with cursor_for() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def all_rows(sql, params=()):
    with cursor_for() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def change(sql, params=()):
    with cursor_for(write=True) as cur:
        cur.execute(sql, params)
        return cur.lastrowid
