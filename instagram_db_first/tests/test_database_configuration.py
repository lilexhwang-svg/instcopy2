"""Keep the intended remote server and database when preparing the app."""
import os

from dotenv import dotenv_values
import mysql.connector
import pytest

from test_social_features import site
import db
import run_local as runner


@pytest.mark.parametrize("errno", [2003, 2005])
def test_remote_failure_never_falls_back_to_localhost(monkeypatch, errno):
    calls = []

    def unavailable(**values):
        calls.append(values)
        raise mysql.connector.InterfaceError("test connection failure", errno=errno)

    monkeypatch.setattr(mysql.connector, "connect", unavailable)
    conf = dict(host="db.example.test", port=25060, user="appuser", password="test-only")
    with pytest.raises(ConnectionError, match="db.example.test:25060"):
        runner.reach_server(conf)
    assert len(calls) == 1
    assert calls[0]["host"] == conf["host"]
    assert calls[0]["port"] == conf["port"]


def test_authentication_failure_keeps_the_configured_endpoint(monkeypatch):
    def denied(**values):
        raise mysql.connector.ProgrammingError("test access denied", errno=1045)

    monkeypatch.setattr(mysql.connector, "connect", denied)
    conf = dict(host="db.example.test", port=25060, user="appuser", password="test-only")
    assert runner.reach_server(conf) == ("db.example.test", 25060)


def test_no_host_does_not_default_to_localhost(monkeypatch, tmp_path):
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setattr(runner, "ENV", tmp_path / "missing.env")
    with pytest.raises(ValueError, match="DB_HOST"):
        runner.settings()
    with pytest.raises(ValueError, match="DB_HOST"):
        db.connect()


def test_saved_config_keeps_the_hosted_database_name(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ENV", tmp_path / ".env")
    values = dict(DB_HOST="db.example.test", DB_PORT="25060", DB_USER="appuser",
                  DB_PASSWORD="test-only", DB_NAME="hosted_coursework")
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    runner.save_env(dict(host=values["DB_HOST"], port=int(values["DB_PORT"]),
                         user=values["DB_USER"], password=values["DB_PASSWORD"]))
    assert dotenv_values(runner.ENV) == values
    assert os.environ["DB_NAME"] == "hosted_coursework"


def test_preparation_uses_the_configured_database(site, monkeypatch, tmp_path):
    name = db.one("SELECT DATABASE() AS name")["name"]
    assert name.startswith("instcopy_test_")
    conn = db.connect()
    conf = dict(host="127.0.0.1", port=int(os.environ["TEST_MYSQL_PORT"]),
                user=os.getenv("TEST_MYSQL_USER", "root"), password=os.getenv("TEST_MYSQL_PASSWORD", ""))
    for key, value in dict(DB_NAME=name, DB_HOST=conf["host"], DB_PORT=str(conf["port"]),
                           DB_USER=conf["user"], DB_PASSWORD=conf["password"]).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(runner, "ENV", tmp_path / ".env")
    monkeypatch.setattr(runner, "connect_or_ask", lambda: (conn, conf))
    runner.prepare_database()
    assert db.one("SELECT DATABASE() AS name")["name"] == name
    assert os.environ["DB_NAME"] == name
