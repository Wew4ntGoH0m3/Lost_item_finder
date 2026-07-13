# LostLink Backend

학교·행사장 안의 분실글과 아직 주인을 찾지 못한 습득글을 자동 비교하는 Flask 백엔드입니다. Flutter 앱에서 게시글을 등록하면 Celery 작업이 실행되고, `FoundPost.status = STORED`인 데이터만 LLM 또는 규칙 기반 점수로 분석해 `Match`를 생성합니다.

## 주요 기능

- JWT 회원가입, 로그인, 토큰 갱신, 사용자·관리자 권한
- 분실글과 습득글 CRUD 및 시설·카테고리·장소 필터
- EC2 로컬 디스크 이미지 업로드와 Nginx 정적 제공
- 분실글 또는 습득글 등록 직후 Celery 자동 분석
- OpenAI 호환 LLM 구조화 응답과 서버 측 ID·배점 재검증
- LLM 키가 없거나 외부 API가 실패해도 동작하는 `rule-v1` 점수 방식
- 수령 요청, 습득자 확인, 관리자 인계 완료 상태 전이
- PostgreSQL, Redis, API, Worker, Nginx Docker Compose
- GitHub Actions 테스트·이미지 빌드·EC2 자동 배포

전체 기능 명세는 [docs/API_SPEC.md](docs/API_SPEC.md)를 참고하세요.

## 기술 구성

| 영역 | 구성 |
|---|---|
| API | Python 3.12, Flask, Gunicorn |
| 인증 | Flask-JWT-Extended |
| DB | PostgreSQL 16, SQLAlchemy, Alembic |
| 비동기 분석 | Celery, Redis |
| AI | OpenAI-compatible Chat Completions API |
| 파일 | EC2 bind mount, Nginx `/uploads/` |
| 배포 | Docker Compose, GitHub Actions |

## 로컬 실행

```bash
cp .env.example .env
mkdir -p data/uploads
docker compose up -d --build
curl http://127.0.0.1/healthz
```

`.env`의 `SECRET_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`는 반드시 변경해야 합니다.

관리자 생성:

```bash
docker compose exec api flask create-admin \
  --email admin@example.com \
  --site-code SCHOOL_001
```

테스트:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/python -m pytest --cov=app
```

## 자동 매칭 흐름

1. 분실글 또는 습득글을 DB에 저장하고 트랜잭션을 커밋합니다.
2. Celery가 등록된 게시글의 분석 작업을 가져갑니다.
3. 같은 `site_code`, 올바른 시간 범위, `status = STORED` 조건으로 후보를 최대 100개 조회합니다.
4. `LLM_API_KEY`가 있으면 최소 필드만 LLM에 전달해 항목별 점수와 이유를 받습니다.
5. Flask가 후보 ID, 항목별 최대 배점, 총점을 다시 검증합니다.
6. 50점 이상만 `Match`로 upsert하고 앱 API에서 점수순으로 제공합니다.
7. LLM 장애 시 같은 요청 안에서 `rule-v1` 점수 방식으로 자동 전환합니다.

점수는 물건 종류 30점, 색상 15점, 장소 20점, 시간 15점, 특징 20점으로 총 100점입니다.

## 이미지 저장

`POST /api/v1/uploads/images`에 `multipart/form-data`의 `image` 필드로 JPEG, PNG, WebP 파일을 전송합니다. 응답의 `/uploads/{uuid}.{ext}` URL을 게시글 `imageUrl`에 저장하면 됩니다.

Compose는 `${UPLOADS_PATH:-./data/uploads}`를 API의 `/data/uploads`와 Nginx에 동시에 마운트합니다. EC2에서는 다음처럼 별도 경로를 사용할 수 있습니다.

```env
UPLOADS_PATH=/home/ec2-user/lostlink-uploads
```

이 경로는 컨테이너를 재생성해도 유지됩니다. EC2 사용자 UID가 쓸 수 있도록 디렉터리를 미리 생성하세요.

```bash
mkdir -p /home/ec2-user/lostlink-uploads
```

## API 요약

| Method | Endpoint | 기능 |
|---|---|---|
| POST | `/api/v1/auth/signup` | 회원가입 |
| POST | `/api/v1/auth/login` | 로그인 |
| POST | `/api/v1/auth/refresh` | Access Token 갱신 |
| POST | `/api/v1/uploads/images` | 이미지 업로드 |
| POST/GET | `/api/v1/lost-posts` | 분실글 생성·목록 |
| POST/GET | `/api/v1/found-posts` | 습득글 생성·미주인 목록 |
| POST | `/api/v1/lost-posts/{id}/matches/analyze` | 수동 재분석 |
| GET | `/api/v1/matches/lost-posts/{id}` | 분실글 기준 후보 |
| POST | `/api/v1/matches/{id}/claims` | 수령 요청 |
| PATCH | `/api/v1/matches/{id}/verify` | 습득자·관리자 확인 |
| PATCH | `/api/v1/matches/{id}/handover` | 관리자 인계 완료 |

인증 API는 `Authorization: Bearer {accessToken}` 헤더를 사용합니다.

## EC2 배포

PostgreSQL을 수동 `docker run`으로 먼저 생성했다면 Compose 전환 전에 컨테이너만 제거합니다. `postgres_data` 볼륨은 제거하지 않습니다.

```bash
docker rm -f postgres
cp .env.example .env
mkdir -p data/uploads
docker compose -p lostlink up -d --build
docker compose -p lostlink ps
```

Compose의 PostgreSQL 호스트 포트는 외부 노출 대신 `127.0.0.1:5433`에만 바인딩됩니다. API 컨테이너는 Docker 내부 네트워크의 `db:5432`로 연결됩니다.

## GitHub Actions 배포 설정

저장소의 Actions secrets에 다음 값을 등록하면 `BE` 브랜치의 검사 성공 후 EC2로 자동 배포됩니다.

| Secret | 설명 |
|---|---|
| `EC2_HOST` | EC2 공개 IP 또는 도메인 |
| `EC2_USER` | SSH 사용자 |
| `EC2_PASSWORD` | SSH 비밀번호. 가능하면 추후 SSH 키로 전환 |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 |
| `SECRET_KEY` | Flask 비밀키 |
| `JWT_SECRET_KEY` | JWT 서명키 |
| `LLM_API_KEY` | 선택값. 비어 있으면 규칙 기반 분석 |

배포 워크플로는 `$HOME/Dorm_lost_item_finder`에서 `BE` 브랜치를 갱신하고 `.env`를 서버에만 생성한 후 `docker compose up -d --build`를 실행합니다.

## 운영 보안

- `.env`, DB 비밀번호, EC2 비밀번호, LLM 키는 Git에 커밋하지 않습니다.
- AWS 보안 그룹은 API용 80/443과 관리용 22만 필요한 출발지에 허용합니다.
- PostgreSQL 5433과 Redis 6379는 인터넷에 공개하지 않습니다.
- 현재 비밀번호 SSH는 초기 배포용이며 운영 전 SSH 키 인증으로 전환하는 것이 좋습니다.
