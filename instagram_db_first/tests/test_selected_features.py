"""The selected five features, verified against an isolated MySQL database."""
import io
from pathlib import Path

import pytest
from PIL import Image

from test_social_features import site, signup, token, upload, action
import app as web
import db
from features import mention_links, remove_avatar


def png():
    image = io.BytesIO()
    Image.new('RGB', (4, 4), 'green').save(image, format='PNG')
    return image.getvalue()


def comment(client, path, body='@alice hello'):
    response = client.post(path + '/comments', data={'csrf': token(client), 'body': body})
    assert response.status_code == 200
    return db.one('SELECT MAX(comment_id) AS id FROM comments')['id']


def profile(client, **values):
    data = {'csrf': token(client), 'display_name': 'New name', 'bio': 'Hello'}
    data.update(values)
    return client.post('/settings/profile', data=data, follow_redirects=False)


def test_mentions_escape_html_and_ignore_email_and_invalid_ids():
    text = '<img src=x onerror=alert(1)> @alice @bobby_1 a@alice.com @@alice @ab @' + 'x' * 33
    result = str(mention_links(text))
    assert '<img' not in result and '&lt;img' in result
    assert '<a href="/users/alice">@alice</a>' in result
    assert '<a href="/users/bobby_1">@bobby_1</a>' in result
    assert result.count('<a ') == 2
    assert 'a@alice.com' in result and '@@alice' in result


def test_avatar_cleanup_cannot_remove_other_paths(tmp_path):
    protected = tmp_path / 'keep.png'
    protected.write_bytes(b'keep')
    for url in ('/uploads/../keep.png', '/uploads/keep.png', '/etc/passwd', ''):
        remove_avatar(url, tmp_path)
    assert protected.read_bytes() == b'keep'


def test_liked_list_is_personal_and_unlike_removes_post(site):
    signup(site)
    path = upload(site, 'alice photo')
    action(site, path, 'like')
    assert path in site.get('/liked').text
    action(site, '', 'logout')
    signup(site, 'bobby')
    assert path not in site.get('/liked').text
    action(site, path, 'like')
    assert path in site.get('/liked').text
    action(site, path, 'unlike')
    assert path not in site.get('/liked').text


def test_comment_like_idempotency_and_owner_only_delete(site):
    signup(site)
    path = upload(site)
    comment_id = comment(site, path)
    base = f'/comments/{comment_id}'
    action(site, '', 'logout')
    signup(site, 'bobby')
    for _ in range(2):
        assert action(site, base, 'like').status_code == 303
    assert db.one('SELECT COUNT(*) AS n FROM comment_likes')['n'] == 1
    assert '좋아요 취소 · 1' in site.get(path).text
    assert f'action="{base}/delete"' not in site.get(path).text
    assert action(site, base, 'delete').status_code == 403
    assert db.one('SELECT comment_id FROM comments WHERE comment_id=%s', (comment_id,))
    for _ in range(2):
        assert action(site, base, 'unlike').status_code == 303
    assert db.one('SELECT COUNT(*) AS n FROM comment_likes')['n'] == 0
    action(site, base, 'like')
    action(site, '', 'logout')
    site.post('/login', data={'csrf': token(site, '/login'), 'user_id': 'alice', 'password': 'password123'})
    assert action(site, base, 'delete').status_code == 303
    assert not db.one('SELECT comment_id FROM comments WHERE comment_id=%s', (comment_id,))
    assert db.one('SELECT COUNT(*) AS n FROM comment_likes')['n'] == 0


def test_new_routes_require_login_csrf_and_valid_targets(site):
    for path in ('/liked', '/settings/profile'):
        assert site.get(path, follow_redirects=False).headers['location'] == '/login'
    anonymous_token = token(site, '/login')
    for name in ('delete', 'like', 'unlike'):
        assert site.post('/comments/1/' + name, data={'csrf': 'fake'}).status_code == 403
        assert site.post('/comments/1/' + name, data={'csrf': anonymous_token}).status_code == 401
    assert site.post('/settings/profile', data={'csrf': anonymous_token, 'display_name': 'x'}).status_code == 401
    signup(site)
    for name in ('delete', 'like', 'unlike'):
        assert site.post('/comments/1/' + name, data={'csrf': 'fake'}).status_code == 403
        assert action(site, '/comments/999999', name).status_code == 404
    assert action(site, '/comments/1', 'unexpected').status_code == 422
    assert site.post('/settings/profile', data={'csrf': 'fake', 'display_name': 'x'}).status_code == 403


def test_profile_text_avatar_replacement_removal_and_account_scope(site):
    signup(site)
    old_post = upload(site, 'unchanged post')
    response = site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'Changed',
        'bio': '<script>hello</script>'}, files={'avatar': ('picture.png', png(), 'image/png')}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/users/alice'
    first = db.one('SELECT avatar_path FROM users WHERE user_id=%s', ('alice',))['avatar_path']
    assert (web.UPLOADS / first.rsplit('/', 1)[1]).is_file()
    page = site.get('/users/alice').text
    assert 'Changed' in page and first in page
    assert '&lt;script&gt;hello&lt;/script&gt;' in page and '<script>hello</script>' not in page
    response = profile(site, bio='Updated')
    assert response.status_code == 303
    assert db.one('SELECT avatar_path FROM users WHERE user_id=%s', ('alice',))['avatar_path'] == first
    response = site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'Final'},
        files={'avatar': ('second.webp', png(), 'image/webp')}, follow_redirects=False)
    assert response.status_code == 303
    second = db.one('SELECT avatar_path FROM users WHERE user_id=%s', ('alice',))['avatar_path']
    assert second != first and second.endswith('.png')
    assert not (web.UPLOADS / first.rsplit('/', 1)[1]).exists()
    assert profile(site, remove_picture='true').status_code == 303
    assert db.one('SELECT avatar_path FROM users WHERE user_id=%s', ('alice',))['avatar_path'] == ''
    assert not (web.UPLOADS / second.rsplit('/', 1)[1]).exists()
    assert site.get(old_post).status_code == 200
    action(site, '', 'logout')
    signup(site, 'bobby')
    assert profile(site, user_id='alice', display_name='Bob').status_code == 303
    assert db.one('SELECT display_name FROM users WHERE user_id=%s', ('alice',))['display_name'] == 'New name'
    assert db.one('SELECT display_name FROM users WHERE user_id=%s', ('bobby',))['display_name'] == 'Bob'


@pytest.mark.parametrize('values', [{'display_name': ' '}, {'display_name': 'x' * 61}, {'bio': 'x' * 301}])
def test_profile_limits(site, values):
    signup(site)
    assert profile(site, **values).status_code == 400
    assert db.one('SELECT display_name FROM users WHERE user_id=%s', ('alice',))['display_name'] == 'alice'


@pytest.mark.parametrize('payload', [b'<svg></svg>', b'x' * (5 * 1024 * 1024 + 1)])
def test_bad_avatar_leaves_no_files_or_profile_changes(site, payload):
    signup(site)
    response = site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'Changed'},
        files={'avatar': ('bad.png', payload, 'image/png')})
    assert response.status_code == 400
    assert list(web.UPLOADS.iterdir()) == []
    assert db.one('SELECT display_name FROM users WHERE user_id=%s', ('alice',))['display_name'] == 'alice'


def test_avatar_database_failure_cleans_new_file_and_preserves_old(site, monkeypatch):
    signup(site)
    site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'alice'},
        files={'avatar': ('first.png', png(), 'image/png')})
    before = list(web.UPLOADS.iterdir())
    original = db.cursor_for

    def fail_write(*, write=False):
        if write:
            raise RuntimeError('simulated database failure')
        return original(write=write)

    monkeypatch.setattr(db, 'cursor_for', fail_write)
    csrf = token(site)
    with pytest.raises(RuntimeError, match='simulated database failure'):
        site.post('/settings/profile', data={'csrf': csrf, 'display_name': 'Changed'},
            files={'avatar': ('new.png', png(), 'image/png')})
    assert list(web.UPLOADS.iterdir()) == before


def test_migration_preserves_main_data_and_can_be_repeated(site):
    signup(site)
    path = upload(site, 'keep existing data')
    comment_id = comment(site, path)
    db.change('DROP TABLE comment_likes')
    db.change('ALTER TABLE users DROP COLUMN bio, DROP COLUMN avatar_path')
    script = (Path(web.BASE) / 'migrations/002_selected_features.sql').read_text()
    script = '\n'.join(line for line in script.splitlines() if not line.startswith('--'))
    for _ in range(2):
        with db.cursor_for(write=True) as cur:
            for statement in script.split(';')[1:]:
                if statement.strip():
                    cur.execute(statement)
                    if cur.with_rows:
                        cur.fetchall()
    assert db.one('SELECT COUNT(*) AS n FROM posts')['n'] == 1
    assert db.one('SELECT bio, avatar_path FROM users')['bio'] == ''
    assert action(site, f'/comments/{comment_id}', 'like').status_code == 303
    assert site.get(path).status_code == 200


def test_oversized_pixel_avatar_is_rejected(site, monkeypatch):
    signup(site)
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 2)
    response = site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'Changed'},
        files={'avatar': ('large.png', png(), 'image/png')})
    assert response.status_code == 400
    assert list(web.UPLOADS.iterdir()) == []


@pytest.mark.parametrize('image_format,extension', [('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp')])
def test_profile_accepts_each_supported_image_format(site, image_format, extension):
    signup(site)
    picture = io.BytesIO()
    Image.new('RGB', (4, 4), 'purple').save(picture, format=image_format)
    response = site.post('/settings/profile', data={'csrf': token(site), 'display_name': 'alice',
        'remove_picture': 'true'}, files={'avatar': ('photo.' + extension, picture.getvalue(), 'image/' + extension)},
        follow_redirects=False)
    assert response.status_code == 303
    avatar = db.one('SELECT avatar_path FROM users WHERE user_id=%s', ('alice',))['avatar_path']
    assert avatar.endswith('.' + extension)
    assert avatar in site.get('/users/alice').text
    with Image.open(web.UPLOADS / avatar.rsplit('/', 1)[1]) as stored:
        assert stored.format == image_format


def test_complete_migration_chain_preserves_original_database(site):
    signup(site)
    path = upload(site, 'original database post')
    comment_id = comment(site, path, 'original comment')
    for table in ('comment_likes', 'post_hashtags', 'hashtags', 'likes', 'saved_posts'):
        db.change(f'DROP TABLE {table}')
    db.change('ALTER TABLE users DROP COLUMN bio, DROP COLUMN avatar_path')
    # Four base tables now match the original app before any optional features.
    for migration in ('001_social_features.sql', '002_selected_features.sql'):
        text = (Path(web.BASE) / 'migrations' / migration).read_text()
        text = '\n'.join(line for line in text.splitlines() if not line.startswith('--'))
        for _ in range(2):
            with db.cursor_for(write=True) as cur:
                for statement in text.split(';')[1:]:
                    if statement.strip():
                        cur.execute(statement)
                        if cur.with_rows:
                            cur.fetchall()
    assert db.one('SELECT COUNT(*) AS n FROM users')['n'] == 1
    assert db.one('SELECT COUNT(*) AS n FROM posts')['n'] == 1
    assert db.one('SELECT COUNT(*) AS n FROM comments')['n'] == 1
    assert action(site, path, 'like').status_code == 303
    assert action(site, path, 'save').status_code == 303
    assert action(site, f'/comments/{comment_id}', 'like').status_code == 303
    assert profile(site, bio='migrated profile').status_code == 303
    assert site.get(path).status_code == 200
