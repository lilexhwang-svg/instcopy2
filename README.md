# Instagram DB Project

## 다른 장소의 컴퓨터에서 같은 MySQL DB 사용하기

여러 PC가 같은 DB를 사용하려면 외부에서 접속 가능한 MySQL 서버가 필요합니다.
`127.0.0.1`과 `localhost`는 접속하는 PC 자신을 의미하므로, 서로 다른 PC의 DB를 연결하는 주소로 사용할 수 없습니다.
MySQL Workbench는 DB 접속 프로그램이며 원격 DB 서버를 제공하지 않습니다.

1. `instagram_db_first/.env.example`을 같은 폴더에 `.env`라는 이름으로 복사합니다.
2. 원격 MySQL 서버의 접속 정보를 `.env`에 입력합니다. Workbench에도 아래 표와 같은 값을 입력합니다.
3. 각 PC에서 같은 서버와 DB 이름을 사용하고, `run.bat`을 실행합니다.

| Workbench 항목 | 프로젝트 설정 |
| --- | --- |
| Connection Name | `asdf` 등 화면에 표시할 이름 |
| Hostname | `DB_HOST` |
| Port | `DB_PORT` |
| Username | `DB_USER` |
| Password | `DB_PASSWORD` |
| Default Schema | `DB_NAME` |

실제 비밀번호가 들어간 `.env`는 GitHub에 올리지 않습니다. 원격 연결에 실패하면 오류를 표시하며 로컬 DB로 자동 변경하지 않습니다.
서버 시작 시 설정된 `DB_NAME`에 스키마와 누락 컬럼을 보완하며 기존 데이터는 보존합니다.
앱 화면에 접속하는 `http://127.0.0.1:8001`과 MySQL 서버 주소는 서로 다른 설정입니다.

사진은 각 앱의 `uploads` 폴더에 저장됩니다. 여러 PC에서 사진까지 함께 보려면 같은 앱 서버를 사용하거나 사진 저장소를 공유해야 합니다.

## 다른 컴퓨터에서 Python 경로 오류가 날 때

`did not find executable at C:\Users\user\...\Python314\python.exe`는 복사된 `.venv`가 이전 컴퓨터의 Python 설치 경로를 찾다가 실패한 것입니다. 이 압축에 포함됐던 `.venv/pyvenv.cfg`에 실제로 해당 경로가 들어 있었습니다. 웹 서버와 MySQL에 연결하기 전, Python 패키지 설치 단계에서 발생한 오류입니다.

이 PC 공유용 수정본은 `.venv`를 제외했습니다. `run.bat`은 현재 컴퓨터의 Python 3.10 이상이 실제로 실행되는지 먼저 확인하고, `bootstrap_env.py`로 새 가상환경을 만듭니다. 기존 `.venv`를 실행할 수 없으면 `.venv.old-날짜시간`으로 백업한 뒤 새로 생성하며 `.env`와 `uploads`는 건드리지 않습니다.

1. 현재 컴퓨터에 Python 3.10 이상이 설치되어 있어야 합니다. `py -3 --version` 또는 `python --version`으로 확인할 수 있습니다.
2. 수정 ZIP 전체를 **새 폴더**에 압축 해제하고 `run.bat`을 실행합니다. ZIP 내부에서 바로 실행하지 마세요.
3. 필요한 패키지를 설치한 후 기존 `run_local.py`가 MySQL 설정과 서버 실행을 이어갑니다. 첫 실행의 패키지 설치에는 인터넷이 필요합니다.
4. 기존 작업 폴더의 설정과 사진을 유지하려면 기존 `.env`와 `uploads`를 새 `instagram_db_first` 폴더로 복사할 수 있습니다. DB 정보는 실행하는 컴퓨터의 MySQL과 일치해야 합니다.

현재 압축을 직접 고치려면 `instagram_db_first/.venv`의 이름을 `.venv_old`로 바꾼 뒤 기존 `run.bat`을 다시 실행해도 됩니다. 다른 컴퓨터로 전달할 때는 `.venv`를 압축에 넣지 마세요.

DB/패키지 설치 없이 가상환경 생성·재사용만 확인하려면 `run.bat --prepare-only`를 실행합니다.

근거: [Python 공식 venv 문서](https://docs.python.org/3/library/venv.html)는 가상환경을 다른 위치나 컴퓨터로 복사하기보다 목적지에서 다시 생성하도록 안내합니다.

MySQL을 중심으로 구현한 인스타그램 형태의 사진 공유 웹 서비스입니다.  
데이터베이스 수업 텀프로젝트로, 테이블 간 관계와 SQL을 활용해 주요 기능을 구현했습니다.

## 기술 스택

- **Backend:** Python, FastAPI
- **Frontend:** HTML, CSS, Jinja2
- **Database:** MySQL

## 주요 기능

- 회원가입, 로그인, 비밀번호 변경
- 사용자 팔로우 및 팔로워·팔로잉 목록 조회
- 사진과 설명을 포함한 게시물 작성
- 댓글 작성 및 `@아이디` 멘션
- 내 게시물과 팔로우한 사용자의 게시물을 최신순으로 보여주는 홈 피드
- 사용자 프로필 및 게시물 조회

## 데이터베이스 구성

| 테이블 | 역할 |
| --- | --- |
| `users` | 회원·프로필 정보 |
| `posts` | 게시물 및 이미지 경로 |
| `comments` | 게시물 댓글 |
| `follows` | 사용자 간 팔로우 관계 |
| `likes` | 게시물 좋아요 |
| `saved_posts` | 개인별 게시물 저장 |
| `hashtags` | 해시태그 정보 |
| `post_hashtags` | 게시물과 해시태그 연결 |
| `comment_likes` | 댓글 좋아요 |

기본키(PK), 외래키(FK), 복합키, CHECK 제약조건과 `ON DELETE CASCADE`를 적용했습니다.
회원·게시물·댓글·팔로우 등의 데이터는 MySQL에 저장하고, 이미지 파일은 별도로 저장합니다.

## 추가 개발 예정

좋아요, 해시태그, 프로필 수정 등 부가 기능을 추가할 계획입니다.


## 추가 기능

아래 기능을 추가해 현재 코드에 반영했습니다.

- 게시물 좋아요·취소 및 좋아요 수 확인
- 해시태그 등록과 태그별 게시물 조회
- 게시물 저장·취소 및 개인 저장 목록
- 사용자 ID·닉네임, 게시물 설명, 해시태그 통합 검색
- 내가 좋아요한 게시물 목록 조회
- 댓글의 `@아이디`를 클릭해 프로필로 이동
- 본인 댓글 삭제
- 댓글 좋아요·취소 및 좋아요 수 확인
- 닉네임·소개글·프로필 사진 수정

[변경 코드 비교 이미지](change-review/)
