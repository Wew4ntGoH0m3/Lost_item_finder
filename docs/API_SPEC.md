# LostLink API 및 테이블 설계 명세서

## 1. 기본 정보

| 항목 | 내용 |
|---|---|
| 서비스 | 학교·행사장 내 분실글과 습득글을 AI가 비교해 연결하는 서비스 |
| 백엔드 | Python 3.12 + Flask REST API |
| 데이터베이스 | Flask-SQLAlchemy + Alembic, 개발 SQLite / 배포 PostgreSQL 권장 |
| API | HTTPS + JSON, 기본 경로 `/api/v1` |
| 클라이언트 | Android/iOS 모바일 앱 |
| 인증 | Bearer Access Token |
| MVP 테이블 | `User`, `LostPost`, `FoundPost`, `Match` |
| 시간 형식 | ISO 8601 UTC |

> 실제 DB에서 `USER`는 예약어일 수 있으므로 물리 테이블명은 `users`를 권장한다.

## 1.1 Flask 구현 기준

| 영역 | 권장 구성 |
|---|---|
| 앱 시작점 | `create_app()` Application Factory |
| API 분리 | `auth`, `lost_posts`, `found_posts`, `matches` Blueprint |
| ORM | Flask-SQLAlchemy 모델 4개 |
| 마이그레이션 | Flask-Migrate/Alembic |
| 인증 | Flask-JWT-Extended Access/Refresh Token |
| 요청 검증 | Marshmallow 또는 Pydantic 중 하나로 통일 |
| 비밀번호 | Werkzeug 또는 Argon2 해시 |
| AI 작업 | 해커톤은 동기 함수, 지연 시 Celery/RQ 비동기 큐 |
| 파일 | `multipart/form-data` 업로드 후 URL만 DB 저장 |
| 알림 | FCM 중심, iOS는 APNs 연동 또는 FCM 중계 |

### 1.2 모바일 앱 통신 규칙

| 항목 | 규칙 |
|---|---|
| Access Token | `Authorization: Bearer {token}` 헤더 사용 |
| Refresh Token | Android Keystore/iOS Keychain 등 보안 저장소에 저장 |
| 토큰 만료 | 앱이 401을 받으면 1회 갱신 후 원 요청 재시도 |
| 이미지 | 앱이 먼저 `/uploads/images`에 업로드하고 반환 URL을 게시글 요청에 포함 |
| 푸시 토큰 | 로그인 또는 토큰 변경 시 `/users/me/push-token`으로 갱신 |
| 네트워크 오류 | 중복 게시글 방지를 위해 생성 요청에 `Idempotency-Key` 사용 권장 |

## 2. 테이블 관계

| 부모 | 자식 | 관계 | 외래 키 |
|---|---|---|---|
| `User` | `LostPost` | 사용자 1명 : 분실글 N개 | `LostPost.user_id` |
| `User` | `FoundPost` | 사용자 1명 : 습득글 N개 | `FoundPost.user_id` |
| `LostPost` | `Match` | 분실글 1개 : 매칭 N개 | `Match.lost_post_id` |
| `FoundPost` | `Match` | 습득글 1개 : 매칭 N개 | `Match.found_post_id` |
| `User` | `Match` | 관리자 1명 : 확인 N개 | `Match.confirmed_by` |

```text
User 1 --- N LostPost
User 1 --- N FoundPost
LostPost 1 --- N Match N --- 1 FoundPost
```

## 3. User 테이블

| 컬럼 | 타입 | 필수 | 키/제약 | 설명 |
|---|---|---:|---|---|
| `id` | BIGINT | Y | PK, Auto Increment | 사용자 ID |
| `email` | VARCHAR(255) | Y | UNIQUE | 로그인 이메일 |
| `password_hash` | VARCHAR(255) | Y |  | 해시된 비밀번호 |
| `nickname` | VARCHAR(20) | Y |  | 화면 표시 이름 |
| `role` | VARCHAR(20) | Y | DEFAULT `USER` | `USER`, `ADMIN` |
| `site_code` | VARCHAR(50) | Y | INDEX | 학교·행사장 코드 |
| `profile_image_url` | VARCHAR(500) | N |  | 프로필 이미지 URL |
| `platform` | VARCHAR(20) | N |  | `ANDROID`, `IOS` |
| `push_token` | VARCHAR(500) | N |  | FCM/APNs 푸시 토큰 |
| `is_active` | BOOLEAN | Y | DEFAULT TRUE | 계정 활성 여부 |
| `created_at` | DATETIME | Y |  | 가입 시각 |
| `updated_at` | DATETIME | Y |  | 수정 시각 |

## 4. LostPost 테이블

| 컬럼 | 타입 | 필수 | 키/제약 | 설명 |
|---|---|---:|---|---|
| `id` | BIGINT | Y | PK, Auto Increment | 분실글 ID |
| `user_id` | BIGINT | Y | FK -> `User.id`, INDEX | 작성자 ID |
| `site_code` | VARCHAR(50) | Y | INDEX | 분실 시설 코드 |
| `title` | VARCHAR(100) | Y |  | 글 제목 |
| `category` | VARCHAR(50) | Y | INDEX | 이어폰, 지갑, 학생증 등 |
| `color` | VARCHAR(30) | Y | INDEX | 대표 색상 |
| `location` | VARCHAR(100) | Y | INDEX | 분실 장소 |
| `lost_at` | DATETIME | Y | INDEX | 분실 추정 시각 |
| `features` | TEXT | Y |  | 스티커, 흠집, 키링 등 특징 |
| `private_feature` | TEXT | N | 암호화, 비공개 | 본인 확인용 특징 |
| `description` | TEXT | N |  | 추가 설명 |
| `image_url` | VARCHAR(500) | N |  | 기존 또는 유사 이미지 |
| `contact_method` | VARCHAR(20) | Y | DEFAULT `NOTIFICATION` | `NOTIFICATION`, `CHAT` |
| `status` | VARCHAR(20) | Y | DEFAULT `OPEN`, INDEX | 처리 상태 |
| `created_at` | DATETIME | Y |  | 작성 시각 |
| `updated_at` | DATETIME | Y |  | 수정 시각 |

| 상태 | 의미 |
|---|---|
| `OPEN` | 찾는 중, AI 매칭 대상 |
| `MATCHED` | 유력한 습득물 확인 |
| `RETURNED` | 물건 반환 완료 |
| `CLOSED` | 작성자가 찾기를 종료 |

## 5. FoundPost 테이블

| 컬럼 | 타입 | 필수 | 키/제약 | 설명 |
|---|---|---:|---|---|
| `id` | BIGINT | Y | PK, Auto Increment | 습득글 ID |
| `user_id` | BIGINT | Y | FK -> `User.id`, INDEX | 작성자 ID |
| `site_code` | VARCHAR(50) | Y | INDEX | 습득 시설 코드 |
| `title` | VARCHAR(100) | Y |  | 글 제목 |
| `category` | VARCHAR(50) | Y | INDEX | 물건 종류 |
| `color` | VARCHAR(30) | Y | INDEX | 대표 색상 |
| `location` | VARCHAR(100) | Y | INDEX | 발견 장소 |
| `found_at` | DATETIME | Y | INDEX | 발견 시각 |
| `storage_location` | VARCHAR(100) | Y |  | 학생회실 등 현재 보관 장소 |
| `features` | TEXT | Y |  | 공개 가능한 특징 |
| `private_feature` | TEXT | N | 암호화, 비공개 | 본인 확인용 특징 |
| `verification_question` | VARCHAR(255) | N | 비공개 | 분실자 본인 확인 질문 |
| `description` | TEXT | N |  | 추가 설명 |
| `image_url` | VARCHAR(500) | N |  | 실제 습득물 이미지 |
| `status` | VARCHAR(20) | Y | DEFAULT `STORED`, INDEX | 처리 상태 |
| `created_at` | DATETIME | Y |  | 작성 시각 |
| `updated_at` | DATETIME | Y |  | 수정 시각 |

| 상태 | 의미 |
|---|---|
| `STORED` | 주인을 아직 찾지 못해 보관 중인 상태. AI 조회의 유일한 대상 |
| `CLAIMED` | 분실자가 수령 요청 |
| `RETURNED` | 물건 반환 완료 |
| `CLOSED` | 기관 이관 또는 처리 종료 |

## 6. Match 테이블

| 컬럼 | 타입 | 필수 | 키/제약 | 설명 |
|---|---|---:|---|---|
| `id` | BIGINT | Y | PK, Auto Increment | 매칭 ID |
| `lost_post_id` | BIGINT | Y | FK -> `LostPost.id`, INDEX | 분실글 ID |
| `found_post_id` | BIGINT | Y | FK -> `FoundPost.id`, INDEX | 습득글 ID |
| `score` | DECIMAL(5,2) | Y | 0~100, INDEX | 최종 매칭률 |
| `category_score` | DECIMAL(5,2) | Y | 0~30 | 물건 종류 점수 |
| `color_score` | DECIMAL(5,2) | Y | 0~15 | 색상 점수 |
| `location_score` | DECIMAL(5,2) | Y | 0~20 | 장소 점수 |
| `time_score` | DECIMAL(5,2) | Y | 0~15 | 시간 점수 |
| `feature_score` | DECIMAL(5,2) | Y | 0~20 | 특징·텍스트 점수 |
| `reasons` | JSON | Y |  | 사용자에게 표시할 일치 이유 |
| `model_version` | VARCHAR(30) | Y |  | 예: `llm-v1` |
| `status` | VARCHAR(30) | Y | DEFAULT `CANDIDATE`, INDEX | 매칭·수령 상태 |
| `claim_answer` | TEXT | N | 암호화, 접근 제한 | 분실자의 본인 확인 답변 |
| `claim_message` | VARCHAR(500) | N |  | 수령 요청 메시지 |
| `claimed_at` | DATETIME | N |  | 수령 요청 시각 |
| `confirmed_by` | BIGINT | N | FK -> `User.id` | 승인한 관리자 |
| `confirmed_at` | DATETIME | N |  | 본인 확인 승인 시각 |
| `rejection_reason` | VARCHAR(500) | N |  | 거절 사유 |
| `handed_over_at` | DATETIME | N |  | 실제 인계 완료 시각 |
| `created_at` | DATETIME | Y |  | AI 매칭 생성 시각 |
| `updated_at` | DATETIME | Y |  | 수정 시각 |

제약조건: `UNIQUE(lost_post_id, found_post_id)`. 두 게시글의 `site_code`가 같아야 하며, 원칙적으로 `found_at >= lost_at`인 조합만 분석한다.

| Match 상태 | 의미 | 다음 상태 |
|---|---|---|
| `CANDIDATE` | AI가 만든 후보 | `CLAIM_REQUESTED`, `REJECTED` |
| `CLAIM_REQUESTED` | 분실자가 내 물건이라고 요청 | `VERIFIED`, `REJECTED` |
| `VERIFIED` | 관리자 또는 습득자가 본인 확인 | `HANDED_OVER` |
| `REJECTED` | 다른 물건 또는 확인 실패 | 종료 |
| `HANDED_OVER` | 실제 물건 인계 완료 | 종료 |

## 7. AI 점수 규칙

| 항목 | 배점 | 기준 |
|---|---:|---|
| 물건 종류 | 30 | 동일 종류 30점, 이어폰·에어팟 케이스 등 유사 표현 부분 점수 |
| 색상 | 15 | 동일 색상 15점, 유사 색상 부분 점수 |
| 위치 | 20 | 같은 장소 20점, 체육관·체육관 입구 등 인접 장소 부분 점수 |
| 시간 | 15 | 분실 후 발견까지 시간 차이가 짧을수록 높은 점수 |
| 특징 | 20 | 스티커, 흠집, 키링과 텍스트 의미 비교 |
| 합계 | 100 | 다섯 항목 합산 |

```text
score = category_score + color_score + location_score + time_score + feature_score
```

| 매칭률 | 등급 | 처리 |
|---:|---|---|
| 85~100 | 매우 높음 | 즉시 알림, 후보 최상단 |
| 70~84 | 높음 | 후보 목록 상단 |
| 50~69 | 보통 | 후보 목록 표시 |
| 0~49 | 낮음 | 기본 후보에서 제외 |

이미지 AI는 MVP 점수에서 제외한다. LLM은 분실글과 서버가 조회한 `STORED` 습득물 후보의 의미 유사성을 비교하고 항목별 점수와 `reasons`를 구조화 JSON으로 반환한다. 서버는 항목별 최대 배점과 최종 합계를 검증하며, 비공개 특징 원문은 사용자용 이유에 노출하지 않는다.

## 8. API 목록

### 인증 및 사용자

| Method | URL | 기능 |
|---|---|---|
| POST | `/auth/signup` | 회원가입 |
| POST | `/auth/login` | 로그인 |
| POST | `/auth/refresh` | 토큰 갱신 |
| POST | `/auth/logout` | 로그아웃 |
| GET | `/users/me` | 내 정보 조회 |
| PATCH | `/users/me/push-token` | 앱 푸시 토큰 등록·갱신 |
| POST | `/uploads/images` | 게시글 이미지 업로드 |

### LostPost

| Method | URL | 기능 | 권한 |
|---|---|---|---|
| POST | `/lost-posts` | 분실글 작성 후 자동 AI 분석 | 회원 |
| GET | `/lost-posts` | 시설·종류·장소·상태별 목록 | 전체 |
| GET | `/lost-posts/{id}` | 분실글 상세 | 전체 |
| PATCH | `/lost-posts/{id}` | 분실글 수정 및 재분석 | 작성자·관리자 |
| DELETE | `/lost-posts/{id}` | 분실글 삭제 | 작성자·관리자 |

### FoundPost

| Method | URL | 기능 | 권한 |
|---|---|---|---|
| POST | `/found-posts` | 습득글 작성 후 자동 AI 분석 | 회원 |
| GET | `/found-posts` | 기본적으로 주인을 못 찾은 `STORED` 습득물만 조회 | 전체 |
| GET | `/found-posts/{id}` | 습득글 상세 | 전체 |
| PATCH | `/found-posts/{id}` | 습득글 수정 및 재분석 | 작성자·관리자 |
| DELETE | `/found-posts/{id}` | 습득글 삭제 | 작성자·관리자 |

### Match와 인계

| Method | URL | 기능 | 권한 |
|---|---|---|---|
| POST | `/lost-posts/{id}/matches/analyze` | 해당 분실글과 미주인 습득물을 LLM으로 분석 | 작성자·관리자 |
| GET | `/matches/lost-posts/{id}` | 분실글 기준 습득 후보 | 분실글 작성자·관리자 |
| GET | `/matches/found-posts/{id}` | 습득글 기준 분실 후보 | 습득글 작성자·관리자 |
| GET | `/matches/{id}` | 점수와 매칭 이유 상세 | 양쪽 작성자·관리자 |
| POST | `/matches/{id}/claims` | 내 물건 같아요 요청과 답변 제출 | 분실글 작성자 |
| PATCH | `/matches/{id}/verify` | 본인 확인 승인 | 습득자·관리자 |
| PATCH | `/matches/{id}/reject` | 매칭 또는 수령 요청 거절 | 양쪽 작성자·관리자 |
| PATCH | `/matches/{id}/handover` | 실제 인계 완료 | 관리자 |

## 9. 상태 동기화

| 동작 | Match | LostPost | FoundPost |
|---|---|---|---|
| AI 후보 생성 | `CANDIDATE` | `OPEN` | `STORED` |
| 수령 요청 | `CLAIM_REQUESTED` | `MATCHED` | `CLAIMED` |
| 관리자 승인 | `VERIFIED` | `MATCHED` | `CLAIMED` |
| 요청 거절 | `REJECTED` | `OPEN` | `STORED` |
| 인계 완료 | `HANDED_OVER` | `RETURNED` | `RETURNED` |

## 10. 대표 오류 코드

| HTTP | 코드 | 설명 |
|---:|---|---|
| 400 | `VALIDATION_FAILED` | 필수값 누락 또는 형식 오류 |
| 401 | `UNAUTHORIZED` | 토큰 없음 또는 만료 |
| 403 | `FORBIDDEN` | 작성자·관리자 권한 없음 |
| 404 | `LOST_POST_NOT_FOUND` | 분실글 없음 |
| 404 | `FOUND_POST_NOT_FOUND` | 습득글 없음 |
| 404 | `MATCH_NOT_FOUND` | 매칭 없음 |
| 409 | `MATCH_ALREADY_EXISTS` | 같은 게시글 조합의 매칭 중복 |
| 409 | `INVALID_STATUS_TRANSITION` | 허용되지 않은 상태 변경 |
| 500 | `AI_ANALYSIS_FAILED` | AI 분석 실패 |

## 11. 보안 및 확장 기준

| 대상 | 규칙 |
|---|---|
| 비밀번호 | Argon2id 또는 Werkzeug 해시만 저장 |
| 앱 토큰 | Access Token은 짧게 유지하고 Refresh Token은 앱 보안 저장소 사용 |
| 비공개 특징 | 일반 게시글 API에서 반환 금지, 암호화 저장 |
| 본인 확인 답변 | 양쪽 작성자와 관리자만 접근, 로그 출력 금지 |
| 사진 | 학생증 번호, 이름, 연락처 등 민감 정보 마스킹 |
| 인계 | 관리자만 `HANDED_OVER` 처리 가능 |

네 테이블 구조는 해커톤 MVP용이다. 운영 단계에서는 수령 요청, 확인 질문, 관리자 처리 이력을 `Claim`, `VerificationQuestion`, `Handover` 테이블로 분리해 변경 이력을 보존한다.

## 12. 미주인 습득물 조회 및 LLM 매칭 상세

| 단계 | 처리 내용 | 필수 조건 | 결과 |
|---:|---|---|---|
| 1 | 분실 게시글 조회 | `LostPost.status = OPEN` | LLM 비교 기준 데이터 확보 |
| 2 | 습득물 DB 조회 | `FoundPost.status = STORED`, 같은 `site_code` | 아직 주인을 못 찾은 습득물 후보만 반환 |
| 3 | 1차 후보 제한 | 같은 시설, 발견 시각이 분실 시각 이후, 최대 100개 | 불필요한 LLM 입력 제거 |
| 4 | LLM 유사도 분석 | 분실글 1개와 조회된 습득물 후보만 전달 | 항목별 점수와 매칭 이유 생성 |
| 5 | 서버 결과 검증 | 후보 ID, 배점 범위, 총점 검증 | 잘못되거나 생성된 ID 제거 |
| 6 | Match 저장 | 총점 50점 이상, 저장 직전에도 `STORED` | `Match.status = CANDIDATE` |
| 7 | 앱 알림 | 총점 85점 이상 | 분실자에게 푸시 알림 |
| 8 | 수령 요청 | 분실자가 본인 확인 답변 제출 | `FoundPost.status = CLAIMED` |
| 9 | 인계 완료 | 관리자 본인 확인 및 전달 | `FoundPost.status = RETURNED` |

### 12.1 조회 원칙

| 규칙 | 명세 |
|---|---|
| 조회 대상 | `FoundPost.status = STORED`인 습득물만 허용 |
| 제외 대상 | `CLAIMED`, `RETURNED`, `CLOSED` 상태는 LLM 후보 쿼리에서 반드시 제외 |
| 시설 범위 | 분실글과 `site_code`가 같은 습득물만 조회 |
| 시간 범위 | 원칙적으로 `found_at >= lost_at`; 시간 오차 정책이 있으면 설정값으로 확장 |
| 후보 개수 | LLM 토큰 및 지연 제한을 위해 1차 DB 후보를 최대 100개로 제한 |
| 정렬 | 같은 카테고리, 가까운 시간, 같은 장소 순으로 우선 정렬 |

`owner_found` 같은 별도 Boolean 컬럼은 두지 않는다. 주인을 찾았는지는 `FoundPost.status`로 단일 관리하여 값 불일치를 방지한다.

조회 성능을 위해 다음 복합 인덱스를 권장한다.

```sql
CREATE INDEX ix_found_post_match_candidates
ON found_post (site_code, status, category, found_at);
```

### 12.2 Flask-SQLAlchemy 후보 쿼리

```python
from sqlalchemy import select

def find_unclaimed_candidates(lost_post: LostPost) -> list[FoundPost]:
    statement = (
        select(FoundPost)
        .where(
            FoundPost.site_code == lost_post.site_code,
            FoundPost.status == "STORED",
            FoundPost.found_at >= lost_post.lost_at,
        )
        .order_by(
            (FoundPost.category == lost_post.category).desc(),
            FoundPost.found_at.asc(),
        )
        .limit(100)
    )
    return list(db.session.scalars(statement))
```

서비스 레이어에서 `status == STORED` 조건을 고정한다. 앱 요청으로 `status`를 전달받아 이 조건을 바꿀 수 없게 한다.

### 12.3 매칭 실행 API

| Method | URL | 기능 |
|---|---|---|
| POST | `/api/v1/lost-posts/{lostPostId}/matches/analyze` | 분실글 기준으로 미주인 습득물 조회 후 LLM 매칭 실행 |

요청 본문은 필요 없다. 서버가 인증 사용자와 `lostPostId`로 분실글을 조회한다.

처리 순서:

1. 분실글 존재 여부와 작성자/관리자 권한을 확인한다.
2. 분실글 상태가 `OPEN`인지 확인한다.
3. DB에서 `FoundPost.status = STORED` 후보만 조회한다.
4. 분실글 1개와 조회된 습득물 후보 목록을 LLM에 전달한다.
5. LLM의 구조화 결과에서 후보 ID, 항목별 점수, 이유를 받는다.
6. 서버가 후보 ID가 실제 조회 목록에 포함되는지와 점수 범위를 검증한다.
7. 총점 50점 이상만 `Match`에 upsert한다.
8. 저장 직전 해당 `FoundPost.status`가 여전히 `STORED`인지 다시 확인한다.
9. 85점 이상이면 분실글 작성자에게 앱 푸시 알림을 전송한다.

### 12.4 LLM 입력 데이터

| 객체 | 전달 필드 | 제외 필드 |
|---|---|---|
| 분실글 | `id`, `category`, `color`, `location`, `lost_at`, `features`, `description` | 사용자 이메일, 연락처, 비밀번호 |
| 습득물 후보 | `id`, `category`, `color`, `location`, `found_at`, `features`, `description` | 작성자 개인정보, 보관 담당자 연락처 |

LLM은 DB에 직접 접근하지 않는다. Flask 서버가 조건에 맞게 조회한 최소 데이터만 전달한다.

LLM 입력 예시:

```json
{
  "lostPost": {
    "id": 101,
    "category": "EARPHONE",
    "color": "BLACK",
    "location": "체육관",
    "lostAt": "2026-07-13T14:00:00Z",
    "features": "작은 흰색 별 스티커",
    "description": "체육 수업 후 잃어버림"
  },
  "foundCandidates": [
    {
      "id": 201,
      "category": "EARPHONE_CASE",
      "color": "BLACK",
      "location": "체육관 입구",
      "foundAt": "2026-07-13T14:20:00Z",
      "features": "흰색 별 모양 스티커",
      "description": "신발장 앞에서 발견"
    }
  ],
  "scoreLimits": {
    "category": 30,
    "color": 15,
    "location": 20,
    "time": 15,
    "feature": 20
  }
}
```

### 12.5 LLM 구조화 출력

```json
{
  "matches": [
    {
      "foundPostId": 201,
      "categoryScore": 25,
      "colorScore": 15,
      "locationScore": 18,
      "timeScore": 14,
      "featureScore": 20,
      "score": 92,
      "reasons": [
        "물건 종류가 유사합니다.",
        "검정색이 일치합니다.",
        "체육관과 체육관 입구는 인접 장소입니다.",
        "발견 시각이 분실 시각으로부터 20분 뒤입니다.",
        "흰색 별 스티커 특징이 일치합니다."
      ]
    }
  ]
}
```

서버 검증 규칙:

| 검증 | 실패 처리 |
|---|---|
| `foundPostId`가 서버가 조회한 후보 목록에 없음 | 해당 결과 폐기 |
| 후보 상태가 더 이상 `STORED`가 아님 | 해당 결과 폐기 |
| 항목별 점수가 최대 배점을 초과 | 결과 폐기 및 오류 로그 |
| `score`가 항목별 점수 합과 다름 | 서버가 합계를 다시 계산 |
| `score < 50` | `Match`에 저장하지 않음 |
| 같은 분실글·습득글 조합이 이미 존재 | 새 행 생성 대신 기존 `Match` 갱신 |

### 12.6 동시성 처리

LLM 분석 중 다른 사용자가 물건을 수령할 수 있으므로, `Match` 저장 시 트랜잭션 안에서 `FoundPost.status = STORED`를 다시 검사한다. 이미 `CLAIMED` 또는 `RETURNED`라면 결과를 저장하거나 앱에 추천하지 않는다.

분실자가 수령 요청하면 같은 트랜잭션에서 `Match.status = CLAIM_REQUESTED`와 `FoundPost.status = CLAIMED`를 함께 변경한다. 요청이 거절된 경우에만 `FoundPost.status`를 다시 `STORED`로 되돌려 다음 매칭 대상에 포함한다.
