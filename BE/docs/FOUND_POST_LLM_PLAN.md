# 로그인 및 습득글 LLM 자동 작성 기능 기획서

## 1. 문서 기준

| 항목 | 내용 |
|---|---|
| 기준 백엔드 | LostLink Flask Backend `BE` 브랜치 |
| 기준 커밋 | `f61356e` |
| 운영 API | `http://13.124.179.95/api/v1` |
| LLM | Ollama `qwen3-vl:4b` |
| 구현 상태 | 개발·테스트·EC2 배포 완료 |

## 2. 목표

사용자는 앱에서 로그인해 JWT를 발급받고, 인증된 상태에서 물건의 객관적인 정보만 입력한다. 서버는 해당 정보만 사용해 습득글의 제목, 공개 특징, 설명을 자동 작성한다.

핵심 원칙은 다음과 같다.

1. 사용자 유형은 하나이며 로그인한 모든 사용자가 분실글과 습득글을 작성할 수 있다.
2. 로그인 이후 보호 API는 Access Token으로 사용자와 게시글 작성자를 식별한다.
3. 사용자가 입력하지 않은 브랜드, 모델, 소유자, 손상, 내용물, 발견 경위를 추측하지 않는다.
4. 보관 위치와 본인 확인용 비공개 정보는 공개 글 생성에 사용하지 않는다.
5. LLM 결과를 그대로 신뢰하지 않고 서버 검증을 통과한 결과만 저장한다.
6. LLM 장애나 근거 검증 실패 시에도 입력 사실만 사용하는 템플릿으로 글을 생성한다.

## 3. 로그인 및 인증 정책

| 항목 | 정책 |
|---|---|
| 사용자 유형 | 단일 `User`, 관리자·분실자·습득자 역할 구분 없음 |
| 회원가입 | API는 유지하지만 모바일 앱 화면에서는 제외 |
| 계정 생성 | 개발자 또는 시연 담당자가 Postman으로 사전 생성 |
| 앱 인증 | 이메일·비밀번호 로그인 |
| Access Token | 보호 API와 Socket.IO 인증에 사용, 기본 30분 |
| Refresh Token | Access Token 재발급에 사용, 기본 30일 |
| 로그아웃 | 백엔드 API 없이 앱이 로컬 Access/Refresh Token 삭제 |

백엔드는 HTTP 요청이 Postman에서 왔는지 앱에서 왔는지 구분할 수 없다. 따라서 회원가입 API 자체를 기술적으로 Postman 전용으로 제한하는 것이 아니라, 모바일 앱에서 회원가입 화면과 호출 코드를 제공하지 않는 운영 방식으로 제한한다.

## 4. 인증 API

### 4.1 Postman 회원가입

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

- 이메일은 로그인 ID이며 중복될 수 없다.
- 비밀번호는 8~64자다.
- 닉네임은 2~20자다.
- 앱에서는 이 API를 호출하지 않는다.

### 4.2 앱 로그인

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "user-a@example.com",
  "password": "StrongPass123!"
}
```

응답의 주요 구조:

```json
{
  "accessToken": "JWT_ACCESS_TOKEN",
  "refreshToken": "JWT_REFRESH_TOKEN",
  "user": {
    "id": 1,
    "email": "user-a@example.com",
    "nickname": "사용자A"
  }
}
```

잘못된 이메일·비밀번호 또는 비활성 계정은 `401 INVALID_CREDENTIALS`로 거절한다. `role` 필드는 존재하지 않는다.

### 4.3 Access Token 갱신

```http
POST /api/v1/auth/refresh
Authorization: Bearer {refreshToken}
```

응답의 새 `accessToken`으로 기존 Access Token을 교체한다. Refresh Token은 일반 보호 API에 사용하지 않는다.

### 4.4 앱 로그아웃

백엔드 로그아웃 API는 제공하지 않는다. 현재 인증은 상태를 저장하지 않는 JWT 방식이므로 앱이 안전한 로컬 저장소의 Access Token과 Refresh Token을 즉시 삭제하고 로그인 화면으로 이동한다.

### 4.5 내 사용자 정보

```http
GET /api/v1/users/me
Authorization: Bearer {accessToken}
```

로그인 복원과 현재 사용자 확인에 사용한다.

## 5. 전체 사용자 흐름

1. 시연 담당자가 Postman으로 일반 사용자 계정을 만든다.
2. 사용자가 앱에서 이메일과 비밀번호로 로그인한다.
3. 앱이 Access Token과 Refresh Token을 안전한 저장소에 보관한다.
4. 이후 모든 보호 API에 `Authorization: Bearer {accessToken}`을 전송한다.
5. Access Token 만료 시 Refresh Token으로 갱신하고 실패하면 로그인 화면으로 이동한다.
6. 습득글 화면에서 발견 위치와 보관 위치를 입력한다. 발견 시간은 선택 입력이며 비우면 현재 시각이 사용된다.
7. 눈으로 확인한 공개 특징이 있으면 `observations`에 입력한다.
8. 사진은 별도 이미지 업로드 API로 전송하고 반환된 URL을 받는다.
9. 카테고리와 색상을 직접 알고 있으면 함께 입력하고, 모르면 둘 다 비운다. 둘 중 하나만 입력하면 거절된다.
10. 앱이 습득글 생성 API를 호출한다. 제목, 특징, 설명은 보내지 않는다.
11. 카테고리·색상을 입력했으면 서버가 텍스트 사실만 Ollama에 전달하고, 비웠으면 업로드된 사진과 위치·시간·관찰 정보를 Ollama Vision에 전달해 카테고리·색상까지 판별한다. 카테고리·색상을 비웠는데 `imageUrl`이 없으면 거절된다.
12. 서버가 LLM 결과를 검증하고 습득글을 저장한다.
13. 앱은 응답의 자동 생성 글을 상세 화면에 표시한다.

## 6. 습득글 생성 API

```http
POST /api/v1/found-posts
Authorization: Bearer {accessToken}
Content-Type: application/json
```

요청 예시 (카테고리·색상을 직접 아는 경우):

```json
{
  "category": "CARD",
  "color": "BLUE",
  "location": "강당 입구",
  "foundAt": "2026-07-13T14:20:00Z",
  "storageLocation": "학생회실",
  "observations": "앞면에 파란색 학교 로고와 모서리 흠집",
  "privateFeature": "학번 끝 두 자리 42",
  "verificationQuestion": "학번 끝 두 자리는 무엇인가요?",
  "imageUrl": "/uploads/example.jpg"
}
```

요청 예시 (사진으로 자동 판별하는 경우, `category`/`color` 생략):

```json
{
  "location": "강당 입구",
  "storageLocation": "학생회실",
  "observations": "모서리에 흠집",
  "imageUrl": "/uploads/example.jpg"
}
```

`category`/`color`를 생략하면 `imageUrl`이 필수이며 `foundAt`도 생략할 수 있다(서버가 현재 시각을 사용).

앱이 보내지 않는 필드:

- `title`
- `features`
- `description`

응답의 주요 구조:

```json
{
  "post": {
    "title": "강당 입구에서 발견된 파란색 학생증",
    "features": "앞면에 파란색 학교 로고와 모서리 흠집이 있습니다.",
    "description": "2026년 7월 13일 강당 입구에서 발견된 파란색 학생증입니다.",
    "contentGenerator": "ollama:qwen3-vl:4b"
  },
  "contentGeneration": {
    "generator": "ollama:qwen3-vl:4b",
    "sourceFields": [
      "category",
      "color",
      "location",
      "foundAt",
      "observations"
    ]
  },
  "analysisQueued": true
}
```

## 7. LLM 전달 정보

카테고리·색상을 직접 입력한 경우 LLM에는 아래 공개 사실만 전달한다.

| 필드 | 필수 | 설명 |
|---|---:|---|
| `category` | Y | Enum의 한국어 표시값 |
| `color` | Y | 색상 코드의 한국어 표시값 |
| `location` | Y | 발견 위치 |
| `foundAt` | Y | UTC ISO 8601 발견 시간 |
| `observations` | N | 사용자가 직접 확인한 공개 특징 |

카테고리·색상을 생략한 경우(사진 기반 자동 판별)에는 아래 사실과 이미지 바이너리를 함께 전달한다.

| 필드 | 필수 | 설명 |
|---|---:|---|
| 이미지 바이너리 | Y | `imageUrl`이 가리키는 업로드된 사진 |
| `location` | Y | 발견 위치 |
| `foundAt` | Y | UTC ISO 8601 발견 시간 |
| `observations` | N | 사용자가 직접 확인한 공개 특징 |

두 경우 모두 LLM에 전달하지 않는 정보:

- `storageLocation`
- `privateFeature`
- `verificationQuestion`
- 사용자 ID, 연락 정보
- `imageUrl` 문자열 자체(사진 기반 판별 시에는 파일 바이너리만 전달)

## 8. Ollama 요청 정책

```json
{
  "model": "qwen3-vl:4b",
  "stream": false,
  "think": false,
  "format": {
    "type": "object",
    "required": ["title", "features", "description"],
    "additionalProperties": false
  },
  "options": {
    "temperature": 0
  }
}
```

- 요청 경로: Ollama native `POST /api/chat`
- 콘텐츠 생성 제한 시간: 20초
- 응답 필드: `title`, `features`, `description`만 허용
- 일부 `qwen3-vl` 응답이 최종 구조화 JSON을 `message.thinking`에 넣는 경우가 있어, `message.content`가 비어 있을 때만 이를 최종 JSON 후보로 처리한다.
- 어떤 응답 위치를 사용하더라도 동일한 JSON·근거 검증을 적용하며 원문 사고 과정은 API 응답에 노출하지 않는다.

## 9. 근거 검증과 대체 처리

서버는 LLM 결과에 다음 검증을 적용한다.

1. 결과가 JSON 객체인지 확인한다.
2. 정확히 `title`, `features`, `description`만 존재하는지 확인한다.
3. 제목 100자, 특징·설명 2,000자 제한을 확인한다.
4. 장소, 색상, 카테고리 핵심어가 생성 결과에 포함되는지 확인한다.
5. 생성 결과의 모든 숫자가 입력 사실에 존재하는 숫자인지 확인한다.
6. 검증 실패, 타임아웃, HTTP 오류, 잘못된 JSON이면 결과를 폐기한다.

대체 생성기 `grounded-template-v1`은 동일한 공개 사실만 조합한다.

```text
제목: {location}에서 {color} {category} 습득
특징: {observations 또는 color + category}
설명: {foundAt}에 {location}에서 발견했습니다.
```

## 10. 이미지 전송 방식과 사진 기반 자동 분석

모바일 앱에서 이미지를 Base64로 전송하지 않는다.

```http
POST /api/v1/uploads/images
Authorization: Bearer {accessToken}
Content-Type: multipart/form-data
```

`image` 파일 필드로 JPEG, PNG, WebP를 업로드한다. 서버는 최대 10MB, 확장자, MIME 타입을 검사하고 EC2 영구 경로에 저장한 뒤 `/uploads/{fileName}` URL을 반환한다.

습득글 생성 요청에 `category`와 `color`를 함께 생략하면, 서버는 반드시 `imageUrl`을 요구하고 해당 이미지 파일을 읽어 Ollama Vision(`qwen3-vl:4b`)에 `location`, `foundAt`, `observations`와 함께 전달한다. LLM은 `category`(`ItemCategory` Enum 중 하나), `color`, `title`, `features`, `description`을 함께 생성한다. `category`, `color` 중 하나만 보내면 `422 VALIDATION_FAILED`로 거절한다.

- `category`/`color`를 모두 보내면 기존과 동일하게 텍스트 사실 기반 생성(§7~§9)을 사용하며 이미지는 분석에 사용하지 않는다.
- `category`/`color`를 모두 생략하면 이미지 기반 자동 분석을 사용하며, 생성기 값은 `ollama-vision:qwen3-vl:4b` 또는 실패 시 대체 생성기 `grounded-template-v1`이다. 대체 생성기 사용 시 `category`는 `ETC`, `color`는 `UNKNOWN`으로 저장된다.
- 이미지 기반 분석에서도 보관 위치, 비공개 특징, 확인 질문, 사용자 ID는 LLM에 전달하지 않는다.
- `foundAt`을 생략하면 서버가 요청 수신 시각(UTC)을 사용한다. `storageLocation`은 사진으로 알 수 없는 운영 정보이므로 계속 필수 입력이다.

## 11. 데이터 저장

`found_posts`의 관련 컬럼:

| 컬럼 | 설명 |
|---|---|
| `title` | 자동 생성 제목 |
| `features` | 자동 생성 공개 특징 |
| `description` | 자동 생성 설명 |
| `source_observations` | 사용자가 입력한 원본 공개 관찰 정보 |
| `content_generator` | 사용한 LLM 또는 대체 생성기 |

기존 데이터는 Alembic `f2d8c6a4e901`에서 기존 `features`를 `source_observations`로 이관하고 생성기를 `legacy/manual-v1`로 기록한다.

## 12. 수정 정책

다음 입력 사실을 수정하면 글 내용을 다시 생성하고 매칭 분석을 재요청한다.

- `category`
- `color`
- `location`
- `foundAt`
- `observations`

`title`, `features`, `description` 직접 수정 요청은 `422 VALIDATION_FAILED`로 거절한다. 보관 위치, 비공개 특징, 확인 질문, 이미지 URL 수정은 글 내용 재생성을 일으키지 않는다.

## 13. 앱 연동 기준

1. 첫 화면은 회원가입이 아니라 로그인 화면으로 구성한다.
2. Access Token은 API·Socket.IO에 사용하고 Refresh Token은 갱신 API에만 사용한다.
3. 토큰을 앱 로그에 출력하거나 일반 설정 저장소에 평문으로 남기지 않는다.
4. 앱 시작 시 저장된 토큰이 있으면 `/users/me`로 로그인 상태를 확인한다.
5. 습득글 작성 화면에서 제목·설명 입력란을 제거한다.
6. `observations`는 “사진에서 확인하기 어려운 특징”을 적는 선택 입력으로 제공한다.
7. 등록 버튼을 누르면 최대 20초 동안 생성 진행 상태를 표시한다.
8. 응답의 `post`를 그대로 상세 화면에 반영한다.
9. `contentGenerator`가 `grounded-template-v1`이어도 등록 성공으로 처리한다.
10. 사진은 먼저 업로드한 뒤 반환된 `imageUrl`을 습득글 요청에 포함한다.

## 14. 완료 기준

- 앱에서 로그인하고 Access/Refresh Token을 발급받을 수 있다.
- 보호 API가 유효한 Access Token 없이 호출되면 401로 거절된다.
- Access Token을 Refresh Token으로 갱신할 수 있다.
- 로그아웃 API 없이 앱에서 두 토큰이 삭제되고 로그인 화면으로 이동한다.
- 회원가입 화면과 호출 코드는 앱 범위에서 제외된다.
- 제목·특징·설명 없이 습득글을 생성할 수 있다.
- Ollama 요청에 `think: false`가 포함된다.
- 운영 환경에서 `ollama:qwen3-vl:4b` 생성 결과가 저장된다.
- 비공개 필드와 이미지가 LLM 요청에 포함되지 않는다.
- 입력에 없는 숫자를 추가한 LLM 결과가 거절된다.
- LLM 장애 시 입력 사실 기반 템플릿으로 정상 등록된다.
- 수동 콘텐츠 수정이 차단되고 입력 사실 변경 시 재생성된다.
- Postman Collection v2.1, HAR, API 명세가 같은 요청 계약을 사용한다.
- PostgreSQL 마이그레이션, Ruff, Pytest, Docker 빌드, EC2 배포가 통과한다.
