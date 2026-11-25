"""Five optional features; reuse the app's session, CSRF and database helpers."""
import io
import logging
import re
import uuid
from typing import Literal

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from markupsafe import Markup, escape
from PIL import Image, UnidentifiedImageError

import db


def mention_links(text):
    parts, start = [], 0
    for match in re.finditer(r"(?<![\w@])@([A-Za-z0-9_]{3,32})(?![A-Za-z0-9_])", text):
        parts.extend((escape(text[start:match.start()]),
                      Markup('<a href="/users/{0}">@{0}</a>').format(match[1])))
        start = match.end()
    parts.append(escape(text[start:]))
    return Markup('').join(parts)


def remove_avatar(url, uploads):
    if url and re.fullmatch(r'/uploads/[0-9a-f]{32}\.(jpg|png|webp)', url):
        try:
            (uploads / url.rsplit('/', 1)[1]).unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning('Could not remove an unused avatar file')


async def read_avatar(avatar):
    content = await avatar.read(5 * 1024 * 1024 + 1)
    await avatar.close()
    try:
        if len(content) > 5 * 1024 * 1024:
            raise ValueError
        with Image.open(io.BytesIO(content)) as picture:
            if picture.width * picture.height > 20_000_000:
                raise ValueError
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(picture.format)
            picture.verify()
        if not extension:
            raise ValueError
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail='사진은 5MB 이하 JPG, PNG, WEBP만 가능합니다.') from exc
    return f'/uploads/{uuid.uuid4().hex}.{extension}', content


def register(app, render, require_csrf, logged_in, redirect, uploads):
    def actor(request: Request, csrf: str = Form(...)):
        require_csrf(request, csrf)
        me = logged_in(request)
        if not me:
            raise HTTPException(status_code=401, detail='로그인이 필요합니다.')
        return me

    @app.get('/liked')
    def liked_posts(request: Request):
        me = logged_in(request)
        if not me:
            return redirect('/login')
        posts = db.all_rows('''SELECT p.* FROM likes l JOIN posts p ON p.post_id=l.post_id
            WHERE l.user_id=%s ORDER BY l.created_at DESC, l.post_id DESC LIMIT 100''', (me,))
        return render(request, 'post_list.html', title='좋아요한 게시물', posts=posts)

    @app.post('/comments/{comment_id}/{action}')
    def comment_action(comment_id: int, action: Literal['delete', 'like', 'unlike'],
                       me: str = Depends(actor)):
        comment = db.one('SELECT post_id, author_id FROM comments WHERE comment_id=%s', (comment_id,))
        if not comment:
            raise HTTPException(status_code=404, detail='댓글이 없습니다.')
        if action == 'delete':
            if comment['author_id'] != me:
                raise HTTPException(status_code=403, detail='본인 댓글만 삭제할 수 있습니다.')
            db.change('DELETE FROM comments WHERE comment_id=%s AND author_id=%s', (comment_id, me))
        elif action == 'like':
            db.change('INSERT IGNORE INTO comment_likes (user_id, comment_id) VALUES (%s,%s)',
                      (me, comment_id))
        else:
            db.change('DELETE FROM comment_likes WHERE user_id=%s AND comment_id=%s', (me, comment_id))
        return redirect(f'/posts/{comment["post_id"]}')

    @app.get('/settings/profile')
    def edit_profile_page(request: Request):
        me = logged_in(request)
        if not me:
            return redirect('/login')
        person = db.one('SELECT user_id, display_name, bio, avatar_path FROM users WHERE user_id=%s', (me,))
        if not person:
            raise HTTPException(status_code=404, detail='사용자가 없습니다.')
        return render(request, 'edit_profile.html', person=person)

    @app.post('/settings/profile')
    async def edit_profile(me: str = Depends(actor), display_name: str = Form(...),
                           bio: str = Form(''), avatar: UploadFile | None = File(None),
                           remove_picture: bool = Form(False)):
        display_name, bio = display_name.strip(), bio.strip()
        if not 1 <= len(display_name) <= 60 or len(bio) > 300:
            raise HTTPException(status_code=400, detail='닉네임은 1~60자, 소개글은 최대 300자입니다.')
        new_url, content = await read_avatar(avatar) if avatar and avatar.filename else ('', None)
        old_url = ''
        try:
            if new_url:
                (uploads() / new_url.rsplit('/', 1)[1]).write_bytes(content)
            with db.cursor_for(write=True) as cur:
                cur.execute('SELECT avatar_path FROM users WHERE user_id=%s FOR UPDATE', (me,))
                account = cur.fetchone()
                if not account:
                    raise HTTPException(status_code=404, detail='사용자가 없습니다.')
                old_url = account['avatar_path']
                avatar_path = new_url or ('' if remove_picture else old_url)
                cur.execute('UPDATE users SET display_name=%s, bio=%s, avatar_path=%s WHERE user_id=%s',
                            (display_name, bio, avatar_path, me))
        except Exception:
            remove_avatar(new_url, uploads())
            raise
        if old_url != avatar_path:
            remove_avatar(old_url, uploads())
        return redirect(f'/users/{me}')
