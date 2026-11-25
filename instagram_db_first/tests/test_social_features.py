"""HTTP + real MySQL tests; each test creates and drops its own isolated database.

Run with TEST_MYSQL_PORT set, using an account permitted to create databases.
Never use a production database account for this suite.
"""
import io
import os
import re
import sys
import uuid
from pathlib import Path

import mysql.connector
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as web
import db


def test_hashtag_normalization_and_limits():
    assert web.parse_hashtags('#Travel #travel #여행 #사진_1 plain') == ['travel', '여행', '사진_1']
    assert web.parse_hashtags('word#ignored #valid') == ['valid']
    with pytest.raises(ValueError):
        web.parse_hashtags('#' + 'x' * 51)
    with pytest.raises(ValueError):
        web.parse_hashtags(' '.join('#t' + str(i) for i in range(31)))


@pytest.fixture
def site(monkeypatch, tmp_path):
    if not os.getenv('TEST_MYSQL_PORT'):
        pytest.skip('Set TEST_MYSQL_PORT for isolated real-MySQL integration tests')
    config = dict(host=os.getenv('TEST_MYSQL_HOST', '127.0.0.1'),
                  port=int(os.environ['TEST_MYSQL_PORT']),
                  user=os.getenv('TEST_MYSQL_USER', 'root'),
                  password=os.getenv('TEST_MYSQL_PASSWORD', ''))
    database = 'instcopy_test_' + uuid.uuid4().hex
    connection = mysql.connector.connect(**config)
    cur = connection.cursor()
    cur.execute(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    cur.execute(f'USE `{database}`')
    schema = (Path(web.BASE) / 'schema.sql').read_text()
    schema = '\n'.join(line for line in schema.splitlines() if not line.startswith('--'))
    # The first two statements select the application's database; use our isolated one.
    statements = schema.split(';')[2:]
    try:
        # Applying twice also verifies idempotent schema initialization.
        for _ in range(2):
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
        connection.commit()
        monkeypatch.setattr(db, 'connect', lambda: mysql.connector.connect(**config, database=database))
        monkeypatch.setattr(web, 'UPLOADS', tmp_path)
        with TestClient(web.app) as client:
            yield client
    finally:
        cur.execute(f'DROP DATABASE `{database}`')
        cur.close()
        connection.close()


def token(client, path='/posts/new'):
    response = client.get(path)
    assert response.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def signup(client, user='alice'):
    response = client.post('/signup', data=dict(user_id=user, display_name=user,
        password='password123', csrf=token(client, '/signup')), follow_redirects=False)
    assert response.status_code == 303


def upload(client, caption='A photo #여행', hashtags='#Travel #travel'):
    image = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(image, format='PNG')
    response = client.post('/posts', data=dict(caption=caption, hashtags=hashtags, csrf=token(client)),
        files={'image': ('photo.png', image.getvalue(), 'image/png')}, follow_redirects=False)
    assert response.status_code == 303
    return response.headers['location']


def action(client, path, name):
    return client.post(path + '/' + name, data={'csrf': token(client)}, follow_redirects=False)


def test_like_save_and_cancel_are_idempotent(site):
    signup(site)
    path = upload(site)
    for name in ('like', 'like', 'save', 'save'):
        assert action(site, path, name).status_code == 303
    page = site.get(path)
    assert '좋아요 취소 · 1' in page.text and '저장 취소' in page.text
    assert 'A photo' in site.get('/saved').text
    for name in ('unlike', 'unlike', 'unsave', 'unsave'):
        assert action(site, path, name).status_code == 303
    assert '좋아요 · 0' in site.get(path).text
    assert '게시물이 없습니다.' in site.get('/saved').text


def test_tags_search_and_escaping(site):
    signup(site)
    path = upload(site, 'hello <script>alert(1)</script> #여행 100%_')
    assert [r['name'] for r in db.all_rows('SELECT name FROM hashtags ORDER BY name')] == ['travel', '여행']
    assert path in site.get('/tags/여행').text
    assert path in site.get('/tags/TRAVEL').text
    assert path in site.get('/search', params={'q': '100%_'}).text
    assert '@alice' in site.get('/search', params={'q': 'alice'}).text
    assert '#travel' in site.get('/search', params={'q': '#travel'}).text
    assert path not in site.get('/search', params={'q': "' OR 1=1 --"}).text
    assert '<script>alert(1)</script>' not in site.get(path).text
    assert site.get('/search', params={'q': 'x' * 101}).status_code == 400
    assert site.get('/search').status_code == 200


def test_actions_require_login_csrf_and_existing_post(site):
    for name in ('like', 'unlike', 'save', 'unsave'):
        assert site.post('/posts/1/' + name, data={'csrf': 'fake'}).status_code == 403
    for path in ('/saved', '/search', '/tags/travel'):
        assert site.get(path, follow_redirects=False).headers['location'] == '/login'
    # A valid anonymous CSRF token must still not allow writes.
    csrf = token(site, '/login')
    for name in ('like', 'unlike', 'save', 'unsave'):
        response = site.post('/posts/1/' + name, data={'csrf': csrf}, follow_redirects=False)
        assert response.headers['location'] == '/login'
    signup(site)
    for name in ('like', 'unlike', 'save', 'unsave'):
        assert site.post('/posts/1/' + name, data={'csrf': 'fake'}).status_code == 403
        assert action(site, '/posts/999999', name).status_code == 404


def test_saved_posts_are_private_and_feed_follows_existing_rules(site):
    signup(site, 'alice')
    alice_post = upload(site, 'alice private save #shared')
    action(site, alice_post, 'save')
    action(site, '', 'logout')
    signup(site, 'bobby')
    bob_post = upload(site, 'bob own photo #shared')
    assert 'alice private save' not in site.get('/feed').text
    assert 'bob own photo' in site.get('/feed').text
    assert 'alice private save' not in site.get('/saved').text
    assert site.post('/users/alice/follow', data={'csrf': token(site)}).status_code == 200
    assert 'alice private save' in site.get('/feed').text
    assert 'bobby' in site.get('/users/alice/connections').text
    assert site.post('/users/alice/unfollow', data={'csrf': token(site)}).status_code == 200
    assert 'alice private save' not in site.get('/feed').text
    assert bob_post in site.get('/users/bobby').text
    response = site.post(alice_post + '/comments', data={'csrf': token(site), 'body': '@alice 멋져요!'})
    assert response.status_code == 200
    assert 'href="/users/alice">@alice</a> 멋져요!' in response.text


def test_account_password_change_and_login(site):
    signup(site)
    response = site.post('/settings/password', data={'csrf': token(site),
        'old_password': 'password123', 'new_password': 'changed123'})
    assert '비밀번호가 변경됐습니다.' in response.text
    action(site, '', 'logout')
    response = site.post('/login', data={'csrf': token(site, '/login'),
        'user_id': 'alice', 'password': 'password123'})
    assert response.status_code == 401
    response = site.post('/login', data={'csrf': token(site, '/login'),
        'user_id': 'alice', 'password': 'changed123'}, follow_redirects=False)
    assert response.status_code == 303


def test_invalid_tags_and_failed_transaction_leave_no_post_or_file(site, monkeypatch):
    signup(site)
    image = io.BytesIO()
    Image.new('RGB', (4, 4)).save(image, format='PNG')
    response = site.post('/posts', data={'csrf': token(site), 'hashtags': '#' + 'x' * 51},
        files={'image': ('photo.png', image.getvalue(), 'image/png')})
    assert response.status_code == 400
    assert db.one('SELECT COUNT(*) AS n FROM posts')['n'] == 0
    db.change('DROP TABLE post_hashtags')
    with pytest.raises(mysql.connector.Error):
        upload(site)
    assert db.one('SELECT COUNT(*) AS n FROM posts')['n'] == 0
    assert list(web.UPLOADS.iterdir()) == []


def test_deleting_post_cascades_relations(site):
    signup(site)
    path = upload(site)
    action(site, path, 'like')
    action(site, path, 'save')
    post_id = int(path.rsplit('/', 1)[1])
    db.change('DELETE FROM posts WHERE post_id=%s', (post_id,))
    for table in ('likes', 'saved_posts', 'post_hashtags'):
        assert db.one(f'SELECT COUNT(*) AS n FROM {table}')['n'] == 0


def test_collation_equivalent_tags_do_not_break_upload(site):
    signup(site)
    path = upload(site, 'photo', '#cafe #café')
    assert site.get(path).status_code == 200
    assert db.one('SELECT COUNT(*) AS n FROM post_hashtags')['n'] == 1


def test_migration_preserves_existing_posts_and_is_repeatable(site):
    signup(site)
    path = upload(site, 'existing post', '')
    for table in ('post_hashtags', 'hashtags', 'likes', 'saved_posts'):
        db.change(f'DROP TABLE {table}')
    script = (Path(web.BASE) / 'migrations/001_social_features.sql').read_text()
    script = '\n'.join(line for line in script.splitlines() if not line.startswith('--'))
    # Keep the isolated test database selected, not the migration's default USE.
    statements = script.split(';')[1:]
    for _ in range(2):
        with db.cursor_for(write=True) as cur:
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
    assert db.one('SELECT COUNT(*) AS n FROM users')['n'] == 1
    assert db.one('SELECT COUNT(*) AS n FROM posts')['n'] == 1
    assert 'existing post' in site.get(path).text
    assert action(site, path, 'like').status_code == 303
