"""DB-first Instagram lab: only the 2026 term project's required features."""
import hmac
import io
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware
from starlette.concurrency import run_in_threadpool

import db
import features
from security import check_password, make_password_hash

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(db.initialize_schema)
    yield


app = FastAPI(title="DB Term Project – Instagram", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32),
    same_site="lax",
    https_only=False,  # Localhost only; use HTTPS and True for public deployment.
)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["mentions"] = features.mention_links


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(24)
    return request.session["csrf"]


def require_csrf(request: Request, submitted: str):
    saved = request.session.get("csrf", "")
    if not saved or not hmac.compare_digest(saved, submitted):
        raise HTTPException(status_code=403, detail="Invalid form token")


def render(request: Request, name: str, *, status_code=200, **context):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "current_user": request.session.get("user_id"),
            "csrf": csrf_token(request),
            **context,
        },
        status_code=status_code,
    )


def redirect(path: str):
    return RedirectResponse(path, status_code=303)


def logged_in(request: Request):
    return request.session.get("user_id")


@app.get("/")
def index(request: Request):
    return redirect("/feed" if logged_in(request) else "/login")


@app.get("/signup")
def signup_page(request: Request):
    return render(request, "signup.html")


@app.post("/signup")
def signup(
    request: Request,
    user_id: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    user_id = user_id.strip()
    display_name = display_name.strip()
    if not re.fullmatch(r"[a-zA-Z0-9_]{3,32}", user_id):
        return render(request, "signup.html", error="아이디는 3~32자의 영문·숫자·_만 가능해요.", status_code=400)
    if not 1 <= len(display_name) <= 60 or len(password) < 8 or len(password) > 200:
        return render(request, "signup.html", error="닉네임은 1~60자, 비밀번호는 8~200자로 입력해 주세요.", status_code=400)
    if db.one("SELECT user_id FROM users WHERE user_id = %s", (user_id,)):
        return render(request, "signup.html", error="이미 사용 중인 아이디입니다.", status_code=400)
    # The PK also prevents duplicate accounts if two requests race.
    try:
        db.change(
            "INSERT INTO users (user_id, display_name, password_hash) VALUES (%s, %s, %s)",
            (user_id, display_name, make_password_hash(password)),
        )
    except Exception as exc:
        # Distinguish duplicate PK from other DB failures; do not hide real problems.
        if getattr(exc, "errno", None) == 1062:
            return render(request, "signup.html", error="이미 사용 중인 아이디입니다.", status_code=400)
        raise
    request.session.clear()
    request.session["user_id"] = user_id
    return redirect("/feed")


@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    user_id: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    account = db.one("SELECT user_id, password_hash FROM users WHERE user_id = %s", (user_id.strip(),))
    if account is None or not check_password(password, account["password_hash"]):
        return render(request, "login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.", status_code=401)
    request.session.clear()
    request.session["user_id"] = account["user_id"]
    return redirect("/feed")


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    require_csrf(request, csrf)
    request.session.clear()
    return redirect("/login")


@app.get("/settings")
def settings_page(request: Request):
    if not logged_in(request):
        return redirect("/login")
    return render(request, "settings.html")


@app.post("/settings/password")
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    account = db.one("SELECT password_hash FROM users WHERE user_id=%s", (me,))
    if not account or not check_password(old_password, account["password_hash"]):
        return render(request, "settings.html", error="기존 비밀번호가 틀렸습니다.", status_code=400)
    if not 8 <= len(new_password) <= 200:
        return render(request, "settings.html", error="새 비밀번호는 8~200자로 입력해 주세요.", status_code=400)
    db.change("UPDATE users SET password_hash=%s WHERE user_id=%s", (make_password_hash(new_password), me))
    return render(request, "settings.html", message="비밀번호가 변경됐습니다.")


@app.get("/feed")
def feed(request: Request):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    # Key course query: self + followed accounts, newest posts first.
    posts = db.all_rows(
        """SELECT p.post_id, p.author_id, u.display_name, p.caption, p.image_path, p.created_at
             FROM posts AS p
             JOIN users AS u ON u.user_id = p.author_id
             WHERE p.author_id = %s
                OR EXISTS (
                   SELECT 1 FROM follows AS f
                   WHERE f.follower_id = %s AND f.followee_id = p.author_id
                )
             ORDER BY p.created_at DESC, p.post_id DESC
             LIMIT 100""",
        (me, me),
    )
    return render(request, "feed.html", posts=posts)


@app.get("/users")
def users(request: Request):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    people = db.all_rows(
        "SELECT user_id, display_name FROM users WHERE user_id<>%s ORDER BY user_id LIMIT 100",
        (me,),
    )
    return render(request, "users.html", people=people)


@app.get("/users/{user_id}")
def profile(request: Request, user_id: str):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    person = db.one(
        """SELECT u.user_id, u.display_name, u.bio, u.avatar_path,
                  (SELECT COUNT(*) FROM follows f WHERE f.followee_id=u.user_id) AS follower_count,
                  (SELECT COUNT(*) FROM follows f WHERE f.follower_id=u.user_id) AS following_count
           FROM users u WHERE u.user_id=%s""",
        (user_id,),
    )
    if not person:
        raise HTTPException(status_code=404, detail="User not found")
    posts = db.all_rows(
        """SELECT post_id, caption, image_path, created_at FROM posts
             WHERE author_id=%s ORDER BY created_at DESC, post_id DESC LIMIT 100""",
        (user_id,),
    )
    following = False if me == user_id else bool(db.one(
        "SELECT 1 FROM follows WHERE follower_id=%s AND followee_id=%s", (me, user_id)
    ))
    return render(request, "profile.html", person=person, posts=posts, is_following=following)


@app.post("/users/{user_id}/follow")
def follow(request: Request, user_id: str, csrf: str = Form(...)):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    if me == user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    if not db.one("SELECT 1 FROM users WHERE user_id=%s", (user_id,)):
        raise HTTPException(status_code=404, detail="User not found")
    db.change(
        "INSERT IGNORE INTO follows (follower_id, followee_id) VALUES (%s,%s)",
        (me, user_id),
    )
    return redirect(f"/users/{user_id}")


@app.post("/users/{user_id}/unfollow")
def unfollow(request: Request, user_id: str, csrf: str = Form(...)):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    db.change("DELETE FROM follows WHERE follower_id=%s AND followee_id=%s", (me, user_id))
    return redirect(f"/users/{user_id}")


@app.get("/users/{user_id}/connections")
def connections(request: Request, user_id: str, kind: str = "followers"):
    if not logged_in(request):
        return redirect("/login")
    if kind not in ("followers", "following"):
        raise HTTPException(status_code=400, detail="Invalid list kind")
    if not db.one("SELECT 1 FROM users WHERE user_id=%s", (user_id,)):
        raise HTTPException(status_code=404, detail="User not found")
    if kind == "followers":
        sql = """SELECT u.user_id, u.display_name FROM follows f
                 JOIN users u ON u.user_id=f.follower_id
                 WHERE f.followee_id=%s ORDER BY u.user_id"""
    else:
        sql = """SELECT u.user_id, u.display_name FROM follows f
                 JOIN users u ON u.user_id=f.followee_id
                 WHERE f.follower_id=%s ORDER BY u.user_id"""
    people = db.all_rows(sql, (user_id,))
    return render(request, "connections.html", people=people, user_id=user_id, kind=kind)


@app.get("/posts/new")
def new_post_page(request: Request):
    if not logged_in(request):
        return redirect("/login")
    return render(request, "new_post.html")


@app.post("/posts")
async def create_post(
    request: Request,
    image: UploadFile = File(...),
    caption: str = Form(""),
    csrf: str = Form(...),
    hashtags: str = Form(""),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    try:
        tags = parse_hashtags(caption + " " + hashtags)
    except ValueError as exc:
        return render(request, "new_post.html", error=str(exc), status_code=400)
    if len(caption) > 500:
        return render(request, "new_post.html", error="설명은 최대 500자입니다.", status_code=400)
    # Allow only verified image data, never trust the browser's filename/extension.
    content = await image.read(MAX_BYTES + 1)
    await image.close()
    if len(content) > MAX_BYTES:
        return render(request, "new_post.html", error="사진은 5MB 이하만 업로드할 수 있어요.", status_code=400)
    try:
        with Image.open(io.BytesIO(content)) as picture:
            if picture.width * picture.height > MAX_IMAGE_PIXELS:
                raise ValueError("too many pixels")
            fmt = picture.format
            picture.verify()
        extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        extension = None
    if not extension:
        return render(request, "new_post.html", error="JPG, PNG, WEBP 이미지 파일만 가능합니다.", status_code=400)
    filename = f"{uuid.uuid4().hex}.{extension}"
    path = UPLOADS / filename
    path.write_bytes(content)
    try:
        # Publish the post and its tags atomically; failure also removes the image.
        with db.cursor_for(write=True) as cur:
            cur.execute(
                "INSERT INTO posts (author_id, image_path, caption) VALUES (%s, %s, %s)",
                (me, f"/uploads/{filename}", caption.strip()),
            )
            post_id = cur.lastrowid
            for tag in tags:
                cur.execute("INSERT IGNORE INTO hashtags (name) VALUES (%s)", (tag,))
                cur.execute(
                    "INSERT IGNORE INTO post_hashtags (post_id, hashtag_id) "
                    "SELECT %s, hashtag_id FROM hashtags WHERE name=%s",
                    (post_id, tag),
                )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return redirect(f"/posts/{post_id}")


@app.get("/posts/{post_id}")
def post_detail(request: Request, post_id: int):
    if not logged_in(request):
        return redirect("/login")
    post = db.one(
        """SELECT p.post_id, p.author_id, p.caption, p.image_path, p.created_at, u.display_name
             FROM posts p JOIN users u ON u.user_id=p.author_id WHERE p.post_id=%s""",
        (post_id,),
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = db.all_rows(
        """SELECT c.comment_id, c.body, c.created_at, c.author_id, u.display_name,
                  (SELECT COUNT(*) FROM comment_likes cl WHERE cl.comment_id=c.comment_id) AS like_count,
                  EXISTS(SELECT 1 FROM comment_likes cl WHERE cl.comment_id=c.comment_id AND cl.user_id=%s) AS liked
             FROM comments c JOIN users u ON c.author_id=u.user_id
             WHERE c.post_id=%s ORDER BY c.created_at ASC, c.comment_id ASC""",
        (logged_in(request), post_id),
    )
    me = logged_in(request)
    stats = db.one(
        """SELECT (SELECT COUNT(*) FROM likes WHERE post_id=%s) AS like_count,
                  EXISTS(SELECT 1 FROM likes WHERE post_id=%s AND user_id=%s) AS liked,
                  EXISTS(SELECT 1 FROM saved_posts WHERE post_id=%s AND user_id=%s) AS saved""",
        (post_id, post_id, me, post_id, me),
    )
    tags = db.all_rows(
        "SELECT h.name FROM hashtags h JOIN post_hashtags ph ON ph.hashtag_id=h.hashtag_id "
        "WHERE ph.post_id=%s ORDER BY h.name", (post_id,),
    )
    return render(request, "post.html", post=post, comments=comments, stats=stats, tags=tags)


@app.post("/posts/{post_id}/comments")
def add_comment(
    request: Request,
    post_id: int,
    body: str = Form(...),
    csrf: str = Form(...),
):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    body = body.strip()
    if not 1 <= len(body) <= 1000:
        raise HTTPException(status_code=400, detail="Comment must have 1~1000 characters")
    if not db.one("SELECT 1 FROM posts WHERE post_id=%s", (post_id,)):
        raise HTTPException(status_code=404, detail="Post not found")
    db.change(
        "INSERT INTO comments (post_id, author_id, body) VALUES (%s,%s,%s)",
        (post_id, me, body),
    )
    return redirect(f"/posts/{post_id}")


def parse_hashtags(text: str) -> list[str]:
    """Accept Unicode letters/numbers/underscore, deduplicate and normalize case."""
    tags = list(dict.fromkeys(tag.lower() for tag in re.findall(r"(?<!\w)#(\w+)", text)))
    if len(tags) > 30 or any(len(tag) > 50 for tag in tags):
        raise ValueError("해시태그는 최대 30개, 각 태그는 50자 이하로 입력해 주세요.")
    return tags


def post_action(request: Request, post_id: int, csrf: str, table: str, add: bool):
    require_csrf(request, csrf)
    me = logged_in(request)
    if not me:
        return redirect("/login")
    if not db.one("SELECT 1 FROM posts WHERE post_id=%s", (post_id,)):
        raise HTTPException(status_code=404, detail="Post not found")
    # table is an internal constant, never user input; values remain parameterized.
    if add:
        db.change(f"INSERT IGNORE INTO {table} (user_id, post_id) VALUES (%s,%s)", (me, post_id))
    else:
        db.change(f"DELETE FROM {table} WHERE user_id=%s AND post_id=%s", (me, post_id))
    return redirect(f"/posts/{post_id}")


@app.post("/posts/{post_id}/like")
def like_post(request: Request, post_id: int, csrf: str = Form(...)):
    return post_action(request, post_id, csrf, "likes", True)


@app.post("/posts/{post_id}/unlike")
def unlike_post(request: Request, post_id: int, csrf: str = Form(...)):
    return post_action(request, post_id, csrf, "likes", False)


@app.post("/posts/{post_id}/save")
def save_post(request: Request, post_id: int, csrf: str = Form(...)):
    return post_action(request, post_id, csrf, "saved_posts", True)


@app.post("/posts/{post_id}/unsave")
def unsave_post(request: Request, post_id: int, csrf: str = Form(...)):
    return post_action(request, post_id, csrf, "saved_posts", False)


@app.get("/saved")
def saved_posts(request: Request):
    me = logged_in(request)
    if not me:
        return redirect("/login")
    posts = db.all_rows(
        """SELECT p.* FROM saved_posts s JOIN posts p ON p.post_id=s.post_id
           WHERE s.user_id=%s ORDER BY s.created_at DESC, s.post_id DESC LIMIT 100""", (me,),
    )
    return render(request, "post_list.html", title="저장한 게시물", posts=posts)


@app.get("/tags/{name}")
def tag_posts(request: Request, name: str):
    if not logged_in(request):
        return redirect("/login")
    posts = db.all_rows(
        """SELECT p.* FROM posts p JOIN post_hashtags ph ON ph.post_id=p.post_id
           JOIN hashtags h ON h.hashtag_id=ph.hashtag_id WHERE h.name=%s
           ORDER BY p.created_at DESC, p.post_id DESC LIMIT 100""", (name.lower(),),
    )
    return render(request, "post_list.html", title="#" + name, posts=posts)


@app.get("/search")
def search(request: Request, q: str = ""):
    if not logged_in(request):
        return redirect("/login")
    q = q.strip()
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="검색어는 100자 이하로 입력해 주세요.")
    people, posts, tags = [], [], []
    if q:
        # LOCATE treats %, _ and quotes literally, without SQL wildcard expansion.
        people = db.all_rows(
            "SELECT user_id, display_name FROM users WHERE LOCATE(%s,user_id)>0 "
            "OR LOCATE(%s,display_name)>0 ORDER BY user_id LIMIT 100", (q, q),
        )
        posts = db.all_rows(
            "SELECT * FROM posts WHERE LOCATE(%s,caption)>0 "
            "ORDER BY created_at DESC, post_id DESC LIMIT 100", (q,),
        )
        tags = db.all_rows(
            "SELECT name FROM hashtags WHERE LOCATE(%s,name)>0 ORDER BY name LIMIT 100",
            (q.lstrip("#").lower(),),
        )
    return render(request, "search.html", q=q, people=people, posts=posts, tags=tags)


features.register(app, render, require_csrf, logged_in, redirect, lambda: UPLOADS)
