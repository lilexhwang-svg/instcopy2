"""Prepare the configured MySQL database and start the local FastAPI server."""
import getpass
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path

import mysql.connector
import uvicorn
from dotenv import load_dotenv, set_key

from db import schema_files, schema_statements

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
PORT = int(os.getenv("PORT", "8001"))
SQL_FILES = schema_files()


def settings():
    load_dotenv(ENV)
    host = os.getenv("DB_HOST", "").strip()
    if not host:
        raise ValueError(".env.example을 .env로 복사하고 DB_HOST에 MySQL 서버 주소를 입력해 주세요.")
    return {
        "host": host,
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def unreachable(exc):
    return exc.errno is None or (exc.errno >= 2000 and exc.errno != 2059)


def reach_server(conf):
    """Keep the exact configured Workbench host and port; never switch servers."""
    try:
        mysql.connector.connect(**conf, connection_timeout=5).close()
    except mysql.connector.Error as exc:
        if unreachable(exc):
            raise ConnectionError(
                f"MySQL 서버 {conf['host']}:{conf['port']}에 연결할 수 없습니다. "
                "Workbench의 Hostname/Port와 서버 접속 허용 설정을 확인해 주세요."
            ) from exc
        # Authentication errors mean this server answered; ask for credentials next.
    return conf["host"], conf["port"]


def connect_or_ask():
    conf = settings()
    conf["host"], conf["port"] = reach_server(conf)
    print(f"  MySQL 서버 찾음: {conf['host']}:{conf['port']}")
    for attempt in range(4):
        try:
            return mysql.connector.connect(**conf, charset="utf8mb4", connection_timeout=5), conf
        except mysql.connector.Error as exc:
            if exc.errno != 1045:
                raise
            if attempt == 3:
                sys.exit("[오류] MySQL Workbench에서 사용하는 계정과 비밀번호를 확인하세요.")
            print(f"[안내] MySQL 로그인 실패 (사용자: {conf['user']}).")
            conf["user"] = input(f"  MySQL 사용자 이름 [{conf['user']}]: ").strip() or conf["user"]
            conf["password"] = getpass.getpass("  MySQL 비밀번호 (화면에 표시되지 않음): ")


def save_env(conn_conf):
    database_name = os.getenv("DB_NAME", "instagram_term_2026")
    ENV.touch(exist_ok=True)
    values = {
        "DB_HOST": conn_conf["host"], "DB_PORT": str(conn_conf["port"]),
        "DB_USER": conn_conf["user"], "DB_PASSWORD": conn_conf["password"],
        "DB_NAME": database_name,
    }
    for key, value in values.items():
        set_key(str(ENV), key, value)
    os.environ.update(values)


def statements(sql):
    return schema_statements(sql)


def prepare_database():
    conn, conf = connect_or_ask()
    try:
        save_env(conf)
        cur = conn.cursor()
        try:
            database_name = os.environ["DB_NAME"]
            if not database_name or len(database_name) > 64 or "\x00" in database_name:
                raise ValueError("DB_NAME에 유효한 MySQL 데이터베이스 이름을 입력해 주세요.")
            quoted_name = "`" + database_name.replace("`", "``") + "`"
            try:
                cur.execute(f"USE {quoted_name}")
            except mysql.connector.Error as exc:
                if exc.errno != 1049:
                    raise
                cur.execute(f"CREATE DATABASE {quoted_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cur.execute(f"USE {quoted_name}")
            for path in SQL_FILES:
                for stmt in statements(path.read_text(encoding="utf-8")):
                    if re.match(r"(?:CREATE\s+DATABASE|USE)\b", stmt, re.IGNORECASE):
                        continue
                    cur.execute(stmt)
                    if cur.with_rows:
                        cur.fetchall()
                conn.commit()
                print(f"  OK {path.relative_to(BASE)}")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    print("[1/2] 데이터베이스 준비 (기존 데이터는 그대로 유지)")
    try:
        prepare_database()
    except (ConnectionError, mysql.connector.Error, OSError, ValueError) as exc:
        sys.exit(f"[오류] {exc}")
    url = f"http://127.0.0.1:{PORT}"
    print(f"[2/2] 서버 시작: {url} (끄려면 Ctrl+C)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    sys.path.insert(0, str(BASE))
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=False)
