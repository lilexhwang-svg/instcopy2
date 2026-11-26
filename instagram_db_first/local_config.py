"""Create a local configuration when a downloaded project has no .env."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"
DEFAULT_ENV = "DB_HOST=127.0.0.1\nDB_PORT=3306\nDB_USER=root\nDB_PASSWORD=\nDB_NAME=instagram_term_2026\nPORT=8001\n"


def ensure_env(path=ENV):
    path = Path(path)
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(DEFAULT_ENV)
        except FileExistsError:
            pass
    return path


def verify_files():
    templates = (
        "_gallery.html", "base.html", "connections.html", "edit_profile.html",
        "feed.html", "login.html", "new_post.html", "post.html", "post_list.html",
        "profile.html", "search.html", "settings.html", "signup.html", "users.html",
    )
    paths = [BASE / "templates" / name for name in templates]
    paths += [BASE / "static/style.css", BASE / "schema.sql"]
    paths += [BASE / "migrations" / name for name in (
        "001_social_features.sql", "002_selected_features.sql", "003_fix_created_at.sql")]
    missing = [str(p.relative_to(BASE)) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError("압축 전체를 새 폴더에 풀어 주세요. 누락 파일: " + ", ".join(missing))
