"""Parameterized MySQL access. Keep SQL visible for database coursework."""
import os
import re
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from local_config import ensure_env

BASE = Path(__file__).resolve().parent
load_dotenv(ensure_env(BASE / ".env"), encoding="utf-8-sig")


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
    try:
        connection = connect()
    except mysql.connector.Error as exc:
        if exc.errno != 1049:
            raise
        connection = mysql.connector.connect(**connection_settings(include_database=False))
        try:
            select_database(connection)
        except Exception:
            connection.close()
            raise
    try:
        apply_schema(connection)
    finally:
        connection.close()


def connection_settings(include_database=True):
    values = dict(
        host=os.getenv("DB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        charset="utf8mb4",
        connection_timeout=5,
    )
    if include_database:
        values["database"] = os.getenv("DB_NAME", "instagram_term_2026")
    return values


def connect():
    return mysql.connector.connect(**connection_settings())


def select_database(connection):
    name = os.getenv("DB_NAME", "instagram_term_2026")
    if not name or len(name) > 64 or "\x00" in name:
        raise ValueError("DB_NAME에 유효한 MySQL 데이터베이스 이름을 입력해 주세요.")
    quoted = "`" + name.replace("`", "``") + "`"
    cursor = connection.cursor()
    try:
        try:
            cursor.execute(f"USE {quoted}")
        except mysql.connector.Error as exc:
            if exc.errno != 1049:
                raise
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {quoted} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE {quoted}")
    finally:
        cursor.close()


def apply_schema(connection):
    cursor = connection.cursor()
    try:
        for path in schema_files():
            for statement in schema_statements(path.read_text(encoding="utf-8-sig")):
                if re.match(r"(?:CREATE\s+DATABASE|USE)\b", statement, re.IGNORECASE):
                    continue
                cursor.execute(statement)
                if cursor.with_rows:
                    cursor.fetchall()
            connection.commit()
    finally:
        cursor.close()


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
