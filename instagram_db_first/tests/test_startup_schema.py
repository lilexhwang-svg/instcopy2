"""Exercise the reported pages against a legacy database and a real app restart."""
import mysql.connector
import pytest
from fastapi.testclient import TestClient

from test_social_features import site, signup, upload, action
import app as web
import db


@pytest.mark.parametrize("with_posts", [False, True])
def test_restart_upgrades_legacy_database_without_losing_data(site, with_posts):
    signup(site)
    if with_posts:
        path = upload(site, "기존 게시물 보존 확인")
        action(site, path, "like")
        action(site, path, "save")

    # Match databases created before the profile and timestamp columns existed.
    db.change("ALTER TABLE users DROP COLUMN bio, DROP COLUMN avatar_path")
    db.change("ALTER TABLE likes DROP COLUMN created_at")
    db.change("ALTER TABLE saved_posts DROP COLUMN created_at")
    paths = ("/saved", "/liked", "/users/alice")
    for route in paths:
        with pytest.raises(mysql.connector.Error) as error:
            site.get(route)
        assert error.value.errno == 1054

    selected_database = db.one("SELECT DATABASE() AS name")["name"]
    assert selected_database.startswith("instcopy_test_")
    for _ in range(2):
        with TestClient(web.app) as restarted:
            restarted.cookies.update(site.cookies)
            for route in paths:
                response = restarted.get(route)
                assert response.status_code == 200
                if with_posts:
                    assert path in response.text
                    assert "기존 게시물 보존 확인" in response.text
                else:
                    assert "게시물이 없습니다." in response.text
            assert db.one("SELECT DATABASE() AS name")["name"] == selected_database
            assert db.one("SELECT COUNT(*) AS n FROM users")["n"] == 1
            for table in ("posts", "likes", "saved_posts"):
                assert db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] == int(with_posts)


def test_startup_reports_database_failure_before_serving_requests(monkeypatch):
    def unavailable():
        raise mysql.connector.Error("database unavailable", errno=2003)

    monkeypatch.setattr(db, "initialize_schema", unavailable)
    with pytest.raises(mysql.connector.Error, match="database unavailable"):
        with TestClient(web.app):
            pytest.fail("Startup must not complete with an unavailable database")
