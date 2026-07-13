# LostLink Backend

학교·행사장의 분실글과 습득글을 동일 카테고리 태그로 먼저 조회한 뒤 AI로 비교하고, 매칭 당사자를 실시간 채팅으로 연결하는 Flask 백엔드입니다.

상세 기획과 API·Socket.IO 명세는 [docs/API_SPEC.md](docs/API_SPEC.md), Postman Collection v2.1은 [LostLink.postman_collection.json](LostLink.postman_collection.json), HTTP HAR는 [har1.2.json](har1.2.json)을 참고하세요.

## 핵심 기능

- 로그인, Access/Refresh JWT, 게시글 소유권·관리자 권한
- 회원가입 API 유지, 모바일 앱 회원가입 화면 제외, Postman으로 시연 계정 생성
- `CARD`, `WALLET`, `EARPHONE` 등 10개 공통 `ItemCategory` Enum
- 같은 시설·카테고리·유효 상태·시간 범위의 후보만 SQL에서 조회
- Ollama `qwen3:4b` 분석, 실패 시 `rule-v1` 자동 대체
- 수령 요청 시 분실자·습득자 전용 채팅방 자동 생성
- Socket.IO 실시간 메시지·입력 상태·읽음 처리와 PostgreSQL 메시지 저장
- Redis/Celery 비동기 분석, EC2 이미지 저장, Docker Compose 배포

## 기술 구성

| 영역 | 구성 |
|---|---|
| API | Python 3.12, Flask, Gunicorn |
| 인증 | Flask-JWT-Extended, Access/Refresh JWT |
| 실시간 채팅 | Flask-SocketIO, WebSocket, Redis message queue |
| DB | PostgreSQL 16, SQLAlchemy, Alembic |
| 비동기 분석 | Celery, Redis |
| AI | Ollama native `/api/chat`, `qwen3:4b` |
| 파일 | EC2 bind mount, Nginx `/uploads/` |
| 배포 | Docker Compose, GitHub Actions |

## 로컬 실행

```bash
cp .env.example .env
mkdir -p data/uploads
docker compose up -d --build
curl http://127.0.0.1/healthz
curl http://127.0.0.1/api/v1/categories
```

`.env`의 `SECRET_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`를 변경해야 합니다. Ollama가 없으면 `OLLAMA_ENABLED=false`로 두면 규칙 기반 분석만 사용합니다.

테스트:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/python -m pytest --cov=app
```

## 인증 운영

백엔드는 HTTP 호출 도구를 구분할 수 없으므로 `/api/v1/auth/signup` 자체는 공개 상태로 유지합니다. 해커톤 앱에는 회원가입 화면과 호출 코드를 넣지 않고, 시연 담당자가 Postman으로 분실자·습득자 계정을 미리 생성합니다. 앱은 로그인만 제공하고 보호 API에 `Authorization: Bearer {accessToken}`을 전송합니다.

## ItemCategory 태그

| 코드 | 의미 |
|---|---|
| `CARD` | 카드, 학생증, 신분증 |
| `WALLET` | 지갑, 카드지갑 |
| `EARPHONE` | 이어폰, 에어팟, 이어폰 케이스 |
| `BAG` | 가방, 백팩, 파우치 |
| `KEY` | 열쇠, 키링 |
| `ELECTRONICS` | 휴대폰, 태블릿, 노트북 |
| `CLOTHING` | 옷, 모자, 장갑 |
| `UMBRELLA` | 우산 |
| `STATIONERY` | 필통, 펜, 노트 |
| `ETC` | 기타 |

앱은 `GET /api/v1/categories` 응답으로 선택 UI를 구성합니다. 분실 태그가 `CARD`이면 다른 태그의 습득글은 AI 입력 후보에도 포함하지 않습니다.

```sql
SELECT *
FROM found_posts
WHERE site_code = :site_code
  AND status = 'STORED'
  AND category = :lost_category
  AND found_at >= :lost_at;
```

## 채팅 흐름

1. 분실자가 매칭 후보에 수령 요청을 보냅니다.
2. 서버가 해당 Match의 분실자·습득자 멤버십으로 채팅방을 자동 생성합니다.
3. 앱은 `/socket.io`에 Access Token으로 연결하고 `join_chat`으로 방에 입장합니다.
4. `send_message` 메시지는 PostgreSQL에 먼저 저장된 뒤 양쪽 앱으로 전송됩니다.
5. 재접속 시 `GET /api/v1/chats`와 `/chats/{id}/messages`로 상태를 복원합니다.
6. 매칭이 거절되거나 인계 완료되면 기존 내역은 조회할 수 있지만 새 메시지는 보낼 수 없습니다.

Socket.IO 연결 인증:

```json
{
  "auth": {
    "token": "{accessToken}"
  }
}
```

주요 이벤트는 `join_chat`, `leave_chat`, `send_message`, `typing`, `mark_read`이며 서버 수신 이벤트는 `connected`, `new_message`, `typing`, `messages_read`입니다.

## API 요약

| Method | Endpoint | 권한 | 기능 |
|---|---|---|---|
| POST | `/api/v1/auth/signup` | 공개, Postman 설정용 | 시연 계정 생성 |
| POST | `/api/v1/auth/login` | 공개 | Access/Refresh JWT 발급 |
| GET | `/api/v1/categories` | 공개 | Enum 태그 목록 |
| POST/GET | `/api/v1/lost-posts` | 생성 JWT / 목록 공개 | 분실글 생성·조회 |
| POST/GET | `/api/v1/found-posts` | 생성 JWT / 목록 공개 | 습득글 생성·조회 |
| GET | `/api/v1/matches/lost-posts/{id}` | 작성자·관리자 | 동일 태그 매칭 후보 |
| POST | `/api/v1/matches/{id}/claims` | 분실글 작성자 | 수령 요청·채팅방 생성 |
| PATCH | `/api/v1/matches/{id}/verify` | 습득자·관리자 | 본인 확인 |
| PATCH | `/api/v1/matches/{id}/handover` | 관리자 | 인계 완료 |
| GET | `/api/v1/chats` | JWT | 내 채팅방 목록 |
| GET | `/api/v1/chats/{id}/messages` | 채팅 참여자 | 메시지 내역 |
| PATCH | `/api/v1/chats/{id}/read` | 채팅 참여자 | 읽음 위치 갱신 |

## 배포

Nginx는 `/socket.io/`의 Upgrade 헤더를 API에 전달합니다. API는 WebSocket 연결 유지를 위해 Gunicorn 1 worker·thread 모드로 실행하고, Socket.IO와 Celery가 Redis를 함께 사용합니다.

```bash
docker compose -p lostlink up -d --build
docker compose -p lostlink ps
```

`BE` 브랜치에 푸시하면 GitHub Actions가 Ruff와 Pytest를 통과한 뒤 EC2 Compose를 재배포합니다. PostgreSQL 호스트 포트는 `127.0.0.1:5433`에만 바인딩됩니다.
