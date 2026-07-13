# LostLink 해커톤 백엔드 기획 및 API 명세

## 1. 최종 결정

| 항목 | 결정 |
|---|---|
| 핵심 기능 | 분실글과 습득글을 같은 카테고리 태그로 먼저 좁힌 뒤 AI로 비교 |
| 인증 | 로그인과 Access/Refresh JWT 유지 |
| 사용자 유형 | 단일 `User`, `role` 및 관리자 없음 |
| 회원가입 | API는 유지하되 모바일 앱에는 화면을 만들지 않고 Postman에서 테스트 계정 생성 |
| 카테고리 | 별도 테이블 없이 공통 `ItemCategory` Enum 태그 사용 |
| 데이터베이스 | PostgreSQL 16, SQLAlchemy, Alembic |
| 비동기 분석 | Redis + Celery |
| AI | Ollama `qwen3-vl:4b`, 습득글 자동 작성과 매칭 분석 모두 `think: false` |
| 이미지 | Base64 미사용, multipart 업로드 후 EC2 디스크 저장·Nginx 제공 |
| 실시간 채팅 | Flask-SocketIO + Redis, 매칭 당사자 전용 |
| 핵심 테이블 | `users`, `lost_posts`, `found_posts`, `matches`, `chat_rooms`, `chat_messages` |

서비스의 핵심 설명:

> 같은 시설에서 같은 카테고리 태그를 가진 데이터만 SQL로 조회하고, 그 후보만 AI가 비교하여 매칭률과 이유를 생성한다.

## 2. 피드백 반영 내용

| 항목 | 적용 내용 | 목적 |
|---|---|---|
| 회원가입 UI | 모바일 앱 범위에서 제외 | 해커톤 핵심 화면과 개발 시간에 집중 |
| 로그인·JWT | 기존 기능 유지 | 게시글 작성자 권한과 비공개 특징 보호 |
| 사용자 구분 | 모든 계정은 동일한 일반 사용자 | 한 사용자가 분실글·습득글 모두 작성 가능 |
| 회원가입 API | `POST /api/v1/auth/signup` 유지 | Postman에서 시연 계정을 사전 생성 |
| 자유 문자열 카테고리 | `ItemCategory` Enum으로 제한 | 오타와 표현 차이 방지 |
| 습득글 내용 입력 | 공개 사실만 받고 제목·특징·설명은 LLM 자동 생성 | 작성 부담과 임의 추측 최소화 |
| 전체 후보 조회 | 동일 시설·동일 태그·다른 작성자·상태·시간 조건 SQL 선필터 | 자기 게시글과 다른 물건 혼입 및 LLM 입력량 감소 |
| AI | Ollama `qwen3-vl:4b` 사용 | 별도 외부 API 키 없이 시연 |
| 채팅 | 수령 요청 후 당사자 전용 Socket.IO 방 생성 | 앱 내 연락과 대화 내역 보존 |

### “Postman 회원가입”의 정확한 의미

백엔드는 Postman과 모바일 앱을 기술적으로 구분하지 않는다. HTTP 요청은 동일하기 때문이다. 따라서 다음 규칙으로 운영한다.

1. 모바일 앱에는 회원가입 화면과 회원가입 API 호출 코드를 만들지 않는다.
2. 개발자 또는 시연 담당자가 Postman으로 `/auth/signup`을 호출해 계정을 만든다.
3. 앱에는 로그인 화면만 제공한다.
4. 로그인 후 받은 Access Token으로 보호 API를 호출한다.
5. Access Token 만료 시 Refresh Token으로 갱신한다.

실제 운영 서비스로 전환할 때는 초대 코드나 회원가입 차단 설정 등을 별도로 추가한다.

### 단일 사용자 원칙

`User`에는 `role` 컬럼이 없으며 관리자, 분실자, 습득자 계정 종류를 구분하지 않는다. 모든 사용자는 `POST /lost-posts`와 `POST /found-posts`를 모두 호출할 수 있다.

명세에서 사용하는 “분실글 작성자”와 “습득글 작성자”는 고정 역할이 아니다. 특정 Match에 연결된 두 게시글의 `user_id`를 뜻하며, 같은 사용자가 상황에 따라 양쪽 게시글을 작성할 수 있다.

## 3. 시스템 구성

```text
Mobile App
    |  Login + Bearer JWT / Socket.IO
    v
Nginx :80
    |----------------------> /uploads/* (EC2 디스크 읽기)
    v
Flask API :8000
    |---- PostgreSQL 16 (사용자, 게시글, 매칭, 채팅)
    |---- Redis (Celery 브로커, Socket.IO message queue)
    `---- Celery Worker
              |
              `---- Ollama 100.102.0.2:11434 / qwen3-vl:4b
```

### 습득글 자동 작성 및 분석 처리

1. Flask가 JWT 사용자, 입력값, Enum 태그를 검증한다.
2. 습득글이면 `category`, `color`, `location`, `foundAt`, `observations`만 Ollama에 전달한다.
3. Ollama가 `title`, `features`, `description`을 JSON으로 작성한다. `think`는 끈다.
4. 생성 결과가 근거 검증을 통과하지 못하면 공개 사실 기반 템플릿으로 대체한다.
5. 게시글과 원본 관찰 정보, 생성기 버전을 PostgreSQL에 저장한다.
6. Celery 분석 작업을 큐에 넣고 API는 `201`을 반환한다.
7. Worker가 동일 태그 후보만 SQL로 조회한다.
8. 후보가 있으면 Ollama에 공개 필드만 전달하고 후보 ID와 점수를 검증한다.
9. 매칭 Ollama 장애 시 `rule-v1`으로 대체한다.
10. 총점 50점 이상만 `matches`에 저장한다.

## 4. ItemCategory Enum 태그

분실글과 습득글의 `category` 컬럼은 같은 Enum을 사용한다. DB CHECK 제약으로 허용되지 않은 값의 저장도 막는다.

| Enum | 앱 표시 | 포함 예시 |
|---|---|---|
| `CARD` | 카드/학생증 | 학생증, 신분증, 체크카드 |
| `WALLET` | 지갑 | 반지갑, 카드지갑 |
| `EARPHONE` | 이어폰 | 에어팟, 이어폰, 이어폰 케이스 |
| `BAG` | 가방 | 백팩, 에코백, 파우치 |
| `KEY` | 열쇠/키링 | 열쇠, 키링 |
| `ELECTRONICS` | 전자기기 | 휴대폰, 태블릿, 노트북 |
| `CLOTHING` | 의류 | 옷, 모자, 장갑 |
| `UMBRELLA` | 우산 | 장우산, 접이식 우산 |
| `STATIONERY` | 문구류 | 필통, 펜, 노트 |
| `ETC` | 기타 | 위 분류에 속하지 않는 물건 |

앱은 `GET /api/v1/categories`의 결과로 선택 UI를 만든다. 에어팟 케이스와 이어폰은 모두 `EARPHONE` 태그로 등록한다.

허용되지 않은 태그는 `422 INVALID_CATEGORY`로 거절한다.

## 5. 데이터 모델

### 5.1 User

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `email` | VARCHAR(255) | Y | 로그인 ID, UNIQUE |
| `password_hash` | VARCHAR(255) | Y | 해시 비밀번호 |
| `nickname` | VARCHAR(20) | Y | 표시 이름 |
| `profile_image_url` | VARCHAR(500) | N | 프로필 이미지 |
| `is_active` | BOOLEAN | Y | 계정 활성 상태 |
| `created_at` | DATETIME | Y | 생성 시각 |
| `updated_at` | DATETIME | Y | 수정 시각 |

### 5.2 LostPost

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `user_id` | BIGINT | Y | FK -> `users.id`, 작성자 |
| `title` | VARCHAR(100) | Y | LLM 또는 근거 템플릿으로 생성된 제목 |
| `category` | `ItemCategory` Enum | Y | 후보 선필터 태그 |
| `color` | VARCHAR(30) | Y | 대표 색상 |
| `location` | VARCHAR(100) | Y | 분실 위치 |
| `lost_at` | DATETIME | Y | 분실 추정 시각 |
| `features` | TEXT | Y | 자동 생성된 공개 특징 |
| `source_observations` | TEXT | Y | 사용자가 입력한 공개 관찰 사실, 작성자에게만 반환 |
| `content_generator` | VARCHAR(100) | Y | `ollama:{model}` 또는 `grounded-template-v1` |
| `private_feature` | TEXT | N | 작성자에게만 반환 |
| `description` | TEXT | N | 추가 설명 |
| `image_url` | VARCHAR(500) | N | 이미지 URL |
| `contact_method` | VARCHAR(20) | Y | 연락 방식 |
| `status` | VARCHAR(20) | Y | `OPEN`, `MATCHED`, `RETURNED`, `CLOSED` |

```sql
CREATE INDEX ix_lost_post_match_candidates
ON lost_posts (status, category, lost_at);
```

### 5.3 FoundPost

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `user_id` | BIGINT | Y | FK -> `users.id`, 작성자 |
| `title` | VARCHAR(100) | Y | 제목 |
| `category` | `ItemCategory` Enum | Y | 후보 선필터 태그 |
| `color` | VARCHAR(30) | Y | 대표 색상 |
| `location` | VARCHAR(100) | Y | 발견 위치 |
| `found_at` | DATETIME | Y | 발견 시각 |
| `storage_location` | VARCHAR(100) | Y | 보관 위치, 작성자에게 반환 |
| `features` | TEXT | Y | 공개 특징 |
| `private_feature` | TEXT | N | 작성자에게만 반환 |
| `verification_question` | VARCHAR(255) | N | 본인 확인 질문 |
| `description` | TEXT | N | 추가 설명 |
| `image_url` | VARCHAR(500) | N | 이미지 URL |
| `status` | VARCHAR(20) | Y | `STORED`, `CLAIMED`, `RETURNED`, `CLOSED` |

```sql
CREATE INDEX ix_found_post_match_candidates
ON found_posts (status, category, found_at);
```

### 5.4 Match

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `lost_post_id` | BIGINT | Y | FK -> `lost_posts.id` |
| `found_post_id` | BIGINT | Y | FK -> `found_posts.id` |
| `score` | DECIMAL(5,2) | Y | 총점 0~100 |
| `category_score` | DECIMAL(5,2) | Y | 동일 태그이므로 30점 |
| `color_score` | DECIMAL(5,2) | Y | 0~15 |
| `location_score` | DECIMAL(5,2) | Y | 0~20 |
| `time_score` | DECIMAL(5,2) | Y | 0~15 |
| `feature_score` | DECIMAL(5,2) | Y | 0~20 |
| `reasons` | JSON | Y | 매칭 이유 |
| `model_version` | VARCHAR(50) | Y | `ollama:qwen3-vl:4b`, `rule-v1` |
| `status` | VARCHAR(30) | Y | 매칭·인계 상태 |
| `claim_answer` | TEXT | N | 본인 확인 답변 |
| `claim_message` | VARCHAR(500) | N | 수령 요청 메시지 |
| `confirmed_by` | BIGINT | N | 확인한 습득글 작성자 |
| `confirmed_at` | DATETIME | N | 확인 시각 |
| `rejection_reason` | VARCHAR(500) | N | 거절 사유 |
| `handed_over_at` | DATETIME | N | 인계 완료 시각 |

`UNIQUE(lost_post_id, found_post_id)`로 중복 매칭을 막는다.

### 5.5 ChatRoom

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `match_id` | BIGINT | Y | FK -> `matches.id`, UNIQUE |
| `created_at` | DATETIME | Y | 생성 시각 |
| `updated_at` | DATETIME | Y | 최근 메시지 시각 |

수령 요청이 생성된 Match마다 채팅방은 최대 하나다.

### 5.6 ChatRoomMember

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK |
| `room_id` | BIGINT | Y | FK -> `chat_rooms.id` |
| `user_id` | BIGINT | Y | 분실글 또는 습득글 작성자 |
| `last_read_message_id` | BIGINT | N | 안 읽은 메시지 계산 커서 |
| `last_read_at` | DATETIME | N | 마지막 읽음 시각 표시 |

`UNIQUE(room_id, user_id)`로 중복 참여자를 막는다. 채팅 참여자는 해당 Match의 분실글 작성자와 습득글 작성자로만 구성한다.

### 5.7 ChatMessage

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `id` | BIGINT | Y | PK, 메시지 커서 |
| `room_id` | BIGINT | Y | FK -> `chat_rooms.id` |
| `sender_id` | BIGINT | Y | FK -> `users.id` |
| `content` | VARCHAR(1000) | Y | 메시지 본문 |
| `client_message_id` | VARCHAR(64) | N | 모바일 재전송 중복 방지 ID |
| `created_at` | DATETIME | Y | 서버 저장 시각 |

`UNIQUE(room_id, sender_id, client_message_id)`로 동일 클라이언트 메시지의 중복 저장을 막는다.

## 6. 동일 태그 후보 쿼리

### 분실글 등록 후

```sql
SELECT *
FROM found_posts
WHERE status = 'STORED'
  AND category = :lost_category
  AND user_id != :lost_author_id
  AND found_at >= :lost_at
ORDER BY found_at ASC
LIMIT 100;
```

### 습득글 등록 후

```sql
SELECT id
FROM lost_posts
WHERE status = 'OPEN'
  AND category = :found_category
  AND user_id != :found_author_id
  AND lost_at <= :found_at
ORDER BY lost_at DESC
LIMIT 100;
```

분실 태그가 `CARD`이면 `WALLET`, `EARPHONE`, `BAG` 습득글은 제목과 특징이 비슷해도 AI에 전달하지 않는다.

## 7. Ollama 습득글 작성과 매칭 점수

### 습득글 내용 자동 작성

LLM에 전달하는 `sourceFacts`는 아래 다섯 필드로 제한한다. `observations`는 선택값이며 나머지는 필수다.

```json
{
  "sourceFacts": {
    "category": "카드/학생증",
    "color": "파란색",
    "location": "강당 입구",
    "foundAt": "2026-07-13T14:15:00+00:00",
    "observations": "앞면에 파란색 학교 로고"
  }
}
```

`storageLocation`, `privateFeature`, `verificationQuestion`, `imageUrl`과 이미지 바이너리는 LLM 요청에 포함하지 않는다. 요청 옵션은 `think: false`, `temperature: 0`, `stream: false`이며 응답은 `title`, `features`, `description`만 허용하는 JSON Schema로 제한한다.

서버는 필수 장소·색상·카테고리가 결과에 포함되는지, 출력 숫자가 입력에 존재하는 숫자인지, 필드 길이가 DB 제약을 만족하는지 검증한다. 실패·타임아웃·잘못된 JSON·근거 검증 실패 시 `grounded-template-v1`을 사용한다.

### 사진 기반 자동 판별 (`category`/`color` 생략 시)

요청에 `category`와 `color`를 모두 생략하면 서버는 `imageUrl`이 가리키는 업로드된 이미지 파일을 읽어 Base64로 인코딩하고, Ollama Vision 요청의 `messages[1].images`에 넣어 함께 전달한다. `sourceFacts`는 `location`, `foundAt`, `observations`(선택)만 포함한다.

```json
{
  "sourceFacts": {
    "location": "강당 입구",
    "foundAt": "2026-07-13T14:15:00+00:00",
    "observations": "모서리에 흠집"
  }
}
```

응답 JSON Schema는 `category`(`ItemCategory` Enum 중 하나), `color`, `title`, `features`, `description`을 모두 요구한다. 서버는 `category`가 유효한 Enum 값인지, `color`가 짧은 영문/한글 코드인지, 장소 키워드 포함 여부와 숫자 근거를 기존과 동일하게 검증한다. 검증에 실패하면 `category=ETC`, `color=UNKNOWN`으로 대체 생성기 `grounded-template-v1`을 사용한다. `category`와 `color` 중 하나만 보내면 `422 VALIDATION_FAILED`로 거절하고, 둘 다 생략했는데 `imageUrl`이 없어도 동일하게 거절한다.

### 매칭 점수

| 항목 | 배점 | 기준 |
|---|---:|---|
| 카테고리 | 30 | 동일 태그 후보만 조회하므로 30점 |
| 색상 | 15 | 동일·유사 색상 |
| 위치 | 20 | 장소명 유사도 |
| 시간 | 15 | 분실 이후 발견 시간 차이 |
| 특징 | 20 | 스티커, 흠집, 이름표 등 |

총점 50점 이상만 저장하며 85점 이상을 최상위 추천으로 표시한다.

Worker 호출 형식:

```json
{
  "model": "qwen3-vl:4b",
  "stream": false,
  "think": false,
  "format": "json",
  "options": {"temperature": 0},
  "messages": [
    {"role": "system", "content": "Return JSON matching scores only."},
    {"role": "user", "content": "동일 태그 분실글과 습득물 후보"}
  ]
}
```

Ollama 연결 실패, 타임아웃, 잘못된 JSON이면 동일 후보에 `rule-v1`을 적용한다.

## 8. 인증 흐름

### 8.1 Postman에서 계정 생성

```http
POST /api/v1/auth/signup
Content-Type: application/json
```

```json
{
  "email": "user-a@example.com",
  "password": "StrongPass123!",
  "nickname": "사용자A"
}
```

발표 전에 일반 사용자 계정 A와 B를 만든다. 두 계정의 데이터 구조와 권한 종류는 같으며, 모바일 앱에서는 이 API를 호출하지 않는다.

### 8.2 앱 로그인

```http
POST /api/v1/auth/login
```

응답의 `accessToken`과 `refreshToken`을 앱 보안 저장소에 보관한다. 보호 API는 다음 헤더를 사용한다.

```http
Authorization: Bearer {accessToken}
```

## 9. API 목록

기본 URL: `http://13.124.179.95/api/v1`

### 인증·사용자

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| POST | `/auth/signup` | 공개, Postman 설정용 | 테스트 계정 생성 |
| POST | `/auth/login` | 공개 | 로그인, JWT 발급 |
| POST | `/auth/refresh` | Refresh JWT | Access Token 갱신 |
| GET | `/users/me` | JWT | 내 정보 조회 |
| PATCH | `/users/me` | JWT | 닉네임·프로필 수정 |

### 공통

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| GET | `/healthz` | 공개 | 상태 확인 |
| GET | `/api/v1/categories` | 공개 | Enum 태그 목록 |
| POST | `/api/v1/uploads/images` | JWT | 이미지 업로드 |
| GET | `/uploads/{fileName}` | 공개 | 이미지 조회 |

### 분실글

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| POST | `/lost-posts` | JWT | 등록·자동 분석 예약 |
| GET | `/lost-posts` | 공개 | 목록·태그 검색 |
| GET | `/lost-posts/{id}` | 공개 | 상세, 작성자는 비공개 특징 포함 |
| PATCH | `/lost-posts/{id}` | 작성자 | 수정·재분석 |
| DELETE | `/lost-posts/{id}` | 작성자 | 삭제 |
| POST | `/lost-posts/{id}/matches/analyze` | 작성자 | 수동 재분석 |

### 습득글

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| POST | `/found-posts` | JWT | 공개 사실로 내용 자동 작성·등록·분석 예약 |
| GET | `/found-posts` | 공개 | 기본 `STORED` 목록·태그 검색 |
| GET | `/found-posts/{id}` | 공개 | 상세, 작성자는 비공개 정보 포함 |
| PATCH | `/found-posts/{id}` | 작성자 | 입력 사실 수정·내용 재생성·재분석 |
| DELETE | `/found-posts/{id}` | 작성자 | 삭제 |

### 매칭·인계

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| GET | `/matches/lost-posts/{id}` | 분실글 작성자 | 후보 조회 |
| GET | `/matches/found-posts/{id}` | 습득글 작성자 | 후보 조회 |
| GET | `/matches/{id}` | 양쪽 게시글 작성자 | 상세 점수·이유 |
| POST | `/matches/{id}/claims` | 분실글 작성자 | 내 물건 요청 |
| PATCH | `/matches/{id}/verify` | 습득글 작성자 | 답변 확인 |
| PATCH | `/matches/{id}/reject` | 양쪽 게시글 작성자 | 거절 |
| PATCH | `/matches/{id}/handover` | 습득글 작성자 | 인계 완료 |

### 채팅

| Method | URL | 권한 | 기능 |
|---|---|---|---|
| GET | `/chats` | JWT | 내 채팅방과 안 읽은 개수 목록 |
| POST | `/chats/matches/{matchId}` | 양쪽 작성자 | 수령 요청 이후 채팅방 조회·복구 |
| GET | `/chats/{roomId}` | 채팅 참여자 | 채팅방 상세 |
| GET | `/chats/{roomId}/messages` | 채팅 참여자 | `beforeId`, `limit` 커서 내역 |
| PATCH | `/chats/{roomId}/read` | 채팅 참여자 | 마지막 읽은 메시지 갱신 |

## 10. 대표 게시글 요청

```json
{
  "title": "학생증 잃어버림",
  "category": "CARD",
  "color": "BLUE",
  "location": "강당",
  "lostAt": "2026-07-13T14:00:00Z",
  "features": "앞면에 파란색 학교 로고",
  "privateFeature": "이름 초성 ㄱㅌㅇ",
  "description": "행사 종료 후 확인",
  "imageUrl": "/uploads/example.jpg"
}
```

```json
{
  "category": "CARD",
  "color": "BLUE",
  "location": "강당 입구",
  "foundAt": "2026-07-13T14:15:00Z",
  "storageLocation": "학생회실",
  "observations": "앞면에 파란색 학교 로고",
  "privateFeature": "이름 초성 ㄱㅌㅇ",
  "verificationQuestion": "학생증 이름의 초성은 무엇인가요?",
  "imageUrl": "/uploads/example.jpg"
}
```

습득글 응답의 `post.title`, `post.features`, `post.description`은 서버가 생성하며 `post.contentGenerator`에서 생성 방식을 확인한다. 두 요청의 태그가 모두 `CARD`이므로 비교 후보가 된다.

## 11. Socket.IO 채팅

### 연결

- URL: `http://13.124.179.95/socket.io`
- 프로토콜: Socket.IO 4.x
- 인증: 연결 옵션의 `auth.token`에 Access Token 전달
- Refresh Token은 소켓 인증에 사용할 수 없음

```javascript
const socket = io("http://13.124.179.95", {
  transports: ["websocket"],
  auth: { token: accessToken }
});
```

토큰이 없거나 만료됐거나 비활성 사용자이면 연결 자체를 거절한다.

### 클라이언트 송신 이벤트

| 이벤트 | 데이터 | 동작 |
|---|---|---|
| `join_chat` | `{roomId}` | 참여 권한 확인 후 실시간 방 입장 |
| `leave_chat` | `{roomId}` | 실시간 방 퇴장 |
| `send_message` | `{roomId, content, clientMessageId?}` | DB 저장 후 전송 |
| `typing` | `{roomId, isTyping}` | 상대방에게 입력 상태 전달 |
| `mark_read` | `{roomId, messageId}` | 읽음 기준 저장 |

각 이벤트는 Socket.IO acknowledgement로 `success`, `data`, `error`를 반환한다.

### 서버 송신 이벤트

| 이벤트 | 설명 |
|---|---|
| `connected` | JWT 연결 완료, `userId` 반환 |
| `new_message` | 저장 완료된 메시지 |
| `typing` | 상대방 입력 상태 |
| `messages_read` | 참여자의 읽음 위치 변경 |

`send_message`는 Match 상태가 `CLAIM_REQUESTED` 또는 `VERIFIED`일 때만 허용한다. `REJECTED`, `HANDED_OVER` 상태에서는 내역 조회만 가능하다.

메시지 전송 예시:

```json
{
  "roomId": 1,
  "content": "학생증 뒷면 학번 끝 두 자리는 42입니다.",
  "clientMessageId": "android-1720839000-1"
}
```

### 수령 요청과 채팅방 생성

`POST /matches/{id}/claims`가 성공하면 응답의 `chatRoomId`가 채워진다. 서버가 트랜잭션 안에서 분실글 작성자와 습득글 작성자를 멤버로 등록하므로 앱이 임의 사용자 ID를 넘기지 않는다.

## 12. 상태 전이

| 동작 | Match | LostPost | FoundPost |
|---|---|---|---|
| 후보 생성 | `CANDIDATE` | `OPEN` | `STORED` |
| 내 물건 요청 | `CLAIM_REQUESTED` | `MATCHED` | `CLAIMED` |
| 습득글 작성자 확인 | `VERIFIED` | `MATCHED` | `CLAIMED` |
| 거절 | `REJECTED` | `OPEN` | `STORED` |
| 습득글 작성자 인계 | `HANDED_OVER` | `RETURNED` | `RETURNED` |

채팅은 `CLAIM_REQUESTED`에서 생성되고 `VERIFIED`까지 송신 가능하다. 거절·인계 후에도 기록은 남지만 송신은 닫힌다.

## 13. 이미지 저장

1. JWT 사용자가 `/uploads/images`에 `multipart/form-data`의 `image`를 보낸다.
2. Flask가 JPEG, PNG, WebP를 검증하고 UUID 파일명으로 저장한다.
3. EC2 `/home/ec2-user/lostlink-uploads`를 컨테이너 `/data/uploads`에 마운트한다.
4. Nginx가 `/uploads/*`를 직접 제공한다.

## 14. 오류 코드

| HTTP | 코드 | 의미 |
|---:|---|---|
| 400 | `VALIDATION_FAILED` | JSON 또는 필수값 오류 |
| 401 | `UNAUTHORIZED` | JWT 없음·만료·잘못된 로그인 |
| 403 | `FORBIDDEN` | 해당 게시글 작성자 또는 매칭 참여자가 아님 |
| 404 | `LOST_POST_NOT_FOUND` | 분실글 없음 |
| 404 | `FOUND_POST_NOT_FOUND` | 습득글 없음 |
| 404 | `MATCH_NOT_FOUND` | 매칭 없음 |
| 404 | `CHAT_ROOM_NOT_FOUND` | 참여 가능한 채팅방 없음 |
| 404 | `ROUTE_NOT_FOUND` | URL 변수가 치환되지 않았거나 API 경로가 없음 |
| 409 | `INVALID_STATUS_TRANSITION` | 허용되지 않은 상태 변경 |
| 409 | `CHAT_NOT_AVAILABLE` | 수령 요청 전 채팅 생성 시도 |
| 409 | `CHAT_CLOSED` | 종료된 채팅방에 메시지 송신 |
| 413 | `IMAGE_TOO_LARGE` | 이미지 크기 초과 |
| 422 | `INVALID_CATEGORY` | Enum에 없는 태그 |
| 422 | `INVALID_IMAGE_TYPE` | 지원하지 않는 이미지 |
| 422 | `INVALID_MESSAGE` | 빈 메시지 또는 1000자 초과 |

## 15. Docker·배포

| 서비스 | 역할 |
|---|---|
| `nginx` | API 프록시, 이미지 제공, WebSocket Upgrade |
| `api` | Flask + Gunicorn, Socket.IO |
| `worker` | Celery 자동 분석 |
| `db` | PostgreSQL 16 |
| `redis` | Celery 작업 큐, Socket.IO message queue |

```dotenv
SECRET_KEY=replace-me
JWT_SECRET_KEY=replace-me-too
POSTGRES_DB=db_server
UPLOADS_PATH=/home/ec2-user/lostlink-uploads
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://100.102.0.2:11434
OLLAMA_MODEL=qwen3-vl:4b
MATCH_MIN_SCORE=50
SOCKET_CORS_ORIGINS=*
```

API는 WebSocket 연결 유지를 위해 Gunicorn 1 worker·thread 모드로 실행한다. 여러 API 인스턴스로 확장할 때는 Redis message queue를 유지하고 Nginx 로드밸런싱 전략을 별도로 구성한다.

`BE` 푸시 시 GitHub Actions가 Ruff, Pytest, Docker 빌드를 통과한 뒤 EC2 Compose를 재배포한다.

## 16. 해커톤 시연 순서

1. Postman으로 동일한 유형의 일반 사용자 계정 A와 B를 만든다.
2. 앱에서 두 계정으로 로그인해 JWT를 받는다.
3. `CARD` 태그 학생증 습득글과 `WALLET` 태그 유사 글을 등록한다.
4. `CARD` 태그 학생증 분실글을 등록한다.
5. 같은 `CARD` 습득글만 후보가 된 결과와 AI 이유를 보여준다.
6. 분실글 작성자가 수령 요청하면 채팅방이 자동 생성되는 것을 보여준다.
7. 두 앱에서 Socket.IO 메시지와 읽음 상태가 실시간으로 반영되는 것을 보여준다.
8. 습득글 작성자가 확인하고 인계 완료 상태를 보여준다.

## 17. 완료 조건

- 사용자 유형은 하나이며 `role`과 관리자 계정이 없다.
- 동일한 사용자가 분실글과 습득글을 모두 작성할 수 있다.
- 로그인, Access/Refresh JWT, 게시글 작성자 검사가 유지된다.
- 회원가입 API는 Postman 테스트 계정 생성용으로 문서화된다.
- 모바일 앱 기능 범위에는 회원가입 화면이 없다.
- 두 게시글이 같은 `ItemCategory` Enum을 사용한다.
- 허용되지 않은 태그가 API와 DB에서 거절된다.
- 양방향 후보 SQL이 동일 태그만 조회한다.
- Ollama 실패 시 규칙 점수로 계속 동작한다.
- 습득글 제목·특징·설명은 공개 입력 사실만으로 자동 작성된다.
- 습득글 생성과 매칭의 Ollama 요청은 모두 `think: false`다.
- 보관 위치·비공개 특징·확인 질문·이미지는 습득글 작성 LLM에 전달되지 않는다.
- 수령 요청 시 당사자 전용 채팅방이 한 개만 생성된다.
- Socket.IO JWT 인증, 실시간 메시지, 중복 방지, 읽음 처리가 동작한다.
- 제3자는 채팅방 조회·입장·메시지 전송이 차단된다.
- 거절·인계 완료 후 기존 메시지는 보존되고 새 메시지는 차단된다.
- 이미지가 EC2 영구 경로에 저장된다.
- 테스트, 마이그레이션, Docker 빌드, EC2 배포가 통과한다.
