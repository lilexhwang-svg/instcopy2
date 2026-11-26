# instcopy — FastAPI 로컬 실행

Python 3.10 이상(3.12 권장)과 실행 중인 MySQL Server가 필요합니다.
MySQL Workbench는 선택 사항입니다.

1. ZIP 전체를 새 폴더에 압축 해제합니다. 개별 파일을 따로 내려받지 마세요.
2. run.bat을 더블클릭합니다. 첫 실행에는 Python 패키지 설치를 위해 인터넷이 필요합니다.
3. MySQL 로그인이 실패하면 화면에 사용자 이름과 비밀번호를 입력합니다.
   사용자 이름이 root이면 Enter를 누르고 본인의 실제 MySQL 비밀번호를 입력하세요.
   연결에 성공한 정보는 .env에 저장되어 다음 실행부터 재사용됩니다.
4. 브라우저에서 http://127.0.0.1:8001 에 접속해 회원가입합니다.

## .env 파일

instagram_db_first/.env가 ZIP에 실제로 포함되어 있습니다.
기본값은 DB_HOST=127.0.0.1, DB_PORT=3306, DB_USER=root,
DB_PASSWORD는 빈 값, DB_NAME=instagram_term_2026입니다.
비밀번호나 포트가 다르면 .env를 메모장으로 수정할 수도 있습니다.
.env를 지우더라도 기본 파일이 다시 만들어지며 기존 .env는 덮어쓰지 않습니다.

## FastAPI 직접 실행

한 번 run.bat으로 환경과 DB 설정을 마친 뒤, instagram_db_first 폴더에서:

    .venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001

run.bat도 같은 FastAPI 앱을 Uvicorn으로 실행합니다.
처음 생성하는 DB와 예전 DB의 테이블/누락 컬럼은 서버 시작 시 보완됩니다.
.env의 MySQL 계정에는 이 프로젝트 DB의 생성/테이블 변경 권한이 필요합니다.

## 포함 기능

게시물 좋아요·취소, 해시태그, 게시물 저장·취소, ID/닉네임·게시물·해시태그 검색,
좋아요한 게시물 목록, 멘션 링크, 본인 댓글 삭제, 댓글 좋아요·취소, 프로필 수정.

HTML은 instagram_db_first/templates, CSS는 static, 사진은 uploads에 있습니다.
프로젝트 폴더 구조를 유지하세요. 회원·게시물 등은 MySQL에, 사진은 uploads에 저장됩니다.
다른 PC로 옮길 때는 .venv를 복사하지 말고 run.bat으로 새로 만드세요.
